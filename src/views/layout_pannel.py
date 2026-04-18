from PySide6.QtWidgets import QWidget, QHBoxLayout, QGridLayout, QVBoxLayout, QLabel
from typing import List

from .web_camera_view import WebCameraView
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

    def _make_child_widget(self, child_cfg: dict) -> QWidget:
        """Create a lightweight widget for a child view config."""
        vtype = str(child_cfg.get("type", "")).strip().lower()
        name = child_cfg.get("name", "unnamed")

        if vtype == "rtsp":
            rtsp = RTSPView(name, child_cfg.get("data", {}))
            rtsp.build()
            return rtsp.get_widget()

        if vtype == "webcamera":
            camera = WebCameraView(name, child_cfg.get("data", {}))
            camera.build()
            return camera.get_widget()
        if vtype == "console":
            console = DebugConsole()
            # Console can be attached later to the global EventBus
            return console
        if vtype == "threejsviewer":
            from .components.threejsViewer import ThreejsViewer
            viewer = ThreejsViewer()
            viewer.build()
            return viewer
        if vtype == "table":
            from .components.table import Table
            data = child_cfg.get("data", {})
            table = Table(data.get("header", []), data.get("data", []))
            table.build()
            return table

        if vtype == "chart":
            from .components.chart import ChartWidget
            return ChartWidget(child_cfg.get("data", {}), event_bus=self.event_bus)

        if vtype == "bitmap":
            bitmap = BitmapPlaceholder(name, child_cfg.get("data", {}))
            bitmap.build()
            return bitmap.get_widget()
        
        # Placeholder for other view types (table, map, point_cloud, etc.)
        lbl = QLabel(f"Placeholder {vtype}: {name}")
        return lbl
