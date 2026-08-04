# Docker Brain: Unifying Real-Robot and HIL Deployment — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move Nav2/EKF/`ball_detector`/`mission_runner` — "the brain" — into one Docker
image/container that runs identically (same launch file, same launch-argument shape)
on HIL and the real robot, converging the two deployment paths onto one.

**Architecture:** One image (extends the existing Dockerfile), one one-shot container
entrypoint (`scripts/container_entrypoint.sh`) that launches `nav2_only_launch.py` with
context-driven launch arguments, waits for Nav2 to report active, runs
`nav_fleet.mission_runner --day`, exits. HIL's Gazebo-dependent test harness (ball
placement, ground-truth judging) stays on the workstation, unchanged — it never runs on
the real robot either, so it was never part of what needs to converge. The real robot
gets a new, simpler self-report telemetry path (own checklist result only, no
ground-truth judging — analysis happens after, from logs/photos, not in real time).

**Tech Stack:** ROS2 Jazzy, Docker (`--network host --ipc host`), bash, Python 3.12,
pytest.

## Global Constraints

- Bare metal on the Jetson = only what's kept current via `apt upgrade`/vendor install,
  with **zero build of our own repo, ever**, once this plan lands — except the vendor
  driver layer (`ugv_ws`, `/dev` access), which stays bare regardless of its own build
  mechanism (device access, not this rule, justifies it).
- `nav2_only_launch.py` stays the **one** launch file for both contexts — no
  `robot_launch.py` is created.
- No `docker pull` and no tag-selection scheme at deploy time, in HIL or on the real
  robot — whatever image is already cached locally on the Jetson is the image that
  runs. (CI's own `stage-4-hil` pull step, which primes that local cache, is
  unaffected and unchanged.)
- Ball placement, ground-truth reading (`gz topic`/`gz service` — a separate protocol
  from CycloneDDS, unverified for cross-machine reachability), and judging stay on the
  **workstation** in HIL, unchanged from today. This code (`tools/mission2_harness.py`)
  is HARNESS-only by its own docstring and never runs on the real robot either way.
- The real robot logs **self-reported** PASS/FAIL per leg (from Nav2's own goal
  completion, via `mission_runner`'s existing checklist) — no ground-truth judging, no
  `tools/mission2_harness` import from robot code. Analysis of logs/photos happens
  after, manually (R2 scope, per `RealRobotStartup.md`).
- Manual verification before automation, at every layer (this project's standing
  rollout pattern) — don't wire a layer into CI or the systemd unit until it's been
  proven by hand over SSH first.

---

### Task 1: `nav2_only_launch.py` — three new launch arguments

**Files:**
- Modify: `src/nav_fleet/launch/nav2_only_launch.py`

**Interfaces:**
- Produces: three new `DeclareLaunchArgument`s — `use_sim_time` (default `'true'`),
  `hsv_config` (default `str(PKG / 'config' / 'hsv_gazebo.yaml')`), `map` (default
  `str(PKG / 'maps' / 'living_room.yaml')`) — consumed by Task 3's
  `container_entrypoint.sh` as `ros2 launch ... use_sim_time:=... hsv_config:=...
  map:=...`.

No automated unit test exists for this file, or any launch file in this repo (confirmed
— zero `test_launch*.py` files exist; `ament_index_python`/`launch`/`launch_ros` aren't
importable in `stage-1-quality`, which has no ROS2 installed at all). Verification is
manual, via the Tier-1 dev loop, matching how every other launch-file change in this
project has been verified.

- [ ] **Step 1: Manual baseline — confirm today's unmodified behavior**

  ```bash
  colcon build --symlink-install
  source install/setup.bash
  ros2 launch nav_fleet nav2_only_launch.py
  ```
  Expected: two `Managed nodes are active` lines (localization, then navigation),
  same as always. Ctrl+C to stop. This is the behavior every later step must not
  change by default.

- [ ] **Step 2: Edit the launch file**

  Replace the whole file with:

  ```python
  # Copyright 2026 Mike
  #
  # Licensed under the Apache License, Version 2.0 (the "License");
  # you may not use this file except in compliance with the License.
  # You may obtain a copy of the License at
  #
  #     http://www.apache.org/licenses/LICENSE-2.0
  #
  # Unless required by applicable law or agreed to in writing, software
  # distributed under the License is distributed on an "AS IS" BASIS,
  # WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
  # See the License for the specific language governing permissions and
  # limitations under the License.
  """Nav2 half only: nav2_bringup with this project's map/params, no simulator.

  The 'robot brain' — runs inside the Docker container (docs/superpowers/specs/
  2026-08-03-docker-brain-real-robot-hil-unification-design.md), on the same
  machine as the sim (via sim_launch.py) for local dev, or on the real Jetson for
  both hardware-in-the-loop AND the real robot — the only difference between HIL
  and the real robot is the VALUE of the three launch arguments below, never the
  file.

  start_delay: seconds to wait before starting Nav2. sim_launch.py passes 13.0 (matches
  the original single-file timing: world load + bridge up + first sensor data). Default
  0.0 — an HIL operator starts this manually only after the sim side is confirmed up.
  """
  import os
  import pathlib

  from ament_index_python.packages import get_package_share_directory
  from launch import LaunchDescription
  from launch.actions import (DeclareLaunchArgument, IncludeLaunchDescription,
                              TimerAction)
  from launch.launch_description_sources import PythonLaunchDescriptionSource
  from launch.substitutions import LaunchConfiguration
  from launch_ros.actions import Node

  PKG = pathlib.Path(__file__).parent.parent


  def generate_launch_description():
      start_delay_arg = DeclareLaunchArgument(
          'start_delay', default_value='0.0',
          description='Seconds to wait before Nav2 bringup (sim_launch.py uses 13.0)',
      )
      log_level_arg = DeclareLaunchArgument(
          'log_level', default_value='info',
          description='Passed through to nav2_bringup (e.g. debug, to see per-cycle '
                      'controller_server/goal_checker reasoning during a stall diagnosis)',
      )
      # Docker-brain unification (2026-08-03 design): the ONE difference between HIL
      # and the real robot. Defaults preserve today's HIL behavior exactly, so every
      # existing caller (sim_launch.py, hil_stage.sh) that doesn't pass these three
      # is unaffected.
      use_sim_time_arg = DeclareLaunchArgument(
          'use_sim_time', default_value='true',
          description='true for sim/HIL (Gazebo clock), false for the real robot',
      )
      hsv_config_arg = DeclareLaunchArgument(
          'hsv_config', default_value=str(PKG / 'config' / 'hsv_gazebo.yaml'),
          description='ball_detector HSV thresholds — hsv_gazebo.yaml for sim/HIL, '
                      'hsv_realcam.yaml for the real robot',
      )
      map_arg = DeclareLaunchArgument(
          'map', default_value=str(PKG / 'maps' / 'living_room.yaml'),
          description='Nav2 map yaml — living_room.yaml for sim/HIL, bedroom_real.yaml '
                      'for the real robot',
      )

      # robot_localization EKF — fuses IMU yaw-rate + wheel-odom translation and owns the
      # odom→base_footprint transform (Session 16 Task 9e; see config/ekf.yaml for the
      # measured ~30% wheel-odom rotation over-report this fixes). This lives on the robot
      # side (nav2_only) because odometry fusion belongs on the robot: in HIL it runs on the
      # Jetson while /robot_001/odom, /robot_001/imu/data and RSP's TF arrive over DDS.
      # Started with no delay so it is already publishing odom→base_footprint before Nav2
      # comes up at start_delay; it simply waits for the first odom/imu message.
      # NOT namespaced — per-robot isolation is applied purely via explicit absolute
      # remappings (a namespaced node's params silently fall through to defaults, a
      # documented failure in CLAUDE.md). /tf + /tf_static → /robot_001/*; filtered output
      # → /robot_001/odometry/filtered (what Nav2's odom_topic now points at).
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

      # Mission 2 HSV ball detector — always-on with the nav stack (spec §4): lives on the
      # robot side so HIL runs it on the Jetson while camera frames arrive over DDS.
      # mission_runner simply ignores detections during steps with no reactions.
      ball_detector = Node(
          package='nav_fleet',
          executable='ball_detector',
          name='ball_detector',
          output='screen',
          parameters=[{'use_sim_time': LaunchConfiguration('use_sim_time'),
                       'hsv_config': LaunchConfiguration('hsv_config')}],
      )

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
                  # Forwarded, not previously wired (found in second-round review,
                  # 2026-07-26): bringup_launch.py DOES declare its own 'log_level' arg
                  # and applies it via --ros-args --log-level to the composed container
                  # (see nav2_bringup's own bringup_launch.py) — this repo's log_level
                  # arg just never reached it, so `log_level:=debug` was silently a
                  # no-op even though Piece 9's stall investigation depended on real
                  # DEBUG-level Nav2 logging to do its diagnosis.
                  'log_level': LaunchConfiguration('log_level'),
              }.items(),
          )],
      )

      return LaunchDescription([
          start_delay_arg,
          log_level_arg,
          use_sim_time_arg,
          hsv_config_arg,
          map_arg,
          ekf_node,
          ball_detector,
          nav2,
      ])
  ```

  Note the return list includes `use_sim_time_arg`/`hsv_config_arg`/`map_arg` — this
  project has bitten itself once already (2026-07-26) on a `DeclareLaunchArgument` that
  was constructed but never added to the returned `LaunchDescription`, which only broke
  when this exact file was launched standalone (the one place that happens is
  `hil_stage.sh`'s `nav2_up()` — see `src/nav_fleet/CLAUDE.md`'s Gotchas). Don't repeat it.

- [ ] **Step 3: Verify defaults are unchanged**

  Repeat Step 1's exact command and confirm identical output (two `Managed nodes are
  active` lines, no new errors, no `launch configuration '...' does not exist` errors).

- [ ] **Step 4: Verify overriding the new arguments doesn't break argument parsing**

  ```bash
  ros2 launch nav_fleet nav2_only_launch.py \
    use_sim_time:=false \
    hsv_config:=$(pwd)/src/nav_fleet/config/hsv_gazebo.yaml \
    map:=$(pwd)/src/nav_fleet/maps/living_room.yaml
  ```
  (Using the existing sim files as stand-ins — `hsv_realcam.yaml`/`bedroom_real.yaml`
  don't exist yet; they're created later, for real, when `RealRobotStartup.md` Part A
  actually runs against real hardware.) Expected: the launch file accepts all three
  overrides with no `does not exist`/parsing error. Nav2 may behave oddly with
  `use_sim_time:=false` against a Gazebo clock (not the point of this check) — Ctrl+C
  once you've confirmed it launched without an argument error.

- [ ] **Step 5: Commit**

  ```bash
  git add src/nav_fleet/launch/nav2_only_launch.py
  git commit -m "feat: nav2_only_launch.py takes use_sim_time/hsv_config/map as launch args

  Defaults preserve today's HIL values — no behavior change for any existing
  caller. First step of the docker-brain unification: this file becomes the ONE
  launch file both HIL and the real robot use, parameterized instead of forked."
  ```

---

### Task 2: `nav_fleet/mission_runner.py` — real-robot self-report telemetry

**Files:**
- Modify: `src/nav_fleet/nav_fleet/mission_runner.py`
- Test: `tests/test_mission_run.py` (already ignored in `stage-1-quality`, already run
  live against Gazebo/Nav2 in `stage-2-gazebo` — same treatment every `rclpy`-importing
  test file in this repo gets)

**Interfaces:**
- Produces: `_log_mission2_day_self_report(results)` — takes the same `results` shape
  `MissionRunner.run_mission2_day()` already returns (`list[dict]`, each with at least
  `ok: bool` and `photos: list[str]`), logs one `mission2_<name>` telemetry row per leg
  via `tools.telemetry_logger.log_run`, using ONLY the leg's own self-reported `ok` —
  no ground truth, no `tools.mission2_harness` import (robot code must never import
  that module — its own docstring says so).
- Consumes: `tools.telemetry_logger.log_run(scenario, steps, final_x, final_y, result,
  step_log, db_path=DB_PATH, **metrics)` — already imported in this file.

- [ ] **Step 1: Write the failing test**

  Add to `tests/test_mission_run.py` (top-level function, no `runner`/`ros_context`
  fixture needed — pure-logic test):

  ```python
  def test_log_mission2_day_self_report_logs_one_row_per_leg_from_self_reported_ok(
          monkeypatch):
      """Real-robot-only telemetry (MISSION2_SELF_REPORT=1, container_entrypoint.sh):
      each leg's PASS/FAIL comes from its OWN self-reported 'ok' (Nav2 goal
      completion via the mission's checklist) — no ground truth, no
      tools.mission2_harness import. The real robot has no Gazebo/ground-truth
      oracle at all; a human's own eyes are the accepted judge, after the fact."""
      logged = []
      monkeypatch.setattr(mission_runner_module, 'log_run',
                          lambda **kw: logged.append(kw))
      monkeypatch.setenv('RUNNER_TYPE', 'real_robot')
      monkeypatch.setenv('POWER_MODE', '25W')

      results = [
          {'ok': True, 'photos': ['/home/mike/fleet-ci-data/photos/a.png']},
          {'ok': False, 'photos': []},
          {'ok': True, 'photos': ['/home/mike/fleet-ci-data/photos/b.png']},
      ]
      mission_runner_module._log_mission2_day_self_report(results)

      assert [row['scenario'] for row in logged] == [
          'mission2_no_ball', 'mission2_yellow', 'mission2_red']
      assert [row['result'] for row in logged] == ['PASS', 'FAIL', 'PASS']
      assert logged[0]['photos'] == '["/home/mike/fleet-ci-data/photos/a.png"]'
      assert logged[1]['photos'] is None
      assert logged[0]['runner_type'] == 'real_robot'
      assert logged[0]['sim_engine'] == 'real'
      assert logged[0]['power_mode'] == '25W'
  ```

- [ ] **Step 2: Run test to verify it fails**

  ```bash
  source /opt/ros/jazzy/setup.bash
  source install/setup.bash
  python -m pytest tests/test_mission_run.py::test_log_mission2_day_self_report_logs_one_row_per_leg_from_self_reported_ok -v
  ```
  Expected: FAIL with `AttributeError: module '...mission_runner' has no attribute
  '_log_mission2_day_self_report'`.

- [ ] **Step 3: Write the implementation**

  In `src/nav_fleet/nav_fleet/mission_runner.py`:

  Add `import json` to the top-of-file imports (currently `argparse, math, os,
  pathlib, time, traceback` — no `json` yet).

  Add, right after the `PHOTO_DIR`/`NAV_TIMEOUT_S`/`CLEAR_COSTMAP_SERVICES` module
  constants (before `class MissionRunner`):

  ```python
  # Mirrors tools.mission2_day.hil_variant_names()'s declared order
  # (config/pipeline_matrix.yaml) — duplicated here, not imported, because this file
  # is ROBOT code and must never import tools.mission2_day (which pulls in
  # tools.mission2_harness — ball positions/judge logic robot code must never see).
  MISSION2_DAY_LEG_NAMES = ('no_ball', 'yellow', 'red')


  def _log_mission2_day_self_report(results):
      """Real-robot-only telemetry (MISSION2_SELF_REPORT=1, set by
      scripts/container_entrypoint.sh's caller for the real-robot context only —
      never for HIL): log each leg's SELF-reported PASS/FAIL (leg['ok'], from Nav2's
      own goal completion) with NO ground-truth judging. The real robot has no
      Gazebo, no ground-truth oracle at all (RealRobotStartup.md: a human's own eyes
      are the accepted substitute, and analysis of the resulting logs/photos happens
      after, not in real time). HIL never sets MISSION2_SELF_REPORT — its judged
      verdict comes from the workstation's own ground-truth check instead
      (tools.mission2_day, which stays workstation-side precisely because it needs
      Gazebo)."""
      for name, leg in zip(MISSION2_DAY_LEG_NAMES, results):
          log_run(
              scenario=f'mission2_{name}',
              steps=1,
              final_x=0.0, final_y=0.0,
              result='PASS' if leg['ok'] else 'FAIL',
              step_log=[],
              robot_id=os.environ.get('ROBOT_ID', 'robot_001'),
              robot_type='jetson_ugv_pt',
              runner_type=os.environ.get('RUNNER_TYPE', 'real_robot'),
              sim_engine='real',
              nav_success_rate=1.0 if leg['ok'] else 0.0,
              power_mode=os.environ.get('POWER_MODE'),
              photos=json.dumps(leg['photos']) if leg['photos'] else None,
          )
  ```

  In `main()`'s `--day` branch, right after `print('MISSION2_DAY_RESULT:' +
  json.dumps(results))`, add:

  ```python
          if os.environ.get('MISSION2_SELF_REPORT') == '1':
              _log_mission2_day_self_report(results)
  ```

- [ ] **Step 4: Run test to verify it passes**

  ```bash
  python -m pytest tests/test_mission_run.py::test_log_mission2_day_self_report_logs_one_row_per_leg_from_self_reported_ok -v
  ```
  Expected: PASS.

- [ ] **Step 5: Run the full live-ROS integration file to confirm no regression**

  ```bash
  ros2 launch src/nav_fleet/launch/sim_launch.py &
  sleep 20
  python -m pytest tests/test_navigation.py tests/test_mission_run.py tests/test_nav_runner.py -v --timeout=300
  ```
  (Order matters — see `CLAUDE.md`'s test-ordering Gotcha.) Expected: all PASS,
  same as before this change.

- [ ] **Step 6: Commit**

  ```bash
  git add src/nav_fleet/nav_fleet/mission_runner.py tests/test_mission_run.py
  git commit -m "feat: mission_runner --day can self-report telemetry (no ground truth)

  MISSION2_SELF_REPORT=1 logs each leg's own PASS/FAIL directly — for the real
  robot, which has no Gazebo/ground-truth oracle to judge against. HIL is
  unaffected (never sets this env var; its judged verdict still comes from the
  workstation-side harness)."
  ```

---

### Task 3: Dockerfile + `scripts/container_entrypoint.sh`

**Files:**
- Modify: `Dockerfile`
- Create: `scripts/container_entrypoint.sh`

**Interfaces:**
- Produces: one executable script, `scripts/container_entrypoint.sh`, invoked as
  `docker run ... <image> bash /ros2_ws/scripts/container_entrypoint.sh` by both
  Task 5 (`JetsonExecutor`, HIL) and Task 6 (`robot_boot.sh`, real robot) —
  identical invocation, differing only in the env vars the caller sets:
  `USE_SIM_TIME`, `HSV_CONFIG_FILE`, `NAV2_MAP_FILE` (required), `MISSION2_SELF_REPORT`
  (optional, real-robot only), `RUNNER_TYPE`/`POWER_MODE` (passed through, unchanged
  convention).

No automated test — this is a shell script whose only real test is "does it bring up
Nav2 inside a container and run a mission," which needs live Docker + ROS2 + (for HIL)
a live Gazebo peer. Verified manually in Task 8's checkpoints, matching how
`scripts/hil_stage.sh`/`scripts/robot_boot.sh` have never had unit tests either.

- [ ] **Step 1: Create `scripts/container_entrypoint.sh`**

  ```bash
  #!/bin/bash
  # Copyright 2026 Mike
  # SPDX-License-Identifier: Apache-2.0
  #
  # Unified "brain" entrypoint (docs/superpowers/specs/2026-08-03-docker-brain-
  # real-robot-hil-unification-design.md) — the ONE thing this container does,
  # identically whether it's HIL (workstation Gazebo simulates the robot's body)
  # or the real robot (vendor drivers on bare metal ARE the body): launch
  # nav2_only_launch.py (EKF + ball_detector + Nav2 bringup) with context-
  # appropriate launch arguments, wait for it to report ready, run one mission2
  # day, exit. One-shot — no long-lived container, no docker exec.
  #
  # Env vars the CALLER (tools/mission2_day.py's JetsonExecutor for HIL,
  # scripts/robot_boot.sh for the real robot) must set via `docker run -e`:
  #   USE_SIM_TIME       'true' (HIL) or 'false' (real robot)
  #   HSV_CONFIG_FILE    filename under src/nav_fleet/config/
  #                      (hsv_gazebo.yaml or hsv_realcam.yaml)
  #   NAV2_MAP_FILE      filename under src/nav_fleet/maps/
  #                      (living_room.yaml or bedroom_real.yaml)
  # Optional:
  #   MISSION2_SELF_REPORT=1   real-robot only — mission_runner.py --day logs its
  #                            own self-reported PASS/FAIL per leg (no ground
  #                            truth, no judging — that harness never runs in this
  #                            container). HIL must NOT set this: the
  #                            workstation's JetsonExecutor judges from the
  #                            printed MISSION2_DAY_RESULT line instead.
  #   RUNNER_TYPE, POWER_MODE  passed through to telemetry (unchanged convention)
  #
  # Must be run with `docker run --network host --ipc host` — shares the host's
  # network namespace, which is what lets regen_cyclonedds_config.sh see the
  # SAME real interfaces the host sees, and what lets Nav2 talk DDS to whatever
  # peer this context needs (the workstation's Gazebo bridge for HIL, or nothing
  # external at all for the real robot).
  set -euo pipefail

  source /opt/ros/jazzy/setup.bash
  source /ros2_ws/install/setup.bash
  export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
  export ROS_DOMAIN_ID=0

  # Fixed, non-$HOME path (the design's DDS-fix gap): a container's default $HOME
  # is /root, not /home/mike — pinning this explicitly means the regenerated
  # config always lands somewhere predictable regardless of which user the image
  # runs as, and regen_cyclonedds_config.sh already supports this override
  # (CYCLONEDDS_CONFIG_PATH env var).
  export CYCLONEDDS_CONFIG_PATH=/ros2_ws/cyclonedds-container.xml
  export CYCLONEDDS_URI="file://${CYCLONEDDS_CONFIG_PATH}"
  bash /ros2_ws/scripts/regen_cyclonedds_config.sh

  mkdir -p /ros2_ws/reports
  NAV2_LOG="/ros2_ws/reports/nav2_container_$(date +%Y%m%dT%H%M%S).log"
  rm -f "$NAV2_LOG"
  # Same (subshell) + < /dev/null pattern hil_stage.sh's nav2_up()/robot_boot.sh
  # both already use and document: without the parens the backgrounded job
  # inherits this script's own stdout/stderr and holds the shell open forever;
  # < /dev/null stops it inheriting stdin.
  (nohup ros2 launch nav_fleet nav2_only_launch.py \
     use_sim_time:="${USE_SIM_TIME}" \
     hsv_config:="/ros2_ws/src/nav_fleet/config/${HSV_CONFIG_FILE}" \
     map:="/ros2_ws/src/nav_fleet/maps/${NAV2_MAP_FILE}" \
     > "$NAV2_LOG" 2>&1 < /dev/null &)

  echo "=== [container-entrypoint] waiting up to 120s for Nav2 to report active ==="
  deadline=$((SECONDS + 120))
  count=0
  until [ "$count" -ge 2 ]; do
    if (( SECONDS >= deadline )); then
      echo "FATAL: Nav2 not active within 120s — see $NAV2_LOG" >&2
      tail -n 40 "$NAV2_LOG" >&2 || true
      exit 1
    fi
    sleep 3
    count=$(grep -c 'Managed nodes are active' "$NAV2_LOG" 2>/dev/null || echo 0)
  done
  echo "=== [container-entrypoint] Nav2 active — starting mission2 day ==="

  python3 -m nav_fleet.mission_runner --day
  ```

- [ ] **Step 2: `chmod +x` and verify shell syntax**

  ```bash
  chmod +x scripts/container_entrypoint.sh
  bash -n scripts/container_entrypoint.sh   # syntax check only, no execution
  ```
  Expected: no output (clean syntax).

- [ ] **Step 3: Edit the Dockerfile**

  Replace the whole file with:

  ```dockerfile
  # arm64 ROS2 Jazzy nav_fleet build — built natively on the Jetson runner (stage-3-arm64).
  # THE brain: EKF + ball_detector + Nav2 bringup + mission_runner, run identically by
  # HIL (tools/mission2_day.py's JetsonExecutor) and the real robot
  # (scripts/robot_boot.sh) via scripts/container_entrypoint.sh — see
  # docs/superpowers/specs/2026-08-03-docker-brain-real-robot-hil-unification-design.md.
  FROM ros:jazzy-ros-base

  SHELL ["/bin/bash", "-c"]

  # System deps. ros-jazzy-robot-localization added 2026-08 (docker-brain unification):
  # EKF now runs inside this image — previously only ever installed on bare hosts.
  RUN apt-get update && apt-get install -y \
      python3-pip \
      ros-jazzy-navigation2 \
      ros-jazzy-nav2-bringup \
      ros-jazzy-rmw-cyclonedds-cpp \
      ros-jazzy-vision-msgs \
      ros-jazzy-robot-localization \
      && rm -rf /var/lib/apt/lists/*

  # Python deps (CI-safe subset — not the full venv pip freeze)
  COPY requirements-ci.txt /tmp/requirements-ci.txt
  RUN pip3 install --no-cache-dir --break-system-packages --ignore-installed -r /tmp/requirements-ci.txt

  # DDS
  ENV RMW_IMPLEMENTATION=rmw_cyclonedds_cpp

  # Copy workspace source
  WORKDIR /ros2_ws
  COPY src/ src/

  # tools/ is imported by nav_fleet.mission_runner (telemetry_logger) — required to run
  # the mission executor inside this image.
  COPY tools/ tools/

  # Entrypoint + the DDS-interface-regeneration script it calls — same script every bare
  # process (hil_stage.sh, robot_boot.sh) already uses, so the container gets the exact
  # same interface-selection behavior.
  COPY scripts/container_entrypoint.sh scripts/regen_cyclonedds_config.sh scripts/
  RUN chmod +x scripts/container_entrypoint.sh scripts/regen_cyclonedds_config.sh

  # Build colcon package.
  # NOT --symlink-install here (unlike the Tier-1 x86/Jetson dev loop): symlink-install's
  # nav_fleet PYTHONPATH hook (pythonpath_develop.sh) lives under build/, which the next
  # `rm -rf build/` deletes — leaving `source install/setup.bash` unable to put nav_fleet on
  # PYTHONPATH inside the image. A plain install copies the package into install/ so
  # build/ is safe to drop.
  RUN source /opt/ros/jazzy/setup.bash && \
      colcon build \
      && rm -rf build/ log/

  # Source on container start
  RUN echo "source /opt/ros/jazzy/setup.bash" >> /root/.bashrc && \
      echo "source /ros2_ws/install/setup.bash" >> /root/.bashrc

  CMD ["/bin/bash"]
  ```

- [ ] **Step 4: Build the image locally to confirm it builds clean**

  On the Jetson runner (arm64 — cross-building x86→arm64 works via buildx/QEMU but is
  much slower; prefer running this directly on the Jetson):
  ```bash
  docker buildx build --platform linux/arm64 \
    --tag docker-brain-test:local --load .
  ```
  Expected: build completes with no error. This does NOT yet prove the entrypoint
  script works end-to-end (Task 8 does that) — it only proves the image builds with
  the new package + copied scripts.

- [ ] **Step 5: Spot-check the new package installed**

  ```bash
  docker run --rm docker-brain-test:local bash -c \
    "source /opt/ros/jazzy/setup.bash && ros2 pkg list | grep robot_localization"
  ```
  Expected: `robot_localization` printed.

- [ ] **Step 6: Commit**

  ```bash
  git add Dockerfile scripts/container_entrypoint.sh
  git commit -m "feat: container image gains EKF + a unified brain entrypoint

  ros-jazzy-robot-localization added (EKF now runs in-container). New
  scripts/container_entrypoint.sh is the one script both HIL and the real robot
  use to launch Nav2 (context-driven launch args) and run mission_runner --day.
  Not yet wired into any caller — that's Tasks 5/6."
  ```

---

### Task 4: `config/pipeline_matrix.yaml` — real-robot scenarios follow the mission2 day

**Files:**
- Modify: `config/pipeline_matrix.yaml`

**Interfaces:**
- Produces: `real.scenarios` now matches what the real robot actually logs (Task 2's
  `mission2_no_ball`/`mission2_yellow`/`mission2_red`, self-reported) — consumed by
  `tools/fleet_status.py --stage real` (referenced in `RealRobotStartup.md` A7) and
  `tools/generate_test_report.py --stage real`.

No test exists for this file's content today (it's read directly by `load_stage()`,
covered indirectly by whatever consumes it). Verified by inspection + Step 2 below.

- [ ] **Step 1: Edit the file**

  Change:
  ```yaml
  real:
    runner_type: real_robot
    scenarios: [bedroom_nav]
  ```
  to:
  ```yaml
  # Real robot (RealRobotStartup.md). Changed 2026-08 (docker-brain unification):
  # RealRobotStartup.md's 2026-08-01 rewrite already moved the real-robot validation
  # target from BR-01/bedroom_nav to the mission2 day (no_ball -> yellow -> red,
  # self-reported per Task 2 above, no ground-truth judging) — this list was never
  # updated to match at the time. Fixed now: tools.fleet_status --stage real and
  # tools.generate_test_report --stage real both read this list directly, and would
  # otherwise silently look for rows that stopped being logged.
  real:
    runner_type: real_robot
    scenarios: [mission2_no_ball, mission2_yellow, mission2_red]
  ```

- [ ] **Step 2: Confirm `load_stage` reads it correctly**

  ```bash
  python -c "from tools.pipeline_matrix import load_stage; print(load_stage('real'))"
  ```
  Expected: `('real_robot', ['mission2_no_ball', 'mission2_yellow', 'mission2_red'])`
  (or the equivalent tuple/list shape this function returns — confirm against
  `tools/pipeline_matrix.py`'s actual return type if this doesn't match).

- [ ] **Step 3: Commit**

  ```bash
  git add config/pipeline_matrix.yaml
  git commit -m "fix: real-stage scenarios match the mission2 day, not stale BR-01

  RealRobotStartup.md moved the real-robot validation target to the mission2 day
  on 2026-08-01; this file's scenario list was never updated to match, so
  fleet_status/generate_test_report --stage real would have found nothing."
  ```

---

### Task 5: `tools/mission2_day.py` + `scripts/hil_stage.sh` — always-container HIL

**Files:**
- Modify: `tools/mission2_day.py`
- Modify: `scripts/hil_stage.sh`
- Modify: `tests/test_mission2_day.py`

**Interfaces:**
- Changes: `JetsonExecutor` no longer branches on `HIL_CONTAINER` — container mode is
  the only mode. `JetsonExecutor.run_day()` now dispatches
  `bash /ros2_ws/scripts/container_entrypoint.sh` (Task 3) instead of building a
  `mission_runner --day` command directly, with `-e USE_SIM_TIME=true -e
  HSV_CONFIG_FILE=hsv_gazebo.yaml -e NAV2_MAP_FILE=living_room.yaml` (HIL's context
  values) plus the CycloneDDS-URI/bind-mount gap the design closes.
  `JetsonExecutor._remote_photo_path()` always does the container-path translation
  (the bare-metal branch is dead now). `hil_stage.sh`'s `run()` drops its `nav2_up()`
  call (Nav2 now starts as part of the container's own one-shot day run, triggered by
  `day()`); `nav2_up()` itself is deleted (no remaining caller); `sync()` drops its
  `colcon build` step (nothing bare launches `nav_fleet` code on the Jetson anymore —
  only the checkout needs to exist there, per the Global Constraints).

This task's tests are pure Python (subprocess/SSH calls are already monkeypatched
throughout the existing test file — no live hardware needed to run them).

- [ ] **Step 1: Update the existing tests to the new (always-container) contract — RED first**

  In `tests/test_mission2_day.py`:

  Delete these three tests (they test the bare-metal branch, which is being removed):
  `test_jetson_executor_bare_metal_skips_image_preflight`,
  `test_run_day_bare_metal_dispatches_ssh_with_day_flag`,
  `test_pull_photos_bare_metal_uses_absolute_path_verbatim`.

  Replace `test_jetson_executor_container_mode_passes_when_image_present` and
  `test_jetson_executor_container_mode_fails_loud_when_image_missing` (currently gated
  behind `monkeypatch.setenv('HIL_CONTAINER', '1')`, which no longer exists) with:

  ```python
  def test_jetson_executor_requires_hil_image(monkeypatch):
      """HIL_IMAGE is required now — container mode is the only mode."""
      monkeypatch.delenv('HIL_IMAGE', raising=False)
      with pytest.raises(KeyError):
          JetsonExecutor('10.42.0.217', '/tmp/hil_stage')


  def test_jetson_executor_passes_preflight_when_image_present(monkeypatch):
      monkeypatch.setenv('HIL_IMAGE', 'ghcr.io/sdfinn/autonomous-fleet-testbed:deadbeef')
      monkeypatch.setattr(
          subprocess, 'run',
          lambda *a, **k: subprocess.CompletedProcess(a, returncode=0, stdout='', stderr=''))

      ex = JetsonExecutor('10.42.0.217', '/tmp/hil_stage')
      assert ex.image == 'ghcr.io/sdfinn/autonomous-fleet-testbed:deadbeef'


  def test_jetson_executor_fails_loud_when_image_missing(monkeypatch):
      monkeypatch.setenv('HIL_IMAGE', 'ghcr.io/sdfinn/autonomous-fleet-testbed:wrongtag')
      monkeypatch.setattr(
          subprocess, 'run',
          lambda *a, **k: subprocess.CompletedProcess(
              a, returncode=1, stdout='', stderr='no such image'))

      with pytest.raises(RuntimeError, match='wrongtag'):
          JetsonExecutor('10.42.0.217', '/tmp/hil_stage')
  ```

  Update `test_run_day_container_mode_uses_plain_docker_run_rm` (drop the
  `HIL_CONTAINER` env var, expect the entrypoint script instead of a direct
  `mission_runner --day` invocation):

  ```python
  def test_run_day_dispatches_the_container_entrypoint(monkeypatch, tmp_path):
      monkeypatch.setenv('HIL_IMAGE', 'ghcr.io/sdfinn/autonomous-fleet-testbed:deadbeef')
      legs = [_leg(), _leg(), _leg()]
      calls = []

      def fake_run(cmd, **kwargs):
          calls.append(cmd)
          if cmd[0] == 'timeout':
              return subprocess.CompletedProcess(cmd, returncode=0,
                                                  stdout=_day_result_stdout(legs), stderr='')
          return subprocess.CompletedProcess(cmd, returncode=0, stdout='', stderr='')

      monkeypatch.setattr(subprocess, 'run', fake_run)
      monkeypatch.setattr(mission2_day_module.JetsonExecutor, '_pull_photos_from_paths',
                          lambda self, paths: list(paths))
      ex = JetsonExecutor('10.42.0.217', str(tmp_path))

      ex.run_day()

      ssh_cmd = next(c for c in calls if 'ssh' in c and 'timeout' in c)
      assert 'docker run --rm' in ssh_cmd[-1]
      assert '--name hil_mission2' in ssh_cmd[-1]
      assert '--network host --ipc host' in ssh_cmd[-1]
      assert 'bash /ros2_ws/scripts/container_entrypoint.sh' in ssh_cmd[-1]
      assert '-e USE_SIM_TIME=true' in ssh_cmd[-1]
      assert '-e HSV_CONFIG_FILE=hsv_gazebo.yaml' in ssh_cmd[-1]
      assert '-e NAV2_MAP_FILE=living_room.yaml' in ssh_cmd[-1]
      assert 'ghcr.io/sdfinn/autonomous-fleet-testbed:deadbeef' in ssh_cmd[-1]
  ```

  Update `test_pull_photos_container_mode_translates_root_prefix_to_tilde` — unchanged
  in spirit but remove the `monkeypatch.setenv('HIL_CONTAINER', '1')` line (no longer
  needed/read).

  Update `test_close_is_a_noop_in_both_modes` — rename to
  `test_close_is_a_noop` and drop the `HIL_CONTAINER` env var line.

  Finally, grep for any other stray references and remove them (harmless but
  misleading once nothing reads this env var — `test_spawn_vlm_canary_on_jetson_
  translates_container_path` has one):
  ```bash
  grep -n "HIL_CONTAINER" tests/test_mission2_day.py
  ```
  Delete each `monkeypatch.setenv('HIL_CONTAINER', '1')`/`monkeypatch.delenv('HIL_
  CONTAINER', raising=False)` line found (leave the rest of each test unchanged).

- [ ] **Step 2: Run the updated tests to verify they fail against the OLD code**

  ```bash
  python -m pytest tests/test_mission2_day.py -v -k "jetson_executor or run_day_dispatches or pull_photos_container or close_is_a_noop"
  ```
  Expected: failures — `JetsonExecutor.__init__` still requires `HIL_CONTAINER=1` to
  read `HIL_IMAGE` at all, and `run_day()` still builds the old `mission_runner --day`
  command shape.

- [ ] **Step 3: Update `JetsonExecutor` in `tools/mission2_day.py`**

  Replace `__init__`:

  ```python
      def __init__(self, jetson_ip, state_dir):
          if not jetson_ip:
              raise RuntimeError('JetsonExecutor needs JETSON_IP (run: hil_stage.sh discover)')
          self.ip = jetson_ip
          self.state_dir = state_dir
          # Container mode is the ONLY mode (docker-brain unification, 2026-08) — Nav2/
          # EKF/ball_detector/mission_runner all run inside the image now; nothing bare
          # launches nav_fleet code on the Jetson any more. KeyError on a missing
          # HIL_IMAGE is a real misconfiguration — surface it, don't default silently.
          self.image = os.environ['HIL_IMAGE']
          self._require_image_local()
  ```

  Replace `run_day()`'s command-building (keep everything else — timeout, logging,
  `_log_startup_crash_if_needed`, `_pull_failure_bags`, `_parse_day_result`, the
  per-leg loop — unchanged):

  ```python
      def run_day(self):
          cmd = (
              "docker run --rm --name hil_mission2 --network host --ipc host "
              "-v $HOME/autonomous-fleet-testbed/reports:/ros2_ws/reports "
              "-v $HOME/fleet-ci-data:/root/fleet-ci-data "
              "-e USE_SIM_TIME=true -e HSV_CONFIG_FILE=hsv_gazebo.yaml "
              "-e NAV2_MAP_FILE=living_room.yaml "
              f"-e RUNNER_TYPE=hil_jetson -e POWER_MODE={POWER_MODE_LABEL} "
              f"{self.image} bash /ros2_ws/scripts/container_entrypoint.sh")
          out_path = os.path.join(self.state_dir, 'day.out')
          dispatch_time = time.time()
          log.info(f'[timing] ssh dispatch for the day at {dispatch_time:.3f}')
          # 1080s (18 min): comfortable headroom over Nav2 bring-up (up to 120s, now
          # INSIDE this one call, see container_entrypoint.sh) + worst-case real leg
          # work + cold-start retry backoff, while leaving a 2-min safety margin under
          # CI's 1200s outer timeout — the inner timeout must fire FIRST so the normal
          # teardown/evidence-upload steps can still run via `if: always()`.
          proc = subprocess.run(
              ['timeout', '1080', 'ssh', '-o', 'BatchMode=yes',
               '-o', 'StrictHostKeyChecking=accept-new',
               f'{JETSON_USER}@{self.ip}', cmd],
              capture_output=True, text=True)
          log.info(f'[timing] ssh returned for the day at {time.time():.3f} '
                   f'(+{time.time() - dispatch_time:.3f}s total)')
          log_text = proc.stdout + proc.stderr
          pathlib.Path(out_path).write_text(log_text)
          log.debug(log_text.rstrip())
          self._log_startup_crash_if_needed(log_text, proc.returncode)
          self._pull_failure_bags(log_text)
          results = self._parse_day_result(log_text)
          for leg in results:
              self._spawn_vlm_canary_on_jetson(leg)
              leg['photos'] = self._pull_photos_from_paths(leg['photos'])
          return results
  ```

  Replace `_remote_photo_path()` (the bare-metal branch is dead — container mode is
  always on now):

  ```python
      def _remote_photo_path(self, rel):
          """`rel` (from a 'photo saved: <path>' log line) is a path INSIDE the
          container (root's HOME, e.g. '/root/fleet-ci-data/...'), which the
          container-run bind mount (-v $HOME/fleet-ci-data:/root/fleet-ci-data) maps
          onto JETSON_USER's real fleet-ci-data dir on the host — substitute the
          container's root prefix for '~' so the remote shell expands it to
          JETSON_USER's actual home."""
          return '~' + rel[len('/root'):]
  ```

  Delete `_require_image_local`'s docstring reference to "a bare local invocation" if
  present (spot-check — the method itself is unchanged, still SSHes a `docker image
  inspect` preflight, unconditionally now rather than only when `self.image is not
  None`).

- [ ] **Step 4: Run the updated tests to verify they pass**

  ```bash
  python -m pytest tests/test_mission2_day.py -v
  ```
  Expected: all PASS (the whole file, not just the touched tests — confirm no other
  test in this file assumed `HIL_CONTAINER` unset/bare mode).

- [ ] **Step 5: Update `scripts/hil_stage.sh`**

  In `sync()`, remove the bare `colcon build` line — nothing bare launches
  `nav_fleet` code on the Jetson anymore, so the checkout only needs to exist there
  (for `regen_cyclonedds_config.sh`'s own presence and for identifying which image to
  run):

  ```bash
  sync() {
    require_ip
    local sha="${1:?usage: hil_stage.sh sync <git-sha>}"
    jssh "cd ${JETSON_REPO} && git fetch origin ${sha} && git checkout --detach FETCH_HEAD"
    # No bare colcon build any more (docker-brain unification, 2026-08) — nothing
    # bare launches nav_fleet code on the Jetson; the checkout only needs to exist
    # here for regen_cyclonedds_config.sh and to identify the tested commit.
  }
  ```

  In `run()`, drop the `nav2_up()` call — Nav2 now starts as part of the container's
  own one-shot day run (triggered by `day()`, via `container_entrypoint.sh`):

  ```bash
  run() {
    # HIL stack GATE (Task 13b, narrowed 2026-08 for the docker-brain unification):
    # clean state, bring up ONLY the workstation's Gazebo half — Nav2/EKF/
    # ball_detector now start INSIDE the container as part of `day()`'s one-shot
    # run (see container_entrypoint.sh), not as a separate bare pre-step.
    clean_state
    sim_up
  }
  ```

  Delete the `nav2_up()` function entirely (no remaining caller — confirm with
  `grep -n nav2_up scripts/hil_stage.sh` before deleting, to be sure).

- [ ] **Step 6: Manually verify `hil_stage.sh`'s shell syntax**

  ```bash
  bash -n scripts/hil_stage.sh
  ```
  Expected: no output.

- [ ] **Step 7: Commit**

  ```bash
  git add tools/mission2_day.py tests/test_mission2_day.py scripts/hil_stage.sh
  git commit -m "feat: HIL always runs the brain in-container, via one entrypoint

  JetsonExecutor no longer has a bare-metal branch — HIL_IMAGE is required, and
  run_day() dispatches scripts/container_entrypoint.sh (which now also brings up
  Nav2 itself) instead of building a mission_runner --day command directly.
  hil_stage.sh's run() drops nav2_up() (folded into the container's own one-shot
  day run); sync() drops its bare colcon build (nothing bare launches nav_fleet
  code on the Jetson any more). Ball placement/ground-truth judging are
  unaffected — still workstation-side, unchanged."
  ```

---

### Task 6: `scripts/robot_boot.sh` + `scripts/robot-mission.service`

**Files:**
- Modify: `scripts/robot_boot.sh`
- Modify: `scripts/robot-mission.service`

**Interfaces:**
- Changes: `robot_boot.sh` runs the SAME container image via `docker run ... bash
  /ros2_ws/scripts/container_entrypoint.sh` (Task 3) with real-robot-context env vars
  (`USE_SIM_TIME=false`, `HSV_CONFIG_FILE=hsv_realcam.yaml`,
  `NAV2_MAP_FILE=bedroom_real.yaml`, `MISSION2_SELF_REPORT=1`), instead of a bare `ros2
  launch nav_fleet robot_launch.py` + bare `python -m tools.mission2_day --ball-ops
  operator`. No `docker pull` — the image tag is derived from the Jetson's own
  checked-out git sha (already kept in sync by `hil_stage.sh sync <sha>`, per the
  Global Constraints' "no tag scheme, whatever's cached locally" decision), with a
  loud preflight check (mirroring `JetsonExecutor._require_image_local`'s pattern) if
  that exact tag isn't already present.

No automated test — same reasoning as Task 3 (a boot script needs a real power cycle
or at minimum a real Jetson+Docker to mean anything). Verified manually in Task 8.

- [ ] **Step 1: Rewrite `scripts/robot_boot.sh`**

  ```bash
  #!/bin/bash
  # Copyright 2026 Mike
  # SPDX-License-Identifier: Apache-2.0
  #
  # Boot-time entry point for the real, deployed Waveshare UGV-PT (RealRobotStartup.md
  # Part A). Runs the SAME container image and the SAME entrypoint script HIL uses
  # (scripts/container_entrypoint.sh) — only the launch-argument VALUES differ
  # (real-robot context: use_sim_time=false, the real-camera HSV profile, the real
  # room's map) — see docs/superpowers/specs/
  # 2026-08-03-docker-brain-real-robot-hil-unification-design.md.
  #
  # No `docker pull`, no tag-selection scheme: whatever image is already sitting in
  # this Jetson's local `docker images` cache is the image that runs — the one
  # `scripts/hil_stage.sh sync <sha>` last checked out here, which is the SAME sha
  # that image is tagged with (stage-3-arm64 tags every build with the commit sha).
  # Get the exact HIL-tested commit onto this checkout BEFORE relying on this script
  # (see RealRobotStartup.md Part A) — this script always runs whatever is currently
  # checked out here, same as it always has.
  #
  # NOT yet exercised by CI/HIL — a power cycle can't be simulated there. Run this
  # manually over SSH first and confirm a full mission2 day passes with your own eyes-on
  # check before trusting the systemd unit (scripts/robot-mission.service) that calls it
  # automatically at boot.
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

  echo "=== [robot-boot] running ${IMAGE} (real-robot context, operator ball placement) ==="
  # RUNNER_TYPE=real_robot matches the convention every other real-robot telemetry row
  # in this project already uses. MISSION2_SELF_REPORT=1: no ground-truth judging (no
  # Gazebo on the real robot) — mission_runner logs each leg's own self-reported
  # PASS/FAIL instead; analysis of the resulting logs/photos happens after, manually.
  docker run --rm --name robot_mission --network host --ipc host \
    -v "$REPO/reports:/ros2_ws/reports" \
    -v "$HOME/fleet-ci-data:/root/fleet-ci-data" \
    -e USE_SIM_TIME=false \
    -e HSV_CONFIG_FILE=hsv_realcam.yaml \
    -e NAV2_MAP_FILE=bedroom_real.yaml \
    -e MISSION2_SELF_REPORT=1 \
    -e RUNNER_TYPE=real_robot \
    "$IMAGE" bash /ros2_ws/scripts/container_entrypoint.sh \
    2>&1 | tee "$LOG_DIR/robot_boot_${TS}.log"
  ```

- [ ] **Step 2: Verify shell syntax**

  ```bash
  bash -n scripts/robot_boot.sh
  ```
  Expected: no output.

- [ ] **Step 3: Update `scripts/robot-mission.service`**

  Add `Requires=docker.service`/`After=docker.service` alongside the existing
  `network-online.target` wait:

  ```ini
  [Unit]
  Description=Real-robot mission2 day (no_ball -> yellow -> red), operator ball placement
  After=network-online.target docker.service
  Wants=network-online.target
  Requires=docker.service
  ```
  (Rest of the file — `[Service]`/`[Install]` sections — unchanged.)

- [ ] **Step 4: Commit**

  ```bash
  git add scripts/robot_boot.sh scripts/robot-mission.service
  git commit -m "feat: real robot runs the same container image HIL uses

  robot_boot.sh now docker-runs container_entrypoint.sh with real-robot-context
  launch args (use_sim_time=false, hsv_realcam.yaml, bedroom_real.yaml,
  MISSION2_SELF_REPORT=1) instead of a bare ros2 launch + bare mission2_day.py.
  No pull, no tag scheme — runs whatever image is already local, tagged with
  this checkout's own git sha. robot-mission.service now waits on docker.service
  too. NOT yet exercised against real hardware — see Task 8's manual checkpoints."
  ```

---

### Task 7: `.github/workflows/ci.yml` — drop the now-unused `HIL_CONTAINER` switch

**Files:**
- Modify: `.github/workflows/ci.yml`

**Interfaces:** none (env-var cleanup only — `JetsonExecutor` no longer reads
`HIL_CONTAINER` at all after Task 5).

- [ ] **Step 1: Remove the `HIL_CONTAINER: "1"` line from `stage-4-hil`'s `env:` block**

  In the `stage-4-hil` job's `env:` section, delete:
  ```yaml
        HIL_CONTAINER: "1"
  ```
  and its preceding comment (`# phase 2 (Task 12): the day orchestrator runs
  mission2 inside the arm64 image...`) — container mode is the only mode now, so this
  env var is dead. Leave `HIL_IMAGE: ghcr.io/${{ github.repository }}:${{ github.sha
  }}` in place — still required (Task 5's `JetsonExecutor.__init__` reads it
  unconditionally).

- [ ] **Step 2: Confirm the YAML still parses**

  ```bash
  python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"
  ```
  Expected: no error. (Use Edit, not a raw Python read/write round-trip, to preserve
  this file's CRLF line endings — see `CLAUDE.md`'s Gotcha on this exact file.)

- [ ] **Step 3: Commit**

  ```bash
  git add .github/workflows/ci.yml
  git commit -m "chore: drop the now-unused HIL_CONTAINER env var from stage-4-hil

  JetsonExecutor no longer branches on it (Task 5) — container mode is the only
  mode. HIL_IMAGE stays; still required."
  ```

---

### Task 8: `RealRobotStartup.md` — update A5/A6 for the docker-brain design

**Files:**
- Modify: `RealRobotStartup.md`

- [ ] **Step 1: Replace section A5**

  Replace the entire "### A5. Create `src/nav_fleet/launch/robot_launch.py`" section
  (including its code block) with:

  ```markdown
  ### A5. No new launch file needed

  Superseded 2026-08 by the docker-brain unification (docs/superpowers/specs/
  2026-08-03-docker-brain-real-robot-hil-unification-design.md): `robot_launch.py` is
  never created. `src/nav_fleet/launch/nav2_only_launch.py` — the same file HIL already
  uses — is reused directly, parameterized by three launch arguments
  (`use_sim_time:=false hsv_config:=.../hsv_realcam.yaml map:=.../bedroom_real.yaml`),
  passed in by `scripts/container_entrypoint.sh` (see A6). Nothing to write here.
  ```

- [ ] **Step 2: Replace section A6**

  Replace the entire "### A6. Build the power-on boot sequence" section with:

  ```markdown
  ### A6. Build the power-on boot sequence

  `scripts/robot_boot.sh`, `scripts/robot-mission.service`, and
  `scripts/container_entrypoint.sh` already exist in the repo — nothing to write here,
  just install and verify:

  - [ ] Get the exact HIL-tested commit onto this checkout (from the workstation):
    ```bash
    scripts/hil_stage.sh sync <the green run's commit sha>
    ```
    This ALSO determines which container image `robot_boot.sh` runs — it derives the
    image tag from this checkout's own `git rev-parse HEAD`, and stage-3-arm64 tags
    every build with its commit sha. No `docker pull` ever happens here: the image
    must already be cached locally from when `stage-4-hil` pulled it for this exact
    commit during CI. `robot_boot.sh` checks this and fails loudly (naming the
    missing tag) rather than trying to fetch it.
  - [ ] Run `scripts/robot_boot.sh` **manually over SSH** first — don't install the
    systemd unit yet. Watch it: image-present check → container starts → DDS regen →
    Nav2/EKF/`ball_detector` come up (inside the container) → "Managed nodes are
    active" ×2 → `mission_runner --day` starts, self-reporting each leg's PASS/FAIL
    (no ground-truth judging — the real robot has none). Place the red ball, then the
    yellow ball, at the right moments (see A7) and confirm the whole day runs to
    completion.
  - [ ] Only once that manual run has actually passed: install the systemd unit so
    power-on triggers it automatically.
    ```bash
    sudo cp scripts/robot-mission.service /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable robot-mission.service
    ```
    This is genuinely new — nothing in CI/HIL exercises a power cycle, so there's no
    automated proof this works, only the manual run above. Treat the manual invocation
    as the real test; the systemd unit is convenience wired on top of something already
    proven to work by hand.
  ```

- [ ] **Step 3: Update the doc's own intro (item 2) to reflect the reversal**

  Replace:
  ```markdown
  2. **Nav2/EKF/`ball_detector` run bare-metal, not containerized.** See
     `docs/bare-metal-vs-container-decision.md` for the full story — short version: the
     container role HIL actually proved was always narrower (just the raw mission loop,
     never Nav2 itself), and running Nav2 in a container was never the thing that got
     hardened across weeks of real HIL runs.
  ```
  with:
  ```markdown
  2. **Nav2/EKF/`ball_detector`/`mission_runner` run INSIDE the container** (reversed
     2026-08-03 — see `docs/superpowers/specs/
     2026-08-03-docker-brain-real-robot-hil-unification-design.md`, which supersedes
     `docs/bare-metal-vs-container-decision.md`'s conclusion). Ball placement and
     ground-truth judging stay workstation-side for HIL (that harness never runs on the
     real robot either way); the real robot self-reports each leg's PASS/FAIL with no
     ground-truth check at all — analysis of logs/photos happens after, manually.
  ```

- [ ] **Step 4: Commit**

  ```bash
  git add RealRobotStartup.md
  git commit -m "docs: RealRobotStartup.md reflects the docker-brain reversal

  A5 no longer proposes a separate robot_launch.py (nav2_only_launch.py is
  reused via the container). A6 rewritten around robot_boot.sh's new
  docker-run-based flow. Intro item 2 updated — the bare-metal-vs-container
  decision this doc originally cited is now superseded."
  ```

---

### Task 9: Manual verification checkpoints (hardware-gated, before CI/systemd wiring)

Per the design's own rollout order — verify each layer by hand, on real hardware,
before it's trusted by CI or the boot-time systemd unit. None of these steps are
automatable; each has an exact command and exact expected output so it's a clean
pass/fail, not a judgment call, wherever that's possible.

- [ ] **Step 1: Build the image on the Jetson runner itself (not cross-built)**

  ```bash
  ssh mike@jetson.local
  cd ~/autonomous-fleet-testbed
  scripts/hil_stage.sh sync $(git rev-parse HEAD)   # from the workstation, first
  docker buildx build --platform linux/arm64 --tag docker-brain-verify:local --load .
  ```
  Expected: clean build, no error.

- [ ] **Step 2: Manually run the container in real-robot-context args (sim config files as stand-ins)**

  Still on the Jetson (`hsv_realcam.yaml`/`bedroom_real.yaml` don't exist yet — Part A
  hasn't run for real — using the sim files proves the MECHANICS: Nav2 comes up inside
  the container, `mission_runner --day` runs, self-report telemetry lands):

  ```bash
  docker run --rm --name robot_boot_verify --network host --ipc host \
    -v ~/autonomous-fleet-testbed/reports:/ros2_ws/reports \
    -v ~/fleet-ci-data:/root/fleet-ci-data \
    -e USE_SIM_TIME=false \
    -e HSV_CONFIG_FILE=hsv_gazebo.yaml \
    -e NAV2_MAP_FILE=living_room.yaml \
    -e MISSION2_SELF_REPORT=1 \
    -e RUNNER_TYPE=real_robot \
    docker-brain-verify:local bash /ros2_ws/scripts/container_entrypoint.sh
  ```
  Expected: two `Managed nodes are active` lines, then `mission_runner --day` runs
  (no ball placed — `ball_detector` never triggers, all 3 legs just complete their
  no-reaction path). Confirm afterward:
  ```bash
  sqlite3 ~/fleet-ci-data/fleet_runs.db \
    "SELECT scenario, result, runner_type, sim_engine FROM runs ORDER BY id DESC LIMIT 3"
  ```
  Expected: 3 rows, `mission2_no_ball`/`mission2_yellow`/`mission2_red`,
  `runner_type=real_robot`, `sim_engine=real` — proving `MISSION2_SELF_REPORT=1`'s
  telemetry path works end-to-end without any ground-truth dependency.

- [ ] **Step 3: Full HIL day, container-based, before touching CI**

  From the workstation:
  ```bash
  JETSON_IP=$(scripts/hil_stage.sh discover)
  HIL_IMAGE="ghcr.io/sdfinn/autonomous-fleet-testbed:$(git rev-parse HEAD)" \
    scripts/hil_stage.sh run
  HIL_IMAGE="ghcr.io/sdfinn/autonomous-fleet-testbed:$(git rev-parse HEAD)" \
    scripts/hil_stage.sh day
  ```
  (Requires the same-sha image already built/pushed and pulled onto the Jetson once,
  same as any HIL run today — `docker pull` it manually onto the Jetson first if this
  exact sha was never run through CI's own pull step.) Expected: `run` brings up only
  Gazebo on the workstation (no more bare `nav2_up()` step); `day` triggers the
  container (which brings up Nav2 itself, then runs the mission), ball choreography +
  judging happen workstation-side exactly as before, all 3 legs PASS, photos pulled
  back correctly.

- [ ] **Step 4: Only once Steps 1-3 all pass — push and let CI prove it**

  Open a PR (or push to `main`, per this repo's own convention) and confirm
  `stage-4-hil` goes green with the new container-based `JetsonExecutor`. Confirm via
  `gh run list`/the dashboard, not the Actions Summary tab (confirmed platform bug,
  `CLAUDE.md`'s Gotchas).

- [ ] **Step 5: Report back to Mike**

  Bring the real results of Steps 1-4 back before considering this plan complete —
  per this project's standing practice, a live-hardware result gets reported honestly
  (including any failure), not assumed to have passed because the code looks right.
