#!/bin/bash
# tool_pull.sh — Pull PROD (PUB et/ou PRV) avec détection auto du mode
#
# Cf. Compta_tools.md pour la spec complète, Compta_extension.md pour la doctrine.

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

PROD_DIR="$PWD"
PROD_PRV_DIR="$PWD/custom"

usage() {
    cat <<EOF
tool_pull.sh — Pull PROD (PUB et/ou PRV)

Usage:
  tool_pull.sh                               # pull PUB + PRV (selon mode)
  tool_pull.sh --pub                         # restreint PUB
  tool_pull.sh --prv                         # restreint PRV
  tool_pull.sh --status                      # affichage état (pas de pull)
  tool_pull.sh -h | --help

Détection auto du mode (lecture du filesystem) :
  - pas de custom/         → cas 0  (PUB seul)
  - custom/ sans .git      → cas B  (PUB seul, --prv erreur)
  - custom/.git sans remote → cas A.1 (pull PRV depuis file:// source)
  - custom/.git avec remote → cas A.2 (pull PRV depuis remote)

Si un pull échoue, l'autre est tenté quand même.
Codes retour : 0 succès, 1 échec d'au moins un pull.

Exécution depuis la racine d'un clone Compta (cwd-relatif).
EOF
    exit 0
}

# --- Détection du mode ---
detect_mode() {
    if [[ ! -d "$PROD_PRV_DIR" ]]; then
        echo "0"
    elif [[ ! -d "$PROD_PRV_DIR/.git" ]]; then
        echo "B"
    elif [[ -z $(git -C "$PROD_PRV_DIR" remote 2>/dev/null) ]]; then
        echo "A1"
    else
        echo "A2"
    fi
}

# --- Parse args ---
TARGET="ALL"          # ALL | PUB | PRV
STATUS_ONLY=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--help)  usage ;;
        --status)   STATUS_ONLY=true; shift ;;
        --pub)
            [[ "$TARGET" != "ALL" ]] && { echo -e "${RED}✗${NC} --pub et --prv exclusifs"; exit 1; }
            TARGET="PUB"; shift ;;
        --prv)
            [[ "$TARGET" != "ALL" ]] && { echo -e "${RED}✗${NC} --pub et --prv exclusifs"; exit 1; }
            TARGET="PRV"; shift ;;
        *)
            echo -e "${RED}✗${NC} Argument inconnu : $1"
            exit 1 ;;
    esac
done

# --- Vérifier cwd (racine d'un clone Compta) ---
if [[ ! -f "$PWD/cpt_update.py" || ! -f "$PWD/inc_mode.py" ]]; then
    echo -e "${RED}✗${NC} Exécuter depuis la racine d'un clone Compta (cwd actuel : $PWD)"
    exit 1
fi

MODE=$(detect_mode)

# PRV demandé explicitement mais indisponible
if [[ "$TARGET" == "PRV" && ( "$MODE" == "0" || "$MODE" == "B" ) ]]; then
    case "$MODE" in
        0) echo -e "${RED}✗${NC} --prv impossible : pas de custom/" ;;
        B) echo -e "${RED}✗${NC} --prv impossible : option B (custom/ sans .git, propagation manuelle)" ;;
    esac
    exit 1
fi

# --- Helpers ---

_status_one() {
    local dir="$1"
    cd "$dir"
    git fetch origin --quiet 2>/dev/null || { echo "  (fetch échoué)"; return; }
    local behind
    behind=$(git rev-list HEAD..origin/main --count 2>/dev/null || echo 0)
    if [[ "$behind" -gt 0 ]]; then
        echo "  ⤵ $behind commit(s) en attente :"
        git log --oneline HEAD..origin/main 2>/dev/null | sed 's/^/    /'
    else
        echo "  À jour."
    fi
}

status_pub() {
    echo -e "${YELLOW}--- Status PUB (~/Compta/) ---${NC}"
    _status_one "$PROD_DIR"
}

status_prv() {
    echo -e "${YELLOW}--- Status PRV (~/Compta/custom/) ---${NC}"
    case "$MODE" in
        0) echo "  Pas de custom/ (cas 0)" ; return ;;
        B) echo "  custom/ sans .git (option B — propagation manuelle)" ; return ;;
    esac
    _status_one "$PROD_PRV_DIR"
}

_pull_one() {
    local dir="$1"
    local label="$2"
    cd "$dir"
    if git pull; then
        echo -e "${GREEN}✓${NC} $label pulled"
        return 0
    else
        echo -e "${RED}✗${NC} $label pull failed"
        return 1
    fi
}

pull_pub() {
    echo -e "${YELLOW}--- Pull PUB ---${NC}"
    _pull_one "$PROD_DIR" "PUB"
}

pull_prv() {
    echo -e "${YELLOW}--- Pull PRV ---${NC}"
    case "$MODE" in
        0) echo "  Pas de custom/ (cas 0) — sauté." ; return 0 ;;
        B) echo "  custom/ sans .git (option B) — propagation manuelle requise." ; return 0 ;;
    esac
    _pull_one "$PROD_PRV_DIR" "PRV"
}

# --- Logique principale ---

# Status
if $STATUS_ONLY; then
    case "$TARGET" in
        ALL) status_pub; echo; status_prv ;;
        PUB) status_pub ;;
        PRV) status_prv ;;
    esac
    exit 0
fi

# Pull
fail=0
case "$TARGET" in
    ALL)
        pull_pub || fail=1
        echo
        pull_prv || fail=1
        ;;
    PUB)
        pull_pub || fail=1
        ;;
    PRV)
        pull_prv || fail=1
        ;;
esac

exit $fail
