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
        >>> categorize("VIR Virement Marc", "SG")
        ('-', {'ref': '-'})
        >>> categorize("CARTE 1234 LECLERC", "SG")
        ('Marché', {})
        >>> categorize("POUR: VeraCash", "SG")
        ('@Change', {'ref': '-'})
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

if __name__ == '__main__':
    # Tests unitaires
    test_cases = [
        # WISE
        ("Argent envoyé à Marc", "WISE", "-", {'ref': '-'}),
        ("Frais Wise Assets Europe", "WISE", "Frais bancaires", {}),

        # SG
        ("PRLV ALLIANZ", "SG", "ALLIANZ", {}),
        ("CARTE 1234 LECLERC BREST", "SG", "-", {}),
        ("RETRAIT DAB SG", "SG", "-", {'ref': '-'}),
        ("POUR: VeraCash", "SG", "@Change", {'ref': '-'}),
        ("BG GESTION virement", "SG", "-", {'ref': '-'}),
        ("LECLERC BREST", "SG", "-", {}),
        ("MUTUALITE SOCIALE AGRICOLE D'ILE DE FR ANCE MOTIF: AV", "SG", "MSA retraite", {}),

        # BB
        ("ACHAT ACCOR", "BB", "@Achat titres", {'ref': '-'}),
        ("VENTE THALES", "BB", "@Vente titres", {'ref': '-'}),
        ("COUPON OBLIGATIONS", "BB", "Coupon", {}),
        ("VIR Virement depuis XXX", "BB", "-", {'ref': '-'}),

        # BG_GESTION
        ("Notre règlement par virement :", "BG_GESTION", "-", {'ref': '-'}),
        ("Loyer (01) 2025", "BG_GESTION", "Yvelles", {}),
        ("Honoraires gestion", "BG_GESTION", "Yvelles", {}),
        ("APPEL DE FONDS", "BG_GESTION", "Yvelles", {}),

        # PEE
        ("Modification de placements du fonds HSBC", "PEE", "@Arbitrage titres", {}),
        ("INVESTISSEMENT EMPLOYEUR", "PEE", "Syngenta", {}),
        ("Remboursement partiel", "PEE", "-", {'ref': '-'}),

        # YUH
        ("E.Leclerc", "YUH", "-", {}),
        ("TotalEnergies", "YUH", "Transport", {}),
        ("Pharmacie LOUEDEC", "YUH", "Santé", {}),
        ("Virement de MR OU MME MARC LEBAS", "YUH", "-", {'ref': '-'}),
        ("GAB PLOUDALMEZEAU", "YUH", "-", {'ref': '-'}),
        ("CHINA TOWN", "YUH", "Restaurant", {}),
        ("Intérêts sur dépôts", "YUH", "Intérêts", {}),
    ]

    print(f"Source: {_JSON_PATH}")
    print(f"JSON existe: {_JSON_PATH.exists()}")
    print()
    print("Tests de catégorisation:")
    print()
    passed = 0
    failed = 0

    for libelle, site, expected_cat, expected_opts in test_cases:
        cat, opts = categorize(libelle, site)
        if cat == expected_cat and opts == expected_opts:
            status = "✓"
            passed += 1
            print(f"{status} {libelle[:40]:40} ({site:12}) → {cat:20} {opts}")
        else:
            status = "✗"
            failed += 1
            print(f"{status} {libelle[:40]:40} ({site:12})")
            print(f"     Attendu: {expected_cat:20} {expected_opts}")
            print(f"     Obtenu:  {cat:20} {opts}")

    print()
    print(f"Résultats: {passed} passés, {failed} échoués")
