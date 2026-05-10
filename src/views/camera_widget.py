from __future__ import annotations

import socket
import time
from threading import Thread
from typing import Any

from PySide6.QtCore import Qt, Signal, QObject
from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget,
)

from src.controller.event_bus import EventBus
from src.views.rtsp_view import RTSPView
from src.views.web_camera_view import WebCameraView


def _rtsp_reachable(ip: str, port: int = 554, timeout: float = 1.5) -> bool:
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except OSError:
        return False


class _PingSignals(QObject):
    result = Signal(int, bool)  # (camera_index, is_reachable)


_BTN_INACTIVE = """
    QPushButton {
        background: #ffffff; color: #374151;
        border: 1px solid #e5e7eb; border-radius: 5px;
        font-size: 12px; padding: 2px 6px;
        text-align: left;
    }
    QPushButton:hover   { background: #f3f4f6; border-color: #d1d5db; }
    QPushButton:pressed { background: #e5e7eb; }
"""

_BTN_ACTIVE = """
    QPushButton {
        background: #d1d5db; color: #111827;
        border: 1px solid #9ca3af; border-radius: 5px;
        font-size: 12px; font-weight: 700; padding: 2px 6px;
        text-align: left;
    }
"""


class CameraWidget:
    """Unified camera widget — supports a camera list for multi-source switching.

    Config with camera list:
    {
        "mode": "rtsp",
        "vtx_host": "192.168.2.2",
        "vtx_port": 5540,
        "cameras": [
            {"name": "Front", "udp_vtx_id": 2, "rtsp_ip": "192.168.2.32"},
            {"name": "Back",  "udp_vtx_id": 3, "rtsp_ip": "192.168.2.34"}
        ],
        "rtsp":      {"source": "rtsp://192.168.2.32:554/"},
        "webcamera": {"device_path": "/dev/video0"}
    }
    With 0-1 cameras the original ComboBox behaviour is preserved.
    """

    MODES = ("rtsp", "webcamera")

    def __init__(self, name: str, config: dict[str, Any], event_bus: EventBus | None = None):
        self.name = name
        self.config = config or {}
        self.event_bus = event_bus or EventBus()

        self._widget: QWidget | None = None
        self._selector: QComboBox | None = None
        self._stack: QStackedWidget | None = None
        self._views: dict[str, Any] = {}
        self._active_mode: str | None = None
        self._active_cam_idx: int = -1

        self._cameras: list[dict] = list(config.get("cameras", []))
        self._vtx_host: str = str(config.get("vtx_host", "192.168.2.2"))
        self._vtx_port: int = int(config.get("vtx_port", 5540))

        self._ping_dots: list[QLabel] = []
        self._cam_buttons: list[QPushButton] = []
        self._mode_label: QLabel | None = None
        self._toggle_btn: QPushButton | None = None
        # None = not yet pinged, True/False = last known state (optimistic start)
        self._rtsp_flags: list[bool | None] = [None] * len(self._cameras)

    # ── Build ─────────────────────────────────────────────────────────────

    def build(self) -> None:
        if self._widget is not None:
            return

        self.event_bus.publish_sync("log", f"CameraWidget[{self.name}] build started")

        use_camera_list = len(self._cameras) > 1

        self._widget = QWidget()

        if not use_camera_list:
            # ── Original single-source mode ───────────────────────────────
            layout = QVBoxLayout(self._widget)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)

            self._selector = QComboBox(self._widget)
            self._selector.addItem("RTSP", "rtsp")
            self._selector.addItem("WebCamera", "webcamera")
            self._selector.currentIndexChanged.connect(self._on_mode_changed)
            layout.addWidget(self._selector)

            self._stack = QStackedWidget(self._widget)
            layout.addWidget(self._stack, 1)
        else:
            # ── Multi-camera mode: sidebar + viewer ───────────────────────
            root = QHBoxLayout(self._widget)
            root.setContentsMargins(0, 0, 0, 0)
            root.setSpacing(0)
            root.addWidget(self._build_sidebar())

            right = QWidget()
            right_layout = QVBoxLayout(right)
            right_layout.setContentsMargins(0, 0, 0, 0)
            right_layout.setSpacing(0)
            right_layout.addWidget(self._build_mode_bar())

            self._stack = QStackedWidget()
            right_layout.addWidget(self._stack, 1)
            root.addWidget(right, 1)

        # ── Shared: build both views ──────────────────────────────────────
        self._views["rtsp"] = RTSPView(
            f"{self.name}-rtsp", self._rtsp_config(), event_bus=self.event_bus
        )
        self._views["webcamera"] = WebCameraView(
            f"{self.name}-webcamera", self._webcamera_config(), event_bus=self.event_bus
        )

        for mode in self.MODES:
            view = self._views[mode]
            view.build()
            self._stack.addWidget(view.get_widget())

        if use_camera_list:
            self._views["rtsp"].hide_controls()

        mode = self._initial_mode()
        self._set_mode(mode, force_rebuild=True)
        self.event_bus.publish_sync("log", f"CameraWidget[{self.name}] ready (mode: {mode})")

        self.event_bus.subscribe("camera.snapshot_request", self._do_snapshot)

    # ── Sidebar ───────────────────────────────────────────────────────────

    def _build_sidebar(self) -> QWidget:
        inner = QWidget()
        inner.setStyleSheet("background: #f9fafb;")

        col = QVBoxLayout(inner)
        col.setContentsMargins(6, 8, 6, 8)
        col.setSpacing(4)

        for idx, cam in enumerate(self._cameras):
            cam_name = str(cam.get("name", f"Cam {idx}"))
            rtsp_ip  = str(cam.get("rtsp_ip", ""))

            dot = QLabel("●")
            dot.setFixedSize(12, 12)
            dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
            dot.setStyleSheet("color: #9ca3af; font-size: 9px; background: transparent;")
            self._ping_dots.append(dot)

            btn = QPushButton(cam_name)
            btn.setFixedHeight(34)
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            btn.setStyleSheet(_BTN_INACTIVE)
            btn.clicked.connect(lambda _=False, i=idx: self._select_camera(i))
            self._cam_buttons.append(btn)

            row = QHBoxLayout()
            row.setSpacing(4)
            row.setContentsMargins(0, 0, 0, 0)
            row.addWidget(dot)
            row.addWidget(btn, 1)
            col.addLayout(row)

            if rtsp_ip:
                self._start_ping_watcher(idx, rtsp_ip)

        col.addStretch()

        scroll = QScrollArea()
        scroll.setWidget(inner)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setFixedWidth(148)
        scroll.setStyleSheet(
            "QScrollArea { border: none; border-right: 1px solid #e5e7eb; background: #f9fafb; }"
        )
        return scroll

    # ── Mode bar ──────────────────────────────────────────────────────────

    def _build_mode_bar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(30)
        bar.setStyleSheet("background: #f3f4f6; border-bottom: 1px solid #e5e7eb;")

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setSpacing(8)

        self._mode_label = QLabel("● RTSP")
        self._mode_label.setStyleSheet("color: #2563eb; font-size: 12px; font-weight: 700; background: transparent;")
        layout.addWidget(self._mode_label)

        layout.addStretch()

        self._toggle_btn = QPushButton("→ VTX")
        self._toggle_btn.setFixedHeight(20)
        self._toggle_btn.setStyleSheet("""
            QPushButton {
                background: #ffffff; color: #374151;
                border: 1px solid #9ca3af; border-radius: 4px;
                font-size: 11px; padding: 0 8px;
            }
            QPushButton:hover   { background: #f9fafb; border-color: #6b7280; }
            QPushButton:pressed { background: #e5e7eb; }
        """)
        self._toggle_btn.clicked.connect(self._on_toggle_mode)
        layout.addWidget(self._toggle_btn)

        return bar

    def _update_mode_bar(self) -> None:
        if self._mode_label is None or self._toggle_btn is None:
            return
        if self._active_mode == "rtsp":
            self._mode_label.setText("● RTSP")
            self._mode_label.setStyleSheet("color: #2563eb; font-size: 12px; font-weight: 700; background: transparent;")
            self._toggle_btn.setText("→ VTX")
        else:
            self._mode_label.setText("● VTX")
            self._mode_label.setStyleSheet("color: #16a34a; font-size: 12px; font-weight: 700; background: transparent;")
            self._toggle_btn.setText("→ RTSP")

    def _on_toggle_mode(self) -> None:
        new_mode = "webcamera" if self._active_mode == "rtsp" else "rtsp"
        self._set_mode(new_mode, force_rebuild=True)

    # ── Ping watcher ──────────────────────────────────────────────────────

    def _start_ping_watcher(self, idx: int, ip: str) -> None:
        signals = _PingSignals()
        signals.result.connect(self._on_ping_result)

        def _loop(s=signals, h=ip, i=idx):
            while True:
                s.result.emit(i, _rtsp_reachable(h))
                time.sleep(5)

        Thread(target=_loop, daemon=True).start()

    def _on_ping_result(self, idx: int, ok: bool) -> None:
        if 0 <= idx < len(self._ping_dots):
            color = "#22c55e" if ok else "#9ca3af"
            self._ping_dots[idx].setStyleSheet(f"color: {color}; font-size: 9px; background: transparent;")

        prev = self._rtsp_flags[idx] if idx < len(self._rtsp_flags) else None
        self._rtsp_flags[idx] = ok

        # Auto-fallback: RTSP was up, now down, and this is the active camera on RTSP
        if (
            idx == self._active_cam_idx
            and self._active_mode == "rtsp"
            and not ok
            and prev is True
        ):
            self.event_bus.publish_sync(
                "log", f"CameraWidget[{self.name}] RTSP unreachable → auto-switch to VTX"
            )
            self._set_mode("webcamera", force_rebuild=False)

    # ── Camera selection ──────────────────────────────────────────────────

    def _select_camera(self, idx: int) -> None:
        if idx >= len(self._cameras):
            return
        cam = self._cameras[idx]
        vtx_id  = int(cam.get("udp_vtx_id", 0))
        rtsp_ip = str(cam.get("rtsp_ip", ""))

        # Highlight active button
        for i, btn in enumerate(self._cam_buttons):
            btn.setStyleSheet(_BTN_ACTIVE if i == idx else _BTN_INACTIVE)
        self._active_cam_idx = idx

        self.event_bus.publish_sync(
            "log", f"CameraWidget[{self.name}] → {cam.get('name')} (vtx={vtx_id} ip={rtsp_ip})"
        )

        # Send VTX switch command regardless of display mode
        webcam_view: WebCameraView = self._views["webcamera"]  # type: ignore[assignment]
        if vtx_id:
            webcam_view.send_vtx_command(vtx_id, self._vtx_host, self._vtx_port)

        if rtsp_ip:
            rtsp_source = cam.get("rtsp_source", f"rtsp://{rtsp_ip}:554/")
            rtsp_view: RTSPView = self._views["rtsp"]  # type: ignore[assignment]
            rtsp_view.set_source(rtsp_source)

            # Use RTSP if last known state is reachable (or unknown → optimistic)
            flag = self._rtsp_flags[idx] if idx < len(self._rtsp_flags) else None
            target_mode = "webcamera" if flag is False else "rtsp"
            self._set_mode(target_mode, force_rebuild=False)

    # ── Helpers ───────────────────────────────────────────────────────────

    def _do_snapshot(self, callback=None) -> None:
        if not callable(callback):
            return
        active_view = self._views.get(self._active_mode or "rtsp")
        snap_fn = getattr(active_view, "capture_snapshot", None)
        if callable(snap_fn):
            pix = snap_fn()
            if pix is not None and not pix.isNull():
                callback(pix)
                return
        # fallback: Qt widget grab (black for GStreamer overlay, but better than nothing)
        target = self._stack if self._stack is not None else self._widget
        if target is not None:
            callback(target.grab())

    def get_widget(self) -> QWidget:
        if self._widget is None:
            self.build()
        return self._widget  # type: ignore[return-value]

    def stop(self) -> None:
        for view in self._views.values():
            stop_fn = getattr(view, "stop", None)
            if callable(stop_fn):
                stop_fn()

    def _initial_mode(self) -> str:
        mode = str(self.config.get("mode", self.config.get("protocol", "rtsp"))).strip().lower()
        return mode if mode in self.MODES else "rtsp"

    def _base_config(self) -> dict[str, Any]:
        ignored = {"mode", "protocol", "rtsp", "webcamera", "cameras", "vtx_host", "vtx_port"}
        return {k: v for k, v in self.config.items() if k not in ignored}

    def _rtsp_config(self) -> dict[str, Any]:
        cfg = dict(self._base_config())
        rtsp_cfg = self.config.get("rtsp", {})
        if isinstance(rtsp_cfg, dict):
            cfg.update(rtsp_cfg)
        return cfg

    def _webcamera_config(self) -> dict[str, Any]:
        cfg = dict(self._base_config())
        webcam_cfg = self.config.get("webcamera", {})
        if isinstance(webcam_cfg, dict):
            cfg.update(webcam_cfg)
        return cfg

    def _set_mode(self, mode: str, force_rebuild: bool = False) -> None:
        if self._stack is None:
            return

        index_by_mode = {"rtsp": 0, "webcamera": 1}
        idx = index_by_mode.get(mode, 0)

        if not force_rebuild and mode == self._active_mode:
            return

        for item_mode, view in self._views.items():
            if item_mode == mode:
                restart_fn = getattr(view, "restart_pipeline", None)
                start_fn   = getattr(view, "start", None)
                if callable(restart_fn):
                    restart_fn()
                elif callable(start_fn):
                    start_fn()
            else:
                pause_fn = getattr(view, "pause", None)
                if callable(pause_fn):
                    pause_fn()

        self._stack.setCurrentIndex(idx)
        if self._selector:
            self._selector.blockSignals(True)
            self._selector.setCurrentIndex(idx)
            self._selector.blockSignals(False)
        self._active_mode = mode
        self._update_mode_bar()

    def _on_mode_changed(self, index: int) -> None:
        self._set_mode("rtsp" if index == 0 else "webcamera", force_rebuild=True)
