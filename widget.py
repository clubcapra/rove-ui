# This Python file uses the following encoding: utf-8
from __future__ import annotations
import asyncio

import sys
from json import load
from typing import Any

from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QMenuBar,
    QLabel,
    QStackedWidget,
)

from PySide6.QtGui import QAction

# Import view skeletons (high-level)
from src.views.console_view import DebugConsole
from src.views.rtsp_view import RTSPView
from src.views.layout_pannel import LayoutPanel
from src.controller.event_bus import EventBus
from src.views.components.header import Header


class Widget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Capraui - Dashboard")

        self._header = Header(parent=self)
        self._menu = QMenuBar(self)
        self._central = QWidget(self)
        self._central_layout = QVBoxLayout(self._central)
        self._central_layout.setContentsMargins(0, 0, 0, 0)
        # stacked widget for top-level pages (dashboard, logs, ...)
        self._stack = QStackedWidget(self._central)
        self._central_layout.addWidget(self._stack)
        #self._console = DebugConsole(self)
        self.event_bus = EventBus()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._header)
        layout.addWidget(self._menu)
        layout.addWidget(self._central)
        #layout.addWidget(self._console)

        self._views: list[Any] = []
        self._pages: dict[str, int] = {}


        # Application-wide EventBus (can be shared or passed to orchestrator)
        self.event_bus = EventBus()


    def load_config(self, configFile):
        """Load JSON from a path and build the interface."""
        if isinstance(configFile, str):
            with open(configFile, "r", encoding="utf-8") as f:
                data = load(f)
        return data

    def buildInterface(self, config: dict):
        """Construct the main interface from the config."""

        config = self.load_config(config)

        header_settings = config.get("header_settings", {})
        header_index = self.layout().indexOf(self._header)
        self.layout().removeWidget(self._header)
        self._header.deleteLater()
        self._header = Header(settings=header_settings, parent=self)
        self.layout().insertWidget(header_index, self._header)

        views_root = config.get("views", {})

        # Clear previous stack pages
        while self._stack.count():
            w = self._stack.widget(0)
            self._stack.removeWidget(w)
            w.setParent(None)

        # Build a 'Views' menu to navigate top-level view pages
        self._menu.clear()
        menu = self._menu.addMenu("Views")

        for view_name, view_cfg in views_root.items():
            vtype = view_cfg.get("type")
            if vtype == "layout":
                panel = LayoutPanel(view_name, view_cfg, children=[])
                panel.build()
                page_widget = panel.get_widget()
                self._views.append(panel)
            else:
                page_widget = QLabel(f"Page placeholder: {view_name} ({vtype})")

            idx = self._stack.addWidget(page_widget)
            self._pages[view_name] = idx

            action = QAction(view_name, self)
            action.triggered.connect(lambda checked, i=idx: self._stack.setCurrentIndex(i))
            menu.addAction(action)

        if self._stack.count() > 0:
            self._stack.setCurrentIndex(0)

    def update_header_time(self, time_value: str):
        self._header.update_time(time_value)

    def update_header_battery(self, battery_level: int):
        self._header.update_battery(battery_level)




if __name__ == "__main__":
    app = QApplication([])
    window = Widget()
    window.buildInterface("./config/config.json")
    window.showMaximized()
    try:
        asyncio.run(window.event_bus.publish("log", "Window : Application has started."))
    except Exception:
        pass
    sys.exit(app.exec())


