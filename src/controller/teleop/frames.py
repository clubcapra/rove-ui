"""Helpers for inspecting / formatting / zeroing RoveControl frames.

Ported from the capra_teleop_interface reference (ui_server.zero_rove_control
and __main__._format_frame/_snapshot). Kept transport-agnostic so the
controller loop can use them for change detection, console logging, and the
E-stop zeroing path.
"""
from __future__ import annotations


def snapshot(msg) -> tuple:
    """Stable tuple of the meaningful command fields (excludes timestamp).

    Used for change detection: two frames are "the same command" when their
    snapshots match within an epsilon, regardless of the per-tick timestamp.
    """
    t = msg.tracks
    f = msg.flippers
    p = msg.ovis.position
    o = msg.ovis.orientation
    return (
        t.left_vel, t.right_vel,
        f.fl, f.fr, f.rl, f.rr,
        p.x, p.y, p.z,
        o.yaw, o.pitch, o.roll,
        int(msg.gripper.position),
    )


def snapshot_changed(a: tuple, b: tuple, eps: float = 0.02) -> bool:
    """True if any field differs by more than ``eps`` (ints compared exactly)."""
    for x, y in zip(a, b):
        if abs(x - y) > eps:
            return True
    return False


def format_frame(msg) -> str:
    """One-line human-readable rendering of a RoveControl frame."""
    t = msg.tracks
    f = msg.flippers
    p = msg.ovis.position
    o = msg.ovis.orientation
    return (
        f"tracks L={t.left_vel:+.2f} R={t.right_vel:+.2f} "
        f"flip {f.fl:+d}/{f.fr:+d}/{f.rl:+d}/{f.rr:+d} "
        f"twist xyz=({p.x:+.2f},{p.y:+.2f},{p.z:+.2f}) "
        f"ypr=({o.yaw:+.2f},{o.pitch:+.2f},{o.roll:+.2f}) "
        f"grip={msg.gripper.position}/255"
    )


def zero_rove_control(msg):
    """Zero all motion fields in place, leaving the gripper untouched.

    The gripper position is latched operator state (0=open..255=closed), not a
    velocity, so an E-stop must not snap it open. Everything else — tracks,
    all four flippers, and the full 6-DOF Ovis twist — is forced to zero so a
    streamed frame actively commands a halt.
    """
    msg.tracks.left_vel = 0.0
    msg.tracks.right_vel = 0.0
    msg.flippers.fl = 0
    msg.flippers.fr = 0
    msg.flippers.rl = 0
    msg.flippers.rr = 0
    msg.ovis.position.x = 0.0
    msg.ovis.position.y = 0.0
    msg.ovis.position.z = 0.0
    msg.ovis.orientation.yaw = 0.0
    msg.ovis.orientation.pitch = 0.0
    msg.ovis.orientation.roll = 0.0
    return msg
