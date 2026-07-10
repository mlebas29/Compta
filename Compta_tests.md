# Compta_tests.md — Tests de non-régression (TNR)

Ce document décrit l'utilisation des TNR publics livrés avec Compta. Audience : contributeur ou mainteneur qui modifie le code et veut valider qu'aucune fonction existante n'est cassée.

> Les TNR ne servent **pas** à l'utilisateur final. Si tu utilises Compta sans modifier le code, tu n'as rien à lancer ici.

## Vue d'ensemble



| Scénario | Durée Linux | Ce qu'il vérifie |
|---|---:|---|
| `roundtrip` | ~7 s | Idempotence load/save d'un classeur (aucune modif) |
| `light_build` | ~8 s | Ajout minimal (1 compte + 1 poste + 1 catégorie EUR) |
| `fast` | ~21 s | Ajout 1 devise + 1 compte |
| `light_reverse` | ~26 s | Teardown du light_build (suppression) |
| `example` | ~38 s | Construction complète du classeur exemple (devises, comptes, titres, opérations) |
| `build` | ~48 s | Construction allégée (4 comptes, 5 titres, 15 opérations via pipe MANUEL) |
| `reverse` | ~105 s | Teardown complet du build (purge + delete jusqu'au template) |
| `fetch` | variable | Collecte réelle des sites de la config réelle (config.ini) dans un dossier dédié jetable (sandbox) |

Sur Mac, compter ×1.5 à ×2.5 selon le scénario (sauf `fetch`, dont la durée dépend du site et de la saisie humaine).

Les sept premiers sont **automatisables** et comparent le classeur produit à un classeur de **référence**.

`fetch` est à part : il lance la **vraie collecte** d'un site — la seule couche que les autres ne touchent pas. Il n'est pas automatisable (mot de passe GPG, double authentification) et n'a pas de classeur de référence (les données changent à chaque collecte).

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

### `fetch` (collecte réelle)

**Objet** : vérifier les collecteurs `cpt_fetch_*.py` — navigation du site, sélecteurs, déroulé de la collecte, garde anti-HTML (qui refuse une page de connexion servie à la place d'un relevé) — ce que `build` et `example` ne couvrent pas, puisqu'ils partent de fichiers déjà téléchargés.

**Nature** : à part des sept autres. Il se connecte aux **vrais sites** (mot de passe GPG, double authentification saisie à la main) et vérifie des **invariants** sur ce qui est collecté — pas de comparaison à un classeur de référence, pas de régénération. Il ne tourne donc que si le credential du site est présent sur la machine, et ne s'enchaîne jamais tout seul. Il n'est pas **isolé** : il lit le `config.ini`, les credentials et les comptes **réels** de l'instance — seul le dossier où atterrit la collecte est mis à l'écart.

**Prérequis** (différents des sept autres) : credential GPG de l'instance, accès réseau. Aucune contrainte côté LibreOffice. Se lance avec le `python3` **habituel** (pas `python3-uno`).

**Choix des sites** (lu dans `config.ini`) :

```bash
python3 tests/tnr_fetch.py              # sites actifs (défaut)
python3 tests/tnr_fetch.py --all        # tout site configuré ayant un collecteur
python3 tests/tnr_fetch.py SOCGEN,WISE  # liste explicite (prioritaire)
python3 tests/tnr_fetch.py --list       # inventaire (actif / configuré)
```

**Déroulé par site** : (1) vraie collecte → un **dossier de collecte dédié et jetable** (le dossier de collecte réel n'est pas touché) ; (2) **invariants** : au moins un fichier collecté · aucun n'est une page HTML (ce qui exerce le garde anti-HTML) · le format `cpt_format_<SITE>` le lit sans erreur → au moins une opération ; (3) verdict par site : réussite, échec, ou ignoré.

**Périmètre** : collecteurs par navigateur. Ceux qui passent par une interface de programmation (sans navigateur) sont ignorés. Un site sans credential sur la machine est ignoré.

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
| Collecte : `cpt_fetch_*`, sélecteurs, garde anti-HTML | `fetch` (manuel, par site — double authentification) |
| Avant un tag de release | les 7 automatiques ; `fetch` à part (manuel, à jouer par site si des collecteurs ont changé) |

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
