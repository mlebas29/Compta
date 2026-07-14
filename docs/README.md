# docs/ — Internals développeur par connecteur

Documentation **dev approfondie**, complémentaire des docs de haut niveau :

- Pour **ajouter un site** (squelettes fetch/format, contrat Tier 2, formats 9/4 champs) → [`Compta_site.md`](../Compta_site.md)
- Pour l'**architecture générale** (3 tiers, data flow, GUI) → [`Compta_dev.md`](../Compta_dev.md)
- Ici (`docs/`) → un **stub par connecteur** : les gotchas non-évidents + pointeur vers le code (`cpt_fetch_*` / `cpt_format_*`, **source de vérité**). Le détail volatil (fichiers, colonnes, sélecteurs, flux) vit dans le code, pas ici — il dériverait trop vite. Plus quelques sujets transverses.

## Connecteurs (un stub par site)

| Site | Doc | Gotchas |
|---|---|---|
| Société Générale | [`site_SOCGEN.md`](site_SOCGEN.md) | banque, OCR clavier virtuel, agrégat ETF (patch privé) |
| BoursoBank | [`site_BOURSOBANK.md`](site_BOURSOBANK.md) | OCR hybride, plafond 2 tentatives / 15 min |
| NATIXIS (PEE) | [`site_NATIXIS.md`](site_NATIXIS.md) | épargne salariale, sortie PDF, assistant « appareil de confiance » |
| DEGIRO | [`site_DEGIRO.md`](site_DEGIRO.md) | courtier titres, 2FA push mobile |
| eToro | [`site_ETORO.md`](site_ETORO.md) | courtier/crypto, modale relevé à ne pas fermer, positions auto-PDF |
| Kraken | [`site_KRAKEN.md`](site_KRAKEN.md) | exchange crypto, CAPTCHA Turnstile |
| Wise | [`site_WISE.md`](site_WISE.md) | multidevises, export CSV all-transactions |
| PayPal | [`site_PAYPAL.md`](site_PAYPAL.md) | CAPTCHA + code SMS |
| Amazon | [`site_AMAZON.md`](site_AMAZON.md) | solde carte cadeau |
| Bitcoin | [`site_BTC.md`](site_BTC.md) | wallets (adresses / xpub publics), API mempool.space |
| Monero | [`site_XMR.md`](site_XMR.md) | nœud distant, client JSON-RPC via tunnel SSH |
| Saisie manuelle | [`site_MANUEL.md`](site_MANUEL.md) | pas de collecte ; format `manuel.xlsx` (contrat utilisateur) |

## Sujets transverses

| Sujet | Doc |
|---|---|
| Interface Format ↔ Update ↔ Excel | [`architecture_import.md`](architecture_import.md) |
| Système d'appariements (réfs, Equiv, MESH_TRANSFERS) | [`appariements.md`](appariements.md) |
| Purge des opérations anciennes | [`purge.md`](purge.md) |
| Portage — détails dev (UNO, Tk/macOS, WSL2) | [`portage_internals.md`](portage_internals.md) |
