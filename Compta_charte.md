# Charte graphique des classeurs comptes

## Référence visuelle

La charte est **incarnée par le classeur de référence**
(`comptes_template.xlsm`, ou ton propre `comptes.xlsm` après initialisation).
Il en montre la palette complète, les bordures, les polices et le format des
nombres dans tous les contextes (tête, pied, devise étrangère, contrôle…).

Cette page **complète** le visuel par les règles non immédiatement lisibles
à l'œil : sémantique des éléments, partage utilisateur / outils,
comportements automatiques.

## Règle d'or — le jaune est à toi

`#FFFF00` (jaune vif) est ta couleur réservée :

- Pose-le librement pour annoter, signaler, attirer ton attention.
- Aucun outil ne pose ni n'écrase de cellule jaune. Drill, import,
  correction de format, sync : tout te le préserve.

Si tu vois du jaune dans le classeur, c'est qu'un utilisateur l'a mis.

## Couleur d'appoint — beige clair

`#EEEBDB` (beige clair) est une 2ᵉ couleur libre d'usage en zone data : tu
peux l'utiliser pour grouper visuellement des lignes ou marquer un
sous-bloc. Les outils ne l'écrasent pas en data.

Distinction avec le jaune : le beige clair est aussi la couleur que les
outils posent pour la 1ʳᵉ colonne (libellés), les sous-pieds de section et
la ligne TOTAL — donc moins discriminant que le jaune pour une annotation
ponctuelle.

## Sémantique des polices

Le visuel donne le style ; voici ce qu'il **veut dire** :

- **Texte bleu** (`#0432FF`) — cellule de saisie utilisateur.
- **Texte gras** — libellés, sous-headers, TOTAL : décor, libre.
- **Nombre gras** — la cellule est **contrôlée par formule**. Ne touche
  pas au gras des nombres à la main, c'est porteur de sens.

## Sémantique des couleurs spéciales

- **Fond gris** (clair ou foncé) sur une ligne → **devise étrangère**
  (USD, CHF, BTC, …). Repérage rapide.
- **Fond rouge clair** → cellule en **alarme** (contrôle ✗).
- **Fond jaune-orange** → **avertissement** (contrôle ⚠).

Rouge et jaune-orange sont posés par mise en forme conditionnelle : ils
s'allument et s'éteignent automatiquement selon la valeur de contrôle.

## Indicateurs ✓ ✗ ⚠

Sur la feuille **Contrôles** et dans la barre d'état de l'application :

- ✓ tout va bien
- ✗ alarme, à corriger
- ⚠ avertissement, à vérifier

Un clic sur la barre d'état affiche le détail des 6 contrôles principaux.

## Règle des montants négatifs

Tous les montants en devise (EUR ou autre) affichent **les négatifs en
rouge**, quelle que soit la devise. Cohérent dans tout le classeur.

## Outils dédiés

Le menu **Outils ▶ Formats** maintient la charte automatiquement :

| Action | Effet |
|---|---|
| Vérifier formats (numériques) | Diagnostic des formats de nombre |
| Vérifier formats (complet) | + diagnostic graphique (couleurs, bordures) |
| Corriger formats (numériques) | Applique les corrections de nombre. `.bak` auto. |
| Corriger formats (complet) | + applique la palette graphique. `.bak` auto. |

Les annotations jaune ne sont **jamais** touchées par ces outils.
