# Compta [EX]

**Comptabilité familiale — classeur Excel + application d'assistance Linux**

## 1. Présentation

Compta est un projet de comptabilité familiale ; il a deux composants :

1. Un **classeur** structuré avec des données brutes et de synthèse
2. Une **application d'assistance** qui
   - gère les structures du classeur (configuration)
   - collecte les données brutes, depuis des sites financiers vers le classeur

### Mode classeur

Le classeur `comptes.xlsm` est utilisable seul avec toute application compatible Excel. L'utilisateur importe manuellement les données financières (xls, PDF, zip, txt, html, CSV) et gère lui-même ses avoirs, comptes, devises, catégories, portefeuilles, etc.

Ce mode convient pour une comptabilité simple, peu diversifiée.

### Mode assisté

L'application graphique s'intercale entre le classeur et les sites financiers. 

Ses deux principales fonctions de configuration et collecte sont au choix de l'utilisateur qui peut vouloir l'assistance de configuration seule ou l'assistance complète (configuration et collecte)

Ce mode convient pour une compatabilité diversifiée, uniquement sous Linux.

| Mode classeur | Mode assisté |
|:---:|:---:|
| ![Mode classeur](images/mode_classeur.png) | ![Mode assisté](images/mode_assiste.png) |

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

| Mode classeur | Mode assisté |
|---|---|
| Classeur avec données d'exemple | Classeur vierge + application complète |
| Prérequis : LibreOffice ou équivalent | Prérequis : Linux, LibreOffice |
| Télécharger [`comptes_exemple.xlsx`](https://github.com/mlebas29/Compta/raw/main/comptes_exemple.xlsx)  ; c'est tout ! | Tout télécharger et installer  (*) |



> ###### (*) Tout télécharger et installer (mode assisté)
>
> ```bash
> sudo apt install git
> git clone https://github.com/mlebas29/Compta.git ~/Compta
> cd ~/Compta && ./install.sh
> # Compta peut être remplacé par un autre nom
> ```
>
> Le Shell script `install.sh` installe les dépendances Python, le navigateur Playwright/Chrome, et le raccourci bureau. En cas de prérequis manquant, il indique la commande `apt install` correspondante. Après quoi il suffira de relancer le script.



## 4. Mise à jour



| Mode classeur                                                | Mode assisté              |
| ------------------------------------------------------------ | ------------------------- |
| Télécharger  [`comptes_exemple.xlsx`](https://github.com/mlebas29/Compta/raw/main/comptes_exemple.xlsx) | `cd ~/Compta && git pull` |



## 5. Documentation

-  [`Compta.md`](Compta.md)  : guide d'utilisation
-  [`Compta_plus.md`](Compta_plus.md) : commandes avancées, dépannage
-  [`Compta_tools.md`](Compta_tools.md) : outils de maintenance du classeur



## 6. Utilisation — mode classeur

Le classeur d'exemple contient des données fictives à remplacer par les vôtres.

> **Conseils de personnalisation :**
>
> - Renommer les comptes, catégories, devises et titres existants plutôt que les supprimer ; ceci permet de conserver formules et formats
> - Supprimer les **lignes d'opérations** (feuille Opérations) librement, en conservant deux lignes #Solde par compte, à des dates différentes
> - Conserver au moins **une ligne par tableau de données** (Opérations, Avoirs, Plus_value, Cotations) pour préserver les formules et le format — les nouvelles lignes se créent par copier/coller d'une ligne existante
> - Modifier avec prudence la structure des feuilles (colonnes, en-têtes et pieds de tableaux, noms définis)
>



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

L'interface guide l'utilisateur à travers les étapes : sélection des sites, collecte, import, vérification. Elle peut aussi être utilisée uniquement pour la gestion du classeur (comptes, catégories, devises, titres), sans activer la collecte.

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

> NB : Toute modification par l'utilisateur des fichiers livrés dans un environnement `git` est possible mais est soumise aux règles de cet environnement. 

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

## 8. Restrictions

- **Mode classeur** : aucune restriction, fonctionne sur tout OS avec un tableur compatible Excel.
- **Mode assisté** : testé sur Ubuntu 22.04 et dérivés (Zorin, Mint). Le script `install.sh` utilise `apt` et ne supporte pas les distributions non Debian/Ubuntu (Fedora, Arch, openSUSE). Sur ces systèmes, une installation manuelle des dépendances est nécessaire (voir `requirements.txt`).

## 9. Licence

Compta [EX] est distribué gratuitement sous licence GNU GPL v3.

C'est la version export d'un projet conçu pour des extensions de sites.
