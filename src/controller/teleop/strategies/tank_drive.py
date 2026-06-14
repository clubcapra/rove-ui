"""Tank drive strategy: each joystick controls one track directly.

Left stick Y  → left track velocity  (up = forward)
Right stick Y → right track velocity (up = forward)

Use this when you need fine independent control of each track — e.g.
pivoting in place, climbing over obstacles where the tracks need to move
at different speeds, or recovering from a stuck condition.

Flippers and haptics follow the shared arcade/drive mapping.
"""
from __future__ import annotations

import time

from ..controllers.input_model import ControllerInput, HapticCommand
from ..proto.core import RoveControl_pb2
from .arcade_drive import apply_flippers, drive_haptics, shape_stick
from .base import ControlStrategy


class TankDriveStrategy(ControlStrategy):
    name = "tank_drive"

    def __init__(self) -> None:
        self._last_update: float | None = None

    def on_activate(self, gripper_position: int = 0) -> None:
        self._last_update = None

    def build_message(self, inp: ControllerInput) -> RoveControl_pb2.RoveControl:
        now = time.monotonic()
        self._last_update = now

        msg = RoveControl_pb2.RoveControl()
        msg.timestamp_us = int(now * 1_000_000)

        # Each stick Y drives its own track. Expo shaping for fine control.
        msg.tracks.left_vel = shape_stick(inp.left_y)
        msg.tracks.right_vel = shape_stick(inp.right_y)

        apply_flippers(inp, msg)
        return msg

    def compute_haptics(
        self, inp: ControllerInput, message: RoveControl_pb2.RoveControl
    ) -> HapticCommand | None:
        return drive_haptics(message)
