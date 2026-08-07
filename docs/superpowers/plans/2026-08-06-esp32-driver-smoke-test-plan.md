# Real-Robot Driver + Bench Smoke Test Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `esp32_driver` (the ROS2 node bridging the Waveshare UGV's ESP32
sub-controller — odom/IMU in, cmd_vel out) and the attended bench smoke test that
proves the driver layer works before it's ever trusted under Nav2, per the approved
design spec.

**Architecture:** One new pure-function protocol module (`esp32_protocol.py`, unit
testable with no ROS2/hardware) backs a thin ROS2 node (`esp32_driver.py`) that owns
the actual serial I/O. A new `sensors_only_launch.py` brings up the driver layer +
EKF + ball_detector with NO Nav2/map — gated so sim/CI never tries to launch real
hardware drivers, only `ekf_node`/`ball_detector` against Gazebo's existing bridge.
`tools/smoke_test.py` is a third `ROBOT_MODE` (alongside `mission`) in the SAME
container/entrypoint every other robot mode already uses — never inferred, always a
literal env var a human-triggered script hardcodes.

**Tech Stack:** ROS2 Jazzy (rclpy), pyserial, existing project conventions
(`tools/coverage_log.py`'s isolated-table pattern, `tools/mission2_day.py`'s
`BallOps`/`GzBallOps`, `scripts/hil_stage.sh`'s SSH orchestration).

## Global Constraints

- **Design spec (source of truth):**
  `docs/superpowers/specs/2026-08-05-real-robot-driver-smoke-test-design.md`.
- **`ROBOT_MODE` is required, no implicit default — fail loudly if unset.**
  `robot_boot.sh` hardcodes `ROBOT_MODE=mission`, never a variable. Smoke test is
  only ever triggered deliberately from the workstation.
- **Smoke-test results never touch drift metrics.** `smoke_test_runs` is an isolated
  table, never read by `baseline_monitor.check_run()`.
- **ESP32 protocol, verified 2026-08-06 against the real vendor firmware source**
  (`waveshareteam/ugv_base_general`, `General_Driver/*.h` — NOT the host reference
  scripts, which turned out to just pass through raw JSON):
  - Velocity: `{"T":13,"X":<m/s>,"Z":<rad/s>}` — direct Twist mapping, firmware does
    the diff-drive math itself (`TRACK_WIDTH=0.172m`, `WHEEL_D=0.08m`).
  - Enable telemetry stream (must be sent once at startup, off by default):
    `{"T":131,"cmd":1}`. Rate: `{"T":142,"cmd":<ms>}`.
  - Streamed telemetry (`T:1001`): `{"L":<speedA m/s>,"R":<speedB m/s>,"r":roll,
    "p":pitch,"y":yaw,"temp":...,"v":volts}` — wheel speeds + fused orientation
    only, no x/y — `esp32_driver` integrates odometry itself.
  - Raw IMU (`T:1002`, `ax/ay/az/gx/gy/gz/mx/my/mz`) is **one-shot only**
    (`{"T":126}`), NOT part of the continuous stream — **decided with Mike
    2026-08-06:** `esp32_driver` polls it on its own ROS timer.
  - Firmware's own watchdog: zeroes speed after `HEART_BEAT_DELAY` (default
    3000ms) with no speed command; used *in addition to* the driver's own 200ms
    watchdog (per `robot_profiles/jetson_ugv_pt.yaml`), not instead of it.
- **Baud rate: 115200 — corrected 2026-08-06.** `robot_profiles/jetson_ugv_pt.yaml`
  previously said 921600 with no basis found anywhere in the firmware; already fixed
  on `main` ahead of this plan (see that file's own comment for the citation).
- **Interactive prompting is deliberate in `tools/smoke_test.py` only** — the bench
  smoke test is by definition attended; `mission_runner`'s no-prompting rule is
  unaffected.
- **This plan does NOT wire `esp32_driver`/`ldlidar_ros2`/`depthai-ros` into
  `ROBOT_MODE=mission`'s daily-mission path** (`nav2_only_launch.py` is explicitly
  unchanged, per the approved spec's architecture diagram). The real robot's actual
  daily mission still has no real driver layer wired in after this plan lands — this
  plan only proves the driver layer works via the smoke test. Flagged here so it
  isn't silently forgotten; folding the driver layer into mission mode is separate,
  not-yet-scoped follow-up work.
- **`ldlidar_ros2`/`depthai-ros` exact launch wiring is NOT pinned down by this
  plan** (neither package is installed as of 2026-08-06; Mike's manual install,
  ~2026-08-11). `sensors_only_launch.py` exposes `lidar_launch_file`/
  `camera_launch_file` launch arguments as the real extension point, left empty by
  default — verified-real launch files exist today at
  `ldrobotSensorTeam/ldlidar_ros2`'s `launch/{ld06,ld14,ld14p,ld19}.launch.py` (topic
  `scan`, frame `base_laser`, params `port_name`/`serial_baudrate` — needs a remap
  layer to this project's `/robot_001/scan` + URDF frame convention) and
  `luxonis/depthai-ros`'s `jazzy` branch `depthai_ros_driver/launch/camera.launch.py`
  (composable-node container, requires its own `params_file` — topic naming is
  governed by that file's pipeline config, not a simple arg). Confirm the exact
  D500/STL-19P → LDROBOT product-name mapping against the physical unit before
  wiring `lidar_launch_file` for real.

---

## File Structure

- `src/nav_fleet/nav_fleet/esp32_protocol.py` (new) — pure JSON encode/decode +
  differential-drive odometry integration. No ROS2, no pyserial — stage-1 testable.
- `src/nav_fleet/nav_fleet/esp32_driver.py` (new) — ROS2 node: owns the serial port,
  subscribes `cmd_vel`, publishes `odom`/`imu/data`, runs the IMU-poll timer and the
  driver-side watchdog.
- `src/nav_fleet/launch/sensors_only_launch.py` (new) — driver layer + EKF +
  ball_detector, no Nav2/map, `use_sim_time`-gated real-hardware group.
- `tools/smoke_test_log.py` (new) — `smoke_test_runs` table + `log_smoke_test_run()`,
  mirrors `tools/coverage_log.py` exactly.
- `tools/smoke_test.py` (new) — the orchestrator: topic sanity, photo, known-distance
  ball correlation, motion check, summary, CLI.
- `scripts/container_entrypoint.sh` (modify) — `ROBOT_MODE` branch (`mission` |
  `smoke_test`).
- `scripts/robot_boot.sh` (modify) — add hardcoded `-e ROBOT_MODE=mission`.
- `scripts/hil_stage.sh` (modify) — new `smoke` (attended, interactive) and
  `smoke-ci` (CI, `GzBallOps`, non-interactive) subcommands.
- `.github/workflows/ci.yml` (modify) — smoke-test machinery regression in
  `stage-2-gazebo` (sim, bare) and `stage-4-hil` (container, `smoke-ci`).
- `src/nav_fleet/package.xml` (modify) — `<exec_depend>python3-serial</exec_depend>`.
- `Dockerfile` (modify) — `python3-serial` apt package.
- `robot_profiles/jetson_ugv_pt.yaml` — already fixed on `main` (baud 115200), no
  further change needed by this plan.

---

### Task 1: `esp32_protocol.py` — pure encode/decode + odometry integration

**Files:**
- Create: `src/nav_fleet/nav_fleet/esp32_protocol.py`
- Test: `tests/test_esp32_protocol.py`

**Interfaces:**
- Produces: `encode_velocity_cmd(linear_x, angular_z) -> dict`,
  `encode_enable_feedback_flow(enable: bool) -> dict`,
  `encode_feedback_flow_interval(interval_ms: int) -> dict`,
  `encode_get_imu_data() -> dict`, `encode_set_heartbeat_timeout(timeout_ms: int) -> dict`,
  `parse_feedback_line(line: str) -> dict | None`,
  `BaseInfo` (namedtuple: `speed_l, speed_r, roll, pitch, yaw, temp, voltage`),
  `parse_base_info(data: dict) -> BaseInfo | None`,
  `ImuData` (namedtuple: `roll, pitch, yaw, ax, ay, az, gx, gy, gz, mx, my, mz, temp`),
  `parse_imu_data(data: dict) -> ImuData | None`,
  `integrate_odometry(x, y, yaw, speed_l, speed_r, track_width, dt) -> (x, y, yaw)`.
  All consumed directly by Task 2 (`esp32_driver.py`) and Task 6
  (`compute_ball_placement_xy`, co-located in `tools/smoke_test.py`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_esp32_protocol.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_esp32_protocol.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'nav_fleet.esp32_protocol'`

- [ ] **Step 3: Write the implementation**

```python
# src/nav_fleet/nav_fleet/esp32_protocol.py
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_esp32_protocol.py -v`
Expected: 17 passed

- [ ] **Step 5: Commit**

```bash
git add src/nav_fleet/nav_fleet/esp32_protocol.py tests/test_esp32_protocol.py
git commit -m "feat: esp32_protocol — pure JSON codec + diff-drive odometry integration"
```

---

### Task 2: `esp32_driver.py` — the ROS2 node

**Files:**
- Create: `src/nav_fleet/nav_fleet/esp32_driver.py`
- Modify: `src/nav_fleet/setup.py:36` (add console_scripts entry, alongside
  `'ball_detector = nav_fleet.ball_detector:main',`)
- Modify: `src/nav_fleet/package.xml` (add `<exec_depend>python3-serial</exec_depend>`
  next to the existing `<exec_depend>robot_localization</exec_depend>`)
- Modify: `Dockerfile:13-18` (add `python3-serial` to the `apt-get install` list,
  alongside `ros-jazzy-vision-msgs`)
- Test: `tests/test_esp32_driver.py`

**Interfaces:**
- Consumes: everything from Task 1 (`esp32_protocol.py`).
- Produces: `Esp32Driver` (rclpy `Node` subclass), console script `esp32_driver`.
  Consumed by Task 3's `sensors_only_launch.py` as `package='nav_fleet',
  executable='esp32_driver'`.

- [ ] **Step 1: Add the system dependency declarations**

```xml
<!-- src/nav_fleet/package.xml — add this line next to the existing
     <exec_depend>robot_localization</exec_depend> -->
<exec_depend>python3-serial</exec_depend>
```

```dockerfile
# Dockerfile — add python3-serial to the existing apt-get install list
RUN apt-get update && apt-get install -y \
    python3-pip \
    python3-serial \
    ...
    ros-jazzy-vision-msgs \
    ros-jazzy-robot-localization \
    ...
```

Manual step (not run by this plan, per the Manual Jetson Installs convention — Mike
installs system packages himself): `sudo apt install python3-serial` on the
workstation's ROS2 environment before Task 2's node can actually run outside CI/the
container (`~/fleet-env`'s Python must also see `pyserial` — the apt package installs
it into the system Python `dist-packages`, which `~/fleet-env` inherits via
`--system-site-packages` if configured that way; confirm with `python3 -c "import
serial"` before relying on it, don't assume).

- [ ] **Step 2: Write the failing tests**

```python
# tests/test_esp32_driver.py
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
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `source install/setup.bash && python -m pytest tests/test_esp32_driver.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'nav_fleet.esp32_driver'`

- [ ] **Step 4: Write the implementation**

```python
# src/nav_fleet/nav_fleet/esp32_driver.py
# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""ROS2 node bridging the Waveshare UGV's ESP32 sub-controller (odom + IMU in,
cmd_vel out) — real-robot driver layer + bench smoke-test design spec
(docs/superpowers/specs/2026-08-05-real-robot-driver-smoke-test-design.md).

Design intent (from the spec): from ekf_node/Nav2's point of view, this node is a
drop-in replacement for Gazebo's sim bridge — same topics (/robot_001/odom,
/robot_001/imu/data, subscribes /robot_001/cmd_vel), same message types, same frame
convention (unprefixed odom/base_footprint, matching ekf.yaml's odom0/imu0 topic
names).

Only ever launched by sensors_only_launch.py's real-hardware group (use_sim_time
false) — sim/CI never constructs this node; Gazebo's bridge publishes the same
topics directly instead.
"""
import json
import math
import threading
import time

import rclpy
import serial
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from rclpy.node import Node
from sensor_msgs.msg import Imu

from nav_fleet.esp32_protocol import (encode_enable_feedback_flow, encode_get_imu_data,
                                      encode_velocity_cmd, integrate_odometry,
                                      parse_base_info, parse_feedback_line, parse_imu_data)


class Esp32Driver(Node):

    def __init__(self):
        super().__init__('esp32_driver')
        self.declare_parameter('serial_device', '/dev/ttyUSB0')
        self.declare_parameter('baud', 115200)
        self.declare_parameter('watchdog_timeout_ms', 200)
        self.declare_parameter('imu_poll_hz', 50.0)
        # Must match the ESP32 firmware's own TRACK_WIDTH constant (ugv_config.h) —
        # 0.172 for the active "UGV Rover" mainType config as of 2026-08-06.
        self.declare_parameter('track_width', 0.172)

        self._track_width = self.get_parameter('track_width').value
        self._watchdog_timeout_s = self.get_parameter('watchdog_timeout_ms').value / 1000.0

        device = self.get_parameter('serial_device').value
        baud = self.get_parameter('baud').value
        try:
            self._ser = serial.Serial(device, baud, timeout=1.0)
        except serial.SerialException as exc:
            # Fail loudly on init, don't retry-forever-silently (design spec's Error
            # handling section — matches this project's established convention).
            self.get_logger().fatal(f"esp32_driver: cannot open {device} @ {baud}: {exc}")
            raise
        self._write_lock = threading.Lock()

        self._x = 0.0
        self._y = 0.0
        self._yaw = 0.0
        self._last_base_info_time = None
        self._last_cmd_time = time.time()
        self._stopped = False

        self.odom_pub = self.create_publisher(Odometry, '/robot_001/odom', 10)
        self.imu_pub = self.create_publisher(Imu, '/robot_001/imu/data', 10)
        self.create_subscription(Twist, '/robot_001/cmd_vel', self._cmd_vel_cb, 10)

        self._send(encode_enable_feedback_flow(True))

        imu_poll_hz = self.get_parameter('imu_poll_hz').value
        self.create_timer(1.0 / imu_poll_hz, self._imu_poll_cb)
        self.create_timer(self._watchdog_timeout_s / 2.0, self._watchdog_cb)

        self._reader_thread = threading.Thread(target=self._read_loop, daemon=True)
        self._reader_thread.start()

        self.get_logger().info(
            f"esp32_driver up — {device}@{baud}, track_width={self._track_width}m, "
            f"watchdog={self.get_parameter('watchdog_timeout_ms').value}ms")

    def _send(self, cmd):
        line = (json.dumps(cmd) + '\n').encode('utf-8')
        with self._write_lock:
            self._ser.write(line)

    def _cmd_vel_cb(self, msg):
        self._last_cmd_time = time.time()
        self._stopped = False
        self._send(encode_velocity_cmd(msg.linear.x, msg.angular.z))

    def _imu_poll_cb(self):
        self._send(encode_get_imu_data())

    def _watchdog_cb(self):
        # Driver-side watchdog — proactive, in ADDITION to the firmware's own
        # HEART_BEAT_DELAY (3000ms default) — see Global Constraints in the plan.
        if self._stopped:
            return
        if time.time() - self._last_cmd_time > self._watchdog_timeout_s:
            self._stopped = True
            self._send(encode_velocity_cmd(0.0, 0.0))
            self.get_logger().warn('esp32_driver: cmd_vel watchdog tripped — zero-velocity sent')

    def _read_loop(self):
        while rclpy.ok():
            try:
                raw = self._ser.readline()
            except serial.SerialException as exc:
                self.get_logger().error(f'esp32_driver: serial read error: {exc}')
                time.sleep(0.5)
                continue
            if not raw:
                continue  # readline timeout, no data yet
            data = parse_feedback_line(raw.decode('utf-8', errors='replace'))
            if data is None:
                continue
            base_info = parse_base_info(data)
            if base_info is not None:
                self._publish_odom(base_info)
                continue
            imu_data = parse_imu_data(data)
            if imu_data is not None:
                self._publish_imu(imu_data)

    def _publish_odom(self, info):
        now = self.get_clock().now()
        now_s = now.nanoseconds / 1e9
        if self._last_base_info_time is not None:
            dt = now_s - self._last_base_info_time
            if dt > 0.0:
                self._x, self._y, self._yaw = integrate_odometry(
                    self._x, self._y, self._yaw, info.speed_l, info.speed_r,
                    self._track_width, dt)
        self._last_base_info_time = now_s

        msg = Odometry()
        msg.header.stamp = now.to_msg()
        msg.header.frame_id = 'odom'
        msg.child_frame_id = 'base_footprint'
        msg.pose.pose.position.x = self._x
        msg.pose.pose.position.y = self._y
        msg.pose.pose.orientation.z = math.sin(self._yaw / 2.0)
        msg.pose.pose.orientation.w = math.cos(self._yaw / 2.0)
        msg.twist.twist.linear.x = (info.speed_l + info.speed_r) / 2.0
        msg.twist.twist.angular.z = (info.speed_r - info.speed_l) / self._track_width
        self.odom_pub.publish(msg)

    def _publish_imu(self, info):
        msg = Imu()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = 'imu_link'
        # ax/ay/az/gx/gy/gz units are NOT confirmed against real hardware — the
        # firmware's own field names ("Raw" in the C++ struct names) are ambiguous
        # about whether QMI8658.cpp's driver already scales to physical SI units or
        # returns raw LSB counts. Passed through as-is; confirm on real hardware
        # before trusting these as calibrated m/s^2 / rad/s (design spec's "Known
        # implementation-time risks" pattern — flag, don't guess).
        msg.linear_acceleration.x = info.ax
        msg.linear_acceleration.y = info.ay
        msg.linear_acceleration.z = info.az
        msg.angular_velocity.x = info.gx
        msg.angular_velocity.y = info.gy
        msg.angular_velocity.z = info.gz
        msg.orientation_covariance[0] = -1.0  # orientation not populated from this message
        self.imu_pub.publish(msg)


def main():
    rclpy.init()
    node = Esp32Driver()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
```

```python
# src/nav_fleet/setup.py — add this line inside entry_points/console_scripts,
# alongside the existing 'ball_detector = nav_fleet.ball_detector:main',
'esp32_driver = nav_fleet.esp32_driver:main',
```

- [ ] **Step 5: Add `test_esp32_driver.py` to stage-1's ignore list**

```yaml
# .github/workflows/ci.yml — stage-1-quality's pytest step: add
# --ignore=tests/test_esp32_driver.py alongside the existing
# --ignore=tests/test_navigation.py etc.
```

- [ ] **Step 6: Build and run tests to verify they pass**

Run: `colcon build --symlink-install && source install/setup.bash && python -m pytest tests/test_esp32_driver.py -v`
Expected: 6 passed

- [ ] **Step 7: Commit**

```bash
git add src/nav_fleet/nav_fleet/esp32_driver.py src/nav_fleet/setup.py \
        src/nav_fleet/package.xml Dockerfile tests/test_esp32_driver.py \
        .github/workflows/ci.yml
git commit -m "feat: esp32_driver ROS2 node — serial bridge to the ESP32 sub-controller"
```

---

### Task 3: `sensors_only_launch.py`

**Files:**
- Create: `src/nav_fleet/launch/sensors_only_launch.py`

**Interfaces:**
- Consumes: `Esp32Driver` (Task 2, via `package='nav_fleet', executable='esp32_driver'`),
  `ekf_node`/`ball_detector` (existing, same as `nav2_only_launch.py`).
- Produces: launch arguments `use_sim_time`, `hsv_config`, `serial_device`,
  `serial_baud`, `lidar_launch_file`, `camera_launch_file` — consumed by Task 8's
  `container_entrypoint.sh` smoke_test branch and Task 10's CI regression steps.

- [ ] **Step 1: Write the launch file**

```python
# src/nav_fleet/launch/sensors_only_launch.py
# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""Driver layer + EKF + ball_detector, deliberately WITHOUT Nav2/AMCL/map_server —
the bench smoke test's launch file (design spec §Architecture). No map required, so
this runs even before bedroom_real.yaml exists.

use_sim_time gating: sim/CI regression relies entirely on Gazebo's own bridge for
/robot_001/{odom,imu/data,scan,camera/image_raw} — matching how nav2_only_launch.py
never launches its own odom/scan/camera source either. esp32_driver/ldlidar_ros2/
depthai-ros are real-hardware-only and skipped entirely when use_sim_time is true.
"""
import pathlib

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, GroupAction, IncludeLaunchDescription
from launch.conditions import IfCondition, UnlessCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PythonExpression
from launch_ros.actions import Node

PKG = pathlib.Path(__file__).parent.parent


def generate_launch_description():
    use_sim_time_arg = DeclareLaunchArgument(
        'use_sim_time', default_value='true',
        description='true for sim/CI regression (Gazebo bridge feeds odom/imu/scan/'
                    'camera directly — esp32_driver/ldlidar_ros2/depthai-ros are '
                    'skipped entirely); false for the real robot bench.',
    )
    hsv_config_arg = DeclareLaunchArgument(
        'hsv_config', default_value=str(PKG / 'config' / 'hsv_gazebo.yaml'),
        description='ball_detector HSV thresholds — hsv_gazebo.yaml for sim, '
                    'hsv_realcam.yaml for the real robot bench',
    )
    serial_device_arg = DeclareLaunchArgument(
        'serial_device', default_value='/dev/ttyUSB0',
        description='ESP32 sub-controller serial device — depends on how Mike wires '
                    'the physical connection; real-robot-only, unused when '
                    'use_sim_time is true',
    )
    serial_baud_arg = DeclareLaunchArgument(
        'serial_baud', default_value='115200',
        description='Confirmed 2026-08-06 against the real ugv_base_general firmware '
                    'source (Serial.begin(115200)) — see robot_profiles/jetson_ugv_pt.yaml',
    )
    lidar_launch_file_arg = DeclareLaunchArgument(
        'lidar_launch_file', default_value='',
        description="Absolute path to ldlidar_ros2's own launch file for the exact "
                    "physical model (D500/STL-19P) — NOT pinned by this project yet "
                    "(package not installed as of 2026-08-06). Left empty = skipped "
                    "even in real-hardware mode, until Mike wires this in.",
    )
    camera_launch_file_arg = DeclareLaunchArgument(
        'camera_launch_file', default_value='',
        description="Absolute path to depthai-ros's own launch file (OAK-D Lite) — "
                    "NOT pinned by this project yet. Left empty = skipped even in "
                    "real-hardware mode, until Mike wires this in.",
    )

    esp32_driver = Node(
        package='nav_fleet',
        executable='esp32_driver',
        name='esp32_driver',
        output='screen',
        parameters=[{'serial_device': LaunchConfiguration('serial_device'),
                     'baud': LaunchConfiguration('serial_baud')}],
    )

    # Real launch files exist today (verified 2026-08-06) at ldrobotSensorTeam/
    # ldlidar_ros2's launch/{ld06,ld14,ld14p,ld19}.launch.py and luxonis/depthai-ros's
    # jazzy-branch depthai_ros_driver/launch/camera.launch.py — neither is wired to a
    # default path here (see this plan's Global Constraints: exact model/params not
    # yet confirmed against the physical hardware). PythonExpression guards each
    # include so an empty path is simply skipped, not a launch error.
    lidar_include = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(LaunchConfiguration('lidar_launch_file')),
        condition=IfCondition(PythonExpression(
            ["'", LaunchConfiguration('lidar_launch_file'), "' != ''"])),
    )
    camera_include = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(LaunchConfiguration('camera_launch_file')),
        condition=IfCondition(PythonExpression(
            ["'", LaunchConfiguration('camera_launch_file'), "' != ''"])),
    )

    real_hardware_drivers = GroupAction(
        condition=UnlessCondition(LaunchConfiguration('use_sim_time')),
        actions=[esp32_driver, lidar_include, camera_include],
    )

    # Always on, both modes — matches nav2_only_launch.py's own always-on pattern
    # for these two nodes exactly (same params, same remappings).
    ekf_node = Node(
        package='robot_localization',
        executable='ekf_node',
        name='ekf_filter_node',
        output='screen',
        parameters=[str(PKG / 'config' / 'ekf.yaml'),
                    {'use_sim_time': LaunchConfiguration('use_sim_time')}],
        remappings=[
            ('/tf', '/robot_001/tf'),
            ('/tf_static', '/robot_001/tf_static'),
            ('odometry/filtered', '/robot_001/odometry/filtered'),
        ],
    )
    ball_detector = Node(
        package='nav_fleet',
        executable='ball_detector',
        name='ball_detector',
        output='screen',
        parameters=[{'use_sim_time': LaunchConfiguration('use_sim_time'),
                     'hsv_config': LaunchConfiguration('hsv_config')}],
    )

    return LaunchDescription([
        use_sim_time_arg, hsv_config_arg, serial_device_arg, serial_baud_arg,
        lidar_launch_file_arg, camera_launch_file_arg,
        real_hardware_drivers, ekf_node, ball_detector,
    ])
```

- [ ] **Step 2: Verify standalone (per the `DeclareLaunchArgument`-must-be-in-the-
  returned-list gotcha — always test a launch file standalone, not just composed)**

Run (with `sim_only_launch.py` already up in another terminal, matching the Task 10
CI step's own sequencing):
```bash
source install/setup.bash
ros2 launch nav_fleet sensors_only_launch.py use_sim_time:=true
```
Expected: `ekf_filter_node` and `ball_detector` start cleanly, no
`launch configuration '...' does not exist` error. Confirm with
`ros2 node list | grep -E "ekf_filter_node|ball_detector"` in a second terminal — no
`esp32_driver` node should appear (real-hardware group correctly skipped).

- [ ] **Step 3: Commit**

```bash
git add src/nav_fleet/launch/sensors_only_launch.py
git commit -m "feat: sensors_only_launch.py — driver layer + EKF + ball_detector, no Nav2"
```

---

### Task 4: `tools/smoke_test_log.py` — `smoke_test_runs` table

**Files:**
- Create: `tools/smoke_test_log.py`
- Test: `tests/test_smoke_test_log.py`

**Interfaces:**
- Consumes: `tools.telemetry_logger.DB_PATH`.
- Produces: `init_db(db_path)`, `log_smoke_test_run(runner_type=, overall_pass=,
  checks=, commit_sha=, ci_run_number=, db_path=) -> int`. Consumed by Task 7
  (`tools/smoke_test.py`'s orchestrator).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_smoke_test_log.py
# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
import pathlib
import sqlite3
import subprocess
import sys

from tools import smoke_test_log


def test_init_db_creates_smoke_test_runs_table(tmp_path):
    db_path = str(tmp_path / "test.db")
    smoke_test_log.init_db(db_path)

    conn = sqlite3.connect(db_path)
    tables = {row[0] for row in
              conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert "smoke_test_runs" in tables


def test_log_smoke_test_run_inserts_row_and_returns_id(tmp_path):
    db_path = str(tmp_path / "test.db")
    checks = {"odom": {"pass": True, "measured_hz": 52.0}}

    row_id = smoke_test_log.log_smoke_test_run(
        runner_type="local", overall_pass=True, checks=checks,
        commit_sha="abc123", ci_run_number=42, db_path=db_path,
    )

    assert row_id is not None
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM smoke_test_runs WHERE id = ?", (row_id,)).fetchone()
    conn.close()
    assert row["runner_type"] == "local"
    assert row["overall_pass"] == 1
    assert row["commit_sha"] == "abc123"
    assert row["ci_run_number"] == 42
    assert '"odom"' in row["checks_json"]
    assert row["timestamp"] is not None


def test_log_smoke_test_run_omitted_fields_stay_null(tmp_path):
    db_path = str(tmp_path / "test.db")

    row_id = smoke_test_log.log_smoke_test_run(overall_pass=False, db_path=db_path)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM smoke_test_runs WHERE id = ?", (row_id,)).fetchone()
    conn.close()
    assert row["runner_type"] is None
    assert row["commit_sha"] is None
    assert row["checks_json"] is None


def test_cli_logs_a_row_via_db_flag(tmp_path):
    db_path = str(tmp_path / "test.db")

    result = subprocess.run(
        [sys.executable, "-m", "tools.smoke_test_log",
         "--runner-type", "local", "--overall-pass", "1",
         "--checks-json", '{"odom": {"pass": true}}',
         "--commit-sha", "deadbeef", "--ci-run-number", "7", "--db", db_path],
        capture_output=True, text=True,
    )

    assert result.returncode == 0, result.stderr
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM smoke_test_runs").fetchone()
    conn.close()
    assert row["overall_pass"] == 1
    assert row["commit_sha"] == "deadbeef"


def test_smoke_test_runs_never_referenced_by_baseline_monitor():
    """Isolated-table guarantee (design spec) — smoke_test_runs must never feed drift
    tracking, same as coverage_runs/vlm_canary_log."""
    baseline_src = (pathlib.Path(__file__).resolve().parent.parent
                    / 'tools' / 'baseline_monitor.py')
    assert 'smoke_test_runs' not in baseline_src.read_text()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_smoke_test_log.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tools.smoke_test_log'`

- [ ] **Step 3: Write the implementation**

```python
# tools/smoke_test_log.py
# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""Bench smoke-test result logging: one row per tools/smoke_test.py run into FLEET_DB.

Isolated-table convention, same shape as coverage_log.py/diagnosis_log.py/
vlm_canary.py — smoke_test_runs is NEVER read by baseline_monitor.check_run() (drift
tracking only reads the runs/steps mission-telemetry tables); a bench smoke test is a
driver-layer sanity check, not a mission, and must never be able to move a drift
baseline.

Run standalone: python -m tools.smoke_test_log --runner-type local --overall-pass 1 \
  --checks-json '{"odom": {...}}' [--commit-sha SHA] [--ci-run-number N] [--db PATH]
"""
import argparse
import json
import os
import sqlite3
import sys
import time

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)

from tools.telemetry_logger import DB_PATH  # noqa: E402


def init_db(db_path: str = DB_PATH):
    parent = os.path.dirname(db_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS smoke_test_runs (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp       TEXT,
            runner_type     TEXT,
            commit_sha      TEXT,
            ci_run_number   INTEGER,
            overall_pass    INTEGER,
            checks_json     TEXT
        )
    """)
    conn.commit()
    conn.close()


def log_smoke_test_run(runner_type=None, overall_pass=None, checks=None,
                       commit_sha=None, ci_run_number=None, db_path: str = DB_PATH) -> int:
    """Insert one row into `smoke_test_runs`. `checks` is a dict (per-check name ->
    {'pass': bool, ...measured values}), stored as a JSON string. Returns the new
    row's id."""
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO smoke_test_runs "
        "(timestamp, runner_type, commit_sha, ci_run_number, overall_pass, checks_json) "
        "VALUES (?,?,?,?,?,?)",
        (time.strftime("%Y-%m-%dT%H:%M:%S"), runner_type, commit_sha, ci_run_number,
         int(bool(overall_pass)) if overall_pass is not None else None,
         json.dumps(checks) if checks is not None else None),
    )
    row_id = cur.lastrowid
    conn.commit()
    conn.close()
    return row_id


def main():
    parser = argparse.ArgumentParser(
        description="Log one bench smoke-test run's result to FLEET_DB"
    )
    parser.add_argument("--runner-type", default=None)
    parser.add_argument("--overall-pass", type=int, choices=[0, 1], default=None)
    parser.add_argument("--checks-json", default=None,
                        help="JSON string, e.g. output of json.dumps(checks)")
    parser.add_argument("--commit-sha", default=None)
    parser.add_argument("--ci-run-number", type=int, default=None)
    parser.add_argument("--db", default=DB_PATH)
    args = parser.parse_args()

    checks = json.loads(args.checks_json) if args.checks_json else None
    log_smoke_test_run(
        runner_type=args.runner_type,
        overall_pass=bool(args.overall_pass) if args.overall_pass is not None else None,
        checks=checks, commit_sha=args.commit_sha, ci_run_number=args.ci_run_number,
        db_path=args.db,
    )


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_smoke_test_log.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add tools/smoke_test_log.py tests/test_smoke_test_log.py
git commit -m "feat: smoke_test_log — isolated smoke_test_runs table, never read by baseline_monitor"
```

---

### Task 5: `tools/smoke_test.py` Part 1 — topic sanity checks

**Files:**
- Create: `tools/smoke_test.py`
- Test: `tests/test_smoke_test.py`

**Interfaces:**
- Consumes: nothing yet built (this task's functions are pure or take an already-
  constructed rclpy `Node`).
- Produces: `load_robot_profile(path) -> dict`, `is_degenerate_scan(msg) -> bool`,
  `compute_ball_placement_xy(x, y, yaw, distance_m) -> (x, y)`,
  `check_topic(node, topic, msg_type, hz_min, degenerate_fn, window_s=3.0) -> dict`.
  Consumed by Task 6/7 (rest of `tools/smoke_test.py`) and by Task 6's ball
  correlation check.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_smoke_test.py
# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""Requires a live ROS2 environment (imports rclpy at module level via tools.smoke_test)
— same --ignore treatment as test_esp32_driver.py in stage-1-quality, run in
stage-2-gazebo. Doesn't need Gazebo for THIS file's tests specifically (a bare rclpy
context + a real publisher is enough), but stays out of stage-1 since rclpy itself
isn't installed there.
"""
import math
import time

import pytest
import rclpy
from sensor_msgs.msg import LaserScan

from tools.smoke_test import (check_topic, compute_ball_placement_xy, is_degenerate_scan,
                              load_robot_profile)


@pytest.fixture(scope='module', autouse=True)
def ros_context():
    rclpy.init()
    yield
    rclpy.try_shutdown()


def test_load_robot_profile_reads_real_profile():
    profile = load_robot_profile('robot_profiles/jetson_ugv_pt.yaml')
    assert profile['sensors']['odometry']['hz_min'] == 50
    assert profile['sub_controller']['baud'] == 115200


def test_is_degenerate_scan_all_inf():
    msg = LaserScan()
    msg.ranges = [float('inf')] * 10
    assert is_degenerate_scan(msg) is True


def test_is_degenerate_scan_real_readings():
    msg = LaserScan()
    msg.ranges = [1.2, 1.3, float('inf'), 0.9]
    assert is_degenerate_scan(msg) is False


def test_compute_ball_placement_xy_facing_positive_x():
    x, y = compute_ball_placement_xy(0.0, 0.0, 0.0, 0.305)
    assert x == pytest.approx(0.305)
    assert y == pytest.approx(0.0, abs=1e-9)


def test_compute_ball_placement_xy_facing_positive_y():
    x, y = compute_ball_placement_xy(1.0, 2.0, math.pi / 2, 0.305)
    assert x == pytest.approx(1.0, abs=1e-9)
    assert y == pytest.approx(2.305)


def test_check_topic_measures_hz_and_flags_low_rate():
    node = rclpy.create_node('test_check_topic_low_rate')
    pub = node.create_publisher(LaserScan, '/test_smoke_topic_low', 10)
    try:
        deadline = time.time() + 1.0
        while time.time() < deadline:
            msg = LaserScan()
            msg.ranges = [1.0, 1.0]
            pub.publish(msg)
            time.sleep(0.5)  # ~2 Hz, well under a 10 Hz hz_min
        result = check_topic(node, '/test_smoke_topic_low', LaserScan, hz_min=10,
                             degenerate_fn=is_degenerate_scan, window_s=1.0)
        assert result['pass'] is False
        assert result['message_count'] >= 1
    finally:
        node.destroy_node()


def test_check_topic_no_messages_received():
    node = rclpy.create_node('test_check_topic_silent')
    try:
        result = check_topic(node, '/nobody_publishes_here', LaserScan, hz_min=1,
                             degenerate_fn=is_degenerate_scan, window_s=0.5)
        assert result['pass'] is False
        assert result['message_count'] == 0
        assert result['degenerate'] is None
    finally:
        node.destroy_node()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source install/setup.bash && python -m pytest tests/test_smoke_test.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tools.smoke_test'`

- [ ] **Step 3: Write the implementation (Part 1 of 3 — this file grows in Tasks 6-7)**

```python
# tools/smoke_test.py
# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""Bench smoke-test orchestrator (design spec §tools/smoke_test.py). Attended, bench-
side sanity check for the driver layer: topic Hz/sanity, one photo, a known-distance
ball correlation check, and an odom-verified motion pulse — BEFORE the driver layer is
ever trusted under Nav2. Interactive prompting is deliberate here (unlike
mission_runner's hard no-prompting rule) — a human runs this standing at the bench.

Run: python -m tools.smoke_test [--ball-ops operator|gz] [--runner-type local] ...
"""
import argparse
import math
import pathlib
import sys
import time

import rclpy
import yaml

REPO_DIR = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_PROFILE = str(REPO_DIR / 'robot_profiles' / 'jetson_ugv_pt.yaml')


def load_robot_profile(path):
    """Load a robot_profiles/*.yaml file (first real consumer of its sensors.*.hz_min
    values, per the design spec — this profile was previously documentation-only)."""
    with open(path) as f:
        return yaml.safe_load(f)


def is_degenerate_scan(msg):
    """True if every range reading is non-finite or non-positive — the lidar 'exists
    on the topic' but never actually initialized."""
    real_readings = [r for r in msg.ranges if math.isfinite(r) and r > 0.0]
    return len(real_readings) == 0


def compute_ball_placement_xy(robot_x, robot_y, robot_yaw, distance_m):
    """The known-distance ball-placement point (design spec: 'known-distance ball
    placement, not a vague wave') — exactly `distance_m` directly ahead of the robot's
    CURRENT heading, so this works regardless of which world/coordinate frame the
    robot happens to start in."""
    return (robot_x + distance_m * math.cos(robot_yaw),
            robot_y + distance_m * math.sin(robot_yaw))


def check_topic(node, topic, msg_type, hz_min, degenerate_fn, window_s=3.0):
    """Subscribe to `topic` for `window_s` seconds. PASS requires: message rate >=
    hz_min AND the most recently received message is not degenerate per degenerate_fn.
    Returns {'pass', 'measured_hz', 'message_count', 'degenerate' (None if zero
    messages received)}."""
    state = {'count': 0, 'last_msg': None}

    def _cb(msg):
        state['count'] += 1
        state['last_msg'] = msg

    sub = node.create_subscription(msg_type, topic, _cb, 10)
    deadline = time.time() + window_s
    while time.time() < deadline:
        rclpy.spin_once(node, timeout_sec=0.1)
    node.destroy_subscription(sub)

    measured_hz = state['count'] / window_s
    degenerate = degenerate_fn(state['last_msg']) if state['last_msg'] is not None else None
    passed = measured_hz >= hz_min and degenerate is False
    return {'pass': passed, 'measured_hz': round(measured_hz, 2),
            'message_count': state['count'], 'degenerate': degenerate}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_smoke_test.py -v`
Expected: 7 passed

- [ ] **Step 5: Add to stage-1's ignore list and commit**

```yaml
# .github/workflows/ci.yml — stage-1-quality's pytest step: add
# --ignore=tests/test_smoke_test.py
```

```bash
git add tools/smoke_test.py tests/test_smoke_test.py .github/workflows/ci.yml
git commit -m "feat: smoke_test.py part 1 — topic Hz/degenerate-payload checks"
```

---

### Task 6: `tools/smoke_test.py` Part 2 — photo + known-distance ball correlation

**Files:**
- Modify: `tools/smoke_test.py` (append to Task 5's file)
- Modify: `tests/test_smoke_test.py` (append)

**Interfaces:**
- Consumes: `tools.mission2_day.GzBallOps` (existing), Task 5's `check_topic`-style
  subscribe pattern, Task 5's `compute_ball_placement_xy`.
- Produces: `OperatorPlaceBallOps` (class), `is_degenerate_image(rgb) -> bool`,
  `check_photo(node, out_path=None) -> dict`, `check_ball_correlation(node, ball_ops,
  known_distance_m=, tolerance_m=, window_s=) -> dict`. Consumed by Task 7's
  orchestrator.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_smoke_test.py — append these imports and tests
import numpy as np
from unittest.mock import MagicMock, patch

from tools.smoke_test import OperatorPlaceBallOps, is_degenerate_image


def test_is_degenerate_image_uniform_black():
    rgb = np.zeros((10, 10, 3), dtype=np.uint8)
    assert is_degenerate_image(rgb) is True


def test_is_degenerate_image_real_content():
    rgb = np.zeros((10, 10, 3), dtype=np.uint8)
    rgb[0, 0] = [255, 0, 0]
    rgb[5, 5] = [0, 255, 0]
    assert is_degenerate_image(rgb) is False


def test_operator_place_ball_ops_prompts_with_inches(monkeypatch):
    prompts = []
    monkeypatch.setattr('builtins.input', lambda p: prompts.append(p) or '')
    OperatorPlaceBallOps().place('yellow', 0.305)
    assert len(prompts) == 1
    assert 'yellow' in prompts[0]
    assert '12' in prompts[0]  # 0.305 m -> ~12 inches
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_smoke_test.py -v -k "degenerate_image or operator_place"`
Expected: FAIL — `ImportError: cannot import name 'OperatorPlaceBallOps'`

- [ ] **Step 3: Append the implementation**

```python
# tools/smoke_test.py — append these imports at the top (alongside the existing ones)
import numpy as np
from sensor_msgs.msg import Image, Imu, LaserScan
from vision_msgs.msg import Detection2DArray

from nav_fleet.image_io import image_msg_to_png, image_msg_to_rgb
from tools.ground_truth import get_ground_truth_xy
from tools.mission2_day import GzBallOps
from tools.telemetry_logger import PHOTO_DIR

KNOWN_DISTANCE_M = 0.305       # 12 inches — design spec §3
DISTANCE_TOLERANCE_M = 0.102   # ~4 inches placement-imprecision tolerance — design spec §3
FORWARD_ARC_HALF_WIDTH_RAD = math.radians(15)


# tools/smoke_test.py — append these to the end of the file (before `def main()`,
# which Task 7 adds)
class OperatorPlaceBallOps:
    """Bench smoke test: lighter than mission2_day.py's BallOps contract (design spec
    §3) — a single place() only, no remove()/swap choreography needed. The operator's
    hands are the actuator; smoke_test.py waits for them."""

    def place(self, color, distance_m):
        inches = distance_m * 39.37
        input(f"Place the {color} ball {inches:.0f} inches ({distance_m:.3f} m) "
              f"directly in front of the robot, then press Enter: ")


def is_degenerate_image(rgb):
    """True if an image is uniformly one color — a camera that 'publishes' without
    ever actually capturing. rgb: HxWx3 numpy array."""
    return bool(np.all(rgb == rgb[0, 0]))


def check_photo(node, camera_topic='/robot_001/camera/image_raw', out_path=None,
                timeout_s=5.0):
    """One take_picture call (design spec §2), reusing the same primitive Mission 2
    already uses. PASS if the file exists afterward and isn't degenerate."""
    state = {'msg': None}

    def _cb(msg):
        state['msg'] = msg

    sub = node.create_subscription(Image, camera_topic, _cb, 10)
    deadline = time.time() + timeout_s
    while state['msg'] is None and time.time() < deadline:
        rclpy.spin_once(node, timeout_sec=0.1)
    node.destroy_subscription(sub)

    if state['msg'] is None:
        return {'pass': False, 'path': None, 'reason': 'no image received'}

    if out_path is None:
        out_path = str(pathlib.Path(PHOTO_DIR) / f"smoke_test_{time.strftime('%Y%m%dT%H%M%S')}.png")
    image_msg_to_png(state['msg'], out_path)
    degenerate = is_degenerate_image(image_msg_to_rgb(state['msg']))
    exists = pathlib.Path(out_path).exists()
    return {'pass': bool(exists and not degenerate), 'path': out_path if exists else None,
            'degenerate': degenerate}


def _forward_arc_min_range(msg, half_width_rad=FORWARD_ARC_HALF_WIDTH_RAD):
    """Minimum finite, positive range within +/- half_width_rad of the scan's zero
    bearing (straight ahead) — restricting to the forward arc so an object beside or
    behind the robot isn't mistaken for the ball placed in front of it."""
    best = None
    angle = msg.angle_min
    for r in msg.ranges:
        if -half_width_rad <= angle <= half_width_rad and math.isfinite(r) and r > 0.0:
            if best is None or r < best:
                best = r
        angle += msg.angle_increment
    return best


def check_ball_correlation(node, ball_ops, known_distance_m=KNOWN_DISTANCE_M,
                           tolerance_m=DISTANCE_TOLERANCE_M, window_s=3.0):
    """Design spec §3: PASS requires the lidar's measured range agrees with
    known_distance_m within tolerance_m, AND a yellow_ball detection is present during
    the window. Camera-estimated range is reported, not gated — hsv_realcam.yaml's
    range_k isn't calibrated against a real camera yet."""
    if isinstance(ball_ops, GzBallOps):
        rx, ry, ryaw = get_ground_truth_xy()
        bx, by = compute_ball_placement_xy(rx, ry, ryaw, known_distance_m)
        ball_ops.place('yellow', bx, by)
    else:
        ball_ops.place('yellow', known_distance_m)

    scan_state = {'min_range': None}
    det_state = {'yellow_range_m': None}

    def _scan_cb(msg):
        r = _forward_arc_min_range(msg)
        if r is not None:
            scan_state['min_range'] = r

    def _det_cb(msg):
        for det in msg.detections:
            for hyp in det.results:
                if hyp.hypothesis.class_id == 'yellow_ball':
                    det_state['yellow_range_m'] = hyp.pose.pose.position.x

    scan_sub = node.create_subscription(LaserScan, '/robot_001/scan', _scan_cb, 10)
    det_sub = node.create_subscription(Detection2DArray, '/robot_001/detections', _det_cb, 10)
    deadline = time.time() + window_s
    while time.time() < deadline:
        rclpy.spin_once(node, timeout_sec=0.1)
    node.destroy_subscription(scan_sub)
    node.destroy_subscription(det_sub)

    lidar_ok = (scan_state['min_range'] is not None and
                abs(scan_state['min_range'] - known_distance_m) <= tolerance_m)
    detection_present = det_state['yellow_range_m'] is not None
    return {
        'pass': bool(lidar_ok and detection_present),
        'lidar_min_range_m': scan_state['min_range'],
        'known_distance_m': known_distance_m,
        'yellow_ball_detected': detection_present,
        'camera_estimated_range_m': det_state['yellow_range_m'],  # reported, not gated
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_smoke_test.py -v`
Expected: 10 passed

- [ ] **Step 5: Commit**

```bash
git add tools/smoke_test.py tests/test_smoke_test.py
git commit -m "feat: smoke_test.py part 2 — photo check + known-distance ball correlation"
```

---

### Task 7: `tools/smoke_test.py` Part 3 — motion check, summary, CLI

**Files:**
- Modify: `tools/smoke_test.py` (append)
- Modify: `tests/test_smoke_test.py` (append)

**Interfaces:**
- Consumes: `tools.smoke_test_log.log_smoke_test_run` (Task 4), everything from
  Tasks 5-6.
- Produces: `check_motion(node, cmd_pub) -> dict`, `run_smoke_test(profile_path,
  ball_ops, runner_type=, commit_sha=, ci_run_number=, db_path=) -> bool`, CLI
  `python -m tools.smoke_test`. Consumed by Task 8's `container_entrypoint.sh`
  smoke_test branch.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_smoke_test.py — append
from nav_msgs.msg import Odometry

from tools.smoke_test import check_motion


def test_check_motion_detects_forward_and_turn_deltas():
    node = rclpy.create_node('test_check_motion')
    odom_pub = node.create_publisher(Odometry, '/robot_001/odom', 10)
    cmd_pub = node.create_publisher(__import__('geometry_msgs.msg', fromlist=['Twist']).Twist,
                                    '/robot_001/cmd_vel', 10)
    try:
        # Simulate a driver publishing odom that visibly moves during the check —
        # a background timer nudges x forward and yaw around so before/after differ.
        state = {'x': 0.0, 'yaw': 0.0, 'tick': 0}

        def _tick():
            state['tick'] += 1
            if state['tick'] > 3:
                state['x'] += 0.02
            if state['tick'] > 15:
                state['yaw'] += 0.05
            msg = Odometry()
            msg.pose.pose.position.x = state['x']
            msg.pose.pose.orientation.z = math.sin(state['yaw'] / 2.0)
            msg.pose.pose.orientation.w = math.cos(state['yaw'] / 2.0)
            odom_pub.publish(msg)

        timer = node.create_timer(0.05, _tick)
        result = check_motion(node, cmd_pub)
        node.destroy_timer(timer)
        assert result['pass'] is True
        assert result['forward_delta_m'] > 0.0
        assert result['turn_delta_rad'] > 0.0
    finally:
        node.destroy_node()


def test_check_motion_no_odom_fails_cleanly():
    node = rclpy.create_node('test_check_motion_no_odom')
    cmd_pub = node.create_publisher(__import__('geometry_msgs.msg', fromlist=['Twist']).Twist,
                                    '/robot_001/cmd_vel', 10)
    try:
        result = check_motion(node, cmd_pub)
        assert result['pass'] is False
        assert 'reason' in result
    finally:
        node.destroy_node()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_smoke_test.py -v -k check_motion`
Expected: FAIL — `ImportError: cannot import name 'check_motion'`

- [ ] **Step 3: Append the implementation**

```python
# tools/smoke_test.py — append these imports at the top
from geometry_msgs.msg import Twist

from tools import smoke_test_log

# tools/smoke_test.py — append to the end of the file
MOTION_FORWARD_MPS = 0.15
MOTION_FORWARD_S = 1.0
MOTION_TURN_RADPS = 0.5
MOTION_TURN_S = 1.0
MOTION_MIN_DELTA_M = 0.03        # generous — sanity check, not calibration (design spec §4)
MOTION_MIN_DELTA_RAD = math.radians(5)


def _latest_odom(node, timeout_s=2.0):
    state = {'msg': None}

    def _cb(msg):
        state['msg'] = msg

    sub = node.create_subscription(Odometry, '/robot_001/odom', _cb, 10)
    deadline = time.time() + timeout_s
    while state['msg'] is None and time.time() < deadline:
        rclpy.spin_once(node, timeout_sec=0.1)
    node.destroy_subscription(sub)
    return state['msg']


def _yaw_from_quat(q):
    return math.atan2(2.0 * (q.w * q.z), 1.0 - 2.0 * (q.z * q.z))


def _publish_for(node, cmd_pub, twist, duration_s, rate_hz=10.0):
    deadline = time.time() + duration_s
    period = 1.0 / rate_hz
    while time.time() < deadline:
        cmd_pub.publish(twist)
        rclpy.spin_once(node, timeout_sec=period)


def check_motion(node, cmd_pub):
    """Design spec §4: two short open-loop cmd_vel pulses (forward, then a turn),
    /robot_001/odom read before and after each. PASS requires a non-trivial delta in
    the commanded direction — a generous sanity check, not a calibration. Operator
    visual confirmation is recommended (catches e.g. wheels spinning but the chassis
    stuck) but isn't required for this automated verdict."""
    before = _latest_odom(node)
    if before is None:
        return {'pass': False, 'reason': 'no odom before motion check'}

    forward = Twist()
    forward.linear.x = MOTION_FORWARD_MPS
    _publish_for(node, cmd_pub, forward, MOTION_FORWARD_S)
    cmd_pub.publish(Twist())
    time.sleep(0.5)
    after_forward = _latest_odom(node)

    turn = Twist()
    turn.angular.z = MOTION_TURN_RADPS
    _publish_for(node, cmd_pub, turn, MOTION_TURN_S)
    cmd_pub.publish(Twist())
    time.sleep(0.5)
    after_turn = _latest_odom(node)

    if after_forward is None or after_turn is None:
        return {'pass': False, 'reason': 'no odom after motion pulses'}

    dx = after_forward.pose.pose.position.x - before.pose.pose.position.x
    dy = after_forward.pose.pose.position.y - before.pose.pose.position.y
    forward_delta_m = math.hypot(dx, dy)

    yaw_before_turn = _yaw_from_quat(after_forward.pose.pose.orientation)
    yaw_after_turn = _yaw_from_quat(after_turn.pose.pose.orientation)
    turn_delta_rad = abs(math.atan2(math.sin(yaw_after_turn - yaw_before_turn),
                                    math.cos(yaw_after_turn - yaw_before_turn)))

    return {'pass': bool(forward_delta_m >= MOTION_MIN_DELTA_M and
                         turn_delta_rad >= MOTION_MIN_DELTA_RAD),
            'forward_delta_m': round(forward_delta_m, 3),
            'turn_delta_rad': round(turn_delta_rad, 3)}


def _is_degenerate_odom(msg):
    """NaN/inf in pose or twist — a genuinely broken publisher. A legitimately
    stationary robot has an all-zero pose/twist (this integrator starts at the
    origin), so all-zero is deliberately NOT treated as degenerate — only non-finite
    values are."""
    p, t = msg.pose.pose.position, msg.twist.twist
    values = (p.x, p.y, p.z, t.linear.x, t.linear.y, t.linear.z,
             t.angular.x, t.angular.y, t.angular.z)
    return not all(math.isfinite(v) for v in values)


def _is_degenerate_image_msg(msg):
    return is_degenerate_image(image_msg_to_rgb(msg))


def _is_degenerate_imu(msg):
    values = (msg.angular_velocity.x, msg.angular_velocity.y, msg.angular_velocity.z,
             msg.linear_acceleration.x, msg.linear_acceleration.y, msg.linear_acceleration.z)
    return not all(math.isfinite(v) for v in values)


def _print_summary(checks, overall_pass):
    print("=== Smoke test summary ===")
    for name, result in checks.items():
        status = 'PASS' if result.get('pass') else 'FAIL'
        print(f"[{status}] {name}: {result}")
    print(f"=== Overall: {'PASS' if overall_pass else 'FAIL'} ===")


def run_smoke_test(profile_path, ball_ops, runner_type='local', commit_sha=None,
                   ci_run_number=None, db_path=None):
    """Design spec §5: run every check regardless of earlier failures (the checklist
    IS the verdict, matching mission_runner's own philosophy), print an itemized
    summary, log one row, return overall PASS/FAIL."""
    profile = load_robot_profile(profile_path)
    sensors = profile['sensors']

    rclpy.init()
    node = rclpy.create_node('smoke_test')
    cmd_pub = node.create_publisher(Twist, '/robot_001/cmd_vel', 10)
    checks = {}
    try:
        checks['odom'] = check_topic(node, sensors['odometry']['topic'], Odometry,
                                     sensors['odometry']['hz_min'], _is_degenerate_odom)
        checks['scan'] = check_topic(node, sensors['lidar']['topic'], LaserScan,
                                     sensors['lidar']['hz_min'], is_degenerate_scan)
        checks['camera'] = check_topic(node, sensors['camera']['topic'], Image,
                                       sensors['camera']['hz_min'], _is_degenerate_image_msg)
        checks['imu'] = check_topic(node, sensors['imu']['topic'], Imu,
                                    sensors['imu']['hz_min'], _is_degenerate_imu)
        checks['photo'] = check_photo(node)
        checks['ball_correlation'] = check_ball_correlation(node, ball_ops)
        checks['motion'] = check_motion(node, cmd_pub)
    finally:
        node.destroy_node()
        rclpy.shutdown()

    overall_pass = all(c.get('pass', False) for c in checks.values())
    _print_summary(checks, overall_pass)

    smoke_test_log.log_smoke_test_run(
        runner_type=runner_type, overall_pass=overall_pass, checks=checks,
        commit_sha=commit_sha, ci_run_number=ci_run_number,
        db_path=db_path or smoke_test_log.DB_PATH)
    return overall_pass


def main():
    parser = argparse.ArgumentParser(
        description="Bench smoke test — driver-layer sanity check before Nav2 trusts it")
    parser.add_argument('--profile', default=DEFAULT_PROFILE)
    parser.add_argument('--ball-ops', choices=['gz', 'operator'], default='operator')
    parser.add_argument('--runner-type', default='local')
    parser.add_argument('--commit-sha', default=None)
    parser.add_argument('--ci-run-number', type=int, default=None)
    parser.add_argument('--db', default=None)
    args = parser.parse_args()

    ball_ops = GzBallOps() if args.ball_ops == 'gz' else OperatorPlaceBallOps()
    overall_pass = run_smoke_test(
        args.profile, ball_ops, runner_type=args.runner_type, commit_sha=args.commit_sha,
        ci_run_number=args.ci_run_number, db_path=args.db)
    sys.exit(0 if overall_pass else 1)


if __name__ == '__main__':
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_smoke_test.py -v`
Expected: 12 passed

- [ ] **Step 5: Commit**

```bash
git add tools/smoke_test.py tests/test_smoke_test.py
git commit -m "feat: smoke_test.py part 3 — motion check, summary, CLI"
```

---

### Task 8: `ROBOT_MODE` branching — `container_entrypoint.sh` + `robot_boot.sh`

**Files:**
- Modify: `scripts/container_entrypoint.sh`
- Modify: `scripts/robot_boot.sh`

**Interfaces:**
- Consumes: `sensors_only_launch.py` (Task 3), `tools.smoke_test` CLI (Task 7).
- Produces: `ROBOT_MODE` env-var contract (`mission` | `smoke_test`), `SMOKE_BALL_OPS`
  env var (default `operator`). Consumed by Task 9 (`hil_stage.sh smoke`/`smoke-ci`)
  and Task 10 (CI).

- [ ] **Step 1: Restructure `container_entrypoint.sh` around a required `ROBOT_MODE`**

```bash
# scripts/container_entrypoint.sh — replace everything from
#   mkdir -p /ros2_ws/reports
# through the final
#   python3 -m nav_fleet.mission_runner --day
# with:

mkdir -p /ros2_ws/reports

# ROBOT_MODE is required, no implicit default — fail loudly if unset (design spec
# §ROBOT_MODE branching: "Standalone power-on can never run a smoke test"; robot_boot.sh
# hardcodes ROBOT_MODE=mission, never a variable that could be left set wrong).
: "${ROBOT_MODE:?ROBOT_MODE must be set to 'mission' or 'smoke_test' — no implicit default}"

case "$ROBOT_MODE" in
  mission)
    NAV2_LOG="/ros2_ws/reports/nav2_container_$(date +%Y%m%dT%H%M%S).log"
    rm -f "$NAV2_LOG"
    (nohup ros2 launch nav_fleet nav2_only_launch.py \
       use_sim_time:="${USE_SIM_TIME}" \
       hsv_config:="/ros2_ws/src/nav_fleet/config/${HSV_CONFIG_FILE}" \
       map:="/ros2_ws/src/nav_fleet/maps/${NAV2_MAP_FILE}" \
       > "$NAV2_LOG" 2>&1 < /dev/null &)

    echo "=== [container-entrypoint] waiting up to 120s for Nav2 to report active ==="
    deadline=$((SECONDS + 120))
    until [ "${count:-0}" -ge 2 ]; do
      if (( SECONDS >= deadline )); then
        echo "FATAL: Nav2 not active within 120s — see $NAV2_LOG" >&2
        tail -n 40 "$NAV2_LOG" >&2 || true
        exit 1
      fi
      sleep 3
      count=$(grep -c 'Managed nodes are active' "$NAV2_LOG" 2>/dev/null || true)
      count="${count:-0}"
    done
    echo "=== [container-entrypoint] Nav2 active — starting mission2 day ==="
    python3 -m nav_fleet.mission_runner --day
    ;;

  smoke_test)
    # Real-robot driver + bench smoke-test design spec (2026-08-05/06): the THIRD
    # ROBOT_MODE, no Nav2/map — proves the driver layer works before Nav2 ever
    # trusts it. Never reached from robot_boot.sh (power-on) — only from
    # scripts/hil_stage.sh's smoke/smoke-ci subcommands, deliberately.
    SENSORS_LOG="/ros2_ws/reports/sensors_container_$(date +%Y%m%dT%H%M%S).log"
    rm -f "$SENSORS_LOG"
    (nohup ros2 launch nav_fleet sensors_only_launch.py \
       use_sim_time:="${USE_SIM_TIME}" \
       hsv_config:="/ros2_ws/src/nav_fleet/config/${HSV_CONFIG_FILE}" \
       serial_device:="${SERIAL_DEVICE:-/dev/ttyUSB0}" \
       serial_baud:="${SERIAL_BAUD:-115200}" \
       lidar_launch_file:="${LIDAR_LAUNCH_FILE:-}" \
       camera_launch_file:="${CAMERA_LAUNCH_FILE:-}" \
       > "$SENSORS_LOG" 2>&1 < /dev/null &)

    echo "=== [container-entrypoint] waiting up to 60s for the sensors stack to report up ==="
    deadline=$((SECONDS + 60))
    until [ "${count:-0}" -ge 1 ]; do
      if (( SECONDS >= deadline )); then
        echo "FATAL: sensors_only_launch.py not up within 60s — see $SENSORS_LOG" >&2
        tail -n 40 "$SENSORS_LOG" >&2 || true
        exit 1
      fi
      sleep 2
      count=$(grep -c 'ball_detector up' "$SENSORS_LOG" 2>/dev/null || true)
      count="${count:-0}"
    done
    echo "=== [container-entrypoint] sensors up — running smoke test ==="
    python3 -m tools.smoke_test --runner-type "${RUNNER_TYPE:-local}" \
      --ball-ops "${SMOKE_BALL_OPS:-operator}" \
      ${COMMIT_SHA:+--commit-sha "$COMMIT_SHA"} \
      ${CI_RUN_NUMBER:+--ci-run-number "$CI_RUN_NUMBER"}
    ;;

  *)
    echo "FATAL: ROBOT_MODE must be 'mission' or 'smoke_test', got '${ROBOT_MODE}'" >&2
    exit 1
    ;;
esac
```

Also update the file's header comment block (env vars documentation) to add
`ROBOT_MODE` (required), `SERIAL_DEVICE`/`SERIAL_BAUD`/`LIDAR_LAUNCH_FILE`/
`CAMERA_LAUNCH_FILE`/`SMOKE_BALL_OPS`/`COMMIT_SHA`/`CI_RUN_NUMBER` (smoke_test-only,
all optional with documented defaults), matching the existing doc style for
`USE_SIM_TIME`/`HSV_CONFIG_FILE`/`NAV2_MAP_FILE`.

- [ ] **Step 2: `robot_boot.sh` hardcodes `ROBOT_MODE=mission`**

```bash
# scripts/robot_boot.sh — add this line to the existing docker run env list,
# alongside the existing -e RUNNER_TYPE=real_robot line:
  -e ROBOT_MODE=mission \
```

Note in the file's own header comment (next to the existing "RUNNER_TYPE=real_robot
matches..." comment): `ROBOT_MODE=mission is hardcoded here, never a variable —
standalone power-on can never run a smoke test (design spec). Smoke test is only
ever triggered from scripts/hil_stage.sh smoke, run by hand from the workstation.`

- [ ] **Step 3: Verify `container_entrypoint.sh`'s CRLF/bash-file editing caution
  does NOT apply here** (that's `ci.yml`-specific — confirm this file's own line
  endings are unaffected by checking `file scripts/container_entrypoint.sh` before
  and after editing; expect plain `ASCII text` both times, not `with CRLF line
  terminators`)

Run: `file scripts/container_entrypoint.sh scripts/robot_boot.sh`
Expected: both report plain `ASCII text` (or `Bourne-Again shell script`), not CRLF

- [ ] **Step 4: Manual smoke check against sim (no real hardware needed for this
  step — proves the ROBOT_MODE branch dispatches correctly)**

Run (with `sim_only_launch.py` already up, matching Task 3's own verification):
```bash
docker run --rm --network host --ipc host \
  -e USE_SIM_TIME=true -e HSV_CONFIG_FILE=hsv_gazebo.yaml \
  -e ROBOT_MODE=smoke_test -e SMOKE_BALL_OPS=gz -e RUNNER_TYPE=local \
  <local-image-tag> bash /ros2_ws/scripts/container_entrypoint.sh
```
Expected: reaches "sensors up — running smoke test", `tools.smoke_test` runs to
completion (PASS or FAIL on individual checks is fine at this stage — the thing
being proven here is that the branch dispatches and the tool runs, not that hardware
exists yet).

- [ ] **Step 5: Commit**

```bash
git add scripts/container_entrypoint.sh scripts/robot_boot.sh
git commit -m "feat: ROBOT_MODE branching — mission (unchanged) | smoke_test (new)"
```

---

### Task 9: `scripts/hil_stage.sh smoke` + `smoke-ci`

**Files:**
- Modify: `scripts/hil_stage.sh`

**Interfaces:**
- Consumes: `sync()`, `require_ip()`, `jssh()` (existing, unchanged), Task 8's
  `ROBOT_MODE=smoke_test` contract.
- Produces: `smoke <sha>` (attended, interactive — bench use), `smoke-ci <sha>`
  (non-interactive, `GzBallOps` — CI use). Consumed by Task 10 (`ci.yml`'s
  stage-4-hil).

- [ ] **Step 1: Add both functions**

```bash
# scripts/hil_stage.sh — add these two functions, right after the existing day()
# function and before the `case "$cmd" in` dispatch block

smoke() {
  # Bench smoke test (real-robot driver + smoke-test design spec, 2026-08-05/06):
  # runs ROBOT_MODE=smoke_test on the Jetson, over SSH — the ONLY place this mode is
  # ever triggered from. robot_boot.sh (power-on) hardcodes ROBOT_MODE=mission and
  # never calls this — this is the deliberate, workstation-triggered counterpart.
  # ATTENDED: this prompts you, via THIS terminal, to place the yellow ball.
  require_ip
  local sha="${1:?usage: hil_stage.sh smoke <git-sha>}"
  sync "$sha"

  local image="ghcr.io/sdfinn/autonomous-fleet-testbed:${sha}"
  echo "=== [smoke] checking ${image} is present locally on the Jetson ==="
  if ! jssh "docker image inspect ${image} >/dev/null 2>&1"; then
    echo "FATAL: ${image} is not present locally on the Jetson — sync to a sha a" >&2
    echo "green stage-3-arm64 run already pushed, or docker pull it by hand first." >&2
    exit 1
  fi

  echo "=== [smoke] running ROBOT_MODE=smoke_test — you will be prompted to place"
  echo "the yellow ball when the correlation check starts =="
  # -t (this ssh) + -it (the remote docker run), unlike jssh() (every OTHER
  # subcommand here is unattended) — so tools/smoke_test.py's operator prompt
  # (design spec: 'interactive prompting is deliberate here') actually reaches you.
  ssh -t -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new \
    "${JETSON_USER}@${JETSON_IP}" \
    "docker rm -f hil_smoke_test 2>/dev/null || true; \
     docker run --rm --name hil_smoke_test --network host --ipc host -it \
       --device=${SERIAL_DEVICE:-/dev/ttyUSB0} \
       -v \$HOME/autonomous-fleet-testbed/reports:/ros2_ws/reports \
       -v \$HOME/fleet-ci-data:/root/fleet-ci-data \
       -e USE_SIM_TIME=false -e HSV_CONFIG_FILE=hsv_realcam.yaml \
       -e ROBOT_MODE=smoke_test -e RUNNER_TYPE=real_robot \
       ${image} bash /ros2_ws/scripts/container_entrypoint.sh"
}

smoke_ci() {
  # CI-only counterpart to smoke() — non-interactive (no -t, no operator prompt):
  # SMOKE_BALL_OPS=gz makes tools/smoke_test.py place the ball itself via GzBallOps,
  # same mechanism mission2_day.py's own CI regression already uses. Never used from
  # a human bench session — that's smoke(), above. USE_SIM_TIME=true so
  # sensors_only_launch.py skips esp32_driver/ldlidar_ros2/depthai-ros entirely and
  # relies on the WORKSTATION's Gazebo bridge reaching the Jetson over DDS — the
  # same cross-machine pattern day()'s mission-mode container run already uses.
  # Precondition: run() (sim_up) must already be up, same as day().
  require_ip
  local sha="${1:?usage: hil_stage.sh smoke-ci <git-sha>}"

  local image="ghcr.io/sdfinn/autonomous-fleet-testbed:${sha}"
  if ! jssh "docker image inspect ${image} >/dev/null 2>&1"; then
    echo "FATAL: ${image} is not present locally on the Jetson" >&2
    exit 1
  fi

  jssh "docker rm -f hil_smoke_test_ci 2>/dev/null || true; \
        docker run --rm --name hil_smoke_test_ci --network host --ipc host \
          -v \$HOME/autonomous-fleet-testbed/reports:/ros2_ws/reports \
          -v \$HOME/fleet-ci-data:/root/fleet-ci-data \
          -e USE_SIM_TIME=true -e HSV_CONFIG_FILE=hsv_gazebo.yaml \
          -e ROBOT_MODE=smoke_test -e SMOKE_BALL_OPS=gz -e RUNNER_TYPE=hil_jetson \
          -e COMMIT_SHA=${sha} -e CI_RUN_NUMBER=${CI_RUN_NUMBER:-} \
          ${image} bash /ros2_ws/scripts/container_entrypoint.sh"
}
```

- [ ] **Step 2: Wire both into the subcommand dispatch and the top-of-file comment**

```bash
# scripts/hil_stage.sh — case "$cmd" in ... add these two lines alongside the
# existing `day) day ;;` line:
  smoke)             smoke "$@" ;;
  smoke-ci)          smoke_ci "$@" ;;
```

```bash
# scripts/hil_stage.sh — top-of-file comment block: add alongside the existing
# `day` subcommand's description:
#   smoke <sha>       Bench smoke test (attended — prompts for ball placement over
#                      this same SSH session). Real-robot-only (USE_SIM_TIME=false).
#   smoke-ci <sha>     CI-only counterpart — non-interactive, GzBallOps, USE_SIM_TIME=true.
#                      Never run by hand; ci.yml's stage-4-hil is the only caller.
```

- [ ] **Step 3: Verify the CRLF caution doesn't apply**

Run: `file scripts/hil_stage.sh`
Expected: plain `Bourne-Again shell script text executable`, not CRLF (this file has
always been LF — only `ci.yml` has the CRLF gotcha per CLAUDE.md's Gotchas)

- [ ] **Step 4: Commit**

```bash
git add scripts/hil_stage.sh
git commit -m "feat: hil_stage.sh smoke / smoke-ci — trigger ROBOT_MODE=smoke_test on the Jetson"
```

---

### Task 10: CI regression coverage — `stage-2-gazebo` (sim) + `stage-4-hil` (container)

**Files:**
- Modify: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: `sensors_only_launch.py` (Task 3), `tools.smoke_test` CLI (Task 7),
  `hil_stage.sh smoke-ci` (Task 9).
- Produces: nothing new — terminal task, validates everything above end-to-end
  against sim/HIL (never real ESP32/lidar/camera hardware, which can't be exercised
  before ~2026-08-11 regardless — the design spec is explicit that a green run here
  must never be mistaken for "real hardware confirmed").

**IMPORTANT — `ci.yml` uses CRLF line endings** (CLAUDE.md Gotchas): edit only via
the Edit tool's exact string replacement, never a raw Python/shell read-modify-write
script. Verify with `file .github/workflows/ci.yml` before and after — must report
"with CRLF line terminators" both times.

- [ ] **Step 1: `stage-2-gazebo` — sim regression, immediately after the existing
  "Upload mission2_day log" step**

```yaml
      - name: Sweep stale sim processes before smoke-test regression
        run: |
          pkill -9 -f "parameter_bridge|component_container_isolated|ekf_node|ball_detector" || true
          pkill -9 -f "static_transform_publisher|robot_state_publisher" || true
          pkill -f "gz sim" || true
          sleep 3

      - name: Bring up sim + sensors-only stack (smoke-test regression, sim)
        run: |
          source /opt/ros/jazzy/setup.bash
          source install/setup.bash
          bash scripts/regen_cyclonedds_config.sh
          export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp ROS_DOMAIN_ID=0
          setsid ros2 launch src/nav_fleet/launch/sim_only_launch.py \
            > /tmp/smoke_sim.log 2>&1 &
          echo "SIM_PGID=$!" >> $GITHUB_ENV
          deadline=$((SECONDS + 60))
          until grep -q 'gz.msgs.Clock' /tmp/smoke_sim.log 2>/dev/null; do
            if (( SECONDS >= deadline )); then
              echo "FATAL: sim/bridge not up within 60s" >&2
              tail -n 40 /tmp/smoke_sim.log >&2 || true
              exit 1
            fi
            sleep 2
          done
          sleep 3
          setsid ros2 launch src/nav_fleet/launch/sensors_only_launch.py \
            use_sim_time:=true > /tmp/smoke_sensors.log 2>&1 &
          echo "SENSORS_PGID=$!" >> $GITHUB_ENV
          deadline=$((SECONDS + 30))
          until grep -q 'ball_detector up' /tmp/smoke_sensors.log 2>/dev/null; do
            if (( SECONDS >= deadline )); then
              echo "FATAL: sensors_only_launch.py not up within 30s" >&2
              tail -n 40 /tmp/smoke_sensors.log >&2 || true
              exit 1
            fi
            sleep 2
          done

      - name: Run smoke-test machinery regression (sim)
        run: |
          source /opt/ros/jazzy/setup.bash
          source install/setup.bash
          coverage run -a -m tools.smoke_test --ball-ops gz --runner-type local \
            --commit-sha ${{ github.sha }} --ci-run-number ${{ github.run_number }}

      - name: Show smoke-test regression logs on failure
        if: failure()
        run: |
          echo '--- sim log ---'; tail -n 60 /tmp/smoke_sim.log || true
          echo '--- sensors log ---'; tail -n 60 /tmp/smoke_sensors.log || true

      - name: Teardown smoke-test regression stack
        if: always()
        run: |
          kill -INT -$SENSORS_PGID 2>/dev/null || true
          kill -INT -$SIM_PGID 2>/dev/null || true
          sleep 2
```

- [ ] **Step 2: `stage-4-hil` — container regression, immediately after the existing
  `hil_stage.sh day` step (same job that already ran `hil_stage.sh run` earlier, so
  Gazebo is already up)**

```yaml
      - name: Run smoke-test machinery regression (HIL container)
        env:
          CI_RUN_NUMBER: ${{ github.run_number }}
        run: |
          scripts/hil_stage.sh smoke-ci ${{ github.sha }}
```

- [ ] **Step 3: Add both new test files to `stage-1-quality`'s ignore list (if not
  already done in Tasks 2/5 — confirm, don't duplicate)**

Run: `grep -n "test_esp32_driver.py\|test_smoke_test.py" .github/workflows/ci.yml`
Expected: both already present from Task 2 Step 5 and Task 5 Step 5 — this step is a
verification, not a new edit, unless one was missed.

- [ ] **Step 4: Push to a draft PR and confirm both jobs green** (per
  `src/nav_fleet/CLAUDE.md`'s established practice: "CI triggers ONLY on push-to-main
  and PRs targeting main — pushing a feature branch runs nothing... open a draft PR")

Run: `gh pr create --draft --title "..." --body "..."` (or push to an existing draft
PR), then `gh run watch` on the resulting run.
Expected: `stage-1-quality`, `stage-2-gazebo` green (including the new smoke-test
regression steps); `stage-3-arm64`/`stage-4-hil` green (including `smoke-ci`'s new
step) — full chain, matching the docker-brain-unification precedent's own bar for
"proven, not just planned."

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: smoke-test machinery regression — stage-2 (sim) + stage-4-hil (container)"
```

---

## Self-Review

**Spec coverage** (against `docs/superpowers/specs/2026-08-05-real-robot-driver-
smoke-test-design.md`'s "In scope" list):
1. `esp32_driver` — Tasks 1-2. ✓
2. `sensors_only_launch.py` — Task 3. ✓
3. `tools/smoke_test.py` — Tasks 5-7 (topic sanity, photo, known-distance
   correlation, motion, summary+exit, all 5 numbered orchestrator steps from the
   spec). ✓
4. `ROBOT_MODE` branching — Task 8. ✓
5. `scripts/hil_stage.sh smoke` — Task 9 (plus the CI-only `smoke-ci` counterpart,
   needed because the spec's own attended/interactive design can't run
   non-interactively in CI — a gap the spec didn't need to resolve since it wasn't
   scoping CI wiring in that section). ✓
6. `smoke_test_runs` table + logging — Task 4, wired into Task 7's orchestrator. ✓
7. CI regression coverage (stage-2/stage-4) — Task 10. ✓

**Placeholder scan:** no TBD/"add error handling"/"similar to Task N" found on
re-read. The two genuinely-deferred pieces (`ldlidar_ros2`/`depthai-ros` exact launch
wiring, ESP32 IMU raw-unit calibration) are explicitly flagged as real, named,
verified-as-unconfirmed risks — not vague placeholders — matching the design spec's
own "Known implementation-time risks" treatment of the same two gaps.

**Type/interface consistency:** `check_topic`'s `degenerate_fn(msg) -> bool` shape is
used identically for scan/camera/odom/imu in Task 7's `run_smoke_test`.
`OperatorPlaceBallOps.place(color, distance_m)` vs `GzBallOps.place(color, x, y)`
signatures deliberately differ (per the spec's own "lighter interface... not a
subclass forced to implement more than it needs") — `check_ball_correlation`
branches on `isinstance(ball_ops, GzBallOps)` to call each correctly, verified
consistent across Task 6's implementation. `esp32_protocol.integrate_odometry`'s
`(x, y, yaw, speed_l, speed_r, track_width, dt)` signature matches its one caller in
`esp32_driver._publish_odom` exactly.

**Scope boundary flagged, not silently dropped:** `ROBOT_MODE=mission`'s daily-
mission path is NOT updated to use the driver layer — recorded in Global Constraints
so it isn't mistaken for done.
