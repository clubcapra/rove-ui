param(
  [ValidateSet('onedir','onefile')][string]$Mode = 'onedir',
  [string]$Python = 'python'
)

$ErrorActionPreference = 'Stop'

Write-Host "== CapraUI Windows build ($Mode) =="

# Run from repo root (folder containing widget.py)
$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $repoRoot

# Ensure deps
& $Python -m pip install --upgrade pip
& $Python -m pip install -r requirements.txt
& $Python -m pip install pyinstaller

# Clean previous build
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue build, dist

$addData = "config;config"  # Windows separator for PyInstaller

$common = @(
  '--noconfirm',
  '--name', 'capraui',
  '--add-data', $addData
)

if ($Mode -eq 'onefile') {
  & $Python -m PyInstaller @common --onefile widget.py
} else {
  & $Python -m PyInstaller @common widget.py
}

Write-Host "\nBuild output in .\\dist\\capraui\\ (or dist\\capraui.exe in onefile mode)"
