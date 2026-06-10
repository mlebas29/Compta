#!/usr/bin/env python3
"""
Module de détection du mode COMPTA (DEV, PROD, EX)

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

# Canonique en MAJUSCULE : la valeur de config.ini = le label affiché = le terme
# de doc (un seul token). DEV/PROD = dual ; EX = mixte (ex-« export »).
VALID_MODES = {'DEV', 'PROD', 'EX'}

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
    if not mode:
        return None
    mode = mode.strip().upper()              # insensible à la casse en entrée
    return mode if mode in VALID_MODES else None


def detect_mode_from_path(script_path=None):
    """
    Détecte le mode depuis le chemin du script (fallback si config.ini absent).
    Vestigial depuis #87 (le mode vient de config.ini) ; gardé comme dernier
    recours et corrigé pour la convention découplée `~/Compta-dev`.

    Returns:
        'DEV' si dans ~/Compta-dev (ou ~/Compta/dev), 'PROD' si dans ~/Compta,
        'EX' sinon
    """
    if script_path is None:
        script_path = Path(sys.argv[0]).absolute().parent
    else:
        script_path = Path(script_path).absolute()

    path_str = str(script_path)

    # ~/Compta-dev (et l'ancien ~/Compta/dev nesté) → dev. À tester AVANT le
    # check '/Compta' (qui matcherait '/Compta-dev' comme substring → prod).
    if ('/Compta-dev' in path_str or '\\Compta-dev' in path_str
            or '/Compta/dev' in path_str or '\\Compta\\dev' in path_str):
        return 'DEV'
    elif '/Compta' in path_str or '\\Compta' in path_str:
        return 'PROD'
    else:
        return 'EX'


def get_mode(verbose=False, config_path=None):
    """
    Détermine le mode COMPTA.

    Priorité :
    1. config.ini [general] mode=
    2. Détection depuis PATH (rétrocompatibilité)

    Returns:
        str: 'DEV', 'PROD' ou 'EX'
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
    2. Mode 'PROD' / 'DEV' : auto-localisation = racine du clone qui exécute
       (inc_mode.py est à la racine). Découple l'emplacement du mode → PROD et DEV
       vivent à des chemins arbitraires, indépendants (ni emboîtés ni frères, cf. #87).
    3. Mode 'EX' / inconnu : répertoire du script (symlinks non résolus → sandbox-friendly)

    Returns:
        Path: Chemin vers le répertoire de base
    """
    env_dir = os.environ.get('COMPTA_BASE_DIR')
    if env_dir:
        return Path(env_dir)

    if mode is None:
        mode = get_mode()

    if mode in ('PROD', 'DEV'):
        # Racine du clone, auto-localisée via l'emplacement de ce module. Robuste
        # au point d'entrée, au cwd et aux fetchers custom/ (qui appellent
        # get_base_dir et dont sys.argv[0] pointerait dans custom/, pas la racine).
        return Path(__file__).resolve().parent

    # EX ou inconnu : répertoire du script (sans résoudre les symlinks → sandbox-friendly)
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
        description='Détecte et vérifie le mode COMPTA (DEV, PROD, EX)'
    )
    parser.add_argument('-v', '--verbose',
                        action='store_true',
                        help='Affichage détaillé')

    args = parser.parse_args()
    verify_environment(verbose=True)
