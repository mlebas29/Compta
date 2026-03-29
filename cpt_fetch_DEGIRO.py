#!/usr/bin/env python3
"""
cpt_fetch_DEGIRO.py - Récupération automatique des données DEGIRO via Playwright

Login semi-automatique : Chrome remplit les identifiants via GPG,
l'utilisateur valide le 2FA sur l'appli mobile DEGIRO, puis le script
automatise les exports CSV.

Prérequis:
- pip install playwright
- playwright install chrome

Usage:
  ./cpt_fetch_DEGIRO.py         # Mode normal
  ./cpt_fetch_DEGIRO.py -v      # Mode verbeux

Workflow:
  1. Lance Chrome avec profil persistant (cookies de session conservés)
  2. Navigue vers degiro.fr → clic "Accès client" → page login
  3. Remplit identifiants (GPG), attend validation 2FA mobile
  4. Télécharge Portfolio.csv (positions) depuis #/portfolio/assets
  5. Télécharge Account.csv (opérations) depuis #/account-overview

Fichiers générés:
  - dropbox/DEGIRO/Portfolio.csv (positions)
  - dropbox/DEGIRO/Account.csv (opérations)

Note: Les soldes sont extraits par cpt_format_DEGIRO.py directement depuis les CSV :
  - CASH dans Portfolio.csv = solde Réserve
  - Colonne Solde dans Account.csv = solde après opération
"""

import sys
import time
from datetime import datetime, timedelta

try:
    from playwright.sync_api import TimeoutError as PlaywrightTimeout
except ImportError:
    print("Module 'playwright' manquant. Installez avec: pip install playwright && playwright install chrome", file=sys.stderr)
    sys.exit(1)

from inc_fetch import BaseFetcher, fetch_main, config, DEBUG


# ============================================================================
# CONFIGURATION
# ============================================================================

# Timeouts
LOGIN_TIMEOUT_S = 180       # 3 min pour 2FA mobile
DOWNLOAD_TIMEOUT_S = 30     # 30s pour téléchargement CSV

# Période de collecte (6 mois)
MAX_DAYS_BACK = config.getint('DEGIRO', 'max_days_back', fallback=180)


class DegiroFetcher(BaseFetcher):
    def __init__(self, verbose=False):
        super().__init__(caller_file=__file__, verbose=verbose)

    def dismiss_cookies(self):
        """Ferme le popup cookies (Cookiebot ou autre, y compris dans une iframe)."""
        selectors = (
            "#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll, "
            "#CybotCookiebotDialogBodyButtonAccept, "
            "button:has-text('Tout accepter'), "
            "a:has-text('Tout accepter'), "
            "button:has-text('Accept All'), "
            "button:has-text('Accepter')"
        )
        # 1. Chercher dans la page principale
        try:
            cookie_btn = self.page.locator(selectors)
            cookie_btn.first.wait_for(state="visible", timeout=3000)
            cookie_btn.first.click()
            self.logger.info("Cookies acceptés")
            time.sleep(1)
            return
        except Exception:
            pass

        # 2. Chercher dans les iframes (Cookiebot rend parfois dans une iframe)
        try:
            for frame in self.page.frames:
                if frame == self.page.main_frame:
                    continue
                cookie_btn = frame.locator(selectors)
                if cookie_btn.count() > 0:
                    cookie_btn.first.click(force=True)
                    self.logger.info("Cookies acceptés (iframe)")
                    time.sleep(1)
                    return
        except Exception:
            pass

        self.logger.debug("Pas de popup cookies")

    def wait_for_login(self):
        """Navigue vers DEGIRO et gère le login + 2FA.

        Flow:
        1. goto degiro.fr
        2. Clic "Accès client" → redirige vers trader.degiro.nl/login
        3. Dismiss Cookiebot
        4. Remplir username/password (GPG)
        5. Attendre 2FA mobile (URL contient /trader/)

        Returns:
            True si connecté, False sinon
        """
        self.logger.info("Navigation vers DEGIRO...")
        self.page.goto(self.base_url, wait_until="domcontentloaded")
        time.sleep(2)

        # Dismiss cookies sur la page marketing (bloque le clic "Accès client")
        self.dismiss_cookies()

        # Vérifier si déjà connecté (session persistante)
        if 'trader.degiro.nl' in self.page.url and '/login' not in self.page.url:
            self.logger.info("Déjà connecté (session existante)")
            return True

        # Clic "Accès client" sur la page marketing
        try:
            access_btn = self.page.locator(
                "a:has-text('Accès client'), "
                "button:has-text('Accès client'), "
                "a:has-text('Login'), "
                "a:has-text('Log in')"
            )
            if access_btn.count() > 0:
                access_btn.first.click()
                self.logger.info("Clic sur 'Accès client'")
                time.sleep(3)
        except Exception:
            self.logger.debug("Bouton 'Accès client' non trouvé — peut-être déjà sur login")

        # Dismiss cookies sur la page de login (peut réapparaître)
        self.dismiss_cookies()

        # Vérifier si déjà connecté après navigation
        if 'trader.degiro.nl' in self.page.url and '/login' not in self.page.url:
            self.logger.info("Déjà connecté")
            return True

        # Remplir le formulaire de login
        if not self._fill_login():
            # Login manuel requis
            self.logger.alert("CONNEXION REQUISE — Connecte-toi dans Chrome puis valide sur mobile")

        # Attendre 2FA mobile
        return self._wait_for_2fa()

    def _fill_login(self):
        """Remplit le formulaire de login avec les credentials GPG.

        Returns:
            True si le formulaire a été soumis, False sinon
        """
        self.logger.info("Chargement des credentials...")
        username, password = self.load_gpg_credentials()

        if not username or not password:
            self.logger.warning("Credentials non trouvés — login manuel requis")
            return False

        try:
            # Champ username
            username_field = self.page.locator("input#username")
            username_field.wait_for(state="visible", timeout=10000)
            username_field.fill(username)
            time.sleep(0.5)

            # Champ password
            password_field = self.page.locator("input#password")
            password_field.fill(password)
            time.sleep(0.5)

            # Bouton login
            login_btn = self.page.locator("button[name='loginButtonUniversal']")
            login_btn.click()
            self.logger.info("Formulaire soumis — en attente de 2FA mobile")
            time.sleep(2)

            return True
        except Exception as e:
            self.logger.warning(f"Erreur remplissage login: {e}")
            return False

    def _wait_for_2fa(self):
        """Attend la validation 2FA mobile (URL passe de /login à /trader/).

        Returns:
            True si 2FA validé, False si timeout
        """
        self.logger.alert("VALIDATION 2FA — Confirme dans l'appli DEGIRO mobile")

        def _is_logged_in(url):
            return '/trader/' in url and '/login' not in url

        start_time = time.time()
        last_url = ""
        while time.time() - start_time < LOGIN_TIMEOUT_S:
            # Vérifier via JS (page.url reste stale après navigation cross-path)
            try:
                js_url = self.page.evaluate("window.location.href")
                if js_url != last_url:
                    self.logger.debug(f"URL: {js_url}")
                    last_url = js_url
                if _is_logged_in(js_url):
                    self.logger.info("2FA validé — connexion réussie")
                    time.sleep(2)
                    return True
            except Exception:
                self.logger.debug("Page stale, scan des onglets...")

            # 3. Vérifier tous les onglets du contexte
            for page in self.context.pages:
                try:
                    pu = page.url
                    if _is_logged_in(pu):
                        self.logger.info("2FA validé — connexion dans un autre onglet")
                        self.page = page
                        time.sleep(2)
                        return True
                except Exception:
                    continue

            time.sleep(2)

        self.logger.error(f"Timeout 2FA ({LOGIN_TIMEOUT_S}s) — dernière URL: {last_url}")
        for i, page in enumerate(self.context.pages):
            try:
                self.logger.debug(f"Onglet {i}: {page.url}")
            except Exception:
                self.logger.debug(f"Onglet {i}: (fermé)")
        return False

    def download_csv(self, page_url, filename):
        """Navigue vers une page et télécharge l'export CSV.

        DEGIRO a un bouton export qui ouvre un popup avec 3 options (XLS, CSV, PDF).

        Args:
            page_url: URL de la page (portfolio ou account-overview)
            filename: Nom attendu du fichier (pour le log)

        Returns:
            Path du fichier téléchargé ou None
        """
        self.logger.info(f"Téléchargement {filename}...")

        try:
            # Navigation SPA hash routing : JS direct (goto bloque sur domcontentloaded)
            if '#' in page_url:
                target_hash = '#' + page_url.split('#', 1)[1]
                self.logger.debug(f"Navigation SPA: {target_hash}")
                self.page.evaluate(f"window.location.hash = '{target_hash}'")
            else:
                self.page.goto(page_url, wait_until="domcontentloaded")
            time.sleep(3)

            # Cliquer sur le bouton export
            export_btn = self.page.locator("button[data-name='exportButton']")
            export_btn.wait_for(state="visible", timeout=15000)
            export_btn.click()
            self.logger.debug("Bouton export cliqué")
            time.sleep(2)

            # Cliquer sur l'option CSV dans le popup
            with self.page.expect_download(timeout=DOWNLOAD_TIMEOUT_S * 1000) as download_info:
                csv_option = self.page.locator("//*[contains(text(), 'CSV')]")
                csv_option.first.click()

            download = download_info.value
            original_name = download.suggested_filename
            dest_path = self.dropbox_dir / original_name
            download.save_as(str(dest_path))

            self.logger.info(f"Téléchargé: {original_name}")
            self.downloads.append(dest_path)
            return dest_path

        except PlaywrightTimeout:
            self.logger.error(f"Timeout téléchargement {filename}")
            return None
        except Exception as e:
            self.logger.error(f"Erreur téléchargement {filename}: {e}")
            return None

    def run(self):
        """Logique principale : login et téléchargement des exports CSV.

        Returns:
            True si au moins un fichier téléchargé, False sinon
        """
        # 1. Login (interactif)
        if not self.wait_for_login():
            self.logger.error("Échec de la connexion")
            return False

        # 2. Télécharger Portfolio (positions)
        portfolio_url = "https://trader.degiro.nl/trader/#/portfolio/assets"
        portfolio_file = self.download_csv(portfolio_url, "Portfolio.csv")

        # 3. Télécharger Account (opérations)
        end_date = datetime.now()
        start_date = end_date - timedelta(days=MAX_DAYS_BACK)
        collection_start = start_date.strftime("%Y-%m-%d")
        collection_end = end_date.strftime("%Y-%m-%d")

        account_url = (
            f"https://trader.degiro.nl/trader/#/account-overview"
            f"?fromDate={collection_start}&toDate={collection_end}"
            f"&aggregateCashFunds=true&currency=Tous&activePeriodType=Custom"
        )
        self.logger.info(f"Période: {collection_start} → {collection_end}")
        account_file = self.download_csv(account_url, "Account.csv")

        # 4. Résumé
        self.logger.info("=" * 50)
        if portfolio_file:
            self.logger.info(f"Portfolio:  {portfolio_file.name}")
        if account_file:
            self.logger.info(f"Account:    {account_file.name}")
        self.logger.info(f"Destination: {self.dropbox_dir}")
        self.logger.info("=" * 50)

        success = bool(portfolio_file) or bool(account_file)
        if success:
            self.logger.info(f"Collecte {self.site_name} terminée ({len(self.downloads)} fichiers)")
        else:
            self.logger.error("Aucun fichier téléchargé")

        return success


if __name__ == '__main__':
    sys.exit(fetch_main(DegiroFetcher, description='Fetch DEGIRO exports via Playwright (semi-automatique)'))
