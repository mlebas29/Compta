"""inc_bootstrap.py — Charge les extensions privées au démarrage.

Mécanisme du framework `private/` (cf. Compta_fusion.md, section
« Chargement dynamique du private/ »). Si un dossier `private/` existe
à côté du code public :

1. `private/` est ajouté à `sys.path` → les modules `cpt_fetch_<NAME>.py`
   et `cpt_format_<NAME>.py` privés deviennent importables comme s'ils
   étaient à la racine (cas A — sites privés via glob discovery).

2. Tous les `private/patch_*.py` sont importés dans l'ordre alphabétique
   — chacun monkeypatche le code public pour une extension ponctuelle
   (cas B — ex: SYNOE dans SOCGEN, item de menu, etc.).

Le code métier (`cpt_*`, `gui_*`) ne mentionne jamais `private/`. Ce module
est l'unique trace publique du framework, importé indirectement via
`inc_mode` (chargé par tous les points d'entrée).
"""
import sys
import importlib
from pathlib import Path

_BASE = Path(__file__).parent
_PRIVATE = _BASE / 'private'

if _PRIVATE.is_dir():
    if str(_PRIVATE) not in sys.path:
        sys.path.insert(0, str(_PRIVATE))
    for _patch in sorted(_PRIVATE.glob('patch_*.py')):
        importlib.import_module(_patch.stem)
