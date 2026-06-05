# Compta [EX]

**Comptabilité familiale — classeur Excel/LibreOffice + application d'assistance**

## 1. Présentation

Compta est un projet de comptabilité familiale ; il a deux composants :

1. Un **classeur** structuré avec des données brutes et de synthèse
2. Une **application d'assistance** qui
   - gère les structures du classeur
   - collecte les données brutes, depuis des sites financiers vers le classeur

> Le suffixe **[EX]** désigne la version *export* : le code public d'un projet conçu pour accueillir des extensions de sites (voir [Extensibilité](#8-extensibilité)).


| Mode classeur | Mode assisté |
|:---:|:---:|
| ![Mode classeur](images/mode_classeur.png) | ![Mode assisté](images/mode_assiste.png) |

### Mode classeur

Le classeur `comptes.xlsm` est utilisable seul avec toute application compatible Excel. L'utilisateur importe manuellement les données financières (xls, PDF, zip, txt, html, CSV) et gère lui-même ses avoirs, comptes, devises, catégories, portefeuilles, etc.

**→ Ce mode convient pour une comptabilité simple, peu diversifiée.**

### Mode assisté

L'application graphique s'intercale entre le classeur et les sites financiers.

L'utilisateur peut vouloir une assistance complète ou partielle (soit configuration, soit collecte).

Ce mode supporte les interventions manuelles dans le classeur. Par exemple pour ajouter, supprimer ou modifier des opérations ou des biens. L'important est de conserver les éléments structurants (tableaux, en-têtes, pieds, formules ...)

**→ Ce mode convient pour une comptabilité diversifiée.**

Les environnements supportés sont : **Linux**, **MacOS**, **Windows 11**, dans tous les cas avec **LibreOffice** pour le classeur.

### Capture d'écran

![](images/Compta.png)



## 2. Fonctions

Le classeur :

- **centralise** dans un format unique les opérations, les avoirs bancaires et biens matériels
- **contrôle** les données saisies, leur cohérence
- présente une feuille **patrimoine**
- présente une feuille **plus/moins-values latentes**
- présente une feuille **budget**

L'application graphique automatise :

- **Collecte** des données depuis les sites bancaires et financiers (via Playwright/Chrome)
- **Import** des opérations collectées dans le tableur (déduplication automatique)
- **Catégorisation** automatique des opérations par pattern matching (regex)
- **Appariement** des opérations liées (virements, changes, achats de titres)
- **Cotations** des devises, cryptomonnaies et métaux précieux

et aussi :

- **Configuration** du tableur : création/modification/suppression des comptes, devises, titres, catégories, postes budgétaires
- **Configuration** des paramètres de collecte



## 3. Installation

|  | Mode classeur | Mode assisté |
|---|:-:|:-:|
| **Prérequis** | Excel ou équivalent (1) | Linux ou MacOS ou Windows 11 |
| **Livré** | Classeur avec données d'exemple | Classeur vierge + application |
| **Action** | Télécharger [`comptes_exemple.xlsx`](https://github.com/mlebas29/Compta/raw/main/comptes_exemple.xlsx) | Tout télécharger et installer |

(1) Doit supporter les nouvelles fonctions XLOOKUP.

Le principe est de télécharger via `git` et d'utiliser un outil d'installation idempotent, c'est-à-dire réutilisable plusieurs fois jusqu'à installation complète au cas où une intervention manuelle serait requise.

Pour **Linux**, le shell script `install.sh` installe les dépendances Python, le navigateur Playwright/Chrome, et le raccourci bureau. Il installe ou met à niveau automatiquement **LibreOffice ≥ 24.8**. En cas de prérequis manquant, il indique la commande d'installation de package correspondante. Après quoi il suffira de relancer le script.

```bash
sudo apt update && sudo apt install -y git
git clone https://github.com/mlebas29/Compta.git ~/Compta
cd ~/Compta && ./install.sh
# Compta peut être remplacé par un autre nom
```

Pour **Windows 11** c'est la même procédure, après avoir installé WSL2 qui permet de faire tourner Linux sur Windows sans machine virtuelle à gérer : voir [Compta_portage.md](Compta_portage.md)

Pour **MacOS** la procédure est plus spécifique, avec une installation manuelle de **LibreOffice 24.8** : Voir [Compta_portage.md](Compta_portage.md)




## 4. Mise à jour

Les évolutions sont tracées sur GitHub dans :

- [`CHANGELOG.md`](https://github.com/mlebas29/Compta/blob/main/CHANGELOG.md) : consigne les changements entre versions
- [`Compta_upgrade.md`](https://github.com/mlebas29/Compta/blob/main/Compta_upgrade.md) : procédures classeur éventuelles attachées aux versions

|                        Mode classeur                         | Mode assisté |
| :----------------------------------------------------------: | :-----------: |
| Télécharger  [`comptes_exemple.xlsx`](https://github.com/mlebas29/Compta/raw/main/comptes_exemple.xlsx) | `git pull` (*) |
| Consulter la procédure classeur éventuelle | Consulter la procédure classeur éventuelle |

**(*)**  à exécuter depuis le répertoire d'installation, met à jour l'application mais pas le classeur `comptes.xlsm` (qui contient vos données). En cas d'évolution du classeur, l'application le signale au démarrage



## 5. Documentation

La documentation est organisée autour de deux points d'entrée :

- 📘 **Utilisation** → [`Compta.md`](Compta.md) — guide d'utilisation du mode assisté, et **carte de toute la doc utilisateur** (plus-values, structuration Excel, dépannage, portage macOS/Windows, mise à niveau, charte…).
- 🛠️ **Technique** → [`Compta_dev.md`](Compta_dev.md) — architecture 3-tiers, ajout de site, mécanisme d'extensions `custom/`, outils, tests.



## 6. Utilisation — mode classeur

Le classeur d'exemple contient des données fictives à remplacer par les vôtres.

**Conseils de personnalisation :**

- Renommer les comptes, catégories, devises et titres existants plutôt que les supprimer ; ceci permet de conserver formules et formats
- Supprimer et ajouter librement les **lignes d'opérations** (feuille Opérations)  en conservant la cohérence avec les lignes #Solde de chaque compte ; a minima avec la plus récente
- Conserver au moins **une ligne par tableau de données** (Opérations, Avoirs, Plus_value, Cotations) pour préserver les formules et le format — les nouvelles lignes se créent par copier/coller d'une ligne existante
- Modifier avec prudence la structure des feuilles (colonnes, en-têtes et pieds de tableaux, formules, noms définis)



## 7. Utilisation — mode assisté

### Sécurité

Les identifiants de connexion sont stockés chiffrés par GPG. `install.sh` pose une copie de travail `config_credentials.md` ; il reste à la remplir puis à la chiffrer comme détaillé dans la doc **Utilisation** ([`Compta.md`](Compta.md)) avant de la supprimer impérativement.

### Via l'interface graphique

L'application graphique guide l'utilisateur à travers les étapes : sélection des sites, collecte, import, vérification. Elle peut aussi être utilisée uniquement pour la gestion du classeur (comptes, catégories, devises, titres) sans activer la collecte.

Le premier lancement est en ligne de commande : `./cpt_gui.py`. Une fois l'application lancée, elle peut être épinglée dans la barre des tâches.

### En ligne de commande

L'app s'utilise aussi en CLI (collecte, import, appariement, cotations, diagnostics) ; les commandes sont détaillées dans la doc **Utilisation** ([`Compta.md`](Compta.md)).


## 8. Extensibilité

L'ajout d'un site bancaire est réalisable par la création de deux modules python (fetch + format) chargés du téléchargement et du formatage. Le nouveau site peut être intégré au code public ou conservé en partie privée sans toucher au code public.

Hors les sites, l'app reste modifiable, mais `git pull` signalera les conflits avec vos modifications locales. Pour s'en affranchir, le dossier `custom/` accepte des **monkeypatches** privés (`patch_*.py`) qui modifient ponctuellement le comportement de l'app sans en altérer le code public.

L'app est livrée avec un environnement de test. Celui-là contient plusieurs scenarii et est lui aussi extensible de manière publique ou privée.

Détails dans la doc **Technique** ([`Compta_dev.md`](Compta_dev.md)).

## 9. Vérifications

Environnements sur lesquels installation, GUI et collecte ont été effectivement vérifiés :

|    Environnement    |   Vérifications   |
| :---------------------------------: | :--------------: |
|       Linux Zorin et Mint (Ubuntu 22)       |     Installation, GUI, Collecte     |
| MacOS Ventura |     Installation, GUI, Collecte     |
|      Windows 11 - WSL/Ubuntu 22      | Installation, GUI, Collecte |



## 10. Restrictions

Limites connues, valables même lorsque les prérequis sont réunis :

|                  | Mode classeur | Mode assisté                                                 |
| ---------------- | ------------- | ------------------------------------------------------------ |
| **Installation** |               | installation manuelle pour certaines distributions Linux **(1)** |
| **GUI**          |               | **Wayland pur** non supporté **(2)**                        |

**(1)** il s'agit de **Fedora, Arch, openSUSE** et toutes les distributions qui n'utilisent pas l'`apt` Debian/Ubuntu — voir `requirements.txt`.

**(2)** mentionné pour mémoire car Wayland pur (sans XWayland) est quasi inexistant en mainstream Linux. La session Wayland pure casse `xclip` utilisé pour 2FA Kraken/Wise.

La partie GUI fonctionne pour les distributions **Linux Ubuntu** et dérivés (**Zorin, Mint**) - avec **GNOME, KDE, XFCE…** en session **X11** (ou XWayland).



## 11. Signaler un bug

- **Sur GitHub** : ouvrir une [Issue](https://github.com/mlebas29/Compta/issues) avec la description du problème et le message d'erreur éventuel
- **En ligne de commande** (nécessite [GitHub CLI](https://cli.github.com/)) :
  ```bash
  gh issue create --title "Bug: description" --body "Détail du problème"
  ```



## 12. Licence

Compta [EX] est distribué gratuitement sous licence GNU GPL v3.



## 13. Glossaire

- **2FA** (Two-Factor Authentication) : Authentification à deux facteurs
- **GPG** (GNU Privacy Guard) : Outil de cryptographie au standard OpenPGP
- **GUI** (Graphical User Interface) : Interface graphique
- **Playwright** : Outil d'automatisation de navigateur, utilisé pour la collecte
- **TNR** : Tests de non-régression
- **WSL** (Windows Subsystem for Linux) : Composant Linux de Microsoft pour Windows
