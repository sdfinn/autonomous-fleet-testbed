# Real Robot Startup

Step-by-step checklist for taking the robot from "arrived" to "running missions and
staying in sync with CI/CD." **Part A is done once.** **Part B is the repeatable loop**
you use every time you power the robot on, or every time new code needs to reach it.

**WiFi assumed available** (Mike has the WiFi card in hand for the Jetson; Session 19's
WiFi bring-up item covers getting it working — this doc assumes that's already done,
so the robot is untethered from Ethernet for everything below except the initial bench
checks).

**Confirmed setup: ONE Jetson, no second CI runner.** The Session 14 Jetson transfers
into the robot permanently — there's no separate dedicated CI runner. This means Part
B3/B4 below require physically pulling the Jetson back out to re-run HIL after any
code change, then reinstalling it — a real, repeated cost, not a one-time thing. Worth
revisiting later if that friction gets painful, but not required for R1.

---

## Part A — One-Time Setup

### A1. Pre-flight, still on the bench (Ethernet, connected to workstation)

- [ ] Confirm CI is green on `main` (`gh run list` or check the dashboard).
- [ ] Confirm the container image tag on the Jetson matches what CI last built and
  tested (`docker images` on the Jetson vs. the latest `stage-3-arm64` run's tag).
- [ ] Check for root-owned residue from prior container-mode HIL runs:
  ```bash
  ls -la ~/fleet-ci-data
  # If anything is root-owned:
  sudo chown -R mike:mike ~/fleet-ci-data
  sudo chmod -R u+rwX,g+rwX ~/fleet-ci-data
  sudo find ~/fleet-ci-data -type d -exec chmod g+s {} \;
  ```
- [ ] (Optional but recommended) Run one more full HIL day as a "last known good"
  checkpoint before touching anything physical: `scripts/hil_stage.sh day`.

### A2. Physical transplant into the Waveshare UGV-PT

- [ ] Follow Waveshare's assembly video/wiki for the physical steps (screws, cable
  routing, Jetson seating) — fill in as you go, this doc can't verify hardware steps
  from a video:
  - [ ] ______________________________________________
  - [ ] ______________________________________________
  - [ ] ______________________________________________
- [ ] Power on. Connect to the robot's WiFi network (or confirm it joins yours).
- [ ] SSH in over WiFi: `ssh mike@<robot-ip>` (find the IP via router admin page or
  `ping jetson.local` if mDNS resolves).
- [ ] Check Jetson health: `nvidia-smi`, temp, `df -h` free space.
- [ ] Evaluate Waveshare's `ugv_ws` ROS2 workspace (github.com/waveshareteam) — it may
  cover the base driver + lidar + camera out of the box. Install/build it.
- [ ] **Verify all four real topics report, before anything else:**
  ```bash
  ros2 topic hz /robot_001/odom
  ros2 topic hz /robot_001/scan
  ros2 topic hz /robot_001/camera/image_raw
  ```
  and confirm `teleop_twist_keyboard`/`teleop_twist_joy` physically drives the wheels.
  (`ball_detector` subscribes to the camera topic and stays silently uninitialized,
  not crashed, if it's missing — check explicitly rather than discovering it later.)
- [ ] Command the pan-tilt gimbal to a fixed forward/level pose (exact mechanism
  depends on what `ugv_ws` exposes — joint command or vendor service call). Verify
  with a test photo. `take_picture` assumes camera-heading == robot-yaw; this only
  holds if the gimbal is pinned forward first.
- [ ] Add a scan FOV mask for the pan-tilt mast's rear self-occlusion (a
  `LaserScanRangeFilter`/equivalent clearing the mast's known bearing range) —
  do this before the SLAM mapping step, not after; an unmasked scan corrupts the
  map, not just the costmap.
- [ ] Confirm — don't re-measure from scratch — the URDF footprint against the vendor
  drawing (`docs/img/waveshare_ugv_pt_dimensions.png`): 253×231 mm footprint, 289 mm
  height w/ mast, 126 mm wheelbase, 25 mm ground clearance. Current URDF (230×252 mm)
  is already close — geometry is not the gap. (6-wheel skid-steer vs. the URDF's
  4-wheel diff-drive model IS a real gap — the EKF node in A4 below is the mitigation,
  not a new task here.)

### A3. Build the real-room SLAM map

- [ ] Joystick setup — pick one and note which for next time:
  - [ ] **Plug the joystick into the Jetson** (USB dongle or Bluetooth), run
    `teleop_twist_joy` locally on the robot. No laptop needed while driving — just
    walk around with the controller. (Recommended: more ergonomic, and now that WiFi
    removes the tether problem, this is about convenience, not necessity.)
  - [ ] OR plug the joystick into the workstation, run `teleop_twist_joy` there,
    commands travel over WiFi (same shape as the old `teleop_twist_keyboard` plan).
- [ ] Start SLAM Toolbox on the Jetson:
  ```bash
  source /opt/ros/jazzy/setup.bash
  ros2 launch slam_toolbox online_async_launch.py use_sim_time:=false
  ```
- [ ] Drive the robot slowly around the room perimeter + past all furniture.
- [ ] **Done when:** the map has no big unexplored gaps and the perimeter closes
  cleanly (check in RViz if available, or by eye if the map image looks complete).
- [ ] Save the map:
  ```bash
  ros2 run nav2_map_server map_saver_cli -f src/nav_fleet/maps/bedroom_real
  # Creates: maps/bedroom_real.pgm + maps/bedroom_real.yaml
  ```
- [ ] Commit `bedroom_real.pgm`/`.yaml`.

### A4. Create `src/nav_fleet/launch/robot_launch.py`

Bare vendor driver + containerized brain — matches `nav2_only_launch.py`'s proven
settings (`use_composition`/`use_namespace` are hard Jazzy requirements; the EKF node
fixes the measured ~30% wheel-odom rotation over-report; `ball_detector` stays
always-on):

```python
# Copyright 2026 Mike. Licensed under Apache 2.0.
"""Launch Nav2 on the real ugv_pt robot (Jetson, no simulation, no Gazebo bridge)."""
import os
import pathlib

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.actions import Node

PKG = pathlib.Path(__file__).parent.parent


def generate_launch_description():
    ekf_node = Node(
        package='robot_localization',
        executable='ekf_node',
        name='ekf_filter_node',
        output='screen',
        parameters=[str(PKG / 'config' / 'ekf.yaml'), {'use_sim_time': False}],
        remappings=[
            ('/tf', '/robot_001/tf'),
            ('/tf_static', '/robot_001/tf_static'),
            ('odometry/filtered', '/robot_001/odometry/filtered'),
        ],
    )

    # Stays on DEFAULT hsv_gazebo.yaml — NOT hsv_realcam.yaml (doesn't exist yet,
    # Session 19 item 1 builds it; a missing config path crashes this node on a bare
    # `open()`). Mission 1 never consumes detections, so this is harmless for now.
    ball_detector = Node(
        package='nav_fleet',
        executable='ball_detector',
        name='ball_detector',
        output='screen',
        parameters=[{'use_sim_time': False,
                     'hsv_config': str(PKG / 'config' / 'hsv_gazebo.yaml')}],
    )

    nav2_bringup_dir = get_package_share_directory('nav2_bringup')
    nav2 = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(nav2_bringup_dir, 'launch', 'bringup_launch.py')
        ),
        launch_arguments={
            'namespace': 'robot_001',
            'use_namespace': 'true',
            'use_sim_time': 'false',
            'params_file': str(PKG / 'config' / 'nav2_params.yaml'),
            'map': str(PKG / 'maps' / 'bedroom_real.yaml'),
            'use_composition': 'True',
            'autostart': 'true',
        }.items(),
    )

    return LaunchDescription([ekf_node, ball_detector, nav2])
```

- [ ] Sanity-check standalone bare-metal first (debug only, isolates launch-file bugs
  from container concerns): `ros2 launch nav_fleet robot_launch.py` directly on the
  Jetson host.
- [ ] Then run it for real inside the container (the run that actually counts, using
  the SAME image `stage-3-arm64` builds — flags match the exact proven pattern
  `tools/mission2_day.py`'s `JetsonExecutor` already uses for HIL, verified
  2026-07-28):
  ```bash
  docker run --rm --name robot_brain --network host --ipc host \
    -v $HOME/autonomous-fleet-testbed/reports:/ros2_ws/reports \
    -v $HOME/fleet-ci-data:/root/fleet-ci-data \
    -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp -e ROS_DOMAIN_ID=0 \
    <hil-image> bash -c "source /opt/ros/jazzy/setup.bash && \
      source /ros2_ws/install/setup.bash && ros2 launch nav_fleet robot_launch.py"
  ```
  No `--device` flags needed — the container only talks DDS topics to the bare
  driver nodes on the same host, never touches `/dev` directly.

### A5. First real mission run + validate

- [ ] Physically place the robot at the known starting position, facing the
  documented heading (matches the R1 gate decision — same known start throughout).
- [ ] Set AMCL's initial-pose params in `nav2_params.yaml` to match that real pose in
  the NEW `bedroom_real` map's coordinate frame (SLAM zeroes its own origin — it has
  no reason to line up with anything else).
- [ ] Run the comparison test from the workstation:
  ```bash
  FLEET_DB=~/fleet-ci-data/fleet_runs.db SIM_ENGINE=real RUNNER_TYPE=real_robot \
    python -m pytest tests/test_navigation.py -v --timeout=120
  # RUNNER_TYPE=real_robot fixed 2026-07-28 — test_navigation.py used to hardcode
  # 'local' regardless of sim_engine, which would have mixed real-robot rows into
  # the sim drift baseline (the exact bug already fixed once for mission2 variants).
  python tools/sim_vs_real_comparison.py --sim-engine gazebo --real-engine real
  # Target: correlation >= 70%
  ```
  **Note (checked 2026-07-28):** `test_navigation.py` is proven today only in
  `stage-2-gazebo` — single machine, sim and test on the same box. `stage-4-hil`
  never runs this test at all (only Mission 2's day script). Running pytest from the
  workstation against the real robot's Nav2 action server is architecturally sound
  (standard cross-machine DDS action calls — the same mechanism HIL already uses for
  topics), but it's a genuinely NEW invocation shape, not something already proven by
  an existing CI leg. Worth watching closely the first time, not assuming it "just
  works" because the pieces are individually proven.
- [ ] **Ground-truth check (not automated — this is the check):** visually confirm the
  robot's actual final position/behavior matches the logged PASS row before trusting
  it. Real hardware has no Gazebo-equivalent oracle; this is the accepted mitigation.
- [ ] If correlation >= 70%: `git tag r1-complete && git push origin r1-complete`.
  If not: tune `nav2_params.yaml`, fix URDF dimensions, or accept the gap with
  documentation.
- [ ] Commit everything.

**Part A complete when:** `bedroom_real.pgm`/`.yaml` committed; `robot_launch.py` runs
clean standalone AND in-container; the robot completes Mission 1 without collision;
Mike's eyes-on check confirms the PASS row is real; correlation >= 70%; `r1-complete`
tagged.

---

## Part B — Day-to-Day Operation

### B1. Turn on and go (repeatable, after Part A is done once)

- [ ] Physically place the robot at the known starting position.
- [ ] Power on. Confirm SSH reachable over WiFi.
- [ ] Launch the brain container (same `docker run` command as A4).
- [ ] Run the mission / test as needed (same commands as A5).
- [ ] Ground-truth check by eye — every time, not just the first time.

### B2. After a test — pass or fail — pull evidence

- [ ] Pull ROS2 logs: `python -m tools.pull_ros_logs --host mike@<robot-ip>` (or set
  `JETSON_USER`/`JETSON_IP` env vars instead — same convention `scripts/hil_stage.sh`
  uses — and omit `--host` entirely).
- [ ] On a FAIL, a rosbag evidence bag should already be sitting in
  `reports/failure_bags/` (auto-captured by `mission_runner.py`'s failure-bag logic) —
  `scp` it back if it hasn't been pulled already.
- [ ] Generate a report: `python -m tools.generate_test_report --stage real`
  (fixed 2026-07-28 — `config/pipeline_matrix.yaml` now declares a `real` stage:
  `runner_type=real_robot`, `scenarios=[bedroom_nav]`, matching what
  `test_navigation.py` actually logs; covered by
  `tests/test_pipeline_matrix.py::test_real_config_declares_real_stage_matching_test_navigation`).
  **Still open:** this only covers the BR-01 nav-only check, not a real run of
  `mission_runner`'s actual `mission1` (navigate → photo → navigate back) —
  decide separately whether the validation gate should also exercise the full
  mission, not just nav-only.
- [ ] Check drift: `python -m tools.baseline_monitor --run-id <id>` (or check the
  dashboard's Drift tab). Real-robot rows now correctly get their own
  `runner_type=real_robot` (fixed 2026-07-28 — `test_navigation.py` used to
  hardcode `'local'` for every run, which would have mixed real-robot rows into
  the sim baseline — the exact scenario-mixing bug already fixed once for
  mission2 variants).

### B3. Code changed — getting back into HIL mode

One Jetson, no separate CI runner — this is a physical swap, every time:
- [ ] Physically remove the Jetson from the robot chassis.
- [ ] Reconnect it to the workstation bench (Ethernet, same as the original HIL
  setup).
- [ ] Re-run `scripts/hil_stage.sh day` / the normal CI pipeline as usual.
- [ ] Re-check `~/fleet-ci-data` ownership before the NEXT bare-metal real-robot run
  (container-mode HIL will re-poison it — see A1's check).

### B4. Code passed CI/CD — redeploy to the real robot

- [ ] Repeat A2's physical transplant steps to reinstall the Jetson into the robot.
- [ ] Repeat A4's container launch with the newly-tested image.
- [ ] Run B1's turn-on-and-go loop to confirm.
