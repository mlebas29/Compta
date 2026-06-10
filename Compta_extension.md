# Compta_extension.md — Étendre Compta

> Document développeur (à partir de v4.2). Pour qui veut **isoler son développement**, **ajouter du code ou des données privées**, **brancher un site**. 

## Le modèle

Compta s'installe en **mode d'instance EX** (thème graphique jaune or) : un seul dossier (habituellement nommé `~/Compta`) portant **deux dépôts git** à périmètres disjoints — **PUB** (code public) à la racine, et **PRV** (privé) dans le sous-dossier `custom/`. 

Le sous-dossier `custom/` ne contient aucun code ni donnée privés : il est prêt à accueillir les extensions privées et l'usage de son dépôt git PRV reste facultatif. PRV est créé vide en mode Solo (sans hub git remote ou local).

On étend le dossier **EX** de **plusieurs façons orthogonales et cumulables** :

1. **Dual** — pour séparer le développement de la partie utilisation en deux instances isolées **DEV** et **PROD** respectivement (§1) ;
2. **Code** — remplir le sous-dossier **`custom/`** de code privé  (§2) ;
3. **Sites** — pour créer un nouveau connecteur de site, possiblement privé (cas d'usage du custom) (§3) ;
4. **Données** — tout fichier privé lié au projet (notes de dev, etc.), **entièrement à ta main** (aucun cadre logiciel, donc aucune section).

Un fichier versionné vit à un seul endroit (PUB **ou** PRV).

Les trois types d'**instance** Compta :

|                    | EX                                      | PROD                              | DEV                               |
| ------------------ | --------------------------------------- | --------------------------------- | --------------------------------- |
| Dépôt git **PUB**  | Clone GitHub créé par install.sh        | Clone EX créé par install_fork.sh | Clone EX créé par install_fork.sh |
| Dépôt git **PRV**  | **Posé vide par install.sh** (Solo)     | Partagé via hub au fork           | Partagé via hub au fork           |
| Isolation instance | Utilisation et développement non isolés | Utilisation isolée                | Développement isolé               |
| Thème instance     | Jaune or                                | Rouge                             | Bleu                              |

En pratique, pour un classeur donné, il existe soit l'instance EX, soit le couple PROD+DEV.

## 1. Dual — isoler le développement

**EX** est *mixte* : un seul dossier où l'on consomme **et/ou** édite. Pour des raisons de **sécurité** (bac à sable de code qui ne doit pas pouvoir corrompre le vrai classeur), on peut passer en **dual** — deux instances spécialisées sur la même machine :

- **PROD** (thème rouge) — consommateur : `git pull` seulement pour la mise à jour de l'app, détient les vraies données et le `classeur_externe` (publication) éventuel ;
- **DEV** (thème bleu) — développement : `push`, données = copie jetable de bac à sable.

Le **mode** d'une instance — **EX**, **PROD** ou **DEV** — porte d'un seul tenant son **rôle git** (push/pull) et son **thème** : un seul axe, pas de distinction rôle/mode à retenir.

### Passer de mixte (EX) à dual (PROD+DEV)

`install_fork.sh` (lancé depuis l'instance EX) crée le dossier DEV, bascule l'EX courant en PROD, et régénère les raccourcis. Le PUB du DEV reste GitHub ; le PRV se partage selon sa **config** :

| Config PRV (EX) | Comportement au fork |
|---|---|
| **Solo** (défaut) | création d'un **hub bare local** + rattachement des deux instances → passe en **Hub local** |
| **Hub distant** | clone depuis le distant — PROD et DEV partagent le hub distant |

Un PRV **Solo** sort donc du fork en **Hub local** : l'outillage (`tool_commit`/`tool_pull`) fonctionne ensuite à l'identique du Hub distant. Pour poser/changer le mode ou réparer un raccourci **sans réinstaller** : `install_fix.sh [EX|PROD|DEV]`. Spec détaillée : [`Compta_tools.md`](Compta_tools.md).

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

## 2. Code — étendre par le code privé

Le code public reste **vierge** : aucune mention de `custom/`. Le chargement du code privé résidant dans `custom/` est dynamique via **`inc_bootstrap.py`** (importé par tous les points d'entrée) — si `custom/` existe, il est ajouté à `sys.path`, tous les `custom/patch_*.py` sont importés (ordre alphabétique), et les sites privés sont découverts par scan glob. Contrat **fail-fast** : un patch qui lève à l'import bloque le démarrage (traceback explicite) ; un chargement réussi est silencieux.

### Mise en place et contenu

`install.sh` pose un `custom/` **Solo** (versionné, sans remote) — le cadre privé homologue au public, prêt à recevoir du code. On partage ensuite selon le besoin :

- **Solo** (défaut) — dépôt privé local, pas de partage. `install_fork.sh` lui crée un hub local au passage en dual. Rien à faire pour démarrer.
- **Hub distant** — pour synchroniser le PRV **entre machines** : `cd custom && git remote add origin <remote-PRV>` (puis push), ou remplacer le frame par un clone. Hub privé (VPS, Gitea…). Le frame étant à **zéro commit**, l'attache à un hub existant se fait en fast-forward propre.

Étant gitignoré par PUB, `custom/` est le **réceptacle naturel de tout le privé**, pas seulement du code chargé : sites, monkeypatches, tests, doc et outils privés — versionnés comme le public.

### Hooks publics

| Hook | Type | Convention |
|---|---|---|
| `cpt_fetch_<NAME>` | module (scan) | classe `<Name>Fetcher(BaseFetcher)` |
| `cpt_format_<NAME>` | module (scan) | `process_operations` / `process_positions` |
| `EXPECTED_FILES`, `DESCRIPTION`, `MAX_ACCOUNTS` | variables module | dans `cpt_format_<NAME>.py` |
| `post_process_supports(...)` | fonction pass-through | monkeypatchable |

Règle : tout hook a un **nom neutre**, une **signature publique stable** et une **implémentation publique en pass-through**. Le code public ne mentionne jamais les patches privés.

### Monkeypatch

Un fichier `custom/patch_<nom>.py` importe un module public et remplace un hook ; `inc_bootstrap` le charge au démarrage. Exemple typique — regrouper des supports d'une assurance-vie en un seul agrégat :

```python
# custom/patch_agregat.py
import cpt_format_SOCGEN

def _agrege(supports_data, total_valorisation, compte):
    ...  # fusionne certains supports, retourne les lignes [(nom, valo), …]

cpt_format_SOCGEN.post_process_supports = _agrege
```

### Tests & docs

Règle stricte : **aucun nom de site privé, jeu de test ou doc privée** dans `tests/`/`docs/` (distribués sur GitHub) — le privé vit sous `custom/`, en miroir. Les TNR opèrent en **sandbox jetable** (jamais le dossier courant ; `find_code_root()` auto-localise les contextes DEV/PROD × public/privé). Détail : [`Compta_tests.md`](Compta_tests.md).

## 3. Sites — ajouter un connecteur

Ajouter un site = fournir **deux modules** : `cpt_fetch_<NAME>.py` (collecte) et `cpt_format_<NAME>.py` (mise en forme) — en **public** (racine) ou en **privé** (`custom/`, à l'identique). La recette détaillée est dans **[`Compta_site.md`](Compta_site.md)**.
