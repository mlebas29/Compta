#!/usr/bin/env python3
"""
cpt_fetch_AMAZON.py - Récupération du solde et historique carte cadeau Amazon

Login semi-automatique : Chrome remplit les identifiants via GPG,
l'utilisateur gère la 2FA si nécessaire, puis le script scrape le tableau
des opérations depuis la page solde carte cadeau.

Prérequis:
- pip install playwright
- playwright install chrome

Usage:
  ./cpt_fetch_AMAZON.py         # Mode normal
  ./cpt_fetch_AMAZON.py -v      # Mode verbeux

Workflow:
  1. Lance Chrome avec profil persistant (cookies de session conservés)
  2. Navigue vers amazon.fr → login si nécessaire (email/password, 2FA possible)
  3. Navigue vers /gc/spy/balance_v2_gcj (historique cartes cadeau)
  4. Scrape le tableau HTML des opérations
  5. Sauvegarde en CSV dans dropbox/AMAZON/

Fichiers générés:
  - dropbox/AMAZON/amazon_operations.csv (opérations scrapées)
"""

import sys
import csv
import time

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
BALANCE_URL_PATH = '/gp/css/gc/balance'


class AmazonFetcher(BaseFetcher):
    def __init__(self, verbose=False):
        super().__init__(
            caller_file=__file__,
            verbose=verbose,
        )

    # ========================================================================
    # LOGIN
    # ========================================================================

    def wait_for_login(self):
        """Navigue vers Amazon et gère le login si nécessaire.

        Returns:
            True si connecté, False si timeout
        """
        self.logger.info("Navigation vers Amazon...")
        self.page.goto(f"{self.base_url}/gp/css/homepage.html",
                       wait_until="domcontentloaded", timeout=30000)
        time.sleep(3)

        current_url = self.page.evaluate("window.location.href")
        self.logger.debug(f"URL après navigation: {current_url}")

        if self._is_logged_in(current_url):
            self.logger.info("Déjà connecté (session existante)")
            return True

        return self._do_login()

    def _is_logged_in(self, url=None):
        """Vérifie si on est sur une page authentifiée Amazon."""
        if url is None:
            url = self.page.evaluate("window.location.href")
        # Pages d'authentification → pas connecté
        if '/ap/signin' in url or '/ap/accountfixup' in url or '/ap/mfa' in url:
            return False
        # Toute page amazon.fr hors /ap/ = connecté
        if 'amazon.fr' in url and '/ap/' not in url:
            return True
        return False

    def _do_login(self, navigate=True):
        """Remplit le login Amazon et attend la connexion.

        Args:
            navigate: Si True, navigue vers la page d'accueil d'abord.
                      Si False, reste sur la page courante (ré-auth).

        Returns:
            True si connecté, False sinon
        """
        # Relancer en headed si nécessaire
        if not (self.debug or self._headed):
            self.relaunch_headed()
            navigate = True  # Après relance, il faut naviguer

        if navigate:
            self.page.goto(f"{self.base_url}/gp/css/homepage.html",
                           wait_until="domcontentloaded", timeout=30000)
            time.sleep(3)

        current_url = self.page.evaluate("window.location.href")
        if self._is_logged_in(current_url):
            self.logger.info("Session active après relance headed")
            return True

        # Remplir les credentials
        if not self._fill_login():
            self.logger.alert("CONNEXION REQUISE — Connecte-toi manuellement dans Chrome")

        return self._wait_for_authenticated()

    def _fill_login(self):
        """Remplit email + mot de passe Amazon (2 pages).

        Page 1: email → Continuer
        Page 2: mot de passe → Se connecter

        Returns:
            True si formulaire soumis, False sinon
        """
        username, password = self.load_gpg_credentials()
        if not username or not password:
            self.logger.warning("Credentials non trouvés — login manuel requis")
            return False

        try:
            # Page 1 : email
            email_input = self.page.locator(
                "input#ap_email, input[name='email'], input[type='email']"
            )
            email_input.first.wait_for(state="visible", timeout=15000)
            email_input.first.fill(username)
            self.logger.debug("Email rempli")
            time.sleep(0.5)

            # Bouton Continuer
            continue_btn = self.page.locator(
                "input#continue, span#continue, "
                "input[type='submit']:has-text('Continuer'), "
                "button:has-text('Continuer'), button:has-text('Continue')"
            )
            if continue_btn.count() > 0:
                continue_btn.first.click()
                self.logger.debug("Clic Continuer")
                time.sleep(2)

            # Page 2 : mot de passe
            pwd_input = self.page.locator(
                "input#ap_password, input[name='password'], input[type='password']"
            )
            pwd_input.first.wait_for(state="visible", timeout=10000)
            pwd_input.first.fill(password)
            self.logger.debug("Mot de passe rempli")
            time.sleep(0.5)

            # Bouton Se connecter
            login_btn = self.page.locator(
                "input#signInSubmit, "
                "input[type='submit'][value*='connecter'], "
                "input[type='submit'][value*='Connexion'], "
                "button:has-text('Se connecter'), button:has-text('Sign in')"
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
        """Attend la connexion (gère 2FA, accountfixup, etc).

        Returns:
            True si connecté, False si timeout
        """
        start_time = time.time()

        while time.time() - start_time < LOGIN_TIMEOUT_S:
            try:
                current_url = self.page.evaluate("window.location.href")
            except Exception:
                time.sleep(3)
                continue

            # Connecté ?
            if self._is_logged_in(current_url):
                self.logger.info("Connexion détectée")
                return True

            # Page "Protégez-vous" (ajout téléphone) → cliquer "Pas maintenant"
            if '/ap/accountfixup' in current_url:
                self._dismiss_accountfixup()

            time.sleep(3)

        self.logger.error(f"Timeout login ({LOGIN_TIMEOUT_S}s)")
        return False

    def _dismiss_accountfixup(self):
        """Ferme la page 'Protégez-vous des pirates' (ajout téléphone)."""
        try:
            skip_btn = self.page.locator(
                "a:has-text('Pas maintenant'), "
                "a:has-text('Not now'), "
                "a#ap-account-fixup-phone-skip-link, "
                "a[id*='skip']"
            )
            if skip_btn.count() > 0 and skip_btn.first.is_visible():
                skip_btn.first.click()
                self.logger.info("Page accountfixup ignorée (Pas maintenant)")
                time.sleep(2)
        except Exception as e:
            self.logger.debug(f"accountfixup: {e}")

    # ========================================================================
    # SCRAPING OPÉRATIONS
    # ========================================================================

    def fetch_operations(self):
        """Navigue vers la page solde carte cadeau et scrape le tableau.

        Returns:
            Path du CSV ou None
        """
        self.logger.info("Navigation vers historique carte cadeau...")
        self.page.goto(f"{self.base_url}{BALANCE_URL_PATH}",
                       wait_until="domcontentloaded", timeout=30000)
        time.sleep(3)

        current_url = self.page.evaluate("window.location.href")
        if '/ap/signin' in current_url or '/ap/accountfixup' in current_url:
            # Amazon demande une ré-authentification pour les pages sensibles
            self.logger.info("Ré-authentification requise pour la page carte cadeau")
            if not self._do_login(navigate=False):
                self.logger.error("Échec ré-authentification")
                return None
            # Re-naviguer vers la page carte cadeau
            self.page.goto(f"{self.base_url}{BALANCE_URL_PATH}",
                           wait_until="domcontentloaded", timeout=30000)
            time.sleep(3)

        # Extraire le solde
        balance = self._extract_balance()
        if balance is not None:
            self.logger.info(f"Solde carte cadeau: {balance} €")

        # Charger toutes les pages du tableau (pagination)
        self._load_all_pages()

        # Scraper le tableau
        operations = self._scrape_table()
        if not operations:
            self.logger.warning("Aucune opération trouvée dans le tableau")

        # Sauvegarder en CSV
        return self._save_csv(operations, balance)

    def _extract_balance(self):
        """Extrait le solde affiché sur la page.

        Returns:
            str du solde ou None
        """
        try:
            # Chercher le texte du solde via JavaScript
            balance_text = self.page.evaluate("""
                () => {
                    // Chercher "Solde" dans le texte de la page
                    const els = document.querySelectorAll('*');
                    for (const el of els) {
                        if (el.children.length === 0 || el.tagName === 'SPAN' || el.tagName === 'H2') {
                            const t = el.textContent || '';
                            if (t.includes('Solde') && t.includes('€')) {
                                return t.trim();
                            }
                        }
                    }
                    return null;
                }
            """)
            if balance_text:
                import re
                match = re.search(r'([\d\s]+[,.]?\d*)\s*€', balance_text)
                if match:
                    return match.group(1).strip()
        except Exception as e:
            self.logger.debug(f"Extraction solde: {e}")
        return None

    def _load_all_pages(self):
        """Clique sur 'Suivant' / 'Précédent' pour charger toutes les pages."""
        # D'abord, naviguer vers la première page si nécessaire
        # Puis charger toutes les pages en cliquant 'Suivant'
        max_pages = 20
        for _ in range(max_pages):
            next_btn = self.page.locator(
                "a:has-text('Suivant'), a:has-text('Next'), "
                "button:has-text('Suivant'), button:has-text('Next')"
            )
            try:
                if next_btn.count() > 0 and next_btn.first.is_visible():
                    next_btn.first.click()
                    self.logger.debug("Page suivante chargée")
                    time.sleep(2)
                else:
                    break
            except Exception:
                break

    def _scrape_table(self):
        """Scrape le tableau des opérations depuis le HTML.

        Returns:
            Liste de dicts {date, description, montant, solde}
        """
        operations = []

        # Le tableau est dans la page avec des lignes d'opérations
        # Essayer de trouver le tableau par JavaScript pour robustesse
        rows_data = self.page.evaluate("""
            () => {
                const results = [];
                // Chercher toutes les lignes du tableau d'opérations
                const tables = document.querySelectorAll('table');
                for (const table of tables) {
                    const rows = table.querySelectorAll('tr');
                    for (const row of rows) {
                        const cells = row.querySelectorAll('td');
                        if (cells.length >= 3) {
                            results.push({
                                cells: Array.from(cells).map(c => c.textContent.trim())
                            });
                        }
                    }
                }
                return results;
            }
        """)

        for row in rows_data:
            cells = row.get('cells', [])
            if len(cells) >= 3:
                operations.append({
                    'date': cells[0],
                    'description': cells[1],
                    'montant': cells[2] if len(cells) > 2 else '',
                    'solde': cells[3] if len(cells) > 3 else '',
                })

        self.logger.info(f"Opérations scrapées: {len(operations)}")
        return operations

    def _save_csv(self, operations, balance):
        """Sauvegarde les opérations en CSV.

        Args:
            operations: Liste de dicts
            balance: Solde courant (str) ou None

        Returns:
            Path du CSV ou None
        """
        self.dropbox_dir.mkdir(parents=True, exist_ok=True)
        csv_path = self.dropbox_dir / 'amazon_operations.csv'

        with open(csv_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f, delimiter=';')
            writer.writerow(['Date', 'Description', 'Montant', 'Solde'])
            for op in operations:
                writer.writerow([
                    op['date'],
                    op['description'],
                    op['montant'],
                    op['solde'],
                ])
            # Ajouter le solde en dernière ligne si disponible
            if balance is not None:
                writer.writerow(['', '#SOLDE', balance, ''])

        file_size = csv_path.stat().st_size / 1024
        self.logger.info(f"CSV sauvegardé: {csv_path.name} ({file_size:.1f} Ko)")
        self.downloads.append(csv_path)
        return csv_path

    # ========================================================================
    # WORKFLOW PRINCIPAL
    # ========================================================================

    def run(self):
        """Execute le workflow de fetch Amazon.

        Returns:
            True si succès, False sinon
        """
        # 1. Login
        if not self.wait_for_login():
            self.logger.error("Échec de la connexion")
            return False

        # 2. Scraper les opérations
        csv_path = self.fetch_operations()

        if not csv_path:
            self.logger.error("Aucun fichier récupéré")
            return False

        # 3. Résumé
        self.logger.info(f"Collecte {self.site_name} terminée ({len(self.downloads)} fichier(s))")
        for dl in self.downloads:
            self.logger.info(f"  {dl.name}")
        return True


if __name__ == '__main__':
    sys.exit(fetch_main(AmazonFetcher, description='Fetch Amazon gift card history via Playwright'))
