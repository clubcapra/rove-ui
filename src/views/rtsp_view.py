from __future__ import annotations

import subprocess

from PySide6.QtCore import QObject, Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QPushButton, QSizePolicy, QVBoxLayout, QWidget
from src.controller.event_bus import EventBus

GST_AVAILABLE = False
GST_IMPORT_ERROR: Exception | None = None

try:
    import gi  # type: ignore

    gi.require_version("Gst", "1.0")
    gi.require_version("GstVideo", "1.0")

    from gi.repository import Gst, GstVideo  # type: ignore

    GST_AVAILABLE = True
except Exception as e:  # pragma: no cover
    # PyGObject / GStreamer are optional runtime dependencies.
    GST_IMPORT_ERROR = e
    Gst = None  # type: ignore[assignment]
    GstVideo = None  # type: ignore[assignment]


class RTSPView(QObject):
    """High-level RTSP view wrapper.

    Default backend uses QtMultimedia (QMediaPlayer/QCamera).
    Optionally, you can use an embedded mpv process for ultra-low-latency RTSP.
    """
    _gst_initialized = False

    class SourceType:
        RTSP = "rtsp"
        USB_VTX = "usb_vtx"

    def __init__(self, name: str, config: dict, event_bus: EventBus | None = None, parent=None):
        super().__init__(parent)

        self.name = name
        self.config = config or {}
        self.event_bus = event_bus or EventBus()

        if GST_AVAILABLE and not RTSPView._gst_initialized:
            Gst.init(None)  # type: ignore[misc]
            RTSPView._gst_initialized = True

        self.root_widget = None
        self.video_widget = None
        self.pipeline = None
        self.bus = None
        self.urlField = None


    def build(self, source_type: str | None = None, source: str | None = None) -> QWidget:
        if self.root_widget is not None:
            return self.root_widget

        self.event_bus.publish_sync("log", f"RTSPView[{self.name}] build started")

        if not GST_AVAILABLE:
            self.root_widget = QWidget()
            layout = QVBoxLayout(self.root_widget)
            layout.setContentsMargins(12, 12, 12, 12)
            msg = (
                "GStreamer (PyGObject) n'est pas disponible.\n\n"
                "Sur Ubuntu, installe :\n"
                "  sudo apt update\n"
                "  sudo apt install -y \
python3-gi gir1.2-gstreamer-1.0 gir1.2-gst-plugins-base-1.0 \
gstreamer1.0-tools gstreamer1.0-gl gstreamer1.0-libav \
gstreamer1.0-plugins-base gstreamer1.0-plugins-good gstreamer1.0-plugins-bad\n\n"
                "Puis relance l'app.\n"
            )
            if GST_IMPORT_ERROR is not None:
                msg += f"\nDétail import: {GST_IMPORT_ERROR}"
            label = QLabel(msg)
            label.setWordWrap(True)
            layout.addWidget(label)
            self.event_bus.publish_sync("log", f"RTSPView[{self.name}] GStreamer not available")
            return self.root_widget

        self.root_widget = QWidget()
        self.root_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        layout = QVBoxLayout(self.root_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        resolved_source_type, resolved_source = self._resolve_source(source_type, source)

        url_row = QWidget(self.root_widget)
        url_row_layout = QHBoxLayout(url_row)
        url_row_layout.setContentsMargins(4, 4, 4, 4)
        url_row_layout.setSpacing(6)

        url_label = QLabel("URL:")
        url_row_layout.addWidget(url_label)

        self.urlField = QLineEdit(resolved_source or "")
        self.urlField.setPlaceholderText("rtsp://...")
        self.urlField.returnPressed.connect(self._apply_url_change)
        url_row_layout.addWidget(self.urlField, 1)

        apply_btn = QPushButton("Apply")
        apply_btn.clicked.connect(self._apply_url_change)
        url_row_layout.addWidget(apply_btn)

        layout.addWidget(url_row)

        self.video_widget = QWidget(self.root_widget)
        self.video_widget.setStyleSheet("background: black;")
        self.video_widget.setAttribute(Qt.WidgetAttribute.WA_NativeWindow, True)
        self.video_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self.video_widget, 1)

        if resolved_source_type is None or resolved_source is None:
            layout.addWidget(QLabel("RTSPView: configuration invalide (source manquante)."))
            self.event_bus.publish_sync("log", f"RTSPView[{self.name}] invalid source configuration")
            return self.root_widget

        if not self._rebuild_pipeline(resolved_source_type, resolved_source):
            self.event_bus.publish_sync("log", f"RTSPView[{self.name}] pipeline build failed")
            return self.root_widget
        self.event_bus.publish_sync("log", f"RTSPView[{self.name}] pipeline ready ({resolved_source_type}: {resolved_source})")
        return self.root_widget

    def get_widget(self) -> QWidget:
        if self.root_widget is None:
            self.build()
        return self.root_widget  # type: ignore[return-value]

    def start(self):
        if self.pipeline is not None:
            sink = self.pipeline.get_by_name("video_sink")
            if sink is not None and self.video_widget is not None:
                win_id = int(self.video_widget.winId())
                if hasattr(sink, "set_window_handle"):
                    sink.set_window_handle(win_id)
                else:
                    GstVideo.VideoOverlay.set_window_handle(sink, win_id)  # type: ignore[misc]
            self.pipeline.set_state(Gst.State.PLAYING)  # type: ignore[misc]
            self.event_bus.publish_sync("log", f"RTSPView[{self.name}] PLAYING")

    def pause(self):
        if self.pipeline is not None:
            self.pipeline.set_state(Gst.State.PAUSED)  # type: ignore[misc]
            self.event_bus.publish_sync("log", f"RTSPView[{self.name}] PAUSED")

    def stop(self):
        self._teardown_pipeline()
        self.event_bus.publish_sync("log", f"RTSPView[{self.name}] stopped")

        self.video_widget = None
        self.urlField = None
        self.root_widget = None

    def _teardown_pipeline(self):
        if self.pipeline is not None:
            self.pipeline.set_state(Gst.State.NULL)  # type: ignore[misc]
            self.pipeline = None

        if self.bus is not None:
            self.bus.remove_signal_watch()
            self.bus = None

    def _bind_video_sink(self):
        if self.pipeline is None or self.video_widget is None:
            return False

        sink = self.pipeline.get_by_name("video_sink")
        if sink is None:
            print("Erreur: impossible de récupérer video_sink")
            return False

        win_id = int(self.video_widget.winId())
        if hasattr(sink, "set_window_handle"):
            sink.set_window_handle(win_id)
        else:
            GstVideo.VideoOverlay.set_window_handle(sink, win_id)  # type: ignore[misc]
        return True

    def _rebuild_pipeline(self, source_type: str, source: str) -> bool:
        self.event_bus.publish_sync("log", f"RTSPView[{self.name}] rebuilding pipeline ({source_type}: {source})")
        self._teardown_pipeline()

        self.pipeline = self._create_pipeline(source_type, source)
        if self.pipeline is None:
            return False

        if not self._bind_video_sink():
            self._teardown_pipeline()
            return False

        self.bus = self.pipeline.get_bus()
        self.bus.add_signal_watch()
        self.bus.connect("message", self._on_bus_message)

        self.start()
        return True

    def _apply_url_change(self):
        if self.urlField is None:
            return

        new_source = self.urlField.text().strip()
        if not new_source:
            return

        resolved_source_type, resolved_source = self._resolve_source(None, new_source)
        if resolved_source_type is None or resolved_source is None:
            return

        self.config["source"] = resolved_source
        self.config["source_type"] = resolved_source_type
        self.event_bus.publish_sync("log", f"RTSPView[{self.name}] URL changed to {resolved_source}")
        self._rebuild_pipeline(resolved_source_type, resolved_source)

    def restart_pipeline(self):
        resolved_source_type, resolved_source = self._resolve_source(None, None)
        if resolved_source_type is None or resolved_source is None:
            return False
        self.event_bus.publish_sync("log", f"RTSPView[{self.name}] restart requested")
        return self._rebuild_pipeline(resolved_source_type, resolved_source)

    def _on_bus_message(self, bus, message):
        msg_type = message.type

        if msg_type == Gst.MessageType.ERROR:  # type: ignore[misc]
            err, debug = message.parse_error()
            print(f"[GStreamer][ERROR] {err}")
            self.event_bus.publish_sync("log", f"RTSPView[{self.name}][ERROR] {err}")
            if debug:
                print(f"[DEBUG] {debug}")
                self.event_bus.publish_sync("log", f"RTSPView[{self.name}][DEBUG] {debug}")

        elif msg_type == Gst.MessageType.EOS:  # type: ignore[misc]
            print("[GStreamer] End of stream")
            self.event_bus.publish_sync("log", f"RTSPView[{self.name}] End of stream")



    def _resolve_source(self, source_type: str | None, source: str | None) -> tuple[str | None, str | None]:
        resolved_source = source or self.config.get("source") or self.config.get("url")
        if not isinstance(resolved_source, str) or not resolved_source.strip():
            return None, None
        resolved_source = resolved_source.strip()

        normalized_type = (source_type or self.config.get("source_type") or "").strip().lower()
        if not normalized_type:
            if resolved_source.startswith(("rtsp://", "rtsps://")):
                normalized_type = self.SourceType.RTSP
            elif resolved_source.startswith("/dev/"):
                normalized_type = self.SourceType.USB_VTX
            else:
                # Default heuristic: treat as RTSP-like URL.
                normalized_type = self.SourceType.RTSP

        return normalized_type, resolved_source

    def _create_pipeline(self, source_type: str, source: str):
        sink_type = str(self.config.get("sink", "ximagesink")).strip() or "ximagesink"

        if source_type == self.SourceType.USB_VTX:
            pipeline_str = (
                f"v4l2src device={source} io-mode=2 do-timestamp=false ! "
                f"queue max-size-buffers=1 leaky=downstream ! "
                f"videoconvert ! "
                f"{sink_type} name=video_sink sync=false qos=false"
            )
            print("[GStreamer] Pipeline:", pipeline_str)
            try:
                return Gst.parse_launch(pipeline_str)  # type: ignore[misc]
            except Exception as e:
                print("Erreur Gst.parse_launch:", e)
                return None

        elif source_type == self.SourceType.RTSP:
            return self._create_rtsp_pipeline(source, sink_type)

        else:
            print(f"Type de source non supporté: {source_type}")
            return None

    def _create_rtsp_pipeline(self, source: str, sink_type: str):
        """Build the RTSP pipeline programmatically.

        rtspsrc exposes dynamic "sometimes" pads that are created only after
        RTSP negotiation.  Linking it statically via parse_launch causes a
        not-linked (-1) error on the UDP src.  Using pad-added signal fixes it.
        """
        transport = str(self.config.get("rtsp_transport", "udp")).strip().lower() or "udp"
        # GstRTSPLowerTrans flags: UDP=4, TCP=16
        protocols_flag = 4 if transport == "udp" else 16

        print(
            f'[GStreamer] Pipeline: rtspsrc location="{source}" protocols={transport} latency=0 '
            f"buffer-mode=none drop-on-latency=true ! rtph265depay ! h265parse ! "
            f"avdec_h265 max-threads=4 ! queue max-size-buffers=1 leaky=downstream ! "
            f"videoconvert ! {sink_type} name=video_sink sync=false qos=false"
        )

        try:
            pipeline = Gst.Pipeline.new("rtsp-pipeline")  # type: ignore[misc]

            rtspsrc = Gst.ElementFactory.make("rtspsrc", "rtspsrc0")  # type: ignore[misc]
            depay   = Gst.ElementFactory.make("rtph265depay", "depay")  # type: ignore[misc]
            parse   = Gst.ElementFactory.make("h265parse", "h265parse")  # type: ignore[misc]
            decode  = Gst.ElementFactory.make("avdec_h265", "decode")  # type: ignore[misc]
            queue   = Gst.ElementFactory.make("queue", "queue")  # type: ignore[misc]
            convert = Gst.ElementFactory.make("videoconvert", "convert")  # type: ignore[misc]
            sink    = Gst.ElementFactory.make(sink_type, "video_sink")  # type: ignore[misc]

            for name, el in (
                ("rtspsrc", rtspsrc),
                ("rtph265depay", depay),
                ("h265parse", parse),
                ("avdec_h265", decode),
                ("queue", queue),
                ("videoconvert", convert),
                (sink_type, sink),
            ):
                if el is None:
                    print(f"[GStreamer] Impossible de créer l'élément: {name}")
                    return None
                pipeline.add(el)

            rtspsrc.set_property("location", source)
            rtspsrc.set_property("protocols", protocols_flag)
            rtspsrc.set_property("latency", 0)
            rtspsrc.set_property("drop-on-latency", True)

            decode.set_property("max-threads", 4)
            queue.set_property("max-size-buffers", 1)
            queue.set_property("leaky", 2)  # 2 = downstream
            sink.set_property("sync", False)
            sink.set_property("qos", False)

            # Link the static portion of the pipeline (depay → sink)
            for src_el, dst_el in ((depay, parse), (parse, decode), (decode, queue), (queue, convert), (convert, sink)):
                if not src_el.link(dst_el):
                    print(f"[GStreamer] Échec du lien: {src_el.get_name()} → {dst_el.get_name()}")
                    return None

            # rtspsrc creates its src pad dynamically after RTSP negotiation.
            # Link it to rtph265depay once the pad is available.
            def _on_pad_added(src, new_pad, depay_el=depay):  # type: ignore[misc]
                sink_pad = depay_el.get_static_pad("sink")
                if sink_pad.is_linked():
                    return
                ret = new_pad.link(sink_pad)
                if ret != Gst.PadLinkReturn.OK:  # type: ignore[misc]
                    print(f"[GStreamer] Échec liaison pad dynamique: {ret}")

            rtspsrc.connect("pad-added", _on_pad_added)
            return pipeline

        except Exception as e:
            print("[GStreamer] Erreur création pipeline RTSP:", e)
            return None

