import sys
import tempfile
import json
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout
from PySide6.QtWebEngineCore import QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from src.controller.event_bus import EventBus


FALLBACK_HTML = """<!DOCTYPE html><html><head><meta charset='utf-8'/><title>Three.js Viewer</title></head><body>Missing template: src/views/components/html/threejsViewer.html</body></html>"""


class ThreejsViewer(QWidget):
    def __init__(self, config=None, event_bus: EventBus | None = None):
        super().__init__()
        self.setMinimumSize(400, 300)
        self._view = None
        self._config = config or {}
        self._event_bus = event_bus or EventBus()
        self._html_file = Path(tempfile.gettempdir()) / "threejs_viewer.html"
        self._html_template_file = Path(__file__).resolve().parent / "html" / "threejsViewer.html"
        self._project_root = Path(__file__).resolve().parents[3]
        self._is_ready = False
        self._pending_scripts = []

    def _load_html_template(self) -> str:
        try:
            return self._html_template_file.read_text(encoding="utf-8")
        except OSError:
            self._event_bus.publish_sync("log", "ThreejsViewer: template file missing, using fallback HTML")
            return FALLBACK_HTML

    def build(self):
        self._event_bus.publish_sync("log", "ThreejsViewer: build started")
        self._view = QWebEngineView()
        self._view.settings().setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True
        )
        self._view.settings().setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True
        )
        self._view.loadFinished.connect(self._on_load_finished)

        self._html_file.write_text(self._load_html_template(), encoding="utf-8")
        self._view.load(QUrl.fromLocalFile(str(self._html_file)))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._view)

    def _on_load_finished(self, ok):
        self._is_ready = bool(ok)
        if not ok:
            self._event_bus.publish_sync("log", "ThreejsViewer: HTML load failed")
            return

        self._event_bus.publish_sync("log", "ThreejsViewer: HTML load finished")

        pending_scripts = list(self._pending_scripts)
        self._pending_scripts.clear()
        for script in pending_scripts:
            self._view.page().runJavaScript(script)

        object_sources = self._config.get("object_sources", [])
        self.set_legend_items_from_objects(object_sources)
        if object_sources:
            self._event_bus.publish_sync("log", f"ThreejsViewer: loading {len(object_sources)} object(s)")
            self.load_objects(object_sources, clear_existing=True)

    def _resolve_source_url(self, source: str) -> str:
        source_path = Path(source)
        candidates = []

        if source_path.is_absolute():
            candidates.append(source_path)
        else:
            candidates.append(self._project_root / source_path)
            candidates.append(self._project_root / "src" / source_path)

        for candidate in candidates:
            if candidate.exists():
                return QUrl.fromLocalFile(str(candidate.resolve())).toString()

        return source

    @staticmethod
    def _vector3(value, default):
        if value is None:
            return list(default)
        if isinstance(value, (int, float)):
            return [value, value, value]
        return list(value)

    def run_js(self, script):
        """Execute arbitrary JavaScript in the viewer."""
        if not self._view:
            return
        if not self._is_ready:
            self._pending_scripts.append(script)
            return
        self._view.page().runJavaScript(script)

    def clear_scene(self):
        self._event_bus.publish_sync("log", "ThreejsViewer: clear scene")
        self.run_js("window.clearScene();")

    def set_legend_items(self, items):
        payload = []
        for item in items:
            payload.append({
                "name": str(item.get("name", "Unnamed")),
                "color": item.get("color", "#4a90d9"),
            })
        self.run_js(f"window.setLegendItems({json.dumps(payload)});")

    def set_legend_items_from_objects(self, objects):
        legend_items = []
        for object_cfg in objects:
            if not isinstance(object_cfg, dict):
                continue
            if not object_cfg.get("name"):
                continue
            legend_items.append(
                {
                    "name": object_cfg.get("name"),
                    "color": object_cfg.get("color", "#4a90d9"),
                }
            )
        self.set_legend_items(legend_items)

    def load_object(
        self,
        name,
        source,
        position=None,
        rotation=None,
        scale=None,
        center=True,
        base_on_ground=True,
        color=None,
        flat_shading=True,
    ):
        self._event_bus.publish_sync("log", f"ThreejsViewer: load object {name} from {source}")
        options = {
            "position": self._vector3(position, (0, 0, 0)),
            "rotation": self._vector3(rotation, (0, 0, 0)),
            "scale": self._vector3(scale, (1, 1, 1)),
            "center": center,
            "baseOnGround": base_on_ground,
            "flatShading": flat_shading,
        }
        if color is not None:
            options["color"] = color

        source_url = self._resolve_source_url(source)
        self.run_js(
            f"window.loadModel({json.dumps(name)}, {json.dumps(source_url)}, {json.dumps(options)});"
        )

    def load_objects(self, objects, clear_existing=False):
        if clear_existing:
            self.clear_scene()

        self.set_legend_items_from_objects(objects)

        for object_cfg in objects:
            name = object_cfg.get("name")
            source = object_cfg.get("source")
            if not name or not source:
                continue
            self.load_object(
                name=name,
                source=source,
                position=object_cfg.get("position"),
                rotation=object_cfg.get("rotation"),
                scale=object_cfg.get("scale"),
                center=object_cfg.get("center", True),
                base_on_ground=object_cfg.get(
                    "base_on_ground",
                    object_cfg.get("baseOnGround", True),
                ),
                color=object_cfg.get("color"),
                flat_shading=object_cfg.get("flat_shading", True),
            )

    def set_object_transform(self, name, position=None, rotation=None, scale=None):
        self._event_bus.publish_sync("log", f"ThreejsViewer: set transform for {name}")
        transform = {}
        if position is not None:
            transform["position"] = self._vector3(position, (0, 0, 0))
        if rotation is not None:
            transform["rotation"] = self._vector3(rotation, (0, 0, 0))
        if scale is not None:
            transform["scale"] = self._vector3(scale, (1, 1, 1))
        self.run_js(
            f"window.setObjectTransform({json.dumps(name)}, {json.dumps(transform)});"
        )

    def set_object_position(self, name, x, y, z):
        self.set_object_transform(name, position=[x, y, z])

    def set_object_rotation(self, name, rx, ry, rz):
        self.set_object_transform(name, rotation=[rx, ry, rz])

    def set_object_scale(self, name, sx, sy, sz):
        self.set_object_transform(name, scale=[sx, sy, sz])

    def remove_object(self, name):
        self._event_bus.publish_sync("log", f"ThreejsViewer: remove object {name}")
        self.run_js(f"window.removeObject({json.dumps(name)});")

    def add_box(self, x=0, y=0, z=0, w=1, h=1, d=1, color=0x4a90d9):
        self.run_js(f"window.addBox({x},{y},{z},{w},{h},{d},{color});")

    def load_gltf(self, url):
        self.run_js(f"window.loadGLTF('{url}');")

    def load_stl(self, url, color=0x4a90d9):
        self.run_js(f"window.loadSTL('{url}', {color});")

    def update(self, data=None):
        """Rebuild scene from config data."""
        if data is None:
            return
        self._config = data
        object_sources = data.get("object_sources", [])
        self._event_bus.publish_sync("log", f"ThreejsViewer: update with {len(object_sources)} object(s)")
        self.set_legend_items_from_objects(object_sources)
        self.load_objects(object_sources, clear_existing=True)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = ThreejsViewer()
    w.build()
    w.resize(800, 600)
    w.show()
    sys.exit(app.exec())
