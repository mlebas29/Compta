#!/usr/bin/env python3
"""
tool_check_integrity.py - Vérifie l'intégrité des formules dans comptes.xlsm

Usage:
    python3 tool_check_integrity.py <fichier.xlsm>
    python3 tool_check_integrity.py --fix ~/Compta/Claude/comptes.xlsm
"""

import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from inc_uno import UnoDocument, HAS_UNO
from inc_check_integrity import IntegrityChecker

if not HAS_UNO:
    print("Ce script doit être exécuté avec le Python système (accès UNO).")
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Vérifie l'intégrité des formules dans comptes.xlsm")
    parser.add_argument('file', type=Path, help='Fichier comptes.xlsm')
    parser.add_argument('--fix', action='store_true',
                        help='(futur) Tenter de réparer les formules corrompues')
    args = parser.parse_args()

    if not args.file.exists():
        print(f"Fichier introuvable : {args.file}")
        sys.exit(1)

    if args.fix:
        print("Option --fix pas encore implémentée.")
        sys.exit(1)

    filepath = args.file.absolute()
    print(f"Vérification de {filepath.name}...\n")

    with UnoDocument(filepath, read_only=True) as doc:
        doc.calculate_all()
        checker = IntegrityChecker(doc.document)
        checker.run_all()
        ok = checker.report()

    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
