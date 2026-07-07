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
import argparse
import base64
import configparser
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

    def close(self):
        """Ferme le navigateur proprement."""
        try:
            if self.context:
                self.context.close()
            if self.playwright:
                self.playwright.stop()
            self.logger.debug("Navigateur fermé")
        except Exception as e:
            self.logger.debug(f"Erreur fermeture navigateur: {e}")

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
        debug_dir = LOGS_DIR / 'debug'
        debug_dir.mkdir(parents=True, exist_ok=True)

        prefix = self.site_name.lower().replace(' ', '_')
        html_file = debug_dir / f'{prefix}_{label}.html'
        html = self.page.content()
        with open(html_file, 'w', encoding='utf-8') as f:
            f.write(html)
        self.logger.debug(f"HTML sauvegardé: {html_file}")

        png_file = debug_dir / f'{prefix}_{label}.png'
        self.page.screenshot(path=str(png_file))
        self.logger.debug(f"Screenshot sauvegardé: {png_file}")


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

    try:
        fetcher.launch_browser()
        success = fetcher.run()
        return 0 if success else 1

    except KeyboardInterrupt:
        fetcher.logger.warning("Interrompu par l'utilisateur")
        return 1
    except Exception as e:
        fetcher.logger.error(f"Erreur inattendue: {e}")
        if DEBUG:
            import traceback
            traceback.print_exc()
        return 1
    finally:
        fetcher.close()
