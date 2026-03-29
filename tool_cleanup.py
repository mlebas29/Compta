#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cpt_cleanup.py - Nettoie les processus Python orphelins et fichiers temporaires

Usage:
  ./cpt_cleanup.py              # Nettoyage complet
  ./cpt_cleanup.py --processes  # Seulement les processus
  ./cpt_cleanup.py --temp       # Seulement les fichiers temporaires
"""

import subprocess
import sys
import os
from pathlib import Path
import argparse


def kill_orphan_processes(dry_run=False):
    """Tue les processus Python bloqués sur openpyxl/Excel"""

    # Chercher les processus Python avec critères suspects
    try:
        result = subprocess.run(
            ['ps', 'aux'],
            capture_output=True,
            text=True,
            timeout=5
        )

        orphans = []
        for line in result.stdout.split('\n'):
            if 'python3' in line.lower():
                parts = line.split()
                if len(parts) < 11:
                    continue

                pid = parts[1]
                cpu = float(parts[2])
                cmd = ' '.join(parts[10:])

                # Critères de détection : CPU > 50% ou contient BACKUP_PURGE/openpyxl
                if cpu > 50.0 or 'BACKUP_PURGE' in cmd or 'load_workbook' in cmd:
                    # Ignorer les processus système
                    if 'networkd' not in cmd and 'unattended' not in cmd:
                        orphans.append((pid, cpu, cmd[:80]))

        if not orphans:
            print("✓ Aucun processus orphelin détecté")
            return 0

        print(f"⚠️  {len(orphans)} processus suspect(s) détecté(s) :")
        for pid, cpu, cmd in orphans:
            print(f"  PID {pid} (CPU: {cpu}%) : {cmd}")

        if dry_run:
            print("\n🔍 MODE DRY-RUN - Aucun processus tué")
            return len(orphans)

        # Demander confirmation si plus de 3 processus
        if len(orphans) > 3:
            response = input(f"\nTuer {len(orphans)} processus ? [o/N] ")
            if response.lower() != 'o':
                print("Annulé")
                return 0

        # Tuer les processus
        killed = 0
        for pid, cpu, cmd in orphans:
            try:
                subprocess.run(['kill', '-9', pid], timeout=2)
                killed += 1
            except Exception as e:
                print(f"⚠️  Échec kill PID {pid}: {e}")

        print(f"\n✓ {killed} processus tué(s)")
        return killed

    except Exception as e:
        print(f"❌ Erreur détection processus: {e}", file=sys.stderr)
        return -1


def clean_temp_files():
    """Nettoie les fichiers temporaires de tâches"""

    temp_dir = Path('/tmp/claude/-home-marc-Compta-Claude/tasks')

    if not temp_dir.exists():
        print("✓ Aucun répertoire temporaire")
        return 0

    # Supprimer les fichiers .output
    count = 0
    for f in temp_dir.glob('*.output'):
        try:
            f.unlink()
            count += 1
        except Exception as e:
            print(f"⚠️  Échec suppression {f.name}: {e}")

    if count > 0:
        print(f"✓ {count} fichier(s) temporaire(s) supprimé(s)")
    else:
        print("✓ Aucun fichier temporaire à nettoyer")

    return count


def main():
    parser = argparse.ArgumentParser(description='Nettoie processus orphelins et fichiers temporaires')
    parser.add_argument('--processes', action='store_true', help='Seulement les processus')
    parser.add_argument('--temp', action='store_true', help='Seulement les fichiers temporaires')
    parser.add_argument('--dry-run', action='store_true', help='Simuler sans tuer')

    args = parser.parse_args()

    # Par défaut, tout nettoyer
    do_processes = args.processes or not args.temp
    do_temp = args.temp or not args.processes

    print("=" * 80)
    print("NETTOYAGE SYSTÈME")
    print("=" * 80)
    print()

    total = 0

    if do_processes:
        print("🔍 Recherche de processus orphelins...")
        killed = kill_orphan_processes(dry_run=args.dry_run)
        if killed > 0:
            total += killed
        print()

    if do_temp:
        print("🗑️  Nettoyage fichiers temporaires...")
        cleaned = clean_temp_files()
        total += cleaned
        print()

    print("=" * 80)
    if args.dry_run:
        print(f"🔍 DRY-RUN - {total} élément(s) détecté(s)")
    else:
        print(f"✓ NETTOYAGE TERMINÉ - {total} élément(s) nettoyé(s)")
    print("=" * 80)


if __name__ == '__main__':
    main()
