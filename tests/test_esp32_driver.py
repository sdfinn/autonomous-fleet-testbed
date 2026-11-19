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
import json
import math
import time
from unittest.mock import MagicMock, patch

import pytest
import rclpy
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from rclpy.time import Time
from sensor_msgs.msg import Imu

from nav_fleet.esp32_driver import GYRO_VARIANCE_RAD2_S2, Esp32Driver


@pytest.fixture(scope='module', autouse=True)
def ros_context():
    rclpy.init()
    yield
    rclpy.try_shutdown()


def _idle_readline(*_args, **_kwargs):
    # Real pyserial (timeout=1.0) BLOCKS for up to 1s when no data has arrived — a
    # bare `return_value = b''` mock doesn't, so _read_loop's background thread
    # hot-spins this call as fast as the interpreter allows for the test's whole
    # lifetime. unittest.mock's internal call-tracking isn't thread-safe under that
    # kind of concurrent hammering — found 2026-08-10 (esp32/odom root-cause fix
    # session) as a real, reproducible `Fatal Python error: Aborted` crash once two
    # driver instances' background threads overlapped. A short sleep here mirrors
    # the real hardware boundary's actual blocking behavior and removes the hot-spin.
    time.sleep(0.01)
    return b''


def _make_driver(**param_overrides):
    with patch('nav_fleet.esp32_driver.serial.Serial') as mock_serial_cls:
        mock_ser = MagicMock()
        mock_ser.readline.side_effect = _idle_readline  # no data — reader thread just idles
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
        # No sign flips (see test_cmd_vel_sends_ros_signs_unchanged...). angular.z is
        # multiplied by angular_cmd_gain (2.8): 0.5 -> 1.4.
        sent = json.loads(sent_bytes)
        assert sent['X'] == pytest.approx(0.2)
        assert sent['Z'] == pytest.approx(0.5 * 2.8)
    finally:
        driver.destroy_node()


def test_cmd_vel_sends_ros_signs_unchanged_and_scales_turn_rate():
    """+linear.x must reach the firmware as +X, and +angular.z as +Z.

    From 2026-08-11 to 2026-11-16 this driver NEGATED both, believing this unit was
    wired backwards. Root cause found 2026-11-16: the controller had chassis type
    main=3 (tracked UGV Beast) stored on a 6-wheel UGV Rover, which reverses motor
    direction and mis-scales speed 2.53x. With main=2 stored, bench-verified on the
    real robot: +X drove it 0.281 m toward a wall (lidar) for a 0.30 m command, and
    +Z turned it left (gyro positive). The turn rate is multiplied by
    angular_cmd_gain to make up for skid-steer tyre scrub."""
    driver, mock_ser = _make_driver()
    try:
        assert driver.get_parameter('angular_cmd_gain').value == 2.8
        mock_ser.write.reset_mock()
        msg = Twist()
        msg.linear.x = 0.15
        msg.angular.z = 0.3
        driver._cmd_vel_cb(msg)
        sent = json.loads(mock_ser.write.call_args.args[0])
        assert sent['T'] == 13
        assert sent['X'] == pytest.approx(0.15)
        assert sent['Z'] == pytest.approx(0.3 * 2.8)

        msg2 = Twist()
        msg2.linear.x = -0.15
        msg2.angular.z = -0.3
        driver._cmd_vel_cb(msg2)
        sent2 = json.loads(mock_ser.write.call_args.args[0])
        assert sent2['X'] == pytest.approx(-0.15)
        assert sent2['Z'] == pytest.approx(-0.3 * 2.8)
    finally:
        driver.destroy_node()


def test_startup_asks_controller_for_its_stored_chassis_type():
    driver, mock_ser = _make_driver()
    try:
        sent = [json.loads(c.args[0]) for c in mock_ser.write.call_args_list]
        assert {'T': 602} in sent
        assert driver._chassis_ok is None        # nothing reported yet
    finally:
        driver.destroy_node()


def test_wrong_chassis_type_blocks_all_motion():
    """If the controller reports any chassis type but the expected one (2, UGV
    Rover), the robot would run ~2.5x fast and possibly backwards (the real state of
    this unit until 2026-11-16) — so every cmd_vel must become a zero command."""
    driver, mock_ser = _make_driver()
    try:
        driver._check_chassis_line('[StepNum: 1 ] - {"T":900,"main":3,"module":0}')
        assert driver._chassis_ok is False
        mock_ser.write.reset_mock()
        msg = Twist()
        msg.linear.x = 0.3
        msg.angular.z = 0.5
        driver._cmd_vel_cb(msg)
        sent = json.loads(mock_ser.write.call_args.args[0])
        assert sent == {'T': 13, 'X': 0.0, 'Z': 0.0}
    finally:
        driver.destroy_node()


def test_correct_chassis_type_allows_motion_and_unrelated_lines_are_ignored():
    driver, mock_ser = _make_driver()
    try:
        driver._check_chassis_line('{"T":1001,"L":0,"R":0}')       # not a T:900 line
        assert driver._chassis_ok is None
        driver._check_chassis_line('[StepNum: 1 ] - {"T":900,"main":2,"module":0}')
        assert driver._chassis_ok is True
        mock_ser.write.reset_mock()
        msg = Twist()
        msg.linear.x = 0.1
        driver._cmd_vel_cb(msg)
        assert json.loads(mock_ser.write.call_args.args[0])['X'] == pytest.approx(0.1)
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
        # Non-speed fields are irrelevant to _publish_odom's own math (it only reads
        # speed_l/speed_r) — zeroed rather than omitted since BaseInfo's real shape
        # (corrected 2026-08-10) requires them.
        # Wheel speeds are used exactly as the controller reports them (no sign flip
        # since 2026-11-16 — see _publish_odom's comment for the chassis-type story).
        info = BaseInfo(speed_l=0.1, speed_r=0.3, ax=0, ay=0, az=0, gx=0, gy=0, gz=0,
                        mx=0, my=0, mz=0, odl=0, odr=0, voltage=11.8)

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
        # Hand-verified: v=(0.1+0.3)/2=0.2, omega=(0.3-0.1)/0.172=1.16279...,
        # mid_yaw=omega*dt/2=0.290698..., x=v*cos(mid_yaw)*dt=0.0958044...,
        # y=v*sin(mid_yaw)*dt=0.0286621..., yaw=omega*dt=0.5813953...
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


def test_publish_imu_scales_raw_accel_gyro_to_physical_units():
    # _publish_imu takes a BaseInfo now (corrected 2026-08-10) — the raw accel/gyro
    # esp32_driver previously (and wrongly) expected from a separate T:1002 message
    # actually lives in the SAME T:1001 message as the wheel speeds.
    #
    # Root cause fix, 2026-08-12/13: this used to assert msg.linear_acceleration.z
    # == 8556 — i.e. the RAW QMI8658 count passed straight through with no unit
    # conversion, which is the actual bug a live AMCL investigation found (a
    # stationary robot's yaw estimate spinning through +/-pi every ~100ms, traced
    # back to this exact pass-through). Now asserts the physically-scaled value —
    # see esp32_protocol.scale_imu_raw's own docstring for the conversion and its
    # confidence level.
    driver, mock_ser = _make_driver()
    received = []
    sub = driver.create_subscription(
        Imu, '/robot_001/imu/data', lambda m: received.append(m), 10)
    try:
        # Built via parse_base_info (not a hand-constructed BaseInfo literal) so this
        # test exercises the SAME int->float coercion the real code path does — a
        # hand-written BaseInfo(ax=-36, ...) with bare int literals bypasses that
        # coercion entirely and would miss the exact crash this fix addresses (a real
        # `Fatal Python error: Aborted` hit developing this test, see
        # esp32_protocol.py's parse_base_info docstring).
        from nav_fleet.esp32_protocol import parse_base_info, scale_imu_raw
        info = parse_base_info({"T": 1001, "L": 0, "R": 0, "ax": -36, "ay": 68,
                                "az": 8556, "gx": -8, "gy": 16, "gz": 0, "mx": -555,
                                "my": 502, "mz": 612, "odl": -1, "odr": 0, "v": 1203})
        driver._publish_imu(info)
        deadline = time.monotonic() + 3.0
        while len(received) < 1 and time.monotonic() < deadline:
            rclpy.spin_once(driver, timeout_sec=0.5)
        assert len(received) == 1
        msg = received[0]
        expected = scale_imu_raw(ax=-36, ay=68, az=8556, gx=-8, gy=16, gz=0)
        assert msg.linear_acceleration.x == pytest.approx(expected[0])
        assert msg.linear_acceleration.y == pytest.approx(expected[1])
        assert msg.linear_acceleration.z == pytest.approx(expected[2])
        assert 9.0 < msg.linear_acceleration.z < 11.0  # ~1g, not the raw 8556 count
        assert msg.angular_velocity.x == pytest.approx(expected[3])
        assert msg.angular_velocity.y == pytest.approx(expected[4])
        assert msg.angular_velocity.z == pytest.approx(expected[5])
        assert msg.orientation_covariance[0] == -1.0  # not yet wired in — see driver comment
        # The gyro MUST carry a real, positive variance. robot_localization drops
        # the whole angular velocity when angular_velocity_covariance[0] == -1
        # ("Ignoring angular velocity..."), which froze the fused heading at 0 on
        # the real robot (2026-08-12 .. 2026-11-16 — see the driver comment). Zero
        # is wrong too ("perfect measurement"). Only the diagonal is populated.
        cov = list(msg.angular_velocity_covariance)
        assert cov[0] == cov[4] == cov[8] == GYRO_VARIANCE_RAD2_S2
        assert GYRO_VARIANCE_RAD2_S2 > 0.0
        assert all(c == 0.0 for i, c in enumerate(cov) if i not in (0, 4, 8))
        # Accel is not fused by ekf.yaml and its noise is uncharacterized: -1 stays.
        assert msg.linear_acceleration_covariance[0] == -1.0
    finally:
        driver.destroy_subscription(sub)
        driver.destroy_node()


def test_publish_imu_subtracts_resting_gyro_offset_once_learned():
    """Real robot, 2026-11-16: stationary gyro z read +0.26 deg/s, which the heading
    filter turned into 22 deg of false rotation in 90 s. After ~2 s of stillness
    (40 samples, wheels at zero, no command) the published rate must be ~0."""
    driver, _ = _make_driver()
    received = []
    sub = driver.create_subscription(Imu, '/robot_001/imu/data',
                                     lambda m: received.append(m), 50)
    try:
        from nav_fleet.esp32_protocol import BaseInfo, scale_imu_raw
        info = BaseInfo(speed_l=0, speed_r=0, ax=0, ay=0, az=8192, gx=-3, gy=16, gz=4,
                        mx=0, my=0, mz=0, odl=0, odr=0, voltage=11.1)
        raw_gz = scale_imu_raw(0, 0, 8192, -3, 16, 4)[5]
        assert raw_gz > 0.004                      # the offset is really there
        driver._stopped = True                     # watchdog has zeroed the command
        for _ in range(41):
            driver._publish_imu(info)
        deadline = time.monotonic() + 3.0
        while len(received) < 41 and time.monotonic() < deadline:
            rclpy.spin_once(driver, timeout_sec=0.2)
        assert received[0].angular_velocity.z == pytest.approx(raw_gz)   # not learned yet
        assert received[-1].angular_velocity.z == pytest.approx(0.0, abs=1e-9)
        assert received[-1].angular_velocity.y == pytest.approx(0.0, abs=1e-9)

        # While a drive command is active the offset is kept, not re-learned.
        driver._stopped = False
        moving = info._replace(speed_l=0.1, speed_r=0.1, gz=404)
        driver._publish_imu(moving)
        assert driver._gyro_bias.bias[2] == pytest.approx(raw_gz)
    finally:
        driver.destroy_subscription(sub)
        driver.destroy_node()


def test_gyro_offset_is_learned_while_zero_speed_commands_keep_arriving():
    """Mapping drive, 2026-11-18: key_teleop publishes zero-speed commands at 20 Hz
    while idle, so the watchdog never trips. The robot is just as still as when
    nobody is publishing, and the offset must be learned then too."""
    driver, _ = _make_driver()
    try:
        from nav_fleet.esp32_protocol import BaseInfo, scale_imu_raw
        info = BaseInfo(speed_l=0, speed_r=0, ax=0, ay=0, az=8192, gx=-3, gy=16, gz=4,
                        mx=0, my=0, mz=0, odl=0, odr=0, voltage=11.1)
        raw_gz = scale_imu_raw(0, 0, 8192, -3, 16, 4)[5]
        for _ in range(41):
            driver._cmd_vel_cb(Twist())            # explicit "stand still", not silence
            driver._publish_imu(info)
        assert driver._stopped is False            # the watchdog never got a chance
        assert driver._gyro_bias.bias[2] == pytest.approx(raw_gz)
    finally:
        driver.destroy_node()


def test_gyro_offset_is_not_learned_while_a_move_is_commanded():
    """Wheels can read zero for a moment while a real move is being commanded (pulling
    away, stalled against something). That is not a resting robot."""
    driver, _ = _make_driver()
    try:
        from nav_fleet.esp32_protocol import BaseInfo
        info = BaseInfo(speed_l=0, speed_r=0, ax=0, ay=0, az=8192, gx=-3, gy=16, gz=4,
                        mx=0, my=0, mz=0, odl=0, odr=0, voltage=11.1)
        moving = Twist()
        moving.linear.x = 0.15
        for _ in range(41):
            driver._cmd_vel_cb(moving)
            driver._publish_imu(info)
        assert driver._gyro_bias.bias == (0.0, 0.0, 0.0)
    finally:
        driver.destroy_node()


def test_dispatch_line_real_hardware_base_info_publishes_odom_and_imu():
    # Byte-for-byte capture from the live root-cause probe against the real ESP32
    # over /dev/ttyTHS1, 2026-08-10 (same capture as
    # test_esp32_protocol.test_parse_base_info_real_hardware_capture) — this is the
    # actual reported bug: before the fix, this exact line produced zero messages
    # on EITHER topic.
    driver, mock_ser = _make_driver()
    odom_received, imu_received = [], []
    odom_sub = driver.create_subscription(
        Odometry, '/robot_001/odom', lambda m: odom_received.append(m), 10)
    imu_sub = driver.create_subscription(
        Imu, '/robot_001/imu/data', lambda m: imu_received.append(m), 10)
    try:
        real_line = {"T": 1001, "L": 0, "R": 0, "ax": -36, "ay": 68, "az": 8556,
                    "gx": -8, "gy": 16, "gz": 0, "mx": -555, "my": 502, "mz": 612,
                    "odl": -1, "odr": 0, "v": 1203}
        driver._dispatch_line(real_line)
        deadline = time.monotonic() + 3.0
        while ((len(odom_received) < 1 or len(imu_received) < 1)
               and time.monotonic() < deadline):
            rclpy.spin_once(driver, timeout_sec=0.5)
        assert len(odom_received) == 1
        assert len(imu_received) == 1
        # Scaled, not the raw -36 count -- see test_publish_imu_scales_raw_accel_gyro_
        # to_physical_units for the full story on why this changed.
        from nav_fleet.esp32_protocol import scale_imu_raw
        expected_ax = scale_imu_raw(ax=-36, ay=68, az=8556, gx=-8, gy=16, gz=0)[0]
        assert imu_received[0].linear_acceleration.x == pytest.approx(expected_ax)
    finally:
        driver.destroy_subscription(odom_sub)
        driver.destroy_subscription(imu_sub)
        driver.destroy_node()


def test_dispatch_line_orientation_is_cached_not_published():
    # T:1002 (a T:126 reply) is fused orientation, not raw IMU data (corrected
    # 2026-08-10) — it should update self._last_orientation and NOT publish
    # anything on its own (no orientation topic; it's a cache for future use).
    driver, mock_ser = _make_driver()
    try:
        assert driver._last_orientation is None
        driver._dispatch_line({"T": 1002, "r": 0.1, "p": 0.2, "y": 0.3,
                               "q0": 1.0, "q1": 0.0, "q2": 0.0, "q3": 0.0})
        from nav_fleet.esp32_protocol import OrientationData
        assert driver._last_orientation == OrientationData(
            roll=0.1, pitch=0.2, yaw=0.3, q0=1.0, q1=0.0, q2=0.0, q3=0.0)
    finally:
        driver.destroy_node()
