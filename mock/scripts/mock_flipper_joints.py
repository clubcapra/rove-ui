#!/usr/bin/env python3
"""
Mock publisher for flipper joint positions.
Publishes DynamicJointState with sinusoidal angles to test the 3D viewer.

Usage:
    python3 scripts/mock_flipper_joints.py

Adjust JOINT_NAMES to match the actual joint names in your robot's URDF.
"""

import math
import time

try:
    import rclpy
    from rclpy.node import Node
    from control_msgs.msg import DynamicJointState, InterfaceValue
    from std_msgs.msg import Header
except ImportError as e:
    print(f"ERROR: ROS2 / control_msgs not available: {e}")
    raise SystemExit(1)

JOINT_NAMES = [
    "flipper_fl_j",
    "flipper_rl_j",
    "flipper_fr_j",
    "flipper_rr_j",
]

# Phase offset per joint so they don't all move in sync
PHASE_OFFSETS = [0.0, math.pi / 2, math.pi, 3 * math.pi / 2]

AMPLITUDE_RAD = 0.8   # ~45 degrees
PERIOD_S = 4.0        # full cycle duration
PUBLISH_RATE_HZ = 20


class MockFlipperPublisher(Node):
    def __init__(self):
        super().__init__("mock_flipper_joints")
        self._pub = self.create_publisher(DynamicJointState, "/dynamic_joint_states", 10)
        period = 1.0 / PUBLISH_RATE_HZ
        self._timer = self.create_timer(period, self._publish)
        self._start = time.monotonic()
        self.get_logger().info(
            f"Publishing flipper mock data on /dynamic_joint_states "
            f"at {PUBLISH_RATE_HZ} Hz  (joints: {JOINT_NAMES})"
        )

    def _publish(self):
        t = time.monotonic() - self._start
        omega = 2 * math.pi / PERIOD_S

        msg = DynamicJointState()
        msg.header = Header()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.joint_names = list(JOINT_NAMES)

        for phase in PHASE_OFFSETS:
            angle = AMPLITUDE_RAD * math.sin(omega * t + phase)
            iv = InterfaceValue()
            iv.interface_names = ["position"]
            iv.values = [angle]
            msg.interface_values.append(iv)

        self._pub.publish(msg)


def main():
    rclpy.init()
    node = MockFlipperPublisher()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
