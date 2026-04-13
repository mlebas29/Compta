# Changelog

## v3.5.0 (2026-04-13)

Fixes
- fix: ColResolver dans cpt_pair — crash NoneType après refactor (wb pas encore ouvert)
- fix: comparaison brutal_only enchaînait une double comparaison inutile (brutal + compare_sheets)
- fix: cellules TODAY() Budget exclues de la comparaison (faux diff dates)
- fix: palette gris devise dual tone + blanc titres PVL + refonte fix_budget
- fix: auto-désactivation des sites sans compte au démarrage (warning → auto-fix)
- fix: refresh liste Sites après désactivation auto du dernier compte
- fix: auto-rebuild config_accounts.json uniquement si fichier absent
- fix: garde hasattr sur _load_excel_data (AttributeError en mode GUI)
- fix: _bien_add — _run_uno_operation au lieu de _save_and_reload (GUI)
- fix: supprime check_done() résiduel dans _run_devise_save (NameError)
- fix: attrape-exceptions GUI (report_callback_exception + try/except main)
- fix: refresh status bar après enregistrement sites
- fix: import circulaire gui_devises ↔ cpt_gui
- fix: import write_config_section_key dans gui_devises (sauvegarde sites)
- fix: _save_config recharge ConfigParser (check cohérence)
- fix: cr non défini dans _append_solde_lines (staticmethod)
- fix: chevauchement champs dans dialogue ajout compte

Infrastructure
- APP_VERSION dans inc_excel_schema.py, affichée dans le titre GUI
- SCHEMA_VERSION restauré dans le classeur DEV et toutes les données de test
- 7 named ranges COT ajoutés aux données de test pipe
- Expected format régénérés (formatteurs avaient évolué)
- CHANGELOG.md créé

Docs
- README : section Restrictions, Installation/GUI, note Wayland, Signaler un bug
- Relecture Compta*.md (Dropbox → dossier collecte, Contrôles A1, colonnes CTRL1)

## v3.4.0 (2026-04-10)

Docs
- Grille v3.4 mise à jour, items export résolus

## v3.3.0 (2026-04-08)

Features
- Refonte CTRL1 : modèle 0..N #Solde via XLOOKUP min/max (suppression D/F/L)
- Cotations : colonnes Famille/Décimales, suppression END_OP, template robustifié
- GUI : check cohérence au démarrage, dialogue modification dynamique, export squelette cotations
- tnr_pipe v2 : snapshot collecte réelle 14 sites + MANUEL, expected versionné

Fixes
- tnr_reverse vert : 6 fixes teardown (devises, AvoirsL, CTRL2 h+2, PV spacer, patrimoine, blank)
- Collecte (5 sites) : NATIXIS/ETORO 2FA, YUH auto-mount, BOURSOBANK retry 401
- Import/appariement : date type, tolérance cross-ccy, dédup Wise, ORCHESTRA APPEL/APPLE
- CTRL1 example : Biens matériels, fond gris EUR, bordures Commentaires
- delete_devise : scan dynamique col CTRL2 depuis START_CTRL2
- cpt_pair refresh_controles inconditionnel
- tool_fix_named_ranges gère no_end (OP)

Refactors
- Suppression miroirs Contrôles!C1 / Avoirs!L1 (lecture A1/L2 cached)

## v3.2.0 (2026-04-01)

Architecture
- Migration FIRST_ROW → named ranges START/END (3 phases, 8 paires)
- Coches aux model rows, nettoyage unifié (_blank_table)
- Déduplication mixins : BudgetMixin, DevisesMixin
- Mode config.ini (suppression COMPTA_MODE)

TNR
- tnr_reverse complet : teardown example → template
- tnr_template restauré
- compare_xlsx --brutal (7 feuilles)

Export
- tool_commit.sh : sync + commit DEV/Export + tag + push
- Documentation Markdown générée (Compta.md/Compta_plus.md/Compta_tools.md)
- install.sh : .desktop dynamique, support Zorin
- Dialogue Réinitialiser Export (classeur vierge / réinstallation)
- gui_budget.py ajouté

## v3.1.0 (2026-03-29)

- Biens matériels onglet Comptes
- Refonte export TNR
- Documentation Export

## v3.0.0 (2026-03-27)

Devises & Cotations
- Cotations dérivées avec formule auto (OrJo, OrPr, AgJo…)
- Colonne Nature (primaire/dérivée) dans feuille Cotations
- Formats devise dynamiques depuis config_cotations.json
- PVL multi-devises : TOTAL portefeuilles + comparaison totaux

Patrimoine & Avoirs
- Biens matériels lus depuis ref_man
- CRUD Patrimoine — sync automatique des 5 blocs
- Type et sous-type Dettes

TNR
- Réorganisation en scénarios indépendants
- Mode batch UNO : example 38s au lieu de 5min (gain ×8)
- Config pipeline propre à chaque scénario
