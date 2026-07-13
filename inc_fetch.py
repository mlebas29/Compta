"""
inc_fetch.py - Classe de base pour les scripts fetch Playwright

Factorise le boilerplate commun : configuration, launch/close browser,
impression PDF via CDP, et main() standard.

Usage dans un script fetch :

    import sys
    from inc_fetch import BaseFetcher, fetch_main

    class MonFetcher(BaseFetcher):
        def __init__(self, verbose=False):
            super().__init__('SECTION', 'cpt_MON_fetch', verbose=verbose)

        def run(self):
            # ... logique métier ...
            return True  # succès

    if __name__ == '__main__':
        sys.exit(fetch_main(MonFetcher))
"""

import sys
import time
import re
import argparse
import base64
import configparser
from contextlib import contextmanager
from pathlib import Path

import inc_config_init  # noqa: F401  — auto-création des fichiers config user manquants
import inc_mode
from inc_logging import Logger

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("Module 'playwright' manquant. Installez avec: pip install playwright && playwright install chrome", file=sys.stderr)
    sys.exit(1)

try:
    from inc_gpg_credentials import get_credentials_from_gpg
except ImportError:
    get_credentials_from_gpg = None

# ============================================================================
# CONFIGURATION GLOBALE
# ============================================================================

BASE_DIR = inc_mode.get_base_dir()
COMPTA_MODE = inc_mode.get_mode()
CONFIG_FILE = BASE_DIR / 'config.ini'

config = configparser.ConfigParser()
config.read(CONFIG_FILE)

DEBUG = config.getboolean('general', 'DEBUG', fallback=False)
# Couche d'investigation (s.202) : snapshot DOM au début de chaque step() du
# profil → toujours le dernier run de chaque site/étape sous la main, borné
# (écrasé par run). off | dom (HTML seul, quasi gratuit) | full (+ PNG, coûteux).
DUMP_STEPS = config.get('general', 'dump_steps', fallback='dom').strip().lower()
LOGS_DIR = BASE_DIR / config.get('paths', 'logs', fallback='./logs')
JOURNAL_FILE = LOGS_DIR / 'journal.log'

DEFAULT_VIEWPORT = {"width": 1280, "height": 900}


def tesseract_install_hint():
    """Message d'erreur explicite OS-aware quand tesseract (OCR) est absent.

    Linux : paquet apt nommé 'tesseract-ocr', binaire 'tesseract'.
    macOS : paquet et binaire 'tesseract'. Sur Ventura : MacPorts requis
    (cf. CLAUDE_mac.md § LibreOffice Mac — bottle Homebrew Ventura inexistant).
    Sur Sonoma+ : brew probable.
    """
    if sys.platform == 'darwin':
        return ("OCR non disponible.\n"
                "  → Mac Ventura : sudo /opt/local/bin/port install tesseract tesseract-eng tesseract-fra (MacPorts)\n"
                "  → Mac Sonoma+ : brew install tesseract (à confirmer)\n"
                "  → puis : pip install pytesseract pillow")
    if sys.platform.startswith('linux'):
        return ("OCR non disponible.\n"
                "  → sudo apt install tesseract-ocr tesseract-ocr-fra\n"
                "  → pip install pytesseract pillow")
    return ("OCR non disponible.\n"
            "  → installer tesseract (cf. https://tesseract-ocr.github.io/)\n"
            "  → pip install pytesseract pillow")


def ensure_tesseract_cmd():
    """Configure `pytesseract.pytesseract.tesseract_cmd` en cherchant
    le binaire tesseract dans le PATH, puis dans les emplacements
    standards par OS si absent.

    Indispensable Mac : selon que le fetcher est lancé depuis le launcher
    .app (PATH étendu avec /opt/local/bin) ou depuis Terminal (PATH du
    shell utilisateur, qui peut ne pas inclure MacPorts/Homebrew),
    `pytesseract` peut spawner `tesseract` via PATH et ne pas le trouver.

    Retourne True si tesseract configuré, False sinon (auquel cas le
    caller devrait appeler `tesseract_install_hint()` et abandonner).
    """
    import shutil
    try:
        import pytesseract
    except ImportError:
        return False

    # 1. PATH du process courant (cas Linux apt, ou Mac launcher étendu)
    path = shutil.which('tesseract')
    if path:
        pytesseract.pytesseract.tesseract_cmd = path
        return True

    # 2. Emplacements standards OS (fallback CLI Mac sans PATH étendu)
    candidates = []
    if sys.platform == 'darwin':
        candidates = [
            '/opt/local/bin/tesseract',     # MacPorts (Ventura)
            '/opt/homebrew/bin/tesseract',  # Homebrew Apple Silicon
            '/usr/local/bin/tesseract',     # Homebrew Intel
        ]
    elif sys.platform.startswith('linux'):
        candidates = ['/usr/bin/tesseract', '/usr/local/bin/tesseract']

    for c in candidates:
        if Path(c).is_file():
            pytesseract.pytesseract.tesseract_cmd = c
            return True

    return False


class BaseFetcher:
    """Classe de base pour les scripts fetch Playwright.

    Fournit l'infrastructure commune : config, logger, launch/close browser,
    impression PDF via CDP.

    Args:
        site_config_section: Nom de la section dans config.ini (ex: 'PEE')
        script_name: Nom du script pour le Logger (ex: 'cpt_fetch_PEE')
        verbose: Mode verbeux
        viewport: Dict {"width": W, "height": H} ou None pour le défaut
        dialog_handler: Callback pour page.on("dialog", ...) ou None
        delete_cookies: Supprimer les cookies du profil avant le lancement
    """

    def __init__(self, site_config_section=None, script_name=None, verbose=False,
                 viewport=None, dialog_handler=None, delete_cookies=False,
                 headed=False, caller_file=None):
        # Dérivation automatique depuis le nom de fichier appelant
        if caller_file:
            stem = Path(caller_file).stem  # ex: cpt_fetch_BB
            if site_config_section is None:
                site_config_section = stem.replace('cpt_fetch_', '')
            if script_name is None:
                script_name = stem
        self.verbose = verbose
        self.debug = DEBUG
        self.site_config_section = site_config_section  # clé site (ex. ETORO) → profil
        self.site_name = config.get(site_config_section, 'name',
                                    fallback=site_config_section)
        self.base_url = config.get(site_config_section, 'base_url',
                                   fallback='')
        self.credential_id = config.get(site_config_section, 'credential_id',
                                        fallback=None)
        self.credentials_file = Path(config.get(
            'paths', 'credentials_file',
            fallback='./config_credentials.md.gpg'
        )).expanduser()
        dossier = config.get(site_config_section, 'dossier', fallback=site_config_section)
        self.dropbox_dir = BASE_DIR / config.get('paths', 'dropbox') / dossier
        self._chrome_profile_dir = BASE_DIR / f'.chrome_profile_{site_config_section.lower()}'
        self._viewport = viewport or DEFAULT_VIEWPORT
        self._dialog_handler = dialog_handler
        self._delete_cookies = delete_cookies
        self._headed = headed
        # Override per-site (config.ini, per-instance) : forcer headed même sous
        # DEBUG=false. Utile là où le headless casse une opération sur une machine
        # donnée (ex. printToPDF CDP qui pend sur macOS, export qui reçoit du HTML)
        # → `[SITE] headed = true`. Facultatif (commenté dans config.ini.default).
        if site_config_section and config.has_option(site_config_section, 'headed'):
            try:
                self._headed = config.getboolean(site_config_section, 'headed')
            except ValueError:
                pass

        self.logger = Logger(
            script_name=script_name,
            journal_file=JOURNAL_FILE,
            verbose=verbose,
            debug=DEBUG,
        )
        self.logs_dir = LOGS_DIR
        self.playwright = None
        self.context = None
        self.page = None
        self.downloads = []

    def launch_browser(self):
        """Lance Chrome avec profil persistant."""
        self._chrome_profile_dir.mkdir(parents=True, exist_ok=True)

        if self._delete_cookies:
            self._delete_profile_cookies()

        self.logger.info(f"Lancement Chrome (profil: {self._chrome_profile_dir.name})")
        self.playwright = sync_playwright().start()

        self.context = self.playwright.chromium.launch_persistent_context(
            user_data_dir=str(self._chrome_profile_dir),
            channel="chrome",
            headless=not DEBUG and not self._headed,
            args=["--disable-blink-features=AutomationControlled"],
            viewport=self._viewport,
        )

        if self.context.pages:
            self.page = self.context.pages[0]
        else:
            self.page = self.context.new_page()

        if self._dialog_handler:
            self.page.on("dialog", self._dialog_handler)

    def _clear_site_storage(self):
        """Nettoie tout le storage du site via CDP (complète la suppression cookies fichier).

        Supprime cookies, cache, local storage, IndexedDB, service workers,
        etc. pour l'origine base_url. Nécessaire car la suppression du fichier
        Cookies seul ne couvre pas tous les mécanismes de persistance.
        """
        if not self.base_url:
            return
        try:
            cdp = self.context.new_cdp_session(self.page)
            origin = self.base_url.rstrip('/')
            cdp.send("Storage.clearDataForOrigin", {
                "origin": origin,
                "storageTypes": "all",
            })
            cdp.detach()
            self.logger.debug(f"Storage nettoyé via CDP: {origin}")
        except Exception as e:
            self.logger.debug(f"Nettoyage storage CDP: {e}")

    @contextmanager
    def _time_limit(self, seconds, what):
        """Borne une section hang-prone par SIGALRM (thread principal du
        sous-process de collecte, cf. cpt_fetch.Popen par site → Mac + Linux).
        Lève TimeoutError au-delà de `seconds`. No-op si SIGALRM indisponible.
        Empêche qu'un appel bloquant SANS timeout interne (CDP printToPDF…) ne
        pende jusqu'au kill orchestrateur (5 min). PEP 475 : le handler qui lève
        interrompt le syscall bloqué sans retry. (Cousin du watchdog close().)"""
        import signal
        if not hasattr(signal, 'SIGALRM'):
            yield
            return

        def _on_timeout(signum, frame):
            raise TimeoutError(what)

        old = signal.signal(signal.SIGALRM, _on_timeout)
        signal.alarm(int(seconds))
        try:
            yield
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old)

    def save_page_as_pdf(self, filename):
        """Imprime la page courante en PDF via CDP Page.printToPDF.

        Args:
            filename: Nom du fichier PDF de sortie

        Returns:
            Path du fichier créé ou None
        """
        output_path = self.dropbox_dir / filename
        try:
            if output_path.exists():
                output_path.unlink()

            self.dropbox_dir.mkdir(parents=True, exist_ok=True)
            cdp = self.context.new_cdp_session(self.page)
            # printToPDF CDP n'a pas de timeout interne → borné (30s) pour qu'une
            # page qui ne répond pas devienne un échec PDF LOCAL rapide (except
            # plus bas → None) plutôt qu'un hang jusqu'au kill orchestrateur
            # 5 min. Générique : NATIXIS/SOCGEN/ETORO/BOURSOBANK y passent (#6).
            with self._time_limit(30, f"printToPDF {filename} dépassé"):
                result = cdp.send("Page.printToPDF", {
                    "printBackground": True,
                    "preferCSSPageSize": True,
                })
            pdf_data = base64.b64decode(result['data'])
            cdp.detach()

            with open(output_path, 'wb') as f:
                f.write(pdf_data)

            file_size = len(pdf_data) / 1024
            self.logger.info(f"  {filename} ({file_size:.0f} Ko)")
            self.downloads.append(output_path)
            return output_path

        except Exception as e:
            self.logger.warning(f"  Impression PDF {filename}: {e}")
            return None

    @staticmethod
    def looks_like_html(data):
        """Vrai si `data` (bytes) ressemble à une page HTML plutôt qu'au fichier
        attendu (CSV/PDF). Sert à refuser d'enregistrer une page login/redirect
        qu'un site sert parfois en HTTP 200 quand la session a expiré ou que
        l'URL d'export n'est plus la bonne — sinon le format échoue plus tard sur
        un cryptique KeyError (ex. BOURSOBANK 'dateOp')."""
        head = (data or b'')[:512].lstrip().lower()
        return head.startswith(b'<!doctype html') or head.startswith(b'<html')

    def reject_saved_if_html(self, path, label):
        """Après un download écrit sur disque : si le fichier est en réalité une
        page HTML (session expirée / mauvais export), le supprimer et renvoyer
        False. Renvoie True si le fichier est légitime (conservé). À appeler sur
        tout chemin de sauvegarde de download qui ne valide pas déjà le contenu
        (l'event `download` Playwright ne porte pas de content-type)."""
        try:
            with open(path, 'rb') as f:
                head = f.read(512)
        except OSError:
            return True  # illisible → laisser le flux normal gérer
        if self.looks_like_html(head):
            self.logger.error(
                f"  {label}: réponse HTML au lieu du fichier attendu "
                f"({path.name}) — session expirée ou mauvais export ? Fichier ignoré.")
            try:
                path.unlink()
            except OSError:
                pass
            return False
        return True

    def load_gpg_credentials(self):
        """Charge les credentials GPG.

        Returns:
            Tuple (username, password) ou (None, None) si indisponible
        """
        if not self.credential_id or not get_credentials_from_gpg:
            return None, None
        return get_credentials_from_gpg(
            self.credentials_file, self.credential_id, verbose=DEBUG
        )

    def relaunch_headed(self):
        """Ferme le navigateur et relance en mode headed (visible).

        Utile pour repli interactif (CAPTCHA, vérification manuelle).
        """
        self.logger.info("Relance Chrome en mode headed...")
        self.close()
        self._headed = True
        self.launch_browser()

    def prompt_manual_login(self, nav_url, connected_check, timeout_s=180):
        """Filet quand l'auto-login échoue (credentials absents, sélecteur cassé,
        OCR raté) : rend la fenêtre VISIBLE si on tournait headless, re-navigue
        vers `nav_url`, et attend que l'utilisateur se connecte à la main. Sans ce
        filet, un fetcher headless resterait invisible → l'humain notifié (🔔) n'a
        pas de fenêtre pour agir.

        `connected_check` : callable() -> bool, vrai une fois connecté (à fournir
        par le site : son propre indicateur de session active). Renvoie True si
        connecté avant `timeout_s`, False sinon. Best-effort (une exception du
        check n'interrompt pas l'attente)."""
        if not (self.debug or self._headed):
            self.relaunch_headed()
        try:
            self.page.goto(nav_url, wait_until="domcontentloaded")
        except Exception:
            pass
        self.logger.alert("CONNEXION REQUISE — connecte-toi dans la fenêtre Chrome")
        start = time.monotonic()
        while time.monotonic() - start < timeout_s:
            try:
                if connected_check():
                    self.logger.user_done()
                    return True
            except Exception:
                pass
            time.sleep(2)
        self.logger.error(f"Timeout login manuel ({timeout_s}s)")
        return False

    def close(self):
        """Ferme le navigateur, borné par un watchdog SIGALRM.

        Sur un contexte persistant ayant servi une session CDP (`printToPDF`),
        `context.close()`/`playwright.stop()` peuvent **pendre indéfiniment**
        (observé NATIXIS + BOURSOBANK, headless comme headed) : les 2 sites
        produisent pourtant TOUS leurs fichiers puis se figent à la fermeture,
        et seul le kill orchestrateur à 5 min y met fin — masquant une collecte
        réussie et bloquant un slot du pool tout ce temps. On borne donc le
        teardown : SIGALRM (thread principal du sous-process de collecte, cf.
        cpt_fetch.Popen par site → Mac + Linux OK). PEP 475 : le handler qui
        lève interrompt le syscall bloqué sans retry.

        Returns:
            True si fermé proprement ; False si le teardown a été abandonné
            (le caller `fetch_main` bascule alors sur os._exit pour ne pas
            risquer un hang au cleanup interpréteur avec un driver mi-fermé).
        """
        import signal

        fired = {'v': False}

        def _on_timeout(signum, frame):
            fired['v'] = True
            raise TimeoutError("teardown navigateur dépassé")

        has_alarm = hasattr(signal, 'SIGALRM')
        old_handler = None
        if has_alarm:
            old_handler = signal.signal(signal.SIGALRM, _on_timeout)
            signal.alarm(20)
        try:
            if self.context:
                self.context.close()
            if self.playwright:
                self.playwright.stop()
            self.logger.debug("Navigateur fermé")
        except Exception as e:
            # On décide « abandon » sur le flag du handler, pas sur le type
            # d'exception : Playwright peut ré-emballer la TimeoutError.
            if fired['v']:
                self.logger.warning(
                    "Fermeture navigateur > 20s — abandon du teardown "
                    "(collecte OK, fichiers déjà écrits)")
            else:
                self.logger.debug(f"Erreur fermeture navigateur: {e}")
        finally:
            if has_alarm:
                signal.alarm(0)
                signal.signal(signal.SIGALRM, old_handler)
        return not fired['v']

    def run(self):
        """Logique métier du script — à implémenter dans les sous-classes.

        Returns:
            True si succès, False sinon
        """
        raise NotImplementedError

    def _delete_profile_cookies(self):
        """Supprime les fichiers cookies du profil Chrome sur disque.

        Prévention anti-redirect : un profil contaminé peut déclencher des
        redirections OAuth. La suppression force un login propre.
        """
        for name in ['Cookies', 'Cookies-journal']:
            cookie_file = self._chrome_profile_dir / 'Default' / name
            if cookie_file.exists():
                cookie_file.unlink()

    def _dump_page_debug(self, label, force=False):
        """Sauvegarde le HTML et un screenshot pour debug.

        Args:
            label: Suffixe pour les fichiers (ex: 'download_fail_compte')
            force: Si True, sauvegarde même si DEBUG=False (pour diagnostiquer les erreurs)
        """
        if not force and not DEBUG:
            return
        # Best-effort ABSOLU : une capture de diagnostic ne doit JAMAIS devenir
        # la panne. HTML et PNG protégés séparément ; screenshot BORNÉ (5s) car
        # sur une page en navigation/détruite `page.screenshot` pendait 30s puis
        # levait — et, appelé depuis un `except` non re-protégé (BB export titres),
        # ça remontait en « erreur inattendue » (s.205). Idem `page.content()`.
        try:
            debug_dir = LOGS_DIR / 'debug'
            debug_dir.mkdir(parents=True, exist_ok=True)
            prefix = self.site_name.lower().replace(' ', '_')
        except Exception:
            return
        try:
            html_file = debug_dir / f'{prefix}_{label}.html'
            with open(html_file, 'w', encoding='utf-8') as f:
                f.write(self.page.content())
            self.logger.debug(f"HTML sauvegardé: {html_file}")
        except Exception as e:
            self.logger.debug(f"Dump HTML {label} impossible: {e}")
        try:
            png_file = debug_dir / f'{prefix}_{label}.png'
            self.page.screenshot(path=str(png_file), timeout=5000)
            self.logger.debug(f"Screenshot sauvegardé: {png_file}")
        except Exception as e:
            self.logger.debug(f"Dump screenshot {label} impossible: {e}")

    def dump_failure(self, label='echec'):
        """Filet de sécurité (#149) : au moindre échec (appelé par fetch_main),
        capture l'état de la page (DOM + screenshot) dans logs/debug/ MÊME sans
        DEBUG, et signale le chemin de façon VISIBLE. Un échec « bloqué/timeout »
        n'est diagnosticable qu'avec le snapshot AU point d'échec (le texte
        title/url est insuffisant et trompeur). No-op si pas de page (navigateur
        non lancé ou déjà fermé) ; best-effort (n'échoue jamais)."""
        if getattr(self, 'page', None) is None:
            return
        try:
            self._dump_page_debug(label, force=True)
            prefix = self.site_name.lower().replace(' ', '_')
            self.logger.warning(
                f"État capturé pour diagnostic : logs/debug/{prefix}_{label}.html (+ .png)")
        except Exception as e:
            self.logger.warning(f"Capture de diagnostic impossible : {e}")

    def step(self, label):
        """Marque une étape de navigation (profil s.202) ET capture un snapshot
        DOM roulant de son début (couche d'investigation). À appeler depuis run()
        à chaque frontière de phase (Login, Opérations, Soldes…) — remplace un
        éventuel logger.info() de début de phase. Le label est la CLÉ de baseline
        du profil ET du nom de fichier snapshot → le garder STABLE."""
        self.logger.step(label)
        self._snapshot_step(label)

    def _snapshot_step(self, label):
        """Snapshot DOM (roulant, écrasé par run) du début d'une étape → on a
        toujours le dernier run de chaque site/étape pour investiguer un
        changement de comportement (cousin de dump_failure #149, mais SANS
        échec). DOM toujours (quasi gratuit) ; PNG seulement en mode 'full'
        (coûteux). Gouverné par [general] dump_steps. Best-effort : jamais
        bloquant (une capture ne doit pas casser une collecte)."""
        if DUMP_STEPS == 'off' or getattr(self, 'page', None) is None:
            return
        try:
            debug_dir = LOGS_DIR / 'debug'
            debug_dir.mkdir(parents=True, exist_ok=True)
            prefix = self.site_name.lower().replace(' ', '_')
            safe = re.sub(r'[^\w]+', '_', label).strip('_').lower() or 'etape'
            base = debug_dir / f'{prefix}_step_{safe}'
            base.with_suffix('.html').write_text(self.page.content(),
                                                 encoding='utf-8')
            if DUMP_STEPS == 'full':
                self.page.screenshot(path=str(base.with_suffix('.png')))
        except Exception:
            pass  # best-effort : ne jamais bloquer une collecte


def fetch_main(fetcher_class, description='', add_arguments=None, pre_run=None):
    """Boilerplate main() pour les scripts fetch.

    Parse -v/--verbose, instancie le fetcher, lance le browser,
    appelle run(), gère les erreurs et ferme proprement.

    Args:
        fetcher_class: Classe héritant de BaseFetcher
        description: Description pour argparse
        add_arguments: Callback(parser) pour ajouter des arguments CLI
        pre_run: Callback(fetcher, args) appelé avant launch_browser().
                 Retourne False pour skip (return 0), True pour continuer.

    Returns:
        Code retour (0 = succès, 1 = erreur)
    """
    parser = argparse.ArgumentParser(
        description=description,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='Mode verbeux')
    if add_arguments:
        add_arguments(parser)
    args = parser.parse_args()

    fetcher = fetcher_class(verbose=args.verbose)
    fetcher.logger.info(f"Récupération {fetcher.site_name}")
    fetcher.logger.info(f"Mode: {COMPTA_MODE.upper()}")

    if pre_run is not None and not pre_run(fetcher, args):
        return 0

    fetcher.dropbox_dir.mkdir(parents=True, exist_ok=True)

    # Vérifier GPG avant de lancer le navigateur (évite Chrome inutile si passphrase fausse)
    if fetcher.credential_id:
        username, password = fetcher.load_gpg_credentials()
        if not username or not password:
            fetcher.logger.error("Credentials GPG invalides — abandon")
            return 1

    success = False
    _t0 = time.monotonic()
    try:
        fetcher.launch_browser()
        success = fetcher.run()
        if not success:
            fetcher.dump_failure('echec_run')  # filet #149 (avant close())
        return 0 if success else 1

    except KeyboardInterrupt:
        fetcher.logger.warning("Interrompu par l'utilisateur")
        return 1
    except Exception as e:
        fetcher.logger.error(f"Erreur inattendue: {e}")
        if DEBUG:
            import traceback
            traceback.print_exc()
        fetcher.dump_failure('exception')  # filet #149 (avant close())
        return 1
    finally:
        clean = fetcher.close()
        # Profil de navigation (s.202) : enregistre le run (étapes + fichiers +
        # succès) et met à jour la baseline machine-locale. Même sur échec (un
        # run partiel EST un signal). Ne doit JAMAIS casser une collecte.
        # Placé APRÈS close() mais avant l'éventuel os._exit → une collecte dont
        # seul le teardown a pendu est bien enregistrée.
        try:
            import inc_fetch_profile
            steps = fetcher.logger.steps()
            if not steps:  # fetcher non instrumenté → au moins la durée totale
                steps = [("Collecte", time.monotonic() - _t0, False)]
            inc_fetch_profile.record_run(
                BASE_DIR, fetcher.site_config_section,
                steps, fetcher.downloads, success)
        except Exception:
            pass
        # Teardown abandonné (watchdog) : le driver Playwright peut être
        # mi-fermé → un exit normal risquerait de re-pendre au cleanup
        # interpréteur/atexit. On sort en dur avec le bon code retour, après
        # avoir vidé stdout (capturé par l'orchestrateur).
        if not clean:
            import os
            try:
                sys.stdout.flush()
                sys.stderr.flush()
            except Exception:
                pass
            os._exit(0 if success else 1)
