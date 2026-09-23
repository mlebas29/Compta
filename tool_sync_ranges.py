#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tool_sync_ranges.py — Resynchronise les plages nommées d'un classeur sur ses ancres.

Les plages nommées dérivent. `tool_purge` déplace des lignes par openpyxl
(`delete_rows`/`insert_rows`) sans déplacer les plages ; un import ajoute
hors plage ; une migration interrompue en laisse manquer. Le classeur continue
de s'ouvrir, mais des formules tombent en `#NOM?` et des totaux se calculent sur
une plage trop courte — silencieusement.

Cet outil recalcule les plages à partir de ce que le classeur porte lui-même :
les MARQUEURS de tête et de pied de chaque tableau (`⚓`, ou `✓` dans les
classeurs d'avant la convention). Un témoin — par défaut `comptes_exemple.xlsx`,
qui intègre toutes les évolutions — ne fournit QUE la géométrie : quelle plage
occupe quelle colonne, relativement à l'ancre de son tableau.

On ne recopie donc jamais une coordonnée. Un classeur de 122 lignes de
plus-values reçoit des plages de 122 lignes ; le témoin en a 52, ça ne change
rien.

Appariement d'un tableau du témoin à un couple de marqueurs de la cible, dans
cet ordre — une feuille peut porter deux tableaux (Budget : POSTES et CAT) :

  1. la plage d'ancrage existe déjà dans la cible → sa colonne fait foi ;
  2. sinon, un couple de marqueurs est à la même colonne que dans le témoin
     (POSTES en A, CTRL1 en A) ;
  3. sinon, le contenu sous le marqueur de tête correspond (CAT se reconnaît à
     `@Change`, `@Achat métaux` — les catégories structurelles que `tool_refs.py`
     code en dur) ;
  4. sinon, non apparié : signalé, jamais deviné.

Les tableaux OUVERTS (quatrième champ de `ANCHOR_TABLES`, `Opérations`) n'ont pas
de marqueur de pied : leur borne basse est conservée telle quelle.

Ne POSE PAS de marqueur manquant : un tableau sans marqueurs n'a rien à quoi
s'accrocher et relève d'une migration datée, pas d'une resynchronisation.

⚠ Écrit par openpyxl, qui ne recalcule pas : les valeurs en cache des formules
sont perdues. LibreOffice les rétablit à l'ouverture.

Usage :
  tool_sync_ranges.py comptes.xlsm                  # rapport seul (défaut)
  tool_sync_ranges.py comptes.xlsm --apply          # pose les plages
  tool_sync_ranges.py comptes.xlsm --temoin X.xlsx  # autre témoin

Codes de sortie : 0 rien à faire · 1 écarts détectés (ou posés) · 2 erreur
"""

import argparse
import re
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent
TEMOIN = RACINE / 'comptes_exemple.xlsx'
MARQUEURS = {'⚓', '✓'}          # ✓ : convention d'avant `⚓`
PLAGE_RE = re.compile(r"^'?([^'!]+)'?!\$([A-Z]{1,3})\$(\d+)(?::\$([A-Z]{1,3})\$(\d+))?$")
PROFONDEUR_CONTENU = 3           # lignes comparées pour l'appariement par contenu


def decoupe(valeur):
    """'Budget!$E$19:$E$35' → ('Budget','E',19,'E',35). None si non reconnu."""
    m = PLAGE_RE.match(str(valeur).strip())
    if not m:
        return None
    f, c1, r1, c2, r2 = m.groups()
    return f, c1, int(r1), c2 or c1, int(r2 or r1)


def col_idx(lettre):
    n = 0
    for ch in lettre:
        n = n * 26 + (ord(ch) - 64)
    return n


def col_lettre(n):
    s = ''
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def plages(wb):
    return {n: str(wb.defined_names[n].value) for n in wb.defined_names}


def geometrie_temoin(wb, tables):
    """Pour chaque tableau : colonne de l'ancre, bornes, et décalage de colonne
    de chaque plage sœur (même feuille, mêmes lignes)."""
    p = plages(wb)
    modele = {}
    for feuille, ancre, _, ouvert in tables:
        cible = next((v for n, v in p.items() if n.lower() == ancre.lower()), None)
        d = decoupe(cible) if cible else None
        if not d:
            continue
        _, c1, r1, _, r2 = d
        soeurs = {}
        for nom, val in p.items():
            dd = decoupe(val)
            if not dd or dd[0] != feuille or nom.lower() == ancre.lower():
                continue
            if (dd[2], dd[4]) != (r1, r2):
                continue                      # pas la même table (ou mono-cellule)
            soeurs[nom] = col_idx(dd[1]) - col_idx(c1)
        modele[ancre] = {'feuille': feuille, 'col': col_idx(c1), 'ouvert': bool(ouvert),
                         'lignes': (r1, r2), 'soeurs': soeurs}
    return modele


def couples(ws):
    """Couples (colonne, ligne_haute, ligne_basse) des marqueurs d'une feuille."""
    par_col = {}
    for row in ws.iter_rows():
        for c in row:
            if isinstance(c.value, str) and c.value.strip() in MARQUEURS:
                par_col.setdefault(c.column, []).append(c.row)
    return [(col, min(rs), max(rs)) for col, rs in par_col.items()]


def contenu(ws, col, ligne):
    return [str(ws.cell(ligne + i, col).value).strip()
            for i in range(1, PROFONDEUR_CONTENU + 1)]


def apparie(ancre, mod, wb_cible, p_cible):
    """Retourne (col, r1, r2) dans la cible, ou None."""
    ws = wb_cible[mod['feuille']] if mod['feuille'] in wb_cible.sheetnames else None
    if ws is None:
        return None
    cs = couples(ws)
    # 1. la plage d'ancrage existe déjà
    v = next((v for n, v in p_cible.items() if n.lower() == ancre.lower()), None)
    d = decoupe(v) if v else None
    if d:
        col = col_idx(d[1])
        for c, r1, r2 in cs:
            if c == col:
                return (col, r1, r2)
        return (col, d[2], d[4])              # pas de marqueur : on garde les bornes
    # 2. même colonne que dans le témoin
    for c, r1, r2 in cs:
        if c == mod['col']:
            return (c, r1, r2)
    return None            # étape 3 (contenu) : traitée par l'appelant, qui a les deux classeurs


def schema(wb):
    """Valeur du marqueur SCHEMA_VERSION, ou None."""
    v = next((str(wb.defined_names[n].value) for n in wb.defined_names
              if n.upper() == 'SCHEMA_VERSION'), None)
    if v is None:
        return None
    d = decoupe(v)
    if not d:
        return v.strip().strip('"')      # constante littérale, pas une référence
    try:
        return str(wb[d[0]][f'{d[1]}{d[2]}'].value).strip()
    except Exception:
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[1],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('cible')
    ap.add_argument('--temoin', default=TEMOIN)
    ap.add_argument('--apply', action='store_true',
                    help='POSE les plages absentes — sans risque : rien à perdre')
    ap.add_argument('--force', action='store_true',
                    help='passe outre la différence de schéma — géométrie vérifiée à la main')
    ap.add_argument('--corriger', action='store_true',
                    help='DÉPLACE aussi les plages divergentes — change le calcul, '
                         'à confirmer sur les en-têtes avant de lancer')
    args = ap.parse_args()
    import openpyxl
    from openpyxl.workbook.defined_name import DefinedName
    sys.path.insert(0, str(RACINE))
    from inc_excel_schema import ANCHOR_TABLES

    cible = Path(args.cible)
    wbT = openpyxl.load_workbook(args.temoin, keep_vba=True)
    wbC = openpyxl.load_workbook(cible, keep_vba=True)
    sT, sC = schema(wbT), schema(wbC)
    if sT != sC and not args.force:
        print(f"⚠ schémas différents : témoin {sT}, cible {sC}.")
        print("  La géométrie du témoin ne vaut QUE pour son schéma. Mesuré le 23/09/2026 :")
        print("  entre schéma 2 et 3, la refonte « drill devise » a supprimé des colonnes PAR")
        print("  DEVISE À L'INTÉRIEUR du bloc CAT (Budget M..X). Appliquer les décalages du")
        print("  témoin y pose CATmontant, CATposte… sur des colonnes de cours de change.")
        print("  Vérifier table par table, puis relancer avec --force.")
        return 2
    modele = geometrie_temoin(wbT, ANCHOR_TABLES)
    pC = plages(wbC)

    # appariement par contenu (étape 3) : fait ici, avec accès aux deux classeurs
    for ancre, mod in modele.items():
        mod['cible'] = apparie(ancre, mod, wbC, pC)
        if mod['cible'] or mod['feuille'] not in wbC.sheetnames:
            continue
        attendu = contenu(wbT[mod['feuille']], mod['col'], mod['lignes'][0])
        for c, r1, r2 in couples(wbC[mod['feuille']]):
            if contenu(wbC[mod['feuille']], c, r1) == attendu:
                mod['cible'] = (c, r1, r2)
                break

    poses, identiques, corrigees, orphelins = [], 0, [], []
    for ancre, mod in modele.items():
        if not mod['cible']:
            orphelins.append(f"{ancre} ({mod['feuille']})")
            continue
        col, r1, r2 = mod['cible']
        if mod['ouvert']:
            d = decoupe(next((v for n, v in pC.items() if n.lower() == ancre.lower()), ''))
            r2 = d[4] if d else r2            # table ouverte : borne basse conservée
        for nom, delta in {**{ancre: 0}, **mod['soeurs']}.items():
            lettre = col_lettre(col + delta)
            neuf = f"'{mod['feuille']}'!${lettre}${r1}:${lettre}${r2}" \
                if ' ' in mod['feuille'] else f"{mod['feuille']}!${lettre}${r1}:${lettre}${r2}"
            actuel = next((v for n, v in pC.items() if n.lower() == nom.lower()), None)
            if actuel is None:
                poses.append((nom, neuf))
            elif decoupe(actuel) != decoupe(neuf):
                corrigees.append((nom, str(actuel), neuf))
            else:
                identiques += 1

    print(f"témoin : {Path(args.temoin).name}   cible : {cible.name}")
    print(f"tableaux appariés : {sum(1 for m in modele.values() if m['cible'])}/{len(modele)}")
    if orphelins:
        print(f"  non appariés (aucun marqueur) : {', '.join(orphelins)}")
    print(f"\nplages conformes : {identiques}")
    print(f"plages ABSENTES  : {len(poses)}")
    for n, v in poses:
        print(f"   + {n:24} {v}")
    print(f"plages DIVERGENTES : {len(corrigees)}")
    for n, a, v in corrigees:
        print(f"   ~ {n:24} {a}  →  {v}")

    # Poser une plage ABSENTE ne peut rien casser : aucune formule ne l'utilise
    # aujourd'hui sans tomber en #NOM?. DÉPLACER une plage existante change ce que
    # calculent les formules qui s'en servent — deux risques, deux drapeaux.
    if not (args.apply or args.corriger):
        if poses or corrigees:
            print("\n(rapport seul — --apply pose les absentes, --corriger déplace les divergentes)")
        return 1 if (poses or corrigees) else 0
    n_p = n_c = 0
    if args.apply:
        for nom, val in poses:
            wbC.defined_names.add(DefinedName(nom, attr_text=val))
            n_p += 1
    if args.corriger:
        for nom, _, val in corrigees:
            del wbC.defined_names[nom]
            wbC.defined_names.add(DefinedName(nom, attr_text=val))
            n_c += 1
    elif corrigees:
        print(f"\n⚠ {len(corrigees)} divergence(s) LAISSÉES en l'état (--corriger pour les déplacer)")
    wbC.save(cible)
    print(f"\n{n_p} posée(s), {n_c} déplacée(s) → {cible}")
    return 1


if __name__ == '__main__':
    sys.exit(main())
