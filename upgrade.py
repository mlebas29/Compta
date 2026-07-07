#!/usr/bin/env python3
"""upgrade.py — point d'entrée UPGRADE consommateur (#94).

Geste utilisateur « le CHANGELOG annonce une version → je mets à jour mon
install ». Distinct du `git pull` de synchro train-train : ici l'objet est
l'UPGRADE — tirer le nouveau CODE et amener l'install à l'état qu'il attend.

PUB seulement : le contenu du dépôt privé (custom/) relève du sync PRIVÉ, hors
scope d'un outil public (qui ne présume ni le remote ni le modèle du PRV). Poser
le CADRE vide custom/ reste OK — c'est structurel (ensure_custom_frame, #93).

Séquence (#94) :
  1. pull résilient PUB, --ff-only ; si histoires disjointes (merge-base vide,
     ex. clone d'avant un squash 🔄) → re-clone AUTOMATIQUE (reclone.sh, sauvegarde
     complète conservée → réversible). Divergence / commits locaux → simplement
     signalé (pas reclone). Seule contrainte du reclone : être lancé HORS du clone.
  2. rattrapages bénins idempotents : config+raccourci (install_fix), migrations
     config (carte), cadre custom/ (ensure_custom_frame). Toujours joués.
  3. migration classeur (carte) : APPLIQUÉE automatiquement via les probes partagées
     avec le GUI (inc_update, par import).

upgrade APPLIQUE automatiquement ce que la carte dit — PAS de consentement : la
sauvegarde (snapshot pré-mutation + backup complet du reclone) est le filet,
réversible via --restore. Qui veut garder la main pas à pas fait le geste manuel
(git pull + lancer les scripts soi-même). Garde-fous conservés (≠ consentement) :
--check (report seul), classeur ouvert / GUI en cours, LibreOffice < 24.8, hors-clone.

Idempotent : un second passage ne fait rien si tout est déjà à jour.

Usage (lancer HORS du clone — cf. en-tête) :
  curl -fsSL <raw>/upgrade.py -o /tmp/upgrade.py && python3 /tmp/upgrade.py <clone>
  python3 /tmp/upgrade.py <clone> --check   # pull + rattrapages sautés, report seul
"""

import argparse
import subprocess
import sys
from pathlib import Path

# AMORCEUR-PUR (#102). upgrade.py a UNE seule entrée : il amène TOUJOURS le clone
# cible (BASE_DIR) à l'état courant (phase A : pull|reclone) PUIS importe le
# cerveau (inc_update) du clone — désormais frais — et migre. Pas de bi-modal,
# pas de re-exec.
#
# Le clone est un ARGUMENT OBLIGATOIRE (positionnel). Geste prescrit, universel :
#     curl -fsSL <raw>/upgrade.py -o /tmp/upgrade.py && python3 /tmp/upgrade.py <clone>
# Hors-clone n'est EXIGÉ que pour le RE-CLONE (vieux clone, butée 🔄) : il swappe le
# dossier du clone, donc un script qui y tourne se ferait remplacer → refus ciblé
# dans la phase A. Le pull, la migration (phase B), `--restore`/`--liste` TOLÈRENT
# l'in-clone (rien n'est swappé) → un restore tardif peut relancer le `upgrade.py`
# du clone, sans re-curl. Vertus : (a) aucune devinette du clone par cwd/dossier-du-
# script (GUI-safe : l'appelant DÉSIGNE le clone) ; (b) via /tmp on exécute l'amorce
# la PLUS FRAÎCHE, en AVANCE sur le code du clone (gère des cas qu'il n'anticipait
# pas) ; (c) « skip » de la phase A impossible.
inc_update = None          # importé APRÈS la phase A (cerveau frais), via _load_brain
BASE_DIR = None            # clone cible = l'argument positionnel, résolu dans main()

REPO_URL_RAW = 'https://raw.githubusercontent.com/mlebas29/Compta/main'

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
    'diverged' (divergence / commits locaux / conflit — pull bloqué) |
    'offline' (transport KO : réseau / accès remote — rien de décidable).
    """
    _, head0 = _git('rev-parse', 'HEAD')
    rc, out = _git('pull', '--ff-only')
    if rc == 0:
        _, head1 = _git('rev-parse', 'HEAD')
        print(f'{GREEN}✓{NC} PUB ' + ('mis à jour.' if head0 != head1 else 'déjà à jour.'))
        return 'ok'

    # Échec ff-only : transport KO ? histoires disjointes (→ reclone) ? divergence ?
    # Le `git fetch` EST le signal de transport : tant qu'il échoue, merge-base
    # (calculé sur des refs locales possiblement périmées) ne tranche RIEN — un
    # réseau coupé se ferait passer pour une divergence, voire pour un reclone.
    rc_fetch, out_fetch = _git('fetch', '--quiet')
    if rc_fetch != 0:
        print(f'{RED}✗{NC} PUB : transport impossible (réseau / accès au remote).')
        last = out_fetch.splitlines()[-1] if out_fetch else (out.splitlines()[-1] if out else '')
        if last:
            print(f'   git : {last}')
        return 'offline'
    rc_mb, mb = _git('merge-base', 'HEAD', 'origin/main')
    if rc_mb != 0 or not mb:
        # merge-base vide (fetch OK) = histoires disjointes (clone fossile d'avant un squash 🔄).
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


def _do_reclone():
    """Re-clone AUTOMATIQUE de BASE_DIR (histoires disjointes / butée 🔄). Comme le
    reste du flux, pas de consentement : `reclone.sh --yes` fait sa propre sauvegarde
    COMPLÈTE (dossier `.backup-<ts>` conservé) → réversible. `reclone.sh` est rapatrié
    FRAIS de GitHub s'il manque (clone v4/v5.0 antérieur à v5.1.0). Toujours ciblé par
    `--repo BASE_DIR`. La seule contrainte (≠ consentement) est le HORS-CLONE, gardé
    en amont dans main() : le swap remplacerait un script tournant dans le dossier.
    Retourne True si le re-clone a réussi.
    """
    script = _fetch_reclone(BASE_DIR)
    if not script:
        return False
    print(f'{YELLOW}--- Re-clone automatique (réécriture d\'historique 🔄 ; '
          f'sauvegarde complète conservée) ---{NC}')
    rc = _run_interactive(f"'{script}' --reclone --repo '{BASE_DIR}' --yes")
    return rc == 0


# --- Rendu uniforme d'une étape du chemin (carte, #121) ---------------------
# Chaque étape (step inconditionnel OU migration gated) s'affiche par UNE ligne
# d'en-tête « {icône} {composant} — {libellé} : {verdict} », suivie du détail
# (sortie de l'outil, ou citation read-only en --check). La parité simulé/réel
# vient de la boucle : on REND toujours le verdict, on EXÉCUTE seulement hors
# --check. Tue l'asymétrie de verbosité (avant : seul le classeur était encadré,
# le shell se déversait brut) et le ℹ d'annonce réservé au classeur.
_STEP_ICONS = {'ok': f'{GREEN}✓{NC}', 'todo': f'{YELLOW}⚠{NC}',
               'force': f'{YELLOW}ℹ{NC}', 'fail': f'{RED}✗{NC}'}


def _step(kind, component, label, verdict):
    print(f'{_STEP_ICONS.get(kind, "•")} {component} — {label} : {verdict}')


def _indent(text, prefix='   '):
    return '\n'.join(prefix + ln for ln in text.splitlines())


# Steps INCONDITIONNELS — l'id de la carte (steps[]) → (sonde, application). La sonde
# (DRY_RUN / --dry-run) honore la convention EFFECTIVE-STATE #121 : rc 3 = CHANGERAIT,
# rc 0 = rien, autre = erreur. L'application réelle rend 0 (succès) / non-0 (échec).
# Invocation shell concrète gardée HORS du JSON déclaratif ; parité id↔runner vérifiée
# par validate_upgrade_map. `. ./inc_install.sh` source la cervelle shell ; le préfixe
# DRY_RUN=1 persiste (builtin `.`) jusqu'à la fonction appelée.
_INC = '. ./inc_install.sh && '
STEP_CMDS = {
    'normalize':    ('DRY_RUN=1 ' + _INC + 'normalize_config config.ini',
                     _INC + 'normalize_config config.ini'),
    'raccourci':    ('DRY_RUN=1 ' + _INC + 'setup_desktop "$(pwd)" "$(read_mode config.ini)"',
                     _INC + 'setup_desktop "$(pwd)" "$(read_mode config.ini)"'),
    'custom_frame': ('DRY_RUN=1 ' + _INC + 'ensure_custom_frame .',
                     _INC + 'ensure_custom_frame .'),
}


def _probe_and_apply(component, label, probe_cmd, apply_cmd, check):
    """Contrat EFFECTIVE-STATE (#121). SONDE d'abord (probe_cmd, read-only) → rc 3 =
    changerait / 0 = rien / autre = erreur. On n'AFFICHE / n'EXÉCUTE que si ça
    changerait (politique (a) : les no-op sont cachés — plus de « forcé » qui
    contredirait l'état effectif). Retourne (failed, todo)."""
    rc, out = _run_bash(probe_cmd)
    if rc not in (0, 3):
        _step('fail', component, label, f'sonde en erreur (rc={rc})')
        if out:
            print(_indent(out))
        return (1, 0)
    if rc == 0:
        return (0, 0)                        # no-op → caché
    if check:                                # rc == 3 : changerait
        _step('todo', component, label, 'à appliquer')
        return (0, 1)
    rc2, out2 = _run_bash(apply_cmd)         # apply : exécute réellement
    if out2:
        print(_indent(out2))
    if rc2 != 0:
        _step('fail', component, label, f'échec (rc={rc2})')
        return (1, 0)
    _step('ok', component, label, 'appliqué')
    return (0, 0)


def apply_benign(check=False):
    """Volet config + steps inconditionnels du chemin (carte #121), en EFFECTIVE-STATE :
    chaque étape est SONDÉE (would-change) puis affichée/jouée seulement si elle
    changerait quelque chose (politique (a) — no-op cachés). Plus de notion « forcé » :
    un step inconditionnel sans effet est silencieux comme une migration à jour. Ordre :
    normalize (config) → migrations config → marqueur → raccourci, custom_frame (app).
    Retourne (échecs, todo).

    Le composant Config porte un marqueur (config_schema_version, #98) : l'apply le pose
    si le relevé diffère de la cible — c'est une CHANGE effective (écrit config.ini même
    quand toutes les migrations sont no-op : données déjà au schéma, marqueur absent),
    donc traitée comme une étape. Le marqueur n'avance que si aucune migration config
    n'a échoué (sinon l'avis ⚙️ doit persister)."""
    failed = todo = 0
    cmap = inc_update.load_upgrade_map(BASE_DIR)
    steps = {s.get('id'): s for s in cmap.get('steps', [])}

    def run_step(sid):
        nonlocal failed, todo
        s = steps.get(sid)
        if not s:
            return
        probe, real = STEP_CMDS[sid]
        f, t = _probe_and_apply(s.get('perimetre', '?'), s.get('summary', sid), probe, real, check)
        failed += f
        todo += t

    # 1. normalize (config)
    run_step('normalize')

    # 2. Migrations de SCHÉMA config — le MARQUEUR (#98) décide l'appartenance au chemin
    # (entrées dont schema_to dépasse le relevé + silencieuses), mais chacune est SONDÉE
    # (--dry-run rc 3/0) pour son effet RÉEL → une migration déjà appliquée (no-op, ex.
    # xmr déjà migré) est cachée, plus affichée « à appliquer » à tort.
    from inc_excel_schema import CONFIG_SCHEMA_VERSION
    config_path = BASE_DIR / 'config.ini'
    releve = inc_update.read_config_schema(config_path)
    config_failed = 0
    for cm in inc_update.pending_config_migrations(BASE_DIR, releve, CONFIG_SCHEMA_VERSION):
        tool = cm.get('tool')
        if not tool:
            continue
        label = cm.get('id', tool)
        f, t = _probe_and_apply('config', label,
                                f'python3 {tool} config.ini --dry-run',
                                f'python3 {tool} config.ini', check)
        config_failed += f
        todo += t
    failed += config_failed

    # 3. Marqueur config (#98) — étape effective : posé si le relevé diffère de la cible.
    # UPGRADE SEUL pose la note (Compta_coherence.md) ; pas si une migration config a
    # échoué (l'avis ⚙️ doit persister).
    if config_failed == 0 and (releve or '') != CONFIG_SCHEMA_VERSION:
        if check:
            _step('todo', 'config',
                  f'marqueur de schéma ({releve or "absent"} → {CONFIG_SCHEMA_VERSION})', 'à poser')
            todo += 1
        else:
            inc_update.write_config_schema(config_path, CONFIG_SCHEMA_VERSION)
            _step('ok', 'config', f'marqueur de schéma → {CONFIG_SCHEMA_VERSION}', 'posé')

    # 4. raccourci + cadre privé custom/ (app) — inconditionnels, sondés
    run_step('raccourci')
    run_step('custom_frame')

    return failed, todo


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
            print(_indent(f'{GREEN}✓{NC} déjà à jour — rien migré.'))
            return {'tool': tool, 'result': 'noop'}
        print(_indent(f'{GREEN}✓{NC} migration appliquée.'))
        return {'tool': tool, 'result': 'applied'}
    if rc == 2:
        print(_indent(f'{RED}✗{NC} LibreOffice < 24.8 — migration refusée (classeur inchangé).'))
        print(_indent('→ migre depuis une machine LO≥24.8 (cf. Compta_upgrade_classeur.md).'))
        return {'tool': tool, 'result': 'refused-lo'}
    print(_indent(f'{RED}✗{NC} {tool} a échoué (rc={rc}).'))
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
    (inc_update.pending_migrations). `upgrade` APPLIQUE automatiquement le chemin
    (structurelles puis rattrapage idempotent) — PAS de consentement : la sauvegarde
    (snapshot pris avant toute mutation) est le filet, réversible via --restore. Qui
    veut garder la main pas à pas utilise le mode manuel (git pull + scripts). Garde-
    fous conservés (≠ consentement) : --check = report seul ; classeur ouvert / GUI
    en cours = refus ; LibreOffice < 24.8 = refus dans _run_migration. Retourne le nb
    de points NON résolus (pending en --check, ou migrations échouées/refusées).
    """
    xlsx = BASE_DIR / 'comptes.xlsm'
    if not xlsx.exists():
        return {'issues': 0, 'migrations': []}
    from inc_excel_schema import SCHEMA_VERSION as code_schema

    problems = inc_update.validate_upgrade_map(BASE_DIR, code_schema, set(STEP_CMDS))
    if problems:
        print(f'{RED}✗{NC} Carte de migration incohérente — migration suspendue :')
        for p in problems:
            print(f'   - {p}')
        return {'issues': 1, 'migrations': []}

    classeur_schema = inc_update.read_classeur_schema(xlsx)
    plan = inc_update.pending_migrations(BASE_DIR, classeur_schema, code_schema)

    if plan['below_floor']:
        _step('fail', 'classeur', f'version {classeur_schema} sous le plancher de la carte',
              'migration manuelle requise')
        print(_indent('→ voir Compta_upgrade_classeur.md.'))
        return {'issues': 1, 'migrations': []}

    # Garde : la migration écrit le .xlsm via UNO ; refuser si le classeur est
    # ouvert (verrou LO) ou l'appli tourne — ne tire QUE s'il y a vraiment une
    # migration à appliquer (sinon le run pull/config se poursuit normalement).
    pending = list(plan['structural'])
    if not plan['structural']:
        pending += plan['catchups']
    if pending and not check:
        busy = _classeur_busy(xlsx)
        if busy:
            _step('fail', 'classeur', ', '.join(busy), 'non migré (classeur occupé)')
            print(_indent("→ ferme l'application et le classeur (LibreOffice), "
                          "puis relance upgrade.py sur ce clone."))
            # bloqué ≠ décliné : ne PAS avancer le stamp (l'avis #99 doit
            # persister jusqu'à migration réelle) ni clamer un run OK.
            return {'issues': len(pending), 'migrations': [], 'blocked': True}

    issues = 0
    ran = []

    # --- migrations structurelles : APPLIQUÉES (snapshot déjà pris → réversible) ---
    for m in plan['structural']:
        _step('todo', 'classeur',
              f"{m['summary']} (schéma {m['schema_from']}→{m['schema_to']})", 'à appliquer')
        if check:
            issues += 1     # l'en-tête « à appliquer » dit déjà tout (pas de détail redondant)
            continue
        r = _run_migration(m['tool'])
        ran.append(r)
        if r['result'] in ('failed', 'refused-lo'):
            issues += 1

    # --- rattrapage (catch-up) idempotent — SONDÉ pour son effet réel (#121,
    # effective-state) : `--dry-run` openpyxl read-only (SANS LibreOffice ; rc 3 =
    # changerait, 0 = rien). Affiché/joué seulement s'il changerait (politique (a) :
    # un classeur déjà fiabilisé est silencieux). ---
    if not plan['structural']:
        for c in plan['catchups']:
            rc, _ = _run_bash(f"./{c['tool']} comptes.xlsm --dry-run")
            if rc == 3:
                _step('todo', 'classeur', c['summary'], 'à appliquer')
                if check:
                    issues += 1
                else:
                    r = _run_migration(c['tool'])
                    ran.append(r)
                    if r['result'] in ('failed', 'refused-lo'):
                        issues += 1
            elif rc != 0:
                _step('fail', 'classeur', f"{c['tool']} (sonde)",
                      f'dry-run indéterminé (code {rc})')
                issues += 1

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
        # Métadonnées lues SUR DISQUE via process frais : _take_snapshot tourne
        # AVANT que le cerveau soit importé in-process (snapshot pré-phase-A) — le
        # global inc_update y est encore None, et un import in-process cacherait la
        # version PRÉ-pull (cassant la fraîcheur voulue par l'amorceur). Les helpers
        # _disk_* lisent le clone tel qu'il est, sans polluer sys.modules.
        meta = {'ts': ts, 'commit': head,
                'from': {'app_version': _disk_app_version(),
                         'classeur_schema': _disk_classeur_schema()},
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
    print(f'{YELLOW}Points de restauration (relancer avec --restore <ts>) :{NC}')
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
    process courant a le module inc_excel_schema caché (valeur pré-pull).
    `-B` (pas d'écriture .pyc) est CRUCIAL : un appel pré-pull (from_app) écrirait
    sinon un `__pycache__/inc_excel_schema.pyc` ; le `git pull` réécrit le .py dans
    la même seconde → CPython compare les mtime À LA SECONDE, juge le cache encore
    valide, et l'appel POST-pull relirait la version PRÉ-pull (stamp #99 jamais avancé)."""
    p = subprocess.run(
        ['python3', '-B', '-c', 'from inc_excel_schema import APP_VERSION; print(APP_VERSION)'],
        cwd=str(BASE_DIR), capture_output=True, text=True)
    return (p.stdout or '').strip() or '?'


def _disk_classeur_schema():
    """SCHEMA du classeur lu via un process FRAIS (inc_update du clone sur disque).
    Symétrique de _disk_app_version : robuste quand le cerveau n'est pas encore
    importé in-process (snapshot pré-phase-A, global inc_update None). None si pas
    de classeur (ou clone trop ancien sans inc_update)."""
    xlsx = BASE_DIR / 'comptes.xlsm'
    if not xlsx.exists():
        return None
    p = subprocess.run(
        ['python3', '-B', '-c',          # -B : pas de .pyc (cf. _disk_app_version)
         "import inc_update; print(inc_update.read_classeur_schema('comptes.xlsm'))"],
        cwd=str(BASE_DIR), capture_output=True, text=True)
    out = (p.stdout or '').strip()
    return int(out) if out.isdigit() else (out or None)


def _write_log(record):
    """Journal forensique externe — `upgrade_log.jsonl` (gitignoré, per-instance).
    Trace l'état from→to et ce qu'upgrade a fait (migrations, backups
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


def _load_brain():
    """Importe `inc_update` DEPUIS le clone cible `BASE_DIR` (post-phase-A → code
    frais) et le pose en global pour report/migrate/snapshots. On insère `BASE_DIR`
    en tête de `sys.path` : indispensable quand le script est lancé HORS du clone
    (téléchargé) — sinon `import inc_update` échouerait ou viserait le mauvais
    dossier. Retourne False si le clone ne porte pas `inc_update.py` (trop ancien,
    < v5.3.0) ; True sinon. No-op si déjà chargé."""
    global inc_update
    if inc_update is not None:
        return True
    if not (BASE_DIR / 'inc_update.py').exists():
        return False
    sys.path.insert(0, str(BASE_DIR))
    import inc_update as _iu
    inc_update = _iu
    return True


def _fetch_reclone(repo):
    """Rapatrie `reclone.sh` FRAIS depuis GitHub raw dans `repo` quand il y est
    absent (instance v4/v5.0 antérieure à la butée v5.1.0 : elle n'a jamais reçu
    le script). On NE le porte PAS en python — `reclone.sh` est le shell maîtrisé
    (ancrage rsync `/.git/` subtil) ; on le réutilise tel quel. Retourne le Path
    du script utilisable, ou None si indisponible (pas de réseau)."""
    local = repo / 'reclone.sh'
    if local.exists():
        return local
    # Hors du clone : reclone.sh mv le clone → backup puis restaure le non-tracké
    # par rsync ; un .sh déposé DANS le clone se ferait recopier dans le clone frais.
    fresh = Path('/tmp/compta-reclone-fresh.sh')
    rc, out = _run_bash(f"curl -fsSL '{REPO_URL_RAW}/reclone.sh' -o '{fresh}' && chmod +x '{fresh}'")
    if rc == 0 and fresh.exists():
        print(f'{GREEN}✓{NC} reclone.sh rapatrié frais (absent de ce clone v4/v5.0).')
        return fresh
    print(f'{RED}✗{NC} reclone.sh introuvable et fetch impossible (réseau ?).')
    if out:
        print(f'   {out.splitlines()[-1] if out else ""}')
    return None


def main():
    ap = argparse.ArgumentParser(
        description="Point d'entrée upgrade consommateur (#94/#102).")
    ap.add_argument('repo', metavar='CLONE',
                    help='dossier du clone à mettre à jour (geste : cf. Compta_upgrade_assiste.md)')
    ap.add_argument('--check', action='store_true',
                    help='report seul : pull et rattrapages sautés')
    ap.add_argument('--liste', action='store_true',
                    help='liste les points de restauration (snapshots) et quitte')
    ap.add_argument('--restore', metavar='TS',
                    help='restaure depuis le snapshot TS (cf. --liste)')
    ap.add_argument('--only', choices=['config', 'xlsm', 'app'],
                    help='restreint --restore à un composant (défaut : tout)')
    args = ap.parse_args()

    # AMORCEUR-PUR (#102) : entrée unique, aucun bi-modal. On résout le clone
    # cible, on l'amène TOUJOURS à l'état courant (phase A) PUIS on importe le
    # cerveau frais et on migre. Lancé in-clone ou téléchargé hors clone : idem.
    global BASE_DIR
    BASE_DIR = Path(args.repo).expanduser().resolve()
    if not (BASE_DIR / '.git').is_dir():
        print(f'{RED}✗{NC} {BASE_DIR} n\'est pas un clone git.', file=sys.stderr)
        print('   (machine nue → install.sh ; sinon vérifie le chemin du clone donné en argument.)')
        return 1

    # --liste / --restore opèrent sur des snapshots existants : pas de phase A.
    if args.liste or args.restore:
        if not _load_brain():
            print(f'{RED}✗{NC} Outillage absent ({BASE_DIR}/inc_update.py) — clone trop ancien.',
                  file=sys.stderr)
            return 1
        return _list_snapshots() if args.liste else _restore(args.restore, args.only or 'all')

    print(f"{YELLOW}=== upgrade — mise à jour de {BASE_DIR} ==={NC}")

    # Version AVANT la phase A (subprocess frais : le module en mémoire serait caché).
    from_app = _disk_app_version()

    # Snapshot COMPLET pré-mutation (jeté en fin si le run est NULL) ; head_before
    # pour détecter une avance de code.
    snapshot = None
    head_before = None
    if not args.check:
        snapshot = _take_snapshot()
        _, head_before = _git('rev-parse', 'HEAD')

    # --- Phase A : amener le clone à l'état courant (TOUJOURS) ---
    failed = 0
    status = None
    if args.check:
        # Parité --check (#111) : on CITE le pull sans l'exécuter. `git fetch` met à
        # jour les refs distantes (n'altère pas l'arbre, comme tool_audit_git) → on
        # peut prédire « déjà à jour / N à tirer » read-only ; le merge ff n'est PAS fait.
        print(f'{YELLOW}--- Pull PUB (simulé) ---{NC}')
        _git('fetch', '--quiet')
        rc_b, behind = _git('rev-list', '--count', 'HEAD..@{u}')
        if rc_b != 0:
            print('   ⚠ pas de remote suivi / hors-ligne — pull non simulable.')
        elif behind in ('', '0'):
            print(f'{GREEN}✓{NC} PUB déjà à jour (rien à tirer).')
        else:
            print(f'   {behind} commit(s) à tirer — l\'apply ferait le pull ff.')
    else:
        print(f'{YELLOW}--- Pull PUB (résilient) ---{NC}')
        status = resilient_pull()
        if status in ('offline', 'diverged'):
            # Transport KO ou divergence : on ne peut pas amener le clone à jour →
            # pas de migration sur un arbre incertain (rien muté → snapshot jeté).
            print('   → pas de réseau / accès remote ; réessaie une fois connecté.'
                  if status == 'offline' else
                  '   → résous la divergence (cf. message git) puis relance.')
            _discard_snapshot(snapshot)
            return 1
        if status == 'reclone':
            # SEUL cas exigeant hors-clone : le re-clone SWAPPE le dossier du clone.
            # Si ce script y tourne, il se ferait remplacer sous les pieds → refus,
            # et on indique le geste /tmp (amorce fraîche, hors clone).
            f = globals().get('__file__')
            sp = Path(f).resolve() if f and f != '<stdin>' else None
            if sp and (sp.parent == BASE_DIR or BASE_DIR in sp.parents):
                print(f'{RED}✗{NC} Re-clone requis, mais ce `upgrade.py` est DANS le clone '
                      f'(le re-clone swappe {BASE_DIR}). Relance-le hors du clone :', file=sys.stderr)
                print(f'   curl -fsSL {REPO_URL_RAW}/upgrade.py -o /tmp/upgrade.py')
                print(f'   python3 /tmp/upgrade.py {args.repo}')
                _discard_snapshot(snapshot)
                return 1
            _discard_snapshot(snapshot)   # reclone fait sa propre sauvegarde complète
            if not _do_reclone():
                print('(re-clone non effectué — relance une fois prêt.)')
                _write_log({'op': 'up', 'from': {'app_version': from_app},
                            'pull': 'reclone', 'migrations': [], 'issues': None,
                            'snapshot': None})
                return 0
            # Reclone fait : le clone (même chemin) est frais → on POURSUIT dans le
            # même run (cerveau frais + migration). Nouveau snapshot pré-migration.
            status = 'ok'
            snapshot = _take_snapshot()
            _, head_before = _git('rev-parse', 'HEAD')

    # --- Cerveau FRAIS (post-phase-A), importé depuis le clone cible ---
    if not _load_brain():
        print(f'{RED}✗{NC} Outillage absent ({BASE_DIR}/inc_update.py) — clone trop ancien.',
              file=sys.stderr)
        print('   → relance SANS --check : la phase A (pull/reclone) installe l\'outillage.')
        return 1

    xlsx = BASE_DIR / 'comptes.xlsm'
    # classeur_schema inchangé par la phase A → lu avec le cerveau frais.
    from_state = {'app_version': from_app,
                  'classeur_schema': inc_update.read_classeur_schema(xlsx)}

    # Marche unique pilotée par la CARTE (#121) : steps inconditionnels +
    # migrations config (apply_benign) PUIS classeur (migrate). Chaque étape rend
    # un verdict uniforme ; --check cite read-only, l'apply exécute → parité
    # carte ↔ check ↔ apply par construction.
    print(f'{YELLOW}--- Mise à niveau (carte) ---{NC}')
    apply_todo = 0
    if status == 'ok' or args.check:
        failed, apply_todo = apply_benign(check=args.check)
    mig = migrate(check=args.check)

    # Diagnostic générique HORS carte : clés config obsolètes (.default) que les
    # migrations dédiées ne couvrent pas. L'avis de SCHÉMA config, lui, est rendu
    # par l'étape de migration config ci-dessus (plus de report() redondant —
    # startup_config_advice reste pour le DÉMARRAGE GUI/CLI, inchangé).
    obsolete = inc_update.check_config_obsolete(BASE_DIR / 'config.ini')
    for w in obsolete:
        print(f'{YELLOW}⚠{NC} {w}')

    # Bilan. En --check, mig['issues'] = points classeur « à appliquer » ; apply_todo
    # = migrations config « à appliquer ». On ne clame « à jour » que si RIEN n'est
    # pending (sinon contradiction avec les « à appliquer » affichés). Hors --check,
    # les pending ont été exécutés → mig['issues'] = échecs/refus résiduels.
    issues = mig['issues'] + len(obsolete)
    if args.check:
        pending = apply_todo + mig['issues']
        if pending == 0 and failed == 0 and not obsolete:
            print(f'{GREEN}✓{NC} Déjà à jour — rien à appliquer.')
        elif pending:
            print(f'{YELLOW}ℹ{NC} {pending} point(s) à appliquer — '
                  f'relance sans --check pour les appliquer.')
    elif issues == 0 and failed == 0:
        print(f'{GREEN}✓{NC} Tout est à jour.')

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
                   'classeur_schema': inc_update.read_classeur_schema(xlsx),
                   'config_schema': inc_update.read_config_schema(BASE_DIR / 'config.ini')},
            'pull': status,
            'rattrapages': ('échec' if failed else 'ok') if status == 'ok' else 'sauté',
            'migrations': mig['migrations'],
            'issues': issues,
            'snapshot': snapshot,
        })
        # Marqueurs (#98, Compta_coherence.md) : le composant Config est avancé par
        # apply_benign (write_config_schema, run OK) ; le composant Classeur par son
        # outil de migration (NR dans le .xlsm). Plus de stamp d'app (honored_version
        # retiré) : l'app n'a pas de marqueur, git porte sa version.

    return 1 if (failed or mig.get('blocked')) else 0


if __name__ == '__main__':
    sys.exit(main())
