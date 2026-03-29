#!/usr/bin/env python3
"""
Bibliothèque commune pour format scripts.

Fonctions utilitaires réutilisables :
- Filtrage temporel (max_days_back)
- Catégorisation automatique (via inc_category_mappings.py)
- Parsing dates multi-formats
- Lecture configuration
"""

from datetime import datetime, timedelta
from pathlib import Path
import configparser
import sys

# Import du module de mappings
try:
    import inc_category_mappings
except ImportError:
    print("⚠ inc_category_mappings.py manquant", file=sys.stderr)
    category_mappings = None


# ============================================================================
# FILTRAGE TEMPOREL
# ============================================================================

def filter_operations_by_date(operations, max_days_back=None, date_key='date'):
    """Filtre les opérations par date

    Args:
        operations: Liste de dicts contenant une clé date
                   [{'date': datetime(...), 'label': '...', ...}, ...]
        max_days_back: Nombre de jours max depuis aujourd'hui (None = pas de filtre)
        date_key: Nom de la clé contenant la date (défaut: 'date')

    Returns:
        Liste filtrée (même format que l'input)

    Example:
        >>> ops = [
        ...     {'date': datetime(2024, 1, 1), 'label': 'Old'},
        ...     {'date': datetime(2025, 12, 1), 'label': 'Recent'},
        ... ]
        >>> filtered = filter_operations_by_date(ops, max_days_back=90)
        >>> len(filtered)
        1
    """
    if not max_days_back:
        return operations

    cutoff = datetime.now() - timedelta(days=max_days_back)
    return [op for op in operations if op.get(date_key) and op[date_key] >= cutoff]


# ============================================================================
# CATÉGORISATION
# ============================================================================

def categorize_operation(libelle, site=None):
    """Catégorise une opération basée sur son libellé

    Wrapper vers inc_category_mappings.categorize()

    Args:
        libelle: Libellé de l'opération
        site: Nom du site (SG, WISE, BB, etc.)

    Returns:
        tuple: (catégorie, options)
               catégorie = str ('Virement', 'Frais bancaires', etc., ou '-' si non trouvée)
               options = dict ({'ref': '-'}, {'equiv': 'amount'}, etc.)

    Example:
        >>> cat, opts = categorize_operation("VIR Virement Marc", "SG")
        >>> cat
        'Virement'
        >>> opts
        {'ref': '-'}
        >>> cat, opts = categorize_operation("Opération inconnue", "SG")
        >>> cat
        '-'
    """
    if not inc_category_mappings:
        return '-', {}

    return inc_category_mappings.categorize(libelle, site)


# ============================================================================
# PARSING DATES
# ============================================================================

def parse_french_date(date_str):
    """Parse date format français DD/MM/YYYY

    Args:
        date_str: Date en format DD/MM/YYYY (ex: "25/12/2025")

    Returns:
        datetime object

    Example:
        >>> parse_french_date("25/12/2025")
        datetime.datetime(2025, 12, 25, 0, 0)
    """
    return datetime.strptime(date_str, '%d/%m/%Y')


def parse_iso_date(date_str):
    """Parse date format ISO YYYY-MM-DD

    Args:
        date_str: Date en format YYYY-MM-DD (ex: "2025-12-25")

    Returns:
        datetime object

    Example:
        >>> parse_iso_date("2025-12-25")
        datetime.datetime(2025, 12, 25, 0, 0)
    """
    return datetime.strptime(date_str, '%Y-%m-%d')


def format_french_date(dt):
    """Formate datetime en DD/MM/YYYY

    Args:
        dt: datetime object

    Returns:
        str: Date formatée DD/MM/YYYY

    Example:
        >>> format_french_date(datetime(2025, 12, 25))
        '25/12/2025'
    """
    if isinstance(dt, datetime):
        return dt.strftime('%d/%m/%Y')
    return ''


# ============================================================================
# CONFIGURATION
# ============================================================================

def get_max_days_back_from_config(config_file, site_name):
    """Lit max_days_back depuis config.ini

    Priorité:
    1. [SITE] max_days_back (override spécifique)
    2. [general] max_days_back (défaut global)
    3. None (pas de filtrage - backward compatible)

    Args:
        config_file: Path vers config.ini
        site_name: Nom du site (SG, WISE, BB, etc.)

    Returns:
        int ou None: Nombre de jours, ou None

    Example:
        >>> get_max_days_back_from_config(Path('config.ini'), 'WISE')
        90
    """
    if not Path(config_file).exists():
        return None

    config = configparser.ConfigParser()
    config.read(config_file)

    # Priorité 1 : override spécifique au site
    if config.has_section(site_name) and config.has_option(site_name, 'max_days_back'):
        return config.getint(site_name, 'max_days_back')

    # Priorité 2 : paramètre global
    if config.has_option('general', 'max_days_back'):
        return config.getint('general', 'max_days_back')

    # Priorité 3 : pas de filtrage
    return None


# ============================================================================
# TESTS
# ============================================================================

if __name__ == '__main__':
    print("Tests inc_categorize.py:")
    print()

    # Test 1: Filtrage dates
    print("Test 1: Filtrage temporel")
    ops = [
        {'date': datetime(2024, 1, 1), 'label': 'Very old'},
        {'date': datetime(2025, 10, 1), 'label': 'Old'},
        {'date': datetime(2025, 12, 20), 'label': 'Recent'},
    ]
    filtered = filter_operations_by_date(ops, max_days_back=90)
    print(f"  {len(ops)} opérations → {len(filtered)} après filtre 90 jours")
    print(f"  Opérations conservées: {[op['label'] for op in filtered]}")
    print()

    # Test 2: Catégorisation
    print("Test 2: Catégorisation")
    test_labels = [
        ("VIR Virement Marc", "SG"),
        ("CARTE 1234 LECLERC", "SG"),
        ("Frais Wise Assets Europe", "WISE"),
        ("POUR: VeraCash", "SG"),
    ]
    for label, site in test_labels:
        cat, opts = categorize_operation(label, site)
        print(f"  '{label[:30]:30}' → {cat:20} {opts}")
    print()

    # Test 3: Parsing dates
    print("Test 3: Parsing dates")
    dt1 = parse_french_date("25/12/2025")
    print(f"  parse_french_date('25/12/2025') → {dt1}")
    dt2 = parse_iso_date("2025-12-25")
    print(f"  parse_iso_date('2025-12-25') → {dt2}")
    formatted = format_french_date(dt1)
    print(f"  format_french_date({dt1}) → {formatted}")
    print()

    # Test 4: Configuration
    print("Test 4: Configuration")
    max_days = get_max_days_back_from_config(Path('config.ini'), 'WISE')
    print(f"  max_days_back pour WISE: {max_days}")
    max_days_global = get_max_days_back_from_config(Path('config.ini'), 'SG')
    print(f"  max_days_back pour SG: {max_days_global}")
    print()

    print("✓ Tests terminés")
