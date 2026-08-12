# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""Requires a live ROS2 environment (imports rclpy at module level) — same treatment
as test_esp32_driver.py (see CLAUDE.md Gotchas): --ignore'd in stage-1-quality.
No hardware boundary to mock here (pure pub/sub, no serial) — real rclpy pub/sub
end to end, matching test_esp32_driver.py's _publish_odom/_publish_imu tests.
"""
import math
import time

import pytest
import rclpy
from sensor_msgs.msg import LaserScan

from nav_fleet.scan_masker import ScanMasker


@pytest.fixture(scope='module', autouse=True)
def ros_context():
    rclpy.init()
    yield
    rclpy.try_shutdown()


def _make_scan(n=8, angle_min=0.0, angle_increment_deg=45.0, range_val=1.0):
    msg = LaserScan()
    msg.angle_min = angle_min
    msg.angle_increment = math.radians(angle_increment_deg)
    msg.ranges = [range_val] * n
    msg.intensities = [100.0] * n
    return msg


def test_construction_declares_expected_defaults():
    node = ScanMasker()
    try:
        assert node.get_parameter('input_topic').value == 'scan'
        assert node.get_parameter('output_topic').value == '/robot_001/scan'
        assert list(node.get_parameter('mask_sectors_deg').value) == [
            46.0, 123.0, 268.0, 277.0]
        assert node.get_parameter('output_frame_id').value == 'lidar_link'
    finally:
        node.destroy_node()


def test_republishes_masked_scan_with_expected_bearings_nanned():
    node = ScanMasker()
    received = []
    sub = node.create_subscription(
        LaserScan, '/robot_001/scan', lambda m: received.append(m), 10)
    pub = node.create_publisher(LaserScan, 'scan', 10)
    try:
        # 8 readings, 45deg apart: bearings 0,45,90,135,180,225,270,315.
        # Default sectors (46-123, 268-277) should NaN out index 2 (90) and index 6 (270).
        pub.publish(_make_scan())
        deadline = time.monotonic() + 3.0
        while len(received) < 1 and time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.5)
        assert len(received) == 1
        out = received[0].ranges
        assert out[0] == pytest.approx(1.0)
        assert out[1] == pytest.approx(1.0)
        assert math.isnan(out[2])
        assert out[3] == pytest.approx(1.0)
        assert out[4] == pytest.approx(1.0)
        assert out[5] == pytest.approx(1.0)
        assert math.isnan(out[6])
        assert out[7] == pytest.approx(1.0)
    finally:
        node.destroy_subscription(sub)
        node.destroy_node()


def test_republished_scan_also_masks_intensities():
    node = ScanMasker()
    received = []
    sub = node.create_subscription(
        LaserScan, '/robot_001/scan', lambda m: received.append(m), 10)
    pub = node.create_publisher(LaserScan, 'scan', 10)
    try:
        pub.publish(_make_scan())
        deadline = time.monotonic() + 3.0
        while len(received) < 1 and time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.5)
        assert len(received) == 1
        assert math.isnan(received[0].intensities[2])
        assert received[0].intensities[0] == pytest.approx(100.0)
    finally:
        node.destroy_subscription(sub)
        node.destroy_node()


def test_republished_scan_preserves_non_masked_fields():
    node = ScanMasker()
    received = []
    sub = node.create_subscription(
        LaserScan, '/robot_001/scan', lambda m: received.append(m), 10)
    pub = node.create_publisher(LaserScan, 'scan', 10)
    try:
        msg = _make_scan()
        msg.header.frame_id = 'base_laser'
        msg.range_min = 0.02
        msg.range_max = 12.0
        pub.publish(msg)
        deadline = time.monotonic() + 3.0
        while len(received) < 1 and time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.5)
        assert len(received) == 1
        assert received[0].range_min == pytest.approx(0.02)
        assert received[0].range_max == pytest.approx(12.0)
        assert received[0].angle_increment == pytest.approx(msg.angle_increment)
    finally:
        node.destroy_subscription(sub)
        node.destroy_node()


def test_republished_scan_rewrites_frame_id_to_match_urdf_not_vendor_default():
    # Real bug, found 2026-08-12: ldlidar_ros2's ld19.launch.py hardcodes
    # frame_id='base_laser' on the RAW scan, but ugv_pt.urdf.xacro's real link is
    # named 'lidar_link' — TF had no path connecting the two, so AMCL's
    # TF-synchronized scan subscription silently buffered every scan forever.
    # scan_masker must correct the frame_id on republish, not pass it through.
    node = ScanMasker()
    received = []
    sub = node.create_subscription(
        LaserScan, '/robot_001/scan', lambda m: received.append(m), 10)
    pub = node.create_publisher(LaserScan, 'scan', 10)
    try:
        msg = _make_scan()
        msg.header.frame_id = 'base_laser'  # the real vendor driver's actual value
        pub.publish(msg)
        deadline = time.monotonic() + 3.0
        while len(received) < 1 and time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.5)
        assert len(received) == 1
        assert received[0].header.frame_id == 'lidar_link'
    finally:
        node.destroy_subscription(sub)
        node.destroy_node()


def test_custom_output_frame_id_param_overrides_default():
    node = ScanMasker()
    node.set_parameters([rclpy.parameter.Parameter(
        'output_frame_id', value='custom_lidar_frame')])
    received = []
    sub = node.create_subscription(
        LaserScan, '/robot_001/scan', lambda m: received.append(m), 10)
    pub = node.create_publisher(LaserScan, 'scan', 10)
    try:
        msg = _make_scan()
        msg.header.frame_id = 'base_laser'
        pub.publish(msg)
        deadline = time.monotonic() + 3.0
        while len(received) < 1 and time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.5)
        assert len(received) == 1
        assert received[0].header.frame_id == 'custom_lidar_frame'
    finally:
        node.destroy_subscription(sub)
        node.destroy_node()


def test_custom_mask_sectors_param_overrides_default():
    node = ScanMasker()
    node.set_parameters([rclpy.parameter.Parameter(
        'mask_sectors_deg', value=[80.0, 100.0])])
    received = []
    sub = node.create_subscription(
        LaserScan, '/robot_001/scan', lambda m: received.append(m), 10)
    pub = node.create_publisher(LaserScan, 'scan', 10)
    try:
        pub.publish(_make_scan())  # bearings 0,45,90,135,180,225,270,315
        deadline = time.monotonic() + 3.0
        while len(received) < 1 and time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.5)
        assert len(received) == 1
        out = received[0].ranges
        assert math.isnan(out[2])       # 90 — inside the custom 80-100 sector
        assert out[6] == pytest.approx(1.0)  # 270 — the DEFAULT sector no longer applies
    finally:
        node.destroy_subscription(sub)
        node.destroy_node()
