#!/usr/bin/env python3
"""
tnr_fetch.py — TNR unitaire de collecte RÉELLE (validation assistée).

Couvre la couche `cpt_fetch_*.py` (Playwright, DOM live, sélecteurs,
enchaînement `run()`) que `tnr_format`/`tnr_pipe` ne voient JAMAIS : eux
partent de fixtures déjà téléchargées. NON automatisable (2FA + credential
+ réseau) → lancé à la main, jamais ramassé par un composite unattended
(un composite sélectionne explicitement les unitaires qu'il chaîne).

Sélection des sites (dérivée de config.ini, source de vérité) :
  python3 tests/tnr_fetch.py                 # [sites] enabled (défaut)
  python3 tests/tnr_fetch.py --all           # toute section config avec un fetcher
  python3 tests/tnr_fetch.py SOCGEN,WISE     # liste explicite (casse libre)
  python3 tests/tnr_fetch.py --list          # inventaire des sites + périmètre

Mécanique par site :
  1. VRAI fetch → dropbox SANDBOX (tests/tnr/fetch/dropbox/<SITE>, gitignoré) ;
  2. assertions d'INVARIANTS (pas de golden ni --update — donnée live) :
     - au moins un fichier collecté ;
     - aucun fichier n'est du HTML (looks_like_html — exerce le garde #137) ;
     - cpt_format_<SITE>.format_site() parse sans exception → ≥ 1 opération ;
  3. verdict par site ✓/✗ + raison.

Périmètre v1 : fetchers navigateur (BaseFetcher). Les fetchers « script-style »
(API/JSON, sans classe BaseFetcher) sont SKIP : sandbox non redirigeable
in-process (et certains sont destructifs à la source, cf. #144).
"""

import argparse
import importlib
import shutil
import sys
from pathlib import Path

_name = Path(__file__).stem.removeprefix('tnr_')
SCENARIO_DIR = Path(__file__).parent / 'tnr' / _name
SANDBOX = SCENARIO_DIR / 'dropbox'

sys.path.insert(0, str(Path(__file__).parent))
from tnr_lib import find_code_root

CODE_ROOT = find_code_root(__file__)
sys.path.insert(0, str(CODE_ROOT))

# inc_bootstrap câble sys.path vers custom/ → fetchers/formats privés
# (sites sous custom/) importables comme les publics.
import inc_bootstrap  # noqa: F401,E402
import inc_fetch  # noqa: E402  — expose le même objet config que les fetchers
import inc_format  # noqa: E402  — is_browser_fetcher (source unique, partagé cpt_fetch)
from inc_fetch import BaseFetcher  # noqa: E402


def _discover_sites():
    """Univers des sites = tous les cpt_fetch_*.py présents (PUB + custom/).
    Sert à résoudre la casse d'une liste explicite et à l'inventaire --list."""
    seen = set()
    for d in (CODE_ROOT, CODE_ROOT / 'custom'):
        if not d.is_dir():
            continue
        for f in d.glob('cpt_fetch_*.py'):
            seen.add(f.stem.removeprefix('cpt_fetch_'))
    return sorted(seen)


def _enabled_set():
    """Noms (MAJ) de [sites] enabled du config.ini de l'instance."""
    raw = inc_fetch.config.get('sites', 'enabled', fallback='')
    return {s.strip().upper() for s in raw.split(',') if s.strip()}


def _config_sites():
    """Noms (MAJ) des sections config.ini (hors sections non-site)."""
    return {s.upper() for s in inc_fetch.config.sections()}


SITES = _discover_sites()


def _find_fetcher_class(module):
    """Classe <Site>Fetcher(BaseFetcher) DÉFINIE dans le module (pas l'import)."""
    for obj in vars(module).values():
        if (isinstance(obj, type) and issubclass(obj, BaseFetcher)
                and obj is not BaseFetcher
                and obj.__module__ == module.__name__):
            return obj
    return None


def _assert_artifacts(site, site_dir):
    """Invariants sur les fichiers collectés. Retourne (ok, message)."""
    files = ([p for p in site_dir.iterdir() if p.is_file()]
             if site_dir.is_dir() else [])
    if not files:
        return False, "aucun fichier collecté"

    # Pas de HTML servi à la place du relevé (exerce le garde #137).
    for p in files:
        try:
            head = p.read_bytes()[:512]
        except OSError:
            continue
        if BaseFetcher.looks_like_html(head):
            return False, f"fichier HTML au lieu du relevé : {p.name}"

    # Le format réel doit parser sans exception et produire ≥ 1 opération.
    try:
        mod = importlib.import_module(f'cpt_format_{site}')
        ops, _pos = mod.format_site(site_dir, verbose=False)
    except Exception as e:
        return False, f"format: {e}"
    if not ops:
        return False, "format: 0 opération produite"

    return True, f"OK ({len(files)} fichier(s), {len(ops)} op)"


def run_fetch(site):
    """Fetch réel dans le sandbox + assertions. Retourne (status, message)."""
    if not inc_format.is_browser_fetcher(site, CODE_ROOT):
        return 'SKIP', "fetcher script-style (API) — hors périmètre v1"

    try:
        mod = importlib.import_module(f'cpt_fetch_{site}')
    except Exception as e:
        return 'SKIP', f"import cpt_fetch_{site}: {e}"

    fetcher_class = _find_fetcher_class(mod)
    if fetcher_class is None:
        return 'SKIP', "aucune classe BaseFetcher trouvée"

    site_dir = SANDBOX / site
    if site_dir.exists():
        shutil.rmtree(site_dir)  # run frais : n'assert que sur cette collecte
    site_dir.mkdir(parents=True, exist_ok=True)

    try:
        fetcher = fetcher_class(verbose=False)
    except Exception as e:
        return 'FAIL', f"instanciation: {e}"

    # Sandbox : redirige l'écriture par instance (zéro mutation du config global).
    fetcher.dropbox_dir = site_dir

    # Credential-gating : credential absent sur cette machine → non applicable.
    if fetcher.credential_id:
        user, pwd = fetcher.load_gpg_credentials()
        if not user or not pwd:
            return 'SKIP', "credential GPG indisponible (absent ou non déchiffré)"

    try:
        fetcher.launch_browser()
        success = fetcher.run()
    except KeyboardInterrupt:
        return 'FAIL', "interrompu"
    except Exception as e:
        return 'FAIL', f"run(): {e}"
    finally:
        try:
            fetcher.close()
        except Exception:
            pass

    if not success:
        return 'FAIL', "run() a renvoyé un échec"

    ok, msg = _assert_artifacts(site, site_dir)
    return ('OK' if ok else 'FAIL'), msg


def main():
    parser = argparse.ArgumentParser(
        description="TNR unitaire de collecte réelle (validation assistée).",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('sites', nargs='*',
                        help="Liste explicite de sites (ex: SOCGEN SOCGEN,WISE). "
                             "Prime sur --all/--enabled.")
    parser.add_argument('--all', action='store_true',
                        help="Tous les sites configurés (toute section config "
                             "ayant un fetcher), pas seulement [sites] enabled.")
    parser.add_argument('--enabled', action='store_true',
                        help="Sites [sites] enabled (défaut si aucune sélection).")
    parser.add_argument('--list', action='store_true',
                        help="Inventaire des sites détectés, puis quitte.")
    args = parser.parse_args()

    if args.list:
        enabled = _enabled_set()
        configured = _config_sites()
        print("Sites détectés (cpt_fetch_*.py) — [E]=enabled [C]=configuré :")
        for s in SITES:
            kind = ("navigateur" if inc_format.is_browser_fetcher(s, CODE_ROOT)
                    else "script-style (SKIP v1)")
            flags = ('E' if s.upper() in enabled else '-') \
                    + ('C' if s.upper() in configured else '-')
            print(f"  [{flags}] {s:15} {kind}")
        return 0

    # Sélection, par priorité :
    #   1. liste explicite (args, séparés par espace et/ou virgule) ;
    #   2. --all  = toute section config ayant un fetcher ;
    #   3. défaut / --enabled = [sites] enabled.
    # Casse résolue au nom canonique (sites en MAJ sauf « quotes »).
    requested = []
    for arg in args.sites:
        requested += [s.strip() for s in arg.split(',') if s.strip()]

    canon = {s.upper(): s for s in SITES}
    unknown = []
    if requested:
        sites = []
        for r in requested:
            c = canon.get(r.upper())
            (sites if c else unknown).append(c or r)
    elif args.all:
        configured = _config_sites()
        sites = [s for s in SITES if s.upper() in configured]
    else:  # défaut = enabled
        enabled = _enabled_set()
        sites = [s for s in SITES if s.upper() in enabled]

    mode = ("liste explicite" if requested
            else "--all (sites configurés)" if args.all
            else "[sites] enabled (défaut)")
    print("=" * 60)
    print("TNR collecte réelle — validation assistée (2FA/credential requis)")
    print(f"  sélection : {mode}")
    print(f"  sandbox   : {SANDBOX}")
    print("=" * 60)

    for u in unknown:
        print(f"  {u:15} INCONNU — sites : {', '.join(SITES)}")

    if not sites and not unknown:
        print("  (aucun site sélectionné — voir --list, --all, ou une liste explicite)")

    passed = failed = skipped = 0
    failures = []
    for site in sites:
        print(f"\n→ {site}...", flush=True)
        status, message = run_fetch(site)
        if status == 'OK':
            print(f"  {site:15} ✓ {message}")
            passed += 1
        elif status == 'SKIP':
            print(f"  {site:15} SKIP ({message})")
            skipped += 1
        else:
            print(f"  {site:15} ✗ ÉCHEC — {message}")
            failed += 1
            failures.append(site)

    print("\n" + "=" * 60)
    print(f"Résultat : {passed} OK, {failed} ÉCHEC, {skipped} SKIP")
    if failures:
        print(f"Échecs : {', '.join(failures)}")
    return 0 if failed == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
