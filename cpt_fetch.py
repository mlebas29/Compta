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
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from datetime import datetime
import inc_mode
import inc_format
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
    def __init__(self, sites_filter=None, verbose=False, auto_only=False):
        """
        Args:
            sites_filter: Liste de sites à traiter (None = tous les sites actifs)
            verbose: Mode verbeux
            auto_only: Ne collecter que le tier 'auto' (#147, mode cron)
        """
        self.sites_filter = sites_filter
        self.verbose = verbose
        self.auto_only = auto_only
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

    def fetch_site(self, site, prefix=''):
        """Lance le script de collecte pour un site donné

        Args:
            site: Nom du site (ex: 'SOCGEN', 'WISE')
            prefix: Préfixe de ligne (ex: '[YUH] ') pour démêler la sortie
                    quand plusieurs sites collectent en parallèle (#147).

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

        # Toujours afficher le site en cours (ligne vide de séparation en mode
        # séquentiel ; en parallèle le préfixe suffit à démêler).
        timestamp = datetime.now().strftime('%H:%M:%S')
        if not prefix:
            print()
        print(f"{prefix}{timestamp} → {site_name} ({site})...", flush=True)

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
                        print(f"{prefix}{line}", flush=True)
                    elif '🔔' in line or 'Skip' in line:
                        print(f"{prefix}  {line}", flush=True)

            reader = threading.Thread(target=read_output, daemon=True)
            reader.start()

            try:
                proc.wait(timeout=300)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
                print(f"{prefix}  ✗ (timeout)")
                self.stats['errors'].append(f"{site}: timeout > 5 min")
                return False

            reader.join(timeout=5)

            if proc.returncode == 0:
                print(f"{prefix}  ✓")
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
                    # Sortie vraiment vide : le code retour reste le seul
                    # indice (négatif = signal, 126/127 = souci d'exécution).
                    last_error = (f"Erreur inconnue (sortie vide, "
                                  f"code retour {proc.returncode})")
                print(f"{prefix}  ✗ {last_error}")
                self.stats['errors'].append(f"{site}: {last_error}")
                return False

        except Exception as e:
            print(f"{prefix}  ✗ ({e})")
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

    # --- Tiérage (#147) : groupe PARALLÈLE vs groupe SÉRIEL ---------------
    # Deux axes ORTHOGONAUX. Axe A = `parallel` : le site va-t-il dans le groupe
    # parallèle (collecté en même temps que les autres) ou sériel (humain requis
    # PENDANT la collecte : 2FA/CAPTCHA/code, un à la fois) ? Axe B = `credential`
    # (dérivé de `credential_id`) ne subdivise QUE le parallèle : semi (GPG, 1
    # pinentry partagé en amont) vs auto (rien → planifiable cron).
    # → 3 tiers : auto (parallèle, sans credential) · semi (parallèle, credential)
    #   · manual (sériel).
    # `parallel` est DÉRIVÉ de la nature du fetcher (structurel, certain : un
    # fetcher sans navigateur ne sollicite jamais l'humain → parallèle),
    # SURCHARGEABLE par `[SITE] parallel` (moitié « compte » : un site navigateur
    # SANS 2FA sur ce compte → `parallel = true`).
    def _site_parallel(self, site):
        # Override config si posé ; sinon dérivé (source unique inc_format) :
        # API/RPC → parallèle, navigateur → sériel. Repli sur l'ancien nom
        # `requires_2fa` (polarité INVERSE : requires_2fa=true ⟺ parallel=false)
        # = compat transitoire, à retirer une fois les config.ini migrées.
        if self.config.has_option(site, 'parallel'):
            return self.config.getboolean(site, 'parallel')
        if self.config.has_option(site, 'requires_2fa'):
            return not self.config.getboolean(site, 'requires_2fa')
        return not inc_format.is_browser_fetcher(site, BASE_DIR)

    def _site_has_credential(self, site):
        return bool(self.config.get(site, 'credential_id', fallback='').strip())

    def _site_tier(self, site):
        if not self._site_parallel(site):
            return 'manual'
        return 'semi' if self._site_has_credential(site) else 'auto'

    def fetch_all(self):
        """Lance la collecte pour tous les sites à traiter

        Returns:
            bool: True si au moins un site a réussi, False sinon
        """
        if not self.sites_to_process:
            self.logger.error("Aucun site à traiter")
            return False

        # Tiérage (#147) : auto (ni credential ni 2FA) → semi (credential sans
        # 2FA) → manual (2FA). Ordre stable dans chaque tier (préserve l'ordre
        # config) → l'humain n'attend pas les sites API, et ceux-ci ne bloquent
        # pas derrière un prompt 2FA.
        tier_rank = {'auto': 0, 'semi': 1, 'manual': 2}
        sites = sorted(self.sites_to_process,
                       key=lambda s: tier_rank[self._site_tier(s)])

        # Mode --auto (cron) : seul le tier 'auto' (aucun credential → aucun
        # pinentry possible → run planifiable sans humain).
        if self.auto_only:
            sites = [s for s in sites if self._site_tier(s) == 'auto']
            if not sites:
                self.logger.info("Mode --auto : aucun site du tier 'auto'")
                return True

        by_tier = {t: [s for s in sites if self._site_tier(s) == t]
                   for t in ('auto', 'semi', 'manual')}
        self.logger.verbose(
            "Tiers — auto: {} · semi: {} · manuel: {}".format(
                ', '.join(by_tier['auto']) or '—',
                ', '.join(by_tier['semi']) or '—',
                ', '.join(by_tier['manual']) or '—'))

        # GPG une seule fois, et SEULEMENT si un site en a besoin → un run --auto
        # (tier auto, sans credential) reste sans pinentry, donc planifiable.
        if any(self._site_has_credential(s) for s in sites) and not self.check_gpg():
            return False

        stats_lock = threading.Lock()

        def _run_one(site, prefix=''):
            with stats_lock:
                self.stats['sites_attempted'] += 1
            try:
                ok = self.fetch_site(site, prefix=prefix)
            except Exception as e:  # garde-fou : un site ne tue jamais le lot
                self.logger.error(f"{prefix}{site}: {e}")
                ok = False
            with stats_lock:
                self.stats['sites_succeeded' if ok else 'sites_failed'] += 1

        # Jambes CONCURRENTES (#147). Chaque non-interactif (auto+semi) = 1 jambe
        # parallèle (plafond 4). Le tier MANUEL forme UNE jambe de plus,
        # séquentielle en interne (l'humain fait une 2FA à la fois) mais tournant
        # EN MÊME TEMPS que les jambes machine → la collecte API/RPC se fait
        # PENDANT les 2FA humaines (total ≈ max, plus somme). Un seul mot de passe
        # GPG (déjà en cache) couvre tout le lot.
        non_interactive = by_tier['auto'] + by_tier['semi']
        manual = by_tier['manual']
        multi = len(non_interactive) + (1 if manual else 0) > 1
        pfx = (lambda s: f"[{s}] ") if multi else (lambda s: '')

        # Jambe manuelle : démarre tout de suite, en parallèle des jambes machine.
        manual_thread = None
        if manual:
            def _manual_leg():
                for site in manual:
                    _run_one(site, pfx(site))
            manual_thread = threading.Thread(target=_manual_leg, daemon=True)
            manual_thread.start()

        # Jambes non-interactives : parallèles, plafond 4.
        if len(non_interactive) > 1:
            self.logger.info(
                "Collecte parallèle : " + ', '.join(non_interactive)
                + (f" + séquence manuelle ({len(manual)})" if manual else ""))
            with ThreadPoolExecutor(max_workers=min(4, len(non_interactive))) as ex:
                for fut in [ex.submit(_run_one, s, pfx(s)) for s in non_interactive]:
                    fut.result()
        elif non_interactive:
            _run_one(non_interactive[0], pfx(non_interactive[0]))

        if manual_thread:
            manual_thread.join()

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
    parser.add_argument('--auto',
                        action='store_true',
                        help="Ne collecter que les sites 'auto' (ni credential "
                             "ni 2FA) — planifiable en cron, sans humain (#147)")

    args = parser.parse_args()

    # Parser la liste de sites si fournie
    sites_filter = None
    if args.sites:
        sites_filter = [s.strip() for s in args.sites.split(',') if s.strip()]

    # Créer le fetcher et lancer la collecte
    fetcher = ComptaFetcher(sites_filter=sites_filter, verbose=args.verbose,
                            auto_only=args.auto)
    success = fetcher.fetch_all()
    fetcher.print_stats()

    if success:
        sys.exit(0)
    else:
        print("\n❌ La collecte a échoué pour tous les sites")
        sys.exit(1)


if __name__ == "__main__":
    main()
