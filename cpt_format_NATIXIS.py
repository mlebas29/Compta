#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cpt_format_PEE.py - Convertit les fichiers PEE en format standardisé

Format d'entrée (operations_*.csv):
  Date;Nature;Montant;Statut

Format d'entrée (supports_*.csv):
  Nom;Montant

Format d'entrée (PDF imprimé):
  PDF imprimé depuis le site HSBC (fallback collecte manuelle)

Format de sortie standardisé (9 champs):
  Date;Libellé;Montant;Devise;Equiv;Réf;Catégorie;Compte;Commentaire

Usage:
  ./cpt_format_PEE.py <fichier.csv|.pdf>
  cat fichier.csv | ./cpt_format_PEE.py
"""

import sys
import re
from pathlib import Path
from datetime import datetime
import json
import inc_categorize
from inc_format import process_files, lines_to_tuples, log_csv_debug as _log_csv_debug, get_file_date, site_name_from_file

SITE = site_name_from_file(__file__)

# Nom du compte : chargé depuis config_accounts.json
_ACCOUNTS_JSON = Path(__file__).parent / 'config_accounts.json'
with open(_ACCOUNTS_JSON, 'r', encoding='utf-8') as _f:
    _natixis_config = json.load(_f).get(SITE, {})
_natixis_accounts = _natixis_config.get('accounts', [])
if not _natixis_accounts or 'name' not in _natixis_accounts[0]:
    raise ValueError('config_accounts.json [NATIXIS] : aucun compte configuré')
ACCOUNT_NAME = _natixis_accounts[0]['name']

try:
    import pdfplumber
except ImportError:
    pdfplumber = None


def format_date(date_str):
    """
    Convertit DD/MM/YYYY en DD/MM/YYYY (déjà au bon format)
    """
    date_str = date_str.strip()
    if re.match(r'\d{2}/\d{2}/\d{4}', date_str):
        return date_str
    return date_str


def format_amount(amount_str):
    """
    Convertit le montant en format avec virgule décimale
    Entrée: "10000,00" ou "10 000,00"
    Sortie: "10000,00"
    """
    amount_str = amount_str.strip()
    # Retirer les espaces (séparateurs de milliers)
    amount_str = amount_str.replace(' ', '')
    # S'assurer qu'on a une virgule décimale
    if ',' not in amount_str:
        amount_str = amount_str + ',00'
    return amount_str


def process_operations(input_file):
    """
    Traite les opérations PEE
    Format entrée: Date;Nature;Montant;Statut

    Note: Le filtrage par date est centralisé dans inc_format.process_files()
    """
    output_lines = []
    operations = []
    solde_op = None

    with open(input_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    # Ignorer l'en-tête - stocker les opérations
    for line in lines[1:]:
        line = line.strip()
        if not line:
            continue

        fields = line.split(';')
        if len(fields) < 4:
            continue

        date_str = format_date(fields[0])
        nature = fields[1].strip()
        montant = format_amount(fields[2])

        # #Solde toujours ajouté (pas de filtrage)
        if nature == "#Solde":
            solde_op = {
                'date_str': date_str,
                'nature': nature,
                'montant': montant,
            }
        else:
            operations.append({
                'date_str': date_str,
                'nature': nature,
                'montant': montant,
            })

    # Générer les lignes formatées
    for op in operations:
        commentaire = ""

        # Déterminer le libellé selon le type d'opération
        if "Modification" in op['nature']:
            # Arbitrage: intégrer le montant dans le libellé
            libelle = f"{op['nature']} ({op['montant']}€)"
            montant = "0,00"  # Arbitrage = somme nulle
        elif op['nature'].startswith("Remboursement"):
            # Remboursement = virement sortant (négatif)
            montant = op['montant']
            if not montant.startswith('-'):
                montant = '-' + montant
            libelle = op['nature']
        else:
            libelle = op['nature']
            montant = op['montant']

        # Catégorisation automatique via patterns
        categorie, opts = inc_categorize.categorize_operation(libelle, SITE)
        ref = opts.get('ref', '')

        # Format standardisé: Date;Libellé;Montant;Devise;Equiv;Réf;Catégorie;Compte;Commentaire
        output_line = f"{op['date_str']};{libelle};{montant};EUR;;{ref};{categorie};{ACCOUNT_NAME};{commentaire}"
        output_lines.append(output_line)

    # Ajouter #Solde à la fin
    if solde_op:
        output_line = f"{solde_op['date_str']};Relevé compte;{solde_op['montant']};EUR;;;#Solde;{ACCOUNT_NAME};"
        output_lines.append(output_line)

    return output_lines


def process_positions(input_file):
    """
    Traite les valorisations de supports PEE (format 4 colonnes)
    Format entrée: Nom;Montant
    Format sortie: Date;Ligne;Montant;Compte
    """
    import re

    output_lines = []
    date_aujourdhui = get_file_date(input_file)
    compte = ACCOUNT_NAME
    total_solde = 0.0

    with open(input_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    # Ignorer l'en-tête
    for line in lines[1:]:
        line = line.strip()
        if not line:
            continue

        fields = line.split(';')
        if len(fields) < 2:
            continue

        nom = fields[0].strip()
        montant_str = fields[1].strip()

        # Ignorer TOTAL ÉPARGNE
        if nom == 'TOTAL ÉPARGNE':
            continue

        # Parser le montant (format anglo-saxon: 44,180.60 ou français: 44 180,60)
        montant_str = re.sub(r'[€\s]', '', montant_str)  # Retirer € et espaces
        # Détecter le format: si contient '.' et ',', c'est anglo-saxon
        if '.' in montant_str and ',' in montant_str:
            # Format anglo-saxon: 44,180.60 -> retirer virgule et garder point
            montant_str = montant_str.replace(',', '')
        elif ',' in montant_str:
            # Format français: 44180,60 -> remplacer virgule par point
            montant_str = montant_str.replace(',', '.')
        # Sinon: format avec point uniquement (44180.60), rien à faire

        try:
            montant = float(montant_str)
        except ValueError:
            continue

        # Format: Date;Ligne;Montant;Compte
        output_lines.append(f'{date_aujourdhui};{nom};{montant:.2f};{compte}')
        total_solde += montant

    # NE PAS ajouter #Solde ici - déjà dans le fichier operations
    # Le #Solde PEE vient du fichier operations_pee_parsed.csv (ligne "#Solde;87886,22")
    # et sera importé via process_operations() dans le fichier temporaire operations

    return output_lines


def process_pdf_printed(file_path):
    """
    Parse un PDF imprimé depuis l'interface web Natixis Interépargne PEE

    Deux types de PDF supportés :
    1. "Historique et suivi de mes opérations" → Opérations
       Format: Nom opération / Total XXX,XX EUR / Date de la demande DD/MM/YYYY / Statut Réalisée

    2. "Mon épargne en détail" → Positions + Solde
       Format: Estimation au DD/MM/YYYY / Plan d'épargne : XXX,XX EUR
               HSBC EE xxx / Voir la fiche / Épargne sur ce fonds : XXX,XX EUR

    Retourne (output_lines, header)
    """
    if pdfplumber is None:
        print("❌ pdfplumber non installé. Exécutez: pip3 install pdfplumber", file=sys.stderr)
        sys.exit(1)

    COMPTE = ACCOUNT_NAME
    operations = []
    positions = []
    solde = None
    date_estimation = None

    with pdfplumber.open(file_path) as pdf:
        full_text = ""
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                full_text += text + "\n"

        if not full_text:
            return [], "Date;Libellé;Montant;Devise;Equiv;Réf;Catégorie;Compte;Commentaire"

        # Détecter le type de PDF
        is_operations_pdf = "Historique et suivi" in full_text
        is_positions_pdf = "Mon épargne en détail" in full_text or "Estimation au" in full_text

        if is_operations_pdf:
            # === PDF OPÉRATIONS (format tableau Selenium print_page) ===
            # Format fragmenté sur plusieurs lignes :
            #   Ligne n  : "Description ... Montant Montant"
            #   Ligne n+1: "DD/MM/YYYY [suite] Réalisée"
            #   Ligne n+2: "suite description EUR EUR"
            #
            # Exemples :
            #   "31/10/2025 Réalisée" (montants et desc sur ligne précédente)
            #   "24/01/2025 6 970,98 EUR 6 970,98 EUR Réalisée"
            #   "06/10/2023 Modification de placements Réalisée"

            lines = full_text.split('\n')
            op_keywords = ('Modification', 'Modi�cation', 'INVESTISSEMENT',
                           'Remboursement', 'Versement', 'Attribution',
                           'Transfert', 'Arbitrage')

            for i, line in enumerate(lines):
                line = line.strip()

                # Pattern: DD/MM/YYYY ... Réalisée
                op_match = re.match(r'^(\d{2}/\d{2}/\d{4})\s*(.*?)\s*Réalisée$', line)
                if not op_match:
                    continue

                date_str = op_match.group(1)
                content = op_match.group(2).strip()

                # Chercher montants et description
                montant = 0.0
                nature = None

                # 1. Chercher dans le contenu de la ligne courante
                montants = re.findall(r'([\d\s]+,\d{2})\s*EUR', content)
                if montants:
                    montant_str = montants[-1].replace(' ', '').replace(',', '.')
                    try:
                        montant = float(montant_str)
                    except ValueError:
                        pass

                for kw in op_keywords:
                    if kw in content:
                        desc_match = re.match(r'^(.+?)\s+[\d\s]+,\d{2}', content)
                        if desc_match:
                            nature = desc_match.group(1).strip()
                        else:
                            nature = content
                        break

                # 2. Chercher sur ligne précédente si pas trouvé
                if i > 0:
                    prev_line = lines[i-1].strip()

                    # Montants sur ligne précédente
                    if montant == 0.0:
                        prev_montants = re.findall(r'([\d\s]+,\d{2})', prev_line)
                        if prev_montants:
                            montant_str = prev_montants[-1].replace(' ', '').replace(',', '.')
                            try:
                                montant = float(montant_str)
                            except ValueError:
                                pass

                    # Description sur ligne précédente
                    if not nature:
                        for kw in op_keywords:
                            if kw in prev_line:
                                # Extraire jusqu'aux montants
                                desc_match = re.match(r'^(.+?)\s+[\d\s]+,\d{2}', prev_line)
                                if desc_match:
                                    nature = desc_match.group(1).strip()
                                else:
                                    nature = prev_line
                                break

                # Default
                if not nature:
                    nature = content if content else 'Opération PEE'

                # Fix encoding issues
                nature = nature.replace('�', 'fi')

                operations.append({
                    'date_str': date_str,
                    'nature': nature,
                    'montant': f"{montant:.2f}".replace('.', ','),
                })

        elif is_positions_pdf:
            # === PDF POSITIONS ===
            # Chercher la date d'estimation
            date_match = re.search(r'Estimation au\s+(\d{2}/\d{2}/\d{4})', full_text)
            if date_match:
                date_estimation = date_match.group(1)

            # Chercher le solde total
            solde_match = re.search(r'Plan d\'épargne\s*:\s*([\d\s]+,\d{2})\s*EUR', full_text)
            if solde_match:
                montant_str = solde_match.group(1).replace(' ', '').replace(',', '.')
                try:
                    solde = float(montant_str)
                except ValueError:
                    pass

            # Parser les positions ligne par ligne
            # Structure :
            #   HSBC EE xxx E (ou G)
            #   Voir la fiche
            #   Épargne sur ce fonds : XXX,XX EUR
            lines = full_text.split('\n')
            current_fonds = None

            for line in lines:
                line = line.strip()
                if not line:
                    continue

                # Détection d'un nom de fonds HSBC EE
                # Le nom peut être suivi de texte parasite (bandeau cookies intercalé par pdfplumber)
                fonds_match = re.match(r'^(HSBC EE[A-Z\s\-]+[EG])\b', line, re.IGNORECASE)
                if fonds_match:
                    current_fonds = fonds_match.group(1).strip()
                    continue

                # Ignorer "Voir la fiche"
                if line == "Voir la fiche":
                    continue

                # Épargne sur ce fonds : XXX,XX EUR
                if current_fonds:
                    epargne_match = re.match(r'^Épargne sur ce fonds\s*:\s*([\d\s]+,\d{2})\s*EUR', line)
                    if epargne_match:
                        montant_str = epargne_match.group(1).replace(' ', '').replace(',', '.')
                        try:
                            montant = float(montant_str)
                            if montant > 0:
                                positions.append({
                                    'nom': current_fonds,
                                    'montant': montant
                                })
                        except ValueError:
                            pass
                        current_fonds = None
                        continue

    # Générer les lignes d'opérations formatées
    # Note: Le filtrage par date est centralisé dans inc_format.process_files()
    output_lines = []
    for op in operations:
        nature = op['nature']
        montant = op['montant']

        # Traitement spécial pour certains types d'opérations
        if "Modification" in nature:
            libelle = f"{nature} ({montant}€)"
            montant = "0,00"
        elif nature.startswith("Remboursement"):
            if not montant.startswith('-'):
                montant = '-' + montant
            libelle = nature
        else:
            libelle = nature

        categorie, opts = inc_categorize.categorize_operation(libelle, SITE)
        ref = opts.get('ref', '')

        output_line = f"{op['date_str']};{libelle};{montant};EUR;;{ref};{categorie};{COMPTE};"
        output_lines.append(output_line)

    # Déterminer le type de sortie
    if positions:
        # Format positions (4 colonnes)
        date_out = date_estimation or get_file_date(file_path)
        pos_lines = []
        for pos in positions:
            pos_lines.append(f"{date_out};{pos['nom']};{pos['montant']:.2f};{COMPTE}")
        # Ajouter #Solde à la fin du fichier positions
        if solde is not None:
            pos_lines.append(f"{date_out};#Solde;{solde:.2f};{COMPTE}")
        return pos_lines, "Date;Ligne;Montant;Compte"
    else:
        # Format opérations (9 colonnes)
        return output_lines, "Date;Libellé;Montant;Devise;Equiv;Réf;Catégorie;Compte;Commentaire"


# ============================================================================
# API POUR UPDATE - NOUVELLE INTERFACE
# ============================================================================

# Variable module pour stocker les positions PDF (communication entre handlers)
_pdf_positions = []


def _process_pdf_wrapper(pdf_file):
    """Wrapper pour process_pdf_printed - retourne les ops, stocke les pos."""
    global _pdf_positions
    output_lines, header = process_pdf_printed(pdf_file)
    if "Ligne" in header:
        # Format positions - stocker dans variable module, retourner liste vide
        _pdf_positions.extend(output_lines)
        return []
    else:
        # Format opérations - retourner directement
        return output_lines


def format_site(site_dir, verbose=False, logger=None):
    """API pour Update."""
    if logger is None:
        from inc_logging import Logger
        logger = Logger(SITE, verbose=verbose)

    # Vérification fichiers dropbox
    from inc_format import verify_dropbox_files
    for w in verify_dropbox_files(site_dir, SITE):
        logger.warning(w)

    global _pdf_positions
    _pdf_positions = []  # Reset à chaque appel

    handlers = [
        ('*.pdf', _process_pdf_wrapper, 'ops'),
        ('operations*.csv', process_operations, 'ops'),
        ('supports*.csv', process_positions, 'pos'),
        ('positions*.csv', process_positions, 'pos'),
    ]
    ops, pos = process_files(site_dir, handlers, verbose, SITE, logger=logger)

    # Ajouter les positions PDF stockées par le wrapper
    pos.extend(lines_to_tuples(_pdf_positions))

    return ops, pos


def log_csv_debug(operations, positions, site_dir, logger=None):
    """Wrapper vers inc_format.log_csv_debug()"""
    _log_csv_debug(SITE, operations, positions, logger)


if __name__ == '__main__':
    from inc_format import cli_main
    cli_main(format_site)
