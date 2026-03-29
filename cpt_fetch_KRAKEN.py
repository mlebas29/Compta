#!/usr/bin/env python3
"""
cpt_fetch_KRAKEN.py - Fetch Kraken exports via Playwright (semi-automatique)

Premier script fetch basé sur Playwright (potentiel modèle pour les autres sites).
Login semi-automatique : Chrome mémorise les identifiants (profil persistant),
l'utilisateur valide le 2FA par email, puis le script automatise les exports.

Prérequis:
- pip install playwright
- playwright install chrome

Usage:
  ./cpt_fetch_KRAKEN.py         # Mode normal
  ./cpt_fetch_KRAKEN.py -v      # Mode verbeux

Workflow:
  1. Lance Chrome avec profil persistant (cookies de session conservés)
  2. Navigue vers Kraken login
  3. Chrome auto-remplit les identifiants, l'utilisateur valide le 2FA par email
  4. Détecte la page connectée (URL contenant /c)
  5. Navigue vers /c/account-settings/documents
  6. Crée export "Registre" (CSV, derniers 90j)
  7. Crée export "Soldes" (CSV, aujourd'hui)
  8. Attend que les exports soient prêts (poll table)
  9. Télécharge les 2 ZIPs → dropbox/KRAKEN/
  10. Ferme le navigateur

Fichiers générés:
  - dropbox/KRAKEN/kraken-spot-ledgers-*.zip
  - dropbox/KRAKEN/kraken-spot-balances-*.zip
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

from inc_fetch import BaseFetcher, fetch_main, config, LOGS_DIR


# ============================================================================
# CONFIGURATION
# ============================================================================

# Timeouts
LOGIN_TIMEOUT_S = 300       # 5 min pour login + email 2FA
EXPORT_READY_TIMEOUT_S = 300  # 5 min pour génération export
EXPORT_POLL_INTERVAL_S = 5    # Poll toutes les 5s


class KrakenFetcher(BaseFetcher):
    def __init__(self, verbose=False):
        super().__init__(caller_file=__file__, verbose=verbose)
        self.kraken_sign_in = f"{self.base_url}/sign-in"
        self.kraken_documents = f"{self.base_url}/c/account-settings/documents"

        # Override max_days_back from config
        self.max_days_back = config.getint('KRAKEN', 'max_days_back', fallback=90)

    def _is_cloudflare_challenge(self):
        """Détecte si la page courante est un challenge Cloudflare Turnstile."""
        try:
            # Texte caractéristique de la page challenge
            body_text = self.page.locator("body").inner_text(timeout=3000)
            if "One More Step" in body_text or "security check" in body_text.lower():
                return True
            # Iframe Turnstile
            turnstile = self.page.locator("iframe[src*='challenges.cloudflare.com']")
            if turnstile.count() > 0:
                return True
        except Exception:
            pass
        return False

    def _wait_cloudflare_resolved(self, timeout=120):
        """Attend que le challenge Cloudflare soit résolu (page redirigée).

        Returns:
            True si résolu, False si timeout
        """
        self.logger.alert("CAPTCHA CLOUDFLARE — Coche la case 'Vérifiez que vous êtes humain' dans Chrome")
        start = time.time()
        while time.time() - start < timeout:
            if not self._is_cloudflare_challenge():
                self.logger.info("Challenge Cloudflare résolu")
                time.sleep(2)
                return True
            time.sleep(2)
        self.logger.error(f"Timeout challenge Cloudflare ({timeout}s)")
        return False

    def dismiss_overlays(self):
        """Ferme les popups/overlays (invitation 2FA, cookies, etc.)."""
        try:
            overlay = self.page.locator("[data-portaled-element='true']")
            if overlay.count() > 0:
                # Ignorer les overlays vides (conteneurs de notifications)
                overlay_text = overlay.first.inner_text().strip()
                if not overlay_text:
                    return False

                # Chercher un bouton de fermeture dans l'overlay
                close_btn = overlay.locator(
                    "button:has-text('Not now'), "
                    "button:has-text('Maybe later'), "
                    "button:has-text('Skip'), "
                    "button:has-text('Dismiss'), "
                    "button:has-text('Remind me later'), "
                    "button:has-text('Pas maintenant'), "
                    "button:has-text('Plus tard'), "
                    "button:has-text('Ignorer'), "
                    "button[aria-label='Close'], "
                    "button[aria-label='Fermer']"
                )
                if close_btn.count() > 0:
                    close_btn.first.click()
                    self.logger.info("Popup overlay fermé")
                    time.sleep(1)
                    return True

                # Fallback : chercher un bouton avec X ou ×
                x_btn = overlay.locator("button:has-text('×'), button:has-text('✕')")
                if x_btn.count() > 0:
                    x_btn.first.click()
                    self.logger.info("Popup overlay fermé (×)")
                    time.sleep(1)
                    return True

                self.logger.warning(f"Overlay détecté mais pas de bouton de fermeture: {overlay_text[:100]}")
                return False
        except Exception as e:
            self.logger.debug(f"Pas d'overlay ou erreur: {e}")
        return False

    def wait_for_login(self):
        """Navigue vers Kraken et attend que l'utilisateur soit connecté.

        Chrome auto-remplit les identifiants si mémorisés (profil persistant).
        L'utilisateur n'a qu'à valider le 2FA par email.
        Au premier lancement, login entièrement manuel.
        """
        # Naviguer vers le dashboard directement
        # Si connecté : on y reste. Sinon : Kraken redirige vers /sign-in
        self.logger.info("Navigation vers Kraken...")
        self.page.goto(f"{self.base_url}/c", wait_until="domcontentloaded")
        time.sleep(5)

        # Double-check : les redirections session-expired peuvent être lentes
        current_url = self.page.url
        self.logger.debug(f"URL après navigation: {current_url}")

        # Cloudflare Turnstile bloque en headless → basculer en headed
        if self._is_cloudflare_challenge():
            self.logger.info("Challenge Cloudflare détecté")
            if not (self.debug or self._headed):
                self.relaunch_headed()
                self.page.goto(f"{self.base_url}/c", wait_until="domcontentloaded")
                time.sleep(5)
            if self._is_cloudflare_challenge():
                if not self._wait_cloudflare_resolved():
                    return False
            current_url = self.page.url

        # Si on est sur le dashboard (pas de redirect vers sign-in)
        if '/sign-in' not in current_url:
            self.logger.info("Déjà connecté (session existante)")
            self.dismiss_overlays()
            return True

        # On est sur /sign-in → login requis
        return self._prompt_and_wait_login()

    def _fill_login(self):
        """Remplit le formulaire de login avec les credentials GPG si disponibles.

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

        # Attendre que la page de login soit stable
        self.logger.debug(f"Page de login: {self.page.url}")
        try:
            self.page.wait_for_load_state("domcontentloaded", timeout=10000)
        except PlaywrightTimeout:
            pass
        time.sleep(2)

        # Remplir le formulaire de login Kraken
        try:
            # Chercher le champ email/username
            email_input = self.page.locator(
                "input[name='email'], input[type='email'], input[id*='email'], "
                "input[name='username'], input[autocomplete='username'], "
                "input[autocomplete='email'], input[id*='login']"
            )
            if email_input.count() > 0:
                email_input.first.wait_for(state="visible", timeout=5000)
                email_input.first.fill(username)
                time.sleep(0.5)
                self.logger.debug("Email rempli")
            else:
                self.logger.debug("Champ email/username non trouvé")
                return False

            pwd_input = self.page.locator("input[name='password'], input[type='password']")
            if pwd_input.count() > 0:
                pwd_input.first.fill(password)
                self.logger.debug("Mot de passe rempli")
            else:
                self.logger.debug("Champ mot de passe non trouvé")
                return False

            # Cliquer le bouton de connexion
            submit_btn = self.page.locator(
                "button[type='submit'], "
                "button:has-text('Sign in'), "
                "button:has-text('Se connecter'), "
                "button:has-text('Log in')"
            )
            if submit_btn.count() > 0:
                submit_btn.first.click()
                self.logger.info("Formulaire soumis — en attente de 2FA email")
            else:
                self.logger.debug("Bouton submit non trouvé")

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

    def _prompt_and_wait_login(self):
        """Passe en headed et attend la validation manuelle (2FA email...).

        Surveille le clipboard : si l'utilisateur copie un lien kraken.com,
        le script navigue automatiquement vers ce lien dans le Chrome Playwright.
        """
        # Relancer en headed seulement si actuellement headless
        if not (self.debug or self._headed):
            self.relaunch_headed()
            self.page.goto(self.kraken_sign_in, wait_until="domcontentloaded")
            time.sleep(3)
        elif '/sign-in' not in self.page.url:
            # Déjà headed mais pas sur /sign-in → naviguer
            self.page.goto(self.kraken_sign_in, wait_until="domcontentloaded")
            time.sleep(3)
        self.dismiss_overlays()

        # Vérifier si la session est active après relance (profil persistant)
        if '/sign-in' not in self.page.url:
            self.logger.info("Session active après relance headed")
            return True

        # Remplir le login
        auto_filled = self._fill_login()
        if auto_filled:
            self.logger.alert("VALIDATION 2FA — Copie le lien de l'email Kraken (clic droit → Copier le lien)")
        else:
            self.logger.alert("CONNEXION REQUISE — Connecte-toi dans Chrome, ou copie le lien email Kraken")

        # Vider le clipboard pour éviter de naviguer vers un ancien lien
        try:
            subprocess.run(['xclip', '-selection', 'clipboard'],
                           input='', text=True, timeout=2)
        except Exception:
            pass

        start_time = time.time()
        last_url = ""
        last_nav_check = 0
        last_clipboard = ""

        while time.time() - start_time < LOGIN_TIMEOUT_S:
            # Vérifier l'onglet courant
            current_url = self.page.url
            if current_url != last_url:
                self.logger.debug(f"URL courante: {current_url}")
                last_url = current_url
            if '/sign-in' not in current_url:
                self.logger.info("Connexion détectée")
                return True

            # Vérifier les autres onglets (redirection post-login vers kraken.com)
            for page in self.context.pages:
                if page != self.page and 'kraken.com' in page.url and '/sign-in' not in page.url:
                    self.logger.debug(f"Nouvel onglet post-login: {page.url}")
                    self.logger.info("Connexion détectée")
                    return True

            # Surveiller le clipboard pour un lien Kraken
            clipboard = self._read_clipboard()
            if clipboard and clipboard != last_clipboard and 'kraken.com' in clipboard:
                last_clipboard = clipboard
                self.logger.info(f"Lien Kraken détecté dans le clipboard")
                try:
                    self.page.goto(clipboard, wait_until="domcontentloaded", timeout=30000)
                    time.sleep(3)
                    # Vérifier si ça a fonctionné
                    if '/sign-in' not in self.page.url:
                        self.logger.info("Connexion validée via lien clipboard")
                        return True
                except Exception as e:
                    self.logger.debug(f"Navigation clipboard: {e}")

            # Toutes les 15s, naviguer vers la page documents et vérifier
            elapsed = time.time() - start_time
            if elapsed - last_nav_check > 15:
                last_nav_check = elapsed
                try:
                    self.page.goto(self.kraken_documents, wait_until="domcontentloaded", timeout=10000)
                    time.sleep(3)
                    export_btn = self.page.locator(
                        "button:has-text('Nouvelle exportation'), "
                        "button:has-text('New export')"
                    )
                    if export_btn.count() > 0:
                        self.logger.info("Session validée (bouton export trouvé)")
                        return True
                    self.logger.debug(f"Session pas encore valide ({int(elapsed)}s)")
                except PlaywrightTimeout:
                    pass

            time.sleep(2)

        self.logger.error(f"Timeout login ({LOGIN_TIMEOUT_S}s)")
        return False

    def navigate_to_exports(self):
        """Navigue vers la page des exports."""
        self.logger.info("Navigation vers la page des exports...")
        # Si déjà sur la page documents (après vérification active post-login), pas de re-navigation
        if 'documents' not in self.page.url:
            self.page.goto(self.kraken_documents, wait_until="domcontentloaded")
            time.sleep(3)

        # Fermer bannière cookies si présente
        try:
            cookie_btn = self.page.locator("button:has-text('Only necessary'), button:has-text('Refuser'), button:has-text('Decline')")
            if cookie_btn.count() > 0:
                cookie_btn.first.click()
                self.logger.debug("Bannière cookies fermée")
                time.sleep(1)
        except Exception:
            pass

        # Cloudflare peut aussi bloquer la navigation vers les documents
        if self._is_cloudflare_challenge():
            self.logger.info("Challenge Cloudflare sur la page documents")
            if not self._wait_cloudflare_resolved():
                return False
            # Re-naviguer après résolution
            self.page.goto(self.kraken_documents, wait_until="domcontentloaded")
            time.sleep(3)

        # Vérifier qu'on est bien sur la page des documents
        current_url = self.page.url
        if 'documents' not in current_url:
            # Session expirée ? Kraken redirige vers id.kraken.com/sign-in
            if 'sign-in' in current_url:
                self.logger.warning("Session expirée — connexion requise")
                # Rester sur la page de login actuelle (ne pas rediriger)
                if not self._prompt_and_wait_login():
                    return False
                # Retenter la navigation vers les exports
                self.page.goto(self.kraken_documents, wait_until="domcontentloaded")
                time.sleep(3)
                if 'documents' not in self.page.url:
                    self.logger.error(f"Page inattendue après re-login: {self.page.url}")
                    return False
            else:
                self.logger.error(f"Page inattendue: {current_url}")
                return False

        self.logger.info("Page des exports atteinte")
        self.dismiss_overlays()
        return True

    def _open_new_export_dialog(self):
        """Ouvre la modale 'New Export'."""
        new_export_btn = self.page.locator(
            "button:has-text('Nouvelle exportation'), "
            "button:has-text('New export'), "
            "button:has-text('Create export')"
        )
        # Attendre que le bouton apparaisse (la page peut mettre du temps à charger)
        try:
            new_export_btn.first.wait_for(state="visible", timeout=15000)
        except PlaywrightTimeout:
            self.logger.error("Bouton 'Nouvelle exportation' introuvable")
            self._dump_page_debug("no_export_btn", force=True)
            return False

        new_export_btn.first.click()
        # Attendre que la modale apparaisse
        self.page.locator("div[role='dialog']").wait_for(state="visible", timeout=5000)
        time.sleep(1)
        return True

    def _select_export_type(self, export_type):
        """Sélectionne le type d'export dans le dropdown de la modale.

        Args:
            export_type: 'ledgers' ou 'balances'
        """
        if export_type == 'ledgers':
            type_options = ["Registre", "Ledgers"]
        else:
            type_options = ["Soldes", "Balances"]

        # Le dropdown est dans la modale (div[role='dialog'])
        dialog = self.page.locator("div[role='dialog']")
        dropdown = dialog.locator("button[aria-haspopup='listbox']")
        if dropdown.count() == 0:
            self.logger.error("Dropdown type d'export introuvable dans la modale")
            return False

        # Clic via dispatch_event (React-compatible, bypass overlay)
        dropdown.first.dispatch_event("click")
        time.sleep(1)

        # Sélectionner l'option dans la listbox
        for opt_text in type_options:
            option = self.page.locator(f"[role='option']:has-text('{opt_text}')")
            if option.count() > 0:
                option.first.click(force=True)
                self.logger.debug(f"Type sélectionné: {opt_text}")
                time.sleep(1)
                return True

        self.logger.error(f"Option type introuvable parmi: {type_options}")
        return False

    def create_export(self, export_type):
        """Crée un export (Registre ou Soldes).

        Args:
            export_type: 'ledgers' ou 'balances'
        """
        type_label = "Registre" if export_type == 'ledgers' else "Soldes"
        self.logger.info(f"Création export {type_label}...")

        # 1. Ouvrir la modale
        if not self._open_new_export_dialog():
            return False

        # 2. Sélectionner le type
        if not self._select_export_type(export_type):
            return False

        # 3. Configurer les options (date, format) si visibles
        if export_type == 'ledgers':
            self._set_date_range()
        self._select_csv_format()

        # 4. Cliquer "Générer"
        generate_btn = self.page.locator("div[role='dialog'] button[type='submit']")
        if generate_btn.count() == 0:
            self.logger.error("Bouton 'Générer' introuvable")
            return False

        # Attendre que le bouton soit activé (plus disabled)
        try:
            generate_btn.wait_for(state="attached", timeout=5000)
        except PlaywrightTimeout:
            pass

        generate_btn.click(force=True)
        self.logger.info(f"Export {type_label} lancé")
        time.sleep(3)

        return True

    def _set_date_range(self):
        """Configure la plage de dates pour l'export Registre.

        Le champ date Kraken est readonly (date picker React react-day-picker).
        On clique dessus pour ouvrir le picker, puis on navigue les dropdowns
        année/mois et on clique le jour cible.

        Structure du picker :
        - .datePicker contient 3 panneaux : Filtres rapides, Date de début, Date de fin
        - Chaque panneau date a : dropdown année, dropdown mois, grille jours
        - data-testid='datepicker-year-dropdown-button' (nth(0)=début, nth(1)=fin)
        - data-testid='datepicker-month-dropdown-button' (nth(0)=début, nth(1)=fin)
        - .rdp-table (nth(0)=début, nth(1)=fin) contient button.rdp-day
        """
        end_date = datetime.now()
        start_date = end_date - timedelta(days=self.max_days_back)

        self.logger.debug(f"Plage cible: {start_date.strftime('%Y-%m-%d')} → {end_date.strftime('%Y-%m-%d')}")

        # Trouver le champ date readonly dans la modale
        dialog = self.page.locator("div[role='dialog']")
        date_input = dialog.locator("input[readonly]")

        if date_input.count() == 0:
            self.logger.debug("Pas de champ date trouvé — utilisation des valeurs par défaut")
            return

        # Ouvrir le date picker
        date_input.first.click(force=True)
        time.sleep(1)

        # Noms de mois français (indices 0-11)
        MOIS_FR = ['janvier', 'février', 'mars', 'avril', 'mai', 'juin',
                   'juillet', 'août', 'septembre', 'octobre', 'novembre', 'décembre']

        target_year = str(start_date.year)
        target_month = MOIS_FR[start_date.month - 1]
        target_day = str(start_date.day)

        # Le date picker est rendu dans un portail hors du dialog
        picker = self.page.locator(".datePicker")
        if picker.count() == 0:
            self.logger.warning("Date picker non trouvé après clic")
            return

        year_btns = picker.locator("[data-testid='datepicker-year-dropdown-button']")
        month_btns = picker.locator("[data-testid='datepicker-month-dropdown-button']")

        # --- DATE DE DÉBUT (dropdowns index 0, grille index 0) ---

        # 1. Sélectionner l'année
        current_year = year_btns.nth(0).inner_text().strip()
        if current_year != target_year:
            year_btns.nth(0).dispatch_event("click")
            time.sleep(0.5)
            option = self.page.locator(f"[role='option']:has-text('{target_year}')")
            if option.count() > 0:
                option.first.click(force=True)
                self.logger.debug(f"Année début: {target_year}")
                time.sleep(0.5)
            else:
                self.logger.warning(f"Année {target_year} non disponible")
                return

        # 2. Sélectionner le mois
        current_month = month_btns.nth(0).inner_text().strip()
        if current_month != target_month:
            month_btns.nth(0).dispatch_event("click")
            time.sleep(0.5)
            option = self.page.locator(f"[role='option']:has-text('{target_month}')")
            if option.count() > 0:
                option.first.click(force=True)
                self.logger.debug(f"Mois début: {target_month}")
                time.sleep(0.5)
            else:
                self.logger.warning(f"Mois {target_month} non disponible")
                return

        # 3. Cliquer le jour dans la première grille calendrier
        start_grid = picker.locator(".rdp-table").nth(0)
        day_buttons = start_grid.locator("button.rdp-day")
        clicked = False
        for i in range(day_buttons.count()):
            if day_buttons.nth(i).inner_text().strip() == target_day:
                day_buttons.nth(i).click(force=True)
                self.logger.debug(f"Jour début: {target_day}")
                clicked = True
                break

        if not clicked:
            self.logger.warning(f"Jour {target_day} non trouvé dans le calendrier")
            return

        time.sleep(0.5)

        # --- Confirmer DATE DE FIN (cliquer aujourd'hui dans la grille fin) ---
        # En mode range, react-day-picker attend un 2e clic pour la fin
        end_day = str(end_date.day)
        end_grid = picker.locator(".rdp-table").nth(1)
        end_day_buttons = end_grid.locator("button.rdp-day")
        for i in range(end_day_buttons.count()):
            if end_day_buttons.nth(i).inner_text().strip() == end_day:
                end_day_buttons.nth(i).click(force=True)
                self.logger.debug(f"Jour fin: {end_day}")
                break

        time.sleep(0.5)

        # Fermer le date picker en cliquant sur le champ date (toggle)
        date_input.first.click(force=True)
        time.sleep(0.5)

        self.logger.info(f"Plage de dates: {start_date.strftime('%d/%m/%Y')} → {end_date.strftime('%d/%m/%Y')}")

    def _select_csv_format(self):
        """Change le format de PDF vers CSV."""
        self.logger.debug("Sélection format CSV...")

        # Chercher le dropdown Format
        format_selectors = [
            "[data-testid='export-format-select']",
            "select[name*='format']",
            "[role='combobox']:near(:text('Format'))",
            "button:near(:text('Format'))",
        ]

        for selector in format_selectors:
            try:
                el = self.page.locator(selector)
                if el.count() > 0:
                    el.first.click(force=True)
                    time.sleep(1)

                    csv_option = self.page.locator(
                        "[role='option']:has-text('CSV'), "
                        "li:has-text('CSV'), "
                        "option:has-text('CSV')"
                    )
                    if csv_option.count() > 0:
                        csv_option.first.click(force=True)
                        self.logger.debug("Format CSV sélectionné")
                        time.sleep(0.5)
                        return True
                    break
            except Exception:
                continue

        # Fallback : chercher directement un texte "CSV" cliquable
        try:
            csv_text = self.page.locator("text=CSV").first
            if csv_text.is_visible():
                csv_text.click(force=True)
                self.logger.debug("Format CSV sélectionné (fallback)")
                time.sleep(0.5)
                return True
        except Exception:
            pass

        self.logger.warning("Impossible de changer le format en CSV — vérifier manuellement")
        return False

    def _find_existing_export(self, export_type):
        """Vérifie si un export téléchargeable existe déjà dans la table.

        Args:
            export_type: 'ledgers' ou 'balances'

        Returns:
            True si un export prêt (avec bouton download) existe, False sinon
        """
        # Labels FR et EN pour matcher les lignes de la table
        if export_type == 'ledgers':
            keywords = ["Registre", "Ledger", "ledger"]
        else:
            keywords = ["Soldes", "Balance", "balance"]
        type_label = keywords[0]

        # Chercher une ligne contenant un des mots-clés ET un bouton download
        selector_parts = []
        for kw in keywords:
            selector_parts.append(f"tr:has-text('{kw}')")
            selector_parts.append(f"[class*='row']:has-text('{kw}')")
        rows = self.page.locator(", ".join(selector_parts))
        for i in range(rows.count()):
            row = rows.nth(i)
            download_btn = row.locator(
                "button:has-text('Download'), "
                "button:has-text('Télécharger'), "
                "a:has-text('Download'), "
                "a:has-text('Télécharger'), "
                "[data-testid*='download']"
            )
            if download_btn.count() > 0:
                self.logger.info(f"Export {type_label} existant trouvé — téléchargement direct")
                return True

        return False

    def _count_download_buttons(self):
        """Compte les boutons de téléchargement visibles dans la table des exports."""
        download_btns = self.page.locator(
            "button:has-text('Download'), "
            "button:has-text('Télécharger'), "
            "a:has-text('Download'), "
            "a:has-text('Télécharger'), "
            "[data-testid*='download']"
        )
        return download_btns.count()

    def wait_for_export_ready(self, export_type, initial_count):
        """Attend qu'un nouvel export soit prêt (un bouton download de plus).

        Args:
            export_type: 'ledgers' ou 'balances'
            initial_count: nombre de boutons download avant la création

        Returns:
            True si l'export est prêt, False si timeout
        """
        type_label = "Registre" if export_type == 'ledgers' else "Soldes"
        self.logger.info(f"Attente export {type_label} (timeout: {EXPORT_READY_TIMEOUT_S}s)...")

        start_time = time.time()
        last_reload = 0
        last_count = initial_count
        while time.time() - start_time < EXPORT_READY_TIMEOUT_S:
            current_count = self._count_download_buttons()

            if current_count != last_count:
                self.logger.debug(f"Boutons download: {last_count} → {current_count}")
                last_count = current_count

            if current_count > initial_count:
                self.logger.info(f"Export {type_label} prêt ({current_count} téléchargements)")
                return True

            # Rafraîchir la page toutes les 30s pour forcer la mise à jour
            elapsed = time.time() - start_time
            if elapsed - last_reload > 30:
                self.page.reload(wait_until="domcontentloaded")
                last_reload = elapsed
                self.logger.debug(f"Page rafraîchie ({int(elapsed)}s, boutons: {current_count}, initial: {initial_count})")
                time.sleep(2)

            time.sleep(EXPORT_POLL_INTERVAL_S)

        self.logger.error(f"Timeout: export {type_label} non prêt après {EXPORT_READY_TIMEOUT_S}s")
        return False

    def download_export(self, export_type):
        """Télécharge un export ZIP vers dropbox/KRAKEN/.

        Args:
            export_type: 'ledgers' ou 'balances'

        Returns:
            Path du fichier téléchargé ou None
        """
        type_label = "Registre" if export_type == 'ledgers' else "Soldes"
        if export_type == 'ledgers':
            keywords = ["Registre", "Ledger", "ledger"]
        else:
            keywords = ["Soldes", "Balance", "balance"]

        self.dropbox_dir.mkdir(parents=True, exist_ok=True)

        # Chercher le bon bouton de téléchargement
        download_btns = self.page.locator(
            "button:has-text('Download'), "
            "button:has-text('Télécharger'), "
            "a:has-text('Download'), "
            "a:has-text('Télécharger'), "
            "[data-testid*='download']"
        )

        if download_btns.count() == 0:
            self.logger.error(f"Aucun bouton de téléchargement pour {type_label}")
            return None

        # Trouver le bon bouton (celui correspondant au type d'export)
        # Stratégie : on cherche dans les lignes de la table un des mots-clés
        target_btn = None

        selector_parts = []
        for kw in keywords:
            selector_parts.append(f"tr:has-text('{kw}')")
            selector_parts.append(f"[class*='row']:has-text('{kw}')")
        rows = self.page.locator(", ".join(selector_parts))
        if rows.count() > 0:
            row_download = rows.first.locator(
                "button:has-text('Download'), "
                "button:has-text('Télécharger'), "
                "a:has-text('Download'), "
                "a:has-text('Télécharger'), "
                "[data-testid*='download']"
            )
            if row_download.count() > 0:
                target_btn = row_download.first

        # Fallback : premier bouton de téléchargement disponible
        if target_btn is None:
            target_btn = download_btns.first

        # Télécharger avec capture de l'événement download
        try:
            with self.page.expect_download(timeout=60000) as download_info:
                target_btn.click()

            download = download_info.value
            original_name = download.suggested_filename
            dest_path = self.dropbox_dir / original_name

            # Sauvegarder le fichier
            download.save_as(str(dest_path))

            self.logger.info(f"Téléchargé: {original_name} → {dest_path}")
            self.downloads.append(dest_path)
            return dest_path

        except PlaywrightTimeout:
            self.logger.error(f"Timeout téléchargement {type_label}")
            return None
        except Exception as e:
            self.logger.error(f"Erreur téléchargement {type_label}: {e}")
            return None

    def run(self):
        """Exécute le workflow complet de fetch Kraken.

        Returns:
            True si au moins un fichier a été téléchargé, False sinon
        """
        # 1. Login (interactif)
        if not self.wait_for_login():
            self.logger.error("Échec de la connexion")
            return False

        # 2. Naviguer vers la page des exports
        if not self.navigate_to_exports():
            self.logger.error("Échec navigation vers les exports")
            return False

        # 3-5. Export Registre (ledgers) : vérifier existant ou créer
        if self._find_existing_export('ledgers'):
            ledgers_file = self.download_export('ledgers')
        else:
            count_before = self._count_download_buttons()
            self.logger.debug(f"Boutons download avant création: {count_before}")
            if not self.create_export('ledgers'):
                self.logger.error("Échec création export Registre")
                return False
            if not self.wait_for_export_ready('ledgers', count_before):
                self.logger.error("Export Registre non prêt")
                return False
            ledgers_file = self.download_export('ledgers')

        # 6-8. Export Soldes (balances) : vérifier existant ou créer
        if self._find_existing_export('balances'):
            balances_file = self.download_export('balances')
        else:
            count_before = self._count_download_buttons()
            if not self.create_export('balances'):
                self.logger.error("Échec création export Soldes")
                return False
            if not self.wait_for_export_ready('balances', count_before):
                self.logger.error("Export Soldes non prêt")
                return False
            balances_file = self.download_export('balances')

        # 9. Résumé
        self.logger.info("=" * 50)
        if ledgers_file:
            self.logger.info(f"Registre:  {ledgers_file.name}")
        if balances_file:
            self.logger.info(f"Soldes:    {balances_file.name}")
        self.logger.info(f"Destination: {self.dropbox_dir}")
        self.logger.info("=" * 50)

        success = bool(ledgers_file) or bool(balances_file)
        if success:
            self.logger.info(f"Collecte {self.site_name} terminée ({len(self.downloads)} fichiers)")
        else:
            self.logger.error("Aucun fichier téléchargé")

        return success


if __name__ == '__main__':
    sys.exit(fetch_main(KrakenFetcher, description='Fetch Kraken exports via Playwright (semi-automatique)'))
