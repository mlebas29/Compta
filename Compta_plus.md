# Compta_plus - Complément de Compta.md

Ce document complète **Compta.md** (guide principal). Il couvre 

- la structuration Excel **comptes.xlsm**
- les commandes avancées, le dépannage et les procédures spéciales
- la liste des fichiers collectés par site

Voir aussi [`Compta_tools.md`](Compta_tools.md) pour les outils de maintenance du classeur.

## Structuration Excel

### Opérations
Les opérations financières sont enregistrées dans la feuille Opération qui comporte un seul tableau.

Le tableau a des lignes descriptives d'en tête (un en-tête par colonne)

Chaque opération de débit ou crédit génère une ligne supplémentaire en bas de tableau. 

### Comptes
Un Compte est défini par un nom et une devise.
La liste des comptes est dans la feuille Avoirs, colonnes A (noms) et E (devise)

La liste des comptes actifs est dans la feuille Contrôles, colonne A

- Les portefeuilles ont des comptes distincts pour les Titres et la Réserve (ex: Portefeuille BB Titres, Portefeuille BB Réserve)
- Certains comptes génèrent une plus value qui est l'écart entre le solde relevé et le solde calculé à partir des opérations de crédit et débit.

### Catégories
Les catégories sont listées feuille Budget colonne L et attribuées en feuille opérations colonne G

Toute opération est attachée à une catégorie, par exemple "Marché" pour une dépense alimentaire

Les méta-catégories # ne correspondent pas à des opérations effectives, il s'agit de :

- #Solde : indicateur de solde de compte relevé; le montant est utilisé pour être comparé au solde calculé 
- #Info  : information, le montant est exclu de tout calcul
- #Balance : marqueur d'équilibre de tous les comptes (pas de transfert en cours) pour l'ensemble des lignes de rang inférieurs.

### Eq. EUR
Cette colonne du tableau Opérations indique l'équivalence en Euro d'une transaction (débit ou crédit) impliquant une autre devise.

Le champ est renseigné automatiquement à l'import pour toute opération en devise non-EUR (sauf virements). Le taux de change est obtenu via l'API ECB (Banque Centrale Européenne).

Cette colonne sert à :
- Calculer les plus-values quand des devises non-EUR sont impliquées
- Contrôler la cohérence : la somme des montants de la colonne doit être nulle

### Réf.
Le champ Réf. du tableau Opérations est un identifiant, par ex V32, qui sert à relier plusieurs opérations des catégories Virement, Change ou Titres (Achat, Vente ...)

- Dans le cas du virement, il y a juste la paire débit/crédit Vxxx
- Dans le cas de change il y a la paire débit/crédit plus les frais s'ils sont comptabilisés séparemment. Le préfixe est celui de la devise créditée en minuscule, par exemple : usd465
- Dans le cas des titres, il y a autant de références txxx que nécessaire, notamment dans les cas d'arbitrage ou de rachat de portefeuilles comportant plusieurs titres. 

### Contrôles
La feuille Contrôles porte deux tableaux et une cellule de statut global A1 (`.` = OK, `COMPTES`, `CATÉGORIES` ou `INCONNUS` = erreur bloquante).

- **Tableau 1** : pour chaque compte et devise, compare le solde relevé (#Solde le plus récent) au solde calculé (somme des opérations). L'écart est en colonne K, le flag bloquant en L.
- **Tableau 2** : autres contrôles par devise — catégories invalides, comptes inconnus, appariements incomplets, balances.

### Cotations
La feuille Cotations contient les cours de change et de valorisation, mis à jour par `cpt_fetch_quotes.py`.

Colonnes : Label (A), Type (B), Source principale (C), Source fallback (D), Code devise/asset (E), Cours en EUR (F), Date (G), Cours de l'Euro (H).

- Type : `fiat`, `crypto`, `metal` ou `immobilier`
- Sources API : frankfurter (fiat), coingecko (crypto), yahoo (metal), kraken (fallback crypto)
- Les cours alimentent les noms définis (`cours_USD`, `cours_SAT`…) utilisés dans les formules d'Avoirs colonne L

### Plus_value
La feuille Plus_value suit la valorisation de tous les comptes en devise non-EUR : portefeuilles titres, crypto, métaux, devises. Chaque ligne porte un compte (A), un libellé de position (B), et le montant valorisé (J) à une date (I).

Les lignes préfixées `*` sont modifiables par le programme. Le nom défini `Retenu` filtre les positions actives. Les formules d'Avoirs (colonnes J-K) agrègent les données de cette feuille pour ces comptes.

### Liste des tableaux
Tableau | Feuille
Avoirs : Avoirs
Opérations : Opérations
Budget : Budget
Catégories : Budget
Contrôles 1 : Contrôles
Contrôles 2 : Contrôles
Cotations : Cotations

## Commandes avancées

### Ciblage

```bash
cpt --sites SG,PEE         # Sites spécifiques uniquement
cpt --fetch-only           # Collecte seule (sans import)
cpt --update-only          # Import seul (sans collecte)
```

### Vérification

```bash
cpt --status               # État du système (erreurs, fichiers en attente)
```

### Comparaison avec archive précédente

Après chaque import avec des opérations ajoutées, `cpt_update.py` lance automatiquement une comparaison avec l'archive précédente. Voir [`Compta_tools.md`](Compta_tools.md) pour l'usage standalone de `tool_compare_xlsx.py`.

### Annulation

```bash
cpt --fallback             # Annuler dernier fetch + import
```

Restaure le backup Excel précédent et remet les fichiers collectés dans dropbox/. Utilisable plusieurs fois pour remonter dans l'historique.

### Réinitialisation

```bash
cpt --reset                # Purge archives/dropbox/logs
```

## Dépannage

Signification des erreurs : voir **Compta.md** (Annexe A - Contrôles Excel).
Les outils de diagnostic sont décrits dans [`Compta_tools.md`](Compta_tools.md).

### Erreur COMPTES

```bash
cpt --fallback             # Annuler et recommencer
```

### Collecte échouée pour un site

```bash
cpt --status               # Vérifier fichiers dans dropbox/
cpt --sites SG             # Relancer un site spécifique
```

### Fichier Excel verrouillé

```bash
killall -9 soffice.bin     # Fermer LibreOffice
rm -f ~/Compta/.~lock.*    # Supprimer verrous
```

## Mode debug

Dans `config.ini` :
```ini
[general]
DEBUG = true
```

Les fichiers debug (screenshots, HTML) sont dans `logs/debug/`.

## Environnement

```bash
python3 cpt_gui.py         # Lancement standard
```
## Fichiers collectés par site

Récapitulatif des fichiers générés par la collecte automatique ou manuelle. Le "→" indique où trouver le solde quand il n'est pas dans le même fichier.

| Site | Fichier | Contenu | Solde(s) extrait(s) |
|------|---------|---------|---------------------|
| **DEGIRO** | `Account.csv` | Opérations | → Portfolio.csv |
| | `Portfolio.csv` | Positions + Soldes | Réserve (CASH), Titres (somme) |
| **BOURSOBANK** | `export_compte_principal.csv` | Opérations | → PDF |
| | `export_livret_bourso.csv` | Opérations | → PDF |
| | `export-operations-*.csv` | Opérations titres | → PDF |
| | `positions.csv` | Positions | Titres (somme) |
| | `Portefeuille - BoursoBank.pdf` | Solde Espèces | Réserve |
| | `Mes Comptes - BoursoBank.pdf` | Soldes | Chèque, Livret |
| **SOCGEN** | `Mes comptes en ligne _ SG.pdf` | Synthèse | Tous les soldes |
| | `Export_XXXXXXXXX_*.csv` | Opérations + Solde | Compte courant, Livrets, LDD, CSL |
| | `SG_Ebene_operations.pdf` | Opérations | Assurance vie Alice |
| | `SG_Ebene2_operations.pdf` | Opérations | Assurance vie Alice |
| | `SG_Ebene_supports.xlsx` | Positions | Assurance vie Alice |
| | `SG_Ebene2_supports.xlsx` | Positions | Assurance vie Alice |
| **NATIXIS** | `Historique et suivi de mes opérations - Natixis Interépargne.pdf` | Opérations + Solde | PEE Alice |
| | `Mon épargne en détail - Natixis Interépargne.pdf` | Positions | PEE Alice |
| **BTC** | `btc_{wallet}_operations.csv` | Opérations | → btc_balances.csv |
| | `btc_balances.csv` | Soldes | Wallets BTC |
| **XMR** | `xmr_{wallet}_operations.csv` | Opérations | → xmr_balances.csv |
| | `xmr_balances.csv` | Soldes | Wallets XMR |
| **KRAKEN** | `ledgers.csv` | Opérations | → balances.csv |
| | `balances.csv` | Soldes | Compte Kraken EUR, Compte Kraken BTC |
| **WISE** | `statement_*.xlsx` (ZIP) | Opérations + Soldes | Par devise (EUR, USD, SGD, SEK) |
| **ETORO** | `eToroTransactions_*.tsv` | Opérations + Solde | Compte eToro Money (EUR) |
| | `etoro-account-statement*.xlsx` | Opérations + Solde | Portefeuille eToro Réserve (USD) |
| | `eToro_accueil.pdf` | Soldes | Compte eToro Money, Portefeuille eToro Réserve |
| | `eToro_portfolio.pdf` | Positions + Solde | Portefeuille eToro Titres (USD) |
| **PAYPAL** | `Download*.CSV` | Opérations + Solde | Compte Paypal |
| **AMAZON** | `amazon_operations.csv` | Opérations + Solde | Compte Amazon |
| **MANUEL** | `*.csv`, `*.xlsx` | Opérations + Soldes | Créances, Compléments |

*Note : Voir `config_site_files.py` pour les patterns exacts et règles de validation.*
