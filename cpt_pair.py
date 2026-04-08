#!/usr/bin/env python3
"""
Script d'appariement des opérations dans comptes.xlsm
Usage:
    cpt_pair.py                     # Exécuter les appariements (défaut)
    cpt_pair.py --pair              # Exécuter les appariements (explicite)
    cpt_pair.py --dry-run           # Simulation sans modification
    cpt_pair.py -v                  # Mode verbeux
"""

import os
import sys
import re
import argparse
import configparser
from pathlib import Path
from datetime import datetime, timedelta

import inc_mode
from inc_logging import Logger
from inc_exchange_rates import convert_to_eur
from inc_excel_import import get_valid_accounts
from inc_excel_compta import (
    ComptaExcel,
    CLASSE_TITRES,
    LINKED_OPERATIONS,
    parse_montant,
)
from inc_excel_schema import OpCol

# ============================================================================
# CONFIGURATION
# ============================================================================

BASE_DIR = inc_mode.get_base_dir()
CONFIG_FILE = BASE_DIR / 'config.ini'

config = configparser.ConfigParser()
if CONFIG_FILE.exists():
    config.read(CONFIG_FILE)

DEBUG = config.getboolean('general', 'DEBUG', fallback=False) if CONFIG_FILE.exists() else False
LOGS_DIR = BASE_DIR / (config.get('paths', 'logs', fallback='./logs') if CONFIG_FILE.exists() else 'logs')
COMPTES_FILE = BASE_DIR / (config.get('paths', 'comptes_file', fallback='./comptes.xlsm') if CONFIG_FILE.exists() else 'comptes.xlsm')

# ============================================================================
# CONFIGURATION DES APPARIEMENTS
# ============================================================================

# Paires de virements à appairer automatiquement
# Ces virements existent déjà des deux côtés (contrairement à LINKED_OPERATIONS
# qui génère de nouvelles opérations). On leur assigne juste une référence Vxx.
TRANSFER_PAIRS = {
    'BG_GESTION_SG': {
        'source': {
            'compte': 'Compte Les Oliviers',
            'pattern': 'Notre règlement par virement',
            'signe': 'negatif',
        },
        'dest': {
            'compte': 'Compte chèque SG',
            'pattern': 'BG GESTION',
            'signe': 'positif',
        },
        'max_jours_ecart': 7,
    },
}

# Virements internes (hub & spokes)
INTERNAL_TRANSFERS = [
    {
        'hub': 'Compte chèque SG',
        'spokes': [
            'Livret A Marc',
            'LDD Marc',
            'Compte livret SG',
            'Livret A Cécile',
            'LDD Cécile',
            'Ass vie ébène Cécile',
            'Ass vie ébène 2 Cécile',
        ],
        'pattern': 'VIR',
        'max_jours_ecart': 3,
    },
    {
        'hub': 'Compte chèque BB',
        'spokes': [
            'Compte livret BB',
            'Portefeuille BB',
        ],
        'pattern': 'VIR',
        'max_jours_ecart': 3,
    },
]

# Transferts inter-comptes (réseau maillé)
# La liste des comptes est chargée dynamiquement depuis comptes.xlsm (feuille Avoirs)
# Paramètres lus depuis config.ini [pairing], avec fallback par défaut
def _get_pairing_float(key, fallback):
    return config.getfloat('pairing', key, fallback=fallback) if CONFIG_FILE.exists() else fallback

def _get_pairing_int(key, fallback):
    return config.getint('pairing', key, fallback=fallback) if CONFIG_FILE.exists() else fallback

MESH_TRANSFERS = {
    'max_jours_same_currency': _get_pairing_int('max_jours_same_currency', 7),
    'max_jours_cross_currency': _get_pairing_int('max_jours_cross_currency', 7),
    'max_ratio_preselect': _get_pairing_float('max_ratio_preselect', 1.25),
    'max_ratio_equiv': _get_pairing_float('max_ratio_equiv', 2.0),
    'ambiguity_threshold': _get_pairing_float('ambiguity_threshold', 0.05),
}


# ============================================================================
# HELPERS
# ============================================================================

_CARD_DATE_RE = re.compile(r'CARTE\s+X\d{4}\s+(?:REMBT\s+)?(\d{2}/\d{2})\b')
_LABEL_DATE_RE = re.compile(r'(\d{2}/\d{2}/\d{4})\b')


def _extract_effective_date(op):
    """Extrait la date effective d'une opération depuis le libellé si disponible.

    Patterns reconnus :
    - Carte à débit différé : 'CARTE X0612 31/12 LECLERC' → 31/12
    - Date explicite en début de libellé : '27/01/2026 Easycash bijoux' → 27/01/2026
    Retourne date_parsed en repli.

    Toujours retourné comme datetime.date (jamais datetime.datetime) pour
    permettre les soustractions cohérentes côté appelant.
    """
    def _to_date(d):
        # Normaliser datetime → date pour éviter les TypeError de soustraction
        if hasattr(d, 'date') and callable(d.date):
            return d.date()
        return d

    # Carte à débit différé (JJ/MM sans année)
    match = _CARD_DATE_RE.match(op.label)
    if match:
        try:
            card_day, card_month = match.group(1).split('/')
            card_date = op.date_parsed.replace(day=int(card_day), month=int(card_month))
            if card_date > op.date_parsed:
                card_date = card_date.replace(year=card_date.year - 1)
            return _to_date(card_date)
        except (ValueError, TypeError):
            pass

    # Date explicite JJ/MM/AAAA en début de libellé (saisie manuelle)
    match = _LABEL_DATE_RE.match(op.label)
    if match:
        try:
            return datetime.strptime(match.group(1), '%d/%m/%Y').date()
        except (ValueError, TypeError):
            pass

    return _to_date(op.date_parsed)


# ============================================================================
# CLASSE PRINCIPALE
# ============================================================================

class ComptaPairer:
    """Appariement des opérations dans comptes.xlsm"""

    def __init__(self, comptes_file=None, verbose=False, dry_run=False):
        self.comptes_file = Path(comptes_file) if comptes_file else COMPTES_FILE
        self.verbose = verbose
        self.dry_run = dry_run

        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        self.logger = Logger(
            script_name="cpt_pair",
            journal_file=LOGS_DIR / "journal.log",
            verbose=self.verbose,
            debug=DEBUG
        )

        # Composition : accès Excel délégué à ComptaExcel
        self.excel = ComptaExcel(
            comptes_file=self.comptes_file,
            verbose=verbose,
            logger=self.logger,
        )

        self.stats = {
            'paired': 0,
            'phases': {},
        }

    # ====================================================================
    # Phase 1 : Appariement des opérations liées (LINKED_OPERATIONS)
    # ====================================================================

    def _match_linked_pairs(self, operations):
        """Appaire les paires originale↔symétrique générées par cpt_update

        Les opérations liées (Espèces, Créances, Titres) sont générées par
        cpt_update avec ref='-'. On les apparie ici par pattern matching.

        Critères :
        - Même date
        - Montants opposés (même valeur absolue, signes opposés)
        - Comptes correspondant aux patterns LINKED_OPERATIONS
          (ou sous-comptes Réserve↔Titres)
        - cat='Virement' ou cat='Achat titres'/'Vente titres'
        """
        matched = set()

        # Phase 1a : LINKED_OPERATIONS (Espèces, Créances)
        for pattern, config in LINKED_OPERATIONS.items():
            compte_cible = config['compte_cible']

            # Trouver les paires : op dans un compte source avec pattern dans label
            # + op dans compte_cible avec label vide, même date, montant opposé
            sources = []
            cibles = []

            for i, op in enumerate(operations):
                if i in matched:
                    continue
                if op.categorie != 'Virement':
                    continue

                label = str(op.label).upper()
                if pattern in label:
                    sources.append(i)
                elif op.compte == compte_cible and not op.label.strip():
                    cibles.append(i)

            for src_idx in sources:
                if src_idx in matched:
                    continue
                src = operations[src_idx]

                for cbl_idx in cibles:
                    if cbl_idx in matched:
                        continue
                    cbl = operations[cbl_idx]

                    # Même date
                    if src.date_parsed != cbl.date_parsed:
                        continue

                    # Montants opposés
                    if abs(src.montant_parsed + cbl.montant_parsed) > 0.01:
                        continue

                    # Match !
                    pairing_ref = self.excel.get_next_pairing_ref('Virement')
                    self.excel.write_ref_to_excel(src.row, pairing_ref, 'Virement')
                    self.excel.write_ref_to_excel(cbl.row, pairing_ref, 'Virement')
                    src.ref = pairing_ref
                    cbl.ref = pairing_ref
                    matched.add(src_idx)
                    matched.add(cbl_idx)
                    self.stats['paired'] += 1

                    self.logger.verbose(f"Appairage linked ({pattern}): {pairing_ref}")
                    break

        # Phase 1b : Titres (Réserve ↔ Titres)
        # Trouver les paires : compte Réserve ↔ compte Titres
        # même base de compte, même date, même label, montants opposés
        reserve_ops = []
        titres_ops = []

        for i, op in enumerate(operations):
            if i in matched:
                continue
            cat = op.categorie
            if cat not in ('Achat titres', 'Vente titres'):
                continue
            if 'Réserve' in op.compte:
                reserve_ops.append(i)
            elif 'Titres' in op.compte:
                titres_ops.append(i)

        for r_idx in reserve_ops:
            if r_idx in matched:
                continue
            r_op = operations[r_idx]

            for t_idx in titres_ops:
                if t_idx in matched:
                    continue
                t_op = operations[t_idx]

                # Même base de compte (Réserve ↔ Titres)
                if r_op.compte.replace('Réserve', '') != t_op.compte.replace('Titres', ''):
                    continue
                # Même date
                if r_op.date_parsed != t_op.date_parsed:
                    continue
                # Même label
                if r_op.label != t_op.label:
                    continue
                # Montants opposés
                if abs(r_op.montant_parsed + t_op.montant_parsed) > 0.01:
                    continue

                # Match !
                cat = r_op.categorie
                devise_credit = t_op.devise if t_op.montant_parsed > 0 else r_op.devise
                pairing_ref = self.excel.get_next_pairing_ref(cat, devise_credit)
                self.excel.write_ref_to_excel(r_op.row, pairing_ref)
                self.excel.write_ref_to_excel(t_op.row, pairing_ref)
                r_op.ref = pairing_ref
                t_op.ref = pairing_ref
                matched.add(r_idx)
                matched.add(t_idx)
                self.stats['paired'] += 1

                self.logger.verbose(f"Appairage titres ({cat}): {pairing_ref}")
                break

        phase_count = len(matched) // 2
        self.stats['phases']['linked'] = phase_count
        if phase_count > 0:
            self.logger.verbose(f"Phase 1 (linked): {phase_count} paire(s)")

        # Retourner uniquement les opérations non matchées
        return [op for i, op in enumerate(operations) if i not in matched]

    # ====================================================================
    # Phase 2 : Appariement TRANSFER_PAIRS
    # ====================================================================

    def _match_transfer_pairs(self, operations):
        """Appaire les virements entre comptes (ex: Les Oliviers <-> SG)"""

        def matches_criteria(compte, label, montant, ref, cfg):
            if compte != cfg['compte']:
                return False
            if cfg['pattern'].upper() not in str(label).upper():
                return False
            if ref != '-':
                return False
            if montant is None:
                return False
            if cfg['signe'] == 'negatif' and montant >= 0:
                return False
            if cfg['signe'] == 'positif' and montant <= 0:
                return False
            return True

        matched = set()

        for pair_name, config in TRANSFER_PAIRS.items():
            source_cfg = config['source']
            dest_cfg = config['dest']
            max_jours = config.get('max_jours_ecart', 7)

            sources = []
            dests = []

            for i, op in enumerate(operations):
                if i in matched:
                    continue
                m = op.montant_parsed
                if matches_criteria(op.compte, op.label, m, op.ref, source_cfg):
                    sources.append(i)
                elif matches_criteria(op.compte, op.label, m, op.ref, dest_cfg):
                    dests.append(i)

            matched_sources = set()
            matched_dests = set()

            for src_idx in sources:
                if src_idx in matched_sources:
                    continue
                src = operations[src_idx]

                for dst_idx in dests:
                    if dst_idx in matched_dests:
                        continue
                    dst = operations[dst_idx]

                    if abs(abs(src.montant_parsed) - abs(dst.montant_parsed)) > 0.01:
                        continue
                    if abs((src.date_parsed - dst.date_parsed).days) > max_jours:
                        continue

                    pairing_ref = self.excel.get_next_pairing_ref('Virement')
                    self.excel.write_ref_to_excel(src.row, pairing_ref, 'Virement')
                    self.excel.write_ref_to_excel(dst.row, pairing_ref, 'Virement')
                    src.ref = pairing_ref
                    dst.ref = pairing_ref
                    src.categorie = 'Virement'
                    dst.categorie = 'Virement'
                    matched.add(src_idx)
                    matched.add(dst_idx)
                    matched_sources.add(src_idx)
                    matched_dests.add(dst_idx)
                    self.stats['paired'] += 1

                    self.logger.verbose(f"Appairage {pair_name}: {pairing_ref}")
                    self.logger.verbose(f"  Source: {src.date_parsed.strftime('%d/%m/%Y')} {src.montant_parsed:+.2f}€")
                    self.logger.verbose(f"  Dest:   {dst.date_parsed.strftime('%d/%m/%Y')} {dst.montant_parsed:+.2f}€")
                    break

        phase_count = len(matched) // 2
        self.stats['phases']['transfer_pairs'] = phase_count
        if phase_count > 0:
            self.logger.verbose(f"Phase 2 (transfer_pairs): {phase_count} paire(s)")

        return [op for i, op in enumerate(operations) if i not in matched]

    # ====================================================================
    # Phase 3 : Appariement INTERNAL_TRANSFERS (hub & spokes)
    # ====================================================================

    def _match_internal_transfers(self, operations):
        """Appaire les virements internes entre hub et spokes"""

        if not INTERNAL_TRANSFERS:
            return operations

        configs = INTERNAL_TRANSFERS if isinstance(INTERNAL_TRANSFERS, list) else [INTERNAL_TRANSFERS]
        total_matched = set()

        for config in configs:
            hub = config.get('hub')
            spokes = config.get('spokes', [])
            pattern = config.get('pattern', 'VIR')
            max_jours = config.get('max_jours_ecart', 3)

            if not hub or not spokes:
                continue

            hub_ops = []
            spoke_ops = []

            for i, op in enumerate(operations):
                if i in total_matched:
                    continue
                if op.ref != '-':
                    continue
                compte = op.compte
                label = str(op.label)
                montant = op.montant_parsed

                if pattern.upper() not in label.upper():
                    continue
                if montant is None or montant == 0:
                    continue
                if compte != hub and compte not in spokes:
                    continue

                if compte == hub:
                    hub_ops.append(i)
                else:
                    spoke_ops.append(i)

            matched_hub = set()
            matched_spoke = set()

            for h_idx in hub_ops:
                if h_idx in matched_hub:
                    continue
                h_op = operations[h_idx]

                for s_idx in spoke_ops:
                    if s_idx in matched_spoke:
                        continue
                    s_op = operations[s_idx]

                    if abs(abs(h_op.montant_parsed) - abs(s_op.montant_parsed)) > 0.01:
                        continue
                    if (h_op.montant_parsed > 0) == (s_op.montant_parsed > 0):
                        continue
                    if abs((h_op.date_parsed - s_op.date_parsed).days) > max_jours:
                        continue

                    pairing_ref = self.excel.get_next_pairing_ref('Virement')
                    self.excel.write_ref_to_excel(h_op.row, pairing_ref, 'Virement')
                    self.excel.write_ref_to_excel(s_op.row, pairing_ref, 'Virement')
                    h_op.ref = pairing_ref
                    s_op.ref = pairing_ref
                    h_op.categorie = 'Virement'
                    s_op.categorie = 'Virement'
                    matched_hub.add(h_idx)
                    matched_spoke.add(s_idx)
                    total_matched.add(h_idx)
                    total_matched.add(s_idx)
                    self.stats['paired'] += 1

                    direction = "→" if h_op.montant_parsed < 0 else "←"
                    self.logger.verbose(f"Appairage interne: {pairing_ref}")
                    self.logger.verbose(f"  {hub} {h_op.montant_parsed:+.2f}€ {direction} {s_op.compte} {s_op.montant_parsed:+.2f}€")
                    break

        phase_count = len(total_matched) // 2
        self.stats['phases']['internal_transfers'] = phase_count
        if phase_count > 0:
            self.logger.verbose(f"Phase 3 (internal_transfers): {phase_count} paire(s)")

        return [op for i, op in enumerate(operations) if i not in total_matched]

    # ====================================================================
    # Phase 4 : Appariement MESH_TRANSFERS
    # ====================================================================

    def _deduce_transfer_category(self, devise1, devise2):
        """Déduit la catégorie de transfert à partir des devises des deux côtés."""
        if devise1 == devise2:
            return 'Virement'
        if devise1.endswith('Jo') or devise2.endswith('Jo'):
            return 'Achat métaux'
        return 'Change'

    def _match_equiv(self, op1, m1, equiv1, d1, op2, m2, equiv2, d2):
        """Vérifie et complète la correspondance Equiv entre deux opérations cross-currency.

        Returns:
            (equiv1, equiv2, updates) mis à jour, ou None si pas de match.
            updates = list of (row, equiv_value) to write to Excel
        """
        max_ratio = MESH_TRANSFERS.get('max_ratio_equiv', 2.0)
        min_ratio = 1.0 / max_ratio
        updates = []

        if equiv1 is not None and equiv2 is not None:
            # Wise (et cross-currency en général) : taux légèrement différents
            # de chaque côté. Si l'écart relatif est tolérable, on moyenne et
            # on force la balance à zéro en réécrivant les 2 equiv.
            diff = abs(abs(equiv1) - abs(equiv2))
            avg = (abs(equiv1) + abs(equiv2)) / 2
            if avg > 0.01 and diff / avg > max_ratio - 1.0:
                # ratio dépasse la tolérance globale (ex max_ratio=2.0 → 100%)
                return None
            if diff > 0.01:
                # Forcer balance nulle : moyenne, signes préservés
                sign1 = -1 if equiv1 < 0 else 1
                equiv1 = sign1 * avg
                equiv2 = -equiv1
                updates.append((op1.row, equiv1))
                updates.append((op2.row, equiv2))
                self.logger.verbose(
                    f"Equiv normalisés (avg) : {equiv1:+.2f}€ / {equiv2:+.2f}€")
        elif equiv1 is not None and equiv2 is None:
            d2_devise = op2.devise
            if d2_devise != 'EUR' and abs(equiv1) > 0.01:
                eur2 = convert_to_eur(abs(m2), d2_devise, d2.strftime('%Y-%m-%d'))
                if eur2 is not None:
                    ratio = eur2 / abs(equiv1)
                    if ratio < min_ratio or ratio > max_ratio:
                        return None
            equiv2 = -equiv1
            updates.append((op2.row, equiv2))
            self.logger.verbose(f"Auto-remplissage Equiv: {equiv2:+.2f}€")
        elif equiv2 is not None and equiv1 is None:
            d1_devise = op1.devise
            if d1_devise != 'EUR' and abs(equiv2) > 0.01:
                eur1 = convert_to_eur(abs(m1), d1_devise, d1.strftime('%Y-%m-%d'))
                if eur1 is not None:
                    ratio = eur1 / abs(equiv2)
                    if ratio < min_ratio or ratio > max_ratio:
                        return None
            equiv1 = -equiv2
            updates.append((op1.row, equiv1))
            self.logger.verbose(f"Auto-remplissage Equiv: {equiv1:+.2f}€")
        else:
            d1_devise = op1.devise
            d2_devise = op2.devise
            eur1 = convert_to_eur(abs(m1), d1_devise, d1.strftime('%Y-%m-%d'))
            eur2 = convert_to_eur(abs(m2), d2_devise, d2.strftime('%Y-%m-%d'))
            if eur1 is None or eur2 is None:
                return None
            if min(eur1, eur2) > 0.01:
                ratio = max(eur1, eur2) / min(eur1, eur2)
                if ratio > max_ratio:
                    return None
            avg_eur = (eur1 + eur2) / 2
            sign1 = -1 if m1 < 0 else 1
            equiv1 = sign1 * avg_eur
            equiv2 = -equiv1
            updates.append((op1.row, equiv1))
            updates.append((op2.row, equiv2))
            self.logger.verbose(f"Auto-calcul Equiv ECB: {equiv1:+.2f}€ / {equiv2:+.2f}€")

        return (equiv1, equiv2, updates)

    def _match_mesh_transfers(self, operations):
        """Appaire les transferts inter-comptes : virements et changes"""

        if not MESH_TRANSFERS:
            return operations

        # Charger les comptes depuis comptes.xlsm (feuille Avoirs, avec devise)
        accounts = set(get_valid_accounts(self.comptes_file))
        max_jours_same = MESH_TRANSFERS.get('max_jours_same_currency', 5)
        max_jours_cross = MESH_TRANSFERS.get('max_jours_cross_currency', 7)

        if not accounts:
            self.logger.warning("Aucun compte trouvé dans Avoirs — appariement mesh désactivé")
            return operations

        cross_only_cats = {'Change', 'Achat métaux'}
        titres_cats = set(CLASSE_TITRES)

        # Collecter les opérations éligibles
        eligible = []  # (index_in_operations, op)
        for i, op in enumerate(operations):
            if op.ref != '-':
                continue
            if op.compte not in accounts:
                continue
            if op.montant_parsed is None or op.montant_parsed == 0:
                continue
            eligible.append((i, op))

        matched = set()

        # Phase 1a : Same-currency
        for i, (idx1, op1) in enumerate(eligible):
            if idx1 in matched:
                continue
            cat1 = op1.categorie
            if cat1 in cross_only_cats or cat1 in titres_cats:
                continue

            for idx2, op2 in eligible[i+1:]:
                if idx2 in matched:
                    continue
                cat2 = op2.categorie
                if cat2 in cross_only_cats or cat2 in titres_cats:
                    continue
                if op1.compte == op2.compte:
                    continue
                if op1.devise != op2.devise:
                    continue
                if abs(abs(op1.montant_parsed) - abs(op2.montant_parsed)) > 0.01:
                    continue
                if (op1.montant_parsed > 0) == (op2.montant_parsed > 0):
                    continue
                d1_eff = _extract_effective_date(op1)
                d2_eff = _extract_effective_date(op2)
                if abs((d1_eff - d2_eff).days) > max_jours_same:
                    continue

                # Détecter transfert cash ↔ portefeuille
                # Réserve ne fait des virements qu'avec l'extérieur
                # Portefeuille sans Réserve dans le nom = achat/vente titres
                portfolio_op = None
                if 'Portefeuille' in op1.compte and 'Réserve' not in op1.compte:
                    portfolio_op = op1
                elif 'Portefeuille' in op2.compte and 'Réserve' not in op2.compte:
                    portfolio_op = op2

                if portfolio_op:
                    category = 'Achat titres' if portfolio_op.montant_parsed > 0 else 'Vente titres'
                else:
                    category = 'Virement'

                pairing_ref = self.excel.get_next_pairing_ref(category)
                self.excel.write_ref_to_excel(op1.row, pairing_ref, category)
                self.excel.write_ref_to_excel(op2.row, pairing_ref, category)
                op1.ref = pairing_ref
                op2.ref = pairing_ref
                op1.categorie = category
                op2.categorie = category

                # Equiv pour paires non-EUR (conversion EUR via taux de change)
                if op1.devise != 'EUR':
                    eur_val = convert_to_eur(abs(op1.montant_parsed), op1.devise,
                                             op1.date_parsed.strftime('%Y-%m-%d'))
                    if eur_val is not None:
                        sign1 = -1 if op1.montant_parsed < 0 else 1
                        eq1 = sign1 * eur_val
                        eq2 = -eq1
                        self.excel.write_equiv_to_excel(op1.row, eq1)
                        self.excel.write_equiv_to_excel(op2.row, eq2)

                matched.add(idx1)
                matched.add(idx2)
                self.stats['paired'] += 1

                self.logger.verbose(f"Appairage mesh same-ccy: {pairing_ref}")
                self.logger.verbose(f"  {op1.compte} {op1.montant_parsed:+.2f} {op1.devise} ↔ {op2.compte} {op2.montant_parsed:+.2f} {op2.devise}")
                break

        # Pré-calcul estimations EUR pour présélection Phase 4b
        max_ratio_preselect = MESH_TRANSFERS.get('max_ratio_preselect', 1.25)
        eur_estimates = {}
        for idx, op in eligible:
            if idx in matched:
                continue
            eq = parse_montant(self.excel.ws_operations.cell(op.row, OpCol.EQUIV).value)
            if eq is not None:
                eur_estimates[idx] = abs(eq)
            elif op.devise == 'EUR':
                eur_estimates[idx] = abs(op.montant_parsed)
            else:
                eur_val = convert_to_eur(abs(op.montant_parsed), op.devise,
                                          op.date_parsed.strftime('%Y-%m-%d'))
                eur_estimates[idx] = eur_val  # None si conversion impossible

        # Phase 1b : Cross-currency (avec présélection EUR et score de proximité)
        for i, (idx1, op1) in enumerate(eligible):
            if idx1 in matched:
                continue
            cat1 = op1.categorie
            if cat1 == 'Virement':
                continue

            candidates = []  # (idx2, op2, result, proximity_score)

            for j in range(i + 1, len(eligible)):
                idx2, op2 = eligible[j]
                if idx2 in matched:
                    continue
                cat2 = op2.categorie
                if cat2 == 'Virement':
                    continue
                if cat1 in cross_only_cats or cat2 in cross_only_cats:
                    if cat1 != cat2:
                        continue
                if op1.compte == op2.compte:
                    continue
                if op1.devise == op2.devise:
                    continue
                if (op1.montant_parsed > 0) == (op2.montant_parsed > 0):
                    continue
                d1_eff = _extract_effective_date(op1)
                d2_eff = _extract_effective_date(op2)
                if abs((d1_eff - d2_eff).days) > max_jours_cross:
                    continue

                # Présélection par proximité EUR estimée
                eur1 = eur_estimates.get(idx1)
                eur2 = eur_estimates.get(idx2)
                if eur1 is not None and eur2 is not None and min(eur1, eur2) > 0.01:
                    ratio = max(eur1, eur2) / min(eur1, eur2)
                    if ratio > max_ratio_preselect:
                        continue

                # Relire equiv (peut avoir été enrichi entre-temps par d'autres phases)
                eq1 = parse_montant(self.excel.ws_operations.cell(op1.row, OpCol.EQUIV).value)
                eq2 = parse_montant(self.excel.ws_operations.cell(op2.row, OpCol.EQUIV).value)

                result = self._match_equiv(
                    op1, op1.montant_parsed, eq1, d1_eff,
                    op2, op2.montant_parsed, eq2, d2_eff)
                if result is None:
                    continue

                # Score de proximité : ratio EUR + pénalité par jour d'écart
                # Permet de désambiguïser des conversions similaires à des dates différentes
                date_diff = abs((d1_eff - d2_eff).days)
                if eur1 and eur2 and min(eur1, eur2) > 0.01:
                    score = max(eur1, eur2) / min(eur1, eur2) + date_diff * 0.1
                else:
                    score = 1.0 + date_diff * 0.1
                candidates.append((idx2, op2, result, score))

            if not candidates:
                continue

            # Trier par score (ratio le plus proche de 1.0 = meilleur)
            candidates.sort(key=lambda c: c[3])
            best = candidates[0]

            # Ambiguïté : si le 2e candidat a un score trop proche du meilleur → skip
            ambiguity_threshold = MESH_TRANSFERS.get('ambiguity_threshold', 0.05)
            if len(candidates) > 1:
                best_score, second_score = best[3], candidates[1][3]
                if best_score > 0 and (second_score - best_score) / best_score < ambiguity_threshold:
                    self.logger.verbose(
                        f"Ambiguïté mesh cross-ccy: {len(candidates)} candidats pour "
                        f"{op1.compte} {op1.montant_parsed:+.2f} {op1.devise}, "
                        f"scores {best_score:.3f} vs {second_score:.3f} — skip")
                    continue

            # Appairer avec le meilleur candidat
            idx2, op2, (eq1_final, eq2_final, equiv_updates), _ = best

            for upd_row, upd_val in equiv_updates:
                self.excel.write_equiv_to_excel(upd_row, upd_val)

            category = self._deduce_transfer_category(op1.devise, op2.devise)
            devise_credit = op2.devise if op2.montant_parsed > 0 else op1.devise
            pairing_ref = self.excel.get_next_pairing_ref(category, devise_credit)
            self.excel.write_ref_to_excel(op1.row, pairing_ref, category)
            self.excel.write_ref_to_excel(op2.row, pairing_ref, category)
            op1.ref = pairing_ref
            op2.ref = pairing_ref
            op1.categorie = category
            op2.categorie = category
            matched.add(idx1)
            matched.add(idx2)
            self.stats['paired'] += 1

            equiv_info = f" (equiv: {abs(eq1_final):.2f}€)" if eq1_final else ""
            self.logger.verbose(f"Appairage mesh cross-ccy: {pairing_ref}{equiv_info}")
            self.logger.verbose(f"  {op1.compte} {op1.montant_parsed:+.2f} {op1.devise} ↔ {op2.compte} {op2.montant_parsed:+.2f} {op2.devise}")

        phase_count = len(matched) // 2
        self.stats['phases']['mesh_transfers'] = phase_count
        if phase_count > 0:
            self.logger.verbose(f"Phase 4 (mesh_transfers): {phase_count} paire(s)")

        return [op for i, op in enumerate(operations) if i not in matched]

    # ====================================================================
    # Phase 5 : Appariement par libellé identique (titres)
    # ====================================================================

    def _match_same_label_pairs(self, operations):
        """Appaire les opérations avec même libellé, même montant absolu, signes opposés"""

        def normalize_label(label):
            return ' '.join(str(label).upper().split())

        categories_eligibles = ['Achat titres', 'Vente titres']

        negatifs = []
        positifs = []

        for i, op in enumerate(operations):
            cat = op.categorie
            ref = op.ref
            if cat not in categories_eligibles or ref != '-':
                continue

            montant = op.montant_parsed
            if montant is None or montant == 0:
                continue

            label_norm = normalize_label(op.label)

            if montant < 0:
                negatifs.append((i, op, abs(montant), label_norm))
            else:
                positifs.append((i, op, montant, label_norm))

        matched = set()

        for n_idx, n_op, n_montant, n_label in negatifs:
            if n_idx in matched:
                continue

            for p_idx, p_op, p_montant, p_label in positifs:
                if p_idx in matched:
                    continue

                if n_op.date_parsed != p_op.date_parsed:
                    continue
                if n_label != p_label:
                    continue

                is_change = n_op.categorie == 'Change'
                if not is_change and abs(n_montant - p_montant) > 0.01:
                    continue

                cat = p_op.categorie
                devise_credit = p_op.devise
                pairing_ref = self.excel.get_next_pairing_ref(cat, devise_credit)
                self.excel.write_ref_to_excel(n_op.row, pairing_ref)
                self.excel.write_ref_to_excel(p_op.row, pairing_ref)
                n_op.ref = pairing_ref
                p_op.ref = pairing_ref
                matched.add(n_idx)
                matched.add(p_idx)
                self.stats['paired'] += 1

                self.logger.verbose(f"Appairage {cat} (libellé): {pairing_ref}")
                self.logger.verbose(f"  {-n_montant:+.2f} ↔ {p_montant:+.2f} | {n_label[:30]}")
                break

        phase_count = len(matched) // 2
        self.stats['phases']['same_label'] = phase_count
        if phase_count > 0:
            self.logger.verbose(f"Phase 5 (same_label): {phase_count} paire(s)")

        return [op for i, op in enumerate(operations) if i not in matched]

    # ====================================================================
    # Orchestration
    # ====================================================================

    def run_pairing(self):
        """Exécute toutes les phases d'appariement"""
        if not self.excel.open_workbook():
            return False

        try:
            ops = self.excel.load_unpaired_operations()

            if not ops:
                self.logger.info("Aucune opération à apparier")
                self.excel.close_workbook(save=False)
                return True

            # Phase 1 : Opérations liées
            ops = self._match_linked_pairs(ops)
            # Phase 2 : Transfer pairs
            ops = self._match_transfer_pairs(ops)
            # Phase 3 : Internal transfers
            ops = self._match_internal_transfers(ops)
            # Phase 4 : Mesh transfers
            ops = self._match_mesh_transfers(ops)
            # Phase 5 : Same label pairs
            ops = self._match_same_label_pairs(ops)

            # Résumé
            self.stats['remaining'] = len(ops)

            if self.dry_run:
                self.excel.close_workbook(save=False)
            else:
                self.excel.close_workbook(save=True)

            return True

        except Exception as e:
            self.logger.error(f"Erreur lors de l'appariement: {e}")
            import traceback
            traceback.print_exc()
            self.excel.close_workbook(save=False)
            return False


# ============================================================================
# MAIN
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Appariement des opérations dans comptes.xlsm",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples:
  %(prog)s                    # Exécuter les appariements
  %(prog)s --pair             # Idem (explicite)
  %(prog)s --dry-run          # Simulation sans modification
  %(prog)s -v                 # Mode verbeux
        """)

    parser.add_argument('--pair',
                        action='store_true', default=True,
                        help='Exécuter les appariements (défaut)')
    parser.add_argument('--dry-run',
                        action='store_true',
                        help='Simulation sans modification')
    parser.add_argument('-v', '--verbose',
                        action='store_true',
                        help='Mode verbeux')

    args = parser.parse_args()

    timestamp = datetime.now().strftime('%H:%M:%S')
    mode_str = "[DRY-RUN] " if args.dry_run else ""
    print(f"{timestamp} Pair {mode_str}")

    pairer = ComptaPairer(
        verbose=args.verbose,
        dry_run=args.dry_run,
    )

    success = pairer.run_pairing()

    if success:
        total = pairer.stats['paired']
        remaining = pairer.stats.get('remaining', 0)
        dry = "[DRY-RUN] " if args.dry_run else ""
        print(f"\n✓ {dry}Appariement : {total} paire(s), {remaining} restante(s)")
        if args.verbose:
            for phase, count in pairer.stats['phases'].items():
                if count > 0:
                    print(f"  {phase}: {count}")
        # Recalcul + miroir C1 si lancé depuis la GUI
        if not args.dry_run:
            # Recalcul UNO + sauvegarde des cached (la GUI lit A1/L2 cached)
            from inc_uno import refresh_controles
            refresh_controles(COMPTES_FILE)
    else:
        print("\n❌ Erreur lors de l'appariement")
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
