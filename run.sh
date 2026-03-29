#!/usr/bin/env bash
set -euo pipefail

# Run the Qt app with safe display/plugin defaults.
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

# Prefer a venv at the project root (../.venv). Fall back to a local one.
VENV_PY=""
if [[ -x "${PROJECT_ROOT}/.venv/bin/python" ]]; then
  VENV_PY="${PROJECT_ROOT}/.venv/bin/python"
elif [[ -x "${SCRIPT_DIR}/.venv/bin/python" ]]; then
  VENV_PY="${SCRIPT_DIR}/.venv/bin/python"
fi

if [[ -z "$VENV_PY" ]]; then
  echo "Virtual environment not found (expected ../.venv or ./.venv)."
  echo "Create it with: python3 -m venv ../.venv"
  echo "Then install deps: ../.venv/bin/python -m pip install -r requirements.txt"
  exit 1
fi

cd "$SCRIPT_DIR"

ENV_ARGS=(
  -u QT_PLUGIN_PATH
  -u QT_QPA_PLATFORM_PLUGIN_PATH
  -u LD_LIBRARY_PATH
)

# Prefer WSLg Wayland socket when available; fallback to X11.
if [[ -S /mnt/wslg/runtime-dir/wayland-0 ]]; then
  # NOTE: Although WSLg provides Wayland, GStreamer VideoOverlay tends to be
  # more reliable via XWayland (xcb) for embedded sinks.
  QT_PLATFORM_DEFAULT="xcb"
  QT_PLATFORM="${CAPRAUI_QT_QPA_PLATFORM:-$QT_PLATFORM_DEFAULT}"
  env "${ENV_ARGS[@]}" \
    XDG_RUNTIME_DIR=/mnt/wslg/runtime-dir \
    WAYLAND_DISPLAY=wayland-0 \
    DISPLAY="${DISPLAY:-:0}" \
    QT_QPA_PLATFORM="$QT_PLATFORM" \
    "$VENV_PY" widget.py
else
  QT_PLATFORM_DEFAULT="xcb"
  QT_PLATFORM="${CAPRAUI_QT_QPA_PLATFORM:-$QT_PLATFORM_DEFAULT}"
  env "${ENV_ARGS[@]}" \
    DISPLAY=:0 \
    QT_QPA_PLATFORM="$QT_PLATFORM" \
    "$VENV_PY" widget.py
fi
