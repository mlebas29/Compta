#!/usr/bin/env python3
"""
Script principal de gestion comptable - Orchestrateur complet
Enchaîne la collecte (Tier 1) et l'import (Tier 3)

Usage:
    cpt.py                          # Collecte + Import tous les sites
    cpt.py --sites SG               # Collecte + Import uniquement SG
    cpt.py --sites SG,BG_GESTION    # Collecte + Import plusieurs sites
    cpt.py --fetch-only             # Collecte uniquement (pas d'import)
    cpt.py --update-only            # Import uniquement (pas de collecte)
    cpt.py --reset                  # Réinitialisation complète du système
    cpt.py --pull                   # Récupérer comptes.xlsm depuis Seafile
    cpt.py --push                   # Pousser comptes.xlsm vers Seafile
    cpt.py --fallback               # Annuler dernier fetch + import
    cpt.py --status                 # Vérifier l'état du système
"""

import sys
import os
import subprocess
import argparse
import shutil
import configparser
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
SCRIPT_DIR = Path(__file__).parent.resolve()

# Logger global (toujours afficher, pas de journal - les sous-scripts ont leur propre journal)
logger = Logger(
    script_name="cpt",
    journal_file=None,
    verbose=True,  # Toujours afficher les messages
    debug=False
)

# Charger la configuration
CONFIG_FILE = BASE_DIR / "config.ini"
config = configparser.ConfigParser()
if CONFIG_FILE.exists():
    config.read(CONFIG_FILE)
else:
    logger.error(f"Fichier de configuration introuvable : {CONFIG_FILE}")
    sys.exit(1)

# Répertoires pour vérifications
ARCHIVES_DIR = BASE_DIR / "archives"
DROPBOX_DIR = BASE_DIR / "dropbox"
LOGS_DIR = BASE_DIR / "logs"
DEBUG_DIR = LOGS_DIR / 'debug'
JOURNAL_FILE = LOGS_DIR / "journal.log"
MAX_SESSIONS = 10


# ============================================================================
# VERIFICATION (intégré depuis cpt_verify.py)
# ============================================================================

class VerificationResult:
    """Résultat d'une vérification"""
    def __init__(self, name):
        self.name = name
        self.passed = True
        self.warnings = []
        self.errors = []
        self.info = []

    def add_info(self, message):
        self.info.append(message)

    def add_warning(self, message):
        self.warnings.append(message)

    def add_error(self, message):
        self.errors.append(message)
        self.passed = False


def verify_backups(verbose=False):
    """Vérifie la cohérence des backups Excel dans archives/"""
    result = VerificationResult("Backups Excel")

    if not ARCHIVES_DIR.exists():
        result.add_error(f"Répertoire archives inexistant: {ARCHIVES_DIR}")
        return result

    backups = sorted(
        list(ARCHIVES_DIR.glob("comptes_HDS_*.xlsx")) + list(ARCHIVES_DIR.glob("comptes_HDS_*.xlsm")),
        key=lambda p: p.stat().st_mtime, reverse=True)
    result.add_info(f"{len(backups)} backup(s) Excel trouvé(s) dans archives/")

    if len(backups) == 0:
        result.add_warning("Aucun backup Excel trouvé dans archives/")
        return result

    if len(backups) > MAX_SESSIONS:
        result.add_warning(f"{len(backups)} backups (> {MAX_SESSIONS} max)")

    for backup in backups:
        try:
            parts = backup.stem.split('_HDS_')
            if len(parts) != 2:
                result.add_error(f"Format de backup invalide: {backup.name}")
                continue
            timestamp_str = parts[1]
            datetime.strptime(timestamp_str, '%Y%m%d_%H%M%S')
        except ValueError:
            result.add_error(f"Format de backup invalide: {backup.name}")

    mtimes = [b.stat().st_mtime for b in backups]
    if mtimes != sorted(mtimes, reverse=True):
        result.add_warning("Backups pas dans l'ordre chronologique")

    return result


def verify_journal(verbose=False):
    """Vérifie la cohérence du journal centralisé"""
    result = VerificationResult("Journal centralisé")

    if not JOURNAL_FILE.exists():
        result.add_warning(f"Journal inexistant: {JOURNAL_FILE}")
        return result

    try:
        with open(JOURNAL_FILE, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        result.add_info(f"{len(lines)} lignes dans le journal")

        sessions = []
        for line in lines:
            if line.startswith('=== SESSION'):
                parts = line.split()
                if len(parts) >= 4:
                    date_part = parts[2].replace('-', '')
                    time_part = parts[3].replace(':', '').replace('===', '').strip()
                    session_timestamp = f"{date_part}_{time_part}"
                    sessions.append(session_timestamp)

        result.add_info(f"{len(sessions)} session(s) dans le journal")

        if len(sessions) > MAX_SESSIONS:
            result.add_warning(f"{len(sessions)} sessions (> {MAX_SESSIONS} max)")

        if ARCHIVES_DIR.exists():
            backups = sorted(
                list(ARCHIVES_DIR.glob("comptes_*_HDS_*.xlsx")) + list(ARCHIVES_DIR.glob("comptes_*_HDS_*.xlsm")))
            backup_timestamps = set()
            for b in backups:
                parts = b.stem.split('_HDS_')
                if len(parts) == 2:
                    backup_timestamps.add(parts[1])

            session_timestamps = set(sessions)

            orphan_sessions = session_timestamps - backup_timestamps
            if orphan_sessions:
                result.add_warning(f"{len(orphan_sessions)} session(s) sans backup correspondant")

            missing_sessions = backup_timestamps - session_timestamps
            if missing_sessions:
                result.add_warning(f"{len(missing_sessions)} backup(s) sans session dans le journal")

    except Exception as e:
        result.add_error(f"Erreur lecture journal: {e}")

    return result


def verify_archives(verbose=False):
    """Vérifie la cohérence des archives"""
    result = VerificationResult("Archives")

    if not ARCHIVES_DIR.exists():
        result.add_warning(f"Répertoire archives inexistant: {ARCHIVES_DIR}")
        return result

    total_archives = 0
    sites = {}

    for site_dir in ARCHIVES_DIR.iterdir():
        if not site_dir.is_dir():
            continue
        archive_files = list(site_dir.glob("*"))
        sites[site_dir.name] = len(archive_files)
        total_archives += len(archive_files)

    result.add_info(f"{total_archives} fichier(s) archivé(s)")

    for site, count in sites.items():
        result.add_info(f"  {site}: {count} fichier(s)")

    backups = sorted(
        list(ARCHIVES_DIR.glob("comptes_*_HDS_*.xlsx")) + list(ARCHIVES_DIR.glob("comptes_*_HDS_*.xlsm")),
        key=lambda p: p.stat().st_mtime)

    if backups:
        oldest_backup_mtime = backups[0].stat().st_mtime
        old_archives = []
        for site_dir in ARCHIVES_DIR.iterdir():
            if not site_dir.is_dir():
                continue
            for archive_file in site_dir.glob("*"):
                if archive_file.stat().st_mtime < oldest_backup_mtime:
                    old_archives.append(archive_file)

        if old_archives:
            result.add_warning(f"{len(old_archives)} archive(s) plus ancienne(s) que le plus vieux backup")

    return result


def verify_dropbox(verbose=False):
    """Vérifie l'état du répertoire dropbox"""
    result = VerificationResult("Dropbox")

    if not DROPBOX_DIR.exists():
        result.add_error(f"Répertoire dropbox inexistant: {DROPBOX_DIR}")
        return result

    total_files = 0
    sites = {}

    root_files = list(DROPBOX_DIR.glob("*.pdf")) + list(DROPBOX_DIR.glob("*.csv"))
    if root_files:
        sites['racine'] = len(root_files)
        total_files += len(root_files)

    for site_dir in DROPBOX_DIR.iterdir():
        if not site_dir.is_dir():
            continue
        site_files = list(site_dir.glob("*.pdf")) + list(site_dir.glob("*.csv")) + list(site_dir.glob("*.xlsx"))
        if site_files:
            sites[site_dir.name] = len(site_files)
            total_files += len(site_files)

    if total_files == 0:
        result.add_info("Dropbox vide (normal après import)")
    else:
        result.add_warning(f"{total_files} fichier(s) en attente de traitement")
        for site, count in sites.items():
            result.add_warning(f"  {site}: {count} fichier(s)")

    return result


def verify_logs(verbose=False):
    """Vérifie l'état des logs"""
    result = VerificationResult("Logs")

    if not LOGS_DIR.exists():
        result.add_warning(f"Répertoire logs inexistant: {LOGS_DIR}")
        return result

    old_logs = list(LOGS_DIR.glob("update_*.log"))
    if old_logs:
        result.add_info(f"{len(old_logs)} log(s) individuel(s) (obsolète)")
        if len(old_logs) > MAX_SESSIONS:
            result.add_warning(f"{len(old_logs)} logs (> {MAX_SESSIONS} max)")

    if JOURNAL_FILE.exists():
        journal_size = JOURNAL_FILE.stat().st_size
        result.add_info(f"Journal: {journal_size:,} octets")
    else:
        result.add_warning("Journal centralisé absent")

    return result


def verify_debug(verbose=False):
    """Vérifie l'état des fichiers debug"""
    result = VerificationResult("Fichiers debug")

    if not DEBUG_DIR.exists():
        result.add_info("Répertoire debug inexistant (normal si DEBUG=false)")
        return result

    debug_files = list(DEBUG_DIR.glob("*"))
    if not debug_files:
        result.add_info("Aucun fichier debug")
        return result

    result.add_info(f"{len(debug_files)} fichier(s) debug")

    cutoff_time = datetime.now().timestamp() - (7 * 24 * 3600)
    old_files = [f for f in debug_files if f.stat().st_mtime < cutoff_time]
    if old_files:
        result.add_warning(f"{len(old_files)} fichier(s) debug > 7 jours")

    return result


def run_script(script_name, args_list):
    """Lance un script Python avec des arguments

    Args:
        script_name: Nom du script (ex: 'cpt_fetch.py')
        args_list: Liste d'arguments pour le script

    Returns:
        bool: True si succès, False sinon
    """
    script_path = BASE_DIR / script_name

    if not script_path.exists():
        logger.error(f"Script {script_name} introuvable dans {BASE_DIR}")
        return False

    try:
        result = subprocess.run(
            [sys.executable, str(script_path)] + args_list,
            cwd=str(BASE_DIR)
        )

        return result.returncode == 0

    except Exception as e:
        logger.error(f"Erreur lors de l'exécution de {script_name}: {e}")
        return False


def get_seafile_path():
    """Récupère le chemin Seafile depuis la configuration

    Returns:
        Path: Chemin vers le fichier Excel sur Seafile
    """
    seafile_path = config.get('paths', 'seafile_comptes_file', fallback=None)
    if not seafile_path:
        logger.error("Chemin Seafile non configuré dans config.ini [paths] seafile_comptes_file")
        sys.exit(1)

    # Expansion du tilde
    seafile_path = Path(seafile_path).expanduser()
    return seafile_path


def do_reset():
    """Réinitialisation complète du système

    Récupère comptes.xlsm depuis Seafile et purge tous les fichiers
    """
    logger.info("🔄 Réinitialisation complète du système")

    # 1. Récupérer comptes.xlsm depuis Seafile
    seafile_path = get_seafile_path()
    local_path = BASE_DIR / "comptes.xlsm"

    if not seafile_path.exists():
        logger.error(f"Fichier Seafile introuvable : {seafile_path}")
        sys.exit(1)

    logger.info(f"  Récupération depuis Seafile : {seafile_path}")
    shutil.copy2(seafile_path, local_path)
    logger.info(f"  ✓ Copié vers {local_path}")

    # 2. Purger tous les fichiers et répertoires dans archives/, dropbox/, logs/
    dirs_to_clean = ['archives', 'dropbox', 'logs']

    for dir_name in dirs_to_clean:
        dir_path = BASE_DIR / dir_name
        if not dir_path.exists():
            continue

        logger.info(f"  Purge {dir_name}/")
        file_count = 0
        dir_count = 0

        # First pass: delete all files
        for file_path in dir_path.rglob('*'):
            if file_path.is_file():
                file_path.unlink()
                file_count += 1

        # Second pass: delete all directories (bottom-up)
        for subdir_path in sorted(dir_path.rglob('*'), key=lambda p: len(p.parts), reverse=True):
            if subdir_path.is_dir():
                try:
                    subdir_path.rmdir()  # Only removes empty directories
                    dir_count += 1
                except OSError:
                    pass  # Directory not empty, skip

        logger.info(f"  ✓ {file_count} fichiers et {dir_count} répertoires supprimés dans {dir_name}/")

    # 3. Créer les répertoires SITE dans dropbox/ et archives/
    sites_enabled = config.get('sites', 'enabled', fallback='')
    sites = [s.strip() for s in sites_enabled.split(',') if s.strip()]

    if sites:
        logger.info("  Création des répertoires SITE...")
        for site in sites:
            for base_dir in ['dropbox', 'archives']:
                site_dir = BASE_DIR / base_dir / site
                site_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"  ✓ {len(sites)} sites : {', '.join(sites)}")

    logger.info("✓ Réinitialisation terminée")


def do_reset_template():
    """Réinitialisation template — classeur vierge + purge configs et données

    Utilisé en mode Export : charge le template vierge, vide les JSON
    de mapping (comptes, pipeline), purge archives/dropbox/logs et cookies.
    """
    logger.info("🔄 Réinitialisation template (classeur vierge)")

    # 1. Copier le template vierge → comptes.xlsm
    # En Export le template est livré à la racine, en DEV il est dans tests/
    if COMPTA_MODE == 'export':
        template_src = BASE_DIR / 'comptes_template.xlsm'
    else:
        template_src = SCRIPT_DIR / 'tests' / 'tnr' / 'template' / 'expected.xlsm'
    local_path = BASE_DIR / "comptes.xlsm"

    if not template_src.exists():
        logger.error(f"Template introuvable : {template_src}")
        sys.exit(1)

    logger.info(f"  Copie template : {template_src}")
    shutil.copy2(template_src, local_path)
    logger.info(f"  ✓ Copié vers {local_path}")

    # 2. Vider les JSON de mapping (références aux comptes du classeur)
    json_resets = {
        'config_accounts.json': '{}',
        'config_pipeline.json': '{"linked": [], "auto_solde": []}',
    }
    for filename, empty_content in json_resets.items():
        json_path = BASE_DIR / filename
        if json_path.exists():
            json_path.write_text(empty_content + '\n', encoding='utf-8')
            logger.info(f"  ✓ {filename} réinitialisé")

    # 3. Supprimer cookies
    cookies_path = BASE_DIR / '.bg_cookies.json'
    if cookies_path.exists():
        cookies_path.unlink()
        logger.info("  ✓ .bg_cookies.json supprimé")

    # 4. Purger archives/, dropbox/, logs/ (même logique que do_reset)
    dirs_to_clean = ['archives', 'dropbox', 'logs']

    for dir_name in dirs_to_clean:
        dir_path = BASE_DIR / dir_name
        if not dir_path.exists():
            continue

        logger.info(f"  Purge {dir_name}/")
        file_count = 0
        dir_count = 0

        for file_path in dir_path.rglob('*'):
            if file_path.is_file():
                file_path.unlink()
                file_count += 1

        for subdir_path in sorted(dir_path.rglob('*'), key=lambda p: len(p.parts), reverse=True):
            if subdir_path.is_dir():
                try:
                    subdir_path.rmdir()
                    dir_count += 1
                except OSError:
                    pass

        logger.info(f"  ✓ {file_count} fichiers et {dir_count} répertoires supprimés dans {dir_name}/")

    # 5. Recréer les répertoires SITE
    sites_enabled = config.get('sites', 'enabled', fallback='')
    sites = [s.strip() for s in sites_enabled.split(',') if s.strip()]

    if sites:
        logger.info("  Création des répertoires SITE...")
        for site in sites:
            for base_dir in ['dropbox', 'archives']:
                site_dir = BASE_DIR / base_dir / site
                site_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"  ✓ {len(sites)} sites : {', '.join(sites)}")

    logger.info("✓ Réinitialisation template terminée")


def do_pull():
    """Récupère comptes.xlsm depuis Seafile"""
    logger.info("⬇️  Pull comptes.xlsm depuis Seafile")

    seafile_path = get_seafile_path()
    local_path = BASE_DIR / "comptes.xlsm"

    if not seafile_path.exists():
        logger.error(f"Fichier Seafile introuvable : {seafile_path}")
        sys.exit(1)

    shutil.copy2(seafile_path, local_path)
    logger.info(f"✓ Copié depuis {seafile_path}")


def do_push(force=False):
    """Pousse comptes.xlsm vers Seafile après vérifications

    Vérifications avant push :
    1. tool_controles.py : COMPTES/CATEGORIES/INCONNUS bloquent (sauf --force)
    2. tool_refs.py --audit : affiche warnings références
    """
    logger.info("⬆️  Push comptes.xlsm vers Seafile")

    # Sécurité : bloquer le push depuis l'environnement TEST
    mode = inc_mode.get_mode()
    if mode == 'dev':
        logger.error("❌ Push interdit depuis l'environnement DEV")
        logger.error("   Déployer d'abord vers PROD : tool_deploy.py --to-prod")
        logger.error("   Puis lancer le push depuis ~/Compta")
        sys.exit(1)

    local_path = BASE_DIR / "comptes.xlsm"

    if not local_path.exists():
        logger.error(f"Fichier local introuvable : {local_path}")
        sys.exit(1)

    # 1. Vérification Contrôles
    logger.info("🔍 Vérification Contrôles...")
    result = subprocess.run(
        ['python3', str(BASE_DIR / 'tool_controles.py')],
        capture_output=True, text=True
    )

    if result.returncode in [1, 2]:
        # Erreur bloquante (COMPTES, CATEGORIES, INCONNUS)
        print(result.stdout)
        if force:
            logger.warning("⚠️  Erreurs ignorées (--force)")
        else:
            logger.error("❌ Push bloqué. Corriger les erreurs ou utiliser --force")
            sys.exit(1)
    elif result.returncode == 3:
        # Warnings non bloquants - afficher les détails
        print(result.stdout)
        logger.warning("⚠️  Warnings détectés (non bloquants)")
    elif result.returncode == 4:
        logger.error("❌ Erreur technique tool_controles.py")
        sys.exit(1)
    else:
        logger.info("✓ Contrôles OK")

    # 2. Audit références (informatif)
    logger.info("🔍 Audit références...")
    result = subprocess.run(
        ['python3', str(BASE_DIR / 'tool_refs.py'), '--audit'],
        capture_output=True, text=True
    )
    # Extraire juste le résumé (lignes avec symboles ✓/⚠/❌)
    for line in result.stdout.split('\n'):
        stripped = line.lstrip()
        if stripped.startswith('⚠') or stripped.startswith('✓') or stripped.startswith('❌'):
            print(f"  {stripped}")

    # 3. Audit catégorisations (informatif)
    logger.info("🔍 Audit catégorisations...")
    result = subprocess.run(
        ['python3', str(BASE_DIR / 'tool_categories_audit.py'), '--lines', '500'],
        capture_output=True, text=True
    )
    # Extraire résumé et divergences
    for line in result.stdout.split('\n'):
        stripped = line.lstrip()
        if stripped.startswith('⚠') or stripped.startswith('✓'):
            print(f"  {stripped}")

    # 4. Push comptes.xlsm
    seafile_path = get_seafile_path()
    shutil.copy2(local_path, seafile_path)
    logger.info(f"✓ Copié vers {seafile_path}")


def do_fallback():
    """Annule le dernier fetch et le dernier import

    Délègue entièrement à cpt_update.py --fallback qui:
    1. Purge les fichiers dans dropbox/ (préserve les dossiers SITE)
    2. Restaure les fichiers depuis archives/ vers dropbox/
    3. Restaure comptes.xlsm depuis le backup
    """
    logger.info("⏪ Rollback (fetch + import)")

    success = run_script('cpt_update.py', ['--fallback'])

    if not success:
        logger.error("❌ Échec du fallback")
        sys.exit(1)

    logger.info("✓ Rollback terminé")


def do_status():
    """Affiche l'état du système (erreurs/warnings + listing fichiers)"""
    logger.info("📊 État du système")

    # Lancer les vérifications
    results = [
        verify_backups(verbose=False),
        verify_journal(verbose=False),
        verify_archives(verbose=False),
        verify_dropbox(verbose=False),
        verify_logs(verbose=False),
        verify_debug(verbose=False),
    ]

    # Afficher uniquement les erreurs et warnings
    has_issues = False
    for result in results:
        if result.warnings or result.errors:
            has_issues = True
            status = "✓" if result.passed else "❌"
            print(f"\n{status} {result.name}")

            for msg in result.warnings:
                print(f"  ⚠️  {msg}")

            for msg in result.errors:
                print(f"  ❌ {msg}")

    if not has_issues:
        print("\n✓ Aucun problème détecté")

    # Listing des fichiers archives et dropbox
    print("\n" + "="*60)
    print("FICHIERS")
    print("="*60)

    # Archives
    archives_dir = BASE_DIR / "archives"
    if archives_dir.exists():
        print("\n📦 Archives:")
        for site_dir in sorted(archives_dir.iterdir()):
            if site_dir.is_dir():
                files = sorted(site_dir.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
                if files:
                    print(f"\n  {site_dir.name}/ ({len(files)} fichiers)")
                    for f in files[:5]:  # Afficher les 5 plus récents
                        mtime = datetime.fromtimestamp(f.stat().st_mtime).strftime('%Y-%m-%d %H:%M')
                        size = f.stat().st_size
                        print(f"    {mtime}  {size:>10,} octets  {f.name}")
                    if len(files) > 5:
                        print(f"    ... et {len(files)-5} autres fichiers")

    # Dropbox
    dropbox_dir = BASE_DIR / "dropbox"
    if dropbox_dir.exists():
        print("\n📥 Dropbox:")
        has_files = False
        for site_dir in sorted(dropbox_dir.iterdir()):
            if site_dir.is_dir():
                files = sorted(site_dir.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
                if files:
                    has_files = True
                    print(f"\n  {site_dir.name}/ ({len(files)} fichiers)")
                    for f in files:
                        mtime = datetime.fromtimestamp(f.stat().st_mtime).strftime('%Y-%m-%d %H:%M')
                        size = f.stat().st_size
                        print(f"    {mtime}  {size:>10,} octets  {f.name}")

        if not has_files:
            print("  Vide (normal après import)")

    print()


def main():
    parser = argparse.ArgumentParser(
        description='Script principal de gestion comptable',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples:
  %(prog)s                           # Collecte + Import tous les sites
  %(prog)s --sites SG                # Collecte + Import uniquement SG
  %(prog)s --sites SG,BG_GESTION     # Collecte + Import plusieurs sites
  %(prog)s --fetch-only              # Collecte uniquement (pas d'import)
  %(prog)s --update-only             # Import uniquement (pas de collecte)
  %(prog)s --reset                   # Réinitialisation complète du système
  %(prog)s --pull                    # Récupérer comptes.xlsm depuis Seafile
  %(prog)s --push                    # Pousser comptes.xlsm vers Seafile
  %(prog)s --fallback                # Annuler dernier fetch + import
  %(prog)s --status                  # Vérifier l'état du système
  %(prog)s -v                        # Mode verbeux

Workflow:
  1. Collecte depuis les sites web (cpt_fetch.py)
  2. Import dans Excel (cpt_update.py)
  3. Cotations (cpt_fetch_quotes.py)
        """)

    # Options workflow principal
    parser.add_argument('--sites',
                        metavar='SITE1,SITE2',
                        help='Liste de sites séparés par des virgules (ex: SG,BG_GESTION)')
    parser.add_argument('--fetch-only',
                        action='store_true',
                        help='Collecte uniquement (pas d\'import)')
    parser.add_argument('--update-only',
                        action='store_true',
                        help='Import uniquement (pas de collecte)')

    # Options gestion système
    parser.add_argument('--reset',
                        action='store_true',
                        help='Réinitialisation complète (pull Seafile + purge archives/dropbox/logs)')
    parser.add_argument('--reset-template',
                        action='store_true',
                        help='Réinitialisation template vierge (purge configs/données)')
    parser.add_argument('--pull',
                        action='store_true',
                        help='Récupérer comptes.xlsm depuis Seafile')
    parser.add_argument('--push',
                        action='store_true',
                        help='Pousser comptes.xlsm vers Seafile (avec vérification)')
    parser.add_argument('--force',
                        action='store_true',
                        help='Forcer --push malgré erreurs bloquantes')
    parser.add_argument('--fallback',
                        action='store_true',
                        help='Annuler dernier fetch + dernier import (purge dropbox + restore backup)')
    parser.add_argument('--status',
                        action='store_true',
                        help='Vérifier l\'état du système (appelle cpt_verify.py)')

    # Options import
    parser.add_argument('--all-soldes',
                        action='store_true',
                        help='Écrire tous les #Solde collectés (pas seulement ceux avec nouvelles opérations)')

    # Options générales
    parser.add_argument('-v', '--verbose',
                        action='store_true',
                        help='Mode verbeux')

    args = parser.parse_args()

    # Gestion des options système (exclusives - sortent immédiatement)
    if args.reset:
        do_reset()
        sys.exit(0)

    if args.reset_template:
        do_reset_template()
        sys.exit(0)

    if args.pull:
        do_pull()
        sys.exit(0)

    if args.push:
        do_push(force=args.force)
        sys.exit(0)

    if args.fallback:
        do_fallback()
        sys.exit(0)

    if args.status:
        do_status()
        sys.exit(0)

    # Vérifications workflow
    if args.fetch_only and args.update_only:
        logger.error("Options --fetch-only et --update-only incompatibles")
        sys.exit(1)

    # Phase 1: Collecte (sauf si --update-only)
    fetch_success = True
    if not args.update_only:
        fetch_args = []
        if args.sites:
            fetch_args.extend(['--sites', args.sites])
        if args.verbose:
            fetch_args.append('-v')

        fetch_success = run_script('cpt_fetch.py', fetch_args)

        if not fetch_success:
            logger.error("Échec de la collecte")
            if not args.fetch_only:
                logger.error("Import annulé (aucun nouveau fichier collecté)")
            sys.exit(1)

    # Phase 2: Import (sauf si --fetch-only)
    if not args.fetch_only:
        update_args = []
        if args.verbose:
            update_args.append('-v')
        if args.all_soldes:
            update_args.append('--all-soldes')

        # Note: cpt_update.py traite tous les fichiers dans dropbox/
        # Il n'a pas de filtre par site (il détecte automatiquement)
        update_success = run_script('cpt_update.py', update_args)

        if not update_success:
            logger.error("Échec de l'import")
            logger.error("Utilisez './cpt_update.py --fallback' pour annuler l'import")
            sys.exit(1)

        # Phase 3: Cotations (après import réussi)
        quotes_args = []
        if args.verbose:
            quotes_args.append('-v')
        quotes_success = run_script('cpt_fetch_quotes.py', quotes_args)

        if not quotes_success:
            logger.error("Échec mise à jour cotations (non bloquant)")
        # Les cotations ne sont pas bloquantes

    sys.exit(0)


if __name__ == "__main__":
    main()
