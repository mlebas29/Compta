#!/usr/bin/env python3
"""
Module de détection du mode COMPTA (dev, prod, export)

Logique de détection :
1. Si config.ini contient mode= dans [general] → utiliser cette valeur
2. Sinon, détection depuis le PATH du script (rétrocompatibilité)
"""

import configparser
import sys
from pathlib import Path

VALID_MODES = {'dev', 'prod', 'export'}

# Variable globale pour éviter d'afficher plusieurs fois le warning
_test_warning_shown = False


def _read_mode_from_config(config_path=None):
    """Lit le mode depuis config.ini [general] mode=."""
    if config_path is None:
        config_path = Path(sys.argv[0]).resolve().parent / 'config.ini'
    else:
        config_path = Path(config_path)

    if not config_path.exists():
        return None

    config = configparser.ConfigParser()
    config.read(config_path)
    mode = config.get('general', 'mode', fallback=None)
    if mode and mode.strip().lower() in VALID_MODES:
        return mode.strip().lower()
    return None


def detect_mode_from_path(script_path=None):
    """
    Détecte le mode depuis le chemin du script (rétrocompatibilité).

    Returns:
        'prod' si dans ~/Compta, 'dev' si dans ~/Compta/Claude,
        'export' si dans ~/Compta/Export
    """
    if script_path is None:
        script_path = Path(sys.argv[0]).resolve().parent
    else:
        script_path = Path(script_path).resolve()

    path_str = str(script_path)

    if '/Compta/Claude' in path_str or '\\Compta\\Claude' in path_str:
        return 'dev'
    elif '/Compta/Export' in path_str or '\\Compta\\Export' in path_str:
        return 'export'
    elif '/Compta' in path_str or '\\Compta' in path_str:
        return 'prod'
    else:
        return 'export'


def get_mode(verbose=False, config_path=None):
    """
    Détermine le mode COMPTA.

    Priorité :
    1. config.ini [general] mode=
    2. Détection depuis PATH (rétrocompatibilité)

    Returns:
        str: 'dev', 'prod' ou 'export'
    """
    # 1. config.ini
    mode = _read_mode_from_config(config_path)
    if mode:
        if verbose:
            print(f"Mode: {mode} (depuis config.ini)", file=sys.stderr)
        return mode

    # 2. Détection PATH
    detected = detect_mode_from_path()
    if verbose:
        print(f"Mode: {detected} (détection automatique)", file=sys.stderr)
    return detected


def get_base_dir(mode=None):
    """
    Retourne le répertoire de base selon le mode.

    Returns:
        Path: Chemin vers le répertoire de base
    """
    if mode is None:
        mode = get_mode()

    if mode == 'prod':
        return Path.home() / 'Compta'
    elif mode == 'dev':
        return Path.home() / 'Compta' / 'Claude'
    else:
        # export ou inconnu : répertoire du script
        return Path(sys.argv[0]).resolve().parent


def verify_environment(verbose=True):
    """
    Vérifie la cohérence complète de l'environnement.

    Returns:
        dict: Informations sur l'environnement
    """
    mode = get_mode(verbose=False)
    base_dir = get_base_dir(mode)

    info = {
        'mode': mode,
        'base_dir': base_dir,
    }

    if verbose:
        print("=" * 60)
        print("ENVIRONNEMENT COMPTA")
        print("=" * 60)
        print(f"Mode: {mode}")
        print(f"Répertoire: {base_dir}")
        print("=" * 60)

    return info


if __name__ == "__main__":
    """Afficher les informations de mode quand exécuté directement"""
    import argparse

    parser = argparse.ArgumentParser(
        description='Détecte et vérifie le mode COMPTA (dev, prod, export)'
    )
    parser.add_argument('-v', '--verbose',
                        action='store_true',
                        help='Affichage détaillé')

    args = parser.parse_args()
    verify_environment(verbose=True)
