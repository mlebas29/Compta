#!/bin/bash
# ============================================================================
# inc_install.sh — fonctions partagées du provisioning Compta (à SOURCER)
#
# Sourcé par install.sh (configure le clone courant), install_fork.sh (passage
# mixte EX → dual PROD+DEV) et install_fix.sh. Registre SETUP en shell —
# pendant de inc_mode.py
# côté runtime Python.
#
# Usage :  . "$(cd "$(dirname "$0")" && pwd)/inc_install.sh"
# Expose : ok/warn/fail, $OS, read_mode, set_mode, normalize_config, setup_desktop,
#          ensure_custom_frame
#          ($DESKTOP_TARGET = chemin du raccourci/bundle après setup_desktop)
# ============================================================================

# --- UI ----------------------------------------------------------------------
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✓${NC} $1"; }
warn() { echo -e "${YELLOW}⚠${NC} $1"; }
fail() { echo -e "${RED}✗${NC} $1" >&2; }

# --- OS ----------------------------------------------------------------------
case "$(uname -s)" in
    Linux*)  OS=linux ;;
    Darwin*) OS=macos ;;
    *)       OS=unknown ;;
esac

# --- Config per-instance non versionnée (gitignorée) -------------------------
# Liste SOURCE des fichiers propres à chaque clone, à rapatrier vers une nouvelle
# machine (cf. tool_pullconf.sh) : git transporte le CODE, ceci transporte la
# config + le classeur. Tous gitignorés (non versionnés). Recoupe ce que
# reclone.sh restaure (lui : tout le non-tracké, même machine) et ce que
# .gitignore protège — défini ici une seule fois pour éviter la dérive.
CONFIG_FILES="config.ini config_credentials.md.gpg config_accounts.json config_category_mappings.json config_cotations.json config_pipeline.json comptes.xlsm"

# --- Mode (config.ini) — pendant shell de inc_mode.py ------------------------
# Canonique MAJUSCULE (insensible à la casse). Pas de shim legacy : seul le
# migrateur normalize_config (ci-dessous) connaît les noms hérités.
read_mode() {  # $1=config.ini ; affiche le mode normalisé ('' si absent/inconnu)
    local f="$1" m
    [[ -f "$f" ]] || { echo ""; return; }
    m=$(grep -E '^[[:space:]]*mode[[:space:]]*=' "$f" | head -1 \
        | sed -E 's/.*=[[:space:]]*//; s/[[:space:]].*//' | tr 'a-z' 'A-Z')
    echo "$m"
}

set_mode() {  # $1=config.ini  $2=mode : force mode=$2
    local f="$1" mode="$2"
    if [[ -n "${DRY_RUN:-}" ]]; then return 0; fi   # dry-run : pas d'écriture (le caller cite)
    if grep -qE '^[[:space:]]*mode[[:space:]]*=' "$f"; then
        sed -i.bak -E "s|^[[:space:]]*mode[[:space:]]*=.*|mode = $mode|" "$f" && rm -f "$f.bak"
    else
        printf 'mode = %s\n' "$mode" >> "$f"
    fi
}

# --- Migration de config (renommages legacy → canonique) ---------------------
# Applique en place les renommages connus à un config.ini préexistant, en
# préservant les commentaires (édition ligne à ligne, pas de dump configparser).
# Idempotent (no-op si déjà à jour). Pendant côté config de la famille
# tool_migrate_* (classeur) : c'est le chemin de migration qui permet de retirer
# les read-shims runtime (cf. #89). Renommages couverts :
#   [general] mode : 'export' (legacy) → EX  (+ casse normalisée DEV/PROD/EX)
#   [paths]   seafile_comptes_file     → classeur_externe
normalize_config() {  # $1=config.ini
    local f="$1" changed=0 raw norm
    [[ -f "$f" ]] || { fail "normalize_config : $f absent"; return 1; }

    raw=$(grep -E '^[[:space:]]*mode[[:space:]]*=' "$f" | head -1 \
          | sed -E 's/.*=[[:space:]]*//; s/[[:space:]].*//')
    if [[ -n "$raw" ]]; then
        norm=$(printf '%s' "$raw" | tr 'a-z' 'A-Z')   # casse normalisée
        [[ "$norm" == EXPORT ]] && norm=EX            # migration legacy (export → EX)
        if [[ "$raw" != "$norm" ]]; then
            set_mode "$f" "$norm"
            changed=1; ok "mode : '$raw' → '$norm'"
        fi
    fi

    if grep -qE '^[[:space:]]*seafile_comptes_file[[:space:]]*=' "$f"; then
        if [[ -z "${DRY_RUN:-}" ]]; then
            sed -i.bak -E 's|^([[:space:]]*)seafile_comptes_file([[:space:]]*=)|\1classeur_externe\2|' "$f" && rm -f "$f.bak"
        fi
        changed=1; ok "clé : seafile_comptes_file → classeur_externe"
    fi

    [[ $changed -eq 0 ]] && ok "config déjà normalisée (rien à migrer)"
    return 0
}

# --- Cadre privé custom/ (dépôt PRV, homologue du public) --------------------
# Pose le frame privé : un dépôt git VIDE dans custom/ (mode Solo — sans remote,
# sans commit, sans contenu). Le PRV est un pair VERSIONNÉ du public (cf.
# Compta_extension.md § Le modèle) → on garantit le .git, pas seulement le dossier.
# Invariant « jamais une contrainte » : custom/ vide est inerte (inc_bootstrap
# no-op), jamais exigé par le code, et son zéro-commit autorise un rattachement
# ff propre à un hub plus tard. Idempotent :
#   - custom/.git présent          → no-op (Solo / Hub local / Hub distant déjà posé)
#   - custom/ sans .git, ou absent → git init (branche main), vide
# Branche posée via symbolic-ref (HEAD unborn) : portable tout git (pas de -b,
# absent avant git 2.28). Câblé dans install.sh seul (installs fraîches) ; le
# rattrapage des installs antérieures relève de l'orchestrateur post-pull (#94).
ensure_custom_frame() {  # $1=install_dir (défaut: répertoire courant)
    local dir="${1:-.}/custom"
    command -v git >/dev/null 2>&1 || { warn "git absent — cadre privé custom/ non posé"; return 0; }
    if [[ -e "$dir/.git" ]]; then
        ok "cadre privé custom/ déjà présent"
        return 0
    fi
    if [[ -n "${DRY_RUN:-}" ]]; then
        ok "cadre privé custom/ : serait posé (git init vide)"
        return 0
    fi
    mkdir -p "$dir" || { fail "création de custom/ impossible"; return 1; }
    git init -q "$dir" || { fail "git init custom/ a échoué"; return 1; }
    git -C "$dir" symbolic-ref HEAD refs/heads/main 2>/dev/null
    ok "cadre privé custom/ posé (Solo : dépôt git vide, sans remote)"
    return 0
}

# --- Raccourci de lancement (Linux .desktop / macOS .app) --------------------
# Le CHEMIN vient du 1er arg ; libellé/icône/wm_class du MODE (2e arg).
# PYTHON (absolu, bundle macOS) : variable d'env si définie, sinon python3.
setup_desktop() {  # $1=install_dir  $2=mode (EX|PROD|DEV)
    local INSTALL_DIR="$1" INSTALL_MODE="$2"
    local PY="${PYTHON:-python3}"
    local _label _icon _wm

    case "$INSTALL_MODE" in
        DEV)  _label="[DEV]";  _icon="cpt_gui.png";        _wm="cpt_gui" ;;
        PROD) _label="[PROD]"; _icon="cpt_gui_prod.png";   _wm="cpt_gui" ;;
        *)    _label="[EX]";   _icon="cpt_gui_export.png"; _wm="cpt_gui_export" ;;
    esac

    # Régénère TOUJOURS le raccourci → en dry-run, la détermination est triviale
    # (« serait régénéré ») : on cite et on sort avant toute écriture, sans toucher
    # aux branches Linux/macOS (#111 parité --check).
    if [[ -n "${DRY_RUN:-}" ]]; then
        ok "Raccourci : serait (re)généré (mode $INSTALL_MODE)"
        return 0
    fi

    if [[ $OS == linux ]]; then
        local DESKTOP_DIR="$HOME/.local/share/applications"
        mkdir -p "$DESKTOP_DIR"
        local DESKTOP_FILE="$DESKTOP_DIR/cpt_gui_${INSTALL_MODE}.desktop"
        # Exec via sh -c pour ajouter ~/.local/bin au PATH (wrapper python3-uno).
        cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Name=Comptabilité ${_label}
Comment=Gestion comptable — collecte, import et appariement
Exec=sh -c 'PATH="\$HOME/.local/bin:\$PATH" exec python3 ${INSTALL_DIR}/cpt_gui.py'
Path=${INSTALL_DIR}
Icon=${INSTALL_DIR}/${_icon}
Terminal=false
Type=Application
Categories=Office;Finance;
StartupWMClass=${_wm}
EOF
        update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true
        DESKTOP_TARGET="$DESKTOP_FILE"
        ok "Raccourci installé (${DESKTOP_FILE})"

    elif [[ $OS == macos ]]; then
        local APPS_DIR="$HOME/Applications"
        # Nom/ID de bundle par mode (EX = défaut) pour que DEV et PROD coexistent
        # sur le même Mac — sinon collision sur "Comptabilité.app" (cf. dual).
        local _suffix="" _idsuffix=""
        if [[ "$INSTALL_MODE" != EX ]]; then
            _suffix=" $INSTALL_MODE"
            _idsuffix=".$(printf '%s' "$INSTALL_MODE" | tr 'A-Z' 'a-z')"
        fi
        local APP_NAME="Comptabilité$_suffix"
        local APP_BUNDLE="$APPS_DIR/${APP_NAME}.app"
        local APP_ID="net.labeille.compta$_idsuffix"
        mkdir -p "$APPS_DIR"
        rm -rf "$APP_BUNDLE"
        mkdir -p "$APP_BUNDLE/Contents/MacOS" "$APP_BUNDLE/Contents/Resources"

        # Chemin absolu de python (Dock = PATH minimal) + PATH augmenté pour
        # les subprocess GUI (UNO / OCR / gpg).
        local PYTHON_ABS; PYTHON_ABS=$(command -v "$PY")
        cat > "$APP_BUNDLE/Contents/MacOS/$APP_NAME" <<EOF
#!/bin/bash
export PATH="\$HOME/.local/bin:/opt/local/bin:/usr/local/bin:/opt/homebrew/bin:\$PATH"
cd "${INSTALL_DIR}"
exec "${PYTHON_ABS}" cpt_gui.py
EOF
        chmod +x "$APP_BUNDLE/Contents/MacOS/$APP_NAME"

        cat > "$APP_BUNDLE/Contents/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>      <string>${APP_NAME}</string>
    <key>CFBundleIdentifier</key>      <string>${APP_ID}</string>
    <key>CFBundleName</key>            <string>${APP_NAME}</string>
    <key>CFBundleDisplayName</key>     <string>${APP_NAME}</string>
    <key>CFBundleVersion</key>         <string>1.0</string>
    <key>CFBundleShortVersionString</key> <string>1.0</string>
    <key>CFBundlePackageType</key>     <string>APPL</string>
    <key>CFBundleIconFile</key>        <string>icon</string>
    <key>NSHighResolutionCapable</key> <true/>
</dict>
</plist>
EOF

        # Icône du bundle = celle du MODE (bleu DEV / rouge PROD / jaune EX),
        # pas systématiquement l'export — cohérent avec le thème runtime.
        local _png="$INSTALL_DIR/$_icon"
        if [[ -f "$_png" ]]; then
            local ICONSET; ICONSET=$(mktemp -d)/icon.iconset
            mkdir -p "$ICONSET"
            local size double
            for size in 16 32 128 256 512; do
                double=$((size * 2))
                sips -z $size $size "$_png" \
                    --out "$ICONSET/icon_${size}x${size}.png" >/dev/null 2>&1
                sips -z $double $double "$_png" \
                    --out "$ICONSET/icon_${size}x${size}@2x.png" >/dev/null 2>&1
            done
            iconutil -c icns "$ICONSET" -o "$APP_BUNDLE/Contents/Resources/icon.icns" 2>/dev/null \
                && ok "Icône convertie en .icns ($_icon)" \
                || warn "Conversion icône échouée — icône Python par défaut"
            rm -rf "$(dirname "$ICONSET")"
        else
            warn "$_icon absent — icône Python par défaut"
        fi
        touch "$APP_BUNDLE"   # force macOS à rafraîchir l'icône
        DESKTOP_TARGET="$APP_BUNDLE"
        ok "Bundle installé ($APP_BUNDLE)"
    fi
}
