# Changelog

Chronique des versions de l'app, orientée utilisateur. Les changements internes du code ne sont généralement pas décrits.

- 📘 = nouvelle version du classeur exemple (mode classeur)
- 🔧 = migration du classeur livrée (mode assisté : `upgrade` la propose ; mode classeur : à reporter à la main)
- 🔄 = re-clonage du dépôt requis (réécriture d'historique git)
- ⚙️ = config à normaliser (lancer `./install_fix.sh`)

## v5.6.0
| 2026-06-14 | Upgrade (Mise à jour de version) : rattrapage d'installations anciennes. |
| ---------- | ------------------------------------------------------------ |

**Détail :**

- **Documentation** — `README` (§ Mise à jour) allégé ; `Compta_upgrade_assiste.md` (méthode, geste, exemple de chemin de mise à jour) et `Compta_upgrade_classeur.md` (couverture par version revue, redondances « mode assisté » retirées) clarifiés.
- **Geste resserré, plus longue portée** — un seul script à télécharger et lancer ; les installations antérieures à v5.1.0, jusqu'ici réinstallables à la main, sont **remises à niveau automatiquement**.
- **Avis de démarrage** — l'avertissement « mise à niveau attendue » renvoie désormais à la procédure détaillée ([`Compta_upgrade_assiste.md`](Compta_upgrade_assiste.md)).

## v5.5.0
| 2026-06-13 | Renommage du geste de mise à jour + carte des versions plus claire. |
| ---------- | ------------------------------------------------------------ |

Le geste s'appelle désormais `./upgrade.py` (au lieu de `install_upgrade.py`), et ses deux docs sont nommées par mode d'usage (`Compta_upgrade_assiste.md` / `Compta_upgrade_classeur.md`). La carte des versions devient un **tableau chronologique unique** (récent en premier) couvrant les trois axes — classeur, config, dépôt — avec les **butées** d'automatisation (point où la mise à jour automatique s'arrête) et leur contournement manuel.

**Détail :**

- **Renommage** — `install_upgrade.py` → **`upgrade.py`** ; docs `Compta_install_upgrade.md` / `Compta_upgrade.md` → **`Compta_upgrade_assiste.md`** / **`Compta_upgrade_classeur.md`**. Seule la commande tapée change ; aucune autre incidence.
- **Carte des butées** — un tableau unique par version (récent d'abord), trois axes + outil ; une **butée** 🧱 marque la profondeur de rattrapage automatique (préhistoire pré-v3.4 ; reclone v5.1.0) et renvoie au contournement manuel. Documentation régénérée depuis la source unique `upgrade_map.json`.

## v5.4.0
| 2026-06-12 | Mise à jour plus sûre et mieux expliquée. |
| ---------- | ------------------------------------------------------------ |

Au démarrage, l'application **prévient** si du code a été tiré sans honorer une mise à niveau attendue (migration classeur ou config), et oriente vers le bon geste. `upgrade` **refuse désormais de migrer un classeur ouvert** (dans LibreOffice ou l'application) pour éviter tout conflit. La documentation de mise à niveau est **générée par mode d'usage** (assisté / classeur) depuis une source unique.

**Détail :**

- **Avis au démarrage** — si une version « badgée » (migration classeur 🔧, config ⚙️) a été franchie sans la honorer, l'app le signale (GUI et ligne de commande) et indique le geste ; sinon elle reste silencieuse. Repère mémorisé dans `config.ini` (`honored_version`).
- **Garde « classeur ouvert »** — `upgrade` détecte un classeur verrouillé (LibreOffice) ou l'application en cours, et **refuse la migration** plutôt que de risquer une corruption ; l'avis de mise à jour persiste tant que ce n'est pas fait.
- **Carte des mises à jour par mode** — `Compta_upgrade_assiste.md` (assisté) et `Compta_upgrade_classeur.md` (classeur) sont dérivés d'une source unique (`upgrade_map.json`), chacun cadré pour son mode.

## v5.3.1
| 2026-06-11 | Garde-fou de mise à jour étendu. |
| ---------- | ------------------------------------------------------------ |

Si le code a été mis à jour sans `upgrade` (un `git pull` manuel), l'application **refuse désormais d'opérer sur un classeur non migré aussi en ligne de commande** — plus seulement dans l'interface — et oriente vers `./upgrade.py` (réversible) plutôt que vers la seule procédure manuelle.

## v5.3.0
| 2026-06-11 | Outil de mise à jour, et réversible. |
| ---------- | ------------------------------------------------------------ |

`./upgrade.py` met à niveau l'installation (code **et** classeur) en une commande : il tire le nouveau code, propose les migrations de classeur nécessaires (sauvegarde + consentement, jamais en silence) et, en cas de souci, permet de **revenir en arrière** (`--restore`).

**Détail :**

- **`upgrade.py`** (mode assisté) — un seul geste pour mettre à jour : tire le code, applique les rattrapages bénins (config, raccourci), **propose** les migrations du classeur (refusé si LibreOffice < 24.8). `--check` montre ce qui serait fait sans rien appliquer.
- **Réversibilité** — chaque mise à jour prend un snapshot complet (code + config + classeur) avant de toucher quoi que ce soit ; `--liste` / `--restore <date>` ramènent l'installation à un point antérieur (les 10 derniers conservés). Détails : [`Compta_upgrade_assiste.md`](Compta_upgrade_assiste.md).
- **Re-clone proposé, jamais forcé** — si une mise à jour normale est impossible (historique réécrit), `upgrade` propose un re-clone sûr au lieu d'échouer.
- **Cadre privé** — `install.sh` prépare un dossier `custom/` pour les extensions (sites privés, monkeypatches) ; voir [`Compta_extension.md`](Compta_extension.md).
- **Documentation** — `Compta_upgrade_classeur.md` recentré sur les migrations du classeur ; le geste de mise à jour a sa page dédiée [`Compta_upgrade_assiste.md`](Compta_upgrade_assiste.md).

## v5.2.1 ⚙️
| 2026-06-08 | Config plus robuste. |
| ---------- | ------------------------------------------------------------ |

Au démarrage, l'app vérifie que `config.ini` est aligné sur le modèle (`config.ini.default`) et signale les clés obsolètes/manquantes ou un mode invalide, en invitant à lancer `./install_fix.sh` — qui **normalise désormais la config** (renommages hérités : `mode = export`→`EX`, `seafile_comptes_file`→`classeur_externe`).

## v5.2.0
| 2026-06-07 | Modes et installation refondus. |
| ---------- | ------------------------------------------------------------ |

Les modes s'appellent désormais **EX / PROD / DEV**, chacun avec son raccourci de lancement aux couleurs du mode. Deux nouveaux scripts d'installation : `install_fork.sh` et `install_fix.sh`.

**Détail :**

- **Modes EX / PROD / DEV** : nouveau nommage (anciennement `export` / `prod` / `dev`) ; les configurations existantes restent comprises, aucune action requise.
- **Lancement par raccourci** : `install.sh` pose un raccourci (menu Applications sous Linux, `~/Applications` sous macOS) — c'est le lancement recommandé. Un raccourci par mode : plusieurs installations coexistent sur une même machine.
- **`install_fork.sh`** : double une installation existante en paire PROD + DEV, pour développer ou essayer sans risque à côté de l'installation de tous les jours. Les données y sont copiées (`--no-data` pour partir à vide).
- **`install_fix.sh`** : change le mode d'une installation ou répare son raccourci.
- **Dossier d'installation libre** : l'application ne suppose plus d'être dans `~/Compta` — chaque installation se repère d'elle-même, quel que soit son dossier.
- **« Classeur externe »** : le classeur publié est désormais désigné ainsi partout (interface, journaux, documentation), sans référence au service qui l'héberge.
- **Robustesse** : une configuration de comptes incomplète n'empêche plus le chargement des sites.
- **Documentation remaniée** : guide d'utilisation ([`Compta.md`](Compta.md)) restructuré ; pour aller plus loin (code privé, nouveaux sites), [`Compta_extension.md`](Compta_extension.md) remplace l'ancienne `Compta_custom.md` ; le script `install_custom.sh` est supprimé (la mise en place du code privé est décrite dans la nouvelle doc).

## v5.1.2
| 2026-06-03 | Collecte BoursoBank robuste. |
| ---------- | ------------------------------------------------------------ |

Les comptes peu mouvementés (sans opération sur la période) ne font plus échouer la collecte : l'absence d'opération est gérée comme un cas normal (le solde reste collecté via le PDF). Correction du téléchargement des relevés de comptes bancaires (un export pouvait ramener une page web au lieu du fichier).

## v5.1.1
| 2026-06-03 | Corrections de collecte. |
| ---------- | ------------------------------------------------------------ |

eToro : la connexion est désormais maintenue quand le site remplace l'onglet pendant la validation 2FA (la collecte n'échoue plus à ce stade). Kraken : l'export CSV est de nouveau fonctionnel (le sélecteur de dates bloquait la génération du rapport) ; la fenêtre collectée est la plage par défaut Kraken (~30 jours) — lancer la collecte régulièrement pour rester continu.

## v5.1.0 🔄
| 2026-06-02 | Historique git réécrit (squash) pour en purger le passif → re-clone requis pour la mise à jour. |
| ---------- | ------------------------------------------------------------ |

**🔄 Migration de l'historique (re-clone)**

L'historique git a été réécrit. Le `git pull` de mise à jour échoue désormais (`refusing to merge unrelated histories`). Récupère et exécute le script de re-clonage par :

```bash
curl -fsSL https://raw.githubusercontent.com/mlebas29/Compta/main/reclone.sh -o /tmp/reclone.sh && bash /tmp/reclone.sh --reclone --yes
```

Le script sauvegarde le dossier entier (`.backup-<horodatage>`), re-clone, et restaure tes fichiers privés (classeur, configuration) 

**Corrections**

- Harmonisation globale (doc et code) des noms de sites.
- Doc : lancement des scripts via `./<script>` au lieu de `python3 <script>` — corrige l'échec sur macOS des scripts UNO.
- Informations privées résiduelles — retrait ou déplacement du Python vers des fichiers de configuration privés `config*.json` ; schéma `config_accounts.json` documenté dans `Compta_dev.md`.

## v5.0.4
| 2026-06-01 | Documentation & confidentialité. |
| ---------- | ------------------------------------------------------------ |

Documentation développeur par connecteur publiée (`docs/`). Correction des dossiers de dépôt dans les procédures de collecte manuelle. Pas de changement applicatif.

**Corrections**

- Procédures de collecte manuelle (Société Générale, NATIXIS, BoursoBank) : le dossier de dépôt indiqué utilisait un ancien code (`dropbox/SG/`, `dropbox/PEE/`, `dropbox/BB/`) au lieu du nom de dossier réel (`dropbox/SOCGEN/`, `dropbox/NATIXIS/`, `dropbox/BOURSOBANK/`).

**Documentation**

- `docs/` : documentation développeur approfondie par connecteur (authentification, parsing, dépannage), reliée à `Compta_dev.md`.
- `Compta.md` : l'adaptation d'un connecteur bancaire à un autre profil client se règle via les paramètres techniques des comptes (GUI) ; les restrictions éventuelles figurent dans la description de chaque site.

## v5.0.3
| 2026-05-29 | Portage WSL — collecte validée. |
| ---------- | ------------------------------------------------------------ |

Affinements `install.sh`, corrections GUI et collecte SOCGEN. Pas de changement applicatif.

**Portage Linux / WSL**

- `install.sh` vérifie sous Linux/WSL qu'un pinentry graphique est installé (`pinentry-gtk2` ou équivalent). Sans lui, la saisie de la passphrase GPG ne fonctionne pas quand la collecte est lancée depuis la GUI, et la collecte échoue dès le 1er site sans message explicite. Le pré-requis est désormais surfacé à l'installation.
- `install.sh` : progression numérotée `[1/8]`…`[8/8]`, bannière finale étoffée, bloc `ACTION REQUISE` si `python3-uno` doit être ajouté au `PATH`.
- Raccourci de lancement Linux corrigé pour que la GUI voie `python3-uno` au 1er lancement, sans manipulation manuelle du shell.
- README §3 : `sudo apt update` ajouté avant l'install de git (utile sur Linux Mint frais).

**GUI**

- Correction de l'affichage : la status bar (synthèse Contrôles + total Avoirs) était masquée au démarrage et n'apparaissait qu'après redimensionnement manuel de la fenêtre. Désormais visible immédiatement.

**Collecte**

- Société Générale : robustification du décodage du clavier virtuel. Symptôme révélé sur WSL uniquement (sans doute lié à un rendu de polices différent qui pousse l'OCR Tesseract à rater sporadiquement un chiffre). La touche manquante est désormais identifiée par analyse visuelle de fallback (les cases vides du clavier se distinguent du chiffre réel). Évite l'échec « Le chiffre 'X' n'a pas été trouvé dans le clavier » qui imposait de relancer la collecte.

**Documentation**

- `README` § 3 : allégement du tableau prérequis, mention auto-install LO sous Linux/WSL.
- `README` § 10 Vérifications : ajout « Collecte » à la ligne WSL/Ubuntu 22.
- `Compta_site` § 4 : la création initiale d'un site `[FOO]` est manuelle (la GUI n'a pas de point d'entrée « Ajouter site »).



## v5.0.2
| 2026-05-23 | Portage macOS Ventura. |
| ---------- | ------------------------------------------------------------ |

Affinements `install.sh` et doc. Pas de changement applicatif.

**Portage macOS Ventura**

- `install.sh` détecte Ventura (macOS ≤ 13) et bascule sur **MacPorts** pour `python311`, `py311-tkinter`, `py311-pip`, `tesseract` : Homebrew se désengage progressivement de Ventura (plus de *bottle* pour python/tesseract → recompilation source > 1 h). Hints `sudo port install …` et rappels `port select` ajoutés.
- Vérif `pip` réécrite via `$PYTHON -m pip` (et non `pip3` du PATH) — couvre le piège où `port select pip` n'a pas été fait et où `pip3` résout vers le CLT Apple, écrivant dans un mauvais site-packages.
- Détection LO stricte sur Ventura : sweet spot 24.8.x (≥ 25 → Python embedded SIGKILL par Launch Constraints Apple ; < 24.8 → XLOOKUP non mappé). Procédure d'install pointe sur les archives officielles (`downloadarchive.documentfoundation.org`), la page principale ne proposant plus que des versions cassées sur Ventura.
- Sanity check `brew`/`port` au démarrage, fallback `/opt/local/bin/tesseract` (PATH `sudo` minimal), `lo_rename_so` retourne 0 explicitement (évitait l'abandon sous `set -e` quand aucun `.so` n'était à renommer).
- Warn PATH `~/.local/bin` shell-aware via `$SHELL` : `~/.zshrc` (zsh), `~/.bash_profile` (bash sur Mac), `~/.bashrc` (bash sur Linux).

**Documentation**

- `Compta_portage.md` § macOS : tableau prérequis Ventura/Sonoma+ étoffé, procédure LibreOffice 24.8 détaillée (archives, drag-to-Applications, `xattr` + AMFI).
- `Compta_portage.md` § Particularités macOS : réorganisé en deux blocs (1er passage / usage quotidien) avec 4 nouveaux points : popup *Command Line Tools* au 1er `git clone`, piège `pip3` vs `python3 -m pip`, ajout PATH `~/.local/bin` selon shell, association `.md` dans LaunchServices (geste Finder).



## v5.0.1 📘
| 2026-05-22 | Portage Windows, correction GUI (ajout biens matériels), classeurs livrés intégrant la migration v5.0.0. |
| ---------- | ------------------------------------------------------------ |

**Portage Windows**

- **LibreOffice ≥ 24.8 obligatoire** (mapping `_xlfn.XLOOKUP`). La version 24.2.x livrée par défaut sur Ubuntu 24.04 corrompait silencieusement les formules XLOOKUP lors d'une sauvegarde via UNO — touche aussi bien les migrations que les opérations GUI déclenchant un recalc. Garde `inc_uno.require_libreoffice_min` ajoutée pour refuser tout `tool_migrate_*` sur LO < 24.8.
- **Auto-install/upgrade LO sur Linux/WSL** : `install.sh` installe LibreOffice si absent, puis bascule sur le PPA `libreoffice/ppa` si la version installée est < 24.8. Sur macOS, l'installation reste manuelle (cf. `Compta_portage.md`).
- **`wslu`** : détecté par `install.sh` (warning si absent). Sans lui, l'ouverture de docs Markdown depuis la GUI tombait sur le navigateur Windows par défaut au lieu d'une app dédiée.
- **`gui_exec`** : utilise `wslview` au lieu de `xdg-open` sous WSL.

**GUI**

- La devise d'un bien matériel se choisit désormais parmi les devises cotées (avant : `-` verrouillé). Permet d'enregistrer un bien dans la devise réelle de l'opération.
- Exclusion de `-` de `ACCOUNT_DEVISES` (ce n'est pas une vraie devise).

**Classeurs livrés**

- `comptes_template.xlsm` et `comptes_exemple.xlsx` régénérés avec la migration v5.0.0 appliquée — 2 améliorations anti-`#REF!` orphelines intégrées :
  - `Cotations!B{alarme métier}` : wrapper `IFERROR(SUMPRODUCT(...);1)` (capte les `#REF!` résiduels en COTcours).
  - `Contrôles!K{Synthèse}` : wrapper `IFERROR(K{section};"⚠")` sur chaque token (sans ce wrapper, une section en erreur faisait tomber la synthèse à ✓).
- Fixtures TNR (5 `expected.xlsm`) régénérées en cohérence.

**Documentation**

- `README` : prérequis LibreOffice consolidé en une seule mention (toutes plateformes), avec rappel de l'auto-install sur Linux/WSL.
- `Compta_portage.md` : section WSL2 enrichie (post-redémarrage, `wslu`, procédure upgrade LO via PPA).



## v5.0.0 🔧
| 2026-05-19 | Portage macOS, environnement de test (TNR), extensibilité, fiabilisation CRUD devises + alarmes anti-`#REF!`. |
| ---------- | ------------------------------------------------------------ |

**Migration assistée** — `tool_migrate_v5.0.0.py` (idempotent, `SCHEMA_VERSION` inchangé)

**Portage macOS**

- Installation : `install.sh` portable Linux / macOS / WSL, avec gestion dual-Python pour macOS.
- Adaptation de l'architecture d'interface Python / LibreOffice spécifique à macOS.
- Sites OS-dépendants : `Kraken` adapte sa méthode de collecte à la plateforme.
- Documentation portage : `Compta_portage.md` refondue, `README` enrichi.

**TNR (Test de non régression)**

- Ajout d'un environnement de test avec plusieurs scénarios : `roundtrip`, `fast`, `build`, `light_build`, `light_reverse`, `example`, `reverse` — utilisables par tout contributeur pour valider une modification du code.
- Isolation par scénario : chaque TNR tourne dans une sandbox dédiée.
- Documentation : nouveau `Compta_tests.md` (manuel d'utilisation des TNR).

**Fiabilisation devises + alarmes**

- **Suppression d'une devise mère** — refus si une devise dérivée en dépend (par exemple XAU n'est plus supprimable tant qu'OrPr ou OrJo existe). Avant : suppression silencieuse, dérivées laissées avec des `#REF!`.
- **Alarme métier Cotations** : détecte aussi les `#REF!` résiduels en colonne *Cours*, pas seulement les codes sans cours.
- **Synthèse Contrôles** : ne tombe plus à ✓ quand une section est elle-même en erreur.

**Architecture `custom/`**

- Nouveau dossier `custom/` pour les extensions privées (sites perso, monkeypatches) sans modification du code public.
- Nouvel outil `install_custom.sh` qui pose l'arborescence et les squelettes Python.
- Outillage git remanié et distribué : `tool_commit.sh`, `tool_pull.sh` (syntaxe unifiée, détection auto du mode).
- `install_custom.sh` multi-machines pour déployer la même config sur plusieurs postes.
- Documentation : nouveaux `Compta_custom.md` et `Compta_site.md` (ajouter un site, public ou privé), section *Extensibilité* dans `README.md`.

**Divers**

- Fiabilisation `tool_fix_formats` post-v4.1.0 : cohérence E/K en EUR sur sections métaux/crypto/devises, scan headers devise robuste.
- Première installation : tous les sites restent visibles en GUI Configuration même sans `config_accounts.json` initial.
- Documentation développeur : nouveau `Compta_dev.md` (point d'entrée contributeur), `README.md` et `Compta.md` enrichis de liens vers les nouveaux docs.



## v4.1.0 📘 🔧
| 2026-05-08 | Fiabilisation Plus_value et Contrôles — refonte des alarmes. Nouveau document sur les plus-values `Compta_pvl.md`. |
| ---------- | ------------------------------------------------------------ |

**Migration assistée** — oui (`tool_migrate_v4.1.0.py` — `SCHEMA_VERSION` 2 → 3)

> **Note pour le mode classeur** — cette version cumule de nombreuses modifications du classeur (insertions de lignes, recopies de formules, poses de mises en forme conditionnelles, renommages). La migration manuelle est laborieuse. Il est recommandé de **basculer ponctuellement en mode assisté** le temps de la migration : `git clone`, exécuter `tool_migrate_v4.1.0.py`, puis revenir au mode classeur si souhaité. Détails dans `Compta_upgrade_classeur.md`.

**Plus_value**

- **Total par portefeuille** unifié — une seule formule pour tous les portefeuilles, mono ou multi-devises (par exemple un portefeuille à titres EUR + USD + CHF). Le pied est exprimé dans la devise du portefeuille. La conversion de devise des portefeuilles mixtes devient correcte.
- **Date du pied Total** — bug d'écriture (colonne *montant* au lieu de *date*) qui court-circuitait la comparaison entre date du pied et date du dernier #Solde et figeait le *Retenu* sur la mauvaise branche. Trois portefeuilles concernés sur la PROD de référence (PEE, Assurance vie, eToro USD).
- **PVL %** sur les 5 pieds (GRAND TOTAL + 4 totaux de section) — dénominateur incorrect (*sigma + montant actuel*) remplacé par (*montant initial + sigma*). Sur la PROD de référence : ~22 % au lieu de ~14 % sur GRAND TOTAL.
- **Formats des sections métaux / crypto-monnaies / devises** — les colonnes *PVL*, *Montant actuel*, *Montant initial* et *Sigma* basculent en EUR (cohérence avec le modèle EUR documenté dans `Compta_pvl.md`). Avant : devise native (gramme d'or, satoshi, USD selon la ligne).

**Contrôles**

- **Synthèse refondue** — la ligne *Cohérence / Date* devient **Divers** avec 3 sous-lignes : *Date hors période*, *Ventilation Patrimoine*, *Cotations*. Nouvelle ligne **Formules** avec 2 sous-lignes : *Avoirs*, *Plus_value*. La synthèse globale agrège désormais 7 contrôles (au lieu de 6).
- **Alarmes formules** — trois cellules de surveillance (`Plus_value!B3`, `Avoirs!L1`, alarme *Cotations*) deviennent rouges en cas d'erreur de calcul sur les pieds montants (#N/A, #REF!, #DIV/0! …). Erreurs comptées dans la nouvelle ligne *Formules*.
- **Alarme cohérence Patrimoine** — nouveau compteur *Erreurs* en pied de la feuille Patrimoine, détecte les ventilations en écart > 0,5 € sur les 5 sections (par type, sous-type, domiciliation, titulaire, propriété). Alimente la sous-ligne *Ventilation Patrimoine* dans Divers.
- **Alarme métier Cotations** — détecte les devises utilisées sans cours configuré et les codes présents mais sans cours.
- **Bug latent** — la ventilation Patrimoine n'est plus comptée deux fois dans le pied *Divers* (apparaissait seulement en cas d'écart Patrimoine effectif).
- **Mise en forme** — labels en MAJUSCULES (DIVERS, FORMULES, BALANCES, APPARIEMENTS) ; indentation des sous-lignes Balances pour cohérence avec Divers et Formules.

**Documentation**

- Nouveau document **`Compta_pvl.md`** — doctrine plus-value latente : sémantique des colonnes, formule pivot E = K − (H + I), modèle DEV (devise native) vs modèle EUR (selon section), traitement des cessions et de la fiscalité.

**Outil de migration**

- Plus robuste — exécutions répétées sans effet de bord (trois corrections d'idempotence), message d'avertissement parasite supprimé, alarme *Cotations* posée à la bonne ligne quelle que soit la taille de la liste de cotations.
- **Rapport de deltas** affiché en fin d'exécution : valeurs des 5 pieds Plus_value avant / après recalcul. Permet de constater immédiatement quelles valeurs ont bougé.



## v4.0.5
| 2026-04-30 | Polissage GUI + fix_formats — verrouillages, défauts cohérents avec Patrimoine, format devise CTRL1, pied POSTES multi-devise. |
| ---------- | ------------------------------------------------------------ |

GUI

- Création de compte : champ *Devise* verrouillé à la liste existante. Champ *Propriété* en menu *oui / non* verrouillé. Défauts `-` pour *Domiciliation* et *Titulaire* (cohérence avec le tableau Patrimoine). Listes *Type* et *Sous-type* enrichies de l'option `-`.
- Création de bien matériel : mêmes verrouillages et défauts ; option `-` ajoutée à la *Devise* pour les biens non monétisables (immobilier).
- Onglet *Exécution* : grille des sites passe de 4 à 7 colonnes pour gagner de la place verticalement.

`tool_fix_formats`

- Format devise étrangère désormais appliqué aux colonnes montants du tableau de contrôles *CTRL1* (oubli antérieur).
- Gras d'alarme : étendu à 2 cellules d'écart non couvertes par les formats conditionnels (ligne *Écart* du pied POSTES, ligne *Écart* du pied CATÉGORIES colonne *Total euro*).


## v4.0.4
| 2026-04-30 | Robustesse à la 1re utilisation — démarrage propre même sans configuration préalable. |
| ---------- | ------------------------------------------------------------ |

- Fichiers de configuration manquants (`config_accounts`, `config_cotations`, `config_pipeline`, `config_category_mappings`) : créés vides au premier lancement au lieu de faire échouer l'app.
- Site mal configuré (compte attendu absent du classeur) : site désactivé avec un message d'avertissement, au lieu d'un arrêt brutal.
- Dropbox vide : message *« rien à importer »* et arrêt propre, sans charger inutilement les modules d'import.


## v4.0.1
| 2026-04-28 | Polissage v4 — ergonomie GUI, robustesse 1re install, documentation. |
| ---------- | ------------------------------------------------------------ |

- **Barre d'état** détaillée : 6 contrôles individuels en plus de la synthèse.
- **Menu Outils ▾** refondu, bouton **📖 Doc ▴** dédié. Menus et combobox ferment proprement.
- **Crash** → bascule auto sur l'onglet Exécution pour lecture de l'erreur.
- **Catégories** : config patterns créée vide à la 1re exécution si absente. Combobox *Site* dans le dialog d'ajout. Catégorie orpheline → warning détaillé (au lieu de purge silencieuse).
- **Cohérence** : warnings sans jargon, nom convivial du site, plus d'auto-désactivation (warnings symétriques). Classeur ou fichiers de configuration absents → warnings explicites.
-  `tool_fix_formats` : résumé audit / corrections distinct, fixes Plus-value (E/K en devise du portefeuille) et CTRL2 (suffix ▼ ignoré).
- Nouveau **`Compta_charte.md`** ; `CHANGELOG.md` et `Compta_upgrade_classeur.md` allégés.


## v4.0.0 📘 🔧
| 2026-04-27 | Refonte structurelle du classeur, correctifs (app + classeur). |
| ---------- | ------------------------------------------------------------ |

**Migration assistée** — oui (toutes les feuilles)

**Une seule colonne devise par tableau** — Budget *CATÉGORIES* et Contrôles *CTRL2* passent de plusieurs colonnes (une par devise) à une colonne unique où la devise se choisit dans une liste déroulante en en-tête, plus une colonne Total EUR. Cours inversés (1/cours) conservés dans une nouvelle colonne *COTcours2* (Cotations), utile aux formules de conversion EUR → devise.

**Ancres ⚓** — Chaque tableau porte deux ancres ⚓ (début et fin) dans sa 1ʳᵉ colonne. Elles fiabilisent les insertions/suppressions de lignes et les contrôles.

**Charte graphique** — Palette harmonisée (tête beige foncé, pied beige clair, data blanc, gris pour devise étrangère), quadrillage fin beige sur tous les tableaux, trait épais brun en haut des pieds. Patrimoine étendu (4 colonnes d'annotation libre) et nouveau tableau *Conventions*.

**Alarmes uniformisées** — Cellules contrôlées en gras ; fond rouge clair pour ✗, jaune-orange pour ⚠. La synthèse Contrôles s'affiche en un seul symbole global.

**Synthèse alarmes** — 2 contrôles Budget existants désormais remontés dans la synthèse globale (CATÉGORIES) .

**Outils nouveaux** :

- `tool_migrate_schema_v2.py` — migration v3.4 et plus récents
- `tool_audit_formats.py` — audit charte
-  `tool_fix_formats.py --charter` — application charte + alarmes en gras



## v3.5.8 🔧
| 2026-04-19 | Balance non-EUR — correction formule basée sur cours d'époque. |
| ---------- | ------------------------------------------------------------ |

**Migration assistée** — oui (utilisateurs multi-devise)

- Contrôle balances non-EUR : correction formule de calcul — maintenant basée sur cours d'époque au lieu de cours du jour.
- **`tool_migrate_ctrl2_balances.py`** pour mettre à niveau un classeur existant.

## v3.5.7 📘 🔧
| 2026-04-18 | Plus-value en EUR — affichage cohérent et ancrage PVL dynamique. |
| ---------- | ------------------------------------------------------------ |

**Migration assistée** — oui (comptes métaux / crypto / devises)

- Plus-value métaux / crypto / devises : colonnes *PVL* et *Solde* affichées en EUR (cohérent avec les formules, auparavant symbole de la devise du compte).
- Ancrage PVL dynamique — usage détaillé dans `Compta_plus.md` §*Eq. EUR*.
- GUI ajout de compte : champ *Équiv. EUR* obligatoire si devise ≠ EUR et solde initial ≠ 0.
- **`tool_migrate_pvl_ancrage.py`** pour mettre à niveau un classeur existant (valeurs manuelles préservées).

## v3.5.6 📘
| 2026-04-17 | Import & Budget — fixes divers (#Solde double, Total épargne, formules pied). |
| ---------- | ------------------------------------------------------------ |

- Import : deux `#Solde` à dates différentes pour un même compte sont désormais conservés tous les deux (ancrage + relevé final).
- Budget : ajout de plusieurs postes en une fois — Total épargne désormais correct (auparavant seul le premier poste était sommé).
- Classeur vierge : formules de pied Budget (Total hors Changes/Virements, Total épargne, Épargne fixe) désormais en plage auto-extensible.
- Classeur exemple : fond des colonnes devise du tableau CATÉGORIES assorti aux lignes.

## v3.5.5
| 2026-04-17 | Fix cotations — `NameError` lors de la mise à jour des cours. |
| ---------- | ------------------------------------------------------------ |

- Correction `cpt_fetch_quotes.py` : `NameError: name 'cr' is not defined` lors de la mise à jour des cotations.

## v3.5.4 🔧
| 2026-04-17 | Outil migration CTRL2 multi-devise — rattrapage v3.5.2. |
| ---------- | ------------------------------------------------------------ |

**Migration assistée** — oui (utilisateurs multi-devise)

- **`tool_migrate_ctrl2_formulas.py`** pour mettre à niveau les formules CTRL2 sur un classeur existant multi-devise (outil v3.5.2 livré en v3.5.4).
- Documentation de mise à niveau enrichie (rappel modes classeur / assisté, section v3.5.2).

## v3.5.3 📘 🔧
| 2026-04-16 | PVL multi-devise — formules génériques, fix double comptage. |
| ---------- | ------------------------------------------------------------ |

**Migration assistée** — oui (portefeuille non-EUR avec titres autre devise)

- Plus-value : correction du double comptage de cours sur portefeuille non-EUR pivot contenant un titre dans une autre devise.
- Formules PVL génériques : plus de regénération à l'ajout/suppression d'une devise.
- **`tool_migrate_pvl_totals.py`** pour mettre à niveau un classeur existant.

## v3.5.2 📘
| 2026-04-16 | Détection erreur Comptes multi-devises — CTRL2 K/L, formats Opérations exemple. |
| ---------- | ------------------------------------------------------------ |

**Migration assistée** — non (outil livré en v3.5.4).

- Détection d'erreur Comptes : les écarts non-EUR sont désormais remontés dans le tableau de contrôle 2.
- Formats devise (symbole, fond gris) appliqués aux opérations du classeur exemple.
-  **`tool_migrate_ctrl2_formulas.py`** pour mettre à niveau un classeur existant (outil livré en v3.5.4).

## v3.5.1
| 2026-04-15 | Compatibilité Ubuntu 24.04 / WSL2 — install.sh PEP 668, portage Windows 11. |
| ---------- | ------------------------------------------------------------ |

- Installation compatible Ubuntu 24.04 et Windows 11 (WSL2) — correction pip PEP 668.
- Documentation portage Windows 11, raccourci bureau Windows.
- Images README corrigées pour l'export GitHub.

## v3.5.0
| 2026-04-13 | Versionnage — numéro de version, historique, robustesse GUI. |
| ---------- | ------------------------------------------------------------ |

- Numéro de version affiché dans le titre de la fenêtre.
- Historique des versions (ce fichier).
- Correction d'un crash à l'appariement.
- Correction de faux écarts sur les dates Budget lors des comparaisons.
- Meilleure robustesse de la GUI au démarrage (sites, comptes, exceptions).
- Documentation alignée entre les installations (README, Changelog, guides).

## v3.4.0
| 2026-04-10 | Documentation — mise à jour. |
| ---------- | ------------------------------------------------------------ |

- Documentation mise à jour

## v3.3.0 📘 🔧
| 2026-04-08 | Refonte CTRL1 — multi-soldes par compte, cohérence GUI, corrections collecte/import. |
| ---------- | ------------------------------------------------------------ |

**Migration assistée** — oui (obsolète — voir §v4 via template + réimport)

- Refonte des contrôles de solde (CTRL1) : gestion de plusieurs soldes par compte
- Colonnes Famille et Décimales ajoutées aux Cotations
- Vérification de cohérence automatique au démarrage de la GUI
- Corrections collecte : NATIXIS, ETORO, BOURSOBANK
- Corrections import : dates, dédoublonnage Wise, appariement multi-devises
- **`tool_migrate_ctrl1.py`** pour porter le tableau CTRL1 d'un classeur v3.2 vers la nouvelle structure.

## v3.2.0
| 2026-04-01 | Colonnes dynamiques + Module Budget GUI — installateur Linux, doc complète. |
| ---------- | ------------------------------------------------------------ |

- Colonnes du classeur résolues dynamiquement (insertion/suppression de colonnes sans casser les scripts).
- Configuration centralisée dans config.ini.
- Outil de déploiement et de livraison (commit, tag, export, push).
- Documentation complète générée (Compta.md, guides utilisateur).
- Installateur Linux (.desktop, support Zorin).
- Module Budget ajouté à la GUI.
- Dialogue de réinitialisation du classeur.

## Versions majeures

- v4 : **classeur** restructuré avec charte graphique
- v3 : **GUI ** et version **Export** avec exemple et template.
- v2 : **Collecte sites**  (première pierre app le 11 nov 2025)
- v1 : **Classeur** initial 
