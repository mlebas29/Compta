# Changelog

Chronique des versions de l'app, orientée utilisateur. Les changements internes du code ne sont généralement pas listés.

## v4.0.1
| 2026-04-28           |                                                              |
| -------------------- | ------------------------------------------------------------ |
| Description          | **Polissage v4** — ergonomie GUI, robustesse 1re install, documentation. |
| Mise à jour classeur | non (app + docs uniquement)                                  |

- **Barre d'état** détaillée : 6 contrôles individuels en plus de la synthèse.
- **Menu Outils ▾** refondu, bouton **📖 Doc ▴** dédié. Menus et combobox ferment proprement.
- **Crash** → bascule auto sur l'onglet Exécution pour lecture de l'erreur.
- **Catégories** : config patterns créée vide à la 1re exécution si absente. Combobox *Site* dans le dialog d'ajout. Catégorie orpheline → warning détaillé (au lieu de purge silencieuse).
- **Cohérence** : warnings sans jargon, nom convivial du site, plus d'auto-désactivation (warnings symétriques). Classeur ou fichiers de configuration absents → warnings explicites.
- 🔧 `tool_fix_formats` : résumé audit / corrections distinct, fixes Plus-value (E/K en devise du portefeuille) et CTRL2 (suffix ▼ ignoré).
- Nouveau **`Compta_charte.md`** ; `CHANGELOG.md` et `Compta_upgrade.md` allégés.


## v4.0.0
| 2026-04-27           |                                                              |
| -------------------- | ------------------------------------------------------------ |
| Description          | **Refonte v4** — refonte structurelle du classeur, correctifs (app + classeur). |
| Mise à jour classeur | oui (toutes les feuilles) — voir Compta_upgrade.md           |

**Une seule colonne devise par tableau** — Budget *CATÉGORIES* et Contrôles *CTRL2* passent de plusieurs colonnes (une par devise) à une colonne unique où la devise se choisit dans une liste déroulante en en-tête, plus une colonne Total EUR. Cours inversés (1/cours) conservés dans une nouvelle colonne *COTcours2* (Cotations), utile aux formules de conversion EUR → devise.

**Ancres ⚓** — Chaque tableau porte deux ancres ⚓ (début et fin) dans sa 1ʳᵉ colonne. Elles fiabilisent les insertions/suppressions de lignes et les contrôles.

**Charte graphique** — Palette harmonisée (tête beige foncé, pied beige clair, data blanc, gris pour devise étrangère), quadrillage fin beige sur tous les tableaux, trait épais brun en haut des pieds. Patrimoine étendu (4 colonnes d'annotation libre) et nouveau tableau *Conventions*.

**Alarmes uniformisées** — Cellules contrôlées en gras ; fond rouge clair pour ✗, jaune-orange pour ⚠. La synthèse Contrôles s'affiche en un seul symbole global.

**Synthèse alarmes** — 2 contrôles Budget existants désormais remontés dans la synthèse globale (CATÉGORIES) .

**Outils nouveaux** :

- 🔧 `tool_migrate_schema_v2.py` — migration v3.4 et plus récents
- 🔧 `tool_audit_formats.py` — audit charte
- 🔧 `tool_fix_formats.py --charter` — application charte + alarmes en gras



## v3.5.8
| 2026-04-19           |                                                              |
| -------------------- | ------------------------------------------------------------ |
| Description          | **Balance non-EUR** — correction formule basée sur cours d'époque. |
| Mise à jour classeur | oui (utilisateurs multi-devise)                              |

- Contrôle balances non-EUR : correction formule de calcul — maintenant basée sur cours d'époque au lieu de cours du jour.
- 🔧 **`tool_migrate_ctrl2_balances.py`** pour mettre à niveau un classeur existant.

## v3.5.7
| 2026-04-18           |                                                              |
| -------------------- | ------------------------------------------------------------ |
| Description          | **Plus-value en EUR** — affichage cohérent et ancrage PVL dynamique. |
| Mise à jour classeur | oui (comptes métaux / crypto / devises)                      |

- Plus-value métaux / crypto / devises : colonnes *PVL* et *Solde* affichées en EUR (cohérent avec les formules, auparavant symbole de la devise du compte).
- Ancrage PVL dynamique — usage détaillé dans `Compta_plus.md` §*Eq. EUR*.
- GUI ajout de compte : champ *Équiv. EUR* obligatoire si devise ≠ EUR et solde initial ≠ 0.
- 🔧 **`tool_migrate_pvl_ancrage.py`** pour mettre à niveau un classeur existant (valeurs manuelles préservées).

## v3.5.6
| 2026-04-17           |                                                              |
| -------------------- | ------------------------------------------------------------ |
| Description          | **Import & Budget** — fixes divers (#Solde double, Total épargne, formules pied). |
| Mise à jour classeur | non (changements limités au classeur vierge et à l'exemple)  |

- Import : deux `#Solde` à dates différentes pour un même compte sont désormais conservés tous les deux (ancrage + relevé final).
- Budget : ajout de plusieurs postes en une fois — Total épargne désormais correct (auparavant seul le premier poste était sommé).
- Classeur vierge : formules de pied Budget (Total hors Changes/Virements, Total épargne, Épargne fixe) désormais en plage auto-extensible.
- Classeur exemple : fond des colonnes devise du tableau CATÉGORIES assorti aux lignes.

## v3.5.5
| 2026-04-17           |                                                              |
| -------------------- | ------------------------------------------------------------ |
| Description          | **Fix cotations** — `NameError` lors de la mise à jour des cours. |
| Mise à jour classeur | non (fix app uniquement)                                     |

- Correction `cpt_fetch_quotes.py` : `NameError: name 'cr' is not defined` lors de la mise à jour des cotations.

## v3.5.4
| 2026-04-17           |                                                              |
| -------------------- | ------------------------------------------------------------ |
| Description          | **Outil migration CTRL2 multi-devise** — rattrapage v3.5.2.  |
| Mise à jour classeur | oui (utilisateurs multi-devise)                              |

- 🔧 **`tool_migrate_ctrl2_formulas.py`** pour mettre à niveau les formules CTRL2 sur un classeur existant multi-devise (outil v3.5.2 livré en v3.5.4).
- Documentation de mise à niveau enrichie (rappel modes classeur / assisté, section v3.5.2).

## v3.5.3
| 2026-04-16           |                                                              |
| -------------------- | ------------------------------------------------------------ |
| Description          | **PVL multi-devise** — formules génériques, fix double comptage. |
| Mise à jour classeur | oui (portefeuille non-EUR avec titres autre devise)          |

- Plus-value : correction du double comptage de cours sur portefeuille non-EUR pivot contenant un titre dans une autre devise.
- Formules PVL génériques : plus de regénération à l'ajout/suppression d'une devise.
- 🔧 **`tool_migrate_pvl_totals.py`** pour mettre à niveau un classeur existant.

## v3.5.2
| 2026-04-16           |                                                              |
| -------------------- | ------------------------------------------------------------ |
| Description          | **Détection erreur Comptes multi-devises** — CTRL2 K/L, formats Opérations exemple. |
| Mise à jour classeur | non (migration livrée en v3.5.4)                             |

- Détection d'erreur Comptes : les écarts non-EUR sont désormais remontés dans le tableau de contrôle 2.
- Formats devise (symbole, fond gris) appliqués aux opérations du classeur exemple.
- 🔧 **`tool_migrate_ctrl2_formulas.py`** pour mettre à niveau un classeur existant (outil livré en v3.5.4).

## v3.5.1
| 2026-04-15           |                                                              |
| -------------------- | ------------------------------------------------------------ |
| Description          | **Compatibilité Ubuntu 24.04 / WSL2** — install.sh PEP 668, portage Windows 11. |
| Mise à jour classeur | non (installation / docs)                                    |

- Installation compatible Ubuntu 24.04 et Windows 11 (WSL2) — correction pip PEP 668.
- Documentation portage Windows 11, raccourci bureau Windows.
- Images README corrigées pour l'export GitHub.

## v3.5.0
| 2026-04-13           |                                                              |
| -------------------- | ------------------------------------------------------------ |
| Description          | **Versionnage** — numéro de version, historique, robustesse GUI. |
| Mise à jour classeur | non (app uniquement)                                         |

- Numéro de version affiché dans le titre de la fenêtre.
- Historique des versions (ce fichier).
- Correction d'un crash à l'appariement.
- Correction de faux écarts sur les dates Budget lors des comparaisons.
- Meilleure robustesse de la GUI au démarrage (sites, comptes, exceptions).
- Documentation alignée entre les installations (README, Changelog, guides).

## v3.4.0
| 2026-04-10           |                                                              |
| -------------------- | ------------------------------------------------------------ |
| Description          | **Documentation** — mise à jour.                             |
| Mise à jour classeur | non (documentation uniquement)                               |

- Documentation mise à jour

## v3.3.0
| 2026-04-08           |                                                              |
| -------------------- | ------------------------------------------------------------ |
| Description          | **Refonte CTRL1** — multi-soldes par compte, cohérence GUI, corrections collecte/import. |
| Mise à jour classeur | oui (passage v3.2 → v3.3, tableau CTRL1)                     |

- Refonte des contrôles de solde (CTRL1) : gestion de plusieurs soldes par compte
- Colonnes Famille et Décimales ajoutées aux Cotations
- Vérification de cohérence automatique au démarrage de la GUI
- Corrections collecte : NATIXIS, ETORO, BOURSOBANK
- Corrections import : dates, dédoublonnage Wise, appariement multi-devises
- 🔧 **`tool_migrate_ctrl1.py`** pour porter le tableau CTRL1 d'un classeur v3.2 vers la nouvelle structure.

## v3.2.0
| 2026-04-01           |                                                              |
| -------------------- | ------------------------------------------------------------ |
| Description          | **Colonnes dynamiques + Module Budget GUI** — installateur Linux, doc complète. |
| Mise à jour classeur | non (module Budget greffé via la GUI sur classeur existant)  |

- Colonnes du classeur résolues dynamiquement (insertion/suppression de colonnes sans casser les scripts).
- Configuration centralisée dans config.ini.
- Outil de déploiement et de livraison (commit, tag, export, push).
- Documentation complète générée (Compta.md, guides utilisateur).
- Installateur Linux (.desktop, support Zorin).
- Module Budget ajouté à la GUI.
- Dialogue de réinitialisation du classeur.

## Jalons antérieurs

- v3 : **14 sites intégrés**, **GUI complète** et publication Export avec exemple et template.
- v2 : **sites intégrés**  (2025-11-11 première pierre app)
- v1 : classeur familial 
