# DEGIRO — collecte

> **Source de vérité = le code.** Voir `cpt_fetch_DEGIRO.py` (login/2FA, exports) et `cpt_format_DEGIRO.py` (parsing, catégorisation, soldes). La constante `DESCRIPTION` de `cpt_fetch_DEGIRO.py` alimente la GUI (onglet Sites) — procédure et repli manuel à jour y sont décrits.

**En bref :** courtier en ligne (compte-titre). Login auto (GPG) + 2FA push sur l'appli mobile DEGIRO à chaque connexion, puis export de 2 CSV (`Portfolio.csv` positions/cash, `Account.csv` opérations).

**À savoir :**
- Les soldes ne viennent d'aucune page HTML : ils sont **dérivés des CSV** par `cpt_format_DEGIRO.py` — Réserve = ligne `CASH` de `Portfolio.csv`, Titres = somme des positions.
- Le `#Solde Réserve` est émis **en opération** (`#Solde`), pas en position, pour éviter un doublon à la conversion par `cpt_update.py`.
- Achat/Vente en devise : les lignes USD (achat/vente) et la ligne EUR « Opération de change » sont **consolidées en une seule opération EUR**.
- Si l'auto-login GPG échoue, repli sur **login manuel** en fenêtre visible (alerte terminal), puis reprise sur l'attente 2FA.
- DEGIRO modifie parfois la structure des CSV (cf. décembre 2025) : ajuster le parsing dans le code si un format casse.
