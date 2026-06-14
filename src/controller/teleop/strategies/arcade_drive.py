"""Arcade drive strategy: one stick steers, throttle on the same stick.

Left joystick: Y = throttle, X = steer → mixed into left/right track velocities.
Back grip pads select which flipper; DPAD up/down steps it.
With no grip held, DPAD moves all four flippers together.

Grip → flipper:
    L4 (top-left)     → front-left
    R4 (top-right)    → front-right
    L5 (bottom-left)  → rear-left
    R5 (bottom-right) → rear-right
"""
from __future__ import annotations

import time

from ..controllers.input_model import Button, ControllerInput, HapticCommand
from ..proto.core import RoveControl_pb2
from .base import ControlStrategy


STICK_DEADZONE = 0.08
# Expo exponent applied to stick input: >1 flattens response near centre
# so small stick deflections give fine control. 2.0 = quadratic feel.
TRACKS_EXPO = 2.0


def _scaled_dz(value: float, dz: float = STICK_DEADZONE) -> float:
    """Deadzone with output rescaled to [0, 1] past the threshold."""
    a = abs(value)
    if a < dz:
        return 0.0
    sign = 1.0 if value >= 0 else -1.0
    return sign * (a - dz) / (1.0 - dz)


def _expo(value: float, exponent: float = TRACKS_EXPO) -> float:
    if value == 0.0:
        return 0.0
    sign = 1.0 if value >= 0 else -1.0
    return sign * (abs(value) ** exponent)


def shape_stick(value: float) -> float:
    """Deadzone + symmetric expo curve; output in [-1, 1]."""
    return _expo(_scaled_dz(value))


def _clamp(v: float) -> float:
    return max(-1.0, min(1.0, v))


def apply_flippers(inp: ControllerInput, msg) -> None:
    """Shared flipper mapping: grip selects, DPAD steps; no grip = all four."""
    dpad_dir = (
        1 if inp.is_pressed(Button.DPAD_UP)
        else -1 if inp.is_pressed(Button.DPAD_DOWN)
        else 0
    )
    l4 = inp.is_pressed(Button.L4)
    r4 = inp.is_pressed(Button.R4)
    l5 = inp.is_pressed(Button.L5)
    r5 = inp.is_pressed(Button.R5)
    none_selected = not (l4 or r4 or l5 or r5)
    msg.flippers.fl = dpad_dir if (l4 or none_selected) else 0
    msg.flippers.fr = dpad_dir if (r4 or none_selected) else 0
    msg.flippers.rl = dpad_dir if (l5 or none_selected) else 0
    msg.flippers.rr = dpad_dir if (r5 or none_selected) else 0


def drive_haptics(message) -> HapticCommand | None:
    speed = max(abs(message.tracks.left_vel), abs(message.tracks.right_vel))
    if speed < 0.1:
        return None
    return HapticCommand(
        low_frequency=speed * 0.4,
        high_frequency=speed * 0.2,
        duration_ms=80,
    )


class ArcadeDriveStrategy(ControlStrategy):
    name = "arcade_drive"

    def __init__(self) -> None:
        self._last_update: float | None = None

    def on_activate(self, gripper_position: int = 0) -> None:
        self._last_update = None

    def build_message(self, inp: ControllerInput) -> RoveControl_pb2.RoveControl:
        now = time.monotonic()
        self._last_update = now

        msg = RoveControl_pb2.RoveControl()
        msg.timestamp_us = int(now * 1_000_000)

        # Arcade drive: left stick Y = throttle (up = +1 on Deck), X = steer.
        throttle = shape_stick(inp.left_y)
        steer = -shape_stick(inp.left_x)
        msg.tracks.left_vel = _clamp(throttle + steer)
        msg.tracks.right_vel = _clamp(throttle - steer)

        apply_flippers(inp, msg)
        return msg

    def compute_haptics(
        self, inp: ControllerInput, message: RoveControl_pb2.RoveControl
    ) -> HapticCommand | None:
        return drive_haptics(message)


# Legacy aliases kept for external callers.
BaseControlStrategy = ArcadeDriveStrategy
