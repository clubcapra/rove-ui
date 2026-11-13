"""Arm control strategy: 6-DOF Ovis arm as Cartesian twist.

Layout:
    Right stick X:       arm position Y  (sideways)
    Right stick Y:       arm position X  (push forward = up on stick = +X)
    DPAD up / down:      arm position Z  (up on dpad = +Z world)
    Left stick X:        arm orientation yaw  (twist left/right)
    Left stick Y:        arm orientation pitch  (up = +pitch)
    DPAD left / right:   arm orientation roll
    RB (right bumper):   toggle gripper open / closed

Stick shaping (deadzone + symmetric expo) is shared with the tracks
strategies via ``shape_stick`` so the feel is identical across modes.

Tracks are zeroed — arm mode does not drive the rover.
"""
from __future__ import annotations

import time

from ..controllers.input_model import Button, ControllerInput, HapticCommand
from ..proto.core import RoveControl_pb2
from .arcade_drive import STICK_DEADZONE, _scaled_dz
from .base import ControlStrategy

# Expo exponent for arm sticks. Higher → flatter near centre, more
# precise small motions, sharper rise near full deflection. The tracks
# use 2.0; the arm wants more precision because the IK solver amplifies
# small input errors into visible end-effector drift.
OVIS_EXPO = 2.5

# Full-stick output cap — avoids saturating the IK velocity envelope.
# After expo shaping produces a value in [-1, 1], this scales it down
# so the integrator never asks the solver for a step it can't take.
OVIS_AXIS_LIMIT = 0.6


def _clamp(v: float) -> float:
    return max(-1.0, min(1.0, v))


def _expo(value: float, exponent: float = OVIS_EXPO) -> float:
    """Symmetric ``|x|^exponent`` with sign preserved. Output in [-1, 1]."""
    if value == 0.0:
        return 0.0
    sign = 1.0 if value >= 0 else -1.0
    return sign * (abs(value) ** exponent)


def _ovis_axis(raw: float) -> float:
    """Deadzone + arm-tuned expo + IK saturation cap.

    Re-uses ``_scaled_dz`` from the tracks module so the deadzone
    threshold stays in one place. The expo exponent is local — tracks
    and arm have different ergonomics and shouldn't co-tune.
    """
    return _clamp(_expo(_scaled_dz(raw, STICK_DEADZONE)) * OVIS_AXIS_LIMIT)


class ArmControlStrategy(ControlStrategy):
    name = "arm_control"
    manages_gripper = True

    def __init__(self) -> None:
        self._last_update: float | None = None
        self._gripper_closed = False
        self._rb_was_pressed = False

    def on_activate(self, gripper_position: int = 0) -> None:
        # Signature mirrors the base class — ControllerBase passes the
        # latched gripper value as a keyword arg, so refusing it raises
        # TypeError inside set_strategy(), which swallows the swap, which
        # makes the UI's strategy buttons look frozen on whatever was
        # selected last. Seed from the latch so re-activating arm mode
        # doesn't snap the gripper open after the operator left it closed.
        self._last_update = None
        self._gripper_closed = gripper_position >= 128
        self._rb_was_pressed = False

    def build_message(self, inp: ControllerInput) -> RoveControl_pb2.RoveControl:
        now = time.monotonic()
        self._last_update = now

        msg = RoveControl_pb2.RoveControl()
        msg.timestamp_us = int(now * 1_000_000)

        # Tracks zeroed — arm mode only.
        msg.tracks.left_vel = 0.0
        msg.tracks.right_vel = 0.0

        # Arm position: right stick swapped vs. world XY so the operator's
        # "push forward" maps to +X (away from the rover) and "left/right"
        # maps to ±Y. Z is on the DPAD up/down.
        msg.ovis.position.x = _ovis_axis(inp.right_y)
        msg.ovis.position.y = _ovis_axis(inp.right_x)
        z = (
            (1.0 if inp.is_pressed(Button.DPAD_UP) else 0.0)
            - (1.0 if inp.is_pressed(Button.DPAD_DOWN) else 0.0)
        )
        msg.ovis.position.z = z * OVIS_AXIS_LIMIT

        # Arm orientation: left stick X=yaw, Y=pitch (inverted);
        # DPAD left/right = roll.
        msg.ovis.orientation.yaw = _ovis_axis(-inp.left_x)
        msg.ovis.orientation.pitch = _ovis_axis(-inp.left_y)
        roll = (
            (1.0 if inp.is_pressed(Button.DPAD_RIGHT) else 0.0)
            - (1.0 if inp.is_pressed(Button.DPAD_LEFT) else 0.0)
        )
        msg.ovis.orientation.roll = roll * OVIS_AXIS_LIMIT

        # Gripper: edge-triggered toggle on RB.
        rb = inp.is_pressed(Button.RB)
        if rb and not self._rb_was_pressed:
            self._gripper_closed = not self._gripper_closed
        self._rb_was_pressed = rb
        msg.gripper.position = 255 if self._gripper_closed else 0

        return msg

    def compute_haptics(
        self, inp: ControllerInput, message: RoveControl_pb2.RoveControl
    ) -> HapticCommand | None:
        arm_active = (
            abs(message.ovis.position.x) > 0.05
            or abs(message.ovis.position.y) > 0.05
            or abs(message.ovis.position.z) > 0.05
            or abs(message.ovis.orientation.yaw) > 0.05
            or abs(message.ovis.orientation.pitch) > 0.05
            or abs(message.ovis.orientation.roll) > 0.05
        )
        if not arm_active:
            return None
        return HapticCommand(
            low_frequency=0.0,
            high_frequency=0.15,
            duration_ms=80,
        )


# Alias for callers still using the old class name.
ArcadeArmStrategy = ArmControlStrategy
