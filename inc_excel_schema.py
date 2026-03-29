"""
Schéma centralisé des colonnes et feuilles de comptes.xlsx.

Ce module définit les indices de colonnes (IntEnum, 1-indexed openpyxl),
les noms de feuilles, les constantes de lignes et le dataclass Operation
utilisées dans tout le codebase.

Convention : toutes les colonnes sont 1-indexed (openpyxl).
Pour tool_controles.py (UNO, 0-indexed), utiliser uno_col().
"""

from dataclasses import dataclass, fields
from datetime import datetime
from enum import IntEnum
from typing import Optional


# ============================================================================
# COLONNES — Feuille Opérations
# ============================================================================

class OpCol(IntEnum):
    """Colonnes de la feuille Opérations (1-indexed, openpyxl)."""
    DATE = 1           # A
    LABEL = 2          # B
    MONTANT = 3        # C
    DEVISE = 4         # D
    EQUIV = 5          # E
    REF = 6            # F
    CATEGORIE = 7      # G
    COMPTE = 8         # H
    COMMENTAIRE = 9    # I


# Noms des 9 champs de base, dans l'ordre OpCol (pour from_tuple / __iter__)
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
# COLONNES — Feuille Avoirs
# ============================================================================

class AvCol(IntEnum):
    """Colonnes de la feuille Avoirs (1-indexed, openpyxl)."""
    INTITULE = 1       # A
    TYPE = 2           # B
    DOMICILIATION = 3  # C
    SOUS_TYPE = 4      # D
    DEVISE = 5         # E
    TITULAIRE = 6      # F
    PROPRIETE = 7      # G
    DATE_ANTER = 8     # H
    MONTANT_ANTER = 9  # I
    DATE_SOLDE = 10    # J  (date du dernier solde)
    MONTANT_SOLDE = 11 # K  (montant du dernier solde, en devise)
    FORMULE_L = 12     # L  (équivalent EUR)


# ============================================================================
# COLONNES — Feuille Contrôles
# ============================================================================

class CtrlCol(IntEnum):
    """Colonnes de la feuille Contrôles (1-indexed, openpyxl).

    Après migration sous-comptes : colonnes B (sous-compte) et N (SC_ABSENT) supprimées.
    """
    COMPTE = 1         # A
    DEVISE = 2         # B  (ex-C)
    DATE_FIN = 5       # E  (ex-F, date la plus récente)
    SOLDE_CALC = 8     # H  (ex-I, solde calculé)
    SOLDE_RELEVE = 9   # I  (ex-J, solde relevé)
    ECART = 10         # J  (ex-K)
    CONTROLE_FLAG = 11 # K  (ex-L, Oui/Non)
    REPORTS_FIN = 12   # L  (ex-M)


# ============================================================================
# COLONNES — Feuille Plus_value
# ============================================================================

class PvCol(IntEnum):
    """Colonnes de la feuille Plus_value (1-indexed, openpyxl)."""
    SECTION = 1        # A — indicateur de section (portefeuilles/métaux/crypto/devises)
    COMPTE = 2         # B
    LIGNE = 3          # C
    DEVISE = 4         # D
    PVL = 5            # E
    PCT = 6            # F
    DATE_INIT = 7      # G
    MONTANT_INIT = 8   # H
    SIGMA = 9          # I
    DATE_SOLDE = 10    # J
    SOLDE = 11         # K


# ============================================================================
# COLONNES — Feuille Cotations
# ============================================================================

class CotCol(IntEnum):
    """Colonnes de la feuille Cotations (1-indexed, openpyxl)."""
    LABEL = 1          # A
    NATURE = 2         # B  (primaire / dérivée)
    CODE = 3           # C
    COURS_EUR = 4      # D
    DATE = 5           # E


# ============================================================================
# COLONNES — Feuille Budget
# ============================================================================

class BudgetCol(IntEnum):
    """Colonnes de la feuille Budget (1-indexed, openpyxl)."""
    CATEGORIES = 12    # L — nom catégorie
    FIRST_DEVISE = 13  # M — première devise (EUR)
    LAST_DEVISE = 24   # X — dernière devise (SEK)
    EQUIV_EUR = 25     # Y — =SUMPRODUCT(M:W * taux)
    ALLOC_PCT = 26     # Z — % affectation
    ALLOC_MONTANT = 27 # AA — =Y*Z
    POSTE = 28         # AB — poste budgétaire


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

# Feuille Avoirs : première ligne de données
AV_FIRST_ROW = 4

# Feuille Contrôles : première ligne de données
CTRL_FIRST_ROW = 3

# Feuille Plus_value
PV_FIRST_ROW = 2
PV_PROTECTED_FIRST_ROW = 5    # première ligne comptes protégés (purge)
# Pas de LAST_ROW : utiliser ws.max_row pour scanner dynamiquement

# Feuille Cotations
COT_FIRST_ROW = 3             # première ligne de données (après en-tête)
# Pas de LAST_ROW : utiliser ws.max_row pour scanner dynamiquement
ASSET_TYPES = {'fiat', 'crypto', 'metal', 'immobilier'}

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
# HELPER UNO (0-indexed)
# ============================================================================

def col_letter(col):
    """Convertit un indice de colonne 1-indexed en lettres Excel (1→A, 26→Z, 27→AA, 30→AD)."""
    result = ''
    while col > 0:
        col, remainder = divmod(col - 1, 26)
        result = chr(65 + remainder) + result
    return result


def get_named_ranges(wb):
    """Extrait les noms définis d'un workbook openpyxl.

    Retourne un dict {name: (sheet_name, col_1indexed, row_1indexed)}.
    Pour les ranges (ex: $A$4:$A$71), retourne le coin supérieur gauche.
    """
    from openpyxl.utils import coordinate_to_tuple
    result = {}
    for name_str in wb.defined_names:
        dn = wb.defined_names[name_str]
        dests = list(dn.destinations)
        if len(dests) != 1:
            continue
        sheet_name, cell_ref = dests[0]  # ('Budget', '$L$27') ou ('Avoirs', '$A$4:$A$71')
        # Prendre le coin supérieur gauche si c'est un range
        cell_ref = cell_ref.split(':')[0].replace('$', '')
        row, col = coordinate_to_tuple(cell_ref)
        result[name_str] = (sheet_name, col, row)
    return result


def uno_col(col):
    """Convertit un indice de colonne openpyxl (1-indexed) en indice UNO (0-indexed)."""
    return int(col) - 1


def uno_row(row):
    """Convertit un indice de ligne Excel/openpyxl (1-indexed) en indice UNO (0-indexed)."""
    return int(row) - 1
