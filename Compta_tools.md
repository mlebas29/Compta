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
python3 tool_check_integrity.py comptes.xlsm
python3 tool_check_integrity.py --fix comptes.xlsm
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
python3 tool_audit_formats.py comptes.xlsm
python3 tool_audit_formats.py comptes.xlsm --verbose
```

### tool_fix_formats.py — Correction des formats de cellules

Remet en ordre les formats d'affichage dans le classeur : montants au format
français (virgule décimale, espace milliers), dates en DD/MM/YY, devises
étrangères avec fond gris. Dry-run par défaut.

L'option `--charter` étend la correction à la charte graphique (palette
beige, quadrillage, traits de pied) et au gras des cellules contrôlées.

```
python3 tool_fix_formats.py comptes.xlsm                     # prévisualise (formats numériques)
python3 tool_fix_formats.py comptes.xlsm --apply             # applique
python3 tool_fix_formats.py comptes.xlsm --charter --apply   # + charte graphique
```

### tool_migrate_schema_v2.py — Mise à niveau du classeur

Migre un classeur d'une version structurelle antérieure (v3.4 et plus
récents) vers la version courante : drill devise, ancres ⚓, charte v4.
Voir `Compta_upgrade.md` §v4.0.0 pour la procédure complète et les
versions sources couvertes.

```
python3 tool_migrate_schema_v2.py comptes.xlsm
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

Cf. `Compta_custom.md` pour la doctrine d'usage (modes A.1 / A.2 / B, routage
PUB/PRV).

### tool_commit.sh — Commit git par instance

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

### tool_pull.sh — Pull git par instance

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

### install_custom.sh — Mise en place de `custom/` (DEV + PROD)

Comble la différence entre l'arborescence cible (décrite dans
`Compta_custom.md`) et l'état initial de l'utilisateur. Les flags paramètrent
la cible ; le script crée tout ce qui manque, idempotent.

```bash
./install_custom.sh                          # statut (diff cible/réel)
./install_custom.sh --git                    # init .git PRV dans dev/custom/
./install_custom.sh --git --remote <url>     # idem + remote PRV
./install_custom.sh --remote <url>           # ajoute remote à .git PRV existant
./install_custom.sh --py=<NAME>              # squelettes cpt_fetch_<NAME>.py / cpt_format_<NAME>.py
./install_custom.sh -h | --help
```

Exécution depuis la racine d'un clone Compta (cwd-relatif). URL du clone PUB
déduite du remote origin de l'instance courante.

Gestes idempotents enchaînés selon les flags (chemins relatifs au cwd) :

| # | Geste | Pré-condition | Effet |
|---|---|---|---|
| 1 | Créer DEV | `dev/` absent | `git clone <origin> dev/` |
| 2 | Créer DEV custom | `dev/custom/` absent | `mkdir` |
| 3 | Init `.git` PRV | `--git` et `.git` absent | `git init` + `.gitignore` minimal |
| 4 | Configurer remote PRV | `--remote <url>` et remote absent | `git remote add origin <url>` |
| 5 | Poser squelettes | `--py=<NAME>` et fichiers absents | crée `cpt_fetch_<NAME>.py` + `cpt_format_<NAME>.py` |
| 6 | Commit initial DEV custom | étape 3 ou 5 ont créé des fichiers | `git commit -m "Init custom/"` |
| 7 | Créer PROD custom | `custom/` absent | clone `file://dev/custom` (mode A) ou rsync (mode B) |

Sans flag, affiche la diff cible/réel et suggère les commandes à lancer.

`.gitignore` PRV minimal posé par étape 3 :

```
__pycache__/
*.pyc
*.bak
*.bak_*

# Sandboxes TNR jetables
tests/tnr/*/sandbox/
```

L'utilisateur reprend ensuite la main : édition des squelettes, configuration
du site dans `config.ini` (via GUI Configuration ou manuellement), commits
ultérieurs via `tool_commit.sh`. Cf. `Compta_custom.md` § *Cas A* pour le
workflow complet d'ajout de site.

Codes retour : 0 succès, 1 erreur.
Exécution depuis la racine d'un clone Compta (cwd-relatif).
