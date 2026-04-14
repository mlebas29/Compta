# Changelog

Cet historique des versions de l'app est orienté utilisateur ; il ne mentionne pas explicitement les changements internes du code.

Hors l'affichage GUI, la version installée de l'app (**APP_VERSION**) est indiquée dans **inc_excel_schema.py**, à côté de la version classeur (SCHEMA_VERSION).

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
