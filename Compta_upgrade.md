# Mise à niveau du classeur

Ce document décrit les mises à niveau à appliquer au classeur `comptes.xlsm` entre versions d'app. Selon le cas, la mise à niveau porte sur la structure, sur des formules, ou sur des formats.

Au démarrage (mode assisté), l'application vérifie que la version de structure `SCHEMA_VERSION` du classeur est compatible ; une incompatibilité de structure est bloquante et signalée par un message. Les autres mises à niveau (formules, formats) sont optionnelles ou recommandées selon le cas — elles n'empêchent pas l'exécution mais peuvent masquer des erreurs ou fausser des calculs.

**Rappel** — [modes d'utilisation](README.md#1-points-de-départ) :

- **Mode classeur** : seul `comptes.xlsx` est téléchargé ; la mise à niveau se fait manuellement dans le classeur, en s'appuyant sur [`comptes_exemple.xlsx`](https://github.com/mlebas29/Compta/raw/main/comptes_exemple.xlsx) comme référence.
- **Mode assisté** : l'ensemble classeur vierge + app + outils est installé ; Récupérer d'abord la mise à jour avec `git pull`.

## v3.5.3 — formules PVL multi-devise génériques (optionnel)

Pas de changement de schéma (`SCHEMA_VERSION` reste à 1). Feuille Plus_value : réécriture des formules du pied `TOTAL portefeuilles` et du `Total` des blocs portefeuille multi-devise vers `SUMPRODUCT` générique (lookup `COTcode`/`COTcours`), pour :

- Corriger le **double comptage de cours** qui apparaît si un portefeuille non-EUR pivot contient un titre dans une autre devise (ex. portefeuille USD avec un titre EUR).
- Supprimer la liste explicite des devises dans les formules : plus besoin de regénérer à chaque ajout de devise.

Pas d'effet sur les valeurs si la configuration actuelle n'exposait pas le bug (portefeuilles non-EUR pivot mono-devise, ou portefeuilles EUR-pivot multi-devise).

| Mode classeur            | Mode assisté                   |
| ------------------------ | ------------------------------ |
| mise à jour manuelle (1) | tool_migrate_pvl_totals.py (2) |

 (1) Télécharger [`comptes_exemple.xlsx`](https://github.com/mlebas29/Compta/raw/main/comptes_exemple.xlsx) pour trouver le modèle des formules du classeur.

 (2) *Procédure (LibreOffice fermé) :*

```bash
python3 tool_migrate_pvl_totals.py ~/Compta/comptes.xlsm --dry-run   # vérification
python3 tool_migrate_pvl_totals.py ~/Compta/comptes.xlsm             # migration
```

L'outil affiche les valeurs `GRAND TOTAL` / `TOTAL portefeuilles` / blocs multi-devise avant et après. Migration transparente = aucune ligne `Δ` dans la sortie.

## v3.5.2 — détection d'erreur Comptes multi-devises (recommandé)

Pas de changement de schéma (`SCHEMA_VERSION` reste à 1). Feuille Contrôles, tableau CTRL2 : les colonnes `Affichage` (✓/✗) et `Général` (somme) ne totalisaient que la colonne EUR sur les lignes `COMPTES`, `CATÉGORIES`, `€ Virements` et `€ Titres`. Un écart sur un compte en devise non-EUR n'était donc pas remonté. Le fix applicatif corrige la génération des formules à l'ajout d'une devise ; cette migration met à niveau les classeurs dont les formules ont été figées avec l'ancienne logique.

Affecte les utilisateurs ayant au moins un compte dans une devise autre que l'EUR.

| Mode classeur            | Mode assisté                       |
| ------------------------ | ---------------------------------- |
| mise à jour manuelle (1) | tool_migrate_ctrl2_formulas.py (2) |

 (1) Télécharger [`comptes_exemple.xlsx`](https://github.com/mlebas29/Compta/raw/main/comptes_exemple.xlsx) pour trouver le modèle des formules `Affichage` / `Général` du tableau CTRL2.

 (2) *Procédure (LibreOffice fermé) :*

```bash
python3 tool_migrate_ctrl2_formulas.py ~/Compta/comptes.xlsm --dry-run   # vérification
python3 tool_migrate_ctrl2_formulas.py ~/Compta/comptes.xlsm             # migration
```

L'outil affiche les formules `Affichage` et `Général` avant et après sur les 4 lignes concernées et détaille les écarts de valeur éventuels.

## v3.2 - SCHEMA_VERSION 1

Première version avec schéma versionné. Introduit :

- Named ranges colonnes (67 noms définis pour toutes les feuilles)
- Named range `SCHEMA_VERSION` = 1

**Depuis un classeur sans version (antérieur à app v3.2) :**

Le classeur ne contient pas les named ranges colonnes nécessaires à l'application.

*Procédure :*
```bash
# Sauvegarder le classeur actuel
cp comptes.xlsm comptes_backup.xlsm

# Recréer depuis le template à jour
cp comptes_template.xlsm comptes.xlsm
```

Relancer l'application après la copie. Le nouveau classeur est vierge. Réimporter vos données via l'application (collecte + import) ou par copier-coller depuis le backup.
