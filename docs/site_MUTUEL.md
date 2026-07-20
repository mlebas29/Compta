# Crédit Mutuel — collecte

> Source de vérité = le code : `cpt_fetch_MUTUEL.py` (collecte) et
> `cpt_format_MUTUEL.py` (parsing). Descriptif opérateur (GUI onglet Sites) =
> constante `DESCRIPTION` du fetch. Ci-dessous, seulement le « pourquoi » non déductible du code.

**En bref.** Banque (comptes courants, livrets, prêts). Login semi-automatique (identifiants GPG) + **2FA systématique** validé sur l'app mobile (côté téléphone → collecte **headless** ; coordination humaine). Un **seul** export Excel multi-comptes, reformaté au schéma standard 9 champs.

## À savoir

- **Un seul fichier pour tout** : `tous_comptes.xlsx` = feuille de synthèse « Vos comptes » (registre : RIB + nom + solde de **tous** les comptes, prêts inclus) + une feuille `Cpt …` par compte mouvementé. Les lignes `#Solde` viennent de la synthèse → couvrent même les prêts, qui n'ont pas de feuille d'opérations.
- **Jointure par RIB, pas par nom** : la clé est le **dernier bloc du RIB** (numéro de compte), présent à la fois dans la synthèse et dans le nom d'onglet. Indispensable car des homonymes (plusieurs prêts de même intitulé) rendent le « par nom » ambigu. Chaque compte déclare son RIB (`config_accounts.json[MUTUEL]`, champ saisi à la création dans l'onglet Comptes).
- **Session détectée par ABSENCE du marqueur 2FA** : le lien « Déconnexion » est présent **aussi** sur la page d'authentification forte → s'y fier seul donnerait un faux positif. On ne considère connecté que lorsque le bouton de validation forte (`DoValidate`) et le titre « authentification forte » ont disparu.
- **Présélection mémorisée côté CM** : format Excel + tous les comptes + tout l'historique sont retenus par la banque → la collecte n'a qu'à actionner « Téléchargez ». Garde HTML : une session expirée en cours de flux renvoie une page au lieu de l'export → le fichier est refusé (sinon échec cryptique au format).
- **Login direct** : la page `authentification.html` est visée directement pour éviter la popin de géolocalisation régionale de l'accueil.

Contrat de formatage Tier 2 : voir [`Compta_site.md`](../Compta_site.md). Renommage en collecte manuelle : voir `Compta_plus.md`.
