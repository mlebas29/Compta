#!/bin/bash
# ============================================================================
# Installation minimale pour exécuter un outil de migration (tool_migrate_*.py)
# Portable Linux / macOS / WSL.
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

# --- Détection OS -------------------------------------------------
case "$(uname -s)" in
    Linux*)  OS=linux ;;
    Darwin*) OS=macos ;;
    *)       fail "OS non supporté : $(uname -s)"; exit 1 ;;
esac

# Indication portable d'installation pour un paquet manquant.
# Args: <linux_apt_name> <macos_brew_name> [cask]
pkg_hint() {
    local linux_pkg=$1 macos_pkg=$2 cask=${3:-}
    if [[ $OS == linux ]]; then
        echo "  → sudo apt install $linux_pkg"
    elif [[ $cask == cask ]]; then
        echo "  → brew install --cask $macos_pkg"
    else
        echo "  → brew install $macos_pkg"
    fi
}

echo "============================================================"
echo " Installation minimale (migration uniquement) — $OS"
echo "============================================================"
echo

# --- Python 3.10+ --------------------------------------------------
PYTHON=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        version=$("$cmd" --version 2>&1 | grep -Eo '[0-9]+\.[0-9]+' | head -1)
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
    pkg_hint python3 python
    ERRORS=$((ERRORS + 1))
fi

# --- LibreOffice (fournit le moteur UNO) ---------------------------
if command -v libreoffice &>/dev/null || [[ -d "/Applications/LibreOffice.app" ]]; then
    ok "libreoffice"
else
    fail "libreoffice (moteur UNO requis par les outils de migration)"
    pkg_hint libreoffice libreoffice cask
    ERRORS=$((ERRORS + 1))
fi

# --- Bindings UNO (python3-uno) -----------------------------------
# Sur Linux : paquet apt 'python3-uno' qui s'installe dans le Python système.
# Sur macOS : pas de paquet brew. Le module 'uno' est livré avec LibreOffice.app
# dans /Applications/LibreOffice.app/Contents/Resources/python (Python embarqué).
# Pour utiliser uno avec le Python système macOS, il faudrait copier le module —
# pratique fragile, on conseille plutôt d'invoquer le Python embarqué.
if [[ -n "$PYTHON" ]] && $PYTHON -c "import uno" &>/dev/null 2>&1; then
    ok "python3-uno (module 'uno' importable)"
elif [[ $OS == macos ]]; then
    warn "module 'uno' non importable depuis le Python système"
    LO_PY="/Applications/LibreOffice.app/Contents/Resources/python"
    if [[ -x "$LO_PY" ]] && "$LO_PY" -c "import uno" &>/dev/null 2>&1; then
        echo "  → uno disponible via le Python embarqué de LibreOffice :"
        echo "      $LO_PY tool_migrate_v4.1.0.py ~/Compta/comptes.xlsm"
        echo "  (utiliser ce binaire au lieu de python3 pour les migrations)"
    else
        fail "Python embarqué de LibreOffice introuvable ($LO_PY)"
        echo "  → réinstaller : brew install --cask libreoffice"
        ERRORS=$((ERRORS + 1))
    fi
else
    fail "python3-uno (bindings Python pour UNO)"
    pkg_hint python3-uno python3-uno
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
