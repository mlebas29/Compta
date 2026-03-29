#!/usr/bin/env python3
"""
Mappings libellé → catégorie pour auto-catégorisation des opérations bancaires.

Format JSON: config_category_mappings.json (à côté de ce fichier)
Chaque entrée: {"pattern": "regex", "category": "catégorie", "ref": "-" (optionnel)}

Utilisation dans format scripts via inc_categorize.py
"""

import json
import re
import sys
from pathlib import Path

# ============================================================================
# CHARGEMENT DES PATTERNS DEPUIS JSON
# ============================================================================

_JSON_PATH = Path(__file__).parent / 'config_category_mappings.json'
_patterns_by_group = None  # Cache chargé au premier appel


def _load_patterns():
    """Charge les patterns depuis config_category_mappings.json.

    Retourne un dict {group_name: [(pattern, category, options), ...]}
    """
    global _patterns_by_group
    if _patterns_by_group is not None:
        return _patterns_by_group

    if not _JSON_PATH.exists():
        print(f"❌ {_JSON_PATH} introuvable", file=sys.stderr)
        sys.exit(1)

    try:
        with open(_JSON_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"❌ Erreur lecture {_JSON_PATH}: {e}", file=sys.stderr)
        sys.exit(1)

    result = {}
    for group_name, entries in data.items():
        patterns = []
        for entry in entries:
            pattern = entry['pattern']
            category = entry['category']
            options = {}
            if 'ref' in entry:
                options['ref'] = entry['ref']
            patterns.append((pattern, category, options))
        result[group_name] = patterns

    _patterns_by_group = result
    return _patterns_by_group


def reload_patterns():
    """Force le rechargement des patterns depuis le JSON (utile après modification GUI)."""
    global _patterns_by_group
    _patterns_by_group = None
    return _load_patterns()


# ============================================================================
# FONCTION DE CATÉGORISATION
# ============================================================================

def categorize(libelle, site=None):
    """Retourne la catégorie et les options d'une opération basée sur son libellé

    Args:
        libelle: Libellé de l'opération
        site: Nom du site (optionnel, pour patterns spécifiques)
              'SG', 'WISE', 'BB', etc.

    Returns:
        tuple: (catégorie, options_dict)
               catégorie = str (catégorie trouvée, ou '-' si aucune)
               options = dict {'ref': '-'} ou {}

    Example:
        >>> categorize("VIR Virement", "SG")
        ('-', {'ref': '-'})
        >>> categorize("CARTE 1234 LECLERC", "SG")
        ('Marché', {})
        >>> categorize("Opération inconnue", "SG")
        ('-', {})
    """
    if not libelle:
        return '-', {}

    patterns = _load_patterns()

    # Patterns spécifiques au site d'abord (priorité)
    site_patterns = patterns.get(site, [])

    # Chercher dans patterns site + génériques
    generic_patterns = patterns.get('GENERIC', [])
    all_patterns = site_patterns + generic_patterns

    for pattern, category, options in all_patterns:
        if re.search(pattern, libelle):
            return category, options

    return '-', {}  # Pas de catégorie trouvée → défaut AWK ligne 3


# ============================================================================
# FONCTION DE TEST (optionnel)
# ============================================================================

