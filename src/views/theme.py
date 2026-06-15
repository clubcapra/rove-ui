# Tactical light theme constants — Rove Mission Control UI

# ── Background layers ─────────────────────────────────────────────────────────
BG_DEEP    = "#e8eaed"   # window / outermost background
BG_DARK    = "#dde0e5"   # panel background
BG_PANEL   = "#d2d6dc"   # elevated surface (header bars, nav)
BG_SURFACE = "#c5cad2"   # interactive cells, hover areas

# ── Borders ───────────────────────────────────────────────────────────────────
BORDER_DIM    = "#b0b8c4"   # inactive / decorative borders
BORDER        = "#8e9aaa"   # default borders
BORDER_BRIGHT = "#5a6a7e"   # highlighted / focused borders

# ── Accent colors ─────────────────────────────────────────────────────────────
CYAN   = "#c47000"   # primary active / selected
GREEN  = "#1a7a4a"   # ok / connected / nominal
RED    = "#cc2020"   # alert / error / e-stop
AMBER  = "#c47a00"   # warning / degraded

# ── Text ──────────────────────────────────────────────────────────────────────
TEXT       = "#1a2230"   # primary readable text
TEXT_DIM   = "#5a6878"   # secondary / inactive labels
TEXT_MUTED = "#9aaabb"   # very dim decorative text

# ── Font ──────────────────────────────────────────────────────────────────────
FONT_MONO = "'Courier New', monospace"

# ── Scrollbars ────────────────────────────────────────────────────────────────
_SCROLL = f"""
QScrollBar:vertical {{
    background: {BG_PANEL}; width: 5px; border: none; margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {BORDER}; border-radius: 2px; min-height: 20px;
}}
QScrollBar::handle:vertical:hover {{ background: {BORDER_BRIGHT}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0; border: 0; background: none;
}}
QScrollBar:horizontal {{
    background: {BG_PANEL}; height: 5px; border: none; margin: 0;
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
