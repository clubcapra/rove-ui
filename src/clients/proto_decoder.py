"""Decodes protobuf bytes into a flat {dot.path: value} dict.

Run scripts/generate_proto.sh first to generate the stubs in src/proto_gen/.
"""
from __future__ import annotations

import sys
import os
from typing import Any

_PROTO_GEN = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "src", "proto_gen")
)
if _PROTO_GEN not in sys.path:
    sys.path.insert(0, _PROTO_GEN)

try:
    from proto import RoveTelemetry_pb2, DriveNodeState_pb2, Battery_pb2
    from proto.imu import Vn300_pb2, Icm40609_pb2
    from google.protobuf.message import Message as _Message
    AVAILABLE = True
except ImportError:
    AVAILABLE = False

_TYPE_MAP: dict[str, Any] = {}
if AVAILABLE:
    _TYPE_MAP = {
        "RoveTelemetry":  RoveTelemetry_pb2.RoveTelemetry,
        "DriveNodeState": DriveNodeState_pb2.DriveNodeState,
        "Battery":        Battery_pb2.Battery,
        "Vn300":          Vn300_pb2.Vn300,
        "Icm40609":       Icm40609_pb2.Icm40609,
    }


def decode(data: bytes, proto_type: str = "RoveTelemetry") -> dict[str, Any]:
    """Parse protobuf bytes and return a flat {dot.path: scalar} dict.

    proto_type must match one of the registered message names.
    """
    if not AVAILABLE:
        raise RuntimeError(
            "Proto stubs not generated. Run: bash scripts/generate_proto.sh"
        )
    cls = _TYPE_MAP.get(proto_type)
    if cls is None:
        raise ValueError(f"Unknown proto_type '{proto_type}'. Known: {list(_TYPE_MAP)}")
    msg = cls()
    msg.ParseFromString(data)
    return _flatten(msg, "")


def _flatten(msg: Any, prefix: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for fd, value in msg.ListFields():
        key = f"{prefix}.{fd.name}" if prefix else fd.name
        if isinstance(value, _Message):
            result.update(_flatten(value, key))
        elif isinstance(value, (int, float, bool, str)):
            result[key] = value
    return result
