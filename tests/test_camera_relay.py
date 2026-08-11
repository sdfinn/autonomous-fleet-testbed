# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""Requires a live ROS2 environment (imports rclpy at module level) — same treatment
as test_scan_masker.py (see CLAUDE.md Gotchas): --ignore'd in stage-1-quality.
Pure pub/sub, no hardware boundary to mock (no serial, unlike esp32_driver.py)."""
import time

import pytest
import rclpy
from sensor_msgs.msg import Image

from nav_fleet.camera_relay import CameraRelay


@pytest.fixture(scope='module', autouse=True)
def ros_context():
    rclpy.init()
    yield
    rclpy.try_shutdown()


def test_construction_declares_expected_defaults():
    node = CameraRelay()
    try:
        assert node.get_parameter('input_topic').value == '/oak/rgb/image_rect'
        assert node.get_parameter('output_topic').value == '/robot_001/camera/image_raw'
    finally:
        node.destroy_node()


def test_relays_image_unchanged_to_output_topic():
    node = CameraRelay()
    received = []
    sub = node.create_subscription(
        Image, '/robot_001/camera/image_raw', lambda m: received.append(m), 10)
    pub = node.create_publisher(Image, '/oak/rgb/image_rect', 10)
    try:
        msg = Image()
        msg.header.frame_id = 'oak_rgb_camera_optical_frame'
        msg.width = 640
        msg.height = 480
        msg.encoding = 'rgb8'
        msg.data = bytes([1, 2, 3, 4])
        pub.publish(msg)
        deadline = time.monotonic() + 3.0
        while len(received) < 1 and time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.5)
        assert len(received) == 1
        assert received[0].width == 640
        assert received[0].height == 480
        assert received[0].encoding == 'rgb8'
        assert bytes(received[0].data) == bytes([1, 2, 3, 4])
        assert received[0].header.frame_id == 'oak_rgb_camera_optical_frame'
    finally:
        node.destroy_subscription(sub)
        node.destroy_node()


def test_custom_topics_via_param_overrides():
    # Topics are wired once in __init__ (standard ROS2 pattern — no live
    # reconfiguration), so overriding them means passing parameter_overrides at
    # construction time, not set_parameters() after the fact.
    overrides = [rclpy.parameter.Parameter('input_topic', value='/custom/in'),
                 rclpy.parameter.Parameter('output_topic', value='/custom/out')]
    node = CameraRelay(parameter_overrides=overrides)
    received = []
    sub = node.create_subscription(Image, '/custom/out', lambda m: received.append(m), 10)
    pub = node.create_publisher(Image, '/custom/in', 10)
    try:
        pub.publish(Image(width=1))
        deadline = time.monotonic() + 3.0
        while len(received) < 1 and time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.5)
        assert len(received) == 1
        assert received[0].width == 1
    finally:
        node.destroy_subscription(sub)
        node.destroy_node()
