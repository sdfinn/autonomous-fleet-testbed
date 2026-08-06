# Real-robot driver layer + bench smoke test — design

**Status:** approved pending Mike's review of this file
**Supersedes/extends:** `RealRobotStartup.md` A2's driver-layer step (rewritten earlier
this session);
`docs/superpowers/specs/2026-08-03-docker-brain-real-robot-hil-unification-design.md`
(same container/entrypoint philosophy, extended with a third mode)

## Context

`RealRobotStartup.md` A2 requires four real topics (`/robot_001/odom`, `/scan`,
`/camera/image_raw`, `/imu/data`) and a working `cmd_vel`→wheels path before anything
else in Part A can proceed. Investigation this session (2026-08-05/06) found:

- Waveshare's own ROS2 workspace (`waveshareteam/ugv_ws`) is Humble-only — no Jazzy
  branch, official or otherwise. Not usable as-is on this project's Jazzy-only stack.
- `robot_profiles/jetson_ugv_pt.yaml` already names the real hardware: lidar D500/
  STL-19P, camera OAK-D Lite, sub-controller an ESP32 over UART @921600 baud. Two of
  the three have vendor-maintained **Jazzy-native** ROS2 packages, independent of
  `ugv_ws`, confirmed working: `ldrobotSensorTeam/ldlidar_ros2` (lidar),
  `luxonis/depthai-ros` (camera). Only the ESP32 link (odom + IMU + `cmd_vel`) has no
  such package — Waveshare documents its JSON-over-serial protocol independently of
  `ugv_ws` (wiki + `waveshareteam/ugv_base_general`/`ugv_base_ros` reference
  firmware), so a small native node is buildable without waiting on the vendor.
- Separately, Mike raised a bench smoke-test concept: bring the robot up on the table
  (Ethernet, then WiFi), with no Nav2/navigation involved, and confirm the driver
  layer actually works — a photo, a lidar reading, a small commanded motion — before
  ever trusting it under Nav2. This doc covers both: they're one project because the
  smoke test is the acceptance test for the driver node, and the driver node has no
  other way to be verified before the robot physically exists.

Decided in conversation this session, not re-litigated here:
- **Embed smoke-test as a third mode of the existing one image/one entrypoint**
  (`scripts/container_entrypoint.sh`), not a second image — matches the
  docker-brain-unification convergence this project already committed to.
- **Standalone power-on can never run a smoke test.** `ROBOT_MODE` is a *required*
  env var with no implicit default; `robot_boot.sh` (systemd-invoked, no workstation
  involved) hardcodes `ROBOT_MODE=mission`. Smoke test is only ever triggered
  deliberately, from the workstation.
- **Smoke-test results must not touch drift metrics.** Logged to a new, isolated
  `smoke_test_runs` table in `fleet_runs.db` — same pattern as `coverage_runs`/
  `vlm_canary_log` — never read by `baseline_monitor.check_run()`.
- **PASS/FAIL should be automatic wherever possible.** Operator eyes-on stays a
  cheap, valuable backstop (per this project's established "ground truth by eye"
  practice for every other real-robot check) but isn't load-bearing for the verdict.

## Scope

**In scope:**
1. `esp32_driver` — new ROS2 node, `src/nav_fleet/nav_fleet/`, bridging the ESP32
   sub-controller: subscribes `/robot_001/cmd_vel`, publishes `/robot_001/odom` +
   `/robot_001/imu/data`.
2. `sensors_only_launch.py` — new launch file bringing up the driver layer
   (`esp32_driver`, `ldlidar_ros2`, `depthai-ros`) + `ekf_node` + `ball_detector`,
   deliberately WITHOUT Nav2/AMCL/map_server — no map required, so this runs even
   before `bedroom_real.yaml` exists.
3. `tools/smoke_test.py` — the bench smoke-test orchestrator.
4. `ROBOT_MODE` branching in `container_entrypoint.sh` (`mission` | `smoke_test`).
5. `scripts/hil_stage.sh smoke` — the workstation-triggered invocation.
6. A `smoke_test_runs` table + logging (mirrors `coverage_log.py`'s shape).
7. CI regression coverage for the smoke-test *machinery* in stage-2/stage-4 (not real
   hardware — see Testing).

**Out of scope (explicitly deferred):**
- Installing `ldlidar_ros2`/`depthai-ros` themselves on the Jetson — Mike's manual
  install, per standing practice, happens around Aug 11.
- The exact ESP32 JSON command/telemetry schema — pulled from Waveshare's docs at
  implementation time, not guessed here (see Risks).
- Any dashboard tab for `smoke_test_runs` — logging is in scope, visualization isn't.
- Real-hardware validation of any of this — cannot happen before the robot exists.

## Architecture

```
Workstation                          Jetson (one image, one entrypoint)
────────────                         ──────────────────────────────────
hil_stage.sh smoke  ──SSH/docker run──▶  container_entrypoint.sh
  (sets ROBOT_MODE=smoke_test)              │
                                             ├─ source setup, regen DDS (shared,
                                             │  unchanged from mission mode)
                                             ├─ ROBOT_MODE == smoke_test?
                                             │    ├─ launch sensors_only_launch.py
                                             │    │  (esp32_driver, ldlidar_ros2,
                                             │    │   depthai-ros, ekf_node,
                                             │    │   ball_detector — no Nav2)
                                             │    └─ python3 -m tools.smoke_test
                                             └─ ROBOT_MODE == mission (robot_boot.sh
                                                default, hardcoded, never overridden)
                                                  └─ existing nav2_only_launch.py +
                                                     mission_runner --day flow,
                                                     unchanged
```

### `esp32_driver` node

- Params: serial device path, baud (921600, from `robot_profiles/jetson_ugv_pt.yaml`),
  `watchdog_timeout_ms` (200, same source).
- Publishes `/robot_001/odom` (`nav_msgs/Odometry`, unprefixed frame IDs — same
  convention `ekf.yaml`'s `odom0` already expects) and `/robot_001/imu/data`
  (`sensor_msgs/Imu`) at whatever rate the board streams — target ≥50 Hz / ≥200 Hz
  per the robot profile's `hz_min` values; confirm against real hardware, not assumed.
- Subscribes `/robot_001/cmd_vel` (`geometry_msgs/Twist`), encodes to the ESP32's JSON
  command format, writes to serial.
- Implements the watchdog itself: no `cmd_vel` within `watchdog_timeout_ms` → send a
  zero-velocity command proactively. This is not new scope invented for this doc — the
  robot profile already declares it; this is where it gets implemented.
- Design intent: from `ekf_node`/Nav2's point of view, this node is a drop-in
  replacement for Gazebo's sim bridge — same topics, same message types, same frame
  convention. Zero changes needed anywhere else in the stack.

### `sensors_only_launch.py`

Sibling to the existing `sim_only_launch.py`/`nav2_only_launch.py` split
(`src/nav_fleet/launch/`) — same naming convention, same idea: one clearly-scoped
launch file per concern. Starts the driver layer + `ekf_node` + `ball_detector`;
explicitly does not include `nav2_bringup`. This is what lets the smoke test run
before a real map exists, and keeps it decoupled from AMCL/planner health entirely —
it's testing "do the senses work," not "can it navigate."

### `tools/smoke_test.py`

Orchestrator, same tier as `mission2_day.py`. Sequence:

1. **Topic sanity (fully automatic).** For each of odom/scan/camera/imu: confirm the
   topic publishes, at ≥ the `hz_min` already declared in
   `robot_profiles/jetson_ugv_pt.yaml` (first real consumer of those values), and that
   payloads aren't degenerate (all-zero/all-NaN scan ranges, a blank/all-black image,
   etc.) — catches "device didn't actually init" even when a topic technically exists.
2. **Photo (fully automatic).** One `take_picture` call (reuses
   `image_io.image_msg_to_png`, same primitive Mission 2 already uses); PASS if the
   file exists and isn't degenerate.
3. **Lidar + camera physical correlation (semi-automatic — operator provides the
   physical event, the tool detects it).** This is the answer to "operator can't
   really read lidar": prompt the operator to hold the actual red or yellow ball
   within ~1 m of the robot's front for a short window, then poll two things
   automatically during that window — a near-range dip in the forward arc of
   `/robot_001/scan`, and a matching-color hit on `/robot_001/detections`
   (`ball_detector` is already running as part of `sensors_only_launch.py`). One
   physical action, two independent automatic confirmations — proves the lidar is
   measuring real distances (not stuck/cached) and that the HSV calibration pipeline
   (`hsv_realcam.yaml`, from A4) works end-to-end, not just that raw frames arrive.
   **Reuses the existing `BallOps` abstraction** (`tools/mission2_day.py`):
   `GzBallOps` (`concurrent=True`) already exists for sim/HIL — CI spawns a ball
   programmatically, no human needed. A new `OperatorWaveBallOps` (`concurrent=False`,
   parallel to the existing `OperatorBallOps`) prints the prompt and waits for the
   operator, for the real-robot case. Same interface, same pattern, not a new concept.
4. **Motion (fully automatic verdict, operator watch recommended).** Two short,
   open-loop `cmd_vel` pulses — a small forward translation, then a ~15° turn — with
   `/robot_001/odom` read before and after each. PASS requires the measured delta to
   be non-trivial and in the commanded direction (generous tolerance — this is a
   sanity check, not a calibration). Operator visual confirmation is still worth
   doing (catches things odom alone can't, e.g. wheels spinning but the chassis stuck)
   but isn't required for the automated verdict, consistent with how this project
   already treats eyes-on checks as a valued addition, not a replacement, elsewhere.
5. **Summary + exit.** Print an itemized PASS/FAIL per check plus measured values;
   overall PASS only if every check passes; non-zero exit code on any FAIL. Log one
   row to `smoke_test_runs` (new table, `tools/smoke_test_log.py`, same
   isolated-table/`--db`-flag convention as `coverage_log.py`).

**Interactive prompting is deliberate here**, unlike `mission_runner`'s hard "no
prompting" rule — that rule exists because the daily mission must run unattended
under `robot-mission.service`. The smoke test is by definition an attended bench
tool; a human choosing to run it is standing right there. Different context, no
contradiction.

### `ROBOT_MODE` branching

`container_entrypoint.sh` requires `ROBOT_MODE` (`mission` or `smoke_test`) — no
implicit default, fail loudly if unset, matching this project's established
fail-loud-not-silent convention (the image-presence check, the sha-derivation
gotcha). `robot_boot.sh` hardcodes `ROBOT_MODE=mission` — never a variable that could
be left set wrong. `scripts/hil_stage.sh smoke <sha>` is the new, only way to trigger
`smoke_test` mode: SSHes to the Jetson, same image-presence-check/tag mechanism
`robot_boot.sh` already uses, `docker run` with `ROBOT_MODE=smoke_test`.
`robot-mission.service` is untouched — it only ever calls `robot_boot.sh`.

### CI coverage (stage-2, stage-4)

Adds a smoke-test-mode regression run to both stages, using each stage's existing
sensor source (Gazebo's bridge in stage-2, Gazebo↔Jetson DDS in stage-4-hil) in place
of real hardware, and `GzBallOps` for the wave-the-ball step (already exists, no new
code). **This validates the smoke-test tooling's own logic — branching, Hz-checks,
photo capture, detection-correlation, motion-delta math — not real ESP32/lidar/camera
hardware**, which can't be exercised before Aug 11 regardless. Worth this doc being
explicit about that distinction so a future green CI run is never mistaken for "real
hardware confirmed." Results log to `smoke_test_runs` tagged with the existing
`runner_type` convention (`local`/`hil_jetson`), same table real-robot runs use —
never `runs`, so drift metrics are structurally unaffected either way.

## Error handling

- Serial port missing/permission-denied at `esp32_driver` startup: fail loudly on
  node init, don't retry-forever-silently (matches this project's established
  preference for a single loud failure over a silent hang).
- Any smoke-test check failing does not abort the remaining checks — run all of them,
  report all results, matching `mission_runner`'s own "the checklist IS the verdict"
  philosophy rather than stopping at the first red.
- `sensors_only_launch.py` failing to bring up within a bounded wait: same
  fail-loud-with-log-tail pattern `container_entrypoint.sh` already uses for Nav2's
  own readiness wait.

## Testing

**Buildable and testable now, without hardware:**
- `esp32_driver`'s protocol encode/decode (Twist→JSON command, JSON telemetry→
  Odometry/Imu) as pure functions — unit-tested against fake/mocked serial bytes, no
  real device needed. The `serial.Serial(...)` I/O boundary itself stays thin and
  deliberately untested until real hardware exists — same treatment this project
  already gives other hardware boundaries (`JetsonExecutor`'s SSH layer, `GzBallOps`
  vs `OperatorBallOps`).
- `sensors_only_launch.py` — testable in sim right now (Gazebo's bridge already
  publishes everything it expects).
- `tools/smoke_test.py`'s logic — Hz-threshold checks, photo-exists checks, odom-delta
  math, the wave-ball-correlation polling — all testable against sim/HIL today via
  `GzBallOps`.
- `smoke_test_runs` logging + the isolated-table guarantee (never read by
  `baseline_monitor`) — fully testable now, same as `coverage_log.py`'s tests.

**Cannot be tested before the robot exists:**
- The ESP32 link actually working over real serial hardware.
- `ldlidar_ros2`/`depthai-ros` against the real D500/OAK-D Lite units.
- Real motion — wheels actually turning, not just a mocked odom delta.
- The WiFi-only rehearsal (Ethernet unplugged) this smoke test also happens to serve
  as, per the earlier session discussion — needs the real bench setup to mean anything
  beyond what's already been proven for SSH/mDNS.

## Known implementation-time risks

- **Exact ESP32 JSON schema is not yet pinned down in this doc.** Waveshare's wiki +
  `ugv_base_general`/`ugv_base_ros` are the source — read those at implementation
  time; don't guess field names now. If the schema turns out to need something this
  design didn't anticipate (e.g. a handshake/init sequence beyond simple JSON frames),
  that's an implementation-time finding, not a design failure.
- **Real achievable odom/IMU rate over 921600 baud JSON framing is unverified.** Should
  comfortably support the profile's 50/200 Hz targets on paper; confirm live once
  hardware exists rather than assuming.
- **Serial device path** (`/dev/ttyUSB0` vs a 40-pin UART device node) depends on how
  Mike wires the physical connection — make it a launch/env parameter, not hardcoded,
  so this is a bench decision, not a code change.
- **`ldlidar_ros2`/`depthai-ros` topic/frame conventions almost certainly won't match
  this project's `/robot_001/...`, unprefixed-frame-name conventions out of the box** —
  expect a remapping layer in `sensors_only_launch.py`, same treatment already applied
  to `ekf_node`/`ball_detector` in `nav2_only_launch.py` today.

## Open questions for the plan (not this doc)

None blocking — the two items Mike explicitly asked about (CI/drift safety,
standalone-start safety) are resolved above as committed design decisions, not left
open.
