"""Client pour tool_gui_cli.py daemon — mixin GUI + façade TNR.

Sur Mac, le system Python (qui héberge Tk) n'a pas accès au module uno
(réservé au Python embarqué LibreOffice). Les opérations UNO sont déléguées
à un process daemon `tool_gui_cli.py daemon` lancé via wrapper python3-uno.
Communication par stdin/stdout, protocole JSON line-based défini dans
_daemon_loop.

Deux clients exposés :

- `DaemonClientMixin` : injecté dans `ConfigGUI` (cpt_gui), dispatché par
  `HAS_UNO` dans les UI handlers (_run_devise_save, etc.) — sur Linux ce
  mixin n'est pas sollicité, la GUI appelle uno in-process.

- `DaemonGUI` : façade standalone pour les TNR. Expose la même API publique
  que `HeadlessGUI` (add_devise, add_account, ...) mais route via JSON RPC
  vers le daemon. Permet de tester le chemin daemon Mac depuis les pilotes
  TNR sans dupliquer les scénarios — flag `--daemon` dans chaque pilote
  bascule le backend.
"""

import json
import subprocess
import threading
from pathlib import Path


class DaemonClientMixin:
    """Client persistant pour tool_gui_cli.py daemon.

    Maintient 1 Popen sur toute la session GUI, spawn lazy au 1er appel.
    Thread-safe : un lock sérialise les calls stdin/stdout (le daemon est
    mono-threadé)."""

    # Méthodes après lesquelles forcer un __flush__ (save + close batch +
    # reload state). En mode in-process, chaque call ouvre/sauve/ferme sa
    # propre session UNO et un `_load_excel_data` refresh les attributs
    # cachés (`_start_avr`/`_end_avr`/etc.) entre les calls. En mode batch
    # ce refresh n'a pas lieu — flush forcé pour les ops qui décalent les
    # bornes lues par les calls suivants.
    #
    # Toutes les ops CRUD qui modifient le classeur doivent flush :
    # - le callback `_after_X_save` côté GUI Tk relit immédiatement le file
    #   disque via openpyxl pour refresh accounts_data / display_accounts ;
    #   sans flush, le batch est encore ouvert et le file disque n'est pas
    #   à jour → la nouvelle ligne n'apparaît pas dans le tree GUI.
    # - les `_save_accounts` / `_save_*` internes utilisent `self._end_avr`
    #   cached pour positionner les pieds Total ; sans flush entre 2 ops,
    #   la 2e écrit aux mauvaises rows.
    # Coût : ~6s par op sur Mac (cold start UNO au prochain batch reopen).
    # Acceptable en GUI interactif. Pour le batch TNR, utiliser explicitement
    # `with gui.batch():` qui ne flushe qu'en sortie de bloc.
    _FLUSH_AFTER = frozenset({
        # CRUD comptes
        'add_account', 'delete_account', 'modify_account',
        'rename_account', 'purge_account', 'cleanup_patrimoine',
        # CRUD devises
        'add_devise', 'delete_devise',
        # CRUD titres
        'add_title', 'rename_pv_title', 'delete_pv_title',
        # CRUD budget
        'add_category', 'delete_category', 'purge_category', 'rename_category',
        'set_category_poste',
        'add_poste', 'delete_poste', 'update_poste',
        # Recatégorisation post-import
        'recategorize',
        # Worker
        '_save_accounts',
    })

    def _daemon_ensure(self):
        """Spawn le daemon si nécessaire et renvoie le Popen vivant."""
        proc = getattr(self, '_daemon_proc', None)
        if proc is not None and proc.poll() is None:
            return proc

        if not self.xlsx_path:
            raise RuntimeError(
                "xlsx_path absent — daemon ne peut pas démarrer")

        script = Path(__file__).parent / 'tool_gui_cli.py'

        # Invocation directe : le shebang #!/usr/bin/env python3-uno du script
        # cible sélectionne le Python embarqué LO (Mac) ou python3 (Linux).
        # stderr → fichier de log : le daemon parle JSON RPC sur stdout, mais
        # ses exceptions (ex: _close_batch au shutdown) doivent rester
        # observables — DEVNULL rendrait le debug aveugle (cf. bug Mac
        # add_account / Cmd+Q diagnostic, mai 2026).
        log_dir = Path(__file__).parent / 'logs'
        log_dir.mkdir(exist_ok=True)
        self._daemon_err_path = log_dir / 'daemon.err'
        self._daemon_proc = subprocess.Popen(
            [str(script), str(self.xlsx_path), 'daemon'],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=open(self._daemon_err_path, 'w'),
            text=True,
            bufsize=1,
        )

        ready_line = self._daemon_proc.stdout.readline()
        if not ready_line:
            rc = self._daemon_proc.poll()
            self._daemon_proc = None
            raise RuntimeError(
                f"Daemon mort au démarrage (returncode={rc})")
        ready = json.loads(ready_line)
        if ready.get('event') != 'ready':
            raise RuntimeError(
                f"Daemon réponse inattendue au démarrage : {ready}")

        return self._daemon_proc

    @staticmethod
    def _json_sanitize(obj):
        """Convertit récursivement les types non-JSON-natifs (sets, tuples)
        en équivalents sérialisables (listes). Préserve dicts/listes/scalaires."""
        if isinstance(obj, set):
            return [DaemonClientMixin._json_sanitize(v) for v in obj]
        if isinstance(obj, dict):
            return {k: DaemonClientMixin._json_sanitize(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [DaemonClientMixin._json_sanitize(v) for v in obj]
        return obj

    def _daemon_call(self, method, **kwargs):
        """Appel JSON synchrone : sérialise {method, kwargs} → stdin,
        lit la réponse → stdout, renvoie response['result'].

        Lève RuntimeError si daemon mort, JSON invalide, ou ok:false.
        Le stdout interne capturé par le daemon est ignoré silencieusement.
        Les sets en kwargs sont convertis en listes (JSON ne sait pas les
        sérialiser) ; côté daemon les workers acceptent indifféremment.

        Auto-flush : si `method` est dans `_FLUSH_AFTER`, force un __flush__
        après le call pour que le file disque soit à jour avant qu'un caller
        (ex: `_after_accounts_save` qui relit via openpyxl) ne voie un état
        stale. Couvre les chemins via proxy `__getattr__` ET les appels
        directs `self._daemon_call('add_account', ...)` depuis la GUI Tk.
        """
        kwargs = self._json_sanitize(kwargs)
        with self._daemon_lock:
            proc = self._daemon_ensure()
            req = {'method': method, 'kwargs': kwargs}
            proc.stdin.write(json.dumps(req) + '\n')
            proc.stdin.flush()

            response_line = proc.stdout.readline()
            if not response_line:
                rc = proc.poll()
                self._daemon_proc = None
                raise RuntimeError(
                    f"Daemon mort sans réponse (returncode={rc}) — "
                    f"méthode '{method}'")

            response = json.loads(response_line)
            if not response.get('ok'):
                err = response.get('error', '?')
                stdout = response.get('stdout', '')
                if stdout:
                    print(stdout, end='')
                # Stack trace déjà loggée par le daemon dans logs/daemon.err
                # (cf. _daemon_loop) — ne pas la dupliquer dans le RuntimeError
                # affiché à l'utilisateur.
                raise RuntimeError(f"daemon.{method} : {err}")
            # Relayer la stdout daemon pour diagnostic (les TNR captent ainsi
            # les ERREUR: prints des workers qui sinon disparaissent).
            stdout = response.get('stdout', '')
            if stdout:
                print(stdout, end='')
            result = response.get('result')

        # Flush hors lock pour éviter le deadlock (_daemon_flush prend aussi
        # le lock). Ne flush pas pour les commandes spéciales __quit__/__flush__
        # (qui ferment déjà le batch) — testées par le check `in _FLUSH_AFTER`.
        if method in self._FLUSH_AFTER:
            self._daemon_flush()
        return result

    def _daemon_flush(self):
        """Save côté daemon + ferme le batch (relâche le lock file).
        Le process daemon reste vivant pour les ops suivantes."""
        if getattr(self, '_daemon_proc', None) is None:
            return
        self._daemon_call('__flush__')

    def _daemon_quit(self):
        """Sauvegarde, ferme le batch, termine le process daemon.
        Idempotent — peut être appelé même si daemon jamais spawné."""
        proc = getattr(self, '_daemon_proc', None)
        if proc is None or proc.poll() is not None:
            self._daemon_proc = None
            return

        try:
            proc.stdin.write(json.dumps({'method': '__quit__'}) + '\n')
            proc.stdin.flush()
            response_line = proc.stdout.readline()
            # Ne PAS swallow une éventuelle erreur du save final : si le daemon
            # renvoie ok=false, relayer error/trace pour qu'on le voie côté
            # terminal GUI (sinon perte silencieuse d'une exception de save).
            if response_line:
                try:
                    resp = json.loads(response_line)
                    if not resp.get('ok'):
                        print(f"⚠ daemon __quit__ failed: {resp.get('error', '?')}")
                        trace = resp.get('trace', '')
                        if trace:
                            print(trace)
                        stdout = resp.get('stdout', '')
                        if stdout:
                            print(stdout, end='')
                except (json.JSONDecodeError, ValueError):
                    pass  # ligne pas JSON (ex: stdout pollué) — diagnostic via logs/daemon.err
        except (BrokenPipeError, ValueError, OSError):
            pass  # daemon déjà parti, rien à faire

        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()

        self._daemon_proc = None


class DaemonGUI(DaemonClientMixin):
    """Façade JSON RPC vers tool_gui_cli.py daemon — pour les TNR.

    Expose la même API publique que `HeadlessGUI` (add_devise, add_account,
    purge_account, etc.) mais chaque appel est routé via daemon. Le batch
    est géré côté daemon (ouvert lazy au 1er call, fermé via __flush__ /
    __quit__).

    Usage :
        with DaemonGUI(xlsx_path) as gui:
            gui.add_devise('USD', 'fiat')
            gui.add_account('Compte X', 'Euros')
            # __exit__ envoie __quit__ → save + cleanup

    Limites :
    - `gui.batch()` est un context manager no-op (le daemon maintient son
      propre batch). Les kwargs `doc=` passés en API sont strippés avant
      JSON RPC (le daemon réinjecte batch_doc côté serveur).
    - Les appels qui manipulent directement le `doc` UNO (`ws.getCellByPosition`,
      `doc.cr.refresh`) ne sont pas proxyables → tnr_build inutilisable via
      DaemonGUI, reste in-process.
    """

    # Méthodes proxyées vers le daemon (publiques + workers utiles aux TNR).
    # Toute autre méthode/attribut → AttributeError.
    _PROXY_METHODS = frozenset({
        # CRUD devises
        'add_devise', 'delete_devise',
        # CRUD comptes
        'add_account', 'delete_account', 'modify_account', 'rename_account',
        'purge_account', 'cleanup_patrimoine',
        # CRUD titres
        'add_title', 'rename_pv_title', 'delete_pv_title',
        # CRUD budget
        'add_category', 'delete_category', 'purge_category', 'rename_category',
        'set_category_poste',
        'add_poste', 'delete_poste', 'update_poste',
        # Recatégorisation post-import
        'recategorize',
        # Workers utilisés par certains TNR (light_build)
        '_save_accounts',
        # Lecture
        'check', 'list_accounts',
    })

    def __init__(self, xlsx_path):
        self.xlsx_path = Path(xlsx_path)
        if not self.xlsx_path.exists():
            raise FileNotFoundError(f"xlsx introuvable : {self.xlsx_path}")
        self._daemon_proc = None
        self._daemon_lock = threading.Lock()

    def __enter__(self):
        # Spawn le daemon dès l'entrée pour que les premières erreurs
        # remontent vite (vs attendre le 1er call).
        self._daemon_ensure()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._daemon_quit()
        return False  # ne masque pas les exceptions du bloc

    # `_FLUSH_AFTER` hérité de DaemonClientMixin — déclenche le flush
    # automatique au retour de `_daemon_call`.

    def __getattr__(self, name):
        """Proxy générique : toute méthode du set _PROXY_METHODS devient
        un appel JSON RPC. Args positionnels convertis en kwargs via la
        signature de HeadlessGUI (JSON RPC ne transporte que des kwargs).
        Le kwarg `doc=` est strippé (le daemon gère son batch interne).
        Le flush des ops dans `_FLUSH_AFTER` est géré dans `_daemon_call`.
        """
        if name in self._PROXY_METHODS:
            def _proxy(*args, **kwargs):
                if args:
                    import inspect
                    from tool_gui_cli import HeadlessGUI
                    sig = inspect.signature(getattr(HeadlessGUI, name))
                    params = [p for p in sig.parameters.values()
                              if p.name != 'self'
                              and p.kind in (p.POSITIONAL_OR_KEYWORD,
                                              p.POSITIONAL_ONLY)]
                    for i, val in enumerate(args):
                        kwargs[params[i].name] = val
                kwargs.pop('doc', None)
                return self._daemon_call(name, **kwargs)
            return _proxy
        raise AttributeError(
            f"DaemonGUI : méthode '{name}' non proxyée. "
            f"Ajouter à _PROXY_METHODS si pertinent pour les TNR.")

    def batch(self):
        """Context manager no-op : le daemon ouvre son batch lazy au 1er
        call et le ferme via __flush__. Le `doc` retourné par __enter__
        est None — les tests qui passent `doc=doc` en kwargs le verront
        strippé par le proxy."""
        outer = self
        class _NoOpBatch:
            def __enter__(self_):
                return None
            def __exit__(self_, *exc_info):
                outer._daemon_flush()
                return False
        return _NoOpBatch()
