from __future__ import annotations

import json
import threading
from datetime import datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from google.protobuf.json_format import MessageToDict
from google.protobuf.message import DecodeError, Message

from src.controller.event_bus import EventBus
from src.proto_gen.proto import Recording_pb2


class RecordingClient:
    """Starts / stops a sensor recording session on the robot via REST.

    Config format:
        name: "recording"
        start_url: "http://<host>/recording/start"
        stop_url:  "http://<host>/recording/stop"
        start_topic:  "recording.start"     # EventBus topic that triggers start
        stop_topic:   "recording.stop"      # EventBus topic that triggers stop
        status_topic: "recording.status"    # published: PENDING | ACTIVE | PARTIAL | STOPPED | ERROR
        config_profile_id: "perception_hd_30fps"
        sensor_ids: ["cam_front_center", ...]
        session_metadata: {"environment": "...", "operator": "..."}
        stop_reason: "run_completed"
        timeout_s: 5.0

    Results and errors are written to the "log" topic (console).
    Responses may be JSON or protobuf (proto/Recording.proto); both are
    normalised to the same dict shape (proto3 JSON mapping).
    """

    def __init__(self, config: dict[str, Any], event_bus: EventBus | None = None):
        self._config = config
        self._event_bus = event_bus or EventBus()
        self._name = str(config.get("name", "recording"))
        self._start_url = str(config.get("start_url", "")).strip()
        self._stop_url = str(config.get("stop_url", "")).strip()
        self._start_topic = str(config.get("start_topic", "recording.start"))
        self._stop_topic = str(config.get("stop_topic", "recording.stop"))
        self._status_topic = str(config.get("status_topic", "recording.status"))
        self._timeout = float(config.get("timeout_s", 5.0))
        self._session_id: str | None = None
        self._busy = threading.Lock()

    def start(self) -> None:
        self._event_bus.subscribe(self._start_topic, self._on_start)
        self._event_bus.subscribe(self._stop_topic, self._on_stop)
        self._log(f"start ← '{self._start_topic}'  stop ← '{self._stop_topic}'")

    def stop(self) -> None:
        self._event_bus.unsubscribe(self._start_topic, self._on_start)
        self._event_bus.unsubscribe(self._stop_topic, self._on_stop)

    # ── EventBus handlers ────────────────────────────────────────────────

    def _on_start(self, *_args) -> None:
        threading.Thread(target=self._do_start, daemon=True).start()

    def _on_stop(self, *_args) -> None:
        threading.Thread(target=self._do_stop, daemon=True).start()

    # ── Requests ─────────────────────────────────────────────────────────

    def _do_start(self) -> None:
        if not self._busy.acquire(blocking=False):
            self._log("WARN: requête déjà en cours, clic ignoré")
            return
        try:
            if self._session_id is not None:
                self._log(f"WARN: enregistrement déjà actif ({self._session_id}), START ignoré")
                return
            if not self._check_url(self._start_url, "start_url"):
                return

            session_id = datetime.now().strftime("session_%Y%m%d_%H%M%S")
            body = {
                "session_id": session_id,
                "config_profile_id": self._config.get("config_profile_id", ""),
                "target_sensors": {"sensor_ids": list(self._config.get("sensor_ids", []))},
                "session_metadata": dict(self._config.get("session_metadata", {})),
            }
            self._set_status("PENDING")
            self._log(f"START {session_id} → POST {self._start_url}")

            resp = self._post(self._start_url, body, Recording_pb2.StartRecordingResponse)
            if resp is None:
                self._set_status("ERROR")
                return

            status = resp.get("status")
            if status != "STATUS_ACTIVE":
                self._log(f"ERROR: START refusé — status={status!r}  réponse={resp}")
                self._set_status("ERROR")
                return

            self._session_id = resp.get("session_id") or session_id
            results = resp.get("sensor_results", [])
            failed = [r for r in results if not r.get("success")]
            for r in results:
                ok = "OK  " if r.get("success") else "FAIL"
                self._log(f"  {ok} {r.get('sensor_id')} ({r.get('sensor_type')})")

            if failed:
                ids = ", ".join(str(r.get("sensor_id")) for r in failed)
                self._log(f"WARN: REC actif {self._session_id} mais capteur(s) en échec: {ids}")
                self._set_status("PARTIAL")
            else:
                self._log(f"REC ACTIF {self._session_id} — {len(results)} capteur(s) "
                          f"depuis {resp.get('started_at', '?')}")
                self._set_status("ACTIVE")
        finally:
            self._busy.release()

    def _do_stop(self) -> None:
        if not self._busy.acquire(blocking=False):
            self._log("WARN: requête déjà en cours, clic ignoré")
            return
        try:
            if self._session_id is None:
                self._log("WARN: aucun enregistrement actif, STOP ignoré")
                return
            if not self._check_url(self._stop_url, "stop_url"):
                return

            body = {
                "session_id": self._session_id,
                "reason": self._config.get("stop_reason", "run_completed"),
            }
            self._log(f"STOP {self._session_id} → POST {self._stop_url}")

            resp = self._post(self._stop_url, body, Recording_pb2.StopRecordingResponse)
            if resp is None:
                # Keep the session id so STOP can be retried.
                self._set_status("ERROR")
                return

            status = resp.get("status")
            if status != "STATUS_STOPPED":
                self._log(f"ERROR: STOP refusé — status={status!r}  réponse={resp}")
                self._set_status("ERROR")
                return

            try:
                duration = f"{int(resp.get('total_duration_ms', 0)) / 1000:.1f}s"
            except (TypeError, ValueError):
                duration = "?"
            self._log(f"REC ARRÊTÉ {self._session_id} — durée {duration}")
            for cam in resp.get("camera_artifacts", []):
                self._log(f"  CAM   {cam.get('sensor_id')}: {cam.get('total_frames_captured')} frames, "
                          f"{cam.get('dropped_frames')} perdues, {cam.get('average_fps')} fps "
                          f"→ {cam.get('video_uri')}")
            for lid in resp.get("lidar_artifacts", []):
                self._log(f"  LIDAR {lid.get('sensor_id')}: {lid.get('total_sweeps_captured')} sweeps, "
                          f"{lid.get('total_points_recorded')} pts → {lid.get('pcd_uri')}")

            self._session_id = None
            self._set_status("STOPPED")
        finally:
            self._busy.release()

    def _post(self, url: str, body: dict, resp_cls: type[Message]) -> dict | None:
        """POST JSON and return the parsed response, or None (error logged)."""
        try:
            req = Request(
                url,
                data=json.dumps(body).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urlopen(req, timeout=self._timeout) as resp:
                content_type = resp.headers.get("Content-Type", "")
                raw = resp.read()
            return self._decode(raw, content_type, resp_cls)
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace").strip()[:300]
            self._log(f"ERROR: HTTP {exc.code} {exc.reason} — {detail}")
        except URLError as exc:
            self._log(f"ERROR: robot injoignable ({exc.reason})")
        except (json.JSONDecodeError, DecodeError):
            self._log("ERROR: réponse illisible (ni JSON ni protobuf valide)")
        except Exception as exc:
            self._log(f"ERROR: {exc}")
        return None

    @staticmethod
    def _decode(raw: bytes, content_type: str, resp_cls: type[Message]) -> dict:
        """Decode a JSON or protobuf body into the proto3 JSON dict shape."""
        if "json" in content_type or raw.lstrip().startswith(b"{"):
            return json.loads(raw.decode("utf-8", errors="replace"))
        msg = resp_cls()
        msg.ParseFromString(raw)
        return MessageToDict(msg, preserving_proto_field_name=True)

    def _check_url(self, url: str, key: str) -> bool:
        if url.startswith(("http://", "https://")):
            return True
        self._log(f"ERROR: '{key}' non configuré ({url!r}) — voir recording_clients dans la config")
        self._set_status("ERROR")
        return False

    def _set_status(self, status: str) -> None:
        self._event_bus.publish_sync(self._status_topic, status)

    def _log(self, msg: str) -> None:
        self._event_bus.publish_sync("log", f"[Recording:{self._name}] {msg}")
