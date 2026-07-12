#!/usr/bin/env python3
"""
tool_migrate_config_cotations.py — dépollution de config_cotations.json (#118).

famille/décimales sont désormais lues du classeur (feuille Cotations,
COTfamille/COTdecimales) = source unique de vérité. Le JSON ne porte plus que
la route de fetch (source1/source2). Cette migration retire famille/décimales
des entrées existantes. Les entrées sont CONSERVÉES (même vides {}) : le JSON
reste le registre des codes de cotation + leurs routes de fetch (les codes
dérivés OrPr/AgPr/SAT… restent des {} ; famille/décimales vivent au classeur).

Auto-gated + idempotent : déclencheur = présence d'un champ famille/decimals ou
d'une entrée vide. No-op ensuite (un ré-ajout ultérieur via la GUI n'écrit que
les sources → jamais re-dépollué à tort). Cf. tool_migrate_config_xmr.py.

Usage: tool_migrate_config_cotations.py [config.ini]   (défaut: <base_dir>/config.ini)
       L'argument sert seulement à localiser le dossier ; la cible réelle est
       config_cotations.json du même répertoire (config_migrations passe config.ini).
"""

import sys
from pathlib import Path

_DROP_KEYS = ('famille', 'decimals')


def migrate(cot_path, dry_run=False):
    """Retire famille/décimales du JSON + supprime les entrées vides.

    `dry_run=True` : DÉTECTE sans écrire (sonde effective-state #121).
    Retourne True si une modification a eu (aurait) lieu, False sinon (no-op)."""
    path = Path(cot_path)
    if not path.exists():
        return False
    from inc_config_io import read_cotations_json, write_cotations_json
    data = read_cotations_json(path)
    if not isinstance(data, dict):
        return False

    changed = False
    cleaned = {}
    for code, entry in data.items():
        if not isinstance(entry, dict):
            cleaned[code] = entry
            continue
        new_entry = {k: v for k, v in entry.items() if k not in _DROP_KEYS}
        if new_entry != entry:
            changed = True
        # Entrée conservée même vide ({}) : registre des codes (+ routes de fetch)
        cleaned[code] = new_entry

    if not changed:
        return False
    if dry_run:
        return True
    write_cotations_json(path, cleaned)
    return True


def main():
    argv = sys.argv[1:]
    dry = '--dry-run' in argv
    pos = [a for a in argv if not a.startswith('--')]
    if pos:
        cot_path = Path(pos[0]).resolve().parent / 'config_cotations.json'
    else:
        import inc_mode
        cot_path = inc_mode.get_base_dir() / 'config_cotations.json'

    # Sonde effective-state (#121) : rc 3 = dépolluerait / 0 = déjà dépollué, sans écrire.
    if dry:
        return 3 if migrate(cot_path, dry_run=True) else 0

    if migrate(cot_path):
        print('✓ config_cotations.json dépollué (famille/décimales → classeur ; entrées conservées)')
    else:
        print('✓ config_cotations.json déjà dépollué (rien à migrer)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
