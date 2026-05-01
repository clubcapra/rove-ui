from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, QTimer, Signal, Slot
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QWidget


class Header(QWidget):
    """
    Thin application header bar.

    Layout
    -------
    LEFT   — two signal indicators  (equipment name + dB value) + E-Stop
    CENTER — current time
    RIGHT  — battery level

    Configuration (config.json → header_settings)
    -----------------------------------------------
    {
        "signals": [
            {"name": "VTX",       "db": -65, "topic": "signals.VTX.db"},
            {"name": "Microhard", "db": -72, "topic": "signals.Microhard.db"}
        ],
        "battery_topic": "battery.percentage",
        "E-Stop": {
            "active_color":   "#ff0000",
            "inactive_color": "#00ff00",
            "topic": "estop_status"
        }
    }
    """

    _battery_signal: Signal = Signal(float)
    _signal_db_signal: Signal = Signal(int, str, float)
    _estop_signal: Signal = Signal(bool)

    _BAR_STYLE = """
        Header {
            background-color: #1a1a2e;
            border-bottom: 1px solid #2e2e4e;
        }
        QLabel {
            color: #e0e0e0;
            font-size: 16px;
            padding: 0px;
        }
    """

    def __init__(self, settings: dict | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        settings = settings or {}
        signals_cfg = (settings.get("signals", []) + [{}, {}])[:2]

        self.setFixedHeight(32)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setStyleSheet(self._BAR_STYLE)

        root = QHBoxLayout(self)
        root.setContentsMargins(10, 0, 10, 0)
        root.setSpacing(0)

        # ── LEFT : signal labels + E-Stop ─────────────────────────────────
        left = QHBoxLayout()
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(18)

        self._signal_labels: list[tuple[str, QLabel]] = []
        for sig in signals_cfg:
            name = sig.get("name", "—")
            db   = sig.get("db", 0)
            lbl  = QLabel(f"{name}  {db} dB")
            lbl.setStyleSheet("color: #000;")
            left.addWidget(lbl)
            self._signal_labels.append((name, lbl))

        estop_cfg = settings.get("E-Stop", {})
        self._estop_active_color   = estop_cfg.get("active_color",   "#ff0000")
        self._estop_inactive_color = estop_cfg.get("inactive_color", "#00ff00")
        self._estop_label = QLabel("E-Stop")
        self._estop_label.setStyleSheet(f"color: {self._estop_inactive_color};")
        left.addWidget(self._estop_label)

        left.addStretch()
        left_w = QWidget()
        left_w.setLayout(left)
        left_w.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        # ── CENTER : clock ────────────────────────────────────────────────
        self._center_time = QLabel(self._current_time())
        self._center_time.setAlignment(Qt.AlignCenter)
        self._center_time.setStyleSheet("font-size: 16px; font-weight: 600; color: #000;")

        # ── RIGHT : battery ───────────────────────────────────────────────
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

        # ── Wire signals to slots (GUI-thread safe) ───────────────────────
        self._battery_signal.connect(self._do_update_battery)
        self._signal_db_signal.connect(self._do_update_signal_db)
        self._estop_signal.connect(self._do_update_estop)

        # ── Clock timer ───────────────────────────────────────────────────
        self._clock = QTimer(self)
        self._clock.timeout.connect(lambda: self._center_time.setText(self._current_time()))
        self._clock.start(1000)

        # ── EventBus subscriptions ────────────────────────────────────────
        event_bus = getattr(parent, "event_bus", None)
        if event_bus:
            estop_topic = estop_cfg.get("topic", "estop_status")
            event_bus.subscribe(estop_topic, self.update_estop)

            battery_topic = str(settings.get("battery_topic", "")).strip()
            if battery_topic:
                event_bus.subscribe(battery_topic, self.update_battery)

            for idx, sig in enumerate(signals_cfg):
                topic = str(sig.get("topic", "")).strip()
                if topic:
                    name = sig.get("name", "—")
                    def _on_db(v, i=idx, n=name):
                        try:
                            self._signal_db_signal.emit(i, n, float(v))
                        except (TypeError, ValueError):
                            pass
                    event_bus.subscribe(topic, _on_db)

    # ── Public API ────────────────────────────────────────────────────────

    @staticmethod
    def _current_time() -> str:
        return datetime.now().strftime("%H:%M:%S")

    def update_time(self, time_str: str) -> None:
        self._center_time.setText(time_str)

    def update_battery(self, value) -> None:
        try:
            self._battery_signal.emit(float(value))
        except (TypeError, ValueError):
            pass

    def update_estop(self, active) -> None:
        self._estop_signal.emit(bool(active))

    # ── Slots (always called from GUI thread via Signal) ──────────────────

    @Slot(float)
    def _do_update_battery(self, value: float) -> None:
        pct = max(0, min(100, int(value)))
        icon = "🪫" if pct <= 20 else "🔋"
        self._battery_label.setText(f"{icon} {pct}%")
        color = "#e05555" if pct <= 20 else "#fbbf24" if pct <= 50 else "#7ec87e"
        self._battery_label.setStyleSheet(f"color: {color};")

    @Slot(int, str, float)
    def _do_update_signal_db(self, idx: int, name: str, db: float) -> None:
        if 0 <= idx < len(self._signal_labels):
            self._signal_labels[idx][1].setText(f"{name}  {db:.0f} dB")

    @Slot(bool)
    def _do_update_estop(self, active: bool) -> None:
        color = self._estop_active_color if active else self._estop_inactive_color
        self._estop_label.setStyleSheet(f"color: {color};")
