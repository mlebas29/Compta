#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cpt_format_DEGIRO.py - Conversion des fichiers DEGIRO au format standard

Convertit Account.csv (format DEGIRO) vers le format standardisé 9 champs.

Format standard :
Date;Libellé;Montant;Devise;Equiv;Réf;Catégorie;Compte;Commentaire

Usage:
  ./cpt_format_DEGIRO.py Account.csv      # opérations
  ./cpt_format_DEGIRO.py Portfolio.csv    # positions

Filtres appliqués:
- Exclusion des virements internes (Virement vers votre Compte Espèces)
- Exclusion des transfers automatiques (Degiro Cash Sweep Transfer)
- Exclusion des intérêts Flatex (Flatex Interest Income)
"""

import sys
import csv
from datetime import datetime, timedelta
from pathlib import Path
import json
import inc_categorize
from inc_format import process_files, lines_to_tuples, log_csv_debug as _log_csv_debug, get_file_date, site_name_from_file, require_account

SITE = site_name_from_file(__file__)

# Noms de comptes : chargés depuis config_accounts.json
_ACCOUNTS_JSON = Path(__file__).parent / 'config_accounts.json'
with open(_ACCOUNTS_JSON, 'r', encoding='utf-8') as _f:
    _degiro_config = json.load(_f).get(SITE, {})
_degiro_accounts = [a['name'] for a in _degiro_config.get('accounts', [])]
ACCOUNT_TITRES = require_account(_degiro_accounts, 'Titres', SITE)
ACCOUNT_RESERVE = require_account(_degiro_accounts, 'Réserve', SITE)
# Nom de base pour le relevé (sans suffixe)
ACCOUNT_BASE = ACCOUNT_TITRES.rsplit(' ', 1)[0]

def parse_degiro_csv(input_file):
    """
    Parse le fichier Account.csv de DEGIRO et le convertit au format standard

    Args:
        input_file: chemin du fichier Account.csv

    Returns:
        list: opérations au format standard

    Logique de consolidation pour achats/ventes en devise étrangère:
    - Le libellé vient de l'opération USD "Achat..." ou "Vente..."
    - Le montant vient de l'opération EUR "Opération de change - Débit/Crédit"
    - Résultat: opération EUR avec libellé descriptif pour appariement Réserve/Titres

    Note: Le #Solde Réserve est généré par format_positions_csv (depuis CASH)
    """
    import re
    from collections import defaultdict

    operations = []

    # Patterns à exclure (virements internes, sweep, intérêts)
    exclude_patterns = [
        'votre Compte Espèces',  # Virements internes (vers OU depuis)
        'Degiro Cash Sweep Transfer',
        'Flatex Interest Income',
    ]

    def parse_montant(montant_str):
        """Parse montant format européen: -10.144,00 → -10144.00"""
        montant = montant_str.replace(' ', '').replace('"', '').replace('EUR', '').strip()
        montant = montant.replace('.', '').replace(',', '.')
        return montant

    def parse_date(date_str):
        """Parse date DD-MM-YYYY ou DD/MM/YYYY → DD/MM/YYYY"""
        try:
            if '-' in date_str:
                date_obj = datetime.strptime(date_str, '%d-%m-%Y')
            else:
                date_obj = datetime.strptime(date_str, '%d/%m/%Y')
            return date_obj.strftime('%d/%m/%Y')
        except ValueError:
            return date_str

    try:
        # === PASSE 1: Collecter toutes les lignes par (produit, date) ===
        raw_rows = []
        with open(input_file, 'r', encoding='utf-8-sig') as f:
            reader = csv.reader(f)
            first_row = next(reader, None)
            if first_row and 'Date' not in first_row[0]:
                raw_rows.append(first_row)
            raw_rows.extend(list(reader))

        # Grouper par (produit, date) pour consolidation
        groups = defaultdict(list)  # {(produit, date): [lignes]}

        for row in raw_rows:
            if len(row) < 8:
                continue

            date_str = row[2].strip() if len(row) > 2 else ""
            produit = row[3].strip() if len(row) > 3 else ""
            description = row[5].strip() if len(row) > 5 else ""
            devise = row[7].strip() if len(row) > 7 else "EUR"
            montant_str = row[8].strip() if len(row) > 8 else ""

            if produit and description:
                libelle = f"{produit} {description}"
            elif description:
                libelle = description
            elif produit:
                libelle = produit
            else:
                continue

            if any(pattern in libelle for pattern in exclude_patterns):
                continue

            date_formatted = parse_date(date_str)
            montant = parse_montant(montant_str)

            groups[(produit, date_formatted)].append({
                'date': date_formatted,
                'produit': produit,
                'description': description,
                'libelle': libelle,
                'devise': devise,
                'montant': montant
            })

        # === PASSE 2: Consolider les opérations ===
        for (produit, date), lignes in groups.items():
            # Séparer EUR et non-EUR
            lignes_eur = [l for l in lignes if l['devise'] == 'EUR']
            lignes_usd = [l for l in lignes if l['devise'] != 'EUR']

            # Chercher paires Achat/Vente USD + Opération de change EUR
            achat_vente_usd = None
            change_eur = None

            for l in lignes_usd:
                if re.search(r'(?i)\b(Achat|Vente)\b', l['description']):
                    achat_vente_usd = l
                    break

            for l in lignes_eur:
                if 'Opération de change' in l['description']:
                    change_eur = l
                    break

            # Consolidation: si on a Achat/Vente USD + Change EUR → fusionner
            if achat_vente_usd and change_eur:
                # Libellé de l'USD (descriptif), montant de l'EUR (réel)
                libelle_final = achat_vente_usd['libelle']
                montant_final = change_eur['montant']

                categorie, opts = inc_categorize.categorize_operation(libelle_final, SITE)
                ref = opts.get('ref', '')

                operations.append({
                    'Date': date,
                    'Libellé': libelle_final,
                    'Montant': montant_final,
                    'Devise': 'EUR',
                    'Equiv': '',
                    'Réf': ref,
                    'Catégorie': categorie,
                    'Compte': ACCOUNT_RESERVE,
                    'Commentaire': ''
                })

                # Retirer change_eur des lignes EUR (déjà traité)
                lignes_eur = [l for l in lignes_eur if l != change_eur]

            # Ajouter les autres lignes EUR (frais, dividendes, dépôts, etc.)
            for l in lignes_eur:
                # Ignorer les "Opération de change" non appariées (USD credit/debit sans Achat)
                if 'Opération de change' in l['description']:
                    continue

                categorie, opts = inc_categorize.categorize_operation(l['libelle'], SITE)
                ref = opts.get('ref', '')

                operations.append({
                    'Date': l['date'],
                    'Libellé': l['libelle'],
                    'Montant': l['montant'],
                    'Devise': 'EUR',
                    'Equiv': '',
                    'Réf': ref,
                    'Catégorie': categorie,
                    'Compte': ACCOUNT_RESERVE,
                    'Commentaire': ''
                })

        # Trier par date (plus récent en premier comme dans le fichier source)
        operations.sort(key=lambda x: datetime.strptime(x['Date'], '%d/%m/%Y'), reverse=True)

        return operations

    except Exception as e:
        print(f"❌ Erreur parsing CSV: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return []


def detect_file_type(input_file):
    """
    Détecte le type de fichier DEGIRO

    Détection par nom de fichier:
    - Account.csv → opérations
    - Portfolio.csv → positions

    Returns:
        'operations' | 'positions' | None
    """
    filename = input_file.name.lower()

    if filename == 'account.csv':
        return 'operations'
    if filename == 'portfolio.csv':
        return 'positions'

    return None


# ============================================================================
# API POUR UPDATE - NOUVELLE INTERFACE
# ============================================================================

# Variable module pour stocker le solde réserve entre handlers
_solde_reserve_cache = None


def _process_account_csv(csv_file):
    """Handler pour Account.csv - retourne les opérations.

    Note: Le filtrage par date est centralisé dans inc_format.process_files()
    """
    operations_dict = parse_degiro_csv(csv_file)
    lines = []

    for op in operations_dict:
        # Convertir en ligne CSV 9 champs
        line = f"{op['Date']};{op['Libellé']};{op['Montant']};{op['Devise']};{op['Equiv']};{op['Réf']};{op['Catégorie']};{op['Compte']};{op['Commentaire']}"
        lines.append(line)

    return lines


def _process_portfolio_csv(csv_file):
    """Handler pour Portfolio.csv - retourne les positions (4 champs) et stocke solde_reserve."""
    global _solde_reserve_cache
    positions_tuples, solde_reserve = _parse_portfolio_tuples(csv_file, verbose=False)
    _solde_reserve_cache = solde_reserve

    # Convertir tuples en lignes CSV 4 champs
    lines = []
    for pos in positions_tuples:
        lines.append(';'.join(str(x) for x in pos))
    return lines


def format_site(site_dir, verbose=False, logger=None):
    """API pour Update."""
    if logger is None:
        from inc_logging import Logger
        logger = Logger(SITE, verbose=verbose)

    # Vérification fichiers dropbox
    from inc_format import verify_dropbox_files
    for w in verify_dropbox_files(site_dir, SITE):
        logger.warning(w)

    global _solde_reserve_cache
    _solde_reserve_cache = None

    handlers = [
        ('Account.csv', _process_account_csv, 'ops'),
        ('Portfolio.csv', _process_portfolio_csv, 'pos'),
    ]
    all_operations, all_positions = process_files(site_dir, handlers, verbose, SITE, logger=logger)

    # Ajouter #Solde Réserve aux opérations si disponible (depuis Portfolio.csv)
    if _solde_reserve_cache is not None:
        date_aujourdhui = get_file_date(Path(site_dir) / 'Portfolio.csv')
        solde_op = (
            date_aujourdhui,
            f'Relevé {ACCOUNT_BASE}',
            f'{_solde_reserve_cache:.2f}',
            'EUR',
            '',  # Equiv
            '',  # Réf
            '#Solde',
            ACCOUNT_RESERVE,
            ''  # Commentaire
        )
        all_operations.append(solde_op)

    logger.verbose(f"format_site: {len(all_operations)} ops, {len(all_positions)} pos")

    return all_operations, all_positions


def _parse_portfolio_tuples(input_file, verbose=False):
    """
    Parse Portfolio.csv et retourne des tuples (pour format_site).

    Args:
        input_file: Path vers Portfolio.csv
        verbose: Activer les logs

    Returns:
        tuple: (positions_list, solde_reserve)
        - positions_list: liste de tuples 4 champs (Date;Ligne;Montant;Compte)
        - solde_reserve: float ou None
    """
    positions = {}  # {isin: (name, amount)}
    solde_reserve = None

    try:
        with open(input_file, 'r', encoding='utf-8-sig') as f:
            reader = csv.reader(f)
            header = next(reader, None)  # Sauter l'en-tête

            for row in reader:
                if len(row) < 7:
                    continue

                produit = row[0].strip()
                isin = row[1].strip()
                montant_eur = row[-1].strip()

                # Nettoyer le montant
                montant_eur = montant_eur.replace(' ', '').replace('"', '').replace(',', '.')
                try:
                    amount = float(montant_eur)
                except ValueError:
                    continue

                # Ligne CASH = solde Réserve
                if 'CASH' in produit.upper():
                    solde_reserve = amount
                    continue

                # Ignorer les lignes sans ISIN
                if not isin:
                    continue

                positions[isin] = (produit, amount)

        # Générer les tuples positions
        positions_list = []
        date_aujourdhui = get_file_date(input_file)
        # Positions titres (triées par nom)
        sorted_positions = sorted(positions.items(), key=lambda x: x[1][0])
        for isin, (name, amount) in sorted_positions:
            pos_tuple = (
                date_aujourdhui,
                name,
                f'{amount:.2f}',
                ACCOUNT_TITRES,
            )
            positions_list.append(pos_tuple)

        # Solde Titres (= somme des positions)
        solde_titres = sum(amount for _, amount in positions.values())
        solde_titres_tuple = (
            date_aujourdhui,
            '#Solde Titres',
            f'{solde_titres:.2f}',
            ACCOUNT_TITRES,
        )
        positions_list.append(solde_titres_tuple)

        # Note: #Solde Réserve est ajouté aux opérations dans format_site()
        # (pas en position pour éviter doublon via conversion cpt_update)

        if verbose:
            print(f"[DEGIRO_FORMAT] ✓ {len(positions)} positions parsées", file=sys.stderr)

        return positions_list, solde_reserve

    except Exception as e:
        if verbose:
            print(f"[DEGIRO_FORMAT] ❌ Erreur parsing Portfolio.csv: {e}", file=sys.stderr)
        return [], None


def log_csv_debug(operations, positions, site_dir, logger=None):
    """Wrapper vers inc_format.log_csv_debug()"""
    _log_csv_debug(SITE, operations, positions, logger)


if __name__ == '__main__':
    from inc_format import cli_main
    cli_main(format_site)
