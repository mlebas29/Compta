# Compta — collecte Monero (XMR) via nœud distant

Comment `cpt_fetch_XMR.py` récupère soldes et transferts des wallets Monero, sans
aucune dépendance Monero locale sur le poste de collecte.

## Pourquoi un nœud distant

Monero sépare deux rôles :

- **`monerod`** (le nœud) : détient la blockchain, parle au réseau p2p, **sert les
  blocs**. Il ne connaît aucune clé — il ignore quels outputs sont à toi.
- **le wallet** (`monero-wallet-cli` / `monero-wallet-rpc`) : détient **tes clés**,
  **télécharge les blocs depuis un monerod et les scanne** lui-même pour reconstituer
  soldes et transferts. C'est le scan qui coûte (et qui doit rattraper le delta de
  blocs depuis la dernière synchro).

Faire tourner le wallet **sur le poste de collecte** (surtout un portable) est fragile :
le scan se fait sur le réseau, le retard s'accumule, les resyncs sont longues.

**Solution** : faire tourner **`monero-wallet-rpc` en service sur la machine qui héberge
déjà monerod** (toujours allumée). Le scan y est *local au nœud* (rapide) et *continu*.
Le poste de collecte n'est plus qu'un **client JSON-RPC** : il ouvre un tunnel SSH et
lit le résultat déjà calculé. Marche identiquement sur Mac / Linux / WSL.

```
   réseau p2p Monero
          │
     ┌────▼──────┐    RPC localhost     ┌────────────────────┐
     │  monerod  │ ◀──(sert les blocs)──│  monero-wallet-rpc  │
     │ blockchain│                      │   tes clés + scan   │
     └───────────┘   ── scan ICI ──     └──────────▲──────────┘
        serveur (toujours allumé)                  │ JSON-RPC (get_balance,
                                                   │  get_transfers) via tunnel SSH
                                        ┌──────────▼──────────┐
                                        │  poste : cpt_fetch  │
                                        └─────────────────────┘
```

## Modèle de sécurité

- **wallet-rpc bindé sur `127.0.0.1`** côté serveur → **jamais exposé** au réseau. Le
  seul accès est le **tunnel SSH** (auth par clé SSH). monerod, lui, peut rester public
  (il n'a pas de clés ; le protéger par `rpc-login` suffit).
- **Mot de passe du wallet** : reste dans le coffre GPG du poste. Il est envoyé à
  `open_wallet` **via le tunnel chiffré** ; les fichiers `.keys` restent **chiffrés au
  repos** sur le serveur. Un serveur compromis seul ne suffit donc pas à dépenser.
- **Login RPC dédié** au wallet-rpc (HTTP Digest), en plus du bind localhost + SSH.

## Mise en place côté serveur

Prérequis : `monerod` en service, **synchronisé**, avec `rpc-login` (RPC complet, p.ex.
`127.0.0.1:18081`), et le binaire `monero-wallet-rpc` présent (même tarball que monerod).

1. **Déposer les wallets À PLAT** dans `~/Monero/wallets/` :
   ```
   ~/Monero/wallets/<nom>          (fichier cache)
   ~/Monero/wallets/<nom>.keys     (clés chiffrées)
   ```
   ⚠️ MoneroGUI range chaque wallet dans un **sous-dossier** homonyme
   (`wallets/<nom>/<nom>`). wallet-rpc **refuse tout `/` dans un nom de wallet**
   (`Invalid filename`, anti-traversée) → il faut **aplatir** : sortir les fichiers du
   sous-dossier pour qu'ils soient directement sous `--wallet-dir`.

2. **Lancer le provisionnement** (sur le serveur, par le propriétaire de monerod) :
   ```
   bash install_xmr_wallet_rpc.sh
   ```
   Le script : localise le binaire, lit le `rpc-login` de monerod (jamais affiché),
   génère un login RPC dédié, écrit `~/.config/monero-wallet-rpc.conf` (chmod 600),
   installe + démarre le service systemd, puis **affiche le login RPC à reporter dans
   le coffre GPG** du poste.

## Configuration côté poste

`config.ini` section `[XMR]` :

| Clé | Rôle |
|---|---|
| `wallet_rpc_ssh_host` | cible SSH du serveur (`user@hote`), LAN ou public — le « choix d'accès » |
| `wallet_rpc_port` | port du wallet-rpc côté serveur (bindé localhost), défaut 18083 |
| `wallet_rpc_local_port` | port local du tunnel SSH, défaut 28083 |
| `wallet_rpc_credential_id` | ID GPG du **login RPC** (HTTP Digest) |
| `credential_id` | ID GPG du **mot de passe wallet** |
| `max_days_back` | fenêtre d'historique des opérations collectées |
| `refresh_timeout` / `tunnel_timeout` | délais (s) |

Les wallets (clé, nom de fichier, libellé) sont déclarés dans `config_accounts.json`
(`XMR.accounts[].wallet_key` / `wallet_name` / `name`).

Deux entrées dans `config_credentials.md.gpg` :
```
| <wallet_rpc_credential_id> | <user RPC>   | <pass RPC>      |
| <credential_id>            | <login>      | <mot de passe wallet> |
```

## Dépannage

- **`Invalid filename`** à `open_wallet` → wallet pas à plat dans `--wallet-dir`
  (voir étape 1 : aplatir, retirer le sous-dossier MoneroGUI).
- **`file not found "<dir>/<nom>.keys"`** → le `.keys` n'est pas au bon endroit / nom.
- **Le `refresh` est long ou timeoute** → c'est le rattrapage *ponctuel* du delta de
  blocs (scan local au nœud). Le rattrapage est **monotone** : même en timeout, wallet-rpc
  continue de scanner en tâche de fond côté serveur et persiste sa progression → il
  suffit de **relancer** (chaque run repart plus haut), ou de monter `refresh_timeout`
  le temps de la 1ʳᵉ synchro. Ensuite les runs sont quasi instantanés.
- **Souci SSH** → tester l'accès `ssh <wallet_rpc_ssh_host>` ; basculer entre nom LAN
  et nom public selon l'emplacement du poste.
- **`0 operations` mais solde non nul** → aucun mouvement dans `max_days_back` jours
  (nominal). Élargir `max_days_back` ponctuellement pour vérifier l'historique.

## Annexe — installer monerod (le nœud)

Tout ce qui précède suppose un `monerod` déjà installé et **synchronisé** (le prérequis
du § « Mise en place côté serveur »). Rappel bref pour le poser sur le serveur :

1. **Binaires officiels** — télécharger le tarball CLI depuis
   [getmonero.org/downloads](https://www.getmonero.org/downloads/) (vérifier le hash / la
   signature), le décompresser : il contient **`monerod` ET `monero-wallet-rpc`** (même
   archive — d'où le prérequis « binaire wallet-rpc présent »). Mettre les binaires dans
   le `PATH` (p.ex. `/usr/local/bin`).

2. **Config** `~/.bitmonero/bitmonero.conf` (ou via `--config-file`) :
   ```
   data-dir=/chemin/vers/la/blockchain
   prune-blockchain=1          # ~1/3 de l'espace disque, suffisant pour un wallet
   rpc-bind-ip=127.0.0.1       # RPC complet en local — c'est là que se connecte wallet-rpc
   rpc-bind-port=18081
   rpc-login=<user>:<pass>     # = le rpc-login que lit install_xmr_wallet_rpc.sh
   ```
   monerod peut rester **public** sur son port p2p (18080) sans risque (il n'a aucune
   clé) ; on garde seulement le **RPC** en local + `rpc-login`.

3. **Service systemd** — une unit qui lance `monerod --config-file <conf> --non-interactive`,
   activée au boot (même esprit que le service wallet-rpc posé par
   `install_xmr_wallet_rpc.sh`). Démarrer, puis **attendre la synchro initiale** : longue
   (heures à jours selon réseau / disque) ; la blockchain pèse des centaines de Go, bien
   moins en mode `prune`.

4. **Vérifier** : `monerod status` (ou RPC `get_info`) → `Height` qui rattrape la cible et
   `synchronized: true`. Une fois synchronisé, enchaîner sur le § « Mise en place côté
   serveur ».

Options avancées (Tor/i2p, nœud distant tiers au lieu d'un nœud à soi, ZMQ) : doc
officielle Monero.
