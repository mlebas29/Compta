#!/bin/bash
# install_custom.sh — Mise en place de custom/ (DEV + PROD)
#
# Cf. Compta_tools.md pour la spec complète, Compta_custom.md pour la doctrine.
#
# Comble la différence entre l'arborescence cible et l'état initial.

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

PROD_DIR="$HOME/Compta"
DEV_DIR="$HOME/Compta/dev"
DEV_CUSTOM="$DEV_DIR/custom"
PROD_CUSTOM="$PROD_DIR/custom"

usage() {
    cat <<EOF
install_custom.sh — Mise en place de custom/ (DEV + PROD)

Usage:
  ./install_custom.sh                          # statut (diff cible/réel)
  ./install_custom.sh --git                    # init .git PRV dans dev/custom/
  ./install_custom.sh --git --remote <url>     # idem + remote PRV
  ./install_custom.sh --remote <url>           # ajoute remote à .git PRV existant
  ./install_custom.sh --py=<NAME>              # squelettes cpt_fetch_<NAME>.py / cpt_format_<NAME>.py
  ./install_custom.sh -h | --help

Comble la différence entre l'arborescence cible (Compta_custom.md) et l'état
réel. Gestes idempotents enchaînés selon les flags :
  1. Créer ~/Compta/dev/ si absent (git clone de l'origin PROD)
  2. Créer ~/Compta/dev/custom/ si absent
  3. Init .git PRV (si --git et .git absent)
  4. Configurer remote PRV (si --remote)
  5. Poser squelettes (si --py=NAME)
  6. Commit initial DEV custom (si étape 3 ou 5 a créé)
  7. Créer ~/Compta/custom/ si absent (clone file:// ou rsync selon mode)

Exécution depuis $PROD_DIR uniquement.
EOF
    exit 0
}

# --- Parse args ---
DO_GIT=false
REMOTE_URL=""
PY_NAME=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--help)  usage ;;
        --git)      DO_GIT=true; shift ;;
        --remote)   REMOTE_URL="$2"; shift 2 ;;
        --remote=*) REMOTE_URL="${1#--remote=}"; shift ;;
        --py=*)     PY_NAME="${1#--py=}"; shift ;;
        --py)
            echo -e "${RED}✗${NC} --py exige une valeur (--py=NOM)"
            exit 1 ;;
        *)
            echo -e "${RED}✗${NC} Argument inconnu : $1"
            exit 1 ;;
    esac
done

# --- Vérifier cwd ---
if [[ "$PWD" != "$PROD_DIR" ]]; then
    echo -e "${RED}✗${NC} Exécuter depuis $PROD_DIR (cwd actuel : $PWD)"
    exit 1
fi

# --- Vérifier PY_NAME format ---
if [[ -n "$PY_NAME" ]]; then
    if [[ ! "$PY_NAME" =~ ^[A-Za-z][A-Za-z0-9_]*$ ]]; then
        echo -e "${RED}✗${NC} --py=$PY_NAME : nom invalide (attendu [A-Za-z][A-Za-z0-9_]*)"
        exit 1
    fi
fi

# --- Détection de l'état ---
HAS_DEV=false
HAS_DEV_CUSTOM=false
HAS_PRV_GIT=false
HAS_PRV_REMOTE=false
PRV_REMOTE_URL=""
HAS_PROD_CUSTOM=false
ORIGIN_URL=""

[[ -d "$DEV_DIR" ]]        && HAS_DEV=true
[[ -d "$DEV_CUSTOM" ]]     && HAS_DEV_CUSTOM=true
[[ -d "$DEV_CUSTOM/.git" ]] && HAS_PRV_GIT=true
[[ -d "$PROD_CUSTOM" ]]    && HAS_PROD_CUSTOM=true

if $HAS_PRV_GIT; then
    PRV_REMOTE_URL=$(git -C "$DEV_CUSTOM" remote get-url origin 2>/dev/null || true)
    [[ -n "$PRV_REMOTE_URL" ]] && HAS_PRV_REMOTE=true
fi

ORIGIN_URL=$(git -C "$PROD_DIR" remote get-url origin 2>/dev/null || true)

# --- Validation flags ---
if [[ -n "$REMOTE_URL" ]] && ! $DO_GIT && ! $HAS_PRV_GIT; then
    echo -e "${RED}✗${NC} --remote sans --git : exige un .git PRV existant ($DEV_CUSTOM/.git absent)"
    exit 1
fi

if [[ -n "$REMOTE_URL" ]] && $HAS_PRV_REMOTE; then
    if [[ "$PRV_REMOTE_URL" == "$REMOTE_URL" ]]; then
        :  # idempotent — même URL, sera signalé plus bas
    else
        echo -e "${RED}✗${NC} --remote : remote déjà configuré ($PRV_REMOTE_URL) ; pour le changer, faire 'git -C $DEV_CUSTOM remote set-url origin <url>' manuellement"
        exit 1
    fi
fi

# --- Détection mode (cible) ---
# 0 / B / A (=A.1 ou A.2 selon REMOTE_URL)
# La cible est paramétrée par les flags + l'état actuel
target_mode() {
    if $DO_GIT || $HAS_PRV_GIT; then
        if [[ -n "$REMOTE_URL" ]] || $HAS_PRV_REMOTE; then
            echo "A.2"
        else
            echo "A.1"
        fi
    elif $HAS_DEV_CUSTOM || [[ -n "$PY_NAME" ]]; then
        echo "B"
    else
        echo "0"
    fi
}

# --- Statut (sans flag d'action) ---
status() {
    echo -e "${BLUE}État de l'arborescence custom :${NC}"
    echo
    if $HAS_DEV; then
        echo -e "  ${GREEN}✓${NC} ~/Compta/dev/"
    else
        echo -e "  ${RED}✗${NC} ~/Compta/dev/                       (absent)"
    fi
    if $HAS_DEV_CUSTOM; then
        echo -e "  ${GREEN}✓${NC} ~/Compta/dev/custom/"
    else
        echo -e "  ${RED}✗${NC} ~/Compta/dev/custom/                (absent)"
    fi
    if $HAS_PRV_GIT; then
        if $HAS_PRV_REMOTE; then
            echo -e "  ${GREEN}✓${NC} ~/Compta/dev/custom/.git/           (remote: $PRV_REMOTE_URL)"
        else
            echo -e "  ${GREEN}✓${NC} ~/Compta/dev/custom/.git/           (sans remote)"
        fi
    else
        echo -e "  ${YELLOW}—${NC} ~/Compta/dev/custom/.git/           (absent — option B ou non installé)"
    fi
    if $HAS_PROD_CUSTOM; then
        echo -e "  ${GREEN}✓${NC} ~/Compta/custom/"
    else
        echo -e "  ${RED}✗${NC} ~/Compta/custom/                    (absent)"
    fi
    echo

    if $HAS_DEV_CUSTOM; then
        local fetches formats patches
        fetches=$(ls "$DEV_CUSTOM"/cpt_fetch_*.py 2>/dev/null | sed 's|.*/cpt_fetch_||; s|\.py$||' | tr '\n' ' ')
        formats=$(ls "$DEV_CUSTOM"/cpt_format_*.py 2>/dev/null | sed 's|.*/cpt_format_||; s|\.py$||' | tr '\n' ' ')
        patches=$(ls "$DEV_CUSTOM"/patch_*.py 2>/dev/null | sed 's|.*/patch_||; s|\.py$||' | tr '\n' ' ')
        echo -e "${BLUE}Modules dans dev/custom/ :${NC}"
        echo "  fetchers : ${fetches:-aucun}"
        echo "  formats  : ${formats:-aucun}"
        echo "  patches  : ${patches:-aucun}"
        echo
    fi

    echo -e "${BLUE}Mode actuel :${NC} $(target_mode)"
    echo

    # Suggestions
    if ! $HAS_DEV || ! $HAS_DEV_CUSTOM; then
        echo -e "${YELLOW}À faire :${NC}"
        echo "  ./install_custom.sh --git --py=<NAME>           # cas A.1 + 1er site"
        echo "  ./install_custom.sh --git --remote <url> --py=<NAME>   # cas A.2 + 1er site"
        echo "  ./install_custom.sh --py=<NAME>                 # cas B (sans .git PRV)"
    fi
}

# --- Helpers ---

skel_dir() {
    [[ ! -d "$DEV_CUSTOM/.gitignore" ]] || true   # noop
}

write_skel_fetch() {
    local name="$1"
    local lower="${name,,}"
    local capitalized="${lower^}"
    local dest="$DEV_CUSTOM/cpt_fetch_${name}.py"
    cat > "$dest" <<'EOF'
from inc_fetch import BaseFetcher, fetch_main


class __CLASS__Fetcher(BaseFetcher):
    def __init__(self, verbose=False):
        super().__init__(caller_file=__file__, verbose=verbose)

    def run(self):
        # TODO : navigation, téléchargement, dépôt dans dropbox/__NAME__/
        pass


if __name__ == '__main__':
    fetch_main(__CLASS__Fetcher, description='Fetch __NAME__')
EOF
    sed -i "s/__CLASS__/${capitalized}/g; s/__NAME__/${name}/g" "$dest"
}

write_skel_format() {
    local name="$1"
    local lower="${name,,}"
    local dest="$DEV_CUSTOM/cpt_format_${name}.py"
    cat > "$dest" <<'EOF'
from inc_format import site_name_from_file


SITE = site_name_from_file(__file__)  # → '__NAME__'

EXPECTED_FILES = [
    # ('__LOWER___operations.csv', 'exact', '1'),
    # ('__LOWER___supports_*.xlsx', 'glob', '0+'),
]

DESCRIPTION = """__NAME__ — description courte du site.

══════ Configuration ══════
TODO : portefeuilles, comptes, devises.

══════ 2FA ══════
TODO : méthode de 2FA.
"""

# Optionnel : limite stricte de comptes (absent = illimité)
# MAX_ACCOUNTS = 4


def process_operations(file_path):
    # TODO : parsing → liste d'opérations
    raise NotImplementedError
EOF
    sed -i "s/__NAME__/${name}/g; s/__LOWER__/${lower}/g" "$dest"
}

write_prv_gitignore() {
    cat > "$DEV_CUSTOM/.gitignore" <<'EOF'
__pycache__/
*.pyc
*.bak
*.bak_*

# Sandboxes TNR jetables
tests/tnr/*/sandbox/
EOF
}

# --- Logique principale ---

# Sans flag → statut
if ! $DO_GIT && [[ -z "$REMOTE_URL" && -z "$PY_NAME" ]]; then
    status
    exit 0
fi

# Pré-condition : origin PROD requis pour cloner DEV (geste 1)
if ! $HAS_DEV; then
    if [[ -z "$ORIGIN_URL" ]]; then
        echo -e "${RED}✗${NC} ~/Compta/dev/ absent et impossible de déterminer l'URL de clone PUB"
        echo "  PROD doit être un clone git ; (ré)installer via 'git clone <url>' (cf. README §3)"
        exit 1
    fi
fi

PRV_GIT_CREATED=false
SKELS_CREATED=false

# Geste 1 — Créer DEV
if ! $HAS_DEV; then
    echo -e "${YELLOW}--- 1. Création ~/Compta/dev/ ---${NC}"
    echo "  git clone $ORIGIN_URL $DEV_DIR"
    git clone "$ORIGIN_URL" "$DEV_DIR"
    HAS_DEV=true
    echo -e "${GREEN}✓${NC} ~/Compta/dev/ créé"
    echo
else
    echo -e "${GREEN}✓${NC} ~/Compta/dev/ déjà présent — sauté"
fi

# Geste 2 — Créer DEV custom
if ! $HAS_DEV_CUSTOM; then
    echo -e "${YELLOW}--- 2. Création ~/Compta/dev/custom/ ---${NC}"
    mkdir -p "$DEV_CUSTOM"
    HAS_DEV_CUSTOM=true
    echo -e "${GREEN}✓${NC} ~/Compta/dev/custom/ créé"
    echo
else
    echo -e "${GREEN}✓${NC} ~/Compta/dev/custom/ déjà présent — sauté"
fi

# Geste 3 — Init .git PRV
if $DO_GIT; then
    if ! $HAS_PRV_GIT; then
        echo -e "${YELLOW}--- 3. Init .git PRV ---${NC}"
        git -C "$DEV_CUSTOM" init -q
        write_prv_gitignore
        HAS_PRV_GIT=true
        PRV_GIT_CREATED=true
        echo -e "${GREEN}✓${NC} .git PRV initialisé + .gitignore posé"
        echo
    else
        echo -e "${GREEN}✓${NC} .git PRV déjà présent — sauté"
    fi
fi

# Geste 4 — Configurer remote PRV
if [[ -n "$REMOTE_URL" ]]; then
    if ! $HAS_PRV_REMOTE; then
        echo -e "${YELLOW}--- 4. Configurer remote PRV ---${NC}"
        git -C "$DEV_CUSTOM" remote add origin "$REMOTE_URL"
        HAS_PRV_REMOTE=true
        PRV_REMOTE_URL="$REMOTE_URL"
        echo -e "${GREEN}✓${NC} remote PRV : $REMOTE_URL"
        echo
    else
        echo -e "${GREEN}✓${NC} remote PRV déjà configuré ($PRV_REMOTE_URL) — sauté"
    fi
fi

# Geste 5 — Poser squelettes
if [[ -n "$PY_NAME" ]]; then
    fetch_file="$DEV_CUSTOM/cpt_fetch_${PY_NAME}.py"
    format_file="$DEV_CUSTOM/cpt_format_${PY_NAME}.py"
    posed=false
    echo -e "${YELLOW}--- 5. Squelettes cpt_*_${PY_NAME}.py ---${NC}"
    if [[ -f "$fetch_file" ]]; then
        echo "  cpt_fetch_${PY_NAME}.py déjà présent — sauté"
    else
        write_skel_fetch "$PY_NAME"
        echo -e "${GREEN}✓${NC} $fetch_file"
        posed=true
    fi
    if [[ -f "$format_file" ]]; then
        echo "  cpt_format_${PY_NAME}.py déjà présent — sauté"
    else
        write_skel_format "$PY_NAME"
        echo -e "${GREEN}✓${NC} $format_file"
        posed=true
    fi
    $posed && SKELS_CREATED=true
    echo
fi

# Geste 6 — Commit initial DEV custom (seulement si init .git vient d'être fait)
if $PRV_GIT_CREATED; then
    echo -e "${YELLOW}--- 6. Commit initial DEV custom ---${NC}"
    cd "$DEV_CUSTOM"
    git add -A
    if [[ -n $(git diff --cached --name-only) ]]; then
        git commit -q -m "Init custom/"
        echo -e "${GREEN}✓${NC} Commit initial créé"
    else
        echo "  Rien à commiter (custom/ vide)"
    fi
    cd "$PROD_DIR"
    echo
fi

# Geste 7 — Créer PROD custom
if ! $HAS_PROD_CUSTOM; then
    # Vérifier que DEV custom n'est pas vide
    if [[ -z "$(ls -A "$DEV_CUSTOM" 2>/dev/null)" ]]; then
        echo -e "${YELLOW}—${NC} ~/Compta/custom/ : DEV custom vide, propagation sautée"
    elif $HAS_PRV_GIT; then
        # Mode A : clone file://
        # Vérifier qu'il y a au moins un commit
        if git -C "$DEV_CUSTOM" rev-parse HEAD >/dev/null 2>&1; then
            echo -e "${YELLOW}--- 7. Création ~/Compta/custom/ (clone file://) ---${NC}"
            git clone -q "file://$DEV_CUSTOM" "$PROD_CUSTOM"
            HAS_PROD_CUSTOM=true
            echo -e "${GREEN}✓${NC} ~/Compta/custom/ cloné depuis DEV"
            echo
        else
            echo -e "${YELLOW}—${NC} ~/Compta/custom/ : DEV custom sans commit, propagation sautée"
            echo "  → faire 'tool_commit.sh \"Init custom/\"' puis relancer install_custom.sh"
        fi
    else
        # Mode B : rsync
        echo -e "${YELLOW}--- 7. Création ~/Compta/custom/ (rsync, mode B) ---${NC}"
        rsync -a "$DEV_CUSTOM/" "$PROD_CUSTOM/"
        HAS_PROD_CUSTOM=true
        echo -e "${GREEN}✓${NC} ~/Compta/custom/ copié depuis DEV"
        echo
    fi
else
    echo -e "${GREEN}✓${NC} ~/Compta/custom/ déjà présent — sauté"
    if $SKELS_CREATED && ! $PRV_GIT_CREATED; then
        echo "  → squelettes posés en DEV ; lancer 'tool_commit.sh \"...\"' puis 'tool_pull.sh' pour propager"
    fi
fi
