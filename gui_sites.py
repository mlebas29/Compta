"""Mixin onglet Sites pour ConfigGUI."""

from pathlib import Path

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

import inc_gpg_credentials as gpg_creds

# Clés de config.ini qui désignent une entrée de la table d'identifiants → elles
# gagnent le bouton « Gérer… ». (XMR en a deux : son login site et son RPC.)
_CREDENTIAL_KEYS = ('credential_id', 'wallet_rpc_credential_id')


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

    def _get_selected_site(self):
        """Retourne le site sélectionné, ou None."""
        sel = self._site_lb.curselection()
        if sel:
            return self._display_sites[sel[0]]
        return None

    def _on_site_selected(self, event):
        # #107 édite-et-pars : persister le site SORTANT avant de jeter ses champs
        # (corrige le piège « changer de site sans sauver perd les params »).
        # No-op si rien changé ; any(site_) → saute la toute 1ʳᵉ sélection.
        if any(k[0].startswith('site_') for k in self.tk_vars):
            self._save_config()
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

        # Overrides collecte (sites navigateur seulement) : headed / parallel en
        # cases à cocher — facultatifs, per-instance (cf. inc_fetch headed override
        # + cpt_fetch parallel). Décoché = comportement dérivé par défaut.
        if self.config.has_option(site, 'base_url'):
            row_cb = ttk.Frame(frame)
            row_cb.pack(fill='x', pady=(2, 6))
            self.site_detail_widgets.append(row_cb)
            headed_var = tk.BooleanVar(
                value=self.config.getboolean(site, 'headed', fallback=False))
            self.tk_vars[('site_' + site, 'headed')] = ('bool', headed_var)
            ttk.Checkbutton(row_cb, text='Fenêtre visible (headed)',
                            variable=headed_var).pack(side='left', padx=(0, 20))
            par_var = tk.BooleanVar(
                value=self.config.getboolean(site, 'parallel', fallback=False))
            self.tk_vars[('site_' + site, 'parallel')] = ('bool', par_var)
            ttk.Checkbutton(row_cb, text='Collecte en parallèle',
                            variable=par_var).pack(side='left')

        # Libellés français par clé
        french_labels = {
            'name': 'Nom',
            'base_url': 'URL',
            # « Réf » et non « Identifiant » : dans la table chiffrée, Réf = la clé
            # et Identifiant = le login du site. Nommer la clé « Identifiant » ici
            # faisait dire au même mot deux choses à deux écrans d'écart.
            'credential_id': 'Réf',
            'max_days_back': 'Jours max',
            'max_reports': 'Nb rapports',
            'dossier': 'Dossier',
            'drive_folder': 'Dossier Drive',
            'drive_account': 'Compte Drive',
            'poll_timeout': 'Timeout collecte (s)',
            'wallet_rpc_ssh_host': 'Hôte SSH wallet-rpc',
            'wallet_rpc_port': 'Port wallet-rpc',
            'wallet_rpc_local_port': 'Port tunnel local',
            'wallet_rpc_credential_id': 'Réf RPC',
            'refresh_timeout': 'Timeout refresh',
            'tunnel_timeout': 'Timeout tunnel',
            'api_url': 'URL API',
        }

        # Hints contextuels par clé
        hints = {
            'max_days_back': f'(global : {self.config.get("general", "max_days_back", fallback="90")})',
        }

        readonly_keys = {'name', 'base_url', 'credential_id', 'wallet_rpc_credential_id', 'dossier'}
        override_keys = ['max_days_back']

        existing_keys = list(self.config.options(site))
        all_keys = existing_keys[:]
        for key in override_keys:
            if key not in all_keys:
                all_keys.append(key)
        # Dossier juste après name
        if 'dossier' in all_keys:
            all_keys.remove('dossier')
            idx = all_keys.index('name') + 1 if 'name' in all_keys else 0
            all_keys.insert(idx, 'dossier')

        for key in all_keys:
            if key in ('headed', 'parallel'):
                continue  # rendus en cases à cocher ci-dessus
            val = self.config.get(site, key, fallback='')
            row = ttk.Frame(frame)
            row.pack(fill='x', pady=1)
            self.site_detail_widgets.append(row)

            display_label = french_labels.get(key, key)
            ttk.Label(row, text=display_label, width=18, anchor='w',
                      font=('', 11, 'bold')).pack(side='left')

            var = tk.StringVar(value=val)
            self.tk_vars[('site_' + site, key)] = ('str', var)
            short_keys = ('max_days_back', 'max_reports', 'wallet_rpc_port',
                          'wallet_rpc_local_port', 'refresh_timeout', 'tunnel_timeout')
            if key in short_keys:
                width = 10
            elif key == 'dossier':
                width = 20
            else:
                width = 45
            state = 'readonly' if key in readonly_keys else 'normal'
            ttk.Entry(row, textvariable=var, width=width,
                      state=state).pack(side='left', padx=5)

            # Porte CONTEXTUELLE : la réf de ce site, directement. La vue globale
            # de la table vit dans Paramètres (cf. _open_credentials_manager).
            if key in _CREDENTIAL_KEYS:
                ttk.Button(row, text='Modifier…', width=10,
                           command=lambda v=var: self._edit_site_credential(v.get())
                           ).pack(side='left', padx=(0, 5))

            if key in hints:
                ttk.Label(row, text=hints[key],
                          style='Hint.TLabel').pack(side='left')

        # Description (lecture seule : source = DESCRIPTION dans cpt_fetch_<site>.py)
        desc_text = self.site_descriptions.get(site, '')
        self.site_desc_text.config(state='normal')
        self.site_desc_text.delete('1.0', 'end')
        self.site_desc_text.insert('1.0', desc_text)
        self.site_desc_text.config(state='disabled')

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

    # ------------------------------------------------------------------
    # Table d'identifiants — CRUD (cf. invariants : inc_gpg_credentials).
    #
    # Hors du modèle « édite-et-pars » des onglets config À DESSEIN : chaque
    # écriture coûte un aller-retour GPG + un backup, donc validation explicite
    # par dialogue. Même raison qui interdit de peupler une liste déroulante
    # d'identifiants dans l'onglet : la remplir exigerait de déchiffrer, donc une
    # demande de passphrase à chaque affichage. On ne déchiffre QUE sur geste.
    # ------------------------------------------------------------------

    def _credentials_file(self):
        raw = self.config.get('paths', 'credentials_file',
                              fallback='./config_credentials.md.gpg')
        return Path(raw).expanduser()

    def _credential_usage(self):
        """identifiant → sites qui s'en servent, lu de config.ini — SANS déchiffrer.

        Le lien site→identifiant vit dans config.ini, la table ne le connaît pas :
        c'est ce qui permet à une clé de rester libre (un site peut en changer, un
        identifiant peut servir deux sites, XMR en use deux). L'afficher rend le
        lien lisible sans le graver dans le nommage, et fait ressortir les orphelins.
        """
        usage = {}
        for section in self.config.sections():
            for key in _CREDENTIAL_KEYS:
                cid = self.config.get(section, key, fallback='').strip()
                if not cid:
                    continue
                label = section if key == 'credential_id' else f'{section} (rpc)'
                usage.setdefault(cid, []).append(label)
        return usage

    def _credential_entry_dialog(self, parent, cid=None, login=''):
        """Formulaire d'une entrée. cid=None → création. Retourne (réf, id, passe|None).

        Vocabulaire aligné sur la table elle-même : Réf = la clé, Identifiant = le
        login du site, Passe = le secret. Le mot de passe n'est jamais préchargé
        (on ne le lit pas pour le gérer) → vide = inchangé.
        """
        d = tk.Toplevel(parent)
        d.title('Modifier la réf' if cid else 'Nouvelle réf')
        d.transient(parent)
        out = {}
        f = ttk.Frame(d, padding=10)
        f.pack(fill='both', expand=True)

        ttk.Label(f, text='Réf :', width=14).grid(row=0, column=0, sticky='w')
        v_id = tk.StringVar(value=cid or '')
        e_id = ttk.Entry(f, textvariable=v_id, width=30)
        e_id.grid(row=0, column=1, pady=3)
        if cid:
            e_id.configure(state='readonly')  # la Réf est la clé : jamais renommée ici

        ttk.Label(f, text='Identifiant :', width=14).grid(row=1, column=0, sticky='w')
        v_log = tk.StringVar(value=login)
        e_log = ttk.Entry(f, textvariable=v_log, width=30)
        e_log.grid(row=1, column=1, pady=3)

        ttk.Label(f, text='Passe :', width=14).grid(row=2, column=0, sticky='w')
        v_pw = tk.StringVar()
        ttk.Entry(f, textvariable=v_pw, width=30, show='•').grid(row=2, column=1, pady=3)
        if cid:
            ttk.Label(f, text='(vide = inchangé)',
                      style='Hint.TLabel').grid(row=3, column=1, sticky='w')

        def ok():
            if not v_id.get().strip():
                messagebox.showwarning('Champ requis',
                                       'La réf est obligatoire.', parent=d)
                return
            out['v'] = (v_id.get().strip(), v_log.get().strip(), v_pw.get() or None)
            d.destroy()

        br = ttk.Frame(f)
        br.grid(row=4, column=0, columnspan=2, pady=(10, 0))
        ttk.Button(br, text='Valider', command=ok).pack(side='left', padx=4)
        ttk.Button(br, text='Annuler', command=d.destroy).pack(side='left', padx=4)
        (e_log if cid else e_id).focus_set()
        # `grab_set` sur une fenêtre pas encore mappée lève « window not viewable ».
        d.wait_visibility()
        d.grab_set()
        d.wait_window()
        return out.get('v')

    def _edit_site_credential(self, cid):
        """Porte CONTEXTUELLE (onglet Sites) : la réf de CE site, directement.

        Ni liste ni colonne « Utilisé par » : le site est implicite, l'afficher
        serait du bruit. Et pas de suppression — une réf peut servir plusieurs
        sites (ou aucun) : ça ne se juge que depuis la vue globale (Paramètres).
        """
        if not cid:
            messagebox.showinfo(
                'Aucune réf', "Ce site n'a pas de réf d'identifiant configurée.",
                parent=self.root)
            return
        path = self._credentials_file()
        if not path.exists():
            messagebox.showerror('Table introuvable',
                                 f"Aucune table d'identifiants à :\n{path}",
                                 parent=self.root)
            return
        pw = simpledialog.askstring("Identifiants", f'Passphrase de {path.name} :',
                                    show='•', parent=self.root)
        if not pw:
            return
        entries, err = gpg_creds.read_entries(path, pw)
        if err:
            messagebox.showerror('Lecture impossible', err, parent=self.root)
            return

        known = dict(entries)
        if cid not in known and not messagebox.askyesno(
                'Réf inconnue',
                f"La réf « {cid} » n'existe pas encore dans la table.\n\nLa créer ?",
                parent=self.root):
            return
        v = self._credential_entry_dialog(self.root, cid, known.get(cid, ''))
        if not v:
            return
        _, login, pwd = v
        _, e = gpg_creds.upsert_entry(path, pw, cid, login,
                                      pwd if cid in known else (pwd or ''))
        if e:
            messagebox.showerror('Écriture impossible', e, parent=self.root)
            return
        messagebox.showinfo('Enregistré', f'Réf « {cid} » enregistrée.',
                            parent=self.root)

    def _open_credentials_manager(self, preselect=''):
        """Porte GLOBALE (onglet Paramètres) : la table entière + « Utilisé par ».

        C'est ici — et ici seulement — qu'on crée, supprime et repère les
        orphelins : ces gestes exigent de voir qui utilise quoi.
        """
        path = self._credentials_file()
        if not path.exists():
            messagebox.showerror(
                'Table introuvable',
                f"Aucune table d'identifiants à :\n{path}\n\n"
                "Crée-la d'abord (cf. install.sh), ou corrige "
                "[paths] credentials_file dans config.ini.",
                parent=self.root)
            return

        pw = simpledialog.askstring(
            "Table d'identifiants", f'Passphrase de {path.name} :',
            show='•', parent=self.root)
        if not pw:
            return
        entries, err = gpg_creds.read_entries(path, pw)
        if err:
            messagebox.showerror('Lecture impossible', err, parent=self.root)
            return

        dlg = tk.Toplevel(self.root)
        dlg.title("Identifiants de collecte")
        dlg.transient(self.root)
        dlg.geometry('720x380')
        dlg.minsize(560, 300)

        ttk.Label(dlg, text=f'{path.name} — également éditable à la main '
                            '(gpg -d / gpg -c)',
                  style='Hint.TLabel').pack(anchor='w', padx=10, pady=(8, 4))

        # Barre d'actions réservée AVANT l'arbre : `pack` sert les widgets dans
        # l'ordre de déclaration, donc un arbre en expand=True posé d'abord
        # chasserait les boutons hors du cadre tant qu'on n'agrandit pas.
        btn_row = ttk.Frame(dlg)
        btn_row.pack(side='bottom', fill='x', padx=10, pady=8)
        grp = ttk.LabelFrame(btn_row, text='Réf', padding=4)
        grp.pack(side='left')

        tree_f = ttk.Frame(dlg)
        tree_f.pack(fill='both', expand=True, padx=10)
        tree = ttk.Treeview(tree_f, columns=('login', 'sites'),
                            show='tree headings', selectmode='browse')
        tree.heading('#0', text='Réf')
        tree.column('#0', width=140)
        tree.heading('login', text='Identifiant')
        tree.column('login', width=250)
        tree.heading('sites', text='Utilisé par')
        tree.column('sites', width=200)
        tree.pack(side='left', fill='both', expand=True)
        sb = ttk.Scrollbar(tree_f, orient='vertical', command=tree.yview)
        sb.pack(side='right', fill='y')
        tree.configure(yscrollcommand=sb.set)

        state = {'pw': pw}

        usage = self._credential_usage()

        def refresh(select=None):
            rows, e = gpg_creds.read_entries(path, state['pw'])
            if e:
                messagebox.showerror('Lecture impossible', e, parent=dlg)
                return
            tree.delete(*tree.get_children())
            for cid, login in rows:
                sites = ', '.join(usage.get(cid, [])) or '⚠ aucun'
                tree.insert('', 'end', iid=cid, text=cid, values=(login, sites))
            if select and tree.exists(select):
                tree.selection_set(select)
                tree.see(select)
            _gate()

        def _gate(_evt=None):
            has = bool(tree.selection())
            b_edit.configure(state='normal' if has else 'disabled')
            b_del.configure(state='normal' if has else 'disabled')

        def add():
            v = self._credential_entry_dialog(dlg)
            if not v:
                return
            cid, login, pwd = v
            _, e = gpg_creds.upsert_entry(path, state['pw'], cid, login, pwd or '')
            if e:
                messagebox.showerror('Écriture impossible', e, parent=dlg)
                return
            refresh(select=cid)

        def edit():
            sel = tree.selection()
            if not sel:
                return
            cid = sel[0]
            v = self._credential_entry_dialog(dlg, cid, tree.item(cid, 'values')[0])
            if not v:
                return
            _, login, pwd = v
            _, e = gpg_creds.upsert_entry(path, state['pw'], cid, login, pwd)
            if e:
                messagebox.showerror('Écriture impossible', e, parent=dlg)
                return
            refresh(select=cid)

        def delete():
            sel = tree.selection()
            if not sel:
                return
            cid = sel[0]
            if not messagebox.askyesno(
                    'Supprimer', f"Supprimer l'identifiant « {cid} » ?\n\n"
                    "Les sites qui l'utilisent ne pourront plus se connecter.\n"
                    f"Une sauvegarde {path.name}.bak est conservée.",
                    parent=dlg):
                return
            e = gpg_creds.delete_entry(path, state['pw'], cid)
            if e:
                messagebox.showerror('Suppression impossible', e, parent=dlg)
                return
            refresh()

        ttk.Button(grp, text='➕', width=3, command=add).pack(side='left', padx=1)
        b_edit = ttk.Button(grp, text='✏', width=3, command=edit)
        b_edit.pack(side='left', padx=1)
        b_del = ttk.Button(grp, text='✖', width=3, command=delete)
        b_del.pack(side='left', padx=1)
        ttk.Button(btn_row, text='Fermer', command=dlg.destroy).pack(side='right')

        tree.bind('<<TreeviewSelect>>', _gate)
        tree.bind('<Double-1>', lambda _e: edit())
        refresh(select=preselect or None)
        dlg.wait_visibility()
        dlg.grab_set()
        dlg.wait_window()
        # On lâche la RÉFÉRENCE — on n'efface pas la mémoire : une chaîne Python
        # est immuable et non écrasable, et Tcl en garde ses propres copies. La
        # passphrase devient collectable, rien de plus. Vie réelle ≈ celle du
        # dialogue, là où gpg-agent, lui, la garde 600 s glissantes MAIS en
        # mémoire verrouillée. Vie plus courte ici, murs plus minces : c'est le
        # prix du loopback, lequel achète en échange l'impossibilité de
        # rechiffrer avec une passphrase divergente.
        state['pw'] = None

