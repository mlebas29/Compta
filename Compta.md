# 1. Présentation

Voir **README.md** pour la présentation du projet, l'installation et l'utilisation.

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

## Collecte

La collecte est déclenchée pour les sites qui auront été sélectionnés. Un mot de passe maître est nécessaire pour accéder aux identifiants et mots de passe de sites. Les fichiers sont téléchargés dans le dossier de collecte local (`./dropbox`).

Chaque site est décrit dans l'application (Onglet Sites). On y trouve notamment une procédure manuelle de secours pour la collecte et des indications pour les procédures 2FA.

Pour certains sites le navigateur Chrome est rendu visible afin de permettre une **intervention manuelle** au moment de la connexion; par exemple saisie d'un code dans une page, ou résolution d'un CAPTCHA. Cf. ANNEXE B

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

Avant la première collecte, le classeur doit être configuré pour refléter les comptes, devises et sites de l'utilisateur. Cette configuration se fait entièrement via l'App, sans toucher au fichier Excel.

Voir **ANNEXE C** pour le détail de la configuration initiale (comptes, devises, catégories, sites, identifiants).

Une fois la configuration faite, elle n'a besoin d'être reprise que lors de l'ouverture ou la fermeture d'un compte, l'ajout d'une devise, etc.

#### Étape 1 - exécution de l'App

Lancer l'App Comptabilité (Symbole Euro)

![](cpt_gui_export.png)

La fenêtre qui s'ouvre présente l'onglet Exécution :

![](images/Compta.png)

Dans l'onglet Exécution, sélectionner les sites voulus puis cliquer sur le bouton "Collecte". L'App demande le mot de passe maitre dans une fenêtre dédiée, puis visite tous les sites sélectionnés pour collecter les données, ce qui peut prendre plusieurs minutes.

> NB : Une présence est nécessaire avec le mobile car certains sites peuvent déclencher une procédure 2FA pendant la collecte.

Quand la collecte est terminée, cliquer sur "Import" pour mettre à jour le fichier **comptes.xlsm** avec les données collectées. On peut aussi attendre pour relancer une collecte avec d'autres sites qui manqueraient.

#### Étape 2 - compléments manuels

Le fichier  **comptes.xlsm** peut alors être ouvert sous LibreOffice, pour une session manuelle afin de :

* vérifier la bonne collecte et l'import des données (opérations, valorisations)

* vérifier les affectations d'opérations aux catégories de dépenses/revenus

* vérifier les appariements d'opérations (virements, changes, titres)

* vérifier l'absence d'erreur (Cf. ANNEXE A - Contrôles Excel)

* corriger si nécessaire

#### Étape 3 - finalisation

La dernière étape consiste à publier le classeur via le bouton "Publier Classeur".

# 4. Dépendances

L'app dépend de :

- Linux
- Python avec plusieurs modules, en particulier PyTk pour l'App graphique
- Chrome et Playwright pour la collecte et son automatisation
- LibreOffice pour le tableur

Les collectes Bitcoin sont effectuées directement depuis la blockchain à partir des adresses publiques des portefeuilles

La collecte Monero Wallets exige un nœud local

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

La cellule A1 est une synthèse de 6 positions (concaténation de 6 symboles) :

| Position | Label | OK | Warning | Erreur | Signification |
|----------|-------|----|---------|--------|---------------|
| 1 | Comptes (soldes) | `✓` | | `✗` | Écarts entre soldes calculés et soldes relevés |
| 2 | Catégories | `✓` | | `✗` | Opération(s) sans catégorie connue |
| 3 | Dates | `✓` | `⚠` | | Date hors période attendue |
| 4 | Appariements | `✓` | `⚠` | | Appariements incomplets |
| 5 | Balances | `✓` | `⚠` | | Problème de balances |
| 6 | Inconnus (comptes) | `✓` | | `✗` | Compte(s) absent(s) de la feuille Avoirs |

Exemples : `✓✓✓⚠⚠✓` = seuls appariements et balances à vérifier. `✗✓✓⚠✓✓` = erreur soldes + appariements incomplets.

Diagnostic détaillé : `./tool_controles.py` (ou `-v` pour le mode verbeux).

**Barre de statut GUI :**

L'App affiche en permanence une barre de statut en bas de fenêtre avec deux zones :
- **Statut** (gauche) : état des Contrôles, coloré selon 3 niveaux — vert (OK), orange (appariements/incohérence), rouge (COMPTES/CATÉGORIES/INCONNUS). Cliquable pour afficher le détail.
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
| **BB/SG/PEE/DEGIRO** | Selon script (2FA, OCR...) | Variable |

- Si session active (profil persistant) : reste headless, pas d'interaction
- Wise : clipboard surveille liens wise.com, ouvre dans nouvel onglet
- Kraken : clipboard surveille liens kraken.com, navigue dans même onglet

# ANNEXE C - Configuration initiale

La configuration se fait via les onglets de l'App. L'ordre ci-dessous respecte les dépendances entre les éléments.

## 1. Identifiants de connexion

Les identifiants des sites financiers sont stockés chiffrés par GPG. Remplir le template `config_credentials.md` avec les identifiants de chaque site, puis chiffrer :

```bash
gpg -c config_credentials.md
rm config_credentials.md
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

Lorsqu'un compte est rattaché à un site, des **champs techniques** supplémentaires apparaissent selon le site. Ils permettent au collecteur d'identifier le compte sur le site bancaire :

| Site | Champs techniques |
|------|------------------|
| **SOCGEN** | Type SG (principal / épargne / assurance_vie), Numéro, ID technique, Clé fichiers (selon le type) |
| **BOURSOBANK** | Numéro de compte |
| **BTC** | Clé wallet, Adresses publiques |
| **XMR** | Clé, Nom du portefeuille |

Ces champs sont propres à chaque site et n'apparaissent que pour les comptes rattachés.

Les biens matériels (immobilier, mobilier) se créent aussi dans cet onglet (bouton "Bien").

## 4. Catégories et postes (onglet Catégories)

Les **postes budgétaires** regroupent les catégories en Fixe ou Variable (ex : Logement, Transport, Loisirs).

Les **catégories** sont les lignes du budget (ex : Loyer, Assurance auto, Restaurants). Chaque catégorie est rattachée à un poste.

Les **correspondances** (regex → catégorie) permettent la catégorisation automatique des opérations à l'import, à partir de leur libellé.

## 5. Sites (onglet Sites)

Activer les sites de collecte correspondant aux comptes créés. Chaque site affiche :

- sa procédure de connexion et les éventuelles interventions 2FA
- les comptes rattachés
- les paramètres spécifiques

Certains sites possèdent des paramètres modifiables :

- **Jours max** : profondeur de collecte en jours (override du paramètre global)
- **Nb rapports** : nombre de rapports à télécharger
- **Dossier Drive**, **Compte Drive** : pour les sites collectés via Google Drive (ex : Yuh)
- **CLI Monero**, **Dossier wallets**, **Timeout wallet** : pour la collecte Monero

## 6. Paramètres (onglet Paramètres)

Ajuster si nécessaire :

- **Appariement** : délai max entre opérations liées, tolérance sur les montants
- **Général** : mode debug, profondeur d'import, rétention des archives
- **Opérations liées** : règles de génération automatique de contreparties (ex : retrait DAB → Espèces)
- **Solde auto** : comptes dont le solde est calculé à partir d'une catégorie trigger
