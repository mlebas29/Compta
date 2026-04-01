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
import tkinter as tk


class ExecMixin:
    """Onglet Exécution (collecte, import, fetch)."""

    def _build_tab_execution(self):
        tab = ttk.Frame(self.notebook)
        self._tab_execution = tab
        self.notebook.add(tab, text='Exécution')

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

        enabled_str = self.config.get('sites', 'enabled', fallback='')
        enabled_list = [s.strip() for s in enabled_str.split(',') if s.strip()]

        # Sites enabled (MANUEL exclu du GUI)
        exec_sites = [s for s in self.all_sites
                      if s in enabled_list and s != 'MANUEL']

        def _dropbox_file_count(site):
            dossier = self.config.get(site, 'dossier', fallback=site)
            site_dir = self._dropbox_dir / dossier
            if not site_dir.exists():
                return ''
            count = sum(1 for f in site_dir.iterdir() if f.is_file())
            return f' ({count})' if count else ''

        # --- Sites (checkboxes) ---
        sites_lf = ttk.LabelFrame(sites_frame, text='Sites', padding=4)
        sites_lf.pack(side='left', fill='both', expand=True)

        sites_grid = ttk.Frame(sites_lf)
        sites_grid.pack(fill='x')

        col = 0
        row = 0
        max_cols = 4
        for site in exec_sites:
            site_name = self.config.get(site, 'name', fallback=site)
            self._exec_site_names[site] = site_name
            var = tk.BooleanVar(value=True)
            self._exec_site_vars[site] = var
            label_text = site_name + _dropbox_file_count(site)
            cb = ttk.Checkbutton(sites_grid, text=label_text, variable=var)
            cb.grid(row=row, column=col, sticky='w', padx=(0, 10), pady=1)
            self._exec_site_widgets[site] = cb
            col += 1
            if col >= max_cols:
                col = 0
                row += 1

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

        # ── Section Lancement ──
        launch_frame = ttk.LabelFrame(tab, text='Lancement', padding=8)
        launch_frame.pack(fill='x', padx=8, pady=4)

        # Boutons action
        btn_frame = ttk.Frame(launch_frame)
        btn_frame.pack(fill='x', pady=(0, 6))

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
        btn.pack(side='left')
        self._exec_buttons.append(btn)

        # Outils (sous-cadre dans Lancement)
        tools_frame = ttk.LabelFrame(launch_frame, text='Outils', padding=6)
        tools_frame.pack(fill='x', pady=(0, 6))

        tools_btn_frame = ttk.Frame(tools_frame)
        tools_btn_frame.pack(fill='x')

        if self.mode != 'export':
            btn = ttk.Button(tools_btn_frame, text='Charger Wiki',
                             command=self._exec_pull)
            btn.pack(side='left', padx=(0, 8))
            self._exec_buttons.append(btn)

        if self.mode == 'prod':
            btn = ttk.Button(tools_btn_frame, text='Publier Wiki',
                             command=self._exec_push)
            btn.pack(side='left', padx=(0, 8))
            self._exec_buttons.append(btn)

        btn = ttk.Button(tools_btn_frame, text='Réinitialiser...',
                         command=self._exec_reset)
        btn.pack(side='left', padx=(0, 8))
        self._exec_buttons.append(btn)

        btn = ttk.Button(tools_btn_frame, text='Annuler import',
                         command=self._exec_fallback)
        btn.pack(side='left', padx=(0, 8))
        self._exec_buttons.append(btn)

        # Bouton Arrêter (en bas du cadre Lancement, s'applique à tout)
        stop_frame = ttk.Frame(launch_frame)
        stop_frame.pack(fill='x')

        self._exec_stop_btn = ttk.Button(stop_frame, text='Arrêter',
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

        text_frame = ttk.Frame(result_frame)
        text_frame.pack(fill='both', expand=True, pady=(4, 4))

        self._exec_output = tk.Text(text_frame, font=('monospace', 10),
                                    wrap='word', height=12)
        self._exec_output.bind('<Key>', self._exec_output_key)
        self._exec_output.bind('<Button-3>', self._exec_output_context_menu)
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
        ttk.Button(files_btn_frame, text='Archives',
                   command=self._exec_open_archives).pack(side='right', padx=(8, 0))
        ttk.Button(files_btn_frame, text='Dropbox',
                   command=self._exec_open_dropbox).pack(side='right', padx=(8, 0))
        ttk.Button(files_btn_frame, text='Journal',
                   command=self._exec_open_journal).pack(side='right', padx=(8, 0))


    # ----------------------------------------------------------------
    # EXÉCUTION : handlers boutons
    # ----------------------------------------------------------------
    def _exec_output_key(self, event):
        """Bloque l'édition du résultat, autorise copie et sélection."""
        if event.state & 0x4 and event.keysym.lower() in ('c', 'a'):
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
            # xclip fiable sur Linux/X11 (Tk perd le clipboard quand le Menu popup est détruit)
            try:
                subprocess.Popen(
                    ['xclip', '-selection', 'clipboard'],
                    stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                ).communicate(text.encode('utf-8'))
            except FileNotFoundError:
                self.clipboard_clear()
                self.clipboard_append(text)
                self.update()

    def _exec_output_select_all(self):
        """Sélectionne tout le contenu de la zone Résultat."""
        self._exec_output.tag_add('sel', '1.0', 'end-1c')

    def _get_selected_sites(self):
        """Retourne la chaîne des sites fetchables cochés (séparés par virgules)."""
        script_dir = self.config_path.parent
        return ','.join(s for s, var in self._exec_site_vars.items()
                        if var.get()
                        and (script_dir / f'cpt_fetch_{s}.py').exists())

    def _exec_fetch_only(self):
        sites = self._get_selected_sites()
        if not sites:
            messagebox.showwarning('Aucun site',
                                   'Aucun site sélectionné pour la collecte.',
                                   parent=self.root)
            return
        cmd = [sys.executable, str(self.config_path.parent / 'cpt.py'),
               '--fetch-only', '--sites', sites]
        if self._exec_verbose_var.get():
            cmd.append('-v')
        self._exec_run(cmd, 'Collecte')

    def _exec_import_only(self):
        # cpt_update.py directement (supporte --no-pair)
        cmd = [sys.executable, str(self.config_path.parent / 'cpt_update.py')]
        if self._exec_all_soldes_var.get():
            cmd.append('--all-soldes')
        no_pair = self.tk_vars.get(('pairing', 'no_pair'))
        if no_pair and no_pair[1].get():
            cmd.append('--no-pair')
        if self._exec_verbose_var.get():
            cmd.append('-v')
        self._exec_run(cmd, 'Import')

    def _exec_cotations(self):
        cmd = [sys.executable, str(self.config_path.parent / 'cpt_fetch_quotes.py')]
        if self._exec_verbose_var.get():
            cmd.append('-v')
        self._exec_run(cmd, 'Cotations')

    def _exec_pull(self):
        cmd = [sys.executable, str(self.config_path.parent / 'cpt.py'), '--pull']
        self._exec_run(cmd, 'Pull Seafile')

    def _exec_push(self):
        cmd = [sys.executable, str(self.config_path.parent / 'cpt.py'), '--push']
        self._exec_run(cmd, 'Push Seafile')

    def _exec_reset(self):
        if self.mode == 'export':
            self._exec_reset_export_dialog()
        else:
            # DEV/PROD : confirmation simple → pull Seafile + purge
            if not messagebox.askyesno(
                    'Confirmation',
                    'Réinitialiser le système ?\n\n'
                    'Cela va :\n'
                    '- Récupérer comptes.xlsm depuis Seafile\n'
                    '- Purger archives, dropbox et logs',
                    parent=self.root):
                return
            cmd = [sys.executable, str(self.config_path.parent / 'cpt.py'),
                   '--reset']
            self._exec_run(cmd, 'Réinitialisation')

    def _exec_reset_export_dialog(self):
        """Dialogue de réinitialisation pour le mode Export."""
        dlg = tk.Toplevel(self.root)
        dlg.title('Réinitialiser')
        dlg.transient(self.root)
        dlg.grab_set()
        dlg.resizable(False, False)

        pad = {'padx': 12, 'pady': 6}

        # --- Option 1 : Template vierge ---
        frame1 = ttk.LabelFrame(dlg, text='Option 1 — Charger template vierge',
                                padding=8)
        frame1.pack(fill='x', **pad)

        ttk.Label(frame1, text=(
            'Remplace comptes.xlsm par le template vierge.\n'
            'Réinitialise les configs comptes/pipeline.\n'
            'Purge archives, dropbox, logs et cookies.'
        ), justify='left').pack(anchor='w')

        ttk.Button(frame1, text='Charger template',
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
                'Charger le template vierge ?\n\n'
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

    def _exec_open_journal(self):
        logs_dir = self.config.get('paths', 'logs', fallback='./logs')
        journal = self.config_path.parent / logs_dir / 'journal.log'
        if journal.exists():
            subprocess.Popen(['xdg-open', str(journal)])
        else:
            messagebox.showinfo('Journal',
                                f'Fichier journal introuvable :\n{journal}',
                                parent=self.root)

    def _exec_open_comptes(self):
        comptes = self.config.get('paths', 'comptes_file', fallback='./comptes.xlsm')
        path = (self.config_path.parent / comptes).resolve()
        if path.exists():
            subprocess.Popen(['xdg-open', str(path)])
        else:
            messagebox.showinfo('comptes.xlsm',
                                f'Fichier introuvable :\n{path}',
                                parent=self.root)

    def _exec_open_dropbox(self):
        path = (self.config_path.parent /
                self.config.get('paths', 'dropbox', fallback='./dropbox')).resolve()
        if path.exists():
            subprocess.Popen(['xdg-open', str(path)])
        else:
            messagebox.showinfo('Dropbox', f'Répertoire introuvable :\n{path}',
                                parent=self.root)

    def _exec_open_archives(self):
        path = (self.config_path.parent /
                self.config.get('paths', 'archives', fallback='./archives')).resolve()
        if path.exists():
            subprocess.Popen(['xdg-open', str(path)])
        else:
            messagebox.showinfo('Archives', f'Répertoire introuvable :\n{path}',
                                parent=self.root)

    # ----------------------------------------------------------------
    # EXÉCUTION : subprocess dans un thread
    # ----------------------------------------------------------------
    def _exec_run(self, cmd_args, label):
        """Lance un subprocess dans un thread dédié."""
        self._exec_output.configure(state='normal')
        self._exec_output.delete('1.0', 'end')

        self._exec_run_label = label
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
                if 'VALIDATION 2FA' in item or 'VALIDATION REQUISE' in item or 'CONNEXION REQUISE' in item:
                    self._exec_2fa_alert()
                elif self._exec_2fa_flashing and item.strip():
                    self._exec_2fa_stop()
        except queue.Empty:
            pass
        self.root.after(100, self._exec_poll)

    def _exec_2fa_alert(self):
        """Alerte visuelle + sonore lors d'une demande de validation 2FA."""
        self._exec_status_var.set('\U0001f513 Validation 2FA \u2014 action requise')
        self._exec_2fa_flashing = True
        self._exec_2fa_flash(True)
        # Auto-stop après 30 s
        self.root.after(30000, self._exec_2fa_stop)
        # Mise au premier plan + son
        self.root.lift()
        self.root.attributes('-topmost', True)
        self.root.after(3000, lambda: self.root.attributes('-topmost', False))
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

        # Recharger les comptes si le fichier a pu être modifié par le subprocess
        if returncode == 0 and self.xlsx_path and self.xlsx_path.exists():
            self._load_accounts_data()
            self._populate_accounts_tree()
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
        self.root.destroy()

    # ----------------------------------------------------------------
    # DESCRIPTIONS SITES (défauts JSON + overrides utilisateur)
    # ----------------------------------------------------------------
    @staticmethod
    def _load_json(path):
        """Charge un fichier JSON, retourne {} si absent ou invalide."""
        if path.exists():
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                pass
        return {}

    def _load_descriptions(self):
        """Charge les descriptions : défauts + overrides utilisateur."""
        merged = dict(self.site_descriptions_default)
        merged.update(self._load_json(self.desc_path))
        return merged

    def _save_descriptions(self):
        """Sauvegarde uniquement les descriptions modifiées par rapport aux défauts."""
        to_save = {}
        for site, text in self.site_descriptions.items():
            default = self.site_descriptions_default.get(site, '')
            if text != default:
                to_save[site] = text
        if to_save:
            with open(self.desc_path, 'w', encoding='utf-8') as f:
                json.dump(to_save, f, ensure_ascii=False, indent=2)
                f.write('\n')
        elif self.desc_path.exists():
            self.desc_path.unlink()

