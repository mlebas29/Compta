# Mise à jour (mode assisté)

Avant V5.3.0 la mise à jour était effectuée avec git pull et des scripts ad-hoc éventuels de mise à jour de classeur (tool_migrate*) décrits dans CHANGELOG.md . Le chemin d'une mise à jour consistait en une succession de tool_migrate

Depuis V5.3.0 un script automatise le chemin pour ces mises à jour classeur et gère la mise à jour de l'app (git pull) et les chemins de mise à jour config (paramètres privés de l'app)

Le script, `./upgrade.py` est à lancer à la racine du clone. Tout ce qui touche à vos données est **proposé**, avec consentement. Idempotent (un 2ᵉ passage ne refait rien d'inutile).

**Avant toute modification, une sauvegarde est faite** (config, classeur, version du code) : c'est le filet qui rend l'upgrade **réversible** (cf. *Restauration*). Un lancement qui ne change rien ne laisse pas de sauvegarde.

## Séquence de mise à jour

1. **Code** — installe le nouveau code (`git pull`). Si le clone est trop divergent pour une mise à jour normale (réécriture d'historique, badge 🔄), il **propose** un re-clone sûr (`reclone.sh`, avec sauvegarde) au lieu d'échouer.
2. **Config** (idempotent) — normalise la configuration, régénère le raccourci, pose le cadre privé `custom/` s'il manque.
3. **Classeur** (idempotent)— si le classeur est en retard, **propose** la migration sous **consentement** explicite, puis exécute l'outil (`tool_migrate_*`). Refusé si **LibreOffice < 24.8** (qui corromprait les formules).
4. **Signalements** — relève les autres écarts (config obsolète…) sans rien forcer.
5. Marquage dans Config du passage du script (honored)

`./upgrade.py --check` : montre ce qui serait fait, **sans rien appliquer**.

## Restauration

Chaque upgrade qui modifie quelque chose laisse un **point de restauration** (snapshot). Pour revenir en arrière :

```bash
./upgrade.py --liste                  # liste les points : date + version
./upgrade.py --restore <date>         # restaure ce point (code + config + classeur)
./upgrade.py --restore <date> --only xlsm   # un seul composant : xlsm | config | app
```

La restauration **sauvegarde l'état courant d'abord** (elle est donc elle-même réversible) et demande confirmation. Les **10 snapshots** les plus récents sont conservés (les plus anciens sont purgés ; le journal `upgrade_log.jsonl`, lui, garde tout l'historique). Restaurer le seul classeur (`--only xlsm`) le ramène à une version antérieure → l'app le signalera au démarrage (re-migration possible).



## Carte des mises à jour depuis v4.0.0 (?)

Ce que chaque version réclame est **décrit par cette carte**. Le badge dit l'intention ; sa **nature** dit comment `upgrade` s'y prend (les badges *cumulatifs* sont rattrapés quel que soit le retard).

**Légende des badges**  :

> *cumulatif* = `upgrade` rattrape le retard accumulé · *informatif* = aucune action · *ponctuel* = à traiter au moment (pas de rattrapage)

- 🔧 *(cumulatif)* migration de structure du classeur — `upgrade` la propose (consentement + sauvegarde)
- 📘 *(informatif)* contenu : nouveau classeur exemple — votre classeur migré reste en place
- ⚙️ *(cumulatif)* config à normaliser — `upgrade` la normalise (rattrapage)
- 🔄 *(ponctuel)* re-clonage du dépôt (réécriture d'historique git) — re-cloner manuellement (`upgrade` n'existait pas encore)

### Classeur (structure & contenu)

| Version | Badges | Effet                                                |
| ------- | ------ | ---------------------------------------------------- |
| v4.0.0  | 📘 🔧    | drill devise (élimine les colonnes par devise)       |
| v4.1.0  | 📘 🔧    | refonte CTRL2 + alarmes                              |
| v5.0.0  | 🔧      | fiabilisation alarmes anti-#REF! orphelines          |
| v5.0.1  | 📘      | classeur exemple livré (intègre la migration v5.0.0) |

### Config (paramètres privés de l'app)

| Version | Badges | Effet                                  |
| ------- | ------ | -------------------------------------- |
| v5.2.1  | ⚙️      | config normalisée (renommages hérités) |

### Dépôt (git, code public)

| Version | Badges | Effet                                             |
| ------- | ------ | ------------------------------------------------- |
| v5.1.0  | 🔄      | historique git réécrit (squash) — re-clone requis |



###### Comment le script détermine le chemin ,exemple de chemin Vs nom du tool

Badge + pour indiquer une action manuelle supplémentaire au standard (git pull primitif ou upgrade)
