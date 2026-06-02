# Site XMR - Monero Wallets

## Vue d'ensemble

Collecte automatique des transactions et soldes d'un wallet Monero via monero-wallet-cli (commandes directes).

**Type:** Mode automatique (fetch complet)
**Source:** monero-wallet-cli (subprocess local)
**Wallets:** 1 wallet (Cake Wallet XMR)
**Unité:** XMR (Monero, 12 décimales)

## Configuration

### config.ini

```ini
[XMR]
name = Monero Wallets
# Chemin wallet
wallet_cake = ~/Monero/wallets/cake/cake
# Chemin monero-wallet-cli
wallet_cli_dir = ~/Applications/monero-gui-v0.18.4.0/extras
# Credential ID pour GPG (passwords wallets)
credential_id = CrMo-DE-M
# Adresse du nœud Monero (daemon)
# Options :
#   - localhost:18081  (nœud local sans auth)
#   - IP:PORT          (nœud privé distant avec auth, ex: 18089 pour RPC restreint)
daemon_address = localhost:18081
# Credential ID pour authentification RPC du nœud distant (optionnel)
# Laisser vide pour nœud local sans auth
# Format dans credentials.md.gpg : | SiMoNo-M | username | password |
daemon_credential_id =
max_days_back = 90
```

**Deux configurations supportées :**

1. **Nœud local (sans authentification) :**
   ```ini
   daemon_address = localhost:18081
   daemon_credential_id =
   ```

2. **Nœud distant (avec authentification) :**
   ```ini
   daemon_address = monero-node.example.lan:18089
   daemon_credential_id = SiMoNo-M
   ```

### credentials.md.gpg

**Format :**
```markdown
| ID | Login | Password |
|----|-------|----------|
| CrMo-DE-M | | <password_wallets> |
| SiMoNo-M | <username_rpc> | <password_rpc> |
```

**Entrées :**

1. **CrMo-DE-M** (obligatoire) :
   - Password du wallet Monero
   - Champ Login vide (non utilisé)

2. **SiMoNo-M** (optionnel) :
   - Authentification RPC du nœud distant
   - Login = username RPC
   - Password = password RPC
   - Non nécessaire pour nœud local

## Prérequis

### Monero Node

**Deux configurations supportées :**

#### 1. Nœud local (sans authentification)

**Setup :**
- Monero GUI ou daemon monérod actif sur localhost
- Port 18081 (RPC standard)
- Pas d'authentification requise

**Configuration :**
```ini
daemon_address = localhost:18081
daemon_credential_id =
```

**Démarrage :**
```bash
# Option 1: Via Monero GUI (recommandé)
monero-wallet-gui

# Option 2: Via ligne de commande
~/Applications/monero-gui-v0.18.4.0/extras/monerod --detach

# Vérifier
curl http://localhost:18081/get_info
monerod status
```

#### 2. Nœud privé distant (avec authentification)

**Setup :**
- Nœud Monero configuré avec RPC authentifié
- Port 18089 (RPC restreint, recommandé) ou 18081
- Authentification HTTP Digest requise

**Configuration :**
```ini
daemon_address = monero-node.example.lan:18089
daemon_credential_id = SiMoNo-M
```

**Vérifier :**
```bash
# Test RPC avec auth
curl --digest -u username:password http://IP:18089/get_info
```

**Pourquoi port 18089 ?**
- **18081** : RPC complet (lecture + écriture)
- **18089** : RPC restreint (lecture seule, plus sécurisé)
- Pour ce script (lecture balance + transactions), **18089 est recommandé**

### Wallets

**Prérequis :**
- Wallets déjà créés/restaurés dans Monero GUI
- Chemins corrects dans config.ini
- Wallets synchronisés avec la blockchain

**Vérification manuelle :**
```bash
cd ~/Applications/monero-gui-v0.18.4.0/extras/

# Nœud local
./monero-wallet-cli --wallet-file ~/Monero/wallets/cake/cake \
                     --password <password> \
                     --daemon-address localhost:18081 \
                     --trusted-daemon \
                     --command balance

# Nœud distant
./monero-wallet-cli --wallet-file ~/Monero/wallets/cake/cake \
                     --password <password> \
                     --daemon-address monero-node.example.lan:18089 \
                     --daemon-login username:password \
                     --trusted-daemon \
                     --command balance
```

### monero-wallet-cli

**Installation :**
- Inclus dans Monero GUI (extras/)
- Version testée : 0.18.4.0
- Compatible : toutes versions >= 0.17

## Architecture technique

### Pre-check Daemon

**Avant toute opération, le script teste la connexion au daemon via RPC HTTP.**

**Endpoint :** `http://{daemon_address}/get_info`

**Authentification :**
- **Nœud local :** Aucune
- **Nœud distant :** HTTP Digest Auth (username:password depuis GPG)

**Avantages :**
- Détection immédiate si daemon inaccessible
- Vérification de la hauteur de bloc (synchronisation)
- Évite de lancer wallet-cli inutilement
- Message d'erreur clair si échec

**Exemple log :**
```
Checking daemon connection: localhost:18081
✗ Connection refused: localhost:18081
✗ Daemon not accessible - aborting
```

### CLI Commands

**Commandes utilisées :**

1. **balance** - Récupérer le solde
   ```
   Balance: 10.780241990000, unlocked balance: 10.780241990000
   ```

2. **show_transfers** - Lister les transactions
   ```
   0      in 2024-12-01 10:23:45  3.500000000000 <txid> <payment_id> 0 0.000000000000 1
   1     out 2024-12-05 15:30:12  1.000000000000 <txid> <payment_id> 0.000500000000 0.000000000000 2
   ```

**Format show_transfers (colonnes) :**
- [0] Index
- [1] Type (in/out/pending/failed/pool)
- [2] Date (YYYY-MM-DD)
- [3] Heure (HH:MM:SS)
- [4] Montant (XMR, 12 décimales)
- [5] Txid
- [6] Payment ID
- [7] Fee (XMR, pour outgoing)
- [8] ??? (toujours 0)
- [9] Confirmations

### Sécurité Password

**Méthode : Fichier temporaire (--password-file)**

```python
# Créer fichier temporaire
pass_fd, pass_file = tempfile.mkstemp(mode='w', suffix='.pwd', text=True)
os.write(pass_fd, password.encode('utf-8'))
os.close(pass_fd)
os.chmod(pass_file, 0o600)  # Permissions 600

# Utiliser CLI
subprocess.run([
    './monero-wallet-cli',
    '--password-file', pass_file,
    ...
])

# Supprimer fichier
os.unlink(pass_file)
```

**Avantages :**
- Pas de password en clair dans les arguments (visible via ps)
- Permissions 600 (lisible uniquement par l'utilisateur)
- Suppression automatique après usage

## Flux de données

### Tier 1 - Fetch (cpt_fetch_XMR.py)

**Input :** Chemins wallets + passwords depuis credentials.md.gpg
**Output :** CSV bruts dans dropbox/XMR/

```
dropbox/XMR/
├── xmr_cake_operations.csv  (raw)
└── xmr_balances.csv         (raw)
```

**Format raw operations :**
```csv
Date,Label,Amount,Currency,Wallet
2024-12-01 10:23:45,Incoming transfer,3.500000000000,XMR,cake
2024-12-05 15:30:12,Outgoing transfer,-1.000000000000,XMR,cake
2024-12-05 15:30:12,Transaction fee,-0.000500000000,XMR,cake
```

**Format raw balances :**
```csv
Wallet,Balance,Currency,Date
Cake Wallet XMR,10.780241990000,XMR,2025-01-12 16:30:00
```

### Tier 2 - Format (cpt_format_XMR.py)

**Monoscript :** Gère operations + balances

**Input :** CSV bruts
**Output :** CSV standardisés (9 ou 4 colonnes) vers stdout

**Format operations (9 colonnes) :**
```csv
Date;Libellé;Montant;Devise;Equiv;Réf;Catégorie;Compte;Commentaire
01/12/2024;Incoming transfer;3.500000000000;XMR;;;Change;Cake Wallet XMR;
05/12/2024;Outgoing transfer;-1.000000000000;XMR;;-;Virement;Cake Wallet XMR;
05/12/2024;Transaction fee;-0.000500000000;XMR;;;Frais bancaires;Cake Wallet XMR;
12/01/2026;Solde XMR;10.780241990000;XMR;;;#Solde;Cake Wallet XMR;
```

**Format balances (4 colonnes) :**
```csv
Date;Ligne;Montant;Compte
12/01/2026;#Solde Cake Wallet XMR;10.780241990000;Cake Wallet XMR
```

**Mappings comptes :**
```python
XMR_ACCOUNTS = {
    'xmr_cake': 'Cake Wallet XMR',
}
```

### Tier 3 - Update (cpt_update.py)

**Input :** CSV temporaires formatés
**Output :** Excel comptes.xlsm (feuille Opérations)

- Import operations avec duplicate detection
- Archive des fichiers raw avec HDS
- Génération des #Solde par wallet

## Catégorisation automatique

Patterns définis dans `inc_category_mappings.py` (section `XMR_PATTERNS`). Voir le code source pour les regex.

**Appariements automatiques :**
- Virements : ref='-' → recherche opération symétrique via MESH_TRANSFERS

## Usage

### Workflow complet

```bash
# Tout en un
./cpt.py --sites XMR

# Étapes séparées
./cpt_fetch_XMR.py          # Collecte (demande passphrase GPG)
./cpt_update.py             # Import
```

### Tests

```bash
# Test fetch seul
./cpt_fetch_XMR.py
ls -lh dropbox/XMR/         # Vérifier 2 CSV

# Test format
./cpt_format_XMR.py dropbox/XMR/xmr_cake_operations.csv
./cpt_format_XMR.py dropbox/XMR/xmr_balances.csv

# Test workflow
./cpt.py --sites XMR --fetch-only
./cpt.py --sites XMR --update-only
```

### Vérifications

```bash
# Vérifier balances
cat dropbox/XMR/xmr_balances.csv

# Vérifier une opération
cat dropbox/XMR/xmr_cake_operations.csv

# Statut système
./cpt.py --status
```

## Troubleshooting

### Erreur : "Wallet file not found"

**Cause :** Chemin incorrect dans config.ini

**Solution :**
1. Vérifier le chemin :
   ```bash
   ls -l ~/Monero/wallets/cake/cake
   ```
2. Corriger config.ini si nécessaire

### Erreur : "CLI command failed (exit 1)"

**Cause :** Password incorrect ou wallet verrouillé

**Solution :**
1. Tester password manuellement :
   ```bash
   cd ~/Applications/monero-gui-v0.18.4.0/extras/
   ./monero-wallet-cli --wallet-file ~/Monero/wallets/cake/cake \
                        --password <password> \
                        --daemon-address localhost:18081 \
                        --trusted-daemon \
                        --command balance
   ```
2. Vérifier credentials.md.gpg
3. Ouvrir wallet dans Monero GUI pour déverrouiller

### Erreur : "✗ Connection refused"

**Cause :** Daemon Monero non accessible

**Solution nœud local :**
1. Démarrer Monero GUI (lance le daemon automatiquement)
2. Ou démarrer monerod manuellement :
   ```bash
   ~/Applications/monero-gui-v0.18.4.0/extras/monerod --detach
   ```
3. Vérifier avec `monerod status`
4. Attendre synchronisation complète

**Solution nœud distant :**
1. Vérifier IP et port dans config.ini
2. Vérifier que le nœud distant est actif
3. Vérifier la connectivité réseau :
   ```bash
   ping monero-node.example.lan
   telnet monero-node.example.lan 18089
   curl http://monero-node.example.lan:18089/get_info
   ```
4. Vérifier firewall/NAT

### Erreur : "✗ Daemon authentication failed (401 Unauthorized)"

**Cause :** Identifiants RPC incorrects pour nœud distant

**Solution :**
1. Vérifier `daemon_credential_id` dans config.ini
2. Vérifier credentials.md.gpg (SiMoNo-M)
3. Vérifier config du nœud distant (monerod --rpc-login)
4. Tester avec curl :
   ```bash
   curl --digest -u username:password http://monero-node.example.lan:18089/get_info
   ```

### Erreur : "Daemon responded but unexpected JSON format"

**Cause :** Version Monero incompatible ou endpoint incorrect

**Solution :**
1. Vérifier version Monero (>= 0.17)
2. Tester endpoint manuellement :
   ```bash
   curl http://localhost:18081/get_info | jq
   ```
3. Activer DEBUG=true pour voir structure JSON

### Erreur : "CLI command timed out"

**Cause :** Wallet en cours de synchronisation ou noeud lent

**Solution :**
1. Attendre fin de synchronisation
2. Augmenter `wallet_timeout` dans config.ini (défaut: 300s)

### Daemon zombie (données périmées sans erreur)

**Symptôme :** Le fetch retourne `✓` mais les opérations récentes sont absentes. Le daemon répond à `get_info` mais ne sert pas le wallet sync.

**Cause :** Le daemon distant est dans un état instable (processus vivant, RPC intermittent). `monero-wallet-cli` retourne exit code 0 avec les données **cachées** du dernier refresh réussi.

**Détection :** Le script vérifie stderr de `monero-wallet-cli` pour les messages `failed to connect` / `no connection to daemon`, même quand exit code = 0.

**Solution :**
1. Utiliser un noeud local (détection d'erreur fiable)
2. Vérifier le daemon : `systemctl status monerod`
3. Si distant : `curl --digest -u user:pass http://IP:PORT/get_info`

### Wallet désynchronisé (opérations manquantes)

**Symptôme :** Le daemon est synchronisé mais le wallet ne voit pas les transactions récentes.

**Cause :** Le wallet n'a pas scanné les blocs récents (changement de daemon, daemon HS prolongé).

**Solution :** Rescan complet du wallet :
```bash
monero-wallet-cli --wallet-file ~/Monero/wallets/cake/cake \
                   --daemon-address localhost:18081 \
                   --trusted-daemon \
                   --command rescan_bc
```
**Note :** Le rescan est lent via un daemon distant ou sur partition NTFS. Avec un daemon local sur ext4, c'est beaucoup plus rapide.

### Balance = 0 mais opérations présentes

**Normal :** Le wallet a été vidé (outgoing transfer)

### Pas d'opérations récentes

**Normal :** Filtrage `max_days_back` exclut les anciennes transactions

### Transactions "pending" ignorées

**Normal :** Seules les transactions confirmées sont collectées

## Limites et notes

- **Nœud local vs distant :** Configurable dans config.ini, basculement sans modification de code
- **Ports Monero :** 18080 (P2P), 18081 (RPC complet), 18089 (RPC restreint, recommandé pour distant)
- **Unité XMR :** 12 décimales (pas en atomic units)
- **Confidentialité :** Adresses non visibles sur la blockchain (scan local requis)
- **Synchronisation :** Nœud + wallets doivent être synchronisés (peut prendre du temps)
- **Filtrage temporel :** `max_days_back = 90` (configurable)
- **Duplicate detection :** Date + Compte + Montant + Libellé
- **Password :** Fichier temporaire 600 (plus sécurisé que --password en clair dans ps)
