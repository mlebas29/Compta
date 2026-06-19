# Compta — Cohérence *(doc dev)*

Comment Compta reste cohérent dans le temps.
*Modèle figé ; implémentation = #98.*

## 1. Introduction

Trois **périmètres** évoluent et peuvent se désynchroniser :

- **l'application** — le code, dépôt public `git` ;
- **le classeur** — `comptes.xlsm`, le fichier comptable de l'utilisateur (privé, hors dépôt git) ;
- **la configuration** — les réglages (`config.ini`, `config_*.json` ; privés, hors dépôt).

Une mise à jour du code (`git`) fait avancer l'application, mais ni le classeur ni la config : ils peuvent devenir incompatibles. Le code connaît la **valeur attendue** de chaque périmètre ; le classeur et la config gardent chacun un **marqueur** — un nombre disant jusqu'où ils ont été mis à niveau. **Comparer le marqueur à la valeur attendue dit s'il y a du retard, et de quelle gravité.**

Trois moments gèrent cette cohérence — **installation**, **upgrade**, **démarrage** — chacun s'appuyant sur les autres.

### Les marqueurs

| Marqueur | Périmètre | Emplacement | Nature |
|---|---|---|---|
| `SCHEMA_VERSION` | Classeur | NR dans `comptes.xlsm` | la **vraie** valeur (autoritaire) |
| `config_schema_version` | Configuration | `config.ini` | un **repère** posé par l'upgrade |
| *(aucun)* | Application | git lui-même | suivi de version git |

> *Historique : `honored_version`, ancien marqueur unique exprimé en version d'application, est **retiré** — chaque périmètre a son marqueur. Laissé commenté dans `config.ini.default` pour ne pas faire passer les vieilles configs pour bancales ; le code ne le lit plus.*

### Forme du marqueur = gravité

La **forme** de la valeur encode ce que le démarrage en fait :

| Forme | Démarrage | Exemple |
|---|---|---|
| **entier** (`4`) | **bloque** | migration structurelle |
| **décimal** (`3.1`) | **avertit** | rattrapage non-bloquant |
| *(pas de marqueur cible)* | **silencieux** | fix idempotent, appliqué à l'upgrade |

**Présence d'un mineur (`3.1`) = non-bloquant ; absence (`3`) = bloquant.** Comparaison **marqueur relevé** (instance) vs **marqueur attendu** (code) : majeur en retard → bloque ; sinon mineur en retard → avertit ; sinon rien. (`"3"` se lit `(3,0)`.) C'est cette forme qui porte la gravité — pas de champ « bloquant » séparé.

### Le catalogue

`upgrade_map.json` liste les mises à niveau. **Deux familles** d'entrées :

- **avec un marqueur cible** (entier = bloquant · décimal = avertissement) : suivies par le marqueur ;
- **sans marqueur cible** : silencieuses, rejouées à chaque upgrade (idempotentes), hors marqueur.

Trois objets à **ne pas confondre** :

- **catalogue** — statique, *toutes* les mises à niveau → ce fichier + sa version lisible `Compta_upgrade_assiste.md` ;
- **chemin** — ce qu'*une* instance doit faire → `upgrade.py --check` ;
- **mécanisme** — comment le chemin se calcule → §3.

## 2. Installation

Prépare une instance neuve : crée la config depuis `config.ini.default` et **pose les marqueurs au niveau courant du code** (lus en direct → toujours justes). Une install fraîche naît « à jour ».

- *vers le démarrage* : démarre sans alerte ;
- *vers l'upgrade* : ne joue **aucune** mise à niveau (rien à rattraper), juste poser les marqueurs.

## 3. Upgrade

**Le seul moment qui modifie.** Outil recommandé : `upgrade.py`. Un `git pull` nu suffit **tant qu'aucune mise à niveau n'est en attente** ; sinon il crée une incohérence — et il échoue si le dépôt doit être re-cloné (historique réécrit). D'où le geste « frais » hors du dossier : voir `Compta_upgrade_assiste.md`.

Déroulé :

1. **Code** — `git pull`, ou re-clone si l'historique git a été réécrit ;
2. **Mises à niveau** — calcule le **chemin** par périmètre, exécute les outils nécessaires-et-suffisants, avec **sauvegarde** + **consentement** pour le non-anodin, puis **avance les marqueurs**.

**Mécanisme du chemin** (le « comment ») : pour chaque périmètre, prendre les entrées dont le **marqueur cible** dépasse le **marqueur relevé** de l'instance, jusqu'au **marqueur attendu** (celui du code) ; les entrées **sans marqueur cible** sont rejouées systématiquement (idempotentes). `app_version` ne sert qu'au **rendu**, jamais à choisir le chemin.

Les outils sont **autonomes** (lançables seuls : `python3 tool_migrate_… config.ini`) et **rejouables sans risque** → une erreur de catalogue se rattrape à la main ou par une entrée corrective à la version suivante.

- *vers l'install* : l'install a posé les marqueurs de départ ;
- *vers le démarrage* : le démarrage **signale**, l'upgrade **résout**.

## 4. Démarrage (interfaces graphique et ligne de commande)

À chaque lancement : **vérifie et alerte — ne met jamais à niveau.** Par périmètre :

- **Classeur** — lit la **vraie** valeur (NR du `.xlsm`) : majeur en retard → **bloque** (opérer sur une structure incompatible **abîmerait les données**) ; mineur en retard → **avertit** sans bloquer.
- **Configuration** — lit son **marqueur** (`config.ini`), même règle (majeur → bloque, mineur → avertit). En pratique les migrations config sont conçues **tolérantes** (le code fonctionne avec une config en retard) → elles sont mineures (avertissent) ou silencieuses, **rarement bloquantes**.
- **App** — `git` signale le retard (et `tool_audit_git`, côté validateurs seulement) ; résolu par `git pull` / `upgrade`.

**Asymétrie assumée** : le classeur tranche sur sa **vraie** valeur (autoritaire → pas de faux-bloc). La config tranche sur un **repère** : un état bâtard peut donc **faux-avertir** (inoffensif) ou **faux-bloquer** (récupérable par `upgrade`). C'est le prix de ne pas ouvrir un artefact lourd pour la config — acceptable, les blocages config étant rares.

- *vers l'upgrade* : y oriente ; *vers l'install* : install fraîche → silence.

## 5. En cas de pépin

- La **validation du catalogue** attrape avant livraison les oublis (niveau, entrée, outil).
- Côté **config** : pas de dégât (le code tolère le retard) → rattrapage à la version suivante, ou outil relancé à la main.
- Côté **classeur** : sauvegarde (upgrade) + blocage (démarrage) couvrent le risque (restaurer, relancer).
- *Dette connue* : le filet générique qui repère une `config.ini` abîmée **ne regarde pas les `.json`** → une mise à niveau JSON mal cataloguée n'a pas de filet automatique (mais reste sans dégât).
