# Mise à niveau du classeur

Ce document décrit la **procédure** à suivre pour mettre à niveau le
classeur `comptes.xlsm` entre versions d'app. Pour la **liste des
changements** apportés par chaque version, voir `CHANGELOG.md`.

**Rappel** — [modes d'utilisation](README.md#1-points-de-départ)

| Mode classeur | Mode assisté |
| --- | --- |
| Seul `comptes.xlsm` est utilisé ; mise à niveau manuelle dans le tableur en s'appuyant sur [`comptes_exemple.xlsx`](https://github.com/mlebas29/Compta/raw/main/comptes_exemple.xlsx) comme référence. | Classeur + app + outils installés via `git clone` ; mise à niveau par l'app, par un outil `tool_migrate_*.py`, ou manuelle. |

Au démarrage (mode assisté), l'app vérifie la `SCHEMA_VERSION` du
classeur ; une incompatibilité bloque l'exécution. Les autres mises à
niveau (formules, formats) sont optionnelles à recommandées — elles
n'empêchent pas l'app de tourner mais peuvent fausser des calculs.



## v4.0.0 — Refonte drill devise + charte v4 (requis)

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
python3 tool_migrate_schema_v2.py ~/Compta/comptes.xlsm
```

Application de la charte v4 :

```bash
python3 tool_fix_formats.py ~/Compta/comptes.xlsm --charter --apply
python3 tool_audit_formats.py ~/Compta/comptes.xlsm    # 0 violation attendu
```


## v3.5.8 — Contrôle 2 balances *(intégré dans v4)*

Pour un classeur passant directement à v4, ce fix est inclus dans
`tool_migrate_schema_v2.py`. L'outil `tool_migrate_ctrl2_balances.py`
n'est plus livré en v4. Section conservée pour mémoire.

Pour un classeur restant en v3.5.x :

| Mode classeur | Mode assisté |
| --- | --- |
| Comparer les formules h+7..h+10 et L(h+2,h+3,h+8,h+10) à `comptes_exemple.xlsx`. | `tool_migrate_ctrl2_balances.py`. |

```bash
python3 tool_migrate_ctrl2_balances.py ~/Compta/comptes.xlsm --dry-run
python3 tool_migrate_ctrl2_balances.py ~/Compta/comptes.xlsm
```


## v3.5.7 — Plus-value : ancrage dynamique sur `#Solde` (recommandé)

Concerne les sections **métaux / crypto / devises** de `Plus_value` et les
colonnes *AVRdate_anter* / *AVRmontant_anter* d'`Avoirs`.

| Mode classeur | Mode assisté |
| --- | --- |
| Comparer les formules à `comptes_exemple.xlsx` (Plus_value sections non-portefeuille, colonnes H/I d'Avoirs). | `tool_migrate_pvl_ancrage.py` (préserve les saisies manuelles). |

```bash
cd ~/Compta
git pull
python3 Claude/tool_migrate_pvl_ancrage.py comptes.xlsm
```

L'option `--dry-run` simule sans sauvegarder.


## v3.5.6 — Pieds Budget en plage auto-extensible (cosmétique)

Nécessaire uniquement si le classeur a été initialisé avec un modèle ≤
v3.5.5 **et** que des catégories / postes ont été ajoutés directement dans
le tableur sans passer par la GUI.

| Mode classeur | Mode assisté |
| --- | --- |
| Comparer les formules de pied Budget à `comptes_exemple.xlsx`. | Une mise à jour de l'app suffit (réécriture au prochain ajout via GUI). |


## v3.5.3 — Formules PVL multi-devise génériques (optionnel)

Concerne le pied `TOTAL portefeuilles` et le `Total` des blocs portefeuille
multi-devise de `Plus_value`.

| Mode classeur | Mode assisté |
| --- | --- |
| Comparer les formules à `comptes_exemple.xlsx`. | `tool_migrate_pvl_totals.py`. |

```bash
python3 tool_migrate_pvl_totals.py ~/Compta/comptes.xlsm --dry-run
python3 tool_migrate_pvl_totals.py ~/Compta/comptes.xlsm
```

Sortie sans ligne `Δ` = migration transparente (aucun écart de valeur).


## v3.5.2 — Détection d'erreur Comptes multi-devises *(intégré dans v4)*

Pour un classeur passant directement à v4, ce fix est inclus dans
`tool_migrate_schema_v2.py`. L'outil `tool_migrate_ctrl2_formulas.py`
n'est plus livré en v4. Section conservée pour mémoire.

Pour un classeur restant en v3.5.x avec au moins un compte non-EUR :

| Mode classeur | Mode assisté |
| --- | --- |
| Comparer les formules CTRL2 *Affichage* / *Général* à `comptes_exemple.xlsx`. | `tool_migrate_ctrl2_formulas.py`. |

```bash
python3 tool_migrate_ctrl2_formulas.py ~/Compta/comptes.xlsm --dry-run
python3 tool_migrate_ctrl2_formulas.py ~/Compta/comptes.xlsm
```


## v3.2 — `SCHEMA_VERSION 1`

Première version avec schéma versionné (named ranges colonnes + named range
`SCHEMA_VERSION` = 1).

**Depuis un classeur sans version (antérieur à app v3.2) :**

Le classeur ne contient pas les named ranges nécessaires à l'application.

```bash
# Sauvegarder
cp comptes.xlsm comptes_backup.xlsm

# Recréer depuis le template à jour
cp comptes_template.xlsm comptes.xlsm
```

Relancer l'app après la copie. Le nouveau classeur est vierge ; réimporter
les données via l'application (collecte + import) ou par copier-coller
depuis le backup.
