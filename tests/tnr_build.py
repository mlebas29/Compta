#!/usr/bin/env python3-uno
"""
tnr_build.py — TNR build (template → GUI batch + pipe MANUEL)

Usage:
  python3 tests/tnr_build.py
  python3 tests/tnr_build.py --keep       # debug (pas de restore)

Scénario allégé : 4 comptes, 5 titres (dont multi-devises), 15 opérations.
Les opérations et positions PVL sont importées via le pipe MANUEL
(pas d'injection directe UNO).
"""

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

_name = Path(__file__).stem.removeprefix('tnr_')
SCENARIO_DIR = Path(__file__).parent / 'tnr' / _name
EXPECTED = SCENARIO_DIR / 'expected.xlsm'
RESULT = SCENARIO_DIR / 'result.xlsm'
MANUEL_XLSX = SCENARIO_DIR / 'manuel.xlsx'

sys.path.insert(0, str(Path(__file__).parent))
import tnr_lib
from tnr_lib import (
    find_code_root, timestamp, check_libreoffice_running,
    compare_result, save_result, check_integrity_fast,
    setup_sandbox,
)

CODE_ROOT = find_code_root(__file__)
sys.path.insert(0, str(CODE_ROOT))
from inc_excel_schema import SHEET_OPERATIONS, ColResolver, uno_row
from tool_gui_cli import HeadlessGUI

# ============================================================================
# DONNÉES DU SCÉNARIO (extraites de man_expected.xlsm)
# ============================================================================

# (code, famille, nom_long, derived_from, formula)
BUILD_COTATIONS_SPOT = [
    ('XAU', 'metal', "Gramme d'or Spot", None, None),
    ('BTC', 'crypto', 'Bitcoin', None, None),
]

BUILD_DEVISES = [
    ('USD', 'fiat', 'Dollar US', None, None),
    ('OrPr', 'metal', "Gramme d'or Premium (pièces)", 'XAU', '*1.1'),
    ('SAT', 'crypto', 'Satoshi (1 / 100 000 000 Bitcoin)', 'BTC', '/100000000'),
]

# (intitulé, type, devise)
BUILD_ACCOUNTS = [
    ('Portefeuille eToro USD Titres', 'Portefeuilles', 'USD'),
    ('Portefeuille eToro USD Réserve', 'Devises étrangères', 'USD'),
    ('Compte Kraken BTC', 'Crypto monnaies', 'SAT'),
]

# (intitulé, type, devise_or_empty) — biens matériels sans devise
BUILD_BIENS = [
    ('Pièces or', 'Biens matériels', 'OrPr'),
]

# (compte, titre, devise)
BUILD_TITLES = [
    ('Portefeuille eToro USD Titres', '*AI.PA*', 'USD'),
    ('Portefeuille eToro USD Titres', '*SPX500*', 'USD'),
    ('Portefeuille eToro USD Titres', '*BTC/USD*', 'USD'),
    ('Portefeuille eToro USD Titres', '*COMT*', 'EUR'),
    ('Portefeuille eToro USD Titres', '*KWEB*', 'USD'),
]

# Cours à écrire dans Cotations (code → cours)
BUILD_COURS = {
    'XAU': 144.12,
    'BTC': 61009,
    'USD': 0.8635,
}

# Postes et catégories budgétaires ajoutés par le scénario
# (le reverse les supprimera pour revenir au template)
BUILD_POSTES = [
    ('Banque', True),  # Fixe
]
BUILD_CATEGORIES = [
    ('Frais bancaires', 'Banque'),
]


def setup_build():
    """Build via GUI batch + pipe MANUEL."""
    SCRIPT_DIR = tnr_lib.SCRIPT_DIR
    COMPTES_XLSX = tnr_lib.COMPTES_XLSX
    TEMPLATE = SCRIPT_DIR / 'comptes_template.xlsm'

    if not TEMPLATE.exists():
        print(f"❌ Template introuvable : {TEMPLATE}")
        return False
    if not MANUEL_XLSX.exists():
        print(f"❌ manuel.xlsx introuvable : {MANUEL_XLSX}")
        return False

    # Copier le template comme base
    shutil.copy2(TEMPLATE, COMPTES_XLSX)
    print(f"   {TEMPLATE.name} → comptes.xlsm")

    # ==== Phase 1 : GUI batch (structure) ====
    gui = HeadlessGUI(COMPTES_XLSX)
    errors = 0

    with gui.batch() as doc:
        # Cotations spot + devises
        all_devises = BUILD_COTATIONS_SPOT + BUILD_DEVISES
        print(f"🔧 Ajout de {len(all_devises)} devises...")
        for code, famille, nom, derived, formula in all_devises:
            if not gui.add_devise(code, famille, nom=nom,
                                  derived_from=derived, formula=formula, doc=doc):
                errors += 1

        # Comptes
        # Champs PAT remplis avec '-'/'oui' pour neutraliser l'alarme Patrimoine
        # (commit d628e492 — toute ventilation laissée vide = écart au TOTAL).
        print(f"🔧 Ajout de {len(BUILD_ACCOUNTS)} comptes...")
        for intitule, acct_type, devise in BUILD_ACCOUNTS:
            if not gui.add_account(intitule, acct_type, devise=devise,
                                   sous_type='-', domiciliation='-',
                                   titulaire='-', propriete='oui',
                                   controle=True, doc=doc):
                errors += 1

        # Biens matériels
        print(f"🔧 Ajout de {len(BUILD_BIENS)} biens matériels...")
        for intitule, acct_type, devise in BUILD_BIENS:
            if not gui.add_account(intitule, acct_type, devise=devise,
                                   sous_type='-', domiciliation='-',
                                   titulaire='-', propriete='oui',
                                   controle=False, doc=doc):
                errors += 1

        # Écrire les comptes avant les titres (dépendance portefeuille)
        gui._save_accounts(doc=doc)

        # Rafraîchir cr : les named ranges CAT* ont été décalés par l'ajout de devises
        doc.cr.refresh(xdoc=doc.document)

        # Postes budgétaires (avant catégories : cat référence poste)
        print(f"🔧 Ajout de {len(BUILD_POSTES)} postes...")
        for name, fixe in BUILD_POSTES:
            if not gui.add_poste(name, fixe=fixe, doc=doc):
                errors += 1

        # Catégories budgétaires
        print(f"🔧 Ajout de {len(BUILD_CATEGORIES)} catégories...")
        for name, poste in BUILD_CATEGORIES:
            if not gui.add_category(name, poste=poste, doc=doc):
                errors += 1

        # Titres
        print(f"🔧 Ajout de {len(BUILD_TITLES)} titres...")
        for compte, titre, devise in BUILD_TITLES:
            if not gui.add_title(compte, titre, devise=devise, doc=doc):
                errors += 1

        # Écrire les cours
        from inc_excel_schema import SHEET_COTATIONS
        from inc_uno import get_col_range_bounds
        cr = doc.cr
        ws_cot = doc.get_sheet(SHEET_COTATIONS)
        cot_bounds = get_col_range_bounds(doc.document, 'COTcode')
        cot_data = (cot_bounds[2] if cot_bounds else 3) + 1
        n_cours = 0
        for r0 in range(uno_row(cot_data), uno_row(cot_data) + 20):
            code = ws_cot.getCellByPosition(cr.col('COTcode'), r0).getString().strip()
            if not code:
                continue
            if code in BUILD_COURS:
                cell = ws_cot.getCellByPosition(cr.col('COTcours'), r0)
                # Préserver les formules de dérivation
                formula = cell.getFormula()
                if formula and str(formula).startswith('='):
                    continue
                cell.setValue(BUILD_COURS[code])
                n_cours += 1
        print(f"   {n_cours} cours écrits")

    if errors:
        print(f"❌ {errors} erreur(s) pendant le build GUI")
        return False
    print("✓ Build GUI terminé")

    # ==== Phase 2 : Pipe MANUEL (opérations + positions PVL) ====
    print(f"\n{timestamp()} Import pipe MANUEL")

    # Copier manuel.xlsx dans dropbox/MANUEL/
    dropbox_manuel = SCRIPT_DIR / 'dropbox' / 'MANUEL'
    dropbox_manuel.mkdir(parents=True, exist_ok=True)
    shutil.copy2(MANUEL_XLSX, dropbox_manuel / 'manuel.xlsx')

    # Activer uniquement MANUEL dans config.ini
    config_ini = SCRIPT_DIR / 'config.ini'
    config_text = config_ini.read_text()
    import re
    config_text = re.sub(r'^(enabled\s*=).*$', r'\1 MANUEL', config_text, flags=re.MULTILINE)
    config_ini.write_text(config_text)

    # Lancer cpt_update (le vrai pipe) avec --TNR
    env = {**os.environ, 'COMPTA_BASE_DIR': str(SCRIPT_DIR)}
    r = subprocess.run(
        [sys.executable, str(SCRIPT_DIR / 'cpt_update.py'),
         '--TNR', '-v'],
        cwd=SCRIPT_DIR, env=env, capture_output=True, text=True)
    if r.stdout:
        for line in r.stdout.strip().splitlines():
            print(f"  {line}")
    if r.returncode != 0:
        print(f"  ❌ cpt_update a retourné {r.returncode}")
        if r.stderr:
            for line in r.stderr.strip().splitlines():
                print(f"  {line}")
        return False
    print("✓ Import MANUEL terminé")

    return True


def main():
    success = True
    t_start = time.time()

    if not check_libreoffice_running():
        return 1

    print(f"\n{timestamp()} Setup sandbox")
    sandbox = setup_sandbox(SCENARIO_DIR)
    tnr_lib.set_base_dir(sandbox)
    SCRIPT_DIR = tnr_lib.SCRIPT_DIR
    COMPTES_XLSX = tnr_lib.COMPTES_XLSX
    print(f"  sandbox : {sandbox}")

    # Mode Classeur : vider config_pipeline.json dans la sandbox
    import json
    pipeline_json = sandbox / 'config_pipeline.json'
    if pipeline_json.exists():
        with open(pipeline_json, 'w') as f:
            json.dump({"linked_operations": {}, "solde_auto": {}}, f, indent=2)

    # Vider config_cotations.json : en PROD le config copié depuis code_root
    # contient les devises utilisateur (USD/CHF/...), incompatibles avec un
    # test qui démarre vierge et les ajoute.
    (sandbox / 'config_cotations.json').write_text('{}\n', encoding='utf-8')

    print(f"\n{timestamp()} Build (GUI batch + pipe MANUEL)")
    if not setup_build():
        success = False
        return 1

    if success:
        print(f"\n{timestamp()} Vérification intégrité")
        if not check_integrity_fast(COMPTES_XLSX):
            success = False

    if success:
        print(f"\n{timestamp()} Normalisation formats")
        # build sert de base au reverse : on applique les corrections pour
        # un expected stable (comme template/example).
        from tool_fix_formats import fix_formats
        from io import StringIO
        import contextlib, re
        buf = StringIO()
        with contextlib.redirect_stdout(buf):
            fix_formats(COMPTES_XLSX, apply=True)
        output = buf.getvalue()
        m = re.search(r'(\d+) correction', output)
        n_fixes = int(m.group(1)) if m else 0
        if n_fixes == 0:
            print("  ✓ Formats OK")
        else:
            print(f"  ✓ {n_fixes} correction(s) de format appliquée(s)")

    if success:
        print(f"\n{timestamp()} Contrôles métier (tool_controles)")
        ctrl_script = SCRIPT_DIR / 'tool_controles.py'
        env = {**os.environ, 'COMPTA_BASE_DIR': str(SCRIPT_DIR)}
        r = subprocess.run(
            [sys.executable, str(ctrl_script), '-f', str(COMPTES_XLSX)],
            cwd=SCRIPT_DIR, env=env, capture_output=True, text=True)
        if r.stdout:
            for line in r.stdout.strip().splitlines():
                print(f"  {line}")
        if r.returncode != 0:
            print(f"  ❌ tool_controles a retourné {r.returncode}")
            if r.stderr:
                print(r.stderr, file=sys.stderr)
            success = False

    if success and EXPECTED.exists():
        print(f"\n{timestamp()} Comparaison vs expected")
        cmp_result = compare_result(EXPECTED, tuples=True, brutal=False)
        if cmp_result is False:
            success = False
    elif success:
        print(f"\n{timestamp()} ⚠ Pas d'expected — valider puis:")
        print(f"   cp {RESULT} {EXPECTED}")

    print(f"\n{timestamp()} Sauvegarde résultat (hors sandbox pour archivage)")
    save_result(RESULT)
    # Note : la sandbox survit (debug post-mortem possible).
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
