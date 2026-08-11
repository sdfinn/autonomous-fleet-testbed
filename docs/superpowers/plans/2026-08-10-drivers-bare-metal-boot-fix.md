# Real driver layer bare-metal boot fix — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the real robot's power-on mission (`robot_boot.sh`) and the bench
smoke test (`hil_stage.sh smoke`) actually start the real driver layer
(esp32_driver/lidar/camera/scan_masker/camera_relay) AND exercise the real
production interface between it and the container's EKF/`ball_detector` — not a
bare-metal stand-in for EKF/`ball_detector` that never touches the actual
container boundary where this project's real bugs have lived (CycloneDDS
big-message, network interface selection).

**Revision note (same night, before any of this was implemented):** the first
version of this plan had the smoke test run EKF+`ball_detector` bare-metal too,
as a standalone copy separate from the container. Mike caught this: the whole
point of smoke-testing is to prove "the robot process" — the actual production
wiring — works, and a bare-metal EKF/`ball_detector` would never exercise the
container boundary at all, silently skipping exactly the class of bug most
likely to hide there. Revised below: only the driver layer (which can't run in
the container — the vendor lidar/camera packages were never installed there,
and per architecture never should be) stays bare-metal for the smoke test too;
EKF+`ball_detector` now run inside the container for BOTH the smoke test and
the real mission, via the same `nav2_only_launch.py`, just with Nav2 bringup
itself skippable (a new `skip_nav2` arg) so the smoke test doesn't need a real
map to exist yet.

**Architecture:**
- Extract the five real-hardware driver nodes out of `sensors_only_launch.py`
  into a new `drivers_only_launch.py` (no EKF, no `ball_detector` — those stay
  exclusively in `nav2_only_launch.py`).
- Add a `skip_nav2` launch arg to `nav2_only_launch.py` — when true, EKF and
  `ball_detector` still start, but the Nav2/AMCL/map_server bringup itself is
  skipped, so this file can run inside a container with no real map yet.
- `robot_boot.sh`: bare-metal `drivers_only_launch.py` → wait for it to report
  up → the existing container (`ROBOT_MODE=mission`, `skip_nav2` defaults to
  false, unchanged from today) with full Nav2.
- `hil_stage.sh smoke`: bare-metal `drivers_only_launch.py` → wait for it →
  container (`ROBOT_MODE=smoke_test`, now running `nav2_only_launch.py` with
  `skip_nav2:=true` instead of the old `sensors_only_launch.py`-in-container
  approach) → wait for EKF/`ball_detector` up → bare-metal
  `tools/smoke_test.py` (reaching the WHOLE ROS graph — bare-metal driver
  topics + containerized EKF/`ball_detector` topics — over the shared
  `--network host` DDS domain) → tear down both the container and the
  bare-metal drivers.
- `smoke-ci` (CI's `USE_SIM_TIME=true` sim-regression path) and
  `stage-4-hil`'s own mission-mode container path are untouched by all of
  this — neither ever needed the real driver layer (Gazebo provides sensor
  data instead).

**Tech Stack:** ROS2 Jazzy launch files (Python), bash (the two orchestration
scripts + the container entrypoint), no new dependencies.

## Global Constraints

- `ekf_node`/`ball_detector` must run exactly ONCE per real deployment — always
  inside the container, never bare-metal, never duplicated. The driver layer
  must run exactly once too — always bare-metal, never inside the container.
- `smoke-ci` (CI's `USE_SIM_TIME=true` path) and `stage-4-hil`'s mission-mode
  container path are NOT touched by this plan — verify after each task that
  neither's behavior changed.
- This repo has no precedent for pytest-testing launch files or the three shell
  scripts touched here (`robot_boot.sh`, `hil_stage.sh`, `container_entrypoint.sh`)
  — none of the existing ones have pytest coverage. Verification in this plan
  is live, on real hardware, matching that established convention.
- Real hardware constants confirmed 2026-08-09/10, reuse verbatim:
  `SERIAL_DEVICE=/dev/ttyTHS1`, `SERIAL_BAUD=115200`,
  `LIDAR_LAUNCH_FILE=$HOME/ros2_drivers_ws/install/ldlidar_ros2/share/ldlidar_ros2/launch/ld19.launch.py`,
  `CAMERA_LAUNCH_FILE=/opt/ros/jazzy/share/depthai_ros_driver/launch/camera.launch.py`.
- Follow this project's existing bash conventions exactly: `set -euo pipefail`
  at file scope, `set +u`/`set -u` bracketing ONLY around sourcing ROS2's own
  `setup.bash`, the `nohup ... > LOG 2>&1 < /dev/null &` background pattern
  for bare-metal processes (capturing `$!` for a real PID when the caller
  needs to wait/kill it, not the fully-detached `(cmd &)` subshell form which
  loses that ability), grep-based readiness polling with an explicit timeout
  that `FATAL`s + tails the log/container-logs on expiry, and `docker rm -f`
  (not a graceful signal) for container teardown — that's this project's own
  already-established, accepted pattern for containers specifically (unlike
  bare-metal processes, which DO get careful SIGINT propagation to avoid
  orphaning host processes).
- **Known, separately-tracked, NOT part of this plan:** `robot_boot.sh` still
  hardcodes `HSV_CONFIG_FILE=hsv_realcam.yaml`, which doesn't exist yet
  (`RealRobotStartup.md` A4). A full `robot_boot.sh` end-to-end run will still
  fail at the container step until A4 is done.

---

### Task 1: Extract `drivers_only_launch.py` out of `sensors_only_launch.py`

**Files:**
- Create: `src/nav_fleet/launch/drivers_only_launch.py`
- Modify: `src/nav_fleet/launch/sensors_only_launch.py` (full replacement — see below)

**Interfaces:**
- Produces: `drivers_only_launch.py` exposes 4 launch args —
  `serial_device` (default `/dev/ttyUSB0`), `serial_baud` (default `115200`),
  `lidar_launch_file` (default `''`), `camera_launch_file` (default `''`) — and
  launches exactly 5 things: `esp32_driver` (package `nav_fleet`), `lidar_include`
  (conditional `IncludeLaunchDescription`), `camera_include` (conditional
  `IncludeLaunchDescription`), `scan_masker` (package `nav_fleet`), `camera_relay`
  (package `nav_fleet`). No EKF, no ball_detector, no `use_sim_time` argument at
  all — this file is only ever invoked in real-hardware contexts.
- Consumed by: Task 3 (`robot_boot.sh`) and Task 5 (`hil_stage.sh smoke`) both
  launch this bare-metal directly. Its `camera_relay up` log line (from
  `camera_relay.py`'s own existing log line) is the readiness signal both use.

- [ ] **Step 1: Create `src/nav_fleet/launch/drivers_only_launch.py`**

```python
# src/nav_fleet/launch/drivers_only_launch.py
# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""Real-hardware driver layer ONLY — esp32_driver (odom/imu/cmd_vel) + the lidar and
camera vendor launch files + scan_masker + camera_relay. No EKF, no ball_detector, no
Nav2 — those stay in nav2_only_launch.py (the container), started separately.

Extracted 2026-08-10 out of sensors_only_launch.py (which used to bundle these five
driver nodes together with EKF + ball_detector for the bench smoke test's own
self-contained convenience) so this exact driver set can ALSO be launched bare-metal
by robot_boot.sh AND by the bench smoke test for the real deployed robot, without
duplicating EKF/ball_detector against the copies nav2_only_launch.py already starts
inside the container. See
docs/superpowers/plans/2026-08-10-drivers-bare-metal-boot-fix.md for the full story:
neither robot_boot.sh's ROBOT_MODE=mission container branch nor the smoke test's old
ROBOT_MODE=smoke_test container branch could ever actually reach the real lidar/
camera — the vendor packages were never installed in the Docker image, and were
never meant to be (this project's own docker-brain-unification decision: the driver
layer stays bare-metal, only Nav2/EKF/ball_detector/mission_runner run in the
container).

No use_sim_time argument here at all — this file is ONLY ever invoked in real-
hardware contexts; sim/CI regression never constructs any of these five nodes,
matching how nav2_only_launch.py never launches its own odom/scan/camera source
either.
"""
import pathlib

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PythonExpression
from launch_ros.actions import Node

PKG = pathlib.Path(__file__).parent.parent


def generate_launch_description():
    serial_device_arg = DeclareLaunchArgument(
        'serial_device', default_value='/dev/ttyUSB0',
        description='ESP32 sub-controller serial device — this Jetson uses '
                    '/dev/ttyTHS1 (40-pin header UART), confirmed 2026-08-09/10.',
    )
    serial_baud_arg = DeclareLaunchArgument(
        'serial_baud', default_value='115200',
        description='Confirmed 2026-08-06 against the real ugv_base_general '
                    'firmware source (Serial.begin(115200)) — see '
                    'robot_profiles/jetson_ugv_pt.yaml',
    )
    lidar_launch_file_arg = DeclareLaunchArgument(
        'lidar_launch_file', default_value='',
        description="Absolute path to ldlidar_ros2's own launch file for the "
                    "exact physical model (D500/STL-19P) — this Jetson's real "
                    "path is ~/ros2_drivers_ws/install/ldlidar_ros2/share/"
                    "ldlidar_ros2/launch/ld19.launch.py, confirmed 2026-08-09. "
                    "Left empty = skipped, not a launch error.",
    )
    camera_launch_file_arg = DeclareLaunchArgument(
        'camera_launch_file', default_value='',
        description="Absolute path to depthai-ros's own launch file (OAK-D "
                    "Lite) — this Jetson's real path is /opt/ros/jazzy/share/"
                    "depthai_ros_driver/launch/camera.launch.py, confirmed "
                    "2026-08-09. Left empty = skipped, not a launch error.",
    )

    esp32_driver = Node(
        package='nav_fleet',
        executable='esp32_driver',
        name='esp32_driver',
        output='screen',
        parameters=[{'serial_device': LaunchConfiguration('serial_device'),
                     'baud': LaunchConfiguration('serial_baud')}],
    )

    # scan_masker: subscribes to ldlidar_ros2's raw 'scan' topic, republishes
    # /robot_001/scan with the pan-tilt mast (46-123deg) and WiFi antenna
    # (268-277deg) self-occlusion sectors NaN'd out — confirmed live against the
    # real hardware 2026-08-10 (see scan_filter.py's module docstring). Also
    # closes the lidar half of the topic-remapping gap (lidar_include below has
    # no remappings at all) as a side effect. Always included alongside
    # lidar_include — harmless with no publisher on 'scan' yet.
    scan_masker = Node(
        package='nav_fleet',
        executable='scan_masker',
        name='scan_masker',
        output='screen',
    )

    # camera_relay: closes the CAMERA half of the same topic-remapping gap
    # (2026-08-10) — depthai-ros's camera.launch.py has no remapping support of
    # its own, so a small relay node republishes its real image_rect topic as
    # /robot_001/camera/image_raw, which ball_detector.py expects. Always
    # included alongside camera_include — harmless with no publisher on
    # image_rect yet.
    camera_relay = Node(
        package='nav_fleet',
        executable='camera_relay',
        name='camera_relay',
        output='screen',
    )

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

    return LaunchDescription([
        serial_device_arg, serial_baud_arg, lidar_launch_file_arg,
        camera_launch_file_arg,
        esp32_driver, lidar_include, camera_include, scan_masker, camera_relay,
    ])
```

- [ ] **Step 2: Replace `src/nav_fleet/launch/sensors_only_launch.py` in full**

```python
# src/nav_fleet/launch/sensors_only_launch.py
# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""Driver layer + EKF + ball_detector, for bare-metal bring-up/debugging use
(RealRobotStartup.md A2's own live driver checks) — deliberately WITHOUT Nav2/
AMCL/map_server. No map required, so this runs even before bedroom_real.yaml
exists.

Refactored 2026-08-10: the five driver nodes (esp32_driver/lidar/camera/
scan_masker/camera_relay) moved out to drivers_only_launch.py. NOTE: the bench
smoke test itself (hil_stage.sh smoke) does NOT use this file any more as of
the same day's later revision — it launches drivers_only_launch.py bare-metal
AND nav2_only_launch.py (skip_nav2:=true) in the container separately, to
actually exercise the container boundary. This file remains for convenient
bare-metal-only driver+EKF+ball_detector bring-up/debugging (A2's own live
checks already use it this way). See
docs/superpowers/plans/2026-08-10-drivers-bare-metal-boot-fix.md.

use_sim_time gating: sim/CI regression relies entirely on Gazebo's own bridge
for /robot_001/{odom,imu/data,scan,camera/image_raw} — matching how
nav2_only_launch.py never launches its own odom/scan/camera source either. The
real-hardware driver layer (drivers_only_launch.py) is skipped entirely when
use_sim_time is true.
"""
import pathlib

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, GroupAction, IncludeLaunchDescription
from launch.conditions import UnlessCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

PKG = pathlib.Path(__file__).parent.parent


def generate_launch_description():
    use_sim_time_arg = DeclareLaunchArgument(
        'use_sim_time', default_value='true',
        description='true for sim/CI regression (Gazebo bridge feeds odom/imu/'
                    'scan/camera directly — the real driver layer is skipped '
                    'entirely); false for the real robot bench.',
    )
    hsv_config_arg = DeclareLaunchArgument(
        'hsv_config', default_value=str(PKG / 'config' / 'hsv_gazebo.yaml'),
        description='ball_detector HSV thresholds — hsv_gazebo.yaml for sim, '
                    'hsv_realcam.yaml for the real robot bench',
    )
    serial_device_arg = DeclareLaunchArgument('serial_device', default_value='/dev/ttyUSB0')
    serial_baud_arg = DeclareLaunchArgument('serial_baud', default_value='115200')
    lidar_launch_file_arg = DeclareLaunchArgument('lidar_launch_file', default_value='')
    camera_launch_file_arg = DeclareLaunchArgument('camera_launch_file', default_value='')

    drivers_include = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(str(PKG / 'launch' / 'drivers_only_launch.py')),
        launch_arguments={
            'serial_device': LaunchConfiguration('serial_device'),
            'serial_baud': LaunchConfiguration('serial_baud'),
            'lidar_launch_file': LaunchConfiguration('lidar_launch_file'),
            'camera_launch_file': LaunchConfiguration('camera_launch_file'),
        }.items(),
    )
    real_hardware_drivers = GroupAction(
        condition=UnlessCondition(LaunchConfiguration('use_sim_time')),
        actions=[drivers_include],
    )

    # Always on, both modes — matches nav2_only_launch.py's own always-on
    # pattern for these two nodes exactly (same params, same remappings).
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

- [ ] **Step 3: Verify args are unchanged on `sensors_only_launch.py` (regression check)**

```bash
ros2 launch nav_fleet sensors_only_launch.py --show-args
```
Expected: exactly 6 arguments — `use_sim_time`, `hsv_config`, `serial_device`,
`serial_baud`, `lidar_launch_file`, `camera_launch_file` — same names/defaults
as before this task's edit (this step is a pure refactor for this file, zero
behavior change to it, even though it's no longer what the smoke test itself
calls).

- [ ] **Step 4: Verify `drivers_only_launch.py` args on its own**

```bash
ros2 launch nav_fleet drivers_only_launch.py --show-args
```
Expected: exactly 4 arguments — `serial_device` (default `/dev/ttyUSB0`),
`serial_baud` (default `115200`), `lidar_launch_file` (default `''`),
`camera_launch_file` (default `''`).

- [ ] **Step 5: Live end-to-end check on the real Jetson**

```bash
ros2 launch nav_fleet sensors_only_launch.py \
  use_sim_time:=false \
  serial_device:=/dev/ttyTHS1 serial_baud:=115200 \
  lidar_launch_file:=$HOME/ros2_drivers_ws/install/ldlidar_ros2/share/ldlidar_ros2/launch/ld19.launch.py \
  camera_launch_file:=/opt/ros/jazzy/share/depthai_ros_driver/launch/camera.launch.py
```
Expected (watch the console output, matching every one of today's earlier live
verifications): `esp32_driver up — ...`, lidar's `ldlidar communication is
normal.`, camera's `Camera with MXID: ... connected!`, `scan_masker up — ...`,
`camera_relay up — ...`, and `ball_detector up — ...`. Ctrl+C to stop; confirm no
orphaned processes remain (`pgrep -fa "esp32_driver|ldlidar|depthai|scan_masker|
camera_relay|ball_detector"` returns nothing).

- [ ] **Step 6: Commit**

```bash
git add src/nav_fleet/launch/drivers_only_launch.py src/nav_fleet/launch/sensors_only_launch.py
git commit -m "refactor: extract drivers_only_launch.py from sensors_only_launch.py

Pure refactor, zero behavior change to sensors_only_launch.py (verified via
--show-args producing the identical 6 arguments, and a live end-to-end run on
the real Jetson producing the same 6 'up' log lines as every earlier
verification today). drivers_only_launch.py is what Tasks 3 and 5 launch
bare-metal; sensors_only_launch.py itself remains for convenient bare-metal
driver+EKF+ball_detector bring-up/debugging (A2's own live checks).

Task 1 of docs/superpowers/plans/2026-08-10-drivers-bare-metal-boot-fix.md."
```

---

### Task 2: Add `skip_nav2` to `nav2_only_launch.py`

**Files:**
- Modify: `src/nav_fleet/launch/nav2_only_launch.py`

**Interfaces:**
- Produces: a new `skip_nav2` launch arg (default `'false'`). When `'true'`,
  EKF and `ball_detector` still launch exactly as before; the Nav2/AMCL/
  map_server bringup (the existing `nav2` `TimerAction`) is skipped entirely
  — no `map` argument needs to resolve to a real file in that case.
- Consumed by: Task 4 (`container_entrypoint.sh`'s `smoke_test` branch passes
  `skip_nav2:=true`). Task 3 (`robot_boot.sh`, via `container_entrypoint.sh`'s
  `mission` branch) relies on the DEFAULT (`false`) — no change needed there.

- [ ] **Step 1: Read the current file to confirm line numbers before editing**

```bash
grep -n "^from launch\|^def generate_launch_description\|nav2 = TimerAction\|return LaunchDescription" src/nav_fleet/launch/nav2_only_launch.py
```
Use the real output to locate the exact lines — don't assume they match this
plan's line numbers verbatim if anything else has changed the file since
2026-08-10.

- [ ] **Step 2: Add the `skip_nav2` argument and import**

Add to the imports (near the top, alongside the existing `from launch.actions
import (...)` line):
```python
from launch.actions import (DeclareLaunchArgument, GroupAction,
                            IncludeLaunchDescription, TimerAction)
from launch.conditions import UnlessCondition
```
(This replaces the current `from launch.actions import (DeclareLaunchArgument,
IncludeLaunchDescription, TimerAction)` line — same imports plus `GroupAction`
— and adds the new `from launch.conditions import UnlessCondition` line, which
this file doesn't currently have at all.)

Add a new argument declaration alongside the existing ones (after `map_arg`):
```python
    skip_nav2_arg = DeclareLaunchArgument(
        'skip_nav2', default_value='false',
        description='true skips Nav2/AMCL/map_server bringup entirely — EKF '
                    'and ball_detector still start. Used by the bench smoke '
                    'test to exercise the real container boundary without '
                    'needing a real map to exist yet (RealRobotStartup.md '
                    'A2 runs before A3/A4). Real missions and HIL always use '
                    'the default false.',
    )
```

- [ ] **Step 3: Gate the existing `nav2` `TimerAction` behind it**

Find:
```python
    nav2_bringup_dir = get_package_share_directory('nav2_bringup')
    nav2 = TimerAction(
        period=LaunchConfiguration('start_delay'),
        actions=[IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                os.path.join(nav2_bringup_dir, 'launch', 'bringup_launch.py')
            ),
            launch_arguments={
                'namespace': 'robot_001',
                'use_namespace': 'true',
                'use_sim_time': LaunchConfiguration('use_sim_time'),
                'params_file': str(PKG / 'config' / 'nav2_params.yaml'),
                'map': LaunchConfiguration('map'),
                'use_composition': 'True',
                'autostart': 'true',
                'log_level': LaunchConfiguration('log_level'),
            }.items(),
        )],
    )
```

Wrap it (same variable name `nav2`, just now the gated version — no other line
in this function references `nav2` before the final `return`, so nothing else
needs to change):
```python
    nav2_bringup_dir = get_package_share_directory('nav2_bringup')
    nav2 = GroupAction(
        condition=UnlessCondition(LaunchConfiguration('skip_nav2')),
        actions=[TimerAction(
            period=LaunchConfiguration('start_delay'),
            actions=[IncludeLaunchDescription(
                PythonLaunchDescriptionSource(
                    os.path.join(nav2_bringup_dir, 'launch', 'bringup_launch.py')
                ),
                launch_arguments={
                    'namespace': 'robot_001',
                    'use_namespace': 'true',
                    'use_sim_time': LaunchConfiguration('use_sim_time'),
                    'params_file': str(PKG / 'config' / 'nav2_params.yaml'),
                    'map': LaunchConfiguration('map'),
                    'use_composition': 'True',
                    'autostart': 'true',
                    'log_level': LaunchConfiguration('log_level'),
                }.items(),
            )],
        )],
    )
```

- [ ] **Step 4: Add `skip_nav2_arg` to the returned `LaunchDescription`**

Find the `return LaunchDescription([...])` at the end of the function and add
`skip_nav2_arg` to the list (alongside the other `*_arg` declarations already
there — exact position among them doesn't matter, launch args aren't ordered).

- [ ] **Step 5: Verify args**

```bash
ros2 launch nav_fleet nav2_only_launch.py --show-args
```
Expected: the existing args (`start_delay`, `log_level`, `use_sim_time`,
`hsv_config`, `map`) PLUS the new `skip_nav2` (default `false`).

- [ ] **Step 6: Live check — `skip_nav2:=true` skips Nav2, EKF/ball_detector still start**

On the real Jetson (or workstation with `use_sim_time:=true` for a quick sim
check if the Jetson isn't available — either proves the gating logic, since
`skip_nav2` doesn't depend on `use_sim_time` at all):
```bash
ros2 launch nav_fleet nav2_only_launch.py skip_nav2:=true use_sim_time:=true
```
Expected: `ekf_filter_node` and `ball_detector` start (their own log lines
appear), and NONE of Nav2's own startup lines appear (no `bt_navigator`,
`controller_server`, `planner_server`, `map_server`, `amcl` — grep the output
for any of those names and confirm zero matches). Then confirm the OPPOSITE
with the default:
```bash
ros2 launch nav_fleet nav2_only_launch.py use_sim_time:=true
```
Expected: Nav2's own components DO start this time (matches existing/unchanged
behavior — this is the regression check that Task 3/HIL/mission mode are
unaffected).

- [ ] **Step 7: Commit**

```bash
git add src/nav_fleet/launch/nav2_only_launch.py
git commit -m "feat: nav2_only_launch.py -- add skip_nav2 arg

Lets the bench smoke test exercise EKF+ball_detector inside the SAME container
code path a real mission uses, without needing a real map to exist yet
(RealRobotStartup.md A2 runs before A3/A4 build one). Default false -- real
missions and HIL are unaffected, verified live both ways (skip_nav2:=true
starts EKF/ball_detector with zero Nav2 component log lines; the default
starts Nav2 exactly as before).

Task 2 of docs/superpowers/plans/2026-08-10-drivers-bare-metal-boot-fix.md."
```

---

### Task 3: `robot_boot.sh` — start the driver layer bare-metal before the container

**Files:**
- Modify: `scripts/robot_boot.sh` (full replacement — see below)

**Interfaces:**
- Consumes: Task 1's `drivers_only_launch.py`, and its `camera_relay up` log
  line as the readiness signal. Does NOT touch `skip_nav2` at all — relies on
  its default (`false`), so the container's Nav2 bringup is unchanged from
  today.

- [ ] **Step 1: Replace `scripts/robot_boot.sh` in full**

```bash
#!/bin/bash
# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
#
# Boot-time entry point for the real, deployed Waveshare UGV-PT (RealRobotStartup.md
# Part A). Two things run, in order: the real-hardware driver layer BARE-METAL
# (drivers_only_launch.py — esp32_driver/lidar/camera/scan_masker/camera_relay), then
# the SAME container image and entrypoint HIL uses (scripts/container_entrypoint.sh,
# ROBOT_MODE=mission — Nav2/EKF/ball_detector/mission_runner, skip_nav2 defaults to
# false so Nav2 runs exactly as before) — only the launch-argument VALUES differ from
# HIL (real-robot context: use_sim_time=false, the real-camera HSV profile, the real
# room's map).
#
# Fixed 2026-08-10 (see docs/superpowers/plans/2026-08-10-drivers-bare-metal-boot-fix.md
# for the full story): this script used to start ONLY the container. Nothing ever
# started the real driver layer for a power-on mission run — Nav2/EKF/ball_detector
# came up inside the container expecting real /robot_001/{odom,scan,camera,imu} data
# with nothing producing it. The container image was also never going to be able to
# run the driver layer itself even if asked to — ldlidar_ros2/depthai-ros were never
# installed in the Docker image, and per this project's own docker-brain-unification
# decision, never should be: the driver layer stays bare-metal, only Nav2/EKF/
# ball_detector/mission_runner run in the container.
#
# NOT yet exercised by CI/HIL (a power cycle can't be simulated there, and HIL's own
# use_sim_time=true path never needs the real driver layer at all — Gazebo provides
# sensor data instead). Run this manually over SSH first and confirm a full mission2
# day passes with your own eyes-on check before trusting the systemd unit
# (scripts/robot-mission.service) that calls it automatically at boot.
#
# Known, separately-tracked gap this script still has (RealRobotStartup.md A4, not
# part of the 2026-08-10 fix above): HSV_CONFIG_FILE below is hardcoded to
# hsv_realcam.yaml, which doesn't exist until HSV calibration is done — a full run of
# this script will still fail at the container step until then.
set -euo pipefail

REPO="$HOME/autonomous-fleet-testbed"
cd "$REPO"

SHA=$(git rev-parse HEAD)
IMAGE="ghcr.io/sdfinn/autonomous-fleet-testbed:${SHA}"

echo "=== [robot-boot] checking image ${IMAGE} is already local (no pull, ever) ==="
if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  echo "FATAL: ${IMAGE} is not present locally — this checkout's sha (${SHA}) was" >&2
  echo "never pulled here by a green stage-4-hil run. Sync to a sha that WAS:" >&2
  echo "  scripts/hil_stage.sh sync <the last green run's commit sha>  (from the workstation)" >&2
  exit 1
fi

LOG_DIR="$HOME/fleet-ci-data/robot_boot_logs"
mkdir -p "$LOG_DIR"
TS=$(date +%Y%m%dT%H%M%S)

# --- Real-hardware driver layer, BARE-METAL (fixed 2026-08-10) ---
echo "=== [robot-boot] starting the real driver layer bare-metal ==="
set +u
source /opt/ros/jazzy/setup.bash
source "$REPO/install/setup.bash"
set -u
bash "$REPO/scripts/regen_cyclonedds_config.sh"

DRIVERS_LOG="$LOG_DIR/drivers_${TS}.log"
rm -f "$DRIVERS_LOG"
ros2 launch nav_fleet drivers_only_launch.py \
  serial_device:=/dev/ttyTHS1 \
  serial_baud:=115200 \
  lidar_launch_file:="$HOME/ros2_drivers_ws/install/ldlidar_ros2/share/ldlidar_ros2/launch/ld19.launch.py" \
  camera_launch_file:=/opt/ros/jazzy/share/depthai_ros_driver/launch/camera.launch.py \
  > "$DRIVERS_LOG" 2>&1 < /dev/null &
DRIVERS_PID=$!

# Clean bare-metal teardown on ANY exit path (mission success, mission failure, this
# script killed) — SIGINT (not SIGKILL) so ros2 launch propagates it to esp32_driver/
# lidar/camera/scan_masker/camera_relay the same clean way Ctrl+C already does
# (CLAUDE.md's own established teardown pattern), instead of leaving them orphaned to
# poison the NEXT boot's driver layer.
cleanup_drivers() {
  echo "=== [robot-boot] stopping the bare-metal driver layer (pid ${DRIVERS_PID}) ==="
  kill -INT "$DRIVERS_PID" 2>/dev/null || true
  wait "$DRIVERS_PID" 2>/dev/null || true
}
trap cleanup_drivers EXIT

echo "=== [robot-boot] waiting up to 60s for the driver layer to report up ==="
deadline=$((SECONDS + 60))
count=0
until [ "$count" -ge 1 ]; do
  if (( SECONDS >= deadline )); then
    echo "FATAL: drivers_only_launch.py not up within 60s — see $DRIVERS_LOG" >&2
    tail -n 40 "$DRIVERS_LOG" >&2 || true
    exit 1
  fi
  sleep 2
  count=$(grep -c 'camera_relay up' "$DRIVERS_LOG" 2>/dev/null || true)
  count="${count:-0}"
done
echo "=== [robot-boot] driver layer up ==="

# --- Nav2/EKF/ball_detector/mission_runner, containerized (unchanged) ---
echo "=== [robot-boot] running ${IMAGE} (real-robot context, operator ball placement) ==="
# RUNNER_TYPE=real_robot matches the convention every other real-robot telemetry row
# in this project already uses. MISSION2_SELF_REPORT=1: no ground-truth judging (no
# Gazebo on the real robot) — mission_runner logs each leg's own self-reported
# PASS/FAIL instead; analysis of the resulting logs/photos happens after, manually.
# ROBOT_MODE=mission is hardcoded here, never a variable — standalone power-on can
# never run a smoke test (design spec). skip_nav2 is NOT set here — its default
# (false) means Nav2 runs exactly as it always has.
docker rm -f robot_mission 2>/dev/null || true
mkdir -p "$REPO/reports"
docker run --rm --name robot_mission --network host --ipc host \
  -v "$REPO/reports:/ros2_ws/reports" \
  -v "$HOME/fleet-ci-data:/root/fleet-ci-data" \
  -e USE_SIM_TIME=false \
  -e HSV_CONFIG_FILE=hsv_realcam.yaml \
  -e NAV2_MAP_FILE=bedroom_real.yaml \
  -e MISSION2_SELF_REPORT=1 \
  -e RUNNER_TYPE=real_robot \
  -e ROBOT_MODE=mission \
  "$IMAGE" bash /ros2_ws/scripts/container_entrypoint.sh \
  2>&1 | tee "$LOG_DIR/robot_boot_${TS}.log"
```

- [ ] **Step 2: Syntax-check**

```bash
bash -n scripts/robot_boot.sh && echo "syntax OK"
```
Expected: `syntax OK`.

- [ ] **Step 3: Live dry-run of the driver-layer half only, on the real Jetson**

Run the script and Ctrl+C right after seeing "driver layer up" (before the
container step, which will still fail today per the Global Constraints'
hsv_realcam.yaml note). Confirm: `$DRIVERS_LOG` shows the same 5 "up"/
"connected" lines as Task 1 Step 5, `cleanup_drivers` fires on Ctrl+C (its own
echo line appears), and `pgrep -fa "esp32_driver|ldlidar|depthai|scan_masker|
camera_relay"` returns nothing afterward.

- [ ] **Step 4: Commit**

```bash
git add scripts/robot_boot.sh
git commit -m "fix: robot_boot.sh -- actually start the real driver layer

Real, previously-undiscovered gap: ROBOT_MODE=mission only ever launched Nav2/
EKF/ball_detector inside the container -- nothing started esp32_driver/lidar/
camera/scan_masker/camera_relay for a real power-on mission run. Fixed by
launching Task 1's drivers_only_launch.py bare-metal first, waiting for it to
report up (camera_relay up, its own existing log line), then starting the
container exactly as before (skip_nav2 defaults to false -- Nav2 unaffected).
Clean teardown via a trap so a failed/killed run never orphans the driver
layer for the next boot.

Verified live on the real Jetson: the driver-layer half comes up with the same
5 confirmation lines as every earlier standalone verification; Ctrl+C cleanly
tears it down with no orphaned processes.

Task 3 of docs/superpowers/plans/2026-08-10-drivers-bare-metal-boot-fix.md.
Full end-to-end (through the container step) still blocked on
RealRobotStartup.md A4 (hsv_realcam.yaml doesn't exist yet) -- separately
tracked, not part of this fix."
```

---

### Task 4: `container_entrypoint.sh`'s `smoke_test` branch — EKF+ball_detector via `nav2_only_launch.py skip_nav2:=true`

**Files:**
- Modify: `scripts/container_entrypoint.sh` (the `smoke_test)` case branch only)

**Interfaces:**
- Consumes: Task 2's `skip_nav2` arg on `nav2_only_launch.py`.
- Produces: a container that, once up, logs `ball_detector up` (unchanged log
  line from `ball_detector.py`) and then blocks (via `wait "$NAV2_PID"`) until
  torn down externally. Task 5 (`hil_stage.sh smoke`) starts this container
  detached (`docker run -d`), polls `docker logs <name>` for that same
  `ball_detector up` line, then tears it down with `docker rm -f` when the
  smoke test finishes — matching this project's own established
  container-teardown convention (a hard `docker rm -f`, not a graceful
  signal, since the whole container's namespace goes away either way).
- Does NOT touch `tools/smoke_test.py` itself, which no longer runs inside
  this container at all — it runs bare-metal, orchestrated directly by
  `hil_stage.sh smoke` (Task 5), since its operator ball-placement prompt
  needs a real terminal, which a detached container invocation doesn't have.

- [ ] **Step 1: Replace the `smoke_test)` branch**

Find the current branch (starts with `smoke_test)` and the comment `# Real-
robot driver + bench smoke-test design spec (2026-08-05/06): the THIRD
ROBOT_MODE...`) and replace the WHOLE branch (through its terminating `;;`)
with:

```bash
  smoke_test)
    # EKF + ball_detector ONLY, no Nav2 (skip_nav2:=true) -- proves EKF/
    # ball_detector actually work THROUGH the real container boundary (the
    # same interface a real mission depends on), not a bare-metal stand-in.
    # Redesigned 2026-08-10 (see docs/superpowers/plans/2026-08-10-drivers-
    # bare-metal-boot-fix.md): the real driver layer runs bare-metal OUTSIDE
    # this container now -- scripts/hil_stage.sh smoke starts it before this
    # container, and starts this container DETACHED (docker run -d), polling
    # this branch's own log for readiness rather than waiting on this script
    # to exit. tools.smoke_test.py itself runs bare-metal too, from
    # hil_stage.sh's own SSH session -- its operator ball-placement prompt
    # needs a real terminal, which this detached container doesn't have.
    NAV2_LOG="/ros2_ws/reports/nav2_container_$(date +%Y%m%dT%H%M%S).log"
    rm -f "$NAV2_LOG"
    ros2 launch nav_fleet nav2_only_launch.py \
      use_sim_time:="${USE_SIM_TIME}" \
      hsv_config:="/ros2_ws/src/nav_fleet/config/${HSV_CONFIG_FILE}" \
      skip_nav2:=true \
      > "$NAV2_LOG" 2>&1 < /dev/null &
    NAV2_PID=$!

    echo "=== [container-entrypoint] waiting up to 60s for EKF+ball_detector to report up ==="
    deadline=$((SECONDS + 60))
    until [ "${count:-0}" -ge 1 ]; do
      if (( SECONDS >= deadline )); then
        echo "FATAL: EKF+ball_detector not up within 60s -- see $NAV2_LOG" >&2
        tail -n 40 "$NAV2_LOG" >&2 || true
        exit 1
      fi
      sleep 2
      count=$(grep -c 'ball_detector up' "$NAV2_LOG" 2>/dev/null || true)
      count="${count:-0}"
    done
    echo "=== [container-entrypoint] EKF+ball_detector up -- idling until torn down externally ==="
    wait "$NAV2_PID"
    ;;
```

- [ ] **Step 2: Syntax-check**

```bash
bash -n scripts/container_entrypoint.sh && echo "syntax OK"
```
Expected: `syntax OK`.

- [ ] **Step 3: Update this file's own top-of-file env-var doc comment**

Find the `# Optional (smoke_test mode only):` comment block near the top of
the file and remove the now-stale `LIDAR_LAUNCH_FILE`/`CAMERA_LAUNCH_FILE`/
`SMOKE_BALL_OPS`/`RUNNER_TYPE`/`COMMIT_SHA`/`CI_RUN_NUMBER` lines (those were
only ever relevant to the old sensors_only_launch.py-in-container +
`tools.smoke_test` invocation, both gone from this branch now) — leave just:
```
# Optional (smoke_test mode only):
#   (none -- this mode now only launches nav2_only_launch.py with
#   skip_nav2:=true; hil_stage.sh smoke handles the driver layer and the
#   smoke test script itself, both bare-metal, outside this container)
```

- [ ] **Step 4: Commit**

```bash
git add scripts/container_entrypoint.sh
git commit -m "fix: container_entrypoint.sh smoke_test branch -- EKF+ball_detector via nav2_only_launch.py

Replaces the old sensors_only_launch.py-in-container approach, which could
never actually reach real lidar/camera hardware (vendor packages never
installed in the image). Now launches nav2_only_launch.py with the new
skip_nav2:=true (Task 2) -- the exact same code path a real mission uses for
EKF/ball_detector, just without needing a real map yet. Blocks (wait
\$NAV2_PID) until torn down externally by hil_stage.sh smoke (Task 5), which
now starts this container detached and polls its logs for readiness instead
of waiting on this script to exit.

Task 4 of docs/superpowers/plans/2026-08-10-drivers-bare-metal-boot-fix.md."
```

---

### Task 5: `hil_stage.sh smoke` — bare-metal drivers + containerized EKF/ball_detector + bare-metal smoke test

**Files:**
- Modify: `scripts/hil_stage.sh` (the `smoke()` function only)

**Interfaces:**
- Consumes: Task 1's `drivers_only_launch.py` (bare-metal), Task 4's revised
  `container_entrypoint.sh` `smoke_test` branch (containerized, detached),
  `tools/smoke_test.py`'s existing CLI (`--runner-type`, unchanged).
- Does NOT touch `smoke_ci()` — verify it's untouched after this task.

- [ ] **Step 1: Replace the `smoke()` function**

Find the current `smoke()` function and replace it in full with:

```bash
smoke() {
  # Bench smoke test (real-robot driver + smoke-test design spec, 2026-08-05/06,
  # redesigned 2026-08-10 -- see docs/superpowers/plans/2026-08-10-drivers-bare-
  # metal-boot-fix.md): exercises the REAL production interface -- EKF +
  # ball_detector running INSIDE the container (nav2_only_launch.py,
  # skip_nav2:=true), talking to the real driver layer bare-metal outside it --
  # not a bare-metal stand-in for EKF/ball_detector. Only the driver layer
  # (vendor lidar/camera packages, never installed in the image, and per this
  # project's architecture never should be) runs bare-metal. ATTENDED: this
  # prompts you, via THIS terminal, to place the yellow ball.
  require_ip
  local sha="${1:?usage: hil_stage.sh smoke <git-sha>}"
  sync "$sha"

  local image="ghcr.io/sdfinn/autonomous-fleet-testbed:${sha}"
  echo "=== [smoke] checking ${image} is present locally on the Jetson ==="
  if ! jssh "docker image inspect ${image} >/dev/null 2>&1"; then
    echo "FATAL: ${image} is not present locally on the Jetson -- sync to a sha a" >&2
    echo "green stage-3-arm64 run already pushed, or docker pull it by hand first." >&2
    exit 1
  fi

  local hsv="${HSV_CONFIG_FILE:-hsv_gazebo.yaml}"

  echo "=== [smoke] starting the real driver layer bare-metal ==="
  jssh "cd ${JETSON_REPO} && \
    (source /opt/ros/jazzy/setup.bash; source install/setup.bash; \
     bash scripts/regen_cyclonedds_config.sh; \
     rm -f /tmp/smoke_drivers.log; \
     nohup ros2 launch nav_fleet drivers_only_launch.py \
       serial_device:=${SERIAL_DEVICE:-/dev/ttyTHS1} \
       serial_baud:=${SERIAL_BAUD:-115200} \
       lidar_launch_file:=\$HOME/ros2_drivers_ws/install/ldlidar_ros2/share/ldlidar_ros2/launch/ld19.launch.py \
       camera_launch_file:=/opt/ros/jazzy/share/depthai_ros_driver/launch/camera.launch.py \
       > /tmp/smoke_drivers.log 2>&1 < /dev/null &)"

  echo "=== [smoke] waiting up to 60s for the driver layer to report up ==="
  local deadline=$((SECONDS + 60))
  local count=0
  until [ "$count" -ge 1 ]; do
    if (( SECONDS >= deadline )); then
      echo "FATAL: drivers_only_launch.py not up within 60s on the Jetson -- see" >&2
      echo "/tmp/smoke_drivers.log there:" >&2
      jssh "tail -n 40 /tmp/smoke_drivers.log" >&2 || true
      jssh "pkill -INT -f 'ros2 launch nav_fleet drivers_only_launch.py'" || true
      exit 1
    fi
    sleep 2
    count=$(jssh "grep -c 'camera_relay up' /tmp/smoke_drivers.log 2>/dev/null || true")
    count="${count:-0}"
  done
  echo "=== [smoke] driver layer up ==="

  echo "=== [smoke] starting EKF+ball_detector in the container (ROBOT_MODE=smoke_test) ==="
  jssh "docker rm -f hil_smoke_test 2>/dev/null || true; \
    docker run -d --name hil_smoke_test --network host --ipc host \
      -v \$HOME/autonomous-fleet-testbed/reports:/ros2_ws/reports \
      -v \$HOME/fleet-ci-data:/root/fleet-ci-data \
      -e USE_SIM_TIME=false -e HSV_CONFIG_FILE=${hsv} \
      -e ROBOT_MODE=smoke_test -e RUNNER_TYPE=real_robot \
      ${image} bash /ros2_ws/scripts/container_entrypoint.sh"

  echo "=== [smoke] waiting up to 60s for EKF+ball_detector to report up in the container ==="
  deadline=$((SECONDS + 60))
  count=0
  until [ "$count" -ge 1 ]; do
    if (( SECONDS >= deadline )); then
      echo "FATAL: EKF+ball_detector not up within 60s in the container -- see" >&2
      jssh "docker logs hil_smoke_test 2>&1 | tail -n 40" >&2 || true
      jssh "docker rm -f hil_smoke_test" || true
      jssh "pkill -INT -f 'ros2 launch nav_fleet drivers_only_launch.py'" || true
      exit 1
    fi
    sleep 2
    count=$(jssh "docker logs hil_smoke_test 2>&1 | grep -c 'ball_detector up' || true")
    count="${count:-0}"
  done
  echo "=== [smoke] EKF+ball_detector up in the container -- running the smoke test"
  echo "(you will be prompted to place the yellow ball when the correlation check"
  echo "starts) =="
  # Plain SSH (no docker -it involved this time -- that's exactly what broke the
  # OLD container-based invocation in a non-interactive tool environment on
  # 2026-08-10). -t is still used here purely to match every other attended step
  # in this file; a bare python3 input() prompt doesn't actually need a pty.
  local rc=0
  ssh -t -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new \
    "${JETSON_USER}@${JETSON_IP}" \
    "cd ${JETSON_REPO} && source /opt/ros/jazzy/setup.bash && source install/setup.bash && \
     python3 -m tools.smoke_test --runner-type real_robot" || rc=$?

  echo "=== [smoke] tearing down the container and the bare-metal driver layer ==="
  jssh "docker rm -f hil_smoke_test" || true
  jssh "pkill -INT -f 'ros2 launch nav_fleet drivers_only_launch.py'" || true
  return "$rc"
}
```

Note the `local rc=0` / `|| rc=$?` capture pattern for the `ssh -t ...` call —
deliberate, not incidental: under this file's own `set -euo pipefail`,
capturing a command's exit code via a bare `rc=$?` on the line *after* it
would trigger an immediate script exit if that command returned non-zero (a
smoke test FAIL, exactly the case the teardown step exists for) — the
teardown below it would never run, leaving BOTH the container and the
bare-metal driver layer orphaned on every failed smoke test. The `|| rc=$?`
form avoids that: `set -e` only fires if the whole `||`-chain's final command
fails, and a plain assignment always succeeds.

- [ ] **Step 2: Syntax-check**

```bash
bash -n scripts/hil_stage.sh && echo "syntax OK"
```
Expected: `syntax OK`.

- [ ] **Step 3: Live run on the real Jetson**

```bash
export JETSON_IP=$(scripts/hil_stage.sh discover)
scripts/hil_stage.sh smoke <the commit sha you're testing>
```
Run this from a REAL interactive terminal (not a non-interactive tool
environment) — place the yellow ball (~0.75m / 2.5ft ahead, on a riser so its
center sits ~6in / 0.1524m up) when prompted. Expected, in order: the driver
layer's 5 "up"/"connected" lines, then the container's `ball_detector up`
line (via `docker logs`, printed by this script's own polling loop, not
directly visible unless you also tail `docker logs -f hil_smoke_test` in a
second terminal — optional but useful the first time), then
`tools/smoke_test.py`'s own PASS/FAIL summary for each check (topics, photo,
ball correlation, motion pulse). After it exits (either PASS or FAIL),
confirm cleanup ran:
```bash
ssh mike@jetson.local 'docker ps -a --filter name=hil_smoke_test; \
  pgrep -fa "esp32_driver|ldlidar|depthai|scan_masker|camera_relay"'
```
Expected: no `hil_smoke_test` container listed (or listed as removed), and no
bare-metal driver processes running.

- [ ] **Step 4: Verify `smoke-ci` is untouched**

```bash
grep -n "^smoke_ci()" -A 30 scripts/hil_stage.sh
```
Expected: identical to before this task — still builds a `docker run
... ROBOT_MODE=smoke_test ... SMOKE_BALL_OPS=gz -e USE_SIM_TIME=true ...`
invocation, unchanged. This task only replaces `smoke()`.

- [ ] **Step 5: Commit**

```bash
git add scripts/hil_stage.sh
git commit -m "fix: hil_stage.sh smoke -- exercise the real container boundary

Redesigned so EKF+ball_detector run INSIDE the container (nav2_only_launch.py,
skip_nav2:=true -- Task 2/4) for the smoke test too, not a bare-metal stand-in
-- proves the actual production interface works, which is exactly where this
project's real bugs have lived (CycloneDDS big-message, interface selection).
Only the driver layer (which genuinely can't run in the container) stays
bare-metal. Container is started detached (docker run -d) and torn down with
docker rm -f -- this project's own established container-teardown convention
-- with a set -e-safe exit-code capture so a FAILED smoke test still tears
down both the container and the bare-metal driver layer (see the function's
own comment for why a naive 'rc=\$?' on the next line would have skipped that).

smoke_ci() is untouched -- its USE_SIM_TIME=true container path never needed
the real driver layer and isn't affected by any of this.

Task 5 of docs/superpowers/plans/2026-08-10-drivers-bare-metal-boot-fix.md."
```

---

### Task 6: Update docs once Tasks 1-5 are verified live

**Files:**
- Modify: `RealRobotStartup.md`
- Modify: `CLAUDE.md`

**Interfaces:** None — documentation only.

- [ ] **Step 1: Update `RealRobotStartup.md`'s A6 section**

Find A6 ("Build the power-on boot sequence") and add a note above its existing
steps:

```markdown
**Driver layer fix, 2026-08-10** (see
docs/superpowers/plans/2026-08-10-drivers-bare-metal-boot-fix.md): `robot_boot.sh`
now starts the real driver layer (`drivers_only_launch.py` — esp32_driver/lidar/
camera/scan_masker/camera_relay) bare-metal BEFORE the container, using the same
real hardware constants confirmed throughout A2 (`/dev/ttyTHS1`@115200, the real
`ld19.launch.py`/`camera.launch.py` paths). Previously nothing started the driver
layer for a real mission run at all — found and fixed the same day as the camera
remapping fix, tracing the boot path to answer a different question. Still
blocked from a full end-to-end run by A4 (HSV calibration) not being done yet —
`HSV_CONFIG_FILE=hsv_realcam.yaml` in `robot_boot.sh` references a file that
doesn't exist.
```

- [ ] **Step 2: Update `RealRobotStartup.md`'s smoke-test step (A2)**

Find the bench smoke test bullet (the one starting `**Run the bench smoke test —
do this before anything past this point relies on the driver layer.**`) and add:

```markdown
**Redesigned 2026-08-10**: `scripts/hil_stage.sh smoke <sha>` now runs the real
driver layer bare-metal AND EKF+ball_detector inside the container
(`nav2_only_launch.py skip_nav2:=true`) — exercising the actual production
container boundary, not a bare-metal stand-in. The old
`ROBOT_MODE=smoke_test`-launches-`sensors_only_launch.py`-in-container approach
never actually worked for real hardware — the container never had the vendor
lidar/camera packages installed. Run this from a real interactive terminal (the
operator ball-placement prompt needs one).
```

- [ ] **Step 3: Update `CLAUDE.md`'s NEXT SESSION section**

Add a new dated entry (following this file's own established superseding
convention: today's current top entry becomes `## (superseded <date>) PREVIOUS
(...)`). Write the entry against the REAL verification output from Tasks 1-5's
own live-run steps, captured at execution time — not invented now, before that
evidence exists. Cover exactly these four things, each grounded in a real log
line or command output you actually saw:
1. What the gap was (mission mode never started the driver layer; the smoke
   test's original container path never could have worked, since the vendor
   packages were never in the image) AND the design correction mid-planning
   (the smoke test needed to exercise the real container boundary, not a
   bare-metal EKF/ball_detector stand-in — Mike's own catch, not something
   caught in the first draft).
2. Why it wasn't caught sooner (HIL always runs `use_sim_time=true`, so it
   structurally can't exercise this code path — cite `stage-4-hil`'s own
   `USE_SIM_TIME` env var in `ci.yml` as the concrete evidence, not just the
   claim).
3. The fix (extract `drivers_only_launch.py`; add `skip_nav2` to
   `nav2_only_launch.py`; bare-metal both `robot_boot.sh` and `hil_stage.sh
   smoke`, with EKF/ball_detector now containerized in the smoke test too) —
   one line each, pointing at this plan file rather than re-explaining it.
4. What was actually verified live vs. what's still blocked (Task 3's
   driver-layer half came up clean; the full `robot_boot.sh` run through the
   container step is still blocked on A4/`hsv_realcam.yaml`, per this plan's
   own Global Constraints) — state this as fact from what you observed, not
   as an assumption carried over from the plan.

- [ ] **Step 4: Commit**

```bash
git add RealRobotStartup.md CLAUDE.md
git commit -m "docs: record the driver-layer bare-metal boot fix

Task 6 of docs/superpowers/plans/2026-08-10-drivers-bare-metal-boot-fix.md."
```
