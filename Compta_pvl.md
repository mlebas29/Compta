# Plus-value latente — doctrine

Ce document décrit le sens du tableau **Plus_value** : ce qu'on y mesure, les
deux modèles de calcul utilisés, et le rapport à la fiscalité. 

PVL = **plus-value latente** : ce qui s'est apprécié (ou déprécié) sur le
capital, *non encore réalisé*. C'est un outil de **pilotage de performance par
classe d'actif**, pas un document fiscal — voir [§Cessions](#cessions-fiscalité).


## Colonnes du tableau

Sémantique des colonnes principales :

| Colonne | Sens |
| --- | --- |
| Section | classe d'actif : *portefeuilles* / *métaux* / *crypto* / *devises* |
| Compte | nom du compte ou du titre |
| Devise | devise de la ligne |
| PVL | plus-value latente : `K − (H + I)` |
| % | PVL en % du capital initial : `E / H` |
| Date d'ancrage | date du dernier `#Solde` retenu |
| Capital initial (`H`) | capital à la date d'ancrage |
| Sigma (`I`) | cumul des **flux externes** depuis l'ancrage |
| Date solde | date du solde courant |
| Solde (`K`) | solde courant |


## Formule pivot

```
PVL = K − (H + I)
```

Lecture : *appréciation latente du capital entre l'ancrage et aujourd'hui*.

- `H` ancre le capital à un instant donné (date d'ancrage).
- `I` cumule les flux externes **depuis l'ancrage** — pour les neutraliser du
  calcul de PVL : sinon une entrée d'argent serait comptée comme une
  appréciation.
- `K` est le solde courant.
- `K − H − I` est donc l'écart **non expliqué par les flux externes** —
  attribuable à la valorisation pure (variation de cours, intérêts internes,
  …).


## Deux modèles selon la section

Le tableau utilise **deux modèles distincts** de calcul, selon la nature de
la classe d'actif :

| Aspect | **Modèle native** (portefeuilles) | **Modèle EUR** (métaux / crypto / devises) |
| --- | --- | --- |
| Devise de calcul | devise du compte (USD, EUR, …) | EUR |
| `H` | montant initial **en devise** | equiv EUR au **cours d'époque** |
| `I` | flux externes en devise | flux externes en equiv EUR cours d'époque |
| `K` | solde courant en devise | solde courant en EUR cours du jour |
| Conversion EUR | uniquement au TOTAL section (× cours du jour) | déjà faite ligne par ligne |
| PVL mesurée | **performance native** dans la devise du compte | **performance EUR** (cost basis EUR consolidé) |

**Performance native** (portefeuilles) :

> *« Mon portefeuille eToro USD a fait +X % en USD, peu importe ce que le
> change EUR/USD a fait. »*

Le rendement de la classe d'actif **dans sa propre unité**. Pertinent pour
des portefeuilles boursiers gérés et lus dans leur devise native.

**Performance EUR** (métaux / crypto / devises) :

> *« Mon stock d'or m'a coûté Y EUR ; il vaut Z EUR aujourd'hui. PVL = Z − Y. »*

Le rendement consolidé en monnaie de référence. La PVL inclut autant
l'appréciation locale que l'effet de change. Pertinent pour des stocks figés
(achat unique en EUR) et le suivi patrimonial.

**Frontière floue** : un compte de devise active (Wise USD avec dividendes,
intérêts, frais en USD) est dans la section *devises* (modèle EUR) bien que
sa nature ressemble à un portefeuille (flux multiples internes). C'est un
choix de catégorisation à arbitrer si la précision devient un sujet.


## Convention « flux interne = masse fluctuante »

Le sigma `I` cumule **uniquement les flux qui sortent de la classe d'actif**.
Tout flux qui **reste dans le compte** rejoint la masse fluctuante et
contribue à la PVL via son impact sur `K` — pas via `I`.

| Type d'opération | Reste sur le compte ? | Dans `I` ? |
| --- | --- | --- |
| Coupon, intérêt, dividende crédité | oui (sauf virement explicite) | non |
| Frais bancaires prélevés | sortie vers la banque (perte sèche) | non |
| Pertes & profits, ajustements | flux interne | non |
| Apport / retrait via `@Virement` | sortie vers autre poche utilisateur | **oui** |
| Change EUR ↔ devise (`@Change`) | flux entre poches utilisateur | **oui** |

Conséquence de lecture : un coupon reçu sur un compte et resté sur ce compte
gonfle `K`, n'est pas dans `I`, et apparaît donc dans la PVL —
**légitimement**, puisque tant qu'il n'est pas viré ailleurs, il fait partie
du capital qui fluctue avec le compte.


## Cessions (fiscalité)

**La PVL n'est pas une grandeur fiscale.** Le tableau Plus_value est un
outil de pilotage interne ; il n'est **pas** destiné à être présenté à
l'administration.

Une plus-value devient **imposable** uniquement à la **cession** — c'est-à-
dire à la sortie de la classe d'actif vers EUR (ou consommation). Tant que
le capital reste investi (titre détenu, lingot stocké, BTC en wallet), il
n'y a pas de cession et donc pas d'imposition, quelle que soit la PVL
affichée.

### Régimes selon l'actif

En France, à la cession (à vérifier au moment de la déclaration) :

- **Titres financiers** : flat tax 30 % (PFU) ou option barème de l'IR.
- **Métaux précieux** : taxe forfaitaire sur le prix de cession (option) ou
  régime des plus-values avec abattements pour durée de détention.
- **Crypto-actifs** : flat tax 30 % sur la plus-value imposable, calcul
  global pondéré sur l'ensemble du portefeuille crypto.
- **Devises étrangères** : plus-value rare en pratique pour un particulier ;
  à vérifier selon le contexte.

### Calcul de la plus-value de cession

Schéma général :

```
PV imposable = (montant cédé en EUR) − (coût d'acquisition en EUR)
```

Pour les actifs en **modèle EUR** (métaux, crypto, devises figées), le coût
d'acquisition est précisément ce que pose `H` : equiv EUR au cours d'époque.
Il est directement lisible dans le tableau Plus_value à la date de cession.

Pour les actifs en **modèle native** (portefeuilles), `H` est en devise du
compte — il faut une conversion EUR au cours d'époque pour obtenir le cost
basis EUR.

### En pratique

Une déclaration fiscale de cession ne se fait **pas** par lecture directe du
tableau Plus_value. Elle nécessite un travail dédié : identification des
lots cédés, prix d'acquisition pondéré (FIFO, CMP, … selon régime),
application des abattements éventuels.

Le tableau Plus_value sert de **point de départ** (notamment pour les métaux
et crypto où `H` est déjà en EUR cours d'époque), pas de document fiscal
final.
