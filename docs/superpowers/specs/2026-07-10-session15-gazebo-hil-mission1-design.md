# Session 15 — Gazebo Hardware-in-the-Loop, Mission 1 Design

**Date:** 2026-07-10
**Status:** Approved (mission numbering revised 2026-07-11 on Mike's review — see note below)
**Scope:** Session 15 (Isaac Sim + Real Jetson Hardware-in-the-Loop, per `Release1Todo.md`) — sim engine decision, mission-framework shape, and the first concrete HIL milestone. Does not cover Mission 2 (full-area coverage + camera-reactive behavior), which is an explicitly deferred follow-up.

> **Mission numbering note (2026-07-11):** As originally written, the *first* milestone was
> called "Mission 2" and the *deferred* follow-up "Mission 1" — a leftover of the order the
> ideas came up in brainstorming, and confusing on review. Renumbered so numbering follows
> build order: **Mission 1 = navigate → photograph → return (this spec's first milestone);
> Mission 2 = full coverage + camera-reactive behavior (the deferred follow-up).** Any doc or
> note dated 2026-07-10 that says "Mission 2 first" is using the old numbering.

---

## Where this came from

Session 15 was created 2026-07-10 as a promotion of Session 14's optional "Jetson-in-the-loop with sim" stretch goal, after a CI pipeline-restructuring conversation (captured from a hand-drawn diagram) surfaced a bigger version of the idea: not just validating that Nav2 fits the Orin Nano's resource budget, but Isaac Sim and the real Jetson genuinely talking to each other as a CI-testable hardware-in-the-loop stage. Session 15's own text left the sim-engine choice deliberately open, pending research rather than assumed. This design closes that question and scopes the first real milestone.

---

## Decision 1: Gazebo, not Isaac Sim, for both Stage 2 and Stage 4/HIL

**Decision:** Gazebo is the simulation engine for both the existing Stage 2 (Gazebo nav tests) and the new Stage 4/HIL work. Isaac Sim is shelved for this line of work — not discarded, revisitable independently whenever a mission genuinely needs what Isaac uniquely offers.

**Reasoning, worked through against this project's own evidence, not vendor claims:**

- The camera actually drives navigation/mission decisions (object detection for mission triggering), not just monitoring — this was the first fork point, since a monitoring-only camera would have made the engine choice not matter much.
- The concrete near-term perception need — distinguishing red vs. yellow colored spheres — needs zero training data. It's solved by classical CV (HSV thresholding), already proven: the prior BC project's `src/behavior_controller.py` implements and validates exactly this (hand-tuned HSV ranges, pixel-count thresholds, tested against both a live USB camera with real croquet balls and simulated camera frames). `MasterBrief.md`'s mention of YOLO for this was aspirational planning text that was never actually built — the real, working implementation used classical CV.
- Isaac Sim's genuine differentiators — Omniverse Replicator's synthetic data generation (domain randomization, free ground-truth labels) and NITROS-accelerated Isaac ROS perception — only pay off once a mission needs a *trained* model (varied/unknown objects, real-world lighting robustness beyond a hand-tuned threshold). Neither applies to the current mission.
- Important nuance: NITROS is Isaac ROS's runtime transport, not part of Isaac Sim itself. Adopting NITROS-accelerated perception on the real deployed Jetson later is a decision independent of which simulator is used for development now.
- Isaac Sim's proven fragility in this project (`CLAUDE.md`'s Isaac gotchas, ~20 debugging iterations to get one passing nav test in Session 11/12) splits into two buckets:
  - **General operational tax** (applies regardless of mission): `/clock` not auto-published, DDS TRANSIENT_LOCAL requiring Isaac+Nav2 to be restarted together every run, RTX lidar broken headless (worked around with PhysX raycasting), wheel-drive damping needing manual patching.
  - **Nav2/AMCL/costmap-specific fragility** (only applies if running the full Nav2 stack under Isaac): AMCL false-positive "success" while physically stuck, recovery behaviors failing 100% of attempts, `collision_monitor` silently self-locking the robot, `SmacPlannerHybrid` footprint tuning as the single biggest time sink in Session 11/12.
  - No camera/perception-specific Isaac issue has ever been hit in this project — the fragility has always been on the localization/navigation-stack side.
- Gazebo's own scaling ceiling for a future multi-robot fleet is a real open question, but an *unmeasured* one — this project has never simulated more than one robot. A concrete, already-hit precedent (CycloneDDS domain-0 participant-limit exhaustion with Nav2's default non-composed launch, for a single robot) suggests DDS discovery scaling is worth watching, but resolving it needs actual measurement (spin up N robot instances, watch RTF degrade), not speculation. Isaac Lab's "thousands of parallel environments" claim is usually about many independent simple training instances, not one shared multi-agent world — not a clearly-better answer to this project's actual fleet-coordination scaling problem either. Deferred as a concrete future experiment, not resolved here.

**Net effect:** choosing Isaac here would mean paying its proven, real cost for a mission that exercises none of its differentiating strengths. The reasoning for Gazebo is not "Isaac can't do this" — nothing about the mission is structurally Isaac-incompatible — it's that Isaac's cost is proven and its benefit for *this* mission is zero.

---

## Decision 2: Scope — one robot, not a fleet, to start

The long-term vision (multi-sensor fusion, remote/fixed cameras, a "smart" robot guiding less-capable robots) is real but is itself a multi-subsystem project — custom vision model training, sensor fusion, a fleet coordination protocol, onboard inference architecture. Session 15 does not attempt to design or build that. It scopes to one robot with real depth (proper Nav2 + LiDAR + camera), informed by the long-term direction but not blocked on building it.

---

## Decision 3: Mission framework, not a single hardcoded task

The robot needs to run different, switchable missions (e.g. a full-coverage-with-reactions mission, and a simple navigate-photograph-return mission) — this is a general mission executor, not one script. Session 13's agentic loop already built the relevant foundation: `SEMANTIC_MAP`-based multi-waypoint mission planning with named locations. New mission types are expressed as waypoint sequences plus action primitives (e.g. "take a picture"), not as new bespoke programs.

---

## Decision 4: First milestone is "Mission 1" — navigate, photograph, return

**Mission 1:** navigate to the doorway center (from a start position not aligned with it, so real heading-correction navigation is exercised — the same capability already proven by BR-01's corridor/doorway navigation) → take a picture (new action primitive: subscribe to `/robot_001/camera/image_raw`, save/publish one frame) → return to the start position (navigate again).

**Explicitly excluded from this milestone:** no ball-reaction, no coverage planning. Those are Mission 2's job (see Decision 5).

**Why this is the right first HIL milestone:** it exercises real navigation, the mission-framework/action-primitive mechanism, the camera pipeline, and the full HIL loop (Gazebo on the workstation ↔ real Jetson over the network) — everything Session 15 needs to prove — while staying small enough to get solid and reproducible quickly. It deliberately does not bundle in the two capabilities that are themselves substantial new engineering (full-coverage planning, camera-reactive Nav2 integration), so HIL-networking bugs don't get debugged at the same time as coverage-planning bugs or perception-integration bugs.

---

## Decision 5: Deferred to a follow-up — Mission 2 (full coverage + camera-reactive behavior)

Not designed in detail here; captured so the shape is known when that follow-up starts.

- **Full-area coverage sweep.** No coverage planner exists in this project today. Needs either a Nav2 coverage plugin (e.g. `opennav_coverage`) or a hand-rolled boustrophedon/lawnmower waypoint generator once the robot arrives at the target zone.
- **Camera-reactive Nav2 integration (approved approach — "split by behavior type, using Nav2's own mechanisms"):**
  - "Yellow ball → avoid that area": a dynamic costmap layer marks the detected location as lethal/keepout via `nav2_costmap_2d` — the existing planner routes around it natively, no custom cancel/replan logic needed.
  - "Red ball → stop": a lightweight external supervisor node cancels the active Nav2 goal directly via the action client (`cancel_goal_async()`) — stopping is urgent/binary and doesn't need planning.
  - Rejected alternatives: a single external supervisor owning the whole goal lifecycle for both behaviors (more hand-managed state than necessary, when Nav2's costmap mechanism already solves the "avoid" half natively); a custom Nav2 Behavior Tree plugin (most "idiomatic," but this project already hit significant BT complexity pain under Isaac and had to strip down to a minimal one-shot BT to get anything reliable — avoided without a strong reason to reintroduce that risk).
- **Perception re-use policy:** reuse BC's `behavior_controller.py` *algorithm* (HSV thresholding — proven, zero training data) as reference, not the file verbatim. Re-tune thresholds for this project's actual Gazebo camera rendering (different renderer/lighting than BC's Isaac-rendered scene) and re-implement following this project's ROS2 node/topic conventions (`/robot_001/` namespacing, etc.) — consistent with this project's established policy that migrated BC code is reference material, not gospel (repeated pattern of subtle bugs from verbatim reuse: stale coordinates, mismatched schema columns, missing deps).

---

## HIL network topology (carried forward from Session 14's original stretch-goal note, not re-litigated here)

Direct connection between workstation and Jetson — either plain Ethernet or the Jetson's USB-C device-mode link (point-to-point, default `192.168.55.1`) — same `ROS_DOMAIN_ID` on both machines, CycloneDDS unicast peers (`CYCLONEDDS_URI`) as a documented fallback if multicast discovery doesn't traverse the link cleanly. Re-verify once bare-metal prototyping is actually underway.

---

## Success criteria for this session

- Mission 1 runs successfully bare-metal first — Jetson + Gazebo, no CI yet. Matches this project's existing tiered-dev-loop philosophy (cheaper to debug outside CI than inside it).
- Only after that: design (not necessarily implement) the actual CI stage — network orchestration approach (does a GHA job on the x86 GPU runner have a clean way to coordinate the Jetson as a second self-hosted runner mid-job, or does this need to be structured differently, e.g. SSH-driven from one job rather than treating the Jetson as a GHA runner for this stage), and a definition of success/failure/timeout/teardown for a HIL test.
- This Isaac-vs-Gazebo decision and its reasoning recorded in `BLUEPRINT.md`'s decision log (separately from this spec, per this project's existing documentation convention).
- Job renumbering/CI-stage-shape implications (if any) decided — can be implemented in this session or deferred to whenever the CI stage itself is actually built.

---

## Explicitly out of scope for this design

- Multi-robot fleet simulation and its scaling limits (flagged as a future measurement, not resolved here)
- Full-area coverage planning implementation details (Decision 5 captures the shape, not the plan)
- Camera-reactive Nav2 integration implementation details (approach is decided; implementation is Mission 2's follow-up work)
- Isaac ROS/NITROS adoption on the real Jetson (independent decision, not blocked by this design either way)
