# Light theme constants — Rove Mission Control UI

# ── Background layers ─────────────────────────────────────────────────────────
BG_DEEP    = "#f0f2f5"   # window / outermost background
BG_DARK    = "#e8ebef"   # panel background
BG_PANEL   = "#dde1e8"   # elevated surface (header bars, nav)
BG_SURFACE = "#d0d5de"   # interactive cells, hover areas

# ── Borders ───────────────────────────────────────────────────────────────────
BORDER_DIM    = "#bfc5cf"   # inactive / decorative borders
BORDER        = "#a8b1bc"   # default borders
BORDER_BRIGHT = "#7a8591"   # highlighted / focused borders

# ── Accent colors ─────────────────────────────────────────────────────────────
CYAN   = "#c07800"   # primary active / selected
GREEN  = "#00875a"   # ok / connected / nominal
RED    = "#c92b2b"   # alert / error / e-stop
AMBER  = "#b86000"   # warning / degraded

# ── Text ──────────────────────────────────────────────────────────────────────
TEXT       = "#1a1d22"   # primary readable text
TEXT_DIM   = "#606870"   # secondary / inactive labels
TEXT_MUTED = "#b8c0ca"   # very dim decorative text

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
