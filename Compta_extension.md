# Compta_extension.md — Étendre Compta

> Document développeur (à partir de v4.2). Pour qui veut **isoler son développement**, **ajouter du code privé**, ou **brancher un site**. Topologie concrète multi-machines : [`custom/Compta_topologie.md`](custom/Compta_topologie.md). Architecture interne (3 tiers) : [`Compta_dev.md`](Compta_dev.md).

## Le modèle

Compta s'installe en **mode d'instance EX** (Thème graphique jaune or) avec un seul dossier contenant un dépôt git, le code public, **sans** code privé. Les données privées (`comptes.xlsm`, `config*`) sont initialement vierges. 

On l'étend de **trois façons orthogonales et cumulables** :

1. **Dual** — séparer le développement de la partie utilisation en deux instances isolées **PROD** et **DEV**  (§1) ;
2. **Custom** — ajouter du code privé : sites, monkeypatches dans un dossier **custom/**  (§2) ;
3. **Sites** — créer un nouveau connecteur de site public ou privé (un cas d'usage du custom) (§3) ;

Deux **dépôts git à périmètres disjoints** sous-tendent tout : **PUB** (public, GitHub — code/doc) et **PRV** (privé — extensions `custom/`). Un fichier versionné vit à un seul endroit. Une **instance** Compta = 

- soit un couple (clone PUB + clone PRV) sur une machine ; chaque clone est un **dossier** 
- soit un singleton (clone PUB)  cas du mode EX initial

> Le dépôt PRV n'est pas obligatoire mais son absence implique quelques contraintes

## 1. Dual — isoler le développement

**EX** est *mixte* : un seul dossier où l'on consomme **et** édite. Pour des raisons de **sécurité** (le bac à sable de code ne doit pas pouvoir corrompre le vrai classeur), on peut passer en **dual** — deux instances spécialisées sur la même machine :

- **PROD** (thème rouge) — consommateur : `pull` seulement, détient les vraies données et le `classeur_externe` (publication) ;
- **DEV** (thème bleu) — développement : `push`, données = copie jetable de bac à sable.

Le **mode** d'une instance — **EX**, **PROD** ou **DEV** — porte d'un seul tenant son **rôle git** (push/pull) et son **thème** : un seul axe, pas de distinction rôle/mode à retenir.

### Passer de mixte à dual

`install_fork.sh` (lancé depuis l'instance EX) crée le dossier DEV par clone distant, bascule l'EX courant en PROD, et régénère les raccourcis. Pour poser/changer le mode ou réparer un raccourci **sans réinstaller** : `install_fix.sh [EX|PROD|DEV]`. Spec : [`Compta_tools.md`](Compta_tools.md).

### Les deux dépôts

| | PUB | PRV |
|---|---|---|
| contenu | code public (`cpt_*`, `gui_*`, `inc_*`, `tool_*`), doc, tests | extensions privées (`cpt_fetch_<NAME>`, `cpt_format_<NAME>`, `patch_*`) |
| hub | GitHub | remote privé (VPS, GitLab, Gitea…) ou local |
| emplacement | racine du dossier | sous-dossier `custom/` (gitignoré par PUB) |

### Usage

- **PROD** consomme : `tool_pull.sh` (combine pull PUB + PRV). Aucune édition.
- **DEV** édite : `tool_commit.sh` route chaque fichier vers son dépôt (`custom/` → PRV, le reste → PUB) — un même message peut produire un commit PUB **et** un commit PRV (`--push`, `--tag`). Spec : [`Compta_tools.md`](Compta_tools.md).
- Les deux dossiers sont **indépendants** (classeur, config, logs séparés) → lancement simultané sans interférence.

### Sans dépôt PRV git

`custom/` peut aussi rester **non versionné** (gitignoré)  le code privé est charge quelle que soit la méthode. Restrictions : pas de `tool_commit`/`tool_pull` PRV, et la sauvegarde de `custom/` est à la charge de l'utilisateur (rsync, backup externe…).

## 2. Custom — étendre par le code

Le code public reste **vierge** : aucune mention de `custom/`. Le chargement est dynamique via **`inc_bootstrap.py`** (importé par tous les points d'entrée) — si `custom/` existe, il est ajouté à `sys.path`, tous les `custom/patch_*.py` sont importés (ordre alphabétique), et les sites privés sont découverts par scan glob.

### Hooks publics

| Hook | Type | Convention |
|---|---|---|
| `cpt_fetch_<NAME>` | module (scan) | classe `<Name>Fetcher(BaseFetcher)` |
| `cpt_format_<NAME>` | module (scan) | `process_operations` / `process_positions` |
| `EXPECTED_FILES`, `DESCRIPTION`, `MAX_ACCOUNTS` | variables module | dans `cpt_format_<NAME>.py` |
| `post_process_supports(...)` | fonction pass-through | monkeypatchable |

Règle : tout hook a un **nom neutre**, une **signature publique stable** et une **implémentation publique en pass-through**. Le code public ne mentionne jamais les patches privés.

### Monkeypatch

Un fichier `custom/patch_<nom>.py` importe un module public et remplace un hook ; `inc_bootstrap` le charge au démarrage. Exemple typique : `cpt_format_SOCGEN.post_process_supports = …` pour regrouper des supports ETF d'une assurance-vie en un seul agrégat.

### Tests & docs

Règle stricte : **aucun nom de site privé, jeu de test ou doc privée** dans `tests/`/`docs/` (distribués sur GitHub) — le privé vit sous `custom/`, en miroir. Les TNR opèrent en **sandbox jetable** (jamais le dossier courant ; `find_code_root()` auto-localise les contextes DEV/PROD × public/privé). Détail : [`Compta_tests.md`](Compta_tests.md).

## 3. Sites — ajouter un connecteur

Ajouter un site = fournir **deux modules** : `cpt_fetch_<NAME>.py` (collecte) et `cpt_format_<NAME>.py` (mise en forme) — en **public** (racine) ou en **privé** (`custom/`, à l'identique). La recette détaillée (squelettes Tier 1/2, interface pipe Tier 3, configuration utilisateur, tests, cas avancés) est dans **[`Compta_site.md`](Compta_site.md)**.
