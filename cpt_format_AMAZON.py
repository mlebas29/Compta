#!/usr/bin/env python3
"""
cpt_format_AMAZON.py - Format Amazon gift card CSV to standardized 9-field format

Input: CSV scrapé par cpt_fetch_AMAZON.py (UTF-8, point-virgule)
       Colonnes: Date;Description;Montant;Solde

Output: Tuples 9 champs (Date, Libellé, Montant, Devise, Equiv, Réf, Catégorie, Compte, Commentaire)
"""

import csv
import json
import re
from pathlib import Path
from datetime import datetime

import inc_categorize
from inc_format import process_files, log_csv_debug as _log_csv_debug, site_name_from_file

SITE = site_name_from_file(__file__)

# Nom du compte : chargé depuis config_accounts.json
_ACCOUNTS_JSON = Path(__file__).parent / 'config_accounts.json'
with open(_ACCOUNTS_JSON, 'r', encoding='utf-8') as _f:
    _amazon_config = json.load(_f).get(SITE, {})
_amazon_accounts = _amazon_config.get('accounts', [])
if not _amazon_accounts or 'name' not in _amazon_accounts[0]:
    raise ValueError('config_accounts.json [AMAZON] : aucun compte configuré')
ACCOUNT_NAME = _amazon_accounts[0]['name']

# Mois français → numéro
MOIS_FR = {
    'janvier': 1, 'février': 2, 'mars': 3, 'avril': 4,
    'mai': 5, 'juin': 6, 'juillet': 7, 'août': 8,
    'septembre': 9, 'octobre': 10, 'novembre': 11, 'décembre': 12,
    'janv': 1, 'févr': 2, 'avr': 4, 'juil': 7,
    'sept': 9, 'oct': 10, 'nov': 11, 'déc': 12,
}


def parse_amazon_csv(csv_file):
    """Parse le CSV Amazon scrapé et retourne les opérations en tuples 9 champs.

    Args:
        csv_file: Path du fichier CSV

    Returns:
        Liste de tuples 9 champs
    """
    operations = []
    last_balance = None
    last_date = None

    with open(csv_file, encoding='utf-8') as f:
        reader = csv.reader(f, delimiter=';')
        header = next(reader)  # Skip header

        for row in reader:
            if len(row) < 3:
                continue

            date_raw, description, montant_raw = row[0], row[1], row[2]
            solde_raw = row[3] if len(row) > 3 else ''

            # Ligne #SOLDE ajoutée par le fetcher
            if description == '#SOLDE':
                last_balance = _parse_amount(montant_raw)
                continue

            # Parser la date
            formatted_date = _parse_date(date_raw)
            if not formatted_date:
                continue

            # Parser le montant
            montant = _parse_amount(montant_raw)
            if montant is None:
                continue

            # Nettoyer la description (retours à la ligne, espaces multiples)
            description = ' '.join(description.split())

            # Catégorisation automatique
            category, opts = inc_categorize.categorize_operation(description, SITE)
            ref = opts.get('ref', '')
            equiv = opts.get('equiv', '')

            operations.append((
                formatted_date,
                description.strip(),
                f"{montant:.2f}",
                'EUR',
                equiv,
                ref,
                category,
                ACCOUNT_NAME,
                '',
            ))

            last_date = formatted_date

            # Tracker le solde
            balance = _parse_amount(solde_raw)
            if balance is not None:
                last_balance = balance

    # Ajouter #Solde si disponible
    if last_balance is not None and last_date:
        operations.append((
            last_date,
            f'Relevé {ACCOUNT_NAME}',
            f"{last_balance:.2f}",
            'EUR',
            '',
            '',
            '#Solde',
            ACCOUNT_NAME,
            '',
        ))

    return operations


def _parse_date(date_str):
    """Parse une date Amazon FR (ex: '2 juillet 2023', '11 nov 2023').

    Returns:
        Date au format DD/MM/YYYY ou None
    """
    date_str = date_str.strip()
    if not date_str:
        return None

    # Déjà au format DD/MM/YYYY ?
    if re.match(r'\d{2}/\d{2}/\d{4}$', date_str):
        return date_str

    # Format "2 juillet 2023" ou "11 nov 2023"
    match = re.match(r'(\d{1,2})\s+(\w+)\.?\s+(\d{4})', date_str)
    if match:
        jour = int(match.group(1))
        mois_str = match.group(2).lower().rstrip('.')
        annee = int(match.group(3))
        mois = MOIS_FR.get(mois_str)
        if mois:
            return f"{jour:02d}/{mois:02d}/{annee}"

    return None


def _parse_amount(amount_str):
    """Parse un montant Amazon (format français, peut contenir €).

    Exemples: '-1,00 €' → -1.0, '10,00 €' → 10.0, '0,00' → 0.0
    """
    if not amount_str:
        return None
    amount_str = amount_str.strip().replace('€', '').replace('\xa0', '').replace(' ', '')
    if not amount_str:
        return None
    amount_str = amount_str.replace('.', '').replace(',', '.')
    try:
        return float(amount_str)
    except ValueError:
        return None


# ============================================================================
# API POUR UPDATE
# ============================================================================

def format_site(site_dir, verbose=False, logger=None):
    """Point d'entrée pour cpt_update.py.

    Args:
        site_dir: Répertoire dropbox/AMAZON/
        verbose: Mode verbose
        logger: Logger optionnel

    Returns:
        tuple: (operations, positions)
    """
    if logger is None:
        from inc_logging import Logger
        logger = Logger(SITE, verbose=verbose)

    # Vérification fichiers dropbox
    from inc_format import verify_dropbox_files
    for w in verify_dropbox_files(site_dir, SITE):
        logger.warning(w)

    handlers = [
        ('amazon_operations.csv', parse_amazon_csv, 'ops'),
    ]

    ops, pos = process_files(site_dir, handlers, verbose, SITE, logger=logger)

    logger.verbose(f"format_site: {len(ops)} ops, {len(pos)} pos")
    return ops, pos


def log_csv_debug(operations, positions, site_dir, logger=None):
    """Wrapper vers inc_format.log_csv_debug()"""
    _log_csv_debug(SITE, operations, positions, logger)


if __name__ == '__main__':
    from inc_format import cli_main
    cli_main(format_site)
