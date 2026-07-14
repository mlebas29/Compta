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
2. Saisie login (input standard) → bouton « Je valide »
3. Clavier virtuel pour mot de passe (chiffres dans le DOM)
4. Validation (bouton « Suivant »)
5. Assistant « appareil de confiance » à écarter (voir ci-dessous)

**Assistant « appareil de confiance » (Natixis 2026) :** Après le mot de passe, le site propose d'enrôler l'appareil (« Simplifiez vos prochaines connexions / Enregistrer un appareil de confiance »). `_dismiss_trusted_device_interstitial()` le franchit en 2 écrans, best-effort (chaque étape est absente si déjà écartée) :
1. Écran 1 : cliquer **« Plus tard »** (ne PAS enrôler). Sans ça, la page reste sur l'IdP SAML (`/auth`) et la détection de connexion timeoute.
2. Écran 2 : cocher **« Ne plus proposer ce message »** (best-effort) puis **« Continuer »**.

Il n'y a **pas** de 2FA classique (SMS/OTP) : le login aboutit directement, mais franchit cet assistant. Le profil Chrome `.chrome_profile_natixis/` persiste la session et la coche « ne plus proposer », si bien que l'assistant est généralement absent aux runs suivants.

**Détection de session :** Vérifie l'absence du formulaire de login (`input[data-testid='login-form-input']`). Connexion confirmée par une URL stable hors du flux login (`!/login && !/auth && readyState complete`).

## Particularités techniques

### Collecte par impression PDF (Angular)

**Contexte :** Le site est une SPA Angular qui rend tout via JavaScript. Plutôt que de gratter le DOM, le fetch **navigue vers chaque page et l'imprime en PDF** (via CDP `Page.printToPDF`, cf. plus bas). Le parsing des montants/opérations est fait ensuite par `cpt_format_NATIXIS.py` (pdfplumber), pas au moment de la collecte.

**Deux pages imprimées :**
- Positions : `.../front/saving-detail` → `Mon épargne en détail - Natixis Interépargne.pdf`
- Opérations : `.../front/transactions` → `Historique et suivi de mes opérations - Natixis Interépargne.pdf`

Avant impression, on attend le rendu Angular (`app-root` attaché + `networkidle` + court `sleep`).

**Robustesse :** le PDF **positions** est non-bloquant (soldes recalculés à l'import, avec alerte si l'écart est notable) ; seul l'échec du PDF **opérations** fait échouer la collecte.

### Solde

Le solde total est **lu dans le PDF positions** (`Plan d'épargne : XXX,XX EUR`), et non recalculé au fetch. Le nombre de fonds HSBC EE est **dynamique** (dépend de l'allocation du PEE du salarié) : le formatteur détecte chaque ligne `Épargne sur ce fonds : XXX,XX EUR` sans nombre figé.

## Collection

### Fichiers produits par le fetch : 2 PDF

Le fetch imprime les deux PDF listés dans `EXPECTED_FILES` de `cpt_format_NATIXIS.py`, dans `dropbox/NATIXIS/` :

- **`Mon épargne en détail - Natixis Interépargne.pdf`** — positions (fonds HSBC EE) + solde
- **`Historique et suivi de mes opérations - Natixis Interépargne.pdf`** — historique des opérations

Ces PDF sont parsés par `process_pdf_printed()` (pdfplumber) : le type est détecté par le texte (`"Historique et suivi"` vs `"Mon épargne en détail"`/`"Estimation au"`), puis les opérations et positions sont extraites. Le nombre de fonds et d'opérations est variable.

### Fallback CSV (legacy)

Le formatteur accepte encore des CSV via des handlers de secours (collecte manuelle) — **ce n'est pas le flux nominal** :

- `operations*.csv` → `Date;Nature;Montant;Statut` (`process_operations`)
- `supports*.csv` / `positions*.csv` → `Nom;Montant` (`process_positions`)

**Doublons légitimes :** plusieurs arbitrages le même jour peuvent partager le libellé "Modification de placements" et un montant formaté à 0,00.

## Formatage (cpt_format_NATIXIS.py)

### Types d'opérations

Le **libellé** et le **montant** sont dérivés de la nature ; la **catégorie** est ensuite déterminée par `inc_categorize.categorize_operation(libelle, SITE)` (config-driven via les patterns du site), qui fournit aussi la réf éventuelle (`opts['ref']`). Les noms de catégories ci-dessous sont donc indicatifs — la vérité est dans la config de catégorisation, pas en dur dans le formatteur.

**1. Arbitrage** ("Modification de placements")
- Déplacement interne à somme nulle
- **Montant :** ramené à 0,00
- **Libellé :** le montant d'origine est **intégré au libellé** : `f"{nature} ({montant}€)"` (ex: `Modification de placements (10000,00€)`)
- **Commentaire :** vide

**2. Versement** ("INVESTISSEMENT DE VOTRE INTERESSEMENT", etc.)
- Versement employeur / intéressement
- **Montant :** montant réel
- **Libellé :** la nature telle quelle

**3. Virement** ("Remboursement des avoirs disponibles")
- Retrait vers compte bancaire — nature commençant par `Remboursement`
- **Montant :** forcé négatif (préfixe `-`)
- **Réf :** issue de la catégorisation (`opts['ref']`)

**4. Solde** ("#Solde")
- Ligne de solde (total)
- **Libellé :** "Relevé compte"
- **Catégorie :** "#Solde"

### Format de sortie

**Standard 9 champs :** `Date;Libellé;Montant;Devise;Equiv;Réf;Catégorie;Compte;Commentaire`

**Compte :** unique (`MAX_ACCOUNTS = 1`), résolu paresseusement depuis `config_accounts.json` (`ACCOUNT_NAME`).

**Commentaire :** toujours vide (le montant d'origine des arbitrages est dans le libellé, pas ici).

## Import (cpt_update.py)

### Positions → Plus_value

Les positions PEE sont traitées comme les supports SG (assurances vie). Flux nominal : elles proviennent du **PDF positions** (`process_pdf_printed` → format 4 colonnes `Date;Ligne;Montant;Compte`, stocké via `_pdf_positions` puis réinjecté par `format_site`). En secours, un CSV `supports*.csv`/`positions*.csv` alimente le même `process_positions`.

1. Extraction des lignes `Épargne sur ce fonds : XXX,XX EUR` (nombre dynamique de fonds)
2. Format `Date;Ligne;Montant;Compte`
3. Mise à jour de la feuille Plus_value
4. Match par nom de support (recherche partielle)
5. Update colonnes J (Date SOLDE) et K (SOLDE)

**Compte :** unique, résolu via `ACCOUNT_NAME` (`config_accounts.json`).

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

### Solde incorrect / manquant

**Cause :** ligne `Plan d'épargne : XXX,XX EUR` non trouvée dans le PDF positions (format changé, PDF tronqué)

**Solution :** vérifier le PDF `Mon épargne en détail`. Le solde en est lu directement ; s'il manque, il est recalculé à l'import à partir des positions (avec alerte si l'écart est notable).

### Langue en anglais

**Cause :** Sélection de langue échouée ou profil Chrome vide

**Solution :**
1. Supprimer `.chrome_profile_natixis/`
2. Faire une connexion manuelle en français
3. Le profil sauvegarde la préférence

### Assistant « appareil de confiance » réapparaît

**Cause :** Profil Chrome supprimé ou coche « ne plus proposer » perdue → l'assistant post-login revient

**Solution :** Ne jamais supprimer `.chrome_profile_natixis/`. `_dismiss_trusted_device_interstitial()` le franchit de toute façon (« Plus tard » puis « Continuer ») ; s'il change de libellé, adapter les sélecteurs (`Plus tard`/`Later`, `Continuer`/`Continue`).

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

- **Collecte = impression PDF :** on navigue vers chaque page Angular et on l'imprime (CDP `printToPDF`) ; le parsing (opérations, positions, solde) est fait ensuite par pdfplumber dans le formatteur — pas de scraping DOM ni innerText/regex au fetch
- **Solde lu du PDF :** `Plan d'épargne : XXX,XX EUR` dans le PDF positions ; nombre de fonds dynamique
- **Profil Chrome :** persiste la session et la coche « ne plus proposer », sauvegardé dans `.chrome_profile_natixis/`
- **Pas de 2FA classique :** le login aboutit directement mais franchit l'assistant « appareil de confiance » (`_dismiss_trusted_device_interstitial`)
- **CDP printToPDF :** obligatoire en mode headed (`page.pdf()` headless uniquement)
