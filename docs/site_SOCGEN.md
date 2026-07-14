# Société Générale — collecte

> Détails vivants (comptes, sélecteurs, flux, fichiers) = **le code**, source de vérité :
> `cpt_fetch_SOCGEN.py` (collecte) et `cpt_format_SOCGEN.py` (formatage).
> La constante `DESCRIPTION` de `cpt_fetch_SOCGEN.py` alimente la GUI (onglet Sites) : config par compte + procédure 2FA.

**En bref** — banque en ligne. Login automatique par OCR du clavier virtuel (Tesseract) puis 2FA occasionnel validé sur l'app mobile. Collecte CSV (compte courant + épargne), XLSX (supports assurance vie) et PDF (opérations AV + synthèse des soldes).

**À savoir**

- **Types de compte config-driven** : `principal` / `epargne` / `assurance_vie` sont pilotés par `config_accounts.json` (numéros, ID techniques, clés fichiers) — rien de figé dans le code.
- **PDF synthèse** : `Mes comptes en ligne _ SG.pdf` est imprimé à la collecte puis parsé (`process_pdf_synthese`) pour produire les lignes `#Solde` de tous les comptes.
- **Agrégat ETF hors code public** : le cœur public délègue au hook `post_process_supports` (pass-through). La logique de regroupement des supports ETF vit dans un monkeypatch privé `custom/patch_*.py`, pas dans le dépôt public.
- **Renommage des supports** : `SUPPORT EURO` → `SÉCURITÉ EUROS` (cas spécial), puis `support_renames` de `config_accounts.json` (exact puis préfixe) ; supports fusionnés = valorisations additionnées.

Contrat de formatage Tier 2 : voir [`Compta_site.md`](../Compta_site.md). Renommage en collecte manuelle : voir `Compta_plus.md`.
