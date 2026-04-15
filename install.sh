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

# PEP 668 (Ubuntu ≥ 23.04, Debian ≥ 12) : pip refuse d'installer
# en dehors d'un venv si EXTERNALLY-MANAGED est présent
PIP_EXTRA=""
PY_STDLIB=$($PYTHON -c "import sysconfig; print(sysconfig.get_path('stdlib'))")
if [[ -f "$PY_STDLIB/EXTERNALLY-MANAGED" ]]; then
    warn "PEP 668 détecté — ajout de --break-system-packages"
    PIP_EXTRA="--break-system-packages"
fi

$PIP install -r requirements.txt $PIP_EXTRA
ok "requirements.txt installé"

# ------------------------------------------------------------------
# 5. Playwright + Chrome
# ------------------------------------------------------------------
echo
echo "--- Installation navigateur Playwright ---"

# Playwright ne reconnaît que Ubuntu/Debian — les dérivés (Zorin, Mint, Pop!_OS)
# nécessitent un patch temporaire de /etc/os-release
OS_ID=$(bash -c 'source /etc/os-release && echo $ID')
OS_VERSION=$(bash -c 'source /etc/os-release && echo $VERSION_ID')
OS_PATCHED=false

if [[ "$OS_ID" != "ubuntu" && "$OS_ID" != "debian" ]]; then
    # Vérifier si c'est un dérivé Ubuntu/Debian
    OS_ID_LIKE=$(bash -c 'source /etc/os-release && echo $ID_LIKE')
    if [[ "$OS_ID_LIKE" == *"ubuntu"* || "$OS_ID_LIKE" == *"debian"* ]]; then
        # Déduire la version Ubuntu réelle depuis le codename
        UBUNTU_CODENAME=$(bash -c 'source /etc/os-release && echo $UBUNTU_CODENAME')
        case "$UBUNTU_CODENAME" in
            noble)  UBUNTU_VERSION="24.04" ;;
            jammy)  UBUNTU_VERSION="22.04" ;;
            focal)  UBUNTU_VERSION="20.04" ;;
            *)      UBUNTU_VERSION="22.04" ;;
        esac
        warn "$OS_ID $OS_VERSION détecté (dérivé Ubuntu $UBUNTU_VERSION/$UBUNTU_CODENAME) — patch temporaire pour Playwright"
        sudo sed -i "s/^ID=$OS_ID/ID=ubuntu/" /etc/os-release
        sudo sed -i "s/^VERSION_ID=\"$OS_VERSION\"/VERSION_ID=\"$UBUNTU_VERSION\"/" /etc/os-release
        OS_PATCHED=true
    fi
fi

if $PYTHON -m playwright install chrome; then
    ok "Chrome installé pour Playwright"
else
    warn "Installation Playwright échouée — essai sans dépendances système"
    $PYTHON -m playwright install chromium --no-shell || warn "Playwright non installé (collecte indisponible)"
fi

# Restaurer /etc/os-release si patché
if $OS_PATCHED; then
    sudo sed -i "s/^ID=ubuntu/ID=$OS_ID/" /etc/os-release
    sudo sed -i "s/^VERSION_ID=\"$UBUNTU_VERSION\"/VERSION_ID=\"$OS_VERSION\"/" /etc/os-release
    ok "/etc/os-release restauré ($OS_ID $OS_VERSION)"
fi

# ------------------------------------------------------------------
# 6. Raccourci bureau GNOME
# ------------------------------------------------------------------
echo
echo "--- Raccourci bureau ---"
INSTALL_DIR="$(pwd)"
DESKTOP_DIR="$HOME/.local/share/applications"
DESKTOP_FILE="$DESKTOP_DIR/cpt_gui_export.desktop"

mkdir -p "$DESKTOP_DIR"
cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Name=Comptabilité [EX]
Comment=Gestion comptable — version export
Exec=python3 ${INSTALL_DIR}/cpt_gui.py
Path=${INSTALL_DIR}
Icon=${INSTALL_DIR}/cpt_gui_export.png
Terminal=false
Type=Application
Categories=Office;Finance;
StartupWMClass=cpt_gui_export
EOF
update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true
ok "Raccourci installé (${INSTALL_DIR}) → clic droit barre des tâches pour épingler"

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
# 8. Classeur initial
# ------------------------------------------------------------------
echo
echo "--- Classeur ---"
if [[ ! -f "comptes.xlsm" && -f "comptes_template.xlsm" ]]; then
    cp comptes_template.xlsm comptes.xlsm
    ok "comptes.xlsm créé depuis le template"
elif [[ -f "comptes.xlsm" ]]; then
    ok "comptes.xlsm déjà présent"
else
    warn "comptes_template.xlsm absent — placer votre comptes.xlsm manuellement"
fi

# ------------------------------------------------------------------
# 9. Fichiers de configuration
# ------------------------------------------------------------------
echo
echo "--- Configuration ---"

# config.ini : copié depuis le .default si absent
if [[ ! -f "config.ini" && -f "config.ini.default" ]]; then
    cp config.ini.default config.ini
    ok "config.ini créé depuis config.ini.default"
elif [[ -f "config.ini" ]]; then
    ok "config.ini déjà présent"
else
    warn "config.ini.default absent — créer config.ini manuellement"
fi

# config_category_mappings.json : copié depuis le .default si absent
if [[ ! -f "config_category_mappings.json" && -f "config_category_mappings.json.default" ]]; then
    cp config_category_mappings.json.default config_category_mappings.json
    ok "config_category_mappings.json créé depuis le .default"
elif [[ -f "config_category_mappings.json" ]]; then
    ok "config_category_mappings.json déjà présent"
else
    warn "config_category_mappings.json.default absent — configurer via l'onglet Catégories"
fi

# ------------------------------------------------------------------
# Résumé
# ------------------------------------------------------------------
echo
echo "============================================================"
echo -e " ${GREEN}Installation terminée${NC}"
echo "============================================================"
echo
echo "Prochaines étapes :"
echo "  1. Lancer : $PYTHON cpt_gui.py"
echo "     → L'interface sert aussi de configurateur (comptes, sites, paramètres)"
echo "  2. Créer le fichier credentials :"
echo "     → Écrire config_credentials.md (voir README.md)"
echo "     → gpg -c config_credentials.md"
echo
