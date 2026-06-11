#!/usr/bin/env python3
"""tool_render_upgrade_map.py — rend la carte (upgrade_map.json) en markdown.

Helper de release : la carte est la SOURCE unique ; ce script en dérive la
présentation doc (table des migrations) à coller dans Compta_upgrade.md. Garde
le doc aligné à la carte sans faire du doc la cible de parsing (#94 volet C).

Usage : ./tool_render_upgrade_map.py   (lit ./upgrade_map.json, imprime stdout)
"""

import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent


def main():
    try:
        cmap = json.loads((BASE / 'upgrade_map.json').read_text(encoding='utf-8'))
    except (OSError, ValueError) as e:
        print(f'✗ upgrade_map.json illisible : {e}', file=sys.stderr)
        return 1
    migs = sorted(cmap.get('migrations', []),
                  key=lambda m: (m['schema_from'], m.get('app_version', '')))
    if not migs:
        print('✗ carte vide', file=sys.stderr)
        return 1

    print('| Version | SCHEMA | Type | Outil | Effet |')
    print('|---|---|---|---|---|')
    for m in migs:
        if m['schema_to'] > m['schema_from']:
            trans = f"{m['schema_from']} → {m['schema_to']}"
            typ = 'structurel (bloquant)'
        else:
            trans = f"{m['schema_to']} (inchangé)"
            typ = 'catch-up (idempotent)'
        print(f"| v{m.get('app_version', '?')} | {trans} | {typ} "
              f"| `{m['tool']}` | {m.get('summary', '')} |")
    return 0


if __name__ == '__main__':
    sys.exit(main())
