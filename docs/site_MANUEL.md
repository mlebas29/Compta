# Site MANUEL — Saisie manuelle d'opérations

## Vue d'ensemble

`MANUEL` permet d'**importer des opérations saisies à la main** via un classeur
`manuel.xlsx`, comme alternative à la saisie directe dans `comptes.xlsm`. Utile
pour les opérations qui doivent **passer par le pipeline d'import** (catégorisation,
appariement, génération des #Solde manquants) plutôt que d'être tapées directement
dans le classeur.

**Type :** saisie manuelle (aucune collecte automatique — pas de `fetch`).
**Visibilité :** site **caché** de la GUI (ni onglet Sites, ni onglet Collecte) —
usage spécifique et marginal.
**Format :** un fichier `.xlsx` déposé dans `dropbox/MANUEL/`.

## Le formulaire `manuel.xlsx`

Feuille **`Import`**, une ligne d'en-tête puis une ligne par opération :

| Colonne | Champ | Obligatoire | Remarque |
|---|---|---|---|
| A | **Date** | oui | `JJ/MM/AAAA` ou date Excel |
| B | Libellé | — | texte libre |
| C | **Montant** | oui | numérique (crédit +, débit −) |
| D | **Devise** | oui | code (EUR, USD, OrJo…) |
| E | Equiv | — | équivalent EUR (sinon calculé) |
| F | Réf | — | référence d'appariement (`-` = à apparier) |
| G | Catégorie | — | catégorie budgétaire / `@…` |
| H | **Compte** | oui | non vide au parse ; l'existence dans la feuille Avoirs est contrôlée en aval |
| I | Commentaire | — | texte libre |

Une ligne de catégorie `#Solde` fixe le solde d'un compte à une date. **Sans
`#Solde` fourni**, `generate_missing_soldes` génère un **« Σ Solde calculé »**
(cumul des opérations) — voir `docs/architecture_import.md`.

## Feuille `Positions` (plus-value latente)

Le même `manuel.xlsx` peut porter une seconde feuille, **`Positions`**, destinée à
alimenter les **positions / plus-value latente (PVL)** : la valorisation d'un titre
à une date, indépendamment du flux d'opérations. Feuille **optionnelle** — absente,
elle est simplement ignorée. Une ligne d'en-tête puis une ligne par position :

| Colonne | Champ | Obligatoire | Remarque |
|---|---|---|---|
| A | **Date** | oui | `JJ/MM/AAAA` ou date Excel ; seul champ requis au parse (ligne ignorée si vide) |
| B | Ligne | — | libellé du titre / de la position |
| C | Montant | — | valorisation (numérique) ; vide → `0` |
| D | Compte | — | compte de rattachement ; l'existence dans la feuille Avoirs est contrôlée en aval |

Seule la **Date** est validée (non vide) au parse ; `Ligne`, `Montant` et `Compte`
sont repris tels quels, les contrôles de cohérence intervenant plus loin dans le
pipeline. Ces lignes ne sont pas des opérations : elles ne passent pas par la
catégorisation ni l'appariement, mais nourrissent le calcul de PVL.

## Cadre d'exécution (provisionnement / archivage)

Le formulaire est **auto-provisionné** et **auto-réapprovisionné**, sans intervention :

1. **Gabarit** : `manuel.xlsx.default` (en-tête seul) est livré à la racine du projet.
2. **Provisionnement** : `install.sh` crée `dropbox/MANUEL/` et y copie le gabarit
   → `dropbox/MANUEL/manuel.xlsx` (si absent). Un formulaire vierge est toujours prêt.
3. **Saisie** : remplir `dropbox/MANUEL/manuel.xlsx` (une ligne par opération).
4. **Import** : lancer l'import (collecte/pipeline). Le fichier est lu, **importé**,
   puis **archivé** dans `archives/MANUEL/` avec un horodatage (HDS) — historique.
5. **Réapprovisionnement** : concomitant à l'archivage, `cpt_update` recopie le
   gabarit → un `manuel.xlsx` vierge est de nouveau présent pour la prochaine saisie.

**Provision-si-absent** : le réapprovisionnement **n'écrase jamais** un `manuel.xlsx`
présent (donc aucune perte de saisie si le fichier n'a pas été consommé). Corollaire
assumé : si vous relancez un import sans rien saisir, le formulaire vierge est archivé
(léger bruit dans `archives/MANUEL/`) — choix de simplicité (archivage sans cas
particulier).

## Notes

- **Repli manuel universel** : `dropbox/MANUEL/` sert aussi de point d'entrée pour
  toute opération ad hoc à faire transiter par le pipeline.
- **Pas de fetch, pas de credentials** : rien à configurer côté collecte.
- MANUEL reste une **section `config.ini`** (nécessaire pour que l'import traite
  `dropbox/MANUEL/`), mais sans `cpt_fetch_MANUEL.py` ni `DESCRIPTION` (site caché).
