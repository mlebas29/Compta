"""Lecture/écriture des fichiers config_*.json de Compta.

Module neutre (pas de dépendance tkinter, openpyxl, UNO) — extrait de cpt_gui.py
pour permettre l'usage depuis des environnements headless (LO Python 3.8 sans
tkinter, scripts CLI sans GUI).

Exposé :
  - config_category_mappings.json : read_mappings_json, write_mappings_json
  - config_accounts.json : read_accounts_json, write_accounts_json,
    accounts_to_site_map, site_map_to_accounts
  - config_cotations.json : read_cotations_json, write_cotations_json
"""

import json
from pathlib import Path


# ============================================================================
# LECTURE / ÉCRITURE CATEGORY_MAPPINGS.JSON
# ============================================================================

def read_mappings_json(path):
    """Lit config_category_mappings.json. Retourne {} si absent."""
    if not Path(path).exists():
        return {}
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def write_mappings_json(path, data):
    """Écrit config_category_mappings.json avec indentation lisible."""
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write('\n')


# ============================================================================
# LECTURE / ÉCRITURE CONFIG_ACCOUNTS.JSON
# ============================================================================

def read_accounts_json(path):
    """Lit config_accounts.json et retourne la structure complète."""
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def write_accounts_json(path, data):
    """Écrit config_accounts.json avec indentation lisible."""
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write('\n')


def accounts_to_site_map(accounts_data):
    """Dérive le dict plat {nom_compte: site} depuis config_accounts.json."""
    site_map = {}
    for site, site_data in accounts_data.items():
        for acct in site_data.get('accounts', []):
            site_map[acct['name']] = site
    return site_map


def site_map_to_accounts(site_map, existing_accounts=None):
    """Reconstruit config_accounts.json depuis un dict plat {nom: site}.

    Préserve les champs enrichis (numero, id_technique, etc.) de existing_accounts.
    """
    # Indexer les comptes existants par nom pour préserver les métadonnées
    existing_by_name = {}
    if existing_accounts:
        for site, site_data in existing_accounts.items():
            for acct in site_data.get('accounts', []):
                existing_by_name[acct['name']] = (site, acct)

    # Regrouper par site
    by_site = {}
    for name, site in site_map.items():
        if site not in by_site:
            by_site[site] = {'accounts': []}
        # Réutiliser l'objet enrichi existant ou créer un minimal
        if name in existing_by_name:
            _, acct = existing_by_name[name]
            by_site[site]['accounts'].append(acct)
        else:
            by_site[site]['accounts'].append({'name': name})

    # Préserver les champs non-accounts (ex: métadonnées site-specific futures)
    if existing_accounts:
        for site, site_data in existing_accounts.items():
            if site in by_site:
                for key, value in site_data.items():
                    if key != 'accounts':
                        by_site[site][key] = value

    return by_site


# ============================================================================
# LECTURE / ÉCRITURE CONFIG_COTATIONS.JSON
# ============================================================================

def read_cotations_json(path):
    """Lit config_cotations.json → dict {code: {source1, source2}} (route de fetch ; famille/décimales = classeur)."""
    if not Path(path).exists():
        return {}
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def write_cotations_json(path, data):
    """Écrit config_cotations.json avec indentation lisible."""
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write('\n')
