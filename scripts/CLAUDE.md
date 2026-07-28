# scripts/ — Isaac Sim notes

Migrated out of the repo root CLAUDE.md by `/doctor` on 2026-07-27 (context-lazy-loading
pass) — loads only when Claude is working with files under this directory
(`isaac_bedroom_gui.py`, `isaac_robot.py`, `isaac_ros2_bridge.py`).

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
- **`/clock` must be explicitly published via OmniGraph.** `isaacsim.ros2.bridge` does NOT
  auto-publish `/clock`. Without it, Nav2 nodes with `use_sim_time: true` stay at time 0 — their
  clocks never advance, they request TF at t≈0, but all TF data from Isaac starts at the sim time
  when Isaac started (e.g. t=24s). Add `ROS2PublishClock` to the OmniGraph:
  ```python
  ("PublishClock", "isaacsim.ros2.bridge.ROS2PublishClock"),
  # connect: OnTick→execIn, SimTime→timeStamp, Context→context
  ```
- **Scan timestamps must use Isaac timeline directly** (`omni.timeline.get_timeline_interface().get_current_time()`),
  NOT `rclpy Node.get_clock().now()`. The rclpy clock with `use_sim_time` returns 0 before the first
  /clock message arrives, causing AMCL to anchor map→odom at t≈0 while odom TF starts at t=24s+.
- **OmniGraph TF topic must be namespaced:** `PublishTF.inputs:topicName` defaults to `/tf` but
  Nav2 with `namespace:robot_001` + `use_namespace:true` subscribes to `/robot_001/tf`. Set:
  `("PublishTF.inputs:topicName", f"/{NS}/tf")`
- **PhysX wheel velocity drives must be set programmatically.** The URDF importer warns
  "Stiffness and damping not available" for wheel joints with no `<dynamics>` tag — it creates
  velocity drives with damping=0. `set_joint_velocity_targets()` is silently ignored. Fix:
  set `damping=100` via `UsdPhysics.DriveAPI.Apply` AFTER `robot.initialize()`:
  ```python
  from pxr import UsdPhysics
  for dof in robot.dof_names:
      jp = stage.GetPrimAtPath(f"{ARTIC_ROOT}/Physics/{dof}")
      drive = UsdPhysics.DriveAPI.Get(jp, "angular") or UsdPhysics.DriveAPI.Apply(jp, "angular")
      drive.GetDampingAttr().Set(100.0)
      drive.GetStiffnessAttr().Set(0.0)
  ```
- **Scan timestamp source (GUI mode):** `omni.timeline.get_timeline_interface().get_current_time()`
  reads the Python/app thread which is stale in GUI mode. Use `rclpy Node.get_clock().now()` AFTER
  OmniGraph has published `/clock` (gate on `clock_now.nanoseconds > 0`).
- **`spin_once(timeout_sec=0)` misses cmd_vel with CycloneDDS.** Zero-timeout returns immediately;
  async DDS messages are consistently missed. Fix: background `SingleThreadedExecutor` daemon thread:
  ```python
  from rclpy.executors import SingleThreadedExecutor
  import threading
  _exec = SingleThreadedExecutor(); _exec.add_node(ros_node)
  threading.Thread(target=_exec.spin, daemon=True).start()
  ```
  Remove `rclpy.spin_once()` calls from the main loop entirely.
- **DDS TRANSIENT_LOCAL TF replay — must restart Isaac AND Nav2 together.** Isaac's
  `/robot_001/tf` publisher uses TRANSIENT_LOCAL QoS. DDS caches the full TF history. Any new
  Nav2 subscriber (even if Isaac kept running) gets the entire history replayed, causing thousands
  of "jump back in time" warnings and goal rejection. Rule: kill BOTH Isaac and Nav2 between runs.
  Start Nav2 within ~5s of Isaac's "Simulation running" message so the replayed history is small.
  **Worth investigating (2026-07-06), not yet done:** `scripts/isaac_bedroom_gui.py`'s
  `ROS2PublishRawTransformTree` OmniGraph node has no explicit QoS override — TRANSIENT_LOCAL
  is just whatever it defaults to, not a setting anyone chose deliberately. Standard ROS2
  convention is `/tf` on VOLATILE QoS (only `/tf_static` should be TRANSIENT_LOCAL). If that
  node exposes a `qosProfile` input, overriding it to VOLATILE could remove this restart
  requirement at the source instead of managing around it forever — hasn't been tried yet.
- **Global costmap obstacle_layer causes "Start occupied" on replan — only with periodic
  replanning.** During navigation, live lidar scans of furniture (e.g. PC tower) accumulate in
  the global costmap's obstacle layer. If the BT triggers a *periodic* replan from a position
  adjacent to that furniture, the global planner finds the start cell occupied and aborts.
  Session 11 fix was to remove `obstacle_layer` from `global_costmap.plugins`. Session 11/12's
  minimal one-shot BT (`navigate_simple.xml` — plan once, no `RateController` replanning loop)
  removes the actual trigger for this, so `obstacle_layer` was restored to the global costmap
  (matches `BC/isaac_project`). If a future BT reintroduces periodic replanning, this failure
  mode comes back and `obstacle_layer` should come back out of `global_costmap.plugins`.
- **`PYTHONUNBUFFERED=1` + `python -u` required.** Isaac's stdout is fully buffered when piped
  to a file — the "Simulation running" message is never flushed without these flags.
- **A ROS2 params YAML's top-level key must equal a node's exact, unqualified name.** Giving a
  node `namespace='robot_001'` in a hand-rolled launch file changes its real name to
  `/robot_001/controller_server`, which no longer matches a plain `controller_server:` key in
  the params file — no error, just a silent fall-through to compiled-in defaults (this is how
  `DWBLocalPlanner` got loaded instead of our configured RPP, with "no critics defined" as the
  only clue). `nav2_bringup`'s `bringup_launch.py` avoids this with its own namespace-templating
  machinery (`ReplaceString`/`<robot_namespace>`). For hand-rolled Nav2 launches: don't namespace
  the node at all — apply the `/robot_001/` prefix entirely through explicit **absolute**
  topic/action remappings instead (see `nav2_isaac_launch.py`).
- **Composable nodes can't accept an empty-list parameter.** A node loaded via a container's
  `load_node` service call (as `nav2_bringup`'s composition does) crashes on `polygons: []` /
  `observation_sources: []` — `Expected 'value' to be ... got '()' of type 'tuple'`. The
  parameter bridging code can't infer an empty array's element type. A reference config with
  this exact syntax can still "work" if its launch never actually instantiates that node live
  (that's why `BC/isaac_project`'s config has this and never hits the bug). Workaround for
  `collision_monitor`: give it one real, harmless polygon instead of an empty list — e.g. a 2cm
  square, smaller than the lidar's own minimum range, so it can never actually trigger.
