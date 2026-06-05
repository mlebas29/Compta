# Compta_site.md — Ajouter un site

Ce document décrit l'ajout d'une nouvelle source de données (banque, courtier, exchange…) à Compta. Audience : contributeur qui veut intégrer un site bancaire/financier supplémentaire.

Un site dans Compta = la combinaison de **deux scripts Python** :

- `cpt_fetch_<NAME>.py` — collecte automatique depuis le site (Playwright/Chrome ou stub manuel)
- `cpt_format_<NAME>.py` — parsing des fichiers collectés vers le format standard interne

Le code est découvert dynamiquement au démarrage (scan glob), sans aucune modification du code central.

## Site public vs site privé

| Cas | Où placer les 2 scripts | Pour qui |
|---|---|---|
| **Site public** | À la racine du projet (`cpt_fetch_FOO.py` + `cpt_format_FOO.py`) | Site générique utile à plusieurs cloneurs — peut être proposé en PR |
| **Site privé** | Dans `custom/` (`custom/cpt_fetch_FOO.py` + `custom/cpt_format_FOO.py`) | Site spécifique à l'utilisateur — données nominatives, dossier unique, etc. |

Les deux cas suivent **les mêmes squelettes Python**. La différence est purement organisationnelle : où vivent les fichiers, et comment ils sont versionnés (PUB pour la racine, PRV pour `custom/`). Pour les détails du mécanisme d'extensions `custom/` (bootstrap, options A/B, monkeypatches), voir [`Compta_custom.md`](Compta_custom.md).

Le reste de ce document utilise `FOO` comme nom de site générique et place les fichiers à la racine (site public). Pour un site privé, remplacer `FOO` par le nom du site et ajouter le préfixe `custom/` aux chemins.

## Étapes — vue d'ensemble

1. Choisir le nom (majuscules, sans espaces : `FOO`, `MYBROKER`, `EUROPEX`)
2. Créer le squelette `cpt_fetch_FOO.py`
3. Créer le squelette `cpt_format_FOO.py`
4. Configurer le site (config.ini, config_accounts.json) — via GUI ou manuellement
5. Tester la collecte et l'import

## 1. Squelette `cpt_fetch_FOO.py` (Tier 1)

Le fetcher télécharge les fichiers bruts depuis le site et les dépose dans `dropbox/FOO/`.

```python
#!/usr/bin/env python3
"""cpt_fetch_FOO.py — collecte FOO."""

from inc_fetch import BaseFetcher, fetch_main, config

# DESCRIPTION (consommée par la GUI onglet Sites)
DESCRIPTION = """FOO — courtier en ligne.

══════ Configuration ══════
1 portefeuille + N comptes (1 par devise).

══════ 2FA ══════
SMS à la connexion.
"""


class FooFetcher(BaseFetcher):
    def __init__(self, verbose=False):
        super().__init__(caller_file=__file__, verbose=verbose)

    def run(self):
        # 1. Authentification (Playwright headed/headless selon site)
        # 2. Navigation vers l'export
        # 3. Téléchargement des fichiers
        # 4. Dépôt dans self.dropbox_dir (== dropbox/FOO/)
        ...


if __name__ == '__main__':
    fetch_main(FooFetcher, description='Fetch FOO')
```

**Points clés** :

- Hérite de `BaseFetcher` (gère credentials, navigateur, dropbox).
- Aucune transformation : les fichiers sont déposés **bruts** dans `dropbox/FOO/`, exactement tels que la banque les envoie. Le formatting est la responsabilité du Tier 2.
- `DESCRIPTION` est lue par la GUI onglet Sites pour afficher l'aide à l'utilisateur.
- Pour un site sans automatisation possible (fichiers déposés manuellement par l'utilisateur), le fetcher peut être un stub qui ne fait rien ou affiche un message d'aide.

## 2. Squelette `cpt_format_FOO.py` (Tier 2)

Le formatter parse les fichiers bruts de `dropbox/FOO/` et produit **le format standard interne consommé par `cpt_update.py` (Tier 3)**. C'est le contrat de pipe central : tout ce qui sort d'un formateur doit respecter l'une des deux signatures ci-dessous, sinon l'import casse.

```python
#!/usr/bin/env python3
"""cpt_format_FOO.py — formateur FOO."""

from inc_format import site_name_from_file
from inc_categorize import categorize_operation, get_max_days_back_from_config

SITE = site_name_from_file(__file__)  # → 'FOO'

# Fichiers attendus dans dropbox/FOO/
EXPECTED_FILES = [
    ('foo_operations.csv', 'exact', '1'),       # 1 fichier obligatoire
    ('foo_supports_*.xlsx', 'glob', '0+'),      # 0 ou + fichiers positions
]

# Optionnel : limite stricte du nombre de comptes
MAX_ACCOUNTS = 4


def process_operations(file_path):
    """Parse foo_operations.csv → liste de tuples 9 champs (Opérations)."""
    ...


def process_positions(file_path):
    """Parse foo_supports_*.xlsx → liste de tuples 4 champs (Positions)."""
    ...
```

### Variables de module — résumé

| Variable | Rôle | Obligatoire | Fichier |
|---|---|---|---|
| `SITE` | Nom du site dérivé du nom de fichier | Oui (auto via `site_name_from_file`) | format |
| `EXPECTED_FILES` | Patterns des fichiers attendus dans `dropbox/SITE/` | Oui | format |
| `MAX_ACCOUNTS` | Limite stricte du nombre de comptes attachés | Non | format |
| `DESCRIPTION` | Texte d'aide affiché en GUI onglet Sites | Oui | **fetch** |

### `EXPECTED_FILES` — détail

Liste de tuples `(pattern, matching, cardinalité)` :

| Champ | Valeurs | Description |
|---|---|---|
| `pattern` | chaîne | nom de fichier (exact) ou glob (`*`, `?`) |
| `matching` | `'exact'` ou `'glob'` | Mode de comparaison |
| `cardinalité` | `'1'`, `'1+'`, `'0-1'`, `'0+'` | Nombre attendu (cf. tableau ci-dessous) |

| Cardinalité | Signification | Si surnuméraires |
|---|---|---|
| `1` | Exactement 1 attendu | Warning + sélection auto |
| `1+` | Au moins 1, tout prendre | OK |
| `0-1` | Optionnel, max 1 | Warning + sélection si > 1 |
| `0+` | Optionnel, tout prendre | OK |

## 3. Interface pipe avec l'import (Tier 3)

Les deux fonctions `process_operations` et `process_positions` sont les **seuls points de contact** entre ton site et l'import dans le classeur. Toute la chaîne aval (`cpt_update.py`, déduplication, appariement, écriture Excel) consomme ces deux formats. Si tu respectes la signature, ton site fonctionne ; sinon l'import casse, parfois en silence.

### Format 9 champs — Opérations

```
Date;Libellé;Montant;Devise;Equiv;Réf;Catégorie;Compte;Commentaire
```

Une ligne par mouvement (débit/crédit), plus une ligne `#Solde` en fin (catégorie spéciale = solde relevé à la date courante).

| Champ | Format | Source typique |
|---|---|---|
| Date | `DD/MM/YYYY` | brut |
| Libellé | texte brut tel que reçu de la banque | brut |
| Montant | nombre signé (positif = crédit, négatif = débit) | brut |
| Devise | code 3 lettres (EUR, USD, BTC, XAU…) | brut |
| Equiv | montant en EUR équivalent (cf. ci-dessous) | calculé ou vide |
| Réf | `-` ou identifiant d'appariement | conventionnel (cf. ci-dessous) |
| Catégorie | catégorie issue de `categorize_operation` | catégorisation |
| Compte | nom exact du compte tel que listé dans `config_accounts.json` | mapping site |
| Commentaire | libre | brut ou vide |

### Format 4 champs — Positions

```
Date;Ligne;Montant;Compte
```

Pour les portefeuilles titres (assurance vie, fonds, actions). Une ligne par holding. Inclut éventuellement une ligne `#Solde Réserve` pour le cash du portefeuille.

### Catégorisation et appariement

```python
cat, opts = categorize_operation(libelle, SITE)
ref = opts.get('ref', '')         # '-' déclenche l'appariement par cpt_update
equiv = opts.get('equiv', '')     # 'amount' = copier le montant dans Equiv
```

Les patterns regex sont déclarés dans `config_category_mappings.json` (section `SITE_PATTERNS[FOO]` ou `GENERIC_PATTERNS`). L'utilisateur les édite via la GUI onglet Catégories.

### Colonne Equiv (équivalent EUR)

| Cas | Valeur Equiv |
|---|---|
| Opération en EUR | vide (Equiv = Montant trivialement) |
| Opération non-EUR sans contrepartie | vide — `cpt_update` enrichit via taux ECB |
| Échange cross-currency avec montant EUR connu | renseigner explicitement, même valeur EUR des deux côtés |

### Colonne Réf et autres champs « ignorés »

Plusieurs champs ne sont pas comparés à l'import :

- **Réf** : numérotation interne, attribuée à l'écriture dans la feuille. Le formatter pose `-` pour signaler une opération à apparier (virement, change, achat de titre) ; toute autre valeur est ignorée.
- **Catégorie** : remplie manuellement par l'utilisateur après import si le pattern regex n'a pas matché.
- **Commentaire** : libre, jamais comparé.

La déduplication compare uniquement `Date + Compte + Montant + Libellé` — peu importe ce que tu mets dans Réf/Commentaire.

### Filtrage temporel

Pour ne pas réimporter d'anciennes opérations à chaque collecte :

```python
max_days = get_max_days_back_from_config(SITE)  # défaut 90 jours
# Filtrer les opérations dont la date est > today - max_days
```

Configurable dans `config.ini` section `[general] max_days_back` (global) ou `[FOO] max_days_back` (override site).

## 4. Configuration utilisateur

### 4.1 Création initiale de la section `[FOO]` (manuelle)

La GUI ne sait éditer que des sections existantes. Pour un site neuf, créer d'abord la section dans `config.ini` en copiant une section voisine et en adaptant les valeurs :

```ini
[FOO]
credential_id = foo                  # clé dans config_credentials.md
url           = https://www.foo.com/login
max_days_back = 90                   # optionnel — override du global
# autres clés selon le fetcher (timeout, headed, etc.)
```

Une fois la section présente, relancer `cpt_gui.py` : FOO apparaît dans l'onglet Sites et tout le reste se fait via la GUI.

### 4.2 Suite via la **GUI Configuration** de `cpt_gui.py`

Trois onglets, trois fichiers :

- **onglet Sites** → `config.ini` : coche `[sites] enabled = …, FOO` et édite les champs de la section `[FOO]`.
- **onglet Comptes** → `config_accounts.json` : liste des comptes attachés à FOO.
- **onglet Catégories** → `config_category_mappings.json` : patterns regex de catégorisation.

### 4.3 Credentials

Déposer les identifiants chiffrés dans le fichier configuré par `config.ini` section `[paths]` clé `credentials_file` (cf. `config_credentials.md.default` pour le modèle).

## 5. Test

```bash
# Vérifier que le site est bien détecté
./cpt_gui.py            # onglet Sites → FOO doit apparaître

# Collecte standalone
./cpt_fetch.py --sites FOO
ls dropbox/FOO/                # → les fichiers téléchargés

# Pipeline complet
./cpt.py --sites FOO     # fetch + import
```

Le formatter parse les fichiers de `dropbox/FOO/`, `cpt_update.py` importe les opérations dans le classeur, archive les fichiers bruts dans `archives/FOO/`.

## Cas avancés

### Échanges cross-currency (Change, Achat métaux/crypto)

Si FOO propose des conversions cross-devise (EUR ↔ USD, EUR ↔ BTC…), ajouter le ou les comptes concernés à la liste `MESH_TRANSFERS` de `cpt_update.py`. C'est ce mécanisme qui apparie automatiquement le débit EUR avec le crédit USD/BTC en chaînant par la colonne Equiv.

### Comptes multiples (portefeuille titres)

Pour un compte-titre (Réserve cash + Titres securities), créer **deux comptes distincts** : `Portefeuille FOO Titres` et `Portefeuille FOO Réserve`. Les achats/ventes génèrent des entrées symétriques (Réserve débit ↔ Titres crédit). `MAX_ACCOUNTS` peut alors être 2 (par exemple).

### Site privé dans `custom/`

Tout ce qui précède s'applique tel quel, en plaçant les scripts dans `custom/` au lieu de la racine. Pour démarrer, copier un fetcher/format existant comme gabarit (le code en place est le meilleur modèle, à jour) :

```bash
cp cpt_fetch_BTC.py custom/cpt_fetch_FOO.py      # gabarit API ; Playwright → cpt_fetch_KRAKEN.py
cp cpt_format_BTC.py custom/cpt_format_FOO.py
```

puis renommer/adapter (cf. étapes ci-dessus). Voir [`Compta_custom.md`](Compta_custom.md) pour le mécanisme d'extensions `custom/` (bootstrap, options A/B, monkeypatches).

### Monkeypatch d'un site existant

Si tu veux **modifier** le comportement d'un site public sans changer son code (par exemple regrouper certaines lignes d'un parsing existant), c'est un patch dans `custom/patch_*.py` — voir [`Compta_custom.md`](Compta_custom.md) §Cas B.
