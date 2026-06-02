# Site SOCGEN - Société Générale

Documentation spécifique pour le site Société Générale.

## Vue d'ensemble

**URL:** `https://particuliers.sg.fr`
**Credential ID:** (voir config.ini)
**Profile Chrome:** `.chrome_profile_sg/` (Playwright persistent context)

## URLs directes

### Comptes bancaires

Pattern d'URL directe d'un compte :
`https://particuliers.sg.fr/icd/cbo/index-react-authsec.html#/operations?b64e200_prestationIdTechnique=<TOKEN>`

Le `<TOKEN>` (chaîne base64) identifie le compte chez SG ; il est récupéré via inspection du DOM lors de la première navigation, puis stocké en local hors versioning.

Périmètre typique d'un foyer :
- 1 compte courant joint
- N livrets d'épargne (Livret A, LDD)
- 1 CSL
- M assurances vie (chacune avec son URL `/icd/avd/index-authsec.html#/accueil_contrat/<TOKEN>`)

## Authentication

**Type:** Clavier virtuel avec OCR (Tesseract)

Le site utilise un clavier virtuel randomisé nécessitant OCR pour identifier les chiffres.

**Flux de connexion :**
1. Saisie identifiant
2. Screenshot du clavier virtuel
3. OCR avec Tesseract pour identifier les positions des chiffres
4. Clic sur les chiffres du mot de passe
5. Validation

**Session persistante :** Le profile Chrome `.chrome_profile_sg/` sauvegarde la session pour éviter le 2FA répété.

**⚠️ CRITIQUE :** Ne jamais supprimer `.chrome_profile_sg/` en production car cela déclenche le 2FA.

## Collection mode

Le script collecte automatiquement toutes les données disponibles :

```bash
./cpt_fetch_SOCGEN.py
```

**Ce qui est collecté (via URLs directes) :**
- **CSV compte courant** : 180 jours d'historique
- **CSV épargne** : 5 comptes d'épargne (export CSV natif SG)
- **XLSX assurances vie** : 2 contrats (positions/supports)
- **PDF assurances vie** : 2 contrats (opérations via impression)

**Durée :** ~30-40 secondes

## Fichiers générés

### Compte courant

**CSV :**
- `{numéro_compte}.csv` : Opérations téléchargées (180 jours)

### Épargne

**CSV :**
- `Export_{numéro}*.csv` : 5 fichiers CSV (Livret A Barnabé, LDD Barnabé, etc.)

### Assurances vie

**Excel (supports) :**
- `SG_alice_supports.xlsx` : Portfolio Assurance vie Alice
- `SG_barnabe_supports.xlsx` : Portfolio Assurance vie Barnabé

**PDF (opérations) :**
- `SG_alice_operations.pdf` : Opérations Assurance vie Alice
- `SG_barnabe_operations.pdf` : Opérations Assurance vie Barnabé

**Structure Excel supports :**
```
Colonne A: ISIN
Colonne B: Support (nom)
Colonne C: Nombre d'UC/parts
Colonne D: Valeur de l'UC/parts
Colonne E: Valorisation
```

## Format CSV natif SG

**Format :** `Date;Court;Long;Montant;Devise` (5 champs)

**Encodage :** latin-1

**Champ "Long" (colonne 3) :** Utilisé pour la catégorisation automatique via patterns.

## Formatage (cpt_format_SOCGEN.py)

Parse le CSV natif SG (latin-1, 5 champs), auto-catégorise via le champ « Long »
et produit le format standard 9 champs. Contrat Tier 2 détaillé : voir
[`Compta_site.md`](../Compta_site.md).

## Supports d'assurance vie

### Traitement dans cpt_update.py

Les fichiers Excel `*_supports_*.xlsx` sont traités pour mettre à jour la feuille Plus_value.

**Mapping automatique des noms :**

SG renomme parfois ses supports ; le système applique un mapping `<ancien nom>` → `<nouveau nom>` configurable. Exemple :
- `SUPPORT EURO` → `FONDS_EUROS`

**ETF agrégé :** Pour le contrat "Assurance vie Alice", calcule l'agrégat ETF = somme de tous les supports SAUF `FONDS_EUROS` et `FONDS_OBLIG`. La détection du compte utilise le nom de fichier (pattern : `alice`). Voir Compta_plus.md pour le renommage en collecte manuelle.

## Particularités techniques

### Downloads

Téléchargements via `page.expect_download()` (Playwright). Les fichiers existants sont écrasés.

### Comparaison des soldes

Le mode par défaut compare les soldes HTML vs Download et avertit si divergence.

**Note :** Divergence normale si opérations en attente (CB différé, virements).

## Troubleshooting

### "Service indisponible"

**Cause :** Maintenance SG ou erreur de formulaire

**Solution :** Vérifier les fichiers debug HTML dans `logs/`

### File not found

**Cause :** Suffixe `(1)` ajouté par le navigateur

**Solution :** S'assurer que les fichiers existants sont écrasés

### Balance warnings

**Cause :** Opérations en attente (CB différé, virements en cours)

**Solution :** Normal, pas d'action requise

### Empty CSV

**Cause :** Pas d'opérations dans la période

**Solution :** Normal, SG retourne juste l'en-tête + résumé

### OCR failures (mode headless)

**Cause :** Window size insuffisante

**Solution :** Actuellement 1400x1000, peut nécessiter ajustement

## Commandes utiles

```bash
# Collection SG uniquement
./cpt_fetch.py --sites SOCGEN

# Workflow complet SG
./cpt.py --sites SOCGEN

# Collecte directe
./cpt_fetch_SOCGEN.py

# Debug avec fichiers HTML/PNG
# Activer DEBUG=true dans config.ini d'abord
./cpt_fetch_SOCGEN.py

# Vérifier les logs
tail -f logs/journal.log
```

## Points critiques

⚠️ **Profile Chrome :** Suppression = 2FA déclenché, ne JAMAIS supprimer `.chrome_profile_sg/` en production

⚠️ **Encodage :** CSV natif en latin-1, pas UTF-8

⚠️ **OCR dependency :** Requiert Tesseract installé

✅ **Session persistante :** Très robuste avec le profile Chrome (Playwright)

✅ **Collecte complète :** CSV (compte courant + épargne) + XLSX/PDF (assurances vie)
