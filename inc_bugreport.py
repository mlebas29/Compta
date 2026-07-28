#!/usr/bin/env python3
"""inc_bugreport.py — dépôt d'un bundle de diagnostic sur un canal privé (#187).

Permet à un utilisateur du **cercle connu** (poste configuré) de remonter un
rapport de bug AVEC ses diagnostics, sans passer par un canal public. Le
transport est un `ssh` vers un compte de dépôt **forced-command** sur le
serveur privé : la clé de l'utilisateur ne peut QUE déposer un bundle (aucun
shell), et le serveur nomme+range le fichier. Setup côté serveur = ressort de
l'administrateur du cercle connu.

L'endpoint (hôte/user) vit dans `config.ini [general] bugreport_host/…` —
**jamais en dur** (le code est public ; l'infra reste privée, per-instance).
Clés de [general] (réservé), PAS une section dédiée (qui serait prise pour un
site). Feature non configurée (host vide) → l'appelant (GUI) masque le bouton.

Contenu du bundle (recos #187) :
  • noyau systématique : journal.log, logs/debug/*, logs/upgrade.log,
    rapport.txt (version/OS/python/date), description.txt (texte utilisateur) ;
  • à la demande : comptes.xlsm + config*.json (bug « chiffre faux ») ;
  • JAMAIS : config_credentials.md.gpg (défense en profondeur — valeur
    diagnostique nulle, perte = compromission totale offline-attaquable).
"""

import configparser
import io
import os
import platform
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime
from pathlib import Path

import inc_mode

# Clé dédiée à ce seul usage (dépôt-seul), per-machine, hors de tout dépôt.
KEY_PATH = Path.home() / '.ssh' / 'compta_bugdrop'

# Ce qui ne DOIT jamais partir, quelle que soit l'option (secrets).
_NEVER = {'config_credentials.md.gpg'}


def _base_dir():
    return inc_mode.get_base_dir()


def _config():
    cfg = configparser.ConfigParser()
    cfg.read(_base_dir() / 'config.ini')
    return cfg


def endpoint():
    """(host, user) depuis config.ini [general] bugreport_host/bugreport_user,
    ou None si non configuré (host vide/absent) → l'appelant masque le bouton.

    Volontairement des CLÉS de [general] (section réservée), PAS une section
    dédiée : une section non réservée serait prise pour un SITE (site fantôme →
    « description manquante » au démarrage). Les clés sont commentées dans
    config.ini.default → connues du check de cohérence (ni « obsolète » ni
    « manquante »)."""
    cfg = _config()
    host = cfg.get('general', 'bugreport_host', fallback='').strip()
    user = cfg.get('general', 'bugreport_user', fallback='bugdrop').strip()
    if not host:
        return None
    return host, user


def is_configured():
    return endpoint() is not None


def key_exists():
    return KEY_PATH.exists()


def ensure_key():
    """Génère la clé dépôt-seul si absente (ed25519, sans passphrase, chemin
    fixe). Retourne (created: bool, pubkey: str). La publique est à transmettre
    à l'administrateur pour autorisation ; la privée ne quitte jamais le poste."""
    pub = KEY_PATH.with_suffix('.pub')
    if KEY_PATH.exists():
        return False, (pub.read_text().strip() if pub.exists() else '')
    KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ['ssh-keygen', '-t', 'ed25519', '-N', '', '-f', str(KEY_PATH),
         '-C', f'compta-bugdrop-{platform.node()}'],
        check=True, capture_output=True, text=True)
    try:
        os.chmod(KEY_PATH, 0o600)
    except OSError:
        pass
    return True, pub.read_text().strip()


def _rapport_txt(description):
    base = _base_dir()
    cfg = _config()
    try:
        from inc_excel_schema import APP_VERSION
    except Exception:
        APP_VERSION = '?'
    lines = [
        f"date        : {datetime.now().isoformat(timespec='seconds')}",
        f"app_version : {APP_VERSION}",
        f"os          : {platform.platform()}",
        f"python      : {platform.python_version()} ({sys.executable})",
        f"hostname    : {platform.node()}",
        f"base_dir    : {base}",
        f"mode        : {cfg.get('general', 'mode', fallback='?')}",
    ]
    return "\n".join(lines) + "\n"


def _add_text(tar, arcname, text):
    data = text.encode('utf-8')
    info = tarfile.TarInfo(name=arcname)
    info.size = len(data)
    info.mtime = 0  # déterministe (pas de Date.now implicite dans l'archive)
    tar.addfile(info, io.BytesIO(data))


def _add_path(tar, path, arcname):
    """Ajoute un fichier/dossier existant, en excluant les secrets."""
    if not path.exists():
        return
    tar.add(str(path), arcname=arcname,
            filter=lambda ti: None if Path(ti.name).name in _NEVER else ti)


def build_bundle(description='', include_classeur=False):
    """Fabrique le tar.gz de diagnostic dans un fichier temporaire. Retourne son
    Path. L'appelant le supprime après envoi."""
    base = _base_dir()
    logs = base / 'logs'
    fd, tmp = tempfile.mkstemp(prefix='compta_bugreport_', suffix='.tar.gz')
    os.close(fd)
    with tarfile.open(tmp, 'w:gz') as tar:
        _add_text(tar, 'rapport.txt', _rapport_txt(description))
        if description.strip():
            _add_text(tar, 'description.txt', description)
        # Noyau systématique : les logs.
        _add_path(tar, logs / 'journal.log', 'logs/journal.log')
        _add_path(tar, logs / 'upgrade.log', 'logs/upgrade.log')
        _add_path(tar, logs / 'debug', 'logs/debug')
        # À la demande : données comptables (sensible mais utile « chiffre faux »).
        if include_classeur:
            _add_path(tar, base / 'comptes.xlsm', 'comptes.xlsm')
            for js in sorted(base.glob('config*.json')):
                _add_path(tar, js, js.name)
    return Path(tmp)


def send_bundle(bundle_path, timeout=60):
    """Envoie le bundle par ssh au compte de dépôt (forced-command). Retourne
    (ok: bool, message: str). `message` = la réponse du serveur (« Rapport
    reçu… ») ou l'erreur."""
    ep = endpoint()
    if ep is None:
        return False, "Aucun endpoint configuré ([bugreport] absent de config.ini)."
    host, user = ep
    if not KEY_PATH.exists():
        return False, "Clé compta_bugdrop absente (activation requise)."
    cmd = [
        'ssh', '-i', str(KEY_PATH),
        '-o', 'BatchMode=yes',
        '-o', 'StrictHostKeyChecking=accept-new',
        '-o', 'ConnectTimeout=15',
        f'{user}@{host}',
    ]
    try:
        with open(bundle_path, 'rb') as f:
            proc = subprocess.run(cmd, stdin=f, capture_output=True,
                                  text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, f"Délai dépassé ({timeout}s) — serveur injoignable ?"
    except Exception as e:
        return False, f"Échec de l'envoi : {e}"
    if proc.returncode == 0:
        msg = (proc.stderr or proc.stdout or '').strip()
        return True, msg or "Rapport envoyé."
    return False, (proc.stderr or proc.stdout or f'rc={proc.returncode}').strip()


def report(description='', include_classeur=False):
    """Fabrique + envoie + nettoie. Retourne (ok, message). Point d'entrée unique
    (GUI et CLI)."""
    bundle = build_bundle(description, include_classeur)
    try:
        return send_bundle(bundle)
    finally:
        try:
            bundle.unlink()
        except OSError:
            pass


if __name__ == '__main__':
    # CLI de dépannage : envoie un rapport avec une description en argument.
    import argparse
    ap = argparse.ArgumentParser(description="Dépose un bundle de diagnostic (#187).")
    ap.add_argument('description', nargs='?', default='(envoi CLI)',
                    help="Texte décrivant le problème.")
    ap.add_argument('--classeur', action='store_true',
                    help="Joindre le classeur + config*.json (données sensibles).")
    ap.add_argument('--pubkey', action='store_true',
                    help="Génère la clé si absente et affiche la publique, puis quitte.")
    args = ap.parse_args()
    if args.pubkey:
        created, pub = ensure_key()
        print(("clé générée — " if created else "clé déjà présente — ")
              + "envoie cette ligne à l'administrateur :")
        print(pub)
        sys.exit(0)
    if not is_configured():
        print("Non configuré : ajoute une section [bugreport] (host/user) à config.ini.",
              file=sys.stderr)
        sys.exit(2)
    ok, msg = report(args.description, include_classeur=args.classeur)
    print(msg)
    sys.exit(0 if ok else 1)
