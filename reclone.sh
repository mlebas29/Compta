#!/usr/bin/env bash
#
# reclone.sh — Re-clone sûr d'une instance après une réécriture d'historique du dépôt.
#
# Après une version marquée 🔄 dans le CHANGELOG (réécriture d'historique git, ex. v5.1.0),
# un « git pull » classique échoue (historiques sans ancêtre commun). Ce script re-clone
# proprement en préservant tes fichiers privés.
#
# Sans --yes : DRY-RUN (montre le plan, n'altère rien).
#
# Instance bloquée qui n'a jamais reçu ce script (a raté la mise à jour avant la réécriture) :
#   curl -fsSL https://raw.githubusercontent.com/mlebas29/Compta/main/reclone.sh -o /tmp/reclone.sh
#   bash /tmp/reclone.sh --reclone --repo ~/Compta/dev --yes
#
set -euo pipefail

MODE=""; REPO_DIR=""; DO_IT=0; REMOTE="origin"

usage() {
  cat <<'EOF'
Usage :
  reclone.sh --reclone [--repo DIR] [--yes]

Sans --yes : DRY-RUN (n'altère rien).

--reclone : re-clone sûr d'une instance après une réécriture d'historique.
            Sauvegarde le dossier ENTIER (mv, instantané), clone frais, puis restaure les
            fichiers gitignorés/non-trackés (config*, comptes.xlsm, custom/, dropbox/…).
            Les modifs de code TRACKÉ ne sont PAS auto-restaurées (historique réécrit) :
            elles restent dans la sauvegarde, à ré-appliquer à la main.
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --reclone) MODE="reclone" ;;
    --repo)    REPO_DIR="${2:?--repo requiert un chemin}"; shift ;;
    --yes)     DO_IT=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Argument inconnu : $1" >&2; usage; exit 1 ;;
  esac
  shift
done
[ -n "$MODE" ] || { usage; exit 0; }

if [ -z "$REPO_DIR" ]; then
  REPO_DIR="$(git rev-parse --show-toplevel 2>/dev/null || echo "$HOME/Compta/dev")"
fi
REPO_DIR="$(cd "$REPO_DIR" && pwd)"
[ -d "$REPO_DIR/.git" ] || { echo "✗ $REPO_DIR n'est pas un dépôt git" >&2; exit 1; }

say()     { printf '%s\n' "$*"; }
run()     { if [ "$DO_IT" = 1 ]; then eval "$@"; else say "  [dry-run] $*"; fi; }
confirm() { [ "$DO_IT" = 1 ] || return 0; read -r -p "$1 [tape 'oui'] " a; [ "$a" = oui ] || { echo Abandon.; exit 1; }; }

URL="$(git -C "$REPO_DIR" remote get-url "$REMOTE")"
BR="$(git -C "$REPO_DIR" branch --show-current)"
TS="$(date +%Y%m%d_%H%M%S)"
backup="${REPO_DIR}.backup-${TS}"

say "Repo   : $REPO_DIR"
say "Remote : $REMOTE → $URL   (branche $BR)"
[ -z "$(git -C "$REPO_DIR" status --porcelain || true)" ] \
  || say "⚠  Working tree NON propre — tes modifs seront dans la sauvegarde."
[ -z "$(git -C "$REPO_DIR" log --oneline "$REMOTE/$BR..HEAD" 2>/dev/null || true)" ] \
  || say "⚠  Commits locaux NON poussés — dans la sauvegarde (.git), à ré-appliquer."
[ "$DO_IT" = 1 ] || say "(DRY-RUN — relance avec --yes pour exécuter)"
say ""
say "Plan :"
say "  1. git clone (frais) dans ${REPO_DIR}.new"
say "  2. mv $REPO_DIR → $backup   (sauvegarde COMPLÈTE)"
say "  3. mv ${REPO_DIR}.new → $REPO_DIR"
say "  4. restaurer fichiers privés/non-trackés depuis la sauvegarde"
confirm "Re-cloner $REPO_DIR ?"
run "git clone \"$URL\" \"${REPO_DIR}.new\""
run "mv \"$REPO_DIR\" \"$backup\""
run "mv \"${REPO_DIR}.new\" \"$REPO_DIR\""
# Restaure le privé/non-tracké, SAUF docs/site_BG.md (relique du rename BG→ORCHESTRA :
# le doc privé vit désormais dans custom/site_ORCHESTRA.md, ne pas le ré-injecter dans le PUB).
run "rsync -a --ignore-existing --exclude='.git/' --exclude='docs/site_BG.md' \"$backup\"/ \"$REPO_DIR\"/"
say ""
say "✓ Re-clone fait. Sauvegarde conservée : $backup (supprime-la quand validé)."
say "  (si lancé depuis l'intérieur du repo : 'cd $REPO_DIR' pour revenir dans le clone frais.)"
