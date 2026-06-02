"""Mixin Paramètres pour ConfigGUI."""

from tkinter import ttk
import tkinter as tk


class ParamsMixin:
    """Onglet Paramètres et Pipeline."""

    def _build_tab_params(self, tab=None):
        if tab is None:
            tab = ttk.Frame(self.notebook)
            self.notebook.add(tab, text='Paramètres')

        # Bouton Enregistrer fixe en bas
        save_frame = ttk.Frame(tab)
        save_frame.pack(side='bottom', fill='x', padx=10, pady=(5, 5))
        ttk.Button(save_frame, text='\U0001f4be Enregistrer',
                   command=self._save_params).pack(side='right')
        ttk.Separator(tab, orient='horizontal').pack(side='bottom', fill='x', padx=10)

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

        # Appariement
        pf = ttk.LabelFrame(scroll_frame, text='Appariement', padding=10)
        pf.pack(fill='x', padx=10, pady=5)
        self._make_help_button(pf)

        self._add_spinbox(pf, 'Même devise (jours)', 'pairing',
                          'max_jours_same_currency', 1, 90,
                          'Fenêtre de dates')
        self._add_spinbox(pf, 'Devises croisées (jours)', 'pairing',
                          'max_jours_cross_currency', 1, 90,
                          'Fenêtre de dates')
        self._add_entry(pf, 'Ratio max présélection', 'pairing',
                        'max_ratio_preselect',
                        'ex: 1.25 = 25%')
        self._add_entry(pf, 'Ratio max équivalent', 'pairing',
                        'max_ratio_equiv',
                        'ex: 2.0 = 100%')
        self._add_entry(pf, 'Seuil ambiguïté', 'pairing',
                        'ambiguity_threshold',
                        'ex: 0.05 = 5%')
        self._add_checkbox(pf, 'Sans appariement', 'pairing', 'no_pair',
                           'Ne pas lancer l\'appariement après l\'import')

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

        # Opérations liées
        lf = ttk.LabelFrame(scroll_frame, text='Opérations liées', padding=10)
        lf.pack(fill='x', padx=10, pady=5)
        self._make_help_button(lf)

        self.linked_tree = ttk.Treeview(
            lf, columns=('pattern', 'compte', 'description'),
            show='headings', height=4, selectmode='browse')
        self.linked_tree.heading('pattern', text='Pattern libellé')
        self.linked_tree.heading('compte', text='Compte cible')
        self.linked_tree.heading('description', text='Description')
        self.linked_tree.column('pattern', width=180, minwidth=100)
        self.linked_tree.column('compte', width=180, minwidth=100)
        self.linked_tree.column('description', width=180, minwidth=100)
        self.linked_tree.pack(fill='x')

        lf_btn = ttk.Frame(lf)
        lf_btn.pack(fill='x', pady=(5, 0))
        ttk.Button(lf_btn, text='\u2795 Ajouter',
                   command=self._linked_add).pack(side='left', padx=2)
        ttk.Button(lf_btn, text='\u2716 Supprimer',
                   command=self._linked_delete).pack(side='left', padx=2)

        self._linked_data = []
        self._load_linked_data()

        # Solde auto
        sf = ttk.LabelFrame(scroll_frame, text='Solde auto', padding=10)
        sf.pack(fill='x', padx=10, pady=5)
        self._make_help_button(sf)

        self.solde_auto_tree = ttk.Treeview(
            sf, columns=('compte', 'categorie', 'devise'),
            show='headings', height=3, selectmode='browse')
        self.solde_auto_tree.heading('compte', text='Compte')
        self.solde_auto_tree.heading('categorie', text='Catégorie trigger')
        self.solde_auto_tree.heading('devise', text='Devise')
        self.solde_auto_tree.column('compte', width=180, minwidth=100)
        self.solde_auto_tree.column('categorie', width=180, minwidth=100)
        self.solde_auto_tree.column('devise', width=120, minwidth=60)
        self.solde_auto_tree.pack(fill='x')

        sf_btn = ttk.Frame(sf)
        sf_btn.pack(fill='x', pady=(5, 0))
        ttk.Button(sf_btn, text='\u2795 Ajouter',
                   command=self._solde_auto_add).pack(side='left', padx=2)
        ttk.Button(sf_btn, text='\u2716 Supprimer',
                   command=self._solde_auto_delete).pack(side='left', padx=2)

        self._solde_auto_data = []
        self._load_solde_auto_data()

    def _load_linked_data(self):
        """Charge les opérations liées depuis config_pipeline.json et peuple le Treeview."""
        self._linked_data = []
        self.linked_tree.delete(*self.linked_tree.get_children())
        pipeline = self._load_pipeline_json()
        for pattern, entry in pipeline.get('linked_operations', {}).items():
            p = pattern.upper()
            compte = entry.get('compte_cible', '')
            desc = entry.get('description', '')
            self._linked_data.append((p, compte, desc))
            self.linked_tree.insert('', 'end', values=(p, compte, desc))

    def _linked_add(self):
        """Dialog pour ajouter une opération liée."""
        dlg = tk.Toplevel(self.root)
        dlg.title('Ajouter opération liée')
        dlg.geometry('400x180')
        dlg.transient(self.root)
        dlg.grab_set()

        fields = {}
        for i, (label, width) in enumerate([
            ('Pattern libellé :', 30), ('Compte cible :', 30),
            ('Description :', 30)]):
            ttk.Label(dlg, text=label).grid(row=i, column=0, sticky='w', padx=10, pady=3)
            var = tk.StringVar()
            ttk.Entry(dlg, textvariable=var, width=width).grid(
                row=i, column=1, padx=10, pady=3, sticky='w')
            fields[i] = var

        def on_ok():
            pattern = fields[0].get().strip().upper()
            compte = fields[1].get().strip()
            desc = fields[2].get().strip()
            if not pattern or not compte or not desc:
                return
            self._linked_data.append((pattern, compte, desc))
            self.linked_tree.insert('', 'end', values=(pattern, compte, desc))
            dlg.destroy()

        btn = ttk.Frame(dlg)
        btn.grid(row=3, column=0, columnspan=2, pady=10)
        ttk.Button(btn, text='OK', command=on_ok).pack(side='left', padx=5)
        ttk.Button(btn, text='Annuler', command=dlg.destroy).pack(side='left', padx=5)

    def _linked_delete(self):
        """Supprime l'opération liée sélectionnée."""
        sel = self.linked_tree.selection()
        if not sel:
            return
        vals = self.linked_tree.item(sel[0])['values']
        self._linked_data = [d for d in self._linked_data if d[0] != str(vals[0])]
        self.linked_tree.delete(sel[0])

    def _load_solde_auto_data(self):
        """Charge les soldes auto depuis config_pipeline.json et peuple le Treeview."""
        self._solde_auto_data = []
        self.solde_auto_tree.delete(*self.solde_auto_tree.get_children())
        pipeline = self._load_pipeline_json()
        for compte, entry in pipeline.get('solde_auto', {}).items():
            cat = entry.get('categorie_trigger', '')
            devise = entry.get('devise', '')
            self._solde_auto_data.append((compte, cat, devise))
            self.solde_auto_tree.insert('', 'end', values=(compte, cat, devise))

    def _solde_auto_add(self):
        """Dialog pour ajouter un solde auto."""
        dlg = tk.Toplevel(self.root)
        dlg.title('Ajouter solde auto')
        dlg.geometry('400x160')
        dlg.transient(self.root)
        dlg.grab_set()

        fields = {}
        for i, (label, width) in enumerate([
            ('Compte :', 30), ('Catégorie trigger :', 30), ('Devise :', 15)]):
            ttk.Label(dlg, text=label).grid(row=i, column=0, sticky='w', padx=10, pady=3)
            var = tk.StringVar()
            ttk.Entry(dlg, textvariable=var, width=width).grid(
                row=i, column=1, padx=10, pady=3, sticky='w')
            fields[i] = var

        def on_ok():
            compte = fields[0].get().strip()
            cat = fields[1].get().strip()
            devise = fields[2].get().strip()
            if not compte or not cat or not devise:
                return
            self._solde_auto_data.append((compte, cat, devise))
            self.solde_auto_tree.insert('', 'end', values=(compte, cat, devise))
            dlg.destroy()

        btn = ttk.Frame(dlg)
        btn.grid(row=3, column=0, columnspan=2, pady=10)
        ttk.Button(btn, text='OK', command=on_ok).pack(side='left', padx=5)
        ttk.Button(btn, text='Annuler', command=dlg.destroy).pack(side='left', padx=5)

    def _solde_auto_delete(self):
        """Supprime le solde auto sélectionné."""
        sel = self.solde_auto_tree.selection()
        if not sel:
            return
        vals = self.solde_auto_tree.item(sel[0])['values']
        self._solde_auto_data = [d for d in self._solde_auto_data
                                  if d[0] != str(vals[0])]
        self.solde_auto_tree.delete(sel[0])

    def _save_params(self):
        """Sauvegarde config.ini et config_pipeline.json depuis l'onglet Paramètres."""
        self._save_config()
        self._save_pipeline_config()
        self._set_status('Paramètres enregistrés')

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

