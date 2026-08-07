# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""Pure JSON encode/decode for the Waveshare UGV's ESP32 sub-controller link, plus
differential-drive odometry integration. No ROS2, no pyserial — the serial.Serial(...)
I/O boundary itself lives in esp32_driver.py and stays thin/untested until real
hardware exists (same treatment this project already gives other hardware boundaries).

Protocol reconstructed 2026-08-06 directly from the real vendor firmware source
(waveshareteam/ugv_base_general, General_Driver/*.h) — NOT the host reference client
scripts (ugv_rpi/ugv_jetson's base_ctrl.py), which turned out to just pass through raw
JSON without parsing odom/IMU fields at all. See CMD_ROS_CTRL (json_cmd.h),
baseInfoFeedback() (ugv_advance.h), getIMUData() (IMU_ctrl.h).

Command "T" codes used here: 13 (velocity), 131 (enable/disable the continuous
telemetry stream), 142 (stream interval), 126 (one-shot raw IMU request), 136
(firmware's own heartbeat/watchdog timeout).

Feedback "T" codes: 1001 (FEEDBACK_BASE_INFO — wheel speeds L/R in m/s + fused
roll/pitch/yaw, streamed continuously once enabled), 1002 (FEEDBACK_IMU_DATA — raw
accel/gyro/mag, one-shot response to a T:126 request only, never part of the stream).
"""
import collections
import json
import math

BaseInfo = collections.namedtuple(
    'BaseInfo', ['speed_l', 'speed_r', 'roll', 'pitch', 'yaw', 'temp', 'voltage'])
ImuData = collections.namedtuple(
    'ImuData', ['roll', 'pitch', 'yaw', 'ax', 'ay', 'az', 'gx', 'gy', 'gz',
               'mx', 'my', 'mz', 'temp'])

_FEEDBACK_BASE_INFO = 1001
_FEEDBACK_IMU_DATA = 1002


def encode_velocity_cmd(linear_x, angular_z):
    """CMD_ROS_CTRL (T:13) — documented in-source as (m/s, rad/s), a direct Twist
    mapping. The firmware does its own diff-drive -> L/R wheel-speed math."""
    return {"T": 13, "X": linear_x, "Z": angular_z}


def encode_enable_feedback_flow(enable):
    """CMD_BASE_FEEDBACK_FLOW (T:131) — must be sent once at startup; the continuous
    T:1001 stream is OFF by default on the firmware side."""
    return {"T": 131, "cmd": 1 if enable else 0}


def encode_feedback_flow_interval(interval_ms):
    """CMD_FEEDBACK_FLOW_INTERVAL (T:142) — minimum ms between streamed T:1001
    messages (firmware default 0 = as fast as its main loop allows)."""
    return {"T": 142, "cmd": interval_ms}


def encode_get_imu_data():
    """CMD_GET_IMU_DATA (T:126) — one-shot request for raw accel/gyro/mag (T:1002).
    NOT part of the continuous stream; esp32_driver polls this on its own timer."""
    return {"T": 126}


def encode_set_heartbeat_timeout(timeout_ms):
    """CMD_HEART_BEAT_SET (T:136) — the firmware's OWN watchdog: zeroes speed if no
    speed command arrives within this many ms (default 3000 on the board). Independent
    of esp32_driver's own watchdog — protects against the Jetson process itself dying."""
    return {"T": 136, "cmd": timeout_ms}


def parse_feedback_line(line):
    """Parse one newline-delimited JSON line from the ESP32. Returns the parsed dict,
    or None on malformed/empty input — a corrupted line must not crash the driver."""
    if not line:
        return None
    try:
        return json.loads(line)
    except (json.JSONDecodeError, ValueError):
        return None


def parse_base_info(data):
    """T:1001 (FEEDBACK_BASE_INFO) -> BaseInfo, or None if `data` isn't this message
    type or is missing an expected field."""
    if not isinstance(data, dict) or data.get("T") != _FEEDBACK_BASE_INFO:
        return None
    try:
        return BaseInfo(speed_l=data["L"], speed_r=data["R"], roll=data["r"],
                        pitch=data["p"], yaw=data["y"], temp=data["temp"],
                        voltage=data["v"])
    except KeyError:
        return None


def parse_imu_data(data):
    """T:1002 (FEEDBACK_IMU_DATA) -> ImuData, or None if `data` isn't this message
    type or is missing an expected field."""
    if not isinstance(data, dict) or data.get("T") != _FEEDBACK_IMU_DATA:
        return None
    try:
        return ImuData(roll=data["r"], pitch=data["p"], yaw=data["y"],
                       ax=data["ax"], ay=data["ay"], az=data["az"],
                       gx=data["gx"], gy=data["gy"], gz=data["gz"],
                       mx=data["mx"], my=data["my"], mz=data["mz"], temp=data["temp"])
    except KeyError:
        return None


def integrate_odometry(x, y, yaw, speed_l, speed_r, track_width, dt):
    """Standard differential-drive dead reckoning from wheel speeds (m/s), midpoint-
    heading method. speed_l/speed_r must use the SAME sign convention as the firmware's
    own T:1001 feedback (L=A=left, R=B=right) — matches encode_velocity_cmd's X/Z
    convention exactly (firmware: setpointA = X - Z*track_width/2, setpointB = X +
    Z*track_width/2, so recombining: omega = (speed_r - speed_l) / track_width)."""
    v = (speed_l + speed_r) / 2.0
    omega = (speed_r - speed_l) / track_width
    mid_yaw = yaw + omega * dt / 2.0
    new_x = x + v * math.cos(mid_yaw) * dt
    new_y = y + v * math.sin(mid_yaw) * dt
    new_yaw = yaw + omega * dt
    return new_x, new_y, new_yaw
