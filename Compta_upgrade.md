# Mise à niveau du classeur

Ce document décrit les changements de structure du classeur `comptes.xlsm` entre versions et la procédure de mise à niveau correspondante.

L'application vérifie au démarrage que le classeur est compatible. En cas d'incompatibilité, un message indique la version détectée et la version attendue.

## Version 1

Première version avec schéma versionné. Introduit :

- Named ranges colonnes (67 noms définis pour toutes les feuilles)
- Named range `SCHEMA_VERSION` → Contrôles!K2

**Depuis un classeur sans version (antérieur à v3.2) :**

Le classeur ne contient pas les named ranges colonnes nécessaires à l'application.

*Procédure :*
```bash
# Sauvegarder le classeur actuel
cp comptes.xlsm comptes_backup.xlsm

# Recréer depuis le template à jour
cp comptes_template.xlsm comptes.xlsm
```

Le nouveau classeur est vierge. Réimporter vos données via l'application (collecte + import) ou par copier-coller depuis le backup.

## Versions futures

Chaque section indiquera :
- Ce qui a changé dans la structure
- La procédure : recréation depuis le template, outil de migration (`tool_migrate.py`), ou mise à jour manuelle
