# apipe — notes

Chaîne complète sur un jeu de forme réelle, anonymisé : import des relevés de 11 sites (`cpt_update`), appariement (`cpt_pair`), comparaison au classeur attendu. ~26 s.

Vérification stricte : toutes les feuilles en comparaison de valeurs, 277 tuples d'appariement, 9 paires de transfert et aucune opération restée en attente.

## Warnings acceptables

- `cpt_update ⚠️ Contrôles!A1 = '⚠'` — état du classeur entre l'import et l'appariement ; l'attendu, lui, est à `✓`.
- `⚠️ Plus_value (variations)` sur les comptes Wise en devises — variations réelles du jeu, pas un écart.

## Spécificités

- `Budget!C2` figé au jour de la collecte (`fige_aujourdhui`) : Budget est comparé comme les autres feuilles.
- Les relevés reprennent leur date de collecte depuis `dates.json` (git ne conserve pas les dates de fichier).
- `dropbox/MANUEL/manuel.xlsx` est vide : la saisie manuelle est couverte par `build`.
