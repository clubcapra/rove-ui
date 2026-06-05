# Tactical dark theme constants — Rove Mission Control UI

# ── Background layers ─────────────────────────────────────────────────────────
BG_DEEP    = "#080808"   # window / outermost background
BG_DARK    = "#0f0f0f"   # panel background
BG_PANEL   = "#161616"   # elevated surface (header bars, nav)
BG_SURFACE = "#1e1e1e"   # interactive cells, hover areas

# ── Borders ───────────────────────────────────────────────────────────────────
BORDER_DIM    = "#222222"   # inactive / decorative borders
BORDER        = "#2e2e2e"   # default borders
BORDER_BRIGHT = "#484848"   # highlighted / focused borders

# ── Accent colors ─────────────────────────────────────────────────────────────
CYAN   = "#ffae00"   # primary active / selected
GREEN  = "#00e676"   # ok / connected / nominal
RED    = "#ff3d3d"   # alert / error / e-stop
AMBER  = "#ffb300"   # warning / degraded

# ── Text ──────────────────────────────────────────────────────────────────────
TEXT       = "#d0d8e0"   # primary readable text
TEXT_DIM   = "#505050"   # secondary / inactive labels
TEXT_MUTED = "#282828"   # very dim decorative text

# ── Font ──────────────────────────────────────────────────────────────────────
FONT_MONO = "'Courier New', monospace"

# ── Scrollbars ────────────────────────────────────────────────────────────────
_SCROLL = f"""
QScrollBar:vertical {{
    background: {BG_DARK}; width: 5px; border: none; margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {BORDER}; border-radius: 2px; min-height: 20px;
}}
QScrollBar::handle:vertical:hover {{ background: {BORDER_BRIGHT}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0; border: 0; background: none;
}}
QScrollBar:horizontal {{
    background: {BG_DARK}; height: 5px; border: none; margin: 0;
}}
QScrollBar::handle:horizontal {{
    background: {BORDER}; border-radius: 2px; min-width: 20px;
}}
QScrollBar::handle:horizontal:hover {{ background: {BORDER_BRIGHT}; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0; border: 0; background: none;
}}
"""

# ── Global stylesheet (apply on QApplication) ─────────────────────────────────
GLOBAL = f"""
* {{
    font-family: {FONT_MONO};
    font-size: 12px;
    outline: none;
}}
QWidget {{
    color: {TEXT};
    background: {BG_DEEP};
}}
QToolTip {{
    background: {BG_PANEL};
    color: {TEXT};
    border: 1px solid {BORDER};
    padding: 4px 8px;
    border-radius: 0;
}}
QComboBox {{
    background: {BG_SURFACE};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 0;
    padding: 2px 8px;
    min-height: 22px;
}}
QComboBox::drop-down {{ border: none; }}
QComboBox QAbstractItemView {{
    background: {BG_PANEL};
    color: {TEXT};
    border: 1px solid {BORDER};
    selection-background-color: {BG_SURFACE};
    selection-color: {CYAN};
}}
QLabel {{ background: transparent; color: {TEXT}; }}
{_SCROLL}
"""
