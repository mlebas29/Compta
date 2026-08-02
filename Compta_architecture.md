# Compta — Architecture de développement avec git & l'IA

> Comment le code et les fichiers de Compta sont organisés en dépôts git, comment ils circulent entre les machines de **développement** et d'**utilisation**, et comment l'assistant IA est utilisé. 
>
> Pour la présentation de l'app, voir [`README.md`](README.md) 



> git est une base de données spécialisée dans le cycle de vie du code d'un projet informatique. Un dépôt git (repository) est matérialisé par un sous-dossier `.git` dans le dossier de l'application.

```
  ┌───────────────────────────────────────────────────────────────┐
  │                          GitHub                               │  https://github.com
  │                           PUB                                 │  Unique dépôt public du projet Compta
  └────┬──────────────────────────────┬────────────────────┬──────┘
       │                              │                    │  
       │                              │                    │
  ┌────┴────────────┐                 │                    │
  │      VPS        │                 │                    │         Serveur privé (hébergement OVH)
  │  PUB  +  PRV    │                 │                    │         2 dépôts (public + privé)
  └──┬───────────┬──┘                 │                    │
     │           │                    │                    │
     │           │                    │                    │
  ┌──┴─────┐ ┌───┴──────────┐  ┌──────┴─────┐  ┌───────────┴───┐
  │MacBook │ │    PC        │  │     PC     │  │ Poste tiers   │    Machines privées
  │PUB+PRV │ │ PUB+PRV      │  │    PUB     │  │    PUB        │    Dépôts public / privés
  └────────┘ └──────────────┘  └────────────┘  └───────────────┘
       Développement                    Utilisation

Le PC fonctionne en dual boot avec une partition Linux et une partition Windows 11 WSL
La partition Linux est elle même duale avec 2 instances Compta, l'une de développement, l'autre d'utilisation
Le VPS a un accès public pour faciliter le nomadisme développement
```

## Dépôts git 

Une machine peut héberger plusieurs instances Compta. Une instance Compta est matérialisée par un répertoire et un raccourci
Chaque instance Compta porte un dépôt PUB et optionnellement un dépôt PRV ; ces deux dépôts git sont indépendants :

| Dépôt | Contenu |
|---|---|
| **PUB** | Code **public** : l'application + les connecteurs de banques publics |
| **PRV** (`custom/`) | Couche **privée** : connecteurs de banques privés, extensions de l'app, données et notes de travail, **fichiers IA** (`CLAUDE*`) |

La séparation garde hors du dépôt public tout ce qui est privé — sites confidentiels, données, notes — sans rien changer au fonctionnement de l'app : au démarrage, le code privé (`custom/`) se superpose au code public (cf. [`Compta_extension.md`](Compta_extension.md)).

## Développement et utilisation

Une instance joue l'un de deux rôles, selon l'`origin` de son dépôt PUB :

- **Développement** — on édite le code et on le valide sur chaque OS. `origin` PUB = le **VPS** (hub privé) ; on **publie** vers GitHub.
- **Utilisation** — l'app tourne, sans édition. `origin` PUB = **GitHub** ; l'instance tire le publié en **lecture seule**, jamais rattaché au hub → **intouchable par le travail en cours**.

**Le circuit.** Les machines de développement convergent sur le **VPS**, où se poussent et se tirent PUB (travail en cours) *et* PRV — c'est là qu'un portage macOS/Windows se valide avant publication. **GitHub ne reçoit que du validé** (`git push github main` + tag) et n'héberge que le **PUB** : le **PRV ne passe jamais par GitHub**, il circule uniquement par le VPS (cloud personnel, pas de service tiers). Les machines d'utilisation tirent le publié (`git pull`).

Seul le **PC Linux** est *dual* — DEV et PROD y cohabitent (deux instances, même machine) pour isoler le vrai classeur de production pendant qu'on développe à côté. MacBook et Windows/WSL sont des postes *mixtes* (ils consomment **et** éditent) ; le poste tiers ne fait que consommer le publié.

## Développement assisté par l'IA

### CLI

Compta est développé avec l'assistant **Claude Code** (CLI d'Anthropic). Cet assistant est installé sur le poste de travail afin de pouvoir lire et modifier ou exécuter sous contrôle utilisateur.

Le CLI peut fonctionner dans un terminal Linux ordinaire (claude) ou dans une App (claude-desktop)

 voir [claude.com/claude-code](https://claude.com/claude-code) pour l'installer.

### Mémoire

L'état de collaboration — conventions de travail et mémoire de l'assistant — vit dans des fichiers **`CLAUDE*`** du dépôt **PRV** (jamais publiés), synchronisés entre les machines de développement par le VPS.

→ Présentation détaillée, contenu du fichier d'instructions et exemples anonymisés : [`Compta_CLAUDE.md`](Compta_CLAUDE.md).

