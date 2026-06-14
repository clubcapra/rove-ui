"""UDP listener for inbound RoveTelemetry packets.

The on-rover control interface mirrors arm joint state (and, later, the
rest of the platform telemetry) back to the address that most recently
sent it a RoveControl frame. We bind a non-blocking socket on a daemon
thread, decode each datagram into a ``RoveTelemetry`` protobuf, and
expose the latest one through ``latest()``.

A lightweight "subscribe" callback list lets the UI / logger pick up
each frame as it arrives without polling.
"""
from __future__ import annotations

import logging
import socket
import threading
from dataclasses import dataclass
from typing import Callable, Optional

from ..proto.core import RoveTelemetry_pb2

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class BindEndpoint:
    host: str
    port: int


class UdpTelemetryReceiver:
    """Background UDP listener that decodes RoveTelemetry frames."""

    def __init__(self, endpoint: BindEndpoint) -> None:
        self._endpoint = endpoint
        self._sock: Optional[socket.socket] = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._latest: Optional[RoveTelemetry_pb2.RoveTelemetry] = None
        self._packets = 0
        self._subscribers: list[Callable[[RoveTelemetry_pb2.RoveTelemetry], None]] = []

    @property
    def endpoint(self) -> BindEndpoint:
        return self._endpoint

    def subscribe(self, fn: Callable[[RoveTelemetry_pb2.RoveTelemetry], None]) -> None:
        self._subscribers.append(fn)

    def start(self) -> None:
        if self._thread is not None:
            return
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((self._endpoint.host, self._endpoint.port))
        self._sock.settimeout(0.25)
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="UdpTelemetryReceiver",
            daemon=True,
        )
        self._thread.start()
        log.info("Telemetry receiver listening on %s:%d", self._endpoint.host, self._endpoint.port)

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None
        if self._sock is not None:
            try:
                self._sock.close()
            finally:
                self._sock = None

    def latest(self) -> Optional[RoveTelemetry_pb2.RoveTelemetry]:
        with self._lock:
            return self._latest

    def packet_count(self) -> int:
        with self._lock:
            return self._packets

    def _run(self) -> None:
        assert self._sock is not None
        while not self._stop.is_set():
            try:
                data, _addr = self._sock.recvfrom(8192)
            except socket.timeout:
                continue
            except OSError as e:
                if self._stop.is_set():
                    break
                log.debug("Telemetry socket error: %s", e)
                continue
            try:
                t = RoveTelemetry_pb2.RoveTelemetry()
                t.ParseFromString(data)
            except Exception as e:
                log.debug("Telemetry decode failed: %s", e)
                continue
            with self._lock:
                self._latest = t
                self._packets += 1
            for cb in self._subscribers:
                try:
                    cb(t)
                except Exception as e:
                    log.debug("Telemetry subscriber raised: %s", e)
