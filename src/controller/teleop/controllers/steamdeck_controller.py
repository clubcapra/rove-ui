"""SteamDeck controller backend.

With Steam Input running (the default on SteamOS), the Deck's controls
appear to applications as an Xbox 360 pad. That means this class shares
most of its behavior with ``XboxController`` and only overrides the bits
that differ:

* Name detection, so we know we're actually on a Deck
* Extra back-grip buttons (L4/L5/R4/R5), which Steam Input surfaces as
  additional buttons when you bind them in the Steam controller profile
* Stick deadzone, which is larger on the Deck to tolerate drift
* The haptic backend, which goes through ``SteamDeckHaptic``

If you're running *without* Steam Input (bare SteamOS desktop, Deck in
"Lizard mode" or kernel hidraw access), swap ``_read_input`` for an
``evdev``/``hidraw`` implementation. The template method in the base
class stays the same either way — that's the whole point.
"""
from __future__ import annotations

import logging
from typing import Optional

from .input_model import Button, ControllerInput
from .xbox_controller import XboxController
from ..haptics.base import HapticFeedback, NullHaptic
from ..haptics.steamdeck_haptic import SteamDeckHaptic

log = logging.getLogger(__name__)

# Steam Input on the Deck exposes extra buttons beyond the standard Xbox
# map: the DPAD lands at 16–19 (it is neither on 11–14 nor on a hat) and
# the back grip paddles L4/R4/L5/R5 land at 20–23. Users can remap these
# in Steam, so treat the values as defaults for the stock profile.
_EXTRA_BUTTON_MAP = {
    16: Button.DPAD_UP,
    17: Button.DPAD_DOWN,
    18: Button.DPAD_LEFT,
    19: Button.DPAD_RIGHT,
    20: Button.L4,
    21: Button.R4,
    22: Button.L5,
    23: Button.R5,
}


class SteamDeckController(XboxController):
    """SteamDeck controller via Steam Input (SDL2)."""

    # Raw joystick axes on the Steam Deck differ from the Xbox SDL mapping.
    # Confirmed via --probe: R2=axis8 (rest -1→+1), L2=axis9 (rest -1→+1).
    _AXIS_LT, _AXIS_RT = 9, 8

    def _open_device(self) -> None:
        super()._open_device()
        if self._joystick is None:
            return
        name = self._joystick.get_name().lower()
        if "steam" not in name and "deck" not in name:
            log.warning(
                "Opened device name %r does not look like a Steam Deck; "
                "SteamDeckController will still work but you may be on a "
                "regular Xbox pad.",
                self._joystick.get_name(),
            )

    def _read_input(self) -> Optional[ControllerInput]:
        inp = super()._read_input()
        if inp is None or self._joystick is None:
            return inp

        # Apply larger stick deadzone for Steam Deck to tolerate drift.
        _STEAMDECK_STICK_DEADZONE = 0.15
        if abs(inp.left_x) < _STEAMDECK_STICK_DEADZONE:
            inp.left_x = 0.0
        if abs(inp.left_y) < _STEAMDECK_STICK_DEADZONE:
            inp.left_y = 0.0
        if abs(inp.right_x) < _STEAMDECK_STICK_DEADZONE:
            inp.right_x = 0.0
        if abs(inp.right_y) < _STEAMDECK_STICK_DEADZONE:
            inp.right_y = 0.0

        # Layer the grip-button mapping on top of the Xbox base.
        for idx, btn in _EXTRA_BUTTON_MAP.items():
            try:
                if self._joystick.get_button(idx):
                    inp.buttons.add(btn)
            except Exception:
                # Index doesn't exist on this mapping — ignore.
                continue

        # Re-apply the phantom filter since we added extras after the base
        # class already filtered.
        inp.buttons -= self._phantom_buttons
        return inp

    def _create_haptic(self) -> HapticFeedback:
        if self._joystick is None:
            return NullHaptic()
        return SteamDeckHaptic(self._joystick)
