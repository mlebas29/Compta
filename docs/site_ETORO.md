# eToro — collecte

> Source de vérité = le code. Voir `cpt_fetch_ETORO.py` (collecte Playwright) et `cpt_format_ETORO.py` (mise au format). La constante `DESCRIPTION` de `cpt_fetch_ETORO.py` alimente l'onglet Sites de la GUI (config, 2FA, secours manuel). Ce fichier ne redonne pas les détails volatils (URLs, sélecteurs, colonnes, patterns) : ils dérivent trop vite du code.

**En bref** — Courtier / crypto, login semi-auto (Playwright + 2FA email/SMS). Trois comptes : Money (EUR), Réserve (USD, dérivée), Titres (USD). Quatre artefacts collectés : opérations Money (TSV), opérations Réserve (XLSX), PDF accueil (soldes) et PDF portfolio (positions).

**À savoir**

- **Modale « Nous préparons votre relevé » (export Réserve) : NE PAS la fermer.** La génération du XLSX est asynchrone ; cliquer « J'ai compris » avant que le fichier soit prêt annule la génération (timeout à vide). Le fetch la laisse et attend l'événement de téléchargement.
- **Positions Titres extraites automatiquement** du PDF portfolio (`pdfplumber`) — ticker, nom, valeur + total. Secours : fournir `positions_titres_parsed.csv` à la main si le PDF manque ou est illisible.
- **Colonne Equiv laissée vide au format** ; l'appariement cross-devise EUR↔USD et l'équivalent EUR sont établis en aval par `cpt_pair`.
- **Catégorisation centralisée** dans `inc_categorize` (patterns `ETORO` de `config_category_mappings.json`), plus dans le format. Clés atelier préfixées `@` (ex. `@Change`, `@Achat titres`).
