#!/usr/bin/env python3
"""install_upgrade.py — point d'entrée UPGRADE consommateur (#94).

Geste utilisateur « le CHANGELOG annonce une version → je mets à jour mon
install ». Distinct de tool_pull (synchro dev commit/pull) : ici l'objet est
l'UPGRADE — tirer le nouveau CODE et amener l'install à l'état qu'il attend.

PUB seulement : le contenu du dépôt privé (custom/) relève du sync PRIVÉ, hors
scope d'un outil public (qui ne présume ni le remote ni le modèle du PRV). Poser
le CADRE vide custom/ reste OK — c'est structurel (ensure_custom_frame, #93).

Séquence (#94) :
  1. pull résilient PUB, --ff-only ; si histoires disjointes (merge-base vide,
     ex. clone d'avant un squash 🔄) → PROPOSE reclone.sh (backup+confirmation),
     jamais auto. Divergence / commits locaux → simplement signalé (pas reclone).
  2. rattrapages bénins idempotents : config+raccourci (install_fix), cadre
     custom/ (ensure_custom_frame). Toujours joués (geste explicite, pas gated
     sur « le pull a avancé »).
  3. report / propose les ajustements à CONSENTEMENT (migration classeur) via les
     probes partagées avec le GUI (inc_update, par import).

Idempotent : un second passage ne fait rien si tout est déjà à jour.

Usage :
  cd <racine du clone> && python3 install_upgrade.py
  python3 install_upgrade.py --check   # pull + rattrapages sautés, report seul
"""

import argparse
import subprocess
import sys
from pathlib import Path

import inc_update

BASE_DIR = Path(__file__).resolve().parent

GREEN = '\033[0;32m'; YELLOW = '\033[1;33m'; RED = '\033[0;31m'; NC = '\033[0m'


def _git(*args):
    """git -C BASE_DIR … → (rc, sortie combinée)."""
    p = subprocess.run(['git', '-C', str(BASE_DIR), *args],
                       capture_output=True, text=True)
    return p.returncode, ((p.stdout or '') + (p.stderr or '')).strip()


def _run_bash(snippet):
    """Snippet bash dans le clone (cwd=BASE_DIR) → (rc, sortie)."""
    p = subprocess.run(['bash', '-c', snippet], cwd=str(BASE_DIR),
                       capture_output=True, text=True)
    return p.returncode, ((p.stdout or '') + (p.stderr or '')).rstrip()


def resilient_pull():
    """Pull PUB --ff-only, résilient. PUB seul (le PRV custom/ = sync privé).

    Retourne 'ok' (avancé ou no-op) | 'reclone' (histoires disjointes) |
    'diverged' (divergence / commits locaux / conflit — pull bloqué).
    """
    _, head0 = _git('rev-parse', 'HEAD')
    rc, out = _git('pull', '--ff-only')
    if rc == 0:
        _, head1 = _git('rev-parse', 'HEAD')
        print(f'{GREEN}✓{NC} PUB ' + ('mis à jour.' if head0 != head1 else 'déjà à jour.'))
        return 'ok'

    # Échec ff-only : histoires disjointes (→ reclone) ou divergence (→ signaler) ?
    _git('fetch', '--quiet')
    rc_mb, mb = _git('merge-base', 'HEAD', 'origin/main')
    if rc_mb != 0 or not mb:
        # merge-base vide = histoires disjointes (clone fossile d'avant un squash 🔄).
        print(f'{YELLOW}⚠{NC} PUB : histoires disjointes (clone d\'avant une réécriture 🔄 ?).')
        return 'reclone'
    # merge-base non vide = divergence / commits locaux / conflit. PAS reclone.
    last = out.splitlines()[-1] if out else ''
    print(f'{RED}✗{NC} PUB : pull ff-only impossible (divergence / commits locaux / conflit).')
    if last:
        print(f'   git : {last}')
    return 'diverged'


def _run_interactive(snippet):
    """Bash héritant le terminal (stdin/stdout) dans BASE_DIR → rc."""
    return subprocess.run(['bash', '-c', snippet], cwd=str(BASE_DIR)).returncode


def propose_reclone():
    """Volet B — propose le re-clone (JAMAIS auto). Montre le plan (dry-run de
    reclone.sh) puis, sur consentement explicite EN TERMINAL, lance
    reclone.sh --reclone --yes (qui fait le backup complet + sa propre
    confirmation « oui »). Sans terminal : propose seulement, n'exécute rien.
    Retourne True si un re-clone a été lancé.
    """
    if not (BASE_DIR / 'reclone.sh').exists():
        print('   → reclone nécessaire mais reclone.sh introuvable ; voir CHANGELOG (procédure 🔄).')
        return False
    if not sys.stdin.isatty():
        # non interactif : on PROPOSE, jamais d'exécution destructive sans terminal.
        print('   → reclone recommandé : ./reclone.sh --reclone --yes (backup + confirmation).')
        return False
    print(f"{YELLOW}--- Plan de re-clone (simulation — rien n'est altéré) ---{NC}")
    _run_interactive('./reclone.sh --reclone')          # dry-run informatif
    try:
        ans = input('Lancer le re-clone maintenant (backup complet + clone frais) ? [oui/non] ').strip().lower()
    except EOFError:
        ans = ''
    if ans == 'oui':
        rc = _run_interactive('./reclone.sh --reclone --yes')   # backup + gate « oui » + reclone
        return rc == 0
    print('   Re-clone non lancé. Plus tard : ./reclone.sh --reclone --yes')
    return False


def apply_benign():
    """Étapes bénignes idempotentes. Retourne le nombre d'échecs."""
    failed = 0

    # config (normalize_config) + raccourci (setup_desktop) → délégués à
    # install_fix.sh : #94 « délègue à install_fix pour la config ».
    rc, out = _run_bash('./install_fix.sh')
    if out:
        print(out)
    if rc != 0:
        print(f'{RED}✗{NC} install_fix.sh a échoué (rc={rc})')
        failed += 1

    # cadre privé custom/ (#93) — rattrapage des installs antérieures à #93.
    # Structurel (pose un .git vide), pas un pull du contenu privé.
    rc, out = _run_bash('. ./inc_install.sh && ensure_custom_frame .')
    if out:
        print(out)
    if rc != 0:
        print(f'{RED}✗{NC} ensure_custom_frame a échoué (rc={rc})')
        failed += 1

    return failed


def report():
    """Report config (inc_update, par import). Retourne le nb de warnings.

    Le classeur n'est plus traité ici mais dans migrate() (volet C carte-driven).
    """
    warns = inc_update.check_config_obsolete(BASE_DIR / 'config.ini')
    for w in warns:
        print(f'{YELLOW}⚠{NC} {w}')
    return len(warns)


def _run_migration(tool):
    """Run le migrateur (shebang python3-uno ; auto-gate LO≥24.8 → exit 2 si trop
    ancienne). Le classeur est déjà couvert par le snapshot pré-run, donc pas de
    backup ici. Le hash sert juste à distinguer migration appliquée / no-op.
    Retourne {tool, result}."""
    import hashlib
    xlsx = BASE_DIR / 'comptes.xlsm'
    digest = lambda: hashlib.md5(xlsx.read_bytes()).hexdigest()
    before = digest()
    rc = _run_interactive(f'./{tool} comptes.xlsm')
    if rc == 0:
        if digest() == before:
            print(f'{GREEN}✓{NC} Classeur déjà à jour ({tool}) — rien migré.')
            return {'tool': tool, 'result': 'noop'}
        print(f'{GREEN}✓{NC} Migration appliquée ({tool}).')
        return {'tool': tool, 'result': 'applied'}
    if rc == 2:
        print(f'{RED}✗{NC} LibreOffice < 24.8 — migration refusée par {tool} (classeur inchangé).')
        print('   → migre depuis une machine LO≥24.8 (cf. Compta_upgrade.md).')
        return {'tool': tool, 'result': 'refused-lo'}
    print(f'{RED}✗{NC} {tool} a échoué (rc={rc}).')
    return {'tool': tool, 'result': 'failed'}


def _classeur_busy(xlsx):
    """Raisons rendant la migration UNO du classeur risquée : classeur ouvert
    (verrou LibreOffice `.~lock.NAME#`) ou appli GUI (`cpt_gui`) en cours.
    Écrire le `.xlsm` via UNO pendant qu'il est ouvert ailleurs = conflit /
    corruption. Retourne list[str] (vide = libre). Signaux portables Linux/Mac.
    """
    reasons = []
    lock = xlsx.parent / f'.~lock.{xlsx.name}#'
    if lock.exists():
        reasons.append('classeur ouvert dans LibreOffice')
    # motif `[c]pt_gui` (bracket trick) : matche le vrai process sans matcher le
    # shell qui porte cette commande pgrep dans sa propre ligne.
    rc, out = _run_bash("pgrep -f '[c]pt_gui.py'")
    if rc == 0 and out.strip():
        reasons.append('application Comptabilité (cpt_gui) en cours')
    return reasons


def migrate(check=False):
    """Volet C — migration classeur pilotée par la CARTE (upgrade_map.json).

    Origine = SCHEMA du classeur, cible = SCHEMA du code → chemin via la carte
    (inc_update.pending_migrations). Structurelles bloquantes : consentement +
    backup + run. Catch-up idempotent : proposé en option. Jamais en silence ;
    non-interactif (ou --check) = propose seulement. Retourne le nb de points
    bloquants signalés.
    """
    xlsx = BASE_DIR / 'comptes.xlsm'
    if not xlsx.exists():
        return {'issues': 0, 'migrations': []}
    from inc_excel_schema import SCHEMA_VERSION as code_schema

    problems = inc_update.validate_upgrade_map(BASE_DIR, code_schema)
    if problems:
        print(f'{RED}✗{NC} Carte de migration incohérente — migration suspendue :')
        for p in problems:
            print(f'   - {p}')
        return {'issues': 1, 'migrations': []}

    classeur_schema = inc_update.read_classeur_schema(xlsx)
    plan = inc_update.pending_migrations(BASE_DIR, classeur_schema, code_schema)

    if plan['below_floor']:
        print(f'{YELLOW}⚠{NC} Classeur trop ancien pour la migration automatique '
              f'(version {classeur_schema} sous le plancher de la carte).')
        print('   → migration manuelle : voir Compta_upgrade.md.')
        return {'issues': 1, 'migrations': []}

    # Garde : la migration écrit le .xlsm via UNO ; refuser si le classeur est
    # ouvert (verrou LO) ou l'appli tourne — ne tire QUE s'il y a vraiment une
    # migration à appliquer (sinon le run pull/config se poursuit normalement).
    pending = list(plan['structural'])
    if plan['catchup'] and not plan['structural']:
        pending.append(plan['catchup'])
    if pending and not check:
        busy = _classeur_busy(xlsx)
        if busy:
            print(f"{RED}✗{NC} Classeur non migré — {', '.join(busy)}.")
            print("   → ferme l'application et le classeur (LibreOffice), "
                  "puis relance ./install_upgrade.py.")
            # bloqué ≠ décliné : ne PAS avancer le stamp (l'avis #99 doit
            # persister jusqu'à migration réelle) ni clamer un run OK.
            return {'issues': len(pending), 'migrations': [], 'blocked': True}

    issues = 0
    ran = []
    interactive = (not check) and sys.stdin.isatty()

    # --- migrations structurelles bloquantes ---
    for m in plan['structural']:
        issues += 1
        print(f"{YELLOW}⚠{NC} Migration requise : SCHEMA {m['schema_from']}→{m['schema_to']} "
              f"({m['summary']}) — {m['tool']}.")
        if not interactive:
            print('   → consentement requis ; relance en terminal pour migrer.')
            continue
        if input('   Migrer maintenant (backup auto) ? [oui/non] ').strip().lower() == 'oui':
            ran.append(_run_migration(m['tool']))
        else:
            print('   Migration non lancée.')

    # --- catch-up idempotent (seulement si structurellement à jour) ---
    c = plan['catchup']
    if c and not plan['structural']:
        print(f"{YELLOW}ℹ{NC} Catch-up formules disponible : {c['summary']} "
              f"({c['tool']}, idempotent).")
        if interactive:
            if input('   Appliquer (backup auto) ? [oui/non] ').strip().lower() == 'oui':
                ran.append(_run_migration(c['tool']))
        else:
            print("   → optionnel ; relance en terminal pour l'appliquer.")

    return {'issues': issues, 'migrations': ran}


def _config_files():
    """Liste `$CONFIG_FILES` depuis inc_install.sh (source unique, pas de duplication)."""
    rc, out = _run_bash('. ./inc_install.sh && printf "%s" "$CONFIG_FILES"')
    return out.split() if rc == 0 else []


def _take_snapshot():
    """Snapshot COMPLET pré-mutation : copie `$CONFIG_FILES` (config* + classeur)
    dans `.upgrade-snapshot-<ts>/`, + `meta.json` AUTO-DESCRIPTIF
    `{ts, commit, from:{app_version, classeur_schema}, files}`. Retourne le nom du
    dossier (ou None). Point de restauration global (app via le commit, config &
    classeur via les copies) ; la version est dans le meta (log non requis)."""
    import json
    import shutil
    from datetime import datetime
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    snap = BASE_DIR / f'.upgrade-snapshot-{ts}'
    try:
        snap.mkdir(exist_ok=True)
        files = [f for f in _config_files() if (BASE_DIR / f).exists()]
        for f in files:
            shutil.copy2(BASE_DIR / f, snap / f)
        _, head = _git('rev-parse', 'HEAD')
        try:
            from inc_excel_schema import APP_VERSION
        except Exception:
            APP_VERSION = '?'
        meta = {'ts': ts, 'commit': head,
                'from': {'app_version': APP_VERSION,
                         'classeur_schema': inc_update.read_classeur_schema(BASE_DIR / 'comptes.xlsm')},
                'files': files}
        (snap / 'meta.json').write_text(json.dumps(meta), encoding='utf-8')
        return snap.name
    except OSError:
        return None


def _prune_snapshots(keep=10):
    """Garde les `keep` snapshots les plus récents (tri par ts = nom), supprime
    les plus vieux. Le JOURNAL n'est PAS purgé (historique forensique léger)."""
    import shutil
    snaps = sorted(p for p in BASE_DIR.glob('.upgrade-snapshot-*') if p.is_dir())
    for p in snaps[:-keep]:
        shutil.rmtree(p, ignore_errors=True)


def _snapshot_unchanged(snap_name):
    """True si tous les `$CONFIG_FILES` sont identiques à la copie du snapshot
    (→ ni config ni classeur n'ont bougé pendant le run)."""
    import filecmp
    snap = BASE_DIR / snap_name
    for f in _config_files():
        cur, ref = BASE_DIR / f, snap / f
        if cur.exists() != ref.exists():
            return False
        if cur.exists() and not filecmp.cmp(cur, ref, shallow=False):
            return False
    return True


def _discard_snapshot(name):
    import shutil
    if name:
        shutil.rmtree(BASE_DIR / name, ignore_errors=True)


def _snapshots_on_disk():
    """Snapshots existants (avec meta.json), triés par ts croissant."""
    return sorted(p for p in BASE_DIR.glob('.upgrade-snapshot-*') if (p / 'meta.json').exists())


def _list_snapshots():
    """`--liste` — points de restauration : chaque snapshot sur disque (`up`,
    `current_saved` d'un `back`, ou run interrompu), avec sa version (meta
    auto-descriptif) et, si dispo, le `to` depuis le journal."""
    import json
    snaps = _snapshots_on_disk()
    if not snaps:
        print('Aucun point de restauration.')
        return 0
    ctx = {}
    log = BASE_DIR / 'upgrade_log.jsonl'
    if log.exists():
        for line in log.read_text(encoding='utf-8').splitlines():
            try:
                e = json.loads(line)
            except ValueError:
                continue
            for k in ('snapshot', 'current_saved'):
                if e.get(k):
                    ctx[e[k]] = e
    print(f'{YELLOW}Points de restauration (./install_upgrade.py --restore <ts>) :{NC}')
    for p in snaps:
        meta = json.loads((p / 'meta.json').read_text(encoding='utf-8'))
        frm = meta.get('from', {})
        ts = p.name.replace('.upgrade-snapshot-', '')
        e = ctx.get(p.name, {})
        if e.get('op') == 'back':
            suffix = '  (état sauvé avant une restauration)'
        elif e.get('to'):
            suffix = f"  → app {e['to'].get('app_version')}, SCHEMA {e['to'].get('classeur_schema')}"
        else:
            suffix = ''
        print(f"  {ts}   app {frm.get('app_version')}, SCHEMA {frm.get('classeur_schema')}{suffix}")
    return 0


def _restore(ts, target):
    """`--restore <ts> [--only …]` — restaure `target` (all|config|xlsm|app) depuis
    le snapshot `<ts>`. Destructif → confirmation + snapshot de l'état courant
    d'abord (réversible, devient un nouveau point). Jamais auto (TTY requis)."""
    import json
    import shutil
    snap = BASE_DIR / f'.upgrade-snapshot-{ts}'
    if not (snap / 'meta.json').exists():
        print(f'{RED}✗{NC} Snapshot {ts} introuvable (cf. --liste).')
        return 1
    meta = json.loads((snap / 'meta.json').read_text(encoding='utf-8'))
    frm = meta.get('from', {})
    print(f"Restaurer {target} depuis {ts} "
          f"(app {frm.get('app_version')}, SCHEMA {frm.get('classeur_schema')}).")
    if not sys.stdin.isatty():
        print('   (non interactif — relance en terminal pour restaurer.)')
        return 1
    if input("   Confirmer (l'état courant sera sauvegardé) ? [oui/non] ").strip().lower() != 'oui':
        print('   Annulé.')
        return 0

    current = _take_snapshot()      # réversibilité (l'état courant devient un point)
    _prune_snapshots()
    restored = []
    do = lambda t: target in ('all', t)
    if do('config'):
        for f in meta['files']:
            if f != 'comptes.xlsm' and (snap / f).exists():
                shutil.copy2(snap / f, BASE_DIR / f)
        restored.append('config')
    if do('xlsm') and (snap / 'comptes.xlsm').exists():
        shutil.copy2(snap / 'comptes.xlsm', BASE_DIR / 'comptes.xlsm')
        restored.append('xlsm')
    if do('app') and meta.get('commit'):
        _, ahead = _git('rev-list', '@{u}..HEAD', '--count')
        if ahead.strip() not in ('', '0'):
            print(f'{RED}✗{NC} commits locaux présents — reset app refusé (sécurité).')
        else:
            rc, _o = _git('reset', '--hard', meta['commit'])
            restored.append('app') if rc == 0 else print(f'{RED}✗{NC} git reset a échoué.')

    print(f'{GREEN}✓{NC} Restauré : {restored or "rien"} (état courant sauvegardé : {current}).')
    _write_log({'op': 'back', 'restored': restored,
                'from_snapshot': snap.name, 'current_saved': current})
    return 0


def _disk_app_version():
    """APP_VERSION du code SUR DISQUE (post-pull), via un process FRAIS — le
    process courant a le module inc_excel_schema caché (valeur pré-pull)."""
    p = subprocess.run(
        ['python3', '-c', 'from inc_excel_schema import APP_VERSION; print(APP_VERSION)'],
        cwd=str(BASE_DIR), capture_output=True, text=True)
    return (p.stdout or '').strip() or '?'


def _write_log(record):
    """Journal forensique externe — `upgrade_log.jsonl` (gitignoré, per-instance).
    Trace l'état from→to et ce qu'install_upgrade a fait (migrations, backups
    conservés), pour retrouver/nettoyer après coup. JAMAIS relu pour décider
    (#94 : témoin, pas autorité). Best-effort : une erreur d'écriture n'interrompt rien.
    """
    import json
    from datetime import datetime
    rec = {'ts': datetime.now().isoformat(timespec='seconds'), **record}
    try:
        with open(BASE_DIR / 'upgrade_log.jsonl', 'a', encoding='utf-8') as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + '\n')
    except OSError:
        pass


def main():
    ap = argparse.ArgumentParser(
        description="Point d'entrée upgrade consommateur (#94).")
    ap.add_argument('--check', action='store_true',
                    help='report seul : pull et rattrapages sautés')
    ap.add_argument('--liste', action='store_true',
                    help='liste les points de restauration (snapshots) et quitte')
    ap.add_argument('--restore', metavar='TS',
                    help='restaure depuis le snapshot TS (cf. --liste)')
    ap.add_argument('--only', choices=['config', 'xlsm', 'app'],
                    help='restreint --restore à un composant (défaut : tout)')
    args = ap.parse_args()

    if not (BASE_DIR / 'cpt_gui.py').exists():
        print(f'{RED}✗{NC} Pas un clone Compta ({BASE_DIR})', file=sys.stderr)
        return 1

    if args.liste:
        return _list_snapshots()
    if args.restore:
        return _restore(args.restore, args.only or 'all')

    print(f"{YELLOW}=== install_upgrade — mise à jour de l'installation ==={NC}")

    # État INITIAL, lu AVANT le pull. from_app = le code qui tourne (pré-pull) ;
    # importer ici fige inc_excel_schema sur la version pré-pull pour tout le run
    # (cohérent : le nouveau code tiré s'applique au prochain lancement).
    from inc_excel_schema import APP_VERSION as from_app
    xlsx = BASE_DIR / 'comptes.xlsm'
    from_state = {'app_version': from_app,
                  'classeur_schema': inc_update.read_classeur_schema(xlsx)}

    # Snapshot COMPLET pré-mutation (jeté en fin si le run est NULL) ; head_before
    # pour détecter une avance de code.
    snapshot = None
    head_before = None
    if not args.check:
        snapshot = _take_snapshot()
        _, head_before = _git('rev-parse', 'HEAD')

    failed = 0
    status = None
    if args.check:
        print('(--check : pull et rattrapages sautés, report seul)')
    else:
        print(f'{YELLOW}--- Pull PUB (résilient) ---{NC}')
        status = resilient_pull()
        if status == 'reclone':
            _discard_snapshot(snapshot)   # reclone fait sa propre sauvegarde complète
            propose_reclone()
            # Le repo est (ou va être) remplacé → on n'enchaîne pas les rattrapages
            # sur l'ancien arbre, et pas de `to` sensé.
            print('(re-clone traité — relance install_upgrade dans le clone frais si nécessaire.)')
            _write_log({'op': 'up', 'from': from_state, 'pull': 'reclone',
                        'migrations': [], 'issues': None, 'snapshot': None})
            return 0
        if status == 'ok':
            print(f'{YELLOW}--- Rattrapages ---{NC}')
            failed = apply_benign()
        # 'diverged' : pull bloqué (à résoudre par l'utilisateur) → rattrapages
        # sautés, on passe directement au report.

    print(f'{YELLOW}--- État ---{NC}')
    config_issues = report()
    mig = migrate(check=args.check)
    issues = config_issues + mig['issues']
    if issues == 0:
        print(f'{GREEN}✓{NC} Rien à signaler.')

    if not args.check:        # le journal forensique ne trace que les RUNS réels
        # Run NULL (ni code avancé, ni config/classeur changés) → on jette le
        # snapshot ; ligne `snapshot: null`. Sinon on le garde (point de restauration).
        _, head_after = _git('rev-parse', 'HEAD')
        null_run = (head_before == head_after) and bool(snapshot) and _snapshot_unchanged(snapshot)
        if snapshot and null_run:
            _discard_snapshot(snapshot)
            snapshot = None
        elif snapshot:
            _prune_snapshots()        # rétention 10 (le snapshot gardé compte)
        _write_log({
            'op': 'up',
            'from': from_state,
            'to': {'app_version': _disk_app_version(),                 # post-pull, lu
                   'classeur_schema': inc_update.read_classeur_schema(xlsx)},
            'pull': status,
            'rattrapages': ('échec' if failed else 'ok') if status == 'ok' else 'sauté',
            'migrations': mig['migrations'],
            'issues': issues,
            'snapshot': snapshot,
        })

        # #99 — pose le stamp honored_version = version disque (post-pull). Après
        # un run OK, l'installation est réputée à jour : rattrapages bénins
        # appliqués ; structurelles déclinées restent gardées par le gate dur
        # check_schema_compat. C'est l'acteur load-bearing du stamp (le self-heal
        # du GUI/CLI n'avance que les pulls sans action due).
        if not failed and not mig.get('blocked'):
            inc_update.write_honored_version(BASE_DIR / 'config.ini', _disk_app_version())

    return 1 if (failed or mig.get('blocked')) else 0


if __name__ == '__main__':
    sys.exit(main())
