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
    """Backup classeur + run le migrateur (via son shebang python3-uno ; le
    migrateur auto-gate LO≥24.8 → exit 2 si trop ancienne). Surface le verdict."""
    import shutil
    from datetime import datetime
    xlsx = BASE_DIR / 'comptes.xlsm'
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup = xlsx.parent / f'comptes.xlsm.bak-{ts}'
    shutil.copy2(xlsx, backup)
    print(f'   backup : {backup.name}')
    rc = _run_interactive(f'./{tool} comptes.xlsm')
    if rc == 0:
        print(f'{GREEN}✓{NC} Migration appliquée ({tool}).')
    elif rc == 2:
        print(f'{RED}✗{NC} LibreOffice < 24.8 — migration refusée par {tool} (classeur inchangé).')
        print('   → migre depuis une machine LO≥24.8 (cf. Compta_upgrade.md).')
    else:
        print(f'{RED}✗{NC} {tool} a échoué (rc={rc}) — backup conservé : {backup.name}')


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
        return 0
    from inc_excel_schema import SCHEMA_VERSION as code_schema
    classeur_schema = inc_update.read_classeur_schema(xlsx)
    plan = inc_update.pending_migrations(BASE_DIR, classeur_schema, code_schema)

    if plan['below_floor']:
        print(f'{YELLOW}⚠{NC} Classeur trop ancien pour la migration automatique '
              f'(version {classeur_schema} sous le plancher de la carte).')
        print('   → migration manuelle : voir Compta_upgrade.md.')
        return 1

    issues = 0
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
            _run_migration(m['tool'])
        else:
            print('   Migration non lancée.')

    # --- catch-up idempotent (seulement si structurellement à jour) ---
    c = plan['catchup']
    if c and not plan['structural']:
        print(f"{YELLOW}ℹ{NC} Catch-up formules disponible : {c['summary']} "
              f"({c['tool']}, idempotent).")
        if interactive:
            if input('   Appliquer (backup auto) ? [oui/non] ').strip().lower() == 'oui':
                _run_migration(c['tool'])
        else:
            print("   → optionnel ; relance en terminal pour l'appliquer.")

    return issues


def main():
    ap = argparse.ArgumentParser(
        description="Point d'entrée upgrade consommateur (#94).")
    ap.add_argument('--check', action='store_true',
                    help='report seul : pull et rattrapages sautés')
    args = ap.parse_args()

    if not (BASE_DIR / 'cpt_gui.py').exists():
        print(f'{RED}✗{NC} Pas un clone Compta ({BASE_DIR})', file=sys.stderr)
        return 1

    print(f"{YELLOW}=== install_upgrade — mise à jour de l'installation ==={NC}")

    failed = 0
    if args.check:
        print('(--check : pull et rattrapages sautés, report seul)')
    else:
        print(f'{YELLOW}--- Pull PUB (résilient) ---{NC}')
        status = resilient_pull()
        if status == 'reclone':
            propose_reclone()
            # Le repo est (ou va être) remplacé → on n'enchaîne pas les rattrapages
            # sur l'ancien arbre.
            print('(re-clone traité — relance install_upgrade dans le clone frais si nécessaire.)')
            return 0
        if status == 'ok':
            print(f'{YELLOW}--- Rattrapages ---{NC}')
            failed = apply_benign()
        # 'diverged' : pull bloqué (à résoudre par l'utilisateur) → rattrapages
        # sautés, on passe directement au report.

    print(f'{YELLOW}--- État ---{NC}')
    issues = report()
    issues += migrate(check=args.check)
    if issues == 0:
        print(f'{GREEN}✓{NC} Rien à signaler.')

    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
