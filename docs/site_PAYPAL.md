# PayPal — collecte

> Source de vérité = le code : `cpt_fetch_PAYPAL.py` (collecte) + `cpt_format_PAYPAL.py` (format). Procédure utilisateur = la constante `DESCRIPTION`, onglet **Sites** de la GUI.

**En bref** — compte PayPal unique (transactions + solde). Auth = login (identifiants GPG) + CAPTCHA éventuel + code **SMS**.

## À savoir (non évident)

- **Pas de téléchargement direct** : le fetch *crée* un rapport CSV via `/reports/dlog` (type « Toutes les transactions » + période), puis **poll** son état jusqu'à ce qu'il passe de « Envoyé » à « Télécharger » avant de récupérer le fichier.
- **Étapes humaines en headed** : CAPTCHA et code SMS ne sont pas automatisés — le script bascule Chrome en fenêtre visible, attend la résolution du CAPTCHA, puis lit le code SMS tapé au clavier dans le terminal.
- **Format CSV (FR)** : montants en virgule décimale, date `DD/MM/YYYY` reprise telle quelle ; la **commission PayPal** non nulle devient une opération séparée (`Frais bancaires`), les lignes « Mémo » (sans impact solde) sont ignorées, et le dernier solde lu génère une ligne `#Solde`.
