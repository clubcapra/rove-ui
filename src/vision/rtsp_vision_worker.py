from __future__ import annotations

import math
import threading
import time
from typing import Any

import numpy as np
from PySide6.QtCore import QObject, Signal

try:
    import gi
    gi.require_version("Gst", "1.0")
    from gi.repository import Gst
    GST_AVAILABLE = True
except Exception:
    GST_AVAILABLE = False
    Gst = None  # type: ignore

from src.vision.detector import PersonDetector


_BOX_COLOR = (0, 255, 0)   # BGR green — person outside zone
_HIT_COLOR = (0, 0, 255)   # BGR red   — person inside zone
_ZONE_COLOR = (0, 200, 255) # BGR amber — zone polygon

_GST_INITIALIZED = False


def _ensure_gst_init() -> None:
    global _GST_INITIALIZED
    if not _GST_INITIALIZED and GST_AVAILABLE:
        Gst.init(None)  # type: ignore
        _GST_INITIALIZED = True


def _parse_positions(raw: dict) -> dict[str, np.ndarray]:
    """Convert {name: [x1,y1,...]} → {name: Nx2 float32 polygon}."""
    out: dict[str, np.ndarray] = {}
    for name, vals in raw.items():
        if not isinstance(vals, (list, tuple)) or len(vals) < 6:
            continue
        coords = list(vals)
        if len(coords) % 2 != 0:
            coords = coords[:-1]
        pts = np.array(
            [(coords[i], coords[i + 1]) for i in range(0, len(coords), 2)],
            dtype=np.float32,
        )
        out[name] = pts
    return out


def _in_zone(cx: float, cy: float, polygon: np.ndarray, offset_px: float) -> bool:
    import cv2
    dist = cv2.pointPolygonTest(polygon, (float(cx), float(cy)), measureDist=True)
    return dist >= -offset_px


class RTSPVisionWorker(QObject):
    """GStreamer-backed RTSP reader with HOG person detection.

    The GStreamer streaming thread calls _on_new_sample on every decoded frame.
    HOG runs every `detection_interval` frames so the display is full-speed
    while detection is rate-limited.

    Signals
    -------
    frame_ready(np.ndarray)          Annotated BGR frame for display
    detection_updated(list)          Detections list, emitted each time HOG runs
    position_triggered(str, object)  (zone_name, info) when a person enters a zone
    log(str)                         Log message — relay to EventBus on main thread
    """

    frame_ready        = Signal(object)        # np.ndarray BGR
    detection_updated  = Signal(object)        # list[dict]
    position_triggered = Signal(str, object)   # (zone_name, info_dict)
    log                = Signal(str)           # log message

    def __init__(self, name: str, config: dict) -> None:
        super().__init__()
        self._name = name

        self._rtsp_source        = str(config.get("rtsp_source", ""))
        self._codec              = str(config.get("codec", "h265")).strip().lower()
        self._rtsp_transport     = str(config.get("rtsp_transport", "udp")).strip().lower()
        self._detection_interval = max(1, int(config.get("detection_interval", 5)))
        self._min_confidence     = float(config.get("min_confidence", 0.3))
        self._offset             = float(config.get("offset", 0.15))
        self._det_scale          = float(config.get("detection_scale", 0.35))

        raw = config.get("positions", {})
        self._zones = _parse_positions(raw) if isinstance(raw, dict) else {}

        self._detector: PersonDetector | None = None
        self._pipeline: Any = None
        self._running = False
        self._frame_count = 0
        self._first_frame = True
        self._last_detections: list[dict] = []
        self._det_lock = threading.Lock()

    def _log(self, msg: str) -> None:
        self.log.emit(f"[Vision:{self._name}] {msg}")

    # ── QThread entry point ───────────────────────────────────────────────

    def start_capture(self) -> None:
        if not GST_AVAILABLE:
            self._log("GStreamer not available — vision disabled")
            return

        _ensure_gst_init()
        self._detector = PersonDetector(detection_scale=self._det_scale)
        self._running = True
        self._first_frame = True

        self._log(f"pipeline starting → {self._rtsp_source}  codec={self._codec}  det_interval={self._detection_interval}")

        pipeline = self._build_pipeline()
        if pipeline is None:
            self._log("pipeline build failed")
            return
        self._pipeline = pipeline

        appsink = pipeline.get_by_name("vsink")
        if appsink is None:
            self._log("appsink 'vsink' not found in pipeline")
            return
        appsink.connect("new-sample", self._on_new_sample)

        pipeline.set_state(Gst.State.PLAYING)  # type: ignore

        bus = pipeline.get_bus()
        while self._running:
            msg = bus.timed_pop_filtered(
                100_000_000,  # 100 ms timeout in nanoseconds
                Gst.MessageType.ERROR | Gst.MessageType.EOS,  # type: ignore
            )
            if msg is None:
                continue
            if msg.type == Gst.MessageType.ERROR:  # type: ignore
                err, debug = msg.parse_error()
                self._log(f"GST ERROR: {err}")
                if debug:
                    self._log(f"GST DEBUG: {debug}")
                time.sleep(1.0)
            elif msg.type == Gst.MessageType.EOS:  # type: ignore
                self._log("stream ended (EOS)")
                break

        pipeline.set_state(Gst.State.NULL)  # type: ignore
        self._pipeline = None
        self._log("pipeline stopped")

    def stop(self) -> None:
        self._running = False
        if self._pipeline is not None:
            self._pipeline.set_state(Gst.State.NULL)  # type: ignore

    # ── GStreamer appsink callback (runs in GStreamer streaming thread) ────

    def _on_new_sample(self, appsink) -> "Gst.FlowReturn":  # type: ignore
        if not self._running:
            return Gst.FlowReturn.OK  # type: ignore

        sample = appsink.emit("pull-sample")
        if sample is None:
            return Gst.FlowReturn.OK  # type: ignore

        buf  = sample.get_buffer()
        caps = sample.get_caps()
        s    = caps.get_structure(0)
        w    = s.get_value("width")
        h    = s.get_value("height")

        ok, mapinfo = buf.map(Gst.MapFlags.READ)  # type: ignore
        if not ok:
            return Gst.FlowReturn.OK  # type: ignore

        try:
            # GStreamer delivers RGB; keep a BGR copy for OpenCV/display
            frame_rgb = np.frombuffer(mapinfo.data, dtype=np.uint8).reshape((h, w, 3))
            frame_bgr = frame_rgb[:, :, ::-1].copy()
        finally:
            buf.unmap(mapinfo)

        self._frame_count += 1

        if self._first_frame:
            self._first_frame = False
            self._log(f"first frame received — {w}x{h}  zones={list(self._zones.keys())}")

        run_detection = (self._frame_count % self._detection_interval == 0)

        if run_detection and self._detector is not None:
            import cv2  # noqa: PLC0415 — lazy import keeps startup clean
            dets = [
                d for d in self._detector.detect(frame_bgr)
                if d["confidence"] >= self._min_confidence
            ]
            fh, fw = frame_bgr.shape[:2]
            offset_px = self._offset * math.sqrt(fw * fh)

            with self._det_lock:
                self._last_detections = dets

            self.detection_updated.emit(dets)

            for det in dets:
                cx = det["x"] + det["w"] / 2
                cy = det["y"] + det["h"] / 2
                for zone_name, polygon in self._zones.items():
                    if _in_zone(cx, cy, polygon, offset_px):
                        self._log(
                            f"ZONE '{zone_name}' triggered  "
                            f"conf={det['confidence']:.2f}  "
                            f"bbox=[{det['x']},{det['y']},{det['w']},{det['h']}]"
                        )
                        self.position_triggered.emit(
                            zone_name,
                            {
                                "bbox":       [det["x"], det["y"], det["w"], det["h"]],
                                "confidence": det["confidence"],
                            },
                        )

        with self._det_lock:
            dets_to_draw = list(self._last_detections)

        fh, fw = frame_bgr.shape[:2]
        offset_px = self._offset * math.sqrt(fw * fh)
        annotated = self._annotate(frame_bgr, dets_to_draw, offset_px)
        self.frame_ready.emit(annotated)

        return Gst.FlowReturn.OK  # type: ignore

    # ── Annotation ────────────────────────────────────────────────────────

    def _annotate(
        self, frame: np.ndarray, detections: list[dict], offset_px: float
    ) -> np.ndarray:
        import cv2  # noqa: PLC0415

        out = frame.copy()

        for polygon in self._zones.values():
            pts = polygon.astype(np.int32).reshape((-1, 1, 2))
            cv2.polylines(out, [pts], isClosed=True, color=_ZONE_COLOR, thickness=1)

        for det in detections:
            x, y, w, h = det["x"], det["y"], det["w"], det["h"]
            in_zone = any(
                _in_zone(x + w / 2, y + h / 2, p, offset_px)
                for p in self._zones.values()
            )
            color = _HIT_COLOR if in_zone else _BOX_COLOR
            cv2.rectangle(out, (x, y), (x + w, y + h), color, 2)
            cv2.putText(
                out, f"{det['confidence']:.2f}",
                (x, max(0, y - 6)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1,
            )

        return out

    # ── Pipeline builder ──────────────────────────────────────────────────

    def _build_pipeline(self):
        if self._codec == "h265":
            depay_name, parse_name, decode_name = "rtph265depay", "h265parse", "avdec_h265"
        else:
            depay_name, parse_name, decode_name = "rtph264depay", "h264parse", "avdec_h264"

        protocols_flag = 4 if self._rtsp_transport == "udp" else 16

        try:
            pipeline = Gst.Pipeline.new("vision-pipeline")  # type: ignore

            rtspsrc  = Gst.ElementFactory.make("rtspsrc",      "rtspsrc0")  # type: ignore
            depay    = Gst.ElementFactory.make(depay_name,     "depay")     # type: ignore
            vparse   = Gst.ElementFactory.make(parse_name,     "vparse")    # type: ignore
            decode   = Gst.ElementFactory.make(decode_name,    "decode")    # type: ignore
            queue    = Gst.ElementFactory.make("queue",         "queue0")    # type: ignore
            conv     = Gst.ElementFactory.make("videoconvert",  "vconv")     # type: ignore
            capsf    = Gst.ElementFactory.make("capsfilter",    "capsf")     # type: ignore
            appsink  = Gst.ElementFactory.make("appsink",       "vsink")     # type: ignore

            for name, el in (
                ("rtspsrc",   rtspsrc),
                (depay_name,  depay),
                (parse_name,  vparse),
                (decode_name, decode),
                ("queue",     queue),
                ("convert",   conv),
                ("capsf",     capsf),
                ("appsink",   appsink),
            ):
                if el is None:
                    print(f"[VisionWorker] Cannot create GStreamer element: {name}")
                    return None
                pipeline.add(el)

            rtspsrc.set_property("location",         self._rtsp_source)
            rtspsrc.set_property("protocols",        protocols_flag)
            rtspsrc.set_property("latency",          0)
            rtspsrc.set_property("drop-on-latency",  True)

            decode.set_property("max-threads", 4)

            queue.set_property("max-size-buffers", 2)
            queue.set_property("leaky",            2)  # leaky downstream

            capsf.set_property(
                "caps", Gst.Caps.from_string("video/x-raw,format=RGB")  # type: ignore
            )

            appsink.set_property("emit-signals", True)
            appsink.set_property("max-buffers",  1)
            appsink.set_property("drop",         True)
            appsink.set_property("sync",         False)

            for src_el, dst_el in (
                (depay,  vparse),
                (vparse, decode),
                (decode, queue),
                (queue,  conv),
                (conv,   capsf),
                (capsf,  appsink),
            ):
                if not src_el.link(dst_el):
                    print(f"[VisionWorker] Link failed: {src_el.get_name()} → {dst_el.get_name()}")
                    return None

            def _on_pad_added(src, new_pad, _depay=depay):  # type: ignore
                sink_pad = _depay.get_static_pad("sink")
                if sink_pad.is_linked():
                    return
                ret = new_pad.link(sink_pad)
                if ret != Gst.PadLinkReturn.OK:  # type: ignore
                    print(f"[VisionWorker] Dynamic pad link failed: {ret}")

            rtspsrc.connect("pad-added", _on_pad_added)
            return pipeline

        except Exception as exc:
            print(f"[VisionWorker] Pipeline build error: {exc}")
            return None
