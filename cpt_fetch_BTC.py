#!/usr/bin/env python3
"""
cpt_fetch_BTC.py - Récupération automatique des wallets Bitcoin

Prérequis:
- pip3 install requests
- Variable d'environnement COMPTA_MODE (test ou prod)

Usage:
  ./cpt_fetch_BTC.py

Fichiers générés:
  - dropbox/BTC/btc_relai_operations.csv
  - dropbox/BTC/btc_bluewallet_operations.csv
  - dropbox/BTC/btc_electrum_operations.csv
  - dropbox/BTC/btc_phoenix_operations.csv
  - dropbox/BTC/btc_deblock_operations.csv
  - dropbox/BTC/btc_balances.csv
"""

import sys
import os
import json
import time
import configparser
import csv
from pathlib import Path
from datetime import datetime, timedelta
import inc_mode
from inc_logging import Logger
from inc_format import site_name_from_file

# Site dérivé du nom de fichier
SITE = site_name_from_file(__file__)

try:
    import requests
except ImportError:
    print("❌ Module 'requests' manquant. Installez avec: pip3 install requests", file=sys.stderr)
    sys.exit(1)

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

# Site-specific config
SITE_NAME = config.get(SITE, 'name', fallback=SITE)
API_URL = config.get(SITE, 'api_url')
MAX_DAYS_BACK = config.getint(SITE, 'max_days_back', fallback=90)

# Wallet addresses from config_accounts.json
_ACCOUNTS_JSON = BASE_DIR / 'config_accounts.json'
with open(_ACCOUNTS_JSON, 'r', encoding='utf-8') as _f:
    _btc_config = json.load(_f).get(SITE, {})
BTC_WALLETS = {
    a['wallet_key']: a['addresses']
    for a in _btc_config.get('accounts', [])
    if 'wallet_key' in a and 'addresses' in a
}

# Logger
logger = Logger(
    script_name="cpt_fetch_BTC",
    journal_file=JOURNAL_FILE,
    verbose=True,
    debug=DEBUG
)


def fetch_with_retry(url, max_retries=3, timeout=10):
    """Fetch URL with retry logic and exponential backoff"""
    for attempt in range(max_retries):
        try:
            response = requests.get(url, timeout=timeout)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            if attempt == max_retries - 1:
                logger.error(f"Échec après {max_retries} tentatives: {e}")
                return None
            logger.warning(f"Tentative {attempt + 1} échouée, nouvel essai...")
            time.sleep(2 ** attempt)  # Exponential backoff
    return None


def parse_btc_transaction(tx, our_address):
    """
    Parse mempool.space transaction JSON

    Args:
        tx: Transaction dict from API
        our_address: Our Bitcoin address

    Returns:
        Tuple: (tx_type, amount, fee, label)
        - tx_type: 'incoming', 'outgoing', or None
        - amount: satoshis (positive for incoming, negative for outgoing)
        - fee: satoshis (only for outgoing)
        - label: Human-readable description
    """
    # Calculate our input (amount sent from our address)
    our_input = 0
    for vin in tx.get('vin', []):
        prevout = vin.get('prevout', {})
        if prevout.get('scriptpubkey_address') == our_address:
            our_input += prevout.get('value', 0)

    # Calculate our output (amount received to our address)
    our_output = 0
    for vout in tx.get('vout', []):
        if vout.get('scriptpubkey_address') == our_address:
            our_output += vout.get('value', 0)

    fee = tx.get('fee', 0)

    # Classify transaction
    if our_input == 0 and our_output > 0:
        # Incoming transaction
        # Extract sender address (first input address)
        sender = "unknown"
        if tx.get('vin') and tx['vin'][0].get('prevout'):
            sender = tx['vin'][0]['prevout'].get('scriptpubkey_address', 'unknown')
            sender = sender[:20] + '...' if len(sender) > 20 else sender

        return 'incoming', our_output, 0, f'Received from {sender}'

    elif our_input > 0 and our_output == 0:
        # Outgoing transaction (full spend)
        # Extract recipient address (first output address)
        recipient = "unknown"
        if tx.get('vout') and tx['vout'][0].get('scriptpubkey_address'):
            recipient = tx['vout'][0]['scriptpubkey_address']
            recipient = recipient[:20] + '...' if len(recipient) > 20 else recipient

        return 'outgoing', -our_input, fee, f'Sent to {recipient}'

    elif our_input > 0 and our_output > 0:
        # Change transaction (send + receive change)
        net = our_output - our_input
        if net < 0:
            # Net spend
            recipient = "unknown"
            for vout in tx.get('vout', []):
                addr = vout.get('scriptpubkey_address')
                if addr and addr != our_address:
                    recipient = addr[:20] + '...' if len(addr) > 20 else addr
                    break
            return 'outgoing', net, fee, f'Sent to {recipient}'
        else:
            # Net receive (shouldn't happen normally)
            return 'incoming', net, 0, 'Received (with change)'

    # Not our transaction
    return None, 0, 0, ''


def is_xpub(address):
    """Check if address is an extended public key (xpub/ypub/zpub)"""
    return address.startswith(('xpub', 'ypub', 'zpub', 'tpub', 'upub', 'vpub'))


def fetch_btc_wallet(address, wallet_key, api_url, max_days_back):
    """
    Fetch Bitcoin wallet transactions from mempool.space API

    Args:
        address: Bitcoin address or xpub (extended public key)
        wallet_key: Wallet identifier (e.g., 'relai')
        api_url: API base URL
        max_days_back: Maximum days back from today

    Returns:
        Tuple: (operations_list, balance_sat)
    """
    is_extended_key = is_xpub(address)
    addr_display = address[:20] + '...' if len(address) > 20 else address
    logger.info(f"Fetching wallet {wallet_key} ({addr_display}) [{'xpub' if is_extended_key else 'address'}]")

    # Calculate cutoff timestamp
    cutoff_date = datetime.now() - timedelta(days=max_days_back)
    cutoff_timestamp = int(cutoff_date.timestamp())

    operations = []

    # Pour les xpub, on ne parse pas les transactions individuelles (trop complexe)
    # On récupère seulement le solde global
    if is_extended_key:
        logger.info("Mode xpub : récupération du solde uniquement")
    else:
        # Fetch transactions for single address
        txs_url = f"{api_url}/address/{address}/txs"
        logger.debug(f"GET {txs_url}")

        txs = fetch_with_retry(txs_url)
        if txs is None:
            logger.warning(f"Failed to fetch transactions for {wallet_key} ({addr_display}), continuing for balance")
            txs = []

        logger.info(f"Found {len(txs)} total transactions")

        # Parse transactions
        for tx in txs:
            # Check confirmation
            status = tx.get('status', {})
            if not status.get('confirmed'):
                logger.debug(f"Skipping unconfirmed tx: {tx.get('txid', 'unknown')[:16]}...")
                continue

            # Check date
            block_time = status.get('block_time', 0)
            if block_time < cutoff_timestamp:
                logger.debug(f"Skipping old tx: {datetime.fromtimestamp(block_time).strftime('%Y-%m-%d')}")
                continue

            # Parse transaction
            tx_type, amount, fee, label = parse_btc_transaction(tx, address)

            if tx_type is None:
                continue

            # Format date
            date_str = datetime.fromtimestamp(block_time).strftime('%Y-%m-%d %H:%M:%S')

            # Add operation
            operations.append({
                'date': date_str,
                'label': label,
                'amount': amount,
                'currency': 'SAT',
                'wallet': wallet_key
            })

            # Add fee as separate operation if present
            if fee > 0:
                operations.append({
                    'date': date_str,
                    'label': 'Transaction fee',
                    'amount': -fee,
                    'currency': 'SAT',
                    'wallet': wallet_key
                })

        logger.info(f"Extracted {len(operations)} operations (after filtering)")

    # Pause anti rate-limiting entre les appels API
    time.sleep(1)

    # Fetch balance (different endpoint and structure for xpub vs address)
    if is_extended_key:
        balance_url = f"{api_url}/v1/xpub/{address}"
    else:
        balance_url = f"{api_url}/address/{address}"
    logger.debug(f"GET {balance_url}")

    addr_info = fetch_with_retry(balance_url)
    balance_sat = 0
    if addr_info:
        if is_extended_key:
            # xpub response: balance is directly in the response
            funded = addr_info.get('chain_stats', {}).get('funded_txo_sum', 0)
            spent = addr_info.get('chain_stats', {}).get('spent_txo_sum', 0)
            balance_sat = funded - spent
        else:
            # address response
            funded = addr_info.get('chain_stats', {}).get('funded_txo_sum', 0)
            spent = addr_info.get('chain_stats', {}).get('spent_txo_sum', 0)
            balance_sat = funded - spent
        logger.info(f"Balance: {balance_sat} SAT")
    else:
        logger.warning(f"Failed to fetch balance for {wallet_key}, using 0")

    return operations, balance_sat


def write_operations_csv(operations, wallet_key, output_file):
    """Write operations to CSV file"""
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Date', 'Label', 'Amount', 'Currency', 'Wallet'])
        for op in operations:
            writer.writerow([
                op['date'],
                op['label'],
                op['amount'],
                op['currency'],
                op['wallet']
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
                balance['balance'],
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
    logger.info(f"Max days back: {MAX_DAYS_BACK}")
    logger.info("=" * 60)

    # Create dropbox directory
    DROPBOX_DIR.mkdir(parents=True, exist_ok=True)

    # Fetch all wallets
    all_balances = []
    success_count = 0

    for wallet_key, addresses in BTC_WALLETS.items():
        try:
            # Fetch all addresses for this wallet
            all_operations = []
            total_balance = 0

            for i, address in enumerate(addresses):
                if i > 0:
                    time.sleep(1)  # Pause entre adresses pour éviter le rate limiting
                operations, balance = fetch_btc_wallet(address, wallet_key, API_URL, MAX_DAYS_BACK)
                all_operations.extend(operations)
                total_balance += balance

            if len(addresses) > 1:
                logger.info(f"  {wallet_key}: {len(addresses)} adresses, solde total = {total_balance} SAT")

            # Write operations CSV
            ops_file = DROPBOX_DIR / f'btc_{wallet_key}_operations.csv'
            write_operations_csv(all_operations, wallet_key, ops_file)

            # Store balance
            all_balances.append({
                'wallet': f'{wallet_key.capitalize()} BTC',
                'balance': total_balance,
                'currency': 'SAT',
                'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            })

            success_count += 1

        except Exception as e:
            logger.error(f"❌ Error fetching {wallet_key}: {e}")
            import traceback
            logger.debug(traceback.format_exc())

    # Write balances CSV to dropbox/BTC/
    if all_balances:
        balances_file = DROPBOX_DIR / 'btc_balances.csv'
        write_balances_csv(all_balances, balances_file)

    # Summary
    logger.info("=" * 60)
    logger.info(f"✓ Collecte terminée: {success_count}/{len(BTC_WALLETS)} wallets")
    logger.info(f"📁 Fichiers dans: {DROPBOX_DIR}")
    logger.info("=" * 60)

    return 0 if success_count > 0 else 1


if __name__ == '__main__':
    sys.exit(main())
