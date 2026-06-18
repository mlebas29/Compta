# Mise à niveau du classeur (mode classeur)

Vous tenez le classeur à la main, sans `upgrade` (pour le mode assisté en un geste, voir [`Compta_upgrade_assiste.md`](Compta_upgrade_assiste.md)). **Deux chemins :**

- soit **partir du classeur exemple le plus récent** ([`comptes_exemple.xlsx`](https://github.com/mlebas29/Compta/raw/main/comptes_exemple.xlsx)) et y reporter **vos propres données** ;
- soit **partir de votre classeur** et y reporter à la main les évolutions décrites ci-dessous (en vous aidant de l'exemple au besoin).

<!-- bloc généré : ./tool_render_upgrade_map.py --mode classeur — ne pas éditer à la main -->

**Légende des badges** :

- 📘 contenu : nouveau classeur exemple — récupérer le nouveau classeur exemple

| Version | Classeur | Effet |
|---|:--:|---|
| v5.0.1 | 📘 | classeur exemple livré (intègre la migration v5.0.0) |
| v4.1.0 | 📘 | refonte CTRL2 + alarmes |
| v4.0.0 | 📘 | drill devise (élimine les colonnes par devise) |

<!-- fin bloc généré -->

**Notes :**

- **drill (devise)** = modèle « une colonne par devise → colonnes génériques avec menu déroulant » (chantier v4.0.0).


## v5.0.1 📘 — Classeur exemple intégrant la migration v5.0.0 + prérequis LibreOffice ≥ 24.8

`SCHEMA_VERSION` inchangé. Les classeurs livrés (`comptes_template.xlsm`, `comptes_exemple.xlsx`) intègrent les 2 améliorations de formules v5.0.0 :

- `Cotations!B{alarme métier}` : wrapper `IFERROR(SUMPRODUCT(...);1)` — capte les `#REF!` orphelines en COTcours.
- `Contrôles!K{Synthèse}` : wrapper `IFERROR(K{section};"⚠")` sur chaque token — une section en erreur ne fait plus tomber la synthèse à ✓.

**Prérequis** : LibreOffice ≥ 24.8 (mapping `_xlfn.XLOOKUP`). Les versions antérieures (notamment 24.2.x, livrée par défaut sur Ubuntu 24.04) corrompent silencieusement les formules XLOOKUP lors d'une sauvegarde.

**Mise à niveau** — récupérer le nouvel exemple `comptes_exemple.xlsx` (il intègre déjà les 2 améliorations), ou les reporter à la main. Vérifier que LibreOffice est ≥ 24.8 avant de sauvegarder le classeur.


## v5.0.0 — Fiabilisation alarmes (anti-`#REF!` orphelines)

`SCHEMA_VERSION` inchangé (reste à 3) : pas de bump structurel, 2 améliorations de formules **idempotentes**. L'exemple **v5.0.1** (📘) les intègre — le récupérer suffit. Sinon, à reporter à la main :

*Cotations*

- Cellule `B{alarme métier}` (col B, ligne juste après la 2e sentinelle ⚓) : wrapper `IFERROR(SUMPRODUCT(...);1)` sur la branche completeness (cas codes listés mais cours vide). Capte aussi les `#REF!` orphelines en COTcours après suppression d'une devise parente sans nettoyage des dérivées.

*Contrôles*

- Cellule `K{Synthèse}` (ligne 'Synthèse des contrôles') : wrapper `IFERROR(K{section};"⚠")` sur chaque token (COMPTES, CATÉGORIES, DIVERS, APPARIEMENTS, BALANCES, INCONNUS, FORMULES). Sans ce wrapper, une section déjà en erreur (`#REF!` propagé) faisait tomber la synthèse à ✓ silencieusement.


## v4.1.0 📘 — Fiabilisation Plus_value + refonte alarmes Contrôles

Schéma `SCHEMA_VERSION 2 → 3`.

> Cette migration cumule de nombreuses opérations dans le classeur (insertion de lignes, recopie de formules, mises en forme conditionnelles, renommages) : compter au moins une heure de saisie minutieuse en report manuel, avec un risque réel d'erreur. **Récupérer le classeur exemple le plus récent est nettement plus fiable** ; le report manuel ci-dessous n'est utile que pour patcher un classeur existant qu'on tient à conserver tel quel.

**Modifications appliquées** (à reporter manuellement, en s'aidant de `comptes_exemple.xlsx`) :

*Plus_value*

- Pied **Total** de chaque portefeuille : recopier la formule unifiée (colonnes H/I/K + *Date initiale* + *Date solde*).
- 5 pieds (GRAND TOTAL + 4 totaux de section) : col **PVL %** = `=E…/(H…+I…)` (au lieu de `E/(I+K)`).
- Pied **TOTAL portefeuilles** : recopier la formule (SUMPRODUCT générique avec lookup COTcours).
- Pieds **TOTAL métaux / crypto-monnaies / devises** : recopier les formules H/I/K (SUMIFS sur named ranges).
- Sections métaux / crypto-monnaies / devises : appliquer le format EUR aux colonnes *PVL*, *Montant initial*, *Sigma*, *Montant actuel* (au lieu de la devise native).

*Contrôles*

- Renommer la ligne *Cohérence* (ou *Date*) en **DIVERS**, ajouter 3 sous-lignes : *Date hors période*, *Ventilation Patrimoine*, *Cotations*.
- Insérer une ligne **FORMULES** avant la sentinelle ⚓ basse, avec 2 sous-lignes : *Avoirs*, *Plus_value*.
- Indenter les sous-lignes BALANCES (*Virements €*, *Titres €*, *Changes Eq €*, *Total €*).
- Mettre les labels en MAJUSCULES (DIVERS, FORMULES, BALANCES, APPARIEMENTS).
- Ajuster la formule **Synthèse des contrôles** pour 7 jetons (au lieu de 6).
- Poser une mise en forme conditionnelle rouge sur `Plus_value!B3`, `Avoirs!L1`, et la cellule alarme *Cotations* (en pied de la liste cotations).

*Patrimoine*

- Ajouter en pied une ligne **Erreurs** (col B) avec le compteur des écarts de ventilation (col D) — formule `=(ABS(D{section1}-D4)>0.5)+…` sur les 5 sections.

*Cotations*

- Ajouter en pied une cellule alarme métier (label *Alarme cotations* en col A) qui détecte les devises utilisées sans cours et les codes sans valeur.

*Conventions* (tableau dans Patrimoine)

- Renommer la ligne `Cohérence` en `DIVERS`.

*Schéma*

- `SCHEMA_VERSION` 2 → 3.


## v4.0.0 📘 — Devises N→1 colonne + charte graphique

Schéma `SCHEMA_VERSION 1 → 2`. Migration **structurelle** lourde (drill devise).

**Mise à niveau** — sauvegarder le classeur, copier `comptes_template.xlsm` (livré v4 dans le repo), puis réimporter les données via l'application (collecte + import) ou par copier-coller depuis la sauvegarde. Un classeur antérieur à v4.0.0 relève de la note **≤ v3.x** ci-dessous.


## ≤ v3.x — repartir de l'exemple

Pour un classeur **antérieur à v4.0.0**, la mise à niveau la plus simple est de **repartir du classeur le plus récent** ; deux cas, selon que le classeur portait déjà un schéma versionné :

- **Schéma 1** (v3.2 – v3.5.x, named ranges colonnes + `SCHEMA_VERSION` = 1) : récupérer `comptes_exemple.xlsx` (il intègre toutes les évolutions) ou copier `comptes_template.xlsm`, puis réimporter les données. Les fixes intermédiaires v3.5.x (PVL multi-devise, CTRL2, alarmes balances) sont détaillés dans `CHANGELOG.md` pour qui veut patcher à la main ; ils sont de toute façon repris dans la structure de l'exemple courant.
- **Sans schéma** (avant v3.2, pas de named ranges de version) : le classeur ne contient pas les named ranges nécessaires à l'application. Le recréer depuis `comptes_template.xlsm` :

  ```bash
  cp comptes.xlsm comptes_backup.xlsm   # sauvegarder
  cp comptes_template.xlsm comptes.xlsm # repartir du template à jour
  ```

  Relancer l'app : le nouveau classeur est vierge ; réimporter les données via l'application (collecte + import) ou par copier-coller depuis la sauvegarde.
