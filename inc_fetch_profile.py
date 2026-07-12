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
"""
import json
from pathlib import Path
from statistics import median

WINDOW = 10        # échantillons de durée gardés par étape (baseline = médiane)
DRIFT_FACTOR = 2.0  # durée d'un run > FACTOR × médiane = dérive signalée
MIN_DRIFT_S = 5     # ...et écart absolu ≥ MIN_DRIFT_S (ne pas crier sur 1s→3s)


def _fmt(s):
    """Durée lisible : décimale sous 10 s (sinon '0s' pour du sous-seconde)."""
    return f"{s:.1f}s" if s < 10 else f"{s:.0f}s"


def _store_path(base_dir):
    return Path(base_dir) / 'logs' / 'fetch_profiles.json'


def load(base_dir):
    """Charge le store (dict) ; {} si absent ou illisible."""
    p = _store_path(base_dir)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding='utf-8'))
        except Exception:
            return {}
    return {}


def save(base_dir, data):
    p = _store_path(base_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                 encoding='utf-8')


def record_run(base_dir, site, steps, files, ok):
    """Enregistre un run et met à jour la baseline du site.

    steps : liste [(label, durée_s)] (logger.steps()).
    files : liste des fichiers produits (fetcher.downloads).
    ok    : bool succès de la collecte.
    """
    if not site:
        return
    data = load(base_dir)
    prof = data.setdefault(site, {"steps": {}, "runs": 0})

    for label, dur in steps:
        s = prof["steps"].setdefault(label, {"samples": []})
        s["samples"].append(round(dur, 1))
        s["samples"] = s["samples"][-WINDOW:]
        s["median"] = round(median(s["samples"]), 1)

    nfiles = len(files)
    prof["last_run"] = {
        "steps": [[label, round(dur, 1)] for label, dur in steps],
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
    for label, dur in run["steps"]:
        seen.add(label)
        s = baseline.get(label)
        if not s or "median" not in s:
            drifts.append(f"étape nouvelle : « {label} » ({dur:.0f}s)")
            continue
        med = s["median"]
        if med > 0 and dur > DRIFT_FACTOR * med and (dur - med) >= MIN_DRIFT_S:
            drifts.append(
                f"« {label} » {_fmt(dur)} ≫ médiane {_fmt(med)} (×{dur / med:.1f})")
    for label in baseline:
        if label not in seen:
            drifts.append(f"étape manquante : « {label} »")

    exp = prof.get("files_expected", 0)
    if exp and run["files"] < exp:
        drifts.append(f"fichiers : {run['files']} produit(s) < {exp} attendu(s)")
    if not run["ok"]:
        drifts.append("collecte en échec/partielle")
    return drifts
