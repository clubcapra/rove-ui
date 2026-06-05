from __future__ import annotations

import json
import tempfile
from pathlib import Path

import json as _json
from PySide6.QtCore import QUrl, Signal, Slot
from PySide6.QtWidgets import QWidget, QVBoxLayout
from PySide6.QtWebEngineCore import QWebEngineSettings, QWebEnginePage
from PySide6.QtWebEngineWidgets import QWebEngineView
from src.controller.event_bus import EventBus


FALLBACK_HTML = """<!DOCTYPE html><html><body style="background:#080808;color:#4a6880;font-family:monospace">Missing template: src/views/components/html/map.html</body></html>"""

_CB_PREFIX = "__mapcb__:"


class _MapPage(QWebEnginePage):
    """Custom page that intercepts __mapcb__: console messages for JS→Python bridge."""

    def __init__(self, event_bus: EventBus, on_click, parent=None):
        super().__init__(parent)
        self._event_bus = event_bus
        self._on_click  = on_click

    def javaScriptConsoleMessage(self, level, message, lineNumber, sourceID):  # noqa: N802
        if message and message.startswith(_CB_PREFIX):
            try:
                data = _json.loads(message[len(_CB_PREFIX):])
                self._on_click(
                    float(data["lat"]), float(data["lng"]),
                    str(data.get("label", "")), str(data.get("id", ""))
                )
            except Exception:
                pass
            return  # don't forward internal messages to the log
        if message:
            self._event_bus.publish_sync("log", f"MapWidget JS[{lineNumber}] {message}")
        super().javaScriptConsoleMessage(level, message, lineNumber, sourceID)


class MapWidget(QWidget):
    _js_queue: Signal = Signal(str)

    def __init__(self, config: dict | None = None, event_bus: EventBus | None = None):
        super().__init__()
        self.setMinimumSize(300, 200)
        self._view: QWebEngineView | None = None
        self._config = config or {}
        self._event_bus = event_bus or EventBus()
        self._html_file = Path(tempfile.gettempdir()) / "map_widget.html"
        self._html_template = Path(__file__).resolve().parent / "html" / "map.html"
        self._is_ready = False
        self._pending_scripts: list[str] = []
        self._robot_lat: float | None = None
        self._robot_lng: float | None = None
        self._first_center_done = False
        self._js_queue.connect(self._exec_js)

    def _load_html(self) -> str:
        try:
            return self._html_template.read_text(encoding="utf-8")
        except OSError:
            return FALLBACK_HTML

    def build(self) -> None:
        self._view = QWebEngineView()
        page = _MapPage(self._event_bus, self._handle_map_click, self._view)
        self._view.setPage(page)
        self._view.settings().setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True
        )
        self._view.loadFinished.connect(self._on_load_finished)

        # Load directly from source so relative paths (leaflet.min.js/css) resolve correctly
        self._view.load(QUrl.fromLocalFile(str(self._html_template)))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._view)

        self._register_position_tracking()
        self._register_poi_button()

    def _on_load_finished(self, ok: bool) -> None:
        self._is_ready = bool(ok)
        if not ok:
            self._event_bus.publish_sync("log", "MapWidget: HTML load failed")
            return
        self._event_bus.publish_sync("log", "MapWidget: ready")

        pending = list(self._pending_scripts)
        self._pending_scripts.clear()
        for script in pending:
            self._view.page().runJavaScript(script)  # type: ignore[union-attr]

        if self._config.get("local", False):
            local_url = str(self._config.get(
                "local_tile_url",
                "http://localhost:8080/tiles/{z}/{x}/{y}.png"
            ))
            self.run_js(f"window.mapSetTileLayer({json.dumps(local_url)});")

        lat = float(self._config.get("initial_lat", 45.5048))
        lng = float(self._config.get("initial_lng", -73.5773))
        zoom = int(self._config.get("initial_zoom", 15))
        self.run_js(f"window.mapSetView({lat}, {lng}, {zoom});")
        self.run_js(f"window.mapSetRobotPosition({lat}, {lng});")
        self._inject_icons()

    def _inject_icons(self) -> None:
        project_root = Path(__file__).resolve().parents[3]

        robot_img = str(self._config.get("robot_cursor_image", "")).strip()
        if robot_img:
            p = Path(robot_img) if Path(robot_img).is_absolute() else project_root / robot_img
            if p.exists():
                url = QUrl.fromLocalFile(str(p)).toString()
                size = self._config.get("robot_cursor_size", [36, 36])
                w, h = (size[0], size[1]) if isinstance(size, list) and len(size) >= 2 else (36, 36)
                self.run_js(f"window.mapSetRobotIcon({json.dumps(url)}, {w}, {h});")

        poi_img = str(self._config.get("poi_image", "")).strip()
        if poi_img:
            p = Path(poi_img) if Path(poi_img).is_absolute() else project_root / poi_img
            if p.exists():
                url = QUrl.fromLocalFile(str(p)).toString()
                size = self._config.get("poi_size", [24, 32])
                w, h = (size[0], size[1]) if isinstance(size, list) and len(size) >= 2 else (24, 32)
                self.run_js(f"window.mapSetPOIIcon({json.dumps(url)}, {w}, {h});")

    def _register_position_tracking(self) -> None:
        lat_topic = str(self._config.get("robot_position_lat_topic", "")).strip()
        lng_topic = str(self._config.get("robot_position_lng_topic", "")).strip()
        yaw_topic = str(self._config.get("robot_position_yaw_topic", "")).strip()
        if not lat_topic and not lng_topic:
            return

        def _push():
            if self._robot_lat is not None and self._robot_lng is not None:
                self.run_js(f"window.mapSetRobotPosition({self._robot_lat}, {self._robot_lng});")
                if not self._first_center_done:
                    self._first_center_done = True
                    self.run_js(f"window.mapSetView({self._robot_lat}, {self._robot_lng});")

        if lat_topic:
            def _on_lat(v):
                try:
                    self._robot_lat = float(v)
                except (TypeError, ValueError):
                    return
                _push()
            self._event_bus.subscribe(lat_topic, _on_lat)

        if lng_topic:
            def _on_lng(v):
                try:
                    self._robot_lng = float(v)
                except (TypeError, ValueError):
                    return
                _push()
            self._event_bus.subscribe(lng_topic, _on_lng)

        if yaw_topic:
            def _on_yaw(v):
                try:
                    yaw = float(v)
                except (TypeError, ValueError):
                    return
                self.run_js(f"window.mapSetRobotYaw({yaw:.4f});")
            self._event_bus.subscribe(yaw_topic, _on_yaw)

        self._event_bus.publish_sync(
            "log",
            f"MapWidget: position tracking (lat={lat_topic or '-'}, lng={lng_topic or '-'}, yaw={yaw_topic or '-'})"
        )

    def _register_poi_button(self) -> None:
        topic = str(self._config.get("add_poi_topic", "")).strip()
        if topic:
            def _on_press(value):
                if not value:
                    return
                if self._robot_lat is None or self._robot_lng is None:
                    return
                label = f"POI {self._robot_lat:.5f},{self._robot_lng:.5f}"
                self.run_js(f"window.mapAddPOI({self._robot_lat}, {self._robot_lng}, {json.dumps(label)});")

            self._event_bus.subscribe(topic, _on_press)
            self._event_bus.publish_sync("log", f"MapWidget: add-POI bound to '{topic}'")

        at_topic = str(self._config.get("add_poi_at_topic", "")).strip()
        if at_topic:
            def _on_poi_at(payload):
                if not isinstance(payload, dict):
                    return
                try:
                    lat = float(payload["lat"])
                    lng = float(payload["lng"])
                except (KeyError, TypeError, ValueError):
                    return
                label  = str(payload.get("label", f"{lat:.5f},{lng:.5f}"))
                poi_id = str(payload.get("poi_id", ""))
                self.run_js(
                    f"window.mapAddPOI({lat}, {lng}, {json.dumps(label)}, {json.dumps(poi_id)});"
                )
                photo = str(payload.get("photo", ""))
                if photo and poi_id:
                    self.run_js(
                        f"window.mapAttachPhoto({json.dumps(poi_id)}, {json.dumps(photo)});"
                    )

            self._event_bus.subscribe(at_topic, _on_poi_at)
            self._event_bus.publish_sync("log", f"MapWidget: add-POI-at bound to '{at_topic}'")

    def _handle_map_click(self, lat: float, lng: float, label: str, poi_id: str) -> None:
        """Called by JS when user clicks the map. Publishes to configured topics."""
        click_topic = str(self._config.get("click_topic", "")).strip()
        poi_topic   = str(self._config.get("poi_topic",   "")).strip()
        if click_topic:
            self._event_bus.publish_sync(click_topic, {"lat": lat, "lng": lng})
        if poi_topic:
            self._event_bus.publish_sync(
                poi_topic, {"lat": lat, "lng": lng, "label": label, "poi_id": poi_id}
            )

    @Slot(str)
    def _exec_js(self, script: str) -> None:
        if self._view:
            self._view.page().runJavaScript(script)

    def run_js(self, script: str) -> None:
        if not self._view:
            return
        if not self._is_ready:
            self._pending_scripts.append(script)
            return
        self._js_queue.emit(script)

    def recenter(self) -> None: self.run_js("window.mapRecenter();")

    # Navigation
    def pan_left(self)  -> None: self.run_js("window.mapPanLeft();")
    def pan_right(self) -> None: self.run_js("window.mapPanRight();")
    def pan_up(self)    -> None: self.run_js("window.mapPanUp();")
    def pan_down(self)  -> None: self.run_js("window.mapPanDown();")
    def zoom_in(self)   -> None: self.run_js("window.mapZoomIn();")
    def zoom_out(self)  -> None: self.run_js("window.mapZoomOut();")

    # POI
    def add_poi(self, lat: float, lng: float, label: str = "") -> None:
        self.run_js(f"window.mapAddPOI({lat}, {lng}, {json.dumps(label)});")

    def remove_poi(self, poi_id: str) -> None:
        self.run_js(f"window.mapRemovePOI({json.dumps(poi_id)});")

    def attach_photo(self, poi_id: str, data_url: str) -> None:
        self.run_js(f"window.mapAttachPhoto({json.dumps(poi_id)}, {json.dumps(data_url)});")

    def set_robot_position(self, lat: float, lng: float) -> None:
        self._robot_lat = lat
        self._robot_lng = lng
        self.run_js(f"window.mapSetRobotPosition({lat}, {lng});")
