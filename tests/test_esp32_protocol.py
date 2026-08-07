# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
import math

import pytest

from nav_fleet.esp32_protocol import (BaseInfo, ImuData, encode_enable_feedback_flow,
                                      encode_feedback_flow_interval, encode_get_imu_data,
                                      encode_set_heartbeat_timeout, encode_velocity_cmd,
                                      integrate_odometry, parse_base_info, parse_feedback_line,
                                      parse_imu_data)


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
    data = {"T": 1001, "L": 0.1, "R": 0.12, "r": 0.0, "p": 0.0, "y": 1.5,
            "temp": 30.0, "v": 11.8}
    info = parse_base_info(data)
    assert info == BaseInfo(speed_l=0.1, speed_r=0.12, roll=0.0, pitch=0.0,
                            yaw=1.5, temp=30.0, voltage=11.8)


def test_parse_base_info_wrong_type_returns_none():
    assert parse_base_info({"T": 1002, "L": 0.1}) is None


def test_parse_base_info_missing_field_returns_none():
    assert parse_base_info({"T": 1001, "L": 0.1}) is None


def test_parse_imu_data_valid():
    data = {"T": 1002, "r": 0.0, "p": 0.0, "y": 0.0, "ax": 0.1, "ay": 0.2, "az": 9.8,
            "gx": 0.01, "gy": 0.02, "gz": 0.03, "mx": 10, "my": 11, "mz": 12, "temp": 30.0}
    info = parse_imu_data(data)
    assert info == ImuData(roll=0.0, pitch=0.0, yaw=0.0, ax=0.1, ay=0.2, az=9.8,
                           gx=0.01, gy=0.02, gz=0.03, mx=10, my=11, mz=12, temp=30.0)


def test_parse_imu_data_wrong_type_returns_none():
    assert parse_imu_data({"T": 1001, "L": 0.1}) is None


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
