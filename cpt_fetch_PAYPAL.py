#!/usr/bin/env python3
"""
cpt_fetch_PAYPAL.py - Récupération automatique des transactions PayPal

Login semi-automatique : Chrome remplit les identifiants via GPG,
l'utilisateur valide le 2FA SMS, puis le script télécharge le rapport CSV.

Prérequis:
- pip install playwright
- playwright install chrome

Usage:
  ./cpt_fetch_PAYPAL.py         # Mode normal
  ./cpt_fetch_PAYPAL.py -v      # Mode verbeux

Workflow:
  1. Lance Chrome avec profil persistant (cookies de session conservés)
  2. Navigue vers paypal.com/signin
  3. Si non connecté : remplit email/password (GPG), gère 2FA SMS
  4. Navigue vers /reports/dlog (rapports d'activité)
  5. Crée un rapport CSV sur la période configurée
  6. Attend la génération puis télécharge le CSV

Fichiers générés:
  - dropbox/PAYPAL/*.csv (transactions)
"""

import sys
import time
from datetime import date, timedelta

from inc_fetch import BaseFetcher, fetch_main, config, DEBUG

try:
    from playwright.sync_api import TimeoutError as PlaywrightTimeout
except ImportError:
    print("Module 'playwright' manquant. Installez avec: pip install playwright && playwright install chrome", file=sys.stderr)
    sys.exit(1)


# ============================================================================
# CONFIGURATION
# ============================================================================

LOGIN_TIMEOUT_S = 300       # 5 min pour login + 2FA
DOWNLOAD_TIMEOUT_S = 60     # 1 min pour téléchargement
REPORT_POLL_INTERVAL_S = 5  # Intervalle de polling génération rapport
REPORT_MAX_WAIT_S = 300     # 5 min max pour la génération du rapport


class PayPalFetcher(BaseFetcher):
    def __init__(self, verbose=False):
        super().__init__(
            caller_file=__file__,
            verbose=verbose,
        )
        self.max_days_back = config.getint('PAYPAL', 'max_days_back',
                                           fallback=config.getint('general', 'max_days_back', fallback=90))

    # ========================================================================
    # LOGIN
    # ========================================================================

    def wait_for_login(self):
        """Navigue vers PayPal et gère le login si nécessaire.

        Returns:
            True si connecté, False si timeout
        """
        self.logger.info("Navigation vers PayPal...")
        self.page.goto(f"{self.base_url}/myaccount/summary",
                       wait_until="domcontentloaded", timeout=30000)
        time.sleep(3)

        current_url = self.page.evaluate("window.location.href")
        self.logger.debug(f"URL après navigation: {current_url}")

        if self._is_logged_in(current_url):
            self.logger.info("Déjà connecté (session existante)")
            return True

        return self._do_login()

    def _is_logged_in(self, url=None):
        """Vérifie si on est sur une page authentifiée PayPal."""
        if url is None:
            url = self.page.evaluate("window.location.href")
        return 'paypal.com/myaccount' in url or 'paypal.com/reports' in url

    def _do_login(self):
        """Remplit le login, gère la 2FA SMS, attend la connexion.

        Returns:
            True si connecté, False sinon
        """
        # Relancer en headed si nécessaire (pour 2FA / CAPTCHA)
        if not (self.debug or self._headed):
            self.relaunch_headed()

        # Naviguer vers la page de login
        self.page.goto(f"{self.base_url}/signin",
                       wait_until="domcontentloaded", timeout=30000)
        time.sleep(3)

        current_url = self.page.evaluate("window.location.href")

        # Si déjà connecté après relance headed (profil persistant)
        if self._is_logged_in(current_url):
            self.logger.info("Session active après relance headed")
            return True

        # Attendre que le CAPTCHA soit résolu si présent
        if 'validatecaptcha' in current_url:
            self.logger.alert("CAPTCHA DÉTECTÉ — Résous-le dans Chrome")
            if not self._wait_for_captcha_resolved():
                return False

        # Remplir les credentials (si le formulaire est visible)
        if not self._fill_login():
            self.logger.alert("CONNEXION REQUISE — Connecte-toi manuellement dans Chrome")

        # Attendre : soit la connexion directe, soit la 2FA
        return self._wait_for_authenticated()

    def _wait_for_captcha_resolved(self):
        """Attend que le CAPTCHA soit résolu et le formulaire login apparaisse.

        Returns:
            True si formulaire login accessible, False si timeout
        """
        start = time.time()
        while time.time() - start < LOGIN_TIMEOUT_S:
            try:
                current_url = self.page.evaluate("window.location.href")
            except Exception:
                time.sleep(3)
                continue

            # CAPTCHA résolu → redirigé vers signin ou déjà connecté
            if self._is_logged_in(current_url):
                return True
            if 'validatecaptcha' not in current_url:
                self.logger.info("CAPTCHA résolu")
                time.sleep(2)
                return True

            time.sleep(3)

        self.logger.error(f"Timeout CAPTCHA ({LOGIN_TIMEOUT_S}s)")
        return False

    def _fill_login(self):
        """Remplit email + mot de passe et clique Connexion.

        Returns:
            True si formulaire soumis, False sinon
        """
        username, password = self.load_gpg_credentials()
        if not username or not password:
            self.logger.warning("Credentials non trouvés — login manuel requis")
            return False

        try:
            # Champ email (plusieurs variantes PayPal)
            email_input = self.page.locator(
                "input#email, input[name='login_email'], "
                "input[type='email'], input[name='email']"
            )
            email_input.first.wait_for(state="visible", timeout=15000)
            email_input.first.fill(username)
            self.logger.debug("Email rempli")
            time.sleep(0.5)

            # Champ mot de passe (peut être sur la même page ou après clic "Suivant")
            pwd_input = self.page.locator(
                "input#password, input[name='login_password'], "
                "input[type='password']"
            )
            if pwd_input.count() > 0 and pwd_input.first.is_visible():
                pwd_input.first.fill(password)
                self.logger.debug("Mot de passe rempli")
            else:
                # PayPal affiche parfois email seul puis password sur page suivante
                next_btn = self.page.locator(
                    "button#btnNext, button:has-text('Suivant'), "
                    "button:has-text('Next')"
                )
                if next_btn.count() > 0 and next_btn.first.is_visible():
                    next_btn.first.click()
                    self.logger.debug("Clic Suivant (page email seul)")
                    time.sleep(2)
                    pwd_input.first.wait_for(state="visible", timeout=10000)
                    pwd_input.first.fill(password)
                    self.logger.debug("Mot de passe rempli (page 2)")

            time.sleep(0.5)

            # Bouton Connexion
            login_btn = self.page.locator(
                "button#btnLogin, button:has-text('Connexion'), "
                "button:has-text('Log In'), button:has-text('Se connecter')"
            )
            if login_btn.count() > 0:
                login_btn.first.click()
                self.logger.info("Formulaire soumis")
            else:
                pwd_input.first.press("Enter")
                self.logger.info("Formulaire soumis (Enter)")

            return True

        except Exception as e:
            self.logger.warning(f"Erreur remplissage login: {e}")
            return False

    def _wait_for_authenticated(self):
        """Attend la connexion, gère la 2FA SMS si détectée.

        Returns:
            True si connecté, False si timeout
        """
        start_time = time.time()
        tfa_attempted = False

        while time.time() - start_time < LOGIN_TIMEOUT_S:
            try:
                current_url = self.page.evaluate("window.location.href")
            except Exception:
                # Page fermée/rechargée — réessayer
                time.sleep(3)
                continue

            # Connecté ?
            if self._is_logged_in(current_url):
                self.logger.info("Connexion détectée")
                return True

            # Page 2FA ? Tenter une seule fois
            if not tfa_attempted and ('authflow' in current_url or 'challenges' in current_url):
                tfa_attempted = True
                self._handle_2fa()
                time.sleep(5)
                continue

            time.sleep(3)

        self.logger.error(f"Timeout login ({LOGIN_TIMEOUT_S}s)")
        return False

    def _handle_2fa(self):
        """Gère la 2FA PayPal : choix SMS + saisie code.

        Returns:
            True si code soumis, False sinon
        """
        current_url = self.page.evaluate("window.location.href")

        # Étape 1 : page de choix de méthode (SMS / WhatsApp / Appel)
        if 'challenges/sms' not in current_url:
            # On est probablement sur la page de choix → sélectionner SMS et cliquer Suivant
            try:
                sms_option = self.page.locator("text=Recevoir un SMS")
                if sms_option.count() > 0:
                    sms_option.first.click()
                    self.logger.debug("Option SMS sélectionnée")
                    time.sleep(0.5)

                next_btn = self.page.locator("button:has-text('Suivant'), button:has-text('Next')")
                if next_btn.count() > 0:
                    next_btn.first.click()
                    self.logger.info("2FA SMS demandé")
                    time.sleep(3)
            except Exception as e:
                self.logger.debug(f"Erreur sélection SMS: {e}")

        # Étape 2 : saisie du code (6 chiffres dans des champs séparés)
        code_inputs = self.page.locator(
            "input[type='tel'], input[type='number'], "
            "input[inputmode='numeric'], input[autocomplete='one-time-code']"
        )

        try:
            code_inputs.first.wait_for(state="visible", timeout=10000)
        except PlaywrightTimeout:
            self.logger.debug("Champs code 2FA non détectés")
            self._dump_page_debug("2fa_no_fields", force=True)
            return False

        field_count = code_inputs.count()
        self.logger.info(f"Champs code 2FA détectés: {field_count}")
        self.logger.alert("CODE SMS REQUIS — Tape le code reçu par SMS puis Entrée")

        try:
            code = input("").strip()
        except EOFError:
            return False

        if not code or not code.isdigit():
            self.logger.warning(f"Code invalide: '{code}'")
            return False

        # Saisir le code
        if field_count == 1:
            code_inputs.first.fill(code)
        else:
            # Champs séparés (un chiffre par champ)
            digits = list(code)
            for i in range(min(len(digits), field_count)):
                code_inputs.nth(i).click()
                code_inputs.nth(i).fill(digits[i])
                time.sleep(0.1)

        self.logger.info(f"Code 2FA saisi ({len(code)} chiffres)")
        time.sleep(0.5)

        # Soumettre
        submit_btn = self.page.locator(
            "button:has-text('Envoyer'), button:has-text('Submit'), "
            "button:has-text('Confirmer'), button:has-text('Verify'), "
            "button[type='submit']"
        )
        if submit_btn.count() > 0:
            submit_btn.first.click()
            self.logger.info("Code 2FA soumis")
        else:
            code_inputs.first.press("Enter")
            self.logger.info("Code 2FA soumis (Enter)")

        return True

    # ========================================================================
    # RAPPORT CSV
    # ========================================================================

    def fetch_report(self):
        """Crée et télécharge un rapport CSV depuis /reports/dlog.

        Workflow :
        1. Naviguer vers la page des rapports
        2. Configurer période et format CSV
        3. Cliquer "Créer le rapport"
        4. Attendre que le rapport soit prêt (polling)
        5. Télécharger le CSV

        Returns:
            Path du fichier CSV téléchargé ou None
        """
        self.logger.info("Navigation vers les rapports...")
        self.page.goto(f"{self.base_url}/reports/dlog",
                       wait_until="domcontentloaded", timeout=30000)
        time.sleep(3)

        # Vérifier qu'on est sur la page des rapports
        current_url = self.page.evaluate("window.location.href")
        if 'reports' not in current_url:
            self.logger.error(f"Page rapports inaccessible: {current_url}")
            return None

        self.logger.info("Page rapports accessible")

        # Sélectionner "Toutes les transactions" comme type de rapport
        self._select_transaction_type()

        # Configurer la période
        end_date = date.today()
        start_date = end_date - timedelta(days=self.max_days_back)

        if not self._set_report_period(start_date, end_date):
            self.logger.warning("Période par défaut utilisée")

        # Cliquer "Créer le rapport"
        create_btn = self.page.locator(
            "button:has-text('Créer le rapport'), button:has-text('Create report'), "
            "button:has-text('Request report')"
        )
        try:
            create_btn.first.wait_for(state="visible", timeout=10000)
        except PlaywrightTimeout:
            self.logger.error("Bouton 'Créer le rapport' introuvable")
            self._dump_page_debug("report_no_create_btn", force=True)
            return None

        create_btn.first.click()
        self.logger.info(f"Rapport demandé: {start_date} → {end_date}")
        time.sleep(3)

        # Attendre la transition Envoyé → Télécharger puis télécharger
        return self._wait_and_download_report()

    def _select_transaction_type(self):
        """Sélectionne 'Toutes les transactions' dans le dropdown type de rapport."""
        try:
            # Le dropdown est un <select> standard sans name/aria-label
            # On le repère par ses options : "Toutes les transactions", "Paiements terminés", etc.
            selects = self.page.locator('select:visible').all()
            for sel in selects:
                opts = [o.get_attribute('value') or '' for o in sel.locator('option').all()]
                if 'All transactions' in opts:
                    sel.select_option(value='All transactions')
                    self.logger.info("Type 'Toutes les transactions' sélectionné")
                    time.sleep(1)
                    return
            self.logger.debug("Dropdown type non trouvé")
        except Exception as e:
            self.logger.debug(f"Sélection type: {e}")

    def _set_report_period(self, start_date, end_date):
        """Configure la période du rapport via les champs date De/Au.

        Le dropdown période contient des options prédéfinies ET deux champs
        date input#start (De) et input#end (Au) au format D/M/YYYY.

        Args:
            start_date: Date de début
            end_date: Date de fin

        Returns:
            True si période configurée, False sinon
        """
        try:
            # Ouvrir le dropdown période pour rendre les champs date visibles
            period_input = self.page.locator('input#text-input-undefined')
            if period_input.count() == 0:
                self.logger.debug("Champ période non trouvé")
                return False

            period_input.click()
            time.sleep(1)

            # Remplir les champs De/Au (format PayPal : D/M/YYYY sans zéro devant)
            start_input = self.page.locator('input#start')
            end_input = self.page.locator('input#end')

            if start_input.count() == 0 or end_input.count() == 0:
                self.logger.debug("Champs date De/Au non trouvés")
                return False

            start_str = f"{start_date.day}/{start_date.month}/{start_date.year}"
            end_str = f"{end_date.day}/{end_date.month}/{end_date.year}"

            # Remplir via JS (les champs sont interceptés par caption/navbar)
            for input_id, val in [('start', start_str), ('end', end_str)]:
                self.page.evaluate("""([id, v]) => {
                    const el = document.getElementById(id);
                    const setter = Object.getOwnPropertyDescriptor(
                        HTMLInputElement.prototype, 'value').set;
                    setter.call(el, v);
                    el.dispatchEvent(new Event('input', {bubbles: true}));
                    el.dispatchEvent(new Event('change', {bubbles: true}));
                }""", [input_id, val])
                time.sleep(0.3)

            # Fermer le dropdown
            self.page.keyboard.press("Escape")
            time.sleep(1)

            self.logger.info(f"Période: {start_str} → {end_str}")
            return True

        except Exception as e:
            self.logger.debug(f"Erreur configuration période: {e}")
            return False

    def _wait_and_download_report(self):
        """Attend qu'un rapport passe de 'Envoyé' à 'Télécharger' puis le télécharge.

        Après création, le premier rapport de la liste affiche 'Envoyé'.
        On poll jusqu'à ce qu'il n'y ait plus de 'Envoyé' visible, ce qui
        signifie que le rapport est passé à 'Télécharger'.

        Returns:
            Path du fichier CSV ou None
        """
        self.logger.info("Attente de la génération du rapport...")

        pending_locator = self.page.locator(
            "text='Envoyé', text='Pending', text='En cours', text='Processing'"
        )
        download_locator = self.page.locator(
            "button:has-text('Télécharger'), a:has-text('Télécharger'), "
            "button:has-text('Download'), a:has-text('Download')"
        )

        start_time = time.time()
        while time.time() - start_time < REPORT_MAX_WAIT_S:
            # Actualiser la page si bouton présent
            refresh_btn = self.page.locator(
                "a:has-text('Actualiser'), button:has-text('Actualiser'), "
                "a:has-text('Refresh'), button:has-text('Refresh')"
            )
            if refresh_btn.count() > 0:
                try:
                    refresh_btn.first.click()
                    time.sleep(2)
                except Exception:
                    pass

            # Plus de rapport en attente → le nouveau est prêt
            if pending_locator.count() == 0 and download_locator.count() > 0:
                self.logger.info("Rapport prêt — téléchargement...")
                return self._download_csv(download_locator.first)

            elapsed = int(time.time() - start_time)
            self.logger.verbose(f"Rapport en cours de génération... ({elapsed}s)")
            time.sleep(REPORT_POLL_INTERVAL_S)

        self.logger.error(f"Timeout génération rapport ({REPORT_MAX_WAIT_S}s)")
        self._dump_page_debug("report_timeout", force=True)
        return None

    def _download_csv(self, download_link):
        """Clique sur le lien de téléchargement et sauvegarde le CSV.

        Args:
            download_link: Locator du lien de téléchargement

        Returns:
            Path du fichier CSV ou None
        """
        self.dropbox_dir.mkdir(parents=True, exist_ok=True)

        try:
            with self.page.expect_download(timeout=DOWNLOAD_TIMEOUT_S * 1000) as download_info:
                download_link.click()

            download = download_info.value
            original_name = download.suggested_filename
            dest_path = self.dropbox_dir / original_name
            download.save_as(str(dest_path))

            file_size = dest_path.stat().st_size / 1024
            self.logger.info(f"CSV téléchargé: {original_name} ({file_size:.1f} Ko)")
            self.downloads.append(dest_path)
            return dest_path

        except PlaywrightTimeout:
            self.logger.error(f"Timeout téléchargement CSV ({DOWNLOAD_TIMEOUT_S}s)")
            self._dump_page_debug("download_timeout", force=True)
            return None
        except Exception as e:
            self.logger.error(f"Erreur téléchargement: {e}")
            return None

    # ========================================================================
    # WORKFLOW PRINCIPAL
    # ========================================================================

    def run(self):
        """Execute le workflow de fetch PayPal complet.

        Returns:
            True si succès, False sinon
        """
        # 1. Login
        if not self.wait_for_login():
            self.logger.error("Échec de la connexion")
            return False

        # 2. Télécharger le rapport CSV
        csv_path = self.fetch_report()

        if not csv_path:
            self.logger.error("Aucun fichier récupéré")
            return False

        # 3. Résumé
        self.logger.info(f"Collecte {self.site_name} terminée ({len(self.downloads)} fichier(s))")
        for dl in self.downloads:
            self.logger.info(f"  {dl.name}")
        return True


if __name__ == '__main__':
    sys.exit(fetch_main(PayPalFetcher, description='Fetch PayPal transactions via Playwright'))
