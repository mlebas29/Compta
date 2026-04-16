# Mise à niveau du classeur

Ce document décrit les changements de structure du classeur `comptes.xlsm` entre versions et la procédure de mise à niveau correspondante.

L'application vérifie au démarrage que le classeur est compatible. En cas d'incompatibilité, un message indique la version détectée et la version attendue.

## Version 1

Première version avec schéma versionné. Introduit :

- Named ranges colonnes (67 noms définis pour toutes les feuilles)
- Named range `SCHEMA_VERSION` = 1

**Depuis un classeur sans version (antérieur à v3.2) :**

Le classeur ne contient pas les named ranges colonnes nécessaires à l'application.

*Procédure :*
```bash
# Sauvegarder le classeur actuel
cp comptes.xlsm comptes_backup.xlsm

# Recréer depuis le template à jour
cp comptes_template.xlsm comptes.xlsm
```

Relancer l'application après la copie. Le nouveau classeur est vierge. Réimporter vos données via l'application (collecte + import) ou par copier-coller depuis le backup.

## v3.5.3 — formules PVL multi-devise génériques (optionnel)

Pas de changement de schéma (`SCHEMA_VERSION` reste à 1). Réécriture des formules du pied `TOTAL portefeuilles` et du `Total` des blocs portefeuille multi-devise vers `SUMPRODUCT` générique (lookup `COTcode`/`COTcours`), pour :

- Corriger le **double comptage de cours** qui apparaît si un portefeuille non-EUR pivot contient un titre dans une autre devise (ex. portefeuille USD avec un titre EUR).
- Supprimer la liste explicite des devises dans les formules : plus besoin de regénérer à chaque ajout de devise.

Pas d'effet sur les valeurs si la configuration actuelle n'exposait pas le bug (portefeuilles non-EUR pivot mono-devise, ou portefeuilles EUR-pivot multi-devise).

*Procédure (LibreOffice fermé) :*
```bash
python3 tool_migrate_pvl_totals.py ~/Compta/comptes.xlsm --dry-run   # vérification
python3 tool_migrate_pvl_totals.py ~/Compta/comptes.xlsm             # migration
```

Le tool affiche les valeurs `GRAND TOTAL` / `TOTAL portefeuilles` / blocs multi-devise avant et après. Migration transparente = aucune ligne `Δ` dans la sortie.

## Versions futures

Chaque section indiquera :
- Ce qui a changé dans la structure
- La procédure : recréation depuis le template, outil de migration (`tool_migrate_*.py`), ou mise à jour manuelle
