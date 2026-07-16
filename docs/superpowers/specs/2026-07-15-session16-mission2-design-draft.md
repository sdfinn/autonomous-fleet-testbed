# Mission 2 design — camera-reactive navigation (DRAFT, brainstorm in progress)

**Status: DRAFT — decisions below are agreed with Mike (2026-07-15 evening session);
open questions listed at the end are the resume point. This supersedes the Decision-5
sketch in `2026-07-10-session15-gazebo-hil-mission1-design.md` where they conflict.**

## Decided (Mike, 2026-07-15)

1. **Preset navigation, no search.** The robot is told where to go; "find it yourself"
   exploration is a later capability stage, deliberately not this one.
2. **The mission:** drive from home to the fixed green sphere at (0, 3.7) — the existing
   BR-01 marker — and **stop before hitting it**. Green sphere stays camera/marker-only
   (no collision, below lidar); the nav goal is placed short of it and the test asserts
   the physical stop distance via Gazebo ground truth (the Session 16 honesty meter).
3. **Reaction semantics (REPLACES Decision 5's yellow-keepout):**
   - **Yellow ball "come across" → take a picture, return home.** (Caution: document
     and retreat.)
   - **Red ball "come across" → take a picture, full stop.** (Danger: document and
     freeze.)
   - Both are supervisor moves on existing primitives (cancel Nav2 goal →
     take_picture → navigate-home | stop). **No dynamic costmap layer in Mission 2** —
     the "avoid-and-continue" keepout capability is DEFERRED to Mission 3 (coverage),
     where routing around an obstacle mid-sweep actually matters. Confirmed by Mike.
4. **"Come across" = trigger definition A — proximity + persistence:** a ball whose
   apparent size implies range ≤ ~1 m, sustained 3 consecutive frames; the camera FOV is
   the only bearing filter. Exact numbers calibrated during implementation against
   Gazebo ground truth, not guessed. **Definition B (bearing corridor) is recorded as a
   future-mission need, not built now.**
5. **Random ball placement, harness-owned:** the TEST HARNESS (never the mission runner)
   spawns red/yellow balls via the Gazebo spawn service — sometimes inside the reaction
   envelope (must react), sometimes deliberately ignorable (must NOT react: spawned so
   the ball never comes within reaction range + ~0.5 m margin of any route point).
   Placement is SEEDED random with the seed logged, so any CI failure reproduces
   exactly. Hard boundary: robot code must not know ball positions — sim truth belongs
   to the judge, not the contestant (2026-07-15 false-PASS lesson).
6. **Perception:** HSV detector node per the standing decisions — BC algorithm
   reimplemented to this project's conventions, remappable image topic, publishes
   color + bearing + apparent size; thresholds as per-source config
   (`hsv_gazebo.yaml` / `hsv_realcam.yaml`). Two-tier camera stands: CI tier =
   scripted Gazebo spheres; manual tier = UVC webcam + real croquet balls with Mike.

## Future-mission framework (recorded so it isn't re-invented)

"**Safely avoidable**" is the Mission 3+ decision: geometry (does a clear route
exist?) × confidence (detection + localization certainty) × mission priority. Its
ingredients are exactly the deferred pieces: trigger definition B / position
projection (option C), the costmap keepout (avoid-and-continue), and Mike's
uncertainty-aware speed principle ("slow down when unsure, speed up when the risk is
low" — first crumb already shipped as the slower rotate-to-heading). Roadmap:
Mission 2 = react correctly; Mission 3 = avoid deliberately; Session 19+ = modulate
behavior by uncertainty.

## Open questions (brainstorm resume point)

1. Pass/fail definitions per scenario variant: red run (PASS = stopped + photo,
   ground-truth distance-to-ball assertion?), yellow run (PASS = photo + physically
   home), ignorable run (PASS = reached sphere, ZERO reactions, stop-short-of-green
   assertion). Telemetry: one scenario name (`mission2`) with variant column, or
   distinct scenario names per variant?
2. Supervisor architecture: extend the mission data model (a reactive navigate step
   type?) vs a supervisor node wrapping NavRunner — and where the reaction policy
   (color → response) lives (mission data, ideally).
3. Detection message type: custom msg vs `vision_msgs`; publish rate; detector node
   lifecycle (always-on vs mission-scoped).
4. Apparent-size → range calibration procedure (one-time, against gz truth) and where
   the calibration constant lives.
5. Ball placement constraint solver details (route corridor sampling; how many balls
   per run; red and yellow in the same run or separate CI variants?).
6. CI shape: how many seeded variants per stage-2 run (time budget); HIL tier scope
   for Mission 2 (Jetson runs Nav2 while balls are sim-side — camera images come from
   Gazebo, so the HIL story works unchanged?).
7. Webcam manual tier: in this plan or a follow-up (hardware purchase status)?
8. Croquet-ball geometry in sim: sphere size/height vs camera FOV and the ~1 m
   trigger; must be visible at reaction range from robot camera height.
