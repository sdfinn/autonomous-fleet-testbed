# autonomous-fleet-testbed — Claude Code Context

## Project
Open-source CI/CD-native fleet simulation testing framework for autonomous robots.
Session plans and the release roadmap are tracked in internal planning docs
(`planning/`, gitignored — not part of this public snapshot); this file captures the
durable technical context and gotchas that survive across sessions.

**History lives in `docs/claude-history.md`** — a verbatim snapshot of this file as of
2026-11-14 (full session narratives, superseded "NEXT SESSION" blocks, long-form gotcha
write-ups with the evidence behind them). This file keeps only the current status and
the durable rules. When a rule below says "see history," grep that file for its
keyword. Keep this file under ~40k chars: when a session's write-up is done, append the
long version to the history file and leave a short summary here.

**Session notes (since 2026-11-14, Mike — mirrors wayfarer):** every session
closes with `docs/sessions/YYYY-MM-DD.md` — each item written as issue → how found →
fix (code excerpt + file:line) → verified → lesson, plus an "Open at close" / "Next"
list and a "Learning — guided reading" section (file + line ranges, what to notice, a
small exercise). At the START of a session, offer to re-show the latest one.

**Releases relabeled 2026-07-17: numbers now = execution order.** The agentic &
alignment layer is **R2** — docs/notes older than 2026-07-17 saying "R4" mean today's
R2. **Ladder cut from 5 releases to 3 on 2026-07-28** (source of truth:
`planning/Releases2Plus.md`): R1 Foundation (ends at `r1-complete`) → R2 Agentic &
Alignment Layer + Real Onboard Autonomy → R3 Fleet & Input Expansion, Real SLAM, and
Autonomy & Perception. The former R4 (Autonomy & Perception) and R5 (Self-Testing
Fleet) are no longer standalone releases — their content was folded into R3 and the
long-range ideas doc. Drone CUT (revivable with a written reason).

**Sister project:** `~/wayfarer` (private, sim-only, Isaac Sim, "Project Luna";
named `synthetic-fleet` until 2026-11 — older docs/notes use that name)
— a deliberate split from this repo with a two-way lessons-learned relationship. As of
2026-09-09 it switched `bt_navigator` to `navigate_to_pose_recovery.xml` and tuned
AMCL recovery params — directly relevant to this repo's open collision/recovery gap
below; read those commits before designing that fix.
**`~/wayfarer/docs/transfer/`** holds notes written there FOR this repo (sim findings
that may apply to the Rover). `ls` it when debugging a nav/doorway/costmap/harness
issue here; treat each as a sim-only hypothesis to verify against this repo's code.
First note (2026-11-15, doorway): this repo's `tools/mission2_day.py`
`_judge_and_log_leg` ignores the mission's own `ok` flag, so a failed navigate leg
can still be judged PASS (verified true here 2026-11-16; not fixed).

## Current status — START HERE (last real work 2026-11-18)

**SAFETY, READ FIRST: the robot must not drive on the floor until
`tools/bench_stop_on_silence.py` prints PASS on the real robot, wheels off the ground.**
On 2026-11-18 the Jetson lost power mid-spin (flat pack, 9.17 V) and the motor board
kept executing its last command; the robot spun until Mike cut power. Cause, from the
firmware source: only wheel-speed commands (T:1) re-arm the board's stop-on-silence
timer, and the driver sent T:13, which leaves it disarmed 3 s after power-on. The driver
now sends T:1 and sets the timer to 500 ms at start-up — tested in software, NOT yet
proven on the robot.

**2026-11-18 session** (full notes: `docs/sessions/2026-11-18.md`).
- **Home error explained and fixed.** The borrowed `living_room.yaml` has an accurate
  bedroom but a made-up hallway, and its home pose is ~0.6 m from where the robot is
  put down. On the robot's own map: 3 of 3 round trips, home error 2-11 cm (was 55 cm),
  believed vs true pose within 1-5 cm at every stop. Two more clean trips with the
  hallway runner down.
- **The robot's own map (A3 done).** Mapping drive = `scripts/robot_map_drive.sh`
  (drivers + bag + hold-to-move `key_teleop`); built offline with
  `scripts/build_map_from_bag.sh`, in the mission frame (drive starts on the home spot
  = the configured home pose, so no waypoint or AMCL seed changes). **Not in git** (a
  floor plan of a real home): `~/fleet-ci-data/maps/bedroom_real.{yaml,pgm}` on the
  Jetson, mounted by `robot_boot.sh`; workstation copy in `reports/maps/`.
- **Wheel-slip detection** (`nav_fleet/scan_motion.py`, `slip_monitor` node,
  `tools/slip_replay.py`): wheels vs scan-to-scan motion. Fires ~1 s into the
  2026-11-17 slip and at the dresser contact; silent on clean trips. Observe-only.
- **Battery** is now read: `/robot_001/battery_voltage`, a state line in the driver
  log, motion refused when critical (<9.9 V), and `robot_boot.sh` starts no mission
  unless the pack reads `ok` (>=10.5 V; `ROBOT_BOOT_IGNORE_BATTERY=1` overrides).
- **Final heading at home overshoots** by up to 37 deg (the end-of-leg spin runs at
  1.2-1.5 rad/s and coasts through the goal). The robot knows; not fixed.
- Also: gyro offset now learned during teleop; `scripts/ensure_nav_fleet_built.sh`
  rebuilds the Jetson's bare-metal install when a new node has no launcher.

**Next session, in order:** (1) charge fully, re-seat tyres, compare the logged voltage
with a multimeter; (2) **bench test wheels-up: `tools/bench_stop_on_silence.py` -> PASS
and `--legacy-t13` -> FAIL**, then a real `robot_boot.sh` start on the stand with
`kill -9` on `esp32_driver`; (3) one attended nav-only run (motion unchanged with T:1?);
(4) a remote stop that works when WiFi drops but the Jetson lives; (5) final-heading
overshoot; (6) collision avoidance/recovery + what a slip verdict should do (test case:
the dresser bag in `reports/robot_boot_20261118_navonly/`); (7) A4 colour calibration,
mast-camera recording. Intermittent stage-2 near-goal stall is still real and unfixed.

**2026-11-17 session, in brief** (`docs/sessions/2026-11-17.md`): `robot_boot.sh`
records a bag on every run (`~/fleet-ci-data/robot_boot_logs/bag_<ts>/`;
`ROBOT_BOOT_NO_BAG=1` skips) and stops on Ctrl+C / SIGTERM / SIGHUP (container, then
bag, then drivers) — but note a DROPPED link sends no SIGHUP, the session just hangs
open. USB webcam on the mast explored (`docs/cameras.md`). Wheel slip at the runner's
edge found (the reason slip detection exists).

**2026-11-16 session** (full notes: `docs/sessions/2026-11-16.md`; previous:
`docs/sessions/2026-11-14.md`). Stage-4 CI hang fixed and pushed (`a6a5da6`, run
`43990188953` fully green). Then two real `robot_boot.sh` runs and a long bench session
found four real-hardware causes behind "drives into a wall, then circles":
1. **Motor controller had the wrong chassis type stored** (`{"T":900,"main":3}` = UGV
   Beast on a 6-wheel UGV Rover): real speed 2.5x the command, odometry echoing the
   command, motor direction reversed. Now `main:2` (saved on the ESP32; firmware is
   `ugv_base_ros` 0.96, NOT `ugv_base_general`). The August driver sign flips were a
   compensation for this and are removed.
2. **EKF ignored the gyro** (`angular_velocity_covariance[0] = -1` means "ignore" to
   `robot_localization`). Now 1e-4; resting gyro offset is learned and subtracted.
3. **Lidar scan was published unrotated** (true front = raw 269 deg, not 285).
   `scan_masker` now rotates it; the stale 268-277 "antenna" mask (dead ahead) is gone.
4. **`MISSION2_IGNORE_REACTIONS` never reached the container** (`robot_boot.sh` now
   passes it).
Result: run 2 made one trip to the marker and back but stopped ~0.55 m from home (the
pose estimate jumped right after "Reached the goal"); the second attempt started from
there and hit the dresser. No bag was recorded for run 2, so that is undiagnosed.

(Committed and pushed as `4022c64`, CI run `44003193932` green.)

**Where things stand:** the real physical robot (Waveshare UGV + Jetson Orin Nano)
is mid bring-up. Full sim + HIL CI pipeline is green. The real-robot production path
(`scripts/robot_boot.sh`: driver layer bare-metal + Nav2/EKF/ball_detector/
mission_runner in the arm64 container) boots, localizes on its own map and completes
the nav-only mission with a home error of a few centimetres (2026-11-18) — but has no
proven stop when the Jetson dies (fix written, bench test owed), no collision avoidance
or stuck recovery, and only observes wheel slip.

**2026-08-12/13 session, in brief (several conclusions SUPERSEDED 2026-11-16 — see above)** (full detail: history, "first real
`robot_boot.sh` production-path test"):
- **AMCL localization bug — FIXED, live-confirmed.** `esp32_driver` was publishing raw
  QMI8658 LSB counts as if SI units; garbage gyro `vyaw` scrambled EKF yaw (X/Y were
  fine — `config/ekf.yaml` fuses only wheel `vx` + gyro `vyaw`). New
  `scale_imu_raw()` in `esp32_protocol.py`. `ACCEL_SENSITIVITY_LSB_PER_G = 8192`
  (high confidence, cross-checked against gravity — vendor doc's ±16g default is
  wrong at runtime); `GYRO_SENSITIVITY_LSB_PER_DPS = 16` (vendor default, NOT
  verified — needs a hand-rotated calibration). IMU covariances now `-1` (REP-145
  "not populated") instead of all-zero. No bias/offset correction yet.
- **`MISSION2_IGNORE_REACTIONS` env var** (`mission_runner._detection_cb`) suppresses
  ball reactions so navigation can be tested in isolation from the HSV false-positive
  bug.
- **2026-08-12 stage-4-hil "regression" (CI run `31558423291`, frozen TF / "Initial
  robot pose is not available")** did NOT reproduce on two controlled clean-Jetson
  runs (DEBUG and info level). Best-evidenced cause: orphaned process/DDS state from
  hours of live debugging, not code. Treat as functionally resolved; re-add
  `log_level:=debug` in `container_entrypoint.sh`'s `mission` branch if it recurs.
- **Real gap exposed: NO working collision-avoidance or stuck-recovery on the real
  robot, by design.** `FollowPath.use_collision_detection: false`; BT is
  `navigate_simple.xml` (no recoveries) because `behavior_server` spin/backup fails
  100% ("Pose Goes Off Grid"); `collision_monitor`'s polygon is a deliberate 2cm no-op
  (a real-sized one silently self-locked). Each, when enabled, caused a permanent
  deadlock worse than the collision it prevented. Robot drove into a wall, then
  circled; Nav2 progress checker aborted legs at ~60-74s. The map is NOT the suspect
  (same map passes in sim/HIL — Mike's correction).
- **Scan mask edge leak:** closest-obstacle readings clustered at 45.7-46.0° and
  123.3-124.1° — right at the mast mask edges (`scan_masker.py`; the 268-277 sector
  was removed 2026-11-16). Edge leak itself not re-checked.

**Repo state:** the August IMU fix / `MISSION2_IGNORE_REACTIONS` commits were pushed
2026-11-14; the Jetson's checkout was reset to `15f9371` by that day's CI sync. Ad-hoc diagnostic scripts
(`robot_boot_debug.sh`, `odom_isolation_test.sh`, `amcl_tf_test.sh` + `tf_watch.py`,
`raw_imu_test.sh`) live only in `~/robot_boot_debug/` on the Jetson. Failure bags +
photos are in `reports/` on the workstation (untracked).

**Older punch list (August; items 1 and 5 updated 2026-11-16 — the order above takes precedence):**
1. **Mast/mask: mostly resolved 2026-11-16** — true front re-measured (269 deg raw),
   scan rotated, stale antenna sector removed. Still open: whether to restrict to the
   forward 180 deg at all, and the mast-edge leak.
2. **Collision avoidance + recovery (the real priority).** Root-cause
   `behavior_server`'s "Pose Goes Off Grid" (or replace recovery), THEN re-enable
   collision detection — one capability at a time, real test at each step. Don't just
   flip `use_collision_detection: true` (known deadlock). Check `planning/
   Release1Todo.md` and wayfarer's 2026-09-09 recovery commits first.
3. **Live pre-motion lidar readout** — prominent forward-arc nearest-obstacle range
   before a goal is dispatched (human or automated pre-flight check), not forensic bag
   analysis after. Plus an open question: does sim's turn segment also pass close to
   a wall, and if so why does sim cope? Compare directly.
4. Decide whether the Jetson's ad-hoc diagnostic scripts belong in `scripts/`.
5. ~~Gyro scale calibration~~ DONE 2026-11-16 (verified by a 360 deg hand turn).
6. Push timing: CI's `stage-4-hil` runs `use_sim_time=true` and never exercises the
   bare-metal driver path, so a push proves nothing about the IMU fix — only a real
   `robot_boot.sh` run does.
7. **A4** real-camera HSV calibration (`hsv_realcam.yaml` doesn't exist;
   `hsv_gazebo.yaml` stand-in false-positives on the red desk — reproduced twice;
   before-photos in `reports/robot_boot_20260813_postfix/`).
8. **A3** real SLAM map (`living_room.yaml` is the right room but not this robot's own
   SLAM output; not ruled out as a contributor).

**Older open items (still true):** driver-readiness 60s timeout never timed on a real
cold boot under `robot-mission.service`; BR-03 (recovery) has no test, so stage-0's
traceability gate keeps `continue-on-error: true`; `test_nav_runner.py` rclpy-teardown
ordering bug (see Gotchas); Release 1→2 branching/`r1-complete` tag; self-hosted-runner
CI docs.

## Development workflow — tier 1 first

**Primary dev loop (x86 bare metal — flush bugs here before touching CI):**
```bash
colcon build --symlink-install          # ~1s
source install/setup.bash
python -m pytest tests/ -v \
  --ignore=tests/test_ros2_contracts.py \
  --ignore=tests/test_navigation.py \
  --ignore=tests/test_mission_run.py \
  --ignore=tests/test_nav_runner.py
ros2 launch nav_fleet sim_launch.py     # Gazebo + Nav2 locally
```
x86 isn't the robot's target OS but finds 90% of bugs at ~1s build vs 23 min QEMU.
Commit to CI only when the x86 pipeline is clean.

## Environment
- Ubuntu 24.04 bare metal (dual boot with Windows 11)
- ROS2 Jazzy + Gazebo Harmonic + CycloneDDS
- Python virtualenv: `~/fleet-env`; colcon workspace: `~/autonomous-fleet-testbed/`
- `ros-jazzy-robot-localization` and `ros-jazzy-vision-msgs` required on BOTH the
  workstation and the Jetson.
- Jetson: JetPack 7.2, CUDA 13.2, Ollama (`moondream:1.8b`) for the VLM canary.

## Key Commands
```bash
# New terminal — .bashrc auto-sources ROS2, CycloneDDS, fleet-env, workspace overlay.
colcon build --symlink-install
ros2 launch src/nav_fleet/launch/sim_launch.py

# Unit tests
python -m pytest tests/ -v --ignore=tests/test_ros2_contracts.py \
  --ignore=tests/test_navigation.py --ignore=tests/test_mission_run.py \
  --ignore=tests/test_nav_runner.py

# Run a mission (sim must be up)
python -m nav_fleet.mission_runner mission1

# Traceability gate
python tools/check_traceability.py requirements/traceability.yaml tests/ \
  --profile robot_profiles/jetson_ugv_pt.yaml

# Coverage — stage-1 subset (no Gazebo). .coveragerc scopes to tools/ +
# src/nav_fleet/nav_fleet/. Combined stage-1+2 only exists in CI's coverage-report
# job (pure-local `coverage combine`, no third-party site); trend on dashboard's
# Coverage tab, browsable HTML in the coverage-html-<run> artifact.
python -m pytest tests/ --ignore=tests/test_ros2_contracts.py \
  --ignore=tests/test_navigation.py --ignore=tests/test_mission_run.py \
  --ignore=tests/test_nav_runner.py -k "not integration" \
  --cov=tools --cov=src/nav_fleet/nav_fleet --cov-report=term-missing

# Dashboard
streamlit run dashboard/app.py

# arm64 Docker build (Tier 2 — only after Tier 1 is clean)
docker buildx build --platform linux/arm64 \
  --tag ghcr.io/sdfinn/autonomous-fleet-testbed:latest --load .

# HIL / real robot
scripts/hil_stage.sh smoke <sha>     # attended bench smoke test (Mike places ball)
scripts/robot_boot.sh                # real production mission path
```

## Architecture (durable facts)
- **One container, two consumers.** Nav2/EKF/`ball_detector`/`mission_runner` run in
  the arm64 image via `scripts/container_entrypoint.sh`, identically on HIL and the
  real robot, differing only by env vars (`use_sim_time`/`hsv_config`/`map`/
  self-report vs judged). Driver layer (`drivers_only_launch.py`: esp32_driver,
  lidar, camera, scan_masker, camera_relay, robot_state_publisher) and Ollama run
  bare-metal on the Jetson. HIL judging/ball placement (`tools/mission2_harness.py`,
  Gazebo transport) stays workstation-side; the real robot self-reports PASS/FAIL.
- **HIL always runs `use_sim_time=true`** — it is structurally blind to the
  real-driver code path (frames, RSP, IMU scaling, sign conventions). Only a real
  `robot_boot.sh` / `hil_stage.sh smoke` run validates that path.
- **Physical calibration facts for this unit** (bench-measured 2026-11-16 unless dated):
  ESP32 firmware `ugv_base_ros` 0.96; chassis type MUST be `main:2` (UGV Rover) —
  `esp32_driver` checks it at start (`T:602`) and refuses to drive otherwise; fix with
  `{"T":900,"main":2,"module":0}` (persists in flash). With that set, +X is forward
  and +Z is left: NO sign flips in the driver. Speed and odometry are true to ~5%.
  Skid-steer scrub: real turn rate ~1/2.8 of wheel-implied (`angular_cmd_gain: 2.8`,
  spins on the spot only, one floor). Gyro: 16 LSB/dps verified (364 deg for a 360 deg
  hand turn), negative = right turn, resting offset ~0.26 deg/s removed in the driver.
  Lidar true forward = raw bearing 269 deg (`scan_masker` `forward_bearing_deg`); mast
  occludes 46-123 deg raw; nothing occludes dead ahead. The OAK camera the stack uses
  is fixed to the chassis front (not on the pan-tilt). Vendor lidar frame `base_laser`
  is rewritten to `lidar_link` by `scan_masker`. Real footprint 0.253 x 0.231 m;
  `robot_radius: 0.24`. Gimbal T:133: pan -=left/+=right, tilt -=down/+=up (seen
  2026-11-17); the serial port is exclusive, so not while `esp32_driver` runs. Drive:
  front and rear wheel pairs are motorized, the centre pair rolls free; the board
  reports ONE speed per side. A second, USB camera sits on the pan-tilt (`docs/cameras.md`).
  Motion commands MUST be T:1 (left/right wheel speeds), never T:13: only T:1/T:11
  re-arm the firmware's stop-on-silence timer (`uart_ctrl.h`; source at
  `waveshareteam/ugv_base_ros`, folder `ROS_Driver/`). The timer (T:136) is not kept
  in flash; the driver sets 500 ms at start-up. Pack voltage is `"v"` in T:1001, in
  hundredths of a volt (3-cell pack: 12.6 V full; 9.17 V read flat on 2026-11-18).
  Real map and home: `~/fleet-ci-data/maps/bedroom_real.yaml`, home spot = configured
  home pose (-1.276, 1.2, 90 deg); bedroom door 0.75 m wide, dresser just right of it.
- **Per-robot TF is namespaced:** subscribe to `/robot_001/tf`, not `/tf`.
- `local_costmap.global_frame: "odom"` is explicit; `nav2_only_launch.py` uses an
  `OpaqueFunction` to inject `use_sim_time` into the params YAML because
  `nav2_bringup`'s `bringup_launch.py` passes `param_rewrites={}`.

## Directory Layout
- `src/nav_fleet/` — ROS2 package; Nav2 launch gotchas in `src/nav_fleet/CLAUDE.md`.
- `tools/` — telemetry DB, reports, harness, coverage log; see `tools/CLAUDE.md`.
- `dashboard/app.py` — Streamlit dashboard; see `dashboard/CLAUDE.md`.
- `scripts/` — `hil_stage.sh`, `robot_boot.sh`, `container_entrypoint.sh`,
  `regen_cyclonedds_config.sh`, install scripts, Isaac Sim scripts
  (`scripts/CLAUDE.md`).
- `requirements/` — traceability matrix and specs. `docs/` — architecture notes,
  `claude-history.md`, runbooks, plans/specs under `docs/superpowers/`.
- `.github/workflows/ci.yml` — stages: 0 traceability, 1 quality, 2 gazebo, 3 arm64,
  4 hil (Jetson), 5 reports, coverage-report. (`stage-4-isaac` retired Session 16;
  pre-2026-07-10 docs use old stage numbering.)
- `RealRobotStartup.md` — real-robot bring-up runbook (Part A one-time, Part B daily).
- `reports/` (gitignored, whole directory) — run bags, logs, photos, analysis scratch;
  `reports/maps/` holds the workstation copy of the real map.
- `planning/` (gitignored) — Release1Todo.md, Releases2Plus.md.
- `/home/mike/BC/isaac_project` (outside repo) — reference: real HSV detector
  (`src/behavior_controller.py`). Its `MasterBrief.md` describes a YOLO+ArUco design
  that was never built — trust the code over it.

## Gotchas (rules; evidence and full stories in `docs/claude-history.md`)

**Process / workflow**
- **Shared machine.** This workstation is the self-hosted CI runner AND a dev box
  that may run `wayfarer`'s Gazebo on the same `/robot_001` namespace. Before
  any local Gazebo/Nav2 run: `gh run list` (a push auto-starts CI here, whose sweep
  step pkills local sims) and `pgrep -fa "gz sim|robot_state_publisher"` checking
  the PROJECT PATH. Never kill another project's session unasked.
- **Orphan processes poison later runs** — Gazebo, bare-metal driver/Nav2 stack, and
  likely container/CI HIL too. Sweep (`ekf_node`, `static_transform_publisher`,
  `component_container_isolated`, `parameter_bridge`, …) before trusting a "clean"
  test. Standing TODO: add a pre-flight sweep to the container/CI HIL path.
- **Code inside the container runs from the image's installed copy**
  (`/ros2_ws/install/.../site-packages/`, plain non-symlink build). Scp to the
  Jetson's native checkout only reaches bare-metal (driver layer). For container
  code, bind-mount over the installed path and verify inside a container first.
- **A stop mechanism that has never been seen to work is an assumption.** Test "the
  computer is gone" by taking the computer away, wheels up, before floor runs — and
  after any firmware update or change to how motion commands are sent (2026-11-18).
- **The Jetson's bare-metal install is a `--symlink-install` build and sync does not
  rebuild.** Edited files arrive via symlinks; a NEW console script needs a build
  (`scripts/ensure_nav_fleet_built.sh`, called by the robot scripts).
- **`ros2 launch x.py arg:=''` is a malformed argument** and exits at once — omit the
  argument to get an empty default.
- **slam_toolbox rejects scans whose reading count varies** (the LD19 gives 500-505);
  `tools/map_from_bag.py` resamples. Its `map_start_pose` does nothing in mapping mode.
- **A hard power-off leaves the bag unfinalized:** `ros2 bag reindex -s mcap <dir>`
  recovers all but the last ~15 s.
- **Prefer SIGINT teardown over `docker stop`** when a rosbag may be recording —
  `docker stop` leaves an empty, unfinalized mcap.
- **`hil_stage.sh sync` self-heals** (`git reset --hard FETCH_HEAD && git clean -fd`)
  — anything uncommitted in the Jetson's `~/autonomous-fleet-testbed` will be wiped.
  `.gitignore` covers `reports/*_container_*.log`; before trusting "it's gitignored,"
  grep what filenames scripts actually write.
- **Verify behaviorally, not textually.** A function whose own diff is clean can
  still change behavior via a shared branch it dispatches into (2026-08-11 C1).
- **Prefer a large, direct visual result over telemetry interpretation** for any
  hardware sign/convention finding. Don't over-read camera CONTENT as camera POSITION.
- **Read vendor source/launch files completely at bring-up**, not after hours of
  debugging (frame_ids, transforms it publishes, param defaults). Trust physics over
  vendor docs when they disagree.
- **When a live observation contradicts a computed number, re-measure the exact
  boundary the observer describes** before arguing.
- **When a symptom recurs after a verified fix, pull the full system journal** around
  the failure — two causes can produce identical log lines.
- **Spot-check bucketed live-topic summaries against raw samples.**
- **Grep DEBUG Nav2 logs, never read them** (hundreds of thousands of lines); use
  Python, not `mawk`, for timestamp-windowed extraction.

**Testing / CI**
- Any test file importing `rclpy` at module level must be `--ignore`d in
  `stage-1-quality` (bare ubuntu, no ROS2). Has bitten repeatedly.
- **`test_nav_runner.py`'s `_ros` fixture shuts down rclpy unconditionally** — if it
  runs before `test_navigation.py`/`test_mission_run.py` (alphabetical discovery
  does this), they error with `NotInitializedException`. CI orders the files
  explicitly; locally pass them in that order. Not fixed.
- Under pytest here, new `logging.getLogger()` loggers default to `propagate=False`
  (launch-testing plugin import side effect) — set `.propagate = True` explicitly
  (see `tools/log_setup.get_logger()`).
- Drift tests seeded with identical baseline values pass vacuously
  (`check_run()` skips zero-variance metrics) — seed real variance.
- Stage-0 traceability gate keeps `continue-on-error: true` until BR-03 has a real
  test; check occasionally that downstream stages still run.
- `ci.yml` is **CRLF** — edit only with the Edit tool or GNU `sed -i`, never a Python
  read/write round-trip. `scripts/**` must stay in the `dorny/paths-filter` list.
- `actions/upload-artifact@v4` silently skips dotfiles; coverage data files record
  absolute paths — `.coveragerc`'s `[paths]` remaps hosted vs self-hosted prefixes.
  When a CI step fails opaquely, `gh run download` the real artifacts and reproduce.
- GitHub's Summary tab mis-caches job summaries (platform bug, not ours) — real
  fleet status goes to console logs. The stage-1 "Canary summary line" step is kept
  deliberately.
- Public repo with self-hosted runners: fork PRs require approval for all outside
  collaborators; `pull_request` (not `_target`), read-only `GITHUB_TOKEN`.

**ROS2 / DDS / networking**
- Gazebo Harmonic is `gz sim`; URDF topics use `/robot_001/`; OGRE2 needs `<diffuse>`.
- Launch files use `pathlib.Path(__file__)...` instead of `get_package_share_directory`
  (no `colcon-ament-python`) — intentional.
- Every `DeclareLaunchArgument` must be in the returned `LaunchDescription`.
- CycloneDDS: `scripts/regen_cyclonedds_config.sh` regenerates the interface list from
  real link state (`/sys/class/net/*/operstate`, physical NICs only via `/device`,
  Ethernet priority over WiFi) before every launch on both machines — CycloneDDS
  hard-fails on a listed-but-down interface and auto-select can pick `docker0` or the
  wrong ifindex. Large uncompressed `Image` messages need `SocketReceiveBufferSize`
  10MB + `net.core.rmem_max` raised on BOTH machines.
- Cross-machine DDS over the AT&T WiFi doesn't work (likely AP isolation / multicast
  filtering) — HIL uses Ethernet. The deployed robot doesn't need networking at all.
- Non-interactive SSH/systemd doesn't source `.bashrc` — export
  `RMW_IMPLEMENTATION`/`CYCLONEDDS_URI` explicitly for the bare-metal driver layer.
  Test interactive-shell setup with `bash -ic`, not plain `ssh host cmd`.
- Bash `&`-backgrounded jobs in non-interactive scripts ignore SIGINT/SIGQUIT — wrap
  the one backgrounding line in `set -m`/`set +m`.
- `ros2 run tf2_ros tf2_echo` hangs here — use a small rclpy `tf2_ros.Buffer` script.
- XML comments can't contain `--`; unquoted heredocs execute backticks/`$()`.

**Jetson / hardware** (more in the `jetson-hardware-notes` skill)
- `~/fleet-ci-data` can go root-owned after container runs (image has no `USER`) →
  bare-metal `PermissionError`/"readonly database". Fix with chown + setgid.
- `nvpmodel -m` can demand an interactive reboot confirmation; CI no longer calls it
  (always 25W). If needed: `echo yes | ssh ... "sudo -n nvpmodel -m <id>"` — a plain
  reboot doesn't clear its pending state.
- `jetson.local` mDNS conflicts: fixed via avahi `use-ipv6=no` and avahi waiting on
  `systemd-time-wait-sync.service` (OS config, not in git — redo on re-provision).
- Ollama: "Unsupported JetPack" install warning is a false alarm (check
  `journalctl -u ollama` for GPU offload); first inference ~45s cold — pre-warm;
  bare-metal needs `pip3 install --break-system-packages ollama`; `nvcc` needs
  `/usr/local/cuda/bin` on PATH.
- In-mission delays on Jetson are not Docker-exec latency — reproduce bare-metal
  first. `jetson_clocks` null results only rule out DVFS if clocks weren't already
  at max.

**Environment / tooling**
- `requirements.txt` is a full pip freeze — CI uses `requirements-ci.txt`.
- DB path env var `FLEET_DB` (default `~/fleet-ci-data/fleet_runs.db`, owned by
  `tools/telemetry_logger.DB_PATH`); `FLEET_TELEMETRY=off` skips writes.
- `.bashrc` exports don't reach Claude Code's non-interactive Bash (early-return
  guard). For `ANTHROPIC_API_KEY`: `eval "$(grep '^export ANTHROPIC_API_KEY'
  ~/.bashrc)"` — never print it. `AGENTIC_BACKEND=ollama`, `OLLAMA_MODEL` switch
  `tools/agentic_loop.py` to a local model.
- Claude Code's Bash `/tmp` is isolated from Mike's real filesystem — hand-off files
  go inside the repo (e.g. `reports/`).
- `SessionStart` hook plain stdout reaches only Claude; user-visible output needs a
  JSON `systemMessage` (`.claude/hooks/session_start_status.sh`).
- When a path constant flips relative↔absolute, grep every consumer of it
  (photo pull-back regression, 2026-07-22).

## See also
- Full history: `docs/claude-history.md`
- Nav2 launch gotchas — `src/nav_fleet/CLAUDE.md`
- Isaac Sim gotchas — `scripts/CLAUDE.md`
- Isaac GUI nav-test procedure — `isaac-gui-nav-test` skill
- Jetson hardware gotchas — `jetson-hardware-notes` skill
