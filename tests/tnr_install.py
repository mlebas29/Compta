#!/usr/bin/env python3
"""tnr_install.py — TNR d'install vierge (couche deps Python) via venv (#185).

Attrape les régressions d'install que le smoke DEV ne peut PAS voir (« already
satisfied » = aveugle par construction) : une dépendance oubliée dans
`requirements.txt`, ou `install_python_deps` cassée. Mécanique :

  1. crée un venv JETABLE (Python neuf, ZÉRO paquet tiers) ;
  2. y lance la VRAIE fonction `install_python_deps` (sourcée depuis
     `inc_install.sh` — zéro réimplémentation, on teste le code réel) ;
  3. vérifie que les paquets déclarés (`requirements.txt`) importent ;
  4. vérifie que les modules CŒUR de l'appli importent dans ce venv — un
     `import` neuf oublié dans `requirements.txt` casse ici (bout-en-bout).

⚠ LIMITE (assumée, cf. #185) : un venv n'est PAS `EXTERNALLY-MANAGED` → il ne
reproduit NI PEP 668 NI le `sys.path` figé de v5.25.2 (son site-packages est
toujours dans le path). Pour CES deux-là il faut un CONTENEUR (mini-OS Debian
jetable) — piste documentée, non couverte ici. Ce TNR couvre la régression la
plus FRÉQUENTE (complétude des deps), pas la fidélité machine-nue.

Coût : un `pip install` complet en venv frais (playwright/pdfplumber/Pillow…)
= plusieurs minutes au 1ᵉʳ run (cache pip ensuite). → scénario LOURD /
pré-release, hors boucle rapide (comme `reverse`).

Usage : python3 tests/tnr_install.py
"""

import os
import shutil
import subprocess
import sys
import tempfile
import venv
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from tnr_lib import find_code_root  # noqa: E402

CODE_ROOT = find_code_root(__file__)

# Paquets déclarés (requirements.txt) → nom d'IMPORT (≠ nom pip : Pillow→PIL).
DECLARED = {
    'playwright': 'playwright',
    'openpyxl': 'openpyxl',
    'pdfplumber': 'pdfplumber',
    'pytesseract': 'pytesseract',
    'Pillow': 'PIL',
    'requests': 'requests',
    'pyperclip': 'pyperclip',
}

# Modules CŒUR (PUB) : leur import tire les deps réelles (playwright/openpyxl/
# pdfplumber…). S'ils importent en venv vierge, requirements.txt est complet.
CORE_MODULES = ['inc_fetch', 'inc_format', 'inc_excel_compta', 'inc_update',
                'inc_logging', 'inc_gpg_credentials',
                'cpt_format_SOCGEN', 'cpt_fetch_WISE']


def _run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def main():
    print("=" * 60)
    print("TNR install vierge (#185) — deps Python dans un venv jetable")
    print("=" * 60)

    venv_dir = Path(tempfile.mkdtemp(prefix='compta_tnr_venv_'))
    try:
        # 1. venv frais, isolé (pas de --system-site-packages → vraiment vide).
        print(f"\n→ création venv : {venv_dir}")
        venv.create(venv_dir, with_pip=True)
        vpy = venv_dir / 'bin' / 'python'
        if not vpy.exists():  # Windows
            vpy = venv_dir / 'Scripts' / 'python.exe'

        # 2. la VRAIE fonction install_python_deps (cwd = clone → requirements.txt).
        print("→ install_python_deps (source inc_install.sh)... "
              "[peut prendre plusieurs minutes]", flush=True)
        r = _run(['bash', '-c',
                  f'source "{CODE_ROOT}/inc_install.sh" '
                  f'&& install_python_deps "{vpy}"'],
                 cwd=CODE_ROOT)
        if r.returncode != 0:
            print((r.stdout or '')[-2000:])
            print((r.stderr or '')[-2000:])
            print("\n✗ ÉCHEC — install_python_deps rc != 0")
            return 1
        for line in (r.stdout or '').strip().splitlines()[-3:]:
            print(f"   {line}")

        failures = []

        # 3. Paquets déclarés importables dans le venv.
        print("\n→ import des paquets déclarés (requirements.txt) :")
        for pkg, mod in DECLARED.items():
            rc = _run([str(vpy), '-c', f'import {mod}']).returncode
            print(f"   {'✓' if rc == 0 else '✗'} {pkg} (import {mod})")
            if rc != 0:
                failures.append(f"paquet {pkg} : import {mod} échoue")

        # 4. Modules cœur de l'appli importables (deps complètes ?).
        print("\n→ import des modules cœur de l'appli (deps complètes ?) :")
        env = {**os.environ, 'PYTHONPATH': str(CODE_ROOT)}
        for m in CORE_MODULES:
            r = _run([str(vpy), '-c', f'import {m}'], cwd=CODE_ROOT, env=env)
            ok = r.returncode == 0
            print(f"   {'✓' if ok else '✗'} {m}")
            if not ok:
                last = ((r.stderr or '').strip().splitlines() or [''])[-1]
                failures.append(f"module {m} : {last}")

        print("\n" + "=" * 60)
        if failures:
            print(f"✗ {len(failures)} ÉCHEC(S) :")
            for f in failures:
                print(f"   - {f}")
            return 1
        print("✓ OK — install_python_deps + tous imports satisfaits (venv vierge)")
        return 0
    finally:
        shutil.rmtree(venv_dir, ignore_errors=True)


if __name__ == '__main__':
    sys.exit(main())
