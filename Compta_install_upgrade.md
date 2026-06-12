# `install_upgrade.py` — mise à jour (mode assisté)

En mode assisté, `./install_upgrade.py` (à lancer à la racine du clone) met à niveau l'installation — **code et classeur** — en **un seul geste**. Pour la liste des changements par version : `CHANGELOG.md` ; pour le détail des **migrations du classeur** : [`Compta_upgrade.md`](Compta_upgrade.md).

Principe : il ne fait **jamais rien en silence** — tout ce qui touche vos données est **proposé**, avec consentement. Idempotent (un 2ᵉ passage ne refait rien d'inutile).

**Avant toute modification, un snapshot complet est pris** (config, classeur, version du code) : c'est le filet qui rend l'upgrade **réversible** (cf. *Restauration*). Un lancement qui ne change rien ne laisse pas de snapshot.

## Séquence

1. **Code** — tire le nouveau code (`git pull`). Si le clone est trop divergent pour une mise à jour normale (réécriture d'historique, badge 🔄), il **propose** un re-clone sûr (`reclone.sh`, avec sauvegarde) au lieu d'échouer.
2. **Rattrapages automatiques** (bénins, idempotents) — normalise la configuration, régénère le raccourci, pose le cadre privé `custom/` s'il manque.
3. **Classeur** — si le classeur est en retard, **propose** la migration sous **consentement** explicite, puis exécute l'outil (`tool_migrate_*`). Refusé si **LibreOffice < 24.8** (qui corromprait les formules). Détail des migrations : [`Compta_upgrade.md`](Compta_upgrade.md).
4. **Signalements** — relève les autres écarts (config obsolète…) sans rien forcer.

`./install_upgrade.py --check` : montre ce qui serait fait, **sans rien appliquer**.

## Carte des mises à jour

Ce que chaque version a réclamé, **dérivé de la carte** `upgrade_map.json` (source unique ; régénérer : `./tool_render_upgrade_map.py --mode assiste`). Le badge dit l'intention ; sa **nature** dit comment `install_upgrade` s'y prend (les badges *cumulatifs* sont rattrapés quel que soit le retard).

**Légende des badges** (geste en mode assiste) :

> *cumulatif* = `install_upgrade` rattrape le retard accumulé · *informatif* = aucune action · *ponctuel* = à traiter au moment (pas de rattrapage)

- 🔧 *(cumulatif)* migration de structure du classeur — `install_upgrade` la propose (consentement + sauvegarde)
- 📘 *(informatif)* contenu : nouveau classeur exemple — votre classeur migré reste en place
- ⚙️ *(cumulatif)* config à normaliser — `install_upgrade` la normalise (rattrapage `install_fix`)
- 🔄 *(ponctuel)* re-clonage du dépôt (réécriture d'historique git) — re-cloner manuellement (`install_upgrade` n'existait pas encore)

### Classeur (structure & contenu)

| Version | Badges | Effet |
|---|---|---|
| v4.0.0 | 📘 🔧 | drill devise (élimine les colonnes par devise) |
| v4.1.0 | 📘 🔧 | refonte CTRL2 + alarmes |
| v5.0.0 | 🔧 | fiabilisation alarmes anti-#REF! orphelines |
| v5.0.1 | 📘 | classeur exemple livré (intègre la migration v5.0.0) |

### Config

| Version | Badges | Effet |
|---|---|---|
| v5.2.1 | ⚙️ | config normalisée (renommages hérités) |

### Dépôt (git)

| Version | Badges | Effet |
|---|---|---|
| v5.1.0 | 🔄 | historique git réécrit (squash) — re-clone requis |

## Restauration

Chaque upgrade qui modifie quelque chose laisse un **point de restauration** (snapshot). Pour revenir en arrière :

```bash
./install_upgrade.py --liste                  # liste les points : date + version
./install_upgrade.py --restore <date>         # restaure ce point (code + config + classeur)
./install_upgrade.py --restore <date> --only xlsm   # un seul composant : xlsm | config | app
```

La restauration **sauvegarde l'état courant d'abord** (elle est donc elle-même réversible) et demande confirmation. Les **10 snapshots** les plus récents sont conservés (les plus anciens sont purgés ; le journal `upgrade_log.jsonl`, lui, garde tout l'historique). Restaurer le seul classeur (`--only xlsm`) le ramène à une version antérieure → l'app le signalera au démarrage (re-migration possible).
