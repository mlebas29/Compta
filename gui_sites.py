"""Mixin onglet Sites pour ConfigGUI."""

from pathlib import Path

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

import inc_gpg_credentials as gpg_creds

# Clés de config.ini qui désignent une entrée de la table de secrets. (XMR en a deux :
# son login site et son RPC.) Elles sont affichées SOUS LEUR VRAI NOM `.ini` — surtout
# pas « Réf » : la feuille Opérations a déjà un terme métier « Réf » (une paire
# d'opérations, cf. glossaire) ET la table chiffrée a une colonne « Réf » (la valeur
# BaSo-M) → un troisième « Réf » pour désigner la clé faisait percuter trois choses.
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
            'max_days_back': 'Jours max',
            'max_reports': 'Nb rapports',
            'dossier': 'Dossier',
            'drive_folder': 'Dossier Drive',
            'drive_account': 'Compte Drive',
            'poll_timeout': 'Timeout collecte (s)',
            'wallet_rpc_ssh_host': 'Hôte SSH wallet-rpc',
            'wallet_rpc_port': 'Port wallet-rpc',
            'wallet_rpc_local_port': 'Port tunnel local',
            'refresh_timeout': 'Timeout refresh',
            'tunnel_timeout': 'Timeout tunnel',
            'api_url': 'URL API',
        }

        # Hints contextuels par clé
        hints = {
            'max_days_back': f'(global : {self.config.get("general", "max_days_back", fallback="90")})',
        }

        # `name` (nom de présentation) est ÉDITABLE : pure étiquette, aucune clé/
        # dossier/fichier n'en dépend (la sélection se fait par id de section). ⚠ Il
        # doit AUSSI être retiré de `readonly_keys` dans `_save_config` (gui_devises),
        # sinon la saisie serait jetée en silence. `base_url`/`dossier` restent gelés
        # (dossier orpheline la dropbox ; base_url peut casser le login).
        readonly_keys = {'base_url', 'dossier'}
        override_keys = ['max_days_back']

        # Les réfs sortent de la boucle générique : elles ont leur cadre, en lecture
        # seule (cf. plus bas).
        existing_keys = [k for k in self.config.options(site)
                         if k not in _CREDENTIAL_KEYS]
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
            if key == 'name':
                # Nom de présentation : rafraîchir le libellé de la liste en live
                # (seul champ éditable qui pilote l'affichage — sinon périmé jusqu'à
                # re-sélection). La persistance reste « édite-et-pars » (à la transition).
                var.trace_add('write',
                              lambda *a, s=site, v=var: self._update_site_label(s, v.get()))
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

            if key in hints:
                ttk.Label(row, text=hints[key],
                          style='Hint.TLabel').pack(side='left')

        # Cadre Authentification — la moitié `.ini` du pont : la/les Réf que ce site pointe.
        # ÉDITABLE et GRATUIT (config.ini seul, aucun pinentry) : la GUI ne RÉSOUT
        # pas la Réf — résoudre = déchiffrer le `.gpg` — l'utilisateur pose lui-même
        # la valeur qui, chez lui, nomme une ligne de la table. L'entrée elle-même
        # (identifiant/passe) se crée dans l'autre porte : Paramètres → Secrets. Deux
        # gestes, deux fichiers, comme avant la GUI. La saisie persiste par l'autosave
        # « édite-et-pars » (tk_vars) comme tout paramètre de site.
        cred_keys = self._site_credential_keys(site)
        if cred_keys:
            cred_f = ttk.LabelFrame(frame, text='Authentification', padding=6)
            cred_f.pack(fill='x', pady=(8, 0))
            self.site_detail_widgets.append(cred_f)
            for key in cred_keys:
                row = ttk.Frame(cred_f)
                row.pack(fill='x', pady=1)
                ttk.Label(row, text=key, width=24,
                          anchor='w', font=('', 10, 'bold')).pack(side='left')
                var = tk.StringVar(value=self.config.get(site, key, fallback=''))
                self.tk_vars[('site_' + site, key)] = ('str', var)
                ttk.Entry(row, textvariable=var, width=30).pack(side='left', padx=5)
            ttk.Label(cred_f, text='La valeur doit trouver sa correspondance en 1ʳᵉ '
                                   'colonne de la table chiffrée (GPG) — onglet '
                                   'Paramètres.',
                      style='Hint.TLabel', wraplength=440,
                      justify='left').pack(anchor='w', pady=(4, 2))

        # Bouton Dupliquer — sites navigateur seulement (un site manuel n'a pas de
        # connecteur à cloner). Modèle C : nouvelle section + symlink des 2 connecteurs
        # vers la source (une seule impl → les correctifs se propagent, pas de copie
        # qui dérive). Pour un 2ᵉ accès à la même banque (autre login, autres comptes).
        if self.config.has_option(site, 'base_url'):
            row_clone = ttk.Frame(frame)
            row_clone.pack(fill='x', pady=(10, 0))
            self.site_detail_widgets.append(row_clone)
            ttk.Button(row_clone, text='Dupliquer cet accès…',
                       command=lambda s=site: self._clone_site(s)).pack(side='left')
            # Supprimer : gaté sur « site vide » (aucun compte déclaré) — le seul
            # risque d'une suppression est d'orpheliner des comptes du classeur.
            empty = self._site_is_empty(site)
            ttk.Button(row_clone, text='Supprimer cet accès…',
                       state=('normal' if empty else 'disabled'),
                       command=lambda s=site: self._delete_site(s)).pack(
                           side='left', padx=(8, 0))
            if not empty:
                ttk.Label(row_clone, text='(a des comptes — vide-le d’abord)',
                          style='Hint.TLabel').pack(side='left', padx=(6, 0))

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

    def _update_site_label(self, site, name):
        """Rafraîchit le libellé d'un site dans la liste (édition live du nom)."""
        if site not in self._display_sites:
            return
        i = self._display_sites.index(site)
        checked = self.site_vars[site].get()
        label = f"✓ {name}" if checked else f"   {name}"
        sel = self._site_lb.curselection()
        self._site_lb.delete(i)
        self._site_lb.insert(i, label)
        if sel:
            self._site_lb.selection_set(sel[0])

    # ------------------------------------------------------------------
    # Dupliquer un accès (modèle C) — 2ᵉ accès à la même banque (autre login,
    # autre profil de comptes). Nouvelle section config.ini + symlink des DEUX
    # connecteurs (cpt_fetch/cpt_format) vers la source. L'identité (SITE, section,
    # dropbox, profil Chrome) vient du nom du lien — Python n'indexe PAS sur la cible
    # résolue de `__file__` (vérifié) → le lien donne un site distinct « gratuitement »,
    # tout en gardant UNE seule impl (les correctifs se propagent, pas de copie qui
    # dérive — doctrine #125). GARDE : ne jamais `realpath(__file__)` sur ces chemins.
    # ------------------------------------------------------------------

    def _resolve_connector(self, prefix, site):
        """Chemin du connecteur `{prefix}{site}.py` (PUB puis custom/), ou None."""
        import inc_mode
        base = inc_mode.get_base_dir()
        for d in (base, base / 'custom'):
            p = d / f'{prefix}{site}.py'
            if p.exists():
                return p
        return None

    def _suggest_section_id(self, source):
        """Propose un id de section libre dérivé de la source (SOURCE2, SOURCE3…)."""
        i = 2
        while (self.config.has_section(f'{source}{i}')
               or self._resolve_connector('cpt_fetch_', f'{source}{i}')):
            i += 1
        return f'{source}{i}'

    def _validate_new_section(self, sec):
        """Message d'erreur si l'id de section neuf est invalide/pris, sinon None."""
        import re
        if not sec:
            return "L'id de section est obligatoire."
        if not re.match(r'^[A-Z][A-Z0-9_]*$', sec):
            return ("Id invalide : majuscules, chiffres et « _ » "
                    "(commence par une lettre). Ex. CREDMUT2.")
        if sec in ('GENERAL', 'PAIRING', 'COMPARISON', 'PATHS', 'SITES', 'MANUEL'):
            return f"« {sec} » est un nom réservé."
        if self.config.has_section(sec):
            return f"La section « {sec} » existe déjà."
        if (self._resolve_connector('cpt_fetch_', sec)
                or self._resolve_connector('cpt_format_', sec)):
            return f"Un connecteur « {sec} » existe déjà sur le disque."
        return None

    def _clone_dialog(self, source, src_name):
        """Saisie id de section + nom affiché. Retourne (section, nom) ou None."""
        d = tk.Toplevel(self.root)
        d.title('Dupliquer un accès')
        d.transient(self.root)
        out = {}
        f = ttk.Frame(d, padding=12)
        f.pack(fill='both', expand=True)

        ttk.Label(f, text=f"Duplication de « {src_name} » ({source}).\n"
                          "Même connecteur ; credential et comptes DISTINCTS.",
                  justify='left').grid(row=0, column=0, columnspan=2,
                                       sticky='w', pady=(0, 10))

        ttk.Label(f, text='Id de section :', width=16).grid(row=1, column=0, sticky='w')
        v_sec = tk.StringVar(value=self._suggest_section_id(source))
        e_sec = ttk.Entry(f, textvariable=v_sec, width=28)
        e_sec.grid(row=1, column=1, pady=3, sticky='w')
        ttk.Label(f, text='(interne : fichier, dropbox, profil — ex. CREDMUT2)',
                  style='Hint.TLabel').grid(row=2, column=1, sticky='w')

        ttk.Label(f, text='Nom affiché :', width=16).grid(row=3, column=0, sticky='w')
        # Placeholder « bis » (pas « (2) ») : l'onglet Exécution affiche « nom (N) »
        # avec N = fichiers collectés → un suffixe numérique entre parenthèses s'y
        # confondrait. L'utilisateur remplace de toute façon par le titulaire.
        v_name = tk.StringVar(value=f'{src_name} bis')
        e_name = ttk.Entry(f, textvariable=v_name, width=28)
        e_name.grid(row=3, column=1, pady=3, sticky='w')
        ttk.Label(f, text='(ce que tu vois, ex. Crédit Mutuel Alice)',
                  style='Hint.TLabel').grid(row=4, column=1, sticky='w')

        def ok():
            sec = v_sec.get().strip().upper()
            name = v_name.get().strip()
            err = self._validate_new_section(sec)
            if err:
                messagebox.showwarning('Id invalide', err, parent=d)
                return
            if not name:
                messagebox.showwarning('Champ requis',
                                       'Le nom affiché est obligatoire.', parent=d)
                return
            out['v'] = (sec, name)
            d.destroy()

        br = ttk.Frame(f)
        br.grid(row=5, column=0, columnspan=2, pady=(12, 0))
        ttk.Button(br, text='Dupliquer', command=ok).pack(side='left', padx=4)
        ttk.Button(br, text='Annuler', command=d.destroy).pack(side='left', padx=4)
        e_sec.focus_set()
        d.wait_visibility()
        d.grab_set()
        d.wait_window()
        return out.get('v')

    def _clone_site(self, source):
        """Duplique l'accès `source` : dialogue, symlink des connecteurs, section."""
        import os
        src_fetch = self._resolve_connector('cpt_fetch_', source)
        src_format = self._resolve_connector('cpt_format_', source)
        if not src_fetch or not src_format:
            messagebox.showerror(
                'Duplication impossible',
                f"Connecteur introuvable pour « {source} » "
                "(cpt_fetch et/ou cpt_format).", parent=self.root)
            return

        src_name = self.config.get(source, 'name', fallback=source)
        res = self._clone_dialog(source, src_name)
        if not res:
            return
        new_section, new_name = res

        # Persister d'éventuelles éditions Sites en attente AVANT d'appendre (l'append
        # travaille sur self.config_raw ; _save_config est no-op si rien changé).
        self._save_config()

        # Symlinks : cible = fichier RÉEL résolu (aplatit un clone-de-clone), relative
        # (même dossier que la source). Rollback du 1ᵉʳ lien si le 2ᵉ échoue.
        created = []
        try:
            for src, prefix in ((src_fetch, 'cpt_fetch_'), (src_format, 'cpt_format_')):
                target = os.path.basename(os.path.realpath(src))
                link = src.parent / f'{prefix}{new_section}.py'
                os.symlink(target, link)
                created.append(link)
        except OSError as e:
            for link in created:
                try:
                    link.unlink()
                except OSError:
                    pass
            messagebox.showerror('Duplication impossible',
                                 f"Création du lien symbolique échouée :\n{e}",
                                 parent=self.root)
            return

        # Nouvelle section config.ini (base_url copiée ; credential vide → cadre
        # Authentification affiché pour saisie ; désactivée par défaut).
        from cpt_gui import append_config_section
        base_url = self.config.get(source, 'base_url', fallback='')
        pairs = [('name', new_name), ('dossier', new_section), ('base_url', base_url)]
        self.config_raw = append_config_section(self.config_raw, new_section, pairs)
        with open(self.config_path, 'w', encoding='utf-8') as fh:
            fh.write(self.config_raw)
        self.config.read_string(self.config_raw)

        # Rafraîchir l'état GUI (site désactivé par défaut) + reconstruire l'onglet.
        if new_section not in self.all_sites:
            self.all_sites.append(new_section)
        self.site_vars[new_section] = tk.BooleanVar(value=False)
        self._rebuild_sites_tab(select=new_section)

        messagebox.showinfo(
            'Accès dupliqué',
            f"« {new_name} » créé (section {new_section}).\n\n"
            "À compléter avant de l'activer :\n"
            "• le secret (cadre Authentification + onglet Paramètres → Secrets) ;\n"
            "• les comptes et leurs RIB (onglet Avoirs).",
            parent=self.root)

    def _rebuild_sites_tab(self, select=None):
        """Reconstruit l'onglet Sites en place (après ajout/retrait d'un site)."""
        for tab_id in self.notebook.tabs():
            if self.notebook.tab(tab_id, 'text') == 'Sites':
                frame = self.notebook.nametowidget(tab_id)
                for w in frame.winfo_children():
                    w.destroy()
                self._build_tab_sites(tab=frame)
                self._install_help_buttons()
                if select and select in self._display_sites:
                    idx = self._display_sites.index(select)
                    self._site_lb.selection_clear(0, 'end')
                    self._site_lb.selection_set(idx)
                    self._on_site_selected(None)
                return

    def _site_is_empty(self, site):
        """True si le site n'a AUCUN compte déclaré (config_accounts.json[site]) — le
        critère de suppression : un site sans compte ne peut orpheliner le classeur."""
        data = getattr(self, 'accounts_json_data', None) or {}
        entry = data.get(site)
        return not (isinstance(entry, dict) and entry.get('accounts'))

    def _delete_site(self, site):
        """Supprime un accès VIDE : section config.ini + enabled, connecteurs (SI
        symlinks — un vrai fichier partagé n'est jamais supprimé), dossier collecte,
        profil Chrome, entrée config_accounts. Le secret (table GPG) n'est pas touché."""
        import shutil
        import inc_mode
        from cpt_gui import (remove_config_section, write_config_section_key,
                             read_config_raw, write_accounts_json)

        name = self.config.get(site, 'name', fallback=site)
        if not self._site_is_empty(site):
            messagebox.showwarning(
                'Suppression impossible',
                f"« {name} » a des comptes déclarés (onglet Avoirs) → retire-les "
                "d'abord.", parent=self.root)
            return
        if not messagebox.askyesno(
                'Supprimer un accès',
                f"Supprimer l'accès « {name} » ({site}) ?\n\n"
                "Seront retirés : la section config.ini, les connecteurs (liens), le "
                "dossier de collecte et le profil de navigation.\n"
                "Le secret (table GPG) et le code partagé ne sont PAS touchés.",
                parent=self.root):
            return

        self._save_config()  # flush d'éventuelles éditions Sites en attente

        base = inc_mode.get_base_dir()
        # Connecteurs : retirer UNIQUEMENT s'ils sont des symlinks (= un clone) ; un
        # vrai module (site d'origine) est du code partagé → jamais supprimé.
        for prefix in ('cpt_fetch_', 'cpt_format_'):
            p = self._resolve_connector(prefix, site)
            if p and p.is_symlink():
                try:
                    p.unlink()
                except OSError:
                    pass
        # Dossier dropbox + profil Chrome (best-effort).
        dossier = self.config.get(site, 'dossier', fallback=site)
        dropbox = base / self.config.get('paths', 'dropbox', fallback='dropbox') / dossier
        for d in (dropbox, base / f'.chrome_profile_{site.lower()}'):
            if d.exists():
                try:
                    shutil.rmtree(d)
                except OSError:
                    pass
        # Entrée config_accounts.json (vide par construction — supprimée si présente).
        data = getattr(self, 'accounts_json_data', None)
        if isinstance(data, dict) and site in data:
            del data[site]
            write_accounts_json(self.json_path, data)
            if hasattr(self, 'account_site_map'):
                self.account_site_map = {k: v for k, v in self.account_site_map.items()
                                         if v != site}
        # Section config.ini + retrait de la liste enabled.
        raw = remove_config_section(self.config_raw, site)
        enabled = [s.strip() for s in
                   self.config.get('sites', 'enabled', fallback='').split(',')
                   if s.strip() and s.strip() != site]
        updated = write_config_section_key(raw, 'sites', 'enabled', ','.join(enabled))
        if updated is not None:
            raw = updated
        with open(self.config_path, 'w', encoding='utf-8') as fh:
            fh.write(raw)
        # Re-parse depuis le disque : read_string MERGE (ne retirerait pas la section
        # du parser) → relecture complète pour un ConfigParser propre.
        self.config_raw, self.config = read_config_raw(self.config_path)

        self.all_sites = [s for s in self.all_sites if s != site]
        self.site_vars.pop(site, None)
        self._rebuild_sites_tab(select=None)
        messagebox.showinfo('Accès supprimé', f"« {name} » ({site}) supprimé.",
                            parent=self.root)

    # ------------------------------------------------------------------
    # Porte Secrets — CRUD du `.gpg`, seul (cf. invariants : inc_gpg_credentials).
    #
    # Cette porte est FIDÈLE au fichier chiffré : colonnes du `.gpg`, rien de
    # config.ini. Hors du modèle « édite-et-pars » À DESSEIN — chaque écriture coûte
    # un aller-retour GPG + un backup, donc validation explicite par dialogue, et on
    # ne déchiffre QUE sur geste (jamais pour un simple affichage). L'autre moitié du
    # pont — la Réf posée dans config.ini — vit dans le cadre « Authentification » de
    # l'onglet Sites, éditable et gratuit (aucun pinentry).
    # ------------------------------------------------------------------

    def _credentials_file(self):
        raw = self.config.get('paths', 'credentials_file',
                              fallback='./config_credentials.md.gpg')
        return Path(raw).expanduser()

    def _site_credential_keys(self, site):
        """Clés d'accès que CE site expose, dans l'ordre d'affichage.

        Une clé présente dans config.ini est exposée telle quelle. `credential_id`
        l'est AUSSI pour tout site navigateur qui ne l'a pas encore : config.ini.default
        n'en fournit à aucun d'eux, donc sans ça une install fraîche n'offrirait nulle
        part où saisir sa réf, et le geste redeviendrait terminal. Garde `base_url`
        = « site navigateur » (idiome maison) : BTC (adresses publiques) et MANUEL
        (saisie) n'ont pas de réf et n'en verront pas.
        """
        keys = [k for k in _CREDENTIAL_KEYS if self.config.has_option(site, k)]
        if 'credential_id' not in keys and self.config.has_option(site, 'base_url'):
            keys.insert(0, 'credential_id')
        return keys

    def _ask_new_passphrase(self, parent):
        """Passphrase de CRÉATION : saisie deux fois, comparée. Retourne str ou None.

        La confirmation est ici indispensable et ne l'est nulle part ailleurs : à la
        création il n'existe aucune passphrase de référence, donc rien qui puisse
        rattraper une faute de frappe. Ailleurs, le déchiffrement amont fait foi.
        """
        d = tk.Toplevel(parent)
        d.title('Nouvelle table de secrets')
        d.transient(parent)
        out = {}
        f = ttk.Frame(d, padding=12)
        f.pack(fill='both', expand=True)
        ttk.Label(f, text="Choisis le mot de passe maître (P2) qui protégera tes\n"
                          "identifiants. Il te sera demandé à chaque collecte.",
                  justify='left').grid(row=0, column=0, columnspan=2, sticky='w',
                                       pady=(0, 10))
        ttk.Label(f, text='Mot de passe :', width=16).grid(row=1, column=0, sticky='w')
        v1 = tk.StringVar()
        e1 = ttk.Entry(f, textvariable=v1, width=28, show='•')
        e1.grid(row=1, column=1, pady=3)
        ttk.Label(f, text='Confirmer :', width=16).grid(row=2, column=0, sticky='w')
        v2 = tk.StringVar()
        ttk.Entry(f, textvariable=v2, width=28, show='•').grid(row=2, column=1, pady=3)
        ttk.Label(f, text='Sans lui, tes identifiants sont irrécupérables.',
                  style='Hint.TLabel').grid(row=3, column=1, sticky='w')

        def ok():
            if not v1.get():
                messagebox.showwarning('Champ requis',
                                       'Le mot de passe ne peut pas être vide.',
                                       parent=d)
                return
            if v1.get() != v2.get():
                messagebox.showwarning('Confirmation',
                                       'Les deux saisies diffèrent.', parent=d)
                v2.set('')
                return
            out['v'] = v1.get()
            d.destroy()

        br = ttk.Frame(f)
        br.grid(row=4, column=0, columnspan=2, pady=(12, 0))
        ttk.Button(br, text='Créer', command=ok).pack(side='left', padx=4)
        ttk.Button(br, text='Annuler', command=d.destroy).pack(side='left', padx=4)
        e1.focus_set()
        d.wait_visibility()
        d.grab_set()
        d.wait_window()
        return out.get('v')

    def _credentials_unlock(self, parent):
        """Point d'entrée UNIQUE des deux portes : rend (chemin, passphrase) prêts à
        l'emploi, ou (None, None) si l'utilisateur renonce.

        **Crée la table si elle n'existe pas** — sans ça, un utilisateur en install
        fraîche resterait renvoyé au terminal (`gpg -c`) pour son tout premier
        identifiant, c'est-à-dire au seul geste qui pose ses mots de passe en clair
        sur le disque. Trois états :
          1. table chiffrée présente → demander la passphrase (le déchiffrement la valide) ;
          2. table en CLAIR présente (chemin manuel interrompu, le `gpg -c` oublié) →
             la reprendre, la chiffrer, puis **effacer le clair** ;
          3. rien → table vide, qui se remplira site par site.
        """
        path = self._credentials_file()
        clear = path.with_name(path.name[:-4]) if path.name.endswith('.gpg') else None

        if not path.exists():
            seed, src = None, None
            if clear and clear.exists():
                try:
                    seed = clear.read_text(encoding='utf-8')   # install antérieure
                    src = clear
                except OSError:
                    seed = None
            msg = (f"Aucune table de secrets à :\n{path}\n\n"
                   "La créer maintenant ?")
            if src:
                msg += (f"\n\nLe fichier en clair {src.name} sera repris, "
                        "chiffré, puis effacé.")
            if not messagebox.askyesno("Créer la table", msg, parent=parent):
                return None, None
            pw = self._ask_new_passphrase(parent)
            if not pw:
                return None, None
            err = gpg_creds.create_table(path, pw, seed)
            if err:
                messagebox.showerror('Création impossible', err, parent=parent)
                return None, None
            if src:
                try:
                    src.unlink()          # le clair ne survit pas au chiffrement
                except OSError as e:
                    messagebox.showwarning(
                        'Clair non effacé',
                        f"La table est chiffrée, mais {src.name} n'a pas pu être "
                        f"supprimé :\n{e}\n\nEfface-le à la main : il contient tes "
                        "mots de passe en clair.", parent=parent)
            messagebox.showinfo('Table créée', f'{path.name} est créée et chiffrée.',
                                parent=parent)
            return path, pw

        pw = simpledialog.askstring("Secrets de collecte",
                                    f'Passphrase de {path.name} :',
                                    show='•', parent=parent)
        if not pw:
            return None, None
        _, err = gpg_creds.decrypt_table(path, pw)   # valide la passphrase
        if err:
            messagebox.showerror('Lecture impossible', err, parent=parent)
            return None, None
        return path, pw

    def _credential_entry_dialog(self, parent, cid=None, login='', passe=''):
        """Formulaire d'une entrée `.gpg`. cid=None → création. Retourne (réf, id,
        passe).

        Vocabulaire aligné sur la table elle-même : Réf = la clé, Identifiant = le
        login du site, Passe = le secret. Les TROIS colonnes sont éditables et
        préchargées comme dans le fichier — changer la Réf en édition RENOMME la
        ligne (l'appelant s'en charge). La passe est en clair (elle l'est déjà dans
        la liste) : ce qu'on voit est ce qui sera écrit, aucune règle cachée.
        """
        creating = cid is None
        d = tk.Toplevel(parent)
        d.title('Nouvelle réf' if creating else 'Modifier la réf')
        d.transient(parent)
        out = {}
        f = ttk.Frame(d, padding=10)
        f.pack(fill='both', expand=True)

        ttk.Label(f, text='Réf :', width=14).grid(row=0, column=0, sticky='w')
        v_id = tk.StringVar(value=cid or '')
        e_id = ttk.Entry(f, textvariable=v_id, width=30)
        e_id.grid(row=0, column=1, pady=3)

        ttk.Label(f, text='Identifiant :', width=14).grid(row=1, column=0, sticky='w')
        v_log = tk.StringVar(value=login)
        e_log = ttk.Entry(f, textvariable=v_log, width=30)
        e_log.grid(row=1, column=1, pady=3)

        ttk.Label(f, text='Passe :', width=14).grid(row=2, column=0, sticky='w')
        v_pw = tk.StringVar(value=passe)
        ttk.Entry(f, textvariable=v_pw, width=30).grid(row=2, column=1, pady=3)

        def ok():
            if not v_id.get().strip():
                messagebox.showwarning('Champ requis',
                                       'La réf est obligatoire.', parent=d)
                return
            out['v'] = (v_id.get().strip(), v_log.get().strip(), v_pw.get())
            d.destroy()

        br = ttk.Frame(f)
        br.grid(row=4, column=0, columnspan=2, pady=(10, 0))
        ttk.Button(br, text='Valider', command=ok).pack(side='left', padx=4)
        ttk.Button(br, text='Annuler', command=d.destroy).pack(side='left', padx=4)
        (e_id if creating else e_log).focus_set()
        # `grab_set` sur une fenêtre pas encore mappée lève « window not viewable ».
        d.wait_visibility()
        d.grab_set()
        d.wait_window()
        return out.get('v')

    def _delete_credential(self, path, pw, cid, parent):
        """Supprime la ligne `.gpg` — ET RIEN D'AUTRE. True si fait.

        Cette porte est fidèle au `.gpg` : elle ne lit ni n'écrit `config.ini`. Un
        site qui pointait cette Réf n'est pas modifié — il pointe désormais une entrée
        absente (pendante), état bénin et réparable (reposer la Réf depuis l'onglet
        Sites, ou un tool d'audit). Savoir QUI pointe la Réf exigerait de croiser
        config.ini, ce que cette porte s'interdit ; l'avertissement reste donc
        générique.
        """
        msg = (f"Supprimer le secret « {cid} » de la table ?\n\n"
               "Un site qui le pointe (onglet Sites) devra pointer une autre Réf.\n"
               f"Une sauvegarde {path.name}.bak est conservée.")
        if not messagebox.askyesno('Supprimer', msg, parent=parent):
            return False
        e = gpg_creds.delete_entry(path, pw, cid)
        if e:
            messagebox.showerror('Suppression impossible', e, parent=parent)
            return False
        return True

    def _open_credentials_manager(self):
        """Porte Secrets (onglet Paramètres) : la table `.gpg`, et rien qu'elle.

        Fidèle au fichier chiffré — colonnes `Réf | Identifiant`, aucune lecture de
        config.ini (donc pas de « Utilisé par », qui coûterait un croisement config).
        Add / edit / delete portent sur les lignes du `.gpg`. L'autre moitié du pont
        — la Réf que chaque site pointe — se pose dans le cadre « Authentification » de l'onglet
        Sites : deux gestes, deux fichiers, comme avant la GUI.
        """
        path, pw = self._credentials_unlock(self.root)
        if not path:
            return

        dlg = tk.Toplevel(self.root)
        dlg.title('Table chiffrée (GPG)')
        dlg.transient(self.root)
        dlg.geometry('720x380')
        dlg.minsize(560, 300)

        ttk.Label(dlg, text=f'{path.name} — également éditable à la main '
                            '(gpg -d / gpg -c).',
                  style='Hint.TLabel', wraplength=690,
                  justify='left').pack(anchor='w', padx=10, pady=(8, 4))

        # Barre d'actions réservée AVANT l'arbre : `pack` sert les widgets dans
        # l'ordre de déclaration, donc un arbre en expand=True posé d'abord
        # chasserait les boutons hors du cadre tant qu'on n'agrandit pas.
        btn_row = ttk.Frame(dlg)
        btn_row.pack(side='bottom', fill='x', padx=10, pady=8)
        grp = ttk.LabelFrame(btn_row, text='Secret', padding=4)
        grp.pack(side='left')

        # Les trois colonnes du fichier, passe comprise : la porte est fidèle à la
        # table chiffrée (déjà déchiffrée ici) → montrer la passe évite les fautes
        # de frappe silencieuses. Rien de plus exposé qu'un `gpg -d` sur le fichier.
        tree_f = ttk.Frame(dlg)
        tree_f.pack(fill='both', expand=True, padx=10)
        tree = ttk.Treeview(tree_f, columns=('login', 'passe'),
                            show='tree headings', selectmode='browse')
        tree.heading('#0', text='Réf')
        tree.column('#0', width=160)
        tree.heading('login', text='Identifiant')
        tree.column('login', width=230)
        tree.heading('passe', text='Passe')
        tree.column('passe', width=170)
        tree.pack(side='left', fill='both', expand=True)
        sb = ttk.Scrollbar(tree_f, orient='vertical', command=tree.yview)
        sb.pack(side='right', fill='y')
        tree.configure(yscrollcommand=sb.set)

        state = {'pw': pw}

        def _known():
            """{réf: login} — pour tester l'existence / préremplir l'édition."""
            rows, e = gpg_creds.read_entries(path, state['pw'])
            if e:
                messagebox.showerror('Lecture impossible', e, parent=dlg)
                return None
            return dict(rows)

        def refresh(select=None):
            rows, e = gpg_creds.read_entries(path, state['pw'], with_password=True)
            if e:
                messagebox.showerror('Lecture impossible', e, parent=dlg)
                return
            tree.delete(*tree.get_children())
            for cid, login, passe in rows:
                tree.insert('', 'end', iid=cid, text=cid, values=(login, passe))
            if select and tree.exists(select):
                tree.selection_set(select)
                tree.see(select)
            _gate()

        def _gate(_evt=None):
            has = bool(tree.selection())
            b_edit.configure(state='normal' if has else 'disabled')
            b_del.configure(state='normal' if has else 'disabled')

        def add():
            known = _known()
            if known is None:
                return
            v = self._credential_entry_dialog(dlg)
            if not v:
                return
            cid, login, pwd = v
            if cid in known and not messagebox.askyesno(
                    'Réf existante',
                    f"« {cid} » existe déjà.\n\nÉcraser son contenu ?", parent=dlg):
                return
            _, e = gpg_creds.upsert_entry(path, state['pw'], cid, login, pwd or '')
            if e:
                messagebox.showerror('Écriture impossible', e, parent=dlg)
                return
            refresh(select=cid)

        def edit():
            sel = tree.selection()
            if not sel:
                return
            old_cid = sel[0]
            rows, e = gpg_creds.read_entries(path, state['pw'], with_password=True)
            if e:
                messagebox.showerror('Lecture impossible', e, parent=dlg)
                return
            table = {c: (l, p) for c, l, p in rows}
            old_login, old_passe = table.get(old_cid, ('', ''))
            v = self._credential_entry_dialog(dlg, old_cid, old_login, old_passe)
            if not v:
                return
            new_cid, login, passe = v
            renamed = new_cid != old_cid
            if renamed and new_cid in table and not messagebox.askyesno(
                    'Réf existante',
                    f"« {new_cid} » existe déjà.\n\nÉcraser son contenu ?", parent=dlg):
                return
            _, e = gpg_creds.upsert_entry(path, state['pw'], new_cid, login, passe)
            if e:
                messagebox.showerror('Écriture impossible', e, parent=dlg)
                return
            if renamed:
                # Renommer = écrire la nouvelle ligne (ci-dessus) puis retirer l'ancienne.
                e = gpg_creds.delete_entry(path, state['pw'], old_cid)
                if e:
                    messagebox.showerror('Suppression impossible', e, parent=dlg)
                    return
            refresh(select=new_cid)

        def delete():
            sel = tree.selection()
            if sel and self._delete_credential(path, state['pw'], sel[0], dlg):
                refresh()

        b_add = ttk.Button(grp, text='➕', width=3, command=add)
        b_add.pack(side='left', padx=1)
        b_edit = ttk.Button(grp, text='✏', width=3, command=edit)
        b_edit.pack(side='left', padx=1)
        b_del = ttk.Button(grp, text='✖', width=3, command=delete)
        b_del.pack(side='left', padx=1)
        ttk.Button(btn_row, text='Fermer', command=dlg.destroy).pack(side='right')

        tree.bind('<<TreeviewSelect>>', _gate)
        tree.bind('<Double-1>', lambda _e: edit() if tree.selection() else None)
        refresh()
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

