#!/usr/bin/env python3
"""
cpt_fetch_WISE.py - Fetch Wise statements via Playwright (semi-automatique)

Login semi-automatique : Chrome remplit les identifiants via GPG,
l'utilisateur valide le 2FA dans l'appli mobile Wise, puis le script
automatise la génération et le téléchargement du relevé.

Prérequis:
- pip install playwright
- playwright install chrome

Usage:
  ./cpt_fetch_WISE.py         # Mode normal
  ./cpt_fetch_WISE.py -v      # Mode verbeux

Workflow:
  1. Lance Chrome avec profil persistant (cookies de session conservés)
  2. Navigue vers la page des relevés Wise
  3. Si non connecté : remplit email/password (GPG), attend validation 2FA mobile
  4. Clique "Créer un Relevé"
  5. Sélectionne la période, toutes les devises, format XLSX
  6. Clique "Générer"
  7. Attend la génération puis clique "Télécharger"
  8. Sauve le ZIP dans dropbox/WISE/

Fichiers générés:
  - dropbox/WISE/statement_YYYY-MM-DD_YYYY-MM-DD.zip
"""

import sys
import os
import time
import subprocess
from datetime import datetime, timedelta

try:
    from playwright.sync_api import TimeoutError as PlaywrightTimeout
except ImportError:
    print("Module 'playwright' manquant. Installez avec: pip install playwright && playwright install chrome", file=sys.stderr)
    sys.exit(1)

from inc_fetch import BaseFetcher, fetch_main, config


# ============================================================================
# CONFIGURATION
# ============================================================================

# Timeouts
LOGIN_TIMEOUT_S = 300       # 5 min pour login + 2FA mobile
DOWNLOAD_TIMEOUT_S = 120    # 2 min pour génération + téléchargement



class WiseFetcher(BaseFetcher):
    def __init__(self, verbose=False):
        super().__init__(caller_file=__file__, verbose=verbose)
        # Note: WISE uses download_path as additional state tracking,
        # but also inherits self.downloads from BaseFetcher
        self.download_path = None
        self.max_days_back = config.getint('WISE', 'max_days_back',
                                           fallback=config.getint('general', 'max_days_back', fallback=90))

        # Compute WISE_STATEMENTS URL from base_url
        self.wise_statements = f"{self.base_url}/balances/statements/balance-statement?schedule=monthly"

    def run(self):
        """Main workflow: login, create statement, download.

        Returns:
            True if successful, False otherwise
        """
        try:
            # 1. Login (interactif si nécessaire)
            if not self.wait_for_login():
                self.logger.error("Échec de la connexion")
                return False

            # 3. Créer le relevé (formulaire)
            if not self.create_statement():
                self.logger.error("Échec création du relevé")
                return False

            # 4. Télécharger le ZIP
            result = self.download_statement()
            if not result:
                self.logger.error("Échec téléchargement")
                return False

            # 5. Résumé
            self.logger.info("=" * 50)
            self.logger.info(f"Fichier:     {result.name}")
            self.logger.info(f"Destination: {self.dropbox_dir}")
            self.logger.info("=" * 50)

            self.logger.info(f"Collecte {self.site_name} terminée")
            return True

        except KeyboardInterrupt:
            self.logger.warning("Interrompu par l'utilisateur")
            return False
        except Exception as e:
            self.logger.error(f"Erreur inattendue: {e}")
            if self.debug:
                import traceback
                traceback.print_exc()
            return False

    def dismiss_cookies(self):
        """Ferme la popup cookies (Reject/Refuser en priorité)."""
        try:
            cookie_btn = self.page.locator(
                "button:has-text('Reject'), "
                "button:has-text('Refuser'), "
                "button:has-text('Decline'), "
                "button:has-text('Tout refuser'), "
                "button:has-text('Reject all'), "
                "button:has-text('Deny')"
            )
            if cookie_btn.count() > 0:
                btn_text = cookie_btn.first.inner_text().strip()[:60]
                self.logger.debug(f"dismiss_cookies: clic sur '{btn_text}'")
                cookie_btn.first.click()
                self.logger.info("Popup cookies fermée (refusé)")
                time.sleep(1)
                return True

            # Fallback : accepter si pas de bouton refuser
            # NB: text-is('OK') au lieu de has-text('OK') car "Facebook" contient "ok"
            accept_btn = self.page.locator(
                "button:has-text('Accept'), "
                "button:has-text('Accepter'), "
                "button:text-is('OK'), "
                "button:has-text('Got it')"
            )
            if accept_btn.count() > 0:
                btn_text = accept_btn.first.inner_text().strip()[:60]
                self.logger.debug(f"dismiss_cookies fallback: clic sur '{btn_text}'")
                accept_btn.first.click()
                self.logger.info("Popup cookies fermée (accepté, pas de bouton refuser)")
                time.sleep(1)
                return True
        except Exception as e:
            self.logger.debug(f"Pas de popup cookies ou erreur: {e}")
        return False

    def wait_for_login(self):
        """Navigue vers la page des relevés et gère le login si nécessaire.

        Si la session est active (profil persistant), on arrive directement
        sur la page des relevés. Sinon, on remplit le login et on attend la 2FA mobile.

        Returns:
            True si connecté, False si timeout
        """
        self.logger.info("Navigation vers Wise...")
        self.page.goto(self.wise_statements, wait_until="domcontentloaded")
        time.sleep(5)

        # Fermer cookies dès que possible
        self.dismiss_cookies()

        try:
            current_url = self.page.evaluate("window.location.href")
        except Exception:
            current_url = self.page.url
        self.logger.debug(f"URL après navigation: {current_url}")

        # Si on est sur la page des relevés (pas redirigé vers login)
        if 'login' not in current_url and 'authorize' not in current_url:
            self.logger.info("Déjà connecté (session existante)")
            return True

        # On est sur la page de login → login requis
        return self._prompt_and_wait_login()

    def _fill_login(self):
        """Remplit le formulaire de login avec les credentials GPG.

        Returns:
            True si les credentials ont été remplis, False sinon
        """
        username, password = self.load_gpg_credentials()
        if not username or not password:
            self.logger.warning("Credentials non trouvés — login manuel requis")
            return False

        try:
            self.page.wait_for_load_state("domcontentloaded", timeout=10000)
        except PlaywrightTimeout:
            pass
        time.sleep(2)
        self.dismiss_cookies()

        # Vérifier qu'on est bien sur wise.com (pas redirigé vers Facebook/Google)
        current_url = self.page.url
        if 'wise.com' not in current_url:
            self.logger.warning(f"Redirigé hors de Wise: {current_url[:80]}")
            self.page.goto(f"{self.base_url}/login", wait_until="domcontentloaded")
            time.sleep(3)
            if 'wise.com' not in self.page.url:
                self.logger.error("Impossible de revenir sur Wise")
                return False

        try:
            # Champ email
            email_input = self.page.locator(
                "input[name='email'], input[type='email'], input[id*='email'], "
                "input[autocomplete='username'], input[autocomplete='email']"
            )
            if email_input.count() > 0:
                email_input.first.wait_for(state="visible", timeout=5000)
                email_input.first.fill(username)
                time.sleep(0.5)
                self.logger.debug("Email rempli")
            else:
                self.logger.debug("Champ email non trouvé")
                return False

            # Champ mot de passe
            pwd_input = self.page.locator("input[name='password'], input[type='password']")
            if pwd_input.count() > 0:
                pwd_input.first.fill(password)
                self.logger.debug("Mot de passe rempli")
            else:
                self.logger.debug("Champ mot de passe non trouvé")
                return False

            # Soumettre le formulaire (profil toujours propre grâce au
            # nettoyage cookies → pas de risque de bouton Facebook)
            submit_btn = self.page.locator(
                "button[type='submit'], "
                "button:text-is('Log in'), "
                "button:text-is('Se connecter')"
            )
            if submit_btn.count() > 0:
                submit_btn.first.click()
                self.logger.info("Formulaire soumis")
            else:
                pwd_input.first.press("Enter")
                self.logger.info("Formulaire soumis (Enter)")

            return True
        except Exception as e:
            self.logger.warning(f"Erreur remplissage login: {e}")
            return False

    def _read_clipboard(self):
        """Lit le contenu du clipboard via xclip.

        Returns:
            str: contenu du clipboard, ou '' si erreur
        """
        try:
            result = subprocess.run(
                ['xclip', '-selection', 'clipboard', '-o'],
                capture_output=True, text=True, timeout=2
            )
            return result.stdout.strip() if result.returncode == 0 else ''
        except Exception:
            return ''

    def _detect_2fa_step(self):
        """Détecte le type de 2FA affiché sur la page.

        Returns:
            'email' si vérification par email, 'mobile' si appli mobile,
            'unknown' si non identifié, None si plus sur page login
        """
        try:
            current_url = self.page.evaluate("window.location.href")
        except Exception:
            current_url = self.page.url

        if 'login' not in current_url and 'authorize' not in current_url:
            return None

        try:
            body = self.page.locator("body").inner_text(timeout=3000).lower()
        except Exception:
            return 'unknown'

        # Page de login encore affichée (soumission en cours) → ignorer
        login_kw = ['se connecter', 'log in', 'mot de passe', 'password',
                     'inscrivez-vous', 'sign up']
        if any(kw in body for kw in login_kw):
            return None

        # Mots-clés vérification email
        email_kw = ['vérifiez vos e-mails', 'check your email',
                     'vérifie ton e-mail', 'vérifiez votre e-mail',
                     'nouvel appareil', 'new device',
                     'sent you an email', 'envoyé un e-mail',
                     "renvoyer l'e-mail", 'resend email',
                     'boîte de réception', 'check your inbox']
        if any(kw in body for kw in email_kw):
            return 'email'

        # Mots-clés validation mobile
        mobile_kw = ['en attente de votre réponse', 'waiting for you',
                      'appli wise', 'wise app', "oui, c'est moi", 'yes, it was me',
                      "demande d'autorisation", 'approve this']
        if any(kw in body for kw in mobile_kw):
            return 'mobile'

        return 'unknown'

    def _poll_login(self, timeout_s):
        """Attend que l'URL quitte la page de login.

        Détecte le type de 2FA (mobile, email, ou les deux en séquence)
        et surveille le clipboard pour les liens Wise (vérification email).

        Returns:
            True si connecté, False si timeout
        """
        # Vider le clipboard pour éviter de naviguer vers un ancien lien
        try:
            subprocess.run(['xclip', '-selection', 'clipboard'],
                           input='', text=True, timeout=2)
        except Exception:
            pass

        start_time = time.time()
        last_url = ""
        last_clipboard = ""
        last_step = None

        while time.time() - start_time < timeout_s:
            try:
                current_url = self.page.evaluate("window.location.href")
            except Exception:
                current_url = self.page.url
            if current_url != last_url:
                self.logger.debug(f"URL courante: {current_url}")
                last_url = current_url

            # Si on n'est plus sur la page de login → connecté
            if 'login' not in current_url and 'authorize' not in current_url:
                self.logger.info("Connexion détectée")
                time.sleep(2)
                self.dismiss_cookies()
                return True

            # Détecter l'étape 2FA et afficher le message adapté
            step = self._detect_2fa_step()
            if step and step != last_step:
                # Ne pas rétrograder d'un type spécifique vers 'unknown' (page de transition)
                if step == 'unknown' and last_step in ('mobile', 'email'):
                    pass
                else:
                    last_step = step
                    if step == 'email':
                        self.logger.alert("VÉRIFICATION EMAIL — Copie le lien de l'email Wise (clic droit → Copier le lien)")
                    elif step == 'mobile':
                        self.logger.alert("VALIDATION MOBILE — Approuve dans l'appli Wise (« Oui, c'est moi »)")
                    elif step == 'unknown':
                        self.logger.alert("VALIDATION 2FA — Approuve dans l'appli mobile, ou copie le lien de l'email Wise")

            # Vérifier les autres onglets (redirection post-2FA dans un nouvel onglet)
            for p in self.context.pages:
                if p != self.page:
                    try:
                        p_url = p.evaluate("window.location.href")
                    except Exception:
                        p_url = p.url
                    if 'wise.com' in p_url and 'login' not in p_url:
                        self.logger.debug(f"Nouvel onglet post-login: {p_url}")
                        self.page = p
                        self.logger.info("Connexion détectée (nouvel onglet)")
                        time.sleep(2)
                        self.dismiss_cookies()
                        return True

            # Surveiller le clipboard pour un lien Wise (vérification email)
            clipboard = self._read_clipboard()
            if clipboard and clipboard != last_clipboard and 'wise.com' in clipboard:
                last_clipboard = clipboard
                self.logger.info("Lien Wise détecté dans le clipboard")
                try:
                    # Ouvrir dans un nouvel onglet (comme l'utilisateur le ferait)
                    # pour ne pas casser le flow de l'onglet principal
                    new_tab = self.context.new_page()
                    new_tab.goto(clipboard, wait_until="domcontentloaded", timeout=30000)
                    time.sleep(3)

                    # Cliquer "Continuer" / "Continue" si présent
                    continue_btn = new_tab.locator(
                        "button:has-text('Continuer'), "
                        "button:has-text('Continue'), "
                        "a:has-text('Continuer'), "
                        "a:has-text('Continue')"
                    )
                    if continue_btn.count() > 0:
                        continue_btn.first.click()
                        self.logger.info("Bouton 'Continuer' cliqué (nouvel onglet)")
                        time.sleep(3)

                    new_tab.close()
                    self.logger.info("Nouvel onglet fermé — attente déblocage onglet principal")
                    time.sleep(5)
                except Exception as e:
                    self.logger.debug(f"Navigation clipboard: {e}")

            time.sleep(2)

        return False

    def _prompt_and_wait_login(self):
        """Passe en headed et attend la validation manuelle (2FA mobile, login...)."""
        # Relancer en headed seulement si actuellement headless
        # En mode TEST (debug=True), le navigateur est déjà headed
        if not (self.debug or self._headed):
            self.relaunch_headed()

        self.page.goto(f"{self.base_url}/login", wait_until="domcontentloaded")
        time.sleep(3)
        self.dismiss_cookies()

        # Vérifier si la session est active après relance (profil persistant)
        try:
            check_url = self.page.evaluate("window.location.href")
        except Exception:
            check_url = self.page.url
        if 'login' not in check_url and 'authorize' not in check_url:
            self.logger.info("Session active après relance headed")
            return True

        # Remplir le login
        auto_filled = self._fill_login()
        if not auto_filled:
            self.logger.alert("CONNEXION REQUISE — Connecte-toi manuellement dans la fenêtre Wise")

        if self._poll_login(LOGIN_TIMEOUT_S):
            return True

        self.logger.error(f"Timeout login ({LOGIN_TIMEOUT_S}s)")
        return False

    def create_statement(self):
        """Remplit le formulaire pour créer un relevé.

        Étapes :
        1. S'assurer d'être sur la page des relevés
        2. Cliquer "Créer un Relevé"
        3. Configurer dates, devises, format XLSX
        4. Cliquer "Générer"

        Returns:
            True si le relevé a été demandé, False sinon
        """
        # S'assurer d'être sur la bonne page
        current_url = self.page.url
        if 'statements' not in current_url:
            self.logger.info("Navigation vers la page des relevés...")
            self.page.goto(self.wise_statements, wait_until="domcontentloaded")
            time.sleep(3)
            self.dismiss_cookies()

        # Chercher et cliquer "Créer..." / "Get statement" / "Create statement"
        create_btn = self.page.locator(
            ":is(button, a, div, span)[role='button']:has-text('Créer'), "
            ":is(button, a, div, span)[role='button']:has-text('Get statement'), "
            ":is(button, a, div, span)[role='button']:has-text('Create statement'), "
            "button:has-text('Créer'), "
            "button:has-text('Get statement'), "
            "button:has-text('Create statement'), "
            "a:has-text('Créer'), "
            "a:has-text('Get statement'), "
            "a:has-text('Create statement')"
        )
        try:
            create_btn.first.wait_for(state="visible", timeout=10000)
        except PlaywrightTimeout:
            self.logger.error("Bouton 'Créer un relevé' introuvable")
            self._dump_page_debug("no_create_btn")
            return False

        create_btn.first.click()
        self.logger.info("Bouton 'Créer un Relevé' cliqué")
        time.sleep(3)

        # Configurer la période
        self._set_date_range()

        # Sélectionner toutes les devises
        self._select_all_currencies()

        # Sélectionner format XLSX
        self._select_xlsx_format()

        # Cliquer "Générer" / "Generate"
        generate_btn = self.page.locator(
            "button:has-text('Générer'), "
            "button:has-text('Generate'), "
            "button[type='submit']"
        )
        if generate_btn.count() == 0:
            self.logger.error("Bouton 'Générer' introuvable")
            self._dump_page_debug("no_generate_btn")
            return False

        generate_btn.first.click()
        self.logger.info("Relevé demandé (Générer cliqué)")
        time.sleep(3)

        # Vérifier que le formulaire a bien été soumis (pas d'erreur de validation)
        validation_error = self.page.locator("text='Champ obligatoire'")
        if validation_error.count() > 0:
            self.logger.error("Formulaire non soumis — champ obligatoire manquant (devises ?)")
            self._dump_page_debug("form_validation_error")
            return False

        return True

    def _set_date_range(self):
        """Configure la plage de dates du relevé à J-max_days_back → aujourd'hui.

        Wise utilise un date picker custom (bouton np-date-trigger → calendrier).
        Les jours ont un aria-label au format "DD/MM/YYYY".
        On navigue mois par mois avec le bouton "précédent mois" puis on clique le jour.
        """
        start_date = datetime.now() - timedelta(days=self.max_days_back)
        target_label = start_date.strftime('%d/%m/%Y')
        self.logger.info(f"Période cible: {target_label} → aujourd'hui ({self.max_days_back}j)")

        # Cliquer le bouton "Date de début" (np-date-trigger)
        from_btn = self.page.locator("button.np-date-trigger").first
        try:
            from_btn.wait_for(state="visible", timeout=5000)
        except PlaywrightTimeout:
            self.logger.warning("Bouton date de début introuvable — dates par défaut")
            return
        from_btn.click()
        time.sleep(1)

        # Attendre que le calendrier s'ouvre
        calendar = self.page.locator("table.tw-date-lookup-calendar")
        try:
            calendar.wait_for(state="visible", timeout=5000)
        except PlaywrightTimeout:
            self.logger.warning("Calendrier non ouvert — dates par défaut")
            return

        # Naviguer vers le mois cible en cliquant "précédent mois"
        prev_btn = self.page.locator("button[aria-label='précédent mois']")
        for i in range(12):  # max 12 mois en arrière
            # Chercher le jour cible par aria-label
            day_btn = self.page.locator(f"button.tw-date-lookup-day-option[aria-label='{target_label}']")
            if day_btn.count() > 0:
                day_btn.first.click()
                self.logger.info(f"Date de début: {target_label}")
                time.sleep(1)
                return

            # Pas trouvé → reculer d'un mois
            if prev_btn.count() > 0:
                prev_btn.first.click()
                time.sleep(0.5)
            else:
                break

        self.logger.warning(f"Jour {target_label} non trouvé dans le calendrier — dates par défaut")
        self.page.keyboard.press("Escape")
        time.sleep(0.5)

    def _select_all_currencies(self):
        """Sélectionne toutes les devises (EUR, USD, SGD, SEK).

        Wise utilise un combobox (bouton role=combobox, classe np-button-input)
        avec placeholder "Sélectionnez des devises". Au clic, un dropdown
        s'ouvre avec les devises disponibles sous forme de checkboxes.
        """
        # Ouvrir le dropdown devises
        currency_combo = self.page.locator(
            "button[role='combobox']:near(:text('Vos devises'))"
        )
        if currency_combo.count() == 0:
            # Fallback : le combobox avec placeholder
            currency_combo = self.page.locator(
                "button[role='combobox']:has-text('Sélectionnez des devises'), "
                "button[role='combobox']:has-text('Select currencies')"
            )
        if currency_combo.count() == 0:
            self.logger.error("Dropdown devises introuvable")
            return

        # Ouvrir le dropdown (dialog headlessui)
        currency_combo.first.click()
        time.sleep(2)

        # Cliquer "Tout sélectionner" / "Select all" (texte du bouton dans le dialog)
        select_all = self.page.locator(
            "button:has-text('Tout sélectionner'), "
            "button:has-text('Select all')"
        )
        if select_all.count() > 0:
            select_all.first.click()
            self.logger.info("Toutes les devises sélectionnées")
            time.sleep(0.5)
        else:
            self.logger.warning("'Tout sélectionner' non trouvé")
            self._dump_page_debug("no_select_all_btn")

        # Fermer le dropdown
        self.page.keyboard.press("Escape")
        time.sleep(0.5)

    def _select_xlsx_format(self):
        """Sélectionne le format XLSX (requis par cpt_format_WISE.py).

        Wise utilise un combobox (bouton role=combobox) dans la section
        "Format du fichier", pré-sélectionné sur "PDF". On l'ouvre et
        on sélectionne "XLSX".
        """
        # Ouvrir le dropdown format
        format_combo = self.page.locator(
            "button[role='combobox']:near(:text('Format du fichier')), "
            "button[role='combobox']:near(:text('File format'))"
        )
        if format_combo.count() == 0:
            # Fallback : combobox contenant "PDF"
            format_combo = self.page.locator(
                "button[role='combobox']:has-text('PDF')"
            )
        if format_combo.count() == 0:
            self.logger.warning("Dropdown format introuvable — PDF par défaut ?")
            return False

        format_combo.first.click()
        time.sleep(1)
        self.logger.debug("Dropdown format ouvert")

        # Sélectionner XLSX
        xlsx_option = self.page.locator(
            "[role='option']:has-text('XLSX'), "
            "[role='listbox'] :has-text('XLSX')"
        )
        if xlsx_option.count() > 0:
            xlsx_option.first.click()
            self.logger.info("Format XLSX sélectionné")
            time.sleep(0.5)
            return True

        # Fallback : Excel
        excel_option = self.page.locator(
            "[role='option']:has-text('Excel'), "
            "[role='listbox'] :has-text('Excel')"
        )
        if excel_option.count() > 0:
            excel_option.first.click()
            self.logger.info("Format Excel sélectionné")
            time.sleep(0.5)
            return True

        self.logger.warning("Option XLSX/Excel non trouvée dans le dropdown")
        return False

    def download_statement(self):
        """Attend la génération du relevé et télécharge le ZIP.

        Après avoir cliqué "Générer", Wise peut :
        - Afficher une nouvelle page avec un bouton "Télécharger"
        - Ou rediriger vers une page de téléchargement

        Returns:
            Path du fichier téléchargé ou None
        """
        self.dropbox_dir.mkdir(parents=True, exist_ok=True)

        # Attendre le bouton "Télécharger" / "Download"
        self.logger.info("Attente du relevé (génération en cours)...")
        download_btn = self.page.locator(
            "button:has-text('Télécharger'), "
            "button:has-text('Download'), "
            "a:has-text('Télécharger'), "
            "a:has-text('Download')"
        )

        try:
            download_btn.first.wait_for(state="visible", timeout=DOWNLOAD_TIMEOUT_S * 1000)
        except PlaywrightTimeout:
            self.logger.error(f"Bouton 'Télécharger' non trouvé après {DOWNLOAD_TIMEOUT_S}s")
            self._dump_page_debug("no_download_btn")
            return None

        self.logger.info("Bouton 'Télécharger' trouvé")
        time.sleep(1)

        # Télécharger avec capture de l'événement download
        try:
            with self.page.expect_download(timeout=60000) as download_info:
                download_btn.first.click()

            download = download_info.value
            original_name = download.suggested_filename
            dest_path = self.dropbox_dir / original_name

            download.save_as(str(dest_path))

            self.logger.info(f"Téléchargé: {original_name}")
            self.download_path = dest_path
            self.downloads.append(dest_path)  # Also track in BaseFetcher's list
            return dest_path

        except PlaywrightTimeout:
            self.logger.error("Timeout téléchargement")
            return None
        except Exception as e:
            self.logger.error(f"Erreur téléchargement: {e}")
            return None


if __name__ == '__main__':
    sys.exit(fetch_main(WiseFetcher, description='Fetch Wise statements via Playwright (semi-automatique)'))
