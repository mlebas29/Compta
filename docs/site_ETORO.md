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

### Usage

```bash
./cpt_fetch_ETORO.py         # Mode normal
./cpt_fetch_ETORO.py -v      # Mode verbeux
```

## Mode manuel (secours)

En cas de blocage anti-bot, la collecte manuelle reste disponible. Voir `Compta_plus.md` section "Collecte manuelle de secours".

### Noms de fichiers détectés

Le script `cpt_format_ETORO.py` détecte automatiquement le type par **patterns dans le nom** :

| Type | Patterns détectés | Exemples |
|------|-------------------|----------|
| Money operations | `*.tsv` avec `transactions` ou `etorotransactions` | `eToroTransactions_22-12-2024_21-12-2025_110994.tsv` |
| Reserve operations | `*.xlsx` avec `account-statement` ou `accountstatement` | `etoro-account-statement-1-1-2025-12-20-2025.xlsx` |
| Soldes | `*soldes*.csv` | `soldes_comptes_parsed.csv` |

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
  - Catégorisation (DPT, WDL, Virement)
  - Remplissage colonne Equiv pour appariements EUR↔USD
- **Mode opérations Réserve** : Conversion XLSX → format standard 9 champs
  - Catégorisation (Position ouverte, Bénéfice/Perte, Dépôt, Dividende, Frais)
  - Extraction montant EUR pour colonne Equiv

**Tier 3 (update):** `cpt_update.py` (script générique)
- Import dans Excel
- Génération automatique des opérations symétriques Titres (achats/ventes)
- Appariement EUR↔USD via colonne Equiv (MESH_TRANSFERS cross-currency)
- Mise à jour Plus_value (positions manuelles)
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

### Opérations Money (EUR)

| Pattern libellé | Catégorie | Réf | Equiv | Appariement |
|-----------------|-----------|-----|-------|-------------|
| `DPT` | Change | `-` | Montant EUR | Réserve (Dépôt) |
| `WDL` | Change | `-` | Montant EUR | Réserve (retrait) |
| `JEAN DUPONT` / Virement | Virement | `-` | Vide | Compte chèque commun |

**Colonne Equiv :**
- DPT/WDL : Remplir avec le montant EUR (même signe)
- Autres : Laisser vide

### Opérations Réserve (USD)

| Type opération | Catégorie | Réf | Equiv | Appariement |
|----------------|-----------|-----|-------|-------------|
| Position ouverte | Achat titres | `-` | Vide | Titres (symétrique) |
| Bénéfice/Perte | Vente titres | `-` | Vide | Titres (symétrique) |
| Dépôt XXX EUR | Change | `-` | Montant EUR extrait | Money (Change) via MESH_TRANSFERS |
| Dividende | Coupon | Vide | Vide | - |
| Frais / Commission | Frais bancaires | Vide | Vide | - |
| Autres | `-` | Vide | Vide | - |

**Colonne Equiv :**
- Dépôt : Extraire montant EUR du libellé (ex: "500.00 EUR eToroMoney" → 500.00)
- Autres : Laisser vide

## Mécanisme d'appariement EUR↔USD

### Principe

Les opérations de transfert entre Money (EUR) et Réserve (USD) sont appariées automatiquement via la colonne **Equiv** (toujours en EUR).

### Exemple concret

**Fichier eToroTransactions_*.tsv :**
```
eToro Trading Platform DPT  24/09/2025  -900  EUR
```
→ Format : `Date=24/09/2025; Montant=-900,00; Devise=EUR; Equiv=-900,00`

**Fichier etoro-account-statement*.xlsx :**
```
Dépôt  900.00 EUR eToroMoney  24/09/2025  1050,06 USD
```
→ Format : `Date=24/09/2025; Montant=1050,06; Devise=USD; Equiv=900,00`

### Détection MESH_TRANSFERS (cross-currency)

Le système `cpt_update.py` compare :
- **Money** : `Equiv = -900 EUR` (pattern DPT)
- **Réserve** : `Equiv = +900 EUR` (pattern Dépôt)
- **Match** : Signes opposés, montants égaux, dates proches
- **Résultat** : Opérations appariées (Réf attribuée)

### Taux de change

Le taux de change est calculé automatiquement :
```
Taux = Montant USD / |Equiv EUR| = 1050.06 / 900 = 1.1667 USD/EUR
```

## Formats de sortie

### Format opérations Money (9 champs)

```csv
Date;Libellé;Montant;Devise;Equiv;Réf;Catégorie;Compte;Commentaire
24/09/2025;eToro Trading Platform DPT;-900,00;EUR;-900,00;-;Change;Compte eToro Money;
24/09/2025;MR OU MME JEAN DUPONT;800,00;EUR;;-;Virement;Compte eToro Money;
24/09/2025;Relevé compte;1234,56;EUR;;;#Solde;Compte eToro Money;
```

### Format opérations Réserve (9 champs)

```csv
Date;Libellé;Montant;Devise;Equiv;Réf;Catégorie;Compte;Commentaire
24/09/2025;Dépôt 900.00 EUR eToroMoney;1050,06;USD;900,00;-;Change;Portefeuille eToro USD Réserve;
24/09/2025;Position ouverte BTC/USD;-999,98;USD;;-;Achat titres;Portefeuille eToro USD Réserve;
21/05/2025;Dividende AI.PA/EUR;0,17;USD;;Coupon;Portefeuille eToro USD Réserve;
24/09/2025;Relevé compte;330,76;USD;;;#Solde;Portefeuille eToro USD Réserve;
```

## Fichiers traités (mode manuel)

### Dans dropbox/ETORO/

1. **eToroTransactions_DD-MM-YYYY_DD-MM-YYYY_HHMMSS.tsv**
   - Source: Téléchargement manuel depuis https://www.etoro.com/wallet/account/EUR
   - Type: Opérations compte Money (EUR)
   - Format: TSV (4 colonnes: Name, Date, Amount, Currency)

2. **etoro-account-statement-D-M-YYYY-D-M-YYYY.xlsx**
   - Source: Téléchargement manuel depuis https://www.etoro.com/documents/accountstatement
   - Type: Opérations compte Réserve (USD)
   - Format: XLSX (colonnes: Type, Details, Amount, Realized Equity, Balance, Position ID, NWA, Date)

3. **soldes_comptes_parsed.csv** (optionnel)
   - Source: Création manuelle
   - Type: Soldes des comptes Money, Réserve, Titres
   - Format: CSV (2 colonnes: Compte;Solde)

### Après import (archives/ETORO/)

```
eToroTransactions_22-12-2024_21-12-2025_110994_HDS_20251221_143022.tsv
etoro-account-statement-1-1-2025-12-20-2025_HDS_20251221_143022.xlsx
soldes_comptes_parsed_HDS_20251221_143022.csv
```

## Cas particuliers

### Extraction montant EUR depuis libellé USD

**Problème :** Les opérations "Dépôt" dans Account Statement (USD) contiennent le montant EUR dans le libellé, mais pas dans une colonne dédiée.

**Exemple :**
```
Type: Dépôt
Details: 900.00 EUR eToroMoney
Amount: 1050.06 USD
```

**Solution :** Voir le code source (`cpt_format_ETORO.py`) pour l'extraction regex.

### Période de collecte

**Recommandation :** Collecter les **6 derniers mois** pour garantir que toutes les opérations sont capturées, même en cas de retard de traitement eToro.

**Note :** La détection de doublons dans `cpt_update.py` filtre automatiquement les opérations déjà importées.

### Positions (valorisations titres)

**Important :** Les positions ne sont pas disponibles en téléchargement depuis eToro en mode manuel.

**Procédure :**
1. Relever manuellement les valorisations depuis https://www.etoro.com/portfolio/overview
2. Les renseigner dans Excel (feuille Plus_value) après import des opérations
3. Colonnes à remplir : Date SOLDE (J) et SOLDE (K) pour chaque ligne de titre

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
- `csv` - Parsing TSV (Money transactions)
- `re` - Extraction montants EUR
- `datetime` - Gestion des dates

**Installation :**
```bash
pip3 install openpyxl
```

## Notes importantes

1. **Mode semi-automatique** - Fetch Playwright avec Chrome réel (profil persistant + anti-détection)
2. **Noms originaux conservés** - Pas de renommage nécessaire (convention non stricte)
3. **Colonne Equiv critique** - Nécessaire pour appariement EUR↔USD via MESH_TRANSFERS
4. **PDFs via CDP** - `Page.printToPDF` en mode headed (page.pdf() ne fonctionne qu'en headless)
5. **Date max = hier** - eToro refuse les exports incluant la date du jour
6. **Mode secours** - Collecte manuelle disponible si anti-bot bloque (voir Compta_plus.md)
