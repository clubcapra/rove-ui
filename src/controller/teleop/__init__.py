"""Teleop controller pipeline (ported from capra_teleop_interface).

The protobuf-generated files use absolute imports rooted at this package
directory (e.g. ``from proto.core import RoveControl_pb2``), so we add
this directory to sys.path when the package is first imported.
"""
import os
import sys

_pkg_dir = os.path.dirname(__file__)
if _pkg_dir not in sys.path:
    sys.path.insert(0, _pkg_dir)
