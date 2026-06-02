# Site BoursoBank (BB)

## Vue d'ensemble

**Site :** https://clients.boursobank.com
**Type :** Banque en ligne (comptes courant, épargne, titres)
**Collecte :** Opérations, Positions, Soldes
**Défi technique :** Clavier virtuel avec OCR + sécurisation 2FA

## Architecture technique

### 1. Authentification

#### Étape 1 : Identifiant
- Champ texte standard (`#form_clientNumber`)
- Remplissage automatique via credentials GPG

#### Étape 2 : Clavier virtuel OCR
- **10 touches randomisées** à chaque session
- Chaque touche = image SVG base64 (chiffre + lettres clavier téléphonique)
- **Extraction par OCR** (Tesseract) en 3 phases

#### Étape 3 : Sécurisation 2FA (nouvel appareil)
- Page `/securisation` → clic "Suivant"
- Page `/securisation/validation` → clic "Poursuivre"
- Envoi notification mobile → clic "Envoyer une notification"
- Attente validation sur l'app mobile BoursoBank (timeout 180s)

### 2. Clavier virtuel - Solution OCR par lettres

**Problème :** L'OCR confond fréquemment certains chiffres (4→7, 1→4, 2→8).

**Solution OCR hybride (chiffre + lettres) :**
1. Screenshot complet de la page
2. Pour chaque bouton (`button[data-matrix-key]`) :
   - OCR partie haute (chiffre) : crop 50%, Tesseract psm 10, whitelist 0-9
   - OCR partie basse (lettres) : crop 50% inférieur, Tesseract whitelist A-Z
3. **Les lettres identifient le chiffre sans ambiguïté** : GHI→4, PQRS→7, TUV→8, etc.
4. Boutons sans lettres (0 et 1) : identifiés par exclusion + densité de pixels

**Taux de succès :** ~100% (les lettres sont plus fiables que les chiffres pour l'OCR)

### 3. Session management

**Profil Chrome persistant :** `.chrome_profile_boursobank/`
- Playwright `launch_persistent_context(channel="chrome")`
- Évite de redemander le password à chaque exécution
- **Important :** Ne pas supprimer ce répertoire

### 4. Downloads

- CSV : `page.expect_download()` + `download.save_as()`
- PDF : CDP `Page.printToPDF` (mode headed, `page.pdf()` ne fonctionne qu'en headless)

## Sources de données

### 1. Compte principal (compte courant)

**Export CSV :**
- Formulaire JS avec dates (6 derniers mois)
- Fichier : `export_compte_principal.csv` (nommé directement via `save_as`)

### 2. Livret Bourso+ (livret épargne)

**Export CSV :**
- Formulaire JS avec dates (6 derniers mois)
- Fichier : `export_livret_bourso.csv` (nommé directement via `save_as`)

### 3. Portefeuille titres - Positions

**Export CSV :**
- Positions courantes (sans filtre de date)
- Fichier horodaté : `export-positions-instantanees-*.csv`

### 4. Portefeuille titres - Mouvements

**Export CSV :**
- Boucle sur 6 mois via `#form_period` (select natif masqué, interaction JS)
- Fichiers horodatés : `export-operations-*.csv`

### 5. PDFs

- **Portefeuille - BoursoBank.pdf** : solde Espèces (Réserve)
- **Mes Comptes - BoursoBank.pdf** : soldes de tous les comptes

## Extraction des URLs de comptes

Les URLs sont extraites dynamiquement du dashboard via JavaScript :
- Pattern : `/compte/<type>/[<subtype>/]<hash-32-chars>/`
- Compte principal : `/compte/cav/<hash>/`
- Livret : `/compte/epargne/csl/<hash>/`
- Portefeuille : `/compte/ord/<hash>/`

## Formulaire d'export opérations

**Champs :** `#movementSearch_fromDate`, `#movementSearch_toDate`
**Submit :** `#movementSearch_submit`
**Format :** radio `input[value='CSV']`

Remplissage via `page.evaluate()` avec events `input`/`change`.

## Configuration config.ini

```ini
[BB]
name = BoursoBank
base_url = https://clients.boursobank.com
credential_id = BaBo-M
```

## Difficultés techniques

### 1. OCR clavier virtuel (★★★★☆)

OCR hybride chiffre + lettres du clavier téléphonique. Les lettres (GHI, PQRS, etc.) sont la source de vérité pour les chiffres 2-9. Les touches 0 et 1 (sans lettres) sont identifiées par exclusion et densité de pixels.

### 2. Sécurisation 2FA (★★★☆☆)

Flow en 3 étapes automatisées (Suivant → Poursuivre → Notification) puis attente passive de la validation mobile. Ne pas naviguer pendant l'attente (sinon boucle de re-sécurisation).

### 3. Formulaire JavaScript dynamique (★★★☆☆)

Remplissage JavaScript des champs via `page.evaluate()` + events.
Select mouvements titres (`#form_period`) : natif masqué par CSS custom → `wait_for(state="attached")`.

### 4. Downloads CSV (★★☆☆☆)

`page.expect_download()` + `download.save_as()`.

### 5. Impression PDF (★★☆☆☆)

CDP `Page.printToPDF` en mode headed. Méthode `_save_page_as_pdf()` réutilisable.

## Gotchas

- **3 échecs = blocage 15 min** — Le script limite à 2 tentatives max
- **Profil Chrome** — Ne pas supprimer `.chrome_profile_boursobank/`
- **Sécurisation** — Déclenché au premier login depuis un nouvel appareil. Ne pas naviguer pendant la validation 2FA
- **Cookies** — Popup possible sur les pages de sécurisation, dismissed automatiquement
