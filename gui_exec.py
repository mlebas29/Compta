"""Mixin Exécution pour ConfigGUI."""

from tkinter import messagebox
from tkinter import ttk
import json
import os
import queue
import re
import signal
import subprocess
import sys
import threading
import time
import tkinter as tk
import pyperclip

from inc_uno import check_env


class ExecMixin:
    """Onglet Exécution (collecte, import, fetch)."""

    def _dropbox_file_count(self, site):
        """Suffixe « (N) » = nb de fichiers en attente dans dropbox/<dossier>."""
        dossier = self.config.get(site, 'dossier', fallback=site)
        site_dir = self._dropbox_dir / dossier
        if not site_dir.exists():
            return ''
        count = sum(1 for f in site_dir.iterdir() if f.is_file())
        return f' ({count})' if count else ''

    def _exec_enabled_sites(self):
        """Sites présents en collecte = activés (site_vars, LIVE) hors MANUEL."""
        return [s for s in self.all_sites
                if self.site_vars[s].get() and s != 'MANUEL']

    def _rebuild_exec_site_list(self):
        """(Re)construit les cases « Sites » de l'onglet collecte depuis l'état
        activé LIVE (site_vars). #107 : décocher « Actif » (onglet Sites) → le
        site disparaît de la collecte ; recocher → réapparaît. Idempotent — ne
        reconstruit que si l'ensemble activé a changé (préserve sinon la sélection
        par-run). Appelé au build et à l'entrée de l'onglet (_on_tab_changed)."""
        want = self._exec_enabled_sites()
        if set(want) == set(self._exec_site_vars):
            # Ensemble activé inchangé → ne PAS reconstruire (préserve la sélection
            # par-run), mais rafraîchir les LIBELLÉS : le nom de présentation a pu
            # changer dans l'onglet Sites (édite-et-pars) → sinon périmé ici jusqu'au
            # redémarrage (la garde de set ne voyait pas un changement de nom seul).
            for site, cb in self._exec_site_widgets.items():
                name = self.config.get(site, 'name', fallback=site)
                self._exec_site_names[site] = name
                cb.configure(text=name + self._dropbox_file_count(site))
            return
        prev = {s: v.get() for s, v in self._exec_site_vars.items()}
        for w in self._exec_sites_grid.winfo_children():
            w.destroy()
        self._exec_site_vars.clear()
        self._exec_site_widgets.clear()
        self._exec_site_names.clear()
        col = row = 0
        max_cols = 7
        for site in want:
            site_name = self.config.get(site, 'name', fallback=site)
            self._exec_site_names[site] = site_name
            var = tk.BooleanVar(value=prev.get(site, True))
            self._exec_site_vars[site] = var
            cb = ttk.Checkbutton(self._exec_sites_grid,
                                 text=site_name + self._dropbox_file_count(site),
                                 variable=var)
            cb.grid(row=row, column=col, sticky='w', padx=(0, 10), pady=1)
            self._exec_site_widgets[site] = cb
            col += 1
            if col >= max_cols:
                col, row = 0, row + 1

    def _build_tab_execution(self):
        tab = ttk.Frame(self.notebook)
        self._tab_execution = tab
        self.notebook.add(tab, text='Exécution')

        # Note : check_env() + lecture logs/daemon.err sont groupés dans
        # `_check_startup_health` (cpt_gui.py), schedulé via root.after pour
        # éviter qu'une messagebox au boot soit cachée derrière la fenêtre
        # principale pas encore mappée sur Mac.

        # Flags partagés (cases à cocher de l'onglet Paramètres) — init précoce
        # car référencés par le menu Outils construit ci-dessous.
        self._exec_all_soldes_var = tk.BooleanVar(value=False)
        self._exec_verbose_var = tk.BooleanVar(value=False)

        # Menus tk_popup à refermer si la fenêtre perd le focus système
        self._popup_menus = []

        # ── Section Collecte ──
        collect_frame = ttk.LabelFrame(tab, text='Collecte', padding=8)
        collect_frame.pack(fill='x', padx=8, pady=(8, 4))

        sites_frame = ttk.Frame(collect_frame)
        sites_frame.pack(fill='x')

        self._exec_site_vars = {}
        self._exec_site_widgets = {}   # site → widget (Checkbutton ou Label)
        self._exec_site_names = {}     # site → nom lisible
        self._dropbox_dir = (self.config_path.parent
                             / self.config.get('paths', 'dropbox',
                                               fallback='./dropbox'))

        # --- Sites (checkboxes) ---
        sites_lf = ttk.LabelFrame(sites_frame, text='Sites', padding=4)
        sites_lf.pack(side='left', fill='both', expand=True)

        # Grille reconstruite par _rebuild_exec_site_list (#107 : suit l'état
        # « Actif » des sites, rafraîchi à l'entrée de l'onglet).
        self._exec_sites_grid = ttk.Frame(sites_lf)
        self._exec_sites_grid.pack(fill='x')
        self._rebuild_exec_site_list()

        sel_frame = ttk.Frame(sites_lf)
        sel_frame.pack(pady=(4, 0))
        ttk.Button(sel_frame, text='\u2713 Tous',
                   command=lambda: [v.set(True)
                                    for v in self._exec_site_vars.values()]
                   ).pack(side='left', padx=(0, 4))
        ttk.Button(sel_frame, text='\u2717 Aucun',
                   command=lambda: [v.set(False)
                                    for v in self._exec_site_vars.values()]
                   ).pack(side='left')

        # Manqués : décoche les sites RÉUSSIS de la dernière
        # collecte, garde les ✗ et les ⚠ (un incomplet a produit des fichiers
        # mais raté une étape — il mérite d'être rejoué).
        # ⚠ N'agit QUE sur `_exec_site_vars` (sélection du lancement,
        #   transitoire). JAMAIS sur `self.site_vars`, qui est la case « Actif »
        #   de l'onglet Sites — un réglage persistant qu'une collecte n'a pas à
        #   modifier (#107).
        # Grisé tant que la dernière collecte n'a rien laissé à rejouer : son
        # état est lui-même l'information « tout est passé ».
        self._exec_missed_btn = ttk.Button(
            sel_frame, text='\u26a0 Manqués',
            command=self._exec_select_missed, state='disabled')
        self._exec_missed_btn.pack(side='left', padx=(12, 0))

        # ── Section Lancement ──
        launch_frame = ttk.LabelFrame(tab, text='Lancement', padding=8)
        launch_frame.pack(fill='x', padx=8, pady=4)

        # Boutons action (Arrêter rangé à droite de la même rangée)
        btn_frame = ttk.Frame(launch_frame)
        btn_frame.pack(fill='x')

        self._exec_buttons = []

        btn = ttk.Button(btn_frame, text='Collecte',
                         command=self._exec_fetch_only)
        btn.pack(side='left', padx=(0, 8))
        self._exec_buttons.append(btn)

        btn = ttk.Button(btn_frame, text='Import',
                         command=self._exec_import_only)
        btn.pack(side='left', padx=(0, 8))
        self._exec_buttons.append(btn)

        btn = ttk.Button(btn_frame, text='Cotations',
                         command=self._exec_cotations)
        btn.pack(side='left', padx=(0, 8))
        self._exec_buttons.append(btn)

        # Bouton Outils — Button + tk_popup (gère bien le grab Linux, contrairement
        # à Menubutton dont le menu reste posté quand la fenêtre perd le focus).
        outils_menu = tk.Menu(self.root, tearoff=0)
        # Items « classeur externe » conditionnés à sa présence en config (cloneur
        # tiers sans classeur externe : ces items disparaissent). Publier reste
        # réservé au mode PROD (le dossier qui a autorité sur le classeur).
        has_classeur = bool(self.config.get(
            'paths', 'classeur_externe',
            fallback=self.config.get('paths', 'seafile_comptes_file', fallback=None)))
        if has_classeur:
            outils_menu.add_command(label='Charger le classeur externe', command=self._exec_pull)
        if has_classeur and self.mode == 'PROD':
            outils_menu.add_command(label='Publier le classeur externe', command=self._exec_push)
        outils_menu.add_command(label='Réinitialiser...', command=self._exec_reset)
        outils_menu.add_command(label='Annuler import', command=self._exec_fallback)
        outils_menu.add_separator()
        outils_menu.add_command(label='Vérifier cohérence',
                                command=self._startup_check)
        outils_menu.add_command(label='Contrôles classeur',
                                command=self._exec_controles)
        outils_menu.add_command(label='Profil de collecte',
                                command=self._exec_profile)

        fix_menu = tk.Menu(outils_menu, tearoff=0)
        fix_menu.add_command(label='Vérifier (numériques)',
                             command=lambda: self._exec_fix_formats(False, False))
        fix_menu.add_command(label='Vérifier (complet)',
                             command=lambda: self._exec_fix_formats(False, True))
        fix_menu.add_command(label='Corriger (numériques)...',
                             command=lambda: self._exec_fix_formats(True, False))
        fix_menu.add_command(label='Corriger (complet)...',
                             command=lambda: self._exec_fix_formats(True, True))
        outils_menu.add_cascade(label='Formats', menu=fix_menu)

        outils_btn = ttk.Button(btn_frame, text='Outils ▾')

        def _popup_outils():
            x = outils_btn.winfo_rootx()
            y = outils_btn.winfo_rooty() + outils_btn.winfo_height()
            outils_menu.tk_popup(x, y)
            outils_menu.grab_release()

        outils_btn.configure(command=_popup_outils)
        outils_btn.pack(side='left')
        self._exec_buttons.append(outils_btn)
        self._popup_menus.extend([outils_menu, fix_menu])

        # Bouton Arrêter sur la même rangée, à droite (s'applique à tout)
        self._exec_stop_btn = ttk.Button(btn_frame, text='Arrêter',
                                         command=self._exec_stop,
                                         state='disabled')
        self._exec_stop_btn.pack(side='right')

        # ── Section Résultat ──
        result_frame = ttk.LabelFrame(tab, text='Résultat', padding=8)
        result_frame.pack(fill='both', expand=True, padx=8, pady=(4, 4))

        self._exec_status_var = tk.StringVar(value='\u25cf Prêt')
        self._exec_status_label = tk.Label(
            result_frame, textvariable=self._exec_status_var,
            font=('', 11, 'bold'), anchor='w', fg='#336699')
        self._exec_status_label.pack(anchor='w', fill='x')
        self._exec_status_label.update_idletasks()
        self._exec_default_bg = self._exec_status_label.cget('bg')
        self._exec_default_fg = self._exec_status_label.cget('fg')
        self._exec_2fa_flashing = False

        # ── Table vivante de la collecte ──
        # Une ligne par site ACTIF (en cours, ou en attente d'une action de
        # Marc). Bornée à 5 PAR CONSTRUCTION : `cpt_fetch.py` lance au plus
        # ThreadPoolExecutor(max_workers=4) + 1 jambe manuelle → jamais plus de
        # 5 lignes, quels que soient les 21 sites configurés. En fin de course
        # plus rien n'est actif : elle bascule alors sur les ÉCHECS, qui sont
        # ce qu'on relit à froid.
        # ⚠ Widget FRÈRE du journal, pas inséré dedans : le log défile dans sa
        #   propre boîte et ne peut ni pousser ni recouvrir la table.
        self._exec_table_frame = ttk.Frame(result_frame)
        self._exec_table = ttk.Treeview(
            self._exec_table_frame, columns=('etat', 'depuis'),
            show='tree headings', height=1, selectmode='browse')
        self._exec_table.heading('#0', text='Site', anchor='w')
        self._exec_table.heading('etat', text='État', anchor='w')
        self._exec_table.heading('depuis', text='Depuis', anchor='w')
        self._exec_table.column('#0', width=150, stretch=False, anchor='w')
        self._exec_table.column('etat', width=420, anchor='w')
        self._exec_table.column('depuis', width=90, stretch=False, anchor='w')
        self._exec_table.tag_configure('wait', background='#FFE0B2',
                                       foreground='#7A3E00')
        self._exec_table.tag_configure('fail', foreground='#CC0000')
        self._exec_table.tag_configure('part', foreground='#B35A00')
        self._exec_table.tag_configure('annul', foreground='#666666')
        self._exec_table.pack(fill='x')
        bas_table = ttk.Frame(self._exec_table_frame)
        bas_table.pack(fill='x')
        self._exec_table_summary = tk.Label(
            bas_table, text='', anchor='w', fg='#666666')
        self._exec_table_summary.pack(side='left', fill='x', expand=True)
        # Arrêter UN site sans emporter les autres. Le bouton « Arrêter » de la
        # rangée du haut fait un `killpg` sur le groupe entier : tout ou rien.
        self._exec_kill_btn = ttk.Button(
            bas_table, text='\u26d4 Arrêter ce site',
            command=self._exec_kill_selected, state='disabled')
        self._exec_kill_btn.pack(side='right')
        self._exec_table.bind('<<TreeviewSelect>>',
                              lambda e: self._exec_kill_refresh())
        # Masquée tant qu'aucune collecte ne tourne (les autres gestes —
        # import, cotations… — n'ont pas de sites).
        self._exec_sites_state = {}
        self._exec_table_active = False
        self._exec_tick_id = None

        text_frame = ttk.Frame(result_frame)
        text_frame.pack(fill='both', expand=True, pady=(4, 4))

        self._exec_output = tk.Text(text_frame, font=('monospace', 10),
                                    wrap='word', height=12)
        self._exec_output.bind('<Key>', self._exec_output_key)
        self._exec_output.bind('<Button-3>', self._exec_output_context_menu)
        if sys.platform == 'darwin':
            # macOS : right-click = Button-2 ou Ctrl+clic gauche (pas Button-3)
            self._exec_output.bind('<Button-2>', self._exec_output_context_menu)
            self._exec_output.bind('<Control-Button-1>', self._exec_output_context_menu)
        output_vsb = ttk.Scrollbar(text_frame, orient='vertical',
                                   command=self._exec_output.yview)
        self._exec_output.configure(yscrollcommand=output_vsb.set)
        self._exec_output.pack(side='left', fill='both', expand=True)
        output_vsb.pack(side='right', fill='y')

        # ── Section Fichiers ──
        files_frame = ttk.LabelFrame(tab, text='Fichiers', padding=8)
        files_frame.pack(fill='x', padx=8, pady=(0, 8))
        files_btn_frame = ttk.Frame(files_frame)
        files_btn_frame.pack(fill='x')

        self._xlsx_btn = tk.Button(files_btn_frame, text='\U0001f4ca comptes.xlsm',
                             command=self._exec_open_comptes,
                             relief='raised', bd=1,
                             font=('', 9), padx=8, pady=6)
        self._xlsx_btn.pack(side='left')
        self._xlsx_btn_default_bg = self._xlsx_btn.cget('bg')
        self._xlsx_btn_default_abg = self._xlsx_btn.cget('activebackground')
        self._xlsx_btn_default_fg = self._xlsx_btn.cget('fg')
        self._xlsx_btn_default_afg = self._xlsx_btn.cget('activeforeground')
        # Bouton Doc dédié — Button + tk_popup, extrême droite
        doc_menu = tk.Menu(self.root, tearoff=0)
        doc_menu.add_command(label="Guide d'utilisation",
                             command=lambda: self._exec_open_doc('Compta.md'))
        doc_menu.add_command(label='Guide étendu',
                             command=lambda: self._exec_open_doc('Compta_plus.md'))
        doc_menu.add_command(label='Référentiel outils',
                             command=lambda: self._exec_open_doc('Compta_tools.md'))
        doc_menu.add_command(label='Mises à niveau',
                             command=lambda: self._exec_open_doc('Compta_upgrade_assiste.md'))
        doc_menu.add_separator()
        doc_menu.add_command(label='Charte graphique',
                             command=lambda: self._exec_open_doc('Compta_charte.md'))
        doc_menu.add_command(label='Plus-value latente',
                             command=lambda: self._exec_open_doc('Compta_pvl.md'))
        doc_menu.add_separator()
        doc_menu.add_command(label='🌐 Versions',
                             command=lambda: self._exec_open_url(
                                 'https://github.com/mlebas29/Compta/blob/main/CHANGELOG.md'))

        doc_btn = ttk.Button(files_btn_frame, text='\U0001f4d6 Doc ▴')

        def _popup_doc():
            x = doc_btn.winfo_rootx()
            y = doc_btn.winfo_rooty() - doc_menu.winfo_reqheight()
            doc_menu.tk_popup(x, y)
            doc_menu.grab_release()

        doc_btn.configure(command=_popup_doc)
        doc_btn.pack(side='right', padx=(8, 0))
        self._popup_menus.append(doc_menu)

        # Pas de boutons Dropbox/Archives : ils ouvraient les dossiers racine dont les
        # sous-dossiers portent les noms internes (dropbox/SOCGEN/, …) → ré-exposeraient
        # le nom interne, qu'on masque en GUI. Le dossier de dépôt de secours est donné,
        # au nom exact, dans la procédure de secours de la description (onglet Sites).
        ttk.Button(files_btn_frame, text='Journal',
                   command=self._exec_open_journal).pack(side='right', padx=(8, 0))

        # Restaurer le verdict de la dernière collecte (survit à la fermeture
        # de Compta). En dernier : tous les widgets qu'il touche existent.
        self._exec_state_load()


    # ----------------------------------------------------------------
    # EXÉCUTION : handlers boutons
    # ----------------------------------------------------------------
    def _exec_output_key(self, event):
        """Bloque l'édition du résultat, autorise copie et sélection."""
        # Ctrl (Linux/Windows) = bit 0x4 ; Cmd (macOS) = bit 0x8 (Mod1)
        modifier_mask = 0x4 | 0x8
        if event.state & modifier_mask and event.keysym.lower() in ('c', 'a'):
            return
        return 'break'

    def _exec_output_context_menu(self, event):
        """Menu contextuel clic droit sur la zone Résultat."""
        menu = tk.Menu(self._exec_output, tearoff=0)
        menu.add_command(label='Copier', command=self._exec_output_copy)
        menu.add_command(label='Tout sélectionner', command=self._exec_output_select_all)
        menu.tk_popup(event.x_root, event.y_root)
        return 'break'  # empêcher Button-3 de désélectionner le texte

    def _exec_output_copy(self):
        """Copie la sélection (ou tout le contenu) dans le presse-papier."""
        try:
            text = self._exec_output.get('sel.first', 'sel.last')
        except tk.TclError:
            text = self._exec_output.get('1.0', 'end-1c')
        if text:
            # pyperclip cross-platform (xclip Linux / pbcopy macOS / win32 Windows) —
            # plus fiable que Tk qui perd le clipboard quand le Menu popup est détruit
            try:
                pyperclip.copy(text)
            except Exception:
                self.clipboard_clear()
                self.clipboard_append(text)
                self.update()

    def _exec_output_select_all(self):
        """Sélectionne tout le contenu de la zone Résultat."""
        self._exec_output.tag_add('sel', '1.0', 'end-1c')

    def _get_selected_sites(self):
        """Retourne la chaîne des sites fetchables cochés (séparés par virgules).

        Un site est fetchable si `cpt_fetch_<site>.py` existe en PUB
        (`script_dir/`) ou en PRV (`script_dir/custom/`).
        """
        script_dir = self.config_path.parent
        def _has_fetcher(s):
            return ((script_dir / f'cpt_fetch_{s}.py').exists()
                    or (script_dir / 'custom' / f'cpt_fetch_{s}.py').exists())
        return ','.join(s for s, var in self._exec_site_vars.items()
                        if var.get() and _has_fetcher(s))

    def _exec_fetch_only(self):
        sites = self._get_selected_sites()
        if not sites:
            messagebox.showwarning('Aucun site',
                                   'Aucun site sélectionné pour la collecte.',
                                   parent=self.root)
            return
        # Invocation directe : cpt.py route en interne via run_script vers des
        # scripts UNO (cpt_fetch_quotes, cpt_update) qui dépendent de leur
        # shebang python3-uno.
        cmd = [str(self.config_path.parent / 'cpt.py'),
               '--fetch-only', '--sites', sites]
        if self._exec_verbose_var.get():
            cmd.append('-v')
        self._exec_run(cmd, 'Collecte')

    def _exec_import_only(self):
        # cpt_update.py directement (supporte --no-pair) — shebang python3-uno.
        cmd = [str(self.config_path.parent / 'cpt_update.py')]
        if self._exec_all_soldes_var.get():
            cmd.append('--all-soldes')
        no_pair = self.tk_vars.get(('pairing', 'no_pair'))
        if no_pair and no_pair[1].get():
            cmd.append('--no-pair')
        if self._exec_verbose_var.get():
            cmd.append('-v')
        self._exec_run(cmd, 'Import')

    def _exec_cotations(self):
        cmd = [str(self.config_path.parent / 'cpt_fetch_quotes.py')]
        if self._exec_verbose_var.get():
            cmd.append('-v')
        self._exec_run(cmd, 'Cotations')

    def _exec_pull(self):
        cmd = [sys.executable, str(self.config_path.parent / 'cpt.py'), '--pull']
        self._exec_run(cmd, 'Pull classeur externe')

    def _exec_push(self):
        cmd = [sys.executable, str(self.config_path.parent / 'cpt.py'), '--push']
        self._exec_run(cmd, 'Push classeur externe')

    def _exec_reset(self):
        # Classeur externe présent → reset simple (pull + purge). Sinon → dialogue
        # template (utilisateur sans classeur externe, p.ex. cloneur tiers en mode
        # classeur).
        has_classeur = bool(self.config.get(
            'paths', 'classeur_externe',
            fallback=self.config.get('paths', 'seafile_comptes_file', fallback=None)))
        if not has_classeur:
            self._exec_reset_template_dialog()
            return

        if not messagebox.askyesno(
                'Confirmation',
                'Réinitialiser le système ?\n\n'
                'Cela va :\n'
                '- Récupérer comptes.xlsm depuis le classeur externe\n'
                '- Purger archives, dropbox et logs',
                parent=self.root):
            return
        cmd = [sys.executable, str(self.config_path.parent / 'cpt.py'),
               '--reset']
        self._exec_run(cmd, 'Réinitialisation')

    def _exec_reset_template_dialog(self):
        """Dialogue de réinitialisation sans classeur externe (template + réinstall)."""
        dlg = tk.Toplevel(self.root)
        dlg.title('Réinitialiser')
        dlg.transient(self.root)
        dlg.wait_visibility()
        dlg.grab_set()
        dlg.resizable(False, False)

        pad = {'padx': 12, 'pady': 6}

        # --- Option 1 : Template vierge ---
        frame1 = ttk.LabelFrame(dlg, text='Option 1 — Charger classeur vierge',
                                padding=8)
        frame1.pack(fill='x', **pad)

        ttk.Label(frame1, text=(
            'Remplace comptes.xlsm par le classeur vierge.\n'
            'Réinitialise les configs Avoirs/Sites.\n'
            'Purge archives, dropbox, logs et cookies.'
        ), justify='left').pack(anchor='w')

        ttk.Button(frame1, text='Charger classeur vierge',
                   command=lambda: self._exec_reset_template(dlg)
                   ).pack(anchor='e', pady=(6, 0))

        # --- Option 2 : Réinstallation complète ---
        frame2 = ttk.LabelFrame(dlg, text='Option 2 — Réinstallation complète',
                                padding=8)
        frame2.pack(fill='x', **pad)

        # URL et chemin dynamiques
        try:
            clone_url = subprocess.check_output(
                ['git', 'remote', 'get-url', 'origin'],
                cwd=str(self.config_path.parent),
                text=True).strip()
        except Exception:
            clone_url = '<url_du_repo>'
        export_dir = str(self.config_path.parent)
        instructions = (
            'Pour une réinstallation complète :\n\n'
            '1. Fermer cette application\n'
            f'2. rm -rf {export_dir}\n'
            f'3. git clone {clone_url} {export_dir}\n'
            f'4. cd {export_dir}\n'
            '5. cp comptes_template.xlsm comptes.xlsm'
        )

        text_frame = ttk.Frame(frame2)
        text_frame.pack(fill='x')
        max_line = max(len(l) for l in instructions.split('\n'))
        text_widget = tk.Text(text_frame, height=8, width=max_line + 2,
                              wrap='none', font=('monospace', 9),
                              relief='flat',
                              background=dlg.cget('background'))
        text_widget.insert('1.0', instructions)
        text_widget.config(state='disabled')
        text_widget.pack(fill='x')

        # --- Bouton Annuler ---
        ttk.Button(dlg, text='Annuler',
                   command=dlg.destroy).pack(pady=(0, 10))

        # Centrer sur la fenêtre parente
        dlg.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - dlg.winfo_width()) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - dlg.winfo_height()) // 2
        dlg.geometry(f'+{x}+{y}')

    def _exec_reset_template(self, dialog):
        """Exécute la réinitialisation template après confirmation."""
        if not messagebox.askyesno(
                'Confirmation',
                'Charger le classeur vierge ?\n\n'
                'Cette action va remplacer comptes.xlsm\n'
                'et réinitialiser les configurations.',
                parent=dialog):
            return
        dialog.destroy()
        cmd = [sys.executable, str(self.config_path.parent / 'cpt.py'),
               '--reset-template']
        self._exec_run(cmd, 'Réinitialisation template')

    def _exec_fallback(self):
        if not messagebox.askyesno(
                'Confirmation',
                'Annuler le dernier import ?\n\n'
                'Le fichier comptes.xlsm sera restauré\n'
                'depuis la dernière sauvegarde.',
                parent=self.root):
            return
        cmd = [sys.executable, str(self.config_path.parent / 'cpt.py'),
               '--fallback']
        self._exec_run(cmd, 'Annulation import')

    def _exec_controles(self):
        cmd = [str(self.config_path.parent / 'tool_controles.py')]
        if self._exec_verbose_var.get():
            cmd.append('-v')
        self._exec_run(cmd, 'Contrôles classeur')

    def _exec_profile(self):
        # Résumé par défaut (rc=0 toujours → statut « ✓ Terminé »). Le --report
        # (dérives) renvoie 1 sur dérive → s'afficherait « ❌ Erreur » ici : gardé
        # au CLI tant que ce contrat de code retour n'est pas tranché.
        cmd = [str(self.config_path.parent / 'tool_fetch_profile.py')]
        self._exec_run(cmd, 'Profil de collecte')

    def _exec_fix_formats(self, apply_changes, with_apparence):
        if apply_changes:
            extra = ' + apparence' if with_apparence else ''
            if not messagebox.askyesno(
                    'Confirmation',
                    f'Appliquer les corrections de format{extra} à comptes.xlsm ?\n\n'
                    'Le fichier sera modifié (sauvegarde .bak créée).',
                    parent=self.root):
                return
        cmd = [str(self.config_path.parent / 'tool_fix_formats.py'),
               str(self.xlsx_path)]
        if apply_changes:
            cmd.append('--apply')
        if with_apparence:
            cmd.append('--charter')
        verb = 'Corriger' if apply_changes else 'Vérifier'
        scope = 'complet' if with_apparence else 'numériques'
        self._exec_run(cmd, f'{verb} formats ({scope})')

    def _open_path(self, path):
        """Ouvre un fichier/dossier avec l'app par défaut (cross-platform).

        macOS → open ; Windows → os.startfile ; WSL → wslview (délègue à
        l'app Windows par défaut) ; Linux natif → xdg-open.
        """
        path_str = str(path)
        if sys.platform == 'darwin':
            # `open` délègue à LaunchServices ; sur un Mac sans app par défaut
            # pour le type (fréquent pour .md), il échoue (LSApplicationNotFoundErr
            # -10814) sans rien ouvrir. Repli sur TextEdit, toujours présent.
            res = subprocess.run(['open', path_str], capture_output=True)
            if res.returncode != 0:
                subprocess.Popen(['open', '-a', 'TextEdit', path_str])
        elif sys.platform == 'win32':
            os.startfile(path_str)
        elif os.environ.get('WSL_DISTRO_NAME'):
            subprocess.Popen(['wslview', path_str])
        else:
            subprocess.Popen(['xdg-open', path_str])

    def _open_with_libreoffice(self, path):
        """Ouvre un classeur en forçant LibreOffice (cross-platform).

        Le code UNO/macros de Compta est calibré pour LibreOffice ; ouvrir
        comptes.xlsm dans Excel (défaut OS sur certains Mac) casse macros,
        formules incompatibles et locks .~lock. Ce helper contourne l'app par
        défaut OS et force LibreOffice.
        """
        path_str = str(path)
        if sys.platform == 'darwin':
            subprocess.Popen(['open', '-a', 'LibreOffice', path_str])
        elif sys.platform == 'win32':
            # Sur Windows natif, soffice peut être dans le PATH si installé via
            # le setup officiel. Fallback sur startfile sinon (= défaut OS).
            try:
                subprocess.Popen(['soffice', path_str])
            except FileNotFoundError:
                os.startfile(path_str)
        else:
            subprocess.Popen(['libreoffice', path_str])

    def _exec_open_doc(self, filename):
        """Ouvre une doc Markdown du repo avec l'app par défaut."""
        path = (self.config_path.parent / filename).resolve()
        if path.exists():
            self._open_path(path)
        else:
            messagebox.showinfo(filename,
                                f'Fichier introuvable :\n{path}',
                                parent=self.root)

    def _exec_open_url(self, url):
        """Ouvre une URL dans le navigateur par défaut (cross-platform).

        Même dispatch OS que `_open_path` (WSL → wslview, qui délègue au
        navigateur Windows), sans le repli TextEdit propre aux fichiers.
        """
        if sys.platform == 'darwin':
            subprocess.Popen(['open', url])
        elif sys.platform == 'win32':
            os.startfile(url)
        elif os.environ.get('WSL_DISTRO_NAME'):
            subprocess.Popen(['wslview', url])
        else:
            subprocess.Popen(['xdg-open', url])

    def _exec_open_journal(self):
        logs_dir = self.config.get('paths', 'logs', fallback='./logs')
        journal = self.config_path.parent / logs_dir / 'journal.log'
        if journal.exists():
            self._open_path(journal)
        else:
            messagebox.showinfo('Journal',
                                f'Fichier journal introuvable :\n{journal}',
                                parent=self.root)

    def _exec_open_comptes(self):
        comptes = self.config.get('paths', 'comptes_file', fallback='./comptes.xlsm')
        path = (self.config_path.parent / comptes).resolve()
        if not path.exists():
            messagebox.showinfo('comptes.xlsm',
                                f'Fichier introuvable :\n{path}',
                                parent=self.root)
            return
        # Sur Mac, le daemon UNO peut tenir le fichier ouvert en batch
        # (lock .~lock.xlsm# + soffice). On flush (save + close batch) avant
        # de laisser LibreOffice ouvrir le fichier de manière interactive.
        # No-op si daemon jamais spawné ou inactif.
        try:
            self._daemon_flush()
        except Exception as e:
            messagebox.showerror('Erreur daemon',
                                 f'Flush daemon a échoué : {e}\n\n'
                                 'Le fichier peut être encore verrouillé.',
                                 parent=self.root)
            return
        self._open_with_libreoffice(path)

    # ----------------------------------------------------------------
    # EXÉCUTION : subprocess dans un thread
    # ----------------------------------------------------------------
    def _exec_run(self, cmd_args, label):
        """Lance un subprocess dans un thread dédié."""
        self._exec_output.configure(state='normal')
        self._exec_output.delete('1.0', 'end')

        self._exec_run_label = label
        self._exec_table_reset(label == 'Collecte')
        self._exec_status_var.set(f'\u23f3 {label} en cours...')
        self._exec_status_label.config(fg='#CC6600')

        for btn in self._exec_buttons:
            btn.config(state='disabled')
        self._exec_stop_btn.config(state='normal')

        self._exec_queue = queue.Queue()
        thread = threading.Thread(target=self._exec_worker, args=(cmd_args,),
                                  daemon=True)
        thread.start()
        self._exec_poll()

    def _exec_worker(self, cmd_args):
        """Worker thread : Popen puis lecture ligne par ligne vers la queue."""
        try:
            env = os.environ.copy()
            env['PYTHONUNBUFFERED'] = '1'
            env['COMPTA_GUI'] = '1'
            self._exec_process = subprocess.Popen(
                cmd_args,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=str(self.config_path.parent),
                bufsize=1,
                start_new_session=True,
                env=env,
            )
            while True:
                line = self._exec_process.stdout.readline()
                if not line:
                    break
                self._exec_queue.put(line)
            self._exec_process.wait()
            self._exec_queue.put(('__done__', self._exec_process.returncode))
        except Exception as e:
            self._exec_queue.put(f'Erreur: {e}\n')
            self._exec_queue.put(('__done__', 1))

    def _exec_poll(self):
        """Polling 100 ms : lit la queue et alimente le Text widget."""
        try:
            while True:
                item = self._exec_queue.get_nowait()
                if isinstance(item, tuple) and item[0] == '__done__':
                    self._exec_on_finished(item[1])
                    return
                self._exec_output.insert('end', item)
                self._exec_output.see('end')
                if self._exec_table_active:
                    self._exec_track(item)
                if '\U0001f514' in item:  # 🔔 = marqueur alert() (2FA/CAPTCHA/login)
                    self._exec_2fa_alert()
                elif (self._exec_2fa_flashing and item.strip()
                      and not self._exec_waiting_sites()):
                    self._exec_2fa_stop()
        except queue.Empty:
            pass
        self.root.after(100, self._exec_poll)

    # ----------------------------------------------------------------
    # TABLE VIVANTE DE LA COLLECTE
    # ----------------------------------------------------------------
    # Alimentée par le flux stdout de `cpt_fetch.py`, qui porte DÉJÀ tout ce
    # qu'il faut — l'orchestrateur n'a pas à changer :
    #     [SITE] HH:MM:SS → Nom (SITE)...      départ
    #     [SITE]   🔔 ...                      demande humaine
    #     [SITE]   ⏳ Attente humaine : Ns     Marc a répondu
    #     [SITE]   ✓ (Ns)   /   ✗ (…) …       fin
    # ⚠ Le préfixe `[SITE] ` n'est émis QUE si plusieurs jambes tournent
    #   (`multi` dans cpt_fetch.py) : sur une collecte mono-site il n'y en a
    #   pas → on retombe sur l'unique site vivant (`_exec_line_site`).

    # ⚠ PAS d'ancrage en fin de ligne, et on prend TOUTES les occurrences.
    #   L'orchestrateur imprime depuis plusieurs fils (jambe manuelle + 4 jambes
    #   machine) ; `print(x)` écrivant le texte PUIS le saut de ligne, un autre
    #   fil peut s'intercaler entre les deux et fusionner deux sorties en une
    #   seule ligne. Ancré sur `$`, le motif ratait alors le départ du site —
    #   eToro absent de la table le 10/09/2026 alors qu'il collectait.
    _RE_START = re.compile(r'→\s+.*?\(([A-Z0-9_]+)\)\.\.\.')
    _RE_PREFIX = re.compile(r'^\s*\[([A-Z0-9_]+)\]\s')
    _RE_OK = re.compile(r'✓\s*\((\d+)s\)')
    _RE_KO = re.compile(r'✗\s*\(([^)]*)\)\s*(.*)$')
    # ⚠ TROISIÈME issue, ni ✓ ni ✗ : le verdict nuancé de cpt_fetch.py (#194) —
    #   « le site a produit des fichiers, mais une étape a échoué ». L'ignorer
    #   laissait le site bloqué en « en cours » et hors de tout compteur
    #   (constaté 10/09/2026 : 11 ✓ + 2 ✗ pour 14 sites).
    _RE_PART = re.compile(r'⚠\s*\((\d+)s\)\s*(.*)$')
    # ✋ : site arrêté à la demande de Marc. Ni erreur, ni succès — même
    # raisonnement que le verdict nuancé ⚠ : mêler une décision à une panne
    # brouille les deux.
    _RE_ANNUL = re.compile(r'✋\s*\((\d+)s\)\s*(.*)$')
    # Le détail d'un ✗ recopie la ligne du fetcher : « HH:MM:SS cpt_fetch_X ❌
    # message ». Dans une colonne on ne veut que le message — l'horodatage et
    # le nom du logger sont déjà dans le journal juste dessous.
    _RE_BRUIT = re.compile(r'^(?:\d{2}:\d{2}:\d{2}\s+\S+\s+)?[❌⚠️✗]*\s*')

    def _exec_table_reset(self, active):
        """Nouvelle collecte → table vidée et affichée. Autre geste (import,
        cotations…) → table masquée, mais l'ÉTAT DE LA DERNIÈRE COLLECTE EST
        CONSERVÉ : un import n'invalide pas le verdict des sites, et le bouton
        « Manqués » doit y survivre."""
        self._exec_table_active = active
        if self._exec_tick_id:
            self.root.after_cancel(self._exec_tick_id)
            self._exec_tick_id = None
        if active:
            self._exec_sites_state = {}
            for iid in self._exec_table.get_children():
                self._exec_table.delete(iid)
            self._exec_missed_btn.config(state='disabled')
            self._exec_table_summary.config(text='')
            self._exec_table_frame.pack(after=self._exec_status_label,
                                        fill='x', pady=(4, 0))
            self._exec_tick()
        else:
            self._exec_table_frame.pack_forget()

    # ── Mémoire de la dernière collecte ──────────────────────────────
    # `_exec_sites_state` vit en mémoire : quitter Compta l'effaçait, et avec
    # lui le bouton « Manqués » — précisément au moment où il sert,
    # puisqu'on quitte Compta POUR aller traiter les échecs (vécu 10/09/2026).
    # Store machine-local sous `logs/` (gitignoré d'office), même idiome que
    # `logs/fetch_profiles.json`. Jetable : toute lecture qui échoue est
    # ignorée — une mémoire de confort ne doit JAMAIS empêcher la GUI d'ouvrir.

    def _exec_state_path(self):
        logs = self.config.get('paths', 'logs', fallback='./logs')
        return self.config_path.parent / logs / 'derniere_collecte.json'

    def _exec_state_save(self):
        try:
            f = self._exec_state_path()
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(json.dumps(
                {'quand': time.strftime('%d/%m %H:%M'),
                 'sites': {s: {k: v for k, v in st.items() if k != 'depuis'}
                           for s, st in self._exec_sites_state.items()}},
                ensure_ascii=False, indent=1))
        except Exception:
            pass

    def _exec_state_load(self):
        """Restaure le verdict de la dernière collecte au démarrage."""
        try:
            data = json.loads(self._exec_state_path().read_text())
            sites = data.get('sites') or {}
            if not sites:
                return
            self._exec_sites_state = {
                s: {'etat': st.get('etat', 'ok'), 'detail': st.get('detail', ''),
                    'fin': st.get('fin', ''), 'depuis': None}
                for s, st in sites.items()}
            self._exec_table_active = True
            self._exec_table_frame.pack(after=self._exec_status_label,
                                        fill='x', pady=(4, 0))
            self._exec_table_refresh()
            self._exec_missed_refresh()
            self._exec_status_var.set(
                f"\u25cf Dernière collecte \u2014 {data.get('quand', '?')}")
        except Exception:
            pass

    def _exec_cancel_dir(self):
        logs = self.config.get('paths', 'logs', fallback='./logs')
        return self.config_path.parent / logs / 'cancel'

    def _exec_kill_refresh(self):
        """Le bouton n'a de sens que sur un site EN COURS d'une collecte qui
        tourne : on n'arrête pas un site déjà terminé."""
        sel = self._exec_table.selection()
        site = sel[0] if sel else None
        st = self._exec_sites_state.get(site) if site else None
        vivant = (self._exec_process is not None
                  and st is not None and st['etat'] in ('run', 'wait'))
        self._exec_kill_btn.config(state='normal' if vivant else 'disabled')

    def _exec_kill_selected(self):
        """Dépose une demande d'annulation pour le site sélectionné.

        On n'envoie PAS de signal nous-mêmes : la GUI ne détient que le PID de
        l'orchestrateur, et tuer un petit-fils par-dessus son parent priverait
        l'échec de son chemin normal (statistiques, compte rendu, journal).
        `cpt_fetch.py` guette ce fichier à chaque seconde et tue SON enfant.
        """
        sel = self._exec_table.selection()
        if not sel:
            return
        site = sel[0]
        if not messagebox.askyesno(
                'Arrêter ce site',
                f'Arrêter la collecte de « {site} » ?\n\n'
                'Les autres sites continuent. Le site sera marqué « arrêté » '
                'et pourra être repris par le bouton Manqués.',
                parent=self.root):
            return
        try:
            d = self._exec_cancel_dir()
            d.mkdir(parents=True, exist_ok=True)
            (d / site).write_text('')
        except OSError as e:
            messagebox.showerror('Arrêt impossible',
                                 f"Impossible de déposer la demande :\n{e}",
                                 parent=self.root)
            return
        self._exec_kill_btn.config(state='disabled')
        self._exec_output.insert('end', f'  → arrêt demandé pour {site}\n')
        self._exec_output.see('end')

    def _exec_select_missed(self):
        """Ne garder cochés que les sites à rejouer (échec ou incomplet)."""
        for site, var in self._exec_site_vars.items():
            st = self._exec_sites_state.get(site)
            if st:                       # site de la dernière collecte
                var.set(st['etat'] in ('ko', 'part', 'annul'))
            # Un site ABSENT de la dernière collecte garde sa case : il n'a pas
            # été jugé, on ne décide pas pour lui.

    def _exec_missed_refresh(self):
        """Le bouton n'a de sens que s'il reste quelque chose à rejouer."""
        rejouables = any(st['etat'] in ('ko', 'part', 'annul')
                         for st in self._exec_sites_state.values())
        self._exec_missed_btn.config(
            state='normal' if rejouables else 'disabled')

    def _exec_line_site(self, line):
        """Site auquel se rapporte une ligne : préfixe `[SITE] ` s'il est là,
        sinon l'unique site encore vivant (cas mono-site, sans préfixe)."""
        m = self._RE_PREFIX.match(line)
        if m and m.group(1) in self._exec_sites_state:
            return m.group(1)
        vivants = [s for s, st in self._exec_sites_state.items()
                   if st['etat'] in ('run', 'wait')]
        return vivants[0] if len(vivants) == 1 else None

    def _exec_track(self, line):
        """Met à jour l'état des sites depuis une ligne du flux.

        ⚠ Une ligne peut en porter PLUSIEURS. L'orchestrateur imprime depuis
        plusieurs fils (jambe manuelle + 4 jambes machine) et `print(x)` écrit
        le texte PUIS le saut de ligne : un autre fil s'intercale entre les
        deux et fusionne deux sorties. On découpe donc sur les préfixes
        `[SITE] ` AVANT d'analyser — sans quoi le verdict d'un site serait
        attribué à celui dont le préfixe ouvre la ligne. Défaut constaté le
        10/09/2026 : eToro collectait sans jamais apparaître dans la table.
        """
        morceaux = [m for m in re.split(r'(?=\[[A-Z0-9_]+\]\s)', line)
                    if m.strip()]
        for morceau in (morceaux or [line]):
            self._exec_track_one(morceau)

    def _exec_track_one(self, line):
        """Analyse UN fragment homogène (un seul site)."""
        now = time.monotonic()
        for m in self._RE_START.finditer(line):
            self._exec_sites_state[m.group(1)] = {
                'etat': 'run', 'detail': 'en cours',
                'depuis': now, 'fin': None}
            self._exec_table_refresh()
            return
        site = self._exec_line_site(line)
        st = self._exec_sites_state.get(site) if site else None
        if not st:
            return
        m = self._RE_OK.search(line)
        if m:
            st.update(etat='ok', detail='terminé', fin=f'{m.group(1)} s')
            self._exec_table_refresh()
            return
        m = self._RE_ANNUL.search(line)
        if m:
            st.update(etat='annul', detail=m.group(2).strip() or 'arrêté',
                      fin=f'{m.group(1)} s')
            self._exec_table_refresh()
            return
        m = self._RE_PART.search(line)
        if m:
            st.update(etat='part', detail=m.group(2).strip() or 'collecte incomplète',
                      fin=f'{m.group(1)} s')
            self._exec_table_refresh()
            return
        m = self._RE_KO.search(line)
        if m:
            duree, reste = m.group(1).strip(), m.group(2).strip()
            reste = self._RE_BRUIT.sub('', reste).strip()
            # `✗ (timeout)` (ancienne forme) met un mot là où les autres
            # mettent une durée : ne pas l'afficher dans la colonne Depuis.
            if not re.fullmatch(r'\d+\s*s?', duree):
                reste, duree = (reste or duree), ''
            st.update(etat='ko', detail=(reste or 'échec'), fin=duree)
            self._exec_table_refresh()
            return
        if '\U0001f514' in line:                       # 🔔 : demande humaine
            st.update(etat='wait', depuis=now,
                      detail=line.split('\U0001f514', 1)[1].strip())
            self._exec_table_refresh()
            return
        if 'Attente humaine' in line:                  # ⏳ : Marc a répondu
            st.update(etat='run', detail='répondu — en cours', depuis=now)
            self._exec_table_refresh()

    def _exec_waiting_sites(self):
        """Sites qui attendent une action humaine, dans l'ordre de démarrage."""
        return [s for s, st in self._exec_sites_state.items()
                if st['etat'] == 'wait']

    @staticmethod
    def _exec_duree(t0):
        if not t0:
            return ''
        s = int(time.monotonic() - t0)
        return f'{s // 60} min {s % 60:02d}' if s >= 60 else f'{s} s'

    def _exec_table_refresh(self):
        """Reconstruit les lignes : les ACTIFS pendant la course, les ÉCHECS
        une fois tout terminé. Les deux ensembles sont petits par nature."""
        if not self._exec_table_active:
            return
        actifs = [(s, st) for s, st in self._exec_sites_state.items()
                  if st['etat'] in ('run', 'wait')]
        lignes = actifs or [(s, st) for s, st in self._exec_sites_state.items()
                            if st['etat'] in ('ko', 'part', 'annul')]
        # ⚠ MISE À JOUR DIFFÉRENTIELLE, surtout pas delete+insert. Le tic de
        #   rafraîchissement passe ici CHAQUE SECONDE (colonne « Depuis ») :
        #   reconstruire la table détruisait la sélection à chaque tour, et le
        #   bouton « Arrêter ce site » ne survivait donc pas une seconde
        #   (signalé le 10/09/2026). On ne retire que ce qui doit disparaître,
        #   on met le reste à jour en place.
        voulus = [s for s, _ in lignes]
        for iid in self._exec_table.get_children():
            if iid not in voulus:
                self._exec_table.delete(iid)
        for rang, (site, st) in enumerate(lignes):
            if st['etat'] == 'wait':
                icone, tag, depuis = '\U0001f514', 'wait', self._exec_duree(st['depuis'])
            elif st['etat'] == 'run':
                icone, tag, depuis = '▶', '', self._exec_duree(st['depuis'])
            elif st['etat'] == 'part':
                icone, tag, depuis = '⚠', 'part', st['fin'] or ''
            elif st['etat'] == 'annul':
                icone, tag, depuis = '✋', 'annul', st['fin'] or ''
            else:
                icone, tag, depuis = '✗', 'fail', st['fin'] or ''
            valeurs = (f"{icone}  {st['detail']}", depuis)
            etiquettes = (tag,) if tag else ()
            if self._exec_table.exists(site):
                self._exec_table.item(site, values=valeurs, tags=etiquettes)
                self._exec_table.move(site, '', rang)
            else:
                self._exec_table.insert('', rang, iid=site, text=f'  {site}',
                                        values=valeurs, tags=etiquettes)
        self._exec_table.config(height=max(1, min(len(lignes), 6)))

        ok = sum(1 for st in self._exec_sites_state.values() if st['etat'] == 'ok')
        ko = sum(1 for st in self._exec_sites_state.values() if st['etat'] == 'ko')
        part = sum(1 for st in self._exec_sites_state.values() if st['etat'] == 'part')
        ann = sum(1 for st in self._exec_sites_state.values() if st['etat'] == 'annul')
        parts = []
        if ok:
            parts.append(f'✓ {ok} réussi' + ('s' if ok > 1 else ''))
        if part:
            parts.append(f'⚠ {part} incomplet' + ('s' if part > 1 else ''))
        if ko:
            parts.append(f'✗ {ko} en échec')
        if ann:
            parts.append(f'✋ {ann} arrêté' + ('s' if ann > 1 else ''))
        self._exec_table_summary.config(
            text=('   ' + '  ·  '.join(parts)) if parts else '')

        # Le compteur d'attente dans la ligne de statut est le cœur du
        # dispositif : il évite d'avoir à CHERCHER si une autre demande dort.
        # Le 10/09/2026, trois 🔔 sont tombés en 7 s derrière un bandeau
        # anonyme — deux ont été manqués.
        self._exec_kill_refresh()
        att = self._exec_waiting_sites()
        if att:
            self._exec_status_var.set(
                f'\U0001f514 {len(att)} SITE' + ('S' if len(att) > 1 else '')
                + ' EN ATTENTE — ' + ', '.join(att))
        elif self._exec_2fa_flashing:
            self._exec_2fa_stop()
        elif self._exec_status_var.get().startswith('\U0001f514'):
            # Filet : `_exec_2fa_stop` sort tôt si le clignotement est déjà
            # éteint — sans ça un « N SITES EN ATTENTE » pourrait survivre à
            # la dernière réponse.
            self._exec_status_var.set(
                f'\u23f3 {self._exec_run_label} en cours...')

    def _exec_tick(self):
        """Rafraîchit les durées « Depuis » pendant la course."""
        if not self._exec_table_active:
            return
        self._exec_table_refresh()
        self._exec_tick_id = self.root.after(1000, self._exec_tick)

    def _exec_2fa_alert(self):
        """Alerte visuelle + sonore sur toute demande d'action humaine (marqueur
        \U0001f514 d'alert() : 2FA, CAPTCHA, login manuel, validation mobile\u2026)."""
        if not self._exec_table_active:
            self._exec_status_var.set('\U0001f514 Action d\'authentification requise \u2014 2FA / CAPTCHA / \u2026')
        self._exec_2fa_flashing = True
        self._exec_2fa_flash(True)
        # Auto-stop après 30 s — SEULEMENT hors collecte suivie. Quand la table
        # est active, l'alerte s'éteint sur l'ÉTAT RÉEL (plus aucun site en
        # attente), jamais sur une minuterie : le 10/09/2026, trois 🔔
        # concurrents ont cessé de signaler leur présence 30 s après, alors
        # qu'ils avaient encore 2 min 30 à courir — deux ont été manqués.
        if not self._exec_table_active:
            self.root.after(30000, self._exec_2fa_stop)
        # Attirer l'œil SANS voler les clics. `-topmost` maintenu 3 s clouait
        # Compta au-dessus de Chrome : le clic destiné au CAPTCHA atterrissait
        # sur Compta, et il en fallait un second pour revenir à Chrome (signalé
        # 10/09/2026). Poser puis retirer l'attribut dans la foulée lève la
        # fenêtre une fois, sans l'épingler — le gestionnaire de fenêtres rend
        # ensuite la main normalement.
        # ⚠ Une demande 2FA se traite le plus souvent AILLEURS (Chrome, ou le
        #   téléphone) : passer Compta devant est au mieux inutile, au pire
        #   dans le chemin. Le bandeau clignotant et la table restent le signal.
        self.root.lift()
        self.root.attributes('-topmost', True)
        self.root.attributes('-topmost', False)
        self.root.bell()

    def _exec_2fa_stop(self):
        """Arrête le flash 2FA et restaure le statut normal."""
        if not self._exec_2fa_flashing:
            return
        self._exec_2fa_flashing = False
        self._exec_status_var.set(f'\u23f3 {self._exec_run_label} en cours...')
        self._exec_status_label.config(bg=self._exec_default_bg, fg='#CC6600')

    def _exec_2fa_flash(self, on):
        """Alterne la couleur du label statut tant que le 2FA est actif."""
        if not self._exec_2fa_flashing:
            self._exec_status_label.config(
                bg=self._exec_default_bg, fg=self._exec_default_fg)
            return
        if on:
            self._exec_status_label.config(bg='#FFA500', fg='#FFFFFF')
        else:
            self._exec_status_label.config(bg=self._exec_default_bg, fg='#CC0000')
        self.root.after(500, self._exec_2fa_flash, not on)

    def _exec_on_finished(self, returncode):
        """Callback fin de subprocess : statut final, réactive les boutons."""
        self._exec_2fa_flashing = False
        self._exec_status_label.config(bg=self._exec_default_bg)
        if self._exec_tick_id:
            self.root.after_cancel(self._exec_tick_id)
            self._exec_tick_id = None
        if self._exec_table_active:
            # ⚠ FILET D'INVARIANT. Le subprocess est fini : plus aucun site ne
            #   peut être « en cours ». S'il en reste un, c'est que son verdict
            #   n'a pas été reconnu — une 4e issue apparue dans cpt_fetch.py.
            #   On la REND VISIBLE plutôt que de la laisser disparaître des
            #   compteurs : c'est ainsi que le verdict nuancé ⚠ (#194) était
            #   passé inaperçu (10/09/2026, « 11 ✓ + 2 ✗ » pour 14 sites).
            for st in self._exec_sites_state.values():
                if st['etat'] in ('run', 'wait'):
                    st.update(etat='part', fin='',
                              detail='issue non reconnue — voir le journal')
            self._exec_table_refresh()   # bascule sur échecs + incomplets
            self._exec_missed_refresh()
            self._exec_state_save()
        if returncode == 0:
            self._exec_status_var.set('\u25cf \u2713 Terminé')
            self._exec_status_label.config(fg='#228B22')
        else:
            self._exec_status_var.set(f'\u25cf \u274c Erreur (code {returncode})')
            self._exec_status_label.config(fg='#CC0000')
        for btn in self._exec_buttons:
            btn.config(state='normal')
        self._exec_stop_btn.config(state='disabled')
        self._exec_process = None
        self._exec_refresh_file_counts()

        # Recharger les comptes seulement si l'import a réussi (état sûr).
        if returncode == 0 and self.xlsx_path and self.xlsx_path.exists():
            self._load_accounts_data()
            self._populate_accounts_tree()

        # Rafraîchir la barre d'état MÊME en cas d'échec : un import qui plante
        # peut avoir muté partiellement le classeur → la barre ne doit pas
        # rester périmée (#178). La lecture ZIP est défensive (fallback + pass).
        if self.xlsx_path and self.xlsx_path.exists():
            self._refresh_status_bar()

    def _exec_stop(self):
        """Arrête le subprocess en cours et tous ses enfants."""
        proc = self._exec_process
        if not proc or proc.poll() is not None:
            return
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except (ProcessLookupError, OSError):
            proc.terminate()

    def _exec_refresh_file_counts(self):
        """Met à jour les compteurs de fichiers dropbox sur tous les sites."""
        for site, widget in self._exec_site_widgets.items():
            name = self._exec_site_names[site]
            dossier = self.config.get(site, 'dossier', fallback=site)
            site_dir = self._dropbox_dir / dossier
            count = 0
            if site_dir.exists():
                count = sum(1 for f in site_dir.iterdir() if f.is_file())
            label_text = f'{name} ({count})' if count else name
            widget.config(text=label_text)

    # ----------------------------------------------------------------
    # AIDE CONTEXTUELLE — tooltip persistant par cadre
    # ----------------------------------------------------------------
    def _make_help_button(self, parent_frame):
        """Enregistre un LabelFrame pour ajout d'un bouton ? (différé).

        Le texte d'aide est cherché dans FRAME_HELP par le titre du cadre.
        Si le titre n'a pas d'entrée dans FRAME_HELP, aucun bouton n'est créé.
        """
        self._pending_help_buttons.append(parent_frame)

    def _install_help_buttons(self):
        """Crée les boutons ? dans le titre de chaque LabelFrame (via labelwidget).

        Différé après la construction complète des onglets pour éviter un
        segfault Tk lié à la création de widgets pendant la construction.
        """
        from cpt_gui import FRAME_HELP
        for parent_frame in self._pending_help_buttons:
            title = parent_frame.cget('text')
            help_text = FRAME_HELP.get(title)
            if not help_text:
                continue
            lw = tk.Frame(parent_frame.master)
            tk.Label(lw, text=title, font=('', 11, 'bold')).pack(side='left')
            btn = tk.Label(lw, text=' ? ', font=('', 9, 'bold'),
                           fg='#555', bg='#e8e8e8', cursor='hand2',
                           relief='flat', padx=2)
            btn.pack(side='left', padx=(6, 0))
            parent_frame.configure(labelwidget=lw)
            btn.bind('<Button-1>',
                     lambda e, w=btn, t=help_text: self._show_help_tooltip(w, t))
        self._pending_help_buttons.clear()

    def _show_help_tooltip(self, widget, text):
        """Affiche un tooltip persistant sous le widget, fermé au clic ailleurs."""
        if self._active_tooltip:
            self._active_tooltip.destroy()
            self._active_tooltip = None

        tip = tk.Toplevel(self.root)
        tip.overrideredirect(True)
        tip.configure(bg='black')

        inner = tk.Frame(tip, bg='#FFFFDD', padx=10, pady=8)
        inner.pack(padx=1, pady=1)

        tk.Label(inner, text=text, bg='#FFFFDD', fg='#333',
                 font=('', 10), wraplength=350, justify='left').pack()

        # Positionner sous le widget, ou au-dessus si trop bas
        widget.update_idletasks()
        tip.update_idletasks()
        x = widget.winfo_rootx()
        y_below = widget.winfo_rooty() + widget.winfo_height() + 2
        tip_height = tip.winfo_reqheight()
        screen_height = self.root.winfo_screenheight()
        if y_below + tip_height > screen_height:
            y = widget.winfo_rooty() - tip_height - 2
        else:
            y = y_below
        tip.geometry(f'+{x}+{y}')

        self._active_tooltip = tip

        def _close_tooltip(event):
            if self._active_tooltip:
                self._active_tooltip.destroy()
                self._active_tooltip = None
            self.root.unbind_all('<Button-1>')

        # Fermer au prochain clic n'importe où (après un petit délai pour ne pas capturer le clic actuel)
        self.root.after(100, lambda: self.root.bind_all('<Button-1>', _close_tooltip))

    def _on_close(self):
        """Fermeture fenêtre : confirmation si exécution en cours."""
        # #181 : jalon de fermeture AVANT le teardown (survit même s'il lève).
        if hasattr(self, '_log_lifecycle'):
            self._log_lifecycle(
                '■', 'GUI fermée'
                + (' pour mise à jour' if getattr(self, '_closing_for_upgrade', False) else ''))
        # #107 « édite-et-pars » : persister l'onglet config courant (no-op si
        # rien changé) — l'utilisateur peut fermer sans avoir quitté l'onglet.
        if hasattr(self, '_autosave_config_tab'):
            self._autosave_config_tab(getattr(self, '_prev_tab_text', None))
        self._stop_file_watcher()
        if self._active_tooltip:
            self._active_tooltip.destroy()
            self._active_tooltip = None
        proc = self._exec_process
        if proc and proc.poll() is None:
            if not messagebox.askyesno(
                    'Exécution en cours',
                    'Une exécution est en cours.\nQuitter quand même ?',
                    parent=self.root):
                return
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except (ProcessLookupError, OSError):
                proc.terminate()
        # Arrêt propre du daemon (save + close batch + exit). No-op si jamais spawné.
        self._daemon_quit()
        self.root.destroy()

