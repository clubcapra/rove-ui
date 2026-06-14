"""Xbox controller backend (wired or wireless, via SDL2/pygame).

SDL2 reports standardized axis/button indices for recognized game
controllers, so this implementation uses pygame's higher-level
game-controller abstraction when available, falling back to raw joystick
indices for portability.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Optional

import pygame

from .controller_base import ControllerBase
from .input_model import Button, ControllerInput
from ..haptics.base import HapticFeedback, NullHaptic
from ..haptics.sdl2_haptic import Sdl2Haptic

log = logging.getLogger(__name__)


# After calibration, anything below this on a trigger is treated as 0.
# Kept small: rest is anchored by calibration (axis 8/9 rest at -1.0 on
# Steam Deck), so abs(delta)/span drift at rest is negligible.
_TRIGGER_DEADZONE = 0.02

_BUTTON_MAP = {
    0: Button.A,
    1: Button.B,
    2: Button.X,
    3: Button.Y,
    4: Button.BACK,
    5: Button.GUIDE,
    6: Button.START,
    7: Button.LS,
    8: Button.RS,
    9: Button.LB,
    10: Button.RB,
    11: Button.DPAD_UP,
    12: Button.DPAD_DOWN,
    13: Button.DPAD_LEFT,
    14: Button.DPAD_RIGHT,
}


class XboxController(ControllerBase):
    """Xbox 360 / Xbox One / Xbox Series controller via SDL2."""

    # Axis indices — subclasses override these for device-specific layouts.
    _AXIS_LX, _AXIS_LY = 0, 1
    _AXIS_RX, _AXIS_RY = 2, 3
    _AXIS_LT, _AXIS_RT = 4, 5

    def __init__(self, *args, device_index: int = 0, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._device_index = device_index
        self._joystick: Optional[pygame.joystick.JoystickType] = None
        # Captured on first read so drift or non-standard trigger rest
        # positions (e.g. unmapped joysticks where triggers rest at 0
        # instead of -1) get zeroed out.
        self._axis_rest: dict[int, float] = {}
        # Captured at startup so any button/hat that reads as "pressed"
        # when the operator isn't touching anything gets treated as
        # phantom input and ignored. Critical on Steam Deck via hid-steam,
        # where extra HID fields routinely appear as always-on buttons.
        self._phantom_buttons: set[Button] = set()
        self._phantom_hat: tuple[int, int] = (0, 0)
        self._buttons_calibrated: bool = False

    def _open_device(self) -> None:
        # SDL2 couples the event pump to the video subsystem, so we need
        # ``pygame.display.init()`` even though we never open a window.
        # The ``dummy`` driver gives us a working event loop without
        # requiring X/Wayland, which also keeps this working headless on
        # a Steam Deck session.
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        pygame.display.init()
        pygame.joystick.init()
        count = pygame.joystick.get_count()
        if count == 0:
            raise RuntimeError("No joysticks detected. Is the controller plugged in?")
        if self._device_index >= count:
            raise RuntimeError(
                f"Device index {self._device_index} out of range (found {count})"
            )
        self._joystick = pygame.joystick.Joystick(self._device_index)
        self._joystick.init()
        log.info("Opened Xbox controller: %s", self._joystick.get_name())

        # SDL emits axis-init events asynchronously after Joystick.init().
        # Drain them before the first calibration read so we capture real
        # rest positions instead of the default-0 placeholders. Steam Deck
        # takes longer to deliver initial state than a USB Xbox pad, so
        # err on the generous side.
        settle_deadline = time.monotonic() + 0.5
        while time.monotonic() < settle_deadline:
            pygame.event.pump()
            time.sleep(0.01)

    def _close_device(self) -> None:
        if self._joystick is not None:
            try:
                self._joystick.quit()
            except Exception:
                pass
            self._joystick = None
        pygame.joystick.quit()
        pygame.display.quit()

    def _read_input(self) -> Optional[ControllerInput]:
        if self._joystick is None:
            return None

        # Pump the event queue; required for joystick state to update.
        pygame.event.pump()

        if not self._axis_rest:
            self._calibrate_rest()

        inp = ControllerInput()
        inp.left_x = self._cal_stick(self._AXIS_LX)
        inp.left_y = self._cal_stick(self._AXIS_LY)
        inp.right_x = self._cal_stick(self._AXIS_RX)
        inp.right_y = self._cal_stick(self._AXIS_RY)
        inp.left_trigger = self._cal_trigger(self._AXIS_LT)
        inp.right_trigger = self._cal_trigger(self._AXIS_RT)

        for idx, btn in _BUTTON_MAP.items():
            try:
                if self._joystick.get_button(idx):
                    inp.buttons.add(btn)
            except pygame.error:
                # Button index out of range for this particular pad.
                continue

        # Some drivers report D-pad as a hat instead of buttons.
        hat_x, hat_y = 0, 0
        if self._joystick.get_numhats() > 0:
            hat_x, hat_y = self._joystick.get_hat(0)
            dx = hat_x - self._phantom_hat[0]
            dy = hat_y - self._phantom_hat[1]
            if dx < 0:
                inp.buttons.add(Button.DPAD_LEFT)
            elif dx > 0:
                inp.buttons.add(Button.DPAD_RIGHT)
            if dy > 0:
                inp.buttons.add(Button.DPAD_UP)
            elif dy < 0:
                inp.buttons.add(Button.DPAD_DOWN)

        # Subclasses (SteamDeck) extend inp before phantom filtering, so
        # hand off the raw reading and let this controller's hook finalize.
        self._finalize_input(inp, hat=(hat_x, hat_y))
        return inp

    def _finalize_input(
        self, inp: ControllerInput, hat: tuple[int, int] = (0, 0)
    ) -> None:
        """Capture phantom state on the first call, filter it on every call.

        Any button or hat component that reads as active when the operator
        clearly isn't touching the pad (first read after settle) is recorded
        as phantom and subtracted from every subsequent read. Critical on
        Steam Deck via hid-steam, which exposes extra HID fields as
        permanently-pressed buttons.
        """
        if not self._buttons_calibrated:
            self._phantom_buttons = set(inp.buttons)
            self._phantom_hat = hat
            self._buttons_calibrated = True
            if self._phantom_buttons or self._phantom_hat != (0, 0):
                log.warning(
                    "Phantom input at startup (ignoring): buttons=%s hat=%s",
                    sorted(b.name for b in self._phantom_buttons),
                    self._phantom_hat,
                )
        inp.buttons -= self._phantom_buttons

    def _create_haptic(self) -> HapticFeedback:
        if self._joystick is None:
            return NullHaptic()
        return Sdl2Haptic(self._joystick)

    def _axis(self, idx: int) -> float:
        try:
            return float(self._joystick.get_axis(idx))
        except pygame.error:
            return 0.0

    def _calibrate_rest(self) -> None:
        for idx in (self._AXIS_LX, self._AXIS_LY, self._AXIS_RX, self._AXIS_RY,
                    self._AXIS_LT, self._AXIS_RT):
            self._axis_rest[idx] = self._axis(idx)
        log.info(
            "Axis rest positions: LX=%.2f LY=%.2f RX=%.2f RY=%.2f LT=%.2f RT=%.2f "
            "(buttons=%d, axes=%d, hats=%d)",
            self._axis_rest[self._AXIS_LX], self._axis_rest[self._AXIS_LY],
            self._axis_rest[self._AXIS_RX], self._axis_rest[self._AXIS_RY],
            self._axis_rest[self._AXIS_LT], self._axis_rest[self._AXIS_RT],
            self._joystick.get_numbuttons(),
            self._joystick.get_numaxes(),
            self._joystick.get_numhats(),
        )

    def _cal_stick(self, idx: int) -> float:
        # Zero out rest-position drift. Range stays roughly [-1, 1].
        return self._axis(idx) - self._axis_rest.get(idx, 0.0)

    def _cal_trigger(self, idx: int) -> float:
        # Produce 0.0 at rest, 1.0 at fully pulled.
        # span = 1.0 - rest handles three driver conventions:
        #   rest=-1 → span=2   (raw SDL joystick, e.g. Steam Deck axis 8/9)
        #   rest= 0 → span=1   (Steam Input Xbox emulation, positive polarity)
        # abs(delta) handles negative-going axes (rest=0, axis→-1).
        rest = self._axis_rest.get(idx, 0.0)
        span = 1.0 - rest
        if span <= 0.01:
            return 0.0
        value = min(1.0, abs(self._axis(idx) - rest) / span)
        return 0.0 if value < _TRIGGER_DEADZONE else value
