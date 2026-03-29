@echo off
setlocal enabledelayedexpansion

REM Build CapraUI on Windows using PyInstaller.
REM Run from the repo root (folder containing widget.py)

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install pyinstaller

if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

REM PyInstaller --add-data uses ';' on Windows to separate src and dest
python -m PyInstaller --noconfirm --name capraui --add-data "config;config" widget.py

echo.
echo Build output in dist\capraui\
endlocal
