# Compta — Outils de maintenance

Le projet inclut des outils en ligne de commande pour diagnostiquer,
vérifier et corriger le classeur `comptes.xlsm`. Ils sont tous optionnels
et complémentaires à l'interface graphique.

---

### tool_controles.py — Diagnostic du classeur

Lit la cellule `Contrôles!A1` (qui résume l'état du classeur) et affiche un
diagnostic humain : comptes déséquilibrés, catégories manquantes, warnings.
C'est le premier réflexe après un import ou une modification manuelle.

```
./tool_controles.py        # diagnostic standard
./tool_controles.py -v     # détails par erreur
```

### tool_compare_xlsx.py — Comparer deux versions du classeur

Compare deux fichiers Excel feuille par feuille (Opérations, Plus_value,
Avoirs). Utile pour vérifier ce qui a changé entre deux runs du pipeline,
ou entre le classeur actuel et une archive précédente.

```
./tool_compare_xlsx.py fichier1.xlsx fichier2.xlsx
./tool_compare_xlsx.py --prev          # compare avec l'archive N-1
./tool_compare_xlsx.py --re "LOYER"    # filtre par regex
```

### tool_check_integrity.py — Vérification des formules

Parcourt le classeur et vérifie que les formules (sommes, références entre
feuilles, named ranges) sont cohérentes. Détecte les formules cassées,
les références `#REF!`, les incohérences de totaux. Option `--fix` pour
corriger automatiquement.

```
python3 tool_check_integrity.py comptes.xlsm
python3 tool_check_integrity.py --fix comptes.xlsm
```

### tool_categories_audit.py — Audit des catégorisations

Compare les règles de catégorisation (`config_category_mappings.json`) avec
ce qui est réellement dans le classeur. Permet de repérer les opérations non
catégorisées ou les patterns obsolètes.

```
./tool_categories_audit.py             # audit complet
./tool_categories_audit.py --summary   # résumé uniquement
```

### tool_refs.py — Audit des références d'appariement

Les opérations importées sont appariées (rapprochées) via des références.
Cet outil audite et normalise ces références : détecte les doublons, corrige
la casse et la classification.

```
./tool_refs.py --audit              # rapport des problèmes
./tool_refs.py --fix --dry-run      # prévisualise les corrections
./tool_refs.py --fix                # applique
```

### tool_audit_formats.py — Audit charte graphique

Vérifie en lecture seule la conformité du classeur à la charte graphique
(palette de fonds, grille beige, bordures de pied). Ne modifie rien. Mode
synthèse par pattern par défaut, `--verbose` pour détailler chaque écart.

```
python3 tool_audit_formats.py comptes.xlsm
python3 tool_audit_formats.py comptes.xlsm --verbose
```

### tool_fix_formats.py — Correction des formats de cellules

Remet en ordre les formats d'affichage dans le classeur : montants au format
français (virgule décimale, espace milliers), dates en DD/MM/YY, devises
étrangères avec fond gris. Dry-run par défaut.

L'option `--charter` étend la correction à la charte graphique (palette
beige, quadrillage, traits de pied) et au gras des cellules contrôlées.

```
python3 tool_fix_formats.py comptes.xlsm                     # prévisualise (formats numériques)
python3 tool_fix_formats.py comptes.xlsm --apply             # applique
python3 tool_fix_formats.py comptes.xlsm --charter --apply   # + charte graphique
```

### tool_migrate_schema_v2.py — Mise à niveau du classeur

Migre un classeur d'une version structurelle antérieure (v3.4 et plus
récents) vers la version courante : drill devise, ancres ⚓, charte v4.
Voir `Compta_upgrade.md` §v4.0.0 pour la procédure complète et les
versions sources couvertes.

```
python3 tool_migrate_schema_v2.py comptes.xlsm
```

### tool_purge.py — Purge de l'historique

Supprime les opérations anciennes (au-delà d'un an) pour réduire la taille
du classeur, en préservant les comptes suivis en valorisation (assurances vie,
portefeuilles, métaux). Crée un backup avant modification.

```
./tool_purge.py --date 2024-01-01   # purge avant cette date
```

### tool_cleanup.py — Nettoyage système

Nettoie les processus Python orphelins (LibreOffice, UNO) et les fichiers
temporaires qui peuvent rester après un crash du pipeline.

```
./tool_cleanup.py                   # nettoyage complet
./tool_cleanup.py --processes       # processus uniquement
```

