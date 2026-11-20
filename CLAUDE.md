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
small exercise). **At the START of a session, read the latest one back without being
asked (Mike, 2026-11-19):** what we did last time, what the issues were, what is next.
The SessionStart hook (`.claude/hooks/session_start_status.sh`) shows him the notes'
Outcome, "Open at close" and "Next (in order)" and hands them to Claude for that first
reply, so keep those three headings exactly as they are in every notes file.
**At close, also PRINT it in the chat (Mike, 2026-11-18):** per problem — the problem,
what was learned, and the code before/after (real lines, file:line). The file alone is
not the close-out.

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

## Current status — START HERE (last real work 2026-11-19)

**The floor ban of 2026-11-18 is lifted.** The motor board's stop-on-silence is proven on
the real robot, wheels up: `tools/bench_stop_on_silence.py` PASS (0.45 s), `--legacy-t13`
FAIL as predicted, and `kill -9` on `esp32_driver` during a real mission stopped the
wheels in 0.33 s. Repeat after any firmware update or change to how motion is sent.

**2026-11-19 session** (full notes: `docs/sessions/2026-11-19.md`). Four full
three-trip missions on the floor. Built, tested, pushed:
- **Operator watch** (`operator_link.py`, `operator_watch` node): a run started over
  SSH pings the operator five times a second. 2 s of silence PAUSES the robot (two
  short beeps), a reply resumes it 1 s later (one long beep), 10 s more gives up (three
  low beeps) and `robot_boot.sh` ends the mission (exit 131). Pause/resume proven on the
  floor; give-up only in a no-motion dry run. Runs not started over SSH watch nobody.
- **Holds live in `esp32_driver`** (`HoldInput`): `/robot_001/operator_hold` and
  `/robot_001/obstacle_hold`. A fresh True holds the wheels; when the watcher is
  mandatory (`operator_watch_required`, `obstacle_guard_required`) silence holds too.
  Nav2 is never told and carries on when the hold is released.
- **Final heading at home: 16-31 deg -> 5-16 deg** with `FollowPath.max_angular_accel:
  10.0` (RPP clamps the spin command to measured rate +/- accel*dt; this base turns
  faster than told, so the default dragged the command up). Still peaks at 1.3-1.5
  rad/s for 0.5 commanded on 180 deg spins: needs closed-loop turn rate in the driver.
- **Ball detection (A4):** the detector boxed every matching pixel, and the wood floor
  is inside the yellow band ("yellow ball 4 cm away" with no ball). A camera profile
  may now carry a `shape:` section: only the largest ball-shaped blob counts.
  `hsv_realcam.yaml` is the OAK front camera, measured in evening room light at four
  distances; `robot_boot.sh` uses it. `hsv_gazebo.yaml` has no `shape:`: sim unchanged.
  **NOT yet run on the robot.**
- **Obstacle guard (step 6a)** (`path_guard.py`, `obstacle_guard` node): holds the
  wheels for 3+ lidar returns within 0.25 m of the bumper in the direction of travel,
  releases after 1 s clear; one low beep. On for every mission. Replayed on recorded
  runs: 16 clean trips, zero holds; the 2026-11-18 dresser run, held 2.7 s before
  contact. **NOT yet run on the robot.** Does not go around, back away, or guard spins.
- `ROBOT_BOOT_NAV2_PARAMS=<file>` mounts a Nav2 params file over the image's for one
  run (tuning without a 20-minute image build).
- **WiFi:** the Jetson's adapter (`rtl88x2ce`) hops between the router's three radios
  by itself, about 2.4 s of silence each time; pinning the band in the NetworkManager
  profile did not stop it. This is why the watch pauses instead of aborting.
- **Battery:** start line stays 10.5 V (Mike). A 10.75 V start sagged to 9.63 V
  (critical, motion refused, resumed 10 s later). Log: `~/fleet-ci-data/battery_log.csv`.

**Repo state at close (2026-11-19):** code is `d4ffd91`, pushed (CI run `44666459134`
green, all stages incl. the Jetson); the Jetson's checkout and image match. The closing
docs commit after it is LOCAL ONLY until Mike asks for a push. Robot on its charger, Ethernet in.
Evidence under `reports/` (gitignored): `robot_boot_20261119_*`, `camera_cal_20261119/`.

**Next session, in order:** (1) nav-only run with a box >= 25 cm tall: trip 1 clear,
trip 2 box ahead (stop, beep; remove, drive on); (2) first real ball reaction: reactions
on, yellow then red near the marker; (3) **a simulated box test** (Mike moved it up):
nothing in sim or CI puts anything in the robot's way, because the guard and the hold
live in the real driver layer; add a box scenario to Gazebo, run `obstacle_guard` on
the sim scan with a stand-in that applies its hold to sim commands; needs no robot and
is the bench for 6c/6d; (4) step 6b, act on a slip verdict; then 6c back away, 6d go
around (re-plan mid-leg), 6e guard spins; (5) operator-watch give-up in a real mission
(do not time it from a piped log: `tr` buffers); (6) closed-loop turn rate.
Also open: `robot_boot.sh` started with no terminal does not shut down cleanly (how
`robot-mission.service` starts it) and exits 0 when every trip fails; battery "critical"
does not latch; gyro vs lidar heading 9-13 deg apart after several spins. Before a floor
run, ask Mike to leave Claude Code's auto mode (it refuses the launch).

**2026-11-18 session, in brief** (`docs/sessions/2026-11-18.md`): the home error was
the borrowed map (made-up hallway, home pose 0.6 m off); the robot's own map fixed it
(home error 2-11 cm). Mapping drive = `scripts/robot_map_drive.sh`, built offline with
`scripts/build_map_from_bag.sh`; the map is NOT in git (a floor plan of a real home):
`~/fleet-ci-data/maps/bedroom_real.{yaml,pgm}` on the Jetson, copy in `reports/maps/`.
Wheel-slip detection (`scan_motion.py`, `slip_monitor`, `tools/slip_replay.py`),
observe-only. Battery read and enforced. Then the Jetson lost power mid-spin on a flat
pack and the robot could not be stopped: T:13 never re-armed the board's timer.

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
  occludes 46-123 deg raw; nothing occludes dead ahead. Lidar scan plane is about 18 cm
  above the floor (tape, 2026-11-19; the URDF says 22.5): a 7.8 cm croquet ball is under it. The OAK camera the stack uses
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
- **A pipe into a file is not live.** `ssh ... | tr -d '\r' > log` block-buffers: a
  script timing actions from that log acts tens of seconds late (2026-11-19, every
  deliberate ping cut missed its leg). Use `stdbuf -oL` or no filter.
- **When a watchdog trips, run an independent observer beside it** before deciding
  which of the two is wrong (2026-11-19: one false stop was the watch, the next was a
  real 2.4 s WiFi outage). And check behaviour, not configuration: a stored setting is
  not an obeyed one.
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
- Bringing up ANY physical robot (the portable lessons from this one) —
  `bringing-up-a-robot` skill, user-level (`~/.claude/skills/`), not in this repo
