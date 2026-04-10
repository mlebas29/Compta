"""Mixin onglet Sites pour ConfigGUI."""

import tkinter as tk
from tkinter import ttk


class SitesMixin:
    """Méthodes de l'onglet Sites (propriétés, descriptions, activation)."""

    def _build_tab_sites(self, tab=None):
        if tab is None:
            tab = ttk.Frame(self.notebook)
            self.notebook.add(tab, text='Sites')

        all_sites = self.all_sites

        # Sites affichés (MANUEL exclu du GUI)
        self._display_sites = [s for s in all_sites if s != 'MANUEL']

        # --- Panneau gauche : liste des sites ---
        left = ttk.Frame(tab)
        left.pack(side='left', fill='y', padx=(5, 2), pady=5)

        sites_frame = ttk.LabelFrame(left, text='Sites', padding=5)
        sites_frame.pack(fill='both', expand=True)
        self._make_help_button(sites_frame)
        lf = ttk.Frame(sites_frame)
        lf.pack(fill='both', expand=True)
        self._site_lb = tk.Listbox(lf, width=24, font=('', 11),
                                   exportselection=False, activestyle='none')
        vsb = ttk.Scrollbar(lf, orient='vertical', command=self._site_lb.yview)
        self._site_lb.configure(yscrollcommand=vsb.set)
        self._site_lb.pack(side='left', fill='both', expand=True)
        vsb.pack(side='right', fill='y')
        for site in self._display_sites:
            display_name = self.config.get(site, 'name', fallback=site)
            label = f"\u2713 {display_name}" if self.site_vars[site].get() else f"   {display_name}"
            self._site_lb.insert('end', label)

        self._site_lb.bind('<<ListboxSelect>>', self._on_site_selected)

        # --- Panneau droit : propriétés du site sélectionné ---
        right = ttk.LabelFrame(tab, text='Propriétés', padding=8)
        right.pack(side='left', fill='both', expand=True, padx=(2, 5), pady=5)
        self._make_help_button(right)

        # Zone propriétés (haut, taille fixe)
        self.site_props_frame = ttk.Frame(right)
        self.site_props_frame.pack(fill='x')

        # Zone description (bas, extensible)
        desc_frame = ttk.LabelFrame(right, text='Description', padding=5)
        desc_frame.pack(fill='both', expand=True, pady=(8, 0))
        self.site_desc_text = tk.Text(desc_frame, font=('', 10), wrap='word')
        desc_vsb = ttk.Scrollbar(desc_frame, orient='vertical',
                                  command=self.site_desc_text.yview)
        self.site_desc_text.configure(yscrollcommand=desc_vsb.set)
        self.site_desc_text.pack(side='left', fill='both', expand=True)
        desc_vsb.pack(side='right', fill='y')

        self.site_detail_widgets = []

        if self._display_sites:
            self._site_lb.selection_set(0)
            self._on_site_selected(None)

        # Bouton Enregistrer (après _on_site_selected pour éviter un segfault Tk)
        save_frame = ttk.Frame(right)
        save_frame.pack(fill='x', side='bottom', pady=(8, 0))
        ttk.Button(save_frame, text='\U0001f4be Enregistrer',
                   command=self._save_sites).pack(side='right')

    def _save_sites(self):
        """Sauvegarde config.ini (sites) + descriptions depuis l'onglet Sites."""
        self._save_config()
        self._save_descriptions()
        self._set_status('Configuration sites enregistrée')
        if self.xlsx_path:
            self._refresh_status_bar()

    def _get_selected_site(self):
        """Retourne le site sélectionné, ou None."""
        sel = self._site_lb.curselection()
        if sel:
            return self._display_sites[sel[0]]
        return None

    def _on_site_selected(self, event):
        # Nettoyer les widgets précédents
        for w in self.site_detail_widgets:
            w.destroy()
        self.site_detail_widgets.clear()
        to_remove = [k for k in self.tk_vars if k[0].startswith('site_')]
        for k in to_remove:
            del self.tk_vars[k]

        # Identifier le site sélectionné
        site = self._get_selected_site()
        if not site:
            return
        if not self.config.has_section(site):
            return

        frame = self.site_props_frame

        # Checkbox Actif (vert/rouge)
        row_actif = ttk.Frame(frame)
        row_actif.pack(fill='x', pady=(0, 6))
        self.site_detail_widgets.append(row_actif)
        is_on = self.site_vars[site].get()
        actif_style = 'SiteOn.TCheckbutton' if is_on else 'SiteOff.TCheckbutton'
        self._site_actif_text = tk.StringVar(value='Actif' if is_on else 'Inactif')
        self._site_actif_cb = ttk.Checkbutton(
            row_actif, textvariable=self._site_actif_text,
            variable=self.site_vars[site],
            style=actif_style,
            command=lambda s=site: self._refresh_site_list())
        self._site_actif_cb.pack(side='left')
        site_name = self.config.get(site, 'name', fallback=site)
        ttk.Label(row_actif, text=site_name,
                  font=('', 12, 'bold')).pack(side='left', padx=(15, 0))

        # Libellés français par clé
        french_labels = {
            'name': 'Nom',
            'base_url': 'URL',
            'credential_id': 'Identifiant',
            'max_days_back': 'Jours max',
            'max_reports': 'Nb rapports',
            'dossier': 'Dossier',
            'drive_folder': 'Dossier Drive',
            'drive_account': 'Compte Drive',
            'wallet_cli_dir': 'CLI Monero',
            'wallet_dir': 'Dossier wallets',
            'daemon_address': 'Adresse daemon',
            'daemon_credential_id': 'Identifiant daemon',
            'wallet_timeout': 'Timeout wallet',
            'api_url': 'URL API',
        }

        # Hints contextuels par clé
        hints = {
            'max_days_back': f'(global : {self.config.get("general", "max_days_back", fallback="90")})',
        }

        readonly_keys = {'name', 'base_url', 'credential_id', 'daemon_address', 'dossier'}
        override_keys = ['max_days_back']

        existing_keys = list(self.config.options(site))
        all_keys = existing_keys[:]
        for key in override_keys:
            if key not in all_keys:
                all_keys.append(key)
        # Dossier juste après name, wallet_dir juste après dossier
        if 'dossier' in all_keys:
            all_keys.remove('dossier')
            idx = all_keys.index('name') + 1 if 'name' in all_keys else 0
            all_keys.insert(idx, 'dossier')
        if 'wallet_dir' in all_keys:
            all_keys.remove('wallet_dir')
            idx = all_keys.index('dossier') + 1 if 'dossier' in all_keys else 0
            all_keys.insert(idx, 'wallet_dir')

        for key in all_keys:
            val = self.config.get(site, key, fallback='')
            row = ttk.Frame(frame)
            row.pack(fill='x', pady=1)
            self.site_detail_widgets.append(row)

            display_label = french_labels.get(key, key)
            ttk.Label(row, text=display_label, width=18, anchor='w',
                      font=('', 11, 'bold')).pack(side='left')

            var = tk.StringVar(value=val)
            self.tk_vars[('site_' + site, key)] = ('str', var)
            short_keys = ('max_days_back', 'max_reports', 'wallet_timeout')
            if key in short_keys:
                width = 10
            elif key == 'dossier':
                width = 20
            else:
                width = 45
            state = 'readonly' if key in readonly_keys else 'normal'
            ttk.Entry(row, textvariable=var, width=width,
                      state=state).pack(side='left', padx=5)

            if key in hints:
                ttk.Label(row, text=hints[key],
                          style='Hint.TLabel').pack(side='left')

        # Description
        desc_text = self.site_descriptions.get(site, '')
        self.site_desc_text.config(state='normal')
        self.site_desc_text.delete('1.0', 'end')
        self.site_desc_text.insert('1.0', desc_text)
        if self.mode in ('prod', 'export'):
            self.site_desc_text.config(state='disabled')
        else:
            # Lier la sauvegarde au site courant
            self.site_desc_text.unbind('<KeyRelease>')
            self.site_desc_text.bind(
                '<KeyRelease>',
                lambda e, s=site: self._update_site_desc(s))

    def _refresh_site_list(self):
        """Met à jour les indicateurs actif/inactif dans la liste."""
        sel = self._site_lb.curselection()
        for i, site in enumerate(self._display_sites):
            display_name = self.config.get(site, 'name', fallback=site)
            label = f"\u2713 {display_name}" if self.site_vars[site].get() else f"   {display_name}"
            self._site_lb.delete(i)
            self._site_lb.insert(i, label)
        if sel:
            self._site_lb.selection_set(sel[0])
        # Mettre à jour couleur et texte de la checkbox
        site = self._get_selected_site()
        if site:
            is_on = self.site_vars[site].get()
            self._site_actif_cb.configure(
                style='SiteOn.TCheckbutton' if is_on else 'SiteOff.TCheckbutton')
            self._site_actif_text.set('Actif' if is_on else 'Inactif')

    def _update_site_desc(self, site):
        """Met à jour la description en mémoire quand l'utilisateur édite."""
        text = self.site_desc_text.get('1.0', 'end-1c').strip()
        self.site_descriptions[site] = text
