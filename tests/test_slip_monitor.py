# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""Requires a live ROS2 environment (imports rclpy at module level) — same treatment
as test_scan_masker.py (see CLAUDE.md Gotchas): --ignore'd in stage-1-quality.
The detection logic itself is covered without ROS in test_scan_motion.py; this file
only proves the node's wiring: messages in -> verdict topics out.

Topics are overridden to /slip_test/... so the test can never hear (or be heard by) a
real or simulated /robot_001 running on this shared machine.
"""
import math
import time

import pytest
import rclpy
from nav_msgs.msg import Odometry
from sensor_msgs.msg import Imu, LaserScan
from std_msgs.msg import String

from nav_fleet.slip_monitor import SlipMonitor

N_RAYS = 360


@pytest.fixture(scope='module', autouse=True)
def ros_context():
    rclpy.init()
    yield
    rclpy.try_shutdown()


def _stamp(msg, t):
    msg.header.stamp.sec = int(t)
    msg.header.stamp.nanosec = int((t - int(t)) * 1e9)
    return msg


def _square_room_scan(t, half=2.0):
    """A lidar in the middle of a 4 x 4 m room that never moves."""
    msg = _stamp(LaserScan(), t)
    msg.angle_min, msg.angle_increment = 0.0, 2 * math.pi / N_RAYS
    msg.range_min, msg.range_max, msg.time_increment = 0.02, 12.0, 0.1 / N_RAYS
    msg.ranges = [half / max(abs(math.cos(i * msg.angle_increment)),
                             abs(math.sin(i * msg.angle_increment))) for i in range(N_RAYS)]
    return msg


def test_construction_declares_expected_defaults():
    node = SlipMonitor()
    try:
        assert node.get_parameter('scan_topic').value == '/robot_001/scan'
        assert node.get_parameter('odom_topic').value == '/robot_001/odom'
        assert node.get_parameter('imu_topic').value == '/robot_001/imu/data'
        assert node.get_parameter('output_prefix').value == '/robot_001/slip'
        assert node.get_parameter('lidar_x_m').value == pytest.approx(0.05)
        assert node.get_parameter('window_scans').value == 5
    finally:
        node.destroy_node()


def test_wheels_turning_in_a_room_that_does_not_move_publishes_slip():
    node = _make_test_node()
    received = []
    sub = node.create_subscription(String, '/slip_test/slip/status',
                                   lambda m: received.append(m.data), 10)
    try:
        # 2 s of data fed straight into the callbacks: wheels claim 0.25 m/s, gyro 0,
        # and the room stays exactly where it is.
        for tick in range(41):
            t = 100.0 + tick * 0.05
            odom = _stamp(Odometry(), t)
            odom.twist.twist.linear.x = 0.25
            node._odom_cb(odom)
            node._imu_cb(_stamp(Imu(), t))
            if tick % 2 == 0:
                node._scan_cb(_square_room_scan(t))
        deadline = time.monotonic() + 3.0
        while len(received) < 4 and time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.2)
        assert received[:3] == ['suspect', 'slip', 'slip']
        assert node.core.detector.phantom_distance_m > 0.2
    finally:
        node.destroy_subscription(sub)
        node.destroy_node()


class _TestSlipMonitor(SlipMonitor):
    """SlipMonitor on /slip_test/... topics."""

    def declare_parameter(self, name, value=None, *args, **kwargs):
        overrides = {'scan_topic': '/slip_test/scan', 'odom_topic': '/slip_test/odom',
                     'imu_topic': '/slip_test/imu', 'output_prefix': '/slip_test/slip'}
        return super().declare_parameter(name, overrides.get(name, value), *args, **kwargs)


def _make_test_node():
    return _TestSlipMonitor()
