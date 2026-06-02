"""Helpers pour les drill cells (cellules avec format `@" ▼"`).

Doctrine : le suffixe ▼ est un *décor* du format, pas de la valeur stockée.
La valeur brute reste le code pur (ex: 'EUR'), le format `@" ▼"` ajoute le
suffixe à l'affichage. `cell.getString()` UNO retourne la valeur **formatée**,
donc 'EUR ▼' — il faut stripper le suffixe avant comparaison ou recopie,
sinon une réécriture re-pose le format → 'EUR ▼ ▼' (double triangle).
"""
import re as _re


def strip_drill_suffix(value, fmt_str=None):
    """Strip le suffixe ▼ (ou tout suffixe text constant d'un format `@"..."`).

    Args:
        value:   valeur lue via cell.getString() (donc formatée).
        fmt_str: format de la cellule (optionnel). Si fourni, parse les
                 préfixes/suffixes text constants de la section `@"..."`.
                 Sinon, strip simplement '▼' final + espaces autour.

    Returns:
        La valeur brute (sans préfixe/suffixe text).
    """
    if not value:
        return value

    # Mode simple : strip '▼' final
    if fmt_str is None:
        if value.endswith('▼'):
            return value[:-1].rstrip()
        return value

    # Mode complet : parse la section text du format
    if '@' not in fmt_str:
        return value
    sections = fmt_str.split(';')
    text_section = sections[3] if len(sections) >= 4 else sections[0]
    if '@' not in text_section:
        return value
    before, after = text_section.split('@', 1)
    prefix_m = _re.match(r'^"([^"]*)"', before.strip())
    suffix_m = _re.match(r'^\s*"([^"]*)"', after)
    prefix = prefix_m.group(1) if prefix_m else ''
    suffix = suffix_m.group(1) if suffix_m else ''
    if prefix and value.startswith(prefix):
        value = value[len(prefix):]
    if suffix and value.endswith(suffix):
        value = value[:-len(suffix)]
    return value
