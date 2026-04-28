"""
inc_formats.py — Constantes et fonctions de formats devise.

Source unique pour les formats numériques UNO et openpyxl,
générés depuis config_cotations.json.
"""

import json
from pathlib import Path

# ============================================================================
# FORMATS DEVISE — source unique (générés depuis config_cotations.json)
# ============================================================================

_CONFIG_PATH = Path(__file__).parent / 'config_cotations.json'
_DEFAULT_DECIMALS = 2  # fiat par défaut


def devise_format(code, decimals=None, style='uno'):
    """Génère le format nombre pour une devise.

    Args:
        code: code devise (EUR, USD, SAT, OrPr, ...)
        decimals: nombre de décimales (None = lire config_cotations.json, fallback 2)
        style: 'uno' (format FR : #\xa0##0,00) ou 'openpyxl' (format US : #,##0.00)

    Returns:
        Format string. EUR inclut le positif;négatif.
    """
    if decimals is None:
        decimals = _load_decimals().get(code, _DEFAULT_DECIMALS)

    if style == 'uno':
        dec_part = ',' + '0' * decimals if decimals > 0 else ''
        if code == 'EUR':
            base = f'#\xa0##0{dec_part} [$€-40C]'
            return f'{base};\\-{base}'
        return f'#\xa0##0{dec_part} [${code}]'
    else:  # openpyxl
        dec_part = '.' + '0' * decimals if decimals > 0 else ''
        if code == 'EUR':
            base = f'#,##0{dec_part}\\ [$€-40C]'
            return f'{base};\\-{base}'
        return f'#,##0{dec_part}\\ [${code}]'


_decimals_cache = None


def _load_decimals():
    """Charge les décimales depuis config_cotations.json (avec cache)."""
    global _decimals_cache
    if _decimals_cache is None:
        _decimals_cache = {}
        if _CONFIG_PATH.exists():
            with open(_CONFIG_PATH) as f:
                cfg = json.load(f)
            for code, entry in cfg.items():
                if 'decimals' in entry:
                    _decimals_cache[code] = entry['decimals']
    return _decimals_cache


def _build_formats_devise():
    """Construit le dict FORMATS_DEVISE depuis config_cotations.json.

    Exclut les entrées immobilier (noms longs, pas des devises).
    Les cotations pures (XAU, XAG, BTC) sont incluses — inoffensives.
    """
    decimals = _load_decimals()
    result = {'EUR': devise_format('EUR', _DEFAULT_DECIMALS)}
    cfg = {}
    if _CONFIG_PATH.exists():
        with open(_CONFIG_PATH) as f:
            cfg = json.load(f)
    for code, dec in decimals.items():
        if code == 'EUR':
            continue
        famille = cfg.get(code, {}).get('famille', '')
        if famille == 'immobilier':
            continue
        result[code] = devise_format(code, dec)
    return result


FORMATS_DEVISE = _build_formats_devise()
FORMAT_EUR = FORMATS_DEVISE['EUR']
FORMAT_EUR_RED = devise_format('EUR', _DEFAULT_DECIMALS).replace(';\\-', ';[RED]\\-')
FORMAT_DATE = 'DD/MM/YY'
GRIS = 0xDCDCDC
GRIS_BLANC = 0xEAEAEA  # gris devise sur fond blanc (lignes données PVL)
GRIS_BEIGE = 0xDED9C0  # gris devise sur fond beige clair (pieds PVL)
BLANC = 0xFFFFFF
BEIGE_CLAIR = 0xEEEBDB  # alternance lignes data + col A (template xlsm)

# ============================================================================
# CHARTE GRAPHIQUE v3.6 — palette et règles par rôle
# ============================================================================
# Palette fonds (int 0xRRGGBB — format UNO natif)
TETE_FILL           = 0xD2C195   # beige foncé : tête tableau
PIED_FILL           = 0xEEEBDB   # beige clair : pied tableau (même que COL_REF)
COL_REF_FILL        = 0xEEEBDB   # beige clair : colonne ref data
DATA_FILL           = 0xFFFFFF   # blanc : zone data
JAUNE               = 0xFFFF00   # annotation user (intouchable, partout)
ALARM_FILL          = 0xFFC7CE   # alarme contrôle ✗ (rouge clair, dxf CF ou fond direct)
WARN_FILL           = 0xFFEB9C   # warning contrôle ⚠ (jaune-orange, gravité moindre que alarme)

# Bordures
HAIR_COLOR          = 0xD2C195   # grille hair D2C195 sur data blanche
PIED_BORDER_COLOR   = 0x6C2E24   # brun foncé : BORDURE_PIED (thick top 1re ligne pied)

# Exceptions tolérées en data (ne sont pas des violations, ne doivent pas être écrasées)
GAMME_BEIGE = {TETE_FILL, PIED_FILL}            # effets de section
GRIS_DEVISE = {GRIS_BLANC, GRIS_BEIGE}          # devise étrangère
EXC_DATA = GAMME_BEIGE | GRIS_DEVISE | {JAUNE, ALARM_FILL, WARN_FILL}  # data / col ref
# Fonds tolérés en tête/pied (remplacement par gris foncé pour colonne devise étrangère)
EXC_HEAD = {TETE_FILL, GRIS_BEIGE, JAUNE, ALARM_FILL, WARN_FILL}
EXC_FOOT = {PIED_FILL, GRIS_BEIGE, JAUNE, ALARM_FILL, WARN_FILL}

# Largeurs bordures UNO (1/100 mm) — mapping OOXML
HAIR_WIDTH_UNO      = 2          # hair   ≈ 0,05 pt
THICK_WIDTH_UNO     = 88         # thick  ≈ 2,5  pt
