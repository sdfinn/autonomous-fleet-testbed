# autonomous-fleet-testbed — Claude Code Context

## Project
Open-source CI/CD-native fleet simulation testing framework for autonomous robots.
Session plans and the release roadmap are tracked in internal planning docs
(`planning/`, gitignored — not part of this public snapshot); this file captures the
durable technical context and gotchas that survive across sessions.

**Goal and vocabulary (Mike, 2026-11-22): `docs/terminology.md`, used in both projects,
in full, no short forms.** Goal: the robot boots and loads everything, can then carry
out any mission, given as a mission script or (preferred) as a request in plain
English to the brain; the robot makes the judgment. Terms: reflexes; state estimation
(EKF, AMCL); navigation; **Nav2's behavior tree** (both projects); detector; describer
(`moondream` on Ollama); **skills** (hard-coded abilities) and the **plan** (which
skill next); mission logic = a **mission script** (here) or **the mission's behavior
tree** (wayfarer only); **brain = a language model on Ollama that chooses the plan and
makes judgments, built in neither project yet**. Never bare "model", "decision tree",
"the tree" or "mission tree"; never "brain" for hard-coded mission logic. Goals go
down, events come up (`docs/goals-and-events.md`, milestones M1-M6).

**History lives in `docs/claude-history.md`** — a verbatim snapshot of this file as of
2026-11-14 (full session narratives, superseded "NEXT SESSION" blocks, long-form gotcha
write-ups with the evidence behind them), plus sections "Moved from CLAUDE.md
2026-11-22" and "... 2026-11-23" (older session paragraphs). This file keeps only the current status and
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

**Releases** (source of truth: `planning/Releases2Plus.md`): R1 Foundation (ends at
`r1-complete`) -> R2 Agentic & Alignment Layer + Real Onboard Autonomy -> R3 Fleet &
Input Expansion, Real SLAM, Autonomy & Perception. Docs older than 2026-07-17 saying
"R4" mean today's R2. Drone CUT (revivable with a written reason).

**Sister project:** `~/wayfarer` (private, sim-only, Isaac Sim, "Project Luna";
named `synthetic-fleet` until 2026-11 — older docs/notes use that name)
— a deliberate split from this repo with a two-way lessons-learned relationship. As of
2026-09-09 it switched `bt_navigator` to `navigate_to_pose_recovery.xml` and tuned
AMCL recovery params — directly relevant to this repo's open collision/recovery gap
below; read those commits before designing that fix.
**`~/wayfarer/docs/transfer/`** holds notes written there FOR this repo (sim findings
that may apply to the Rover). `ls` it when debugging a nav/doorway/costmap/harness
issue here; treat each as a sim-only hypothesis to verify against this repo's code.
First note (2026-11-15, doorway): this repo's `tools/mission2_run.py`
`_judge_and_log_leg` ignores the mission's own `ok` flag, so a failed navigate leg
can still be judged PASS (verified true here 2026-11-16; not fixed).

## Current status — START HERE (last real work 2026-11-23)

**2026-11-23 session: item A done, item B merged, first floor runs on all of it.**
Detail: `docs/sessions/2026-11-23.md` (15 sections), `docs/detection-history.md`.
- **Floor, afternoon (`reports/robot_boot_20261123_*`):** a full Mission 2 on the merged
  code; past a box against the door jamb twice (38 cm planning circle, Mike's number;
  re-planning every second). **The first box run TOUCHED the box:** Nav2's pause to
  recover made the obstacle guard release with the box still there (it only checked
  while a speed was asked for), the robot crept 4 cm, 1 cm, 0 cm, then turned into it.
  Fixed (`path_guard.py`): a hold lasts until the zone that caused it is clear, and a
  turn on the spot is held for anything inside the circle the corners sweep + 3 cm,
  ignoring returns inside the robot's own outline (the real lidar sees the robot
  0.03 m from its center; the simulated one never does: found by REPLAYING the real
  bags through the new logic before the floor). Not yet shown on the floor against a
  box that truly blocks.
- **The robot's own messaging is on loopback** (`CYCLONEDDS_SCOPE=local`, set by
  `robot_boot.sh` for both halves; CI's Jetson stage stays on the network). The
  Jetson's WiFi address changed mid-mission again (2026-11-20, 2026-11-23) and the
  processes could no longer hear each other. PROVEN on the stand the same evening: a
  run carried on through 35 s with the WiFi switched off, no messaging error in any
  log. The operator watch still pauses/ends an attended run on link loss; Mike wants
  "carry on and keep logging" as the rule (next).
- **Mission names (Mike): one sequence for both projects, never per release**
  (`docs/terminology.md`): 1 doorway photo; 2 yellow and red; 3 green ball, front and
  back (wayfarer only); 4 is it tidy; 5 is it tidy with names; 6+ next. It is
  "Mission 2", never "Mission 2"; the rename of the tool/flag/CI names in this repo
  is proposed (mapping in the 2026-11-23 chat), not done.
- **A floor "go" means with video (mast camera) and monitoring.**
- **RF-DETR (`object_detector`) is the only detector**: real robot, local simulator,
  CI's simulator stage, CI's Jetson stage, all three smoke-test paths. The hand-written
  color detector, its two color profiles, two calibration tools and their tests are
  deleted (last commit that has them: `7996135`).
- **Where it runs.** On the Jetson: OUTSIDE the container, on the GPU (TensorRT):
  started by `robot_boot.sh` (always; not ready within 60 s = no mission) and by
  `hil_stage.sh run` (stopped by `teardown`). On the workstation: started by
  `sim_launch.py` / `sensors_only_launch.py object_detector:=true`, ONNX Runtime on
  the processor, about 70 ms a picture. The container starts no detector.
- **Needed outside the repo on the workstation (CI runner):**
  `~/fleet-ci-data/models/rfdetr-small.onnx`, and ONNX Runtime for the SYSTEM Python
  (`ros2 launch` starts nodes with `/usr/bin/python3`, not `fleet-env`):
  `/usr/bin/python3 -m pip install --user --break-system-packages --no-deps onnxruntime`
  (`--no-deps` so it cannot shadow ROS's protobuf). CI's simulator stage checks both.
- **A pretrained network finds Gazebo's plain spheres** ("sports ball" 0.73-0.94,
  0.5-2.5 m) and the real camera's color bands fit Gazebo's colors; only the distance
  constant differs (`config/detector_rfdetr_gazebo.yaml`).
- **`nav_fleet/detection.py`**: what mission logic is given about an object (class,
  confidence, kind known/hazard/unknown, bearing, distance and its source). Same
  fields and kinds as wayfarer's reader, written here, no import either way. The
  mission script reacts only to a HAZARD with a trusted distance. `OBJECTS` there is
  the table of classes missions may act on.
- **The first-drive stall in CI (six times since 2026-11-20) is FIXED: `FollowPath.stateful:
  false`.** Cause, from Nav2's source (Regulated Pure Pursuit 1.3.12) and a recording:
  the follower latched "position reached" the one time its own distance to the goal was
  under `xy_goal_tolerance` (0.144 m against 0.150), stopped driving for good, the robot
  ended 0.163 m out, the goal checker never saw it inside, and they waited for each
  other until "Failed to make progress" while the robot swung left-right on the spot.
  6 stalls in 14 first drives before, 0 in 13 after. `max_angular_accel: 10.0` only made
  it likelier. Pinned by `tests/test_nav2_params.py`. NOT yet run on the floor.
- **To make a local run behave like CI, run it WITHOUT A DISPLAY:**
  `env -u DISPLAY -u XAUTHORITY -u WAYLAND_DISPLAY <command>`. The CI service has none,
  so Gazebo renders camera and lidar in software there; with a display the graphics
  card does it and the stall above never reproduced locally.
- **`nav_runner.py` logs where the robot stood on any goal Nav2 does not complete**
  (`describe_failed_goal`): read that line first, in CI or on the floor.
- **ONNX Runtime's defaults used about 16 cores** for the detector on the workstation;
  now 8 threads, no spinning: 80 ms a picture, 5 cores (`rfdetr_backends.ONNX_THREADS`).
- **The smoke test's lidar check compares like with like** (`expected_lidar_range`:
  known distance minus the lidar's forward position minus the ball's radius, both
  modes). Simulator reads 0.656 m against an expected 0.657. The bench prompt now gives
  the distance from the robot's FRONT EDGE (24.5 inches). Bench mode not re-run.
- **Item B: cause found and fixed (merged PR #6).** The robot never went around anything for two reasons, both standard Nav2
  settings: (1) the global costmap's lidar source had no `max_obstacle_height` (Nav2's
  default 0.0 discards every point above the floor), so the planner only knew the saved
  map; (2) the one-shot tree planned once per goal. `BackUp`/`Spin` SUCCEED in the
  simulator (spawn pose, after a drive, after a costmap clear): "Pose Goes Off Grid" is
  a pose outside the behavior server's copy of the local costmap, very likely the local
  costmap's old `map` frame (fixed 2026-08-12, never re-tested). On the branch: lidar
  marking in the planner's costmap, `navigate_to_pose_recovery.xml` (re-plan every
  second; back up, wait, spin; 6 tries), 10 s stand-still limit with
  `PoseProgressChecker`, an explicit `behavior_server` section. Simulator: a box in
  open floor is driven around in 19 s; a box with no way through ends the goal in
  40-113 s with the robot clear. MERGED 2026-11-23 (`d6dc39c`) on Mike's instruction and run on the floor the same
  afternoon (first bullet above).
- **Removed switches:** `ROBOT_BOOT_SHADOW_DETECTOR`, `ROBOT_BOOT_DETECTOR`,
  `HSV_CONFIG_FILE`, `BALL_DETECTOR`, launch arguments `hsv_config` / `ball_detector`.
  `ROBOT_BOOT_RFDETR=<file>` now only names another model file.

- **Simulator harness:** attaching the Gazebo GUI PAUSES the simulation (un-pause
  command in `src/nav_fleet/CLAUDE.md`); the mission tool no longer leaves a ball
  behind when a mission dies and clears leftover balls at the start (it asks
  `gz model --list`: Gazebo's remove call answers "true" for a model that is not there).
- **`robot_boot.sh` shutdown race fixed:** cleanup no longer `wait`s for the operator
  watch's waiter (if it had already exited, the `wait` never returned and nothing was
  shut down; 6 of 8 under load before, 16 of 16 after). CI stage 1 has
  `--timeout=180` per test and `timeout-minutes: 20`.

**NEXT (Mike, 2026-11-23 close; `docs/sessions/2026-11-23.md` "Next"):** (1) the
link-loss rule: carry on and keep logging when the operator's link is lost, "pause" as
an option; (2) mast camera on every run from `robot_boot.sh`; (3) the "day" rename;
(4) a floor run with a box that truly blocks; (5) rest of Release 1: telemetry
transfer step (57 real-robot rows on the Jetson, 0 on the workstation),
`sim_vs_real_comparison.py`, `r1-complete`; start-pose check; reaction rule in seconds.
Release 2 not started; a simple brain built here is under consideration. Class names
stay the model's own labels ("sports ball"); `yellow_ball`/`red_ball` keep the underscore.

**2026-11-22 session** (`docs/sessions/2026-11-22.md`, `docs/detection-history.md`; the
full paragraph is in `docs/claude-history.md`, "Moved from CLAUDE.md 2026-11-23"):
- **Detector decided (Mike): RF-DETR small for production, YOLO for comparison only, no
  training for now.** RF-DETR is Apache-2.0 like this repo; Ultralytics YOLO26/YOLOE
  are AGPL-3.0: keep them out of tracked code, the image and CI (`~/detect-exp-env`).
- **Confidence is not correctness, and a detector never says "unknown object"** (a
  yellow ball was "orange" at 0.92). `moondream` works as a second opinion with
  "Describe this image." and answers NOTHING to a yes/no prompt.
- **On the Jetson:** RF-DETR small 96 pictures a second on the GPU (TensorRT); the
  camera's 10 a second is the limit; an engine is built ON the Jetson from ONNX.
- **The hand-written detector's results reached the mission 3 s late** (a subscription
  queue of 10 behind a slow consumer), which is why yellow never reacted. Detections
  are still about 0.9 s behind the picture during a real mission: unexplained.
- **First floor run with RF-DETR in control:** both reactions fired; the return from
  yellow STALLED at the door frame (obstacle hold, 61 s, nothing followed: third time).
- **Ollama today:** CI only (`tools/vlm_canary.py`, log-only); never in a real mission.
- **Wayfarer (Mike):** wayfarer builds brain releases; this robot receives them. The
  detector stays a separate node. Plan: the describer proven in a real run; untrusted
  boxes to the describer, log-only; then wayfarer's mission's behavior tree and brain
  installed here. `docs/goals-and-events.md` (milestones M1-M6) shows the install is
  blocked by `Spin`/`BackUp` on the real robot and by holds nobody listens to.

**The floor ban of 2026-11-18 is lifted.** The motor board's stop-on-silence is proven on
the real robot, wheels up: `tools/bench_stop_on_silence.py` PASS (0.45 s), `--legacy-t13`
FAIL as predicted, and `kill -9` on `esp32_driver` during a real mission stopped the
wheels in 0.33 s. Repeat after any firmware update or change to how motion is sent.

**2026-11-20 session** (`docs/sessions/2026-11-20.md`; the full paragraph is in
`docs/claude-history.md`, "Moved from CLAUDE.md 2026-11-23"): box in the path PASSED on
the floor and is in CI as a simulated test; frozen-IMU check (`ImuHealth`); the dresser
stall (nothing follows a hold); a WiFi address change killed a mission (wait for the
address to settle before a run); mast camera recorder `~/robot_boot_debug/mast_record.py`.

**Mike's direction (2026-11-20):** the practical target is "rove around the whole house
and give me an inventory of where all the dog toys are"; ball-detection polish is
timeboxed. And: "if this is supposed to be an autonomous vehicle, loss of wifi should
not be fatal."

**To finish Release 1, in order (order proposed at close, not confirmed):** (1) robot
messaging on loopback and a link-loss policy per run (pause-and-resume / carry on /
carry on then come home); a dry run with the WiFi down proves it; (2) one real-robot
row per run in the telemetry DB (it has 603 local and 411 hil_jetson rows and ZERO
real_robot rows, so the dashboard and drift detection are blind to the real robot and
R1's last checkbox, `tools/sim_vs_real_comparison.py` then the `r1-complete` tag, has
nothing to compare); (3) go around (6d, with 6c back away) in the simulator on the box
bench, then the dresser; (4) start-pose check before the first goal; (5) reaction rule
in seconds, not frames, so yellow fires, then one timeboxed floor run; (6) record the mast camera on every run, one run folder with a summary, later a
debug switch on `robot_boot.sh`.
**First items of Release 2 (Mike's decision, 2026-11-20):** the joystick that came with
the robot (never set up; ask him what it is), a whole-house map driven with it, and a
trained detector (decided 2026-11-22, above; keep `docs/detection-history.md` current). Automatic
(frontier) exploration comes after the joystick map; the lidar cannot see a downward
step. **US spelling in all new text (Mike, 2026-11-20).**
Still owed: 6b act on a slip verdict, 6e guard spins, operator-watch give-up in a real
mission, closed-loop turn rate.
Also open: `robot_boot.sh` leaves the driver layer orphaned when DDS dies, exits 0 when
every trip fails, and with no terminal does not shut down cleanly;
`tests/test_esp32_driver.py` runs in no CI stage; battery "critical" does not latch;
gyro vs lidar heading 9-13 deg apart after several spins.
**Two projects, one workstation (2026-11-22).** This repo runs on ROS domain 0,
wayfarer on 42. Every by-name kill on the workstation goes through
`tools/proc_sweep.py` (`ci.yml` x3, `hil_stage.sh` teardown,
`mission2_run.sweep_orphans`): it signals only processes started on our own domain
(`/proc/<pid>/environ`; unset counts as 0) and never its own shell. Use it instead of
`pkill -f`. Wayfarer scoped its sweeps the same day; both pipelines ran at the same
time and both were green (runs `45060191707` here, `45060634456` there).
Before a floor run, ask Mike
to leave Claude Code's auto mode if it refuses the launch.

**Earlier sessions (one line each; the full "in brief" paragraphs were moved verbatim
to `docs/claude-history.md` on 2026-11-22, section "Moved from CLAUDE.md 2026-11-22";
per-session detail is in `docs/sessions/`):**
- **2026-11-19:** stop-on-silence proven on the robot; operator watch (pause after 2 s
  without the operator, give up after 10 s more: never seen in a real mission); holds
  live in `esp32_driver` (`hold_input.py`: `/robot_001/operator_hold`,
  `/robot_001/obstacle_hold`); obstacle guard (`path_guard.py`, `obstacle_guard`: 3+
  lidar returns within 0.25 m of the bumper in the direction of travel, not spins);
  `FollowPath.max_angular_accel: 10.0` (still peaks 1.3-1.5 rad/s for 0.5 commanded);
  first `hsv_realcam.yaml`; `ROBOT_BOOT_NAV2_PARAMS=<file>`; the WiFi adapter roams by
  itself (~2.4 s of silence); battery start line 10.5 V, `~/fleet-ci-data/battery_log.csv`.
- **2026-11-18:** the robot's own map fixed the home error (2-11 cm). Mapping drive =
  `scripts/robot_map_drive.sh`, built offline with `scripts/build_map_from_bag.sh`; the
  map is NOT in git (`~/fleet-ci-data/maps/bedroom_real.{yaml,pgm}` on the Jetson, copy
  in `reports/maps/`). Wheel-slip detection, observe-only (`scan_motion.py`,
  `slip_monitor`, `tools/slip_replay.py`). Battery read and enforced. The Jetson lost
  power mid-spin and the robot could not be stopped (T:13 never re-armed the timer).
- **2026-11-17:** `robot_boot.sh` records a bag on every run
  (`~/fleet-ci-data/robot_boot_logs/bag_<ts>/`; `ROBOT_BOOT_NO_BAG=1` skips) and stops
  on Ctrl+C / SIGTERM / SIGHUP; a DROPPED link sends no SIGHUP, the session just hangs.
- **2026-11-16:** four real-hardware causes behind "drives into a wall, then circles":
  wrong chassis type on the motor board, EKF ignoring the gyro, lidar scan unrotated,
  `MISSION2_IGNORE_REACTIONS` not reaching the container. All fixed (`4022c64`); the
  resulting facts are in "Physical calibration facts" below.
- **2026-08-12/13:** first `robot_boot.sh` production-path test; IMU scaling fix
  (`scale_imu_raw()`); several conclusions superseded 2026-11-16. Design facts that
  still hold: `FollowPath.use_collision_detection: false`; BT is `navigate_simple.xml`
  (no recoveries) because `behavior_server` spin/backup fails ("Pose Goes Off Grid");
  `collision_monitor`'s polygon is a deliberate 2 cm no-op. Each, when enabled, caused
  a permanent deadlock; root-cause before re-enabling, one capability at a time.

**Where things stand:** the real robot (Waveshare UGV + Jetson Orin Nano) is mid
bring-up. Sim + HIL CI is green. The production path (`scripts/robot_boot.sh`: driver
layer and RF-DETR detector bare-metal + Nav2/EKF/mission_runner in the arm64 container)
boots, localizes on its own map, completes the nav-only mission with a home error of a
few centimeters, holds for an obstacle, and has a proven stop when the Jetson dies. It
has no go-around or stuck recovery, and only observes wheel slip.

**Still open from the August punch list** (the Release 1 order above takes precedence):
whether to restrict the lidar to the forward 180 deg, and the mast-edge leak (returns
clustering at 45.7-46.0 and 123.3-124.1 deg raw); a live pre-motion lidar readout
before a goal is dispatched; whether the Jetson's ad-hoc diagnostic scripts
(`~/robot_boot_debug/`) belong in `scripts/`; CI's `stage-4-hil` runs
`use_sim_time=true`, so a push proves nothing about the bare-metal driver path.

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
- **One container, two consumers.** Nav2/EKF/`mission_runner` run in
  the arm64 image via `scripts/container_entrypoint.sh`, identically on HIL and the
  real robot, differing only by env vars (`use_sim_time`/`map`/
  self-report vs judged). Driver layer (`drivers_only_launch.py`: esp32_driver,
  lidar, camera, scan_masker, camera_relay, robot_state_publisher), the detector
  (`object_detector`, needs the GPU) and Ollama run bare-metal on the Jetson. HIL judging/ball placement (`tools/mission2_harness.py`,
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
  front and rear wheel pairs are motorized, the center pair rolls free; the board
  reports ONE speed per side. A second, USB camera sits on the pan-tilt (`docs/cameras.md`).
  Motion commands MUST be T:1 (left/right wheel speeds), never T:13: only T:1/T:11
  re-arm the firmware's stop-on-silence timer (`uart_ctrl.h`; source at
  `waveshareteam/ugv_base_ros`, folder `ROS_Driver/`). The timer (T:136) is not kept
  in flash; the driver sets 500 ms at start-up. Pack voltage is `"v"` in T:1001, in
  hundredths of a volt (3-cell pack: 12.6 V full; 9.17 V read flat on 2026-11-18).
  IMU: the board's accel/gyro chip can fail to start at power-on and repeat one
  frozen sample (seen 2026-11-20; gravity read 3.87 g); the driver and `robot_boot.sh`
  check for it; cure = power-cycle. OAK ball geometry: a croquet ball on the floor has
  `bottom_row = 325 + 1.32 * width_px` (1280x720, robot still); the detector delivers
  about 3.6 frames a second.
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
  `detection-history.md` (ball detection: what broke, what fixed it, why YOLO is next),
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
- **Existing-solution check before designing our own (Mike, 2026-11-22).** Before
  building or hand-fixing a capability (perception, recovery, localization, a tool),
  spend ~15 minutes and tell Mike: (1) what the standard solution is and who maintains
  it; (2) whether it fits this hardware and license (repo is Apache-2.0); (3) the
  cheapest experiment that would show it working here; (4) what we would learn or lose
  by building our own instead. Then he chooses. Also applies when a standard component
  FAILS here: root-cause it or ask upstream before building around it. Two cases behind
  the rule: the hand-built HSV ball detector (three sessions of fixes before a trained
  detector was tried) and Nav2's `collision_monitor` / `behavior_server`, switched off
  after deadlocks and replaced by a hand-built guard instead of being root-caused.
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
  real 2.4 s WiFi outage). And check behavior, not configuration: a stored setting is
  not an obeyed one.
- **A test passes here and hangs in CI: starve it.** Pin it to one core beside four
  busy loops (`taskset -c 0`) and run it a dozen times; durations in two clumps (3 s or
  never) mean a race, not slowness. `tests/test_robot_boot_script.py`'s `_finish()`
  prints the process tree of a stuck script; a per-process shell trace
  (`BASH_ENV` + `BASH_XTRACEFD`) names the line (2026-11-23).
- **`pkill -f` / `pgrep -f` match the shell that runs them** when the pattern (or an
  `echo` containing it) is in the same command line: four self-kills on 2026-11-20. Pick
  the PID with `ps -eo pid,comm,args | awk` on the process NAME, then kill that PID.
- **Create a log folder, check it exists, then launch.** A redirect into a missing
  folder kills only the logging: the robot still starts, unlogged (2026-11-20).
- **`cut` buffers like `tr`.** A live watcher ends in `grep --line-buffered`, nothing
  after it.
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
