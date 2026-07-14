# Monero (XMR) — collecte

> Source de vérité = le code : `cpt_fetch_XMR.py` (collecte) + `cpt_format_XMR.py` (format) ; `DESCRIPTION` (dans le fetch) = texte affiché par la GUI (onglet Sites). **Setup côté serveur (le nœud wallet-rpc) + modèle de sécurité + dépannage = `Compta_xmr.md`.**

**En bref :** soldes et transactions de wallets Monero lus via un **nœud distant** — ce poste n'est qu'un **client JSON-RPC sur tunnel SSH** vers un `monero-wallet-rpc` distant ; **aucune dépendance Monero locale** (ni monerod, ni wallet-cli, ni fichiers wallet), donc Mac / Linux / WSL identiques.

## À savoir (non évident)

- **Nœud distant, scan délégué.** Le `monero-wallet-rpc` tourne en service sur une machine toujours allumée (collée à monerod) : le scan de blocs, coûteux, y reste local et continu. Le poste ne fait qu'ouvrir un tunnel SSH (wallet-rpc bindé `127.0.0.1` côté serveur → jamais exposé) et lire le résultat déjà calculé. Setup et sécurité : `Compta_xmr.md`.
- **Wallets déclarés dans `config_accounts.json`, pas `config.ini`** — section `XMR`, un compte par wallet (`wallet_key`, `wallet_name` = fichier côté serveur, `name`). `config.ini [XMR]` ne porte que les scalaires du site (cible SSH, ports, IDs credentials GPG, `max_days_back`, timeouts). Ajouter/retirer un wallet = éditer le JSON.
- **Wallets à plat côté serveur** — `wallet-rpc` refuse tout `/` dans un nom de wallet (anti-traversée), donc chaque fichier wallet (`<nom>` + `<nom>.keys`) doit être directement sous `--wallet-dir`, pas dans un sous-dossier homonyme comme le range MoneroGUI. Cf. `Compta_xmr.md`.
- **Unité XMR** — 12 décimales (1 XMR = 1e12 piconero) ; la conversion depuis le piconero est faite par le fetcher.
