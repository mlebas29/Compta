"""
inc_check_integrity.py — Vérification d'intégrité du classeur comptes.xlsm

Fonctions et classes partagées : validate_structure(), IntegrityChecker.
Utilisé par tool_check_integrity (CLI), tool_fix_formats, tool_gui_cli.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from inc_uno import get_named_range_pos


def col_letter(col_0indexed):
    """0-indexed column number to Excel letter(s)."""
    if col_0indexed < 26:
        return chr(65 + col_0indexed)
    return chr(64 + col_0indexed // 26) + chr(65 + col_0indexed % 26)


def validate_structure(xdoc):
    """Vérifie la structure du classeur avant toute opération.

    Contrôle les feuilles, named ranges, headers et marqueurs attendus.
    Retourne (ok, errors, warnings).
    Utilisable par tool_fix_formats, tool_check_integrity, etc.
    """
    from inc_excel_schema import (
        SHEET_AVOIRS, SHEET_BUDGET, SHEET_PLUS_VALUE,
        SHEET_CONTROLES, SHEET_OPERATIONS,
        AvCol, PvCol, OpCol, uno_col, uno_row,
    )

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

    # --- Named ranges requis ---
    REQUIRED_RANGES = {
        'START_AVR': SHEET_AVOIRS,
        'END_AVR': SHEET_AVOIRS,
        'START_CAT': SHEET_BUDGET,
        'START_PVL': SHEET_PLUS_VALUE,
        'END_PVL': SHEET_PLUS_VALUE,
    }
    for name, expected_sheet in REQUIRED_RANGES.items():
        pos = get_named_range_pos(xdoc, name)
        if not pos:
            errors.append(f"Named range manquant : {name}")
        elif pos[0] != expected_sheet:
            errors.append(f"{name} pointe sur '{pos[0]}' au lieu de '{expected_sheet}'")

    # --- Named ranges optionnels (warning si absents) ---
    nr = xdoc.NamedRanges
    for name in ('START_CTRL2', 'END_CTRL2', 'OPdevise'):
        if not nr.hasByName(name):
            warnings.append(f"Named range optionnel absent : {name}")

    # --- Cohérence START < END ---
    for prefix in ('AVR', 'PVL'):
        start = get_named_range_pos(xdoc, f'START_{prefix}')
        end = get_named_range_pos(xdoc, f'END_{prefix}')
        if start and end:
            if start[2] >= end[2]:
                errors.append(f"START_{prefix} (row {start[2]+1}) >= END_{prefix} (row {end[2]+1})")

    # --- #REF! dans les named ranges structurels (START_/END_/OP*/PVL*) ---
    STRUCTURAL_PREFIXES = ('START_', 'END_', 'OP', 'PVL', 'AVR')
    STRUCTURAL_NAMES = ('Solde', 'Retenu', 'Spéciale')
    for name in nr.ElementNames:
        content = nr.getByName(name).Content
        if '#REF!' in content:
            if any(name.startswith(p) for p in STRUCTURAL_PREFIXES) or name in STRUCTURAL_NAMES:
                errors.append(f"Named range structurel #REF! : {name} → {content}")

    # --- Cohérence ranges colonnes vs START/END ---
    import re as _re
    RANGE_FAMILIES = {
        'AVR': ('START_AVR', 'END_AVR'),
        'PVL': ('START_PVL', 'END_PVL'),
    }
    for prefix, (start_name, end_name) in RANGE_FAMILIES.items():
        start_pos = get_named_range_pos(xdoc, start_name)
        end_pos = get_named_range_pos(xdoc, end_name)
        if not start_pos or not end_pos:
            continue
        expected_start_row = start_pos[2] + 1  # 0-indexed → 1-indexed
        expected_end_row = end_pos[2] + 1
        for name in nr.ElementNames:
            if not name.startswith(prefix) or name.startswith(f'{prefix}_'):
                continue  # skip START_AVR/END_AVR eux-mêmes
            content = nr.getByName(name).Content
            if '#REF!' in content:
                continue
            rows = _re.findall(r'\$(\d+)', content)
            if len(rows) >= 2:
                r_start, r_end = int(rows[0]), int(rows[1])
                if r_start != expected_start_row or r_end != expected_end_row:
                    errors.append(
                        f"{name} rows {r_start}:{r_end} != "
                        f"{start_name}/{end_name} rows {expected_start_row}:{expected_end_row}")

    # --- Marqueurs de headers ---
    # Opérations : header row 3 doit contenir "Date", "Montant", "Devise"
    ws_op = sheets.getByName(SHEET_OPERATIONS)
    for col_enum, label in ((OpCol.DATE, 'Date'), (OpCol.MONTANT, 'Montant'), (OpCol.DEVISE, 'Devise')):
        val = ws_op.getCellByPosition(uno_col(col_enum), uno_row(3)).getString().strip()
        if val and label.lower() not in val.lower():
            warnings.append(f"Opérations header col {chr(64+col_enum)}: attendu '{label}', trouvé '{val}'")

    # Plus_value : vérifier header
    ws_pv = sheets.getByName(SHEET_PLUS_VALUE)
    start_pvl = get_named_range_pos(xdoc, 'START_PVL')
    if start_pvl:
        pv_header_row = start_pvl[2]
        for col_enum, label in ((PvCol.SECTION, 'Section'), (PvCol.DEVISE, 'Devise')):
            val = ws_pv.getCellByPosition(uno_col(col_enum), pv_header_row).getString().strip()
            if val and label.lower() not in val.lower():
                warnings.append(f"Plus_value header col {chr(64+col_enum)}: attendu '{label}', trouvé '{val}'")

    # CTRL2 : vérifier que EUR est trouvable
    # Convention : START_CTRL2 pointe sur h+2 (données), header EUR = h+0 = START - 2
    ws_ctrl = sheets.getByName(SHEET_CONTROLES)
    ctrl2_pos = get_named_range_pos(xdoc, 'START_CTRL2')
    eur_found = False
    if ctrl2_pos:
        header_row = ctrl2_pos[2] - 2
        val = ws_ctrl.getCellByPosition(ctrl2_pos[1], header_row).getString().strip()
        if val == 'EUR':
            eur_found = True
        else:
            warnings.append(f"START_CTRL2 header (row {header_row+1}): attendu 'EUR', trouvé '{val}' — fallback scan")
    if not eur_found:
        for r in range(0, 80):
            for c in range(14, 35):
                if ws_ctrl.getCellByPosition(c, r).getString().strip() == 'EUR':
                    eur_found = True
                    break
            if eur_found:
                break
        if not eur_found:
            errors.append("CTRL2 : header 'EUR' introuvable")

    return len(errors) == 0, errors, warnings


class IntegrityChecker:
    """Vérifie l'intégrité des formules d'un classeur comptes.xlsm."""

    def __init__(self, xdoc):
        self.xdoc = xdoc
        self.errors = []
        self.warnings = []
        self.checked = 0

    def get_bounds(self, start_name, end_name):
        """Return (sheet_name, start_col, start_row, end_col, end_row) or None."""
        s = get_named_range_pos(self.xdoc, start_name)
        e = get_named_range_pos(self.xdoc, end_name)
        if s is None or e is None:
            self.warnings.append(f"Noms définis manquants : {start_name}/{end_name}")
            return None
        return s[0], s[1], s[2], e[1], e[2]

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
        bounds = self.get_bounds("START_AVR", "END_AVR")
        if not bounds:
            return
        sheet_name, _, row_start, _, row_end = bounds
        sheet = self.xdoc.Sheets.getByName(sheet_name)
        label = "Avoirs"

        # Only check rows that have a devise (col E=4) — rows without devise
        # are mobilier/immobilier/special with manual values
        formula_rows = []
        for row in range(row_start, row_end + 1):
            devise = sheet.getCellByPosition(4, row).getString()
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

        # Check Total row (row after END_AVR)
        total_row = row_end + 1
        total_a = sheet.getCellByPosition(0, total_row).getString()
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
        bounds = self.get_bounds("START_CTRL1", "END_CTRL1")
        if not bounds:
            return
        sheet_name, _, row_start, _, row_end = bounds
        sheet = self.xdoc.Sheets.getByName(sheet_name)
        label = "Contrôles"

        # D=3 (# déb, COUNTIFS), E=4 (date fin, MAXIFS), F=5 (durée)
        # L=11 (reports fin, SUMIFS or value)
        for col in [3, 4, 5, 11]:
            self._check_formula_col(sheet, col, row_start, row_end, label,
                                    allow_empty=True)

    def check_controles_synthese(self):
        """Check Contrôles synthèse section: N, O columns."""
        bounds = self.get_bounds("START_CTRL2", "END_CTRL2")
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
        bounds = self.get_bounds("START_PVL", "END_PVL")
        if not bounds:
            return
        sheet_name, _, row_start, _, row_end = bounds
        sheet = self.xdoc.Sheets.getByName(sheet_name)
        label = "Plus_value"

        for row in range(row_start, row_end + 1):
            b_val = sheet.getCellByPosition(1, row).getString().strip()
            if not b_val:
                continue  # Empty row

            c_val = sheet.getCellByPosition(2, row).getString().strip()
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
        """Check Budget devise exchange rate row (SUMIF Cotations)."""
        bounds = self.get_bounds("START_CAT", "END_CAT")
        if not bounds:
            return
        sheet_name, cat_col, cat_start, _, _ = bounds
        sheet = self.xdoc.Sheets.getByName(sheet_name)
        label = "Budget"

        cours_row = None
        for row in range(max(0, cat_start - 5), cat_start + 2):
            for col in range(cat_col + 1, cat_col + 15):
                f = sheet.getCellByPosition(col, row).getFormula()
                if f and 'SUMIF' in f.upper() and 'Cotations' in f:
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
        bounds = self.get_bounds("START_COT", "END_COT")
        if not bounds:
            return
        sheet_name, _, row_start, _, row_end = bounds
        sheet = self.xdoc.Sheets.getByName(sheet_name)
        label = "Cotations"

        empty_rows = 0
        for row in range(row_start, row_end + 1):
            a = sheet.getCellByPosition(0, row).getString()
            self.checked += 1
            if not a:
                empty_rows += 1
        if empty_rows > 2:
            self.warnings.append(
                f"  {label}: {empty_rows} lignes vides sur "
                f"{row_end - row_start + 1}")

    def check_named_ranges(self):
        """Verify all 14 named ranges exist and point to valid cells."""
        expected = [
            "START_POSTES", "END_POSTES",
            "START_CAT", "END_CAT",
            "START_CTRL1", "END_CTRL1",
            "START_CTRL2", "END_CTRL2",
            "START_AVR", "END_AVR",
            "START_PVL", "END_PVL",
            "START_COT", "END_COT",
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
        """Scan toutes les feuilles pour détecter les cellules #REF!."""
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
                    if '#REF!' in formula or cell.getError() == 524:
                        ref_count += 1
                        self.errors.append(
                            f"  {name} {col_letter(col)}{row+1}: "
                            f"#REF! — {formula[:60]}")
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
