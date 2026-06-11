#!/usr/bin/env python3-uno
"""Migration classeur v5.0.0 — fiabilisation alarmes contre #REF! orphelines.

Sections intégrées :

1. Cotations!B{alarme} — IFERROR sur SUMPRODUCT completeness
   Wrappe `SUMPRODUCT((COTcode<>"")*(COTcours=""))` dans `IFERROR(...;1)`.
   Sans ça, un `#REF!` dans une cellule COTcours (typiquement après
   suppression d'une devise mère sans nettoyage des dérivées) propageait
   l'erreur dans `COTcours=""` → SUMPRODUCT plantait → IF retournait l'erreur
   et l'alarme métier n'affichait plus ⚠ visible. IFERROR force le résultat
   à 1 → l'alarme bascule à ⚠.

2. Contrôles!K{Synthèse} — IFERROR par section dans la concat
   Wrappe chaque token K{section} (COMPTES, CATÉGORIES, DIVERS, …) dans
   `IFERROR(K{r};"⚠")`. Sans ça, une section déjà en erreur (#REF! propagé
   depuis une dépendance) cassait la concat → FIND retournait l'erreur →
   `ISNUMBER(#REF!) = FALSE` → la synthèse tombait à ✓ alors qu'une section
   affichait ✗ visiblement. IFERROR convertit chaque section cassée en ⚠.

Idempotent : si déjà migré, ne fait rien. SCHEMA_VERSION inchangé (3) — ces
deux fixes sont des améliorations de formules, pas du structurel.

Usage:
    python3 tool_migrate_v5.0.0.py ~/Compta/comptes.xlsm
    python3 tool_migrate_v5.0.0.py ~/Compta/comptes.xlsm --dry-run
"""
import argparse
import shutil
import sys
from pathlib import Path

from inc_uno import UnoDocument, check_lock_file, require_libreoffice_min
from inc_excel_schema import uno_row


CTRL2_TYPE_COL = 9    # J
CTRL2_DISPL_COL = 10  # K


def _ctrl2_find_row(ws_ctrl, label):
    """Cherche `label` dans la col CTRL2type (J)."""
    for r in range(1, 200):
        v = ws_ctrl.getCellByPosition(
            CTRL2_TYPE_COL, uno_row(r)).getString().strip()
        if v == label:
            return r
    return None


def _section1_cotations_alarm_iferror(ws_cot, dry_run, changes):
    """Cotations!B{alarme} — wrapper IFERROR sur la branche (b) completeness.

    Cible la même cellule que la section 3 de v4.1.0 (alarme métier
    completeness). Position retrouvée dynamiquement via la 2e sentinelle ⚓
    en col A (pied de la table Cotations) — layout-agnostic.
    """
    anchor_row = None
    for r in range(2, 100):
        v = ws_cot.getCellByPosition(0, uno_row(r)).getString().strip()
        if v == '⚓':
            if anchor_row is None:
                anchor_row = r
            else:
                anchor_row = r
                break
    target_row = (anchor_row + 1) if anchor_row else 20

    formula = (
        '=IF('
        # (a) Devises utilisées non listées
        'SUMPRODUCT((COUNTIF(COTcode;PVLdevise)=0)*(PVLdevise<>""))'
        '+SUMPRODUCT((COUNTIF(COTcode;AVRdevise)=0)*(AVRdevise<>""))'
        # (b) Codes listés mais cours vide / (c) cours en erreur (#REF!)
        '+IFERROR(SUMPRODUCT((COTcode<>"")*(COTcours=""));1)'
        '>0;"⚠";"✓")'
    )
    cell = ws_cot.getCellByPosition(1, uno_row(target_row))
    if cell.getFormula() != formula:
        if not dry_run:
            cell.setFormula(formula)
        changes.append(
            f"~ Cotations!B{target_row} : IFERROR sur SUMPRODUCT "
            f"completeness (capte #REF! orphelines)")


def _section2_synthese_iferror(ws_ctrl, cr, doc, dry_run, changes):
    """Contrôles!K{Synthèse} — wrapper IFERROR sur chaque token K{section}.

    Bornes via NR CTRL2type (layout-agnostic). Refresh cr préalable au cas où
    une migration antérieure a étendu les NRs côté UNO sans invalider le
    cache ColResolver.
    """
    cr.refresh(xdoc=doc.document)
    headers = ['COMPTES', 'CATÉGORIES', 'DIVERS', 'APPARIEMENTS',
               'BALANCES', 'INCONNUS', 'FORMULES']
    rows = {}
    try:
        s, e = cr.rows('CTRL2type')
        scan_range = range(max(1, s - 2), e + 5)
    except Exception:
        scan_range = range(1, 200)
    for r in scan_range:
        v = ws_ctrl.getCellByPosition(
            CTRL2_TYPE_COL, uno_row(r)).getString().strip()
        for lbl in headers:
            if v == lbl or v.startswith(lbl):
                rows[lbl] = r

    missing = [h for h in headers if h not in rows]
    if missing:
        print(f"⚠ Synthèse : headers manquants {missing} — skip "
              f"(classeur pas migré v4.1.0 ?)")
        return

    synth_row = _ctrl2_find_row(ws_ctrl, 'Synthèse des contrôles')
    if synth_row is None:
        synth_row = _ctrl2_find_row(ws_ctrl, 'Synthèse')
    if synth_row is None:
        print("⚠ Synthèse : ligne 'Synthèse [des contrôles]' introuvable — skip")
        return

    k_concat = '&'.join(f'IFERROR(K{rows[h]};"⚠")' for h in headers)
    synth_k = (
        f'=IF(ISNUMBER(FIND("✗";{k_concat}));"✗";'
        f'IF(ISNUMBER(FIND("⚠";{k_concat}));"⚠";"✓"))'
    )
    cell = ws_ctrl.getCellByPosition(CTRL2_DISPL_COL, uno_row(synth_row))
    if cell.getFormula() != synth_k:
        if not dry_run:
            cell.setFormula(synth_k)
        changes.append(
            f"~ Contrôles!K{synth_row} : IFERROR wrapper par section "
            f"(évite masquage ✓ silencieux)")


def migrate(xlsm_path, dry_run=False):
    # LO < 24.8 corrompt les XLOOKUP via UNO save (ajoute `_xlfn.` illisible).
    # On sort avant ouverture pour éviter d'écrire un classeur corrompu.
    if not dry_run:
        require_libreoffice_min(24, 8)

    p = Path(xlsm_path).resolve()
    if not p.exists():
        print(f"❌ Fichier introuvable : {p}")
        return 1
    if check_lock_file(p):
        print(f"❌ Fichier verrouillé : {p}")
        print("   Ferme LibreOffice.")
        return 1

    with UnoDocument(p) as doc:
        cr = doc.cr
        ws_cot = doc.get_sheet('Cotations')
        ws_ctrl = doc.get_sheet('Contrôles')

        changes = []

        try:
            _section1_cotations_alarm_iferror(ws_cot, dry_run, changes)
        except Exception as e:
            print(f"⚠ Section 1 (Cotations B22) : {e}")

        try:
            _section2_synthese_iferror(ws_ctrl, cr, doc, dry_run, changes)
        except Exception as e:
            print(f"⚠ Section 2 (Synthèse K) : {e}")

        if not changes:
            print(f"✓ {p.name} : déjà migré, rien à faire.")
            return 0

        print(f"Migration {p.name} :")
        for c in changes:
            print(f"  {c}")

        if dry_run:
            print("\n[dry-run] pas de sauvegarde")
            return 0

        bak = p.with_suffix('.xlsm.bak')
        shutil.copy2(p, bak)
        print(f"📦 Backup : {bak.name}")

        doc.save()
        print(f"\n✓ Sauvé : {p}")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('xlsm', help='Chemin du classeur à migrer')
    ap.add_argument('--dry-run', action='store_true',
                    help="N'enregistre pas, affiche les changements prévus")
    args = ap.parse_args()
    return migrate(args.xlsm, dry_run=args.dry_run)


if __name__ == '__main__':
    sys.exit(main())
