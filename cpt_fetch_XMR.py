#!/usr/bin/env python3
"""
cpt_fetch_XMR.py - Récupération des wallets Monero via monero-wallet-rpc distant

Architecture (refonte « nœud distant », cf. Compta_xmr.md) :
- Un monero-wallet-rpc tourne en service sur une machine toujours allumée (le NUC),
  collé au monerod local : le scan de la blockchain s'y fait, en continu et en local
  du nœud (rapide), donc la resynchro longue n'est plus à la charge de ce poste.
- Ce fetcher est un simple CLIENT JSON-RPC : il ouvre un tunnel SSH vers le wallet-rpc
  (bind localhost côté serveur → jamais exposé) puis lit balance + transferts.
- Aucune dépendance Monero locale (ni monerod, ni monero-wallet-cli, ni fichiers wallet)
  → fonctionne identiquement sur Mac / Linux / WSL.

Modèle de secrets :
- mot de passe wallet : reste dans le GPG du poste, envoyé à open_wallet via le tunnel
  chiffré ; les .keys restent chiffrées au repos sur le serveur.
- login RPC du wallet-rpc : GPG (wallet_rpc_credential_id), auth HTTP Digest.

Prérequis :
- Accès SSH non-interactif vers [XMR] wallet_rpc_ssh_host.
- Service monero-wallet-rpc actif côté serveur (voir install_xmr_wallet_rpc.sh).

Fichiers générés (format inchangé) :
- dropbox/XMR/xmr_<wallet_key>_operations.csv
- dropbox/XMR/xmr_balances.csv
"""

import sys
import os
import json
import socket
import time
import contextlib
import subprocess
import configparser
import csv
import requests
from requests.auth import HTTPDigestAuth
from pathlib import Path
from datetime import datetime, timedelta
import inc_mode
from inc_logging import Logger
from inc_format import site_name_from_file
import inc_gpg_credentials

# Site dérivé du nom de fichier
SITE = site_name_from_file(__file__)

# Unité atomique Monero : 1 XMR = 1e12 piconero
ATOMIC = 10 ** 12


# ============================================================================
# DESCRIPTION (consommée par la GUI onglet Sites)
# ============================================================================

DESCRIPTION = """Monero — wallets auto-hébergés, lus via un nœud distant.
Setup du nœud serveur (wallet-rpc) + dépannage : voir Compta_xmr.md.

══════ Configuration ══════

N comptes (1 par wallet). Chaque wallet a un wallet_key et un wallet_name (nom du
fichier wallet côté serveur) dans config_accounts.json.

La collecte se fait à distance : un monero-wallet-rpc tourne en service sur une
machine toujours allumée (collé à monerod). Ce poste ne fait qu'ouvrir un tunnel
SSH et lire balance + transferts en JSON-RPC. Aucun monerod / wallet-cli local.

config.ini [XMR] : wallet_rpc_ssh_host (cible SSH), wallet_rpc_port (port distant),
wallet_rpc_credential_id (login RPC, GPG), credential_id (mot de passe wallet, GPG).

══════ 2FA ══════

Aucune. Auth = clé SSH (tunnel) + login RPC (HTTP Digest) + mot de passe wallet.

══════ Collecte manuelle de secours ══════

Pas de procédure manuelle web."""

# Mode detection
BASE_DIR = inc_mode.get_base_dir()
COMPTA_MODE = inc_mode.get_mode()
CONFIG_FILE = BASE_DIR / 'config.ini'

# Load config
config = configparser.ConfigParser()
config.read(CONFIG_FILE)

# Standard paths
DEBUG = config.getboolean('general', 'DEBUG', fallback=False)
DROPBOX_DIR = BASE_DIR / config.get('paths', 'dropbox') / config.get(SITE, 'dossier', fallback=SITE)
LOGS_DIR = BASE_DIR / config.get('paths', 'logs', fallback='./logs')
DEBUG_DIR = LOGS_DIR / 'debug'
JOURNAL_FILE = LOGS_DIR / 'journal.log'
CREDENTIALS_FILE = Path(config.get('paths', 'credentials_file')).expanduser()

# XMR-specific config
SITE_NAME = config.get(SITE, 'name', fallback='Monero Wallets')
CREDENTIAL_ID = config.get(SITE, 'credential_id')                       # mot de passe wallet
WALLET_RPC_SSH_HOST = config.get(SITE, 'wallet_rpc_ssh_host')           # ex: marc@maillol.labeille.net
WALLET_RPC_PORT = config.getint(SITE, 'wallet_rpc_port', fallback=18083)
WALLET_RPC_LOCAL_PORT = config.getint(SITE, 'wallet_rpc_local_port', fallback=28083)
WALLET_RPC_CREDENTIAL_ID = config.get(SITE, 'wallet_rpc_credential_id')  # login RPC wallet-rpc
MAX_DAYS_BACK = config.getint(SITE, 'max_days_back', fallback=90)
REFRESH_TIMEOUT = config.getint(SITE, 'refresh_timeout', fallback=300)  # resync wallet (local au nœud)
TUNNEL_TIMEOUT = config.getint(SITE, 'tunnel_timeout', fallback=15)

# Wallet mapping : chargé depuis config_accounts.json
_ACCOUNTS_JSON = BASE_DIR / 'config_accounts.json'
with open(_ACCOUNTS_JSON, 'r', encoding='utf-8') as _f:
    _xmr_config = json.load(_f).get(SITE, {})
XMR_WALLETS = {
    a['wallet_key']: {
        # wallet-rpc refuse tout '/' dans le filename (anti-traversée) → les fichiers
        # wallet doivent être À PLAT dans --wallet-dir côté serveur : <wallet-dir>/<wallet_name>
        # (+ <wallet_name>.keys). cf. install_xmr_wallet_rpc.sh / Compta_xmr.md.
        'filename': a['wallet_name'],
        'output_key': f'xmr_{a["wallet_key"]}',
        'display_name': a['name'],
    }
    for a in _xmr_config.get('accounts', [])
    if 'wallet_key' in a and 'wallet_name' in a
}

# Logger
logger = Logger(
    script_name="cpt_fetch_XMR",
    journal_file=JOURNAL_FILE,
    verbose=True,
    debug=DEBUG
)


@contextlib.contextmanager
def ssh_tunnel(ssh_host, local_port, remote_port, timeout=15):
    """
    Ouvre un tunnel SSH (-L local_port:127.0.0.1:remote_port) le temps du bloc.

    Le wallet-rpc est bindé en localhost côté serveur : le tunnel est le seul accès.
    L'auth se fait par la clé SSH (BatchMode, non-interactif).
    """
    cmd = [
        'ssh', '-N',
        '-o', 'BatchMode=yes',
        '-o', 'ExitOnForwardFailure=yes',
        '-o', 'ServerAliveInterval=15',
        '-o', 'ConnectTimeout=10',
        '-L', f'{local_port}:127.0.0.1:{remote_port}',
        ssh_host,
    ]
    logger.debug(f"Ouverture tunnel SSH: {ssh_host} (local {local_port} → distant {remote_port})")
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        deadline = time.time() + timeout
        while True:
            if proc.poll() is not None:
                err = (proc.stderr.read() or b'').decode(errors='replace').strip()
                raise RuntimeError(f"Tunnel SSH fermé prématurément: {err or 'cause inconnue'}")
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1)
                try:
                    s.connect(('127.0.0.1', local_port))
                    logger.debug("Tunnel SSH établi")
                    break
                except OSError:
                    if time.time() >= deadline:
                        raise RuntimeError(f"Tunnel SSH: port local {local_port} non ouvert après {timeout}s")
                    time.sleep(0.5)
        yield
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


class WalletRPC:
    """Client JSON-RPC minimal pour monero-wallet-rpc (via le tunnel)."""

    def __init__(self, url, auth):
        self.url = url
        self.auth = auth
        self._id = 0

    def call(self, method, params=None, timeout=60):
        self._id += 1
        payload = {'jsonrpc': '2.0', 'id': self._id, 'method': method, 'params': params or {}}
        logger.debug(f"RPC → {method} {params or {}}")
        resp = requests.post(self.url, json=payload, auth=self.auth, timeout=timeout)
        if resp.status_code == 401:
            raise RuntimeError("wallet-rpc: 401 Unauthorized (login RPC incorrect)")
        resp.raise_for_status()
        data = resp.json()
        if data.get('error'):
            raise RuntimeError(f"wallet-rpc {method}: {data['error']}")
        return data.get('result', {})


def parse_transfers(result, max_days_back):
    """
    Convertit la réponse get_transfers en opérations (mêmes champs que l'ancien parseur CLI).

    get_transfers renvoie {'in': [...], 'out': [...]} ; montants/fees en piconero (atomiques),
    timestamp en epoch. On filtre sur max_days_back, on signe les sorties, et on émet le fee
    comme opération séparée (comportement historique conservé pour le format/import).
    """
    cutoff = datetime.now() - timedelta(days=max_days_back)
    base = []

    for entry in result.get('in', []):
        ts = datetime.fromtimestamp(entry['timestamp'])
        if ts < cutoff:
            continue
        base.append({
            'date': ts.strftime('%Y-%m-%d %H:%M:%S'),
            'type': 'in',
            'amount': entry['amount'] / ATOMIC,
            'fee': 0.0,
            'label': 'Incoming transfer',
        })

    for entry in result.get('out', []):
        ts = datetime.fromtimestamp(entry['timestamp'])
        if ts < cutoff:
            continue
        base.append({
            'date': ts.strftime('%Y-%m-%d %H:%M:%S'),
            'type': 'out',
            'amount': -entry['amount'] / ATOMIC,
            'fee': entry.get('fee', 0) / ATOMIC,
            'label': 'Outgoing transfer',
        })

    base.sort(key=lambda o: o['date'])

    # Émettre les frais en opérations distinctes (comme l'ancien fetcher)
    operations = []
    for op in base:
        operations.append(op)
        if op['fee'] > 0:
            operations.append({
                'date': op['date'],
                'type': 'fee',
                'amount': -op['fee'],
                'fee': 0.0,
                'label': 'Transaction fee',
            })

    logger.debug(f"Parsed {len(operations)} operations")
    return operations


def fetch_xmr_wallet(rpc, wallet_info, wallet_password, max_days_back):
    """
    Ouvre un wallet côté serveur, le resynchronise, lit balance + transferts, le referme.

    Returns:
        Tuple (operations_list, balance_xmr)
    """
    filename = wallet_info['filename']
    display_name = wallet_info['display_name']
    logger.info(f"Wallet {display_name} (fichier: {filename})")

    # Refermer un éventuel wallet resté ouvert (run précédent interrompu)
    try:
        rpc.call('close_wallet')
    except Exception:
        pass

    rpc.call('open_wallet', {'filename': filename, 'password': wallet_password})
    try:
        # Resync (local au nœud côté serveur → rapide même sur un gros delta)
        logger.debug("refresh…")
        rpc.call('refresh', {}, timeout=REFRESH_TIMEOUT)

        bal = rpc.call('get_balance', {'account_index': 0})
        balance = bal.get('balance', 0) / ATOMIC
        logger.info(f"Balance: {balance} XMR")

        transfers = rpc.call('get_transfers', {'in': True, 'out': True})
        operations = parse_transfers(transfers, max_days_back)
        logger.info(f"Extracted {len(operations)} operations")
    finally:
        try:
            rpc.call('close_wallet')
        except Exception as e:
            logger.debug(f"close_wallet: {e}")

    return operations, balance


def write_operations_csv(operations, wallet_key, output_file):
    """Write operations to CSV file"""
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Date', 'Label', 'Amount', 'Currency', 'Wallet'])
        for op in operations:
            writer.writerow([
                op['date'],
                op['label'],
                f"{op['amount']:.12f}",  # XMR has 12 decimals
                'XMR',
                wallet_key
            ])
    logger.info(f"✓ Wrote {len(operations)} operations to {output_file.name}")


def write_balances_csv(balances, output_file):
    """Write balances to CSV file"""
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Wallet', 'Balance', 'Currency', 'Date'])
        for balance in balances:
            writer.writerow([
                balance['wallet'],
                f"{balance['balance']:.12f}",  # XMR has 12 decimals
                balance['currency'],
                balance['date']
            ])
    logger.info(f"✓ Wrote {len(balances)} balances to {output_file.name}")


def main():
    """Main workflow"""
    logger.info("=" * 60)
    logger.info(f"Démarrage collecte {SITE_NAME}")
    logger.info(f"Mode: {COMPTA_MODE.upper()}")
    logger.info(f"DEBUG: {DEBUG}")
    logger.info(f"wallet-rpc: {WALLET_RPC_SSH_HOST} :{WALLET_RPC_PORT} (tunnel local {WALLET_RPC_LOCAL_PORT})")
    logger.info(f"Max days back: {MAX_DAYS_BACK}")
    logger.info("=" * 60)

    if not WALLET_RPC_SSH_HOST:
        logger.error("Config [XMR] wallet_rpc_ssh_host manquant")
        return 1
    if not XMR_WALLETS:
        logger.error("Aucun wallet XMR dans config_accounts.json")
        return 1

    # Create dropbox directory
    DROPBOX_DIR.mkdir(parents=True, exist_ok=True)

    # Mot de passe wallet (envoyé à open_wallet via le tunnel)
    logger.info(f"Chargement mot de passe wallet (GPG {CREDENTIAL_ID})")
    try:
        _login, wallet_password = inc_gpg_credentials.get_credentials_from_gpg(
            CREDENTIALS_FILE, CREDENTIAL_ID, verbose=DEBUG
        )
    except Exception as e:
        logger.error(f"Échec lecture mot de passe wallet: {e}")
        return 1
    if not wallet_password:
        logger.error(f"Mot de passe wallet introuvable pour {CREDENTIAL_ID}")
        return 1

    # Login RPC du wallet-rpc (HTTP Digest)
    logger.info(f"Chargement login RPC wallet-rpc (GPG {WALLET_RPC_CREDENTIAL_ID})")
    try:
        rpc_user, rpc_pass = inc_gpg_credentials.get_credentials_from_gpg(
            CREDENTIALS_FILE, WALLET_RPC_CREDENTIAL_ID, verbose=DEBUG
        )
    except Exception as e:
        logger.error(f"Échec lecture login RPC: {e}")
        return 1
    if not rpc_user or not rpc_pass:
        logger.error(f"Login RPC introuvable pour {WALLET_RPC_CREDENTIAL_ID}")
        return 1

    all_balances = []
    success_count = 0

    try:
        with ssh_tunnel(WALLET_RPC_SSH_HOST, WALLET_RPC_LOCAL_PORT, WALLET_RPC_PORT, TUNNEL_TIMEOUT):
            url = f"http://127.0.0.1:{WALLET_RPC_LOCAL_PORT}/json_rpc"
            rpc = WalletRPC(url, HTTPDigestAuth(rpc_user, rpc_pass))

            # Vérif connexion + auth
            ver = rpc.call('get_version')
            logger.info(f"✓ wallet-rpc joignable (version {ver.get('version', '?')})")

            for wallet_key, wallet_info in XMR_WALLETS.items():
                try:
                    operations, balance = fetch_xmr_wallet(
                        rpc, wallet_info, wallet_password, MAX_DAYS_BACK
                    )
                    ops_file = DROPBOX_DIR / f"{wallet_info['output_key']}_operations.csv"
                    write_operations_csv(operations, wallet_key, ops_file)
                    all_balances.append({
                        'wallet': wallet_info['display_name'],
                        'balance': balance,
                        'currency': 'XMR',
                        'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    })
                    success_count += 1
                except Exception as e:
                    logger.error(f"❌ Error fetching {wallet_key}: {e}")
                    import traceback
                    logger.debug(traceback.format_exc())
    except Exception as e:
        logger.error("=" * 60)
        logger.error(f"✗ Collecte impossible: {e}")
        logger.error("Hint: vérifier l'accès SSH et le service monero-wallet-rpc côté serveur")
        logger.error("=" * 60)
        return 1

    # Write balances CSV to dropbox/XMR/
    if all_balances:
        balances_file = DROPBOX_DIR / 'xmr_balances.csv'
        write_balances_csv(all_balances, balances_file)

    # Summary
    logger.info("=" * 60)
    logger.info(f"✓ Collecte terminée: {success_count}/{len(XMR_WALLETS)} wallets")
    logger.info(f"📁 Fichiers dans: {DROPBOX_DIR}")
    logger.info("=" * 60)

    return 0 if success_count > 0 else 1


if __name__ == '__main__':
    sys.exit(main())
