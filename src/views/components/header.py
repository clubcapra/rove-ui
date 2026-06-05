from __future__ import annotations

import re
import subprocess
from datetime import datetime
from threading import Thread

from PySide6.QtCore import Qt, QTimer, Signal, Slot
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QWidget

from src.views import theme


def _ping_ms(host: str, timeout_s: int = 1) -> float | None:
    try:
        result = subprocess.run(
            ["ping", "-c", "1", "-W", str(timeout_s), host],
            capture_output=True, text=True, timeout=timeout_s + 1,
        )
        m = re.search(r"time=(\d+(?:\.\d+)?)\s*ms", result.stdout)
        return float(m.group(1)) if m else None
    except Exception:
        return None



class Header(QWidget):
    _battery_signal: Signal = Signal(float)
    _ping_signal:    Signal = Signal(int, str, object)
    _estop_signal:   Signal = Signal(bool)

    _STYLE = f"""
        Header {{
            background: {theme.BG_DARK};
            border-bottom: 1px solid {theme.CYAN};
        }}
        QLabel {{
            background: transparent;
            color: {theme.TEXT};
            font-family: {theme.FONT_MONO};
            font-size: 11px;
            padding: 0;
        }}
    """

    def __init__(self, settings: dict | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        settings = settings or {}
        signals_cfg   = settings.get("signals", [])
        ping_interval = int(settings.get("ping_interval_s", 2))

        self.setFixedHeight(36)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(self._STYLE)

        root = QHBoxLayout(self)
        root.setContentsMargins(14, 0, 14, 0)
        root.setSpacing(0)

        # ── LEFT: link status + E-Stop ────────────────────────────────────
        left = QHBoxLayout()
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(18)

        self._ping_labels: list[QLabel] = []
        for sig in signals_cfg:
            name = sig.get("name", "?")
            lbl = QLabel(f"[LINK {name} …]")
            lbl.setStyleSheet(f"color: {theme.TEXT_DIM};")
            left.addWidget(lbl)
            self._ping_labels.append(lbl)

        estop_cfg = settings.get("E-Stop", {})
        self._estop_active_color   = estop_cfg.get("active_color",   theme.RED)
        self._estop_inactive_color = estop_cfg.get("inactive_color", theme.GREEN)

        self._estop_label = QLabel("[E-STOP  NOMINAL]")
        self._estop_label.setStyleSheet(
            f"color: {theme.GREEN}; font-weight: 700; letter-spacing: 1px;"
        )
        left.addWidget(self._estop_label)
        left.addStretch()

        left_w = QWidget()
        left_w.setLayout(left)
        left_w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        left_w.setStyleSheet("background: transparent;")

        # ── CENTER: clock ─────────────────────────────────────────────────
        self._center_time = QLabel(self._current_time())
        self._center_time.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._center_time.setStyleSheet(
            f"color: {theme.CYAN}; font-size: 15px; font-weight: 700; "
            f"font-family: {theme.FONT_MONO}; letter-spacing: 3px; background: transparent;"
        )

        # ── RIGHT: battery ────────────────────────────────────────────────
        right = QHBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(0)
        right.addStretch()
        self._battery_label = QLabel("🔋  --V")
        self._battery_label.setStyleSheet(f"color: {theme.TEXT_DIM};")
        right.addWidget(self._battery_label)

        right_w = QWidget()
        right_w.setLayout(right)
        right_w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        right_w.setStyleSheet("background: transparent;")

        root.addWidget(left_w, 1)
        root.addWidget(self._center_time, 0)
        root.addWidget(right_w, 1)

        # ── Signals ───────────────────────────────────────────────────────
        self._battery_signal.connect(self._do_update_battery)
        self._ping_signal.connect(self._do_update_ping)
        self._estop_signal.connect(self._do_update_estop)

        self._clock = QTimer(self)
        self._clock.timeout.connect(
            lambda: self._center_time.setText(self._current_time())
        )
        self._clock.start(1000)

        for idx, sig in enumerate(signals_cfg):
            host = str(sig.get("host", "")).strip()
            name = str(sig.get("name", "?"))
            if not host:
                continue
            def _loop(i=idx, n=name, h=host, iv=ping_interval):
                import time
                while True:
                    ms = _ping_ms(h)
                    self._ping_signal.emit(i, n, ms)
                    time.sleep(iv)
            Thread(target=_loop, daemon=True).start()

        event_bus = getattr(parent, "event_bus", None)
        if event_bus:
            estop_topic = estop_cfg.get("topic", "estop_status")
            event_bus.subscribe(estop_topic, self.update_estop)
            battery_topic = str(settings.get("battery_topic", "")).strip()
            if battery_topic:
                event_bus.subscribe(battery_topic, self.update_battery)

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

    def update_time(self, time_value: str) -> None:
        self._center_time.setText(time_value)

    @Slot(float)
    def _do_update_battery(self, value: float) -> None:
        self._battery_label.setText(f"🔋  {value:.1f}V")
        self._battery_label.setStyleSheet(f"color: {theme.TEXT};")

    @Slot(int, str, object)
    def _do_update_ping(self, idx: int, name: str, ms) -> None:
        if not (0 <= idx < len(self._ping_labels)):
            return
        lbl = self._ping_labels[idx]
        if ms is None:
            lbl.setText(f"[LINK {name}  TIMEOUT]")
            lbl.setStyleSheet(f"color: {theme.RED};")
        else:
            color = theme.GREEN if ms < 50 else theme.AMBER if ms < 150 else theme.RED
            lbl.setText(f"[LINK {name}  {ms:.0f}ms]")
            lbl.setStyleSheet(f"color: {color};")

    @Slot(bool)
    def _do_update_estop(self, active: bool) -> None:
        if active:
            self._estop_label.setText("[E-STOP  ACTIVE]")
            self._estop_label.setStyleSheet(
                f"color: {theme.BG_DEEP}; background: {theme.RED}; "
                f"font-weight: 700; padding: 0 10px; letter-spacing: 1px;"
            )
        else:
            self._estop_label.setText("[E-STOP  NOMINAL]")
            self._estop_label.setStyleSheet(
                f"color: {theme.GREEN}; background: transparent; "
                f"font-weight: 700; letter-spacing: 1px;"
            )
