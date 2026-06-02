# example — notes

Construction complète du classeur exemple via GUI (devises, comptes, catégories, patrimoine, opérations). ~38 s en batch UNO.

Aucun warning spécifique.

## Spécificités

- 8 devises (EUR, XAU, BTC, USD, SGD, OrPr, SAT, XMR).
- Appariements (16 tuples) vérifiés strictement.
- `Plus_value` et `Avoirs` en warn_only : seuil 10 % absorbe la dérive des cours live.
- `Patrimoine TOTAL` et `Plus_value GRAND TOTAL` vérifiés en sus.
