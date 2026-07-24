#!/usr/bin/env python3
"""tnr_download.py — TNR HERMÉTIQUE de la plomberie de download (#146).

Complément AUTOMATISABLE de `tnr_fetch` (#145, réel/manuel, credential+2FA) :
exerce la couche PARTAGÉE de `BaseFetcher` — cycle `launch/run/close`, motif
`expect_download → save_as → dropbox_dir`, et le garde #137
(`reject_saved_if_html`/`looks_like_html`) — via un VRAI download Playwright
servi par un `http.server` local, SANS credential / 2FA / réseau externe.

Ne couvre PAS les sélecteurs site-spécifiques des 11 vrais fetchers (impossible
sans leur DOM) → complémentaire de #145, pas substitut.

Deux couches :
  • unit  (C) : `BaseFetcher.looks_like_html` sur octets HTML/CSV → tourne
                PARTOUT (aucun navigateur), VPS nu inclus ;
  • live  (A) : serveur local (127.0.0.1, port choisi par l'OS) + fetcher
                fictif → deux sous-cas :
                  - /statement.csv (CSV valide) → conservé, format → ≥ 1 op ;
                  - /expired (page login HTML en 200, servie en attachment) →
                    le garde DOIT rejeter et supprimer le fichier.
                Chrome requis → SKIP propre si le navigateur est absent
                (machine sans navigateur : VPS nu).

Usage : python3 tests/tnr_download.py
"""

import http.server
import shutil
import socketserver
import sys
import threading
from pathlib import Path

SCENARIO_DIR = Path(__file__).parent / 'tnr' / 'download'
SANDBOX = SCENARIO_DIR / 'dropbox'

sys.path.insert(0, str(Path(__file__).parent))
from tnr_lib import find_code_root  # noqa: E402

CODE_ROOT = find_code_root(__file__)
sys.path.insert(0, str(CODE_ROOT))

# inc_bootstrap câble sys.path vers custom/ (comme les vrais fetchers).
import inc_bootstrap  # noqa: F401,E402
from inc_fetch import BaseFetcher  # noqa: E402

# Modules fixture (fetcher/format fictifs), volontairement HORS de la racine
# (sinon site fantôme dans la découverte de l'appli) → ajoutés ici seulement.
sys.path.insert(0, str(SCENARIO_DIR))

VALID_CSV = (b'date,label,amount\r\n'
             b'2026-01-05,Cafe,3.50\r\n'
             b'2026-01-06,Salaire,1234.00\r\n')

LOGIN_HTML = (b'<!doctype html><html><head><title>Connexion</title></head>'
              b'<body><form action="/login"><input name="user">'
              b'<input name="pass" type="password"></form></body></html>')

INDEX_HTML = (b'<!doctype html><html><body>'
              b'<a id="csv" href="/statement.csv" download>csv</a> '
              b'<a id="expired" href="/expired" download>expired</a>'
              b'</body></html>')


class _Handler(http.server.BaseHTTPRequestHandler):
    """Sert : / (page à 2 liens), /statement.csv (CSV valide en attachment),
    /expired (page login HTML servie 200 en attachment = piège #137)."""

    def _send(self, ctype, body, filename=None):
        self.send_response(200)
        self.send_header('Content-Type', ctype)
        if filename:
            self.send_header('Content-Disposition',
                             f'attachment; filename="{filename}"')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == '/':
            self._send('text/html', INDEX_HTML)
        elif self.path == '/statement.csv':
            self._send('text/csv', VALID_CSV, filename='statement.csv')
        elif self.path == '/expired':
            # HTML servi en attachment → download au CONTENU HTML : le garde
            # lit les octets sauvés (pas le content-type) et doit rejeter.
            self._send('text/html', LOGIN_HTML, filename='statement.csv')
        else:
            self.send_error(404)

    def log_message(self, *args):  # silencieux
        pass


class _Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


# --- Couche unit (C) : le garde, sans navigateur -----------------------------

def run_unit():
    """Teste `looks_like_html` sur des octets connus. Retourne (ok, message)."""
    cases = [
        (b'<!doctype html><html>...', True, 'doctype'),
        (b'  \n  <HTML lang="fr">', True, 'html avec espaces/casse'),
        (b'date,label,amount\r\n2026-01-05,x,1', False, 'CSV'),
        (b'%PDF-1.4\n...', False, 'PDF'),
        (b'', False, 'vide'),
    ]
    for data, expected, label in cases:
        got = BaseFetcher.looks_like_html(data)
        if got != expected:
            return False, f"looks_like_html({label}) = {got}, attendu {expected}"
    return True, f"garde HTML OK ({len(cases)} cas)"


# --- Couche live (A) : vrai download navigateur ------------------------------

def _run_fixture(base_url, target):
    """Instancie le fetcher fictif, lance le navigateur, exécute run(), ferme.
    Retourne (success_bool, exception_or_None). L'exception de launch (Chrome
    absent) remonte au caller pour un SKIP propre."""
    import cpt_fetch_FIXTURE
    fetcher = cpt_fetch_FIXTURE.FixtureFetcher(
        verbose=False, base_url=base_url, target=target)
    fetcher.dropbox_dir = SANDBOX  # sandbox : zéro écriture dropbox réel
    # Profil Chrome sous le sandbox (nettoyé au run suivant) plutôt qu'à la
    # racine du dépôt → tous les artefacts du test regroupés.
    fetcher._chrome_profile_dir = SANDBOX / '.chrome_profile'
    fetcher.launch_browser()       # peut lever si Chrome absent → SKIP
    try:
        success = fetcher.run()
    finally:
        try:
            fetcher.close()
        except Exception:
            pass
    return success


def run_live():
    """Deux sous-cas contre le serveur local. Retourne (status, message)
    où status ∈ {'OK','FAIL','SKIP'}."""
    if SANDBOX.exists():
        shutil.rmtree(SANDBOX)
    SANDBOX.mkdir(parents=True, exist_ok=True)

    server = _Server(('127.0.0.1', 0), _Handler)
    port = server.server_address[1]
    base_url = f'http://127.0.0.1:{port}'
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    try:
        # Sous-cas 1 : CSV valide → conservé + parse ≥ 1 op.
        try:
            ok = _run_fixture(base_url, '/statement.csv')
        except Exception as e:
            msg = str(e).splitlines()[0]
            if 'chrome' in msg.lower() or 'executable' in msg.lower() \
                    or 'browser' in msg.lower():
                return 'SKIP', f"navigateur indisponible ({msg})"
            return 'FAIL', f"lancement/run (valide): {msg}"
        dest = SANDBOX / 'statement.csv'
        if not ok:
            return 'FAIL', "CSV valide rejeté par run() (garde trop strict ?)"
        if not dest.is_file():
            return 'FAIL', "CSV valide non sauvé"
        if BaseFetcher.looks_like_html(dest.read_bytes()[:512]):
            return 'FAIL', "fichier sauvé est du HTML (serveur/fixture cassé)"
        import cpt_format_FIXTURE
        ops, _pos = cpt_format_FIXTURE.format_site(SANDBOX, verbose=False)
        if not ops:
            return 'FAIL', "format: 0 opération produite sur le CSV valide"

        # Sous-cas 2 : page HTML piège → le garde DOIT rejeter (test positif).
        try:
            ok = _run_fixture(base_url, '/expired')
        except Exception as e:
            return 'FAIL', f"lancement/run (expired): {str(e).splitlines()[0]}"
        dest = SANDBOX / 'statement.csv'
        if ok:
            return 'FAIL', "garde #137 n'a PAS rejeté la page HTML piège"
        if dest.exists():
            return 'FAIL', "garde a rejeté mais n'a pas supprimé le fichier HTML"

        return 'OK', f"download OK ({len(ops)} op) + garde HTML rejette bien"
    finally:
        server.shutdown()
        server.server_close()
        # Leave-no-trace : le sandbox (CSV + profil Chrome) ne sert pas au
        # post-mortem (test hermétique, déterministe, messages explicites) →
        # nettoyé en fin comme le venv de tnr_install. Le rmtree d'entrée
        # reste un filet si un run précédent a été tué en cours.
        shutil.rmtree(SANDBOX, ignore_errors=True)


def main():
    print("=" * 60)
    print("TNR download hermétique (#146) — plomberie BaseFetcher + garde #137")
    print(f"  sandbox : {SANDBOX}")
    print("=" * 60)

    failed = 0

    ok, msg = run_unit()
    print(f"\n→ unit (garde, sans navigateur)")
    print(f"  {'✓' if ok else '✗ ÉCHEC —'} {msg}")
    if not ok:
        failed += 1

    status, msg = run_live()
    print(f"\n→ live (vrai download Playwright)")
    if status == 'OK':
        print(f"  ✓ {msg}")
    elif status == 'SKIP':
        print(f"  SKIP ({msg})")
    else:
        print(f"  ✗ ÉCHEC — {msg}")
        failed += 1

    print("\n" + "=" * 60)
    print(f"Résultat : {'OK' if failed == 0 else f'{failed} ÉCHEC'}")
    return 0 if failed == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
