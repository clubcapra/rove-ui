from __future__ import annotations

import json
import math
import time
from pathlib import Path

import json as _json
from PySide6.QtCore import QUrl, Signal, Slot, QTimer
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import QWidget, QVBoxLayout, QDialog
from PySide6.QtWebEngineCore import QWebEngineSettings, QWebEnginePage
from PySide6.QtWebEngineWidgets import QWebEngineView
from src.controller.event_bus import EventBus


FALLBACK_HTML = """<!DOCTYPE html><html><body style="background:#080808;color:#4a6880;font-family:monospace">Missing template: src/views/components/html/map.html</body></html>"""


def _center_dialog(dialog, parent: QWidget) -> None:
    """Center a dialog over its parent widget."""
    dialog.adjustSize()
    center = parent.mapToGlobal(parent.rect().center())
    dialog.move(center.x() - dialog.width() // 2, center.y() - dialog.height() // 2)

_CB_PREFIX = "__mapcb__:"


class _MapPage(QWebEnginePage):
    """Custom page that intercepts __mapcb__: console messages for JS→Python bridge."""

    def __init__(self, event_bus: EventBus, on_action, parent=None):
        super().__init__(parent)
        self._event_bus = event_bus
        self._on_action = on_action

    def javaScriptConsoleMessage(self, level, message, lineNumber, sourceID):  # noqa: N802
        if message and message.startswith(_CB_PREFIX):
            try:
                data = _json.loads(message[len(_CB_PREFIX):])
                self._on_action(data)
            except Exception:
                pass
            return
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
        self._html_template = Path(__file__).resolve().parent / "html" / "map.html"
        self._is_ready = False
        self._pending_scripts: list[str] = []
        self._robot_lat: float | None = None
        self._robot_lng: float | None = None
        self._last_position_push: float = 0.0
        self._first_center_done = False
        self._poi_seq = 0
        self._mission_seq = 0
        self._js_queue.connect(self._exec_js)

        # Relative position state (mapping API)
        self._robot_x: float = 0.0
        self._robot_y: float = 0.0
        self._start_map_x: float | None = None   # map-frame coords when start was set
        self._start_map_y: float | None = None
        self._pos_nam: QNetworkAccessManager | None = None
        self._pos_timer: QTimer | None = None
        self._pos_pending: bool = False

    def _load_html(self) -> str:
        try:
            return self._html_template.read_text(encoding="utf-8")
        except OSError:
            return FALLBACK_HTML

    def build(self) -> None:
        self._view = QWebEngineView()
        page = _MapPage(self._event_bus, self._handle_map_action, self._view)
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
        self._register_tile_source()
        self._register_relative_position()

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

    def _register_tile_source(self) -> None:
        topic = str(self._config.get("tile_source_topic", "")).strip()
        if not topic:
            return
        def _on_tile_source(url: str) -> None:
            self.run_js(f"window.mapSetTileLayer({json.dumps(str(url))});")
        self._event_bus.subscribe(topic, _on_tile_source)

    def _register_position_tracking(self) -> None:
        lat_topic = str(self._config.get("robot_position_lat_topic", "")).strip()
        lng_topic = str(self._config.get("robot_position_lng_topic", "")).strip()
        yaw_topic = str(self._config.get("robot_position_yaw_topic", "")).strip()
        if not lat_topic and not lng_topic:
            return

        def _push():
            if self._robot_lat is None or self._robot_lng is None:
                return
            now = time.monotonic()
            if now - self._last_position_push < 0.05:  # throttle to ~20 fps
                return
            self._last_position_push = now
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

        def _on_marker_remove(payload):
            marker_id = str(payload.get("id", "")) if isinstance(payload, dict) else str(payload)
            if marker_id:
                self.run_js(f"window.mapRemoveMissionStep({json.dumps(marker_id)});")

        self._event_bus.subscribe("mission.marker_remove", _on_marker_remove)

    def _register_relative_position(self) -> None:
        pos_src = str(self._config.get("position_source", "")).strip()
        if not pos_src:
            return
        self._pos_nam = QNetworkAccessManager(self)
        self._pos_nam.finished.connect(self._on_pos_reply)
        self._pos_timer = QTimer(self)
        self._pos_timer.timeout.connect(self._fetch_pos)
        interval_ms = max(100, int(self._config.get("pos_poll_interval_ms", 200)))
        self._pos_timer.start(interval_ms)
        self._fetch_pos()
        self._event_bus.publish_sync("log", f"MapWidget: relative position source {pos_src}")

    def _fetch_pos(self) -> None:
        if self._pos_pending or self._pos_nam is None:
            return
        src = str(self._config.get("position_source", "")).strip()
        if not src:
            return
        req = QNetworkRequest(QUrl(src))
        req.setRawHeader(b"Cache-Control", b"no-cache")
        self._pos_nam.get(req)
        self._pos_pending = True

    def _on_pos_reply(self, reply: QNetworkReply) -> None:
        self._pos_pending = False
        if reply.error() == QNetworkReply.NetworkError.NoError:
            try:
                data = _json.loads(bytes(reply.readAll()))
                self._robot_x = float(data.get("x", self._robot_x))
                self._robot_y = float(data.get("y", self._robot_y))
                if "yaw_deg" in data:
                    yaw = float(data["yaw_deg"])
                elif "yaw_rad" in data:
                    yaw = math.degrees(float(data["yaw_rad"]))
                elif "yaw" in data:
                    yaw = math.degrees(float(data["yaw"]))
                else:
                    yaw = None
                if self._start_map_x is not None:
                    yaw_arg = f"{yaw:.4f}" if yaw is not None else "null"
                    self.run_js(
                        f"window.mapUpdateRelativePosition("
                        f"{self._robot_x:.4f}, {self._robot_y:.4f}, {yaw_arg});"
                    )
            except Exception:
                pass
        reply.deleteLater()

    def _handle_map_action(self, data: dict) -> None:
        """Dispatches action-wheel selections from JS."""
        action = str(data.get("action", "poi"))

        if action == "remove_poi":
            poi_id = str(data.get("poi_id", ""))
            if poi_id:
                self.run_js(f"window.mapRemovePOI({json.dumps(poi_id)});")
                poi_topic = str(self._config.get("poi_remove_topic", "")).strip()
                if poi_topic:
                    self._event_bus.publish_sync(poi_topic, {"poi_id": poi_id})
            return

        if action == "set_start":
            try:
                lat = float(data["lat"])
                lng = float(data["lng"])
            except (KeyError, TypeError, ValueError):
                return
            self._start_map_x = self._robot_x
            self._start_map_y = self._robot_y
            self.run_js(
                f"window.mapSetStartPosition("
                f"{lat:.8f}, {lng:.8f}, "
                f"{self._robot_x:.4f}, {self._robot_y:.4f});"
            )
            self._event_bus.publish_sync(
                "log",
                f"[Map] Start set: GPS=({lat:.6f},{lng:.6f}) "
                f"map=({self._robot_x:.3f},{self._robot_y:.3f})",
            )
            return

        if action == "clear_start":
            self._start_map_x = None
            self._start_map_y = None
            self._event_bus.publish_sync("log", "[Map] Start position cleared")
            return

        try:
            lat = float(data["lat"])
            lng = float(data["lng"])
        except (KeyError, TypeError, ValueError):
            return

        if action == "poi":
            QTimer.singleShot(0, lambda: self._show_poi_dialog(lat, lng))
        elif action == "goto":
            QTimer.singleShot(0, lambda: self._handle_goto(lat, lng))
        elif action == "mission_goto":
            sid = self._next_step_id()
            self._publish_step("GoTo", {"a": {"lat": lat, "lng": lng, "alt": 0.0}}, sid)
            self._add_mission_marker("goto", lat, lng, sid)
        elif action == "mission_relay":
            sid = self._next_step_id()
            self._publish_step("RelayPosition", {"position": {"lat": lat, "lng": lng, "alt": 0.0}}, sid)
            self._add_mission_marker("relay", lat, lng, sid)
        elif action == "mission_sentinel_a":
            self._event_bus.publish_sync(
                "log", f"[Map] Sentinel A ({lat:.6f},{lng:.6f}) — tap map for point B"
            )
        elif action == "mission_sentinel_b":
            try:
                lat_a = float(data["lat_a"])
                lng_a = float(data["lng_a"])
            except (KeyError, TypeError, ValueError):
                return
            sid = self._next_step_id()
            self._publish_step("Sentinel", {
                "a": {"lat": lat_a, "lng": lng_a, "alt": 0.0},
                "b": {"lat": lat,   "lng": lng,   "alt": 0.0},
            }, sid)
            self._add_mission_marker("sentinel", lat_a, lng_a, sid, extra={"lat_b": lat, "lng_b": lng})
        elif action == "mission_orbit":
            QTimer.singleShot(0, lambda: self._handle_orbit(lat, lng))
        elif action == "mission_pathway":
            points = data.get("points", [])
            if len(points) >= 2:
                sid = self._next_step_id()
                self._publish_step("Pathway", {"points": [
                    {"lat": float(p["lat"]), "lon": float(p["lng"]), "alt": 0.0}
                    for p in points
                ]}, sid)
                self._add_mission_marker("pathway", lat, lng, sid, extra={"points": [
                    {"lat": float(p["lat"]), "lng": float(p["lng"])} for p in points
                ]})

    def _show_poi_dialog(self, lat: float, lng: float) -> None:
        from src.views.components.bitmap import _AltitudePicker, _NamePicker

        ocr_url = str(self._config.get("ocr_url", "")).strip()
        picker = _AltitudePicker(self._event_bus, ocr_url, self)
        _center_dialog(picker, self)
        if picker.exec() != QDialog.DialogCode.Accepted:
            return
        altitude  = picker.altitude()
        photo_url = picker.photo_data_url()

        self._poi_seq += 1
        default_name = f"WP{self._poi_seq:03d}"
        name_picker = _NamePicker(default_name, self)
        _center_dialog(name_picker, self)
        if name_picker.exec() != QDialog.DialogCode.Accepted:
            self._poi_seq -= 1
            return

        label  = name_picker.name() or default_name
        poi_id = f"poi_{self._poi_seq}"

        self.run_js(f"window.mapAddPOI({lat}, {lng}, {json.dumps(label)}, {json.dumps(poi_id)});")
        if photo_url:
            self.run_js(f"window.mapAttachPhoto({json.dumps(poi_id)}, {json.dumps(photo_url)});")

        poi_topic = str(self._config.get("poi_topic", "")).strip()
        if poi_topic:
            payload: dict = {"lat": lat, "lng": lng, "label": label, "alt": altitude, "poi_id": poi_id}
            if photo_url:
                payload["photo"] = photo_url
            self._event_bus.publish_sync(poi_topic, payload)

        self._event_bus.publish_sync(
            "log",
            f"[Map] POI {self._poi_seq} «{label}» → GPS=({lat:.6f},{lng:.6f}) alt={altitude:.2f}m",
        )

    def _handle_goto(self, lat: float, lng: float) -> None:
        goto_topic = str(self._config.get("goto_topic", "")).strip()
        if goto_topic:
            self._event_bus.publish_sync(goto_topic, {"lat": lat, "lng": lng})
        self._event_bus.publish_sync("log", f"[Map] GOTO → ({lat:.6f},{lng:.6f})")

    def _handle_orbit(self, lat: float, lng: float) -> None:
        from src.views.components.bitmap import _RadiusPicker
        picker = _RadiusPicker(10.0, self)
        _center_dialog(picker, self)
        if picker.exec() != QDialog.DialogCode.Accepted:
            return
        radius = picker.radius()
        sid = self._next_step_id()
        self._publish_step("Orbit", {
            "center": {"lat": lat, "lng": lng, "alt": 0.0},
            "radius": radius,
        }, sid)
        self._add_mission_marker("orbit", lat, lng, sid, extra={"radius": radius})

    def _next_step_id(self) -> str:
        self._mission_seq += 1
        return f"ms_{self._mission_seq}"

    def _add_mission_marker(
        self, mtype: str, lat: float, lng: float, step_id: str, extra: dict | None = None
    ) -> None:
        label = f"{mtype.upper()} #{self._mission_seq}"
        extra_js = json.dumps(extra or {})
        self.run_js(
            f"window.mapAddMissionStep("
            f"{json.dumps(mtype)},{json.dumps(step_id)},{lat},{lng},"
            f"{json.dumps(label)},{extra_js});"
        )

    def _publish_step(self, command: str, params: dict, map_marker_id: str = "") -> None:
        topic = str(self._config.get("mission_step_topic", "mission.step_request")).strip()
        self._event_bus.publish_sync(topic, {
            "command": command, "params": params, "map_marker_id": map_marker_id,
        })
        self._event_bus.publish_sync("log", f"[Map] → mission queue: {command}")

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
