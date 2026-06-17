# Compta — Portage sur d'autres OS

L'application est développée sous **Linux Ubuntu 22.04+** et dérivés (Zorin, Mint).
Elle a été portée et validée sur **macOS** (Ventura Intel) et fonctionne sous **Windows 11 via WSL2**.
Ce document décrit les prérequis et particularités de chaque plateforme.

## Linux (référence)

Plateforme de développement.

| Élément | Version testée |
|---|---|
| Distribution | Ubuntu 22.04 / 24.04 et dérivés (Zorin, Mint) |
| LibreOffice | **≥ 24.8.x** (installé/mis à niveau automatiquement par `install.sh`) |
| Python | 3.10+ (système) |
| Bridge UNO | `python3-uno` natif (paquet `apt`) |

Installation : `./install.sh` depuis le répertoire cloné. Le script installe automatiquement LibreOffice (et l'upgrade via le PPA `libreoffice/ppa` si la version disponible est < 24.8), et indique la commande d'installation de package correspondante pour les autres prérequis manquants.

## macOS

**Cible officielle : Sonoma 14+** (Apple Silicon ou Intel récent).
**Validé en pratique : Ventura 13.7 Intel** (MBP 14,3 2017 bloqué à Ventura par Apple).
Sonoma+ : architecture identique, mais non testé en l'état — pourrait permettre LibreOffice 25.x.

### Prérequis

| Composant | Source Ventura | Source Sonoma+ | Notes |
|---|---|---|---|
| **Homebrew** | https://brew.sh — pour `gnupg` et `libreoffice` cask | https://brew.sh — pour tout | Gestionnaire macOS standard |
| **MacPorts** | https://macports.org — pour `python311`, `py311-tkinter`, `py311-pip`, `tesseract` | non requis | Maintenu sur Ventura, ses bottles existent encore |
| **LibreOffice** | DMG officiel **24.8.x** | DMG officiel **24.8.x** | Voir tableau versions plus bas |
| **Tesseract** | MacPorts (`tesseract` + langues) | Homebrew (`tesseract`) | OCR pour 2FA Société Générale |
| **Python 3.10+** | MacPorts (`python311`) | Homebrew (`python`) | Interpréteur applicatif |

### Pourquoi MacPorts sur Ventura

Homebrew se désengage progressivement de Ventura : `brew install python` et `brew install tesseract` ne trouvent plus de *bottle* (binaire pré-compilé) pour macOS 13.x x86_64 et retombent sur une compilation source qui dépasse l'heure. MacPorts reste maintenu sur Ventura et fournit `python311` et `tesseract` en binaire (`/opt/local/`). Les deux gestionnaires coexistent sans conflit avec `/usr/local/` ou `/opt/homebrew/`.

Sur Sonoma+, Homebrew redevient suffisant pour tout — MacPorts n'est plus nécessaire.

### LibreOffice — versions

Le bridge UNO est sensible à la version LibreOffice :

| Version | Verdict Ventura | Raison |
|---|---|---|
| 7.x | ❌ `#NAMES?` sur CTRL1 | `_xlfn.XLOOKUP` non mappé |
| 24.2.x | ❌ `#NAMES?` sur CTRL1 | mapping `_xlfn.` introduit après 24.2 |
| **24.8.x** | ✅ **sweet spot** | XLOOKUP mappé + Python embedded lançable + Python 3.9 |
| 25.x+ | ❌ Python embedded SIGKILL | Apple *Launch Constraints* sur Ventura |

Sur **Sonoma+** : LO 25.x+ pourrait fonctionner (Launch Constraints honorées différemment) — à confirmer.

### Installation

**1. LibreOffice 24.8.x**

   a. Télécharger le DMG depuis les archives officielles (la page principale ne propose plus
      que Fresh 26.x et Still 25.x, tous deux cassés sur Ventura) :
      https://downloadarchive.documentfoundation.org/libreoffice/old/
      → naviguer vers le dossier de la dernière 24.8.x (ex. `24.8.7.2/`)
      → puis `mac/x86_64/`
      → télécharger `LibreOffice_X.Y.Z.W_MacOS_x86-64.dmg` (~320 Mo)
   b. Double-clic sur le `.dmg` → glisser `LibreOffice.app` dans `/Applications`
   c. Lever Gatekeeper + déclencher l'enregistrement AMFI :
      ```bash
      sudo xattr -dr com.apple.quarantine /Applications/LibreOffice.app
      open /Applications/LibreOffice.app && sleep 2 \
        && osascript -e 'quit app "LibreOffice"'
      ```

**2. Compta**

```bash
git clone https://github.com/mlebas29/Compta.git ~/Compta
cd ~/Compta && ./install.sh
```

`install.sh` est idempotent et OS-aware : il vérifie chaque prérequis (Python, pip, Tkinter, Tesseract, gpg, LibreOffice) et, pour ceux qui manquent, affiche la commande exacte d'installation à exécuter — `sudo port install …` sur Ventura, `brew install …` sur Sonoma+. À relancer après chaque correction jusqu'à n'avoir plus que des `✓`. Il détecte aussi la version LO installée et émet un *warning* si elle est trop ancienne ou si le Python embarqué n'est pas lançable.

#### Environnement Python

Sur Mac, `install.sh` installe les dépendances dans **deux interpréteurs Python distincts** (système pour la GUI Tk + LibreOffice embarqué pour les scripts UNO). C'est transparent pour l'utilisateur.

### Lancement

L'installeur crée `~/Applications/Comptabilité.app` (bundle macOS, icône ICNS) — épinglable au Dock.

Ligne de commande :
```bash
cd ~/Compta && ./cpt_gui.py
```

### Particularités macOS

**Au 1er passage d'installation :**

- **Popup Command Line Tools** — sur un Mac neuf sans Xcode/CLT, `git clone` déclenche une fenêtre macOS proposant d'installer les *Command Line Tools* (~1 Go, quelques minutes). Accepter, attendre la fin, relancer la commande.
- **`pip3` vs `python3 -m pip` (Ventura)** — si `sudo port select --set pip pip311` n'a pas été exécuté, `pip3` dans le PATH peut résoudre vers le `pip` des Command Line Tools Apple — donc installer dans un site-packages différent du `python3` détecté par `install.sh`. Toujours utiliser `python3 -m pip install …` (c'est ce que fait `install.sh`).
- **PATH `~/.local/bin`** — `install.sh` dépose le wrapper `python3-uno` dans `~/.local/bin`. Si ce chemin n'est pas dans votre PATH (le script émet alors un *warning* en fin d'install), ajouter :
  ```
  export PATH="$HOME/.local/bin:$PATH"
  ```
  dans le bon fichier de profil selon le shell :
  - `~/.zshrc` — shell par défaut depuis Catalina ;
  - `~/.bash_profile` — si shell bash (et **pas** `~/.bashrc`, qui n'est pas chargé par les terminaux Mac).

  Recharger avec `source ~/.zshrc` (resp. `.bash_profile`) ou ouvrir un nouveau terminal.

  NB : le **lancement via le Dock** (`~/Applications/Comptabilité.app`) n'est **pas** concerné — le launcher du bundle injecte déjà ce PATH. La note ci-dessus ne vaut que pour le lancement en ligne de commande (CLI / shebangs `python3-uno`).

**Usage quotidien :**

- **Ouverture des `.md` depuis la GUI** — si aucune application n'est associée à `.md` dans LaunchServices, `open` renvoie `LSApplicationNotFoundErr`. La GUI le détecte et **se rabat automatiquement sur TextEdit** (toujours présent), donc les liens vers la doc fonctionnent sans configuration. Pour utiliser un éditeur préféré (VS Code, BBEdit…), associer `.md` une fois : Finder → clic droit sur un `.md` → **Lire les informations** → section **Ouvrir avec :** → choisir l'app → bouton **Tout modifier…** → confirmer.
- **Perfs UNO** — certaines opérations sont 2× à 10× plus lentes qu'en Linux (bridge socket sur Mac vs appel C natif sur Linux). Acceptable pour l'usage courant ; à éviter pour scans denses type `tool_fix_formats --charter` (~400 s vs 37 s).
- **Clipboard** — `pyperclip` natif (utilise `pbcopy`/`pbpaste`), aucune dépendance externe (pas de `xclip` requis).
- **MacPorts sudo** — `sudo` ignore le PATH utilisateur sur Mac. Utiliser le chemin absolu : `sudo /opt/local/bin/port ...`.

## Windows 11 — via WSL2

**WSL2** (Windows Subsystem for Linux) permet de faire tourner un Linux complet dans Windows 11, sans machine virtuelle à gérer. **WSLg** (intégré) affiche les fenêtres Linux nativement sur le bureau Windows.

Résultat : l'application tourne **sans modification de code**, y compris la GUI tkinter et LibreOffice.

| Élément | Version testée |
|---|---|
| Distribution WSL | Ubuntu 24.04 |
| LibreOffice | **≥ 24.8.x** (installé/mis à niveau automatiquement par `install.sh`) |

> **⚠ Piège LibreOffice 24.2.x** (paquet `apt` Ubuntu 24.04 par défaut) : cette version corrompt silencieusement les formules XLOOKUP lors d'une sauvegarde via UNO — elle ajoute le préfixe `_xlfn.` mais ne sait pas le relire à l'ouverture suivante (mapping introduit en 24.8). Conséquence : tout `tool_migrate_*.py` exécuté sur LO 24.2.x corrompt des centaines de cellules CTRL1 / Avoirs. `install.sh` détecte le cas et upgrade automatiquement via le PPA officiel — aucune action manuelle.

### Installation WSL2

Dans un terminal PowerShell (administrateur) :

```powershell
wsl --install -d Ubuntu-24.04
```

Redémarrer Windows, puis ouvrir un terminal PowerShell et taper `wsl` pour entrer dans la distribution. Créer un utilisateur Linux quand demandé.

> **Note :** le premier appel à `wsl --install` peut échouer avec « erreur irrémédiable ». Relancer la même commande — le second appel devrait fonctionner. Redémarrer ensuite Windows pour la prise en compte.

### Installation de l'application

Ouvrir un terminal PowerShell et taper `wsl` pour entrer dans la distribution. Dans le terminal Ubuntu WSL :

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install git
git clone https://github.com/mlebas29/Compta.git ~/Compta
cd ~/Compta && ./install.sh
```

C'est la même procédure que sous Linux natif. Le script `install.sh` :

- détecte la restriction pip PEP 668 présente sur Ubuntu 24.04 et l'active si nécessaire ;
- installe LibreOffice si absent ; si la version installée est < 24.8 (Ubuntu 24.04 livre 24.2.x par défaut), il ajoute automatiquement le PPA `libreoffice/ppa` et bascule sur ≥ 24.8.

En cas d'échec de l'upgrade automatique, la procédure manuelle équivalente est :

```bash
sudo add-apt-repository -y ppa:libreoffice/ppa
sudo apt update
sudo apt install -y libreoffice
libreoffice --version    # vérifier ≥ 24.8
```

Les `tool_migrate_*.py` refusent de tourner si LO < 24.8 (garde dans `inc_uno.require_libreoffice_min`).

### wslu (recommandé)

Pour que l'ouverture des documents Markdown depuis la GUI utilise l'app Windows par défaut (au lieu de tomber sur Chrome via le fallback `sensible-browser`) :

```bash
sudo apt install wslu
```

`install.sh` détecte WSL et émet un *warning* si `wslu` est absent. Sans ce paquet, `xdg-open` ne trouve aucune association Linux pour `text/markdown` (Ubuntu WSL minimal n'a pas d'éditeur GUI) et finit par invoquer le navigateur Windows par défaut.

Avec `wslu` installé, l'app appelle `wslview` qui délègue à l'app Windows associée à `.md` (Bloc-notes, VS Code, Typora…). L'association se configure côté Windows : clic droit sur un .md → Ouvrir avec → choisir l'app → cocher « Toujours ».

### Lancement

```bash
cd ~/Compta && ./cpt_gui.py
```

La fenêtre s'affiche sur le bureau Windows grâce à WSLg.

### Points d'attention

| Sujet | Détail |
|-------|--------|
| **Performances fichiers** | Travailler dans le filesystem Linux (`~/Compta/`), pas dans `/mnt/c/...` qui est lent |
| **Playwright headed** | Le mode navigateur visible (Cloudflare) fonctionne via WSLg mais peut être un peu lent graphiquement |
| **Accès classeur depuis Windows** | Le classeur dans WSL est accessible depuis l'Explorateur Windows : `\\wsl$\Ubuntu-24.04\home\<user>\Compta\` |
| **LibreOffice GUI** | Pour ouvrir le classeur dans LibreOffice, le lancer depuis WSL (`libreoffice ~/Compta/comptes.xlsm`), pas depuis Windows |

### Raccourci Windows

Pour lancer l'application depuis le bureau Windows sans ouvrir manuellement un terminal :

1. Clic droit sur le bureau → **Nouveau → Raccourci**
2. Emplacement :
   ```
   wsl.exe -d Ubuntu-24.04 -- bash -lc "cd ~/Compta && ./cpt_gui.py"
   ```
3. Nommer le raccourci **Comptabilité**
4. Clic droit → **Épingler à la barre des tâches**
5. Optionnel : clic droit sur le raccourci → **Propriétés** → champ "Exécuter" → **Réduite** (pour masquer le terminal)

### Limitations connues

- **Windows 10** : WSLg n'est pas disponible. Il faut installer un serveur X séparé (VcXsrv, X410) pour afficher la GUI. Fonctionnel mais moins intégré.
- **Wayland pur** : même limitation que sous Linux — `xclip` (2FA Kraken/Wise) ne fonctionne pas en Wayland pur.

## Windows natif (sans WSL) — non supporté

Le portage sur Windows pur (sans WSL2) **n'est pas supporté** pour le mode assisté. La raison principale est le bridge Python ↔ UNO : sur Windows pur, UNO n'est accessible que via le Python embarqué de LibreOffice, pas via un Python externe — ce qui imposerait une refonte de l'orchestration.

L'analyse théorique des autres adaptations (à titre informatif) :

| Composant | Linux | Windows | Effort |
|-----------|-------|---------|--------|
| Lancement LibreOffice | `soffice` dans le PATH | Chemin complet `Program Files\...` | petit |
| Détection processus | `pgrep -x soffice.bin` | `tasklist` ou `psutil` | petit |
| Clipboard | `xclip` | `pyperclip` ou Win32 API | petit |
| Ouverture fichiers | `xdg-open` | `os.startfile()` | trivial |
| Script d'installation | `install.sh` (bash) | PowerShell `.ps1` | moyen |
| Raccourci bureau | `.desktop` GNOME | `.lnk` Windows | petit |
| Bridge UNO Python | Intégré au Python système | Python embarqué LibreOffice uniquement | **bloquant** |

**Recommandation** : sous Windows, utiliser WSL2 (section précédente), qui évite tout portage.
