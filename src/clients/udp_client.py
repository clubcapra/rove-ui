from __future__ import annotations

import struct
from dataclasses import dataclass
from socket import AF_INET, SO_REUSEADDR, SOCK_DGRAM, SOL_SOCKET, socket, timeout
from threading import Event, Thread
from typing import Any
from urllib.parse import urljoin, urlparse
from urllib.request import urlopen
import json
import time

from src.controller.event_bus import EventBus
from src.clients import proto_decoder

# Subscription packet protocol: | version(1B) | msg_type(1B) | seq_num(2B LE) |
_UDP_VERSION     = 0x01
_MSG_SUBSCRIBE   = 0x01
_MSG_UNSUBSCRIBE = 0x02
_HEADER_SIZE     = 4

_SUBSCRIBE_PACKET   = struct.pack("<BBH", _UDP_VERSION, _MSG_SUBSCRIBE,   0)
_UNSUBSCRIBE_PACKET = struct.pack("<BBH", _UDP_VERSION, _MSG_UNSUBSCRIBE, 0)


def _strip_header(raw: bytes) -> tuple[int, bytes]:
    if len(raw) >= _HEADER_SIZE:
        _, msg_type, _ = struct.unpack("<BBH", raw[:_HEADER_SIZE])
        return msg_type, raw[_HEADER_SIZE:]
    return 0, raw


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
    discovery_sensor_id: str = ""
    poll_interval_ms: int = 250
    request_timeout_s: float = 1.0
    max_data_age_ms: int = 2000
    topic_prefix: str = ""
    node_ids: tuple[int, ...] = ()
    publish_node_data: bool = True
    publish_field_topics: bool = True
    port: int = 0


class UDPClient:
    def __init__(self, config: dict[str, Any], event_bus: EventBus | None = None):
        client_type = str(config.get("type", config.get("client_type", "udp"))).strip().lower()
        node_ids = tuple(
            int(nid) for nid in config.get("node_ids", []) if str(nid).strip()
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
            discovery_sensor_id=str(config.get("discovery_sensor_id", "")),
            poll_interval_ms=max(50, int(config.get("poll_interval_ms", 250))),
            request_timeout_s=float(config.get("request_timeout_s", 1.0)),
            max_data_age_ms=max(0, int(config.get("max_data_age_ms", 2000))),
            topic_prefix=str(config.get("topic_prefix", "")).strip("."),
            node_ids=node_ids,
            publish_node_data=bool(config.get("publish_node_data", True)),
            publish_field_topics=bool(config.get("publish_field_topics", True)),
            port=int(config.get("port", 0)),
        )
        self.event_bus = event_bus or EventBus()
        self._raw_config = config
        self._socket: socket | None = None
        self._sub_sock: socket | None = None
        self._stop_event = Event()
        self._thread: Thread | None = None
        self._last_timestamps_by_node: dict[int, int] = {}

    def start(self) -> None:
        if not self.config.enabled or self._thread is not None:
            return
        self._stop_event.clear()

        if self.config.client_type == "odrive_http":
            self._thread = Thread(target=self._poll_odrive_loop, name=self.config.name, daemon=True)
            self._thread.start()
            self.event_bus.publish_sync("log", f"ODrive HTTP client '{self.config.name}' polling {self.config.base_url}")
            return

        if self.config.client_type == "json_http":
            self._thread = Thread(target=self._poll_nested_loop, name=self.config.name, daemon=True)
            self._thread.start()
            self.event_bus.publish_sync("log", f"HTTP client '{self.config.name}' polling {self.config.source}")
            return

        if self.config.client_type == "json_http_flat":
            self._thread = Thread(target=self._poll_flat_loop, name=self.config.name, daemon=True)
            self._thread.start()
            self.event_bus.publish_sync("log", f"HTTP flat client '{self.config.name}' polling {self.config.source}")
            return

        if self.config.client_type == "json_http_named_list":
            self._thread = Thread(target=self._poll_named_list_loop, name=self.config.name, daemon=True)
            self._thread.start()
            self.event_bus.publish_sync("log", f"HTTP named-list client '{self.config.name}' polling {self.config.source}")
            return

        if self.config.client_type == "udp_poll":
            self._thread = Thread(target=self._subscribe_loop, name=self.config.name, daemon=True)
            self._thread.start()
            self.event_bus.publish_sync("log", f"UDP subscription client '{self.config.name}' -> {self.config.source}")
            return

        # Generic UDP listener (passive)
        host, port = self._parse_source(self.config.source)
        self._socket = socket(AF_INET, SOCK_DGRAM)
        self._socket.bind((host, port))
        self._socket.settimeout(0.5)
        self._thread = Thread(target=self._listen_loop, name=self.config.name, daemon=True)
        self._thread.start()
        self.event_bus.publish_sync("log", f"UDP client '{self.config.name}' listening on {host}:{port}")

    def stop(self) -> None:
        self._stop_event.set()
        for sock in (self._socket, self._sub_sock):
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    pass
        self._socket = None
        self._sub_sock = None
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    # ── Loops ──────────────────────────────────────────────────────────────

    def _listen_loop(self) -> None:
        assert self._socket is not None
        while not self._stop_event.is_set():
            try:
                payload, _ = self._socket.recvfrom(self.config.buffer_size)
            except timeout:
                continue
            except OSError:
                break
            self.event_bus.publish_sync(self.config.topic, self._decode_text(payload))

    def _poll_nested_loop(self) -> None:
        """Poll {outer_key: {field: value}} → publish {prefix}.{outer_key}.{field}."""
        interval = self.config.poll_interval_ms / 1000
        prefix = self.config.topic_prefix or "data"
        while not self._stop_event.is_set():
            try:
                data = self._http_get_json(self.config.source)
            except Exception as exc:
                self.event_bus.publish_sync("log", f"'{self.config.name}' fetch failed: {exc}")
                time.sleep(interval)
                continue
            if isinstance(data, dict):
                for outer, fields in data.items():
                    if isinstance(fields, dict):
                        for field, value in fields.items():
                            self.event_bus.publish_sync(f"{prefix}.{outer}.{field}", value)
            time.sleep(interval)

    def _poll_flat_loop(self) -> None:
        """Poll {field: value} → publish {prefix}.{field}."""
        interval = self.config.poll_interval_ms / 1000
        prefix = self.config.topic_prefix
        while not self._stop_event.is_set():
            try:
                data = self._http_get_json(self.config.source)
            except Exception as exc:
                self.event_bus.publish_sync("log", f"'{self.config.name}' fetch failed: {exc}")
                time.sleep(interval)
                continue
            if isinstance(data, dict):
                for field, value in data.items():
                    if isinstance(value, (int, float, str, bool)):
                        self.event_bus.publish_sync(
                            f"{prefix}.{field}" if prefix else field, value
                        )
            time.sleep(interval)

    def _poll_named_list_loop(self) -> None:
        """Poll {list_key: [{name_key: X, ...}]} → publish {prefix}.{X}.{field}."""
        interval = self.config.poll_interval_ms / 1000
        prefix = self.config.topic_prefix
        list_key = str(self._raw_config.get("list_key", "items"))
        name_key = str(self._raw_config.get("name_key", "name"))
        while not self._stop_event.is_set():
            try:
                data = self._http_get_json(self.config.source)
            except Exception as exc:
                self.event_bus.publish_sync("log", f"'{self.config.name}' fetch failed: {exc}")
                time.sleep(interval)
                continue
            for item in (data.get(list_key, []) if isinstance(data, dict) else []):
                if not isinstance(item, dict):
                    continue
                item_name = str(item.get(name_key, "")).strip()
                if not item_name:
                    continue
                for field, value in item.items():
                    if field != name_key and isinstance(value, (int, float, str, bool)):
                        self.event_bus.publish_sync(
                            f"{prefix}.{item_name}.{field}" if prefix else f"{item_name}.{field}",
                            value,
                        )
            time.sleep(interval)

    def _poll_odrive_loop(self) -> None:
        """Poll ODrive nodes discovered via HTTP, publish per-node and per-field topics."""
        interval = self.config.poll_interval_ms / 1000
        while not self._stop_event.is_set():
            try:
                endpoints = self._discover_odrive_endpoints()
            except Exception as exc:
                self.event_bus.publish_sync("log", f"'{self.config.name}' discovery failed: {exc}")
                time.sleep(interval)
                continue
            if not endpoints:
                time.sleep(interval)
                continue
            snapshot: dict[int, dict] = {}
            for node_id, url in endpoints.items():
                if self._stop_event.is_set():
                    break
                try:
                    data = self._http_get_json(url)
                except Exception:
                    continue
                if not isinstance(data, dict) or not self._accept_odrive_snapshot(node_id, data):
                    continue
                snapshot[node_id] = data
                self._publish_odrive_node(node_id, data)
            if snapshot:
                self.event_bus.publish_sync(self.config.topic, snapshot)
            time.sleep(interval)

    def _subscribe_loop(self) -> None:
        """Subscribe-based UDP receiver for RoveTelemetry protobuf.

        1. GET {base_url}/{discovery_endpoint} → extract data_port
        2. Bind locally to mirror port (same number); fallback to OS-assigned if busy
        3. Send Subscribe packet [0x01 0x01 0x00 0x00]
        4. Receive Data packets, decode as RoveTelemetry protobuf, publish flat topics
        5. Re-subscribe on silence (recv_timeout_s) or heartbeat (rediscovery_interval_s)
        6. Send Unsubscribe on stop

        Config keys:
          base_url               HTTP base URL
          discovery_endpoint     path (default "/discover")
          discovery_port_field   JSON key for UDP port (default "data_port")
          discovery_sensor_id    sensor id to match in /discover response (optional)
          rediscovery_interval_s heartbeat period (default 30)
          recv_timeout_s         silence before re-subscribe (default 2.0)
          topic_prefix           EventBus prefix for flat fields
          publish_field_topics   publish per-field topics (default true)
        """
        base_url = (self.config.base_url or self.config.source).rstrip("/")
        remote_host = urlparse(base_url).hostname or "127.0.0.1"
        discovery_url = f"{base_url}/{self.config.discovery_endpoint.lstrip('/')}"
        port_field = str(self._raw_config.get("discovery_port_field", "data_port"))
        rediscovery_s = float(self._raw_config.get("rediscovery_interval_s", 30))
        recv_timeout_s = float(self._raw_config.get("recv_timeout_s", 2.0))
        _RECV_POLL = 0.5

        current_port: int | None = None
        sock: socket | None = None
        last_sub_t: float = 0.0
        last_data_t: float = 0.0

        def _discover() -> int | None:
            try:
                data = self._http_get_json(discovery_url)
                if "sensors" in data and self.config.discovery_sensor_id:
                    for s in data["sensors"]:
                        if s.get("id") == self.config.discovery_sensor_id:
                            return int(s[port_field])
                    raise KeyError(f"sensor '{self.config.discovery_sensor_id}' not found")
                return int(data[port_field])
            except Exception as exc:
                self.event_bus.publish_sync("log", f"UDP '{self.config.name}' discovery failed: {exc}")
                return None

        def _open_socket(port: int) -> socket:
            s = socket(AF_INET, SOCK_DGRAM)
            s.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
            s.settimeout(_RECV_POLL)
            s.bind(("0.0.0.0", 0))
            local = s.getsockname()[1]
            #self.event_bus.publish_sync("log", f"UDP '{self.config.name}' :{local} -> {remote_host}:{port}")
            self._sub_sock = s
            return s

        def _subscribe() -> bool:
            try:
                sock.sendto(_SUBSCRIBE_PACKET, (remote_host, current_port))
                return True
            except OSError as exc:
                self.event_bus.publish_sync("log", f"UDP '{self.config.name}' subscribe failed: {exc}")
                return False

        proto_type = str(self._raw_config.get("proto_type", "RoveTelemetry"))
        _throttle_s = self.config.poll_interval_ms / 1000.0
        _last_publish_t: float = 0.0
        _first_published = False

        def _publish(raw: bytes) -> None:
            nonlocal _last_publish_t, _first_published
            now = time.monotonic()
            if now - _last_publish_t < _throttle_s:
                return
            _last_publish_t = now

            _, payload = _strip_header(raw)
            try:
                message = json.loads(payload.decode("utf-8", errors="replace"))
            except Exception:
                try:
                    message = proto_decoder.decode(payload, proto_type)
                except Exception:
                    message = self._decode_text(payload)

            self.event_bus.publish_sync(self.config.topic, message)
            if self.config.publish_field_topics and isinstance(message, dict):
                prefix = self.config.topic_prefix
                for field, value in message.items():
                    if isinstance(value, (int, float, str, bool)):
                        self.event_bus.publish_sync(f"{prefix}.{field}" if prefix else field, value)

            if not _first_published:
                _first_published = True
                if isinstance(message, dict):
                    topics = [f"{self.config.topic_prefix}.{f}" if self.config.topic_prefix else f for f in message]
                    self.event_bus.publish_sync("log", f"[UDP:{self.config.name}] topics publiés: {topics}")

        while not self._stop_event.is_set():
            if current_port is None or sock is None:
                if self.config.port:
                    new_port = self.config.port
                else:
                    new_port = _discover()
                    if new_port is None:
                        time.sleep(1.0)
                        continue
                if sock:
                    sock.close()
                sock = _open_socket(new_port)
                current_port = new_port
                last_sub_t = 0.0
                last_data_t = time.monotonic()

            now = time.monotonic()
            need_sub = (
                last_sub_t == 0.0
                or (now - last_sub_t) >= rediscovery_s
                or (now - last_data_t) >= recv_timeout_s
            )
            if need_sub:
                if not _subscribe():
                    sock.close()
                    sock = None
                    self._sub_sock = None
                    current_port = None
                    continue
                last_sub_t = now

            try:
                raw, _ = sock.recvfrom(self.config.buffer_size)
                last_data_t = time.monotonic()
                _publish(raw)
            except timeout:
                pass
            except OSError:
                sock.close()
                sock = None
                self._sub_sock = None
                if not self.config.port:
                    current_port = None

        if sock and current_port:
            try:
                sock.sendto(_UNSUBSCRIBE_PACKET, (remote_host, current_port))
            except OSError:
                pass
            sock.close()
            self._sub_sock = None

    # ── ODrive helpers ──────────────────────────────────────────────────────

    def _discover_odrive_endpoints(self) -> dict[int, str]:
        url = urljoin(f"{self.config.base_url}/", self.config.discovery_endpoint.lstrip("/"))
        payload = self._http_get_json(url)
        sensors = payload.get("sensors", []) if isinstance(payload, dict) else []
        endpoints: dict[int, str] = {}
        for sensor in sensors:
            if not isinstance(sensor, dict):
                continue
            sid = str(sensor.get("id", ""))
            if not sid.startswith("odrive_"):
                continue
            try:
                node_id = int(sid.split("_", 1)[1])
            except ValueError:
                continue
            if self.config.node_ids and node_id not in self.config.node_ids:
                continue
            data_path = sensor.get("endpoints", {}).get("data") or f"/odrive_{node_id}/data"
            endpoints[node_id] = urljoin(f"{self.config.base_url}/", str(data_path).lstrip("/"))
        return endpoints

    def _accept_odrive_snapshot(self, node_id: int, data: dict) -> bool:
        ts = data.get("timestamp_ns")
        if not isinstance(ts, int):
            return True
        if ts <= self._last_timestamps_by_node.get(node_id, 0):
            return False
        if self.config.max_data_age_ms > 0:
            if (time.time_ns() - ts) > self.config.max_data_age_ms * 1_000_000:
                return False
        self._last_timestamps_by_node[node_id] = ts
        return True

    def _publish_odrive_node(self, node_id: int, data: dict) -> None:
        prefix = self.config.topic_prefix or "odrive"
        if self.config.publish_node_data:
            self.event_bus.publish_sync(f"{prefix}.{node_id}", data)
        if self.config.publish_field_topics:
            for field, value in data.items():
                self.event_bus.publish_sync(f"{prefix}.{node_id}.{field}", value)

    # ── Utilities ───────────────────────────────────────────────────────────

    def _http_get_json(self, url: str) -> Any:
        with urlopen(url, timeout=self.config.request_timeout_s) as r:
            charset = r.headers.get_content_charset() or self.config.encoding
            return json.loads(r.read().decode(charset, errors=self.config.errors))

    def _decode_text(self, payload: bytes) -> Any:
        text = payload.decode(self.config.encoding, errors=self.config.errors)
        if self.config.parse_json:
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                pass
        return text

    def _parse_source(self, source: str) -> tuple[str, int]:
        parsed = urlparse(source)
        return parsed.hostname or "0.0.0.0", parsed.port or 9999
