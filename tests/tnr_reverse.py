#!/usr/bin/env python3-uno
"""
tnr_reverse.py — TNR reverse (build → template via GUI purge/delete)

Usage:
  python3 tests/tnr_reverse.py

Part du build expected (plus léger qu'example), purge+supprime chaque compte,
supprime les devises, compare le résultat avec le template.
Exerce les chemins GUI de suppression.
"""

import argparse
import shutil
import sys
import time
from pathlib import Path

_name = Path(__file__).stem.removeprefix('tnr_')
SCENARIO_DIR = Path(__file__).parent / 'tnr' / _name
RESULT = SCENARIO_DIR / 'result.xlsm'
SOURCE = Path(__file__).parent / 'tnr' / 'build' / 'expected.xlsm'
# Référence = expected local (promu après investigation).
# Cible idéale = template mais plusieurs restrictions techniques temporaires documentées dans notes.md :
#   - purge_account réduit les bornes OP* (artefact UNO) : tolérance built-in (OP* raccourcis = warning)
#   - teardown ne régénère pas les formules Budget pieds en named ranges : héritées de _save_devise (magique)
#   - → cible template visée après refactor _save_devise (chantier 3B)
EXPECTED = SCENARIO_DIR / 'expected.xlsm'

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

# Comptes, catégories, postes et devises ajoutés par tnr_build (à supprimer dans le reverse)
SOURCE_ACCOUNTS = [
    'Portefeuille eToro USD Titres',
    'Portefeuille eToro USD Réserve',
    'Compte Kraken BTC',
    'Pièces or',
]
SOURCE_CATEGORIES = ['Frais bancaires']
SOURCE_POSTES = ['Banque']
SOURCE_DERIVED = ['USD', 'OrPr', 'SAT']  # dérivées (ordre import)
SOURCE_SPOTS = ['XAU', 'BTC']            # spots (ordre import)

# Valeurs Patrimoine à conserver (celles du template)
PATRIMOINE_KEEP = {
    'sous_type':     {'Euro', 'Foncier', 'Mobilier', 'Titres'},
    'domiciliation': set(),
    'titulaire':     set(),
    'propriete':     {'oui', 'non'},
}


def teardown(gui):
    """Purge+supprime chaque compte, catégories, postes, devises, patrimoine.
    Les delete_* renvoient False silencieusement si absent — pas de pré-check
    sur les attributs d'instance (non disponibles via DaemonGUI)."""
    # 1. Purge + suppression de chaque compte
    print(f"   {len(SOURCE_ACCOUNTS)} comptes à purger+supprimer")
    for name in SOURCE_ACCOUNTS:
        gui.purge_account(intitule=name)
        gui.delete_account(intitule=name)

    # 1b. Tentative "Compte clos" résiduel (créé par purge pour reloger les ops).
    gui.delete_account(intitule='Compte clos')

    # 2. Suppression des catégories (sauf structurelles et "-")
    print(f"   Suppression {len(SOURCE_CATEGORIES)} catégorie(s)...")
    for name in SOURCE_CATEGORIES:
        gui.delete_category(name=name)

    # 3. Suppression des postes (sauf Divers)
    print(f"   Suppression {len(SOURCE_POSTES)} poste(s)...")
    for name in SOURCE_POSTES:
        gui.delete_poste(name=name)

    # 4. Suppression des devises non-EUR (dérivées d'abord, puis spots)
    print(f"   Suppression de {len(SOURCE_DERIVED) + len(SOURCE_SPOTS)} devises...")
    for code in reversed(SOURCE_DERIVED):
        gui.delete_devise(code=code)
    for code in reversed(SOURCE_SPOTS):
        gui.delete_devise(code=code)

    # 5. Nettoyage Patrimoine (lignes en trop vs template)
    print(f"   Nettoyage Patrimoine...")
    gui.cleanup_patrimoine(keep_values=PATRIMOINE_KEEP)

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
        print(f"   Lancer d'abord : python3 tests/tnr_build.py")
        return 1

    print(f"\n{timestamp()} Setup sandbox")
    sandbox = setup_sandbox(SCENARIO_DIR)
    tnr_lib.set_base_dir(sandbox)
    COMPTES_XLSX = tnr_lib.COMPTES_XLSX
    print(f"  sandbox : {sandbox}")

    # Copier le build expected comme point de départ
    print(f"\n{timestamp()} Copie source → comptes.xlsm")
    shutil.copy2(SOURCE, COMPTES_XLSX)
    print(f"   {SOURCE.name} → comptes.xlsm")

    # Purge + suppression via GUI
    print(f"\n{timestamp()} Teardown via GUI ({backend})")
    with gui_cls(COMPTES_XLSX) as gui:
        if not teardown(gui):
            print("❌ Erreur pendant le teardown")
            return 1

    # Vérification intégrité
    print(f"\n{timestamp()} Vérification intégrité")
    ok = check_integrity_fast(COMPTES_XLSX)

    # Comparaison vs expected (template)
    print(f"\n{timestamp()} Comparaison vs expected")
    cmp_result = compare_result(EXPECTED, tuples=False, brutal=True)
    if cmp_result is False:
        ok = False

    # Sauvegarder le résultat (hors sandbox pour archivage)
    print(f"\n{timestamp()} Sauvegarde résultat")
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
