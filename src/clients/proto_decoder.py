"""Decodes RoveTelemetry protobuf bytes into a flat {dot.topic: value} dict.

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
    from proto import RoveTelemetry_pb2 as _rt
    from google.protobuf.message import Message as _Message
    AVAILABLE = True
except ImportError:
    AVAILABLE = False


def decode(data: bytes) -> dict[str, Any]:
    """Parse RoveTelemetry bytes and return flat {dot.path: scalar} dict."""
    if not AVAILABLE:
        raise RuntimeError(
            "Proto stubs not generated. Run: bash scripts/generate_proto.sh"
        )
    msg = _rt.RoveTelemetry()
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
