# Site NATIXIS — PEE Inter Épargne / HSBC

Documentation spécifique pour le site PEE EMPLOYEUR (Plan d'Épargne Entreprise).

## Vue d'ensemble

**URL:** `https://hsbc.epargnants.votreepargnesalariale.com`
**Credential ID:** `BaNa-C`
**Profile Chrome:** `.chrome_profile_natixis/`

## Authentication

**Type:** Clavier virtuel HTML (pas d'OCR nécessaire)

Le site utilise un clavier virtuel où les chiffres sont dans le DOM (accessible via `span.text-primary-600`). Contrairement à SG, pas besoin d'OCR car les valeurs sont en texte.

**Flux de connexion :**
1. Sélection langue française (mat-select Angular)
2. Saisie login (input standard)
3. Clavier virtuel pour mot de passe (chiffres dans le DOM)
4. Validation

**Session persistante :** Le profil Chrome `.chrome_profile_natixis/` sauvegarde la session pour éviter le 2FA répété.

**Détection de session :** Vérifie l'absence du formulaire de login (`input[data-testid='login-form-input']`).

## Particularités techniques

### Angular Material UI

**Problème critique :** Le site utilise Angular qui rend les éléments UNIQUEMENT via JavaScript. Les `<app-transaction-card>` ne sont jamais accessibles dans le DOM.

**Solution :** Extraction par regex depuis `document.body.innerText` au lieu de parcourir le DOM.

```python
# NE FONCTIONNE PAS
operations = driver.find_elements(By.CSS_SELECTOR, "app-transaction-card")

# FONCTIONNE
text = driver.execute_script("return document.body.innerText;")
matches = re.findall(pattern, text)
```

### Calcul du total

**Important :** Le total affiché "Épargne nette estimée" sur le site ne correspond PAS à la somme des supports HSBC.

**Solution :** Calculer nous-mêmes le total en sommant les 5 supports :

```python
total_amount = sum([float(s['montant'].replace(',', '.')) for s in supports_data])
```

## Collection

### Supports (5 fonds HSBC)

**Fichier généré :** `supports_YYYYMMDD.csv`

**Format :** `Nom;Montant` (2 colonnes)

**Supports collectés :** 5 fonds typiques HSBC EE (monétaire, dynamique, équilibré, actions monde, tempéré). La liste exacte dépend de l'allocation du PEE de chaque salarié.

**Destination :** Plus_value sheet (traités directement par `cpt_update.py`)

### Opérations

**Fichier généré :** `operations_YYYYMMDD.csv`

**Format :** `Date;Nature;Montant;Statut` (4 colonnes)

**Contenu :**
- 11 opérations historiques (5 dernières années)
- 1 ligne #Solde (total calculé des 5 supports)

**Regex d'extraction :**
```python
pattern = r'(\d{2}/\d{2}/\d{4}).*?([^\n]+?)\s+([\d\s,]+)\s*EUR.*?([\d\s,]+)\s*EUR\s+(Réalisée|En cours)'
```

Capture : Date, Nature, Montant (colonne 1), Montant (colonne 2), Statut

**Exemple de doublons légitimes :** 3 arbitrages le 06/10/2023 avec le même libellé "Modification de placements" et montant 0,00 (après formatage).

## Formatage (cpt_format_NATIXIS.py)

### Types d'opérations

**1. Arbitrage** ("Modification de placements")
- Déplacement interne à somme nulle
- **Montant :** 0,00
- **Catégorie :** "Arbitrage titres"
- **Commentaire :** Montant d'origine à titre informatif (ex: "10000,00€")

**2. Versement** ("INVESTISSEMENT DE VOTRE INTERESSEMENT")
- Versement employeur
- **Montant :** Montant réel
- **Catégorie :** "EMPLOYEUR"

**3. Virement** ("Remboursement des avoirs disponibles")
- Retrait vers compte bancaire
- **Montant :** Négatif
- **Réf :** "-"
- **Catégorie :** "Virement"

**4. Solde** ("#Solde")
- Total calculé des 5 supports
- **Libellé :** "Relevé compte"
- **Catégorie :** "#Solde"

### Format de sortie

**Standard 9 champs :** `Date;Libellé;Montant;Devise;Equiv;Réf;Catégorie;Compte;Commentaire`

**Compte :** "PEE EMPLOYEUR Alice"

**Commentaire :** Vide (sauf pour arbitrages)

## Import (cpt_update.py)

### Supports → Plus_value

Les supports PEE sont traités comme les supports SG (assurances vie) :

1. Lecture du CSV `supports_YYYYMMDD.csv`
2. Parsing : Nom;Montant (format: "44156,42")
3. Mise à jour de la feuille Plus_value
4. Match par nom de support (recherche partielle)
5. Update colonnes J (Date SOLDE) et K (SOLDE)

**Mapping compte :** `'supports_': 'PEE EMPLOYEUR Alice'`

### Opérations → Opérations sheet

Import standard avec détection de doublons (voir Compta.md pour la logique globale).

## Optimisations

### Temporisations réduites

Toutes les temporisations `time.sleep()` ont été optimisées :

- Chargement pages : 3s → 1s
- Clics divers : 0.5-2s → supprimé ou 0.3-0.5s
- Clavier virtuel : 0.3s → 0.1s par chiffre

**Gain :** ~15-20 secondes par exécution

### Mode verbose

Pour debug, activer dans `config.ini` :
```ini
[general]
DEBUG = true
```

## Impression PDF — CDP printToPDF

`page.pdf()` Playwright ne fonctionne qu'en headless. En mode headed (profil persistant), on utilise CDP :

```python
cdp = context.new_cdp_session(page)
result = cdp.send("Page.printToPDF", {"printBackground": True, "preferCSSPageSize": True})
pdf_data = base64.b64decode(result['data'])
cdp.detach()
```

Même pattern que `cpt_fetch_ETORO.py`.

## Troubleshooting

### "Service indisponible"

**Cause :** Maintenance du site ou erreur de formulaire

**Solution :** Vérifier manuellement dans Chrome

### Opérations non collectées

**Cause :** Angular n'a pas fini de charger les données

**Solution :** Augmenter le `time.sleep()` après `wait_for(state="attached")` (actuellement 1s)

### Total incorrect

**Cause :** Le site affiche "Épargne nette estimée" qui peut différer

**Solution :** Notre système calcule le total en sommant les 5 supports (plus fiable)

### Langue en anglais

**Cause :** Sélection de langue échouée ou profil Chrome vide

**Solution :**
1. Supprimer `.chrome_profile_natixis/`
2. Faire une connexion manuelle en français
3. Le profil sauvegarde la préférence

### 2FA répété

**Cause :** Profil Chrome supprimé ou cookies expirés

**Solution :** Ne jamais supprimer `.chrome_profile_natixis/` en production

## Commandes utiles

```bash
# Collection PEE uniquement
./cpt_fetch.py --sites NATIXIS

# Workflow complet PEE
./cpt.py --sites NATIXIS

# Mode verbeux
./cpt_fetch_NATIXIS.py -v

# Vérifier les logs
tail -f logs/journal.log
```

## Points critiques

- **Angular limitation :** Ne jamais essayer d'accéder aux éléments `<app-*>` dans le DOM, toujours utiliser `innerText` + regex
- **Profil Chrome :** Critique pour éviter 2FA, sauvegardé dans `.chrome_profile_natixis/`
- **Total calculé :** Ne pas utiliser "Épargne nette estimée" du site, toujours calculer la somme des 5 supports
- **Session persistante :** Fonctionne bien, pas de 2FA après la première connexion
- **CDP printToPDF :** Obligatoire en mode headed (page.pdf() headless uniquement)
