from __future__ import annotations

import os

import yaml
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from src.controller.event_bus import EventBus
from src.views import theme

_SETTINGS_FILE = os.path.expanduser("~/.rove_input_manager.yaml")


class InputManagerWidget(QWidget):
    """Dark-theme gamepad manager: load YAML config, shows per-device status."""

    def __init__(self, config: dict, event_bus: EventBus | None = None, parent=None) -> None:
        super().__init__(parent)
        self._cfg = config
        self.event_bus = event_bus or EventBus()
        self._manager = None
        self._config_data: dict = {"devices": []}
        self._device_rows: list[dict] = []

        self._build_ui()
        self._init_manager()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh_status)
        self._timer.start(500)

    # ------------------------------------------------------------------
    # Setup

    def _init_manager(self) -> None:
        from src.controller.device_manager import DeviceManager
        self._manager = DeviceManager(self.event_bus)

        udp_host = self._cfg.get("udp_host", "")
        udp_port = int(self._cfg.get("udp_port", 0))
        if udp_host and udp_port:
            self._manager.configure_udp(udp_host, udp_port)

        # Resolve default config: widget config → persisted path
        path = self._cfg.get("default_config", "")
        if not path and os.path.exists(_SETTINGS_FILE):
            try:
                with open(_SETTINGS_FILE) as f:
                    path = (yaml.safe_load(f) or {}).get("last_config", "")
            except Exception:
                pass

        if path and os.path.exists(path):
            self._load_config_file(path)

    def _build_ui(self) -> None:
        self.setStyleSheet(f"background: {theme.BG_PANEL}; color: {theme.TEXT};")
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        # ── Header row ────────────────────────────────────────────────
        hdr = QHBoxLayout()
        hdr.setSpacing(8)

        title = QLabel("◆ INPUT MANAGER")
        title.setStyleSheet(
            f"color: {theme.CYAN}; font-size: 11px; font-family: 'Courier New'; "
            f"letter-spacing: 1px; background: transparent;"
        )
        hdr.addWidget(title)
        hdr.addStretch()

        load_btn = QPushButton("LOAD CONFIG")
        load_btn.setStyleSheet(_btn_style(theme.CYAN))
        load_btn.clicked.connect(self._on_load_click)
        hdr.addWidget(load_btn)

        root.addLayout(hdr)

        self._file_label = QLabel("no config")
        self._file_label.setStyleSheet(
            f"color: {theme.TEXT_DIM}; font-size: 10px; font-family: 'Courier New';"
        )
        root.addWidget(self._file_label)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {theme.BORDER_DIM};")
        root.addWidget(sep)

        # ── UDP indicator ─────────────────────────────────────────────
        self._udp_label = QLabel()
        udp_host = self._cfg.get("udp_host", "")
        udp_port = self._cfg.get("udp_port", 0)
        if udp_host and udp_port:
            self._udp_label.setText(f"UDP → {udp_host}:{udp_port}")
            self._udp_label.setStyleSheet(
                f"color: {theme.CYAN}; font-size: 10px; font-family: 'Courier New';"
            )
        else:
            self._udp_label.setText("UDP: not configured")
            self._udp_label.setStyleSheet(
                f"color: {theme.TEXT_DIM}; font-size: 10px; font-family: 'Courier New';"
            )
        root.addWidget(self._udp_label)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet(f"color: {theme.BORDER_DIM};")
        root.addWidget(sep2)

        # ── Device list ───────────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self._list_widget = QWidget()
        self._list_widget.setStyleSheet("background: transparent;")
        self._list_layout = QVBoxLayout(self._list_widget)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(4)
        self._list_layout.addStretch()

        scroll.setWidget(self._list_widget)
        root.addWidget(scroll, 1)

        # ── Empty state label ─────────────────────────────────────────
        self._empty_label = QLabel("No devices — load a YAML config")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setStyleSheet(
            f"color: {theme.TEXT_DIM}; font-size: 11px; font-family: 'Courier New';"
        )
        root.addWidget(self._empty_label)

    # ------------------------------------------------------------------
    # Config loading

    def _on_load_click(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Input Config", "", "YAML Files (*.yaml *.yml);;All Files (*)"
        )
        if path:
            self._load_config_file(path)

    def _load_config_file(self, path: str) -> None:
        try:
            with open(path) as f:
                config_data = yaml.safe_load(f) or {}
            self._config_data = config_data
            self._file_label.setText(os.path.basename(path))
            self._file_label.setStyleSheet(
                f"color: {theme.TEXT}; font-size: 10px; font-family: 'Courier New';"
            )
            self._manager.load_config(config_data)
            self._rebuild_device_list()
            try:
                with open(_SETTINGS_FILE, "w") as f:
                    yaml.dump({"last_config": path}, f)
            except Exception:
                pass
        except Exception as exc:
            self._file_label.setText(f"ERROR: {exc}")
            self._file_label.setStyleSheet(
                "color: #ff4444; font-size: 10px; font-family: 'Courier New';"
            )

    # ------------------------------------------------------------------
    # Device list

    def _rebuild_device_list(self) -> None:
        for row in self._device_rows:
            row["widget"].deleteLater()
        self._device_rows.clear()

        while self._list_layout.count():
            self._list_layout.takeAt(0)

        devices = self._config_data.get("devices", [])
        self._empty_label.setVisible(not devices)

        for dev in devices:
            alias = dev.get("alias", "unknown")
            name = dev.get("name", alias)
            enabled = dev.get("enabled", False)

            row_w = QWidget()
            row_w.setStyleSheet(
                f"QWidget {{ background: {theme.BG_DARK}; border: 1px solid {theme.BORDER_DIM}; "
                f"border-radius: 4px; }}"
            )
            row_l = QHBoxLayout(row_w)
            row_l.setContentsMargins(8, 6, 8, 6)
            row_l.setSpacing(8)

            dot = QLabel("●")
            dot.setFixedWidth(16)
            dot.setStyleSheet(
                f"color: {'#44ff44' if enabled else theme.TEXT_DIM}; "
                f"font-size: 14px; background: transparent; border: none;"
            )
            row_l.addWidget(dot)

            col = QVBoxLayout()
            col.setSpacing(1)
            name_lbl = QLabel(name)
            name_lbl.setStyleSheet(
                f"color: {theme.TEXT}; font-size: 12px; font-weight: bold; "
                f"background: transparent; border: none;"
            )
            alias_lbl = QLabel(f"joy/{alias}")
            alias_lbl.setStyleSheet(
                f"color: {theme.TEXT_DIM}; font-size: 10px; "
                f"font-family: 'Courier New'; background: transparent; border: none;"
            )
            col.addWidget(name_lbl)
            col.addWidget(alias_lbl)
            row_l.addLayout(col, 1)

            toggle_btn = QPushButton("DISABLE" if enabled else "ENABLE")
            toggle_btn.setStyleSheet(
                _btn_style("#ff6666") if enabled else _btn_style("#44ff44")
            )
            toggle_btn.clicked.connect(lambda _, a=alias: self._toggle_device(a))
            row_l.addWidget(toggle_btn)

            self._list_layout.addWidget(row_w)
            self._device_rows.append({"widget": row_w, "alias": alias, "dot": dot, "toggle": toggle_btn})

        self._list_layout.addStretch()

    def _toggle_device(self, alias: str) -> None:
        for dev in self._config_data.get("devices", []):
            if dev.get("alias") == alias:
                dev["enabled"] = not dev.get("enabled", False)
                break
        self._manager.load_config(self._config_data)
        self._rebuild_device_list()

    # ------------------------------------------------------------------
    # Status polling

    def _refresh_status(self) -> None:
        if not self._manager:
            return
        status_map = {s["alias"]: s for s in self._manager.get_status()}
        for row in self._device_rows:
            s = status_map.get(row["alias"], {})
            enabled = s.get("enabled", False)
            connected = s.get("connected", False)
            if connected:
                color = "#44ff44"
            elif enabled:
                color = "#ffaa00"
            else:
                color = theme.TEXT_DIM
            row["dot"].setStyleSheet(
                f"color: {color}; font-size: 14px; background: transparent; border: none;"
            )


def _btn_style(accent: str = "") -> str:
    c = accent or theme.TEXT_DIM
    return (
        f"QPushButton {{ background: {theme.BG_DARK}; color: {c}; "
        f"border: 1px solid {theme.BORDER_DIM}; border-radius: 3px; "
        f"padding: 4px 12px; font-size: 11px; font-family: 'Courier New'; }}"
        f"QPushButton:hover {{ border-color: {c}; }}"
        f"QPushButton:pressed {{ background: {theme.BG_PANEL}; }}"
    )
