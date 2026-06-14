"""Abstract haptic feedback interface.

Both Xbox controllers and the SteamDeck expose rumble, but through very
different backends (XInput / SDL2 rumble vs. SteamDeck's hidraw interface
or SDL2's game-controller API). This module defines the neutral interface;
concrete implementations live under ``haptics/``.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from ..controllers.input_model import HapticCommand


class HapticFeedback(ABC):
    """Common interface for any controller that can rumble."""

    @abstractmethod
    def rumble(self, command: HapticCommand) -> None:
        """Trigger rumble with the given intensities and duration."""

    @abstractmethod
    def stop(self) -> None:
        """Immediately stop any ongoing rumble."""

    def __enter__(self) -> "HapticFeedback":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            self.stop()
        except Exception:
            pass


class NullHaptic(HapticFeedback):
    """No-op haptic backend, used when rumble is unavailable or disabled."""

    def rumble(self, command: HapticCommand) -> None:
        return

    def stop(self) -> None:
        return
