from __future__ import annotations

import json
import os
import socket
from typing import Any

import yaml

from src.controller.event_bus import EventBus


class DeviceManager:
    """Manages evdev DeviceWorkers and bridges gamepad state to the EventBus + UDP."""

    def __init__(self, event_bus: EventBus | None = None) -> None:
        self.event_bus = event_bus or EventBus()
        self.workers: dict[str, Any] = {}
        self.config_data: dict = {"devices": []}
        self._udp_sock: socket.socket | None = None
        self._udp_host: str = ""
        self._udp_port: int = 0

    # ------------------------------------------------------------------
    # Configuration

    def configure_udp(self, host: str, port: int) -> None:
        self._udp_host = host
        self._udp_port = port
        if self._udp_sock:
            self._udp_sock.close()
        self._udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def load_config(self, config_data: dict) -> None:
        self.stop_all()
        self.config_data = config_data
        for dev_cfg in config_data.get("devices", []):
            if dev_cfg.get("enabled", False):
                self._start_device(dev_cfg)

    def load_config_file(self, path: str) -> dict:
        with open(path) as f:
            config_data = yaml.safe_load(f) or {}
        self.load_config(config_data)
        return config_data

    # ------------------------------------------------------------------
    # Internals

    def _start_device(self, dev_cfg: dict) -> None:
        from src.controller.device_worker import DeviceWorker
        alias = dev_cfg.get("alias", "unknown")
        worker = DeviceWorker(
            dev_cfg,
            on_joy=self._on_joy,
            on_status=self._on_status,
            on_log=lambda msg: self.event_bus.publish_sync("log", msg),
        )
        worker.start()
        self.workers[alias] = worker

    def _on_joy(self, alias: str, axes: list, buttons: list, is_connected: bool) -> None:
        payload = {"axes": axes, "buttons": buttons, "alias": alias, "connected": is_connected}
        self.event_bus.publish_sync(f"joy/{alias}", payload)
        if self._udp_sock and self._udp_host and self._udp_port:
            try:
                self._udp_sock.sendto(
                    json.dumps(payload).encode(),
                    (self._udp_host, self._udp_port),
                )
            except OSError:
                pass

    def _on_status(self, alias: str, is_connected: bool, name: str) -> None:
        self.event_bus.publish_sync(f"joy/{alias}/connected", is_connected)
        status = "connected" if is_connected else "disconnected"
        self.event_bus.publish_sync("log", f"[InputManager] {name}: {status}")

    # ------------------------------------------------------------------
    # Public API

    def stop_all(self) -> None:
        for worker in self.workers.values():
            worker.stop()
        self.workers.clear()

    def get_status(self) -> list[dict]:
        return [
            {
                "name": dev.get("name", dev.get("alias", "?")),
                "alias": dev.get("alias", "unknown"),
                "enabled": dev.get("enabled", False),
                "connected": (w := self.workers.get(dev.get("alias", ""))) is not None and w.is_connected,
            }
            for dev in self.config_data.get("devices", [])
        ]
