#!/usr/bin/env python3-uno
"""
tnr_light_reverse.py — TNR light reverse (light_build → template mono-devise)

Usage:
  python3 tests/tnr_light_reverse.py

Teardown minimal : supprime le compte, le poste, la catégorie ajoutés par
tnr_light_build. Pas de devises à supprimer (mono-EUR). Compare vs template.
"""

import argparse
import shutil
import sys
import time
from pathlib import Path

_name = Path(__file__).stem.removeprefix('tnr_')
SCENARIO_DIR = Path(__file__).parent / 'tnr' / _name
RESULT = SCENARIO_DIR / 'result.xlsm'
SOURCE = Path(__file__).parent / 'tnr' / 'light_build' / 'expected.xlsm'

sys.path.insert(0, str(Path(__file__).parent))
import tnr_lib
from tnr_lib import (
    find_code_root, timestamp, check_libreoffice_running,
    save_result, compare_result, check_integrity_fast,
    setup_sandbox,
)

CODE_ROOT = find_code_root(__file__)
sys.path.insert(0, str(CODE_ROOT))
from tool_gui_cli import HeadlessGUI
from gui_daemon import DaemonGUI

# Référence = template (pas d'expected local) : le TNR reste rouge tant que
# le code GUI écrase les named ranges par des refs magiques. Vire vert dès que
# _add_poste / _add_category / _save_devise deviennent idempotents.
EXPECTED = CODE_ROOT / 'comptes_template.xlsm'

SOURCE_ACCOUNTS = ['Livret A Barnabé']
SOURCE_CATEGORIES = ['Frais bancaires']
SOURCE_POSTES = ['Banque']


def teardown(gui):
    """Purge+supprime le compte, la cat, le poste. Les delete_* renvoient
    False silencieusement si l'item est absent — pas de pré-check sur les
    attributs d'instance (non disponibles via DaemonGUI)."""
    print(f"   {len(SOURCE_ACCOUNTS)} compte(s) à purger+supprimer")
    for name in SOURCE_ACCOUNTS:
        gui.purge_account(intitule=name)
        gui.delete_account(intitule=name)

    # Tentative "Compte clos" : peut être présent (paires orphelines balayées
    # à la purge) ou non, delete_account gère les deux.
    gui.delete_account(intitule='Compte clos')

    print(f"   Suppression {len(SOURCE_CATEGORIES)} catégorie(s)...")
    for name in SOURCE_CATEGORIES:
        gui.delete_category(name=name)

    print(f"   Suppression {len(SOURCE_POSTES)} poste(s)...")
    for name in SOURCE_POSTES:
        gui.delete_poste(name=name)

    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--daemon', action='store_true',
                        help='Router via daemon JSON RPC (DaemonGUI)')
    args = parser.parse_args()
    gui_cls = DaemonGUI if args.daemon else HeadlessGUI
    backend = 'DaemonGUI (JSON RPC)' if args.daemon else 'HeadlessGUI (in-process)'

    t0 = time.time()
    print(f"  backend : {backend}")

    if not check_libreoffice_running():
        return 1

    if not SOURCE.exists():
        print(f"❌ Source introuvable : {SOURCE}")
        print(f"   Lancer d'abord : python3 tests/tnr_light_build.py")
        return 1

    print(f"\n{timestamp()} Setup sandbox")
    sandbox = setup_sandbox(SCENARIO_DIR)
    tnr_lib.set_base_dir(sandbox)
    COMPTES_XLSX = tnr_lib.COMPTES_XLSX
    print(f"  sandbox : {sandbox}")

    print(f"\n{timestamp()} Copie source → comptes.xlsm")
    shutil.copy2(SOURCE, COMPTES_XLSX)
    print(f"   {SOURCE.name} → comptes.xlsm")

    print(f"\n{timestamp()} Teardown via GUI ({backend})")
    with gui_cls(tnr_lib.COMPTES_XLSX) as gui:
        if not teardown(gui):
            print("❌ Erreur pendant le teardown")
            return 1

    ok = True
    print(f"\n{timestamp()} Vérification intégrité")
    if not check_integrity_fast(COMPTES_XLSX):
        ok = False

    if EXPECTED.exists():
        print(f"\n{timestamp()} Comparaison vs expected")
        cmp_result = compare_result(EXPECTED, tuples=False, brutal=True)
        if cmp_result is False:
            ok = False
    else:
        print(f"\n{timestamp()} ⚠ Pas d'expected — valider puis:")
        print(f"   cp {RESULT} {EXPECTED}")

    print(f"\n{timestamp()} Sauvegarde résultat (hors sandbox)")
    save_result(RESULT)
    # Plus de restore_context : la sandbox isole intrinsèquement le test.

    elapsed = int(time.time() - t0)
    if ok:
        print(f"\n✅ TEST RÉUSSI ({elapsed}s)")
        return 0
    else:
        print(f"\n❌ TEST ÉCHOUÉ ({elapsed}s)")
        return 1


if __name__ == '__main__':
    sys.exit(main())
