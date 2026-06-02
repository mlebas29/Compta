# light_reverse — notes

Teardown minimal de `light_build` : suppression du compte EUR, du poste et de la catégorie. Compare au template mono-devise.

## Spécificités

- Pas de devise à supprimer (mono-EUR).
- Pas d'artefact bornes OP* (pas d'opération à purger, contrairement à `reverse`).
- Comparaison stricte.
