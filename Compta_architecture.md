# Compta — Architecture de développement avec git & l'IA

Ce document expose comment le code et les fichiers de Compta sont organisés en dépôts git (*), comment ils circulent entre les machines de **développement** et d'**utilisation**, et comment l'assistant IA est utilisé.

> (*) git est une base de données spécialisée dans le cycle de vie d'un projet informatique. Un dépôt git est matérialisé par un sous-dossier `.git` dans le dossier de l'application où vit le code.

Pour la présentation de Compta, voir [`README.md`](README.md).

```
 +-----------------------------------------+
 |                 GitHub                  |
 |                   PUB                   |
 +---+-----------------------+---------+---+
     |                       |         |
     |                       |         |
 +---+-----------+           |         |
 |      VPS      |           |         |
 |   PUB + PRV   |           |         |
 +---+---------+-+           |         |
     |         |             |         |
     |         |             |         |
 +---+---+ +---+---+     +---+---+ +---+---+
 |MacBook| |  PC   |     |  PC   | | Tiers |
 |PUB+PRV| |PUB+PRV|     |  PUB  | |  PUB  |
 +-------+ +-------+     +-------+ +-------+
   Développement            Utilisation
```

**Les 3 niveaux :**

- **GitHub** : l'unique dépôt PUB public ([github.com](https://github.com)).
- **VPS** : serveur privé (hébergement OVH) portant les **deux** dépôts de référence public + privé (PUB + PRV).
- **Machines privées** : chaque poste porte le dépôt PUB — et PRV en plus pour le développement ; **Tiers** = un poste d'utilisation tierce.



> Le **PC** fonctionne en **dual boot** (partition Linux + partition Windows 11 / WSL) ; sa partition **Linux** est elle-même **duale** — deux instances Compta, l'une de développement, l'autre d'utilisation.
>
> Le **VPS** a un accès public pour faciliter le **nomadisme** du développement.

## Dépôts git

Une machine peut héberger plusieurs instances Compta ; une instance est un répertoire (avec son raccourci de lancement), portant un dépôt **PUB** — et optionnellement un dépôt **PRV** (`custom/`) en développement. Contenu de chacun :

| Dépôt | Contenu |
|---|---|
| **PUB** | Code **public** : l'application + les connecteurs de banques publics |
| **PRV** (`custom/`) | Couche **privée** : connecteurs de banques privés, extensions de l'app, données et notes de travail, **fichiers IA** (`CLAUDE*`) |

La séparation garde hors du dépôt public tout ce qui est privé — sites confidentiels, données, notes — sans rien changer au fonctionnement de l'app : au démarrage, le code privé (`custom/`) se superpose au code public (cf. [`Compta_extension.md`](Compta_extension.md)).

## Développement et utilisation

Une instance joue l'un des deux rôles, selon l'`origin` de son dépôt PUB :

- **Développement** — on édite le code et on le valide sur chaque OS. `origin` PUB = le **VPS** (hub privé) ; on **publie** vers GitHub.
- **Utilisation** — l'app tourne, sans édition. `origin` PUB = **GitHub** ; l'instance tire le publié en **lecture seule**, jamais rattaché au hub → **intouchable par le travail en cours**.

**Le circuit.** Les machines de développement convergent sur le **VPS**, où se poussent et se tirent PUB (travail en cours) *et* PRV — c'est là qu'un portage macOS/Windows se valide avant publication. **GitHub ne reçoit que du validé** (`git push github main` + tag) et n'héberge que le **PUB** : le **PRV ne passe jamais par GitHub**, il circule uniquement par le VPS (cloud personnel, pas de service tiers). Les machines d'utilisation tirent le publié (`git pull`).

Seul le **PC Linux** est *dual* — développement et utilisation y cohabitent (deux instances, même machine) pour isoler le vrai classeur de production pendant qu'on développe à côté. MacBook et Windows/WSL sont des postes *mixtes* (ils consomment **et** éditent) ; le poste tiers ne fait que consommer le publié.

## Développement assisté par l'IA

### CLI

Compta est développé avec l'assistant **Claude Code** (CLI d'Anthropic). Cet assistant est installé sur le poste de travail Linux, Mac ou Windows afin de pouvoir lire, modifier ou exécuter sous contrôle utilisateur.

Le CLI peut fonctionner dans un terminal ou une console ordinaire (`claude`), ou dans une App (`claude-desktop`). Voir [claude.com/claude-code](https://claude.com/claude-code) pour l'installer.

### Fichiers `CLAUDE*`

L'état de collaboration vit dans des fichiers **`CLAUDE*`**, versionnés dans le dépôt **PRV** (`custom/`, jamais publiés) et synchronisés entre les machines de développement par le VPS.

#### `CLAUDE.md`

 Les instructions du développeur pour l'assistant ; ce qu'il doit connaître et respecter. Ce fichier est automatiquement lu par Claude Code à chaque lancement.

Exemple de contenu

```
# Présentation du projet
  README.md

# Préférences
  Langue : Français.   Ton : tutoiement.
  TNR (tests de non-régression, sans pytest) : ne jamais committer un
  fichier de test sans un TNR vert juste avant.

# Fichiers partagés (PRV, gérés par CLAUDE)
  CLAUDE_log.md  : sessions récentes (5 dernières).
  CLAUDE_todo.md : idées / plans / dette (conventions en tête du fichier).
  CLAUDE_mem.md  : mémoire durable inter-machines (index + custom/mem/<thème>.md).

# Dépôts (PUB / PRV)
  Deux dépôts par instance : PUB (code app) à la racine, origin GitHub ;
  PRV dans custom/ (origin VPS) = fichiers Claude + sites privés.
  La session démarre dans custom/ ; garder un wd canonique par machine.

# Rituels de session
  Ouverture : ./claude_open.sh (hôte + wd + audit git read-only), charger la mémoire.
  Clôture   : préparer todo/log/mem -> un seul « go » -> commit (git nu) -> aligner.

# Mémoire native (machine-locale)
  ~/.claude/projects/<slug>/memory/ — per-machine, non versionnée, non
  synchronisée ; complète la couche partagée CLAUDE_mem.
```

#### `CLAUDE_log.md`

 journal des sessions récentes (les 5 dernières) :

Exemple de contenu

```
# Session 42 — 2026-01-15 — PC Linux — Connecteur « BanqueX »
## Contexte
Reprise de #17 (nouveau connecteur).
## Enseignements
- Le CSV de BanqueX date en JJ/MM/AAAA → parseur adapté.
## Reste
- Valider sur macOS avant publication.

# Session 43 ...
```

#### `CLAUDE_todo.md`

idées / plans / dette ; ses conventions vivent en tête du fichier :

Exemple de contenu

```
# En tête
Dernier #id attribué : #190  (incrémenter à chaque nouvel item)

Identité : chaque item porte un #NN ; toute référence croisée se fait par #NN.
           Un #id retiré reste mort (jamais réutilisé).
Format   : entête (#NN · titre court) ; détails en sous-bullets.
Purge    : au-delà de ~30 items, élaguer les plus anciens

# Items
#186 Unifier l'écriture du journal.log : date + point d'écriture unique + sortir les tracebacks bruts + journaliser les actions GUI
#187 ...

```

#### `CLAUDE_mem.md`

mémoire durable inter-machines (les faits non évidents à retenir) :

Exemple de contenu

```
- Ne jamais sauvegarder un .xlsm avec openpyxl (corrompt le format) →
  écriture du classeur via LibreOffice/UNO uniquement.
- ...
```
