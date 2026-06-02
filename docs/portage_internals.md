# Portage — détails dev (`portage_internals.md`)

Doc dev complémentaire à [`Compta_portage.md`](../Compta_portage.md) (utilisateur). Décrit les choix architecturaux et particularités techniques du portage macOS, et leur extension future (WSL2, Sonoma+, autres OS).

Audience : contributeur, mainteneur, dev d'un portage ultérieur.

## Glossaire

- **UNO** — Universal Network Objects, framework de composants LibreOffice qui permet à un script Python de piloter Calc (cellules, formules, named ranges, styles) comme s'il manipulait des objets locaux.
- **`python3-uno`** — wrapper bash installé par `install.sh` dans `~/.local/bin/`. Abstrait la différence d'OS pour le shebang : Linux → `exec python3` (système), Mac → `exec /Applications/LibreOffice.app/Contents/Resources/python`.
- **Shebang `#!/usr/bin/env python3-uno`** — ligne en tête de script qui force l'interpréteur capable de `import uno`.
- **HeadlessGUI** — classe Python (dans `tool_gui_cli.py`) qui hérite des mixins `gui_*.py` sans tkinter. Expose les CRUD du classeur en API Python pure.
- **Daemon** — invocation `python3-uno tool_gui_cli.py xlsm daemon` qui démarre un process long-vivant lisant des requêtes JSON sur stdin et répondant sur stdout. Évite de re-payer le démarrage Python + LO à chaque op.
- **Batch (UNO)** — session `UnoDocument` ouverte sur le xlsm, maintenue vivante pendant plusieurs ops successives. Le daemon en garde un seul, lazy au 1ᵉʳ appel.
- **In-process** — exécution dans le même process Python que le caller, par opposition à `subprocess` qui spawn un nouveau process.
- **Cold start** — temps d'initialisation d'un process avant qu'il soit utilisable. Sur Mac, le démarrage de `soffice --headless` prend ~5–6 s.

## Architecture wrapper `python3-uno`

Source de vérité unique pour le dispatch OS. Le wrapper bash est déposé par `install.sh` dans `~/.local/bin/python3-uno` :

```bash
#!/bin/bash
case "$(uname -s)" in
  Darwin) exec /Applications/LibreOffice.app/Contents/Resources/python "$@" ;;
  *)      exec python3 "$@" ;;
esac
```

Utilisé via shebang `#!/usr/bin/env python3-uno` sur les scripts qui ont besoin du module `uno` ET dont les deps sont dispos dans LO Python embedded.

Sites migrés : `tool_controles.py`, `tool_fix_formats.py`, `tests/tnr_roundtrip.py`, `cpt_fetch_quotes.py`, `cpt_update.py`, `tool_refs.py`. Extensible script par script.

**Effet PATH** : le launcher .app Mac exporte `~/.local/bin` ET `/opt/local/bin` (tesseract MacPorts) — sinon le PATH lancé depuis Dock est minimal.

**Subprocess avec shebang fire** : pour qu'un shebang `python3-uno` s'applique, l'invocation subprocess doit être `[str(script_path)]` et non `[sys.executable, str(script_path)]` (qui court-circuite le shebang). Doctrine appliquée à toutes les invocations GUI → script UNO.

## Tk vs uno sur Mac — incompatibilité fondamentale

Sur Linux, le system Python peut `import uno` directement (paquet `python3-uno` = module C compilé in-process). Sur Mac, le module `uno` n'est livré que dans le Python embarqué de `LibreOffice.app` ; le system Python (celui qui a `tkinter`) **ne peut pas l'importer**. Et le Python embarqué LO n'a **pas** `tkinter`.

**Conséquence GUI** : `cpt_gui.py` (Tk) doit tourner sur le system Python pour avoir Tk → il ne peut pas appeler UNO en in-process sur Mac. Tous les onglets CRUD qui faisaient `with UnoDocument(...) as doc:` en direct (Comptes, Devises, Catégories, Budget) cassaient en `ImportError`.

**Résolution** : daemon `tool_gui_cli.py` lancé en subprocess persistant sous `python3-uno`, dialogue avec la GUI Tk via JSON RPC line-based sur stdin/stdout. Voir section *Topologie process*.

## Transport UNO — appel C vs round-trip socket

Le module `uno` exporte le même graphe d'objets sur les 2 OS (Document, Sheet, Cell, NamedRange…) mais le **transport** sous-jacent diffère :

| OS | Transport Python ↔ soffice | Coût par appel UNO atomique |
|---|---|---:|
| Linux | module C natif (`uno.so` lié à `libuno_*`), appels in-process | ~quelques μs |
| Mac | bridge socket TCP local sur port 2002 (`--accept=socket,...;urp;`), sérialisation URP | ~0.1–1 ms |

Sur Mac, **chaque `cell.getValue()` = 1 round-trip TCP**. Plus un script est « bavard » (boucle cellule par cellule), plus l'écart se creuse linéairement. C'est inhérent à l'architecture sandbox/signing macOS — LO est un bundle isolé avec son propre runtime Python, Apple ne permet pas qu'un Python système charge ses `.dylib` UNO directement.

Le **mode batch** (UNO session unique pour N ops) amortit le cold start LO mais **n'attaque pas le coût round-trip** — chaque appel UNO atomique intra-batch reste un round-trip. Le daemon hérite donc des perfs Mac.

**Atténuations possibles** (non attaquées dans ce portage) :
- Batching API Range (1 round-trip pour N cellules) — gain potentiel 10×→2-3×
- Mode léger par défaut sur Mac
- Warning préventif GUI pour les ops dense scan

## Topologie process

**GUI Linux** (chemin in-process direct) :

```
┌──────────────────────────────────────────────┐
│  cpt_gui.py  (system python3)               │
│    ├─ tkinter (UI Tk) ✓                     │
│    └─ import uno ✓                          │
│         └─ in-process calls (μs)            │
└──────────────────┬───────────────────────────┘
                   │  fonction C
                   ▼
┌──────────────────────────────────────────────┐
│  libreoffice (process)                       │
│  - lit/écrit comptes.xlsm                    │
└──────────────────────────────────────────────┘
```

→ 1 process Python + 1 process LO. Pas de subprocess intermédiaire.

**GUI Mac** (chemin daemon JSON RPC) :

```
┌──────────────────────────────────────────────┐
│  cpt_gui.py  (system python3)               │
│    ├─ tkinter (UI Tk) ✓                     │
│    └─ import uno ✗  → HAS_UNO=False         │
│    Thread main UI + Thread "exec"           │
│        │                                     │
│        │  stdin/stdout JSON line-based      │
│        ▼                                     │
└──────────────────────────────────────────────┘
                   │  subprocess.Popen
                   │  ({method, kwargs}/{ok, result, stdout})
                   ▼
┌──────────────────────────────────────────────┐
│  tool_gui_cli.py daemon                     │
│  (LO embedded python3-uno, persistant)      │
│    └─ import uno ✓                          │
│    Thread JSON loop sys.stdin → dispatch    │
│        │                                     │
│        │  UNO bridge URP                    │
│        ▼  socket TCP localhost:2002         │
└──────────────────────────────────────────────┘
                   │  round-trip socket par appel atomique
                   ▼
┌──────────────────────────────────────────────┐
│  soffice --headless --accept=socket,...     │
└──────────────────────────────────────────────┘
```

→ 3 process : cpt_gui (Tk), tool_gui_cli (daemon), soffice. Le daemon et soffice sont spawned lazy au 1ᵉʳ CRUD, persistent jusqu'à fermeture GUI.

**Subprocess Mac classique** (Fetch, Cotations, Push) :

```
cpt_gui.py → spawn `python3-uno cpt_fetch_X.py xlsm`
              (process éphémère, 1 par clic, cold start ~5–6 s)
              └─ spawn soffice → bridge URP socket → ...
              ↑ termine après l'op
```

## Cinq chemins effectifs vers UNO

| Chemin | Process Python | Usage |
|---|---|---|
| A. `HeadlessGUI` importé direct | hôte (TNR, smoke test) | TNR, CLI admin |
| B. `tool_gui_cli.py xlsm add-X ...` (one-shot CLI) | nouveau par appel | admin manuel |
| C. Daemon JSON RPC line-based | process persistant | GUI Mac (Devises/Comptes/Catégories) |
| D. Scripts UNO autonomes (`cpt_fetch_quotes`…) | nouveau par invocation | GUI Mac+Linux (Fetch/Import…), CLI |
| E. `import uno` in-process direct depuis `cpt_gui.py` | system Python | GUI Linux uniquement (Mac → impossible) |

Sur Mac : A (sous `python3-uno`), B, C, D actifs. Chemin E impossible → remplacé par C pour les CRUD GUI. Sur Linux : tous actifs ; le dispatch `HAS_UNO=True` côté `gui_*` choisit in-process E.

## Performance comparée TNR (Mac Ventura Intel vs Linux DEV)

| TNR | Linux in-process | Mac in-process | Linux daemon | Mac daemon | Ratio Mac/Linux |
|---|---:|---:|---:|---:|---:|
| `roundtrip` (baseline) | 7s | 10s | — | — | 1.4× |
| `fast` | 21s | 34s | 15s | 31s | 1.6× |
| `light_build` | 8s | 17s | — | — | 2.1× |
| `light_reverse` | 26s | 40s | 27s | 29s | 1.5× |
| `build` | 48s | 113s | — | — | 2.4× |
| `reverse` | 105s | 159s | 69s | 122s | 1.5× |

Daemon plus rapide qu'in-process malgré `_FLUSH_AFTER` (cf. *Limites* infra) : ~25 % Mac, ~34 % Linux sur `reverse`. Cohérent avec la doctrine bridge in-process C natif (Linux) vs socket TCP (Mac).

## Dual-Python sur macOS

Sur Mac, deux interpréteurs Python distincts cohabitent — conséquence du fait que **Tk et `uno` sont mutuellement exclusifs dans un même Python** (cf. supra). `install.sh` installe automatiquement les dépendances requises dans chacun :

| Python | Chemin | Scripts ciblés (shebang) | Deps installées |
|---|---|---|---|
| Système | `/Library/Frameworks/Python.framework/...` | `#!/usr/bin/env python3` (cpt_gui, fetchers Playwright…) | `requirements.txt` (playwright, openpyxl, pdfplumber, pytesseract, Pillow, requests…) |
| LO embarqué | `/Applications/LibreOffice.app/Contents/Resources/python` (3.9) | `#!/usr/bin/env python3-uno` (cpt_update, cpt_fetch_quotes, tool_refs, tool_controles, tool_fix_formats) | `openpyxl`, `requests`, `pdfplumber` |

Certaines deps sont en double (openpyxl/requests/pdfplumber dans les deux environnements).

### `lo_rename_so()` — extensions binaires

Une fonction `lo_rename_so()` dans `install.sh` renomme automatiquement les extensions binaires post-pip du LO embarqué : `pip` Mac écrit en suffix `cpython-39-darwin.so` mais le Python LO 3.9 attend `cpython-3.9.so` (cf. `EXTENSION_SUFFIXES`). Sans ce rename, `cffi`/`cryptography`/`pdfplumber` sont physiquement présents mais invisibles à l'import. Idempotent — réappliquée à chaque réinstall.

## LibreOffice Mac — diagnostic versions

| Versions | Verdict Ventura | Raison |
|---|---|---|
| 7.x | ❌ #NAMES? CTRL1 | `_xlfn.XLOOKUP` non mappé |
| 24.2.x | ❌ #NAMES? CTRL1 | mapping `_xlfn.` introduit après 24.2 |
| **24.8.x** | **✅ sweet spot** | XLOOKUP mappé + pas de Launch Constraints + Python 3.9 |
| 25.x+ | ❌ wrapper KO sur Ventura | Apple Launch Constraints → Python embedded SIGKILL |

Sur Sonoma+ : LO 25.x+ pourrait fonctionner (Launch Constraints honorées différemment) — à confirmer.

**Procédure post-DMG** :

```bash
sudo xattr -dr com.apple.quarantine /Applications/LibreOffice.app   # 1. Gatekeeper
open /Applications/LibreOffice.app && sleep 2 \
  && osascript -e 'quit app "LibreOffice"'                          # 2. AMFI
/Applications/LibreOffice.app/Contents/Resources/python -m pip install openpyxl requests pdfplumber  # 3. deps
```

`install.sh` détecte la version installée et émet un warning si < 24 ou si le Python embedded n'est pas lançable.

## Conventions macOS

- **Bash 3.2** (système Mac) — helpers `to_lower` / `to_upper_first` / `sed_inplace` dans les scripts shell installés pour combler les manques vis-à-vis de bash 4+.
- **MacPorts pour Ventura** — bottles Homebrew indisponibles pour certains paquets (Tesseract). Sonoma+ peut rester sur Homebrew. Les deux coexistent (`/opt/local/` vs `/usr/local/` ou `/opt/homebrew/`).
- **Piège sudo PATH** — `sudo` réinitialise via `secure_path`, n'hérite pas du PATH utilisateur. Toujours chemin absolu : `sudo /opt/local/bin/port install ...`.
- **Clipboard** — `pyperclip` natif (utilise `pbcopy`/`pbpaste`) — pas de dépendance `xclip`.
- **Détection processus soffice** — `pgrep -x soffice.bin` (le process s'appelle bien `soffice.bin` sur Mac, comme sur Linux).

## Couverture fonctionnelle et limites

### Couverture au merge `portage-mac → main`

| Niveau | Couvert |
|---|---|
| Architecture daemon serveur + client câblé GUI Mac | ✅ Devises + Comptes + Catégories |
| Dispatch `HAS_UNO` partagé Linux/Mac | ✅ 18 sites GUI |
| Migration shebang `python3-uno` scripts orchestration | ✅ `cpt_update`, `tool_refs`, `cpt_fetch_quotes`, `tool_controles`, `tnr_*` |
| TNR PUB exécutables Mac+Linux | ✅ 5/5 |
| TNR validés via chemin daemon (DaemonGUI) | ✅ 3/5 (`fast`, `light_reverse`, `reverse`) |
| TNR in-process only | ⚠️ 2/5 (`light_build`, `build`) — UNO direct sur `doc` non proxyable |

### Limites architecturales identifiées

**Workers non batch-friendly** — le mode batch daemon expose une doctrine implicite : pour qu'une méthode publique soit utilisable en batch, elle doit (a) accepter `doc=None`, (b) forwarder au worker, (c) le worker doit utiliser `owned/nullcontext`, (d) ne pas dépendre d'attributs Python cachés qui ne sont rafraîchis qu'en mode non-batch. Le point (d) est partiellement contourné par `_FLUSH_AFTER` plutôt que résolu à la racine.

**`_FLUSH_AFTER` — workaround pragmatique** — `DaemonGUI` force un `__flush__` (save + close batch + reload state) après `purge_account` et `delete_account`. Effet : on défait partiellement le bénéfice batch (8 cycles open/close au lieu d'un seul pour `tnr_reverse` daemon), mais le gain net reste positif vs in-process car on évite le redémarrage Python LO entre ops.

**Coverage 3/5 daemon** — `tnr_light_build` et `tnr_build` utilisent des manipulations UNO directes sur le `doc` du batch (`ws_cot.getCellByPosition`, `doc.cr.refresh`) qu'on ne peut pas proxier via JSON RPC. Restent in-process only. Décision acceptée comme limite du périmètre.

## Bilan portage

### Volume code

35 commits sur la branche `portage-mac` depuis `main` :

| Catégorie | Fichiers | +Insertions | -Suppressions |
|---|---:|---:|---:|
| Code Python applicatif | 26 | 1 700+ | 600+ |
| TNR (pilotes + scénarios) | 17 | 1 200+ | 90 |
| Shell installs + journal | 7 | 900+ | 100 |
| **Total** | 50 | ~3 800 | ~790 |

Top fichiers : `cpt_gui.py` (refactor extraction modules neutres), `tool_gui_cli.py` (daemon + DaemonGUI), `gui_accounts.py` (dispatch 9 sites + 4 workers refactorés), `inc_compta_schema.py` (nouveau, extrait), `gui_categories.py` (dispatch 7 sites), `gui_daemon.py` (nouveau, DaemonClientMixin + DaemonGUI), `inc_config_io.py` (nouveau).

### Ce qui a facilité le portage

Malgré une transformation conséquente (~1 800 lignes de vrai code applicatif), 5 facteurs ont permis un portage relativement léger :

- Architecture mixin déjà en place → injection de `DaemonClientMixin` et `CategoriesMixin` en 1 ligne d'héritage.
- Workers déjà séparés des handlers UI → proxying mécanique, pas de réécriture de logique métier.
- Pattern `owned`/`nullcontext` déjà inventé pour `_save_devise` et `_save_accounts` → extension naturelle aux workers manquants.
- `HAS_UNO` global propre → un seul signal pour orienter tous les chemins, pas de polymorphisme à introduire.
- Infrastructure TNR (sandbox + reference) portable telle quelle.

### Bugs latents exposés

7 régressions ou anti-patterns du code original mis au jour par les TNR Mac (aucun introduit par le portage lui-même) :

1. **CTRL2 cache stale** dans `_save_accounts` — `cr.rows('CTRL2type')` lit cache pré-insert. Fix `cr.refresh()` avant lecture.
2. **Pré-écriture JSON dialog devise** — `cotations_meta[code]` écrit avant l'appel daemon → daemon voit duplicate → skip silencieux. Fix : suppression pré-écriture.
3. **`cr` référencé avant `doc`** dans `_rename_pv_title` / `_delete_pv_title` — NameError hors batch. Fix : `cr = doc.cr` dans le `with`.
4. **Chaîne pdfplumber Mac** — pip écrit `.so` en suffix `cpython-39-darwin.so` invisible à LO Python 3.9. Fix : `lo_rename_so()` dans install.sh + chargement défensif + `cpt_update` lazy-load.
5. **Doctrine `doc=` inégalement appliquée** — 5 méthodes (`delete_category`, `delete_poste`, `delete_devise`, `cleanup_patrimoine`) ne forwardaient pas `doc=` → conflit double `UnoDocument` en batch. Fix : ajout `doc=None` + forward.
6. **State caching attributs Python** — `self._end_avr`, `self._start_avr` chargés une fois par `_load_excel_data`, jamais rafraîchis pendant un batch. Workaround `_FLUSH_AFTER` ; vrai fix architectural à porter aux workers.
7. **Drift schema template `tnr_light_build`** — expected.xlsm généré avant un row-shift fix.

### Recommandations post-merge

Par ordre de priorité décroissante :

1. **Workers batch-friendly** — propager la lecture live des bornes UNO à `_save_accounts` et workers similaires. Supprime le besoin de `_FLUSH_AFTER`, libère le bénéfice batch complet, fixe structurellement les bugs #1 et #6.
2. **Régénérer `tnr_light_build` expected.xlsm** après le fix #1 généralisé.
3. **Smoke GUI manuels Mac** pour les onglets Comptes et Catégories (test interactif des 14 boutons CRUD).
4. **Pattern `binary_install_hint(name)` factorisé** (cosmétique) — aujourd'hui `tesseract_install_hint()` ad-hoc. À factoriser pour d'autres binaires externes (gpg, soffice…).

## Risques WSL2 anticipés (non testés en profondeur)

| Sévérité | Sujet | Note |
|---|---|---|
| Haute | Clipboard pyperclip via xclip (WSLg Win 11) | Vérifier xclip post-install |
| Haute | GUI Tk (WSLg Win 11 OK ; Win 10 = X server tiers) | Scope Win 10 à confirmer |
| Moyenne | Retry UNO 12×1s | Premier soffice lent en VM |
| Moyenne | Compta sous /mnt/c (I/O cross-FS) | Best : `~/` côté WSL ext4 |
| Basse | Line endings CRLF | `.gitattributes : * text=auto eol=lf` |
