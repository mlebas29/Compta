#!/usr/bin/env python3
"""tool_migrate_schema_v2.py — migre un classeur xlsm de SCHEMA_VERSION 1 vers 2.

Chantier « drill devise » (Phase 2) : élimination des colonnes par devise dans
Budget CAT et Contrôles CTRL2 au profit d'un modèle drill-down.

Opérations appliquées (dans l'ordre) :

A. Stash A/B (session 2) — named ranges manquants + formules template en NR
   1. Ajout NR CATeur (Budget!F), POSTESmontant (Budget!C), POSTEStype (Budget!B)
   2. Réécriture Avoirs!L6, Budget!C5/C7/C8/F24/G24 en formules NR

B. Renommage @ catégories structurelles (template + Opérations + formules CTRL2)
   3. Budget cats E16-E22 : Change → @Change, etc.
   4. Opérations col OPcatégorie : idem sur toutes les lignes
   5. Formules CTRL2 : "Virement*" → "@Virement", "Change" → "@Change", "Achat métaux" → "@Achat métaux"

C. Refonte drill devise (Phase 2)
   6. Drop rows CTRL2 natives (Virements native + Titres native) → 2 rows en moins
   7. Rename NR : CATeur → CATmontant, CTRL2eur → CTRL2drill
   8. Ajout NR : CTRL2_fonds_en_transit, CTRL2_synthese
   9. Budget F13 + Contrôles M8 : valeur 'EUR' (drill cells)
  10. Cell styles Drill_dec{0,2,5} + CF sur body drill : format dynamique
      selon COTdecimales lookup par COTcode (pas de modif _save_devise)
  11. Budget G col (Total €) : SUMPRODUCT cours du jour via COTcode × COTcours
  12. Contrôles L col (Général) : SUMIFS/COUNTIFS all-devise

Usage :
  python3 tool_migrate_schema_v2.py <xlsm_path>

NOTE : pour l'instant, gère surtout le template single-devise. Les xlsm
multi-devises (PROD, TNR expected avec > 1 devise) nécessitent une étape
supplémentaire de fusion des colonnes F-M (Budget) / M-T (CTRL2) → 1 col drill.
À faire en Phase 5 quand tout sera stabilisé.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import uno
from inc_uno import UnoDocument
from inc_excel_schema import uno_row, uno_col


RENAME_CATS = {
    'Change': '@Change',
    'Achat métaux': '@Achat métaux',
    'Virement': '@Virement',
    'Virement*': '@Virement',  # résidu mauvais import
    'Achat titres': '@Achat titres',
    'Vente titres': '@Vente titres',
    'Arbitrage titres': '@Arbitrage titres',
}

FORMULA_REPLACEMENTS = [
    ('"Virement*"', '"@Virement"'),
    ('"Change"', '"@Change"'),
    ('"Achat métaux"', '"@Achat métaux"'),
]


# ========== A. Stash A/B ==========

def _col_letter_to_idx(letter):
    idx = 0
    for c in letter:
        idx = idx * 26 + (ord(c) - ord('A') + 1)
    return idx - 1


def _nr_col_letter(nr, name):
    import re
    if not nr.hasByName(name):
        return None
    m = re.match(r'\$[^.]+\.\$([A-Z]+)\$', nr.getByName(name).Content)
    return m.group(1) if m else None


def _nr_bounds(nr, name):
    import re
    if not nr.hasByName(name):
        return None
    m = re.match(r'\$([^.]+)\.\$([A-Z]+)\$(\d+):\$[A-Z]+\$(\d+)',
                 nr.getByName(name).Content)
    return (m.group(1), m.group(2), int(m.group(3)), int(m.group(4))) if m else None


def fuse_devise_cols_budget(ws_bud, nr, log):
    """DEV (multi-devise) : supprime les cols devises additionnelles dans Budget CAT.
    Garde la première (EUR = CATnom + 1) qui devient la col drill. Idempotent.

    Détection : cols strictement entre (CATnom + 1) et CATtotal_euro.
    Drill col = CATeur (si existe) ou CATmontant (si existe) ou CATnom + 1.
    Après delete, LO auto-ajuste CATtotal_euro et les NRs suivants.
    """
    drill_letter = _nr_col_letter(nr, 'CATeur') or _nr_col_letter(nr, 'CATmontant')
    if not drill_letter:
        # Fallback : première col devise = CATnom_col + 1
        cat_b = _nr_bounds(nr, 'CATnom')
        if not cat_b:
            return
        _, nom_letter, _, _ = cat_b
        drill_col = _col_letter_to_idx(nom_letter) + 1
        drill_letter = _idx_to_col_letter(drill_col)
    total_letter = _nr_col_letter(nr, 'CATtotal_euro')
    if not total_letter:
        return
    drill_col = _col_letter_to_idx(drill_letter)
    total_col = _col_letter_to_idx(total_letter)
    if total_col - drill_col <= 1:
        return  # déjà fusé
    n_delete = total_col - drill_col - 1
    for c in range(total_col - 1, drill_col, -1):
        ws_bud.Columns.removeByIndex(c, 1)
    log.append(f'  Budget fuse : {n_delete} cols devises supprimées (entre {drill_letter} et {total_letter})')


def _idx_to_col_letter(idx):
    """0-idx → lettre ('A'=0)."""
    letter = ''
    n = idx
    while True:
        letter = chr(ord('A') + (n % 26)) + letter
        n = n // 26 - 1
        if n < 0:
            break
    return letter


def _pose_charter_row(ws, row_1, ref_col_0, min_col_0, max_col_0, text=None):
    """Pose la charte v3.6 d'une ligne sentinelle/model-row :
      - col ref_col (0-idx) → COL_REF_FILL (beige clair)
      - cols min..max (0-idx) hors ref → DATA_FILL (blanc)
    Si `text` non-None, écrit la valeur sur ref_col (ex: '⚓').
    Idempotent. Appelé par ensure_anchors, ensure_conventions_table et la
    normalisation layout CTRL2."""
    from inc_formats import COL_REF_FILL, DATA_FILL
    for c in range(min_col_0, max_col_0 + 1):
        cell = ws.getCellByPosition(c, uno_row(row_1))
        if c == ref_col_0:
            if text is not None:
                cell.setString(text)
            cell.CellBackColor = COL_REF_FILL
        else:
            cell.CellBackColor = DATA_FILL


def _family_cols_range(nr, prefix, ref_col_0):
    """Retourne (min_col_0, max_col_0) pour la famille de NRs de préfixe donné.
    Fallback (ref_col, ref_col) si aucun NR de famille."""
    import re as _re2
    cols = {ref_col_0}
    for nr_name in list(nr.ElementNames):
        if not nr_name.startswith(prefix):
            continue
        content = nr.getByName(nr_name).Content
        m = _re2.match(r'\$[^.]+\.\$([A-Z]+)\$', content)
        if m:
            cols.add(_col_letter_to_idx(m.group(1)))
    return (min(cols), max(cols))


# ---- Cell snapshot helpers (duplication minimale de tool_sync_from_witness) ----
def _side_dict(side):
    return {
        'Color': side.Color, 'LineWidth': side.LineWidth,
        'LineStyle': side.LineStyle,
        'InnerLineWidth': getattr(side, 'InnerLineWidth', 0),
        'OuterLineWidth': getattr(side, 'OuterLineWidth', 0),
        'LineDistance': getattr(side, 'LineDistance', 0),
    }


def _make_border(b):
    from com.sun.star.table import BorderLine2
    bl = BorderLine2()
    bl.Color = b['Color']; bl.LineWidth = b['LineWidth']
    bl.LineStyle = b['LineStyle']
    bl.InnerLineWidth = b['InnerLineWidth']
    bl.OuterLineWidth = b['OuterLineWidth']
    bl.LineDistance = b['LineDistance']
    return bl


def _register_format(formats, fmt_str):
    from com.sun.star.lang import Locale
    if not fmt_str:
        return 0
    locale = Locale()
    key = formats.queryKey(fmt_str, locale, False)
    if key == -1:
        key = formats.addNew(fmt_str, locale)
    return key


def _snapshot_cell(cell, formats):
    """Snapshot valeur + styles d'une cellule source."""
    formula = cell.getFormula()
    has_formula = formula.startswith('=')
    try:
        fmt_str = formats.getByKey(cell.NumberFormat).FormatString
    except Exception:
        fmt_str = None
    return {
        'has_formula': has_formula,
        'formula': formula if has_formula else None,
        'value': cell.getString() if not has_formula else None,
        'back_color': cell.CellBackColor,
        'char_color': cell.CharColor,
        'font_name': cell.CharFontName,
        'font_size': cell.CharHeight,
        'font_weight': cell.CharWeight,
        'font_posture': cell.CharPosture,
        'hori_justify': cell.HoriJustify,
        'vert_justify': cell.VertJustify,
        'top_border': _side_dict(cell.TopBorder),
        'bottom_border': _side_dict(cell.BottomBorder),
        'left_border': _side_dict(cell.LeftBorder),
        'right_border': _side_dict(cell.RightBorder),
        'number_format': fmt_str,
    }


def _apply_snapshot(cell, cd, formats):
    """Écrit un snapshot sur une cellule cible."""
    if cd['has_formula']:
        cell.setFormula(cd['formula'])
    elif cd['value']:
        cell.setString(cd['value'])
    else:
        cell.setString('')
    cell.CellBackColor = cd['back_color']
    cell.CharColor = cd['char_color']
    cell.CharFontName = cd['font_name']
    cell.CharHeight = cd['font_size']
    cell.CharWeight = cd['font_weight']
    cell.CharPosture = cd['font_posture']
    cell.HoriJustify = cd['hori_justify']
    cell.VertJustify = cd['vert_justify']
    cell.TopBorder = _make_border(cd['top_border'])
    cell.BottomBorder = _make_border(cd['bottom_border'])
    cell.LeftBorder = _make_border(cd['left_border'])
    cell.RightBorder = _make_border(cd['right_border'])
    if cd['number_format']:
        cell.NumberFormat = _register_format(formats, cd['number_format'])


def read_conv_from_template(target_path, log):
    """Pré-lecture de la tête + body CONV depuis le template adjacent (Export
    livre `comptes_template.xlsm` à côté des scripts).

    Retourne une liste [(r_off, c_off, cell_snapshot)] où r_off couvre [-2..+21] :
      - r_off -2 : titre CONV ('Conventions d'affichage...')
      - r_off -1 : labels ('cellule' / 'légende')
      - r_off 0  : ⚓ top (J)
      - r_off 1..20 : body (exemples + labels réservés)
      - r_off 21 : ⚓ bot (J)

    Retourne None si skip :
      - cible == template source (self-reference)
      - template source introuvable
      - CONVnom absent dans le template
    """
    from pathlib import Path
    import re as _re
    script_dir = Path(__file__).parent.resolve()
    template_path = script_dir / 'comptes_template.xlsm'
    target_res = Path(target_path).resolve()
    if target_res == template_path:
        return None
    if not template_path.exists():
        log.append(f'  [warn] CONV source introuvable : {template_path.name}')
        return None
    from inc_uno import UnoDocument
    with UnoDocument(template_path) as src_doc:
        src_nr = src_doc.document.NamedRanges
        if not src_nr.hasByName('CONVnom'):
            log.append('  [warn] CONV source : CONVnom absent dans template')
            return None
        content = src_nr.getByName('CONVnom').Content
        m = _re.match(r'\$([^.]+)\.\$([A-Z]+)\$(\d+):\$[A-Z]+\$(\d+)', content)
        if not m:
            return None
        sheet, col_letter, r1, r2 = m.group(1), m.group(2), int(m.group(3)), int(m.group(4))
        ws = src_doc.get_sheet(sheet)
        col_idx = _col_letter_to_idx(col_letter)
        formats = src_doc.document.getNumberFormats()
        cells = []
        # Head (r_off -2 titre, -1 labels) + body (0 à r2-r1, inclut ⚓ top/bot)
        for r in range(r1 - 2, r2 + 1):
            if r < 1:
                continue
            for c_off in range(3):
                cell = ws.getCellByPosition(col_idx + c_off, uno_row(r))
                cd = _snapshot_cell(cell, formats)
                cells.append((r - r1, c_off, cd))
    log.append(f'  CONV source : {len(cells)} cellules lues depuis {template_path.name}')
    return cells


def write_conv_to_target(xdoc, nr_tgt, cells, log):
    """Écrit les snapshots CONV (head + body) sur la cible, filtrant les
    cellules avec formule (source ou cible) comme tool_sync_from_witness.

    Skip entier si la cible a déjà un body CONV rempli : protège à la fois
    le témoin (source de vérité pour le contenu CONV) et toute retouche
    manuelle utilisateur. Détection : au moins une cellule K/L non vide
    dans le body (rows r1+1 .. r2-1)."""
    import re as _re
    if not cells:
        return
    if not nr_tgt.hasByName('CONVnom'):
        log.append('  [skip] write_conv_body : CONVnom absent sur cible')
        return
    content = nr_tgt.getByName('CONVnom').Content
    m = _re.match(r'\$([^.]+)\.\$([A-Z]+)\$(\d+):\$[A-Z]+\$(\d+)', content)
    if not m:
        return
    sheet_name = m.group(1)
    tgt_col_idx = _col_letter_to_idx(m.group(2))
    tgt_r1 = int(m.group(3))
    tgt_r2 = int(m.group(4))
    ws_tgt = xdoc.Sheets.getByName(sheet_name)
    # Pré-check : body déjà rempli ? (cells K/L non vides entre les ⚓)
    populated = False
    for r in range(tgt_r1 + 1, tgt_r2):
        for c_off in (1, 2):  # col K, L
            if ws_tgt.getCellByPosition(tgt_col_idx + c_off, uno_row(r)).getString():
                populated = True
                break
        if populated:
            break
    if populated:
        log.append('  CONV body : cible déjà renseignée, skip (préservation contenu)')
        return
    formats = xdoc.getNumberFormats()
    n_written = 0
    n_skipped = 0
    for r_off, c_off, cd in cells:
        tgt_row_1 = tgt_r1 + r_off
        if tgt_row_1 < 1:
            continue
        tgt_cell = ws_tgt.getCellByPosition(tgt_col_idx + c_off, uno_row(tgt_row_1))
        if cd['has_formula'] or tgt_cell.getFormula().startswith('='):
            n_skipped += 1
            continue
        _apply_snapshot(tgt_cell, cd, formats)
        n_written += 1
    log.append(f'  CONV : {n_written} cellules écrites, {n_skipped} skip (formule)')


def ensure_eur_cotation(ws_cot, nr, log):
    """Ajoute EUR dans Cotations (COTcode) si absent. EUR est la devise de base
    du drill (cours = 1, toujours présente). Nécessaire pour DEV pré-drill où
    EUR était implicite.
    """
    cot_b = _nr_bounds(nr, 'COTcode')
    if not cot_b:
        return
    _, e_letter, r1, r2 = cot_b
    e_col_0 = _col_letter_to_idx(e_letter)
    # Scan EUR in the range
    for r in range(r1, r2 + 1):
        v = ws_cot.getCellByPosition(e_col_0, uno_row(r)).getString().strip()
        if v == 'EUR':
            return  # déjà présent
    # Insérer EUR en TÊTE : row juste après r1 (premier data row)
    # LO auto-extend les NR si on insère au milieu.
    insert_row_1 = r1 + 1
    ws_cot.Rows.insertByIndex(uno_row(insert_row_1), 1)
    # Écrire valeurs : label (A), nature (B), famille (C), decimales (D), code (E),
    # cours (F). Utilise les lettres de chaque NR COT* pour layout-agnostic.
    def w(nr_name, value, as_string=True):
        letter = _nr_col_letter(nr, nr_name)
        if letter:
            cell = ws_cot.getCellByPosition(
                _col_letter_to_idx(letter), uno_row(insert_row_1))
            if as_string:
                cell.setString(str(value))
            else:
                cell.setValue(value)
    w('COTlabel', 'Euro')
    w('COTnature', 'primaire')
    w('COTfamille', 'fiat')
    w('COTdecimales', 2, as_string=False)
    w('COTcode', 'EUR')
    w('COTcours', 1, as_string=False)
    log.append(f'  Cotations : EUR ajouté en row {insert_row_1} (cours=1)')


def normalize_total_col_fill(ws_bud, nr, log):
    """Normalise le fond de la col CATtotal_euro (body blanc + pied beige clair).

    Nécessaire après fuse DEV : la col N hérite du fill GRIS_BEIGE/GRIS_BLANC
    de l'ancienne col per-devise à sa position.
    """
    from inc_formats import BEIGE_CLAIR, BLANC
    total_letter = _nr_col_letter(nr, 'CATtotal_euro')
    cat_b = _nr_bounds(nr, 'CATnom')
    if not total_letter or not cat_b:
        return
    total_col_0 = _col_letter_to_idx(total_letter)
    _, _, r1, r2 = cat_b
    # Body rows : r1 à r2 (incluant ✓ model rows) → BLANC
    for r in range(r1, r2 + 1):
        ws_bud.getCellByPosition(total_col_0, uno_row(r)).CellBackColor = BLANC
    # Pied rows : r2+1 à r2+5 (Total, Somme, Écart, Total hors, Montant Euros) → BEIGE_CLAIR
    for r in range(r2 + 1, r2 + 6):
        ws_bud.getCellByPosition(total_col_0, uno_row(r)).CellBackColor = BEIGE_CLAIR
    log.append(f'  Budget col {total_letter} : fond normalisé (body BLANC + pied BEIGE_CLAIR)')


def fuse_devise_cols_ctrl(ws_ctrl, nr, log):
    """DEV fuse Contrôles : garde seulement la première col drill (M EUR),
    supprime les cols devises à droite (N, O, ..., jusqu'à header vide).
    """
    drill_letter = _nr_col_letter(nr, 'CTRL2eur') or _nr_col_letter(nr, 'CTRL2drill')
    type_bounds = _nr_bounds(nr, 'CTRL2type')
    if not drill_letter or not type_bounds:
        return
    drill_col = _col_letter_to_idx(drill_letter)
    _, _, type_r1, _ = type_bounds
    header_row_0 = type_r1 - 3  # 0-indexed row (header = type_start - 2)
    # Scan à droite pour trouver les cols devises
    cols_to_delete = []
    for c in range(drill_col + 1, drill_col + 30):
        val = ws_ctrl.getCellByPosition(c, header_row_0).getString().strip()
        if not val:
            break
        cols_to_delete.append(c)
    for c in reversed(cols_to_delete):
        ws_ctrl.Columns.removeByIndex(c, 1)
    if cols_to_delete:
        log.append(f'  Contrôles fuse : {len(cols_to_delete)} cols devises supprimées à droite de {drill_letter}')


from inc_excel_schema import ANCHOR_TABLES


def ensure_conventions_table(xdoc, nr, log):
    """Bootstrap du tableau CONV (Patrimoine) si absent.

    Layout constant pour tous les classeurs (témoin = référence v3.6) :
      col CONVnom = col PATlabel + 8  (J si PATlabel en B)
      CONVcell    = col + 1,  CONVlégende = col + 2
      CONV_r1     = pat_r2 + 8          (row de ⚓ top)
      CONV_r2     = CONV_r1 + 21        (row de ⚓ bot — 22 lignes totales)

    Idempotent : si CONVnom existe déjà, no-op. Sinon crée les 3 NRs + pose
    les ⚓ aux bornes. Le remplissage du body (tête/body/pied + fond ⚓) est
    fait par `tool_sync_from_witness.py` (TABLES_COPY_BODY + cleanup cible).

    Note : le cleanup des résidus (ancien cartouche vert, cellules col M
    hors nouveau CONV) est fait côté sync, pas ici, pour ne pas toucher au
    témoin qui est la source de vérité.
    """
    import re as _re
    if nr.hasByName('CONVnom'):
        return
    if not nr.hasByName('PATlabel'):
        log.append('  [skip] ensure_conventions_table : PATlabel absent')
        return
    m = _re.match(r'\$([^.]+)\.\$([A-Z]+)\$(\d+):\$[A-Z]+\$(\d+)',
                  nr.getByName('PATlabel').Content)
    if not m:
        log.append('  [skip] ensure_conventions_table : PATlabel parse KO')
        return
    sheet_name = m.group(1)
    pat_col_letter = m.group(2)
    pat_r2 = int(m.group(4))
    pat_col_idx = _col_letter_to_idx(pat_col_letter)       # B=1 (0-indexed)
    conv_col_idx = pat_col_idx + 8                         # J=9
    conv_col_letter = _idx_to_col_letter(conv_col_idx)
    conv_r1 = pat_r2 + 8
    conv_r2 = conv_r1 + 21                                 # 22 rows (témoin : 40..61)

    ws = xdoc.Sheets.getByName(sheet_name)
    # Cleanup résidus ancien cartouche (rows pat_r2+1..conv_r2+5 cols J..M) :
    # CellFlags VALUE|DATETIME|STRING|ANNOTATION|FORMULA|HARDATTR = 63.
    # Zone élargie à 4 cols (J..M) car l'ancien cartouche débordait en col M ;
    # marge bas de +5 rows pour couvrir les queues de l'ancien cartouche.
    clear_rng = ws.getCellRangeByPosition(
        conv_col_idx, uno_row(pat_r2 + 1),
        conv_col_idx + 3, uno_row(conv_r2 + 5))
    clear_rng.clearContents(63)
    log.append(f'  Cleanup résidus cartouche : rows {pat_r2+1}..{conv_r2+5} '
               f'cols {_idx_to_col_letter(conv_col_idx)}..'
               f'{_idx_to_col_letter(conv_col_idx+3)}')
    # Pose ⚓ + charte sur les 2 sentinelles (col ref beige, autres cols blanc)
    max_col = conv_col_idx + 2  # col L
    _pose_charter_row(ws, conv_r1, conv_col_idx, conv_col_idx, max_col, text='⚓')
    _pose_charter_row(ws, conv_r2, conv_col_idx, conv_col_idx, max_col, text='⚓')
    # Pied CONV (row r2+1) : PIED_FILL + BORDURE_PIED (thick brun top) sur J..L
    from inc_formats import PIED_FILL, PIED_BORDER_COLOR, THICK_WIDTH_UNO
    from com.sun.star.table import BorderLine2
    pied_border = BorderLine2()
    pied_border.Color = PIED_BORDER_COLOR
    pied_border.LineWidth = THICK_WIDTH_UNO
    pied_border.LineStyle = 0
    for c in range(conv_col_idx, max_col + 1):
        cell = ws.getCellByPosition(c, uno_row(conv_r2 + 1))
        cell.CellBackColor = PIED_FILL
        cell.TopBorder = pied_border
    pos = uno.createUnoStruct('com.sun.star.table.CellAddress')
    pos.Sheet = 0; pos.Column = 0; pos.Row = 0
    for name, col_offset in (('CONVnom', 0), ('CONVcell', 1), ('CONVlégende', 2)):
        col_letter = _idx_to_col_letter(conv_col_idx + col_offset)
        content = f'${sheet_name}.${col_letter}${conv_r1}:${col_letter}${conv_r2}'
        nr.addNewByName(name, content, pos, 0)
    log.append(f'  Bootstrap CONV : {sheet_name}!{conv_col_letter}{conv_r1}..'
               f'{_idx_to_col_letter(conv_col_idx+2)}{conv_r2} '
               f'(PAT_bot={pat_r2} → CONV_top={conv_r1} [+8])')


def ensure_pat_extension_nrs(xdoc, nr, log):
    """Ajoute PAText1..PAText4 sur les 4 colonnes à droite de PATpoids.

    Décoratif : étend le tableau Patrimoine vers la droite pour que la grille
    hair s'applique sur les colonnes adjacentes (cohérence visuelle).

    Idempotent : skip si PAText1 déjà présent. Bornes (sheet, rows) lues depuis
    PATpoids (ou PATlabel en fallback).
    """
    import re as _re
    if nr.hasByName('PAText1'):
        return
    ref_name = 'PATpoids' if nr.hasByName('PATpoids') else 'PATlabel'
    if not nr.hasByName(ref_name):
        log.append('  [skip] ensure_pat_extension_nrs : PATpoids/PATlabel absent')
        return
    m = _re.match(r'\$([^.]+)\.\$([A-Z]+)\$(\d+):\$[A-Z]+\$(\d+)',
                  nr.getByName(ref_name).Content)
    if not m:
        log.append('  [skip] ensure_pat_extension_nrs : parse KO')
        return
    sheet_name = m.group(1)
    ref_col_letter = m.group(2)
    r1 = int(m.group(3))
    r2 = int(m.group(4))
    ref_col_idx = _col_letter_to_idx(ref_col_letter)
    # Si on s'est appuyé sur PATlabel (B), PAText commence à B+4 (= F).
    # Sinon PATpoids (E) → PAText commence à E+1 (= F).
    base_col_idx = ref_col_idx + (4 if ref_name == 'PATlabel' else 1)

    pos = uno.createUnoStruct('com.sun.star.table.CellAddress')
    pos.Sheet = 0
    pos.Column = 0
    pos.Row = 0
    added = []
    for i in range(1, 5):
        name = f'PAText{i}'
        if nr.hasByName(name):
            continue
        col_letter = _idx_to_col_letter(base_col_idx + i - 1)
        content = f'${sheet_name}.${col_letter}${r1}:${col_letter}${r2}'
        nr.addNewByName(name, content, pos, 0)
        added.append(f'{name}={col_letter}')
    if added:
        log.append(f'  PAT extension NRs : {", ".join(added)} (rows {r1}..{r2})')


def ensure_anchors(xdoc, nr, log):
    """Pose ⚓ aux rows sentinelles et maintient la règle
    « NR couvre exactement [row(⚓_top), row(⚓_bot)] ».

    Col dérivée du `ref_nr`. Famille dérivée par préfixe alpha+digit (CAT*,
    CTRL1*, CTRL2*, etc.).

    Tolérance offset : si une sentinelle existe dans ±2 rows du r1/r2 du NR,
    le NR est réaligné (étendu ou restreint) pour coller à la sentinelle, au
    lieu d'en poser une nouvelle. Ça couvre les schémas hybrides (sentinelles
    déjà posées mais NR désaligné) sans écraser de data.

    Pour chaque bout (top/bot) :
      OK     cell(r) est ✓/⚓             → rename ✓→⚓ si besoin
      OFFSET cell(r±k) est ✓/⚓ (k∈1,2)   → réaligner r sur cette position
      MISSING pas de sentinelle voisine   → poser ⚓ (r-1 si vide, sinon insert)

    Tous les NRs de la famille sont ensuite alignés sur les nouvelles bornes.
    Seul cas d'abort : ref_nr parse KO ou multi-col (erreurs dures de
    validate_anchors, jamais rencontrées en nominal).
    """
    import re
    from inc_check_integrity import validate_anchors, _parse_nr_bounds, _col_letter_to_idx

    # ---- Pré-check : abort uniquement sur erreurs dures ----
    ok, errs, warns = validate_anchors(xdoc)
    if not ok:
        log.append('  [ABORT] validate_anchors — erreurs dures :')
        for e in errs:
            log.append(f'    ✗ {e}')
        raise RuntimeError(
            f'ensure_anchors aborté — {len(errs)} erreur(s) dure(s). '
            f'Utiliser tool_migrate_schema_v2.py --check pour diagnostiquer.')
    for w in warns:
        log.append(f'  [warn] {w}')

    # ---- Helpers UNO ----
    def cell_val(ws, col_0, row_1):
        return ws.getCellByPosition(col_0, uno_row(row_1)).getString().strip()

    def bounds_of(name):
        if not nr.hasByName(name):
            return None
        return _parse_nr_bounds(nr.getByName(name).Content)

    def align_family(prefix, new_r1, new_r2):
        """Aligne tous les NRs dont le nom commence par `prefix` à (new_r1, new_r2)."""
        for nr_name in list(nr.ElementNames):
            if not nr_name.startswith(prefix):
                continue
            obj = nr.getByName(nr_name)
            p = _parse_nr_bounds(obj.Content)
            if not p:
                continue
            sh, c1, r1, c2, r2 = p
            if r1 == new_r1 and r2 == new_r2:
                continue
            pos = obj.ReferencePosition
            typ = obj.Type
            new_content = f'${sh}.${c1}${new_r1}:${c2}${new_r2}'
            nr.removeByName(nr_name)
            nr.addNewByName(nr_name, new_content, pos, typ)
            log.append(f'  NR {nr_name} : ${c1}${r1}:${c2}${r2} → ${c1}${new_r1}:${c2}${new_r2}')

    SENT = ('✓', '⚓')

    def find_sentinel(ws, col_0, row_1):
        """Cherche ✓/⚓ à row_1 puis dans ±1, ±2. Retourne (row_trouvée, valeur)
        ou (None, '')."""
        if cell_val(ws, col_0, row_1) in SENT:
            return row_1, cell_val(ws, col_0, row_1)
        for delta in (-1, 1, -2, 2):
            r = row_1 + delta
            if r > 0 and cell_val(ws, col_0, r) in SENT:
                return r, cell_val(ws, col_0, r)
        return None, ''

    def ensure_symbol(ws, col_0, row_1, side_label):
        """Après ajustement, garantir ⚓ (renommer ✓ si besoin)."""
        v = cell_val(ws, col_0, row_1)
        if v == '✓':
            ws.getCellByPosition(col_0, uno_row(row_1)).setString('⚓')
            log.append(f'  {side_label} : ✓ → ⚓')

    # ---- Boucle tables ----
    for sh_name, ref_nr, target_end, only_start in ANCHOR_TABLES:
        b = bounds_of(ref_nr)
        if not b:
            log.append(f'  [skip] {sh_name}/{ref_nr} : ref_nr absent')
            continue
        _, c1, r1, _, r2 = b
        ref_col = _col_letter_to_idx(c1)
        ws = xdoc.Sheets.getByName(sh_name)
        prefix_m = re.match(r'^([A-Z]+\d*)', ref_nr)
        if not prefix_m:
            continue
        prefix = prefix_m.group(1)
        # Plage colonnes de la famille pour la charte (sentinelles)
        min_col_fam, max_col_fam = _family_cols_range(nr, prefix, ref_col)

        # --- Top ---
        found_top, _ = find_sentinel(ws, ref_col, r1)
        if found_top is not None:
            new_r1 = found_top
            ensure_symbol(ws, ref_col, new_r1, f'{sh_name}!{c1}{new_r1}')
            if new_r1 != r1:
                log.append(f'  {sh_name} top réaligné : NR {c1}{r1} → {c1}{new_r1} (sentinelle existante)')
        else:
            # MISSING : poser ⚓ à r1-1 si vide, sinon insertion à r1
            if r1 > 1 and cell_val(ws, ref_col, r1 - 1) == '':
                _pose_charter_row(ws, r1 - 1, ref_col, min_col_fam, max_col_fam, text='⚓')
                log.append(f'  {sh_name}!{c1}{r1-1} : ⚓ posé (cellule vide hors NR)')
                new_r1 = r1 - 1
            else:
                ws.Rows.insertByIndex(uno_row(r1), 1)
                _pose_charter_row(ws, r1, ref_col, min_col_fam, max_col_fam, text='⚓')
                log.append(f'  {sh_name}!{c1}{r1} : ⚓ posé (row insérée, data décalée +1)')
                new_r1 = r1
                r1 += 1
                r2 += 1

        # --- Bot ---
        if only_start:
            # Pas d'ancre bot (OP) : garder le r2 existant, pas de sentinelle posée.
            new_r2 = r2
        elif target_end is not None:
            # Cible fixe : poser/renommer ⚓ à target_end, new_r2 = target_end.
            if cell_val(ws, ref_col, target_end) not in SENT:
                _pose_charter_row(ws, target_end, ref_col, min_col_fam, max_col_fam, text='⚓')
                log.append(f'  {sh_name}!{c1}{target_end} : ⚓ posé (cible fixe)')
            else:
                ensure_symbol(ws, ref_col, target_end, f'{sh_name}!{c1}{target_end}')
            new_r2 = target_end
        else:
            found_bot, _ = find_sentinel(ws, ref_col, r2)
            if found_bot is not None:
                new_r2 = found_bot
                ensure_symbol(ws, ref_col, new_r2, f'{sh_name}!{c1}{new_r2}')
                if new_r2 != r2:
                    log.append(f'  {sh_name} bot réaligné : NR {c1}{r2} → {c1}{new_r2} (sentinelle existante)')
            else:
                if cell_val(ws, ref_col, r2 + 1) == '':
                    _pose_charter_row(ws, r2 + 1, ref_col, min_col_fam, max_col_fam, text='⚓')
                    log.append(f'  {sh_name}!{c1}{r2+1} : ⚓ posé (cellule vide hors NR)')
                    new_r2 = r2 + 1
                else:
                    # Insertion row à r2+1 : décale data en dessous mais NR inchangé
                    ws.Rows.insertByIndex(uno_row(r2 + 1), 1)
                    _pose_charter_row(ws, r2 + 1, ref_col, min_col_fam, max_col_fam, text='⚓')
                    log.append(f'  {sh_name}!{c1}{r2+1} : ⚓ posé (row insérée après NR)')
                    new_r2 = r2 + 1

        # --- Aligner toute la famille (préfixe) à (new_r1, new_r2) ---
        # Toujours appelé : si un NR de la famille a des bornes différentes
        # (schéma hybride pré-v3.6), align_family les ramène à (new_r1, new_r2).
        align_family(prefix, new_r1, new_r2)

        # --- Pied : row r2+1 (hors NR, juste sous ⚓ bot) ---
        # Convention v3.6 : la row juste après ⚓ bot est la ligne pied visuelle
        # (ex : PAT r33 vide, CTRL2 r26 'Synthèse', CONV r62 vide, etc.) avec
        # PIED_FILL (beige clair) + BORDURE_PIED (top thick brun foncé).
        # Contenu éventuel préservé.
        if not only_start:
            from inc_formats import PIED_FILL, PIED_BORDER_COLOR, THICK_WIDTH_UNO
            from com.sun.star.table import BorderLine2
            pied_border = BorderLine2()
            pied_border.Color = PIED_BORDER_COLOR
            pied_border.LineWidth = THICK_WIDTH_UNO
            pied_border.LineStyle = 0  # solide
            for c in range(min_col_fam, max_col_fam + 1):
                cell = ws.getCellByPosition(c, uno_row(new_r2 + 1))
                cell.CellBackColor = PIED_FILL
                cell.TopBorder = pied_border


def ensure_named_ranges(xdoc, nr, log):
    """Ajoute CATmontant, POSTESmontant, POSTEStype, COTcours2 si absents.

    CATmontant : position prise depuis CATeur (si existe, DEV multi-devise) ou
    depuis CATnom+1 col (fallback template single-devise).
    COTcours2 : col H (COTcours + 1), porte les formules `=1/F{r}` Cours de
    l'Euro. Ajouté pour étendre la famille COT à col H et faire propager la
    charte (pied/tête).
    """
    import re
    def bounds_of(name):
        if not nr.hasByName(name):
            return None
        content = nr.getByName(name).Content
        m = re.match(r'\$([^.]+)\.\$([A-Z]+)\$(\d+):\$[A-Z]+\$(\d+)', content)
        return (m.group(1), m.group(2), int(m.group(3)), int(m.group(4))) if m else None

    cat_b = bounds_of('CATnom')
    cateur_b = bounds_of('CATeur')
    post_b = bounds_of('POSTESnom')
    cot_b = bounds_of('COTcours')
    to_add = []
    if cat_b and not nr.hasByName('CATmontant'):
        sh, _, r1, r2 = cat_b
        # Si CATeur existe, réutiliser sa position (même col)
        if cateur_b:
            _, drill_letter, _, _ = cateur_b
        else:
            # Template : col drill = CATnom_col + 1
            _, cat_letter, _, _ = cat_b
            drill_idx = _col_letter_to_idx(cat_letter) + 1
            # idx → letter
            drill_letter = chr(ord('A') + drill_idx) if drill_idx < 26 else None
            if drill_letter is None:
                return
        to_add.append(('CATmontant', f'${sh}.${drill_letter}${r1}:${drill_letter}${r2}'))
    if post_b:
        sh, _, r1, r2 = post_b
        to_add.append(('POSTESmontant', f'${sh}.$C${r1}:$C${r2}'))
        to_add.append(('POSTEStype',    f'${sh}.$B${r1}:$B${r2}'))
    if cot_b and not nr.hasByName('COTcours2'):
        sh, _, r1, r2 = cot_b
        # Position = col max de la famille COT* + 1 (H si COTdate en G)
        max_col_cot = 0
        for nr_name in list(nr.ElementNames):
            if not nr_name.startswith('COT'):
                continue
            c2 = bounds_of(nr_name)
            if c2:
                max_col_cot = max(max_col_cot, _col_letter_to_idx(c2[1]))
        cot2_letter = _idx_to_col_letter(max_col_cot + 1)
        to_add.append(('COTcours2', f'${sh}.${cot2_letter}${r1}:${cot2_letter}${r2}'))
    for name, content in to_add:
        if nr.hasByName(name):
            continue
        pos = uno.createUnoStruct('com.sun.star.table.CellAddress')
        pos.Sheet = 0; pos.Column = 0; pos.Row = 0
        nr.addNewByName(name, content, pos, 0)
        log.append(f'  NR ajouté : {name} = {content}')


def _purge_misplaced_formula(ws, col_idx, keep_row, signature, log, label):
    """Parcourt col_idx rows 1..60, efface les cellules dont la formule contient
    'signature' sauf celle à keep_row. Retourne la liste des rows purgées.
    """
    purged = []
    for r in range(1, 61):
        if r == keep_row:
            continue
        cell = ws.getCellByPosition(uno_col(col_idx), uno_row(r))
        f = cell.getFormula()
        if signature in f:
            cell.setString('')
            purged.append(r)
    if purged:
        log.append(f'  {label} : purge {len(purged)} vestiges ({signature}) rows {purged}')
    return purged


def stash_a_formulas(doc, nr, log):
    """Réécrit formules template pour utiliser named ranges — positions dynamiques.

    Problème connu : mes writes hardcoded précédents laissaient des formules
    SUM(NR) sur des lignes intérieures aux NR (circular ref) quand les NR
    s'étaient étendues via GUI. Fix : 1) scan & purge les vestiges, 2) écrire
    aux vraies positions calculées depuis les NR_end.
    """
    import re
    ws_av = doc.get_sheet('Avoirs')
    ws_bud = doc.get_sheet('Budget')

    def nr_end_row(name):
        if not nr.hasByName(name):
            return None
        m = re.match(r'\$[^.]+\.\$[A-Z]+\$\d+:\$[A-Z]+\$(\d+)', nr.getByName(name).Content)
        return int(m.group(1)) if m else None

    # --- Avoirs L Total : AVRmontant_solde_euro_end + 1 ---
    avr_end = nr_end_row('AVRmontant_solde_euro')
    if avr_end:
        avr_total_row = avr_end + 1
        _purge_misplaced_formula(ws_av, 12, avr_total_row,
                                 'AVRmontant_solde_euro', log, 'Avoirs!L*')
        ws_av.getCellByPosition(uno_col(12), uno_row(avr_total_row)).setFormula(
            '=ROUND(SUM(AVRmontant_solde_euro);2)')
        log.append(f'  Avoirs!L{avr_total_row} : =ROUND(SUM(AVRmontant_solde_euro);2) (Total)')

        # Restaure les formules L body pour data rows qui en manqueraient
        # Formule : =K{r} pour EUR, =K{r}*cours_{devise} sinon.
        avr_match = re.match(r'\$[^.]+\.\$[A-Z]+\$(\d+):',
                             nr.getByName('AVRmontant_solde_euro').Content)
        avr_start = int(avr_match.group(1)) if avr_match else 4
        for r in range(avr_start + 1, avr_end):  # data rows entre les ✓
            intitule = ws_av.getCellByPosition(uno_col(1), uno_row(r)).getString().strip()
            devise = ws_av.getCellByPosition(uno_col(5), uno_row(r)).getString().strip()
            if not intitule or not devise:
                continue
            cell_l = ws_av.getCellByPosition(uno_col(12), uno_row(r))
            if cell_l.getFormula().strip():
                continue  # déjà une formule
            if devise == 'EUR':
                cell_l.setFormula(f'=K{r}')
            else:
                cell_l.setFormula(f'=K{r}*cours_{devise}')
            log.append(f'  Avoirs!L{r} : restauré (devise {devise})')

    # --- POSTES : Total = SUM(POSTESmontant) en NR_end + 1 ; Épargne fixe en +2 ---
    posts_end = nr_end_row('POSTESmontant')
    if posts_end:
        posts_total_row = posts_end + 1   # Ligne 'Total = épargne'
        posts_epargne_row = posts_total_row + 1  # Ligne 'Epargne fixe'
        _purge_misplaced_formula(ws_bud, 3, posts_total_row,
                                 'SUM(POSTESmontant)', log, 'Budget!C*')
        _purge_misplaced_formula(ws_bud, 3, posts_epargne_row,
                                 'SUMIF(POSTEStype', log, 'Budget!C*')
        ws_bud.getCellByPosition(uno_col(3), uno_row(posts_total_row)).setFormula(
            '=SUM(POSTESmontant)')
        ws_bud.getCellByPosition(uno_col(3), uno_row(posts_epargne_row)).setFormula(
            '=SUMIF(POSTEStype;"Fixe";POSTESmontant)')
        log.append(f'  Budget!C{posts_total_row} : =SUM(POSTESmontant) (Total = épargne)')
        log.append(f'  Budget!C{posts_epargne_row} : =SUMIF(POSTEStype;"Fixe";POSTESmontant)')

    # --- Budget CAT C5 Divers : =SUMIF(CATposte,A5,CATaffectation) ---
    # Position C5 stable : A5 = Divers (premier poste user), ligne de référence
    ws_bud.getCellByPosition(uno_col(3), uno_row(5)).setFormula(
        '=SUMIF(CATposte;A5;CATaffectation)')
    log.append('  Budget!C5 : =SUMIF(CATposte;A5;CATaffectation)')

    # --- Budget F/G Total (drill + EUR total) : layout-agnostic via NRs ---
    cat_bounds = _nr_bounds(nr, 'CATnom')
    drill_letter = _nr_col_letter(nr, 'CATmontant') or _nr_col_letter(nr, 'CATeur')
    total_letter = _nr_col_letter(nr, 'CATtotal_euro')
    nom_letter = cat_bounds[1] if cat_bounds else 'E'
    cat_end = cat_bounds[3] if cat_bounds else None
    if cat_end and drill_letter and total_letter:
        drill_col = _col_letter_to_idx(drill_letter)
        total_col = _col_letter_to_idx(total_letter)
        nom_col = _col_letter_to_idx(nom_letter)
        bud_total_row = cat_end + 1
        _purge_misplaced_formula(ws_bud, drill_col + 1, bud_total_row,
                                 'SUM(CATmontant)', log, f'Budget!{drill_letter}*')
        _purge_misplaced_formula(ws_bud, total_col + 1, bud_total_row,
                                 'SUM(CATtotal_euro)', log, f'Budget!{total_letter}*')
        ws_bud.getCellByPosition(drill_col, uno_row(bud_total_row)).setFormula(
            '=SUM(CATmontant)')
        ws_bud.getCellByPosition(total_col, uno_row(bud_total_row)).setFormula(
            '=SUM(CATtotal_euro)')
        log.append(f'  Budget!{drill_letter}{bud_total_row} : =SUM(CATmontant) (Total drill)')
        log.append(f'  Budget!{total_letter}{bud_total_row} : =SUM(CATtotal_euro) (Total EUR)')

        # --- Restaure/migre les formules body (drill SUMIFS, total SUMPRODUCT) ---
        # Idempotent : si formule déjà présente avec une ref drill_letter$XX obsolète
        # (ex: M$29 pré-drill au lieu de M$28), migre la ref sans toucher le reste.
        cat_start = cat_bounds[2]
        drill_row = cat_start - 2  # header row CAT = drill cell
        import re as _re
        fixed_refs = 0
        for r in range(cat_start + 1, cat_end):  # body rows entre les ⚓
            cell_nom = ws_bud.getCellByPosition(nom_col, uno_row(r))
            if not cell_nom.getString().strip():
                continue
            cell_drill = ws_bud.getCellByPosition(drill_col, uno_row(r))
            f = cell_drill.getFormula()
            if not f.strip():
                cell_drill.setFormula(
                    f'=SUMIFS(OPmontant;OPdevise;{drill_letter}${drill_row};'
                    f'OPcatégorie;${nom_letter}{r};OPdate;">"&$C$2-365)')
                log.append(f'  Budget!{drill_letter}{r} : restauré SUMIFS body')
            else:
                # Migration idempotente : corriger ref {drill_letter}$OLD → $drill_row
                pattern = _re.compile(
                    rf'(OPdevise[;,]\s*{_re.escape(drill_letter)}\$)(\d+)')
                def _fix(m):
                    return m.group(1) + str(drill_row) if int(m.group(2)) != drill_row else m.group(0)
                new_f = pattern.sub(_fix, f)
                if new_f != f:
                    cell_drill.setFormula(new_f)
                    fixed_refs += 1
            cell_total = ws_bud.getCellByPosition(total_col, uno_row(r))
            if not cell_total.getFormula().strip():
                cell_total.setFormula(
                    f'=SUMPRODUCT(SUMIFS(OPmontant;OPcatégorie;${nom_letter}{r};'
                    f'OPdate;">"&$C$2-365;OPdevise;COTcode)*COTcours)')
                log.append(f'  Budget!{total_letter}{r} : restauré SUMPRODUCT body')
        if fixed_refs:
            log.append(f'  Budget!{drill_letter} body : {fixed_refs} SUMIFS refs drill '
                       f'migrés vers {drill_letter}${drill_row}')


# ========== B. Renommage @ ==========

def migrate_budget_cats(ws_bud, log):
    """Renomme les catégories structurelles dans Budget (scan large)."""
    count = 0
    for c in range(1, 27):
        for r in range(1, 101):
            cell = ws_bud.getCellByPosition(uno_col(c), uno_row(r))
            val = cell.getString()
            if val in RENAME_CATS:
                cell.setString(RENAME_CATS[val])
                count += 1
    if count:
        log.append(f'  Budget : {count} cat structurelles renommées @')


def migrate_operations_cats(ws_ops, cr, log):
    """Renomme les cat dans Opérations col OPcatégorie."""
    col_cat = cr.col('OPcatégorie')
    empty_streak = 0
    count = 0
    for r in range(4, 10001):
        cell = ws_ops.getCellByPosition(col_cat, uno_row(r))
        val = cell.getString()
        if not val:
            empty_streak += 1
            if empty_streak > 100:
                break
            continue
        empty_streak = 0
        if val in RENAME_CATS:
            cell.setString(RENAME_CATS[val])
            count += 1
    if count:
        log.append(f'  Opérations col G : {count} cellules renommées')


def migrate_controles_formulas(ws_ctrl, nr, log):
    """Patch formules CTRL2 : "Virement*"/"Change"/"Achat métaux" → @."""
    import re
    row_start, row_end = None, None
    if nr.hasByName('CTRL2type'):
        content = nr.getByName('CTRL2type').Content
        m = re.match(r'\$[^.]+\.\$[A-Z]+\$(\d+):\$[A-Z]+\$(\d+)', content)
        if m:
            row_start, row_end = int(m.group(1)), int(m.group(2))
    if row_start is None:
        # Fallback : détecter 'CONTRÔLES' label col J
        for r in range(1, 200):
            if ws_ctrl.getCellByPosition(uno_col(10), uno_row(r)).getString() == 'CONTRÔLES':
                row_start = r
                row_end = r + 18
                break
    if row_start is None:
        log.append('  CTRL2 zone non localisée — skip formules')
        return
    count = 0
    for c in range(10, 27):
        for r in range(row_start, row_end + 1):
            cell = ws_ctrl.getCellByPosition(c, uno_row(r))
            old = cell.getFormula()
            if not old or not old.startswith('='):
                continue
            new = old
            for src, dst in FORMULA_REPLACEMENTS:
                new = new.replace(src, dst)
            if new != old:
                cell.setFormula(new)
                count += 1
    if count:
        log.append(f'  Contrôles CTRL2 (rows {row_start}-{row_end}) : {count} formules patchées')


def migrate_budget_totals(ws_bud, nr, log):
    """Budget Total hors @* : drill / total / affectation — SUMIFS NR.

    Positions layout-agnostic via NRs CATmontant / CATtotal_euro / CATaffectation.
    """
    required = ('CATmontant', 'CATtotal_euro', 'CATaffectation')
    missing = [n for n in required if not nr.hasByName(n)]
    if missing:
        log.append(f'  Budget Total hors : skip (NR manquants: {missing})')
        return
    # Détection de la ligne via label (col cats = CATnom col)
    nom_letter = _nr_col_letter(nr, 'CATnom') or 'E'
    nom_col_0 = _col_letter_to_idx(nom_letter)
    target_label = 'Total hors Changes et Virements'
    target_row = None
    for r in range(20, 200):
        if ws_bud.getCellByPosition(nom_col_0, uno_row(r)).getString().strip() == target_label:
            target_row = r
            break
    if target_row is None:
        log.append('  Budget Total hors : label non trouvé — skip')
        return
    # Cols via NRs
    drill_letter = _nr_col_letter(nr, 'CATmontant')
    total_letter = _nr_col_letter(nr, 'CATtotal_euro')
    aff_letter = _nr_col_letter(nr, 'CATaffectation')
    refactor = {
        drill_letter: '=SUMIFS(CATmontant;CATnom;"<>@*")',
        total_letter: '=SUMIFS(CATtotal_euro;CATnom;"<>@*")',
        aff_letter: '=SUMIFS(CATaffectation;CATnom;"<>@*")',
    }
    for letter, formula in refactor.items():
        if not letter:
            continue
        ws_bud.getCellByPosition(_col_letter_to_idx(letter), uno_row(target_row)).setFormula(formula)
        log.append(f'  Budget {letter}{target_row} : {formula}')


# ========== C. Refonte drill devise ==========

def drop_native_balance_rows(ws_ctrl, nr, log):
    """Supprime les 2 lignes 'Virements' et 'Titres' natives de CTRL2 Balances.

    Détecte par contenu col J pour rester indépendant de la position exacte.
    """
    # Parcourir CTRL2 pour trouver 'Virements' et 'Titres' (labels) — pas '€'
    deleted = []
    # Scan large, supprime en ordre inverse pour garder indices stables
    rows_to_delete = []
    for r in range(1, 200):
        label = ws_ctrl.getCellByPosition(uno_col(10), uno_row(r)).getString().strip()
        if label in ('Virements', 'Titres'):
            rows_to_delete.append(r)
    # Vérification : avant drop, les formules Balances (L14/M14 typiquement) référencent
    # les rows de J15-J17 ou J15-J19. Après drop, il faut recaler L14 à COUNTA($J<start>:$J<end>).
    # On laisse cette adaptation à rewrite_ctrl2_general_col.
    for r in reversed(rows_to_delete):
        ws_ctrl.Rows.removeByIndex(uno_row(r), 1)
        deleted.append(r)
    if deleted:
        log.append(f'  CTRL2 drop natives : rows {deleted} supprimées')
    return deleted


def compact_ctrl2_layout(ws_ctrl, log):
    """Supprime les rows vides redondantes dans CTRL2 (post-setup_drill_cells) :
      - row entre 'Type de contrôle' et ⚓ haut (héritage v1 multi-devise)
      - row entre 'Total €' et 'INCONNUS' (résidu pré-migrate)

    Idempotent : skip si rows déjà compactées (J{r+1} non vide).
    """
    col_j = uno_col(10)  # J = col 10 (1-idx) → 9 (0-idx)
    rows_to_delete = []

    def jval(r_1):
        return ws_ctrl.getCellByPosition(col_j, uno_row(r_1)).getString().strip()

    for r in range(1, 200):
        label = jval(r)
        if label == 'Type de contrôle':
            if not jval(r + 1) and jval(r + 2) == '⚓':
                rows_to_delete.append(r + 1)
        elif label == 'Total €':
            if not jval(r + 1) and 'INCONNUS' in jval(r + 2):
                rows_to_delete.append(r + 1)

    # Suppression en ordre inverse (indices stables)
    for r in sorted(set(rows_to_delete), reverse=True):
        ws_ctrl.Rows.removeByIndex(uno_row(r), 1)
        log.append(f'  CTRL2 compact : row {r} (vide redondante) supprimée')
    return rows_to_delete


def rename_drill_nrs(nr, log):
    """Rename CTRL2eur → CTRL2drill (CATmontant déjà créé directement en ensure_named_ranges)."""
    renames = {'CTRL2eur': 'CTRL2drill'}
    for old, new in renames.items():
        if nr.hasByName(old) and not nr.hasByName(new):
            content = nr.getByName(old).Content
            nr.removeByName(old)
            pos = uno.createUnoStruct('com.sun.star.table.CellAddress')
            pos.Sheet = 0; pos.Column = 0; pos.Row = 0
            nr.addNewByName(new, content, pos, 0)
            log.append(f'  NR renommé : {old} → {new} ({content})')


def add_drill_nrs(ws_ctrl, nr, log):
    """Ajoute CTRL2_fonds_en_transit (Total €) et CTRL2_synthese (K synthèse).

    Détecte les cellules cibles par labels : 'Total €' et 'Synthèse des contrôles' col J."""
    total_row = None
    synth_row = None
    for r in range(1, 200):
        lbl = ws_ctrl.getCellByPosition(uno_col(10), uno_row(r)).getString().strip()
        if lbl == 'Total €':
            total_row = r
        elif lbl.startswith('Synthèse'):
            synth_row = r
    if total_row and not nr.hasByName('CTRL2_fonds_en_transit'):
        content = f'$Contrôles.$L${total_row}'
        pos = uno.createUnoStruct('com.sun.star.table.CellAddress')
        pos.Sheet = 0; pos.Column = 0; pos.Row = 0
        nr.addNewByName('CTRL2_fonds_en_transit', content, pos, 0)
        log.append(f'  NR nouveau : CTRL2_fonds_en_transit = {content}')
    if synth_row and not nr.hasByName('CTRL2_synthese'):
        content = f'$Contrôles.$K${synth_row}'
        pos = uno.createUnoStruct('com.sun.star.table.CellAddress')
        pos.Sheet = 0; pos.Column = 0; pos.Row = 0
        nr.addNewByName('CTRL2_synthese', content, pos, 0)
        log.append(f'  NR nouveau : CTRL2_synthese = {content}')


def _apply_drill_validation(cell, source_formula):
    """Applique une validation de type LIST sur la cellule.

    ValidationType.LIST = 6, ShowList = 1 (dropdown unsorted)."""
    validation = cell.Validation
    validation.Type = 6
    validation.setFormula1(source_formula)
    validation.ShowList = 1
    validation.IgnoreBlankCells = True
    validation.ErrorAlertStyle = 0  # STOP
    validation.ShowErrorMessage = True
    cell.Validation = validation


def setup_drill_cells(doc, ws_bud, ws_ctrl, nr, log):
    """Drill cell Budget + Contrôles : valeur 'EUR' + validation LIST.

    Position dynamique :
    - Budget drill = F(CATnom.row_start - 2) [header row CAT]
    - Contrôles drill = M(CTRL2type.row_start - 2) [header row CTRL2]

    Source validation : bornes data de COTcode (exclut ✓ top/bottom).
    Format affiché : `@" ▼"` (suffixe ▼ visuel, valeur stockée 'EUR' inchangée)."""
    import re
    src = '$Cotations.$E$4:$E$4'
    if nr.hasByName('COTcode'):
        content = nr.getByName('COTcode').Content
        m = re.match(r'\$([^.]+)\.\$([A-Z]+)\$(\d+):\$[A-Z]+\$(\d+)', content)
        if m:
            sheet, col, r1, r2 = m.group(1), m.group(2), int(m.group(3)), int(m.group(4))
            src = f'${sheet}.${col}${r1+1}:${col}${r2-1}'

    def bounds_row_start(name):
        if not nr.hasByName(name):
            return None
        content = nr.getByName(name).Content
        m = re.match(r'\$[^.]+\.\$[A-Z]+\$(\d+):', content)
        return int(m.group(1)) if m else None

    cat_r = bounds_row_start('CATnom')
    ctrl2_r = bounds_row_start('CTRL2type')
    # Position drill cells via NRs (layout-agnostic)
    bud_drill_letter = _nr_col_letter(nr, 'CATmontant') or _nr_col_letter(nr, 'CATeur') or 'F'
    ctrl_drill_letter = _nr_col_letter(nr, 'CTRL2drill') or _nr_col_letter(nr, 'CTRL2eur') or 'M'
    bud_drill_col = _col_letter_to_idx(bud_drill_letter)
    ctrl_drill_col = _col_letter_to_idx(ctrl_drill_letter)
    fmt_drill = doc.register_number_format('@" ▼"')
    if cat_r:
        bud_row = cat_r - 2  # header row CAT
        cell = ws_bud.getCellByPosition(bud_drill_col, uno_row(bud_row))
        cell.setString('EUR')
        cell.NumberFormat = fmt_drill  # affichage "EUR ▼" (valeur reste 'EUR')
        _apply_drill_validation(cell, src)
        log.append(f'  Budget {bud_drill_letter}{bud_row} : valeur "EUR" + validation LIST + ▼')
    if ctrl2_r:
        # Drill cell CTRL2 alignée sur la row des labels 'Type de contrôle'.
        # Détection layout-aware par contenu (pas d'offset fixe) : selon le
        # classeur source, labels peuvent être à r1-2 (v3.6 avec row vide
        # intermédiaire r1-1, héritage v1 multi-devise de l'ancienne ligne
        # cours) ou directement à r1-1 (v1 compact). Les deux layouts sont
        # valides en v3.6 — la row intermédiaire n'est plus nécessaire
        # depuis la refonte drill et on la laisse intacte si présente.
        ctrl_type_letter = _nr_col_letter(nr, 'CTRL2type') or 'J'
        ctrl_type_col = _col_letter_to_idx(ctrl_type_letter)
        labels_row = None
        for r in range(max(1, ctrl2_r - 5), ctrl2_r):
            if ws_ctrl.getCellByPosition(ctrl_type_col, uno_row(r)).getString().strip() \
                    == 'Type de contrôle':
                labels_row = r
                break
        if labels_row is None:
            labels_row = ctrl2_r - 2  # fallback
            log.append(f'  [warn] Contrôles labels row introuvable, fallback r1-2={labels_row}')
        ctrl_row = labels_row
        cell = ws_ctrl.getCellByPosition(ctrl_drill_col, uno_row(ctrl_row))
        cell.setString('EUR')
        cell.NumberFormat = fmt_drill  # affichage "EUR ▼"
        _apply_drill_validation(cell, src)
        log.append(f'  Contrôles {ctrl_drill_letter}{ctrl_row} : valeur "EUR" + validation LIST + ▼')
        # Nettoyage : tout "EUR" résiduel en col drill entre r1-5 et r1-1 hors
        # labels_row (issu d'anciennes migrations partielles).
        for r in range(max(1, ctrl2_r - 5), ctrl2_r):
            if r == labels_row:
                continue
            stale = ws_ctrl.getCellByPosition(ctrl_drill_col, uno_row(r))
            if stale.getString() == 'EUR' or stale.Validation.Type != 0:
                stale.setString('')
                v = stale.Validation
                v.Type = 0
                stale.Validation = v
                log.append(f'  Contrôles {ctrl_drill_letter}{r} : drill résiduelle nettoyée')
    log.append(f'  Source validation : {src}')


def _ensure_drill_cell_style(xdoc, name, fmt_str, bg_color, log):
    """Idempotent : crée / met à jour un cell style avec NumberFormat + fond.

    bg_color = None → fond transparent (hérite du fond naturel de la cellule).
    bg_color = int  → fond solide (ex. GRIS_BLANC, GRIS_BEIGE).
    Police toujours noire explicite (sinon LO écrit color rgb=00FFFFFF dans le
    dxf, interprété comme blanc opaque).
    """
    from com.sun.star.lang import Locale
    cell_styles = xdoc.StyleFamilies.getByName('CellStyles')
    created = False
    if not cell_styles.hasByName(name):
        new_style = xdoc.createInstance('com.sun.star.style.CellStyle')
        cell_styles.insertByName(name, new_style)
        created = True
    style = cell_styles.getByName(name)
    num_formats = xdoc.NumberFormats
    locale = Locale()
    fmt_idx = num_formats.queryKey(fmt_str, locale, False)
    if fmt_idx == -1:
        fmt_idx = num_formats.addNew(fmt_str, locale)
    style.NumberFormat = fmt_idx
    if bg_color is None:
        try:
            style.IsCellBackgroundTransparent = True
        except Exception:
            pass
    else:
        try:
            style.IsCellBackgroundTransparent = False
            style.CellBackColor = bg_color
        except Exception:
            pass
    try:
        style.CharColor = 0x000000
    except Exception:
        pass
    if created:
        bg_desc = 'transparent' if bg_color is None else f'#{bg_color:06X}'
        log.append(f'  Cell style créé : {name} ({fmt_str}, bg={bg_desc})')


def _read_cot_devises(ws_cot, nr):
    """Retourne [(code, decimals)] depuis COTcode et COTdecimales (body uniquement).

    Exclut les cellules de modèle ✓ (haut/bas) en prenant les bornes data-only :
    r1+1 .. r2-1 sur le named range.
    """
    import re
    if not nr.hasByName('COTcode') or not nr.hasByName('COTdecimales'):
        return []
    def parse(name):
        m = re.match(r'\$[^.]+\.\$([A-Z]+)\$(\d+):\$[A-Z]+\$(\d+)', nr.getByName(name).Content)
        return (m.group(1), int(m.group(2)), int(m.group(3))) if m else None
    code_b = parse('COTcode')
    dec_b = parse('COTdecimales')
    if not code_b or not dec_b:
        return []

    def col_idx(letter):
        return ord(letter.upper()) - ord('A')

    code_col = col_idx(code_b[0])
    dec_col = col_idx(dec_b[0])
    # Body = entre les 2 ✓ model rows
    r1, r2 = code_b[1] + 1, code_b[2] - 1
    result = []
    for r in range(r1, r2 + 1):
        code = ws_cot.getCellByPosition(code_col, uno_row(r)).getString().strip()
        try:
            dec = int(ws_cot.getCellByPosition(dec_col, uno_row(r)).getValue())
        except Exception:
            dec = 2
        if code:
            result.append((code, dec))
    return result


def _prop(name, value):
    pv = uno.createUnoStruct('com.sun.star.beans.PropertyValue')
    pv.Name = name
    pv.Value = value
    return pv


FORMULA_OP = 9  # com.sun.star.sheet.ConditionOperator.FORMULA


def _is_drill_cf_formula(f):
    """True si la formule CF est une règle drill (approche A ou B)."""
    import re
    if not f:
        return False
    if 'INDEX(COTdecimales' in f:
        return True
    if re.match(r'\s*\$[A-Z]+\$\d+\s*=\s*"', f):
        return True
    return False


def _purge_devise_cf(cf):
    """Retire les règles drill de la CF donnée (purge UNO locale)."""
    to_remove = []
    for i in range(cf.Count):
        entry = cf.getByIndex(i)
        try:
            if _is_drill_cf_formula(entry.Formula1):
                to_remove.append(i)
        except Exception:
            pass
    for idx in reversed(to_remove):
        cf.removeByIndex(idx)


def _xml_remove_obsolete_cf(xlsm_path, log):
    """Retire des CF Budget rendues obsolètes par la refonte drill multi-devise :

    - `G{r} notEqual G{r+1}` (ancienne check Total drill = Total all-devise) :
      plus valable en multi-devise, G et F col portent des sémantiques différentes.
    """
    import zipfile
    import shutil
    import tempfile
    import re
    from pathlib import Path

    tmp_dir = Path(tempfile.mkdtemp())
    try:
        with zipfile.ZipFile(xlsm_path, 'r') as zin:
            zin.extractall(tmp_dir)

        fp = tmp_dir / 'xl/worksheets/sheet3.xml'
        if not fp.exists():
            return
        xml = fp.read_text(encoding='utf-8')

        removed = []
        def drop_obsolete(m):
            block = m.group(0)
            sqref_m = re.search(r'sqref="([^"]+)"', block)
            if not sqref_m:
                return block
            sqref = sqref_m.group(1)
            # CF {L}{r} notEqual {L}${r+1} — Total drill EUR vs Montant Euros historique.
            # Layout-agnostic : matche toute lettre de col. Capture la lettre dans sqref
            # et vérifie que la formule utilise la même lettre.
            single_ref = re.match(r'^([A-Z]+)(\d+)$', sqref)
            if single_ref:
                letter, row = single_ref.group(1), single_ref.group(2)
                if re.search(rf'<formula>{letter}\$\d+</formula>', block):
                    removed.append(sqref)
                    return ''
            return block

        new_xml = re.sub(
            r'<conditionalFormatting[^>]*>.*?</conditionalFormatting>',
            drop_obsolete, xml, flags=re.DOTALL)

        if new_xml != xml:
            fp.write_text(new_xml, encoding='utf-8')
            with zipfile.ZipFile(xlsm_path, 'r') as zin:
                names = zin.namelist()
            with zipfile.ZipFile(xlsm_path, 'w', zipfile.ZIP_DEFLATED) as zout:
                for name in names:
                    src = tmp_dir / name
                    if src.exists():
                        zout.write(src, arcname=name)
            log.append(f'  CF obsolètes retirées : {removed}')
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _xml_rebuild_ecart_cf_sqref(xlsm_path, cat_ecart_row, posts_ecart_row,
                                drill_letter, total_letter, posts_col_letter, log):
    """Reconstruit le sqref de la CF 'cellIs notEqual 0' (alerte Écart) pour ne couvrir
    QUE les cellules Écart (CAT F/G + POSTES C).

    L'ancien sqref template hardcodait plusieurs rows du pied (`G25:I25`, `H27:H28`,
    `J25:J28`, etc.) qui, après refonte drill + insertion de rows, tombaient sur
    Total ou Somme ops (→ orange sur valeurs légitimes).

    Identification : unique bloc <conditionalFormatting> avec
    <cfRule type="cellIs" operator="notEqual" formula=0 dxfId=4> sur sheet3.xml.
    """
    import zipfile
    import shutil
    import tempfile
    import re
    from pathlib import Path

    tmp_dir = Path(tempfile.mkdtemp())
    try:
        with zipfile.ZipFile(xlsm_path, 'r') as zin:
            zin.extractall(tmp_dir)

        fp = tmp_dir / 'xl/worksheets/sheet3.xml'
        if not fp.exists():
            return
        xml = fp.read_text(encoding='utf-8')

        new_sqref_parts = []
        if cat_ecart_row:
            new_sqref_parts.append(f'{drill_letter}{cat_ecart_row}:{total_letter}{cat_ecart_row}')
        if posts_ecart_row:
            new_sqref_parts.append(f'{posts_col_letter}{posts_ecart_row}')
        new_sqref = ' '.join(new_sqref_parts)
        if not new_sqref:
            return

        def fix_block(m):
            if ('operator="notEqual"' not in m.group(0)
                    or '<formula>0</formula>' not in m.group(0)):
                return m.group(0)
            sqref_m = re.search(r'sqref="([^"]+)"', m.group(0))
            if not sqref_m:
                return m.group(0)
            old_sqref = sqref_m.group(1)
            if old_sqref == new_sqref:
                return m.group(0)
            return m.group(0).replace(f'sqref="{old_sqref}"', f'sqref="{new_sqref}"', 1)

        new_xml = re.sub(
            r'<conditionalFormatting[^>]*>.*?</conditionalFormatting>',
            fix_block, xml, flags=re.DOTALL)

        if new_xml != xml:
            fp.write_text(new_xml, encoding='utf-8')
            with zipfile.ZipFile(xlsm_path, 'r') as zin:
                names = zin.namelist()
            with zipfile.ZipFile(xlsm_path, 'w', zipfile.ZIP_DEFLATED) as zout:
                for name in names:
                    src = tmp_dir / name
                    if src.exists():
                        zout.write(src, arcname=name)
            log.append(f'  CF alerte Écart : sqref → {new_sqref}')
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _xml_cleanup_drill_cf(xlsm_path, log):
    """Post-process : retire les <conditionalFormatting> orphelines dont toutes
    les <cfRule> sont des règles drill (approche A ou B).

    UNO laisse parfois des CF fantômes avec sqref partiel quand les ranges cibles
    ont bougé entre runs. Post-process XML = fiable.
    """
    import zipfile
    import shutil
    import tempfile
    import re
    from pathlib import Path

    SHEET_FILES = ['xl/worksheets/sheet3.xml', 'xl/worksheets/sheet6.xml']
    tmp_dir = Path(tempfile.mkdtemp())
    try:
        with zipfile.ZipFile(xlsm_path, 'r') as zin:
            zin.extractall(tmp_dir)

        removed_total = 0
        for sf in SHEET_FILES:
            fp = tmp_dir / sf
            if not fp.exists():
                continue
            xml = fp.read_text(encoding='utf-8')
            new_xml = xml
            # Pour chaque <conditionalFormatting>, supprimer les <cfRule> drill.
            # Si aucune règle ne reste, supprimer aussi le bloc.
            def fix_cf(m):
                nonlocal removed_total
                block = m.group(0)
                def fix_rule(rm):
                    rule = rm.group(0)
                    fm = re.search(r'<formula>([^<]+)</formula>', rule)
                    if fm and _is_drill_cf_formula(fm.group(1).replace('&quot;', '"')):
                        return ''
                    return rule
                new_block = re.sub(r'<cfRule[^>]*>.*?</cfRule>', fix_rule, block, flags=re.DOTALL)
                # Si plus de cfRule restant, supprimer le bloc entier
                if re.search(r'<cfRule', new_block) is None:
                    removed_total += 1
                    return ''
                return new_block
            new_xml = re.sub(
                r'<conditionalFormatting[^>]*>.*?</conditionalFormatting>',
                fix_cf, new_xml, flags=re.DOTALL)
            if new_xml != xml:
                fp.write_text(new_xml, encoding='utf-8')

        # Rezip preserving vbaProject.bin + order
        with zipfile.ZipFile(xlsm_path, 'r') as zin:
            names = zin.namelist()
        with zipfile.ZipFile(xlsm_path, 'w', zipfile.ZIP_DEFLATED) as zout:
            for name in names:
                src = tmp_dir / name
                if src.exists():
                    zout.write(src, arcname=name)
        if removed_total:
            log.append(f'  XML post-cleanup : {removed_total} blocs CF drill orphelins retirés')
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _apply_devise_cf(range_obj, drill_ref, devises, style_name_for):
    """Efface les CF devise de la range puis en ajoute N (une par devise).

    style_name_for(code) → str : nom du cell style à appliquer pour ce code.
    """
    cf = range_obj.ConditionalFormat
    _purge_devise_cf(cf)
    for code, _dec in devises:
        formula = f'{drill_ref}="{code}"'
        props = (
            _prop('Operator', FORMULA_OP),
            _prop('Formula1', formula),
            _prop('StyleName', style_name_for(code)),
        )
        cf.addNew(props)
    range_obj.ConditionalFormat = cf


def _drill_style_name(code, variant):
    """variant ∈ {'body', 'pied'}. EUR → un seul style transparent partagé."""
    if code == 'EUR':
        return 'Drill_EUR'
    return f'Drill_{code}_{variant}'


def setup_drill_formats(doc, ws_bud, ws_ctrl, nr, log):
    """Format dynamique drill devise (approche B : cell style + CF par devise).

    Sémantique :
    - Budget col F (drill) = OPmontant native + SUMPROD cours du jour (G col).
      → Col F drill-native → format drill (CF par devise, code + décimales + bg)
      → F14 = cours(drill), F28 = F27×cours (EUR converti, format EUR fixe)
    - Contrôles col M (drill) = OPequiv_euro + SUM cours d'époque.
      → Col M toujours EUR → aucune CF drill (format EUR conservé)

    Convention visuelle (cohérente avec PVL) :
    - EUR sélectionné → style transparent (bg naturel : blanc body, beige pied)
    - Devise non-EUR → bg gris (GRIS_BLANC sur body, GRIS_BEIGE sur pied),
      format nombre avec code devise `[$CODE]` + décimales par COTdecimales.
    """
    import re
    from inc_formats import devise_format, GRIS_BLANC, GRIS_BEIGE
    xdoc = doc._document

    # 1) Lire les devises COT et créer/maj les cell styles
    ws_cot = doc.get_sheet('Cotations')
    devises = _read_cot_devises(ws_cot, nr)
    if not devises:
        log.append('  CF drill : aucune devise COT trouvée, skip')
        return
    for code, dec in devises:
        fmt = devise_format(code, dec, style='uno')
        if code == 'EUR':
            _ensure_drill_cell_style(xdoc, 'Drill_EUR', fmt, None, log)
        else:
            _ensure_drill_cell_style(xdoc, f'Drill_{code}_body', fmt, GRIS_BLANC, log)
            _ensure_drill_cell_style(xdoc, f'Drill_{code}_pied', fmt, GRIS_BEIGE, log)

    # 2) Bornes dynamiques via NR
    def bounds(name):
        if not nr.hasByName(name):
            return None
        content = nr.getByName(name).Content
        m = re.match(r'\$[^.]+\.\$([A-Z]+)\$(\d+):\$[A-Z]+\$(\d+)', content)
        return (m.group(1), int(m.group(2)), int(m.group(3))) if m else None

    cat_b = bounds('CATnom')
    if not cat_b:
        log.append('  CF drill Budget : skip (CATnom absent)')
        return
    _, r1, r2 = cat_b
    # Layout-agnostic : col drill / total lues depuis NRs
    drill_letter = _nr_col_letter(nr, 'CATmontant') or 'F'
    total_letter = _nr_col_letter(nr, 'CATtotal_euro') or 'G'
    drill_col_0 = _col_letter_to_idx(drill_letter)
    total_col_0 = _col_letter_to_idx(total_letter)
    drill_row = r1 - 2       # header row (drill cell)
    pied_total_row = r2 + 1  # Total
    pied_somme_row = r2 + 2  # Somme opérations
    pied_ecart_row = r2 + 3  # Écart
    pied_thc_row = r2 + 4    # Total hors Changes/Virements (dernière ligne drill)
    pied_eur_row = r2 + 5    # Montant Euros (toujours EUR, PAS drill)
    cours_row = r1 - 1       # cours du drill

    # 3) cours(drill) et Montant Euros converti (col drill, pas drill-dep format)
    cours_lookup = f'INDEX(COTcours;MATCH(${drill_letter}${drill_row};COTcode;0))'
    ws_bud.getCellByPosition(drill_col_0, uno_row(cours_row)).setFormula(f'={cours_lookup}')
    _set_number_format(doc, ws_bud.getCellByPosition(drill_col_0, uno_row(cours_row)),
                       '#\xa0##0,00000 [$€-40C];\\-#\xa0##0,00000 [$€-40C]')
    ws_bud.getCellByPosition(drill_col_0, uno_row(pied_eur_row)).setFormula(
        f'={drill_letter}${pied_thc_row}*{cours_lookup}')
    _set_number_format(doc, ws_bud.getCellByPosition(drill_col_0, uno_row(pied_eur_row)),
                       '#\xa0##0,00 [$€-40C];\\-#\xa0##0,00 [$€-40C]')
    log.append(f'  Budget {drill_letter}{cours_row} = cours(drill)')
    log.append(f'  Budget {drill_letter}{pied_eur_row} = {drill_letter}{pied_thc_row} × cours (EUR)')

    # 3b) Total col : Somme opérations EUR + Écart EUR (symétriques à drill col pied)
    ws_bud.getCellByPosition(total_col_0, uno_row(pied_somme_row)).setFormula(
        '=SUMPRODUCT(SUMIFS(OPmontant;OPdate;">"&$C$2-365;'
        'OPcatégorie;"<>"&Spéciale;OPdevise;COTcode)*COTcours)')
    ws_bud.getCellByPosition(total_col_0, uno_row(pied_ecart_row)).setFormula(
        f'=ROUND({total_letter}${pied_total_row}-{total_letter}${pied_somme_row};2)')
    log.append(f'  Budget {total_letter}{pied_somme_row} : SUMPRODUCT Somme ops EUR')
    log.append(f'  Budget {total_letter}{pied_ecart_row} : =ROUND Écart EUR')

    # 4) Purger CF drill résiduelle dans Budget col drill + Contrôles col drill
    _purge_devise_cf(
        ws_bud.getCellRangeByName(f'{drill_letter}1:{drill_letter}{pied_eur_row + 10}').ConditionalFormat)
    ctrl_b = bounds('CTRL2type')
    ctrl_drill_letter = _nr_col_letter(nr, 'CTRL2drill') or 'M'
    ctrl_cat_row = None
    if ctrl_b:
        _, cr1, cr2 = ctrl_b
        ctrl_rng = ws_ctrl.getCellRangeByName(
            f'{ctrl_drill_letter}1:{ctrl_drill_letter}{cr2 + 10}')
        cf = ctrl_rng.ConditionalFormat
        _purge_devise_cf(cf)
        ctrl_rng.ConditionalFormat = cf
        log.append(f'  CF drill purgée : Contrôles!{ctrl_drill_letter} col (EUR fixe sauf CATÉGORIES)')
        # Réappliquer CF drill UNIQUEMENT sur la row CATÉGORIES (calcul en devise native).
        # Les autres rows CTRL2 M (COMPTES count, Appariements, Balances/Virements €/Titres €)
        # sont des compteurs ou des equiv_euro → EUR fixe.
        for r in range(cr1, cr2 + 1):
            if ws_ctrl.getCellByPosition(uno_col(10), uno_row(r)).getString().strip() \
                    == 'CATÉGORIES (année glissante)':
                ctrl_cat_row = r
                break

    # 5) CF Budget : body (data rows entre ✓) + pied (Total/Somme/Écart/Total hors)
    body_range = f'{drill_letter}{r1 + 1}:{drill_letter}{r2 - 1}'
    pied_range = f'{drill_letter}{r2 + 1}:{drill_letter}{pied_thc_row}'
    drill_ref = f'${drill_letter}${drill_row}'
    _apply_devise_cf(ws_bud.getCellRangeByName(body_range), drill_ref, devises,
                     lambda c: _drill_style_name(c, 'body'))
    log.append(f'  CF drill body : Budget!{body_range} → {len(devises)} règles')
    _apply_devise_cf(ws_bud.getCellRangeByName(pied_range), drill_ref, devises,
                     lambda c: _drill_style_name(c, 'pied'))
    log.append(f'  CF drill pied : Budget!{pied_range} → {len(devises)} règles')

    # 6) CF drill CTRL2 — uniquement la row CATÉGORIES (calcul en devise native).
    # Drill cell = labels row "Type de contrôle" (r1-2 v3.6 ou r1-1 v1). On
    # détecte par contenu (même logique que set_drill_cells / rewrite_ctrl2).
    if ctrl_cat_row is not None:
        drill_header_row = None
        for r in range(max(1, cr1 - 5), cr1):
            if ws_ctrl.getCellByPosition(uno_col(10), uno_row(r)).getString().strip() \
                    == 'Type de contrôle':
                drill_header_row = r
                break
        if drill_header_row is None:
            drill_header_row = cr1 - 2  # fallback
        ctrl_drill_ref = f'${ctrl_drill_letter}${drill_header_row}'
        cat_cell_range = ws_ctrl.getCellRangeByName(
            f'{ctrl_drill_letter}{ctrl_cat_row}:{ctrl_drill_letter}{ctrl_cat_row}')
        _apply_devise_cf(cat_cell_range, ctrl_drill_ref, devises,
                         lambda c: _drill_style_name(c, 'body'))
        log.append(f'  CF drill CTRL2 : {ctrl_drill_letter}{ctrl_cat_row} (CATÉGORIES)'
                   f' → {len(devises)} règles (ref {ctrl_drill_ref})')


def _set_number_format(doc, cell, fmt_str):
    """Helper : applique un NumberFormat UNO à une cellule."""
    from com.sun.star.lang import Locale
    num_formats = doc._document.NumberFormats
    locale = Locale()
    fmt_idx = num_formats.queryKey(fmt_str, locale, False)
    if fmt_idx == -1:
        fmt_idx = num_formats.addNew(fmt_str, locale)
    cell.NumberFormat = fmt_idx




def rewrite_budget_total_col(ws_bud, nr, log):
    """Budget G col (Total €) : SUMPRODUCT cours du jour via COTcode × COTcours.

    Détecte les bornes de CAT via CATnom (ex: E15:E23). Le body est E16:E22 (entre
    les 2 model rows). Pour chaque ligne, G = SUMPROD(SUMIFS × cours, toutes devises).
    """
    import re
    cat_b = _nr_bounds(nr, 'CATnom')
    if not cat_b:
        log.append('  Budget G (Total €) : skip (CATnom absent)')
        return
    _, nom_letter, r_start, r_end = cat_b
    total_letter = _nr_col_letter(nr, 'CATtotal_euro') or 'G'
    total_col_0 = _col_letter_to_idx(total_letter)
    # Body = rows entre ✓ (r_start + 1 ... r_end - 1)
    body_start, body_end = r_start + 1, r_end - 1
    for r in range(body_start, body_end + 1):
        formula = (f'=SUMPRODUCT(SUMIFS(OPmontant;OPcatégorie;${nom_letter}{r};'
                   f'OPdate;">"&$C$2-365;OPdevise;COTcode)*COTcours)')
        ws_bud.getCellByPosition(total_col_0, uno_row(r)).setFormula(formula)
    log.append(f'  Budget {total_letter}{body_start}:{total_letter}{body_end} : SUMPRODUCT cours du jour × COTcode')


def rewrite_cat_affectation_col(ws_bud, nr, log):
    """Budget Affectation col (P) : ={total_euro}{R}*{pct}{r} pour chaque ligne data.

    R = row de la cat parent (= row courante si CATnom non-vide ; sinon
    dernière row au-dessus avec CATnom non-vide). Permet la ventilation N
    postes : 1 row "tête" avec CATnom + total, suivie de N-1 rows "extras"
    avec CATnom vide + aff% + poste différent. Sur extras, P{r}={total}{parent}
    × {pct}{r} pour propager le total de la cat parent.

    Bornes via CATaffectation. Cols : CATtotal_euro, CATaffectation_pct, CATnom.
    Idempotent.
    """
    aff_b = _nr_bounds(nr, 'CATaffectation')
    if not aff_b:
        log.append('  Budget Affectation : skip (CATaffectation absent)')
        return
    _, aff_letter, r_start, r_end = aff_b
    g_letter = _nr_col_letter(nr, 'CATtotal_euro') or 'G'
    h_letter = _nr_col_letter(nr, 'CATaffectation_pct') or 'H'
    nom_letter = _nr_col_letter(nr, 'CATnom') or 'E'
    aff_col_0 = _col_letter_to_idx(aff_letter)
    nom_col_0 = _col_letter_to_idx(nom_letter)
    body_start, body_end = r_start + 1, r_end - 1
    fixes = 0
    extras_fixed = 0
    parent_row = None
    for r in range(body_start, body_end + 1):
        nom_val = ws_bud.getCellByPosition(nom_col_0, uno_row(r)).getString().strip()
        if nom_val and nom_val != '⚓':
            parent_row = r
            target_row = r
        elif not nom_val and parent_row:
            target_row = parent_row  # extra row : pointer P sur N de la parent
        else:
            continue  # row vide hors ventilation (ex. début avant 1re cat)
        cell = ws_bud.getCellByPosition(aff_col_0, uno_row(r))
        cur = cell.getFormula()
        expected = f'={g_letter}{target_row}*{h_letter}{r}'
        if cur.startswith('=') and cur != expected:
            cell.setFormula(expected)
            fixes += 1
            if target_row != r:
                extras_fixed += 1
    if fixes:
        msg = (f'  Budget {aff_letter}{body_start}:{aff_letter}{body_end} : '
               f'{fixes} formule(s) Affectation rectifiée(s) → ={g_letter}R*{h_letter}r')
        if extras_fixed:
            msg += f' (dont {extras_fixed} extras → R=parent)'
        log.append(msg)


def rewrite_ctrl2_general_col(ws_ctrl, nr, log):
    """Contrôles L col (Général) : all-devise via SUMIFS/COUNTIFS sans filtre devise.

    Après drop natives, layout CTRL2 (ex HEAD → post-drop) :
      COMPTES, CATÉGORIES, Date, Appariements, Balances, Virements €, Titres €,
      Changes Eq €, Total €, (blank), INCONNUS, Synthèse.

    On détecte les rows par contenu col J.
    """
    # Identifier les rows par label
    rows = {}
    for r in range(1, 200):
        lbl = ws_ctrl.getCellByPosition(uno_col(10), uno_row(r)).getString().strip()
        if lbl == 'COMPTES (de début #Solde à fin #Solde)':
            rows['COMPTES'] = r
        elif lbl == 'CATÉGORIES (année glissante)':
            rows['CAT'] = r
        elif lbl == 'Date':
            rows['Date'] = r
        elif lbl.startswith('Appariements'):
            rows['Apparie'] = r
        elif lbl == 'Balances':
            rows['Balance'] = r
        elif lbl == '€':
            # 1er € = Virements € post-drop, 2e = Titres € — mais labels changent à Virements €/Titres €
            pass  # noop — après drop natives, les '€' restent. On gère via offset.
        elif lbl == 'Changes Eq €':
            rows['ChgEqu'] = r
        elif lbl == 'Total €':
            rows['TotalEu'] = r
    # Détection Virements €/Titres € — soit '€' (juste après drop natives),
    # soit 'Virements €'/'Titres €' (migrate déjà passé). Idempotence.
    eur_rows = []
    for r in range(1, 200):
        lbl = ws_ctrl.getCellByPosition(uno_col(10), uno_row(r)).getString().strip()
        if lbl == '€':
            eur_rows.append(r)
    if len(eur_rows) == 2:
        ws_ctrl.getCellByPosition(uno_col(10), uno_row(eur_rows[0])).setString('Virements €')
        ws_ctrl.getCellByPosition(uno_col(10), uno_row(eur_rows[1])).setString('Titres €')
        rows['Virements'] = eur_rows[0]
        rows['Titres'] = eur_rows[1]
        log.append(f'  CTRL2 J{eur_rows[0]} → "Virements €", J{eur_rows[1]} → "Titres €"')
    else:
        # Déjà renommés ? Re-scanner par nouveaux labels
        for r in range(1, 200):
            lbl = ws_ctrl.getCellByPosition(uno_col(10), uno_row(r)).getString().strip()
            if lbl == 'Virements €':
                rows['Virements'] = r
            elif lbl == 'Titres €':
                rows['Titres'] = r
        if 'Virements' not in rows or 'Titres' not in rows:
            log.append(f'  CTRL2 : {len(eur_rows)} row "€" + {"V" if "Virements" in rows else "?"}{"T" if "Titres" in rows else "?"} — skip')
            return

    # Layout-agnostic : L/M cols via NRs (CTRL2general/CTRL2drill)
    l_letter = _nr_col_letter(nr, 'CTRL2general') or 'L'
    m_letter = _nr_col_letter(nr, 'CTRL2drill') or 'M'
    l_col_0 = _col_letter_to_idx(l_letter)
    m_col_0 = _col_letter_to_idx(m_letter)
    def L(r): return ws_ctrl.getCellByPosition(l_col_0, uno_row(r))
    def M(r): return ws_ctrl.getCellByPosition(m_col_0, uno_row(r))
    # Header row (drill cell) : détection layout-aware via le contenu col J
    # 'Type de contrôle' (même logique que set_drill_cells). Couvre à la fois :
    #  - v3.6 avec row vide entre labels et ⚓ → labels @ r1-2
    #  - v1 migré où ⚓ est posée directement sous les labels → labels @ r1-1
    ctrl2_type_b = _nr_bounds(nr, 'CTRL2type')
    ctrl2_r1 = ctrl2_type_b[2] if ctrl2_type_b else rows.get('COMPTES', 10)
    drill_header_row = None
    for r in range(max(1, ctrl2_r1 - 5), ctrl2_r1):
        if ws_ctrl.getCellByPosition(uno_col(10), uno_row(r)).getString().strip() \
                == 'Type de contrôle':
            drill_header_row = r
            break
    if drill_header_row is None:
        drill_header_row = ctrl2_r1 - 2  # fallback
    if 'COMPTES' in rows:
        L(rows['COMPTES']).setFormula(
            '=COUNTIFS(CTRL1controle;"Oui")-COUNTIFS(CTRL1controle;"Oui";CTRL1ecart;0)')
        # M COMPTES drill : NR-based auto-extend (aligné avec GUI _save_accounts #18b)
        M(rows['COMPTES']).setFormula(
            f'=COUNTIFS(CTRL1devise;{m_letter}${drill_header_row};CTRL1controle;"Oui")'
            f'-COUNTIFS(CTRL1devise;{m_letter}${drill_header_row};CTRL1controle;"Oui";CTRL1ecart;0)')
    if 'CAT' in rows:
        # Écart CATÉGORIES : CTRL2 = résumé d'erreurs toutes feuilles confondues.
        # Général L pointe le calcul Budget G (Écart EUR all-devise cours du jour).
        # M drill = calcul direct en devise native M$header_row (pas d'équiv Budget).
        # Tolérance <1 EUR sur K33 pour absorber le bruit FP du SUMPRODUCT Budget
        # (typiquement ~0.5 EUR sur des totaux ~2000 EUR).
        import re as _re2
        cat_end = None
        if nr.hasByName('CATnom'):
            _m = _re2.match(r'\$[^.]+\.\$[A-Z]+\$\d+:\$[A-Z]+\$(\d+)',
                            nr.getByName('CATnom').Content)
            if _m:
                cat_end = int(_m.group(1))
        bud_ecart_row = (cat_end + 3) if cat_end else 28          # Écart drill EUR (G)
        cat_total_hors_row = (cat_end + 4) if cat_end else 29     # Total hors @ (G/I)
        # Écart Affectation Budget C{posts_end + 4} (= ROUND(C$8 - I$29; 2))
        posts_end = None
        if nr.hasByName('POSTESmontant'):
            _mp = _re2.match(r'\$[^.]+\.\$[A-Z]+\$\d+:\$[A-Z]+\$(\d+)',
                             nr.getByName('POSTESmontant').Content)
            if _mp:
                posts_end = int(_mp.group(1))
        posts_ecart_row = (posts_end + 4) if posts_end else 11
        cat_r = rows['CAT']
        # L_cat = somme abs de 3 écarts Budget (synthèse triple) :
        #   A = écart drill EUR (Budget G{bud_ecart_row})
        #   B = écart Affectation totale (Budget I{...} - G{...} sur ligne Total hors @)
        #   C = écart Affectation par poste (Budget C{posts_ecart_row})
        # K_cat ✓/⚠ avec tolérance 1 EUR sur le cumul.
        L(cat_r).setFormula(
            f'=ABS($Budget.G${bud_ecart_row})'
            f'+ABS($Budget.I${cat_total_hors_row}-$Budget.G${cat_total_hors_row})'
            f'+ABS($Budget.C${posts_ecart_row})')
        # K{cat_r} : tolérance 1 EUR (comme avant : alarme si > 1 EUR cumulé)
        ws_ctrl.getCellByPosition(uno_col(11), uno_row(cat_r)).setFormula(
            f'=IF(ABS(L{cat_r})<1;"✓";"⚠")')
        # Drill M : devise native M$header_row. Convention sign = Budget F$écart
        # (cats - non-spécial = -uncategorized), cohérent avec L pointeur Budget.
        header_row = drill_header_row
        M(cat_r).setFormula(
            f'=ROUND(SUMPRODUCT(SUMIFS(OPmontant;OPdevise;{m_letter}${header_row};'
            f'OPcatégorie;CATnom;OPdate;">"&$Budget.$C$2-365))'
            f'-SUMIFS(OPmontant;OPdevise;{m_letter}${header_row};'
            f'OPcatégorie;"<>"&Spéciale;OPdate;">"&$Budget.$C$2-365);2)')
    # Date inchangé (all-devise). Apparie / Virements / Titres / ChgEqu M :
    # migration idempotente des refs drill obsolètes ({m_letter}$OLD →
    # {m_letter}${drill_header_row}) dans `OPdevise;{m_letter}$OLD`.
    import re as _re3
    _drill_re = _re3.compile(
        rf'(OPdevise[;,]\s*{_re3.escape(m_letter)}\$)(\d+)')
    def _migrate_drill_ref(key, label):
        if key not in rows:
            return
        cell = M(rows[key])
        f = cell.getFormula()
        if not f.startswith('='):
            return
        new_f = _drill_re.sub(
            lambda m: f'{m.group(1)}{drill_header_row}'
                      if int(m.group(2)) != drill_header_row else m.group(0),
            f)
        if new_f != f:
            cell.setFormula(new_f)
            log.append(f'  CTRL2 {m_letter}{rows[key]} ({label}) : ref drill migrée → ${m_letter}${drill_header_row}')
    _migrate_drill_ref('Apparie',   'Apparie')
    _migrate_drill_ref('Virements', 'Virements €')
    _migrate_drill_ref('Titres',    'Titres €')
    _migrate_drill_ref('ChgEqu',    'Changes Eq €')
    if 'Balance' in rows:
        # Balances count on Virements€, Titres€, Changes (3 rows)
        if 'Virements' in rows and 'ChgEqu' in rows:
            vr, cr = rows['Virements'], rows['ChgEqu']
            L(rows['Balance']).setFormula(f'=3-COUNTIFS(L{vr}:L{cr};0)')
    if 'Virements' in rows:
        L(rows['Virements']).setFormula(
            '=ROUND(SUMIFS(OPequiv_euro;OPcatégorie;"@Virement");0)')
    if 'Titres' in rows:
        L(rows['Titres']).setFormula(
            '=ROUND(SUMIFS(OPequiv_euro;OPcatégorie;"*titres");0)')
    # Changes Eq € L : inchangé (déjà all-devise)
    if 'TotalEu' in rows:
        # Total € = V€ + T€ + Changes
        vr = rows.get('Virements'); tr = rows.get('Titres'); cr = rows.get('ChgEqu')
        if vr and tr and cr:
            L(rows['TotalEu']).setFormula(f'={l_letter}{vr}+{l_letter}{tr}+{l_letter}{cr}')
            M_total = ws_ctrl.getCellByPosition(m_col_0, uno_row(rows['TotalEu']))
            M_total.setFormula(f'={m_letter}{vr}+{m_letter}{tr}+{m_letter}{cr}')
    # M col Balances : COUNTA sur label rows
    if 'Balance' in rows and 'Virements' in rows and 'ChgEqu' in rows:
        vr, cr = rows['Virements'], rows['ChgEqu']
        M_bal = ws_ctrl.getCellByPosition(m_col_0, uno_row(rows['Balance']))
        M_bal.setFormula(f'=COUNTA($J{vr}:$J{cr})-COUNTIFS({m_letter}{vr}:{m_letter}{cr};0)')
    log.append(f'  CTRL2 L col : formules all-devise réécrites pour rows {rows}')


def cleanup_dead_nrs(nr, log):
    """Supprime les named ranges pointant sur #REF! (cadavres d'anciennes devises)."""
    to_remove = []
    for i in range(nr.Count):
        item = nr.getByIndex(i)
        if '#REF!' in item.Content:
            to_remove.append(item.Name)
    for name in to_remove:
        nr.removeByName(name)
        log.append(f'  NR mort supprimé : {name}')


def bump_schema_version(nr, log):
    """Bump SCHEMA_VERSION named range constant de 1 à 2."""
    if not nr.hasByName('SCHEMA_VERSION'):
        log.append('  SCHEMA_VERSION absent — skip bump')
        return
    # Named ranges pour constantes utilisent un format particulier (valeur numérique)
    # On le supprime et recrée avec nouveau contenu
    cur = nr.getByName('SCHEMA_VERSION').Content
    if cur == '2':
        return
    nr.removeByName('SCHEMA_VERSION')
    pos = uno.createUnoStruct('com.sun.star.table.CellAddress')
    pos.Sheet = 0; pos.Column = 0; pos.Row = 0
    nr.addNewByName('SCHEMA_VERSION', '2', pos, 0)
    log.append(f'  SCHEMA_VERSION : {cur} → 2')


# ========== Entry ==========

def migrate(path):
    path = Path(path)
    print(f'\n🔧 Migration SCHEMA_VERSION 1 → 2 : {path}')
    log = []
    # Pré-cleanup XML : retire toute CF drill legacy (approche A ou B rerun),
    # pour repartir d'un état propre avant que UNO re-crée les CF clean.
    _xml_cleanup_drill_cf(path, log)
    # Pré-lecture CONV (head + body) depuis le template adjacent (UNO
    # secondaire avant ouverture de la cible). Skip si cible == template ou
    # template absent ; conv_data reste None → coquille vide posée par
    # ensure_conventions_table, à remplir manuellement.
    conv_data = read_conv_from_template(path, log)
    with UnoDocument(path) as doc:
        xdoc = doc._document
        nr = xdoc.NamedRanges
        cr = doc.cr
        ws_bud = doc.get_sheet('Budget')
        ws_ops = doc.get_sheet('Opérations')
        ws_ctrl = doc.get_sheet('Contrôles')

        # A. Fuse cols devises (DEV multi-devise → 1 col drill). No-op si déjà fusé.
        ensure_eur_cotation(doc.get_sheet('Cotations'), nr, log)
        fuse_devise_cols_budget(ws_bud, nr, log)
        fuse_devise_cols_ctrl(ws_ctrl, nr, log)
        normalize_total_col_fill(ws_bud, nr, log)
        if hasattr(cr, 'refresh'):
            cr.refresh()
        # B. Rename NRs (CATeur → CATmontant, CTRL2eur → CTRL2drill) AVANT ensure,
        #    pour que ensure_named_ranges voie CATmontant déjà positionné au bon col.
        rename_drill_nrs(nr, log)
        # C. Ensure remaining NRs (POSTES + CATmontant si pas venu du rename)
        ensure_named_ranges(xdoc, nr, log)
        # C'. Ancres ⚓ : rename ✓→⚓ + étendre NRs pour englober les sentinels.
        # Doit précéder ensure_conventions_table car la pose des ⚓ PAT peut
        # insérer une row (shift des rows du dessous) qui modifie pat_r2 ;
        # CONV doit être calé sur pat_r2 FINAL. CONVnom n'existe pas encore :
        # ensure_anchors le skippe via "[skip] Patrimoine/CONVnom : ref_nr absent".
        ensure_anchors(xdoc, nr, log)
        # C''. Bootstrap tableau CONV (Patrimoine) si absent — utilise le
        # pat_r2 final, offset +8 garanti.
        ensure_conventions_table(xdoc, nr, log)
        # C''bis. Extension PAT (PAText1..PAText4) — décoratif, étend le tableau
        # Patrimoine sur F:I pour cohérence visuelle (grille hair).
        ensure_pat_extension_nrs(xdoc, nr, log)
        # C'''. Remplissage CONV (head + body) depuis le template adjacent
        # (si lu en préambule). Filtre formules (comme tool_sync_from_witness).
        if conv_data:
            write_conv_to_target(xdoc, nr, conv_data, log)
        if hasattr(cr, 'refresh'):
            cr.refresh()
        stash_a_formulas(doc, nr, log)
        if hasattr(cr, 'refresh'):
            cr.refresh()
        # D. @ rename
        migrate_budget_cats(ws_bud, log)
        migrate_operations_cats(ws_ops, cr, log)
        migrate_controles_formulas(ws_ctrl, nr, log)
        migrate_budget_totals(ws_bud, nr, log)
        # E. Drill refonte (CTRL2 drop natives + drill cells + formats + CF)
        drop_native_balance_rows(ws_ctrl, nr, log)
        add_drill_nrs(ws_ctrl, nr, log)
        setup_drill_cells(doc, ws_bud, ws_ctrl, nr, log)
        setup_drill_formats(doc, ws_bud, ws_ctrl, nr, log)
        rewrite_budget_total_col(ws_bud, nr, log)
        rewrite_cat_affectation_col(ws_bud, nr, log)
        rewrite_ctrl2_general_col(ws_ctrl, nr, log)
        # Compact CTRL2 — fait APRÈS les rewrites, sinon les refs M$OLD vers
        # rows à supprimer deviennent #REF! (rewrite_ctrl2_general_col migre
        # ces refs vers le drill_header_row courant).
        compact_ctrl2_layout(ws_ctrl, log)
        cleanup_dead_nrs(nr, log)
        bump_schema_version(nr, log)

        # Calcul positions Écart + cols drill/total pour CF sqref (tout dynamique via NR)
        import re as _re
        def _end(name):
            if not nr.hasByName(name):
                return None
            m = _re.match(r'\$[^.]+\.\$[A-Z]+\$\d+:\$[A-Z]+\$(\d+)',
                          nr.getByName(name).Content)
            return int(m.group(1)) if m else None
        cat_end_row = _end('CATnom')
        posts_end_row = _end('POSTESmontant')
        cat_ecart_row = (cat_end_row + 3) if cat_end_row else None   # Écart = Total+2
        posts_ecart_row = (posts_end_row + 4) if posts_end_row else None  # Écart Affectation
        ecart_drill_letter = _nr_col_letter(nr, 'CATmontant') or 'F'
        ecart_total_letter = _nr_col_letter(nr, 'CATtotal_euro') or 'G'
        posts_col_letter = _nr_col_letter(nr, 'POSTESmontant') or 'C'

        doc.save()

    # Post-process XML : rebuilder le sqref CF alerte Écart (dynamique)
    _xml_rebuild_ecart_cf_sqref(path, cat_ecart_row, posts_ecart_row,
                                ecart_drill_letter, ecart_total_letter, posts_col_letter, log)
    # Post-process XML : retirer CF obsolètes (refonte drill multi-devise)
    _xml_remove_obsolete_cf(path, log)

    # Post-process JSON : renommer les catégories structurelles dans le mapping
    # de catégorisation (sinon l'auto-fix de cohérence GUI purgerait ces patterns
    # comme orphelins puisque Budget contient désormais @<cat>).
    _migrate_category_mappings(path, log)

    for line in log:
        print(line)
    print(f'✅ Migration terminée ({len(log)} opérations)')


def _migrate_category_mappings(xlsm_path, log):
    """Renomme les catégories structurelles dans config_category_mappings.json.

    Cherche le JSON dans le même dossier que le xlsm. Pour chaque pattern dont
    la `category` figure dans RENAME_CATS, applique le rename `<cat>` → `@<cat>`.
    Sauvegarde l'ancien JSON en `.bak` si modifications.
    """
    import json
    json_path = Path(xlsm_path).parent / 'config_category_mappings.json'
    if not json_path.exists():
        return
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        log.append(f'  [warn] config_category_mappings.json non lu : {e}')
        return

    renamed = 0
    for site, patterns in data.items():
        if not isinstance(patterns, list):
            continue
        for p in patterns:
            cat = p.get('category')
            if cat in RENAME_CATS:
                p['category'] = RENAME_CATS[cat]
                renamed += 1

    if not renamed:
        return

    bak = json_path.with_suffix('.json.bak')
    import shutil
    shutil.copy2(json_path, bak)
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write('\n')
    log.append(f'  config_category_mappings.json : {renamed} pattern(s) renommé(s) (cat → @cat)')


if __name__ == '__main__':
    args = sys.argv[1:]
    if len(args) == 2 and args[0] == '--check':
        # Mode read-only : validate_anchors + validate_structure, rapport, no-op
        from inc_check_integrity import validate_anchors, validate_structure
        path = Path(args[1])
        print(f'🔍 Check {path}')
        with UnoDocument(path) as doc:
            xdoc = doc._document
            ok_s, errs_s, warns_s = validate_structure(xdoc)
            ok_a, errs_a, warns_a = validate_anchors(xdoc)
        errs = errs_s + errs_a  # validate_structure dédoublonne déjà via appel interne ; ici on affiche tout
        warns = warns_s + warns_a
        # Dédup
        errs = list(dict.fromkeys(errs))
        warns = list(dict.fromkeys(warns))
        if errs:
            print(f'\n✗ {len(errs)} erreur(s) :')
            for e in errs:
                print(f'  {e}')
        if warns:
            print(f'\n⚠ {len(warns)} warning(s) :')
            for w in warns:
                print(f'  {w}')
        if not errs and not warns:
            print('\n✓ Classeur conforme (anchors + structure)')
        sys.exit(0 if not errs else 1)
    if len(args) != 1:
        print('Usage:')
        print('  tool_migrate_schema_v2.py <xlsm_path>       # migrate SCHEMA_VERSION 1 → 2')
        print('  tool_migrate_schema_v2.py --check <xlsm>    # read-only validate_anchors + structure')
        sys.exit(1)
    migrate(args[0])
