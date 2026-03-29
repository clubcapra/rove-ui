from PySide6.QtWidgets import QWidget, QHBoxLayout, QGridLayout, QVBoxLayout, QLabel
from typing import List

from .web_camera_view import WebCameraView

# Import known view wrappers for high-level composition
from .rtsp_view import RTSPView
from .camera_view import CameraView
from .console_view import DebugConsole


class LayoutPanel:
    """High-level layout panel.

    Responsibilities (high-level):
    - Interpret a layout config and compose child view classes.
    - Delegate UI construction to the child view classes (via `get_widget()`).
    - Expose `get_widget()` to provide the assembled QWidget to the caller.

    Concrete UI population is intentionally left to the child view classes.
    """

    def __init__(self, name: str, config: dict, children: List[object]):
        self.name = name
        self.config = config
        self.children = children
        self._widget = None

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

                content = self.config.get("content", [])
                for idx, child_cfg in enumerate(content):
                    r = idx // cols
                    c = idx % cols
                    w = self._make_child_widget(child_cfg)
                    layout.addWidget(w, r, c)

            elif pos == "vertical":
                layout = QVBoxLayout()
                for child_cfg in self.config.get("content", []):
                    layout.addWidget(self._make_child_widget(child_cfg))

            else:
                # default to horizontal
                layout = QHBoxLayout()
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
        vtype = child_cfg.get("type")
        name = child_cfg.get("name", "unnamed")

        if vtype == "rtsp":
            rtsp = RTSPView(name, child_cfg.get("data", {}))
            rtsp.build()
            return rtsp.get_widget()

        if vtype == "camera":
            camera = CameraView(name, child_cfg.get("data", {}))
            camera.build()
            return camera.get_widget()
        if vtype == "webcamera":
            camera = WebCameraView(name, child_cfg.get("data", {}))
            camera.build()
            return camera.get_widget()
        if vtype == "console":
            console = DebugConsole()
            # Console can be attached later to the global EventBus
            return console

        # Placeholder for other view types (table, map, point_cloud, etc.)
        lbl = QLabel(f"Placeholder {vtype}: {name}")
        return lbl
