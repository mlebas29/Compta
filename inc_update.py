"""inc_update.py — probes d'ajustement partagées (détection pure, sans effet).

Cervelle commune de la doctrine de rattrapage (#94, cf. Compta_extension.md) :
des probes PURES qui lisent l'état RÉEL d'un clone et retournent un verdict
texte. Deux front-ends les consomment, chacun à SA cadence, chacun RECALCULANT
(aucun cache inter-acteur — fraîcheur garantie par construction) :

  - cpt_gui (démarrage, quotidien) : AFFICHE les warnings / BLOQUE sur schema.
  - install_update.py (post-pull, rare) : APPLIQUE les bénins / signale le reste.

Le partage est du CODE (ces fonctions), pas une donnée figée passée de l'un à
l'autre : GUI et install_update sont deux process distincts, chacun appelle ces
probes pour lui-même.

Perf — le seul hotspot est l'ouverture du classeur (.xlsm à macros/NR). Les
probes classeur acceptent un workbook DÉJÀ ouvert (param `wb`, injection) pour
qu'un front-end qui l'a déjà chargé ne le rouvre pas. Les probes config sont du
texte (cheap).
"""

import configparser
import json
import re
from pathlib import Path

import openpyxl


# --- Badges de release (#99) -------------------------------------------------
# Univers CLOS, 4 types (légende canonique CHANGELOG.md). Portés par
# upgrade_map.json (machine-lisible) ; le CHANGELOG en est le rendu humain, jamais
# parsé. ACTIONABLE = badges qui réclament un geste au démarrage :
#   🔧 migration classeur (→ upgrade) · ⚙️ config à normaliser (→ install_fix).
# 🔄 (reclone) est self-resolving — exécuter du code au-delà d'une frontière
# reclone implique d'avoir reclôné ; 📘 (classeur exemple) n'est pas actionnable
# en mode assisté. Ni l'un ni l'autre ne déclenche d'avis.
KNOWN_BADGES = {'📘', '🔧', '🔄', '⚙️'}
ACTIONABLE_BADGES = {'🔧', '⚙️'}


def check_schema_compat(xlsx_path, wb=None):
    """Vérifie la version de schéma du classeur vs l'application.

    Gate de COMPATIBILITÉ (un entier monotone, le seul rôle qu'une probe d'état
    ne peut pas couvrir : un classeur d'une version future est illisible). Ne
    décide PAS « quoi migrer » — juste « compatible ou non ».

    Args:
        xlsx_path: chemin du classeur (ignoré si `wb` fourni).
        wb: workbook openpyxl déjà ouvert (injection perf) ; sinon ouvert ici
            en lecture seule.

    Returns:
        str | None: message si incompatible (classeur < app, absent ou invalide),
        None si OK ou lecture impossible (non bloquant).
    """
    from inc_excel_schema import SCHEMA_VERSION
    own = False
    try:
        if wb is None:
            if not xlsx_path or not Path(xlsx_path).exists():
                return None  # pas de classeur → rien à vérifier ici
            wb = openpyxl.load_workbook(xlsx_path, data_only=True, read_only=True)
            own = True
        dn = wb.defined_names.get('SCHEMA_VERSION')
    except Exception:
        return None  # pas bloquant si lecture impossible
    finally:
        if own and wb is not None:
            wb.close()

    # Suffixe de routage commun aux trois branches : le geste assisté
    # (upgrade, réversible) d'abord ; la procédure manuelle / mode
    # classeur (Compta_upgrade_classeur.md) en repli.
    fix = ('→ Mettre à niveau : ./upgrade.py (mode assisté, réversible)\n'
           '  ou Compta_upgrade_classeur.md (migration manuelle / mode classeur).')
    if dn is None:
        return (f'Classeur sans numéro de version (version {SCHEMA_VERSION} attendue).\n{fix}')
    try:
        classeur_version = int(dn.attr_text)
    except (ValueError, TypeError):
        return (f'SCHEMA_VERSION invalide : « {dn.attr_text} » (entier attendu).\n{fix}')
    if classeur_version < SCHEMA_VERSION:
        return (f'Classeur version {classeur_version}, version {SCHEMA_VERSION} attendue.\n{fix}')
    return None


def check_config_obsolete(config_path):
    """Compare config.ini à config.ini.default : clés obsolètes / manquantes,
    mode invalide. Indépendant du classeur (texte, cheap).

    - **obsolète** : clé d'une section *connue du modèle* absente de l'univers
      des clés du modèle (actives OU commentées, toutes sections — une clé
      documentée quelque part vaut partout). Les sections inconnues du modèle
      (sites privés) sont ignorées.
    - **manquante** : section / clé *active* du modèle absente de la config.
    - **mode** : valeur hors `VALID_MODES`.

    Args:
        config_path: chemin de config.ini (config.ini.default cherché à côté).

    Returns:
        list[str]: warnings (vide si pas de modèle ou config alignée).
    """
    try:
        from inc_mode import VALID_MODES
    except Exception:
        VALID_MODES = {'DEV', 'PROD', 'EX'}

    config_path = Path(config_path)
    default_path = config_path.parent / 'config.ini.default'
    if not config_path.exists() or not default_path.exists():
        return []

    known_global = set()        # clés (actives+commentées), toutes sections
    default_active = {}         # section -> clés actives
    default_sections = set()
    section = None
    key_re = re.compile(r'^\s*#?\s*([A-Za-z0-9_]+)\s*=')
    sec_re = re.compile(r'^\s*\[([^\]]+)\]')
    try:
        with open(default_path, encoding='utf-8') as fh:
            for line in fh:
                ms = sec_re.match(line)
                if ms:
                    section = ms.group(1)
                    default_sections.add(section)
                    default_active.setdefault(section, set())
                    continue
                if section is None:
                    continue
                mk = key_re.match(line)
                if mk:
                    key = mk.group(1).lower()
                    known_global.add(key)
                    if not line.lstrip().startswith('#'):
                        default_active[section].add(key)
    except OSError:
        return []

    user = configparser.ConfigParser()
    try:
        user.read(config_path, encoding='utf-8')
    except configparser.Error as e:
        return [f'config.ini illisible ({e}) — vérifier la syntaxe.']

    warnings = []
    for sec in user.sections():
        if sec not in default_sections:     # section privée → non jugée
            continue
        for key in sorted({o.lower() for o in user.options(sec)} - known_global):
            warnings.append(
                f'config.ini : clé obsolète [{sec}] {key} — absente de '
                f'config.ini.default ; lance ./install_fix.sh pour normaliser.')
    for sec, keys in default_active.items():
        if not user.has_section(sec):
            if keys:
                warnings.append(
                    f'config.ini : section [{sec}] manquante (présente dans config.ini.default).')
            continue
        for key in sorted(keys - {o.lower() for o in user.options(sec)}):
            warnings.append(
                f'config.ini : clé manquante [{sec}] {key} (active dans config.ini.default).')
    if user.has_option('general', 'mode'):
        raw = user.get('general', 'mode', raw=True).strip()
        if raw.upper() not in VALID_MODES:
            warnings.append(
                f'config.ini : mode « {raw} » invalide (attendu : '
                f'{"/".join(sorted(VALID_MODES))}) ; lance ./install_fix.sh.')
    return warnings


# --- Migration classeur pilotée par carte (#94 volet C) ----------------------
# Lecture PURE : lit la carte (upgrade_map.json) + la version du classeur, et
# calcule le chemin de migration. Consommé par upgrade (l'exécuteur) ;
# le GUI ne s'en sert pas (il garde son blocage SCHEMA simple). Testable hors LO.

def read_classeur_schema(xlsx_path, wb=None):
    """Lit le NR SCHEMA_VERSION du classeur → int, ou None (absent / illisible).

    Args:
        xlsx_path: chemin du classeur (ignoré si `wb` fourni).
        wb: workbook openpyxl déjà ouvert (injection perf).
    """
    own = False
    try:
        if wb is None:
            if not xlsx_path or not Path(xlsx_path).exists():
                return None
            wb = openpyxl.load_workbook(xlsx_path, data_only=True, read_only=True)
            own = True
        dn = wb.defined_names.get('SCHEMA_VERSION')
    except Exception:
        return None
    finally:
        if own and wb is not None:
            wb.close()
    if dn is None:
        return None
    try:
        return int(dn.attr_text)
    except (ValueError, TypeError):
        return None


def load_upgrade_map(base_dir):
    """Lit upgrade_map.json (la carte). Retourne le dict, ou {} si absent/illisible."""
    p = Path(base_dir) / 'upgrade_map.json'
    if not p.exists():
        return {}
    try:
        with open(p, encoding='utf-8') as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def pending_migrations(base_dir, classeur_schema, code_schema):
    """Calcule le chemin de migration d'un classeur depuis la carte.

    Args:
        classeur_schema: SCHEMA_VERSION lu dans le classeur (int) ou None (absent).
        code_schema: SCHEMA_VERSION attendu par le code (int).

    Returns:
        dict {
          'structural': [migrations bloquantes à jouer, dans l'ordre],
          'catchup': la migration idempotente la plus récente (dict) ou None,
          'below_floor': classeur sous le plancher de la carte (non rattrapable),
          'up_to_date': structurellement à jour,
        }
    """
    migs = load_upgrade_map(base_dir).get('migrations', [])
    structural = sorted(
        (m for m in migs if m.get('schema_to', 0) > m.get('schema_from', 0)),
        key=lambda m: m['schema_from'])
    floor = structural[0]['schema_from'] if structural else None

    origin = classeur_schema
    if origin is None:
        # NR absent : la 1ʳᵉ migration structurelle gère « absent → plancher+1 ».
        origin = floor
    elif floor is not None and origin < floor:
        return {'structural': [], 'catchup': None,
                'below_floor': True, 'up_to_date': False}

    path = [m for m in structural
            if origin is not None
            and m['schema_from'] >= origin and m['schema_to'] <= code_schema]

    catchups = [m for m in migs
                if m.get('schema_from') == m.get('schema_to') == code_schema
                and m.get('idempotent')]
    catchup = (sorted(catchups, key=lambda m: m.get('app_version', ''))[-1]
               if catchups else None)

    up_to_date = not path and origin is not None and origin >= code_schema
    return {'structural': path, 'catchup': catchup,
            'below_floor': False, 'up_to_date': up_to_date}


def validate_upgrade_map(base_dir, code_schema):
    """Cohérence de la carte vs le code. Retourne list[str] de problèmes (vide=OK).

    Filet de la barrière de release : détecte une carte désynchronisée (SCHEMA
    bumpé sans entrée carte, trou dans la chaîne, outil disparu).
    """
    problems = []
    cmap = load_upgrade_map(base_dir)
    migs = cmap.get('migrations', [])
    if not migs:
        return ['upgrade_map.json absent ou vide.']
    actions = cmap.get('actions', [])
    legend_entries = cmap.get('badges_legend', [])
    legend = {e.get('badge') for e in legend_entries}

    structural = sorted(
        (m for m in migs if m.get('schema_to', 0) > m.get('schema_from', 0)),
        key=lambda m: m['schema_from'])

    # chaîne structurelle contiguë (pas de trou)
    for a, b in zip(structural, structural[1:]):
        if b['schema_from'] != a['schema_to']:
            problems.append(
                f"trou dans la chaîne : {a['id']} (→{a['schema_to']}) puis "
                f"{b['id']} (depuis {b['schema_from']}).")

    # la carte atteint la version du code
    max_to = max((m.get('schema_to', 0) for m in migs), default=0)
    if max_to != code_schema:
        problems.append(
            f"max(schema_to)={max_to} ≠ SCHEMA_VERSION code={code_schema} "
            f"(carte ou code désynchronisé).")

    # les outils référencés existent
    for m in migs:
        tool = m.get('tool')
        if tool and not (Path(base_dir) / tool).exists():
            problems.append(f"outil absent : {tool} (migration {m.get('id')}).")

    # légende : badge connu + périmètre valide (= SECTION du rendu) + au moins un
    # geste (= mode-applicabilité). Périmètre et geste sont indépendants (ex. 🔧 :
    # périmètre classeur, geste assisté seul) → pas de couplage à vérifier.
    valid_perim = {'classeur', 'config', 'app'}
    valid_nature = {'cumulatif', 'ponctuel', 'informatif'}
    valid_geste = {'assiste', 'assiste_avant', 'classeur'}
    for e in legend_entries:
        b = e.get('badge')
        if b not in KNOWN_BADGES:
            problems.append(f"badge inconnu en légende : « {b} ».")
        if e.get('perimetre') not in valid_perim:
            problems.append(f"périmètre invalide « {e.get('perimetre')} » (badge {b}).")
        if e.get('nature') not in valid_nature:
            problems.append(f"nature invalide « {e.get('nature')} » (badge {b}).")
        geste = e.get('geste') or {}
        if not geste or set(geste) - valid_geste:
            problems.append(f"geste invalide pour {b} : {sorted(geste)} (attendu ⊆ {sorted(valid_geste)}).")
        if 'assiste' not in geste and 'assiste_avant' not in geste:
            problems.append(f"badge {b} sans geste assisté.")

    # badge utilisé (migrations + actions) ⊆ légende
    for entry in migs + actions:
        ref = entry.get('id') or entry.get('app_version') or '?'
        for b in (entry.get('badges') or []):
            if b not in legend:
                problems.append(f"badge « {b} » absent de badges_legend (entrée {ref}).")

    return problems


# --- Stamp honored_version (#99) — avis « version badgée non honorée » --------
# Ferme la surface « git pull nu » du trou raquette upgrade que le gate dur
# check_schema_compat laisse passer (pull de code SANS bump de schéma : fix,
# badge ⚙️/🔄/📘). Dirty-bit O(1) : config.ini [general] honored_version. Tant
# qu'il == APP_VERSION, silence total, ZÉRO sonde (pas d'ouverture classeur juste
# pour découvrir qu'il n'y a rien à dire). Au-delà, lecture de la carte (cheap).

def _parse_version(v):
    """'5.3.1' → (5, 3, 1) pour comparaison ; () si illisible (jamais > rien)."""
    try:
        return tuple(int(x) for x in str(v).strip().split('.'))
    except (ValueError, AttributeError):
        return ()


def _badged_versions(base_dir):
    """[(version_tuple, set(badges)), ...] depuis la carte (entrées avec badges)."""
    m = load_upgrade_map(base_dir)
    out = []
    for entry in (m.get('migrations', []) + m.get('actions', [])):
        av, badges = entry.get('app_version'), entry.get('badges')
        if av and badges:
            out.append((_parse_version(av), set(badges)))
    return out


def check_honored_version(config_path, base_dir, app_version=None):
    """#99 — avis « version badgée non honorée » au démarrage. Détection PURE
    (lit config.ini + upgrade_map.json, jamais le classeur, n'écrit RIEN) :
    l'appelant écrit le stamp via write_honored_version (l'effet lui revient).

    Décision (cf. CLAUDE_todo #99) :
      - honored == APP_VERSION (ou clé seedée) → silence, zéro sonde.
      - honored < APP_VERSION (un pull a eu lieu) → badges actionnables dans
        ]honored, code] ? ⚙️ ne compte que si la config est RÉELLEMENT obsolète
        (live, cheap) — résolu par install_fix ⇒ self-heal au démarrage suivant.
          · aucun actionnable → version réputée honorée → stamp_to = APP_VERSION
            (self-heal : le fast-path O(1) tient ensuite).
          · 🔧 / ⚙️ actionnable → avis, stamp_to = None (n'avance que quand
            upgrade / install_fix a fait le geste).
      - clé absente (install pré-#99 / fraîche) → seed stamp_to = APP_VERSION,
        silence (on ne nage pas un historique inconnu).

    Args:
        config_path: chemin de config.ini.
        base_dir: racine du clone (upgrade_map.json).
        app_version: override (tests) ; sinon inc_excel_schema.APP_VERSION.

    Returns:
        dict {verdict: 'silent'|'heal'|'advise', stamp_to: str|None,
              message: str|None, badges: list[str]}.
    """
    if app_version is None:
        from inc_excel_schema import APP_VERSION
        app_version = APP_VERSION

    silent = {'verdict': 'silent', 'stamp_to': None, 'message': None, 'badges': []}
    config_path = Path(config_path)
    if not config_path.exists():
        return silent
    cp = configparser.ConfigParser()
    try:
        cp.read(config_path, encoding='utf-8')
    except configparser.Error:
        return silent

    honored_raw = (cp.get('general', 'honored_version', fallback='')
                   if cp.has_section('general') else '').strip()
    if not honored_raw:                      # seed (install pré-#99 / fraîche)
        return {'verdict': 'heal', 'stamp_to': app_version, 'message': None, 'badges': []}

    honored, code = _parse_version(honored_raw), _parse_version(app_version)
    if not honored or not code or honored >= code:
        return silent                        # à jour (ou stamp illisible → on n'agit pas)

    actionable = set()
    for ver, badges in _badged_versions(base_dir):
        if honored < ver <= code:
            for b in badges & ACTIONABLE_BADGES:
                if b == '⚙️' and not check_config_obsolete(config_path):
                    continue                 # ⚙️ déjà résolu (config propre)
                actionable.add(b)

    if not actionable:                       # rien à faire → self-heal
        return {'verdict': 'heal', 'stamp_to': app_version, 'message': None, 'badges': []}

    parts = []
    if '🔧' in actionable:
        parts.append('migration du classeur en attente → lance ./upgrade.py')
    if '⚙️' in actionable:
        parts.append('config à normaliser → lance ./install_fix.sh')
    msg = (f'Mise à jour du code détectée (version honorée {honored_raw} → '
           f'{app_version}). Action requise :\n  ' + '\n  '.join(parts))
    return {'verdict': 'advise', 'stamp_to': None, 'message': msg,
            'badges': sorted(actionable)}


def write_honored_version(config_path, version):
    """Écrit/avance [general] honored_version = `version` dans config.ini.

    SEUL writer Python de config.ini : édition ligne à ligne préservant les
    commentaires et la mise en page (comme set_mode côté shell), pas de dump
    configparser. Partagé par tous les acteurs qui posent le stamp :
    upgrade (fin de run OK, version disque), GUI / cpt.py (self-heal +
    seed). EFFET (hors probes) — best-effort : une erreur est silencieuse (le
    stamp n'est pas load-bearing, le gate dur check_schema_compat reste le
    backstop). Retourne True si écrit.
    """
    config_path = Path(config_path)
    if not config_path.exists():
        return False
    try:
        lines = config_path.read_text(encoding='utf-8').splitlines(keepends=True)
    except OSError:
        return False

    key_re = re.compile(r'^\s*honored_version\s*=', re.I)
    sec_re = re.compile(r'^\s*\[([^\]]+)\]')
    stamp = f'honored_version = {version}\n'
    out, in_general, written = [], False, False
    for line in lines:
        ms = sec_re.match(line)
        if ms:
            if in_general and not written:   # on quitte [general] sans la clé → insérer
                out.append(stamp)
                written = True
            in_general = (ms.group(1) == 'general')
            out.append(line)
            continue
        if in_general and key_re.match(line):
            out.append(stamp)
            written = True
            continue
        out.append(line)
    if in_general and not written:           # [general] = dernière section
        out.append(stamp)
        written = True
    if not written:                          # pas de [general] → l'ajouter
        out.append(f'\n[general]\n{stamp}')

    try:
        config_path.write_text(''.join(out), encoding='utf-8')
    except OSError:
        return False
    return True
