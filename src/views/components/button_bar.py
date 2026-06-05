from __future__ import annotations

from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)
from src.controller.event_bus import EventBus

_BTN = """
QPushButton {
    background: #292928; color: #e0e0e0;
    border: 1px solid #3a3a38; border-radius: 4px;
    font-size: 12px; font-weight: 600; padding: 4px 16px;
}
QPushButton:hover   { background: #3a3a38; border-color: #555; }
QPushButton:pressed { background: #444; }
"""

_BTN_ACTIVE = """
QPushButton {
    background: #2a1410; color: #eb4034;
    border: 1px solid #eb4034; border-radius: 4px;
    font-size: 12px; font-weight: 700; padding: 4px 16px;
}
"""


class ButtonBar(QWidget):
    """A bar of buttons that publish EventBus events on click.

    Config keys:
      orientation  — "horizontal" (default) or "vertical"
      label        — optional text label shown before the buttons
      height       — fixed height in px (default: 44)
      buttons      — list of { label, event, value, active_topic? }

    Each button config:
      label        — button text
      event        — event name to publish on click
      value        — payload sent with the event
      active_topic — optional topic to subscribe to for syncing active state
    """

    def __init__(self, config: dict, event_bus: EventBus | None = None, parent=None):
        super().__init__(parent)
        self.config = config
        self.event_bus = event_bus or EventBus()
        self._buttons: list[QPushButton] = []
        self._button_cfgs: list[dict] = []
        self._build()

    def _build(self) -> None:
        orientation = self.config.get("orientation", "horizontal")
        bar_label = self.config.get("label")
        fixed_h = int(self.config.get("height", 44))

        self.setFixedHeight(fixed_h)
        self.setStyleSheet("background: #1c1c1b; border-top: 1px solid #3a3a38;")

        if orientation == "vertical":
            layout = QVBoxLayout(self)
        else:
            layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 4, 10, 4)
        layout.setSpacing(8)

        if bar_label:
            lbl = QLabel(bar_label)
            lbl.setStyleSheet("color: #888; font-size: 11px; background: transparent;")
            layout.addWidget(lbl)

        for cfg in self.config.get("buttons", []):
            label = str(cfg.get("label", ""))
            btn = QPushButton(label)
            btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)
            btn.setStyleSheet(_BTN)
            btn.clicked.connect(lambda _=False, c=cfg: self._on_click(c))
            layout.addWidget(btn)
            self._buttons.append(btn)
            self._button_cfgs.append(cfg)

            active_topic = cfg.get("active_topic")
            if active_topic:
                expected = cfg.get("value")
                self.event_bus.subscribe(
                    active_topic,
                    lambda v, b=btn, e=expected: b.setStyleSheet(
                        _BTN_ACTIVE if str(v) == str(e) else _BTN
                    ),
                )

        layout.addStretch()

    def _on_click(self, cfg: dict) -> None:
        event = cfg.get("event")
        value = cfg.get("value")
        if event:
            if value is not None:
                self.event_bus.publish_sync(event, value)
            else:
                self.event_bus.publish_sync(event)
        self._sync_active(value)

    def _sync_active(self, value) -> None:
        for btn, cfg in zip(self._buttons, self._button_cfgs):
            active = str(cfg.get("value", "")) == str(value)
            btn.setStyleSheet(_BTN_ACTIVE if active else _BTN)
