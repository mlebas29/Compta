#!/usr/bin/env python3
"""
tool_refs.py - Audit et normalisation des références d'appariement Excel

Usage:
    ./tool_refs.py --audit              # Rapport détaillé des problèmes
    ./tool_refs.py --fix [--dry-run]    # Corriger casse + classe
    ./tool_refs.py --fix-duplicates     # Dédoublonner les N-uplets
"""

import os
import sys
import argparse
import re
import json
from pathlib import Path
from collections import defaultdict
from datetime import datetime
from itertools import combinations

import inc_mode
from inc_logging import Logger
from inc_excel_compta import (
    ComptaExcel,
    normalize_devise,
    classify_reference_pattern,
    normalize_reference_case,
)
from inc_excel_schema import PAIRING_COUNTER_CELL, ColResolver

# Configuration environnement
BASE_DIR = inc_mode.get_base_dir()
EXCEL_FILE = BASE_DIR / 'comptes.xlsm'
VALIDATED_GROUPS_FILE = BASE_DIR / 'validated_groups.json'


class ComptaRefsTool:
    """Audit et normalisation des références d'appariement dans comptes.xlsm"""

    def __init__(self, comptes_file=None, verbose=False, dry_run=False):
        self.dry_run = dry_run
        self.verbose = verbose
        self.comptes_file = Path(comptes_file) if comptes_file else EXCEL_FILE

        self.logger = Logger(
            script_name="tool_refs",
            verbose=verbose,
        )
        self.excel = ComptaExcel(
            comptes_file=self.comptes_file,
            verbose=verbose,
            logger=self.logger,
        )
        self.cr = ColResolver.from_openpyxl(self.excel.wb)

    # ====================================================================
    # Mode --audit
    # ====================================================================

    def audit(self, year_filter=None, ref_regex_filter=None, account_pair_filter=None):
        """Rapport détaillé des problèmes de références (7 sections)"""

        # Afficher filtres actifs
        filters = []
        if year_filter:
            filters.append(f"année={year_filter}")
        if ref_regex_filter:
            filters.append(f"ref_regex={ref_regex_filter}")
        if account_pair_filter:
            filters.append(f"comptes={account_pair_filter[0]} ↔ {account_pair_filter[1]}")

        if filters:
            print(f"🔍 Filtres actifs: {', '.join(filters)}")

        if not self.excel.open_workbook():
            return 1

        print(f"📖 Lecture de {self.comptes_file}...")
        refs = self.excel.load_all_references(
            year_filter=year_filter,
            ref_regex_filter=ref_regex_filter,
            account_pair_filter=account_pair_filter,
        )
        self.excel.close_workbook(save=False)

        print(f"✓ {len(refs)} références uniques chargées\n")

        self._print_audit_report(refs)
        return 0

    def _print_audit_report(self, refs):
        """Affiche le rapport d'audit complet (7 sections)"""

        print("=" * 80)
        print("AUDIT DES RÉFÉRENCES D'APPARIEMENT")
        print("=" * 80)
        print()

        # Séparer #Info des vraies opérations
        refs_real = {}
        refs_info = {}

        for ref_str, occurrences in refs.items():
            real_ops = [op for op in occurrences if '#Info' not in op[2] and '#info' not in op[2]]
            info_ops = [op for op in occurrences if '#Info' in op[2] or '#info' in op[2]]

            if real_ops:
                refs_real[ref_str] = real_ops
            if info_ops:
                refs_info[ref_str] = info_ops

        # 1. Statistiques globales
        print("=== 1. STATISTIQUES GLOBALES ===\n")

        total_refs = len(refs)
        total_real = len(refs_real)
        total_info = len(refs_info)

        perfect_pairs = 0
        reused = 0
        orphans = sum(1 for ops in refs_real.values() if len(ops) == 1)

        for ref, ops in refs_real.items():
            count = len(ops)
            if count == 2:
                perfect_pairs += 1
            elif count > 2:
                reused += 1

        print(f"Références totales:        {total_refs}")
        print(f"  - Opérations réelles:    {total_real}")
        print(f"  - Annotations #Info:     {total_info}")
        print()
        print(f"Références réelles:")
        print(f"  - Paires parfaites (2x): {perfect_pairs}")
        print(f"  - N-uplets (>2x):        {reused}")
        print(f"  - Orphelines (1x):       {orphans}")
        print()

        # 2. Répartition par pattern
        print("=== 2. RÉPARTITION PAR PATTERN ===\n")

        pattern_counts = defaultdict(int)
        for ref_str in refs_real.keys():
            pattern = classify_reference_pattern(ref_str)
            pattern_counts[pattern] += 1

        for pattern, count in sorted(pattern_counts.items(), key=lambda x: -x[1]):
            print(f"  {pattern:15s}: {count:4d} références")
        print()

        # 3. N-uplets (count > 2)
        print("=== 3. N-UPLETS (count > 2) ===\n")

        reused_refs = [(ref, ops) for ref, ops in refs_real.items() if len(ops) > 2]
        reused_refs.sort(key=lambda x: -len(x[1]))

        if reused_refs:
            print(f"Total: {len(reused_refs)} N-uplets\n")

            for ref_str, ops in reused_refs[:20]:
                pattern = classify_reference_pattern(ref_str)
                print(f"  Réf: {ref_str} ({pattern}) - {len(ops)} occurrences")

                for row, date, cat, amt, equiv, acc, devise in ops:
                    amt_str = f"{amt:+.2f}".replace('.', ',')
                    equiv_str = f"(€{equiv:+.2f})".replace('.', ',') if equiv is not None else ''
                    print(f"    L{row:5d} | {date:10s} | {amt_str:>10s} {equiv_str:12s} | {cat:25s} | {acc}")
                print()

            if len(reused_refs) > 20:
                print(f"  ... et {len(reused_refs) - 20} autres références réutilisées\n")
        else:
            print("  ✓ Aucune référence réutilisée\n")

        # 4. Références orphelines (count == 1)
        print("=== 4. RÉFÉRENCES ORPHELINES (count == 1) ===\n")

        orphan_refs = [(ref, ops) for ref, ops in refs_real.items() if len(ops) == 1]
        orphan_refs.sort(key=lambda x: x[0])

        if orphan_refs:
            print(f"Total: {len(orphan_refs)} références orphelines\n")

            for ref_str, ops in orphan_refs[:30]:
                pattern = classify_reference_pattern(ref_str)
                row, date, cat, amt, equiv, acc, devise = ops[0]
                amt_str = f"{amt:+.2f}".replace('.', ',')
                equiv_str = f"(€{equiv:+.2f})".replace('.', ',') if equiv is not None else ''
                print(f"  L{row:5d} | {date:10s} | {ref_str:10s} ({pattern:10s}) | {amt_str:>10s} {equiv_str:12s} | {cat:25s} | {acc}")

            if len(orphan_refs) > 30:
                print(f"\n  ... et {len(orphan_refs) - 30} autres références orphelines\n")
        else:
            print("  ✓ Aucune référence orpheline\n")

        # 5. Paires avec montants non-opposés
        print("=== 5. PAIRES AVEC MONTANTS NON-OPPOSÉS ===\n")

        bad_pairs = []
        for ref_str, ops in refs_real.items():
            if len(ops) == 2:
                row1, date1, cat1, amt1, equiv1, acc1, devise1 = ops[0]
                row2, date2, cat2, amt2, equiv2, acc2, devise2 = ops[1]

                if equiv1 is not None and equiv2 is not None:
                    if abs(equiv1 + equiv2) > 0.01:
                        bad_pairs.append((ref_str, ops, 'equiv'))
                else:
                    if abs(amt1 + amt2) > 0.01:
                        if equiv1 is None and equiv2 is None:
                            bad_pairs.append((ref_str, ops, 'amount'))

        if bad_pairs:
            print(f"Total: {len(bad_pairs)} paires avec montants non-opposés\n")

            for ref_str, ops, comp_type in bad_pairs[:20]:
                pattern = classify_reference_pattern(ref_str)
                comp_label = "Equiv EUR" if comp_type == 'equiv' else "Montant"
                print(f"  Réf: {ref_str} ({pattern}) - Comparaison: {comp_label}")

                for row, date, cat, amt, equiv, acc, devise in ops:
                    amt_str = f"{amt:+.2f}".replace('.', ',')
                    equiv_str = f"(€{equiv:+.2f})".replace('.', ',') if equiv is not None else ''
                    print(f"    L{row:5d} | {date:10s} | {amt_str:>10s} {equiv_str:12s} | {cat:25s} | {acc}")

                if comp_type == 'equiv':
                    total = sum(equiv for _, _, _, _, equiv, _, _ in ops if equiv is not None)
                    print(f"    → Somme Equiv: {total:+.2f} EUR (devrait être ≈ 0)")
                else:
                    total = sum(amt for _, _, _, amt, _, _, _ in ops)
                    print(f"    → Somme Montant: {total:+.2f} (devrait être ≈ 0)")
                print()

            if len(bad_pairs) > 20:
                print(f"  ... et {len(bad_pairs) - 20} autres paires problématiques\n")
        else:
            print("  ✓ Toutes les paires ont des montants opposés\n")

        # 6. Typos détectées
        print("=== 6. TYPOS DÉTECTÉES ===\n")

        typos = [(ref, ops) for ref, ops in refs_real.items() if classify_reference_pattern(ref) == 'orxx (typo)']

        if typos:
            print(f"Total: {len(typos)} typos détectées (0rXX au lieu de OrXX)\n")

            for ref_str, ops in typos:
                print(f"  Réf: {ref_str} → devrait être: {ref_str.replace('0r', 'Or')}")
                for row, date, cat, amt, equiv, acc, devise in ops:
                    amt_str = f"{amt:+.2f}".replace('.', ',')
                    equiv_str = f"(€{equiv:+.2f})".replace('.', ',') if equiv is not None else ''
                    print(f"    L{row:5d} | {date:10s} | {amt_str:>10s} {equiv_str:12s} | {cat:25s} | {acc}")
                print()
        else:
            print("  ✓ Aucune typo détectée\n")

        # 7. Variantes de casse
        print("=== 7. VARIANTES DE CASSE ===\n")

        ref_by_lower = defaultdict(list)
        for ref_str in refs_real.keys():
            ref_by_lower[ref_str.lower()].append(ref_str)

        case_variants = []
        for ref_lower, variants in ref_by_lower.items():
            if len(variants) > 1:
                total_ops = []
                for variant in variants:
                    total_ops.extend(refs_real[variant])
                case_variants.append((ref_lower, variants, total_ops))

        if case_variants:
            print(f"Total: {len(case_variants)} références avec variantes de casse\n")

            for ref_lower, variants, all_ops in sorted(case_variants)[:20]:
                print(f"  Réf (lowercase): {ref_lower} - {len(variants)} variantes:")

                for variant in sorted(variants):
                    ops = refs_real[variant]
                    print(f"    {variant}: {len(ops)} occurrence(s)")
                    for row, date, cat, amt, equiv, acc, devise in ops:
                        amt_str = f"{amt:+.2f}".replace('.', ',')
                        equiv_str = f"(€{equiv:+.2f})".replace('.', ',') if equiv is not None else ''
                        print(f"      L{row:5d} | {date:10s} | {amt_str:>10s} {equiv_str:12s} | {cat:25s} | {acc}")

                print(f"    → Total combiné: {len(all_ops)} occurrences")
                print()

            if len(case_variants) > 20:
                print(f"  ... et {len(case_variants) - 20} autres variantes de casse\n")
        else:
            print("  ✓ Aucune variante de casse détectée\n")

        # Résumé final
        print("=" * 80)
        print("RÉSUMÉ")
        print("=" * 80)
        print()
        print(f"✓ Paires parfaites:            {perfect_pairs}")
        print(f"⚠ Références réutilisées:      {reused}")
        print(f"⚠ Références orphelines:       {orphans}")
        print(f"⚠ Paires montants incorrects:  {len(bad_pairs)}")
        print(f"⚠ Typos (0rXX):                {len(typos)}")
        print(f"⚠ Variantes de casse:          {len(case_variants)}")
        print()

        if orphans + len(bad_pairs) + len(typos) + len(case_variants) == 0:
            print("✅ Aucun problème détecté!")
        else:
            print("❌ Problèmes détectés - Correction nécessaire")
            print()
            print("Correction recommandée:")
            print("  1. Lancer: ./tool_refs.py --fix --dry-run")
            print("  2. Lancer: ./tool_refs.py --fix-duplicates --dry-run")
        print()

    # ====================================================================
    # Mode --fix
    # ====================================================================

    def fix(self, auto_confirm=False):
        """Corrige les références : casse, typos, et cohérence classe/catégorie"""

        mode = "[SIMULATION]" if self.dry_run else "[APPLICATION]"
        print("=" * 80)
        print(f"CORRECTION DES RÉFÉRENCES {mode}")
        print("=" * 80)
        print()

        # 1. Charger les références actuelles
        print("📖 Analyse des références actuelles...")

        if not self.excel.open_workbook():
            return 1

        print(f"📖 Lecture de {self.comptes_file}...")
        refs = self.excel.load_all_references()
        print(f"✓ {len(refs)} références uniques chargées\n")

        all_existing_refs = set(refs.keys())

        # 2. Construire le mapping ancien → nouveau
        ref_mapping = {}
        corrections_case = []
        corrections_class = []

        for ref_str, occurrences in refs.items():
            new_ref = ref_str

            # A) Correction de casse et typos
            case_corrected = normalize_reference_case(ref_str)
            if case_corrected != ref_str:
                new_ref = case_corrected
                corrections_case.append((ref_str, case_corrected))

            # B) Correction de classe (basée sur catégorie/devise)
            expected_class = self._detect_expected_class(occurrences)
            if expected_class:
                match = re.match(r'^([a-zA-Z]+)(\d+)$', new_ref)
                if match:
                    current_class = match.group(1).lower()

                    if current_class != expected_class:
                        new_num = self._find_next_available_number(expected_class, all_existing_refs)
                        new_ref = f"{expected_class}{new_num}"
                        all_existing_refs.add(new_ref)
                        corrections_class.append((ref_str, new_ref, current_class, expected_class))

            if new_ref != ref_str:
                ref_mapping[ref_str] = new_ref

        if not ref_mapping:
            print("✓ Aucune correction nécessaire\n")
            self.excel.close_workbook(save=False)
            return 0

        # 3. Afficher les corrections
        print(f"✓ {len(ref_mapping)} références à corriger:\n")

        if corrections_case:
            case_only = [(old, new) for old, new in corrections_case
                         if old not in [c[0] for c in corrections_class]]
            if case_only:
                print(f"  Casse/typos ({len(case_only)}):")
                for old_ref, new_ref in sorted(case_only)[:10]:
                    print(f"    {old_ref:15s} → {new_ref}")
                if len(case_only) > 10:
                    print(f"    ... et {len(case_only) - 10} autres")
                print()

        if corrections_class:
            print(f"  Classe ({len(corrections_class)}):")
            for old_ref, new_ref, old_class, new_class in sorted(corrections_class):
                print(f"    {old_ref:15s} → {new_ref:15s} [{old_class} → {new_class}]")
            print()

        if self.dry_run:
            print("Mode simulation - relancez sans --dry-run pour appliquer.\n")
            self.excel.close_workbook(save=False)
            return 0

        # Confirmation (sauf si --yes)
        if not auto_confirm:
            response = input("Appliquer ces corrections? [o/N] ")
            if response.lower() not in ['o', 'oui', 'y', 'yes']:
                print("❌ Annulé")
                self.excel.close_workbook(save=False)
                return 1

        # 4. Backup Excel
        print("\n💾 Création backup...")
        backup_path = self.excel.create_backup(prefix="BACKUP_FIX")
        print(f"✓ Backup: {backup_path.name}\n")

        # 5. Appliquer les corrections
        print("✏️  Application des corrections...")

        corrections_count = 0
        for row in range(4, self.excel.ws_operations.max_row + 1):
            ref_cell = self.excel.ws_operations.cell(row, self.cr.col('OPréf'))
            ref_val = ref_cell.value

            if ref_val and str(ref_val) in ref_mapping:
                old_ref = str(ref_val)
                new_ref = ref_mapping[old_ref]
                ref_cell.value = new_ref
                corrections_count += 1

        print(f"✓ {corrections_count} cellules corrigées\n")

        # 6. Sauvegarder
        print("💾 Sauvegarde Excel...")
        self.excel.close_workbook(save=True)
        print(f"✓ Sauvegardé: {self.comptes_file}\n")

        print("✅ Corrections terminées avec succès!\n")
        return 0

    # ====================================================================
    # Mode --fix-duplicates
    # ====================================================================

    def fix_duplicates(self, year_filter=None, ref_regex_filter=None, account_pair_filter=None,
                       date_tolerance=0, max_rank=50, full=False, skip_balance_check=False):
        """Corrige les références réutilisées avec logique de pairing"""

        mode = "[SIMULATION]" if self.dry_run else "[APPLICATION]"
        print("=" * 80)
        print(f"{mode} CORRECTION DES RÉFÉRENCES RÉUTILISÉES")
        print("=" * 80)
        print()

        # 1. Charger les références avec filtres
        print("📖 Analyse des références actuelles...")

        if not self.excel.open_workbook():
            return 1

        # Afficher filtres actifs
        filters = []
        if year_filter:
            filters.append(f"année={year_filter}")
        if ref_regex_filter:
            filters.append(f"ref_regex={ref_regex_filter}")
        if account_pair_filter:
            filters.append(f"comptes={account_pair_filter[0]} ↔ {account_pair_filter[1]}")
        if filters:
            print(f"🔍 Filtres actifs: {', '.join(filters)}")

        print(f"📖 Lecture de {self.comptes_file}...")
        refs = self.excel.load_all_references(
            year_filter=year_filter,
            ref_regex_filter=ref_regex_filter,
            account_pair_filter=account_pair_filter,
        )
        print(f"✓ {len(refs)} références uniques chargées\n")

        # Filtrer les références réutilisées ou paires imparfaites
        refs_to_fix = {}
        skipped_perfect_pairs = []

        for ref_str, occurrences in refs.items():
            real_ops = [op for op in occurrences if '#Info' not in op[2] and '#info' not in op[2]]
            if not real_ops:
                continue

            if len(real_ops) == 2:
                pairs, unpaired = self._pair_operations_for_ref(real_ops, date_tolerance, max_rank, skip_balance_check)
                if len(pairs) == 1 and len(unpaired) == 0:
                    skipped_perfect_pairs.append(ref_str)
                    continue

            if len(real_ops) != 2:
                refs_to_fix[ref_str] = real_ops

        # 2. Trouver le prochain numéro disponible
        print("Recherche du prochain numéro disponible (compteur unique)...")

        max_num = 0
        for row in range(4, self.excel.ws_operations.max_row + 1):
            ref = self.excel.ws_operations.cell(row, self.cr.col('OPréf')).value
            if ref:
                ref_str = str(ref)
                match = re.match(r'^[a-zA-Z]+(\d+)$', ref_str)
                if match:
                    try:
                        num = int(match.group(1))
                        max_num = max(max_num, num)
                    except Exception:
                        pass

        # Mettre à jour le compteur F2 si nécessaire
        current_f2 = self.excel.ws_operations.cell(*PAIRING_COUNTER_CELL).value
        if current_f2 and isinstance(current_f2, int) and current_f2 < max_num + 1:
            self.excel.ws_operations.cell(*PAIRING_COUNTER_CELL).value = max_num + 1
            self.excel.wb.save(self.comptes_file)
            print(f"✓ Compteur F2 mis à jour: {current_f2} → {max_num + 1}")
            # Recalcul + miroir C1 si lancé depuis la GUI
            if os.environ.get('COMPTA_GUI'):
                from inc_uno import refresh_controles
                refresh_controles(self.comptes_file)

        next_num = max_num + 1
        print(f"✓ Prochain numéro disponible: {next_num}\n")

        if not refs_to_fix:
            print(f"✓ Aucune référence à corriger")
            if skipped_perfect_pairs:
                print(f"✓ {len(skipped_perfect_pairs)} paires déjà correctes (non modifiées)\n")
            self.excel.close_workbook(save=False)
            return 0

        print(f"✓ {len(refs_to_fix)} références à corriger")
        if skipped_perfect_pairs:
            print(f"✓ {len(skipped_perfect_pairs)} paires déjà correctes (non modifiées)\n")

        # 3. Analyser et générer corrections
        ref_mapping = {}  # {row_num: new_ref}
        all_pairs = []
        all_unpaired = []
        display_count = 0

        print("\nAnalyse et appariement:")
        print()

        for ref_str, operations in sorted(refs_to_fix.items()):
            pairs, unpaired = self._pair_operations_for_ref(operations, date_tolerance, max_rank, skip_balance_check)

            all_pairs.extend(pairs)
            all_unpaired.extend(unpaired)

            if full or display_count < 10:
                print(f"  Réf: {ref_str} - {len(operations)} occurrences")
                print(f"    → {len(pairs)} paires formées, {len(unpaired)} orphelins")

                for i, (op1, op2) in enumerate(pairs):
                    new_ref = f"v{next_num + len(ref_mapping)//2}"
                    row1, date1, cat1, amt1, equiv1, acc1 = op1[:6]
                    row2, date2, cat2, amt2, equiv2, acc2 = op2[:6]
                    rank_diff = row2 - row1 - 1

                    ref_mapping[row1] = new_ref
                    ref_mapping[row2] = new_ref

                    print(f"      Paire {i+1}: L{row1} ({date1}) - L{row2} ({date2}) (Δ{rank_diff}) → {new_ref}")
                    print(f"        {amt1:+10.2f} {acc1[:30]}")
                    print(f"        {amt2:+10.2f} {acc2[:30]}")

                if unpaired:
                    print(f"      ⚠ {len(unpaired)} orphelins:")
                    orphans_to_show = unpaired if full else unpaired[:3]
                    for op in orphans_to_show:
                        row, date, cat, amt, equiv, acc = op[:6]
                        print(f"        L{row}: {date} | {amt:+10.2f} | {acc[:30]}")
                    if not full and len(unpaired) > 3:
                        print(f"        ... et {len(unpaired) - 3} autres (utilisez --full pour tout afficher)")

                print()

            else:
                for op1, op2 in pairs:
                    new_ref = f"v{next_num + len(ref_mapping)//2}"
                    ref_mapping[op1[0]] = new_ref
                    ref_mapping[op2[0]] = new_ref

            display_count += 1

        if not full and len(refs_to_fix) > 10:
            print(f"  ... et {len(refs_to_fix) - 10} autres références\n")

        print(f"\nRésumé:")
        print(f"  Paires formées          : {len(all_pairs)}")
        print(f"  Opérations appariées    : {len(all_pairs) * 2}")
        print(f"  Opérations orphelines   : {len(all_unpaired)}")
        print(f"  Total changements       : {len(ref_mapping)}\n")

        if not ref_mapping:
            print("✓ Aucune correction nécessaire\n")
            self.excel.close_workbook(save=False)
            return 0

        # Confirmation si pas dry_run
        if not self.dry_run:
            response = input("Appliquer ces corrections? [o/N] ")
            if response.lower() not in ['o', 'oui', 'y', 'yes']:
                print("❌ Annulé")
                self.excel.close_workbook(save=False)
                return 1

        if not self.dry_run:
            # 4. Backup Excel
            print("\n💾 Création backup...")
            backup_path = self.excel.create_backup(prefix="BACKUP_DUPLICATES")
            print(f"✓ Backup: {backup_path.name}\n")

            # 5. Appliquer les corrections
            print("✏️  Application des corrections...")

            corrections_count = 0
            for row_num, new_ref in ref_mapping.items():
                self.excel.ws_operations.cell(row_num, self.cr.col('OPréf')).value = new_ref
                corrections_count += 1

            print(f"✓ {corrections_count} cellules corrigées\n")

            # 6. Sauvegarder
            print("💾 Sauvegarde Excel...")
            self.excel.close_workbook(save=True)
            print(f"✓ Sauvegardé: {self.comptes_file}\n")

            # 7. Nouvel audit
            print("=" * 80)
            print("NOUVEL AUDIT APRÈS CORRECTION")
            print("=" * 80)
            print()

            if self.excel.open_workbook():
                refs_new = self.excel.load_all_references(
                    year_filter=year_filter,
                    ref_regex_filter=ref_regex_filter,
                    account_pair_filter=account_pair_filter,
                )
                self.excel.close_workbook(save=False)
                print(f"✓ {len(refs_new)} références uniques chargées\n")
                self._print_audit_report(refs_new)
        else:
            print("Mode simulation - relancez sans --dry-run pour appliquer.\n")
            self.excel.close_workbook(save=False)

        return 0

    # ====================================================================
    # Helpers privés
    # ====================================================================

    def _detect_expected_class(self, occurrences):
        """Détecte la classe attendue selon les catégories et devises des opérations.

        Returns:
            str: classe attendue ('v', 'btc', 'or', 't', 'usd', etc.) ou None
        """
        secondary_categories = {'frais bancaires', 'ajustement', 'frais', 'cadeaux'}

        main_ops = []
        for op in occurrences:
            row, date, cat, amt, equiv, acc, devise = op
            if '#Info' in cat or '#info' in cat:
                continue
            cat_lower = cat.lower()
            if not any(sec in cat_lower for sec in secondary_categories):
                main_ops.append((cat_lower, amt, devise))

        if not main_ops:
            return None

        categories_str = ' '.join(cat for cat, amt, devise in main_ops)

        # 1. Titres
        if any(keyword in categories_str for keyword in ['titres', 'arbitrage', 'rachat']):
            return 't'

        # 2. Change → devise du côté crédit
        if 'change' in categories_str:
            for cat, amt, devise in main_ops:
                if 'change' in cat and amt > 0:
                    return normalize_devise(devise)
            for cat, amt, devise in main_ops:
                if 'change' in cat and devise and devise.upper() != 'EUR':
                    return normalize_devise(devise)
            return None

        # 3. Achat métaux → devise crédit + 'jo'
        if 'achat métaux' in categories_str or 'achat metaux' in categories_str:
            for cat, amt, devise in main_ops:
                if ('achat métaux' in cat or 'achat metaux' in cat) and amt > 0:
                    return normalize_devise(devise) + 'jo'
            for cat, amt, devise in main_ops:
                if ('achat métaux' in cat or 'achat metaux' in cat) and devise and devise.upper() != 'EUR':
                    return normalize_devise(devise) + 'jo'
            return None

        # 4. Virement
        if 'virement' in categories_str:
            return 'v'

        return None

    def _find_next_available_number(self, prefix, existing_refs):
        """Trouve le prochain numéro disponible pour un préfixe donné"""
        max_num = 0
        pattern = re.compile(f'^{re.escape(prefix)}(\\d+)$', re.IGNORECASE)

        for ref in existing_refs:
            match = pattern.match(ref)
            if match:
                num = int(match.group(1))
                max_num = max(max_num, num)

        return max_num + 1

    def _find_next_available_ref(self, base_ref, existing_refs):
        """Trouve la prochaine référence disponible"""
        match = re.match(r'^([A-Za-z]+)(\d+)$', base_ref)
        if not match:
            return base_ref

        prefix = match.group(1)
        max_num = 0
        pattern = re.compile(r'^' + re.escape(prefix) + r'(\d+)$', re.IGNORECASE)

        for ref in existing_refs:
            m = pattern.match(ref)
            if m:
                num = int(m.group(1))
                if num > max_num:
                    max_num = num

        return f"{prefix}{max_num + 1}"

    def _pair_operations_for_ref(self, operations, date_tolerance_days=0, max_rank_diff=50, skip_balance_check=False):
        """Groupe les opérations d'une même référence en paires.

        Returns:
            pairs: liste de paires d'opérations
            unpaired: liste d'opérations non appariées
        """
        ops = []
        for op in operations:
            row, date_str, cat, amt, equiv, acc = op[:6]
            try:
                if isinstance(date_str, str) and date_str:
                    parts = date_str.split('/')
                    if len(parts) == 3:
                        date_obj = datetime(int(parts[2]), int(parts[1]), int(parts[0]))
                    else:
                        date_obj = None
                else:
                    date_obj = None
            except Exception:
                date_obj = None

            ops.append({
                'row': row,
                'date': date_obj,
                'montant': amt,
                'compte': acc,
                'original': op,
            })

        ops.sort(key=lambda x: x['row'])

        pairs = []
        unpaired = []
        used = set()

        i = 0
        while i < len(ops):
            if i in used:
                i += 1
                continue

            paired = False
            for j in range(i + 1, len(ops)):
                if j in used:
                    continue

                date1 = ops[i]['date']
                date2 = ops[j]['date']

                if date1 and date2:
                    date_diff = abs((date2 - date1).days)
                    if date_diff > date_tolerance_days:
                        continue
                elif date1 != date2:
                    continue

                rank_diff = ops[j]['row'] - ops[i]['row'] - 1
                if rank_diff > max_rank_diff:
                    continue

                if not skip_balance_check:
                    montant1 = ops[i]['montant']
                    montant2 = ops[j]['montant']
                    somme = abs(montant1 + montant2)
                    if somme >= 0.01:
                        continue

                pairs.append((ops[i]['original'], ops[j]['original']))
                used.add(i)
                used.add(j)
                paired = True
                break

            if not paired:
                used.add(i)
                unpaired.append(ops[i]['original'])

            i += 1

        return pairs, unpaired

    def _group_operations_into_sets(self, operations):
        """Groupe des opérations en paires/N-uplets logiquement cohérents.

        Returns:
            list of sets, list of orphans
        """
        WINDOW_DAYS = 14

        TRANSACTION_KEYWORDS = {
            'achat': ['@Achat titres'],
            'vente': ['@Vente titres', 'Vente Or'],
            'change': ['@Change'],
            'achat_metaux': ['@Achat métaux'],
            'frais': ['Frais bancaires'],
            'arbitrage': ['@Arbitrage titres']
        }

        def parse_date_str(date_str):
            try:
                return datetime.strptime(date_str, '%d/%m/%Y')
            except Exception:
                return None

        def dates_within_window(date1, date2, days=WINDOW_DAYS):
            d1 = parse_date_str(date1)
            d2 = parse_date_str(date2)
            if d1 is None or d2 is None:
                return False
            return abs((d1 - d2).days) <= days

        def get_category_type(cat):
            cat_lower = cat.lower()
            for cat_type, keywords in TRANSACTION_KEYWORDS.items():
                for keyword in keywords:
                    if keyword.lower() in cat_lower:
                        return cat_type
            return 'autre'

        sets = []
        remaining = operations.copy()

        # PASSE 1 : TRANSACTIONS (par date + catégories cohérentes)
        for n in range(6, 1, -1):
            changed = True
            while changed and len(remaining) >= n:
                changed = False

                for indices in combinations(range(len(remaining)), n):
                    ops_group = [remaining[i] for i in indices]

                    dates = [op[1] for op in ops_group]
                    if not all(dates_within_window(dates[0], d) for d in dates):
                        continue

                    categories = [get_category_type(op[2]) for op in ops_group]
                    is_transaction = False

                    if categories.count('change') >= 2:
                        montants = [op[3] for op in ops_group if get_category_type(op[2]) == 'change']
                        if any(m < 0 for m in montants) and any(m > 0 for m in montants):
                            is_transaction = True
                    elif categories.count('achat_metaux') >= 2:
                        montants = [op[3] for op in ops_group if get_category_type(op[2]) == 'achat_metaux']
                        if any(m < 0 for m in montants) and any(m > 0 for m in montants):
                            is_transaction = True
                    elif categories.count('vente') >= 2:
                        is_transaction = True
                    elif categories.count('arbitrage') >= 2:
                        is_transaction = True
                    elif categories.count('achat') >= 2:
                        is_transaction = True

                    if is_transaction:
                        sets.append(tuple(ops_group))
                        for i in sorted(indices, reverse=True):
                            remaining.pop(i)
                        changed = True
                        break

        # PASSE 2 : VIREMENTS (par somme nulle)
        for n in range(3, 1, -1):
            changed = True
            while changed and len(remaining) >= n:
                changed = False

                for indices in combinations(range(len(remaining)), n):
                    ops_group = [remaining[i] for i in indices]

                    dates = [op[1] for op in ops_group]
                    if not all(dates_within_window(dates[0], d) for d in dates):
                        continue

                    amounts = [op[3] for op in ops_group]
                    equivs = [op[4] for op in ops_group]

                    if all(e is not None for e in equivs):
                        total = sum(equivs)
                    else:
                        total = sum(amounts)

                    if abs(total) < 0.01:
                        sets.append(tuple(ops_group))
                        for i in sorted(indices, reverse=True):
                            remaining.pop(i)
                        changed = True
                        break

        orphans = remaining
        return sets, orphans

    def _load_validated_groups(self):
        """Charge le dictionnaire des N-uplets validés"""
        if not VALIDATED_GROUPS_FILE.exists():
            return {}

        try:
            with open(VALIDATED_GROUPS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)

            validated = {}
            for group in data.get('groups', []):
                if group.get('validated', False):
                    validated[group['ref']] = group

            if validated:
                print(f"📋 {len(validated)} groupes validés chargés depuis {VALIDATED_GROUPS_FILE.name}\n")

            return validated
        except Exception as e:
            print(f"⚠️  Erreur lecture {VALIDATED_GROUPS_FILE.name}: {e}\n")
            return {}


# ============================================================================
# CLI
# ============================================================================

def main():
    """Point d'entrée principal"""

    parser = argparse.ArgumentParser(description="Audit et normalisation des références d'appariement")
    parser.add_argument('--audit', action='store_true',
                       help="Afficher rapport d'audit détaillé")
    parser.add_argument('--fix', action='store_true',
                       help="Corriger casse, typos et cohérence classe/catégorie")
    parser.add_argument('--fix-duplicates', action='store_true',
                       help="Corriger les références réutilisées avec logique de pairing")

    # Filtres
    parser.add_argument('--year', type=int,
                       help="Filtrer par année (ex: 2023)")
    parser.add_argument('--ref-regex', type=str,
                       help="Regex pour filtrer références (ex: ^v24, ^v2[0-9], ^v)")
    parser.add_argument('--accounts', type=str,
                       help="Paire de comptes séparés par virgule (ex: 'Compte chèque SG,Créance prêt familial')")

    # Paramètres de pairing (pour --fix-duplicates)
    parser.add_argument('--date-tolerance', type=int, default=0,
                       help="Tolérance en jours pour dates (défaut: 0 = même date)")
    parser.add_argument('--max-rank', type=int, default=50,
                       help="Écart de rang maximum (défaut: 50)")
    parser.add_argument('--dry-run', action='store_true',
                       help="Simulation sans modification")
    parser.add_argument('--yes', '-y', action='store_true',
                       help="Confirmer automatiquement sans prompt")
    parser.add_argument('--full', action='store_true',
                       help="Afficher tous les orphelins au lieu de limiter à 3")
    parser.add_argument('--skip-balance-check', action='store_true',
                       help="Ignorer la vérification montants opposés")
    parser.add_argument('-v', '--verbose', action='store_true',
                       help="Mode verbeux")

    args = parser.parse_args()

    if not EXCEL_FILE.exists():
        print(f"❌ Fichier Excel introuvable: {EXCEL_FILE}", file=sys.stderr)
        return 1

    # Parser filtres
    account_pair = None
    if args.accounts:
        parts = [p.strip() for p in args.accounts.split(',')]
        if len(parts) == 2:
            account_pair = (parts[0], parts[1])
        else:
            print("❌ --accounts doit contenir exactement 2 comptes séparés par virgule\n")
            return 1

    tool = ComptaRefsTool(dry_run=args.dry_run, verbose=args.verbose)

    if args.audit:
        return tool.audit(
            year_filter=args.year,
            ref_regex_filter=args.ref_regex,
            account_pair_filter=account_pair,
        )

    if args.fix:
        return tool.fix(auto_confirm=args.yes)

    if args.fix_duplicates:
        return tool.fix_duplicates(
            year_filter=args.year,
            ref_regex_filter=args.ref_regex,
            account_pair_filter=account_pair,
            date_tolerance=args.date_tolerance,
            max_rank=args.max_rank,
            full=args.full,
            skip_balance_check=args.skip_balance_check,
        )

    parser.print_help()
    return 0


if __name__ == '__main__':
    sys.exit(main())
