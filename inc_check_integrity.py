"""
inc_check_integrity.py — Vérification d'intégrité du classeur comptes.xlsm

Fonctions et classes partagées : validate_structure(), IntegrityChecker.
Utilisé par tool_check_integrity (CLI), tool_fix_formats, tool_gui_cli.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
# inc_uno imports done locally where needed


def col_letter(col_0indexed):
    """0-indexed column number to Excel letter(s)."""
    if col_0indexed < 26:
        return chr(65 + col_0indexed)
    return chr(64 + col_0indexed // 26) + chr(65 + col_0indexed % 26)


def _parse_nr_bounds(content):
    """Retourne (sheet, col_letter_start, r1, col_letter_end, r2) ou None."""
    import re
    m = re.match(r'\$?([^.!]+)[.!]\$([A-Z]+)\$(\d+):\$([A-Z]+)\$(\d+)', content)
    if not m:
        return None
    return (m.group(1), m.group(2), int(m.group(3)), m.group(4), int(m.group(5)))


def _col_letter_to_idx(letter):
    """'A' → 0, 'Z' → 25, 'AA' → 26. 0-indexed."""
    result = 0
    for c in letter:
        result = result * 26 + (ord(c) - ord('A') + 1)
    return result - 1


def validate_anchors(xdoc):
    """Vérifie la règle NR ↔ sentinelles pour toutes les tables ancrées.

    Règle : pour chaque table de ANCHOR_TABLES, le ref_nr existe, sa col
    porte une sentinelle ⚓ (ou ✓ legacy) en r1 et r2, et tous les NRs de
    la famille (mêmes préfixe alpha) ont les mêmes bornes row.

    Retourne (ok, errors, warnings).

    Classifications par bout (top/bot) :
    - OK         : sentinelle ∈ {✓,⚓} à la row borne du NR
    - MISSING    : pas de sentinelle, row borne pointe sur autre chose (cas
                   pré-migration : PAT/CTRL2 sans sentinelles ou OP sans fin)
    - INCOHERENT : sentinelle existe mais pas à la row borne (déborde / décale)
    """
    from inc_excel_schema import ANCHOR_TABLES

    errors = []
    warnings = []
    nr = xdoc.NamedRanges

    for sheet_name, ref_nr, target_end, only_start in ANCHOR_TABLES:
        # --- Existence ref_nr ---
        if not nr.hasByName(ref_nr):
            errors.append(f"[{sheet_name}] ref_nr '{ref_nr}' manquant")
            continue
        parsed = _parse_nr_bounds(nr.getByName(ref_nr).Content)
        if not parsed:
            errors.append(f"[{sheet_name}] ref_nr '{ref_nr}' : parse KO "
                          f"({nr.getByName(ref_nr).Content})")
            continue
        _, c1, r1, c2, r2 = parsed
        if c1 != c2:
            errors.append(f"[{sheet_name}] ref_nr '{ref_nr}' multi-col "
                          f"({c1}..{c2}) — attendu 1 col")
            continue
        ref_col = _col_letter_to_idx(c1)
        ws = xdoc.Sheets.getByName(sheet_name)

        # --- Sentinelles (top, bot) ---
        # Classification — tout ce qui est réparable par ensure_anchors devient
        # WARNING (pas ERROR). Seuls les cas vraiment pathologiques (NR parse
        # KO, multi-col, …) sont errors bloquantes.
        #
        #  OK       = sentinelle à la row borne du NR
        #  OFFSET   = sentinelle à ±1 ou ±2 rows → ensure_anchors ajustera le NR
        #  MISSING  = pas de sentinelle dans voisinage → ensure_anchors en posera
        SENT = ('✓', '⚓')

        def cell_val(row_1):
            return ws.getCellByPosition(ref_col, row_1 - 1).getString().strip()

        def classify(row_1):
            """Retourne ('OK'|'OFFSET'|'MISSING', suggested_row).
            suggested_row = row où ensure_anchors placera la sentinelle.
            """
            if cell_val(row_1) in SENT:
                return 'OK', row_1
            for delta in (-1, 1, -2, 2):  # priorité aux rows les plus proches
                candidate = row_1 + delta
                if candidate > 0 and cell_val(candidate) in SENT:
                    return 'OFFSET', candidate
            return 'MISSING', row_1

        top_status, top_suggest = classify(r1)

        if only_start:
            # Pas d'ancre bot attendue (OP). Skip classification bot.
            bot_status, bot_suggest = 'OK', r2
        elif target_end is not None and r2 != target_end:
            bot_status, bot_suggest = 'MISSING', target_end
        else:
            bot_status, bot_suggest = classify(r2)

        if top_status == 'OFFSET':
            warnings.append(
                f"[{sheet_name}] {ref_nr} top : sentinelle à {c1}{top_suggest} "
                f"au lieu de {c1}{r1} (NR à ajuster)")
        elif top_status == 'MISSING':
            warnings.append(f"[{sheet_name}] {ref_nr} top {c1}{r1} : sentinelle absente")

        if bot_status == 'OFFSET':
            warnings.append(
                f"[{sheet_name}] {ref_nr} bot : sentinelle à {c1}{bot_suggest} "
                f"au lieu de {c1}{r2} (NR à ajuster)")
        elif bot_status == 'MISSING':
            if target_end is not None and r2 != target_end:
                warnings.append(
                    f"[{sheet_name}] {ref_nr} bot : NR finit {c1}{r2}, "
                    f"cible attendue row {target_end}")
            else:
                warnings.append(f"[{sheet_name}] {ref_nr} bot {c1}{r2} : sentinelle absente")

        # --- Homogénéité famille : warning (ensure_anchors alignera) ---
        # Préfixe = lettres + digits initiaux (pour distinguer CTRL1 de CTRL2).
        import re
        prefix_match = re.match(r'^([A-Z]+\d*)', ref_nr)
        if not prefix_match:
            continue
        prefix = prefix_match.group(1)
        for name in nr.ElementNames:
            if not name.startswith(prefix) or name == ref_nr:
                continue
            p = _parse_nr_bounds(nr.getByName(name).Content)
            if not p:
                continue
            _, _, fr1, _, fr2 = p
            if fr1 != r1 or fr2 != r2:
                warnings.append(
                    f"[{sheet_name}] famille {prefix}* : {name} rows {fr1}:{fr2} "
                    f"≠ {ref_nr} rows {r1}:{r2} (à réaligner)")

    return (len(errors) == 0, errors, warnings)


def validate_structure(xdoc, cr=None):
    """Vérifie la structure du classeur avant toute opération.

    Contrôle les feuilles, named ranges, headers et marqueurs attendus.
    Retourne (ok, errors, warnings).
    Utilisable par tool_fix_formats, tool_check_integrity, etc.
    """
    from inc_excel_schema import (
        SHEET_AVOIRS, SHEET_BUDGET, SHEET_PLUS_VALUE,
        SHEET_CONTROLES, SHEET_OPERATIONS,
        ColResolver, uno_row,
    )
    if cr is None:
        cr = ColResolver.from_uno(xdoc)

    errors = []
    warnings = []

    # --- Feuilles requises ---
    sheets = xdoc.Sheets
    for name in (SHEET_AVOIRS, SHEET_BUDGET, SHEET_PLUS_VALUE,
                 SHEET_CONTROLES, SHEET_OPERATIONS):
        if not sheets.hasByName(name):
            errors.append(f"Feuille manquante : {name}")

    if errors:
        return False, errors, warnings

    # --- Named ranges colonnes requis ---
    REQUIRED_COL_RANGES = {
        'AVRintitulé': SHEET_AVOIRS,
        'CATnom': SHEET_BUDGET,
        'PVLcompte': SHEET_PLUS_VALUE,
    }
    nr = xdoc.NamedRanges
    from inc_uno import get_col_range_bounds
    for name, expected_sheet in REQUIRED_COL_RANGES.items():
        if not nr.hasByName(name):
            errors.append(f"Named range manquant : {name}")
        else:
            bounds = get_col_range_bounds(xdoc, name)
            if bounds and bounds[0] != expected_sheet:
                errors.append(f"{name} pointe sur '{bounds[0]}' au lieu de '{expected_sheet}'")

    # --- Named ranges optionnels (warning si absents) ---
    for name in ('CTRL2type', 'OPdevise'):
        if not nr.hasByName(name):
            warnings.append(f"Named range optionnel absent : {name}")

    # --- Résidus START_*/END_* (migration legacy partiellement aboutie) ---
    legacy = [n for n in nr.ElementNames
              if n.startswith('START_') or n.startswith('END_')]
    if legacy:
        errors.append(
            f"Named ranges legacy START_*/END_* présents ({len(legacy)}) — "
            f"migration v3.x incomplète : {', '.join(legacy[:5])}"
            + (' ...' if len(legacy) > 5 else ''))

    # --- Cohérence START < END (via named ranges colonnes) ---
    for ref_name in ('AVRintitulé', 'PVLcompte'):
        s, e = cr.rows(ref_name)
        if s and e and s >= e:
            errors.append(f"{ref_name} START (row {s}) >= END (row {e})")

    # --- #REF! dans les named ranges structurels ---
    STRUCTURAL_PREFIXES = ('OP', 'PVL', 'AVR', 'CTRL1', 'CTRL2', 'COT', 'CAT', 'PAT', 'POSTES')
    STRUCTURAL_NAMES = ('Solde', 'Retenu', 'Spéciale')
    for name in nr.ElementNames:
        content = nr.getByName(name).Content
        if '#REF!' in content:
            if any(name.startswith(p) for p in STRUCTURAL_PREFIXES) or name in STRUCTURAL_NAMES:
                errors.append(f"Named range structurel #REF! : {name} → {content}")

    # --- Cohérence ranges colonnes + sentinelles : délégué à validate_anchors ---
    anchors_ok, anchors_errs, anchors_warns = validate_anchors(xdoc)
    errors.extend(anchors_errs)
    warnings.extend(anchors_warns)

    # --- Marqueurs de headers ---
    # Opérations : header row 3 doit contenir "Date", "Montant", "Devise"
    ws_op = sheets.getByName(SHEET_OPERATIONS)
    for nr_name, label in (('OPdate', 'Date'), ('OPmontant', 'Montant'), ('OPdevise', 'Devise')):
        val = ws_op.getCellByPosition(cr.col(nr_name), uno_row(3)).getString().strip()
        if val and label.lower() not in val.lower():
            warnings.append(f"Opérations header col {cr.letter(nr_name)}: attendu '{label}', trouvé '{val}'")

    # Plus_value : vérifier header
    ws_pv = sheets.getByName(SHEET_PLUS_VALUE)
    pvl_s, _ = cr.rows('PVLcompte')
    if pvl_s:
        pv_header_row = uno_row(pvl_s) - 1  # header = 1 ligne au-dessus de START
        for nr_name, label in (('PVLsection', 'Section'), ('PVLdevise', 'Devise')):
            val = ws_pv.getCellByPosition(cr.col(nr_name), pv_header_row).getString().strip()
            if val and label.lower() not in val.lower():
                warnings.append(f"Plus_value header col {cr.letter(nr_name)}: attendu '{label}', trouvé '{val}'")

    # CTRL2 : vérifier que le header EUR (drill cell) est sur la row des labels
    # "Type de contrôle". Détection layout-aware (row peut être r1-2 pour les
    # classeurs v3.6 avec row vide intermédiaire, ou r1-1 pour les classeurs
    # v1 fraîchement migrés où ⚓ est directement sous les labels).
    ws_ctrl = sheets.getByName(SHEET_CONTROLES)
    ctrl2_s, _ = cr.rows('CTRL2drill')
    if ctrl2_s:
        type_col = cr.col('CTRL2type')
        drill_col = cr.col('CTRL2drill')
        header_row_1 = None
        for r in range(max(1, ctrl2_s - 5), ctrl2_s):
            if ws_ctrl.getCellByPosition(type_col, uno_row(r)).getString().strip() \
                    == 'Type de contrôle':
                header_row_1 = r
                break
        if header_row_1 is None:
            header_row_1 = ctrl2_s - 2  # fallback
        val = ws_ctrl.getCellByPosition(drill_col, uno_row(header_row_1)).getString().strip()
        # Le format `@" ▼"` posé sur la drill cell suffixe l'affichage : getString
        # renvoie 'EUR ▼' alors que la valeur brute est 'EUR'. On strip avant compare.
        if val.endswith('▼'):
            val = val[:-1].rstrip()
        if val != 'EUR':
            warnings.append(
                f"CTRL2 header col {cr.letter('CTRL2drill')} (row {header_row_1}): "
                f"attendu 'EUR', trouvé '{val}'")

    return len(errors) == 0, errors, warnings


class IntegrityChecker:
    """Vérifie l'intégrité des formules d'un classeur comptes.xlsm."""

    def __init__(self, xdoc, cr=None):
        self.xdoc = xdoc
        from inc_excel_schema import ColResolver
        self.cr = cr if cr is not None else ColResolver.from_uno(xdoc)
        self.errors = []
        self.warnings = []
        self.checked = 0

    def get_bounds(self, ref_range):
        """Return (sheet_name, start_col, start_row, end_col, end_row) or None.

        Résout via named range colonne. Les indices sont 0-indexed.
        """
        from inc_uno import get_col_range_bounds
        bounds = get_col_range_bounds(self.xdoc, ref_range)
        if bounds:
            sheet, col_0, start_1, end_1 = bounds
            return sheet, col_0, start_1 - 1, col_0, end_1 - 1  # 0-indexed
        self.warnings.append(f"Bornes introuvables pour {ref_range}")
        return None

    def _has_formula(self, cell):
        """True if cell contains a real formula (starts with '=')."""
        f = cell.getFormula()
        return f.startswith('=')

    def _check_formula_col(self, sheet, col, row_start, row_end, label,
                           pattern=None, allow_empty=False):
        """Check that cells in a column have formulas, not static values."""
        for row in range(row_start, row_end + 1):
            cell = sheet.getCellByPosition(col, row)
            has_formula = self._has_formula(cell)
            value = cell.getValue()
            string = cell.getString()
            self.checked += 1

            if has_formula:
                # Has formula — check pattern if specified
                if pattern:
                    f = cell.getFormula()
                    if pattern not in f.upper():
                        self.warnings.append(
                            f"  {label} {col_letter(col)}{row+1}: "
                            f"formule inattendue: {f[:60]}")
                continue

            # No formula
            if allow_empty and not string and value == 0:
                continue  # Legitimately empty

            if string or value != 0:
                # Has a static value where a formula was expected
                display = string if string else str(value)
                self.errors.append(
                    f"  {label} {col_letter(col)}{row+1}: "
                    f"valeur statique '{display[:30]}' (formule manquante)")

    def check_avoirs(self):
        """Check Avoirs formulas: J, K columns (MAXIFS/SUMIFS), L (totals)."""
        bounds = self.get_bounds("AVRintitulé")
        if not bounds:
            return
        sheet_name, _, row_start, _, row_end = bounds
        sheet = self.xdoc.Sheets.getByName(sheet_name)
        label = "Avoirs"

        # Only check rows that have a devise (col E=4) — rows without devise
        # are mobilier/immobilier/special with manual values
        formula_rows = []
        for row in range(row_start, row_end + 1):
            devise = sheet.getCellByPosition(self.cr.col('AVRdevise'), row).getString()
            if devise:
                formula_rows.append(row)

        # Columns to check (0-indexed):
        # J=9 (date solde, MAXIFS/SUMIF), K=10 (montant, SUMIFS)
        # L=11 (montant EUR, formule SUM ou calcul)
        for col in [9, 10, 11]:
            for row in formula_rows:
                cell = sheet.getCellByPosition(col, row)
                self.checked += 1
                if self._has_formula(cell):
                    continue
                value = cell.getValue()
                string = cell.getString()
                if not string and value == 0:
                    continue  # Legitimately empty
                # Text-only cells (type=2) are intentional labels (e.g. "En cours")
                if cell.Type.value == 'TEXT':
                    continue
                if string or value != 0:
                    display = string if string else str(value)
                    self.errors.append(
                        f"  {label} {col_letter(col)}{row+1}: "
                        f"valeur statique '{display[:30]}' (formule manquante)")

        # Check Total row (row after end AVR)
        total_row = row_end + 1
        total_a = sheet.getCellByPosition(self.cr.col('AVRintitulé'), total_row).getString()
        if 'Total' in total_a:
            for col in [9, 10, 11]:
                cell = sheet.getCellByPosition(col, total_row)
                self.checked += 1
                if not self._has_formula(cell):
                    v = cell.getString()
                    if v:
                        self.errors.append(
                            f"  {label} {col_letter(col)}{total_row+1} (Total): "
                            f"valeur statique '{v[:30]}'")

    def check_controles_comptes(self):
        """Check Contrôles comptes section: D, E, F, L columns."""
        bounds = self.get_bounds("CTRL1compte")
        if not bounds:
            return
        sheet_name, _, row_start, _, row_end = bounds
        sheet = self.xdoc.Sheets.getByName(sheet_name)
        label = "Contrôles"

        # Refonte 0..N #Solde : C=2 date ancrage, D=3 date relevé,
        # E=4 montant ancrage, F=5 solde calc, G=6 montant relevé, H=7 écart
        for col in [2, 3, 4, 5, 6, 7]:
            self._check_formula_col(sheet, col, row_start, row_end, label,
                                    allow_empty=True)

    def check_controles_synthese(self):
        """Check Contrôles synthèse section: N, O columns."""
        bounds = self.get_bounds("CTRL2type")
        if not bounds:
            return
        sheet_name, _, row_start, _, row_end = bounds
        sheet = self.xdoc.Sheets.getByName(sheet_name)
        label = "Ctrl.Synthèse"

        # N=13: should have IF formulas for check rows
        # O=14: should have check formulas (some legitimately empty)
        for row in range(row_start, row_end + 1):
            n_cell = sheet.getCellByPosition(13, row)
            n_v = n_cell.getString()
            self.checked += 1

            if self._has_formula(n_cell):
                continue  # Has formula, OK
            if not n_v:
                continue  # Empty, OK (sub-detail rows)
            # Static value in N without formula = likely corruption
            if n_v and n_v not in ('', 'Affichage'):
                self.warnings.append(
                    f"  {label} N{row+1}: valeur statique '{n_v}' "
                    f"(formule IF attendue)")

    def check_plus_value(self):
        """Check Plus_value formulas — structure with Section column."""
        bounds = self.get_bounds("PVLcompte")
        if not bounds:
            return
        sheet_name, _, row_start, _, row_end = bounds
        sheet = self.xdoc.Sheets.getByName(sheet_name)
        label = "Plus_value"

        for row in range(row_start, row_end + 1):
            b_val = sheet.getCellByPosition(self.cr.col('PVLcompte'), row).getString().strip()
            if not b_val:
                continue  # Empty row

            c_val = sheet.getCellByPosition(self.cr.col('PVLtitre'), row).getString().strip()
            is_grand = 'GRAND' in b_val.upper()
            is_total = b_val.upper().startswith('TOTAL ')
            is_title = c_val.startswith('*') and c_val.endswith('*')
            is_section_header = c_val == 'Portefeuille'
            is_retenu = c_val in ('Retenu', '#Solde Opérations')
            is_compte_total = c_val == 'Total'
            is_simple = (not c_val and not is_total and not is_grand
                         and b_val not in ('Compte',))

            if is_section_header or b_val == 'Compte':
                continue

            cols_to_check = []

            if is_grand or is_total:
                cols_to_check = [4, 6, 7, 8, 9, 10]  # E,G,H,I,J,K
            elif is_retenu:
                cols_to_check = [4, 6, 7, 8, 9, 10]  # E,G,H,I,J,K
            elif is_compte_total:
                cols_to_check = [4]                    # E (PVL)
            elif is_title:
                cols_to_check = [4, 8]                 # E,I (PVL, SIGMA)
            elif is_simple:
                cols_to_check = [4, 6, 8, 9, 10]      # E,G,I,J,K

            display = b_val[:20]
            for col in cols_to_check:
                cell = sheet.getCellByPosition(col, row)
                self.checked += 1
                if self._has_formula(cell):
                    continue
                v = cell.getValue()
                if v == 0:
                    continue
                s = cell.getString()
                self.errors.append(
                    f"  {label} {col_letter(col)}{row+1} "
                    f"({display}): "
                    f"valeur statique '{s[:30] or str(v)}'")

    def check_budget_cours(self):
        """Check Budget devise exchange rate row.

        v1 : ligne cours multi-devise (SUMIF Cotations par colonne).
        v3.6 : cell cours sous la drill cell (INDEX/MATCH COTcours).
        """
        bounds = self.get_bounds("CATnom")
        if not bounds:
            return
        sheet_name, cat_col, cat_start, _, _ = bounds
        sheet = self.xdoc.Sheets.getByName(sheet_name)
        label = "Budget"

        cours_row = None
        for row in range(max(0, cat_start - 5), cat_start + 2):
            for col in range(cat_col + 1, cat_col + 15):
                f = sheet.getCellByPosition(col, row).getFormula()
                if not f:
                    continue
                u = f.upper()
                # v1 pattern (SUMIF Cotations) OU v3.6 pattern (INDEX COTcours)
                if (('SUMIF' in u and 'Cotations' in f) or
                        ('COTCOURS' in u and 'MATCH' in u)):
                    cours_row = row
                    break
            if cours_row is not None:
                break

        if cours_row is None:
            self.warnings.append(f"  {label}: ligne cours devises non trouvée")
            return

        first_col = True
        for col in range(cat_col + 1, cat_col + 15):
            cell = sheet.getCellByPosition(col, cours_row)
            v = cell.getValue()
            self.checked += 1
            if first_col:
                first_col = False
                continue  # EUR column = 1.0, no SUMIF needed
            if v == 0:
                continue  # Empty column
            if not self._has_formula(cell):
                self.errors.append(
                    f"  {label} {col_letter(col)}{cours_row+1}: "
                    f"cours statique '{v}' (SUMIF Cotations attendu)")

    def check_cotations(self):
        """Check Cotations: cours and date columns should have formulas or values."""
        bounds = self.get_bounds("COTcode")
        if not bounds:
            return
        sheet_name, _, row_start, _, row_end = bounds
        sheet = self.xdoc.Sheets.getByName(sheet_name)
        label = "Cotations"

        empty_rows = 0
        for row in range(row_start, row_end + 1):
            a = sheet.getCellByPosition(self.cr.col('COTlabel'), row).getString()
            self.checked += 1
            if not a:
                empty_rows += 1
        if empty_rows > 2:
            self.warnings.append(
                f"  {label}: {empty_rows} lignes vides sur "
                f"{row_end - row_start + 1}")

    def check_named_ranges(self):
        """Verify essential named ranges exist and point to valid cells."""
        expected = [
            "POSTESnom", "CATnom", "CATtotal_euro", "CATposte",
            "CTRL1compte", "CTRL2type", "CTRL2drill",
            "AVRintitulé", "AVRmontant_solde_euro",
            "PVLcompte", "PVLtitre",
            "COTcode", "COTcours",
            "OPdate", "OPcompte", "OPdevise",
            "PATlabel", "PATnombre", "PATvaleur", "PATpoids",
            "PAText1", "PAText2", "PAText3", "PAText4",
            "CONVnom", "CONVcell", "CONVlégende",
        ]
        nr = self.xdoc.NamedRanges
        missing = []
        corrupted = []
        for name in expected:
            if not nr.hasByName(name):
                missing.append(name)
            else:
                content = nr.getByName(name).Content
                if '#REF!' in content:
                    corrupted.append(f"{name} → {content}")
        if missing:
            self.errors.append(
                f"  Noms définis manquants: "
                f"{', '.join(missing)}")
        if corrupted:
            self.errors.append(
                f"  Noms définis corrompus: "
                f"{', '.join(corrupted)}")
        return len(missing) == 0 and len(corrupted) == 0

    def check_ref_errors(self):
        """Scan toutes les feuilles pour détecter les cellules en erreur.

        Codes d'erreur UNO (cell.getError()) les plus courants :
          519 = #VALUE!    520 = #N/A        522 = circular ref
          523 = #NAME?     524 = #REF!       525 = #DIV/0!
        """
        # Libellés courts des codes d'erreur LO/Calc
        ERR_LABELS = {
            519: '#VALUE!',
            520: '#N/A',
            522: 'Err 522 (circular)',
            523: '#NAME?',
            524: '#REF!',
            525: '#DIV/0!',
        }
        sheets = self.xdoc.Sheets
        ref_count = 0
        for i in range(sheets.getCount()):
            sheet = sheets.getByIndex(i)
            name = sheet.getName()
            cursor = sheet.createCursor()
            cursor.gotoStartOfUsedArea(False)
            cursor.gotoEndOfUsedArea(True)
            addr = cursor.getRangeAddress()
            for row in range(addr.StartRow, addr.EndRow + 1):
                for col in range(addr.StartColumn, addr.EndColumn + 1):
                    cell = sheet.getCellByPosition(col, row)
                    formula = cell.getFormula()
                    if not formula.startswith('='):
                        continue
                    self.checked += 1
                    err_code = cell.getError()
                    if '#REF!' in formula or err_code in ERR_LABELS:
                        label = '#REF!' if '#REF!' in formula else ERR_LABELS[err_code]
                        ref_count += 1
                        self.errors.append(
                            f"  {name} {col_letter(col)}{row+1}: "
                            f"{label} — {formula[:60]}")
        return ref_count

    def run_all(self):
        """Run all integrity checks."""
        print("Validation structure...")
        ok, struct_errors, struct_warnings = validate_structure(self.xdoc)
        self.warnings.extend(struct_warnings)
        if not ok:
            self.errors.extend(struct_errors)
            print("  ✗ Structure invalide — impossible de continuer")
            return

        print("Vérification #REF!...")
        ref_count = self.check_ref_errors()
        if ref_count:
            print(f"  {ref_count} cellule(s) #REF! trouvée(s)")

        print("Vérification des noms définis...")
        if not self.check_named_ranges():
            print("  ✗ Noms définis manquants — impossible de continuer")
            return

        print("Vérification Avoirs...")
        self.check_avoirs()

        print("Vérification Contrôles (comptes)...")
        self.check_controles_comptes()

        print("Vérification Contrôles (synthèse)...")
        self.check_controles_synthese()

        print("Vérification Plus_value...")
        self.check_plus_value()

        print("Vérification Budget (cours devises)...")
        self.check_budget_cours()

        print("Vérification Cotations...")
        self.check_cotations()

    def report(self):
        """Print summary report."""
        print(f"\n{'='*50}")
        print(f"  {self.checked} cellules vérifiées")
        print(f"{'='*50}")

        if self.errors:
            print(f"\n✗ {len(self.errors)} ERREUR(S) (formules corrompues) :")
            for e in self.errors:
                print(e)

        if self.warnings:
            print(f"\n⚠ {len(self.warnings)} avertissement(s) :")
            for w in self.warnings:
                print(w)

        if not self.errors and not self.warnings:
            print("\n✓ Aucune anomalie détectée")

        return len(self.errors) == 0
