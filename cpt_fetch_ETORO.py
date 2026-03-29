#!/usr/bin/env python3
"""
cpt_fetch_ETORO.py - Fetch eToro data via Playwright (semi-automatique)

Login semi-automatique : Chrome remplit les identifiants via GPG,
l'utilisateur valide le 2FA (email ou SMS), puis le script automatise
les exports et captures PDF.

Prérequis:
- pip install playwright
- playwright install chrome

Usage:
  ./cpt_fetch_ETORO.py         # Mode normal
  ./cpt_fetch_ETORO.py -v      # Mode verbeux

Workflow:
  1. Lance Chrome avec profil persistant (cookies de session conservés)
  2. Navigue vers la page d'accueil eToro
  3. Si non connecté : remplit email/password (GPG), attend validation 2FA
  4. Export opérations Money (TSV) depuis /wallet/account/EUR
  5. Export opérations Réserve (XLSX) depuis /documents/accountstatement
  6. Capture PDF page d'accueil (soldes) via CDP
  7. Capture PDF portfolio (positions) via CDP

Fichiers générés:
  - dropbox/ETORO/eToroTransactions_*.tsv
  - dropbox/ETORO/etoro-account-statement-*.xlsx
  - dropbox/ETORO/eToro_accueil.pdf
  - dropbox/ETORO/eToro_portfolio.pdf
"""

import sys
import os
import time
import base64
from datetime import datetime, date, timedelta
from urllib.parse import urlparse
import re

from inc_fetch import BaseFetcher, fetch_main, config, COMPTA_MODE, DEBUG, LOGS_DIR

try:
    from playwright.sync_api import TimeoutError as PlaywrightTimeout
except ImportError:
    print("Module 'playwright' manquant. Installez avec: pip install playwright && playwright install chrome", file=sys.stderr)
    sys.exit(1)


# ============================================================================
# CONFIGURATION
# ============================================================================

# Timeouts
LOGIN_TIMEOUT_S = 300       # 5 min pour login + 2FA
DOWNLOAD_TIMEOUT_S = 120    # 2 min pour téléchargement


class EtoroFetcher(BaseFetcher):
    def __init__(self, verbose=False):
        super().__init__(caller_file=__file__, verbose=verbose, delete_cookies=True)

        # URLs eToro (computed from base_url)
        self.etoro_home = f"{self.base_url}/home"
        self.etoro_money_eur = f"{self.base_url}/wallet/account/EUR"
        self.etoro_account_statement = f"{self.base_url}/documents/accountstatement"
        self.etoro_portfolio = f"{self.base_url}/portfolio/overview"

        # Max days back from config
        self.max_days_back = config.getint('ETORO', 'max_days_back', fallback=365)

    def dismiss_cookies(self):
        """Ferme la popup cookies (Reject/Refuser en priorité).

        Utilise force=True car le bouton peut exister dans le DOM
        sans être visuellement accessible (overlay CDK).
        Timeout court (3s) pour ne pas bloquer le flux.
        """
        try:
            cookie_btn = self.page.locator(
                "button:has-text('Reject'), "
                "button:has-text('Refuser'), "
                "button:has-text('Decline'), "
                "button:has-text('Tout refuser'), "
                "button:has-text('Reject all'), "
                "button:has-text('Deny')"
            )
            cookie_btn.first.wait_for(state="visible", timeout=3000)
            cookie_btn.first.click(force=True)
            self.logger.info("Popup cookies fermée (refusé)")
            time.sleep(1)
            return True
        except (PlaywrightTimeout, Exception):
            pass

        try:
            accept_btn = self.page.locator(
                "button:has-text('Accept'), "
                "button:has-text('Accepter'), "
                "button:has-text('OK'), "
                "button:has-text('Got it')"
            )
            accept_btn.first.wait_for(state="visible", timeout=2000)
            accept_btn.first.click(force=True)
            self.logger.info("Popup cookies fermée (accepté)")
            time.sleep(1)
            return True
        except (PlaywrightTimeout, Exception):
            pass

        return False

    def wait_for_login(self):
        """Navigue vers eToro et gère le login si nécessaire.

        Si la session est active (profil persistant), on arrive directement
        sur la page d'accueil. Sinon, on remplit le login et on attend la 2FA.

        Returns:
            True si connecté, False si timeout
        """
        self.logger.info("Navigation vers eToro...")
        self.page.goto(self.etoro_home, wait_until="domcontentloaded")
        time.sleep(5)

        # Fermer cookies dès que possible
        self.dismiss_cookies()

        current_url = self.page.url
        self.logger.debug(f"URL après navigation: {current_url}")

        # Si on est sur une page authentifiée (pas redirigé vers login)
        authenticated_paths = ['/home', '/portfolio', '/wallet', '/watchlists',
                               '/discover', '/news-and-analysis']
        if self._is_authenticated_url(current_url, authenticated_paths):
            self.logger.info("Déjà connecté (session existante)")
            return True

        # On est sur la page de login -> login requis
        return self._prompt_and_wait_login()

    def _fill_login(self):
        """Remplit le formulaire de login avec les credentials GPG.

        Returns:
            True si les credentials ont été remplis, False sinon
        """
        if not self.credential_id:
            return False

        self.logger.info("Chargement des credentials...")
        username, password = self.load_gpg_credentials()

        if not username or not password:
            self.logger.warning("Credentials non trouvés — login manuel requis")
            return False

        try:
            self.page.wait_for_load_state("domcontentloaded", timeout=10000)
        except PlaywrightTimeout:
            pass
        time.sleep(2)

        # Vérifier qu'on est bien sur etoro.com
        current_url = self.page.url
        if 'etoro.com' not in current_url:
            self.logger.warning(f"Redirigé hors d'eToro: {current_url[:80]}")
            self.page.goto(f"{self.base_url}/login", wait_until="domcontentloaded")
            time.sleep(3)
            if 'etoro.com' not in self.page.url:
                self.logger.error("Impossible de revenir sur eToro")
                return False

        try:
            # Champ email/username
            email_input = self.page.locator(
                "input[name='username'], input[name='email'], "
                "input[type='email'], input[id*='username'], "
                "input[autocomplete='username'], input[data-automation='login-sts-username']"
            )
            if email_input.count() > 0:
                email_input.first.wait_for(state="visible", timeout=5000)
                email_input.first.fill(username)
                time.sleep(0.5)
                self.logger.debug("Email/username rempli")
            else:
                self.logger.debug("Champ email/username non trouvé")
                return False

            # Champ mot de passe
            pwd_input = self.page.locator(
                "input[name='password'], input[type='password'], "
                "input[data-automation='login-sts-password']"
            )
            if pwd_input.count() > 0:
                pwd_input.first.fill(password)
                self.logger.debug("Mot de passe rempli")
            else:
                self.logger.debug("Champ mot de passe non trouvé")
                return False

            # Soumettre le formulaire
            submit_btn = self.page.locator(
                "button[type='submit'], "
                "button[data-automation='login-sts-btn-sign-in'], "
                "button:text-is('Sign in'), "
                "button:text-is('Se connecter'), "
                "button:text-is('Log In')"
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

    def _try_2fa_from_terminal(self):
        """Détecte le champ 2FA et lit le code depuis le terminal.

        Gère deux layouts :
        - Single input : un seul champ pour le code complet
        - Multi-digit : N inputs séparés (un chiffre par champ)

        Returns:
            True si le code a été saisi et soumis, False sinon
        """
        # Attendre que la page 2FA apparaisse (Angular transition)
        time.sleep(2)

        # Chercher les champs de saisie 2FA
        # eToro Angular: automation-id (sans data-), inputmode="decimal", autocomplete="one-time-code"
        code_input = self.page.locator(
            "input[automation-id*='twofa'], input[automation-id*='code'], "
            "input[autocomplete='one-time-code'], "
            "input[inputmode='decimal'], input[inputmode='numeric'], "
            "input[type='tel'], input[type='number'], "
            "input[name*='code'], input[name*='otp'], input[name*='verification'], "
            "input[data-automation*='code']"
        )

        # Attendre que le champ apparaisse (jusqu'à 10s)
        try:
            code_input.first.wait_for(state="visible", timeout=10000)
        except Exception:
            self.logger.debug("Champ 2FA non détecté après 10s")
            self._dump_page_debug("2fa_no_field", force=True)
            return False

        field_count = code_input.count()

        self.logger.info(f"Champs 2FA détectés: {field_count}")
        self.logger.alert("VALIDATION 2FA — Tape le code reçu par SMS/email puis Entrée")

        try:
            code = input("").strip()
        except EOFError:
            return False

        if not code or not code.isdigit():
            self.logger.warning(f"Code invalide: '{code}'")
            return False

        # Saisir le code selon le layout
        if field_count == 1:
            # Single input : remplir le code complet
            code_input.first.click()
            code_input.first.fill(code)
            self.logger.info(f"Code 2FA saisi (single input, {len(code)} chiffres)")
        else:
            # Multi-digit : un chiffre par champ
            digits = list(code)
            if len(digits) < field_count:
                self.logger.warning(f"Code trop court ({len(digits)} chiffres pour {field_count} champs)")
            for i in range(min(len(digits), field_count)):
                code_input.nth(i).click()
                code_input.nth(i).fill(digits[i])
                time.sleep(0.1)
            self.logger.info(f"Code 2FA saisi (multi-digit, {min(len(digits), field_count)}/{field_count} champs)")
        time.sleep(0.5)

        # Chercher et cliquer le bouton de validation
        # eToro a un bouton "Continue" sur la page 2FA
        submit = self.page.locator(
            "button:has-text('Continue'), button:has-text('Continuer'), "
            "button[type='submit'], "
            "button:has-text('Verify'), button:has-text('Vérifier'), "
            "button:has-text('Submit'), button:has-text('Envoyer')"
        )
        if submit.count() > 0:
            submit.first.click()
            self.logger.info("Code 2FA soumis")
        else:
            # Fallback: Enter sur le champ
            code_input.first.press("Enter")
            self.logger.info("Code 2FA soumis (Enter)")

        time.sleep(5)
        return True

    def _prompt_and_wait_login(self):
        """Passe en headed et attend la validation manuelle (2FA, CAPTCHA...)."""
        AUTHENTICATED_PATHS = ['/home', '/portfolio', '/wallet', '/watchlists',
                               '/discover', '/news-and-analysis']

        # Relancer en headed seulement si actuellement headless
        if not (self.debug or self._headed):
            self.relaunch_headed()
        self.page.goto(self.etoro_home, wait_until="domcontentloaded")
        time.sleep(3)
        self.dismiss_cookies()

        # Vérifier si la session est active après relance (profil persistant)
        try:
            check_url = self.page.evaluate("window.location.href")
            if self._is_authenticated_url(check_url, AUTHENTICATED_PATHS):
                self.logger.info("Session active après relance headed")
                return True
        except Exception:
            pass

        # Remplir le login
        auto_filled = self._fill_login()
        if not auto_filled:
            self.logger.alert("CONNEXION REQUISE — Connecte-toi dans Chrome (CAPTCHA, 2FA...)")
        else:
            self.logger.alert("VALIDATION REQUISE — Résous le CAPTCHA et/ou saisis le code 2FA dans Chrome")

        # Poll hybride :
        # - Phase 1 (0-60s) : observation passive (ne pas interférer avec la 2FA)
        # - Phase 2 (60s+) : vérification active (navigation vers /home toutes les 20s)
        PASSIVE_PHASE_S = 60
        ACTIVE_CHECK_INTERVAL_S = 20
        start_time = time.time()
        last_url = ""
        last_active_check = 0
        while time.time() - start_time < LOGIN_TIMEOUT_S:
            elapsed = time.time() - start_time

            # Vérifier self.page (JS pour éviter page.url stale)
            try:
                current_url = self.page.evaluate("window.location.href")
            except Exception:
                current_url = self.page.url
            if current_url != last_url:
                self.logger.debug(f"URL courante: {current_url}")
                last_url = current_url

            if self._is_authenticated_url(current_url, AUTHENTICATED_PATHS):
                self.logger.info("Connexion détectée")
                time.sleep(2)
                self.dismiss_cookies()
                return True

            # Vérifier TOUS les onglets (y compris self.page au cas où)
            for p in self.context.pages:
                page_url = p.url
                if self._is_authenticated_url(page_url, AUTHENTICATED_PATHS):
                    if p != self.page:
                        self.logger.debug(f"Nouvel onglet post-login: {page_url}")
                        self.page = p
                    self.logger.info("Connexion détectée")
                    time.sleep(2)
                    self.dismiss_cookies()
                    return True

            # Phase 2 : après PASSIVE_PHASE_S, navigation active périodique
            if elapsed > PASSIVE_PHASE_S:
                if elapsed - last_active_check > ACTIVE_CHECK_INTERVAL_S:
                    last_active_check = elapsed
                    self.logger.debug(f"Vérification active session ({int(elapsed)}s)...")
                    try:
                        self.page.goto(self.etoro_home, wait_until="domcontentloaded", timeout=10000)
                        time.sleep(3)
                        check_url = self.page.evaluate("window.location.href")
                        self.logger.debug(f"URL après navigation: {check_url}")
                        if self._is_authenticated_url(check_url, AUTHENTICATED_PATHS):
                            # Vérifier que ce n'est pas un faux positif (Angular SPA redirect interne)
                            login_form = self.page.locator(
                                "input[data-automation='login-sts-username'], "
                                "input[autocomplete='username'][name='username']"
                            )
                            if login_form.count() > 0:
                                self.logger.debug("Faux positif — page login détectée malgré URL /home")
                            else:
                                self.logger.info("Session validée (navigation active)")
                                self.dismiss_cookies()
                                return True
                    except PlaywrightTimeout:
                        pass

            time.sleep(3)

        self.logger.error(f"Timeout login ({LOGIN_TIMEOUT_S}s)")
        return False

    def fetch_money_operations(self):
        """Export des opérations Money EUR (TSV).

        Navigation vers /wallet/account/EUR, clic Export, dates, téléchargement.

        Returns:
            Path du fichier téléchargé ou None
        """
        self.logger.info("Export opérations Money (EUR)...")

        self.page.goto(self.etoro_money_eur, wait_until="domcontentloaded")
        time.sleep(3)
        self.dismiss_cookies()

        # Dates : hier - MAX_DAYS_BACK → hier (eToro n'accepte pas aujourd'hui)
        end_date = date.today() - timedelta(days=1)
        start_date = end_date - timedelta(days=self.max_days_back)
        # Format mm/dd/yyyy pour eToro
        start_str = start_date.strftime("%m/%d/%Y")
        end_str = end_date.strftime("%m/%d/%Y")
        self.logger.info(f"Période: {start_str} → {end_str}")

        # Chercher et cliquer le bouton/lien Export
        export_btn = self.page.locator(
            "a:has-text('Export'), "
            "button:has-text('Export'), "
            "a:has-text('Exporter'), "
            "button:has-text('Exporter'), "
            "[data-etoro-automation-id='wallet-account-export-link']"
        )
        try:
            export_btn.first.wait_for(state="visible", timeout=15000)
        except PlaywrightTimeout:
            self.logger.error("Bouton 'Export' introuvable sur /wallet/account/EUR")
            self._dump_page_debug("money_no_export_btn")
            return None

        export_btn.first.click(force=True)
        self.logger.debug("Bouton Export cliqué")
        time.sleep(3)

        # eToro utilise Angular CDK : le dialogue d'export est dans un overlay
        # Les date inputs sont des Angular Material datepickers (input.mat-datepicker-input)
        dialog = self.page.locator(".cdk-overlay-pane").last
        if dialog.count() == 0:
            self.logger.debug("Pas de CDK overlay — fallback page entière")
            dialog = self.page

        # Remplir les dates : Angular Material datepicker (placeholder mm/dd/yyyy)
        date_inputs = dialog.locator("input.mat-datepicker-input")
        date_count = date_inputs.count()
        self.logger.debug(f"Champs mat-datepicker dans dialog: {date_count}")

        if date_count >= 2:
            try:
                # Premier champ = date début, second = date fin
                date_inputs.nth(0).click(force=True)
                time.sleep(0.3)
                date_inputs.nth(0).fill("")
                date_inputs.nth(0).type(start_str, delay=50)
                time.sleep(0.5)

                date_inputs.nth(1).click(force=True)
                time.sleep(0.3)
                date_inputs.nth(1).fill("")
                date_inputs.nth(1).type(end_str, delay=50)
                time.sleep(0.5)
                self.logger.debug(f"Dates remplies: {start_str} → {end_str}")
            except Exception as e:
                self.logger.warning(f"Erreur remplissage dates: {e}")
                self._dump_page_debug("money_date_fill_error")
        else:
            self.logger.warning(f"Champs date non trouvés ({date_count}) — dates par défaut")
            self._dump_page_debug("money_no_date_fields")

        # Cliquer le bouton Exporter du formulaire (scopé dans le dialog CDK)
        submit_btn = dialog.locator("button:has-text('Exporter'), button:has-text('Export')")

        self.dropbox_dir.mkdir(parents=True, exist_ok=True)

        try:
            if submit_btn.count() > 0:
                with self.page.expect_download(timeout=DOWNLOAD_TIMEOUT_S * 1000) as download_info:
                    submit_btn.first.click(force=True)
            else:
                # Fallback : le clic Export initial déclenche peut-être directement le download
                self.logger.warning("Bouton submit non trouvé — attente téléchargement...")
                with self.page.expect_download(timeout=DOWNLOAD_TIMEOUT_S * 1000) as download_info:
                    self.page.keyboard.press("Enter")

            download = download_info.value
            original_name = download.suggested_filename
            dest_path = self.dropbox_dir / original_name
            download.save_as(str(dest_path))

            self.logger.info(f"Money TSV téléchargé: {original_name}")
            self.downloads.append(dest_path)
            return dest_path

        except PlaywrightTimeout:
            self.logger.error(f"Timeout téléchargement Money TSV ({DOWNLOAD_TIMEOUT_S}s)")
            self._dump_page_debug("money_download_timeout")
            return None
        except Exception as e:
            self.logger.error(f"Erreur téléchargement Money: {e}")
            return None

    def fetch_reserve_operations(self):
        """Export des opérations Réserve USD (XLSX).

        Navigation vers /documents/accountstatement, sélection période,
        création rapport, téléchargement XLS.

        Returns:
            Path du fichier téléchargé ou None
        """
        self.logger.info("Export opérations Réserve (USD)...")

        # Dates : hier - MAX_DAYS_BACK → hier
        end_date = date.today() - timedelta(days=1)
        start_date = end_date - timedelta(days=self.max_days_back)

        # Le bouton "Créer" est un <a> avec href=/documents/accountstatement/YYYY-MM-DD/YYYY-MM-DD
        # On navigue directement vers l'URL avec nos dates (pas besoin du dropdown)
        start_iso = start_date.strftime("%Y-%m-%d")
        end_iso = end_date.strftime("%Y-%m-%d")
        statement_url = f"{self.base_url}/documents/accountstatement/{start_iso}/{end_iso}"
        self.logger.info(f"Période: {start_iso} → {end_iso}")

        self.page.goto(statement_url, wait_until="domcontentloaded")
        time.sleep(5)
        self.dismiss_cookies()

        # Le bouton Excel est un <a> avec icône (pas de texte visible)
        # automation-id="as-menu-export-excel"
        xls_btn = self.page.locator("[automation-id='as-menu-export-excel']")
        try:
            xls_btn.wait_for(state="visible", timeout=30000)
        except PlaywrightTimeout:
            self.logger.error("Bouton Excel introuvable")
            self._dump_page_debug("reserve_no_xls_btn")
            return None

        self.logger.debug("Bouton Excel trouvé")
        self.dropbox_dir.mkdir(parents=True, exist_ok=True)

        # Le clic déclenche un preloader (préparation fichier) puis un download.
        # eToro affiche parfois une modale "Nous préparons votre relevé"
        # avec un bouton "J'ai compris" qu'il faut fermer avant le download.
        try:
            with self.page.expect_download(timeout=DOWNLOAD_TIMEOUT_S * 1000) as download_info:
                xls_btn.click(force=True)
                self.logger.info("Bouton Excel cliqué — attente préparation...")

                # Fermer la modale "Nous préparons votre relevé" si présente
                try:
                    dismiss_btn = self.page.locator(
                        "button:has-text(\"j'ai compris\"), "
                        "button:has-text(\"J'ai compris\")"
                    )
                    dismiss_btn.first.wait_for(state="visible", timeout=10000)
                    dismiss_btn.first.click(force=True)
                    self.logger.info("Popup 'Nous préparons votre relevé' fermée")
                except Exception:
                    pass

            download = download_info.value
            original_name = download.suggested_filename
            dest_path = self.dropbox_dir / original_name
            download.save_as(str(dest_path))

            self.logger.info(f"Reserve XLSX téléchargé: {original_name}")
            self.downloads.append(dest_path)
            return dest_path

        except PlaywrightTimeout:
            self.logger.error(f"Timeout téléchargement Reserve XLSX ({DOWNLOAD_TIMEOUT_S}s)")
            self._dump_page_debug("reserve_download_timeout")
            return None
        except Exception as e:
            self.logger.error(f"Erreur téléchargement Reserve: {e}")
            return None

    def capture_home_pdf(self):
        """Capture la page d'accueil eToro en PDF (soldes).

        Utilise CDP Page.printToPDF (fonctionne en mode headed, contrairement
        à page.pdf() qui nécessite headless).

        Returns:
            Path du PDF ou None
        """
        self.logger.info("Capture PDF page d'accueil (soldes)...")

        self.page.goto(self.etoro_home, wait_until="domcontentloaded")
        time.sleep(5)
        self.dismiss_cookies()

        dest_path = self.dropbox_dir / 'eToro_accueil.pdf'
        result = self._save_page_as_pdf(dest_path)
        if result:
            self.logger.info(f"PDF accueil sauvegardé: {dest_path.name}")
            self.downloads.append(dest_path)
        return result

    def capture_portfolio_pdf(self):
        """Capture la page portfolio eToro en PDF (positions).

        Returns:
            Path du PDF ou None
        """
        self.logger.info("Capture PDF portfolio (positions)...")

        self.page.goto(self.etoro_portfolio, wait_until="domcontentloaded")
        time.sleep(5)
        self.dismiss_cookies()

        dest_path = self.dropbox_dir / 'eToro_portfolio.pdf'
        result = self._save_page_as_pdf(dest_path)
        if result:
            self.logger.info(f"PDF portfolio sauvegardé: {dest_path.name}")
            self.downloads.append(dest_path)
        return result

    def _save_page_as_pdf(self, dest_path):
        """Sauvegarde la page courante en PDF via CDP.

        page.pdf() ne fonctionne qu'en headless. CDP Page.printToPDF
        fonctionne en mode headed avec un vrai Chrome.

        Args:
            dest_path: Path de destination du PDF

        Returns:
            Path si succès, None sinon
        """
        try:
            self.dropbox_dir.mkdir(parents=True, exist_ok=True)
            cdp = self.context.new_cdp_session(self.page)
            result = cdp.send("Page.printToPDF", {
                "printBackground": True,
                "preferCSSPageSize": True,
            })
            pdf_data = base64.b64decode(result['data'])
            with open(dest_path, 'wb') as f:
                f.write(pdf_data)
            cdp.detach()
            return dest_path
        except Exception as e:
            self.logger.warning(f"Erreur capture PDF: {e}")
            return None

    @staticmethod
    def _is_authenticated_url(url, authenticated_paths):
        """Vérifie si l'URL correspond à une page eToro authentifiée.

        Gère les préfixes locale (ex: /fr/home, /en/portfolio).
        """
        if 'etoro.com' not in url:
            return False
        path = urlparse(url).path
        # Supprimer préfixe locale optionnel (/fr/, /en/, /de/, etc.)
        path = re.sub(r'^/[a-z]{2}(?=/)', '', path)
        return any(path.startswith(p) for p in authenticated_paths)

    def _dump_page_debug(self, label, force=False):
        """Sauvegarde le HTML et un screenshot pour debug."""
        if not self.debug and not force:
            return
        debug_dir = LOGS_DIR / 'debug'
        debug_dir.mkdir(parents=True, exist_ok=True)

        html_file = debug_dir / f'etoro_{label}.html'
        html = self.page.content()
        with open(html_file, 'w', encoding='utf-8') as f:
            f.write(html)
        self.logger.debug(f"HTML sauvegardé: {html_file}")

        png_file = debug_dir / f'etoro_{label}.png'
        self.page.screenshot(path=str(png_file))
        self.logger.debug(f"Screenshot sauvegardé: {png_file}")

    def run(self):
        """Execute le workflow de fetch eToro complet.

        Returns:
            True si succès (au moins un fichier récupéré), False sinon
        """
        self.logger.info(f"Démarrage collecte {self.site_name}")
        self.logger.info(f"Mode: {COMPTA_MODE.upper()}, DEBUG: {DEBUG}")
        self.logger.info(f"Période: derniers {self.max_days_back} jours (jusqu'à hier)")

        try:
            # 1. Login (interactif si nécessaire)
            if not self.wait_for_login():
                self.logger.error("Échec de la connexion")
                return False

            # 3. Export opérations Money (TSV)
            tsv_path = self.fetch_money_operations()

            # 4. Export opérations Réserve (XLSX)
            xlsx_path = self.fetch_reserve_operations()

            # 5. Capture PDF accueil (soldes) — optionnel
            pdf_home = self.capture_home_pdf()
            if not pdf_home:
                self.logger.warning("PDF accueil non capturé (non bloquant)")

            # 6. Capture PDF portfolio (positions) — optionnel
            pdf_portfolio = self.capture_portfolio_pdf()
            if not pdf_portfolio:
                self.logger.warning("PDF portfolio non capturé (non bloquant)")

            # 7. Résumé
            self.logger.info("=" * 50)
            for dl in self.downloads:
                self.logger.info(f"  {dl.name}")
            self.logger.info(f"Destination: {self.dropbox_dir}")
            self.logger.info("=" * 50)

            # Succès si au moins TSV + XLSX récupérés
            if tsv_path and xlsx_path:
                self.logger.info(f"Collecte {self.site_name} terminée")
                return True
            elif tsv_path or xlsx_path:
                self.logger.warning(f"Collecte {self.site_name} partielle (fichiers manquants)")
                return True
            else:
                self.logger.error(f"Collecte {self.site_name} échouée (aucun export)")
                return False

        except KeyboardInterrupt:
            self.logger.warning("Interrompu par l'utilisateur")
            return False
        except Exception as e:
            self.logger.error(f"Erreur inattendue: {e}")
            if self.debug:
                import traceback
                traceback.print_exc()
            return False
        finally:
            self.close()


if __name__ == '__main__':
    sys.exit(fetch_main(EtoroFetcher, description='Fetch eToro data via Playwright (semi-automatique)'))
