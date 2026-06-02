#!/usr/bin/env python3-uno
"""
tnr_roundtrip.py — TNR round-trip (load → save sans modif → compare)

Usage:
  python3 tests/tnr_roundtrip.py

Vérifie que HeadlessGUI load + save sans modification ne corrompt pas le xlsm.
Part du template expected, copie → load → save → check intégrité → compare vs original.
"""

import shutil
import sys
import time
from pathlib import Path

_name = Path(__file__).stem[len('tnr_'):]
SCENARIO_DIR = Path(__file__).parent / 'tnr' / _name

# tests/ d'abord pour importer tnr_lib (qui contient find_code_root)
sys.path.insert(0, str(Path(__file__).parent))
from tnr_lib import find_code_root, timestamp, check_libreoffice_running, check_integrity_fast, compare_named_ranges, setup_sandbox

CODE_ROOT = find_code_root(__file__)
sys.path.insert(0, str(CODE_ROOT))
from tool_gui_cli import HeadlessGUI
from inc_uno import check_env


def main():
    t_start = time.time()
    success = True

    _env_ok, _env_msg = check_env()
    if not _env_ok:
        print(f"⚠️  {_env_msg}")

    if not check_libreoffice_running():
        return 1

    # 0. Sandbox : isole le test (DEV jamais touché). Le template public sert de référence.
    print(f"\n{timestamp()} Setup sandbox")
    sandbox = setup_sandbox(SCENARIO_DIR)
    TEMPLATE = sandbox / 'comptes_template.xlsm'
    RESULT = sandbox / 'result.xlsm'
    print(f"  sandbox : {sandbox}")

    if not TEMPLATE.exists():
        print(f"❌ Template introuvable : {TEMPLATE}")
        return 1

    # 1. Copier template → result
    print(f"\n{timestamp()} Copie template → {RESULT.name}")
    shutil.copy2(TEMPLATE, RESULT)

    # 2. Load + save sans modification (1 appel UNO)
    print(f"\n{timestamp()} Round-trip : load → save")
    gui = HeadlessGUI(RESULT)
    gui._save_and_reload()
    print("  ✓ Save sans modification")

    # 3. Vérification intégrité
    print(f"\n{timestamp()} Vérification intégrité")
    if not check_integrity_fast(RESULT):
        success = False

    # 4. Comparer vs original (template)
    if success:
        print(f"\n{timestamp()} Comparaison vs template")
        from inc_compare_xlsx import compare_xlsx
        if not compare_xlsx(str(RESULT), str(TEMPLATE)):
            success = False
        if compare_named_ranges(TEMPLATE, result_path=RESULT) is False:
            success = False

    elapsed = time.time() - t_start
    print()
    if success:
        print(f"✅ TEST RÉUSSI ({elapsed:.0f}s)")
        return 0
    else:
        print(f"❌ TEST ÉCHOUÉ ({elapsed:.0f}s)")
        return 1


if __name__ == '__main__':
    sys.exit(main())
