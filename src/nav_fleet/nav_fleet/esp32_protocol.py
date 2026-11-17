# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""Pure JSON encode/decode for the Waveshare UGV's ESP32 sub-controller link, plus
differential-drive odometry integration. No ROS2, no pyserial — the serial.Serial(...)
I/O boundary itself lives in esp32_driver.py and stays thin/untested until real
hardware exists (same treatment this project already gives other hardware boundaries).

Protocol commands (T:13/131/142/126/136) reconstructed 2026-08-06 directly from the
real vendor firmware source (waveshareteam/ugv_base_general, General_Driver/*.h) —
NOT the host reference client scripts (ugv_rpi/ugv_jetson's base_ctrl.py), which
turned out to just pass through raw JSON without parsing odom/IMU fields at all. See
CMD_ROS_CTRL (json_cmd.h), baseInfoFeedback() (ugv_advance.h), getIMUData() (IMU_ctrl.h).

**Feedback field SHAPES corrected 2026-08-10 against real hardware** — the
2026-08-06 source read got the two feedback messages' actual field layout backwards
(a genuine discrepancy between the firmware source and its real runtime JSON output,
not a transcription error). Confirmed by directly probing the real ESP32 sub-
controller over /dev/ttyTHS1 (root-cause investigation for the "esp32_driver
produces zero /robot_001/odom or /robot_001/imu/data messages" bug) and capturing
real bytes — see test_esp32_protocol.py's `_real_hardware_capture` tests, which use
those exact captured lines as fixtures:
- T:1001 (FEEDBACK_BASE_INFO, streamed continuously once enabled): wheel speeds
  L/R (m/s) + RAW accel/gyro/mag + wheel encoder tick counts + voltage. NOT fused
  roll/pitch/yaw/temp as originally assumed — those keys don't exist in this message.
- T:1002 (FEEDBACK_IMU_DATA, one-shot response to a T:126 request only, never part
  of the stream): fused roll/pitch/yaw (Euler) PLUS a quaternion. NOT raw
  accel/gyro/mag/temp as originally assumed — those keys don't exist in this message
  either; the raw IMU data is in T:1001 instead. BaseInfo/parse_base_info stayed
  as-is (still the right message for L/R, plus a bonus of raw IMU fields);
  ImuData/parse_imu_data renamed to OrientationData/parse_orientation to match what
  this message actually carries.
"""
import collections
import json
import math
import re

BaseInfo = collections.namedtuple(
    'BaseInfo', ['speed_l', 'speed_r', 'ax', 'ay', 'az', 'gx', 'gy', 'gz',
                 'mx', 'my', 'mz', 'odl', 'odr', 'voltage'])
OrientationData = collections.namedtuple(
    'OrientationData', ['roll', 'pitch', 'yaw', 'q0', 'q1', 'q2', 'q3'])

_FEEDBACK_BASE_INFO = 1001
_FEEDBACK_ORIENTATION = 1002

# QMI8658 raw-count -> physical-unit sensitivity constants (2026-08-12/13 root cause):
# BaseInfo.ax/ay/az/gx/gy/gz are RAW LSB register counts, not already-scaled physical
# units, despite esp32_driver._publish_imu previously passing them straight into a ROS
# Imu message unconverted — flagged as an open, unconfirmed risk in that file's own
# comment since 2026-08-10 ("NOT confirmed against real hardware... confirm before
# trusting these as calibrated m/s^2 / rad/s"). Confirmed broken the hard way: a live
# AMCL investigation found a STATIONARY robot's odom->base_footprint yaw jumping
# through the full +/-pi range every ~100ms, traced through ekf_node's gyro-rate-only
# motion-model input straight back to these unscaled counts (~200x too large once
# treated as rad/s instead of raw LSB).
#
# ACCEL_SENSITIVITY_LSB_PER_G — HIGH confidence, cross-checked against real physics,
# not read blindly from vendor source: two independent real hardware captures
# (2026-08-10's test fixture below, a live 2026-08-12 capture, ~1 month apart) both
# show az~8556-8576 raw counts while the robot sat stationary/level — i.e. ~1g on the
# Z axis. Checked against every QMI8658 accel full-scale range's LSB/g value: only
# +/-4g (8192 LSB/g) lands close to 1g (1.044-1.047g, a plausible few-percent real
# tilt/bias); +/-2g/+/-8g/+/-16g give 0.52g/2.09g/4.18g respectively — all physically
# implausible for a robot sitting still. An automated read of the vendor's own
# QMI8658.cpp claimed a DEFAULT of +/-16g, which this real data directly contradicts —
# exactly the vendor-source-vs-real-runtime mismatch this module's own docstring
# already documents happening twice before on this same protocol. Trusting the
# physics, not the doc.
ACCEL_SENSITIVITY_LSB_PER_G = 8192.0
GRAVITY_M_S2 = 9.80665

# GYRO_SENSITIVITY_LSB_PER_DPS — LOWER confidence, NOT independently cross-checked the
# same way accel was: unlike accel, true angular velocity at rest is 0 for ANY
# sensitivity value, so there's no physical constant in this data to calibrate
# against. This value (16 LSB/dps, the QMI8658's +/-2048dps range) is the vendor
# source's own stated default for gyro; applying it to real stationary-robot raw
# captures (~0-10 raw counts) produces a plausible near-zero angular velocity
# (<0.7 dps / <0.012 rad/s) — consistent with a stationary robot, but a much weaker
# check than accel's gravity cross-check, since many other range values would also
# look "small enough" against these small raw counts. Needs a real calibration test
# before this is trusted the way ACCEL_SENSITIVITY_LSB_PER_G now is — e.g. a
# measured, hand-rotated known angle, mirroring spin_experiment.py's own methodology
# for the wheel-odom rotation-over-report fix. Flagged, not guessed blind — but
# flagged as the SPECIFIC open risk this fix does not close.
GYRO_SENSITIVITY_LSB_PER_DPS = 16.0
_DEG_TO_RAD = math.pi / 180.0


def scale_imu_raw(ax, ay, az, gx, gy, gz):
    """Convert QMI8658 raw LSB counts (BaseInfo.ax/ay/az/gx/gy/gz, as published in the
    real firmware's T:1001 message) into the physical SI units sensor_msgs/Imu
    requires: linear_acceleration in m/s^2, angular_velocity in rad/s. See the
    sensitivity constants' own comments above for the confidence level behind each
    conversion factor — accel is real-physics-verified, gyro is a flagged, unverified
    best estimate pending a real calibration test.

    Pure function (no ROS, no offset/bias correction — that's a separate, still-open
    gap) so it's testable in stage-1-quality like the rest of this module.
    esp32_driver._publish_imu calls this before populating the ROS message.
    """
    accel_scale = GRAVITY_M_S2 / ACCEL_SENSITIVITY_LSB_PER_G
    gyro_scale = _DEG_TO_RAD / GYRO_SENSITIVITY_LSB_PER_DPS
    return (ax * accel_scale, ay * accel_scale, az * accel_scale,
            gx * gyro_scale, gy * gyro_scale, gz * gyro_scale)


class GyroBiasEstimator:
    """Learns the gyro's resting offset while the robot sits still, so the driver can
    subtract it. Pure logic, no ROS.

    Why: on 2026-11-16 the stationary robot's gyro z read +0.0046 rad/s (0.26 deg/s),
    which the heading filter integrated into 22 degrees of false turn in 90 s.

    update() takes one scaled sample (rad/s) and whether the caller believes the
    robot is stationary (wheels reporting zero, no drive command). Samples collect
    into a window; when `window` of them are in hand, the window becomes the new bias
    ONLY if it looks like a still robot: every axis spread (max - min) is within
    `max_spread` and every axis mean within `max_bias`. That second test matters
    because "wheels stopped" is not proof of stillness — the robot can be carried or
    turned by hand. Any non-stationary sample discards the partial window.
    Returns the current bias (0, 0, 0) until the first good window."""

    def __init__(self, window=40, max_spread=0.05, max_bias=0.06):
        self._window = window
        self._max_spread = max_spread
        self._max_bias = max_bias
        self._samples = []
        self.bias = (0.0, 0.0, 0.0)

    def update(self, gx, gy, gz, stationary):
        if not stationary:
            self._samples = []
            return self.bias
        self._samples.append((gx, gy, gz))
        if len(self._samples) >= self._window:
            axes = list(zip(*self._samples))
            means = tuple(sum(a) / len(a) for a in axes)
            quiet = all(max(a) - min(a) <= self._max_spread for a in axes)
            small = all(abs(m) <= self._max_bias for m in means)
            if quiet and small:
                self.bias = means
            self._samples = []
        return self.bias


def encode_velocity_cmd(linear_x, angular_z):
    """CMD_ROS_CTRL (T:13) — documented in-source as (m/s, rad/s), a direct Twist
    mapping. The firmware does its own diff-drive -> L/R wheel-speed math."""
    return {"T": 13, "X": linear_x, "Z": angular_z}


def encode_boot_mission_info():
    """CMD_BOOT_MISSION_INFO (T:602) — asks the controller to print the commands it
    runs at every power-up. The chassis type lives there as a stored T:900 line (see
    parse_chassis_main_type). The reply is plain text lines, not a JSON message."""
    return {"T": 602}


_CHASSIS_LINE = re.compile(r'"T"\s*:\s*900\s*,\s*"main"\s*:\s*(\d+)')


def parse_chassis_main_type(line):
    """Returns the firmware's stored chassis "main" type (1 RaspRover, 2 UGV Rover,
    3 UGV Beast — ugv_base_ros README / mm_settings()) if `line` contains a T:900
    command, else None. Matches the T:602 reply text, e.g.
    '[StepNum: 1 ] - {"T":900,"main":2,"module":0}'.

    Why this matters (found 2026-11-16): this unit shipped with main=3 (tracked UGV
    Beast) stored on a 6-wheel UGV Rover. In that state the firmware mis-scales its
    own speed measurement by 2.53x (so the robot drives 2.5x faster than commanded and
    reports odometry 2.5x short) and reverses motor direction."""
    m = _CHASSIS_LINE.search(line)
    return int(m.group(1)) if m else None


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


def encode_gimbal_cmd(pan_deg, tilt_deg):
    """CMD_GIMBAL_CTRL_SIMPLE (T:133) — commands the pan-tilt mast to an absolute
    pose in degrees. SPD/ACC are both 0 (firmware "as fast as possible" default) —
    this only needs to be sent ONCE at setup time to pin the gimbal forward/level,
    not driven continuously, so there's no need to expose speed/accel here.

    **Confirmed live against real hardware, 2026-08-10** (RealRobotStartup.md A2):
    pan_deg (X) negative = left, positive = right, 0 = forward; tilt_deg (Y)
    negative = down (directly observed), 0 = level, positive = up (inferred by
    symmetry with the confirmed negative direction, not separately observed —
    this robot's own use case only ever needed forward/level + a downward test
    move). Originally sourced from Waveshare's wiki via web search (direct fetches
    403'd) with the sign convention unverified — that gap is now closed."""
    return {"T": 133, "X": pan_deg, "Y": tilt_deg, "SPD": 0, "ACC": 0}


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
    type or is missing an expected field.

    speed_l/speed_r/ax/ay/az/gx/gy/gz are coerced to float — the real firmware sends
    whole-number readings as bare JSON ints (e.g. "ax":-36, confirmed against a real
    capture), and every one of these fields eventually reaches a ROS float64 message
    field (Odometry.twist / Imu.linear_acceleration / Imu.angular_velocity).
    esp32_driver._publish_imu's direct field assignment has no arithmetic to coerce
    an int to float the way _publish_odom's `/2.0` division accidentally does —
    passing an int straight to a geometry_msgs/Vector3 field hard-ABORTS the whole
    process (rosidl's C converter asserts PyFloat_Check rather than raising a
    catchable Python exception). Found 2026-08-10 the hard way: a real crash,
    reproduced from the real captured bytes, not a hypothetical. mx/my/mz/odl/odr
    aren't currently consumed by any ROS message field, so left as-is (ints from the
    firmware, which is what encoder tick counts naturally are anyway)."""
    if not isinstance(data, dict) or data.get("T") != _FEEDBACK_BASE_INFO:
        return None
    try:
        return BaseInfo(speed_l=float(data["L"]), speed_r=float(data["R"]),
                        ax=float(data["ax"]), ay=float(data["ay"]), az=float(data["az"]),
                        gx=float(data["gx"]), gy=float(data["gy"]), gz=float(data["gz"]),
                        mx=data["mx"], my=data["my"], mz=data["mz"],
                        odl=data["odl"], odr=data["odr"], voltage=data["v"])
    except KeyError:
        return None


def parse_orientation(data):
    """T:1002 (FEEDBACK_IMU_DATA, a one-shot reply to a T:126 request) -> fused
    orientation (Euler + quaternion), or None if `data` isn't this message type or
    is missing an expected field. Named for what this message actually carries
    (fused orientation), not the firmware's own "IMU data" feedback-code name — see
    this file's module docstring for why.

    roll/pitch/yaw/q0-q3 are coerced to float for the same reason parse_base_info's
    fields are (see its docstring) — a real capture showed these as bare JSON ints
    too ("r":0 etc.). Not yet wired into a ROS message field (esp32_driver.py's
    self._last_orientation is cached but unused — see its comment), but the same
    hard-abort landmine would hit geometry_msgs/Quaternion the moment it is, so
    fixed here now rather than left for whoever wires it in to rediscover."""
    if not isinstance(data, dict) or data.get("T") != _FEEDBACK_ORIENTATION:
        return None
    try:
        return OrientationData(roll=float(data["r"]), pitch=float(data["p"]),
                               yaw=float(data["y"]), q0=float(data["q0"]),
                               q1=float(data["q1"]), q2=float(data["q2"]),
                               q3=float(data["q3"]))
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
