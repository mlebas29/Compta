#!/usr/bin/env python3
"""tool_render_upgrade_map.py — rend la carte (upgrade_map.json) en markdown.

UNE source, deux objectifs : pilotage (upgrade) ET description (doc).
Ce script sert le second : il dérive UNE vue PAR MODE d'usage, pour son doc.

  • --mode assiste (défaut) → Compta_upgrade_assiste.md (geste `upgrade`)
  • --mode classeur          → Compta_upgrade_classeur.md (récupérer le nouvel exemple)

Deux axes INDÉPENDANTS portés par `badges_legend` :
  • `perimetre` (classeur/config/app) = la SECTION du rendu.
  • `geste` = la mode-applicabilité (clés présentes = modes où le badge est
    actionnable) + l'instruction par mode.
Ainsi 🔧 (périmètre classeur, geste assisté seul) n'apparaît qu'en assisté : en
mode classeur on ne migre pas en place, on récupère le nouvel exemple (📘). Seul
📘 est dual-mode. La description ne porte ni schéma ni outil ni idempotence
(notions de pilotage) ; upgrade les lit dans le JSON. La légende est
cohérente avec l'usage (seuls les badges présents y figurent).

Usage : ./tool_render_upgrade_map.py [--mode assiste|classeur]
"""

import argparse
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent

# axe : (clé périmètre, entête de colonne courte, description longue pour la légende)
PERIMETRES = [('classeur', 'Classeur', 'structure & contenu'),
              ('config', 'Config', "paramètres privés de l'app"),
              ('app', 'App', 'code public (dépôt git)')]

# Glossaire des natures — surfacé dans la vue ASSISTÉE seulement (la nature décrit
# le rapport d'upgrade au badge ; en classeur 📘 est l'action, pas un info).
NATURE_GLOSS = {
    'cumulatif': '`upgrade` rattrape le retard accumulé',
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
    if 'assiste' in g:
        modes.add('assiste')
    if 'classeur' in g:
        modes.add('classeur')
    return modes


def _gesture(badge_def, mode):
    """Geste d'un badge pour `mode` (None si le badge n'agit pas dans ce mode)."""
    return badge_def.get('geste', {}).get(mode)


def render_legend(legend, used, mode):
    shown = []
    for e in legend:                              # ordre canonique de la carte
        b = e['badge']
        if b not in used:
            continue
        geste = _gesture(e, mode)
        if geste:
            shown.append((e, geste))
    if not shown:
        return []
    out = ['**Légende des badges** :', '']
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


def _entry_axis(e, badge_perim):
    """Axe (périmètre) d'une entrée : périmètre explicite, sinon celui de son
    premier badge porteur de périmètre (les marqueurs comme 🧱 n'en ont pas)."""
    if e.get('perimetre'):
        return e['perimetre']
    for b in (e.get('badges') or []):
        if badge_perim.get(b):
            return badge_perim[b]
    return None


def _cell_badges(e, perim, mode_badges, badge_perim, e_axis):
    """Badges de `e` à afficher dans la colonne `perim` : badge porté par ce
    périmètre, OU marqueur (sans périmètre propre) si l'axe de l'entrée = perim."""
    out = [b for b in (e.get('badges') or [])
           if b in mode_badges
           and (badge_perim.get(b) == perim
                or (badge_perim.get(b) is None and e_axis == perim))]
    return ' '.join(out)


def render_matrix(rows, active, mode_badges, badge_perim, show_tool):
    """Tableau unique chronologique (récent d'abord) : Version × axes [+ Outil] + Effet.
    `active` = [(clé, entête, desc)] des axes ayant au moins un badge en ce mode.
    `show_tool` ajoute la colonne Outil (ce que `upgrade` lance — vue assistée)."""
    ncol = len(active)
    head = ['Version'] + [s for _, s, _ in active] + (['Outil'] if show_tool else []) + ['Effet']
    sep = ['---'] + [':--:'] * ncol + (['---'] if show_tool else []) + ['---']
    out = ['| ' + ' | '.join(head) + ' |', '|' + '|'.join(sep) + '|']
    for e in rows:
        e_axis = _entry_axis(e, badge_perim)
        ver = e.get('version_label') or f"v{e.get('app_version', '?')}"
        row = [ver] + [_cell_badges(e, k, mode_badges, badge_perim, e_axis) for k, _, _ in active]
        if show_tool:
            tool = e.get('tool') or ''
            row.append(f'`{tool}`' if tool else '')
        row.append(e.get('summary', ''))
        out.append('| ' + ' | '.join(row) + ' |')
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
    badge_perim = {e['badge']: e.get('perimetre') for e in legend}
    mode_badges = {e['badge'] for e in legend if mode in _modes_of(e)}
    entries = (list(cmap.get('migrations', []))
               + list(cmap.get('config_migrations', []))
               + list(cmap.get('actions', [])))

    # badges réellement utilisés en ce mode → légende
    used = set()
    for e in entries:
        used |= set(e.get('badges') or []) & mode_badges

    lines = render_legend(legend, used, mode)

    # axes ayant au moins un badge en ce mode = colonnes du tableau (≥1 en classeur)
    active = [p for p in PERIMETRES if any(
        _cell_badges(e, p[0], mode_badges, badge_perim, _entry_axis(e, badge_perim))
        for e in entries)]
    if active:
        rows = sorted(
            (e for e in entries
             if any(b in mode_badges for b in (e.get('badges') or []))),
            key=lambda e: _pv(e.get('app_version')), reverse=True)
        # colonne Outil = notion du geste `upgrade` → vue assistée seule
        # (en classeur on récupère l'exemple, sans outil)
        assiste = mode == 'assiste'
        if len(active) > 1:                       # caption des axes utile en multi-axes seulement
            lines += ['', '_Axes : ' + ' · '.join(f'**{s}** = {d}' for _, s, d in active) + '_']
        lines += [''] + render_matrix(rows, active, mode_badges, badge_perim, assiste)
    print('\n'.join(lines))
    return 0


if __name__ == '__main__':
    sys.exit(main())
