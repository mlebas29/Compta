# Compta_site.md — Ajouter un site

Ce document décrit l'ajout d'une nouvelle source de données (banque, courtier, exchange…) à Compta. Audience : contributeur qui veut intégrer un site bancaire/financier supplémentaire.

Un site dans Compta = la combinaison de **deux scripts Python** :

- `cpt_fetch_<NAME>.py` — collecte automatique depuis le site (Playwright/Chrome ou stub manuel)
- `cpt_format_<NAME>.py` — parsing des fichiers collectés vers le format standard interne

Le code est découvert dynamiquement au démarrage (scan glob), sans aucune modification du code central.

## Site public vs site privé

| Cas | Où placer les 2 scripts | Pour qui |
|---|---|---|
| **Site public** | À la racine du projet (`cpt_fetch_FOO.py` + `cpt_format_FOO.py`) | Site générique utile à plusieurs cloneurs — peut être proposé en PR |
| **Site privé** | Dans `custom/` (`custom/cpt_fetch_FOO.py` + `custom/cpt_format_FOO.py`) | Site spécifique à l'utilisateur — données nominatives, dossier unique, etc. |

Les deux cas suivent **les mêmes squelettes Python**. La différence est purement organisationnelle : où vivent les fichiers, et comment ils sont versionnés (PUB pour la racine, PRV pour `custom/`). Pour les détails du mécanisme d'extensions `custom/` (bootstrap, versionnage, monkeypatches), voir [`Compta_extension.md`](Compta_extension.md).

Le reste de ce document utilise `FOO` comme nom de site générique et place les fichiers à la racine (site public). Pour un site privé, remplacer `FOO` par le nom du site et ajouter le préfixe `custom/` aux chemins.

## Étapes — vue d'ensemble

1. Choisir le nom (majuscules, sans espaces : `FOO`, `MYBROKER`, `EUROPEX`)
2. Créer le squelette `cpt_fetch_FOO.py`
3. Créer le squelette `cpt_format_FOO.py`
4. Configurer le site (config.ini, config_accounts.json) — via GUI ou manuellement
5. Tester la collecte et l'import

## 1. Squelette `cpt_fetch_FOO.py` (Tier 1)

Le fetcher télécharge les fichiers bruts depuis le site et les dépose dans `dropbox/FOO/`.

```python
#!/usr/bin/env python3
"""cpt_fetch_FOO.py — collecte FOO."""

from inc_fetch import BaseFetcher, fetch_main, config

# DESCRIPTION (consommée par la GUI onglet Sites)
DESCRIPTION = """FOO — courtier en ligne.

══════ Configuration ══════
1 portefeuille + N comptes (1 par devise).

══════ 2FA ══════
SMS à la connexion.
"""


class FooFetcher(BaseFetcher):
    def __init__(self, verbose=False):
        super().__init__(caller_file=__file__, verbose=verbose)

    def run(self):
        # 1. Authentification (Playwright headed/headless selon site)
        # 2. Navigation vers l'export
        # 3. Téléchargement des fichiers
        # 4. Dépôt dans self.dropbox_dir (== dropbox/FOO/)
        ...


if __name__ == '__main__':
    fetch_main(FooFetcher, description='Fetch FOO')
```

**Points clés** :

- Hérite de `BaseFetcher` (gère credentials, navigateur, dropbox).
- Aucune transformation : les fichiers sont déposés **bruts** dans `dropbox/FOO/`, exactement tels que la banque les envoie. Le formatting est la responsabilité du Tier 2.
- `DESCRIPTION` est lue par la GUI onglet Sites pour afficher l'aide à l'utilisateur.
- Pour un site sans automatisation possible (fichiers déposés manuellement par l'utilisateur), le fetcher peut être un stub qui ne fait rien ou affiche un message d'aide.

## 2. Squelette `cpt_format_FOO.py` (Tier 2)

Le formatter parse les fichiers bruts de `dropbox/FOO/` et produit **le format standard interne consommé par `cpt_update.py` (Tier 3)**. C'est le contrat de pipe central : tout ce qui sort d'un formateur doit respecter l'une des deux signatures ci-dessous, sinon l'import casse.

```python
#!/usr/bin/env python3
"""cpt_format_FOO.py — formateur FOO."""

from inc_format import site_name_from_file
from inc_categorize import categorize_operation, get_max_days_back_from_config

SITE = site_name_from_file(__file__)  # → 'FOO'

# Fichiers attendus dans dropbox/FOO/
EXPECTED_FILES = [
    ('foo_operations.csv', 'exact', '1'),       # 1 fichier obligatoire
    ('foo_supports_*.xlsx', 'glob', '0+'),      # 0 ou + fichiers positions
]

# Optionnel : limite stricte du nombre de comptes
MAX_ACCOUNTS = 4


def process_operations(file_path):
    """Parse foo_operations.csv → liste de tuples 9 champs (Opérations)."""
    ...


def process_positions(file_path):
    """Parse foo_supports_*.xlsx → liste de tuples 4 champs (Positions)."""
    ...
```

### Variables de module — résumé

| Variable | Rôle | Obligatoire | Fichier |
|---|---|---|---|
| `SITE` | Nom du site dérivé du nom de fichier | Oui (auto via `site_name_from_file`) | format |
| `EXPECTED_FILES` | Patterns des fichiers attendus dans `dropbox/SITE/` | Oui | format |
| `MAX_ACCOUNTS` | Limite stricte du nombre de comptes attachés | Non | format |
| `DESCRIPTION` | Texte d'aide affiché en GUI onglet Sites | Oui | **fetch** |

### `EXPECTED_FILES` — détail

Liste de tuples `(pattern, matching, cardinalité)` :

| Champ | Valeurs | Description |
|---|---|---|
| `pattern` | chaîne | nom de fichier (exact) ou glob (`*`, `?`) |
| `matching` | `'exact'` ou `'glob'` | Mode de comparaison |
| `cardinalité` | `'1'`, `'1+'`, `'0-1'`, `'0+'` | Nombre attendu (cf. tableau ci-dessous) |

| Cardinalité | Signification | Si surnuméraires |
|---|---|---|
| `1` | Exactement 1 attendu | Warning + sélection auto |
| `1+` | Au moins 1, tout prendre | OK |
| `0-1` | Optionnel, max 1 | Warning + sélection si > 1 |
| `0+` | Optionnel, tout prendre | OK |

## 3. Interface pipe avec l'import (Tier 3)

Les deux fonctions `process_operations` et `process_positions` sont les **seuls points de contact** entre ton site et l'import dans le classeur. Toute la chaîne aval (`cpt_update.py`, déduplication, appariement, écriture Excel) consomme ces deux formats. Si tu respectes la signature, ton site fonctionne ; sinon l'import casse, parfois en silence.

### Format 9 champs — Opérations

```
Date;Libellé;Montant;Devise;Equiv;Réf;Catégorie;Compte;Commentaire
```

Une ligne par mouvement (débit/crédit), plus une ligne `#Solde` en fin (catégorie spéciale = solde relevé à la date courante).

| Champ | Format | Source typique |
|---|---|---|
| Date | `DD/MM/YYYY` | brut |
| Libellé | texte brut tel que reçu de la banque | brut |
| Montant | nombre signé (positif = crédit, négatif = débit) | brut |
| Devise | code 3 lettres (EUR, USD, BTC, XAU…) | brut |
| Equiv | montant en EUR équivalent (cf. ci-dessous) | calculé ou vide |
| Réf | `-` ou identifiant d'appariement | conventionnel (cf. ci-dessous) |
| Catégorie | catégorie issue de `categorize_operation` | catégorisation |
| Compte | nom exact du compte tel que listé dans `config_accounts.json` | mapping site |
| Commentaire | libre | brut ou vide |

### Format 4 champs — Positions

```
Date;Ligne;Montant;Compte
```

Pour les portefeuilles titres (assurance vie, fonds, actions). Une ligne par holding. Inclut éventuellement une ligne `#Solde Réserve` pour le cash du portefeuille.

### Catégorisation et appariement

```python
cat, opts = categorize_operation(libelle, SITE)
ref = opts.get('ref', '')         # '-' déclenche l'appariement par cpt_update
equiv = opts.get('equiv', '')     # 'amount' = copier le montant dans Equiv
```

Les patterns regex sont déclarés dans `config_category_mappings.json` (section `SITE_PATTERNS[FOO]` ou `GENERIC_PATTERNS`). L'utilisateur les édite via la GUI onglet Catégories.

### Colonne Equiv (équivalent EUR)

| Cas | Valeur Equiv |
|---|---|
| Opération en EUR | vide (Equiv = Montant trivialement) |
| Opération non-EUR sans contrepartie | vide — `cpt_update` enrichit via taux ECB |
| Échange cross-currency avec montant EUR connu | renseigner explicitement, même valeur EUR des deux côtés |

### Colonne Réf et autres champs « ignorés »

Plusieurs champs ne sont pas comparés à l'import :

- **Réf** : numérotation interne, attribuée à l'écriture dans la feuille. Le formatter pose `-` pour signaler une opération à apparier (virement, change, achat de titre) ; toute autre valeur est ignorée.
- **Catégorie** : remplie manuellement par l'utilisateur après import si le pattern regex n'a pas matché.
- **Commentaire** : libre, jamais comparé.

La déduplication compare uniquement `Date + Compte + Montant + Libellé` — peu importe ce que tu mets dans Réf/Commentaire.

### Filtrage temporel

Pour ne pas réimporter d'anciennes opérations à chaque collecte :

```python
max_days = get_max_days_back_from_config(SITE)  # défaut 90 jours
# Filtrer les opérations dont la date est > today - max_days
```

Configurable dans `config.ini` section `[general] max_days_back` (global) ou `[FOO] max_days_back` (override site).

## 4. Configuration utilisateur

### 4.1 Création initiale de la section `[FOO]` (manuelle)

La GUI ne sait éditer que des sections existantes. Pour un site neuf, créer d'abord la section dans `config.ini` en copiant une section voisine et en adaptant les valeurs :

```ini
[FOO]
credential_id = foo                  # clé dans config_credentials.md
url           = https://www.foo.com/login
max_days_back = 90                   # optionnel — override du global
# autres clés selon le fetcher (timeout, headed, etc.)
```

Une fois la section présente, relancer `cpt_gui.py` : FOO apparaît dans l'onglet Sites et tout le reste se fait via la GUI.

### 4.2 Suite via la **GUI Configuration** de `cpt_gui.py`

Trois onglets, trois fichiers :

- **onglet Sites** → `config.ini` : coche `[sites] enabled = …, FOO` et édite les champs de la section `[FOO]`.
- **onglet Comptes** → `config_accounts.json` : liste des comptes attachés à FOO.
- **onglet Catégories** → `config_category_mappings.json` : patterns regex de catégorisation.

### 4.3 Credentials

Déposer les identifiants chiffrés dans le fichier configuré par `config.ini` section `[paths]` clé `credentials_file` (cf. `config_credentials.md.default` pour le modèle).

### 4.4 Champs de compte spécifiques au site (`ACCOUNT_FIELDS`)

Par défaut, créer un compte dans l'onglet **Comptes** ne demande que les champs génériques (intitulé, devise, type…). Un site peut exiger des **champs supplémentaires** (un RIB, un numéro de contrat, une clé de wallet…) en déclarant la variable `ACCOUNT_FIELDS` dans son module `cpt_format_<NAME>.py` :

```python
# cpt_format_FOO.py
ACCOUNT_FIELDS = [
    ('RIB :',  'rib',  'entry', None),                 # champ texte
    ('Type :', 'type', 'combo', ['principal', 'épargne']),  # liste déroulante
]
```

Chaque tuple est `(libellé, clé, widget, options)` — `widget` ∈ `'entry'` / `'combo'` (`options` = la liste pour un combo, sinon `None`). Le dialogue « Ajouter un compte » de l'onglet Comptes affiche alors ces champs (tous **requis**) ; leurs valeurs sont persistées dans l'entrée du compte de `config_accounts.json` sous la `clé` indiquée, où le formateur les relit (ex. mapping RIB → nom de compte).

Mécanisme : `inc_format.get_account_fields()` lit `ACCOUNT_FIELDS` du module ; `gui_accounts._site_account_fields` y retombe pour tout site non câblé en dur. **Aucune modification du cœur** (pas de nom de site dans le code public) — la déclaration vit entièrement dans le module du site, `custom/` compris.

### 4.5 Collecte tiérée : groupe parallèle vs sériel (`parallel`)

La collecte `cpt_fetch.py` range chaque site dans un **groupe parallèle** (collecté en même temps que les autres) ou un **groupe sériel** (sites exigeant l'humain **pendant** la collecte — 2FA, CAPTCHA, code — traités **un à la fois**). Le parallèle est collecté **en premier** ; l'humain n'intervient qu'ensuite sur le sériel.

**Deux axes ORTHOGONAUX** :
- **`parallel`** (l'appartenance au groupe) a **deux moitiés** :
  - *structurelle — décidée par le code* : un fetcher **sans navigateur** (API/RPC) ne *peut pas* solliciter l'humain → **parallèle** ; un fetcher **navigateur** (`BaseFetcher`) → **sériel** par défaut. Détecté en **scannant la source** `cpt_fetch_<SITE>.py` (présence de `class …(BaseFetcher)`), sans importer le module (les fetchers tournent en sous-processus).
  - *« compte » — décidée par l'utilisateur* : qu'un site navigateur exige *réellement* la 2FA dépend de son compte → **override** `[SITE] parallel = true`, à ne poser **que pour l'exception** (site navigateur sans 2FA sur ce compte).
- **`credential`** (présence de `credential_id`) est **dérivé** et ne subdivise QUE le parallèle.

Trois tiers en découlent :

| Tier | Condition | Traitement |
|---|---|---|
| **auto** | parallèle, **pas** de `credential_id` | **parallèle**, planifiable sans humain (`--auto`, cron) |
| **semi** | parallèle, **avec** `credential_id` | **parallèle** ; un seul mot de passe GPG (mis en cache) couvre le lot |
| **manual** | sériel | **séquentiel**, humain requis |

Les parallèles (auto + semi) sont collectés **en parallèle** (plafond 4) et **avant** les sériels. **`cpt_fetch.py --auto`** ne collecte que le tier **auto** (aucun `credential_id` → aucun pinentry) → idéal en **cron**.

En pratique, **`config.ini` ne contient `parallel` que pour de rares overrides** (souvent aucun) : les API sont parallèles d'office, les sites navigateur sériels d'office. _(Ancien nom `requires_2fa` — polarité inverse — encore lu en repli, le temps de la transition.)_

## 5. Test

```bash
# Vérifier que le site est bien détecté
./cpt_gui.py            # onglet Sites → FOO doit apparaître

# Collecte standalone
./cpt_fetch.py --sites FOO
ls dropbox/FOO/                # → les fichiers téléchargés

# Pipeline complet
./cpt.py --sites FOO     # fetch + import
```

Le formatter parse les fichiers de `dropbox/FOO/`, `cpt_update.py` importe les opérations dans le classeur, archive les fichiers bruts dans `archives/FOO/`.

## 6. Instrumentation & robustesse (briques `BaseFetcher`)

Le squelette des §1-5 suffit à **collecter**. Cette section couvre les briques qui rendent un fetcher **robuste** (échecs diagnostiquables, sessions expirées détectées) et **instrumenté** (attentes humaines notifiées et mesurées, dérives de site détectées). Elles sont **opt-in** : un fetcher marche sans, mais un fetcher de production les câble toutes.

> **Mettre à niveau un vieux fetcher** — checklist. Un fetcher écrit avant ces briques (ou copié d'un ancien gabarit) se remet à niveau en câblant, dans l'ordre :
> 1. **`self.step(...)`** aux frontières de phase (remplace les `logger.info` d'entête) — §6.2
> 2. **`self.logger.alert(...)` + `self.logger.user_done()`** autour de chaque 2FA/CAPTCHA/login manuel — §6.1
> 3. **`self.reject_saved_if_html(path, label)`** après chaque download — §6.3
> 4. **`self.relaunch_headed()`** sur besoin d'action humaine (indispensable en headless) — §6.4
> 5. Config : migrer `requires_2fa` → `parallel` dans la section `[SITE]` — §4.5
>
> Les briques §6.5 (dump sur échec) et §6.6 (snapshot d'étape) sont **automatiques** : rien à câbler, elles s'activent dès que le fetcher hérite de `BaseFetcher` et passe par `fetch_main`.

### 6.1 Attente humaine — `alert()` / `user_done()`

Encadre **tout** moment où la collecte attend une action de l'utilisateur (2FA, CAPTCHA, validation mobile, saisie de code, login manuel) :

```python
self.logger.alert("VALIDATION 2FA — Valide sur l'appli mobile")  # AVANT l'attente
# ... poll jusqu'à ce que la connexion soit détectée ...
self.logger.user_done()                                          # APRÈS l'action
```

Un seul appel `alert()` par séquence suffit à armer le chrono (les alertes consécutives le partagent) ; `user_done()` le clôt. **Triple gain** :

- **GUI** : la ligne `alert()` porte le marqueur `🔔` → l'onglet Exécution flashe, sonne et passe au premier plan (`gui_exec.py`). C'est **le seul signal en headless** (fenêtre invisible) — sans lui, un 2FA/CAPTCHA se solde par un hang silencieux jusqu'au timeout.
- **Journal** : `user_done()` écrit un marqueur parsable `⏳ Attente humaine : Ns` → permet de déduire le temps machine (total − attente).
- **Profilage** (§6.2) : la durée d'attente humaine est **retranchée** de la durée de l'étape → la baseline mesure le site, pas ta latence de réaction. Appeler `user_done()` **juste après** la résolution : si l'attente reste ouverte, la clôture d'étape la strippe grossièrement (temps machine post-action perdu, mais jamais gonflé).

### 6.2 Profil de navigation — `self.step(label)`

Marque chaque frontière de phase dans `run()` (remplace un `logger.info()` d'entête, zéro ligne en plus) :

```python
def run(self):
    self.step("Login")
    if not self.wait_for_login():
        return False
    self.step("Opérations")
    self._download_operations()
    self.step("Soldes")
    self._fetch_balances()
    return True
```

Chaque étape est chrono-métrée → baseline **médiane glissante par site** (`inc_fetch_profile`, store `logs/fetch_profiles.json` machine-local). Consultable via `tool_fetch_profile.py --show SITE`. Répond à « le site a-t-il changé de comportement ? » (étape nouvelle/disparue, durée qui explose, fichier manquant). **Le label est la clé de baseline ET le nom du snapshot (§6.6) → le garder STABLE** dans le temps (`"Login"`, pas `"Login v2"`).

### 6.3 Garde anti-HTML — `reject_saved_if_html()`

Un site sert parfois une **page de login/redirect en HTTP 200** quand la session a expiré ou que l'URL d'export a changé. L'event `download` Playwright ne porte pas de content-type : sans garde, tu sauves le HTML, et le formateur échoue plus tard sur un `KeyError` cryptique. Après chaque écriture de download :

```python
path = self.dropbox_dir / 'foo_operations.csv'
# ... sauvegarde du download vers path ...
if not self.reject_saved_if_html(path, "opérations"):
    return False   # fichier HTML supprimé, erreur claire déjà loggée
```

### 6.4 Repli visible — `relaunch_headed()`

Le headless est le défaut (`DEBUG=false`). Un fetcher qui a besoin d'une action humaine doit **repasser visible**, sinon la fenêtre invisible bloque l'utilisateur :

```python
if login_requis:
    if not (self.debug or self._headed):   # déjà visible en mode DEBUG
        self.relaunch_headed()             # ferme + relance Chrome en visible
    self.logger.alert("CONNEXION REQUISE — Connecte-toi dans Chrome")
    # ... attendre la connexion, puis user_done() ...
```

Sans ce repli, un fetcher qui `alert()` mais reste headless **notifie** l'utilisateur (§6.1) sans lui donner de fenêtre pour agir : la collecte n'aboutit que si la session était déjà valide.

### 6.5 Diagnostic sur échec — `dump_failure()` *(automatique)*

`fetch_main` appelle `dump_failure()` sur tout `run()` renvoyant `False` **et** sur toute exception : capture DOM + screenshot dans `logs/debug/<site>_echec_run.html` (+ `.png`), **même sans DEBUG**, chemin signalé en clair. Un échec « bloqué/timeout » n'est diagnosticable qu'avec ce snapshot au point d'échec. **Rien à câbler** — le fetcher en hérite. Pour capturer un point risqué précis en cours de route : `self._dump_page_debug('label', force=True)`.

### 6.6 Snapshot d'étape — *(automatique)*

Chaque `self.step(label)` (§6.2) capture aussi un snapshot DOM roulant du début de l'étape (cousin de §6.5 mais **sans** échec) → on a toujours le dernier état de chaque site/étape pour investiguer un changement. Gouverné par `[general] dump_steps` (`dom` par défaut · `full` ajoute le PNG, coûteux · `off`). Best-effort, jamais bloquant.

## Cas avancés

### Échanges cross-currency (Change, Achat métaux/crypto)

Si FOO propose des conversions cross-devise (EUR ↔ USD, EUR ↔ BTC…), ajouter le ou les comptes concernés à la liste `MESH_TRANSFERS` de `cpt_update.py`. C'est ce mécanisme qui apparie automatiquement le débit EUR avec le crédit USD/BTC en chaînant par la colonne Equiv.

### Comptes multiples (portefeuille titres)

Pour un compte-titre (Réserve cash + Titres securities), créer **deux comptes distincts** : `Portefeuille FOO Titres` et `Portefeuille FOO Réserve`. Les achats/ventes génèrent des entrées symétriques (Réserve débit ↔ Titres crédit). `MAX_ACCOUNTS` peut alors être 2 (par exemple).

### Site privé dans `custom/`

Tout ce qui précède s'applique tel quel, en plaçant les scripts dans `custom/` au lieu de la racine. Pour démarrer, copier un fetcher/format existant comme gabarit (le code en place est le meilleur modèle, à jour) :

```bash
cp cpt_fetch_BTC.py custom/cpt_fetch_FOO.py      # gabarit API ; Playwright → cpt_fetch_KRAKEN.py
cp cpt_format_BTC.py custom/cpt_format_FOO.py
```

puis renommer/adapter (cf. étapes ci-dessus). Voir [`Compta_extension.md`](Compta_extension.md) pour le mécanisme d'extensions `custom/` (bootstrap, versionnage, monkeypatches).

### Monkeypatch d'un site existant

Si tu veux **modifier** le comportement d'un site public sans changer son code (par exemple regrouper certaines lignes d'un parsing existant), c'est un patch dans `custom/patch_*.py` — voir [`Compta_extension.md`](Compta_extension.md) §2 (Monkeypatch).
