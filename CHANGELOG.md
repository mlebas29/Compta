# Changelog

Cet historique des versions de l'app **APP_VERSION** est orienté utilisateur ; il ne mentionne pas explicitement les changements internes du code.

**APP_VERSION** est affiché dans la fenêtre graphique et indiqué dans `inc_excel_schema.py` à côté de la version classeur (SCHEMA_VERSION).

## v3.5.5 (2026-04-17)

- Correction `cpt_fetch_quotes.py` : `NameError: name 'cr' is not defined` lors de la mise à jour des cotations

## v3.5.4 (2026-04-17)

- Outil de migration `tool_migrate_ctrl2_formulas.py` pour mettre à jour les formules `Affichage` / `Général` du tableau CTRL2 sur un classeur existant multi-devise (voir `Compta_upgrade.md`)
- Documentation de mise à niveau enrichie : rappel des modes classeur / assisté, section v3.5.2 ajoutée

## v3.5.3 (2026-04-16)

- Correction du calcul Plus-value : pour un portefeuille dans une devise non-EUR contenant un titre dans une autre devise, le Total du bloc et le TOTAL portefeuilles étaient convertis deux fois (bug latent sauf configuration spécifique)
- Formules PVL devenues génériques : plus besoin d'être regénérées à l'ajout ou suppression d'une devise
- Outil de migration `tool_migrate_pvl_totals.py` pour mettre à jour un classeur existant (voir `Compta_upgrade.md`)

## v3.5.2 (2026-04-16)

- Correction détection d'erreur Comptes : avec plusieurs devises, les écarts non-EUR n'étaient pas détectés dans le tableau de contrôle 2
- Formats devise (symbole, fond gris) appliqués sur les opérations du classeur exemple

## v3.5.1 (2026-04-15)

- Installation compatible Ubuntu 24.04 et Windows 11 (WSL2) — correction pip PEP 668
- Documentation portage Windows 11, raccourci bureau Windows
- Images README corrigées pour l'export GitHub

## v3.5.0 (2026-04-13)

- Numéro de version affiché dans le titre de la fenêtre
- Historique des versions (ce fichier)
- Correction d'un crash à l'appariement
- Correction de faux écarts sur les dates Budget lors des comparaisons
- Meilleure robustesse de la GUI au démarrage (sites, comptes, exceptions)
- Documentation alignée entre les installations (README, Changelog, guides)

## v3.4.0 (2026-04-10)

- Documentation mise à jour

## v3.3.0 (2026-04-08)

- Refonte des contrôles de solde (CTRL1) : gestion de plusieurs soldes par compte
- Colonnes Famille et Décimales ajoutées aux Cotations
- Vérification de cohérence automatique au démarrage de la GUI
- Corrections collecte : NATIXIS, ETORO, YUH, BOURSOBANK
- Corrections import : dates, dédoublonnage Wise, appariement multi-devises

## v3.2.0 (2026-04-01)

- Colonnes du classeur résolues dynamiquement (insertion/suppression de colonnes sans casser les scripts)
- Configuration centralisée dans config.ini
- Outil de déploiement et de livraison (commit, tag, export, push)
- Documentation complète générée (Compta.md, guides utilisateur)
- Installateur Linux (.desktop, support Zorin)
- Module Budget ajouté à la GUI
- Dialogue de réinitialisation du classeur

## v3.1.0 (2026-03-29)

- Biens matériels gérés depuis l'onglet Comptes
- Documentation Export complète

## v3.0.0 (2026-03-27)

- Cotations dérivées avec formule automatique (Or joaillier, Or premier, Argent…)
- Formats de devise dynamiques (plus de valeurs en dur)
- Plus-values multi-devises avec totaux par portefeuille
- Gestion du Patrimoine dans la GUI (ajout, modification, suppression)
- Type et sous-type pour les Dettes (symétrique des Créances)
