"""Neutral input snapshot shared across controller backends.

Both the Xbox and SteamDeck controllers populate a ``ControllerInput`` each
frame. Strategies read from this model exclusively, so they never know which
physical device produced the values. This is the contract that keeps the
strategy pattern decoupled from the controller template.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto


class Button(Enum):
    # Face buttons (Xbox naming; SteamDeck maps A/B/X/Y the same way)
    A = auto()
    B = auto()
    X = auto()
    Y = auto()
    # Shoulders
    LB = auto()
    RB = auto()
    # Sticks (clicked in)
    LS = auto()
    RS = auto()
    # Center cluster
    BACK = auto()      # "View" / "..." on Xbox, "Select" on SteamDeck
    START = auto()     # "Menu" / "≡"
    GUIDE = auto()     # Xbox / Steam logo
    # D-pad
    DPAD_UP = auto()
    DPAD_DOWN = auto()
    DPAD_LEFT = auto()
    DPAD_RIGHT = auto()
    # SteamDeck-only extras (always False on Xbox)
    L4 = auto()
    L5 = auto()
    R4 = auto()
    R5 = auto()


_MODIFIER_BUTTONS = {Button.L4, Button.R4, Button.L5, Button.R5}


@dataclass
class ControllerInput:
    """Normalized snapshot of controller state for one frame.

    Axes are floats in ``[-1.0, 1.0]``. Triggers are floats in ``[0.0, 1.0]``.
    Buttons live in the ``buttons`` set: present means pressed.
    """
    # Left stick
    left_x: float = 0.0
    left_y: float = 0.0
    # Right stick
    right_x: float = 0.0
    right_y: float = 0.0
    # Triggers (analog, 0..1)
    left_trigger: float = 0.0
    right_trigger: float = 0.0
    # Pressed buttons
    buttons: set[Button] = field(default_factory=set)

    def is_pressed(self, button: Button) -> bool:
        return button in self.buttons

    def is_idle(
        self,
        stick_deadzone: float = 0.08,
        trigger_deadzone: float = 0.02,
    ) -> bool:
        """True when nothing the operator could do is above the noise floor.

        Used to suppress UDP sends: the robot is push-based, so emitting a
        frame with no commanded motion is both pointless and potentially
        misleading (drift values inside the deadzone would still be sent).

        The back-grip buttons (L4/R4/L5/R5) are modifiers, not commands —
        they only select *which* flipper the DPAD moves. Holding a grip
        alone issues no motion, so it doesn't count toward non-idle.
        """
        if self.buttons - _MODIFIER_BUTTONS:
            return False
        if abs(self.left_x) > stick_deadzone or abs(self.left_y) > stick_deadzone:
            return False
        if abs(self.right_x) > stick_deadzone or abs(self.right_y) > stick_deadzone:
            return False
        if self.left_trigger > trigger_deadzone or self.right_trigger > trigger_deadzone:
            return False
        return True

    def copy(self) -> "ControllerInput":
        return ControllerInput(
            left_x=self.left_x,
            left_y=self.left_y,
            right_x=self.right_x,
            right_y=self.right_y,
            left_trigger=self.left_trigger,
            right_trigger=self.right_trigger,
            buttons=set(self.buttons),
        )


@dataclass(frozen=True)
class HapticCommand:
    """Rumble command returned by a strategy.

    ``low_frequency`` is the heavy/left motor, ``high_frequency`` the
    light/right motor. Both in ``[0.0, 1.0]``. ``duration_ms`` is how long
    the controller should keep vibrating before auto-stopping.
    """
    low_frequency: float = 0.0
    high_frequency: float = 0.0
    duration_ms: int = 100

    @classmethod
    def off(cls) -> "HapticCommand":
        return cls(0.0, 0.0, 0)
