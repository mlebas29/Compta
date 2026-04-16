#!/usr/bin/env python3
"""Migration one-shot : formules PVL multi-devise → SUMPRODUCT générique.

Réécrit :
- TOTAL portefeuilles (H/I/K) via lookup COTcode/COTcours
- Total des blocs portefeuille avec >1 devise parmi leurs titres (ex. Yuh)

Capture les valeurs GRAND TOTAL / TOTAL portefeuilles / blocs AVANT et APRÈS
pour vérifier qu'aucune valeur ne change (ou pour révéler le bug latent).

Usage:
    python3 tool_migrate_pvl_totals.py ~/Compta/comptes.xlsm
    python3 tool_migrate_pvl_totals.py ~/Compta/comptes.xlsm --dry-run
"""
import argparse
import sys
from pathlib import Path

from inc_uno import UnoDocument, check_lock_file
from inc_excel_schema import SHEET_PLUS_VALUE, ColResolver, uno_row


PVL_COLS = ('PVLmontant_init', 'PVLsigma', 'PVLmontant')
LOOKUP = 'IFERROR(INDEX(COTcours;MATCH(PVLdevise;COTcode;0));1)'


def _snapshot(ws, cr, rows):
    """Capture les valeurs H/I/K (et E pour GRAND TOTAL) de chaque ligne."""
    snap = {}
    for r in rows:
        r0 = uno_row(r)
        snap[r] = {
            'E': ws.getCellByPosition(cr.col('PVLpvl'), r0).getValue(),
            'H': ws.getCellByPosition(cr.col('PVLmontant_init'), r0).getValue(),
            'I': ws.getCellByPosition(cr.col('PVLsigma'), r0).getValue(),
            'K': ws.getCellByPosition(cr.col('PVLmontant'), r0).getValue(),
        }
    return snap


def _find_rows(ws, cr):
    """Localise GRAND TOTAL, TOTAL portefeuilles, et tous les blocs Total portefeuille."""
    total_pf_row = None
    grand_total_row = None
    bloc_totals = []  # [(row, account_name)]
    current_account = None

    for r in range(1, 300):
        r0 = uno_row(r)
        a = ws.getCellByPosition(cr.col('PVLsection'), r0).getString().strip()
        b = ws.getCellByPosition(cr.col('PVLcompte'), r0).getString().strip()
        c = ws.getCellByPosition(cr.col('PVLtitre'), r0).getString().strip()
        if a == 'GRAND TOTAL':
            grand_total_row = r
        elif a == 'TOTAL portefeuilles':
            total_pf_row = r
        elif a == 'portefeuilles' and c == 'Total' and b:
            bloc_totals.append((r, b))
    return grand_total_row, total_pf_row, bloc_totals


def _bloc_titres_devises(ws, cr, account_name, total_row):
    """Retourne {devise: [rows]} pour les titres *...* du bloc au-dessus de total_row."""
    devises = {}
    col_b = cr.col('PVLcompte')
    col_c = cr.col('PVLtitre')
    col_d = cr.col('PVLdevise')
    for scan in range(total_row - 1, 0, -1):
        b = ws.getCellByPosition(col_b, uno_row(scan)).getString().strip()
        if b != account_name:
            break
        c = ws.getCellByPosition(col_c, uno_row(scan)).getString().strip()
        if c.startswith('*') and c.endswith('*'):
            d = ws.getCellByPosition(col_d, uno_row(scan)).getString().strip()
            if d:
                devises.setdefault(d, []).append(scan)
    return devises


def _rewrite_total_pf(ws, cr, row):
    """Réécrit TOTAL portefeuilles H/I/K avec SUMPRODUCT + lookup."""
    r0 = uno_row(row)
    for nr_name in PVL_COLS:
        formula = (
            f'=SUMPRODUCT((PVLsection="portefeuilles")*(PVLtitre="Retenu")'
            f'*{nr_name}*{LOOKUP})'
        )
        ws.getCellByPosition(cr.col(nr_name), r0).setFormula(formula)


def _rewrite_bloc_total(ws, cr, devises, total_row):
    """Réécrit Total bloc H/I/K via SUMPRODUCT — reste en devise pivot (D{total_row})."""
    first = min(r for rows in devises.values() for r in rows)
    last = max(r for rows in devises.values() for r in rows)
    d_range = f'D{first}:D{last}'
    pivot = f'IFERROR(INDEX(COTcours;MATCH(D{total_row};COTcode;0));1)'
    lookup_bloc = f'IFERROR(INDEX(COTcours;MATCH({d_range};COTcode;0));1)'
    r0 = uno_row(total_row)
    for nr_name in PVL_COLS:
        cl = cr.letter(nr_name)
        formula = (
            f'=SUMPRODUCT({cl}{first}:{cl}{last}*{lookup_bloc})/{pivot}'
        )
        ws.getCellByPosition(cr.col(nr_name), r0).setFormula(formula)


def _format_delta(before, after):
    lines = []
    for row in sorted(before.keys()):
        b, a = before[row], after[row]
        for col in ('E', 'H', 'I', 'K'):
            if abs(b[col] - a[col]) > 1e-6:
                lines.append(f"    row {row} {col}: {b[col]:.2f} → {a[col]:.2f} (Δ {a[col]-b[col]:+.2f})")
    return lines


def migrate(xlsx_path, dry_run=False):
    p = Path(xlsx_path).expanduser().resolve()
    if not p.exists():
        print(f"❌ Fichier introuvable : {p}")
        return 1
    if check_lock_file(p):
        print(f"❌ Fichier verrouillé (LibreOffice ouvert) : {p}")
        return 1

    with UnoDocument(str(p)) as doc:
        xdoc = doc.document
        cr = ColResolver.from_uno(xdoc)
        ws = doc.get_sheet(SHEET_PLUS_VALUE)

        gt_row, pf_row, bloc_rows = _find_rows(ws, cr)
        if pf_row is None:
            print("❌ 'TOTAL portefeuilles' introuvable")
            return 1
        print(f"GRAND TOTAL row {gt_row}, TOTAL portefeuilles row {pf_row}")
        print(f"Blocs portefeuille détectés : {len(bloc_rows)}")

        # Identifier les blocs multi-devise
        bloc_multi = []
        for r, name in bloc_rows:
            devises = _bloc_titres_devises(ws, cr, name, r)
            if len(devises) > 1:
                bloc_multi.append((r, name, devises))
                print(f"  bloc multi-devise : row {r} {name} → {sorted(devises.keys())}")
        if not bloc_multi and pf_row is None:
            print("Aucune formule à migrer.")
            return 0

        # Snapshot BEFORE (force recalc d'abord)
        doc.calculate_all()
        snap_rows = [gt_row, pf_row] + [r for r, _, _ in bloc_multi]
        snap_rows = [r for r in snap_rows if r is not None]
        before = _snapshot(ws, cr, snap_rows)
        print(f"\nSnapshot AVANT ({len(before)} lignes) :")
        for r in sorted(before.keys()):
            v = before[r]
            print(f"  row {r}: E={v['E']:.2f} H={v['H']:.2f} I={v['I']:.2f} K={v['K']:.2f}")

        # Réécrire TOTAL portefeuilles
        _rewrite_total_pf(ws, cr, pf_row)
        print(f"\n✓ TOTAL portefeuilles (row {pf_row}) réécrit")

        # Réécrire blocs multi-devise
        for r, name, devises in bloc_multi:
            _rewrite_bloc_total(ws, cr, devises, r)
            print(f"✓ Bloc {name} (row {r}) réécrit")

        # Snapshot AFTER
        doc.calculate_all()
        after = _snapshot(ws, cr, snap_rows)

        deltas = _format_delta(before, after)
        if deltas:
            print("\n⚠️  Écarts détectés (probablement bug latent désormais corrigé) :")
            for line in deltas:
                print(line)
        else:
            print("\n✓ Valeurs identiques avant/après — migration transparente")

        if dry_run:
            print("\n[dry-run] pas de sauvegarde")
            return 0

        doc.save()
        print(f"\n✓ Sauvé : {p}")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('xlsm', help='Chemin du classeur comptes.xlsm')
    ap.add_argument('--dry-run', action='store_true', help='N\'enregistre pas, affiche les écarts')
    args = ap.parse_args()
    return migrate(args.xlsm, dry_run=args.dry_run)


if __name__ == '__main__':
    sys.exit(main())
