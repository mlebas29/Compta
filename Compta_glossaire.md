# Glossaire

Glossaire du projet.

---

## A. Termes métier

- **Opération** — transaction financière attachée à un compte ; une ligne de la feuille Opérations.
- **Position / Solde** — valorisation (balance) d'un compte ou d'un titre à une date donnée.
- **Relevé / Solde calculé** — solde *relevé* = valeur externe lue d'un relevé bancaire (un écart avec le calcul est signifiant) ; *solde calculé* = synthétisé par l'import, marqué du préfixe `Σ`.
- **Avoir(s)** — feuille de synthèse donnant le total du patrimoine en euros.
- **Bien matériel** — actif non bancaire (immobilier, mobilier), saisi manuellement, sans opérations.
- **Catégorie** — regroupement d'opérations.
- **Poste budgétaire** — regroupement de catégories (niveau Fixe/Variable).
- **Portefeuille / Titre** — compte de titres ; un *titre* est une valeur cotée en bourse (obligation, action, ETF).
- **Devise / Devise dérivée** — unité de valeur (EUR, USD, XAU, BTC…) ; une devise *dérivée* est définie par une formule à partir d'une autre (once → gramme d'or).
- **Correspondance** — règle *regex → catégorie* appliquée à l'import pour la catégorisation automatique.
- **Collecte** — téléchargement des données depuis les sites Internet vers le dossier local `./dropbox`.
- **dropbox** — dossier de collecte **local** (`./dropbox`) ; ⚠ sans rapport avec le service Dropbox.
- **Import** — intégration des données collectées dans `comptes.xlsm`.
- **Cotation** — mise à jour des cours de change pour valoriser en euros les avoirs en devises non-EUR.
- **Plus-value latente (PVL)** — gain ou perte non réalisé sur un titre ou valeur non-EUR ; détail dans [`Compta_pvl.md`](Compta_pvl.md).
- **Appariement / Réf** — mise en paire d'opérations liées (virement, change, achat de titre) ; *Réf* = référence unique de la paire (colonne Réf de la feuille Opérations).
- **Virement / Change** — transfert entre deux comptes de même devise / conversion entre deux devises.
- **Ventilation (Patrimoine)** — répartition des avoirs par section patrimoniale.
- **Contrôles** — feuille de synthèse des cohérences (✓ / ⚠ / ✗) ; détail en ANNEXE A de [`Compta.md`](Compta.md).

## B. Sigles & outils techniques

- **2FA** (Two-Factor Authentication) — authentification à deux facteurs.
- **2FA mobile / action en fenêtre** — validation sur le téléphone (sans fenêtre) vs saisie *dans la page Chrome* ; cf. ANNEXE B de [`Compta.md`](Compta.md).
- **CAPTCHA** — test anti-robot à résoudre dans la page.
- **P2** — mot de passe maître de la collecte, saisi au démarrage ; il déchiffre le fichier d'identifiants chiffré par GPG.
- **GPG** (GNU Privacy Guard) — outil de chiffrement au standard OpenPGP (fichier d'identifiants).
- **OCR** (Optical Character Recognition) — reconnaissance optique de caractères (lecture du clavier virtuel de certains sites bancaires).
- **GUI** (Graphical User Interface) — interface graphique.
- **CLI** (Command-Line Interface) — lancement en ligne de commande.
- **headless / headed** — navigateur invisible (mode par défaut de la collecte) / visible.
- **API / RPC** — collecte sans navigateur (interface programmatique / appel de procédure distant), ex. BTC, XMR.
- **Playwright** — outil d'automatisation de navigateur utilisé pour la collecte.
- **LibreOffice (LO)** — suite bureautique ; moteur d'écriture du classeur.
- **regex** — expression régulière ; reconnaît un libellé par sa structure (catégorisation).
- **TNR** — tests de non-régression.
- **WSL** (Windows Subsystem for Linux) — composant Linux de Microsoft pour Windows.
- **Shebang** — première ligne `#!…` d'un script, indiquant le chemin de l'interpréteur (ici `python3`).

## C. Termes développeur

Les termes strictement **développeur** (UNO, named range/NR, format conditionnel/CF, monkeypatch, HDS…) sont définis dans [`Compta_dev.md`](Compta_dev.md).
