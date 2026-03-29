#!/usr/bin/env python3
"""
Module de détection et vérification du mode COMPTA (TEST ou PROD)

Logique de détection :
1. Si COMPTA_MODE définie → utiliser cette valeur
2. Sinon, détecter depuis le PATH du script :
   - ~/Compta/Claude → mode TEST
   - ~/Compta → mode PROD

Vérification de cohérence :
- Si COMPTA_MODE=prod mais PATH contient "Claude" → Erreur
- Si COMPTA_MODE=test mais PATH ne contient pas "Claude" → Avertissement
"""

import os
import sys
from pathlib import Path

# Variable globale pour éviter d'afficher plusieurs fois le warning Mode TEST
_test_warning_shown = False


def detect_mode_from_path(script_path=None):
    """
    Détecte le mode depuis le chemin du script

    Args:
        script_path: Chemin du script (ou None pour détecter automatiquement)

    Returns:
        'prod' si dans ~/Compta, 'test' si dans ~/Compta/Claude
    """
    if script_path is None:
        # Détecter depuis le script appelant
        script_path = Path(sys.argv[0]).resolve().parent
    else:
        script_path = Path(script_path).resolve()

    # Vérifier si on est dans Claude (TEST), Export ou Compta direct (PROD)
    # Convertir en string pour une recherche plus fiable
    path_str = str(script_path)

    if '/Compta/Claude' in path_str or '\\Compta\\Claude' in path_str:
        return 'test'
    elif '/Compta/Export' in path_str or '\\Compta\\Export' in path_str:
        return 'export'
    elif '/Compta' in path_str or '\\Compta' in path_str:
        return 'prod'
    else:
        # Par défaut, si le chemin est inconnu, supposer test
        return 'test'


def get_mode(verbose=False):
    """
    Détermine le mode COMPTA avec vérification de cohérence

    Logique :
    1. Variable d'environnement COMPTA_MODE (si définie et valide)
    2. Détection automatique depuis PATH du script
       - PROD (~/Compta) : transparent, aucun message
       - TEST (~/Compta/Claude) : avertissement dev si COMPTA_MODE non définie

    Vérification de cohérence :
    - Erreur bloquante si COMPTA_MODE=prod dans répertoire TEST

    Returns:
        str: 'prod' ou 'test'

    Raises:
        SystemExit: Si incohérence critique détectée
    """
    # Récupérer la variable d'environnement
    env_mode = os.environ.get('COMPTA_MODE', '').lower()

    # Détecter depuis le PATH
    path_mode = detect_mode_from_path()

    # Cas 1 : Variable d'environnement définie et valide
    if env_mode in ['prod', 'test', 'export']:
        # SÉCURITÉ : Vérifier cohérence avec le PATH
        if env_mode == 'prod' and path_mode == 'test':
            print("❌ ERREUR: Incohérence critique détectée !", file=sys.stderr)
            print(f"   COMPTA_MODE=prod mais script dans répertoire TEST (~/Compta/Claude)", file=sys.stderr)
            print("", file=sys.stderr)
            print("Solutions:", file=sys.stderr)
            print("  1. export COMPTA_MODE=test", file=sys.stderr)
            print("  2. Ou déployez vers PROD: cd ~/Compta/Claude && ./tool_deploy.py --to-prod", file=sys.stderr)
            sys.exit(1)

        if env_mode == 'test' and path_mode == 'prod':
            # Avertissement mineur (dev teste en PROD)
            if verbose:
                print("⚠️  COMPTA_MODE=test mais dans répertoire PROD", file=sys.stderr)

        if verbose:
            print(f"Mode: {env_mode} (depuis COMPTA_MODE)", file=sys.stderr)

        return env_mode

    # Cas 2 : Variable non définie → Détection automatique depuis PATH
    detected_mode = path_mode

    # Mode TEST/PROD détecté automatiquement, pas de message
    # (l'utilisateur peut vérifier avec `./inc_mode.py -v` si besoin)

    if verbose:
        print(f"Mode: {detected_mode} (détection automatique)", file=sys.stderr)

    return detected_mode


def get_base_dir(mode=None):
    """
    Retourne le répertoire de base selon le mode

    Args:
        mode: 'prod' ou 'test' (ou None pour détection automatique)

    Returns:
        Path: Chemin vers le répertoire de base
    """
    if mode is None:
        mode = get_mode()

    if mode == 'prod':
        return Path.home() / 'Compta'
    elif mode == 'export':
        return Path.home() / 'Compta' / 'Export'
    else:
        return Path.home() / 'Compta' / 'Claude'


def verify_environment(verbose=True):
    """
    Vérifie la cohérence complète de l'environnement

    Returns:
        dict: Informations sur l'environnement
    """
    mode = get_mode(verbose=False)
    base_dir = get_base_dir(mode)
    env_mode = os.environ.get('COMPTA_MODE', '(non définie)')
    path_mode = detect_mode_from_path()

    info = {
        'mode': mode,
        'base_dir': base_dir,
        'env_mode': env_mode,
        'path_mode': path_mode,
        'coherent': (env_mode == '(non définie)' or env_mode == mode)
    }

    if verbose:
        print("=" * 60)
        print("ENVIRONNEMENT COMPTA")
        print("=" * 60)
        print(f"Variable COMPTA_MODE: {env_mode}")
        print(f"Mode détecté (PATH): {path_mode}")
        print(f"Mode effectif: {mode}")
        print(f"Répertoire de base: {base_dir}")
        print(f"Cohérence: {'✓ OK' if info['coherent'] else '⚠️  Attention'}")
        print("=" * 60)

    return info


if __name__ == "__main__":
    """Afficher les informations de mode quand exécuté directement"""
    import argparse

    parser = argparse.ArgumentParser(
        description='Détecte et vérifie le mode COMPTA (TEST ou PROD)'
    )
    parser.add_argument('-v', '--verbose',
                        action='store_true',
                        help='Affichage détaillé')

    args = parser.parse_args()

    info = verify_environment(verbose=True)

    # Code de sortie selon cohérence
    sys.exit(0 if info['coherent'] else 1)
