#!/usr/bin/env python3
"""
Module pour lire les credentials depuis un fichier GPG
Format supporté: tableau Markdown avec colonnes | ID | login | password |

Deux couches, deux usages :

  - LECTURE d'un secret (collecte) — `get_credentials_from_gpg` : passe par
    gpg-agent/pinentry, l'application ne voit JAMAIS la passphrase. C'est le
    chemin historique, inchangé.

  - CRUD de la table (GUI) — `read_entries`/`upsert_entry`/`delete_entry` :
    la passphrase est fournie par l'appelant (loopback). Nécessaire parce que
    `gpg -c` réclamerait sinon une NOUVELLE passphrase (avec confirmation) à
    chaque écriture, qu'une simple faute de frappe rendrait divergente de celle
    du fichier — table irrécupérable. Ici le déchiffrement AMONT valide la
    passphrase, et le rechiffrement réutilise la même : la divergence est
    structurellement impossible.

Invariants du CRUD (les tenir, ils portent la sûreté du geste) :

  - Le SUPPORT ne change pas : table Markdown chiffrée en symétrique, donc
    toujours éditable à la main (`gpg -d` / `gpg -c`). La GUI est une surface
    de plus, jamais un passage obligé.
  - Écriture LIGNE À LIGNE (patron `inc_update._write_general_key`) : seule la
    ligne ciblée est réécrite, tout le reste — commentaires, colonnes en trop,
    ordre, mise en page — est recopié verbatim.
  - Le CLAIR ne touche jamais le disque (pipes uniquement), et la passphrase ne
    passe jamais par la ligne de commande (`ps` la verrait) : fd dédié.
  - Backup avant toute écriture, puis remplacement atomique.
  - `read_entries` rend (id, login) par défaut ; le mot de passe n'est joint que
    sur `with_password=True`, réservé à la porte « Table chiffrée » qui l'affiche
    (table déjà déchiffrée sous les yeux → le montrer évite les fautes de frappe).
"""

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Tuple, Optional, List

# Cellule de séparateur Markdown : que des tirets, avec l'alignement optionnel
# (`---`, `:---`, `---:`, `:---:`).
_SEP_CELL = re.compile(r':?-{2,}:?$')

# Filet pour une table SANS séparateur (rare) : l'en-tête ne peut alors se
# reconnaître qu'au libellé. Sur une table normale ce filet ne sert pas — la
# STRUCTURE tranche (cf. `_header_index`), ce qui rend inutile de deviner le
# vocabulaire, la langue ou l'encodage des accents de l'en-tête.
_HEADER_TOKENS = ('id', 'identifiant', 'site', 'service', 'clé', 'cle', 'key')


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
        | Réf        | Identifiant | Passe   |
        |------------|-------------|---------|
        | MaBanque-1 | mon_login   | mon_mdp |
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
                        # Nettoyer les caractères parasites ajoutés par la synchro/l'éditeur Markdown
                        login = parts[1].strip('`"\'<>')
                        password = parts[2].strip('`"\'<>')
                        log(f"Credentials trouvés pour {credential_id}")
                        return login, password
            else:
                # Format simple: ID | login | password ou ID login password
                parts = [p.strip() for p in line.split('|')] if '|' in line else line.split()
                
                if len(parts) >= 3 and parts[0] == credential_id:
                    # Nettoyer les caractères parasites ajoutés par la synchro/l'éditeur Markdown
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


# ---------------------------------------------------------------------------
# CRUD de la table (surface GUI) — cf. docstring du module pour les invariants.
# ---------------------------------------------------------------------------


def _run_gpg(args: list, passphrase: str, stdin_data: Optional[bytes] = None):
    """Lance gpg avec la passphrase sur un fd DÉDIÉ (jamais argv → invisible de `ps`).

    stdin reste libre pour le clair à chiffrer. Retourne le CompletedProcess.
    """
    r_fd, w_fd = os.pipe()
    try:
        os.write(w_fd, (passphrase + '\n').encode('utf-8'))
        os.close(w_fd)
        w_fd = None
        cmd = ['gpg', '--batch', '--quiet', '--yes', '--pinentry-mode', 'loopback',
               '--passphrase-fd', str(r_fd)] + args
        return subprocess.run(cmd, input=stdin_data, capture_output=True,
                              pass_fds=(r_fd,), check=False)
    finally:
        if w_fd is not None:
            os.close(w_fd)
        os.close(r_fd)


def decrypt_table(gpg_file, passphrase: str) -> Tuple[Optional[str], Optional[str]]:
    """Déchiffre la table en MÉMOIRE. Retourne (contenu, None) ou (None, erreur).

    Sert aussi de VALIDATION de la passphrase : tout écrivain doit passer par ici
    d'abord, ce qui garantit qu'on rechiffre avec la passphrase réelle du fichier.
    """
    gpg_file = Path(gpg_file)
    if not gpg_file.exists():
        return None, f"Fichier introuvable : {gpg_file}"
    try:
        res = _run_gpg(['--decrypt', str(gpg_file)], passphrase)
    except FileNotFoundError:
        return None, "GPG n'est pas installé."
    if res.returncode != 0:
        err = (res.stderr or b'').decode('utf-8', 'replace').strip()
        if 'Mauvaise clef' in err or 'Bad session key' in err or 'decryption failed' in err:
            return None, "Passphrase incorrecte."
        return None, f"Échec du déchiffrement : {err[:200]}"
    return res.stdout.decode('utf-8', 'replace'), None


def _encrypt_table(content: str, gpg_file, passphrase: str) -> Optional[str]:
    """Rechiffre `content` vers `gpg_file`. Backup d'abord, remplacement atomique.

    Retourne None si OK, sinon le message d'erreur. Le clair ne touche pas le
    disque : il transite par stdin, et seul le chiffré est écrit.
    """
    gpg_file = Path(gpg_file)
    backup = gpg_file.with_name(gpg_file.name + '.bak')
    tmp = gpg_file.with_name(gpg_file.name + '.tmp')
    if gpg_file.exists():                 # rien à sauvegarder à la CRÉATION
        try:
            shutil.copy2(gpg_file, backup)
        except OSError as e:
            return f"Backup impossible, écriture abandonnée : {e}"
    try:
        res = _run_gpg(['--symmetric', '--output', str(tmp)], passphrase,
                       stdin_data=content.encode('utf-8'))
        if res.returncode != 0:
            err = (res.stderr or b'').decode('utf-8', 'replace').strip()
            return f"Échec du chiffrement : {err[:200]}"
        # Relecture de contrôle AVANT de remplacer l'original : une table qu'on ne
        # sait pas relire ne doit jamais devenir le fichier de référence.
        check, err = decrypt_table(tmp, passphrase)
        if check != content:
            return "Relecture de contrôle KO — original conservé."
        os.replace(tmp, gpg_file)
        return None
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def _split_cells(line: str) -> Optional[List[str]]:
    """Cellules d'une ligne de TABLEAU (quelle qu'elle soit), ou None."""
    s = line.strip()
    if not s.startswith('|'):
        return None
    return [p.strip() for p in s.split('|')[1:-1]]


def _is_separator(line: str) -> bool:
    """Ligne de séparation Markdown — reconnue à sa FORME (`|---|:--:|`…), pas à
    un préfixe : les variantes d'alignement sont des séparateurs de plein droit."""
    cells = _split_cells(line)
    return bool(cells) and all(_SEP_CELL.match(c) for c in cells)


def _header_index(lines: List[str]) -> Optional[int]:
    """Indice de la ligne d'EN-TÊTE, déduit de la STRUCTURE : en Markdown, c'est la
    ligne de tableau qui précède immédiatement le séparateur — quel que soit son
    libellé, sa langue ou l'encodage de ses accents.

    Deviner l'en-tête à une liste de mots (« id », « clé »…) dérive dès que la
    table ne dit pas exactement ce que la liste prévoyait ; la position, elle, est
    une propriété du format. Retourne None si la table n'a pas de séparateur (on
    retombe alors sur `_HEADER_TOKENS`).
    """
    for i, line in enumerate(lines):
        if _is_separator(line):
            j = i - 1
            if j >= 0 and _split_cells(lines[j]) is not None:
                return j
            return None
    return None


EMPTY_TABLE = "| Réf | Identifiant | Passe |\n|-----|-------------|-------|\n"


def create_table(gpg_file, passphrase: str,
                 content: Optional[str] = None) -> Optional[str]:
    """Crée la table chiffrée. Retourne None si OK, sinon l'erreur.

    SEUL endroit où une passphrase NEUVE est légitime : il n'existe encore aucune
    passphrase dont diverger, donc rien à valider en amont — c'est à l'appelant de
    la faire confirmer (deux saisies). Partout ailleurs, la règle inverse tient
    (cf. docstring du module).

    `content` = graine (une table en clair déjà remplie à reprendre, p.ex.) ;
    None → table vide avec son seul en-tête.
    """
    gpg_file = Path(gpg_file)
    if gpg_file.exists():
        return f"La table existe déjà : {gpg_file}"
    if not passphrase:
        return "Passphrase vide."
    return _encrypt_table(content if content is not None else EMPTY_TABLE,
                          gpg_file, passphrase)


def _row_cells(line: str) -> Optional[List[str]]:
    """Cellules d'une ligne d'ENTRÉE, ou None si la ligne n'en est pas une
    (commentaire, séparateur, en-tête, ligne de tableau VIDE, ligne libre...).
    Miroir de `get_credentials_from_gpg` : les deux doivent voir la même chose.

    ⚠ Sans contexte, cette fonction ne peut pas voir l'en-tête POSITIONNEL — les
    appelants passent par `_entries` qui, lui, l'écarte par la structure.

    Une ligne de tableau sans identifiant (`| | | |`, résidu de mise en page) n'est
    PAS une entrée : rendue telle quelle elle produirait une entrée d'ID vide, que
    personne ne peut ni chercher ni cibler. Elle est donc ignorée — et par là même
    préservée verbatim, puisqu'on ne réécrit que les lignes qu'on reconnaît.
    """
    cells = _split_cells(line)
    if cells is None or _is_separator(line):
        return None
    if len(cells) < 3 or not cells[0] or cells[0].lower() in _HEADER_TOKENS:
        return None
    return cells


def _entries(lines: List[str]) -> dict:
    """{indice de ligne: cells} des seules ENTRÉES — en-tête écarté par la position.

    Point de vérité unique partagé par la lecture ET les écritures : les trois
    doivent voir exactement le même ensemble de lignes, sinon la GUI afficherait
    une ligne que l'écrivain ne saurait pas cibler (ou l'inverse).
    """
    head = _header_index(lines)
    out = {}
    for i, line in enumerate(lines):
        if i == head:
            continue
        cells = _row_cells(line)
        if cells:
            out[i] = cells
    return out


def _format_row(cred_id: str, login: str, password: str) -> str:
    return f"| {cred_id} | {login} | {password} |"


def read_entries(gpg_file, passphrase: str,
                 with_password: bool = False) -> Tuple[Optional[list], Optional[str]]:
    """Liste les entrées : [(id, login), ...], ou [(id, login, passe), ...] si
    `with_password`. Retourne (entrées, None) ou (None, erreur).

    Le mot de passe ne remonte que sur demande EXPLICITE : la porte « Table chiffrée »
    l'affiche (le voir évite les fautes de frappe, et la table est déjà déchiffrée
    sous les yeux) ; les autres appelants s'en passent.
    """
    content, err = decrypt_table(gpg_file, passphrase)
    if err:
        return None, err
    rows = [(c[0], c[1], c[2]) if with_password else (c[0], c[1])
            for c in _entries(content.splitlines()).values()]
    return rows, None


def upsert_entry(gpg_file, passphrase: str, cred_id: str,
                 login: Optional[str] = None,
                 password: Optional[str] = None) -> Tuple[Optional[str], Optional[str]]:
    """Crée ou modifie l'entrée `cred_id`. Retourne (action, None) | (None, erreur),
    action ∈ {'ajoutée', 'modifiée'}.

    `login`/`password` à None = inchangé (permet de corriger un login sans
    connaître le mot de passe, et réciproquement). Une entrée neuve prend '' pour
    les champs omis.
    """
    if not cred_id or '|' in cred_id:
        return None, "Identifiant vide ou contenant « | » (séparateur de colonnes)."
    if (login and '|' in login) or (password and '|' in password):
        return None, "Le caractère « | » est interdit (séparateur de colonnes)."
    content, err = decrypt_table(gpg_file, passphrase)
    if err:
        return None, err

    lines = content.splitlines(keepends=True)
    entries = _entries(lines)
    target = next((i for i, c in entries.items() if c[0] == cred_id), None)

    out, last_table_idx = [], -1
    for i, line in enumerate(lines):
        if _split_cells(line) is not None:
            last_table_idx = i
        if i == target:
            cells = entries[i]
            eol = '\n' if line.endswith('\n') else ''
            new_login = cells[1] if login is None else login
            new_pw = cells[2] if password is None else password
            out.append(_format_row(cred_id, new_login, new_pw) + eol)
            continue
        out.append(line)

    action = 'modifiée'
    if target is None:
        action = 'ajoutée'
        row = _format_row(cred_id, login or '', password or '') + '\n'
        if last_table_idx >= 0:
            # Insérer À LA SUITE du bloc table, pas en fin de fichier : ce qui suit
            # (notes, commentaires) doit rester après la table.
            if not out[last_table_idx].endswith('\n'):
                out[last_table_idx] += '\n'
            out.insert(last_table_idx + 1, row)
        else:
            out.append(row)

    err = _encrypt_table(''.join(out), gpg_file, passphrase)
    return (None, err) if err else (action, None)


def delete_entry(gpg_file, passphrase: str, cred_id: str) -> Optional[str]:
    """Supprime l'entrée `cred_id`. Retourne None si OK, sinon l'erreur."""
    content, err = decrypt_table(gpg_file, passphrase)
    if err:
        return err
    lines = content.splitlines(keepends=True)
    target = next((i for i, c in _entries(lines).items() if c[0] == cred_id), None)
    if target is None:
        return f"Identifiant « {cred_id} » introuvable."
    out = [l for i, l in enumerate(lines) if i != target]
    return _encrypt_table(''.join(out), gpg_file, passphrase)


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
