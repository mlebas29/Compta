# Compta — Outils de maintenance

Le projet inclut des outils en ligne de commande pour diagnostiquer,
vérifier et corriger le classeur `comptes.xlsm`. Ils sont tous optionnels
et complémentaires à l'interface graphique.

Deux familles principales : les **outils classeur** (audit, fix, migration) qui
agissent sur le `.xlsm` ; et les **outils d'environnement git** (commit, pull,
install de `custom/`) qui orchestrent la circulation du code entre PROD, DEV et
github — usage plutôt dev. S'y ajoute `tool_fetch_profile.py`, diagnostic
**lecture seule** des collectes (profil de navigation par site).

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
Voir `Compta_upgrade_classeur.md` §v4.0.0 pour la procédure complète et les
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

### tool_fetch_profile.py — Profil de navigation des collectes

Audit **lecture seule** des profils de navigation par site (baseline glissante
machine-locale `logs/fetch_profiles.json`, alimentée par les collectes via
`fetch_main`). Répond à « le site a-t-il changé de comportement ? » : durée
**machine** par étape (attente humaine 2FA/CAPTCHA retranchée), nombre de
fichiers, succès, et **occurrence d'interaction** humaine par étape (taux
glissant `k/N`). Ne lance aucune collecte.

Les **étapes** affichées (Login / Opérations / Soldes…) suivent le vocabulaire des fetchers. « **Login** » = phase d'**authentification complète** (identification + éventuels 2FA / CAPTCHA / écrans intermédiaires), cf. `Compta.md` ANNEXE B.

```
./tool_fetch_profile.py              # résumé (sites, runs, dernier état)
./tool_fetch_profile.py --report     # dérives du dernier run vs baseline
./tool_fetch_profile.py --show SITE   # baseline détaillée d'un site
```

---

## Outils environnement git

Cf. `Compta_extension.md` pour la doctrine d'usage (dual PROD/DEV, routage
PUB/PRV).

### Commit / push — git nu, par dépôt

Plus de wrapper (`tool_commit` retiré #110) : commit et push en `git` nu, par
dépôt. Routage **par chemin** : `custom/` → dépôt **privé** (PRV), le reste →
dépôt **public** (PUB).

```bash
git -C .      commit -am "msg"  &&  git -C .      push    # PUB
git -C custom commit -am "msg"  &&  git -C custom push    # PRV (si présent)
```

- L'`origin` de chaque dépôt — et d'éventuels **remotes additionnels** (publication,
  synchro) — dépendent de l'**installation** : un poste simple pousse PUB vers
  GitHub ; une topologie multi-instances peut router autrement (propre à l'install).
- **Avant push** : `git status` + `git ls-files --others --exclude-standard`
  (un fichier neuf oublié ?). `tool_audit_git.py` signale arbre, non-trackés et
  état de publication.
- **Tag** : `git tag vX.Y.Z` (local), poussé à la publication. **Jamais**
  `git push --force` ; pas de commit/push sans accord.

### Synchro git (pull) — git nu, par dépôt

Plus de wrapper `tool_pull` : les deux dépôts se pullent en **git direct**, par
dossier — `git pull` à la racine pour PUB, `git -C custom pull` pour PRV (cf.
modèle de portée). À l'ouverture, `tool_audit_git.py` (sans option) **signale**
le retard sur le clone courant — et l'avis badge → `upgrade` si une migration
est en attente ; à la clôture, `tool_audit_git.py --align` pull `--ff-only`
**tous** les clones joignables. La correction reste git ; l'audit est le
détecteur.

### tool_pullconf.sh — Pull config depuis une autre machine

Là où **git** rapatrie le **code**, `tool_pullconf` rapatrie la **config
per-instance non versionnée** (gitignorée :
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
le fork détecte l'état de `custom/` (taxonomie **Absent / Fichiers / Solo / Hub** :
Absent = pas de `custom/` ; Fichiers = sans `.git` ; Solo = `.git` sans remote ;
Hub = `.git` avec remote) et adapte :

| État de `custom/` | Comportement du fork |
|---|---|
| **Absent** — pas de `custom/` | rien — instance PUB seule |
| **Fichiers** — `custom/` sans `.git` | copie des fichiers vers le DEV (non versionné des deux côtés ; sauvegarde à la charge de l'utilisateur) |
| **Solo** — `.git` sans remote | crée un hub **bare local** (`~/Compta-hub/custom.git`, override `$COMPTA_HUB`), y rattache l'instance courante (origin + tracking) et y clone le DEV → **les deux instances passent en Hub** |
| **Hub** — `.git` avec remote | clone distant depuis l'origin — les deux instances partagent le hub existant |

Le cas Solo exige que le chemin du hub soit libre (erreur explicite sinon).
Migration ultérieure du hub local vers un distant (VPS, NAS…) : déplacer le
bare puis `git remote set-url origin <url>` dans chaque clone — aucune autre
restructuration.
