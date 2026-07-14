# Kraken — collecte

> **Source de vérité = le code.** Détails du flux, des sélecteurs et du format dans
> `cpt_fetch_KRAKEN.py` (Tier 1, Playwright) et `cpt_format_KRAKEN.py` (Tier 2,
> parsing). La constante `DESCRIPTION` de `cpt_fetch_KRAKEN.py` (affichée dans la GUI
> onglet Sites) documente configuration, 2FA et collecte manuelle de secours.
> Ce fichier n'est qu'un pointeur : il ne duplique pas ces détails volatils.

**En bref :** exchange crypto ; fetch semi-auto (login GPG + 2FA email), export de 2 ZIP
(`ledgers` = opérations, `balances` = positions) → `dropbox/KRAKEN/` ; import via
`cpt_update.py` (générique).

## À savoir (points non évidents)

- **Cloudflare Turnstile** peut s'interposer avant le login/la page documents et bloque
  en headless → le script bascule en fenêtre visible et attend que tu coches la case.
- **Extraction des ZIP par le Tier 2** (`cpt_format_KRAKEN.py`), pas par `cpt_update.py`
  (import générique, sans logique Kraken) : CSV extraits dans un temp `.kraken_temp/`,
  jamais dans `dropbox/KRAKEN/`.
- **Anti-périmé** : un export existant n'est réutilisé que si sa fin de période est
  ≥ hier, sinon un export frais est créé (évite de reboucler sur des ledgers figés).
- **Fenêtre de collecte ~30 j** (plage Kraken par défaut ; le date picker n'est plus
  ouvert, cf. code) → lancer la collecte régulièrement.
