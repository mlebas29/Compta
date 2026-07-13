"""Profil de navigation par site (s.202).

Baseline glissante MACHINE-LOCALE des durées d'étape + du nombre de fichiers
produits par chaque fetcher, pour répondre à « le site a-t-il changé de
comportement ? » (nouvelle étape, étape disparue, durée qui explose, fichier
manquant, timeout atteint).

Deux natures de signal :
  - STRUCTURE (étapes présentes, fichiers produits, échec) = globale, robuste,
    répond fort à « site changé ? » ;
  - DURÉES = machine-locale et bruitée → baseline = MÉDIANE d'une fenêtre
    glissante (robuste aux pics : un run à 120 s ne déplace pas la médiane de 15).

Store gitignoré (logs/fetch_profiles.json → machine-local d'office). Alimenté par
inc_fetch.fetch_main à chaque run (record_run) ; lu par tool_fetch_profile.py.
Le profil ne doit JAMAIS casser une collecte (appelé sous try/except muet).
Store versionné par PROFILE_VERSION (enveloppe {version, sites}) : un changement de
format cassant bump le numéro → le store est JETÉ et reconstruit (cache jetable, pas
de migration ; « version » ≠ un « schéma » de cohérence classeur/config).
"""
import json
from pathlib import Path
from statistics import median

WINDOW = 10        # échantillons de durée gardés par étape (baseline = médiane)
DRIFT_FACTOR = 2.0  # durée d'un run > FACTOR × médiane = dérive signalée
MIN_DRIFT_S = 5     # ...et écart absolu ≥ MIN_DRIFT_S (ne pas crier sur 1s→3s)
# Version du FORMAT du store de profil (enveloppe {version, sites}). Volontairement
# nommé « version » et NON « schéma » : ce n'est PAS un marqueur de cohérence
# (≠ SCHEMA_VERSION classeur / config_schema_version, eux migrés et gatés à la
# release). Ici = cache jetable machine-local → un mismatch de version EXPLICITE au
# load = DISCARD + rebuild par les runs suivants, JAMAIS de migration. Le format nu
# legacy (sans clé "version") est ADOPTÉ, pas jeté (emballé au prochain save → zéro
# perte). Bump SEULEMENT sur un changement cassant (un champ existant qui change de
# sens) ; les ajouts purement additifs restent gérés en lecture tolérante.
PROFILE_VERSION = 1


def _fmt(s):
    """Durée lisible : décimale sous 10 s (sinon '0s' pour du sous-seconde)."""
    return f"{s:.1f}s" if s < 10 else f"{s:.0f}s"


def _store_path(base_dir):
    return Path(base_dir) / 'logs' / 'fetch_profiles.json'


def load(base_dir):
    """Charge le store et renvoie {site: profil} (dict).

    Enveloppe VERSIONNÉE {"version": N, "sites": {...}}. Politique :
      - format NU legacy (pas de clé "version") → ADOPTÉ tel quel (les champs
        ajoutés sont lus en tolérant), ré-emballé au prochain save : aucune
        perte de l'historique existant ;
      - "version" présente mais ≠ code (`PROFILE_VERSION`) → store JETÉ (renvoie
        {}), reconstruit par les runs suivants — cache dérivé machine-local, on
        INVALIDE sans migrer. Le discard est réservé à ce mismatch EXPLICITE
        (un vrai changement de format cassant).
    {} aussi si absent / illisible / structure inattendue.
    """
    p = _store_path(base_dir)
    if not p.exists():
        return {}
    try:
        raw = json.loads(p.read_text(encoding='utf-8'))
    except Exception:
        return {}
    if not isinstance(raw, dict):
        return {}
    if "version" not in raw:
        return raw                    # legacy nu → adopté (emballé au prochain save)
    if raw.get("version") != PROFILE_VERSION:
        return {}                     # mismatch explicite → discard + rebuild
    sites = raw.get("sites", {})
    return sites if isinstance(sites, dict) else {}


def save(base_dir, data):
    """Écrit le store sous enveloppe versionnée {"version", "sites"}."""
    p = _store_path(base_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"version": PROFILE_VERSION, "sites": data},
                            ensure_ascii=False, indent=2),
                 encoding='utf-8')


def record_run(base_dir, site, steps, files, ok):
    """Enregistre un run et met à jour la baseline du site.

    steps : liste [(label, durée_s[, interacted])] (logger.steps()).
    files : liste des fichiers produits (fetcher.downloads).
    ok    : bool succès de la collecte.
    """
    if not site:
        return
    data = load(base_dir)
    prof = data.setdefault(site, {"steps": {}, "runs": 0})

    for entry in steps:
        label, dur = entry[0], entry[1]
        interacted = bool(entry[2]) if len(entry) > 2 else False
        s = prof["steps"].setdefault(label, {"samples": []})
        s["samples"].append(round(dur, 1))
        s["samples"] = s["samples"][-WINDOW:]
        s["median"] = round(median(s["samples"]), 1)
        # Occurrence d'interaction humaine (2FA/CAPTCHA/login) sur la même fenêtre
        # glissante que les durées → signal STRUCTUREL (un pas devenu interactif =
        # changement de comportement du site). Le flag du dernier run = interactions[-1].
        inter = s.setdefault("interactions", [])
        inter.append(1 if interacted else 0)
        s["interactions"] = inter[-WINDOW:]
        s["interactive_rate"] = round(
            sum(s["interactions"]) / len(s["interactions"]), 2)

    nfiles = len(files)
    prof["last_run"] = {
        "steps": [[e[0], round(e[1], 1),
                   bool(e[2]) if len(e) > 2 else False] for e in steps],
        "files": nfiles,
        "ok": ok,
    }
    # Fichiers attendus = max observé sur un run RÉUSSI (un run complet fixe la barre).
    if ok:
        prof["files_expected"] = max(prof.get("files_expected", 0), nfiles)
    prof["last_ok"] = ok
    prof["runs"] = prof.get("runs", 0) + 1
    data[site] = prof
    save(base_dir, data)


def compare(prof):
    """Compare le dernier run (prof['last_run']) à la baseline du profil.

    Renvoie une liste de dérives (str). Vide = conforme. Le run est déjà inclus
    dans la médiane, mais la médiane l'absorbe (fenêtre glissante) → un pic
    ressort quand même. Ne compare que s'il y a une baseline et un last_run.
    """
    drifts = []
    run = prof.get("last_run")
    if not run:
        return drifts
    baseline = prof.get("steps", {})
    seen = set()
    for entry in run["steps"]:
        label, dur = entry[0], entry[1]
        interacted = bool(entry[2]) if len(entry) > 2 else False
        seen.add(label)
        s = baseline.get(label)
        if not s or "median" not in s:
            drifts.append(f"étape nouvelle : « {label} » ({dur:.0f}s)")
            continue
        med = s["median"]
        if med > 0 and dur > DRIFT_FACTOR * med and (dur - med) >= MIN_DRIFT_S:
            drifts.append(
                f"« {label} » {_fmt(dur)} ≫ médiane {_fmt(med)} (×{dur / med:.1f})")
        # Étape devenue interactive : le dernier run a exigé une action humaine
        # alors que l'historique en était (quasi) dépourvu → changement structurel.
        # Taux historique = hors run courant (déjà inclus dans interactions[-1]).
        inter = s.get("interactions", [])
        if interacted and len(inter) >= 3 and (sum(inter) - 1) / (len(inter) - 1) <= 0.3:
            drifts.append(
                f"étape « {label} » devenue interactive (2FA/CAPTCHA inhabituel)")
    for label in baseline:
        if label not in seen:
            drifts.append(f"étape manquante : « {label} »")

    exp = prof.get("files_expected", 0)
    if exp and run["files"] < exp:
        drifts.append(f"fichiers : {run['files']} produit(s) < {exp} attendu(s)")
    if not run["ok"]:
        drifts.append("collecte en échec/partielle")
    return drifts
