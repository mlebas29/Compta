#!/bin/bash
# ============================================================================
# install_fork.sh — Passage d'une instance mixte (EX) au dual (PROD + DEV)
#
# Lancé depuis la racine d'une instance EX (1 dossier, mixte) :
#   cd ~/Compta && ./install_fork.sh [--no-data] [chemin-dev] [--yes]
#
# Effet :
#   1. crée une instance DEV : clone PUB depuis origin (GitHub) ; volet PRV
#      selon l'état de custom/ (taxonomie 0/B/A.1/A.2, cf. Compta_tools.md) :
#        0   pas de custom/          → rien (instance PUB seule)
#        B   custom/ sans .git       → copie des fichiers (non versionné des
#                                      deux côtés, sauvegarde à la charge de
#                                      l'utilisateur)
#        A.1 custom/.git sans remote → crée un hub bare LOCAL
#                                      (~/Compta-hub/custom.git, override
#                                      $COMPTA_HUB), y rattache l'instance
#                                      courante et y clone le DEV → les deux
#                                      passent en A.2 ; migration vers un hub
#                                      distant plus tard = git remote set-url
#        A.2 custom/.git avec remote → clone distant depuis l'origin (les
#                                      deux instances partagent le hub)
#   2. bascule le dossier courant EX → PROD (consommateur, thème rouge) ;
#   3. (re)génère les raccourcis des deux dossiers via setup_desktop
#      (inc_install.sh).
#
# Données métier (classeur + config*) : copiées par défaut dans le DEV —
# sémantique du fork (bac à sable réel). --no-data y déroge : pas de copie,
# DEV provisionné vierge (config depuis .default, classeur template).
#
# Le DEV est en mode DEV : la publication y est doublement bloquée (bouton masqué
# si mode≠PROD, et cpt.py --push refuse en DEV). Cf. Compta_extension.md § Dual.
# ============================================================================

set -euo pipefail

# Fonctions partagées (UI, $OS, read_mode/set_mode, setup_desktop)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
. "$SCRIPT_DIR/inc_install.sh"
die() { fail "$1"; exit 1; }

# --- Arguments ---------------------------------------------------------------
COPY_DATA=true
DEV_DIR=""
ASSUME_YES=false
for arg in "$@"; do
    case "$arg" in
        --no-data)    COPY_DATA=false ;;
        --yes|-y)     ASSUME_YES=true ;;
        -h|--help)
            grep -E '^# ' "$0" | sed 's/^# \{0,1\}//'
            exit 0 ;;
        --*) die "Option inconnue : $arg" ;;
        *)   DEV_DIR="$arg" ;;
    esac
done

EX_DIR="$(pwd)"
DEV_DIR="${DEV_DIR:-$HOME/Compta-dev}"
HUB_DIR="${COMPTA_HUB:-$HOME/Compta-hub/custom.git}"   # hub bare local (cas A.1)

# --- Helpers (read_mode/set_mode viennent de inc_install.sh) ------------------
git_clean() {  # 0 si l'arbre git $1 est propre
    [[ -z "$(git -C "$1" status --porcelain)" ]]
}

# --- Pré-checks --------------------------------------------------------------
echo "--- Pré-vérifications ---"

[[ -d "$EX_DIR/.git" ]]        || die "Dossier courant non-git : $EX_DIR"
[[ -f "$EX_DIR/config.ini" ]]  || die "config.ini absent dans $EX_DIR"

CUR_MODE="$(read_mode "$EX_DIR/config.ini")"
[[ "$CUR_MODE" == EX ]] || die "Le dossier courant doit être en mode EX (trouvé : '${CUR_MODE:-?}'). Le fork part d'une instance mixte."

[[ -e "$DEV_DIR" ]] && die "La cible existe déjà : $DEV_DIR"

git_clean "$EX_DIR" || die "Arbre PUB non propre ($EX_DIR) — commit/range avant de forker."

PUB_ORIGIN="$(git -C "$EX_DIR" remote get-url origin 2>/dev/null)" \
    || die "Pas d'origin PUB sur $EX_DIR"

# État PRV — taxonomie 0/B/A.1/A.2 (la même que tool_commit.sh/tool_pull.sh)
PRV_CASE="" PRV_ORIGIN="" PRV_PLAN=""
if [[ ! -d "$EX_DIR/custom" ]]; then
    PRV_CASE="0"
    PRV_PLAN="pas de custom/ — instance PUB seule"
elif [[ ! -e "$EX_DIR/custom/.git" ]]; then
    PRV_CASE="B"
    PRV_PLAN="custom/ non versionné — copie des fichiers"
else
    git_clean "$EX_DIR/custom" || die "Arbre PRV non propre ($EX_DIR/custom) — commit/range avant de forker."
    if PRV_ORIGIN="$(git -C "$EX_DIR/custom" remote get-url origin 2>/dev/null)"; then
        PRV_CASE="A.2"
        PRV_PLAN="clone distant depuis l'origin ($PRV_ORIGIN)"
    else
        PRV_CASE="A.1"
        PRV_PLAN="création hub bare local ($HUB_DIR) + rattachement des deux instances"
        [[ -e "$HUB_DIR" ]] && die "Hub cible déjà existant : $HUB_DIR (le rattacher à la main, ou \$COMPTA_HUB vers un autre chemin)"
    fi
fi

ok "Instance EX valide : $EX_DIR"
ok "Origin PUB : $PUB_ORIGIN"
ok "PRV (cas $PRV_CASE) : $PRV_PLAN"

# --- Confirmation ------------------------------------------------------------
echo
echo "Plan :"
echo "  • EX courant  : $EX_DIR   →  bascule en PROD (rouge, consommateur)"
echo "  • DEV nouveau : $DEV_DIR  (bleu) — données : $($COPY_DATA && echo "copiées (défaut)" || echo "vierges (--no-data)")"
echo "  • PRV         : cas $PRV_CASE — $PRV_PLAN"
echo
if ! $ASSUME_YES; then
    read -r -p "Confirmer le fork ? [o/N] " reply || reply=""
    [[ "$reply" == [oOyY] ]] || die "Annulé."
fi

# --- 1. Création du DEV (PUB : clone distant ; PRV : selon cas) --------------
echo
echo "--- Création DEV ---"
git clone "$PUB_ORIGIN" "$DEV_DIR"
ok "Clone PUB créé dans $DEV_DIR"

case "$PRV_CASE" in
    0)
        ok "PRV : pas de custom/ — rien à faire" ;;
    B)
        cp -Rp "$EX_DIR/custom" "$DEV_DIR/custom"
        ok "PRV : custom/ non versionné copié tel quel (sauvegarde à ta charge)" ;;
    A.1)
        mkdir -p "$(dirname "$HUB_DIR")"
        git clone --bare --quiet "$EX_DIR/custom" "$HUB_DIR"
        git -C "$HUB_DIR" remote remove origin 2>/dev/null || true   # un hub n'a pas d'amont
        git -C "$EX_DIR/custom" remote add origin "$HUB_DIR"
        PRV_BRANCH="$(git -C "$EX_DIR/custom" symbolic-ref --short HEAD)"
        git -C "$EX_DIR/custom" push --quiet -u origin "$PRV_BRANCH"  # no-op, pose le tracking
        git clone "$HUB_DIR" "$DEV_DIR/custom"
        ok "PRV : hub bare créé ($HUB_DIR), les deux custom/ rattachés (→ cas A.2)" ;;
    A.2)
        git clone "$PRV_ORIGIN" "$DEV_DIR/custom"
        ok "PRV : clone distant créé dans $DEV_DIR/custom" ;;
esac

# --- 2. config.ini + données du DEV -----------------------------------------
echo
echo "--- Configuration DEV ---"
if $COPY_DATA; then
    cp -p "$EX_DIR/config.ini" "$DEV_DIR/config.ini"
    [[ -f "$EX_DIR/comptes.xlsm" ]] && cp -p "$EX_DIR/comptes.xlsm" "$DEV_DIR/"
    for f in "$EX_DIR"/config_*; do
        [[ -e "$f" ]] && cp -p "$f" "$DEV_DIR/"
    done
    ok "Classeur + config* copiés depuis l'instance courante"
else
    if [[ -f "$DEV_DIR/config.ini.default" ]]; then
        cp "$DEV_DIR/config.ini.default" "$DEV_DIR/config.ini"
    fi
    [[ -f "$DEV_DIR/comptes_template.xlsm" ]] && cp "$DEV_DIR/comptes_template.xlsm" "$DEV_DIR/comptes.xlsm"
    ok "DEV vierge (config .default, classeur template, sans credentials)"
fi
set_mode "$DEV_DIR/config.ini" DEV
ok "Mode DEV forcé dans $DEV_DIR/config.ini"

# --- 3. Bascule EX → PROD ----------------------------------------------------
echo
echo "--- Bascule du dossier courant EX → PROD ---"
set_mode "$EX_DIR/config.ini" PROD
ok "Mode PROD forcé dans $EX_DIR/config.ini"

# --- 4. Raccourcis (desktop-only, sans réinstaller les deps) -----------------
echo
echo "--- Raccourcis ---"
setup_desktop "$DEV_DIR" DEV  || warn "Raccourci DEV à régénérer manuellement"
setup_desktop "$EX_DIR"  PROD || warn "Raccourci PROD à régénérer manuellement"

# --- Résumé ------------------------------------------------------------------
echo
ok "Fork terminé."
echo "  PROD (rouge) : $EX_DIR"
echo "  DEV  (bleu)  : $DEV_DIR"
[[ "$PRV_CASE" == A.1 ]] && echo "  Hub PRV      : $HUB_DIR (bare local — déplaçable plus tard via git remote set-url)"
echo
echo "Étapes éventuelles :"
echo "  • remote LAN secondaire de validation cross-platform (cf. Compta_topologie.md) ;"
echo "  • déclarer le nouveau DEV dans custom/topology.local.json (clé \"instances\")."
