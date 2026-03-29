#!/usr/bin/env python3
"""
cpt_fetch_XMR.py - Récupération automatique des wallets Monero

Prérequis:
- monero-wallet-cli installé
- Variable d'environnement COMPTA_MODE (test ou prod)
- Wallets déjà créés/restaurés dans Monero GUI

Usage:
  ./cpt_fetch_XMR.py

Fichiers générés:
  - dropbox/XMR/xmr_marc_operations.csv
  - dropbox/XMR/xmr_cake_operations.csv
  - dropbox/XMR/xmr_balances.csv
"""

import sys
import os
import configparser
import csv
import subprocess
import tempfile
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
WALLET_CLI_DIR = Path(config.get(SITE, 'wallet_cli_dir')).expanduser()
CREDENTIAL_ID = config.get(SITE, 'credential_id')
DAEMON_ADDRESS = config.get(SITE, 'daemon_address', fallback='localhost:18081')
DAEMON_CREDENTIAL_ID = config.get(SITE, 'daemon_credential_id', fallback='').strip()
MAX_DAYS_BACK = config.getint(SITE, 'max_days_back', fallback=90)
WALLET_TIMEOUT = config.getint(SITE, 'wallet_timeout', fallback=300)
WALLET_DIR = Path(config.get(SITE, 'wallet_dir', fallback='~/Monero/wallets')).expanduser()

# Wallet mapping : chargé depuis config_accounts.json
import json
_ACCOUNTS_JSON = BASE_DIR / 'config_accounts.json'
with open(_ACCOUNTS_JSON, 'r', encoding='utf-8') as _f:
    _xmr_config = json.load(_f).get(SITE, {})
XMR_WALLETS = {
    a['wallet_key']: {
        'path': WALLET_DIR / a['wallet_name'] / a['wallet_name'],
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


def check_daemon_connection(daemon_address, daemon_login=None, timeout=10):
    """
    Check if Monero daemon is accessible via RPC

    Args:
        daemon_address: Daemon address (format: "host:port")
        daemon_login: Optional authentication (format: "username:password")
        timeout: Connection timeout in seconds

    Returns:
        True if daemon is accessible, False otherwise
    """
    try:
        # Build RPC URL
        url = f"http://{daemon_address}/get_info"

        # Prepare auth if needed (Monero uses HTTP Digest Auth)
        auth = None
        if daemon_login and ':' in daemon_login:
            username, password = daemon_login.split(':', 1)
            auth = HTTPDigestAuth(username, password)

        logger.debug(f"Testing daemon connection: {url}")

        # Send RPC request
        response = requests.post(
            url,
            json={},
            auth=auth,
            timeout=timeout
        )

        if response.status_code == 200:
            data = response.json()
            # Monero RPC returns either 'result' (JSON-RPC 2.0) or direct fields
            if 'result' in data:
                height = data['result'].get('height', 'unknown')
                logger.info(f"✓ Daemon accessible (block height: {height})")
                return True
            elif 'height' in data:
                # Direct format (non JSON-RPC wrapper)
                height = data.get('height', 'unknown')
                logger.info(f"✓ Daemon accessible (block height: {height})")
                return True
            else:
                logger.warning(f"Daemon responded but unexpected JSON format")
                logger.debug(f"Response keys: {list(data.keys())}")
                return False
        elif response.status_code == 401:
            logger.error("✗ Daemon authentication failed (401 Unauthorized)")
            return False
        else:
            logger.error(f"✗ Daemon returned status {response.status_code}")
            return False

    except requests.exceptions.ConnectionError:
        logger.error(f"✗ Connection refused: {daemon_address}")
        return False
    except requests.exceptions.Timeout:
        logger.error(f"✗ Connection timeout: {daemon_address}")
        return False
    except Exception as e:
        logger.error(f"✗ Daemon check failed: {e}")
        logger.debug(f"Exception details: {type(e).__name__}")
        return False


def call_wallet_cli(wallet_path, password, command, wallet_cli_path, daemon_login=None, timeout=60):
    """
    Execute monero-wallet-cli command

    Args:
        wallet_path: Path to wallet file
        password: Wallet password
        command: CLI command (e.g., "show_transfers")
        wallet_cli_path: Path to monero-wallet-cli binary
        daemon_login: Optional daemon authentication (format: "username:password")
        timeout: Command timeout in seconds

    Returns:
        Command output (stdout)
    """
    # Create temporary password file (more secure than --password)
    pass_fd, pass_file = tempfile.mkstemp(suffix='.pwd', text=True)
    try:
        # Write password and close fd
        os.write(pass_fd, password.encode('utf-8'))
        os.close(pass_fd)

        # Set permissions to 600
        os.chmod(pass_file, 0o600)

        # Build CLI command
        cli_binary = wallet_cli_path / 'monero-wallet-cli'
        if not cli_binary.exists():
            raise FileNotFoundError(f"monero-wallet-cli not found at {cli_binary}")

        cmd = [
            str(cli_binary),
            '--wallet-file', str(wallet_path),
            '--password-file', pass_file,
            '--daemon-address', DAEMON_ADDRESS,
        ]

        # Add daemon authentication if provided
        if daemon_login:
            cmd.extend(['--daemon-login', daemon_login])

        cmd.extend([
            '--trusted-daemon',
            '--command', command
        ])

        # Log command (hide passwords)
        log_cmd = f"monero-wallet-cli --wallet-file {wallet_path.name} --daemon-address {DAEMON_ADDRESS}"
        if daemon_login:
            log_cmd += " --daemon-login ***:***"
        log_cmd += f" --trusted-daemon --command {command}"
        logger.debug(f"Executing: {log_cmd}")

        # Run command
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False
        )

        if result.returncode != 0:
            logger.error(f"CLI command failed (exit {result.returncode})")
            logger.debug(f"stderr: {result.stderr}")
            return None

        # Check stderr for daemon connection issues (CLI returns 0 with cached data)
        if result.stderr:
            stderr_lower = result.stderr.lower()
            if 'failed to connect' in stderr_lower or 'no connection to daemon' in stderr_lower:
                logger.error(f"⚠ Wallet CLI: daemon inaccessible (données cachées ignorées)")
                logger.debug(f"stderr: {result.stderr}")
                return None

        return result.stdout

    except subprocess.TimeoutExpired:
        logger.error(f"CLI command timed out after {timeout}s")
        return None
    except Exception as e:
        logger.error(f"CLI execution failed: {e}")
        return None
    finally:
        # Delete temp password file
        try:
            os.unlink(pass_file)
        except:
            pass


def parse_balance(output):
    """
    Parse output of 'balance' command

    Output format example:
    Currently selected account: [0] Primary account
    Tag: (No tag assigned)
    Balance: 10.780241990000, unlocked balance: 10.780241990000

    Returns:
        Balance in XMR (float), or 0 if parsing fails
    """
    if not output:
        return 0.0

    for line in output.split('\n'):
        # Look for "Balance: X.XXX, unlocked balance: Y.YYY"
        if 'Balance:' in line and 'unlocked balance:' in line:
            try:
                # Extract first number after "Balance:"
                parts = line.split('Balance:')[1].split(',')[0].strip()
                balance = float(parts)
                logger.debug(f"Parsed balance: {balance} XMR")
                return balance
            except (ValueError, IndexError) as e:
                logger.warning(f"Failed to parse balance line: {line}")
                logger.debug(f"Parse error: {e}")
                continue

    logger.warning("No balance line found in output")
    return 0.0


def parse_show_transfers(output, max_days_back):
    """
    Parse output of 'show_transfers' command

    Output format example (tab-separated):
         0      in 2024-12-01 10:23:45  3.500000000000 <txid> <payment_id> 0 0.000000000000 1
         1     out 2024-12-05 15:30:12  1.000000000000 <txid> <payment_id> 0.000500000000 0.000000000000 2

    Columns (space-separated):
    0: Index
    1: Type (in/out/pending/failed/pool)
    2: Date
    3: Time
    4: Amount (XMR)
    5: Txid
    6: Payment ID
    7: Fee (for outgoing)
    8: ??? (always 0?)
    9: Confirmations

    Returns:
        List of operations: [{'date': str, 'type': str, 'amount': float, 'fee': float}, ...]
    """
    if not output:
        return []

    operations = []
    cutoff_date = datetime.now() - timedelta(days=max_days_back)

    for line in output.split('\n'):
        line = line.strip()
        if not line or line.startswith('Loaded') or 'show_transfers' in line:
            continue

        # Split by whitespace, but be careful with multiple spaces
        parts = line.split()
        if len(parts) < 9:
            logger.debug(f"Line has {len(parts)} parts, skipping: {line}")
            continue

        try:
            # Extract fields
            # Format: index type status date time amount ...
            # Example: 3437921 in unlocked 2025-06-20 05:44:18 3.444110140000 ...
            # Special case: 3589187 in 4 blks 2026-01-16 16:00:16 0.885786670000 ...
            logger.debug(f"Parsing line: {line}")
            logger.debug(f"Parts: {parts}")
            index = parts[0]
            tx_type = parts[1]

            # Handle "N blks" format (recent unconfirmed transactions)
            if parts[3] == 'blks':
                # Format: index type N blks date time amount ...
                status = f"{parts[2]} blks"  # e.g., "4 blks"
                date_str = parts[4]  # YYYY-MM-DD
                time_str = parts[5]  # HH:MM:SS
                amount_str = parts[6]
            else:
                # Standard format: index type status date time amount ...
                status = parts[2]  # unlocked/locked/pending/failed/-
                date_str = parts[3]  # YYYY-MM-DD
                time_str = parts[4]  # HH:MM:SS
                amount_str = parts[5]

            # Skip if not a transaction line
            if tx_type not in ['in', 'out', 'pending', 'failed', 'pool']:
                continue

            # Skip pending/failed/pool transactions
            if tx_type in ['pending', 'failed', 'pool']:
                logger.debug(f"Skipping {tx_type} transaction")
                continue

            # Parse date
            try:
                tx_date = datetime.strptime(date_str, '%Y-%m-%d')
            except ValueError:
                logger.debug(f"Invalid date format: {date_str}")
                continue

            # Check cutoff
            if tx_date < cutoff_date:
                logger.debug(f"Skipping old transaction: {date_str}")
                continue

            # Parse amount
            amount = float(amount_str)

            # Parse fee (for outgoing only)
            fee = 0.0
            if tx_type == 'out':
                try:
                    # Fee index depends on format
                    fee_idx = 11 if parts[3] == 'blks' else 8
                    if len(parts) > fee_idx:
                        fee = float(parts[fee_idx])
                except (ValueError, IndexError):
                    pass

            # Format datetime
            datetime_str = f"{date_str} {time_str}"

            # Add operation
            operations.append({
                'date': datetime_str,
                'type': tx_type,
                'amount': amount if tx_type == 'in' else -amount,
                'fee': fee,
                'label': 'Incoming transfer' if tx_type == 'in' else 'Outgoing transfer'
            })

        except (ValueError, IndexError) as e:
            logger.debug(f"Failed to parse line: {line}")
            logger.debug(f"Parse error: {e}")
            continue

    logger.debug(f"Parsed {len(operations)} operations")
    return operations


def fetch_xmr_wallet(wallet_key, wallet_info, password, daemon_login, max_days_back):
    """
    Fetch XMR wallet transactions and balance

    Args:
        wallet_key: Wallet identifier (e.g., 'marc')
        wallet_info: Wallet configuration dict
        password: Wallet password
        daemon_login: Daemon authentication (format: "username:password", or None)
        max_days_back: Maximum days back from today

    Returns:
        Tuple: (operations_list, balance_xmr)
    """
    wallet_path = wallet_info['path']
    display_name = wallet_info['display_name']

    logger.info(f"Fetching wallet {display_name} ({wallet_path.name})")

    # Verify wallet exists
    if not wallet_path.exists():
        logger.error(f"Wallet file not found: {wallet_path}")
        return [], 0.0

    # Fetch balance
    logger.debug("Executing: balance")
    balance_output = call_wallet_cli(wallet_path, password, 'balance', WALLET_CLI_DIR, daemon_login, timeout=WALLET_TIMEOUT)
    balance = 0.0
    if balance_output:
        balance = parse_balance(balance_output)
        logger.info(f"Balance: {balance} XMR")
    else:
        logger.warning(f"Failed to fetch balance for {wallet_key}")

    # Fetch transfers
    logger.debug("Executing: show_transfers")
    transfers_output = call_wallet_cli(wallet_path, password, 'show_transfers', WALLET_CLI_DIR, daemon_login, timeout=WALLET_TIMEOUT)
    operations = []
    if transfers_output:
        operations = parse_show_transfers(transfers_output, max_days_back)
        logger.info(f"Extracted {len(operations)} operations")

        # Add fee as separate operation if present
        operations_with_fees = []
        for op in operations:
            operations_with_fees.append(op)
            if op['fee'] > 0:
                operations_with_fees.append({
                    'date': op['date'],
                    'type': 'fee',
                    'amount': -op['fee'],
                    'fee': 0.0,
                    'label': 'Transaction fee'
                })
        operations = operations_with_fees
    else:
        logger.warning(f"Failed to fetch transfers for {wallet_key}")

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
    logger.info(f"Daemon: {DAEMON_ADDRESS}")
    logger.info(f"Max days back: {MAX_DAYS_BACK}")
    logger.info("=" * 60)

    # Create dropbox directory
    DROPBOX_DIR.mkdir(parents=True, exist_ok=True)

    # Get wallet password from credentials
    logger.info(f"Loading wallet credentials from GPG ({CREDENTIAL_ID})")
    try:
        login, password = inc_gpg_credentials.get_credentials_from_gpg(
            CREDENTIALS_FILE,
            CREDENTIAL_ID,
            verbose=DEBUG
        )
        if not password:
            logger.error(f"Wallet credentials not found for {CREDENTIAL_ID}")
            return 1

        logger.info("✓ Wallet password loaded")

    except Exception as e:
        logger.error(f"Failed to load wallet credentials: {e}")
        return 1

    # Get daemon credentials if configured
    daemon_login = None
    if DAEMON_CREDENTIAL_ID:
        logger.info(f"Loading daemon credentials from GPG ({DAEMON_CREDENTIAL_ID})")
        try:
            daemon_user, daemon_pass = inc_gpg_credentials.get_credentials_from_gpg(
                CREDENTIALS_FILE,
                DAEMON_CREDENTIAL_ID,
                verbose=DEBUG
            )
            if daemon_user and daemon_pass:
                daemon_login = f"{daemon_user}:{daemon_pass}"
                logger.info("✓ Daemon credentials loaded (authenticated)")
            else:
                logger.warning(f"Daemon credentials not found for {DAEMON_CREDENTIAL_ID}")
        except Exception as e:
            logger.warning(f"Failed to load daemon credentials: {e}")
            logger.info("Continuing without daemon authentication")
    else:
        logger.info("No daemon authentication configured")

    # Check daemon connection before starting
    logger.info(f"Checking daemon connection: {DAEMON_ADDRESS}")
    if not check_daemon_connection(DAEMON_ADDRESS, daemon_login):
        logger.error("=" * 60)
        logger.error("✗ Daemon not accessible - aborting")
        logger.error("Hint: Start Monero daemon (monerod or Monero GUI)")
        logger.error("=" * 60)
        return 1

    # Fetch all wallets
    all_balances = []
    success_count = 0

    for wallet_key, wallet_info in XMR_WALLETS.items():
        try:
            # Fetch wallet
            operations, balance = fetch_xmr_wallet(
                wallet_key,
                wallet_info,
                password,
                daemon_login,
                MAX_DAYS_BACK
            )

            # Write operations CSV
            ops_file = DROPBOX_DIR / f"{wallet_info['output_key']}_operations.csv"
            write_operations_csv(operations, wallet_key, ops_file)

            # Store balance
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
