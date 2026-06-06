#!/bin/bash
# ============================================================================
# tool_fork.sh — Passage d'une instance mixte (EX) au dual (PROD + DEV)
#
# Lancé depuis la racine d'une instance EX (1 dossier, mixte) :
#   cd ~/Compta && ./tool_fork.sh [--data=keep|erase] [chemin-dev] [--yes]
#
# Effet :
#   1. crée une instance DEV par clone DISTANT (origin GitHub pour PUB,
#      origin du hub pour PRV custom/) ;
#   2. bascule le dossier courant EX → PROD (consommateur, thème rouge) ;
#   3. (re)génère les raccourcis des deux dossiers via install.sh --desktop-only.
#
# Données (classeur + config*) dans le DEV :
#   --data=keep  (défaut) : copiées depuis l'instance courante (bac à sable réel)
#   --data=erase          : DEV vierge (config depuis .default, classeur template)
#
# Le DEV est en mode DEV : la publication y est doublement bloquée (bouton masqué
# si mode≠PROD, et cpt.py --push refuse en DEV). Cf. Compta_extension.md § Dual.
# ============================================================================

set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✓${NC} $1"; }
warn() { echo -e "${YELLOW}⚠${NC} $1"; }
fail() { echo -e "${RED}✗${NC} $1" >&2; }
die()  { fail "$1"; exit 1; }

# --- Arguments ---------------------------------------------------------------
DATA=keep
DEV_DIR=""
ASSUME_YES=false
for arg in "$@"; do
    case "$arg" in
        --data=keep)  DATA=keep ;;
        --data=erase) DATA=erase ;;
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

# --- Helpers -----------------------------------------------------------------
read_mode() {  # lit et normalise le mode d'un config.ini ($1) ; '' si absent
    local f="$1" m
    [[ -f "$f" ]] || { echo ""; return; }
    m=$(grep -E '^[[:space:]]*mode[[:space:]]*=' "$f" | head -1 \
        | sed -E 's/.*=[[:space:]]*//; s/[[:space:]].*//' | tr 'a-z' 'A-Z')
    [[ "$m" == EXPORT ]] && m=EX        # compat legacy
    echo "$m"
}

set_mode() {  # force mode=$2 dans le config.ini $1
    local f="$1" mode="$2"
    if grep -qE '^[[:space:]]*mode[[:space:]]*=' "$f"; then
        sed -i.bak -E "s|^[[:space:]]*mode[[:space:]]*=.*|mode = $mode|" "$f" && rm -f "$f.bak"
    else
        printf 'mode = %s\n' "$mode" >> "$f"
    fi
}

git_clean() {  # 0 si l'arbre git $1 est propre
    [[ -z "$(git -C "$1" status --porcelain)" ]]
}

# --- Pré-checks --------------------------------------------------------------
echo "--- Pré-vérifications ---"

[[ -d "$EX_DIR/.git" ]]        || die "Dossier courant non-git : $EX_DIR"
[[ -d "$EX_DIR/custom/.git" ]] || die "PRV custom/ non-git : $EX_DIR/custom"
[[ -f "$EX_DIR/config.ini" ]]  || die "config.ini absent dans $EX_DIR"

CUR_MODE="$(read_mode "$EX_DIR/config.ini")"
[[ "$CUR_MODE" == EX ]] || die "Le dossier courant doit être en mode EX (trouvé : '${CUR_MODE:-?}'). Le fork part d'une instance mixte."

[[ -e "$DEV_DIR" ]] && die "La cible existe déjà : $DEV_DIR"

git_clean "$EX_DIR"        || die "Arbre PUB non propre ($EX_DIR) — commit/range avant de forker."
git_clean "$EX_DIR/custom" || die "Arbre PRV non propre ($EX_DIR/custom) — commit/range avant de forker."

PUB_ORIGIN="$(git -C "$EX_DIR" remote get-url origin 2>/dev/null)" \
    || die "Pas d'origin PUB sur $EX_DIR"
PRV_ORIGIN="$(git -C "$EX_DIR/custom" remote get-url origin 2>/dev/null)" \
    || die "Pas d'origin PRV sur $EX_DIR/custom"

ok "Instance EX valide : $EX_DIR"
ok "Origin PUB : $PUB_ORIGIN"
ok "Origin PRV : $PRV_ORIGIN"

# --- Confirmation ------------------------------------------------------------
echo
echo "Plan :"
echo "  • EX courant  : $EX_DIR   →  bascule en PROD (rouge, consommateur)"
echo "  • DEV nouveau : $DEV_DIR  (clone distant, bleu) — données : $DATA"
echo
if ! $ASSUME_YES; then
    read -r -p "Confirmer le fork ? [o/N] " reply || reply=""
    [[ "$reply" == [oOyY] ]] || die "Annulé."
fi

# --- 1. Clone distant du DEV -------------------------------------------------
echo
echo "--- Clone DEV (distant) ---"
git clone "$PUB_ORIGIN" "$DEV_DIR"
git clone "$PRV_ORIGIN" "$DEV_DIR/custom"
ok "Clones PUB + PRV créés dans $DEV_DIR"

# --- 2. config.ini + données du DEV -----------------------------------------
echo
echo "--- Configuration DEV (--data=$DATA) ---"
if [[ "$DATA" == keep ]]; then
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
( cd "$DEV_DIR" && ./install.sh --desktop-only ) || warn "Raccourci DEV à régénérer manuellement"
( cd "$EX_DIR"  && ./install.sh --desktop-only ) || warn "Raccourci PROD à régénérer manuellement"

# --- Résumé ------------------------------------------------------------------
echo
ok "Fork terminé."
echo "  PROD (rouge) : $EX_DIR"
echo "  DEV  (bleu)  : $DEV_DIR"
echo
echo "Étapes éventuelles :"
echo "  • remote LAN secondaire de validation cross-platform (cf. Compta_topologie.md) ;"
echo "  • déclarer le nouveau DEV dans custom/topology.local.json (clé \"instances\")."
