# Kraken - Documentation Technique

## Vue d'ensemble

**Type:** Compte crypto (exchange)
**Mode:** Semi-automatique (fetch Playwright avec login interactif + 2FA email)
**Tier 1:** `cpt_fetch_KRAKEN.py` (Playwright Chrome, profil persistant)
**Tier 2:** `cpt_format_KRAKEN.py` (conversion CSV → CSV standard)
**Tier 3:** `cpt_update.py` (extraction ZIP automatique + import)
**URL:** https://www.kraken.com
**Credentials:** GPG (`BaKr-M`)

## Architecture

### Comptes gérés

Kraken gère 2 comptes séparés dans `comptes.xlsm`:

| Compte Excel | Description | Devise |
|--------------|-------------|--------|
| Compte Kraken EUR | Fiat (EUR) | EUR |
| Compte Kraken BTC | Crypto (BTC) | BTC |

**Note:** Même organisation que BB/DEGIRO/WISE : comptes séparés Titres/Réserve par devise/asset.

### Flux de données

```
cpt_fetch_KRAKEN.py (Playwright Chrome)
    ├─ Login GPG auto-fill + 2FA email (interactif)
    ├─ Navigation vers /c/account-settings/documents
    ├─ Création/réutilisation exports (Registre 90j + Soldes)
    └─ Téléchargement 2 ZIP → dropbox/KRAKEN/
        ↓
cpt_update.py (extraction automatique)
    ├─ Extrait ledgers.csv dans dropbox/KRAKEN/
    ├─ Extrait YYYY-MM-DD_balances.csv dans dropbox/KRAKEN/
    ├─ Archive ZIP avec HDS → archives/KRAKEN/kraken-*_HDS_xxx.zip
    └─ Pour chaque CSV:
        ├─ Appelle cpt_format_KRAKEN.py (CSV → CSV standard temporaire)
        ├─ Import CSV dans comptes.xlsm
        │   ├─ ledgers.csv → Feuille Opérations (Compte Kraken EUR + Compte Kraken BTC)
        │   └─ balances.csv → Feuille Plus_value (Compte Kraken BTC uniquement)
        └─ Archive CSV avec HDS → archives/KRAKEN/ledgers_HDS_xxx.csv
```

**Important:**
- Les 2 ZIP et les 2 CSV sont tous archivés avec le même HDS pour traçabilité
- Les achats crypto génèrent 2 opérations symétriques (Réserve debit + Titres credit)

## Tier 1 - Fetch Playwright

### Script: `cpt_fetch_KRAKEN.py`

**Technologie:** Playwright sync API avec Chrome réel (pas Chromium)

**Profil persistant:** `.chrome_profile_kraken/` (cookies de session, mots de passe mémorisés)

**Usage:**
```bash
./cpt_fetch_KRAKEN.py -v         # Direct (verbose)
./cpt_fetch.py --sites KRAKEN    # Via orchestrateur
```

### Workflow automatisé

1. Lancement Chrome avec profil persistant (`launch_persistent_context`)
2. Navigation vers `https://www.kraken.com/c` (détection session active)
3. Si session expirée → page login :
   - Auto-fill identifiants via GPG (`credential_id = BaKr-M`)
   - 2FA email : l'utilisateur copie le lien de validation dans la fenêtre Chrome
4. Navigation vers `/c/account-settings/documents`
5. Pour chaque export (Registre 90j + Soldes) :
   - Vérification si export existant téléchargeable (réutilisation)
   - Sinon : création via formulaire (type, dates, format CSV)
6. Téléchargement 2 ZIP → `dropbox/KRAKEN/`
7. Fermeture navigateur

### Procédure 2FA email

Kraken exige la validation "nouveau device" par email lors des premières connexions ou après expiration de session :

1. Le script remplit automatiquement les identifiants et soumet le formulaire
2. Un email Kraken est envoyé avec un lien de validation
3. **Copier le lien** depuis l'email et le **coller dans la fenêtre Chrome** ouverte par le script
4. Le script détecte automatiquement la validation et poursuit

**Important:** Ne pas ouvrir le lien dans le navigateur par défaut (Brave) — Kraken exige que le lien soit ouvert dans le même navigateur que le login.

### Particularités techniques

- **React UI :** `force=True` sur les clics (modal overlay `data-portaled-element` intercepte les events)
- **Dropdowns React :** `dispatch_event("click")` au lieu de `click()` standard
- **Scope modale :** locators scopés dans `div[role='dialog']` pour cibler les éléments de la modale
- **Date picker :** `react-day-picker` avec dropdowns année/mois (`data-testid='datepicker-year/month-dropdown-button'`) + grille `.rdp-table`
- **Export readiness :** comptage boutons download avant/après création (pas juste > 0)
- **Session expirée :** détection de redirection vers `id.kraken.com/sign-in` dans `navigate_to_exports()`

### Contenu des ZIP

**1. kraken-ledgers-*.zip** contient:
```
ledgers.csv
```

**2. kraken-balances-*.zip** contient:
```
YYYY-MM-DD_balances.csv
```

## Tier 2 - Format script

### Script: `cpt_format_KRAKEN.py`

**Fonction:** Parse les fichiers CSV Kraken et génère des CSV au format standard (9 ou 4 colonnes).

**Monoscript:** Détection automatique du type de fichier (ledgers vs balances).

**Input:**
- CSV ledgers: `dropbox/KRAKEN/ledgers.csv`
- CSV balances: `dropbox/KRAKEN/YYYY-MM-DD_balances.csv`

**Output:**
- Operations (ledgers): CSV standard 9 colonnes sur stdout (capturé par `cpt_update.py`)
- Positions (balances): CSV standard 4 colonnes sur stdout (capturé par `cpt_update.py`)

### Traitement ledgers.csv (opérations)

**1. Parsing CSV:**
- Format: `txid,refid,time,type,subtype,aclass,subclass,asset,wallet,amount,fee,balance`
- Filtrage: opérations < `max_days_back` jours (configurable `config.ini [KRAKEN] max_days_back`)

**2. Groupement par refid:**
- Les achats crypto génèrent 2 entrées avec le même refid:
  - `type = spend` (débit EUR)
  - `type = receive` (crédit crypto)
- Les dépôts/retraits génèrent 1 entrée unique

**3. Génération opérations:**

**Single entries (deposits, withdrawals):**
- `deposit EUR` → Virement (Compte Kraken EUR)
- `withdrawal EUR` → Virement (Compte Kraken EUR)

**Paired entries (crypto purchases):**
- Génère 2 opérations symétriques:
  1. EUR account debit: Catégorie `Change`, Montant EUR négatif, **Equiv = montant EUR négatif**, Ref = `-`
  2. BTC account credit: Catégorie `Change`, Montant BTC positif, **Equiv = montant EUR positif**, Ref = `-`
- Auto-pairing via **MESH_TRANSFERS** cross-currency (`abs(equiv_EUR) == abs(equiv_BTC)`)
- `cpt_update.py` assigne automatiquement ref `btcxx` aux deux opérations

**4. Balance EUR:**
- Extrait depuis dernière entrée EUR dans ledgers.csv
- Utilisé pour ligne `#Solde` du compte EUR

### Traitement balances.csv (positions)

**1. Parsing CSV:**
- Format: `asset,aclass,subclass,wallet,quantity,price (USD),value (USD)`
- Date extraite du nom de fichier: `YYYY-MM-DD_balances.csv`

**2. Filtrage:**
- Skip ligne "Total"
- Skip EUR (déjà dans #Solde du compte EUR)
- Conserve uniquement crypto assets (BTC, ETH, etc.)

**3. Génération positions:**
- Format: `Date;Ligne;Montant;Compte`
- Une ligne par crypto asset (Compte Kraken BTC)
- Montant = valeur en USD (format Kraken)

### Structure CSV Kraken

Voir le code source (`cpt_format_KRAKEN.py`) pour le détail des colonnes.

**ledgers.csv :** `txid,refid,time,type,subtype,aclass,subclass,asset,wallet,amount,fee,balance`
- `refid` relie les entrées pairées (spend/receive)
- `type` : deposit, spend, receive, withdrawal

**balances.csv :** `asset,aclass,subclass,wallet,quantity,price (USD),value (USD)`

### Format de sortie

**Operations (ledgers):**
```csv
Date;Libellé;Montant;Devise;Equiv;Réf;Catégorie;Compte;Commentaire
18/09/2025;Dépôt EUR;50.00;EUR;;-;Virement;Compte Kraken EUR;
23/09/2025;Achat BTC;-50.50;EUR;-50.50;-;Change;Compte Kraken EUR;Fee: 0.50 EUR
23/09/2025;Achat BTC;0.00051277;BTC;50.50;-;Change;Compte Kraken BTC;
23/09/2025;Relevé Compte Kraken EUR;10.00;EUR;;;#Solde;Compte Kraken EUR;
```

**Note sur colonnes :**
- **Equiv** : Montant EUR pour auto-pairing MESH_TRANSFERS (négatif EUR side, positif BTC side, même valeur absolue)
- **Ref** : `-` signale opérations à appairer, `cpt_update.py` assigne automatiquement `btcxx`

**Positions (balances):**
```csv
Date;Ligne;Montant;Compte
02/01/2026;BTC;3862.56;Compte Kraken BTC
```

## Configuration

### config.ini

```ini
[KRAKEN]
name = Kraken
base_url = https://www.kraken.com
credential_id = BaKr-M
max_days_back = 90
```

**Paramètres:**
- `base_url`: URL de base (déclenche le fetch automatique via `cpt_fetch.py`)
- `credential_id`: Identifiant GPG pour login automatique
- `max_days_back`: Limite temporelle pour import (90 jours recommandé)

### Sites enabled

```ini
[sites]
enabled = SOCGEN,NATIXIS,BOURSOBANK,DEGIRO,ETORO,WISE,KRAKEN
```

## Workflow utilisateur

### Fetch + import automatique

```bash
# Via cpt.py (workflow complet)
cpt

# Ou ciblé sur Kraken uniquement
cpt --sites KRAKEN
```

Le script ouvre Chrome, remplit les identifiants, attend la validation 2FA email, puis télécharge les exports automatiquement.

### Import seul (si ZIP déjà dans dropbox)

```bash
# Placer les ZIP manuellement dans dropbox/KRAKEN/ (mode secours)
cp ~/Downloads/kraken-ledgers-*.zip dropbox/KRAKEN/
cp ~/Downloads/kraken-balances-*.zip dropbox/KRAKEN/

# Import sans fetch
./cpt_update.py -v
```

## Particularités techniques

### Extraction automatique des ZIP

Le script `cpt_update.py` gère automatiquement l'extraction ZIP (méthode `extract_kraken_zips()`) :
- Détection ZIP dans `dropbox/KRAKEN/`
- Extraction des CSV dans `dropbox/KRAKEN/`
- Archivage des ZIP avec HDS dans `archives/KRAKEN/`
- Traitement séquentiel des CSV par `cpt_format_KRAKEN.py`
- Archivage des CSV avec HDS dans `archives/KRAKEN/`

### Comptes séparés (pattern WISE)

Kraken suit le pattern comptes séparés comme WISE (pas comme BB/DEGIRO):
- **Compte Kraken EUR:** Fiat (EUR)
- **Compte Kraken BTC:** Crypto (BTC)
- **Comptes séparés** par devise/asset

**Opérations symétriques** pour achats crypto:
- Compte Kraken EUR debit (EUR avec fee)
- Compte Kraken BTC credit (crypto)

### Multi-assets crypto

Kraken supporte de nombreux crypto-actifs:
- BTC (Bitcoin)
- ETH (Ethereum)
- SOL (Solana)
- ADA (Cardano)
- DOT (Polkadot)
- etc.

Tous sont traités dans des comptes crypto dédiés (Compte Kraken BTC, etc.).

### Valorisation en USD

Kraken fournit les valorisations en **USD** (pas EUR):
- Colonne `price (USD)` et `value (USD)` dans balances.csv
- La feuille Plus_value Excel affichera les montants en USD
- Conversion EUR possible via cotations ultérieurement

### Fees (frais de transaction)

Les fees sont inclus dans le montant de l'opération spend:
- `amount = -50.00, fee = 0.50` → montant net = `-50.50 EUR`
- Commentaire: `Fee: 0.50 EUR`
- Permet de tracer les frais tout en conservant le montant exact débité

## Limites et contraintes

### Login interactif requis

Le fetch nécessite une intervention utilisateur pour la 2FA email (copier-coller du lien de validation dans Chrome). Ce n'est pas un fetch 100% automatique comme BTC/XMR.

### Limite temporelle recommandée

**max_days_back = 90** pour éviter:
- Import de doublons avec anciennes opérations manuelles
- Surcharge Excel avec historique trop long

**Ajustable** selon besoin (30, 60, 120 jours).

### Format CSV uniquement

Kraken exporte en CSV (pas XLSX), suffisant pour notre usage.

### Valorisation en USD

Les montants des positions sont en USD, pas EUR. Nécessite conversion manuelle ou via cotations.

## Tests et validation

### Test fetch + import

```bash
# 1. Fetch Kraken (Chrome s'ouvre, valider 2FA email)
./cpt_fetch_KRAKEN.py -v

# Résultat attendu:
# ✓ Export Registre trouvé (téléchargement direct) ou créé
# ✓ Export Soldes trouvé (téléchargement direct) ou créé
# ✓ 2 ZIP téléchargés dans dropbox/KRAKEN/

# 2. Import
./cpt_update.py -v

# 3. Vérifier
./cpt.py --status

# 4. Rollback si nécessaire
./cpt.py --fallback
```

### Vérifications

- [ ] 2 ZIP téléchargés dans `dropbox/KRAKEN/` par le fetch
- [ ] ZIP extraits automatiquement (CSV créés dans dropbox/KRAKEN/)
- [ ] ZIP et CSV archivés dans `archives/KRAKEN/` avec HDS
- [ ] Opérations importées (Compte Kraken EUR + Compte Kraken BTC)
- [ ] Positions importées (Compte Kraken BTC)
- [ ] Achats crypto pairés correctement (2 opérations symétriques)
- [ ] `dropbox/KRAKEN/` vide après import

## Troubleshooting

### Erreur "Cannot determine file type from filename"

**Cause:** Nom de fichier CSV non reconnu (ni "ledgers" ni "balances").

**Solution:** Vérifier que les fichiers suivent le pattern:
- `ledgers.csv`
- `YYYY-MM-DD_balances.csv`

### Erreur "Unexpected N entries for refid"

**Cause:** Opération complexe avec plus de 2 entrées pour le même refid.

**Solution:** Vérifier manuellement les entrées et adapter le script si nécessaire.

### Soldes incohérents (erreurs COMPTES)

**Cause:** Opérations manuelles anciennes avec libellés différents.

**Solution:**
1. Vérifier colonne K (Écart) dans feuille Contrôles
2. Utiliser `./cpt_controles.py -v` pour diagnostic détaillé
3. Identifier opérations en doublon
4. Corriger anciens libellés Excel pour matcher Kraken
5. Re-import après `./cpt.py --fallback`

### Positions non mises à jour

**Cause:** Fichier balances.csv non trouvé ou mal formaté.

**Solution:**
1. Vérifier présence de `YYYY-MM-DD_balances.csv` dans dropbox/KRAKEN/
2. Vérifier format CSV (colonnes asset, value (USD))
3. Vérifier extraction ZIP réussie

