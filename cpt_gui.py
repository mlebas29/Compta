#!/usr/bin/env python3
"""
GUI Tkinter pour la comptabilité : exécution, configuration, comptes et catégories.

Usage:
    python3 cpt_gui.py
    python3 cpt_gui.py --config /chemin/vers/config.ini
    python3 cpt_gui.py --xlsx /chemin/vers/comptes.xlsm

Cinq onglets :
  - Exécution : lancement collecte/import, outils système
  - Sites : liste des sites activés/désactivés + détails par site
  - Comptes : visualisation/édition de la feuille Avoirs de comptes.xlsm
  - Catégories : édition des patterns config_category_mappings.json
  - Paramètres : sections general, pairing, comparison de config.ini
"""

import json
import os
import queue
import re
import shutil
from datetime import datetime, timedelta
import signal
import subprocess
import sys
import threading
import tkinter as tk
try:
    from inotify_simple import INotify, flags as iflags
    HAS_INOTIFY = True
except ImportError:
    HAS_INOTIFY = False
from copy import copy
from tkinter import ttk, messagebox
from pathlib import Path

import openpyxl
from openpyxl.styles import PatternFill

import inc_mode
import json

with open(Path(__file__).parent / 'config_gui_help.json', encoding='utf-8') as _f:
    FRAME_HELP = json.load(_f)
from inc_excel_schema import (
    SHEET_AVOIRS, SHEET_CONTROLES, SHEET_BUDGET, SHEET_OPERATIONS, SHEET_COTATIONS,
    SHEET_PLUS_VALUE,
    DEVISE_SOURCES,
)

# ============================================================================
# CHEMINS PAR DÉFAUT
# ============================================================================

SCRIPT_DIR = Path(__file__).parent
DEFAULT_CONFIG = SCRIPT_DIR / 'config.ini'
DEFAULT_JSON = SCRIPT_DIR / 'config_category_mappings.json'
DEFAULT_ACCOUNTS = SCRIPT_DIR / 'config_accounts.json'


# ============================================================================
# LECTURE / ÉCRITURE CONFIG.INI (préserve commentaires et structure)
# ============================================================================

def read_config_raw(path):
    """Lit config.ini et retourne le texte brut + un dict structuré des valeurs."""
    import configparser
    with open(path, 'r', encoding='utf-8') as f:
        raw = f.read()
    cfg = configparser.ConfigParser()
    cfg.optionxform = str  # préserve la casse
    cfg.read(path, encoding='utf-8')
    return raw, cfg


def write_config_value(raw_text, key, new_value):
    """Remplace la valeur d'une clé dans le texte brut config.ini."""
    pattern = rf'^({re.escape(key)}\s*=\s*).*$'
    return re.sub(pattern, rf'\g<1>{new_value}', raw_text, flags=re.MULTILINE)


def _insert_key_in_section(raw_text, section, key, value):
    """Insère une nouvelle clé=valeur à la fin d'une section."""
    lines = raw_text.split('\n')
    section_header = f'[{section}]'
    section_line = None
    for i, line in enumerate(lines):
        if line.strip() == section_header:
            section_line = i
            break
    if section_line is None:
        return raw_text
    # Trouver la dernière ligne de contenu de cette section
    last_content_line = section_line
    for i in range(section_line + 1, len(lines)):
        stripped = lines[i].strip()
        if re.match(r'^\[.+\]', stripped):
            break
        if stripped and not stripped.startswith('#'):
            last_content_line = i
    lines.insert(last_content_line + 1, f'{key} = {value}')
    return '\n'.join(lines)



def write_config_section_key(raw_text, section, key, new_value):
    """Remplace la valeur d'une clé dans une section spécifique (évite les doublons inter-sections).
    Retourne le texte modifié, ou None si la clé n'existe pas dans la section."""
    lines = raw_text.split('\n')
    in_section = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped == f'[{section}]':
            in_section = True
            continue
        if in_section and re.match(r'^\[.+\]', stripped):
            break
        if in_section and re.match(rf'^{re.escape(key)}\s*=', stripped):
            lines[i] = f'{key} = {new_value}'
            return '\n'.join(lines)
    return None


# ============================================================================
# LECTURE / ÉCRITURE CATEGORY_MAPPINGS.JSON
# ============================================================================

def read_mappings_json(path):
    """Lit config_category_mappings.json. Retourne {} si absent."""
    if not Path(path).exists():
        return {}
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def write_mappings_json(path, data):
    """Écrit config_category_mappings.json avec indentation lisible."""
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write('\n')


# ============================================================================
# LECTURE / ÉCRITURE CONFIG_ACCOUNTS.JSON
# ============================================================================

def read_accounts_json(path):
    """Lit config_accounts.json et retourne la structure complète."""
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def write_accounts_json(path, data):
    """Écrit config_accounts.json avec indentation lisible."""
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write('\n')


def accounts_to_site_map(accounts_data):
    """Dérive le dict plat {nom_compte: site} depuis config_accounts.json."""
    site_map = {}
    for site, site_data in accounts_data.items():
        for acct in site_data.get('accounts', []):
            site_map[acct['name']] = site
    return site_map


def site_map_to_accounts(site_map, existing_accounts=None):
    """Reconstruit config_accounts.json depuis un dict plat {nom: site}.

    Préserve les champs enrichis (numero, id_technique, etc.) de existing_accounts.
    """
    # Indexer les comptes existants par nom pour préserver les métadonnées
    existing_by_name = {}
    if existing_accounts:
        for site, site_data in existing_accounts.items():
            for acct in site_data.get('accounts', []):
                existing_by_name[acct['name']] = (site, acct)

    # Regrouper par site
    by_site = {}
    for name, site in site_map.items():
        if site not in by_site:
            by_site[site] = {'accounts': []}
        # Réutiliser l'objet enrichi existant ou créer un minimal
        if name in existing_by_name:
            _, acct = existing_by_name[name]
            by_site[site]['accounts'].append(acct)
        else:
            by_site[site]['accounts'].append({'name': name})

    # Préserver les champs non-accounts (ex: métadonnées site-specific futures)
    if existing_accounts:
        for site, site_data in existing_accounts.items():
            if site in by_site:
                for key, value in site_data.items():
                    if key != 'accounts':
                        by_site[site][key] = value

    return by_site


# ============================================================================
# LECTURE / ÉCRITURE CONFIG_COTATIONS.JSON
# ============================================================================

def read_cotations_json(path):
    """Lit config_cotations.json → dict {code: {famille, source1, source2}}."""
    if not Path(path).exists():
        return {}
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def write_cotations_json(path, data):
    """Écrit config_cotations.json avec indentation lisible."""
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write('\n')


# ============================================================================
# APPLICATION PRINCIPALE
# ============================================================================

from gui_accounts import AccountsMixin
from gui_budget import BudgetMixin
from gui_categories import CategoriesMixin
from gui_devises import DevisesMixin
from gui_exec import ExecMixin
from gui_params import ParamsMixin
from gui_sites import SitesMixin


class ConfigGUI(AccountsMixin, BudgetMixin, CategoriesMixin, DevisesMixin,
                ExecMixin, ParamsMixin, SitesMixin):
    def __init__(self, config_path, json_path, xlsx_path=None):
        self.config_path = Path(config_path)
        self.json_path = Path(json_path)
        self.xlsx_path = Path(xlsx_path) if xlsx_path else None

        # Charger les données
        self.config_raw, self.config = read_config_raw(self.config_path)
        self.mappings = read_mappings_json(self.json_path)

        # Détecter le mode depuis config.ini
        self.mode = inc_mode.get_mode(config_path=self.config_path)

        # Couleurs selon le mode
        _MODE_THEMES = {
            'prod':   ('PROD',   '#b91c1c', '#ffffff', '#fef2f2', 'cpt_gui_prod'),
            'export': ('EX',     '#ca8a04', '#ffffff', '#fefce8', 'cpt_gui_export'),
            'dev':    ('DEV',    '#1d4ed8', '#ffffff', '#eff6ff', 'cpt_gui'),
        }
        label, bg, fg, accent, wm_class = _MODE_THEMES.get(self.mode, _MODE_THEMES['dev'])
        self._mode_label = label
        self._mode_bg = bg
        self._mode_fg = fg
        self._mode_accent = accent
        self.root = tk.Tk(className=wm_class)
        from inc_excel_schema import APP_VERSION
        self.root.title(f'Comptabilité v{APP_VERSION} [{self._mode_label}]')
        self.root.geometry('1100x880')
        self.root.minsize(900, 600)
        self.root.report_callback_exception = self._handle_tk_exception

        # Icône fenêtre et barre des tâches (bleu=test, rouge=prod, jaune=export)
        _ICON_NAMES = {'prod': 'cpt_gui_prod.png', 'export': 'cpt_gui_export.png'}
        icon_name = _ICON_NAMES.get(self.mode, 'cpt_gui.png')
        icon_path = Path(__file__).parent / icon_name
        if icon_path.exists():
            self._icon_img = tk.PhotoImage(file=str(icon_path))
            self.root.iconphoto(True, self._icon_img)

        # Police plus grande pour meilleur contraste
        default_font = ('', 11)
        self.root.option_add('*Font', default_font)
        self.root.option_add('*TCombobox*Listbox.font', default_font)

        # Style ttk — contraste amélioré
        style = ttk.Style()
        style.configure('TLabel', font=default_font)
        style.configure('TButton', font=default_font, padding=4)
        style.configure('TCheckbutton', font=default_font)
        style.configure('TNotebook.Tab', font=('', 11, 'bold'), padding=(12, 6))
        style.configure('TLabelframe.Label', font=('', 11, 'bold'))
        style.configure('Treeview', font=default_font, rowheight=26)
        style.configure('Treeview.Heading', font=('', 11, 'bold'))
        style.configure('Hint.TLabel', font=('', 9), foreground='#666')
        style.configure('StatusOK.TLabel', font=('', 9, 'bold'), foreground='#16a34a')
        style.configure('StatusWarn.TLabel', font=('', 9, 'bold'), foreground='#b45309')
        style.configure('StatusError.TLabel', font=('', 9, 'bold'), foreground='#dc2626')
        style.configure('Mode.TLabel', font=('', 12, 'bold'),
                        background=self._mode_bg, foreground=self._mode_fg)
        style.configure('SiteOn.TCheckbutton', font=('', 11, 'bold'),
                        foreground='#16a34a')
        style.configure('SiteOff.TCheckbutton', font=('', 11, 'bold'),
                        foreground='#dc2626')

        # Bandeau mode PROD/TEST
        mode_banner = tk.Frame(self.root, bg=self._mode_bg, height=32)
        mode_banner.pack(fill='x')
        mode_banner.pack_propagate(False)
        display_path = str(self.config_path.parent).replace(str(Path.home()), '~', 1)
        tk.Label(mode_banner, text=f'  Mode {self._mode_label}  \u2014  {display_path}',
                 bg=self._mode_bg, fg=self._mode_fg,
                 font=('', 11, 'bold'), anchor='w').pack(side='left', padx=8)

        # Variables Tk
        self.tk_vars = {}
        self.site_vars = {}

        # Descriptions par site : défauts (config_descriptions_default.json) + overrides utilisateur
        self.desc_default_path = self.config_path.parent / 'config_descriptions_default.json'
        self.desc_path = self.config_path.parent / 'config_descriptions.json'
        self.site_descriptions_default = self._load_json(self.desc_default_path)
        self.site_descriptions = self._load_descriptions()

        # Mapping compte → site (persisté dans config_accounts.json)
        self.accounts_json_path = self.config_path.parent / 'config_accounts.json'
        self.accounts_json_data = self._load_accounts_json()
        self.account_site_map = accounts_to_site_map(self.accounts_json_data)

        # Métadonnées cotations (persistées dans config_cotations.json)
        self.cotations_json_path = self.config_path.parent / 'config_cotations.json'
        self.cotations_meta = read_cotations_json(self.cotations_json_path)

        # Pipeline config (linked_operations, solde_auto)
        self.pipeline_json_path = self.config_path.parent / 'config_pipeline.json'

        # Charger les données comptes.xlsm si disponible
        self.accounts_data = []
        self.budget_categories = []  # catégories depuis Budget col L
        self.budget_cat_rows = {}    # nom → ligne Excel (1-indexed)
        self.budget_total_row = None # ligne "Total" (1-indexed)
        self.budget_insert_row = None # ligne d'insertion (séparateur "-")
        self.budget_posts = []       # postes budgétaires depuis Budget col A
        self.budget_post_rows = {}   # nom → ligne Excel (1-indexed)
        self.budget_post_types = {}  # nom → "Fixe"|"Variable"
        self.budget_posts_total_row = None  # ligne "Total = épargne"
        self._deleted_accounts = []  # noms des comptes supprimés (purge complète Opérations+Avoirs)
        self._soft_deleted_accounts = []  # noms des comptes à purge partielle (ops non appariées)
        self._deleted_ctrl_rows = []  # ctrl_row des comptes supprimés
        self._last_sweep_count = 0  # lignes balayées dans "Compte clos" (paires orphelines)
        self._excel_loaded = False

        # Tous les sites (config sections hors general/pairing/comparison/paths/sites)
        config_sections = ['general', 'pairing', 'comparison', 'paths', 'sites']
        self.all_sites = [s for s in self.config.sections()
                          if s not in config_sections]

        # État exécution subprocess
        self._exec_process = None
        self._exec_queue = queue.Queue()
        self._active_tooltip = None
        self._pending_help_buttons = []
        self.root.protocol('WM_DELETE_WINDOW', self._on_close)

        # Notebook (onglets)
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill='both', expand=True, padx=8, pady=(4, 8))

        # Construction lazy des onglets : seul l'onglet visible est construit
        # immédiatement, les autres sont construits au premier affichage
        self._build_tab_execution()
        self._install_help_buttons()

        # Onglets différés : placeholder frames, construits au premier clic
        self._deferred_tabs = {}  # tab_frame -> builder name
        for tab_name, builder, condition in [
            ('Sites', '_build_tab_sites', True),
            ('Avoirs', '_build_tab_accounts', bool(self.xlsx_path)),
            ('Catégories', '_build_tab_categories', True),
            ('Paramètres', '_build_tab_params', True),
        ]:
            if condition:
                tab = ttk.Frame(self.notebook)
                self.notebook.add(tab, text=tab_name)
                self._deferred_tabs[str(tab)] = builder

        self.notebook.bind('<<NotebookTabChanged>>', self._on_tab_changed)

        # Initialiser site_vars tôt (utilisé par l'exécution)
        enabled_str = self.config.get('sites', 'enabled', fallback='')
        enabled_list = [s.strip() for s in enabled_str.split(',') if s.strip()]
        for site in self.all_sites:
            self.site_vars[site] = tk.BooleanVar(value=site in enabled_list)

        # Barre de statut
        status_frame = ttk.Frame(self.root)
        status_frame.pack(fill='x', padx=8, pady=(0, 8))

        self._coherence_auto_fixes = []
        self._coherence_warnings = []
        self._status_details = []  # détails affichés au clic

        # Zone 1 : Statut fusionné (colorée, cliquable)
        self.status_var = tk.StringVar(value='')
        self.status_label = ttk.Label(status_frame, textvariable=self.status_var,
                                      style='Hint.TLabel', cursor='hand2')
        self.status_label.pack(side='left', padx=(5, 0))
        self.status_label.bind('<Button-1>', self._on_status_click)

        # Séparateur
        self._status_sep = ttk.Label(status_frame, text='  —  ', style='Hint.TLabel')

        # Zone 2 : Total Avoirs (neutre, non cliquable)
        self._status_total_var = tk.StringVar(value='')
        self._status_total_label = ttk.Label(status_frame,
                                             textvariable=self._status_total_var,
                                             style='Hint.TLabel')

        # Bouton ? aide statut
        help_text = FRAME_HELP.get('Statut', '')
        if help_text:
            btn = tk.Label(status_frame, text=' ? ', font=('', 9, 'bold'),
                           fg='#555', bg='#e8e8e8', cursor='hand2',
                           relief='flat', padx=2)
            btn.pack(side='right', padx=(0, 5))
            btn.bind('<Button-1>',
                     lambda e, w=btn, t=help_text: self._show_help_tooltip(w, t))

        # Lecture Contrôles A1 (synthèse) au démarrage
        if self.xlsx_path:
            self._refresh_status_bar()
            self._start_file_watcher()

        # Construction des onglets en arrière-plan (après affichage initial)
        self.root.after(100, self._build_deferred_tabs)

        # Workarounds bug Tk Linux X11 :
        # (1) clic externe (autre app) → polling focus_displayof() ferme menus
        # (2) clic interne dans la GUI hors menu → bind <Button-1> global
        # Limitation connue (cf. CLAUDE_todo #41) : ne couvre PAS les combobox
        # ttk dont le popdown garde le focus interne.
        self._popup_menus = getattr(self, '_popup_menus', [])
        self.root.after(500, self._global_focus_watch)

        def _on_internal_click(event):
            # Si le clic est sur un Menu ou un Combobox lui-même, Tk gère
            # (sélection d'item ou ouverture du dropdown).
            if isinstance(event.widget, (tk.Menu, ttk.Combobox)):
                return
            # Sinon : fermer les menus posted et les dropdowns combobox.
            for m in self._popup_menus:
                try:
                    if m.winfo_ismapped():
                        m.unpost()
                except tk.TclError:
                    pass
            self._unpost_comboboxes(self.root)
        self.root.bind('<Button-1>', _on_internal_click, add='+')

    def _unpost_comboboxes(self, widget):
        """Ferme tous les dropdowns combobox ttk encore mappés."""
        for child in widget.winfo_children():
            if isinstance(child, ttk.Combobox):
                try:
                    popdown = child.tk.call(
                        'ttk::combobox::PopdownWindow', str(child))
                    if popdown and child.tk.call(
                            'winfo', 'ismapped', popdown):
                        child.tk.call('ttk::combobox::Unpost', str(child))
                except tk.TclError:
                    pass
            self._unpost_comboboxes(child)

    def _global_focus_watch(self):
        # Eval Tcl direct au lieu de focus_displayof() : ce dernier lève
        # KeyError 'popdown' si le focus est sur le popdown listbox d'un
        # combobox (wrapper Python incapable de résoudre ce widget interne).
        try:
            focus_path = self.root.tk.eval('focus -displayof .')
            if not focus_path:
                for m in self._popup_menus:
                    try:
                        m.unpost()
                    except tk.TclError:
                        pass
        except Exception:
            pass
        try:
            self.root.after(150, self._global_focus_watch)
        except Exception:
            pass

    # ----------------------------------------------------------------
    # FILE WATCHER — rafraîchit la barre d'état sur modification externe
    # ----------------------------------------------------------------

    def _start_file_watcher(self):
        """Démarre un thread inotify surveillant comptes.xlsm."""
        self._inotify_stop = threading.Event()
        if not HAS_INOTIFY or not self.xlsx_path:
            return
        t = threading.Thread(target=self._file_watcher_loop, daemon=True)
        t.start()

    def _file_watcher_loop(self):
        """Thread inotify : surveille CLOSE_WRITE sur le xlsm et ses .bak."""
        ino = INotify()
        watch_dir = str(Path(self.xlsx_path).parent)
        ino.add_watch(watch_dir, iflags.CLOSE_WRITE | iflags.MOVED_TO)
        target_name = Path(self.xlsx_path).name
        while not self._inotify_stop.is_set():
            for event in ino.read(timeout=1000):
                if event.name == target_name:
                    self.root.after(200, self._refresh_status_bar)
        ino.close()

    def _stop_file_watcher(self):
        """Arrête le thread inotify."""
        if hasattr(self, '_inotify_stop'):
            self._inotify_stop.set()

    # Cellules des 6 contrôles individuels dans Contrôles (col K, dans l'ordre _CTRL_LABELS)
    _CTRL_CELLS = ('K63', 'K64', 'K65', 'K66', 'K67', 'K72')

    def _read_status_cells_zip(self):
        """Lecture rapide Contrôles A1 + K63..K72 + Avoirs L2 via ZIP (~9ms vs ~70ms openpyxl).

        Returns:
            tuple: (ctrl_text, total_value, tokens) — ctrl_text str (synthèse mono-char A1),
                tokens list[str] de longueur 6 (✓/✗/⚠ par contrôle, ✓ par défaut),
                total_value float|None
        """
        import zipfile
        import xml.etree.ElementTree as ET
        ns = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
        rns = 'http://schemas.openxmlformats.org/package/2006/relationships'
        ons = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'

        def _read_cell(tree, ref):
            cell = tree.find(f'.//s:sheetData/s:row/s:c[@r="{ref}"]', ns)
            if cell is None:
                return None
            v = cell.find('s:v', ns)
            val = v.text if v is not None else None
            if cell.get('t') == 's' and val:
                val = strings[int(val)]
            return val

        with zipfile.ZipFile(self.xlsx_path) as z:
            with z.open('xl/sharedStrings.xml') as f:
                strings = [(''.join(t.text or '' for t in si.findall('.//s:t', ns)))
                           for si in ET.parse(f).findall('.//s:si', ns)]
            with z.open('xl/workbook.xml') as f:
                sheets = [(s.get('name'), s.get(f'{{{ons}}}id'))
                          for s in ET.parse(f).findall('.//s:sheet', ns)]
            with z.open('xl/_rels/workbook.xml.rels') as f:
                rel_map = {r.get('Id'): r.get('Target')
                           for r in ET.parse(f).findall(f'.//{{{rns}}}Relationship')}
            sheet_targets = {}
            for name, rid in sheets:
                if name in (SHEET_CONTROLES, SHEET_AVOIRS):
                    sheet_targets[name] = 'xl/' + rel_map[rid]

            # Contrôles A1 = synthèse mono-char (=$K$74), valeur cached MAJ par LO à chaque save.
            # K63..K72 = 6 contrôles individuels (✓/✗/⚠) lus pour le détail au clic.
            # Le tree XML est parsé une seule fois.
            ctrl = ''
            tokens = ['✓'] * 6
            if SHEET_CONTROLES in sheet_targets:
                with z.open(sheet_targets[SHEET_CONTROLES]) as f:
                    tree = ET.parse(f)
                ctrl = (_read_cell(tree, 'A1') or '').strip()
                for i, ref in enumerate(self._CTRL_CELLS):
                    val = _read_cell(tree, ref)
                    if val:
                        tokens[i] = val.strip()

            # Avoirs L2 = formule Total (=L81 ou similaire), cached value
            # mise à jour par LO à chaque save. Pas besoin de miroir L1.
            total = None
            if SHEET_AVOIRS in sheet_targets:
                with z.open(sheet_targets[SHEET_AVOIRS]) as f:
                    tree = ET.parse(f)
                val = _read_cell(tree, 'L2')
                if val:
                    try:
                        total = float(val)
                    except (ValueError, TypeError):
                        pass

        return ctrl, total, tokens

    def _refresh_status_bar(self):
        """Lecture Contrôles A1 + Avoirs L2 + cohérence JSON au démarrage."""
        try:
            # Lecture rapide ZIP, fallback openpyxl si erreur
            try:
                ctrl, total, tokens = self._read_status_cells_zip()
            except Exception:
                from openpyxl import load_workbook
                wb = load_workbook(self.xlsx_path, read_only=True, data_only=True)
                ctrl, total = '', None
                tokens = ['✓'] * 6
                if SHEET_CONTROLES in wb.sheetnames:
                    ws = wb[SHEET_CONTROLES]
                    ctrl = str(ws['A1'].value or '').strip()
                    for i, ref in enumerate(self._CTRL_CELLS):
                        v = ws[ref].value
                        if v:
                            tokens[i] = str(v).strip()
                if SHEET_AVOIRS in wb.sheetnames:
                    ws = wb[SHEET_AVOIRS]
                    val = ws['L2'].value
                    if isinstance(val, (int, float)):
                        total = val
                wb.close()

            details = []
            level = 'ok'

            if ctrl and ctrl != '.' and ctrl != '✓':
                details.append(ctrl)
                if '✗' in ctrl or any(k in ctrl for k in ('COMPTES', 'CATÉGORIES', 'INCONNUS')):
                    level = 'error'
                else:
                    level = 'warn'

            # Cohérence JSON ↔ Excel
            self._coherence_auto_fixes, self._coherence_warnings = self._check_coherence()
            if self._coherence_warnings or self._coherence_auto_fixes:
                details.extend(self._coherence_warnings)
                if level == 'ok':
                    level = 'warn'

            # Stocker pour le clic
            self._status_ctrl = ctrl if ctrl and ctrl != '.' else ''
            self._status_tokens = tokens
            self._status_details = details

            # Synthèse zone 1 : A1 brut + indicateur alertes config
            status_text = ctrl or '.'
            if self._coherence_warnings:
                status_text += ' ⚙'
                if level == 'ok':
                    level = 'warn'
            self._set_status(status_text, level)

            # Zone 2 : Total Avoirs
            total_text = ''
            if total is not None:
                total_text = f'Total: {total:,.0f} €'.replace(',', ' ')
            self._status_sep.pack_forget()
            self._status_total_label.pack_forget()
            self._status_total_var.set(total_text)
            if total_text:
                self._status_sep.pack(side='left')
                self._status_total_label.pack(side='left')

        except Exception:
            pass

    def _check_schema_version(self):
        """Vérifie la version du schéma classeur (Contrôles!K2) vs l'application.

        Returns:
            str or None: message d'erreur si incompatible, None si OK.
        """
        from inc_excel_schema import SCHEMA_VERSION
        try:
            wb = openpyxl.load_workbook(self.xlsx_path, data_only=True, read_only=True)
            dn = wb.defined_names.get('SCHEMA_VERSION')
            wb.close()
        except Exception:
            return None  # pas bloquant si lecture impossible

        if dn is None:
            return (f'Classeur sans numéro de version (version {SCHEMA_VERSION} attendue).\n'
                    f'Voir Compta_upgrade.md pour la procédure de mise à niveau.')
        try:
            classeur_version = int(dn.attr_text)
        except (ValueError, TypeError):
            return (f'SCHEMA_VERSION invalide : « {dn.attr_text} » (entier attendu).\n'
                    f'Voir Compta_upgrade.md.')
        if classeur_version < SCHEMA_VERSION:
            return (f'Classeur version {classeur_version}, version {SCHEMA_VERSION} attendue.\n'
                    f'Voir Compta_upgrade.md pour la procédure de mise à niveau.')
        return None

    def _startup_check(self):
        """Check de cohérence au démarrage : charge Excel puis vérifie."""
        out = self._exec_output

        # Vérification version schéma (indépendante du chargement complet)
        version_error = self._check_schema_version()
        if version_error:
            self._coherence_auto_fixes = []
            self._coherence_warnings = [version_error]
            out.configure(state='normal')
            out.delete('1.0', 'end')
            out.insert('end', f'⚠ {version_error}\n')
            out.see('end')
            out.configure(state='disabled')
            self._set_status('VERSION', 'error')
            return

        try:
            self._ensure_excel_loaded()
            # Relire les JSON depuis le disque (ils ont pu être modifiés en externe)
            self.accounts_json_data = self._load_accounts_json()
            self.account_site_map = accounts_to_site_map(self.accounts_json_data)
            self.cotations_meta = read_cotations_json(self.cotations_json_path)
            auto_fixes, warnings = self._check_coherence()
        except Exception as e:
            import traceback
            self._coherence_auto_fixes = []
            self._coherence_warnings = [str(e)]
            out.configure(state='normal')
            out.delete('1.0', 'end')
            out.insert('end', f'❌ Erreur au check de cohérence :\n\n{traceback.format_exc()}')
            out.see('end')
            out.configure(state='disabled')
            self._set_status('ERR', 'error')
            return

        # Mettre à jour les attributs pour la status bar
        self._coherence_auto_fixes = auto_fixes
        self._coherence_warnings = warnings

        # Afficher dans la zone Résultat
        out.configure(state='normal')
        out.delete('1.0', 'end')

        if not auto_fixes and not warnings:
            out.insert('end', '✓ Cohérence vérifiée\n')
        else:
            if auto_fixes:
                out.insert('end', '=== Corrections automatiques ===\n\n')
                for line in auto_fixes:
                    out.insert('end', f'  [AUTO-FIX] {line}\n')
                out.insert('end', '\n')
            if warnings:
                out.insert('end', '=== Problèmes détectés ===\n\n')
                for line in warnings:
                    out.insert('end', f'  [ATTENTION] {line}\n')

        out.see('end')
        out.configure(state='disabled')

        # Rafraîchir la status bar avec les résultats
        if self.xlsx_path:
            self._refresh_status_bar()

    def _check_coherence(self):
        """Vérifie la cohérence entre Excel et les fichiers JSON de config.

        Returns:
            tuple(list[str], list[str]): (auto_fixes effectués, warnings à traiter)
        """
        if not self._excel_loaded:
            return [], []
        auto_fixes = []
        warnings = []
        avoirs_names = {a['intitule'] for a in self.accounts_data}
        avoirs_by_row = {a['row']: a for a in self.accounts_data}

        # --- JSON absent : détection et auto-correction ---
        if not self.accounts_json_path.exists() and self.accounts_data:
            # config_accounts.json absent mais le classeur a des comptes → reconstruire
            self._save_site_map()
            self.accounts_json_data = read_accounts_json(self.accounts_json_path)
            self.account_site_map = accounts_to_site_map(self.accounts_json_data)
            auto_fixes.append('config_accounts.json reconstruit depuis le classeur')

        mappings_path = self.config_path.parent / 'config_category_mappings.json'
        if not mappings_path.exists():
            # Auto-création d'un JSON vide (l'utilisateur enrichit via l'onglet Catégories)
            write_mappings_json(mappings_path, {})
            self.mappings = {}
            auto_fixes.append('config_category_mappings.json absent — créé vide')
            mappings = {}
        else:
            mappings = read_mappings_json(mappings_path)
            # Warning seulement si l'utilisateur a des comptes (sinon rien à
            # catégoriser — JSON vide est un état neutre, pas une incohérence).
            sites_with_accounts = {s for s in self.account_site_map.values()
                                   if s and s != 'N/A'}
            if not mappings and sites_with_accounts:
                warnings.append(
                    'Aucun pattern de catégorisation — toutes les opérations '
                    'importées seront affectées à « - ». Configure via l\'onglet Catégories.')

        if not self.cotations_meta:
            devises_non_eur = [d for d in getattr(self, 'ACCOUNT_DEVISES', []) if d != 'EUR']
            if devises_non_eur:
                warnings.append(
                    f'config_cotations.json est vide — devises sans cotation : '
                    f'{", ".join(devises_non_eur)}')

        # --- Contrôles → Avoirs : vérification formules ---
        try:
            wb_check = openpyxl.load_workbook(self.xlsx_path, data_only=False, read_only=True)
            ws_ctrl = wb_check[SHEET_CONTROLES]
            ctrl_data_start = self._start_ctrl1 + 1
            for row_idx in range(ctrl_data_start, self._end_ctrl1 + 1):
                cell_val = ws_ctrl.cell(row_idx, self.cr.col('CTRL1compte')).value
                if not cell_val:
                    continue
                cell_str = str(cell_val).strip()
                m = re.match(r"=Avoirs!\$?A(\d+)", cell_str)
                if m:
                    ref_row = int(m.group(1))
                    acct = avoirs_by_row.get(ref_row)
                    if not acct:
                        warnings.append(
                            f'Contrôles ligne {row_idx}: référence Avoirs.A{ref_row} invalide')
                elif cell_str and cell_str not in ('✓', '⚓') and cell_str not in avoirs_names:
                    warnings.append(
                        f'Contrôles ligne {row_idx}: compte « {cell_str} » absent d\'Avoirs')
            wb_check.close()
        except Exception:
            pass

        # --- Comptes Avoirs ↔ mapping sites : nettoyage auto ---
        site_map_names = set(self.account_site_map.keys())
        orphan_sites = site_map_names - avoirs_names
        if orphan_sites:
            for name in orphan_sites:
                del self.account_site_map[name]
            # Supprimer les comptes orphelins du JSON (sans reconstruire tout)
            for site_data in self.accounts_json_data.values():
                accts = site_data.get('accounts', [])
                site_data['accounts'] = [a for a in accts
                                         if a.get('name') not in orphan_sites]
            write_accounts_json(self.accounts_json_path, self.accounts_json_data)
            auto_fixes.append(
                f'config_accounts.json : {len(orphan_sites)} compte(s) orphelin(s) supprimé(s)')

        def _site_label(s):
            """Nom utilisateur du site (config.ini section name) avec fallback clé."""
            return self.config.get(s, 'name', fallback=s)

        # --- Sites activés vs comptes (warnings informatifs, sans auto-fix) ---
        # Ne PAS désactiver automatiquement : l'utilisateur peut activer un
        # site avant de créer ses comptes (préparation de la config). On
        # signale simplement les deux cas d'incohérence.
        enabled_str = self.config.get('sites', 'enabled', fallback='')
        enabled_sites = {s.strip() for s in enabled_str.split(',') if s.strip()}
        enabled_sites.discard('MANUEL')
        sites_with_accounts = set(self.account_site_map.values()) - {'N/A'}
        for s in sorted(enabled_sites - sites_with_accounts):
            warnings.append(
                f'Site « {_site_label(s)} » activé mais aucun compte associé '
                f'— pas d\'import possible')
        for s in sorted(sites_with_accounts - enabled_sites):
            if s in set(self.all_sites):
                warnings.append(
                    f'Site « {_site_label(s)} » a des comptes mais est désactivé')

        # --- Devises Avoirs sans cotation (hors EUR) ---
        devises_avoirs = {a['devise'] for a in self.accounts_data if a['devise']}
        devises_avoirs.discard('EUR')
        if self.cotations_meta:
            cotations_codes = set(self.cotations_meta.keys())
            devises_sans_cotation = devises_avoirs - cotations_codes
            for d in sorted(devises_sans_cotation):
                warnings.append(f'Devise « {d} » utilisée dans Avoirs mais absente des cotations')

        # --- Catégories Budget ↔ règles de catégorisation : warning si orphelins ---
        # Pas de purge silencieuse (la perte de patterns serait invisible) :
        # on prévient, l'utilisateur arbitre via l'onglet Catégories ou le Budget.
        if hasattr(self, 'budget_categories') and self.budget_categories:
            budget_cats = set(self.budget_categories)
            if mappings_path.exists():
                mappings = read_mappings_json(mappings_path)
                json_cats_count = {}
                for rules in mappings.values():
                    for rule in rules:
                        cat = rule.get('category', '')
                        if cat and cat != '-' and not cat.startswith('#'):
                            json_cats_count[cat] = json_cats_count.get(cat, 0) + 1
                orphan_cats = {c: n for c, n in json_cats_count.items()
                               if c not in budget_cats}
                for cat in sorted(orphan_cats):
                    n = orphan_cats[cat]
                    warnings.append(
                        f'Catégorie « {cat} » utilisée par {n} pattern(s) '
                        f'mais absente du Budget — ajouter au Budget ou '
                        f'modifier les patterns via l\'onglet Catégories')

        # --- Sites config.ini ↔ JSONs : cohérence ---
        ini_sites = set(self.all_sites)
        # Sites référencés dans config_accounts.json (hors N/A)
        map_sites = set(v for v in self.account_site_map.values() if v != 'N/A')
        for s in map_sites - ini_sites:
            # Site absent de config.ini : pas de nom convivial, on garde la clé
            warnings.append(f'Site « {s} » dans config_accounts.json mais absent de config.ini')
        # Sites sans description par défaut
        for s in ini_sites - set(self.site_descriptions_default.keys()):
            warnings.append(f'Site « {_site_label(s)} » absent de config_descriptions_default.json')

        return auto_fixes, warnings

    # 6 contrôles individuels lus dans Contrôles!K63..K67 + K72 (cf. _CTRL_CELLS).
    # A1 = =$K$74 = synthèse mono-char globale ; le détail vient de la lecture directe.
    _CTRL_LABELS = [
        'Comptes (soldes)',
        'Catégories',
        'Dates',
        'Appariements',
        'Balances',
        'Inconnus (comptes)',
    ]
    _CTRL_EXPLANATIONS = [
        'Écarts entre soldes calculés et soldes relevés',
        'Opération(s) sans catégorie connue',
        'Date hors période attendue',
        'Appariements incomplets',
        'Déséquilibre balances',
        'Compte(s) absent(s) de la feuille Avoirs',
    ]

    def _on_status_click(self, event):
        """Affiche le détail des alertes dans la zone Résultat."""
        ctrl = getattr(self, '_status_ctrl', '')
        tokens = getattr(self, '_status_tokens', ['✓'] * 6)
        coherence = getattr(self, '_coherence_warnings', [])
        auto_fixes = getattr(self, '_coherence_auto_fixes', [])
        if not ctrl and not coherence and not auto_fixes:
            return

        out = self._exec_output
        out.configure(state='normal')
        out.delete('1.0', 'end')

        # Section classeur — 6 contrôles, colonnes alignées
        if ctrl:
            out.insert('end', '=== Contrôles classeur ===\n\n')
            for i, label in enumerate(self._CTRL_LABELS):
                token = tokens[i] if i < len(tokens) else '✓'
                if token == '✗':
                    icon = '✗'
                    detail = self._CTRL_EXPLANATIONS[i]
                elif token == '⚠':
                    icon = '⚠'
                    detail = self._CTRL_EXPLANATIONS[i]
                else:
                    icon = '✓'
                    detail = 'OK'
                out.insert('end', f'  {icon}  {label:<22} {detail}\n')
            out.insert('end', '\n')

        # Section corrections automatiques
        if auto_fixes:
            out.insert('end', '=== Corrections automatiques ===\n\n')
            for line in auto_fixes:
                out.insert('end', f'  [AUTO-FIX] {line}\n')
            out.insert('end', '\n')

        # Section configuration
        if coherence:
            out.insert('end', '=== Configuration ===\n\n')
            for line in coherence:
                out.insert('end', f'  [ATTENTION] {line}\n')

        out.configure(state='disabled')
        self.notebook.select(self._tab_execution)

    _STATUS_STYLES = {
        'ok': 'StatusOK.TLabel',
        'warn': 'StatusWarn.TLabel',
        'error': 'StatusError.TLabel',
    }

    _XLSX_BTN_COLORS = {
        'warn': ('#FFEB9C', '#FFF0B3', '#000000'),     # jaune pâle, texte noir
        'error': ('#c62828', '#e53935', '#FFFFFF'),     # rouge, texte blanc
    }

    def _set_status(self, msg, level='ok'):
        """Met à jour la barre de statut avec couleur selon le niveau."""
        self.status_var.set(msg)
        self.status_label.configure(
            style=self._STATUS_STYLES.get(level, 'Hint.TLabel'))
        # Colorer le bouton comptes.xlsm seulement en cas de problème
        btn = getattr(self, '_xlsx_btn', None)
        if btn and level in self._XLSX_BTN_COLORS:
            bg, abg, fg = self._XLSX_BTN_COLORS[level]
            btn.configure(bg=bg, activebackground=abg, fg=fg, activeforeground=fg)
        elif btn:
            btn.configure(bg=self._xlsx_btn_default_bg,
                          activebackground=self._xlsx_btn_default_abg,
                          fg=self._xlsx_btn_default_fg,
                          activeforeground=self._xlsx_btn_default_afg)

    def _build_deferred_tabs(self):
        """Construit les onglets restants en arrière-plan, un par tick event-loop."""
        if not self._deferred_tabs:
            return
        try:
            self._ensure_excel_loaded()
            # Prendre le premier onglet en attente et le construire
            tab_id, builder_name = next(iter(self._deferred_tabs.items()))
            del self._deferred_tabs[tab_id]
            builder = getattr(self, builder_name)
            tab_frame = self.notebook.nametowidget(tab_id)
            builder(tab=tab_frame)
            self._install_help_buttons()
        except Exception:
            import traceback
            traceback.print_exc()
            self._deferred_tabs.clear()
        # Planifier le suivant au prochain tick (laisse le GUI respirer)
        if self._deferred_tabs:
            self.root.after_idle(self._build_deferred_tabs)
        elif self.xlsx_path:
            # Tous les onglets construits → lancer le check de cohérence
            self.root.after_idle(self._startup_check)

    def _on_tab_changed(self, event):
        """Construit un onglet différé si l'utilisateur clique avant le background."""
        tab_id = self.notebook.select()
        builder_name = self._deferred_tabs.pop(tab_id, None)
        if builder_name:
            self._ensure_excel_loaded()
            builder = getattr(self, builder_name)
            tab_frame = self.notebook.nametowidget(tab_id)
            builder(tab=tab_frame)
            self._install_help_buttons()
        # Rafraîchir la combobox Catégories à chaque sélection de cet onglet :
        # account_site_map peut avoir évolué via l'onglet Comptes.
        try:
            tab_text = self.notebook.tab(tab_id, 'text')
        except tk.TclError:
            tab_text = ''
        if tab_text == 'Catégories' and hasattr(self, '_refresh_cat_groups'):
            self._refresh_cat_groups()

    def _ensure_excel_loaded(self):
        """Charge les données Excel une seule fois, au premier besoin."""
        if not self._excel_loaded and self.xlsx_path:
            self._load_all_excel_data()
            self._excel_loaded = True

    # ----------------------------------------------------------------
    # CHARGEMENT COMPTES.XLSX (feuille Avoirs)
    # ----------------------------------------------------------------

    # Nom du named range Excel pour le cours d'une devise (convention : cours_{code})
    @staticmethod
    def cours_name(code):
        """Retourne le nom du named range cours pour une devise (None si EUR)."""
        if not code or code == 'EUR':
            return None
        return f'cours_{code}'

    # Formats numériques pour la colonne K — source unique depuis config_cotations.json
    from inc_formats import FORMATS_DEVISE as AVOIRS_K_FORMATS

    # Fond gris pour les comptes non-EUR
    NON_EUR_FILL = PatternFill(start_color='FFDCDCDC', end_color='FFDCDCDC',
                               fill_type='solid')

    ACCOUNT_DEVISES = ['EUR']  # rechargé dynamiquement depuis Avoirs

    ACCOUNT_TYPES = [
        'Portefeuilles', 'Euros', 'Devises étrangères',
        'Crypto monnaies', 'Créances', 'Dettes',
    ]

    BIEN_TYPES = ['Foncier', 'Mobilier']

    SOUS_TYPES_BASE = ['Euro', 'Foncier', 'Titres', 'Mobilier']

    # Marqueurs de section Plus_value (col A) : section_id → label
    PV_SECTION_LABELS = {
        'portefeuilles': 'Les portefeuilles',
        'métaux': 'Les métaux',
        'crypto': 'Les cryptos',
        'devises': 'Les devises',
    }

    # Mapping famille cotation → label TOTAL dans Plus_value
    PV_SECTION_TOTALS = {
        'metal': 'TOTAL métaux',
        'crypto': 'TOTAL crypto-monnaies',
        'fiat': 'TOTAL devises',
    }

    def _load_accounts_json(self):
        """Charge config_accounts.json."""
        if self.accounts_json_path.exists():
            return read_accounts_json(self.accounts_json_path)
        return {}

    def _save_site_map(self):
        """Reconstruit le mapping compte→site depuis accounts_data et l'écrit."""
        mapping = {}
        for acct in self.accounts_data:
            site = acct.get('site', '')
            if site:
                mapping[acct['intitule']] = site
        self.accounts_json_data = site_map_to_accounts(mapping, self.accounts_json_data)
        write_accounts_json(self.accounts_json_path, self.accounts_json_data)
        self.account_site_map = mapping

    def _load_all_excel_data(self):
        """Charge toutes les données Excel au démarrage (2 ouvertures au lieu de 5)."""
        wb_formula = openpyxl.load_workbook(self.xlsx_path, data_only=False)
        wb_values = openpyxl.load_workbook(self.xlsx_path, data_only=True)
        try:
            self._load_accounts_data(wb_formula, wb_values)
            self._load_budget_categories(wb_values)
            self._load_pv_titles(wb_values)
        finally:
            wb_formula.close()
            wb_values.close()

    def _load_accounts_data(self, wb_formula=None, wb_values=None):
        """Charge Avoirs (éditable) + Contrôles (sous-comptes) de comptes.xlsm."""
        close_formula = close_values = False
        if wb_formula is None:
            wb_formula = openpyxl.load_workbook(self.xlsx_path, data_only=False)
            close_formula = True
        if wb_values is None:
            wb_values = openpyxl.load_workbook(self.xlsx_path, data_only=True)
            close_values = True
        try:
            self._load_accounts_data_inner(wb_formula, wb_values)
        finally:
            if close_formula:
                wb_formula.close()
            if close_values:
                wb_values.close()

    def _load_accounts_data_inner(self, wb_formula, wb_values):
        """Charge Avoirs + Contrôles depuis les workbooks déjà ouverts."""
        # Bornes via named ranges colonnes (cr.rows retourne start/end 1-indexed)
        from inc_excel_schema import ColResolver
        self.cr = ColResolver.from_openpyxl(wb_formula)
        self._start_avr, self._end_avr = self.cr.rows('AVRintitulé')
        self._start_ctrl1, self._end_ctrl1 = self.cr.rows('CTRL1compte')
        self._start_pvl, self._end_pvl = self.cr.rows('PVLcompte')
        self._start_cot, self._end_cot = self.cr.rows('COTcode')
        self._start_op, _ = self.cr.rows('OPdate')
        self._end_op = None  # OP n'a pas de borne END fixe
        # Fallbacks
        if self._end_avr is None: self._end_avr = 200
        if self._end_ctrl1 is None: self._end_ctrl1 = 100
        if self._end_pvl is None: self._end_pvl = 200
        if self._end_cot is None: self._end_cot = 30

        # --- Avoirs : données éditables + formules ---
        ws_formula = wb_formula[SHEET_AVOIRS]

        # --- Avoirs : comptes éditables (pour sauvegarde) ---
        self.accounts_data = []
        self._accounts_total_row = None

        # Données entre start AVR+1 et end AVR, Total = end AVR+1
        avr_data_start = self._start_avr + 1
        self._accounts_total_row = (self._end_avr + 1) if self._end_avr else None
        for row_idx in range(avr_data_start, self._end_avr or avr_data_start + 200):
            cell_a = ws_formula.cell(row_idx, self.cr.col('AVRintitulé')).value
            if not cell_a or str(cell_a).strip() in ('✓', '⚓'):
                continue

            orig_name = str(cell_a).strip()
            account = {
                'row': row_idx,
                'intitule': orig_name,
                'type': str(ws_formula.cell(row_idx, self.cr.col('AVRtype')).value or '').strip(),
                'domiciliation': str(ws_formula.cell(row_idx, self.cr.col('AVRdomiciliation')).value or '').strip(),
                'sous_type': str(ws_formula.cell(row_idx, self.cr.col('AVRsous_type')).value or '').strip(),
                'devise': str(ws_formula.cell(row_idx, self.cr.col('AVRdevise')).value or '').strip(),
                'titulaire': str(ws_formula.cell(row_idx, self.cr.col('AVRtitulaire')).value or '').strip(),
                'propriete': str(ws_formula.cell(row_idx, self.cr.col('AVRpropriete')).value or '').strip(),
                'date_anter': ws_formula.cell(row_idx, self.cr.col('AVRdate_anter')).value,
                'montant_anter': ws_formula.cell(row_idx, self.cr.col('AVRmontant_anter')).value,
                'formula_j': ws_formula.cell(row_idx, self.cr.col('AVRdate_solde')).value,
                'formula_k': ws_formula.cell(row_idx, self.cr.col('AVRmontant_solde')).value,
                'formula_l': ws_formula.cell(row_idx, self.cr.col('AVRmontant_solde_euro')).value,
                'site': self.account_site_map.get(orig_name, ''),
            }

            self.accounts_data.append(account)

        avoirs_by_row = {a['row']: a for a in self.accounts_data}
        avoirs_by_name = {a['intitule']: a for a in self.accounts_data}

        # Devises : Avoirs col E + Budget header (devises avec colonne Budget)
        devises_set = {a['devise'] for a in self.accounts_data if a['devise']}
        if hasattr(self, 'budget_devises'):
            devises_set |= self.budget_devises
        devises_set.discard('')
        self.ACCOUNT_DEVISES = sorted(devises_set)

        # Sous-types : base + sous-types existants dans les données
        existing_sous_types = {a.get('sous_type', '') for a in self.accounts_data}
        self.ACCOUNT_SOUS_TYPES = sorted(
            set(self.SOUS_TYPES_BASE) | (existing_sous_types - {''})
        )

        # --- Contrôles : une ligne par (compte, sous-compte) ---
        ws_ctrl = wb_formula[SHEET_CONTROLES]
        ws_ctrl_val = wb_values[SHEET_CONTROLES]

        self.display_accounts = []
        seen_avoirs = set()  # intitulés vus dans Contrôles

        ctrl_data_start = self._start_ctrl1 + 1
        for row_idx in range(ctrl_data_start, self._end_ctrl1 + 1):
            cell_a = ws_ctrl.cell(row_idx, self.cr.col('CTRL1compte')).value
            if not cell_a or str(cell_a).strip() in ('✓', '⚓'):
                continue

            name = str(cell_a).strip()
            m = re.match(r"=Avoirs!\$?A(\d+)", name)
            if m:
                avoirs_row = int(m.group(1))
                acct = avoirs_by_row.get(avoirs_row)
                if acct:
                    name = acct['intitule']
                else:
                    continue

            if name not in avoirs_by_name:
                continue

            avoirs_acct = avoirs_by_name[name]
            seen_avoirs.add(name)
            ctrl_val = str(ws_ctrl_val.cell(row_idx, self.cr.col('CTRL1controle')).value or '').strip()

            self.display_accounts.append({
                'ctrl_row': row_idx,
                'intitule': name,
                'devise': avoirs_acct['devise'],
                'controle': ctrl_val.lower() == 'oui',
                'site': avoirs_acct['site'],
                'type': avoirs_acct['type'],
                'avoirs_ref': avoirs_acct,
            })

        # Biens matériels : pas dans Contrôles, ajout direct
        for acct in self.accounts_data:
            if acct.get('type') == 'Biens matériels' and acct['intitule'] not in seen_avoirs:
                self.display_accounts.append({
                    'ctrl_row': None,
                    'intitule': acct['intitule'],
                    'devise': acct['devise'],
                    'controle': False,
                    'site': acct.get('site', 'N/A'),
                    'type': acct['type'],
                    'avoirs_ref': acct,
                })

    def _load_pv_titles(self, wb_values=None):
        """Charge les titres de portefeuille depuis Plus_value.

        Stocke self.pv_titles = {account_name: [(title, devise, row), ...]}
        """
        self.pv_titles = {}
        if not self.xlsx_path:
            return
        close_wb = False
        if wb_values is None:
            wb_values = openpyxl.load_workbook(self.xlsx_path, data_only=True)
            close_wb = True
        try:
            ws = wb_values[SHEET_PLUS_VALUE]
            pvl_data_start = (self._start_pvl or 5) + 1
            for row_idx in range(pvl_data_start, ws.max_row + 1):
                val_a = str(ws.cell(row_idx, self.cr.col('PVLcompte')).value or '').strip()
                val_b = str(ws.cell(row_idx, self.cr.col('PVLtitre')).value or '').strip()
                if not val_a or not val_b:
                    continue
                if val_b.startswith('*') and val_b.endswith('*') and len(val_b) > 2:
                    title = val_b[1:-1]  # enlever les *
                    devise = str(ws.cell(row_idx, self.cr.col('PVLdevise')).value or '').strip()
                    self.pv_titles.setdefault(val_a, []).append(
                        (title, devise, row_idx))
            if close_wb:
                wb_values.close()
        except Exception:
            self.pv_titles = {}

    def _load_budget_categories(self, wb_values=None):
        """Charge les catégories, postes et métadonnées depuis la feuille Budget."""
        close_wb = False
        if wb_values is None:
            wb_values = openpyxl.load_workbook(self.xlsx_path, data_only=True)
            close_wb = True
        try:
            ws = wb_values[SHEET_BUDGET]

            # Résoudre les colonnes/lignes via ColResolver
            cat_col = self.cr.col('CATnom')
            cat_start_row, cat_end_row = self.cr.rows('CATnom')
            postes_start_row, postes_end_row = self.cr.rows('POSTESnom')

            # Catégories : colonne cat_col entre start CAT et end CAT
            cats = []
            cat_rows = {}
            start_row = cat_start_row
            total_row = None
            separator_row = None
            # Scanner les catégories entre start CAT et end CAT (exclus)
            scan_start = (start_row or 0) + 1
            scan_end = cat_end_row if cat_end_row else scan_start + 200
            for row_idx in range(scan_start, scan_end):
                val = ws.cell(row_idx, cat_col).value
                if not val:
                    continue
                name = str(val).strip()
                if name in ('✓', '⚓'):
                    continue
                if name == '-':
                    separator_row = row_idx
                    continue
                if name:
                    cats.append(name)
                    cat_rows[name] = row_idx
            # Total = row après end CAT (pas de scan texte)
            total_row = (cat_end_row + 1) if cat_end_row else None

            # Postes budgétaires : col A (nom), col B (type Fixe/Variable)
            posts = []
            post_rows = {}
            post_types = {}
            posts_total_row = None
            scan_start = (postes_start_row + 1) if postes_start_row else 4
            scan_end = postes_end_row or start_row or 200
            for row_idx in range(scan_start, scan_end):
                val = ws.cell(row_idx, 1).value  # col A
                if not val:
                    continue
                name_a = str(val).strip()
                if name_a in ('✓', '⚓'):
                    continue
                if name_a:
                    posts.append(name_a)
                    post_rows[name_a] = row_idx
                    type_val = ws.cell(row_idx, 2).value  # col B
                    post_types[name_a] = str(type_val).strip() if type_val else ''
            # Total postes = row après end POSTES (pas de scan texte)
            posts_total_row = (postes_end_row + 1) if postes_end_row else None

            # Détecter la première colonne devise = cat_col + 1
            first_devise_col = cat_col + 1
            # Détecter la dernière devise (scan en-tête = 2 lignes au-dessus de start CAT)
            # Compter colonnes non-vides depuis cat_col, soustraire 6 structurelles
            # Structure : CATÉGORIES(1) + devises(N) + Total(1) + Alloc%(1) + Alloc(1) + Poste(1)
            header_row = (start_row - 2) if start_row else 27
            total_cols = 0
            for col_idx in range(cat_col, cat_col + 30):
                val = ws.cell(header_row, col_idx).value
                if not val:
                    break
                total_cols += 1
            n_devises = total_cols - 5  # 5 = CATÉGORIES + Total + Alloc% + Alloc + Poste
            budget_last_devise = first_devise_col + max(0, n_devises - 1)

            # Collecter les codes devises depuis le header Budget
            budget_devises = set()
            for col_idx in range(first_devise_col, budget_last_devise + 1):
                val = ws.cell(header_row, col_idx).value
                if val and str(val).strip():
                    budget_devises.add(str(val).strip())

            # Détecter la dernière colonne devise dans Contrôles
            # CTRL2drill pointe sur la colonne EUR (première devise).
            # Le header devises est 2 lignes au-dessus de CTRL2type START.
            ctrl_last_devise = None
            ctrl2_header_row = None
            if SHEET_CONTROLES in wb_values.sheetnames:
                ws_ctrl = wb_values[SHEET_CONTROLES]
                ctrl2_s, ctrl2_e = self.cr.rows('CTRL2type')
                if ctrl2_s:
                    # v3.6 : drill CTRL2 en r1-1 (sentinelle ⚓ incluse dans NR).
                    ctrl2_header_row = ctrl2_s - 1
                else:
                    ctrl2_header_row = 61
                # Scanner depuis CTRL2drill (colonne EUR) pour la dernière devise
                eur_col = self.cr.col('CTRL2drill') if 'CTRL2drill' in self.cr._cols else None
                if eur_col:
                    for col_idx in range(eur_col, eur_col + 30):
                        val = ws_ctrl.cell(ctrl2_header_row, col_idx).value
                        if not val or not str(val).strip():
                            ctrl_last_devise = col_idx - 1
                            break
                if ctrl_last_devise is None:
                    ctrl_last_devise = 29  # fallback AC

            if close_wb:
                wb_values.close()
            self.budget_categories = cats
            self.budget_cat_rows = cat_rows
            self.budget_cat_col = cat_col
            # start_row = start CAT (model row). Les taux sont 1 ligne au-dessus.
            # Le header devises (EUR, USD...) est 2 lignes au-dessus.
            self.budget_start_row = (start_row - 1) if start_row else None  # ligne taux (START)
            self.budget_header_row = (start_row - 2) if start_row else 27   # ligne headers devises
            self.budget_total_row = total_row
            self.budget_insert_row = separator_row or total_row
            self.budget_posts = posts
            self.budget_post_rows = post_rows
            self.budget_post_types = post_types
            self.budget_posts_total_row = posts_total_row
            self.budget_first_devise_col = first_devise_col
            self.budget_last_devise_col = budget_last_devise
            self.budget_devises = budget_devises
            self.ctrl_last_devise_col = ctrl_last_devise
            self.ctrl2_header_row = ctrl2_header_row
        except Exception:
            self.budget_categories = []
            self.budget_cat_rows = {}
            self.budget_cat_col = self.cr.col('CATnom')
            self.budget_start_row = None
            self.budget_header_row = 27
            self.budget_total_row = None
            self.budget_insert_row = None
            self.budget_posts = []
            self.budget_post_rows = {}
            self.budget_post_types = {}
            self.budget_posts_total_row = None
            self.budget_first_devise_col = self.cr.col('CATnom') + 1
            self.budget_last_devise_col = self.cr.col('CATtotal_euro') - 1
            self.budget_devises = {'EUR'}
            self.ctrl_last_devise_col = 29
            self.ctrl2_header_row = 62

    # ----------------------------------------------------------------
    # LANCEMENT
    # ----------------------------------------------------------------
    def _handle_tk_exception(self, exc_type, exc_value, exc_tb):
        """Attrape les exceptions non gérées dans les callbacks Tkinter."""
        import traceback
        msg = ''.join(traceback.format_exception(exc_type, exc_value, exc_tb))
        print(msg, file=sys.stderr)
        try:
            out = self._exec_output
            out.configure(state='normal')
            out.insert('end', f'\n❌ Erreur inattendue :\n\n{msg}')
            out.see('end')
            out.configure(state='disabled')
            # Auto-bascule sur l'onglet Exécution pour rendre l'erreur visible
            try:
                self.notebook.select(self._tab_execution)
            except Exception:
                pass
        except Exception:
            pass  # zone Résultat pas encore construite
        try:
            self._set_status('ERR', 'error')
        except Exception:
            pass

    def run(self):
        self.root.mainloop()


# ============================================================================
# MAIN
# ============================================================================

def main():
    import argparse
    parser = argparse.ArgumentParser(
        description='GUI Comptabilité')
    parser.add_argument('--config', '-c', default=str(DEFAULT_CONFIG),
                        help=f'Chemin config.ini (défaut: {DEFAULT_CONFIG})')
    parser.add_argument('--json', '-j', default=str(DEFAULT_JSON),
                        help=f'Chemin config_category_mappings.json (défaut: {DEFAULT_JSON})')
    parser.add_argument('--xlsx', '-x', default=None,
                        help='Chemin comptes.xlsm (défaut: depuis config.ini [paths] comptes_file)')
    args = parser.parse_args()

    config_path = Path(args.config)
    json_path = Path(args.json)

    if not config_path.exists():
        print(f"Erreur: {config_path} introuvable", file=sys.stderr)
        sys.exit(1)
    # json_path (config_category_mappings.json) : pas d'exit si absent —
    # le check de cohérence créera un fichier vide au démarrage.

    # Résoudre le chemin xlsx
    xlsx_path = None
    if args.xlsx:
        xlsx_path = Path(args.xlsx)
    else:
        import configparser
        cfg = configparser.ConfigParser()
        cfg.optionxform = str
        cfg.read(config_path, encoding='utf-8')
        comptes_file = cfg.get('paths', 'comptes_file', fallback='./comptes.xlsm')
        xlsx_path = (config_path.parent / comptes_file).resolve()

    if xlsx_path and not xlsx_path.exists():
        print(f"Warning: {xlsx_path} introuvable, onglet Comptes désactivé",
              file=sys.stderr)
        xlsx_path = None

    app = ConfigGUI(config_path, json_path, xlsx_path)
    app.run()


if __name__ == '__main__':
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
        try:
            from tkinter import messagebox
            messagebox.showerror('Erreur fatale', traceback.format_exc())
        except Exception:
            pass
        sys.exit(1)
