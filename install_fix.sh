#!/bin/bash
# ============================================================================
# install_fix.sh — Pose le mode et/ou régénère le raccourci d'un clone Compta,
# sans réinstaller les dépendances (réparation / changement de mode léger).
#
#   cd <racine du clone> && ./install_fix.sh [EX|PROD|DEV]
#
#   sans argument : régénère le raccourci selon le mode de config.ini (réparation)
#   avec un mode  : écrit mode= dans config.ini + régénère le raccourci
#
# Complément léger d'install.sh (qui, lui, ne gère plus le mode) : utile après
# un correctif du lanceur, un raccourci cassé, ou pour changer le mode d'un clone.
# ============================================================================

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
. "$SCRIPT_DIR/inc_install.sh"

[[ "${1:-}" == -h || "${1:-}" == --help ]] && { grep -E '^# ' "$0" | sed 's/^# \{0,1\}//'; exit 0; }

[[ -f cpt_gui.py ]] || { fail "Pas un clone Compta (cpt_gui.py absent dans $(pwd))"; exit 1; }

# Migre les clés legacy d'un config.ini préexistant (export→EX, seafile→classeur).
[[ -f config.ini ]] && normalize_config config.ini

mode=""
if [[ -n "${1:-}" ]]; then
    mode=$(printf '%s' "$1" | tr 'a-z' 'A-Z')
    case "$mode" in
        DEV|PROD|EX) ;;
        *) fail "Mode invalide : '$1' (attendu : DEV | PROD | EX)"; exit 1 ;;
    esac
fi

if [[ -n "$mode" ]]; then
    [[ -f config.ini ]] || { fail "config.ini absent — lance d'abord ./install.sh"; exit 1; }
    set_mode config.ini "$mode"
    ok "Mode défini dans config.ini : $mode"
else
    mode=$(read_mode config.ini)
    mode=${mode:-EX}
fi

setup_desktop "$(pwd)" "$mode"
ok "Raccourci régénéré (mode $mode)"
