# Compta_custom.md — Architecture du framework `custom/`

Document développeur. Décrit l'architecture du projet à partir de **v4.2** afin de pouvoir personnaliser l'application pour y ajouter un ou plusieurs sites privés et/ou modifier son comportement avec des "monkeypatch" privés. 

L'architecture se caractérise par l'ajout d'un dossier **custom** dans l'arborescence. Le contenu de ce dossier qui accueille les extensions peut être versionné avec git (option A), ou non versionné (option B).

L'infrastructure des Tests de non régression **TNR** se conforme au schéma custom pour d'éventuels tests des extensions.

**Option A** — deux dépôts git à périmètres disjoints (PUB public + PRV privé d'extensions), deux instances physiques (PROD usage / DEV édition), et le mécanisme bootstrap qui charge dynamiquement les extensions privées sans qu'aucun fichier public ne les mentionne. Le dépôt PRV peut être hébergé sur un remote git privé (GitHub privé, GitLab, Gitea…) ou rester strictement local (propagation `file://`) — au choix de l'utilisateur.

**Option B** — un seul dépôt public, `custom/` non versionné. Les instances PROD/DEV restent recommandées ; la propagation `dev/custom/` → `custom/` se fait par copie manuelle (rsync, cp) à défaut de `git pull`. Même mécanisme bootstrap.

> Ce document s'adresse aux contributeurs (cloneurs GitHub qui ajoutent leur propre `custom/`) et aux développeurs du dépôt public GitHub.

## Principe

Deux dépôts **à périmètres disjoints** (*), deux instances physiques **complètement isolées**. Une instance regroupe un clone du dépôt PUB et un clone du dépôt PRV. Un clone est une copie locale d'un dépôt, susceptible de diverger temporairement de la source.

- **Dépôt GitHub public** (`github.com/mlebas29/Compta`) — **PUB** = code et doc public
- **Dépôt privé** (avec ou sans `.git` local) — **PRV** = extensions privées
- **Instance PROD** (`~/Compta/`) — dossier d'utilisation du classeur familial avec PUB + PRV
- **Instance DEV** (`~/Compta/dev/`) — dossier facultatif pour développement PUB et PRV

(*) Un fichier versionné vit **à un seul endroit** : soit dans PUB, soit dans PRV.

## Schéma

```
github.com/mlebas29/Compta              (repo public, .git PUB)
        ▲
        │ git pull / push
        │
~/Compta/                               PROD — instance d'usage quotidien
├── .git/                               clone PUB
├── .gitignore                          exclut /dev/, données perso
├── cpt_*.py, gui_*.py, inc_*.py        code PUB
├── tool_*.py                           outils PUB
├── tests/                              TNR (Tests de non régression) PUB
├── docs/                               doc dev PUB 
├── README.md, Compta_*.md              doc PUB
│
├── custom/                             extensions privées
│   ├── .git/                           option A : pull depuis remote PRV ou file://~/Compta/dev/custom
│   ├── cpt_fetch_<NAME>.py             sites privés
│   ├── cpt_format_<NAME>.py            (idem)
│   ├── patch_*.py                      monkeypatches du code public
│
├── comptes.xlsm, config.ini            classeur + config locale
├── config_*.json                       données de configuration
├── dropbox/, archives/, logs/          données opérationnelles
│
└── dev/                                DEV — gitignored par PROD
    ├── .git/                           clone PUB autonome (parallèle)
    ├── cpt_*.py, gui_*.py, …           code en cours d'édition
    ├── tests/                          TNR (édition + run, public)
    ├── docs/                           doc dev
    │
    ├── custom/                         dépôt PRV de référence (.git PRV)
    │   ├── .git/                       option A uniquement
    │   ├── cpt_fetch_*.py / cpt_format_*.py
    │   ├── patch_*.py
    │   ├── tests/                      PRV tests de référence (overlay privé)
    │   └── docs/                       PRV docs de référence
    │
    ├── comptes.xlsm                    sandbox jetable
    ├── config.ini, config_*.json       sandbox
    └── dropbox/, archives/, logs/      sandbox
```

`tests/` et `docs/` existent à plusieurs emplacements (PROD/DEV × public/custom). Le code TNR utilise `find_code_root()` pour s'auto-localiser quel que soit le contexte.

## Répartition des fichiers

| Fichier | Dépôt | Instance | Pourquoi |
|---|---|---|---|
| `cpt_*.py`, `gui_*.py`, `inc_*.py`, `tool_*.py` | PUB | PROD + DEV | code utilisable par tout cloneur |
| `tests/`, `install.sh`, `README.md`, `Compta_*.md` | PUB | PROD + DEV | doc + tests utilisateur |
| `tool_commit.sh`, `tool_pull.sh` | PUB | PROD + DEV | wrappers utiles à tout cloneur qui ajoute son `custom/` |
| `cpt_fetch_<NAME>.py`, `cpt_format_<NAME>.py` (sites privés) | PRV | `custom/` | sites perso |
| `patch_*.py` (monkeypatches) | PRV | `custom/` | extensions ponctuelles du code public |
| `comptes.xlsm`, `config.ini`, `config_*.json`, `dropbox/`, `archives/`, `logs/` | — | PROD + DEV (instances séparées) | données opérationnelles, jamais versionnées |
| `CLAUDE.md`, `CLAUDE_todo.md`, `CLAUDE_log.md` | — | DEV uniquement | outils session Claude, jamais versionnés |

## Usage côté PROD

L'instance PROD ne fait que **consommer** du code stable. Aucune édition.

### Option A — deux `git pull`

Mécanique git native, un `git pull` par dépôt :

```bash
cd ~/Compta            && git pull        # PUB depuis github
cd ~/Compta/custom    && git pull        # PRV (remote privé ou file://)
python gui_main.py
```

`tool_pull.sh` est un wrapper qui combine les deux pulls et détecte automatiquement le mode (présence de `.git` PRV, remote configuré ou non). Cf. **`Compta_tools.md`** pour la spec complète (synopsis, flags, codes retour).

### Option B — un `git pull` PUB + propagation manuelle de `custom/`

```bash
cd ~/Compta && git pull                                # PUB depuis github
rsync -a ~/Compta/dev/custom/ ~/Compta/custom/         # si instance DEV maintenue
python gui_main.py
```

`tool_pull.sh --prv` n'a pas de sens dans ce mode (pas de `.git` PRV). Le contenu de `custom/` est soit édité sur place, soit propagé depuis DEV par `rsync`/`cp`.

## Usage côté DEV

L'instance DEV est où le développeur édite, teste, casse.

### Option A — deux `.git` cohabitent

`.git` PUB à la racine `~/Compta/dev/`, `.git` PRV sous `~/Compta/dev/custom/`. Le `.gitignore` PUB exclut `custom/` ⇒ les deux dépôts ne se voient jamais.

Mécanique git native — selon le path du fichier modifié, on commit dans le `.git` correspondant :

```bash
# fichier PUB
cd ~/Compta/dev
git add cpt_foo.py
git commit -m "msg"
git push                              # → github

# fichier PRV
cd ~/Compta/dev/custom
git add cpt_extras_synoe.py
git commit -m "msg"
git push                              # → remote PRV si configuré
```

`tool_commit.sh` est un wrapper qui automatise ce routage : il classe les fichiers modifiés selon leur path, fait un `git add` + `git commit` dans le `.git` adapté, et permet à un même message de produire **un commit PUB + un commit PRV** en une seule invocation. Cf. **`Compta_tools.md`** pour la spec complète (synopsis, flags, push/tag, codes retour).

#### Édition des fichiers PRV depuis DEV

Le `custom/` côté DEV héberge le `.git` PRV de référence — c'est là que les commits PRV naissent. Quand PROD pull, c'est soit ce répertoire qu'il consulte via `file://`, soit le remote PRV s'il est configuré.

### Option B — `.git` PUB seul

Un seul dépôt (PUB) à la racine de DEV. Les fichiers sous `custom/` sont gitignorés et éditables directement, sans `.git` PRV ni `tool_commit.sh PRV`. La sauvegarde de `custom/` est à la charge de l'utilisateur (rsync vers PROD, backup externe, dépôt git privé hors arbo, etc.).

`tool_commit.sh` continue à fonctionner pour PUB (status, commit, push, tag) — la cible PRV est simplement sans objet.

## Usage parallèle PROD + DEV

Les deux instances sont indépendantes — classeur, config, dropbox, logs séparés. Lancement simultané supporté :

```bash
# terminal 1 — activité quotidienne
cd ~/Compta && python gui_main.py

# terminal 2 — dev/test
cd ~/Compta/dev && python gui_main.py
```

Aucune ressource partagée, aucune interférence.

## Chargement dynamique du `custom/`

Le code métier (`cpt_*`, `gui_*`) reste vierge — aucune mention de `custom/`. Le mécanisme : **bootstrap minimal** combinant glob discovery (sites) et monkeypatches (hooks ponctuels).

### `inc_bootstrap.py`

Au démarrage de tout point d'entrée :

1. Si `custom/` existe, l'ajouter à `sys.path`.
2. Importer tous les `custom/patch_*.py` dans l'ordre alphabétique — chacun monkeypatche ce qu'il doit modifier dans le code public.
3. Le scan des fetchers / formateurs (cas A) découvre les modules privés via `sys.path`.

L'import se fait via `inc_mode` (lui-même importé par tous les points d'entrée), donc 1 seul endroit dans le code public.

### Hooks publics offerts

Le code public expose deux familles de points d'extension. Toute extension privée s'accroche à l'un d'eux (ou aux deux).

| Hook | Type | Lieu | Convention |
|---|---|---|---|
| `cpt_fetch_<NAME>` | module | scan glob | classe `<Name>Fetcher(BaseFetcher)` + appel `fetch_main(...)` |
| `cpt_format_<NAME>` | module | scan glob | fonctions `process_operations`, `process_positions` (selon le site) |
| `EXPECTED_FILES = [...]` | variable module | `cpt_format_<NAME>.py` | liste de tuples `(pattern, 'exact'\|'glob', '1'\|'1+'\|'0-1'\|'0+')` ; définit ce qui est attendu dans `dropbox/<NAME>/` |
| `DESCRIPTION = """..."""` | variable module | `cpt_format_<NAME>.py` | texte d'aide affiché dans la GUI Configuration |
| `MAX_ACCOUNTS = N` | variable module | `cpt_format_<NAME>.py` | optionnelle ; limite stricte du nombre de comptes attachés au site (absent = illimité) |
| `post_process_supports(supports_data, total_valorisation, compte) → list[(name, val)]` | fonction | `cpt_format_SOCGEN.py` | pass-through public, monkeypatchable |

Tout nouveau hook ponctuel à ajouter doit suivre la même règle : nom neutre, signature publique stable, implémentation publique en pass-through. Le code public n'a jamais à mentionner les patches privés.

### Cas A — ajouter un site privé `FOO`

Aucun fichier public à modifier. Le bootstrap découvre le nouveau site au prochain démarrage.

**Bootstrap automatique** via `install_custom.sh` (cf. `Compta_tools.md`) :

```bash
cd ~/Compta
./install_custom.sh --git --py=FOO          # cas A.1 (.git PRV local)
./install_custom.sh --git --remote <url> --py=FOO   # cas A.2 (avec remote)
```

Le script crée DEV s'il manque, initialise `.git` PRV, pose les squelettes
`cpt_fetch_FOO.py` / `cpt_format_FOO.py`, fait un commit initial et propage
vers `~/Compta/custom/`. Il reste à l'utilisateur :

1. Étoffer les squelettes (cf. modèles ci-dessous)
2. Configurer le site dans `config.ini` et `config_accounts.json` (via GUI Configuration ou manuellement)
3. Lancer l'app — le bootstrap découvre le site

```
custom/cpt_fetch_FOO.py     # collecte (Playwright auto, ou stub manuel pour PDF/CSV déposé)
custom/cpt_format_FOO.py    # parsing → CSV opérations + soldes
```

Squelette `cpt_fetch_FOO.py` :

```python
from inc_fetch import BaseFetcher, fetch_main, config

class FooFetcher(BaseFetcher):
    def __init__(self, verbose=False):
        super().__init__(caller_file=__file__, verbose=verbose)
    def run(self):
        # navigation, téléchargement, dépôt dans dropbox/FOO/
        ...

if __name__ == '__main__':
    fetch_main(FooFetcher, description='Fetch FOO')
```

Squelette `cpt_format_FOO.py` :

```python
from inc_format import site_name_from_file

SITE = site_name_from_file(__file__)  # → 'FOO'

EXPECTED_FILES = [
    ('foo_operations.csv', 'exact', '1'),
    ('foo_supports_*.xlsx', 'glob', '0+'),
]

DESCRIPTION = """FOO — courtier en ligne, compte-titre.

══════ Configuration ══════
1 portefeuille + N comptes (1 par devise).

══════ 2FA ══════
SMS à la connexion.
"""

# Optionnel : limite stricte de comptes (absent = illimité)
MAX_ACCOUNTS = 4

def process_operations(file_path):
    ...
```

Configuration côté utilisateur — entièrement par la GUI Configuration (cpt_gui) :

- activer le site dans `config.ini` `[sites] enabled` et créer la section `[FOO]` (clés site-spécifiques)
- déclarer les comptes attachés dans `config_accounts.json` (mapping site → liste de comptes)

Aucune édition manuelle de fichier de config requise — la GUI lit les modules disponibles, propose la configuration et persiste les choix.

### Cas B — installer un patch code

Pattern monkeypatch : 1 fichier `custom/patch_<nom>.py` qui importe un module public et override un hook. `inc_bootstrap.py` charge tous les `patch_*.py` au démarrage.

Exemple — regrouper les supports ETF d'une assurance vie en un seul agrégat :

```python
# custom/patch_etf.py
import cpt_format_SOCGEN

HORS_ETF = {'FONDS_EUROS', 'FONDS_OBLIG'}

def post_process_supports(supports_data, total_valorisation, compte):
    if compte != 'Assurance vie Alice':
        return [(n, supports_data[n]) for n in sorted(supports_data)]
    total_hors_etf = sum(
        supports_data[n] for n in HORS_ETF if n in supports_data
    )
    etf = total_valorisation - total_hors_etf
    rows = [
        (n, supports_data[n]) for n in sorted(HORS_ETF) if n in supports_data
    ]
    rows.append(('ETF', etf))
    return rows

cpt_format_SOCGEN.post_process_supports = post_process_supports
```

Côté public, `cpt_format_SOCGEN.py` réserve le hook en pass-through :

```python
def post_process_supports(supports_data, total_valorisation, compte):
    """Pass-through par défaut. Monkeypatchable depuis custom/patch_*.py."""
    return [(n, supports_data[n]) for n in sorted(supports_data)]
```

### Cas A + B combiné

Un site privé peut nécessiter à la fois ses 2 modules (cas A) **et** un patch sur le code public (cas B). Pas de friction — les deux mécanismes coexistent naturellement :

```
custom/
├── cpt_fetch_FOO.py
├── cpt_format_FOO.py
└── patch_gui_foo_menu.py   # ex : ajoute un raccourci "Outils → FOO" dans la GUI
```

Le bootstrap charge d'abord les `patch_*.py` (au démarrage), puis le scan des sites trouve `cpt_fetch_FOO.py` au moment de l'orchestration. Ordre préservé.

## Tests et docs — séparation public/privé

Cf. l'arbo en section [Schéma](#schéma) : `tests/` et `docs/` existent à plusieurs emplacements. Les emplacements publics étant distribuables sur GitHub, une règle stricte s'impose :

> **Aucune référence à un site privé, aucun jeu de test privé, aucune doc qui nomme un site privé n'a sa place dans `tests/` ou `docs/`.** Tout ce qui est privé vit sous `custom/`, en miroir de la structure publique.

### Doctrine sandbox pour les TNR

Le code TNR n'opère **jamais** directement sur l'instance courante (DEV ou PROD). Chaque scénario travaille dans une sandbox jetable :

```
tests/tnr/<scenario>/sandbox/    créée à chaque run par setup_sandbox()
├── *.py                         symlinks vers le code applicatif (DEV racine)
├── custom -> ../../../custom/   symlink vers l'overlay privé
├── config.ini, config_*.json    copies modifiables
└── comptes_template.xlsm        copie initiale
```

Trois helpers dans `tnr_lib.py` :

| Helper | Rôle |
|---|---|
| `find_code_root(test_file)` | Auto-détection des 4 contextes DEV/PROD × public/custom. Remonte 2 niveaux et corrige si on est sous `custom/`. |
| `setup_sandbox(scenario_dir)` | Crée la sandbox (mkdir + symlinks + copies). Idempotent (reset si existante). |
| `set_base_dir(sandbox)` | Bascule `SCRIPT_DIR` + 11 vars dérivées (`COMPTES_XLSX`, `DROPBOX_DIR`, configs, etc.) sur la sandbox. Élimine le besoin de `backup_context`/`restore_context`. |

Variable d'environnement **`COMPTA_BASE_DIR`** : exportée par les TNR avant chaque appel `subprocess` au code applicatif (`cpt_update.py`, `tool_controles.py`, etc.) pour que `inc_mode.get_base_dir()` retourne la sandbox.

Bénéfices : DEV jamais touché (LibreOffice peut éditer `comptes.xlsm` pendant un TNR), debug post-mortem possible (la sandbox survit au plantage), parallélisation triviale, plus de `.tnr_running`/`.test_backup`.

### Doc

Pas de mécanisme de merge — `docs/` (public) et `custom/docs/` (privé) sont deux répertoires distincts consultés séparément selon le besoin. La séparation au niveau dossier suffit : aucune doctrine de fusion, aucune mécanique côté code.

### `custom/tests/` — overlay privé

En option A, `custom/tests/` versionne sous PRV les jeux de test et scripts TNR **strictement privés** (référencent un site privé ou contiennent des données nominatives). Le tracking principal reste `tests/` côté PUB.

En option B, la sauvegarde de `custom/tests/` relève des choix de l'utilisateur (cf. *Usage côté DEV — Option B*).
