# Wise — Documentation technique

## Vue d'ensemble

**Type :** compte de paiement multi-devises international
**Mode :** semi-automatique (fetch Playwright + 2FA mobile)
**Tier 1 :** `cpt_fetch_WISE.py` — login semi-auto (GPG) + validation push mobile ; export **CSV**
**Tier 2 :** `cpt_format_WISE.py` — décompose le CSV « all-transactions » en jambes par devise + lit les soldes
**Tier 3 :** `cpt_update.py` — déduplication + archivage + import
**URL :** https://wise.com
**Credentials :** `BaWiWe-M` (GPG)
**Profil Chrome :** `.chrome_profile_wise/`

> **Refonte #131 (v5.14.0)** — l'ancien assistant « relevé XLSX » (un ZIP de N fichiers XLSX), devenu inaccessible côté Wise, a été **remplacé par l'export CSV « all-transactions » en 1 clic**. Le flux normal ne produit **plus de ZIP** ; le chemin ZIP/XLSX ne subsiste qu'en **repli manuel legacy** (cf. section dédiée).

## Architecture

### Comptes gérés

Un compte `comptes.xlsm` **par devise** (jar Wise). Le rattachement se fait par la devise détectée → `Compte Wise <DEVISE>`.

### Flux de données (normal, CSV)

```
cpt_fetch_WISE.py  (Playwright + 2FA mobile)
    ├─ /all-transactions → Télécharger → CSV
    │     → dropbox/WISE/transaction-history.csv   (toutes devises, toutes opérations)
    └─ page du groupe multi-devises → jars par devise
          → dropbox/WISE/wise_balances.csv         (solde courant par devise)
    ↓
cpt_format_WISE.py
    ├─ transaction-history.csv → jambes par devise (format 9 champs)
    └─ wise_balances.csv       → une ligne #Solde par compte
    ↓
cpt_update.py  (dédup + import + archivage HDS des CSV)
```

## Tier 1 — Fetch Playwright (semi-auto, 2FA mobile)

`cpt_fetch_WISE.py` :

1. Lance Chrome avec profil persistant (`.chrome_profile_wise/`, cookies de session conservés).
2. **Login** si nécessaire : email / mot de passe (GPG `BaWiWe-M`).
3. **2FA mobile** (systématique) : approuver dans l'appli Wise (« Oui, c'est moi »). Occasionnellement un **2ᵉ facteur email** s'ajoute (typiquement nouvel appareil) : clic droit sur le bouton d'approbation du mail → *Copier le lien* ; le script surveille le presse-papier et ouvre le lien dans un nouvel onglet.
4. **Opérations** : `/all-transactions` → bouton **Télécharger** → tiroir « Format du fichier » → **CSV** → download → `transaction-history.csv`.
5. **Soldes** : `/home` → identifiant du groupe multi-devises → `/groups/<id>` → lecture des jars par devise → `wise_balances.csv`.

```bash
./cpt_fetch_WISE.py        # normal
./cpt_fetch_WISE.py -v     # verbeux (dump DOM aux étapes clés)
```

## Tier 2 — Format (`cpt_format_WISE.py`)

**Entrées** (`dropbox/WISE/`) : `transaction-history.csv` (opérations) + `wise_balances.csv` (soldes).
**Sortie** : format standard 9 champs (`Date;Libellé;Montant;Devise;Equiv;Réf;Catégorie;Compte;Commentaire`), décomposé en une jambe par devise.

### Décomposition du CSV « all-transactions »

`parse_all_transactions_csv` répartit les lignes selon leur type :

- **ACCRUAL_CHARGE** — frais → 1 jambe (débit).
- **TRANSFER IN / OUT** — transfert → 1 jambe ; la cible d'un OUT est **toujours externe** (même en conversion).
- **BALANCE_TRANSACTION / NEUTRAL** — change interne → **2 jambes** (`ref='-'`) ; les frais sont **inclus dans le débit**.

### Soldes

`wise_balances.csv` → une ligne **`#Solde`** par compte (solde courant du jar). ⚠ Le jar **EUR** est lu depuis la page **groupe** (et non depuis `/home`, où l'EUR est la devise de base non-jar, d'un montant sans rapport avec le vrai jar EUR).

## Repli manuel (legacy ZIP / XLSX)

Le format accepte encore l'ancien format si on le dépose **à la main** :

- Déposer un `statement_*.zip` (ou directement des `statement_*.xlsx`) dans `dropbox/WISE/` → `extract_wise_zips()` extrait puis parse les XLSX (feuille « All transactions »).
- **Exclusivité** : si un CSV « all-transactions » est présent, le legacy XLSX est **ignoré** (anti-doublon).
- Ce chemin sert surtout au **TNR pipe** (fixtures XLSX conservées) et au dépannage ; **il n'est plus alimenté par le fetch**.

## Configuration

```ini
[WISE]
name = Wise
base_url = https://wise.com
credential_id = BaWiWe-M
max_days_back = 90
```

- `base_url` : active le fetch automatique (`cpt_fetch.py`).
- `credential_id` : identifiant GPG pour le login.
- `max_days_back` : profondeur d'import (défaut 90 j) ; la **déduplication à l'import** écarte les doublons.

## Particularités

- **Multi-devises** : un compte distinct par devise, pas de conversion EUR (colonne `Equiv` vide). Les conversions internes Wise apparaissent en **2 jambes appariées** (`ref='-'`).
- **Wise Assets** : investissements (frais `ACCRUAL_CHARGE`, ventes `SELL` avec ISIN) importés normalement, sans traitement spécial.
- **SPA** : la page ne passe jamais en `networkidle` → le fetch attend des **sélecteurs ciblés** (`wait_for_function`), pas l'idle réseau.
- **Décimales** : `wise_balances.csv` est écrit avec le point décimal (virgule Wise → point) pour éviter la collision avec le séparateur CSV.

## Troubleshooting

- **Sélecteur cassé / étape bloquée** : lire les dumps `logs/debug/wise_step_*.html` (+ PNG en mode `full`) — le fetch dumpe à l'échec ; `-v` enrichit.
- **Soldes incohérents** : opérations manuelles anciennes aux libellés divergents → vérifier l'écart COMPTES dans la feuille Contrôles, ajuster `max_days_back`.
- **Rollback** : `./cpt_update.py --fallback` (restaure le classeur **et** les fichiers `dropbox/`).
