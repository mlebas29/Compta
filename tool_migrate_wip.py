#!/usr/bin/env python3
"""Migrations xls en cours d'élaboration (WIP), pour la prochaine release.

Script intégrateur : chaque nouvelle migration vient s'ajouter ici en
préparation du tag. Au moment de la release, ce fichier est renommé en
`tool_migrate_v<X>.<Y>.<Z>.py` et figé tel quel — c'est l'outil unique
livré à l'utilisateur (cf. convention Compta_upgrade.md « 1 outil par
version »).

Sections actuellement intégrées :

1. Alarme Patrimoine + CTRL2 'DIVERS'
   Pose dans le classeur cible (positions identifiées dynamiquement) :
   - Patrimoine!B{r}  = "Erreurs"   où r = dernier TOTAL + 2 (ligne pied)
   - Patrimoine!D{r}  = compteur de ventilations en écart > 0.5 EUR
                       (entier 0..5, en gras)
   - Contrôles : ligne 'Date' renommée 'DIVERS' (identifiée via NR
     CTRL2type ; variantes legacy 'Cohérence'/'Divers' reconnues),
     formule de la colonne 'Général' (CTRL2general) étendue avec
     +Patrimoine.D{r}.
   CF rouge sur D{r} (warning si ≠ 0) : à poser à la main dans LibreOffice.

2. Ligne CONV 'DIVERS' (label réservé)
   Insertion d'une row dans le tableau CONV (Patrimoine, NRs CONVnom/cell/
   légende) juste après la ligne K=='COMPTES', avec K=DIVERS /
   L='Tableau 2 feuille Contrôles'. UNO étend automatiquement les 3 NRs
   couvrant la zone. Idempotence étendue : si une variante legacy
   ('Cohérence'/'Divers') existe déjà, on la renomme en 'DIVERS' (au lieu
   de re-insérer), corrigeant l'écart entre CONV et le label tab2.
   Convention : la chirurgie structurelle (insertion row + redim NR) reste
   de la responsabilité de cette migration ; tool_sync_from_witness
   propage ensuite le contenu statique sur dimensions alignées.

3. Alarmes formules sur synthèses + alarme métier Cotations
   Pose des cellules d'alarme :
   - Plus_value!B3   = ✗/✓ via ISERROR sur GRAND TOTAL pied (E + K).
                       Détecte une rupture de calcul (#N/A, #REF!, …) sur
                       la synthèse PVL.
   - Avoirs!L1       = ✗/✓ via ISERROR sur Total pied (L{Total}).
                       Détecte une rupture de calcul sur synthèse Avoirs.
   - Cotations!B20   = ⚠/✓ alarme métier "completeness" :
                       (a) devises utilisées (PVL/AVR) absentes de COTcode
                       (b) codes COTcode présents mais cours vide
   Note : pas de patch NA() sur les SUMPRODUCT PVL (essai initial → revert).
   IFERROR(...; 1) reste : NA() polluerait cross-section dans SUMPRODUCT.

4. Refonte Contrôles K65 → 'DIVERS' + sous-lignes
   Bascule du check monolithique date+Patrimoine vers pattern Balances :
   - J{r65} renommé : ('Date' | 'Cohérence' | 'Divers') → 'DIVERS'
   - Insertion 3 sous-lignes (Date hors période / Ventilation Patrimoine
     / Cotations) — chacune token ⚠/✓
   - K{r65} (Affichage) en agrégateur : priorité ✗ > ⚠ > ✓ sur sous-lignes
   - L{r65} (Général) = compteur sous-lignes alarme
   La sous-ligne 'Cotations' pointe sur l'alarme métier Cotations!B20
   (Section 3). UNO étend automatiquement les NRs CTRL2*.

5. Insertion ligne 'FORMULES' + sous-lignes Avoirs / Plus_value
   Nouveau header juste avant ⚓ basse :
   - J{rN} = 'FORMULES' (header ; variante legacy 'Formules' reconnue)
   - 2 sous-lignes indentées : 'Avoirs' (count si L1=✗), 'Plus_value' (count si B3=✗)
   - K{rN} en agrégateur SUM (niveau ✗ direct)
   Mise à jour formule Synthèse (K{rSynth}) pour 7 tokens (au lieu de 6).

6. Indentation des sous-lignes Balances existantes
   Préfixe 4 espaces sur 'Virements €' / 'Titres €' / 'Changes Eq €' /
   'Total €' pour cohérence visuelle avec les sous-lignes Divers et
   Formules (pattern uniforme : sous-ligne = J indenté, K vide, L = valeur).

7. Restriction des plages CF d'alarme étendues (CTRL2)
   Les insertions des Sections 4 et 5 ont fait étendre par UNO les CF des
   cellules headers (K65 → K65:K68 pour DIVERS, K75 → K75:K78 pour INCONNUS+
   FORMULES) aux sous-lignes K vides. L'expression CF `FIND("✗"|"⚠"; RC)`
   se déclenche par effet de bord sur les sous-lignes voisines quand le
   header s'allume. Solution : fissionner ces ranges multi-row pour ne
   conserver la CF que sur les rows headers (J non-vide non-indenté).

8. Auto-pose CF d'alarme sur Plus_value!B3, Avoirs!L1, Cotations!B20
   Les 3 cellules d'alarme posées par la Section 3 retournent ✗/✓ ou ⚠/✓
   (formule métier) mais n'avaient pas de CF associée — convention "à la
   main" héritée du commit d628e492. Cette section pose les 2 conditions
   FIND("✗") / FIND("⚠") avec les styles ConditionalStyle_2/3 existants.

9. Pieds globaux Plus_value H/I/K en NR-driven (#46 partiel)
   Pieds 'TOTAL métaux/crypto-monnaies/devises' : remplace
   `=SUMIFS(K:K, A:A, "X")` (col absolus) par `=SUMIFS(<NR>, PVLsection, "X")`
   sur H (PVLmontant_init), I (PVLsigma), K (PVLmontant) — layout-agnostic.
   Note : sous-totaux 'Total' par portefeuille **non migrés** — leurs refs
   absolues (K8:K12, etc.) restent en place faute d'une formule NR-driven
   sans cycle ni perte de conversion devise (Yuh). À reprendre ultérieurement.

10. Bump SCHEMA_VERSION 2 → 3
   Le named range constante SCHEMA_VERSION du classeur passe de '2' à '3'
   pour refléter la refonte CTRL2 (insertions rows + nouvelles cellules).
   Sans ce bump, l'app détecte un mismatch au démarrage et bloque
   (cf. inc_excel_schema.SCHEMA_VERSION = 3 et cpt_gui._check_schema_version).

Idempotent : si déjà migré, ne fait rien.

Usage:
    python3 tool_migrate_wip.py ~/Compta/comptes.xlsm
    python3 tool_migrate_wip.py ~/Compta/comptes.xlsm --dry-run
"""
import argparse
import sys
from pathlib import Path

from inc_uno import (
    UnoDocument, check_lock_file,
    has_alarm_cf, set_alarm_cf,
)
from inc_excel_schema import uno_row


# Position cible Patrimoine : pied = PATlabel_end + 1 (juste après ⚓ basse).
# Trouvée dynamiquement via NR (layout-agnostic).
PAT_LABEL_COL_0 = 1   # B
PAT_FORMULA_COL_0 = 3  # D
PAT_LABEL = 'Erreurs'
PAT_TOLERANCE = 0.5  # EUR, seuil d'arrondi pour considérer un écart de ventilation

CTRL2_OLD_LABEL = 'Date'           # label v3.x (avant migration)
CTRL2_NEW_LABEL = 'DIVERS'         # label cible v4.1 (MAJUSCULES)
# Variantes intermédiaires reconnues pour idempotence sur classeurs partiellement migrés
CTRL2_VARIANT_LABELS = ('Cohérence', 'Divers')
# Idem pour Section 5 (FORMULES)
CTRL2_FORMULES_LABEL = 'FORMULES'
CTRL2_FORMULES_VARIANTS = ('Formules',)
# Référence Patrimoine.D{target_row} construite dynamiquement (syntaxe UNO : point)

BOLD = 150


# Helpers CF (set_alarm_cf, has_alarm_cf) déplacés dans inc_uno.py — partagés
# avec tool_fix_formats / tool_audit_formats (#53).


# ━━━ Section 3 helpers ━━━

def _find_row_by_label(ws, label, col_0=0, max_row=300):
    """Trouve la 1ère row 1-indexed dont la cellule en col_0 == label."""
    for r in range(1, max_row + 1):
        v = ws.getCellByPosition(col_0, uno_row(r)).getString().strip()
        if v == label:
            return r
    return None


def _section3_plus_value(ws_pvl, dry_run, changes):
    """Pose Plus_value!B3 = alarme formule sur la synthèse GRAND TOTAL.

    Surveille E (PVL) et K (PVLmontant) du GRAND TOTAL — si l'une des deux
    est en erreur (#N/A, #REF!, #DIV/0!, #VALUE!…), c'est qu'une formule
    en amont a planté. Référence le pied (cellule réelle de calcul), pas
    la recopie tête. ISERROR = catch-all (vs ISNA seulement #N/A).
    """
    gt_row = _find_row_by_label(ws_pvl, 'GRAND TOTAL', col_0=0)
    if gt_row is None:
        return  # Pas de GRAND TOTAL : feuille vide, pas d'alarme à poser
    b3_formula = f'=IF(OR(ISERROR(E{gt_row});ISERROR(K{gt_row}));"✗";"✓")'
    b3 = ws_pvl.getCellByPosition(1, uno_row(3))  # B3
    if b3.getFormula() != b3_formula:
        if not dry_run:
            b3.setFormula(b3_formula)
        changes.append(
            f"+ Plus_value!B3 = alarme formule (ISERROR E{gt_row}/K{gt_row} GRAND TOTAL)")


def _section3_avoirs(ws_avr, dry_run, changes):
    """Pose Avoirs!L1 = alarme formule sur la synthèse Total Avoirs.

    Surveille L{Total} (= ROUND(SUM(AVRmontant_solde_euro),2)) — pied réel.
    Référence le pied, pas la recopie L2.
    Posé en L1 (col du montant, dans le tableau) plutôt que M2 (hors tableau).
    ISERROR = catch-all (#N/A, #REF!, #DIV/0!, #VALUE!…).
    """
    total_row = _find_row_by_label(ws_avr, 'Total', col_0=0)
    if total_row is None:
        return
    l1_formula = f'=IF(ISERROR(L{total_row});"✗";"✓")'
    l1 = ws_avr.getCellByPosition(11, uno_row(1))  # L1 (col 11 0-based)
    if l1.getFormula() != l1_formula:
        if not dry_run:
            l1.setFormula(l1_formula)
        changes.append(
            f"+ Avoirs!L1 = alarme formule (ISERROR L{total_row} Total pied)")
    # Nettoyer M2 si héritage migration précédente (cell hors tableau)
    m2 = ws_avr.getCellByPosition(12, uno_row(2))  # M2
    f_m2 = m2.getFormula()
    if f_m2.startswith('=IF(ISNA(L') or f_m2.startswith('=IF(ISERROR(L'):
        if not dry_run:
            m2.setString('')  # vide
        changes.append("~ Avoirs!M2 nettoyée (héritage migration précédente)")


# ━━━ Sections 4 & 5 helpers ━━━

CTRL2_TYPE_COL = 9     # J
CTRL2_DISPL_COL = 10   # K (Affichage — header uniquement, vide pour sous-lignes)
CTRL2_GEN_COL = 11     # L (Général — valeur numérique des sous-lignes)
CTRL2_EUR_COL = 12     # M (EUR)
CTRL2_INDENT = '    '  # 4 espaces : indentation des sous-lignes (pattern Balances)


def _ctrl2_find_row(ws_ctrl, cr, label):
    """Trouve la 1ère row du bloc CTRL2 dont J == label (ou commence par label).

    Bornes lues dynamiquement via NR CTRL2type (layout-agnostic) ; fallback
    sur scan large (1..200) si NR absent.
    """
    try:
        s, e = cr.rows('CTRL2type')
    except Exception:
        s, e = 1, 200
    # Étendre légèrement pour capter les rows juste avant/après le NR
    # (header CONTRÔLES, sentinelles ⚓, ligne Synthèse).
    for r in range(max(1, s - 2), e + 5):
        v = ws_ctrl.getCellByPosition(CTRL2_TYPE_COL, uno_row(r)).getString().strip()
        if v == label or v.startswith(label):
            return r
    return None


def _section4_divers(ws_ctrl, ws_pat, cr, dry_run, changes):
    """Refonte K65 : renommage → DIVERS + 3 sous-lignes en pattern Balances.

    Idempotent : si une sous-ligne 'Date hors période' existe déjà juste
    après K65, on ne refait rien. Reconnaît variantes legacy 'Date'
    (v3.x), 'Cohérence' (migration partielle), 'Divers' (Title case).
    """
    # Localiser le header (DIVERS, ou variante legacy)
    target_row = None
    for label in (CTRL2_NEW_LABEL, *CTRL2_VARIANT_LABELS, CTRL2_OLD_LABEL):
        target_row = _ctrl2_find_row(ws_ctrl, cr, label)
        if target_row is not None:
            break
    if target_row is None:
        print(f"⚠ Section 4 : ligne {CTRL2_NEW_LABEL}/variantes/Date introuvable — skip")
        return

    # Idempotence
    next_label = ws_ctrl.getCellByPosition(
        CTRL2_TYPE_COL, uno_row(target_row + 1)).getString().strip()
    if next_label == 'Date hors période':
        return  # Déjà migré

    # Localiser Patrimoine D{r} (compteur écarts ventilation)
    pat_d_row = None
    for r in range(2, 200):
        v = ws_pat.getCellByPosition(1, uno_row(r)).getString().strip()  # col B
        if v == 'Erreurs':
            pat_d_row = r
            break

    # Renommer J{target_row} en 'DIVERS'
    j_cell = ws_ctrl.getCellByPosition(CTRL2_TYPE_COL, uno_row(target_row))
    if j_cell.getString().strip() != CTRL2_NEW_LABEL:
        old = j_cell.getString().strip()
        if not dry_run:
            j_cell.setString(CTRL2_NEW_LABEL)
        changes.append(f"~ Contrôles!J{target_row} : '{old}' → '{CTRL2_NEW_LABEL}'")

    # Insertion 3 rows juste après target_row
    if not dry_run:
        ws_ctrl.Rows.insertByIndex(uno_row(target_row + 1), 3)

    r_date = target_row + 1
    r_pat = target_row + 2
    r_cot = target_row + 3

    # Sous-lignes : J indenté, K vide, L = count numérique (agrégeable par SUM).

    # Date hors période — count direct.
    # Borne haute via NR `année_courante` (dynamique, suit l'année en cours)
    # plutôt qu'un DATE hardcodé.
    date_l = (
        '=COUNTIF(OPdate;"<"&DATE(2020;1;1))'
        '+COUNTIF(OPdate;">"&DATE(année_courante;12;31))'
    )
    if not dry_run:
        ws_ctrl.getCellByPosition(CTRL2_TYPE_COL, uno_row(r_date)).setString(
            CTRL2_INDENT + 'Date hors période')
        ws_ctrl.getCellByPosition(CTRL2_DISPL_COL, uno_row(r_date)).setString('')
        ws_ctrl.getCellByPosition(CTRL2_GEN_COL, uno_row(r_date)).setFormula(date_l)
    changes.append(f"+ Contrôles row {r_date} : sous-ligne 'Date hors période'")

    # Ventilation Patrimoine — pointeur Patrimoine.D{r} (déjà numérique)
    if pat_d_row:
        pat_l = f'=Patrimoine.D{pat_d_row}'
    else:
        pat_l = '0'
        print("⚠ Section 4 : Patrimoine 'Erreurs' D{r} introuvable, sous-ligne posée à 0")
    if not dry_run:
        ws_ctrl.getCellByPosition(CTRL2_TYPE_COL, uno_row(r_pat)).setString(
            CTRL2_INDENT + 'Ventilation Patrimoine')
        ws_ctrl.getCellByPosition(CTRL2_DISPL_COL, uno_row(r_pat)).setString('')
        ws_ctrl.getCellByPosition(CTRL2_GEN_COL, uno_row(r_pat)).setFormula(pat_l)
    changes.append(f"+ Contrôles row {r_pat} : sous-ligne 'Ventilation Patrimoine'")

    # Cotations — Cotations.B20 retourne token, transformer en count (1 si ⚠)
    cot_l = '=IF(Cotations.B20="⚠";1;0)'
    if not dry_run:
        ws_ctrl.getCellByPosition(CTRL2_TYPE_COL, uno_row(r_cot)).setString(
            CTRL2_INDENT + 'Cotations')
        ws_ctrl.getCellByPosition(CTRL2_DISPL_COL, uno_row(r_cot)).setString('')
        ws_ctrl.getCellByPosition(CTRL2_GEN_COL, uno_row(r_cot)).setFormula(cot_l)
    changes.append(f"+ Contrôles row {r_cot} : sous-ligne 'Cotations'")

    # Header K{target_row} (DIVERS) — pattern Balances : K dépend de L (qui agrège).
    # Niveau ⚠ uniquement (pas de ✗ : aucune sous-ligne DIVERS ne propage ✗).
    divers_k = f'=IF(L{target_row}>0;"⚠";"✓")'
    divers_l = f'=SUM(L{r_date}:L{r_cot})'
    if not dry_run:
        ws_ctrl.getCellByPosition(CTRL2_DISPL_COL, uno_row(target_row)).setFormula(divers_k)
        ws_ctrl.getCellByPosition(CTRL2_GEN_COL, uno_row(target_row)).setFormula(divers_l)
    changes.append(f"~ Contrôles K{target_row}/L{target_row} : DIVERS en agrégateur pattern Balances")


def _section5_formules(ws_ctrl, cr, dry_run, changes):
    """Insère ligne 'FORMULES' juste après INCONNUS + 2 sous-lignes (PVL/AVR).

    Idempotent : si 'FORMULES' (ou variante legacy 'Formules') existe déjà
    juste après INCONNUS, skip — et renomme la variante en MAJ si trouvée.
    """
    inconnus_row = _ctrl2_find_row(ws_ctrl, cr, 'INCONNUS')
    if inconnus_row is None:
        print("⚠ Section 5 : ligne INCONNUS introuvable — skip")
        return

    # Idempotence : reconnaître la cible et toutes les variantes legacy
    next_label = ws_ctrl.getCellByPosition(
        CTRL2_TYPE_COL, uno_row(inconnus_row + 1)).getString().strip()
    if next_label == CTRL2_FORMULES_LABEL:
        return
    if next_label in CTRL2_FORMULES_VARIANTS:
        # Migration partielle : renommer le header en MAJ et continuer (la suite
        # est idempotente sur les sous-lignes/formules, qui ne dépendent pas de la casse).
        cell = ws_ctrl.getCellByPosition(CTRL2_TYPE_COL, uno_row(inconnus_row + 1))
        if not dry_run:
            cell.setString(CTRL2_FORMULES_LABEL)
        changes.append(
            f"~ Contrôles!J{inconnus_row + 1} : '{next_label}' → '{CTRL2_FORMULES_LABEL}'")
        return

    # Vérification layout : ⚓ attendu juste après INCONNUS
    if next_label != '⚓':
        print(f"⚠ Section 5 : layout inattendu après INCONNUS row {inconnus_row} "
              f"(trouvé '{next_label}', attendu '⚓') — skip")
        return

    # Insertion 3 rows juste après INCONNUS (avant ⚓)
    if not dry_run:
        ws_ctrl.Rows.insertByIndex(uno_row(inconnus_row + 1), 3)

    r_form = inconnus_row + 1
    r_avr = inconnus_row + 2   # Avoirs en premier (ordre alphabétique)
    r_pvl = inconnus_row + 3   # Plus_value en second

    # Sous-lignes : J indenté + nom complet feuille, K vide, L = count (1 si ✗)

    # Avoirs (alphabétique en premier)
    if not dry_run:
        ws_ctrl.getCellByPosition(CTRL2_TYPE_COL, uno_row(r_avr)).setString(
            CTRL2_INDENT + 'Avoirs')
        ws_ctrl.getCellByPosition(CTRL2_DISPL_COL, uno_row(r_avr)).setString('')
        ws_ctrl.getCellByPosition(CTRL2_GEN_COL, uno_row(r_avr)).setFormula(
            '=IF(Avoirs.L1="✗";1;0)')
    changes.append(f"+ Contrôles row {r_avr} : sous-ligne 'Avoirs'")

    # Plus_value
    if not dry_run:
        ws_ctrl.getCellByPosition(CTRL2_TYPE_COL, uno_row(r_pvl)).setString(
            CTRL2_INDENT + 'Plus_value')
        ws_ctrl.getCellByPosition(CTRL2_DISPL_COL, uno_row(r_pvl)).setString('')
        ws_ctrl.getCellByPosition(CTRL2_GEN_COL, uno_row(r_pvl)).setFormula(
            '=IF(Plus_value.B3="✗";1;0)')
    changes.append(f"+ Contrôles row {r_pvl} : sous-ligne 'Plus_value'")

    # Header FORMULES — K dépend de L (qui agrège). Niveau ✗ (B3/L1 retournent ✗).
    formules_k = f'=IF(L{r_form}>0;"✗";"✓")'
    formules_l = f'=SUM(L{r_avr}:L{r_pvl})'
    if not dry_run:
        ws_ctrl.getCellByPosition(CTRL2_TYPE_COL, uno_row(r_form)).setString(CTRL2_FORMULES_LABEL)
        ws_ctrl.getCellByPosition(CTRL2_DISPL_COL, uno_row(r_form)).setFormula(formules_k)
        ws_ctrl.getCellByPosition(CTRL2_GEN_COL, uno_row(r_form)).setFormula(formules_l)
    changes.append(f"+ Contrôles row {r_form} : header '{CTRL2_FORMULES_LABEL}' (agrégateur Avoirs+Plus_value)")


def _section_bump_schema_version(doc, dry_run, changes, target_version='3'):
    """Bump le named range SCHEMA_VERSION du classeur (constante).

    Idempotent : skip si déjà à la version cible.
    """
    import uno
    nr = doc.document.NamedRanges
    if not nr.hasByName('SCHEMA_VERSION'):
        print("⚠ SCHEMA_VERSION absent — skip bump (classeur trop ancien ?)")
        return
    cur = nr.getByName('SCHEMA_VERSION').Content
    if cur == target_version:
        return
    if not dry_run:
        nr.removeByName('SCHEMA_VERSION')
        pos = uno.createUnoStruct('com.sun.star.table.CellAddress')
        pos.Sheet = 0
        pos.Column = 0
        pos.Row = 0
        nr.addNewByName('SCHEMA_VERSION', target_version, pos, 0)
    changes.append(f"~ SCHEMA_VERSION : {cur} → {target_version}")


def _section_fix_headers_k_simple_ref(ws_ctrl, cr, dry_run, changes):
    """Corrige les K headers DIVERS/FORMULES pour référencer L au lieu de SUM(L:L).

    Idempotent. Si la formule contient SUM(...), la remplace par IF(L{r}>0,...).
    Bug : SUM(L:L) dans IF empêche LO de propager le recalcul correctement —
    K reste à "✓" alors que L bascule à >0.
    """
    for header_label, alarm_token in ((CTRL2_NEW_LABEL, '⚠'), (CTRL2_FORMULES_LABEL, '✗')):
        target_row = _ctrl2_find_row(ws_ctrl, cr, header_label)
        if target_row is None:
            continue
        cell = ws_ctrl.getCellByPosition(CTRL2_DISPL_COL, uno_row(target_row))
        f = cell.getFormula()
        if 'SUM(L' not in f or 'IF(SUM' not in f:
            continue
        new_f = f'=IF(L{target_row}>0;"{alarm_token}";"✓")'
        if not dry_run:
            cell.setFormula(new_f)
        changes.append(
            f"~ Contrôles!K{target_row} ({header_label}) : SUM en double → IF(L{target_row}>0…)")


def _section_fix_date_formula(ws_ctrl, cr, dry_run, changes):
    """Corrige la formule L de la sous-ligne Date hors période existante.

    Idempotent. Si la formule contient DATE(2030,1,1) (premier jet hardcodé),
    la remplace par DATE(année_courante,12,31) pour suivre dynamiquement
    l'année courante. Aucune action sinon.
    """
    target_row = _ctrl2_find_row(ws_ctrl, cr, 'Date hors période')
    if target_row is None:
        return
    cell = ws_ctrl.getCellByPosition(CTRL2_GEN_COL, uno_row(target_row))
    f = cell.getFormula()
    if 'DATE(2030' not in f and 'DATE(2030,1,1)' not in f and 'DATE(2030;1;1)' not in f:
        return
    new_f = (
        '=COUNTIF(OPdate;"<"&DATE(2020;1;1))'
        '+COUNTIF(OPdate;">"&DATE(année_courante;12;31))'
    )
    if not dry_run:
        cell.setFormula(new_f)
    changes.append(
        f"~ Contrôles!L{target_row} : DATE(2030,…) → DATE(année_courante,12,31)")


def _section6_indent_balances(ws_ctrl, cr, dry_run, changes):
    """Indenter les libellés des 4 sous-lignes Balances existantes.

    Cohérence visuelle avec les nouvelles sous-lignes Divers et Formules.
    """
    for label in ('Virements €', 'Titres €', 'Changes Eq €', 'Total €'):
        r = _ctrl2_find_row(ws_ctrl, cr, label)
        if r is None:
            continue
        cell = ws_ctrl.getCellByPosition(CTRL2_TYPE_COL, uno_row(r))
        cur = cell.getString()
        if cur.startswith(CTRL2_INDENT):
            continue  # déjà indenté
        new = CTRL2_INDENT + cur.lstrip()
        if not dry_run:
            cell.setString(new)
        changes.append(f"~ Contrôles!J{r} : '{cur.strip()}' indenté")


def _section_uppercase_legacy_headers(ws_ctrl, cr, dry_run, changes):
    """Renomme en MAJUSCULES les headers CTRL2 restés en Title case.

    Le chantier MAJUSCULES de v4.1.0 (Sections 4/5) gère DIVERS et FORMULES.
    Les autres headers (COMPTES, CATÉGORIES, INCONNUS) ont leur libellé MAJ
    posé à la main dans le témoin. Mais APPARIEMENTS et BALANCES, présents
    historiquement, peuvent rester en Title case ('Appariements', 'Balances')
    sur les classeurs migrés. Cette section les normalise.

    Retire aussi les espaces insécables \\xa0 et tabulations parasites
    hérités de saisies par copier-coller.

    Idempotent : skip si déjà en MAJUSCULES.
    """
    legacy_map = {
        'appariements': 'APPARIEMENTS',
        'balances': 'BALANCES',
    }
    try:
        s, e = cr.rows('CTRL2type')
    except Exception:
        s, e = 1, 200
    for r in range(max(1, s - 2), e + 5):
        cell = ws_ctrl.getCellByPosition(CTRL2_TYPE_COL, uno_row(r))
        v = cell.getString()
        v_clean = v.strip(' \xa0\t')
        cible = legacy_map.get(v_clean.lower())
        if cible is None or v == cible:
            continue
        if not dry_run:
            cell.setString(cible)
        changes.append(f"~ Contrôles!J{r} : {v_clean!r} → '{cible}'")


def _section7_fix_alarm_cf_ranges(ws_ctrl, dry_run, changes):
    """Restreint les plages CF d'alarme étendues aux cellules headers seules.

    Sections 4 et 5 ont inséré des sous-lignes après les headers DIVERS et
    INCONNUS/FORMULES, ce qui a fait étendre par UNO les CF des cellules
    parentes vers ces nouvelles rows :
      K65 → K65:K68 (DIVERS + 3 sous-lignes K vides)
      K75 → K75:K78 (INCONNUS + FORMULES + 2 sous-lignes K vides)
    L'expression `FIND("✗"|"⚠"; RC)` se déclenche par effet de bord sur les
    sous-lignes voisines quand le header s'allume.

    Approche : pour chaque CF couvrant un range col K multi-row, identifier
    les rows headers (J non-vide non-indenté) ; si la plage mélange headers
    et sous-lignes, supprimer la CF étendue et recréer cellule par cellule
    sur les seuls headers.

    Idempotent : ne touche que les ranges multi-row mixtes (header + sous-ligne).
    """
    import re as _re
    cfs = ws_ctrl.ConditionalFormats

    for cf in list(cfs.ConditionalFormats):
        addr = cf.Range.getRangeAddressesAsString()
        m = _re.match(r"^[^.]+\.K(\d+):K(\d+)$", addr)
        if not m:
            continue
        row_s, row_e = int(m.group(1)), int(m.group(2))
        if row_s == row_e:
            continue  # déjà single cell

        # Identifier les rows headers (J non-vide, non-indenté, non-⚓)
        header_rows = []
        for r in range(row_s, row_e + 1):
            v = ws_ctrl.getCellByPosition(CTRL2_TYPE_COL, uno_row(r)).getString()
            if v and not v.startswith(' ') and v.strip() != '⚓':
                header_rows.append(r)

        # Skip si pas de header ou que des headers (range homogène, pas concerné)
        if not header_rows or len(header_rows) == (row_e - row_s + 1):
            continue

        cf_id = cf.ID
        if not dry_run:
            cfs.removeByID(cf_id)
            for r in header_rows:
                cell = ws_ctrl.getCellByPosition(CTRL2_DISPL_COL, uno_row(r))
                set_alarm_cf(cell)
        rows_str = ','.join(f'K{r}' for r in header_rows)
        changes.append(f"~ Contrôles CF K{row_s}:K{row_e} → fissionnée sur {rows_str}")


def _section8_alarm_cf_three_cells(doc, dry_run, changes):
    """Pose les 2 CF d'alarme ✗/⚠ sur Plus_value!B3, Avoirs!L1, Cotations!B20.

    Les 3 cellules portent les formules métier des Sections 3 (token ✗/✓ ou
    ⚠/✓) mais n'avaient pas de CF associée — convention "à la main" héritée
    du commit d628e492. Cette section pose les 2 conditions FIND("✗") /
    FIND("⚠") avec les styles existants ConditionalStyle_2 / ConditionalStyle_3.

    Idempotent : skip si la cellule a déjà 2 CF avec les bonnes formules.
    """
    targets = [
        ('Plus_value', 'B3'),
        ('Avoirs', 'L1'),
        ('Cotations', 'B20'),
    ]
    for sheet_name, cell_addr in targets:
        try:
            sheet = doc.get_sheet(sheet_name)
        except Exception as e:
            print(f"⚠ Section 8 : feuille '{sheet_name}' introuvable ({e})")
            continue
        cell = sheet.getCellRangeByName(cell_addr)
        if has_alarm_cf(cell):
            continue
        if not dry_run:
            set_alarm_cf(cell)
        changes.append(f"+ {sheet_name}!{cell_addr} : CF d'alarme ✗/⚠")


def _section_synthese(ws_ctrl, cr, doc, dry_run, changes):
    """Réécrit la formule Synthèse (K{rSynth}) pour 7 tokens.

    Scanne les rows headers post-migration (positions actualisées par les
    insertions des sections 4-5) et construit la concat dynamiquement.
    Bornes via NR CTRL2type (layout-agnostic). Refresh cr préalable car les
    insertions ont étendu les NRs côté UNO mais pas côté ColResolver cache.
    """
    cr.refresh(xdoc=doc.document)
    headers = ['COMPTES', 'CATÉGORIES', 'DIVERS', 'APPARIEMENTS',
               'BALANCES', 'INCONNUS', 'FORMULES']
    rows = {}
    try:
        s, e = cr.rows('CTRL2type')
        scan_range = range(max(1, s - 2), e + 5)
    except Exception:
        scan_range = range(1, 200)
    for r in scan_range:
        v = ws_ctrl.getCellByPosition(CTRL2_TYPE_COL, uno_row(r)).getString().strip()
        for lbl in headers:
            if v == lbl or v.startswith(lbl):
                rows[lbl] = r

    missing = [h for h in headers if h not in rows]
    if missing:
        print(f"⚠ Synthèse : headers manquants {missing} — formule non mise à jour")
        return

    synth_row = _ctrl2_find_row(ws_ctrl, cr, 'Synthèse des contrôles')
    if synth_row is None:
        synth_row = _ctrl2_find_row(ws_ctrl, cr, 'Synthèse')
    if synth_row is None:
        return

    k_concat = '&'.join(f'K{rows[h]}' for h in headers)
    synth_k = (
        f'=IF(ISNUMBER(FIND("✗";{k_concat}));"✗";'
        f'IF(ISNUMBER(FIND("⚠";{k_concat}));"⚠";"✓"))'
    )
    cell = ws_ctrl.getCellByPosition(CTRL2_DISPL_COL, uno_row(synth_row))
    if cell.getFormula() != synth_k:
        if not dry_run:
            cell.setFormula(synth_k)
        changes.append(f"~ Contrôles K{synth_row} : Synthèse étendue à 7 tokens")


def _section3_cotations(ws_cot, dry_run, changes):
    """Pose Cotations!B20 = alarme métier 'completeness'.

    Compte les devises utilisées (PVLdevise + AVRdevise) absentes de COTcode.
    Si > 0, lacune de configuration → ⚠.
    Pas de propagation #N/A toxique : COUNTIF ne plante pas sur lookup raté.
    """
    # Scanner pour ⚓ basse de la table cotations (pied)
    anchor_row = None
    for r in range(2, 100):
        v = ws_cot.getCellByPosition(0, uno_row(r)).getString().strip()
        if v == '⚓':
            # 2 ⚓ : la 1re est tête (r3), la 2e est pied
            if anchor_row is None:
                anchor_row = r  # 1re trouvée
            else:
                anchor_row = r  # remplacée par la 2e (qui est le pied)
                break
    target_row = (anchor_row + 1) if anchor_row else 20  # par défaut B20
    # Détecte 2 cas de lacune :
    #  (a) devise utilisée (PVLdevise/AVRdevise) absente de COTcode
    #  (b) devise présente dans COTcode mais sans cours (COTcours vide)
    formula = (
        '=IF('
        # (a) Devises utilisées non listées
        'SUMPRODUCT((COUNTIF(COTcode;PVLdevise)=0)*(PVLdevise<>""))'
        '+SUMPRODUCT((COUNTIF(COTcode;AVRdevise)=0)*(AVRdevise<>""))'
        # (b) Codes listés mais cours vide
        '+SUMPRODUCT((COTcode<>"")*(COTcours=""))'
        '>0;"⚠";"✓")'
    )
    cell = ws_cot.getCellByPosition(1, uno_row(target_row))  # col B (1)
    if cell.getFormula() != formula:
        if not dry_run:
            cell.setFormula(formula)
        changes.append(
            f"+ Cotations!B{target_row} = alarme métier (devises non cotées)")
    # Label en A pour lisibilité
    label_cell = ws_cot.getCellByPosition(0, uno_row(target_row))
    if label_cell.getString().strip() != 'Alarme cotations':
        if not dry_run:
            label_cell.setString('Alarme cotations')
        changes.append(f"+ Cotations!A{target_row} = 'Alarme cotations'")


def _section9_pvl_formulas_nr_driven(ws_pvl, dry_run, changes):
    """Convertit les pieds globaux H/I/K du Plus_value en NR-driven (#46).

    Cible : pieds 'TOTAL métaux/crypto-monnaies/devises' (col A) sur les 3
    colonnes H (PVLmontant_init), I (PVLsigma), K (PVLmontant).
    Remplace `=SUMIFS(K:K, A:A, "X")` (col absolus) par
    `=SUMIFS(<NR>, PVLsection, "X")` — layout-agnostic.

    Cellules HORS zone PVLmontant donc pas de cycle d'évaluation possible.

    Cas non couverts (volontairement) :
    - 'TOTAL portefeuilles' : déjà NR-driven (SUMPRODUCT via PVLtitre="Retenu").
    - 'Total' par portefeuille : refs absolues hardcoded conservées. Tentatives
      NR-driven (SUMIFS / SUMPRODUCT) cassent la conversion devise (Yuh) ou
      créent un cycle non résoluble (la cellule est dans la zone PVLmontant
      et ses dépendantes Retenu/#Solde forment un cycle bidirectionnel).
      À reprendre dans une version ultérieure si solution propre identifiée.

    Idempotent : compare la formule courante au format cible, skip si identique.
    """
    COLS = [
        (7,  'PVLmontant_init'),  # H
        (8,  'PVLsigma'),         # I
        (10, 'PVLmontant'),       # K
    ]
    COL_LETTER = {7: 'H', 8: 'I', 10: 'K'}
    section_targets = {
        'TOTAL métaux': 'métaux',
        'TOTAL crypto-monnaies': 'crypto',
        'TOTAL devises': 'devises',
    }

    # NB : GRAND TOTAL apparaît AVANT les TOTAL portefeuilles/métaux/crypto/devises
    # (pied multi-lignes), donc pas de break dessus — scan complet jusqu'à 300.
    for r in range(1, 300):
        a = ws_pvl.getCellByPosition(0, uno_row(r)).getString().strip()
        if a in section_targets:
            section_label = section_targets[a]
            for col_0, nr in COLS:
                target = f'=SUMIFS({nr};PVLsection;"{section_label}")'
                cell = ws_pvl.getCellByPosition(col_0, uno_row(r))
                if cell.getFormula() != target:
                    if not dry_run:
                        cell.setFormula(target)
                    changes.append(
                        f"~ Plus_value!{COL_LETTER[col_0]}{r} ({a}) : SUMIFS NR-driven")


def migrate(xlsm_path, dry_run=False):
    p = Path(xlsm_path).resolve()
    if not p.exists():
        print(f"❌ Fichier introuvable : {p}")
        return 1

    if check_lock_file(p):
        print(f"❌ Fichier verrouillé : {p}")
        print("   Ferme LibreOffice.")
        return 1

    with UnoDocument(p) as doc:
        cr = doc.cr
        ws_pat = doc.get_sheet('Patrimoine')
        ws_ctrl = doc.get_sheet('Contrôles')

        changes = []

        # --- Position cible Patrimoine = pied = PATlabel_end + 1 ---
        # Convention layout-agnostic : le NR PATlabel se termine sur la sentinelle ⚓,
        # le pied est la ligne juste après.
        pat_s, pat_e = cr.rows('PATlabel')
        if not pat_e:
            print("❌ NR PATlabel introuvable — abandon.")
            return 1
        pat_row = pat_e + 1
        pat_d_ref = f'Patrimoine.D{pat_row}'  # syntaxe UNO

        # --- Patrimoine B{pat_row} : label "Erreurs" ---
        b_cell = ws_pat.getCellByPosition(PAT_LABEL_COL_0, pat_row - 1)
        if b_cell.getString().strip() != PAT_LABEL:
            if not dry_run:
                b_cell.setString(PAT_LABEL)
            changes.append(f"+ Patrimoine!B{pat_row} = '{PAT_LABEL}'")

        # --- Construire la formule compteur écarts dynamiquement ---
        # Scan col B pour les TOTAL des sections (skip le 1er = TOTAL global qui
        # pointe sur une feuille externe).
        all_total_rows = []
        for r in range(2, 200):
            v = ws_pat.getCellByPosition(PAT_LABEL_COL_0, r - 1).getString().strip()
            if v == 'TOTAL':
                all_total_rows.append(r)
        if len(all_total_rows) < 2:
            print("❌ Moins de 2 lignes 'TOTAL' (global + sections) dans Patrimoine — abandon.")
            return 1
        section_rows = all_total_rows[1:]  # skip le global
        terms = [f'(ABS(D{r}-D4)>{PAT_TOLERANCE})' for r in section_rows]
        pat_formula = '=' + '+'.join(terms)

        # --- Patrimoine D{pat_row} : compteur écarts ventilations + bold ---
        d_cell = ws_pat.getCellByPosition(PAT_FORMULA_COL_0, pat_row - 1)
        cur_d = d_cell.getFormula()
        if cur_d.replace(' ', '') != pat_formula.replace(' ', ''):
            if not dry_run:
                d_cell.setFormula(pat_formula)
            changes.append(
                f"+ Patrimoine!D{pat_row} = compteur écarts (sections {section_rows})")
        if d_cell.CharWeight != BOLD:
            if not dry_run:
                d_cell.CharWeight = BOLD
            changes.append(f"+ Patrimoine!D{pat_row} bold")

        # --- Contrôles : ligne 'Date' (v3.x) / 'Cohérence' / 'Divers' / 'DIVERS' via NR CTRL2type ---
        ctrl2_s, ctrl2_e = cr.rows('CTRL2type')
        type_col = cr.col('CTRL2type')
        gen_col = cr.col('CTRL2general')

        recognized_labels = (CTRL2_OLD_LABEL, CTRL2_NEW_LABEL, *CTRL2_VARIANT_LABELS)
        target_row = None
        for r in range(ctrl2_s, ctrl2_e + 1):
            val = ws_ctrl.getCellByPosition(type_col, uno_row(r)).getString().strip()
            if val in recognized_labels:
                target_row = r
                break

        if target_row is None:
            print(f"⚠ Aucun label parmi {recognized_labels} trouvé dans CTRL2type — skip Contrôles")
        else:
            # Renommer si besoin (cible : MAJUSCULES)
            j_cell = ws_ctrl.getCellByPosition(type_col, uno_row(target_row))
            if j_cell.getString().strip() != CTRL2_NEW_LABEL:
                old = j_cell.getString().strip()
                if not dry_run:
                    j_cell.setString(CTRL2_NEW_LABEL)
                changes.append(f"+ Contrôles!J{target_row} : '{old}' → '{CTRL2_NEW_LABEL}'")

            # Étendre L{row} : purger d'abord les anciennes refs Patrimoine.D{x}
            # obsolètes (héritage migrations antérieures à mauvaise position),
            # puis ajouter la ref vers la cible courante si absente.
            import re as _re
            l_cell = ws_ctrl.getCellByPosition(gen_col, uno_row(target_row))
            cur_l = l_cell.getFormula()
            uno_ref = pat_d_ref                                 # Patrimoine.D{r}
            xlsx_ref = pat_d_ref.replace('.', '!')              # Patrimoine!D{r}
            new_l = cur_l
            # Purge des refs obsolètes (toute Patrimoine.D{x} ou Patrimoine!D{x}
            # avec x ≠ pat_row)
            obsolete_pat = _re.compile(
                r'\+\$?Patrimoine[.!]D(\d+)')
            def _filter_ref(m):
                return '' if int(m.group(1)) != pat_row else m.group(0)
            cleaned = obsolete_pat.sub(_filter_ref, new_l)
            if cleaned != new_l:
                changes.append(
                    f"~ Contrôles!L{target_row} : purge ref(s) Patrimoine.D obsolète(s)")
                new_l = cleaned
            # Ajout de la ref cible si absente
            if uno_ref not in new_l and xlsx_ref not in new_l:
                if new_l.startswith('='):
                    new_l = new_l + '+' + uno_ref
                else:
                    new_l = '=' + uno_ref
                changes.append(f"+ Contrôles!L{target_row} étendu : ...+{uno_ref}")
            if new_l != cur_l and not dry_run:
                l_cell.setFormula(new_l)

            # Format L{row} = nombre entier (au lieu d'EUR hérité de la col)
            fmt_nb = doc.register_number_format('0')
            if l_cell.NumberFormat != fmt_nb:
                if not dry_run:
                    l_cell.NumberFormat = fmt_nb
                changes.append(f"+ Contrôles!L{target_row} format = nombre entier")

        # ━━━ Section 2 : ligne CONV 'DIVERS' (label réservé) ━━━
        conv_s, conv_e = cr.rows('CONVnom')
        if not conv_s:
            print("⚠ NR CONVnom introuvable — skip CONV row")
        else:
            conv_col_0 = cr.col('CONVnom')
            cell_col_0 = conv_col_0 + 1   # K
            leg_col_0 = conv_col_0 + 2    # L

            # Idempotence étendue (corrige aussi #52) :
            #   - 'DIVERS' déjà là → rien à faire
            #   - variante legacy ('Cohérence' / 'Divers') → renommer en 'DIVERS'
            #   - rien → insérer une row avec 'DIVERS'
            existing_row = None       # row où une variante a été trouvée
            already_dest = False      # 'DIVERS' déjà posé
            for r in range(conv_s, conv_e + 1):
                v = ws_pat.getCellByPosition(cell_col_0, uno_row(r)).getString().strip()
                if v == CTRL2_NEW_LABEL:
                    already_dest = True
                    break
                if v in CTRL2_VARIANT_LABELS:
                    existing_row = r
                    break

            if already_dest:
                pass  # déjà migré
            elif existing_row is not None:
                # Renommage in place (correction #52)
                cell = ws_pat.getCellByPosition(cell_col_0, uno_row(existing_row))
                old = cell.getString().strip()
                if not dry_run:
                    cell.setString(CTRL2_NEW_LABEL)
                changes.append(
                    f"~ Patrimoine!K{existing_row} : '{old}' → '{CTRL2_NEW_LABEL}' (CONV)")
            else:
                # Insertion juste après la ligne K=='COMPTES' (groupe sémantique
                # "Tableau 2 feuille Contrôles"). Layout-agnostic : pas de row
                # hardcodée, on scan le label.
                insert_row = None
                for r in range(conv_s, conv_e + 1):
                    v = ws_pat.getCellByPosition(cell_col_0, uno_row(r)).getString().strip()
                    if v == 'COMPTES':
                        insert_row = r + 1
                        break
                if insert_row is None:
                    print("⚠ ligne CONV 'COMPTES' introuvable — skip CONV row")
                else:
                    if not dry_run:
                        # insertByIndex étend automatiquement les NRs (CONVnom/
                        # cell/légende) qui couvrent insert_row.
                        ws_pat.Rows.insertByIndex(uno_row(insert_row), 1)
                        ws_pat.getCellByPosition(cell_col_0, uno_row(insert_row)).setString(CTRL2_NEW_LABEL)
                        ws_pat.getCellByPosition(leg_col_0, uno_row(insert_row)).setString('Tableau 2 feuille Contrôles')
                    changes.append(
                        f"+ Patrimoine!K{insert_row} = '{CTRL2_NEW_LABEL}' (insertion row CONV)")

        # ━━━ Section 3 : alarmes formules sur synthèses + alarme métier Cotations ━━━
        try:
            _section3_plus_value(doc.get_sheet('Plus_value'), dry_run, changes)
        except Exception as e:
            print(f"⚠ Section 3 Plus_value : {e}")
        try:
            _section3_avoirs(doc.get_sheet('Avoirs'), dry_run, changes)
        except Exception as e:
            print(f"⚠ Section 3 Avoirs : {e}")
        try:
            _section3_cotations(doc.get_sheet('Cotations'), dry_run, changes)
        except Exception as e:
            print(f"⚠ Section 3 Cotations : {e}")

        # ━━━ Section 5 : ligne Formules + sous-lignes (insertion bas) ━━━
        # Faite AVANT Section 4 pour que les insertions ne se mêlent pas.
        try:
            _section5_formules(ws_ctrl, cr, dry_run, changes)
        except Exception as e:
            print(f"⚠ Section 5 : {e}")

        # ━━━ Section 4 : refonte K65 Cohérence → Divers + sous-lignes ━━━
        try:
            _section4_divers(ws_ctrl, ws_pat, cr, dry_run, changes)
        except Exception as e:
            print(f"⚠ Section 4 : {e}")

        # ━━━ Section 6 : indenter sous-lignes Balances existantes ━━━
        try:
            _section6_indent_balances(ws_ctrl, cr, dry_run, changes)
        except Exception as e:
            print(f"⚠ Section 6 : {e}")

        # ━━━ Fix headers K Divers/Formules : SUM en double → IF(L>0,…) ━━━
        try:
            _section_fix_headers_k_simple_ref(ws_ctrl, cr, dry_run, changes)
        except Exception as e:
            print(f"⚠ Fix K headers : {e}")

        # ━━━ Fix formule Date hors période (DATE(2030,…) → année_courante) ━━━
        try:
            _section_fix_date_formula(ws_ctrl, cr, dry_run, changes)
        except Exception as e:
            print(f"⚠ Fix Date : {e}")

        # ━━━ Normalisation MAJUSCULES headers Appariements / Balances ━━━
        try:
            _section_uppercase_legacy_headers(ws_ctrl, cr, dry_run, changes)
        except Exception as e:
            print(f"⚠ Uppercase headers : {e}")

        # ━━━ Synthèse : recalibrage K{rSynth} pour 7 tokens ━━━
        try:
            _section_synthese(ws_ctrl, cr, doc, dry_run, changes)
        except Exception as e:
            print(f"⚠ Synthèse : {e}")

        # ━━━ Section 7 : restreindre CF étendues sur sous-lignes K vides ━━━
        try:
            _section7_fix_alarm_cf_ranges(ws_ctrl, dry_run, changes)
        except Exception as e:
            print(f"⚠ Section 7 : {e}")

        # ━━━ Section 8 : auto-pose CF d'alarme sur les 3 cellules métier ━━━
        try:
            _section8_alarm_cf_three_cells(doc, dry_run, changes)
        except Exception as e:
            print(f"⚠ Section 8 : {e}")

        # ━━━ Section 9 : formules K Plus_value en NR-driven (#46) ━━━
        try:
            _section9_pvl_formulas_nr_driven(doc.get_sheet('Plus_value'), dry_run, changes)
        except Exception as e:
            print(f"⚠ Section 9 : {e}")

        # ━━━ Bump SCHEMA_VERSION 2 → 3 (refonte CTRL2 + alarmes) ━━━
        try:
            _section_bump_schema_version(doc, dry_run, changes, target_version='3')
        except Exception as e:
            print(f"⚠ Bump SCHEMA_VERSION : {e}")

        if not changes:
            print(f"✓ {p.name} : déjà migré, rien à faire.")
            return 0

        print(f"Migration {p.name} :")
        for c in changes:
            print(f"  {c}")

        if dry_run:
            print("\n[dry-run] pas de sauvegarde")
            return 0

        # Backup avant écriture (rollback simple en cas de problème).
        import shutil
        bak = p.with_suffix('.xlsm.bak')
        shutil.copy2(p, bak)
        print(f"📦 Backup : {bak.name}")

        doc.save()
        print(f"\n✓ Sauvé : {p}")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('xlsm', help='Chemin du classeur (témoin / template / comptes.xlsm)')
    ap.add_argument('--dry-run', action='store_true',
                    help="N'enregistre pas, affiche les changements prévus")
    args = ap.parse_args()
    return migrate(args.xlsm, dry_run=args.dry_run)


if __name__ == '__main__':
    sys.exit(main())
