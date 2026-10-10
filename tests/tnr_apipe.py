#!/usr/bin/env python3
"""
tnr_apipe.py — TNR pipeline (import des relevés de 11 sites + appariement)

Scénario `apipe` : un jeu complet de forme réelle, anonymisé (libellés, noms,
numéros et montants transformés ; dates et structure conservées).
Entrée   : comptes.xlsm, classeur arrêté avant la période des relevés
Attendu  : expected.xlsm, le même classeur après import et appariement
Relevés  : dropbox/ — AMAZON, BOURSOBANK, BTC, DEGIRO, ETORO, KRAKEN, NATIXIS,
PAYPAL, SOCGEN, WISE, XMR (+ MANUEL/manuel.xlsx, vide)

Le nom du scénario est dérivé du nom du script (tnr_<nom>.py → tnr/<nom>/).

Usage:
  python3 tests/tnr_apipe.py              # standard
  python3 tests/tnr_apipe.py --max        # maximal (--all-soldes)
  python3 tests/tnr_apipe.py --no-tuples  # sans comparaison groupes appariement
"""

import argparse
import shutil
import sys
import time
from pathlib import Path

# Données du scénario (dérivé du nom du script : tnr_apipe.py → tnr/apipe/)
_name = Path(__file__).stem.removeprefix('tnr_')
SCENARIO_DIR = Path(__file__).parent / 'tnr' / _name
INPUT_XLSM = SCENARIO_DIR / 'comptes.xlsm'
EXPECTED = SCENARIO_DIR / 'expected.xlsm'
RESULT = SCENARIO_DIR / 'result.xlsm'
# Note : tous les fichiers sont en .xlsm (depuis avril 2026, refonte)
CATEGORY_MAPPINGS_PY = SCENARIO_DIR / 'inc_category_mappings.py'
CATEGORY_MAPPINGS_JSON = SCENARIO_DIR / 'config_category_mappings.json'
PIPELINE_JSON = SCENARIO_DIR / 'config_pipeline.json'
CONFIG_ACCOUNTS = SCENARIO_DIR / 'config_accounts.json'  # fixture propre au scénario (#111 : auto-suffisance)
CONFIG_INI = SCENARIO_DIR / 'config.ini'  # config complète du scénario
DROPBOX_SRC = SCENARIO_DIR / 'dropbox'

# Import lib
sys.path.insert(0, str(Path(__file__).parent))
import tnr_lib
from tnr_lib import (
    find_code_root, timestamp, check_libreoffice_running,
    setup_input_xlsm, setup_dropbox, run_cpt_update, run_cpt_pair,
    apply_patches, compare_result, save_result,
    setup_sandbox, fige_aujourdhui,
)

CODE_ROOT = find_code_root(__file__)
sys.path.insert(0, str(CODE_ROOT))


def _overlay(src, dest):
    """Dépose `src` sur `dest` dans la sandbox en écrasant un symlink éventuel.

    setup_sandbox symlinke tous les `.py` vers DEV ; un `shutil.copy2` direct sur
    un tel lien SUIT le lien et écrit la source DEV trackée (clobber, #111). On
    retire d'abord le lien/fichier pour que la copie crée un vrai fichier sandbox.
    """
    if dest.is_symlink() or dest.exists():
        dest.unlink()
    shutil.copy2(src, dest)


def main():
    parser = argparse.ArgumentParser(description='TNR pipeline')
    parser.add_argument('--max', action='store_true',
                        help='Mode maximal (--all-soldes)')
    parser.add_argument('--no-tuples', action='store_true',
                        help='Désactiver la comparaison des groupes d\'appariement')
    args = parser.parse_args()

    is_max = args.max
    expected = EXPECTED  # un seul expected pour les 2 modes
    mode_label = 'maximal' if is_max else 'minimal'

    success = True
    t_start = time.time()

    # 0. Vérifier LibreOffice
    if not check_libreoffice_running():
        return 1

    # 1. Setup sandbox + bascule des paths tnr_lib
    print(f"\n{timestamp()} Setup sandbox")
    sandbox = setup_sandbox(SCENARIO_DIR)
    tnr_lib.set_base_dir(sandbox)
    print(f"  sandbox : {sandbox}")

    # 1b. Configs spécifiques au scénario : overlay dans la sandbox.
    #     _overlay écrase un symlink éventuel AVANT de copier — sinon copy2 suit
    #     le lien et écrit la cible DEV (inc_category_mappings.py est symlinké vers
    #     DEV → clobber d'une source trackée, #111).
    for _src, _name in (
        (CATEGORY_MAPPINGS_PY, 'inc_category_mappings.py'),
        (CATEGORY_MAPPINGS_JSON, 'config_category_mappings.json'),
        (PIPELINE_JSON, 'config_pipeline.json'),
        (CONFIG_ACCOUNTS, 'config_accounts.json'),
        (CONFIG_INI, 'config.ini'),
    ):
        if _src.exists():
            _overlay(_src, sandbox / _name)

    # 2. Setup : copier xlsm + dropbox dans la sandbox (via tnr_lib, qui pointe sandbox)
    print(f"\n{timestamp()} Setup test pipeline ({mode_label})")
    if not setup_input_xlsm(INPUT_XLSM):
        success = False
        return 1
    if not setup_dropbox(DROPBOX_SRC):
        success = False
        return 1
    fige_aujourdhui()

    # 3. Exécution : cpt_update + cpt_pair + patches
    # Note : on continue même si cpt_update signale des écarts soldes
    # (non-bloquant pour la suite : pair + patches doivent quand même tourner)
    print(f"\n{timestamp()} Exécution cpt_update ({mode_label})")
    flags = ['--no-pair', '--TNR']
    if is_max:
        flags.append('--all-soldes')
    update_ok = run_cpt_update(flags)
    if not update_ok:
        print("⚠ cpt_update a signalé une erreur — on continue avec pair+patches")

    print(f"\n{timestamp()} Appariement")
    if not run_cpt_pair():
        success = False
    else:
        print(f"\n{timestamp()} Patches")
        apply_patches(DROPBOX_SRC / 'MANUEL')

    # 4. Comparaison
    if success:
        print(f"\n{timestamp()} Comparaison résultat vs expected")
        is_minimal = not is_max
        cmp_result = compare_result(
            expected,
            tuples=not args.no_tuples,
            brutal=is_minimal,
        )
        if cmp_result is False:
            success = False

    # 5. Sauvegarde résultat (hors sandbox pour archivage)
    print(f"\n{timestamp()} Sauvegarde résultat")
    save_result(RESULT)
    # Plus de restore_context : la sandbox isole intrinsèquement le test.

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
