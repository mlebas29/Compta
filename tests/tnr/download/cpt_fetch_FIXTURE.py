#!/usr/bin/env python3
"""cpt_fetch_FIXTURE.py — connecteur FICTIF pour le TNR hermétique (#146).

N'est PAS un vrai site : sert uniquement à exercer la plomberie PARTAGÉE de
`BaseFetcher` (cycle launch/run/close, motif `expect_download → save_as →
reject_saved_if_html`, garde #137) contre un vrai download Playwright servi
par un `http.server` local — sans credential, 2FA ni réseau externe.

⚠ Vit sous `tests/tnr/download/` (PAS à la racine) pour ne PAS être ramassé
par la découverte de sites de l'appli (`_discover_sites` globe `cpt_fetch_*.py`
en racine + `custom/`) : ce dossier n'est ajouté à `sys.path` que par le
scénario `tnr_download.py`. Zéro site fantôme en GUI/config.

Piloté par le runner : `base_url` (l'URL du serveur local, port choisi par
l'OS) et `target` (chemin à cliquer) sont injectés à la construction, car il
n'existe pas de section `[FIXTURE]` dans `config.ini`.
"""

from inc_fetch import BaseFetcher

DOWNLOAD_TIMEOUT_S = 30


class FixtureFetcher(BaseFetcher):
    """Fetcher minimal : va sur la page d'accueil du serveur local, clique le
    lien de download demandé, sauve le fichier et applique le garde HTML —
    exactement le motif des 11 vrais fetchers, mais sur une origine fictive."""

    def __init__(self, verbose=False, base_url='', target='/statement.csv'):
        # Pas de section [FIXTURE] : __init__ retombe sur les fallbacks
        # (base_url='', credential_id=None, dossier='FIXTURE'). On surcharge
        # base_url ensuite avec l'URL réelle du serveur (port OS-choisi).
        super().__init__('FIXTURE', 'cpt_fetch_FIXTURE', verbose=verbose)
        self.base_url = base_url
        self._target = target
        # La page d'accueil expose deux liens (#csv / #expired) ; on clique
        # celui qui correspond à la cible demandée.
        self._link_id = 'csv' if 'statement' in target else 'expired'

    def run(self):
        self.page.goto(self.base_url + '/', wait_until='domcontentloaded')
        dest = self.dropbox_dir / 'statement.csv'
        self.dropbox_dir.mkdir(parents=True, exist_ok=True)
        with self.page.expect_download(
                timeout=DOWNLOAD_TIMEOUT_S * 1000) as dl_info:
            self.page.click(f'#{self._link_id}')
        dl_info.value.save_as(str(dest))
        # Garde #137 : un download au CONTENU HTML (page login servie en 200)
        # est refusé et supprimé → run() renvoie False (attendu pour /expired).
        if not self.reject_saved_if_html(dest, 'FIXTURE'):
            return False
        return True
