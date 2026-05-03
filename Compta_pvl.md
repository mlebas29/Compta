# Plus-value latente 

Ce document décrit le sens du tableau **Plus_value** : ce qu'on y mesure, les deux modèles de calcul utilisés, et le rapport à la fiscalité.

PVL = **plus-value latente** : ce qui s'est apprécié (ou déprécié) sur le capital, *non encore réalisé*. C'est un outil de **pilotage de performance par classe d'actif**, pas un document fiscal — voir [§Cessions](#cessions).


## Colonnes du tableau

Sémantique des colonnes principales :

| Colonne | Lettre | Sens |
| --- | --- | --- |
| Section | A | classe d'actif : *portefeuilles* / *métaux* / *crypto* / *devises* |
| Compte | B | nom du compte ou du titre |
| Devise | C | devise |
| **PVL** | E | **plus-value latente** |
| Date initiale | G | date d'ancrage |
| Montant initial | H | capital à l'ancrage |
| SIGMA | I | cumul des opérations saisies |
| Date SOLDE | J | date du solde courant |
| SOLDE | K | solde courant |


## Formule pivot

```
PVL = SOLDE − (Montant initial + SIGMA)
```

Lecture : *effet de cours pur sur les positions résiduelles entre l'ancrage et aujourd'hui*.

- Le **Montant initial** ancre la valeur à un instant donné (date initiale).
- Le **SIGMA** cumule l'ensemble des opérations saisies depuis l'ancrage 
- Le **SOLDE** est la valeur courante.
- La PVL est donc la part **non expliquée par les opérations**, attribuable à la valorisation des cours sur ce qui est détenu.


## Convention : SIGMA = cumul brut des opérations saisies

Le SIGMA cumule **toutes les opérations saisies depuis l'ancrage**, quelle que soit leur catégorie — paiements (carte, espèces), prélèvements, apports, retraits, changes, coupons, intérêts, ajustements. Seuls sont exclus les **marqueurs `#*`** (`#Solde`, `#Info`, …) qui ne sont pas des opérations réelles.

C'est une convention car on aurait pu vouloir filtrer : ne retenir que les opérations *externes* (apports, retraits, achats, ventes — qui modifient le périmètre du compte) et laisser les opérations *internes* (coupons, dividendes, intérêts — produites par les positions détenues) compter comme rendement attribué dans le SOLDE.

Sur un compte où les opérations sont **fongibles** (coupon, frais, paiement, virement passent par le même solde), cette distinction n'est pas opérationnelle : quand on retire 50 EUR au resto avec une carte adossée à un stock fongible, on ne peut pas dire si on consomme « le coupon de mai » ou « le montant initial ». Le SIGMA tranche en traitant toutes les opérations uniformément.

**Ce que mesure la PVL.** Avec cette convention, la PVL n'est pas une « performance globale du compte » (qui supposerait l'isolation des opérations internes), mais l'**effet de cours pur sur les positions résiduelles**. Un paiement carte, un prélèvement, un coupon ne font pas bouger la PVL — leur effet sur le SOLDE est exactement compensé par leur cumul dans SIGMA. Seul le **mouvement des cours sur ce qui reste détenu** la fait bouger.

**Cas où la séparation préexiste.** Pour les portefeuilles équipés d'un sous-compte cash dédié (Portefeuille BB Titres, DEGIRO, eToro), les dividendes peuvent être versés sur ce sous-compte cash, hors du périmètre PVL du titre. Lorsque c'est le cas (cela dépend de la politique de la banque), il s'agit alors d'une plus-value **réalisée**, et non latente, qui tombe dans une catégorie ad-hoc (Intérêts ou autre). Sur la ligne d'un titre individuel, le SIGMA brut = exactement les opérations externes au titre (achats/ventes), et la PVL mesure bien la valorisation pure du titre. La fongibilité ne pose alors pas de problème, parce que la séparation est faite en amont par la structure du compte.


## Deux modèles selon la section

Le tableau utilise **deux modèles distincts** de calcul, selon la nature de la classe d'actif :

|  | **Modèle DEV** | Modèle EUR |
| --- | --- | --- |
| Classe actif | portefeuilles | métaux / crypto / devises |
| Devise de calcul | devise du compte (USD, EUR, …) | EUR |
| Montant initial | **en devise** | equiv EUR au **cours d'époque** |
| SIGMA | opérations saisies en **devise** | opérations saisies en equiv EUR **cours d'époque** |
| SOLDE | solde courant en **devise** | solde courant en EUR **cours du jour** |
| Conversion EUR | uniquement au TOTAL section (× **cours du jour**) | déjà faite ligne par ligne |
| PVL mesurée | **performance DEV** dans la devise du compte | **performance EUR** (cost basis EUR consolidé) |

**Performance DEV** (portefeuilles) :

> *« Mon portefeuille eToro USD a fait +X % en USD, peu importe ce que le change EUR/USD a fait. »*

Le rendement de la classe d'actif **dans sa propre unité**.

**Performance EUR** (métaux / crypto / devises) :

> *« Mon stock d'or m'a coûté Y EUR ; il vaut Z EUR aujourd'hui. PVL = Z − Y. »*

Effet de cours en EUR sur la quantité détenue. Pour un actif coté en devise (or coté en USD, BTC en USD), la PVL combine implicitement l'évolution du cours local et l'effet de change — les deux sont consolidés dans le cours EUR.


### Pourquoi ce choix : trois critères

Trois critères convergents guident l'attribution d'une section à l'un ou l'autre modèle. Ils sont présentés ici par ordre d'importance.

**1. Dépensabilité ou encore monnaie d'échange — critère prédominant, lien fiscal.** L'actif peut-il directement payer un bien ou un service, sans étape de cession explicite ?

- *Non* (portefeuille thésaurisé) → modèle DEV. Pour consommer il faut d'abord vendre — la cession est un événement marqué et ponctuel, séparé du quotidien.
- *Oui* (métal via carte, crypto, devise étrangère) → modèle EUR. Chaque paiement est une **cession partielle** au sens fiscal, fait générateur. Le cost basis EUR doit donc être disponible **ligne par ligne, à tout moment** — c'est exactement ce que pose le Montant initial en modèle EUR.

**2. Nature de la performance recherchée.** Pour un portefeuille activement géré dans sa devise (eToro USD, PEA EUR), on cherche à isoler la **qualité de gestion** du bruit de change ; l'effet EUR/USD est un facteur exogène qu'on neutralise → modèle DEV. Pour un stock figé (lingot d'or, BTC en wallet), il n'y a pas de « gestion » à mesurer, juste une valorisation patrimoniale → modèle EUR.

**3. Monnaie de référence pertinente.** Un portefeuille USD se lit en USD. Une devise étrangère se lit en EUR — sinon la performance native serait `0` par construction. Les métaux et crypto se lisent en EUR parce que l'effet de cours *est* la performance.

**Cas Veracash.** Compte de paiement Mastercard adossé à des pièces de monnaie en or. Naturellement classé *métaux*. Le critère « performance recherchée » seul n'est pas tranchant (il y a des opérations diverses : achats/ventes de pièces, frais, paiements carte). C'est la **dépensabilité** (carte Veracash) qui justifie pleinement le modèle EUR.

**Cas Wise USD.** Devise active avec carte de paiement, intérêts, frais. Les critères « performance recherchée » et « monnaie de référence » oscillent (ressemble à un portefeuille USD avec opérations multiples). La dépensabilité tranche net : carte → modèle EUR.

**Règle pratique :** dès lors qu'un actif est **dépensable**, modèle EUR — peu importe que sa structure interne ressemble à un portefeuille.


## Re-ancrage

Le Montant initial et la date initiale suivent le **dernier `#Solde` retenu** dans les opérations du compte. Conséquence : la PVL mesure l'appréciation **depuis ce dernier ancrage**, pas nécessairement depuis l'achat originel.

- Si le compte n'a jamais été ré-ancré, le Montant initial = capital d'acquisition d'origine.
- Si on a ré-ancré (par exemple pour reposer un point de référence après une période trop longue ou une cession partielle), le Montant initial est postérieur à l'achat — la PVL ne mesure plus la performance « depuis le début ».

Pour la fiscalité (cf. [§Cessions](#cessions)), le **cost basis fiscal** est par définition la valeur d'acquisition d'origine ; il coïncide avec le Montant initial *seulement si* on n'a pas ré-ancré. Sinon, il faut le remonter ailleurs (historique des achats).


## Cessions

**La PVL n'est pas une grandeur fiscale.** Le tableau Plus_value est un outil de pilotage interne ; il n'est **pas** destiné à être présenté à l'administration.

Une plus-value devient **imposable** à la **cession** — c'est-à-dire à la sortie de la classe d'actif vers EUR ou vers consommation. Tant que le capital reste investi (titre détenu, lingot stocké, BTC en wallet), il n'y a pas de cession. Pour les actifs dépensables, **chaque paiement est une cession partielle**.

### Régimes selon l'actif

En France, à la cession (à vérifier au moment de la déclaration) :

- **Titres financiers** : flat tax 30 % (PFU) ou option barème de l'IR.
- **Métaux précieux** : taxe forfaitaire sur le prix de cession (option) ou régime des plus-values avec abattements pour durée de détention.
- **Crypto-actifs** : flat tax 30 % sur la plus-value imposable, calcul global pondéré sur l'ensemble du portefeuille crypto.
- **Devises étrangères** : plus-value rare en pratique pour un particulier ; à vérifier selon le contexte.

### Calcul de la plus-value de cession

Schéma général :

```
PV imposable = (montant cédé en EUR) − (coût d'acquisition en EUR)
```

Pour les actifs en **modèle EUR** *non ré-ancrés*, le Montant initial fournit un equiv EUR au cours d'époque — utilisable comme cost basis pour la quantité détenue à la Date initiale. C'est un **snapshot** à cette date, pas le cumul historique des achats : si des achats ou cessions partielles ont eu lieu depuis, le cost basis du lot cédé doit être reconstitué autrement (historique des opérations). Si le compte a été ré-ancré, le Montant initial n'est plus le cost basis d'origine — voir [§Re-ancrage](#re-ancrage).

Pour les actifs en **modèle DEV** (portefeuilles), le Montant initial est en devise du compte ; il faut une conversion EUR au cours d'époque de l'achat pour obtenir le cost basis EUR.

### En pratique

Une déclaration fiscale de cession ne se fait **pas** par lecture directe du tableau Plus_value. Elle nécessite un travail dédié : identification des lots cédés, prix d'acquisition pondéré (FIFO, CMP, … selon régime), application des abattements éventuels.

Le tableau Plus_value sert de **point de départ** (notamment pour les métaux et crypto où le Montant initial est déjà en EUR cours d'époque), pas de document fiscal final.
