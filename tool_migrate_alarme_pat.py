#!/usr/bin/env python3
"""Migration : ajout cell de cohérence Patrimoine + alarme CTRL2 'Cohérence'.

Pose dans le classeur cible (positions identifiées dynamiquement) :
- Patrimoine!B{r}  = "Erreurs"             où r = dernier TOTAL + 2 (ligne pied)
- Patrimoine!D{r}  = compteur de ventilations en écart > 0.5 EUR (entier 0..5, en gras)
- Contrôles : ligne 'Date' renommée 'Cohérence' (identifiée via NR CTRL2type),
  formule de la colonne 'Général' (CTRL2general) étendue avec +Patrimoine.D{r}.

CF rouge sur D33 (warning si ≠ 0) : à poser à la main dans LibreOffice.

Idempotent : si déjà migré, ne fait rien.

Usage:
    python3 tool_migrate_alarme_pat.py ~/Compta/comptes.xlsm
    python3 tool_migrate_alarme_pat.py ~/Compta/comptes.xlsm --dry-run
"""
import argparse
import sys
from pathlib import Path

from inc_uno import UnoDocument, check_lock_file
from inc_excel_schema import uno_row


# Position cible Patrimoine : pied = PATlabel_end + 1 (juste après ⚓ basse).
# Trouvée dynamiquement via NR (layout-agnostic).
PAT_LABEL_COL_0 = 1   # B
PAT_FORMULA_COL_0 = 3  # D
PAT_LABEL = 'Erreurs'
PAT_TOLERANCE = 0.5  # EUR, seuil d'arrondi pour considérer un écart de ventilation

CTRL2_OLD_LABEL = 'Date'
CTRL2_NEW_LABEL = 'Cohérence'
# Référence Patrimoine.D{target_row} construite dynamiquement (syntaxe UNO : point)

BOLD = 150


def migrate(xlsm_path, dry_run=False):
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
        ws_pat = doc.get_sheet('Patrimoine')
        ws_ctrl = doc.get_sheet('Contrôles')

        changes = []

        # --- Position cible Patrimoine = pied = PATlabel_end + 1 ---
        # Convention layout-agnostic : le NR PATlabel se termine sur la sentinelle ⚓,
        # le pied est la ligne juste après.
        pat_s, pat_e = cr.rows('PATlabel')
        if not pat_e:
            print("❌ NR PATlabel introuvable — abandon.")
            return 1
        pat_row = pat_e + 1
        pat_d_ref = f'Patrimoine.D{pat_row}'  # syntaxe UNO

        # --- Patrimoine B{pat_row} : label "Erreurs" ---
        b_cell = ws_pat.getCellByPosition(PAT_LABEL_COL_0, pat_row - 1)
        if b_cell.getString().strip() != PAT_LABEL:
            if not dry_run:
                b_cell.setString(PAT_LABEL)
            changes.append(f"+ Patrimoine!B{pat_row} = '{PAT_LABEL}'")

        # --- Construire la formule compteur écarts dynamiquement ---
        # Scan col B pour les TOTAL des sections (skip le 1er = TOTAL global qui
        # pointe sur une feuille externe).
        all_total_rows = []
        for r in range(2, 200):
            v = ws_pat.getCellByPosition(PAT_LABEL_COL_0, r - 1).getString().strip()
            if v == 'TOTAL':
                all_total_rows.append(r)
        if len(all_total_rows) < 2:
            print("❌ Moins de 2 lignes 'TOTAL' (global + sections) dans Patrimoine — abandon.")
            return 1
        section_rows = all_total_rows[1:]  # skip le global
        terms = [f'(ABS(D{r}-D4)>{PAT_TOLERANCE})' for r in section_rows]
        pat_formula = '=' + '+'.join(terms)

        # --- Patrimoine D{pat_row} : compteur écarts ventilations + bold ---
        d_cell = ws_pat.getCellByPosition(PAT_FORMULA_COL_0, pat_row - 1)
        cur_d = d_cell.getFormula()
        if cur_d.replace(' ', '') != pat_formula.replace(' ', ''):
            if not dry_run:
                d_cell.setFormula(pat_formula)
            changes.append(
                f"+ Patrimoine!D{pat_row} = compteur écarts (sections {section_rows})")
        if d_cell.CharWeight != BOLD:
            if not dry_run:
                d_cell.CharWeight = BOLD
            changes.append(f"+ Patrimoine!D{pat_row} bold")

        # --- Contrôles : ligne 'Date' / 'Cohérence' via NR CTRL2type ---
        ctrl2_s, ctrl2_e = cr.rows('CTRL2type')
        type_col = cr.col('CTRL2type')
        gen_col = cr.col('CTRL2general')

        target_row = None
        for r in range(ctrl2_s, ctrl2_e + 1):
            val = ws_ctrl.getCellByPosition(type_col, uno_row(r)).getString().strip()
            if val in (CTRL2_OLD_LABEL, CTRL2_NEW_LABEL):
                target_row = r
                break

        if target_row is None:
            print(f"⚠ Ni '{CTRL2_OLD_LABEL}' ni '{CTRL2_NEW_LABEL}' trouvé dans CTRL2type — skip Contrôles")
        else:
            # Renommer si besoin
            j_cell = ws_ctrl.getCellByPosition(type_col, uno_row(target_row))
            if j_cell.getString().strip() != CTRL2_NEW_LABEL:
                old = j_cell.getString().strip()
                if not dry_run:
                    j_cell.setString(CTRL2_NEW_LABEL)
                changes.append(f"+ Contrôles!J{target_row} : '{old}' → '{CTRL2_NEW_LABEL}'")

            # Étendre L{row} : purger d'abord les anciennes refs Patrimoine.D{x}
            # obsolètes (héritage migrations antérieures à mauvaise position),
            # puis ajouter la ref vers la cible courante si absente.
            import re as _re
            l_cell = ws_ctrl.getCellByPosition(gen_col, uno_row(target_row))
            cur_l = l_cell.getFormula()
            uno_ref = pat_d_ref                                 # Patrimoine.D{r}
            xlsx_ref = pat_d_ref.replace('.', '!')              # Patrimoine!D{r}
            new_l = cur_l
            # Purge des refs obsolètes (toute Patrimoine.D{x} ou Patrimoine!D{x}
            # avec x ≠ pat_row)
            obsolete_pat = _re.compile(
                r'\+\$?Patrimoine[.!]D(\d+)')
            def _filter_ref(m):
                return '' if int(m.group(1)) != pat_row else m.group(0)
            cleaned = obsolete_pat.sub(_filter_ref, new_l)
            if cleaned != new_l:
                changes.append(
                    f"~ Contrôles!L{target_row} : purge ref(s) Patrimoine.D obsolète(s)")
                new_l = cleaned
            # Ajout de la ref cible si absente
            if uno_ref not in new_l and xlsx_ref not in new_l:
                if new_l.startswith('='):
                    new_l = new_l + '+' + uno_ref
                else:
                    new_l = '=' + uno_ref
                changes.append(f"+ Contrôles!L{target_row} étendu : ...+{uno_ref}")
            if new_l != cur_l and not dry_run:
                l_cell.setFormula(new_l)

            # Format L{row} = nombre entier (au lieu d'EUR hérité de la col)
            fmt_nb = doc.register_number_format('0')
            if l_cell.NumberFormat != fmt_nb:
                if not dry_run:
                    l_cell.NumberFormat = fmt_nb
                changes.append(f"+ Contrôles!L{target_row} format = nombre entier")

        if not changes:
            print(f"✓ {p.name} : déjà migré, rien à faire.")
            return 0

        print(f"Migration {p.name} :")
        for c in changes:
            print(f"  {c}")

        if dry_run:
            print("\n[dry-run] pas de sauvegarde")
            return 0

        doc.save()
        print(f"\n✓ Sauvé : {p}")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('xlsm', help='Chemin du classeur (témoin / template / comptes.xlsm)')
    ap.add_argument('--dry-run', action='store_true',
                    help="N'enregistre pas, affiche les changements prévus")
    args = ap.parse_args()
    return migrate(args.xlsm, dry_run=args.dry_run)


if __name__ == '__main__':
    sys.exit(main())
