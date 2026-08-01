# src/nav_fleet/ — package notes

ROS2 colcon package (nav runner, metrics collector). Migrated out of the repo root
CLAUDE.md by `/doctor` on 2026-07-27 (context-lazy-loading pass) — loads only when
Claude is working with files under this directory.

- `launch/sim_launch.py` — main launch file (Gazebo + bridge); Session 15 split it into
  `launch/sim_only_launch.py` (Gazebo + bridge) and `launch/nav2_only_launch.py` (Nav2
  bringup only — the mission executor is a separate third process,
  `python -m nav_fleet.mission_runner`), which `sim_launch.py` now composes for Tier-1 —
  the same split lets the two halves run on separate machines for HIL (Gazebo on x86,
  Nav2 on the Jetson).
- `nav_fleet/semantic_map.py` — Session 15: `SEMANTIC_MAP` waypoint registry (doorway_center,
  home_base, ...) that missions reference by name
- `nav_fleet/missions.py` — Session 15: mission data model (`MissionStep(action, label,
  location=None, yaw=None)`) — Mission 1 is navigate → take_picture → navigate
- `nav_fleet/mission_runner.py` — Session 15: mission executor CLI
  (`python -m nav_fleet.mission_runner <mission_name>`)
- `nav_fleet/failure_bag.py` — S17 Piece 3 (2026-07-21): rolling rosbag2 evidence on
  FAIL. Uses `ros2 bag record --snapshot-mode` (CLI-only, no rclpy API) — buffers
  `cmd_vel`/`scan`/`amcl_pose`/`navigate_to_pose`'s action-status in memory ONLY until
  the `/rosbag2_recorder/snapshot` service is called, which persists the buffered
  window to disk. `mission_runner.py`'s `main()` starts it before `rclpy.init()`,
  calls `snapshot()` only on FAIL/crash, and keeps the bag (`reports/failure_bags/`)
  only if that snapshot succeeded — zero disk cost on a passing mission. Prints
  `failure bag kept: <path>` on keep; `mission2_day.py`'s `JetsonExecutor` scrapes
  that line and `scp -r`s the bag back from the Jetson (mirrors the existing
  `_pull_photos` pattern).
- `nav_fleet/image_io.py` — Session 15: `take_picture` action primitive support
  (`image_msg_to_png`), backed by pillow
- `urdf/ugv_pt.urdf.xacro` — 4-wheel UGV robot URDF (diff-drive, lidar, camera)
- `worlds/bedroom_simple.sdf` — real bedroom geometry from BC/isaac_project measurements
- `maps/`                — pre-built Nav2 occupancy grid from BC project (0.05 m/px)
- `config/nav2_params.yaml` — Nav2 params tuned for this room and robot

## Nav2 Launch Gotchas (Session 10+)
- `gz sim` WITHOUT `-s` launches a GUI that crashes on this machine (snap/glibc libpthread conflict)
  and takes the Gazebo server down with it. Always use `gz sim -s -r <world>` (server only).
  To view the simulation separately: `gz sim -g` (GUI client only, connects to running server).
- **The snap/glibc GUI crash is caused by snap-VS-Code environment pollution — and it hits the
  separate `gz sim -g` client too when launched from a VS-Code/Claude-Code shell** (found
  2026-07-12: `GTK_PATH`/`GTK_EXE_PREFIX`/etc. point into `/snap/code/...`, whose GTK modules
  drag in snap core20's libpthread → `symbol lookup error: __libc_pthread_init`). Plain user
  terminals are unaffected. Workaround from a polluted shell — scrubbed environment:
  ```bash
  env -i HOME=$HOME USER=$USER TERM=xterm PATH=/usr/local/bin:/usr/bin:/bin DISPLAY=:0 \
    XAUTHORITY=${XAUTHORITY:-/run/user/1000/gdm/Xauthority} \
    bash -c 'source /opt/ros/jazzy/setup.bash && gz sim -g'
  ```
- **A different failure — `gz sim -s -r` (headless SERVER, not just `-g`) can die with a GLX
  `BadValue` X error if the NVIDIA driver's kernel module and userspace libraries have drifted
  out of sync — don't assume it's the snap/glibc issue above just because the symptom looks
  similar.** Found 2026-07-26 (Session 17 Piece 2 performance pass): `gz sim -s -r
  bedroom_simple.sdf` died immediately with `X Error of failed request: BadValue ... GLX
  ... process has died`, reproduced identically with AND without the scrubbed-env workaround
  above — ruling out snap/GTK pollution as the cause this time. Root cause: Ubuntu's
  unattended-upgrades had silently upgraded the NVIDIA userspace packages (`nvidia-utils-595`
  et al., 595.71.05 → 595.84) without a reboot, so the loaded kernel module (confirmed via
  `cat /proc/driver/nvidia/version` → still 595.71.05) no longer matched. `nvidia-smi` is the
  fast diagnostic: `Failed to initialize NVML: Driver/library version mismatch` means every
  GL-context-creating process on the box (including Ogre2's offscreen context for the camera
  sensor) is broken until reboot — not just Gazebo. Fix: reboot (reloading the nvidia kernel
  module live under an active desktop session is riskier than just rebooting). No code-side
  workaround exists or should be attempted — this is host maintenance, not a project bug.
  Worth periodically checking `nvidia-smi` after any unattended driver-package upgrade,
  independent of this project.
- **Jetson powered off ⇒ local sim breaks (silently) unless `ROS_LOCALHOST_ONLY=1`.** With the
  Jetson down, `enp6s0` goes `NO-CARRIER`/DOWN and CycloneDDS floods "Exception sending a
  multicast message: Network is unreachable" — DDS discovery fails, so Nav2 never reaches
  "Managed nodes are active" (found 2026-07-12). For any local-only session while the shared
  link is down, prefix EVERY command (launch, mission runner, pytest) with
  `ROS_LOCALHOST_ONLY=1`. All processes must agree — mixing localhost-only and normal
  processes means they can't see each other. Unset it (or use fresh terminals) for HIL work.
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
- **Orphaned `parameter_bridge`/`static_transform_publisher` processes poison EVERY later sim
  run on their DDS domain — including CI (domain 0).** Found 2026-07-15: 13+ bridges had
  accumulated across a debug day because every teardown pattern checked
  `gz sim|component_container|robot_state_publisher|ros2 launch` and none matched
  `parameter_bridge`, `static_transform_publisher`, or `ekf_node`. gz-transport has NO DDS
  domain isolation, so an old bridge attaches to any NEW Gazebo server and re-publishes
  /clock + TF into its OLD domain: two interleaved /clock publishers → out-of-order stamps →
  tf2 "Detected jump back in time" floods (8,716 in one CI run) → AMCL can't anchor TF →
  goals REJECTED, and the nav2 container can even SIGABRT on an uncaught
  `tf2::NoDataForExtrapolationException`. The COMPLETE teardown/verify pattern is:
  `pgrep -af "gz sim|component_container|robot_state_publisher|ros2 launch|parameter_bridge|static_transform|ekf_node|ball_detector"`
  (`ball_detector` added 2026-07-26, second-round code review: its cmdline contains
  `nav_fleet`, not `nav2`, so it matched none of the sweep sites and 2 live orphans were
  found running on the Jetson — not cosmetic, since extra publishers on
  `/robot_001/detections` raise the effective detection rate and shorten Mission 2's
  `REACTION_FRAMES` time-to-trigger). stage-2 in ci.yml now sweeps this pattern before
  launch and after the job. Also: unique
  `ROS_DOMAIN_ID` per local run only hides leftovers, it doesn't prevent them — and reusing a
  domain number (or running on 0, like CI) collides with them. From a Claude Code shell,
  subagent-spawned leftovers may not respond to sandboxed pkill — kill by explicit PID with
  sandbox disabled if the pattern kill reports success but pgrep still shows them.
- **Headless Gazebo here renders via llvmpipe (software) — a newly spawned model takes up to
  ~1.5 s to appear in camera frames.** Found 2026-07-17 (Mission 2 calibration): a fixed
  `sleep(1.0)` after `gz service` spawn is flaky; poll-until-detected (≤5 s, 0.5 s steps) is
  the pattern for any test/tool that spawns a model then expects the camera to see it.
  **Removal lags too** (found same evening): a REMOVED model lingers in rendered camera
  frames for seconds — back-to-back tests reacted to the previous test's "ghost" ball.
  Hence `BALL_REMOVAL_SETTLE_S = 3.0` after `remove_ball`/`BallOps.settle()` in
  `tools/mission2_harness.py` (consumed by `tools/mission2_day.py`; the old
  standalone `tests/test_mission2.py` this originally referenced was removed
  2026-08-01 as redundant with `mission2_day.py`'s in-process stage-2 run).
- **`pkill -f`/`pgrep -f` SELF-MATCH: the pattern matches the invoking shell's own command
  line.** Bit twice on 2026-07-17: a teardown containing `pkill -INT -f "ros2 launch …"`
  plus a relaunch of that same string SIGINT'd its own shell (exit 144) and never killed the
  target; a `pgrep -f "gz sim -g"` check listed itself. Rules: derive PIDs with
  `ps -eo pid,cmd | grep/awk` + `grep -v grep` (or `awk '/[r]os2 launch/'` bracket trick),
  kill by explicit PID, and never put the literal pattern in the same command that greps
  for it.
- **CI triggers ONLY on push-to-main and PRs targeting main** — pushing a feature branch
  runs nothing. To exercise CI from a branch, open a (draft) PR; that's what draft PR #4
  is for on `mission2-camera-reactive` (2026-07-17: full 8-job green first try, incl.
  stage-4 HIL on the Jetson, run 29626889652).
- **Don't trust a run's Actions "Summary" page for report/drift content — it's a
  confirmed GitHub platform bug, recurred twice (2026-07-23, 2026-07-25).** GitHub's
  Summary page has repeatedly shown `stage-1-quality` displaying `Report — hil_jetson`/
  `DRIFT DETECTED` content that job structurally cannot produce (zero
  `$GITHUB_STEP_SUMMARY` writes anywhere in its job spec — only the two
  `stage-5-reports-*` jobs write that content). Confirmed not just misattribution but
  genuinely STALE data: on 2026-07-25 the displayed content didn't match that exact
  run's own real console log OR its own downloadable PDF artifact. No code fix exists
  — GitHub Actions' job-summary feature has no public API at all (`gh api
  .../check-runs/<id>` returns `output.summary: null` always; the Summary tab is a
  JS-rendered SPA with nothing in the raw HTML). **Verify report/drift content against
  the telemetry DB or the downloaded PDF artifact instead of the Summary page.** Both `stage-5-reports-*` jobs now
  print a direct one-click link to their own PDF artifact in their summary (2026-07-25)
  — still downloads as a zip (a GitHub Actions platform constraint, no way around it
  short of moving off the standard artifacts system entirely, e.g. GitHub Pages/
  Releases — not done, real trade-offs, not attempted).
- **Mission 2 state (post-2026-07-18, Task 13 Option B):** Mission 2 is now ONE
  self-returning mission — a verified round trip, not a one-way drive. Five steps: (1) home
  reference photo BEFORE any movement, (2) navigate to the floor marker with reactions armed
  (red 1.3 m -> `photo_then_stop`, yellow 0.8 m -> `photo_then_home`), (3) marker photo,
  (4) navigate itself HOME (no external reset leg), (5) home arrival photo — must MATCH the
  reference (see `tools/mission2_harness.judge_home_pair` / `HOME_PAIR_MAX_DIFF`, a
  gross-failure guard, not a precision instrument — see its comment in
  `tools/mission2_harness.py`). The mission's own per-waypoint checklist (`runner.checklist`,
  printed by `mission_runner.main()`) IS the verdict. A fired reaction SHORTENS the mission
  (Option B): red stops in place after its photo (no further steps); yellow folds its own
  return-and-arrival-photo into the reaction, so the pair check still applies. The no-ball
  scenario is renamed `mission2_no_ball` (was `mission2_nominal`) — old telemetry rows keep
  their old name, only new rows use the new one. Marker (0.9, 3.90) / ball (1.2, 3.90) now
  sit EAST of the dresser (Mike's GUI review, 2026-07-18) — see `semantic_map.py`'s
  `sphere_approach`/`MARKER_XY` comments for the clearance math. `tools/mission2_day.py` is
  THE single day orchestrator — it is stage-4's only Mission 2 step, the GUI demo command,
  and the future real-robot-day runner, all running the SAME sequence (no_ball -> yellow ->
  red). Ball placement is pluggable (`GzBallOps` for sim/HIL, `OperatorBallOps` for a human
  on the real robot) and mid-return placement is part of the choreography: the yellow ball
  is placed DURING no_ball's return leg, and yellow is swapped for red DURING yellow's
  return leg (both behind the retreating robot, after a settle — reactions are
  outbound-only, so this can't self-trigger). Judges enforce min-travel (≥0.5 m before a
  reaction counts) + start-position preconditions. World sun `cast_shadows` is FALSE
  (observability; detection revalidated live shadow-free). Detector ignores
  frame-edge-clipped bboxes (clipped width corrupts the range estimate). `-k red`-style
  pytest filters are substring matches — the ignore test was renamed after `-k red` matched
  `…is_ignoRED`.
  **One continuous day, S17 Piece 9 (2026-07-25, branch `fix/hil-container-lifecycle`,
  PR #5, not yet merged): the day is now ONE continuous execution, not 3 externally-invoked
  scenario calls.** Supersedes both the old per-scenario architecture AND Piece 8's
  persistent-container fix below (which became unnecessary once there's only one
  invocation per day). `mission_runner.py` gained `MissionRunner.run_mission2_day()`
  (loops `run_mission('mission2')` 3x in one process, collects each leg's
  checklist/photos/reaction_events) and a `--day` CLI mode (prints one
  `MISSION2_DAY_RESULT:<json>` line). `tools/mission2_day.py`'s `InProcessExecutor`/
  `JetsonExecutor` both implement `run_day() -> list[dict]` — `JetsonExecutor.run_day()`
  is now a SINGLE `docker run --rm`/bare-SSH call for the whole day (Piece 8's
  `_start_container`/`close()`/`HIL_CONTAINER_NAME`/`docker exec`-into-a-persistent-
  container machinery was REMOVED, not kept dormant, since one call/day has nothing
  left to amortize). `run_no_ball`/`run_yellow`/`run_red` (the old scenario-named
  functions) are DELETED. Ball choreography is now `GroundTruthLog` (continuous
  timestamped ground-truth samples for the whole day, `record`/`nearest`/
  `closest_approach_to`) + `run_ball_choreography()` (ONE thread for the whole day,
  concurrent/gz mode only — `if ball_ops.concurrent:` guards it, so operator mode gets
  no thread and no ball_ops calls at all: **no prompting of any kind** — Mike's explicit
  call, "it's up to the human to place the balls at the correct time themselves,
  watching the robot," `OperatorBallOps.place`/`.remove` (the old `input()`-prompting
  methods) were removed as unreachable). `_judge_and_log_leg`/`run_day()` (top-level)
  replace the old `run_no_ball`/`run_yellow`/`run_red`, feeding `judge_*`/
  `log_variant_row`/`home_pair_similarity` (unchanged signatures — frozen by design)
  from post-hoc `GroundTruthLog` lookups instead of live point-in-time polls.
  **Measured result: 0.0000s leg-to-leg loop overhead**, confirmed 3x independently
  (x86 in-process, Jetson bare-metal, Jetson container) — down from the ~17.6s Jetson
  inter-scenario gap this piece targeted (the scrapped persistent-service/DDS-RPC first direction, and the
  design conversation).
  **Two real bugs found live during GUI-watched verification, both fixed the same
  session (neither anticipated by the plan):** (1) a premature yellow→red ball swap — the second retreat-wait armed a
  fresh `RetreatDetector` immediately after placing yellow, while leg 1's OWN return
  was still in progress, getting fooled by leftover leg-1 descent into firing almost
  instantly; fixed with a new `OutboundDetector` (mirrors `RetreatDetector` — tracks
  the lowest y seen, fires once climbed back up `climb_m` above it) that gates the
  second wait behind a genuine "robot has left home again" signal. (2) an 8-second
  ground-truth-polling stall, TWICE per leg (`get_ground_truth_xy()` in
  `ground_truth.py` runs `gz topic -e` with `GZ_POSE_TIMEOUT_S`, which off-sim can
  never succeed and always burned the full timeout) — pre-existing (Session 13-era),
  not a Piece 9 regression, just newly VISIBLE once Piece 9 removed the bigger cost
  that used to mask it; fixed by cutting `GZ_POSE_TIMEOUT_S` 8.0 -> 1.0 (evidence-based:
  measured real local x86 response 0.09-0.11s, ~10x margin retained) rather than an
  env-var-gated skip, since a timeout fix covers HIL now AND any future real-robot
  runner-type automatically.
  **Known, deliberately accepted/deferred gap:** `final_x`/`final_y` telemetry columns
  are now always `0.0` for Mission 2 rows (both executors return plain dicts, not a
  live object with `.nav.last_final_x` for `log_variant_row` to read — its signature
  is frozen by this piece's own design). Confirmed the HIL path was ALREADY zeroed
  before this change; only x86 loses real data; `mean_position_error` (the actual
  drift-watched metric) was never sourced from Mission 2 rows either way — no
  monitoring capability lost. A real fix exists (thread the robot's own final-position
  estimate through the leg dict, same treatment photos already get) but Mike
  deliberately deferred it: Mission 2 is scripted/hardcoded so the fix would be easy,
  but Mission 3 will be autonomous enough that "final position" may not even be a
  well-defined concept — that design work should decide the shape of this fix, not
  a Mission-2-specific patch made now.
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
- **bt_navigator `default_server_timeout` 20ms → 1000ms is the ROOT FIX for the cold-goal
  abort storm** (Task 13 fix wave, 2026-07-18): on a fresh mission_runner process, the FIRST
  goal was sometimes accepted then aborted in ~0.1-0.25s before the robot moved. Cause: the
  BT's internal goal-ack window (20ms default) is too short on a loaded Jetson — the
  controller_server's ack legitimately takes longer than that under load, so bt_navigator
  gives up on a goal that was actually fine. Worse, the controller could go on to EXECUTE the
  delivered path after bt_navigator had already aborted the handle — a "zombie goal": the
  robot drives with no supervising mission, a real safety issue on hardware. Fix has two
  parts: the timeout bump (root fix, `src/nav_fleet/config/nav2_params.yaml`
  `default_server_timeout: 1000`) removes the race at the source; `nav_runner.py`'s bounded
  cold-start retry (escalating `sleep(2.0 * (attempt+1))` backoff, `COLD_ABORT_RETRIES`) is
  now just a safety net for whatever the timeout doesn't catch, not the primary fix; and a
  cancel-on-failure guard (`NavRunner._last_goal_handle`) cancels any still-outstanding goal
  before reporting failure, so a giving-up mission can never leave an unsupervised robot
  driving.
- **`yaw_goal_tolerance` tightened 0.5 → 0.15 rad** (`src/nav_fleet/config/nav2_params.yaml`):
  needed for home-pose squareness — Mike observed the robot arriving home visibly
  off-heading (nosed left) even though the old 0.5 rad (~29°) tolerance called it arrived.
  0.15 rad (~8.6°) is what makes Mission 2's home-arrival photo actually match the reference
  pose (see `HOME_PAIR_MAX_DIFF` in `tools/mission2_harness.py` for why photo similarity
  alone can't police this).
- **stage-4-hil runs ONLY the deployment mission** — the day orchestrator
  (`tools/mission2_day.py`), invoked via `scripts/hil_stage.sh day`. Mission 1 stays in
  stage-2 (sim regression, `tests/test_mission_run.py`); it is no longer run on hardware as
  a warm-up. `hil_stage.sh run` is now just the stack-up gate (sim + Nav2, no mission, no
  retry) — a mission failure must surface RED, so all harness-level whole-mission retries
  were removed (the in-process cold-goal retry above is the only retry left anywhere).
- **GUI-watched Mission 2 day, the command sequence:** bring the HIL stack up with
  `scripts/hil_stage.sh run`, view it with the scrubbed-env `gz sim -g` recipe above (the
  snap/glibc GUI-crash workaround), then run `DAY_HOLD_S=10 scripts/hil_stage.sh day` — the
  env var reaches `tools/mission2_day.py --hold-s` and keeps the robot in place after the
  final red run so an observer sees an unambiguous "done" instead of the process exiting
  mid-frame.
- **`hil_stage.sh sync` works only with PUSHED shas** (`git fetch origin <sha>` of an
  unpushed commit fails "not our ref") — and the Jetson's local `main` only advances via
  `restore-checkout`, which fast-forwards since d3bb66e (2026-07-19; before that it sat on
  week-old code and silently invalidated a bare-metal bug repro). Manual Jetson runs:
  sync to `$(git rev-parse origin/main)`, and verify with `git log -1` on the Jetson.
- **A "CI-exact" local HIL run must export `POWER_MODE_ID=0` (15W) for the run/day steps.**
  ci.yml's stage-4 builds at 25W then drops to 15W for the mission (deployment power,
  2026-07-14); `hil_stage.sh`'s default is 1 (25W) — a full local day at the default
  silently tests a faster Jetson than CI does (this masked the 15W axis during the
  2026-07-19 yellow-bug forensics).
- **Container-mode HIL image tag: verified locally before the day starts, since S17 Piece
  2's container preflight (`JetsonExecutor._require_image_local`, `tools/mission2_day.py`).**
  The sign-off false start hit this: a wrong `HIL_IMAGE` tag → GHCR pull denied → `docker
  run` dies in ~2s → looked exactly like three silent mission failures with no clue why.
  Now `JetsonExecutor.__init__` SSHes a `docker image inspect` check before any mission
  runs and raises one loud error naming the missing tag. **Tag gotcha (the root cause):**
  CI's `pull_request` builds tag the image with the synthetic MERGE-commit sha
  (`GITHUB_SHA`), NOT the branch head sha — a manual container-mode run must read the real
  tag from the CI run's env or `docker images` on the Jetson, never construct one from
  `git rev-parse`.
- **The 2026-07-18 "yellow bug" is an UNREPRODUCED INTERMITTENT, instrumented not fixed:**
  post-merge stage-4 died 3/3 that night (goal-end abort → bt_navigator bond drop →
  lifecycle cascade → GraphicsMagick SIGSEGV in recovery map-load), then 2026-07-19 went
  12/12 local + 1/1 CI green at the same sha with every code suspect exonerated. Leading
  theory: accumulated Jetson uptime/load state (reboots preceded every green). Since
  d3bb66e stage-4 uploads the Jetson `nav2_hil_*.log` in the mission-evidence artifact —
  on any recurrence, pull the artifact FIRST; full dossier + forensics in
  `.superpowers/sdd/progress.md` ("FORENSICS DAY 2026-07-19"). The GraphicsMagick env
  knobs (`MAGICK_THREAD_LIMIT=1 OMP_NUM_THREADS=1`) are VERIFIED delivered to the Nav2
  processes (/proc/environ) — if the SIGSEGV recurs, the knob is insufficient, not missing.
- **A `DeclareLaunchArgument` that isn't in the returned `LaunchDescription`'s action
  list is never actually registered — but the failure only surfaces when that launch
  file is invoked STANDALONE, not when a parent composes it.** Broke CI stage-4-hil the
  same day it was introduced (2026-07-26, second-round review's `log_level` fix):
  `nav2_only_launch.py` declared `log_level_arg = DeclareLaunchArgument('log_level', ...)`
  as a local variable and used `LaunchConfiguration('log_level')` further down, but never
  added `log_level_arg` to the `return LaunchDescription([...])` list — so the argument
  was never declared in the launch context. Worked fine through `sim_launch.py` (which
  declares its OWN top-level `log_level_arg` and forwards the resolved value down via
  `launch_arguments`), so local testing through that composed path never caught it. The
  ONE place that launches `nav2_only_launch.py` standalone — no `sim_launch.py` in
  between — is `hil_stage.sh`'s `nav2_up()` (i.e., Stage 4 HIL), which is exactly where
  it broke: `[ERROR] [launch]: Caught exception in launch: launch configuration
  'log_level' does not exist`, Nav2 never came up. Lesson: when adding/fixing a
  `DeclareLaunchArgument` in a launch file that's ALSO composed by another launch file,
  test the file standalone too (`ros2 launch <file>.py` directly, no wrapper) — a
  composing parent's own declaration of the same argument name can mask a broken
  declaration in the child indefinitely.
