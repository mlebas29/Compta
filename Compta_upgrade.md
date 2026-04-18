# Mise à niveau du classeur

Ce document décrit les mises à niveau à appliquer au classeur `comptes.xlsm` entre les versions d'app. Selon le cas, la mise à niveau porte sur la structure, sur des formules, ou sur des formats.

**Rappel** — [modes d'utilisation](README.md#1-points-de-départ)

| Mode classeur                                                | Mode assisté                                                 |
| ------------------------------------------------------------ | ------------------------------------------------------------ |
| seul `comptes.xlsm` est utilisé ; la mise à niveau se fait manuellement dans le classeur, en s'appuyant sur [`comptes_exemple.xlsx`](https://github.com/mlebas29/Compta/raw/main/comptes_exemple.xlsx) comme référence | l'ensemble classeur vierge + app + outils est installé avec `git clone` et mis à jour avec `git pull` - la mise à niveau du classeur est soit manuelle soit réalisée par l'app soit par un outil tool_migrate_*.py |

Au démarrage (mode assisté), l'application vérifie que la version de structure `SCHEMA_VERSION` du classeur est compatible ; une incompatibilité de structure est bloquante et signalée par un message. Les autres mises à niveau (formules, formats) sont optionnelles ou recommandées selon le cas — elles n'empêchent pas l'exécution mais peuvent masquer des erreurs ou fausser des calculs.



## v3.5.7 — Plus-value : ancrage dynamique via équivalent EUR sur `#Solde` (recommandé)

Pas de changement de schéma (`SCHEMA_VERSION` reste à 1). Feuilles `Plus_value` et `Avoirs` : les formules de *date* et *montant initial* (antériorité) pour les sections **métaux / crypto / devises** et les colonnes *AVRdate_anter* / *AVRmontant_anter* des comptes (hors biens matériels) sont remplacées par des formules dynamiques qui s'ancrent sur le `#Solde` **le plus récent dont l'équivalent EUR est renseigné** (et non plus un `#Solde` par défaut + montant `0` codé en dur).

**Effet utilisateur** :
- Tant qu'aucun `#Solde` n'a d'équivalent EUR renseigné, la PVL est calculée **depuis l'origine** du compte (toutes les opérations comptent). C'est utile pour voir la plus-value "depuis l'acquisition".
- En renseignant l'équivalent EUR sur un `#Solde` (au cours d'époque de ce relevé), vous fixez un **point d'ancrage** : la PVL est alors calculée depuis ce point. Utile pour *purger* les vieilles opérations et repartir d'un solde connu.
- Les **valeurs `Montant initial` saisies manuellement** (différentes de 0) dans Plus_value sont **préservées** par l'outil de migration.
- La **GUI d'ajout d'un compte** demande désormais l'équivalent EUR si la devise n'est pas EUR et le solde initial non nul (champ *Équiv. EUR*).

| Mode classeur            | Mode assisté                    |
| ------------------------ | ------------------------------- |
| mise à jour manuelle (1) | tool_migrate_pvl_ancrage.py (2) |

 (1) Télécharger [`comptes_exemple.xlsx`](https://github.com/mlebas29/Compta/raw/main/comptes_exemple.xlsx) pour trouver le modèle des formules des sections non-portefeuille de Plus_value et des colonnes H/I d'Avoirs.

 (2) *Procédure (LibreOffice fermé) :*

```bash
cd ~/Compta
git pull
python3 Claude/tool_migrate_pvl_ancrage.py comptes.xlsm
```

L'outil affiche les lignes migrées, les lignes skippées (saisie manuelle préservée), et les éventuels écarts de valeur. L'option `--dry-run` simule sans sauvegarder.

## v3.5.6 — formules de pied Budget range auto-extensibles (cosmétique)

Pas de changement de schéma (`SCHEMA_VERSION` reste à 1). Feuille Budget : les formules de pied suivantes utilisaient une référence mono-cellule au lieu d'une plage, ce qui empêchait leur extension automatique à l'insertion d'une nouvelle catégorie ou d'un nouveau poste :

- `Total = épargne` (pied du tableau Postes)
- `Épargne fixe`
- `Total hors Changes et Virements` (par colonne devise du tableau Catégories)

Aucun effet sur les valeurs dans la plupart des cas : l'application réécrit ces formules au premier ajout de devise / poste / catégorie via la GUI. La mise à niveau n'est nécessaire que si votre classeur a été initialisé à partir d'un modèle livré antérieurement (jusqu'à v3.5.5) **et** que vous avez ajouté des catégories / postes **directement dans le tableur** sans passer par la GUI.

| Mode classeur            | Mode assisté                    |
| ------------------------ | ------------------------------- |
| mise à jour manuelle (1) | une mise à jour de l'app suffit |

 (1) Télécharger [`comptes_exemple.xlsx`](https://github.com/mlebas29/Compta/raw/main/comptes_exemple.xlsx) pour trouver les formules range.

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
