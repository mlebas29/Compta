#!/usr/bin/env python3
"""
cpt_fetch_WISE.py - Collecte Wise via Playwright (semi-automatique)

Login semi-automatique : Chrome remplit les identifiants via GPG.
Wise demande systématiquement une approbation par notification push dans
l'appli Wise (« Oui, c'est moi ») ; selon le contexte (typiquement
changement d'appareil), une vérification email peut s'y ajouter — copier
le lien reçu (clic droit → Copier le lien), le clipboard est surveillé
et le lien est ouvert dans un nouvel onglet. Le script exporte ensuite
l'historique et lit les soldes.

Depuis #131, l'assistant relevé XLSX (devenu inaccessible côté Wise) est
remplacé par l'export CSV « all-transactions » (1 clic) que le format
décompose en jambes par devise, plus une lecture des soldes courants.

Prérequis:
- pip install playwright
- playwright install chrome

Usage:
  ./cpt_fetch_WISE.py         # Mode normal
  ./cpt_fetch_WISE.py -v      # Mode verbeux (dump du DOM aux étapes clés)

Workflow:
  1. Lance Chrome avec profil persistant (cookies de session conservés)
  2. Login si nécessaire : email/password (GPG) + validation push mobile
     puis (si demandée) lien email Wise copié dans le clipboard
  3. /all-transactions → bouton « Télécharger » → tiroir → format CSV → download
  4. Soldes : /home → id du groupe multi-devises → /groups/<id> → lecture des
     jars par devise (« Compte principal »)

Fichiers générés (dropbox/WISE/):
  - transaction-history.csv  (toutes les opérations, toutes devises)
  - wise_balances.csv        (solde courant par devise, pour le #Solde)
"""

import sys
import os
import time
import subprocess
import pyperclip
from datetime import datetime, timedelta

try:
    from playwright.sync_api import TimeoutError as PlaywrightTimeout
except ImportError:
    print("Module 'playwright' manquant. Installez avec: pip install playwright && playwright install chrome", file=sys.stderr)
    sys.exit(1)

from inc_fetch import BaseFetcher, fetch_main, config


# ============================================================================
# DESCRIPTION (consommée par la GUI onglet Sites)
# ============================================================================

DESCRIPTION = """Wise — comptes paiements multi-devises.

══════ Configuration ══════

N comptes (1 par devise).

══════ 2FA ══════

Systématique, via App mobile (notification push à approuver).
Occasionnellement complété par un 2nd 2FA email (typiquement nouvel appareil) : clic droit sur le bouton d'approbation dans le mail → copier le lien. Le script surveille le clipboard et fait le reste.

Procédure :
1. Le script lance Chrome
2. L'alerte « VALIDATION MOBILE » s'affiche dans le terminal
3. Approuver la connexion dans l'appli Wise mobile ("Oui, c'est moi")
4. Si l'alerte « VÉRIFICATION EMAIL » apparaît ensuite : copier le lien du mail Wise (clic droit → Copier le lien)
5. Le script détecte la connexion et poursuit la collecte

══════ Collecte manuelle de secours ══════

1. Opérations
   wise.com/all-transactions → Télécharger → format CSV → Télécharger
   → dropbox/WISE/ (le format le décompose en jambes par devise)

2. Intérêts comptes rémunérés (annuel, début d'année)
   wise.com/balances/.../holding-money → Année précédente
   → Reporter manuellement dans Excel
   → dropbox/WISE/"""


# ============================================================================
# CONFIGURATION
# ============================================================================

# Timeouts
LOGIN_TIMEOUT_S = 300       # 5 min pour login + 2FA (push mobile + email éventuel)
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
        """Workflow : login → export « all-transactions » (CSV) → soldes (#Solde).

        #131 : l'assistant relevé XLSX (devenu inaccessible) est remplacé par
        l'export CSV « all-transactions » (1 clic) que le format décompose en
        jambes, plus une lecture des soldes courants pour le #Solde par devise.
        (Le fetch assistant create_statement/download_statement a été retiré ;
        le format garde son chemin de lecture XLSX pour le TNR pipe.)

        Returns:
            True if successful, False otherwise
        """
        try:
            # 1. Login (interactif si nécessaire)
            self.step("Login")
            if not self.wait_for_login():
                self.logger.error("Échec de la connexion")
                return False

            # 2. Exporter l'historique complet (CSV all-transactions)
            self.step("Opérations")
            csv_path = self.export_all_transactions()
            if not csv_path:
                self.logger.error("Échec export all-transactions")
                return False

            # 3. Soldes par devise → #Solde (best-effort : les opérations priment ;
            #    sans soldes, les comptes Wise seront auto-calculés à l'import).
            self.step("Soldes")
            try:
                self.fetch_balances()
            except Exception as e:
                self.logger.warning(f"Soldes non collectés (comptes auto-calculés): {e}")

            # 4. Résumé
            self.logger.info("=" * 50)
            self.logger.info(f"Fichier:     {csv_path.name}")
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

    def export_all_transactions(self):
        """Exporte l'historique complet en CSV depuis wise.com/all-transactions.

        Remplace l'assistant relevé XLSX (#131) : la page « Toutes les
        transactions » offre un export en ~1 clic (bouton « Télécharger » → tiroir
        → format CSV → action). Validé live s.194 ; dump (logs/debug/) à chaque échec.

        Returns:
            Path du CSV téléchargé ou None
        """
        url = f"{self.base_url}/all-transactions"
        self.logger.info(f"Navigation vers {url}")
        self.page.goto(url, wait_until="domcontentloaded")
        time.sleep(3)
        self.dismiss_cookies()
        # Dump du DOM à l'arrivée (--verbose) : capture la page au moment décisif
        # pour caler/maintenir les sélecteurs (les dumps d'échec ne suffisent pas
        # si un sélecteur « marche à moitié »). Cf. maintenance-sélecteurs #131.
        self._dump_page_debug('all_transactions_landing', force=self.verbose)

        # 1. Ouvrir le tiroir de téléchargement (bouton « Télécharger », icône ↓).
        dl_btn = self.page.locator(
            "button[aria-label='Télécharger'], button[aria-label='Download']")
        try:
            dl_btn.first.wait_for(state="visible", timeout=15000)
        except PlaywrightTimeout:
            self.logger.error("Bouton 'Télécharger' introuvable sur all-transactions")
            self._dump_page_debug("no_export_btn", force=True)
            return None
        dl_btn.first.click()
        self.logger.info("Tiroir de téléchargement ouvert")
        time.sleep(2)
        # Le tiroir (« Format du fichier ») est rendu au clic → dump pour caler le
        # sélecteur de format + le bouton d'action (inconnus hors collecte réelle).
        self._dump_page_debug("download_drawer", force=self.verbose)

        # 2. Choisir le format CSV dans le tiroir (best-effort, multi-stratégies).
        if not self._choose_csv_format():
            self.logger.warning("Format CSV non sélectionné — voir dump download_drawer")

        # 3. Déclencher l'action « Télécharger » du tiroir + capturer le download.
        #    Deux boutons portent « Télécharger » (en-tête + action du tiroir) → on
        #    prend le DERNIER (action du tiroir, ajoutée en fin de DOM).
        self.dropbox_dir.mkdir(parents=True, exist_ok=True)
        dest_path = self.dropbox_dir / 'transaction-history.csv'
        action = self.page.locator(
            "button[aria-label='Télécharger'], button:has-text('Télécharger'), "
            "button:has-text('Download')")
        try:
            with self.page.expect_download(timeout=DOWNLOAD_TIMEOUT_S * 1000) as dl_info:
                action.last.click()
            dl_info.value.save_as(str(dest_path))
        except PlaywrightTimeout:
            self.logger.error("Téléchargement CSV non déclenché (timeout)")
            self._dump_page_debug("no_csv_download", force=True)
            return None
        except Exception as e:
            self.logger.error(f"Erreur téléchargement CSV: {e}")
            self._dump_page_debug("csv_download_error", force=True)
            return None

        # Garde-fou anti-HTML (#137) : refuser une page servie au lieu du CSV
        if not self.reject_saved_if_html(dest_path, 'all-transactions'):
            self._dump_page_debug("csv_is_html", force=True)
            return None

        self.logger.info(f"Téléchargé: {dest_path.name}")
        self.download_path = dest_path
        self.downloads.append(dest_path)
        return dest_path

    def _choose_csv_format(self):
        """Sélectionne le format CSV dans le tiroir « Format du fichier »
        (best-effort — sélecteurs exacts à confirmer sur le dump download_drawer).

        Returns:
            True si une stratégie a effectivement choisi CSV, False sinon.
        """
        # a) <select> natif (par libellé puis par valeur, casse haute/basse)
        sel = self.page.locator("select")
        if sel.count() > 0:
            for kwargs in ({'label': 'CSV'}, {'value': 'CSV'}, {'value': 'csv'}):
                try:
                    sel.first.select_option(**kwargs)
                    self.logger.info("Format CSV sélectionné (select natif)")
                    return True
                except Exception:
                    pass
        # b) radio / option / libellé cliquable « CSV »
        csv_opt = self.page.locator(
            "input[value='CSV'], input[value='csv'], label:has-text('CSV'), "
            "[role='option']:has-text('CSV'), [role='radio']:has-text('CSV'), "
            "button:has-text('CSV')")
        if csv_opt.count() > 0:
            try:
                csv_opt.first.click()
                self.logger.info("Format CSV sélectionné (option)")
                return True
            except Exception:
                pass
        # c) composant custom : ouvrir le combobox puis choisir CSV
        combo = self.page.locator("[role='combobox'], [class*='Select']")
        if combo.count() > 0:
            try:
                combo.first.click()
                time.sleep(0.5)
                opt = self.page.locator("[role='option']:has-text('CSV'), li:has-text('CSV')")
                if opt.count() > 0:
                    opt.first.click()
                    self.logger.info("Format CSV sélectionné (combobox)")
                    return True
            except Exception:
                pass
        return False

    def fetch_balances(self):
        """Lit les soldes par devise -> dropbox/WISE/wise_balances.csv (« DEVISE,
        solde » par ligne), consomme par le format pour le #Solde (#131, choix b).

        Les 5 jars (EUR inclus) sont sur la page du GROUPE multi-devises
        (« Compte principal »), pas sur /home : /home affiche l'EUR comme
        devise de BASE (non-jar), d'un montant sans rapport avec le vrai jar
        EUR -> le lire la fausserait ; d'ou le passage par la page groupe.
        On extrait l'id du groupe depuis /home (« MCA - <id> ») -> /groups/<id>,
        puis on lit chaque jar dans les spans `np-option__title` (« <montant> <ISO> »).
        NB : /balances = 404. Id extrait dynamiquement (portable, pas de hardcode).
        Nav pure `goto` : pas de wait_for_load_state('networkidle') (la SPA ne
        devient jamais idle -> timeout inutile) ; on attend juste la condition ciblee.
        """
        # 1. /home -> id du groupe multi-devises
        self.page.goto(f"{self.base_url}/home", wait_until="domcontentloaded")
        try:
            self.page.wait_for_function(
                "() => /MCA\\s*-\\s*\\d+|multi-currency-account/"
                ".test(document.documentElement.innerHTML)",
                timeout=12000)
        except PlaywrightTimeout:
            self.logger.warning("/home lent - id groupe peut-etre absent")
        group_id = self.page.evaluate(r"""
            () => {
                const h = document.documentElement.innerHTML;
                let m = h.match(/multi-currency-account[":\s]+(\d+)/)
                     || h.match(/MCA\s*-\s*(\d+)/)
                     || h.match(/\/groups\/(\d+)/);
                return m ? m[1] : null;
            }
        """)
        if not group_id:
            self.logger.warning("Id du groupe multi-devises introuvable sur /home")
            self._dump_page_debug("no_group_id", force=True)
            return
        self.logger.info(f"Groupe multi-devises: {group_id}")

        # 2. /groups/<id> -> les 5 jars
        url = f"{self.base_url}/groups/{group_id}"
        self.logger.info(f"Lecture des soldes: {url}")
        self.page.goto(url, wait_until="domcontentloaded")
        try:
            self.page.wait_for_function(
                "() => !!document.querySelector('.np-option__title, [class*=\"option__title\"]')",
                timeout=12000)
        except PlaywrightTimeout:
            self.logger.warning("Cartes de solde non apparues (page lente ?)")
        self.dismiss_cookies()
        self._dump_page_debug("balances_group", force=self.verbose)

        # Chaque jar = un span de titre d'option « <montant> <ISO> » (les codes
        # ISO sont dans le texte visible sur la page groupe ; les transactions,
        # elles, ne portent pas cette classe -> pas de pollution).
        pairs = self.page.evaluate(r"""
            () => {
                const out = [];
                document.querySelectorAll('.np-option__title, [class*="option__title"]').forEach(el => {
                    const t = (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim();
                    const m = t.match(/^([0-9][0-9\s.,]*?)\s*([A-Z]{3})$/);
                    if (m) out.push([m[2], m[1]]);
                });
                return out;
            }
        """)
        seen = {}
        for cur, amt in (pairs or []):
            cur = (cur or '').strip().upper()
            if len(cur) == 3 and cur.isalpha() and amt:
                seen[cur] = amt  # dernier gagne
        if not seen:
            self._dump_page_debug("no_balances", force=True)
            self.logger.warning("Aucun solde lu sur le groupe - voir dump")
            return

        def _norm(a):
            # « 19 437,07 » -> « 19437.07 » : retirer les espaces (dont fines/nbsp)
            # puis virgule decimale -> point, sinon collision avec la virgule
            # separateur de wise_balances.csv (CHF,19 437,07 = 3 champs !).
            a = ''.join(ch for ch in a if not ch.isspace())
            if ',' in a and '.' not in a:
                a = a.replace(',', '.')
            return a
        out = self.dropbox_dir / 'wise_balances.csv'
        with open(out, 'w', encoding='utf-8') as f:
            for cur, amt in seen.items():
                f.write(f"{cur},{_norm(amt)}\n")
        self.downloads.append(out)
        self.logger.info(f"Soldes ecrits: {out.name} ({len(seen)} devises: {','.join(seen)})")

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
        sur la page des relevés. Sinon, on remplit le login et on attend
        la 2FA (push mobile systématique, lien email parfois en complément).

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
        """Lit le contenu du clipboard (cross-platform via pyperclip).

        Returns:
            str: contenu du clipboard, ou '' si erreur
        """
        try:
            return pyperclip.paste().strip()
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
            pyperclip.copy('')
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
                self.logger.user_done()
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
                        self.logger.user_done()  # #150 chemin nouvel onglet : clore l'attente 2FA
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
        """Passe en headed et attend la validation manuelle (push mobile + email éventuel, login...)."""
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


if __name__ == '__main__':
    sys.exit(fetch_main(WiseFetcher, description='Fetch Wise statements via Playwright (semi-automatique)'))
