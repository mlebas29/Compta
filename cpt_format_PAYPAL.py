#!/usr/bin/env python3
"""
cpt_format_PAYPAL.py - Format PayPal CSV to standardized 9-field format

Input: CSV téléchargé depuis paypal.com/reports/dlog (UTF-8 BOM, virgule)
Output: Tuples 9 champs (Date, Libellé, Montant, Devise, Equiv, Réf, Catégorie, Compte, Commentaire)

Colonnes CSV PayPal utilisées:
  - Date (col 0) : DD/MM/YYYY
  - Nom (col 3) : bénéficiaire/payeur → Libellé
  - Type (col 4) : type d'opération → complète le libellé
  - Devise (col 6) : EUR
  - Net (col 9) : montant net après commission
  - Commission (col 8) : frais PayPal (opération séparée si non nulle)
  - Titre de l'objet (col 15) : détail → Commentaire
  - Solde (col 29) : solde courant → #Solde
  - Impact sur le solde (col 40) : Crédit/Débit/Mémo → filtre Mémo
"""

import csv
import io
import json
from pathlib import Path

import inc_categorize
from inc_format import process_files, log_csv_debug as _log_csv_debug, site_name_from_file

SITE = site_name_from_file(__file__)

# Nom du compte : chargé depuis config_accounts.json
_ACCOUNTS_JSON = Path(__file__).parent / 'config_accounts.json'
with open(_ACCOUNTS_JSON, 'r', encoding='utf-8') as _f:
    _paypal_config = json.load(_f).get(SITE, {})
_paypal_accounts = _paypal_config.get('accounts', [])
if not _paypal_accounts or 'name' not in _paypal_accounts[0]:
    raise ValueError('config_accounts.json [PAYPAL] : aucun compte configuré')
ACCOUNT_NAME = _paypal_accounts[0]['name']


def parse_paypal_csv(csv_file):
    """Parse un CSV PayPal et retourne les opérations en tuples 9 champs.

    Args:
        csv_file: Path du fichier CSV

    Returns:
        Liste de tuples 9 champs
    """
    raw = csv_file.read_bytes()
    # Supprimer le BOM UTF-8 si présent
    if raw.startswith(b'\xef\xbb\xbf'):
        raw = raw[3:]
    text = raw.decode('utf-8')

    reader = csv.reader(io.StringIO(text))
    header = next(reader)

    # Mapper les colonnes par nom pour robustesse
    col_idx = {name.strip('"'): i for i, name in enumerate(header)}

    operations = []
    last_balance = None
    last_date = None

    for row in reader:
        if not row or len(row) < 10:
            continue

        # Colonnes clés
        date_raw = _get(row, col_idx, 'Date', '')
        nom = _get(row, col_idx, 'Nom', '')
        op_type = _get(row, col_idx, 'Type', '')
        devise = _get(row, col_idx, 'Devise', '')
        net_raw = _get(row, col_idx, 'Net', '')
        commission_raw = _get(row, col_idx, 'Commission', '')
        objet = _get(row, col_idx, "Titre de l'objet", '')
        balance_raw = _get(row, col_idx, 'Solde', '')
        impact = _get(row, col_idx, 'Impact sur le solde', '')

        # Filtrer les lignes "Mémo" (pas d'impact sur le solde)
        if impact.strip().lower() == 'mémo':
            continue

        # Parser la date (DD/MM/YYYY tel quel)
        formatted_date = _parse_date(date_raw)
        if not formatted_date:
            continue

        # Parser le montant net
        net = _parse_amount(net_raw)
        if net is None:
            continue

        # Construire le libellé
        label = _build_label(nom, op_type)

        # Catégorisation automatique
        category, opts = inc_categorize.categorize_operation(label, SITE)
        ref = opts.get('ref', '')
        equiv = opts.get('equiv', '')

        # Commentaire : titre de l'objet si présent
        commentaire = objet.strip() if objet.strip() else ''

        operations.append((
            formatted_date,
            label,
            f"{net:.2f}",
            devise.strip(),
            equiv,
            ref,
            category,
            ACCOUNT_NAME,
            commentaire,
        ))

        # Commission PayPal séparée (si non nulle)
        commission = _parse_amount(commission_raw)
        if commission is not None and commission != 0.0:
            operations.append((
                formatted_date,
                f"Commission PayPal ({nom})" if nom else "Commission PayPal",
                f"{commission:.2f}",
                devise.strip(),
                '',
                '',
                'Frais bancaires',
                ACCOUNT_NAME,
                '',
            ))

        # Tracker le solde le plus récent
        balance = _parse_amount(balance_raw)
        if balance is not None:
            last_balance = balance
            last_date = formatted_date

    # Ajouter #Solde si on a un solde
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


def _get(row, col_idx, name, default=''):
    """Récupère une colonne par nom avec fallback."""
    idx = col_idx.get(name)
    if idx is not None and idx < len(row):
        return row[idx]
    return default


def _parse_date(date_str):
    """Parse une date PayPal (DD/MM/YYYY) et la retourne telle quelle.

    PayPal FR exporte en DD/MM/YYYY — c'est déjà le format cible.
    """
    date_str = date_str.strip()
    if not date_str:
        return None
    # Vérifier le format DD/MM/YYYY
    parts = date_str.split('/')
    if len(parts) == 3 and len(parts[2]) == 4:
        return date_str
    return None


def _parse_amount(amount_str):
    """Parse un montant PayPal (format français : virgule décimale, espace séparateur).

    Exemples: "1 234,56" → 1234.56, "-12,34" → -12.34, "" → None
    """
    amount_str = amount_str.strip().replace('\xa0', '').replace(' ', '')
    if not amount_str:
        return None
    # Virgule décimale → point
    amount_str = amount_str.replace('.', '').replace(',', '.')
    try:
        return float(amount_str)
    except ValueError:
        return None


def _build_label(nom, op_type):
    """Construit le libellé à partir du nom et du type d'opération.

    Si le nom est vide, utilise le type seul.
    """
    nom = nom.strip()
    op_type = op_type.strip()
    if nom and op_type:
        return f"{op_type} {nom}"
    return nom or op_type or 'PayPal'


# ============================================================================
# API POUR UPDATE
# ============================================================================

def format_site(site_dir, verbose=False, logger=None):
    """Point d'entrée pour cpt_update.py.

    Args:
        site_dir: Répertoire dropbox/PAYPAL/
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
        ('*.csv', parse_paypal_csv, 'ops'),
        ('*.CSV', parse_paypal_csv, 'ops'),
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
