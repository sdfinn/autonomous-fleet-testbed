# BLUEPRINT.md — Master Strategic Brief

**This is the working strategic brief for autonomous-fleet-testbed. Read it for direction; execute from `Release1Todo.md`.**

## Document map (what to read, what to build from)

| Document | Role | Build from it? |
|---|---|---|
| **BLUEPRINT.md** (this file) | Master strategic brief — vision, roadmap, career framing, decisions | No — sets direction |
| `robotics_cicd_10x_blueprint.md` | Source strategic dialogue (10x / VC brainstorm) | **No — reference only** |
| `Release1Todo.md` | Session-by-session execution plan | **Yes — tasks come from here** |
| `.superpowers/sdd/` specs | Per-feature design specs | **Yes — code comes from here** |
| `config/drift_config.yaml`, `robot_profiles/*.yaml`, `requirements/traceability.yaml` | Data-driven config | Yes — behavior is data, not code |

We do **not** code directly from either strategy doc. Strategy sets the "why"; session plans and SDD specs set the "what" and "how."

---

## The project in one line

A CI/CD-native, **local-first** testing framework for autonomous robots that brings 20 years of enterprise release discipline to a field full of brilliant ML/hardware engineers who lack it — and layers an **AI agentic test-and-heal loop** plus **automated sim-to-real alignment** on top.

## Two products (independently demoable, mutually reinforcing)

1. **Fleet CI/CD Pipeline Framework** — "How do you know your robot software works before it touches hardware?" Robot-agnostic, open-source-ready. Lives in `tools/` + `.github/workflows/`.
2. **AI Autonomous Mission Planner** — "How do you tell a fleet what to do and prove they can do it?" Scripted in R1, AI-driven later. Lives in `src/nav_fleet/` (+ future `mission_planner/`).

The pipeline validates the planner; the planner generates the scenarios the pipeline tests.

---

## Career context — the actual optimization target

- **Who:** Mike, 66, Principal Test Engineer with 20 years in enterprise automation, test pipelines, CI/CD, and release management (call-center software). Prior Brain Corp context (isaac_project). Building this at home.
- **Goal (80% probability path):** Transition into a Principal / Staff robotics engineering role — AI infrastructure, MLOps, or test/validation at an autonomous mobile robot company. Brain Corp, Locus Robotics, Vecna, Symbotic, Boston Dynamics, Agility Robotics, or similar. The Brain Corp background is a credibility signal — this project uses the same stack (ROS2, Gazebo, GHA, arm64 cross-compile, HIL testing) but local-first, open-source, with an agentic layer added.
- **20% path:** Commercial open-source or founding-architect role (Temporal/Tailscale/Sidero model). The polished OSS artifact is the same deliverable either way.
- **Honest monetization read:** Classic VC rocketship, solo, at 66 → low probability. Not the bet to optimize for.
- The job artifact, the OSS project, and the product seed are **the same deliverable.** No effort split.

## Showcase strategy

**Format:** Each release ships two companion deliverables — a short video of the sim run and a short video of the real robot doing the same mission. Side-by-side, they get more compelling with every release. R1 shows a single nav test closing the loop. The agentic loop iteration makes R2/R4 the memorable demo.

**Distribution:**
- **GitHub:** Public README + video links/embeds. Code stays private (request access to contact).
- **YouTube:** Short (1–2 min) per-release videos, unlisted or public. Linked from README.
- **Code access:** Private repo. Share on request to serious contacts only — forces a conversation.

**Target audience:** Engineering directors and Principal engineers at AMR companies who recognize the stack immediately. The Brian Corp stack (ROS2, Gazebo, GHA, arm64, HIL) plus the agentic layer plus the local-first economics story = a demonstrably rare combination.

---

## The core strategic insight: two axes, optimize the right one

There are two ways to grow this project. They are different axes:

- **Robot ambition ladder** (the original R1→R3B plan): 1 robot → fleet → drone → autonomous missions. Adds *hardware and coordination complexity.*
- **Infrastructure value ladder** (the 10x blueprint): cloud/local orchestration → generative scenarios → hardware-in-the-loop, wrapped in an agentic self-healing loop and local-first economics.

**The differentiator — and the career/product value — lives on the infrastructure axis.** Adding a second robot or a drone does little for a hiring director or investor. Proving an **agentic test-and-heal loop** + **automated sim-to-real alignment** on a *single rover*, on a *$3K workstation*, with *reproducible cost numbers*, is the thing nobody else has packaged. Multi-robot/drone work is a **demo flourish**, not the core value.

Consequence: **the roadmap is reprioritized.** The agentic/alignment layer (R4) is pulled *before* the multi-robot ladder (R2/R3).

---

## Revised roadmap

```
R1  (current)   Finish the 6-stage pipeline in sim, single rover → Showcase Moment 1
                Stage 4 / Isaac Sim = reserved slot, NOT built (see Simulation Tiers)

R4  (NEXT after R1)   The Agentic & Alignment Layer — THE differentiator
                Pillars: agentic test/heal · sim-to-real alignment · generative worlds
                Outputs: local-throughput benchmark · positioning write-up

R2 / R3  (OPTIONAL, demo flourish)   Multi-robot · drone · autonomous missions
                Pulled forward only if a specific role/customer/demo demands it

Stage 4 / Isaac Sim   Fidelity tier — drops into reserved slot when perception matters
```

| Release | Robot composition | Mission style | Intelligence layer | Priority |
|---|---|---|---|---|
| R1 (current) | 1 Jetson Orin Nano (sim + real) | Scripted: navigate, sweep, stop/avoid | Drift detection + AI test generation | **Active** |
| **R4** | Same single rover | Same scripted missions | **Agentic test/heal + sim-to-real alignment + generative worlds** | **Next** |
| R2 | 1 Jetson + 1–2 cheaper robots | Coordinated search | Multi-robot coordination | Optional |
| R3A | Add drone | More autonomous | Aerial + ground coordination | Optional |
| R3B | Any fleet | Fully autonomous ("go find the red ball") | AI-defined missions, parallel sim | Optional |

---

## R4 — The Agentic & Alignment Layer (the differentiator)

**Three pillars:**

1. **Closed-loop agentic test/heal** — on **3 named failure modes** (candidates: nav collision, odom Hz drop, sim-to-real drift breach). Claude detects the invariant violation, diagnoses from telemetry, and **proposes** a fix. **Human-in-the-loop approval.** This is the blueprint's Part 4 loop, scoped honestly.
2. **Automated sim-to-real alignment** (the "monkey") — ingest real rover/Jetson telemetry, auto-tune domain-randomization params so the sim tracks reality. `sim_vs_real_comparison.py` is the seed; the *auto-tuning* is the new work.
3. **Generative scenario → real world** — NL prompt ("dense clutter, low light") → actual Gazebo SDF, not just the JSON scenario descriptions `ai_test_generator.py` produces today.

**Two outputs (these ARE the career assets):**

4. **Local-first benchmark** — "N robot-hours validated, $0 cloud spend, one RTX 5080," reproducible.
5. **Positioning write-up** — "20 years of enterprise release engineering meets physical AI."

**⚠️ Credibility discipline (non-negotiable):** Ship and demo the **human-in-the-loop** version of the agentic loop. *Frame* full unattended autonomy as the roadmap, do not claim it. Full autonomy-until-SLA is research-grade and cherry-pickable; claiming it before it's robust will get caught by exactly the technical buyers we target. **Under-claim, over-deliver.**

---

## The local-first economics wedge

The sharpest, most-unique angle: **enterprise-grade agentic robot CI without a cloud bill.** RTX 5080 (Blackwell, FP4/FP8), 96 GB RAM, Jetson Orin Nano for real HIL. The message: *"Eliminate ballooning cloud R&D costs — bring disciplined agentic automation local, deliver hardware-verified binaries to the edge."* This is a first-class, **measured, marketed** feature — captured by R4 output #4, not an afterthought.

## Simulation tiers: throughput vs. fidelity

Two tiers, complementary — not competitors:

- **Throughput / economics tier → Gazebo Harmonic headless.** Cheap, parallel, "100 robot-hours for $0." Drives the local-first story. Built in R1/R4.
- **Fidelity tier → Isaac Sim (Stage 4).** Photorealistic perception (YOLO mAP) when a customer/role demands it. **Deferred-and-positioned**, not deferred-and-forgotten.

**Isaac Sim decision (2026-06-27):** Deferred from R1 on **priority grounds, not difficulty.** (Mike has run Isaac Sim on Windows + ROS2-on-WSL; bare-metal Ubuntu is doable and faster — setup is not the blocker.) Stage 4 stays a **reserved, designed slot** in the 6-stage pipeline; CI keeps a clean stub/skip so it drops in later with no rework. Offering *both* tiers (developer picks per-PR) is a stronger, "enterprise tiering discipline" story than either alone — exactly the kind of thing the experience card articulates that ML-heavy teams won't.

---

## Showcase moments

1. **Moment 1 (R1):** Single rover in sim + real doing the same mission; drift detection visible. 1–2 min video.
2. **Moment "R4" (the real differentiator):** Agentic loop catches an injected regression, diagnoses it from telemetry, proposes a fix (human approves), sim-to-real alignment shown tracking; plus the local-first benchmark number on screen. **This is the demo that lands the role / opens the pitch.**
3. **Moment 2 (R2, optional):** 1 smart + 1–2 cheap robots, coordinated mission.
4. **Moment 3A/3B (R3, optional):** Drone added / "brains demo" — pipeline defines and runs its own test missions.

## Tiered development loop

**Rule: flush bugs on the fastest tier before moving to the next.** Most bugs are platform-agnostic — a broken nav goal, wrong topic namespace, bad metric collection — they show up equally on x86. No reason to wait 23 minutes per iteration to find them. Only arm64-specific issues (compiled dependency differences, Jetson driver behavior, memory alignment) actually require Tier 2+.

| Tier | Platform | `colcon build` | Full cycle (build → sim → nav test) | Purpose |
|---|---|---|---|---|
| **1 — primary dev loop** | x86 bare metal + Gazebo local | **~1s** | ~3–10 min | Flush common bugs fast |
| 2 — arm64 compat check | GHA ubuntu-latest QEMU | 23m43s (Docker build+push, cold) | +sim stub | Validate arm64 cross-compile |
| 3 — target platform | Jetson native arm64 (Phase B) | 4.76s (bare `colcon build`) / 9m45s (Docker build+push, non-cached) | +real hw | Validate actual deploy target |
| 4 — full HIL | Real rover + Jetson (Phase C) | SSH deploy | full loop | Final validation |

> Tier 2/3's `colcon build` column really means "build-stage wall time" — for Tier 2/3 that's
> the whole Docker image build+push (`stage-3-arm64`), not the bare `colcon build` command,
> which is a separate, much faster number on native hardware (Tier 3: 4.76s, in line with
> Tier 1). Both Tier 3 numbers measured 2026-07-10 on the real Jetson Orin Nano Super,
> microSD, JetPack 7.2 — see `docs/runbooks/JetsonInstallSession14.md` Part 7/8 for the full runs.

**Tier 1 full cycle** (once Gazebo is wired in Session 09):
```
colcon build (1s) → gz sim headless → nav2 → nav_runner → metrics_collector → drift check → repeat
```
This is the loop that finds 90% of bugs. Commit to CI only when the x86 pipeline is clean.

## Architecture framing (vocabulary that resonates with AMR companies)

This project implements the same architectural patterns used in production AMR systems.
Using the correct vocabulary makes the work immediately legible to hiring directors in this space:

| What we build | Enterprise term | Where it lives |
|---|---|---|
| Nav2 AMCL + costmaps + behavior tree | **Probabilistic AI layer** | `src/nav_fleet/`, `nav2_params.yaml` |
| Scan min-range assertion + collision check | **Deterministic safety layer** | `tests/test_navigation.py` |
| Session 17 SLAM map build (drive once, auto after) | **Teach Run / Teach-and-Repeat** | `maps/bedroom_real.*` |
| Jetson + UGV-PT testing (Sessions 14–15) | **Hardware-in-the-Loop (HIL)** | Stage 6 CI |
| Stage 6 SSH deploy + smoke test + rollback | **OTA update pipeline** | `.github/workflows/ci.yml` |
| `telemetry_logger.py` + `baseline_monitor.py` | **Networked fleet learning loop** (1-robot scale) | `tools/` |
| Session 13 agentic loop with SEMANTIC_MAP | **VLA-lite semantic mission planning** | `tools/agentic_loop.py` |

The dual-layer safety split (probabilistic AI + deterministic safety) is the pattern
Brain Corp uses in BrainOS®. Our Nav2 layer IS the probabilistic layer; our `collision_detected`
assertion IS the deterministic layer. Name it that way in the README and write-ups.

### Nav2 plugin stack (as of Session 10)

| Role | Plugin | Notes |
|---|---|---|
| Localization motion model | `nav2_amcl::DifferentialMotionModel` | Non-holonomic; noise tuned via alpha1–5 |
| Laser model | likelihood field (AMCL built-in) | Beam endpoint vs. nearest map obstacle |
| Global planner | `nav2_smac_planner::SmacPlanner2D` | Equal diagonal/cardinal cost → true NNE paths |
| Path follower | `nav2_regulated_pure_pursuit_controller::RegulatedPurePursuitController` | `use_collision_detection:false`, `rotate_to_heading_min_angle:0.3` |
| BT navigator | `nav2_bt_navigator::NavigateToPoseNavigator` | Default Nav2 behavior tree |
| Progress checker | `nav2_controller::SimpleProgressChecker` | 0.1m in 60s or abort |
| Goal checker | `nav2_controller::SimpleGoalChecker` | xy_tolerance 0.15m, yaw_tolerance 0.5 rad |
| Global costmap layers | `StaticLayer` → `ObstacleLayer` → `InflationLayer` | inflation_radius 0.30m |
| Local costmap layers | `ObstacleLayer` → `InflationLayer` | inflation_radius 0.25m, rolling 4×4m window |

Config lives in `src/nav_fleet/config/nav2_params.yaml`.

### Simulation platform compatibility matrix

Verified before Session 11 install. Isaac Sim runs on the x86 dev machine only — not on Jetson.
JetPack is the compatibility target for Stage 6 real-robot deploy, not for running Isaac Sim.

| Requirement | Isaac Sim 6.0.1.0 spec | x86 dev machine | JetPack 7.2 (Orin Nano) | Status |
|---|---|---|---|---|
| Isaac Sim version | 6.0.1.0 | 6.0.1.0 (pip, pypi.nvidia.com) | n/a — sim runs on x86 | ✅ |
| Ubuntu | 24.04 (primary target) | 24.04 bare metal | 24.04 (L4T 39.2) | ✅ |
| Python | 3.12 (cp312 wheels) | 3.12.3 | 3.12 | ✅ |
| ROS2 distro | Jazzy (native on 24.04) | Jazzy | Jazzy | ✅ |
| CUDA | 12.x+ | 13.2 | 13.2 | ✅ |
| GPU driver | 570+ | 595.71.05 (RTX 5080) | n/a (Jetson integrated) | ✅ |
| GLIBC | 2.34+ (manylinux_2_34) | 2.39 | 2.39 | ✅ |
| ROS2 bridge | Jazzy auto-loaded on 24.04 | sourced from `/opt/ros/jazzy` | sourced from `/opt/ros/jazzy` | ✅ |

> **Note:** Isaac Sim 5.x was never published to pypi.nvidia.com; 6.0.x is the first pip-installable
> release. Isaac Sim 5.x + Jazzy had known Python 3.11/3.12 mismatch bugs. 6.0.x resolves this.
> RTX 5080 (Blackwell) not explicitly listed in NVIDIA's tested GPU matrix but driver requirement met.

---

## Design principles (preserve across all releases)

- **Data-driven:** thresholds, requirements, profiles in YAML — never hardcoded in Python.
- **Robot-agnostic:** tools know nothing about specific robots; profiles declare capabilities.
- **Shift left:** catch bugs in sim before hardware; generate scenarios to find more bugs sooner.
- **Pipeline as product:** the CI/CD pipeline IS the deliverable, not just a quality gate.
- **Under-claim, over-deliver:** especially on agentic autonomy.
- **Tier 1 first:** develop and debug on x86 bare metal Gazebo; go to arm64 only to validate compatibility, not to find common bugs.

---

## What's Next — Release 3 and Beyond

These ideas are captured here to prevent scope creep in R1 and the agentic layer work.
Pull forward only when a specific role, customer, or demo demands it.

**Infrastructure / platform:**
- **MQTT telemetry** — replace JSON file polling with MQTT pub/sub for real-time edge-to-cloud telemetry (matches the IoT protocol pattern used by production AMR fleets)
- **RaaS framing doc** — document the framework as a Robotics-as-a-Service offering: hardware lease + software subscription, OTA updates included
- **Safety certification framing** — annotate the dual-layer architecture against SIL2 / UL 60730-1 requirements (not certification, just the mapping)
- **Dynamic SLAM** — handle moving obstacles (people, forklifts) using a costmap layer that ages out dynamic detections
- **CI stage ordering — considered, not decided (2026-07-06).** `stage-2-arm64` and
  `stage-3-gazebo` currently run in parallel (both just `needs: stage-1-quality`) — fast
  signal on the sim stages, but it burns the full QEMU build (24–37 min) even when
  Gazebo/Isaac are already known-red. Discussed making Stage 2 sequential, gated behind
  Stage 3/4 passing, to stop wasting that compute on already-failing runs. Tradeoff: costs
  ~150s on the success path (no more free overlap) to save the full QEMU build on failure.
  Mostly stops mattering once Session 14 makes Stage 2 native (~3–5 min projected) — revisit
  then, or sooner if QEMU minutes/cost become a real pain point before that.
- **Structural CI-stage-timing telemetry** — `stage_timings_sec` already exists as a column
  in the `runs` schema (`tools/telemetry_logger.py`) but nothing populates it. CI stage
  durations (QEMU vs. native arm64 build, per-stage wall time) are currently hand-copied into
  this decisions log as prose instead. Wiring real stage timings into that column would let
  the dashboard show the trend over time rather than one-off notes.

**AI / intelligence:**
- **Full VLA models** — replace LLM mission planning with Vision-Language-Action models for visually grounded semantic navigation ("go to the area with the green box")
- **SelfPath-style auto-route generation** — autonomous route planning without human-defined waypoints; robot generates its own coverage path
- **Closed-loop sim-to-real auto-tuning** — automatically adjust URDF/nav2 params to minimize the sim-to-real gap based on telemetry comparison

**Robot / fleet expansion:**
- **Multi-robot fleet (R2)** — 2+ robots, coordinated missions, inter-robot collision avoidance. If the Jetson takes a **leader-node role** (central telemetry hub, fleet DB on-robot): NVMe becomes mandatory (sustained-write duty kills SD cards — see 2026-07-03 decision), workers send compact telemetry only (never raw video/lidar streams over Wi-Fi — bandwidth and leader memory both cap out fast), and DDS traffic needs scoping (CycloneDDS config or Zenoh) so sensor topics stay local to each robot
- **Drone integration (R3A)** — aerial + ground coordination, combined sensing
- **Fully autonomous missions (R3B)** — AI defines and runs its own test missions with no scripted waypoints

**Demo / portfolio:**
- **Per-release video series** — YouTube shorts showing sim + real robot doing the same mission; compile into a progression reel for R3

---

### Background: Traditional Architectures vs. VLA Models

Traditional robotic software relies on a modular, hand-coded pipeline — separate components acting like train cars, each passing data to the next. VLA models replace the entire chain with a single unified neural network that behaves like one brain processing vision, language, and motor output simultaneously.

| Feature | Traditional Architecture | VLA Model Architecture |
|---|---|---|
| **Data processing** | Separates perception (camera), localization (SLAM), and motion planning into distinct modules | Merges vision, text instructions, and motor controls into a single framework |
| **Adaptability** | Low — requires explicit reprogramming if an object changes shape or location | High — generalizes to new objects and environments via prior training |
| **Logic layer** | Rigid — runs on geometric maps and exact numeric coordinates | Intuitive — uses probabilistic, semantic associations to predict next actions |
| **Failure mode** | Cascading — if perception misidentifies an object, the entire pipeline breaks | Hallucination — may misunderstand a physical constraint or environmental context |

Our Session 13 agentic loop is **VLA-lite**: Claude handles the language → action translation while Nav2 handles the deterministic execution. The SEMANTIC_MAP bridges the two — named locations give Claude spatial grounding without requiring a full neural perception stack. Full VLA integration (where the model directly generates motor commands from camera + language) is the R3 destination.

### Background: Semantic Mapping in Dynamic Environments

Traditional robots see a busy public space (retail store, airport, warehouse) as a fluctuating cloud of obstacles. They avoid collisions but do not understand what they are avoiding. Semantic mapping overlays meaning onto geometry:

- **Contextual tracking:** Instead of labeling a moving mass as "unidentified dynamic barrier," a semantically grounded robot classifies it as "shopper with shopping cart" and predicts it will continue moving forward — whereas a cardboard display will not.
- **Affordance awareness:** The robot links objects to their function. A wet floor requires a reroute; a dropped piece of soft packaging can be rolled over. These distinctions require semantic labels, not just geometry.
- **Mitigating VLA weaknesses:** VLA models are stochastic — their outputs can be unpredictable. Embedding a fixed semantic 3D world model gives the robot a reliable safety framework to double-check the VLA's decisions against the physical reality of the environment. This is the same dual-layer principle (probabilistic AI + deterministic safety) used in BrainOS®.

Our current SEMANTIC_MAP in `agentic_loop.py` is a static lookup table — a first step. The R3 version upgrades this to a live semantic costmap updated by camera detections.

---

## Decisions log

- **2026-06-27 — Roadmap reprioritized.** R4 (Agentic & Alignment Layer) pulled *before* R2/R3. Rationale: the differentiator and all career/product value live on the infrastructure axis, not the robot-ambition axis. R2/R3 become optional demo flourishes.
- **2026-06-27 — Isaac Sim / Stage 4 deferred-and-positioned.** Reserved slot in the 6-stage pipeline; reframed as the "fidelity tier" alongside Gazebo's "throughput tier." Deferred on priority, not difficulty. Affects `Release1Todo.md` session 12 only.
- **2026-06-27 — Agentic loop scoped to human-in-the-loop for portfolio/demo.** Full unattended autonomy is roadmap, not a claim.
- **2026-06-27 — BLUEPRINT.md created** as the master brief; `robotics_cicd_10x_blueprint.md` retained as reference-only source dialogue. CLAUDE.md pointer corrected.
- **2026-06-28 — Stage 2 arm64 QEMU baseline recorded** (Session 08). Both local and GHA builds green after fixing two issues: (1) `contents: read` missing from GHA job permissions block — adding `packages: write` alone revokes all other defaults including checkout access; (2) `pluggy` uninstall conflict — `ros:jazzy-ros-base` installs pytest/pluggy via apt with no pip RECORD file; fixed with `--ignore-installed`. Timings:
  - **x86 bare metal `colcon build` (nav_fleet Python package):** ~1s — the Tier 1 dev loop baseline
  - **GHA ubuntu-latest (QEMU, cold build):** 23m43s — authoritative Phase B comparison baseline
  - **Local RTX 5080 workstation (QEMU, pip+colcon only — apt layers cached from failed first attempt):** 37m23s — full uncached local ~60+ min
  - **Phase B Jetson native arm64 runner:** measured 2026-07-10, Session 14 (originally
    projected 3–5 min, actual came in higher — see below). Two numbers, not one, because they
    measure different things: bare `colcon build` on the Jetson's own OS is **4.76s** (in line
    with Tier 1's ~1s, just slower hardware — this is the number that matters for local
    dev-loop iteration on the robot). The actual CI comparison — `stage-2-arm64`'s Docker
    build+push, now running natively on the Jetson as a self-hosted runner instead of QEMU —
    is **9m45s (585s) non-cached** (a first measurement hit GHA's build cache and read a
    misleadingly fast 15s; re-measured after deliberately invalidating the cache via
    `requirements-ci.txt` to get a real number). vs. the 23m43s–24m31s QEMU baseline, that's
    **~2.4x faster** — a real, credible win, just far short of the original 3–5 min guess.
    Two likely reasons the estimate undershot: (1) still on microSD (Part 9's NVMe migration
    hasn't happened — sustained small-file I/O during `pip install`/layer extraction is
    exactly where microSD is weakest); (2) the 3–5 min guess implicitly assumed eliminating
    QEMU's emulation tax alone would get most of the way there, but a meaningful chunk of the
    23-minute baseline is genuinely CPU/IO-bound work (pip installs of pandas/numpy/scipy/etc.,
    `colcon build`) that doesn't disappear just because emulation does. Full run details:
    `docs/runbooks/JetsonInstallSession14.md` Part 8.2 (PR #1, then a follow-up direct push to `main` for
    the non-cached remeasurement).
  - Decision: develop and debug on Tier 1 (x86 bare metal Gazebo, ~1s build, ~3–10 min full cycle) before committing to CI. x86 is not the target OS but finds 90% of bugs at 23× less wait time per iteration.
- **2026-06-29 — Showcase strategy locked.** Video-first portfolio (sim + real robot, one per release). Code stays private; README + YouTube videos public; code on request only. Primary audience: AMR companies (Brain Corp-adjacent). Brain Corp architectural vocabulary added to BLUEPRINT.md. Session plan (10–16) fully expanded with code snippets. SEMANTIC_MAP added to Session 13 agentic loop for named-location mission planning. "What's Next (R3+)" section added to capture deferred ideas.
- **2026-07-02 — Isaac nav debugging: BR-01 passing green (Session 11/12).** Goal:
  `tests/test_navigation.py::test_navigation_succeeds` passing against Isaac Sim (GUI mode) —
  **achieved**, after the four early fixes below plus a much larger pivot once they weren't
  enough on their own:
  1. **Scan timestamps (GUI):** `get_current_time()` reads stale app thread in GUI mode. Fix: rclpy clock gated on `nanoseconds > 0`.
  2. **cmd_vel delivery:** `spin_once(timeout_sec=0)` with CycloneDDS returns immediately, missing async messages. Fix: background `SingleThreadedExecutor` daemon thread.
  3. **PhysX wheel drives:** URDF importer creates `damping=0` drives; `set_joint_velocity_targets()` silently ignored. Fix: programmatically set `damping=100` via `UsdPhysics.DriveAPI` after `robot.initialize()`.
  4. **Global costmap "Start occupied":** Live scan data in global obstacle_layer marks replan start cell as occupied when robot is adjacent to furniture. Fix: removed `obstacle_layer` from `global_costmap.plugins` (static map + inflation only).

  Those four weren't sufficient — ~15 more iterations chasing a circular-footprint-vs-doorway
  tradeoff, `SmacPlannerHybrid`, a broken `behavior_server` recovery path, and an AMCL false
  positive (`Goal succeeded` reported while the robot was actually stuck spinning against the
  Dresser — extended in-place rotation next to a large close surface is a classic scan-matching
  divergence trigger). Root cause of the divergence class of problems: layering AMCL +
  `SmacPlannerHybrid` + `collision_monitor` + recovery behaviors on all at once with no working
  baseline underneath made it impossible to tell a real bug apart from a tuning problem apart
  from a false positive. Found `BC/isaac_project` (same room, a Jetbot, already proven working)
  and matched its minimal architecture instead: `NavfnPlanner` + plain `robot_radius`, a
  one-shot BT (`navigate_simple.xml`, no periodic replanning, no recovery dependency), and a
  static `map→odom` TF instead of AMCL. Full writeup, deferred capability (AMCL hardening,
  recovery, accurate footprint planning, multi-robot launch parameterization), and two hard-won
  ROS2/Nav2 launch gotchas are in `Release1Todo.md` Session 17+ and `CLAUDE.md`.
  **Process note:** DDS TRANSIENT_LOCAL caches Isaac's full TF history — must kill Isaac AND Nav2 together between runs. Start Nav2 within ~5s of Isaac ready. See CLAUDE.md "Isaac GUI Nav Test — Terminal Procedure".
- **2026-07-03 — First fully green, hands-off CI run of the Isaac nav test (Session 11/12).**
  `stage-4-isaac` rewritten from a sensor-rate smoke test to the real BR-01/02/10 headless
  navigation test (verified manually twice first — clean pass both times, no headless-specific
  bugs). Along the way, fixed two unrelated pre-existing CI blockers that had silently been
  failing every push since ~July 1 (`requirements/traceability.yaml` referencing test names
  that didn't match Session 10's actual implementation; `test_navigation.py` never added to
  `stage-1-quality`'s `--ignore` list, so it failed `import rclpy` on the bare hosted runner).
  Also decoupled `stage-3-gazebo` from `stage-2-arm64` (they don't share a runner or an
  artifact, so there was no reason for the sim tests to wait ~20+ min on an emulated arm64
  build that hasn't caught a genuinely architecture-specific bug since Session 08 setup — see
  `stage-2-arm64`'s job comment in `ci.yml`). Full green run, all timings from the same CI run
  (`gh run 28630844951`):
  - **Stage 2 arm64 (QEMU, cold build):** 24m31s — consistent with the Session 08 baseline (~23m43s), now running in parallel instead of gating the sim stages
  - **Stage 3 Gazebo (headless, cold sim/Nav2 start → all 3 tests passing):** 52s
  - **Stage 4 Isaac Sim (headless, cold sim/Nav2 start → all 3 tests passing):** 100s — ~2x Gazebo, but manual testing showed the actual navigation portion is comparably fast (~13–28s) once both are already running; the gap is Isaac's own startup overhead (extension loading, URDF import), not slower navigation
  - Both stage-3/stage-4 timers start after `colcon build`, so they're apples-to-apples with each other (not full job time from checkout)
  - This is the baseline Session 14/16 will compare real Jetson Orin Nano hardware timing against — not a sim-engine-vs-real-hardware comparison on the same platform, since Isaac Sim itself doesn't run on Jetson's embedded GPU at all (see Release1Todo.md Session 17+)
- **2026-07-03 — Session 12 pre-flight review: SQLite is the single telemetry store.** The session text described a JSON-file-per-run architecture (`reports/history/<run_id>.json`), but all five migrated tools (telemetry_logger, generate_test_report, baseline_monitor, validate_telemetry, dashboard) were already built on SQLite (`reports/fleet_runs.db` via `FLEET_DB`) and nothing read `reports/history/` at all. Decisions: (1) SQLite stays — JSON-per-run dropped; (2) add a `sim_engine` column (gazebo/isaac/real) via the logger's `_ensure_run_columns()` migration; (3) the telemetry hook (`test_navigation.py` → `log_run()`) is the session's real deliverable — it didn't exist, so no run data did either; (4) new CI job is `stage-5-reports` on the self-hosted runner with `FLEET_DB` at a persistent path outside the job workspace (`~/fleet-ci-data/`) so drift detection accumulates cross-run history — a hosted runner would PDF an empty database. Session 12/15 text and CLAUDE.md corrected to match.
- **2026-07-03 — Jetson deployment decisions (pre-Session 14 review).** Five decisions from the untethered/storage/container discussion:
  1. **Storage: MicroSD first, NVMe later — both measured within Session 14 (moved up from Session 17+ on 2026-07-06).** Flash R1 to SD (dev kit default boot), record a baseline (apt/ROS2 install, `colcon build`, `docker pull` times), then swap to NVMe and re-record the same numbers before the module ever leaves the dev kit for the robot chassis — storage swaps are strictly easier on a bare dev kit than after Session 16 wires it into anything. Publish the before/after table — the second "measured, marketed" number after QEMU→native. No architecture work needed: nothing in the repo depends on the storage medium, so the swap is a reflash, not a redesign. SD hygiene until the swap: no rosbags/heavy logging to the card.
  2. **Bare metal + container hybrid on the Jetson.** Native bare-metal build stays the Session 14 runner path (simplest, and it produces the QEMU→native speedup headline). The stage-2 arm64 image is repurposed, not retired: pulled on the Jetson with the unit tests run inside it — the *exact CI artifact* proven on target silicon, making "deliver hardware-verified binaries to the edge" literal rather than aspirational. The whole chain is one distro — x86 workstation, stage-2 image (`ros:jazzy-ros-base`), and Jetson (JetPack 7.2 = L4T 39.2 = Ubuntu 24.04) are all 24.04/Jazzy; no Humble anywhere. Container as robot *runtime* therefore buys env pinning/rollback, not distro compatibility: bare metal runtime is the R1 default, container runtime is an R2+ option (pairs with the RaaS/OTA framing).
  3. **Git-sync over SSH is the deployment mechanism.** Stage 6's CI job already implements it (`git pull` + `colcon build` via SSH). Ansible rejected as YAGNI for a one-robot fleet.
  4. **systemd autostart ("going untethered") deferred to Session 17+.** r1-complete works entirely over SSH; boot-to-nav is captured as a concrete Session 17+ block (units, ordering, non-interactive-shell gotcha, headless power-cycle acceptance test).
  5. **Plan gap found and closed: the hardware driver layer.** No session provided `/robot_001/cmd_vel`→wheels, wheel odometry, or `/scan` on real hardware — Session 16 assumed the topics existed. Added as Session 16's first step: evaluate Waveshare's `ugv_ws` ROS2 workspace before writing a thin driver node. Also removed Session 14's stale JetPack 6.x/Humble note (predates JetPack 7.x Orin Nano support) — the plan commits to JetPack 7.2/Jazzy; flash-day sanity check only.
- **2026-07-01 — Session 11 complete (Stage 4 — Isaac Sim bare metal, ROS2 bridge + scan working).** Isaac Sim 6.0.1.0 installed via pip (~20 GB). Key findings:
  - **RTX lidar (RTX render product) does not work headless.** `IsaacSensorCreateRtxLidar` creates an `OmniLidar` prim, but no sensor-specific render product is created in headless mode — only the generic `/Render/OmniverseKit/HydraTextures/Replicator` product exists. `ROS2RtxLidarHelper` OmniGraph node can't produce scan data from it.
  - **Solution: `RotatingLidarPhysX`** (PhysX raycasting, `isaacsim.sensors.physx`). Works natively headless, no render product needed. Frame key is `'linear_depth'`. Published via rclpy `sensor_msgs/LaserScan` in the simulation loop.
  - **Odom via OmniGraph** (`IsaacComputeOdometry → ROS2PublishOdometry + ROS2PublishRawTransformTree`) works unchanged from 4.x pattern — same node names still valid in 6.0.
  - **Prim layout after URDF import:** Geometry sub-prim injected: `/ugv_pt/Geometry/base_footprint/...`. Always traverse stage to discover paths.
  - **Bare-metal timing (x86, RTX 5080):** First launch shader compile: ~10 s (RTX 5080 — far faster than expected). Subsequent launch to ROS2 topic visible: ~7 s. 600-step robot script (odom + scan): ~60 s wall time.
  - **Measured Hz:** `/robot_001/odom` ~96 Hz, `/robot_001/scan` ~22 Hz.
  - **CI job `stage-4-isaac` added** — runs after `stage-3-gazebo`, checks odom ≥ 50 Hz and scan ≥ 5 Hz.
- **2026-06-29 — Session numbering cleaned up.** Stage/Phase/R4 labels dropped from session headings — session numbers only. Isaac Sim pulled forward to Session 11 (previously deferred). Timing records integrated into each session rather than a standalone session.
- **2026-07-01 — Session 10 complete (Stage 3 — first passing nav test).** All three navigation tests pass locally (BR-01, BR-02, BR-10). Root cause of multi-session "robot won't turn" debug: the Gazebo diff-drive plugin was only driving the rear two wheels; passive front wheels resisted in-place rotation via lateral friction, and odom (computed from driven-wheel joint positions only) falsely reported rotation. Fix: add all 4 wheel joints to the diff-drive plugin. Key decisions:
  - **Planner changed to SMAC 2D** (`nav2_smac_planner::SmacPlanner2D`): NavFn A* penalises diagonal moves (cost √2), routing north-first and giving RPP near-zero heading error. SMAC treats all 8 directions equally → diagonal NNE path → 27° heading error → rotate-to-heading triggers.
  - **RPP params locked:** `use_collision_detection: false` (prevents premature abort on corridor approach), `rotate_to_heading_min_angle: 0.3` (17° — fires on SMAC's ~27° initial heading error).
  - **Green sphere** at (0.0, 3.7) — bedroom floor centre, visually marks the nav goal. Kept below lidar scan plane (z=0.038m, lidar at z=0.225m) so Nav2 never sees it as an obstacle.
  - **Camera visual/collision geometry removed** from URDF: GPU lidar uses visual geometry for ray-casting, so any camera visual appears as a self-return inside the footprint and collision_monitor zeroes cmd_vel.
  - **Spawn:** (−1.276, 1.2) — outer hallway doorway arch, facing north. AMCL initial_pose matches.
  - **Bare-metal timing (x86, RTX 5080):** Nav2 startup ~90s wall, navigation run ~45s wall (Gazebo ~3× RTF → ~135s sim). Total `pytest tests/test_navigation.py` wall time: ~3–4 min including Nav2 startup.
  - **URDF note corrected:** Session 09 BLUEPRINT entry said "2 rear driven + 2 front passive". All 4 are now driven — front joints are no longer passive.
- **2026-06-28 — Session 09 complete (Stage 3 Part 1).** ugv_pt robot spawned in Gazebo Harmonic bedroom world with `/robot_001/odom` at 50 Hz and `/robot_001/scan` at 10 Hz. Key design decisions:
  - **World geometry** reused from `BC/isaac_project/scripts/generate_map.py` OBSTACLES (real measured bedroom, same XY coordinates) so the pre-built Nav2 map (`maps/living_room.pgm`, 0.05 m/px) matches the Gazebo world — no SLAM needed for Session 10.
  - **URDF**: 4-wheel layout (2 rear driven by `gz-sim-diff-drive-system` + 2 front passive fixed joints). Diff-drive is an approximation of the real robot's 4WD skid-steer (ESP32 sub-controller). Acceptable for Nav2; evaluate in Session 16 sim-to-real delta.
  - **OGRE2 materials**: `<diffuse>` required alongside `<ambient>` in SDF for visible colours — ambient-only renders black under directional light.
  - **Launch path resolution**: `pathlib.Path(__file__).parent.parent` instead of `get_package_share_directory()` because `colcon-ament-python` is not installed on this system (AMENT_PREFIX_PATH not populated for Python packages).
  - **Robot fidelity gaps carried to Session 10**: IMU (200 Hz, required for Nav2 EKF), OAK-D Lite depth camera (`/robot_001/camera/depth/points`), actual physical dimensions from Waveshare spec sheet, `base_footprint` root link for KDL warning.
- **2026-07-06 — Session 12 complete: telemetry wired end-to-end.** `test_navigation.py`
  now logs one real `runs` row per pytest session (nav result, position error,
  time-to-goal, steps, collision, odom/lidar/camera Hz), verified against live Gazebo.
  `log_run()` extended with optional kwargs for all rate metrics (it only took
  scenario/steps/final_x/final_y/result/step_log before) plus a new `robot_id` column —
  distinct from `robot_type` (the model/profile) — added ahead of the next project's
  multi-robot fleet tracking ask, so the schema doesn't need a later migration; nothing
  built on top of it yet. `generate_test_report.py`, `dashboard/app.py` (5 tabs, checked
  via Playwright), `validate_telemetry.py`, and `baseline_monitor.py` all verified against
  real data for the first time. Found and fixed three more instances of stale
  `isaac_project` cruft surfacing only once real data flowed through: two separate
  "goal zone" plot rectangles using the old living-room coordinates instead of this
  project's bedroom goal; a hard dashboard traceback from `num_frames`/
  `detections_per_frame_avg`/`class_distribution` — YOLO object-detection columns never
  part of this project's schema; and a missing `plotly` dependency (imported by the
  dashboard, never installed or pinned). `stage-5-reports` wired on the self-hosted
  runner and pushed; CI run in progress at time of writing.
- **2026-07-06 — Session 13 pre-flight review: same JSON-vs-SQLite staleness as
  Session 12, plus a stale semantic map.** `load_latest_run()` still assumed the dropped
  `reports/history/*.json` architecture, and the diagnosis prompt hardcoded absolute
  drift thresholds that duplicate what `baseline_monitor.py` (Session 12) now does for
  real with a rolling baseline + sigma comparison. Rewritten to query `FLEET_DB` directly
  and to feed Claude `baseline_monitor.check_run()`'s actual flagged/sigma output instead.
  Also found `SEMANTIC_MAP` (added 2026-06-29, before `bedroom_simple.sdf` existed) was a
  generic 4-direction placeholder (`north_corridor`, `east_zone`, ...) that doesn't match
  this project's real topology — one hallway into a single bedroom, not a symmetric grid.
  Replaced with named locations tied to actual model poses in the SDF (`home_base`,
  `bedroom_goal`, `dresser`, `desk`, `pc_tower`, `bed`). Model string updated
  `claude-sonnet-4-6` → `claude-sonnet-5` (`tools/ai_test_generator.py` has the same stale
  string; not touched here since Session 13 doesn't modify that file).
- **2026-07-06 — NVMe SSD comparison moved from Session 17+ into Session 14.** Rationale:
  swapping storage is strictly easier on a bare dev kit sitting on a desk than after
  Session 16 transfers the module into the robot chassis — no reason to wait. Session 14
  now records the same three numbers (apt/ROS2 install, `colcon build`, `docker pull`) on
  both MicroSD and NVMe and publishes the before/after table itself, rather than only
  recording an SD baseline and deferring the NVMe side. Decided during a discussion of CI
  runner hygiene for the upcoming native-arm64 tier: persistent runner (matches the
  existing x86 self-hosted runner model), occasional deliberate re-flash to catch drift —
  not a re-flash-per-CI-run policy, which isn't practical anyway (SDK Manager flashing is
  a manual, tethered, recovery-mode process, not something a webhook can trigger).
- **2026-07-06 — Session 13 complete: agentic test/heal loop working end-to-end against
  the live Claude API.** `tools/agentic_loop.py` reads the latest run + real drift report
  (`baseline_monitor.check_run()`, not hardcoded thresholds) and proposes one of three
  actions via tool use, human approval required. Verified live, not just reviewed: a
  healthy run correctly reported insufficient baseline history and proposed a real
  multi-waypoint mission using actual `SEMANTIC_MAP` locations; an injected failure
  (scratch DB) flagged `mean_position_error` at sigma=76.6 and correctly proposed reducing
  `inflation_radius` after ruling out collision/sensor causes first. `generate_world_variant`
  was verified directly (`gz sdf -k` confirmed valid output) rather than via repeated LLM
  re-rolls, since Claude consistently and reasonably preferred the mission-plan tool given
  how little run history exists so far. Found and fixed two bugs in the reviewed plan's own
  code: a broken separator string in `human_approval()`, and `python tools/agentic_loop.py`
  failing outright (`ModuleNotFoundError`) since the plain-script form doesn't put the repo
  root on `sys.path` — must use `python -m tools.agentic_loop`. Also discovered and worked
  around: Ubuntu's default `.bashrc` skips the whole file for non-interactive shells, so an
  `ANTHROPIC_API_KEY` export added there never reached this tool's non-interactive Bash
  sessions even after `source ~/.bashrc` — see CLAUDE.md gotcha.
  **Known limitation found post-verification:** the injected-failure test's proposal
  claimed `"current_value": "0.55"` for `local_costmap.inflation_layer.inflation_radius` —
  the real value in `nav2_params.yaml` is 0.25 (confirmed directly). `diagnose()`'s prompt
  never includes the actual params file, so Claude infers a plausible-sounding
  `current_value` from general Nav2 knowledge rather than reading ground truth. Only
  `proposed_value` + rationale should inform a human's decision; `current_value` in any
  proposal isn't trustworthy as-is. Feeding the real `nav2_params.yaml` into the prompt
  would fix this — not done in Session 13, worth a follow-up before this tool is trusted
  for anything beyond a human-reviewed suggestion.
- **2026-07-08 — Session 14 in progress: hardware flash + network verified, paused before
  ROS2 install.** Real Jetson Orin Nano Super hardware (not simulated) flashed with JetPack
  7.2 via SDK Manager over USB-C recovery mode — `lsusb` confirmed `0955:7523 APX` before
  flashing, `/etc/nv_tegra_release` confirmed `R39 REVISION: 2.0` (= L4T r39.2 = JetPack 7.2)
  after. Direct-Ethernet + NetworkManager-shared networking (Part 4) came up clean: SSH
  reachable at `10.42.0.217`, internet confirmed via `curl`/HTTP (plain ICMP `ping nvidia.com`
  was a false negative — that network silently drops outbound ICMP; NAT/MASQUERADE itself was
  verified healthy via `iptables -t nat -L POSTROUTING -v` packet counters). Full Part 5 smoke
  test passed: rootfs correctly on `mmcblk0p1` (microSD, as planned), 97G free, power mode set
  to max (`nvpmodel -m 0`), thermals nominal. Two flash-time choices to revisit later, not
  blockers: SDK Manager's pre-config screen only asked for username/password this run (not
  hostname, still `localhost.localdomain` — fix with `hostnamectl set-hostname` whenever
  convenient), and Target Components (CUDA/cuDNN/TensorRT) were intentionally skipped for a
  clean OS-only first flash (add later with `sudo apt install nvidia-jetpack` once on-device
  inference for navigation is actually needed — L4T apt sources are already present, no
  re-flash required). **Session paused here — resume at `docs/runbooks/JetsonInstallSession14.md` Part 6**
  (ROS2 Jazzy install); Parts 7–10 (native build baseline, CI runner, NVMe migration, closeout)
  not yet attempted.
- **2026-07-10 — Docker on the Jetson scoped to Stage 2 only; everything else native.**
  Decision: the Jetson runs Docker exclusively for CI's `stage-2-arm64` reproducibility gate
  (build + push the arm64 image to GHCR, replacing the QEMU-emulated build once Part 8 makes
  it a self-hosted runner). Every other Jetson-side activity — dev-loop iteration, the
  optional "Jetson-in-the-loop-with-sim" stretch goal (native ROS2 nodes on the Jetson talking
  to Gazebo/Nav2 on the workstation, camera + colored-blob detection triggering sim events) —
  runs native, no container. Rationale: Stage 2's Docker image is a reproducibility checkpoint
  ("does a clean build from source still work"), not a runtime; forcing perception/HIL
  experimentation through a container adds rebuild friction and device-passthrough complexity
  (USB camera access, no CUDA runtime needed anyway since Target Components were skipped) for
  no benefit while the code is still being iterated on. The risk of native iteration drifting
  from what Stage 2 actually verifies is accepted for now — re-run the Stage 2 gate before
  trusting anything built that way. Storage/memory headroom checked and judged sufficient for
  this dual-mode setup on the *current* microSD flash (97G free per the Part 5 smoke test,
  8GB module RAM) — Docker images/layers plus native ROS2 + Nav2 packages together are a few
  GB, well under that. The Session 16 tradeoff (transfer this Jetson into the UGV-PT chassis
  vs. buy a second module to keep this one as a dedicated CI runner) is still open and
  unaffected by this decision either way.
- **2026-07-10 — Pipeline restructured into two verification paths after Stage 3 (Piece 1 of
  a two-piece plan; Piece 2 deferred to a new Session 15).** Sketched from a hand-drawn
  diagram: Stage 3 (Gazebo) forks into a fast "sim path" (straight to its own drift/report
  job) and a slower "hardware path" (`stage-2-arm64` → `stage-4-isaac` → its own drift/report
  job), both writing to the same `FLEET_DB`. Concretely, in `ci.yml`:
  - `stage-2-arm64` now `needs: [stage-3-gazebo, changes]` (was `[stage-1-quality, changes]`)
    — fail-fast: don't spend ~10 real minutes on a native arm64 build if the fast Gazebo nav
    check already failed. This is a real trade, not free — it removes the parallelism
    stage-2/stage-3 used to have (both used to fire right after stage-1), in exchange for not
    wasting the arm64 build on code already known to be broken.
  - `stage-5-reports` split into `stage-5-reports-sim` (`needs: stage-3-gazebo`) and
    `stage-5-reports-hw` (`needs: stage-4-isaac`) — Gazebo's drift recording no longer waits
    on the arm64+Isaac chain to finish (or skips entirely if that chain fails/is skipped).
  - `stage-4-isaac`'s `needs` deliberately left on `stage-3-gazebo`, **not** changed to
    `stage-2-arm64` despite the diagram showing an arm64→Isaac arrow — nothing in Stage 4
    consumes the arm64 artifact today (it's headless Isaac Sim only, no Jetson involvement),
    so wiring that dependency in now would only add ~10 min of pointless waiting. That edge is
    real, but it's Piece 2's job to earn it (see Session 15 below), not something to fake
    today.
  - Job keys/numbers (`stage-2`, `stage-3`, ...) intentionally **not** renumbered to match the
    new execution order — Piece 2 will likely reshape this graph again (new HIL job(s), maybe
    a real `stage-2→stage-4` edge), and renumbering once after that settles beats renumbering
    twice.
  - **Known limit, not a bug:** `stage-3-gazebo`, `stage-4-isaac`, and both `stage-5-reports-*`
    jobs all run on the single self-hosted x86 GPU runner — they're logically independent now,
    but still physically serialized on that one box regardless of DAG shape. Only
    `stage-2-arm64` (a separate Jetson runner) gets genuine wall-clock parallelism. True
    concurrency for the sim/hardware split would need a second x86 GPU runner, not attempted
    here.
  - **Piece 2 — Isaac Sim + real Jetson hardware-in-the-loop — promoted from Session 14's
    optional stretch goal into its own session: see `Release1Todo.md` Session 15.** That
    session's original 2026-07-06 write-up explicitly recommended Gazebo over Isaac for this
    exact use case (Isaac's ROS2 integration called "the most fragile part of this project").
    Tonight's diagram instead put the HIL stage on Isaac (reusing Stage 4's existing slot).
    Deliberately **left open** rather than decided here — Isaac has gotten measurably more
    stable since that note (Session 11/12 got it green in CI), but real-hardware sync is a new
    failure mode stacked on top regardless of which sim engine. Session 15 needs its own
    research/design pass on this, including whether industry practice actually favors Isaac
    for this kind of work before assuming it does, and whether to prototype HIL bare-metal
    (both Gazebo and Isaac) before ever touching the arm64/CI path.
- **2026-07-10 (later same night) — Two things from the entry above corrected after review
  against the actual `ci.yml` graph and the original hand-drawn diagram:**
  1. **Job keys renumbered to match execution order**, reversing the "intentionally not
     renumbered" call above — `stage-2-arm64` → `stage-3-arm64`, `stage-3-gazebo` →
     `stage-2-gazebo` (Gazebo now runs first, gating both arm64 and Isaac). `stage-4-isaac`
     and `stage-5-reports-*` keep their numbers.
  2. **`stage-4-isaac`'s `needs` changed from `stage-2-gazebo` to `stage-3-arm64`** — the
     literal arm64→Isaac edge the diagram always showed, deliberately *not* wired above with
     the reasoning "nothing in Stage 4 consumes the arm64 artifact today." On review, wanted
     regardless, ahead of Piece 2 actually using the artifact. **Real, deliberately accepted
     consequence:** `stage-3-arm64` is skipped outright on docs-only pushes (the `changes`
     job's `if:`), and GitHub Actions propagates a skipped `needs` by default — so
     `stage-4-isaac` and `stage-5-reports-hw`'s drift recording now also skip on docs-only
     pushes, not just code changes. This incidentally resolves the "should stage-3/4/5 skip
     on docs-only pushes" question raised earlier tonight (previously left open) in the "skip
     it" direction, as a side effect of this choice rather than its own decision.
     `stage-5-reports-sim` is unaffected and still records drift on every push regardless.
  Verified live: pushing this change showed `stage-3-arm64` and `stage-4-isaac` running in
  the corrected sequence, all 8 jobs green.
- **2026-07-10 (same night) — Session 15 design resolved via a full `/superpowers:brainstorming`
  pass: Gazebo (not Isaac Sim) for both Stage 2 and Stage 4/HIL; first milestone is "Mission
  1" (navigate/photograph/return), not full coverage.** Full reasoning, rejected alternatives,
  and the deferred "Mission 2" shape are in
  `docs/superpowers/specs/2026-07-10-session15-gazebo-hil-mission1-design.md` — summary here
  (mission numbering uses the revised 2026-07-11 scheme; see that day's entry below):
  - **Gazebo wins on evidence, not vendor framing.** External research (pasted from another
    session) leaned heavily pro-Isaac in tone ("industry leader," "production pipeline") but
    never accounted for this project's own documented Isaac pain (Session 11/12's ~20
    debugging iterations; `CLAUDE.md`'s gotchas). Cross-checked against real project history
    instead of taking the research at face value, per Mike's explicit ask for that skepticism.
  - **The camera drives real mission decisions** (object detection for mission triggering,
    not just monitoring/logging) — confirmed early, since this is what makes the sim-engine
    choice matter at all for perception.
  - **Checked `/home/mike/BC/isaac_project` directly rather than trusting memory or planning
    docs.** `MasterBrief.md` (2026-06-19, superseded, predates `BLUEPRINT.md`) describes an
    aspirational YOLO+ArUco dual-detection design that was **never actually built**. The real,
    working, hardware-validated code (`src/behavior_controller.py`, tested against a live USB
    camera with real croquet balls) is classical HSV color thresholding — zero training data,
    zero ML. This directly answered "why would 2 colored spheres need training data" (they
    don't) and is the concrete evidence that the near-term mission needs none of Isaac's
    synthetic-data/NITROS differentiators.
  - **Isaac's proven fragility splits into two buckets**, and matters differently depending on
    architecture: general operational tax (manual `/clock` wiring, DDS TF replay requiring
    Isaac+Nav2 restarted together, headless RTX lidar breakage) applies regardless of mission;
    Nav2/AMCL/costmap-specific fragility (the ~20-iteration saga) only applies if running full
    Nav2 under Isaac. No camera/perception-specific Isaac issue has ever been hit in this
    project — the fragility has always been navigation-stack-side.
  - **NITROS clarified as Isaac ROS's runtime transport, not part of Isaac Sim** — adopting
    NITROS-accelerated perception on the real deployed Jetson later is decoupled from which
    simulator is used for development now. Removes "we'll want NITROS eventually" as a forcing
    function for choosing Isaac Sim today.
  - **Gazebo's multi-robot fleet ceiling is a real open question, deliberately left
    unmeasured, not assumed.** One concrete precedent exists (CycloneDDS domain-0 participant
    limit nearly exhausted by a single robot's non-composed Nav2 launch — already in
    `CLAUDE.md`'s gotchas), but the actual N-robot RTF breaking point needs real measurement,
    flagged as a future experiment rather than settled by argument. Isaac Lab's "thousands of
    parallel environments" claim was also checked and pushed back on — that's usually many
    independent simple training instances, not one shared multi-agent world, so it doesn't
    clearly answer this project's actual fleet-coordination scaling question either.
  - **Mission scope decomposed rather than accepted whole.** Mike's full vision (map-aware
    navigation → full-coverage sweep → camera-reactive behavior, plus a general
    multi-mission framework) was two different axes bundled together — a mission-framework
    extension (small, builds on Session 13's `SEMANTIC_MAP` infrastructure) and full-coverage
    planning (a real, standalone piece of new engineering, no existing Nav2 coverage planner
    in this project). Landed on "Mission 1" (navigate + photograph + return, no ball-reaction,
    no coverage) as the first HIL milestone — proves the mission-framework mechanism, real
    navigation, the camera pipeline, and the full HIL loop, without bundling in the two
    capabilities that are themselves substantial new engineering. "Mission 2" (full coverage +
    camera-reactive Nav2 integration via costmap keepout + external-cancel supervisor) is an
    explicitly deferred, already-shaped follow-up.
  - **Next step:** review the spec doc, then `/superpowers:writing-plans` for the actual
    implementation plan — bare-metal Mission 1 prototype first, before touching CI, per this
    project's existing tiered dev-loop philosophy.
- **2026-07-11 — Mission numbering flipped on Mike's spec review: the first milestone is now
  "Mission 1" (navigate → photograph → return) and the deferred coverage + camera-reactive
  follow-up is "Mission 2."** As brainstormed on 2026-07-10 the names were the other way
  around (an artifact of the order the ideas came up), which read as "build Mission 2 before
  Mission 1" — confusing. Numbering now follows build order. The spec file was renamed to
  `...-mission1-design.md` and updated in place; anything dated 2026-07-10 that says
  "Mission 2 first" is the old naming. No scope change — purely a rename.
- **2026-07-11 — Session 15 closeout: Mission 1 implemented, first real HIL run passed, HIL CI
  stage design decided.**
  - **Mission 1 implemented** on top of Session 13's `SEMANTIC_MAP` multi-waypoint
    infrastructure (`nav_fleet/semantic_map.py`, `missions.py`, `mission_runner.py`) rather
    than a bespoke script, so future missions (Mission 2, ...) are switchable through the same
    framework. New `take_picture` action primitive (`nav_fleet/image_io.py`, backed by
    pillow) writes a PNG from `/robot_001/camera/image_raw` mid-mission. The single-machine
    `sim_launch.py` was split into `sim_only_launch.py` (Gazebo + bridge) and
    `nav2_only_launch.py` (Nav2 bringup only — the mission executor runs as a separate
    third process), composed back together by
    `sim_launch.py` for Tier-1, so the same two halves can instead run on separate machines
    for HIL.
  - **Mission 1 Tier-1 (x86 Gazebo, single machine): PASS.** CLI exit 0, telemetry row
    `mission1|PASS|local|gazebo`, photo shows the bedroom from the doorway, integration test
    `tests/test_mission_run.py` passed in 16.21 s. The doorway goal `(-0.974, 2.430)` worked
    without needing the costmap-inflation fallback that was flagged as a risk at plan time.
  - **First real HIL run (2026-07-11): PASS on the first attempt.** Gazebo on the x86
    workstation talked to Nav2 + the mission executor running natively on the real Jetson
    Orin Nano, over the existing shared-Ethernet link. **Plain CycloneDDS multicast discovery
    worked — the unicast-peers fallback was not needed.** Nav2 reached "Managed nodes are
    active" in ~5 s on the Orin; the mission ran in ~18 s total (step 1 navigate ~5.3 s, step 2
    take_picture ~0.07 s, step 3 navigate ~10.6 s); DB row
    `('mission1','PASS','hil_jetson','gazebo', 7.95, 0.21)` (`mean_time_to_goal`,
    `mean_position_error`); photo verified — bedroom from the doorway, camera pipeline crossed
    the network intact. Full record, including deviations from the runbook and the
    single-run reproducibility caveat: `docs/runbooks/Mission1HILSession15.md` (Results section).
  - **HIL CI stage design decided** (`docs/session15-hil-ci-stage-design.md`): one GitHub
    Actions job on the existing x86 GPU self-hosted runner, driving the Jetson entirely over
    SSH (Nav2 launch, mission run, DB read, photo retrieval, teardown) rather than
    coordinating two separate runner jobs — keeps a single `if: always()` teardown in control
    of both sides. **No job renumbering**: the new job takes the existing Stage 4 slot as
    `stage-4-hil`, replacing `stage-4-isaac` in the same PR that adds it, so the pipeline
    shape and `needs:` edges stay stable. **`stage-4-isaac` remains in `ci.yml` until
    `stage-4-hil` is actually implemented** — this closeout only records the design, it does
    not touch `ci.yml`. Phase 2 (deferred, mechanism already decided) is what finally makes
    the existing `needs: stage-3-arm64` edge real: pulling the Stage 3 GHCR arm64 image onto
    the Jetson and running the mission executor inside it, instead of natively.
- **2026-07-12 — Roadmap gap closed on Mike's review: new Session 16 ("Update HIL Stage with
  Gazebo + Tidy Up E2E Simulation") inserted; prior 16/17+ renumbered to 17/18+ (second
  renumbering — same convention as 2026-07-10: dated historical entries keep original
  numbers).** Session 15 delivered the HIL *design* but no session owned *implementing*
  `stage-4-hil` (replacing `stage-4-isaac`) — the plan jumped from design straight to Real
  Robot. New Session 16 owns: the `stage-4-hil` CI job per
  `docs/session15-hil-ci-stage-design.md` (retiring `stage-4-isaac` in the same change),
  HIL reproducibility (≥3 consecutive green runs — Session 15's record is a single run),
  the arm64-image-consumption phase, and the parked Session 15 follow-ups (FAIL-row metric
  skew, mission validation, dead `headless` arg, photo freshness, constructor-in-try,
  Jetson `actions-runner` relocation). Also this date: **runbooks moved to
  `docs/runbooks/`** (`JetsonInstallSession14.md`, `Mission1HILSession15.md` — operator
  manuals, kept separate from the session plan by deliberate choice; root stays clean) and
  Session 15's stale "Isaac Sim" title/status in `Release1Todo.md` corrected to Gazebo/
  COMPLETE (the title predated the sim-engine decision and outlived it).
- **2026-07-12 (later) — Sequencing: NVMe migration (Session 14 Part 9) runs BEFORE Session
  16, via the 5-step sequence recorded at the top of
  `docs/runbooks/JetsonInstallSession14.md` Part 9.** Rationale: (1) Session 16's
  deliverables are *records* — build-cache benchmarks and a ≥3-consecutive-green
  `stage-4-hil` reproducibility run — and records taken on microSD go stale the moment
  storage changes; take them once, on the final configuration. (2) HIL mission timing is
  Nav2/CPU/network-bound, so SD-era HIL numbers would add noise, not signal — the
  storage-sensitive metrics are exactly Part 7's build/pull table, which the migration
  fills. (3) Migrating first avoids confounding new-CI-stage flakiness with new-storage
  behavior. (4) The SD column gets re-baselined at 25W first: the Jetson was found in 15W
  mode and pinned to 25W on 2026-07-12 (`nvpmodel -m 1`, persists), and Session 14's
  original numbers were taken at an unrecorded mode — re-measuring makes the SD-vs-NVMe
  A/B power-consistent. Also this date: root-caused the 18-minute `stage-3-arm64` build
  (BuildKit evicted the apt layer's cache → fully cold build, vs the 9m45s baseline that
  kept apt cached) — fixes (GHCR registry-backed build cache, BuildKit GC budget, pinned
  power mode, post-NVMe re-benchmark) are Session 16 Piece 1 checkboxes.
- **2026-07-12 (evening) — NVMe migration method flipped: on-device clone → fresh install
  (headless SDK Manager recovery flash primary, Jetson ISO USB as monitor-attached
  fallback — runbook Part 9's "The migration" checklist).** The same-day clone plan died at its own
  compatibility gate, checked before touching hardware: JetsonHacks'
  `migrate-jetson-to-ssd` is "only tested on JetPack 6" (repo README; last commit Jan
  2025, zero JetPack-7/r39 reports, open post-migration boot-hang issues #12/#13), while
  live inspection of the board (2026-07-12, SSD already seated — `nvme0n1` 465.8 G blank)
  showed JetPack 7.2 boots UEFI→extlinux with `root=PARTUUID` plus a separate `/boot/efi`
  ESP (`mmcblk0p10`) in a 15-partition layout the UUID-era scripts predate — the boot-config
  rewrite, the script's most critical step, is exactly the unverified part. The clone's two
  advantages had also evaporated: the 25W SD re-baseline (previous entry, point 4) was
  **dropped by decision** — the Part 7 table becomes an NVMe-at-25W go-forward record with
  the old SD numbers flagged historical, not a controlled A/B — and Mike explicitly wants
  the Part 4–8 re-provision as a learning pass that doubles as a live completeness test of
  the runbook (which is slated to graduate into a general robot-setup manual, candidate
  name `RobotSetup.md`; per the same discussion, **no new per-session runbooks** — Session
  16 material lives in `Release1Todo.md`). Rider decisions: **headless-first** — SDK
  Manager recovery flash (the already-executed Part 3 process, retargeted at NVMe) chosen
  over NVIDIA's recommended Jetson ISO installer specifically because it needs no
  monitor/keyboard (Mike's call; ISO kept as fallback); **no GUI on the Jetson** — stock
  desktop left installed but boot target set to `multi-user.target` (headless CI runner +
  Nav2 don't need it; frees memory on the 8 GB board; one-command reversible); Jetson
  identity changes at the fresh install — username `Mike`→`mike` (matches workstation;
  capital M was a pre-config accident), hostname `localhost.localdomain`→`jetson` (fixes
  the Session 14 wart at the source; enables `mike@jetson.local` mDNS). The SD stays
  untouched as rollback until Session 16's `stage-4-hil` is 3× green.
