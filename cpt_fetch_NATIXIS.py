#!/usr/bin/env python3
"""
cpt_fetch_PEE.py - Récupération automatique des données PEE (Plan d'Épargne Entreprise)
Collecte les valorisations et opérations depuis l'espace Inter Épargne via impression PDF.

Prérequis:
- pip install playwright
- playwright install chrome

Usage:
  ./cpt_fetch_PEE.py           # Mode normal
  ./cpt_fetch_PEE.py -v        # Mode verbeux

Fichiers générés:
  - dropbox/PEE/Mon épargne en détail - Natixis Interépargne.pdf
  - dropbox/PEE/Historique et suivi de mes opérations - Natixis Interépargne.pdf
"""

import sys
import time

from inc_fetch import BaseFetcher, fetch_main, config

# URLs directes
URL_POSITIONS = "https://hsbc.epargnants.votreepargnesalariale.com/front/saving-detail"
URL_OPERATIONS = "https://hsbc.epargnants.votreepargnesalariale.com/front/transactions"

TIMEOUT_PAGE = 15000  # ms


class PeeFetcher(BaseFetcher):
    def __init__(self, verbose=False):
        super().__init__(caller_file=__file__, verbose=verbose,
                         viewport={"width": 1400, "height": 1000})

    def run(self):
        """Logique métier : login + impression 2 PDFs."""
        if not self.wait_for_login():
            self.logger.error("Échec de connexion")
            return False

        failed = []

        pdf_positions = self.print_page_pdf(
            URL_POSITIONS,
            "Mon épargne en détail - Natixis Interépargne.pdf",
            "positions"
        )
        if not pdf_positions:
            failed.append("PDF positions")

        pdf_operations = self.print_page_pdf(
            URL_OPERATIONS,
            "Historique et suivi de mes opérations - Natixis Interépargne.pdf",
            "opérations"
        )
        if not pdf_operations:
            failed.append("PDF opérations")

        total = len(self.downloads)
        if failed:
            self.logger.warning(f"Collecte partielle: {total}/2 PDF, échecs: {', '.join(failed)}")
        elif total:
            self.logger.info(f"Collecte {self.site_name} terminée ({total} PDF)")
        else:
            self.logger.warning("Aucun fichier créé")

        return not failed

    def wait_for_login(self):
        """Navigue vers le dashboard et gère le login si nécessaire.

        Returns:
            True si connecté, False sinon
        """
        self.logger.info("Vérification session...")
        self.page.goto(self.base_url, wait_until="networkidle", timeout=30000)

        # Attendre qu'Angular rende soit le formulaire login soit le dashboard
        login_field = self.page.locator("input[data-testid='login-form-input']")
        try:
            login_field.wait_for(state="visible", timeout=5000)
        except Exception:
            # Pas de formulaire login après 5s → session active
            self.logger.info("Session active (profil Chrome)")
            return True

        # Login requis
        self.logger.info("Connexion requise...")
        login_id, password = self.load_gpg_credentials()
        if not login_id or not password:
            self.logger.error("Credentials non trouvés")
            return False

        return self._fill_login(login_id, password)

    def _fill_login(self, login_id, password):
        """Remplit le formulaire de login.

        Returns:
            True si login réussi, False sinon
        """
        try:
            self._dismiss_cookies()
            self._select_french()

            # Saisir le login
            self.logger.info("Saisie du login...")
            login_field = self.page.locator("input[data-testid='login-form-input']")
            login_field.wait_for(state="visible", timeout=TIMEOUT_PAGE)
            login_field.fill(login_id)

            # Bouton "Je valide"
            validate_btn = self.page.locator("nie-button[data-testid='validate-button'] button")
            validate_btn.wait_for(state="visible", timeout=5000)
            # Attendre que le bouton ne soit plus disabled
            self.page.wait_for_function(
                "() => !document.querySelector(\"nie-button[data-testid='validate-button'] button[disabled]\")",
                timeout=5000
            )
            validate_btn.click()
            self.logger.info("Login validé")

            # Clavier virtuel pour le mot de passe
            self.logger.info("Saisie du mot de passe...")
            if not self._click_virtual_keyboard(password):
                return False

            # Bouton "Suivant"
            next_btn = self.page.locator("//span[contains(text(), 'Suivant') or contains(text(), 'Next')]")
            next_btn.wait_for(state="visible", timeout=TIMEOUT_PAGE)
            next_btn.click()
            self.logger.info("Mot de passe validé")

            # Vérifier connexion réussie
            self.page.wait_for_function(
                "() => document.title.includes('Tableau de bord')",
                timeout=15000
            )
            self.logger.info("Connexion réussie")
            return True

        except Exception as e:
            self.logger.error(f"Erreur connexion: {e}")
            return False

    def _dismiss_cookies(self):
        """Accepte le popup cookies si présent."""
        try:
            cookie_btn = self.page.locator(
                "//button[contains(text(), 'Tout accepter') or contains(text(), 'Accept all')]"
            )
            cookie_btn.first.click(timeout=3000)
            self.logger.info("Cookies acceptés")
        except Exception:
            pass

    def _select_french(self):
        """Sélectionne la langue française via le mat-select Angular."""
        try:
            lang_select = self.page.locator("#select-language")
            lang_select.wait_for(state="visible", timeout=10000)
            lang_select.click()
            time.sleep(0.3)

            french_option = self.page.locator("//mat-option[contains(., 'Français')]")
            french_option.wait_for(state="visible", timeout=5000)
            french_option.click(force=True)
            self.logger.info("Langue française sélectionnée")
            time.sleep(0.5)
        except Exception as e:
            self.logger.warning(f"Langue non sélectionnée: {e}")

    def _click_virtual_keyboard(self, password):
        """Clique sur le clavier virtuel PEE (chiffres dans le HTML, pas d'OCR).

        Returns:
            True si succès, False sinon
        """
        try:
            keyboard = self.page.locator("app-login-password-keyboard")
            keyboard.wait_for(state="visible", timeout=TIMEOUT_PAGE)

            buttons = keyboard.locator("app-login-password-keyboard-input button")
            count = buttons.count()
            self.logger.verbose(f"{count} boutons détectés")

            # Mapper chaque bouton à son chiffre
            button_map = {}
            for i in range(count):
                btn = buttons.nth(i)
                digit_span = btn.locator("span.text-primary-600")
                if digit_span.count() > 0:
                    digit = digit_span.text_content().strip()
                    if digit.isdigit():
                        button_map[digit] = btn

            if not button_map:
                self.logger.error("Aucun chiffre détecté sur le clavier")
                return False

            self.logger.verbose(f"Clavier déchiffré: {len(button_map)} chiffres")

            # Cliquer sur chaque chiffre du mot de passe
            for char in password:
                if char not in button_map:
                    self.logger.error(f"Chiffre '{char}' non trouvé sur le clavier")
                    return False
                button_map[char].click()
                time.sleep(0.1)

            self.logger.info("Mot de passe saisi")
            return True

        except Exception as e:
            self.logger.error(f"Erreur clavier virtuel: {e}")
            return False

    def print_page_pdf(self, url, filename, description):
        """Navigue vers une URL et imprime la page en PDF via CDP.

        Args:
            url: URL de la page à imprimer
            filename: Nom du fichier PDF de sortie
            description: Description pour les logs

        Returns:
            Path du fichier créé ou None
        """
        self.logger.info(f"Impression {description}...")

        try:
            self.page.goto(url, wait_until="networkidle", timeout=30000)

            # Attendre le chargement Angular
            try:
                self.page.locator("app-root").wait_for(state="attached", timeout=TIMEOUT_PAGE)
                self.page.wait_for_load_state("networkidle", timeout=TIMEOUT_PAGE)
                time.sleep(2)  # Laisser Angular finir le rendu des données
            except Exception:
                self.logger.warning(f"Timeout chargement {description}")

            return self.save_page_as_pdf(filename)

        except Exception as e:
            self.logger.error(f"  Erreur impression {description}: {e}")
            return None


if __name__ == '__main__':
    sys.exit(fetch_main(PeeFetcher, description='Fetch données PEE via Playwright'))
