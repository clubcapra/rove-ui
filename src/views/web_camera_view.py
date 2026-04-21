from __future__ import annotations

import subprocess
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget

from src.controller.event_bus import EventBus

GST_AVAILABLE = False
GST_IMPORT_ERROR: Exception | None = None

try:
    import gi  # type: ignore

    gi.require_version("Gst", "1.0")
    gi.require_version("GstVideo", "1.0")
    from gi.repository import Gst, GstVideo  # type: ignore

    GST_AVAILABLE = True
except Exception as e:
    GST_IMPORT_ERROR = e
    Gst = None  # type: ignore[assignment]
    GstVideo = None  # type: ignore[assignment]


class WebCameraView:
    """Web camera view using GStreamer v4l2src.

    Config (optional):
    - device_path: str  e.g. "/dev/video0"  (default: /dev/video0)
    - device_index: int  used to build /dev/videoN when device_path absent
    - sink: str  GStreamer sink element (default: ximagesink)
    - autoplay: bool (default True)
        - responsive: dict
                - min_width: int  minimum rendered video width before clipping starts
                - freeze_below_min_width: bool  keep video width at min_width when the
                    layout gets smaller, clipping the overflow instead of shrinking more
                - overflow_anchor: str  one of left, center, right
    """

    _gst_initialized = False

    def __init__(self, name: str, config: dict, event_bus: EventBus | None = None):
        self.name = name
        self.config = config or {}
        self.event_bus = event_bus or EventBus()

        if GST_AVAILABLE and not WebCameraView._gst_initialized:
            Gst.init(None)  # type: ignore[misc]
            WebCameraView._gst_initialized = True

        self._widget: Optional[QWidget] = None
        self._viewport: Optional[_ResponsiveVideoViewport] = None
        self._video_widget: Optional[QWidget] = None
        self._pipeline = None
        self._bus = None

    def build(self):
        if self._widget is not None:
            return

        self.event_bus.publish_sync("log", f"WebCameraView[{self.name}] build started")

        self._widget = QWidget()
        layout = QVBoxLayout(self._widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        if not GST_AVAILABLE:
            label = QLabel(
                f"GStreamer non disponible.\n{GST_IMPORT_ERROR}"
            )
            label.setWordWrap(True)
            layout.addWidget(label)
            self.event_bus.publish_sync("log", f"WebCameraView[{self.name}] GStreamer not available")
            return

        device = self._resolve_device()

        responsive_cfg = self.config.get("responsive", {})
        self._viewport = _ResponsiveVideoViewport(responsive_cfg, self._widget)
        layout.addWidget(self._viewport)

        self._video_widget = QWidget(self._viewport)
        self._video_widget.setStyleSheet("background: black;")
        self._video_widget.setAttribute(Qt.WidgetAttribute.WA_NativeWindow, True)
        self._viewport.set_video_widget(self._video_widget)


        btn = QPushButton("Send '2' UDP")
        btn.setFixedHeight(32)
        btn.clicked.connect(self._send_udp_command)
        layout.addWidget(btn)

        if not self._rebuild_pipeline(device):
            layout.addWidget(QLabel("Erreur: impossible de créer le pipeline webcam"))
            self.event_bus.publish_sync("log", f"WebCameraView[{self.name}] pipeline build failed")
            return

        if bool(self.config.get("autoplay", True)):
            self.start()

    def _resolve_device(self) -> str:
        device = self.config.get("device_path", "").strip()
        if device:
            return device
        try:
            idx = int(self.config.get("device_index", 0))
        except Exception:
            idx = 0
        return f"/dev/video{idx}"
    
    def _send_udp_command(self):
        try:
            subprocess.Popen(
                "echo '2' | nc -u 192.168.2.2 5540",
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self.event_bus.publish_sync("log", "[CMD] echo '2' | nc -u 192.168.2.2 5540")
        except Exception as e:
            self.event_bus.publish_sync("log", f"[CMD][ERROR] {e}")

    def _on_bus_message(self, bus, message):
        if message.type == Gst.MessageType.ERROR:  # type: ignore[misc]
            err, debug = message.parse_error()
            self.event_bus.publish_sync("log", f"[GStreamer][WebCam][ERROR] {err}")
            if debug:
                self.event_bus.publish_sync("log", f"[DEBUG] {debug}")
        elif message.type == Gst.MessageType.EOS:  # type: ignore[misc]
            self.event_bus.publish_sync("log", "[GStreamer][WebCam] End of stream")

    def start(self) -> None:
        if self._pipeline is None:
            self.restart_pipeline()
        if self._pipeline is not None:
            sink = self._pipeline.get_by_name("video_sink")
            if sink is not None and self._video_widget is not None:
                win_id = int(self._video_widget.winId())
                if hasattr(sink, "set_window_handle"):
                    sink.set_window_handle(win_id)
                else:
                    GstVideo.VideoOverlay.set_window_handle(sink, win_id)  # type: ignore[misc]
            self._pipeline.set_state(Gst.State.PLAYING)  # type: ignore[misc]
            self.event_bus.publish_sync("log", f"WebCameraView[{self.name}] PLAYING")

    def pause(self) -> None:
        if self._pipeline is not None:
            self._pipeline.set_state(Gst.State.PAUSED)  # type: ignore[misc]
            self.event_bus.publish_sync("log", f"WebCameraView[{self.name}] PAUSED")

    def stop(self) -> None:
        self.pause()
        self._teardown_pipeline()
        self._viewport = None
        self._video_widget = None
        self._widget = None
        self.event_bus.publish_sync("log", f"WebCameraView[{self.name}] stopped")

    def restart_pipeline(self) -> bool:
        device = self._resolve_device()
        self.event_bus.publish_sync("log", f"WebCameraView[{self.name}] restart requested ({device})")
        ok = self._rebuild_pipeline(device)
        if ok:
            self.start()
        return ok

    def _teardown_pipeline(self) -> None:
        if self._pipeline is not None:
            self._pipeline.set_state(Gst.State.NULL)  # type: ignore[misc]
            self._pipeline = None
        if self._bus is not None:
            self._bus.remove_signal_watch()
            self._bus = None

    def _rebuild_pipeline(self, device: str) -> bool:
        self._teardown_pipeline()

        sink_type = str(self.config.get("sink", "ximagesink")).strip() or "ximagesink"
        pipeline_str = (
            f"v4l2src device={device} ! "
            f"queue max-size-buffers=1 leaky=downstream ! "
            f"videoconvert ! "
            f"{sink_type} name=video_sink sync=false qos=false"
        )
        print(f"[GStreamer][WebCam] Pipeline: {pipeline_str}")

        try:
            self._pipeline = Gst.parse_launch(pipeline_str)  # type: ignore[misc]
        except Exception as e:
            self.event_bus.publish_sync("log", f"[GStreamer][WebCam][ERROR] {e}")
            return False

        sink = self._pipeline.get_by_name("video_sink")
        if sink is None:
            self.event_bus.publish_sync("log", "[GStreamer][WebCam][ERROR] video_sink introuvable")
            self._teardown_pipeline()
            return False

        if self._video_widget is not None:
            win_id = int(self._video_widget.winId())
            if hasattr(sink, "set_window_handle"):
                sink.set_window_handle(win_id)
            else:
                GstVideo.VideoOverlay.set_window_handle(sink, win_id)  # type: ignore[misc]

        self._bus = self._pipeline.get_bus()
        self._bus.add_signal_watch()
        self._bus.connect("message", self._on_bus_message)
        return True

    def get_widget(self) -> QWidget:
        if self._widget is None:
            self.build()
        return self._widget  # type: ignore[return-value]


class _ResponsiveVideoViewport(QWidget):
    def __init__(self, config: dict | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        config = config or {}

        self._video_widget: QWidget | None = None
        self._min_width = max(1, int(config.get("min_width", 480)))
        self._freeze_below_min_width = bool(config.get("freeze_below_min_width", True))
        self._overflow_anchor = str(config.get("overflow_anchor", "center")).strip().lower()

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setContentsMargins(0, 0, 0, 0)

    def set_video_widget(self, widget: QWidget) -> None:
        self._video_widget = widget
        self._video_widget.setParent(self)
        self._video_widget.show()
        self._update_video_geometry()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_video_geometry()

    def _update_video_geometry(self) -> None:
        if self._video_widget is None:
            return

        viewport_width = max(0, self.width())
        viewport_height = max(0, self.height())

        if self._freeze_below_min_width and viewport_width < self._min_width:
            video_width = self._min_width
        else:
            video_width = viewport_width

        x = self._compute_offset(viewport_width, video_width)
        self._video_widget.setGeometry(x, 0, video_width, viewport_height)

    def _compute_offset(self, viewport_width: int, video_width: int) -> int:
        if self._overflow_anchor == "left":
            return 0
        if self._overflow_anchor == "right":
            return viewport_width - video_width
        return (viewport_width - video_width) // 2
