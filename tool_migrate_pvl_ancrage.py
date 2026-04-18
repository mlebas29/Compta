#!/usr/bin/env python3
"""Migration one-shot : ancrage PVL via OPequiv_euro sur #Solde.

Réécrit :
- Plus_value (sections métaux/crypto/devises) : PVLdate_init et PVLmontant_init
  avec les nouvelles formules ancrées sur MAX(#Solde avec Equiv renseigné)
- Avoirs (comptes avec devise, hors biens matériels statiques) :
  AVRdate_anter et AVRmontant_anter avec formules dynamiques équivalentes

Les biens matériels (val_acq en valeur statique sur H/I) ne sont pas touchés.

Capture les valeurs PVL E/H/I/K AVANT et APRÈS pour visibilité.

Usage:
    python3 tool_migrate_pvl_ancrage.py ~/Compta/comptes.xlsm
    python3 tool_migrate_pvl_ancrage.py ~/Compta/comptes.xlsm --dry-run
"""
import argparse
import sys
from pathlib import Path

from inc_uno import UnoDocument, check_lock_file
from inc_excel_schema import (
    SHEET_PLUS_VALUE, SHEET_AVOIRS, ColResolver, uno_row,
)


NON_PF_SECTIONS = {'métaux', 'crypto', 'devises'}


def _snapshot_pvl(ws, cr, rows):
    """Capture E/H/I/K pour chaque ligne PVL."""
    snap = {}
    for r in rows:
        r0 = uno_row(r)
        snap[r] = {
            'E': ws.getCellByPosition(cr.col('PVLpvl'), r0).getValue(),
            'G': ws.getCellByPosition(cr.col('PVLdate_init'), r0).getValue(),
            'H': ws.getCellByPosition(cr.col('PVLmontant_init'), r0).getValue(),
            'I': ws.getCellByPosition(cr.col('PVLsigma'), r0).getValue(),
            'K': ws.getCellByPosition(cr.col('PVLmontant'), r0).getValue(),
        }
    return snap


def _find_pvl_rows(ws, cr):
    """Localise les lignes PVL sections non-portefeuille (avec devise).

    Skip si la valeur calculée de PVLmontant_init est ≠ 0 — présume que
    l'utilisateur (ou un outil antérieur) a déjà renseigné/calculé un ancrage
    qu'il ne faut pas écraser (saisie manuelle, formule custom, bien matériel
    valorisé directement dans PVL).
    """
    rows = []
    skipped = []
    for r in range(1, 300):
        r0 = uno_row(r)
        section = ws.getCellByPosition(cr.col('PVLsection'), r0).getString().strip()
        devise = ws.getCellByPosition(cr.col('PVLdevise'), r0).getString().strip()
        compte = ws.getCellByPosition(cr.col('PVLcompte'), r0).getString().strip()
        if section not in NON_PF_SECTIONS or not devise or not compte:
            continue
        # Garde : toute valeur Montant_init ≠ 0 est préservée (formule ou statique)
        val_h = ws.getCellByPosition(cr.col('PVLmontant_init'), r0).getValue()
        if abs(val_h) > 1e-9:
            skipped.append((r, compte, val_h))
            continue
        rows.append(r)
    return rows, skipped


def _rewrite_pvl_line(ws, cr, r):
    """Réécrit PVLdate_init, PVLmontant_init, PVLsigma pour une ligne."""
    r0 = uno_row(r)
    cB = cr.letter('PVLcompte')
    cD = cr.letter('PVLdevise')
    cG = cr.letter('PVLdate_init')
    # Ancrage = MAX(date #Solde avec Equiv renseigné)
    ws.getCellByPosition(cr.col('PVLdate_init'), r0).setFormula(
        f'=MAXIFS(OPdate;OPcompte;{cB}{r};OPdevise;{cD}{r};'
        f'OPcatégorie;Solde;OPequiv_euro;"<>")')
    # Montant_init = Equiv EUR à la date d'ancrage
    ws.getCellByPosition(cr.col('PVLmontant_init'), r0).setFormula(
        f'=SUMIFS(OPequiv_euro;OPcompte;{cB}{r};OPdevise;{cD}{r};'
        f'OPcatégorie;Solde;OPdate;{cG}{r})')
    # SIGMA : ops post ancrage, exclut tout #* (via Spéciale wildcard)
    ws.getCellByPosition(cr.col('PVLsigma'), r0).setFormula(
        f'=SUMIFS(OPequiv_euro;OPcompte;{cB}{r};OPdevise;{cD}{r};'
        f'OPcatégorie;"<>"&Spéciale;OPdate;">="&{cG}{r})')


def _find_avr_rows(ws, cr):
    """Localise les lignes Avoirs avec devise (hors biens matériels statiques).

    Skip si H ou I contient une valeur (pas une formule) — convention biens matériels.
    """
    rows = []
    avr_s, avr_e = cr.rows('AVRintitulé')
    if not avr_s:
        return rows
    for r in range(avr_s, (avr_e or avr_s + 30) + 1):
        r0 = uno_row(r)
        intitule = ws.getCellByPosition(cr.col('AVRintitulé'), r0).getString().strip()
        if not intitule or intitule in ('Total', 'Compte clos', '✓'):
            continue
        devise = ws.getCellByPosition(cr.col('AVRdevise'), r0).getString().strip()
        type_ = ws.getCellByPosition(cr.col('AVRtype'), r0).getString().strip()
        if not devise or type_ == 'Biens matériels':
            continue
        # Skip si H ou I contient une valeur statique (formule commence par =, sinon valeur)
        fh = ws.getCellByPosition(cr.col('AVRdate_anter'), r0).getFormula()
        fi = ws.getCellByPosition(cr.col('AVRmontant_anter'), r0).getFormula()
        static_h = fh and not fh.startswith('=')
        static_i = fi and not fi.startswith('=')
        if static_h or static_i:
            # antériorité saisie statiquement (rare hors biens matériels) — on respecte
            continue
        rows.append((r, intitule, devise))
    return rows


def _rewrite_avr_line(ws, cr, r):
    """Réécrit AVRdate_anter et AVRmontant_anter pour une ligne compte devise."""
    r0 = uno_row(r)
    ws.getCellByPosition(cr.col('AVRdate_anter'), r0).setFormula(
        f'=MAXIFS(OPdate;OPcompte;$A{r};OPdevise;$E{r};'
        f'OPcatégorie;Solde;OPequiv_euro;"<>")')
    ws.getCellByPosition(cr.col('AVRmontant_anter'), r0).setFormula(
        f'=SUMIFS(OPmontant;OPcompte;$A{r};OPdevise;$E{r};'
        f'OPcatégorie;Solde;OPdate;$H{r})')


def _format_delta(before, after):
    lines = []
    for row in sorted(before.keys()):
        b, a = before[row], after[row]
        for col in ('E', 'G', 'H', 'I', 'K'):
            if abs(b[col] - a[col]) > 1e-6:
                lines.append(
                    f"    row {row} {col}: {b[col]:.2f} → {a[col]:.2f} "
                    f"(Δ {a[col]-b[col]:+.2f})")
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
        ws_pv = doc.get_sheet(SHEET_PLUS_VALUE)
        ws_av = doc.get_sheet(SHEET_AVOIRS)

        pv_rows, pv_skipped = _find_pvl_rows(ws_pv, cr)
        av_rows = _find_avr_rows(ws_av, cr)

        if pv_skipped:
            print(f"Plus_value : {len(pv_skipped)} ligne(s) skippées "
                  "(Montant_init saisi manuellement, à préserver)")
            for r, name, v in pv_skipped:
                print(f"  row {r}: {name} → H={v:.2f} conservé")
            print()

        print(f"Plus_value : {len(pv_rows)} ligne(s) sections non-portefeuille")
        for r in pv_rows:
            compte = ws_pv.getCellByPosition(
                cr.col('PVLcompte'), uno_row(r)).getString().strip()
            devise = ws_pv.getCellByPosition(
                cr.col('PVLdevise'), uno_row(r)).getString().strip()
            print(f"  row {r}: {compte} ({devise})")

        print(f"\nAvoirs : {len(av_rows)} ligne(s) avec devise (hors biens matériels)")
        for r, name, dev in av_rows:
            print(f"  row {r}: {name} ({dev})")

        if not pv_rows and not av_rows:
            print("\nAucune ligne à migrer.")
            return 0

        # Snapshot AVANT
        doc.calculate_all()
        before = _snapshot_pvl(ws_pv, cr, pv_rows)

        # Réécrire Plus_value
        for r in pv_rows:
            _rewrite_pvl_line(ws_pv, cr, r)
        if pv_rows:
            print(f"\n✓ Plus_value : {len(pv_rows)} ligne(s) réécrites (G, H, I)")

        # Réécrire Avoirs
        for r, _, _ in av_rows:
            _rewrite_avr_line(ws_av, cr, r)
        if av_rows:
            print(f"✓ Avoirs : {len(av_rows)} ligne(s) réécrites (H, I)")

        # Snapshot APRÈS
        doc.calculate_all()
        after = _snapshot_pvl(ws_pv, cr, pv_rows)

        deltas = _format_delta(before, after)
        if deltas:
            print("\n⚠️  Écarts PVL détectés (bug latent corrigé — lire Compta_upgrade.md) :")
            for line in deltas:
                print(line)
        else:
            print("\n✓ Valeurs PVL identiques avant/après")

        if dry_run:
            print("\n[dry-run] pas de sauvegarde")
            return 0

        doc.save()
        print(f"\n✓ Sauvé : {p}")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('xlsm', help='Chemin du classeur comptes.xlsm')
    ap.add_argument('--dry-run', action='store_true',
                    help="N'enregistre pas, affiche les écarts")
    args = ap.parse_args()
    return migrate(args.xlsm, dry_run=args.dry_run)


if __name__ == '__main__':
    sys.exit(main())
