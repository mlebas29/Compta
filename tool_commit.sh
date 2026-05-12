#!/bin/bash
# tool_commit.sh — Commit DEV (PUB et/ou PRV) avec routage automatique
#
# Cf. Compta_tools.md pour la spec complète, Compta_custom.md pour la doctrine.
#
# Routage automatique :
#   - Fichiers sous custom/  → .git PRV
#   - Tout le reste            → .git PUB

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

DEV_DIR="$PWD"
PRV_DIR="$PWD/custom"
CO_AUTHOR="Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"

usage() {
    cat <<EOF
tool_commit.sh — Commit DEV (PUB et/ou PRV)

Usage:
  tool_commit.sh "message"                   # commit local (PUB + PRV selon mode)
  tool_commit.sh "message" --push            # commit + push (PUB → github ; PRV → remote si configuré)
  tool_commit.sh "message" --push --tag vX   # commit + push + tag PUB
  tool_commit.sh "message" --pub             # restreint PUB
  tool_commit.sh "message" --prv             # restreint PRV
  tool_commit.sh --status                    # affichage état (pas de commit)
  tool_commit.sh -h | --help

Détection auto du mode (lecture du filesystem) :
  - pas de custom/         → cas 0  (PUB seul)
  - custom/ sans .git      → cas B  (PUB seul, PRV signalé sans .git)
  - custom/.git sans remote → cas A.1 (PUB push, PRV commit local)
  - custom/.git avec remote → cas A.2 (PUB et PRV push)

Tag : --tag taggue PUB uniquement (jamais PRV) et implique --push.
Non trackés : avertissement, pas d'auto-add (utiliser git add explicite).

Exécution depuis la racine d'un clone Compta (cwd-relatif).
EOF
    exit 0
}

# --- Détection du mode ---
detect_mode() {
    if [[ ! -d "$PRV_DIR" ]]; then
        echo "0"
    elif [[ ! -d "$PRV_DIR/.git" ]]; then
        echo "B"
    elif [[ -z $(git -C "$PRV_DIR" remote 2>/dev/null) ]]; then
        echo "A1"
    else
        echo "A2"
    fi
}

# --- Parse args ---
MSG=""
PUSH=false
TAG=""
TARGET="ALL"          # ALL | PUB | PRV
STATUS_ONLY=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--help)  usage ;;
        --status)   STATUS_ONLY=true; shift ;;
        --push)     PUSH=true; shift ;;
        --tag)      TAG="$2"; PUSH=true; shift 2 ;;
        --pub)
            [[ "$TARGET" != "ALL" ]] && { echo -e "${RED}✗${NC} --pub et --prv exclusifs"; exit 1; }
            TARGET="PUB"; shift ;;
        --prv)
            [[ "$TARGET" != "ALL" ]] && { echo -e "${RED}✗${NC} --pub et --prv exclusifs"; exit 1; }
            TARGET="PRV"; shift ;;
        -*)
            echo -e "${RED}✗${NC} Flag inconnu : $1"
            exit 1 ;;
        *)
            [[ -n "$MSG" ]] && { echo -e "${RED}✗${NC} Un seul argument positionnel (message)"; exit 1; }
            MSG="$1"; shift ;;
    esac
done

# --- Vérifier cwd (racine d'un clone Compta) ---
if [[ ! -f "$PWD/cpt_update.py" || ! -f "$PWD/inc_mode.py" ]]; then
    echo -e "${RED}✗${NC} Exécuter depuis la racine d'un clone Compta (cwd actuel : $PWD)"
    exit 1
fi

MODE=$(detect_mode)

# --- Cohérence args ---
if $STATUS_ONLY; then
    if [[ -n "$MSG" || $PUSH == true || -n "$TAG" ]]; then
        echo -e "${RED}✗${NC} --status est exclusif (pas de message, --push, --tag)"
        exit 1
    fi
else
    if [[ -z "$MSG" ]]; then
        echo -e "${RED}✗${NC} Message obligatoire (ou --status pour afficher l'état)"
        exit 1
    fi
fi

# PRV demandé explicitement mais indisponible
if [[ "$TARGET" == "PRV" && ( "$MODE" == "0" || "$MODE" == "B" ) ]]; then
    case "$MODE" in
        0) echo -e "${RED}✗${NC} --prv impossible : pas de custom/" ;;
        B) echo -e "${RED}✗${NC} --prv impossible : option B (custom/ sans .git)" ;;
    esac
    exit 1
fi

# --- Helpers ---

_show_changes() {
    local dir="$1"
    local filter="$2"
    cd "$dir"
    local untracked modified staged
    if [[ -n "$filter" ]]; then
        untracked=$(git ls-files --others --exclude-standard 2>/dev/null | grep -v "$filter" || true)
    else
        untracked=$(git ls-files --others --exclude-standard 2>/dev/null || true)
    fi
    modified=$(git diff --name-only 2>/dev/null || true)
    staged=$(git diff --cached --name-only 2>/dev/null || true)
    if [[ -z "$untracked" && -z "$modified" && -z "$staged" ]]; then
        echo "  Rien à signaler."
    else
        [[ -n "$staged" ]]    && { echo "  Staged :";     echo "$staged"    | sed 's/^/    /'; }
        [[ -n "$modified" ]]  && { echo "  Modifié :";    echo "$modified"  | sed 's/^/    /'; }
        [[ -n "$untracked" ]] && { echo "  Non tracké :"; echo "$untracked" | sed 's/^/    /'; }
    fi
}

status_pub() {
    echo -e "${YELLOW}--- PUB (.git racine) ---${NC}"
    _show_changes "$DEV_DIR" '^custom/'
    cd "$DEV_DIR"
    local ahead
    ahead=$(git rev-list @{u}..HEAD --count 2>/dev/null || echo 0)
    if [[ "$ahead" -gt 0 ]]; then
        echo "  ⤴ $ahead commit(s) à pousser :"
        git log --oneline @{u}..HEAD 2>/dev/null | sed 's/^/    /'
    fi
}

status_prv() {
    echo -e "${YELLOW}--- PRV (.git custom/) ---${NC}"
    case "$MODE" in
        0) echo "  Pas de custom/ (cas 0)" ; return ;;
        B) echo "  custom/ sans .git (option B — propagation manuelle)" ; return ;;
    esac
    _show_changes "$PRV_DIR" ''
    cd "$PRV_DIR"
    if [[ "$MODE" == "A2" ]]; then
        local ahead
        ahead=$(git rev-list @{u}..HEAD --count 2>/dev/null || echo 0)
        if [[ "$ahead" -gt 0 ]]; then
            echo "  ⤴ $ahead commit(s) à pousser :"
            git log --oneline @{u}..HEAD 2>/dev/null | sed 's/^/    /'
        fi
    fi
}

_do_commit() {
    local dir="$1"
    local label="$2"
    local filter="$3"
    cd "$dir"
    local untracked
    if [[ -n "$filter" ]]; then
        untracked=$(git ls-files --others --exclude-standard 2>/dev/null | grep -v "$filter" || true)
    else
        untracked=$(git ls-files --others --exclude-standard 2>/dev/null || true)
    fi
    if [[ -n "$untracked" ]]; then
        echo -e "${YELLOW}⚠${NC} Non trackés $label (ignorés par ce commit) :"
        echo "$untracked" | sed 's/^/    /'
        echo "  → git add <fichier> pour inclure"
    fi
    git add -u
    if [[ -n $(git diff --cached --name-only) ]]; then
        local commit_msg="$MSG"
        [[ "$label" == "PUB" ]] && commit_msg="$MSG

$CO_AUTHOR"
        git commit -m "$commit_msg"
        echo -e "${GREEN}✓${NC} $label commité"
        return 0
    else
        echo "  $label : rien à commiter"
        return 1
    fi
}

commit_pub() {
    echo -e "${YELLOW}--- PUB ---${NC}"
    _do_commit "$DEV_DIR" "PUB" '^custom/' || true
}

commit_prv() {
    echo -e "${YELLOW}--- PRV ---${NC}"
    case "$MODE" in
        0) echo "  Pas de custom/ (cas 0) — sauté." ; return ;;
        B) echo "  custom/ sans .git (option B) — sauté." ; return ;;
    esac
    _do_commit "$PRV_DIR" "PRV" '' || true
}

push_pub() {
    cd "$DEV_DIR"
    echo -e "${YELLOW}--- Push PUB ---${NC}"
    git push
    [[ -n "$TAG" ]] && git push origin "$TAG"
    echo -e "${GREEN}✓${NC} PUB poussé"
}

push_prv() {
    case "$MODE" in
        0|B|A1)
            [[ "$MODE" == "A1" ]] && echo "  PRV : pas de remote configuré — push sauté."
            return ;;
    esac
    cd "$PRV_DIR"
    echo -e "${YELLOW}--- Push PRV ---${NC}"
    git push
    echo -e "${GREEN}✓${NC} PRV poussé"
}

tag_pub() {
    cd "$DEV_DIR"
    git tag -a "$TAG" -m "$MSG"
    echo -e "${GREEN}✓${NC} PUB tagué $TAG"
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

# Commit
case "$TARGET" in
    ALL) commit_pub; echo; commit_prv ;;
    PUB) commit_pub ;;
    PRV) commit_prv ;;
esac

# Tag (PUB uniquement, après commit)
if [[ -n "$TAG" ]]; then
    if [[ "$TARGET" == "PRV" ]]; then
        echo "  ⚠ --tag ignoré (cible PRV)"
    else
        tag_pub
    fi
fi

# Push
if $PUSH; then
    echo
    case "$TARGET" in
        ALL) push_pub; push_prv ;;
        PUB) push_pub ;;
        PRV) push_prv ;;
    esac
fi
