#!/bin/bash
# ============================================================================
# Installation de Compta — portable Linux / macOS / WSL
#
# Usage:
#   cd <racine du clone Compta> && ./install.sh
#   Installe une instance EX (config.ini ← config.ini.default = EX).
#   Pour spécialiser le mode (PROD/DEV) ou réparer le raccourci : ./install_fix.sh
#
# (script cwd-relatif : INSTALL_DIR = $PWD)
#
# Vérifie les prérequis système, installe les dépendances Python,
# le navigateur Playwright, et crée un raccourci de lancement.
#
# Prérequis macOS :
#   Sonoma 14+ → Homebrew couvre tout.
#   Ventura 13 → MacPorts pour python/tesseract/gnupg : Homebrew se désengage
#   progressivement de Ventura et ses bottles disparaissent (brew install python,
#   brew install tesseract → recompilation source d'une heure et plus). MacPorts
#   reste maintenu sur Ventura et fournit les binaires.
#   LibreOffice : DMG officiel sur les deux (cf. Compta_portage.md).
# ============================================================================

set -e

# Fonctions partagées du provisioning : UI, $OS, read_mode/set_mode, setup_desktop
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
. "$SCRIPT_DIR/inc_install.sh"

ERRORS=0

# ------------------------------------------------------------------
# Mode (pour le raccourci) : lu dans config.ini > config.ini.default > EX.
# install.sh ne GÈRE PAS le mode (plus d'argument) — pour le poser/changer,
# utiliser ./install_fix.sh [EX|PROD|DEV]. #87 : config.ini fait foi.
# ------------------------------------------------------------------
if [[ "${1:-}" == -h || "${1:-}" == --help ]]; then
    echo "Usage: ./install.sh   (installe le clone courant ; mode/raccourci via ./install_fix.sh)"
    exit 0
fi

# install.sh crée une instance EX (config.ini hérite de config.ini.default = EX) :
# il ne pose pas le mode. Anomalie signalée si un config.ini préexistant n'est
# pas en EX (dossier déjà spécialisé → ./install_fix.sh pour le mode/raccourci).
INSTALL_MODE=EX
_pre=$(read_mode config.ini)
if [[ -n "$_pre" && "$_pre" != EX ]]; then
    warn "config.ini déjà en mode $_pre — install.sh installe en EX ; pour gérer le mode $_pre : ./install_fix.sh"
fi

# ------------------------------------------------------------------
# 0. OS (détecté par inc_install.sh)
# ------------------------------------------------------------------
[[ "$OS" == unknown ]] && { fail "OS non supporté : $(uname -s)"; exit 1; }

# Sous-cas WSL : Linux mais avec délégation possible à Windows pour
# l'ouverture de fichiers (wslview au lieu de xdg-open).
IS_WSL=false
if [[ $OS == linux ]] && grep -qi microsoft /proc/version 2>/dev/null; then
    IS_WSL=true
fi

# Sous-cas Ventura : Homebrew n'a plus de bottle pour python/tesseract sur
# macOS 13.x ; on bascule sur MacPorts. Sonoma+ : brew reste suffisant.
MACOS_USE_PORTS=false
MACOS_VERSION=""
if [[ $OS == macos ]]; then
    MACOS_VERSION=$(sw_vers -productVersion 2>/dev/null)
    MACOS_MAJOR=${MACOS_VERSION%%.*}
    if [[ -n "$MACOS_MAJOR" && "$MACOS_MAJOR" -le 13 ]]; then
        MACOS_USE_PORTS=true
    fi
fi

# Indication portable d'installation pour un paquet manquant.
# Args : <apt_pkg> <brew_pkg> [3e_arg]
#   3e_arg :
#     "cask"   → brew install --cask <brew_pkg> (utilisé aussi sur Ventura)
#     "NAME"   → nom paquet MacPorts, utilisé seulement sur Ventura
#                (sur Sonoma+ on retombe sur brew install <brew_pkg>)
#     absent   → brew install <brew_pkg>
pkg_hint() {
    local linux_pkg=$1 macos_pkg=$2 third=${3:-}
    if [[ $OS == linux ]]; then
        echo "  → sudo apt install $linux_pkg"
    elif [[ "$third" == cask ]]; then
        echo "  → brew install --cask $macos_pkg"
    elif $MACOS_USE_PORTS && [[ -n "$third" ]]; then
        echo "  → sudo port install $third"
    else
        echo "  → brew install $macos_pkg"
    fi
}

echo "============================================================"
if [[ $OS == macos ]]; then
    if $MACOS_USE_PORTS; then
        echo " Installation Compta — macOS $MACOS_VERSION (MacPorts pour python/tesseract)"
    else
        echo " Installation Compta — macOS $MACOS_VERSION (Homebrew)"
    fi
else
    echo " Installation Compta ($OS)"
fi
echo "============================================================"
echo

# Sanity check gestionnaires de paquets macOS (non bloquant)
if [[ $OS == macos ]]; then
    if ! command -v brew &>/dev/null; then
        warn "Homebrew non installé (requis pour gnupg, LibreOffice cask)"
        echo '  → /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
    fi
    if $MACOS_USE_PORTS && ! command -v port &>/dev/null; then
        warn "MacPorts non installé (requis pour python/tesseract sur Ventura)"
        echo "  → 1. télécharger https://www.macports.org/install.php    # ligne 'macOS 13 Ventura'"
        echo "       (MacPorts-X.X.X-13-Ventura.pkg) puis double-clic"
        echo "  → 2. dans un terminal neuf : sudo port selfupdate"
    fi
fi

# ------------------------------------------------------------------
# 1. Python
# ------------------------------------------------------------------
echo "--- [1/8] Vérification Python ---"

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
        else
            warn "$cmd $version (3.10+ requis)"
        fi
    fi
done

if [[ -z "$PYTHON" ]]; then
    fail "Python 3.10+ introuvable"
    pkg_hint python3 python "python311 py311-pip py311-tkinter"
    if [[ $OS == macos ]] && $MACOS_USE_PORTS; then
        echo "    sudo port select --set python3 python311"
        echo "    sudo port select --set pip pip311"
    fi
    ERRORS=$((ERRORS + 1))
fi

# ------------------------------------------------------------------
# 2. pip
# ------------------------------------------------------------------
# On vérifie pip *associé au $PYTHON détecté* (et non un pip3 quelconque dans
# le PATH). Sur macOS, $(command -v python3) et $(command -v pip3) peuvent
# pointer sur deux installations différentes — typiquement port select pour
# python3 + CLT Apple pour pip3 si l'utilisateur a oublié `port select pip`.
# Conséquence : `pip install` écrit dans le mauvais site-packages, et les
# imports échouent ensuite côté GUI.
if [[ -n "$PYTHON" ]] && $PYTHON -m pip --version &>/dev/null; then
    ok "pip (via $PYTHON -m pip)"
else
    fail "pip introuvable dans $PYTHON"
    pkg_hint python3-pip python py311-pip
    ERRORS=$((ERRORS + 1))
fi

# ------------------------------------------------------------------
# 3. Paquets système
# ------------------------------------------------------------------
echo
echo "--- [2/8] Vérification paquets système ---"

# Tkinter
if [[ -n "$PYTHON" ]] && $PYTHON -c "import tkinter" &>/dev/null 2>&1; then
    ok "tkinter"
else
    fail "tkinter (interface graphique)"
    pkg_hint python3-tk python-tk py311-tkinter
    ERRORS=$((ERRORS + 1))
fi

# Tesseract
# Sur Linux : bloquant (collecte SG indispensable)
# Sur macOS : warn (collecte SG optionnelle ; sur Ventura via MacPorts car
# Homebrew n'a plus de bottle).
# /opt/local/bin n'est pas toujours dans le PATH de l'install.sh (cron, sudo) →
# fallback explicite sur le chemin MacPorts.
if command -v tesseract &>/dev/null; then
    ok "tesseract"
elif [[ $OS == macos && -x /opt/local/bin/tesseract ]]; then
    ok "tesseract (MacPorts)"
elif [[ $OS == macos ]]; then
    warn "tesseract absent (collecte SG indisponible)"
    pkg_hint tesseract-ocr tesseract "tesseract tesseract-eng tesseract-fra"
else
    fail "tesseract (nécessaire pour la collecte SG)"
    pkg_hint tesseract-ocr tesseract
    ERRORS=$((ERRORS + 1))
fi

# Clipboard pour 2FA Kraken/Wise
if [[ $OS == macos ]]; then
    if command -v pbcopy &>/dev/null; then
        ok "pbcopy (clipboard natif macOS)"
    else
        fail "pbcopy introuvable — inhabituel sur macOS"
        ERRORS=$((ERRORS + 1))
    fi
else
    if command -v xclip &>/dev/null; then
        ok "xclip"
    else
        fail "xclip (nécessaire pour 2FA Kraken/Wise)"
        pkg_hint xclip xclip
        ERRORS=$((ERRORS + 1))
    fi
fi

# GPG
if command -v gpg &>/dev/null; then
    ok "gpg"
else
    fail "gpg (déchiffrement credentials)"
    pkg_hint gnupg gnupg gnupg2
    ERRORS=$((ERRORS + 1))
fi

# Pinentry GUI Linux/WSL — déchiffrement credentials depuis subprocess
# (capture_output=True dans cpt_fetch / inc_gpg_credentials → pas de TTY).
# pinentry-curses échoue avec "Inappropriate ioctl for device". Hard fail :
# sans pinentry GUI, toute collecte lancée depuis la GUI échoue.
# Pas de check macOS : les installs gpg usuelles (GPGTools/MacGPG2, brew)
# semblent configurer pinentry-mac correctement — à ajouter si un cas Mac
# réel se présente.
if [[ $OS == linux ]] && command -v gpg &>/dev/null; then
    if command -v pinentry-gtk-2 &>/dev/null \
       || command -v pinentry-gnome3 &>/dev/null \
       || command -v pinentry-qt &>/dev/null; then
        ok "pinentry GUI"
    else
        fail "pinentry GUI (déchiffrement credentials depuis la GUI)"
        echo "  → sudo apt install pinentry-gtk2"
        ERRORS=$((ERRORS + 1))
    fi
fi

# wslu (wslview) — sous WSL uniquement
# Permet l'ouverture des docs Markdown depuis la GUI via l'app Windows par défaut.
# Non bloquant : l'app fonctionne sans, mais l'ouverture de docs depuis la GUI
# tombera sur xdg-open qui n'a pas d'association fiable pour text/markdown sous
# Ubuntu WSL et finit par lancer Chrome.
if $IS_WSL; then
    if command -v wslview &>/dev/null; then
        ok "wslview (wslu)"
    else
        warn "wslview absent (ouverture des docs depuis la GUI dégradée)"
        warn "  → sudo apt install wslu"
    fi
fi

# LibreOffice — sweet spot ≥ 24.8 (mapping _xlfn.XLOOKUP).
# LO < 24.8 (notamment 24.2.x livré par apt Ubuntu 24.04 par défaut) corrompt
# silencieusement les formules XLOOKUP via UNO save — vrai pour les migrations
# ET pour les opérations GUI qui déclenchent un recalc.
# Sur macOS, ≥ 25 introduit aussi des Launch Constraints qui cassent le Python
# embedded (cf. CLAUDE_mac.md § LibreOffice Mac).
#
# Politique :
#   Linux/WSL  → install/upgrade automatique vers ≥ 24.8 (apt + PPA si besoin)
#   macOS      → détection seule, install/upgrade manuel par l'utilisateur

# Helpers Linux pour la gestion LibreOffice
_lo_ver_linux() {
    libreoffice --version 2>/dev/null | head -1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1
}
_lo_ge_24_8() {
    local ver=$1
    [[ -z $ver ]] && return 1
    local major=${ver%%.*}
    local minor=${ver#*.}; minor=${minor%%.*}
    [[ "$major" -gt 24 ]] || { [[ "$major" -eq 24 ]] && [[ "$minor" -ge 8 ]]; }
}
_lo_install_ppa_linux() {
    sudo apt install -y software-properties-common 2>/dev/null || true
    sudo add-apt-repository -y ppa:libreoffice/ppa && \
        sudo apt update && \
        sudo apt install -y libreoffice
}

if [[ $OS == macos ]]; then
    if [[ -x /Applications/LibreOffice.app/Contents/MacOS/soffice ]]; then
        LO_VER=$(/Applications/LibreOffice.app/Contents/MacOS/soffice --version 2>/dev/null | head -1 | awk '{print $2}')
        LO_MAJOR=$(echo "$LO_VER" | cut -d. -f1)
        LO_MINOR=$(echo "$LO_VER" | cut -d. -f2)
        # Test Python embedded utilisable (= absence Launch Constraints / SIGKILL AMFI)
        if /Applications/LibreOffice.app/Contents/Resources/python --version &>/dev/null; then
            PY_OK=true
        else
            PY_OK=false
        fi
        # Sur Ventura : strict 24.8.x (sweet spot — cf. Compta_portage.md § LibreOffice versions)
        #   < 24.8  → _xlfn.XLOOKUP non mappé (formules CTRL1 en #NAMES?)
        #   ≥ 25    → Python embedded SIGKILL par les Launch Constraints Apple
        # Sur Sonoma+ : tolérance — on accepte 24.8 et + tant que le Python embedded démarre.
        if $MACOS_USE_PORTS && ! { [[ "$LO_MAJOR" == "24" && "$LO_MINOR" == "8" ]]; }; then
            warn "libreoffice $LO_VER : sweet spot Ventura = 24.8.x"
            if [[ "$LO_MAJOR" -lt 24 || ( "$LO_MAJOR" -eq 24 && "$LO_MINOR" -lt 8 ) ]]; then
                warn "  → trop ancien : _xlfn.XLOOKUP non mappé (formules CTRL1 en #NAMES?)"
            else
                warn "  → trop récent : Apple Launch Constraints → Python embedded SIGKILL"
            fi
            warn "  → 24.8.x : https://downloadarchive.documentfoundation.org/libreoffice/old/ → dernier dossier 24.8.x.y → mac/x86_64/"
        elif ! $PY_OK; then
            warn "libreoffice $LO_VER : Python embedded non lançable"
            warn "  → vérifier quarantaine : sudo xattr -dr com.apple.quarantine /Applications/LibreOffice.app"
            warn "  → ou repasser sur 24.8.x : https://downloadarchive.documentfoundation.org/libreoffice/old/"
        elif [[ "$LO_MAJOR" -lt 24 ]]; then
            warn "libreoffice $LO_VER : < 24 — _xlfn.XLOOKUP non mappé (formules CTRL1 en #NAMES?)"
            warn "  → 24.8.x : https://downloadarchive.documentfoundation.org/libreoffice/old/"
        else
            ok "libreoffice $LO_VER (Python embedded OK)"
        fi
    else
        fail "libreoffice (tableur et service UNO)"
        echo "  → 1. DMG 24.8.x depuis les archives (la page principale ne propose plus que 25.x/26.x) :"
        echo "       https://downloadarchive.documentfoundation.org/libreoffice/old/"
        echo "       → dernier dossier 24.8.x.y → mac/x86_64/ → LibreOffice_*_MacOS_x86-64.dmg"
        echo "  → 2. double-clic .dmg → glisser LibreOffice.app dans /Applications"
        echo "  → 3. sudo xattr -dr com.apple.quarantine /Applications/LibreOffice.app"
        echo "       open /Applications/LibreOffice.app  # déclenche enregistrement AMFI"
        ERRORS=$((ERRORS + 1))
    fi
else
    # Linux/WSL : install si absent, puis upgrade via PPA si version < 24.8
    if ! command -v libreoffice &>/dev/null; then
        echo "libreoffice absent — installation via apt..."
        sudo apt install -y libreoffice || true
    fi

    if command -v libreoffice &>/dev/null; then
        LO_VER=$(_lo_ver_linux)
        if _lo_ge_24_8 "$LO_VER"; then
            ok "libreoffice $LO_VER"
        else
            warn "libreoffice $LO_VER : < 24.8 — corruption XLOOKUP via UNO save"
            warn "  → upgrade automatique via PPA libreoffice/ppa..."
            if _lo_install_ppa_linux; then
                LO_VER=$(_lo_ver_linux)
                ok "libreoffice $LO_VER (via PPA)"
            else
                fail "Échec install/upgrade LibreOffice — voir la commande PPA manuelle"
                warn "  → sudo add-apt-repository -y ppa:libreoffice/ppa && sudo apt update && sudo apt install libreoffice"
                ERRORS=$((ERRORS + 1))
            fi
        fi
    else
        fail "libreoffice (échec install via apt)"
        warn "  → sudo apt install libreoffice"
        ERRORS=$((ERRORS + 1))
    fi
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
echo "--- [3/8] Installation dépendances Python ---"

# PEP 668 (Ubuntu ≥ 23.04, Debian ≥ 12, Homebrew Python) : pip refuse
# d'installer hors d'un venv si EXTERNALLY-MANAGED est présent.
PIP_EXTRA=""
PY_STDLIB=$($PYTHON -c "import sysconfig; print(sysconfig.get_path('stdlib'))")
if [[ -f "$PY_STDLIB/EXTERNALLY-MANAGED" ]]; then
    warn "PEP 668 détecté — ajout de --break-system-packages"
    PIP_EXTRA="--break-system-packages"
fi

$PYTHON -m pip install -r requirements.txt $PIP_EXTRA
ok "requirements.txt installé"

# Python embarqué LibreOffice (macOS) : openpyxl indispensable pour les scripts UNO
# (tool_fix_formats, tool_controles) lancés via le wrapper python3-uno sur Mac.
# Le module 'uno' est livré avec LibreOffice ; openpyxl ne l'est pas.
#
# Helper : pip Mac écrit les extensions binaires en suffix `cpython-39-darwin.so`,
# mais le Python embedded LO 3.9 (Mac) attend `cpython-3.9.so` côté
# EXTENSION_SUFFIXES. Sans ce rename, cffi/cryptography/pdfplumber etc.
# sont physiquement présents mais invisibles à l'import. Idempotent.
lo_rename_so() {
    local count=0 f new
    while IFS= read -r f; do
        new="${f%.cpython-39-darwin.so}.cpython-3.9.so"
        [[ -e "$new" ]] && continue
        if mv "$f" "$new" 2>/dev/null; then
            count=$((count + 1))
        fi
    done < <(find /Applications/LibreOffice.app -name '*.cpython-39-darwin.so' -type f 2>/dev/null)
    [[ $count -gt 0 ]] && ok "  → $count .so renommé(s) (cpython-39-darwin → cpython-3.9)"
    return 0   # éviter exit code 1 sous `set -e` quand count=0 (aucun .so à renommer)
}

if [[ $OS == macos ]]; then
    LO_PY="/Applications/LibreOffice.app/Contents/Resources/python"
    # Deps requises par les scripts UNO (shebang python3-uno) dans le Python LO :
    #   openpyxl   → cpt_update et cpt_format_* (lecture/écriture xlsm)
    #   requests   → cpt_fetch_quotes (cotations)
    #   pdfplumber → cpt_format_BOURSOBANK / cpt_format_ETORO (relevés PDF)
    LO_PY_DEPS="openpyxl requests pdfplumber"
    if [[ -x "$LO_PY" ]]; then
        if "$LO_PY" -c "import openpyxl, requests, pdfplumber" 2>/dev/null; then
            ok "deps Python LO embedded présentes ($LO_PY_DEPS)"
        else
            echo "Installation deps dans le Python embarqué LibreOffice ($LO_PY_DEPS)…"
            if "$LO_PY" -m pip install $LO_PY_DEPS 2>/dev/null; then
                ok "deps installées dans le Python LibreOffice"
                lo_rename_so
            else
                warn "Échec install deps dans LibreOffice — les scripts UNO depuis la GUI pourraient échouer"
                warn "  → relancer manuellement : $LO_PY -m pip install $LO_PY_DEPS"
            fi
        fi
        # Toujours tenter le rename même si les deps sont déjà installées :
        # couvre les cas où l'utilisateur a installé manuellement d'autres
        # deps binaires sans relancer install.sh entre.
        lo_rename_so
    else
        warn "Python embarqué LibreOffice introuvable ($LO_PY) — boutons UNO de la GUI inopérants"
    fi
fi

# Wrapper python3-uno : sélectionne le Python qui contient le module 'uno'
# selon l'OS. Cible des shebangs '#!/usr/bin/env python3-uno' dans les scripts
# UNO. Sur Linux : exec python3. Sur macOS : exec le Python embarqué LibreOffice.
mkdir -p "$HOME/.local/bin"
WRAPPER="$HOME/.local/bin/python3-uno"
cat > "$WRAPPER" <<'WRAPPER_EOF'
#!/bin/bash
# python3-uno — installé par Compta install.sh.
# Utilisé via shebang : #!/usr/bin/env python3-uno
if [[ "$(uname -s)" == "Darwin" ]]; then
    LO_PY="/Applications/LibreOffice.app/Contents/Resources/python"
    if [[ -x "$LO_PY" ]]; then
        exec "$LO_PY" "$@"
    else
        echo "python3-uno : LibreOffice introuvable ($LO_PY)" >&2
        exit 127
    fi
else
    exec python3 "$@"
fi
WRAPPER_EOF
chmod +x "$WRAPPER"
if command -v python3-uno >/dev/null 2>&1; then
    ok "wrapper python3-uno installé dans $WRAPPER"
else
    warn "wrapper python3-uno déposé mais introuvable dans le PATH"
    # Fichier de profil shell selon $SHELL : ~/.bashrc n'est PAS chargé par les
    # terminaux Mac (Terminal.app ouvre un login shell), d'où ~/.bash_profile.
    case "$(basename "${SHELL:-}")" in
        zsh)  SHELL_RC="~/.zshrc" ;;
        bash) [[ $OS == macos ]] && SHELL_RC="~/.bash_profile" || SHELL_RC="~/.bashrc" ;;
        *)    SHELL_RC="votre fichier de profil shell" ;;
    esac
    warn "  → ajouter à $SHELL_RC : export PATH=\"\$HOME/.local/bin:\$PATH\""
fi

# ------------------------------------------------------------------
# 5. Playwright + Chrome
# ------------------------------------------------------------------
echo
echo "--- [4/8] Installation navigateur Playwright ---"

# Cas heureux : un browser utilisable par Playwright est déjà disponible.
# On évite alors le patch sudo /etc/os-release (qui ne sert qu'à install-deps
# pour les dérivés Ubuntu non-reconnus par Playwright). Côté Linux cela évite
# aussi de bloquer une exécution non-interactive (CI, sandbox, automatisation).
if command -v google-chrome &>/dev/null || [[ -d "$HOME/.cache/ms-playwright" ]]; then
    ok "Browser Playwright déjà disponible (skip patch /etc/os-release)"
    $PYTHON -m playwright install chrome || warn "Playwright install chrome a renvoyé un warning"
else
    OS_PATCHED=false

    if [[ $OS == linux ]]; then
        # Playwright ne reconnaît qu'Ubuntu/Debian — les dérivés (Zorin, Mint, Pop!_OS)
        # nécessitent un patch temporaire de /etc/os-release.
        OS_ID=$(bash -c 'source /etc/os-release && echo $ID')
        OS_VERSION=$(bash -c 'source /etc/os-release && echo $VERSION_ID')

        if [[ "$OS_ID" != "ubuntu" && "$OS_ID" != "debian" ]]; then
            OS_ID_LIKE=$(bash -c 'source /etc/os-release && echo $ID_LIKE')
            if [[ "$OS_ID_LIKE" == *"ubuntu"* || "$OS_ID_LIKE" == *"debian"* ]]; then
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
fi

# ------------------------------------------------------------------
# 6. Raccourci de lancement
# ------------------------------------------------------------------
echo
echo "--- [5/8] Raccourci ---"
setup_desktop "$(pwd)" "$INSTALL_MODE"

# ------------------------------------------------------------------
# 7. Répertoires de travail
# ------------------------------------------------------------------
echo
echo "--- [6/8] Répertoires ---"
for dir in dropbox archives logs; do
    mkdir -p "$dir"
done
ok "dropbox/ archives/ logs/ créés"

# Cadre privé : dépôt PRV vide (Solo) si absent — homologue du public, inerte
# tant que vide (cf. inc_install.sh ensure_custom_frame / Compta_extension.md).
ensure_custom_frame "$(pwd)"

# ------------------------------------------------------------------
# 8. Classeur initial
# ------------------------------------------------------------------
echo
echo "--- [7/8] Classeur ---"
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
echo "--- [8/8] Configuration ---"

# config.ini : copié depuis le .default si absent
if [[ ! -f "config.ini" && -f "config.ini.default" ]]; then
    cp config.ini.default config.ini
    ok "config.ini créé depuis config.ini.default"
elif [[ -f "config.ini" ]]; then
    ok "config.ini déjà présent"
else
    warn "config.ini.default absent — créer config.ini manuellement"
fi

# config_credentials.md : poser la copie de travail depuis le modèle, mais seulement
# s'il n'existe encore aucun credential (ni clair, ni chiffré) — idempotent : ne pas
# ré-écraser une saisie en cours ni recréer le modèle vierge après chiffrement + rm.
if [[ ! -f "config_credentials.md" && ! -f "config_credentials.md.gpg" && -f "config_credentials.md.default" ]]; then
    cp config_credentials.md.default config_credentials.md
    ok "config_credentials.md créé depuis le modèle — à remplir, puis chiffrer (gpg -c) et supprimer le clair"
fi

# config_category_mappings.json : pas de .default — l'app crée un JSON vide
# automatiquement à la 1re exécution si le fichier est absent.

# ------------------------------------------------------------------
# Résumé
# ------------------------------------------------------------------
# Recheck PATH après création du wrapper : sur Linux Mint/Ubuntu, ~/.profile
# n'ajoute ~/.local/bin au PATH qu'à la *prochaine* session si le dossier vient
# d'être créé. La GUI est couverte par le sh -c du .desktop, mais le shell
# courant de l'utilisateur ne verra python3-uno qu'après reload.
PATH_WARNING=""
if ! command -v python3-uno >/dev/null 2>&1; then
    PATH_WARNING="yes"
fi

echo
echo "############################################################"
echo -e "#  ${GREEN}Installation terminée${NC}"
echo "############################################################"
echo
echo " Récapitulatif :"
echo "  • Dépendances Python (requirements.txt) installées"
echo "  • Navigateur Playwright installé"
if [[ $OS == linux ]]; then
    echo "  • Raccourci créé : $DESKTOP_TARGET"
else
    echo "  • Bundle créé : $DESKTOP_TARGET"
fi
echo "  • Wrapper python3-uno déposé : $WRAPPER"
echo "  • Répertoires de travail : dropbox/ archives/ logs/"
echo "  • Cadre privé : custom/ (dépôt PRV vide, Solo — cf. Compta_extension.md)"
echo "  • Classeur initial : comptes.xlsm"
echo "  • Configuration : config.ini"
echo
if [[ -n "$PATH_WARNING" ]]; then
    echo -e "${YELLOW}############################################################${NC}"
    echo -e "${YELLOW}#  ACTION REQUISE — PATH${NC}"
    echo -e "${YELLOW}############################################################${NC}"
    echo
    echo " Le wrapper python3-uno a été déposé dans ~/.local/bin mais n'est pas"
    echo " visible dans le PATH de ce shell. La GUI est OK (le raccourci ajoute"
    echo " ~/.local/bin automatiquement), mais en ligne de commande :"
    echo
    echo -e "   ${GREEN}→ ouvrir un nouveau terminal${NC}"
    echo -e "   ${GREEN}→ ou exécuter : source ~/.profile${NC}"
    echo
fi
echo "------------------------------------------------------------"
echo " Prochaines étapes :"
echo "------------------------------------------------------------"
if [[ $OS == macos ]]; then
    echo "  1. Lancer : « Comptabilité.app » (~/Applications — Launchpad/Spotlight)"
    echo "     → préférer le bundle au terminal (PATH/interpréteur gérés), cf. Compta.md § Lancement"
else
    echo "  1. Lancer : raccourci « Comptabilité [EX] » — ou en terminal : $PYTHON cpt_gui.py"
fi
echo "     → L'interface sert aussi de configurateur (comptes, sites, paramètres)"
echo "  2. Renseigner les credentials :"
echo "     → remplir config_credentials.md (créé depuis le modèle — voir README.md)"
echo "     → gpg -c config_credentials.md  &&  rm config_credentials.md   (rm impératif : efface le clair)"
echo
