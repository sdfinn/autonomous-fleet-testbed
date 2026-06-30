# autonomous-fleet-testbed — Claude Code Context

## Project
Open-source CI/CD-native fleet simulation testing framework for autonomous robots.
Master strategic brief: BLUEPRINT.md (working doc — vision, roadmap, decisions).
robotics_cicd_10x_blueprint.md is reference-only source dialogue, not for coding.
Execute from Release1Todo.md (session plans); code from .superpowers/sdd/ specs.

## Development workflow — tier 1 first

**Primary dev loop (x86 bare metal — use this to flush bugs before touching CI):**
```bash
colcon build --symlink-install          # ~1s — build the ROS2 package
source install/setup.bash
python -m pytest tests/ -v \
  --ignore=tests/test_ros2_contracts.py # seconds — run Python unit tests
ros2 launch nav_fleet sim_launch.py    # Session 09+ — Gazebo + Nav2 locally
# nav_runner, metrics_collector, drift check all run here
```

x86 is not the robot's target OS but finds 90% of bugs at ~1s build vs 23 min QEMU.
Commit to CI only when the x86 pipeline is clean. See BLUEPRINT.md "Tiered development loop."

## Environment
- Ubuntu 24.04 bare metal (dual boot with Windows 11)
- ROS2 Jazzy + Gazebo Harmonic + CycloneDDS
- Python virtualenv: ~/fleet-env (activate before running Python tools)
- Colcon workspace: ~/autonomous-fleet-testbed/ (build from here)

## Key Commands
```bash
# New terminal — .bashrc auto-sources ROS2, CycloneDDS, fleet-env, and workspace overlay.
# Only need to build + launch:
colcon build --symlink-install
ros2 launch src/nav_fleet/launch/sim_launch.py   # Session 09+ — Gazebo locally

# Run Python unit tests (venv auto-activated by .bashrc)
python -m pytest tests/ -v --ignore=tests/test_ros2_contracts.py

# Traceability gate
python tools/check_traceability.py requirements/traceability.yaml tests/ \
  --profile robot_profiles/jetson_ugv_pt.yaml

# Dashboard
streamlit run dashboard/app.py

# arm64 Docker build (Tier 2 — only after Tier 1 is clean)
docker buildx build --platform linux/arm64 \
  --tag ghcr.io/sdfinn/autonomous-fleet-testbed:latest --load .
```

## Directory Layout
- `src/nav_fleet/`         — ROS2 colcon package (nav runner, metrics collector)
  - `launch/sim_launch.py` — main launch file (Gazebo + bridge)
  - `urdf/ugv_pt.urdf.xacro` — 4-wheel UGV robot URDF (diff-drive, lidar, camera)
  - `worlds/bedroom_simple.sdf` — real bedroom geometry from BC/isaac_project measurements
  - `maps/`                — pre-built Nav2 occupancy grid from BC project (0.05 m/px)
  - `config/nav2_params.yaml` — Nav2 params tuned for this room and robot
- `tools/`          — Python utilities (baseline monitor, telemetry logger, etc.)
- `tests/`          — pytest test suite
- `config/`         — drift_config.yaml
- `robot_profiles/` — Per-robot capability YAML
- `requirements/`   — Traceability matrix and requirement specs
- `reports/history/`— CI run JSON reports (drift detection reads from here)
- `.github/workflows/ci.yml` — 6-stage CI pipeline
- `GazeboCommands.md` — Gazebo viewer navigation cheat sheet

## Gotchas
- `.bashrc` now sources ROS2, CycloneDDS, fleet-env venv, AND workspace overlay automatically.
  After `colcon build`, a new terminal picks up all changes — no manual `source install/setup.bash` needed.
- `source install/setup.bash` still required in the same terminal that ran `colcon build`.
- Gazebo Harmonic command is `gz sim`, NOT `ign gazebo`
- URDF topics must use /robot_001/ namespace
- Launch file uses `pathlib.Path(__file__).parent.parent` instead of `get_package_share_directory`
  because `colcon-ament-python` is not installed — this is intentional and correct.
- OGRE2 (Gazebo Harmonic renderer) needs `<diffuse>` in SDF materials, not just `<ambient>`.
  Ambient-only = black surfaces. Both the SDF world and URDF gazebo blocks use `<diffuse>`.
- Isaac Sim session (Session 11): requires NVIDIA driver 570+. Driver 595.71.05 already installed.
- `requirements.txt` is a full pip freeze of the local ROS2 venv — NOT for CI use. Use `requirements-ci.txt` in CI jobs.
- DB path env var is `FLEET_DB` (default: `reports/fleet_runs.db`) — used by telemetry_logger, validate_telemetry, ai_test_generator, dashboard
- `tests/test_ros2_contracts.py` requires a live ROS2 environment — always `--ignore` it in local pytest runs
- CI stage-0 exits with code 1 intentionally (missing Session 10 tests). `continue-on-error: true` is in place; remove it in Session 10.

## Nav2 Launch Gotchas (Session 10+)
- `gz sim` WITHOUT `-s` launches a GUI that crashes on this machine (snap/glibc libpthread conflict)
  and takes the Gazebo server down with it. Always use `gz sim -s -r <world>` (server only).
  To view the simulation separately: `gz sim -g` (GUI client only, connects to running server).
- The ros_gz_bridge must be delayed ~5s after Gazebo starts. If the bridge subscribes before
  Gazebo's gz-transport publishers are up, the GZ→ROS subscriptions silently fail (no reconnect).
- Nav2 Jazzy requires `use_composition: 'True'` (capital F). 'False' launches ~16 separate
  processes that exhaust CycloneDDS domain 0 participant limit.
- Nav2 Jazzy requires collision_monitor with `polygons` + `observation_sources` populated (empty
  lists fail). Docking_server requires `dock_plugins`. Both added to nav2_params.yaml.
- Nav2 Jazzy `controller_server` requires `progress_checker_plugins` (plural, list) NOT the old
  `progress_checker_plugin` (singular string). Also requires `controller_frequency`,
  `costmap_update_timeout`, `failure_tolerance`, `use_realtime_priority` — see Jazzy defaults.
- **TF architecture (multi-robot):** RSP publishes frames by URDF link name (no prefix: `odom`,
  `base_footprint`, `lidar_link`). diff_drive `<frame_id>` and `<child_frame_id>` must also be
  unprefixed (`odom`, `base_footprint`). Both sources publish to `/robot_001/tf` (RSP remapped).
  Nav2 with `namespace:robot_001` + `use_namespace:true` subscribes to `/robot_001/tf` — per-robot
  TF isolation is at the TOPIC level, not the frame-name level. frame_prefix NOT supported in
  Jazzy RSP 3.3.4.
- nav2_params.yaml frame names (`base_frame_id`, `odom_frame_id`, `robot_base_frame`) must use
  unprefixed frame names (`odom`, `base_footprint`, `base_link`) to match RSP output.
  Topic names (`scan_topic`, `odom_topic`) still use `/robot_001/` prefix — those are correct.
- **ros_gz_bridge direction:** Use `[` (GZ→ROS) and `]` (ROS→GZ) NOT `@` (bidirectional).
  Bidirectional on `/robot_001/tf` creates an echo loop: AMCL's map→odom goes ROS→GZ→ROS,
  causing "jump back in time" warnings that clear the TF buffer continuously.
  Rule: odom/scan/camera/imu/tf/clock = `[` (GZ→ROS). cmd_vel = `]` (ROS→GZ).
- Gazebo GPU lidar publishes scan with frame_id = `robot_001/base_footprint/lidar` (Gazebo internal
  entity path). A zero-offset static TF from `lidar_link` → `robot_001/base_footprint/lidar`
  is needed in the launch file (lidar_frame_bridge node).
- Nav2 bringup with `use_namespace:true` + `namespace:robot_001` remaps all Nav2 topics to
  `/robot_001/` prefix. The action server is at `/robot_001/navigate_to_pose`.
- AMCL `set_initial_pose: true` with initial_pose params works — sets pose to bedroom origin.
- **Gazebo RTF:** RTX 5080 runs Gazebo at ~3x real-time. After 95s wall time, sim time is ~280s.
  Old sim-time TF data from a previous run can pollute a fresh TF buffer if the nav2 container
  isn't fully killed. Power down between debug sessions to avoid stale data.
- **Killing sim processes:** `pkill` on individual processes is unreliable — orphaned Gazebo
  and nav2 container processes persist. Correct approach: Ctrl+C on the `ros2 launch` foreground
  process (it sends SIGINT to the whole process group). For CI, the launch process is killed by
  the runner's job cleanup. Never chain `pkill` calls hoping to clean up mid-session.
- **nav_runner goal stamp:** Use `Time().to_msg()` (zero timestamp = "use latest TF") for the
  NavigateToPose goal header stamp. Wall-clock `get_clock().now()` will be rejected by Nav2
  which uses sim time (far-future wall timestamp has no TF data in Nav2's buffer).
- Self-hosted CI runner: labels `self-hosted, x86, gpu, rtx5080`. Service: actions.runner.*.service.
  Token must be regenerated if expired (GitHub → Settings → Actions → Runners → Add Runner).
