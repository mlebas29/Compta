# Interface Format ↔ Update ↔ Excel

*Documentation architecture d'import - mise à jour 08/02/2026*

## Architecture globale

```
┌─────────────────────────────────────────────────────────────┐
│  FORMATTEUR                                                 │
│  Dit ce qu'il sait, ne dit pas ce qu'il ignore              │
│  format_site(site_dir) → (operations, positions)            │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  UPDATE (cpt_update) + PAIR (cpt_pair)                      │
│  Déduplique, filtre, enrichit, intègre dans Excel           │
│  Apparie les opérations, vérifie Contrôles                  │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  EXCEL (Contrôles)                                          │
│  Vérifie la cohérence, signale les anomalies                │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  UTILISATEUR                                                │
│  Gère les exceptions (compte liquidé, etc.)                 │
└─────────────────────────────────────────────────────────────┘
```

**Principe** : La gestion des cas particuliers (comptes liquidés, exceptions métier)
relève de la couche supérieure (Excel ou utilisateur), pas du code d'import.

## Interface format_site() (implémentée 02/02/2026)

Tous les formatteurs exposent maintenant une interface Python directe :

```python
# cpt_format_SITE.py

def format_site(site_dir: Path, verbose: bool = False) -> tuple[list, list]:
    """API pour Update.

    Args:
        site_dir: Répertoire dropbox/SITE/
        verbose: Mode debug

    Returns:
        (operations, positions)
        - operations: liste de tuples 9 champs
        - positions: liste de tuples 4 champs
    """
```

### Responsabilités du formatteur

| Responsabilité | Description |
|----------------|-------------|
| Trouver ses fichiers | Patterns définis dans le formatteur |
| Gérer les ZIP | Extraction si nécessaire (KRAKEN ; WISE en repli legacy) |
| Agréger N fichiers | Une seule passe sur tous les fichiers |
| Déduplication fichiers | Même nom → garder le plus récent |
| Vérifier dropbox | Signaler fichiers intrus/manquants |

### Responsabilités d'Update

| Responsabilité | Description |
|----------------|-------------|
| Déduplication données | vs Excel existant |
| Filtre date | max_days_back (config.ini) |
| Enrichissement | Equiv EUR via API ECB |
| Appariement | Génère les références |
| Intégration Excel | Opérations + Plus_value |
| Vérification Contrôles | ERREUR COMPTES = échec |

## Utilitaires partagés (inc_format.py)

| Fonction | Usage |
|----------|-------|
| `process_files()` | Boucle générique sur handlers (pattern, func, cible) |
| `cli_main()` | Point d'entrée CLI standard |
| `verify_dropbox_files()` | Vérification patterns vs fichiers présents |
| `parse_french_date_from_iso()` | Conversion date ISO → DD/MM/YYYY |
| `filter_ops_by_date()` | Filtrage temporel (max_days_back) |

## Formatteurs

| Site | Particularités |
|------|----------------|
| MANUEL | Pass-through CSV 9 colonnes |
| DEGIRO | Consolidation 2 lignes → 1 op EUR |
| BB | Calcul Réserve = Total - Titres |
| ETORO | Fichiers intermédiaires (PDF → CSV) |
| KRAKEN | Extraction ZIP, 2 comptes séparés |
| WISE | CSV all-transactions → jambes par devise |
| SG | ETF agrégé, N comptes + M assurances vie |
| BTC/XMR | Fetch extrait les soldes |

## Configurations (données, pas code)

| Configuration | Module | Usage |
|---------------|--------|-------|
| `LINKED_OPERATIONS` | inc_excel_compta | Patterns SG → génère ops Espèces/Créances |
| `TRANSFER_PAIRS` | cpt_pair | Appairage entre comptes internes |
| `INTERNAL_TRANSFERS` | cpt_pair | Hubs SG et BB avec leurs spokes |
| `MESH_TRANSFERS` | cpt_pair | Virements same-ccy + changes cross-ccy |

## Principe clé

```
Solde inconnu ≠ Solde = 0

Si le formatteur ne connaît pas → il ne dit rien
(pas de ligne avec valeur par défaut)
```

---

# Architecture cible : séparation Import / Appariement

*Spécification - 05/02/2026, implémenté Phase 1+2 le 08/02/2026*

**État actuel :** `cpt_update.py` fait l'import (garde son nom), `cpt_pair.py` fait l'appariement.
Les opérations liées (LINKED_OPERATIONS) sont générées par cpt_update avec `ref='-'`,
puis appariées par cpt_pair. L'accès Excel est factorisé dans deux modules :
- `inc_excel_compta.py` (387 L) : base légère (workbook + pairing) → chargé par cpt_pair
- `inc_excel_import.py` (1248 L) : extension import (ComptaExcelImport hérite ComptaExcel) → chargé par cpt_update

## Motivation

Le script monolithique `cpt_update.py` (~3900 lignes) mélange deux responsabilités distinctes :
- **Import** : acquisition et intégration des données
- **Appariement** : matching des opérations et assignation des références

Cette séparation permet :
1. **Catégorisation manuelle** entre import et appariement
2. **Appariement plus fiable** (catégorisation correcte → meilleur matching)
3. **Audit des anomalies** indépendant de l'import
4. **Maintenance** simplifiée

## Architecture cible

```
┌─────────────────────────────────────────────────────────────┐
│  format_* (par SITE)                                        │
│  Conversion format source → CSV standardisé                 │
│  Catégorisation via inc_categorize                          │
│  ref='-' (à apparier) ou ref='' (isolée)                    │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  cpt_update (import)                                        │
│  Collecte dropbox, appel format_*, dédoublonnage            │
│  Opérations liées génériques (Réserve, Créance...)          │
│  Insertion Excel + archivage                                │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  UTILISATEUR                                                │
│  Catégorisation manuelle dans Excel                         │
│  (optionnel mais recommandé avant appariement)              │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  cpt_pair                                                   │
│  --audit   : Analyse complète (anomalies + candidats)       │
│  --pair    : Appariement des ref='-'                        │
│  --compare : Comparaison TNR vs référence                   │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  EXCEL (Contrôles)                                          │
│  Vérifie la cohérence, signale les anomalies                │
└─────────────────────────────────────────────────────────────┘
```

## cpt_update (import)

### Responsabilités

| Responsabilité | Description |
|----------------|-------------|
| Collecte dropbox | Parcourt dropbox/SITE/ pour chaque site |
| Appel format_* | Conversion format source → tuples standardisés |
| Opérations liées | Génération Réserve, Créance, Espèces (config LINKED_OPERATIONS) |
| Dédoublonnage | vs Excel existant (date + compte + montant + label) |
| Filtre date | max_days_back (config.ini) |
| Enrichissement | Equiv EUR via API ECB |
| Insertion Excel | Nouvelles lignes dans Opérations |
| Archivage | Déplace fichiers traités vers archives/ |
| Vérification | ERREUR COMPTES → échec |

### Ce que cpt_update ne fait PAS

- Pas d'appariement (ref reste '-' ou '')
- Pas d'assignation de références numériques (v42, btc5...)
- Pas de matching inter-comptes

### Options CLI

```bash
cpt_update [options]
  --fallback       Restaurer état précédent
  --archive-only   Archiver sans importer
  --all-soldes     Écrire tous les soldes
  --no-pair        Ne pas lancer cpt_pair après l'import
  --verbose        Mode debug
```

## cpt_pair

### Responsabilités

Trois modes exclusifs :

### Mode `--audit`

Analyse TOUTES les références (pas seulement ref='-').

**Anomalies détectées :**

| Type | Description |
|------|-------------|
| Orphelines | ref sans contrepartie (count=1) |
| N-uplets | ref réutilisée (count>2) |
| Montants incorrects | paires dont la somme ≠ 0 |
| Typos | 0r au lieu de or |
| Variantes casse | Btc1 vs btc1 |
| Non appariées | ref='-' avec candidats potentiels |
| Non faisables | ref='-' sans candidat (données incomplètes) |

**Output :** Rapport texte (pas de modification Excel)

### Mode `--pair`

Appariement de TOUTES les opérations avec ref='-' :
- Nouvelles (import récent)
- Anciennes (devenues appariables grâce aux nouvelles données)

**Algorithme (6 phases) :**

1. Opérations liées (si pas déjà fait dans import)
2. Paires spécifiques (TRANSFER_PAIRS)
3. Hub-and-spokes (INTERNAL_TRANSFERS)
4. Réseau mesh unifié (MESH_TRANSFERS : virements same-ccy + changes cross-ccy)
5. Fallback label identique

**Output :** Excel modifié (refs numériques assignées)

### Mode `--compare`

Comparaison TNR : résultat vs référence attendue.

Usage tests de non-régression uniquement.

### Options CLI

```bash
cpt_pair [mode] [options]

Modes (exclusifs):
  --audit          Rapport d'analyse complet
  --pair           Exécuter les appariements
  --compare REF    Comparer avec fichier référence

Options:
  --dry-run        Simulation sans modification (--pair)
  --year YYYY      Filtrer par année
  --verbose        Mode debug
```

## Workflow recommandé

### Usage quotidien

```bash
# 1. Import + appariement automatique
./cpt_update.py

# 2. Catégorisation manuelle dans Excel (optionnel)
#    - Corriger les catégories '-'
#    - Vérifier les catégories auto-assignées

# 3. Audit pour voir l'état
./cpt_pair.py --audit

# 4. Ré-appariement si nécessaire
./cpt_pair.py --pair
```

### TNR (tests de non-régression)

Voir [`Compta_tests.md`](../Compta_tests.md) — 7 scénarios indépendants lancés via le shebang : `./tests/tnr_<scénario>.py`.

## Migration depuis l'ancien cpt_update monolithique

### Scripts absorbés

| Ancien | Nouveau |
|--------|---------|
| cpt_update.py (monolithique) | cpt_update (import) + cpt_pair (appariement) |
| tool_refs.py --audit | Audit références (standalone) |
| tool_refs.py --fix* | Corrections références |

### Constantes déplacées

| Constante | Module |
|-----------|--------|
| LINKED_OPERATIONS | inc_excel_compta (partagé) |
| TRANSFER_PAIRS | cpt_pair |
| INTERNAL_TRANSFERS | cpt_pair |
| MESH_TRANSFERS | cpt_pair |

### Architecture modules Excel

```
inc_excel_compta.py (473 L) — base légère
├── ComptaExcel : workbook, pairing, refs (load_unpaired, load_all_references, write_ref, get_next_pairing_ref, create_backup)
└── Chargé par cpt_pair.py et tool_refs.py

inc_excel_import.py (1248 L) — extension import
├── ComptaExcelImport(ComptaExcel) : append, valorisations, linked ops, UNO
└── Chargé par cpt_update.py (inclut aussi la base)
```

## Évolutions futures

- Configuration externalisée (YAML ou config.ini étendu)
