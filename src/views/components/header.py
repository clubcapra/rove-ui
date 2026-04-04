from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QSizePolicy


class Header(QWidget):
    """
    Thin application header bar.

    Layout
    -------
    LEFT   — two signal indicators  (equipment name + dB value)
    CENTER — current time
    RIGHT  — current time + battery level

    Configuration (config.json → header_settings)
    -----------------------------------------------
    {
        "signals": [
            {"name": "Radio 1", "db": -65},
            {"name": "Radio 2", "db": -72}
        ]
    }

    Runtime updates
    ---------------
    header.update_time("14:32:01")
    header.update_battery(87)
    """

    _BAR_STYLE = """
        Header {
            background-color: #1a1a2e;
            border-bottom: 1px solid #2e2e4e;
        }
        QLabel {
            color: #e0e0e0;
            font-size: 11px;
            padding: 0px;
        }
    """

    def __init__(self, settings: dict | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        settings = settings or {}
        signals = (settings.get("signals", []) + [{}, {}])[:2]

        self.setFixedHeight(32)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setStyleSheet(self._BAR_STYLE)

        root = QHBoxLayout(self)
        root.setContentsMargins(10, 0, 10, 0)
        root.setSpacing(0)

        # ── LEFT : two signal labels ──────────────────────────────────────
        left = QHBoxLayout()
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(18)
        self._signal_labels: list[QLabel] = []
        for sig in signals:
            name = sig.get("name", "—")
            db = sig.get("db", 0)
            lbl = QLabel(f"{name}  {db} dB")
            lbl.setStyleSheet("color: #000;")
            left.addWidget(lbl)
            self._signal_labels.append(lbl)
        left.addStretch()
        left_w = QWidget()
        left_w.setLayout(left)
        left_w.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        # ── CENTER : clock ────────────────────────────────────────────────
        self._center_time = QLabel(self.getCurrentTime())
        self._center_time.setAlignment(Qt.AlignCenter)
        self._center_time.setStyleSheet("font-size: 13px; font-weight: 600; color: #000;")

        # ── RIGHT : clock + battery ───────────────────────────────────────
        right = QHBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(10)
        right.addStretch()
        self._battery_label = QLabel("🔋 --%")
        self._battery_label.setStyleSheet("color: #000;")
        right.addWidget(self._battery_label)
        right_w = QWidget()
        right_w.setLayout(right)
        right_w.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        root.addWidget(left_w, 1)
        root.addWidget(self._center_time, 0)
        root.addWidget(right_w, 1)

    # ── Public API ────────────────────────────────────────────────────────
    def getCurrentTime(self) -> str:
        """Return current time as HH:MM:SS string."""
        from datetime import datetime
        return datetime.now().strftime("%H:%M:%S")
    
    def update_time(self, time_str: str) -> None:
        """Update both time displays simultaneously."""
        self._center_time.setText(time_str)

    def update_battery(self, value: int) -> None:
        """Update battery level indicator (0-100)."""
        value = max(0, min(100, value))
        icon = "🪫" if value <= 20 else "🔋"
        self._battery_label.setText(f"{icon} {value}%")
        color = "#e05555" if value <= 20 else "#fbbf24" if value <= 50 else "#7ec87e"
        self._battery_label.setStyleSheet(f"color: {color};")
