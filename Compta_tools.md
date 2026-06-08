# Compta — Outils de maintenance

Le projet inclut des outils en ligne de commande pour diagnostiquer,
vérifier et corriger le classeur `comptes.xlsm`. Ils sont tous optionnels
et complémentaires à l'interface graphique.

Deux familles : les **outils classeur** (audit, fix, migration) qui agissent
sur le `.xlsm` ; et les **outils d'environnement git** (commit, pull, install
de `custom/`) qui orchestrent la circulation du code entre PROD, DEV et
github — usage plutôt dev.

---

### tool_controles.py — Diagnostic du classeur

Lit la cellule `Contrôles!A1` (qui résume l'état du classeur) et affiche un
diagnostic humain : comptes déséquilibrés, catégories manquantes, warnings.
C'est le premier réflexe après un import ou une modification manuelle.

```
./tool_controles.py        # diagnostic standard
./tool_controles.py -v     # détails par erreur
```

### tool_compare_xlsx.py — Comparer deux versions du classeur

Compare deux fichiers Excel feuille par feuille (Opérations, Plus_value,
Avoirs). Utile pour vérifier ce qui a changé entre deux runs du pipeline,
ou entre le classeur actuel et une archive précédente.

```
./tool_compare_xlsx.py fichier1.xlsx fichier2.xlsx
./tool_compare_xlsx.py --prev          # compare avec l'archive N-1
./tool_compare_xlsx.py --re "LOYER"    # filtre par regex
```

### tool_check_integrity.py — Vérification des formules

Parcourt le classeur et vérifie que les formules (sommes, références entre
feuilles, named ranges) sont cohérentes. Détecte les formules cassées,
les références `#REF!`, les incohérences de totaux. Option `--fix` pour
corriger automatiquement.

```
./tool_check_integrity.py comptes.xlsm
./tool_check_integrity.py --fix comptes.xlsm
```

### tool_categories_audit.py — Audit des catégorisations

Compare les règles de catégorisation (`config_category_mappings.json`) avec
ce qui est réellement dans le classeur. Permet de repérer les opérations non
catégorisées ou les patterns obsolètes.

```
./tool_categories_audit.py             # audit complet
./tool_categories_audit.py --summary   # résumé uniquement
```

### tool_refs.py — Audit des références d'appariement

Les opérations importées sont appariées (rapprochées) via des références.
Cet outil audite et normalise ces références : détecte les doublons, corrige
la casse et la classification.

```
./tool_refs.py --audit              # rapport des problèmes
./tool_refs.py --fix --dry-run      # prévisualise les corrections
./tool_refs.py --fix                # applique
```

### tool_audit_formats.py — Audit charte graphique

Vérifie en lecture seule la conformité du classeur à la charte graphique
(palette de fonds, grille beige, bordures de pied). Ne modifie rien. Mode
synthèse par pattern par défaut, `--verbose` pour détailler chaque écart.

```
./tool_audit_formats.py comptes.xlsm
./tool_audit_formats.py comptes.xlsm --verbose
```

### tool_fix_formats.py — Correction des formats de cellules

Remet en ordre les formats d'affichage dans le classeur : montants au format
français (virgule décimale, espace milliers), dates en DD/MM/YY, devises
étrangères avec fond gris. Dry-run par défaut.

L'option `--charter` étend la correction à la charte graphique (palette
beige, quadrillage, traits de pied) et au gras des cellules contrôlées.

```
./tool_fix_formats.py comptes.xlsm                     # prévisualise (formats numériques)
./tool_fix_formats.py comptes.xlsm --apply             # applique
./tool_fix_formats.py comptes.xlsm --charter --apply   # + charte graphique
```

### tool_migrate_schema_v2.py — Mise à niveau du classeur

Migre un classeur d'une version structurelle antérieure (v3.4 et plus
récents) vers la version courante : drill devise, ancres ⚓, charte v4.
Voir `Compta_upgrade.md` §v4.0.0 pour la procédure complète et les
versions sources couvertes.

```
./tool_migrate_schema_v2.py comptes.xlsm
```

### tool_purge.py — Purge de l'historique

Supprime les opérations anciennes (au-delà d'un an) pour réduire la taille
du classeur, en préservant les comptes suivis en valorisation (assurances vie,
portefeuilles, métaux). Crée un backup avant modification.

```
./tool_purge.py --date 2024-01-01   # purge avant cette date
```

### tool_cleanup.py — Nettoyage système

Nettoie les processus Python orphelins (LibreOffice, UNO) et les fichiers
temporaires qui peuvent rester après un crash du pipeline.

```
./tool_cleanup.py                   # nettoyage complet
./tool_cleanup.py --processes       # processus uniquement
```

---

## Outils environnement git

Cf. `Compta_extension.md` pour la doctrine d'usage (dual PROD/DEV, routage
PUB/PRV).

### tool_commit.sh — Commit git par dossier

Wrapper qui détecte le mode d'installation `custom/` et route les commits
vers le `.git` adapté selon le path du fichier modifié (`custom/` → PRV,
reste → PUB). Permet de produire en une invocation un commit PUB et un commit
PRV avec le même message.

La sémantique du script est le commit local. Push et tag sont des options
explicites.

```bash
./tool_commit.sh "message"                   # commit local (PUB + PRV selon ce qui existe)
./tool_commit.sh "message" --push            # commit + push (PUB → github ; PRV → remote si configuré)
./tool_commit.sh "message" --push --tag vX   # commit + push + tag PUB
./tool_commit.sh "message" --pub             # restreint PUB
./tool_commit.sh "message" --prv             # restreint PRV
./tool_commit.sh --status                    # affichage état (pas de commit)
./tool_commit.sh -h | --help
```

Détection automatique du mode (lecture du filesystem, aucune config externe) :

| Mode | État physique | Comportement |
|---|---|---|
| **0** | pas de `custom/` | PUB seul |
| **B** | `custom/` sans `.git` | PUB seul, PRV signalé sans `.git` |
| **A.1** | `custom/.git` sans remote | PUB push, PRV commit local |
| **A.2** | `custom/.git` avec remote | PUB et PRV push |

Tag : `--tag vX.Y.Z` taggue PUB uniquement (jamais PRV — un tag invisible
n'a pas de sens) et implique `--push`.

Fichiers non trackés : avertissement listant chaque fichier, sans auto-ajout.
L'utilisateur reste maître de l'inclusion (`git add` explicite).

Codes retour : 0 succès, 1 erreur (cwd, conflit, argument invalide).
Exécution depuis la racine d'un clone Compta (cwd-relatif).

### tool_pull.sh — Pull git par dossier

Wrapper qui pull les dépôts disponibles selon le mode détecté. PUB est
toujours pullé depuis github. PRV est pullé depuis son remote configuré
(option A.2) ou depuis le `file://` source local (option A.1).

```bash
./tool_pull.sh                               # pull PUB + PRV (selon mode)
./tool_pull.sh --pub                         # restreint PUB
./tool_pull.sh --prv                         # restreint PRV
./tool_pull.sh --status                      # affichage état (pas de pull)
./tool_pull.sh -h | --help
```

Détection mode : identique à `tool_commit.sh`.

Cas 0 et B : `--prv` retourne une erreur explicite (pas de `.git` PRV à
pull ; propagation manuelle requise en option B).

Si un pull échoue, l'autre est tenté quand même. Résumé final par dépôt.

Codes retour : 0 succès, 1 échec d'au moins un pull.
Exécution depuis la racine d'un clone Compta (cwd-relatif).

### tool_pullconf.sh — Pull config depuis une autre machine

Frère de `tool_pull.sh` : là où `tool_pull` rapatrie le **code** (git),
`tool_pullconf` rapatrie la **config per-instance non versionnée** (gitignorée :
`config.ini`, credentials, `config_*.json`, classeur) depuis une autre machine —
utile pour amorcer un nouveau clone (git transporte le code, pas la config).

```bash
./tool_pullconf.sh <source> [--path DIR] [--dry-run]
./tool_pullconf.sh marc@autre-machine.local              # apply (avec backup)
./tool_pullconf.sh marc@autre-machine.local --dry-run    # liste présents/absents
./tool_pullconf.sh marc@autre-machine.local --path /chemin/instance
```

`<source>` = adresse SSH ; `--path` = chemin de l'instance distante (défaut :
`Compta`, relatif au `$HOME` distant ; absolu accepté). Liste des fichiers =
`$CONFIG_FILES` (source unique dans `inc_install.sh`, partagée conceptuellement
avec ce que `reclone.sh` restaure et ce que `.gitignore` protège).

Transport par **flux** `tar | ssh` : aucun fichier sensible n'est matérialisé
sur le disque distant (pas de tar temporaire à nettoyer). Applique par défaut sur
le clone courant en **sauvegardant** tout fichier existant (`<f>.bak-<horodatage>`)
avant écrasement ; `--dry-run` n'inspecte que la source. Fichiers absents tolérés,
joignabilité SSH vérifiée d'abord (fail-loud).

Codes retour : 0 succès, 1 erreur (SSH injoignable, transfert incomplet, argument).
Exécution depuis la racine d'un clone Compta (cwd-relatif).

### Mise en place de `custom/`

`install_custom.sh` a été retiré : la mise en place du dépôt privé `custom/`
se fait désormais par un simple clone du remote PRV —
`git clone <remote-PRV> custom`. Détails et alternatives (sans dépôt PRV git)
dans [`Compta_extension.md`](Compta_extension.md).

## Provisioning (install)

| Outil | Rôle |
|---|---|
| `install.sh` | installe une instance **EX** dans le clone courant (deps + structure + raccourci) |
| `install_fork.sh [--no-data] [chemin-dev]` | passe d'une instance EX au **dual** PROD+DEV (bascule EX→PROD, raccourcis ; volet PRV selon l'état de `custom/`, cf. ci-dessous). Données métier copiées par défaut (sémantique du fork) ; `--no-data` = DEV vierge (config `.default`, classeur template) |
| `install_fix.sh [EX\|PROD\|DEV]` | pose le mode / répare le raccourci, sans réinstaller les dépendances |

Module commun sourcé : `inc_install.sh` (UI, OS, mode, raccourci). Doctrine (mixte EX, dual PROD/DEV) : [`Compta_extension.md`](Compta_extension.md).

### install_fork.sh — volet PRV selon l'état de `custom/`

Le PUB du DEV est toujours un clone distant de l'origin (GitHub). Pour le PRV,
le fork détecte l'état de `custom/` (même taxonomie 0/B/A.1/A.2 que
`tool_commit.sh`) et adapte :

| État de `custom/` | Comportement du fork |
|---|---|
| **0** — pas de `custom/` | rien — instance PUB seule |
| **B** — `custom/` sans `.git` | copie des fichiers vers le DEV (non versionné des deux côtés ; sauvegarde à la charge de l'utilisateur) |
| **A.1** — `.git` sans remote | crée un hub **bare local** (`~/Compta-hub/custom.git`, override `$COMPTA_HUB`), y rattache l'instance courante (origin + tracking) et y clone le DEV → **les deux instances passent en A.2** |
| **A.2** — `.git` avec remote | clone distant depuis l'origin — les deux instances partagent le hub existant |

Le cas A.1 exige que le chemin du hub soit libre (erreur explicite sinon).
Migration ultérieure du hub local vers un distant (VPS, NAS…) : déplacer le
bare puis `git remote set-url origin <url>` dans chaque clone — aucune autre
restructuration.
