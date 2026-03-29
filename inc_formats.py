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
BLANC = 0xFFFFFF
