# Wise - Documentation Technique

## Vue d'ensemble

**Type:** Compte multi-devises international
**Mode:** Semi-automatique (fetch Playwright + 2FA mobile)
**Tier 1:** `cpt_fetch_WISE.py` (Playwright Chrome, login semi-auto avec 2FA mobile)
**Tier 2:** `cpt_format_WISE.py` (conversion XLSX → CSV standard)
**Tier 3:** `cpt_update.py` (extraction ZIP automatique + import)
**URL:** https://wise.com
**Credentials:** BaWiWe-M (GPG)
**Profil Chrome:** `.chrome_profile_wise/`

## Architecture

### Comptes gérés

Wise gère 4 comptes multi-devises dans `comptes.xlsm`:

| Compte Excel | Devise | Fichier source (pattern) |
|--------------|--------|--------------------------|
| Compte Wise EUR | EUR | `statement_XXXXXXXX_EUR_YYYY-MM-DD_YYYY-MM-DD.xlsx` |
| Compte Wise USD | USD | `statement_XXXXXXXX_USD_YYYY-MM-DD_YYYY-MM-DD.xlsx` |
| Compte Wise SGD | SGD | `statement_XXXXXXXX_SGD_YYYY-MM-DD_YYYY-MM-DD.xlsx` |
| Compte Wise SEK | SEK | `statement_XXXXXXXX_SEK_YYYY-MM-DD_YYYY-MM-DD.xlsx` |

### Flux de données

```
Téléchargement manuel (ZIP)
    ↓
dropbox/WISE/statement_YYYY-MM-DD_YYYY-MM-DD.zip
    ↓
cpt_update.py (extraction automatique)
    ├─ Extrait 4 XLSX dans dropbox/WISE/
    ├─ Archive ZIP avec HDS → archives/WISE/statement_..._HDS_xxx.zip
    └─ Pour chaque XLSX:
        ├─ Appelle cpt_format_WISE.py (XLSX → CSV temporaire)
        ├─ Import CSV dans comptes.xlsm
        └─ Archive XLSX avec HDS → archives/WISE/statement_..._HDS_xxx.xlsx
```

**Important:**
- Le ZIP et les 4 XLSX sont tous archivés avec le même HDS pour traçabilité
- L'utilisateur dépose simplement le ZIP dans `dropbox/WISE/` - tout le reste est automatique
- Pas besoin d'exécuter `cpt_WISE_extract.sh` (obsolète)

## Tier 1 - Fetch Playwright (semi-auto 2FA mobile)

### Script: `cpt_fetch_WISE.py`

**Fonctionnement:**
1. Lance Chrome avec profil persistant (`.chrome_profile_wise/`)
2. Navigue vers la page des relevés
3. Si non connecté : remplit email/password (GPG `BaWiWe-M`)
4. **2FA mobile** : l'utilisateur approuve dans l'appli Wise ("Oui, c'est moi")
5. Clique "Créer un Relevé", configure dates/devises/format
6. Clique "Générer" puis "Télécharger"
7. Sauve le ZIP dans `dropbox/WISE/`

**Usage:**
```bash
./cpt_fetch_WISE.py         # Mode normal
./cpt_fetch_WISE.py -v      # Mode verbeux
```

### Procédure manuelle (secours)

Si le fetch automatique échoue, procédure manuelle :

1. **Connexion:**
   - URL: https://wise.com/balances/statements/balance-statement
   - Login/password: credentials GPG `BaWiWe-M`
   - 2FA mobile: "Approuvez cette connexion en ouvrant l'appli Wise et en appuyant sur « Oui, c'est moi »"

2. **Génération du relevé:**
   - Cliquer sur "Créer un Relevé"
   - Sélectionner date début (aujourd'hui - 90 jours recommandé)
   - Sélectionner date fin (aujourd'hui)
   - **Sélectionner toutes les devises** (EUR, USD, SGD, SEK)
   - Format: **XLSX**
   - Cliquer sur "Générer"

3. **Téléchargement:**
   - Nouvelle page → bouton "Télécharger"
   - Fichier ZIP obtenu: `statement_YYYY-MM-DD_YYYY-MM-DD.zip`
   - Placer dans `dropbox/WISE/`

### Contenu du ZIP

Le ZIP contient 4 fichiers XLSX (un par devise):

```
statement_10000001_EUR_2024-01-01_2025-12-28.xlsx
statement_10000004_USD_2024-01-01_2025-12-28.xlsx
statement_10000003_SGD_2024-01-01_2025-12-28.xlsx
statement_10000002_SEK_2024-01-01_2025-12-28.xlsx
```

**Pattern:** `statement_<ACCOUNT_ID>_<CURRENCY>_<START_DATE>_<END_DATE>.xlsx`

## Tier 2 - Format script

### Script: `cpt_format_WISE.py`

**Fonction:** Parse un fichier XLSX Wise et génère un CSV au format standard 9 colonnes.

**Input:**
- XLSX: `dropbox/WISE/statement_XXXXXXXX_<CURRENCY>_YYYY-MM-DD_YYYY-MM-DD.xlsx`

**Output:**
- CSV standard 9 colonnes sur stdout (capturé par `cpt_update.py`)

**Traitement:**

1. **Extraction métadonnées du nom de fichier:**
   - Pattern: `statement_<ACCOUNT_ID>_<CURRENCY>_<START_DATE>_<END_DATE>.xlsx`
   - Devise détectée: EUR, USD, SGD, SEK
   - Mapping automatique vers `Compte Wise <CURRENCY>`

2. **Parsing XLSX:**
   - Feuille: "All transactions" (colonnes B=Date, D=Montant, E=Devise, F=Description, H=Solde)
   - Filtrage: opérations < `max_days_back` jours (configurable `config.ini [WISE] max_days_back`)
   - Inversion ordre: Wise exporte du plus récent au plus ancien → inversion pour ordre chronologique

3. **Génération CSV:**
   - Format: `Date;Libellé;Montant;Devise;Equiv;Réf;Catégorie;Compte;Commentaire`
   - Ligne finale: `#Solde` avec solde du compte (colonne H ligne 2)

### Structure XLSX Wise

**Feuille:** `All transactions`

**Colonnes importantes (1-based):**

| Col | Nom | Description |
|-----|-----|-------------|
| 2 | Date | Date de l'opération (YYYY-MM-DD HH:MM:SS) |
| 4 | Montant | Montant signé (négatif = débit, positif = crédit) |
| 5 | Devise | Code devise (EUR, USD, SGD, SEK) |
| 6 | Description | Libellé de l'opération |
| 8 | Solde actuel | Solde après transaction |

**Ordre:** Du plus récent (ligne 2) au plus ancien (dernière ligne)

**Types d'opérations observées:**
- `ACCRUAL_CHARGE`: Frais mensuels Wise Assets Europe
- `TRANSFER`: Transferts vers comptes externes
- `CONVERSION`: Conversions de devises (EUR ↔ SGD, etc.)
- `SELL`: Ventes d'actifs (fonds d'investissement Wise)

### Format de sortie

**Fichier:** `operations_wise_{devise}.tmp.csv` (4 fichiers générés)

**Format:** 9 colonnes standard
```csv
Date;Libellé;Montant;Devise;Equiv;Réf;Catégorie;Compte;Commentaire
03/12/2025;Frais Wise Assets Europe;-0.01;EUR;;-;;Compte Wise EUR;
30/10/2025;Argent envoyé à Barnabé;-1000.00;EUR;;-;;Compte Wise EUR;
03/12/2025;#Solde Compte Wise EUR;-16.17;EUR;;-;;Compte Wise EUR;
```

**Dernière ligne:** `#Solde` avec le solde le plus récent (ligne 2 du XLSX).

## Configuration

### config.ini

```ini
[WISE]
name = Wise
base_url = https://wise.com
credential_id = BaWiWe-M
max_days_back = 90
```

**Paramètres:**
- `base_url`: URL de base Wise (active le fetch automatique via `cpt_fetch.py`)
- `credential_id`: Identifiant GPG pour login automatique
- `max_days_back`: Limite temporelle pour import (90 jours recommandé)

### Sites enabled

```ini
[sites]
enabled = SOCGEN,NATIXIS,BOURSOBANK,DEGIRO,ETORO,WISE
```

## Workflow utilisateur

### Import standard

```bash
# 1. Télécharger ZIP depuis wise.com
# 2. Placer dans dropbox/WISE/
cp ~/Downloads/statement_2024-01-01_2025-12-28.zip dropbox/WISE/

# 3. Import (lance automatiquement cpt_format_WISE.py)
./cpt_update.py -v

# 4. Vérifier résultats
./cpt.py --status
```

### Import avec cpt.py

```bash
# Import complet (si WISE activé dans config)
./cpt.py --update-only

# Vérifier archives
ls -lh archives/WISE/
```

## Particularités techniques

### Extraction automatique du ZIP

Le script `cpt_update.py` gère automatiquement l'extraction ZIP:
- Détection ZIP dans `dropbox/WISE/` (méthode `extract_wise_zips()`)
- Extraction des 4 fichiers XLSX dans `dropbox/WISE/`
- Archivage du ZIP avec HDS dans `archives/WISE/`
- Traitement séquentiel des 4 XLSX par `cpt_format_WISE.py`
- Archivage des XLSX avec HDS dans `archives/WISE/`

**Avantage:**
- Utilisateur dépose uniquement le ZIP → tout le reste est automatique
- Pas besoin d'exécuter `cpt_WISE_extract.sh` (script obsolète conservé pour compatibilité)
- ZIP et XLSX archivés avec le même HDS pour traçabilité complète

### Multi-devises

Wise gère nativement 4 devises avec 4 comptes séparés dans Excel:
- Pas de conversion EUR (colonne `Equiv` vide)
- Chaque devise = compte distinct = fichier CSV distinct
- Pas de matching cross-currency automatique (conversions manuelles dans Wise)

### Wise Assets Europe

Wise propose des investissements (fonds indexés):
- Opérations de type `SELL` avec ISIN (ex: IE00B41N0724)
- Frais mensuels `ACCRUAL_CHARGE`
- Ces opérations sont importées normalement (pas de traitement spécial)

## Limites et contraintes

### Fetch semi-automatique (2FA mobile)

**Raison:** 2FA mobile obligatoire (validation dans l'appli Wise)

**Conséquence:** Le script `cpt_fetch_WISE.py` automatise tout sauf la validation 2FA mobile, qui reste manuelle (appuyer sur "Oui, c'est moi" dans l'appli).

### Limite temporelle recommandée

**max_days_back = 90** pour éviter:
- Import de doublons avec anciennes opérations manuelles
- Surcharge Excel avec historique trop long

**Ajustable** selon besoin (30, 60, 120 jours).

### Format XLSX uniquement

Wise propose CSV et XLSX, mais seul XLSX est supporté (plus riche en métadonnées).

## Tests et validation

### Test d'import complet

```bash
# 1. Télécharger ZIP depuis wise.com (voir Tier 1)

# 2. Placer ZIP dans dropbox/WISE/
cp ~/Downloads/statement_2024-01-01_2025-12-28.zip dropbox/WISE/

# 3. Import automatique (extraction + conversion + import)
./cpt_update.py -v

# Résultat attendu:
# ✓ Extraction ZIP Wise: statement_2024-01-01_2025-12-28.zip
# ✓   Extrait: statement_10000001_EUR_2024-01-01_2025-12-28.xlsx
# ✓   Extrait: statement_10000002_SEK_2024-01-01_2025-12-28.xlsx
# ✓   Extrait: statement_10000003_SGD_2024-01-01_2025-12-28.xlsx
# ✓   Extrait: statement_10000004_USD_2024-01-01_2025-12-28.xlsx
# ✓   ZIP archivé: statement_2024-01-01_2025-12-28.zip
# ✓ ZIP Wise: 4 fichier(s) XLSX extrait(s)
# [... traitement normal des 4 XLSX ...]
# Opérations ajoutées:
#   Compte Wise EUR: X
#   Compte Wise USD: Y
#   Compte Wise SGD: Z
#   Compte Wise SEK: W

# 4. Vérifier archives
ls -lh archives/WISE/

# 5. Vérifier Contrôles
./cpt_controles.py -v

# 6. Rollback si nécessaire
./cpt.py --fallback
```

### Vérifications

- [ ] ZIP extrait automatiquement (4 XLSX créés dans dropbox/WISE/)
- [ ] ZIP archivé dans `archives/WISE/` avec HDS
- [ ] 4 XLSX archivés dans `archives/WISE/` avec HDS (même timestamp)
- [ ] Opérations importées pour chaque devise
- [ ] Opérations filtrées correctement (< 90 jours par défaut)
- [ ] Pas d'erreur COMPTES dans Contrôles
- [ ] `dropbox/WISE/` vide après import

## Troubleshooting

### Erreur "Cannot extract currency from filename"

**Cause:** Nom de fichier XLSX non conforme au pattern Wise.

**Solution:** Vérifier que les fichiers suivent le pattern `statement_XXXXXXXX_<CURRENCY>_YYYY-MM-DD_YYYY-MM-DD.xlsx`.

### Soldes incohérents

**Cause:** Opérations manuelles anciennes avec libellés différents.

**Solution:**
1. Vérifier colonne K (Écart) dans feuille Contrôles
2. Identifier opérations en doublon
3. Supprimer doublons manuels ou ajuster `max_days_back`

### Fichiers temporaires non nettoyés

**Cause:** Erreur pendant traitement.

**Solution:**
```bash
rm -rf dropbox/WISE/.wise_temp/
rm -f dropbox/WISE/*.tmp.csv
```
