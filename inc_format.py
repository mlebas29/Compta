#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
inc_format.py - Fonctions communes pour les formatteurs de sites

Fournit les utilitaires partagés par tous les cpt_*_format.py
"""

import os
import sys
import zipfile
from pathlib import Path
from datetime import datetime, timedelta
import inc_categorize

# Flag TNR — positionné par cpt_update.py --TNR, jamais par variable d'environnement
TNR_MODE = False


def require_account(accounts, keyword, site, ignorecase=False):
    """Cherche un compte par mot-clé dans la liste. Erreur si absent.

    Args:
        accounts: liste de noms de comptes (str)
        keyword: mot-clé à chercher (ex: 'Titres', 'EUR')
        site: nom du site pour le message d'erreur (ex: 'BB')
        ignorecase: recherche insensible à la casse
    """
    if ignorecase:
        kw = keyword.lower()
        val = next((n for n in accounts if kw in n.lower()), None)
    else:
        val = next((n for n in accounts if keyword in n), None)
    if val is None:
        raise ValueError(
            f'config_accounts.json [{site}] : aucun compte contenant "{keyword}"')
    return val


def site_name_from_file(filepath):
    """Extrait le nom du site depuis le chemin du script appelant.

    Usage dans cpt_format_SITE.py :
        SITE = site_name_from_file(__file__)  # 'BB', 'SG', etc.
    """
    return Path(filepath).stem.replace('cpt_format_', '')


def get_file_date(filepath):
    """Date de modification du fichier source, formatée DD/MM/YYYY.

    Proxy pour la date de collecte (fetch) : le fetcher crée/télécharge
    le fichier au moment de la collecte, donc mtime ≈ date du fetch.
    """
    mtime = os.path.getmtime(filepath)
    return datetime.fromtimestamp(mtime).strftime('%d/%m/%Y')


def parse_french_date_from_iso(iso_date):
    """Convertit une date ISO en format français DD/MM/YYYY.

    Args:
        iso_date: Date au format 'YYYY-MM-DD HH:MM:SS' ou 'YYYY-MM-DD'

    Returns:
        Date au format 'DD/MM/YYYY' ou la valeur originale si parsing échoue
    """
    try:
        dt = datetime.strptime(iso_date, '%Y-%m-%d %H:%M:%S')
    except ValueError:
        try:
            dt = datetime.strptime(iso_date, '%Y-%m-%d')
        except ValueError:
            return iso_date
    return dt.strftime('%d/%m/%Y')


def filter_ops_by_date(operations, max_days_back, verbose=False, site_name=None, logger=None):
    """Filtre les opérations par date (garde les N derniers jours).

    Args:
        operations: Liste de tuples (date en position 0, format DD/MM/YYYY)
        max_days_back: Nombre de jours max depuis aujourd'hui
        verbose: Mode verbose
        site_name: Nom du site pour les logs
        logger: Logger optionnel

    Returns:
        Liste filtrée de tuples
    """
    # TNR désactive le filtrage (dates de test fixes, sinon exclues après max_days_back)
    if TNR_MODE or not max_days_back or not operations:
        return operations

    cutoff_date = datetime.now() - timedelta(days=max_days_back)
    filtered = []

    for op in operations:
        try:
            date_str = op[0]  # Date en position 0
            op_date = datetime.strptime(date_str, '%d/%m/%Y')
            if op_date >= cutoff_date:
                filtered.append(op)
        except (ValueError, IndexError):
            # Garder les lignes sans date valide (ex: #Solde ajouté après)
            filtered.append(op)

    if len(filtered) != len(operations):
        msg = f"Filtrage date: {len(operations)} → {len(filtered)} opérations"
        if logger:
            logger.verbose(msg)
        elif verbose and site_name:
            print(f"[{site_name}] {msg}", file=sys.stderr)

    return filtered


def _validate_file(f, site_name, logger=None):
    """Vérifie l'intégrité d'un fichier avant traitement.

    Returns:
        True si le fichier est valide, False si dégradé (warning émis).
    """
    name = f.name

    def _warn(msg):
        if logger:
            logger.warning(f"{name}: {msg}")
        else:
            tag = site_name or 'FORMAT'
            print(f"⚠ [{tag}] {name}: {msg}", file=sys.stderr)

    # Fichier vide (toutes extensions)
    if f.stat().st_size == 0:
        _warn("fichier vide (0 octets)")
        return False

    suffix = f.suffix.lower()

    # PDF : magic bytes %PDF
    if suffix == '.pdf':
        try:
            header = f.read_bytes()[:4]
            if header != b'%PDF':
                _warn("PDF corrompu")
                return False
        except Exception:
            pass

    # ZIP : intégrité + contenu non vide
    elif suffix == '.zip':
        if not zipfile.is_zipfile(f):
            _warn("ZIP corrompu")
            return False
        try:
            with zipfile.ZipFile(f) as zf:
                if not zf.namelist():
                    _warn("ZIP vide")
                    return False
        except zipfile.BadZipFile:
            _warn("ZIP corrompu")
            return False

    # XLSX : ouverture openpyxl
    elif suffix == '.xlsx':
        try:
            import openpyxl
            openpyxl.load_workbook(f, read_only=True, data_only=True).close()
        except Exception:
            _warn("XLSX corrompu")
            return False

    return True


def process_files(site_dir, handlers, verbose=False, site_name=None, logger=None):
    """Boucle générique sur les fichiers d'un répertoire site.

    Args:
        site_dir: Répertoire à scanner (Path ou str)
        handlers: Liste de tuples (pattern, fonction, cible)
            - pattern: glob pattern (ex: '*.pdf', '*.PDF')
            - fonction: callable qui prend un Path et retourne une liste
            - cible: 'ops' pour opérations, 'pos' pour positions
        verbose: Mode verbose
        site_name: Nom du site pour les logs (optionnel)
        logger: Logger optionnel

    Returns:
        tuple: (operations, positions) - listes de tuples

    Exemple:
        handlers = [
            ('*.pdf', process_pdf, 'ops'),
            ('*.csv', process_csv, 'ops'),
            ('positions*.csv', process_positions, 'pos'),
        ]
        ops, pos = process_files(site_dir, handlers, verbose=True)
    """
    site_dir = Path(site_dir)
    all_ops = []
    all_pos = []
    processed_files = set()

    for pattern, func, target in handlers:
        for f in site_dir.glob(pattern):
            # Skip fichiers déjà formatés ou déjà traités par un autre pattern
            if '_formatted' in f.name or '_temp' in f.name:
                continue
            # Clé (fichier, fonction) : permet au même fichier d'être traité
            # par des handlers différents (ex: PDF → ops ET pos)
            process_key = (f, func)
            if process_key in processed_files:
                continue
            processed_files.add(process_key)

            if not _validate_file(f, site_name, logger):
                continue

            try:
                if logger:
                    logger.verbose(f"{pattern}: {f.name}")
                elif verbose and site_name:
                    print(f"[{site_name}] {pattern}: {f.name}", file=sys.stderr)

                result = func(f)

                # Convertir les lignes CSV en tuples si nécessaire
                tuples = []
                for item in result:
                    if isinstance(item, str):
                        fields = item.split(';')
                        tuples.append(tuple(fields))
                    elif isinstance(item, (list, tuple)):
                        tuples.append(tuple(item))
                    else:
                        tuples.append(item)

                # Ajouter à la bonne liste
                if target == 'ops':
                    all_ops.extend(tuples)
                else:
                    all_pos.extend(tuples)

            except Exception as e:
                if logger:
                    logger.warning(f"Erreur {f.name}: {e}")
                else:
                    print(f"⚠ [{site_name or 'FORMAT'}] Erreur {f.name}: {e}", file=sys.stderr)

    # Filtrage par date centralisé (si configuré pour ce site)
    if site_name:
        config_file = Path(__file__).parent / 'config.ini'
        max_days_back = inc_categorize.get_max_days_back_from_config(config_file, site_name)
        if max_days_back:
            all_ops = filter_ops_by_date(all_ops, max_days_back, verbose, site_name, logger)

    return all_ops, all_pos


def lines_to_tuples(lines, expected_fields=None):
    """Convertit des lignes CSV en tuples.

    Args:
        lines: Liste de str (lignes CSV) ou tuples
        expected_fields: Nombre de champs attendus (filtre les autres)

    Returns:
        Liste de tuples
    """
    result = []
    for item in lines:
        if isinstance(item, str):
            fields = tuple(item.split(';'))
        else:
            fields = tuple(item)

        if expected_fields is None or len(fields) == expected_fields:
            result.append(fields)
    return result


def log_csv_debug(site_name, operations, positions, logger=None):
    """Écrit les tuples en CSV pour debug.

    Fichiers créés dans logs/debug/:
    - {site}_ops_debug.csv (opérations 10 champs)
    - {site}_pos_debug.csv (positions 5 champs)

    Args:
        site_name: Nom du site (ex: 'BB', 'SG', 'KRAKEN')
        operations: Liste de tuples opérations (10 champs)
        positions: Liste de tuples positions (5 champs)
        logger: Logger optionnel pour messages verbose
    """
    debug_dir = Path(__file__).parent / 'logs' / 'debug'
    debug_dir.mkdir(parents=True, exist_ok=True)

    # Opérations
    if operations:
        ops_file = debug_dir / f'{site_name}_ops_debug.csv'
        with open(ops_file, 'w', encoding='utf-8') as f:
            f.write('Date;Libellé;Montant;Devise;Equiv;Réf;Catégorie;Compte;Sous-compte;Commentaire\n')
            for op in operations:
                f.write(';'.join(str(x) for x in op) + '\n')
        if logger:
            logger.verbose(f"Debug CSV: {ops_file}")

    # Positions
    if positions:
        pos_file = debug_dir / f'{site_name}_pos_debug.csv'
        with open(pos_file, 'w', encoding='utf-8') as f:
            f.write('Date;Ligne;Montant;Compte;Sous-compte\n')
            for pos in positions:
                f.write(';'.join(str(x) for x in pos) + '\n')
        if logger:
            logger.verbose(f"Debug CSV: {pos_file}")


def cli_main(format_site_func):
    """Point d'entrée CLI générique pour les formatteurs.

    Usage dans chaque formatteur:
        if __name__ == '__main__':
            from inc_format import cli_main
            cli_main(format_site)
    """
    from inc_logging import Logger

    import sys
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('.')
    site_dir = path if path.is_dir() else path.parent

    # Extraire le nom du site depuis le nom du module appelant
    import inspect
    caller = inspect.stack()[1]
    module_name = Path(caller.filename).stem  # ex: cpt_format_BB
    site_name = module_name.replace('cpt_format_', '') if 'cpt_format_' in module_name else 'FORMAT'

    logger = Logger(site_name, verbose=True)
    ops, pos = format_site_func(site_dir, verbose=True, logger=logger)
    for op in ops:
        print(';'.join(str(x) for x in op))
    for p in pos:
        print(';'.join(str(x) for x in p), file=sys.stderr)


def verify_dropbox_files(site_dir, site_name):
    """Vérifie les fichiers dropbox contre le profil attendu.

    Args:
        site_dir: Répertoire dropbox/SITE/ (Path ou str)
        site_name: Nom du site (ex: 'SG', 'DEGIRO')

    Returns:
        Liste de warnings (strings). Liste vide si tout est OK.
    """
    import fnmatch
    from config_site_files import SITE_FILES

    import os
    site_dir = Path(site_dir)
    warnings = []

    # Contexte test → pas de vérification (patterns prod ≠ fichiers test)
    if TNR_MODE or 'test_data' in str(site_dir) or '/tnr/' in str(site_dir):
        return warnings

    # Site non configuré ou MANUEL → pas de vérification
    if site_name not in SITE_FILES:
        return warnings

    patterns = SITE_FILES[site_name]

    # Lister tous les fichiers présents (ignorer _temp, _formatted)
    all_files = [f.name for f in site_dir.iterdir()
                 if f.is_file() and '_temp' not in f.name and '_formatted' not in f.name]

    # Pour chaque pattern, trouver les fichiers qui matchent
    pattern_matches = {}  # pattern -> liste de fichiers
    matched_files = set()

    for pattern, matching, cardinality in patterns:
        matches = []
        for filename in all_files:
            if matching == 'exact':
                if filename == pattern:
                    matches.append(filename)
            else:  # glob
                if fnmatch.fnmatch(filename, pattern):
                    matches.append(filename)

        pattern_matches[pattern] = matches
        matched_files.update(matches)

    # 1. Fichiers intrus (ne matchent aucun pattern)
    for filename in all_files:
        if filename not in matched_files:
            warnings.append(f"[{site_name}] Fichier inattendu: {filename}")

    # 2. Fichiers manquants (cardinalité 1 ou 1+ sans match)
    for pattern, matching, cardinality in patterns:
        matches = pattern_matches[pattern]
        if cardinality in ('1', '1+') and len(matches) == 0:
            warnings.append(f"[{site_name}] Fichier manquant: {pattern}")

    # 3. Surnuméraires (cardinalité 1 ou 0-1 avec plusieurs matches)
    for pattern, matching, cardinality in patterns:
        matches = pattern_matches[pattern]
        if cardinality in ('1', '0-1') and len(matches) > 1:
            files_list = ', '.join(sorted(matches))
            warnings.append(f"[{site_name}] Plusieurs fichiers pour {pattern}: {files_list}")

    return warnings


def select_file_for_pattern(site_dir, pattern, matching, files):
    """Sélectionne un fichier parmi plusieurs (le plus récent).

    Args:
        site_dir: Répertoire dropbox/SITE/ (Path)
        pattern: Le pattern concerné
        matching: 'exact' ou 'glob'
        files: Liste des fichiers matchant le pattern

    Returns:
        Le fichier sélectionné (le plus récent par mtime)
    """
    site_dir = Path(site_dir)
    if len(files) <= 1:
        return files[0] if files else None

    # Sélectionner le plus récent
    files_with_mtime = [(f, (site_dir / f).stat().st_mtime) for f in files]
    files_with_mtime.sort(key=lambda x: x[1], reverse=True)
    return files_with_mtime[0][0]
