from __future__ import annotations

import glob
import socket
import time as _time
from datetime import datetime
from pathlib import Path
from threading import Thread

from PySide6.QtCore import Qt, QTimer, Signal, Slot
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QWidget

from src.views import theme


def _read_system_battery() -> float | None:
    try:
        import psutil
        b = psutil.sensors_battery()
        return b.percent if b else None
    except Exception:
        pass
    for cap in glob.glob("/sys/class/power_supply/BAT*/capacity"):
        try:
            return float(Path(cap).read_text().strip())
        except Exception:
            pass
    return None


def _ping_ms(host: str, timeout_s: float = 1.0) -> float | None:
    try:
        t0 = _time.perf_counter()
        with socket.create_connection((host, 80), timeout=timeout_s):
            pass
        return (_time.perf_counter() - t0) * 1000
    except Exception:
        return None


class Header(QWidget):
    _battery_signal: Signal = Signal(int, float)
    _ping_signal:    Signal = Signal(int, str, object)
    _estop_signal:   Signal = Signal(bool)
    _mapping_signal: Signal = Signal(str, str)   # (text, css-color)

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

        self._mapping_label = QLabel("[MAP  --]")
        self._mapping_label.setStyleSheet(f"color: {theme.TEXT_DIM};")
        left.addWidget(self._mapping_label)

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

        # ── RIGHT: batteries ──────────────────────────────────────────────
        right = QHBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(18)
        right.addStretch()

        # Build battery list — support legacy single `battery_topic` or new `batteries` list
        batteries_cfg: list[dict] = list(settings.get("batteries", []))
        legacy_topic = str(settings.get("battery_topic", "")).strip()
        if not batteries_cfg and legacy_topic:
            batteries_cfg = [{"name": "BAT", "topic": legacy_topic, "unit": "V"}]

        self._battery_labels: list[QLabel] = []
        self._battery_units:  list[str]    = []
        for bat in batteries_cfg:
            name = str(bat.get("name", "BAT")).upper()
            unit = str(bat.get("unit", "V"))
            lbl  = QLabel(f"🔋 {name}  --{unit}")
            lbl.setStyleSheet(f"color: {theme.TEXT_DIM};")
            right.addWidget(lbl)
            self._battery_labels.append(lbl)
            self._battery_units.append(unit)

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
        self._mapping_signal.connect(self._do_update_mapping)

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

            mapping_cfg = settings.get("mapping_status", {})
            state_topic = str(mapping_cfg.get("state_topic", "")).strip()
            nodes_topic = str(mapping_cfg.get("nodes_topic", "")).strip()
            lc_topic    = str(mapping_cfg.get("lc_topic",    "")).strip()
            if state_topic or nodes_topic:
                self._map_state = "--"
                self._map_nodes: str = "--"
                self._map_lc:    str = "--"

                def _push_map():
                    s = self._map_state
                    color = (theme.GREEN if s == "running"
                             else theme.AMBER if s in ("paused", "initializing")
                             else theme.TEXT_DIM)
                    txt = f"[MAP  {s.upper()}"
                    if self._map_nodes != "--":
                        txt += f"  {self._map_nodes}n"
                    if self._map_lc != "--":
                        txt += f"  {self._map_lc}lc"
                    txt += "]"
                    self._mapping_signal.emit(txt, color)

                if state_topic:
                    event_bus.subscribe(
                        state_topic,
                        lambda v: (setattr(self, "_map_state", str(v).lower()), _push_map()),
                    )
                if nodes_topic:
                    event_bus.subscribe(
                        nodes_topic,
                        lambda v: (setattr(self, "_map_nodes",
                                           str(int(v)) if isinstance(v, (int, float)) else str(v)),
                                   _push_map()),
                    )
                if lc_topic:
                    event_bus.subscribe(
                        lc_topic,
                        lambda v: (setattr(self, "_map_lc",
                                           str(int(v)) if isinstance(v, (int, float)) else str(v)),
                                   _push_map()),
                    )

            for bat_idx, bat in enumerate(batteries_cfg):
                topic = str(bat.get("topic", "")).strip()
                if not topic:
                    continue
                if bat.get("source") == "system":
                    interval = int(bat.get("poll_interval_s", 30))
                    def _sys_loop(t=topic, iv=interval, eb=event_bus):
                        import time
                        while True:
                            v = _read_system_battery()
                            if v is not None:
                                eb.publish_sync(t, v)
                            time.sleep(iv)
                    Thread(target=_sys_loop, daemon=True).start()
                    event_bus.subscribe(topic, lambda v, i=bat_idx: self._on_battery(i, v))
                else:
                    event_bus.subscribe(
                        topic,
                        lambda v, i=bat_idx: self._on_battery(i, v),
                    )

    def _on_battery(self, idx: int, value) -> None:
        try:
            self._battery_signal.emit(idx, float(value))
        except (TypeError, ValueError):
            pass

    def update_estop(self, active) -> None:
        try:
            is_active = bool(int(active))
        except (TypeError, ValueError):
            is_active = bool(active)
        self._estop_signal.emit(is_active)

    def update_time(self, time_value: str) -> None:
        self._center_time.setText(time_value)

    @staticmethod
    def _current_time() -> str:
        return datetime.now().strftime("%H:%M:%S")

    @Slot(int, float)
    def _do_update_battery(self, idx: int, value: float) -> None:
        if not (0 <= idx < len(self._battery_labels)):
            return
        lbl  = self._battery_labels[idx]
        unit = self._battery_units[idx]
        fmt  = f"{value:.0f}" if unit == "%" else f"{value:.1f}"
        lbl.setText(f"🔋 {self._bat_name(idx)}  {fmt}{unit}")
        lbl.setStyleSheet(f"color: {theme.TEXT};")

    def _bat_name(self, idx: int) -> str:
        try:
            return self._battery_labels[idx].text().split()[1]
        except (IndexError, AttributeError):
            return "BAT"

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

    @Slot(str, str)
    def _do_update_mapping(self, text: str, color: str) -> None:
        self._mapping_label.setText(text)
        self._mapping_label.setStyleSheet(f"color: {color};")

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
