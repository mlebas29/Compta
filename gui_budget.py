"""Mixin Budget (postes et catégories) pour HeadlessGUI / ConfigGUI."""

import shutil
from inc_excel_schema import (
    uno_col, uno_row, ColResolver,
    SHEET_BUDGET,
)


class BudgetMixin:
    """Opérations UNO sur la feuille Budget : ajout de postes et catégories."""

    def _add_category(self, name, poste='Divers', alloc_pct=1.0, doc=None):
        """Insère une catégorie dans la feuille Budget via UNO.

        Args:
            doc: UnoDocument ouvert (mode batch). Si None, ouvre/ferme automatiquement.
        """
        if name in self.budget_categories:
            print(f"ERREUR: catégorie '{name}' existe déjà")
            return False
        if not self.budget_insert_row:
            print(f"ERREUR: point d'insertion Budget introuvable")
            return False

        from contextlib import nullcontext
        from inc_uno import UnoDocument

        owned = doc is None
        ctx = UnoDocument(self.xlsx_path) if owned else nullcontext(doc)
        with ctx as doc:
            cr = doc.cr
            ws = doc.get_sheet(SHEET_BUDGET)
            insert_row = self.budget_insert_row
            r = insert_row
            r0 = uno_row(r)

            # Insérer 1 ligne avant le séparateur "-"
            ws.Rows.insertByIndex(r0, 1)
            # Style propagé automatiquement depuis la model row par insertByIndex

            # Nom catégorie
            ws.getCellByPosition(uno_col(self.budget_cat_col), r0).setString(name)

            # Devises : SUMIFS par devise
            hr = self.budget_header_row
            cat_letter = ColResolver._idx_to_letter(self.budget_cat_col)
            last = self.budget_last_devise_col
            for col in range(self.budget_first_devise_col, last + 1):
                cl = ColResolver._idx_to_letter(col)
                ws.getCellByPosition(uno_col(col), r0).setFormula(
                    f'=SUMIFS(OPmontant;OPdevise;{cl}${hr};OPcatégorie;${cat_letter}{r};OPdate;">"&$C$2-365)')

            # Equiv EUR : SUMPRODUCT
            equiv_col = cr.col('CATtotal_euro') + 1  # openpyxl 1-indexed
            first_dev_letter = ColResolver._idx_to_letter(self.budget_first_devise_col)
            last_letter = ColResolver._idx_to_letter(last)
            sr = self.budget_start_row
            ws.getCellByPosition(uno_col(equiv_col), r0).setFormula(
                f'=SUMPRODUCT({first_dev_letter}{r}:{last_letter}{r};{first_dev_letter}${sr}:{last_letter}${sr})')

            # Allocation 100%
            alloc_pct_col = cr.col('CATaffectation_pct') + 1
            alloc_montant_col = cr.col('CATaffectation') + 1
            poste_col = cr.col('CATposte') + 1
            cell_pct = ws.getCellByPosition(uno_col(alloc_pct_col), r0)
            cell_pct.setValue(alloc_pct)
            # Format % (la model row a General → patcher la 1ère ligne, les suivantes propagent)
            cell_pct.NumberFormat = doc.register_number_format('0%')
            equiv_letter = ColResolver._idx_to_letter(equiv_col)
            ws.getCellByPosition(uno_col(alloc_montant_col), r0).setFormula(
                f'={equiv_letter}{r}*{ColResolver._idx_to_letter(alloc_pct_col)}{r}')

            # Poste budgétaire
            ws.getCellByPosition(uno_col(poste_col), r0).setString(poste)

            # Mettre à jour l'état mémoire
            self.budget_categories.append(name)
            self.budget_cat_rows[name] = r
            self.budget_insert_row = insert_row + 1
            if self.budget_total_row:
                self.budget_total_row += 1

            if owned:
                doc.save()

        if owned:
            self._load_excel_data()

        print(f"Catégorie ajoutée: {name} (poste={poste})")
        return True

    def _add_poste(self, name, fixe=True, doc=None):
        """Insère un poste dans la feuille Budget via UNO.

        Args:
            doc: UnoDocument ouvert (mode batch). Si None, ouvre/ferme automatiquement.
        """
        if name in self.budget_posts:
            print(f"ERREUR: poste '{name}' existe déjà")
            return False

        from contextlib import nullcontext
        from inc_uno import UnoDocument
        from inc_excel_schema import ColResolver

        owned = doc is None
        ctx = UnoDocument(self.xlsx_path) if owned else nullcontext(doc)
        with ctx as doc:
            cr = doc.cr
            ws = doc.get_sheet(SHEET_BUDGET)

            # Insérer avant END (dernière model row)
            _, end_row = cr.rows('POSTESnom')
            insert_row = end_row if end_row else (max(self.budget_post_rows.values()) + 1 if self.budget_post_rows else 10)

            r0 = uno_row(insert_row)
            ws.Rows.insertByIndex(r0, 1)
            # Style propagé automatiquement depuis la model row par insertByIndex

            # Nom poste (col A)
            ws.getCellByPosition(0, r0).setString(name)
            # Type (col B) : Fixe ou Variable
            ws.getCellByPosition(1, r0).setString('Fixe' if fixe else 'Variable')

            # Mettre à jour l'état mémoire AVANT l'écriture des formules
            # (l'insertByIndex a déjà décalé les lignes réelles)
            self.budget_posts.append(name)
            self.budget_post_rows[name] = insert_row
            if self.budget_insert_row and insert_row <= self.budget_insert_row:
                self.budget_insert_row += 1
            if self.budget_total_row and insert_row <= self.budget_total_row:
                self.budget_total_row += 1
            if self.budget_start_row and insert_row <= self.budget_start_row:
                self.budget_start_row += 1
            if self.budget_header_row and insert_row <= self.budget_header_row:
                self.budget_header_row += 1
            if hasattr(self, 'budget_posts_total_row') and self.budget_posts_total_row and insert_row <= self.budget_posts_total_row:
                self.budget_posts_total_row += 1
            for cat_name in self.budget_cat_rows:
                if insert_row <= self.budget_cat_rows[cat_name]:
                    self.budget_cat_rows[cat_name] += 1

            # Formule SUMIF (col C) : =SUMIF(poste_range, A{row}, alloc_range)
            poste_col = cr.col('CATposte') + 1  # openpyxl 1-indexed
            alloc_col = cr.col('CATaffectation') + 1
            pl = ColResolver._idx_to_letter(poste_col)
            al = ColResolver._idx_to_letter(alloc_col)
            first_cat = min(self.budget_cat_rows.values()) if self.budget_cat_rows else (self.budget_start_row or 14) + 2
            sep = self.budget_insert_row or first_cat
            ws.getCellByPosition(2, r0).setFormula(
                f'=SUMIF({pl}{first_cat}:{pl}{sep};A{insert_row};{al}{first_cat}:{al}{sep})')

            # Réécrire les pieds POSTES (Total, Epargne fixe) avec le range complet
            # Les formules template sont en single-cell et ne s'étendent pas
            first_data = min(self.budget_post_rows.values())
            last_data = max(self.budget_post_rows.values())
            tr = getattr(self, 'budget_posts_total_row', None)
            if tr:
                ws.getCellByPosition(2, uno_row(tr)).setFormula(
                    f'=SUM(C{first_data}:C{last_data})')
                ws.getCellByPosition(2, uno_row(tr + 1)).setFormula(
                    f'=SUMIF($B{first_data}:$B{last_data};"Fixe";C{first_data}:C{last_data})')

            if owned:
                doc.save()

        if owned:
            self._load_excel_data()

        print(f"Poste ajouté: {name} ({'Fixe' if fixe else 'Variable'})")
        return True

    def _delete_category(self, name, reassign_to=None, doc=None):
        """Supprime une catégorie de la feuille Budget via UNO.

        Même logique que CategoriesMixin._delete_budget_category +
        _after_budget_cat_delete, sans dépendance tkinter.
        """
        if name not in self.budget_cat_rows:
            print(f"ERREUR: catégorie '{name}' introuvable")
            return False

        from contextlib import nullcontext
        from inc_uno import UnoDocument
        from inc_excel_schema import ColResolver

        owned = doc is None
        ctx = UnoDocument(self.xlsx_path) if owned else nullcontext(doc)
        with ctx as doc:
            cr = doc.cr
            # Réaffecter les opérations col G si demandé
            if reassign_to:
                ws_ops = doc.get_sheet(SHEET_OPERATIONS)
                col_g = cr.col('OPcatégorie')
                cursor = ws_ops.createCursor()
                cursor.gotoStartOfUsedArea(False)
                cursor.gotoEndOfUsedArea(True)
                last_row_0 = cursor.getRangeAddress().EndRow
                for r in range(2, last_row_0 + 1):
                    cell = ws_ops.getCellByPosition(col_g, r)
                    if cell.getString() == name:
                        cell.setString(reassign_to)

            # Supprimer la ligne Budget
            ws = doc.get_sheet(SHEET_BUDGET)
            cat_row = self.budget_cat_rows[name]
            ws.Rows.removeByIndex(uno_row(cat_row), 1)

            # Mettre à jour l'état mémoire
            del self.budget_cat_rows[name]
            self.budget_categories.remove(name)
            for cat, row in self.budget_cat_rows.items():
                if row > cat_row:
                    self.budget_cat_rows[cat] = row - 1
            if self.budget_insert_row and self.budget_insert_row > cat_row:
                self.budget_insert_row -= 1
            if self.budget_total_row and self.budget_total_row > cat_row:
                self.budget_total_row -= 1

            if owned:
                doc.save()

        if owned:
            self._load_excel_data()

        print(f"Catégorie supprimée: {name}")
        return True

    def _delete_poste(self, name, doc=None):
        """Supprime un poste budgétaire de la feuille Budget via UNO.

        Même logique que CategoriesMixin._delete_budget_post +
        _after_budget_post_delete, sans dépendance tkinter.
        """
        if name not in self.budget_post_rows:
            print(f"ERREUR: poste '{name}' introuvable")
            return False

        from contextlib import nullcontext
        from inc_uno import UnoDocument

        owned = doc is None
        ctx = UnoDocument(self.xlsx_path) if owned else nullcontext(doc)
        with ctx as doc:
            ws = doc.get_sheet(SHEET_BUDGET)
            post_row = self.budget_post_rows[name]
            ws.Rows.removeByIndex(uno_row(post_row), 1)

            # Mettre à jour l'état mémoire
            del self.budget_post_rows[name]
            self.budget_posts.remove(name)
            if name in self.budget_post_types:
                del self.budget_post_types[name]
            for p, row in self.budget_post_rows.items():
                if row > post_row:
                    self.budget_post_rows[p] = row - 1
            if hasattr(self, 'budget_posts_total_row') and self.budget_posts_total_row and self.budget_posts_total_row > post_row:
                self.budget_posts_total_row -= 1
            for cat, row in self.budget_cat_rows.items():
                if row > post_row:
                    self.budget_cat_rows[cat] = row - 1
            if self.budget_insert_row and self.budget_insert_row > post_row:
                self.budget_insert_row -= 1
            if self.budget_total_row and self.budget_total_row > post_row:
                self.budget_total_row -= 1

            if owned:
                doc.save()

        if owned:
            self._load_excel_data()

        print(f"Poste supprimé: {name}")
        return True
