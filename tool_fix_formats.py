#!/usr/bin/env python3
"""
tool_fix_formats.py — Corrige les formats de cellules dans comptes.xlsm

Usage:
  python3 tool_fix_formats.py comptes.xlsm           # dry run
  python3 tool_fix_formats.py comptes.xlsm --apply   # applique les corrections

Corrections toutes feuilles :
  - Montants : format français (virgule décimale, espace milliers)
  - Dates : DD/MM/YY
  - Avoirs : fond gris E+K pour non-EUR, format devise K, format EUR L
"""

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from inc_excel_schema import (
    AvCol, AV_FIRST_ROW, SHEET_AVOIRS,
    uno_col, uno_row,
)
from inc_uno import get_named_range_pos
from inc_check_integrity import validate_structure
from inc_formats import (
    devise_format, _load_decimals, _DEFAULT_DECIMALS,
    FORMATS_DEVISE, FORMAT_EUR, FORMAT_EUR_RED, FORMAT_DATE, GRIS, BLANC,
)

# Cache format strings pour comparaison (LO assigne des IDs différents
# pour des formats visuellement identiques selon la locale)
_fmt_str_cache = {}


def _normalize_fmt(fmt_str):
    """Normalise un format LO pour comparaison.

    Gère deux variantes du même format visuel :
    - '\\<espace>' vs '<espace>' avant symboles devise (encodage LO)
    - US Excel (#,##0.00) vs FR UNO (#\xa0##0,00) — même rendu en locale FR
    """
    import re
    s = fmt_str.replace('\\ ', ' ')
    # US Excel → FR UNO : #,##0.00 → # ##0,00  (en protégeant les [$...])
    if '#,##0' in s:
        parts = re.split(r'(\[\$[^\]]*\])', s)
        converted = []
        for part in parts:
            if part.startswith('[$'):
                converted.append(part)
            else:
                # , → placeholder, . → , (décimal), placeholder → \xa0
                part = part.replace(',', '\x01').replace('.', ',').replace('\x01', '\xa0')
                converted.append(part)
        s = ''.join(converted)
    return s


def _fmt_eq(formats, fmt_id_a, fmt_id_b):
    """True si deux format IDs produisent le même rendu."""
    if fmt_id_a == fmt_id_b:
        return True
    for fid in (fmt_id_a, fmt_id_b):
        if fid not in _fmt_str_cache:
            _fmt_str_cache[fid] = formats.getByKey(fid).FormatString
    return _normalize_fmt(_fmt_str_cache[fmt_id_a]) == _normalize_fmt(_fmt_str_cache[fmt_id_b])


def fix_avoirs(doc, apply):
    """Corrige les formats de la feuille Avoirs."""
    ws = doc.get_sheet(SHEET_AVOIRS)
    fixes = 0

    # Bornes via named ranges START_AVR / END_AVR
    start_avr = get_named_range_pos(doc.document, 'START_AVR')
    end_avr = get_named_range_pos(doc.document, 'END_AVR')
    first_row = (start_avr[2] + 1 + 1) if start_avr else AV_FIRST_ROW  # 0-indexed → 1-indexed, +1 skip header
    end_row = (end_avr[2] + 1) if end_avr else first_row + 200  # 0-indexed → 1-indexed

    formats = doc.document.getNumberFormats()
    fmt_date = doc.register_number_format(FORMAT_DATE)
    fmt_eur = doc.register_number_format(FORMAT_EUR)
    fmt_cache = {}
    for devise, fmt_str in FORMATS_DEVISE.items():
        fmt_cache[devise] = doc.register_number_format(fmt_str)

    for r in range(AV_FIRST_ROW, end_row):
        intitule = ws.getCellByPosition(uno_col(AvCol.INTITULE), uno_row(r)).getString().strip()
        if not intitule:
            continue

        devise = ws.getCellByPosition(uno_col(AvCol.DEVISE), uno_row(r)).getString().strip()
        r0 = uno_row(r)
        is_non_eur = devise and devise != 'EUR'
        row_fixes = []

        # Date J
        j_cell = ws.getCellByPosition(uno_col(AvCol.DATE_SOLDE), r0)
        if not _fmt_eq(formats, j_cell.NumberFormat, fmt_date):
            row_fixes.append('J:date')
            if apply:
                j_cell.NumberFormat = fmt_date

        # Montant K
        k_cell = ws.getCellByPosition(uno_col(AvCol.MONTANT_SOLDE), r0)
        expected_k = fmt_cache.get(devise, fmt_eur)
        if not _fmt_eq(formats, k_cell.NumberFormat, expected_k):
            row_fixes.append(f'K:fmt({devise})')
            if apply:
                k_cell.NumberFormat = expected_k

        # Equiv EUR L
        l_cell = ws.getCellByPosition(uno_col(AvCol.FORMULE_L), r0)
        if not _fmt_eq(formats, l_cell.NumberFormat, fmt_eur):
            row_fixes.append('L:fmt(EUR)')
            if apply:
                l_cell.NumberFormat = fmt_eur

        # Fond gris E
        e_cell = ws.getCellByPosition(uno_col(AvCol.DEVISE), r0)
        if is_non_eur and e_cell.CellBackColor != GRIS:
            row_fixes.append('E:gris')
            if apply:
                e_cell.CellBackColor = GRIS
        elif not is_non_eur and e_cell.CellBackColor == GRIS:
            row_fixes.append('E:blanc')
            if apply:
                e_cell.CellBackColor = 0xFFFFFF

        # Fond gris K
        if is_non_eur and k_cell.CellBackColor != GRIS:
            row_fixes.append('K:gris')
            if apply:
                k_cell.CellBackColor = GRIS
        elif not is_non_eur and k_cell.CellBackColor == GRIS:
            row_fixes.append('K:blanc')
            if apply:
                k_cell.CellBackColor = 0xFFFFFF

        if row_fixes:
            fixes += 1
            print(f"  {intitule:<35} {devise:<5} → {', '.join(row_fixes)}")

    return fixes


def fix_budget(doc, apply):
    """Corrige les formats du tableau Catégories dans Budget.

    Chaque colonne devise reçoit le format de sa devise + fond gris si non-EUR.
    Appliqué sur toutes les lignes entre START_CAT et END_CAT (données + Total).
    """
    from inc_excel_schema import SHEET_BUDGET

    ws = doc.get_sheet(SHEET_BUDGET)

    # Trouver START_CAT / END_CAT via named ranges UNO
    start_cat = get_named_range_pos(doc.document, 'START_CAT')
    if not start_cat:
        print("  (START_CAT absent — skip)")
        return 0

    cat_col = start_cat[1] + 1  # 0-indexed → 1-indexed
    header_row = start_cat[2]   # 0-indexed row = 1-indexed - 1 = header
    data_start = start_cat[2] + 2  # 1-indexed: start_row + 1
    # Trouver "Montant Euros" pour arrêter le gris AVANT (cette ligne est en EUR)
    data_end = data_start + 100      # format devise
    data_end_gris = data_start + 100  # fond gris (exclu Montant Euros)
    for r in range(data_start, data_start + 100):
        val = ws.getCellByPosition(cat_col - 1, r - 1).getString().strip()  # 0-indexed
        if val.startswith('Montant'):
            data_end = r  # exclure Montant Euros du format devise
            data_end_gris = r  # exclure du gris aussi
            break
        elif val == 'Total':
            # Continuer — on veut inclure Total et les lignes après
            pass

    # Scanner les devises depuis le header
    devises = []
    for c in range(cat_col + 1, cat_col + 30):
        val = ws.getCellByPosition(c - 1, header_row - 1).getString().strip()  # 0-indexed
        if not val or val.startswith('Équiv') or val.startswith('Equiv') or val.startswith('Affectation'):
            break
        devises.append((c, val))

    if not devises:
        print("  (aucune devise trouvée)")
        return 0

    # Enregistrer les formats
    formats = doc.document.getNumberFormats()
    fmt_cache = {}
    for devise, fmt_str in FORMATS_DEVISE.items():
        fmt_cache[devise] = doc.register_number_format(fmt_str)
    fmt_eur = doc.register_number_format(FORMAT_EUR)

    fixes = 0
    for col_1idx, devise in devises:
        expected_fmt = fmt_cache.get(devise, fmt_eur)
        is_non_eur = devise != 'EUR'
        col_fixes = 0

        c0 = col_1idx - 1  # 0-indexed
        for r in range(data_start, data_end):
            r0 = r - 1  # 0-indexed
            cell = ws.getCellByPosition(c0, r0)

            # Format devise
            if not _fmt_eq(formats, cell.NumberFormat, expected_fmt):
                col_fixes += 1
                if apply:
                    cell.NumberFormat = expected_fmt

            # Fond gris (zone plus restreinte, exclut Montant Euros)
            if is_non_eur and r < data_end_gris and cell.CellBackColor != GRIS:
                col_fixes += 1
                if apply:
                    cell.CellBackColor = GRIS

        # Ligne "Montant Euros" : format EUR, pas de gris
        if data_end < data_start + 100:
            cell = ws.getCellByPosition(c0, data_end - 1)
            if not _fmt_eq(formats, cell.NumberFormat, fmt_eur):
                col_fixes += 1
                if apply:
                    cell.NumberFormat = fmt_eur

        if col_fixes:
            fixes += col_fixes
            print(f"  col {devise:<5} → {col_fixes} cellules")

    return fixes


def fix_plus_value(doc, apply):
    """Corrige les formats de la feuille Plus_value.

    Pour chaque ligne avec devise :
    - Dates G et J : DD/MM/YY
    - Montants H et I : format devise
    - Solde K : format EUR (valeur en euros)
    - Devise D : fond gris si non-EUR
    """
    from inc_excel_schema import PvCol, SHEET_PLUS_VALUE

    ws = doc.get_sheet(SHEET_PLUS_VALUE)

    start_pvl = get_named_range_pos(doc.document, 'START_PVL')
    end_pvl = get_named_range_pos(doc.document, 'END_PVL')
    if not start_pvl:
        print("  (START_PVL absent — skip)")
        return 0

    fixes = 0

    # Marqueurs de section : label en col A (pas en col C)
    SECTION_IDS = {'portefeuilles', 'métaux', 'crypto', 'devises'}
    for r in range(1, start_pvl[2] + 2):  # scanner avant START_PVL
        r0 = r - 1
        val_a = ws.getCellByPosition(uno_col(PvCol.SECTION), r0).getString().strip()
        val_c = ws.getCellByPosition(uno_col(PvCol.LIGNE), r0).getString().strip()
        if val_a in SECTION_IDS and val_c.startswith('Les '):
            # Déplacer label de C vers A
            print(f"  marqueur '{val_c}' : col C → col A")
            ws.getCellByPosition(uno_col(PvCol.SECTION), r0).setString(val_c)
            ws.getCellByPosition(uno_col(PvCol.SECTION), r0).CharWeight = 150  # BOLD
            ws.getCellByPosition(uno_col(PvCol.LIGNE), r0).setString('')
            fixes += 1

    data_start = start_pvl[2] + 1 + 1  # 0-indexed → 1-indexed, +1 pour skip header
    # END_PVL peut être corrompu (row 6 au lieu de 123) → scanner jusqu'à la fin
    end_row_hint = (end_pvl[2] + 1) if end_pvl else data_start + 200  # 0-indexed → 1-indexed
    if end_row_hint < data_start + 10:
        end_row_hint = data_start + 200
    data_end = end_row_hint + 1

    formats = doc.document.getNumberFormats()
    fmt_date = doc.register_number_format(FORMAT_DATE)
    fmt_eur = doc.register_number_format(FORMAT_EUR)
    fmt_eur_red = doc.register_number_format(FORMAT_EUR_RED)
    fmt_cache = {}
    fmt_cache_red = {'EUR': fmt_eur_red}
    for devise, fmt_str in FORMATS_DEVISE.items():
        fmt_cache[devise] = doc.register_number_format(fmt_str)
        if devise != 'EUR':
            fmt_cache_red[devise] = doc.register_number_format(f'{fmt_str};[RED]\\-{fmt_str}')

    for r in range(data_start, data_end):
        r0 = r - 1  # 0-indexed
        devise = ws.getCellByPosition(uno_col(PvCol.DEVISE), r0).getString().strip()
        if not devise:
            continue

        ligne = ws.getCellByPosition(uno_col(PvCol.LIGNE), r0).getString().strip()
        section = ws.getCellByPosition(uno_col(PvCol.SECTION), r0).getString().strip()
        is_non_eur = devise != 'EUR'
        row_fixes = []

        # Portefeuilles : H et I en devise native
        # Métaux, crypto, devises : H et I en EUR (formules SUMIF sur OPEquiv)
        is_devise_section = section == 'portefeuilles'
        expected_hi_fmt = fmt_cache.get(devise, fmt_eur) if is_devise_section else fmt_eur
        hi_label = devise if is_devise_section else 'EUR'
        # E et K : toujours en devise de la ligne
        expected_devise_fmt = fmt_cache.get(devise, fmt_eur)
        expected_devise_red = fmt_cache_red.get(devise, fmt_eur_red)

        # Date G (DATE_INIT)
        cell = ws.getCellByPosition(uno_col(PvCol.DATE_INIT), r0)
        if not _fmt_eq(formats, cell.NumberFormat, fmt_date):
            row_fixes.append('G:date')
            if apply:
                cell.NumberFormat = fmt_date

        # PVL E — en devise de la ligne (rouge négatif)
        expected_devise_red = fmt_cache_red.get(devise, fmt_eur_red)
        cell = ws.getCellByPosition(uno_col(PvCol.PVL), r0)
        if not _fmt_eq(formats, cell.NumberFormat, expected_devise_fmt) and \
           not _fmt_eq(formats, cell.NumberFormat, expected_devise_red):
            row_fixes.append(f'E:fmt({devise})')
            if apply:
                cell.NumberFormat = expected_devise_red

        # Montant H (MONTANT_INIT)
        cell = ws.getCellByPosition(uno_col(PvCol.MONTANT_INIT), r0)
        if not _fmt_eq(formats, cell.NumberFormat, expected_hi_fmt):
            row_fixes.append(f'H:fmt({hi_label})')
            if apply:
                cell.NumberFormat = expected_hi_fmt

        # Sigma I
        cell = ws.getCellByPosition(uno_col(PvCol.SIGMA), r0)
        if not _fmt_eq(formats, cell.NumberFormat, expected_hi_fmt):
            row_fixes.append(f'I:fmt({hi_label})')
            if apply:
                cell.NumberFormat = expected_hi_fmt

        # Date J (DATE_SOLDE)
        cell = ws.getCellByPosition(uno_col(PvCol.DATE_SOLDE), r0)
        if not _fmt_eq(formats, cell.NumberFormat, fmt_date):
            row_fixes.append('J:date')
            if apply:
                cell.NumberFormat = fmt_date

        # Solde K — en devise de la ligne (rouge négatif)
        cell = ws.getCellByPosition(uno_col(PvCol.SOLDE), r0)
        if not _fmt_eq(formats, cell.NumberFormat, expected_devise_fmt) and \
           not _fmt_eq(formats, cell.NumberFormat, expected_devise_red):
            row_fixes.append(f'K:fmt({devise})')
            if apply:
                cell.NumberFormat = expected_devise_red

        # Fond blanc D-K pour lignes données (hors pieds portefeuille)
        # Le gris devise se superpose au blanc → ne mettre blanc que sur les colonnes non-gris
        # Note : l'en-tête portefeuille (LIGNE='Portefeuille') n'a pas de devise
        # → skippée par le 'if not devise: continue' plus haut
        PV_PIEDS = {'Total', '#Solde Opérations', 'Retenu'}
        if ligne not in PV_PIEDS:
            ALL_DK = {PvCol.DEVISE, PvCol.PVL, PvCol.PCT,
                      PvCol.DATE_INIT, PvCol.MONTANT_INIT, PvCol.SIGMA,
                      PvCol.DATE_SOLDE, PvCol.SOLDE}
            # Colonnes qui seront grisées (non-EUR)
            if is_non_eur:
                gris_set = {PvCol.DEVISE, PvCol.PVL, PvCol.SOLDE}
                if is_devise_section:
                    gris_set |= {PvCol.MONTANT_INIT, PvCol.SIGMA}
            else:
                gris_set = set()
            for col_pvl in sorted(ALL_DK - gris_set):
                cell = ws.getCellByPosition(uno_col(col_pvl), r0)
                if cell.CellBackColor != BLANC:
                    row_fixes.append(f'{chr(64+col_pvl)}:blanc')
                    if apply:
                        cell.CellBackColor = BLANC

        # Fond gris non-EUR
        if is_non_eur:
            # D (devise), E (PVL), K (SOLDE) : toujours gris (montants en devise)
            # H, I : gris seulement pour portefeuilles (montants en devise native)
            GRIS_COLS = [PvCol.DEVISE, PvCol.PVL, PvCol.SOLDE]
            if is_devise_section:
                GRIS_COLS += [PvCol.MONTANT_INIT, PvCol.SIGMA]
            # Colonnes jamais grisées
            NO_GRIS_COLS = [PvCol.PCT, PvCol.DATE_INIT, PvCol.DATE_SOLDE]
            if not is_devise_section:
                NO_GRIS_COLS += [PvCol.MONTANT_INIT, PvCol.SIGMA]

            for col_pvl in GRIS_COLS:
                cell = ws.getCellByPosition(uno_col(col_pvl), r0)
                if cell.CellBackColor != GRIS:
                    row_fixes.append(f'{chr(64+col_pvl)}:gris')
                    if apply:
                        cell.CellBackColor = GRIS
            for col_pvl in NO_GRIS_COLS:
                cell = ws.getCellByPosition(uno_col(col_pvl), r0)
                if cell.CellBackColor == GRIS:
                    row_fixes.append(f'{chr(64+col_pvl)}:-gris')
                    if apply:
                        cell.CellBackColor = BLANC

        if row_fixes:
            fixes += 1
            print(f"  {ligne:<20} {devise:<5} → {', '.join(row_fixes)}")

    return fixes


def fix_ctrl2(doc, apply):
    """Corrige les formats du tableau CTRL2 dans Contrôles.

    Structure CTRL2 (offsets depuis header h) :
      h+0  : header devises
      h+1  : taux
      h+2  : COMPTES (entier)
      h+3  : CATÉGORIES — montant devise, gris non-EUR
      h+4  : Date (vide — seul O général est pertinent)
      h+5  : Appariements (entier)
      h+6  : Balances (entier)
      h+7  : Virements — montant devise, gris non-EUR
      h+8  : € (equiv) — montant EUR
      h+9  : Titres — montant devise, gris non-EUR
      h+10 : € (equiv) — montant EUR
      h+11 : Changes Eq € — montant EUR
      h+12 : Total € — montant EUR
    """
    from inc_excel_schema import SHEET_CONTROLES

    ws = doc.get_sheet(SHEET_CONTROLES)

    # Trouver le header CTRL2 via named range START_CTRL2
    # Convention : START_CTRL2 pointe sur h+2 (données), header EUR = h+0 = START - 2
    h = None
    eur_col = None
    ctrl2_pos = get_named_range_pos(doc.document, 'START_CTRL2')
    if ctrl2_pos:
        header_row = ctrl2_pos[2] - 2
        val = ws.getCellByPosition(ctrl2_pos[1], header_row).getString().strip()
        if val == 'EUR':
            h = header_row
            eur_col = ctrl2_pos[1]

    if h is None:
        # Fallback : scan pour "EUR" dans les colonnes > 14
        for r in range(0, 80):
            for c in range(14, 35):
                val = ws.getCellByPosition(c, r).getString().strip()
                if val == 'EUR':
                    h = r
                    eur_col = c
                    break
            if h is not None:
                break

    if h is None:
        print("  (header CTRL2 introuvable — skip)")
        return 0

    # Scanner les devises
    devises = []
    for c in range(eur_col, eur_col + 20):
        val = ws.getCellByPosition(c, h).getString().strip()
        if not val:
            break
        devises.append((c, val))

    formats = doc.document.getNumberFormats()
    fmt_cache = {}
    for devise, fmt_str in FORMATS_DEVISE.items():
        fmt_cache[devise] = doc.register_number_format(fmt_str)
    fmt_eur = doc.register_number_format(FORMAT_EUR)
    fmt_eur_red = doc.register_number_format(FORMAT_EUR_RED)
    fmt_int = doc.register_number_format('#\xa0##0')

    # Formats rouge négatif par devise (pour Virements h+7)
    fmt_red_cache = {'EUR': fmt_eur_red}
    for devise, fmt_str in FORMATS_DEVISE.items():
        if devise == 'EUR':
            continue
        # Pattern : positif;[RED]\-négatif
        red_fmt = f'{fmt_str};[RED]\\-{fmt_str}'
        fmt_red_cache[devise] = doc.register_number_format(red_fmt)

    # Propriétés de style à propager depuis la colonne EUR
    STYLE_PROPS = ('CharHeight', 'CharWeight', 'CharColor', 'CharFontName',
                   'HoriJustify', 'VertJustify',
                   'TopBorder', 'BottomBorder', 'LeftBorder', 'RightBorder')

    # Lignes en montant devise (avec gris non-EUR)
    DEVISE_ROWS = {3, 9}        # CATÉGORIES, Titres
    DEVISE_ROWS_RED = {7}       # Virements (rouge négatif)
    # Lignes en entier
    INTEGER_ROWS = {2, 5, 6}  # COMPTES, Appariements, Balances (h+4 Dates = vide)
    # Lignes en montant EUR
    EUR_ROWS = {1, 8, 10, 11, 12}  # Taux, € equiv ×2, Changes, Total
    # Lignes pied de tableau — style seul, pas de format nombre
    # Calculer depuis END_CTRL2 (2 lignes après la dernière ligne de données)
    end_ctrl2 = get_named_range_pos(doc.document, 'END_CTRL2')
    if end_ctrl2:
        end_offset = end_ctrl2[2] - h  # 0-indexed
        FOOTER_ROWS = {end_offset - 1, end_offset}
    else:
        FOOTER_ROWS = {13, 14}
    # Toutes les lignes à styler (y compris header h+0 et pied)
    ALL_DATA_ROWS = sorted({0} | DEVISE_ROWS | DEVISE_ROWS_RED | INTEGER_ROWS | EUR_ROWS | FOOTER_ROWS)

    fixes = 0
    for col_0, devise in devises:
        is_non_eur = devise != 'EUR'
        expected_fmt = fmt_cache.get(devise, fmt_eur)
        col_fixes = 0

        # 1) Propager le style de base depuis la colonne EUR
        if is_non_eur:
            for row_offset in ALL_DATA_ROWS:
                eur_cell = ws.getCellByPosition(eur_col, h + row_offset)
                cell = ws.getCellByPosition(col_0, h + row_offset)
                for prop in STYLE_PROPS:
                    eur_val = getattr(eur_cell, prop, None)
                    cur_val = getattr(cell, prop, None)
                    if eur_val is not None and str(eur_val) != str(cur_val):
                        col_fixes += 1
                        if apply:
                            setattr(cell, prop, eur_val)
                # Propager CellBackColor sauf si gris sera appliqué après
                if row_offset not in DEVISE_ROWS and row_offset not in DEVISE_ROWS_RED:
                    if eur_cell.CellBackColor != cell.CellBackColor:
                        col_fixes += 1
                        if apply:
                            cell.CellBackColor = eur_cell.CellBackColor

        # 2) Number formats spécifiques par type de ligne
        for row_offset in DEVISE_ROWS:
            cell = ws.getCellByPosition(col_0, h + row_offset)
            if not _fmt_eq(formats, cell.NumberFormat, expected_fmt):
                col_fixes += 1
                if apply:
                    cell.NumberFormat = expected_fmt
            if is_non_eur and cell.CellBackColor != GRIS:
                col_fixes += 1
                if apply:
                    cell.CellBackColor = GRIS

        for row_offset in DEVISE_ROWS_RED:
            cell = ws.getCellByPosition(col_0, h + row_offset)
            expected_red = fmt_red_cache.get(devise, fmt_eur_red)
            if not _fmt_eq(formats, cell.NumberFormat, expected_red):
                col_fixes += 1
                if apply:
                    cell.NumberFormat = expected_red
            if is_non_eur and cell.CellBackColor != GRIS:
                col_fixes += 1
                if apply:
                    cell.CellBackColor = GRIS

        for row_offset in INTEGER_ROWS:
            cell = ws.getCellByPosition(col_0, h + row_offset)
            if not _fmt_eq(formats, cell.NumberFormat, fmt_int):
                col_fixes += 1
                if apply:
                    cell.NumberFormat = fmt_int

        for row_offset in EUR_ROWS:
            cell = ws.getCellByPosition(col_0, h + row_offset)
            if not _fmt_eq(formats, cell.NumberFormat, fmt_eur):
                col_fixes += 1
                if apply:
                    cell.NumberFormat = fmt_eur

        if col_fixes:
            fixes += col_fixes
            print(f"  col {devise:<5} → {col_fixes} cellules")

    return fixes


def fix_operations(doc, apply):
    """Corrige les formats de la feuille Opérations.

    Pour chaque ligne :
    - Montant C : format devise
    - Equiv E : format EUR
    - Fond gris C et D pour non-EUR
    """
    from inc_excel_schema import OpCol, SHEET_OPERATIONS

    ws = doc.get_sheet(SHEET_OPERATIONS)

    formats = doc.document.getNumberFormats()
    fmt_cache = {}
    for devise, fmt_str in FORMATS_DEVISE.items():
        fmt_cache[devise] = doc.register_number_format(fmt_str)
    fmt_eur = doc.register_number_format(FORMAT_EUR)

    # Bornes depuis OPdevise named range (ex: $Opérations.$D$4:$D$6004)
    import re
    nr = doc.document.NamedRanges
    op_start, op_end = 4, 7000  # fallback
    if nr.hasByName('OPdevise'):
        content = nr.getByName('OPdevise').Content
        m = re.findall(r'\$(\d+)', content)
        if len(m) >= 1:
            op_start = int(m[0])
        if len(m) >= 2:
            op_end = int(m[1])

    fixes = 0
    for r in range(op_start, op_end + 1):
        r0 = r - 1
        devise = ws.getCellByPosition(uno_col(OpCol.DEVISE), r0).getString().strip()
        if not devise:
            continue

        is_non_eur = devise != 'EUR'
        expected_fmt = fmt_cache.get(devise, fmt_eur)

        # Montant C : format devise
        c_cell = ws.getCellByPosition(uno_col(OpCol.MONTANT), r0)
        if not _fmt_eq(formats, c_cell.NumberFormat, expected_fmt):
            fixes += 1
            if apply:
                c_cell.NumberFormat = expected_fmt

        # Equiv E : format EUR
        e_cell = ws.getCellByPosition(uno_col(OpCol.EQUIV), r0)
        if not _fmt_eq(formats, e_cell.NumberFormat, fmt_eur):
            fixes += 1
            if apply:
                e_cell.NumberFormat = fmt_eur

        # Fond gris C et D pour non-EUR
        if is_non_eur:
            for col in (OpCol.MONTANT, OpCol.DEVISE):
                cell = ws.getCellByPosition(uno_col(col), r0)
                if cell.CellBackColor != GRIS:
                    fixes += 1
                    if apply:
                        cell.CellBackColor = GRIS

    return fixes


def fix_generic_sheet(doc, sheet_name, apply):
    """Corrige les formats monétaires et dates sur une feuille quelconque.

    Scanne toutes les cellules avec un format numérique et remplace
    les formats US par les équivalents français.
    """
    try:
        ws = doc.get_sheet(sheet_name)
    except Exception:
        return 0

    formats = doc.document.getNumberFormats()
    fixes = 0

    # Scanner la zone utilisée
    cursor = ws.createCursor()
    cursor.gotoStartOfUsedArea(False)
    cursor.gotoEndOfUsedArea(True)
    addr = cursor.getRangeAddress()

    for row in range(addr.StartRow, addr.EndRow + 1):
        for col in range(addr.StartColumn, addr.EndColumn + 1):
            cell = ws.getCellByPosition(col, row)
            fmt_id = cell.NumberFormat
            if fmt_id == 0:  # General
                continue

            fmt_str = formats.getByKey(fmt_id).FormatString
            new_fmt = _fix_format_string(fmt_str)

            if new_fmt and new_fmt != fmt_str:
                coord = f"{chr(65 + col) if col < 26 else chr(64 + col // 26) + chr(65 + col % 26)}{row + 1}"
                fixes += 1
                if apply:
                    cell.NumberFormat = doc.register_number_format(new_fmt)

    return fixes


def _fix_format_string(fmt_str):
    """Transforme un format US en format français.

    Retourne le nouveau format, ou None si pas de changement nécessaire.
    """
    original = fmt_str

    # Point décimal + virgule milliers → virgule décimale + espace milliers
    # Détecter si c'est un format US (point décimal)
    # Les formats US ont #,##0.00 — les formats FR ont #.##0,00 ou # ##0,00
    if '#,##0.' in fmt_str or '#,##0;' in fmt_str or fmt_str.endswith('#,##0'):
        # C'est un format US : , = milliers, . = décimal
        # Convertir en français : espace insécable = milliers, , = décimal
        # Étape 1: protéger les séquences [$...] (symboles devise)
        import re
        parts = re.split(r'(\[\$[^\]]*\])', fmt_str)
        converted = []
        for part in parts:
            if part.startswith('[$'):
                converted.append(part)
            else:
                # , → placeholder, . → , (décimal), placeholder → espace insécable
                part = part.replace(',', '\x01').replace('.', ',').replace('\x01', '\xa0')
                converted.append(part)
        fmt_str = ''.join(converted)

    # Symbole devise AVANT le montant → APRÈS
    # [$€-40C] #,##0 → # ##0 [$€-40C]
    import re
    m = re.match(r'^(\[\$[^\]]+\])\s*(.+)$', fmt_str)
    if m:
        symbol, rest = m.group(1), m.group(2)
        # Vérifier que le reste ne contient pas déjà le symbole
        if symbol not in rest:
            fmt_str = f'{rest} {symbol}'

    # Traiter les formats avec ; (positif;négatif)
    if ';' in fmt_str and not fmt_str.startswith(';'):
        parts = fmt_str.split(';')
        fixed_parts = []
        for part in parts:
            m = re.match(r'^(\\?-?)(\[\$[^\]]+\])\s*(.+)$', part.strip())
            if m:
                prefix, symbol, rest = m.group(1), m.group(2), m.group(3)
                if symbol not in rest:
                    part = f'{prefix}{rest} {symbol}'
            fixed_parts.append(part)
        fmt_str = ';'.join(fixed_parts)

    if fmt_str != original:
        return fmt_str
    return None


def check_format_coherence(doc):
    """Vérifie la cohérence entre le format nombre et la devise indiquée.

    Détecte les cellules dont le format ne correspond pas à la devise
    de la même ligne (ex: format USD sur une ligne CHF).
    Retourne le nombre d'incohérences trouvées.
    """
    from inc_excel_schema import (
        AvCol, AV_FIRST_ROW, SHEET_AVOIRS,
        OpCol, SHEET_OPERATIONS,
        PvCol, SHEET_PLUS_VALUE,
        uno_col, uno_row,
    )
    import re

    formats = doc.document.getNumberFormats()
    issues = 0

    def _extract_devise_from_fmt(fmt_id):
        """Extrait le code devise d'un format nombre (ex: '[$USD]' → 'USD')."""
        fmt_str = formats.getByKey(fmt_id).FormatString
        # [$€-40C] → EUR, [$USD] → USD, [$CHF-40C] → CHF
        m = re.search(r'\[\$([^\]]+)\]', fmt_str)
        if m:
            code = m.group(1)
            # Retirer le suffixe locale (-40C, -409, etc.)
            code = re.sub(r'-[0-9A-Fa-f]+$', '', code)
            if code in ('€', '$'):
                return 'EUR' if code == '€' else 'USD'
            return code
        return None  # pas de symbole devise (entier, décimal pur)

    # === Avoirs : K (montant) vs E (devise) ===
    ws_av = doc.get_sheet(SHEET_AVOIRS)
    end_avr = get_named_range_pos(doc.document, 'END_AVR')
    end_row = (end_avr[2] + 1) if end_avr else AV_FIRST_ROW + 200
    for r in range(AV_FIRST_ROW + 1, end_row + 1):
        r0 = uno_row(r)
        intitule = ws_av.getCellByPosition(uno_col(AvCol.INTITULE), r0).getString().strip()
        if not intitule:
            continue
        devise = ws_av.getCellByPosition(uno_col(AvCol.DEVISE), r0).getString().strip()
        if not devise:
            continue
        k_fmt_devise = _extract_devise_from_fmt(
            ws_av.getCellByPosition(uno_col(AvCol.MONTANT_SOLDE), r0).NumberFormat)
        if k_fmt_devise and k_fmt_devise != devise:
            print(f"  ✗ Avoirs {intitule}: K formaté {k_fmt_devise}, devise={devise}")
            issues += 1

    # === Opérations : C (montant) vs D (devise) ===
    ws_op = doc.get_sheet(SHEET_OPERATIONS)
    nr = doc.document.NamedRanges
    op_start, op_end = 4, 7000
    if nr.hasByName('OPdevise'):
        content = nr.getByName('OPdevise').Content
        m = re.findall(r'\$(\d+)', content)
        if len(m) >= 1:
            op_start = int(m[0])
        if len(m) >= 2:
            op_end = int(m[1])

    op_issues = 0
    for r in range(op_start, op_end + 1):
        r0 = r - 1
        devise = ws_op.getCellByPosition(uno_col(OpCol.DEVISE), r0).getString().strip()
        if not devise:
            continue
        c_fmt_devise = _extract_devise_from_fmt(
            ws_op.getCellByPosition(uno_col(OpCol.MONTANT), r0).NumberFormat)
        if c_fmt_devise and c_fmt_devise != devise:
            op_issues += 1
    if op_issues:
        print(f"  ✗ Opérations: {op_issues} ligne(s) avec format montant ≠ devise")
        issues += op_issues

    # === PVL : H/I vs devise (section-aware) ===
    ws_pv = doc.get_sheet(SHEET_PLUS_VALUE)
    start_pvl = get_named_range_pos(doc.document, 'START_PVL')
    end_pvl = get_named_range_pos(doc.document, 'END_PVL')
    if start_pvl:
        data_start = start_pvl[2] + 2
        end_hint = (end_pvl[2] + 1) if end_pvl else data_start + 200
        if end_hint < data_start + 10:
            end_hint = data_start + 200

        for r in range(data_start, end_hint + 1):
            r0 = r - 1
            devise = ws_pv.getCellByPosition(uno_col(PvCol.DEVISE), r0).getString().strip()
            if not devise:
                continue
            section = ws_pv.getCellByPosition(uno_col(PvCol.SECTION), r0).getString().strip()
            ligne = ws_pv.getCellByPosition(uno_col(PvCol.LIGNE), r0).getString().strip()

            # H/I : devise native pour portefeuilles, EUR pour les autres sections
            expected_hi = devise if section == 'portefeuilles' else 'EUR'
            for col, col_name in ((PvCol.MONTANT_INIT, 'H'), (PvCol.SIGMA, 'I')):
                fmt_devise = _extract_devise_from_fmt(
                    ws_pv.getCellByPosition(uno_col(col), r0).NumberFormat)
                if fmt_devise and fmt_devise != expected_hi:
                    print(f"  ✗ PVL {ligne or '?'} ({devise}): {col_name} formaté {fmt_devise}, attendu {expected_hi}")
                    issues += 1

            # E (PVL) et K (SOLDE) : toujours en devise de la ligne
            for col, col_name in ((PvCol.PVL, 'E'), (PvCol.SOLDE, 'K')):
                fmt_devise = _extract_devise_from_fmt(
                    ws_pv.getCellByPosition(uno_col(col), r0).NumberFormat)
                if fmt_devise and fmt_devise != devise:
                    print(f"  ✗ PVL {ligne or '?'} ({devise}): {col_name} formaté {fmt_devise}, attendu {devise}")
                    issues += 1

    return issues


def fix_formats(xlsm_path, apply=False, sheets=None):
    """Scanne et corrige les formats des feuilles.

    Args:
        sheets: liste de noms de feuilles à traiter (None = toutes).
                Noms courts acceptés : avoirs, budget, pvl, ctrl2, operations, controles, patrimoine, cotations.
    """
    from inc_uno import UnoDocument

    xlsm_path = Path(xlsm_path).resolve()
    if not xlsm_path.exists():
        print(f"❌ Fichier introuvable : {xlsm_path}")
        return False

    if apply:
        bak = xlsm_path.with_suffix('.xlsm.bak')
        shutil.copy2(xlsm_path, bak)
        print(f"Backup : {bak.name}")

    total_fixes = 0

    with UnoDocument(xlsm_path) as doc:
        # === Validation structurelle ===
        ok, errors, warnings = validate_structure(doc.document)
        if warnings:
            for w in warnings:
                print(f"  ⚠ {w}")
        if not ok:
            for e in errors:
                print(f"  ❌ {e}")
            print("\nAbandon : structure invalide")
            return False
        print("✓ Structure validée")

        # === Cohérence format ↔ devise ===
        print("\n🔍 Cohérence format/devise")
        n_coherence = check_format_coherence(doc)
        if not n_coherence:
            print("  ✓ OK")

        # Mapping noms courts → liste de (label, fonction)
        # Une feuille peut avoir plusieurs passes (ex: controles = CTRL2 + generic)
        SHEET_FIXES = {
            'avoirs':     [('📋 Avoirs',              lambda: fix_avoirs(doc, apply))],
            'budget':     [('📋 Budget (catégories)',  lambda: fix_budget(doc, apply)),
                           ('📋 Budget (global)',      lambda: fix_generic_sheet(doc, 'Budget', apply))],
            'pvl':        [('📋 Plus_value',           lambda: fix_plus_value(doc, apply))],
            'controles':  [('📋 Contrôles (CTRL2)',    lambda: fix_ctrl2(doc, apply)),
                           ('📋 Contrôles (global)',   lambda: fix_generic_sheet(doc, 'Contrôles', apply))],
            'operations': [('📋 Opérations',           lambda: fix_operations(doc, apply))],
            'patrimoine': [('📋 Patrimoine',           lambda: fix_generic_sheet(doc, 'Patrimoine', apply))],
            'cotations':  [('📋 Cotations',            lambda: fix_generic_sheet(doc, 'Cotations', apply))],
        }

        # Normaliser les noms de feuilles demandés
        if sheets:
            selected = {s.lower().replace('plus_value', 'pvl').replace('opérations', 'operations')
                        for s in sheets}
        else:
            selected = None  # toutes

        for key, passes in SHEET_FIXES.items():
            if selected and key not in selected:
                continue
            for label, fix_fn in passes:
                print(f"\n{label}")
                n = fix_fn()
                total_fixes += n
                if not n:
                    print("  ✓ OK")
                elif n and 'global' in label.lower():
                    print(f"  {n} cellule(s)")

        if apply and total_fixes:
            doc.calculate_all()
            doc.save()

    action = 'corrigés' if apply else 'à corriger'
    print(f"\nTotal : {total_fixes} correction(s) {action}")
    return True


def main():
    parser = argparse.ArgumentParser(
        description='Corrige les formats de cellules dans comptes.xlsm')
    parser.add_argument('xlsm', help='Fichier xlsm à corriger')
    parser.add_argument('--apply', action='store_true',
                        help='Appliquer les corrections (défaut: dry run)')
    parser.add_argument('--sheet', '-s', nargs='+', metavar='FEUILLE',
                        help='Feuille(s) à traiter (avoirs, budget, pvl, controles, operations, '
                             'patrimoine, cotations). Défaut: toutes.')
    args = parser.parse_args()

    fix_formats(args.xlsm, apply=args.apply, sheets=args.sheet)


if __name__ == '__main__':
    main()
