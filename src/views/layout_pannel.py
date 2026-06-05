from PySide6.QtWidgets import QWidget, QHBoxLayout, QGridLayout, QVBoxLayout, QLabel
from PySide6.QtCore import QRect
from typing import List

from .web_camera_view import WebCameraView
from .camera_widget import CameraWidget
from .components.bitmap import Bitmap
from src.controller.event_bus import EventBus

# Import known view wrappers for high-level composition
from .rtsp_view import RTSPView
from .console_view import DebugConsole


class AbsoluteContainer(QWidget):
    """Container that positions children with absolute coordinates.

    Each layer is defined by (widget, style) where style supports:
      x, y        — position in px or "N%" relative to container
      width, height — size in px or "N%" (default: "100%")
      z_index     — stacking order (higher = on top)
      margin      — uniform outer inset applied to all four sides
      padding     — inner content margin applied inside the widget area
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._layers: list[tuple[QWidget, dict]] = []

    def add_layer(self, widget: QWidget, style: dict) -> None:
        widget.setParent(self)
        self._layers.append((widget, style))
        # Re-sort by z_index so lower indices are raised first (higher z ends on top)
        self._layers.sort(key=lambda x: x[1].get("z_index", 0))
        for w, _ in self._layers:
            w.raise_()
        widget.show()
        self._relayout()

    @staticmethod
    def _resolve(value, parent_dim: int) -> int:
        if isinstance(value, str) and value.endswith("%"):
            return int(parent_dim * float(value[:-1]) / 100)
        return int(value)

    def _relayout(self) -> None:
        pw, ph = self.width(), self.height()
        for widget, style in self._layers:
            margin = int(style.get("margin", 0))
            w = self._resolve(style.get("width", "100%"), pw) - 2 * margin
            h = self._resolve(style.get("height", "100%"), ph) - 2 * margin

            if "right" in style:
                x = pw - self._resolve(style["right"], pw) - w - margin
            else:
                x = self._resolve(style.get("x", 0), pw) + margin

            if "bottom" in style:
                y = ph - self._resolve(style["bottom"], ph) - h - margin
            else:
                y = self._resolve(style.get("y", 0), ph) + margin

            padding = int(style.get("padding", 0))
            if padding:
                child_layout = widget.layout()
                if child_layout is not None:
                    child_layout.setContentsMargins(padding, padding, padding, padding)
            widget.setGeometry(QRect(x, y, max(1, w), max(1, h)))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._relayout()

    def showEvent(self, event):
        super().showEvent(event)
        self._relayout()


class LayoutPanel:
    """High-level layout panel.

    Responsibilities (high-level):
    - Interpret a layout config and compose child view classes.
    - Delegate UI construction to the child view classes (via `get_widget()`).
    - Expose `get_widget()` to provide the assembled QWidget to the caller.

    Concrete UI population is intentionally left to the child view classes.
    """

    def __init__(self, name: str, config: dict, children: List[object], event_bus: EventBus | None = None):
        self.name = name
        self.config = config
        self.children = children
        self._widget = None
        self.event_bus = event_bus or EventBus()
        self._children_by_name: dict[str, object] = {}

    def build(self):
        """High-level build: interpret layout config and place child widgets."""
        if self._widget is None:
            self._widget = QWidget()

            pos = self.config.get("diaposition", "horizontal")

            if pos == "absolute":
                container = AbsoluteContainer()
                for child_cfg in self.config.get("content", []):
                    style = child_cfg.get("style", {})
                    child_widget = self._make_child_widget(child_cfg)
                    container.add_layer(child_widget, style)
                self._widget = container
                return

            if pos == "grid":
                grid_cfg = self.config.get("grid", {})
                rows = int(grid_cfg.get("rows", 1))
                cols = int(grid_cfg.get("columns", 1))
                layout = QGridLayout()
                layout.setContentsMargins(0, 0, 0, 0)
                layout.setSpacing(int(grid_cfg.get("spacing", 8)))

                for row in range(rows):
                    layout.setRowStretch(row, 1)
                for col in range(cols):
                    layout.setColumnStretch(col, 1)

                content = self.config.get("content", [])
                for idx, child_cfg in enumerate(content):
                    grid_item = child_cfg.get("grid", {})
                    r = int(grid_item.get("row", idx // cols))
                    c = int(grid_item.get("column", idx % cols))
                    row_span = int(grid_item.get("row_span", 1))
                    col_span = int(grid_item.get("column_span", 1))
                    w = self._make_child_widget(child_cfg)
                    layout.addWidget(w, r, c, row_span, col_span)

            elif pos == "vertical":
                layout = QVBoxLayout()
                layout.setContentsMargins(0, 0, 0, 0)
                for child_cfg in self.config.get("content", []):
                    layout.addWidget(self._make_child_widget(child_cfg))

            else:
                # default to horizontal
                layout = QHBoxLayout()
                layout.setContentsMargins(0, 0, 0, 0)
                for child_cfg in self.config.get("content", []):
                    layout.addWidget(self._make_child_widget(child_cfg))

            self._widget.setLayout(layout)

    def get_widget(self) -> QWidget:
        if self._widget is None:
            # Ensure build() has been called so layout is created
            self.build()
        return self._widget

    def get_child_view(self, name: str):
        return self._children_by_name.get(name)

    def _register_child(self, name: str, child: object) -> None:
        self.children.append(child)
        self._children_by_name[name] = child

    def _merge_dicts(self, parent_data: dict, child_data: dict) -> dict:
        merged = dict(parent_data)
        for key, value in child_data.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = self._merge_dicts(merged[key], value)
            else:
                merged[key] = value
        return merged

    def _resolve_child_data(self, child_cfg: dict) -> dict:
        parent_data = self.config.get("data", {})
        child_data = child_cfg.get("data", {})
        if not isinstance(parent_data, dict):
            parent_data = {}
        if not isinstance(child_data, dict):
            child_data = {}
        return self._merge_dicts(parent_data, child_data)

    def _make_child_widget(self, child_cfg: dict) -> QWidget:
        """Create a lightweight widget for a child view config."""
        vtype = str(child_cfg.get("type", "")).strip().lower()
        name = child_cfg.get("name", "unnamed")
        data = self._resolve_child_data(child_cfg)

        if vtype == "layout":
            nested = LayoutPanel(name, child_cfg, [], event_bus=self.event_bus)
            nested.build()
            self._register_child(name, nested)
            return nested.get_widget()

        if vtype == "rtsp":
            rtsp = RTSPView(name, data, event_bus=self.event_bus)
            rtsp.build()
            self._register_child(name, rtsp)
            return rtsp.get_widget()

        if vtype == "webcamera":
            camera = WebCameraView(name, data, event_bus=self.event_bus)
            camera.build()
            self._register_child(name, camera)
            return camera.get_widget()
        if vtype == "camera":
            camera = CameraWidget(name, data, event_bus=self.event_bus)
            camera.build()
            self._register_child(name, camera)
            return camera.get_widget()
        if vtype == "console":
            console = DebugConsole()
            # Console can be attached later to the global EventBus
            self._register_child(name, console)
            return console
        if vtype == "threejsviewer":
            from .components.threejsViewer import ThreejsViewer
            viewer_config = dict(data)
            controls = child_cfg.get("controls")
            if controls is not None:
                viewer_config["controls"] = controls
            viewer = ThreejsViewer(viewer_config, event_bus=self.event_bus)
            viewer.build()
            self._register_child(name, viewer)
            return viewer
        if vtype == "table":
            from .components.table import Table
            table = Table(data.get("header", []), data.get("data", []))
            table.build()
            self._register_child(name, table)
            return table

        if vtype == "chart":
            from .components.chart import ChartWidget
            chart = ChartWidget(data, event_bus=self.event_bus)
            self._register_child(name, chart)
            return chart

        if vtype == "map":
            from .components.map_widget import MapWidget
            widget = MapWidget(data, event_bus=self.event_bus)
            widget.build()
            self._register_child(name, widget)
            return widget

        if vtype == "button_bar":
            from .components.button_bar import ButtonBar
            bar = ButtonBar(data, event_bus=self.event_bus)
            self._register_child(name, bar)
            return bar

        if vtype == "bitmap":
            bitmap = Bitmap(name, data, event_bus=self.event_bus)
            bitmap.build()
            self._register_child(name, bitmap)
            return bitmap.get_widget()

        if vtype == "robot":
            from .components.urdf_viewer import URDFViewer
            controls = child_cfg.get("controls")
            viewer_config = dict(data)
            if controls is not None:
                viewer_config["controls"] = controls
            viewer = URDFViewer(name, viewer_config, event_bus=self.event_bus)
            viewer.build()
            self._register_child(name, viewer)
            return viewer

        # Placeholder for other view types (table, map, point_cloud, etc.)
        lbl = QLabel(f"Placeholder {vtype}: {name}")
        return lbl
