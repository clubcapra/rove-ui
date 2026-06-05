# This Python file uses the following encoding: utf-8
from __future__ import annotations
import asyncio

import os
import sys
from json import load
from typing import Any

from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QLabel,
    QStackedWidget,
)

from PySide6.QtGui import QIcon
from pathlib import Path

from src.views.layout_pannel import LayoutPanel
from src.views import theme
from src.controller.event_bus import EventBus
from src.views.components.header import Header
from src.views.components.nav_bar import NavBar
from src.clients.udp_client import UDPClient
from src.clients.ros2_client import ROS2Client


class Widget(QWidget):
    def __init__(self, parent=None, event_bus: EventBus | None = None):
        super().__init__(parent)
        self.setWindowTitle("Rove - UI")

        self.event_bus = event_bus or EventBus()

        self._header = Header(parent=self)
        self._nav = NavBar(self)
        self._central = QWidget(self)
        self._central_layout = QVBoxLayout(self._central)
        self._central_layout.setContentsMargins(0, 0, 0, 0)
        self._stack = QStackedWidget(self._central)
        self._central_layout.addWidget(self._stack)

        self._main_layout = QVBoxLayout(self)
        self._main_layout.setContentsMargins(0, 0, 0, 0)
        self._main_layout.setSpacing(0)
        self._main_layout.addWidget(self._header)
        self._main_layout.addWidget(self._nav)
        self._main_layout.addWidget(self._central)

        self._views: list[Any] = []
        self._pages: dict[str, int] = {}
        self._udp_clients: list[UDPClient] = []
        self._ros2_clients: list[ROS2Client] = []
        self._bottom_bar: QWidget | None = None


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

        self._nav.clear()

        for view_name, view_cfg in views_root.items():
            vtype = view_cfg.get("type")
            if vtype == "layout":
                panel = LayoutPanel(view_name, view_cfg, children=[], event_bus=self.event_bus)
                panel.build()
                page_widget = panel.get_widget()
                self._views.append(panel)
            else:
                page_widget = QLabel(f"Page placeholder: {view_name} ({vtype})")

            idx = self._stack.addWidget(page_widget)
            self._pages[view_name] = idx
            self._nav.add_page(view_name, lambda i=idx: self._stack.setCurrentIndex(i))

        if self._stack.count() > 0:
            self._stack.setCurrentIndex(0)
            self._nav.activate_first()

        self._rebuild_bottom_bar(config.get("bottom_bar"))
        self._restart_udp_clients(config.get("udp_clients", []))
        self._restart_ros2_clients(config.get("ros2_clients", []))

    def _rebuild_bottom_bar(self, bar_cfg: dict | None) -> None:
        if self._bottom_bar is not None:
            self._main_layout.removeWidget(self._bottom_bar)
            self._bottom_bar.deleteLater()
            self._bottom_bar = None
        if bar_cfg:
            from src.views.components.button_bar import ButtonBar
            self._bottom_bar = ButtonBar(bar_cfg, event_bus=self.event_bus)
            self._main_layout.addWidget(self._bottom_bar)

    def update_header_time(self, time_value: str):
        self._header.update_time(time_value)

    def update_header_battery(self, battery_level: int):
        self._header.update_battery(battery_level)

    def _restart_udp_clients(self, client_configs: list[dict[str, Any]]) -> None:
        for client in self._udp_clients:
            client.stop()
        self._udp_clients = []

        for client_config in client_configs:
            client = UDPClient(client_config, self.event_bus)
            client.start()
            self._udp_clients.append(client)

    def _restart_ros2_clients(self, client_configs: list[dict[str, Any]]) -> None:
        for client in self._ros2_clients:
            client.stop()
        self._ros2_clients = []

        for client_config in client_configs:
            client = ROS2Client(client_config, self.event_bus)
            client.start()
            self._ros2_clients.append(client)

    def closeEvent(self, event):
        for client in self._udp_clients:
            client.stop()
        self._udp_clients = []
        for client in self._ros2_clients:
            client.stop()
        self._ros2_clients = []
        super().closeEvent(event)




if __name__ == "__main__":
    app = QApplication([])
    app.setApplicationName("Rove - UI")
    app.setDesktopFileName("rove-ui")
    _icon_dir = Path(__file__).resolve().parent / "src" / "media" / "icons"
    _app_icon: QIcon | None = None
    for _candidate in (_icon_dir / "app_icon.png", _icon_dir / "app_icons.png"):
        if _candidate.exists():
            _app_icon = QIcon(str(_candidate))
            break
    if _app_icon:
        app.setWindowIcon(_app_icon)
    window = Widget()
    if _app_icon:
        window.setWindowIcon(_app_icon)
    app.setStyleSheet(theme.GLOBAL)

    window.buildInterface("./config/config_window1.json")
    window.showFullScreen()
    window.setStyleSheet(f"background: {theme.BG_DEEP};")
    screens = app.screens()
    primary_screen = app.primaryScreen()

    window.move(primary_screen.geometry().topLeft())
    secondary_screens = [s for s in screens if s != primary_screen]

    if os.path.exists("./config/config_window2.json"):
        window2 = Widget(event_bus=window.event_bus)
        if _app_icon:
            window2.setWindowIcon(_app_icon)
        window2.buildInterface("./config/config_window2.json")
        screens = app.screens()
        if len(screens) > 1:
            second_screen = secondary_screens[0]
            window2.move(second_screen.geometry().topLeft())
            asyncio.run(window.event_bus.publish("log", "Window : Application has started on the second screen."))

        window2.showFullScreen()
        window2.setStyleSheet(f"background: {theme.BG_DEEP};")

        
    try:
        asyncio.run(window.event_bus.publish("log", "Window : Application has started."))
    except Exception:
        pass
    sys.exit(app.exec())


