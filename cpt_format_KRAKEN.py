#!/usr/bin/env python3
"""
Format Kraken export files (ledgers.csv and balances.csv) to standardized CSV format.

Input: ledgers.csv (operations) or balances.csv (positions)
Output: Temporary CSV file with standardized format

Tier 2 script: Raw CSV → Standardized CSV

Monoscript approach:
- ledgers.csv → 9-field operations CSV (Réserve + Titres transactions)
- balances.csv → 4-field positions CSV (Titres holdings)
"""

import sys
import csv
import re
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict
import inc_categorize
from inc_format import process_files, lines_to_tuples, log_csv_debug as _log_csv_debug, get_file_date, site_name_from_file, require_account

SITE = site_name_from_file(__file__)

# Account names : chargés depuis config_accounts.json
import json
_ACCOUNTS_JSON = Path(__file__).parent / 'config_accounts.json'
with open(_ACCOUNTS_JSON, 'r', encoding='utf-8') as _f:
    _kraken_config = json.load(_f).get(SITE, {})
_kraken_accounts = {a['name']: a['name'] for a in _kraken_config.get('accounts', [])}
ACCOUNT_EUR = require_account(_kraken_accounts, 'EUR', SITE)
ACCOUNT_BTC = require_account(_kraken_accounts, 'BTC', SITE)

# Asset types
FIAT_ASSETS = {'EUR', 'USD', 'GBP', 'CHF'}
CRYPTO_ASSETS = {'BTC', 'ETH', 'SOL', 'ADA', 'DOT'}  # Add more as needed

# Crypto units conversion
SATOSHI_PER_BTC = 100_000_000  # 1 BTC = 100,000,000 satoshis

def log(message, verbose=False):
    """Print log message if verbose mode enabled."""
    if verbose:
        print(f"[KRAKEN_FORMAT] {message}", file=sys.stderr)


def extract_zips(zip_path, dest_dir, verbose=False):
    """Extrait les fichiers CSV d'un ZIP Kraken et les renomme selon la convention.

    Pour les exports Kraken, l'utilisateur télécharge 2 ZIP :
    - kraken-ledgers-*.zip (contient ledgers.csv)
    - kraken-balances-*.zip (contient YYYY-MM-DD_balances.csv)

    Cette fonction extrait les CSV et les renomme selon la convention :
    - ledgers.csv → operations_compte-kraken_parsed.csv
    - *balances*.csv → positions_compte-kraken_parsed.csv

    Args:
        zip_path: Path du fichier ZIP
        dest_dir: Path du répertoire de destination
        verbose: Activer les logs

    Returns:
        list: Liste des fichiers CSV extraits (Path objects)
    """
    import zipfile

    zip_path = Path(zip_path)
    dest_dir = Path(dest_dir)
    extracted_files = []

    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            # Lister les fichiers CSV dans le ZIP
            csv_files = [f for f in zf.namelist() if f.endswith('.csv')]

            if not csv_files:
                print(f"⚠ [KRAKEN] ZIP '{zip_path.name}' ne contient pas de fichiers CSV", file=sys.stderr)
                return extracted_files

            for csv_file in csv_files:
                # Extraire dans le répertoire de destination
                zf.extract(csv_file, dest_dir)
                extracted_path = dest_dir / csv_file

                # Renommer selon la convention
                if 'balances' in csv_file.lower():
                    renamed_path = dest_dir / 'positions_compte-kraken_parsed.csv'
                elif 'ledgers' in csv_file.lower():
                    renamed_path = dest_dir / 'operations_compte-kraken_parsed.csv'
                else:
                    renamed_path = extracted_path

                # Renommer si nécessaire
                if renamed_path != extracted_path:
                    if renamed_path.exists():
                        renamed_path.unlink()  # Supprimer si existe déjà
                    extracted_path.rename(renamed_path)
                    log(f"Extrait: {csv_file} → {renamed_path.name}", verbose)
                else:
                    log(f"Extrait: {csv_file}", verbose)

                extracted_files.append(renamed_path)

    except Exception as e:
        log(f"Erreur extraction {zip_path.name}: {e}", verbose=True)

    return extracted_files


def parse_kraken_date(date_str):
    """
    Parse Kraken date format to DD/MM/YYYY.

    Args:
        date_str: Date string in format "YYYY-MM-DD HH:MM:SS"

    Returns:
        Date string in format DD/MM/YYYY
    """
    # Extract date part (YYYY-MM-DD) from datetime string
    date_part = date_str.split()[0]
    dt = datetime.strptime(date_part, '%Y-%m-%d')
    return dt.strftime('%d/%m/%Y')

def get_asset_type(asset):
    """Determine if asset is fiat or crypto."""
    return 'fiat' if asset in FIAT_ASSETS else 'crypto'

def parse_ledgers_csv(csv_file, verbose=False):
    """
    Parse Kraken ledgers.csv file (operations).

    CSV format:
    txid,refid,time,type,subtype,aclass,subclass,asset,wallet,amount,fee,balance

    Operation types:
    - deposit: Fiat deposit (EUR) → Réserve
    - spend: Buy crypto (EUR debit) → Réserve
    - receive: Buy crypto (crypto credit) → Titres
    - (spend + receive share same refid)

    Note: Le filtrage par date est centralisé dans inc_format.process_files()

    Args:
        csv_file: Path to ledgers.csv file
        verbose: Enable verbose logging

    Returns:
        Tuple: (operations list, reserve_balance_eur)
    """
    log(f"Parsing ledgers: {csv_file.name}", verbose)

    # Read all ledger entries
    ledger_entries = []
    reserve_balance = None

    with open(csv_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            ledger_entries.append(row)

    log(f"Found {len(ledger_entries)} ledger entries", verbose)

    # Group entries by refid (to pair spend/receive for crypto purchases)
    refid_groups = defaultdict(list)
    for entry in ledger_entries:
        refid = entry['refid']
        refid_groups[refid].append(entry)

    # Process grouped entries
    operations = []

    for refid, entries in refid_groups.items():
        if len(entries) == 1:
            # Single entry (deposit, withdrawal, etc.)
            entry = entries[0]
            op = process_single_entry(entry, verbose)
            if op:
                operations.append(op)
        elif len(entries) == 2:
            # Paired entries (likely spend EUR + receive crypto)
            op_pair = process_paired_entries(entries, verbose)
            if op_pair:
                operations.extend(op_pair)
        else:
            log(f"Warning: Unexpected {len(entries)} entries for refid {refid}", verbose)
            # Process individually as fallback
            for entry in entries:
                op = process_single_entry(entry, verbose)
                if op:
                    operations.append(op)

    # Get EUR reserve balance from last EUR entry
    for entry in reversed(ledger_entries):
        if entry['asset'] == 'EUR':
            reserve_balance = float(entry['balance'])
            log(f"EUR reserve balance: {reserve_balance:.2f}", verbose)
            break

    if reserve_balance is None:
        log("Warning: No EUR balance found in ledgers, #Solde not generated", verbose)

    log(f"Extracted {len(operations)} operations, EUR balance: {reserve_balance}", verbose)

    return operations, reserve_balance

def process_single_entry(entry, verbose=False):
    """
    Process a single ledger entry (deposit, withdrawal, etc.).

    Returns:
        Operation tuple (Date, Libellé, Montant, Devise, Equiv, Réf, Catégorie, Compte, Commentaire)
        or None if entry should be skipped
    """
    op_type = entry['type']
    asset = entry['asset']
    amount = float(entry['amount'])
    fee = float(entry['fee'])
    date_str = entry['time']

    formatted_date = parse_kraken_date(date_str)

    # Determine account (separate accounts for EUR and BTC)
    asset_type = get_asset_type(asset)
    account_name = ACCOUNT_EUR if asset_type == 'fiat' else ACCOUNT_BTC

    # Build description
    if op_type == 'deposit':
        libelle = f'Dépôt {asset}'
    elif op_type == 'withdrawal':
        libelle = f'Retrait {asset}'
    else:
        # Generic fallback
        libelle = f'{op_type.capitalize()} {asset}'

    # Catégorisation automatique via patterns
    category, opts = inc_categorize.categorize_operation(libelle, SITE)
    ref = opts.get('ref', '')

    # Include fee if present
    net_amount = amount - fee if fee > 0 else amount

    # Format amount with appropriate precision (2 decimals for fiat, 8 for crypto)
    decimals = 2 if asset_type == 'fiat' else 8
    amount_str = f"{net_amount:.{decimals}f}"
    fee_str = f"{fee:.{decimals}f}" if fee > 0 else ''

    # Build operation
    operation = (
        formatted_date,
        libelle,
        amount_str,
        asset,
        '',  # Equiv (empty for now)
        ref,
        category,
        account_name,
        f'Fee: {fee_str} {asset}' if fee > 0 else ''
    )

    return operation

def process_paired_entries(entries, verbose=False):
    """
    Process paired ledger entries (spend EUR + receive crypto).

    Generates 2 symmetric operations:
    1. Réserve debit (spend EUR + fee)
    2. Titres credit (receive crypto)

    Returns:
        List of 2 operation tuples or None if pairing fails
    """
    # Identify spend and receive entries
    spend_entry = None
    receive_entry = None

    for entry in entries:
        if entry['type'] == 'spend':
            spend_entry = entry
        elif entry['type'] == 'receive':
            receive_entry = entry

    if not spend_entry or not receive_entry:
        log(f"Warning: Cannot pair entries - missing spend or receive", verbose)
        return None

    # Extract data
    date_str = spend_entry['time']
    formatted_date = parse_kraken_date(date_str)

    spend_asset = spend_entry['asset']
    spend_amount = float(spend_entry['amount'])  # Negative
    spend_fee = float(spend_entry['fee'])

    receive_asset = receive_entry['asset']
    receive_amount = float(receive_entry['amount'])  # Positive

    # Calculate net spend (include fee)
    net_spend = spend_amount - spend_fee  # More negative (e.g., -50.5 = -50 - 0.5)

    # Convert BTC amount to satoshis (Excel uses satoshis as unit)
    if receive_asset == 'BTC':
        receive_amount_display = receive_amount * SATOSHI_PER_BTC
        amount_str = f"{receive_amount_display:.0f}"  # No decimals for satoshis
    else:
        # Other cryptos: keep original precision
        receive_amount_display = receive_amount
        amount_str = f"{receive_amount_display:.8f}"

    # Catégorisation automatique via patterns (equiv déterminé par cpt_pair)
    libelle = f'Achat {receive_asset}'
    category, opts = inc_categorize.categorize_operation(libelle, SITE)
    ref = opts.get('ref', '')

    # Build symmetric operations
    # 1. EUR account debit (spend EUR)
    op_eur = (
        formatted_date,
        libelle,
        f"{net_spend:.2f}",  # Negative amount (includes fee)
        spend_asset,
        '',  # Equiv (déterminé par cpt_pair)
        ref,
        category,
        ACCOUNT_EUR,
        f'Fee: {spend_fee:.2f} {spend_asset}' if spend_fee > 0 else ''
    )

    # 2. BTC account credit (receive crypto)
    op_btc = (
        formatted_date,
        libelle,
        amount_str,  # Satoshis for BTC (no decimals)
        receive_asset,
        '',  # Equiv (déterminé par cpt_pair)
        ref,
        category,
        ACCOUNT_BTC,
        ''  # No comment
    )

    return [op_eur, op_btc]

def parse_balances_csv(csv_file, verbose=False):
    """
    Parse Kraken balances.csv file (positions).

    CSV format:
    asset,aclass,subclass,wallet,quantity,price (USD),value (USD)

    Returns:
        Tuple: (positions list, valuation_date)
    """
    log(f"Parsing balances: {csv_file.name}", verbose)

    # Extract date from filename: "2026-01-02_balances.csv"
    match = re.search(r'(\d{4}-\d{2}-\d{2})_balances\.csv', csv_file.name)
    if match:
        date_str = match.group(1)
        valuation_date = datetime.strptime(date_str, '%Y-%m-%d').strftime('%d/%m/%Y')
    else:
        log(f"Warning: Cannot extract date from filename, using file date", verbose)
        valuation_date = get_file_date(csv_file)

    positions = []

    with open(csv_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            asset = row['asset']
            quantity = row['quantity']
            value_usd = row['value (USD)']

            # Skip Total line
            if asset == 'Total':
                continue

            # Skip EUR (already in #Solde Réserve from operations)
            if asset == 'EUR':
                continue

            # Only process crypto assets (Titres)
            if get_asset_type(asset) != 'crypto':
                continue

            # Parse value (remove thousands separator)
            value = float(value_usd.replace(',', ''))

            # Build position line
            # Format: Date;Ligne;Montant;Compte
            position = (
                valuation_date,
                asset,  # Ligne (asset name)
                f"{value:.2f}",  # Montant (value in USD)
                ACCOUNT_BTC,
            )
            positions.append(position)

    log(f"Extracted {len(positions)} positions", verbose)

    return positions, valuation_date

# ============================================================================
# API POUR UPDATE - NOUVELLE INTERFACE
# ============================================================================

def format_site(site_dir, verbose=False, logger=None):
    """API pour Update.

    Note: Le filtrage par date est centralisé dans inc_format.process_files()
    """
    if logger is None:
        from inc_logging import Logger
        logger = Logger(SITE, verbose=verbose)

    # Vérification fichiers dropbox
    from inc_format import verify_dropbox_files
    for w in verify_dropbox_files(site_dir, SITE):
        logger.warning(w)

    site_dir = Path(site_dir)

    # 1. Extraire les ZIPs dans un répertoire temporaire (jamais dans dropbox!)
    temp_dir = site_dir / '.kraken_temp'
    temp_dir.mkdir(exist_ok=True)
    for zip_path in site_dir.glob('*.zip'):
        extract_zips(zip_path, temp_dir, verbose)

    # 2. Variables pour stocker le solde EUR
    reserve_balance = None

    def _parse_ledgers(f):
        nonlocal reserve_balance
        ops, balance = parse_ledgers_csv(f, verbose)
        if balance is not None:
            reserve_balance = balance
        return ops

    def _parse_balances(f):
        pos, _ = parse_balances_csv(f, verbose)
        return pos

    # 3. Handlers pour process_files (cherche dans temp_dir pour fichiers extraits)
    handlers = [
        ('*ledgers*.csv', _parse_ledgers, 'ops'),
        ('operations_*.csv', _parse_ledgers, 'ops'),
        ('*balances*.csv', _parse_balances, 'pos'),
        ('positions_*.csv', _parse_balances, 'pos'),
    ]

    # Traiter les fichiers extraits dans temp_dir
    operations, positions = process_files(temp_dir, handlers, verbose, SITE, logger=logger)

    # Nettoyer le répertoire temporaire
    import shutil
    if temp_dir.exists():
        shutil.rmtree(temp_dir)

    # 4. Ajouter #Solde EUR si connu
    if reserve_balance is not None and operations:
        solde_date = operations[-1][0]
        solde_line = (solde_date, f'Relevé {ACCOUNT_EUR}', f'{reserve_balance:.2f}',
                      'EUR', '', '', '#Solde', ACCOUNT_EUR, '')
        operations.append(solde_line)

    logger.verbose(f"format_site: {len(operations)} ops, {len(positions)} pos")
    return operations, positions


def log_csv_debug(operations, positions, site_dir, logger=None):
    """Wrapper vers inc_format.log_csv_debug()"""
    _log_csv_debug(SITE, operations, positions, logger)


if __name__ == '__main__':
    from inc_format import cli_main
    cli_main(format_site)
