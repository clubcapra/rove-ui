from __future__ import annotations

import math
import threading
import time
from typing import Any

from src.controller.event_bus import EventBus


def _latlon_to_en(lat: float, lng: float, lat0: float, lng0: float) -> tuple[float, float]:
    north = (lat - lat0) * 111_320.0
    east  = (lng - lng0) * 111_320.0 * math.cos(math.radians(lat0))
    return round(east, 4), round(north, 4)


def _dist_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Approximate distance in metres between two GPS points (flat-earth)."""
    dn = (lat2 - lat1) * 111_320.0
    de = (lng2 - lng1) * 111_320.0 * math.cos(math.radians((lat1 + lat2) / 2))
    return math.sqrt(dn * dn + de * de)


class PathRecorder:
    """Records GPS positions into a path and dispatches waypoints as goto commands.

    Config keys
    -----------
    name               : str   Identifier used in log messages
    lat_topic          : str   EventBus topic for GPS latitude  (default: gnss.latitude)
    lng_topic          : str   EventBus topic for GPS longitude (default: gnss.longitude)
    record_topic       : str   Topic that accepts "start" / "stop" / "clear"
    play_topic         : str   Topic that triggers path playback (any value)
    goto_dispatch_topic: str   Topic to publish each waypoint on playback
                               (default: path.goto_step — wire this to your HTTP client)
    waypoints_topic    : str   Topic to publish the full waypoint list on play
    sample_interval_s  : float Minimum time between samples while recording (default: 1.0)
    min_distance_m     : float Minimum robot movement to record a new point (default: 0.5)
    step_delay_ms      : int   Delay between sequential goto dispatches in ms (default: 0)
    """

    def __init__(self, config: dict[str, Any], event_bus: EventBus | None = None) -> None:
        self._config     = config
        self._event_bus  = event_bus or EventBus()
        self._name       = str(config.get("name", "path"))

        self._lat_topic         = str(config.get("lat_topic",          "gnss.latitude"))
        self._lng_topic         = str(config.get("lng_topic",          "gnss.longitude"))
        self._record_topic      = str(config.get("record_topic",       "path.record"))
        self._play_topic        = str(config.get("play_topic",         "path.play"))
        self._dispatch_topic    = str(config.get("goto_dispatch_topic","path.goto_step"))
        self._waypoints_topic   = str(config.get("waypoints_topic",    "path.waypoints"))
        self._sample_interval   = float(config.get("sample_interval_s", 1.0))
        self._min_distance_m    = float(config.get("min_distance_m",    0.5))
        self._step_delay_ms     = int(config.get("step_delay_ms",       0))

        self._lat: float | None = None
        self._lng: float | None = None
        self._recording  = False
        self._path: list[dict] = []            # [{lat, lng, east, north}]
        self._origin_lat: float | None = None
        self._origin_lng: float | None = None
        self._last_sample_t    = 0.0
        self._last_sample_lat: float | None = None
        self._last_sample_lng: float | None = None
        self._play_timer: threading.Timer | None = None

    # ── Lifecycle ─────────────────────────────────────────────────────────

    def start(self) -> None:
        self._event_bus.subscribe(self._lat_topic,    self._on_lat)
        self._event_bus.subscribe(self._lng_topic,    self._on_lng)
        self._event_bus.subscribe(self._record_topic, self._on_record_cmd)
        self._event_bus.subscribe(self._play_topic,   lambda _: self._play())
        self._log(
            f"ready  record='{self._record_topic}'  play='{self._play_topic}'  "
            f"dispatch='{self._dispatch_topic}'"
        )

    def stop(self) -> None:
        self._recording = False
        if self._play_timer is not None:
            self._play_timer.cancel()
            self._play_timer = None

    # ── GPS subscriptions ─────────────────────────────────────────────────

    def _on_lat(self, value: Any) -> None:
        try:
            self._lat = float(value)
        except (TypeError, ValueError):
            return
        self._maybe_sample()

    def _on_lng(self, value: Any) -> None:
        try:
            self._lng = float(value)
        except (TypeError, ValueError):
            return

    # ── Recording ─────────────────────────────────────────────────────────

    def _on_record_cmd(self, value: Any) -> None:
        cmd = str(value).strip().lower()

        if cmd == "start":
            if self._lat is None or self._lng is None:
                self._log("record start ignored — no GPS fix yet")
                return
            self._recording    = True
            self._origin_lat   = self._lat
            self._origin_lng   = self._lng
            self._last_sample_t = 0.0
            self._last_sample_lat = None
            self._last_sample_lng = None
            self._log(
                f"recording STARTED  origin=({self._origin_lat:.6f},{self._origin_lng:.6f})"
            )

        elif cmd == "stop":
            self._recording = False
            self._log(f"recording STOPPED  {len(self._path)} point(s) recorded")

        elif cmd == "clear":
            self._recording  = False
            n = len(self._path)
            self._path       = []
            self._origin_lat = None
            self._origin_lng = None
            self._log(f"path CLEARED  ({n} point(s) discarded)")

    def _maybe_sample(self) -> None:
        if not self._recording:
            return
        if self._lat is None or self._lng is None:
            return
        if self._origin_lat is None or self._origin_lng is None:
            return

        now = time.monotonic()
        if now - self._last_sample_t < self._sample_interval:
            return

        # Distance filter — skip if robot hasn't moved enough
        if self._last_sample_lat is not None and self._last_sample_lng is not None:
            d = _dist_m(self._last_sample_lat, self._last_sample_lng, self._lat, self._lng)
            if d < self._min_distance_m:
                return

        east, north = _latlon_to_en(self._lat, self._lng, self._origin_lat, self._origin_lng)
        self._path.append({
            "lat":   self._lat,
            "lng":   self._lng,
            "east":  east,
            "north": north,
        })
        self._last_sample_t   = now
        self._last_sample_lat = self._lat
        self._last_sample_lng = self._lng
        n = len(self._path)
        self._log(f"#{n:03d}  east={east:+.2f}m  north={north:+.2f}m  ({self._lat:.6f},{self._lng:.6f})")

    # ── Playback ──────────────────────────────────────────────────────────

    def _play(self) -> None:
        if not self._path:
            self._log("play: path is empty")
            return

        n = len(self._path)
        self._log(f"play: dispatching {n} waypoint(s) → '{self._dispatch_topic}'")

        # Publish full list to waypoints topic (for a batch endpoint if needed)
        self._event_bus.publish_sync(self._waypoints_topic, list(self._path))

        if self._step_delay_ms <= 0:
            # Fire all immediately — let the HTTP client / backend queue them
            for i, wp in enumerate(self._path):
                self._event_bus.publish_sync(self._dispatch_topic, wp)
                self._log(f"step {i+1}/{n}  east={wp['east']:+.2f}m  north={wp['north']:+.2f}m")
        else:
            # Chain with threading.Timer for human-readable pacing
            self._dispatch_step(list(self._path), 0)

    def _dispatch_step(self, waypoints: list[dict], idx: int) -> None:
        if idx >= len(waypoints):
            self._log("play: all waypoints dispatched")
            return
        wp = waypoints[idx]
        self._event_bus.publish_sync(self._dispatch_topic, wp)
        self._log(
            f"step {idx+1}/{len(waypoints)}  east={wp['east']:+.2f}m  north={wp['north']:+.2f}m"
        )
        delay = self._step_delay_ms / 1000.0
        self._play_timer = threading.Timer(
            delay, self._dispatch_step, args=(waypoints, idx + 1)
        )
        self._play_timer.daemon = True
        self._play_timer.start()

    # ── Helpers ───────────────────────────────────────────────────────────

    def _log(self, msg: str) -> None:
        self._event_bus.publish_sync("log", f"[PathRecorder:{self._name}] {msg}")
