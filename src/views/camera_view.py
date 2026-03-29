from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import QWidget, QStackedLayout

from .rtsp_view import RTSPView
from .web_camera_view import WebCameraView


class CameraView:
    """Composite view that can switch between RTSP and a local webcam.

    This is a small wrapper around two child views:
    - `RTSPView` (Qt Multimedia / FFmpeg)
    - `WebCameraView` (Qt Multimedia capture)

    Config (flexible):
    - mode: "rtsp" | "webcam" (default "rtsp")
    - rtsp: dict (passed to RTSPView)
    - webcam: dict (passed to WebCameraView)
    - For convenience, if `rtsp` is missing, the whole config is used as RTSP config.
    """

    def __init__(self, name: str, config: dict):
        self.name = name
        self.config = config

        self._widget: Optional[QWidget] = None
        self._stack: Optional[QStackedLayout] = None

        self._rtsp_view: Optional[RTSPView] = None
        self._webcam_view: Optional[WebCameraView] = None

    def build(self) -> None:
        if self._widget is not None:
            return

        self._widget = QWidget()
        self._stack = QStackedLayout(self._widget)

        rtsp_cfg = self.config.get("rtsp")
        if not isinstance(rtsp_cfg, dict):
            rtsp_cfg = self.config
        webcam_cfg = self.config.get("webcam")
        if not isinstance(webcam_cfg, dict):
            webcam_cfg = {}

        self._rtsp_view = RTSPView(f"{self.name} (rtsp)", rtsp_cfg)
        self._rtsp_view.build()
        self._stack.addWidget(self._rtsp_view.get_widget())

        self._webcam_view = WebCameraView(f"{self.name} (webcam)", webcam_cfg)
        self._webcam_view.build()
        self._stack.addWidget(self._webcam_view.get_widget())

        self.set_mode(str(self.config.get("mode", "rtsp")))

    def get_widget(self) -> QWidget:
        if self._widget is None:
            self.build()
        return self._widget  # type: ignore[return-value]

    def set_mode(self, mode: str) -> None:
        if self._stack is None:
            self.build()
        if self._stack is None:
            return

        normalized = (mode or "").strip().lower()
        if normalized in {"web", "webcam", "camera", "usb"}:
            # Free the RTSP decoder pipeline when switching.
            if self._rtsp_view is not None:
                self._rtsp_view.stop()
            self._stack.setCurrentIndex(1)
            if self._webcam_view is not None:
                self._webcam_view.start()
        else:
            # Free the webcam device when switching.
            if self._webcam_view is not None:
                self._webcam_view.stop()
            self._stack.setCurrentIndex(0)
            if self._rtsp_view is not None:
                self._rtsp_view.start()

    def start(self) -> None:
        self.set_mode(str(self.config.get("mode", "rtsp")))

    def stop(self) -> None:
        if self._rtsp_view is not None:
            self._rtsp_view.stop()
        if self._webcam_view is not None:
            self._webcam_view.stop()
