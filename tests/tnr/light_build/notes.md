# light_build — notes

Scénario minimal mono-devise : template + 1 compte EUR + 1 poste + 1 catégorie. Isole les opérations CRUD Budget / POSTES / CAT du code multi-devises.

## Spécificités

- Pas de cotations non-EUR, pas de titre, pas d'opération.
- Comparaison stricte (pas de `warn_only`).
- Sert de point de départ canonique pour `light_reverse`.
