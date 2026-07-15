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
- Contrôler la cohérence : la somme des montants de la colonne **hors catégories `#…`** doit être nulle (les catégories `#Solde`, `#Info`, `#Balance` sont exclues car ce sont des marqueurs statiques sans contrepartie)
- **Ancrer le calcul de plus-value** pour les comptes en devise non-EUR : si la colonne est renseignée sur une ligne `#Solde`, cette ligne devient le point d'ancrage (date et montant initial) du calcul PVL du compte concerné. Si plusieurs `#Solde` du même compte ont leur équivalent EUR renseigné, c'est le plus récent qui fait foi — ce qui permet de "purger" les opérations anciennes en posant un nouveau point d'ancrage. L'équivalent EUR d'un `#Solde` doit être saisi au cours d'époque du relevé.

Pour les comptes en EUR, l'équivalent EUR est trivialement égal au montant et la GUI le pose automatiquement à la création d'un compte avec solde initial. Pour les comptes non-EUR, la GUI demande l'équivalent EUR à la saisie du solde initial (cours d'époque, obligatoire).

### Réf.
Le champ Réf. du tableau Opérations est un identifiant, par ex V32, qui sert à relier plusieurs opérations des catégories Virement, Change ou Titres (Achat, Vente ...)

- Dans le cas du virement, il y a juste la paire débit/crédit Vxxx
- Dans le cas de change il y a la paire débit/crédit plus les frais s'ils sont comptabilisés séparemment. Le préfixe est celui de la devise créditée en minuscule, par exemple : usd465
- Dans le cas des titres, il y a autant de références txxx que nécessaire, notamment dans les cas d'arbitrage ou de rachat de portefeuilles comportant plusieurs titres. 

### Contrôles
La feuille Contrôles porte deux tableaux et une cellule de statut global A1 (synthèse de symboles `✓`/`✗`/`⚠`, cf. ANNEXE A de Compta.md).

- **Tableau 1** : pour chaque compte et devise, compare le solde relevé (#Solde le plus récent) au solde calculé (somme des opérations). Colonnes définies par named ranges CTRL1 (écart, contrôle).
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
cpt --sites SOCGEN,NATIXIS  # Sites spécifiques uniquement
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

## Configuration en ligne de commande

L'App n'est jamais un passage obligé : les fichiers de configuration restent lisibles et modifiables à la main. Ce chemin sert sur une machine sans écran, en dépannage lorsque l'interface graphique ne démarre pas, ou simplement par préférence. Le parcours assisté équivalent est décrit dans [`Compta.md`](Compta.md) ANNEXE C.

### La table d'identifiants

`config_credentials.md.gpg` est un **tableau Markdown chiffré en symétrique**. Rien de plus : `gpg` seul suffit à l'ouvrir et à le refermer, sans l'App.

- **Présentation formatée**

| Réf        | Identifiant | Passe |
| ---------- | ----------- | ----- |
| PAYPAL     |             |       |
| ETORO      |             |       |
| BOURSOBANK |             |       |

- **Présentation brute**

```
| Réf | Identifiant | Passe |
|-----|-------------|-------|
| PAYPAL | | |
| ETORO | | |
| BOURSOBANK | | |
```

La **Réf** (nom au choix) est à reporter à l'identique lors de la configuration du site ([`Compta.md`](Compta.md) ANNEXE C §4). Les libellés d'en-tête, eux, sont libres : l'App reconnaît l'en-tête à sa **position** — la ligne qui précède le séparateur — pas à son intitulé.

#### Première mise en place

```bash
# config_credentials.md est créé par install.sh
# (sinon : cp config_credentials.md.default config_credentials.md)
# … remplir config_credentials.md …
gpg -c config_credentials.md     # → config_credentials.md.gpg (chiffré)
rm config_credentials.md         # impératif : efface les identifiants en clair
```

#### Modifier la table à la main

```bash
gpg -d config_credentials.md.gpg > config_credentials.md   # déchiffre
# … modifier config_credentials.md …
gpg -c config_credentials.md                               # rechiffre
rm config_credentials.md                                   # impératif : efface le clair
```

> ⚠️ Le chemin manuel fait exister une **copie en clair** de vos mots de passe le temps de l'édition : le `rm` final n'est pas optionnel. C'est la différence avec l'App, qui ne pose jamais le clair sur le disque.
>
> ⚠️ `gpg -c` demande une **nouvelle** passphrase et la fait confirmer : une faute de frappe produit une table que votre mot de passe habituel n'ouvrira plus. Gardez une copie du `.gpg` avant de rechiffrer.

### Les autres fichiers de configuration

`config.ini` et les `config_*.json` s'éditent de même : ce sont des fichiers texte. Aucun n'est versionné — ils décrivent **votre** installation, et survivent donc aux mises à jour. Le détail de chacun — rôle, ce qui est livré, ce qui est généré à la volée — est tenu à jour dans la table *Configuration* de [`Compta_dev.md`](Compta_dev.md).

## Mise à jour et modifications locales

### Mise à jour simple

```bash
cd ~/Compta && git pull
```

Cette commande télécharge les dernières modifications depuis le dépôt distant et les applique. Si vous n'avez modifié aucun fichier versionné, tout se passe automatiquement.

### Fichiers personnels hors versionnement

Les fichiers de configuration personnels (`config.ini` et les `config_*.json`) ne sont pas versionnés par git — voir la table Configuration de [`Compta_dev.md`](Compta_dev.md) pour la liste détaillée. Ils ne sont donc jamais affectés par `git pull`.

### Si vous avez modifié des fichiers versionnés

Si vous avez modifié un script ou un fichier versionné (par exemple un formateur `cpt_format_*.py`), `git pull` peut échouer avec un message du type :

```
error: Your local changes to the following files would be overwritten by merge
```

**Méthode recommandée — mettre de côté puis réappliquer :**

```bash
git stash                  # Met vos modifications de côté
git pull                   # Télécharge la mise à jour
git stash pop              # Réapplique vos modifications
```

Si `git stash pop` signale un conflit (les mêmes lignes ont été modifiées des deux côtés), git insère des marqueurs dans le fichier concerné :

```
<<<<<<< Updated upstream
    ligne de la version distante
=======
    votre ligne modifiée
>>>>>>> Stashed changes
```

Ouvrez le fichier, choisissez la version à garder (ou combinez les deux), puis supprimez les marqueurs `<<<<<<<`, `=======`, `>>>>>>>`. Ensuite :

```bash
git add le_fichier_corrigé.py
git stash drop             # Supprime le stash résolu
```

**Alternatives rapides :**

```bash
# Garder votre version pour un fichier (ignorer la mise à jour distante)
git checkout --ours le_fichier.py

# Garder la version distante (abandonner votre modification)
git checkout --theirs le_fichier.py
```

### Si `git pull` échoue avec « unrelated histories »

Après une **réécriture d'historique** du dépôt (versions marquées 🔄 dans le [CHANGELOG](CHANGELOG.md), ex. v5.1.0), un `git pull` classique échoue avec :

```
fatal: refusing to merge unrelated histories
```

Ce n'est **pas** un conflit de modification : l'historique a été réinitialisé côté distant. La bonne réponse est de **re-cloner** — vos fichiers privés (`config.ini`, `config_*.json`, `comptes.xlsm`, `custom/`…) sont sauvegardés puis restaurés automatiquement :

```bash
./reclone.sh --reclone --yes
```

Si le script n'est pas présent (mise à jour ratée avant la réécriture), récupérez-le par son canal de secours :

```bash
curl -fsSL https://raw.githubusercontent.com/mlebas29/Compta/main/reclone.sh -o /tmp/reclone.sh && bash /tmp/reclone.sh --reclone --yes
```

Détails dans l'entrée 🔄 du [CHANGELOG](CHANGELOG.md).

### Voir ce qui a été modifié localement

```bash
git status                 # Liste des fichiers modifiés
git diff                   # Détail des modifications
git diff le_fichier.py     # Modifications d'un fichier spécifique
```

### Annuler toutes les modifications locales

Pour revenir à l'état du dépôt (perte de toutes vos modifications) :

```bash
git checkout .             # Restaure tous les fichiers versionnés
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
cpt --sites SOCGEN         # Relancer un site spécifique
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
./cpt_gui.py         # Lancement standard
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
| | `{numero}.csv` | Opérations + Solde | Compte courant |
| | `Export_XXXXXXXXX_*.csv` | Opérations + Solde | Livrets, LDD, CSL |
| | `SG_Ebene_operations.pdf`, `SG_Ebene_operations#*.pdf` | Opérations | Assurance vie Alice |
| | `SG_Ebene2_operations.pdf`, `SG_Ebene2_operations#*.pdf` | Opérations | Assurance vie Alice |
| | `SG_Ebene_supports.xlsx` | Positions | Assurance vie Alice |
| | `SG_Ebene2_supports.xlsx` | Positions | Assurance vie Alice |
| **NATIXIS** | `Historique et suivi de mes opérations - Natixis Interépargne.pdf` | Opérations + Solde | PEE Alice |
| | `Mon épargne en détail - Natixis Interépargne.pdf` | Positions | PEE Alice |
| **BTC** | `btc_{wallet}_operations.csv` | Opérations | → btc_balances.csv |
| | `btc_balances.csv` | Soldes | Wallets BTC |
| **XMR** | `xmr_{wallet}_operations.csv` | Opérations | → xmr_balances.csv |
| | `xmr_balances.csv` | Soldes | Wallets XMR |
| **KRAKEN** | `kraken-spot-ledgers-*.zip` | Opérations | → balances (interne) |
| | `kraken-spot-balances-*.zip` | Soldes | Compte Kraken EUR, Compte Kraken BTC |
| **WISE** | `transaction-history.csv` | Opérations | Jambes par devise |
| | `wise_balances.csv` | Soldes | #Solde par devise (jar) |
| **ETORO** | `eToroTransactions_*.tsv` | Opérations + Solde | Compte eToro Money (EUR) |
| | `etoro-account-statement*.xlsx` | Opérations + Solde | Portefeuille eToro Réserve (USD) |
| | `eToro_accueil.pdf` | Soldes | Compte eToro Money, Portefeuille eToro Réserve |
| | `eToro_portfolio.pdf` | Positions + Solde | Portefeuille eToro Titres (USD) |
| **PAYPAL** | `*.CSV` | Opérations + Solde | Compte Paypal |
| **AMAZON** | `amazon_operations.csv` | Opérations + Solde | Compte Amazon |
| **MANUEL** | `*.xlsx` | Opérations + Soldes | Créances, Compléments |

*Note : Voir la variable `EXPECTED_FILES` dans chaque `cpt_format_<NAME>.py` pour les patterns exacts et règles de validation.*

> 📖 Sigles et termes du projet : [`Compta_glossaire.md`](Compta_glossaire.md).
