# Compta — Cohérence *(doc dev)*

Comment Compta reste cohérent dans le temps.

## 1. Introduction

Trois composants Compta évoluent et peuvent se désynchroniser :

- **le classeur** — `comptes.xlsm`, le fichier comptable de l'utilisateur (privé, hors dépôt git) ;
- **l'application** — le code de l'application, dépôt public `git` ;
- **la configuration** — les réglages de l'application (`config.ini`, `config_*.json` ; privés, hors dépôt).

Une mise à jour du code (`git`) fait avancer l'application, mais pas le classeur ni la config : ils peuvent devenir incompatibles. Le code connaît la **valeur attendue** de chaque composant ; le classeur et la config gardent chacun un **marqueur** — un nombre disant jusqu'où ils ont été mis à niveau. **Comparer le marqueur à la valeur attendue dit s'il y a du retard, et s'il est impératif de le combler.**

Trois moments gèrent cette cohérence — **installation**, **upgrade**, **démarrage** — chacun s'appuyant sur les autres.

### Les marqueurs

| Marqueur | Composant | Emplacement |
|---|---|---|
| `SCHEMA_VERSION` | Classeur | NR dans `comptes.xlsm` |
| `config_schema_version` | Configuration | `config.ini` |
| *(aucun)* | Application | git lui-même |

> *Historique : `honored_version`, ancien marqueur d'application, est **retiré** mais laissé commenté dans `config.ini.default` pour ne pas déclencher d'alertes ; le code ne le lit plus.*

La **forme** du marqueur cible indique ce que le démarrage fait :

| Forme | Démarrage | Exemple |
|---|---|---|
| **entier** (`4`) | **bloque** | migration structurelle |
| **décimal** (`3.1`) | **avertit** | rattrapage non-bloquant |
| *(pas de marqueur cible)* | **silencieux** | fix idempotent, appliqué à l'upgrade |

### Le catalogue

Le fichier `upgrade_map.json` recense toutes les mises à niveau. Il contient les versions d'app, les marqueurs associés, les scripts de migration (classeur ou config), etc.

Son contenu est rendu lisible dans `Compta_upgrade_assiste.md` (section *Carte*, bloc généré automatiquement).

## 2. Installation

Prépare une instance neuve : crée la config depuis `config.ini.default` et **pose les marqueurs au niveau courant du code** (lus en direct → toujours justes). Une installation fraîche naît « à jour ».

- *vers le démarrage* : démarre sans alerte ;
- *vers l'upgrade* : ne joue **aucune** mise à niveau (rien à rattraper), juste poser les marqueurs.

## 3. Upgrade

**Le seul moment qui modifie.** Outil recommandé : `upgrade.py`.

> Un `git pull` nu suffit **tant qu'aucune mise à niveau n'est en attente** ; sinon il crée une incohérence — et il échoue si le dépôt doit être re-cloné (historique réécrit). D'où le geste « frais » hors du dossier : voir `Compta_upgrade_assiste.md`.

Déroulé :

1. **Code** — appelle `git pull`, ou re-clone si l'historique git a été réécrit ;
2. **Mises à niveau** — calcule le **chemin** par composant, exécute les outils nécessaires-et-suffisants, avec **sauvegarde** + **consentement** pour le non-anodin, puis **avance les marqueurs**.

**Mécanisme du chemin** (le « comment ») : pour chaque composant, prendre les entrées dont le **marqueur cible** dépasse le **marqueur relevé** de l'instance, jusqu'au **marqueur attendu** (celui du code) ; les entrées **sans marqueur cible** sont rejouées systématiquement (idempotentes).

Les outils sont **autonomes** (lançables seuls : `python3 tool_migrate_… config.ini`) et **rejouables sans risque** → une erreur de catalogue se rattrape à la main ou par une entrée corrective à la version suivante.

- *vers l'install* : l'install a posé les marqueurs de départ ;
- *vers le démarrage* : le démarrage **signale**, l'upgrade **résout**.

## 4. Démarrage (interfaces graphique et ligne de commande)

À chaque lancement l'application **vérifie et alerte — ne met jamais à niveau.** Par composant :

- **Classeur** — lit son **marqueur** dans le `.xlsm` (NR) : si majeur en retard → **bloque** (opérer sur une structure incompatible **abîmerait les données**) ; si mineur en retard → **avertit** sans bloquer.
- **Configuration** — lit son **marqueur** (`config.ini`), même règle (majeur → bloque, mineur → avertit). En pratique les migrations config sont conçues **tolérantes** (le code fonctionne avec une config en retard) → elles sont mineures ou silencieuses, et **bloquent rarement**.
- **App** — l'application n'a pas de marqueur : git porte sa version, elle ne se compare donc à rien (elle *est* le code courant en place). Elle vérifie en revanche les fichiers dont elle dépend — `config.ini`, les `config_*.json` : présence, clés attendues, contenu. Ces contrôles mesurent l'**intégrité** de la config (fichier absent, clé manquante), pas un retard de version ; ils tournent à chaque démarrage, indépendamment des marqueurs.

- *vers l'upgrade* : le démarrage **signale**, l'upgrade **résout** — jamais de mise à niveau ici.

## Glossaire

NR (Named Range) : Nom définissant une cellule ou une plage de cellules
