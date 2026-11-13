"""UDP listener for inbound robot telemetry that drives controller rumble.

The robot publishes its highest current torque reading to a UDP endpoint.
We deserialize each datagram as a ``JointState`` protobuf and expose its
``torque`` field as the latest reading. The control loop reads that value
every tick and translates it into a rumble command the active controller
can play through its SDL2-based haptic backend.

Running the receive loop on a daemon thread keeps the control loop
non-blocking: a missing or delayed torque packet never stalls the
outgoing UDP stream.
"""
from __future__ import annotations

import logging
import socket
import threading
from dataclasses import dataclass

from ..controllers.input_model import HapticCommand
from ..proto.core import JointState_pb2

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class BindEndpoint:
    """Local address to bind the inbound UDP socket to."""
    host: str
    port: int


class UdpTorqueReceiver:
    """Background UDP listener that tracks the latest torque reading.

    Parameters
    ----------
    endpoint:
        Local host/port to bind the socket on.
    torque_max:
        Torque (Nm) that corresponds to full-scale rumble. Readings are
        clamped to ``[0, torque_max]`` and normalized into ``[0, 1]``.
    duration_ms:
        How long each rumble pulse should last. Short pulses are re-armed
        every control-loop tick, so this mostly controls how long rumble
        lingers if packets stop arriving.
    """

    # Treat anything below this normalized value as "no rumble" so the
    # motors don't buzz at idle from sensor noise.
    IDLE_THRESHOLD = 0.05

    def __init__(
        self,
        endpoint: BindEndpoint,
        torque_max: float = 50.0,
        duration_ms: int = 100,
    ) -> None:
        if torque_max <= 0:
            raise ValueError("torque_max must be positive")
        self._endpoint = endpoint
        self._torque_max = torque_max
        self._duration_ms = duration_ms

        self._sock: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        # Single-writer/single-reader on a float is atomic in CPython, but
        # keep a lock for clarity and to stay safe under alternate runtimes.
        self._lock = threading.Lock()
        self._latest_torque = 0.0

    @property
    def endpoint(self) -> BindEndpoint:
        return self._endpoint

    def start(self) -> None:
        if self._thread is not None:
            return
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((self._endpoint.host, self._endpoint.port))
        # Short timeout so the thread can observe the stop flag without
        # relying on a self-pipe or a shutdown packet.
        self._sock.settimeout(0.25)
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="UdpTorqueReceiver",
            daemon=True,
        )
        self._thread.start()
        log.info(
            "Torque receiver listening on %s:%d (torque_max=%.2f Nm)",
            self._endpoint.host,
            self._endpoint.port,
            self._torque_max,
        )

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None
        if self._sock is not None:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None

    def latest_torque(self) -> float:
        """Return the most recent raw torque reading in Nm."""
        with self._lock:
            return self._latest_torque

    def as_haptic_command(self) -> HapticCommand:
        """Translate the latest torque reading into a ``HapticCommand``."""
        torque = self.latest_torque()
        normalized = max(0.0, min(1.0, torque / self._torque_max))
        if normalized < self.IDLE_THRESHOLD:
            return HapticCommand.off()
        # Heavy motor (low freq) takes the brunt — it conveys "load" better
        # than the light motor, which we use for a subtler overlay.
        return HapticCommand(
            low_frequency=normalized,
            high_frequency=normalized * 0.4,
            duration_ms=self._duration_ms,
        )

    # ---- Internals ---------------------------------------------------------

    def _run(self) -> None:
        assert self._sock is not None
        while not self._stop.is_set():
            try:
                payload, _addr = self._sock.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError as exc:
                if self._stop.is_set():
                    break
                log.debug("Torque socket error: %s", exc)
                continue

            try:
                joint = JointState_pb2.JointState()
                joint.ParseFromString(payload)
            except Exception as exc:
                log.debug("Torque payload parse failed: %s", exc)
                continue

            with self._lock:
                self._latest_torque = float(joint.torque)
