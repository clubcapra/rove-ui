"""SteamDeck haptic backend.

On Steam Deck, Steam Input normally abstracts the controller so that it
appears as a regular Xbox 360 pad to applications, which means the SDL2
rumble backend Just Works. This class therefore subclasses ``Sdl2Haptic``
but keeps a separate name so the controller wiring stays clear and so
future Deck-specific behavior (trackpad haptics via the Steam Input API
or raw hidraw writes) can be layered in without touching the Xbox path.
"""
from __future__ import annotations

import logging

from ..controllers.input_model import HapticCommand
from .sdl2_haptic import Sdl2Haptic

log = logging.getLogger(__name__)


class SteamDeckHaptic(Sdl2Haptic):
    """Rumble on Steam Deck.

    If you disable Steam Input and talk to the Deck's controller directly
    via hidraw, you'd override ``rumble`` here and write the appropriate
    feature report instead of delegating to SDL2. With Steam Input enabled
    (the default), delegation is all we need.
    """

    def __init__(self, joystick):
        super().__init__(joystick)
        log.info("SteamDeck haptic backend initialized (via SDL2/Steam Input)")

    # Placeholder hook: the Deck supports richer haptics than basic rumble
    # (the trackpads can do high-fidelity haptic clicks). If/when the
    # strategy wants to use them, extend HapticCommand and override here.
    def rumble(self, command: HapticCommand) -> None:
        super().rumble(command)
