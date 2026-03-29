#!/bin/bash
# ============================================================================
# Installation de Compta
#
# Usage:
#   cd ~/Compta/Export && ./install.sh
#
# Vérifie les prérequis système, installe les dépendances Python,
# le navigateur Playwright, et le raccourci bureau GNOME.
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
echo " Installation Compta"
echo "============================================================"
echo

# ------------------------------------------------------------------
# 1. Python
# ------------------------------------------------------------------
echo "--- Vérification Python ---"

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
        else
            warn "$cmd $version (3.10+ requis)"
        fi
    fi
done

if [[ -z "$PYTHON" ]]; then
    fail "Python 3.10+ introuvable"
    echo "  → sudo apt install python3"
    ERRORS=$((ERRORS + 1))
fi

# ------------------------------------------------------------------
# 2. pip
# ------------------------------------------------------------------
PIP=""
for cmd in pip3 pip; do
    if command -v "$cmd" &>/dev/null; then
        PIP="$cmd"
        ok "$cmd"
        break
    fi
done

if [[ -z "$PIP" ]]; then
    fail "pip introuvable"
    echo "  → sudo apt install python3-pip"
    ERRORS=$((ERRORS + 1))
fi

# ------------------------------------------------------------------
# 3. Paquets système
# ------------------------------------------------------------------
echo
echo "--- Vérification paquets système ---"

# Tkinter
if $PYTHON -c "import tkinter" &>/dev/null 2>&1; then
    ok "python3-tk"
else
    fail "python3-tk (interface graphique)"
    echo "  → sudo apt install python3-tk"
    ERRORS=$((ERRORS + 1))
fi

# Tesseract
if command -v tesseract &>/dev/null; then
    ok "tesseract-ocr"
else
    warn "tesseract-ocr absent (nécessaire pour la collecte SG)"
    echo "  → sudo apt install tesseract-ocr"
fi

# xclip
if command -v xclip &>/dev/null; then
    ok "xclip"
else
    warn "xclip absent (nécessaire pour 2FA Kraken/Wise)"
    echo "  → sudo apt install xclip"
fi

# GPG
if command -v gpg &>/dev/null; then
    ok "gpg"
else
    fail "gpg (déchiffrement credentials)"
    echo "  → sudo apt install gnupg"
    ERRORS=$((ERRORS + 1))
fi

# LibreOffice
if command -v libreoffice &>/dev/null; then
    ok "libreoffice"
else
    fail "libreoffice (tableur et service UNO)"
    echo "  → sudo apt install libreoffice"
    ERRORS=$((ERRORS + 1))
fi

# ------------------------------------------------------------------
# Arrêt si prérequis manquants
# ------------------------------------------------------------------
if [[ $ERRORS -gt 0 ]]; then
    echo
    fail "$ERRORS prérequis manquant(s) — corriger puis relancer ./install.sh"
    exit 1
fi

# ------------------------------------------------------------------
# 4. Dépendances Python
# ------------------------------------------------------------------
echo
echo "--- Installation dépendances Python ---"
$PIP install -r requirements.txt
ok "requirements.txt installé"

# ------------------------------------------------------------------
# 5. Playwright + Chrome
# ------------------------------------------------------------------
echo
echo "--- Installation navigateur Playwright ---"
$PYTHON -m playwright install chrome
ok "Chrome installé pour Playwright"

# ------------------------------------------------------------------
# 6. Raccourci bureau GNOME
# ------------------------------------------------------------------
echo
echo "--- Raccourci bureau ---"
DESKTOP_SRC="cpt_gui_export.desktop"
DESKTOP_DIR="$HOME/.local/share/applications"

if [[ -f "$DESKTOP_SRC" ]]; then
    mkdir -p "$DESKTOP_DIR"
    cp "$DESKTOP_SRC" "$DESKTOP_DIR/"
    update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true
    ok "Raccourci installé → clic droit barre des tâches pour épingler"
else
    warn "Fichier $DESKTOP_SRC absent, raccourci non installé"
fi

# ------------------------------------------------------------------
# 7. Répertoires de travail
# ------------------------------------------------------------------
echo
echo "--- Répertoires ---"
for dir in dropbox archives logs; do
    mkdir -p "$dir"
done
ok "dropbox/ archives/ logs/ créés"

# ------------------------------------------------------------------
# Résumé
# ------------------------------------------------------------------
echo
echo "============================================================"
echo -e " ${GREEN}Installation terminée${NC}"
echo "============================================================"
echo
echo "Prochaines étapes :"
echo "  1. Éditer config.ini (sites actifs, chemins)"
echo "  2. Créer le fichier credentials :"
echo "     → Écrire config_credentials.md (voir README.md)"
echo "     → gpg -c config_credentials.md"
echo "  3. Placer votre fichier comptes.xlsm ici"
echo "  4. Lancer : $PYTHON cpt_gui.py"
echo
