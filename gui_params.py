"""Mixin Paramètres pour ConfigGUI."""

from tkinter import ttk
import tkinter as tk


class ParamsMixin:
    """Onglet Paramètres et Pipeline."""

    def _build_tab_params(self, tab=None):
        if tab is None:
            tab = ttk.Frame(self.notebook)
            self.notebook.add(tab, text='Paramètres')

        canvas = tk.Canvas(tab)
        scrollbar = ttk.Scrollbar(tab, orient='vertical', command=canvas.yview)
        scroll_frame = ttk.Frame(canvas)

        scroll_frame.bind('<Configure>',
                          lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.create_window((0, 0), window=scroll_frame, anchor='nw')
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')

        # Général
        gf = ttk.LabelFrame(scroll_frame, text='Général', padding=10)
        gf.pack(fill='x', padx=10, pady=5)
        self._make_help_button(gf)

        self._add_checkbox(gf, 'Mode debug', 'general', 'DEBUG',
                           'Traces détaillées dans les logs')
        self._add_spinbox(gf, 'Sessions archivées', 'general', 'max_sessions',
                          1, 100, 'Nombre de sessions à garder')
        self._add_spinbox(gf, 'Jours max import', 'general', 'max_days_back',
                          0, 365, '0 = illimité')

        # Appariement — un cadre, deux sous-sections : Générale (params de l'algo) +
        # Spécifique (paires prédéfinies transfer_pairs). #133
        pf = ttk.LabelFrame(scroll_frame, text='Appariement', padding=10)
        pf.pack(fill='x', padx=10, pady=5)
        self._make_help_button(pf)

        # — Générale : paramètres de l'algo d'appariement (config.ini [pairing])
        gpf = ttk.LabelFrame(pf, text='Générale', padding=8)
        gpf.pack(fill='x', pady=(0, 6))
        self._add_spinbox(gpf, 'Même devise (jours)', 'pairing',
                          'max_jours_same_currency', 1, 90,
                          'Fenêtre de dates')
        self._add_spinbox(gpf, 'Devises croisées (jours)', 'pairing',
                          'max_jours_cross_currency', 1, 90,
                          'Fenêtre de dates')
        self._add_entry(gpf, 'Ratio max présélection', 'pairing',
                        'max_ratio_preselect',
                        'ex: 1.25 = 25%')
        self._add_entry(gpf, 'Ratio max équivalent', 'pairing',
                        'max_ratio_equiv',
                        'ex: 2.0 = 100%')
        self._add_entry(gpf, 'Seuil ambiguïté', 'pairing',
                        'ambiguity_threshold',
                        'ex: 0.05 = 5%')
        self._add_checkbox(gpf, 'Sans appariement', 'pairing', 'no_pair',
                           'Ne pas lancer l\'appariement après l\'import')

        # — Spécifique : paires prédéfinies (transfer_pairs, config_accounts.json).
        # Apparie deux opérations DÉJÀ existantes que l'algo général rate (décalage
        # récurrent, ex. gérance→SG à 1 mois). Liste = Nom seul, détail dans le dialog.
        spf = ttk.LabelFrame(pf, text='Spécifique (paires prédéfinies)', padding=8)
        spf.pack(fill='x')
        self.transfer_tree = ttk.Treeview(
            spf, columns=('name',), show='headings', height=4, selectmode='browse')
        self.transfer_tree.heading('name', text='Nom')
        self.transfer_tree.column('name', width=320, minwidth=120)
        self.transfer_tree.pack(fill='x')
        tf_btn = ttk.Frame(spf)
        tf_btn.pack(fill='x', pady=(5, 0))
        ttk.Button(tf_btn, text='➕ Ajouter',
                   command=self._transfer_pair_add).pack(side='left', padx=2)
        ttk.Button(tf_btn, text='✏ Éditer',
                   command=self._transfer_pair_edit).pack(side='left', padx=2)
        ttk.Button(tf_btn, text='✖ Supprimer',
                   command=self._transfer_pair_delete).pack(side='left', padx=2)
        self._transfer_pairs_data = []
        self._load_transfer_pairs()

        # Comparaison
        cf = ttk.LabelFrame(scroll_frame, text='Comparaison', padding=10)
        cf.pack(fill='x', padx=10, pady=5)
        self._make_help_button(cf)

        self._add_spinbox(cf, 'Seuil variation (%)', 'comparison',
                          'warn_threshold', 0, 100,
                          'Alerte Plus_value')

        # Exécution
        ef = ttk.LabelFrame(scroll_frame, text='Exécution', padding=10)
        ef.pack(fill='x', padx=10, pady=5)
        self._make_help_button(ef)

        # _exec_all_soldes_var et _exec_verbose_var sont initialisés dans _build_tab_execution
        # (partagés avec le menu Outils, qui en a besoin avant la construction de cet onglet).
        frame = ttk.Frame(ef)
        frame.pack(fill='x', pady=2)
        ttk.Checkbutton(frame, text='Import soldes',
                        variable=self._exec_all_soldes_var).pack(side='left')
        ttk.Label(frame, text='Importer tous les soldes (--all-soldes)',
                  style='Hint.TLabel').pack(side='left', padx=10)

        frame2 = ttk.Frame(ef)
        frame2.pack(fill='x', pady=2)
        ttk.Checkbutton(frame2, text='Verbeux',
                        variable=self._exec_verbose_var).pack(side='left')
        ttk.Label(frame2, text='Traces détaillées à l\'exécution',
                  style='Hint.TLabel').pack(side='left', padx=10)

        # Opérations de compensation (ex « Opérations liées », linked_operations).
        # À partir d'une op existante (pattern matché sur le libellé), GÉNÈRE une op
        # de compensation dans un compte cible + marque l'appariement. C'est de la
        # GÉNÉRATION, pas de l'appariement pur. Liste = Nom seul (champ libre), détail
        # dans le dialog. #133/#140
        lf = ttk.LabelFrame(scroll_frame, text='Opérations de compensation', padding=10)
        lf.pack(fill='x', padx=10, pady=5)
        self._make_help_button(lf)

        self.linked_tree = ttk.Treeview(
            lf, columns=('name',), show='headings', height=4, selectmode='browse')
        self.linked_tree.heading('name', text='Nom')
        self.linked_tree.column('name', width=320, minwidth=120)
        self.linked_tree.pack(fill='x')

        lf_btn = ttk.Frame(lf)
        lf_btn.pack(fill='x', pady=(5, 0))
        ttk.Button(lf_btn, text='➕ Ajouter',
                   command=self._linked_add).pack(side='left', padx=2)
        ttk.Button(lf_btn, text='✏ Éditer',
                   command=self._linked_edit).pack(side='left', padx=2)
        ttk.Button(lf_btn, text='✖ Supprimer',
                   command=self._linked_delete).pack(side='left', padx=2)

        self._linked_data = []
        self._load_linked_data()


    def _load_linked_data(self):
        """Charge linked_operations (config_pipeline.json). Liste = Nom (description) seul."""
        self._linked_data = []
        pipeline = self._load_pipeline_json()
        for pattern, entry in pipeline.get('linked_operations', {}).items():
            self._linked_data.append((pattern.upper(),
                                      entry.get('compte_cible', ''),
                                      entry.get('description', '')))
        self._refresh_linked_tree()

    def _refresh_linked_tree(self):
        self.linked_tree.delete(*self.linked_tree.get_children())
        for i, (pattern, compte, desc) in enumerate(self._linked_data):
            self.linked_tree.insert('', 'end', iid=str(i), values=(desc or pattern,))

    def _linked_dialog(self, existing=None):
        """Dialog Ajouter/Éditer une op de compensation. Retourne (pattern, compte, nom) ou None."""
        dlg = tk.Toplevel(self.root)
        dlg.title('Opération de compensation')
        dlg.geometry('460x210')
        dlg.transient(self.root)
        dlg.grab_set()
        pattern0, compte0, nom0 = existing or ('', '', '')
        rows = [('Nom :', nom0), ('Pattern libellé :', pattern0), ('Compte cible :', compte0)]
        vals = []
        for i, (lab, v) in enumerate(rows):
            ttk.Label(dlg, text=lab).grid(row=i, column=0, sticky='w', padx=10, pady=4)
            var = tk.StringVar(value=v)
            ttk.Entry(dlg, textvariable=var, width=34).grid(row=i, column=1, padx=10, pady=4, sticky='w')
            vals.append(var)
        result = {}

        def on_ok():
            nom = vals[0].get().strip()
            pattern = vals[1].get().strip().upper()
            compte = vals[2].get().strip()
            if not pattern or not compte:
                return
            result['row'] = (pattern, compte, nom)
            dlg.destroy()

        btn = ttk.Frame(dlg)
        btn.grid(row=3, column=0, columnspan=2, pady=12)
        ttk.Button(btn, text='OK', command=on_ok).pack(side='left', padx=5)
        ttk.Button(btn, text='Annuler', command=dlg.destroy).pack(side='left', padx=5)
        dlg.wait_window()
        return result.get('row')

    def _linked_add(self):
        row = self._linked_dialog()
        if row:
            self._linked_data.append(row)
            self._refresh_linked_tree()

    def _linked_edit(self):
        sel = self.linked_tree.selection()
        if not sel:
            return
        i = int(sel[0])
        row = self._linked_dialog(self._linked_data[i])
        if row:
            self._linked_data[i] = row
            self._refresh_linked_tree()

    def _linked_delete(self):
        sel = self.linked_tree.selection()
        if not sel:
            return
        del self._linked_data[int(sel[0])]
        self._refresh_linked_tree()

    def _load_transfer_pairs(self):
        """Charge transfer_pairs (config_accounts.json). Liste = Nom seul."""
        self._transfer_pairs_data = list(self.accounts_json_data.get('transfer_pairs', []))
        self._refresh_transfer_tree()

    def _refresh_transfer_tree(self):
        self.transfer_tree.delete(*self.transfer_tree.get_children())
        for i, p in enumerate(self._transfer_pairs_data):
            self.transfer_tree.insert('', 'end', iid=str(i), values=(p.get('name', ''),))

    def _transfer_pair_dialog(self, existing=None):
        """Dialog Ajouter/Éditer une paire prédéfinie. Retourne le dict paire ou None."""
        dlg = tk.Toplevel(self.root)
        dlg.title('Paire de virements (appariement prédéfini)')
        dlg.geometry('480x360')
        dlg.transient(self.root)
        dlg.grab_set()
        e = existing or {}
        src = e.get('source', {})
        dst = e.get('dest', {})
        rows = [
            ('Nom :', e.get('name', '')),
            ('Source — compte :', src.get('compte', '')),
            ('Source — pattern libellé :', src.get('pattern', '')),
            ('Dest — compte :', dst.get('compte', '')),
            ('Dest — pattern libellé :', dst.get('pattern', '')),
            ('Jours max écart :', str(e.get('max_jours_ecart', 7))),
        ]
        keys = ['name', 'src_compte', 'src_pattern', 'dst_compte', 'dst_pattern', 'jours']
        vars = {}
        for i, ((lab, v), key) in enumerate(zip(rows, keys)):
            ttk.Label(dlg, text=lab).grid(row=i, column=0, sticky='w', padx=10, pady=3)
            var = tk.StringVar(value=v)
            ttk.Entry(dlg, textvariable=var, width=34).grid(row=i, column=1, padx=10, pady=3, sticky='w')
            vars[key] = var
        ttk.Label(dlg, text='Source — signe :').grid(row=6, column=0, sticky='w', padx=10, pady=3)
        src_signe = tk.StringVar(value=src.get('signe', 'negatif'))
        ttk.Combobox(dlg, textvariable=src_signe, values=['negatif', 'positif'],
                     state='readonly', width=12).grid(row=6, column=1, sticky='w', padx=10, pady=3)
        ttk.Label(dlg, text='Dest — signe :').grid(row=7, column=0, sticky='w', padx=10, pady=3)
        dst_signe = tk.StringVar(value=dst.get('signe', 'positif'))
        ttk.Combobox(dlg, textvariable=dst_signe, values=['negatif', 'positif'],
                     state='readonly', width=12).grid(row=7, column=1, sticky='w', padx=10, pady=3)
        result = {}

        def on_ok():
            name = vars['name'].get().strip()
            src_c = vars['src_compte'].get().strip()
            dst_c = vars['dst_compte'].get().strip()
            if not name or not src_c or not dst_c:
                return
            try:
                jours = int(vars['jours'].get().strip() or '7')
            except ValueError:
                jours = 7
            result['pair'] = {
                'name': name,
                'max_jours_ecart': jours,
                'source': {'compte': src_c, 'pattern': vars['src_pattern'].get().strip(),
                           'signe': src_signe.get()},
                'dest': {'compte': dst_c, 'pattern': vars['dst_pattern'].get().strip(),
                         'signe': dst_signe.get()},
            }
            dlg.destroy()

        btn = ttk.Frame(dlg)
        btn.grid(row=8, column=0, columnspan=2, pady=12)
        ttk.Button(btn, text='OK', command=on_ok).pack(side='left', padx=5)
        ttk.Button(btn, text='Annuler', command=dlg.destroy).pack(side='left', padx=5)
        dlg.wait_window()
        return result.get('pair')

    def _transfer_pair_add(self):
        p = self._transfer_pair_dialog()
        if p:
            self._transfer_pairs_data.append(p)
            self._refresh_transfer_tree()

    def _transfer_pair_edit(self):
        sel = self.transfer_tree.selection()
        if not sel:
            return
        i = int(sel[0])
        p = self._transfer_pair_dialog(self._transfer_pairs_data[i])
        if p:
            self._transfer_pairs_data[i] = p
            self._refresh_transfer_tree()

    def _transfer_pair_delete(self):
        sel = self.transfer_tree.selection()
        if not sel:
            return
        del self._transfer_pairs_data[int(sel[0])]
        self._refresh_transfer_tree()


    def _add_checkbox(self, parent, label, section, key, tooltip=''):
        frame = ttk.Frame(parent)
        frame.pack(fill='x', pady=2)
        val = self.config.get(section, key, fallback='false')
        var = tk.BooleanVar(value=val.lower() == 'true')
        self.tk_vars[(section, key)] = ('bool', var)
        cb = ttk.Checkbutton(frame, text=label, variable=var)
        cb.pack(side='left')
        if tooltip:
            ttk.Label(frame, text=tooltip, style='Hint.TLabel').pack(side='left', padx=10)

    def _add_spinbox(self, parent, label, section, key, from_, to, tooltip=''):
        frame = ttk.Frame(parent)
        frame.pack(fill='x', pady=2)
        ttk.Label(frame, text=label, width=28, anchor='w').pack(side='left')
        val = self.config.get(section, key, fallback='0')
        var = tk.IntVar(value=int(val))
        self.tk_vars[(section, key)] = ('int', var)
        sb = ttk.Spinbox(frame, from_=from_, to=to, textvariable=var, width=8)
        sb.pack(side='left', padx=5)
        if tooltip:
            ttk.Label(frame, text=tooltip, style='Hint.TLabel').pack(side='left', padx=5)

    def _add_entry(self, parent, label, section, key, tooltip=''):
        frame = ttk.Frame(parent)
        frame.pack(fill='x', pady=2)
        ttk.Label(frame, text=label, width=28, anchor='w').pack(side='left')
        val = self.config.get(section, key, fallback='')
        var = tk.StringVar(value=val)
        self.tk_vars[(section, key)] = ('str', var)
        entry = ttk.Entry(frame, textvariable=var, width=12)
        entry.pack(side='left', padx=5)
        if tooltip:
            ttk.Label(frame, text=tooltip, style='Hint.TLabel').pack(side='left', padx=5)

