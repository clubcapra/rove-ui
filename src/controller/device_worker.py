from __future__ import annotations

import os
import threading
import time
from typing import Callable

from evdev import InputDevice, list_devices


def _axis_bar(val: float) -> str:
    """e.g. val=+0.75 → '────────►        '  val=-1.0 → '◄────────────────'"""
    width = 10
    mid = width // 2
    pos = int(round((val + 1.0) / 2.0 * width))
    pos = max(0, min(width, pos))
    bar = ["-"] * width
    if pos < mid:
        bar[pos] = "◄"
    elif pos > mid:
        bar[pos - 1] = "►"
    else:
        bar[mid] = "│"
    return "[" + "".join(bar) + "]"


class DeviceWorker(threading.Thread):
    """Reads evdev events from one gamepad and fires callbacks with normalized state."""

    def __init__(
        self,
        config: dict,
        on_joy: Callable[[str, list, list, bool], None],
        on_status: Callable[[str, bool, str], None] | None = None,
        on_log: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(daemon=True)
        self.config = config
        self._on_joy = on_joy
        self._on_status = on_status
        self._on_log = on_log
        self.running = True
        self.device: InputDevice | None = None
        self.is_connected = False
        self._alias = config.get("alias", "unknown")

        self._axes: list[float] = [0.0] * 12
        self._buttons: list[int] = [0] * 24
        self._prev_buttons: list[int] = [0] * 24
        # Last axis value that triggered a log — only log on significant change
        self._prev_axes_logged: list[float] = [0.0] * 12

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
            joy_idx = self.axis_map[event.code]
            self._axes[joy_idx] = val
            self._log_axis(joy_idx, val)

            for e in self.axes_as_buttons:
                if e["axis_code"] != event.code:
                    continue
                t = e["threshold"]
                for btn_idx, fired in (
                    (e["neg_button"], val < -t),
                    (e["pos_button"], val > t),
                ):
                    if btn_idx >= 0:
                        new = 1 if fired else 0
                        self._buttons[btn_idx] = new
                        self._log_button(btn_idx, new)

        elif event.type == 1:  # EV_KEY — buttons
            if event.code in self.btn_map:
                joy_idx = self.btn_map[event.code]
                new = 1 if event.value > 0 else 0
                self._buttons[joy_idx] = new
                self._log_button(joy_idx, new)

    def _log_button(self, joy_idx: int, new: int) -> None:
        if not self._on_log or new == self._prev_buttons[joy_idx]:
            return
        self._prev_buttons[joy_idx] = new
        self._on_log(
            f"[{self._alias}] BTN {joy_idx:2d}  {'▼ PRESSED' if new else '▲ released'}"
        )

    def _log_axis(self, joy_idx: int, val: float) -> None:
        if not self._on_log:
            return
        prev = self._prev_axes_logged[joy_idx]
        # Log when crossing ±0.4 from center, or returning near zero
        if (abs(prev) < 0.4 and abs(val) >= 0.4) or (abs(prev) >= 0.4 and abs(val) < 0.1):
            self._prev_axes_logged[joy_idx] = val
            bar = _axis_bar(val)
            self._on_log(f"[{self._alias}] AXIS {joy_idx:2d}  {val:+.2f} {bar}")

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
