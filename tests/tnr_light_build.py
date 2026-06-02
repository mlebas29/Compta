#!/usr/bin/env python3-uno
"""
tnr_light_build.py — TNR light build (template + 1 compte/1 poste/1 cat EUR uniquement)

Usage:
  python3 tests/tnr_light_build.py
  python3 tests/tnr_light_build.py --keep       # debug (pas de restore)

Scénario minimal mono-devise pour isoler les opérations CRUD Budget/POSTES/CAT
du code multi-devises. Pas de cotations non-EUR, pas de titre, pas d'opération.
"""

import shutil
import sys
import time
from pathlib import Path

_name = Path(__file__).stem.removeprefix('tnr_')
SCENARIO_DIR = Path(__file__).parent / 'tnr' / _name
EXPECTED = SCENARIO_DIR / 'expected.xlsm'
RESULT = SCENARIO_DIR / 'result.xlsm'

sys.path.insert(0, str(Path(__file__).parent))
import tnr_lib
from tnr_lib import (
    find_code_root, timestamp, check_libreoffice_running,
    compare_result, save_result, check_integrity_fast,
    setup_sandbox,
)

CODE_ROOT = find_code_root(__file__)
sys.path.insert(0, str(CODE_ROOT))
from tool_gui_cli import HeadlessGUI

# ============================================================================
# DONNÉES DU SCÉNARIO (mono-devise EUR)
# ============================================================================

LIGHT_ACCOUNTS = [
    # Champs PAT remplis avec '-'/'oui' pour neutraliser l'alarme Patrimoine
    # (commit d628e492). sous_type laissé vide → 'Euro' par défaut pour EUR.
    ('Livret A Barnabé', 'Créances', 'EUR'),
]

LIGHT_POSTES = [
    ('Banque', True),  # Fixe
]

LIGHT_CATEGORIES = [
    ('Frais bancaires', 'Banque'),
]


def setup_build():
    SCRIPT_DIR = tnr_lib.SCRIPT_DIR
    COMPTES_XLSX = tnr_lib.COMPTES_XLSX
    TEMPLATE = SCRIPT_DIR / 'comptes_template.xlsm'

    if not TEMPLATE.exists():
        print(f"❌ Template introuvable : {TEMPLATE}")
        return False

    shutil.copy2(TEMPLATE, COMPTES_XLSX)
    print(f"   {TEMPLATE.name} → comptes.xlsm")

    gui = HeadlessGUI(COMPTES_XLSX)
    errors = 0

    with gui.batch() as doc:
        print(f"🔧 Ajout de {len(LIGHT_ACCOUNTS)} compte(s)...")
        for intitule, acct_type, devise in LIGHT_ACCOUNTS:
            if not gui.add_account(intitule, acct_type, devise=devise,
                                   domiciliation='-', titulaire='-',
                                   propriete='oui',
                                   controle=True, doc=doc):
                errors += 1

        gui._save_accounts(doc=doc)

        if hasattr(doc.cr, 'refresh'):
            doc.cr.refresh(xdoc=doc.document)

        print(f"🔧 Ajout de {len(LIGHT_POSTES)} poste(s)...")
        for name, fixe in LIGHT_POSTES:
            if not gui.add_poste(name, fixe=fixe, doc=doc):
                errors += 1

        print(f"🔧 Ajout de {len(LIGHT_CATEGORIES)} catégorie(s)...")
        for name, poste in LIGHT_CATEGORIES:
            if not gui.add_category(name, poste=poste, doc=doc):
                errors += 1

    if errors:
        print(f"❌ {errors} erreur(s) pendant le build GUI")
        return False
    print("✓ Build GUI terminé")
    return True


def main():
    success = True
    t_start = time.time()

    if not check_libreoffice_running():
        return 1

    print(f"\n{timestamp()} Setup sandbox")
    sandbox = setup_sandbox(SCENARIO_DIR)
    tnr_lib.set_base_dir(sandbox)
    COMPTES_XLSX = tnr_lib.COMPTES_XLSX
    print(f"  sandbox : {sandbox}")

    # Mode Classeur : vider config_pipeline.json dans la sandbox
    import json
    pipeline_json = sandbox / 'config_pipeline.json'
    if pipeline_json.exists():
        with open(pipeline_json, 'w') as f:
            json.dump({"linked_operations": {}, "solde_auto": {}}, f, indent=2)

    print(f"\n{timestamp()} Light build (GUI batch mono-devise)")
    if not setup_build():
        success = False
        return 1

    if success:
        print(f"\n{timestamp()} Vérification intégrité")
        if not check_integrity_fast(COMPTES_XLSX):
            success = False

    if success and EXPECTED.exists():
        print(f"\n{timestamp()} Comparaison vs expected (brutal)")
        cmp_result = compare_result(EXPECTED, tuples=False, brutal=True)
        if cmp_result is False:
            success = False
    elif success:
        print(f"\n{timestamp()} ⚠ Pas d'expected — valider puis:")
        print(f"   cp {RESULT} {EXPECTED}")

    print(f"\n{timestamp()} Sauvegarde résultat (hors sandbox)")
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
