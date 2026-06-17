from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt, QThread, QTimer
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QLabel, QSizePolicy, QVBoxLayout, QWidget

from src.controller.event_bus import EventBus
from src.vision.rtsp_vision_worker import RTSPVisionWorker


_IDLE    = "color: #7a8591; font-size: 11px; padding: 2px 8px;"
_DETECT  = "color: #ff3d3d; font-size: 11px; padding: 2px 8px; font-weight: 700;"
_TRIGGER = "color: #ffae00; font-size: 11px; padding: 2px 8px; font-weight: 700;"


class VisionCameraWidget(QWidget):
    """RTSP viewer with HOG person detection overlay.

    Uses GStreamer for hardware H265/H264 decoding (same backend as RTSPView).
    Displays every frame via QLabel; HOG detection runs every N frames.

    Config keys
    -----------
    rtsp_source        : str   RTSP URL
    codec              : str   "h265" (default) or "h264"
    rtsp_transport     : str   "udp" (default) or "tcp"
    detection_topic    : str   EventBus topic when a zone is triggered
    offset             : float Normalised tolerance around zone edges (default 0.15)
    detection_interval : int   Run HOG every N frames (default 5)
    min_confidence     : float HOG threshold (default 0.3)
    detection_scale    : float Frame scale for HOG (default 0.35)
    positions          : dict  {name: [x1,y1,x2,y2,...]} pixel-coord polygons
    """

    def __init__(self, name: str, config: dict, event_bus: EventBus | None = None):
        super().__init__()
        self.name      = name
        self.config    = config
        self.event_bus = event_bus or EventBus()
        self._topic    = config.get("detection_topic", "vision.person_detected")

        # ── Video label ───────────────────────────────────────────────────
        self._video = QLabel("Connecting…")
        self._video.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._video.setStyleSheet("background: #0a0a0a; color: #7a8591; font-size: 13px;")
        self._video.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # ── Status bar ────────────────────────────────────────────────────
        self._status = QLabel("No detection")
        self._status.setFixedHeight(22)
        self._status.setStyleSheet(_IDLE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._video, 1)
        layout.addWidget(self._status)

        # Auto-clear status after 3 s of silence
        self._clear_timer = QTimer(self)
        self._clear_timer.setSingleShot(True)
        self._clear_timer.setInterval(3000)
        self._clear_timer.timeout.connect(self._clear_status)

        # ── Worker thread ─────────────────────────────────────────────────
        self._thread = QThread(self)
        self._worker = RTSPVisionWorker(name, config)
        self._worker.moveToThread(self._thread)

        self._worker.frame_ready.connect(self._on_frame, Qt.ConnectionType.QueuedConnection)
        self._worker.detection_updated.connect(self._on_detection, Qt.ConnectionType.QueuedConnection)
        self._worker.position_triggered.connect(self._on_position_triggered, Qt.ConnectionType.QueuedConnection)
        self._worker.log.connect(self._on_worker_log, Qt.ConnectionType.QueuedConnection)
        self._thread.started.connect(self._worker.start_capture)

        src = config.get("rtsp_source", "?")
        self.event_bus.publish_sync("log", f"[Vision:{name}] widget created — {src}")
        self._thread.start()

    # ── Slots (always called on Qt main thread via QueuedConnection) ──────

    def _on_frame(self, frame: np.ndarray) -> None:
        h, w = frame.shape[:2]
        # frame is BGR — convert to RGB for QImage
        rgb = np.ascontiguousarray(frame[:, :, ::-1])
        qt_img = QImage(rgb.data, w, h, w * 3, QImage.Format.Format_RGB888)
        pix = QPixmap.fromImage(qt_img).scaled(
            self._video.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.FastTransformation,
        )
        self._video.setPixmap(pix)
        self._video.setStyleSheet("background: #0a0a0a;")

    def _on_detection(self, detections: list) -> None:
        if not detections:
            return
        n = len(detections)
        self._status.setText(f"● {n} person{'s' if n > 1 else ''} detected")
        self._status.setStyleSheet(_DETECT)
        self._clear_timer.start()

    def _on_worker_log(self, msg: str) -> None:
        self.event_bus.publish_sync("log", msg)

    def _on_position_triggered(self, zone_name: str, info: dict) -> None:
        self._status.setText(f"▲ ZONE '{zone_name}' — person detected!")
        self._status.setStyleSheet(_TRIGGER)
        self._clear_timer.start()
        self.event_bus.publish_sync(self._topic, {"zone": zone_name, **info})

    def _clear_status(self) -> None:
        self._status.setText("No detection")
        self._status.setStyleSheet(_IDLE)

    # ── Lifecycle ─────────────────────────────────────────────────────────

    def closeEvent(self, event):
        self._worker.stop()
        self._thread.quit()
        self._thread.wait(2000)
        super().closeEvent(event)
