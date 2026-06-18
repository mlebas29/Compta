"""
inc_formats.py — Constantes et fonctions de formats devise.

Source unique pour les formats numériques UNO et openpyxl. Les décimales et la
famille viennent du classeur (feuille Cotations, COTdecimales/COTfamille) =
source unique de vérité ; lues au point d'application via
inc_excel_schema.read_cotations_meta[_uno] puis build_formats_devise().
"""

# ============================================================================
# FORMATS DEVISE — décimales/famille lues du classeur (build_formats_devise)
# ============================================================================

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
        decimals = _DEFAULT_DECIMALS

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


def build_formats_devise(meta, style='uno'):
    """Construit {code: format} depuis un meta {code: {famille, decimals}}.

    meta provient du classeur (inc_excel_schema.read_cotations_meta[_uno]).
    EUR toujours inclus ; les entrées immobilier (noms longs, pas des devises)
    sont exclues. style : 'uno' ou 'openpyxl'.
    """
    result = {'EUR': devise_format('EUR', _DEFAULT_DECIMALS, style=style)}
    for code, info in meta.items():
        if code == 'EUR':
            continue
        if (info.get('famille') or '') == 'immobilier':
            continue
        result[code] = devise_format(code, info.get('decimals', _DEFAULT_DECIMALS), style=style)
    return result


def formats_devise_uno(doc, style='uno'):
    """{code: format} construit depuis le classeur ouvert en UNO."""
    from inc_excel_schema import read_cotations_meta_uno
    return build_formats_devise(read_cotations_meta_uno(doc), style=style)


def formats_devise_openpyxl(wb, style='openpyxl'):
    """{code: format} construit depuis le classeur ouvert en openpyxl."""
    from inc_excel_schema import read_cotations_meta
    return build_formats_devise(read_cotations_meta(wb), style=style)


FORMAT_EUR = devise_format('EUR', _DEFAULT_DECIMALS)
FORMAT_EUR_RED = devise_format('EUR', _DEFAULT_DECIMALS).replace(';\\-', ';[RED]\\-')
FORMAT_DATE = 'DD/MM/YY'
GRIS = 0xDCDCDC
GRIS_LEGACY_D5 = 0xD5D5D5  # ancien gris hérité — reconnu pour nettoyage uniquement
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
