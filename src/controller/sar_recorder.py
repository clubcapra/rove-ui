"""
SAR (Search & Rescue) trial recorder and exporter.

Records robot path and OPI positions for end-of-trial file submission.

Required output files:
  path.txt      — UTM path coordinates (WGS84), one timestamped point per line
  opi_list.txt  — UTM OPI coordinates in discovery order
  path_map.jpg  — satellite image with yellow path + red-X OPI markers
  <ts>_<utm>.jpg — one JPEG per OPI photo, filename = timestamp + UTM coords

All timestamps are UNIX/POSIX (float seconds since epoch, UTC).
All coordinates are UTM WGS84.
"""

from __future__ import annotations

import base64
import io
import math
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable


# ── UTM conversion (WGS84) ────────────────────────────────────────────────────

def latlon_to_utm(lat: float, lon: float) -> tuple[int, str, float, float]:
    """Return (zone_number, zone_letter, easting, northing) for WGS84 lat/lon."""
    a  = 6_378_137.0
    f  = 1.0 / 298.257_223_563
    b  = a * (1.0 - f)
    e2 = 1.0 - (b / a) ** 2
    ep2 = e2 / (1.0 - e2)
    k0 = 0.9996

    lat_r = math.radians(lat)
    lon_r = math.radians(lon)

    zone = int((lon + 180.0) / 6.0) + 1
    # Special zones (Norway / Svalbard)
    if 56.0 <= lat < 64.0 and 3.0 <= lon < 12.0:
        zone = 32
    elif 72.0 <= lat <= 84.0:
        if    0.0 <= lon <  9.0: zone = 31
        elif  9.0 <= lon < 21.0: zone = 33
        elif 21.0 <= lon < 33.0: zone = 35
        elif 33.0 <= lon < 42.0: zone = 37

    lon0     = math.radians((zone - 1) * 6.0 - 180.0 + 3.0)
    sin_lat  = math.sin(lat_r)
    cos_lat  = math.cos(lat_r)
    tan_lat  = math.tan(lat_r)

    N = a / math.sqrt(1.0 - e2 * sin_lat ** 2)
    T = tan_lat ** 2
    C = ep2 * cos_lat ** 2
    A = cos_lat * (lon_r - lon0)

    M = a * (
        (1.0 - e2 / 4.0 - 3.0 * e2 ** 2 / 64.0 - 5.0 * e2 ** 3 / 256.0) * lat_r
        - (3.0 * e2 / 8.0 + 3.0 * e2 ** 2 / 32.0 + 45.0 * e2 ** 3 / 1024.0) * math.sin(2.0 * lat_r)
        + (15.0 * e2 ** 2 / 256.0 + 45.0 * e2 ** 3 / 1024.0) * math.sin(4.0 * lat_r)
        - (35.0 * e2 ** 3 / 3072.0) * math.sin(6.0 * lat_r)
    )

    easting = k0 * N * (
        A
        + (1.0 - T + C) * A ** 3 / 6.0
        + (5.0 - 18.0 * T + T ** 2 + 72.0 * C - 58.0 * ep2) * A ** 5 / 120.0
    ) + 500_000.0

    northing = k0 * (
        M + N * tan_lat * (
            A ** 2 / 2.0
            + (5.0 - T + 9.0 * C + 4.0 * C ** 2) * A ** 4 / 24.0
            + (61.0 - 58.0 * T + T ** 2 + 600.0 * C - 330.0 * ep2) * A ** 6 / 720.0
        )
    )
    if lat < 0.0:
        northing += 10_000_000.0

    letters = "CDEFGHJKLMNPQRSTUVWXX"
    letter  = letters[int((lat + 80.0) / 8.0)] if -80.0 <= lat <= 84.0 else "Z"
    return zone, letter, easting, northing


# ── Satellite tile / path-image generation ────────────────────────────────────

_TILE_URL  = (
    "https://server.arcgisonline.com/ArcGIS/rest/services/"
    "World_Imagery/MapServer/tile/{z}/{y}/{x}"
)
_TILE_SIZE = 256


def _lat_lon_to_tile(lat: float, lon: float, z: int) -> tuple[int, int]:
    n  = 2 ** z
    tx = int((lon + 180.0) / 360.0 * n)
    ty = int((1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n)
    return tx, ty


def _lat_lon_to_px(lat: float, lon: float, z: int, x0: int, y0: int) -> tuple[float, float]:
    """Pixel position relative to tile grid origin (x0, y0) at zoom z."""
    n  = 2 ** z
    px = (lon + 180.0) / 360.0 * n * _TILE_SIZE - x0 * _TILE_SIZE
    py = (1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n * _TILE_SIZE - y0 * _TILE_SIZE
    return px, py


def _fetch_tile(z: int, x: int, y: int) -> bytes | None:
    url = _TILE_URL.format(z=z, x=x, y=y)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "RoveUI/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.read()
    except Exception:
        return None


def _auto_zoom(min_lat: float, max_lat: float, min_lon: float, max_lon: float,
               max_px: int = 2048) -> int:
    for z in range(19, 10, -1):
        tx0, ty0 = _lat_lon_to_tile(max_lat, min_lon, z)
        tx1, ty1 = _lat_lon_to_tile(min_lat, max_lon, z)
        w = (max(tx1, tx0) - min(tx1, tx0) + 1) * _TILE_SIZE
        h = (max(ty1, ty0) - min(ty1, ty0) + 1) * _TILE_SIZE
        if w <= max_px and h <= max_px:
            return z
    return 10


def generate_path_image(
    path_pts: list[tuple[float, float, float]],  # (ts, lat, lng)
    opi_pts:  list[tuple[float, float, float]],  # (ts, lat, lng)
) -> bytes | None:
    """
    Return JPEG bytes of a satellite map with:
      - yellow line  : robot path
      - red X        : OPI markers
      - green circle : path start

    Returns None if Pillow is unavailable or there is no path data.
    """
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return None

    if not path_pts:
        return None

    all_lats = [p[1] for p in path_pts] + [p[1] for p in opi_pts]
    all_lons = [p[2] for p in path_pts] + [p[2] for p in opi_pts]
    pad      = 0.0004
    min_lat, max_lat = min(all_lats) - pad, max(all_lats) + pad
    min_lon, max_lon = min(all_lons) - pad, max(all_lons) + pad

    z    = _auto_zoom(min_lat, max_lat, min_lon, max_lon)
    tx0, ty0 = _lat_lon_to_tile(max_lat, min_lon, z)
    tx1, ty1 = _lat_lon_to_tile(min_lat, max_lon, z)
    tx0, tx1 = min(tx0, tx1), max(tx0, tx1)
    ty0, ty1 = min(ty0, ty1), max(ty0, ty1)

    cols = tx1 - tx0 + 1
    rows = ty1 - ty0 + 1
    canvas = Image.new("RGB", (cols * _TILE_SIZE, rows * _TILE_SIZE), (20, 20, 20))

    for iy in range(rows):
        for ix in range(cols):
            data = _fetch_tile(z, tx0 + ix, ty0 + iy)
            if data:
                try:
                    tile = Image.open(io.BytesIO(data)).convert("RGB")
                    canvas.paste(tile, (ix * _TILE_SIZE, iy * _TILE_SIZE))
                except Exception:
                    pass

    draw = ImageDraw.Draw(canvas)

    # Yellow path
    if len(path_pts) >= 2:
        pixels = [_lat_lon_to_px(p[1], p[2], z, tx0, ty0) for p in path_pts]
        for i in range(len(pixels) - 1):
            draw.line([pixels[i], pixels[i + 1]], fill=(255, 220, 0), width=4)

    # Path start — green ring
    if path_pts:
        sx, sy = _lat_lon_to_px(path_pts[0][1], path_pts[0][2], z, tx0, ty0)
        r = 10
        draw.ellipse([(sx - r, sy - r), (sx + r, sy + r)],
                     outline=(0, 230, 118), width=3)

    # OPI markers — red X
    xr = 14
    for _, lat, lon in opi_pts:
        ox, oy = _lat_lon_to_px(lat, lon, z, tx0, ty0)
        draw.line([(ox - xr, oy - xr), (ox + xr, oy + xr)], fill=(255, 30, 30), width=4)
        draw.line([(ox + xr, oy - xr), (ox - xr, oy + xr)], fill=(255, 30, 30), width=4)

    out = io.BytesIO()
    canvas.save(out, format="JPEG", quality=92)
    return out.getvalue()


# ── WebDAV upload ─────────────────────────────────────────────────────────────

def webdav_put(server_url: str, filename: str, data: bytes,
               username: str = "", password: str = "") -> None:
    """HTTP PUT a single file to a WebDAV server."""
    url = server_url.rstrip("/") + "/" + filename.lstrip("/")
    req = urllib.request.Request(url, data=data, method="PUT")
    if username:
        cred = base64.b64encode(f"{username}:{password}".encode()).decode()
        req.add_header("Authorization", f"Basic {cred}")
    req.add_header("Content-Type", "application/octet-stream")
    with urllib.request.urlopen(req, timeout=30):
        pass


# ── SAR Recorder ──────────────────────────────────────────────────────────────

_PathPoint = tuple[float, float, float]   # (unix_ts, lat, lng)
_OPI       = dict                          # {ts, lat, lng, label, photo}


class SARRecorder:
    """
    Records robot GPS path and OPI positions, then exports the four required
    SAR trial files (path.txt, opi_list.txt, path_map.jpg, OPI images).

    Subscribes (via EventBus) to:
      gps_topic (default "gnss") — dict with lat_field/lng_field (default "latitude"/"longitude")
      "map.poi"                  — dict {lat, lng, label, photo?, ts?}
      "costmap.poi"              — dict {lat, lng, label, photo?, ts?}
    """

    def __init__(self, event_bus, config: dict | None = None):
        self._bus    = event_bus
        self._cfg    = config or {}
        self._lock   = threading.Lock()

        self._recording  = False
        self._path_pts:  list[_PathPoint] = []
        self._opis:      list[_OPI]       = []

        self._last_lat: float | None = None
        self._last_lng: float | None = None
        self._last_ts:  float        = 0.0

        self._min_dist_m   = float(self._cfg.get("path_min_distance_m", 1.0))
        self._max_interval = float(self._cfg.get("path_max_interval_s", 5.0))
        self._gps_topic    = str(self._cfg.get("gps_topic",   "gnss"))
        self._lat_field    = str(self._cfg.get("lat_field",   "latitude"))
        self._lng_field    = str(self._cfg.get("lng_field",   "longitude"))

        self._status_cbs: list[Callable] = []
        self._log_cbs:    list[Callable] = []

        self._bus.subscribe(self._gps_topic,  self._on_position)
        self._bus.subscribe("map.poi",        self._on_poi)
        self._bus.subscribe("costmap.poi",    self._on_poi)

    # ── Callbacks ─────────────────────────────────────────────────────────

    def add_status_cb(self, cb: Callable) -> None:
        self._status_cbs.append(cb)

    def add_log_cb(self, cb: Callable) -> None:
        self._log_cbs.append(cb)

    def _emit_status(self) -> None:
        for cb in self._status_cbs:
            try:
                cb(self._recording, len(self._path_pts), len(self._opis))
            except Exception:
                pass

    def _log(self, msg: str) -> None:
        for cb in self._log_cbs:
            try:
                cb(msg)
            except Exception:
                pass
        self._bus.publish_sync("log", f"[SAR] {msg}")

    # ── Public API ─────────────────────────────────────────────────────────

    @property
    def is_recording(self) -> bool:
        return self._recording

    @property
    def path_count(self) -> int:
        return len(self._path_pts)

    @property
    def opi_count(self) -> int:
        return len(self._opis)

    def start(self) -> None:
        self._recording = True
        self._log("Recording started")
        self._emit_status()

    def stop(self) -> None:
        self._recording = False
        self._log(f"Recording stopped — {len(self._path_pts)} pts, {len(self._opis)} OPIs")
        self._emit_status()

    def clear(self) -> None:
        with self._lock:
            self._path_pts.clear()
            self._opis.clear()
            self._last_lat = None
            self._last_lng = None
            self._last_ts  = 0.0
        self._log("Data cleared")
        self._emit_status()

    # ── EventBus intake ────────────────────────────────────────────────────

    @staticmethod
    def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        R    = 6_371_000.0
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a    = (math.sin(dlat / 2) ** 2
                + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
                * math.sin(dlon / 2) ** 2)
        return 2.0 * R * math.asin(math.sqrt(a))

    def _on_position(self, payload: dict) -> None:
        if not self._recording:
            return
        try:
            lat = float(payload[self._lat_field])
            lng = float(payload[self._lng_field])
            ts  = float(payload.get("ts", time.time()))
        except (TypeError, KeyError, ValueError):
            return

        now     = time.monotonic()
        dist    = (
            self._haversine_m(self._last_lat, self._last_lng, lat, lng)
            if self._last_lat is not None else float("inf")
        )
        elapsed = now - self._last_ts

        if dist >= self._min_dist_m or elapsed >= self._max_interval:
            with self._lock:
                self._path_pts.append((ts, lat, lng))
                self._last_lat = lat
                self._last_lng = lng
                self._last_ts  = now
            self._emit_status()

    def _on_poi(self, payload: dict) -> None:
        if not isinstance(payload, dict):
            return
        try:
            lat = float(payload["lat"])
            lng = float(payload["lng"])
        except (KeyError, TypeError, ValueError):
            return
        # Skip zero-GPS (no start position set yet)
        if lat == 0.0 and lng == 0.0:
            return
        ts    = float(payload.get("ts", time.time()))
        label = str(payload.get("label", "OPI"))
        photo = payload.get("photo")
        with self._lock:
            self._opis.append({"ts": ts, "lat": lat, "lng": lng,
                                "label": label, "photo": photo})
        self._log(f"OPI #{len(self._opis)} recorded: «{label}» ({lat:.6f},{lng:.6f})")
        self._emit_status()

    # ── Export ─────────────────────────────────────────────────────────────

    def export(
        self,
        output_dir: str,
        on_progress: Callable[[str], None] | None = None,
        on_done:     Callable[[bool, dict, str | None], None] | None = None,
    ) -> None:
        """Start export in a background thread.
        on_done(success, files_dict, error_str)
        """
        with self._lock:
            path_snap = list(self._path_pts)
            opi_snap  = list(self._opis)

        def _run():
            try:
                files = _do_export(path_snap, opi_snap, output_dir, on_progress)
                if on_done:
                    on_done(True, files, None)
            except Exception as exc:
                if on_done:
                    on_done(False, {}, str(exc))

        threading.Thread(target=_run, daemon=True, name="sar-export").start()

    def upload(
        self,
        files:       dict[str, str],
        server_url:  str,
        username:    str = "",
        password:    str = "",
        on_progress: Callable[[str], None] | None = None,
        on_done:     Callable[[bool, str | None], None] | None = None,
    ) -> None:
        """Upload exported files to WebDAV in a background thread."""
        def _run():
            try:
                for _, path in files.items():
                    fname = Path(path).name
                    if on_progress:
                        on_progress(f"Uploading {fname} …")
                    webdav_put(server_url, fname, Path(path).read_bytes(),
                               username, password)
                if on_done:
                    on_done(True, None)
            except Exception as exc:
                if on_done:
                    on_done(False, str(exc))

        threading.Thread(target=_run, daemon=True, name="sar-upload").start()


# ── Pure export logic (no Qt, runs in background thread) ─────────────────────

def _do_export(
    path_pts:   list[_PathPoint],
    opis:       list[_OPI],
    output_dir: str,
    progress:   Callable[[str], None] | None,
) -> dict[str, str]:
    def p(msg: str) -> None:
        if progress:
            progress(msg)

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    files: dict[str, str] = {}

    # 1 ── path.txt
    p("Writing path.txt …")
    lines = ["# UTM (WGS84)"]
    for ts, lat, lng in path_pts:
        zone, letter, e, n = latlon_to_utm(lat, lng)
        lines.append(f"{ts:.6f} {zone}{letter} {e:.2f} {n:.2f}")
    path_file = out / "path.txt"
    path_file.write_text("\n".join(lines), encoding="utf-8")
    files["path"] = str(path_file)
    p(f"  → {len(path_pts)} points")

    # 2 ── opi_list.txt
    p("Writing opi_list.txt …")
    lines = ["# UTM (WGS84)"]
    for opi in opis:
        zone, letter, e, n = latlon_to_utm(opi["lat"], opi["lng"])
        lines.append(f"{opi['ts']:.6f} {zone}{letter} {e:.2f} {n:.2f}")
    opi_file = out / "opi_list.txt"
    opi_file.write_text("\n".join(lines), encoding="utf-8")
    files["opi_list"] = str(opi_file)
    p(f"  → {len(opis)} OPIs")

    # 3 ── OPI images (filename = timestamp_UTM.jpg)
    p(f"Writing {len(opis)} OPI image(s) …")
    for opi in opis:
        photo = opi.get("photo")
        if not photo:
            continue
        zone, letter, e, n = latlon_to_utm(opi["lat"], opi["lng"])
        # File name matches the spec: timestamp_ZONEeasting_northing.jpg
        fname = f"{opi['ts']:.6f}_{zone}{letter}{e:.2f}_{n:.2f}.jpg"
        fname = fname.replace(" ", "")
        try:
            if isinstance(photo, str) and photo.startswith("data:"):
                _, b64 = photo.split(",", 1)
                img_bytes = base64.b64decode(b64)
            elif isinstance(photo, bytes):
                img_bytes = photo
            else:
                continue
        except Exception:
            continue
        (out / fname).write_bytes(img_bytes)
        files[f"opi_img_{opi['ts']:.0f}"] = str(out / fname)
        p(f"  → {fname}")

    # 4 ── path_map.jpg
    p("Generating path_map.jpg (fetching satellite tiles) …")
    opi_pts  = [(o["ts"], o["lat"], o["lng"]) for o in opis]
    img_data = generate_path_image(path_pts, opi_pts)
    if img_data:
        img_file = out / "path_map.jpg"
        img_file.write_bytes(img_data)
        files["path_map"] = str(img_file)
        p(f"  → path_map.jpg ({len(img_data)//1024} KB)")
    else:
        p("  WARNING: path_map.jpg skipped (install Pillow: pip install Pillow)")

    p("Export complete.")
    return files
