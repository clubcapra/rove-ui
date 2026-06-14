"""VectorNav-driven stuck detection -> haptic feedback.

The teleop process subscribes to rove_sensor_api's vectornav data port,
keeps the latest NED velocity + yaw rate, and compares them against the
operator's commanded track velocities each tick. When the operator is
clearly trying to move (either track commanded above the deadband) but
the IMU sees no translation AND no rotation for a sustained window, the
robot is stuck — and we light up the controller's rumble motor.

Critical: pivot-in-place commands (left = -right) produce zero net
translation but non-zero yaw rate, so we OR the two channels rather
than AND them. Stuck only fires when BOTH translation and yaw are
flat-lined.

This module is self-contained — it hits sensor_api's HTTP `/discover` to
find the vectornav data port, opens its own UDP subscriber, and tears
down cleanly on stop(). One detector per teleop process.
"""
from __future__ import annotations

import collections
import json
import logging
import socket
import struct
import threading
import time
import urllib.error
import urllib.request
from typing import Callable, Optional

from ..controllers.input_model import HapticCommand

log = logging.getLogger(__name__)

# rove_sensor_api wire format — same as elsewhere in the package.
_PROTOCOL_VERSION = 0x01
_MSG_SUBSCRIBE = 0x01
_MSG_UNSUBSCRIBE = 0x02
_MSG_DATA = 0x03
_HEADER_FMT = "<BBH"


def _encode(mt: int, seq: int, payload: Optional[dict]) -> bytes:
    body = json.dumps(payload).encode() if payload is not None else b""
    return struct.pack(_HEADER_FMT, _PROTOCOL_VERSION, mt, seq & 0xFFFF) + body


def _decode(data: bytes) -> tuple[int, Optional[dict]]:
    if len(data) < 4:
        raise ValueError("short")
    ver, mt, _ = struct.unpack(_HEADER_FMT, data[:4])
    if ver != _PROTOCOL_VERSION:
        raise ValueError(f"bad protocol version {ver}")
    return mt, (json.loads(data[4:]) if data[4:] else None)


class StuckDetector:
    """Subscribes to vectornav data, returns a HapticCommand when stuck."""

    # Tuning knobs — exposed as constants so future config can override.
    # Track command magnitude above this counts as "operator wants to move".
    _TRACK_CMD_DEADBAND = 0.10
    # Below these magnitudes the IMU says the robot isn't actually moving.
    _LINEAR_THRESHOLD_MPS = 0.05         # m/s — horizontal speed magnitude
    _ANGULAR_THRESHOLD_RPS = 0.10        # rad/s — yaw rate magnitude (gyro_z)
    # How long the stuck condition must persist before rumble fires. Avoids
    # false alarms during startup latency and the ~200 ms it takes a track
    # to accelerate from rest.
    _STUCK_WINDOW_S = 0.6
    # IMU data must be no older than this for the detector to trust it; an
    # older frame means we lost the link and shouldn't fire stuck-rumble on
    # stale measurements.
    _STALE_AFTER_S = 1.0

    def __init__(
        self,
        sensor_api_base_url: str,
        get_commanded_tracks: Callable[[], tuple[float, float]],
        *,
        discover_timeout_s: float = 3.0,
        subscribe_interval_ms: int = 50,
    ) -> None:
        self._base_url = sensor_api_base_url.rstrip("/")
        self._get_commanded_tracks = get_commanded_tracks
        self._discover_timeout_s = discover_timeout_s
        self._interval_ms = subscribe_interval_ms

        self._enabled = False
        self._sock: Optional[socket.socket] = None
        self._thread: Optional[threading.Thread] = None
        self._stop_evt = threading.Event()

        # Latest IMU readings (lock-guarded so the controller thread can
        # cheaply read them).
        self._lock = threading.Lock()
        self._last_linear_mps: float = 0.0
        self._last_yaw_rate_rps: float = 0.0
        self._last_frame_t: float = 0.0
        # When tracks-commanded but IMU shows no movement, this is the
        # monotonic time the stuck condition started. None = not stuck.
        self._stuck_since: Optional[float] = None

    # --- lifecycle ----------------------------------------------------------

    def set_enabled(self, enabled: bool) -> None:
        """Flip the detector on or off. Idempotent."""
        if enabled and not self._enabled:
            self._enabled = True
            self._start_subscriber()
        elif not enabled and self._enabled:
            self._enabled = False
            self._stop_subscriber()

    def is_enabled(self) -> bool:
        return self._enabled

    def stop(self) -> None:
        self.set_enabled(False)

    # --- haptic read -------------------------------------------------------

    def as_haptic_command(self) -> Optional[HapticCommand]:
        """If currently stuck, return the rumble pattern. None otherwise."""
        if not self._enabled:
            return None
        left, right = self._get_commanded_tracks()
        # Operator must actually want to move for "stuck" to mean anything.
        if max(abs(left), abs(right)) < self._TRACK_CMD_DEADBAND:
            self._stuck_since = None
            return None

        with self._lock:
            linear = self._last_linear_mps
            yaw = self._last_yaw_rate_rps
            last_t = self._last_frame_t

        # If we haven't seen a fresh IMU frame, don't fire — could be a
        # link drop rather than the robot being stuck.
        if last_t == 0.0 or (time.monotonic() - last_t) > self._STALE_AFTER_S:
            self._stuck_since = None
            return None

        moving = (
            linear >= self._LINEAR_THRESHOLD_MPS
            or abs(yaw) >= self._ANGULAR_THRESHOLD_RPS
        )
        now = time.monotonic()
        if moving:
            self._stuck_since = None
            return None

        if self._stuck_since is None:
            self._stuck_since = now
            return None
        if now - self._stuck_since < self._STUCK_WINDOW_S:
            return None

        # Strong, distinctive alarm pattern — separable from torque rumble.
        return HapticCommand(
            low_frequency=0.9,
            high_frequency=0.5,
            duration_ms=150,
        )

    # --- internal subscriber loop ------------------------------------------

    def _discover_vectornav(self) -> Optional[tuple[str, int]]:
        """Return (host, data_port) for vectornav, or None if not present."""
        url = f"{self._base_url}/discover"
        try:
            with urllib.request.urlopen(url, timeout=self._discover_timeout_s) as resp:
                data = json.loads(resp.read())
        except Exception as exc:
            log.warning("StuckDetector: /discover failed (%s)", exc)
            return None
        sensors = data.get("sensors", data) if isinstance(data, dict) else data
        from urllib.parse import urlparse
        host = urlparse(self._base_url).hostname or "127.0.0.1"
        for s in sensors:
            sid = str(s.get("id", "")).lower()
            if sid.startswith("vectornav") or sid.startswith("vn"):
                port = s.get("data_port")
                if port is not None:
                    return host, int(port)
        log.warning("StuckDetector: no vectornav sensor in /discover")
        return None

    def _start_subscriber(self) -> None:
        self._stop_evt.clear()
        self._thread = threading.Thread(
            target=self._run, name="StuckDetector", daemon=True,
        )
        self._thread.start()

    def _stop_subscriber(self) -> None:
        self._stop_evt.set()
        if self._sock is not None:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None
        # Reset latched state so re-enabling starts clean.
        with self._lock:
            self._last_linear_mps = 0.0
            self._last_yaw_rate_rps = 0.0
            self._last_frame_t = 0.0
        self._stuck_since = None

    def _run(self) -> None:
        # Discover + (re-)subscribe in a loop until disabled. This handles
        # sensor_api restarts, vectornav hot-plug, and an initial connect
        # that happens before sensor_api is up.
        last_resubscribe_t = 0.0
        addr: Optional[tuple[str, int]] = None
        while not self._stop_evt.is_set():
            if addr is None:
                addr = self._discover_vectornav()
                if addr is None:
                    # Retry every 5 s while disabled; cheap.
                    if self._stop_evt.wait(5.0):
                        return
                    continue
                try:
                    self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    self._sock.settimeout(0.5)
                    self._sock.sendto(
                        _encode(_MSG_SUBSCRIBE, 0,
                                {"interval_ms": self._interval_ms}),
                        addr,
                    )
                    last_resubscribe_t = time.monotonic()
                    log.info("StuckDetector: subscribed to vectornav at %s:%d",
                             *addr)
                except Exception as exc:
                    log.warning("StuckDetector: subscribe failed: %s", exc)
                    self._sock = None
                    addr = None
                    if self._stop_evt.wait(2.0):
                        return
                    continue

            try:
                data, _ = self._sock.recvfrom(8192)
            except socket.timeout:
                # If we haven't seen a frame in a while, re-SUBSCRIBE
                # (sensor_api may have restarted).
                if time.monotonic() - last_resubscribe_t > 5.0:
                    try:
                        self._sock.sendto(
                            _encode(_MSG_SUBSCRIBE, 0,
                                    {"interval_ms": self._interval_ms}),
                            addr,
                        )
                    except Exception:
                        pass
                    last_resubscribe_t = time.monotonic()
                continue
            except Exception as exc:
                log.warning("StuckDetector: recv failed: %s", exc)
                if self._sock is not None:
                    try: self._sock.close()
                    except Exception: pass
                self._sock = None
                addr = None
                continue

            try:
                mt, body = _decode(data)
            except Exception:
                continue
            if mt != _MSG_DATA or not isinstance(body, dict):
                continue
            # vectornav NED velocity; horizontal magnitude only.
            try:
                vn = float(body.get("vel_north", 0.0))
                ve = float(body.get("vel_east",  0.0))
                gz = float(body.get("gyro_z",    0.0))
            except (TypeError, ValueError):
                continue
            linear = (vn * vn + ve * ve) ** 0.5
            with self._lock:
                self._last_linear_mps = linear
                self._last_yaw_rate_rps = gz
                self._last_frame_t = time.monotonic()
