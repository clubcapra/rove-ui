from __future__ import annotations

import re
import subprocess
from datetime import datetime
from threading import Thread

from PySide6.QtCore import Qt, QTimer, Signal, Slot
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QWidget


def _ping_ms(host: str, timeout_s: int = 1) -> float | None:
    """Return round-trip ms or None on timeout/error."""
    try:
        result = subprocess.run(
            ["ping", "-c", "1", "-W", str(timeout_s), host],
            capture_output=True, text=True, timeout=timeout_s + 1
        )
        match = re.search(r"time=(\d+(?:\.\d+)?)\s*ms", result.stdout)
        return float(match.group(1)) if match else None
    except Exception:
        return None


class Header(QWidget):
    """
    Thin application header bar.

    Layout
    -------
    LEFT   — ping indicators (name + ms) + E-Stop
    CENTER — current time
    RIGHT  — battery level

    Configuration (config.json → header_settings)
    -----------------------------------------------
    {
        "signals": [
            {"name": "Robot",  "host": "192.168.2.2"},
            {"name": "Camera", "host": "192.168.2.34"}
        ],
        "ping_interval_s": 2,
        "battery_topic": "battery.percentage",
        "E-Stop": {
            "active_color":   "#ff0000",
            "inactive_color": "#00ff00",
            "topic": "estop_status"
        }
    }
    """

    _battery_signal: Signal = Signal(float)
    _ping_signal:    Signal = Signal(int, str, object)   # idx, name, ms|None
    _estop_signal:   Signal = Signal(bool)

    _BAR_STYLE = """
        Header {
            background-color: #1c1c1b;
            border-bottom: 1px solid #292928;
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
        signals_cfg = settings.get("signals", [])
        ping_interval = int(settings.get("ping_interval_s", 2))

        self.setFixedHeight(32)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setStyleSheet(self._BAR_STYLE)

        root = QHBoxLayout(self)
        root.setContentsMargins(10, 0, 10, 0)
        root.setSpacing(0)

        # ── LEFT : ping labels + E-Stop ───────────────────────────────────
        left = QHBoxLayout()
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(18)

        self._ping_labels: list[QLabel] = []
        for sig in signals_cfg:
            name = sig.get("name", "—")
            lbl = QLabel(f"{name}  … ms")
            lbl.setStyleSheet("color: #888;")
            left.addWidget(lbl)
            self._ping_labels.append(lbl)

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
        self._center_time.setStyleSheet("font-size: 16px; font-weight: 600; color: #e0e0e0;")

        # ── RIGHT : battery ───────────────────────────────────────────────
        right = QHBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(10)
        right.addStretch()
        self._battery_label = QLabel("🔋 --%")
        self._battery_label.setStyleSheet("color: #e0e0e0;")
        right.addWidget(self._battery_label)
        right_w = QWidget()
        right_w.setLayout(right)
        right_w.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        root.addWidget(left_w, 1)
        root.addWidget(self._center_time, 0)
        root.addWidget(right_w, 1)

        # ── Wire signals → slots (GUI-thread safe) ────────────────────────
        self._battery_signal.connect(self._do_update_battery)
        self._ping_signal.connect(self._do_update_ping)
        self._estop_signal.connect(self._do_update_estop)

        # ── Clock ─────────────────────────────────────────────────────────
        self._clock = QTimer(self)
        self._clock.timeout.connect(lambda: self._center_time.setText(self._current_time()))
        self._clock.start(1000)

        # ── Ping threads ──────────────────────────────────────────────────
        for idx, sig in enumerate(signals_cfg):
            host = str(sig.get("host", "")).strip()
            name = str(sig.get("name", "—"))
            if not host:
                continue
            def _ping_loop(i=idx, n=name, h=host, interval=ping_interval):
                import time
                while True:
                    ms = _ping_ms(h)
                    self._ping_signal.emit(i, n, ms)
                    time.sleep(interval)
            Thread(target=_ping_loop, daemon=True).start()

        # ── EventBus subscriptions ────────────────────────────────────────
        event_bus = getattr(parent, "event_bus", None)
        if event_bus:
            estop_topic = estop_cfg.get("topic", "estop_status")
            event_bus.subscribe(estop_topic, self.update_estop)

            battery_topic = str(settings.get("battery_topic", "")).strip()
            if battery_topic:
                event_bus.subscribe(battery_topic, self.update_battery)

    # ── Public API ────────────────────────────────────────────────────────

    @staticmethod
    def _current_time() -> str:
        return datetime.now().strftime("%H:%M:%S")

    def update_battery(self, value) -> None:
        try:
            self._battery_signal.emit(float(value))
        except (TypeError, ValueError):
            pass

    def update_estop(self, active) -> None:
        self._estop_signal.emit(bool(active))

    # ── Slots (GUI thread) ────────────────────────────────────────────────

    @Slot(float)
    def _do_update_battery(self, value: float) -> None:
        pct = max(0, min(100, int(value)))
        icon = "🪫" if pct <= 20 else "🔋"
        self._battery_label.setText(f"{icon} {pct}%")
        color = "#e05555" if pct <= 20 else "#fbbf24" if pct <= 50 else "#7ec87e"
        self._battery_label.setStyleSheet(f"color: {color};")

    @Slot(int, str, object)
    def _do_update_ping(self, idx: int, name: str, ms) -> None:
        if not (0 <= idx < len(self._ping_labels)):
            return
        lbl = self._ping_labels[idx]
        if ms is None:
            lbl.setText(f"{name}  timeout")
            lbl.setStyleSheet("color: #e05555;")
        else:
            lbl.setText(f"{name}  {ms:.0f} ms")
            color = "#7ec87e" if ms < 50 else "#fbbf24" if ms < 150 else "#e05555"
            lbl.setStyleSheet(f"color: {color};")

    @Slot(bool)
    def _do_update_estop(self, active: bool) -> None:
        color = self._estop_active_color if active else self._estop_inactive_color
        self._estop_label.setStyleSheet(f"color: {color};")
