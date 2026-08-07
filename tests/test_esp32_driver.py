# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""Requires a live ROS2 environment (imports rclpy at module level) — same treatment
as test_navigation.py/test_nav_runner.py (see CLAUDE.md Gotchas): --ignore'd in
stage-1-quality, run in stage-2-gazebo's live-ROS test invocation. Does NOT need
Gazebo — a bare rclpy context is enough — but stays out of stage-1 because rclpy
itself isn't installed there.

The serial.Serial(...) I/O boundary is mocked throughout (matches this project's
established treatment of thin hardware boundaries, e.g. JetsonExecutor's SSH layer) —
these tests verify wiring and the pure logic reachable from callbacks, not real
hardware.
"""
from unittest.mock import MagicMock, patch

import pytest
import rclpy
from geometry_msgs.msg import Twist

from nav_fleet.esp32_driver import Esp32Driver


@pytest.fixture(scope='module', autouse=True)
def ros_context():
    rclpy.init()
    yield
    rclpy.try_shutdown()


def _make_driver(**param_overrides):
    with patch('nav_fleet.esp32_driver.serial.Serial') as mock_serial_cls:
        mock_ser = MagicMock()
        mock_ser.readline.return_value = b''  # no data — reader thread just idles
        mock_serial_cls.return_value = mock_ser
        driver = Esp32Driver()
        for name, value in param_overrides.items():
            driver.set_parameters([rclpy.parameter.Parameter(name, value=value)])
    return driver, mock_ser


def test_construction_declares_expected_defaults():
    driver, mock_ser = _make_driver()
    try:
        assert driver.get_parameter('serial_device').value == '/dev/ttyUSB0'
        assert driver.get_parameter('baud').value == 115200
        assert driver.get_parameter('watchdog_timeout_ms').value == 200
        assert driver.get_parameter('track_width').value == pytest.approx(0.172)
    finally:
        driver.destroy_node()


def test_construction_enables_feedback_flow_on_startup():
    driver, mock_ser = _make_driver()
    try:
        sent = [call.args[0] for call in mock_ser.write.call_args_list]
        assert any(b'"T": 131' in s or b'"T":131' in s for s in sent)
    finally:
        driver.destroy_node()


def test_cmd_vel_callback_sends_velocity_command():
    driver, mock_ser = _make_driver()
    try:
        mock_ser.write.reset_mock()
        msg = Twist()
        msg.linear.x = 0.2
        msg.angular.z = 0.5
        driver._cmd_vel_cb(msg)
        (sent_bytes,) = mock_ser.write.call_args.args
        assert b'"T": 13' in sent_bytes or b'"T":13' in sent_bytes
        assert b'0.2' in sent_bytes
        assert b'0.5' in sent_bytes
    finally:
        driver.destroy_node()


def test_watchdog_sends_zero_velocity_after_timeout():
    driver, mock_ser = _make_driver()
    try:
        driver._last_cmd_time -= 10.0  # force "long ago"
        mock_ser.write.reset_mock()
        driver._watchdog_cb()
        (sent_bytes,) = mock_ser.write.call_args.args
        assert b'"X": 0.0' in sent_bytes or b'"X":0.0' in sent_bytes
        assert driver._stopped is True
    finally:
        driver.destroy_node()


def test_watchdog_does_not_resend_once_already_stopped():
    driver, mock_ser = _make_driver()
    try:
        driver._last_cmd_time -= 10.0
        driver._watchdog_cb()
        mock_ser.write.reset_mock()
        driver._watchdog_cb()  # second tick, still stopped, still no new cmd_vel
        mock_ser.write.assert_not_called()
    finally:
        driver.destroy_node()


def test_publish_odom_integrates_and_publishes(qos_capture=None):
    driver, mock_ser = _make_driver()
    received = []
    sub = driver.create_subscription(
        __import__('nav_msgs.msg', fromlist=['Odometry']).Odometry,
        '/robot_001/odom', lambda m: received.append(m), 10)
    try:
        from nav_fleet.esp32_protocol import BaseInfo
        info = BaseInfo(speed_l=0.1, speed_r=0.1, roll=0.0, pitch=0.0, yaw=0.0,
                        temp=30.0, voltage=11.8)
        driver._publish_odom(info)
        rclpy.spin_once(driver, timeout_sec=0.5)
        assert len(received) == 1
        assert received[0].child_frame_id == 'base_footprint'
    finally:
        driver.destroy_subscription(sub)
        driver.destroy_node()
