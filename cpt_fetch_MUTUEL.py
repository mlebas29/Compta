#!/usr/bin/env python3
"""cpt_fetch_MUTUEL.py — collecte Crédit Mutuel via Playwright.

Login semi-automatique : Chrome remplit identifiant/mot de passe via GPG,
le titulaire valide le 2FA sur l'app mobile (systématique → coordination
nécessaire), puis le script télécharge l'export Excel multi-comptes depuis la
page « Téléchargement ».

Prérequis :
- pip install playwright ; playwright install chrome
- credential `credential_id` (config.ini [MUTUEL]) dans le fichier GPG

Usage :
  ./cpt_fetch_MUTUEL.py        # collecte (headless ; 2FA validé au téléphone)
  ./cpt_fetch_MUTUEL.py -v     # verbeux

⚠️ SÉLECTEURS À CONFIRMER EN LIVE — les constantes `SEL_*` / `*_HINT` ci-dessous
sont des hypothèses (DOM réel CM non observé). À ajuster lors d'une session avec
le titulaire. Le login est **semi-auto headless** (2FA validé côté téléphone) ;
si l'auto-login échoue, un repli bascule en **fenêtre visible** (login manuel).
"""

import sys
import time

try:
    from playwright.sync_api import TimeoutError as PlaywrightTimeout
except ImportError:
    print("Module 'playwright' manquant. Installez : pip install playwright && playwright install chrome",
          file=sys.stderr)
    sys.exit(1)

from inc_fetch import BaseFetcher, fetch_main, DEBUG


# ============================================================================
# DESCRIPTION (consommée par la GUI onglet Sites)
# ============================================================================

DESCRIPTION = """Crédit Mutuel — banque (comptes courants, livrets, prêts).

══════ Configuration ══════

Un seul export Excel multi-comptes (tous_comptes.xlsx) couvrant tous les
comptes visibles. Déclarer chaque compte avec son RIB dans l'onglet Comptes
(le RIB sert de clé de rapprochement avec les onglets de l'export).

══════ 2FA ══════

Systématique, à chaque connexion : validation sur l'app mobile Crédit Mutuel
(côté téléphone → pas de fenêtre en régime normal). Se coordonner avec le
titulaire. Une fenêtre ne s'ouvre qu'en secours, pour un login manuel.
"""


# ============================================================================
# Sélecteurs / repères — À CONFIRMER en session live (DOM réel CM)
# ============================================================================

# Page de login DIRECTE (évite la home + la popin géoloc régionale) et page de
# téléchargement. telechargement.cgi redirige vers la 1ʳᵉ si non authentifié.
LOGIN_URL = 'https://www.creditmutuel.fr/fr/authentification.html'
DOWNLOAD_URL = 'https://www.creditmutuel.fr/fr/banque/compte/telechargement.cgi'

# Login : champs identifiant / mot de passe (DOM CM réel confirmé).
SEL_USERNAME = "#_userid"
SEL_PASSWORD = "#_pwduser"

# Page Téléchargement : la PRÉSÉLECTION est mémorisée côté CM (« Conserver mes choix
# pour mes prochains téléchargements » : format Excel + tous les comptes + tout
# l'historique) → en pratique il n'y a qu'à actionner le bouton « Téléchargez ».
TXT_TELECHARGER = 'Téléchargez'
# Labels du formulaire complet (cf. captures), SI un jour la présélection est perdue
# (à rejouer alors avant le bouton) : à confirmer via le dump HTML DEBUG.  # TODO[live]
TXT_FORMAT_EXCEL = 'Excel'
TXT_TOUT_COCHER = 'Tout cocher'
TXT_TOUTES_OPS = 'Téléchargez toutes les opérations disponibles'

# Nom du fichier déposé (matche EXPECTED_FILES de cpt_format_MUTUEL)
OUTPUT_FILENAME = 'tous_comptes.xlsx'

LOGIN_TIMEOUT_S = 180   # marge pour la validation 2FA humaine
DOWNLOAD_TIMEOUT_S = 60


class MutuelFetcher(BaseFetcher):
    def __init__(self, verbose=False):
        # Headless par défaut (comme la flotte) : le 2FA CM est validé côté
        # TÉLÉPHONE (`_wait_for_authenticated` ne fait que poller) → aucune fenêtre
        # requise en régime normal. Le repli login-manuel bascule en fenêtre
        # visible via prompt_manual_login (relaunch_headed).
        super().__init__(caller_file=__file__, verbose=verbose)

    # ---- Étapes ------------------------------------------------------------

    def _fill_login(self):
        """Remplit identifiant/mot de passe via GPG. False si creds indispo
        ou champs introuvables (→ login manuel)."""
        username, password = self.load_gpg_credentials()
        if not username or not password:
            self.logger.warning("Identifiants GPG indisponibles → login manuel requis")
            return False
        try:
            self.page.fill(SEL_USERNAME, username, timeout=15000)
            self.page.fill(SEL_PASSWORD, password)
            self.page.locator(SEL_PASSWORD).press("Enter")   # soumet le formulaire
            self.logger.info("Identifiants soumis")
            return True
        except Exception as e:
            self.logger.warning(f"Remplissage login échoué ({e}) → login manuel requis")
            return False

    def _authenticated(self):
        """True = lien « Déconnexion » présent ET on n'est PAS sur la page d'auth
        forte. Le lien Déconnexion (#ei_tpl_ident_logout_title / …/deconnexion.cgi)
        existe aussi sur validation.aspx (2FA), d'où un faux positif si on s'y fie
        seul ; on l'écarte donc tant que subsiste le marqueur 2FA : bouton
        `_FID_DoValidate` (« Confirmer l'authentification forte ») ou titre idoine."""
        try:
            page = self.page
            on_2fa = (
                page.locator("input[name*='DoValidate']").count() > 0
                or 'authentification forte' in (page.title() or '').lower()
            )
            if on_2fa:
                return False
            return page.locator("a[href*='deconnexion.cgi']").count() > 0
        except Exception:
            return False

    def _wait_for_authenticated(self):
        """Attend la fin du login + 2FA (humain). True si authentifié.

        Logge chaque CHANGEMENT d'URL (capture du flux réel) et dumpe au timeout.
        """
        self.logger.alert("VALIDE LE 2FA sur l'app mobile Crédit Mutuel "
                          f"(jusqu'à {LOGIN_TIMEOUT_S}s)…")
        deadline = time.monotonic() + LOGIN_TIMEOUT_S
        last_url = None
        while time.monotonic() < deadline:
            url = self.page.url
            if url != last_url:
                self.logger.info(f"URL : {url}")   # capture du flux d'auth réel
                last_url = url
            if self._authenticated():
                self.logger.user_done()   # succès login → clôt le chrono d'attente humaine (#147)
                self.logger.info("Authentifié")
                return True
            time.sleep(2)
        self.logger.error(f"Délai 2FA dépassé (dernière URL : {self.page.url})")
        self._dump_page_debug('auth_timeout', force=True)
        return False

    def _download_export(self):
        """Page Téléchargement : la présélection (Excel + tous comptes + tout
        l'historique) étant mémorisée côté CM, il suffit d'actionner « Téléchargez ».
        """
        self.logger.info("Téléchargement de l'export multi-comptes…")
        try:
            self.page.goto(DOWNLOAD_URL, wait_until="domcontentloaded")
            time.sleep(2)
            self._dismiss_cookies()
            # Capture la page (HTML + screenshot) pour affiner les sélecteurs au besoin.
            self._dump_page_debug('download_page', force=True)

            dest_path = self.dropbox_dir / OUTPUT_FILENAME
            self.dropbox_dir.mkdir(parents=True, exist_ok=True)
            # Bouton « Téléchargez » : CM = <input type=submit> ou <a class="ei_btn">
            # (pas un <button>). Présélection déjà appliquée. TODO[live] : si la
            # présélection est perdue, re-sélectionner via TXT_FORMAT_EXCEL /
            # TXT_TOUT_COCHER / TXT_TOUTES_OPS avant ce clic.
            # Bouton « Télécharger » : avec JS c'est l'<a class="ei_btn_typ_download
            # needscript"> (l'<input name=_FID_DoDownload> est masqué par hideifscript).
            btn = self.page.locator(
                "a.ei_btn_typ_download, "
                "a.ei_btn:has-text('Télécharger'), "
                "input[name='_FID_DoDownload']"
            )
            with self.page.expect_download(timeout=DOWNLOAD_TIMEOUT_S * 1000) as dl_info:
                btn.first.click()
            download = dl_info.value
            if dest_path.exists():
                dest_path.unlink()
            download.save_as(str(dest_path))
            # Garde #137 : CM peut servir une page login/redirect en HTTP 200 si la
            # session a expiré en cours de flux → refuser un « export » qui est en
            # réalité du HTML (sinon le format plante plus tard sur un KeyError obscur).
            if not self.reject_saved_if_html(dest_path, 'export multi-comptes'):
                return None
            self.logger.info(f"Téléchargé : {dest_path.name} → {self.dropbox_dir}")
            self.downloads.append(dest_path)
            return dest_path
        except PlaywrightTimeout:
            self.logger.error("Timeout téléchargement — présélection perdue ? cf. dump")
            self._dump_page_debug('download_fail', force=True)
            return None
        except Exception as e:
            self.logger.error(f"Erreur téléchargement : {e}")
            self._dump_page_debug('download_fail', force=True)
            return None

    def _dismiss_cookies(self):
        """Ferme la bannière cookies CM (best-effort, page + iframes)."""
        # Bannière CM = maison (boutons <a>) : a.ei_btn_typ_validate = « Accepter »,
        # a.ei_lb_btnskip = « Continuer sans accepter ». + fallbacks génériques.
        selectors = (
            "a.ei_btn_typ_validate, "
            "a.ei_lb_btnskip, "
            "a:has-text('Accepter'), "
            "a:has-text('Continuer sans accepter'), "
            "button:has-text('Tout accepter'), "
            "button:has-text(\"J'accepte\"), "
            "button:has-text('Accepter')"
        )
        try:
            btn = self.page.locator(selectors)
            btn.first.wait_for(state="visible", timeout=3000)
            btn.first.click()
            self.logger.info("Cookies acceptés")
            time.sleep(1)
            return
        except Exception:
            pass
        try:
            for frame in self.page.frames:
                if frame == self.page.main_frame:
                    continue
                btn = frame.locator(selectors)
                if btn.count() > 0:
                    btn.first.click(force=True)
                    self.logger.info("Cookies acceptés (iframe)")
                    time.sleep(1)
                    return
        except Exception:
            pass
        self.logger.debug("Pas de bannière cookies")

    def _dismiss_popups(self):
        """Ferme un éventuel popup post-login (messagerie/notifications), best-effort.

        Sélecteurs génériques — à CALER sur le vrai DOM via le dump post_login.html.
        """
        # Modal messagerie CM post-login : bouton « Fermer » = a.ei_btn_typ_cancel
        # avec onclick ActionAfterPopupWithLastMail(false,…). + fallbacks génériques.
        selectors = (
            "a.ei_btn_typ_cancel[onclick*='ActionAfterPopupWithLastMail'], "
            "a[onclick*='ActionAfterPopupWithLastMail'], "
            ".ei_blocmodal a.ei_btn_typ_cancel, "
            "button[aria-label*='ermer'], a[aria-label*='ermer'], "
            ".ei_lb_close, button:has-text('Fermer'), a:has-text('Fermer')"
        )
        try:
            btn = self.page.locator(selectors)
            if btn.count() > 0 and btn.first.is_visible():
                btn.first.click()
                self.logger.info("Popup post-login fermé")
                time.sleep(1)
        except Exception:
            self.logger.debug("Pas de popup post-login (ou sélecteur à affiner)")

    # ---- Orchestration -----------------------------------------------------

    def run(self):
        """Login (semi-auto + 2FA) puis téléchargement de l'export."""
        self.step("Login")
        self.logger.info(f"Navigation vers la page de login {LOGIN_URL}…")
        self.page.goto(LOGIN_URL, wait_until="domcontentloaded")
        time.sleep(2)
        self._dismiss_cookies()   # bannière cookies bloque sinon les clics

        # Déjà connecté (session persistante) ?
        if self._authenticated():
            self.logger.info("Déjà connecté (session existante)")
        elif self._fill_login():
            # Auto-login OK → attendre le 2FA (validé côté téléphone → headless OK).
            if not self._wait_for_authenticated():
                return False
        else:
            # Auto-login impossible (identifiants absents, sélecteur cassé) → bascule
            # en fenêtre VISIBLE pour un login manuel. prompt_manual_login (filet
            # partagé de la flotte) dumpe auto_login_fail (#149/B1) puis relaunch_headed.
            if not self.prompt_manual_login(LOGIN_URL, self._authenticated,
                                            timeout_s=LOGIN_TIMEOUT_S):
                return False

        time.sleep(2)
        self._dump_page_debug('post_login', force=True)   # capture le popup messagerie
        self._dismiss_popups()
        self.step("Opérations")
        export = self._download_export()
        if not export:
            self.logger.error("Aucun fichier téléchargé")
            return False
        self.logger.info(f"Collecte {self.site_name} terminée (1 fichier)")
        return True


if __name__ == '__main__':
    sys.exit(fetch_main(MutuelFetcher, description='Fetch Crédit Mutuel'))
