#!/usr/bin/env python3
"""upgrade_launcher.py — lanceur détaché de mise à jour (#181).

`upgrade.py` refuse de tourner GUI/classeur ouverts (garde `_classeur_busy` :
verrou LibreOffice + process `cpt_gui`) car il pull|reclone le code qui tourne
ET pilote LibreOffice. Ce lanceur résout le problème : la GUI se ferme, ce
process DÉTACHÉ (`start_new_session`) lui SURVIT, attend sa mort réelle, joue
l'upgrade HEADLESS derrière une fenêtre de réassurance minimale, puis relance
la GUI — quoi qu'il arrive.

Double usage :
  - spawné par la GUI (bouton « Mettre à jour ») — copié dans /tmp d'abord, pour
    être clone-indépendant (un reclone remplace le dossier du clone) ; la GUI
    passe --base, --python, --xlsx, --gui-pid.
  - lancé à la main en CLI : `python3 upgrade_launcher.py [--base <clone>]`
    (orchestration identique ; sans GUI vivante l'attente est immédiate).

Journalisation (#181), sans importer inc_logging (un reclone peut remplacer le
code du clone en cours de route) :
  - journal.log (jalons partagés) : lanceur début · upgrade début · upgrade fin (rc).
  - logs/upgrade.log : transcript brut d'upgrade (OVERWRITE par run — l'historique
    vit dans journal.log qui est append).
  - logs/upgrade_status.json : {ts, rc, ok, phase} → la GUI relancée sait
    afficher un échec SANS terminal.
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import datetime
from pathlib import Path

REPO_URL_RAW = 'https://raw.githubusercontent.com/mlebas29/Compta/main'
UPGRADE_URL = f'{REPO_URL_RAW}/upgrade.py'

WAIT_TIMEOUT = 120  # s — délai max d'attente de la mort GUI + libération du verrou


# ---------------------------------------------------------------------------
# Traces (best-effort, jamais bloquantes)
# ---------------------------------------------------------------------------

def _now():
    return datetime.now().strftime('%H:%M:%S')


def _journal(base, prefix, msg):
    """Jalon → base/logs/journal.log (même fil narratif que la GUI/collecte)."""
    try:
        jf = base / 'logs' / 'journal.log'
        jf.parent.mkdir(parents=True, exist_ok=True)
        with open(jf, 'a', encoding='utf-8') as f:
            f.write(f'{_now()} upgrade_launcher {prefix} {msg}\n')
    except Exception:
        pass


def _write_status(base, rc, ok, phase):
    """logs/upgrade_status.json — lu par la GUI relancée (bandeau d'échec)."""
    try:
        p = base / 'logs' / 'upgrade_status.json'
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({
            'ts': datetime.now().isoformat(timespec='seconds'),
            'rc': rc, 'ok': ok, 'phase': phase,
        }), encoding='utf-8')
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Attente de la mort réelle de la GUI (process + verrou LO)
# ---------------------------------------------------------------------------

def _pid_alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True          # existe mais pas à nous → vivant
    except OSError:
        return False
    return True


def _gui_alive(gui_pid):
    if gui_pid is not None:
        return _pid_alive(gui_pid)
    # bracket-trick : ne matche pas le pgrep lui-même
    return subprocess.run(['pgrep', '-f', '[c]pt_gui.py'],
                          capture_output=True).returncode == 0


def _classeur_locked(xlsx):
    if not xlsx:
        return False
    return (xlsx.parent / f'.~lock.{xlsx.name}#').exists()


def _wait_gui_gone(gui_pid, xlsx, on_status=None):
    """Attend que la GUI soit morte ET le verrou LO relâché. True si libéré,
    False si timeout (upgrade alors annulé — muter le classeur ouvert = risque)."""
    deadline = time.monotonic() + WAIT_TIMEOUT
    while time.monotonic() < deadline:
        if not _gui_alive(gui_pid) and not _classeur_locked(xlsx):
            return True
        if on_status:
            on_status("Fermeture de l'application…")
        time.sleep(0.5)
    return False


# ---------------------------------------------------------------------------
# Upgrade headless : curl amorce fraîche → exécute → transcript tee'd
# ---------------------------------------------------------------------------

def _run_upgrade(python, base):
    """Télécharge l'amorce fraîche puis l'exécute headless ; transcript →
    logs/upgrade.log (overwrite). Retourne ('offline', detail) | ('done', rc)."""
    tmp_upgrade = Path(tempfile.gettempdir()) / 'compta_upgrade.py'
    try:
        urllib.request.urlretrieve(UPGRADE_URL, tmp_upgrade)   # anonyme, public
    except Exception as e:
        return ('offline', f'{e}')

    log = base / 'logs' / 'upgrade.log'
    try:
        log.parent.mkdir(parents=True, exist_ok=True)
        lf = open(log, 'w', encoding='utf-8')
    except Exception:
        lf = None
    try:
        if lf:
            lf.write(f'=== upgrade {datetime.now().isoformat(timespec="seconds")} '
                     f'— base={base} python={python} ===\n')
            lf.flush()
        proc = subprocess.Popen(
            [python, str(tmp_upgrade), str(base)],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for line in proc.stdout:
            if lf:
                lf.write(line)
                lf.flush()
        rc = proc.wait()
    finally:
        if lf:
            lf.close()
    return ('done', rc)


def _relaunch_gui(python, base):
    """Relance la GUI, détachée (survit à la mort de ce lanceur).

    Env NETTOYÉ du drapeau de debug `COMPTA_FORCE_UPDATE` : la GUI relancée est
    une instance fraîche — un drapeau de lancement ponctuel ne doit pas s'y
    propager (sinon l'indicateur de test « persiste » au redémarrage)."""
    try:
        env = {k: v for k, v in os.environ.items() if k != 'COMPTA_FORCE_UPDATE'}
        subprocess.Popen([python, str(base / 'cpt_gui.py')],
                         start_new_session=True, cwd=str(base), env=env)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def _orchestrate(args, set_status):
    base, python, xlsx = args.base, args.python, args.xlsx
    _journal(base, '▶', f'Lanceur MàJ démarré (base={base}, python={python})')

    set_status("Fermeture de l'application…")
    if not _wait_gui_gone(args.gui_pid, xlsx, on_status=set_status):
        _journal(base, '✗', 'GUI toujours active après délai — mise à jour annulée')
        _write_status(base, None, False, 'gui_busy')
        set_status("Impossible de fermer l'application — redémarrage…")
        if not args.no_relaunch:
            _relaunch_gui(python, base)
        return

    set_status('Mise à jour en cours… (ne ferme pas l’ordinateur)')
    _journal(base, '▶', 'upgrade début')
    kind, payload = _run_upgrade(python, base)
    if kind == 'offline':
        _journal(base, '✗', f'upgrade impossible (téléchargement KO : {payload})')
        _write_status(base, None, False, 'offline')
        set_status('Pas de réseau — mise à jour reportée. Redémarrage…')
    else:
        rc = payload
        ok = (rc == 0)
        _journal(base, '✓' if ok else '✗', f'upgrade fin (rc={rc})')
        _write_status(base, rc, ok, 'done')
        set_status('Mise à jour terminée. Redémarrage…' if ok
                   else 'Échec de la mise à jour (voir le journal). Redémarrage…')

    if not args.no_relaunch:
        _relaunch_gui(python, base)   # relance INCONDITIONNELLE (sauf --no-relaunch, CLI/test)


# ---------------------------------------------------------------------------
# Fenêtre de réassurance minimale (splash) — best-effort
# ---------------------------------------------------------------------------

def _run_with_splash(args):
    try:
        import queue
        import threading
        import tkinter as tk
        from tkinter import ttk
    except Exception:
        _orchestrate(args, lambda s: None)   # pas de Tk → headless
        return

    root = tk.Tk()
    root.title('Mise à jour de Comptabilité')
    root.resizable(False, False)
    root.protocol('WM_DELETE_WINDOW', lambda: None)   # infermable tant que non fini

    frame = ttk.Frame(root, padding=20)
    frame.pack(fill='both', expand=True)
    ttk.Label(frame, text='Mise à jour de Comptabilité',
              font=('TkDefaultFont', 12, 'bold')).pack(pady=(0, 10))
    status_var = tk.StringVar(value='Préparation…')
    ttk.Label(frame, textvariable=status_var, width=48).pack(pady=(0, 12))
    bar = ttk.Progressbar(frame, mode='indeterminate', length=320)
    bar.pack()
    bar.start(12)

    q = queue.Queue()
    done = {'flag': False}

    def worker():
        try:
            _orchestrate(args, q.put)
        finally:
            done['flag'] = True

    def poll():
        try:
            while True:
                status_var.set(q.get_nowait())
        except queue.Empty:
            pass
        if done['flag']:
            root.after(1200, root.destroy)   # laisse lire le dernier message
            return
        root.after(150, poll)

    threading.Thread(target=worker, daemon=True).start()
    root.after(150, poll)
    root.mainloop()


def main():
    ap = argparse.ArgumentParser(description='Lanceur détaché de mise à jour (#181)')
    ap.add_argument('--base', type=Path, default=None,
                    help='clone cible (défaut : dossier du script)')
    ap.add_argument('--python', default=sys.executable,
                    help='interpréteur pour relancer la GUI (défaut : courant)')
    ap.add_argument('--xlsx', type=Path, default=None,
                    help='classeur — attendre la libération du verrou LibreOffice')
    ap.add_argument('--gui-pid', type=int, default=None,
                    help='PID de la GUI à attendre (défaut : pgrep cpt_gui)')
    ap.add_argument('--no-splash', action='store_true',
                    help='pas de fenêtre (CLI / headless)')
    ap.add_argument('--no-relaunch', action='store_true',
                    help='ne pas relancer la GUI après upgrade (CLI / test)')
    args = ap.parse_args()

    args.base = (args.base or Path(__file__).resolve().parent).resolve()

    if args.no_splash:
        _orchestrate(args, lambda s: None)
    else:
        _run_with_splash(args)


if __name__ == '__main__':
    main()
