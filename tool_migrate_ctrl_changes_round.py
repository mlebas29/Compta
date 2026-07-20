#!/usr/bin/env python3-uno
"""Migration idempotente : enveloppe la ligne « Changes Eq € » du bloc BALANCES
(feuille Contrôles, colonne € = L) dans ROUND(...,0).

Contexte (#176) : le compteur BALANCES `L = 3-COUNTIFS(Lvir:Lchg,0)` teste
l'égalité EXACTE à zéro. Ses trois lignes sont « Virements € », « Titres € »,
« Changes Eq € ». Les deux premières sont déjà `ROUND(SUMIFS(...),0)` ; seule
« Changes Eq € » ne l'était pas → un résidu flottant (ex. 4.08e-14, affiché
« 0.00 ») comptait comme anomalie → K = ⚠ → A1 = ⚠, sans aucun vrai
déséquilibre. Enrober de ROUND absorbe le bruit, comme ses sœurs.

Le bloc BALANCES se déplace verticalement (le tableau CTRL1 au-dessus grossit
avec le nombre de comptes) → la ligne est trouvée PAR LIBELLÉ (« Changes Eq »
dans la colonne des libellés), jamais par cellule fixe. La formule existante est
réutilisée VERBATIM et simplement enveloppée → aucune hypothèse de séparateur
(UNO rend `;` en locale FR, le stockage xlsx est en `,`).

Idempotent : ne fait rien si la formule est déjà enveloppée de ROUND.

Usage :
    python3 tool_migrate_ctrl_changes_round.py ~/Compta/comptes.xlsm [--dry-run]

--dry-run : sonde openpyxl SANS LibreOffice (rc 3 = changerait, 0 = déjà à jour).
"""
import argparse
import sys
from pathlib import Path

SHEET = 'Contrôles'
LABEL = 'Changes Eq'   # sous-chaîne du libellé (colonne des libellés du bloc BALANCES)
VALUE_COL_OFFSET = 2   # libellé en col J → valeur € en col L (J→K→L)


def _find_label_cell(ws, get):
    """Retourne (row, col) 1-indexés de la cellule dont la valeur contient LABEL,
    ou (None, None). `get(r, c)` renvoie la valeur texte de la cellule 1-indexée."""
    for r in range(1, ws.max_row + 1 if hasattr(ws, 'max_row') else 60):
        for c in range(1, 20):
            v = get(r, c)
            if v and LABEL in str(v):
                return r, c
    return None, None


def _already_round(xlsm_path):
    """Sonde openpyxl (SANS LibreOffice) : la formule € de « Changes Eq » est-elle
    déjà enveloppée de ROUND ? True = migration inutile."""
    import openpyxl
    wb = openpyxl.load_workbook(xlsm_path, data_only=False,
                               keep_vba=str(xlsm_path).endswith('.xlsm'))
    try:
        if SHEET not in wb.sheetnames:
            return True                          # pas de feuille Contrôles → rien à faire
        ws = wb[SHEET]
        r, c = _find_label_cell(ws, lambda rr, cc: ws.cell(rr, cc).value)
        if r is None:
            return True                          # libellé absent → rien à faire
        formula = ws.cell(r, c + VALUE_COL_OFFSET).value or ''
        return str(formula).upper().lstrip().startswith('=ROUND(')
    finally:
        wb.close()


def _apply(xlsm_path):
    """Enveloppe la formule € de « Changes Eq » dans ROUND(...,0) via UNO. Idempotent."""
    from inc_uno import UnoDocument, check_lock_file
    from inc_excel_schema import uno_row

    busy = check_lock_file(xlsm_path)
    if busy:
        print(f"✗ Classeur ouvert ({busy}) — ferme LibreOffice puis relance.", file=sys.stderr)
        return 1

    with UnoDocument(str(xlsm_path)) as doc:
        ws = doc.get_sheet(SHEET)
        # Recherche par libellé (0-indexé côté UNO)
        r0 = c0 = None
        for r in range(0, 60):
            for c in range(0, 20):
                if LABEL in ws.getCellByPosition(c, r).getString():
                    r0, c0 = r, c
                    break
            if r0 is not None:
                break
        if r0 is None:
            print(f"✗ Libellé « {LABEL} » introuvable dans {SHEET}.", file=sys.stderr)
            return 1

        vcell = ws.getCellByPosition(c0 + VALUE_COL_OFFSET, r0)
        formula = vcell.getFormula()             # locale UNO (séparateur `;`)
        if formula.upper().lstrip().startswith('=ROUND('):
            print("✓ « Changes Eq € » déjà enveloppée de ROUND — rien à faire.")
            return 0
        if not formula.startswith('='):
            print(f"✗ Cellule € de « {LABEL} » sans formule ({formula!r}).", file=sys.stderr)
            return 1

        body = formula[1:]                       # retire le `=`
        new_formula = f"=ROUND({body};0)"        # enveloppe verbatim, séparateur UNO
        vcell.setFormula(new_formula)
        col_letter = chr(ord('A') + c0 + VALUE_COL_OFFSET)
        doc.save()
        print(f"✓ « Changes Eq € » enveloppée de ROUND ({col_letter}{r0 + 1}).")

    # Hors du `with` (fichier fermé) : recadrer la vue salie par le save UNO
    # (patch ZIP-XML pur, idempotent). Cf. doctrine « --reframe avant livraison ».
    from tool_fix_formats import frame_views
    frame_views(str(xlsm_path), verbose=False)
    return 0


def main():
    ap = argparse.ArgumentParser(
        description="Enveloppe la ligne « Changes Eq € » (BALANCES) dans ROUND(...,0).")
    ap.add_argument('xlsm', help='chemin du classeur comptes.xlsm')
    ap.add_argument('--dry-run', action='store_true',
                    help='sonde openpyxl (rc 3 = changerait, 0 = déjà à jour), sans LibreOffice')
    args = ap.parse_args()

    p = Path(args.xlsm).expanduser()
    if not p.exists():
        print(f"✗ Introuvable : {p}", file=sys.stderr)
        return 1

    if args.dry_run:
        return 0 if _already_round(p) else 3

    return _apply(p)


if __name__ == '__main__':
    sys.exit(main())
