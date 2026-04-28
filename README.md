# Compta [EX]

**Comptabilité familiale — classeur Excel + application d'assistance Linux**

## 1. Présentation

Compta est un projet de comptabilité familiale ; il a deux composants :

1. Un **classeur** structuré avec des données brutes et de synthèse
2. Une **application d'assistance** qui
   - gère les structures du classeur (configuration)
   - collecte les données brutes, depuis des sites financiers vers le classeur
   
   

| Mode classeur | Mode assisté |
|:---:|:---:|
| ![Mode classeur](images/mode_classeur.png) | ![Mode assisté](images/mode_assiste.png) |

### Mode classeur

Le classeur `comptes.xlsm` est utilisable seul avec toute application compatible Excel. L'utilisateur importe manuellement les données financières (xls, PDF, zip, txt, html, CSV) et gère lui-même ses avoirs, comptes, devises, catégories, portefeuilles, etc.

Ce mode convient pour une comptabilité simple, peu diversifiée.

### Mode assisté

L'application graphique s'intercale entre le classeur et les sites financiers. 

L'utilisateur peut vouloir l'assistance de configuration seule ou l'assistance complète (configuration et collecte)

Le mode assisté n'est pas incompatible avec des interventions manuelles dans le classeur. Par exemple pour ajouter, supprimer ou modifier des opérations ou des biens. L'important est de conserver les éléments structurants (tableaux, en-têtes, pieds ...)

Ce mode convient pour une comptabilité diversifiée. 

Les environnements supportés sont :

-  Linux

-  **Windows 11** avec WSL (Windows Subsystem for Linux) qui permet de faire tourner Linux dans Windows, sans machine virtuelle à gérer



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
| **Prérequis** | LibreOffice ou équivalent | Linux ou Windows 11, LibreOffice |
| **Livré** | Classeur avec données d'exemple | Classeur vierge + application |
| **Action** | Télécharger [`comptes_exemple.xlsx`](https://github.com/mlebas29/Compta/raw/main/comptes_exemple.xlsx) | Tout télécharger et installer  (*) |



> ###### (*) Tout télécharger et installer
>
> ```bash
> sudo apt install git
> git clone https://github.com/mlebas29/Compta.git ~/Compta
> cd ~/Compta && ./install.sh
> # Compta peut être remplacé par un autre nom
> ```
>
> Le Shell script `install.sh` installe les dépendances Python, le navigateur Playwright/Chrome, et le raccourci bureau. En cas de prérequis manquant, il indique la commande `apt install` correspondante. Après quoi il suffira de relancer le script.
>
> Pour **Windows 11** c'est la même procédure, après avoir installé WSL2  (Voir [Compta_portage.md](Compta_portage.md))



## 4. Mise à jour

|                        Mode classeur                         |       Mode assisté        |
| :----------------------------------------------------------: | :-----------------------: |
| Télécharger  [`comptes_exemple.xlsx`](https://github.com/mlebas29/Compta/raw/main/comptes_exemple.xlsx) | `cd ~/Compta && git pull` |

`git pull` met à jour l'application mais pas le classeur `comptes.xlsm` (qui contient vos données). En cas d'incompatibilité, l'application le signale au démarrage — voir [`Compta_upgrade.md`](Compta_upgrade.md).

Voir aussi [`CHANGELOG.md`](CHANGELOG.md) : informations de mise à jour

## 5. Documentation

La documentation concerne essentiellement le mode assisté

-  [`Compta.md`](Compta.md)  : guide d'utilisation
-  [`Compta_plus.md`](Compta_plus.md) : commandes avancées, dépannage
-  [`Compta_tools.md`](Compta_tools.md) : outils de maintenance du classeur
-  [`Compta_upgrade.md`](Compta_upgrade.md) : mise à niveau du classeur
-  [`Compta_charte.md`](Compta_charte.md) : charte graphique du classeur
-  [`CHANGELOG.md`](CHANGELOG.md) : informations de mise à jour



## 6. Utilisation — mode classeur

Le classeur d'exemple contient des données fictives à remplacer par les vôtres.

**Conseils de personnalisation :**

- Renommer les comptes, catégories, devises et titres existants plutôt que les supprimer ; ceci permet de conserver formules et formats
- Supprimer et ajouter librement les **lignes d'opérations** (feuille Opérations)  en conservant la cohérence avec les lignes #Solde de chaque compte ; a minima avec la plus récente
- Conserver au moins **une ligne par tableau de données** (Opérations, Avoirs, Plus_value, Cotations) pour préserver les formules et le format — les nouvelles lignes se créent par copier/coller d'une ligne existante
- Modifier avec prudence la structure des feuilles (colonnes, en-têtes et pieds de tableaux, noms définis)



## 7. Utilisation — mode assisté

### Sécurité

Les identifiants de connexion sont stockés chiffrés par GPG. Remplir le template `config_credentials.md` puis chiffrer :

```bash
gpg -c config_credentials.md
rm config_credentials.md
```

### Via l'interface graphique

```bash
python3 cpt_gui.py
```

L'application graphique guide l'utilisateur à travers les étapes : sélection des sites, collecte, import, vérification. Elle peut aussi être utilisée uniquement pour la gestion du classeur (comptes, catégories, devises, titres) sans activer la collecte.

Une fois l'application lancée, elle peut être épinglée dans la barre des tâches.



### En ligne de commande

```bash
# Collecte d'un site
python3 cpt_fetch.py SOCGEN

# Import des fichiers collectés
python3 cpt_update.py

# Appariement seul
python3 cpt_pair.py

# Mise à jour des cotations
python3 cpt_fetch_quotes.py

# Diagnostics
python3 tool_controles.py -v
```

### Structure du projet

```
cpt_gui.py              # Interface graphique (Tkinter)
cpt.py                  # Orchestrateur général (collecte, import, appariement, cotation)
cpt_fetch.py            # Orchestrateur de collecte
cpt_update.py           # Import des opérations dans Excel
cpt_pair.py             # Appariement des opérations
cpt_fetch_quotes.py     # Mise à jour des cotations

cpt_fetch_SITE.py       # Collecteur par site (Playwright)
cpt_format_SITE.py      # Formatteur par site

inc_*.py                # Modules partagés (Excel, format, fetch, ...)
gui_*.py                # Modules graphiques partagés
config*.json            # Configuration (catégories, comptes, descriptions)
config.ini              # Configuration générale

tool_*.py               # Outils de maintenance
```

### Modification de l'application

Les fichiers de l'application sont modifiables, mais `git pull` signalera les conflits avec vos modifications locales. Voir [`Compta_plus.md`](Compta_plus.md) pour la résolution.



## 8. Restrictions

|                  | Mode classeur                              | Mode assisté                                                 |
| ---------------- | ------------------------------------------ | ------------------------------------------------------------ |
| **Installation** | Aucune (juste un tableur compatible Excel) | installation manuelle pour certaines distributions Linux  **(1)** |
| **GUI**          | N/A — utilisation directe du tableur       | **Wayland pur** non supporté  **(2)**                        |

**(1)** **Fedora, Arch, openSUSE** et toutes les distributions qui n'utilisent pas l'`apt` Debian/Ubuntu  — voir `requirements.txt`. 

**(2)**  mentionné pour mémoire car Wayland pur (sans XWayland) est quasi inexistant en mainstream Linux.  La session Wayland pure casse `xclip` utilisé pour 2FA Kraken/Wise.

 L'app fonctionne pour :

- **Linux Ubuntu 22.04 / 24.04** et dérivés (**Zorin, Mint**) - avec **GNOME, KDE, XFCE…** en session **X11** (ou XWayland).
-  **Windows 11** via WSL2-Ubuntu



## 9. Signaler un bug

- **Sur GitHub** : ouvrir une [Issue](https://github.com/mlebas29/Compta/issues) avec la description du problème et le message d'erreur éventuel
- **En ligne de commande** (nécessite [GitHub CLI](https://cli.github.com/)) :
  ```bash
  gh issue create --title "Bug: description" --body "Détail du problème"
  ```



## 10. Licence

Compta [EX] est distribué gratuitement sous licence GNU GPL v3.

C'est la version export d'un projet conçu pour des extensions de sites.
