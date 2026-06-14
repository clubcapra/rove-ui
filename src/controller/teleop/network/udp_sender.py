"""UDP transport for protobuf messages."""
from __future__ import annotations

import logging
import socket
from dataclasses import dataclass

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class UdpEndpoint:
    """Destination host/port for outgoing telemetry."""
    host: str
    port: int


class UdpSender:
    """Thin wrapper around a non-blocking UDP socket.

    Serializes any protobuf message that has a ``SerializeToString`` method
    and ships it to the configured endpoint. Sending is best-effort; a
    failed send is logged but never raised, because a control loop should
    never die because the network hiccuped for one frame.
    """

    def __init__(self, endpoint: UdpEndpoint):
        self._endpoint = endpoint
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Non-blocking: if the OS buffer is full we'd rather drop a frame
        # than stall the control loop.
        self._sock.setblocking(False)

    @property
    def endpoint(self) -> UdpEndpoint:
        return self._endpoint

    def send(self, message) -> bool:
        """Serialize and send a protobuf message. Returns True on success."""
        try:
            payload = message.SerializeToString()
        except Exception as exc:  # pragma: no cover - programmer error
            log.error("Failed to serialize protobuf: %s", exc)
            return False

        try:
            self._sock.sendto(payload, (self._endpoint.host, self._endpoint.port))
            return True
        except BlockingIOError:
            log.debug("UDP send would block, dropping frame")
            return False
        except OSError as exc:
            log.warning("UDP send failed: %s", exc)
            return False

    def close(self) -> None:
        self._sock.close()

    def __enter__(self) -> "UdpSender":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
