# 1. Présentation

Ce document est le **guide d'utilisation** et le point d'entrée de la documentation utilisateur. Selon votre besoin :

| Besoin | Document |
|---|---|
| Découvrir le projet, installer, mettre à jour | [`README.md`](README.md) |
| Personnaliser le classeur (mode classeur) | [`README.md`](README.md) §Utilisation — mode classeur |
| **Utiliser l'app d'assistance** (collecte, import, cotations) | **ce document** |
| Structuration Excel, commandes avancées, dépannage | [`Compta_plus.md`](Compta_plus.md) |
| Comprendre les plus-values latentes | [`Compta_pvl.md`](Compta_pvl.md) |
| Charte graphique du classeur | [`Compta_charte.md`](Compta_charte.md) |
| Mettre à jour l'installation (mode assisté) | [`Compta_upgrade_assiste.md`](Compta_upgrade_assiste.md) |
| Mettre à niveau le classeur | [`Compta_upgrade_classeur.md`](Compta_upgrade_classeur.md) |
| Installer sur macOS ou Windows (WSL) | [`Compta_portage.md`](Compta_portage.md) |
| Outils de maintenance (CLI) | [`Compta_tools.md`](Compta_tools.md) |
| Développer / contribuer | [`Compta_dev.md`](Compta_dev.md) (hub développeur) |

# 2. Introduction

La gestion comptable a pour but de centraliser dans un tableur :

* les **opérations** (ou transactions) financières

* les **positions** (ou valorisations ou balances ou soldes) de titres et comptes.

* les autres **valeurs de biens matériels** (immobilier ...)

Le tableur **comptes.xlsm** présente ces données et les synthétise selon différentes vues : postes budgétaires, [plus values latentes](Compta_pvl.md), répartitions patrimoniales. Il détecte aussi des incohérences telles que des écarts entre  soldes calculés et soldes relevés.

Les tâches de la gestion comptable :

* **collecte** des données financières depuis les **sites** Internet
* saisie **manuelle** des opérations pour lesquelles il n'existe pas de site de rattachement (créances, achat bijoux ...)
* **importation** des données collectées dans le tableur.
* affectation des opérations à des **catégories** prédéfinies, elle même regroupées en **postes** budgétaires
* **appariement** d'opérations liées dans des comptes différents
* mise à jour des **cotations** monétaires pour la valorisation des biens
* **configuration** du tableur (Ajout / modification / suppression de Comptes, devises, titres, catégories, postes ...)

# 3. App d'assistance

L'App graphique **Comptabilité** :

- automatise la quasi totalité de ces tâches
- dispense de connaissances Excel pour la configuration
- conserve les données Excel qui sont hors de son périmètre

L'App peut générer automatiquement des opérations (ex : crédit espèces en contrepartie d'un retrait DAB).

Une présence est nécessaire au moment de la collecte lorsque les procédures 2FA (Two Factor Authentication) sont déclenchées. Ces procédures sont inexistantes, occasionnelles ou systématiques, selon les sites.

Une supervision reste nécessaire ; par exemple pour compléter la catégorisation ou pour relancer la collecte d'un site particulier.

## Sites pris en charge

Compta est livré avec **12 sites publics** :

| Site | Nature |
|---|---|
| SOCGEN | Banque (Société Générale) |
| BOURSOBANK | Banque en ligne |
| NATIXIS | Épargne salariale (PEE) |
| DEGIRO | Courtier (titres) |
| ETORO | Courtier / crypto |
| KRAKEN | Exchange crypto |
| WISE | Compte multidevises |
| PAYPAL | Compte PayPal |
| AMAZON | Carte cadeau Amazon |
| BTC | Wallets Bitcoin (adresses publiques) |
| XMR | Wallets Monero (nœud local requis) |
| MANUEL | Saisie manuelle (créances, biens, sites sans collecte) |

Les connecteurs crypto et multidevises (Kraken, Wise, BTC, XMR, eToro…) sont utilisables tels quels. Les connecteurs bancaires (SOCGEN, NATIXIS…) dépendent du profil client de la banque ; ce profil est pris en compte via les paramètres techniques des comptes (GUI création de compte). Les restrictions éventuelles propres à chaque site figurent dans sa description (GUI onglet Sites).

**Pour activer les sites qui vous concernent**, voir ANNEXE C — Configuration initiale (§5 Sites).

## Collecte

La collecte est déclenchée pour les sites qui auront été sélectionnés. Un mot de passe maître est nécessaire pour accéder aux identifiants et mots de passe de sites. Les fichiers sont téléchargés dans le dossier de collecte local (`./dropbox`).

Chaque site est décrit dans l'application (Onglet Sites). On y trouve notamment une procédure manuelle de secours pour la collecte et des indications pour les procédures 2FA.

Pour certains sites le navigateur Chrome est rendu visible afin de permettre une **intervention manuelle** au moment de la connexion; par exemple saisie d'un code dans une page, ou résolution d'un CAPTCHA. Cf. ANNEXE B

Afin d'optimiser le temps de collecte, les sites **sans 2FA** (services par interface de programmation, ou comptes sans double authentification) sont collectés **en parallèle**, et pendant le traitement des autres sites avec 2FA (une à la fois). 

> Le classement parallèle/séquentiel est **automatique** mais tout site peut être ajouté dans le groupe parallèle. Cependant, lorsque des sites interactifs sont placés dans le groupe parallèle, il y a des risques d'entrelacement des dialogues avec les sites du groupe séquentiel. Sans danger mais potentiellement déroutant pour l'utilisateur.



## Import

L'import concerne toutes les collectes (dossier de collecte)

Les opérations collectées ne sont importées que si elles sont nouvelles, en considérant leur libellé, leur date, leur montant et devise.

Une option de lancement "Import soldes" permet d'ajouter les Soldes des comptes dans la feuille d'opération Excel, même quand aucune opération n'est importée. Cette option génère de nombreuses lignes de soldes.

L'import vide le dossier de collecte de ses fichiers pour les archiver, ce qui permet une restauration ultérieure du dossier de collecte et du comptes.xlsm d'avant l'import. Le bouton "Annuler l'import" peut être actionné plusieurs fois pour remonter dans l'historique des archives. Chaque annulation supprime l'état courant (dossier de collecte, **comptes.xlsm**)

### Catégorisation

Pendant l'import, la catégorisation automatique est déclenchée à partir du libellé d'une opération via une "regex" qui permet de reconnaître un libellé par sa structure et son contenu (pattern matching)

Les correspondances regex → Catégories sont paramétrables dans l'App (onglet Catégories)

### Appariements

Ceci concerne les virements, changes, achats de titres ou de métaux précieux. Chaque paire d'opération est identifiée par une référence unique (Colonne Réf. dans Excel Opérations)

L'App fait une recherche d'appariement sur toute opération éligible (Réf="-" indiqué par la catégorisation). Elle apparie deux opérations si elles ont des comptes différents, des signes opposés, des dates proches, et des montants EUR équivalents, sauf pour les virements où les montants doivent être strictement identiques et dans la même devise.

En cas d'ambiguïté (plusieurs candidats indiscernables), les opérations restent non appariées pour vérification manuelle.

Les seuils (délai max, tolérance montants) sont paramétrables dans l'App  (onglet Paramètres).

## Cotations

La fonction de cotation a pour effet de mettre à jour dans le fichier excel les montants en Euro des avoirs exprimés en devises non Euro.

## Mode d'emploi de l'App d'assistance

Le mode opératoire est dirigé par l'interface graphique qui documente les procédures spécifiques de connexion.

#### Préalable - Configuration

Avant la première collecte il s'agit de renseigner :

- les identifiants de connexion via GPG ; ceux-là sont stockés dans un fichier chiffré (la copie en clair est à supprimer après chiffrement) ;
- tous les autres paramètres via l'application Compta ; ceux-là sont stockés pour la plupart dans le classeur (noms de comptes, devises utilisées, etc.). Cette configuration se fait entièrement via l'App, sans toucher au fichier Excel

Voir **ANNEXE C** pour le détail de la configuration initiale (identifiants, devises, comptes, catégories, sites).

Une fois la configuration faite, elle n'a besoin d'être reprise que lors de l'ouverture ou la fermeture d'un compte, l'ajout d'une devise, etc.

#### Étape 1 - Lancement de l'App

Lancer l'App Comptabilité soit **en cliquant sur le raccourci** (icône € colorée selon le mode : Or pour EX, rouge pour PROD, bleu pour DEV), soit **en ligne de commande** : `cd ~/Compta && ./cpt_gui.py`.

> En lancement terminal, le Dock (macOS) ou la barre des tâches affiche l'icône de l'interpréteur Python (une « fusée »), pas l'icône € colorée — c'est normal : le raccourci (bundle `.app` / `.desktop`) n'est pas impliqué. L'icône du mode n'apparaît qu'au lancement *via le raccourci*.

![](cpt_gui_export.png)

La fenêtre qui s'ouvre présente l'onglet Exécution :

![](images/Compta.png)

#### Étape 2 - Collecte

Dans l'onglet Exécution, sélectionner les sites voulus puis cliquer sur le bouton "Collecte". L'App demande le mot de passe maitre dans une fenêtre dédiée, puis visite tous les sites sélectionnés pour collecter les données, ce qui peut prendre plusieurs minutes.

> NB : Une présence est nécessaire avec le mobile car certains sites peuvent déclencher une procédure 2FA pendant la collecte.

Quand la collecte est terminée, cliquer sur "Import" pour mettre à jour le fichier **comptes.xlsm** avec les données collectées. On peut aussi attendre pour relancer une collecte avec d'autres sites qui manqueraient.

#### Étape 3 - compléments manuels

Le fichier  **comptes.xlsm** peut alors être ouvert sous LibreOffice, pour une session manuelle afin de :

* vérifier la bonne collecte et l'import des données (opérations, valorisations)

* vérifier les affectations d'opérations aux catégories de dépenses/revenus

* vérifier les appariements d'opérations (virements, changes, titres)

* vérifier l'absence d'erreur (Cf. ANNEXE A - Contrôles Excel)

* corriger si nécessaire



# 4. Cotations

Les cotations sont effectuées depuis 3 sites publics :

- Métaux précieux (Yahoo Finance)
- Cryptomonnaies (CoinGecko)
- Devises (Frankfurter/BCE)

# 5. Pour approfondir

Plus d'information dans **Compta\_plus.md** (installation, commandes avancées, dépannage).

# ANNEXE A - Contrôles Excel

Dans **comptes.xlsm** Feuille Contrôles, cellule A1.

Contenu = "✓" : rien à signaler

Tous les autres cas sont signalés par un changement de couleur (format conditionnel : vert=OK, orange=warning, rouge=erreur) et sont à investiguer.

La cellule A1 est une synthèse de 7 positions (concaténation de 7 symboles) :

| Position | Label | OK | Warning | Erreur | Signification |
|----------|-------|----|---------|--------|---------------|
| 1 | Comptes (soldes) | `✓` | | `✗` | Écarts entre soldes calculés et soldes relevés |
| 2 | Catégories | `✓` | | `✗` | Opération(s) sans catégorie connue |
| 3 | Divers | `✓` | `⚠` | | Date hors période / Ventilation Patrimoine / Cotations incomplètes |
| 4 | Appariements | `✓` | `⚠` | | Appariements incomplets |
| 5 | Balances | `✓` | `⚠` | | Problème de balances |
| 6 | Inconnus (comptes) | `✓` | | `✗` | Compte(s) absent(s) de la feuille Avoirs |
| 7 | Formules | `✓` | | `✗` | Synthèse PVL ou Avoirs en erreur (#N/A, #REF!, …) |

Exemples : `✓✓✓⚠⚠✓✓` = seuls appariements et balances à vérifier. `✗✓✓⚠✓✓✓` = erreur soldes + appariements incomplets. `✓✓✓✓✓✓✗` = la synthèse Avoirs ou Plus_value plante.

Les contrôles **Divers** et **Balances** sont des agrégateurs : ils consolident plusieurs sous-contrôles, visibles en sous-lignes indentées de la feuille Contrôles :

- **Divers** : *Date hors période* (dates anormales en Opérations) + *Ventilation Patrimoine* (cumul des sections vs total global) + *Cotations* (devises utilisées en PVL/AVR mais absentes ou sans cours dans Cotations).
- **Balances** : *Virements €* + *Titres €* + *Changes Eq €*.

Le contrôle **Formules** surveille des cellules d'alarme posées dans les feuilles Plus_value et Avoirs : il bascule en `✗` si une formule en amont propage `#N/A`, `#REF!`, etc. (détail technique des cellules et named ranges : [`Compta_dev.md`](Compta_dev.md) §Feuille Contrôles).

Diagnostic détaillé : `./tool_controles.py` (ou `-v` pour le mode verbeux).

**Barre de statut GUI :**

L'App affiche en permanence une barre de statut en bas de fenêtre avec deux zones :
- **Statut** (gauche) : état des Contrôles, coloré selon 3 niveaux — vert (OK), orange (Divers/Appariements/Balances), rouge (Comptes/Catégories/Inconnus/Formules). Cliquable pour afficher le détail des 7 contrôles.
- **Total Avoirs** (droite) : total EUR lu depuis Avoirs L2 (cached value de la formule Total, mise à jour à chaque sauvegarde).

**Checks de cohérence au démarrage GUI :**
- Formules Contrôles → Avoirs : détection de références cassées
- Sites orphelins dans la configuration JSON
- Catégories absentes du Budget

# ANNEXE B - Récap headed

Tous les scripts démarrent en **headless** (fenêtre du navigateur invisible). Bascule headed selon le contexte :

| Site | Déclencheur headed | Interaction utilisateur |
|------|-------------------|----------------------|
| **eToro** | Login requis (session expirée) | CAPTCHA et/ou code 2FA dans Chrome |
| **Wise** | Login requis (session expirée) | Mobile 2FA + email 2FA (clipboard) |
| **Kraken** | Cloudflare Turnstile (CAPTCHA) | Cocher "humain", puis 2FA email (clipboard) |
| **BOURSOBANK/SOCGEN/NATIXIS/DEGIRO** | Selon script (2FA, OCR...) | Variable |

- Si session active (profil persistant) : reste headless, pas d'interaction
- Wise : clipboard surveille liens wise.com, ouvre dans nouvel onglet
- Kraken : clipboard surveille liens kraken.com, navigue dans même onglet

# ANNEXE C - Configuration initiale

La configuration se fait via les onglets de l'App. L'ordre ci-dessous respecte les dépendances entre les éléments.

## 1. Identifiants de connexion

Les identifiants des sites financiers sont stockés chiffrés par GPG. `install.sh` pose une copie de travail `config_credentials.md` (gitignorée) depuis le modèle versionné `config_credentials.md.default` ; il reste à la remplir avec les identifiants de chaque site, puis à la chiffrer :

```bash
# config_credentials.md est créé par install.sh
# (sinon : cp config_credentials.md.default config_credentials.md)
# … remplir config_credentials.md …
gpg -c config_credentials.md     # → config_credentials.md.gpg (chiffré)
rm config_credentials.md         # impératif : efface les identifiants en clair
```

Le mot de passe GPG (P2) sera demandé à chaque collecte.

## 2. Devises (onglet Devises)

Ajouter les devises nécessaires (hors EUR qui est la devise de base). Pour chaque devise :

- **Code** : code standard (USD, GBP, BTC, XAU...)
- **Famille** : Fiat, Crypto ou Métal
- **Nom** : libellé libre

Les devises dérivées (ex : once d'or → gramme d'or) se définissent par une formule à partir d'une devise existante.

## 3. Comptes (onglet Comptes)

Créer un compte pour chaque compte bancaire, placement ou portefeuille. Pour chaque compte :

- **Intitulé** : nom libre (ex : "LBP Courant")
- **Devise** : devise du compte (doit exister, cf. étape 2)
- **Type** : Courant, Épargne, Titres, PEA...
- **Site** : site de collecte rattaché (ou N/A pour les comptes sans collecte)
- **Domiciliation**, **Titulaire**, **Propriété** : attributs patrimoniaux

Lorsqu'un compte est rattaché à un site, des **champs techniques** supplémentaires apparaissent selon le site. Ils permettent au collecteur d'identifier le compte sur le site bancaire.

Ces champs sont propres à chaque site et n'apparaissent que pour les comptes rattachés. 

**L'onglet Sites** aide à acquérir la valeur de certains champs techniques

| Site | Champs techniques |
|------|------------------|
| **SOCGEN** | Type SG (principal / épargne / assurance_vie), Numéro, ID technique, Clé fichiers (selon le type) |
| **BOURSOBANK** | Numéro de compte |
| **BTC** | Clé wallet, Adresses publiques |
| **XMR** | Clé, Nom du portefeuille |

Les biens matériels (immobilier, mobilier) se créent aussi dans cet onglet (bouton "Bien").

## 4. Catégories et postes (onglet Catégories)

Les **postes budgétaires** regroupent les catégories en Fixe ou Variable (ex : Logement, Transport, Loisirs).

Les **catégories** sont les lignes du budget (ex : Loyer, Assurance auto, Restaurants). Chaque catégorie est rattachée à un poste.

Les **correspondances** (regex → catégorie) permettent la catégorisation automatique des opérations à l'import, à partir de leur libellé.

## 5. Sites (onglet Sites)

Vous n'activez que les sites correspondant à vos comptes. Pour chacun, le parcours reprend les étapes précédentes de cette annexe :

1. **Identifiants** — la ligne du site dans `config_credentials.md` (§1 ci-dessus).
2. **Compte(s)** — le ou les comptes rattachés, champ **Site** + champs techniques (§3 ci-dessus).
3. **Activation** — cocher le site dans l'onglet Sites et cliquer sur le bouton **Enregistrer**.
4. **Collecte** — le sélectionner dans l'onglet Exécution et lancer (intervention 2FA éventuelle selon le site, cf. ANNEXE B).

Chaque site affiche une zone descriptive qui indique :

- sa procédure de connexion et les éventuelles interventions 2FA
- les types de comptes collectables
- les **paramètres techniques** spécifiques

Certains sites possèdent des paramètres modifiables :

- **Jours max** : profondeur de collecte en jours (override du paramètre global)

- **Nb rapports** : nombre de rapports à télécharger

- **Dossier Drive**, **Compte Drive** : pour les sites collectés via Google Drive

- **CLI Monero**, **Dossier wallets**, **Timeout wallet** : pour la collecte Monero

- **parallel** : pour placer le site dans le groupe de collecte parallèle

  > parallel n'a pas de champ dans l'interface graphique, il faut ajouter `parallel = true` sous son `[SITE]` dans `config.ini`.

## 6. Paramètres (onglet Paramètres)

Ajuster si nécessaire :

- **Appariement** : délai max entre opérations liées, tolérance sur les montants
- **Général** : mode debug, profondeur d'import, rétention des archives
- **Opérations liées** : règles de génération automatique de contreparties (ex : retrait DAB → Espèces)
- **Solde auto** : comptes dont le solde est calculé à partir d'une catégorie trigger

## Aller plus loin

- [`Compta_plus.md`](Compta_plus.md) — commandes avancées, structuration Excel, dépannage
- [`Compta_tools.md`](Compta_tools.md) — outils de maintenance et environnement git
- [`Compta_upgrade_assiste.md`](Compta_upgrade_assiste.md) — mettre à jour l'installation (mode assisté)
- [`Compta_upgrade_classeur.md`](Compta_upgrade_classeur.md) — migrations du classeur, par version
- [`Compta_dev.md`](Compta_dev.md) — documentation développeur (architecture, contributeur)
