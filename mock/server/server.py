#!/usr/bin/env python3
"""
Rove Mock Server — replaces ROS2 topics and ODrive hardware for local development.

HTTP Endpoints
--------------
ODrive (compatible with udp_client.py / main.py):
  GET  /discover                 — sensor discovery (data_port, command_port per sensor)
  GET  /odrive_{nid}/data        — motor telemetry  (nid: 31-34)
  GET  /odrive_{nid}/info        — sensor info with UDP ports
  POST /odrive_{nid}/command     — command handler
  POST /odrive_{nid}/estop       — node e-stop

IMU / VectorNav:
  GET  /vectornav_ttyUSB_VN300/data  — IMU telemetry
  GET  /vectornav_ttyUSB_VN300/info  — sensor info
  POST /vectornav_ttyUSB_VN300/command

Kinova arm:
  GET  /kinova_arm/data
  GET  /kinova_arm/info
  POST /kinova_arm/command
  POST /kinova_arm/estop

Legacy / extra:
  GET  /track_joints  /flipper_joints  /map_feed
  GET  /gnss  /battery  /signals
  POST /api/estop  GET /api/health  GET /api/sensors

UDP Protocol (per sensor, automatically started on boot)
---------------------------------------------------------
Data port — subscribe / push:
  Client → Server  b'\\x01\\x01\\x00\\x00'  Subscribe   (msg_type 0x01)
  Client → Server  b'\\x01\\x02\\x00\\x00'  Unsubscribe (msg_type 0x02)
  Server → Client  [hdr 4B] + JSON payload  Data push   (msg_type 0x03) @ 20 Hz

  Backwards compat: bare b'\\x01' is accepted as Subscribe.

Command port — REST or Stream:
  Client → Server  [hdr 4B] + JSON or RoveControl protobuf  Command     (0x10)
  Client → Server  [hdr 4B] + JSON or RoveControl protobuf  StreamStart (0x12)
  Server → Client  [hdr 4B] + {status: ok}                  CommandAck  (0x11)
  Client → Server  [hdr 4B]                                  StreamStop  (0x13)

  Packet header: | version=0x01 (1B) | msg_type (1B) | seq_num (2B LE) |

Run directly:
  pip install -r requirements.txt
  uvicorn server:app --host 0.0.0.0 --port 8080 --reload

Via Docker:
  docker compose up
"""

from __future__ import annotations

import asyncio
import io
import json
import math
import os
import socket
import struct
import sys
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Callable

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image

# ---------------------------------------------------------------------------
# Protobuf (optional — graceful fallback to JSON-only if not compiled)
# ---------------------------------------------------------------------------

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "proto_gen"))
try:
    from proto import DriveNodeState_pb2, RoveControl_pb2
    from proto.imu import Vn300_pb2
    _PROTO_OK = True
except Exception as _proto_err:
    _PROTO_OK = False
    print(f"[proto] disabled ({_proto_err}); run compile_protos.sh to enable", flush=True)

# ---------------------------------------------------------------------------
# UDP protocol constants
# ---------------------------------------------------------------------------

_UDP_VERSION    = 0x01
MSG_SUBSCRIBE   = 0x01
MSG_UNSUBSCRIBE = 0x02
MSG_DATA        = 0x03
MSG_COMMAND     = 0x10
MSG_CMD_ACK     = 0x11
MSG_STREAM_START = 0x12
MSG_STREAM_STOP  = 0x13

PUSH_HZ = 20          # data push rate
PUSH_INTERVAL = 1.0 / PUSH_HZ


def _parse_msg_type(data: bytes) -> int:
    """Extract msg_type from an incoming UDP packet.
    Accepts both the proper 4-byte header and the legacy bare b'\\x01'."""
    if len(data) == 1:
        return data[0]          # legacy: bare 0x01 subscribe
    if len(data) >= 2:
        return data[1]          # [version, msg_type, seq_lo, seq_hi, ...]
    return 0


def _make_packet(msg_type: int, seq: int, payload: bytes) -> bytes:
    return struct.pack("<BBH", _UDP_VERSION, msg_type, seq & 0xFFFF) + payload


def _decode_command(sensor_id: str, payload: bytes) -> dict:
    """Try RoveControl protobuf first, then fall back to JSON."""
    if not payload:
        return {}
    if _PROTO_OK:
        try:
            ctrl = RoveControl_pb2.RoveControl()
            ctrl.ParseFromString(payload)
            return {
                "type": "RoveControl",
                "tracks": {"left_vel": ctrl.tracks.left_vel, "right_vel": ctrl.tracks.right_vel},
                "flippers": {
                    "fl": {"pos_deg": ctrl.flippers.fl.pos_deg, "vel": ctrl.flippers.fl.vel},
                    "fr": {"pos_deg": ctrl.flippers.fr.pos_deg, "vel": ctrl.flippers.fr.vel},
                    "rl": {"pos_deg": ctrl.flippers.rl.pos_deg, "vel": ctrl.flippers.rl.vel},
                    "rr": {"pos_deg": ctrl.flippers.rr.pos_deg, "vel": ctrl.flippers.rr.vel},
                },
                "timestamp_us": ctrl.timestamp_us,
            }
        except Exception:
            pass
    try:
        return json.loads(payload.decode("utf-8", errors="replace"))
    except Exception:
        return {"raw_hex": payload[:64].hex()}

# ---------------------------------------------------------------------------
# UDP DatagramProtocol classes
# ---------------------------------------------------------------------------

class SensorDataPort(asyncio.DatagramProtocol):
    """Listens for Subscribe / Unsubscribe, pushes Data packets to subscribers."""

    def __init__(self, sensor_id: str, data_gen: Callable[[], bytes]) -> None:
        self._sensor_id = sensor_id
        self._data_gen = data_gen
        self._subscribers: dict[tuple, int] = {}   # addr -> seq_num
        self._transport: asyncio.DatagramTransport | None = None
        self._push_task: asyncio.Task | None = None

    def connection_made(self, transport: asyncio.DatagramTransport) -> None:  # type: ignore[override]
        self._transport = transport
        self._push_task = asyncio.get_running_loop().create_task(self._push_loop())

    def datagram_received(self, data: bytes, addr: tuple) -> None:
        msg_type = _parse_msg_type(data)
        if msg_type == MSG_SUBSCRIBE:
            self._subscribers[addr] = 0
            print(f"[UDP] {self._sensor_id} ← Subscribe from {addr[0]}:{addr[1]}", flush=True)
        elif msg_type == MSG_UNSUBSCRIBE:
            self._subscribers.pop(addr, None)
            print(f"[UDP] {self._sensor_id} ← Unsubscribe from {addr[0]}:{addr[1]}", flush=True)

    async def _push_loop(self) -> None:
        while True:
            if self._subscribers and self._transport:
                try:
                    payload = self._data_gen()
                except Exception as exc:
                    print(f"[UDP] {self._sensor_id} data_gen error: {exc}", flush=True)
                    await asyncio.sleep(PUSH_INTERVAL)
                    continue
                dead: list[tuple] = []
                for addr, seq in list(self._subscribers.items()):
                    try:
                        self._transport.sendto(_make_packet(MSG_DATA, seq, payload), addr)
                        self._subscribers[addr] = seq + 1
                    except Exception:
                        dead.append(addr)
                for addr in dead:
                    self._subscribers.pop(addr, None)
            await asyncio.sleep(PUSH_INTERVAL)

    def error_received(self, exc: Exception) -> None:
        pass

    def connection_lost(self, exc: Exception | None) -> None:
        if self._push_task:
            self._push_task.cancel()


class SensorCmdPort(asyncio.DatagramProtocol):
    """Receives Command / StreamStart packets, decodes protobuf, sends CommandAck."""

    def __init__(self, sensor_id: str) -> None:
        self._sensor_id = sensor_id
        self._transport: asyncio.DatagramTransport | None = None

    def connection_made(self, transport: asyncio.DatagramTransport) -> None:  # type: ignore[override]
        self._transport = transport

    def datagram_received(self, data: bytes, addr: tuple) -> None:
        if len(data) < 4:
            return
        _, msg_type, seq = struct.unpack("<BBH", data[:4])
        payload = data[4:]

        if msg_type in (MSG_COMMAND, MSG_STREAM_START):
            cmd = _decode_command(self._sensor_id, payload)
            tag = "StreamStart" if msg_type == MSG_STREAM_START else "Command"
            print(f"[UDP] {self._sensor_id} {tag} from {addr[0]}:{addr[1]}: {cmd}", flush=True)
            if self._transport:
                ack_payload = json.dumps({"status": "ok", "sensor": self._sensor_id}).encode()
                self._transport.sendto(_make_packet(MSG_CMD_ACK, seq, ack_payload), addr)
        elif msg_type == MSG_STREAM_STOP:
            print(f"[UDP] {self._sensor_id} StreamStop from {addr[0]}:{addr[1]}", flush=True)

    def error_received(self, exc: Exception) -> None:
        pass

    def connection_lost(self, exc: Exception | None) -> None:
        pass

# ---------------------------------------------------------------------------
# Sensor data generators (return JSON bytes for UDP push)
# ---------------------------------------------------------------------------

_START = time.monotonic()


def _t() -> float:
    return time.monotonic() - _START


def _sin(period: float, phase: float = 0.0) -> float:
    return math.sin(2 * math.pi * _t() / period + phase)


def _noise(scale: float, freq: float, phase: float = 0.0) -> float:
    t = _t()
    return scale * (
        0.50 * math.sin(2 * math.pi * t * freq + phase)
        + 0.30 * math.sin(2 * math.pi * t * freq * 1.618 + phase * 1.3)
        + 0.20 * math.sin(2 * math.pi * t * freq * 2.718 + phase * 0.7)
    )


_LEFT_NODES: frozenset[int] = frozenset({32, 33})
_RIGHT_NODES: frozenset[int] = frozenset({31, 34})
_ALL_NODES: frozenset[int] = _LEFT_NODES | _RIGHT_NODES

_LEADER_FOLLOWER: dict[int, int] = {32: 33, 34: 31}
_FOLLOWER_LEADER: dict[int, int] = {v: k for k, v in _LEADER_FOLLOWER.items()}


def _odrive_data_dict(nid: int) -> dict:
    sign = 1 if nid in _LEFT_NODES else -1
    vel     = sign * 2.5 * _sin(4.0)
    iq      = vel * 0.5
    motor_t = 45.0 + _noise(8.0, 0.012, phase=float(nid))
    fet_t   = 36.0 + _noise(5.0, 0.015, phase=float(nid) + 1.0)
    bus_v   = 48.0 + _noise(0.4, 0.08,  phase=float(nid) + 2.0)
    bus_i   = abs(vel) * 1.8 + _noise(0.1, 0.3, phase=float(nid))
    return {
        "node_id":          nid,
        "axis_state":       8,
        "axis_error":       0,
        "active_errors":    0,
        "disarm_reason":    0,
        "procedure_result": 0,
        "trajectory_done":  True,
        "pos_estimate":     round(math.sin(2 * math.pi * _t() / 8.0) * 0.25, 4),
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
    }


def _odrive_data_bytes(nid: int) -> bytes:
    """HTTP endpoint — always JSON."""
    return json.dumps(_odrive_data_dict(nid)).encode()


def _odrive_udp_bytes(nid: int) -> bytes:
    """UDP push — protobuf when available, JSON fallback."""
    if _PROTO_OK:
        d = _odrive_data_dict(nid)
        msg = DriveNodeState_pb2.DriveNodeState()
        msg.node_id       = d["node_id"]
        msg.node_state    = d["axis_state"]
        msg.node_temp_c   = d["fet_temp"]
        msg.motor_temp_c  = d["motor_temp"]
        msg.motor_amp     = d["iq_measured"]
        msg.active_errors = d["active_errors"]
        msg.latched_errors = 0
        msg.motor_pos     = d["pos_estimate"]
        return msg.SerializeToString()
    return _odrive_data_bytes(nid)


def _vn300_data_dict() -> dict:
    t_gps = _t()
    return {
        # Position
        "latitude":           round(45.5017  + 0.0001 * _sin(80.0),         8),
        "longitude":          round(-73.5673 + 0.0001 * _sin(80.0, 1.57),   8),
        "altitude":           round(12.5     + 0.15   * _sin(60.0),          2),
        # Attitude
        "yaw":                round(45.0 + 5.0 * _sin(30.0),                 2),
        "pitch":              round(_noise(2.0, 0.05),                        2),
        "roll":               round(_noise(1.5, 0.07, 1.0),                   2),
        # Velocity
        "vel_north":          round(0.3  * _sin(12.0),          3),
        "vel_east":           round(0.2  * _sin(12.0, 0.8),     3),
        "vel_down":           round(0.01 * _sin(20.0),          3),
        # IMU
        "accel_x":            round(_noise(0.3, 0.5),            3),
        "accel_y":            round(_noise(0.2, 0.6, 1.0),       3),
        "accel_z":            round(9.81 + _noise(0.05, 0.3),    3),
        "gyro_x":             round(_noise(0.02, 1.0),            4),
        "gyro_y":             round(_noise(0.015, 1.2, 0.5),      4),
        "gyro_z":             round(_noise(0.01, 0.8, 1.0),       4),
        # Magnetometer
        "mag_x":              round(_noise(0.05, 0.1),            4),
        "mag_y":              round(_noise(0.04, 0.12, 0.5),      4),
        "mag_z":              round(-0.35 + _noise(0.02, 0.08),   4),
        # GNSS
        "gnss_fix":           True,
        "gnss_fix_type":      3,
        "gnss_num_sats":      9,
        "gnss_compass_active": True,
        "gnss_heading_aiding": True,
        "gps_week":           int(t_gps / 604800) + 2300,
        "gps_tow":            round(t_gps % 604800, 3),
        # INS status
        "ins_mode":           2,
        "ins_error":          0,
        "ins_status_raw":     0x0002,
        "last_async_header":  "VNYIA",
        # Uncertainties
        "att_uncertainty":    round(0.5 + _noise(0.1, 0.02),  2),
        "pos_uncertainty":    round(1.2 + _noise(0.2, 0.03),  2),
        "vel_uncertainty":    round(0.1 + _noise(0.02, 0.04), 2),
        # Environment
        "pressure":           round(101.325 + _noise(0.05, 0.01), 3),
        "temperature":        round(22.0 + _noise(0.5, 0.005),    1),
        # Port / diagnostics
        "port":               "/dev/ttyUSB_VN300",
        "messages_parsed":    int(_t() * 40),
        "messages_dropped":   0,
        "timestamp_ns":       time.time_ns(),
    }


def _vn300_data_bytes() -> bytes:
    """HTTP endpoint — always JSON."""
    return json.dumps(_vn300_data_dict()).encode()


def _vn300_udp_bytes() -> bytes:
    """UDP push — protobuf when available, JSON fallback."""
    if _PROTO_OK:
        d = _vn300_data_dict()
        msg = Vn300_pb2.Vn300()
        msg.position.lat      = d["latitude"]
        msg.position.lon      = d["longitude"]
        msg.position.alt      = d["altitude"]
        msg.orientation.yaw   = d["yaw"]
        msg.orientation.pitch = d["pitch"]
        msg.orientation.roll  = d["roll"]
        msg.velocity.x        = d["vel_north"]
        msg.velocity.y        = d["vel_east"]
        msg.velocity.z        = d["vel_down"]
        msg.accel.x           = d["accel_x"]
        msg.accel.y           = d["accel_y"]
        msg.accel.z           = d["accel_z"]
        msg.gyro.x            = d["gyro_x"]
        msg.gyro.y            = d["gyro_y"]
        msg.gyro.z            = d["gyro_z"]
        return msg.SerializeToString()
    return _vn300_data_bytes()


def _kinova_data_dict() -> dict:
    joints = {}
    for i in range(1, 7):
        phase = (i - 1) * math.pi / 3
        joints[f"joint_{i}_pos"]     = round(_sin(8.0, phase) * 45.0, 3)
        joints[f"joint_{i}_vel"]     = round(_sin(4.0, phase) * 10.0, 3)
        joints[f"joint_{i}_torque"]  = round(_noise(2.0, 0.3, float(i)), 3)
        joints[f"joint_{i}_temp"]    = round(35.0 + _noise(5.0, 0.02, float(i)), 2)
        joints[f"joint_{i}_current"] = round(abs(_sin(4.0, phase)) * 2.5 + _noise(0.1, 0.5, float(i)), 3)
    return {
        **joints,
        "accel_x":               round(_noise(0.1, 0.4),           3),
        "accel_y":               round(_noise(0.08, 0.5, 1.0),     3),
        "accel_z":               round(9.81 + _noise(0.03, 0.3),   3),
        "control_enabled":       True,
        "estopped":              False,
        "retract_state":         0,
        "robot_type":            1,
        "torque_sensors_available": True,
        "bus_voltage":           round(24.0 + _noise(0.2, 0.05), 2),
        "bus_current":           round(2.5  + _noise(0.3, 0.2),  3),
        "timestamp_ns":          time.time_ns(),
    }


def _kinova_data_bytes() -> bytes:
    return json.dumps(_kinova_data_dict()).encode()


# ---------------------------------------------------------------------------
# Sensor configuration
# ---------------------------------------------------------------------------

@dataclass
class _SensorConf:
    id: str
    display_name: str
    data_port: int
    cmd_port: int
    data_gen: Callable[[], bytes]
    command_mode: str = "Rest"       # "Rest" or "Stream"
    stream_interval_ms: int = 250


_SENSORS: list[_SensorConf] = [
    _SensorConf(
        id="vectornav_ttyUSB_VN300",
        display_name="VectorNav VN-300 (/dev/ttyUSB_VN300)",
        data_port=5000, cmd_port=5001,
        data_gen=_vn300_udp_bytes,
        command_mode="Rest",
    ),
    _SensorConf(
        id="kinova_arm",
        display_name="Kinova Gen2 6DOF (Custom Spherical)",
        data_port=5002, cmd_port=5003,
        data_gen=_kinova_data_bytes,
        command_mode="Stream", stream_interval_ms=100,
    ),
    _SensorConf(
        id="odrive_34",
        display_name="ODrive Node 34",
        data_port=5004, cmd_port=5005,
        data_gen=lambda: _odrive_udp_bytes(34),
        command_mode="Stream",
    ),
    _SensorConf(
        id="odrive_31",
        display_name="ODrive Node 31",
        data_port=5006, cmd_port=5007,
        data_gen=lambda: _odrive_udp_bytes(31),
        command_mode="Stream",
    ),
    _SensorConf(
        id="odrive_33",
        display_name="ODrive Node 33",
        data_port=5008, cmd_port=5009,
        data_gen=lambda: _odrive_udp_bytes(33),
        command_mode="Stream",
    ),
    _SensorConf(
        id="odrive_32",
        display_name="ODrive Node 32",
        data_port=5010, cmd_port=5011,
        data_gen=lambda: _odrive_udp_bytes(32),
        command_mode="Stream",
    ),
]

_SENSOR_MAP: dict[str, _SensorConf] = {s.id: s for s in _SENSORS}
_ODRIVE_NODES = [s for s in _SENSORS if s.id.startswith("odrive_")]

# ---------------------------------------------------------------------------
# FastAPI app + UDP lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    loop = asyncio.get_running_loop()
    transports: list[asyncio.BaseTransport] = []

    for s in _SENSORS:
        for port, factory in [
            (s.data_port, lambda _s=s: SensorDataPort(_s.id, _s.data_gen)),
            (s.cmd_port,  lambda _s=s: SensorCmdPort(_s.id)),
        ]:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("0.0.0.0", port))
            transport, _ = await loop.create_datagram_endpoint(factory, sock=sock)
            transports.append(transport)

        label = "Stream" if s.command_mode == "Stream" else "REST"
        print(
            f"[UDP] {s.id} ({label}) — data:{s.data_port}  cmd:{s.cmd_port}",
            flush=True,
        )

    yield

    for t in transports:
        t.close()


app = FastAPI(title="Rove Mock Server", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# /discover  (matches DiscoverResponse schema from API spec)
# ---------------------------------------------------------------------------

@app.get("/discover", summary="List all available sensors")
def discover() -> dict:
    sensors = []
    for s in _SENSORS:
        mode: dict
        if s.command_mode == "Stream":
            mode = {"type": "Stream", "interval_ms": s.stream_interval_ms}
        else:
            mode = {"type": "Rest"}
        sensors.append({
            "id":           s.id,
            "display_name": s.display_name,
            "command_mode": mode,
            "data_port":    s.data_port,
            "command_port": s.cmd_port,
            "endpoints": {
                "info":     f"/{s.id}/info",
                "data":     f"/{s.id}/data",
                "command":  f"/{s.id}/command",
                "estop":     f"/{s.id}/estop" if s.command_mode == "Stream" else None,
                "calibrate": f"/{s.id}/calibrate" if s.id.startswith(("odrive", "kinova")) else None,
                "config":    f"/{s.id}/config"    if s.id.startswith("odrive") else None,
                "endpoints": f"/{s.id}/endpoints" if s.id.startswith("odrive") else None,
            },
        })
    return {"sensors": sensors}


# ---------------------------------------------------------------------------
# Field schemas  (FieldDescriptor per API spec)
# ---------------------------------------------------------------------------

def _fd(name: str, desc: str, type_name: str, unit: str | None = None) -> dict:
    d: dict = {"name": name, "description": desc, "type_name": type_name}
    if unit:
        d["unit"] = unit
    return d


_ODRIVE_DATA_SCHEMA = [
    _fd("node_id",          "CAN node ID",                    "u32"),
    _fd("axis_state",       "Axis state (8=ClosedLoop)",       "u32"),
    _fd("axis_error",       "Axis error flags",               "u32"),
    _fd("active_errors",    "Active error bitmask",           "u32"),
    _fd("disarm_reason",    "Reason motor was disarmed",       "u32"),
    _fd("procedure_result", "Result of last procedure",       "u32"),
    _fd("trajectory_done",  "Trajectory completed",           "bool"),
    _fd("pos_estimate",     "Position estimate",              "f64", "turns"),
    _fd("vel_estimate",     "Velocity estimate",              "f64", "turns/s"),
    _fd("iq_setpoint",      "Current setpoint (q-axis)",      "f64", "A"),
    _fd("iq_measured",      "Measured current (q-axis)",      "f64", "A"),
    _fd("motor_temp",       "Motor temperature",              "f64", "°C"),
    _fd("fet_temp",         "FET temperature",                "f64", "°C"),
    _fd("bus_voltage",      "DC bus voltage",                 "f64", "V"),
    _fd("bus_current",      "DC bus current",                 "f64", "A"),
    _fd("electrical_power", "Electrical power",               "f64", "W"),
    _fd("mechanical_power", "Mechanical power",               "f64", "W"),
    _fd("torque_estimate",  "Torque estimate",                "f64", "N·m"),
    _fd("torque_target",    "Torque target",                  "f64", "N·m"),
    _fd("count_cpr",        "Encoder count (CPR)",            "i32"),
    _fd("shadow_count",     "Shadow encoder count",           "i32"),
    _fd("timestamp_ns",     "Packet timestamp",               "i64", "ns"),
]

_ODRIVE_CMD_SCHEMA = [
    _fd("axis_state",          "Target axis state",              "u32"),
    _fd("control_mode",        "Control mode (1=torque 2=vel 3=pos)", "u32"),
    _fd("input_mode",          "Input mode",                     "u32"),
    _fd("input_pos",           "Position setpoint",              "f64", "turns"),
    _fd("input_vel",           "Velocity setpoint",              "f64", "turns/s"),
    _fd("input_torque",        "Torque setpoint",                "f64", "N·m"),
    _fd("input_vel_ff",        "Velocity feed-forward",          "f64", "turns/s"),
    _fd("input_torque_ff",     "Torque feed-forward",            "f64", "N·m"),
    _fd("vel_gain",            "Velocity gain",                  "f64"),
    _fd("vel_integrator_gain", "Velocity integrator gain",       "f64"),
    _fd("pos_gain",            "Position gain",                  "f64"),
    _fd("velocity_limit",      "Velocity limit",                 "f64", "turns/s"),
    _fd("current_limit",       "Current limit",                  "f64", "A"),
    _fd("traj_vel_limit",      "Trajectory velocity limit",      "f64", "turns/s"),
    _fd("traj_accel_limit",    "Trajectory acceleration limit",  "f64", "turns/s²"),
    _fd("traj_decel_limit",    "Trajectory deceleration limit",  "f64", "turns/s²"),
    _fd("traj_inertia",        "Trajectory inertia",             "f64"),
    _fd("clear_errors",        "Clear axis errors",              "bool"),
    _fd("reboot",              "Reboot the controller",          "bool"),
]

_VN300_DATA_SCHEMA = [
    _fd("latitude",            "Latitude",                       "f64", "degrees"),
    _fd("longitude",           "Longitude",                      "f64", "degrees"),
    _fd("altitude",            "Altitude (MSL)",                 "f64", "m"),
    _fd("yaw",                 "Yaw (heading)",                  "f64", "degrees"),
    _fd("pitch",               "Pitch",                          "f64", "degrees"),
    _fd("roll",                "Roll",                           "f64", "degrees"),
    _fd("vel_north",           "Velocity North",                 "f64", "m/s"),
    _fd("vel_east",            "Velocity East",                  "f64", "m/s"),
    _fd("vel_down",            "Velocity Down",                  "f64", "m/s"),
    _fd("accel_x",             "Acceleration X",                 "f64", "m/s²"),
    _fd("accel_y",             "Acceleration Y",                 "f64", "m/s²"),
    _fd("accel_z",             "Acceleration Z",                 "f64", "m/s²"),
    _fd("gyro_x",              "Angular rate X",                 "f64", "rad/s"),
    _fd("gyro_y",              "Angular rate Y",                 "f64", "rad/s"),
    _fd("gyro_z",              "Angular rate Z",                 "f64", "rad/s"),
    _fd("mag_x",               "Magnetic field X",               "f64", "Gauss"),
    _fd("mag_y",               "Magnetic field Y",               "f64", "Gauss"),
    _fd("mag_z",               "Magnetic field Z",               "f64", "Gauss"),
    _fd("gnss_fix",            "GNSS fix acquired",              "bool"),
    _fd("gnss_fix_type",       "GNSS fix type (3=3D)",           "u32"),
    _fd("gnss_num_sats",       "Number of GNSS satellites",      "u32"),
    _fd("gnss_compass_active", "Dual-antenna compass active",    "bool"),
    _fd("gnss_heading_aiding", "GNSS heading aiding active",     "bool"),
    _fd("gps_week",            "GPS week number",                "u32"),
    _fd("gps_tow",             "GPS time of week",               "f64", "s"),
    _fd("ins_mode",            "INS mode",                       "u32"),
    _fd("ins_error",           "INS error flags",                "u32"),
    _fd("ins_status_raw",      "Raw INS status word",            "u32"),
    _fd("last_async_header",   "Last async output header",       "String"),
    _fd("att_uncertainty",     "Attitude uncertainty (1σ)",      "f64", "degrees"),
    _fd("pos_uncertainty",     "Position uncertainty (1σ)",      "f64", "m"),
    _fd("vel_uncertainty",     "Velocity uncertainty (1σ)",      "f64", "m/s"),
    _fd("pressure",            "Barometric pressure",            "f64", "kPa"),
    _fd("temperature",         "Temperature",                    "f64", "°C"),
    _fd("port",                "Serial port path",               "String"),
    _fd("messages_parsed",     "Total messages parsed",          "u64"),
    _fd("messages_dropped",    "Total messages dropped",         "u64"),
    _fd("timestamp_ns",        "Packet timestamp",               "i64", "ns"),
]

_VN300_CMD_SCHEMA = [
    _fd("reset",                   "Reset the sensor",                   "bool"),
    _fd("tare",                    "Tare (zero) orientation",            "bool"),
    _fd("restore_factory_settings","Restore factory settings",           "bool"),
    _fd("write_settings",          "Persist settings to flash",          "bool"),
    _fd("set_initial_heading",     "Set initial heading",                "f64", "degrees"),
    _fd("set_async_type",          "Set async output message type",      "u32"),
    _fd("set_async_freq",          "Set async output frequency",         "u32", "Hz"),
    _fd("raw",                     "Raw NMEA command string",            "String"),
]

_KINOVA_DATA_SCHEMA = [
    _fd("accel_x",               "Acceleration X",                "f64", "m/s²"),
    _fd("accel_y",               "Acceleration Y",                "f64", "m/s²"),
    _fd("accel_z",               "Acceleration Z",                "f64", "m/s²"),
    _fd("bus_voltage",           "Bus voltage",                   "f64", "V"),
    _fd("bus_current",           "Bus current",                   "f64", "A"),
    _fd("control_enabled",       "Control loop active",           "bool"),
    _fd("estopped",              "Emergency stop active",         "bool"),
    _fd("retract_state",         "Retract sequence state",        "u32"),
    _fd("robot_type",            "Robot type identifier",         "u32"),
    _fd("torque_sensors_available", "Torque sensors present",     "bool"),
    _fd("timestamp_ns",          "Packet timestamp",              "i64", "ns"),
] + [
    field
    for i in range(1, 7)
    for field in [
        _fd(f"joint_{i}_pos",     f"Joint {i} position",         "f64", "degrees"),
        _fd(f"joint_{i}_vel",     f"Joint {i} velocity",         "f64", "degrees/s"),
        _fd(f"joint_{i}_torque",  f"Joint {i} torque",           "f64", "N·m"),
        _fd(f"joint_{i}_temp",    f"Joint {i} temperature",      "f64", "°C"),
        _fd(f"joint_{i}_current", f"Joint {i} current",          "f64", "A"),
    ]
]

_KINOVA_CMD_SCHEMA = [
    _fd("control_mode",       "Control mode string",            "String"),
    _fd("start_control",      "Start control loop",             "bool"),
    _fd("clear_errors",       "Clear error flags",              "bool"),
    _fd("move_home",          "Move to home position",          "bool"),
    _fd("erase_trajectories", "Erase trajectory queue",         "bool"),
] + [
    field
    for i in range(1, 7)
    for field in [
        _fd(f"joint_{i}_pos", f"Joint {i} position setpoint",  "f64", "degrees"),
        _fd(f"joint_{i}_vel", f"Joint {i} velocity setpoint",  "f64", "degrees/s"),
    ]
]

_SCHEMAS: dict[str, tuple[list, list]] = {
    "vectornav_ttyUSB_VN300": (_VN300_DATA_SCHEMA,   _VN300_CMD_SCHEMA),
    "kinova_arm":             (_KINOVA_DATA_SCHEMA,  _KINOVA_CMD_SCHEMA),
}
for _nid in _ALL_NODES:
    _SCHEMAS[f"odrive_{_nid}"] = (_ODRIVE_DATA_SCHEMA, _ODRIVE_CMD_SCHEMA)


# ---------------------------------------------------------------------------
# Generic /info helper
# ---------------------------------------------------------------------------

def _sensor_info(s: _SensorConf) -> dict:
    mode: dict
    if s.command_mode == "Stream":
        mode = {"type": "Stream", "interval_ms": s.stream_interval_ms}
    else:
        mode = {"type": "Rest"}
    data_schema, cmd_schema = _SCHEMAS.get(s.id, ([], []))
    return {
        "id":             s.id,
        "display_name":   s.display_name,
        "command_mode":   mode,
        "data_port":      s.data_port,
        "command_port":   s.cmd_port,
        "data_schema":    data_schema,
        "command_schema": cmd_schema,
        "udp_protocol": {
            "header_format": "version(1B) | msg_type(1B) | seq_num(2B LE) | payload",
            "data_subscription": {
                "description": "Send Subscribe to data_port; server pushes Data packets at 20 Hz",
                "flow":        "client→Subscribe(0x01) → server pushes Data(0x03) → client→Unsubscribe(0x02)",
                "subscribe_packet":   {"name": "Subscribe",   "header_hex": "01 01 00 00", "description": "4-byte header, no payload"},
                "unsubscribe_packet": {"name": "Unsubscribe", "header_hex": "01 02 00 00", "description": "4-byte header, no payload"},
                "data_push_packet":   {"name": "Data",        "header_hex": "01 03 XX XX", "description": "4-byte header + JSON payload"},
            },
            "command_protocol": {
                "description": "Send Command or StreamStart on cmd_port; server acks with CommandAck",
                "flow":        "client→Command(0x10) or StreamStart(0x12) → server→CommandAck(0x11)",
                "packets": [
                    {"name": "Command",     "header_hex": "01 10 XX XX", "description": "4-byte header + JSON or RoveControl protobuf"},
                    {"name": "StreamStart", "header_hex": "01 12 XX XX", "description": "4-byte header + JSON or RoveControl protobuf"},
                    {"name": "StreamStop",  "header_hex": "01 13 XX XX", "description": "4-byte header, no payload"},
                    {"name": "CommandAck",  "header_hex": "01 11 XX XX", "description": "4-byte header + {status: ok}"},
                ],
            },
        },
    }


# ---------------------------------------------------------------------------
# ODrive routes  (nid: 31-34)
# ---------------------------------------------------------------------------

@app.get("/odrive_{nid}/info", tags=["odrive"])
def odrive_info(nid: int) -> Response:
    sid = f"odrive_{nid}"
    if sid not in _SENSOR_MAP:
        return Response(status_code=404)
    return Response(content=json.dumps(_sensor_info(_SENSOR_MAP[sid])), media_type="application/json")


@app.get("/odrive_{nid}/data", summary="ODrive node telemetry")
def odrive_data(nid: int) -> Response:
    if nid not in _ALL_NODES:
        return Response(status_code=404)
    return Response(content=_odrive_data_bytes(nid), media_type="application/json")


@app.post("/odrive_{nid}/command", summary="Send command to ODrive node")
async def odrive_command(nid: int, body: dict) -> dict:
    return {"status": "ok", "result": f"Command accepted by odrive_{nid}"}


@app.post("/odrive_{nid}/estop", summary="E-stop ODrive node")
async def odrive_estop(nid: int) -> dict:
    return {"status": "ok", "result": f"ESTOP sent to odrive_{nid}"}


@app.post("/odrive_{nid}/calibrate", summary="Start calibration on ODrive node")
async def odrive_calibrate(nid: int, body: dict) -> dict:
    cal_type = body.get("type", "full")
    return {"status": "ok", "result": f"Calibration '{cal_type}' started on odrive_{nid}"}


@app.get("/odrive_{nid}/config", summary="Read ODrive config")
async def odrive_config_read(nid: int) -> dict:
    return {"phase_resistance": 0.15, "phase_inductance": 0.0002, "current_lim": 40.0,
            "vel_limit": 20.0, "pole_pairs": 7, "cpr": 8192}


@app.post("/odrive_{nid}/config", summary="Write ODrive config")
async def odrive_config_write(nid: int, body: dict) -> dict:
    return {"status": "ok", "result": body}


@app.get("/odrive_{nid}/endpoints", summary="List ODrive endpoints")
async def odrive_endpoints(nid: int) -> dict:
    return {"axis0.controller.config.vel_limit": {"id": 456, "type": "float", "access": "rw"}}


@app.get("/odrive_{nid}/endpoint/{path:path}", summary="Read ODrive endpoint")
async def odrive_endpoint_read(nid: int, path: str) -> dict:
    return {"path": path, "value": 0.0, "type": "float"}


@app.post("/odrive_{nid}/endpoint/{path:path}", summary="Write ODrive endpoint")
async def odrive_endpoint_write(nid: int, path: str, body: dict) -> dict:
    return {"path": path, "written": True}


# ---------------------------------------------------------------------------
# VectorNav VN-300 routes
# ---------------------------------------------------------------------------

@app.get("/vectornav_ttyUSB_VN300/info")
def vn300_info() -> Response:
    return Response(
        content=json.dumps(_sensor_info(_SENSOR_MAP["vectornav_ttyUSB_VN300"])),
        media_type="application/json",
    )


@app.get("/vectornav_ttyUSB_VN300/data")
def vn300_data() -> Response:
    return Response(content=_vn300_data_bytes(), media_type="application/json")


@app.post("/vectornav_ttyUSB_VN300/command")
async def vn300_command(body: dict) -> dict:
    return {"status": "ok", "result": "VN300 command accepted"}


# ---------------------------------------------------------------------------
# Kinova arm routes
# ---------------------------------------------------------------------------

@app.get("/kinova_arm/info")
def kinova_info() -> Response:
    return Response(
        content=json.dumps(_sensor_info(_SENSOR_MAP["kinova_arm"])),
        media_type="application/json",
    )


@app.get("/kinova_arm/data")
def kinova_data() -> Response:
    return Response(content=_kinova_data_bytes(), media_type="application/json")


@app.post("/kinova_arm/command")
async def kinova_command(body: dict) -> dict:
    return {"status": "ok", "result": "Kinova command accepted"}


@app.post("/kinova_arm/estop")
async def kinova_estop() -> dict:
    return {"status": "ok", "result": "Kinova ESTOP sent"}


@app.post("/kinova_arm/calibrate")
async def kinova_calibrate(body: dict) -> dict:
    return {"status": "ok", "result": f"Kinova calibration '{body.get('type', 'full')}' started"}


# ---------------------------------------------------------------------------
# ODrive global endpoint map upload
# ---------------------------------------------------------------------------

@app.post("/odrive/endpoints", summary="Upload flat_endpoints.json")
async def odrive_upload_endpoints(body: dict) -> dict:
    count = len(body.get("endpoints", {}))
    return {"status": "ok", "loaded": count}


# ---------------------------------------------------------------------------
# Track / flipper joints  (legacy HTTP polling)
# ---------------------------------------------------------------------------

_TRACK_CFG: dict[str, dict] = {
    "track_fl_j": {"sign":  1.0, "phase": 0.00},
    "track_rl_j": {"sign":  1.0, "phase": 0.05},
    "track_fr_j": {"sign": -1.0, "phase": 0.00},
    "track_rr_j": {"sign": -1.0, "phase": 0.05},
}

_FLIPPER_JOINTS = ["flipper_fl_j", "flipper_rl_j", "flipper_fr_j", "flipper_rr_j"]
_FLIPPER_PHASES = [0.0, math.pi / 2, math.pi, 3 * math.pi / 2]
_AMPLITUDE = 0.8
_PERIOD    = 4.0


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


@app.get("/flipper_joints", summary="Flipper joint positions (sinusoidal)")
def flipper_joints() -> dict:
    omega = 2 * math.pi / _PERIOD
    return {
        joint: {"position": round(_AMPLITUDE * math.sin(omega * _t() + phase), 6)}
        for joint, phase in zip(_FLIPPER_JOINTS, _FLIPPER_PHASES)
    }


# ---------------------------------------------------------------------------
# Costmap
# ---------------------------------------------------------------------------

_MAP_CELLS = 50
_MAP_SCALE = 6


@app.get("/map_feed", summary="50×50 costmap bitmap (PNG)")
def map_feed() -> Response:
    t   = _t()
    img = Image.new("L", (_MAP_CELLS, _MAP_CELLS), 0)
    pix = img.load()

    for x in range(_MAP_CELLS):
        pix[x, 0] = pix[x, _MAP_CELLS - 1] = 210
    for y in range(_MAP_CELLS):
        pix[0, y] = pix[_MAP_CELLS - 1, y] = 210

    for x in range(10, 40):
        pix[x, 20] = 200
    for y in range(5, 20):
        pix[25, y] = 200

    ox = int(25 + 12 * math.sin(t * 0.22))
    oy = int(25 + 10 * math.cos(t * 0.17))
    for dx in range(-3, 4):
        for dy in range(-3, 4):
            x, y = ox + dx, oy + dy
            if 1 <= x < _MAP_CELLS - 1 and 1 <= y < _MAP_CELLS - 1:
                pix[x, y] = 180

    ox2 = int(15 + 8 * math.cos(t * 0.28 + 1.5))
    oy2 = int(35 + 7 * math.sin(t * 0.19 + 0.8))
    for dx in range(-2, 3):
        for dy in range(-2, 3):
            x, y = ox2 + dx, oy2 + dy
            if 1 <= x < _MAP_CELLS - 1 and 1 <= y < _MAP_CELLS - 1:
                pix[x, y] = 160

    rx = int(25 + 4 * math.sin(t * 0.07))
    ry = int(25 + 4 * math.cos(t * 0.09))
    for dx in range(-1, 2):
        for dy in range(-1, 2):
            x, y = rx + dx, ry + dy
            if 0 <= x < _MAP_CELLS and 0 <= y < _MAP_CELLS:
                pix[x, y] = 255

    img = img.resize((_MAP_CELLS * _MAP_SCALE, _MAP_CELLS * _MAP_SCALE), Image.NEAREST)
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=False)
    return Response(
        content=buf.getvalue(),
        media_type="image/png",
        headers={"Cache-Control": "no-cache, no-store"},
    )


# ---------------------------------------------------------------------------
# GNSS / Battery / Signals
# ---------------------------------------------------------------------------

@app.get("/gnss", summary="GNSS position (lat/lon/alt)")
def gnss() -> dict:
    return _vn300_data_dict()


@app.get("/battery", summary="Battery status")
def battery() -> dict:
    _BATTERY_START_PCT = 85.0
    _DRAIN_PCT_PER_S   = 0.5 / 60
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


@app.get("/signals", summary="Radio signal strengths")
def signals() -> dict:
    return {
        "signals": [
            {"name": "VTX",       "db": round(-65.0 + _noise(3.5, 0.09),      1), "quality": "good", "frequency_mhz": 5800},
            {"name": "Microhard", "db": round(-72.0 + _noise(4.0, 0.07, 1.2), 1), "quality": "fair", "frequency_mhz": 900},
        ],
        "timestamp_ns": time.time_ns(),
    }


# ---------------------------------------------------------------------------
# ArcRaven shims
# ---------------------------------------------------------------------------

@app.post("/api/estop")
def api_estop() -> dict:
    return {"success": True, "message": "ESTOP sent to all sensors (mock)"}


@app.get("/api/health")
def api_health() -> dict:
    return {
        "status": "ok",
        "sensor_count": len(_SENSORS),
        "active_subscriptions": 0,
        "sensors": {s.id: {"running": True, "last_data_ms_ago": 40} for s in _SENSORS},
    }


@app.get("/api/sensors")
def api_sensors() -> list:
    return [
        {
            "id":               s.id,
            "name":             s.id,
            "running":          True,
            "accepts_commands": True,
            "last_data_ms_ago": 40,
            "data_port":        s.data_port,
            "command_port":     s.cmd_port,
        }
        for s in _SENSORS
    ]
