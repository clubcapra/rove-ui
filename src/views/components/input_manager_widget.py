from __future__ import annotations

import threading
from typing import Optional

from PySide6.QtCore import Qt, QTimer, Signal, QObject
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
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
_MAX_LOG_LINES = 600


class _Emitter(QObject):
    log_line = Signal(str)
    status_changed = Signal(bool)   # True = running


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
        self._emitter = _Emitter()
        self._emitter.log_line.connect(self._append_log)
        self._emitter.status_changed.connect(self._set_running)

        self._build_ui()
        self.event_bus.subscribe("estop_status", self._on_estop)

    # ------------------------------------------------------------------
    # UI

    def _build_ui(self) -> None:
        self.setStyleSheet(f"background: {theme.BG_PANEL}; color: {theme.TEXT};")
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        title = QLabel("◆ TELEOP CONTROLLER")
        title.setStyleSheet(
            f"color: {theme.CYAN}; font-size: 11px; font-family: 'Courier New'; "
            "letter-spacing: 1px; background: transparent;"
        )
        root.addWidget(title)

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {theme.BORDER_DIM};")
        root.addWidget(sep)

        # ── Config ────────────────────────────────────────────────────
        form = QVBoxLayout(); form.setSpacing(4)

        self._host_edit = QLineEdit(str(self._cfg.get("host", "192.168.2.5")))
        form.addLayout(self._field("Host", self._host_edit))

        self._port_spin = QSpinBox()
        self._port_spin.setRange(1, 65535)
        self._port_spin.setValue(int(self._cfg.get("port", 9101)))
        form.addLayout(self._field("Port", self._port_spin))

        self._device_combo = QComboBox()
        self._device_combo.addItems(_DEVICES)
        dev = str(self._cfg.get("device", "xbox"))
        if dev in _DEVICES:
            self._device_combo.setCurrentText(dev)
        form.addLayout(self._field("Device", self._device_combo))

        self._strategy_combo = QComboBox()
        self._strategy_combo.addItems(list(_STRATEGIES.keys()))
        strat = str(self._cfg.get("strategy", "arcade_drive"))
        if strat in _STRATEGIES:
            self._strategy_combo.setCurrentText(strat)
        form.addLayout(self._field("Strategy", self._strategy_combo))

        self._rate_spin = QSpinBox()
        self._rate_spin.setRange(1, 200)
        self._rate_spin.setSuffix(" Hz")
        self._rate_spin.setValue(int(self._cfg.get("rate", 100)))
        form.addLayout(self._field("Rate", self._rate_spin))

        root.addLayout(form)

        # ── Status row ────────────────────────────────────────────────
        ctrl = QHBoxLayout(); ctrl.setSpacing(8)

        self._status_dot = QLabel("●")
        self._status_dot.setFixedWidth(16)
        self._status_dot.setStyleSheet(
            f"color: {theme.TEXT_DIM}; font-size: 14px; background: transparent;"
        )
        ctrl.addWidget(self._status_dot)

        self._status_label = QLabel("stopped")
        self._status_label.setStyleSheet(
            f"color: {theme.TEXT_DIM}; font-size: 10px; "
            "font-family: 'Courier New'; background: transparent;"
        )
        ctrl.addWidget(self._status_label, 1)

        self._start_btn = QPushButton("START")
        self._start_btn.setStyleSheet(_btn_style("#44ff44"))
        self._start_btn.clicked.connect(self._start)
        ctrl.addWidget(self._start_btn)

        self._stop_btn = QPushButton("STOP")
        self._stop_btn.setStyleSheet(_btn_style("#ff6666"))
        self._stop_btn.setEnabled(False)
        self._stop_btn.clicked.connect(self._stop)
        ctrl.addWidget(self._stop_btn)

        root.addLayout(ctrl)

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
        clr.setStyleSheet(_btn_style(theme.TEXT_DIM))
        clr.clicked.connect(self._log.clear)
        root.addWidget(clr)

    def _field(self, label: str, widget: QWidget) -> QHBoxLayout:
        row = QHBoxLayout(); row.setSpacing(8)
        lbl = QLabel(label)
        lbl.setFixedWidth(70)
        lbl.setStyleSheet(
            f"color: {theme.TEXT_DIM}; font-size: 10px; "
            "font-family: 'Courier New'; background: transparent;"
        )
        row.addWidget(lbl)
        row.addWidget(widget, 1)
        return row

    # ------------------------------------------------------------------
    # Controller lifecycle

    def _start(self) -> None:
        if self._thread and self._thread.is_alive():
            return

        host = self._host_edit.text().strip()
        port = self._port_spin.value()
        device_key = self._device_combo.currentText()
        strategy_key = self._strategy_combo.currentText()
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
            )
        except Exception as exc:
            self._append_log(f"[ERROR] Failed to build controller: {exc}")
            return

        self._emitter.status_changed.emit(True)

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
    # EventBus callbacks

    def _on_estop(self, value) -> None:
        if str(value) == "1":
            self._stop()

    # ------------------------------------------------------------------
    # UI helpers (called from Qt thread)

    def _append_log(self, text: str) -> None:
        self._log.appendPlainText(text)
        sb = self._log.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _set_running(self, running: bool) -> None:
        color = "#44ff44" if running else theme.TEXT_DIM
        label = "running" if running else "stopped"
        self._status_dot.setStyleSheet(
            f"color: {color}; font-size: 14px; background: transparent;"
        )
        self._status_label.setText(label)
        self._status_label.setStyleSheet(
            f"color: {color}; font-size: 10px; "
            "font-family: 'Courier New'; background: transparent;"
        )
        self._start_btn.setEnabled(not running)
        self._stop_btn.setEnabled(running)
        self._host_edit.setEnabled(not running)
        self._port_spin.setEnabled(not running)
        self._device_combo.setEnabled(not running)
        self._strategy_combo.setEnabled(not running)
        self._rate_spin.setEnabled(not running)

    def closeEvent(self, event) -> None:
        self._stop()
        super().closeEvent(event)


def _btn_style(accent: str = "") -> str:
    c = accent or theme.TEXT_DIM
    return (
        f"QPushButton {{ background: {theme.BG_DARK}; color: {c}; "
        f"border: 1px solid {theme.BORDER_DIM}; border-radius: 3px; "
        f"padding: 4px 12px; font-size: 11px; font-family: 'Courier New'; }}"
        f"QPushButton:hover {{ border-color: {c}; }}"
        f"QPushButton:pressed {{ background: {theme.BG_PANEL}; }}"
        f"QPushButton:disabled {{ color: {theme.TEXT_DIM}; border-color: {theme.BORDER_DIM}; }}"
    )
