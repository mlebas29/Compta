#!/usr/bin/env python3
"""Migration one-shot : formules CTRL2 K/L multi-devise.

Réécrit dans la feuille Contrôles les formules K/L qui synthétisent par ligne
les écarts multi-devise (COMPTES, CATÉGORIES, € Virements, € Titres) :

- L(h+2), L(h+3), L(h+8), L(h+10) : SUM({EUR}..{dernière devise})
- K(h+2)                          : IF(L{h+2}=0;"✓";"✗")

h = ctrl2_header_row = CTRL2type START - 2 (ligne des codes devise).

Avant v3.5.2, seule la colonne EUR était sommée : les écarts sur les colonnes
devises non-EUR n'étaient pas détectés. Le fix applicatif corrige la génération
des formules à l'ajout d'une devise ; ce tool met à niveau les classeurs
existants dont les formules ont été figées avec l'ancienne logique.

Usage:
    python3 tool_migrate_ctrl2_formulas.py ~/Compta/comptes.xlsm --dry-run
    python3 tool_migrate_ctrl2_formulas.py ~/Compta/comptes.xlsm
"""
import argparse
import sys
from pathlib import Path

from inc_uno import UnoDocument, check_lock_file
from inc_excel_schema import SHEET_CONTROLES, ColResolver, uno_col, uno_row


L_COL_1 = 12  # colonne L (1-indexed)
K_COL_1 = 11  # colonne K (1-indexed)
OFFSETS = (2, 3, 8, 10)  # lignes relatives à h : COMPTES, CATÉGORIES, € Virements, € Titres


def _snapshot(ws, h):
    """Capture formules + valeurs K(h+2) et L(h+2,3,8,10)."""
    snap = {}
    for offset in OFFSETS:
        cell = ws.getCellByPosition(uno_col(L_COL_1), uno_row(h + offset))
        snap[f'L{h+offset}'] = {'f': cell.getFormula(), 'v': cell.getValue()}
    cell_k = ws.getCellByPosition(uno_col(K_COL_1), uno_row(h + 2))
    snap[f'K{h+2}'] = {'f': cell_k.getFormula(), 'v': cell_k.getString()}
    return snap


def _scan_last_devise_col(ws, h, eur_col_0):
    """Scanne la ligne header h depuis EUR jusqu'à la première cellule vide.

    Retourne l'indice 0-indexed de la dernière colonne devise non-vide.
    """
    last = eur_col_0
    for col_0 in range(eur_col_0, eur_col_0 + 30):
        val = ws.getCellByPosition(col_0, uno_row(h)).getString().strip()
        if not val:
            break
        last = col_0
    return last


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
        ws = doc.get_sheet(SHEET_CONTROLES)

        ctrl2_start, _ = cr.rows('CTRL2type')
        if ctrl2_start is None:
            print("❌ Named range CTRL2type introuvable")
            return 1
        h = ctrl2_start - 2  # ligne des codes devise

        eur_col_0 = cr.col('CTRL2eur')
        eur_letter = ColResolver._idx_to_letter(eur_col_0 + 1)
        last_col_0 = _scan_last_devise_col(ws, h, eur_col_0)
        last_letter = ColResolver._idx_to_letter(last_col_0 + 1)

        # Récapituler les devises détectées
        devises = []
        for col_0 in range(eur_col_0, last_col_0 + 1):
            code = ws.getCellByPosition(col_0, uno_row(h)).getString().strip()
            devises.append(code)
        print(f"CTRL2 header row : {h}")
        print(f"Devises détectées ({len(devises)}) : {devises}")
        print(f"Plage colonnes : {eur_letter}..{last_letter}")

        # Snapshot AVANT
        doc.calculate_all()
        before = _snapshot(ws, h)
        print("\nFormules AVANT :")
        for key in sorted(before.keys()):
            f = before[key]['f']
            v = before[key]['v']
            print(f"  {key} = {f!r}  → {v}")

        # Réécriture
        for offset in OFFSETS:
            row = h + offset
            formula = f'=SUM({eur_letter}{row}:{last_letter}{row})'
            ws.getCellByPosition(uno_col(L_COL_1), uno_row(row)).setFormula(formula)
        ws.getCellByPosition(uno_col(K_COL_1), uno_row(h + 2)).setFormula(
            f'=IF(L{h+2}=0;"✓";"✗")')

        # Snapshot APRÈS
        doc.calculate_all()
        after = _snapshot(ws, h)
        print("\nFormules APRÈS :")
        for key in sorted(after.keys()):
            f = after[key]['f']
            v = after[key]['v']
            print(f"  {key} = {f!r}  → {v}")

        # Deltas
        deltas = []
        for key in before:
            bf, af = before[key], after[key]
            if bf['f'] != af['f']:
                deltas.append(f"    {key} formule : {bf['f']!r} → {af['f']!r}")
            if bf['v'] != af['v']:
                deltas.append(f"    {key} valeur  : {bf['v']} → {af['v']}")
        if deltas:
            print("\n⚠️  Écarts détectés :")
            for line in deltas:
                print(line)
        else:
            print("\n✓ Aucun écart — formules déjà à jour")

        if dry_run:
            print("\n[dry-run] pas de sauvegarde")
            return 0

        doc.save()
        print(f"\n✓ Sauvé : {p}")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('xlsm', help='Chemin du classeur comptes.xlsm')
    ap.add_argument('--dry-run', action='store_true', help="N'enregistre pas, affiche les écarts")
    args = ap.parse_args()
    return migrate(args.xlsm, dry_run=args.dry_run)


if __name__ == '__main__':
    sys.exit(main())
