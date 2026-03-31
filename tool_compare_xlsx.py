#!/usr/bin/env python3
"""
tool_compare_xlsx.py - Compare deux fichiers Excel (feuilles Opérations, Plus_value et Avoirs)

Usage:
  ./tool_compare_xlsx.py fichier1.xlsx fichier2.xlsx
  ./tool_compare_xlsx.py --prev                    # Compare comptes.xlsm avec l'archive N-1
  ./tool_compare_xlsx.py --prev 2                  # Compare avec l'archive N-2
  ./tool_compare_xlsx.py --full                    # Affiche toutes les différences
  ./tool_compare_xlsx.py --sheet Opérations        # Filtre sur une feuille
  ./tool_compare_xlsx.py --re "LOYER" -i           # Filtre par regex (case-insensitive)
  ./tool_compare_xlsx.py --since 2025-10-01        # Opérations depuis cette date
  ./tool_compare_xlsx.py --tuples                  # Compare les groupes d'appariement
"""

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

from inc_compare_xlsx import compare_xlsx, find_prev_archive, _read_config_threshold


def main():
    parser = argparse.ArgumentParser(
        description='Compare deux fichiers Excel (feuilles Opérations et Plus_value)'
    )
    parser.add_argument('files', nargs='*',
                        help='Deux fichiers à comparer (result expected)')
    parser.add_argument('-r', '--result',
                        default='tests/expected/comptes_result.xlsx',
                        help='Fichier résultat')
    parser.add_argument('-e', '--expected',
                        default='tests/expected/comptes_expected.xlsx',
                        help='Fichier attendu')
    parser.add_argument('-n', '--max-display', type=int, default=10,
                        help='Nombre max de lignes à afficher par groupe')
    parser.add_argument('-f', '--full', action='store_true',
                        help='Affiche toutes les différences')
    parser.add_argument('-s', '--sheet',
                        help='Filtre sur une feuille (Opérations, Plus_value ou Avoirs)')
    parser.add_argument('--re', dest='regex',
                        help='Filtre les lignes par expression régulière')
    parser.add_argument('-i', dest='ignore_case', action='store_true',
                        help='Regex case-insensitive')
    parser.add_argument('-v', '--invert', dest='invert', action='store_true',
                        help='Inverse le filtre (exclut les lignes matchant)')
    parser.add_argument('-x', '--exclude', dest='exclude_cols',
                        help='Colonnes à exclure (remplace le défaut F,G,J). Ex: F,J ou E,F,G,J')
    parser.add_argument('--approx', dest='approx', nargs='?', const=0.02, type=float,
                        metavar='SEUIL',
                        help='Tolérance relative sur Equiv/col E (défaut: 0.02 = 2%%)')
    parser.add_argument('--tuples', action='store_true',
                        help='Compare les groupes d\'appariement (opérations partageant la même Ref)')
    parser.add_argument('--since', dest='since_date',
                        help='Ne compare que les opérations depuis cette date (YYYY-MM-DD)')
    parser.add_argument('--prev', dest='prev', nargs='?', const=1, type=int, metavar='N',
                        help='Compare comptes.xlsm avec la Nème archive (défaut: 1 = plus récente)')
    parser.add_argument('--brutal', action='store_true',
                        help='Comparaison cellule par cellule (formules + valeurs)')
    parser.add_argument('--threshold', dest='threshold', type=float, metavar='PCT',
                        help='Seuil variation Plus_value en %% (surcharge config.ini)')

    args = parser.parse_args()

    # Parser les colonnes à exclure (-x remplace les défauts de SHEETS_CONFIG)
    override_ignore_cols = None
    if args.exclude_cols:
        override_ignore_cols = set()
        for col in args.exclude_cols.upper().replace(' ', '').split(','):
            if col and col.isalpha() and len(col) == 1:
                override_ignore_cols.add(ord(col) - ord('A') + 1)

    # --full équivaut à --max-display 0
    if args.full:
        args.max_display = 0

    # Compiler la regex si fournie
    regex_pattern = None
    if args.regex:
        flags = re.IGNORECASE if args.ignore_case else 0
        regex_pattern = re.compile(args.regex, flags)

    # Parser la date --since
    since_date = None
    if args.since_date:
        try:
            since_date = datetime.strptime(args.since_date, '%Y-%m-%d')
        except ValueError:
            print(f"❌ Format de date invalide: {args.since_date} (attendu: YYYY-MM-DD)")
            return 1

    # Mode --prev : comparer avec archive
    if args.prev is not None:
        archives_dir = Path(__file__).parent / 'archives'
        archive = find_prev_archive(archives_dir, args.prev)
        if archive is None:
            print(f"❌ Pas d'archive N={args.prev} dans {archives_dir}")
            return 1
        result_path = str(Path(__file__).parent / 'comptes.xlsm')
        expected_path = str(archive)
        threshold = args.threshold / 100.0 if args.threshold is not None else _read_config_threshold()
        compare_xlsx(
            result_path, expected_path,
            max_display=args.max_display,
            sheet_filter=args.sheet,
            prev_mode=True,
            warn_threshold_override=threshold,
            labels=('ACTUEL', 'PRÉCÉDENT')
        )
        return 0

    # Déterminer les fichiers à comparer
    if len(args.files) >= 2:
        result_path = args.files[0]
        expected_path = args.files[1]
    else:
        result_path = args.result
        expected_path = args.expected

    # Comparer
    success = compare_xlsx(
        result_path, expected_path,
        max_display=args.max_display,
        sheet_filter=args.sheet,
        regex_pattern=regex_pattern,
        invert=args.invert,
        override_ignore_cols=override_ignore_cols,
        since_date=since_date,
        approx_tolerance=args.approx,
        compare_tuples_flag=args.tuples,
        brutal=args.brutal
    )

    print()
    if success:
        print("✅ FICHIERS IDENTIQUES")
        return 0
    else:
        print("❌ FICHIERS DIFFÉRENTS")
        return 1


if __name__ == '__main__':
    sys.exit(main())
