#!/bin/bash
# ============================================================================
# Installation minimale pour exécuter un outil de migration (tool_migrate_*.py)
#
# Usage:
#   cd ~/Compta-tmp && ./install_migrate.sh
#   python3 tool_migrate_v4.1.0.py ~/Compta/comptes.xlsm
#
# Cible : utilisateur en mode classeur qui veut emprunter ponctuellement
# le mode assisté juste pour exécuter une migration. N'installe ni Playwright,
# ni Tkinter, ni GPG, ni Tesseract — uniquement ce dont les outils de
# migration ont besoin (UNO + openpyxl).
#
# Pour une installation complète (interface GUI, collecte web, OCR, etc.)
# utiliser ./install.sh.
# ============================================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

ok()   { echo -e "${GREEN}✓${NC} $1"; }
warn() { echo -e "${YELLOW}⚠${NC} $1"; }
fail() { echo -e "${RED}✗${NC} $1"; }

ERRORS=0

echo "============================================================"
echo " Installation minimale (migration uniquement)"
echo "============================================================"
echo

# --- Python 3.10+ --------------------------------------------------
PYTHON=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        version=$("$cmd" --version 2>&1 | grep -oP '\d+\.\d+')
        major=$(echo "$version" | cut -d. -f1)
        minor=$(echo "$version" | cut -d. -f2)
        if [[ "$major" -ge 3 && "$minor" -ge 10 ]]; then
            PYTHON="$cmd"
            ok "$cmd $version"
            break
        fi
    fi
done
if [[ -z "$PYTHON" ]]; then
    fail "Python 3.10+ introuvable"
    echo "  → sudo apt install python3"
    ERRORS=$((ERRORS + 1))
fi

# --- LibreOffice (fournit le moteur UNO) ---------------------------
if command -v libreoffice &>/dev/null; then
    ok "libreoffice"
else
    fail "libreoffice (moteur UNO requis par les outils de migration)"
    echo "  → sudo apt install libreoffice"
    ERRORS=$((ERRORS + 1))
fi

# --- python3-uno (bindings UNO) -----------------------------------
if [[ -n "$PYTHON" ]] && $PYTHON -c "import uno" &>/dev/null 2>&1; then
    ok "python3-uno"
else
    fail "python3-uno (bindings Python pour UNO)"
    echo "  → sudo apt install python3-uno"
    ERRORS=$((ERRORS + 1))
fi

if [[ $ERRORS -gt 0 ]]; then
    echo
    fail "$ERRORS prérequis manquant(s) — corriger puis relancer ./install_migrate.sh"
    exit 1
fi

# --- openpyxl (pip) ------------------------------------------------
PIP_EXTRA=""
PY_STDLIB=$($PYTHON -c "import sysconfig; print(sysconfig.get_path('stdlib'))")
if [[ -f "$PY_STDLIB/EXTERNALLY-MANAGED" ]]; then
    PIP_EXTRA="--break-system-packages"
fi

if $PYTHON -c "import openpyxl" &>/dev/null 2>&1; then
    ok "openpyxl déjà installé"
else
    $PYTHON -m pip install 'openpyxl>=3.0.0' $PIP_EXTRA
    ok "openpyxl installé"
fi

echo
echo "============================================================"
echo -e " ${GREEN}Prêt${NC} — fermer LibreOffice puis lancer la migration :"
echo "============================================================"
echo
echo "  $PYTHON tool_migrate_v4.1.0.py ~/Compta/comptes.xlsm"
echo
