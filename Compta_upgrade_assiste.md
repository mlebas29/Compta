# Mise à jour (mode assisté)

Avant v5.3.0 la mise à jour était effectuée avec `git pull` et des scripts ad-hoc éventuels de mise à jour de classeur (`tool_migrate_*`) décrits dans `CHANGELOG.md`. Le chemin d'une mise à jour consistait en une succession de `tool_migrate_*` à enchaîner manuellement.

Depuis v5.3.0 un script automatise le chemin pour ces mises à jour classeur et gère la mise à jour de l'app (`git pull`) et les chemins de mise à jour config (paramètres privés de l'app).

Le script `./upgrade.py` est à lancer à la racine du clone. Tout ce qui touche à vos données est **proposé**, avec consentement. Idempotent (un 2ᵉ passage ne refait rien d'inutile).

**Avant toute modification, une sauvegarde est faite** (config, classeur, version du code) : c'est le filet qui rend l'upgrade **réversible** (cf. *Restauration*). Un lancement qui ne change rien ne laisse pas de sauvegarde.

## Séquence de mise à jour

1. **Code** — installe le nouveau code (`git pull`). Si le clone est trop divergent pour une mise à jour normale (réécriture d'historique, badge 🔄), il **propose** un re-clone sûr (`reclone.sh`, avec sauvegarde) au lieu d'échouer.
2. **Config** (idempotent) — normalise la configuration, régénère le raccourci, pose le cadre privé `custom/` s'il manque.
3. **Classeur** (idempotent) — si le classeur est en retard, **propose** la migration sous **consentement** explicite, puis exécute l'outil (`tool_migrate_*`). Refusé si **LibreOffice < 24.8** (qui corromprait les formules).
4. **Signalements** — relève les autres écarts (config obsolète…) sans rien forcer.
5. **Marquage** dans la config du passage du script (`honored_version`) — sert l'avis au démarrage qui signale une mise à niveau attendue mais non honorée.

`./upgrade.py --check` : montre ce qui serait fait, **sans rien appliquer**.

## Restauration

Chaque upgrade qui modifie quelque chose laisse un **point de restauration** (snapshot). Pour revenir en arrière :

```bash
./upgrade.py --liste                  # liste les points : date + version
./upgrade.py --restore <date>         # restaure ce point (code + config + classeur)
./upgrade.py --restore <date> --only xlsm   # un seul composant : xlsm | config | app
```

La restauration **sauvegarde l'état courant d'abord** (elle est donc elle-même réversible) et demande confirmation. Les **10 snapshots** les plus récents sont conservés (les plus anciens sont purgés ; le journal `upgrade_log.jsonl`, lui, garde tout l'historique). Restaurer le seul classeur (`--only xlsm`) le ramène à une version antérieure → l'app le signalera au démarrage (re-migration possible).

## Carte des mises à jour

Ce que chaque version réclame, **dérivé de la carte** `upgrade_map.json` (source unique). Le badge dit l'intention ; sa **nature** dit comment `upgrade` s'y prend (les *cumulatifs* sont rattrapés quel que soit le retard) ; une **butée** 🧱 marque la profondeur où le rattrapage automatique s'arrête (en deçà : manuel).

<!-- bloc généré : ./tool_render_upgrade_map.py --mode assiste — ne pas éditer à la main -->

**Légende des badges** :

> *cumulatif* = `upgrade` rattrape le retard accumulé · *informatif* = aucune action · *ponctuel* = à traiter au moment (pas de rattrapage)

- 🔧 *(cumulatif)* migration de structure du classeur — `upgrade` la propose (consentement + sauvegarde)
- 📘 *(informatif)* contenu : nouveau classeur exemple — votre classeur migré reste en place
- ⚙️ *(cumulatif)* config à normaliser — `upgrade` la normalise (rattrapage)
- 🔄 *(ponctuel)* re-clonage du dépôt (réécriture d'historique git) — re-cloner manuellement (`upgrade` n'existait pas encore)
- 🧱 *(ponctuel)* butée d'automatisation (profondeur de rattrapage) — sous cette ligne le rattrapage automatique s'arrête → contournement manuel (voir la note)

_Axes : **Classeur** = structure & contenu · **Config** = paramètres privés de l'app · **Dépôt** = git, code public_

| Version | Classeur | Config | Dépôt | Outil | Effet |
|---|:--:|:--:|:--:|---|---|
| ⎯ v5.3.0 ⎯ |  |  |  |  | **frontière `upgrade`** : au-dessous, mise à jour **manuelle** (l'outil n'existait pas) |
| v5.2.1 |  | ⚙️ |  | `install_fix.sh` | config normalisée (renommages hérités) |
| v5.1.0 |  |  | 🔄 🧱 | `reclone.sh` | historique git réécrit (squash) — re-clone requis |
| v5.0.1 | 📘 |  |  |  | classeur exemple livré (intègre la migration v5.0.0) |
| v5.0.0 | 🔧 |  |  | `tool_migrate_v5.0.0.py` | fiabilisation alarmes anti-#REF! orphelines |
| v4.1.0 | 📘 🔧 |  |  | `tool_migrate_v4.1.0.py` | refonte CTRL2 + alarmes |
| v4.0.0 | 📘 🔧 |  |  | `tool_migrate_schema_v2.py` | drill devise (élimine les colonnes par devise) |
| ≤ v3.x | 🧱 |  |  |  | schéma < 1 (pré-v3.4) : outils de migration retirés du dépôt git → migration manuelle (ancien mode classeur) |

<!-- fin bloc généré -->

## Comment le script détermine le chemin

`upgrade` ne rejoue pas les versions une à une : il calcule le **chemin de migration du classeur** entre deux numéros de schéma — l'**origine** (le `SCHEMA_VERSION` inscrit dans votre classeur) et la **cible** (celui du code installé) — puis enchaîne les migrateurs qui couvrent l'intervalle.

Exemple — un classeur en **schéma 1** mis à niveau vers un code en **schéma 3** :

| Étape | Migrateur | Schéma |
|---|---|:--:|
| 1 | `tool_migrate_schema_v2.py` | 1 → 2 |
| 2 | `tool_migrate_v4.1.0.py` | 2 → 3 |

Les étapes s'exécutent dans l'ordre, sous consentement et après sauvegarde. Un classeur déjà en schéma 3 n'a aucune étape (rien à faire) ; un classeur en **schéma < 1** est sous la **butée** 🧱 (outils retirés du dépôt git) → migration manuelle, cf. [`Compta_upgrade_classeur.md`](Compta_upgrade_classeur.md).


**2ᵉ exemple — une butée sur un autre axe rallonge le chemin.** Le même classeur en **v4.0.0** est déjà en **schéma 2** : côté classeur, atteindre le code **v5.3.0** (schéma 3) ne demande donc qu'**une** migration (2 → 3). Mais le chemin franchit la **butée app v5.1.0** (réécriture d'historique git) — un simple `git pull` ne la traverse pas → il faut **re-cloner d'abord**. Soit **2 étapes, sur deux axes** :

| Étape | Axe | Geste |
|---|---|---|
| 1 | Dépôt | `reclone.sh` — franchir la butée app v5.1.0 (sinon `git pull` casse) |
| 2 | Classeur | `tool_migrate_v4.1.0.py` — schéma 2 → 3 |

Le `SCHEMA_VERSION` du classeur ne dit donc pas, à lui seul, tout le chemin : une **butée sur un autre axe** (ici le dépôt) ajoute son propre geste, indépendamment du retard de schéma.
