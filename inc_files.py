#!/usr/bin/env python3
"""
Utilitaires pour la gestion des fichiers (nommage, doublons)
"""

from pathlib import Path


def get_unique_path(target_path):
    """
    Retourne un chemin unique en ajoutant #N si le fichier existe déjà.

    Args:
        target_path: Path ou str du fichier cible

    Returns:
        Path: chemin unique (original si n'existe pas, sinon avec #N)

    Examples:
        get_unique_path("export.csv")      -> "export.csv" (si n'existe pas)
        get_unique_path("export.csv")      -> "export#2.csv" (si export.csv existe)
        get_unique_path("export.csv")      -> "export#3.csv" (si #2 existe aussi)
        get_unique_path("rapport.pdf")     -> "rapport#2.pdf"
    """
    target_path = Path(target_path)

    if not target_path.exists():
        return target_path

    # Séparer nom et extension
    stem = target_path.stem
    suffix = target_path.suffix
    parent = target_path.parent

    # Chercher le prochain numéro disponible
    n = 2
    while True:
        new_path = parent / f"{stem}#{n}{suffix}"
        if not new_path.exists():
            return new_path
        n += 1


def move_with_unique_name(source_path, dest_dir):
    """
    Déplace un fichier vers un répertoire en gérant les doublons.

    Args:
        source_path: Path du fichier source
        dest_dir: Path du répertoire destination

    Returns:
        Path: chemin final du fichier déplacé
    """
    source_path = Path(source_path)
    dest_dir = Path(dest_dir)

    target_path = dest_dir / source_path.name
    unique_path = get_unique_path(target_path)

    source_path.rename(unique_path)
    return unique_path
