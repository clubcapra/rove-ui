# CapraUI

Application Qt (PySide6) avec un point d'entree simple dans `widget.py`.

## Prerequis

- Ubuntu/WSL
- Python 3.12+
- pip
- Dependance systeme Qt (xcb):

```bash
sudo apt update
sudo apt install -y libxcb-cursor0
```

- Dependance systeme GStreamer (necessaire pour `RTSPView` / RTSP):

```bash
sudo apt update
sudo apt install -y \
  python3-gi gir1.2-gstreamer-1.0 gir1.2-gst-plugins-base-1.0 \
  gstreamer1.0-tools gstreamer1.0-gl gstreamer1.0-libav \
  gstreamer1.0-plugins-base gstreamer1.0-plugins-good gstreamer1.0-plugins-bad
```

## Installation

Depuis le dossier du projet:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
```

Note: si tu utilises `python3-gi` installe via `apt`, un `venv` standard ne le voit pas.
Dans ce cas, recree le venv avec:

```bash
python3 -m venv --system-site-packages .venv
```

## Lancement (WSL recommande)

Utiliser le script fourni:

```bash
./run.sh
```

Le script:
- nettoie les variables Qt qui peuvent casser le chargement des plugins,
- utilise Wayland via WSLg si disponible,
- retombe sur xcb/X11 sinon.

## Lancement manuel

### Option Wayland (WSLg)

```bash
env -u QT_PLUGIN_PATH -u QT_QPA_PLATFORM_PLUGIN_PATH -u LD_LIBRARY_PATH \
  XDG_RUNTIME_DIR=/mnt/wslg/runtime-dir \
  WAYLAND_DISPLAY=wayland-0 \
  QT_QPA_PLATFORM=wayland \
  .venv/bin/python widget.py
```

### Option xcb (fallback)

```bash
env -u QT_PLUGIN_PATH -u QT_QPA_PLATFORM_PLUGIN_PATH -u LD_LIBRARY_PATH \
  DISPLAY=:0 \
  QT_QPA_PLATFORM=xcb \
  .venv/bin/python widget.py
```

## Depannage rapide

- Verifier l'affichage WSLg:

```bash
echo $WAYLAND_DISPLAY
echo $DISPLAY
```

- Verifier le socket Wayland WSLg:

```bash
ls -la /mnt/wslg/runtime-dir/wayland-0
```

- Si besoin, redemarrer WSL depuis Windows PowerShell:

```powershell
wsl --shutdown
wsl
```

## Build Windows (pour tester la webcam facilement)

La webcam est souvent plus simple à tester en natif Windows (WSL ne voit pas toujours `/dev/video*`).

### Prérequis

- Python 3.12+ sur Windows

### Build avec PyInstaller

Dans un PowerShell (dans le dossier `capraui` qui contient `widget.py`) :

```powershell
python -m venv .venv
.venv\Scripts\activate
./build_windows.ps1 -Mode onedir
```

Le binaire est dans `dist\capraui\`.

Alternative CMD:

```bat
python -m venv .venv
.venv\Scripts\activate
build_windows.cmd
```
