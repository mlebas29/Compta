# reverse — notes

Teardown complet : `build/expected.xlsm` → suppression de tout (comptes, catégories, postes, devises, patrimoine) jusqu'à l'équivalent du template.

## Restriction connue et acceptée

**Bornes OP* raccourcies** — `purge_account` supprime ~16 lignes d'opérations, UNO réduit automatiquement les named ranges `OPdate`/`OPmontant`/... de `$A$4:$A$10000` à `$A$4:$A$9984`. Tolérance intégrée dans `compare_named_ranges` (affiché ℹ info). L'expected contient les bornes réduites.
