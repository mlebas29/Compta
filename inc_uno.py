"""Module partagé pour l'accès UNO à LibreOffice.

Centralise le démarrage soffice, la connexion UNO, l'ouverture de documents
et le cleanup. Remplace le code dupliqué dans tool_controles.py,
tool_migrate_cotations.py et inc_excel_import.py.

Usage:
    from inc_uno import UnoDocument, check_lock_file

    if check_lock_file(xlsx_path):
        print("Fichier verrouillé par LibreOffice")
        return

    with UnoDocument(xlsx_path, read_only=True, logger=logger) as doc:
        sheet = doc.get_sheet('Avoirs')
        cell = sheet.getCellByPosition(0, 0)
        print(cell.getString())

ATTENTION formules setFormula() — syntaxe Calc A1 native :
  - Séparateur d'arguments : point-virgule (;), PAS virgule (,)
  - Référence inter-feuille : point (.), PAS exclamation (!)
    cell.setFormula('=SUMIFS(A1:A10;B1:B10;"x")')   # OK
    cell.setFormula('=Avoirs.A12')                    # OK
    cell.setFormula('=SUMIFS(A1:A10,B1:B10,"x")')   # Err 509 !
    cell.setFormula('=Avoirs!A12')                    # Err 509 !
"""

import os
import subprocess
import time
from pathlib import Path

try:
    import uno
    from com.sun.star.beans import PropertyValue
    HAS_UNO = True
except ImportError:
    HAS_UNO = False


def check_lock_file(file_path):
    """True si .~lock.* existe (LibreOffice a le fichier ouvert)."""
    p = Path(file_path)
    lock = p.parent / f".~lock.{p.name}#"
    return lock.exists()


def copy_row_style(sheet, src_row, dst_row, col_start=0, col_end=12):
    """Copie style (fond, police, bordures, format nombre) d'une ligne à une autre.

    Indices UNO 0-indexed. col_end est exclusif.
    """
    for col in range(col_start, col_end):
        src_cell = sheet.getCellByPosition(col, src_row)
        dst_cell = sheet.getCellByPosition(col, dst_row)
        dst_cell.CellStyle = src_cell.CellStyle
        dst_cell.CellBackColor = src_cell.CellBackColor
        dst_cell.CharHeight = src_cell.CharHeight
        dst_cell.CharWeight = src_cell.CharWeight
        dst_cell.CharColor = src_cell.CharColor
        dst_cell.NumberFormat = src_cell.NumberFormat
        # Bordures
        dst_cell.TopBorder = src_cell.TopBorder
        dst_cell.BottomBorder = src_cell.BottomBorder
        dst_cell.LeftBorder = src_cell.LeftBorder
        dst_cell.RightBorder = src_cell.RightBorder
        # Alignement
        dst_cell.HoriJustify = src_cell.HoriJustify
        dst_cell.VertJustify = src_cell.VertJustify


def copy_col_style(sheet, src_col, dst_col, row_start=0, row_end=100, skip_rows=None):
    """Copie style (fond, police, bordures, format nombre) d'une colonne à une autre.

    Indices UNO 0-indexed. row_end est exclusif.
    skip_rows: set de row 0-indexed à ne pas toucher (model rows ✓).
    """
    for row in range(row_start, row_end):
        if skip_rows and row in skip_rows:
            continue
        src_cell = sheet.getCellByPosition(src_col, row)
        dst_cell = sheet.getCellByPosition(dst_col, row)
        dst_cell.CellStyle = src_cell.CellStyle
        dst_cell.CellBackColor = src_cell.CellBackColor
        dst_cell.CharHeight = src_cell.CharHeight
        dst_cell.CharWeight = src_cell.CharWeight
        dst_cell.CharColor = src_cell.CharColor
        dst_cell.NumberFormat = src_cell.NumberFormat
        # Bordures
        dst_cell.TopBorder = src_cell.TopBorder
        dst_cell.BottomBorder = src_cell.BottomBorder
        dst_cell.LeftBorder = src_cell.LeftBorder
        dst_cell.RightBorder = src_cell.RightBorder
        # Alignement
        dst_cell.HoriJustify = src_cell.HoriJustify
        dst_cell.VertJustify = src_cell.VertJustify


def get_named_range_pos(xdoc, name):
    """Retourne (sheet_name, col_0indexed, row_0indexed) pour un nom défini UNO.

    Retourne None si le nom n'existe pas.
    """
    nr = xdoc.NamedRanges
    if not nr.hasByName(name):
        return None
    content = nr.getByName(name).Content  # e.g. "$Contrôles.$A$3"
    # Parse: $Sheet.$Col$Row
    content = content.lstrip('$')
    parts = content.split('.$')
    sheet_name = parts[0]
    cell_ref = parts[1] if len(parts) > 1 else parts[0]
    # Parse col/row from e.g. "A$3" or "A3" or "$A$3"
    cell_ref = cell_ref.replace('$', '')
    col_str = ''
    row_str = ''
    for ch in cell_ref:
        if ch.isalpha():
            col_str += ch
        else:
            row_str += ch
    col = 0
    for ch in col_str.upper():
        col = col * 26 + (ord(ch) - 64)
    col -= 1  # 0-indexed
    try:
        row = int(row_str) - 1  # 0-indexed
    except ValueError:
        return None  # Named range corrompu (#REF!, etc.)
    return sheet_name, col, row


def get_table_bounds_uno(xdoc, table_name):
    """Retourne (start_row_1indexed, end_row_1indexed) depuis les named ranges UNO.

    START pointe sur la model row ✓. Les données commencent à start_row + 1.
    Retourne (None, None) si les named ranges sont absentes.

    Usage:
        s, e = get_table_bounds_uno(xdoc, 'AVR')
        for r in range(s + 1, e):  # données entre les 2 model rows
            ...  # utiliser uno_row(r)
    """
    s = get_named_range_pos(xdoc, f'START_{table_name}')
    e = get_named_range_pos(xdoc, f'END_{table_name}')
    if s and e:
        return s[2] + 1, e[2] + 1  # 0-indexed → 1-indexed
    # OP n'a pas d'END_OP depuis v3.0.0 — pas de warning si seul END manque
    if table_name == 'OP' and s and not e:
        return s[2] + 1, None
    import logging
    missing = []
    if not s: missing.append(f'START_{table_name}')
    if not e: missing.append(f'END_{table_name}')
    logging.warning(f"Named range(s) manquant(s): {', '.join(missing)} — fallback constante")
    return None, None


class UnoDocument:
    """Context manager pour accès UNO à un fichier xlsx.

    with UnoDocument(file_path, read_only=False, logger=None) as doc:
        sheet = doc.get_sheet('Avoirs')
        sheet.Rows.insertByIndex(pos, count)  # formules auto-ajustées
        doc.calculate_all()
        doc.save()
    """

    def __init__(self, file_path, read_only=False, logger=None):
        self._file_path = Path(file_path).resolve()
        self._read_only = read_only
        self._logger = logger
        self._process = None
        self._document = None
        self._desktop = None

    def _log(self, msg):
        if self._logger:
            self._logger.info(msg)

    def __enter__(self):
        if not HAS_UNO:
            raise ImportError("Module UNO non disponible. Utiliser le Python système.")

        # Démarrer soffice
        self._process = subprocess.Popen(
            ['soffice', '--headless',
             '--accept=socket,host=localhost,port=2002;urp;',
             '--nofirststartwizard'],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        time.sleep(3)

        # Connexion avec retry (5 tentatives)
        localContext = uno.getComponentContext()
        resolver = localContext.ServiceManager.createInstanceWithContext(
            "com.sun.star.bridge.UnoUrlResolver", localContext)

        ctx = None
        for attempt in range(5):
            try:
                ctx = resolver.resolve(
                    "uno:socket,host=localhost,port=2002;urp;StarOffice.ComponentContext")
                break
            except Exception:
                if attempt < 4:
                    time.sleep(1)
                else:
                    raise

        smgr = ctx.ServiceManager
        self._desktop = smgr.createInstanceWithContext(
            "com.sun.star.frame.Desktop", ctx)

        # Ouvrir le document
        url = uno.systemPathToFileUrl(str(self._file_path))
        properties = (
            PropertyValue("Hidden", 0, True, 0),
            PropertyValue("ReadOnly", 0, self._read_only, 0),
        )
        self._document = self._desktop.loadComponentFromURL(
            url, "_blank", 0, properties)
        time.sleep(2)

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if self._document:
                if not self._read_only:
                    self._document.setModified(False)
                self._document.close(True)
        except Exception:
            pass
        try:
            if self._desktop:
                self._desktop.terminate()
        except Exception:
            pass
        if self._process:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait()
        return False

    def get_sheet(self, name):
        """Retourne une feuille par nom. ValueError si absente."""
        sheets = self._document.getSheets()
        if not sheets.hasByName(name):
            raise ValueError(f"Feuille '{name}' introuvable")
        return sheets.getByName(name)

    def save(self):
        """Sauvegarde le document. Erreur si read_only.

        Les miroirs Contrôles C1 et Avoirs L1 ont été supprimés : la GUI lit
        directement A1/L2 (cached values des formules, à jour après tout save).
        """
        if self._read_only:
            raise RuntimeError("Document ouvert en lecture seule, save() interdit")
        self._document.store()

    def calculate_all(self):
        """Force le recalcul de toutes les formules."""
        self._document.calculateAll()

    def register_number_format(self, format_string):
        """Enregistre un format nombre et retourne sa clé UNO."""
        formats = self._document.getNumberFormats()
        locale = uno.createUnoStruct('com.sun.star.lang.Locale')
        key = formats.queryKey(format_string, locale, False)
        if key == -1:
            key = formats.addNew(format_string, locale)
        return key

    @property
    def document(self):
        """Accès direct au document UNO."""
        return self._document


def refresh_controles(file_path, logger=None):
    """Recalcule les formules et met à jour le miroir Avoirs L1.

    Appelé par les scripts openpyxl en fin de traitement (les sauvegardes
    openpyxl n'écrivent pas les valeurs cached des formules — la GUI en a
    besoin pour lire A1/L2 rapidement via ZIP).
    Force LibreOffice à recalculer toutes les formules et à re-écrire les
    valeurs cached (utilisées ensuite par la lecture rapide ZIP de la GUI).
    """
    if not HAS_UNO:
        return
    try:
        with UnoDocument(file_path, read_only=False, logger=logger) as doc:
            doc.calculate_all()
            doc.save()  # save() recalcule + écrit le miroir Avoirs L1
    except Exception as e:
        if logger:
            logger.warning(f"refresh_controles: {e}")
