# ETORO - Documentation technique

## Vue d'ensemble

**Site :** https://www.etoro.com
**Type :** Plateforme de trading (compte EUR + compte-titre USD)
**Collecte :** Mode semi-automatique (Playwright + 2FA email/SMS)
**Scripts :** `cpt_fetch_ETORO.py` (fetch) + `cpt_format_ETORO.py` (format)

> Migration Playwright (02/2026) : profil Chrome persistant + anti-détection, login semi-auto GPG + 2FA email/SMS.

## Mode semi-automatique (Playwright)

### Fonctionnement

Le script `cpt_fetch_ETORO.py` :
1. Lance Chrome avec profil persistant `.chrome_profile_etoro/`
2. Remplit les identifiants via GPG (credential `BaeT-M`)
3. Attend la validation 2FA (email ou SMS) par l'utilisateur
4. Exporte les opérations Money EUR (TSV)
5. Exporte les opérations Réserve USD (XLSX)
6. Capture PDF page d'accueil (soldes) via CDP
7. Capture PDF portfolio (positions) via CDP

### Détails techniques

- **Profil Chrome :** `.chrome_profile_etoro/` (persistant, conserve session)
- **Nettoyage cookies :** au lancement (prévention contamination OAuth)
- **Dates :** `hier - MAX_DAYS_BACK` → `hier` (eToro n'accepte pas aujourd'hui)
- **PDFs :** Capturés via CDP `Page.printToPDF` (fonctionne en mode headed)
- **Anti-bot :** `--disable-blink-features=AutomationControlled` + Chrome réel
- **Timeout login :** 300s (5 min pour 2FA)
- **Blocage Facebook :** le Facebook Pixel d'eToro est bloqué au niveau réseau (sinon un popup de consentement cookies Facebook masque le formulaire de login)

> ⚠️ **Modale « Nous préparons votre relevé »** (export Réserve XLSX) : eToro affiche *parfois* (1ʳᵉ génération de la journée / charge serveur) une modale « Nous préparons votre relevé / J'ai compris » — la génération du XLSX est asynchrone et le téléchargement se déclenche à la fin. **NE PAS fermer cette modale** : cliquer « J'ai compris » avant que le fichier soit prêt **annule** la génération (timeout 120s à vide). Le script ne touche pas la modale et attend simplement l'événement de téléchargement.

### Usage

```bash
./cpt_fetch_ETORO.py         # Mode normal
./cpt_fetch_ETORO.py -v      # Mode verbeux
```

## Mode manuel (secours)

En cas de blocage anti-bot, la collecte manuelle reste disponible. Voir `Compta_plus.md` section "Collecte manuelle de secours".

### Noms de fichiers détectés

Le script `cpt_format_ETORO.py` détecte automatiquement le type par **patterns dans le nom** (TSV/XLSX/CSV) et par **contenu** pour les PDF (`detect_pdf_type`) :

| Type | Détection | Exemples |
|------|-----------|----------|
| Money operations | `*.tsv` avec `transactions` ou `etorotransactions` | `eToroTransactions_22-12-2024_21-12-2025_110994.tsv` |
| Reserve operations | `*.xlsx` avec `account-statement` ou `accountstatement` | `etoro-account-statement-1-1-2025-12-20-2025.xlsx` |
| PDF accueil (soldes) | `*.pdf` contenant `USD disponible` + `EUR disponible` | `eToro_accueil.pdf` |
| PDF portfolio (positions) | `*.pdf` contenant `Actifs` + `Prix`/`Unités` | `eToro_portfolio.pdf` |
| Soldes | `*soldes*parsed*.csv` | `soldes_comptes_parsed.csv` |
| Positions | `*positions*parsed*.csv` | `positions_titres_parsed.csv` |

> Les deux PDF ont un nom fixe mais sont distingués par leur **contenu** (`detect_pdf_type` → `pdf_home` / `pdf_portfolio`), pas par leur nom.

**Avantages :**
- ✅ Pas de renommage nécessaire
- ✅ Compatible avec noms dynamiques (timestamps)

### Gestion des soldes

**Mode automatique :** Le fetch Playwright capture les PDFs accueil et portfolio via CDP. Le script `cpt_format_ETORO.py` extrait les soldes des PDFs.

**Mode secours :** En cas d'échec des PDFs, créer manuellement `dropbox/ETORO/soldes_comptes_parsed.csv` :
- Format : `Compte;Solde` (2 colonnes CSV)
- Noms de comptes EXACTS selon Excel
- OU laisser le script générer des #Solde à 0.00 et corriger dans Excel

## Architecture

**Tier 1 (fetch):** `cpt_fetch_ETORO.py` (Playwright semi-auto, profil Chrome persistant)

**Tier 2 (format):** `cpt_format_ETORO.py` (monoscript)
- **Mode opérations Money** : Conversion TSV → format standard 9 champs
  - Catégorisation déléguée à `inc_categorize` (patterns DPT, WDL, VIR/Virement)
  - Colonne Equiv laissée **vide** (déterminée par `cpt_pair` lors de l'appariement)
- **Mode opérations Réserve** : Conversion XLSX → format standard 9 champs
  - Catégorisation déléguée à `inc_categorize` (Position ouverte, Bénéfice/Perte, Dépôt, Dividende, Frais)
  - Colonne Equiv laissée **vide** (déterminée par `cpt_pair` lors de l'appariement)
- **Mode PDF** : Extraction des soldes (accueil) et des positions Titres (portfolio) → voir « Gestion des soldes » et « Positions »

**Tier 3 (update):** `cpt_update.py` (script générique)
- Import dans Excel
- Génération automatique des opérations symétriques Titres (achats/ventes)
- Appariement EUR↔USD par `cpt_pair`, qui renseigne la colonne Equiv (MESH_TRANSFERS cross-currency)
- Mise à jour Plus_value (positions extraites du PDF portfolio)
- Archivage avec HDS

## Configuration

**Dans `config.ini` :**
```ini
[ETORO]
name = eToro
base_url = https://www.etoro.com
credential_id = BaeT-M
max_days_back = 365
```

**Détection automatique (convention) :**
- Script format : `cpt_format_ETORO.py`
- Répertoire dropbox : `dropbox/ETORO/`
- Répertoire archives : `archives/ETORO/`

## Structure des comptes

eToro utilise une structure à **3 comptes** :

### 1. Compte eToro Money (EUR)
- **Type :** Compte de dépôt/retrait
- **Devise :** EUR
- **Nom Excel :** `Compte eToro Money`
- **Opérations :**
  - Virements bancaires (arrivée/départ)
  - Transferts vers Réserve USD (DPT = débit, WDL = crédit)

### 2. Portefeuille eToro USD Réserve
- **Type :** Espèces disponibles
- **Devise :** USD
- **Nom Excel :** `Portefeuille eToro USD Réserve`
- **Opérations :**
  - Dépôts depuis Money (EUR→USD)
  - Achats/Ventes de titres (Réserve ↔ Titres)
  - Dividendes, frais

### 3. Portefeuille eToro USD Titres
- **Type :** Valorisation des positions
- **Devise :** USD
- **Nom Excel :** `Portefeuille eToro USD Titres`
- **Opérations :**
  - Achats/Ventes de titres

### Flux typiques

**Dépôt (virement bancaire → Money) :**
```
Compte chèque commun → Compte eToro Money (EUR)
```

**Transfert Money → Réserve (conversion EUR→USD) :**
```
Compte eToro Money (EUR) → Portefeuille eToro USD Réserve (USD)
```

**Achat de titres :**
```
Portefeuille eToro USD Réserve (USD) → Portefeuille eToro USD Titres (USD)
```

## Catégorisation des opérations

La catégorisation n'est **plus** faite dans `cpt_format_ETORO.py` : elle est centralisée dans `inc_categorize.categorize_operation(libellé, site)`, qui applique les patterns déclarés pour `ETORO` dans `config_category_mappings.json`. Les clés de catégorie « atelier » sont préfixées d'un `@` (ex. `@Change`, `@Achat titres`), résolues en catégories finales à l'import.

Le format **ne remplit jamais la colonne Equiv** (laissée vide) : l'appariement cross-devise et le calcul de l'équivalent EUR sont faits en aval par `cpt_pair`.

### Opérations Money (EUR)

| Pattern libellé | Catégorie | Réf | Appariement |
|-----------------|-----------|-----|-------------|
| `DPT` | `@Change` | `-` | Réserve (Dépôt) |
| `WDL` / `WITHDRAWAL` | `@Change` | `-` | Réserve (retrait) |
| `VIR` / `VIREMENT` / virement nominatif | `-` | `-` | Compte chèque commun |

### Opérations Réserve (USD)

| Type opération | Catégorie | Réf | Appariement |
|----------------|-----------|-----|-------------|
| Position ouverte | `@Achat titres` | `-` | Titres (symétrique) |
| Bénéfice / Perte | `@Vente titres` | `-` | Titres (symétrique) |
| Dépôt / Transfer EUR↔USD | `@Change` | `-` | Money (Change) via appariement |
| Dividende | `Coupon` | — | - |
| Frais / Commission | `Frais bancaires` | — | - |

> Pour un achat de titres (`@Achat titres`), le format **inverse le signe** du montant : le XLSX affiche la valeur de l'achat en positif, mais la Réserve est débitée (négatif).

## Mécanisme d'appariement EUR↔USD

### Principe

Les opérations de transfert entre Money (EUR) et Réserve (USD) sont appariées automatiquement par `cpt_pair`, qui **renseigne la colonne Equiv** (toujours en EUR). Au stade du format, Equiv est laissée **vide** des deux côtés — c'est l'appariement qui l'établit.

### Exemple concret

**Fichier eToroTransactions_*.tsv :**
```
eToro Trading Platform DPT  24/09/2025  -900  EUR
```
→ Format : `Date=24/09/2025; Montant=-900,00; Devise=EUR; Equiv=` (vide)

**Fichier etoro-account-statement*.xlsx :**
```
Dépôt  900.00 EUR eToroMoney  24/09/2025  1050,06 USD
```
→ Format : `Date=24/09/2025; Montant=1050,06; Devise=USD; Equiv=` (vide)

### Appariement cross-currency (cpt_pair)

`cpt_pair` rapproche la ligne Money (EUR, catégorie `@Change`) et la ligne Réserve (USD, `@Change`) sur dates proches et montants cohérents, attribue une Réf commune, et **remplit Equiv** avec l'équivalent EUR (ex. `900,00` côté Réserve).

### Taux de change

Une fois Equiv renseignée, le taux de change se déduit :
```
Taux = Montant USD / |Equiv EUR| = 1050.06 / 900 ≈ 1.1667 USD/EUR
```

## Formats de sortie

### Format opérations Money (9 champs)

```csv
Date;Libellé;Montant;Devise;Equiv;Réf;Catégorie;Compte;Commentaire
24/09/2025;eToro Trading Platform DPT;-900,00;EUR;;-;@Change;Compte eToro Money;
24/09/2025;MR OU MME JEAN DUPONT;800,00;EUR;;-;-;Compte eToro Money;
```
> Equiv reste vide au format ; `cpt_pair` la renseigne à l'appariement. Le `#Solde` Money ne vient pas du TSV mais du PDF accueil (`Relevé solde`).

### Format opérations Réserve (9 champs)

```csv
Date;Libellé;Montant;Devise;Equiv;Réf;Catégorie;Compte;Commentaire
24/09/2025;Dépôt 900.00 EUR eToroMoney;1050,06;USD;;-;@Change;Portefeuille eToro USD Réserve;
24/09/2025;Position ouverte BTC/USD;-999,98;USD;;-;@Achat titres;Portefeuille eToro USD Réserve;
21/05/2025;Dividende ALFA.PA/EUR;0,17;USD;;;Coupon;Portefeuille eToro USD Réserve;
```
> Equiv reste vide au format. Le `#Solde` Réserve vient du PDF accueil, pas du XLSX.

## Fichiers traités (mode manuel)

### Dans dropbox/ETORO/

1. **eToroTransactions_DD-MM-YYYY_DD-MM-YYYY_HHMMSS.tsv**
   - Source: Téléchargement manuel depuis https://www.etoro.com/wallet/account/EUR
   - Type: Opérations compte Money (EUR)
   - Format: TSV (4 colonnes: Name, Date, Amount, Currency)

2. **etoro-account-statement-D-M-YYYY-D-M-YYYY.xlsx**
   - Source: Téléchargement manuel depuis https://www.etoro.com/documents/accountstatement
   - Type: Opérations compte Réserve (USD)
   - Format: XLSX, onglet **« Activité du compte »**, colonnes lues: Date, Type, Détails, Montant, Unités

3. **eToro_accueil.pdf** et **eToro_portfolio.pdf**
   - Source: Impression PDF des pages accueil/portfolio (via CDP `printToPDF` en mode auto)
   - Type: Soldes (accueil) et positions Titres (portfolio)
   - Extraction: `pdfplumber` → `soldes_comptes_parsed.csv` + `positions_titres_parsed.csv`

4. **soldes_comptes_parsed.csv** (optionnel, secours)
   - Source: Généré par le format depuis le PDF accueil, ou création manuelle en secours
   - Type: Soldes des comptes Money, Réserve, Titres
   - Format: CSV (2 colonnes: Compte;Solde)

### Après import (archives/ETORO/)

```
eToroTransactions_22-12-2024_21-12-2025_110994_HDS_20251221_143022.tsv
etoro-account-statement-1-1-2025-12-20-2025_HDS_20251221_143022.xlsx
soldes_comptes_parsed_HDS_20251221_143022.csv
```

## Cas particuliers

### Montant EUR dans un libellé USD

Les opérations « Dépôt » de l'Account Statement (USD) portent le montant EUR dans le libellé (`Details`), pas dans une colonne dédiée :
```
Type: Dépôt
Details: 900.00 EUR eToroMoney
Amount: 1050.06 USD
```

**Note :** la fonction `extract_eur_amount` existe encore dans `cpt_format_ETORO.py` mais n'est **plus appelée** — le format ne remplit plus Equiv. L'équivalent EUR est établi par `cpt_pair` lors de l'appariement Money↔Réserve.

### Période de collecte

**Recommandation :** Collecter les **6 derniers mois** pour garantir que toutes les opérations sont capturées, même en cas de retard de traitement eToro.

**Note :** La détection de doublons dans `cpt_update.py` filtre automatiquement les opérations déjà importées.

### Positions (valorisations titres)

Les positions sont extraites **automatiquement** du PDF portfolio (`eToro_portfolio.pdf`), capturé par le fetch.

**Chaîne :**
1. `parse_pdf_portfolio` lit chaque actif (ticker, nom, valeur) et le total dans le texte du PDF (`pdfplumber`)
2. Écriture de `positions_titres_parsed.csv` (`Date;Ligne;Montant`) + mise à jour de `soldes_comptes_parsed.csv` avec le total Titres
3. `process_positions` produit les lignes 4 colonnes (`Date;Ligne;Montant;Compte`) et ajoute la ligne `#Solde Titres`, importées sur le compte Titres

**Secours :** si le PDF portfolio manque ou est illisible, relever les valorisations depuis https://www.etoro.com/portfolio/overview et fournir manuellement `positions_titres_parsed.csv`.

## Workflow de test

```bash
# 1. Télécharger fichiers depuis eToro (voir procédure ci-dessus)
# 2. Placer dans dropbox/ETORO/

cd ~/Compta
export COMPTA_MODE=test

# 3. Test du format script seul
./cpt_format_ETORO.py dropbox/ETORO/eToroTransactions_*.tsv > test_money.csv
./cpt_format_ETORO.py dropbox/ETORO/etoro-account-statement-*.xlsx > test_reserve.csv
cat test_money.csv
cat test_reserve.csv

# 4. Test du workflow complet
./cpt_update.py -v

# 5. Vérifier comptes.xlsm (feuille Opérations)
libreoffice comptes.xlsm

# 6. Vérifier contrôles (A1 doit être ".")
./cpt_controles.py -v
```

## Dépendances

**Python :**
- `openpyxl` - Lecture XLSX (Account Statement)
- `pdfplumber` - Extraction texte des PDF accueil/portfolio (soldes + positions)
- `csv` - Parsing TSV (Money transactions)
- `re` - Détection de patterns (dates, montants, tickers)
- `datetime` - Gestion des dates

**Installation :**
```bash
pip3 install openpyxl pdfplumber
```

## Notes importantes

1. **Mode semi-automatique** - Fetch Playwright avec Chrome réel (profil persistant + anti-détection)
2. **Noms originaux conservés** - Pas de renommage nécessaire (convention non stricte)
3. **Colonne Equiv** - Laissée vide au format ; renseignée par `cpt_pair` lors de l'appariement EUR↔USD
4. **PDFs via CDP** - `Page.printToPDF` en mode headed (page.pdf() ne fonctionne qu'en headless)
5. **Date max = hier** - eToro refuse les exports incluant la date du jour
6. **Mode secours** - Collecte manuelle disponible si anti-bot bloque (voir Compta_plus.md)
