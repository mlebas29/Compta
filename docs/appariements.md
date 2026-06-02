# Système d'appariements - Documentation technique

## Vue d'ensemble

Le système d'appariements relie automatiquement les opérations d'une même transaction financière via des **références d'appariement** (exemple: `V100`, `btc12`, `or5`).

**Scripts concernés :**
- **`cpt_update.py`** : Génère et attribue automatiquement les références lors de l'import (Tier 3)
- **`tool_refs.py`** : Audit et normalisation a posteriori des références dans Excel
- **`category_mappings.py`** : Définit les catégories d'opérations qui déterminent les classes de références

---

## 1. Références d'appariement

### 1.1 Structure

Une référence est constituée d'un **préfixe de classe** suivi d'un **numéro séquentiel** :

| Référence | Classe | Description |
|-----------|--------|-------------|
| `V100` | V | Virement EUR entre comptes |
| `btc12` | btc | Change EUR ↔ Bitcoin |
| `or5` | or | Change EUR ↔ Or Premium |
| `orjo3` | orjo | Achat métaux (Or Joaillerie) |
| `usd8` | usd | Change EUR ↔ USD |
| `t42` | t | Opération Titres (achat/vente/arbitrage) |

### 1.2 Classes de références

La classe reflète le type de transaction et détermine les règles d'appariement.

#### Détection automatique de la classe (tool_refs.py)

```python
# Règle : analyse des catégories et devises (hors frais bancaires/ajustements)

# Catégorie Change - classe déterminée par la devise de l'opération positive
if 'Change' in catégories:
    if devise == 'BTC' → classe = 'btc'
    if devise == 'XMR' → classe = 'xmr'
    if devise in ['OrPr', 'AgPr'] → classe = 'or' ou 'ag'
    if devise == 'USD' → classe = 'usd'
    if devise == 'CHF' → classe = 'chf'
    # etc.

# Catégorie Achat métaux - métaux physiques (bijoux)
if 'Achat métaux' in catégories → classe = 'orjo' ou 'agjo' selon devise

# Titres (actions, fonds, PEE)
if 'titres' ou 'Arbitrage' ou 'Rachat' in catégories → classe = 't'

# Virements (par défaut si aucune classe spécifique)
if 'Virement' in catégories → classe = 'V'
```

**Note importante :** Les frais bancaires suivent la classe de la transaction principale (exemple : frais bancaires lors d'un achat Bitcoin → classe `btc`).

#### Conventions de casse

| Classe | Casse | Exemple |
|--------|-------|---------|
| V (Virements) | Majuscule | `V100` |
| t (Titres) | Minuscule | `t42` |
| Crypto/Métaux/Devises | Minuscule | `btc12`, `or5`, `usd8` |

**Typo corrigée automatiquement :** `0r508` → `or508` (zéro vs lettre O)

---

## 2. Colonne Equiv Euro

### 2.1 Objectif

La colonne **Equiv Euro** contient l'équivalent EUR d'une opération dans une autre devise/crypto/métal. Elle permet d'apparier des opérations avec **montants différents** (taux de change).

**Principe clé :** Equiv Euro est **TOUJOURS en EUR**, quel que soit la devise native de l'opération.

### 2.2 Remplissage par les format scripts (Tier 2)

#### Via category_mappings (option `equiv`)

```python
# Exemple : Change Or chez un courtier métaux
(r'POUR: COURTIER OR', 'Change', {'ref': '-', 'equiv': 'amount'})

# Si equiv='amount' → copier le montant EUR dans la colonne Equiv
if opts.get('equiv') == 'amount':
    equiv = montant_str  # Montant déjà en EUR
```

#### Calcul manuel pour échanges multi-devises

**Exemple : eToro Money EUR → Réserve USD**

**Côté EUR (Money account) :**
```csv
Date;Libellé;Montant;Devise;Equiv;Réf;Catégorie;...
24/09/2025;eToro Trading Platform DPT;-900.00;EUR;-900.00;-;Change;...
```

**Côté USD (Réserve account) :**
```csv
Date;Libellé;Montant;Devise;Equiv;Réf;Catégorie;...
24/09/2025;Dépôt 900.00 EUR eToroMoney;1050.06;USD;900.00;-;Change;...
```

**Résultat de l'appariement :**
- Equiv EUR correspondent : `-900` et `+900` ✓
- Référence attribuée : `usd8` (classe déterminée par devise USD)
- Taux de change calculé : `1050.06 / 900 = 1.1667 USD/EUR`

### 2.3 Règles de remplissage

| Cas | Montant | Devise | Equiv | Exemple |
|-----|---------|--------|-------|---------|
| Change EUR (débit) | -900 | EUR | -900 | Change (virement courtier or) |
| Change Actif (crédit) | +0.25 | BTC | +900 | Change (réception crypto) |
| Change USD (crédit) | +1050 | USD | +900 | Change (dépôt eToro) |
| Opération sans contrepartie | +50 | USD | *(vide)* | Dividende USD |

**Important :** Ne PAS remplir Equiv pour :
- Virements EUR → EUR (même devise)
- Opérations Titres (achats/ventes en EUR)
- Opérations isolées sans échange

---

## 3. Transactions à somme nulle

### 3.1 Montant vs Equiv Euro

| Type | Champ | Somme nulle ? | Exception |
|------|-------|---------------|-----------|
| Montant | Montant | ⚠ Presque | Frais possibles |
| Equiv Euro | Equiv | ✓ Toujours | Aucune |

**Exemple avec frais :**
```csv
# Virement avec frais bancaires (3 opérations, référence V100)
Date;Libellé;Montant;Equiv;Réf;Catégorie;Compte
10/01/2025;Virement sortant;-1000.00;;V100;Virement;Compte SG
10/01/2025;Frais virement;-2.50;;V100;Frais bancaires;Compte SG
12/01/2025;Virement entrant;1000.00;;V100;Virement;Compte BB

# Somme Montant = -1000 - 2.50 + 1000 = -2.50 (frais)
# Somme Equiv = (vides) → N/A
```

**Exemple échange crypto :**
```csv
# Achat Bitcoin (2 opérations, référence btc12)
Date;Libellé;Montant;Devise;Equiv;Réf;Catégorie;Compte
15/03/2025;Achat BTC;-5000.00;EUR;-5000.00;btc12;Change;Kraken Money
15/03/2025;Achat BTC;0.12;BTC;5000.00;btc12;Change;Kraken Réserve

# Somme Montant = -5000 + 0.12 ≠ 0 (devises différentes)
# Somme Equiv = -5000 + 5000 = 0 ✓
```

---

## 4. Catégorie #Info

La catégorie **#Info** (comme toutes les catégories `#xx`) décrit une **opération non comptabilisée**.

**Usage :** Annotation manuelle pour indiquer des frais déjà intégrés dans l'opération principale.

**Exemple :**
```csv
Date;Libellé;Montant;Réf;Catégorie;Commentaire
20/01/2025;Achat BTC;-5020.00;btc12;Change;
20/01/2025;Frais intégrés;0.00;btc12;#Info;Frais 20€ inclus dans montant
20/01/2025;Achat BTC;0.12;btc12;Change;
```

**Traitement par les scripts :**
- `cpt_update.py` : Ignore les opérations `#Info` lors de l'appariement
- `tool_refs.py` : Exclut les opérations `#Info` de l'audit (section 1 du rapport)

---

## 5. Logique d'appariement (cpt_update.py)

### 5.1 Cinq stratégies d'appariement

```
generate_linked_operations()
├── LINKED_OPERATIONS     → Génère Espèces/Créances (DAB, prêts)
├── TRANSFER_PAIRS        → Appaire paires spécifiques (comptes internes)
├── INTERNAL_TRANSFERS    → Hub ↔ spokes (SG ↔ Livrets)
└── MESH_TRANSFERS        → Virements same-ccy + changes cross-ccy (via Equiv)
```

### 5.2 MESH_TRANSFERS (réseau maillé unifié)

**Configuration actuelle (cpt_update.py) :**
```python
MESH_TRANSFERS = {
    'accounts': [
        # Comptes bancaires, fintech, trading, crypto, métaux...
        'Compte chèque commun', 'Compte Wise EUR',
        'Portefeuille eToro USD', 'Cake Wallet XMR', 'Pièces or', ...
    ],
    'max_jours_same_currency': 5,
    'max_jours_cross_currency': 7,
}
```

**Catégorie déduite automatiquement :**
- **Virement** : même devise (same-currency)
- **Change** : devises différentes (cross-currency)
- **Achat métaux** : devise se terminant par 'Jo' (OrJo, etc.)

**Critères d'appariement :**
1. `ref = '-'` + compte dans la liste MESH_TRANSFERS
2. Signes opposés (négatif ↔ positif)
3. Same-currency : même montant absolu, ±5 jours
4. Cross-currency : **Equiv Euro opposés** (tolérance 0.01€), ±7 jours
5. Si aucun Equiv pré-rempli : calcul automatique via taux ECB
6. Respect catégorie pré-assignée : Change/Achat métaux → cross-ccy only
7. Cherche d'abord dans le batch, puis dans Excel existant

**Exemple de matching :**
```python
# Opération 1 (côté EUR, négatif)
{
    'categorie': 'Change',
    'montant': '-5000.00',
    'devise': 'EUR',
    'equiv': '-5000.00',  # EUR négatif
    'ref': '-'
}

# Opération 2 (côté actif, positif)
{
    'categorie': 'Change',
    'montant': '0.12',
    'devise': 'BTC',
    'equiv': '5000.00',   # EUR positif
    'ref': '-'
}

# → Match détecté → Référence attribuée : btc12 (classe déterminée par devise BTC)
```

---

## 6. Audit et normalisation (tool_refs.py)

### 6.1 Phases de traitement

#### Phase 1 : Audit (`--audit`)

Détecte 7 types de problèmes :

1. **Statistiques globales** : Paires parfaites, N-uplets, orphelins
2. **Répartition par pattern** : Vxx, btcxx, orxx, etc.
3. **N-uplets (count > 2)** : Références réutilisées (ex: V25 utilisé 4 fois)
4. **Orphelins (count = 1)** : Références sans partenaire
5. **Paires déséquilibrées** : Montants non-opposés (ou Equiv si rempli)
6. **Typos** : `0r508` au lieu de `or508`
7. **Variantes de casse** : `Btc1` vs `btc1`

**Usage :**
```bash
# Audit complet
./tool_refs.py --audit

# Audit filtré par année
./tool_refs.py --audit --year 2023

# Audit filtré par références V2x
./tool_refs.py --audit --ref-regex '^V2[0-9]'

# Audit filtré par paire de comptes
./tool_refs.py --audit --accounts 'Compte chèque commun,Créance prêt familial'
```

#### Phase 2 : Correction variantes de casse (`--fix-case`)

Normalise automatiquement :
- `0r508` → `or508` (typo)
- `Btc1` → `btc1` (minuscule)
- `v100` → `V100` (majuscule)

**Usage :**
```bash
./tool_refs.py --fix-case
```

#### Phase 3 : Correction références réutilisées (`--fix-duplicates`)

Sépare les N-uplets en paires logiques via **algorithme de pairing** :

**Critères de pairing :**
1. **Dates proches** : tolérance configurable (défaut: même date)
2. **Rangs proches** : écart maximum configurable (défaut: 50 lignes)
3. **Montants opposés** : `abs(montant1 + montant2) < 0.01` (sauf si `--skip-balance-check`)

**Usage :**
```bash
# Simulation (dry-run)
./tool_refs.py --fix-duplicates --dry-run

# Application réelle
./tool_refs.py --fix-duplicates

# Avec filtres
./tool_refs.py --fix-duplicates --year 2023 --ref-regex '^V24'

# Paramètres de pairing
./tool_refs.py --fix-duplicates --date-tolerance 3 --max-rank 100

# Ignorer vérification montants opposés (pour arbitrages, dividendes)
./tool_refs.py --fix-duplicates --skip-balance-check
```

**Exemple de traitement :**
```
Réf: V25 - 4 occurrences
  → 2 paires formées, 0 orphelins
    Paire 1: L1234 (12/01/2025) - L1236 (12/01/2025) (Δ1) → V100
      -1000.00 Compte SG
      +1000.00 Compte BB
    Paire 2: L5678 (15/03/2025) - L5680 (15/03/2025) (Δ1) → V101
      -500.00 Compte SG
      +500.00 Livret A
```

#### Phase 4 : Normalisation sémantique (`--normalize`)

Vérifie la cohérence **catégorie → classe de référence** et renomme si nécessaire.

**Règles :**
1. Frais bancaires/ajustements suivent la classe de la transaction principale
2. Détection automatique de la classe attendue via `detect_expected_class()`
3. Renommage avec gestion conflits (trouve prochain numéro disponible)

**Exemple :**
```
V12 avec catégories ['Change', 'Frais bancaires'] et devise BTC
  → Classe attendue: btc (pas V)
  → Renommage: V12 → btc5
```

**Usage :**
```bash
# Simulation
./tool_refs.py --normalize --dry-run

# Application
./tool_refs.py --normalize
```

### 6.2 Compteur F2

La cellule **F2** (colonne Réf, ligne 2) contient le **compteur d'appariement** :
- Incrémenté automatiquement lors de l'attribution d'une nouvelle référence Vxx
- Mis à jour par `--fix-duplicates` si nécessaire (scan de toutes les Vxx existantes)
- Utilisé par `cpt_update.py` via `get_next_pairing_ref()`

---

## 7. Maintenance régulière

Après chaque import (`./cpt.py`), vérifier :
```bash
# Audit rapide (dernière année seulement)
./tool_refs.py --audit --year 2025

# Si problèmes détectés → corriger immédiatement
./tool_refs.py --fix-duplicates --year 2025
```

---

## 8. Checklist format scripts (Tier 2)

Lors de l'ajout d'un nouveau site, s'assurer que `cpt_format_SITE.py` :

**Colonne Equiv Euro :**
- [ ] Importer `cpt_categorize`
- [ ] Utiliser `cpt_categorize.categorize_operation(libelle, "SITE")`
- [ ] Gérer `opts.get('equiv', '')` :
  - [ ] Si `equiv='amount'` : copier montant dans colonne Equiv
  - [ ] Si échange multi-devises/crypto : calculer manuellement Equiv (montant EUR)
  - [ ] Sinon : laisser Equiv vide

**Colonne Réf :**
- [ ] Utiliser `opts.get('ref', '')` pour remplir la colonne Réf
- [ ] Patterns avec `{'ref': '-'}` dans `category_mappings.py`

**category_mappings.py :**
- [ ] Ajouter patterns dans `SITE_PATTERNS`
- [ ] Utiliser catégorie **"Change"** pour échanges devises/crypto/métaux dématérialisés
- [ ] Utiliser catégorie **"Achat métaux"** pour achats métaux physiques (bijoux)

**cpt_update.py :**
- [ ] Pas de modification nécessaire (catégories "Change" et "Achat métaux" déjà configurées)

---

## 9. Références

**Scripts :**
- `cpt_update.py` : Génération automatique des références (lignes 1087-1900)
- `tool_refs.py` : Audit et normalisation a posteriori
- `category_mappings.py` : Définition des catégories et options

**Documentation :**
- `Compta.md` : Vue d'ensemble système 3-tiers
- `docs/appariements.md` : Ce document
