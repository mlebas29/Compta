# Site BTC - Bitcoin Wallets

## Vue d'ensemble

Collecte automatique des transactions et soldes de 2 wallets Bitcoin via l'API publique mempool.space.

**Type:** Mode automatique (fetch complet)
**Source:** API REST publique (pas d'authentification)
**Wallets:** 2 wallets (BlueWallet, Phoenix Lightning)
**Unité:** SAT (satoshis, 1 BTC = 100,000,000 SAT)

## Configuration

### config.ini

```ini
[BTC]
name = Bitcoin Wallets
# Vos adresses publiques BTC (exemples ci-dessous — visibles sur la blockchain)
address_bluewallet = bc1qexamplewalletbluewallet00000000000000
address_phoenix = bc1qexamplewalletphoenix0000000000000000
# API publique
api_url = https://mempool.space/api
max_days_back = 90
```

**Note :** Les adresses Bitcoin sont publiques par nature (visibles sur la blockchain). Pas de credentials requis.

## Architecture technique

### API mempool.space

**Endpoints utilisés :**
- `GET /api/address/{address}/txs` - Liste des transactions
- `GET /api/address/{address}` - Balance et statistiques

**Caractéristiques :**
- Pas d'authentification requise
- Rate limit : ~10 req/s (géré par retry logic)
- Filtrage temporel : `max_days_back` (défaut: 90 jours)
- Retry avec backoff exponentiel (3 tentatives)

### Classification des transactions

**Logic de parsing (parse_btc_transaction):**

1. **Incoming** (our_input=0, our_output>0):
   - Montant : +satoshis
   - Label : "Received from {sender_address}"
   - Catégorie : "Change"

2. **Outgoing** (our_input>0, our_output=0):
   - Montant : -satoshis
   - Fee : satoshis (séparé)
   - Label : "Sent to {recipient_address}"
   - Catégorie : "Virement" (avec ref='-')

3. **Change** (our_input>0, our_output>0):
   - Net = our_output - our_input
   - Si net < 0 : dépense (avec change)
   - Si net > 0 : réception (rare)

**Fees :**
- Extraits automatiquement pour les transactions sortantes
- Générés comme opération séparée : "Transaction fee"
- Catégorie : "Frais bancaires"

## Flux de données

### Tier 1 - Fetch (cpt_fetch_BTC.py)

**Input :** Adresses BTC depuis config.ini
**Output :** CSV bruts dans dropbox/BTC/

```
dropbox/BTC/
├── btc_bluewallet_operations.csv  (raw)
├── btc_phoenix_operations.csv     (raw)
└── btc_balances.csv               (raw)
```

**Format raw operations :**
```csv
Date,Label,Amount,Currency,Wallet
2025-01-10 15:23:45,Received from bc1q...,150000,SAT,bluewallet
2025-01-09 12:00:00,Sent to bc1q...,-100000,SAT,bluewallet
2025-01-09 12:00:00,Transaction fee,-1000,SAT,bluewallet
```

**Format raw balances :**
```csv
Wallet,Balance,Currency,Date
BlueWallet BTC,150000,SAT,2025-01-12 16:30:00
Phoenix Lightning BTC,0,SAT,2025-01-12 16:30:00
...
```

### Tier 2 - Format (cpt_format_BTC.py)

**Monoscript :** Gère operations + balances

**Input :** CSV bruts
**Output :** CSV standardisés (9 ou 4 colonnes) vers stdout

**Format operations (9 colonnes) :**
```csv
Date;Libellé;Montant;Devise;Equiv;Réf;Catégorie;Compte;Commentaire
29/10/2025;Received from bc1q...;1011283;SAT;;;Change;BlueWallet BTC;
12/01/2026;Solde BTC;1011283;SAT;;;#Solde;BlueWallet BTC;
```

**Format balances (4 colonnes) :**
```csv
Date;Ligne;Montant;Compte
12/01/2026;#Solde BlueWallet BTC;8082216;BlueWallet BTC
12/01/2026;#Solde Phoenix Lightning BTC;0;Phoenix Lightning BTC
...
```

**Mappings comptes :**
```python
BTC_ACCOUNTS = {
    'btc_bluewallet': 'BlueWallet BTC',
    'btc_phoenix': 'Phoenix Lightning BTC',
}
```

### Tier 3 - Update (cpt_update.py)

**Input :** CSV temporaires formatés
**Output :** Excel comptes.xlsm (feuille Opérations)

- Import operations avec duplicate detection
- Archive des fichiers raw avec HDS
- Génération des #Solde par wallet

## Catégorisation automatique

Patterns définis dans `inc_category_mappings.py` (section `BTC_PATTERNS`). Voir le code source pour les regex.

**Appariements automatiques :**
- Virements : ref='-' → recherche opération symétrique via MESH_TRANSFERS

## Usage

### Workflow complet

```bash
# Tout en un
./cpt.py --sites BTC

# Étapes séparées
./cpt_fetch_BTC.py          # Collecte
./cpt_update.py             # Import
```

### Tests

```bash
# Test fetch seul
./cpt_fetch_BTC.py
ls -lh dropbox/BTC/         # Vérifier 3 CSV

# Test format
./cpt_format_BTC.py dropbox/BTC/btc_bluewallet_operations.csv
./cpt_format_BTC.py dropbox/BTC/btc_balances.csv

# Test workflow
./cpt.py --sites BTC --fetch-only
./cpt.py --sites BTC --update-only
```

### Vérifications

```bash
# Vérifier balances
cat dropbox/BTC/btc_balances.csv

# Vérifier une opération
cat dropbox/BTC/btc_bluewallet_operations.csv

# Statut système
./cpt.py --status
```

## Troubleshooting

### Erreur : "Failed after 3 attempts"

**Cause :** Rate limit API ou problème réseau

**Solution :**
1. Attendre 1-2 minutes (rate limit mempool.space)
2. Vérifier connexion internet
3. Tester URL manuellement :
   ```bash
   curl https://mempool.space/api/address/bc1qexamplewalletbluewallet00000000000000
   ```

### Erreur : "No transactions found"

**Cause :** max_days_back trop court ou wallet inactif

**Solution :**
1. Augmenter `max_days_back` dans config.ini :
   ```ini
   [BTC]
   max_days_back = 180  # 6 mois au lieu de 90
   ```
2. Vérifier que le wallet a bien des transactions récentes

### Erreur : "Invalid address"

**Cause :** Adresse Bitcoin incorrecte dans config.ini

**Solution :**
1. Vérifier format bc1q... (Bech32)
2. Tester sur mempool.space web
3. Corriger config.ini

### Balance = 0 mais opérations présentes

**Normal :** Le wallet a été vidé (sent to)

### Pas d'opérations récentes

**Normal :** Filtrage `max_days_back` exclut les anciennes transactions

## Limites et notes

- **Unité SAT :** satoshis (1 BTC = 100,000,000 SAT), pas de décimales
- **Adresses publiques :** Informations visibles sur la blockchain, pas de credentials requis
- **Rate limits API :** ~10 req/s, retry automatique avec backoff
- **Filtrage temporel :** `max_days_back = 90` (configurable)
- **Duplicate detection :** Date + Compte + Montant + Libellé
