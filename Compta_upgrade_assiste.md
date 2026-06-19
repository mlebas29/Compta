# Mise à jour (mode assisté)

> **⚠️ Changement de méthode — depuis v5.3.0.** La mise à jour assistée se fait désormais avec `upgrade.py`. Ce **geste unique** remplace les anciennes procédures (`git pull` + scripts `tool_migrate_*` enchaînés à la main, re-clone manuel) et fonctionne **quelle que soit votre version de départ** — il met à jour automatiquement les versions antérieures à v5.1.0, dont l'historique git a été réécrit. **Si une doc d'une version antérieure décrit une autre procédure, préférez lui celle-ci.**

```bash
# Depuis un terminal: télécharger puis lancer upgrade.py.
curl -fsSL https://github.com/mlebas29/Compta/raw/main/upgrade.py -o /tmp/upgrade.py
python3 /tmp/upgrade.py ~/Compta
# ~/Compta à remplacer éventuellement par le dossier réellement utilisé
```

Tout ce qui touche à vos données est **proposé**, avec consentement. Idempotent (un 2ᵉ passage ne refait rien d'inutile).

**Avant toute modification, une sauvegarde est faite** (config, classeur, version du code) : c'est le filet qui rend l'upgrade **réversible** (cf. *Restauration*). Un lancement qui ne change rien ne laisse pas de sauvegarde.



## Séquence de mise à jour

1. **Code** — `git pull`. Si le clone est trop ancien pour un pull (historique réécrit, clone antérieur à v5.1.0), il **propose** (consentement) un re-clone sûr : sauvegarde complète + clone frais **préservant** `custom/` et la configuration.
2. **Config** (idempotent) — normalise la configuration, régénère le raccourci, pose le cadre privé `custom/` s'il manque.
3. **Classeur** (idempotent) — si le classeur est en retard, **propose** la migration sous **consentement** explicite, puis exécute l'outil (`tool_migrate_*`). Refusé si **LibreOffice < 24.8** (qui corromprait les formules).
4. **Signalements** — relève les autres écarts (config obsolète…) sans rien forcer.
5. **Marquage** du niveau atteint, par périmètre (marqueurs de schéma — classeur et config) — sert l'avis au démarrage, qui signale (ou bloque) une mise à niveau en attente.

`upgrade.py --check` : montre ce qui serait fait, **sans rien appliquer**.

## Restauration

Chaque upgrade qui modifie quelque chose laisse un **point de restauration** (snapshot). Pour revenir en arrière :

```bash
python3 /tmp/upgrade.py ~/Compta --liste              # liste les points : date + version
python3 /tmp/upgrade.py ~/Compta --restore <date>     # restaure ce point (code + config + classeur)
python3 /tmp/upgrade.py ~/Compta --restore <date> --only xlsm   # un seul composant : xlsm | config | app
```

La restauration **sauvegarde l'état courant d'abord** (elle est donc elle-même réversible) et demande confirmation. Les **10 snapshots** les plus récents sont conservés (les plus anciens sont purgés ; le journal `upgrade_log.jsonl`, lui, garde tout l'historique). Restaurer le seul classeur (`--only xlsm`) le ramène à une version antérieure → l'app le signalera au démarrage (re-migration possible).

> **Restauration tardive.** Si le `/tmp/upgrade.py` téléchargé n'est plus là (reboot), le clone porte aussi le script — `python3 ~/Compta/upgrade.py ~/Compta --restore <date>`. Le restore ne re-clone pas → le lancer depuis le clone est toléré, inutile de re-télécharger.

## Carte des mises à jour

**Inventaire** de ce que chaque version apporte, par périmètre (**dérivé de `upgrade_map.json`**, source unique) — c'est le **catalogue**, *pas votre chemin* : celui-ci dépend de votre instance, `upgrade.py --check` le montre. Le badge dit l'intention ; une **butée** 🧱 marque la profondeur où le rattrapage automatique s'arrête (en deçà : manuel).

<!-- bloc généré : ./tool_render_upgrade_map.py --mode assiste — ne pas éditer à la main -->
**Légende des badges** :

> *cumulatif* = `upgrade` rattrape le retard accumulé · *informatif* = aucune action · *ponctuel* = à traiter au moment (pas de rattrapage)

- 🔧 *(cumulatif)* migration de structure du classeur — `upgrade` la propose (consentement + sauvegarde)
- 📘 *(informatif)* contenu : nouveau classeur exemple — votre classeur migré reste en place
- ⚙️ *(cumulatif)* config à normaliser — `upgrade` la normalise (rattrapage)
- 🔄 *(ponctuel)* re-clonage du dépôt (réécriture d'historique git) — `upgrade` re-clone automatiquement (sauvegarde + consentement)
- 🧱 *(ponctuel)* butée d'automatisation (profondeur de rattrapage) — profondeur où le rattrapage automatique s'arrête → recréer le classeur depuis le template (cf. Compta_upgrade_classeur.md)

_Axes : **Classeur** = structure & contenu · **Config** = paramètres privés de l'app · **App** = code public (dépôt git)_

| Version | Classeur | Config | App | Outil | Effet |
|---|:--:|:--:|:--:|---|---|
| v5.8.3 |  | ⚙️ |  | `tool_migrate_config_cotations.py` | config_cotations.json dépollué : famille/décimales retirées (source unique = feuille Cotations) |
| v5.7.0 |  | ⚙️ |  | `tool_migrate_config_xmr.py` | [XMR] migré vers collecte par nœud distant (wallet-rpc) — site désactivé, reconfiguration + credential GPG requis (cf. Compta_xmr.md) |
| v5.2.1 |  | ⚙️ |  | `install_fix.sh` | config normalisée (renommages hérités) |
| v5.1.0 |  |  | 🔄 | `reclone.sh` | historique git réécrit (squash) — re-clone automatique par upgrade |
| v5.0.1 | 📘 |  |  |  | classeur exemple livré (intègre la migration v5.0.0) |
| v5.0.0 | 🔧 |  |  | `tool_migrate_v5.0.0.py` | fiabilisation alarmes anti-#REF! orphelines |
| v4.1.0 | 📘 🔧 |  |  | `tool_migrate_v4.1.0.py` | refonte CTRL2 + alarmes |
| v4.0.0 | 📘 🔧 |  |  | `tool_migrate_schema_v2.py` | drill devise (élimine les colonnes par devise) |
| ≤ v3.x | 🧱 |  |  |  | schéma < 1 (pré-v3.4) : outils de migration retirés du dépôt git → migration manuelle (ancien mode classeur) |

<!-- fin bloc généré -->

## Comment le script détermine le chemin

Le « chemin » peut toucher trois axes — **classeur**, **config**, **app** — et chacun se détermine différemment.

**Côté classeur**, `upgrade` ne rejoue pas les versions une à une : il calcule le **chemin de migration** entre deux numéros de schéma — l'**origine** (le `SCHEMA_VERSION` inscrit dans votre classeur) et la **cible** (celui du code installé) — puis enchaîne les migrateurs qui couvrent l'intervalle.

**Côté config**, il n'y a pas de numéro de schéma à comparer : `upgrade` ne calcule pas d'intervalle. À la place, chaque migration de config **vérifie l'état réel** de votre `config.ini` et ne le **met en conformité que si besoin** (sinon elle n'y touche pas). Elles sont donc toutes repassées à chaque mise à jour, mais une config déjà à jour reste **intacte**.

**Côté app**, ni numéro de version ni script dédié : c'est l'**état réel du dépôt git** qui tranche. `upgrade` tente un `git pull` ; s'il avance normalement, rien de plus. Mais si l'**historique a été réécrit** (un `git pull` ne peut pas le traverser), il **re-clone** l'installation — sauvegarde + consentement — c'est la 🔄 (ex. v5.1.0).

Exemple — un classeur en **schéma 1** mis à niveau vers un code en **schéma 3** :

| Étape | Migrateur | Schéma |
|---|---|:--:|
| 1 | `tool_migrate_schema_v2.py` | 1 → 2 |
| 2 | `tool_migrate_v4.1.0.py` | 2 → 3 |

Les étapes s'exécutent dans l'ordre, sous consentement et après sauvegarde. Un classeur déjà en schéma 3 n'a aucune étape (rien à faire) ; un classeur en **schéma < 1** est sous la **butée** 🧱 (outils retirés du dépôt git) → migration manuelle, cf. [`Compta_upgrade_classeur.md`](Compta_upgrade_classeur.md).

**2ᵉ exemple — un événement sur un autre axe rallonge le chemin.** Le même classeur en **v4.0.0** est déjà en **schéma 2** : côté classeur, atteindre **v5.3.0** (schéma 3) ne demande qu'**une** migration (2 → 3). Mais le chemin franchit la **réécriture d'historique git de v5.1.0** (axe App, 🔄) qu'un `git pull` ne traverse pas → `upgrade` **re-clone automatiquement** (sauvegarde + consentement) avant de migrer. Soit **2 étapes, sur deux axes** :

| Étape | Axe | Geste (par `upgrade`) |
|---|---|---|
| 1 | App | re-clone — réécriture d'historique v5.1.0 qu'un `git pull` ne traverse pas |
| 2 | Classeur | `tool_migrate_v4.1.0.py` — schéma 2 → 3 |

Le `SCHEMA_VERSION` ne dit donc pas, à lui seul, tout le chemin : un **événement sur un autre axe** (l'app) ajoute son geste — `upgrade` enchaîne les deux.
