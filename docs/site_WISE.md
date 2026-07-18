# Wise — collecte

> **Source de vérité = le code.** Voir `cpt_fetch_WISE.py` (login/2FA, export CSV, soldes) et `cpt_format_WISE.py` (décomposition en jambes par devise, #Solde). La constante `DESCRIPTION` de `cpt_fetch_WISE.py` alimente la GUI (onglet Sites) — procédure et repli manuel à jour y sont décrits.

**En bref :** compte de paiement multi-devises (un compte par devise, pas de conversion EUR). Login semi-auto (Playwright + GPG) avec 2FA mobile systématique (push à approuver), occasionnellement complété d'un 2ᵉ facteur email. Collecte = export CSV « all-transactions » (1 clic) + lecture des soldes courants.

**À savoir :**
- **Source normale = CSV « all-transactions » (depuis #131)** ; l'ancien assistant relevé XLSX (ZIP) n'est plus qu'un **repli legacy** déposé à la main, ignoré si un CSV est présent (source unique, anti-doublon). Le chemin XLSX sert surtout au TNR pipe.
- Le `#Solde` de chaque compte vient de `wise_balances.csv` (fetch). Le **jar EUR se lit sur la page du groupe multi-devises**, pas sur `/home` (qui y affiche l'EUR comme devise de base, d'un montant sans rapport avec le vrai jar).
- **Intérêts Wise Assets suivis (v5.21.0)** : le rendement d'un solde rémunéré est **invisible aux transactions** (crédité au solde) → collecté à part (`wise_interest.csv`, « Rendements depuis le début ») et booké à l'import par un **delta C-déduit** ; `Σ(ops « Intérêts » du compte)` doit égaler le cumul scrapé, sinon `#Solde` retenu → « ⚠ Solde calculé » (virement manquant ?). Détail : docstrings `cpt_format_WISE.build_soldes_and_interest` / `cpt_fetch_WISE.fetch_interest`.
- Le format décompose le CSV **en jambes par devise** selon le type d'opération ; les conversions internes donnent **2 jambes appariées** (`ref='-'`), frais inclus dans le débit.
- Page **SPA qui n'atteint jamais `networkidle`** → le fetch attend des sélecteurs ciblés, pas l'idle réseau ; à chaque échec, dumps DOM dans `logs/debug/`.
