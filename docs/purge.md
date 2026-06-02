# Purge des opérations anciennes - Documentation

## Vue d'ensemble

Le script `cpt_purge.py` permet de purger les opérations anciennes dans `comptes.xlsm` pour réduire la taille du fichier et améliorer les performances, tout en préservant l'intégrité des données.

**Objectif :** Conserver 1+ an d'historique (opérations récentes) et purger les opérations anciennes.

**Gain typique :** 50-60% de réduction après plusieurs années d'utilisation.

---

## Contraintes de sécurité

Le script applique 5 protections strictes pour garantir l'intégrité des données :

### 1. Comptes Plus_value (jamais purgés)

**Règle :** Les comptes listés dans `Plus_value!A5:A117` ne sont **jamais purgés**.

**Raison :** Ces comptes sont suivis pour leurs valorisations (assurances vie, PEE, portefeuilles crypto/titres). La purge casserait l'historique nécessaire aux calculs de plus-values.

**Exemples de comptes protégés :**
- Assurances vie
- PEE EMPLOYEUR
- Portefeuilles titres (BoursoBank, DEGIRO, eToro)
- Portefeuilles crypto (Kraken BTC, Cake Wallet XMR, BlueWallet BTC, etc.)
- Comptes multi-devises (Wise USD/SEK/SGD)
- (+ comptes spécifiquement privés gérés via l'overlay `custom/`, propres à chaque foyer)

**Détection automatique :** Le script lit `Plus_value!A5:A117` au démarrage (29 comptes protégés typiquement).

### 2. Références appariées (paires conservées intégralement)

**Règle :** Si une paire d'opérations appariées (même référence Vxx, btcxx, etc.) a une opération avant la date de coupure et une opération après, **les deux sont conservées**.

**Raison :** Éviter les références cassées (orphelines) qui créeraient des incohérences dans les appariements.

**Exemple :**
```
Date de coupure : 01/01/2025

Opération A : 15/12/2024, Virement -1000€, ref=V100  [avant coupure]
Opération B : 05/01/2025, Virement +1000€, ref=V100  [après coupure]

→ Opération A conservée (malgré date < coupure) pour préserver la paire
```

**Statistiques :** Typiquement 90-100 paires sauvées, représentant ~100 lignes conservées pour intégrité.

### 3. Dernier #Solde (conservé et généré)

**Règle :** Pour chaque compte purgé, le dernier #Solde avant la date de coupure est :
1. Conservé s'il existe
2. Généré automatiquement au 31/12/N-1 s'il manque

**Raison :** Garantir la cohérence des soldes. Sans ce #Solde, le premier solde après purge serait incohérent.

**Exemple :**
```
Avant purge (Compte chèque commun) :
  01/06/2024  Opération A      -500€
  15/09/2024  Opération B      +1200€
  31/12/2024  #Solde           22863.13€  ← Conservé
  10/01/2025  Opération C      -150€

Après purge :
  31/12/2024  #Solde           22863.13€  ← Point de départ cohérent
  10/01/2025  Opération C      -150€
```

### 4. Année fiscale N-1 (conservée intégralement)

**Règle par défaut :** Sans option `--date` ou `--keep-months`, la date de coupure est fixée au **01/01/N-1**.

**Raison :** Préserver l'année fiscale précédente complète pour les déclarations fiscales et calculs de plus-values.

**Exemple en 2026 :**
- Date de coupure par défaut : 01/01/2025
- Années conservées : 2025 + 2026 (année en cours)
- Années purgées : 2024 et antérieures

### 5. Backup automatique

**Règle :** Avant toute modification, un backup est créé dans `archives/comptes_BACKUP_PURGE_YYYYMMDD_HHMMSS.xlsx`.

**Raison :** Permet de restaurer en cas de problème ou d'erreur d'appréciation.

---

## Usage

### Commandes principales

```bash
# Simuler (mode audit, aucune modification)
./cpt_purge.py --audit

# Purge par défaut (garder année N-1 + N)
./cpt_purge.py

# Garder X mois (ex: 24 mois = 2 ans)
./cpt_purge.py --keep-months 24

# Purger avant une date précise
./cpt_purge.py --date 2023-01-01

# Mode verbeux (afficher détails paires sauvées)
./cpt_purge.py --audit -v
```

### Workflow recommandé

```bash
# 1. Audit initial (simuler)
./cpt_purge.py --audit

# 2. Vérifier le résumé (comptes protégés, lignes à supprimer, gain)

# 3. Exécuter réellement si OK
./cpt_purge.py

# 4. Confirmer à l'invite
Supprimer 2805 lignes? [o/N] o

# 5. Vérifier Excel après purge
./cpt_controles.py          # Vérifier Contrôles!A1
./tool_refs.py --audit --year 2025  # Vérifier appariements
```

---

## Exemple de sortie

### Mode audit

```
================================================================================
PURGE DES OPÉRATIONS ANCIENNES
================================================================================

📅 Date de coupure: 01/01/2025
   Opérations antérieures à cette date seront purgées

⚠️  Contraintes de sécurité:
   • Comptes Plus_value: jamais purgés (valorisations)
   • Références appariées: paires conservées intégralement
   • Dernier #Solde: conservé par compte avant coupure
   • Année fiscale N-1: conservée intégralement (calculs fiscaux)

📖 Lecture de comptes.xlsm...
🔒 Lecture des comptes protégés (Plus_value!A5:A117)...
   29 comptes protégés

🔍 Analyse des opérations...
   5147 opérations totales
   2901 opérations purgeables
   780 opérations protégées

📋 Génération du plan de purge...
   2805 lignes à supprimer
   26 nouveaux #Solde à créer
   95 paires sauvées (éviter références cassées)
   96 lignes conservées pour intégrité

📊 Résumé par compte:

  🗑️  Compte chèque commun                     → 2214 lignes (#Solde 31/12/2024: 22863.13€)
  🗑️  Compte chèque BB                         → 343 lignes (#Solde 31/12/2024: 0.00€)
  🔒 Portefeuille BB                          → PROTÉGÉ (Compte dans Plus_value)
  🔒 Assurance vie Alice                       → PROTÉGÉ (Compte dans Plus_value)
  ✓  Compte Kraken EUR                        → Aucune opération ancienne

✓ AUDIT TERMINÉ - Aucune modification effectuée
```

**Interprétation :**
- **Gain potentiel :** 2805 / 5147 = 54% de réduction
- **Comptes purgés :** 26 comptes (symbole 🗑️)
- **Comptes protégés :** 29 comptes (symbole 🔒)
- **Comptes récents :** Pas d'opérations anciennes (symbole ✓)

---

## Fonctionnement interne

### Architecture du script

```
main()
├── load_protected_accounts()      # Lit Plus_value!A5:fin de tableau
├── analyze_operations()           # Analyse opérations par compte et date
├── check_broken_pairs()           # Détecte paires à sauver
├── calculate_new_soldes()         # Génère #Solde au 31/12/N-1
├── generate_purge_plan()          # Construit plan complet
└── execute_purge()                # Supprime lignes + ajoute #Solde
```

### Étapes détaillées

#### 1. Lecture des comptes protégés

```python
def load_protected_accounts(ws_plusvalue):
    """Charge la liste depuis Plus_value colonne A (scan dynamique)"""
    protected = set()
    for row in range(PV_PROTECTED_FIRST_ROW, ws_plusvalue.max_row + 1):
        cell_value = ws_plusvalue.cell(row=row, column=PvCol.COMPTE).value
        if cell_value:
            protected.add(str(cell_value).strip())
    return protected
```

**Colonne A (Plus_value) :**
- Lignes 1-4 : Headers
- Lignes 5-117 : Noms de comptes (1 par ligne)
- Exemple : "Portefeuille BB", "Assurance vie Alice", etc.

#### 2. Analyse des opérations

Pour chaque compte :
- Collecter toutes les opérations (avant et après coupure)
- Identifier les #Solde existants
- Compter opérations purgeables vs protégées

```python
def analyze_operations(ws_operations, cutoff_date, protected_accounts):
    """Retourne stats par compte"""
    for row in range(3, ws_operations.max_row + 1):
        date = ws_operations.cell(row, 1).value
        compte = ws_operations.cell(row, 8).value
        categorie = ws_operations.cell(row, 7).value

        if compte in protected_accounts:
            # Marquer comme protégé
        elif date < cutoff_date:
            # Marquer comme purgeable
```

#### 3. Détection des paires à sauver

```python
def check_broken_pairs(ws_operations, purgeable_rows, protected_rows):
    """Détecte références qui seraient cassées par la purge"""
    refs = {}

    # Grouper par référence
    for row in all_rows:
        ref = ws_operations.cell(row, 6).value  # Col F
        if ref and ref not in ['-', '#Solde']:
            refs[ref].append(row)

    # Détecter paires mixtes (avant + après coupure)
    for ref, rows in refs.items():
        if has_purgeable_and_kept_rows(rows):
            # Sauver TOUTES les lignes de cette référence
```

**Exemple de paire sauvée :**
```
Référence: V1523
  Purgeable: L1234 (15/12/2024, Virement -500€)
  Conservée: L3456 (10/01/2025, Virement +500€)

→ L1234 sauvée pour préserver l'intégrité de la paire
```

#### 4. Génération des #Solde

Pour chaque compte purgé :

```python
def calculate_new_soldes(stats, cutoff_date):
    """Calcule solde au 31/12/N-1"""
    for account, info in stats['accounts'].items():
        # Trouver dernier #Solde avant coupure
        last_solde = find_last_solde_before(account, cutoff_date)

        if last_solde:
            # Conserver ce #Solde
            new_solde = last_solde
        else:
            # Calculer solde en sommant opérations jusqu'à coupure
            new_solde = sum_operations_until(account, cutoff_date)
```

**Date du nouveau #Solde :** Toujours fixée au **31/12/N-1** (veille de la date de coupure).

#### 5. Exécution de la purge

```python
def execute_purge(ws_operations, plan, cutoff_date, dry_run=False):
    """Supprime lignes et ajoute #Solde"""
    if dry_run:
        return 0  # Simulation

    # 1. Supprimer lignes (de la fin vers le début pour éviter décalage)
    for row in sorted(plan['rows_to_delete'], reverse=True):
        ws_operations.delete_rows(row)

    # 2. Ajouter nouveaux #Solde (après dernière opération de chaque compte)
    for account, solde_info in plan['new_soldes'].items():
        insert_position = find_insertion_point(account)
        ws_operations.insert_rows(insert_position)
        ws_operations.cell(insert_position, 1).value = solde_info['date']
        ws_operations.cell(insert_position, 2).value = "Relevé compte"
        ws_operations.cell(insert_position, 3).value = solde_info['amount']
        ws_operations.cell(insert_position, 7).value = "#Solde"
        ws_operations.cell(insert_position, 8).value = account
```

---

## Quand utiliser la purge

### Indicateurs de besoin

1. **Taille fichier Excel > 10 Mo**
   - Ralentissements à l'ouverture/sauvegarde
   - Difficultés avec LibreOffice Calc

2. **Plus de 5 ans d'historique**
   - Opérations de 2019 et antérieures peu utiles
   - Risque de doublons manuels/automatiques anciens

3. **Performances dégradées**
   - `cpt_update.py` prend > 30 secondes
   - Contrôles Excel lents (> 1 minute)

4. **Besoin de clarté**
   - Focus sur période récente (2-3 ans)
   - Éviter confusion avec vieux comptes fermés

### Fréquence recommandée

**Une fois par an** (début d'année) :
```bash
# Janvier 2026 : purger avant 2025
./cpt_purge.py --audit
./cpt_purge.py
```

**Avantages :**
- Conserve année fiscale précédente complète (déclarations)
- Gain de performance pour l'année en cours
- Fichier Excel maintenu à taille raisonnable

---

## Cas particuliers

### Compte fermé récemment

**Problème :** Un compte fermé il y a 6 mois (solde = 0€) est conservé car date récente.

**Solution :** Utiliser `--date` pour cibler spécifiquement :
```bash
# Purger tout avant 01/07/2025 (6 mois seulement)
./cpt_purge.py --date 2025-07-01 --audit
```

### Besoin de garder 3 ans d'historique

**Solution :** Utiliser `--keep-months` :
```bash
# Garder 36 mois (3 ans)
./cpt_purge.py --keep-months 36 --audit
```

### Restaurer après purge

Si problème détecté après purge :

```bash
# 1. Identifier le backup
ls -lht archives/comptes_BACKUP_PURGE_*.xlsx | head -1

# 2. Restaurer
cp archives/comptes_BACKUP_PURGE_20260111_143052.xlsx comptes.xlsm

# 3. Vérifier
./cpt_controles.py
```

---

## Vérifications post-purge

Après exécution de la purge, lancer systématiquement :

### 1. Contrôles Excel

```bash
./cpt_controles.py
```

**Attendu :** Contrôles!A1 = "."

**Si erreur :** Restaurer le backup et investiguer.

### 2. Appariements année courante

```bash
./tool_refs.py --audit --year 2025
```

**Attendu :** Aucune paire cassée (orphelins = 0 pour refs récentes).

### 3. Vérification manuelle Excel

Ouvrir `comptes.xlsm` et vérifier :
- **Opérations (ligne 3)** : Premier #Solde par compte au 31/12/N-1
- **Contrôles** : Tous les comptes équilibrés (colonne K)
- **Plus_value** : Aucun compte valorisé n'a été purgé

---

## Limites et précautions

### Ce que le script NE fait PAS

1. **Ne purge pas les autres feuilles** (Plus_value, Avoirs, Budget, etc.)
2. **Ne compresse pas le fichier** (taille disque identique si Excel non réenregistré)
3. **Ne supprime pas les comptes** (structure Avoirs/Contrôles intacte)
4. **Ne modifie pas les catégories** (Budget!L29:L116 intact)

### Précautions avant purge

1. **Vérifier comptes protégés** dans Plus_value!A5:A117
   - Ajouter un compte si besoin AVANT la purge
   - Exemple : Nouveau portefeuille crypto à protéger

2. **Vérifier date de coupure** correspond aux besoins
   - Par défaut : 01/01/N-1 (conserve année fiscale complète)
   - Ajuster si besoin spécifique (impôts, audit)

3. **Mode TEST recommandé** pour première utilisation
   - Tester sur copie de comptes.xlsm d'abord
   - Vérifier résultats avant appliquer en PROD

4. **Seafile sync** : Pas de `--push` automatique
   - La purge est locale uniquement
   - Push manuel si résultat satisfaisant

---

## FAQ

### Q : Puis-je purger un compte spécifique ?

**R :** Non, le script purge tous les comptes non-protégés. Pour cibler, ajouter temporairement les autres comptes dans Plus_value!A5:A117.

### Q : Que deviennent les références appariées après purge ?

**R :** Les paires sont conservées intégralement. Exemple : Si V1523 a une opération avant et après coupure, les deux sont gardées.

### Q : Puis-je annuler une purge ?

**R :** Oui, restaurer le backup `archives/comptes_BACKUP_PURGE_*.xlsx`. Aucun mécanisme de rollback automatique.

### Q : Combien de temps prend la purge ?

**R :** 5-15 secondes typiquement (2800 lignes supprimées). L'audit prend ~3 secondes.

### Q : La purge casse-t-elle les formules Excel ?

**R :** Non, le script ne touche que la feuille Opérations (suppression de lignes). Les formules dans Contrôles, Budget, etc. restent intactes.

### Q : Que faire si Contrôles!A1 ≠ "." après purge ?

**R :** Restaurer le backup immédiatement. Investiguer avec `./cpt_controles.py -v` pour comprendre l'erreur. Possibilité de bug dans le script (signaler).

---

## Références

**Scripts liés :**
- `cpt_controles.py` : Vérifier intégrité après purge
- `tool_refs.py` : Auditer appariements après purge
- `cpt_update.py` : Workflow normal (pas de purge automatique)

**Documentation :**
- `Compta.md` : Vue d'ensemble du système
- `docs/appariements.md` : Système de références
- `docs/purge.md` : Ce document

**Fichiers :**
- Script : `cpt_purge.py` (732 lignes)
- Backup : `archives/comptes_BACKUP_PURGE_*.xlsx`
- Excel : `comptes.xlsm` (feuille Opérations modifiée)
