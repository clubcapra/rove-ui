from __future__ import annotations

import threading
import time
from typing import Optional

from PySide6.QtCore import Signal, QObject
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from src.controller.event_bus import EventBus
from src.views import theme

_DEVICES = ["xbox", "steamdeck"]
_STRATEGIES = {
    "arcade_drive": "ArcadeDriveStrategy",
    "tank_drive":   "TankDriveStrategy",
    "arm_control":  "ArmControlStrategy",
    "arcade_arm":   "ArcadeArmStrategy",
}
_STRATEGY_LABELS = {
    "arcade_drive": "Arcade Drive",
    "tank_drive":   "Tank Drive",
    "arm_control":  "Arm Control",
    "arcade_arm":   "Arcade + Arm",
}
_MAX_LOG_LINES = 600


class _Emitter(QObject):
    log_line = Signal(str)
    status_changed = Signal(bool)   # True = running
    estop_changed = Signal(bool)    # True = E-stop engaged


class InputManagerWidget(QWidget):
    """Teleop controller manager.

    Builds and runs an xbox/steamdeck controller (from src.controller.teleop)
    in a background thread, streaming RoveControl protobuf at 100 Hz.
    """

    def __init__(self, config: dict, event_bus: EventBus | None = None, parent=None) -> None:
        super().__init__(parent)
        self._cfg = config
        self.event_bus = event_bus or EventBus()
        self._controller = None
        self._thread: Optional[threading.Thread] = None
        self._last_log_t = 0.0
        self._emitter = _Emitter()
        self._emitter.log_line.connect(self._append_log)
        self._emitter.status_changed.connect(self._set_running)
        self._emitter.estop_changed.connect(self._set_estop_ui)
        self._active_strategy_key: str = str(self._cfg.get("strategy", "arcade_drive"))
        self._gripper_latch: int = 0  # survives stop/start cycles

        self._build_ui()
        self.event_bus.subscribe("estop_status", self._on_estop)

    # ------------------------------------------------------------------
    # UI

    def _build_ui(self) -> None:
        self.setStyleSheet(f"background: {theme.BG_PANEL}; color: {theme.TEXT};")
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        title = QLabel("◆ TELEOP CONTROLLER")
        title.setStyleSheet(
            f"color: {theme.CYAN}; font-size: 12px; font-family: 'Courier New'; "
            "letter-spacing: 1px; background: transparent;"
        )
        root.addWidget(title)

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {theme.BORDER_DIM};")
        root.addWidget(sep)

        # ── Config ────────────────────────────────────────────────────
        form = QVBoxLayout(); form.setSpacing(6)

        self._host_edit = QLineEdit(str(self._cfg.get("host", "192.168.2.2")))
        self._host_edit.setStyleSheet(_input_style())
        form.addLayout(self._field("Host", self._host_edit))

        self._port_spin = QSpinBox()
        self._port_spin.setRange(1, 65535)
        # 5050 is the rover teleop control port (NOT 5005, which is the
        # gripper command port — see capra_teleop_interface default.yaml).
        self._port_spin.setValue(int(self._cfg.get("port", 5050)))
        self._port_spin.setStyleSheet(_input_style())
        form.addLayout(self._field("Port", self._port_spin))

        self._device_combo = QComboBox()
        self._device_combo.addItems(_DEVICES)
        dev = str(self._cfg.get("device", "xbox"))
        if dev in _DEVICES:
            self._device_combo.setCurrentText(dev)
        self._device_combo.setStyleSheet(_input_style())
        form.addLayout(self._field("Device", self._device_combo))

        self._rate_spin = QSpinBox()
        self._rate_spin.setRange(1, 200)
        self._rate_spin.setSuffix(" Hz")
        self._rate_spin.setValue(int(self._cfg.get("rate", 100)))
        self._rate_spin.setStyleSheet(_input_style())
        form.addLayout(self._field("Rate", self._rate_spin))

        root.addLayout(form)

        # ── Strategy selector (always live, hot-swaps while running) ──
        strat_label = QLabel("STRATEGY")
        strat_label.setStyleSheet(
            f"color: {theme.TEXT_DIM}; font-size: 10px; font-family: 'Courier New'; "
            "letter-spacing: 1px; background: transparent;"
        )
        root.addWidget(strat_label)

        self._strategy_btns: dict[str, QPushButton] = {}
        strat_grid = QGridLayout()
        strat_grid.setSpacing(5)
        strat_grid.setContentsMargins(0, 0, 0, 0)
        keys = list(_STRATEGIES.keys())
        for i, key in enumerate(keys):
            btn = QPushButton(_STRATEGY_LABELS[key])
            btn.setCheckable(True)
            btn.setMinimumHeight(44)
            btn.clicked.connect(lambda _checked, k=key: self._on_strategy_selected(k))
            self._strategy_btns[key] = btn
            strat_grid.addWidget(btn, i // 2, i % 2)

        active = self._active_strategy_key
        if active not in self._strategy_btns:
            active = keys[0]
            self._active_strategy_key = active
        for k, b in self._strategy_btns.items():
            b.setChecked(k == active)
            self._style_strategy_btn(b, k == active)

        root.addLayout(strat_grid)

        # ── Status row ────────────────────────────────────────────────
        ctrl = QHBoxLayout(); ctrl.setSpacing(8)

        self._status_dot = QLabel("●")
        self._status_dot.setFixedWidth(18)
        self._status_dot.setStyleSheet(
            f"color: {theme.TEXT_DIM}; font-size: 16px; background: transparent;"
        )
        ctrl.addWidget(self._status_dot)

        self._status_label = QLabel("stopped")
        self._status_label.setStyleSheet(
            f"color: {theme.TEXT_DIM}; font-size: 11px; "
            "font-family: 'Courier New'; background: transparent;"
        )
        ctrl.addWidget(self._status_label, 1)

        self._start_btn = QPushButton("START")
        self._start_btn.setMinimumHeight(60)
        self._start_btn.setStyleSheet(_btn_style("#44ff44", large=True))
        self._start_btn.clicked.connect(self._start)
        ctrl.addWidget(self._start_btn)

        self._stop_btn = QPushButton("STOP")
        self._stop_btn.setMinimumHeight(60)
        self._stop_btn.setStyleSheet(_btn_style("#ff6666", large=True))
        self._stop_btn.setEnabled(False)
        self._stop_btn.clicked.connect(self._stop)
        ctrl.addWidget(self._stop_btn)

        root.addLayout(ctrl)

        # ── E-stop ────────────────────────────────────────────────────
        # Latching: engaging zeroes all motion (gripper kept) and keeps
        # streaming zeros so the robot actively halts; RESUME clears it.
        self._estop_btn = QPushButton("⏻  E-STOP")
        self._estop_btn.setMinimumHeight(54)
        self._estop_btn.setEnabled(False)
        self._estop_btn.clicked.connect(self._toggle_estop)
        self._style_estop(False)
        root.addWidget(self._estop_btn)

        sep2 = QFrame(); sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet(f"color: {theme.BORDER_DIM};")
        root.addWidget(sep2)

        # ── Log ───────────────────────────────────────────────────────
        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setStyleSheet(
            f"background: {theme.BG_DARK}; color: {theme.TEXT}; "
            "font-family: 'Courier New'; font-size: 10px; border: none;"
        )
        self._log.setMaximumBlockCount(_MAX_LOG_LINES)
        root.addWidget(self._log, 1)

        clr = QPushButton("CLEAR LOG")
        clr.setMinimumHeight(36)
        clr.setStyleSheet(_btn_style(theme.TEXT_DIM))
        clr.clicked.connect(self._log.clear)
        root.addWidget(clr)

    def _field(self, label: str, widget: QWidget) -> QHBoxLayout:
        row = QHBoxLayout(); row.setSpacing(10)
        lbl = QLabel(label)
        lbl.setFixedWidth(56)
        lbl.setStyleSheet(
            f"color: {theme.TEXT_DIM}; font-size: 11px; "
            "font-family: 'Courier New'; background: transparent;"
        )
        row.addWidget(lbl)
        row.addWidget(widget, 1)
        return row

    def _style_strategy_btn(self, btn: QPushButton, active: bool) -> None:
        if active:
            btn.setStyleSheet(
                f"QPushButton {{ background: {theme.BG_DARK}; color: {theme.CYAN}; "
                f"border: 2px solid {theme.CYAN}; border-radius: 4px; "
                f"font-size: 13px; font-family: 'Courier New'; font-weight: bold; }}"
                f"QPushButton:hover {{ background: {theme.BG_SURFACE}; }}"
            )
        else:
            btn.setStyleSheet(
                f"QPushButton {{ background: {theme.BG_DARK}; color: {theme.TEXT}; "
                f"border: 1px solid {theme.BORDER}; border-radius: 4px; "
                f"font-size: 13px; font-family: 'Courier New'; }}"
                f"QPushButton:hover {{ border-color: {theme.CYAN}; color: {theme.CYAN}; }}"
                f"QPushButton:pressed {{ background: {theme.BG_SURFACE}; }}"
            )

    # ------------------------------------------------------------------
    # Strategy hot-swap

    def _on_strategy_selected(self, key: str) -> None:
        if key == self._active_strategy_key:
            self._strategy_btns[key].setChecked(True)
            return

        self._active_strategy_key = key
        for k, b in self._strategy_btns.items():
            b.setChecked(k == key)
            self._style_strategy_btn(b, k == key)

        if self._controller is not None:
            try:
                from src.controller.teleop.strategies import (
                    ArcadeDriveStrategy, TankDriveStrategy,
                    ArmControlStrategy, ArcadeArmStrategy,
                )
                strategy_map = {
                    "arcade_drive": ArcadeDriveStrategy,
                    "tank_drive":   TankDriveStrategy,
                    "arm_control":  ArmControlStrategy,
                    "arcade_arm":   ArcadeArmStrategy,
                }
                self._controller.set_strategy(strategy_map[key]())
                self._append_log(f"→ strategy: {key}")
            except Exception as exc:
                self._append_log(f"[ERROR] strategy switch failed: {exc}")

    # ------------------------------------------------------------------
    # Controller lifecycle

    def _start(self) -> None:
        if self._thread and self._thread.is_alive():
            return

        host = self._host_edit.text().strip()
        port = self._port_spin.value()
        device_key = self._device_combo.currentText()
        strategy_key = self._active_strategy_key
        rate = float(self._rate_spin.value())
        no_haptics = bool(self._cfg.get("no_haptics", False))

        self._append_log(f"Starting {device_key} / {strategy_key} → {host}:{port}")

        try:
            from src.controller.teleop.controllers import XboxController, SteamDeckController
            from src.controller.teleop.strategies import (
                ArcadeDriveStrategy, TankDriveStrategy,
                ArmControlStrategy, ArcadeArmStrategy,
            )
            from src.controller.teleop.network.udp_sender import UdpSender, UdpEndpoint

            strategy_map = {
                "arcade_drive": ArcadeDriveStrategy,
                "tank_drive":   TankDriveStrategy,
                "arm_control":  ArmControlStrategy,
                "arcade_arm":   ArcadeArmStrategy,
            }
            device_map = {
                "xbox":       XboxController,
                "steamdeck":  SteamDeckController,
            }

            endpoint = UdpEndpoint(host=host, port=port)
            sender = UdpSender(endpoint)
            strategy = strategy_map[strategy_key]()
            device_cls = device_map[device_key]

            self._controller = device_cls(
                sender=sender,
                strategy=strategy,
                rate_hz=rate,
                haptics_enabled=not no_haptics,
                on_frame_sent=self._on_frame_sent,
                initial_gripper_position=self._gripper_latch,
            )
        except Exception as exc:
            self._append_log(f"[ERROR] Failed to build controller: {exc}")
            return

        self._last_log_t = 0.0
        self._emitter.status_changed.emit(True)
        self._emitter.estop_changed.emit(False)

        def _run():
            try:
                self._controller.run()
            except Exception as exc:
                self._emitter.log_line.emit(f"[ERROR] {exc}")
            finally:
                self._emitter.status_changed.emit(False)
                self._emitter.log_line.emit("[controller stopped]")

        self._thread = threading.Thread(target=_run, daemon=True, name="teleop-controller")
        self._thread.start()

    def _stop(self) -> None:
        if self._controller is not None:
            self._controller.stop()

    # ------------------------------------------------------------------
    # E-stop

    def _toggle_estop(self) -> None:
        if self._controller is None:
            return
        engage = not self._controller.is_estopped()
        self._controller.set_estop(engage)
        self._append_log("*** E-STOP ENGAGED ***" if engage else "--- E-stop cleared (RESUME) ---")
        self._set_estop_ui(engage)

    def _set_estop_ui(self, engaged: bool) -> None:
        self._estop_btn.setText("RESUME" if engaged else "⏻  E-STOP")
        self._style_estop(engaged)

    def _style_estop(self, engaged: bool) -> None:
        # Red when armed (click to halt); amber when latched (click to resume).
        accent = "#ffaa00" if engaged else "#ff3333"
        self._estop_btn.setStyleSheet(
            f"QPushButton {{ background: {theme.BG_DARK}; color: {accent}; "
            f"border: 2px solid {accent}; border-radius: 4px; padding: 10px; "
            f"font-size: 15px; font-weight: bold; font-family: 'Courier New'; "
            "letter-spacing: 2px; }"
            f"QPushButton:hover {{ background: {accent}; color: {theme.BG_DARK}; }}"
            f"QPushButton:disabled {{ color: {theme.TEXT_DIM}; border-color: {theme.BORDER_DIM}; }}"
        )

    # ------------------------------------------------------------------
    # EventBus callbacks

    def _on_estop(self, value) -> None:
        # Drive the latch (engage on "1", clear otherwise) so an app-wide
        # E-stop signal halts the robot the same way the on-page button does,
        # instead of killing the controller thread outright.
        if self._controller is None:
            return
        self._controller.set_estop(str(value) == "1")
        self._emitter.estop_changed.emit(str(value) == "1")

    # ------------------------------------------------------------------
    # Frame logging (called from the controller thread)

    def _on_frame_sent(self, msg, changed: bool) -> None:
        # Runs on the teleop thread. Log every change immediately; throttle
        # held-heartbeat frames to ~2 s so the pane doesn't flood. Marshal to
        # the Qt thread via the emitter signal.
        now = time.monotonic()
        if not changed and (now - self._last_log_t) < 2.0:
            return
        self._last_log_t = now
        from src.controller.teleop.frames import format_frame
        estopped = self._controller is not None and self._controller.is_estopped()
        marker = "[ESTOP]" if estopped else ("→" if changed else "·")
        line = f"{marker} {format_frame(msg)}"
        self._emitter.log_line.emit(line)
        print(f"[teleop] {line}")  # also to stdout console

    # ------------------------------------------------------------------
    # UI helpers (called from Qt thread)

    def _append_log(self, text: str) -> None:
        self._log.appendPlainText(text)
        sb = self._log.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _set_running(self, running: bool) -> None:
        if not running and self._controller is not None:
            self._gripper_latch = self._controller.gripper_position

        color = "#44ff44" if running else theme.TEXT_DIM
        label = "running" if running else "stopped"
        self._status_dot.setStyleSheet(
            f"color: {color}; font-size: 16px; background: transparent;"
        )
        self._status_label.setText(label)
        self._status_label.setStyleSheet(
            f"color: {color}; font-size: 11px; "
            "font-family: 'Courier New'; background: transparent;"
        )
        self._start_btn.setEnabled(not running)
        self._stop_btn.setEnabled(running)
        self._estop_btn.setEnabled(running)
        if not running:
            self._set_estop_ui(False)
        # Config fields locked while running; strategy buttons are always live.
        self._host_edit.setEnabled(not running)
        self._port_spin.setEnabled(not running)
        self._device_combo.setEnabled(not running)
        self._rate_spin.setEnabled(not running)

    def closeEvent(self, event) -> None:
        self._stop()
        super().closeEvent(event)


def _input_style() -> str:
    return (
        f"background: {theme.BG_DARK}; color: {theme.TEXT}; "
        f"border: 1px solid {theme.BORDER}; border-radius: 3px; "
        f"padding: 6px 10px; font-size: 13px; font-family: 'Courier New'; "
        "min-height: 36px;"
    )


def _btn_style(accent: str = "", large: bool = False) -> str:
    c = accent or theme.TEXT_DIM
    padding = "12px 24px" if large else "8px 18px"
    font_size = "15px" if large else "13px"
    border = f"2px solid {theme.BORDER_DIM}" if large else f"1px solid {theme.BORDER_DIM}"
    return (
        f"QPushButton {{ background: {theme.BG_DARK}; color: {c}; "
        f"border: {border}; border-radius: 4px; "
        f"padding: {padding}; font-size: {font_size}; font-weight: bold; font-family: 'Courier New'; }}"
        f"QPushButton:hover {{ border-color: {c}; background: {theme.BG_SURFACE}; }}"
        f"QPushButton:pressed {{ background: {theme.BG_PANEL}; }}"
        f"QPushButton:disabled {{ color: {theme.TEXT_DIM}; border-color: {theme.BORDER_DIM}; }}"
    )
