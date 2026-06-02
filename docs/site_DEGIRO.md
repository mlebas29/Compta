# DEGIRO - Documentation technique

## Vue d'ensemble

**Site :** https://degiro.fr
**Type :** Courtier en ligne (compte-titre)
**Collecte :** Opérations, Positions, Soldes

## Architecture

**Tier 1 (fetch):** `cpt_fetch_DEGIRO.py`
- Playwright Chrome avec profil persistant `.chrome_profile_degiro/`
- Login auto (GPG) + 2FA via appli mobile DEGIRO
- Téléchargement Portfolio.csv (positions)
- Téléchargement Account.csv (opérations)

**Tier 2 (format):** `cpt_format_DEGIRO.py` (monoscript)
- **Mode opérations** : Conversion Account.csv → format standard 9 champs
  - Filtrage des opérations internes
  - Catégorisation (Achat/Vente titres, Coupon, Impôts, Frais)
- **Mode positions** : Conversion Portfolio.csv → format 4 champs
  - Extraction des valorisations titres
  - Solde Réserve depuis soldes_comptes_parsed.csv

**Tier 3 (update):** `cpt_update.py` (script générique)
- Import dans Excel
- Génération automatique des opérations symétriques Titres
- Mise à jour Plus_value (positions)
- Archivage avec HDS

## Configuration

**Dans `config.ini` :**
```ini
[DEGIRO]
name = DEGIRO
base_url = https://degiro.fr
credential_id = BaDEWe-M
```

**Détection automatique :**
- Script fetch : `cpt_fetch_DEGIRO.py`
- Script format : `cpt_format_DEGIRO.py`
- Répertoire dropbox : `dropbox/DEGIRO/`
- Répertoire archives : `archives/DEGIRO/`

## Authentification

### Login standard
- URL: https://degiro.fr
- Credentials GPG: `BaDEWe-M`
- Champs: Nom d'utilisateur + Mot de passe
- Bouton: `button[name='loginButtonUniversal']`

### 2FA (Application mobile)
Après soumission du formulaire, DEGIRO demande une validation via l'application mobile.

**Comportement du script :**
- Attend automatiquement (max 180s)
- Détecte la redirection : URL contient `trader.degiro.nl` et ne contient plus `/login`

### Session persistante
- Profil Chrome: `.chrome_profile_degiro/`
- Évite 2FA répétés (session mémorisée)
- **Important:** Ne PAS supprimer ce répertoire

## Pages et données collectées

### 1. Portfolio (positions)

**Export CSV :**
1. Cliquer bouton export
2. Popup → cliquer bouton CSV
3. Téléchargement: `Portfolio.csv`

**Contenu :** Positions des titres (ex: Dassault, Thales)

**Fichier:** `Portfolio.csv` (nom original DEGIRO)

### 2. Account (opérations)

**URL avec dates personnalisées** : 6 mois en arrière → date du jour

**Export CSV :**
1. Cliquer bouton export
2. Popup → cliquer bouton CSV
3. Téléchargement: `Account.csv`

**Structure CSV brut (depuis décembre 2025) :**
```
Date,Heure,Date de,Produit,Code ISIN,Description,FX,Mouvements,,Solde,,ID Ordre
```

**Fichier:** `Account.csv` (nom original DEGIRO)

## Filtrage des opérations

Le script `cpt_format_DEGIRO.py` **exclut** 4 types d'opérations internes :

1. **Virements internes** : `votre Compte Espèces` (mouvement vers/depuis compte bancaire externe)
2. **Cash Sweep automatique** : `Degiro Cash Sweep Transfer`
3. **Intérêts Flatex** : `Flatex Interest Income`
4. **Dépôt initial Flatex** : `Dépôt flatex`

**Toutes les autres opérations sont conservées :**
- Achats/ventes de titres
- Dividendes
- Frais de courtage
- Virements entrants/sortants

## Formats de sortie

### Format opérations (9 champs)

```csv
Date;Libellé;Montant;Devise;Equiv;Réf;Catégorie;Compte;Commentaire
06/03/2025;THALES SA Achat 40 Thales SA@253,6 EUR (FR0000121329);-10144.00;EUR;;;Achat titres;Portefeuille DEGIRO Réserve;
04/12/2025;THALES SA Dividende;38.00;EUR;;;Coupon;Portefeuille DEGIRO Réserve;
04/12/2025;THALES SA Impôts sur dividende;-9.50;EUR;;;Impôts revenu;Portefeuille DEGIRO Réserve;
11/12/2025;Relevé compte;117.16;EUR;;;#Solde;Portefeuille DEGIRO Réserve;
```

**Champs :**
- **Date:** DD/MM/YYYY
- **Libellé:** Produit + Description (ex: "THALES SA Achat 40 Thales...")
- **Montant:** Montant brut (EUR, négatif pour achats)
- **Devise:** EUR
- **Réf:** Vide (rempli par cpt_update.py pour opérations symétriques Titres)
- **Catégorie:** Achat titres, Vente titres, Coupon, Impôts revenu, Frais bancaires, #Solde
- **Compte:** `Portefeuille DEGIRO Réserve` (mouvements cash), `Portefeuille DEGIRO Titres` (généré automatiquement)

### Format positions (4 champs)

```csv
Date;Ligne;Montant;Compte
12/12/2025;DASSAULT AVIATION SA;270.20;Portefeuille DEGIRO Titres
12/12/2025;THALES SA;9140.00;Portefeuille DEGIRO Titres
12/12/2025;#Solde Réserve;117.16;Portefeuille DEGIRO Réserve
```

**Utilisation :** Met à jour la feuille Excel "Plus_value" (colonnes Date SOLDE et SOLDE).

## Fichiers générés

### Dans dropbox/DEGIRO/

1. **Account.csv** : Opérations brutes (nom original DEGIRO)
2. **Portfolio.csv** : Positions titres (nom original DEGIRO)
3. **soldes_comptes_parsed.csv** : Soldes Titres + Réserve

### Après import (archives/DEGIRO/)

Tous les fichiers sont archivés avec timestamp HDS :
- `Account_HDS_20251212_103045.csv`
- `Portfolio_HDS_20251212_103045.csv`
- `soldes_comptes_parsed_HDS_20251212_103045.csv`

## Workflow de test

```bash
cd ~/Compta
export COMPTA_MODE=test

# Test complet
./cpt.py --sites DEGIRO -v

# Vérifier fichiers générés
ls -lh dropbox/DEGIRO/

# Vérifier Excel
libreoffice comptes.xlsm

# Vérifier contrôles
./cpt_controles.py -v
```

## Dépannage

### Erreur "2FA timeout"

**Symptôme:** `❌ Timeout 2FA - validation non reçue`

**Solution:**
1. Vérifier que l'application DEGIRO est installée sur mobile
2. Autoriser les notifications push
3. En mode DEBUG, prendre le temps de valider manuellement

### Erreur "Bouton export non trouvé"

**Causes possibles:**
- Page non complètement chargée
- DEGIRO a modifié l'interface
- Connexion non établie

**Solution:**
1. Activer DEBUG=true pour voir la page
2. Vérifier que la navigation réussit
3. Mettre à jour le sélecteur CSS si nécessaire

### Soldes non extraits

**Symptôme:** `⚠ Impossible d'extraire tous les soldes`

**Solution:**
1. Activer DEBUG=true
2. Examiner `degiro_04_homepage_soldes.html`
3. Ajuster les regex dans `extract_soldes()` si le format HTML a changé

## Notes importantes

1. **2FA systématique** - Première connexion ou après expiration de session
2. **Profil Chrome critique** - Ne pas supprimer `.chrome_profile_degiro/`
3. **Format CSV évolutif** - DEGIRO modifie parfois la structure des CSV (voir décembre 2025)
4. **Filtrage automatique** - Les virements internes et opérations techniques sont exclus
5. **Période de collecte** - Année en cours (1er janvier → aujourd'hui)
