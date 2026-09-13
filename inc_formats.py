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


# ============================================================================
# RÈGLES CELLULE — feuille Opérations (#208) : format conditionnel + validation
# ============================================================================
# Définition UNIQUE, par colonne : plage nommée (bornée, ligne ⚓ incluse),
# prédicat du format conditionnel, style, validation de données. Trois
# appelants re-posent ces règles idempotemment — un seul morceau par colonne,
# en écrasant les miettes : l'import (à chaque run, coût nul),
# `tool_fix_formats --cellules` (à la demande), la migration (pose initiale).
# Écrivain = openpyxl (quelques ms) ; jamais LibreOffice depuis l'import.
#
# Pourquoi re-poser : l'import ajoute en fin de plage ; openpyxl (tool_purge)
# déplace les lignes sans déplacer les plages de format ; et LibreOffice
# TRONQUE la plage d'une validation à la sauvegarde (mesuré s.238 : G4:G9983
# → G4:G4271, soit la zone utilisée + 1000). Une plage posée pleine sur la
# plage nommée est immune aux deux premières causes ; la troisième exige la
# repose — d'où l'import comme appelant systématique.
#
# Prédicats = ceux des verdicts de la feuille Contrôles (une définition,
# trois usages : verdict, localisation, prévention) :
#   - opération réelle = date NUMÉRIQUE (la ligne ⚓ et les lignes vides ne
#     s'allument jamais) ;
#   - catégorie : vide, ou absente de CATnom — hors méta-catégories `#…`
#     (plage Spéciale) — miroir des sous-lignes Manquantes / Inconnues ;
#   - compte : vide (sauf méta-opération `#…`, ex. #Balance), ou absent
#     d'AVRintitulé — miroir d'INCONNUS (L76) ;
#   - devise : vide (sauf méta-opération), ou absente de COTcode — miroir
#     d'INCONNUS (terme devises, v5.32.0) ;
#   - date : hors [01/01/2020 ; 31/12/année_courante] — miroir de DIVERS ;
#   - réf. `-` : non apparié (surlignage historique, jaune pâle).
# COUNTIF est insensible à la casse, comme les SUMIFS/COUNTIF des verdicts :
# une graphie divergente n'est une erreur pour aucun des trois usages.
#
# Validations = par FORMULE (« Arrêter », cellule vide admise), pas par liste :
# une liste ne sait ni filtrer une plage (blancs, ⚓, biens) ni tolérer les
# méta-catégories `#…` (décision Marc s.238). L'autocomplétion de Calc propose.
#
# Placeholders des formules : {c} = cellule de la colonne ($G4, ligne
# relative = 1re ligne de la plage), {date} / {cat} = cellules date / catégorie
# de la même ligne.

REF_FILL = 0xFFFC98   # Réf. `-` = non apparié (jaune pâle, style hérité)

OP_CELL_RULES = (
    {
        'nr': 'OPdate', 'label': 'Date',
        'cf': ('formula', 'AND(ISNUMBER({c}),OR({c}<DATE(2020,1,1),'
                          '{c}>DATE(année_courante,12,31)))'),
        'fill': ALARM_FILL,
        'dv': {'formula1': 'AND(ISNUMBER({c}),{c}>=DATE(2020,1,1),{c}<=DATE(année_courante,12,31))',
               'errorTitle': 'Date hors période',
               'error': "La date doit être comprise entre le 01/01/2020 et le 31/12 "
                        "de l'année courante (contrôle DIVERS de la feuille Contrôles)."},
    },
    {
        'nr': 'OPdevise', 'label': 'Devise',
        'cf': ('formula', 'AND(ISNUMBER({date}),OR(AND({c}="",LEFT({cat},1)<>"#"),'
                          'AND({c}<>"",COUNTIF(COTcode,{c})=0)))'),
        'fill': ALARM_FILL,
        'dv': {'formula1': 'COUNTIF(COTcode,{c})>0',
               'errorTitle': 'Devise inconnue',
               'error': "Saisis un code devise de la feuille Cotations (colonne Code) "
                        "— ou ajoute la devise d'abord dans Cotations."},
    },
    {
        'nr': 'OPréf', 'label': 'Réf.',
        'cf': ('cellIs', '"-"'),
        'fill': REF_FILL,
        'dv': None,
    },
    {
        'nr': 'OPcatégorie', 'label': 'Catégorie',
        'cf': ('formula', 'AND(ISNUMBER({date}),LEFT({c},1)<>"#",'
                          'OR({c}="",COUNTIF(CATnom,{c})=0))'),
        'fill': ALARM_FILL,
        'dv': {'formula1': 'OR(LEFT({c},1)="#",COUNTIF(CATnom,{c})>0)',
               'errorTitle': 'Catégorie inconnue',
               'error': "Saisis une catégorie de la feuille Budget (colonne Catégories) "
                        "ou une méta-catégorie #… — ou ajoute-la d'abord dans Budget."},
    },
    {
        'nr': 'OPcompte', 'label': 'Compte',
        'cf': ('formula', 'AND(ISNUMBER({date}),OR(AND({c}="",LEFT({cat},1)<>"#"),'
                          'AND({c}<>"",COUNTIF(AVRintitulé,{c})=0)))'),
        'fill': ALARM_FILL,
        # Saisie = comptes SUIVIS (table CTRL1, entretenue par la GUI : ni clos ni
        # bien sans devise). Le verdict INCONNUS garde AVRintitulé (un compte clos
        # porte des opérations valides).
        'dv': {'formula1': 'COUNTIF(CTRL1compte,{c})>0',
               'errorTitle': 'Compte inconnu',
               'error': "Saisis un compte suivi (feuille Avoirs, avec devise) "
                        "— ou crée-le d'abord dans Avoirs."},
    },
)


def _hex6(color):
    """0xRRGGBB → 'RRGGBB'."""
    return f'{color:06X}'


def _dxf_fill_hex(rule):
    """Couleur de fond (6 hex, majuscules) du style d'une règle CF openpyxl, ou ''.
    Les dxf écrits par LibreOffice et openpyxl portent la couleur en bgColor ;
    fgColor accepté par tolérance (cf. tool_fix_formats._read_alarm_sqrefs)."""
    dxf = getattr(rule, 'dxf', None)
    fill = getattr(dxf, 'fill', None) if dxf is not None else None
    if fill is None:
        return ''
    for attr in ('bgColor', 'fgColor'):
        col = getattr(fill, attr, None)
        rgb = getattr(col, 'rgb', None)
        if isinstance(rgb, str) and len(rgb) >= 6:
            return rgb[-6:].upper()
    return ''


def _ranges_touch_col(sqref, col_idx):
    """Vrai si l'une des plages de `sqref` (MultiCellRange ou str) couvre la colonne."""
    from openpyxl.worksheet.cell_range import MultiCellRange
    for rng in MultiCellRange(str(sqref)).ranges:
        if rng.min_col <= col_idx <= rng.max_col:
            return True
    return False


def _expand(body, letter, start, date_letter, cat_letter):
    return (body.replace('{c}', f'${letter}{start}').replace('{date}', f'${date_letter}{start}')
                .replace('{cat}', f'${cat_letter}{start}'))


def _cf_target(rule, letter, start, date_letter, cat_letter):
    """(type, formula, operator) attendus pour une règle."""
    kind, body = rule['cf']
    body = _expand(body, letter, start, date_letter, cat_letter)
    if kind == 'cellIs':
        return 'cellIs', body, 'equal'
    return 'expression', body, None


def _dv_conform(dv, spec, formula, letter, start, min_end):
    """La validation openpyxl `dv` (formule attendue `formula`, titre/message de `spec`)
    couvre-t-elle la colonne ?

    Plage : même début, fin ≥ `min_end` (dernière ligne utilisée de la feuille)
    — LibreOffice TRONQUE la plage à la zone utilisée + 1000 à chaque
    sauvegarde (mesuré s.238) : exiger la plage nommée entière ferait re-poser
    à chaque sonde pour rien ; ce qui compte est que toute ligne existante soit
    couverte. formula2 d'une liste ignoré (LibreOffice y réécrit '0')."""
    from openpyxl.worksheet.cell_range import MultiCellRange
    ranges = list(MultiCellRange(str(dv.sqref)).ranges)
    if len(ranges) != 1:
        return False
    rng = ranges[0]
    if (rng.min_col != rng.max_col or rng.min_row != start or rng.max_row < min_end
            or dv.type != 'custom' or (dv.formula1 or '') != formula):
        return False
    return (dv.errorStyle == 'stop' and bool(dv.showErrorMessage)
            and bool(dv.allow_blank)
            and (dv.errorTitle or '') == spec['errorTitle']
            and (dv.error or '') == spec['error'])


def apply_operations_cell_rules(wb, apply=True):
    """Pose (apply=True) ou sonde (apply=False) les règles cellule d'Opérations.

    Pour chaque colonne d'OP_CELL_RULES : UN format conditionnel et, s'il est
    défini, UNE validation, sur la plage nommée entière. Tout format ou
    validation existant sur la colonne est retiré (miettes héritées, formats
    morts comme « Hors compte »). Les autres colonnes (B2 ✗/⚠…) sont intactes.

    Args:
        wb: classeur openpyxl chargé SANS data_only (keep_vba pour un .xlsm).
        apply: False = ne modifie rien, retourne seulement ce qui changerait.

    Returns:
        list[str] des changements (vide = classeur conforme). Idempotent :
        un second appel après pose retourne [].
    """
    from openpyxl.formatting.rule import CellIsRule, FormulaRule
    from openpyxl.formatting.formatting import ConditionalFormattingList
    from openpyxl.styles import PatternFill
    from openpyxl.worksheet.datavalidation import DataValidation
    from inc_excel_schema import SHEET_OPERATIONS, ColResolver

    if SHEET_OPERATIONS not in wb.sheetnames:
        return []
    ws = wb[SHEET_OPERATIONS]
    cr = ColResolver.from_openpyxl(wb)
    if 'OPdate' not in cr._cols:
        return []
    date_letter = cr.letter('OPdate')
    cat_letter = cr.letter('OPcatégorie') if 'OPcatégorie' in cr._cols else date_letter
    changes = []

    for rule in OP_CELL_RULES:
        nr = rule['nr']
        if nr not in cr._cols:
            continue
        start, end = cr.rows(nr)
        if start is None:
            continue
        letter, col_idx = cr.letter(nr), cr.col(nr)
        sqref = f'{letter}{start}:{letter}{end}'
        fill_hex = _hex6(rule['fill'])
        t_type, t_formula, t_op = _cf_target(rule, letter, start, date_letter, cat_letter)

        # --- format conditionnel : existant sur la colonne vs cible ---
        existing = [(cf, ws.conditional_formatting[cf]) for cf in ws.conditional_formatting
                    if _ranges_touch_col(cf.sqref, col_idx)]
        conform = False
        if len(existing) == 1 and str(existing[0][0].sqref) == sqref:
            rules = existing[0][1]
            if len(rules) == 1:
                r = rules[0]
                conform = (r.type == t_type
                           and list(r.formula or []) == [t_formula]
                           and (r.operator or None) == t_op
                           and _dxf_fill_hex(r) == fill_hex)
        if not conform:
            pieces = sum(len(str(cf.sqref).split()) for cf, _ in existing)
            changes.append(f"{rule['label']} : format conditionnel {sqref}"
                           + (f" (remplace {pieces} morceau(x))" if existing else ''))
            if apply:
                kept = ConditionalFormattingList()
                for cf in ws.conditional_formatting:
                    if _ranges_touch_col(cf.sqref, col_idx):
                        continue
                    for r in ws.conditional_formatting[cf]:
                        kept.add(str(cf.sqref), r)
                ws.conditional_formatting = kept
                fill = PatternFill(bgColor=fill_hex)
                if t_type == 'cellIs':
                    new = CellIsRule(operator='equal', formula=[t_formula], fill=fill)
                else:
                    new = FormulaRule(formula=[t_formula], fill=fill)
                ws.conditional_formatting.add(sqref, new)

        # --- validation de données ---
        spec = rule['dv']
        dvs = list(ws.data_validations.dataValidation)
        on_col = [dv for dv in dvs if _ranges_touch_col(dv.sqref, col_idx)]
        if spec is None:
            continue
        min_end = max(start, ws.max_row)
        dv_formula = _expand(spec['formula1'], letter, start, date_letter, cat_letter)
        if len(on_col) == 1 and _dv_conform(on_col[0], spec, dv_formula, letter, start, min_end):
            continue
        changes.append(f"{rule['label']} : validation {sqref}"
                       + (f" (remplace {len(on_col)})" if on_col else ''))
        if apply:
            ws.data_validations.dataValidation = [dv for dv in dvs if dv not in on_col]
            new = DataValidation(type='custom', formula1=dv_formula,
                                 allow_blank=True, showErrorMessage=True, errorStyle='stop',
                                 errorTitle=spec['errorTitle'], error=spec['error'])
            ws.add_data_validation(new)
            new.add(sqref)

    return changes
