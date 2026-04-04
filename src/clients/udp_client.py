from __future__ import annotations

from dataclasses import dataclass
from socket import AF_INET, SOCK_DGRAM, socket, timeout
from threading import Event, Thread
from typing import Any
from urllib.parse import urlparse
import json

from src.controller.event_bus import EventBus


@dataclass(slots=True)
class UDPClientConfig:
	source: str
	topic: str
	name: str = "udp_client"
	buffer_size: int = 4096
	encoding: str = "utf-8"
	errors: str = "replace"
	parse_json: bool = False
	enabled: bool = True


class UDPClient:
	def __init__(self, config: dict[str, Any], event_bus: EventBus | None = None):
		self.config = UDPClientConfig(
			source=str(config.get("source", "udp://0.0.0.0:9999")),
			topic=str(config.get("topic", "udp.data")),
			name=str(config.get("name", "udp_client")),
			buffer_size=int(config.get("buffer_size", 4096)),
			encoding=str(config.get("encoding", "utf-8")),
			errors=str(config.get("errors", "replace")),
			parse_json=bool(config.get("parse_json", False)),
			enabled=bool(config.get("enabled", True)),
		)
		self.event_bus = event_bus or EventBus()
		self._socket: socket | None = None
		self._stop_event = Event()
		self._thread: Thread | None = None

	def start(self) -> None:
		if not self.config.enabled or self._thread is not None:
			return

		host, port = self._parse_source(self.config.source)
		self._socket = socket(AF_INET, SOCK_DGRAM)
		self._socket.bind((host, port))
		self._socket.settimeout(0.5)

		self._stop_event.clear()
		self._thread = Thread(target=self._listen_loop, name=self.config.name, daemon=True)
		self._thread.start()
		self.event_bus.publish_sync(
			"log",
			f"UDP client '{self.config.name}' listening on {host}:{port} -> topic '{self.config.topic}'",
		)

	def stop(self) -> None:
		self._stop_event.set()
		if self._socket is not None:
			try:
				self._socket.close()
			except OSError:
				pass
			self._socket = None

		if self._thread is not None:
			self._thread.join(timeout=1.0)
			self._thread = None

	def _listen_loop(self) -> None:
		assert self._socket is not None

		while not self._stop_event.is_set():
			try:
				payload, address = self._socket.recvfrom(self.config.buffer_size)
			except timeout:
				continue
			except OSError:
				break

			message = self._decode_payload(payload)
			self.event_bus.publish_sync(self.config.topic, message)
			self.event_bus.publish_sync(
				"log",
				f"UDP '{self.config.name}' received packet from {address[0]}:{address[1]} on topic '{self.config.topic}'",
			)

	def _decode_payload(self, payload: bytes) -> Any:
		text = payload.decode(self.config.encoding, errors=self.config.errors)
		if self.config.parse_json:
			try:
				return json.loads(text)
			except json.JSONDecodeError:
				self.event_bus.publish_sync(
					"log",
					f"UDP '{self.config.name}' received invalid JSON payload; forwarding raw text",
				)
		return text

	def _parse_source(self, source: str) -> tuple[str, int]:
		parsed = urlparse(source)
		if parsed.scheme and parsed.scheme != "udp":
			raise ValueError(f"Unsupported UDP source scheme: {parsed.scheme}")

		host = parsed.hostname or "0.0.0.0"
		port = parsed.port or 9999
		return host, port
