# Compta_tests.md — Tests de non-régression (TNR)

Ce document décrit l'utilisation des TNR publics livrés avec Compta. Audience : contributeur ou mainteneur qui modifie le code et veut valider qu'aucune fonction existante n'est cassée.

> Les TNR ne servent **pas** à l'utilisateur final. Si tu utilises Compta sans modifier le code, tu n'as rien à lancer ici.

## Vue d'ensemble

Sept scénarios indépendants, du plus rapide au plus long :

| Scénario | Durée Linux | Ce qu'il vérifie |
|---|---:|---|
| `roundtrip` | ~7 s | Idempotence load/save d'un classeur (aucune modif) |
| `light_build` | ~8 s | Ajout minimal (1 compte + 1 poste + 1 catégorie EUR) |
| `fast` | ~21 s | Ajout 1 devise + 1 compte |
| `light_reverse` | ~26 s | Teardown du light_build (suppression) |
| `example` | ~38 s | Construction complète du classeur exemple (devises, comptes, titres, opérations) |
| `build` | ~48 s | Construction allégée (4 comptes, 5 titres, 15 opérations via pipe MANUEL) |
| `reverse` | ~105 s | Teardown complet du build (purge + delete jusqu'au template) |

Sur Mac, compter ×1.5 à ×2.5 selon le scénario.

## Mise en œuvre

### Prérequis

- **LibreOffice fermé** : aucun `soffice.bin` ne doit tourner sur ta machine. Sinon les TNR échouent au démarrage avec un message explicite. Pour forcer la fermeture : `killall -9 soffice.bin && rm -f ~/Compta/dev/.~lock.*`
- **Environnement Python UNO** opérationnel. Les scripts utilisent le shebang `#!/usr/bin/env python3-uno` (Linux : système ; Mac : Python embarqué LibreOffice via wrapper installé par `install.sh`).

### Lancement

Depuis la racine `~/Compta/dev/`, via le shebang (sélectionne automatiquement le bon Python : `python3-uno` sur Mac, système sur Linux) :

```bash
./tests/tnr_roundtrip.py
./tests/tnr_fast.py
./tests/tnr_example.py
# ... etc
```

> Sur Mac, ne pas lancer `python3 tests/...` : le `python3` système n'a pas UNO (6 runners sur 7 ont le shebang `python3-uno`). Utiliser le shebang `./tests/...` ou `python3-uno tests/...`.

Chaque TNR est autonome. Pas d'ordre obligatoire — sauf si tu veux comparer un teardown à son setup (cf. `light_build` → `light_reverse`, `build` → `reverse`).

### Sortie

Le TNR affiche un trace horodatée pas-à-pas, puis un verdict final :

- `✓` (vert) → identique à `expected.xlsm` aux tolérances près
- `ℹ` (bleu) → écart prévu et toléré (cf. notes.md du scénario)
- `⚠` (jaune) → écart sur une feuille en `warn_only` (ex : Plus_value avec cotations live)
- `✗` (rouge) → régression détectée, à investiguer

Le résultat est conservé dans `tests/tnr/<scenario>/result.xlsm` pour comparaison manuelle.

### Sandbox

Chaque scénario travaille dans une **sandbox jetable** : `tests/tnr/<scenario>/sandbox/`. Le code applicatif est accédé via symlinks ; le classeur `comptes.xlsm` est une copie modifiable du template. Conséquence pratique :

- **Ton dossier DEV ou PROD n'est jamais touché.** Tu peux éditer `comptes.xlsm` dans LibreOffice pendant qu'un TNR tourne (à l'exception de celui-là, qui spawn son propre soffice).
- **Debug post-mortem** : si un TNR échoue, la sandbox survit. Tu peux ouvrir `tests/tnr/<scenario>/sandbox/comptes.xlsm` ou `result.xlsm` dans LibreOffice pour comprendre.

### Options communes

| Option | Effet | Disponible sur |
|---|---|---|
| `--keep` | Ne restaure pas la sandbox en fin de run (debug) | `build`, `light_build`, `example` |
| `--daemon` | Route les appels UNO via le daemon JSON RPC (chemin GUI Mac) | `fast`, `light_reverse`, `reverse` |
| `--legacy` | Mode séquentiel ancien (~5 min, sans batch UNO) | `example` |

`--daemon` ne change pas la sémantique du test — il valide simplement que le chemin daemon (utilisé par la GUI sur Mac) produit le même résultat que le chemin in-process.

## Scénarios — détail

### `roundtrip`

**Objet** : vérifier qu'un load + save sans modification du classeur ne corrompt rien. C'est le test de base : si celui-là échoue, tous les autres tombent en cascade.

**Que fait-il ?** Part du template `comptes_template.xlsm`. Ouvre via `HeadlessGUI`, sauvegarde sans rien modifier. Compare le résultat au template original — identité stricte attendue.

**Quand le lancer ?** Avant tout autre TNR si tu doutes de ton environnement (LibreOffice, Python UNO).

### `fast`

**Objet** : valider le chemin GUI minimal — ajout d'une devise non-EUR et d'un compte.

**Que fait-il ?** Part du template. Ajoute la devise USD et un compte associé via `HeadlessGUI`. Compare au `expected.xlsm` du scénario. Les feuilles Plus_value et Avoirs sont en `warn_only` (les cotations live de l'USD peuvent dériver).

### `build`

**Objet** : construction allégée du classeur (sans opérations issues de sites), point de départ canonique pour `reverse`.

**Que fait-il ?** Part du template. Ajoute 4 comptes, le poste Frais bancaires, 5 devises, 15 opérations et 5 titres (dont multi-devises) via le pipe MANUEL (`manuel.xlsx`). Compare au `expected.xlsm`.

### `light_build`

**Objet** : variante minimale mono-devise (EUR uniquement) pour isoler les opérations CRUD Budget / POSTES / CAT du code multi-devises.

**Que fait-il ?** Part du template. Ajoute 1 compte EUR + 1 poste + 1 catégorie. Pas de cotations non-EUR, pas de titre, pas d'opération. Compare au `expected.xlsm`.

### `light_reverse`

**Objet** : teardown minimal de `light_build` — supprime le compte, le poste, la catégorie ajoutés. Compare au template d'origine.

**Que fait-il ?** Part de `tnr/light_build/expected.xlsm`. Supprime les 3 éléments via `HeadlessGUI`. Compare au `template` (mono-EUR, donc pas de devise à supprimer).

### `example`

**Objet** : reconstitution complète du classeur d'exemple livré dans le dépôt (`comptes_exemple.xlsx`).

**Que fait-il ?** Part du template. Construit le scénario complet via la GUI en mode batch UNO (1 session pour N ops) : 8 devises (EUR, XAU, BTC, USD, SGD, OrPr, SAT, XMR), comptes, catégories, patrimoine, opérations importées via `cpt_update`. Compare au `expected.xlsm` avec vérification stricte des 16 tuples d'appariement.

Plus_value et Avoirs en `warn_only` (cotations live). Patrimoine TOTAL et Plus_value GRAND TOTAL vérifiés en sus.

Mode `--legacy` (~5 min) disponible pour comparer le résultat batch au mode séquentiel historique.

### `reverse`

**Objet** : teardown complet — exerce tous les chemins GUI de suppression.

**Que fait-il ?** Part de `tnr/build/expected.xlsm`. Purge et supprime chaque compte, supprime les catégories, postes, devises, patrimoine. Compare au `expected.xlsm` (équivalent du template à une restriction près).

> **Restriction connue** — `purge_account` réduit les bornes des named ranges `OPdate`/`OPmontant`/... de `$A$4:$A$10000` à `$A$4:$A$9984` (artefact UNO). Tolérance intégrée dans `compare_named_ranges` (affichée en `ℹ info`). L'expected contient les bornes réduites.

## Quand lancer quel TNR

Guide selon le type de modification dans le code :

| Modification | TNR conseillés |
|---|---|
| Refacto sans changement fonctionnel | `roundtrip` |
| Ajout compte / devise GUI | `fast`, `build` |
| CRUD Budget / Catégories / Postes | `light_build`, `light_reverse` |
| Logique de suppression / purge | `reverse` (et `light_reverse` pour les petits cas) |
| Import des opérations (`cpt_update`, `inc_excel_import`) | `build`, `example` |
| Formats / charte v3.6 (`inc_formats`, `tool_fix_formats`) | `example` (couverture complète) |
| Plus_value, multi-devises, cotations | `example` (cas multi-devise large) |
| Avant un tag de release | les 7 |

Si pressé : `roundtrip` + `fast` (~30 s) couvre la moitié des régressions structurelles courantes. Pour un PR sérieux, ajouter `build` + `reverse` (~3 min). Avant un release, lancer les 7.

## Cas d'échec

Quand un TNR retourne `✗` :

1. **Lire la trace** — le TNR pointe la feuille et la cellule de l'écart.
2. **Ouvrir la sandbox** — `tests/tnr/<scenario>/sandbox/comptes.xlsm` (état post-modification) et `tests/tnr/<scenario>/result.xlsm` (copie sauvegardée). Comparer visuellement avec `expected.xlsm`.
3. **Relancer avec `--keep`** si disponible — empêche le cleanup de fin de run, permet d'inspecter en détail.
4. **Vérifier qu'aucune lock LibreOffice ne traîne** — `ls ~/Compta/dev/.~lock.*` doit être vide.

**Ne jamais régénérer `expected.xlsm` par un simple `cp result expected`** sans investigation — cela rendrait le test vert par construction et masquerait la régression. Si l'écart est légitime (changement de schéma assumé), promouvoir l'expected explicitement et documenter le delta dans le commit.

## Notes par scénario

Chaque scénario a un `tests/tnr/<scenario>/notes.md` qui détaille les spécificités de comparaison (colonnes ignorées, tolérances, warn_only, restrictions connues).
