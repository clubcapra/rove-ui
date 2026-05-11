from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QWidget


class NavBar(QWidget):
    """Horizontal tab navigation bar."""

    _NAVBAR_BG = "#1c1c1b"
    _ACCENT    = "#eb4034"
    _TEXT_DIM  = "#888888"
    _HEIGHT    = 44

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(self._HEIGHT)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            NavBar {{ background: {self._NAVBAR_BG}; }}
            QPushButton {{
                background: transparent;
                color: {self._TEXT_DIM};
                border: none;
                border-bottom: 3px solid transparent;
                padding: 0 28px;
                font-size: 13px;
                font-weight: 600;
                letter-spacing: 0.5px;
                min-height: {self._HEIGHT}px;
            }}
            QPushButton:hover {{ color: #e5e7eb; background: rgba(255,255,255,0.05); }}
            QPushButton[active="true"] {{
                color: {self._ACCENT};
                border-bottom: 3px solid {self._ACCENT};
            }}
        """)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(0)
        layout.addStretch(1)
        self._buttons: dict[str, QPushButton] = {}

    def add_page(self, name: str, on_click) -> None:
        btn = QPushButton(name.upper())
        btn.setFlat(True)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFixedHeight(self._HEIGHT)
        btn.setProperty("active", "false")
        btn.clicked.connect(lambda _=False, n=name, cb=on_click: self._activate(n, cb))
        layout = self.layout()
        layout.insertWidget(layout.count() - 1, btn)
        self._buttons[name] = btn

    def _activate(self, name: str, callback) -> None:
        for n, b in self._buttons.items():
            val = "true" if n == name else "false"
            b.setProperty("active", val)
            b.style().unpolish(b)
            b.style().polish(b)
        callback()

    def activate_first(self) -> None:
        if self._buttons:
            first = next(iter(self._buttons))
            self._activate(first, lambda: None)

    def clear(self) -> None:
        layout = self.layout()
        for btn in self._buttons.values():
            layout.removeWidget(btn)
            btn.deleteLater()
        self._buttons.clear()
