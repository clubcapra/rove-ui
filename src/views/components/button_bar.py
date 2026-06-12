from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)
from src.controller.event_bus import EventBus
from src.views import theme

def _btn_style(color: str | None = None) -> str:
    c = color or theme.TEXT
    b = color or theme.BORDER
    return f"""
QPushButton {{
    background: {theme.BG_SURFACE};
    color: {theme.TEXT_DIM};
    border: 1px solid {theme.BORDER_DIM};
    border-radius: 0;
    font-family: {theme.FONT_MONO};
    font-size: 15px;
    font-weight: 700;
    letter-spacing: 1px;
    padding: 4px 18px;
}}
QPushButton:hover {{
    background: {theme.BG_PANEL};
    border-color: {b};
    color: {c};
}}
QPushButton:pressed {{
    background: {theme.BG_DARK};
    border-color: {b};
}}
"""

def _btn_active_style(color: str | None = None) -> str:
    c = color or theme.CYAN
    return f"""
QPushButton {{
    background: {theme.BG_PANEL};
    color: {c};
    border: 1px solid {c};
    border-radius: 0;
    font-family: {theme.FONT_MONO};
    font-size: 15px;
    font-weight: 700;
    letter-spacing: 1px;
    padding: 4px 18px;
}}
QPushButton:hover {{
    background: {theme.BG_SURFACE};
    border-color: {c};
    color: {c};
}}
QPushButton:pressed {{ background: {theme.BG_DARK}; }}
"""

_BTN        = _btn_style()
_BTN_ACTIVE = _btn_active_style()


class ButtonBar(QWidget):
    """A bar of buttons that publish EventBus events on click.

    Config keys:
      orientation  — "horizontal" (default) or "vertical"
      label        — optional text label shown before the buttons
      height       — fixed height in px (default: 44)
      buttons      — list of { label, event, value, active_topic? }
    """

    def __init__(self, config: dict, event_bus: EventBus | None = None, parent=None):
        super().__init__(parent)
        self.config = config
        self.event_bus = event_bus or EventBus()
        self._buttons: list[QPushButton] = []
        self._button_cfgs: list[dict] = []
        self._toggle_states: dict[int, bool] = {}  # index → active
        self._build()

    def _build(self) -> None:
        orientation = self.config.get("orientation", "horizontal")
        bar_label   = self.config.get("label")
        fixed_h     = int(self.config.get("height", 44))

        self.setFixedHeight(fixed_h)
        self.setAttribute(
            __import__("PySide6.QtCore", fromlist=["Qt"]).Qt.WidgetAttribute.WA_StyledBackground,
            True,
        )
        self.setStyleSheet(
            f"background: {theme.BG_DARK}; border: 1px solid {theme.BORDER};"
        )

        if orientation == "vertical":
            layout = QVBoxLayout(self)
        else:
            layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)
        layout.setSpacing(6)

        if bar_label:
            lbl = QLabel(bar_label.upper())
            lbl.setStyleSheet(
                f"color: {theme.TEXT_MUTED}; font-size: 10px; "
                f"letter-spacing: 2px; background: transparent;"
            )
            layout.addWidget(lbl)

        for idx, cfg in enumerate(self.config.get("buttons", [])):
            label  = str(cfg.get("label", ""))
            color  = cfg.get("color") or None
            btn = QPushButton(label)
            btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)
            btn.setStyleSheet(_btn_style(color))
            btn.clicked.connect(lambda _=False, c=cfg, i=idx: self._on_click(c, i))
            layout.addWidget(btn)
            self._buttons.append(btn)
            self._button_cfgs.append(cfg)

            if cfg.get("toggle"):
                self._toggle_states[idx] = False

            active_topic = cfg.get("active_topic")
            if active_topic:
                expected = cfg.get("value")
                self.event_bus.subscribe(
                    active_topic,
                    lambda v, b=btn, e=expected, col=color: b.setStyleSheet(
                        _btn_active_style(col) if str(v) == str(e) else _btn_style(col)
                    ),
                )

        layout.addStretch()

    def _on_click(self, cfg: dict, idx: int | None = None) -> None:
        event = cfg.get("event")
        color = cfg.get("color") or None

        if cfg.get("toggle") and idx is not None:
            new_state = not self._toggle_states.get(idx, False)
            self._toggle_states[idx] = new_state
            btn = self._buttons[idx]
            btn.setStyleSheet(_btn_active_style(color) if new_state else _btn_style(color))
            value = cfg.get("value", "1") if new_state else cfg.get("off_value", "0")
        else:
            value = cfg.get("value")

        if event:
            if value is not None:
                QTimer.singleShot(0, lambda e=event, v=value: self.event_bus.publish_sync(e, v))
            else:
                QTimer.singleShot(0, lambda e=event: self.event_bus.publish_sync(e))
