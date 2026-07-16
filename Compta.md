# 1. Présentation

Ce document est le **guide d'utilisation** et le point d'entrée de la documentation utilisateur. Selon votre besoin :

| Besoin | Document |
|---|---|
| Découvrir le projet, installer, mettre à jour | [`README.md`](README.md) |
| Personnaliser le classeur (mode classeur) | [`README.md`](README.md) §Utilisation — mode classeur |
| **Utiliser l'app d'assistance** (collecte, import, cotations) | **ce document** |
| Structuration Excel, commandes avancées, configuration en ligne de commande, dépannage | [`Compta_plus.md`](Compta_plus.md) |
| Comprendre les plus-values latentes | [`Compta_pvl.md`](Compta_pvl.md) |
| Charte graphique du classeur | [`Compta_charte.md`](Compta_charte.md) |
| Mettre à jour l'installation (mode assisté) | [`Compta_upgrade_assiste.md`](Compta_upgrade_assiste.md) |
| Mettre à niveau le classeur | [`Compta_upgrade_classeur.md`](Compta_upgrade_classeur.md) |
| Installer sur macOS ou Windows (WSL) | [`Compta_portage.md`](Compta_portage.md) |
| Outils de maintenance (CLI) | [`Compta_tools.md`](Compta_tools.md) |
| Vocabulaire (métier + sigles) | [`Compta_glossaire.md`](Compta_glossaire.md) |
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

Une présence est nécessaire au moment de la collecte lorsque des procédures d'authentification sont déclenchées. Selon les sites ces procédures sont inexistantes, occasionnelles ou systématiques.

Une supervision reste nécessaire ; par exemple pour compléter la catégorisation ou pour relancer la collecte d'un site particulier.

## Sites pris en charge

Comptabilité est livrée avec **11 sites publics** :

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
| XMR | Wallets Monero (nœud distant, par tunnel SSH) |

Les connecteurs crypto et multidevises (Kraken, Wise, BTC, eToro…) sont utilisables tels quels — sauf **XMR**, qui interroge un `monero-wallet-rpc` hébergé sur une machine tierce toujours allumée et exige donc un provisionnement à part. Les connecteurs bancaires (SOCGEN, NATIXIS…) dépendent du profil client de la banque ; ce profil est pris en compte via les paramètres techniques des comptes (GUI création de compte). Les restrictions éventuelles propres à chaque site figurent dans sa description (GUI onglet Sites).

**Pour activer les sites qui vous concernent**, voir ANNEXE C — Configuration initiale (§4 Sites).

## Collecte

La collecte est déclenchée pour les sites qui auront été sélectionnés. Un mot de passe maître (**P2**), saisi au démarrage de la collecte, est nécessaire pour accéder aux identifiants et mots de passe de sites. Les fichiers sont téléchargés dans le dossier de collecte local (`./dropbox`).

Chaque site est décrit dans l'application (Onglet Sites). On y trouve notamment une procédure manuelle de secours pour la collecte et des indications pour les procédures d'authentification.

- **Interaction** - Lorsqu'un site nécessite une action humaine, l'onglet Exécution la signale visuellement (alerte d'authentification requise).

- **Visibilité de navigation** - Pour une **action en fenêtre** — saisie d'un code, résolution d'un CAPTCHA, ou login manuel *dans la page* — le navigateur Chrome est rendu visible. Une **2FA mobile** (validation sur le téléphone) ne nécessite aucune fenêtre. Un site peut aussi être **forcé visible** (case « Fenêtre visible » de l'onglet Sites) (Cf. ANNEXE C)

- **Parallélisme** - Afin d'optimiser le temps de collecte, plusieurs sites sont collectés en parallèle, pendant le traitement des autres sites à **interaction humaine** (authentification, un à la fois).  Le classement parallèle/séquentiel est prédéfini (Cf. ANNEXE B) mais tout site peut être ajouté dans le groupe parallèle (Cf. ANNEXE C).

- **Profilage** -  À chaque collecte, l'App tient à jour un profil de navigation qui sert à repérer qu'un site a **changé de comportement** — une étape qui disparaît ou s'ajoute, une durée qui explose, un fichier attendu manquant, une connexion devenue soudain interactive. Le profil est consultable hors ligne.

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

Certaines opérations prédéfinies peuvent être appariées automatiquement (onglet Paramètres).

## Cotations

La fonction de cotation a pour effet de mettre à jour dans le fichier excel les montants en Euro des avoirs exprimés en devises non Euro.

## Mode d'emploi de l'App d'assistance

Le mode opératoire est guidé par l'interface graphique qui documente les procédures spécifiques de connexion.

#### 🚧 Préalable - Configuration

Préalable à la première collecte.

Voir **ANNEXE C** pour le détail de la configuration initiale (devises, comptes, catégories, sites).

> Une fois la configuration faite, elle n'a besoin d'être reprise que lors de l'ouverture ou la fermeture d'un compte, l'ajout d'une devise, un changement de catégorie, etc.

#### ▶️ Étape 1 - Lancement de l'App

Lancer l'App Comptabilité soit **en cliquant sur le raccourci** (icône € colorée selon le mode : Or pour EX, rouge pour PROD, bleu pour DEV), soit **en ligne de commande** : `cd ~/Compta && ./cpt_gui.py`.

> En lancement terminal, le Dock (macOS) ou la barre des tâches affiche l'icône de l'interpréteur Python (une « fusée »), pas l'icône € colorée — c'est normal : le raccourci (bundle `.app` / `.desktop`) n'est pas impliqué. L'icône du mode n'apparaît qu'au lancement *via le raccourci*.

![](cpt_gui_export.png)

La fenêtre qui s'ouvre présente l'onglet Exécution :

![](images/Compta.png)

L'App affiche en permanence une barre de statut en bas de fenêtre avec deux zones (Cf. ANNEXE A)

#### 🌐 Étape 2 - Collecte

Dans l'onglet Exécution, sélectionner les sites voulus puis cliquer sur le bouton "Collecte". L'App demande le mot de passe maître (**P2**) dans une fenêtre dédiée, puis visite tous les sites sélectionnés pour collecter les données, ce qui peut prendre plusieurs minutes.

> NB : Une présence est nécessaire car certains sites peuvent déclencher une procédure d'authentification (avec ou sans mobile) pendant la collecte.

Quand la collecte est terminée, cliquer sur "Import" pour mettre à jour le fichier **comptes.xlsm** avec les données collectées. On peut aussi attendre pour relancer une collecte avec d'autres sites qui manqueraient.

#### 👁️ Étape 3 - compléments manuels

Le fichier  **comptes.xlsm** peut alors être ouvert sous LibreOffice, pour une session manuelle afin de :

* vérifier la bonne collecte et l'import des données (opérations, valorisations)

* vérifier les affectations d'opérations aux catégories de dépenses/revenus ("-" pour non attribué)

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

# ANNEXE B - Comportement de collecte par site

Deux axes **indépendants** gouvernent la collecte de chaque site :

- **Parallélisme** — *parallèle* (collecté en même temps que les autres) ou *séquentiel* (humain requis pendant : 2FA/CAPTCHA/code/lien e-mail → un à la fois). Tout site peut être forcé parallèle (cf. ANNEXE C).
- **Fenêtre** — les connecteurs (fetchers) démarrent **headless** (invisible). Une fenêtre n'apparaît que pour une **action en fenêtre** (saisie d'un code, CAPTCHA, login manuel — *dans la page Chrome*) ; une **2FA mobile** (validation sur le téléphone) se fait **sans fenêtre**. Dans tous les cas, l'onglet Exécution **notifie** (alerte d'authentification requise). L'ouverture d'une fenêtre Chrome pour un site persiste jusqu'à la fin de collecte du site.

| Groupe | Sites | Parallélisme | Fenêtre visible | Action utilisateur |
|---|---|---|---|---|
| **1. Sans navigateur** (API/RPC) | BTC, XMR | parallèle | — | aucune |
| **2. Navigateur, sans interaction** | NATIXIS | séquentiel par défaut | jamais | aucune (login auto, pas de 2FA) |
| **3. Repli visible automatique** | AMAZON, ETORO, KRAKEN, PAYPAL, WISE | séquentiel par défaut | à la demande | **action en fenêtre** : login manuel / CAPTCHA / code |
| **4. Headless + 2FA mobile** | BOURSOBANK, SOCGEN, DEGIRO | séquentiel par défaut | seulement si l'auto-login échoue (filet) | **2FA mobile** (téléphone) ; login manuel en fenêtre en secours |

**Groupe 3** — fenêtre à la volée quand le site réclame une action *dans la page*, puis poursuite. WISE/KRAKEN : surveillance du presse-papier pour les liens e-mail (WISE ouvre un nouvel onglet, KRAKEN navigue dans le même).

**Groupe 4** — login **automatique** (identifiants chiffrés ; clavier virtuel OCR pour les deux banques) + **2FA mobile** (validation sur le téléphone) → pas de fenêtre en régime normal ; le **filet** n'ouvre une fenêtre que si l'auto-login est impossible (identifiants absents, site modifié).

> **Connexion** (« Login ») = authentification **complète** d'un site : identification (identifiants) + éventuels 2FA / CAPTCHA / code / lien e-mail / écrans intermédiaires — pas seulement la saisie des identifiants.

# ANNEXE C - Configuration initiale

La configuration se fait par les onglets de l'App. L'ordre ci-dessous respecte les dépendances entre les éléments ; l'**interdépendance Compte ↔ Site** est décrite dans les deux sections concernées (§2 Comptes et §4 Sites).

> L'App n'est jamais un passage obligé : les fichiers de configuration restent des fichiers texte, lisibles et modifiables à la main. Le chemin en ligne de commande — utile sur une machine sans écran, ou en dépannage — est décrit dans [`Compta_plus.md`](Compta_plus.md) § *Configuration en ligne de commande*.

## 1️⃣ Devises (onglet Devises)

Ajouter les devises nécessaires (hors EUR qui est la devise de base). Pour chaque devise :

- **Code** : code standard (USD, GBP, BTC, XAU...)
- **Famille** : Fiat, Crypto ou Métal
- **Nom** : libellé libre

Les devises dérivées (ex : once d'or → gramme d'or) se définissent par une formule à partir d'une devise existante.

## 2️⃣ Comptes (onglet Comptes)

Créer un compte pour chaque compte bancaire, placement ou portefeuille. Pour chaque compte :

- **Intitulé** : nom libre (ex : "LBP Courant")
- **Devise** : devise du compte (doit exister, cf. étape 1)
- **Type** : Courant, Épargne, Titres, PEA...
- **Site** : site de collecte rattaché — ou **N/A** pour les comptes sans collecte
- **Domiciliation**, **Titulaire**, **Propriété** : attributs patrimoniaux

> **Amorçage sans boucle (Compte ↔ Site)** : un compte se rattache à un site, mais un site se configure à partir de ses comptes (étape 4). Pour éviter cette dépendance circulaire, créez d'abord le compte avec **Site = N/A** ; le rattachement effectif au site se fait en **étape 4**, lors de son activation.

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

## 3️⃣ Catégories et postes (onglet Catégories)

Les **postes budgétaires** regroupent les catégories en Fixe ou Variable (ex : Logement, Transport, Loisirs).

Les **catégories** sont les lignes du budget (ex : Loyer, Assurance auto, Restaurants). Chaque catégorie est rattachée à un poste.

Les **correspondances** (regex → catégorie) permettent la catégorisation automatique des opérations à l'import, à partir de leur libellé.

## 4️⃣ Sites (onglet Sites)

Vous n'activez que les sites correspondant à vos comptes. Pour chacun :

1. **Compte(s)** — rattacher le(s) compte(s) au site : passer leur champ **Site** de N/A à ce site (les champs techniques apparaissent alors, cf. §2).

2. **Activation** — cocher le site dans l'onglet Sites.

### Description et paramètres

Chaque site affiche une zone descriptive qui indique :

- sa procédure de connexion et les éventuelles interventions d'authentification
- les types de comptes collectables
- les **paramètres techniques** spécifiques

Certains sites possèdent des paramètres modifiables :

- **Jours max** : profondeur de collecte en jours (override du paramètre global)

- **Nb rapports** : nombre de rapports à télécharger

- **Dossier Drive**, **Compte Drive** : pour les sites collectés via Google Drive

- **Hôte SSH wallet-rpc**, **Timeout refresh**, **Timeout tunnel** : pour la collecte Monero, qui interroge un nœud distant par tunnel SSH

- **Collecte en parallèle** (case à cocher) : force le site dans le groupe de collecte parallèle (sites navigateur)

- **Fenêtre visible** *(headed)* (case à cocher) : force le navigateur en mode **visible** — réglage **par poste** (sites navigateur)

- Le cadre **Authentification** reçoit la *Réf* du site. **Sur un site neuf le champ est vide : vous y saisissez la Réf** — le nom sous lequel ranger ses identifiants dans la table chiffrée (§5), à y créer s'il n'existe pas encore. ⚠️ *Une fois posée*, la **renommer** est déconseillé : elle doit rester en correspondance avec une Réf de la 1ʳᵉ colonne de la table, sinon le site ne retrouve plus son entrée.

  >  Le site Wallet monero a deux noms d'authentification  (un pour le wallet, un pour le nœud RPC).


## 5️⃣ Paramètres (onglet Paramètres)

Ajuster si nécessaire :

- **Table chiffrée (GPG)** : bouton *Éditer* — la table des identifiants, chiffrée par GPG et protégée par un **mot de passe maître** (**P2**), dans `config_credentials.md.gpg` (un site s'y authentifie avec un **identifiant** et un **mot de passe**). **La toute première fois — si la table n'existe pas encore — *Éditer* propose de la créer et demande le mot de passe maître (saisi deux fois).** Ensuite : créer, modifier, renommer ou supprimer les entrées Réf / Identifiant / Passe ; une sauvegarde `.bak` précède chaque modification. ⚠️ Renommer la 1ʳᵉ colonne (Réf) oblige à corriger la valeur correspondante dans le cadre *Authentification* du site associé (§4)
- **Appariement** : délai max entre opérations liées, tolérance sur les montants
- **Général** : mode debug, profondeur d'import, rétention des archives
- **Opérations liées** : règles de génération automatique de contreparties (ex : retrait DAB → Espèces)



> `config_credentials.md.gpg` reste un **tableau Markdown chiffré en symétrique** : `gpg` seul suffit à l'ouvrir et à le refermer, sans l'App — voir [`Compta_plus.md`](Compta_plus.md) § *Configuration en ligne de commande*. L'App est une commodité, jamais un verrou.

## Aller plus loin

- [`Compta_glossaire.md`](Compta_glossaire.md) — glossaire du projet (métier + sigles)
- [`Compta_plus.md`](Compta_plus.md) — commandes avancées, structuration Excel, dépannage
- [`Compta_tools.md`](Compta_tools.md) — outils de maintenance et environnement git
- [`Compta_upgrade_assiste.md`](Compta_upgrade_assiste.md) — mettre à jour l'installation (mode assisté)
- [`Compta_upgrade_classeur.md`](Compta_upgrade_classeur.md) — migrations du classeur, par version
- [`Compta_dev.md`](Compta_dev.md) — documentation développeur (architecture, contributeur)
