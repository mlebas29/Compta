# Compta

**Tout votre patrimoine familial, centralisé et tenu à jour automatiquement — dans un classeur qui reste le vôtre.**

## 1. Présentation

Compta suit un patrimoine familial **diversifié** (plusieurs banques, titres, crypto, métaux précieux, multi-devises) et lui épargne la saisie manuelle : il **collecte** vos données sur vos sites financiers, les **importe**, les **catégorise** et les **apparie** — pour alimenter des feuilles de synthèse **patrimoine**, **plus-values** et **budget**.

**Vos données ne quittent jamais votre machine.** Tout vit dans un classeur Excel/LibreOffice que *vous* contrôlez : ni cloud, ni abonnement, ni service en ligne à qui confier vos finances. Gratuit et open source (GPL v3).

Deux composants :

1. un **classeur** `comptes.xlsm` — vos données brutes **et** leurs synthèses ;
2. une **application d'assistance** (optionnelle) — gère la structure du classeur et collecte depuis les sites.

**Pour qui ?** Une famille dont les avoirs sont assez variés pour que le suivi à la main devienne pénible, et qui préfère **garder la main sur ses données** plutôt que de les confier à une app en ligne.


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

Pour **Windows 11** c'est la même procédure, après avoir installé WSL2 qui permet de faire tourner Linux sur Windows sans machine virtuelle à gérer.

Pour **MacOS** la procédure est plus spécifique, avec une installation manuelle de **LibreOffice 24.8**.

Pour aller plus loin avec Windows et MacOS :  [Compta_portage.md](Compta_portage.md)




## 4. Mise à jour

Les évolutions sont tracées sur GitHub dans [`CHANGELOG.md`](https://github.com/mlebas29/Compta/blob/main/CHANGELOG.md), qui consigne les changements entre versions.

|                        Mode classeur                         | Mode assisté |
| :----------------------------------------------------------: | :-----------: |
| Télécharger  [`comptes_exemple.xlsx`](https://github.com/mlebas29/Compta/raw/main/comptes_exemple.xlsx) | Télécharger et lancer `upgrade.py` (*) |
| Consulter [`Compta_upgrade_classeur.md`](https://github.com/mlebas29/Compta/blob/main/Compta_upgrade_classeur.md) | Consulter [`Compta_upgrade_assiste.md`](https://github.com/mlebas29/Compta/blob/main/Compta_upgrade_assiste.md) |

> (*) `upgrade.py` est **réversible** : il sauvegarde l'état avant toute mise à jour.



## 5. Documentation

La documentation est organisée autour de deux points d'entrée :

- 📘 **Utilisation** → [`Compta.md`](Compta.md) — guide d'utilisation du mode assisté, et **index de la doc utilisateur** 
- 🛠️ **Technique** → [`Compta_dev.md`](Compta_dev.md) — pour les activités de développement



## 6. Utilisation — mode classeur

Le classeur d'exemple contient des données fictives à remplacer par les vôtres.

**Conseils de personnalisation :**

- Renommer les comptes, catégories, devises et titres existants plutôt que les supprimer ; ceci permet de conserver formules et formats
- Supprimer et ajouter librement les **lignes d'opérations** (feuille Opérations)  en conservant la cohérence avec les lignes #Solde de chaque compte ; a minima avec la plus récente
- Conserver au moins **une ligne par tableau de données** (Opérations, Avoirs, Plus_value, Cotations) pour préserver les formules et le format — les nouvelles lignes se créent par copier/coller d'une ligne existante
- Modifier avec prudence la structure des feuilles (colonnes, en-têtes et pieds de tableaux, formules, noms définis)



## 7. Utilisation — mode assisté

Le classeur livré est vierge de données personnelles. L'application graphique — à lancer via le raccourci installé (icône €) — guide l'utilisateur à travers les étapes : sélection des sites, collecte, import, vérification. Elle peut aussi être utilisée uniquement pour la gestion du classeur (comptes, catégories, devises, titres) sans activer la collecte. L'app s'utilise également en ligne de commande (collecte, import, appariement, cotations, diagnostics).

Avant la première collecte il s'agit de renseigner :

- les identifiants de connexion via GPG ; ceux-là sont stockés dans un fichier chiffré (la copie en clair est à supprimer après chiffrement) ;
- tous les autres paramètres via l'application Compta ; ceux-là sont stockés pour la plupart dans le classeur (noms de comptes, devises utilisées, etc.).

Pour aller plus loin : **Utilisation** ([`Compta.md`](Compta.md))



## 8. Extensibilité

Il y a plusieurs axes d'extension :

- L'ajout d'un site bancaire peut être intégré au code public ou conservé en partie privée sans toucher au code public.

- Hors les sites, il est possible d'ajouter des "monkeypatch" qui modifient le comportement de l'app sans altérer le code public.

- L'app est livrée avec un environnement de test contenant plusieurs scenarii. Il est lui aussi extensible de manière publique ou privée.

- Le dossier où résident l'application et le classeur peut être cloné pour séparer l'activité développement de l'activité utilisation afin de protéger le classeur.

Pour aller plus loin : **[`Compta_extension.md`](Compta_extension.md)**



## 9. Vérifications

Environnements sur lesquels installation, GUI et collecte sont effectivement vérifiés :

|    Environnement    |   Vérifications   |
| :---------------------------------: | :--------------: |
|       Linux Zorin et Mint (Ubuntu 22)       |     Installation, GUI, Collecte     |
| MacOS Ventura |     Installation, GUI, Collecte     |
|      Windows 11 - WSL/Ubuntu 22      | Installation, GUI, Collecte |

Grâce au système WSL de Microsoft qui simule parfaitement Linux, l'App de base Linux tourne quasiment sans adaptation sur Windows. Pour MacOS, le portage demande plus d'attention en raison d'une architecture différente, bien que cousine pour l'OS, notamment avec LibreOffice et Python.



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
