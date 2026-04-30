from PySide6.QtWidgets import QWidget, QHBoxLayout, QGridLayout, QVBoxLayout, QLabel
from typing import List

from .web_camera_view import WebCameraView
from .camera_widget import CameraWidget
from .components.bitmap_placeholder import BitmapPlaceholder
from src.controller.event_bus import EventBus

# Import known view wrappers for high-level composition
from .rtsp_view import RTSPView
from .console_view import DebugConsole


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

        if vtype == "bitmap":
            bitmap = BitmapPlaceholder(name, data)
            bitmap.build()
            self._register_child(name, bitmap)
            return bitmap.get_widget()
        
        # Placeholder for other view types (table, map, point_cloud, etc.)
        lbl = QLabel(f"Placeholder {vtype}: {name}")
        return lbl
