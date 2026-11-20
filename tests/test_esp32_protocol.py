# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
import json
import math

import pytest

from nav_fleet.esp32_protocol import (BaseInfo, OrientationData, encode_enable_feedback_flow,
                                      encode_feedback_flow_interval, encode_gimbal_cmd,
                                      encode_get_imu_data, encode_set_heartbeat_timeout,
                                      encode_velocity_cmd, integrate_odometry, parse_base_info,
                                      parse_feedback_line, parse_orientation, scale_imu_raw)


def test_encode_velocity_cmd():
    assert encode_velocity_cmd(0.1, 0.3) == {"T": 13, "X": 0.1, "Z": 0.3}


def test_encode_gimbal_cmd():
    assert encode_gimbal_cmd(0, 0) == {"T": 133, "X": 0, "Y": 0, "SPD": 0, "ACC": 0}


def test_encode_enable_feedback_flow_on():
    assert encode_enable_feedback_flow(True) == {"T": 131, "cmd": 1}


def test_encode_enable_feedback_flow_off():
    assert encode_enable_feedback_flow(False) == {"T": 131, "cmd": 0}


def test_encode_feedback_flow_interval():
    assert encode_feedback_flow_interval(20) == {"T": 142, "cmd": 20}


def test_encode_get_imu_data():
    assert encode_get_imu_data() == {"T": 126}


def test_encode_set_heartbeat_timeout():
    assert encode_set_heartbeat_timeout(200) == {"T": 136, "cmd": 200}


def test_parse_feedback_line_valid_json():
    assert parse_feedback_line('{"T":1001,"L":0.1}') == {"T": 1001, "L": 0.1}


def test_parse_feedback_line_malformed_json_returns_none():
    assert parse_feedback_line('not json{{{') is None


def test_parse_feedback_line_empty_string_returns_none():
    assert parse_feedback_line('') is None


def test_parse_base_info_valid():
    # Real T:1001 wire shape (see esp32_protocol.py's module docstring, corrected
    # 2026-08-10) — wheel speeds + RAW accel/gyro/mag + encoder ticks + voltage.
    # NOT roll/pitch/yaw/temp — that was the original (wrong) 2026-08-06 assumption.
    data = {"T": 1001, "L": 0.1, "R": 0.12, "ax": 0.1, "ay": 0.2, "az": 9.8,
            "gx": 0.01, "gy": 0.02, "gz": 0.03, "mx": 10, "my": 11, "mz": 12,
            "odl": -1, "odr": 0, "v": 11.8}
    info = parse_base_info(data)
    assert info == BaseInfo(speed_l=0.1, speed_r=0.12, ax=0.1, ay=0.2, az=9.8,
                            gx=0.01, gy=0.02, gz=0.03, mx=10, my=11, mz=12,
                            odl=-1, odr=0, voltage=11.8)


def test_parse_base_info_wrong_type_returns_none():
    assert parse_base_info({"T": 1002, "L": 0.1}) is None


def test_parse_base_info_missing_field_returns_none():
    assert parse_base_info({"T": 1001, "L": 0.1}) is None


def test_parse_base_info_real_hardware_capture():
    # Byte-for-byte from a live probe against the real ESP32 sub-controller over
    # /dev/ttyTHS1, 2026-08-10 (root-cause investigation for the odom/imu-never-
    # publishes bug) — not hand-written, so this can't silently drift from what the
    # real firmware actually sends the way the 2026-08-06 reconstruction did.
    data = json.loads(
        '{"T":1001,"L":0,"R":0,"ax":-36,"ay":68,"az":8556,"gx":-8,"gy":16,"gz":0,'
        '"mx":-555,"my":502,"mz":612,"odl":-1,"odr":0,"v":1203}')
    info = parse_base_info(data)
    assert info == BaseInfo(speed_l=0, speed_r=0, ax=-36, ay=68, az=8556, gx=-8,
                            gy=16, gz=0, mx=-555, my=502, mz=612, odl=-1, odr=0,
                            voltage=1203)


def test_parse_base_info_coerces_whole_number_fields_to_float():
    # Real regression, not a hypothetical: the real firmware sends whole-number
    # readings as bare JSON ints ("ax":-36), and esp32_driver._publish_imu assigns
    # ax/ay/az/gx/gy/gz straight into a ROS Imu message's geometry_msgs/Vector3
    # fields with no intervening arithmetic — an int there hard-ABORTS the whole
    # process (rosidl's C converter asserts PyFloat_Check rather than raising a
    # catchable exception). Reproduced live 2026-08-10 from these exact bytes before
    # this coercion existed. speed_l/speed_r locked in too since they reach
    # Odometry's float64 fields the same way, just via arithmetic that happens to
    # coerce today — this test doesn't rely on that arithmetic staying in place.
    data = json.loads(
        '{"T":1001,"L":0,"R":0,"ax":-36,"ay":68,"az":8556,"gx":-8,"gy":16,"gz":0,'
        '"mx":-555,"my":502,"mz":612,"odl":-1,"odr":0,"v":1203}')
    info = parse_base_info(data)
    for field in ('speed_l', 'speed_r', 'ax', 'ay', 'az', 'gx', 'gy', 'gz'):
        assert isinstance(getattr(info, field), float), f'{field} must be float'


def test_scale_imu_raw_real_hardware_capture_gives_physically_plausible_values():
    # Root cause, found 2026-08-12/13 via a live AMCL investigation: esp32_driver
    # was publishing these RAW QMI8658 LSB counts straight into a ROS Imu message
    # with NO unit conversion at all — flagged as an open, unconfirmed risk in
    # esp32_driver.py's own comment since 2026-08-10, confirmed broken tonight (a
    # stationary robot's odom->base_footprint yaw was jumping through the full
    # +/-pi range every ~100ms; traced through ekf_node's motion-model input
    # straight back to these unscaled raw counts). Same real capture as
    # test_parse_base_info_real_hardware_capture above — robot was stationary and
    # level. The whole point of this test: once scaled, az must land near ONE
    # real g (9.80665 m/s^2) and gx/gy/gz must land near zero rad/s, not the raw
    # 8556/-8/16/0 counts.
    ax, ay, az, gx, gy, gz = scale_imu_raw(ax=-36, ay=68, az=8556, gx=-8, gy=16, gz=0)
    assert az == pytest.approx(9.80665 * 8556 / 8192, abs=0.05)
    assert 9.0 < az < 10.6, 'az must be close to one real g, not a raw LSB count'
    for value in (ax, ay, gx, gy, gz):
        assert abs(value) < 1.0, 'small raw counts must scale to small physical values'


def test_scale_imu_raw_is_a_pure_linear_scale():
    # Sensitivity-constant math sanity check, independent of any specific capture —
    # doubling the raw input must double the scaled output (pure proportional scale,
    # no offset/bias correction applied here — offset calibration is a separate,
    # still-open gap, see esp32_driver.py's own comment).
    single = scale_imu_raw(ax=1, ay=0, az=0, gx=1, gy=0, gz=0)
    double = scale_imu_raw(ax=2, ay=0, az=0, gx=2, gy=0, gz=0)
    assert double[0] == pytest.approx(2 * single[0])
    assert double[3] == pytest.approx(2 * single[3])


def test_scale_imu_raw_zero_input_is_zero_output():
    assert scale_imu_raw(ax=0, ay=0, az=0, gx=0, gy=0, gz=0) == (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)


def test_parse_orientation_valid():
    # Real T:1002 wire shape (reply to a T:126 request) — fused roll/pitch/yaw PLUS
    # a quaternion. NOT raw accel/gyro/mag/temp — that was the original (wrong)
    # 2026-08-06 assumption; the raw IMU data actually lives in T:1001 (above).
    data = {"T": 1002, "r": 0.0, "p": 0.0, "y": 1.5,
            "q0": 1.0, "q1": 0.0, "q2": 0.0, "q3": 0.0}
    info = parse_orientation(data)
    assert info == OrientationData(roll=0.0, pitch=0.0, yaw=1.5,
                                   q0=1.0, q1=0.0, q2=0.0, q3=0.0)


def test_parse_orientation_wrong_type_returns_none():
    assert parse_orientation({"T": 1001, "L": 0.1}) is None


def test_parse_orientation_missing_field_returns_none():
    assert parse_orientation({"T": 1002, "r": 0.0}) is None


def test_parse_orientation_real_hardware_capture():
    # Byte-for-byte from the same live probe as test_parse_base_info_real_hardware_
    # capture above, 2026-08-10.
    data = json.loads('{"T":1002,"r":0,"p":0,"y":0,"q0":0,"q1":0,"q2":0,"q3":0}')
    info = parse_orientation(data)
    assert info == OrientationData(roll=0, pitch=0, yaw=0, q0=0, q1=0, q2=0, q3=0)


def test_parse_orientation_coerces_whole_number_fields_to_float():
    # Same real bug class as test_parse_base_info_coerces_whole_number_fields_to_
    # float above — not yet wired into a ROS message field today, but the same
    # hard-abort landmine sits under geometry_msgs/Quaternion the moment it is.
    data = json.loads('{"T":1002,"r":0,"p":0,"y":0,"q0":0,"q1":0,"q2":0,"q3":0}')
    info = parse_orientation(data)
    for field in ('roll', 'pitch', 'yaw', 'q0', 'q1', 'q2', 'q3'):
        assert isinstance(getattr(info, field), float), f'{field} must be float'


def test_integrate_odometry_straight_line():
    x, y, yaw = integrate_odometry(0.0, 0.0, 0.0, speed_l=0.1, speed_r=0.1,
                                   track_width=0.172, dt=1.0)
    assert x == pytest.approx(0.1)
    assert y == pytest.approx(0.0, abs=1e-9)
    assert yaw == pytest.approx(0.0, abs=1e-9)


def test_integrate_odometry_pure_rotation():
    # equal-and-opposite wheel speeds: v == 0, so x/y don't move, yaw does.
    x, y, yaw = integrate_odometry(0.0, 0.0, 0.0, speed_l=-0.1, speed_r=0.1,
                                   track_width=0.2, dt=1.0)
    assert x == pytest.approx(0.0, abs=1e-9)
    assert y == pytest.approx(0.0, abs=1e-9)
    assert yaw == pytest.approx(1.0)  # omega = (0.1 - (-0.1)) / 0.2 = 1.0 rad/s


def test_integrate_odometry_quarter_circle_from_90deg_heading():
    # starting already facing +y (yaw=pi/2), pure forward motion should move +y, not +x.
    x, y, yaw = integrate_odometry(0.0, 0.0, math.pi / 2, speed_l=0.1, speed_r=0.1,
                                   track_width=0.172, dt=1.0)
    assert x == pytest.approx(0.0, abs=1e-9)
    assert y == pytest.approx(0.1)


# --- chassis type (T:602 query / stored T:900 line) — real-robot root cause, 2026-11-16

def test_encode_boot_mission_info():
    from nav_fleet.esp32_protocol import encode_boot_mission_info
    assert encode_boot_mission_info() == {'T': 602}


def test_parse_chassis_main_type_real_hardware_capture():
    """Lines captured verbatim from this robot's controller, 2026-11-16: the first is
    what it had stored (UGV Beast on a UGV Rover), the second after the fix."""
    from nav_fleet.esp32_protocol import parse_chassis_main_type
    assert parse_chassis_main_type('[StepNum: 1 ] - {"T":900,"main":3,"module":0}') == 3
    assert parse_chassis_main_type('[StepNum: 1 ] - {"T":900,"main":2,"module":0}') == 2
    assert parse_chassis_main_type('[lineNum: 2 ] - {"T": 900, "main": 2, "module": 2}') == 2


def test_parse_chassis_main_type_ignores_other_lines():
    from nav_fleet.esp32_protocol import parse_chassis_main_type
    assert parse_chassis_main_type('{"T":1001,"L":0,"R":0,"odl":-129}') is None
    assert parse_chassis_main_type('reading file: [boot] starts:') is None
    assert parse_chassis_main_type('') is None


# --- GyroBiasEstimator — resting gyro drift, measured 0.26 deg/s on z, 2026-11-16 ---

def _feed(est, n, sample, stationary=True):
    out = None
    for _ in range(n):
        out = est.update(*sample, stationary=stationary)
    return out


def test_gyro_bias_is_zero_until_a_full_quiet_window_has_been_seen():
    from nav_fleet.esp32_protocol import GyroBiasEstimator
    est = GyroBiasEstimator(window=40)
    assert _feed(est, 39, (0.001, 0.018, 0.0045)) == (0.0, 0.0, 0.0)


def test_gyro_bias_converges_to_the_resting_offset():
    from nav_fleet.esp32_protocol import GyroBiasEstimator
    est = GyroBiasEstimator(window=40)
    bx, by, bz = _feed(est, 40, (-0.0028, 0.0182, 0.0046))   # today's measured offsets
    assert bx == pytest.approx(-0.0028)
    assert by == pytest.approx(0.0182)
    assert bz == pytest.approx(0.0046)


def test_gyro_bias_ignores_samples_while_the_robot_is_driving():
    from nav_fleet.esp32_protocol import GyroBiasEstimator
    est = GyroBiasEstimator(window=40)
    _feed(est, 40, (0.0, 0.0, 0.0046))
    # A long real turn while driving must not be learned as "bias".
    assert _feed(est, 200, (0.0, 0.0, 0.5), stationary=False)[2] == pytest.approx(0.0046)


def test_gyro_bias_rejects_a_window_with_real_motion_in_it():
    """Wheels stopped does not prove the robot is still: on 2026-11-16 it was turned
    a full circle BY HAND with the wheels reporting zero. A window whose readings
    spread more than max_spread (or sit far from zero) is thrown away."""
    from nav_fleet.esp32_protocol import GyroBiasEstimator
    est = GyroBiasEstimator(window=40)
    _feed(est, 40, (0.0, 0.0, 0.0046))
    for i in range(40):                       # hand turn: rate ramps 0 -> 1 rad/s
        est.update(0.0, 0.0, i / 40.0, stationary=True)
    assert est.bias[2] == pytest.approx(0.0046)
    # ...and a steady hand turn (no spread, but far too fast to be drift) as well.
    assert _feed(est, 80, (0.0, 0.0, 0.4))[2] == pytest.approx(0.0046)


def test_gyro_bias_tracks_slow_change_window_by_window():
    from nav_fleet.esp32_protocol import GyroBiasEstimator
    est = GyroBiasEstimator(window=40)
    _feed(est, 40, (0.0, 0.0, 0.0046))
    assert _feed(est, 40, (0.0, 0.0, 0.0060))[2] == pytest.approx(0.0060)


# --- wheel-speed command, battery (2026-11-18) -------------------------------------

from nav_fleet.esp32_protocol import (  # noqa: E402
    BATTERY_CRITICAL, BATTERY_LOW, BATTERY_OK, BatteryMonitor, battery_volts,
    encode_wheel_speed_cmd, twist_to_wheel_speeds,
)


def test_encode_wheel_speed_cmd_is_t1_with_float_fields():
    cmd = encode_wheel_speed_cmd(0, -0.25)
    assert cmd == {"T": 1, "L": 0.0, "R": -0.25}
    # the firmware checks is<float>() on both: an int 0 must still go out as 0.0
    assert json.dumps(cmd) == '{"T": 1, "L": 0.0, "R": -0.25}'


def test_twist_to_wheel_speeds_matches_the_firmwares_own_ros_ctrl_arithmetic():
    # movtion_module.h rosCtrl(): A = X - Z*W/2 (left), B = X + Z*W/2 (right)
    assert twist_to_wheel_speeds(0.2, 0.0, 0.172) == pytest.approx((0.2, 0.2))
    assert twist_to_wheel_speeds(0.0, 1.0, 0.172) == pytest.approx((-0.086, 0.086))
    left, right = twist_to_wheel_speeds(0.15, -0.5, 0.172)
    assert left > right                                  # -Z = right turn: left side faster
    assert (left + right) / 2 == pytest.approx(0.15)


def test_battery_volts_reads_centivolts():
    assert battery_volts(917) == pytest.approx(9.17)     # the flat pack, 2026-11-18
    assert battery_volts(1260) == pytest.approx(12.6)


def test_battery_monitor_gives_no_state_until_it_has_a_full_window():
    mon = BatteryMonitor(window=5)
    assert [mon.update(11.8) for _ in range(4)] == [None] * 4
    assert mon.update(11.8) == BATTERY_OK
    assert mon.volts == pytest.approx(11.8)


@pytest.mark.parametrize('volts, expected', [
    (12.6, BATTERY_OK), (10.5, BATTERY_OK), (10.49, BATTERY_LOW),
    (9.9, BATTERY_LOW), (9.89, BATTERY_CRITICAL), (9.17, BATTERY_CRITICAL),
])
def test_battery_monitor_thresholds(volts, expected):
    mon = BatteryMonitor(window=3)
    for _ in range(3):
        state = mon.update(volts)
    assert state == expected


def test_battery_monitor_uses_the_median_so_load_sag_does_not_flip_the_state():
    mon = BatteryMonitor(window=10)
    for i in range(30):
        state = mon.update(9.0 if i % 5 == 0 else 11.2)   # one sample in five sags
    assert state == BATTERY_OK
    assert mon.volts == pytest.approx(11.2)


def test_battery_monitor_ignores_zero_readings_from_a_sensor_not_yet_answering():
    mon = BatteryMonitor(window=3)
    for _ in range(10):
        assert mon.update(0.0) is None
    for _ in range(3):
        state = mon.update(11.0)
    assert state == BATTERY_OK


# --- IMU health (2026-11-20) -----------------------------------------------------------
# The raw status line the board sent on 2026-11-20 with the robot standing still: every
# axis stuck, gravity reading 3.9 g, gyro z reading 706 deg/s.
FROZEN_20261120 = (308, 31265, -5042, -32253, 3840, 11305)


def _live_sample(i):
    """A still robot's raw counts: gravity on z, the lowest bits flickering."""
    return (-36 + i % 3, 68 - i % 2, 8556 + i % 5, -8 + i % 2, 16 - i % 3, i % 4)


def test_imu_health_gives_no_verdict_until_it_has_a_full_window():
    from nav_fleet.esp32_protocol import ImuHealth
    health = ImuHealth(window=5)
    assert [health.update(*_live_sample(i)) for i in range(4)] == [None] * 4
    assert health.update(*_live_sample(4)) == 'ok'


def test_imu_health_calls_a_live_resting_sensor_ok():
    from nav_fleet.esp32_protocol import IMU_OK, ImuHealth
    health = ImuHealth()
    for i in range(200):
        state = health.update(*_live_sample(i))
    assert state == IMU_OK


def test_imu_health_catches_the_frozen_sensor_of_2026_11_20():
    """The sensor chip did not start at power-on. The board went on sending the same
    nine numbers 20 times a second; the driver published 12.33 rad/s of turn from a
    robot standing still, and the position estimate left the home spot by 2.2 m
    before the first goal."""
    from nav_fleet.esp32_protocol import IMU_FROZEN, ImuHealth
    health = ImuHealth()
    for _ in range(40):
        state = health.update(*FROZEN_20261120)
    assert state == IMU_FROZEN
    assert '11305' in health.detail                  # the log line names the stuck value


def test_imu_health_catches_a_sensor_that_moves_but_does_not_feel_gravity():
    from nav_fleet.esp32_protocol import IMU_IMPLAUSIBLE, ImuHealth
    health = ImuHealth()
    for i in range(40):
        state = health.update(300 + i % 3, 31265, -5042, i % 2, 0, 0)     # 3.9 g
    assert state == IMU_IMPLAUSIBLE
    for i in range(40):
        state = health.update(i % 3, i % 2, 40 + i % 4, 0, i % 2, 0)       # 0.005 g
    assert state == IMU_IMPLAUSIBLE


def test_imu_health_recovers_when_the_sensor_comes_back():
    from nav_fleet.esp32_protocol import IMU_FROZEN, IMU_OK, ImuHealth
    health = ImuHealth()
    for _ in range(40):
        health.update(*FROZEN_20261120)
    assert health.state == IMU_FROZEN
    for i in range(40):
        health.update(*_live_sample(i))
    assert health.state == IMU_OK


def test_imu_health_is_not_fooled_by_hard_driving():
    """Braking and turning swing single samples well away from 1 g; the middle sample
    of two seconds does not move."""
    from nav_fleet.esp32_protocol import IMU_OK, ImuHealth
    health = ImuHealth()
    for i in range(40):
        jolt = 9000 if i % 7 == 0 else 0
        state = health.update(jolt, -jolt // 2, 8556 + i % 5, 400 * (i % 3), i, -3000 + i)
    assert state == IMU_OK
