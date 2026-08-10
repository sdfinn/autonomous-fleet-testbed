# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
import json
import math

import pytest

from nav_fleet.esp32_protocol import (BaseInfo, OrientationData, encode_enable_feedback_flow,
                                      encode_feedback_flow_interval, encode_get_imu_data,
                                      encode_set_heartbeat_timeout, encode_velocity_cmd,
                                      integrate_odometry, parse_base_info, parse_feedback_line,
                                      parse_orientation)


def test_encode_velocity_cmd():
    assert encode_velocity_cmd(0.1, 0.3) == {"T": 13, "X": 0.1, "Z": 0.3}


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
