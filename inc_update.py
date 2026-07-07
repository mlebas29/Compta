"""inc_update.py — probes d'ajustement partagées (détection pure, sans effet).

Cervelle commune de la doctrine de cohérence (#94/#98, cf. Compta_coherence.md) :
des probes PURES qui lisent l'état RÉEL d'un clone et retournent un verdict
texte. Deux front-ends les consomment, chacun à SA cadence, chacun RECALCULANT
(aucun cache inter-acteur — fraîcheur garantie par construction) :

  - cpt_gui / cpt.py (démarrage, quotidien) : ALERTE — AFFICHE les warnings /
    BLOQUE sur schema, ne mute JAMAIS.
  - upgrade.py (rare) : RÉSOUT — applique les migrations et avance les marqueurs.

Le partage est du CODE (ces fonctions), pas une donnée figée passée de l'un à
l'autre : démarrage et upgrade sont des process distincts, chacun appelle ces
probes pour lui-même.

Perf — le seul hotspot est l'ouverture du classeur (.xlsm à macros/NR). Les
probes classeur acceptent un workbook DÉJÀ ouvert (param `wb`, injection) pour
qu'un front-end qui l'a déjà chargé ne le rouvre pas. Les probes config sont du
texte (cheap).
"""

import configparser
import json
import os
import re
from pathlib import Path

import openpyxl


# --- Badges de release ------------------------------------------------------
# Univers CLOS, 5 types (légende canonique CHANGELOG.md). Portés par
# upgrade_map.json (machine-lisible) ; le CHANGELOG en est le rendu humain, jamais
# parsé. L'avis au démarrage n'est PLUS dérivé des badges (modèle #99 retiré) mais
# du MARQUEUR de chaque composant (cf. check_config_schema / check_schema_compat,
# Compta_coherence.md) : la forme du marqueur porte la gravité. Les badges restent
# DESCRIPTIFS (rendu par mode, légende). 🔄 (reclone) est franchi automatiquement
# par upgrade ; 📘 (classeur exemple) n'est pas actionnable en mode assisté.
# 🧱 (butée d'automatisation) est un MARQUEUR cross-périmètre : pas de 'perimetre'
# propre — porté par l'entrée.
KNOWN_BADGES = {'📘', '🔧', '🔄', '⚙️', '🧱'}
MARKER_BADGES = {'🧱'}  # badges sans section propre, routés par le périmètre de l'entrée


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
    fix = ('→ Mettre à niveau : `upgrade.py` (mode assisté, réversible — geste dans\n'
           '  Compta_upgrade_assiste.md) ; ou Compta_upgrade_classeur.md (mode classeur).')
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


def _version_tuple(s):
    """'5.15.0' -> (5, 15, 0) pour un tri NUMÉRIQUE (≠ lexico : 5.9 < 5.15)."""
    out = []
    for p in str(s or '').split('.'):
        try:
            out.append(int(p))
        except ValueError:
            out.append(0)
    return tuple(out)


def pending_migrations(base_dir, classeur_schema, code_schema):
    """Calcule le chemin de migration d'un classeur depuis la carte.

    Args:
        classeur_schema: SCHEMA_VERSION lu dans le classeur (int) ou None (absent).
        code_schema: SCHEMA_VERSION attendu par le code (int).

    Returns:
        dict {
          'structural': [migrations bloquantes à jouer, dans l'ordre],
          'catchups': [migrations idempotentes au code_schema, app_version croissant],
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

    # TOUS les catchups idempotents au code_schema, triés par app_version
    # CROISSANT (rattrapage déterministe : un classeur qui a sauté des versions
    # les rejoue dans l'ordre historique ; chevauchement éventuel → le plus
    # récent s'applique en dernier = état cible). Tri NUMÉRIQUE (pas lexico,
    # sinon 5.9.0 passerait après 5.15.0). Chacun est idempotent + sondé en
    # dry-run côté upgrade → coût réel = seulement ceux qui ont du travail.
    catchups = sorted(
        (m for m in migs
         if m.get('schema_from') == m.get('schema_to') == code_schema
         and m.get('idempotent')),
        key=lambda m: _version_tuple(m.get('app_version', '')))

    up_to_date = not path and origin is not None and origin >= code_schema
    return {'structural': path, 'catchups': catchups,
            'below_floor': False, 'up_to_date': up_to_date}


def validate_upgrade_map(base_dir, code_schema, known_step_ids=None):
    """Cohérence de la carte vs le code. Retourne list[str] de problèmes (vide=OK).

    Filet de la barrière de release : détecte une carte désynchronisée (SCHEMA
    bumpé sans entrée carte, trou dans la chaîne, outil disparu).

    `known_step_ids` (set, optionnel) : ids des runners de steps INCONDITIONNELS
    connus de l'appelant (upgrade.STEP_RUNNERS). Fourni → parité id↔runner
    BIDIRECTIONNELLE vérifiée (un step de la carte sans runner, ou un runner sans
    entrée steps[] = drift, #121). None → contrôle sauté (appelants hors-upgrade).
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

    # les outils référencés existent (migrations classeur + config)
    for m in migs + cmap.get('config_migrations', []):
        tool = m.get('tool')
        if tool and not (Path(base_dir) / tool).exists():
            problems.append(f"outil absent : {tool} (migration {m.get('id')}).")
    # les migrations CLASSEUR sont invoquées via `./tool` (shebang python3-uno) → bit
    # exécutable requis, sinon rc 126 opaque à l'upgrade. On le vérifie ICI (barrière
    # carte) pour transformer l'omission de +x en « carte incohérente » lisible. Les
    # config_migrations sont lancées `python3 tool` (upgrade.py:244) → +x non requis,
    # hors contrôle.
    for m in migs:
        tool = m.get('tool')
        p = Path(base_dir) / tool if tool else None
        if p and p.exists() and not os.access(p, os.X_OK):
            problems.append(
                f"outil non exécutable : {tool} (chmod +x requis — migration {m.get('id')}).")

    # chaîne config (marker-driven, #98) : la carte atteint le marqueur du code.
    from inc_excel_schema import CONFIG_SCHEMA_VERSION
    cfg_targets = [_parse_marker(m.get('schema_to'))
                   for m in cmap.get('config_migrations', []) if m.get('schema_to')]
    code_cfg = _parse_marker(CONFIG_SCHEMA_VERSION)
    if cfg_targets and code_cfg and max(cfg_targets) != code_cfg:
        problems.append(
            f"max(config schema_to)={max(cfg_targets)} ≠ "
            f"CONFIG_SCHEMA_VERSION={code_cfg} (carte ou code désynchronisé).")

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
        if b not in MARKER_BADGES and e.get('perimetre') not in valid_perim:
            problems.append(f"périmètre invalide « {e.get('perimetre')} » (badge {b}).")
        if e.get('nature') not in valid_nature:
            problems.append(f"nature invalide « {e.get('nature')} » (badge {b}).")
        geste = e.get('geste') or {}
        if not geste or set(geste) - valid_geste:
            problems.append(f"geste invalide pour {b} : {sorted(geste)} (attendu ⊆ {sorted(valid_geste)}).")
        if 'assiste' not in geste and 'assiste_avant' not in geste:
            problems.append(f"badge {b} sans geste assisté.")

    # badge utilisé (migrations + config_migrations + steps + actions) ⊆ légende
    steps = cmap.get('steps', [])
    for entry in migs + actions + cmap.get('config_migrations', []) + steps:
        ref = entry.get('id') or entry.get('app_version') or '?'
        for b in (entry.get('badges') or []):
            if b not in legend:
                problems.append(f"badge « {b} » absent de badges_legend (entrée {ref}).")

    # steps[] (#121) : id obligatoire, périmètre valide, parité id↔runner.
    carte_ids = set()
    for s in steps:
        sid = s.get('id')
        if not sid:
            problems.append('step sans id dans steps[].')
            continue
        carte_ids.add(sid)
        if s.get('perimetre') not in valid_perim:
            problems.append(f"périmètre invalide « {s.get('perimetre')} » (step {sid}).")
    if known_step_ids is not None:
        for sid in sorted(carte_ids - set(known_step_ids)):
            problems.append(f"step « {sid} » sans runner (carte ↛ code, #121).")
        for sid in sorted(set(known_step_ids) - carte_ids):
            problems.append(f"runner « {sid} » sans entrée steps[] (code ↛ carte, #121).")

    return problems


# --- Marqueur de schéma config (#98) — avis ⚙️ « configuration à mettre à niveau »
# Modèle de cohérence (cf. Compta_coherence.md) : le composant Configuration porte
# un marqueur (config.ini [general] config_schema_version) ; le DÉMARRAGE le compare
# au marqueur attendu (CONFIG_SCHEMA_VERSION) et ALERTE (lecture seule, n'écrit
# RIEN) ; UPGRADE SEUL avance le marqueur. La FORME du marqueur porte la gravité :
# major en retard → bloque · minor → avertit · absent ⇒ plancher 0.
# Remplace l'ancien stamp honored_version (#99, retiré) : le marqueur config est
# ancré sur l'état réel du composant, pas sur une « croyance » de version d'app —
# d'où l'immunité au bug s.174 (migration config-JSON invisible au boot).

def _parse_marker(v):
    """Marqueur de composant → (major, minor) pour comparaison.

    Accepte un entier (NR classeur), une string '3' / '3.1' / '0.2', ou None.
    Forme ENTIÈRE (sans '.') → (M, 0), domaine bloquant ; forme DÉCIMALE 'M.m' →
    (M, m), domaine avertissement. None / illisible → None (l'appelant décide du
    plancher). Comparer deux tuples donne directement « major puis minor ».
    """
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    parts = s.split('.')
    try:
        major = int(parts[0])
        minor = int(parts[1]) if len(parts) > 1 and parts[1] != '' else 0
    except (ValueError, IndexError):
        return None
    return (major, minor)


def read_config_schema(config_path):
    """Lit [general] config_schema_version → string brute, ou None (absent/illisible)."""
    config_path = Path(config_path)
    if not config_path.exists():
        return None
    cp = configparser.ConfigParser()
    try:
        cp.read(config_path, encoding='utf-8')
    except configparser.Error:
        return None
    val = (cp.get('general', 'config_schema_version', fallback='')
           if cp.has_section('general') else '').strip()
    return val or None


def pending_config_migrations(base_dir, config_schema, code_marker):
    """Chemin de migration config depuis la carte (marker-driven, #98).

    Args:
        config_schema: marqueur relevé (config.ini) — string ou None (absent ⇒ plancher (0,0)).
        code_marker: CONFIG_SCHEMA_VERSION attendu par le code (string).

    Returns:
        list[dict]: entrées à jouer, dans l'ordre de la carte — celles dont
        schema_to dépasse le relevé (jusqu'au code), PLUS les entrées SILENCIEUSES
        (sans schema_to) rejouées systématiquement (idempotentes, run-all). Le
        « run-all sans gating » d'avant #98 ne survit que pour ces silencieuses.
    """
    migs = load_upgrade_map(base_dir).get('config_migrations', [])
    releve = _parse_marker(config_schema) or (0, 0)
    code = _parse_marker(code_marker)
    out = []
    for m in migs:
        to = _parse_marker(m.get('schema_to'))
        if to is None:                       # entrée silencieuse → toujours rejouée
            out.append(m)
        elif to > releve and (code is None or to <= code):
            out.append(m)
    return out


def _write_general_key(config_path, key, value):
    """SEUL writer Python de config.ini : pose/avance [general] `key` = `value` par
    édition ligne à ligne (préserve commentaires et mise en page, comme set_mode
    côté shell — JAMAIS de dump configparser, qui les écraserait). Best-effort :
    une erreur est silencieuse. Retourne True si écrit."""
    config_path = Path(config_path)
    if not config_path.exists():
        return False
    try:
        lines = config_path.read_text(encoding='utf-8').splitlines(keepends=True)
    except OSError:
        return False

    key_re = re.compile(rf'^\s*#?\s*{re.escape(key)}\s*=', re.I)
    sec_re = re.compile(r'^\s*\[([^\]]+)\]')
    stamp = f'{key} = {value}\n'
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
        if in_general and not written and key_re.match(line):
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


def write_config_schema(config_path, value):
    """Écrit/avance [general] config_schema_version = `value` dans config.ini.

    Appelé par UPGRADE SEUL (fin de run config) et le seed install — jamais par le
    démarrage (qui n'alerte que). Best-effort (le marqueur n'est pas load-bearing :
    les outils config restent idempotents + auto-gated sur l'état réel). Retourne
    True si écrit.
    """
    return _write_general_key(config_path, 'config_schema_version', value)


def check_config_schema(config_path, base_dir=None, code_marker=None):
    """#98 — avis ⚙️ « configuration à mettre à niveau », piloté par le marqueur.

    Compare le marqueur relevé (config.ini, absent ⇒ plancher (0,0)) au marqueur
    attendu (CONFIG_SCHEMA_VERSION). Détection PURE — n'écrit RIEN (upgrade SEUL
    avance le marqueur). La FORME décide la gravité : major en retard → bloquant ·
    minor → avertissement (cf. Compta_coherence.md). `base_dir` n'est pas utilisé
    (le marqueur attendu vient du code) — gardé pour la symétrie de signature.

    Returns:
        dict {verdict: 'silent'|'advise', severity: 'warn'|'block'|None,
              message: str|None}.
    """
    if code_marker is None:
        from inc_excel_schema import CONFIG_SCHEMA_VERSION
        code_marker = CONFIG_SCHEMA_VERSION
    silent = {'verdict': 'silent', 'severity': None, 'message': None}
    code = _parse_marker(code_marker)
    if code is None:
        return silent
    releve = _parse_marker(read_config_schema(config_path)) or (0, 0)
    if releve >= code:
        return silent
    severity = 'block' if code[0] > releve[0] else 'warn'
    lead = 'BLOQUANT — ' if severity == 'block' else ''
    # Message GÉNÉRIQUE (le boot ALERTE, ne sonde pas — pas de numéros de schéma
    # cryptiques qui sous-vendraient le changement) ; le DÉTAIL effectif (quoi sera
    # migré) est à un `upgrade.py --check` près. Cf. Compta_coherence.md.
    msg = (f'{lead}Configuration à mettre à niveau → lance upgrade.py '
           f'(détail : upgrade.py --check ; cf. Compta_upgrade_assiste.md).')
    return {'verdict': 'advise', 'severity': severity, 'message': msg}


def startup_config_advice(config_path, base_dir, code_marker=None):
    """Avis config au démarrage — ordre canonique partagé CLI + GUI (1 seule source
    pour que les deux appelants ne divergent JAMAIS).

    Gating mutuellement exclusif :
      1. check_config_schema D'ABORD (marqueur ⚙️ en retard ? — #98, marker-driven).
      2. marqueur en retard → cet avis SEUL : upgrade honore le composant config
         (install_fix normalize ET les config_migrations via apply_benign) → citer
         en plus le générique check_config_obsolete (qui ne renvoie qu'à install_fix)
         serait redondant.
         sinon → check_config_obsolete (filet générique, toujours-ON) : il ne reste
         alors que du générique à normaliser, son renvoi vers install_fix est juste.

    Le DÉMARRAGE NE MUTE JAMAIS (ni marqueur ni config) — upgrade SEUL résout.

    Returns:
        list[str]: avertissements à afficher, dans l'ordre.
    """
    r = check_config_schema(config_path, base_dir, code_marker)
    if r['message']:
        return [r['message']]
    return check_config_obsolete(config_path)
