#!/usr/bin/env python3
"""
Script de collecte automatique depuis plusieurs sites - Tier 1
Usage:
    cpt_fetch.py                    # Collecte depuis tous les sites actifs
    cpt_fetch.py --sites SOCGEN         # Collecte uniquement depuis SG
    cpt_fetch.py --sites SOCGEN,WISE  # Collecte depuis plusieurs sites
"""

import sys
import os
import subprocess
import argparse
import configparser
import threading
from pathlib import Path
from datetime import datetime
import inc_mode
from inc_logging import Logger

# ============================================================================
# CONFIGURATION
# ============================================================================

# Utiliser la détection automatique de mode avec vérification de cohérence
BASE_DIR = inc_mode.get_base_dir()
COMPTA_MODE = inc_mode.get_mode()
SCRIPT_DIR = Path(__file__).parent
CONFIG_FILE = BASE_DIR / 'config.ini'


class ComptaFetcher:
    def __init__(self, sites_filter=None, verbose=False):
        """
        Args:
            sites_filter: Liste de sites à traiter (None = tous les sites actifs)
            verbose: Mode verbeux
        """
        self.sites_filter = sites_filter
        self.verbose = verbose
        self.stats = {
            'sites_attempted': 0,
            'sites_succeeded': 0,
            'sites_failed': 0,
            'errors': []
        }

        # Charger la configuration
        self.config = configparser.ConfigParser()
        if not CONFIG_FILE.exists():
            print(f"❌ config.ini introuvable dans {BASE_DIR}", file=sys.stderr)
            sys.exit(1)

        self.config.read(CONFIG_FILE)
        self.debug = self.config.getboolean('general', 'DEBUG', fallback=False)

        # Créer le logger
        self.logger = Logger(
            script_name="cpt_fetch",
            journal_file=None,  # Pas de journal pour ce script (les sous-scripts ont leur propre journal)
            verbose=self.verbose,
            debug=self.debug
        )

        # Charger les sites activés
        self.enabled_sites = []
        if self.config.has_section('sites'):
            enabled = self.config.get('sites', 'enabled', fallback='')
            self.enabled_sites = [s.strip() for s in enabled.split(',') if s.strip()]

        # Filtrer si nécessaire
        if self.sites_filter:
            self.sites_to_process = [s for s in self.sites_filter if s in self.enabled_sites]
            if len(self.sites_to_process) < len(self.sites_filter):
                missing = set(self.sites_filter) - set(self.sites_to_process)
                self.logger.warning(f"Sites non configurés ou inactifs: {', '.join(missing)}")
        else:
            self.sites_to_process = self.enabled_sites

    def fetch_site(self, site):
        """Lance le script de collecte pour un site donné

        Args:
            site: Nom du site (ex: 'SOCGEN', 'WISE')

        Returns:
            bool: True si succès, False sinon
        """
        if not self.config.has_section(site):
            self.logger.error(f"Site {site}: configuration introuvable")
            return False

        site_name = self.config.get(site, 'name', fallback=site)

        # Convention automatique: cpt_fetch_SITE.py — d'abord PUB (BASE_DIR),
        # fallback PRV (BASE_DIR/custom). Permet aux sites custom
        # (sites privés sous custom/) d'être pris en charge.
        fetch_script_path = BASE_DIR / f'cpt_fetch_{site}.py'
        if not fetch_script_path.exists():
            custom_path = BASE_DIR / 'custom' / f'cpt_fetch_{site}.py'
            if custom_path.exists():
                fetch_script_path = custom_path
        if not fetch_script_path.exists():
            # Vérifier si c'est un site en mode manuel (pas de base_url)
            has_base_url = self.config.has_option(site, 'base_url')
            if not has_base_url:
                # Site en mode manuel - ignorer silencieusement
                self.logger.info(f"Site {site}: mode manuel (pas de fetch automatique)")
                return True  # Succès (pas d'erreur)
            else:
                self.logger.error(f"Site {site}: script cpt_fetch_{site}.py introuvable (ni PUB ni custom/)")
                return False

        # Toujours afficher le site en cours
        timestamp = datetime.now().strftime('%H:%M:%S')
        print(f"\n{timestamp} → {site_name} ({site})...", flush=True)

        try:
            # Invocation directe : laisse le shebang du script cible imposer
            # son interpréteur (notamment `python3-uno` pour cpt_fetch_quotes
            # ou tout futur fetcher UNO). Cohérent avec doctrine § Décisions
            # architecturales. Les fetchers gèrent leur flush via
            # `print(..., flush=True)` (pas besoin du -u).
            #
            # PYTHONPATH=BASE_DIR pour que les fetchers custom/ trouvent les
            # modules PUB (inc_fetch, inc_excel_schema, ...) à l'import —
            # sys.path par défaut prend le dossier du script (= custom/).
            import os
            env = {**os.environ}
            existing = env.get('PYTHONPATH', '')
            env['PYTHONPATH'] = (f"{BASE_DIR}{os.pathsep}{existing}"
                                 if existing else str(BASE_DIR))
            proc = subprocess.Popen(
                [str(fetch_script_path)],
                cwd=str(BASE_DIR),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                env=env,
            )

            output_lines = []

            def read_output():
                for line in proc.stdout:
                    line = line.rstrip('\n')
                    output_lines.append(line)
                    if self.verbose:
                        print(line, flush=True)
                    elif '🔔' in line or 'Skip' in line:
                        print(f"  {line}", flush=True)

            reader = threading.Thread(target=read_output, daemon=True)
            reader.start()

            try:
                proc.wait(timeout=300)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
                print("  ✗ (timeout)")
                self.stats['errors'].append(f"{site}: timeout > 5 min")
                return False

            reader.join(timeout=5)

            if proc.returncode == 0:
                print("  ✓")
                return True
            else:
                # Chercher la dernière erreur dans la sortie capturée.
                # 1. Priorité : ligne `❌` formelle des fetchers.
                # 2. Sinon : dernière ligne d'un Traceback Python (cause typique
                #    d'erreurs non gérées : ModuleNotFoundError, etc.).
                # 3. Fallback : dernière ligne non-vide.
                last_error = ""
                for line in reversed(output_lines):
                    if '❌' in line:
                        last_error = line.strip()
                        break
                if not last_error:
                    # Détecter un traceback : prendre la ligne suivant le
                    # dernier "Traceback (most recent call last):" jusqu'à la
                    # fin (en pratique = type d'exception + message).
                    for i, line in enumerate(output_lines):
                        if 'Traceback (most recent call last)' in line:
                            tail = [l for l in output_lines[i+1:]
                                    if l.strip() and not l.startswith('  ')]
                            if tail:
                                last_error = tail[-1].strip()
                                break
                if not last_error:
                    # Dernière ligne non vide quelle qu'elle soit
                    for line in reversed(output_lines):
                        if line.strip():
                            last_error = line.strip()
                            break
                if not last_error:
                    last_error = "Erreur inconnue (sortie vide)"
                print(f"  ✗ {last_error}")
                self.stats['errors'].append(f"{site}: {last_error}")
                return False

        except Exception as e:
            print(f"  ✗ ({e})")
            self.stats['errors'].append(f"{site}: {e}")
            return False

    def check_gpg(self):
        """Vérifie que le fichier GPG se déchiffre (passphrase en cache ou saisie).

        Returns:
            bool: True si OK, False si échec
        """
        credentials_file = Path(self.config.get(
            'paths', 'credentials_file',
            fallback='./config_credentials.md.gpg'
        )).expanduser()

        if not credentials_file.exists():
            self.logger.error(f"Fichier credentials introuvable: {credentials_file}")
            return False

        result = subprocess.run(
            ['gpg', '--decrypt', str(credentials_file)],
            capture_output=True, text=True, check=False
        )
        if result.returncode != 0:
            self.logger.error("Échec déchiffrement GPG — abandon collecte")
            if result.stderr:
                self.logger.error(f"  {result.stderr[:200]}")
            return False
        return True

    def fetch_all(self):
        """Lance la collecte pour tous les sites à traiter

        Returns:
            bool: True si au moins un site a réussi, False sinon
        """
        if not self.sites_to_process:
            self.logger.error("Aucun site à traiter")
            return False

        # Vérifier GPG une seule fois avant de lancer les sites
        if not self.check_gpg():
            return False

        self.logger.verbose(f"Sites à traiter: {', '.join(self.sites_to_process)}")

        for site in self.sites_to_process:
            self.stats['sites_attempted'] += 1

            if self.fetch_site(site):
                self.stats['sites_succeeded'] += 1
            else:
                self.stats['sites_failed'] += 1

        return self.stats['sites_succeeded'] > 0

    def print_stats(self):
        """Affiche les statistiques de collecte"""
        if self.stats['errors']:
            print(f"\n⚠️  Erreurs ({len(self.stats['errors'])}):")
            for error in self.stats['errors']:
                print(f"  - {error}")


def main():
    parser = argparse.ArgumentParser(
        description='Script de collecte automatique depuis plusieurs sites',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples:
  %(prog)s                           # Collecte depuis tous les sites actifs
  %(prog)s --sites SOCGEN                # Collecte uniquement depuis SG
  %(prog)s --sites SOCGEN,WISE     # Collecte depuis plusieurs sites
  %(prog)s -v                        # Mode verbeux
        """)

    parser.add_argument('--sites',
                        metavar='SITE1,SITE2',
                        help='Liste de sites séparés par des virgules (ex: SOCGEN,WISE)')
    parser.add_argument('-v', '--verbose',
                        action='store_true',
                        help='Mode verbeux (affiche la sortie de chaque script)')

    args = parser.parse_args()

    # Parser la liste de sites si fournie
    sites_filter = None
    if args.sites:
        sites_filter = [s.strip() for s in args.sites.split(',') if s.strip()]

    # Créer le fetcher et lancer la collecte
    fetcher = ComptaFetcher(sites_filter=sites_filter, verbose=args.verbose)
    success = fetcher.fetch_all()
    fetcher.print_stats()

    if success:
        sys.exit(0)
    else:
        print("\n❌ La collecte a échoué pour tous les sites")
        sys.exit(1)


if __name__ == "__main__":
    main()
