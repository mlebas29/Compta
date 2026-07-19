"""
Schéma centralisé des colonnes et feuilles de comptes.xlsx.

Ce module définit le ColResolver (résolution dynamique des colonnes via
named ranges), les noms de feuilles et le dataclass Operation.

Les colonnes sont résolues dynamiquement via ColResolver.from_uno(xdoc) ou
ColResolver.from_openpyxl(wb). Plus d'IntEnum en dur.
"""

from dataclasses import dataclass, fields
from datetime import datetime
from typing import Optional


# Version de l'application — incrémentée à chaque livraison
APP_VERSION = "5.21.2"

# Version du schéma classeur — incrémentée à chaque changement de structure
# (named ranges, colonnes, formules). Le classeur doit avoir un named range
# SCHEMA_VERSION (constante) égal à cette valeur.
# Voir Compta_upgrade_classeur.md pour l'historique et les procédures de migration.
# Forme ENTIÈRE = domaine bloquant (cf. Compta_coherence.md : forme = gravité).
SCHEMA_VERSION = 3

# Version du schéma config — marqueur du composant Configuration (#98). Forme
# `major.minor` (string) : major en retard → bloque · minor → avertit. Toutes les
# migrations config actuelles sont tolérantes → décimales (major 0, jamais
# bloquant). Marqueur stocké dans config.ini [general] config_schema_version,
# avancé par upgrade SEUL. Distinct d'APP_VERSION et du SCHEMA_VERSION classeur.
# Voir Compta_coherence.md (modèle) et upgrade_map.json (config_migrations).
CONFIG_SCHEMA_VERSION = "0.2"

# Noms des 9 champs de base (colonnes Opérations A-I)
_BASE_FIELD_NAMES = (
    'date', 'label', 'montant', 'devise', 'equiv',
    'ref', 'categorie', 'compte', 'commentaire',
)


@dataclass
class Operation:
    """Représentation unifiée d'une opération dans le pipeline format→import→pair.

    Les 9 champs de base correspondent aux colonnes OpCol (A-I).
    Les champs enrichis (row, *_parsed) sont ajoutés par l'import ou le pairing.
    """
    # 9 champs de base (colonnes Excel A-I)
    date: str = ''
    label: str = ''
    montant: str = ''
    devise: str = 'EUR'
    equiv: str = ''
    ref: str = ''
    categorie: str = ''
    compte: str = ''
    commentaire: str = ''
    # Champs enrichis (pairing/Excel) — jamais sérialisés en CSV
    row: Optional[int] = None
    date_parsed: Optional[datetime] = None
    montant_parsed: Optional[float] = None
    equiv_parsed: Optional[float] = None

    # ------------------------------------------------------------------
    # Compatibilité transitoire : accès par index (op[0]), itération, len
    # ------------------------------------------------------------------

    def _base_values(self):
        """Retourne les 10 valeurs de base comme tuple de strings."""
        return tuple(
            str(getattr(self, name)) if getattr(self, name) is not None else ''
            for name in _BASE_FIELD_NAMES
        )

    def __getitem__(self, index):
        return self._base_values()[index]

    def __iter__(self):
        return iter(self._base_values())

    def __len__(self):
        return 9

    # ------------------------------------------------------------------
    # Constructeurs depuis l'existant
    # ------------------------------------------------------------------

    @classmethod
    def from_tuple(cls, t):
        """Construit depuis un tuple de 7-9 éléments (sortie formatteur)."""
        vals = list(t) + [''] * (9 - len(t))
        return cls(
            date=str(vals[0]) if vals[0] is not None else '',
            label=str(vals[1]) if vals[1] is not None else '',
            montant=str(vals[2]) if vals[2] is not None else '',
            devise=str(vals[3]) if vals[3] else 'EUR',
            equiv=str(vals[4]) if vals[4] is not None else '',
            ref=str(vals[5]) if vals[5] is not None else '',
            categorie=str(vals[6]) if vals[6] is not None else '',
            compte=str(vals[7]) if vals[7] is not None else '',
            commentaire=str(vals[8]) if vals[8] is not None else '',
        )

    @classmethod
    def from_dict(cls, d):
        """Construit depuis un dict (ancien format parse_csv_line / generate_linked)."""
        return cls(
            date=d.get('date', '') or '',
            label=d.get('label', '') or '',
            montant=str(d.get('montant', '')) if d.get('montant') is not None else '',
            devise=d.get('devise', 'EUR') or 'EUR',
            equiv=str(d.get('equiv', '')) if d.get('equiv') is not None else '',
            ref=d.get('ref', '') or '',
            categorie=d.get('categorie', '') or '',
            compte=d.get('compte', '') or '',
            commentaire=d.get('commentaire', '') or '',
            row=d.get('row'),
            date_parsed=d.get('date_parsed'),
            montant_parsed=d.get('montant_parsed'),
            equiv_parsed=d.get('equiv_parsed'),
        )

    def to_csv_line(self):
        """Sérialise les 10 champs de base en ligne CSV (debug)."""
        return ';'.join(self._base_values())


# ============================================================================


# ============================================================================
# NOMS DE FEUILLES
# ============================================================================

SHEET_OPERATIONS = 'Opérations'
SHEET_AVOIRS = 'Avoirs'
SHEET_CONTROLES = 'Contrôles'
SHEET_CONTROLES_LEGACY = 'Controle'     # ancien nom sans accent
SHEET_PLUS_VALUE = 'Plus_value'
SHEET_BUDGET = 'Budget'
SHEET_COTATIONS = 'Cotations'


# ============================================================================
# CONSTANTES DE LIGNES
# ============================================================================

PV_PROTECTED_FIRST_ROW = 5  # tool_purge : première ligne titre protégé

# Sources API par famille de devise (source1, source2/fallback)
DEVISE_SOURCES = {
    'fiat':   ('frankfurter', ''),
    'crypto': ('coingecko', 'kraken'),
    'metal':  ('yahoo', ''),
    'autre':  ('', ''),
}

# Cellule du compteur d'appariement : F2 (row=2, col=6)
PAIRING_COUNTER_CELL = (2, 6)

# NOTE sur la first row Opérations :
# Trois usages coexistent dans le codebase, selon le contexte :
#   row 2 : lectures incluant les #Solde (load_existing_operations, etc.)
#   row 3 : lectures excluant l'en-tête 2 lignes (load_unpaired_operations, analyze)
#   row 4 : lectures excluant les lignes spéciales (load_all_references)
# Pas de constante unique — chaque usage garde sa valeur explicite.


# ============================================================================
# ANCRES TABLEAUX (sentinelles ⚓ + règle NR ↔ sentinelles)
# ============================================================================
# Règle : chaque NR colonne de référence couvre exactement [row(⚓_top), row(⚓_bot)].
# La col porteuse des sentinelles = col du ref_nr (déduite dynamiquement).
# La famille de NRs = tous ceux dont le nom commence par le préfixe alpha du ref_nr.
# Les bornes row de tous les NRs de la famille sont identiques.
#
# Champs : (sheet, ref_nr, target_end_row_or_None, only_start)
# target_end = None : r2+1 pour introduire une nouvelle ancre de fin
#                     (cas PAT/CTRL2 pré-migration, tables à ancrer ex-nihilo).
# target_end = int  : row cible fixe pour l'ancre de fin (non utilisé en v3.6).
# only_start = True : table à ancrage top uniquement (OP — NR volontairement
#                     large sans ancre bot pour éviter d'impacter la zone
#                     utilisée UNO / les cursor.gotoEndOfUsedArea()).

ANCHOR_TABLES = [
    (SHEET_AVOIRS,     'AVRintitulé',  None,  False),
    (SHEET_BUDGET,     'CATnom',       None,  False),
    (SHEET_BUDGET,     'POSTESnom',    None,  False),
    (SHEET_COTATIONS,  'COTlabel',     None,  False),
    (SHEET_CONTROLES,  'CTRL1compte',  None,  False),
    (SHEET_CONTROLES,  'CTRL2type',    None,  False),
    (SHEET_OPERATIONS, 'OPdate',       None,  True),   # only_start
    ('Patrimoine',     'PATlabel',     None,  False),
    # CONV absent volontairement : c'est un tableau statique créé par
    # ensure_conventions_table (tool_migrate), invariant entre classeurs et
    # propagé tel quel par tool_sync_from_witness. Pas de bornes dynamiques
    # à valider/ajuster.
    (SHEET_PLUS_VALUE, 'PVLsection',   None,  False),
]


# ============================================================================
# HELPER UNO (0-indexed)
# ============================================================================



def uno_col(col):
    """Convertit un indice de colonne openpyxl (1-indexed) en indice UNO (0-indexed)."""
    return int(col) - 1


def uno_row(row):
    """Convertit un indice de ligne Excel/openpyxl (1-indexed) en indice UNO (0-indexed)."""
    return int(row) - 1


# ============================================================================
# ColResolver — résolution dynamique des colonnes via named ranges
# ============================================================================

class ColResolver:
    """Résout les colonnes dynamiquement depuis les named ranges du classeur.

    Deux modes :
    - UNO (0-indexed) : cr = ColResolver.from_uno(xdoc)
    - openpyxl (1-indexed) : cr = ColResolver.from_openpyxl(wb)

    Usage :
        cr = ColResolver.from_uno(xdoc)
        ws.getCellByPosition(cr.col('PATlabel'), r0)
        cell.setFormula('=SUM(PATvaleur)')  # named range = range colonne complet
    """

    def __init__(self, cols, letters, rows=None):
        """Constructeur interne — utiliser from_uno() ou from_openpyxl()."""
        self._cols = cols        # {name: col_index}
        self._letters = letters  # {name: col_letter_string}
        self._rows = rows or {}  # {name: (start_row_1idx, end_row_1idx)}

    def col(self, name):
        """Retourne l'indice de colonne (0-indexed UNO ou 1-indexed openpyxl)."""
        return self._cols[name]

    def letter(self, name):
        """Retourne la lettre de colonne (ex: 'A', 'AB')."""
        return self._letters[name]

    def rows(self, name):
        """Retourne (start_row, end_row) 1-indexed depuis le named range colonne.

        Usage :
            s, e = cr.rows('AVRintitulé')
            for r in range(s + 1, e):  # données entre model rows
        """
        return self._rows.get(name, (None, None))

    def refresh(self, xdoc=None, wb=None):
        """Reconstruit le cache après modifications structurelles (insertion/suppression colonnes).

        Appeler après des opérations qui changent les colonnes (ex: phase_clean_budget).
        Passer xdoc (UNO) ou wb (openpyxl) selon le contexte.
        """
        if xdoc:
            fresh = ColResolver.from_uno(xdoc)
        elif wb:
            fresh = ColResolver.from_openpyxl(wb)
        else:
            return
        self._cols = fresh._cols
        self._letters = fresh._letters
        self._rows = fresh._rows

    @staticmethod
    def _idx_to_letter(n):
        """Convertit un index 1-indexed en lettre (1→A, 26→Z, 27→AA)."""
        result = ''
        while n > 0:
            n, rem = divmod(n - 1, 26)
            result = chr(65 + rem) + result
        return result

    @classmethod
    def from_uno(cls, xdoc):
        """Construit un ColResolver depuis un document UNO (colonnes 0-indexed)."""
        from inc_uno import get_col_range_bounds
        nr = xdoc.NamedRanges
        cols = {}
        letters = {}
        rows = {}
        for i in range(nr.Count):
            name = nr.getByIndex(i).Name
            bounds = get_col_range_bounds(xdoc, name)
            if bounds:
                _, col_0, start_1, end_1 = bounds
                cols[name] = col_0
                letters[name] = cls._idx_to_letter(col_0 + 1)
                rows[name] = (start_1, end_1)
        return cls(cols, letters, rows)

    @classmethod
    def from_openpyxl(cls, wb):
        """Construit un ColResolver depuis un workbook openpyxl (colonnes 1-indexed)."""
        import re
        cols = {}
        letters = {}
        rows = {}
        for dn in wb.defined_names.values():
            attr = dn.attr_text
            # Parser 'Sheet!$A$4:$A$80' ou 'Sheet!$A$4'
            m = re.match(r"'?[^'!]+'?!\$([A-Z]+)\$(\d+)(?::\$[A-Z]+\$(\d+))?", attr)
            if not m:
                continue
            col_str = m.group(1)
            start_row = int(m.group(2))
            end_row = int(m.group(3)) if m.group(3) else start_row
            # Lettre → index 1-indexed
            col_1 = 0
            for ch in col_str:
                col_1 = col_1 * 26 + (ord(ch) - 64)
            cols[dn.name] = col_1
            letters[dn.name] = col_str
            rows[dn.name] = (start_row, end_row)
        return cls(cols, letters, rows)


# ============================================================================
# Lecteurs métadonnées Cotations (famille / décimales) — SOURCE = classeur
# ============================================================================
# famille et décimales vivent dans la feuille Cotations (COTfamille/COTdecimales),
# source unique de vérité. config_cotations.json ne porte plus que la route de
# fetch (source1/source2), consommée par cpt_fetch_quotes. Ces lecteurs alimentent
# la couche format (inc_formats.build_formats_devise) au point d'application, où
# le classeur est déjà ouvert (zéro lecture classeur à l'import).

_COT_DEFAULT_DECIMALS = 2


def _cot_decimals(value):
    """Normalise une valeur de cellule COTdecimales en int (fallback défaut)."""
    if value is None or str(value).strip() == '':
        return _COT_DEFAULT_DECIMALS
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return _COT_DEFAULT_DECIMALS


def read_cotations_meta(wb):
    """{code: {'famille': str, 'decimals': int}} depuis la feuille Cotations (openpyxl).

    Source unique de vérité = classeur. Retourne {} si feuille/colonnes absentes
    (classeur trop ancien) → les appelants retombent sur les défauts.
    """
    if SHEET_COTATIONS not in wb.sheetnames:
        return {}
    ws = wb[SHEET_COTATIONS]
    cr = ColResolver.from_openpyxl(wb)
    if 'COTcode' not in cr._cols:
        return {}
    code_col = cr.col('COTcode')
    fam_col = cr._cols.get('COTfamille')
    dec_col = cr._cols.get('COTdecimales')
    start, end = cr.rows('COTcode')
    start = start or 3
    end = end or ws.max_row
    meta = {}
    for row in range(start + 1, end + 1):
        code = ws.cell(row=row, column=code_col).value
        if not code:
            continue
        code = str(code).strip()
        if not code or code in ('✓', '⚓'):
            continue
        fam = ws.cell(row=row, column=fam_col).value if fam_col is not None else ''
        dec = ws.cell(row=row, column=dec_col).value if dec_col is not None else None
        meta[code] = {
            'famille': str(fam).strip() if fam else '',
            'decimals': _cot_decimals(dec),
        }
    return meta


def read_cotations_meta_uno(doc):
    """{code: {'famille': str, 'decimals': int}} depuis la feuille Cotations (UNO)."""
    sheets = doc.Sheets
    if not sheets.hasByName(SHEET_COTATIONS):
        return {}
    ws = sheets.getByName(SHEET_COTATIONS)
    cr = ColResolver.from_uno(doc)
    if 'COTcode' not in cr._cols:
        return {}
    code_col = cr.col('COTcode')
    fam_col = cr._cols.get('COTfamille')
    dec_col = cr._cols.get('COTdecimales')
    start, end = cr.rows('COTcode')
    if not start:
        return {}
    meta = {}
    for r_1 in range(start + 1, end + 1):
        r0 = r_1 - 1
        code = ws.getCellByPosition(code_col, r0).getString().strip()
        if not code or code in ('✓', '⚓'):
            continue
        fam = ws.getCellByPosition(fam_col, r0).getString().strip() if fam_col is not None else ''
        dec = ws.getCellByPosition(dec_col, r0).getValue() if dec_col is not None else None
        meta[code] = {'famille': fam, 'decimals': _cot_decimals(dec)}
    return meta


# Marqueurs de ligne-modèle / sentinelle des tableaux (ignorés au scan).
_OP_SENTINELS = ('⚓', '✓')


def iter_operations(wb, compte=None, categorie=None):
    """Générateur des opérations (feuille Opérations), **borné par named range**
    (jamais `ws.max_row`), filtré optionnellement par `compte` et/ou `categorie`
    (comparaison casse-insensible). Yield un dict par ligne de données :
    {row, date, montant, devise, equiv, réf, libellé, catégorie, compte, commentaire}.

    Lecteur PARTAGÉ : centralise le motif « ColResolver + scan OP + filtre »
    au lieu de le redupliquer (cf. get_account_balance / load_existing_operations,
    à converger — #125). Openpyxl, valeurs brutes (le parsing reste au caller).
    """
    ws = wb[SHEET_OPERATIONS]
    cr = ColResolver.from_openpyxl(wb)
    r0, r1 = cr.rows('OPcompte')
    if not r0:
        return
    cols = {k: cr._cols.get('OP' + k) for k in
            ('date', 'montant', 'devise', 'equiv_euro', 'réf', 'libellé',
             'catégorie', 'compte', 'commentaire')}
    if not cols['compte']:
        return
    cat_lc = categorie.strip().lower() if categorie else None

    def _cell(row, key):
        ci = cols[key]
        return ws.cell(row, ci).value if ci else None

    for row in range(r0, r1 + 1):
        cpt = _cell(row, 'compte')
        if not cpt or cpt in _OP_SENTINELS:
            continue
        if compte is not None and cpt != compte:
            continue
        cat = _cell(row, 'catégorie')
        if cat_lc is not None and str(cat or '').strip().lower() != cat_lc:
            continue
        yield {
            'row': row,
            'date': _cell(row, 'date'),
            'montant': _cell(row, 'montant'),
            'devise': _cell(row, 'devise'),
            'equiv': _cell(row, 'equiv_euro'),
            'réf': _cell(row, 'réf'),
            'libellé': _cell(row, 'libellé'),
            'catégorie': cat,
            'compte': cpt,
            'commentaire': _cell(row, 'commentaire'),
        }
