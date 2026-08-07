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
import math
import time
from unittest.mock import MagicMock, patch

import pytest
import rclpy
from geometry_msgs.msg import Twist
from rclpy.time import Time

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
        from nav_fleet.esp32_protocol import BaseInfo, integrate_odometry
        # Differing left/right speeds so the scenario has real curvature (omega != 0),
        # not just straight-line motion — exercises the full mid_yaw formula, not a
        # degenerate case where a broken dt/sign bug could coincidentally still pass.
        info = BaseInfo(speed_l=0.1, speed_r=0.3, roll=0.0, pitch=0.0, yaw=0.0,
                        temp=30.0, voltage=11.8)

        # Control the node's clock across two calls so _publish_odom computes a
        # known, exact dt (0.5s). The FIRST call only seeds _last_base_info_time —
        # matching real behavior on the very first feedback line ever received,
        # where the `if self._last_base_info_time is not None:` branch is skipped
        # and integrate_odometry is never called. The SECOND call is where the real
        # dead-reckoning math actually runs, with a dt we control exactly.
        dt = 0.5
        t0 = Time(seconds=2000, nanoseconds=0)
        t1 = Time(seconds=2000, nanoseconds=int(dt * 1e9))
        fake_clock = MagicMock()
        fake_clock.now.side_effect = [t0, t1]
        driver.get_clock = MagicMock(return_value=fake_clock)

        driver._publish_odom(info)
        assert (driver._x, driver._y, driver._yaw) == (0.0, 0.0, 0.0)

        driver._publish_odom(info)
        # Two messages published -> spin_once (which delivers at most one ready
        # callback per call, and intra-process discovery isn't instant) may need
        # more than one call to drain both; poll with a bounded deadline rather
        # than assuming a fixed call count.
        deadline = time.monotonic() + 3.0
        while len(received) < 2 and time.monotonic() < deadline:
            rclpy.spin_once(driver, timeout_sec=0.5)

        # Expected value from the SAME formula integrate_odometry implements,
        # computed independently from known inputs (x=y=yaw=0, dt=0.5s) — not
        # read back from driver internals, so a wiring bug (e.g. wrong dt sign,
        # dt never applied) would produce a real mismatch, not a vacuous pass.
        # Hand-verified independently (v=0.2, omega=(0.3-0.1)/0.172=1.16279...,
        # mid_yaw=omega*dt/2=0.290698..., x=v*cos(mid_yaw)*dt=0.0958044...,
        # y=v*sin(mid_yaw)*dt=0.0286621..., yaw=omega*dt=0.5813953...).
        expected_x, expected_y, expected_yaw = integrate_odometry(
            0.0, 0.0, 0.0, info.speed_l, info.speed_r, driver._track_width, dt)
        assert expected_x == pytest.approx(0.09580441407640837)
        assert expected_y == pytest.approx(0.028662069769576793)
        assert expected_yaw == pytest.approx(0.5813953488372093)

        assert driver._x == pytest.approx(expected_x)
        assert driver._y == pytest.approx(expected_y)
        assert driver._yaw == pytest.approx(expected_yaw)

        assert len(received) == 2
        second = received[-1]
        assert second.child_frame_id == 'base_footprint'
        assert second.pose.pose.position.x == pytest.approx(expected_x)
        assert second.pose.pose.position.y == pytest.approx(expected_y)
        assert second.pose.pose.orientation.z == pytest.approx(math.sin(expected_yaw / 2.0))
        assert second.pose.pose.orientation.w == pytest.approx(math.cos(expected_yaw / 2.0))
    finally:
        driver.destroy_subscription(sub)
        driver.destroy_node()
