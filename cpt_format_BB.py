#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cpt_format_BB.py - Convertit les CSV BoursoBank en format standardisé

Format d'entrée (opérations bancaires):
  dateOp;dateVal;label;category;categoryParent;supplierFound;amount;comment;accountNum;accountLabel;accountbalance

Format d'entrée (mouvements titres):
  Date opération;Date valeur;Opération;Valeur;Code ISIN;Montant;Quantité;Cours

Format de sortie standardisé (9 champs):
  Date;Libellé;Montant;Devise;Equiv;Réf;Catégorie;Compte;Commentaire

Note: Les positions titres (name;isin;quantity;...) ne sont PAS formatées
      → elles sont parsées directement par cpt_update.py pour Plus_value

Usage:
  ./cpt_format_BB.py <fichier.csv>
"""

import sys
import csv
import re
from pathlib import Path
from datetime import datetime
import inc_categorize
from inc_format import process_files, lines_to_tuples, log_csv_debug as _log_csv_debug, get_file_date, site_name_from_file

SITE = site_name_from_file(__file__)

try:
    import pdfplumber
except ImportError:
    pdfplumber = None


# Mapping numéro → nom compte : chargé depuis config_accounts.json
import json
_ACCOUNTS_JSON = Path(__file__).parent / 'config_accounts.json'
with open(_ACCOUNTS_JSON, 'r', encoding='utf-8') as _f:
    _bb_config = json.load(_f).get('BB', {})
ACCOUNT_MAPPING = {
    a['numero']: a['name']
    for a in _bb_config.get('accounts', [])
    if 'numero' in a
}
_bb_accounts = [a['name'] for a in _bb_config.get('accounts', [])]
ACCOUNT_TITRES = next((n for n in _bb_accounts if 'Titres' in n), 'Portefeuille BB Titres')
ACCOUNT_RESERVE = next((n for n in _bb_accounts if 'Réserve' in n), 'Portefeuille BB Réserve')
ACCOUNT_BASE = ACCOUNT_TITRES.rsplit(' ', 1)[0] if ' Titres' in ACCOUNT_TITRES else 'Portefeuille BB'


def format_date(date_str):
    """
    Convertit YYYY-MM-DD en DD/MM/YYYY ou garde DD/MM/YYYY
    """
    date_str = date_str.strip()

    # Si déjà au format DD/MM/YYYY
    if re.match(r'\d{2}/\d{2}/\d{4}', date_str):
        return date_str

    # Si format YYYY-MM-DD (BoursoBank)
    if re.match(r'\d{4}-\d{2}-\d{2}', date_str):
        try:
            dt = datetime.strptime(date_str, '%Y-%m-%d')
            return dt.strftime('%d/%m/%Y')
        except:
            pass

    return date_str


def format_amount(amount_str):
    """
    Convertit le montant en format décimal avec virgule
    Entrée: "-4 500,00" ou "1795.77" ou "-1 977,58"
    Sortie: "-4500,00" ou "1795,77" ou "-1977,58"
    """
    amount_str = str(amount_str).strip()

    # Retirer les espaces
    amount_str = amount_str.replace(' ', '')

    # Retirer les guillemets
    amount_str = amount_str.replace('"', '')

    # Si point décimal, convertir en virgule
    if '.' in amount_str and ',' not in amount_str:
        amount_str = amount_str.replace('.', ',')

    # S'assurer qu'on a 2 décimales
    if ',' in amount_str:
        parts = amount_str.split(',')
        if len(parts[1]) == 1:
            amount_str = amount_str + '0'
    else:
        amount_str = amount_str + ',00'

    return amount_str


def process_bank_operations(input_file):
    """
    Traite les opérations bancaires (compte principal, livret)
    Format: dateOp;dateVal;label;category;categoryParent;supplierFound;amount;comment;accountNum;accountLabel;accountbalance

    Note: Le filtrage par date est centralisé dans inc_format.process_files()
    Note: Le champ accountbalance du CSV n'est PAS fiable (solde obsolète).
    Les #Solde sont générés par process_pdf_accueil() (PDF page accueil).
    """
    output_lines = []
    operations = []
    account_name = None

    with open(input_file, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f, delimiter=';')

        for row in reader:
            date_str = format_date(row['dateOp'])
            label = row['label'].strip().replace('"', '')

            # Normaliser les libellés composites "XXX | YYY" → garder seulement la partie après le pipe
            # Fix: BoursoBank a changé le format des libellés (déc 2025)
            # Ancien: "VIR Virement depuis XXX"
            # Nouveau: "Vir Virement Depuis XXX | VIR Virement depuis XXX"
            if ' | ' in label:
                label = label.split(' | ')[1]  # Garder la partie après le pipe (format stable)

            amount = format_amount(row['amount'])
            category = row['category'].strip() if row['category'] else ''
            account_num = row['accountNum'].strip()

            # Mapper le compte
            account_name = ACCOUNT_MAPPING.get(account_num, row['accountLabel'].strip())

            operations.append({
                'date_str': date_str,
                'label': label,
                'amount': amount,
                'category': category,
                'account_name': account_name
            })

    # Générer les lignes formatées
    for op in operations:
        # Catégorisation automatique via patterns
        cat, opts = inc_categorize.categorize_operation(op['label'], SITE)
        ref = opts.get('ref', '')

        # Format standardisé (pas de commentaire pour opérations bancaires)
        output_line = f"{op['date_str']};{op['label']};{op['amount']};EUR;;{ref};{cat};{op['account_name']};"
        output_lines.append(output_line)

    # Note: Les #Solde sont générés par process_pdf_accueil() (pas ici)
    return output_lines


def process_stock_movements(input_file):
    """
    Traite les mouvements titres (transactions boursières) - compte Réserve
    Format: Date opération;Date valeur;Opération;Valeur;Code ISIN;Montant;Quantité;Cours

    Note: Le filtrage par date est centralisé dans inc_format.process_files()
    Note: Ces opérations concernent le compte Portefeuille BB Réserve (Espèces).
    """
    output_lines = []
    operations = []

    with open(input_file, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f, delimiter=';')

        for row in reader:
            date_str = format_date(row['Date opération'])
            operation = row['Opération'].strip()
            valeur = row['Valeur'].strip() if row['Valeur'] else ''
            montant = format_amount(row['Montant'])

            # Construire le libellé avec détails
            if valeur:
                label = f"{operation} {valeur}"
            else:
                label = operation

            operations.append({
                'date_str': date_str,
                'label': label,
                'montant': montant
            })

    # Générer les lignes formatées
    for op in operations:
        # Catégorisation automatique via patterns
        category, opts = inc_categorize.categorize_operation(op['label'], SITE)
        ref = opts.get('ref', '')

        # Format standardisé - Portefeuille BB Réserve
        output_line = f"{op['date_str']};{op['label']};{op['montant']};EUR;;{ref};{category};{ACCOUNT_RESERVE};"
        output_lines.append(output_line)

    return output_lines


def process_pdf_accueil(input_file):
    """
    Parse le PDF de la page d'accueil BoursoBank pour extraire les soldes

    Format attendu dans le PDF (texte extrait) :
    - "Compte principal" suivi de "XXX,XX €"
    - "Livret Bourso+" suivi de "XXX,XX €"
    - "Portefeuille titres" ignoré (solde Réserve extrait du PDF portefeuille)

    Returns:
        list: lignes de soldes au format "Date;Libellé;Montant;Devise;;;#Solde;Compte;"
    """
    if pdfplumber is None:
        print("❌ pdfplumber non installé. Exécutez: pip3 install pdfplumber", file=sys.stderr)
        sys.exit(1)

    output_lines = []
    date_aujourdhui = get_file_date(input_file)

    with pdfplumber.open(input_file) as pdf:
        full_text = ""
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                full_text += text + "\n"

    if not full_text:
        print("⚠ PDF vide ou illisible", file=sys.stderr)
        return []

    # Extraire les soldes avec regex
    # Pattern: "Nom compte" ... "XXX,XX €" ou "XXX XXX,XX €"
    lines = full_text.split('\n')

    current_compte = None

    for line in lines:
        line = line.strip()

        # Détecter le type de compte
        if 'Compte principal' in line:
            current_compte = 'Compte chèque BB'
        elif 'Livret Bourso+' in line:
            current_compte = 'Compte livret BB'
        elif 'Portefeuille titres' in line:
            current_compte = ACCOUNT_BASE

        # Chercher les montants
        # Pattern pour montant: "XXX,XX €" ou "X XXX,XX €" ou "-XXX,XX €"
        montant_match = re.search(r'([-−]?\s*[\d\s]+,\d{2})\s*€', line)

        if montant_match and current_compte:
            montant_str = montant_match.group(1).replace(' ', '').replace('−', '-')
            montant_str = montant_str.replace(',', '.')

            try:
                montant = float(montant_str)
            except ValueError:
                continue

            # Pour le portefeuille, ignorer (solde Réserve extrait du PDF portefeuille)
            if current_compte == ACCOUNT_BASE:
                current_compte = None
                continue

            # Générer la ligne de solde (Chèque et Livret)
            montant_fmt = f"{montant:.2f}".replace('.', ',')
            output_line = f"{date_aujourdhui};Relevé compte;{montant_fmt};EUR;;;#Solde;{current_compte};"
            output_lines.append(output_line)
            current_compte = None

    return output_lines


def process_pdf_portefeuille(input_file):
    """
    Parse le PDF de la page portefeuille BoursoBank pour extraire le solde Espèces.

    Ce PDF est imprimé depuis la page /bourse/portefeuille et contient
    le détail du portefeuille titres dont le "Solde Espèces" (= Réserve).

    Returns:
        list: lignes de positions au format "Date;#Solde;Montant;Compte"
    """
    if pdfplumber is None:
        print("❌ pdfplumber non installé. Exécutez: pip3 install pdfplumber", file=sys.stderr)
        sys.exit(1)

    with pdfplumber.open(input_file) as pdf:
        full_text = ""
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                full_text += text + "\n"

    if not full_text:
        print("⚠ PDF portefeuille vide ou illisible", file=sys.stderr)
        return []

    # Chercher le solde Espèces (patterns BoursoBank)
    # Patterns possibles : "Solde Espèces XXX,XX €", "Espèces XXX,XX €"
    solde_especes = None
    for line in full_text.split('\n'):
        line_stripped = line.strip()
        if re.search(r'[Ee]sp[èe]ces', line_stripped):
            montant_match = re.search(r'([-−]?\s*[\d\s]+,\d{2})\s*€', line_stripped)
            if montant_match:
                montant_str = montant_match.group(1).replace(' ', '').replace('−', '-')
                montant_str = montant_str.replace(',', '.')
                try:
                    solde_especes = float(montant_str)
                except ValueError:
                    continue

    if solde_especes is None:
        print("⚠ Solde Espèces non trouvé dans le PDF portefeuille", file=sys.stderr)
        return []

    date_aujourdhui = get_file_date(input_file)

    return [f'{date_aujourdhui};#Solde Réserve;{solde_especes:.2f};{ACCOUNT_RESERVE}']


def detect_file_type(input_file):
    """
    Détecte le type de fichier BoursoBank (CSV ou PDF)

    Détection basée sur:
    1. Extension (.pdf)
    2. Nom de fichier (noms originaux BoursoBank)
    3. Contenu du header (fallback pour CSV)

    Returns:
        'pdf_accueil'     : PDF page accueil (soldes)
        'bank_operations' : opérations bancaires (compte principal, livret)
        'stock_movements' : mouvements titres (achats/ventes) - Portefeuille BB Réserve
        'positions'       : positions titres (à ne PAS formatter)
        'soldes'          : soldes parsed (à ne PAS formatter)
        None              : type non reconnu
    """
    filename = input_file.name.lower()
    ext = input_file.suffix.lower()

    # Fichiers PDF
    if ext == '.pdf':
        if 'portefeuille' in filename:
            return 'pdf_portefeuille'
        return 'pdf_accueil'

    # Noms après renommage (export_compte_principal.csv, export_livret_bourso.csv)
    if filename.startswith('export_compte') or filename.startswith('export_livret'):
        return 'bank_operations'

    # Noms originaux BoursoBank (compatibilité collecte manuelle)
    if filename == 'export.csv' or filename == 'export (1).csv':
        return 'bank_operations'

    if filename == 'positions.csv':
        return 'positions'

    if filename.startswith('export-positions-instantanees'):
        return 'positions'

    # export-operations-*.csv : type déterminé par contenu (bank_operations ou stock_movements)
    # → fallback par contenu ci-dessous

    # Fallback: détection par contenu header
    with open(input_file, 'r', encoding='utf-8-sig') as f:
        first_line = f.readline().strip()

    # Enlever les guillemets pour la détection
    first_line_clean = first_line.replace('"', '')

    # Positions titres
    if first_line_clean.startswith('name;isin;quantity'):
        return 'positions'

    # Opérations bancaires
    if 'dateOp;dateVal;label' in first_line_clean:
        return 'bank_operations'

    # Mouvements titres
    if 'Date opération;Date valeur;Opération;Valeur;Code ISIN' in first_line_clean:
        return 'stock_movements'

    return None


def process_positions(input_files):
    """
    Traite les fichiers positions BB (format 4 colonnes)

    Fusionne plusieurs fichiers si nécessaire (discriminants)
    Génère le Solde Titres = somme des positions.
    Note: Le Solde Réserve est extrait du PDF portefeuille (process_pdf_portefeuille).

    Returns:
        list: lignes au format Date;Ligne;Montant;Compte
    """
    # Mapping des noms de titres (correction des variations de labellisation par la banque)
    TITRE_MAPPING = {
        'NORTH ATLANTIC ENERGIES': 'ESSO',
        'NORT ATLA ENERG': 'ESSO',
    }

    # Parser tous les fichiers positions
    all_positions = {}
    dropbox_dir = None
    first_file = None

    for input_file in input_files:
        if not input_file.exists():
            continue

        # Ignorer les fichiers non-CSV (PDF, etc.)
        if input_file.suffix.lower() != '.csv':
            continue

        if first_file is None:
            first_file = input_file
        dropbox_dir = input_file.parent

        # Parser positions (format: name;isin;quantity;buyingPrice;lastPrice;intradayVariation;amount;amountVariation;variation)
        try:
            with open(input_file, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f, delimiter=';')
                for row in reader:
                    isin = row['isin'].strip()
                    name = row['name'].strip()
                    amount_str = row['amount'].strip()

                    # Appliquer le mapping des noms de titres (normalisation)
                    name = TITRE_MAPPING.get(name, name)

                    # Nettoyer le montant
                    amount_str = amount_str.replace(' ', '').replace('"', '').replace(',', '.')
                    try:
                        amount = float(amount_str)
                    except ValueError:
                        continue

                    # Dédupliquer par ISIN (garder le dernier)
                    all_positions[isin] = (name, amount)
        except Exception as e:
            print(f"⚠ Erreur lecture {input_file.name}: {e}", file=sys.stderr)

    if not all_positions:
        return []

    # Calculer la somme des titres
    somme_titres = sum(amount for name, amount in all_positions.values())

    # Générer les lignes au format unifié
    output_lines = []
    date_aujourdhui = get_file_date(first_file)
    # Positions titres (triées par nom)
    sorted_positions = sorted(all_positions.items(), key=lambda x: x[1][0])
    for isin, (name, amount) in sorted_positions:
        output_lines.append(f'{date_aujourdhui};{name};{amount:.2f};{ACCOUNT_TITRES}')

    # Solde Titres = somme des positions
    output_lines.append(f'{date_aujourdhui};#Solde Titres;{somme_titres:.2f};{ACCOUNT_TITRES}')

    # Note: Le Solde Réserve est extrait du PDF portefeuille (process_pdf_portefeuille)

    return output_lines


# ============================================================================
# API POUR UPDATE - NOUVELLE INTERFACE
# ============================================================================

def _process_csv_by_type(csv_file):
    """Wrapper pour traiter les CSV selon leur type détecté."""
    file_type = detect_file_type(csv_file)
    if file_type == 'bank_operations':
        return process_bank_operations(csv_file)
    elif file_type == 'stock_movements':
        return process_stock_movements(csv_file)
    return []


def _process_positions_wrapper(position_files_list):
    """Wrapper pour process_positions qui accepte une liste de fichiers."""
    def processor(csv_file):
        # Collecter tous les fichiers positions du même répertoire
        site_dir = csv_file.parent
        position_files = []
        for pattern in ['positions.csv', 'export-positions-instantanees*.csv']:
            position_files.extend(site_dir.glob(pattern))
        if position_files and csv_file in position_files:
            # Ne traiter qu'une fois (quand on rencontre le premier fichier)
            if csv_file == min(position_files, key=lambda f: f.name):
                return process_positions(position_files)
        return []
    return processor


def _deduplicate_cross_file_ops(ops_by_file):
    """Déduplique les opérations présentes dans plusieurs fichiers export-operations.

    Les doublons intra-fichier sont conservés (légitimes).
    Seuls les doublons inter-fichiers sont éliminés.

    Pour chaque ligne présente dans N fichiers, on garde les occurrences
    du fichier qui en a le plus (préserve les doublons intra-fichier légitimes).

    Args:
        ops_by_file: dict {filename: [lines]} (résultats de _process_csv_by_type)

    Returns:
        list: lignes dédupliquées
    """
    if len(ops_by_file) < 2:
        result = []
        for lines in ops_by_file.values():
            result.extend(lines)
        return result

    # Compter occurrences par ligne par fichier
    line_per_file = {}  # line -> {fname: count}
    for fname, lines in ops_by_file.items():
        for line in lines:
            d = line_per_file.setdefault(line, {})
            d[fname] = d.get(fname, 0) + 1

    # Pour les lignes cross-fichier, choisir le fichier propriétaire (max occurrences)
    line_owner = {}
    for line, fmap in line_per_file.items():
        if len(fmap) > 1:
            line_owner[line] = max(fmap, key=lambda f: fmap[f])

    # Émettre les lignes, exclure les cross-fichier non propriétaires
    result = []
    n_dedup = 0
    for fname, lines in ops_by_file.items():
        for line in lines:
            if line in line_owner and line_owner[line] != fname:
                n_dedup += 1
                continue
            result.append(line)

    if n_dedup > 0:
        print(f"⚠ [BB] {n_dedup} opération(s) en doublon inter-fichiers export-operations ignorée(s)", file=sys.stderr)

    return result


def format_site(site_dir, verbose=False, logger=None):
    """API pour Update.

    Ordre de traitement :
    1. PDFs : accueil (soldes Chèque/Livret) + portefeuille (solde Espèces/Réserve)
    2. Positions CSV (Titres uniquement)
    3. Opérations CSV
    """
    if logger is None:
        from inc_logging import Logger
        logger = Logger(SITE, verbose=verbose)

    # Vérification fichiers dropbox
    from inc_format import verify_dropbox_files
    for w in verify_dropbox_files(site_dir, SITE):
        logger.warning(w)

    site_dir = Path(site_dir)

    logger.verbose(f"format_site: {site_dir}")

    # Phase 1: PDFs
    handlers_pdf = [
        ('Mes Comptes - BoursoBank.pdf', process_pdf_accueil, 'ops'),
        ('Portefeuille - BoursoBank.pdf', process_pdf_portefeuille, 'pos'),
    ]
    ops_pdf, pos_pdf = process_files(site_dir, handlers_pdf, verbose, SITE, logger=logger)

    # Phase 2: Positions CSV (Titres uniquement, Réserve vient du PDF portefeuille)
    handlers_pos = [
        ('positions.csv', _process_positions_wrapper([]), 'pos'),
        ('export-positions-instantanees*.csv', _process_positions_wrapper([]), 'pos'),
    ]
    _, pos_csv = process_files(site_dir, handlers_pos, verbose, SITE, logger=logger)
    all_positions = pos_pdf + pos_csv

    # Phase 3: Opérations CSV (détection par type)
    # 3a: export-operations avec dédup cross-fichier (recouvrement entre fetchs)
    export_files = sorted(site_dir.glob('export-operations-*.csv'))

    if len(export_files) >= 2:
        ops_by_file = {}
        for f in export_files:
            logger.verbose(f"export-operations: {f.name}")
            ops_by_file[f.name] = _process_csv_by_type(f)
        deduped = _deduplicate_cross_file_ops(ops_by_file)
        # Convertir en tuples (comme process_files)
        ops_export = []
        for item in deduped:
            if isinstance(item, str):
                ops_export.append(tuple(item.split(';')))
            elif isinstance(item, (list, tuple)):
                ops_export.append(tuple(item))
    else:
        ops_export = []  # sera traité par process_files ci-dessous

    # 3b: Autres CSV (skip export-operations si déjà traités en 3a)
    skip_exports = len(export_files) >= 2

    def _process_csv_phase3(csv_file):
        """Wrapper qui skip les export-operations déjà traités en 3a."""
        if skip_exports and csv_file.name.startswith('export-operations-'):
            return []
        return _process_csv_by_type(csv_file)

    handlers_ops = [
        ('*.csv', _process_csv_phase3, 'ops'),
    ]
    ops_other, _ = process_files(site_dir, handlers_ops, verbose, SITE, logger=logger)
    ops_csv = ops_export + ops_other

    all_operations = ops_pdf + ops_csv

    logger.verbose(f"format_site: {len(all_operations)} ops, {len(all_positions)} pos")

    return all_operations, all_positions


def log_csv_debug(operations, positions, site_dir, logger=None):
    """Wrapper vers inc_format.log_csv_debug()"""
    _log_csv_debug(SITE, operations, positions, logger)


if __name__ == '__main__':
    from inc_format import cli_main
    cli_main(format_site)
