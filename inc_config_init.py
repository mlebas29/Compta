"""Auto-création des fichiers de configuration utilisateur manquants.

Ces fichiers sont éditables par l'utilisateur et gitignored côté Export.
À la 1re exécution sur un clone vierge, ils sont créés vides pour ne pas
bloquer les imports des modules qui les lisent au module-level.
"""
from pathlib import Path
import json

_BASE_DIR = Path(__file__).parent

# Fichier → template minimal à créer si absent
_USER_CONFIGS = {
    'config_accounts.json': {},
    'config_cotations.json': {},
    'config_pipeline.json': {'linked_operations': {}, 'solde_auto': {}},
    'config_category_mappings.json': {},
}


def ensure_user_configs():
    """Crée les fichiers de config utilisateur manquants avec un template vide."""
    for filename, template in _USER_CONFIGS.items():
        path = _BASE_DIR / filename
        if not path.exists():
            path.write_text(
                json.dumps(template, indent=2, ensure_ascii=False) + '\n',
                encoding='utf-8',
            )


# Auto-exécution à l'import du module
ensure_user_configs()
