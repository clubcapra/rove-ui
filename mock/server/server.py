#!/usr/bin/env python3
"""
Rove Mock Server — replaces ROS2 topics and ODrive hardware for local development.

Endpoints
---------
ODrive (compatible with udp_client.py / main.py):
  GET  /discover                 — sensor discovery
  GET  /odrive_{nid}/data        — motor telemetry  (nid: 31-34)
  POST /odrive_{nid}/command     — command handler
  POST /odrive_{nid}/estop       — node e-stop

Track joints (replaces mock.sh):
  GET  /track_joints             — velocity + temperatures for FL/RL/FR/RR

Flipper joints (replaces mock_flipper_joints.py):
  GET  /flipper_joints           — sinusoidal positions for FL/RL/FR/RR

Costmap:
  GET  /map_feed                 — 50×50 occupancy bitmap (PNG, evolves over time)

Navigation / system:
  GET  /gnss                     — latitude / longitude / altitude
  GET  /battery                  — charge, voltage, current, temperature
  GET  /signals                  — signal strengths (VTX, Microhard)

ArcRaven-compatible shims:
  POST /api/estop                — global e-stop
  GET  /api/health               — health summary
  GET  /api/sensors              — sensor list

Run directly:
  pip install -r requirements.txt
  uvicorn server:app --host 0.0.0.0 --port 8080 --reload

Via Docker:
  docker compose up
"""

from __future__ import annotations

import io
import math
import time

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI(title="Rove Mock Server", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_START = time.monotonic()


def _t() -> float:
    """Seconds since server start."""
    return time.monotonic() - _START


def _sin(period: float, phase: float = 0.0) -> float:
    return math.sin(2 * math.pi * _t() / period + phase)


def _noise(scale: float, freq: float, phase: float = 0.0) -> float:
    """Cheap pseudo-noise via sum of incommensurate sines — no extra deps."""
    t = _t()
    return scale * (
        0.50 * math.sin(2 * math.pi * t * freq + phase)
        + 0.30 * math.sin(2 * math.pi * t * freq * 1.618 + phase * 1.3)
        + 0.20 * math.sin(2 * math.pi * t * freq * 2.718 + phase * 0.7)
    )


# ---------------------------------------------------------------------------
# ODrive topology
# ---------------------------------------------------------------------------

_LEFT_NODES: frozenset[int] = frozenset({32, 33})
_RIGHT_NODES: frozenset[int] = frozenset({31, 34})
_ALL_NODES: frozenset[int] = _LEFT_NODES | _RIGHT_NODES

# leader → follower per track
_LEADER_FOLLOWER: dict[int, int] = {32: 33, 34: 31}
_FOLLOWER_LEADER: dict[int, int] = {v: k for k, v in _LEADER_FOLLOWER.items()}


# ---------------------------------------------------------------------------
# /discover
# ---------------------------------------------------------------------------

@app.get("/discover", summary="ODrive sensor discovery")
def discover() -> dict:
    sensors = []
    for nid in sorted(_ALL_NODES):
        sensors.append({
            "id": f"odrive_{nid}",
            "command_port": 9100 + nid,
            "endpoints": {
                "data":    f"/odrive_{nid}/data",
                "command": f"/odrive_{nid}/command",
                "info":    f"/odrive_{nid}/info",
            },
        })
    return {"sensors": sensors}


# ---------------------------------------------------------------------------
# /odrive_{nid}/data
# ---------------------------------------------------------------------------

@app.get("/odrive_{nid}/data", summary="ODrive node telemetry")
def odrive_data(nid: int) -> Response:
    if nid not in _ALL_NODES:
        return Response(status_code=404)

    sign = 1 if nid in _LEFT_NODES else -1

    vel      = sign * 2.5 * _sin(4.0)
    iq       = vel * 0.5
    motor_t  = 45.0 + _noise(8.0, 0.012, phase=float(nid))
    fet_t    = 36.0 + _noise(5.0, 0.015, phase=float(nid) + 1.0)
    bus_v    = 48.0 + _noise(0.4, 0.08,  phase=float(nid) + 2.0)
    bus_i    = abs(vel) * 1.8 + _noise(0.1, 0.3, phase=float(nid))

    import json
    body = json.dumps({
        "node_id":          nid,
        "axis_state":       8,        # ClosedLoopControl
        "axis_error":       0,
        "active_errors":    0,
        "disarm_reason":    0,
        "procedure_result": 0,
        "trajectory_done":  True,
        "pos_estimate":     round(math.sin(2 * math.pi * _t() / 8.0) * 10.0, 4),
        "vel_estimate":     round(vel,   4),
        "iq_setpoint":      round(iq,    4),
        "iq_measured":      round(iq + _noise(0.03, 1.0, float(nid)), 4),
        "motor_temp":       round(motor_t, 2),
        "fet_temp":         round(fet_t,   2),
        "bus_voltage":      round(bus_v,   2),
        "bus_current":      round(bus_i,   3),
        "electrical_power": round(bus_i * bus_v, 2),
        "mechanical_power": round(bus_i * bus_v * 0.92, 2),
        "torque_estimate":  round(iq * 0.236, 4),
        "torque_target":    round(iq * 0.236, 4),
        "count_cpr":        8192,
        "shadow_count":     int(vel * _t() * 100) % 65536,
        "timestamp_ns":     time.time_ns(),
    }).encode()

    return Response(content=body, media_type="application/json")


@app.post("/odrive_{nid}/command", summary="Send command to ODrive node")
async def odrive_command(nid: int, body: dict) -> dict:
    return {"success": True, "message": f"Command accepted by odrive_{nid}"}


@app.post("/odrive_{nid}/estop", summary="E-stop ODrive node")
async def odrive_estop(nid: int) -> dict:
    return {"success": True}


# ---------------------------------------------------------------------------
# /track_joints  (replaces mock.sh)
# ---------------------------------------------------------------------------

_TRACK_CFG: dict[str, dict] = {
    "track_fl_j": {"sign":  1.0, "phase": 0.00},
    "track_rl_j": {"sign":  1.0, "phase": 0.05},
    "track_fr_j": {"sign": -1.0, "phase": 0.00},
    "track_rr_j": {"sign": -1.0, "phase": 0.05},
}


@app.get("/track_joints", summary="Track joint states (velocity + temperatures)")
def track_joints() -> dict:
    result: dict = {}
    for i, (name, cfg) in enumerate(_TRACK_CFG.items()):
        vel = cfg["sign"] * 2.5 * math.sin(2 * math.pi * _t() / 4.0 + cfg["phase"])
        result[name] = {
            "velocity":          round(vel, 4),
            "motor_temperature": round(45.0 + _noise(8.0, 0.012, float(i)),       2),
            "fet_temperature":   round(36.0 + _noise(5.0, 0.015, float(i) + 1.0), 2),
        }
    return result


# ---------------------------------------------------------------------------
# /flipper_joints  (replaces mock_flipper_joints.py)
# ---------------------------------------------------------------------------

_FLIPPER_JOINTS = ["flipper_fl_j", "flipper_rl_j", "flipper_fr_j", "flipper_rr_j"]
_FLIPPER_PHASES = [0.0, math.pi / 2, math.pi, 3 * math.pi / 2]
_AMPLITUDE      = 0.8   # rad (~45°)
_PERIOD         = 4.0   # seconds


@app.get("/flipper_joints", summary="Flipper joint positions (sinusoidal)")
def flipper_joints() -> dict:
    omega = 2 * math.pi / _PERIOD
    return {
        joint: {"position": round(_AMPLITUDE * math.sin(omega * _t() + phase), 6)}
        for joint, phase in zip(_FLIPPER_JOINTS, _FLIPPER_PHASES)
    }


# ---------------------------------------------------------------------------
# /map_feed  — 50×50 occupancy costmap, PNG, evolves over time
# ---------------------------------------------------------------------------

_MAP_CELLS = 50
_MAP_SCALE = 6    # upscale factor for display (→ 300×300 px)


@app.get("/map_feed", summary="50×50 costmap bitmap (PNG)")
def map_feed() -> Response:
    t   = _t()
    img = Image.new("L", (_MAP_CELLS, _MAP_CELLS), 0)   # 0 = free space
    pix = img.load()

    # ── static border walls ──
    for x in range(_MAP_CELLS):
        pix[x, 0] = pix[x, _MAP_CELLS - 1] = 210
    for y in range(_MAP_CELLS):
        pix[0, y] = pix[_MAP_CELLS - 1, y] = 210

    # ── static inner structure (corridors) ──
    for x in range(10, 40):
        pix[x, 20] = 200
    for y in range(5, 20):
        pix[25, y] = 200

    # ── moving obstacle A ──
    ox = int(25 + 12 * math.sin(t * 0.22))
    oy = int(25 + 10 * math.cos(t * 0.17))
    for dx in range(-3, 4):
        for dy in range(-3, 4):
            x, y = ox + dx, oy + dy
            if 1 <= x < _MAP_CELLS - 1 and 1 <= y < _MAP_CELLS - 1:
                pix[x, y] = 180

    # ── moving obstacle B ──
    ox2 = int(15 + 8 * math.cos(t * 0.28 + 1.5))
    oy2 = int(35 + 7 * math.sin(t * 0.19 + 0.8))
    for dx in range(-2, 3):
        for dy in range(-2, 3):
            x, y = ox2 + dx, oy2 + dy
            if 1 <= x < _MAP_CELLS - 1 and 1 <= y < _MAP_CELLS - 1:
                pix[x, y] = 160

    # ── robot footprint (white) ──
    rx = int(25 + 4 * math.sin(t * 0.07))
    ry = int(25 + 4 * math.cos(t * 0.09))
    for dx in range(-1, 2):
        for dy in range(-1, 2):
            x, y = rx + dx, ry + dy
            if 0 <= x < _MAP_CELLS and 0 <= y < _MAP_CELLS:
                pix[x, y] = 255

    # upscale for visibility and encode
    img = img.resize((_MAP_CELLS * _MAP_SCALE, _MAP_CELLS * _MAP_SCALE), Image.NEAREST)
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=False)

    return Response(
        content=buf.getvalue(),
        media_type="image/png",
        headers={"Cache-Control": "no-cache, no-store"},
    )


# ---------------------------------------------------------------------------
# /gnss
# ---------------------------------------------------------------------------

@app.get("/gnss", summary="GNSS position (lat/lon/alt)")
def gnss() -> dict:
    return {
        "latitude":    round(45.5017 + 0.0001 * _sin(80.0),          8),
        "longitude":   round(-73.5673 + 0.0001 * _sin(80.0, 1.57),   8),
        "altitude":    round(12.5     + 0.15   * _sin(60.0),          2),
        "fix":         "3D",
        "satellites":  9,
        "hdop":        1.2,
        "accuracy_m":  round(1.5 + 0.2 * _sin(30.0), 2),
        "timestamp_ns": time.time_ns(),
    }


# ---------------------------------------------------------------------------
# /battery
# ---------------------------------------------------------------------------

_BATTERY_START_PCT = 85.0
_DRAIN_PCT_PER_S   = 0.5 / 60   # 0.5 % per minute


@app.get("/battery", summary="Battery status")
def battery() -> dict:
    pct     = max(0.0, _BATTERY_START_PCT - _t() * _DRAIN_PCT_PER_S)
    voltage = 44.0 + (pct / 100.0) * 8.0
    current = 5.0 + 0.5 * _sin(10.0)
    return {
        "percentage":   round(pct,     1),
        "voltage":      round(voltage, 2),
        "current":      round(current, 2),
        "power_w":      round(voltage * current, 1),
        "temperature":  round(28.0 + 0.8 * _sin(120.0), 1),
        "status":       "discharging",
        "cell_count":   12,
        "cell_voltage": round(voltage / 12.0, 3),
        "timestamp_ns": time.time_ns(),
    }


# ---------------------------------------------------------------------------
# /signals
# ---------------------------------------------------------------------------

@app.get("/signals", summary="Radio signal strengths")
def signals() -> dict:
    return {
        "signals": [
            {
                "name":          "VTX",
                "db":            round(-65.0 + _noise(3.5, 0.09),        1),
                "quality":       "good",
                "frequency_mhz": 5800,
            },
            {
                "name":          "Microhard",
                "db":            round(-72.0 + _noise(4.0, 0.07, 1.2),   1),
                "quality":       "fair",
                "frequency_mhz": 900,
            },
        ],
        "timestamp_ns": time.time_ns(),
    }


# ---------------------------------------------------------------------------
# ArcRaven-compatible shims
# ---------------------------------------------------------------------------

@app.post("/api/estop", summary="Global e-stop (ArcRaven compatible)")
def api_estop() -> dict:
    return {"success": True, "message": "ESTOP sent to all ODrives (mock)"}


@app.get("/api/health", summary="Service health")
def api_health() -> dict:
    return {
        "status":               "ok",
        "sensor_count":         len(_ALL_NODES) + 3,
        "active_subscriptions": 0,
        "sensors": {
            **{f"odrive_{nid}": {"running": True, "last_data_ms_ago": 40}
               for nid in _ALL_NODES},
            "gnss":    {"running": True, "last_data_ms_ago": 100},
            "battery": {"running": True, "last_data_ms_ago": 200},
            "signals": {"running": True, "last_data_ms_ago": 150},
        },
    }


@app.get("/api/sensors", summary="Sensor list (ArcRaven compatible)")
def api_sensors() -> list:
    result = []
    for nid in sorted(_ALL_NODES):
        result.append({
            "id":              f"odrive_{nid}",
            "name":            f"odrive_{nid}",
            "kinds":           ["JointState"],
            "running":         True,
            "accepts_commands": True,
            "last_data_ms_ago": 40,
            "command_port":    9100 + nid,
            "commands": [
                {"name": "estop",          "description": "Emergency stop"},
                {"name": "set_axis_state", "description": "Set axis state",
                 "example_args": {"state": 8}},
                {"name": "set_input_vel",  "description": "Set input velocity",
                 "example_args": {"vel": 0.0}},
                {"name": "clear_errors",   "description": "Clear axis errors"},
            ],
        })
    return result
