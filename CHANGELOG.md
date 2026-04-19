# Changelog

Cet historique des versions de l'app est orienté utilisateur ; il ne mentionne pas explicitement les changements internes du code.

**Pour le détail des mises à niveau classeur : voir `Compta_upgrade.md`**



## v3.5.7 (2026-04-18)
*Mise à jour — app : 🟠 recommandée · classeur : 🟠 recommandée*

- Plus-value métaux / crypto / devises : colonnes *PVL* et *Solde* affichées en EUR (cohérent avec les formules, auparavant symbole de la devise du compte).
- Ancrage PVL dynamique — usage détaillé dans `Compta_plus.md` §*Eq. EUR*.
- GUI ajout de compte : champ *Équiv. EUR* obligatoire si devise ≠ EUR et solde initial ≠ 0.
- 🔧 **`tool_migrate_pvl_ancrage.py`** pour mettre à niveau un classeur existant (valeurs manuelles préservées).

## v3.5.6 (2026-04-17)
*Mise à jour — app : 🟠 recommandée · classeur : 🟢 optionnelle*

- Import : deux `#Solde` à dates différentes pour un même compte sont désormais conservés tous les deux (ancrage + relevé final).
- Budget : ajout de plusieurs postes en une fois — Total épargne désormais correct (auparavant seul le premier poste était sommé).
- Classeur vierge : formules de pied Budget (Total hors Changes/Virements, Total épargne, Épargne fixe) désormais en plage auto-extensible.
- Classeur exemple : fond des colonnes devise du tableau CATÉGORIES assorti aux lignes.

## v3.5.5 (2026-04-17)
*Mise à jour — app : 🔴 critique (module cotations) · classeur : ⚪ aucune*

- Correction `cpt_fetch_quotes.py` : `NameError: name 'cr' is not defined` lors de la mise à jour des cotations.

## v3.5.4 (2026-04-17)
*Mise à jour — app : 🟢 optionnelle · classeur : 🟠 recommandée (utilisateurs multi-devise)*

- 🔧 **`tool_migrate_ctrl2_formulas.py`** pour mettre à niveau les formules CTRL2 sur un classeur existant multi-devise (outil v3.5.2 livré en v3.5.4).
- Documentation de mise à niveau enrichie (rappel modes classeur / assisté, section v3.5.2).

## v3.5.3 (2026-04-16)
*Mise à jour — app : 🟠 recommandée · classeur : 🟢 optionnelle*

- Plus-value : correction du double comptage de cours sur portefeuille non-EUR pivot contenant un titre dans une autre devise.
- Formules PVL génériques : plus de regénération à l'ajout/suppression d'une devise.
- 🔧 **`tool_migrate_pvl_totals.py`** pour mettre à niveau un classeur existant.

## v3.5.2 (2026-04-16)
*Mise à jour — app : 🟠 recommandée · classeur : ⚪ aucune (migration livrée en v3.5.4)*

- Détection d'erreur Comptes : les écarts non-EUR sont désormais remontés dans le tableau de contrôle 2.
- Formats devise (symbole, fond gris) appliqués aux opérations du classeur exemple.
- 🔧 **`tool_migrate_ctrl2_formulas.py`** pour mettre à niveau un classeur existant (outil livré en v3.5.4).

## v3.5.1 (2026-04-15)
*Mise à jour — app : 🟠 recommandée (Ubuntu 24.04 / WSL2) · classeur : ⚪ aucune*

- Installation compatible Ubuntu 24.04 et Windows 11 (WSL2) — correction pip PEP 668.
- Documentation portage Windows 11, raccourci bureau Windows.
- Images README corrigées pour l'export GitHub.

## v3.5.0 (2026-04-13)
*Mise à jour — app : 🟠 recommandée · classeur : ⚪ aucune*

- Numéro de version affiché dans le titre de la fenêtre.
- Historique des versions (ce fichier).
- Correction d'un crash à l'appariement.
- Correction de faux écarts sur les dates Budget lors des comparaisons.
- Meilleure robustesse de la GUI au démarrage (sites, comptes, exceptions).
- Documentation alignée entre les installations (README, Changelog, guides).

## v3.4.0 (2026-04-10)

- Documentation mise à jour

## v3.3.0 (2026-04-08)

- Refonte des contrôles de solde (CTRL1) : gestion de plusieurs soldes par compte
- Colonnes Famille et Décimales ajoutées aux Cotations
- Vérification de cohérence automatique au démarrage de la GUI
- Corrections collecte : NATIXIS, ETORO, BOURSOBANK
- Corrections import : dates, dédoublonnage Wise, appariement multi-devises
- 🔧 **`tool_migrate_ctrl1.py`** pour porter le tableau CTRL1 d'un classeur v3.2 vers la nouvelle structure.

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
