# Compta — Portage sur d'autres OS

L'application est développée et testée sous **Linux Ubuntu 22.04+** et dérivés (Zorin, Mint).
Ce document décrit les options de portage vers d'autres systèmes.

## Windows 11 — via WSL2

**WSL2** (Windows Subsystem for Linux) permet de faire tourner un Linux complet dans Windows 11, sans machine virtuelle à gérer. **WSLg** (intégré) affiche les fenêtres Linux nativement sur le bureau Windows.

Résultat : l'application tourne **sans modification de code**, y compris la GUI tkinter et LibreOffice.

### Installation WSL2

Dans un terminal PowerShell (administrateur) :

```powershell
wsl --install -d Ubuntu-24.04
```

Redémarrer, puis lancer Ubuntu depuis le menu Démarrer. Créer un utilisateur Linux quand demandé.

### Installation de l'application

Dans le terminal Ubuntu WSL :

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install git
git clone https://github.com/mlebas29/Compta.git ~/Compta
cd ~/Compta && ./install.sh
```

C'est la même procédure que sous Linux natif.

### Lancement

```bash
cd ~/Compta && python3 cpt_gui.py
```

La fenêtre s'affiche sur le bureau Windows grâce à WSLg.

### Points d'attention

| Sujet | Détail |
|-------|--------|
| **Performances fichiers** | Travailler dans le filesystem Linux (`~/Compta/`), pas dans `/mnt/c/...` qui est lent |
| **Playwright headed** | Le mode navigateur visible (Cloudflare) fonctionne via WSLg mais peut être un peu lent graphiquement |
| **Accès classeur depuis Windows** | Le classeur dans WSL est accessible depuis l'Explorateur Windows : `\\wsl$\Ubuntu-24.04\home\<user>\Compta\` |
| **LibreOffice GUI** | Pour ouvrir le classeur dans LibreOffice, le lancer depuis WSL (`libreoffice ~/Compta/comptes.xlsm`), pas depuis Windows |

### Limitations connues

- **Windows 10** : WSLg n'est pas disponible. Il faut installer un serveur X séparé (VcXsrv, X410) pour afficher la GUI. Fonctionnel mais moins intégré.
- **Wayland pur** : même limitation que sous Linux — `xclip` (2FA Kraken/Wise) ne fonctionne pas en Wayland pur.

## macOS

Non testé. Les composants principaux (Python, tkinter, LibreOffice, Playwright) existent sous macOS.

Les adaptations nécessaires seraient similaires à un portage Windows natif :

- `xclip` → `pbcopy`/`pbpaste` (commandes macOS natives)
- `xdg-open` → `open`
- `pgrep` : disponible nativement sur macOS
- `install.sh` : remplacer `apt` par `brew`
- Raccourci bureau : `.desktop` → application macOS

Effort estimé : **1 à 2 jours**, dont les tests.

## Windows natif (sans WSL)

Portage possible mais plus lourd. Les points à adapter :

| Composant | Linux | Windows | Effort |
|-----------|-------|---------|--------|
| Lancement LibreOffice | `soffice` dans le PATH | Chemin complet `Program Files\...` | petit |
| Détection processus | `pgrep -x soffice.bin` | `tasklist` ou `psutil` | petit |
| Clipboard | `xclip` | `pyperclip` ou Win32 API | petit |
| Ouverture fichiers | `xdg-open` | `os.startfile()` | trivial |
| Script d'installation | `install.sh` (bash) | PowerShell `.ps1` | moyen |
| Raccourci bureau | `.desktop` GNOME | `.lnk` Windows | petit |
| Bridge UNO Python | Intégré au Python système | Configuration PATH spécifique | **risque** |

Effort estimé : **2 à 3 jours**, dont le risque principal est le bridge Python-UNO sous Windows.

**Recommandation** : préférer la solution WSL2 sous Windows 11, qui évite tout portage.
