"""SDL2-backed rumble implementation.

Works for any controller SDL2 recognizes as a game controller, which
includes wired/wireless Xbox pads on Linux, macOS and Windows. pygame's
``joystick`` module wraps SDL2, so we use that for portability.
"""
from __future__ import annotations

import logging

from ..controllers.input_model import HapticCommand
from .base import HapticFeedback

log = logging.getLogger(__name__)


class Sdl2Haptic(HapticFeedback):
    """Rumble via pygame's SDL2 joystick rumble API.

    The underlying SDL call is ``SDL_GameControllerRumble(low, high, duration)``
    which takes 16-bit intensities and a duration in milliseconds. pygame
    accepts floats in ``[0, 1]`` and converts for us.
    """

    def __init__(self, joystick):
        # ``joystick`` is a ``pygame.joystick.Joystick`` instance that has
        # already been ``init()``-ed by the controller class.
        self._joystick = joystick
        # Probe once; some drivers/devices don't implement rumble.
        self._supported = True
        try:
            self._joystick.rumble(0.0, 0.0, 1)
        except Exception as exc:
            log.warning("Rumble not supported on this device: %s", exc)
            self._supported = False

    def rumble(self, command: HapticCommand) -> None:
        if not self._supported:
            return
        low = max(0.0, min(1.0, command.low_frequency))
        high = max(0.0, min(1.0, command.high_frequency))
        try:
            self._joystick.rumble(low, high, max(0, command.duration_ms))
        except Exception as exc:
            log.debug("Rumble call failed: %s", exc)

    def stop(self) -> None:
        if not self._supported:
            return
        try:
            self._joystick.stop_rumble()
        except Exception:
            pass
