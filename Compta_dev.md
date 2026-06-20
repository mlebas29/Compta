# Compta_dev.md — Point d'entrée développeur

Documentation technique pour le contributeur ou le mainteneur. Décrit l'architecture générale du projet et distribue vers les docs spécialisées selon le sujet.

> Audience : développeur qui modifie le code, ajoute un site, debug un comportement. Pour l'usage de l'application, voir [`Compta.md`](Compta.md).

## Index thématique

| Sujet | Doc |
|---|---|
| Ajouter un site (fetch + format) | [`Compta_site.md`](Compta_site.md) |
| Internals par connecteur (auth, parsing, gotchas) | [`docs/`](docs/README.md) |
| Étendre Compta (dual, custom/, monkeypatches) | [`Compta_extension.md`](Compta_extension.md) |
| Tests de non-régression (TNR) | [`Compta_tests.md`](Compta_tests.md) |
| Cohérence install / upgrade / démarrage (marqueurs par composant) | [`Compta_coherence.md`](Compta_coherence.md) |
| Outils maintenance, git (git nu, `tool_audit_git` status/align) | [`Compta_tools.md`](Compta_tools.md) |
| Guide utilisateur (concepts, PVL, portage, charte, mise à niveau) | [`Compta.md`](Compta.md) |

## Architecture en 3 tiers

```
Tier 1 (fetch)  → Playwright/Chrome — télécharger les documents depuis les sites
Tier 2 (format) → Convertir documents bruts → formats internes (monoscript par site)
Tier 3 (update) → Importer dans Excel — déduplication + archivage + appariement
```

**Scripts principaux** : `cpt.py` → `cpt_fetch.py` → `cpt_update.py`. Plus `cpt_gui.py` qui sert de front-end Tk pour les 3 tiers (les boutons GUI lancent en subprocess les commandes CLI équivalentes).

### Séparation des responsabilités

| Couche | Responsabilité |
|---|---|
| **Tier 1 (fetch)** | Authentification, navigation, téléchargement. Aucune transformation. Dépose les fichiers bruts dans `dropbox/SITE/`. |
| **Tier 2 (format)** | Parsing des fichiers bruts. Produit le format standard 9 champs (opérations) et/ou 4 champs (positions). Stateless, testable. |
| **Tier 3 (update)** | Lit les sorties du Tier 2, déduplique, filtre temporellement, enrichit (Equiv ECB), apparie, écrit dans le classeur, archive. |

Cette séparation permet de changer une source de données (Tier 1 réécrit) sans toucher à la logique d'import (Tier 3) — ou inversement.

### Interface Tier 2 ↔ Tier 3 — contrat de pipe

Les formats produits par les `cpt_format_SITE.py` sont **le seul point de contact** avec l'import. Toute évolution du format casse la chaîne aval.

**Format opérations — 9 champs** :

```
Date;Libellé;Montant;Devise;Equiv;Réf;Catégorie;Compte;Commentaire
```

**Format positions — 4 champs** :

```
Date;Ligne;Montant;Compte
```

Détail des conventions (Equiv, Réf, filtrage temporel, catégorisation) dans [`Compta_site.md`](Compta_site.md) §3.

### Pourquoi 3 tiers (pas 2, pas 4)

- Tier 1 isolé = changer de banque / d'API sans toucher le parsing.
- Tier 3 isolé = la logique Excel (named ranges, formules, archivage) ne bouge plus quand on ajoute un site.
- Tier 2 monoscript par site (vs un parsing centralisé) = la connaissance de chaque banque reste localisée, pas de switch géant.

## Data flow

```
SITE → dropbox/SITE/   (Tier 1)
                      ↓
        cpt_format_SITE.py (Tier 2)
                      ↓
        cpt_update.py (Tier 3)
                      ↓
        comptes.xlsm
                      +
        archives/SITE/*_HDS_*.csv  (originaux conservés)
```

### Naming dropbox

Les fichiers gardent leur **nom original** tel que reçu de la banque. Le site est identifié par le **sous-répertoire** (`dropbox/SOCGEN/`, `dropbox/DEGIRO/`…), pas par le nom de fichier. En cas de collision de nom, suffixes `#2`, `#3`.

### Fichiers attendus par site

Chaque module `cpt_format_SITE.py` déclare sa propre `EXPECTED_FILES = [...]` avec patterns + cardinalités (`1`, `1+`, `0-1`, `0+`). `inc_format.get_expected_files(site)` les agrège. Voir [`Compta_site.md`](Compta_site.md) §2 pour la spécification.

### Archivage HDS

Chaque session reçoit un timestamp unique `HDS_YYYYMMDD_HHMMSS` qui tague tous les fichiers archivés. Permet le `--fallback` (restauration du dernier import) en réinjectant les fichiers archivés dans `dropbox/`.

- Tous les fichiers de `dropbox/` sont archivés (même en erreur).
- ZIP WISE : seul le ZIP est archivé (XLSX extraits en temp puis supprimés).
- Journal centralisé `logs/journal.log` trace toutes les sessions.
- Purge synchronisée : N dernières sessions (défaut 10), archives + journal + debug.

**Règle stricte** : `dropbox/` est en lecture seule pour le code (sauf `--fallback` qui restaure). Les fichiers temporaires vont dans `logs/debug/SITE/`.

## Logique cœur Tier 3

### Déduplication

Comparaison **CSV vs Excel** (jamais CSV vs CSV) :

- Champs comparés : `Date + Compte + Montant + Libellé`
- Champs exclus : Réf, Catégorie, Commentaire, méta-opérations `#Solde` / `#Balance` / `#Info`
- Le set `existing_ops` (opérations Excel) est **immutable** pendant la boucle CSV — sinon on éliminerait les doublons légitimes intra-CSV (3 arbitrages le même jour au même montant, par exemple).

### Appariement (linked operations)

Auto-apparie les opérations marquées `ref = '-'` via 4 stratégies dans `cpt_pair.py` :

| Stratégie | Cas |
|---|---|
| `LINKED_OPERATIONS` | Patterns d'auto-génération (retrait DAB → Espèces, remboursement prêt → Créance) |
| `TRANSFER_PAIRS` | Paires de comptes spécifiques (montants identiques) |
| `INTERNAL_TRANSFERS` | Hub ↔ spokes (montants identiques) |
| `MESH_TRANSFERS` | Réseau maillé unifié — virements same-currency + changes cross-currency via Equiv EUR |

Pour les cross-currency, l'appariement se fait par valeur Equiv EUR commune (cf. §Conventions Equiv dans [`Compta_site.md`](Compta_site.md)).

### Mise à jour Plus_value

La feuille `Plus_value` est mise à jour à chaque import à partir des fichiers `positions/*` (4 champs). Une ligne par holding, avec date de valorisation + montant. Distinct des opérations : Plus_value reflète la valeur marché, pas les mouvements.

Doctrine complète : [`Compta_pvl.md`](Compta_pvl.md).

### Feuille Contrôles

Validation post-import. Cellule `Contrôles!A1` = statut global agrégé (sémantique des positions : [`Compta.md`](Compta.md) Annexe A). Miroir `C1` recopié au save pour lecture instantanée par openpyxl sans relancer UNO.

Les contrôles agrégateurs s'appuient sur le bloc `CTRL2` (named ranges, sous-lignes indentées) et sur des cellules d'alarme locales :

- `Plus_value!B3` — surveille la synthèse GRAND TOTAL (E + K) ; `✗` si `#N/A`/`#REF!` propagé en amont.
- `Avoirs!L1` — surveille la synthèse Total Avoirs (`L{Total}`) ; idem.
- `Cotations!B20` — alarme métier au pied de la table Cotations : devise utilisée mais absente de `COTcode`, ou code listé sans cours associé.

Détail des contrôles et signification des codes d'erreur : [`Compta.md`](Compta.md) Annexe A.

## Interactions avec le classeur

Une part importante du code manipule `comptes.xlsm`. Deux bibliothèques cohabitent, chacune adaptée à un usage différent.

### `openpyxl` vs UNO

| | `openpyxl` | UNO (LibreOffice API) |
|---|---|---|
| Nature | pur Python | pilote `soffice --headless` |
| Recalcul des formules | **non** | oui |
| Lecture statique (data, formules) | rapide | lent (cold start ~5–6 s) |
| Écriture / save `.xlsm` | **interdit** (corrompt le fichier) | obligatoire pour les saves |
| Usage typique | scan de cellules, lecture statut, parsing, comparaison TNR | CRUD, calcul, sauvegarde |

> **Règle absolue** : ne jamais sauvegarder un `.xlsm` avec openpyxl — la macro VBA et certains formats sont perdus silencieusement. Toujours passer par UNO via `UnoDocument` pour les saves.

### Modules

| Module | Rôle |
|---|---|
| `inc_uno.py` | Context manager `UnoDocument`, gestion du soffice subprocess, retry, dispatch wrapper `python3-uno` |
| `inc_excel_schema.py` | `ColResolver` (cr), helpers named ranges, sentinels ⚓ |
| `inc_excel_compta.py` | Opérations métier sur le classeur (ajouter compte/devise/titre, purger, etc.) |
| `inc_excel_import.py` | Import des opérations dans la feuille Opérations + mise à jour Plus_value |
| `inc_compare_xlsx.py` | Comparaison `.xlsm` pour les TNR |
| `inc_formats.py` | Application de la charte v3.6 (couleurs, bordures, polices) |
| `inc_check_integrity.py` | Vérification post-import |

### Named ranges — système de référence central

Le classeur est entièrement structuré par des **named ranges** : `OPdate`, `OPmontant`, `AVRintitulé`, `CTRL1controle`, etc. Ils définissent les bornes des tableaux et permettent au code de se référer aux cellules sans coordonnées en dur — toute insertion/suppression UNO ajuste automatiquement les bornes.

- **Conventions ⚓ ancres + sentinels** : voir [`Compta_charte.md`](Compta_charte.md).
- **`ColResolver`** (`cr` dans le code) : résout les colonnes via named ranges. Itération bornée : `for row in cr.rows('OPdate'): ...`.
- **2 model rows minimum** par tableau — si la suppression UNO retire toutes les lignes, le range devient `#REF!`. Garder une row factice protège l'intégrité.
- **Insertion devant un `=SUM(range)`** n'étend pas automatiquement le range → extension manuelle ou utiliser des plages absolues.

### Pièges UNO à connaître

- **`setFormula()`** : point-virgule (`;`) comme séparateur, **jamais** virgule, sinon Err 509.
- **Références inter-feuilles** : point (`.`), pas `!`. Ex : `=$Cotations.$B$3` (et non `=Cotations!$B$3`).
- **`getFormula()`** retourne la valeur brute si pas de formule (ex : `"44927"` pour une date) — tester `startswith('=')` pour distinguer.
- **`setString('')`** n'efface pas la « used range » — `Rows.removeByIndex` pour vraie compaction. Conséquence : les boucles `while not cell.getString()` depuis EndRow peuvent boucler longtemps si la used range a été artificiellement étendue.
- **`addNewByName`** refuse les noms qui évoquent une référence cellule (`PAT1`, `XAU2`…) — colonnes valides en Excel. Suffixer en non-référence (`PAT_1`, `PATa`…).
- **`getString()` inclut les suffixes décoratifs du format** : sur une cellule TEXT formatée `@" ▼"` contenant `'EUR'`, retourne `'EUR ▼'`. Utiliser `getFormula()` pour le brut ou `val.split()[0]` selon le cas.
- **Reset vue avant save** : `controller.setActiveSheet(sheet)` + `controller.select(A1)` sur chaque feuille pour éviter de saver un état d'affichage incohérent.

### Cellules miroirs — lecture statut sans UNO

Le statut global `Contrôles!A1` est miroité dans `Contrôles!C1`, `Opérations!L1` et `Plus_value!L1` à chaque save (via `UnoDocument.save()` et la macro VBA `OnSave` du classeur). Permet à openpyxl de lire le statut **instantanément** sans relancer un cycle UNO complet.

### Sur Mac : bridge socket

Le transport UNO côté Mac passe par un socket TCP localhost (port 2002) — chaque appel atomique = 1 round-trip. Conséquence : le code « bavard » (boucle cellule par cellule) explose en coût (×10–11 sur certains scans). Atténuation par batch UNO et préférence pour les API range.

## GUI Tkinter

`cpt_gui.py` est un front-end Tk qui orchestre les scripts CLI via subprocess. Pas de logique métier dedans — uniquement de l'UI et du dispatch.

| Onglet | Rôle |
|---|---|
| Exécution | Sélection sites, lancement collecte/import/cotations |
| Sites | Description par site (lue depuis `cpt_fetch_SITE.DESCRIPTION`) |
| Comptes | CRUD comptes Excel (Avoirs) |
| Catégories | Édition `config_category_mappings.json` |
| Paramètres | Réglages `config.ini` |

### Sur Mac : daemon JSON RPC

Sur Linux, les onglets CRUD font `with UnoDocument(...) as doc:` en in-process. Sur Mac, Tk et `uno` sont mutuellement exclusifs dans un même Python — les CRUD passent obligatoirement par un daemon `tool_gui_cli.py` lancé en subprocess sous `python3-uno`.

## Configuration

| Fichier | Rôle | Versionné |
|---|---|---|
| `config.ini` | Paramètres généraux + sections par site | Non (`.default` versionné) |
| `config_accounts.json` | Comptes attachés à chaque site | Non (généré par `inc_config_init.py`) |
| `config_category_mappings.json` | Patterns regex catégorisation | Non (généré par `inc_config_init.py`) |
| `config_cotations.json` | Devises et cotations configurées | Non (généré par `inc_config_init.py`) |
| `config_pipeline.json` | Paramètres collecte avancés | Non (généré par `inc_config_init.py`) |

`config.ini` est copié depuis `config.ini.default` par `install.sh` à la première installation. Les JSON n'ont pas de `.default` : ils sont générés vides à la volée par `inc_config_init.py` (`ensure_user_configs()`). Détail dans [`Compta_plus.md`](Compta_plus.md).

### Schéma `config_accounts.json`

Top-level : code **site** canonique (`SOCGEN`, `BOURSOBANK`, `NATIXIS`, `BTC`, …) → ses comptes et options. La GUI gère le couple **compte → site** (`name`) ; les **champs techniques** et les **mappings** sont saisis à la main (lus par les `cpt_format_*` / `cpt_pair`, fallback vide → clé absente = inactive).

```jsonc
{
  "SOCGEN": {
    "accounts": [
      { "name": "Compte chèque commun",  "numero": "12345678", "type_sg": "principal" },
      { "name": "Livret A Barnabé",      "numero": "23456789", "type_sg": "epargne" },
      { "name": "Assurance vie Barnabé", "numero": "34567890", "type_sg": "assurance_vie" }
    ],
    "support_renames": { "<nom support relevé SG>": "<nom Plus_value>" }
  },
  "BOURSOBANK": {
    "accounts": [ { "name": "Portefeuille BB Titres", "numero": "..." } ],
    "titre_renames": { "<label titre banque>": "<nom canonique>" }
  },
  "BTC": {
    "accounts": [ { "name": "BlueWallet BTC", "wallet_key": "bluewallet", "addresses": ["bc1q..."] } ]
  },
  "transfer_pairs": [
    { "name": "...", "max_jours_ecart": 7,
      "source": { "compte": "...", "pattern": "...", "signe": "negatif" },
      "dest":   { "compte": "...", "pattern": "...", "signe": "positif" } }
  ]
}
```

| Clé | Lu par | Rôle |
|---|---|---|
| `accounts[].name` | tous + GUI | nom du compte dans le classeur |
| `accounts[].numero` | SOCGEN, BOURSOBANK | numéro (mapping synthèse / 4 derniers chiffres) |
| `accounts[].type_sg` | SOCGEN | `principal` / `epargne` / `assurance_vie` |
| `accounts[].wallet_key` (+ `addresses`) | BTC, XMR | préfixe fichier + adresses publiques |
| `support_renames` (par site) | `cpt_format_SOCGEN` | renomme un support relevé → nom Plus_value |
| `titre_renames` (par site) | `cpt_format_BOURSOBANK` | normalise un label de titre |
| `transfer_pairs` (top-level) | `cpt_pair` | paires de virements à apparier explicitement |

### Credentials

Stockés chiffrés GPG dans le fichier pointé par `config.ini` `[paths] credentials_file`. Format Markdown — voir `config_credentials.md.default` pour le modèle et `inc_gpg_credentials.py` pour l'implémentation.

## Organisation du dépôt

```
~/Compta/                         # PROD — dossier d'usage
├── .git/                         # clone PUB (github.com:mlebas29/Compta)
├── cpt_*.py                      # pipeline (fetch/update/pair/gui)
├── cpt_fetch_<SITE>.py           # 1 par site public
├── cpt_format_<SITE>.py          # 1 par site public
├── gui_*.py                      # modules GUI Tk
├── inc_*.py                      # librairies partagées
├── tool_*.py                     # outils de maintenance
├── tests/                        # TNR + jeux de données expected
├── docs/                         # doc dev spécialisée
├── images/                       # captures GUI, icônes
├── Compta_*.md                   # documentation
├── README.md, LICENSE, CHANGELOG
│
├── custom/                       # extensions privées (optionnel)
│   ├── .git/                     # dépôt PRV (option A)
│   ├── cpt_fetch_<SITE>.py       # sites privés
│   ├── cpt_format_<SITE>.py
│   ├── patch_*.py                # monkeypatches
│   └── tests/                    # TNR privés
│
├── comptes.xlsm                  # classeur (non versionné)
├── config*.{ini,json}            # config locale (non versionnée)
└── dropbox/, archives/, logs/    # données opérationnelles
```

Le dossier DEV est **indépendant** (`~/Compta-dev/`, même structure, mode `DEV` ; depuis #87 il n'est plus nesté sous PROD). Détail de l'archi PUB/PRV + dual : [`Compta_extension.md`](Compta_extension.md).

## Dépendances techniques

**Python** : playwright, openpyxl, pdfplumber, pytesseract, pillow, configparser, requests.

**Externes** : tesseract-ocr (OCR 2FA), gpg (credentials), libreoffice (UNO API pour calcul de formules — openpyxl ne recalcule pas).

**Browser** : Chrome via Playwright (persistent context dans `.chrome_profile_*/` — supprimer ces dossiers déclenche les 2FA).

Liste complète : `requirements.txt` (Python) + `install.sh` (système).

## Notes diverses

1. **Accès concurrent Excel** — plusieurs process LibreOffice/UNO simultanés causent des locks. Si import échoue avec « Fichier verrouillé » ou « Contrôles!A1 non lisible » : `killall -9 soffice.bin; rm -f ~/Compta/.~lock.*`.
2. **Chrome profiles critiques** — supprimer `.chrome_profile_*/` déclenche le 2FA pour ce site.
3. **Dates** : `DD/MM/YYYY` dans les CSV intermédiaires, format natif dans Excel.
4. **NATIXIS arbitrages** — montant intégré dans le libellé (ex : « Modification répartition (1250,00€) »), pas dans la colonne montant.
5. **Filtrage temporel** : `max_days_back` dans `config.ini` (défaut 90 jours) évite les doublons avec d'anciennes opérations manuelles.
6. **Catégorisation** : patterns dans `inc_category_mappings.py` (code) + `config_category_mappings.json` (utilisateur), utilisable par tous les formateurs via `inc_categorize.categorize_operation(libelle, SITE)`.
7. **TNR avant commit** — toute modif qui touche `cpt_format_*`, `cpt_update`, `cpt_pair`, `inc_excel_*` doit passer au moins `roundtrip` + `fast` (cf. [`Compta_tests.md`](Compta_tests.md)).
