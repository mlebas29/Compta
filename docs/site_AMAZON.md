# Amazon (cartes cadeau) — collecte

> Source de vérité = le code : `cpt_fetch_AMAZON.py` (collecte) + `cpt_format_AMAZON.py` (format). Procédure utilisateur = `DESCRIPTION`, GUI onglet Sites.

**En bref** — solde et historique de la carte cadeau Amazon (compte unique), collectés par login semi-automatique Playwright (identifiants GPG, 2FA gérée manuellement si Amazon la déclenche).

## À savoir (non évident)

- **Ré-authentification sur la page sensible** : même déjà connecté, l'accès à la page solde/carte cadeau peut renvoyer sur `/ap/signin` → le fetch relance le login sans re-naviguer, puis retourne sur la page.
- **Page « Protégez-vous » (`/ap/accountfixup`)** : Amazon pousse l'ajout d'un téléphone ; le fetch clique « Pas maintenant » automatiquement pour ne pas rester bloqué.
- **Solde synthétique en fin de CSV** : le fetch ajoute une ligne `#SOLDE` que le format convertit en opération `#Solde` (relevé) ; le solde est extrait par heuristique texte (« Solde » + « € »), donc absent si la page change.
- **Dates en français** : le format accepte « 2 juillet AAAA » / « 11 nov AAAA » (mois abrégés inclus) en plus de `JJ/MM/AAAA`.
