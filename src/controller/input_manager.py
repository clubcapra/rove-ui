"""
Input Manager for handling gamepad/joystick inputs.

Processes Joy messages and provides semantic input events based on device mapping.
Handles button presses, axis movements, deadzones, and threshold conversions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Callable, Optional

from src.controller.event_bus import EventBus


class ButtonEvent(IntEnum):
    """Standard button codes matching evdev conventions."""
    BUTTON_A = 304
    BUTTON_B = 305
    BUTTON_X = 307
    BUTTON_Y = 308
    BUTTON_LB = 310
    BUTTON_RB = 311
    BUTTON_VIEW = 314
    BUTTON_MENU = 315
    BUTTON_SUPER = 316
    BUTTON_LS = 317
    BUTTON_RS = 318


@dataclass
class AxisAsButton:
    """Converts an axis to a button event when threshold is crossed."""
    axis_code: int
    neg_button: int  # Button when value < -threshold (-1 to ignore)
    pos_button: int  # Button when value > +threshold (-1 to ignore)
    threshold: float = 0.5
    _state: int = 0  # Track previous state to detect changes


@dataclass
class DeviceMapping:
    """Mapping configuration for a specific input device."""
    name: str
    udev_path: str
    device_id: str
    alias: str
    enabled: bool = True
    deadzone: float = 0.05
    sanitize: bool = True
    
    button_map: dict[int, int] = field(default_factory=dict)  # Joy index -> button code
    axis_map: dict[int, int] = field(default_factory=dict)    # Joy index -> axis code
    axis_ranges: dict[int, tuple[int, int]] = field(default_factory=dict)  # axis code -> [min, max]
    axes_as_buttons: list[AxisAsButton] = field(default_factory=list)


@dataclass
class InputState:
    """Current state of all input values."""
    buttons: dict[int, int] = field(default_factory=dict)  # button -> state (0/1)
    axes: dict[int, float] = field(default_factory=dict)   # axis -> normalized value (-1 to 1)


class InputManager:
    """
    Manages gamepad input processing and distribution.
    
    Usage:
        manager = InputManager(event_bus)
        manager.set_device_mapping(device_config_dict)
        manager.process_joy_message(axes, buttons)
    """
    
    def __init__(self, event_bus: EventBus | None = None):
        self.event_bus = event_bus or EventBus()
        self.devices: dict[str, DeviceMapping] = {}
        self.input_state: dict[str, InputState] = {}
        
    def set_device_mapping(self, device_config: dict[str, Any]) -> None:
        """Load device mapping from configuration dict."""
        mapping = DeviceMapping(
            name=device_config.get("name", "Unknown"),
            udev_path=device_config.get("udev_path", ""),
            device_id=device_config.get("id", ""),
            alias=device_config.get("alias", ""),
            enabled=device_config.get("enabled", True),
            deadzone=float(device_config.get("deadzone", 0.05)),
            sanitize=bool(device_config.get("sanitize", True)),
        )
        
        # Parse button mapping
        buttons_cfg = device_config.get("mapping", {}).get("buttons", {})
        for joy_idx, button_code in buttons_cfg.items():
            mapping.button_map[int(joy_idx)] = button_code
        
        # Parse axis mapping
        axes_cfg = device_config.get("mapping", {}).get("axes", {})
        for joy_idx, axis_code in axes_cfg.items():
            mapping.axis_map[int(joy_idx)] = axis_code
        
        # Parse axis ranges for normalization
        axis_ranges_cfg = device_config.get("mapping", {}).get("axis_ranges", {})
        for axis_code, range_pair in axis_ranges_cfg.items():
            mapping.axis_ranges[int(axis_code)] = tuple(range_pair)
        
        # Parse axes_as_buttons conversions
        axes_as_buttons_cfg = device_config.get("mapping", {}).get("axes_as_buttons", [])
        for aab_cfg in axes_as_buttons_cfg:
            aab = AxisAsButton(
                axis_code=int(aab_cfg.get("axis_code", 0)),
                neg_button=int(aab_cfg.get("neg_button", -1)),
                pos_button=int(aab_cfg.get("pos_button", -1)),
                threshold=float(aab_cfg.get("threshold", 0.5)),
            )
            mapping.axes_as_buttons.append(aab)
        
        self.devices[mapping.alias] = mapping
        self.input_state[mapping.alias] = InputState()
        self.event_bus.publish_sync(
            "log",
            f"Input device mapping loaded: {mapping.name} ({mapping.alias})",
        )
    
    def process_joy_message(
        self,
        device_alias: str,
        axes: list[float],
        buttons: list[int],
    ) -> None:
        """
        Process a Joy message and publish semantic input events.
        
        Publishes:
        - input.{device_alias}.button.{button_code}: 0 or 1
        - input.{device_alias}.axis.{axis_code}: normalized float (-1 to 1)
        - input.{device_alias}.pressed.{button_name}: for button presses
        - input.{device_alias}.released.{button_name}: for button releases
        """
        device = self.devices.get(device_alias)
        if not device or not device.enabled:
            return
        
        state = self.input_state[device_alias]
        prefix = f"input.{device_alias}"
        
        # Process buttons
        for joy_idx, button_state in enumerate(buttons):
            button_code = device.button_map.get(joy_idx)
            if button_code is None:
                continue
            
            prev_state = state.buttons.get(button_code, 0)
            state.buttons[button_code] = button_state
            
            # Publish button state
            self.event_bus.publish_sync(
                f"{prefix}.button.{button_code}",
                button_state,
            )
            
            # Publish press/release events
            if button_state and not prev_state:
                self.event_bus.publish_sync(f"{prefix}.pressed.{button_code}", True)
            elif not button_state and prev_state:
                self.event_bus.publish_sync(f"{prefix}.released.{button_code}", True)
        
        # Process axes
        for joy_idx, raw_value in enumerate(axes):
            axis_code = device.axis_map.get(joy_idx)
            if axis_code is None:
                continue
            
            # Normalize axis value
            normalized = self._normalize_axis(device, axis_code, raw_value)
            
            # Apply deadzone
            if abs(normalized) < device.deadzone:
                normalized = 0.0
            
            prev_value = state.axes.get(axis_code, 0.0)
            state.axes[axis_code] = normalized
            
            # Publish axis value
            self.event_bus.publish_sync(
                f"{prefix}.axis.{axis_code}",
                normalized,
            )
        
        # Process axes_as_buttons conversions
        for aab in device.axes_as_buttons:
            axis_value = state.axes.get(aab.axis_code, 0.0)
            
            # Check negative threshold
            if aab.neg_button >= 0:
                if axis_value < -aab.threshold and aab._state != 1:
                    aab._state = 1
                    self.event_bus.publish_sync(
                        f"{prefix}.pressed.{aab.neg_button}",
                        True,
                    )
                elif axis_value >= -aab.threshold and aab._state == 1:
                    aab._state = 0
                    self.event_bus.publish_sync(
                        f"{prefix}.released.{aab.neg_button}",
                        True,
                    )
            
            # Check positive threshold
            if aab.pos_button >= 0:
                if axis_value > aab.threshold and aab._state != 2:
                    aab._state = 2
                    self.event_bus.publish_sync(
                        f"{prefix}.pressed.{aab.pos_button}",
                        True,
                    )
                elif axis_value <= aab.threshold and aab._state == 2:
                    aab._state = 0
                    self.event_bus.publish_sync(
                        f"{prefix}.released.{aab.pos_button}",
                        True,
                    )
    
    def _normalize_axis(
        self,
        device: DeviceMapping,
        axis_code: int,
        raw_value: float,
    ) -> float:
        """Normalize raw axis value to [-1, 1] range."""
        axis_range = device.axis_ranges.get(axis_code)
        
        if axis_range is None:
            # Default normalization (standard -32767 to 32767)
            return max(-1.0, min(1.0, raw_value / 32767.0))
        
        raw_min, raw_max = axis_range
        
        # Handle single-sided ranges (like triggers 0-1023)
        if raw_min == raw_max:
            return 0.0
        
        # Normalize to [-1, 1]
        normalized = (raw_value - raw_min) / (raw_max - raw_min)
        normalized = normalized * 2.0 - 1.0  # Convert [0, 1] to [-1, 1]
        
        return max(-1.0, min(1.0, normalized))
