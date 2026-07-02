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
- **4-wheel diff-drive: ALL wheel joints must be in the plugin.** The Gazebo Harmonic
  `gz-sim-diff-drive-system` plugin supports multiple `<left_joint>`/`<right_joint>` entries.
  If only rear wheels are driven and front wheels are passive `continuous` joints, the front
  wheels resist in-place rotation via lateral friction — the robot cannot rotate. The odom is
  computed from the DRIVEN wheel joint positions only, so it reports rotation even when the body
  is physically stationary. Fix: include all four wheel joints.
  ```xml
  <left_joint>rear_left_wheel_joint</left_joint>
  <left_joint>front_left_wheel_joint</left_joint>
  <right_joint>rear_right_wheel_joint</right_joint>
  <right_joint>front_right_wheel_joint</right_joint>
  ```
- **RPP (RegulatedPurePursuitController) — two params required for in-place rotation:**
  `use_collision_detection: false` (default true fires before rotation on tight corridors) and
  `rotate_to_heading_min_angle: 0.3` (17° — lower than the 45° default to catch small heading
  errors from diagonal SMAC paths).
- **SMAC Planner 2D vs NavFn:** NavFn A* penalises diagonal grid moves (cost √2 vs 1.0),
  producing north-first paths. SMAC 2D uses equal cost for all 8 directions — it naturally
  routes diagonally toward the goal. Use SMAC when diagonal paths matter for controller heading
  error. Plugin: `nav2_smac_planner::SmacPlanner2D`.

## Isaac Sim Gotchas (Session 11+)
- **Version:** `isaacsim==6.0.1.0` is the correct pip package (`isaacsim[all,extscache]==6.0.1.0`
  for the full bundle). Isaac Sim 5.x was never published to pypi.nvidia.com.
- **EULA:** Set `OMNI_KIT_ACCEPT_EULA=YES` env var (or `os.environ` before import) for headless
  non-interactive use. Without it, the process hangs at an interactive prompt.
- **Import ordering:** ALL `omni.*` and `isaacsim.*` imports must come AFTER `SimulationApp` is
  instantiated. The Carbonite framework won't load extensions before the app exists.
- **URDF import API (6.0):** Use `URDFImporter(URDFImporterConfig(...)).import_urdf()` from
  `isaacsim.asset.importer.urdf`. The old `omni.kit.commands.execute("URDFCreateImportConfig")`
  command is not registered in 6.0.
- **URDF prim layout after import:** The importer adds a `Geometry` layer:
  `/ugv_pt/Geometry/base_footprint/base_link/...` (not `/ugv_pt/base_footprint/...`).
  Joints are at `/ugv_pt/Physics/`. Always traverse the stage after import to discover paths.
- **USD output path:** Pass `usd_path="/tmp/..."` (outside the repo). If the path already exists,
  the importer creates versioned subdirs (`ugv_pt_1/`, `ugv_pt_2/`, ...) inside it.
- **RTX lidar headless:** In headless mode, `IsaacSensorCreateRtxLidar` creates an `OmniLidar`
  prim (not a Camera prim). No sensor-specific render product is created — only the generic
  `/Render/OmniverseKit/HydraTextures/Replicator` product exists. `ROS2RtxLidarHelper` can't
  get scan data from it. Use `RotatingLidarPhysX` (PhysX raycasting) for headless scan publishing.
- **RotatingLidarPhysX frame key:** Frame dict key is `'linear_depth'` (not `'linear_depth_data'`).
  Call `lidar.add_linear_depth_data_to_frame()` before `initialize()`, then `get_current_frame()`
  in the loop. Publish via rclpy `sensor_msgs/LaserScan` manually.
- **IsaacSensorCreateRtxLidar orientation:** Pass `Gf.Quatd(w, x, y, z)` not a plain tuple —
  plain tuples are interpreted as `GfVec4d` and cause a USD type mismatch error.
- **ROS2 bridge extension name (6.0):** `isaacsim.ros2.bridge` (not `omni.isaac.ros2_bridge`).
  Import path: `from isaacsim.core.utils.extensions import enable_extension`.
- **OmniGraph odom chassis prim:** `IsaacComputeOdometry` needs the articulation root (`/ugv_pt`),
  not a link prim. Link prims fail with "not a valid rigid body or articulation root".
