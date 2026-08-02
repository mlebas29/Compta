# Compta — Développement assisté par l'IA

> Comment Compta est développé avec l'assistant **Claude Code** : les fichiers `CLAUDE*` (conventions de travail + mémoire) et leur contenu. Pour la vue d'ensemble de l'architecture de développement, voir [`Compta_architecture.md`](Compta_architecture.md).

## Les fichiers `CLAUDE*`

L'état de collaboration vit dans des fichiers **`CLAUDE*`**, versionnés dans le dépôt **PRV** (`custom/`, jamais publiés) et synchronisés entre les machines de développement par le VPS. Contenu et extraits **anonymisés** ci-dessous.

### `CLAUDE.md`

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

### `CLAUDE_log.md`

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

### `CLAUDE_todo.md`

idées / plans / dette ; ses conventions vivent en tête du fichier :

Exemple de contenu

```
# En tête
Dernier #id attribué : #190  (incrémenter à chaque nouvel item)

Identité : chaque item porte un #NN ; toute référence croisée se fait par #NN.
           Un #id retiré reste mort (jamais réutilisé).
Format   : entête (#NN · badge éventuel · titre court) ; détails en sous-bullets.
Purge    : au-delà de ~30 items, élaguer les plus anciens

# Items
#186 Unifier l'écriture du journal.log : date + point d'écriture unique + sortir les tracebacks bruts + journaliser les actions GUI
#187 ...

```

### `CLAUDE_mem.md`

mémoire durable inter-machines (les faits non évidents à retenir) :

Exemple de contenu

```
- Ne jamais sauvegarder un .xlsm avec openpyxl (corrompt le format) →
  écriture du classeur via LibreOffice/UNO uniquement.
- ...
```
