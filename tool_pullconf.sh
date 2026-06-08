#!/bin/bash
# ============================================================================
# tool_pullconf.sh — Rapatrie la config per-instance (non versionnée) depuis une
# autre machine Compta, pour amorcer un nouveau clone.
#
# Famille provisioning : git transporte le CODE ; reclone.sh restaure le local
# non-tracké d'une MÊME machine ; ce script transporte la CONFIG (+ classeur)
# vers une NOUVELLE machine. Liste des fichiers = $CONFIG_FILES (inc_install.sh).
#
#   tool_pullconf.sh <source> [--path DIR] [--dry-run]
#
#     <source>   adresse SSH (user@host) de la machine qui détient la config
#     --path     chemin de l'instance distante (défaut : Compta, relatif au
#                $HOME distant ; un chemin absolu marche aussi)
#     --dry-run  liste seulement les fichiers présents côté source, n'applique rien
#
# Transport par FLUX (tar | ssh) : aucun fichier sensible (credentials, classeur)
# n'est matérialisé sur le disque distant ni nettoyé après. Applique par défaut
# sur le clone courant (cwd = racine d'une instance Compta), en sauvegardant tout
# fichier existant en <f>.bak-<horodatage> avant de l'écraser.
#
# Pré-requis : clé SSH enrôlée vers <source> ; tar des deux côtés.
# ============================================================================
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
. "$SCRIPT_DIR/inc_install.sh"

# Affiche le bloc d'en-tête (lignes # contiguës après le shebang), sans le corps.
usage() { awk 'NR==1{next} /^#/{sub(/^# ?/,"");print;next} {exit}' "$0"; }

SRC=""; RPATH="Compta"; DRY=0
while [ $# -gt 0 ]; do
    case "$1" in
        --path)    RPATH="${2:?--path requiert un chemin}"; shift ;;
        --dry-run) DRY=1 ;;
        -h|--help) usage; exit 0 ;;
        -*)        fail "Option inconnue : $1"; exit 1 ;;
        *)         [ -z "$SRC" ] && SRC="$1" || { fail "Source déjà fournie ($SRC)"; exit 1; } ;;
    esac
    shift
done

[ -n "$SRC" ] || { fail "Source SSH manquante."; usage; exit 1; }

# Joignabilité SSH (fail-loud avant tout transfert).
ssh -o BatchMode=yes -o ConnectTimeout=8 "$SRC" true 2>/dev/null \
    || { fail "SSH injoignable : $SRC (clé enrôlée ? hôte allumé ?)"; exit 1; }

# Liste des fichiers RÉELLEMENT présents côté source (tolère les absents).
# '|| true' : la commande distante finit sur un test faux si le dernier fichier
# est absent (exit 1) — sans ça, set -e tuerait l'assignation. La joignabilité
# SSH ayant déjà été vérifiée, un présent vide = pas de config (pas un échec SSH).
present=$(ssh -T "$SRC" "cd \"$RPATH\" 2>/dev/null && for f in $CONFIG_FILES; do [ -e \"\$f\" ] && printf '%s\n' \"\$f\"; done") || true

if [ "$DRY" = 1 ]; then
    echo "Config sur $SRC:$RPATH :"
    for f in $CONFIG_FILES; do
        if printf '%s\n' "$present" | grep -qxF "$f"; then ok "$f"; else warn "$f (absent)"; fi
    done
    exit 0
fi

[ -n "$present" ] || { fail "Aucun fichier de config présent dans $SRC:$RPATH"; exit 1; }
[ -f cpt_gui.py ] || { fail "Pas une racine d'instance Compta (cpt_gui.py absent dans $(pwd))"; exit 1; }

# Transport par flux des seuls fichiers présents.
# 'tar xm' : n'applique PAS les mtimes de l'archive → évite l'avortement sur un
# simple warning d'horloge désynchronisée entre machines ("timestamp in the
# future"), exit-code 1 fréquent que pipefail prendrait pour un échec. Le verdict
# se fait sur la COMPLÉTUDE (tous les présents ont atterri), plus fiable que le
# code de sortie de tar face aux warnings bénins — un flux tronqué (ssh coupé)
# laisse des fichiers manquants et est donc bien détecté.
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
# $present non-quoté → newlines aplatis en espaces (sinon ils survivent dans la
# chaîne double-quote envoyée à ssh et coupent la commande tar en deux).
ssh -T "$SRC" "cd \"$RPATH\" && COPYFILE_DISABLE=1 tar cf - $(echo $present) 2>/dev/null" \
    | tar xmf - -C "$tmp" || true

missing=""
while IFS= read -r f; do
    [ -n "$f" ] && { [ -e "$tmp/$f" ] || missing="$missing $f"; }
done <<EOF
$present
EOF
[ -z "$missing" ] || { fail "Transfert incomplet — manquant(s) :$missing"; exit 1; }

# Application avec sauvegarde des existants.
ts=$(date +%Y%m%d_%H%M%S); n=0
while IFS= read -r -d '' f; do
    rel="${f#"$tmp"/}"
    [ -e "$rel" ] && { cp -a "$rel" "$rel.bak-$ts"; warn "sauvegardé : $rel → $rel.bak-$ts"; }
    mkdir -p "$(dirname "$rel")"
    cp -a "$f" "$rel"
    ok "appliqué : $rel"
    n=$((n + 1))
done < <(find "$tmp" -type f -print0)

ok "$n fichier(s) de config transféré(s) depuis $SRC."
