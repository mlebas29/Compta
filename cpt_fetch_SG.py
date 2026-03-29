#!/usr/bin/env python3
"""
cpt_fetch_SG.py - Récupération automatique des relevés Société Générale

Login automatique (GPG) avec clavier virtuel OCR (pytesseract), export CSV
comptes bancaires, XLSX et PDF assurances vie via Playwright/Chrome.

Prérequis:
- pip install playwright pytesseract Pillow
- playwright install chrome
- tesseract-ocr installé (apt install tesseract-ocr)

Usage:
  ./cpt_fetch_SG.py           # Mode normal
  ./cpt_fetch_SG.py -v        # Mode verbeux

Fichiers générés (11) :
  - {numéro_compte}.csv                    # Opérations compte courant
  - Export_{numéro}*.csv (x 5)             # Opérations comptes épargne
  - SG_Ebene_supports.xlsx                 # Positions ass. vie Ébène
  - SG_Ebene2_supports.xlsx                # Positions ass. vie Ébène 2
  - SG_Ebene_operations.pdf                # Opérations ass. vie Ébène
  - SG_Ebene2_operations.pdf               # Opérations ass. vie Ébène 2
  - Mes comptes en ligne _ SG.pdf          # Synthèse (tous les soldes)
"""

import sys
import base64
import time
import re
import json
from datetime import datetime
from pathlib import Path

from inc_fetch import BaseFetcher, fetch_main

try:
    from playwright.sync_api import TimeoutError as PlaywrightTimeout
except ImportError:
    print("Module 'playwright' manquant. Installez avec: pip install playwright && playwright install chrome", file=sys.stderr)
    sys.exit(1)

try:
    import pytesseract
    from PIL import Image, ImageEnhance
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False
    print("pytesseract ou PIL non disponible. Installation: pip install pytesseract pillow", file=sys.stderr)

# ============================================================================
# CONFIGURATION
# ============================================================================

TIMEOUT_PAGE = 15000  # ms

# ============================================================================
# URLs DIRECTES PAR COMPTE
# ============================================================================

URL_BASE_CBO = "https://particuliers.sg.fr/icd/cbo/index-react-authsec.html"
URL_BASE_AVD = "https://particuliers.sg.fr/icd/avd/index-authsec.html"
URL_SYNTHESE = f"{URL_BASE_CBO}#/synthese"

# Comptes et assurances vie : chargés depuis config_accounts.json
_ACCOUNTS_JSON = Path(__file__).parent / 'config_accounts.json'
with open(_ACCOUNTS_JSON, 'r', encoding='utf-8') as _f:
    _sg_config = json.load(_f).get('SG', {})

COMPTES_BANCAIRES = [
    (a['numero'], a['name'], a['id_technique'])
    for a in _sg_config.get('accounts', [])
    if 'numero' in a and 'id_technique' in a
]
COMPTE_PRINCIPAL = _sg_config.get('compte_principal', '')

ASSURANCES_VIE = [
    (a['name'], a['id_technique'])
    for a in _sg_config.get('assurances_vie', [])
]


class SgFetcher(BaseFetcher):
    def __init__(self, verbose=False):
        super().__init__(caller_file=__file__, verbose=verbose,
                         viewport={"width": 1400, "height": 1000})
        self._alert_text = None
        self._dialog_handler = self._handle_dialog

    def _handle_dialog(self, dialog):
        """Capture et accepte les dialogues JS (alertes service indisponible)."""
        self._alert_text = dialog.message
        self.logger.debug(f"Alerte JS: {dialog.message}")
        dialog.accept()

    def wait_for_login(self, username, password):
        """Navigue vers SG et gère le login si nécessaire.

        Returns:
            True si connecté, False sinon
        """
        self.logger.info("Vérification session...")

        # Naviguer vers la page de téléchargement (redirige vers login si pas connecté)
        download_url = f"{self.base_url}/restitution/tel_telechargement.html"
        self.page.goto(download_url, wait_until="domcontentloaded", timeout=30000)
        time.sleep(2)

        current_url = self.page.evaluate("window.location.href")
        self.logger.info(f"URL: {current_url}")

        # Cas 1 : déjà connecté (page de téléchargement avec select compte)
        if self.page.locator("#compte").count() > 0:
            self.logger.info("Session active (profil Chrome)")
            return True

        # Cas 2 : page 2FA résiduelle (run précédent interrompu)
        if self._detect_2fa():
            self.logger.info("Page 2FA détectée")
            self._wait_for_2fa()
            return self._verify_connection()

        # Cas 3 : page de login
        login_field = self.page.locator("#user_id")
        if login_field.count() > 0:
            return self._try_login_once(username, password)

        # Cas inconnu
        self.logger.error(f"Page inattendue: {current_url}")
        return False

    def _try_login_once(self, username, password):
        """Tentative de connexion complète : identifiant + clavier virtuel + 2FA.

        Returns:
            True si connecté, False sinon
        """
        try:
            # Page de login
            download_url = f"{self.base_url}/restitution/tel_telechargement.html"
            self.page.goto(download_url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(2)

            self._dismiss_cookies()

            # Saisir l'identifiant
            username_field = self.page.locator("#user_id")
            username_field.wait_for(state="visible", timeout=TIMEOUT_PAGE)

            # Clear et remplir (type() simule les frappes clavier, contrairement à fill())
            try:
                username_field.clear()
                username_field.type(username, delay=50)
                self.logger.info(f"Identifiant saisi: {username}")
            except Exception:
                self.logger.info("Identifiant déjà mémorisé")

            time.sleep(0.5)

            # Activer et cliquer sur le bouton Valider (clic JS direct)
            self.page.evaluate("""
                () => {
                    const btn = document.getElementById('btn-validate');
                    if (btn) {
                        btn.classList.remove('swm_btn-disable', 'swm_btn-disable-css');
                        btn.removeAttribute('disabled');
                        btn.click();
                    }
                }
            """)
            self.logger.info("Bouton 'Valider' cliqué")

            # Attendre que le clavier virtuel soit prêt
            time.sleep(2)

            # Saisir le mot de passe sur le clavier virtuel
            self._click_virtual_keyboard(password)

            # Attendre la réaction du serveur (validation mot de passe → 2FA ou connexion)
            time.sleep(2)

            # Détecter 2FA ou connexion directe (max 10s)
            for _ in range(5):
                if self._detect_2fa():
                    self._wait_for_2fa()
                    break
                if self.page.locator("#compte").count() > 0:
                    self.logger.info("Connexion directe (sans 2FA)")
                    return True
                time.sleep(2)

            return self._verify_connection()

        except Exception as e:
            self.logger.error(f"Erreur connexion: {e}")
            return False

    def _verify_connection(self):
        """Vérifie la connexion en naviguant vers la page téléchargement."""
        self.logger.info("Vérification de la connexion...")
        # Si déjà sur la page téléchargement, pas besoin de re-naviguer
        if self.page.locator("#compte").count() > 0:
            self.logger.info("Connexion réussie")
            return True
        self.page.goto(
            f"{self.base_url}/restitution/tel_telechargement.html",
            wait_until="domcontentloaded", timeout=30000
        )
        time.sleep(2)
        try:
            self.page.locator("#compte").wait_for(state="visible", timeout=10000)
            self.logger.info("Connexion réussie")
            return True
        except PlaywrightTimeout:
            self.logger.error("Session expirée après authentification")
            return False

    def _dismiss_cookies(self):
        """Ferme le popup cookies si présent."""
        try:
            cookie_btn = self.page.locator("#popin_tc_privacy_button_3")
            cookie_btn.click(timeout=3000)
            self.logger.info("Cookies fermés")
            time.sleep(1)
        except Exception:
            pass

    def _click_virtual_keyboard(self, password):
        """Clique sur le clavier virtuel pour saisir le mot de passe via OCR Tesseract."""
        self.logger.info("Saisie du mot de passe sur clavier virtuel...")

        if not OCR_AVAILABLE:
            raise Exception("OCR non disponible. Installez: sudo apt install tesseract-ocr && pip install pytesseract pillow")

        # Attendre que le clavier apparaisse (spans avec id hover_touche_*)
        key_spans = None
        for _ in range(10):
            time.sleep(0.5)
            key_spans = self.page.locator('[id^="hover_touche"]').all()
            if len(key_spans) >= 10:
                time.sleep(0.5)
                break

        if not key_spans or len(key_spans) < 10:
            raise Exception(f"Clavier virtuel: seulement {len(key_spans) if key_spans else 0} touches trouvées")

        self.logger.debug(f"Clavier détecté: {len(key_spans)} touches")

        # Screenshot complet pour OCR
        screenshot_path = self.logs_dir / 'debug' / 'sg_keyboard_full.png'
        screenshot_path.parent.mkdir(parents=True, exist_ok=True)
        self.page.screenshot(path=str(screenshot_path))
        full_image = Image.open(screenshot_path)

        # Mapper chaque touche avec OCR via bounding_box()
        digit_buttons = {}

        for span in key_spans:
            box = span.bounding_box()
            if not box or box['width'] < 5 or box['height'] < 5:
                continue

            span_id = span.get_attribute('id')
            x, y, w, h = box['x'], box['y'], box['width'], box['height']

            try:
                # Crop avec marge pour éviter les bords
                margin_x = int(w * 0.2)
                margin_y = int(h * 0.2)
                touch_image = full_image.crop((
                    x + margin_x, y + margin_y,
                    x + w - margin_x, y + h - margin_y
                ))

                # Prétraitement OCR
                touch_image = touch_image.convert('L')
                enhancer = ImageEnhance.Contrast(touch_image)
                touch_image = enhancer.enhance(3.0)
                touch_image = touch_image.point(lambda p: 255 if p > 128 else 0)

                custom_config = r'--oem 3 --psm 10 -c tessedit_char_whitelist=0123456789'
                digit = pytesseract.image_to_string(touch_image, config=custom_config).strip()
                digit = ''.join(c for c in digit if c.isdigit())

                if len(digit) == 1 and digit not in digit_buttons:
                    digit_buttons[digit] = span_id
                    self.logger.debug(f"  Touche '{digit}' → {span_id} ({len(digit_buttons)}/10)")

                if self.debug:
                    touch_image.save(self.logs_dir / 'debug' / f"sg_key_{span_id}_{digit or '?'}.png")

            except Exception as e:
                self.logger.debug(f"Erreur OCR {span_id}: {e}")

            if len(digit_buttons) >= 10:
                break

        if len(digit_buttons) == 0:
            raise Exception("Aucune touche mappée par OCR")

        self.logger.info(f"Clavier mappé: {len(digit_buttons)} chiffres détectés")

        # Saisir le mot de passe (clic JS DOM comme dans la version Selenium)
        for digit in password:
            if digit not in digit_buttons:
                raise Exception(f"Le chiffre '{digit}' n'a pas été trouvé dans le clavier")
            div_id = digit_buttons[digit]
            self.page.evaluate(f"document.getElementById('{div_id}').click()")
            time.sleep(0.3)  # 300ms entre chaque touche (comme Selenium original)

        self.logger.info("Mot de passe saisi")

        # Cliquer sur Valider (bouton de soumission du mot de passe)
        clicked = self.page.evaluate("""
            () => {
                const buttons = document.querySelectorAll('button');
                for (const btn of buttons) {
                    if (btn.textContent.trim().includes('Valider') && btn.offsetParent !== null) {
                        btn.click();
                        return btn.textContent.trim();
                    }
                }
                return null;
            }
        """)
        if clicked:
            self.logger.info(f"Bouton '{clicked}' cliqué")
        else:
            self.logger.warning("Bouton 'Valider' non trouvé après saisie du mot de passe")

        # Nettoyage
        if not self.debug and screenshot_path.exists():
            screenshot_path.unlink()

    def _detect_2fa(self):
        """Détecte si l'authentification forte (2FA) est requise."""
        try:
            # Chercher "PASS SÉCURITÉ" ou le bouton Continuer (tout type d'élément)
            pass_secu = self.page.locator("//*[contains(text(), 'PASS')]")
            continuer = self.page.locator("//*[contains(text(), 'Continuer')]")
            found = pass_secu.count() > 0 or continuer.count() > 0
            if found:
                self.logger.debug(f"2FA détecté: PASS={pass_secu.count()}, Continuer={continuer.count()}")
            return found
        except Exception:
            return False

    def _wait_for_2fa(self):
        """Attend la validation 2FA par polling automatique.

        Après le clic sur "Continuer", poll la page pour détecter quand
        l'authentification forte est terminée. Après 30s, tente aussi de
        naviguer vers la page de téléchargement pour vérifier la session.

        Timeout: 3 minutes.
        """
        TIMEOUT_2FA = 180  # 3 minutes
        CHECK_NAV_AFTER = 30  # Commencer navigation active après 30s
        CHECK_NAV_INTERVAL = 15  # Vérifier toutes les 15s

        self.logger.alert("VALIDATION 2FA — Valide sur l'appli mobile SG")

        # Cliquer sur Continuer via JS (cherche le plus petit élément contenant le texte)
        try:
            clicked = self.page.evaluate("""
                () => {
                    // Chercher tous les éléments cliquables avec "Continuer"
                    const candidates = document.querySelectorAll('button, a, input[type="submit"], [role="button"]');
                    for (const el of candidates) {
                        if (el.textContent.trim().includes('Continuer') && el.offsetParent !== null) {
                            el.click();
                            return el.tagName + ': ' + el.textContent.trim().substring(0, 30);
                        }
                    }
                    // Fallback: chercher tout élément avec onclick
                    const all = document.querySelectorAll('*');
                    for (const el of all) {
                        const text = el.textContent.trim();
                        const children = el.children.length;
                        if (text === 'Continuer' && children === 0) {
                            el.click();
                            return el.tagName + ': ' + text;
                        }
                    }
                    return null;
                }
            """)
            if clicked:
                self.logger.info(f"Bouton cliqué: {clicked}")
            else:
                self.logger.warning("Bouton 'Continuer' non trouvé via JS")
            time.sleep(2)
        except Exception as e:
            self.logger.warning(f"Erreur clic Continuer: {e}")

        # Polling : attendre que la 2FA soit validée
        start_time = time.time()
        last_check_nav = 0
        last_click_continuer = time.time()  # On vient de cliquer

        while time.time() - start_time < TIMEOUT_2FA:
            elapsed = time.time() - start_time

            # Vérification passive : la page 2FA a-t-elle disparu ?
            if not self._detect_2fa():
                self.logger.info(f"2FA validée ({int(elapsed)}s)")
                time.sleep(3)
                return

            # Re-cliquer "Continuer" si visible (SG peut présenter plusieurs étapes)
            if time.time() - last_click_continuer > 10:
                try:
                    continuer = self.page.locator(
                        "button:has-text('Continuer'), a:has-text('Continuer'), "
                        "[role='button']:has-text('Continuer')"
                    )
                    if continuer.first.is_visible(timeout=1000):
                        continuer.first.click(timeout=3000)
                        last_click_continuer = time.time()
                        self.logger.info(f"  Clic 'Continuer' ({int(elapsed)}s)")
                        time.sleep(2)
                        continue
                except Exception:
                    pass

            # Après 30s, tenter de naviguer vers la page téléchargement
            if elapsed > CHECK_NAV_AFTER and elapsed - last_check_nav > CHECK_NAV_INTERVAL:
                last_check_nav = elapsed
                try:
                    self.page.goto(
                        f"{self.base_url}/restitution/tel_telechargement.html",
                        wait_until="domcontentloaded", timeout=10000
                    )
                    time.sleep(2)
                    if self.page.locator("#compte").count() > 0:
                        self.logger.info(f"2FA validée ({int(elapsed)}s)")
                        return
                except Exception:
                    pass
                self.logger.info(f"  En attente 2FA ({int(elapsed)}s)...")

            time.sleep(3)

        self.logger.error(f"Timeout 2FA après {TIMEOUT_2FA}s")

    def download_csv_compte_courant(self):
        """Télécharge le CSV du compte courant via la page de téléchargement.

        Cette page présente un formulaire avec sélection de compte, format,
        et dates de période. Le compte courant n'est pas disponible via
        l'export CSV direct (réservé aux comptes épargne).

        Returns:
            Path du fichier téléchargé ou None
        """
        self.logger.info("Export compte courant (page téléchargement)...")

        try:
            self.page.goto(
                f"{self.base_url}/restitution/tel_telechargement.html",
                wait_until="domcontentloaded", timeout=30000
            )
            time.sleep(3)

            # 1. Sélectionner le compte (Compte commun)
            self.page.evaluate("""
                () => {
                    const select = document.getElementById('compte');
                    if (!select) return;
                    for (const opt of select.options) {
                        if (opt.text.toLowerCase().includes('commun')) {
                            select.value = opt.value;
                            select.dispatchEvent(new Event('change', {bubbles: true}));
                            break;
                        }
                    }
                }
            """)
            self.logger.info("Compte commun sélectionné")
            time.sleep(1)

            # 2. Sélectionner le format CSV
            self.page.evaluate("""
                () => {
                    const selects = document.querySelectorAll('select');
                    if (selects.length >= 2) {
                        const fmt = selects[1];
                        for (const opt of fmt.options) {
                            if (opt.text.includes('CSV') || opt.text.includes('Tableur')) {
                                fmt.value = opt.value;
                                fmt.dispatchEvent(new Event('change', {bubbles: true}));
                                break;
                            }
                        }
                    }
                }
            """)
            self.logger.info("Format CSV sélectionné")
            time.sleep(1)

            # 3. Sélectionner la période : attendre le radio XXJOURS (re-rendu après change format)
            xxjours = self.page.locator("input[type='radio'][value='XXJOURS']")
            try:
                xxjours.wait_for(timeout=5000)
                xxjours.click(force=True)
                self.logger.info("Période: 180 derniers jours (XXJOURS)")
            except Exception:
                # Remplir les champs de date (dernier jour ouvré comme fin, 180 jours en arrière)
                from datetime import timedelta
                end_date = datetime.now() - timedelta(days=1)
                # SG n'accepte que les jours ouvrés : reculer si samedi (5) ou dimanche (6)
                while end_date.weekday() >= 5:
                    end_date -= timedelta(days=1)
                start_date = end_date - timedelta(days=179)
                start_str = start_date.strftime("%d/%m/%Y")
                end_str = end_date.strftime("%d/%m/%Y")

                self.page.evaluate(f"""
                    () => {{
                        // Chercher les champs de date (input type=text ou date)
                        const inputs = document.querySelectorAll('input[type="text"], input[type="date"]');
                        const dateInputs = Array.from(inputs).filter(i =>
                            i.name && (i.name.includes('date') || i.name.includes('Date') ||
                            i.id && (i.id.includes('date') || i.id.includes('Date')))
                        );
                        if (dateInputs.length >= 2) {{
                            dateInputs[0].value = '{start_str}';
                            dateInputs[0].dispatchEvent(new Event('input', {{bubbles: true}}));
                            dateInputs[0].dispatchEvent(new Event('change', {{bubbles: true}}));
                            dateInputs[1].value = '{end_str}';
                            dateInputs[1].dispatchEvent(new Event('input', {{bubbles: true}}));
                            dateInputs[1].dispatchEvent(new Event('change', {{bubbles: true}}));
                        }}
                        // Aussi chercher par placeholder ou label
                        const allInputs = document.querySelectorAll('input');
                        for (const inp of allInputs) {{
                            const ph = (inp.placeholder || '').toLowerCase();
                            const nm = (inp.name || '').toLowerCase();
                            if (ph.includes('début') || nm.includes('debut') || nm.includes('start')) {{
                                inp.value = '{start_str}';
                                inp.dispatchEvent(new Event('input', {{bubbles: true}}));
                                inp.dispatchEvent(new Event('change', {{bubbles: true}}));
                            }}
                            if (ph.includes('fin') || nm.includes('fin') || nm.includes('end')) {{
                                inp.value = '{end_str}';
                                inp.dispatchEvent(new Event('input', {{bubbles: true}}));
                                inp.dispatchEvent(new Event('change', {{bubbles: true}}));
                            }}
                        }}
                    }}
                """)
                self.logger.info(f"Période: {start_str} → {end_str}")
            time.sleep(1)

            # 4. Télécharger
            self._alert_text = None
            download_link = self.page.locator(
                "a[href*='telecharger'], button[onclick*='telecharger']"
            )
            if download_link.count() == 0:
                self.logger.error("Bouton 'Télécharger' non trouvé")
                return None

            try:
                with self.page.expect_download(timeout=30000) as download_info:
                    download_link.first.click(force=True)

                download = download_info.value
                clean_name = re.sub(r'\(\d+\)', '', download.suggested_filename).strip()
                target_path = self.dropbox_dir / clean_name
                download.save_as(str(target_path))

                self.logger.info(f"  {target_path.name}")
                self.downloads.append(target_path)
                return target_path

            except PlaywrightTimeout:
                if self._alert_text:
                    self.logger.error(f"Alerte SG: {self._alert_text}")
                self.logger.error("Timeout téléchargement compte courant")
                self._dump_page_debug('download_fail_cpt_courant', force=True)
                return None

        except Exception as e:
            self.logger.error(f"Erreur export compte courant: {e}")
            return None

    def export_epargne_csv(self, compte_info):
        """Exporte le CSV d'un compte épargne via URL directe.

        Args:
            compte_info: tuple (numéro, nom, id_technique)

        Returns:
            Path du fichier téléchargé ou None
        """
        numero, nom, id_technique = compte_info
        url = f"{URL_BASE_CBO}#/operations?b64e200_prestationIdTechnique={id_technique}"

        self.logger.info(f"Export {nom}...")

        try:
            # Navigation SPA hash routing
            self._navigate_spa(url)
            time.sleep(2)

            # Chercher le bouton "Exporter au format CSV"
            export_btn = self.page.locator(
                "button:has(span:has-text('Exporter au format CSV')), "
                "button:has-text('Exporter'), "
                "a:has-text('Exporter')"
            )

            try:
                export_btn.first.wait_for(state="visible", timeout=10000)
            except PlaywrightTimeout:
                self.logger.error(f"  Bouton export non trouvé pour {nom}")
                return None

            # Télécharger
            try:
                with self.page.expect_download(timeout=30000) as download_info:
                    export_btn.first.click()

                download = download_info.value
                target_path = self.dropbox_dir / download.suggested_filename
                # Nettoyer le nom (retirer les (1), (2), etc.)
                clean_name = re.sub(r'\(\d+\)', '', target_path.name).strip()
                if clean_name != target_path.name:
                    target_path = self.dropbox_dir / clean_name
                download.save_as(str(target_path))

                self.logger.info(f"  {target_path.name}")
                self.downloads.append(target_path)
                return target_path

            except PlaywrightTimeout:
                self.logger.error(f"  Timeout téléchargement {nom}")
                return None

        except Exception as e:
            self.logger.error(f"  Erreur export {nom}: {e}")
            return None

    def export_all_epargne_csv(self):
        """Exporte les CSV de tous les comptes épargne (hors compte courant).

        Returns:
            Liste des fichiers téléchargés
        """
        fichiers = []
        comptes_epargne = [c for c in COMPTES_BANCAIRES if c[0] != COMPTE_PRINCIPAL]

        self.logger.info(f"Export des {len(comptes_epargne)} comptes épargne...")

        for compte_info in comptes_epargne:
            fichier = self.export_epargne_csv(compte_info)
            if fichier:
                fichiers.append(fichier)

        self.logger.info(f"  {len(fichiers)}/{len(comptes_epargne)} comptes exportés")
        return fichiers

    def export_assurance_vie_supports(self, assurance_info):
        """Télécharge les supports XLSX d'une assurance vie via URL directe.

        Args:
            assurance_info: tuple (nom, id_technique)

        Returns:
            Path du fichier téléchargé ou None
        """
        nom, id_technique = assurance_info
        url = f"{URL_BASE_AVD}#/accueil_contrat/{id_technique}"

        self.logger.info(f"Export supports {nom}...")

        try:
            # Forcer un vrai rechargement en passant par about:blank
            # (goto avec même base URL + hash différent = same-page navigation, pas de reload)
            self.page.goto("about:blank", wait_until="domcontentloaded", timeout=10000)
            self.page.goto(url, wait_until="domcontentloaded", timeout=30000)

            # Attendre chargement (disparition du "Veuillez patienter")
            try:
                self.page.locator("//*[contains(text(), 'Veuillez patienter')]").wait_for(
                    state="hidden", timeout=15000
                )
            except PlaywrightTimeout:
                pass
            time.sleep(2)

            # Chercher le bouton de téléchargement
            download_btn = self.page.locator(
                "button:has(span:has-text('Télécharger la liste des supports')), "
                "a:has-text('Télécharger la liste des supports'), "
                "button:has-text('supports')"
            )

            try:
                download_btn.first.wait_for(state="visible", timeout=10000)
            except PlaywrightTimeout:
                self.logger.error(f"  Bouton téléchargement non trouvé pour {nom}")
                return None

            # Télécharger
            try:
                with self.page.expect_download(timeout=30000) as download_info:
                    download_btn.first.click()

                download = download_info.value
                new_name = f"SG_{nom}_supports.xlsx"
                target_path = self.dropbox_dir / new_name
                if target_path.exists():
                    target_path.unlink()
                download.save_as(str(target_path))

                self.logger.info(f"  {target_path.name}")
                self.downloads.append(target_path)
                return target_path

            except PlaywrightTimeout:
                self.logger.error(f"  Timeout téléchargement supports {nom}")
                return None

        except Exception as e:
            self.logger.error(f"  Erreur export supports {nom}: {e}")
            return None

    def export_all_assurances_vie_supports(self):
        """Télécharge les supports de toutes les assurances vie.

        Returns:
            Liste des fichiers téléchargés
        """
        fichiers = []

        self.logger.info(f"Export des supports assurances vie ({len(ASSURANCES_VIE)} contrats)...")

        for assurance_info in ASSURANCES_VIE:
            fichier = self.export_assurance_vie_supports(assurance_info)
            if fichier:
                fichiers.append(fichier)

        self.logger.info(f"  {len(fichiers)}/{len(ASSURANCES_VIE)} contrats exportés")
        return fichiers

    def print_assurance_vie_operations_pdf(self, assurance_info):
        """Imprime les opérations d'une assurance vie en PDF.

        Args:
            assurance_info: tuple (nom, id_technique)

        Returns:
            Path du fichier PDF ou None
        """
        nom, id_technique = assurance_info
        url = f"{URL_BASE_AVD}#/accueil_contrat/{id_technique}"
        output_filename = f"SG_{nom}_operations.pdf"

        self.logger.info(f"Impression opérations {nom}...")

        try:
            # Forcer un vrai rechargement en passant par about:blank
            # (goto avec même base URL + hash différent = same-page navigation, pas de reload)
            self.page.goto("about:blank", wait_until="domcontentloaded", timeout=10000)
            self.page.goto(url, wait_until="domcontentloaded", timeout=30000)

            # Attendre que Angular ait fini le rendu
            try:
                self.page.locator("//*[contains(text(), 'Veuillez patienter')]").wait_for(
                    state="hidden", timeout=15000
                )
            except PlaywrightTimeout:
                pass
            time.sleep(2)

            # Cliquer sur "Suivre mes opérations"
            try:
                ops_btn = self.page.locator(
                    "button:has(span:has-text('Suivre mes opérations')), "
                    "a:has-text('Suivre mes opérations'), "
                    "button:has-text('opérations')"
                )
                ops_btn.first.wait_for(state="visible", timeout=10000)
                ops_btn.first.click()
                self.logger.debug(f"  Bouton 'Suivre mes opérations' cliqué")
                time.sleep(3)
            except PlaywrightTimeout:
                self.logger.error(f"  Bouton 'Suivre mes opérations' non trouvé pour {nom}")
                return None

            return self.save_page_as_pdf(output_filename)

        except Exception as e:
            self.logger.error(f"  Erreur opérations {nom}: {e}")
            return None

    def print_all_assurances_vie_operations_pdf(self):
        """Imprime les opérations de toutes les assurances vie en PDF.

        Returns:
            Liste des fichiers PDF créés
        """
        fichiers = []

        self.logger.info(f"Impression PDF opérations assurances vie ({len(ASSURANCES_VIE)} contrats)...")

        for assurance_info in ASSURANCES_VIE:
            fichier = self.print_assurance_vie_operations_pdf(assurance_info)
            if fichier:
                fichiers.append(fichier)

        self.logger.info(f"  {len(fichiers)}/{len(ASSURANCES_VIE)} PDF créés")
        return fichiers

    def print_synthese_pdf(self):
        """Imprime la page synthèse (tous les soldes) en PDF.

        Returns:
            Path du fichier PDF ou None
        """
        self.logger.info("Impression page synthèse (soldes)...")

        try:
            # Navigation SPA hash
            self._navigate_spa(URL_SYNTHESE)

            # Attendre chargement
            try:
                self.page.locator("//*[contains(text(), 'Veuillez patienter')]").wait_for(
                    state="hidden", timeout=15000
                )
            except PlaywrightTimeout:
                pass
            time.sleep(2)

            return self.save_page_as_pdf("Mes comptes en ligne _ SG.pdf")

        except Exception as e:
            self.logger.error(f"  Erreur synthèse: {e}")
            return None

    def _navigate_spa(self, url):
        """Navigation SPA hash routing (pattern DEGIRO).

        Pour les URLs avec hash (#), goto() peut bloquer car le
        domcontentloaded ne se re-déclenche pas. On utilise JS direct.
        """
        if '#' in url:
            # Vérifier si on est déjà sur la bonne base URL
            base_part = url.split('#', 1)[0]
            target_hash = '#' + url.split('#', 1)[1]

            current_url = self.page.evaluate("window.location.href")
            current_base = current_url.split('#', 1)[0] if '#' in current_url else current_url

            if current_base == base_part:
                # Même base URL : changer juste le hash
                self.page.evaluate(f"window.location.hash = '{target_hash}'")
            else:
                # Base URL différente : goto complet
                self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(2)
        else:
            self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(2)


    def run(self):
        """Workflow principal : login, export CSV/XLSX/PDF tous comptes."""
        # Credentials
        username, password = self.load_gpg_credentials()
        if not username or not password:
            self.logger.error("Credentials invalides ou incomplets")
            return False

        # Connexion
        if not self.wait_for_login(username, password):
            self.logger.error("Échec connexion")
            return False

        failed = []

        # Download CSV compte courant (page téléchargement)
        csv_cc = self.download_csv_compte_courant()
        if not csv_cc:
            failed.append("CSV compte courant")

        # Export CSV comptes épargne (URLs directes)
        epargne = self.export_all_epargne_csv()
        n_epargne = len([c for c in COMPTES_BANCAIRES if c[0] != COMPTE_PRINCIPAL])
        if len(epargne) < n_epargne:
            failed.append(f"CSV épargne ({len(epargne)}/{n_epargne})")

        # Téléchargement supports assurances vie (URLs directes)
        av_supports = self.export_all_assurances_vie_supports()
        if len(av_supports) < len(ASSURANCES_VIE):
            failed.append(f"supports AV ({len(av_supports)}/{len(ASSURANCES_VIE)})")

        # Impression PDF opérations assurances vie (URLs directes)
        av_pdf = self.print_all_assurances_vie_operations_pdf()
        if len(av_pdf) < len(ASSURANCES_VIE):
            failed.append(f"PDF opérations AV ({len(av_pdf)}/{len(ASSURANCES_VIE)})")

        # Impression PDF synthèse (tous les soldes)
        synthese = self.print_synthese_pdf()
        if not synthese:
            failed.append("PDF synthèse")

        # Résumé
        total = len(self.downloads)
        if failed:
            self.logger.warning(f"Collecte partielle: {total} fichier(s), échecs: {', '.join(failed)}")
        elif total:
            self.logger.info(f"Collecte terminée: {total} fichier(s)")
        else:
            self.logger.warning("Aucun fichier collecté")
        self.logger.info(f"Destination: {self.dropbox_dir}")

        return not failed


if __name__ == '__main__':
    sys.exit(fetch_main(SgFetcher, description='Fetch données Société Générale via Playwright'))
