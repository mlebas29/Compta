# docs/ — Internals développeur par connecteur

Documentation **dev approfondie**, complémentaire des docs de haut niveau :

- Pour **ajouter un site** (squelettes fetch/format, contrat Tier 2, formats 9/4 champs) → [`Compta_site.md`](../Compta_site.md)
- Pour l'**architecture générale** (3 tiers, data flow, GUI) → [`Compta_dev.md`](../Compta_dev.md)
- Ici (`docs/`) → les **détails propres à chaque connecteur** (authentification, 2FA, parsing, gotchas, dépannage) et quelques sujets transverses.

## Connecteurs (un fichier par site)

| Site | Doc | Spécificités |
|---|---|---|
| Société Générale | [`site_SOCGEN.md`](site_SOCGEN.md) | chèque / épargne / assurance vie, synthèse PDF |
| BoursoBank | [`site_BOURSOBANK.md`](site_BOURSOBANK.md) | clavier virtuel OCR, comptes + titres |
| NATIXIS (PEE) | [`site_NATIXIS.md`](site_NATIXIS.md) | épargne salariale, Angular Material, PDF CDP |
| DEGIRO | [`site_DEGIRO.md`](site_DEGIRO.md) | courtier titres, 2FA mobile systématique |
| eToro | [`site_ETORO.md`](site_ETORO.md) | courtier/crypto, comptes Money + Réserve/Titres USD |
| Kraken | [`site_KRAKEN.md`](site_KRAKEN.md) | exchange crypto, ZIP ledgers/balances, Turnstile |
| Wise | [`site_WISE.md`](site_WISE.md) | multidevises, export CSV all-transactions |
| Bitcoin | [`site_BTC.md`](site_BTC.md) | wallets (adresses publiques), API mempool.space |
| Monero | [`site_XMR.md`](site_XMR.md) | wallets, monero-wallet-cli, nœud daemon |

## Sujets transverses

| Sujet | Doc |
|---|---|
| Interface Format ↔ Update ↔ Excel | [`architecture_import.md`](architecture_import.md) |
| Système d'appariements (réfs, Equiv, MESH_TRANSFERS) | [`appariements.md`](appariements.md) |
| Purge des opérations anciennes | [`purge.md`](purge.md) |
| Portage — détails dev (UNO, Tk/macOS, WSL2) | [`portage_internals.md`](portage_internals.md) |
