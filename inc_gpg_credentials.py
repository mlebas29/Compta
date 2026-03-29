#!/usr/bin/env python3
"""
Module pour lire les credentials depuis un fichier GPG
Format supporté: tableau Markdown avec colonnes | ID | login | password |
"""

import subprocess
from pathlib import Path
from typing import Tuple, Optional


def get_credentials_from_gpg(
    gpg_file: Path,
    credential_id: str,
    verbose: bool = True
) -> Tuple[Optional[str], Optional[str]]:
    """
    Lit les credentials depuis un fichier GPG chiffré
    
    Args:
        gpg_file: Chemin vers le fichier .gpg
        credential_id: Identifiant à rechercher (colonne 1)
        verbose: Afficher les messages de log
        
    Returns:
        (login, password) ou (None, None) si non trouvé ou erreur
        
    Format du fichier déchiffré (Markdown):
        | ID     | Login      | Password   |
        |--------|------------|------------|
        | YvBG-M | mon_login  | mon_mdp    |
    """
    
    def log(msg: str, error: bool = False):
        if verbose:
            prefix = "❌" if error else "✓"
            print(f"{prefix} {msg}")
    
    if not gpg_file.exists():
        log(f"Fichier credentials introuvable: {gpg_file}", error=True)
        return None, None
    
    try:
        # Décrypter avec gpg (demandera la passphrase)
        log(f"Lecture de {gpg_file.name}...")
        log("Entrez votre passphrase GPG si demandée")
        
        # Tenter d'abord sans loopback (utilise l'agent GPG en cache)
        # Si échec, on pourra ajouter --pinentry-mode loopback avec --passphrase
        result = subprocess.run(
            ['gpg', '--decrypt', str(gpg_file)],
            capture_output=True,
            text=True,
            check=False
        )
        
        if result.returncode != 0:
            log("Erreur décryptage GPG", error=True)
            if result.stderr:
                log(f"  {result.stderr[:200]}", error=True)
            return None, None
        
        # Parser le contenu
        content = result.stdout
        
        for line in content.splitlines():
            line = line.strip()
            # Ignorer les lignes vides, commentaires, et séparateurs Markdown
            if not line or line.startswith('#') or line.startswith('|---') or line.startswith('| ---'):
                continue
            
            # Format tableau Markdown: | ID | login | password |
            if line.startswith('|'):
                parts = [p.strip() for p in line.split('|')[1:-1]]  # Enlever les | de début et fin
                
                if len(parts) >= 3:
                    # Ignorer la ligne d'en-tête
                    if parts[0].lower() in ['id', 'identifiant', 'site', 'service']:
                        continue
                    
                    if parts[0] == credential_id:
                        # Nettoyer les caractères parasites ajoutés par Seafile/Markdown
                        login = parts[1].strip('`"\'<>')
                        password = parts[2].strip('`"\'<>')
                        log(f"Credentials trouvés pour {credential_id}")
                        return login, password
            else:
                # Format simple: ID | login | password ou ID login password
                parts = [p.strip() for p in line.split('|')] if '|' in line else line.split()
                
                if len(parts) >= 3 and parts[0] == credential_id:
                    # Nettoyer les caractères parasites ajoutés par Seafile/Markdown
                    login = parts[1].strip('`"\'<>')
                    password = parts[2].strip('`"\'<>')
                    log(f"Credentials trouvés pour {credential_id}")
                    return login, password
        
        log(f"Credentials pour {credential_id} non trouvés dans le fichier", error=True)
        return None, None
        
    except FileNotFoundError:
        log("GPG non installé. Installez avec: sudo apt install gnupg", error=True)
        return None, None
    except Exception as e:
        log(f"Erreur lecture GPG: {e}", error=True)
        return None, None


def list_credential_ids(gpg_file: Path, verbose: bool = True) -> list:
    """
    Liste tous les IDs disponibles dans le fichier GPG
    
    Args:
        gpg_file: Chemin vers le fichier .gpg
        verbose: Afficher les messages
        
    Returns:
        Liste des IDs trouvés
    """
    def log(msg: str):
        if verbose:
            print(f"✓ {msg}")
    
    if not gpg_file.exists():
        return []
    
    try:
        result = subprocess.run(
            ['gpg', '--decrypt', str(gpg_file)],
            capture_output=True,
            text=True,
            check=False
        )
        
        if result.returncode != 0:
            return []
        
        ids = []
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line or line.startswith('#') or line.startswith('|---'):
                continue
            
            if line.startswith('|'):
                parts = [p.strip() for p in line.split('|')[1:-1]]
                if len(parts) >= 1 and parts[0].lower() not in ['id', 'identifiant', 'site', 'service']:
                    ids.append(parts[0])
        
        return ids
        
    except:
        return []


# Exemple d'utilisation
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 3:
        print("Usage: python3 gpg_credentials.py <fichier.gpg> <credential_id>")
        print("   ou: python3 gpg_credentials.py <fichier.gpg> --list")
        sys.exit(1)
    
    gpg_file = Path(sys.argv[1])
    
    if sys.argv[2] == "--list":
        print(f"\nIDs disponibles dans {gpg_file.name}:")
        ids = list_credential_ids(gpg_file)
        for id in ids:
            print(f"  - {id}")
    else:
        credential_id = sys.argv[2]
        login, password = get_credentials_from_gpg(gpg_file, credential_id)
        
        if login and password:
            print(f"\n✅ Credentials trouvés:")
            print(f"   Login: {login}")
            print(f"   Password: {'*' * len(password)}")
        else:
            print(f"\n❌ Credentials non trouvés pour: {credential_id}")
            sys.exit(1)
