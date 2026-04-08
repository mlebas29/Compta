#!/usr/bin/env python3
"""
Format Wise statement files (ZIP or XLSX) to standardized CSV format.

Input: ZIP containing multiple XLSX statements, or individual XLSX files
Output: Temporary CSV file(s) with 9-field standard format + #Solde

Tier 2 script: Raw XLSX → Standardized CSV
"""

import sys
import openpyxl
import zipfile
import re
from pathlib import Path
from datetime import datetime, timedelta
import configparser
import inc_categorize
from inc_format import process_files, lines_to_tuples, log_csv_debug as _log_csv_debug, site_name_from_file

SITE = site_name_from_file(__file__)

# Currency to account name mapping : chargé depuis config_accounts.json
import json
_ACCOUNTS_JSON = Path(__file__).parent / 'config_accounts.json'
with open(_ACCOUNTS_JSON, 'r', encoding='utf-8') as _f:
    _wise_config = json.load(_f).get(SITE, {})
CURRENCY_ACCOUNTS = {}
for _a in _wise_config.get('accounts', []):
    _name = _a['name']
    # Extraire la devise du nom (ex: "Compte Wise EUR" → "EUR")
    _parts = _name.rsplit(' ', 1)
    if len(_parts) == 2 and len(_parts[1]) == 3 and _parts[1].isupper():
        CURRENCY_ACCOUNTS[_parts[1]] = _name

def log(message, verbose=False):
    """Print log message if verbose mode enabled."""
    if verbose:
        print(f"[WISE_FORMAT] {message}", file=sys.stderr)


def extract_zips(zip_path, dest_dir, verbose=False):
    """Extrait les fichiers XLSX d'un ZIP Wise.

    Pour les relevés Wise multi-devises, l'utilisateur télécharge un ZIP contenant
    4 fichiers XLSX (EUR, USD, SGD, SEK).

    Args:
        zip_path: Path du fichier ZIP
        dest_dir: Path du répertoire de destination
        verbose: Activer les logs

    Returns:
        list: Liste des fichiers XLSX extraits (Path objects), vide si erreur ou pas de XLSX
    """
    zip_path = Path(zip_path)
    dest_dir = Path(dest_dir)
    extracted_files = []

    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            # Lister les fichiers XLSX dans le ZIP
            all_files = zf.namelist()
            xlsx_files = [f for f in all_files if f.endswith('.xlsx')]

            # Alerte si le ZIP ne contient pas de XLSX
            if not xlsx_files:
                other_extensions = set(Path(f).suffix.lower() for f in all_files if Path(f).suffix)
                if other_extensions:
                    log(
                        f"ZIP '{zip_path.name}' ne contient pas de fichiers XLSX "
                        f"(trouvé: {', '.join(sorted(other_extensions))}). "
                        f"Retélécharger le relevé au format XLSX sur wise.com",
                        verbose=True
                    )
                return []

            # Extraire les XLSX dans le répertoire de destination
            for xlsx_file in xlsx_files:
                zf.extract(xlsx_file, dest_dir)
                extracted_path = dest_dir / xlsx_file
                extracted_files.append(extracted_path)
                log(f"Extrait: {xlsx_file}", verbose)

    except Exception as e:
        log(f"Erreur extraction {zip_path.name}: {e}", verbose=True)

    return extracted_files


def extract_currency_from_filename(filename):
    """
    Extract currency code from Wise statement filename.
    Pattern: statement_XXXXXXXX_<CURRENCY>_YYYY-MM-DD_YYYY-MM-DD.xlsx

    Args:
        filename: Name of the XLSX file

    Returns:
        Currency code (EUR, USD, etc.) or None if not found
    """
    match = re.search(r'statement_\d+_([A-Z]{3})_\d{4}-\d{2}-\d{2}_\d{4}-\d{2}-\d{2}\.xlsx', filename)
    return match.group(1) if match else None

def parse_wise_date(date_value):
    """
    Parse Wise date format to DD/MM/YYYY.

    Args:
        date_value: Date string in format YYYY-MM-DD HH:MM:SS or datetime object

    Returns:
        Date string in format DD/MM/YYYY
    """
    if isinstance(date_value, datetime):
        return date_value.strftime('%d/%m/%Y')
    elif isinstance(date_value, str):
        # Extract date part (YYYY-MM-DD) from datetime string
        date_str = date_value.split()[0]
        dt = datetime.strptime(date_str, '%Y-%m-%d')
        return dt.strftime('%d/%m/%Y')
    return ''

def parse_wise_xlsx(xlsx_file, verbose=False):
    """
    Parse a Wise XLSX statement file.

    Note: Le filtrage par date est centralisé dans inc_format.process_files()

    Args:
        xlsx_file: Path to XLSX file
        verbose: Enable verbose logging

    Returns:
        Tuple: (operations list, final_balance, currency, account_name)
    """
    log(f"Parsing {xlsx_file.name}", verbose)

    # Extract currency from filename
    currency = extract_currency_from_filename(xlsx_file.name)
    if not currency:
        raise ValueError(f"Cannot extract currency from filename: {xlsx_file.name}")

    account_name = CURRENCY_ACCOUNTS.get(currency)
    if not account_name:
        raise ValueError(
            f"Devise {currency} non configurée dans cpt_format_WISE.py (CURRENCY_ACCOUNTS). "
            f"Ajouter '{currency}': 'Compte Wise {currency}' et créer le compte dans comptes.xlsx (feuille Avoirs)"
        )

    log(f"Currency: {currency}, Account: {account_name}", verbose)

    # Load workbook
    wb = openpyxl.load_workbook(xlsx_file, data_only=True)
    ws = wb['All transactions']

    operations = []
    final_balance = 0.0  # Default to 0 for empty files

    # Get final balance from row 2 (most recent transaction) regardless of filtering
    if ws.max_row >= 2:
        balance_val = ws.cell(2, 8).value  # Column H: Solde actuel
        if balance_val is not None:
            final_balance = float(balance_val)

    # Process rows (skip header row 1, start from row 2)
    for row_idx in range(2, ws.max_row + 1):
        # Column indices (1-based in openpyxl)
        wise_id = ws.cell(row_idx, 1).value  # Column A: Pièce d'identité (transaction ID)
        date_val = ws.cell(row_idx, 2).value  # Column B: Date
        amount_val = ws.cell(row_idx, 4).value  # Column D: Montant
        currency_val = ws.cell(row_idx, 5).value  # Column E: Devise
        description_val = ws.cell(row_idx, 6).value  # Column F: Description
        balance_val = ws.cell(row_idx, 8).value  # Column H: Solde actuel

        # Skip empty rows
        if not date_val or amount_val is None:
            continue

        # Format operation
        formatted_date = parse_wise_date(date_val)
        amount = float(amount_val)
        description = str(description_val) if description_val else ''

        # Catégorisation automatique via patterns
        category, opts = inc_categorize.categorize_operation(description, SITE)
        # Réf : ID Wise (TRANSFER-..., BALANCE-..., ACCRUAL_...) si dispo
        # garantit le dédoublonnage stable même si la date varie d'1 jour
        ref = str(wise_id).strip() if wise_id else opts.get('ref', '')
        equiv = opts.get('equiv', '')

        # Build operation tuple: (Date, Libellé, Montant, Devise, Equiv, Réf, Catégorie, Compte, Commentaire)
        operation = (
            formatted_date,
            description,
            f"{amount:.2f}",
            currency,
            equiv,
            ref,
            category,
            account_name,
            ''   # Commentaire
        )
        operations.append(operation)

    wb.close()

    # Reverse operations (Wise exports newest first, we need oldest first)
    operations.reverse()

    log(f"Extracted {len(operations)} operations, final balance: {final_balance:.2f} {currency}", verbose)

    return operations, final_balance, currency, account_name

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

    # Dossier temporaire pour extraction des ZIPs
    temp_dir = site_dir / '.wise_temp'
    all_operations = []

    try:
        # 1. Extraire les ZIPs présents
        for zip_path in site_dir.glob('*.zip'):
            temp_dir.mkdir(exist_ok=True)
            extract_zips(zip_path, temp_dir, verbose)

        # 2. Fonction de parsing qui ajoute le #Solde
        def _parse_xlsx(xlsx_file):
            operations, final_balance, currency, account_name = parse_wise_xlsx(
                xlsx_file, verbose
            )
            # Ne pas générer de #Solde si le statement est vide (solde réel inconnu)
            if not operations:
                return []
            # Ajouter #Solde
            solde_date = operations[-1][0]
            solde_line = (solde_date, f'Relevé {account_name}', f'{final_balance:.2f}',
                          currency, '', '', '#Solde', account_name, '')
            return operations + [solde_line]

        # 3. Handlers pour les deux répertoires
        handlers = [('statement_*.xlsx', _parse_xlsx, 'ops')]

        # Parser les XLSX extraits
        if temp_dir.exists():
            ops_temp, _ = process_files(temp_dir, handlers, verbose, SITE, logger=logger)
            all_operations.extend(ops_temp)

        # Parser les XLSX directs
        ops_direct, _ = process_files(site_dir, handlers, verbose, SITE, logger=logger)
        all_operations.extend(ops_direct)

    finally:
        # Nettoyer le dossier temporaire
        if temp_dir.exists():
            import shutil
            shutil.rmtree(temp_dir)

    logger.verbose(f"format_site: {len(all_operations)} ops, 0 pos")
    return all_operations, []


def log_csv_debug(operations, positions, site_dir, logger=None):
    """Wrapper vers inc_format.log_csv_debug()"""
    _log_csv_debug(SITE, operations, positions, logger)


if __name__ == '__main__':
    from inc_format import cli_main
    cli_main(format_site)
