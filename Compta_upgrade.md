# Mise à niveau du classeur

Ce document catalogue les **migrations du classeur** `comptes.xlsm` par version. En **mode assisté**, [`install_upgrade.py`](Compta_install_upgrade.md) les applique ; en **mode classeur**, à reporter à la main. Pour la liste des changements par version : `CHANGELOG.md`.

**Rappel** — [modes d'utilisation](README.md#1-points-de-départ)

| Mode classeur | Mode assisté |
| --- | --- |
| Seul `comptes.xlsm` est utilisé ; mise à niveau manuelle dans le tableur en s'appuyant sur [`comptes_exemple.xlsx`](https://github.com/mlebas29/Compta/raw/main/comptes_exemple.xlsx) comme référence. | À partir de **5.3.0** : un seul geste, [`./install_upgrade.py`](Compta_install_upgrade.md) (code + classeur).<br />Avant 5.3.0 : `git pull` (procédures éventuelles dans `CHANGELOG`). |

Au démarrage (mode assisté), l'app vérifie la `SCHEMA_VERSION` du classeur ; une incompatibilité bloque l'exécution. Les autres mises à niveau (formules, formats) sont optionnelles à recommandées — elles n'empêchent pas l'app de tourner mais peuvent fausser des calculs.

**Lecture du CHANGELOG** — chaque version peut porter deux badges :

- 📘 = nouveau classeur exemple livré → mode classeur : comparer son `comptes.xlsm` à `comptes_exemple.xlsx` sur la zone indiquée ci-dessous.
- 🔧 = migration du classeur livrée (changement de structure/formules) → **mode assisté** : `install_upgrade` la propose (consentement) ; **mode classeur** : à reporter à la main (cf. section par-version).

Une version peut porter l'un, l'autre, ou les deux. Les sections ci-dessous suivent le même découpage.


## Mise à niveau en mode classeur — récupérer l'exemple

> En **mode classeur**, vous tenez `comptes.xlsm` à la main, **sans** `install_upgrade`. Le geste de mise à niveau y est simple : quand une version livre un **nouveau classeur exemple** (📘), récupérez le plus récent — il intègre déjà la nouvelle structure. _(Mise à niveau **assistée** : [`Compta_install_upgrade.md`](Compta_install_upgrade.md). Détail technique par version — SCHEMA, outil — dans les sections ci-dessous.)_

**Légende des badges** (geste en mode classeur) :

- 📘 contenu : nouveau classeur exemple — récupérer le nouveau classeur exemple

### Classeur (structure & contenu)

| Version | Badges | Effet |
|---|---|---|
| v4.0.0 | 📘 | drill devise (élimine les colonnes par devise) |
| v4.1.0 | 📘 | refonte CTRL2 + alarmes |
| v5.0.1 | 📘 | classeur exemple livré (intègre la migration v5.0.0) |

_Dérivé de `upgrade_map.json` (régénérer : `./tool_render_upgrade_map.py --mode classeur`)._

**Notes :**
- **SCHEMA** = `SCHEMA_VERSION`, le numéro de **structure** du classeur. Une migration **structurelle** le fait monter (ex. `1 → 2`) et est **bloquante** : l'app refuse de tourner sur un classeur en retard.
- **catch-up** = mise à niveau qui **ne change pas** la structure (`SCHEMA` inchangé) mais corrige/fiabilise des formules ; **idempotente** (la relancer ne fait rien si déjà appliquée) → non bloquante.
- **drill (devise)** = modèle « une colonne par devise → colonnes génériques avec menu déroulant » (chantier v4.0.0).


## v5.0.1 📘 — Classeurs avec migration v5.0.0 intégrée + prérequis LibreOffice ≥ 24.8

`SCHEMA_VERSION` inchangé. Pas d'outil de migration livré (la migration v5.0.0 reste l'outil de référence pour rattraper les améliorations de formules).

**Nouveautés livrées :**

- Les **classeurs livrés** (`comptes_template.xlsm`, `comptes_exemple.xlsx`) intègrent désormais les 2 améliorations de formules v5.0.0 :
  - `Cotations!B{alarme métier}` : wrapper `IFERROR(SUMPRODUCT(...);1)` — capte les `#REF!` orphelines en COTcours.
  - `Contrôles!K{Synthèse}` : wrapper `IFERROR(K{section};"⚠")` sur chaque token — une section en erreur ne fait plus tomber la synthèse à ✓.
- **Prérequis** : LibreOffice ≥ 24.8 (mapping `_xlfn.XLOOKUP`). Les versions antérieures (notamment 24.2.x livrée par défaut sur Ubuntu 24.04) corrompent silencieusement les formules XLOOKUP lors d'une sauvegarde via UNO. La garde `inc_uno.require_libreoffice_min` refuse d'exécuter les `tool_migrate_*` sur LO < 24.8.

| Mode classeur | Mode assisté |
| --- | --- |
| Vérifier que LibreOffice est ≥ 24.8 avant de sauvegarder le classeur. Reporter les 2 améliorations ci-dessus dans son `comptes.xlsm` en s'appuyant sur le nouvel exemple `comptes_exemple.xlsx`. | `git pull` puis relancer `./install.sh` — sur Linux/WSL, l'installeur met à niveau LibreOffice automatiquement via le PPA `libreoffice/ppa` si nécessaire. Sur macOS, installer la version 24.8.x manuellement depuis libreoffice.org. Si la migration v5.0.0 n'a pas été appliquée, lancer `./tool_migrate_v5.0.0.py ~/Compta/comptes.xlsm` (idempotent). |


## v5.0.0 🔧 — Architecture `custom/`, portage macOS, TNR + fiabilisation alarmes

`SCHEMA_VERSION` inchangé (reste à 3) : pas de bump structurel. Mais la version livre 2 améliorations de formules anti-`#REF!` orphelines via un outil idempotent. Optionnelle si le classeur n'a jamais subi de suppression de devise mère sans nettoyage préalable des dérivées — mais recommandée pour mettre la garde en cohérence avec les alarmes.

| Mode classeur | Mode assisté |
| --- | --- |
| Voir la liste des modifications ci-dessous (à reporter dans le classeur). | `tool_migrate_v5.0.0.py` (procédure ci-dessous). |

*Procédure mode assisté (LibreOffice fermé) :*

```bash
./tool_migrate_v5.0.0.py ~/Compta/comptes.xlsm
```

**Modifications appliquées :**

*Cotations*

- Cellule `B{alarme métier}` (col B, ligne juste après la 2e sentinelle ⚓) : wrapper `IFERROR(SUMPRODUCT(...);1)` sur la branche completeness (cas codes listés mais cours vide). Capte aussi les `#REF!` orphelines en COTcours après suppression d'une devise parente sans nettoyage des dérivées.

*Contrôles*

- Cellule `K{Synthèse}` (ligne 'Synthèse des contrôles') : wrapper `IFERROR(K{section};"⚠")` sur chaque token (COMPTES, CATÉGORIES, DIVERS, APPARIEMENTS, BALANCES, INCONNUS, FORMULES). Sans ce wrapper, une section déjà en erreur (`#REF!` propagé) faisait tomber la synthèse à ✓ silencieusement.


## v4.1.0 📘🔧 — Fiabilisation Plus_value + refonte alarmes Contrôles

Schéma `SCHEMA_VERSION 2 → 3`. Outil idempotent : exécution sans effet sur un classeur déjà à niveau.

> **Recommandation pour le mode classeur** — la migration v4.1.0 cumule de nombreuses opérations dans le classeur (insertion de lignes, recopie de formules, pose de mises en forme conditionnelles, renommages). Compter au moins une heure de saisie minutieuse, avec un risque réel d'erreur. Il est plus simple de **basculer ponctuellement en mode assisté** le temps de la migration, puis de revenir au mode classeur si on le souhaite :
>
> ```bash
> git clone https://github.com/mlebas29/Compta.git ~/Compta-tmp
> cd ~/Compta-tmp
> bash install_migrate.sh             # installation minimale (Python + LibreOffice + openpyxl)
> ./tool_migrate_v4.1.0.py ~/Compta/comptes.xlsm
> ```
>
> `install_migrate.sh` est une variante allégée de `install.sh` (sans Playwright, Tkinter, GPG, OCR…). Procédure **Linux** ou **Windows 11 + WSL2** uniquement — Windows pur n'est pas supporté. Une fois la migration faite, le clone `~/Compta-tmp` peut être supprimé.

| Mode classeur | Mode assisté |
| --- | --- |
| Voir la liste des modifications ci-dessous (à reporter dans le classeur en s'aidant de `comptes_exemple.xlsx`). | `tool_migrate_v4.1.0.py` (procédure ci-dessous). |

*Procédure mode assisté (LibreOffice fermé) :*

```bash
./tool_migrate_v4.1.0.py ~/Compta/comptes.xlsm
```

À la fin de l'exécution, l'outil affiche un **rapport de deltas** sur les 5 pieds Plus_value (GRAND TOTAL et 4 totaux de section) — utile pour repérer les portefeuilles dont la valeur *Retenu* a basculé après la correction des dates de pied.

**Modifications appliquées** (à reporter manuellement en mode classeur) :

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

**Note** — vu le volume, le passage par `tool_migrate_v4.1.0.py` est nettement plus fiable que le report manuel.


## v4.0.0 📘 🔧 — Devises N-->1 colonne + charte graphique 

Schéma `SCHEMA_VERSION 1 → 2`.

| Mode classeur | Mode assisté |
| --- | --- |
| Sauvegarder, copier `comptes_template.xlsm` (livré v4 dans le repo), réimporter les données. | `tool_migrate_schema_v2.py` (procédure ci-dessous). |

**Versions sources couvertes par l'outil :**
- v3.5.x : cas nominal, migration directe.
- v3.4.0 : tolérée (pas de bump si `SCHEMA_VERSION` absente).
- v3.0–v3.3 : **non couvert**. Suivre d'abord §v3.2 ci-dessous (template + réimport) ; le template livré étant déjà v4, la migration est inutile ensuite.

*Procédure (LibreOffice fermé) :*

```bash
./tool_migrate_schema_v2.py ~/Compta/comptes.xlsm
```

Application de la charte v4 :

```bash
./tool_fix_formats.py ~/Compta/comptes.xlsm --charter --apply
./tool_audit_formats.py ~/Compta/comptes.xlsm    # 0 violation attendu
```


## v3.5.8 🔧 — Alarmes balances 

Pour un classeur passant directement à v4, ce fix est inclus dans `tool_migrate_schema_v2.py`. L'outil `tool_migrate_ctrl2_balances.py` n'est plus livré en v4. Section conservée pour mémoire.

Pour un classeur restant en v3.5.x :

| Mode classeur | Mode assisté |
| --- | --- |
| Comparer les formules h+7..h+10 et L(h+2,h+3,h+8,h+10) à `comptes_exemple.xlsx`. | `tool_migrate_ctrl2_balances.py`. |

```bash
./tool_migrate_ctrl2_balances.py ~/Compta/comptes.xlsm --dry-run
./tool_migrate_ctrl2_balances.py ~/Compta/comptes.xlsm
```


## v3.5.7 📘 🔧 — Plus-value : ancrage dynamique sur `#Solde`

Concerne les sections **métaux / crypto / devises** de `Plus_value` et les colonnes *AVRdate_anter* / *AVRmontant_anter* d'`Avoirs`.

| Mode classeur | Mode assisté |
| --- | --- |
| Comparer les formules à `comptes_exemple.xlsx` (Plus_value sections non-portefeuille, colonnes H/I d'Avoirs). | `tool_migrate_pvl_ancrage.py` (préserve les saisies manuelles). |

```bash
cd ~/Compta
git pull
./tool_migrate_pvl_ancrage.py comptes.xlsm
```

L'option `--dry-run` simule sans sauvegarder.


## v3.5.6 📘 — Pieds Budget en plage auto-extensible 

Nécessaire uniquement si le classeur a été initialisé avec un modèle ≤ v3.5.5 **et** que des catégories / postes ont été ajoutés directement dans le tableur sans passer par la GUI.

| Mode classeur | Mode assisté |
| --- | --- |
| Comparer les formules du pied Budget à `comptes_exemple.xlsx` (feuille `Budget` : *Total hors Changes/Virements*, *Total épargne*, *Épargne fixe*). | Rien à faire — réécriture au prochain ajout via GUI. |


## v3.5.4 🔧 — Outil de migration CTRL2 multi-devise

Cet outil applique le fix annoncé en v3.5.2 — voir §v3.5.2 pour la procédure (`tool_migrate_ctrl2_formulas.py`).


## v3.5.3 📘 🔧 — Formules PVL multi-devise génériques 

Concerne le pied `TOTAL portefeuilles` et le `Total` des blocs portefeuille multi-devise de `Plus_value`.

| Mode classeur | Mode assisté |
| --- | --- |
| Comparer les formules à `comptes_exemple.xlsx` (feuille `Plus_value` : pied *TOTAL portefeuilles* et ligne *Total* des blocs portefeuille multi-devise). | `tool_migrate_pvl_totals.py`. |

```bash
./tool_migrate_pvl_totals.py ~/Compta/comptes.xlsm --dry-run
./tool_migrate_pvl_totals.py ~/Compta/comptes.xlsm
```

Sortie sans ligne `Δ` = migration transparente (aucun écart de valeur).


## v3.5.2 📘 — Détection d'erreur Comptes multi-devises

Pour un classeur passant directement à v4, ce fix est inclus dans `tool_migrate_schema_v2.py`. L'outil `tool_migrate_ctrl2_formulas.py` n'est plus livré en v4. Section conservée pour mémoire.

Pour un classeur restant en v3.5.x avec au moins un compte non-EUR :

| Mode classeur | Mode assisté |
| --- | --- |
| Comparer les formules CTRL2 *Affichage* / *Général* à `comptes_exemple.xlsx`. | `tool_migrate_ctrl2_formulas.py`. |

```bash
./tool_migrate_ctrl2_formulas.py ~/Compta/comptes.xlsm --dry-run
./tool_migrate_ctrl2_formulas.py ~/Compta/comptes.xlsm
```


## v3.2.0 — `SCHEMA_VERSION 1`

Première version avec schéma classeur versionné (named ranges colonnes + named range `SCHEMA_VERSION` = 1).

**Depuis un classeur sans version (antérieur à app v3.2) :**

Le classeur ne contient pas les named ranges nécessaires à l'application.

```bash
# Sauvegarder
cp comptes.xlsm comptes_backup.xlsm

# Recréer depuis le template à jour
cp comptes_template.xlsm comptes.xlsm
```

Relancer l'app après la copie. Le nouveau classeur est vierge ; réimporter les données via l'application (collecte + import) ou par copier-coller depuis le backup.
