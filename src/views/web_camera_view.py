from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

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
    """

    _gst_initialized = False

    def __init__(self, name: str, config: dict):
        self.name = name
        self.config = config or {}

        if GST_AVAILABLE and not WebCameraView._gst_initialized:
            Gst.init(None)  # type: ignore[misc]
            WebCameraView._gst_initialized = True

        self._widget: Optional[QWidget] = None
        self._video_widget: Optional[QWidget] = None
        self._pipeline = None
        self._bus = None

    def build(self):
        if self._widget is not None:
            return

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
            return

        device = self._resolve_device()

        self._video_widget = QWidget(self._widget)
        self._video_widget.setStyleSheet("background: black;")
        self._video_widget.setAttribute(Qt.WidgetAttribute.WA_NativeWindow, True)
        layout.addWidget(self._video_widget)

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
            layout.addWidget(QLabel(f"Erreur pipeline: {e}"))
            return

        sink = self._pipeline.get_by_name("video_sink")
        if sink is None:
            layout.addWidget(QLabel("Erreur: video_sink introuvable"))
            return

        win_id = int(self._video_widget.winId())
        if hasattr(sink, "set_window_handle"):
            sink.set_window_handle(win_id)
        else:
            GstVideo.VideoOverlay.set_window_handle(sink, win_id)  # type: ignore[misc]

        self._bus = self._pipeline.get_bus()
        self._bus.add_signal_watch()
        self._bus.connect("message", self._on_bus_message)

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

    def _on_bus_message(self, bus, message):
        if message.type == Gst.MessageType.ERROR:  # type: ignore[misc]
            err, debug = message.parse_error()
            print(f"[GStreamer][WebCam][ERROR] {err}")
            if debug:
                print(f"[DEBUG] {debug}")
        elif message.type == Gst.MessageType.EOS:  # type: ignore[misc]
            print("[GStreamer][WebCam] End of stream")

    def start(self) -> None:
        if self._pipeline is None:
            self.build()
        if self._pipeline is not None:
            self._pipeline.set_state(Gst.State.PLAYING)  # type: ignore[misc]

    def stop(self) -> None:
        if self._pipeline is not None:
            self._pipeline.set_state(Gst.State.NULL)  # type: ignore[misc]
            self._pipeline = None
        if self._bus is not None:
            self._bus.remove_signal_watch()
            self._bus = None
        self._video_widget = None
        self._widget = None

    def get_widget(self) -> QWidget:
        if self._widget is None:
            self.build()
        return self._widget  # type: ignore[return-value]
