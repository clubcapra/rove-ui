from __future__ import annotations

from dataclasses import dataclass
from socket import AF_INET, SOCK_DGRAM, socket, timeout
from threading import Event, Thread
from typing import Any
from urllib.parse import urljoin, urlparse
from urllib.request import urlopen
import json
import time

from src.controller.event_bus import EventBus


@dataclass(slots=True)
class UDPClientConfig:
	client_type: str
	source: str
	topic: str
	name: str = "udp_client"
	buffer_size: int = 4096
	encoding: str = "utf-8"
	errors: str = "replace"
	parse_json: bool = False
	enabled: bool = True
	last_timestamp: float = 0.0
	base_url: str = ""
	discovery_endpoint: str = "/discover"
	poll_interval_ms: int = 250
	request_timeout_s: float = 1.0
	max_data_age_ms: int = 2000
	topic_prefix: str = "odrive"
	node_ids: tuple[int, ...] = ()
	publish_node_data: bool = True
	publish_field_topics: bool = True


class UDPClient:
	def __init__(self, config: dict[str, Any], event_bus: EventBus | None = None):
		client_type = str(config.get("type", config.get("client_type", "udp"))).strip().lower()
		node_ids = tuple(
			int(node_id)
			for node_id in config.get("node_ids", [])
			if str(node_id).strip()
		)
		self.config = UDPClientConfig(
			client_type=client_type,
			source=str(config.get("source", "udp://0.0.0.0:9999")),
			topic=str(config.get("topic", "udp.data")),
			name=str(config.get("name", "udp_client")),
			buffer_size=int(config.get("buffer_size", 4096)),
			encoding=str(config.get("encoding", "utf-8")),
			errors=str(config.get("errors", "replace")),
			parse_json=bool(config.get("parse_json", False)),
			enabled=bool(config.get("enabled", True)),
			base_url=str(config.get("base_url", config.get("source", ""))).rstrip("/"),
			discovery_endpoint=str(config.get("discovery_endpoint", "/discover")),
			poll_interval_ms=max(50, int(config.get("poll_interval_ms", 250))),
			request_timeout_s=float(config.get("request_timeout_s", 1.0)),
			max_data_age_ms=max(0, int(config.get("max_data_age_ms", 2000))),
			topic_prefix=str(config.get("topic_prefix", "odrive")).strip("."),
			node_ids=node_ids,
			publish_node_data=bool(config.get("publish_node_data", True)),
			publish_field_topics=bool(config.get("publish_field_topics", True)),
		)
		self.event_bus = event_bus or EventBus()
		self._raw_config = config
		self._socket: socket | None = None
		self._stop_event = Event()
		self._thread: Thread | None = None
		self._last_timestamps_by_node: dict[int, int] = {}
		self._discovered_endpoints: dict[int, str] = {}

	def start(self) -> None:
		if not self.config.enabled or self._thread is not None:
			return

		self._stop_event.clear()

		if self.config.client_type == "odrive_http":
			self._thread = Thread(target=self._poll_loop, name=self.config.name, daemon=True)
			self._thread.start()
			self.event_bus.publish_sync(
				"log",
				f"Telemetry client '{self.config.name}' polling {self.config.base_url or self.config.source}",
			)
			return

		if self.config.client_type == "json_http":
			self._thread = Thread(target=self._poll_flat_loop, name=self.config.name, daemon=True)
			self._thread.start()
			self.event_bus.publish_sync(
				"log",
				f"HTTP client '{self.config.name}' polling {self.config.source} -> prefix '{self.config.topic_prefix}'",
			)
			return

		if self.config.client_type == "json_http_flat":
			self._thread = Thread(target=self._poll_flat_simple_loop, name=self.config.name, daemon=True)
			self._thread.start()
			self.event_bus.publish_sync(
				"log",
				f"HTTP flat client '{self.config.name}' polling {self.config.source} -> prefix '{self.config.topic_prefix}'",
			)
			return

		if self.config.client_type == "udp_poll":
			self._thread = Thread(target=self._poll_udp_loop, name=self.config.name, daemon=True)
			self._thread.start()
			self.event_bus.publish_sync(
				"log",
				f"UDP poll client '{self.config.name}' -> {self.config.source} (mirror port)",
			)
			return

		if self.config.client_type == "json_http_named_list":
			self._thread = Thread(target=self._poll_named_list_loop, name=self.config.name, daemon=True)
			self._thread.start()
			self.event_bus.publish_sync(
				"log",
				f"HTTP named-list client '{self.config.name}' polling {self.config.source} -> prefix '{self.config.topic_prefix}'",
			)
			return

		host, port = self._parse_source(self.config.source)
		self._socket = socket(AF_INET, SOCK_DGRAM)
		self._socket.bind((host, port))
		self._socket.settimeout(0.5)

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

		# IF Timestamp > 2s, ignore the datas
		# IF Timestamp is older than last valeur, ignore the datas

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

	def _poll_flat_loop(self) -> None:
		"""Poll a single JSON endpoint that returns {outer_key: {field: value}}.

		Publishes each leaf value as '{topic_prefix}.{outer_key}.{field}'.
		Used for /track_joints and /flipper_joints on the mock server.
		"""
		poll_interval_s = self.config.poll_interval_ms / 1000
		url = self.config.source
		prefix = self.config.topic_prefix or "joints"

		while not self._stop_event.is_set():
			try:
				data = self._http_get_json(url)
			except Exception as exc:
				self.event_bus.publish_sync(
					"log",
					f"HTTP client '{self.config.name}' fetch failed: {exc}",
				)
				time.sleep(poll_interval_s)
				continue

			if not isinstance(data, dict):
				time.sleep(poll_interval_s)
				continue

			for outer_key, fields in data.items():
				if not isinstance(fields, dict):
					continue
				for field_name, value in fields.items():
					self.event_bus.publish_sync(f"{prefix}.{outer_key}.{field_name}", value)

			time.sleep(poll_interval_s)

	def _poll_udp_loop(self) -> None:
		"""Request-response UDP with dynamic port discovery.

		Protocol:
		  1. GET {base_url}/{discovery_endpoint} → extract UDP port from JSON
		  2. Bind locally to that port (mirror port = same number as remote)
		  3. Send b'\\x01' to remote_host:discovered_port
		  4. Receive response and publish to EventBus
		  5. Re-discover on startup and after any failure

		Config keys (in addition to standard ones):
		  base_url               HTTP base URL of the robot API
		  discovery_endpoint     path to call for port discovery (default "/discovery")
		  discovery_port_field   JSON field containing the UDP port   (default "port")
		  rediscovery_interval_s re-discover even if healthy, seconds (default 30)
		  parse_json             decode UDP response as JSON           (default false)
		  publish_field_topics   publish {prefix}.{field} per scalar  (default true)
		"""
		base_url = (self.config.base_url or self.config.source).rstrip("/")
		remote_host = urlparse(base_url).hostname or "127.0.0.1"
		discovery_path = self.config.discovery_endpoint.lstrip("/")
		discovery_url = f"{base_url}/{discovery_path}"
		port_field = str(self._raw_config.get("discovery_port_field", "port"))
		rediscovery_interval_s = float(self._raw_config.get("rediscovery_interval_s", 30))
		poll_interval_s = self.config.poll_interval_ms / 1000

		current_port: int | None = None
		sock: socket | None = None
		last_discovery_t: float = 0.0

		def _discover() -> int | None:
			try:
				data = self._http_get_json(discovery_url)
				return int(data[port_field])
			except Exception as exc:
				self.event_bus.publish_sync(
					"log", f"UDP poll '{self.config.name}' discovery failed: {exc}"
				)
				return None

		def _bind(port: int) -> socket | None:
			s = socket(AF_INET, SOCK_DGRAM)
			try:
				s.bind(("0.0.0.0", port))
				s.settimeout(poll_interval_s)
				self.event_bus.publish_sync(
					"log",
					f"UDP poll '{self.config.name}' bound :{port} -> {remote_host}:{port}",
				)
				return s
			except OSError as exc:
				self.event_bus.publish_sync(
					"log", f"UDP poll '{self.config.name}' bind :{port} failed: {exc}"
				)
				s.close()
				return None

		while not self._stop_event.is_set():
			now = time.monotonic()
			need_rediscovery = (
				current_port is None
				or sock is None
				or (now - last_discovery_t) >= rediscovery_interval_s
			)

			if need_rediscovery:
				new_port = _discover()
				if new_port is None:
					time.sleep(poll_interval_s)
					continue

				if new_port != current_port or sock is None:
					if sock:
						sock.close()
					sock = _bind(new_port)
					if sock is None:
						current_port = None
						time.sleep(poll_interval_s)
						continue
					current_port = new_port

				last_discovery_t = now

			try:
				sock.sendto(b"\x01", (remote_host, current_port))
			except OSError as exc:
				self.event_bus.publish_sync(
					"log", f"UDP poll '{self.config.name}' send failed: {exc}"
				)
				current_port = None
				time.sleep(poll_interval_s)
				continue

			try:
				raw, _addr = sock.recvfrom(self.config.buffer_size)
			except timeout:
				time.sleep(poll_interval_s)
				continue
			except OSError:
				current_port = None
				time.sleep(poll_interval_s)
				continue

			message = self._decode_payload(raw)
			self.event_bus.publish_sync(self.config.topic, message)

			if self.config.publish_field_topics and isinstance(message, dict):
				prefix = self.config.topic_prefix
				for field, value in message.items():
					if isinstance(value, (int, float, str, bool)):
						self.event_bus.publish_sync(
							f"{prefix}.{field}" if prefix else field, value
						)

			time.sleep(poll_interval_s)

		if sock:
			sock.close()

	def _poll_named_list_loop(self) -> None:
		"""Poll an endpoint returning {list_key: [{name_key: X, field: v, ...}]}.

		Publishes {prefix}.{X}.{field} for every scalar field in each item.
		Used for /signals on the mock server.
		"""
		poll_interval_s = self.config.poll_interval_ms / 1000
		url = self.config.source
		prefix = self.config.topic_prefix
		raw = self._raw_config
		list_key = str(raw.get("list_key", "items"))
		name_key = str(raw.get("name_key", "name"))

		while not self._stop_event.is_set():
			try:
				data = self._http_get_json(url)
			except Exception as exc:
				self.event_bus.publish_sync(
					"log",
					f"HTTP named-list client '{self.config.name}' fetch failed: {exc}",
				)
				time.sleep(poll_interval_s)
				continue

			items = data.get(list_key, []) if isinstance(data, dict) else []
			for item in items:
				if not isinstance(item, dict):
					continue
				item_name = str(item.get(name_key, "")).strip()
				if not item_name:
					continue
				for field, value in item.items():
					if field == name_key:
						continue
					if isinstance(value, (int, float, str, bool)):
						topic = f"{prefix}.{item_name}.{field}" if prefix else f"{item_name}.{field}"
						self.event_bus.publish_sync(topic, value)

			time.sleep(poll_interval_s)

	def _poll_flat_simple_loop(self) -> None:
		"""Poll a flat JSON endpoint {field: value} and publish {prefix}.{field}.

		Used for /gnss, /battery and similar single-level endpoints on the mock server.
		"""
		poll_interval_s = self.config.poll_interval_ms / 1000
		url = self.config.source
		prefix = self.config.topic_prefix

		while not self._stop_event.is_set():
			try:
				data = self._http_get_json(url)
			except Exception as exc:
				self.event_bus.publish_sync(
					"log",
					f"HTTP flat client '{self.config.name}' fetch failed: {exc}",
				)
				time.sleep(poll_interval_s)
				continue

			if not isinstance(data, dict):
				time.sleep(poll_interval_s)
				continue

			for field_name, value in data.items():
				if isinstance(value, (int, float, str, bool)):
					topic = f"{prefix}.{field_name}" if prefix else field_name
					self.event_bus.publish_sync(topic, value)

			time.sleep(poll_interval_s)

	def _poll_loop(self) -> None:
		poll_interval_s = self.config.poll_interval_ms / 1000

		while not self._stop_event.is_set():
			try:
				endpoints = self._discover_node_endpoints()
			except Exception as exc:
				self.event_bus.publish_sync(
					"log",
					f"Telemetry '{self.config.name}' discovery failed: {exc}",
				)
				time.sleep(poll_interval_s)
				continue

			if not endpoints:
				self.event_bus.publish_sync(
					"log",
					f"Telemetry '{self.config.name}' discovered no ODrive nodes",
				)
				time.sleep(poll_interval_s)
				continue

			cycle_snapshot: dict[int, dict[str, Any]] = {}
			for node_id, data_endpoint in endpoints.items():
				if self._stop_event.is_set():
					break

				try:
					data = self._http_get_json(data_endpoint)
				except Exception as exc:
					self.event_bus.publish_sync(
						"log",
						f"Telemetry '{self.config.name}' failed to fetch node {node_id}: {exc}",
					)
					continue

				if not isinstance(data, dict):
					continue

				if not self._should_accept_snapshot(node_id, data):
					continue

				cycle_snapshot[node_id] = data
				self._publish_node_snapshot(node_id, data)

			if cycle_snapshot:
				self.event_bus.publish_sync(self.config.topic, cycle_snapshot)

			time.sleep(poll_interval_s)

	def _discover_node_endpoints(self) -> dict[int, str]:
		discover_url = urljoin(f"{self.config.base_url}/", self.config.discovery_endpoint.lstrip("/"))
		payload = self._http_get_json(discover_url)
		sensors = payload.get("sensors", []) if isinstance(payload, dict) else []
		endpoints: dict[int, str] = {}

		for sensor in sensors:
			if not isinstance(sensor, dict):
				continue

			sensor_id = str(sensor.get("id", ""))
			if not sensor_id.startswith("odrive_"):
				continue

			try:
				node_id = int(sensor_id.split("_", 1)[1])
			except ValueError:
				continue

			if self.config.node_ids and node_id not in self.config.node_ids:
				continue

			data_path = sensor.get("endpoints", {}).get("data") or f"/odrive_{node_id}/data"
			endpoints[node_id] = urljoin(f"{self.config.base_url}/", str(data_path).lstrip("/"))

		self._discovered_endpoints = endpoints
		return endpoints

	def _http_get_json(self, url: str) -> Any:
		with urlopen(url, timeout=self.config.request_timeout_s) as response:
			charset = response.headers.get_content_charset() or self.config.encoding
			return json.loads(response.read().decode(charset, errors=self.config.errors))

	def _should_accept_snapshot(self, node_id: int, data: dict[str, Any]) -> bool:
		timestamp_ns = data.get("timestamp_ns")
		if not isinstance(timestamp_ns, int):
			return True

		last_timestamp = self._last_timestamps_by_node.get(node_id, 0)
		if timestamp_ns <= last_timestamp:
			return False

		if self.config.max_data_age_ms > 0:
			age_ns = time.time_ns() - timestamp_ns
			if age_ns > self.config.max_data_age_ms * 1_000_000:
				return False

		self._last_timestamps_by_node[node_id] = timestamp_ns
		self.config.last_timestamp = float(timestamp_ns)
		return True

	def _publish_node_snapshot(self, node_id: int, data: dict[str, Any]) -> None:
		topic_prefix = self.config.topic_prefix or "odrive"

		if self.config.publish_node_data:
			self.event_bus.publish_sync(f"{topic_prefix}.{node_id}", data)

		if not self.config.publish_field_topics:
			return

		for field_name, value in data.items():
			self.event_bus.publish_sync(f"{topic_prefix}.{node_id}.{field_name}", value)

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
