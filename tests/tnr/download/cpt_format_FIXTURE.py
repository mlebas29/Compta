#!/usr/bin/env python3
"""cpt_format_FIXTURE.py — format FICTIF pour le TNR hermétique (#146).

Parse le CSV servi par le serveur local en opérations minimales, pour que le
scénario `tnr_download.py` vérifie l'invariant « le fichier collecté se parse
sans exception → ≥ 1 opération » — miroir de l'assertion de `tnr_fetch` (#145)
sur les vrais sites. Contrat de retour aligné : `(ops, positions)`.

CSV attendu (en-tête + lignes) :
    date,label,amount
    2026-01-05,Test op,12.34
"""

import csv
from pathlib import Path


def format_site(site_dir, verbose=False, logger=None):
    """Retourne (liste d'ops, liste de positions). Positions vide (le fixture
    ne porte pas de titres/cotations)."""
    ops = []
    for csv_file in sorted(Path(site_dir).glob('*.csv')):
        with open(csv_file, newline='', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                date = (row.get('date') or '').strip()
                label = (row.get('label') or '').strip()
                amount = (row.get('amount') or '').strip()
                if not date:
                    continue
                ops.append({'date': date, 'label': label, 'amount': amount})
    return ops, []
