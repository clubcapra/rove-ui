from __future__ import annotations

import os
import threading
import time
from typing import Callable

from evdev import InputDevice, list_devices


class DeviceWorker(threading.Thread):
    """Reads evdev events from one gamepad and fires callbacks with normalized state."""

    def __init__(
        self,
        config: dict,
        on_joy: Callable[[str, list, list, bool], None],
        on_status: Callable[[str, bool, str], None] | None = None,
    ) -> None:
        super().__init__(daemon=True)
        self.config = config
        self._on_joy = on_joy
        self._on_status = on_status
        self.running = True
        self.device: InputDevice | None = None
        self.is_connected = False

        self._axes: list[float] = [0.0] * 12
        self._buttons: list[int] = [0] * 24

        mapping = config.get("mapping", {})
        # evdev_code → joy_index (inverted from YAML)
        self.btn_map = {int(v): int(k) for k, v in mapping.get("buttons", {}).items()}
        self.axis_map = {int(v): int(k) for k, v in mapping.get("axes", {}).items()}

        axis_ranges_cfg = mapping.get("axis_ranges", {})
        self.axis_ranges: dict[int, list] = {int(k): v for k, v in axis_ranges_cfg.items()}

        self.axes_as_buttons = [
            {
                "axis_code": int(e["axis_code"]),
                "neg_button": int(e["neg_button"]),
                "pos_button": int(e["pos_button"]),
                "threshold": float(e.get("threshold", 0.5)),
            }
            for e in mapping.get("axes_as_buttons", [])
        ]

    # ------------------------------------------------------------------

    def _find_device(self) -> InputDevice | None:
        udev_path = self.config.get("udev_path")
        if udev_path and os.path.exists(udev_path):
            try:
                return InputDevice(udev_path)
            except Exception:
                pass

        target_id = self.config.get("id")
        for path in list_devices():
            try:
                dev = InputDevice(path)
                if f"{dev.info.vendor:04x}:{dev.info.product:04x}" == target_id:
                    if 3 in dev.capabilities():  # EV_ABS = real controller
                        return dev
            except Exception:
                continue
        return None

    def _normalize(self, evdev_code: int, raw: int) -> float:
        if evdev_code in self.axis_ranges:
            lo, hi = self.axis_ranges[evdev_code]
            span = hi - lo
            if span == 0:
                return 0.0
            return max(-1.0, min(1.0, 2.0 * (raw - lo) / span - 1.0))
        return max(-1.0, min(1.0, raw / 32767.0))

    def process_event(self, event) -> None:
        if event.type == 3:  # EV_ABS — axes
            if event.code not in self.axis_map:
                return
            val = self._normalize(event.code, event.value)
            if self.config.get("sanitize", False):
                if abs(val) < self.config.get("deadzone", 0.0):
                    val = 0.0
            self._axes[self.axis_map[event.code]] = val
            for e in self.axes_as_buttons:
                if e["axis_code"] != event.code:
                    continue
                t = e["threshold"]
                if e["neg_button"] >= 0:
                    self._buttons[e["neg_button"]] = 1 if val < -t else 0
                if e["pos_button"] >= 0:
                    self._buttons[e["pos_button"]] = 1 if val > t else 0

        elif event.type == 1:  # EV_KEY — buttons
            if event.code in self.btn_map:
                self._buttons[self.btn_map[event.code]] = 1 if event.value > 0 else 0

    # ------------------------------------------------------------------

    def run(self) -> None:
        alias = self.config.get("alias", "unknown")
        name = self.config.get("name", alias)
        last_joy_t = 0.0
        previously_connected = False

        while self.running:
            now = time.time()

            if not self.is_connected:
                self.device = self._find_device()
                if self.device:
                    self.is_connected = True
                    previously_connected = True
                    if self._on_status:
                        self._on_status(alias, True, name)
                else:
                    if previously_connected:
                        previously_connected = False
                        if self._on_status:
                            self._on_status(alias, False, name)
                    self._axes = [0.0] * 12
                    self._buttons = [0] * 24

            if self.is_connected:
                try:
                    while True:
                        event = self.device.read_one()
                        if event is None:
                            break
                        self.process_event(event)
                except (OSError, RuntimeError):
                    self.is_connected = False
                    self.device = None
                    if self._on_status:
                        self._on_status(alias, False, name)

            if now - last_joy_t >= 0.1:
                self._on_joy(alias, list(self._axes), list(self._buttons), self.is_connected)
                last_joy_t = now

            time.sleep(0.01)

    def stop(self) -> None:
        self.running = False
