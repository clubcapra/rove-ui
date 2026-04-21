from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QComboBox, QStackedWidget, QVBoxLayout, QWidget

from src.controller.event_bus import EventBus
from src.views.rtsp_view import RTSPView
from src.views.web_camera_view import WebCameraView


class CameraWidget:
    """Unified camera widget that can switch between RTSP and webcam sources.

    Config example:
    {
        "mode": "rtsp",
        "rtsp": {"source": "rtsp://..."},
        "webcamera": {"device_path": "/dev/video0"}
    }
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

    def build(self) -> None:
        if self._widget is not None:
            return

        self.event_bus.publish_sync("log", f"CameraWidget[{self.name}] build started")

        self._widget = QWidget()
        layout = QVBoxLayout(self._widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._selector = QComboBox(self._widget)
        self._selector.addItem("RTSP", "rtsp")
        self._selector.addItem("WebCamera", "webcamera")
        self._selector.currentIndexChanged.connect(self._on_mode_changed)
        layout.addWidget(self._selector)

        self._stack = QStackedWidget(self._widget)
        layout.addWidget(self._stack, 1)

        self._views["rtsp"] = RTSPView(f"{self.name}-rtsp", self._rtsp_config(), event_bus=self.event_bus)
        self._views["webcamera"] = WebCameraView(f"{self.name}-webcamera", self._webcamera_config(), event_bus=self.event_bus)

        for mode in self.MODES:
            view = self._views[mode]
            view.build()
            self._stack.addWidget(view.get_widget())

        mode = self._initial_mode()
        self._set_mode(mode, force_rebuild=True)
        self.event_bus.publish_sync("log", f"CameraWidget[{self.name}] ready (initial mode: {mode})")

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
        if mode not in self.MODES:
            return "rtsp"
        return mode

    def _base_config(self) -> dict[str, Any]:
        # Shared keys can be defined at the parent level and are inherited by both children.
        ignored = {"mode", "protocol", "rtsp", "webcamera"}
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
        if self._selector is None or self._stack is None:
            return

        index_by_mode = {"rtsp": 0, "webcamera": 1}
        idx = index_by_mode.get(mode, 0)

        if not force_rebuild and mode == self._active_mode:
            return

        self.event_bus.publish_sync(
            "log",
            f"CameraWidget[{self.name}] switching mode {self._active_mode} -> {mode} (force={force_rebuild})",
        )

        # Pause inactive pipelines and rebuild the selected one to avoid stale/frozen streams.
        for item_mode, view in self._views.items():
            pause_fn = getattr(view, "pause", None)
            start_fn = getattr(view, "start", None)
            restart_fn = getattr(view, "restart_pipeline", None)
            if item_mode == mode:
                if callable(restart_fn):
                    restart_fn()
                elif callable(start_fn):
                    start_fn()
            elif item_mode != mode and callable(pause_fn):
                pause_fn()

        self._stack.setCurrentIndex(idx)
        self._selector.blockSignals(True)
        self._selector.setCurrentIndex(idx)
        self._selector.blockSignals(False)
        self._active_mode = mode
        self.event_bus.publish_sync("log", f"CameraWidget[{self.name}] mode active: {mode}")

    def _on_mode_changed(self, index: int) -> None:
        mode = "rtsp" if index == 0 else "webcamera"
        self._set_mode(mode, force_rebuild=True)
        

