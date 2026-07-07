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
import sys
import time
from pathlib import Path

try:
    import uno
    from com.sun.star.beans import PropertyValue
    HAS_UNO = True
except ImportError:
    HAS_UNO = False


def _uno_unavailable_msg():
    """Message d'erreur explicite selon l'OS quand le module uno est absent."""
    if sys.platform == 'darwin':
        return ("Module UNO non disponible avec ce Python.\n"
                "Sur macOS, 'uno' n'est livré qu'avec LibreOffice.app.\n"
                "  → relancer en utilisant le shebang : ./<script.py> [args]\n"
                "    (le wrapper python3-uno sélectionne automatiquement le Python embarqué)\n"
                "  → ou explicitement : /Applications/LibreOffice.app/Contents/Resources/python <script.py>\n"
                "Wrapper installé par install.sh dans ~/.local/bin/python3-uno.")
    if sys.platform.startswith('linux'):
        return ("Module UNO non disponible.\n"
                "  → sudo apt install python3-uno")
    return "Module UNO non disponible sur cette plateforme."


def _soffice_path():
    """Chemin du binaire soffice selon l'OS.

    Linux : 'soffice' (dans le PATH via le paquet libreoffice).
    macOS : chemin absolu dans le bundle LibreOffice.app (PATH n'inclut pas
    /Applications/LibreOffice.app/Contents/MacOS).
    """
    if sys.platform == 'darwin':
        return '/Applications/LibreOffice.app/Contents/MacOS/soffice'
    return 'soffice'


def get_libreoffice_version():
    """Retourne la version LibreOffice comme tuple (major, minor, patch).

    Lève RuntimeError si LO introuvable ou sortie illisible.
    """
    import subprocess, re
    try:
        out = subprocess.check_output(
            [_soffice_path(), '--version'],
            text=True, stderr=subprocess.STDOUT, timeout=10)
    except (FileNotFoundError, subprocess.CalledProcessError,
            subprocess.TimeoutExpired) as e:
        raise RuntimeError(f"LibreOffice introuvable ou injoignable : {e}")
    m = re.search(r'(\d+)\.(\d+)\.(\d+)', out)
    if not m:
        raise RuntimeError(f"Version LibreOffice illisible : {out!r}")
    return tuple(int(x) for x in m.groups())


def require_libreoffice_min(major, minor):
    """Refuse l'exécution si LO < (major, minor). Sort avec exit(2) sinon.

    LO < 24.8 corrompt les formules XLOOKUP via UNO save (ajoute le préfixe
    `_xlfn.` qu'il ne sait pas relire). Voir Compta_portage.md § WSL.
    """
    actual = get_libreoffice_version()
    if actual < (major, minor):
        ver_str = '.'.join(str(x) for x in actual)
        sys.stderr.write(
            f"❌ LibreOffice {ver_str} détectée — minimum requis : "
            f"{major}.{minor}.x\n"
            f"   Cette version corrompt les formules XLOOKUP lors d'un "
            f"save UNO (préfixe _xlfn. ajouté puis illisible).\n"
            f"   Upgrade :\n"
            f"     Linux/WSL : sudo add-apt-repository ppa:libreoffice/ppa\n"
            f"                 sudo apt update && sudo apt install libreoffice\n"
            f"     macOS     : télécharger LO ≥ 24.8.x depuis libreoffice.org\n"
        )
        sys.exit(2)


def check_env():
    """Contrôle de cohérence environnement Compta.

    Hook unique appelé au démarrage des scripts (CLI, GUI, TNR) pour valider
    les pré-requis. Aujourd'hui : présence du wrapper python3-uno (shebang
    des scripts UNO). Extensible : peut accueillir d'autres checks
    (LibreOffice, openpyxl dans LO Python, configs critiques, etc.)

    Retourne (True, '') si tout OK, sinon (False, message_explicite).
    Conçu non bloquant : à chaque caller de décider du niveau d'alerte
    (logger.warning / messagebox / print).
    """
    import shutil
    if not shutil.which('python3-uno'):
        return False, (
            "Wrapper 'python3-uno' introuvable dans le PATH.\n"
            "Les commandes UNO (push, update, fetch quotes, boutons GUI) "
            "vont échouer.\n"
            "  → relancer ./install.sh, ou ajouter ~/.local/bin au PATH "
            "(installé par install.sh).")
    return True, ''


def check_lock_file(file_path):
    """True si .~lock.* existe (LibreOffice a le fichier ouvert)."""
    p = Path(file_path)
    lock = p.parent / f".~lock.{p.name}#"
    return lock.exists()


def copy_row_style(sheet, src_row, dst_row, col_start=0, col_end=12):
    """Copie style (fond, police, bordures, format nombre) d'une ligne à une autre.

    Indices UNO 0-indexed. col_end est exclusif.
    Le template (src_row) doit être une model row conforme charte (typiquement
    une row adjacente à la sentinelle ⚓ top du NR), pour que la propagation
    de fond (col_ref beige + data blanc) se fasse correctement de proche en
    proche. Les exceptions (sub-pied PVL beige, grisage devise) sont posées
    explicitement par les fonctions GUI métier en 2ème couche.
    """
    for col in range(col_start, col_end):
        src_cell = sheet.getCellByPosition(col, src_row)
        dst_cell = sheet.getCellByPosition(col, dst_row)
        dst_cell.CellStyle = src_cell.CellStyle
        # Fond : CellBackColor d'abord, puis IsCellBackgroundTransparent pour écraser
        dst_cell.CellBackColor = src_cell.CellBackColor
        dst_cell.IsCellBackgroundTransparent = src_cell.IsCellBackgroundTransparent
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
        # Fond : CellBackColor d'abord, puis IsCellBackgroundTransparent pour écraser
        dst_cell.CellBackColor = src_cell.CellBackColor
        dst_cell.IsCellBackgroundTransparent = src_cell.IsCellBackgroundTransparent
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


def _parse_cell_ref(cell_ref):
    """Parse 'A3' ou 'A$3' ou '$A$3' → (col_0indexed, row_0indexed)."""
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
        return None
    return col, row


def get_col_range_bounds(xdoc, name):
    """Retourne (sheet_name, col_0indexed, start_row_1indexed, end_row_1indexed).

    Pour un named range colonne comme AVRintitulé = $Avoirs.$A$4:$A$80.
    Retourne None si le nom n'existe pas ou est une cellule unique.
    """
    nr = xdoc.NamedRanges
    if not nr.hasByName(name):
        return None
    content = nr.getByName(name).Content  # e.g. "$Avoirs.$A$4:$A$80"
    if ':' not in content:
        return None
    left, right = content.split(':')
    left = left.lstrip('$')
    parts = left.split('.$')
    sheet_name = parts[0]
    start_ref = parts[1] if len(parts) > 1 else parts[0]
    start = _parse_cell_ref(start_ref)
    end = _parse_cell_ref(right)
    if not start or not end:
        return None
    return sheet_name, start[0], start[1] + 1, end[1] + 1  # 1-indexed


def col_of(xdoc, name):
    """Retourne la colonne (0-indexed) d'un named range colonne.

    Résout dynamiquement depuis le classeur — résiste aux insertions/suppressions
    de colonnes puisque LO recale automatiquement les named ranges.

    Usage:
        col = col_of(xdoc, 'PATlabel')
        ws.getCellByPosition(col, r0)
    """
    bounds = get_col_range_bounds(xdoc, name)
    return bounds[1] if bounds else None


def letter_of(xdoc, name):
    """Retourne la lettre de colonne d'un named range colonne.

    Usage pour les formules Excel :
        letter = letter_of(xdoc, 'PATlabel')
        cell.setFormula(f'=SUM({letter}{start}:{letter}{end})')
    """
    c = col_of(xdoc, name)
    if c is None:
        return None
    # 0-indexed → lettre (A=0, B=1, ..., Z=25, AA=26, ...)
    result = ''
    n = c + 1  # 1-indexed
    while n > 0:
        n, rem = divmod(n - 1, 26)
        result = chr(65 + rem) + result
    return result


# ━━━ Helpers Conditional Format ━━━
#
# Les classeurs Compta utilisent 2 patterns de CF d'alarme :
#   1. Token ✗/⚠ (cellules de synthèse) : 2 conditions FIND("✗") puis FIND("⚠")
#      avec styles ConditionalStyle_2 (rouge) / ConditionalStyle_3 (orange).
#   2. ISERROR (pieds montants surveillés) : 1 condition ISERROR(self) avec
#      style ConditionalStyle_2 (rouge) — colore la cellule si formule plante.
#
# Les styles ConditionalStyle_2/3 sont créés par les CF d'origine du témoin
# (mappés par LO depuis dxfId 1/2 du xlsm). Les helpers ci-dessous les réutilisent.
#
# Note séparateur : UNO veut ; (PAS , — sinon Err 509). Openpyxl relit en virgules
# à l'écriture xlsx, c'est attendu.

CF_STYLE_ERROR = 'ConditionalStyle_2'
CF_STYLE_WARN = 'ConditionalStyle_3'
CF_FORMULA_ERROR = 'NOT(ISERROR(FIND("✗";INDIRECT("RC";0))))'
CF_FORMULA_WARN = 'NOT(ISERROR(FIND("⚠";INDIRECT("RC";0))))'
CF_FORMULA_ISERROR = 'ISERROR(INDIRECT("RC";0))'


def _make_cf_prop(name, value):
    """Construit un PropertyValue UNO pour addNew sur ConditionalFormat."""
    pv = uno.createUnoStruct('com.sun.star.beans.PropertyValue')
    pv.Name = name
    pv.Value = value
    return pv


def has_alarm_cf(cell):
    """Vrai si la cellule porte les 2 conditions FIND("✗") et FIND("⚠")."""
    cf = cell.ConditionalFormat
    if cf.Count < 2:
        return False
    has_x = False
    has_w = False
    for i in range(cf.Count):
        f = cf.getByIndex(i).Formula1
        if '"✗"' in f and 'FIND' in f:
            has_x = True
        if '"⚠"' in f and 'FIND' in f:
            has_w = True
    return has_x and has_w


def has_iserror_cf(cell):
    """Vrai si la cellule porte la CF ISERROR(INDIRECT("RC";0))."""
    cf = cell.ConditionalFormat
    for i in range(cf.Count):
        f = cf.getByIndex(i).Formula1
        if 'ISERROR' in f and 'INDIRECT' in f and 'FIND' not in f:
            return True
    return False


def set_alarm_cf(cell):
    """(Re)pose les 2 CF d'alarme ✗/⚠. clear() préalable.

    Utiliser après check has_alarm_cf() pour idempotence, ou sur cellule
    connue sans autre CF (le clear() supprime tout).
    """
    from com.sun.star.sheet.ConditionOperator import FORMULA
    cf = cell.ConditionalFormat
    cf.clear()
    cf.addNew((
        _make_cf_prop('Operator', FORMULA),
        _make_cf_prop('Formula1', CF_FORMULA_ERROR),
        _make_cf_prop('StyleName', CF_STYLE_ERROR),
    ))
    cf.addNew((
        _make_cf_prop('Operator', FORMULA),
        _make_cf_prop('Formula1', CF_FORMULA_WARN),
        _make_cf_prop('StyleName', CF_STYLE_WARN),
    ))
    cell.ConditionalFormat = cf


def set_iserror_cf(cell):
    """Pose une CF qui colore la cellule en rouge si la formule plante.

    Pieds montants surveillés (E{GT}/E3 PVL, L{Total}/L2 AVR) : si la SUM/
    SUMPRODUCT propage une erreur (#N/A, #REF!, #DIV/0!, #VALUE!), la
    cellule s'allume directement, complétant la synthèse via B3/L1.

    clear() préalable. Utiliser après check has_iserror_cf() pour idempotence.
    """
    from com.sun.star.sheet.ConditionOperator import FORMULA
    cf = cell.ConditionalFormat
    cf.clear()
    cf.addNew((
        _make_cf_prop('Operator', FORMULA),
        _make_cf_prop('Formula1', CF_FORMULA_ISERROR),
        _make_cf_prop('StyleName', CF_STYLE_ERROR),
    ))
    cell.ConditionalFormat = cf


def has_nonzero_cf(cell):
    """Vrai si la cellule porte une CF cellIs NOT_EQUAL 0 (style rouge)."""
    from com.sun.star.sheet.ConditionOperator import NOT_EQUAL
    cf = cell.ConditionalFormat
    for i in range(cf.Count):
        e = cf.getByIndex(i)
        try:
            if e.Operator == NOT_EQUAL and e.Formula1 == '0':
                return True
        except Exception:
            pass
    return False


def set_nonzero_cf(cell):
    """Pose une CF qui colore la cellule en rouge si elle est différente de 0.

    Pattern « cellIs notEqual 0 » répandu dans les classeurs Compta pour les
    pieds compteurs d'écart (Patrimoine!D{Erreurs}, Budget pieds POSTES/CAT).

    clear() préalable. Utiliser après check has_nonzero_cf() pour idempotence.
    """
    from com.sun.star.sheet.ConditionOperator import NOT_EQUAL
    cf = cell.ConditionalFormat
    cf.clear()
    cf.addNew((
        _make_cf_prop('Operator', NOT_EQUAL),
        _make_cf_prop('Formula1', '0'),
        _make_cf_prop('StyleName', CF_STYLE_ERROR),
    ))
    cell.ConditionalFormat = cf


def _cleanup_drill_dxf_borders(xlsm_path, logger=None):
    """Retire les <border> vides des dxfs (xl/styles.xml).

    Effet de bord LO : à la sérialisation des cell styles Drill_* utilisés par
    les CF devise, LO ajoute systématiquement un bloc <border><left/>... vide.
    Appliqué via CF, ce bloc efface les bordures de la cellule sous-jacente —
    notamment la BORDURE_PIED thick top de la 1re ligne pied (ex. F26 Total).

    Idempotent : ne fait rien si aucun dxf concerné. Scope strict au bloc
    <dxfs>...</dxfs> (sinon casse border 0 du bloc <borders> — toutes les
    cellules glissent d'un cran dans l'index).
    """
    import zipfile
    import shutil
    import re

    TARGET = ('<border diagonalUp="false" diagonalDown="false">'
              '<left/><right/><top/><bottom/><diagonal/></border>')

    xlsm_path = Path(xlsm_path)
    tmp = xlsm_path.with_suffix(xlsm_path.suffix + '.tmp')

    n = 0
    with zipfile.ZipFile(xlsm_path, 'r') as zin:
        with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                data = zin.read(item.filename)
                if item.filename == 'xl/styles.xml':
                    xml = data.decode('utf-8')
                    m = re.search(r'<dxfs[^>]*>.*?</dxfs>', xml, re.DOTALL)
                    if m:
                        block = m.group(0)
                        n = block.count(TARGET)
                        if n:
                            new_block = block.replace(TARGET, '')
                            xml = xml[:m.start()] + new_block + xml[m.end():]
                            data = xml.encode('utf-8')
                zout.writestr(item, data)

    shutil.move(str(tmp), str(xlsm_path))
    if n and logger:
        logger.info(f'  XML post-cleanup : {n} bordure(s) vide(s) retirée(s) des dxfs drill')


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
        self._cr = None
        self._was_saved = False

    @property
    def cr(self):
        """ColResolver lazy — construit une seule fois, réutilisé ensuite."""
        if self._cr is None:
            from inc_excel_schema import ColResolver
            self._cr = ColResolver.from_uno(self._document)
        return self._cr

    @cr.setter
    def cr(self, value):
        self._cr = value

    def _log(self, msg):
        if self._logger:
            self._logger.info(msg)

    def __enter__(self):
        if not HAS_UNO:
            raise ImportError(_uno_unavailable_msg())

        # Démarrer soffice
        self._process = subprocess.Popen(
            [_soffice_path(), '--headless',
             '--accept=socket,host=localhost,port=2002;urp;',
             '--nofirststartwizard'],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        # Attente initiale : Linux ~3s, macOS ~4-8s au premier lancement
        time.sleep(3)

        # Connexion avec retry (12 tentatives × 1s = jusqu'à ~15s total)
        localContext = uno.getComponentContext()
        resolver = localContext.ServiceManager.createInstanceWithContext(
            "com.sun.star.bridge.UnoUrlResolver", localContext)

        ctx = None
        max_attempts = 12
        for attempt in range(max_attempts):
            try:
                ctx = resolver.resolve(
                    "uno:socket,host=localhost,port=2002;urp;StarOffice.ComponentContext")
                break
            except Exception:
                if attempt < max_attempts - 1:
                    time.sleep(1)
                else:
                    # Aucune connexion après ~15s : le soffice qu'on a lancé n'a pas
                    # ouvert le port 2002. Cause la plus fréquente = un LibreOffice
                    # DÉJÀ ouvert (mono-instance par profil → notre --accept ne bind
                    # pas). Tuer NOTRE process (sinon il fuit en zombie --headless),
                    # puis lever un message actionnable au lieu du NoConnectException
                    # brut. Couvre le cas « LO ouvert sur un autre document » que le
                    # garde _classeur_busy (verrou du .xlsm) ne détecte pas.
                    if self._process is not None:
                        self._process.terminate()
                        self._process = None
                    raise RuntimeError(
                        "Impossible de contacter LibreOffice via UNO (port 2002 non "
                        "ouvert après ~15s). Un LibreOffice est-il déjà ouvert ? "
                        "Ferme-le entièrement, puis relance.") from None

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
        # macOS UNIQUEMENT, quand le soffice nous appartient : fermeture NON
        # INTERACTIVE par KILL du process, SANS close/terminate UNO gracieux. Sur
        # macOS, ces appels déclenchent une modale « Enregistrer le document ? »
        # (ExecuteQuerySaveDocument) INVISIBLE qui BLOQUE indéfiniment le thread
        # principal de soffice (le doc vient d'être modifié, et --headless ne la
        # supprime pas au close) → daemon GUI figé sur « écriture en cours » (ex.
        # création de poste budgétaire). Le store a déjà eu lieu côté caller
        # (_uno_finalize/save) → le doc en mémoire meurt proprement avec le process.
        # Linux N'EST PAS concerné (--headless y supprime la modale) → on y garde le
        # teardown gracieux d'origine, qui libère proprement port 2002 / lock file
        # (dont dépendent les gardes du chemin in-process Linux).
        if self._process is not None and sys.platform == 'darwin':
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait()
            # Lock résiduel éventuel (arrêt abrupt sans fermeture gracieuse).
            try:
                lock = self._file_path.parent / f".~lock.{self._file_path.name}#"
                if lock.exists():
                    lock.unlink()
            except Exception:
                pass
        else:
            # Linux, ou soffice externe → fermeture gracieuse (comportement d'origine).
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
        # Post-process xlsm si sauvegardé : retire les <border> vides des dxfs
        # (effet de bord LO sur cell styles Drill_*, écrase BORDURE_PIED top).
        if self._was_saved and exc_type is None:
            try:
                _cleanup_drill_dxf_borders(self._file_path, self._logger)
            except Exception as e:
                if self._logger:
                    self._logger.warning(f"cleanup dxf borders failed: {e}")
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
        self._was_saved = True

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
