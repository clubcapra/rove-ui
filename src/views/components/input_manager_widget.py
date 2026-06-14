from __future__ import annotations

from PySide6.QtCore import Qt, QProcess, QProcessEnvironment
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
_STRATEGIES = ["arcade_drive", "tank_drive", "arm_control", "arcade_arm"]

_MAX_LOG_LINES = 500


class InputManagerWidget(QWidget):
    """Subprocess launcher for capra_teleop_interface.

    Spawns `python3 -m capra_teleop_interface` with the configured args and
    streams its stdout/stderr into a live log area.
    """

    def __init__(self, config: dict, event_bus: EventBus | None = None, parent=None) -> None:
        super().__init__(parent)
        self._cfg = config
        self.event_bus = event_bus or EventBus()
        self._process = QProcess(self)
        self._process.readyReadStandardOutput.connect(self._on_stdout)
        self._process.readyReadStandardError.connect(self._on_stderr)
        self._process.finished.connect(self._on_finished)
        self._build_ui()

    # ------------------------------------------------------------------
    # UI

    def _build_ui(self) -> None:
        self.setStyleSheet(f"background: {theme.BG_PANEL}; color: {theme.TEXT};")
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        # ── Title ─────────────────────────────────────────────────────
        title = QLabel("◆ TELEOP CONTROLLER")
        title.setStyleSheet(
            f"color: {theme.CYAN}; font-size: 11px; font-family: 'Courier New'; "
            f"letter-spacing: 1px; background: transparent;"
        )
        root.addWidget(title)

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {theme.BORDER_DIM};")
        root.addWidget(sep)

        # ── Config form ───────────────────────────────────────────────
        form = QVBoxLayout(); form.setSpacing(4)

        self._host_edit = QLineEdit(str(self._cfg.get("host", "192.168.2.5")))
        form.addLayout(self._field("Host", self._host_edit))

        self._port_spin = QSpinBox()
        self._port_spin.setRange(1, 65535)
        self._port_spin.setValue(int(self._cfg.get("port", 9101)))
        form.addLayout(self._field("Port", self._port_spin))

        self._device_combo = QComboBox()
        self._device_combo.addItems(_DEVICES)
        device = str(self._cfg.get("device", "xbox"))
        if device in _DEVICES:
            self._device_combo.setCurrentText(device)
        form.addLayout(self._field("Device", self._device_combo))

        self._strategy_combo = QComboBox()
        self._strategy_combo.addItems(_STRATEGIES)
        strategy = str(self._cfg.get("strategy", "arcade_drive"))
        if strategy in _STRATEGIES:
            self._strategy_combo.setCurrentText(strategy)
        form.addLayout(self._field("Strategy", self._strategy_combo))

        root.addLayout(form)

        # ── Status + buttons ──────────────────────────────────────────
        ctrl = QHBoxLayout(); ctrl.setSpacing(8)

        self._status_dot = QLabel("●")
        self._status_dot.setFixedWidth(16)
        self._status_dot.setStyleSheet(
            f"color: {theme.TEXT_DIM}; font-size: 14px; background: transparent;"
        )
        ctrl.addWidget(self._status_dot)

        self._status_label = QLabel("stopped")
        self._status_label.setStyleSheet(
            f"color: {theme.TEXT_DIM}; font-size: 10px; font-family: 'Courier New'; background: transparent;"
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

        # ── Log area ──────────────────────────────────────────────────
        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setStyleSheet(
            f"background: {theme.BG_DARK}; color: {theme.TEXT}; "
            f"font-family: 'Courier New'; font-size: 10px; border: none;"
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
        lbl.setStyleSheet(f"color: {theme.TEXT_DIM}; font-size: 10px; font-family: 'Courier New'; background: transparent;")
        row.addWidget(lbl)
        row.addWidget(widget, 1)
        return row

    # ------------------------------------------------------------------
    # Process control

    def _build_args(self) -> list[str]:
        args = [
            "-m", "capra_teleop_interface",
            "--host", self._host_edit.text().strip(),
            "--port", str(self._port_spin.value()),
            "--device", self._device_combo.currentText(),
            "--strategy", self._strategy_combo.currentText(),
            "--rate", str(float(self._cfg.get("rate", 100.0))),
            "--no-ui",
        ]
        if self._cfg.get("no_haptics", False):
            args.append("--no-haptics")
        return args

    def _start(self) -> None:
        if self._process.state() != QProcess.ProcessState.NotRunning:
            return

        package_dir = str(self._cfg.get("package_dir", "."))
        self._process.setWorkingDirectory(package_dir)

        env = QProcessEnvironment.systemEnvironment()
        self._process.setProcessEnvironment(env)

        args = self._build_args()
        self._log.appendPlainText(f"$ python3 {' '.join(args)}")
        self._process.start("python3", args)

        if not self._process.waitForStarted(3000):
            self._log.appendPlainText("[ERROR] Failed to start process")
            return

        self._set_running(True)

    def _stop(self) -> None:
        if self._process.state() == QProcess.ProcessState.NotRunning:
            return
        self._process.terminate()
        if not self._process.waitForFinished(3000):
            self._process.kill()

    # ------------------------------------------------------------------
    # Process signals

    def _on_stdout(self) -> None:
        data = self._process.readAllStandardOutput().data().decode(errors="replace")
        for line in data.splitlines():
            self._log.appendPlainText(line)
        self._scroll_to_bottom()

    def _on_stderr(self) -> None:
        data = self._process.readAllStandardError().data().decode(errors="replace")
        for line in data.splitlines():
            self._log.appendPlainText(f"[ERR] {line}")
        self._scroll_to_bottom()

    def _on_finished(self, exit_code: int, exit_status: QProcess.ExitStatus) -> None:
        self._set_running(False)
        self._log.appendPlainText(f"[process exited: code={exit_code}]")

    def _scroll_to_bottom(self) -> None:
        sb = self._log.verticalScrollBar()
        sb.setValue(sb.maximum())

    # ------------------------------------------------------------------
    # State helpers

    def _set_running(self, running: bool) -> None:
        color = "#44ff44" if running else theme.TEXT_DIM
        label = "running" if running else "stopped"
        self._status_dot.setStyleSheet(
            f"color: {color}; font-size: 14px; background: transparent;"
        )
        self._status_label.setText(label)
        self._status_label.setStyleSheet(
            f"color: {color}; font-size: 10px; font-family: 'Courier New'; background: transparent;"
        )
        self._start_btn.setEnabled(not running)
        self._stop_btn.setEnabled(running)
        self._host_edit.setEnabled(not running)
        self._port_spin.setEnabled(not running)
        self._device_combo.setEnabled(not running)
        self._strategy_combo.setEnabled(not running)

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
