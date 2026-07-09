# Mise à jour (mode assisté)

## Méthode

La mise à jour de l'application, de ses réglages et du classeur se fait désormais avec `upgrade.py`. Ce geste unique :

- remplace les anciennes procédures (`git pull` + scripts `tool_migrate_*` enchaînés à la main, re-clone manuel) ;
- met à jour automatiquement les **marqueurs** de chaque composant (cf. la *Carte* ci-dessous).

L'outil est :

- **réversible** : avant toute modification, une sauvegarde est faite (config, classeur, version du code). Un lancement qui ne change rien ne laisse pas de sauvegarde.
- **idempotent** : un 2ᵉ passage ne refait rien d'inutile.

Deux façons de le lancer (A distante, B locale) ; une échappatoire manuelle pour le dépannage ou le **cas trivial** (`git pull` suffit : pas de badge, ni outil, ni marqueur).

### A — Méthode distante

Cette méthode fonctionne **pour toutes les versions**, même celles qui ne disposent pas encore de l'outil localement (avant v5.3.0). **Si une doc d'une version antérieure décrit une autre procédure, préférez celle-ci.**

```bash
# Depuis un terminal : télécharger puis lancer upgrade.py.
curl -fsSL https://github.com/mlebas29/Compta/raw/main/upgrade.py -o /tmp/upgrade.py
python3 /tmp/upgrade.py ~/Compta
# ~/Compta à remplacer éventuellement par le dossier réellement utilisé
```

### B — Méthode locale

Depuis v5.3.0, `upgrade.py` est présent dans le dossier Compta et se lance comme les autres outils.

```bash
# Depuis un terminal : lancer upgrade.py présent dans le dossier.
python3 upgrade.py .
```

Plus simple ; et si la mise à jour exige un **re-clone 🔄** (historique git réécrit), l'outil **s'arrête proprement** et renvoie vers la méthode A — il ne fait jamais un re-clone à moitié.

## Séquence de mise à jour

1. **Code** — `git pull`. Si le clone est trop ancien pour un pull (historique réécrit, clone antérieur à v5.1.0), il **re-clone automatiquement** : sauvegarde complète conservée + clone frais **préservant** `custom/` et la configuration. (Seule contrainte : lancer `upgrade.py` **hors** du dossier mis à jour — cf. le geste `/tmp` en tête.)
2. **Config** (idempotent) — applique les migrations de config en attente, normalise la configuration, régénère le raccourci, pose le cadre privé `custom/` s'il manque.
3. **Classeur** (idempotent) — si le classeur est en retard, **applique automatiquement** la migration (`tool_migrate_*`) après sauvegarde. Refusé si le classeur est **ouvert** (ou l'application en cours), ou si **LibreOffice < 24.8** (qui corromprait les formules).
4. **Signalements** — relève les autres écarts (config obsolète…) sans rien forcer.
5. **Marquage** du niveau atteint, par composant (marqueurs de schéma — classeur et config) — sert l'avis au démarrage, qui signale (ou bloque) une mise à niveau en attente.

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

**Inventaire** de ce que chaque version apporte, par composant (**dérivé de `upgrade_map.json`**, source unique) — c'est le **catalogue**, *pas votre chemin* : celui-ci dépend de votre instance, `upgrade.py --check` le montre. Le badge dit l'intention ; une **butée** 🧱 marque la profondeur où le rattrapage automatique s'arrête (en deçà : manuel).

<!-- bloc généré : ./tool_render_upgrade_map.py --mode assiste — ne pas éditer à la main -->

**Légende des badges** :

> *cumulatif* = `upgrade` rattrape le retard accumulé · *informatif* = aucune action · *ponctuel* = à traiter au moment (pas de rattrapage)

- 🔧 *(cumulatif)* migration de structure du classeur — `upgrade` l'applique automatiquement (sauvegarde préalable → réversible)
- 📘 *(informatif)* contenu : nouveau classeur exemple — votre classeur migré reste en place
- ⚙️ *(cumulatif)* config à normaliser — `upgrade` la normalise (rattrapage)
- 🔄 *(ponctuel)* re-clonage du dépôt (réécriture d'historique git) — `upgrade` re-clone automatiquement (sauvegarde complète → réversible)
- 🧱 *(ponctuel)* butée d'automatisation (profondeur de rattrapage) — profondeur où le rattrapage automatique s'arrête → recréer le classeur depuis le template (cf. Compta_upgrade_classeur.md)

_Composants : **Classeur** = structure & contenu · **Config** = paramètres privés de l'app · **App** = code public (dépôt git)_

_Le **nombre** dans la colonne d’un composant = le marqueur de schéma que la mise à jour pose pour CE composant (Classeur ou Config). Sa **forme** porte la gravité au démarrage — **entier** (`3`) bloque (structure incompatible), **décimal** (`0.2`) avertit ; **aucun** = silencieux (rejoué, sans alerte). Cf. `Compta_coherence.md`._

| Version | Classeur | Config | App | Outil | Effet |
|---|:--:|:--:|:--:|---|---|
| v5.16.0 | 🔧 📘 `3` |  |  | `tool_migrate_add_legende_soldes.py` | légende des libellés #Solde (Relevé / Σ / ⚠ Solde calculé) dans la table conventions |
| v5.14.1 | 🔧 `3` |  |  | `tool_migrate_pvl_min_ancrage.py` | ancrage PVL au premier #Solde (MIN, fin du re-ancrage mort) |
| v5.14.1 | 📘 |  |  |  | classeur exemple livré (intègre la migration pvl_min_ancrage) |
| v5.9.0 |  | ⚙️ `0.2` |  | `tool_migrate_config_cotations.py` | config_cotations.json dépollué : famille/décimales retirées (source unique = feuille Cotations) |
| v5.7.0 |  | ⚙️ `0.1` |  | `tool_migrate_config_xmr.py` | [XMR] migré vers collecte par nœud distant (wallet-rpc) — site désactivé, reconfiguration + credential GPG requis (cf. Compta_xmr.md) |
| v5.1.0 |  |  | 🔄 | `reclone.sh` | historique git réécrit (squash) — re-clone automatique par upgrade |
| v5.0.1 | 📘 |  |  |  | classeur exemple livré (intègre la migration v5.0.0) |
| v5.0.0 | 🔧 `3` |  |  | `tool_migrate_v5.0.0.py` | fiabilisation alarmes anti-#REF! orphelines |
| v4.1.0 | 📘 🔧 `3` |  |  | `tool_migrate_v4.1.0.py` | refonte CTRL2 + alarmes |
| v4.0.0 | 📘 🔧 `2` |  |  | `tool_migrate_schema_v2.py` | drill devise (élimine les colonnes par devise) |
| ≤ v3.x | 🧱 |  |  |  | schéma < 1 (pré-v3.4) : outils de migration retirés du dépôt git → migration manuelle (ancien mode classeur) |

_**À chaque mise à jour**, `upgrade` vérifie aussi (et corrige si nécessaire — idempotent, hors gate de version) : ⚙️ normalisation de la config (renommages hérités) · raccourci de lancement (régénéré si le lanceur a changé) · cadre privé custom/ (dépôt git vide) — rattrapage des installs antérieures à v5.3.0._

<!-- fin bloc généré -->

## Comment le script détermine le chemin

Le « chemin » peut toucher trois composants — **classeur**, **config**, **app** — et chacun se détermine différemment.

**Côté classeur**, `upgrade` ne rejoue pas les versions une à une : il calcule le **chemin de migration** entre deux numéros de schéma — l'**origine** (le `SCHEMA_VERSION` inscrit dans votre classeur) et la **cible** (celui du code installé) — puis enchaîne les migrateurs qui couvrent l'intervalle.

**Côté config**, même principe : un marqueur de schéma (`config_schema_version`, inscrit dans votre `config.ini`) donne l'**origine**, le code donne la **cible**, et `upgrade` joue les migrations de config qui couvrent l'intervalle. S'y ajoute une **vérification générique**, toujours active, qui remet en conformité les réglages obsolètes (renommages hérités…) sans dépendre du marqueur — une config déjà à jour reste **intacte**.

**Côté app**, ni numéro de version ni script dédié : c'est l'**état réel du dépôt git** qui tranche. `upgrade` tente un `git pull` ; s'il avance normalement, rien de plus. Mais si l'**historique a été réécrit** (un `git pull` ne peut pas le traverser), il **re-clone automatiquement** l'installation — sauvegarde complète conservée — c'est la 🔄 (ex. v5.1.0).

Exemple — un classeur en **schéma 1** mis à niveau vers un code en **schéma 3** :

| Étape | Migrateur | Schéma |
|---|---|:--:|
| 1 | `tool_migrate_schema_v2.py` | 1 → 2 |
| 2 | `tool_migrate_v4.1.0.py` | 2 → 3 |

Les étapes s'exécutent dans l'ordre, automatiquement, après sauvegarde. Un classeur déjà en schéma 3 n'a aucune étape (rien à faire) ; un classeur en **schéma < 1** est sous la **butée** 🧱 (outils retirés du dépôt git) → migration manuelle, cf. [`Compta_upgrade_classeur.md`](Compta_upgrade_classeur.md).

**2ᵉ exemple — un événement sur un autre composant rallonge le chemin.** Le même classeur en **v4.0.0** est déjà en **schéma 2** : côté classeur, atteindre **v5.3.0** (schéma 3) ne demande qu'**une** migration (2 → 3). Mais le chemin franchit la **réécriture d'historique git de v5.1.0** (composant App, 🔄) qu'un `git pull` ne traverse pas → `upgrade` **re-clone automatiquement** (sauvegarde complète conservée) avant de migrer. Soit **2 étapes, sur deux composants** :

| Étape | Composant | Geste (par `upgrade`) |
|---|---|---|
| 1 | App | re-clone — réécriture d'historique v5.1.0 qu'un `git pull` ne traverse pas |
| 2 | Classeur | `tool_migrate_v4.1.0.py` — schéma 2 → 3 |

Le `SCHEMA_VERSION` ne dit donc pas, à lui seul, tout le chemin : un **événement sur un autre composant** (l'app) ajoute son geste — `upgrade` enchaîne les deux.
