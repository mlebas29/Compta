#!/usr/bin/env python3
"""
cpt_format_XMR.py - Formatage des fichiers Monero (monoscript)

Gère deux types de fichiers :
1. Operations : xmr_*_operations.csv → format 9 champs + #Solde
2. Balances : xmr_balances.csv → format 4 champs

Usage:
  ./cpt_format_XMR.py input.csv > output.csv
"""

import sys
import csv
import json
from pathlib import Path
import inc_mode
import inc_categorize
from inc_format import process_files, lines_to_tuples, log_csv_debug as _log_csv_debug, parse_french_date_from_iso, site_name_from_file

SITE = site_name_from_file(__file__)

# Mode detection
BASE_DIR = inc_mode.get_base_dir()
CONFIG_FILE = BASE_DIR / 'config.ini'

# Comptes XMR : chargés depuis config_accounts.json
_ACCOUNTS_JSON = Path(__file__).parent / 'config_accounts.json'
with open(_ACCOUNTS_JSON, 'r', encoding='utf-8') as _f:
    _xmr_config = json.load(_f).get(SITE, {})
XMR_ACCOUNTS = {
    f'xmr_{a["wallet_key"]}': a['name']
    for a in _xmr_config.get('accounts', [])
    if 'wallet_key' in a
}


def detect_account_from_filename(filename):
    """Detect account from filename: xmr_marc_operations.csv → Marc XMR"""
    for key, account_name in XMR_ACCOUNTS.items():
        if key in filename:
            return account_name
    return None


# ============================================================================
# API POUR UPDATE - NOUVELLE INTERFACE
# ============================================================================

# Variable module pour communication entre handlers
_balances_data = {}  # wallet -> (balance, date)


def _process_operations(ops_file):
    """Handler pour process_files: parse un fichier operations et retourne des tuples 9 champs.

    Note: Le filtrage par date est centralisé dans inc_format.process_files()
    """
    # Detect account from filename
    account_name = detect_account_from_filename(ops_file.name)
    if not account_name:
        return []

    # Read operations
    operations = []
    with open(ops_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            date_str = row['Date'].strip()
            label = row['Label'].strip()
            amount_str = row['Amount'].strip()
            currency = row['Currency'].strip()

            # Parse date
            date_french = parse_french_date_from_iso(date_str)

            # Categorize operation
            category, opts = inc_categorize.categorize_operation(label, SITE)
            ref = opts.get('ref', '')
            equiv = ''

            operations.append({
                'date_str': date_french,
                'label': label,
                'amount': amount_str,
                'currency': currency,
                'equiv': equiv,
                'ref': ref,
                'category': category,
                'account': account_name,
                'comment': ''
            })

    # Convert to tuples
    result = []
    for op in operations:
        result.append((op['date_str'], op['label'], op['amount'], op['currency'], op['equiv'],
                       op['ref'], op['category'], op['account'], op['comment']))

    return result


def _process_balances(balances_file):
    """Handler pour process_files: parse xmr_balances.csv et retourne des tuples 4 champs."""
    global _balances_data
    result = []
    with open(balances_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            wallet = row['Wallet'].strip()
            balance = row['Balance'].strip()
            date_str = row['Date'].strip()

            # Stocker pour les opérations
            _balances_data[wallet] = (balance, date_str)

            # Convert date
            date_french = parse_french_date_from_iso(date_str)

            result.append((date_french, 'Relevé compte', balance, wallet))

    return result


def format_site(site_dir, verbose=False, logger=None):
    """API pour Update."""
    if logger is None:
        from inc_logging import Logger
        logger = Logger(SITE, verbose=verbose)

    # Vérification fichiers dropbox
    from inc_format import verify_dropbox_files
    for w in verify_dropbox_files(site_dir, SITE):
        logger.warning(w)

    global _balances_data
    _balances_data = {}  # Reset à chaque appel

    handlers = [
        # Balances d'abord pour alimenter _balances_data
        ('xmr_balances.csv', _process_balances, 'pos'),
        ('xmr_*_operations.csv', _process_operations, 'ops'),
    ]
    return process_files(site_dir, handlers, verbose, SITE, logger=logger)


def log_csv_debug(operations, positions, site_dir, logger=None):
    """Wrapper vers inc_format.log_csv_debug()"""
    _log_csv_debug(SITE, operations, positions, logger)


if __name__ == '__main__':
    from inc_format import cli_main
    cli_main(format_site)
