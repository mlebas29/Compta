#!/usr/bin/env python3
"""Audit des profils de navigation par site (s.202).

Répond à « le site a-t-il changé de comportement ? » en comparant le dernier run
de chaque fetcher à sa baseline glissante machine-locale (logs/fetch_profiles.json,
alimentée par inc_fetch.fetch_main). Aucune collecte n'est lancée : lecture seule.

Usage :
  tool_fetch_profile.py                # résumé (sites, runs, dernier état)
  tool_fetch_profile.py --report       # dérives du dernier run vs baseline
  tool_fetch_profile.py --show SITE     # baseline détaillée d'un site
"""
import argparse
import sys

import inc_mode
import inc_fetch_profile as prof_mod

BASE_DIR = inc_mode.get_base_dir()


def cmd_list(data):
    if not data:
        print("Aucun profil enregistré (lance une collecte d'abord).")
        return
    print(f"{'Site':<14}{'runs':>5}  {'dernier':<8}{'fichiers':>9}  étapes")
    print("-" * 60)
    for site in sorted(data):
        p = data[site]
        last = "✓ ok" if p.get("last_ok") else "✗ échec"
        exp = p.get("files_expected", 0)
        nsteps = len(p.get("steps", {}))
        print(f"{site:<14}{p.get('runs', 0):>5}  {last:<8}"
              f"{exp:>9}  {nsteps} étape(s)")


def cmd_report(data):
    if not data:
        print("Aucun profil enregistré (lance une collecte d'abord).")
        return 0
    any_drift = False
    clean = []
    for site in sorted(data):
        drifts = prof_mod.compare(data[site])
        if drifts:
            any_drift = True
            print(f"\n⚠️  {site} — dérive(s) au dernier run :")
            for d in drifts:
                print(f"     • {d}")
        else:
            clean.append(site)
    if clean:
        print(f"\n✓ Conformes : {', '.join(clean)}")
    if not any_drift:
        print("\nAucune dérive détectée.")
    return 1 if any_drift else 0


def cmd_show(data, site):
    p = data.get(site)
    if not p:
        print(f"Pas de profil pour « {site} ». Sites connus : "
              f"{', '.join(sorted(data)) or '(aucun)'}")
        return 1
    print(f"Profil {site} — {p.get('runs', 0)} run(s), "
          f"{p.get('files_expected', 0)} fichier(s) attendu(s), "
          f"dernier : {'✓ ok' if p.get('last_ok') else '✗ échec'}")
    print(f"\n  {'Étape':<40}{'médiane':>9}  échantillons")
    print("  " + "-" * 66)
    for label, s in p.get("steps", {}).items():
        med = s.get("median", "?")
        samples = ", ".join(str(x) for x in s.get("samples", []))
        print(f"  {label:<40}{str(med) + 's':>9}  [{samples}]")
    run = p.get("last_run")
    if run:
        print(f"\n  Dernier run : {run['files']} fichier(s), "
              f"{'ok' if run['ok'] else 'échec'}")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--report', action='store_true',
                        help="signale les dérives du dernier run vs baseline")
    parser.add_argument('--show', metavar='SITE',
                        help="baseline détaillée d'un site")
    args = parser.parse_args()

    data = prof_mod.load(BASE_DIR)

    if args.show:
        return cmd_show(data, args.show.upper())
    if args.report:
        return cmd_report(data)
    cmd_list(data)
    return 0


if __name__ == '__main__':
    sys.exit(main())
