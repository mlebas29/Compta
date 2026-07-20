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

    # Sections ACTIVES du modèle (config.ini.default) absentes de la config → les
    # ajouter (nouveau site promu au public, p. ex.). Additif et idempotent : ne
    # touche jamais une section existante ; ne copie que les sections à clés
    # ACTIVES (un bloc purement commenté du modèle est ignoré). Miroir fixeur du
    # détecteur check_config_obsolete « section [X] manquante » (inc_update.py).
    local def; def="$(dirname "$f")/config.ini.default"
    if [[ -f "$def" ]]; then
        local sec
        while IFS= read -r sec; do
            [[ -n "$sec" ]] || continue
            grep -qE "^\[${sec}\]" "$f" && continue          # déjà présente → skip
            if [[ -z "${DRY_RUN:-}" ]]; then
                # bloc [sec] du modèle jusqu'à la section suivante, en élaguant
                # les lignes vides/commentaires de queue (= l'en-tête du bloc suivant).
                {
                    printf '\n'
                    awk -v s="[$sec]" '
                        $0==s {grab=1}
                        grab && /^\[/ && $0!=s {stop=1}
                        grab && !stop {buf[n++]=$0}
                        END {
                            while (n>0 && (buf[n-1] ~ /^[[:space:]]*$/ || buf[n-1] ~ /^[[:space:]]*#/)) n--
                            for (i=0; i<n; i++) print buf[i]
                        }
                    ' "$def"
                } >> "$f"
            fi
            changed=1; ok "section : [$sec] ajoutée depuis config.ini.default"
        done < <(awk '
            /^\[/ {sec=$0; gsub(/[][]/, "", sec)}
            /^[[:space:]]*[A-Za-z0-9_]+[[:space:]]*=/ && sec {active[sec]=1}
            END {for (s in active) print s}
        ' "$def")

        # Clés ACTIVES du modèle absentes d'une section DÉJÀ présente (clé nouvelle
        # ajoutée à une section existante de config.ini.default). Additif, idempotent :
        # la ligne verbatim du modèle est insérée juste après l'en-tête de section.
        # Tourne APRÈS l'ajout de section (une section neuve arrive déjà complète).
        local defline kname
        while IFS=$'\t' read -r sec defline; do
            [[ -n "$sec" && -n "$defline" ]] || continue
            if [[ -z "${DRY_RUN:-}" ]]; then
                awk -v s="[$sec]" -v line="$defline" \
                    '{print} $0==s {print line}' "$f" > "$f.tmp" && mv "$f.tmp" "$f"
            fi
            kname=${defline%%=*}; kname=${kname// /}
            changed=1; ok "clé : [$sec] $kname ajoutée depuis config.ini.default"
        done < <(awk '
            FNR==NR {
                if ($0 ~ /^\[/) { dsec=$0; gsub(/[][]/, "", dsec) }
                else if (dsec != "" && $0 ~ /^[[:space:]]*[A-Za-z0-9_]+[[:space:]]*=/) {
                    line=$0; sub(/^[[:space:]]*/, "", line)
                    eq=index(line, "="); k=substr(line, 1, eq-1); sub(/[[:space:]]+$/, "", k)
                    dkey[dsec SUBSEP k]=$0
                }
                next
            }
            {
                if ($0 ~ /^\[/) { fsec=$0; gsub(/[][]/, "", fsec); fseen[fsec]=1 }
                else if (fsec != "" && $0 ~ /^[[:space:]]*[A-Za-z0-9_]+[[:space:]]*=/) {
                    line=$0; sub(/^[[:space:]]*/, "", line)
                    eq=index(line, "="); k=substr(line, 1, eq-1); sub(/[[:space:]]+$/, "", k)
                    fkey[fsec SUBSEP k]=1
                }
            }
            END {
                for (key in dkey) {
                    split(key, a, SUBSEP); s=a[1]; k=a[2]
                    if (fseen[s] && !(key in fkey)) print s "\t" dkey[key]
                }
            }
        ' "$def" "$f")
    fi

    [[ $changed -eq 0 ]] && ok "config déjà normalisée (rien à migrer)"
    # Sonde effective-state (#121) : sous DRY_RUN, rc 3 = la normalisation CHANGERAIT
    # quelque chose, rc 0 = rien. En réel l'écriture a eu lieu → rc 0.
    if [[ -n "${DRY_RUN:-}" && $changed -eq 1 ]]; then return 3; fi
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
        return 3     # sonde effective-state (#121) : rc 3 = serait créé (le cas présent → rc 0 plus haut)
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
# Contenu cible du raccourci — FACTORISÉ pour que la SONDE dry-run (#121, compare à
# l'installé) et l'ÉCRITURE réelle partent du MÊME template → zéro dérive sonde/écriture.
_desktop_linux_content() {  # $1=install_dir $2=label $3=icon $4=wm_class
    cat <<EOF
[Desktop Entry]
Name=Comptabilité ${2}
Comment=Gestion comptable — collecte, import et appariement
Exec=sh -c 'PATH="\$HOME/.local/bin:\$PATH" exec python3 ${1}/cpt_gui.py'
Path=${1}
Icon=${1}/${3}
Terminal=false
Type=Application
Categories=Office;Finance;
StartupWMClass=${4}
EOF
}

_macos_exec_content() {  # $1=install_dir $2=python_abs
    cat <<EOF
#!/bin/bash
export PATH="\$HOME/.local/bin:/opt/local/bin:/usr/local/bin:/opt/homebrew/bin:\$PATH"
cd "${1}"
exec "${2}" cpt_gui.py
EOF
}

setup_desktop() {  # $1=install_dir  $2=mode (EX|PROD|DEV)
    local INSTALL_DIR="$1" INSTALL_MODE="$2"
    local PY="${PYTHON:-python3}"
    local _label _icon _wm

    case "$INSTALL_MODE" in
        DEV)  _label="[DEV]";  _icon="cpt_gui.png";        _wm="cpt_gui" ;;
        PROD) _label="[PROD]"; _icon="cpt_gui_prod.png";   _wm="cpt_gui" ;;
        *)    _label="[EX]";   _icon="cpt_gui_export.png"; _wm="cpt_gui_export" ;;
    esac

    # Sonde effective-state (#121) : génère le contenu cible et le compare à l'installé
    # → rc 3 (le raccourci CHANGERAIT) / 0 (déjà à jour), SANS rien écrire. upgrade ne
    # lance l'écriture réelle (plus bas) que si la sonde a renvoyé 3 → plus de
    # réécriture pour rien, verdict --check exact. Même template des deux côtés
    # (_*_content) → zéro dérive. macOS : on compare l'exécutable (porte INSTALL_DIR +
    # python absolu, les plus volatils) ; plist/icône stables à mode fixé.
    if [[ -n "${DRY_RUN:-}" ]]; then
        if [[ $OS == linux ]]; then
            local f="$HOME/.local/share/applications/cpt_gui_${INSTALL_MODE}.desktop"
            if [[ -f "$f" && "$(_desktop_linux_content "$INSTALL_DIR" "$_label" "$_icon" "$_wm")" == "$(cat "$f")" ]]; then
                ok "Raccourci : déjà à jour (mode $INSTALL_MODE)"; return 0
            fi
        elif [[ $OS == macos ]]; then
            local _sfx=""; [[ "$INSTALL_MODE" != EX ]] && _sfx=" $INSTALL_MODE"
            local _exe="$HOME/Applications/Comptabilité${_sfx}.app/Contents/MacOS/Comptabilité${_sfx}"
            local _pyabs; _pyabs=$(command -v "$PY")
            if [[ -f "$_exe" && "$(_macos_exec_content "$INSTALL_DIR" "$_pyabs")" == "$(cat "$_exe")" ]]; then
                ok "Raccourci : déjà à jour (mode $INSTALL_MODE)"; return 0
            fi
        fi
        ok "Raccourci : serait (re)généré (mode $INSTALL_MODE)"; return 3
    fi

    if [[ $OS == linux ]]; then
        local DESKTOP_DIR="$HOME/.local/share/applications"
        mkdir -p "$DESKTOP_DIR"
        local DESKTOP_FILE="$DESKTOP_DIR/cpt_gui_${INSTALL_MODE}.desktop"
        # Exec via sh -c pour ajouter ~/.local/bin au PATH (wrapper python3-uno).
        _desktop_linux_content "$INSTALL_DIR" "$_label" "$_icon" "$_wm" > "$DESKTOP_FILE"
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
        _macos_exec_content "$INSTALL_DIR" "$PYTHON_ABS" > "$APP_BUNDLE/Contents/MacOS/$APP_NAME"
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
