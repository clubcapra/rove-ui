"""Send MissionBuilder payloads to the control bridge's protobuf front door."""
from __future__ import annotations

import socket
import threading

from google.protobuf.json_format import ParseDict
from src.controller.event_bus import EventBus
from src.proto_gen.proto.Mission_pb2 import Mission, MissionResult


class MissionClient:
    def __init__(self, config: dict, event_bus: EventBus):
        self._config = config
        self._event_bus = event_bus
        self._topic = str(config.get("topic", "mission.send"))

    def start(self):
        self._event_bus.subscribe(self._topic, self._on_event)

    def stop(self):
        self._event_bus.unsubscribe(self._topic, self._on_event)

    def _on_event(self, payload):
        threading.Thread(target=self._send, args=(payload,), daemon=True).start()

    def _send(self, payload):
        destination = (str(self._config["host"]), int(self._config.get("port", 5051)))
        try:
            mission = ParseDict(payload, Mission())
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.settimeout(float(self._config.get("timeout_s", 2.0)))
                sock.connect(destination)
                # Raw protobuf; the bridge does not use HALo's four-byte header.
                sock.send(mission.SerializeToString())
                result = MissionResult.FromString(sock.recv(65536))
            status = MissionResult.Status.Name(result.status)
            self._event_bus.publish_sync("log", f"[Mission] {destination}: {status} {result.detail}")
        except socket.timeout:
            # Do not retry: a lost acknowledgement must not execute a mission twice.
            self._event_bus.publish_sync("log", f"[Mission] No acknowledgement from {destination}; delivery is unknown.")
        except Exception as exc:
            self._event_bus.publish_sync("log", f"[Mission] {destination}: {exc}")
