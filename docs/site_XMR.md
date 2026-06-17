# Site XMR - Monero Wallets

## Vue d'ensemble

Collecte automatique des soldes et transactions de wallets Monero via un
**`monero-wallet-rpc` distant**, lu en **client JSON-RPC sur tunnel SSH**. Aucune
dépendance Monero locale sur le poste de collecte (ni `monerod`, ni
`monero-wallet-cli`, ni fichiers wallet) → fonctionne identiquement sur Mac / Linux / WSL.

**Type :** Mode automatique (fetch complet)
**Source :** `monero-wallet-rpc` distant (service systemd), via tunnel SSH + JSON-RPC
**Wallets :** N wallets (1 compte par wallet), déclarés dans `config_accounts.json`
**Unité :** XMR (Monero, 12 décimales ; 1 XMR = 1e12 piconero)

> **Setup côté serveur (le nœud) + modèle de sécurité détaillé : voir `Compta_xmr.md`**
> (doc canonique). Le présent fichier décrit la **collecte côté poste**.

### Pourquoi un nœud distant

Monero sépare deux rôles : `monerod` (la blockchain, sert les blocs, ne connaît aucune
clé) et le **wallet** (`monero-wallet-rpc`, détient les clés, **télécharge et scanne**
les blocs lui-même). Le scan est ce qui coûte. Faire tourner le wallet sur le poste de
collecte (surtout un portable) est fragile : le retard s'accumule, les resyncs sont
longues. La solution retenue : `monero-wallet-rpc` tourne **en service sur la machine
qui héberge déjà monerod** (toujours allumée) ; le scan y est local au nœud (rapide) et
continu. Le poste n'est plus qu'un **client JSON-RPC** qui ouvre un tunnel SSH et lit le
résultat déjà calculé.

## Configuration

### config.ini

```ini
[XMR]
name = Monero Wallets
dossier = XMR
# Cible SSH du serveur hébergeant wallet-rpc (clé SSH non-interactive requise) :
wallet_rpc_ssh_host = user@monero-host.example.lan
# Port du wallet-rpc côté serveur (bindé localhost là-bas) + port local du tunnel SSH
wallet_rpc_port = 18083
wallet_rpc_local_port = 28083
# Login RPC du wallet-rpc (GPG) — auth HTTP Digest
wallet_rpc_credential_id = SiWaRpc-M
# Mot de passe du wallet (GPG) — envoyé à open_wallet via le tunnel chiffré
credential_id = CrMo-M
# Fenêtre d'historique des opérations + délais (secondes)
max_days_back = 90
refresh_timeout = 300
tunnel_timeout = 15
```

| Clé | Rôle |
|---|---|
| `wallet_rpc_ssh_host` | cible SSH du serveur (`user@hote`), LAN ou public — le « choix d'accès » |
| `wallet_rpc_port` | port du wallet-rpc côté serveur (bindé localhost), défaut 18083 |
| `wallet_rpc_local_port` | port local du tunnel SSH, défaut 28083 |
| `wallet_rpc_credential_id` | ID GPG du **login RPC** (HTTP Digest) |
| `credential_id` | ID GPG du **mot de passe wallet** |
| `max_days_back` | fenêtre d'historique des opérations collectées (jours) |
| `refresh_timeout` / `tunnel_timeout` | délais (s) — voir dépannage « refresh long » |

### config_accounts.json

Les wallets (clé, nom de fichier côté serveur, libellé) sont déclarés dans la section
`XMR` de `config_accounts.json` :

```json
{
  "XMR": {
    "accounts": [
      { "wallet_key": "<clé>", "wallet_name": "<nom du fichier wallet côté serveur>", "name": "<libellé du compte>" }
    ]
  }
}
```

- `wallet_key` : identifiant court (sert au nom des fichiers raw : `xmr_<wallet_key>_operations.csv`).
- `wallet_name` : nom du fichier wallet **côté serveur**, sous `~/Monero/wallets/` (à plat — voir dépannage).
- `name` : libellé du compte dans le classeur (feuille Opérations).

### config_credentials.md.gpg

Deux entrées :

```markdown
| ID | Login | Password |
|----|-------|----------|
| SiWaRpc-M | <username RPC> | <password RPC>      |
| CrMo-M    |                | <mot de passe wallet> |
```

1. **`SiWaRpc-M`** (login RPC du wallet-rpc, HTTP Digest) — Login = username, Password =
   password. Reporté depuis la sortie de `install_xmr_wallet_rpc.sh` lors du
   provisionnement serveur.
2. **`CrMo-M`** (mot de passe du wallet) — Login vide, Password = mot de passe du wallet.
   Envoyé à `open_wallet` via le tunnel chiffré ; les `.keys` restent chiffrées au repos
   côté serveur.

## Prérequis

### Côté serveur

`monerod` synchronisé + service `monero-wallet-rpc` actif (bindé `127.0.0.1`), provisionné
par **`install_xmr_wallet_rpc.sh`**. Wallets déposés **à plat** dans `~/Monero/wallets/`.
Procédure complète (install monerod, sécurité, install_xmr_wallet_rpc.sh) : **`Compta_xmr.md`**.

### Côté poste (collecte)

- **Accès SSH non-interactif** vers `[XMR] wallet_rpc_ssh_host` (auth par clé SSH).
  Tester : `ssh <wallet_rpc_ssh_host>`.
- Bibliothèque Python `requests` (dépendance standard du projet).
- Les credentials GPG `SiWaRpc-M` + `CrMo-M` renseignés (voir ci-dessus).

Aucune installation Monero locale (le poste ne fait que parler JSON-RPC dans le tunnel).

## Architecture technique

### Flux d'une collecte (`cpt_fetch_XMR.py`)

1. Résolution config + lecture des credentials GPG.
2. **Ouverture d'un tunnel SSH** `localhost:<wallet_rpc_local_port>` →
   `<wallet_rpc_ssh_host>:<wallet_rpc_port>` (wallet-rpc bindé localhost côté serveur).
3. Pour chaque wallet déclaré : `open_wallet` (mot de passe via le tunnel) → `refresh`
   (resynchro — voir « refresh long ») → `get_balance` → `get_transfers` → `close_wallet`.
4. Écriture des CSV bruts dans `dropbox/XMR/`, fermeture du tunnel.

### Modèle de sécurité (résumé)

- wallet-rpc **bindé `127.0.0.1`** côté serveur → jamais exposé ; seul accès = tunnel SSH.
- Mot de passe wallet dans le coffre GPG du poste, transmis **via le tunnel chiffré** ;
  `.keys` chiffrées au repos sur le serveur → un serveur compromis seul ne suffit pas.
- Login RPC dédié (HTTP Digest) en plus du bind localhost + SSH.

Détail complet : `Compta_xmr.md` § « Modèle de sécurité ».

## Flux de données

### Tier 1 - Fetch (`cpt_fetch_XMR.py`)

**Input :** config `[XMR]` + credentials GPG.
**Output :** CSV bruts dans `dropbox/XMR/` (un fichier operations par wallet + un fichier
balances global).

```
dropbox/XMR/
├── xmr_<wallet_key>_operations.csv  (raw, 1 par wallet)
└── xmr_balances.csv                 (raw, global)
```

**Format raw operations :**
```csv
Date,Label,Amount,Currency,Wallet
2024-12-01 10:23:45,Incoming transfer,3.500000000000,XMR,<wallet_key>
2024-12-05 15:30:12,Outgoing transfer,-1.000000000000,XMR,<wallet_key>
2024-12-05 15:30:12,Transaction fee,-0.000500000000,XMR,<wallet_key>
```

**Format raw balances :**
```csv
Wallet,Balance,Currency,Date
<libellé compte>,10.780241990000,XMR,2025-01-12 16:30:00
```

### Tier 2 - Format (`cpt_format_XMR.py`)

**Monoscript** (operations + balances). Le compte est détecté depuis le nom de fichier
(`xmr_<wallet_key>_operations.csv` → libellé via `XMR_ACCOUNTS`, **chargé depuis
`config_accounts.json`**).

**Input :** CSV bruts.
**Output :** CSV standardisés vers stdout (9 colonnes operations, 4 colonnes balances).

**Format operations (9 colonnes) :**
```csv
Date;Libellé;Montant;Devise;Equiv;Réf;Catégorie;Compte;Commentaire
01/12/2024;Incoming transfer;3.500000000000;XMR;;;Change;<libellé compte>;
05/12/2024;Outgoing transfer;-1.000000000000;XMR;;-;Virement;<libellé compte>;
05/12/2024;Transaction fee;-0.000500000000;XMR;;;Frais bancaires;<libellé compte>;
12/01/2026;Solde XMR;10.780241990000;XMR;;;#Solde;<libellé compte>;
```

**Format balances (4 colonnes) :**
```csv
Date;Ligne;Montant;Compte
12/01/2026;#Solde <libellé compte>;10.780241990000;<libellé compte>
```

### Tier 3 - Update (`cpt_update.py`)

**Input :** CSV temporaires formatés.
**Output :** classeur `comptes.xlsm` (feuille Opérations).

- Import operations avec détection de doublons (Date + Compte + Montant + Libellé).
- Archive des fichiers raw avec HDS.
- Génération des `#Solde` par wallet.

## Catégorisation automatique

Patterns définis dans `inc_category_mappings.py` (section `XMR_PATTERNS`). Voir le code
source pour les regex.

**Appariements automatiques :**
- Virements : `ref='-'` → recherche d'opération symétrique via `MESH_TRANSFERS`.

## Usage

### Workflow complet

```bash
# Tout en un
./cpt.py --sites XMR

# Étapes séparées
./cpt_fetch_XMR.py          # Collecte (tunnel SSH + JSON-RPC ; demande passphrase GPG)
./cpt_update.py             # Import
```

### Tests

```bash
# Test fetch seul
./cpt_fetch_XMR.py
ls -lh dropbox/XMR/         # Vérifier les CSV (operations par wallet + balances)

# Test format
./cpt_format_XMR.py dropbox/XMR/xmr_<wallet_key>_operations.csv
./cpt_format_XMR.py dropbox/XMR/xmr_balances.csv

# Test workflow
./cpt.py --sites XMR --fetch-only
./cpt.py --sites XMR --update-only
```

## Troubleshooting

### Erreur : souci SSH (tunnel impossible)

**Cause :** accès SSH non-interactif vers `wallet_rpc_ssh_host` indisponible.

**Solution :**
1. Tester `ssh <wallet_rpc_ssh_host>` (doit ouvrir sans demander de mot de passe).
2. Basculer entre nom **LAN** et nom **public** du serveur selon l'emplacement du poste
   (le `wallet_rpc_ssh_host` est le « choix d'accès »).
3. Vérifier la clé SSH (agent, `~/.ssh/config`).

### Erreur : `Invalid filename` à l'ouverture du wallet

**Cause :** le wallet n'est pas **à plat** dans `~/Monero/wallets/` côté serveur.
MoneroGUI range chaque wallet dans un sous-dossier homonyme (`wallets/<nom>/<nom>`), or
wallet-rpc **refuse tout `/` dans un nom de wallet** (anti-traversée).

**Solution :** aplatir côté serveur (sortir `<nom>` et `<nom>.keys` du sous-dossier pour
qu'ils soient directement sous `--wallet-dir`). Cf. `Compta_xmr.md`.

### Erreur : `file not found "<dir>/<nom>.keys"`

**Cause :** le `.keys` n'est pas au bon endroit / mauvais `wallet_name`.

**Solution :** vérifier `wallet_name` dans `config_accounts.json` vs le fichier réel côté
serveur (à plat sous `~/Monero/wallets/`).

### Le `refresh` est long ou timeoute

**Cause :** rattrapage **ponctuel** du delta de blocs (scan local au nœud), typiquement à
la 1ʳᵉ synchro ou après une longue coupure du nœud.

**Solution :** le rattrapage est **monotone** — même en timeout, wallet-rpc continue de
scanner en tâche de fond côté serveur et persiste sa progression. Il suffit de
**relancer** (chaque run repart plus haut), ou de monter `refresh_timeout` le temps de la
1ʳᵉ synchro. Ensuite les runs sont quasi instantanés.

### Authentification RPC refusée (401)

**Cause :** identifiants RPC incorrects (login `SiWaRpc-M`).

**Solution :** vérifier `wallet_rpc_credential_id` (config.ini) + l'entrée `SiWaRpc-M`
dans `config_credentials.md.gpg` vs le `rpc-login` posé par `install_xmr_wallet_rpc.sh`.

### `0 operations` mais solde non nul

**Normal :** aucun mouvement dans la fenêtre `max_days_back` jours. Élargir `max_days_back`
ponctuellement pour vérifier l'historique.

### Balance = 0 mais opérations présentes

**Normal :** le wallet a été vidé (outgoing transfer).

### Transactions "pending" ignorées

**Normal :** seules les transactions confirmées sont collectées.

## Limites et notes

- **Aucune dépendance Monero locale** sur le poste (Mac / Linux / WSL identiques).
- **Accès SSH non-interactif obligatoire** vers le serveur wallet-rpc.
- **Unité XMR :** 12 décimales (pas en atomic units côté CSV ; conversion depuis le
  piconero faite par le fetcher).
- **Confidentialité :** adresses non visibles sur la blockchain (scan côté wallet requis).
- **Filtrage temporel :** `max_days_back` (configurable).
- **Duplicate detection :** Date + Compte + Montant + Libellé.
</content>
</invoke>
