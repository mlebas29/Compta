#!/usr/bin/env python3
"""
cpt_fetch_BB.py - Récupération automatique des données BoursoBank

Login automatique (GPG) avec clavier virtuel OCR (pytesseract), export CSV
comptes bancaires et titres, impression PDF.

Prérequis:
- pip install playwright pytesseract Pillow
- playwright install chrome
- tesseract-ocr installé (apt install tesseract-ocr)

Usage:
  ./cpt_fetch_BB.py           # Mode normal
  ./cpt_fetch_BB.py -v        # Mode verbeux

Fichiers générés:
  - dropbox/BB/export_compte_principal.csv (opérations compte chèque)
  - dropbox/BB/export_livret_bourso.csv (opérations livret)
  - dropbox/BB/export-operations-*.csv (mouvements titres horodatés)
  - dropbox/BB/export-positions-instantanees-*.csv (positions titres)
  - dropbox/BB/Portefeuille - BoursoBank.pdf (solde Espèces portefeuille)
  - dropbox/BB/Mes Comptes - BoursoBank.pdf (soldes tous comptes)
"""

import sys
import json
import base64
import time
from pathlib import Path
from datetime import datetime, timedelta

from inc_fetch import BaseFetcher, fetch_main
from inc_format import site_name_from_file

SITE = site_name_from_file(__file__)

# ============================================================================
# CONFIGURATION
# ============================================================================

# Comptes BB : chargés depuis config_accounts.json
_ACCOUNTS_JSON = Path(__file__).parent / 'config_accounts.json'
with open(_ACCOUNTS_JSON, 'r', encoding='utf-8') as _f:
    _bb_config = json.load(_f).get(SITE, {})
_BB_ACCOUNTS = {
    a['numero']: a['name']
    for a in _bb_config.get('accounts', [])
    if 'numero' in a
}

TIMEOUT_PAGE = 15000  # ms

# Période de collecte (6 mois)
COLLECTION_MONTHS = 6

# Clavier téléphonique : lettre → chiffre
PHONE_LETTERS = {
    'A': '2', 'B': '2', 'C': '2',
    'D': '3', 'E': '3', 'F': '3',
    'G': '4', 'H': '4', 'I': '4',
    'J': '5', 'K': '5', 'L': '5',
    'M': '6', 'N': '6', 'O': '6',
    'P': '7', 'Q': '7', 'R': '7', 'S': '7',
    'T': '8', 'U': '8', 'V': '8',
    'W': '9', 'X': '9', 'Y': '9', 'Z': '9',
}


def get_date_range():
    """Calcule les dates de début et fin pour la collecte (6 mois)."""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=180)
    return start_date.strftime("%d/%m/%Y"), end_date.strftime("%d/%m/%Y")


class BbFetcher(BaseFetcher):
    def __init__(self, verbose=False):
        super().__init__(caller_file=__file__, verbose=verbose, viewport={"width": 1400, "height": 1000})

    def wait_for_login(self, username, password):
        """Navigue vers /connexion/ et gère le login si nécessaire.

        Args:
            username: Identifiant BoursoBank
            password: Mot de passe (chiffres pour clavier virtuel)

        Returns:
            True si connecté, False sinon
        """
        self.logger.info("Vérification session...")
        self.page.goto(f"{self.base_url}/connexion/", wait_until="domcontentloaded", timeout=30000)
        time.sleep(2)

        # Vérifier si déjà connecté (redirigé hors de /connexion)
        current_url = self.page.url
        if '/connexion' not in current_url:
            # Vérifier si la page de sécurisation est affichée
            if '/securisation' in current_url:
                self.logger.info("Session active mais sécurisation requise")
                return self._handle_securisation()
            self.logger.info("Session active (profil Chrome)")
            return True

        # Login requis — retry avec nouveau clavier randomisé
        max_retries = 2
        for attempt in range(1, max_retries + 1):
            if attempt > 1:
                self.logger.info(f"Tentative {attempt}/{max_retries} (nouveau clavier randomisé)")
                time.sleep(2)

            result = self._try_login_once(username, password)

            if result == 'success':
                if attempt > 1:
                    self.logger.info(f"Connexion réussie à la tentative {attempt}")
                return True
            elif result == 'invalid':
                if attempt < max_retries:
                    self.logger.warning(f"Tentative {attempt} échouée (OCR), retry...")
                    continue
                else:
                    self.logger.error(f"Échec après {max_retries} tentatives")
                    return False
            else:  # 'error'
                self.logger.error("Erreur fatale (non liée à l'OCR)")
                return False

        return False

    def _try_login_once(self, username, password):
        """Tentative de connexion unique.

        Returns:
            'success', 'invalid' (OCR incorrect), ou 'error'
        """
        try:
            # Page connexion
            self.logger.info("Page connexion - Saisie identifiant")
            self.page.goto(f"{self.base_url}/connexion/", wait_until="domcontentloaded", timeout=30000)
            time.sleep(2)

            self._dismiss_cookies()

            # Saisir l'identifiant
            username_field = self.page.locator("#form_clientNumber")
            username_field.wait_for(state="visible", timeout=TIMEOUT_PAGE)
            username_field.fill(username)

            # Cliquer sur Suivant
            next_button = self.page.locator("button[data-login-id-submit]")
            next_button.click()
            self.logger.info("Identifiant saisi")
            time.sleep(2)

            # Page mot de passe — clavier virtuel
            self.logger.info("Page mot de passe - Clavier virtuel")

            # Décoder le clavier virtuel avec OCR
            keyboard_map = self._decode_keyboard_matrix()

            if len(keyboard_map) < 8:
                self.logger.warning(f"Clavier incomplet ({len(keyboard_map)}/10)")

            # Saisir le mot de passe
            for digit in password:
                if not self._click_virtual_keyboard_digit(digit, keyboard_map):
                    self.logger.error(f"Échec saisie chiffre: {digit}")
                    return 'invalid'

            self.logger.info("Mot de passe saisi")

            # Cliquer sur "Je me connecte"
            login_button = self.page.locator("button[type='submit']")
            login_button.click()
            self.logger.info("Connexion en cours...")

            # Attendre que la page change (sortie de /connexion)
            try:
                self.page.wait_for_function(
                    "() => !window.location.href.includes('/connexion')",
                    timeout=15000
                )
                time.sleep(2)
            except Exception:
                self.logger.warning("Timeout: URL n'a pas changé après 15s")

                # Vérifier si erreur "identifiant ou mot de passe invalide"
                error_loc = self.page.locator("//*[contains(text(), 'Identifiant') and contains(text(), 'invalide')]")
                if error_loc.count() > 0:
                    self.logger.warning("Message 'identifiant ou mot de passe invalide' détecté")
                    return 'invalid'

                # Toujours sur page de connexion = échec
                if '/connexion' in self.page.url:
                    self.logger.warning("Toujours sur la page de connexion")
                    return 'invalid'

                return 'error'

            # Double vérification
            if '/connexion' in self.page.url:
                self.logger.warning("Toujours sur la page de connexion après tentative")
                return 'invalid'

            # Vérifier si sécurisation ou 2FA est nécessaire
            if '/securisation' in self.page.url:
                if not self._handle_securisation():
                    return 'error'
            elif not self._is_on_dashboard():
                if not self._wait_for_2fa():
                    return 'error'

            self.logger.info("Connexion réussie")
            return 'success'

        except Exception as e:
            self.logger.error(f"Erreur connexion: {e}")
            return 'error'

    def _dismiss_cookies(self):
        """Accepte le popup cookies si présent."""
        try:
            cookie_btn = self.page.locator(
                "//*[contains(text(), 'Tout accepter') or contains(text(), 'tout accepter')]"
            )
            cookie_btn.first.click(timeout=3000)
            self.logger.info("Cookies acceptés")
            time.sleep(1)
        except Exception:
            pass

    def _is_on_dashboard(self):
        """Détecte si on est sur le dashboard BoursoBank (pas en auth/2FA)."""
        url = self.page.url
        auth_paths = [
            '/connexion', '/login', '/securite', '/securisation',
            '/confirmation', '/auth'
        ]
        if any(p in url for p in auth_paths):
            return False
        if 'boursobank.com' not in url:
            return False
        # Vérifier qu'il y a du contenu dashboard (pas juste une page vide)
        try:
            return self.page.locator("a[href*='/compte/']").count() > 0
        except Exception:
            return False

    def _handle_securisation(self):
        """Gère le flow de sécurisation BoursoBank (nouvel appareil).

        Étape 1 : /securisation → clic "Suivant"
        Étape 2 : /securisation/validation → clic "Poursuivre"
        Étape 3 : attente validation 2FA sur mobile

        Returns:
            True si la sécurisation est complétée, False si timeout/erreur
        """
        self.logger.info("Page sécurisation détectée (nouvel appareil)")

        self._dismiss_cookies()

        # Étape 1 : cliquer "Suivant" sur /securisation
        try:
            suivant_btn = self.page.locator(
                "button:has-text('Suivant'), a:has-text('Suivant')"
            )
            suivant_btn.first.wait_for(state="visible", timeout=5000)
            suivant_btn.first.click()
            self.logger.info("Étape 1/3 : Suivant")
            time.sleep(3)
        except Exception as e:
            self.logger.warning(f"Bouton Suivant non trouvé: {e}")

        # Étape 2 : cliquer "Poursuivre" sur /securisation/validation
        try:
            poursuivre_btn = self.page.locator(
                "button:has-text('Poursuivre'), a:has-text('Poursuivre')"
            )
            poursuivre_btn.first.wait_for(state="visible", timeout=5000)
            poursuivre_btn.first.click()
            self.logger.info("Étape 2/3 : Poursuivre")
            time.sleep(3)
        except Exception as e:
            self.logger.warning(f"Bouton Poursuivre non trouvé: {e}")

        # Étape 3 : cliquer "Envoyer une notification à mon appareil"
        try:
            notif_btn = self.page.locator(
                "button:has-text('Envoyer une notification'), "
                "a:has-text('Envoyer une notification')"
            )
            notif_btn.first.wait_for(state="visible", timeout=5000)
            notif_btn.first.click()
            self.logger.alert("VALIDATION 2FA — Notification envoyée, valide sur l'appli mobile BoursoBank")
            time.sleep(3)
        except Exception as e:
            self.logger.warning(f"Bouton notification non trouvé: {e}")

        # Attendre la validation 2FA sur mobile
        return self._wait_for_2fa()

    def _wait_for_2fa(self):
        """Attend la validation 2FA par l'utilisateur sur l'app mobile.

        Mode passif uniquement : observe l'URL sans naviguer pour ne pas
        interférer avec le flow de sécurisation BoursoBank.
        Après 60s, tente un reload (pas une navigation) pour forcer la
        détection si la page ne redirige pas automatiquement.

        Returns:
            True si connecté, False si timeout
        """
        TIMEOUT_2FA = 180  # 3 minutes
        RELOAD_AFTER = 60  # Reload (pas navigation) après 60s
        RELOAD_INTERVAL = 20

        self.logger.alert("VALIDATION 2FA — Valide sur l'appli mobile BoursoBank")

        start_time = time.time()
        last_url = ""
        last_reload = 0

        while time.time() - start_time < TIMEOUT_2FA:
            elapsed = time.time() - start_time
            current_url = self.page.url

            if current_url != last_url:
                self.logger.debug(f"  URL: {current_url}")
                last_url = current_url

            # Vérification passive : on est sur le dashboard ?
            if self._is_on_dashboard():
                self.logger.info(f"2FA validée ({int(elapsed)}s)")
                time.sleep(2)
                return True

            # Vérifier les autres onglets
            for p in self.context.pages:
                if p != self.page and 'boursobank.com' in p.url:
                    if not any(x in p.url for x in ['/connexion', '/securisation']):
                        self.page = p
                        if self._is_on_dashboard():
                            self.logger.info(f"2FA validée ({int(elapsed)}s, nouvel onglet)")
                            time.sleep(2)
                            return True

            # Après 60s, reload la page courante (pas de navigation vers une autre URL)
            if elapsed > RELOAD_AFTER and elapsed - last_reload > RELOAD_INTERVAL:
                last_reload = elapsed
                try:
                    self.page.reload(wait_until="domcontentloaded", timeout=10000)
                    time.sleep(2)
                    if self._is_on_dashboard():
                        self.logger.info(f"2FA validée ({int(elapsed)}s)")
                        return True
                    self.logger.debug(f"  En attente 2FA ({int(elapsed)}s)...")
                except Exception:
                    pass

            time.sleep(3)

        self.logger.error(f"Timeout 2FA après {TIMEOUT_2FA}s")
        return False

    def _decode_keyboard_matrix(self):
        """Décode le clavier virtuel BoursoBank en utilisant OCR.

        Approche en 3 phases :
        1. OCR chiffre (partie haute) + OCR lettres (partie basse) pour chaque bouton
        2. Construction du mapping : lettres font foi pour 2-9, OCR chiffre en fallback
        3. Attribution de 0 et 1 aux boutons sans lettres

        Returns:
            dict: mapping {chiffre: data-matrix-key}
        """
        try:
            import pytesseract
            from PIL import Image, ImageEnhance
        except ImportError:
            self.logger.error("pytesseract ou PIL non disponible pour OCR")
            return {}

        try:
            # Attendre que le clavier soit chargé
            self.page.locator("button[data-matrix-key]").first.wait_for(
                state="visible", timeout=10000
            )
            time.sleep(2)

            # Trouver tous les boutons du clavier
            buttons = self.page.locator("button[data-matrix-key]").all()

            if len(buttons) < 10:
                self.logger.error(f"Seulement {len(buttons)} boutons trouvés (attendu: 10)")
                return {}

            self.logger.info(f"Décodage de {len(buttons)} touches du clavier virtuel")

            # Screenshot complet une fois
            screenshot_path = self.logs_dir / 'debug' / 'bb_keyboard_full.png'
            screenshot_path.parent.mkdir(parents=True, exist_ok=True)
            self.page.screenshot(path=str(screenshot_path))
            full_screenshot = Image.open(screenshot_path)

            # ── Phase 1 : Collecter OCR chiffre + OCR lettres pour chaque bouton ──
            button_data = []  # (matrix_key, button, digit_ocr, letter_digit)

            for button in buttons:
                try:
                    matrix_key = button.get_attribute('data-matrix-key')

                    img_element = button.locator('img')
                    if img_element.count() == 0:
                        continue
                    src = img_element.get_attribute('src')
                    if not src or not src.startswith('data:image/svg+xml;base64,'):
                        continue

                    box = button.bounding_box()
                    if not box:
                        continue

                    # OCR du chiffre (partie haute)
                    digit_ocr = self._ocr_button_digit(
                        box, full_screenshot, pytesseract, Image, ImageEnhance
                    )

                    # OCR des lettres (partie basse) → identification par clavier téléphonique
                    letter_digit = self._ocr_button_letters(
                        box, full_screenshot, pytesseract, Image, ImageEnhance
                    )

                    self.logger.debug(
                        f"  Touche {matrix_key}: chiffre_OCR={digit_ocr or '?'}, "
                        f"lettres→{letter_digit or 'aucune'}"
                    )

                    button_data.append((matrix_key, button, digit_ocr, letter_digit))

                    # Debug: sauvegarder images
                    if self.debug:
                        x, y, w, h = box['x'], box['y'], box['width'], box['height']
                        full_btn = full_screenshot.crop((x, y, x + w, y + int(h * 0.95)))
                        label = letter_digit or digit_ocr or '?'
                        full_btn.save(
                            self.logs_dir / 'debug' / f"keyboard_full_{matrix_key}_{label}.png"
                        )

                except Exception as e:
                    self.logger.debug(f"  Erreur décodage bouton: {e}")
                    continue

            # ── Phase 2 : Construire le mapping (lettres font foi pour 2-9) ──
            keyboard_map = {}
            no_letter_buttons = []  # boutons sans lettres détectées (candidats 0/1)

            for matrix_key, button, digit_ocr, letter_digit in button_data:
                if letter_digit:
                    # Les lettres identifient le chiffre sans ambiguïté
                    if letter_digit != digit_ocr:
                        self.logger.info(
                            f"  Correction {matrix_key}: OCR={digit_ocr} → lettres={letter_digit}"
                        )
                    if letter_digit in keyboard_map:
                        self.logger.warning(
                            f"  Doublon lettres '{letter_digit}' sur "
                            f"{keyboard_map[letter_digit]} et {matrix_key}"
                        )
                    keyboard_map[letter_digit] = matrix_key
                else:
                    no_letter_buttons.append((matrix_key, button, digit_ocr))

            # ── Phase 3 : Attribuer 0 et 1 aux boutons sans lettres ──
            if len(no_letter_buttons) == 2:
                mk1, btn1, d1 = no_letter_buttons[0]
                mk2, btn2, d2 = no_letter_buttons[1]

                # Cas simple : l'OCR a correctement identifié l'un des deux
                if d1 == '0' and d2 != '0':
                    keyboard_map['0'] = mk1
                    keyboard_map['1'] = mk2
                elif d2 == '0' and d1 != '0':
                    keyboard_map['0'] = mk2
                    keyboard_map['1'] = mk1
                elif d1 == '1' and d2 != '1':
                    keyboard_map['1'] = mk1
                    keyboard_map['0'] = mk2
                elif d2 == '1' and d1 != '1':
                    keyboard_map['1'] = mk2
                    keyboard_map['0'] = mk1
                else:
                    # OCR indécis : utiliser la densité de pixels
                    # '0' = ovale fermé (plus de pixels), '1' = trait fin (moins de pixels)
                    px1 = self._count_digit_pixels(btn1, full_screenshot)
                    px2 = self._count_digit_pixels(btn2, full_screenshot)
                    self.logger.debug(f"  Pixels 0/1: {mk1}={px1}, {mk2}={px2}")
                    if px1 > px2:
                        keyboard_map['0'] = mk1
                        keyboard_map['1'] = mk2
                    else:
                        keyboard_map['0'] = mk2
                        keyboard_map['1'] = mk1
                    self.logger.info(
                        f"  Attribution pixels: 0→{keyboard_map['0']}, 1→{keyboard_map['1']}"
                    )
            elif len(no_letter_buttons) == 1:
                mk, btn, d = no_letter_buttons[0]
                missing = {'0', '1'} - set(keyboard_map.keys())
                if len(missing) == 1:
                    keyboard_map[missing.pop()] = mk
            elif len(no_letter_buttons) > 2:
                # Fallback : OCR lettres a échoué pour certains boutons 2-9
                self.logger.warning(
                    f"  {len(no_letter_buttons)} boutons sans lettres "
                    f"(attendu: 2) — utilisation OCR chiffre en fallback"
                )
                for mk, btn, d in no_letter_buttons:
                    if d and d not in keyboard_map:
                        keyboard_map[d] = mk

            if len(keyboard_map) == 10:
                self.logger.info(f"Clavier décodé: 10 chiffres")
            else:
                self.logger.warning(f"Clavier incomplet: {len(keyboard_map)}/10 chiffres")

            return keyboard_map

        except Exception as e:
            self.logger.error(f"Erreur décodage clavier: {e}")
            return {}

    def _ocr_button_digit(self, box, full_screenshot, pytesseract, Image, ImageEnhance):
        """OCR du chiffre dans la partie haute d'un bouton.

        Returns:
            str: chiffre détecté ('0'-'9') ou ''
        """
        x, y, w, h = box['x'], box['y'], box['width'], box['height']

        for crop_ratio in [0.5, 0.85]:
            margin_sides = int(w * 0.15)
            margin_top = int(h * 0.05)
            crop_height = int(h * crop_ratio)

            img = full_screenshot.crop((
                x + margin_sides, y + margin_top,
                x + w - margin_sides, y + margin_top + crop_height
            ))

            img = img.convert('L')
            img_w, img_h = img.size
            img = img.resize((img_w * 2, img_h * 2), Image.Resampling.LANCZOS)
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(2.5)
            img = img.point(lambda p: 255 if p > 120 else 0)

            for ocr_config in [
                r'--oem 3 --psm 10 -c tessedit_char_whitelist=0123456789',
                r'--oem 3 --psm 8 -c tessedit_char_whitelist=0123456789',
            ]:
                result = pytesseract.image_to_string(img, config=ocr_config).strip()
                result = ''.join(c for c in result if c.isdigit())
                if result and len(result) == 1:
                    return result

        return ''

    def _ocr_button_letters(self, box, full_screenshot, pytesseract, Image, ImageEnhance):
        """OCR des lettres dans la partie basse d'un bouton.

        Sur un clavier téléphonique : 2=ABC, 3=DEF, ..., 9=WXYZ.
        0 et 1 n'ont pas de lettres.

        Returns:
            str: chiffre déduit des lettres ('2'-'9') ou None
        """
        x, y, w, h = box['x'], box['y'], box['width'], box['height']
        margin_sides = int(w * 0.1)
        top_offset = int(h * 0.5)

        img = full_screenshot.crop((
            x + margin_sides, y + top_offset,
            x + w - margin_sides, y + h - int(h * 0.05)
        ))

        img = img.convert('L')
        img = img.resize((img.width * 3, img.height * 3), Image.Resampling.LANCZOS)
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(2.5)
        img = img.point(lambda p: 255 if p > 120 else 0)

        for psm in [7, 8, 13]:
            result = pytesseract.image_to_string(
                img,
                config=f'--oem 3 --psm {psm} -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ'
            ).strip()
            letters = ''.join(c for c in result if c.isalpha() and c.isupper())
            if letters:
                # Vote majoritaire sur les lettres reconnues
                digit_votes = {}
                for letter in letters:
                    d = PHONE_LETTERS.get(letter)
                    if d:
                        digit_votes[d] = digit_votes.get(d, 0) + 1
                if digit_votes:
                    return max(digit_votes, key=digit_votes.get)

        return None

    def _count_digit_pixels(self, button, full_screenshot):
        """Compte les pixels noirs dans la zone chiffre d'un bouton.

        Utilisé pour distinguer 0 (ovale, beaucoup de pixels) de 1 (trait, peu de pixels).
        """
        box = button.bounding_box()
        if not box:
            return 0
        from PIL import Image
        x, y, w, h = box['x'], box['y'], box['width'], box['height']
        margin_sides = int(w * 0.15)
        margin_top = int(h * 0.05)
        crop_height = int(h * 0.5)

        img = full_screenshot.crop((
            x + margin_sides, y + margin_top,
            x + w - margin_sides, y + margin_top + crop_height
        ))
        img = img.convert('L')
        img = img.point(lambda p: 0 if p < 128 else 255)
        return sum(1 for p in img.getdata() if p == 0)

    def _click_virtual_keyboard_digit(self, digit, keyboard_map):
        """Clique sur un chiffre du clavier virtuel.

        Args:
            digit: chiffre à cliquer (str)
            keyboard_map: mapping {chiffre: data-matrix-key}

        Returns:
            True si succès, False sinon
        """
        if digit not in keyboard_map:
            self.logger.error(f"Chiffre {digit} non trouvé dans le clavier")
            return False

        try:
            matrix_key = keyboard_map[digit]
            button = self.page.locator(f"button[data-matrix-key='{matrix_key}']")
            button.click()
            time.sleep(0.3)
            self.logger.debug(f"Clic chiffre: {digit}")
            return True
        except Exception as e:
            self.logger.error(f"Erreur clic chiffre {digit}: {e}")
            return False

    def _click_and_download(self, locator, label, timeout=30):
        """Clic sur un lien/bouton et attente du download avec détection HTTP 401/403.

        Écoute les réponses HTTP en parallèle. Échoue immédiatement si 401/403
        au lieu d'attendre le timeout complet.

        Args:
            locator: Playwright Locator à cliquer
            label: Label pour les logs
            timeout: Timeout en secondes (défaut 30)

        Returns:
            Download object ou None si échec
        """
        download_obj = [None]
        http_error = [None]

        def on_download(dl):
            download_obj[0] = dl

        def on_response(resp):
            if resp.status in (401, 403) and not http_error[0]:
                http_error[0] = (resp.status, resp.url)

        self.page.on("download", on_download)
        self.page.on("response", on_response)

        try:
            locator.click(force=True)

            deadline = time.time() + timeout
            while time.time() < deadline:
                if download_obj[0]:
                    return download_obj[0]
                if http_error[0]:
                    status, url = http_error[0]
                    self.logger.error(f"  HTTP {status} sur {url}")
                    return None
                time.sleep(0.5)

            self.logger.error(f"  Timeout download {label} ({timeout}s)")
            return None
        finally:
            self.page.remove_listener("download", on_download)
            self.page.remove_listener("response", on_response)

    def _fetch_download(self, url, target_path, label):
        """Téléchargement via requête HTTP directe (context.request).

        Utilise les cookies du navigateur pour faire une requête GET directe,
        sans dépendre de la page courante (évite les problèmes de navigation).

        Args:
            url: URL complète du download (form action + params)
            target_path: Path du fichier de sortie
            label: Label pour les logs

        Returns:
            True si succès, False sinon
        """
        try:
            response = self.context.request.get(url)
            self.logger.info(f"  Requête directe {label}: HTTP {response.status}")

            if not response.ok:
                self.logger.error(f"  HTTP {response.status} sur {response.url}")
                return False

            target_path.parent.mkdir(parents=True, exist_ok=True)
            body = response.body()
            with open(target_path, 'wb') as f:
                f.write(body)

            self.logger.info(f"  {target_path.name} (direct)")
            self.downloads.append(target_path)
            return True

        except Exception as e:
            self.logger.error(f"  Requête directe {label}: {e}")
            return False

    def export_account_operations(self, account_name, account_url):
        """Export CSV des opérations d'un compte bancaire.

        Args:
            account_name: nom du fichier de sortie (ex: "compte_principal")
            account_url: URL de la page de détails du compte

        Returns:
            True si succès
        """
        try:
            self.logger.info(f"Export {account_name}")

            self.page.goto(account_url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(2)

            # Cliquer sur "Exporter mes opérations"
            export_link = self.page.locator("a:has-text('Exporter')")
            export_link.first.wait_for(state="visible", timeout=TIMEOUT_PAGE)
            export_link.first.click()
            time.sleep(2)

            # Attendre que le formulaire JS soit chargé
            self.page.locator("#movementSearch_fromDate").wait_for(
                state="visible", timeout=TIMEOUT_PAGE
            )
            time.sleep(1)

            # Remplir les dates via JavaScript
            start_date, end_date = get_date_range()

            self.page.evaluate("""
                ([startDate, endDate]) => {
                    const fromField = document.getElementById('movementSearch_fromDate');
                    fromField.value = startDate;
                    fromField.dispatchEvent(new Event('input', { bubbles: true }));
                    fromField.dispatchEvent(new Event('change', { bubbles: true }));

                    const toField = document.getElementById('movementSearch_toDate');
                    toField.value = endDate;
                    toField.dispatchEvent(new Event('input', { bubbles: true }));
                    toField.dispatchEvent(new Event('change', { bubbles: true }));
                }
            """, [start_date, end_date])

            time.sleep(0.5)

            # Sélectionner format CSV
            csv_radio = self.page.locator("input[value='CSV']")
            if not csv_radio.is_checked():
                csv_radio.click(force=True)

            # Intercepter le téléchargement et cliquer sur Exporter
            target_name = f"export_{account_name}.csv"
            target_path = self.dropbox_dir / target_name

            # Construire l'URL de téléchargement depuis le formulaire
            form_action = self.page.evaluate("""
                () => {
                    const form = document.querySelector('form');
                    return form ? form.action : null;
                }
            """)
            if not form_action:
                self.logger.error(f"  Formulaire export non trouvé")
                return False

            fetch_url = (
                f"{form_action}"
                f"?movementSearch%5BfromDate%5D={start_date}"
                f"&movementSearch%5BtoDate%5D={end_date}"
                f"&movementSearch%5Bformat%5D=CSV"
            )

            if not self._fetch_download(fetch_url, target_path, account_name):
                self._dump_page_debug(f'download_fail_{account_name}', force=True)
                return False

            self.logger.info(f"  {target_name} ({start_date} → {end_date})")
            return True

        except Exception as e:
            self.logger.error(f"Erreur export {account_name}: {e}")
            self._dump_page_debug(f'download_fail_{account_name}', force=True)
            return False

    def export_titres_complete(self):
        """Export positions + mouvements titres en une seule visite.

        1. Navigate to Portefeuille titres
        2. Impression PDF portefeuille (solde Espèces pour Réserve)
        3. Export positions CSV
        4. Basculer sur onglet Mouvements
        5. Export 6 mois de mouvements

        Returns:
            True si succès
        """
        try:
            self.logger.info("Export positions + mouvements titres")

            # Aller sur la page accueil puis Portefeuille titres
            self.page.goto(f"{self.base_url}/", wait_until="domcontentloaded", timeout=30000)
            time.sleep(2)

            titres_link = self.page.locator("a:has-text('Portefeuille titres')")
            titres_link.first.wait_for(state="visible", timeout=TIMEOUT_PAGE)
            titres_link.first.click()
            time.sleep(3)

            # ÉTAPE 1 : PDF portefeuille (solde Espèces pour Réserve)
            self.save_page_as_pdf("Portefeuille - BoursoBank.pdf")

            # ÉTAPE 2 : Export positions CSV
            try:
                csv_link = self.page.locator("a:has-text('Exporter en CSV')")
                csv_link.first.wait_for(state="visible", timeout=TIMEOUT_PAGE)

                download = self._click_and_download(csv_link.first, 'positions')
                if download:
                    target_path = self.dropbox_dir / download.suggested_filename
                    download.save_as(str(target_path))
                    self.logger.info(f"  {download.suggested_filename}")
                    self.downloads.append(target_path)
                else:
                    self._dump_page_debug('download_fail_positions', force=True)
            except Exception as e:
                self.logger.warning(f"  Export positions CSV: {e}")
                self._dump_page_debug('download_fail_positions', force=True)

            # ÉTAPE 3 : Basculer sur onglet Mouvements
            mouvements_tab = self.page.locator("a:has-text('Mouvements')")
            mouvements_tab.first.wait_for(state="visible", timeout=TIMEOUT_PAGE)
            mouvements_tab.first.click()
            time.sleep(2)

            # ÉTAPE 4 : Export mouvements (6 mois)
            self.logger.info("  Export mouvements (6 mois)")

            # Le select natif est masqué par un custom dropdown CSS
            self.page.locator("#form_period").wait_for(state="attached", timeout=TIMEOUT_PAGE)

            # Extraire les valeurs des options AVANT la boucle
            months_data = self.page.evaluate("""
                () => {
                    const select = document.getElementById('form_period');
                    const options = Array.from(select.options);
                    // Options 1 à 6 = les 6 derniers mois
                    return options.slice(1, 7).map(o => ({
                        value: o.value,
                        text: o.text
                    }));
                }
            """)

            for month_info in months_data:
                month_value = month_info['value']
                month_text = month_info['text']
                self.logger.info(f"    {month_text}")

                # Sélectionner le mois et soumettre
                self.page.evaluate("""
                    ([value]) => {
                        const select = document.getElementById('form_period');
                        select.value = value;
                        select.dispatchEvent(new Event('change', { bubbles: true }));
                    }
                """, [month_value])
                time.sleep(0.5)

                self.page.locator("#form_submit").click(force=True)
                time.sleep(2)  # Attendre rechargement complet

                # Télécharger CSV si disponible (retry avec re-fetch du href si 401)
                downloaded = False
                for attempt in range(1, 4):
                    try:
                        csv_link = self.page.locator("a:has-text('Exporter en CSV')")
                        csv_link.first.wait_for(state="visible", timeout=5000)

                        # Extraire le href (frais à chaque tentative — token peut expirer)
                        csv_href = csv_link.first.get_attribute('href')
                        if not csv_href:
                            self.logger.info(f"      Pas de lien CSV")
                            break
                        if csv_href.startswith('/'):
                            csv_href = self.base_url + csv_href
                        target_name = f"export-operations-{month_value}.csv"
                        target_path = self.dropbox_dir / target_name
                        if self._fetch_download(csv_href, target_path, f'mouvements_{month_text}'):
                            self.logger.info(f"      Export CSV: {target_name}")
                            downloaded = True
                            break
                        # Échec : retry après pause
                        if attempt < 3:
                            self.logger.info(f"      Retry {attempt + 1}/3 dans 2s...")
                            time.sleep(2)
                            # Re-soumettre pour rafraîchir le token
                            self.page.locator("#form_submit").click(force=True)
                            time.sleep(2)
                    except Exception as e:
                        self.logger.info(f"      Tentative {attempt}/3 échouée: {e}")
                        if attempt < 3:
                            time.sleep(2)
                if not downloaded:
                    self.logger.info(f"      Échec téléchargement {month_text} après 3 tentatives")

            self.logger.info("  Mouvements titres collectés")
            return True

        except Exception as e:
            self.logger.error(f"Erreur export titres: {e}")
            self._dump_page_debug('download_fail_titres', force=True)
            return False

    def print_accueil_pdf(self):
        """Imprime la page d'accueil (soldes de tous les comptes) en PDF.

        Returns:
            Path du fichier PDF ou None
        """
        self.logger.info("Impression page accueil (soldes)")

        try:
            self.page.goto(f"{self.base_url}/", wait_until="domcontentloaded", timeout=30000)
            time.sleep(2)

            # Attendre que les soldes soient chargés
            try:
                self.page.locator(".c-card-account").first.wait_for(
                    state="visible", timeout=TIMEOUT_PAGE
                )
            except Exception:
                self.logger.warning("Timeout chargement page accueil")

            return self.save_page_as_pdf("Mes Comptes - BoursoBank.pdf")

        except Exception as e:
            self.logger.error(f"  Erreur impression PDF accueil: {e}")
            return None

    def check_downloaded_files(self):
        """Vérifie et renomme les fichiers téléchargés.

        Identification par contenu (numéro de compte dans la première ligne).
        Les numéros et noms de fichiers sont dérivés de config_accounts.json.
        """
        # Mapping numéro → nom de fichier de sortie
        _EXPORT_NAMES = {
            'Compte chèque BB': 'export_compte_principal.csv',
            'Compte livret BB': 'export_livret_bourso.csv',
        }

        # Collecter tous les fichiers à analyser
        export_ops_files = list(self.dropbox_dir.glob('export-operations-*.csv'))
        for name in ['export.csv', 'export (1).csv']:
            f = self.dropbox_dir / name
            if f.exists():
                export_ops_files.append(f)
        export_ops_files = sorted(export_ops_files)

        identified = {}  # numero → csv_file
        mouvements_titres = []

        for csv_file in export_ops_files:
            try:
                with open(csv_file, 'r', encoding='utf-8-sig') as f:
                    header = f.readline().strip().replace('"', '')
                    first_line = f.readline().strip().replace('"', '')

                if 'dateOp;dateVal;label' in header and 'accountNum' in header:
                    for numero in _BB_ACCOUNTS:
                        if numero in first_line:
                            identified[numero] = csv_file
                            break
                elif 'Date opération' in header and 'Code ISIN' in header:
                    mouvements_titres.append(csv_file)
            except Exception as e:
                self.logger.debug(f"Erreur analyse {csv_file.name}: {e}")

        # Renommer les fichiers identifiés
        for numero, csv_file in identified.items():
            account_name = _BB_ACCOUNTS[numero]
            export_name = _EXPORT_NAMES.get(account_name)
            if export_name:
                new_path = self.dropbox_dir / export_name
                if new_path.exists():
                    new_path.unlink()
                csv_file.rename(new_path)
                self.logger.info(f"{csv_file.name} → {export_name}")

        if mouvements_titres:
            self.logger.info(f"{len(mouvements_titres)} fichier(s) mouvements titres")

        # Fichiers positions
        export_pos = list(self.dropbox_dir.glob('export-positions-instantanees-*.csv'))
        if export_pos:
            self.logger.info(f"{len(export_pos)} fichier(s) positions titres")

        # PDF soldes
        pdf_files = list(self.dropbox_dir.glob('*.pdf'))
        for pdf in pdf_files:
            self.logger.info(f"{pdf.name} (soldes)")


    def run(self):
        """Workflow principal : login, export comptes, titres, PDF."""
        # Credentials
        username, password = self.load_gpg_credentials()
        if not username or not password:
            self.logger.error("Credentials invalides ou incomplets")
            return False

        # Connexion
        if not self.wait_for_login(username, password):
            self.logger.error("Échec connexion")
            return False

        # Collecte des données
        success_count = 0
        total_count = 4

        # Extraire les URLs des comptes depuis la page accueil
        self.logger.info("Extraction URLs des comptes")
        self.page.goto(f"{self.base_url}/", wait_until="domcontentloaded", timeout=30000)
        time.sleep(3)

        # Extraire les liens de comptes réels (URLs avec hash 32 chars)
        account_links = self.page.evaluate("""
            () => {
                const links = document.querySelectorAll('a[href]');
                const accounts = [];
                // Pattern : /compte/<type>/[.../<subtype>/]<hash-32-chars>/
                const hashPattern = /\\/compte\\/(?:\\w+\\/)+[a-f0-9]{32}\\//;
                for (const link of links) {
                    const href = link.getAttribute('href');
                    const text = link.textContent.trim().replace(/\\s+/g, ' ');
                    if (href && hashPattern.test(href)) {
                        accounts.push({href, text: text.substring(0, 80)});
                    }
                }
                return accounts;
            }
        """)

        self.logger.verbose(f"Liens comptes trouvés: {len(account_links)}")
        for a in account_links:
            self.logger.verbose(f"  {a['text']} → {a['href']}")

        # Identifier les comptes par type d'URL
        compte_url = None
        livret_url = None
        for a in account_links:
            href = a['href']
            if href.startswith('/'):
                href = self.base_url + href
            if not compte_url and '/compte/cav/' in href:
                compte_url = href
            if not livret_url and ('/compte/epargne/' in href or '/csl/' in href):
                livret_url = href

        # Compte principal
        if compte_url:
            self.logger.info(f"  Compte principal: {compte_url}")
            if self.export_account_operations("compte_principal", compte_url):
                success_count += 1
        else:
            self.logger.warning("Compte principal non trouvé sur le dashboard")

        # Livret Bourso+
        if livret_url:
            self.logger.info(f"  Livret: {livret_url}")
            if self.export_account_operations("livret_bourso", livret_url):
                success_count += 1
        else:
            self.logger.warning("Livret Bourso+ non trouvé sur le dashboard")

        # Portefeuille titres complet (positions + mouvements)
        if self.export_titres_complete():
            success_count += 1

        # PDF page accueil (soldes)
        if self.print_accueil_pdf():
            success_count += 1

        # Vérifier les fichiers téléchargés
        time.sleep(2)
        self.check_downloaded_files()

        # Résumé
        total_files = len(self.downloads)
        if success_count < total_count:
            self.logger.warning(f"Collecte partielle: {success_count}/{total_count} sources, {total_files} fichier(s)")
        else:
            self.logger.info(f"Collecte terminée: {success_count}/{total_count} sources, {total_files} fichier(s)")
        self.logger.info(f"Fichiers dans: {self.dropbox_dir}")

        return success_count == total_count


if __name__ == '__main__':
    sys.exit(fetch_main(BbFetcher, description='Fetch données BoursoBank via Playwright'))
