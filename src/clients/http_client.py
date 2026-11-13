from __future__ import annotations

import json
import threading
from typing import Any
from urllib.request import urlopen, Request
from urllib.error import URLError

from src.controller.event_bus import EventBus


class HttpClient:
    """Subscribes to EventBus topics and fires HTTP requests in a background thread.

    Config format:
        type: "http_action"
        name: "mapping"
        base_url: "http://192.168.2.3"
        actions:
          - topic: "mapping.go"
            method: "POST"       # GET | POST
            endpoint: "/mapping/go"
            body: {}             # optional JSON body for POST
            timeout_s: 5.0
    """

    def __init__(self, config: dict[str, Any], event_bus: EventBus | None = None):
        self._config = config
        self._event_bus = event_bus or EventBus()
        self._base_url = str(config.get("base_url", "")).rstrip("/")
        self._name = str(config.get("name", "http_client"))

    def start(self) -> None:
        for action in self._config.get("actions", []):
            topic    = str(action.get("topic", "")).strip()
            method   = str(action.get("method", "POST")).upper()
            endpoint = str(action.get("endpoint", "")).strip()
            body     = action.get("body", None)
            timeout  = float(action.get("timeout_s", 5.0))

            if not topic or not endpoint:
                continue

            url = self._base_url + endpoint

            trigger      = action.get("trigger_value", None)
            log_response = bool(action.get("log_response", False))

            def _on_event(value, _url=url, _method=method, _body=body, _timeout=timeout,
                          _trigger=trigger, _log_resp=log_response):
                if _trigger is not None and str(value) != str(_trigger):
                    return
                actual_body = self._resolve_body(_body, value)
                threading.Thread(
                    target=self._fire,
                    args=(_url, _method, actual_body, _timeout, _log_resp),
                    daemon=True,
                ).start()

            self._event_bus.subscribe(topic, _on_event)
            self._event_bus.publish_sync(
                "log", f"[HttpClient:{self._name}] {method} {url} ← topic '{topic}'"
            )

    def stop(self) -> None:
        pass

    @staticmethod
    def _resolve_body(body: Any, payload: Any) -> Any:
        """Resolve body template against a payload dict.

        - "$payload"           → forward the whole payload as-is
        - {"key": "$field"}    → replace "$field" with payload["field"]
        - anything else        → return unchanged
        """
        if body == "$payload":
            return payload
        if isinstance(body, dict) and isinstance(payload, dict):
            return {
                k: (payload.get(v[1:], v) if isinstance(v, str) and v.startswith("$") else v)
                for k, v in body.items()
            }
        return body

    def _fire(self, url: str, method: str, body: Any, timeout: float,
              log_response: bool = False) -> None:
        try:
            data = json.dumps(body).encode() if body is not None else b""
            headers = {"Content-Type": "application/json"} if data else {}
            req = Request(url, data=data or None, headers=headers, method=method)
            with urlopen(req, timeout=timeout) as resp:
                status = resp.status
                resp_body = resp.read().decode("utf-8", errors="replace").strip() if log_response else ""
            msg = f"[HttpClient:{self._name}] {method} {url} → {status}"
            if resp_body:
                msg += f"  ← {resp_body[:300]}"
            self._event_bus.publish_sync("log", msg)
        except URLError as exc:
            self._event_bus.publish_sync("log", f"[HttpClient:{self._name}] {method} {url} ERROR: {exc}")
        except Exception as exc:
            self._event_bus.publish_sync("log", f"[HttpClient:{self._name}] {method} {url} ERROR: {exc}")
