#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cpt_controles.py - Diagnostic des erreurs feuille Contrôles

Lit la cellule Contrôles!A1 et diagnostique les erreurs détectées.

Usage:
  ./cpt_controles.py              # Diagnostic standard
  ./cpt_controles.py -v           # Diagnostic détaillé
  ./cpt_controles.py --help       # Aide

Codes de sortie:
  0 : Contrôles OK (A1 = '.')
  1 : Erreur COMPTES détectée
  2 : Erreur CATÉGORIES détectée
  3 : Warning (-, !, #) détecté
  4 : Erreur technique (fichier absent, etc.)
"""

"""
Diagnostic en cas d'erreur COMPTES

Pour chaque compte de la feuille Contrôles (colonne A) il y a erreur si l'un de ces cas existe :

1. Écart non nul (colonne J) entre solde calculé et solde relevé ET colonne K = "Oui"
2. Colonne L != 1 (il doit y avoir UNE SEULE ligne #Solde à la date la plus récente)
"""

import sys
from pathlib import Path
import argparse
from inc_excel_schema import (
    ColResolver,
    SHEET_OPERATIONS, SHEET_AVOIRS, SHEET_CONTROLES, SHEET_BUDGET,
)
from inc_uno import UnoDocument, get_named_range_pos


def read_a1_status(sheet):
    """Lit la valeur de Contrôles!A1"""
    cell_a1 = sheet.getCellByPosition(0, 0)
    return cell_a1.String


# Décodage de la synthèse Contrôles N76 (6 positions)
# Formule : N63 & N64 & N65 & N66 & N67 & N75 (6 symboles ✓/✗/⚠)
_CTRL_LABELS = [
    'Comptes (soldes)',
    'Catégories',
    'Dates',
    'Appariements',
    'Balances',
    'Inconnus (comptes)',
]
_CTRL_EXPLANATIONS = [
    'Écarts entre soldes calculés et soldes relevés',
    'Opération(s) sans catégorie connue',
    'Date hors période attendue',
    'Appariements incomplets',
    'Déséquilibre balances',
    'Compte(s) absent(s) de la feuille Avoirs',
]


def parse_ctrl(ctrl):
    """Parse la synthèse N76 en liste de 6 tokens.

    Nouveau format (v2.7) : 6 symboles collés ✓/✗/⚠
    Ex: "✓✓✓⚠⚠✓" → ['✓', '✓', '✓', '⚠', '⚠', '✓']

    Ancien format (rétrocompat) : ". . .-!." avec espaces et mots-clés
    """
    # Nouveau format : 6 symboles unicode
    if ctrl and ctrl[0] in ('✓', '✗', '⚠'):
        return list(ctrl[:6])

    # Ancien format : "N63 N64 N65N66N67N75" avec espaces
    parts = ctrl.split(' ', 2)
    tokens = parts[:2]
    if len(parts) == 3:
        tail = parts[2]
        suffix = ''
        if tail.endswith('INCONNUS'):
            suffix = 'INCONNUS'
            tail = tail[:-len('INCONNUS')]
        tokens.extend(list(tail))
        if suffix:
            tokens.append(suffix)
    return tokens


def print_ctrl_summary(tokens):
    """Affiche le décodage des 6 positions de la synthèse Contrôles."""
    print("\n📊 Synthèse Contrôles (6 positions) :")
    for i, label in enumerate(_CTRL_LABELS):
        token = tokens[i] if i < len(tokens) else '✓'
        if token in ('.', '✓'):
            status = '✅'
            detail = 'OK'
        elif token in ('✗', 'COMPTES', 'CATÉGORIES', 'INCONNUS'):
            status = '❌'
            detail = _CTRL_EXPLANATIONS[i]
        else:
            status = '⚠️ '
            detail = _CTRL_EXPLANATIONS[i]
        print(f"  {status} {label:<22} {detail}")


def get_rows_with_discrepancies(sheet, cr, verbose=False):
    """
    Récupère les lignes avec écarts selon les règles CTRL1 (refonte 0..N #Solde).

    Retourne : {'comptes': [...]} — lignes avec écart != 0 ET Ctrl écart = "Oui"
    """
    comptes_errors = []

    for row_idx in range(2, 60):  # Lignes 3 à 60
        compte = sheet.getCellByPosition(cr.col('CTRL1compte'), row_idx).String
        if compte and compte.strip() == '✓':
            continue
        devise = sheet.getCellByPosition(cr.col('CTRL1devise'), row_idx).String
        solde_calc = sheet.getCellByPosition(cr.col('CTRL1solde_calc'), row_idx).Value
        solde_releve = sheet.getCellByPosition(cr.col('CTRL1montant_releve'), row_idx).Value
        ecart = sheet.getCellByPosition(cr.col('CTRL1ecart'), row_idx).Value
        ctrl_ecart = sheet.getCellByPosition(cr.col('CTRL1controle'), row_idx).String

        if not compte:
            continue

        if abs(ecart) > 0.01 and ctrl_ecart == "Oui":
            comptes_errors.append({
                'row': row_idx + 1,
                'compte': compte,
                'devise': devise,
                'solde_calc': solde_calc,
                'solde_releve': solde_releve,
                'ecart': ecart,
            })

    return {'comptes': comptes_errors}


def print_comptes_errors(errors, verbose=False):
    """Affiche les erreurs COMPTES"""
    if not errors:
        return

    print("\n❌ ERREURS COMPTES (écarts non justifiés)")
    print("=" * 105)
    print(f"{'Ligne':<6} {'Compte':<35} {'Solde calc.':<15} {'Solde relevé':<15} {'Écart':<15}")
    print("-" * 105)

    for err in errors:
        devise = err['devise'] if err['devise'] else ''
        solde_calc_str = f"{err['solde_calc']:.2f} {devise}" if err['solde_calc'] is not None else "N/A"
        solde_releve_str = f"{err['solde_releve']:.2f} {devise}" if err['solde_releve'] is not None else "N/A"
        ecart_str = f"{err['ecart']:.2f} {devise}"

        print(f"{err['row']:<6} {err['compte']:<35} {solde_calc_str:<15} {solde_releve_str:<15} {ecart_str:<15}")

    print(f"\n💡 Piste de résolution:")
    print(f"  1. Vérifier qu'au moins un #Solde existe pour ce compte (sinon le contrôle est inactif)")
    print(f"  2. Vérifier les opérations manquantes dans la feuille Opérations")
    print(f"  3. Comparer avec les relevés bancaires")


def get_unknown_accounts(operations_sheet, avoirs_sheet, cr, verbose=False):
    """
    Cherche les comptes dans Opérations qui n'existent pas dans Avoirs

    Returns:
        list: liste des comptes inconnus avec leurs occurrences
    """
    # Récupérer les comptes de référence depuis Avoirs (colonne A)
    valid_accounts = set()
    for row_idx in range(3, 100):  # Lignes 4 à 100
        compte = avoirs_sheet.getCellByPosition(cr.col('AVRintitulé'), row_idx).String
        if compte and compte.strip() and compte not in ('Total', '✓'):
            valid_accounts.add(compte.strip())

    if verbose:
        print(f"  📋 Comptes Avoirs : {len(valid_accounts)} comptes de référence")

    # Chercher les comptes inconnus dans Opérations
    unknown_accounts = {}  # {compte: [liste de lignes]}
    empty_rows_count = 0

    for row_idx in range(3, 10000):  # Commencer à la ligne 4
        compte = operations_sheet.getCellByPosition(cr.col('OPcompte'), row_idx).String

        if not compte:
            empty_rows_count += 1
            if empty_rows_count > 50:
                break
            continue

        empty_rows_count = 0
        compte = compte.strip()

        if compte and compte not in valid_accounts:
            if compte not in unknown_accounts:
                unknown_accounts[compte] = []
            if len(unknown_accounts[compte]) < 3:  # Garder max 3 exemples par compte
                date = operations_sheet.getCellByPosition(cr.col('OPdate'), row_idx).String
                libelle = operations_sheet.getCellByPosition(cr.col('OPlibellé'), row_idx).String
                unknown_accounts[compte].append({
                    'row': row_idx + 1,
                    'date': date,
                    'libelle': libelle[:40] if libelle else ''
                })

    return unknown_accounts


def print_unknown_accounts_errors(unknown_accounts, verbose=False):
    """Affiche les erreurs COMPTES INCONNUS"""
    if not unknown_accounts:
        return

    total_occurrences = sum(len(v) for v in unknown_accounts.values())

    print(f"\n❌ COMPTES INCONNUS ({len(unknown_accounts)} comptes, non listés dans Avoirs)")
    print("=" * 100)

    for compte, examples in sorted(unknown_accounts.items()):
        print(f"\n  📌 '{compte}'")
        for ex in examples:
            print(f"      Ligne {ex['row']}: {ex['date']} - {ex['libelle']}")

    print(f"\n💡 Piste de résolution:")
    print(f"  1. Ajouter ces comptes dans la feuille Avoirs (colonne A) avec leur type (colonne B)")
    print(f"  2. Ou corriger l'orthographe dans Opérations si c'est une erreur de saisie")
    print(f"  3. Vérifier la casse (majuscules/minuscules) - la comparaison est sensible à la casse")


def get_valid_categories(budget_sheet, cr, verbose=False):
    """
    Lit les catégories valides depuis feuille Budget.

    La colonne catégories est résolue via le named range CATnom.
    Plage délimitée par marqueurs textuels START / Total.

    Returns:
        set: ensemble des catégories valides (y compris '-')
    """
    cat_col_0 = cr.col('CATnom')
    # Trouver la ligne START via le contenu (première ligne du range)
    from inc_uno import get_col_range_bounds
    # On n'a pas xdoc ici, mais cr a déjà résolu les colonnes
    # Scan depuis le début de la zone Budget
    start_from = 0
    # Chercher le marqueur '✓' ou 'START' à partir de row 0
    for probe in range(0, 100):
        v = budget_sheet.getCellByPosition(cat_col_0, probe).String.strip()
        if v == '✓':
            start_from = probe
            break

    categories = set()
    collecting = start_from > 0
    first_row = start_from + 1 if collecting else None
    last_row = None

    scan_start = (start_from + 1) if collecting else 0
    for row_idx in range(scan_start, scan_start + 200):
        cell_value = budget_sheet.getCellByPosition(cat_col_0, row_idx).String

        if not cell_value:
            continue

        cell_value = cell_value.strip()

        # Détecter le marqueur de début (fallback si pas de START trouvé)
        if not collecting and 'START' in cell_value.upper():
            collecting = True
            first_row = row_idx + 1
            continue

        # Détecter le marqueur de fin
        if collecting and 'TOTAL' in cell_value.upper():
            last_row = row_idx - 1
            break

        # Collecter les catégories entre START et TOTAL
        if collecting and cell_value:
            categories.add(cell_value)

    if verbose and first_row is not None and last_row is not None:
        col_l = cr.letter('CATnom')
        print(f"  📋 Catégories Budget : {col_l}{first_row+1}:{col_l}{last_row+1} ({len(categories)} catégories)")

    return categories


def get_categories_errors(operations_sheet, valid_categories, cr, verbose=False):
    """
    Cherche les opérations avec catégories manquantes ou invalides

    Critères d'opération valide (non meta-opération) :
    - Date non vide (colonne A)
    - Montant non nul (colonne C)
    - Devise non vide (colonne D)
    - Catégorie != #Solde, #Balance, etc.

    Returns:
        dict: {'missing': [...], 'invalid': [...]}
    """
    missing_category = []
    invalid_category = []

    # Chercher dans toutes les lignes avec données (max 10000 lignes raisonnable)
    # Note: Rows.Count retourne le nb total de lignes de la feuille (~1M), pas le nb de lignes avec données
    empty_rows_count = 0
    for row_idx in range(1, 10000):
        # Ignorer la ligne 3 (row_idx == 2) qui est le header du tableau Opérations
        if row_idx == 2:
            continue

        date = operations_sheet.getCellByPosition(cr.col('OPdate'), row_idx).String
        libelle = operations_sheet.getCellByPosition(cr.col('OPlibellé'), row_idx).String
        montant = operations_sheet.getCellByPosition(cr.col('OPmontant'), row_idx).Value
        devise = operations_sheet.getCellByPosition(cr.col('OPdevise'), row_idx).String
        categorie = operations_sheet.getCellByPosition(cr.col('OPcatégorie'), row_idx).String
        compte = operations_sheet.getCellByPosition(cr.col('OPcompte'), row_idx).String

        # Ignorer les lignes vides ou incomplètes
        if not date or not devise or not compte:
            empty_rows_count += 1
            # Arrêter après 50 lignes vides consécutives (fin des données)
            if empty_rows_count > 50:
                break
            continue

        # Réinitialiser le compteur de lignes vides
        empty_rows_count = 0

        # Ignorer les meta-opérations (#Solde, #Balance, etc.)
        if categorie and categorie.startswith('#'):
            continue

        # Vérifier catégorie manquante
        if not categorie or not categorie.strip():
            missing_category.append({
                'row': row_idx + 1,
                'date': date,
                'libelle': libelle[:50] if libelle else '',
                'montant': montant,
                'devise': devise,
                'compte': compte
            })
        # Vérifier catégorie invalide (pas dans Budget L29:L116)
        elif categorie not in valid_categories:
            invalid_category.append({
                'row': row_idx + 1,
                'date': date,
                'libelle': libelle[:50] if libelle else '',
                'montant': montant,
                'devise': devise,
                'categorie': categorie,
                'compte': compte
            })

    return {
        'missing': missing_category,
        'invalid': invalid_category
    }


def print_categories_errors(errors, verbose=False):
    """Affiche les erreurs CATÉGORIES"""
    missing = errors['missing']
    invalid = errors['invalid']

    if not missing and not invalid:
        print("\n✅ Aucune erreur de catégorie détectée")
        return

    if missing:
        print("\n❌ CATÉGORIES MANQUANTES (colonne G vide)")
        print("=" * 140)
        print(f"{'Ligne':<7} {'Date':<12} {'Libellé':<52} {'Montant':<12} {'Compte':<40}")
        print("-" * 140)

        for err in missing[:20]:  # Limiter à 20 lignes
            montant_str = f"{err['montant']:.2f} {err['devise']}"
            print(f"{err['row']:<7} {err['date']:<12} {err['libelle']:<52} {montant_str:<12} {err['compte']:<40}")

        if len(missing) > 20:
            print(f"\n... et {len(missing) - 20} autres opérations sans catégorie")

        print(f"\n💡 Piste de résolution:")
        print(f"  1. Ajouter les patterns manquants dans inc_category_mappings.py")
        print(f"  2. Ou mettre '-' pour les catégories non reconnues (à catégoriser manuellement)")
        print(f"  3. Vérifier que les format scripts utilisent bien inc_categorize.categorize_operation()")

    if invalid:
        print("\n⚠️  CATÉGORIES INVALIDES (pas dans Budget L29:L116)")
        print("=" * 150)
        print(f"{'Ligne':<7} {'Date':<12} {'Libellé':<52} {'Catégorie':<30} {'Compte':<40}")
        print("-" * 150)

        for err in invalid[:20]:  # Limiter à 20 lignes
            print(f"{err['row']:<7} {err['date']:<12} {err['libelle']:<52} {err['categorie']:<30} {err['compte']:<40}")

        if len(invalid) > 20:
            print(f"\n... et {len(invalid) - 20} autres opérations avec catégorie invalide")

        print(f"\n💡 Piste de résolution:")
        print(f"  1. Ajouter la catégorie manquante dans Budget L29:L116")
        print(f"  2. Ou corriger la catégorie dans inc_category_mappings.py (typo, ancienne catégorie)")
        print(f"  3. Vérifier l'orthographe (majuscules, accents, espaces)")


def main():
    parser = argparse.ArgumentParser(
        description='Diagnostic des erreurs feuille Contrôles',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples:
  ./tool_controles.py                       # Diagnostic standard (comptes.xlsm)
  ./tool_controles.py -f autre.xlsx         # Diagnostic d'un autre fichier
  ./tool_controles.py -v                    # Diagnostic détaillé

Codes de sortie:
  0 : Contrôles OK (A1 = '.')
  1 : Erreur COMPTES détectée
  2 : Erreur CATÉGORIES détectée
  3 : Warning (-, !, #) détecté
  4 : Erreur technique
        """
    )
    parser.add_argument('-f', '--file', dest='excel_file',
                        default='comptes.xlsm',
                        help='Fichier Excel à analyser (défaut: comptes.xlsm)')
    parser.add_argument('-v', '--verbose', action='store_true', help='Mode verbeux')
    args = parser.parse_args()

    # Vérifier que le fichier Excel existe
    excel_file = Path(args.excel_file)
    if not excel_file.exists():
        print(f"❌ Erreur: {excel_file} introuvable")
        return 4

    print(f"🔍 Diagnostic feuille Contrôles ({excel_file.name})...")

    exit_code = 0

    try:
        with UnoDocument(excel_file.absolute(), read_only=True) as doc:
            cr = ColResolver.from_uno(doc.document)
            controles_sheet = doc.get_sheet(SHEET_CONTROLES)
            budget_sheet = doc.get_sheet(SHEET_BUDGET)
            operations_sheet = doc.get_sheet(SHEET_OPERATIONS)
            avoirs_sheet = doc.get_sheet(SHEET_AVOIRS)

            # Lire A1
            a1_value = read_a1_status(controles_sheet)
            print(f"\nContrôles!A1 = '{a1_value}'")

            # Analyser le statut
            if a1_value == '.':
                print("\n✅ CONTRÔLES OK - Aucune erreur détectée")
                exit_code = 0
            else:
                # Décodage des 6 positions (formule N76)
                tokens = parse_ctrl(a1_value)
                print_ctrl_summary(tokens)

                # Analyser les positions pour identifier les types d'erreurs
                # Position 0=Comptes, 1=Catégories, 2=Dates, 3=Appariements, 4=Balances, 5=Inconnus
                has_comptes = len(tokens) > 0 and tokens[0] in ('✗', 'COMPTES')
                has_categories = len(tokens) > 1 and tokens[1] in ('✗', 'CATÉGORIES')
                has_comptes_inconnus = len(tokens) > 5 and tokens[5] in ('✗', 'INCONNUS')
                has_warnings = any(t in ('-', '!', '⚠') for t in tokens)

                if has_comptes:
                    errors = get_rows_with_discrepancies(controles_sheet, cr, args.verbose)
                    print_comptes_errors(errors['comptes'], args.verbose)
                    exit_code = 1

                if has_comptes_inconnus:
                    unknown_accounts = get_unknown_accounts(operations_sheet, avoirs_sheet, cr, args.verbose)
                    print_unknown_accounts_errors(unknown_accounts, args.verbose)
                    if exit_code == 0:
                        exit_code = 1

                if has_categories:
                    valid_categories = get_valid_categories(budget_sheet, cr)
                    categories_errors = get_categories_errors(operations_sheet, valid_categories, cr, args.verbose)
                    print_categories_errors(categories_errors, args.verbose)
                    exit_code = 2

                if has_warnings and not has_comptes and not has_categories and not has_comptes_inconnus:
                    exit_code = 3

    except Exception as e:
        print(f"\n❌ Erreur technique: {e}")
        exit_code = 4

    return exit_code


if __name__ == '__main__':
    sys.exit(main())
