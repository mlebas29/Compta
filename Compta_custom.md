# Compta_custom.md — Architecture du framework `custom/`

Document développeur. Décrit l'architecture du projet à partir de **v4.2** : deux dépôts git à périmètres disjoints (PUB public + PRV privé d'extensions), deux instances physiques (PROD usage / DEV édition), et le mécanisme bootstrap qui charge dynamiquement les extensions privées sans qu'aucun fichier public ne les mentionne.

> Ce doc s'adresse aux contributeurs (cloneurs GitHub qui ajoutent leur propre `custom/`) et aux développeurs du repo public.

## Principe

Deux dépôts git **à périmètres disjoints** (*), deux instances physiques **complètement isolées** :

- **Dépôt public** (`github.com/mlebas29/Compta`) — **PUB** = code et doc public
- **Dépôt privé** (`.git` local, sans remote distant) — **PRV** = extensions privées
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
├── tests/                              TNR PUB
├── README.md, Compta_*.md              doc PUB
│
├── custom/                            clone PRV read-only
│   ├── .git/                           remote = file://~/Compta/dev/custom
│   ├── cpt_fetch_<NAME>.py             sites privés
│   ├── cpt_format_<NAME>.py            (idem)
│   └── patch_*.py                      monkeypatches du code public
│
├── comptes.xlsm, config.ini            classeur + config locale
├── config_*.json                       mappings, alias
├── dropbox/, archives/, logs/          données opérationnelles
│
└── dev/                                DEV — gitignored par PROD
    ├── .git/                           clone PUB autonome (parallèle)
    ├── cpt_*.py, gui_*.py, …           code en cours d'édition
    ├── tests/                          TNR (édition + run)
    ├── CLAUDE.md, CLAUDE_todo.md       outils session Claude (gitignored)
    ├── CLAUDE_log.md                   (gitignored, jetable)
    │
    ├── custom/                        dépôt PRV authoritative (.git PRV)
    │   ├── .git/                       AUCUN remote distant
    │   ├── cpt_fetch_*.py / cpt_format_*.py
    │   └── patch_*.py
    │
    ├── comptes.xlsm                    sandbox jetable
    ├── config.ini, config_*.json
    └── dropbox/, archives/, logs/      sandbox
```

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

Mécanique git native, deux `git pull` (un par dépôt) :

```bash
cd ~/Compta            && git pull        # PUB depuis github
cd ~/Compta/custom    && git pull        # PRV depuis ~/Compta/dev/custom (file://)
python gui_main.py
```

`tool_pull.sh` est un wrapper qui combine les deux pulls et offre un mode status. Spec :

```
tool_pull.sh                       # status (commits/tags en attente)
tool_pull.sh PUB                   # pull PUB depuis github
tool_pull.sh PRV                   # pull PRV depuis ~/Compta/dev/custom
tool_pull.sh PUB PRV               # pull les deux

tool_pull.sh -h | --help

Argument positionnel : PUB | PRV (combinables). Sans argument, fait un status
(git fetch --dry-run pour PUB, git log ..origin/main pour PRV).

Si un pull échoue, l'autre est tenté quand même. Résumé final par dépôt.
Codes retour : 0 succès, 1 échec d'au moins un pull.

Exécution depuis ~/Compta/ uniquement.
```

## Usage côté DEV

L'instance DEV est où Marc édite, teste, casse. Deux `.git` cohabitent : `.git` PUB à la racine `~/Compta/dev/`, `.git` PRV sous `~/Compta/dev/custom/`. Le `.gitignore` PUB exclut `custom/` ⇒ les deux dépôts ne se voient jamais.

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
git commit -m "msg"                   # pas de push, .git PRV n'a pas de remote
```

`tool_commit.sh` est un wrapper qui automatise ce routage : il classe les fichiers modifiés selon leur path, fait un `git add` + `git commit` dans le `.git` adapté, et permet à un même `-m "msg"` de produire **un commit PUB + un commit PRV** en une seule invocation. Spec :

```
tool_commit.sh                           # status PUB + PRV (défaut, sans -m)
tool_commit.sh PUB                       # status PUB seulement
tool_commit.sh PRV                       # status PRV seulement

tool_commit.sh -m "message"              # commit PUB + PRV (selon modifs)
tool_commit.sh -m "message" PUB          # commit PUB seulement
tool_commit.sh -m "message" PRV          # commit PRV seulement

tool_commit.sh -m "message" --push       # commit + push PUB
tool_commit.sh -m "message" --tag vX.Y.Z # commit + tag PUB

tool_commit.sh -h | --help

Argument positionnel (optionnel) : PUB | PRV. Par défaut les deux.
--push et --tag n'agissent que sur PUB (PRV n'a pas de remote, et un tag PRV
serait invisible).

Routage automatique des modifs :
  - Fichiers sous custom/  → .git PRV
  - Tout le reste            → .git PUB

Fichiers non trackés : avertissement listant chaque fichier, sans auto-ajout.
L'utilisateur reste maître de l'inclusion (git add explicite).

Codes retour : 0 succès, 1 erreur (cwd, conflit, argument invalide).
Exécution depuis ~/Compta/dev/ uniquement.
```

### Édition des fichiers PRV depuis DEV

Le `custom/` côté DEV héberge le `.git` PRV authoritative — c'est là que les commits PRV naissent. Quand PROD pull, c'est ce répertoire qu'il consulte via `file://`.

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

Exemple — regrouper les supports d'une assurance vie en agrégat ETF :

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

`tests/` et `docs/` à la racine DEV ont vocation à devenir publics (cf. chantier #63 anonymisation TNR + ouverture progressive de la doc dev). Ils sont aujourd'hui gitignored par PUB **temporairement**. À leur ouverture, ils seront distribués à tout cloneur GitHub — ce qui dicte une règle stricte :

> **Aucune référence à un site privé, aucune fixture privée, aucune doc qui nomme un site privé n'a sa place dans `tests/` ou `docs/`.** Tout ce qui est privé vit sous `custom/`, en miroir de la structure publique.

```
~/Compta/dev/
├── tests/                       futur public (anonymisé via #63)
│   ├── tnr_pipe.py              code TNR commun
│   ├── tnr_lib.py
│   └── tnr/pipe/                fixtures publiques (BOURSOBANK, NATIXIS, …)
├── docs/                        futur partiel public
│   └── site_BOURSOBANK.md
└── custom/                      privé strict (PRV)
    ├── tests/tnr/pipe/          fixtures privées (overlay)
    └── docs/
        └── site_FOO.md          (cohérent avec Cas A)
```

### Pattern overlay pour les TNR

Le code TNR public scanne `tests/tnr/<scenario>/` puis, **si** des fixtures privées existent à l'emplacement miroir, les ajoute à la liste. Le scénario tourne avec ou sans privé sans connaître le contenu spécifique.

Pour respecter la doctrine *« le code public ne mentionne jamais `custom/` »*, `inc_bootstrap.py` reste l'unique fichier public à exposer le chemin. Il publie une variable consommable :

```python
# inc_bootstrap.py — extension à prévoir lors du premier TNR/doc privé
CUSTOM_DIR = _CUSTOM if _CUSTOM.is_dir() else None
```

Le code TNR consulte `inc_bootstrap.CUSTOM_DIR` (et None si absent), sans jamais épeler le nom `custom/`. Un cloneur GitHub sans `custom/` voit ses TNR publics tourner normalement avec ses seules fixtures publiques.

### Doc

Pas de mécanisme de merge — `docs/` (public) et `custom/docs/` (privé) sont deux répertoires distincts consultés séparément selon le besoin. La séparation au niveau dossier suffit : aucune doctrine de fusion, aucune mécanique côté code.

### Statut

Doctrine **cible**, à appliquer quand un TNR ou une doc privée sera créé. Le mécanisme `CUSTOM_DIR` reste à exposer dans `inc_bootstrap.py`. Aucun TNR ni doc privée n'existe à ce jour.
