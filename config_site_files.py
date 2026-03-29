#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
config_site_files.py - Définition des fichiers attendus par site dans dropbox/

Source de vérité pour :
- La vérification des fichiers dropbox (fichiers intrus, surnuméraires, manquants)
- La documentation (Compta_dev.md)

Structure: SITE_FILES[site] = liste de tuples (pattern, matching, cardinalité)

Matching:
- 'exact' : nom de fichier exact (case-sensitive)
- 'glob'  : pattern glob (*, ?)

Cardinalité:
- '1'   : exactement 1 fichier attendu (surnuméraires → warning + sélection)
- '1+'  : au moins 1, tout prendre
- '0-1' : optionnel, max 1 (surnuméraires → warning + sélection)
- '0+'  : optionnel, tout prendre

Note: MANUEL est exclu des vérifications (pas de vérification (fichiers libres))
"""

SITE_FILES = {
    'DEGIRO': [
        ('Account.csv', 'exact', '1'),
        ('Portfolio.csv', 'exact', '1'),
    ],

    'BOURSOBANK': [
        ('export_compte_principal.csv', 'exact', '1'),
        ('export_livret_bourso.csv', 'exact', '1'),
        ('export-operations-*.csv', 'glob', '0+'),
        ('positions.csv', 'exact', '0-1'),  # collecte manuelle
        ('export-positions-instantanees-*.csv', 'glob', '0-1'),  # fetch automatique
        ('Mes Comptes - BoursoBank.pdf', 'exact', '1'),
        ('Portefeuille - BoursoBank.pdf', 'exact', '0-1'),
    ],

    'SOCGEN': [
        ('Mes comptes en ligne _ SG.pdf', 'exact', '1'),
        ('00050659433.csv', 'exact', '1'),
        ('Export_00030472944_*.csv', 'glob', '1'),
        ('Export_00030472951_*.csv', 'glob', '1'),
        ('Export_00034192035_*.csv', 'glob', '1'),
        ('Export_00034192043_*.csv', 'glob', '1'),
        ('Export_00036889059_*.csv', 'glob', '1'),
        ('SG_Ebene_operations.pdf', 'exact', '0-1'),
        ('SG_Ebene_operations#*.pdf', 'glob', '0+'),
        ('SG_Ebene2_operations.pdf', 'exact', '0-1'),
        ('SG_Ebene2_operations#*.pdf', 'glob', '0+'),
        ('SG_Ebene_supports.xlsx', 'exact', '1'),
        ('SG_Ebene2_supports.xlsx', 'exact', '1'),
    ],
    'NATIXIS': [
        ('Historique et suivi de mes opérations - Natixis Interépargne.pdf', 'exact', '1'),
        ('Mon épargne en détail - Natixis Interépargne.pdf', 'exact', '1'),
    ],

    'BTC': [
        ('btc_balances.csv', 'exact', '1'),
        ('btc_*_operations.csv', 'glob', '0+'),
    ],

    'XMR': [
        ('xmr_balances.csv', 'exact', '1'),
        ('xmr_*_operations.csv', 'glob', '0+'),
    ],
    'KRAKEN': [
        ('kraken-spot-balances-*.zip', 'glob', '1'),
        ('kraken-spot-ledgers-*.zip', 'glob', '1'),
    ],

    'WISE': [
        ('statement_*.zip', 'glob', '1'),
    ],

    'ETORO': [
        ('eToroTransactions_*.tsv', 'glob', '1'),
        ('etoro-account-statement*.xlsx', 'glob', '1'),
        ('eToro_accueil.pdf', 'exact', '1'),
        ('eToro_portfolio.pdf', 'exact', '1'),
    ],
    'AMAZON': [
        ('amazon_operations.csv', 'exact', '1'),
    ],

    'PAYPAL': [
        ('*.CSV', 'glob', '1'),
    ],

    'MANUEL': [
        ('*.xlsx', 'glob', '0-1'),
    ],
}


def get_site_patterns(site):
    """Retourne les patterns pour un site donné."""
    return SITE_FILES.get(site, [])
