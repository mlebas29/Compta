#!/usr/bin/env python3
"""
Module de détection du mode COMPTA (dev, prod, export)

Logique de détection :
1. Si config.ini contient mode= dans [general] → utiliser cette valeur
2. Sinon, détection depuis le PATH du script (rétrocompatibilité)
"""

import configparser
import os
import sys
from pathlib import Path

# Chargement opportuniste des extensions privées (cf. Compta_fusion.md).
# inc_mode est importé par tous les points d'entrée → 1 seul endroit suffit.
import inc_bootstrap  # noqa: F401  — side-effect : sys.path + patches privés

VALID_MODES = {'dev', 'prod', 'export'}

# Variable globale pour éviter d'afficher plusieurs fois le warning
_test_warning_shown = False


def _read_mode_from_config(config_path=None):
    """Lit le mode depuis config.ini [general] mode=."""
    if config_path is None:
        config_path = Path(sys.argv[0]).absolute().parent / 'config.ini'
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
    Détecte le mode depuis le chemin du script (fallback si config.ini absent).

    Returns:
        'dev' si dans ~/Compta/dev, 'prod' si dans ~/Compta, 'export' sinon
    """
    if script_path is None:
        script_path = Path(sys.argv[0]).absolute().parent
    else:
        script_path = Path(script_path).absolute()

    path_str = str(script_path)

    if '/Compta/dev' in path_str or '\\Compta\\dev' in path_str:
        return 'dev'
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

    Priorité :
    1. Variable d'environnement COMPTA_BASE_DIR (override absolu — sandbox, install custom)
    2. Mode 'prod' → ~/Compta, 'dev' → ~/Compta/dev (defaults usuels)
    3. Fallback : répertoire du script (mode 'export' / inconnu)

    Returns:
        Path: Chemin vers le répertoire de base
    """
    env_dir = os.environ.get('COMPTA_BASE_DIR')
    if env_dir:
        return Path(env_dir)

    if mode is None:
        mode = get_mode()

    if mode == 'prod':
        return Path.home() / 'Compta'
    elif mode == 'dev':
        return Path.home() / 'Compta' / 'dev'
    else:
        # export ou inconnu : répertoire du script (sans résoudre les symlinks → sandbox-friendly)
        return Path(sys.argv[0]).absolute().parent


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
