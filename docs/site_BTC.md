# Bitcoin (BTC) — collecte

> Source de vérité = code : `cpt_fetch_BTC.py` + `cpt_format_BTC.py` ; `DESCRIPTION` (dans le fetch) = texte affiché par la GUI (onglet Sites).

**En bref :** collecte automatique des soldes et transactions de wallets Bitcoin via l'API publique mempool.space (sans authentification). Les wallets sont désignés par leurs adresses (ou xpub) publiques, visibles sur la blockchain.

## À savoir

- **Adresses dans `config_accounts.json`, pas `config.ini`** — section `BTC`, un compte par wallet (`name`, `wallet_key`, `addresses`). `config.ini [BTC]` ne porte que les paramètres scalaires du site (URL API, fenêtre `max_days_back`). Ajouter/retirer un wallet = éditer le JSON, zéro code à toucher.
- **Multi-adresses par wallet** — le champ `addresses` est une liste : un wallet peut lister plusieurs adresses (ex. wallet HD), le fetch les parcourt et **somme les soldes** en un solde unique par compte.
- **xpub/ypub/zpub = mode solde-seul** — une entrée `addresses` commençant par `xpub`/`ypub`/`zpub` (ou testnet `tpub`/`upub`/`vpub`) n'est pas parsée transaction par transaction (trop complexe) : seul le solde global est récupéré.
- **Unité SAT** — satoshis (1 BTC = 100 000 000 SAT), pas de décimales.
