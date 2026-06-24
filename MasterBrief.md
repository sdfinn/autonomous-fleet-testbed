# autonomous-fleet-testbed — Master Brief

**Repo:** `autonomous-fleet-testbed` (private, GitHub, created on Ubuntu)
**Last updated:** 2026-06-19
**Status:** Living document — iterate now, update only on major direction changes later.
**Reference architecture:** `G:\BC\rover_cicd_architecture.html` (open in browser, interactive)
**Guide:** `G:\BC\ros2_rover_cicd_guide.pdf`

---

## Table of Contents

1. [The Vision](#the-vision)
2. [Moonshot Pressure Test](#moonshot-pressure-test)
3. [What This Project Is NOT](#what-this-project-is-not)
4. [Release Structure: R1 → R2 → R3](#release-structure)
5. [The 10x Framework: Three Pillars](#the-10x-framework-three-pillars)
6. [Target Stack](#target-stack)
7. [Architecture: 6-Stage Pipeline](#architecture-6-stage-pipeline)
   - Stage 0 — Requirements Gate
   - Stage 1 — Code Quality
   - Stage 2 — Cross-Compile arm64
   - Stage 3 — Gazebo Harmonic (Primary CI Gate)
   - Stage 4 — Isaac Sim (RTX 5080)
   - Stage 5 — Reports + Publish
   - Stage 6 — Deploy to Jetson (R1 Live Target)
8. [Autonomy & Navigation](#autonomy--navigation)
   - What the Jetson Enables (R1)
   - The R1 Navigation Scenario
   - What We Test
   - R3: Heterogeneous Fleet — Capability Tiers and WiFi Offloading
9. [Execution Strategy: R1 → R2 → R3](#execution-strategy-r1--r2--r3)
10. [Current State → R1 → R2 → R3 Evolution](#current-state--r1--r2--r3-evolution)
11. [GitHub Strategy](#github-strategy)
    - Repo Setup
    - What to Migrate from Current Repo
    - Release / Visibility Strategy
    - Open-Core Model (Post-R2)
12. [First Actions (Ordered)](#first-actions-ordered)
13. [AI Coding Agent Workflow](#ai-coding-agent-workflow)
14. [Open Questions](#open-questions)
15. [Decisions Log](#decisions-log)
16. [Reference Files](#reference-files)

---

## The Vision

> *Build an open-source, CI/CD-native fleet simulation testing framework for autonomous robots — so small teams and independent developers can validate multi-robot systems before real-world deployment, without needing enterprise-grade infrastructure.*

**The 10x framing:** The 10% version is "better test coverage for one robot." The 10x version is: a developer commits code and a CI gate automatically spawns a parameterized legion of virtual robots, stress-tests the fleet against randomized physics and sensor conditions, detects statistical drift, and blocks the deploy if anything regresses — all before a single physical robot is touched.

The unsolved problem: there is no accessible, open-source, CI/CD-native framework for multi-robot parallel simulation testing. This project is the foundation of exactly that.

| 10% thinking | 10x thinking |
|---|---|
| Test one robot navigating one room | Test a fleet of N robots across randomized environments in CI |
| Pass/fail on a single run | Statistical drift detection across build history |
| Manual scenario creation | Parameterized perturbation matrix (physics, sensor noise, lighting) |
| Run sim manually before deploy | Headless CI gate blocks merge if fleet regressions detected |
| Portfolio project | Open-core framework any team can adopt |

---

## Moonshot Pressure Test

### The Monkey

The riskiest assumption that would collapse the project if it's wrong:

> **Headless Gazebo simulation produces results that meaningfully predict real robot behavior.**

If Stage 3 sim results have no statistical correlation with Stage 6 real-robot performance, the CI gate is theater — it blocks merges based on numbers that don't reflect what the robot actually does. This must be tested early in R1, not discovered at the end. The sim-to-real comparison module (`sim_vs_real_comparison.py`) exists for exactly this purpose. If correlation on `nav_success_rate` and `mean_position_error` is below ~70% after Stage 6, the pipeline architecture needs rethinking before R2.

### Kill Criteria

Conditions that would force a strategic pivot rather than continuing on the current path:

| Condition | What it signals | Pivot |
|---|---|---|
| Sim-to-real correlation < 70% after Stage 6 | Gazebo gate is not predictive | Rethink Stage 3 as a unit-test-only gate; move integration validation to hardware-in-loop |
| Stage 3 wall-clock time > 20 min per PR | CI gate too slow to be adopted | Reduce episode count; gate only the perturbation P50, not full matrix |
| Arm64 QEMU build > 45 min even after optimization | QEMU baseline is unusable | Procure Jetson Dev Kit before R1 closes, skip QEMU baseline |
| Zero external teams using the open CLI after public release | Adoption barrier too high | Strip to a single-command install, simplify schema, improve onboarding docs |

### Three-Audience Pitch

The same project, told for three audiences:

**Job interview (hiring manager, SDET/robotics context):**
> "I built a CI/CD pipeline that gates autonomous robot code against simulation-validated behavioral baselines — navigation success rate, position error, sensor Hz — so regressions are caught before a single physical robot is touched. The same statistical drift detector that flags a bad commit also produces the audit trail that maps every test back to a requirement."

**Business pitch (robotics startup CTO):**
> "Your team can run 20–50 parameterized fleet simulations per pull request and block the merge automatically if the distribution of outcomes shifts. No enterprise infrastructure needed — it runs on GitHub Actions."

**Open-source community (ROS2 developer):**
> "pytest for robot fleets. Drop in your URDF and your requirements YAML, and get a CI gate that tells you statistically whether your new Nav2 params made things better or worse."

---

## What This Project Is NOT

- Not a project *about* AI coding agents. Using Claude Code, Cursor, or similar to build the project faster is a workflow choice — not the product.
- Not a robotics hardware project. The physical rover is a target integration endpoint — the point is the software pipeline that tests it.
- Not a research project. The goal is a clean, buildable, demonstrable CI/CD pipeline — not novel navigation algorithms.
- Not a CrewAI / multi-agent orchestration project. "Coding legion" = using AI tools well to accelerate development. Nothing more.

---

## Release Structure

Three releases capture the full arc — from single real robot to fleet simulation to live fleet product. Every decision in R1 is made with R2 and R3 in mind.

### R1 — End-to-End Single Robot (Current Focus)

Complete the full 6-stage CI/CD pipeline with one real Waveshare UGV PT + Jetson Orin Nano Super. Simulation stages (Gazebo + Isaac Sim) AND real hardware deployment (Stage 6) are both completed before R1 closes. Hardware is purchased before R1 is declared done.

The critical R1 outcome: sim-to-real validation is real, not a placeholder. You have actual rosbags, actual sensor data, and actual deployment experience that R2 builds on.

**Tag:** `git tag r1-complete`

### R2 — Fleet Simulation (Lessons Applied)

With R1 lessons in hand, add the fleet simulation layer: the three 10x pillars (Perturbation Matrix, Parallel Orchestrator, Fleet Drift Detector) become first-class features. The framework now runs N robots simultaneously in CI, parameterized over a matrix of physics and sensor conditions. Architecture documented in `ARCHITECTURE_R2.md`.

R2 is where the project becomes a demonstrable framework, not just a pipeline. The diff between R1 and R2 is the product pitch.

**Tag:** `git tag r2-complete`

### R3 — Live Multi-Robot Fleet (Stretch / Business Transition)

The live fleet: R1's Jetson-class robot plus N cheaper bots (heterogeneous — different sensors, different compute). Some bots may have lidar but no GPU; some may have depth cameras but rely on WiFi offloading for inference. The framework handles all types via per-robot capability profiles.

R3 is the stretch goal that opens the door to consulting, open-source release, or a product pitch. It requires some hardware expense, but R1 and R2 de-risk the architecture decisions that make R3 feasible.

**Private through R2 complete. Open-source strategy revisited at R2 tag.**

### What R3 Changes in R1 and R2 Design

R3 is heterogeneous: any robot type, varying capabilities, varying sensors. Design decisions in R1 that keep R3 feasible:

- **ROS2 namespace from day one** — even with a single robot in R1, put it in `/robot_001/` namespace. R2 multi-robot becomes trivial; R3 does not require a refactor.
- **`robot_profiles/` directory from day one** — one YAML per robot type defining sensors, GPU capability, applicable tests, and whether perception offloading is needed. In R1 there's one profile. In R3 there are N.
- **`drift_config.yaml` includes `robot_type` field** — even if it's always `waveshare_ugv_pt` in R1, the field is there. R3 never requires a schema migration.
- **Test runner reads profile, not hardcode** — the test runner skips tests that don't apply to a robot type. YOLO mAP tests run only on GPU-capable bots; lidar-only tests run on all.

---

## The 10x Framework: Three Pillars

These are R1 building blocks and the explicit R2 upgrade targets. Build R1 with clean seams at these three points.

### Pillar 1: The Perturbation Matrix (Chaos Generator)

Instead of manually building N different simulation scenes, a `matrix.yaml` config file auto-injects parameter variations across the fleet. The framework reads the matrix and spawns one robot instance per parameter combination.

```yaml
# simulation/matrix.yaml (R2 target shape)
floor_friction:     [0.4, 0.7, 1.0]
sensor_noise_level: [none, low, high]
lighting_lux:       [50, 200, 400]
obstacle_count:     [2, 4, 8]
```

- **Physics fuzzing:** floor friction, wheel slip coefficient, surface slopes
- **Sensor noise:** lidar dropped packets, camera exposure variation, IMU drift
- **Environment variation:** lighting levels, obstacle density, goal pose selection

In R1, this is a single fixed scene. The clean seam is keeping environment parameters in `drift_config.yaml` from day one — the matrix just iterates over that file in R2.

### Pillar 2: Headless Parallel Orchestrator

Running N simulation worlds simultaneously on one machine requires bypassing graphical rendering entirely. The orchestrator runs lightweight, containerized headless instances that use the GPU purely for physics and kinematics.

**Key mechanism — ROS2 namespacing:** Each robot exists in its own namespace so topics don't collide:

```
/robot_001/cmd_vel    /robot_002/cmd_vel    /robot_003/cmd_vel
/robot_001/odom       /robot_002/odom       /robot_003/odom
/robot_001/scan       /robot_002/scan       /robot_003/scan
```

A Python orchestrator manages the fleet like a dispatcher: spin up instances, assign goals, monitor metrics, tear down, aggregate results.

In R1, this is a single headless Gazebo instance. The clean seam is keeping the Gazebo launch wrapper in a single `run_sim.py` function — in R2 that becomes a loop over N instances.

### Pillar 3: Predictive Drift Detector

Instead of binary pass/fail on hardcoded thresholds, the drift detector acts as a flight data recorder: it aggregates metrics across runs, tracks a statistical baseline over the last 20 builds, and emits tiered alerts when a metric regresses beyond a sigma threshold.

**Tiered severity:** Not all regressions are equal. A 2σ deviation might be noise; a 5σ deviation is a production blocker.

| Sigma | Severity | Meaning |
|---|---|---|
| ≥ 5σ | critical | Immediate block — regression is almost certainly real |
| ≥ 4σ | error | Investigate soon |
| ≥ 3σ | warning | Investigate when convenient |
| ≥ 2σ | info | Monitor — may be noise |

**Post-merge sensitivity boost:** The first 5 CI runs after a new commit use a tighter threshold (1.4σ instead of 2σ). A regression that shows up consistently in the first few post-merge runs is almost never noise — catching it early is the point.

```python
# drift_detector.py — tiered sigma system
import numpy as np

METRICS = {
    "nav_success_rate":    "down",   # alert when current < baseline
    "mean_position_error": "up",     # alert when current > baseline
    "odom_hz_mean":        "down",
    "collision_rate":      "up",
}

THRESHOLDS = {5.0: "critical", 4.0: "error", 3.0: "warning", 2.0: "info"}

def detect(history: list[dict], current: dict, runs_since_commit: int) -> list[dict]:
    σ_floor = 2.0 * (0.7 if runs_since_commit <= 5 else 1.0)
    alerts = []
    for metric, direction in METRICS.items():
        values = [h[metric] for h in history[-20:]]
        if len(values) < 5: continue
        μ, σ = np.mean(values), np.std(values, ddof=1)
        if σ < 1e-6: continue
        z = (current[metric] - μ) / σ
        if direction == "down": z = -z          # flip: lower value = worse
        if z >= σ_floor:
            severity = next(s for t, s in sorted(THRESHOLDS.items(), reverse=True) if z >= t)
            alerts.append({"metric": metric, "severity": severity,
                           "sigma": round(z, 2), "current": current[metric], "mean": μ})
    return alerts
```

Metrics tracked: `nav_success_rate`, `mean_position_error`, `mean_time_to_goal`, `collision_rate`, `odom_hz_mean`, `lidar_hz_mean`, `camera_hz_mean`. `firmware_test_pass_rate` is a hard-threshold metric (any failure = fail) and bypasses sigma analysis.

Each alert is stored in the drift archive (committed JSON) alongside the run that triggered it. In R2, alerts carry an `ai_root_cause` field: the AI coding agent reviews the alert, the recent git diff, and past similar alerts to suggest a probable cause.

**R2 enhancement — Mann-Kendall trend analysis:** The σ-threshold system catches step-change regressions. Mann-Kendall detects monotonic trends — the "boiling frog" case where each build is slightly worse but never enough to trip a threshold. R2 adds this as a parallel check, flagging sustained directional trends even when no single run hits 2σ.

In R1, drift detection runs on single-robot Gazebo results. In R2, it aggregates across the entire fleet run — a statistically much stronger signal.

---

## Target Stack

```
Ubuntu 24.04 bare metal (workstation + Jetson)
ROS2 Jazzy Jalisco
rmw_cyclonedds_cpp        ← DDS (Nav2-recommended on Jazzy; replaces FastRTPS used in old WSL2 project)
Gazebo Harmonic           ← primary headless CI gate (R1+)
Isaac Sim 5.x + RTX 5080  ← perception tests, Stage 4 (R1+, self-hosted runner)
Docker + buildx arm64
GitHub Actions            ← pipeline orchestration
ghcr.io                   ← container registry
Waveshare UGV Rover PT    ← R1 target hardware (purchased before R1 closes)
  └─ Jetson Orin Nano Super (JetPack 7.2 / Ubuntu 24.04 / CUDA 13)
  └─ ESP32 sub-controller (PID motor control, IMU, encoder odometry)
  └─ D500 lidar
  └─ OAK-D Lite depth camera
R3 fleet additions (TBD)  ← cheaper bots, heterogeneous sensors, WiFi offloading
Python / pytest           ← test harness
Pandera                   ← schema validation
Streamlit                 ← run dashboard
ReportLab                 ← PDF reports
Claude API (claude-sonnet-4-6) ← AI scenario generation
```

---

## Architecture: 6-Stage Pipeline

| Stage | Name | What it does | Hardware | Release |
|---|---|---|---|---|
| 0 | Requirements gate | Specs → traceability matrix → `check_traceability.py` | None | R1 |
| 1 | Code quality | ament_lint, clang-tidy, gtest, ESP32 Unity unit tests | None | R1 |
| 2 | Cross-compile arm64 | Docker buildx, micro-ROS layer, ghcr.io cache | None / Jetson runner | R1 |
| 3 | Gazebo Harmonic | Headless Nav2 integration + drift detection | None — **primary CI gate** | R1 |
| 4 | Isaac Sim | RTX perception tests, sim-to-real metrics, YOLO mAP | RTX 5080 workstation | R1 |
| 5 | Reports + publish | HTML/JSON artifacts, ghcr.io push, drift archive commit | None | R1 |
| 6 | Deploy to Jetson | SSH docker pull, micro-ROS bridge, smoke test, rollback | Physical rover | R1 (real) |

Stage 3 is the mandatory merge gate. Stages 4–6 run on `release/*` branch or manual trigger.

---

### Stage 0 — Requirements Gate

The traceability check runs before any build. `check_traceability.py` reads `requirements/traceability.yaml` and fails the pipeline if any requirement ID has no test mapped to it. Zero rover-specific logic — CLI args only (`--requirements`, `--test-results`). This ships unchanged into the R3 open-source package.

**Scene requirements (SC):**

| ID | Requirement |
|---|---|
| SC-01 | Flat indoor floor, 8m × 8m minimum |
| SC-02 | At least 4 static box obstacles, 0.3m tall |
| SC-03 | Defined start pose + 3 named goal poses |
| SC-04 | Lidar scan valid (no NaN/inf) in all directions — D500 lidar |
| SC-05 | Depth camera valid point cloud at 1m–6m — OAK-D Lite |
| SC-06 | Ground friction 0.7 — no wheel slip at 0.5 m/s |
| SC-07 | 400 lux uniform lighting (Isaac Sim stage) |
| SC-08 | Scene reproducible from fixed random seed |

**Brain / autonomy requirements (BR):**

| ID | Requirement |
|---|---|
| BR-01 | Navigate to goal within 0.15m of target pose |
| BR-02 | Avoid static obstacles with 0.25m clearance |
| BR-03 | Recover from stuck state within 10 seconds |
| BR-04 | Publish /odom at >= 50 Hz |
| BR-05 | SLAM map converges within 60 sec of start |
| BR-06 | E-stop halts motion within 100 ms |
| BR-07 | Nav success rate regression <= 5% across builds |
| BR-08 | CPU usage on Jetson < 80% during navigation |
| BR-09 | Lidar-camera extrinsic error < 3 cm |
| BR-10 | Behavior tree completes waypoint mission without abort |

**MCU / ESP32 requirements:**

| ID | Requirement |
|---|---|
| MCU-01 | PID control loop runs at 1 kHz, independent of ROS2 |
| MCU-02 | Watchdog: safe-stop if no cmd_vel for 200 ms |
| MCU-03 | Wheel encoder odometry published to /odom at 50 Hz |
| MCU-04 | IMU data published to /imu/data at 200 Hz |
| MCU-05 | Max motor current limit enforced in firmware |
| MCU-06 | UART communication at 921600 baud, JSON instruction set |

**Traceability YAML:**

```yaml
# requirements/traceability.yaml
tests:
  test_waypoint_arrival:    covers: [BR-01]
  test_obstacle_avoidance:  covers: [BR-02, SC-02]
  test_odom_rate:           covers: [BR-04, MCU-03]
  test_slam_convergence:    covers: [BR-05, SC-08]
  test_estop_latency:       covers: [BR-06, MCU-02]
  test_drift_nav_success:   covers: [BR-07]
  test_lidar_valid:         covers: [SC-04]
  test_camera_pointcloud:   covers: [SC-05]
  test_mcu_pid_rate:        covers: [MCU-01]
  test_mcu_current_limit:   covers: [MCU-05]
```

---

### Stage 1 — Code Quality

Runs on every push.

**1a. ament_lint + cpplint:**
```xml
<test_depend>ament_lint_auto</test_depend>
<test_depend>ament_lint_common</test_depend>
```
Checks: cpplint, uncrustify, cppcheck, flake8/pep8, ament_copyright.

**1b. clang-tidy static analysis:**
```yaml
Checks: >-
  clang-diagnostic-*, clang-analyzer-*, cppcoreguidelines-*,
  modernize-*, readability-*, -modernize-use-trailing-return-type
```

**1c. gtest (ROS2) + ESP32 Unity tests (PlatformIO, no hardware needed):**
```bash
colcon test --packages-select rover_control && colcon test-result --verbose
pio test -e native   # ESP32: PID bounds, watchdog, kinematics, JSON parsing, current limits
```

---

### Stage 2 — Cross-Compile arm64

**Why arm64 and why the Jetson runner matters:**

The Jetson Orin Nano Super is ARM64 (Cortex-A78AE). Standard GitHub Actions cloud runners are x86_64. Building ARM64 Docker images on x86_64 requires QEMU — a software CPU emulator that translates every ARM instruction to x86 at runtime. A full ROS2 colcon build via QEMU takes **25+ minutes** per pipeline run.

Registering the Jetson as a GitHub Actions self-hosted runner changes this completely: the arm64 image builds natively on ARM hardware — no translation, no emulation overhead. Build time drops to **~3 minutes**. Side benefit: since the Jetson is already running JetPack 7.2 / Ubuntu 24.04 / CUDA 13, native builds catch runtime issues (driver mismatches, library ABI differences) that cross-compiled QEMU builds miss entirely.

**QEMU path (before Jetson runner is registered):**
```yaml
- uses: docker/setup-qemu-action@v3
- uses: docker/setup-buildx-action@v3
- uses: docker/build-push-action@v5
  with:
    platforms: linux/arm64
    push: false
    cache-from: type=gha
    cache-to: type=gha,mode=max
    file: docker/Dockerfile.ros2
```

**Jetson self-hosted runner (activate when hardware is in hand):**
```yaml
runs-on: [self-hosted, arm64, jetson]
# Register: GitHub > Settings > Actions > Runners > New self-hosted runner
# Labels: self-hosted, arm64, jetson
```

**Docker image layers (cache-optimized):**
```
Layer 1: ros:jazzy-ros-base (Ubuntu 24.04)   — rarely changes
Layer 2: system apt deps + micro-ROS agent   — cached across most builds
Layer 3: colcon build of rover packages      — rebuilds per commit
Layer 4: runtime entrypoint                  — thin, fast
```

**micro-ROS agent in image:**
```dockerfile
FROM ros:jazzy-ros-base AS base
RUN apt-get install -y ros-jazzy-micro-ros-agent
```

**ESP32 JSON instruction set (UART at 921600 baud):**
```json
{"T":1,"L":0.5,"R":0.5}   // set left/right velocity
{"T":0}                    // emergency stop
{"T":2,"cmd":"get_imu"}    // request IMU reading
```

**Image tagging:**
```
ghcr.io/youruser/rover_ws:abc1234   # immutable SHA
ghcr.io/youruser/rover_ws:latest    # main branch tip
ghcr.io/youruser/rover_ws:stable    # post-smoke-test promoted
```

---

### Stage 3 — Gazebo Harmonic (Primary CI Gate)

Must pass for any merge to main. Runs headless — no GPU, no display required.

```bash
sudo apt-get install -y ros-jazzy-ros-gz ros-jazzy-gz-ros2-control gz-harmonic

ros2 launch rover_bringup sim_test.launch.py \
    headless:=true \
    world:=simulation/gazebo/rover_world.sdf \
    timeout:=120
```

**URDF essentials:** Start from Waveshare `ugv_ws` GitHub repo. 4 drive wheels + 2 passive casters, differential drive plugin. D500 lidar → `/robot_001/scan` at 10 Hz. OAK-D Lite → `/robot_001/camera/depth/points`. IMU → `/robot_001/imu/data` at 200 Hz. Ground truth pose plugin for test assertions.

Note: all topics under `/robot_001/` namespace from day one, even in Gazebo with a single robot.

**Nav2 test assertions per run:**
- Euclidean distance to goal < 0.15m (BR-01)
- Zero collisions (BR-02)
- Recovery completes within 10s if triggered (BR-03)
- `/robot_001/odom` Hz >= 50 (BR-04)
- `/robot_001/scan` Hz >= 10 (SC-04)
- Behavior tree returns SUCCESS (BR-10)

**Drift detection thresholds (stored in `drift_config.yaml`, not hardcoded):**

| Metric | Direction | Threshold | Requirement |
|---|---|---|---|
| `nav_success_rate` | down > 5% | fail | BR-07 |
| `mean_position_error` | up > 3 cm | fail | BR-01 |
| `mean_time_to_goal` | up > 5 s | fail | — |
| `collision_rate` | up > 2% | fail | BR-02 |
| `odom_hz_mean` | down > 5 Hz | fail | BR-04 |
| `lidar_hz_mean` | down > 1 Hz | fail | SC-04 |
| `camera_hz_mean` | down > 1 Hz | fail | SC-05 |
| `firmware_test_pass_rate` | any failure | fail (hard) | MCU-all |
| `stage_2_arm64_build` | up > 60 s | warn | CI health |
| `stage_3_gazebo` | up > 30 s | warn | CI health |

History window: rolling last 5 passing builds. CI timing metrics use `warn` not `fail` — a slow build is a signal, not a blocker. The `runner_type` field in the report schema means QEMU and Jetson runs are automatically separated in the drift history, so a runner change doesn't create a false regression alert.

---

### Stage 4 — Isaac Sim (RTX 5080 · Ubuntu 24.04)

Runs on the self-hosted workstation runner. RTX renderer enables perception tests impossible in Gazebo headless. Ubuntu 24.04 + CUDA 13 alignment across workstation and Jetson reduces driver friction.

```bash
pip install isaacsim-rl isaacsim-replicator isaacsim-extscache-physics \
  --extra-index-url https://pypi.nvidia.com
```

**Perception tests:**
- YOLO mAP vs annotated Isaac ground truth
- D500 lidar point density at 5m, 10m, 20m
- OAK-D Lite depth RMSE vs ground truth (target: < 3 cm at 2m)
- Camera exposure stability across lighting (SC-07)
- Multi-reflection lidar test (glass surfaces)
- Low-light navigation at 50 lux

**Sim-to-real metrics** (meaningful because R1 has real rosbags from Stage 6):

| Metric | Target |
|---|---|
| D500 lidar density | < 5% diff vs real rosbag at 5m |
| OAK-D Lite depth RMSE | < 3 cm at 2m |
| SLAM trajectory RMSE | < 0.05m over 10m route (evo_ape) |
| Nav2 success rate | sim >= real − 5% |
| Velocity profile | < 0.1 m/s RMSE vs commanded |

```bash
./python.sh simulation/isaac/run_validation.py \
  --headless --scene simulation/isaac/rover_scene.usd \
  --ros2-bridge --num-runs 20 --output reports/isaac_run.json
```

---

### Stage 5 — Reports + Publish

Every run produces a JSON artifact and HTML summary. Drift history committed to `reports/history/`.

```json
{
  "run_id": "sha-abc123",
  "robot_type": "waveshare_ugv_pt",
  "runner_type": "jetson-self-hosted",
  "jetson_stack": "JetPack 7.2 / Ubuntu 24.04 / Jazzy",
  "stage_timings_sec": {
    "stage_0_requirements": 12,
    "stage_1_quality":      94,
    "stage_2_arm64_build":  187,
    "stage_3_gazebo":       143,
    "stage_4_isaac":        310,
    "stage_5_reports":      18
  },
  "stages": {
    "firmware_tests": {"status": "pass", "unity_passed": 12},
    "gazebo_sim": {"nav_success_rate": 0.92, "odom_hz_mean": 51.2, "drift_status": "clean"}
  }
}
```

`stage_timings_sec` is captured from day one. `runner_type` records whether Stage 2 ran on QEMU cloud or native Jetson — the field makes the before/after comparison automatic in the drift archive. `robot_type` is in the schema from day one — R3 multi-type reporting doesn't require a schema migration.

---

### Stage 6 — Deploy to Jetson (R1 Live Target)

**Status in R1: real deliverable, hardware purchased before R1 closes.**

**Simulation stages use programmatic maps — no SLAM needed.** Stages 3 and 4 generate the Nav2 occupancy grid directly from scene geometry (`scripts/generate_map.py`). No teleop, no SLAM session, no GPU required for map building in CI.

**First deployment only: build real-world map.** Before Stage 6 can run repeatably in CI, you need one SLAM session with the real robot. Teleop it through the full environment, save the map, commit it. Every subsequent Stage 6 CI run uses the committed map file unattended.

```bash
# On Jetson — one-time setup, not a CI step
ros2 launch slam_toolbox online_async_launch.py
# In a second terminal: teleop through full room, then:
ros2 run nav2_map_server map_saver_cli -f maps/bedroom_real
# Commit maps/bedroom_real.pgm + maps/bedroom_real.yaml to repo
```

```yaml
- name: Deploy to Jetson Orin Nano Super
  run: |
    echo "$SSH_KEY" > /tmp/key && chmod 600 /tmp/key
    ssh -i /tmp/key jetson@$JETSON_HOST \
      "docker pull ghcr.io/$REPO:latest && \
       docker compose -f ~/rover/docker-compose.yml up -d --remove-orphans"
```

**Smoke test + auto-rollback:**
```bash
sleep 15
ssh -i /tmp/key jetson@$JETSON_HOST \
  "source /opt/ros/jazzy/setup.bash && \
   ros2 topic hz /robot_001/odom --once && \
   ros2 topic hz /robot_001/scan --once && \
   echo SMOKE_PASS" | grep SMOKE_PASS || (
  ssh -i /tmp/key jetson@$JETSON_HOST \
    "docker compose down && docker run -d ghcr.io/$REPO:stable"
  exit 1
)
```

**Topics verified:** `/robot_001/odom` (>= 50 Hz), `/robot_001/scan` (>= 10 Hz), `/robot_001/camera/depth/points`, `/robot_001/imu/data` (>= 100 Hz), `/tf`.

**ESP32 watchdog:**
```cpp
const uint32_t WATCHDOG_MS = 200;
void loop() {
  rclc_executor_spin_some(&executor, 1000000);
  if (millis() - last_cmd_ms > WATCHDOG_MS)
    set_motor_velocities(0, 0);
}
```

**Jetson initial setup (one-time when hardware arrives):**
```bash
# Flash JetPack 7.2 via Unified ISO (developer.nvidia.com/embedded/jetpack)
sudo apt install ros-jazzy-ros-base ros-jazzy-micro-ros-agent
# Register as self-hosted GHA runner (see Stage 2 above)
```

---

## Autonomy & Navigation

### What the Jetson Enables (R1)

The Jetson Orin Nano Super's GPU (1024 CUDA cores + 32 Tensor Cores) is the key differentiator from a Raspberry Pi. On the Waveshare UGV PT it enables:

**Navigation stack:**
- **SLAM mapping** (slam_toolbox) — builds and updates a 2D occupancy grid in real time from D500 lidar while navigating
- **Global path planning** (Nav2 + Smac Planner) — lattice-based A* over the SLAM map
- **MPPI local controller** (Model Predictive Path Integral) — GPU-accelerated trajectory sampling; smoother and more reactive than the standard DWB controller
- **Behavior tree mission execution** (Nav2 BT Navigator) — multi-step missions: go to waypoint, recover if stuck, retry, execute conditional behaviors
- **Dynamic costmap** — fused obstacle map from lidar (/scan) + depth camera (/camera/depth/points)

**Perception (GPU-accelerated on Tensor Cores):**
- **YOLO object detection** — 30–60 FPS real-time detection; identifies and classifies objects in the camera feed
- **OAK-D Lite depth fusion** — combines YOLO bounding boxes with depth data to get 3D positions of detected objects, not just 2D screen positions
- **Lidar-camera extrinsic calibration** — fuse /scan and depth point cloud for a richer, more reliable obstacle costmap
- **Low-light / adverse condition handling** — GPU enables running perception models that are too slow for CPU in degraded conditions

### The R1 Navigation Scenario

**Bedroom Coverage Patrol with Dual Detection**

Same room as the Jetbot project (bedroom carpet), but on a smarter platform and with a richer detection stack. The familiar setup — colored balls, defined coverage path — makes sim-to-real comparison easy since the environment is already characterized.

The robot:
1. Starts at home position (defined corner of carpet area)
2. Navigates coverage waypoints across the carpet (lawnmower pattern or defined grid)
3. Encounters a **red ball** → STOP, log detection, test expects halt within 500ms
4. Encounters a **yellow ball** → DETOUR, navigate around the ball, continue mission
5. Detects **ArUco markers** at designated waypoints → log marker ID and 6DOF pose, verify correct ID matched expected
6. Returns to home, logs mission complete

**Detection stack — two layers, running simultaneously on Jetson GPU:**
- **YOLO** — colored ball detection and classification (red vs yellow). Same behavioral logic as the Jetbot project; same test intuition carries forward.
- **OpenCV ArUco** (`cv2.aruco`) — marker ID + 6DOF pose estimation. No YOLO training needed; OpenCV handles this natively. Runs in the same ROS2 node.

Both detection streams publish to separate topics: `/robot_001/detected_objects` (YOLO) and `/robot_001/aruco_detections` (ArUco). The behavior tree subscribes to both and branches accordingly.

**Additional BR requirements for R1 dual detection:**

| ID | Requirement |
|---|---|
| BR-11 | YOLO detects red ball within 1m at >= 90% confidence → robot halts within 500ms |
| BR-12 | YOLO detects yellow ball within 1.5m at >= 85% confidence → detour initiated |
| BR-13 | ArUco marker detected within 0.5m → ID logged, pose error < 5cm position / < 5° orientation |
| BR-14 | Full coverage mission visits all waypoints or logs reason for any skip |

**R1 mission test assertions:**
- Arrive at each waypoint within 0.15m (BR-01)
- Zero collisions during full mission (BR-02)
- Recovery from stuck within 10s if triggered (BR-03)
- Red ball halt within 500ms of detection threshold (BR-11)
- Yellow ball detour completes without backtracking to same ball (BR-12)
- ArUco ID and pose logged correctly at each marker waypoint (BR-13)
- Full mission completes or all skips are logged with reason (BR-14)
- Nav success rate stable across builds (BR-07)

### Test Environments: R1 → R2 → R3

The environment scales across releases — from bedroom to court to live outdoor deployment.

| | R1 | R2 (simulated) | R3 (real) |
|---|---|---|---|
| Location | Bedroom carpet | Backyard basketball court (Gazebo) | Actual backyard basketball court |
| Area | ~3m × 4m | Half-court ~14m × 15m | Same as R2 |
| Surface | Indoor carpet | Concrete/asphalt | Real concrete |
| Lighting | Controlled indoor | Parameterized 50–1000 lux | Natural outdoor (variable) |
| Key obstacles | Colored balls + ArUco markers | Court furniture + dynamic obstacles | Real world |
| Fleet size | 1 robot | 3–5 parallel sim instances | 2–3 real robots |
| Nav challenge | Tight space, reactive behavior | Large open area + zone coverage | Real sensor noise + weather |

**Why basketball court for R2:** The court has known dimensions, clear structural zones (key, arc, wing), and court markings that are excellent SLAM landmarks. It's large enough to make a fleet make sense for coverage. The perturbation matrix maps naturally to outdoor variables:

```yaml
# simulation/matrix.yaml (R2 court scenario)
surface_friction:  [0.6, 0.8, 1.0]   # dry vs damp concrete
lighting_lux:      [50, 400, 1000]    # dawn, cloudy, direct sun
obstacle_config:   [clear, benches, cones]
robot_count:       [1, 3, 5]
```

**R2 fleet coverage scenario (draft):** 3 robots assigned to non-overlapping court zones (paint/key, left wing + arc, right wing + arc). Each robot maps its zone, identifies ArUco markers on the court surface, and reports back. The CI gate validates that collective zone coverage meets a target percentage within a time budget. This is the fleet coordination demo that doesn't exist in R1.

### What We Test

| Layer | What's tested | Stage |
|---|---|---|
| MCU firmware | PID bounds, watchdog, encoder math, JSON parsing | Stage 1 (unit), Stage 6 (smoke) |
| Sensor rates | /odom Hz, /scan Hz, /imu Hz | Stage 3 + Stage 6 |
| Navigation accuracy | Waypoint arrival error, collision rate | Stage 3 + Stage 6 |
| Recovery behavior | Stuck recovery time | Stage 3 |
| Colored ball detection | YOLO confidence, halt latency (BR-11), detour trigger (BR-12) | Stage 4 (sim) + Stage 6 (real) |
| ArUco detection | Marker ID accuracy, pose error (BR-13) | Stage 4 (sim) + Stage 6 (real) |
| Perception fidelity | YOLO mAP, depth RMSE, lidar density | Stage 4 |
| Sim-to-real gap | Trajectory RMSE, velocity profile, detection rate delta | Stage 4 vs Stage 6 real data |
| Mission completeness | All waypoints visited or skip logged (BR-14) | Stage 3 + Stage 6 |
| Drift | All above metrics tracked over build history | Stage 3 + Stage 5 |
| Traceability | Every requirement has a test | Stage 0 |

### R3: Heterogeneous Fleet — Capability Tiers and WiFi Offloading

**Hardware cost reality and fleet strategy:**

| Item | Estimated cost |
|---|---|
| Waveshare UGV Rover PT (with D500 lidar + OAK-D Lite) | ~$700 |
| Jetson Orin Nano Super Dev Kit | ~$250 |
| **R1 total (one robot)** | **~$950** |

For R3, two options:

- **Option A — Homogeneous:** 2 more identical Waveshare UGV PT + Jetson setups. ~$950 × 2 = ~$1,900 additional. Full capability on every robot. Boring architecturally.
- **Option B — Heterogeneous flagship + workers:** 1 Jetson robot (already owned from R1) + 2–3 cheaper bots (~$400–500 each). **This is the more interesting option.** The demo: cheap bots handle physical coverage, Jetson handles perception and coordination. Proves the framework is fleet-capable without a GPU in every unit.

**Cheaper bot breakdown (~$400–500 per unit):**
- Waveshare UGV Rover base model (no premium sensors): ~$200–300
- Raspberry Pi 5 (4GB): ~$60
- Basic 2D lidar (RPLIDAR A1 or similar): ~$100–150
- Total: ~$360–510

**R3 decision: Option B (heterogeneous).** Leaning confirmed. One Jetson flagship from R1 + 2 cheaper bots.

**1. Per-robot capability profiles (`robot_profiles/`)**

Every robot type has a YAML. Test runner reads it and routes tests accordingly. Drift detector groups metrics by capability tier — never comparing YOLO mAP between a Jetson bot and a lidar-only bot.

```yaml
# robot_profiles/waveshare_ugv_pt.yaml  (R1 robot — full capability)
robot_type: waveshare_ugv_pt
sensors: [lidar_d500, depth_oak_d_lite, imu]
compute: jetson_orin_nano_super
gpu: true
perception_offload: false
applicable_tests: [all]

# robot_profiles/rpi_rover_basic.yaml  (R3 cheaper bot — lidar only, no GPU)
robot_type: rpi_rover_basic
sensors: [lidar_2d, imu]
compute: raspberry_pi_5
gpu: false
perception_offload: true        # stream camera to central Jetson GPU node
applicable_tests: [nav, lidar, odom]   # YOLO/ArUco tests skipped locally
```

**2. WiFi offloading for perception on GPU-less bots**

ROS2 DDS works over WiFi natively — all robots on the same network communicate via standard pub/sub. No special protocol. The offloading pattern:

```
RPi bot (/robot_002/)
  └─ publishes /robot_002/camera/image_raw  (raw frames over WiFi)

Jetson perception server node (runs on /robot_001 Jetson)
  └─ subscribes to /robot_002/camera/image_raw
  └─ runs YOLO + ArUco detection
  └─ publishes /robot_002/detected_objects and /robot_002/aruco_detections

RPi bot nav stack
  └─ subscribes to /robot_002/detected_objects (reacts to detections without local GPU)
```

WiFi latency is typically 50–100ms — acceptable for navigation-level decisions. Hard real-time motor control stays on the ESP32 at 1 kHz, completely independent of WiFi latency.

**R3 basketball court demo scenario (draft):**
The fleet covers the backyard court. The Jetson robot leads — it has full perception and acts as the fleet's perception hub. The two RPi bots cover their assigned zones, offloading camera inference to the Jetson. The collective task: identify all ArUco markers placed on the court and log their positions. The CI pipeline validates: did all three robots complete their zones? Did the ArUco detections agree across all three robots? Was the WiFi offload latency within spec?

This is a compelling live demonstration of the full 10x framework: real robots, heterogeneous fleet, WiFi coordination, CI/CD validates the whole thing.

---

## Execution Strategy: R1 → R2 → R3

### R1: End-to-End Single Robot

Follow the 6-stage guide faithfully. Clean, correct, conventional. No clever abstractions beyond what the guide requires. Rover purchased before R1 closes. Real Stage 6 deployment is part of R1 completion.

**Four structural decisions that keep R1 clean for R2 refactoring (implement from day one):**

1. **`parse_gazebo_result()`** — single function for all sim output parsing. Becomes the adapter interface in R2 when multiple sim instances need to feed the same downstream logic.
2. **`drift_config.yaml`** — all thresholds as data from day one. In R2, this makes `drift_detector.py` a generic CLI across robot types.
3. **`check_traceability.py` as zero-rover logic** — CLI args only (`--requirements`, `--test-results`). Ships as-is into the R3 open-source package.
4. **`run_sim.py` as a single function wrapper** — encapsulates the Gazebo launch and result collection. In R2 this becomes a loop over N instances.

**Tag:** `git tag r1-complete`

### R2: Fleet Simulation (Lessons Applied)

After `r1-complete` is tagged, upgrade with documented architectural changes:

- **Perturbation Matrix** — `matrix.yaml` drives parallel simulation runs
- **Headless Parallel Orchestrator** — N robots, N namespaces, one result aggregator
- **Fleet Drift Detector** — statistical baseline over fleet-wide runs, not single-robot
- Document in `ARCHITECTURE_R2.md`

The diff between r1 and r2 tags is the product pitch.

**Tag:** `git tag r2-complete`

### R3: Live Multi-Robot Fleet

After r2-complete, evaluate open-source release timing. Then build the live heterogeneous fleet:

- Multiple robot types, defined via `robot_profiles/`
- WiFi offloading for perception on GPU-less bots
- Fleet orchestration UI (extend Streamlit dashboard)
- Framework presented as productizable

**Open-source strategy revisited at r2-complete.**

---

## Current State → R1 → R2 → R3 Evolution

```
Current (Jetbot / Isaac Sim)          R1 (single rover, full pipeline)      R2 (fleet simulation)             R3 (live fleet, business)
───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Single Jetbot, Isaac Sim only         Waveshare UGV PT, Gazebo + Isaac      N robots in parallel sim           N real robots, heterogeneous
Windows 11 / WSL2                     Ubuntu 24.04 bare metal               Same, cloud-scalable               Same + WiFi fleet mesh
1 room, fixed scene                   Fixed scene, namespaced               Perturbation matrix                Real-world environments
Manual runs                           GitHub Actions CI pipeline            Parameterized chaos matrix         Live fleet orchestration
Isaac Sim drift detection             Stage 3 Gazebo drift (r1)             Fleet-wide drift aggregation       Cross-type drift comparison
SQLite + Streamlit                    JSON artifacts + drift archive        Fleet dashboard                    Fleet orchestration UI
Public repo                           Private repo                          Private through r2-complete        Open-source core extract
Stage 6 deferred                      Stage 6 real (rover purchased R1)     Stage 6 = multi-robot deploy       N-robot deploy
1 robot profile                       1 profile (waveshare_ugv_pt)          Profile per sim instance type      Profile per real robot type
```

---

## GitHub Strategy

### Repo: `autonomous-fleet-testbed`

Create fresh on Ubuntu after dual boot is set up. Initialize with:
- `README.md` — project description, pipeline status badge, hardware status
- `CLAUDE.md` — dev environment, quick-start commands, gotchas
- `.github/workflows/` — CI skeleton (built stage by stage)
- `robot_profiles/` — one YAML for Waveshare UGV PT (R1), expanded in R3
- `requirements/` — traceability.yaml and specs (Stage 0 deliverable)

### What to Migrate from Current Repo

Do not copy wholesale — current project is ~70% Isaac Sim-specific code. Cherry-pick and clean (remove Windows/WSL2 path assumptions):

| File | What to take | What to change |
|---|---|---|
| `src/baseline_monitor.py` | Rolling-window drift algorithm | Metric schema changes for new sensors/robot; upgrade to tiered sigma system (Pillar 3) |
| `src/telemetry_logger.py` | SQLite logging class (TelemetryLogger) — DB write layer pattern | Schema rewrites for new robot/sensor metrics; remove Windows absolute path assumptions |
| `src/validate_telemetry.py` | Pandera schema validation + CI gate wiring | Schema class rewrites entirely for new sensors; gate logic reuses as-is |
| `src/generate_test_report.py` | ReportLab + matplotlib PDF report structure | Swap metric names and chart data; remove Windows path assumptions |
| `src/ai_test_generator.py` | Claude API scenario generation + feedback loop | Update model: `claude-sonnet-4-6`; update context for multi-robot scenarios (fleet-wide, not single-robot) |
| `src/scenario_analyzer.py` | 0.0–1.0 quality scoring of AI scenarios; feeds high-value results back into next prompt | Update scoring criteria for fleet/coverage scenarios |
| `src/sim_vs_real_comparison.py` | Statistical sim-to-real comparison (trajectory RMSE, Hz deltas, coverage rate) | Update metric names; two DB inputs (Gazebo run + Stage 6 real rosbag) |
| `dashboard/app.py` | Streamlit multi-tab structure and layout | Swap data model; add `robot_type` and `runner_type` fields; update tabs for fleet metrics |
| `.github/workflows/` | CI skeleton (trigger, jobs, artifact upload) | Gut Isaac Sim-specific steps; rebuild per 6-stage guide |
| `tests/test_baseline.py` | pytest structure and fixture patterns | Rewrite test content for new metrics and drift schema |
| `tests/test_ros2_contracts.py` | ROS2 topic contract tests (type, Hz, schema validation) — Stage 3 CI gate | Update topic names to `/robot_001/` namespace; update expected Hz rates for new sensors |

**Do NOT migrate:** `launch_scene.py`, `nav_controller.py`, `behavior_controller.py`, OmniGraph files, USD scene files, `ros2_src/` Isaac Sim bridge code, `object_detector.py` (Replicator-specific), `obstacle_utils.py` (USD prim injection), `sim_mock.py` (replaced by headless Gazebo Stage 3), `migrate_telemetry.py` (one-off schema migration), `conftest.py` (sim_app fixture is Isaac Sim-specific).

### Release / Visibility Strategy

```
Private: autonomous-fleet-testbed      ← all dev work through r2-complete
    └── Real experiments, in-progress, proprietary refinements

Public (after r2-complete): evaluate   ← open-source the generalizable core
    └── Timing and scope TBD at r2-complete

Current public repo stays public       ← sdfinn/autonomous-nav-test-pipeline
    └── Clean it up: proper README, frame as "Phase 1 — single robot sim pipeline"
    └── Standalone portfolio evidence of the journey
```

### Open-Core Model (Post-R2)

The traceability gate and local drift detector are the most generalizable pieces — they're not rover-specific. The right business model split follows a real value boundary, not an arbitrary feature gate:

| Tier | What's included | Why free / why paid |
|---|---|---|
| **Free / open-source** | `check_traceability.py` CLI + local `drift_detector.py` | Zero external state — reads YAML and JSON files in the repo; charging for this just pushes teams to maintain their own version |
| **Paid — hosted** | Fleet dashboard, cross-run history, alert notifications | Requires always-on server and storage beyond CI artifact retention — a hosting-cost boundary, not a cleverness boundary |
| **Paid — predictive** | Drift model trained on pooled multi-team run data | Needs many teams' histories to outperform per-team static thresholds; genuine network-effect moat. **Do not market until the data exists.** |

**Sequencing:** Open-source CLI first → get adoption → hosted dashboard as first paid tier → predictive model once sufficient pooled data exists. Building the predictive model before the data is an overclaim that erodes credibility with the technical audience this tool needs.

This model means R1 and R2 produce the open-source core (the CLI tools). The hosted and predictive tiers are post-R2 product decisions, not engineering tasks.

---

## First Actions (Ordered)

Structured as two infrastructure phases before hardware enters at all. Each step unblocks the next.

### Phase A — Simulation Pipeline (No Hardware Required)

1. **Ubuntu 24.04 dual boot** — Gazebo Harmonic, native ROS2 Jazzy, and Isaac Sim with RTX 5080 all require bare metal Ubuntu. Everything else depends on this. (See Open Questions for partition configuration.)
2. **Create `autonomous-fleet-testbed` private repo** on GitHub from Ubuntu. Initialize with README, CLAUDE.md, `robot_profiles/`, `requirements/`.
3. **Ubuntu dev environment** — ROS2 Jazzy, Gazebo Harmonic, Docker + buildx, register RTX 5080 workstation as self-hosted GHA runner for Stage 4.
4. **Stage 0: Write requirements** — `scene_requirements.md`, `brain_requirements.md`, `traceability.yaml`, `check_traceability.py`. First real deliverable.
5. **Port and clean the five files** from current repo (Windows path assumptions removed, model IDs updated).
6. **Stage 1: Wire up CI linting and unit tests** — green pipeline before any rover-specific code.
7. **Stage 2: arm64 Docker build with QEMU** — Dockerfile, buildx, clean ghcr.io image. Use QEMU on standard cloud runner intentionally — this is the baseline to measure. **Capture and record Stage 2 wall-clock time.**
8. **Stage 3: Gazebo headless** — URDF working, Nav2 launching, first passing navigation test. First real CI gate.
9. **Stage 4 (Isaac Sim) + Stage 5 (reports)** — complete the simulation pipeline end-to-end.
10. **Tag:** `git tag ci-qemu-baseline` — records the full pipeline timing before any hardware optimization.

*At this point: Stages 0–5 are green on cloud runners + workstation. Stage 6 is written and pending hardware. This is a complete, demonstrable CI/CD simulation pipeline.*

### Phase B — Jetson Runner Upgrade (First Hardware Purchase)

11. **Buy Jetson Orin Nano Super Developer Kit (~$250)** — standalone mini-computer, connects to home network via ethernet. No rover needed yet.
12. **Set up Jetson Dev Kit** — flash JetPack 7.2, install ROS2 Jazzy, register as GitHub Actions self-hosted runner with labels `[self-hosted, arm64, jetson]`.
13. **Update Stage 2 workflow** — switch `runs-on` from cloud runner to `[self-hosted, arm64, jetson]`. One line change in the YAML.
14. **Measure Stage 2 timing again** — same build, native arm64 hardware.
15. **Tag:** `git tag ci-jetson-upgrade` — records the timing after the upgrade.
16. **Document the delta** — the diff between these two tags, plus the timing numbers, is a quantified case study. Expected: ~25–28 min → ~3 min (85–89% reduction in Stage 2 cycle time).

### Phase C — Real Hardware (Rover Purchase, Before R1 Closes)

17. **Order Waveshare UGV PT** — rover chassis + D500 lidar + OAK-D Lite + Jetson carrier board (~$700, no Jetson module included).
18. **Transfer or buy second Jetson module** — either move the module from the Dev Kit to the rover carrier board, OR buy a second Jetson module (~$250) to keep the Dev Kit as a permanent desk CI runner.
19. **Stage 6: Deploy pipeline** — SSH deploy, smoke test, auto-rollback, real sensor validation.
20. **R1 complete.** Tag `git tag r1-complete`.

---

## AI Coding Agent Workflow

### Philosophy

Using agentic tools (Claude Code, Cursor) is a multiplier — GPS for navigating large codebases faster. The danger is not that agents write bad code; it's that they write *plausible* code you can't interrogate. The skill at risk is not writing code — it's reading and reasoning about code you didn't write.

Your QA instinct is the right frame: you think in systems, not components. Agents optimize locally (one function, one file). Your value is reading horizontally — across files, across services, across the sim-to-real boundary.

**The person who knows what to test and why is worth more than the person who writes the test. Agents are making that gap wider, in your favor.**

### Lean Claude API Approach (Not CrewAI)

A lightweight state-machine Python script routes tasks to specialized role prompts. Prompt caching keeps costs low (cached input tokens ~90% cheaper). Three specialized roles cover the project:

- **Firmware Specialist** — ESP32 PlatformIO, micro-ROS config, UART/JSON safety
- **Autonomy Engineer** — ROS2 workspaces, Nav2, behavior trees, Python integration tests
- **CI/CD & Test Architect** — GitHub Actions, Gazebo SDF validation, drift regression logic

```python
# agent_workspace.py — lightweight, no framework needed
import os, anthropic

client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

def run_coding_task(role_prompt: str, task: str, target_file: str) -> str:
    with open(target_file) as f:
        source = f.read()
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4000,
        temperature=0.2,
        system=[{"type": "text", "text": role_prompt,
                 "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user",
                   "content": f"File ({target_file}):\n\n{source}\n\nTask:\n{task}"}]
    )
    return response.content[0].text
```

**Guardrails:** Always run agents on an isolated feature branch. Set `max_iter` limits on loops. Keep `PROJECT_ARCHITECTURE.md` as ground truth fed as cached context.

### Five Principles for Staying Sharp

1. **Explain It Back** — Never accept agent-generated code until you can explain it at the systems level: "this does X, talks to Y via Z, fails if W."
2. **Debug Solo First** — 15–20 minutes independent diagnosis before asking the agent.
3. **Architecture First Always** — Write plain English description (inputs, outputs, failure modes, integration points) before any agent writes a line.
4. **Maintain a No-Agent Zone** — One area owned entirely yourself. Best candidate: `drift_detector.py` core logic.
5. **Read Horizontally** — Regularly trace a single event through every layer: firmware → ROS2 topic → Nav2 → test assertion → drift detector → CI gate.

---

## Open Questions

Live decisions. When answered, move to Decisions Log.

| # | Question | Status |
|---|---|---|
| 1 | Ubuntu 24.04 dual boot partition size and bootloader config | Hold — too detailed for now. Revisit at install time. |
| 2 | Confirm Jetson Orin Nano Super as self-hosted GHA runner for native arm64 builds? (~3 min vs ~25 min QEMU) | Leaning yes — confirm when hardware is in hand. |
| 3 | R3 cheaper bot platform: finalize specific model at R2 design time. Budget ~$400–500/unit. RPi 5 + base rover + RPLIDAR A1 is the leading option. | TBD at R2 design time. |
| 4 | Long-term open-source release strategy (scope and timing) | TBA — revisit at r2-complete. |
| 5 | R3 basketball court demo: define precise success criteria for collective ArUco identification mission (coverage %, latency spec for WiFi offload) | TBD at R2 design time. |
| 6 | Capability-gated requirements in `check_traceability.py`: requirements like "Nav2 BT returns SUCCESS" only apply when `robot_profiles/*.yaml` declares `nav_stack: nav2_full`. R1 assumes full Nav2 on Jetson — but if a lightweight compute platform (e.g. Arduino UNO Q, microprocessor+microcontroller single chip, no GPU, limited RAM) is added as a target, the traceability gate must filter requirements against the profile before checking coverage. Do NOT hardcode Nav2/SLAM assumptions into the gate in R1 — keep the profile-requirement binding loose enough to add lightweight tiers in R2/R3 without a rewrite. | Design constraint for R1 — no decision needed yet, but must not be designed around. |

---

## Decisions Log

| Date | Decision |
|---|---|
| 2026-06-17 | Fresh start: new repo, not a copy of the Jetbot project |
| 2026-06-17 | Ubuntu 24.04 dual boot bare metal before any project code |
| 2026-06-17 | `drift_config.yaml` for thresholds from day one (data, not hardcode) |
| 2026-06-17 | `check_traceability.py` with zero rover-specific logic, CLI args only |
| 2026-06-17 | Lean Claude API + prompt caching over agent frameworks |
| 2026-06-19 | Repo name: `autonomous-fleet-testbed` |
| 2026-06-19 | R1/R2/R3 release structure adopted (replaces v1/v2) |
| 2026-06-19 | Hardware (Waveshare UGV PT) purchased before R1 closes |
| 2026-06-19 | Stage 6 is a real R1 deliverable, not a placeholder |
| 2026-06-19 | ROS2 `/robot_001/` namespace from day one, even with single robot |
| 2026-06-19 | `robot_type` field in run report schema from day one |
| 2026-06-19 | `robot_profiles/` directory from R1 (one profile, expandable in R3) |
| 2026-06-19 | Private through r2-complete; open-source strategy revisited at that tag |
| 2026-06-19 | R3 = heterogeneous fleet, any robot type, capability profiles per type |
| 2026-06-19 | R3 WiFi offloading: central perception node on Jetson for GPU-less bots via ROS2 DDS over WiFi |
| 2026-06-19 | R1 scenario: bedroom carpet coverage patrol, colored balls (red=STOP, yellow=DETOUR) + ArUco markers |
| 2026-06-19 | Detection stack: YOLO for colored balls + OpenCV ArUco (`cv2.aruco`) for markers, running simultaneously |
| 2026-06-19 | R2 sim environment: backyard basketball court (half-court ~14m × 15m, concrete surface, outdoor variables) |
| 2026-06-19 | R3 fleet strategy: Option B — heterogeneous (1 Jetson flagship from R1 + 2 cheaper RPi bots ~$400–500 each) |
| 2026-06-19 | R3 estimated total hardware: ~$950 (R1) + ~$800–1000 (2 cheaper bots) = ~$1,750–1,950 |
| 2026-06-19 | Baseline-first CI strategy: run Stage 2 on QEMU first, capture timing, then upgrade to Jetson runner and measure delta |
| 2026-06-19 | `stage_timings_sec` and `runner_type` added to run report schema from day one |
| 2026-06-19 | Git tags `ci-qemu-baseline` and `ci-jetson-upgrade` mark the before/after timing milestone |
| 2026-06-19 | CI timing drift tracked as `warn` (not fail) — slow builds are a signal, not a blocker |
| 2026-06-19 | Jetson Orin Nano Super Dev Kit purchased as standalone desk CI runner; rover uses separate Jetson module |

---

## Reference Files

Active references — consult during R1 implementation for version-specific detail not reproduced in this brief.

| File | Purpose |
|---|---|
| `G:\BC\rover_cicd_architecture.html` | Interactive 6-stage pipeline diagram — click nodes for full config details |
| `G:\BC\ros2_rover_cicd_guide.pdf` | Full 6-stage pipeline guide — JetPack 7.2 / apt packages / exact version pins |


