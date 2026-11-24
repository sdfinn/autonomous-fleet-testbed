# CLAUDE.md history archive

Verbatim snapshot of the root `CLAUDE.md` as of 2026-11-14 (176k chars), before it was slimmed
under the context-size limit. Full session narratives, superseded "NEXT SESSION" blocks, and
long-form gotcha write-ups live here. The live `CLAUDE.md` keeps the durable rules and links back.
Search this file (grep) rather than reading it top to bottom.

---

# autonomous-fleet-testbed — Claude Code Context

## Project
Open-source CI/CD-native fleet simulation testing framework for autonomous robots.
Session plans and the release roadmap are tracked in internal planning docs (not part
of this public snapshot); this file captures the durable technical context and
gotchas that survive across sessions.
**Releases relabeled 2026-07-17: numbers now = execution order.** The agentic &
alignment layer is **R2** — docs/notes older than 2026-07-17 saying "R4" mean today's
R2. Ladder: R1 Foundation → R2 Agentic & Alignment → R3 Fleet & Input Expansion → R4
Autonomy & Perception → R5 Self-Testing Fleet; drone CUT (revivable with reason).

## ⚠️ REAL REGRESSION IN THE PUSHED COMMIT (22f1d0b), found same night, NOT fixed
CI run `31558423291` (the push right after tonight's AMCL fix) — `stage-4-hil`
FAILED, all 3 Mission 2 legs, real robot, container mode
(`use_sim_time=true`). NOT a flake: both lifecycle managers go active fine
(matching tonight's bare-metal success), but `bt_navigator` then logs
`"Initial robot pose is not available"` repeatedly for the ~60s the mission ran,
alongside TF errors showing a FROZEN requested timestamp (`20.100000`) falling
further behind the TF buffer's advancing data on every retry — never recovers.
All 3 legs FAIL: `"robot did not reach/photograph the marker"`,
`"robot barely moved: 0.000 m from start"`. This is a genuinely different code
path than anything proven bare-metal tonight (container mode, `use_sim_time=
true`) — tonight's own text already flagged this as UNPROVEN; this confirms it's
actually BROKEN, not just unverified. Prime suspect: the new
`nav2_only_launch.py` `OpaqueFunction`/`resolved_nav2_params_file` mechanism
(added tonight, runs unconditionally for both `use_sim_time` values) — it
wasn't live-tested against the `true` branch at all before pushing, only
`false` (bare-metal). Full raw log:
`reports/nav2_container_20260812T030606.log` on the Jetson (also pulled into
the CI run's own artifact). **Not investigated further tonight — Mike wants to
log off; next session should start here, before anything else**, since this
is a regression in already-pushed `main`, not just an open TODO.

**UPDATE 2026-08-12 — did NOT reproduce; best-evidenced explanation is
environmental contamination, NOT the `OpaqueFunction`/`resolved_nav2_params_file`
mechanism originally suspected above. Not confirmed via a deliberate repro, so
treat as strong-but-not-proven.** Started this session by temporarily wiring
`log_level:=debug` into `container_entrypoint.sh`'s `mission` branch (it was
already threaded through `nav2_only_launch.py` → `bringup_launch.py`, just never
actually passed at this one call site) and pushing to get a fresh, real
DEBUG-level log of the failure — no other code touched. Before that push's CI run
reached `stage-4-hil`, the Jetson lost power entirely (unrelated, physical) and
Mike power-cycled it — the least ambiguous possible full teardown of whatever
process/DDS state existed. The resulting run (`31602611709`) came back
**genuinely green**: all 3 legs real PASS in telemetry (not skipped — checked
`fleet_runs.db` directly, `home_photo_similarity` populated for no_ball/yellow as
expected), and the new 219MB DEBUG log shows the exact original symptom is
**gone**: `grep -c "Initial robot pose is not available"` → **0** (vs. **7** in
the original failing run's log), AMCL's `createLaserObject` fires cleanly, both
lifecycle managers active in both runs. Since the only code difference between
the failing run and this one was the unrelated `log_level` flag, and the only
other difference was the hard reboot, the leading explanation is that the
failing run was contaminated by stale/orphaned process or DDS/TF state left over
from that same night's hours of live bare-metal AMCL debugging (see this
session's own retrospective below — orphaned `ekf_node`/
`static_transform_publisher` processes were already found and swept once that
night, but nothing ruled out more accumulating afterward, e.g. during the
smoke-test bug-fixing work or the CI push itself) — this is the same failure
class this project has hit repeatedly (Gazebo, the bare-metal driver stack;
never before in this specific container/CI path). **`log_level:=debug` has been
reverted** (`container_entrypoint.sh` is byte-identical to `22f1d0b` again) now
that the diagnostic log was captured; re-add it (same one-line change) if this
recurs. Original prime suspect (the `OpaqueFunction` mechanism) is now believed
**exonerated, not fixed** — no code in it was changed. Concrete follow-up worth
doing: extend the retrospective's "pre-flight orphan sweep as a standing habit"
recommendation (below) to the container-mode/CI HIL path too, not just ad-hoc
bare-metal testing — this is a second, different location the same contamination
class may be able to hit. Logs for comparison: failing run —
`reports/nav2_container_20260812T030606.log`; passing debug run —
`nav2_container_20260812T135520.log` (pulled to `/tmp/hil_stage/` on the
workstation via `hil-mission-evidence` scp, not committed — regenerate via the
CI artifact or re-run with `log_level:=debug` if needed again).

**FOLLOW-UP 2026-08-12, same session — confound isolated, debug-timing ruled
out.** Mike correctly flagged a real gap in the update above: DEBUG-level
logging adds per-callback I/O overhead, which could itself have been enough to
dodge a timing-sensitive race — the passing run above never actually isolated
"clean reboot" from "slower, debug-logged timing," since both changed at once.
Fix: pushed the already-reverted, byte-identical-to-`22f1d0b` `info`-level
commit (`551a973`) immediately afterward, deliberately *while the Jetson was
still confirmed clean* (checked directly first: `pgrep` for every known orphan
pattern found nothing, `docker ps -a` showed zero containers running or
stopped, `uptime -s` matched the reboot — `hil_stage.sh teardown`'s sweep, kept
current across many prior sessions' fixes, had done its job after the debug
run). Result (`31604966760`): **also genuinely green**, real PASS/PASS/PASS in
telemetry, same as the debug run. Since this run had NO debug logging at
all — identical `log_level` to the original failing run — and still passed,
debug-timing is now ruled out as the deciding factor: clean process/DDS state
alone was sufficient. This is real evidence from a controlled second data
point, not just a second lucky green run. Standing at two-for-two clean-Jetson
passes (one with DEBUG logs proving the specific symptom absent, one at
`info` ruling out logging-timing as a confound) vs. one failure on a Jetson
with hours of uncontrolled live-testing history — genuinely strong support for
the environmental-contamination theory now, though still not a *deliberate*
repro (nobody has reproduced the contaminated state on purpose and watched it
fail again). Treat as functionally resolved for now; the concrete follow-up
two paragraphs up (extend the pre-flight orphan sweep habit to the
container-mode/CI HIL path) is the real preventive fix still worth doing.

## NEXT SESSION — START HERE (2026-08-12 late night — first real `robot_boot.sh`
production-path test found a genuine, serious AMCL localization bug; root-caused
to raw/unscaled IMU data, fixed with TDD, deployed to the Jetson, and CONFIRMED
FIXED live — HSV/A4 false-positive risk also newly confirmed real, still open)

**Picks up exactly where the "REAL REGRESSION" section above left off** — Mike asked to
try the real `scripts/robot_boot.sh` production path (never yet run end to end with the
AMCL deadlock fix) "just to see what happens." Pre-flight was clean (Jetson reachable,
native checkout at `551a973` matching `origin/main`, zero orphan processes, arm64 image
for that sha already local, no leftover containers) — genuinely fair conditions for a
first real test, not a contaminated one.

**First run (unattended — Mike ran it himself before reading the readiness question)
surfaced two real problems, both initially misdiagnosed, both eventually root-caused
correctly:**
1. Leg 1 (`no_ball`) failed 4/4 goal attempts with `COLD-START GOAL ABORT`
   (~20-30ms each, near-zero displacement) — NOT the intermittent bt_navigator
   ack-timeout race that classifier was built for (2026-07-18, always cleared by
   attempt 2 historically); this persisted every time.
2. Legs 2 and 3 both immediately (within ~20-40ms of first motion) fired a false
   `red` ball reaction — no ball was ever placed. Photos pulled back
   (`reports/robot_boot_20260813_review/`) showed a real red-painted object near
   Mike's desk in the background — `ball_detector` is still running on the sim-tuned
   `hsv_gazebo.yaml` stand-in (A4, real-camera HSV calibration, was already a flagged
   open gap — this is the first real, reproduced evidence of the exact false-positive
   risk that gap predicted, not fixed tonight, still open).

**First (wrong) hypothesis for #1, corrected live by Mike, worth remembering the
lesson:** pixel-checked `living_room.pgm` against `semantic_map.py`'s coordinates —
found the robot's AMCL-reported pose sitting on occupied ("wall"/furniture) map cells
near the mapped `bed` object, while `home_base` (the AMCL seed) and the goal were both
free space, and reasoned the camera photo showing a bed/desk in frame "corroborated"
the robot being physically near them. **Mike correctly rejected this** — he'd placed
the robot exactly at the doorway both times, and a camera can see a bed across the room
through an open doorway without being anywhere near it; seeing furniture in frame is
not evidence of proximity. Lesson: don't over-read camera CONTENT as proof of camera
POSITION.

**Real root cause, found via a live, monitored, iteratively-narrowed debug arc (door to
the other bedroom closed, red desk covered, Mike watching throughout, several live
robot_boot-style reruns with a bind-mounted debug entrypoint — `log_level:=debug`
re-added the same one-line way as the earlier REAL REGRESSION section, this time via a
non-committed bind-mount override so no image rebuild/push was needed for iteration):**
- A rerun's DEBUG-level AMCL log showed the robot's own tracked pose smoothly
  "translating" ~4m across the room over ~8 seconds — BEFORE any navigate_to_pose goal
  was ever dispatched (mission_runner was still on step 1, "reference photo at home").
  **Mike confirmed directly: the robot never moved, not even a centimeter**, ruling out
  real uncommanded motion (a serious safety bug) in favor of a pure software issue.
- Isolated the odometry pipeline directly (driver layer + `ekf_node` only, no Nav2/AMCL,
  no goals ever sent): raw `/robot_001/odom` and EKF-fused `/robot_001/odometry/filtered`
  **position** fields both sat at exact `(0,0,0)` for a full 20s — pipeline looked clean.
  This test had a real gap (only checked `pose.pose.position`, never orientation) that
  wasn't caught until the next step.
- A separate physical detour, not the cause: Mike found and moved two unidentified
  "position sensor"-looking modules ("tucked them under the hood") mid-session — rerun
  the same stationary AMCL/TF capture before and after touching them, byte-for-byte
  identical chaotic-yaw pattern both times. Genuinely ruled out, not just assumed —
  matches Mike's own guess that they're unused kit parts, nothing in this repo's code
  references a second IMU/position sensor.
- Wrote a small direct-rclpy `tf2_ros.Buffer`/`TransformListener` diagnostic (NOT
  `ros2 run tf2_ros tf2_echo` — this project's own past investigation already documented
  that hanging repeatedly; also had to fix it once live to subscribe to `/robot_001/tf`
  instead of the unremapped default `/tf`, this project's real per-robot TF-namespacing
  convention, confirmed against `src/nav_fleet/CLAUDE.md`) to watch `odom->base_footprint`
  directly, full Nav2/AMCL running, no goal ever sent. **Found it: X/Y sat at exact
  `0.0000` the entire 20s (matching the odometry test above), but YAW bounced randomly
  through the FULL +/-pi range every ~100-200ms.** EKF's translation output was perfect;
  its orientation output was garbage.
- `config/ekf.yaml`'s own design (read directly, not assumed) explained exactly why this
  is diagnostic gold: it deliberately fuses ONLY wheel-odom `vx` (translation) and ONLY
  IMU gyro-rate `vyaw` (rotation) — no redundancy on either axis. X/Y being solid and yaw
  being garbage points at exactly one thing: whatever feeds `vyaw` (the raw gyro
  reading) is bad.
- Captured raw `/robot_001/imu/data` directly (driver layer only, no EKF/Nav2 at all):
  `angular_velocity` in small single-digit-to-low-teens counts, `linear_acceleration.z`
  = **8556-8576** — not physically plausible SI values (8576 m/s^2 would be ~875g).
  These are **raw, unscaled QMI8658 LSB register counts** being published directly as if
  they were already rad/s and m/s^2. `esp32_driver.py`'s own existing comment had
  already flagged this exact risk as unconfirmed since 2026-08-10 ("NOT confirmed
  against real hardware... confirm before trusting these as calibrated") — tonight is
  that confirmation, and the answer was no.
- **Real, independent confirmation, not a one-off:** this project's own existing test
  fixture (`tests/test_esp32_protocol.py`'s real-hardware-capture test, captured
  2026-08-10) already had `az=8556` baked in from a real probe a month earlier — tonight's
  live capture (`az=8576`) matches it almost exactly. A highly stable, repeatable raw
  reading, not noise.

**Fix, found + drafted + TDD'd this session (`src/nav_fleet/nav_fleet/esp32_protocol.py`,
`esp32_driver.py`, `tests/test_esp32_protocol.py`, `tests/test_esp32_driver.py` — 3 new
tests + 2 updated, full local suite 548 passed, NOT yet committed anywhere — see "what's
still open" below):**
- New `scale_imu_raw()` in `esp32_protocol.py` converts raw LSB counts into real SI units
  before they reach ROS. `esp32_driver._publish_imu` now calls it instead of assigning
  raw counts straight into the `Imu` message.
- `ACCEL_SENSITIVITY_LSB_PER_G = 8192.0` — HIGH confidence, cross-checked against real
  physics, not trusted blindly from vendor source: found+fetched the real vendor firmware
  (`waveshareteam/ugv_base_general`'s `QMI8658.cpp`) via web search — an automated read
  claimed a DEFAULT of +/-16g, which the real captured data directly contradicts (would
  mean the stationary robot reads 4.18g; only the +/-4g range's 8192 LSB/g gives a
  plausible ~1.04-1.05g). Same vendor-doc-vs-real-runtime mismatch this exact protocol's
  module docstring already documents happening twice before — trusted the physics, not
  the doc, and said so in the code comment.
- `GYRO_SENSITIVITY_LSB_PER_DPS = 16.0` — LOWER confidence, explicitly flagged as such in
  the code: unlike accel, true angular velocity at rest is 0 regardless of scale, so
  there's no physical constant in stationary data to cross-check against the way gravity
  cross-checks accel. This is the vendor doc's own stated default; applying it to real
  captured noise gives a plausible near-zero result but that's a much weaker check. Real
  next step: a measured, hand-rotated known-angle calibration, mirroring
  `spin_experiment.py`'s own methodology for the wheel-odom rotation-over-report fix
  (`config/ekf.yaml`'s own header comment) — NOT done tonight.
- Also fixed `angular_velocity_covariance[0]`/`linear_acceleration_covariance[0]`, which
  were defaulting to all-zero (= "zero variance, trust this completely" to a consuming
  EKF — backwards for an unscaled/uncharacterized sensor) — now `-1` (REP-145 "not
  populated"), honest until real noise is characterized.

**Deployed and CONFIRMED FIXED live, same session:** `esp32_driver.py`/
`esp32_protocol.py` scp'd directly onto the Jetson's native checkout (this package
builds `--symlink-install`, confirmed this takes effect immediately with no rebuild —
verified live via a direct `python3 -c 'from nav_fleet.esp32_protocol import
scale_imu_raw...'` import on the Jetson before re-testing). Reran the exact same
stationary TF capture: **yaw held at exact `0.0000` for the full 20s** (was bouncing
through the full +/-pi range every ~100-200ms before) — X/Y unchanged (already solid).
AMCL's own `Num samples` debug line dropped from **167** forced updates in 20s (stuck at
`max_particles`=2000, never converging) to **exactly 1** (the initial seed) — it
correctly recognizes no real motion now and stops churning. Then closed the loop with a
full production-path mission retest, robot repositioned exactly at the doorway (same
bind-mounted-debug `robot_boot.sh` harness used all session): AMCL's reported pose is
now **`(-1.276, 1.200)`/`(-1.276, 1.329)`** — right at `home_base`, matching real
placement, versus the earlier run's ~4m-off `(0.27-0.32, 5.3-5.4)`. Leg 1's navigation
succeeded normally this time — one ordinary ~0.3s controller-startup delay (well inside
the existing `COLD_ABORT_WINDOW_S=2.0` tolerance), no retries needed, real velocity
~0.1 m/s. **Mike directly observed the robot move a real, small, controlled ~4 inches
forward before stopping** — the first genuine confirmed real motion of the whole
investigation. All 3 legs still fired the same false `red` reaction as the first run
(desk wasn't re-covered for this rerun) — confirms that risk is real and reproducible,
completely unrelated to and untouched by this fix.

**What's still open, as fact, not assumption:**
1. **Nothing from tonight has been pushed anywhere.** The code fix is committed locally
   on the workstation's `main` only (this commit). The Jetson's native checkout has the
   two fixed files scp'd directly over the tracked versions — a DIRTY tree, not a commit
   — matching this project's own established ad-hoc live-verification pattern (see the
   `hil_stage.sh sync` self-healing fix, 2026-08-11/12 — a future `sync()` call will
   `git reset --hard`/`git clean -fd` this away automatically, don't be surprised
   finding it dirty next session).
2. **Gyro scale factor is a flagged best estimate, not independently verified** — the
   concrete follow-up (a real, measured, hand-rotated calibration test) is still open.
3. **HSV real-camera calibration (A4) still doesn't exist** — `hsv_gazebo.yaml` is still
   the running stand-in, and tonight gave it a REAL, reproduced false-positive case
   (the desk's red paint), not just a theoretical risk.
4. **Accel/gyro zero-offset (bias) calibration is a separate, still-open gap**, flagged
   in the new code comments — tonight's fix is a pure proportional scale factor only, no
   bias/offset correction attempted.
5. Whether/when to push this fix, and whether the arm64 Docker image needs a rebuild for
   it (the driver layer runs bare-metal — this fix never touches the container image
   directly — but worth confirming deliberately, not assuming, before trusting CI's own
   `stage-4-hil`/HIL path reflects it) — not decided, bring to Mike.
6. Ad-hoc diagnostic scripts built tonight (`robot_boot_debug.sh`,
   `odom_isolation_test.sh`, `amcl_tf_test.sh` + `tf_watch.py`, `raw_imu_test.sh`) live
   only in `~/robot_boot_debug/` on the Jetson — genuinely useful, reusable diagnostic
   tools, not part of the tracked repo. Worth deciding whether any belong in
   `scripts/` properly, or should stay scratch.
7. Photos from the closing-loop rerun: `reports/robot_boot_20260813_postfix/` on the
   workstation (real checkout, not `/tmp`) — home-reference + reaction-red pairs for
   all 3 legs, useful for a future HSV/A4 session as real before-photos of the exact
   false-positive object.

**LATER THE SAME NIGHT — with the AMCL/IMU fix confirmed, tried a genuinely
uninterrupted navigation test and found a separate, PRE-EXISTING, deeper gap: this
robot currently has NO working collision-avoidance or stuck-recovery mechanism at
all. Confirmed from real config + real bag data, not guessed. NOT fixed tonight —
full punch list below, for tomorrow.**

Added a diagnostic-only `MISSION2_IGNORE_REACTIONS` env var (TDD,
`nav_fleet/mission_runner.py`'s `_detection_cb` + `tests/test_mission_run.py`) so a
navigate leg's ball-color reactions can be suppressed for testing — the goal was to
isolate navigation/localization validation from the still-open HSV/A4 false-positive
bug. **First deployment attempt was a real mistake, worth remembering the shape of:**
scp'd the fix to the Jetson's NATIVE checkout only, but `mission_runner.py` actually
runs from a SEPARATE, plain (non-symlink) copy baked into the Docker image at
`/ros2_ws/install/nav_fleet/lib/python3.12/site-packages/nav_fleet/mission_runner.py`
(confirmed by reading the Dockerfile directly — plain `colcon build`, deliberately no
`--symlink-install`, so `build/` can be safely dropped after). The native-checkout scp
never reached this. Result: reactions were NOT actually suppressed on the first live
attempt — the robot autonomously drove a full, unsupervised, ~60-second
`photo_then_home` return-navigation with nobody expecting it to. Very likely why it
ended up near Mike's desk, prompting a real physical intervention ("picked it up
because it was on my desk"). Fixed properly the second time — bind-mounted
`mission_runner.py` over the CONTAINER's actual installed path, and this time verified
it live (grepped the file from inside a throwaway container) before trusting it. Lesson
generalized: any fix meant to reach code running inside the container needs to target
where the container actually imports from, and needs to be verified live inside the
container before being trusted — the native-checkout convenience that worked for the
bare-metal driver layer earlier tonight does not carry over.

Corrected test confirmed reactions genuinely suppressed (no reaction events fired) —
but leg 1 and leg 2 BOTH still failed anyway, this time via Nav2's own
`SimpleProgressChecker` (`movement_time_allowance: 60.0`) — 74.166s and 60.122s
respectively, a completely different failure signature than tonight's earlier ~20-30ms
cold-aborts. Mike watched leg 1 drive straight into a wall; repositioned mid-room, the
next attempt just circled. Confirmed everything was safely torn down (`docker stop` +
zero remaining processes) before investigating further.

**Mike's own correction, and it was the right one:** don't reflexively blame the map.
The identical map file lets sim/HIL pass this exact leg regularly (dashboard status at
session start showed `mission2_no_ball: PASS` for both `hil_jetson` and `local`) — so
the map's planning graph is provably geometrically valid on paper. Whatever's actually
failing has to be specific to real-hardware execution, not a map-authoring error. This
correction is what led to the real finding below, instead of a third wrong guess.

**Root investigation, from real config and real recorded data, not more live testing:**
- `nav2_params.yaml`'s `FollowPath.use_collision_detection: false` — documented,
  deliberate, not new tonight. Its own comment: `true` DID correctly stop the robot
  before a real collision once ("the Dresser corner"), but then left it in "a
  guaranteed deadlock with no way out," because recovery is separately, already
  broken.
- `bt_navigator`'s BT tree is `navigate_simple.xml` — one-shot, no periodic replanning,
  NO recovery behaviors at all — because `behavior_server`'s recovery (spin/backup)
  has "a real, separate bug" ("Pose Goes Off Grid") that "fails 100% of the time," an
  "unsolvable-in-one-session tangle" from a past session (see this file's own top-of-
  `nav2_params.yaml` comment), deferred to `Release1Todo.md` (private planning doc,
  outside this public snapshot).
- `collision_monitor`'s only polygon (`FootprintApproach`) is deliberately shrunk to a
  2cm x 2cm square — smaller than the lidar's own minimum range (0.12m) — a documented,
  deliberate no-op. A properly-sized version was tried once and hit an IDENTICAL
  deadlock signature, per its own comment: "one real command, then zero [motion] for
  ~225s" (a silent self-lock — clamps `cmd_vel` toward zero as it nears something, and
  since the robot then stops, the distance never changes, so the clamp never lifts).
- **Conclusion: there is currently no working collision-avoidance or stuck-recovery
  mechanism anywhere in this robot's real navigation stack.** Both available
  mechanisms were independently tried, both caused a WORSE failure (a permanent,
  silent deadlock) than the collision they existed to prevent, so both are
  deliberately disabled. This predates tonight entirely — it was simply never exposed
  before, because every previous real-hardware run got interrupted early (cold-aborts
  from the AMCL bug, or false ball-detections) before ever running long enough to
  reach it. Fixing both of those earlier tonight removed the accidental early exits
  that had been masking this deeper gap.
- Pulled both kept `failure_bag`s (real rosbag2/mcap — `/robot_001/scan` +
  `/robot_001/cmd_vel` + `/robot_001/amcl_pose`) to the workstation for analysis
  (`reports/failure_bags_analysis/`, not tracked by git). One
  (`mission2_20260813_031705`, the actual wall-collision leg Mike watched) was lost —
  empty, no metadata — because `docker stop` doesn't let rosbag2's recorder cleanly
  finalize the mcap file the way SIGINT does. Real, separate lesson: prefer a graceful
  SIGINT-based teardown over `docker stop` whenever a live recording might be in
  flight. The other (`mission2_20260813_031206`, a DIFFERENT leg's stall — the
  yellow-reaction's return-home timeout, from the earlier still-reaction-affected
  attempt) was intact and analyzed directly (`rosbag2_py` + `rclpy.serialization`,
  no existing tool for this in the repo, done ad-hoc):
  - `/robot_001/cmd_vel`: one real ~2s burst of forward motion, then **exactly zero
    linear velocity for the remaining ~73s**, with `angular.z` pegged at a constant
    +0.160 rad/s for ~57 continuous seconds — the controller was trying to rotate in
    place, not drive forward, almost the entire time.
  - `/robot_001/amcl_pose`: only 4 messages, all within the first ~2 seconds — AMCL
    never published again for the remaining ~73s, consistent with the robot genuinely
    not making real physical progress (translation OR rotation) despite the sustained
    rotation command.
  - `/robot_001/scan`: "closest obstacle" readings throughout were 3-29cm — genuinely
    very close — but the reported bearing only drifted slowly (46 deg -> 124 deg ->
    150-178 deg) across the full ~75s window, far less angular sweep than 57 seconds
    of genuinely free rotation at 0.16 rad/s would produce (several full 360 deg
    sweeps). Strong evidence the robot was NOT actually freely rotating despite being
    commanded to — consistent with being physically wedged against something real.
- **New, separate, concrete finding: the scan self-occlusion mask may be too narrow.**
  `scan_masker.py`'s `DEFAULT_MASK_SECTORS_DEG = [46.0, 123.0, 268.0, 277.0]` masks the
  mast (46-123 deg) and WiFi antenna (268-277 deg). A cluster of the bag's
  "closest obstacle" readings landed at 45.7-46.0 deg and 123.3-124.1 deg — right at
  the mask sector's own edges — suggesting the mast's real angular extent is slightly
  WIDER than the hardcoded boundary, letting its own edge leak through as a phantom
  "obstacle right next to me." Does NOT explain the whole episode by itself (later
  readings at 147-178 deg are outside either masked sector and don't correspond to any
  known self-occlusion source, so likely a real external object) — but it's a real,
  fixable, independently-testable bug on its own, separate from the collision/recovery
  gap above.

**Mike's punch list for tomorrow, recorded in full (his own framing, expanded with
tonight's context so it's actionable cold):**

1. **Mast/mask redesign — CONFIRMED plan: restrict the useful lidar FOV to the
   forward 180 deg (robot-relative bearing -90 deg to +90 deg around
   `TRUE_FORWARD_BEARING_RAD` = 285 deg, i.e. raw bearing [195 deg, 360 deg) union
   [0 deg, 15 deg)) instead of maintaining narrow, precisely-bounded per-object
   exclusion sectors.** Mike's call, and the numbers support it cleanly: the mast
   (46-123 deg, confirmed opposite-of-forward, ~160 deg off centerline) is fully in
   the rear half, no masking needed once this lands. The WiFi antenna is physically
   at the back of the robot too (off to one side of the mast, per Mike directly —
   not literally behind the mast, but still rear-hemisphere) — this contradicts its
   CURRENTLY RECORDED sector (268-277 deg, which computes to only ~12.5 deg off
   dead-ahead-forward, i.e. essentially in front) — so that recorded value is stale
   or wrong, not a sign the front-180 design has a gap. **First concrete step, a
   quick confirmation not an open design question:** re-measure the antenna's real
   bearing the same way the mast's was originally confirmed (marker at a known real
   position, read back the lidar's own reported bearing for it) — expected to land
   somewhere in the rear hemisphere, at which point the front-180 restriction covers
   both objects with zero per-object special-casing, exactly as designed. Also worth
   deciding deliberately, not assuming, while implementing: does discarding the rear
   180 deg cost Nav2's local costmap anything it actually needs (e.g. obstacles
   behind the robot during an in-place rotation or backing up go completely
   undetected)? A real tradeoff to think through, not just implement.
2. **The fixes we think we need, roughly cheapest/most-isolated to hardest/most-
   architectural:**
   - Widen (or replace via #1) the scan self-occlusion mask so the mast's own edge
     stops registering as a phantom obstacle.
   - **The big one, and the real root gap:** collision-avoidance and stuck-recovery
     are both currently non-functional by design. This needs real design work, not a
     quick parameter flip — recall `use_collision_detection: true` alone already
     caused a WORSE failure (permanent deadlock) once, because recovery doesn't work;
     simply flipping it back on without fixing recovery first would very likely
     reproduce that immediately. The actual fix is almost certainly: root-cause
     `behavior_server`'s "Pose Goes Off Grid" bug (or replace/reimplement recovery some
     other way), THEN re-enable collision detection, one capability at a time with a
     real test at each step — exactly matching this file's own existing "Deferred Nav2
     capability" guidance in `nav2_params.yaml`'s own top comment. Check
     `Release1Todo.md` (private planning doc, outside this public snapshot) for
     whatever context already exists there before starting fresh.
   - HSV real-camera calibration (A4) — still open, still real (confirmed again
     tonight, separately from all of this).
   - Gyro scale calibration (from earlier tonight's IMU fix) — still an unverified
     best estimate, needs a real hand-rotated calibration test.
   - Real SLAM map (A3) — tonight's evidence doesn't prove this is the primary driver
     of the wall/circling episode (sim proves the existing map's plan is geometrically
     valid), but it's still worth doing eventually for real margin/precision, and
     hasn't been ruled OUT as a contributing factor either — the real room's actual
     furniture/clearances still aren't independently verified against the map.
3. **Better debugging, and a real open question, both from Mike directly:**
   - **We should know the lidar's actual distance-to-nearest-obstacle BEFORE the robot
     ever moves, live, not reconstructed after the fact from a bag.** Tonight's
     diagnosis relied entirely on forensic post-hoc analysis of a failure bag —
     useful, but by definition too late to prevent anything. Concrete ask: a live,
     prominent (not buried in DEBUG-level Nav2 log spam) readout of forward-arc lidar
     range, ideally available before a navigate goal is even dispatched, so a human
     watching (or an automated pre-flight check) can catch "the lidar says something
     is 5cm away, that's suspicious" BEFORE commanding motion, not just after a
     60-second stall.
   - **Open question, not yet answered: does this same path's turning segment bring
     the robot close to a wall in SIM too, and if so, why does sim handle it fine
     while the real robot doesn't?** If sim's version of this maneuver also turns near
     a wall at comparable clearance and it's a non-issue there, that's real evidence
     pointing at something specific to real execution (localization precision during
     motion, real wheel slip, real vs. simulated wall placement, controller tuning
     only ever validated in sim) rather than the path itself being unsafe on paper. If
     sim's turn happens with much MORE clearance than reality actually has, that would
     point back toward a real map/room mismatch after all. Needs a real, direct
     comparison — not assumed either way.

**Next session, in order:** (1) Mike's 3-item punch list above — mast/mask redesign,
the collision/recovery architecture gap (the real priority — everything else is
secondary until the robot has a working way to not get permanently stuck), and the
live lidar-distance debugging tool + the sim-vs-real turning-clearance comparison; (2)
decide whether to commit tonight's ad-hoc diagnostic scripts (`robot_boot_debug.sh`,
`odom_isolation_test.sh`, `amcl_tf_test.sh` + `tf_watch.py`, `raw_imu_test.sh`, the
rosbag2_py bag-analysis one-off) somewhere durable, or let them stay scratch; (3) a
real gyro calibration test (hand-rotated known angle) to replace the flagged
best-estimate `GYRO_SENSITIVITY_LSB_PER_DPS`; (4) decide push timing for tonight's IMU
fix — CI's `stage-4-hil` has never exercised this exact bare-metal driver code path
(it always runs `use_sim_time=true`, so this whole bug class was structurally
invisible to it, same standing gap the 2026-08-11 retrospective already flagged) so a
push proves nothing new about THIS fix by itself; a real `scripts/robot_boot.sh` rerun
(as done tonight) is the only thing that actually validates it; (5) A4 (real-camera
HSV calibration) — now has real reproduced evidence backing it twice over; (6) A3
(real SLAM map) — still open, not proven to be tonight's primary driver but not ruled
out as a contributing factor either.

## (superseded 2026-08-12) PREVIOUS NEXT SESSION — START HERE (2026-08-11 — drivers-bare-metal-boot-fix DONE and
PUSHED, first CI run's stage-4-hil failure fixed at the root cause and re-pushed
GREEN — the attended bench smoke test was then genuinely ATTEMPTED live (real
terminal, real ball, Mike watching) and found 3 MORE real hardware bugs, all
fixed and live-verified on real hardware, awaiting a second push + fresh CI
confirmation before the full official smoke test can be re-run end to end)

**Attended smoke-test attempt, same day, found 3 real hardware bugs — full
story:** once CI went green (run `31514981563`, all 9 jobs), Mike ran the real
`scripts/hil_stage.sh smoke <sha>` from his own terminal. Everything through the
attended ball-placement prompt worked (proving the whole boot-fix arc above is
sound), but the results revealed 3 real, previously-unknown/mis-recorded hardware
behaviors, each found+fixed+live-verified this session (ad-hoc verification
scripts, not yet re-proven through the OFFICIAL `hil_stage.sh smoke` path — that
re-run is the very next step once this second push's CI goes green):
1. **`linear.x` was inverted on this specific unit** — a ROS `+linear.x` command
   physically drove the robot BACKWARD (Mike watched it happen during the
   `motion` check, which PASSED anyway — see #3). Confirmed via a small,
   ad-hoc, non-attended direction-check burst (bare driver layer only, no
   container): odom simultaneously reported FORWARD while the robot moved
   backward, since the firmware's own T:1001 wheel-speed feedback shares the
   same reversed convention as its setpoint math. Fixed: `esp32_driver.py`'s
   `_cmd_vel_cb` now negates `linear.x` before encoding; `_publish_odom`
   uniformly negates the T:1001 `L`/`R` feedback so odometry tracks reality
   too. Commit `9d2c283`.
2. **`angular.z` was ALSO inverted — and this directly CONTRADICTS an earlier
   "confirmed" CLAUDE.md record from the 2026-08-10 A2 rotation check**
   (which claimed negative `angular.z` = right, matching REP-103 = already
   correct, no fix needed). Live testing today found the opposite: raw,
   uncorrected positive `angular.z` physically turns the robot RIGHT, not
   left — repeated, direct, unambiguous visual confirmation with Mike
   watching a real ~25-30deg turn (a first, too-short 1s pulse gave an
   inconclusive-but-correctly-signed ~3deg result that wasn't trusted at the
   time — worth remembering that a small ambiguous result's SIGN can still be
   informative). **The earlier record is now believed mistaken, not this
   session's finding** — see the corrected/annotated Gotchas entry below,
   left in place rather than silently deleted. Fixed in the same commit
   (`9d2c283`) alongside `linear.x` — required an intermediate wrong turn:
   uniformly negating both wheels' feedback (fixing linear) initially broke
   the ALREADY-correct-feeling turn math, which led to a "swap-and-negate"
   transform that was ALSO wrong once the real angular.z convention was
   understood — full back-and-forth documented in `esp32_driver.py`'s own
   comments, left as real history, not cleaned up after the fact.
3. **`check_ball_correlation`'s lidar check read the WRONG bearing.**
   `_forward_arc_min_range` checked around the scan's raw bearing 0 (the
   lidar's own physical zero — the URDF's `lidar_joint` has no rotation
   applied) instead of true forward (~285deg raw, the A2 finding) — so the
   reported "lidar distance to the ball" (0.511m) was actually the distance
   to whatever's nearest in a completely unrelated direction, not the ball at
   all (confirmed: the real captured photo showed the ball correctly placed
   and visible; the camera's own independent range estimate, 0.68m, was
   reasonably close to the true 0.75m placement). Fixed: new
   `TRUE_FORWARD_BEARING_RAD` constant, `_forward_arc_min_range` now centers
   its arc there with proper atan2-based wraparound handling. Commit
   `d7da3d9`.
Also, separately (Mike's own ask, not a bug): the `motion` check's pulses felt
too large (~5.9in forward / ~28.6deg turn) — retuned to ~1in/~20deg (same 1.0s
pulse duration throughout, not shortened, to avoid the documented ~1.2s
startup-delay artifact eating a shorter pulse). While touching this, fixed a
REAL gap the linear.x bug itself exposed: `check_motion`'s own PASS math
(`math.hypot`) only measured MAGNITUDE, not direction — the exact reason the
backward-motion bug above passed the `motion` check instead of failing it, only
caught by Mike watching. Now resolves displacement along the robot's own
heading (signed) so a future direction-inversion bug would FAIL automatically.
Commit `5489ed4`. TDD throughout all 3 fixes; full local suite (542 tests)
re-run clean after each.
**Not yet done:** docs weren't updated to reflect ANY of this until this very
entry (in progress); the second push (`5489ed4..?`) hasn't happened yet as this
was being written.

**Closes the boot-sequence gap flagged at 2026-08-10 EOD** ("nothing in the boot
chain ever starts `sensors_only_launch.py`"). Implemented via subagent-driven-
development, 5 tasks + a follow-up whole-branch-review fix pass. Plan:
`docs/superpowers/plans/2026-08-10-drivers-bare-metal-boot-fix.md`; full ledger:
`.superpowers/sdd/progress.md`.

**Push + CI arc, this session:** first push (`bfed3f3..f5c56c4`, 9 commits)
triggered CI run `31513008012` — `stage-4-hil` failed at its very first step
(`Sync the commit under test on the Jetson`), everything after it skipped. Root
cause: the Jetson's NATIVE checkout (`~/autonomous-fleet-testbed`, the same
directory `hil_stage.sh sync` operates on) had local, uncommitted files left by
this session's own live-hardware verification (subagents `rsync`'d individual
files there for Tasks 1/3/5's real-Jetson checks, never cleaned up afterward) —
`git checkout --detach FETCH_HEAD` correctly refused to overwrite them. This is
the IDENTICAL failure signature CLAUDE.md already documented from 2026-08-10 ("HIL
hardening session" Gotchas entry) — it recurred because that session's fix was
manual cleanup, not a structural one. **Fixed at the root cause this time, not
just cleaned again:** `hil_stage.sh sync()` now self-heals (`git reset --hard
FETCH_HEAD && git clean -fd` instead of a plain `checkout` that fails hard on any
local state) — see the new dated Gotchas entry below for the full story,
including a second, real bug found WHILE testing this exact fix (a `.gitignore`
gap that let `git clean -fd` delete 6 real, uncommitted `reports/
sensors_container_*.log` files — also fixed, also documented). Confirmed the
Jetson's stray files were genuinely stale (superseded by later commits, not
diverged real work) via direct `diff` before touching anything, and confirmed
`smoke()` itself calls `sync()` as its own first action — so this fix isn't just
an operational unblock, it's a real precondition for the attended smoke test to
ever work at all. Re-pushed (`f5c56c4..<new tip>`) rather than re-running the
failed job in place — Mike's explicit call this time (opposite of the
2026-08-10 precedent's "no unnecessary extra CI runs," since this push includes a
real code fix, not just a clean Jetson tree).

**The gap, restated precisely:** `robot_boot.sh` -> `container_entrypoint.sh`'s
`mission` branch -> `nav2_only_launch.py` only ever started Nav2/EKF/`ball_detector`
— nothing in that chain ever started `sensors_only_launch.py` (esp32_driver/lidar/
camera/scan_masker/camera_relay). Separately, the bench smoke test's ORIGINAL design
(`ROBOT_MODE=smoke_test` launching `sensors_only_launch.py` INSIDE the container)
could never have worked on real hardware either — the container image never had the
vendor lidar/camera packages installed, only bare-metal can reach that hardware. A
mid-planning design correction — **Mike's own catch, not something a reviewer
found**: the smoke test needed to exercise the REAL container boundary (EKF+
ball_detector running INSIDE the container, driver layer running bare-metal OUTSIDE
it), not a bare-metal stand-in for the whole thing.

**Why this wasn't caught sooner:** HIL always runs `use_sim_time=true` — `ci.yml`'s
`stage-4-hil` job, "Run smoke-test machinery regression (HIL container)" step, own
comment: `USE_SIM_TIME=true so sensors_only_launch.py skips esp32_driver/
ldlidar_ros2/depthai-ros and relies on the workstation's Gazebo bridge`. HIL is
therefore structurally incapable of exercising the real-hardware driver-layer code
path this fix touches — every HIL run since this project's inception was blind to
this gap by design, not by oversight.

**The 5-task fix** (full detail in the plan doc, one line each here):
1. Extracted `drivers_only_launch.py` out of `sensors_only_launch.py` — the 5 driver
   nodes now live in their own launch file; `sensors_only_launch.py` composes it via
   `IncludeLaunchDescription`, keeps its own always-on EKF/ball_detector.
2. Added `skip_nav2` to `nav2_only_launch.py` (true = EKF+ball_detector only, no
   Nav2/AMCL/map_server — the smoke test's new production-boundary mechanism).
3. `robot_boot.sh` now starts the driver layer bare-metal before the container.
4. `container_entrypoint.sh`'s `smoke_test` branch reworked to launch
   `nav2_only_launch.py skip_nav2:=true` instead of the old in-container
   `sensors_only_launch.py` approach.
5. `hil_stage.sh smoke()` reworked to match: driver layer bare-metal via SSH,
   EKF+ball_detector in a container, both polled for readiness, explicit teardown.

**Two real bugs found DURING implementation, not from the plan's own text — the
same bug, found twice, independently, in two different scripts:** bash silently
sets `SIGINT`/`SIGQUIT` to `SIG_IGN` on any `&`-backgrounded job inside a
non-interactive script (POSIX: async jobs without job control auto-ignore both
signals). Found in Task 3 (`robot_boot.sh`'s own local backgrounding — `kill -INT`
on the driver-launch PID was a silent no-op until fixed), then found to recur
identically in Task 5 (`hil_stage.sh smoke()`'s remote `ssh host "cmd &"`
backgrounding — same mechanism, local vs. remote doesn't change it). Both
live-verified via real `/proc/<pid>/status` `SigIgn` bitmasks on the Jetson (`0x6` =
SIGINT+SIGQUIT ignored before the fix, `0x1` = only SIGHUP after), both fixed with a
tightly-scoped `set -m`/`set +m` bracket around just the one backgrounding line.

**Final whole-branch review (after all 5 tasks individually Approved) found 2
Critical bugs invisible at single-task scope, both fixed in one follow-up commit
(`4366ecb..0b85350`), both re-reviewed independently clean — "Ready to push: Yes":**
- **C1 — CI would have hung.** Task 4's rewrite of `container_entrypoint.sh`'s
  shared `ROBOT_MODE=smoke_test` branch made it idle forever (`wait "$NAV2_PID"`,
  waiting on external teardown) — but `smoke_ci()` (CI's own `stage-4-hil`
  regression step, genuinely untouched by any of the 5 tasks' own diffs) runs that
  SAME shared branch in the foreground with no external teardown. Would have hung
  `stage-4-hil` until CI's 20-minute timeout on the very next push. **The real
  lesson, not just the bug:** "is smoke_ci untouched" was verified TEXTUALLY
  (diffing smoke_ci's own body, which really was unchanged) rather than
  BEHAVIORALLY (what the shared branch it dispatches into now actually does) — a
  textually-clean diff isn't the same question as a behaviorally-clean one. Fixed by
  branching the shared `smoke_test` case on the already-existing `USE_SIM_TIME`
  value (both callers already set it, zero new env vars): `true` (smoke_ci, CI-only)
  restores the pre-Task-4 original in-container logic byte-for-byte (verified via
  `diff`, confirmed identical); `false` (the real bench) keeps Task 4's new
  idle-until-torn-down behavior.
- **C2 — the bare-metal driver layer would have talked to the wrong DDS
  implementation.** `robot_boot.sh` and `hil_stage.sh smoke()` never exported
  `RMW_IMPLEMENTATION`/`CYCLONEDDS_URI` for the driver layer under non-interactive
  SSH/systemd (no `.bashrc` there) — defaults to FastDDS while the container
  hardcodes CycloneDDS, meaning zero DDS traffic would cross the boundary on a real
  power-on. This reproduces this whole plan's original bug in a new, invisible
  form — masked during every earlier task's own live check since those all ran
  interactively (where `.bashrc` supplies the export). **Live-verified both states
  on the real Jetson via `printenv`:** confirmed genuinely unset before the fix
  (plain non-interactive SSH, exit code 1, no output), confirmed correctly set after
  (`RMW_IMPLEMENTATION=rmw_cyclonedds_cpp`,
  `CYCLONEDDS_URI=file:///home/mike/cyclonedds-hil.xml`, matching the container's
  own hardcoded config; the referenced XML file confirmed to actually exist at that
  path).
- Plus 5 Important + 3 Minor fixed in the same pass: readiness gate strengthened to
  require ALL 4 driver "up" lines (esp32_driver/lidar/camera/camera_relay —
  `scan_masker` isn't gated, it starts regardless of upstream driver status), not
  just `camera_relay up`; a teardown trap added
  to `smoke()` (previously no coverage for Ctrl+C at the ball-placement prompt);
  `ros2_drivers_ws` overlay sourcing added to `smoke()` to match `robot_boot.sh`'s
  own already-fixed gotcha; a `fleet-ci-data` ownership pre-flight warning; a loud
  HSV-fallback-to-sim-thresholds warning; stale docstring pointers; the pkill
  bracket-trick convention applied consistently. Full list:
  `.superpowers/sdd/final-review-fix-report.md`.

**What's still open, as fact, not assumption:**
1. **The attended end-to-end bench smoke test has not been run.** Needs a real
   terminal and Mike physically placing the yellow ball
   (`scripts/hil_stage.sh smoke <sha>`). This is the very next real step.
2. **C2 is proven "exported," not yet proven "crosses the boundary."** The env-var
   fix is confirmed correct in isolation on the Jetson; whether real DDS traffic
   actually reaches the container from the bare-metal driver layer is unverified
   until the attended smoke test (or a real `robot_boot.sh` run) actually happens.
3. **The driver-readiness timeout has only been timed warm** (~25s on an
   interactive SSH session) — never on a real cold boot under
   `robot-mission.service`, where USB/udev enumeration for the camera/lidar is
   expected to be slower than the warm number, against the same 60s budget. Worth
   timing for real, or bumping the timeout, before trusting the systemd unit as-is.
4. **`hsv_realcam.yaml` (A4) still doesn't exist** — a full `robot_boot.sh` run
   through the container step will still fail there; `smoke()`'s HSV default falls
   back to sim thresholds with a loud warning now, but that's a mitigation, not a
   fix.

**Later the SAME night (2026-08-11), a separate real investigation: Mike attempted
a genuine bare-metal `robot_boot.sh` production run and hit a NEW, previously-
undiscovered blocker — AMCL never processed a single lidar scan, `local_costmap`
timed out waiting for the `map` transform forever, no error, no abort.** Chased to
root cause live, over several hours, using DEBUG-level Nav2 logging, direct rclpy
diagnostic scripts (bypassing repeatedly-hanging `ros2 run tf2_ros tf2_echo`), and
reading vendor source directly rather than guessing. **Two real, independent bugs
found stacked on top of each other, both fixed, both confirmed live:**
1. **`robot_state_publisher` was never started anywhere in the real robot's boot
   chain at all** — confirmed via `grep -rln "robot_state_publisher"` matching only
   sim launch files. Without it, nothing published the URDF's static sensor-frame
   transforms (`base_footprint`→`base_link`→`camera_link`/`imu_link`/`lidar_link`),
   so AMCL's TF-synchronized scan subscription had no path to resolve at all. Fixed:
   added to `drivers_only_launch.py` (real-hardware group), same pattern
   `sim_only_launch.py` already proves.
2. **A frame-name mismatch, found AFTER fix 1 still didn't resolve the deadlock:**
   `ldlidar_ros2`'s own `ld19.launch.py` hardcodes `frame_id: 'base_laser'` on every
   scan message (confirmed by reading the vendor launch file directly), but
   `ugv_pt.urdf.xacro`'s real lidar link is named `lidar_link` — two different names
   for the same physical mount, so even with `robot_state_publisher` running, the
   scan's own frame_id still had no path into the rest of the TF tree. Fixed in
   `scan_masker.py` (not the vendor file — this project's own convention) — it
   already republishes every scan message (masking self-occlusion sectors), so it
   now ALSO rewrites `header.frame_id` to a new `output_frame_id` param (default
   `'lidar_link'`), TDD, 2 new tests including one that pins the OLD (wrong)
   pass-through behavior as a regression test for the new one.
   Two more real, supporting fixes found and confirmed live along the way, both
   needed regardless of the two bugs above:
   `nav2_only_launch.py`'s composed Nav2 nodes never actually received `use_sim_time`
   — root cause: `nav2_bringup`'s own `bringup_launch.py` calls its internal
   `RewrittenYaml` with `param_rewrites={}` (an empty dict, confirmed by reading that
   file directly on this ROS2 Jazzy build) — fixed with a small `OpaqueFunction` in
   `nav2_only_launch.py` that resolves `use_sim_time` into a fresh params YAML before
   Nav2 loads it. Separately, `local_costmap` had no `global_frame` override at all,
   silently defaulting to `"map"` instead of `"odom"` — fixed with an explicit
   `global_frame: "odom"` in `nav2_params.yaml`, with a comment explaining why.
   **A THIRD contributing factor, found only when testing the above two fixes fresh
   tonight — likely present (and contaminating) every earlier test this session, not
   a new bug from these fixes:** three orphaned `ekf_node` processes (`PPID=1`, each
   from a separate earlier container/`nav2_only_launch.py` run that was never torn
   down) were all still alive on the Jetson, all simultaneously publishing
   `odom`→`base_footprint` onto the same `/robot_001/tf` — the exact "orphaned
   process poisons every later run" failure class `src/nav_fleet/CLAUDE.md` already
   documents for Gazebo, now recurring on the real driver stack. A 12+-hour-old
   orphaned `static_transform_publisher` (`base_link`→`base_laser`, part of
   `ld19.launch.py`'s own bring-up) was found alongside it. Both swept before the
   final clean test — this is why the earlier "RSP added, deadlock persists" result
   recorded mid-session shouldn't be fully trusted as a clean test of fix 1 alone.
   **Confirmed genuinely fixed, launched completely fresh with zero orphans:** every
   Nav2/AMCL node reports `active [3]` (`amcl`, `controller_server`, `planner_server`,
   `smoother_server`, `behavior_server`, `bt_navigator`, `map_server`, both
   costmaps); AMCL's own log shows `createLaserObject` (confirmed via reading
   `amcl_node.cpp` directly — only fires from inside the scan-processing callback
   that was dead silent all night); `map`→`odom` publishing continuously, **440
   updates over 45s, ~9.75Hz**, not a one-off fluke. This is the first time the full
   real-hardware Nav2 stack has come up genuinely healthy end to end.
   **Committed locally, NOT pushed yet** (`robot_state_publisher`/`scan_masker.py`
   frame_id rewrite/`nav2_only_launch.py` use_sim_time fix/`nav2_params.yaml`
   `global_frame`/`robot_boot.sh` NAV2_MAP_FILE+HSV_CONFIG_FILE stand-ins) — this
   commit (self-referencing a hash here just chases its own amend, so named by
   description instead — `git log --oneline -- src/nav_fleet/nav_fleet/scan_masker.py`
   finds it).
   **What this does NOT yet prove:** all of tonight's testing ran the driver layer +
   `nav2_only_launch.py` bare-metal directly (the same ad-hoc pattern used all
   session) — NOT through `robot_boot.sh`'s real Docker container path. The arm64
   image `robot_boot.sh` actually pulls/runs was built BEFORE these fixes existed,
   so a real `robot_boot.sh` mission-mode run tonight would still hit the identical
   deadlock — the container needs a rebuild with tonight's commit before that path is
   provably fixed too. `robot_boot.sh`'s `NAV2_MAP_FILE`/`HSV_CONFIG_FILE` were ALSO
   fixed tonight to point at files that actually exist (`living_room.yaml` — Mike
   confirmed live this session it's the same physical room as `bedroom_real.yaml`,
   which doesn't exist; `hsv_gazebo.yaml` as an explicit A4 stand-in, since
   `hsv_realcam.yaml` still doesn't exist) — `bedroom_real.yaml`/A3 (real SLAM map)
   and `hsv_realcam.yaml`/A4 (real HSV calibration) both remain genuinely open, not
   fixed by tonight's work, just no longer silently crash-worthy placeholders.

**Retrospective, written same night while it's fresh — what could have caught
tonight's bugs earlier, and what to actually change:**

*What was real-hardware-only, no test could have caught it:* the `linear.x`/
`angular.z` sign inversions and the lidar's ~285° forward-bearing offset are
physical facts about THIS unit's wiring/mounting — no sim or static check can
know them in advance. These need a documented, once-and-done calibration record,
not a smarter test.

*What WAS structurally catchable, cheaply, and wasn't caught because nothing
looked:*
- **`robot_state_publisher` missing from the real boot chain** — a pure launch-
  graph completeness question (does the composed real-hardware launch actually
  include every node Nav2 config assumes exists), answerable by static analysis,
  zero ROS2 runtime needed. No test like this exists yet.
- **`base_laser` vs `lidar_link`** — a pure string-consistency question (does
  every `frame_id` a real-hardware launch file declares/remaps actually match a
  real URDF link name), also answerable by static analysis. No test like this
  exists yet either.
- **Three orphaned `ekf_node` processes contaminating a "clean" test** — this
  project already has the identical lesson on file for Gazebo
  (`src/nav_fleet/CLAUDE.md`, 2026-07-15) but it was never generalized to the
  bare-metal driver/Nav2 stack, so the same failure class recurred in a new
  location.
- **HIL is structurally blind to this entire bug class by design** — it always
  runs `use_sim_time=true`, so `sensors_only_launch.py`'s real-driver code path
  (and therefore any frame/RSP/global_frame bug in it) is simply never exercised
  by CI, ever. This isn't a gap in test QUALITY, it's a gap in what HIL is
  even capable of detecting.

**The bigger, generalizable miss: vendor specs and source were read reactively
(after hours of live debugging), not proactively (as an upfront bring-up
step).** `ld19.launch.py`'s own hardcoded `frame_id='base_laser'` — AND the fact
that it ships its own `base_link`→`base_laser` static transform, a real design
signal about how the vendor expects this wired — was only read tonight, under
pressure, as a last resort after hours chasing the deadlock another way. The
ESP32 firmware source has already produced multiple "reconstructed from source,
turned out wrong" bugs across sessions (protocol field-mapping backwards,
2026-08-10; the sign-convention entries here). The one clean counter-example:
the Waveshare vendor dimension drawing (`docs/img/waveshare_ugv_pt_dimensions.png`)
WAS read directly and correctly, upfront, during the A2 footprint task — proof
this project already knows how to do this well when it remembers to.

**Concrete changes worth making, roughly cheapest-and-highest-value first:**
1. A stage-1 (no-ROS2-runtime-needed) test that statically parses every
   real-hardware launch file composition and asserts each node Nav2's own
   config expects is actually present in the returned `LaunchDescription` —
   same bug class as the already-documented `DeclareLaunchArgument`-not-returned
   lesson (2026-07-26), one level up.
2. A stage-1 test that greps every real-hardware launch file's declared
   `frame_id` params/remappings against the real link names in
   `ugv_pt.urdf.xacro`, failing on any mismatch.
3. A pre-flight orphan sweep as a STANDING habit for any bare-metal Jetson
   testing (not just Gazebo) — mirror the existing `stage-2` sweep pattern for
   the driver/Nav2/EKF process names.
4. A single "physical calibration record" file (sign conventions, mount
   offsets, frame names) with a `last verified: <date>, method: <...>` field per
   fact — so a future session can't cite a stale, telemetry-inferred value as
   settled ground truth the way the 2026-08-10 `angular.z` entry was
   (see its own "CORRECTED 2026-08-11" annotation above).
5. When bringing up ANY new vendor package for the first time, read its actual
   launch/source files completely before writing the integration code that
   depends on it — not just when something breaks. Extract frame_id
   conventions, topics, any transforms IT publishes, and parameter defaults
   into the bring-up doc as a first step, not a debugging step.
6. A cheap, no-real-sensors-needed CI leg that launches the real-hardware
   launch files with `use_sim_time:=false` (mocking/stubbing the hardware
   inputs if needed) and asserts `map`→`odom` eventually publishes — closes the
   "HIL can't even in principle catch this" gap directly.

**Next session, in order:** (1) confirm THIS session's second push
(`5489ed4..?`, the 3 hardware-bug fixes above) goes green, `stage-4-hil`
specifically — check `gh run list` first before assuming; (2) re-run the
OFFICIAL `scripts/hil_stage.sh smoke <sha>` end to end for real, with Mike
physically present, now that all 3 known hardware bugs are fixed (the ad-hoc
scripts used to find/verify them today were deliberately narrower than a real
attended run — this is the first real proof the FULL path works with the
fixes in place); (3) rebuild the arm64 Docker image to include tonight's AMCL
deadlock fix (`robot_state_publisher`/`scan_masker` frame_id rewrite/
`use_sim_time` propagation/`local_costmap.global_frame`), then run a real
`scripts/robot_boot.sh` mission-mode test — the bare-metal ad-hoc test proved
the FIX, not yet the CONTAINER path production actually uses; (4) Mike's own
follow-up experiment, once (2) passes: rerun the smoke test with the yellow
ball placed WITHOUT the riser (floor/table level) and confirm the PREDICTED
failure mode — `camera`/`photo` still PASS, `ball_correlation` FAILs
specifically because the 2D lidar's fixed scan plane (~6in up) physically
cannot see a floor-level ball at any distance, regardless of width — a real
physics constraint, not a bug, worth directly demonstrating; (5) A4 (HSV
calibration — `hsv_realcam.yaml` still doesn't exist, only stood-in for now);
(6) A3 (a real SLAM map of the room — `living_room.yaml` is a real, confirmed
room match, but was never actually built as this robot's own SLAM output).

## (superseded 2026-08-11) PREVIOUS (2026-08-10 EOD — ESP32 odom/imu resolved, A2 essentially
complete (gimbal + scan FOV mask + footprint fixed, all live-verified), pushed, and
CONFIRMED FULLY GREEN end to end including a real HIL mission day — one real
previously-undiscovered boot-sequence gap found, still open)

**Picks up exactly where 2026-08-09 EOD left off: the ESP32 odom/imu blocker from
that session is resolved** (`435cedd`/`e5ac621`, root cause: `esp32_protocol.py`'s
T:1001/T:1002 feedback field-mapping had the two messages' shapes backwards —
confirmed by probing the real hardware directly with raw pyserial, not guessed).
Today continued A2 live, same terminal-in-hand-with-Claude-over-SSH mode as
yesterday, through 3 more checklist items plus a real, useful detour prompted by a
disaster-recovery question, then pushed everything (23 commits total,
`f09c949..d6f4198`) and drove the resulting CI run through 4 real, distinct
failures to a genuine fully-green finish — see the dedicated section below for
that whole arc; don't assume "pushed" alone means "proven" without reading it.

**A2 checklist — gimbal, scan mask, and footprint all done, TDD + live-verified:**
- **Pan-tilt gimbal (`encode_gimbal_cmd` + `tools/pin_gimbal.py`):** T:133 command
  confirmed live, Mike watching the physical mast for each move. Sign convention
  nailed down empirically (not from the web-search-sourced doc alone): X (pan)
  negative=left/positive=right, Y (tilt) negative=down (observed)/positive=up
  (inferred by symmetry).
- **Lidar FOV self-occlusion mask (`scan_filter.py` + `scan_masker.py`):**
  ldlidar_ros2's own `angle_crop` only masks one contiguous arc (confirmed against
  its real source) — this robot needs two, so a small custom node masks both
  (mast 46-123deg, WiFi antenna 268-277deg) and republishes `/robot_001/scan`
  directly, closing the LIDAR half of the topic-remapping gap as a side effect
  (camera half still open). **Both sectors found by real measurement, not
  guesswork:** placed a box+ball at a known bearing (directly in front, the same
  direction the pinned-forward gimbal looks) and read back the lidar's own bearing
  for it — found true forward is lidar bearing ~285deg, NOT 0deg as the static
  transform's zero-rotation assumption implied. The mast (physically confirmed
  opposite of forward) then predicted at 285-180=105deg landed right inside the
  independently-measured 46-123deg block — internally consistent, not a lucky
  guess.
- **URDF footprint (`ugv_pt.urdf.xacro`):** read the real vendor drawing directly
  (not from memory/transcription) — confirmed 253x231mm/289mm/126mm/25.13mm are
  all accurate. `base_length`/`base_width` were 0.35/0.30 (a real ~38%/~30%
  oversize, no basis found anywhere) — fixed to 0.253/0.231. Nav2's real safety
  param (`robot_radius: 0.24`) was independently confirmed still adequate by the
  math (171mm half-diagonal vs 240mm radius) — sim-collision-geometry fix only,
  not a navigation-safety change.
- **Quick rotation sanity check (Mike's ask, not a checklist item):** confirmed
  negative `angular.z` = turn right on the real hardware (matches REP-103),
  via direct-serial T:13 bursts with live T:1001 telemetry captured concurrently
  (not just visual observation). Found a real, uninvestigated ~1.2s delay between
  a velocity command and the wheels actually reporting motion in a short burst —
  not chased further (continuous Nav2 control sends cmd_vel repeatedly, unlikely
  to hit the same one-shot-burst artifact), but worth remembering if it resurfaces.
  **CORRECTED 2026-08-11 — this finding was WRONG, not a hardware change.** Live
  bench-smoke-test testing found the OPPOSITE: raw (uncorrected) positive
  `angular.z` physically turns the robot RIGHT, not left — repeated, direct visual
  confirmation with Mike watching, twice, at a large enough turn angle (~25-30deg)
  to be unambiguous (an earlier too-short 1s pulse gave an inconclusive-but-
  correctly-signed ~3deg result that wasn't trusted at the time). Root cause of the
  ORIGINAL wrong finding not established — it relied on "live T:1001 telemetry"
  interpretation rather than a large, unambiguous direct visual turn, and that
  telemetry-reading step is the most likely place an equivalent sign-confusion
  could have crept in unnoticed, given a real, independently-confirmed
  sign-inversion bug was ALSO found the same day in linear.x (see the boot-fix
  final-review section above) — but this is a plausible explanation, not a
  confirmed one. **Both `linear.x` AND `angular.z` are now negated in
  `esp32_driver.py`'s `_cmd_vel_cb` before reaching the firmware** (T:1001
  wheel-speed feedback is uniformly negated to match in `_publish_odom`) — live-
  verified on both axes simultaneously: a real forward move and a real ~25-30deg
  LEFT turn (now correctly commanded) both match what `/robot_001/odom` reports.
  Lesson for next time a "confirmed" hardware-convention finding needs trusting:
  prefer a large, unambiguous, DIRECT visual result over one that depends on
  reading raw telemetry back — telemetry interpretation is exactly the kind of
  step a sign-convention bug can hide inside undetected.

**Real, previously-undiscovered gap found tracing the boot path (NOT fixed —
flag this before trusting A6):** `robot_boot.sh` -> `container_entrypoint.sh`'s
`mission` branch -> `nav2_only_launch.py` only ever starts Nav2/EKF/`ball_detector`
— **nothing in that chain, or in `robot-mission.service`, ever starts
`sensors_only_launch.py`** (esp32_driver/lidar/camera/scan_masker). A real power-on
mission run today would bring up Nav2 expecting real sensor data with nothing
actually producing it. Every bring-up step so far has worked only because drivers
were started by hand over SSH each time. Needs a real fix before A6 is trusted.

**Disaster-recovery conversation (Mike's own framing: "robot gets hit by a bus,
new Jetson, fresh clone, run CI") led to a real, useful piece of work: 3 fragile
one-off shell recipes converted into versioned, idempotent repo artifacts** —
`scripts/install_lidar_driver.sh`, `scripts/udev/80-movidius.rules` +
`scripts/install_movidius_udev_rule.sh`, and the CycloneDDS large-message fix
folded permanently into `scripts/regen_cyclonedds_config.sh` (was bench-workaround
-only since 2026-08-09). All 3 verified live against the real, already-provisioned
Jetson (idempotent re-run correctly no-op'd already-applied patches). Caught a
real XML gotcha building the CycloneDDS fix: a `<!-- ... -->` comment body can
never contain a literal double hyphen — broke well-formedness on the first
attempt, fixed, see the Gotchas section below.
Also confirmed precisely (not assumed) that this Jetson's own GitHub Actions
runner checks out into `~/actions-runner/_work/...`, a directory completely
separate from `~/autonomous-fleet-testbed` — pushing and running CI will NOT
touch or overwrite the native dev checkout this whole bring-up has been using.

**The push + CI debugging arc — 4 real, distinct failures, all found via actual
logs (never guessed), all fixed, ending genuinely fully green (run
`31450359510`, all 8 jobs, including a real `stage-4-hil` mission day on the
Jetson):**
1. **`esp32_protocol.py` E128 flake8 error.** A real regression from yesterday's
   ESP32 fix (`435cedd`) that had simply never been through CI before (it sat
   unpushed) — I'd checked this exact line earlier the same session, correctly
   concluded "pre-existing relative to my own edits," and wrongly stopped there
   instead of checking it against the last GREEN CI baseline. One-space
   continuation-line fix (`fix: esp32_protocol.py E128...`).
2. **`pyserial` missing from `requirements-ci.txt`.** `tools/pin_gimbal.py`
   imports `serial` at module level with no rclpy dependency at all — its test
   was never flagged for stage-1's usual rclpy-based `--ignore` treatment, it
   just needed this one PyPI package stage-1's minimal install never pulled in.
   Verified the fix against a genuinely scrubbed environment (`env -i`, no
   inherited `PYTHONPATH`) matching stage-1's real bare-`ubuntu-latest`
   conditions — a first, non-scrubbed repro attempt gave a misleading, unrelated
   `lark` import error from leftover ROS2 env leakage.
3. **Jetson git-tree conflict.** `hil_stage.sh sync`'s plain `git checkout`
   correctly refused to overwrite today's whole day of `scp`-synced local state
   on `~/autonomous-fleet-testbed` (the exact directory this whole session's
   bring-up used) — every file byte-diffed identical to what the new commit
   already contained, so cleaned it directly (`git checkout --` the tracked
   ones, `rm` the untracked ones) rather than push a code change for an
   operational, not-a-bug issue.
4. **Workstation missing the CycloneDDS `net.core.rmem_max` bump.**
   `regen_cyclonedds_config.sh` runs on BOTH machines, and today's
   `SocketReceiveBufferSize min="10MB"` addition needed a matching OS-level
   sysctl on both too — I'd only ever verified/known about it on the Jetson
   (yesterday's bench work). Every ROS2 node in the HIL sim crashed instantly
   (`rmw_create_node: failed to create domain`) until Mike ran the matching
   `sudo sysctl -w net.core.rmem_max=2147483647` + persistent sysctl.d file on
   the workstation (I don't have sudo in this environment — handed him the
   exact command rather than trying to work around it).
Each fix was verified against the real failure (log excerpt or a genuine local
repro), never guessed-and-pushed. Issues #1-#2 were real code bugs, each needing
its own fix commit + new push (3 CI runs total: the original push, then one more
per fix). Issues #3-#4 were operational, not code bugs — fixed directly (cleaned
the Jetson's tree; had Mike run the sysctl command) and re-run IN PLACE via `gh
run rerun --failed` on that same third run, no new push either time (Mike's
explicit ask: no unnecessary extra CI runs) — that third run is `31450359510`,
the one that ultimately finished fully green.

**Next session, in order:** (1) fix the boot-sequence gap above (`robot_boot.sh`
needs to actually start `sensors_only_launch.py` somewhere) before trusting A6;
(2) fix the camera half of the remapping gap (lidar half already closed by
`scan_masker`); (3) run the bench smoke test for real — fully unblocked now, a
fresh arm64 image with everything through today is confirmed present and
working on the Jetson; (4) A3 (SLAM map) and A4 (HSV calibration,
`hsv_realcam.yaml` still doesn't exist) still untouched — note the smoke test's
ball-detection check will still be running against `hsv_gazebo.yaml` until A4
happens.

## (superseded 2026-08-10) PREVIOUS (2026-08-09 EOD — real physical robot arrived and bring-up
started LIVE; CI-side smoke-test fixes shipped + proven; hardware bring-up genuinely
in progress, one real blocker open)

**Two distinct threads finished/progressed today — CI-side fixes (done, pushed,
proven) and physical robot bring-up (started today, real progress, one open
blocker, nothing pushed yet).**

### Thread 1: check_ball_correlation + related CI fixes — DONE, pushed, proven green
Fixed three real bugs found live in CI (first-ever real exercise of the smoke-test
feature from the prior session): (1) camera FOV geometry at the original 12" distance
— raised to 0.75m; (2) 2D-planar lidar can't see a floor-level ball — spawns at lidar
height now; (3) check_topic()'s Hz gates had zero tolerance for real timing jitter —
added a 10% tolerance; (4) HIL-container ball_correlation can't reach Gazebo ground
truth (structural, not a bug) — now marked `skipped`, doesn't fail the run. **Full
pipeline (sim + real Jetson HIL) confirmed green multiple times**, most recently run
`31336300719`. Also: a live doc review found and fixed two real `RealRobotStartup.md`
gaps (`pull_ros_logs.py` silently stale for container-mode Nav2; the gimbal-control
section still said "do NOT install `ugv_ws`" 37 lines after also saying gimbal control
"depends on `ugv_ws`" — resolved via research: it's a `T:133` command over the SAME
serial protocol `esp32_protocol.py` already uses, not `ugv_ws`-specific, but not yet
implemented). All pushed to `origin/main` (last pushed: `f09c949`).

Also did a one-off Jetson cleanup this session (separate from the above): fixed
root-owned `~/fleet-ci-data` (known recurring issue, symptom-fixed again, root cause
— no `USER` in the Dockerfile — deliberately deferred, Mike's call, "everything's
working, more interested in moving forward"), cleared `~/.ros/log` (4.5G→48K, dead
since Nav2 moved into the container), pruned 5.7G of stale docker build cache.

### Thread 2: physical robot bring-up — STARTED LIVE TODAY, genuinely in progress
The robot physically arrived and Mike began `RealRobotStartup.md`'s A1/A2 live,
checkbox by checkbox, terminal-in-hand, with Claude debugging in real time via SSH.
**This found a LOT of real, previously-undocumented gaps — the doc went from "links
and vague pointers" to concrete, hardware-verified commands, several rounds, live.**
**10 commits, all doc-only (`RealRobotStartup.md`), all LOCAL ONLY — nothing from this
thread has been pushed. Check `git log origin/main..HEAD` first thing next session.**

Real findings, in the order hit:
- **A1 done**: CI green confirmed, power mode confirmed, `~/fleet-ci-data` ownership
  clean (from the cleanup above).
- **Native workspace build was never documented as a real prerequisite** — this exact
  Jetson checkout had genuinely never been `colcon build`'d (every prior HIL/CI run
  used the pre-built container image instead). Added as an explicit new A2 step. Two
  system packages it needs (`ros-jazzy-robot-localization`, `ros-jazzy-vision-msgs`)
  were already installed — nothing to do there.
- **Lidar (`ldlidar_ros2`) — fully verified working, real hardware, real data.** Three
  real build/runtime bugs found + fixed, all now documented with exact commands:
  rosdep never initialized on this Jetson; the SDK's `sdk/` dir is a git submodule a
  plain clone leaves empty; a genuine vendor bug (`#include <pthread.h>` commented out
  in the SDK's own `log_module.h`, confirmed against a known upstream GitHub issue).
  Plus two hardware-specific gotchas: this unit enumerates as `/dev/ttyACM0` (not the
  vendor's hardcoded default `/dev/ttyUSB0`), and needed the user added to the
  `dialout` group (`crw-rw---- root:dialout` device perms).
- **Camera (`depthai-ros`, OAK-D Lite) — fully verified working, real hardware, real
  data.** apt-installed cleanly. Needed a udev rule for the Movidius USB device
  (`03e7:2485`, same class of fix as `dialout` above, different mechanism) — confirmed
  a power-cycle re-applies udev rules via the boot-time coldplug pass, no need to
  physically find/replug the camera's jammed-in cable.
- **Real, project-wide-relevant bug found: CycloneDDS doesn't deliver uncompressed
  `sensor_msgs/Image` messages at all** (`ros2 topic hz` hangs indefinitely on
  `/oak/rgb/image_raw`/`image_rect`, while compressed siblings work immediately) — a
  known, documented ROS2/CycloneDDS large-message limitation, not a depthai-ros bug.
  **This will hit the real deployed robot too** — `ball_detector.py` subscribes to
  `/robot_001/camera/image_raw`, the identical topic class. Worked around for
  bench-testing only (`sysctl` + a one-off CycloneDDS XML file) — **NOT yet folded
  into `scripts/regen_cyclonedds_config.sh`, which is what the real container path
  actually uses.** This is a real, scoped, not-yet-started TODO: fix the script,
  re-verify via the FULL CI+HIL cycle (Ethernet-reconnected, same bar as Thread 1's
  fixes) before trusting it on the real robot.
- **`.bashrc` updated to auto-source both project workspaces** (matching the
  workstation's own convention) — verified working, but ONLY via a proper interactive-
  shell test (`bash -ic '...'`) — a naive `ssh host "command"` test gives a false
  negative here, since Ubuntu's default `.bashrc` has the identical
  `case $- in *i*) ;; *) return;; esac` early-exit guard documented elsewhere in this
  file for the workstation. Don't re-litigate this as "broken" without using that same
  test methodology.
- **ESP32 driver / odom+IMU — UNRESOLVED, stopped here for the night.** Connects via
  the Jetson's 40-pin header UART (`/dev/ttyTHS1` or `/dev/ttyTHS2`, not USB).
  `ttyTHS1` shows genuine electrical activity (likely an ESP32 boot-reset burst) and
  correct baud (115200, confirmed via `stty`) — yet `esp32_driver` run directly against
  it still produces zero messages on `/robot_001/odom`. Full diagnostic trail and the
  next-step plan (power-cycle first, untested — deliberately not attempted this late)
  are in `RealRobotStartup.md` itself now, not just here.
- **Not yet reached:** gimbal control (researched, not implemented — see Thread 1's
  doc-review note), the `sensors_only_launch.py` topic-remapping gap (pre-existing,
  still open), footprint verification, SLAM mapping, HSV calibration, and everything
  else past A2.

**Next session, in order:** (1) decide whether to push Thread 2's 10 local commits
before or after resuming — they're pure documentation of real findings, low-risk to
push anytime; (2) resume the ESP32/odom investigation starting with the power-cycle
Mike already planned; (3) once odom+IMU are confirmed, finish A2 (gimbal, footprint,
remapping fix — remapping needs the SAME full-CI+HIL treatment as the CycloneDDS fix,
both touch `sensors_only_launch.py`, worth doing together); (4) A3 onward (SLAM map,
HSV calibration) still untouched.

## (superseded 2026-08-09) PREVIOUS (2026-08-04 — docker-brain unification SHIPPED, merged, live-validated on real hardware; Task 9 closed)

**The whole docker-brain-unification effort (all 9 tasks) is done and merged to
`main`.** Implemented via subagent-driven-development in an isolated worktree (Tasks
1-8, each independently reviewed, plus two rounds of whole-branch review), merged
`feat/docker-brain-unification` → `main` same day, then pushed straight to CI
(deliberate call, skipping the plan's own manual-first Task 9 steps — see below for
why that was still the right call). Nav2/EKF/`ball_detector`/`mission_runner` now run
identically, via one container/one entrypoint (`scripts/container_entrypoint.sh`), on
both HIL and the eventual real robot — differing only by env-var values
(`use_sim_time`/`hsv_config`/`map`/self-report vs. judged).

- **First-ever fully green CI run including a real, live `stage-4-hil` on the actual
  Jetson** (run `30970690023`) — the container-based HIL path, container-based real-
  robot path, and the whole convergence this branch exists for are now proven on real
  hardware, not just on paper.
- **Pushing straight to CI (skipping manual Task 9 verification first) found 2 real
  bugs a manual-only path might have taken longer to catch** — both fixed live,
  same day, re-verified green:
  1. A stale pre-existing unit test (`tests/test_pipeline_matrix.py`) outside every
     diff any reviewer looked at, still asserting the pre-branch `bedroom_nav`
     scenario — `config/pipeline_matrix.yaml`'s `real` stage was correctly changed by
     Task 4, the test just never got updated. `stage-1-quality` caught it correctly.
  2. **`container_entrypoint.sh` crashed immediately (1.7s, before Nav2 ever started)**
     — `/opt/ros/jazzy/setup.bash: line 8: AMENT_TRACE_SETUP_FILES: unbound variable`.
     ROS2's own `setup.bash` isn't `set -u`-safe; `hil_stage.sh`'s `sim_up()`/
     `ws_source()` already work around this exact issue (`set +u` bracketing the
     source calls) — this brand-new file just never inherited that guard. Nothing in
     Task 3's manual verification (`docker buildx build` succeeding) could have caught
     this, since that only proves the image builds, not that the entrypoint runs. Fix:
     same `set +u`/`set -u` bracket, matching the established pattern exactly.
  A separate, one-off infra hiccup also hit `stage-3-arm64` mid-session: a GHCR push
  got stuck on a genuinely dead, half-closed TCP connection (`FIN-WAIT-1`, confirmed
  via `ss`) — not a code issue, not GHCR being down (direct `curl` to `ghcr.io/v2/`
  was healthy throughout) — cancel + rerun fixed it immediately. Worth knowing this
  failure mode exists if `stage-3-arm64` ever hangs post-build-step with no forward
  log progress for several minutes.
- **GUI-watched runs, both sim and HIL, done live with Mike watching, both fully
  PASS** (all 3 legs, no_ball/yellow/red) — results saved for comparison at
  `~/fleet-ci-data/{sim,hil}_gui_comparison_2026-08-04/` (log + photos + telemetry
  rows each). Yellow leg's `home_photo_similarity` matched almost exactly between sim
  and HIL (0.033 vs 0.034); `no_ball` diverged more (0.112 vs 0.029) — not flagged as
  a problem by either run's own judging, just a real difference worth knowing exists.
  Ollama/VLM canary fired successfully on all 4 runs checked (2 CI, 2 manual),
  correctly identifying "a red ball" every time, zero errors — confirmed the
  `--ingest-vlm-canary` step is CI-only, `hil_stage.sh day` doesn't call it on its own
  (a manual HIL run's canary result needs that step run by hand or it's stranded on
  the Jetson).
- **Task 9 closed, deliberately, with Step 2 not completed — decided with Mike, not
  a gap to revisit:** Steps 1/3/4 (build-on-Jetson / full HIL day / push+CI-proof) are
  genuinely done, on real hardware. Step 2 (an isolated container run with
  `MISSION2_SELF_REPORT=1`, no Gazebo, no real robot) was attempted twice — first
  attempt was contaminated by a leftover HIL Gazebo simulation from an earlier
  run that never got torn down (a real process-hygiene mistake, not a product bug —
  the still-running workstation Gazebo's live camera bridge fed the "isolated"
  container a real detection of its own leftover red ball); teardown fixed that, but
  the clean rerun then hit a genuine wall: **Nav2 never reaches "active" at all with
  zero sensor input of any kind** (no camera, no lidar, no odometry — `local_costmap`
  times out after 120s unable to get the `map` transform, since AMCL/EKF have nothing
  to localize against). Building a stub sensor source just to unblock this would
  amount to reinventing Gazebo badly — Mike's call, and the right one: not worth it.
  `mission_runner`'s actual self-report telemetry code path (the thing Step 2 was
  meant to validate) was therefore never exercised by either attempt — genuinely
  inconclusive, not proven, not a real risk either (the actual deployed robot will
  have real sensors, so this specific "zero sensors at all" failure mode shouldn't
  occur there). The self-report path's real validation waits for the actual physical
  robot.

**What's next (no urgency, no firm date — whenever the physical robot is ready):**
`RealRobotStartup.md` Part A (one-time setup: real SLAM map, real-camera HSV
calibration via `calibrate_hsv_realcam.py`, install `robot_boot.sh` +
`robot-mission.service`) then Part B (day-to-day operation) — this is the only
remaining piece that needs the actual hardware. Nothing else is blocking. Older,
lower-priority backlog items (Release 1→2 branching/tagging, self-hosted-runner CI
docs) are unrelated carryover from before this session, still open, not urgent.

## (superseded 2026-08-04) PREVIOUS (2026-08-03 evening — docker-brain implementation, Tasks 1-4 of 9 done)
**Spec reviewed/approved earlier this session** (with two real deviations from the
original spec text, decided live with Mike — see below), **implementation plan
written and execution started via subagent-driven-development, 4 of 9 tasks
complete.** Work is happening in an isolated git worktree, NOT on `main`:
`/home/mike/autonomous-fleet-testbed/.worktrees/feat/docker-brain-unification`
(branch `feat/docker-brain-unification`) — `cd` there to resume, don't redo this
work on `main`. Nothing has been pushed anywhere.

- **Plan:** `docs/superpowers/plans/2026-08-03-docker-brain-real-robot-hil-unification-plan.md`
  (9 tasks, already committed to `main` and inherited by the worktree).
- **Ledger (full task-by-task history, gitignored — worktree-local, not on `main`):**
  `.worktrees/feat/docker-brain-unification/.superpowers/sdd/progress.md`.
- **Done, each independently reviewed (spec + quality) via the subagent-driven-development
  loop, all Approved:** Task 1 (`nav2_only_launch.py` launch args), Task 2
  (`mission_runner.py` self-report telemetry for the real robot), Task 3 (Dockerfile +
  new `scripts/container_entrypoint.sh` — real arm64 build verified, ~39 min under QEMU
  emulation on this workstation since the Jetson runner wasn't used for this manual
  check), Task 4 (`pipeline_matrix.yaml` real-stage scenario fix — was stale, still
  pointing at the old BR-01 gate).
- **Real bug found + fixed along the way:** a `grep -c ... || echo 0` double-print bug
  in `container_entrypoint.sh`'s Nav2-readiness wait loop (the plan's own transcribed
  code carried this forward from an existing, unrelated bug already present in
  `robot_boot.sh`) — fixed to match `hil_stage.sh`'s already-correct pattern, re-reviewed
  clean. **`scripts/robot_boot.sh` itself still has this same bug on `main` today,
  unfixed** — Task 6 (below) replaces that file's Nav2-wait loop entirely with a
  container invocation, so it'll disappear there as a side effect, not a targeted fix;
  worth confirming that actually happens when Task 6 lands.
- **Two important deviations from the design spec doc's literal text, decided live with
  Mike this session, NOT yet folded back into the spec file itself** (the spec doc at
  `docs/superpowers/specs/2026-08-03-docker-brain-real-robot-hil-unification-design.md`
  still describes the ORIGINAL, wider idea — reading the spec doc alone would be
  misleading; the plan doc's own "Global Constraints" section has the real, current
  decision):
  1. Ball placement, ground-truth reading, and judging (`tools/mission2_harness.py`)
     stay workstation-side for HIL, unchanged from today — NOT moved into the
     container's self-orchestration as the spec originally described. Reason: they use
     `gz`/Gazebo-transport, a separate protocol from CycloneDDS with unverified
     cross-machine reachability, and that harness code never runs on the real robot
     either way (no Gazebo there) — so moving it wouldn't actually converge HIL with
     the robot, just add unproven risk.
  2. The real robot does NOT get ground-truth judging at all (impossible — no Gazebo,
     no oracle) — it self-reports each leg's own PASS/FAIL and saves logs/photos;
     analysis happens after, manually, not in real time.
  Consider updating the spec doc itself to match, or at least adding a pointer at its
  top to the plan's Global Constraints section, before this is forgotten.
- **Remaining, in order:** Task 5 (`JetsonExecutor`/`hil_stage.sh` → always-container
  HIL, the biggest remaining piece — retires the bare-metal Nav2-on-Jetson path
  entirely), Task 6 (`robot_boot.sh`/`robot-mission.service` rewrite), Task 7 (`ci.yml`
  cleanup — drop the now-dead `HIL_CONTAINER` env var), Task 8 (`RealRobotStartup.md`
  doc updates — A5/A6 + intro item 2), Task 9 (manual hardware-verification
  checkpoints — needs live Jetson access, cannot be subagent-dispatched, needs Mike or
  a session with real SSH access to the robot).
- **Known process-hygiene lesson from this session, worth carrying into future
  subagent-driven-development dispatches in this repo:** an implementer subagent left
  orphaned `gz sim`/`robot_state_publisher` processes running after its own manual
  live-ROS verification step — the controller had to sweep them by hand
  (`CLAUDE.md`'s own documented teardown pattern). Future dispatch prompts for any task
  that launches Gazebo/Nav2 should explicitly include a teardown/sweep step, not just a
  check-before-launch step.

**Summary of the decision this spec captures:** reverses the 2026-08-01 bare-metal-
end-to-end call — item 1 of that session's punch list ("does `stage-3-arm64` still
earn its keep") got a real answer: yes, restructured. Nav2/EKF/`ball_detector`/
`mission_runner`/`mission2_day` all move into one Docker container long-term (driver
layer stays bare, Ollama stays bare); HIL and the real robot converge onto the exact
same container entrypoint and the exact same `nav2_only_launch.py` (parameterized by
3 new launch args — `use_sim_time`/`hsv_config`/`map` — not a separate
`robot_launch.py` file); the biggest single piece of rework is HIL's own orchestration
moving from workstation-SSH-dispatch onto the Jetson's own container, matching how
the real robot already has to run. Mike's explicit framing for this reversal: decide
on long-term architectural merit for the fleet testbed's future, not on which
direction avoids rework — read the spec's own "Context" section for the full
reasoning, and its "Known implementation-time risks" section before starting
implementation.

## (superseded 2026-08-03) PREVIOUS (2026-08-01, evening session — real robot deploy rewrite)
**Item 1, first thing next session (Mike's explicit ask): review the docker/no-docker
decision and review what real value `stage-3-arm64` is providing.** This session found
(see `docs/bare-metal-vs-container-decision.md` for the full writeup, and the
`RealRobotStartup.md` rewrite) that the container role HIL actually proved was always
narrower than the original 2026-07-27 "containerized brain" decision — only the raw
`mission_runner.py --day` ROS2 loop ever runs in a container, never Nav2/EKF/
`ball_detector`, and the real robot's own deployment (`scripts/robot_boot.sh`) ended up
bare-metal end to end, not using the Docker image at all. Given that, is `stage-3-arm64`
(the native arm64 build, ~10 min of the pipeline) still earning its keep, or has its
actual value shrunk now that the real robot doesn't consume its output? Concretely to
revisit: does `stage-4-hil` still need the arm64 image at all (currently gates
`HIL_CONTAINER=1`'s mission_runner-in-container run), or could HIL also move to running
`mission_runner.py --day` bare, matching what the real robot now does — collapsing two
divergent "how does the mission actually run" paths into one? Not decided, not started —
this is the open question to bring to Mike, not a predetermined answer.

Also carried forward, not yet started: item 4 (Release 1 → Release 2 planning — branching
strategy, `r1-complete` tag now real per the deploy rewrite above) and item 6 (GitHub CI
pipeline docs, self-hosted runner setup writeup) from the prior punch list below.

**This evening's session, full summary:** `RealRobotStartup.md` fully rewritten (was
last-verified 2026-07-28, materially stale against everything hardened since — WiFi/DDS/
avahi fixes, HIL hardening's 6 fixes, container-mode findings). Real-time collaborative
correction with Mike caught several wrong assumptions before they got written down:
mission target moved from BR-01/`test_navigation.py` to the mission2 3-leg day
(`sim_vs_real_comparison.py`'s correlation gate dropped entirely — log/drift analysis is
R2 scope per Mike); the architecture is bare-metal end to end (not the originally-planned
containerized brain, corrected mid-conversation after tracing the ACTUAL `nav2_up()`/
`JetsonExecutor` code, not the plan doc); power-on now fully automates the mission via a
new `scripts/robot_boot.sh` + `scripts/robot-mission.service` (systemd, `network-
online.target`-gated) — NOT yet exercised by CI/HIL (can't simulate a power cycle there),
manual-first-then-systemd is the explicit safety pattern in the doc. New: `tools/
calibrate_hsv_realcam.py` (+ 4 tests) — a real, previously-missed gap, since mission2's
yellow/red legs need real-camera HSV thresholds that never mattered under the old
BR-01-only gate. `docs/bare-metal-vs-container-decision.md` is a new standing reference
(the honest architecture-drift story, written for reuse — design reviews, interview prep).
**Nothing in this session has been pushed** — Mike wanted to log off; everything is
committed locally on `main` only, push next session after a final look.

## (superseded 2026-08-01 evening) PREVIOUS (2026-08-01, paused mid-Item-3, machine-safety pause)
Session continued the 2026-07-31 punch list. Items 1 and 2 fully closed out today
(details below and in the dated Gotchas). Item 3 (real code coverage) is IN PROGRESS —
deliberately paused, not blocked on anything code-related, purely because the
workstation (this repo's self-hosted CI runner) is unsafe to run Gazebo on right now —
see the new dated Gotchas entries below before resuming. Punch list for next time, in
order:
1. ~~**Remove the duplicate mission2 tests from stage-2.**~~ **Done 2026-08-01.**
   `tests/test_mission2.py` (the 3 old per-scenario no_ball/yellow/red tests) deleted
   outright — confirmed redundant with `tools/mission2_day.py`'s in-process run
   already in the same stage (same 3 legs, same judging, plus VLM canary coverage the
   old tests never had). Every reference across `ci.yml`, `README.md`,
   `tools/mission2_harness.py`, and `src/nav_fleet/CLAUDE.md` updated or repointed at
   `mission2_day.py`. **Audit of the rest of stage-2's suite (`test_navigation.py`,
   `test_mission_run.py`, `test_nav_runner.py`) — conclusion: nothing else moves.**
   `test_nav_runner.py`/`test_mission_run.py` mock out Nav2 itself (no live Gazebo
   needed for their own logic), but all 4 files still `import rclpy` at module level,
   and `stage-1-quality` (bare `ubuntu-latest`) never installs `rclpy` — only the
   ROS2 apt repo + `ros-jazzy-ament-*` lint tools, confirmed by reading that job's
   steps directly. Moving any of them would require installing full ROS2
   (`ros-jazzy-ros-base`+) in stage-1, which defeats its whole "cheap/fast feedback"
   purpose — not done. Already optimally split as-is.
2. ~~**Revisit CI + PDF output.**~~ **Done 2026-08-01.** Sim PDF (`sim-report-159-DRIFT.pdf`)
   confirmed correct: VLM canary text appears exactly once, under `mission2_red`'s own
   section, never duplicated into `no_ball`/`yellow`. The HIL PDF (`hil-report-159.pdf`)
   check found a REAL bug, not just an unfinished verification: `ingest_vlm_canary_
   from_jetson()` (`tools/mission2_day.py`) was joining the wrong photo directory
   (`state_dir` instead of `PHOTO_DIR`) — a copy of the reaction-red photo exists in
   BOTH directories with the same basename but a different absolute path, and
   `find_vlm_canary_results()`'s exact-string join silently matched nothing. Confirmed
   directly against the real `fleet_runs.db` (run 690): the `photos` column and
   `vlm_canary_log.photo_path` pointed at two different directories for the same
   photo. Every HIL PDF report has shown ZERO canary text since the feature shipped
   2026-07-31, even though the canary genuinely ran and was ingested every time. Fixed
   with a one-line change (glob `PHOTO_DIR`, not `state_dir`), TDD throughout (test
   rewritten to prove the bug RED, fix confirmed GREEN, full 435-test suite still
   green) — commit `bba663b`.
3. **Real code coverage — CI wiring done + validated 2026-08-01, pure-local (no
   third-party site).** A Codecov-hosted design was built first, then dropped the
   same day — pushing real coverage data to an external site "did not sit well"
   with Mike (his words), and a live CI run had already surfaced that Codecov's
   tokenless upload doesn't actually work for this repo by default anyway (`error
   -- Upload queued for processing failed: {"message":"Token required - not valid
   tokenless upload"}` — confirmed from the real job log, not assumed from docs).
   Rebuilt entirely on `coverage.py`'s own built-in `coverage combine` instead —
   still `pytest-cov`, no new dependency, no network call, no token.
   **How it works:** `.coveragerc` (repo root) scopes measurement to `tools/` +
   `src/nav_fleet/nav_fleet/` and omits the 3 hand-invoked hardware debug scripts
   (`calibrate_ball_range.py`, `direct_drive_test.py`, `ghcr_prune.py`). `stage-1-
   quality` and `stage-2-gazebo` (the latter via `coverage run -a` across BOTH the
   pytest integration tests AND the in-process `mission2_day` run, so the VLM-
   canary code path is covered too, not just what pytest touches) each save their
   own `.coverage` data file (renamed `.coverage.stageN`) as a GitHub Actions
   artifact. A new job, **`coverage-report`** (needs `stage-2-gazebo`, runs even on
   a stage-2 FAILURE — best-effort, same pattern as `stage-5-reports-hw`),
   downloads both artifacts, computes each stage's own % via `COVERAGE_FILE=` env
   overrides, then `coverage combine` for the REAL merged total (not double-counted
   — the two stages run non-overlapping test files, confirmed by the Item 1 audit).
   `coverage html` is uploaded as a `coverage-html-<run>` artifact (download,
   unzip, open `index.html` — the browsable view, no hosted dashboard needed).
   Each stage plus the combine job also writes a ONE-LINE `$GITHUB_STEP_SUMMARY`
   pointer only, never the full report, per the confirmed Summary-tab mis-caching
   bug Gotcha.
   **Trend history: `tools/coverage_log.py`** (new, TDD, 6 tests, same isolated-
   table-in-`fleet_runs.db` convention as `diagnosis_log.py`/`vlm_canary.py` —
   `coverage_runs` table, `log_coverage_run()`, a `--db`-flag CLI). The
   `coverage-report` job's last step calls `python -m tools.coverage_log
   --stage1-pct ... --stage2-pct ... --combined-pct ... --commit-sha
   ${{ github.sha }} --ci-run-number ${{ github.run_number }}` — logged into the
   SAME self-hosted DB every other telemetry tool already reads/writes, not a new
   system. `dashboard/app.py` gained a 6th tab, **Coverage** — 3 metric tiles
   (latest stage1/stage2/combined %), a trend line chart (`load_coverage_history()`,
   guarded for the table not existing yet on a fresh/pre-feature DB — catches BOTH
   `sqlite3.OperationalError` and `pd.errors.DatabaseError`, since pandas wraps the
   former as the latter and that wrapping isn't guaranteed across pandas
   versions/connection types — found live, not assumed, see below), and a run-log
   table. **Verified live via Playwright both ways** (this file's own dashboard/
   CLAUDE.md precedent — zero automated pytest coverage for `app.py` by design):
   once against a throwaway DB copy seeded with fake trend rows (real chart, real
   metrics, no crash) and once against the REAL production DB, which doesn't have
   `coverage_runs` yet (empty-state info message, no crash) — this second pass is
   what caught the `sqlite3.OperationalError`-only guard being wrong; a naive
   `pd.read_sql` against a missing table actually raises `pd.errors.DatabaseError`,
   confirmed from a real traceback, not from memory of how `vlm_canary.py`'s
   different (`conn.execute`, not `pd.read_sql`) guard behaves.
   **Two real bugs found + fixed getting the pure-local `coverage-report` job
   itself to a genuine green run, both root-caused against real CI artifacts, not
   guessed:**
   1. **`actions/upload-artifact@v4`'s glob matcher silently skips dotfiles.**
      `mv .coverage .coverage.stage1` succeeded and `coverage report` printed a
      real 66% right before it, but the upload step logged `"No files were found
      with the provided path: .coverage.stage1. No artifacts will be uploaded"`
      and uploaded nothing (confirmed via the run's real artifact list — no
      `coverage-data-stage1`/`2` existed at all). Fixed by dropping the leading
      dot everywhere (`coverage.stage1`/`coverage.stage2`) — `coverage combine`
      takes explicit filenames as arguments, so the name never needed to match
      any convention.
   2. **Coverage data files record ABSOLUTE source paths — combining data
      collected on two different machines breaks reporting.** `stage-1-quality`
      runs on a GitHub-hosted `ubuntu-latest` runner (`/home/runner/work/...`);
      `stage-2-gazebo`/`coverage-report` run on the self-hosted runner (a
      different absolute checkout path). Once bug 1 was fixed and the artifacts
      actually downloaded, `coverage report`/`combine` failed with `"No source
      for code: /home/runner/work/autonomous-fleet-testbed/.../__init__.py"` —
      reproduced locally against the REAL downloaded artifacts (`gh run download
      <run> -n coverage-data-stageN`) before touching `.coveragerc` again, ruling
      out a coverage.py VERSION mismatch first (hosted runner's fresh `pip
      install` got 7.15.2, self-hosted `~/fleet-env` has 7.14.3 — tested
      cross-version combine directly, it worked fine, not the cause). Fixed with
      a `[paths]` section in `.coveragerc` (coverage.py's documented mechanism
      for exactly this multi-machine scenario) remapping either machine's
      absolute prefix back to the relative path — verified end-to-end against
      the real downloaded artifacts before re-pushing (STAGE1_PCT=66,
      STAGE2_PCT=31, COMBINED_PCT=82, `coverage html` succeeds).
   **Lesson for next time this bites:** when a CI step fails with no visible
   error text between two log lines, don't assume `set -e` swallowed something —
   download the run's REAL artifacts (`gh run download`) and reproduce locally
   with the actual data before touching config; both bugs here needed exactly
   that to root-cause instead of guessing from the step names alone.
   Below is prior-session context (still accurate — this pivot only changed HOW
   the numbers get combined/reported, not what was measured):
   `pytest-cov` is already a dependency — no external service needed to get a real
   number locally.  Numbers gathered so far:
   - Stage-1-only subset (pure Python, no ROS): **62%** (`tools/` + `src/nav_fleet/nav_fleet/`).
   - + `test_nav_runner.py` (mocked ROS, no Gazebo needed): **67%**.
   - Full suite (all 3 live-ROS files via real Gazebo) attempted twice — **both runs
     produced unreliable numbers, DO NOT trust either one.** Root causes found (see the
     two new dated Gotchas below): a real test-ordering fragility in
     `test_nav_runner.py`'s rclpy teardown, AND a live, concurrent `synthetic-fleet`
     Gazebo/Nav2 session sharing this exact machine's `/robot_001` DDS namespace at the
     time — found mid-investigation, session paused there rather than fight through it.
   - **Resume checklist:** (1) confirm no OTHER Gazebo/Nav2 session is running on this
     machine — `pgrep -fa "gz sim|robot_state_publisher"` and check the launching
     PROJECT PATH in the command line, not just process existence (`synthetic-fleet`
     vs `autonomous-fleet-testbed` look identical at the process-name level); (2)
     confirm no CI run is in-flight (`gh run list`) since a push auto-triggers CI on
     this same self-hosted machine; (3) launch fresh, wait for "Managed nodes are
     active"; (4) run the CI-safe-ORDER invocation from the test-ordering Gotcha below
     (NOT a naive `pytest tests/` — that reorders `test_nav_runner.py` before
     `test_navigation.py` and silently breaks the shared rclpy context).
   - **Decided with Mike (2026-08-01), later SUPERSEDED same day:** the original plan
     here was Codecov as a hosted reporting layer (trend history + PR diff-coverage),
     README badge deferred. **Reversed later the same session** — see the pure-local
     `coverage combine`/`coverage-report`-job/`tools/coverage_log.py`/dashboard design
     above, which is what's actually built. What DID survive the reversal unchanged:
     coverage collection spans BOTH stage-1 and stage-2 (non-overlapping test files —
     stage-2 doesn't re-run stage-1's own tests), NOT stage-4-hil (doesn't invoke
     pytest at all — runs `mission_runner.py --day` directly over SSH on the Jetson —
     would just re-measure the same lines stage-2 already covers via a different
     executor, not teach us anything new); and the `.coveragerc` omit list for the
     one-off manual CLI tools (`calibrate_ball_range.py`, `direct_drive_test.py`,
     `ghcr_prune.py`) so they don't drag the headline number down — they're
     hand-invoked hardware debug scripts, never meant to be unit-tested.
4. Release 1 → Release 2 planning (branching strategy, `r1-complete` tag).
5. ~~`RealRobotStartup.md` accuracy check~~ **Done 2026-08-01 evening** — full rewrite,
   see the NEXT SESSION block above for the summary.
6. GitHub CI pipeline docs (self-hosted runner setup writeup).

## Development workflow — tier 1 first

**Primary dev loop (x86 bare metal — use this to flush bugs before touching CI):**
```bash
colcon build --symlink-install          # ~1s — build the ROS2 package
source install/setup.bash
python -m pytest tests/ -v \
  --ignore=tests/test_ros2_contracts.py \
  --ignore=tests/test_navigation.py \
  --ignore=tests/test_mission_run.py \
  --ignore=tests/test_nav_runner.py    # seconds — run Python unit tests
ros2 launch nav_fleet sim_launch.py    # Session 09+ — Gazebo + Nav2 locally
# nav_runner, metrics_collector, drift check all run here
```

x86 is not the robot's target OS but finds 90% of bugs at ~1s build vs 23 min QEMU.
Commit to CI only when the x86 pipeline is clean.

## Environment
- Ubuntu 24.04 bare metal (dual boot with Windows 11)
- ROS2 Jazzy + Gazebo Harmonic + CycloneDDS
- Python virtualenv: ~/fleet-env (activate before running Python tools)
- Colcon workspace: ~/autonomous-fleet-testbed/ (build from here)
- `ros-jazzy-robot-localization` (ekf_node) required on BOTH machines since Session 16 —
  workstation + Jetson (`sudo apt install ros-jazzy-robot-localization` on a rebuilt Jetson)
- `ros-jazzy-vision-msgs` required on BOTH machines since Session 16 Plan B (ball_detector) —
  `sudo apt install ros-jazzy-vision-msgs`

## Key Commands
```bash
# New terminal — .bashrc auto-sources ROS2, CycloneDDS, fleet-env, and workspace overlay.
# Only need to build + launch:
colcon build --symlink-install
ros2 launch src/nav_fleet/launch/sim_launch.py   # Session 09+ — Gazebo locally

# Run Python unit tests (venv auto-activated by .bashrc)
python -m pytest tests/ -v --ignore=tests/test_ros2_contracts.py \
  --ignore=tests/test_navigation.py --ignore=tests/test_mission_run.py \
  --ignore=tests/test_nav_runner.py

# Run a mission (repo root; sim must be up — see launch commands above)
python -m nav_fleet.mission_runner mission1

# Traceability gate
python tools/check_traceability.py requirements/traceability.yaml tests/ \
  --profile robot_profiles/jetson_ugv_pt.yaml

# Code coverage — stage-1 (unit) subset, safe to run anytime, no Gazebo needed.
# .coveragerc (repo root) scopes to tools/ + src/nav_fleet/nav_fleet/, omits the 3
# hand-invoked hardware debug scripts. CI mirrors this exact invocation for its own
# stage-1 number; the real combined stage-1+stage-2 total (via `coverage combine`,
# pure-local, no third-party site) only exists in CI's coverage-report job — not
# locally runnable in one shot (stage-2's half needs live Gazebo — see the
# shared-machine gotcha before running that locally).
python -m pytest tests/ --ignore=tests/test_ros2_contracts.py \
  --ignore=tests/test_navigation.py --ignore=tests/test_mission_run.py \
  --ignore=tests/test_nav_runner.py -k "not integration" \
  --cov=tools --cov=src/nav_fleet/nav_fleet --cov-report=term-missing
# Browsable HTML instead of the terminal table:
coverage html && xdg-open htmlcov/index.html
# Combined stage-1+stage-2 trend + browsable HTML report:
# - trend/latest numbers: streamlit dashboard, Coverage tab (below)
# - full browsable report: download the coverage-html-<run> artifact from any CI
#   run's coverage-report job, unzip, open index.html

# Dashboard
streamlit run dashboard/app.py

# arm64 Docker build (Tier 2 — only after Tier 1 is clean)
docker buildx build --platform linux/arm64 \
  --tag ghcr.io/sdfinn/autonomous-fleet-testbed:latest --load .
```

## Directory Layout
- `src/nav_fleet/` — ROS2 colcon package (nav runner, metrics collector, Nav2 launch
  files). Package internals and Nav2 launch gotchas: `src/nav_fleet/CLAUDE.md`.
- `tools/` — Python utilities (baseline monitor, telemetry logger, etc.), including the
  telemetry DB and `reports/` conventions. Details: `tools/CLAUDE.md`.
- `dashboard/app.py` — Streamlit telemetry dashboard. Details: `dashboard/CLAUDE.md`.
- `scripts/` — Isaac Sim scripts (`isaac_bedroom_gui.py` etc.) and `hil_stage.sh`. Isaac
  Sim gotchas: `scripts/CLAUDE.md`; the manual GUI nav-test procedure is the
  `isaac-gui-nav-test` skill.
- Jetson Orin Nano hardware (flashing, power modes, SSH/mDNS): the `jetson-hardware-notes`
  skill.
- `requirements/`   — Traceability matrix and requirement specs
- `docs/`           — architecture review notes, simulation-environments writeup, project
  overview slide deck (`autonomous-fleet-testbed-overview.pptx`, python-pptx generated)
- `.github/workflows/ci.yml` — CI pipeline (job keys renumbered 2026-07-10 to match
  execution order — Gazebo is `stage-2-gazebo`, arm64 is `stage-3-arm64`, both gate
  `stage-4-hil`, real-hardware-in-the-loop on the Jetson runner; `stage-4-isaac` was
  retired in Session 16 — if older docs/notes say `stage-4-isaac` or
  `stage-2-arm64`/`stage-3-gazebo`, that's pre-Session-16/pre-2026-07-10 naming)
- `GazeboCommands.md` — Gazebo viewer navigation cheat sheet
- `docs/runbooks/Mission1HILSession15.md` — Session 15 Mission 1 hardware-in-the-loop runbook (Jetson +
  Gazebo terminal procedure) and the first real HIL run's Results (2026-07-11, PASS)
- `RealRobotStartup.md` — the real-robot bring-up runbook. Part A = one-time setup
  (driver bring-up, SLAM map, `robot_launch.py`); Part B = the repeatable day-to-day
  loop, including the physical Jetson swap required to get back into HIL mode
  (confirmed single-Jetson deployment, no dedicated CI runner).
- **`/home/mike/BC/isaac_project`** (outside this repo, not migrated) — has more reference
  material than what was pulled into this project. Notably `src/behavior_controller.py`
  (HSV color-threshold ball detection — proven, hardware-validated, zero training data) and
  `src/nav_controller.py` (the reactive coverage/avoidance mission it drives). `MasterBrief.md`
  in that same directory describes a fancier YOLO+ArUco design that was **never actually
  built** — don't trust that file over the real code when the two disagree (found 2026-07-10).

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
- DB path env var is `FLEET_DB` (default: `~/fleet-ci-data/fleet_runs.db`, owned by
  `tools/telemetry_logger.DB_PATH` — Session 17 Foundation piece, 2026-07-21; previously
  each of 6 files redeclared its own default independently, which is exactly how it
  drifted out of sync with CI's real path for 5 sessions) — used by telemetry_logger,
  validate_telemetry, dashboard, baseline_monitor, generate_test_report, agentic_loop
  (ai_test_generator/scenario_analyzer deleted 2026-07-19 — S17 review CR-05, rebuilt
  fresh in R2). `FLEET_TELEMETRY=off` skips writing a telemetry row entirely.
- **`ANTHROPIC_API_KEY` in `.bashrc` doesn't reach non-interactive shells/tools.** Ubuntu's
  default `.bashrc` has an early guard (`case $- in *i*) ;; *) return;; esac`) that skips
  the entire rest of the file when the shell isn't interactive — which includes Claude
  Code's own Bash tool. `source ~/.bashrc` there silently does nothing past that guard, so
  any export added below it (e.g. `ANTHROPIC_API_KEY` for `tools/agentic_loop.py`) never
  takes effect. Workaround for a non-interactive shell: `eval "$(grep '^export
  ANTHROPIC_API_KEY' ~/.bashrc)"` — targeted, doesn't print the key. Real terminals
  (interactive) are unaffected and work fine as-is. Two related env-var switches added
  2026-07-28 in `tools/agentic_loop.py`: `AGENTIC_BACKEND` (default `'claude'`; set to
  `'ollama'` to use a local model instead) and `OLLAMA_MODEL` (default
  `'qwen2.5:14b-instruct'`, only consulted when the Ollama backend is selected).
- `tests/test_ros2_contracts.py` requires a live ROS2 environment — always `--ignore` it in local pytest runs
- `tests/test_navigation.py` also requires a live ROS2 environment (`import rclpy` at module
  level) plus a running Gazebo/Isaac + Nav2 stack — same treatment as `test_ros2_contracts.py`
  above. It was added in Session 10 but never added to `stage-1-quality`'s `--ignore` list in
  `ci.yml`, which silently broke that stage on a bare `ubuntu-latest` runner (no ROS2 at all)
  until Session 11/12 caught it. It's correctly run as an integration test in
  `stage-2-gazebo`/`stage-4-isaac`, where live ROS2 actually exists. If a new test file imports
  `rclpy` at module level, it needs the same `--ignore` treatment in `stage-1-quality` — this
  has now bitten twice. `tests/test_mission2.py` (Session 16+ Plan B camera-reactive Mission 2)
  is the same shape — live ROS2 + a running sim — and got the `--ignore` treatment in
  `stage-1-quality` up front this time (commit 0b77e10), correctly running instead as an
  integration test in `stage-2-gazebo`. (File itself removed 2026-08-01 as redundant
  with `tools/mission2_day.py`'s in-process run — left here as historical context for
  the `--ignore`-treatment lesson, which still applies to any new rclpy-importing file.)
- **CI stage-0's traceability gate has `continue-on-error: true` — this is a live, ongoing gap,
  not stale.** Session 10 added `test_navigation.py`, but 2 of its 3 test function names never
  matched `requirements/traceability.yaml`'s placeholder names (fixed in Session 11/12: BR-01/
  BR-10 → `test_navigation_succeeds`, BR-02 → `test_no_collision`). BR-03 (recovery behavior)
  has no test at all — recovery is genuinely broken, so this isn't a naming fix, it's a
  real missing capability.
  Remove `continue-on-error` only once BR-03 has an actual test. Until then: this gate silently
  went from "intentionally red" to "actually blocking every downstream CI stage" once someone
  removed `continue-on-error` without the underlying gaps being fixed — check `gh run list`
  occasionally to make sure stage-3/stage-4 are still actually running, not skipped.
- **Under pytest in this repo, ANY new `logging.getLogger(...)` defaults to
  `propagate=False` — silently swallowing output.** Found 2026-07-20 building
  `tools/log_setup.py`: a test passed standalone (`python3 -c ...`) but failed under
  pytest with an empty log file, no errors, no exceptions. Root cause: the
  `launch-testing`/`launch-testing-ros` pytest plugins are *installed* (they show in
  `plugins:` even though `pytest.ini`'s `addopts` disables their hooks via
  `-p no:launch-testing -p no:launch-testing-ros`) — pytest still *imports* the plugin
  module during collection to know what to disable, and `launch.logging` runs
  `logging.setLoggerClass(LaunchLogger)` as an import side effect, which defaults
  `propagate=False`. This silently affects every NEW logger name created anywhere in
  a pytest run in this repo, not just `tools/log_setup.py`'s. Fix: any code creating
  its own logger must explicitly set `.propagate = True` rather than trust the
  default — see `tools/log_setup.get_logger()`.
- **Claude Code's own Bash tool runs with an isolated `/tmp`, separate from the real
  filesystem the user's browser/file manager sees.** Found 2026-07-21 (Session 17
  Piece 4): files written to `/tmp/...` via the Bash tool exist and are readable from
  *later* Bash calls in the same session, but Mike couldn't open them — they were
  never on his real filesystem. Files written inside the repo checkout (e.g.
  `reports/scratch-name.pdf`, cleaned up after) don't have this problem — that
  directory IS the real, shared filesystem (confirmed: it's what the IDE has open all
  session). Rule: when a file needs to be handed to the user directly (not served over
  a network port like Streamlit, which works fine from `/tmp` since a port isn't a
  filesystem path), write it inside the repo, not `/tmp`.
- **A "clean run" / "no drift" test that seeds a rolling baseline with IDENTICAL
  values gives a vacuous pass, not a real one.** Recurred at least 4 times across
  Session 17 (Foundation, Piece 4 ×2, Piece 5) — `baseline_monitor.check_run()`
  explicitly skips any metric whose baseline has zero variance
  (`if sd == 0.0: continue`), so a test seeding e.g. 11 identical
  `nav_success_rate=0.95` rows never actually compares anything — `flagged=False` is
  true only because nothing was checked, not because a real comparison found no
  drift. The fix pattern used throughout, matching `tests/test_baseline.py`'s
  original `_BASELINE_NAV_SUCCESS_RATES`: seed with real (small) variance
  (`0.94, 0.95, 0.96, 0.95, ...`) so `check_run()` performs a genuine comparison. The
  other legitimate way to dodge this trap (used once, in
  `test_build_trend_summary_reports_stable_metric`): bypass `check_run()` entirely by
  hand-constructing a `BaselineReport` and testing only the CONSUMING function's own
  formatting logic — sound as long as that consumer never reads `.sigma`/`.stddev`.
- **Making a path absolute breaks every OTHER place that assumed it was relative — a
  same-day regression, not a hypothetical.** The Piece 4 final-review fix above made
  `PHOTO_DIR` absolute; it fixed `stage-5-reports-*` but broke `tools/mission2_day.py`'s
  `_pull_photos()`, which still built the remote scp path as
  `f'...:autonomous-fleet-testbed/{rel}'` — correct when `rel` was checkout-relative,
  nonsense once `rel` became absolute. Silent failure: `mission_runner`'s own on-Jetson
  checklist still logged 100% PASS (the robot genuinely drove and photographed
  correctly, both variants), but every scp pull-back failed
  (`could not scp Jetson photo ...`, a WARNING not an error), so the workstation judge
  saw zero photos and FAILed all 3 mission2 variants in the very next CI run
  (29892759160, 2026-07-22) — a pure evidence-retrieval regression, not a
  navigation/perception bug. Compounding wrinkle found during the fix: the
  container-mode HIL path (`HIL_CONTAINER=1`) additionally lost the photos entirely —
  the image has no `USER` directive (`ros:jazzy-ros-base` default = root), so `PHOTO_DIR`
  resolves to `/root/fleet-ci-data` *inside the container*, which wasn't captured by the
  existing `-v $HOME/autonomous-fleet-testbed/reports:/ros2_ws/reports` bind mount at
  all — photos were written into the ephemeral container and vanished on `--rm`. Fixed
  (2026-07-22) with two changes in `tools/mission2_day.py`: (1) `_ssh_mission2` gained a
  second bind mount, `-v $HOME/fleet-ci-data:/root/fleet-ci-data`, so the container's
  root-HOME photos land in `JETSON_USER`'s real `fleet-ci-data` on the host; (2)
  `_pull_photos` gained `_remote_photo_path()`, which uses the logged absolute path
  verbatim for bare-metal (already the real host path) and substitutes the container's
  `/root` prefix for `~` in container mode (relying on the remote shell's own tilde
  expansion to land on `JETSON_USER`'s home) — covered by
  `test_pull_photos_bare_metal_uses_absolute_path_verbatim` and
  `test_pull_photos_container_mode_translates_root_prefix_to_tilde` in
  `tests/test_mission2_day.py`, the first tests either code path has ever had.
  `_pull_failure_bags` was NOT touched — `failure_bag.py`'s `BAG_DIR` is still
  checkout-relative, so its existing `autonomous-fleet-testbed/{rel}` scp path is still
  correct. **Lesson for next time: when a path constant changes from relative to
  absolute (or vice versa), grep every OTHER consumer of that same log line / directory
  convention, not just the one place the bug report points at** — Piece 4's own review
  found 3 duplicate relative-path bugs by doing exactly this for the *definition* side;
  this regression was the *consumption* side of the identical fix, missed because no
  task/review step in Piece 4 exercised a live HIL day's SSH pull-back, only photo
  existence-on-disk and dashboard rendering of already-local data.

- **The Jetson's `~/fleet-ci-data/` can be silently poisoned root-owned by a container-mode
  HIL run, breaking every later bare-metal run — found 2026-07-22 (Piece 7 timing exercise).**
  Root cause: the arm64 Docker image has no `USER` directive (default = root), and the
  2026-07-22 photo-pullback fix's bind mount (`-v $HOME/fleet-ci-data:/root/fleet-ci-data`)
  doesn't remap UIDs — every file a container-mode run (`HIL_CONTAINER=1`, which every
  CI `stage-4-hil` run uses) writes there lands root-owned on the Jetson's real disk. A
  later bare-metal run (`HIL_CONTAINER` unset — any manual local proof) runs
  `mission_runner.py` as `mike` over plain SSH, which then can't create files in a
  root-owned directory (mode 755 — group/other have no write bit): `PermissionError` on
  the first photo save, immediately followed by a cascading
  `sqlite3.OperationalError: attempt to write a readonly database` when it tries to log
  even the crash itself — looks exactly like the robot never started (it didn't: it died
  at mission step 1, before any navigation). Fix applied: `chown -R mike:mike
  ~/fleet-ci-data` + `chmod -R u+rwX,g+rwX` + setgid (`g+s`) on the directories so a
  FUTURE root-written file still lands in a group mike can traverse/create alongside.
  This can recur any time a container-mode run touches the directory again — if a bare-
  metal run gets a `PermissionError`/readonly-database crash with zero navigation
  logged, check `ls -la ~/fleet-ci-data` on the Jetson before assuming a code regression.
- **A real motion-start stall on HIL exists starting from the 2nd goal of a Mission 2 day
  onward and is NOT visible in any Nav2 log line — confirmed live 2026-07-22, root cause
  still unknown, NOT fixed (Piece 7 stays open until it is).** Live-narrated observation
  (Mike watching the Gazebo viewer while Claude tailed the Jetson's real Nav2 stdout log
  and correlated timestamps in real time, twice) confirmed: the FIRST goal of a HIL day
  (fresh Nav2 stack) starts the robot moving right when `controller_server` logs
  "Received a goal, begin computing control effort" — no stall. The 2nd and 3rd goals
  (no_ball→yellow, yellow→red transitions) do NOT: the robot visibly sits still for a
  real, observable stretch AFTER that same log line appears, then starts moving on its
  own with no further log activity in between — no abort, reject, or retry logged by
  bt_navigator/controller_server/planner_server.
  **Ruled out:** fresh-process cold start alone — bt_navigator/controller_server are the
  SAME persistent processes across all 3 runs (only `mission_runner` restarts per run
  over SSH), yet goal #1 on that persistent stack is clean and #2/#3 aren't.
  **Also ruled out (weaker, worth re-checking):** "goal right after a cancellation is
  slow to settle" — no_ball's own run ends via NORMAL SUCCESS (arrival home), not a
  cancelled goal, yet the FOLLOWING transition (into yellow's first goal) still stalled.
  So the trigger looks like "which goal number this is for the Nav2 stack's lifetime,"
  not specifically "did the prior goal get cancelled."
  **Diagnostic plan for next time (not yet done, in this order):**
  1. Add timestamped debug logging in `nav_runner.py` around goal dispatch — log the
     instant the goal is sent, the instant the "goal accepted" callback fires, and the
     instant odometry/feedback first shows non-negligible velocity. This turns the stall
     into something measurable from a log, not something that needs a human watching a
     screen every time.
  2. Live-watch `/robot_001/cmd_vel` publish activity (`ros2 topic echo`) during a
     transition: is the controller actually publishing near-zero velocity commands
     during the stall (a controller-side issue — e.g. RPP still converging/rotating),
     or is it publishing real commands that aren't reaching the simulated robot (a
     bridge/DDS issue)? This is the fastest way to split the hypothesis space in half.
  3. Check whether the same stall appears on a goal WITHIN a single run (e.g. no_ball's
     own return-home leg, its 2nd goal within the same mission_runner process) — this
     would tell us whether the trigger is "2nd+ goal of the whole Nav2 stack's uptime"
     (survives across mission_runner restarts) vs. something scoped to inter-run
     transitions specifically.
  4. If (1)-(3) point at costmap/localization settling rather than the controller
     itself, check AMCL/costmap timestamps around the stall — the log already shows a
     "Received request to clear entirely the global/local costmap" line right at goal
     start; worth checking whether that clear-and-rebuild has a real settle cost that
     grows after the first goal.
  This is tracked as confirmed-but-not-root-caused — do not mark it done until an
  actual fix (not just a diagnosis) lands.
  **UPDATE 2026-07-24: likely explained, under a different
  framing, not the one this entry originally used.** A much deeper live investigation
  (jetson_clocks, DEBUG-level Nav2 logging, live cmd_vel watching, x86-vs-Jetson A/B)
  found TWO separate real things, neither of which is "motion won't start": (1) an
  inter-scenario gap (~17.6s on Jetson, ~0.4s on x86) caused by `mission_runner`
  restarting as a fresh SSH-spawned process every scenario on Jetson vs. staying
  resident in-process on x86 — fix designed, not yet implemented (see the
  `mission2_day.py` entry above); (2) a ~18-29s intra-goal
  "pegged rotation" stall, reproducible identically on x86 AND Jetson, bare-metal AND
  container — platform-independent, likely a `yaw_goal_tolerance`/RPP tuning issue,
  still not root-caused. Neither is "no log activity, no abort/reject/retry" in the
  way originally described — DEBUG-level logging (not available at the time this entry
  was written) shows real, continuous, explainable activity in both cases. Leave this
  entry as historical context; treat Piece 9 as the current source of truth.
- **Docker/JetPack "docker exec is slow" write-ups are a plausible-sounding dead end for
  ANY delay that occurs mid-mission on the Jetson, not just this one — verify against
  bare-metal before spending time here.** Found 2026-07-24 (Piece 9): a detailed,
  specific-sounding explanation (PAM/`systemd-logind` D-Bus timeout, cgroups-v2 driver
  mismatch, NSS/mDNS hostname lookup, `nvidia-container-runtime` hook overhead — all
  real, documented JetPack 7.2 + Ubuntu 24.04 phenomena in general) was offered for the
  Piece 9 inter-scenario/intra-goal delays. All of it is about `docker exec -it ...
  bash` SESSION-STARTUP latency specifically. Two things rule it out for any delay that
  happens ONCE a mission is already running: (1) `controller_server`/`bt_navigator` are
  NEVER containerized in EITHER HIL mode — `scripts/hil_stage.sh run` always launches
  them as bare host processes via `nohup ros2 launch`, regardless of `HIL_CONTAINER`;
  (2) the fastest way to check is simply reproducing the SAME delay in bare-metal mode
  (`HIL_CONTAINER` unset) — if it's still there with zero Docker involved anywhere in
  the path, Docker was never the cause. Don't skip straight to Docker-daemon-config
  changes for an in-mission delay without this check first.
- **jetson_clocks is a legitimate, fast (~5s), reversible test for "is this CPU/GPU/
  memory clock throttling" — but confirm it actually changed something before trusting
  a null result.** `sudo jetson_clocks --show` before/after: if `CurrentFreq` already
  equals `MaxFreq` on all cores before running it (i.e. the CPU governor already has
  you at the current power mode's ceiling), running `jetson_clocks` again will lock
  GPU/EMC higher but can't push CPU past a ceiling it was already at — a "no change"
  result there rules out DVFS/idle-scaling specifically, not "not enough Jetson compute
  at this power mode" in general (a genuinely higher `nvpmodel` mode, e.g. MAXN_SUPER,
  is a separate, bigger test with real deployment-power tradeoffs — don't conflate the
  two).
- **A DEBUG-level dump of `ros2 launch`'s log is enormous (hundreds of thousands of
  lines for one ~18s goal, mostly `[rcl]`/`[rcl_action]` subscription-taking noise) —
  grep it, don't read it.** Found 2026-07-24 (Piece 9): useful signal (goal-received/
  reached lines, `bt_navigator`'s "unknown goal" feedback-tracking messages,
  `controller_server`'s "Control loop missed its desired rate" warnings) is present but
  buried; filter explicitly for `[rcl]:`/`[rcl_action]:`/`[rmw` exclusion plus the
  specific node-tagged messages you care about, and use Python (not shell `awk`, whose
  default `mawk` on this box lacks 3-arg `match()`) for timestamp-windowed extraction
  from a raw Jetson-side log file over SSH.
- **A 1-second-bucketed "max value per bucket" summary of a live topic can look
  identical to "continuously pegged at max" even when it isn't — always spot-check
  against raw, unbucketed samples before drawing a conclusion from a bucketed one.**
  Practice adopted 2026-07-24 (Piece 9) after this exact concern was raised mid-
  investigation: a cmd_vel bucketing script reporting `max|ang_z|=0.5000` for 7
  straight 1-second buckets was checked against the raw per-sample stream before being
  trusted — in that specific case the raw data DID confirm genuinely continuous
  pegged commands (smooth ramps, no gaps), but the check itself is now a standing
  practice for any bucketed live-topic analysis in this project, since the failure
  mode (a brief real blip inflating an otherwise-quiet bucket to look "pegged") is
  real and easy to miss.
- **When a live GUI-watched observation contradicts an already-computed timing number,
  re-derive the number from the SAME event the observer is describing before arguing
  with the observation.** The costliest mistake in this investigation
  (2026-07-24): an intra-goal delay (`goal accepted` → `goal result received`, ~18-29s,
  confirmed identical on x86 and Jetson) was conflated with the inter-scenario gap Mike
  was actually describing (`goal result received` → next scenario's dispatch) — which
  turned out to be ~40x different between platforms (~0.4s x86 vs. ~17.6s Jetson) and
  fully explained his repeated, correct, "watching the whole time" observation. Don't
  minimize a repeated, specific live observation as "which moment you happened to be
  watching" — re-measure the SPECIFIC boundary being described first.
- **GitHub Actions' own Summary tab has a confirmed platform-side bug — it mis-caches/
  mis-maps job-summary content client-side, unrelated to anything in `ci.yml`. Not
  fixable from this repo; stop re-investigating it as if it were our bug.** Confirmed
  twice, independently (2026-07-23 and again 2026-07-25, same signature both times):
  `stage-1-quality`'s own Summary panel displayed `stage-5`'s drift-report content
  (`hil_jetson: FAIL`, a large σ-drift banner) verbatim — even though `stage-1-quality`'s
  job spec (checkout → ROS2 apt install → ament lint install → flake8 → pytest) writes
  to `$GITHUB_STEP_SUMMARY` **zero times**, re-verified line-by-line against `ci.yml`
  both times. The 2026-07-25 recurrence went further: the displayed content didn't match
  that run's own console log OR its own downloadable PDF artifact either — genuinely
  stale/cached data from an unrelated run, not just a rendering-order mix-up. The Checks
  API confirms `output.summary` is `null` for every job; `$GITHUB_STEP_SUMMARY` has no
  public REST/GraphQL surface at all — the browser's Summary tab (a JS-rendered SPA) is
  the only place this data exists, which is exactly why no automated check can catch it.
  **Workaround in place, not a fix for the underlying bug:** `stage-5-reports-sim`/`-hw`
  moved their real "Fleet status" content off `$GITHUB_STEP_SUMMARY` into plain
  console-log output (`ci.yml`, the `Fleet status` steps) so the actually-meaningful
  content lives somewhere trustworthy even though the Summary tab can't be. This does
  NOT generalize to "never touch `$GITHUB_STEP_SUMMARY`" — every stage still writes a
  short one-line timing/link summary (`Stage N ... wall time`, `Download the PDF
  report`) with no reported problem; only large report-content blocks have been
  observed getting mis-cached. `stage-1-quality` still carries a diagnostic canary step
  (`"Canary summary line"`, `echo "### Message from Mike" >> $GITHUB_STEP_SUMMARY`,
  added 2026-07-25 specifically to probe this bug in its own panel) — its own comment
  says to remove it once confirmed live, which already happened; left in place
  deliberately (2026-08-01, Mike's call) rather than removed, so don't treat that
  comment as a live TODO.
- **`.github/workflows/ci.yml` uses CRLF line endings — a raw Python `open(path).read()`/
  `open(path, 'w').write()` round-trip silently strips them all to LF, producing a
  1000+-line noise diff that buries the real 2-line change.** Found 2026-07-26 (Piece 2
  second-round review fixes): patched two `pkill` lines via a small Python script for a
  `str.replace()` across 2 occurrences — worked, but `git diff --stat` showed 1102 lines
  changed for what was actually a 6-line diff, because text-mode Python I/O converts
  CRLF→LF on read and never restores it on write. No other file in this repo has this
  issue (checked: only `ci.yml` is CRLF). Fix used: `git checkout HEAD -- <file>` to
  restore the original CRLF, then reapply the SAME edit via the Edit tool instead (which
  does an exact string replacement without a full-file read/write round-trip and
  correctly preserves CRLF) — verified after with `file ci.yml` still reporting "with
  CRLF line terminators". Rule: never touch `ci.yml` with a raw Python/shell
  read-modify-write script; always use Edit (or `sed -i` with GNU sed, which also
  preserves line endings) for this specific file.
- **An XML `<!-- ... -->` comment body can never contain a literal double hyphen
  anywhere inside it — not even in prose — a real parse failure, not a style
  nitpick.** Found 2026-08-10 folding the CycloneDDS large-message fix into
  `scripts/regen_cyclonedds_config.sh`'s generated XML: a comment describing the
  fix used `--` as a prose separator (`"...above -- doesn't touch..."`), which
  broke the file's well-formedness (`xml.dom.minidom.parse` raised
  `ExpatError: not well-formed`, confirmed directly, not assumed). The `<!--`/`-->`
  delimiters themselves are fine — the restriction is on `--` appearing inside the
  body. Rule: any prose written into a shell-heredoc-generated XML comment in this
  project must use a colon, semicolon, or an em dash character (`—`), never `--`.
  Same session, separate gotcha worth remembering alongside this one: an
  UNQUOTED heredoc (`<<EOF`, not `<<'EOF'`) also runs full shell expansion on its
  body — a markdown-style `` `backtick code` `` inside the same comment text got
  executed as a real command (harmlessly failed here, but could easily not).
  Quote the delimiter or scrub backticks/`$()`/`$VAR` from any prose destined for
  an unquoted heredoc body.
- **A Claude Code `SessionStart` hook's plain stdout reaches ONLY Claude's own context,
  never the human user's terminal — confirmed against the official docs 2026-07-29,
  after Mike reported the dashboard-reminder hook (added 2026-07-28, `.claude/
  settings.json`) "isn't working."** It wasn't a flake: Claude Code's docs state
  plainly that for `SessionStart` (and `UserPromptSubmit`/`UserPromptExpansion`),
  stdout is "added as context that Claude can see and act on" — nothing about the
  user seeing it. The hook was genuinely running (Claude's own system-reminder showed
  `SessionStart:startup hook success: ...` every session), which is exactly why this
  was easy to wrongly call "already working" from inside a session — the assistant
  DOES see it fire, the human never does. To make a `SessionStart` hook's output
  user-visible, its stdout must be JSON with a `systemMessage` field (shown to the
  user) — `hookSpecificOutput.additionalContext` is the separate field for Claude-only
  context; plain unstructured stdout is Claude-only for this event, full stop. Fixed
  by moving the hook's logic into `.claude/hooks/session_start_status.sh`, which emits
  `{"systemMessage": ..., "hookSpecificOutput": {"additionalContext": ...}}` via `jq`
  instead of plain `echo`; `.claude/settings.json` now invokes that script via
  `${CLAUDE_PROJECT_DIR}` (the documented placeholder for referencing hook scripts
  regardless of working directory) rather than inlining two bare `echo`/`python -m`
  commands. **Lesson for any future hook meant to inform the human specifically:**
  "the assistant received it in a system-reminder" is NOT evidence the user saw
  anything — verify hook user-visibility by checking for `systemMessage` in its JSON
  output, not by trusting that a hook "fired successfully."
- **CUDA/Ollama installed on the Jetson, 2026-07-30 (VLM red-ball canary).** Installed
  manually by Mike, per plan: `nvidia-jetpack 7.2-b187` (`sudo apt install
  nvidia-jetpack` — no reflash, L4T apt sources already present from the original
  OS-only flash), CUDA Toolkit `13.2.1-1` (`nvcc` — real version confirmed:
  `Cuda compilation tools, release 13.2, V13.2.78`), Ollama `0.32.5` on the Jetson
  (workstation is `0.32.0` — versions don't need to match). Model pinned:
  `moondream:1.8b`.
  **Gotcha 1 — `nvcc` isn't on `PATH` after `nvidia-jetpack` installs**, even though
  the toolkit itself installed correctly (`dpkg -l | grep cuda-toolkit` shows it real).
  Fix: `echo 'export PATH=/usr/local/cuda/bin:$PATH' >> ~/.bashrc`.
  **Gotcha 2 — Ollama's install script warns `"Unsupported JetPack version detected.
  GPU may not be supported"` on JetPack 7.2 — this is a false alarm, not a real
  problem.** JetPack 7.2 is NEWER than what `install.sh`'s version-detection list
  currently recognizes (native support tops out at JetPack 6.2), so the script's
  warning is a version-list gap, not evidence of a broken GPU path. Confirmed via
  `journalctl -u ollama`: Ollama's runner correctly skips one bundled CUDA library
  variant (`cuda_v12`, which lacks compiled support for Orin's compute capability
  8.7) and falls back to a working one (`cuda_v13`) — the real proof is
  `load_tensors: offloaded 25/25 layers to GPU` and `clip_ctx: CLIP using CUDA0
  backend` in the log, both present and correct. Don't trust the install-time warning
  text either way — check `journalctl -u ollama | grep -iE "cuda|gpu|offload"` for
  the real answer.
  **Gotcha 3 — the FIRST inference call after a fresh Ollama server start is
  dramatically slower than every call after it** (~45s vs ~4s, measured live,
  `moondream:1.8b` on this exact board) — one-time CUDA kernel JIT compilation for
  Orin's specific compute capability (not precompiled in the bundled library) plus
  cold model load, not a sustained performance problem. This is why the design spec
  calls for pre-warming (one throwaway inference call) before any timing-sensitive
  use — see that spec's "Model choice + pre-warming" section.
  **Gotcha 4 — the Ollama *server* install (`curl -fsSL https://ollama.com/install.sh
  | sh`) does NOT install the `ollama` Python client package** — that's a separate,
  additional `pip3 install ollama` (or `pip3 install --break-system-packages ollama`
  on this Ubuntu/JetPack userland, which enforces PEP 668's
  externally-managed-environment restriction) needed on the Jetson's bare-metal
  system Python for any bare-metal script/tool that does `import ollama` directly
  (confirmed live: `ModuleNotFoundError: No module named 'ollama'` until this was
  done). **Container-mode HIL does NOT need this extra step** — `requirements-ci.txt`
  already pins `ollama>=0.4` (added earlier for `tools/agentic_loop.py`'s Ollama
  backend), so the arm64 Docker image already has it baked in.
- **Connecting a second network interface (WiFi) on the Jetson broke HIL's cross-machine
  ROS2 discovery entirely — root-caused 2026-07-30, same session as the CUDA/Ollama install
  above, but a separate, unrelated bug.** After enabling the Jetson's WiFi (`wlP1p1s0`,
  connected to a real home network for testing before the robot's arrival), `scripts/
  hil_stage.sh run` started reliably failing: Nav2 came up fine locally on the Jetson
  (`map_server`/`amcl` activated, bonded, "Managed nodes are active" all logged normally),
  but was **completely invisible from the workstation** (`ros2 node list` showed zero
  Jetson-side nodes) and vice versa (the Jetson received zero data on topics the workstation
  publishes — confirmed with `ros2 topic hz /robot_001/scan` timing out with no output at
  all). `local_costmap` looped forever on "Timed out waiting for transform from
  base_footprint to map". Survived a full soft reboot AND a hard power cycle identically —
  ruled out as a transient/stale-process issue. Root cause, found via `ip maddr show` (no
  `tcpdump` needed): CycloneDDS's default interface auto-selection picks the first viable
  multicast-capable interface by **ifindex**, not necessarily the one that actually reaches
  the other machine. On the Jetson, WiFi's ifindex (2) is lower than Ethernet's (5) — likely
  because the WiFi driver probes before the Ethernet controller at boot — so CycloneDDS
  joined its discovery multicast group (`239.255.0.1`) on `wlP1p1s0` instead of `enP8p1s0`,
  the only interface that actually reaches the workstation. (The workstation's own Ethernet
  happens to have the lower ifindex there, so it was never affected — pure luck, not a
  difference in configuration.) This is exactly why WiFi hadn't broken anything before this
  session: it was never up long enough to matter until today. **Fix:** `~/cyclonedds-hil.xml`
  on the Jetson lists BOTH interfaces explicitly with an assigned `priority` (higher wins,
  per CycloneDDS's own docs — default is 0 for a regular interface, 2 for loopback):
  `enP8p1s0` at `priority="10"`, `wlP1p1s0` at `priority="1"`. Ethernet stays preferred
  whenever it's up; WiFi remains genuinely available as a fallback if Ethernet is ever
  disconnected (the untethered-robot scenario this WiFi bring-up exists for in the first
  place) — a narrower first version of this fix pinned Ethernet ONLY, which would have
  silently broken untethered operation the same way the original bug broke tethered
  operation; corrected same day after Mike caught it. `scripts/hil_stage.sh`'s `JENV` now
  exports `CYCLONEDDS_URI=file://$HOME/cyclonedds-hil.xml` for every Jetson-side launch, so
  this is immune to future interface/ifindex changes (a new USB-Ethernet dongle, a different
  WiFi card, etc.) regardless of enumeration order. **Diagnostic lesson:** `ros2 topic hz` on a
  topic the SAME machine also locally publishes (e.g. via its own Gazebo bridge) proves
  nothing about cross-machine delivery — check the topic from the OTHER machine's side, or
  check a topic/node that can only exist on the remote side, to actually test the link.
- **`ssh mike@jetson.local` stopped resolving the same day as the WiFi bring-up above — a
  separate bug from the CycloneDDS one, root-caused 2026-07-30.** `avahi-daemon` on the
  Jetson logged `Host name conflict, retrying with jetson-3` at boot and started
  advertising as `jetson-3.local` instead of `jetson.local` — confirmed via `journalctl -u
  avahi-daemon`, not a workstation-side or firewall issue (ruled out: workstation's own
  `avahi-browse -a -t` showed real mDNS traffic from other devices on WiFi, `ip maddr show`
  confirmed `224.0.0.251` correctly joined on the Ethernet interface both sides, and
  `239.255.0.1` — a DIFFERENT multicast group, CycloneDDS's own — was independently proven
  working on that exact same Ethernet link at that exact same time, ruling out "multicast is
  blocked on this interface" as a category). **Root cause: a boot-time race, specific to
  having Ethernet AND WiFi both come up together at avahi's own startup** — the log showed
  IPv6 privacy/temporary addresses on `wlP1p1s0` churning (registering, withdrawing,
  re-registering within the same second) exactly while avahi was probing for name
  uniqueness, triggering a spurious self-conflict. Confirmed by elimination: restarting
  avahi-daemon *after* boot (interfaces already settled) always claimed `jetson.local`
  cleanly with zero conflict, every time. **Fix:** `use-ipv6=no` in
  `/etc/avahi/avahi-daemon.conf`'s `[server]` section on the Jetson — this project doesn't
  use IPv6 anywhere (SSH, ROS2/DDS are all IPv4), so removing it removes the churn that
  triggered the boot race. Verified with a full reboot (not just a service restart): clean
  `jetson.local` claim with zero conflict, both interfaces up together at boot, confirmed
  both by the journal log (no `Joining mDNS multicast group on interface *.IPv6` lines at
  all this time, vs. explicit IPv6 joins before the fix) and by a live `ping`/`ssh
  mike@jetson.local` against the fresh boot. Not committed to git — this is a Jetson
  OS-level config file, outside the repo; re-provisioning this exact board (or a
  replacement) needs this step redone manually.
  **UPDATE 2026-07-30 (same day, next power cycle): recurred with a THIRD, different
  trigger — the `use-ipv6=no` fix above is confirmed still holding (zero IPv6 multicast
  joins), so this is additive, not a regression of that fix.** After a full workstation +
  Jetson power-down/power-up, `ssh mike@jetson.local` failed again
  (`jetson-2.local` this time). `journalctl -b` (whole system, not just the avahi unit)
  pinpointed the trigger to the exact millisecond: `systemd-timesyncd[465]: Initial clock
  synchronization to Thu 2026-07-30 15:33:14...` fires in the SAME event-loop tick as
  avahi's withdraw-everything/re-register-everything burst that produces `Host name
  conflict, retrying with jetson-2` — this Jetson has no trustworthy RTC, boots showing a
  bogus date (`Dec 31`), and only gets its first real NTP fix once WiFi associates
  (Ethernet's DHCP hadn't even completed yet at the moment of conflict, ruling out
  "Ethernet coming up" as this trigger, unlike what the previous entry's framing might
  suggest for a similar-looking symptom). The abrupt `CLOCK_REALTIME` step while avahi is
  mid-probe corrupts its own timing/scheduling and it loses a race against its own
  in-flight re-announcement. **Fix: stop avahi from starting until the clock is already
  synced, rather than reacting after the fact** — `sudo systemctl enable
  systemd-time-wait-sync.service` (ships with systemd, disabled by default) plus a
  drop-in override at `/etc/systemd/system/avahi-daemon.service.d/override.conf`
  (`[Unit]` / `After=systemd-time-wait-sync.service` / `Wants=systemd-time-wait-sync.service`)
  so `avahi-daemon.service` waits on it. Verified with **three consecutive full reboots**
  (this project's bar for an intermittent-fix, `feedback_proof_bar_sizing`): zero
  `Host name conflict` lines in any of the three, `ssh mike@jetson.local` resolved
  immediately every time with no manual restart, CycloneDDS's `~/cyclonedds-hil.xml`
  confirmed byte-identical throughout (this fix touches only avahi/systemd, not DDS
  interface selection). Also not committed to git, same reason as above — two systemd
  changes to redo on any re-provision: `systemctl enable systemd-time-wait-sync.service`
  and the avahi-daemon.service.d override file. **Lesson: when the same user-visible
  symptom recurs after a fix already verified by a full reboot, don't assume the old fix
  regressed — pull the FULL system journal (not just the one unit) around the exact
  failure timestamp first. Two unrelated root causes can produce byte-identical log
  output (`Host name conflict, retrying with jetson-N`).**
- **`nvpmodel -m <id>` started demanding an interactive reboot confirmation on
  2026-07-30, breaking `scripts/hil_stage.sh power-mode` (and therefore every
  stage-4-hil CI run) even when setting the Jetson to the mode it was ALREADY in** —
  `NVPM WARN: Golden image context is already created` / `Reboot required for
  changing to this power mode: 1` / `DO YOU WANT TO REBOOT NOW?`, which a
  non-interactive SSH/CI invocation answers with EOF, producing `NVPM ERROR: bad
  input!` and a nonzero exit — `hil_stage.sh`'s `set -euo pipefail` (and CI's lack of
  `|| true` on this specific step) then aborts the whole job before sync/build/mission
  ever run, which is why a "failed HIL run" can show almost NO mission logs at all —
  check `gh api .../jobs/<id> -q '.steps[]'` for per-step conclusions before assuming
  the mission itself ran. **Two things ruled out before finding the real fix:** (1) a
  leftover `jetson_clocks` diagnostic (forced CPU clocks to hardware max, MinFreq=
  MaxFreq=1728000, never restored) was a real, separate, self-inflicted issue — found
  via `jetson_clocks --show` still showing the stuck state — but a clean `sudo
  reboot` fixed THAT specific problem while the nvpmodel prompt persisted unchanged,
  proving it wasn't the (sole) cause; (2) `ollama.service` actively holding a live
  GPU/CUDA context was a plausible read of "Golden image context" — ruled out by
  `sudo systemctl stop ollama` then retrying `nvpmodel -m 1`, which showed the
  identical prompt with Ollama fully stopped. **Real fix: nvpmodel tracks its own
  internal "confirmed reboot pending" state, separate from live hardware clocks —
  a GENERIC `sudo reboot` does NOT clear it; only letting nvpmodel drive its OWN
  confirm-and-reboot cycle does.** Fixed by piping the confirmation directly: `echo
  yes | ssh ... "sudo -n nvpmodel -m 1"` — nvpmodel printed `NVPM WARN: rebooting..`
  and rebooted itself; after that reboot, `nvpmodel -m 1` returned cleanly (`rc=0`,
  no output) twice in a row, non-interactively, matching the behavior every prior
  session had relied on. Exact trigger not fully certain — most likely the JetPack/
  CUDA install earlier the same day (`nvidia-jetpack 7.2-b187`) initialized the GPU
  driver on this board for the first time ever and set this pending-reboot flag as a
  one-time side effect, needing exactly one nvpmodel-confirmed reboot to clear (apt
  history shows the install itself never touched `nvidia-l4t-nvpmodel`, the package
  that actually owns `/usr/sbin/nvpmodel`, ruling out a package-version change as the
  direct cause). **If this recurs, the fix is the same one-line `echo yes | ssh ...
  nvpmodel -m <id>` — don't reach for a plain reboot or restart-a-service guess
  first**, both were tried and ruled out this time.
- **This repo went public 2026-07-31 — it uses two SELF-HOSTED runners (the workstation
  + the Jetson), which is a real, well-known GitHub Actions risk category for a public
  repo: a fork PR can trigger a workflow run that executes on physical hardware.**
  Confirmed and hardened the same day. Facts, not guesses: `ci.yml` has no
  `workflow_dispatch` trigger (no one, including the owner, can manually trigger a run
  from the web UI); `sdfinn` is the sole collaborator (confirmed via API — direct push
  to `main` is impossible for anyone else); `ci.yml` uses `pull_request`, not the
  riskier `pull_request_target`, so GitHub automatically withholds repository secrets
  from any fork-PR-triggered run regardless of settings; `default_workflow_permissions`
  is `read` (confirmed via `gh api repos/.../actions/permissions/workflow`), so even the
  automatic `GITHUB_TOKEN` can't push/write. The one real, findable, worth-doing setting
  is Settings → Actions → General → "Fork pull request workflows from outside
  collaborators" → **set to "require approval for all outside collaborators"** (done
  2026-07-31) — every fork PR now needs an explicit manual click before anything runs,
  no exception for repeat contributors. Self-hosted runner network exposure itself was
  never a real concern regardless of ISP/CGNAT — these runners are outbound-only by
  design (they long-poll GitHub for work; GitHub never connects inbound), so the actual
  risk category is "approved code executes on my hardware," not "my machine is
  reachable from the internet." **A specific pair of checkboxes was initially described
  as also worth checking ("Send write tokens"/"Send secrets to workflows from fork pull
  requests") — Mike couldn't find them on this personal-account repo, most likely an
  org-only setting or a misremembered UI detail from a general-knowledge recall, not
  verified against the live page before being stated.** Don't re-describe specific UI
  element names/locations as fact without a way to verify them live (API check, or the
  user's own screen) — the two structural facts above (secrets withheld from
  `pull_request` fork runs; read-only `GITHUB_TOKEN`) already cover what those
  checkboxes would have, so there's nothing to keep hunting for.
- **HIL hardening session, 2026-07-31 — full arc, ending in the first fully-green
  end-to-end CI run of the project (run 30657248798).** Six real, distinct problems
  found and fixed in sequence; each looked plausible as "the" fix at the time and each
  turned out to be real but incomplete on its own:
  1. **25W always, no more `nvpmodel -m` calls in CI at all (Mike's decision).** HIL is
     wall-powered and the real robot's own short (<30min) field experiments also stay
     at 25W, so the old 15W-during-mission/25W-during-build switch bought nothing real
     — and that exact switch is what was tripping nvpmodel's stuck reboot-confirmation
     bug (see the 2026-07-30 entry above) on *every* HIL run, not a rare one-off as
     first assumed. Fix wasn't "pick a different number" — an initial pass still kept
     an explicit `nvpmodel -m 1` "safety net" step and it STILL tripped the bug (the
     mode requested doesn't have to differ from the current one for the bug to fire).
     Real fix: stop calling `nvpmodel -m` anywhere in the automated CI path at all.
     `nvpmodel -q` (read-only, no reboot risk) stays for telemetry's power-mode label.
  2. **CycloneDDS interface list hard-fails on ANY down interface, doesn't skip to the
     next-priority one.** The 2026-07-30 fix below (list both interfaces, Ethernet
     priority 10, WiFi priority 1) assumed CycloneDDS would silently prefer whichever
     listed interface was actually up. Confirmed false, live: with Ethernet physically
     unplugged, Nav2 hard-failed on the Jetson with `enP8p1s0: does not match an
     available interface` / `rmw_create_node: failed to create domain` — every ROS2
     node on the Jetson died at startup, never got to try wlP1p1s0 at all. This exact
     "Ethernet unplugged, real CycloneDDS traffic" scenario had never actually been
     exercised before — the 2026-07-30 WiFi work only verified SSH/mDNS, a different
     subsystem entirely, unrelated to CycloneDDS's own interface binding.
  3. **`scripts/regen_cyclonedds_config.sh` (new)** — regenerates the interface config
     from REAL current link state (`/sys/class/net/<iface>/operstate` — NOT `ip
     link`'s administrative UP flag, which stays "UP" with no cable plugged in, the
     root cause of #2) immediately before every launch, on the Jetson
     (`hil_stage.sh`'s `nav2_up()`, over SSH) — never lists a down interface, so it's
     correct however the Jetson happens to be connected at boot, no manual step ever
     needed. Verified live via a direct manual test (bare `ros2 launch
     nav2_only_launch.py` with the interface removed from the file by hand): fixed
     immediately, all nodes came up clean.
  4. **Same failure CLASS, different machine: the workstation's `sim_up()` had NO
     CycloneDDS config at all**, relying on CycloneDDS's own default auto-selection —
     which picked `docker0` (a virtual Docker bridge on an unrelated 172.17.0.0/16
     subnet) over the real WiFi interface. Confirmed via `/sys/class/net/<iface>/
     device` — the standard way to tell a real NIC from a virtual bridge/veth/loopback
     apart on Linux (docker0/veth* have no `device` symlink; enp6s0/wlp5s0 do). Result:
     the workstation's own Gazebo/bridge topics never reached the Jetson at all, even
     though both machines could ping each other fine (SSH/ping are unicast; CycloneDDS
     discovery is multicast — a fully separate question). `regen_cyclonedds_config.sh`
     was generalized (not duplicated per-machine) to auto-detect physical-vs-virtual
     interfaces via the `/device` check and prioritize by the standard `en*`/`eth*`
     (Ethernet) vs `wl*` (WiFi) naming convention, so ONE script runs unmodified on
     both machines despite their real interface names differing
     (enP8p1s0/wlP1p1s0 vs enp6s0/wlp5s0). Wired into `sim_up()` the same way.
     Verified live on the workstation itself (real `hil_stage.sh run` invocation,
     `JETSON_IP` deliberately unset so `nav2_up()` cleanly stopped at its own
     `require_ip` check before ever touching the Jetson) — regenerated correctly,
     `docker0` excluded, Gazebo + bridge came up clean.
  5. **Even with #3 and #4 both fixed, cross-machine DDS discovery over WiFi ALONE
     still didn't work** — `local_costmap` kept timing out waiting for the `map`
     transform, live, in CI, with both machines confirmed correctly bound to their
     real WiFi interfaces (no wrong-interface, no docker0). Leading theory, NOT
     confirmed further: the WiFi router (AT&T-provided) has AP/client isolation
     enabled, or filters multicast between wireless clients (common consumer/ISP-
     router behavior) — would exactly explain why unicast (SSH, ping) worked fine all
     session but CycloneDDS's multicast-based discovery never crossed the AP.
     **Deliberately not investigated further** — see the insight below for why, and
     `scripts/hil_stage.sh`'s own top-of-file comment for the pointer.
  6. **`scripts/**` was missing from `ci.yml`'s `dorny/paths-filter`** — a
     `hil_stage.sh`-only push silently skipped the ENTIRE arm64+HIL chain (a run came
     back green only because everything that ran passed, not because stage-4-hil did
     — it never ran at all). `hil_stage.sh` drives HIL's entire SSH orchestration, so
     a change to it should never be able to skip validation this way. Fixed by adding
     `scripts/**` to the filter's watched paths.
  **Key insight (Mike): the real, deployed robot does not need WiFi/Ethernet for its
  core operation at all.** HIL is a two-machine system *by design* — Gazebo (the
  simulated world) runs on the workstation while Nav2/mission_runner run on the real
  Jetson, specifically so real onboard software can be tested against a simulated
  world it can't tell apart from reality. That split is the ENTIRE reason any of #2-#5
  above exist. The deployed robot has none of it: Nav2, mission_runner, ball_detector,
  ekf_node, and the VLM canary's Ollama call all run on the same Jetson; even the
  Docker container path (`HIL_CONTAINER=1`) uses `--network host`, so container-to-
  host traffic (e.g. reaching Ollama) goes over `localhost` regardless of whether
  WiFi/Ethernet exists at all. Given that, there's no R1 payoff to chasing #5 further
  — Ethernet was reconnected for HIL instead (2026-07-31), which is what actually
  produced the first fully-green run. A dedicated WiFi router/AP Mike controls (not
  the AT&T gateway) is the right fix if/when it's actually needed — deferred until
  either a second/slave robot arrives (R2/R3 multi-robot coordination will need real
  wireless) or R1 debugging over Ethernet-tethered HIL gets cumbersome enough to
  justify it sooner. Bluetooth was considered and ruled out for this purpose — wrong
  transport for ROS2/DDS (no standard transport, assumes IP networking + bandwidth for
  topics like `/scan`/camera streams).
- **On-device VLM canary, 2026-07-31 — the canary was silently classifying
  workstation-side even for stage-4-hil, missing the entire point of "on-device."**
  `_maybe_spawn_vlm_canary()` (`tools/mission2_day.py`) is called from the shared,
  workstation-side `run_day()` function regardless of executor — so even in HIL mode,
  classification happened on the WORKSTATION's own Ollama/GPU, using the ALREADY-
  pulled-back local photo copy, never touching the Jetson's own CUDA/Ollama install
  (the one specifically installed for this purpose, 2026-07-30). Found when Mike
  pointed out HIL is "primarily where we want it, the main reason for implementing
  now." Fixed: `JetsonExecutor` now spawns BOTH the warm-up and the real
  classification directly on the Jetson over SSH (fire-and-forget, detached,
  `_spawn_vlm_canary_on_jetson`/`spawn_vlm_warmup`), using `_remote_photo_path`'s
  existing bare-metal/container path translation, BEFORE `_pull_photos_from_paths`
  overwrites the leg's photo list with workstation-local copies. A new
  `MissionExecutor.spawns_own_vlm_canary` flag stops the workstation-side spawn from
  ALSO firing for a Jetson-executed leg (the same red photo would otherwise get
  classified twice, by two different machines). Stage-2 (sim, no real Jetson) is
  unaffected — workstation-side classification is the only sensible option there.
  **The result has to get back to the WORKSTATION's real `fleet_runs.db`** (the
  Jetson's own local sqlite write is invisible to every report/dashboard tool, which
  all read the workstation's copy) — `tools/vlm_canary.py`'s `main()` now also writes
  a small `vlm_canary_last_result.json` snapshot (overwritten each call — at most one
  red reaction per day, so "last" is unambiguous) alongside the sqlite DB; a new
  `python -m tools.mission2_day --ingest-vlm-canary` CI step (placed as LATE as
  possible in `stage-4-hil`, after the Nav2-log fetch, to give the fire-and-forget
  background call maximum wall-clock time) pulls that file back and logs it into the
  workstation's real DB — deliberately re-resolving `photo_path` to the ALREADY-
  pulled-back workstation-local equivalent rather than trusting the Jetson's own
  (meaningless-on-the-workstation) path, so it joins correctly against
  `generate_test_report.py`'s `photos` column (next entry). **Verified end-to-end,
  live, in the first fully-green run**: `vlm_canary_log` row created at the same
  wall-clock second as the HIL mission's own `PASS` telemetry row, `photo_path`
  pointing at the real pulled-HIL-photo (distinct timestamp from the sim run's own
  canary photo), ingest step logging the real filename rather than "no result file to
  ingest yet" (which is what every earlier, blocked attempt logged).
- **Photo/VLM-canary cross-contamination in PDF reports, found + fixed 2026-07-31 —
  likely present in every HIL report since Piece 9 (2026-07-24), not just today's sim
  addition.** `generate_test_report.py`'s `find_run_photos()` matches by a ±180s time
  window around a row's own timestamp — but mission2's 3 legs get telemetry-logged
  within the same wall-clock second (one tight judging loop, no meaningful delay), so
  EVERY leg's PDF section showed every OTHER leg's photos and VLM canary text too.
  Confirmed directly: the exact same canary answer (belonging only to the red leg)
  appeared duplicated under `no_ball` and `yellow`'s sections in a real generated PDF.
  Fixed with a new `photos` telemetry column (JSON-encoded, this row's own exact
  list, populated by `_judge_and_log_leg`/`log_variant_row`) that
  `generate_test_report.py`'s new `_row_photos()` helper prefers over the time-window
  guess, falling back to it only for scenarios that don't populate it yet
  (bedroom_nav/mission1 — unaffected, no reported bug there). Regression-tested
  directly: two rows sharing an identical timestamp but distinct `photos` columns now
  correctly produce distinct PDF sections.
- **`ingest_vlm_canary_from_jetson()` was joining the wrong photo directory — every HIL
  PDF report has shown zero VLM canary text since the feature shipped 2026-07-31, found
  + fixed 2026-08-01.** `_pull_photos_from_paths()` writes each leg's `photos`
  telemetry column using `PHOTO_DIR`-based paths (`~/fleet-ci-data/photos/...`), but
  `ingest_vlm_canary_from_jetson()` globbed `state_dir` (e.g. `/tmp/hil_stage/...`)
  for the local reaction-red photo instead — a real copy of the same file exists in
  BOTH directories (state_dir gets a `cp -f`'d duplicate), same basename, different
  absolute path, so `find_vlm_canary_results()`'s exact-string `WHERE photo_path IN
  (...)` join silently matched nothing. Confirmed directly against the real
  `fleet_runs.db` (run 690): `photos` column pointed at PHOTO_DIR, `vlm_canary_log.
  photo_path` pointed at state_dir. The sim report never had this bug (sim never goes
  through this Jetson-specific ingest path), which is exactly why only the HIL PDF was
  affected. Fixed: glob `PHOTO_DIR` instead — TDD, `tests/test_mission2_day.py`'s
  `test_ingest_vlm_canary_from_jetson_logs_result_with_photo_dir_path` (replaces the
  old test, which had enshrined the WRONG assumption) confirmed RED against the old
  code, GREEN after.
- **`test_nav_runner.py`'s rclpy teardown will silently break `test_navigation.py`/
  `test_mission_run.py` if pytest's file collection order ever changes — found
  2026-08-01 running a naive `pytest tests/` for a coverage check.** `conftest.py`'s
  `ros_context` fixture (session-scoped) is deliberately shared ONLY between
  `test_navigation.py` and `test_mission_run.py` — its own docstring says so. But
  `test_nav_runner.py` has a SEPARATE, independent module-scoped `_ros` fixture that
  calls `rclpy.try_shutdown()` unconditionally on teardown — if `test_nav_runner.py`
  happens to run BEFORE the other two finish (which is exactly what plain alphabetical
  pytest discovery does: `test_nav_runner.py` < `test_navigation.py`), its teardown
  kills the shared rclpy context out from under them, and every subsequent
  `test_navigation.py`/`test_mission_run.py` test ERRORs with
  `rclpy.exceptions.NotInitializedException`. **CI never hits this** — `ci.yml`'s
  `Run navigation + mission integration tests` step explicitly orders the 3 files
  (`test_navigation.py test_mission_run.py test_nav_runner.py`, nav_runner LAST) —
  but ANY local ad-hoc `pytest tests/ ...` invocation that lets pytest auto-discover
  will silently hit this. **Not fixed** (a real fix would make `test_nav_runner.py`'s
  `_ros` fixture check whether it OWNS the context before shutting it down, mirroring
  `ros_context`'s own care) — flagged, not yet a priority; the safe workaround for now
  is to always pass the 3 live-ROS files explicitly in CI's order:
  `pytest tests/test_navigation.py tests/test_mission_run.py tests/test_nav_runner.py
  tests/ --ignore=tests/test_ros2_contracts.py --ignore=tests/test_navigation.py
  --ignore=tests/test_mission_run.py --ignore=tests/test_nav_runner.py ...`. **Caution
  found the same session, still being separated out:** a second, independent full-suite
  attempt using exactly that safe-order command still came back with wildly wrong
  numbers (~15% total, only 29 tests collected) — root cause NOT this ordering bug (a
  different symptom entirely) — see the next entry; don't assume this ordering fix
  alone is sufficient before re-verifying against a genuinely idle machine.
- **This workstation is BOTH `autonomous-fleet-testbed`'s self-hosted CI runner AND a
  general dev machine that can have OTHER projects' full Gazebo/Nav2 stacks running at
  the same time — found 2026-08-01, mid-coverage-investigation, twice in one session.**
  Two distinct instances of the same hazard class:
  1. **A `git push` to `main` auto-triggers a real CI run on THIS machine.** Pushed two
     commits, then immediately launched a local Gazebo session for a coverage check —
     CI's own `stage-2-gazebo` job started concurrently, and its "Sweep stale sim
     processes" step (`pkill -9 -f "parameter_bridge|component_container_isolated|
     ekf_node|ball_detector"`, etc.) killed the local session out from under it
     mid-run. The collision also caused two REAL test failures in CI itself
     (`test_navigation_succeeds`, `test_mission1_completes` — genuine `Goal rejected
     after all retries` errors from two Nav2 stacks fighting over the same DDS
     topics/action servers), which needed a re-run to clear (confirmed: same commit,
     zero code change, passed clean the second time — pure resource contention, not a
     regression). **Practice adopted:** check `gh run list` for an in-flight run before
     launching anything Gazebo-related locally, especially right after a push.
  2. **A SEPARATE, unrelated local Gazebo/Nav2 stack from the `synthetic-fleet` project
     (a different git working directory on this same machine, open in another VS Code
     window) was found ALREADY RUNNING**, bound to the identical `/robot_001/...` DDS
     topic namespace as this repo's own launch — `pgrep -fa` showed two full sets of
     `robot_state_publisher`/`ball_detector`/`ekf_node`/Nav2-container processes
     side by side, one launched from `/home/mike/synthetic-fleet/install/...`, one from
     `/home/mike/autonomous-fleet-testbed/install/...`. This most likely explains the
     wildly-wrong ~15%/29-tests coverage run in the previous entry (two stacks
     cross-talking on the same topics looks exactly like flaky/failing navigation, not
     an obviously "two robots" symptom) and possibly some of the earlier collision's
     confusion too. **Deliberately NOT killed by Claude** — another project's live
     session in a window Mike may be actively using is not something to touch without
     being asked. Session paused here rather than work around it. **Before resuming
     Item 3 (or any local Gazebo-dependent test run on this machine going forward):**
     `pgrep -fa "gz sim|robot_state_publisher"` and check the launching PROJECT PATH in
     the command line specifically — process names alone look identical across
     projects that share the same `nav_fleet` package name.
- **`hil_stage.sh sync`'s Jetson git-tree-conflict failure (first documented
  2026-07-31, HIL hardening session) RECURRED 2026-08-11 — same signature, and this
  time it was self-inflicted by Claude's own live-hardware-verification workflow,
  not an incidental leftover.** During this session's driver-boot-fix implementation
  (Tasks 1/3/5), subagents `rsync`'d individual changed/new files directly onto the
  Jetson's NATIVE checkout (`~/autonomous-fleet-testbed` — the SAME directory
  `hil_stage.sh sync` operates on) to live-verify against real hardware, then never
  cleaned up afterward — each task's own verification was independently correct, but
  nothing in the workflow ever restored that checkout to a git-clean state before the
  eventual push. First post-push CI run (`31513008012`) failed immediately at
  `stage-4-hil`'s `Sync the commit under test on the Jetson` step: `git checkout
  --detach FETCH_HEAD` correctly refused to overwrite 2 modified tracked files
  (`scripts/robot_boot.sh`, `src/nav_fleet/launch/sensors_only_launch.py`) and 1
  untracked one (`src/nav_fleet/launch/drivers_only_launch.py`) — everything after
  that step skipped. Confirmed via direct `diff` before touching anything that all 3
  were genuinely STALE (superseded by later commits already reviewed/pushed), not
  diverged real work, so safe to discard.
  **Fixed at the root cause this time, not just cleaned by hand again:**
  `scripts/hil_stage.sh`'s `sync()` now runs `git fetch origin <sha> && git reset
  --hard FETCH_HEAD && git clean -fd` instead of the old fail-hard `git checkout
  --detach FETCH_HEAD` — this function's whole job is "make the Jetson match commit
  X," which never actually required preserving local state, so a self-healing sync
  is the correct fix, not a defensive one. This also means `scripts/hil_stage.sh
  smoke` (the attended bench smoke test, `smoke()` calls `sync()` as its OWN first
  action) is now immune to this same failure class, not just CI.
  **A second, real bug was found WHILE testing this exact fix, before it was
  trusted:** a deliberate dirty-tree test (a stray tracked-file edit + an untracked
  probe file) proved the reset/clean logic itself worked, but a follow-up test using
  a REAL report filename pattern revealed `.gitignore` had a genuine gap —
  `reports/nav2_container_*.log` was covered, `reports/sensors_container_*.log` (the
  bench smoke test's own log, same age, same directory, same naming convention) was
  never added. Running the new `sync()` against the Jetson's actual dirty tree
  **deleted 6 real, uncommitted `sensors_container_*.log` files** (historical debug
  logs from earlier live-verification runs, not anything a currently-green run
  needs) as a genuine, unintended side effect of `git clean -fd` doing exactly what
  it was asked — not a bug in `git clean`, a real gap in what `.gitignore` told it
  was safe to remove. Fixed by broadening the pattern to `reports/*_container_*.log`
  (covers both current names and any future one sharing this convention) rather than
  just adding the one missing literal name. **Lesson: before trusting "X is
  gitignored, so this is safe," verify EVERY actual filename pattern the codebase
  writes into that directory — grep the scripts that create the files, don't infer
  coverage from a partial read of `.gitignore` itself.** This is exactly how the
  first version of this fix's own code comment ended up asserting a false "confirmed
  fully covered by .gitignore" claim — caught by testing the fix against a real dirty
  tree before pushing it, not by reading the diff more carefully.

## See also (moved out of this file by /doctor, 2026-07-27, context-lazy-loading pass)
- Nav2 launch gotchas (Session 10+) — `src/nav_fleet/CLAUDE.md`
- Isaac Sim gotchas (Session 11+) — `scripts/CLAUDE.md`
- Isaac GUI nav-test terminal procedure (Session 12+) — `isaac-gui-nav-test` skill
- Jetson Orin Nano hardware gotchas (Session 14+) — `jetson-hardware-notes` skill

---

# Moved from CLAUDE.md 2026-11-22

Verbatim text of the "Current status" paragraphs for the sessions of 2026-11-19,
2026-11-18, 2026-11-17, 2026-11-16 and 2026-08-12/13, the August "Where things stand",
"Repo state" and "Older punch list", as they stood in `CLAUDE.md` on 2026-11-22 before
being replaced there by one-line summaries.

**2026-11-19 session, in brief** (`docs/sessions/2026-11-19.md`): stop-on-silence proven
on the robot (see above); operator watch (`operator_link.py`, `operator_watch`): a run
started over SSH pauses after 2 s without the operator and resumes when the link
returns, gives up after 10 s more (never seen in a real mission); holds live in
`esp32_driver` (`HoldInput`, now `hold_input.py`): `/robot_001/operator_hold` and
`/robot_001/obstacle_hold`, and silence holds too when the watcher is mandatory;
`FollowPath.max_angular_accel: 10.0` cut the final heading error at home to 5-16 deg
(still peaks at 1.3-1.5 rad/s for 0.5 commanded: needs closed-loop turn rate);
ball-shaped-blob detection and the first `hsv_realcam.yaml`; obstacle guard
(`path_guard.py`, `obstacle_guard`): holds for 3+ lidar returns within 0.25 m of the
bumper in the direction of travel, does not guard spins; `ROBOT_BOOT_NAV2_PARAMS=<file>`;
the WiFi adapter (`rtl88x2ce`) roams between the router's radios by itself (~2.4 s of
silence each time); battery start line 10.5 V, log `~/fleet-ci-data/battery_log.csv`.

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

## Second pass, same day: longer versions of the 2026-11-22 and 2026-11-20 entries, the 2026-11-20 repo state, the shared-workstation entry and the release relabeling note

**2026-11-22 session (planning and workstation only; no robot, no simulator).**
- **Detector decided (Mike): RF-DETR for production, YOLO for comparison only, no
  training for now.** RF-DETR is Apache-2.0 like this repo; Ultralytics YOLO26/YOLOE are
  AGPL-3.0 (workstation use only). First experiment, pretrained weights on the saved
  real-camera frames: every model boxed nearly every ball (incl. a third ball with no
  hand-built rule), but small YOLO models named the yellow ball "orange" at up to 0.92:
  **a detector's confidence is not correctness, and it never says "unknown object"**.
  Box width gives distance at 6-8% error (hand-built: 12%); the floor-line rule holds
  for every box; `moondream` describes 22 of 25 ball crops as a ball with "Describe
  this image." and answers NOTHING to a yes/no prompt. Results, decisions and the
  agreed next steps: `docs/detection-history.md`. Scripts: `reports/detect_exp_20261122/`;
  environment `~/detect-exp-env` (not `fleet-env`). Later the same day, from the
  robot's camera: plush dog toys are found as "teddy bear"; RF-DETR boxed 8-9 of 12
  clutter objects (YOLO 3-4) but named few; flat, dark or shadowed things are missed.
  **On the Jetson (no install needed, `trtexec`): RF-DETR small 96 pictures a second,
  nano 163, 0.2 GB of memory, fine beside the Ollama vision model; the camera's 10
  pictures a second is now the limit.** Not yet built: the detector node (shadow mode
  next). Untested: rope or rubber toys, with Nav2 running, a moving robot.
- **Ollama today:** CI only (`tools/vlm_canary.py`, log-only, 83 of 83 simulator photos
  described as "red ball"); never called in a real-robot mission.
- **Wayfarer relationship (Mike):** wayfarer builds brain releases (a release may carry
  a "limited on this Jetson because..." caveat); this repo's robot receives them. The
  detector stays a separate node; the brain gets detections plus an "unknown object"
  kind. Two transfer notes written 2026-11-22 (ROS domain; detector and brain).
- New rule: existing-solution check (Gotchas, Process). New tool: `tools/proc_sweep.py`
  (see "Two projects, one workstation" below).

**2026-11-20 session** (full notes: `docs/sessions/2026-11-20.md`). Five floor runs.
- **Box in the path (step 1): PASSED.** Guard quiet on clear trips; held 0.22 m short of
  the box, beeped (too quietly), drove on by itself when the box was lifted.
- **Frozen IMU.** After one power-on the board's accel/gyro chip did not start and sent
  one frozen sample (gz = 706 deg/s); the pose estimate left home and the robot spun on
  the spot. A power-cycle clears it. Now: `ImuHealth` (`esp32_protocol.py`) judges the IMU
  on raw counts, `esp32_driver` refuses motion and stops publishing on a bad one, and
  `robot_boot.sh` will not start without `imu ok`. The frozen case was never seen live
  on the new driver (unit tests on the captured values only).
- **Dresser stall.** A hand-placed start took the robot at the dresser foot; the guard
  held it 0.18 m short and then NOTHING happened (Nav2 pushed forward for 10 s) until
  Mike turned it by hand. No back-away, no re-plan, no start-pose check.
- **Ball detection (step 2): red reacted, yellow missed by one frame.** The lamp-light
  profile lost red completely in daylight (hue 352-358 -> ~330) and lost yellow behind a
  closed curtain. Fix: a camera profile may carry a `floor:` section -- a ball resting
  on the floor has `bottom_row = row0 + slope * width_px` (325 + 1.32 w on this camera),
  and only blobs on that line count; `max_flat_aspect` allows a ball with its top lost
  to glare; red band widened. On the floor: both balls tracked continuously, first real
  reaction (red; stopped 58 cm from the ball), yellow got two frames inside 0.8 m and
  the rule needs three. Known limits are written in `hsv_realcam.yaml`.
- **Simulated box test (step 3): built and in CI.** `sim_only_launch.py
  obstacle_guard:=true` runs the real `obstacle_guard` on the sim scan plus
  `sim_wheel_hold` (stand-in for the driver's hold, same `HoldInput` rule);
  `tools/sim_box.py`; `tests/test_sim_box_guard.py`. CI stage 2 runs with the guard on.
  14 of 15 local runs passed; the one failure (first goal on a fresh simulator, no
  motion for 71 s after the box was removed) is unexplained and unreproduced.
- **WiFi address change killed a mission.** About a minute after the Ethernet is
  unplugged the Jetson's WiFi re-associates and gets a NEW address; every node's DDS
  sockets die, the driver's watchdog stops the wheels, and shutdown leaves the driver
  layer orphaned. Until fixed: after pulling the Ethernet, wait for the address to
  settle (`hostname -I` twice, a minute apart) before starting a run.
- `ROBOT_BOOT_DETECTOR=<folder>` mounts a trial `hsv_detect.py` + `hsv_realcam.yaml`
  over the image's for one run. Mast camera recorder: `~/robot_boot_debug/mast_record.py`
  on the Jetson only (plans: `docs/cameras.md` items 9-15).

**Repo state at close (2026-11-20):** code is `e91f5b8`, pushed (CI run `44838564976`
green, all nine stages incl. the Jetson and the new box test); the Jetson's checkout and
image match. Robot on its charger, Ethernet in.
Evidence under `reports/` (gitignored): `robot_boot_20261120_*`, `camera_cal_20261120_day/`,
`sim_box_20261120/`. A lessons note for wayfarer is in
`~/wayfarer/docs/transfer/2026-11-20-lessons-from-aft.md`.

**Mike expects the NEXT session to be on wayfarer** (he alternates: the real robot for
a while, then the simulator). The list below is for the next session back here.

**Two projects, one workstation (2026-11-22).** This repo runs on ROS domain 0;
wayfarer is moving to 42 (its own session's job: `~/wayfarer/docs/transfer/
2026-11-22-ros-domain-id-from-aft.md`). Every sweep on the workstation (`ci.yml` x3,
`hil_stage.sh` teardown, `mission2_day.sweep_orphans`) now goes through
`tools/proc_sweep.py`, which signals only processes started on our own domain (read
from `/proc/<pid>/environ`; unset counts as 0) and never its own shell. Use it instead
of `pkill -f` for anything by name on the workstation. Not yet protected: wayfarer's
processes until it actually sets 42 (unset looks like ours), and this repo from
wayfarer's own CI sweep until wayfarer scopes it. Until both are done: no push here
while wayfarer has a sim or CI run in flight, and the reverse. Not exercised in a real
CI run when this was written. 

**Releases relabeled 2026-07-17: numbers now = execution order.** The agentic &
alignment layer is **R2** — docs/notes older than 2026-07-17 saying "R4" mean today's
R2. **Ladder cut from 5 releases to 3 on 2026-07-28** (source of truth:
`planning/Releases2Plus.md`): R1 Foundation (ends at `r1-complete`) → R2 Agentic &
Alignment Layer + Real Onboard Autonomy → R3 Fleet & Input Expansion, Real SLAM, and
Autonomy & Perception. The former R4 (Autonomy & Perception) and R5 (Self-Testing
Fleet) are no longer standalone releases — their content was folded into R3 and the
long-range ideas doc. Drone CUT (revivable with a written reason).

## Moved from CLAUDE.md 2026-11-23

The 2026-11-20 session paragraph, verbatim as it stood in CLAUDE.md on 2026-11-23.

**2026-11-20 session** (`docs/sessions/2026-11-20.md`), five floor runs:
- **Box in the path: PASSED** (held 0.22 m short, drove on when the box was lifted; the
  beep is too quiet). **Simulated box test** is in CI (`sim_only_launch.py
  obstacle_guard:=true`, `sim_wheel_hold`, `tools/sim_box.py`,
  `tests/test_sim_box_guard.py`); 14 of 15 local runs passed, one failure unexplained.
- **Frozen IMU:** `ImuHealth` (`esp32_protocol.py`); the driver refuses motion and
  `robot_boot.sh` will not start without `imu ok`. Never seen to trip on the real robot.
- **Dresser stall:** the guard held the robot and then NOTHING happened. No back-away,
  no re-plan, no start-pose check.
- **Ball detection:** the floor rule (`floor:` section in a camera profile) fixed
  daylight; red reacted on the robot, yellow missed by one frame (two inside 0.8 m,
  three needed). (That detector and `hsv_realcam.yaml` were removed 2026-11-23.)
- **WiFi address change killed a mission.** After unplugging the Ethernet, wait for the
  address to settle (`hostname -I` twice, a minute apart) before starting a run.
- Mast camera recorder: `~/robot_boot_debug/mast_record.py` on the Jetson (`docs/cameras.md` 9-15).

The 2026-11-22 session paragraph, verbatim as it stood in CLAUDE.md on 2026-11-23.

**2026-11-22 session (the camera, the Jetson's GPU, three floor runs in the evening).** Detail:
`docs/detection-history.md` (results, decisions, next steps), `docs/sessions/2026-11-22.md`.
- **Detector decided (Mike): RF-DETR small for production, YOLO for comparison only, no
  training for now.** RF-DETR is Apache-2.0 like this repo; Ultralytics YOLO26/YOLOE
  are AGPL-3.0: keep them out of tracked code, the image and CI (`~/detect-exp-env`).
- **What the experiments showed:** pretrained detectors box nearly every ball and plush
  toy ("teddy bear") and most clutter, but names are unreliable (yellow ball =
  "orange" at 0.92): **confidence is not correctness, and a detector never says
  "unknown object"**. Flat, dark or shadowed things are missed. The floor-line rule
  still holds for every box. `moondream` works as a second opinion with "Describe this
  image." and answers NOTHING to a yes/no prompt.
- **On the Jetson** (TensorRT `trtexec`, already installed): RF-DETR small 96 pictures
  a second, 0.2 GB, fine beside the describer. The camera's 10 pictures a
  second is now the limit. An engine is built on the Jetson (about 3 min), from ONNX.
- **Floor run in shadow mode done (evening): the hand-written detector's results reach
  the mission about 3 s after the picture was taken** (RF-DETR shadow: 1 s). That, not
  the frame count, is why yellow does not react: nine pictures in a row had it in
  range, and they arrived as the leg ended. Likely `ball_detector.py:35`'s subscription
  queue of 10 with a consumer slower than the camera. **Retest with a queue of 1
  (mounted for one run): 1.39 s, and the yellow reaction fired for the first time on
  the real robot.** With no ball in the room the hand-written detector reported "red"
  in about 60 pictures; RF-DETR none. Both detectors are still 1-1.4 s behind during a
  mission (0.45 s idle): unexplained. Evidence `reports/robot_boot_20261122_shadow/`,
  `reports/robot_boot_20261122_q1/`; `docs/sessions/2026-11-22.md` sections 8-9.
- **First floor run with RF-DETR in control (18:26): both reactions fired, colors named
  correctly, detections 0.92 s after the picture. The return from yellow STALLED at the
  door frame:** the obstacle guard held 61 s and nothing followed (third time; "go
  around" is missing). CI's simulator stage failed twice beside wayfarer's CI and passed
  idle. Wayfarer wrote its own RF-DETR node; the two need merging
  (`docs/sessions/2026-11-22.md` section 11).
- **RF-DETR became the robot's detector (Mike, evening).** Yellow from red is read
  from the color INSIDE the network's box (`ball_color`), published as `yellow_ball` /
  `red_ball`. Node `object_detector` (`rfdetr_detect.py`, `rfdetr_backends.py`); 10
  pictures a second live on the Jetson (camera-limited), pictures about 0.35 s old at
  publish. Model files: `~/fleet-ci-data/models/` on the Jetson.
  `tests/test_object_detector.py` needs ROS and runs in no CI stage. Untested:
  rope/rubber toys, a moving robot.
- **Ollama today:** CI only (`tools/vlm_canary.py`, log-only); never in a real mission.
- **Wayfarer (Mike):** wayfarer builds brain releases (a release may carry a "limited
  on this Jetson because..." caveat); this robot receives them. Both projects are about
  the brain more than the hardware: a cheap robot feeds a "mother ship". The detector
  stays a separate node. Plan in order: RF-DETR under the mission script; the
  describer proven in a real run; untrusted boxes to the describer, log-only; then
  wayfarer's mission's behavior tree and brain installed here (in one step or two: not
  decided). The list of goals (down) and events (up) is drafted:
  `docs/goals-and-events.md`, with milestones M1-M6. It shows the install is blocked
  by Nav2's `Spin`/`BackUp` failing on the real robot and by holds nobody listens to.

### Moved the evening of 2026-11-23: the Release 1 order of 2026-11-20 (all six items since built)

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
