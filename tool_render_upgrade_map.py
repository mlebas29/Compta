#!/usr/bin/env python3
"""tool_render_upgrade_map.py — rend la carte (upgrade_map.json) en markdown.

UNE source, deux objectifs : pilotage (install_upgrade) ET description (doc).
Ce script sert le second : il dérive UNE vue PAR MODE d'usage, pour son doc.

  • --mode assiste (défaut) → Compta_install_upgrade.md (geste `install_upgrade`)
  • --mode classeur          → Compta_upgrade.md (récupérer le nouvel exemple)

Deux axes INDÉPENDANTS portés par `badges_legend` :
  • `perimetre` (classeur/config/app) = la SECTION du rendu.
  • `geste` = la mode-applicabilité (clés présentes = modes où le badge est
    actionnable) + l'instruction par mode.
Ainsi 🔧 (périmètre classeur, geste assisté seul) n'apparaît qu'en assisté : en
mode classeur on ne migre pas en place, on récupère le nouvel exemple (📘). Seul
📘 est dual-mode. La description ne porte ni schéma ni outil ni idempotence
(notions de pilotage) ; install_upgrade les lit dans le JSON. La légende est
cohérente avec l'usage (seuls les badges présents y figurent) ; frontière
`_install_upgrade_since` : un geste `assiste_avant` (🔄) rend le manuel d'époque.

Usage : ./tool_render_upgrade_map.py [--mode assiste|classeur]
"""

import argparse
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent

PERIMETRES = [('classeur', 'Classeur (structure & contenu)'),
              ('config', 'Config'),
              ('app', 'Dépôt (git)')]

# Glossaire des natures — surfacé dans la vue ASSISTÉE seulement (la nature décrit
# le rapport d'install_upgrade au badge ; en classeur 📘 est l'action, pas un info).
NATURE_GLOSS = {
    'cumulatif': '`install_upgrade` rattrape le retard accumulé',
    'ponctuel': 'à traiter au moment (pas de rattrapage)',
    'informatif': 'aucune action',
}


def _pv(s):
    """'5.3.0' -> (5, 3, 0) ; tolère les segments non numériques."""
    out = []
    for part in str(s or '').split('.'):
        try:
            out.append(int(part))
        except ValueError:
            break
    return tuple(out)


def _modes_of(badge_def):
    g = badge_def.get('geste', {})
    modes = set()
    if 'assiste' in g or 'assiste_avant' in g:
        modes.add('assiste')
    if 'classeur' in g:
        modes.add('classeur')
    return modes


def _gesture(badge_def, mode, used_versions, frontier):
    """Geste d'un badge pour `mode`. En assisté, applique la frontière d'époque :
    si toutes les occurrences sont antérieures à install_upgrade et que le badge
    a un `assiste_avant`, on rend le geste manuel d'époque."""
    g = badge_def.get('geste', {})
    if mode == 'assiste' and 'assiste_avant' in g and used_versions \
            and all(v < frontier for v in used_versions):
        return g['assiste_avant']
    return g.get(mode)


def render_legend(legend, used, mode, frontier, badge_versions):
    shown = []
    for e in legend:                              # ordre canonique de la carte
        b = e['badge']
        if b not in used:
            continue
        geste = _gesture(e, mode, badge_versions.get(b, []), frontier)
        if geste:
            shown.append((e, geste))
    if not shown:
        return []
    out = [f'**Légende des badges** (geste en mode {mode}) :', '']
    if mode == 'assiste':                         # glossaire des natures présentes
        natures = []
        for e, _ in shown:
            n = e.get('nature')
            if n and n not in natures:
                natures.append(n)
        if natures:
            out += ['> ' + ' · '.join(f'*{n}* = {NATURE_GLOSS.get(n, n)}' for n in natures), '']
    for e, geste in shown:
        tag = f"*({e['nature']})* " if mode == 'assiste' and e.get('nature') else ''
        out.append(f"- {e['badge']} {tag}{e.get('label', '')} — {geste}")
    return out


def render_section(label, entries, mode_badges):
    out = [f'### {label}', '', '| Version | Badges | Effet |', '|---|---|---|']
    for e in entries:
        cell = ' '.join(b for b in (e.get('badges') or []) if b in mode_badges) or '—'
        out.append(f"| v{e.get('app_version', '?')} | {cell} | {e.get('summary', '')} |")
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--mode', choices=['assiste', 'classeur'], default='assiste',
                    help="mode d'usage rendu (défaut : assiste)")
    args = ap.parse_args()

    try:
        cmap = json.loads((BASE / 'upgrade_map.json').read_text(encoding='utf-8'))
    except (OSError, ValueError) as e:
        print(f'✗ upgrade_map.json illisible : {e}', file=sys.stderr)
        return 1
    if not cmap.get('migrations'):
        print('✗ carte vide', file=sys.stderr)
        return 1
    legend = cmap.get('badges_legend', [])
    mode = args.mode
    frontier = _pv(cmap.get('_install_upgrade_since', '0'))

    badge_perim = {e['badge']: e.get('perimetre') for e in legend}
    mode_badges = {e['badge'] for e in legend if mode in _modes_of(e)}
    entries = list(cmap.get('migrations', [])) + list(cmap.get('actions', []))

    # usage (∩ mode) pour la légende + versions par badge (frontière)
    used, badge_versions = set(), {}
    for e in entries:
        v = _pv(e.get('app_version'))
        for b in set(e.get('badges') or []) & mode_badges:
            used.add(b)
            badge_versions.setdefault(b, []).append(v)

    lines = render_legend(legend, used, mode, frontier, badge_versions)
    for perim, label in PERIMETRES:
        sect = sorted(
            (e for e in entries
             if any(badge_perim.get(b) == perim and b in mode_badges
                    for b in (e.get('badges') or []))),
            key=lambda e: _pv(e.get('app_version')))
        if sect:
            lines += [''] + render_section(label, sect, mode_badges)
    print('\n'.join(lines))
    return 0


if __name__ == '__main__':
    sys.exit(main())
