# Mission 2 design — camera-reactive navigation

**Status: APPROVED (Mike, 2026-07-16) — brainstorm complete, ready for
`superpowers:writing-plans` (Plan B). Supersedes the Decision-5 sketch in
`2026-07-10-session15-gazebo-hil-mission1-design.md` and the pre-draft Piece 2
checkboxes in `Release1Todo.md` where they conflict.**
(Was `2026-07-15-session16-mission2-design-draft.md`; the 2026-07-15 decisions are
unchanged, the former open questions are now resolved in §3–§9.)

**Implemented:** 2026-07-18, draft PR #4 (all three HIL rungs live-proven on the Jetson).

## 1. Mission definition

1. **Preset navigation, no search.** The robot is told where to go; "find it yourself"
   exploration is a later capability stage, deliberately not this one.
2. **The mission:** drive from home to the fixed green sphere at (0, 3.7) — the existing
   BR-01 marker — and **stop before hitting it**. Green sphere stays camera/marker-only
   (no collision, below lidar); the nav goal is placed short of it and the test asserts
   the physical stop distance via Gazebo ground truth (the Session 16 honesty meter).

## 2. Reaction semantics

- **Yellow ball "come across" → take a picture, return home.** (Caution: document and
  retreat.)
- **Red ball "come across" → take a picture, full stop.** (Danger: document and freeze.)
- Both are supervisor moves on existing primitives (cancel Nav2 goal → take_picture →
  navigate-home | stop). **No dynamic costmap layer in Mission 2** — the
  "avoid-and-continue" keepout capability is DEFERRED to Mission 3 (coverage), where
  routing around an obstacle mid-sweep actually matters.
- **"Come across" = trigger definition A — proximity + persistence:** a ball whose
  apparent size implies range ≤ ~1 m, sustained 3 consecutive frames; the camera FOV is
  the only bearing filter. A glimpse that doesn't persist (ball seen at 2 m, or lost
  while turning toward the goal before 3 frames) does NOT trigger — the robot keeps
  going. Exact numbers calibrated during implementation against Gazebo ground truth
  (§6), not guessed. **Definition B (bearing corridor) is recorded as a future-mission
  need, not built now.**

## 3. Scenario variants and pass/fail (ground truth = Gazebo, the honesty meter)

One ball per run; three variants, each a separate scenario run. "Band" below =
distance measured by the HARNESS between ground-truth poses; nominal numbers
**0.3 m (near) / 1.3 m (far)**, calibrated during implementation and then fixed in the
test config.

- **`mission2_red`** — red ball placed inside the reaction envelope. PASS =
  detection fired **and** photo file exists **and** robot is stationary at mission end
  **and** its final pose is within the band of the ball's true position. Near bound
  proves it didn't hit the ball; far bound proves it stopped BECAUSE of the ball (a
  robot that quit 3 m away for an unrelated reason FAILS).
- **`mission2_yellow`** — yellow ball placed inside the reaction envelope. PASS =
  robot's pose at the moment the reaction fired is within the band of the ball
  **and** photo file exists **and** final pose is physically within ~0.3 m of
  `home_base`. The reaction-point check catches a badly calibrated trigger that fires
  at 3 m even when the retreat itself succeeds.
- **`mission2_ignore`** — ball placed so it can never trigger (§5). PASS =
  **zero reaction events of any kind** during the whole run **and** the mission
  completes exactly like the nominal mission: robot physically stops short of the
  green sphere within its own ground-truth band. This variant is simultaneously the
  detector's false-positive test and the nominal-mission regression test.

Failure edges these definitions already cover: detector never fires on a must-react
run → mission completes "nominally" → FAIL (no reaction event / wrong final pose);
spurious reaction on an ignorable run → FAIL (zero-reactions clause); reaction fires
but photo write fails → FAIL (photo clause).

## 4. Architecture — reactive step in the mission executor

- **Mission data model:** the `navigate` step gains an optional `reactions` field,
  declared in `missions.py` data, e.g.
  `reactions={'red': 'photo_then_stop', 'yellow': 'photo_then_home'}`.
  Missions stay pure data (no ROS imports). A step without `reactions` behaves exactly
  as today — **Mission 1 is untouched.**
- **Supervision lives in `mission_runner`:** while awaiting the Nav2 goal result it
  also watches the detection topic; on a trigger (per §2's persistence rule) it cancels
  the goal via `cancel_goal_async()` and executes the declared reaction using existing
  primitives. No new long-running process, no custom Behavior Tree (explicitly
  rejected), no separate supervisor node (rejected: splits mission state across
  processes and moves policy out of mission data).
- **Detector node (new, `nav_fleet/`):** HSV thresholding — the algorithm from BC's
  `behavior_controller.py` (hardware-proven, zero training data) reimplemented to this
  project's conventions. Subscribes to a **remappable** image topic; publishes
  **`vision_msgs/Detection2DArray`** (class `red_ball`/`yellow_ball`, bbox → bearing
  from pixel x + FOV, apparent size from bbox). No custom rosidl package.
  **Publishes one message per processed camera frame INCLUDING empty frames**, so
  "3 consecutive frames" is directly countable by the subscriber with no timing
  heuristics. **Always-on with the nav stack** (launched alongside Nav2, one lifecycle,
  nothing to choreograph); mission_runner simply ignores detections during steps with
  no `reactions`.
- **Dependency rule (learned twice):** `ros-jazzy-vision-msgs` is declared on the
  workstation, the Jetson, AND in the arm64 Dockerfile **in the same commit** that
  first imports it.
- HSV thresholds are config data, not code: `config/hsv_gazebo.yaml` now,
  `config/hsv_realcam.yaml` in the webcam follow-up (§9); the measured delta between
  them is itself a sim-to-real data point worth keeping.

## 5. Ball placement — harness-owned, seeded random

- The TEST HARNESS (never the mission runner) spawns the ball via the Gazebo spawn
  service. **Hard boundary: robot code must not know ball positions** — sim truth
  belongs to the judge, not the contestant (2026-07-15 false-PASS lesson).
- Must-react placements put the ball inside the reaction envelope of the planned
  route; ignorable placements guarantee the ball never comes within reaction range
  + ~0.5 m margin of any route point (route corridor sampled from the planned
  waypoint legs).
- **Seed policy: fresh random seed per CI run, per variant, logged and stored (§7).**
  CI becomes a slow, honest fuzzer over the placement space; any failure reproduces
  exactly from its seed, so a "new" failure is signal, never dismissible as flake.

## 6. Ball geometry and size→range calibration

- **Real croquet size, ~86 mm diameter, on the floor.** If it proves marginal at the
  1 m trigger range from the camera's mounting height, we pitch the CAMERA down —
  never inflate the ball, or the calibration becomes fiction and Session 18's real
  balls invalidate it.
- **Calibration procedure (one-time, scripted):** spawn the ball at known ranges from
  the camera (Gazebo ground truth), record apparent size per range, fit the
  size→range curve. The constant lives in the same per-camera config file as the HSV
  thresholds (`hsv_gazebo.yaml`) — it is camera-specific exactly like the thresholds,
  and the webcam tier will produce its own (`hsv_realcam.yaml`).

## 7. Telemetry

- **Distinct scenario names:** `mission2_red` / `mission2_yellow` / `mission2_ignore`.
  Zero schema redesign — per-variant drift baselines fall out of the existing
  scenario keying (baseline_monitor already slices by runner_type + power_mode), and
  the variants' metric profiles are too different to pool (red stops early, yellow
  drives out-and-back, ignore looks nominal).
- **New nullable `seed` column on `runs`** (NULL for Mission 1 rows). The pandera
  schema learns the column **in the same commit** — never as a follow-up fix
  (power_mode / hil_jetson lesson). Makes failures queryable: "every seed that ever
  failed" is one DB query, from the dashboard too.

## 8. CI shape and HIL rollout

- **Stage-2 (sim):** each run executes Mission 1 (unchanged) plus the three Mission 2
  variants, one fresh seed each. Budget: stage-2 ran 107 s on 2026-07-16; three more
  short mission runs lands it well inside the stage's historical envelope — revisit
  only if it crowds the "CI stage wall times" watch item.
- **Stage-4-hil (Jetson): incremental graduation, NO formal 3×-green gate**
  (Mike, 2026-07-16 — the pipeline runs constantly and self-proves). Ladder:
  **ignorable → red → yellow**, each added once stable in sim, **all three in HIL
  within Release 1**. The ignorable variant serves as the "nominal" first rung — it
  IS the base mission plus a must-not-trigger ball. The HIL story is unchanged
  mechanically: camera frames come from Gazebo over the bridge even when Nav2 +
  detector run on the Jetson; balls are sim-side.
- Reference wall times (2026-07-16, all-green run 29545011894): stage-3 161 s (warm
  registry cache — expected band ~150 s warm / ~570 s cold), stage-4 103 s.

## 9. Webcam manual tier — follow-up plan, not Plan B

The real-camera tier (UVC webcam on the Jetson, Mike presenting croquet balls,
`hsv_realcam.yaml` calibration, pinned exposure/white-balance, clock-domain decision)
becomes its own small plan once the webcam physically arrives. Plan B is sim tier +
HIL graduation only, so it is never blocked on shipping. The Release1Todo Piece 2
webcam checkboxes transfer to that follow-up.

## 10. Future-mission framework (recorded so it isn't re-invented)

"**Safely avoidable**" is the Mission 3+ decision: geometry (does a clear route
exist?) × confidence (detection + localization certainty) × mission priority. Its
ingredients are exactly the deferred pieces: trigger definition B / position
projection, the costmap keepout (avoid-and-continue), and Mike's uncertainty-aware
speed principle ("slow down when unsure, speed up when the risk is low" — first crumb
already shipped as the slower rotate-to-heading). Roadmap: Mission 2 = react
correctly; Mission 3 = avoid deliberately; Session 19+ = modulate behavior by
uncertainty.
