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
APP_VERSION = "3.5.5"

# Version du schéma classeur — incrémentée à chaque changement de structure
# (named ranges, colonnes, formules). Le classeur doit avoir un named range
# SCHEMA_VERSION (constante) égal à cette valeur.
# Voir Compta_upgrade.md pour l'historique et les procédures de migration.
SCHEMA_VERSION = 1

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
