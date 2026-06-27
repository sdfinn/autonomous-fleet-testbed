# autonomous-fleet-testbed — Full Pipeline Architecture Design

**Date:** 2026-06-27
**Status:** Approved
**Scope:** Full system architecture — all releases, all layers. Produced before Session 06 to give every subsequent session a north star.

---

## The Project in One Sentence

A portfolio-ready CI/CD pipeline that doesn't just test robot software, but continuously validates, simulates, and improves the intelligence of autonomous robot fleets — from a single robot navigating a room to a coordinated fleet executing autonomous missions. Designed to be open-sourceable as a framework product, on the owner's timeline.

---

## Two Products

This project produces two complementary, independently-demoable products.

### Product 1: Fleet CI/CD Pipeline Framework

> *"How do you know your robot software works before you deploy it to hardware?"*

A robot-agnostic CI/CD pipeline built on open-source tools (ROS2, Gazebo, GitHub Actions, Docker, pytest). Designed so any ROS2 team could adopt it — with the option to open-source it as a product on the owner's timeline. The value is the infrastructure: requirements traceability, drift detection, simulation gates, hardware deployment, and automated reports.

Lives in: `tools/`, `.github/workflows/`, `requirements/`, `reports/`

### Product 2: AI Autonomous Mission Planner

> *"How do you tell a fleet of robots what to do — and how do you prove they can actually do it?"*

An intelligence layer that starts as scripted missions in Release 1 and evolves into an AI that designs its own missions, coordinates multi-robot teams, and generates the scenarios that prove the software is robust. Independently demoable — a Jetson and two cheap robots executing a mission they've never been given before.

Lives in: `src/nav_fleet/` (Release 1), future `mission_planner/` module (Release 2+)

### How They Relate

```
┌─────────────────────────────┐     ┌─────────────────────────────┐
│   Product 2: Mission        │     │   Product 1: CI/CD Pipeline │
│   Planner                   │     │   Framework                 │
│                             │     │                             │
│  - mission definitions      │◄────│  Validates that the mission │
│  - robot coordination       │     │  planner software works     │
│  - AI scenario generation   │     │  before deploying to        │
│  - world generation         │────►│  real hardware              │
└─────────────────────────────┘     └─────────────────────────────┘
         what gets tested                   what does the testing
```

The pipeline validates the mission planner. The mission planner generates the scenarios the pipeline tests. They feed each other.

---

## Career Context

*(Private repo — remove before going public)*

This project applies years of CI/CD, test automation, and release management expertise from call center software to autonomous robotics. The selling point is not deep expertise in any single technology, but the ability to integrate complex systems — ROS2, Gazebo, Isaac Sim, GitHub Actions, Docker, Claude AI — into a disciplined, production-grade pipeline.

Target outcomes: industry transfer into robotics, or founding a business around the open-source framework and/or the AI mission planner as commercial products.

---

## Three-Layer Architecture

```
┌─────────────────────────────────────────────────────┐
│  Layer 3: Intelligence  (Release 2 → Release 3)     │
│  AI mission generation, multi-robot coordination,   │
│  autonomous test design, parallel sim runs          │
├─────────────────────────────────────────────────────┤
│  Layer 2: Validation  (Release 1 → )                │
│  Drift detection, behavioral regression,            │
│  sim-to-real comparison, reports, dashboard         │
├─────────────────────────────────────────────────────┤
│  Layer 1: Pipeline  (Release 1 — current focus)     │
│  6-stage CI/CD gate: requirements → code quality →  │
│  arm64 build → Gazebo sim → perception → deploy     │
└─────────────────────────────────────────────────────┘
```

Each layer is independently demonstrable. The showcase moments map to layers becoming operational.

---

## Release Roadmap

| Release | Robot Composition | Mission Style | Intelligence |
|---|---|---|---|
| R1 (current) | 1 Jetson Orin Nano (sim + real) | Scripted: navigate, sweep, stop/avoid | Drift detection + AI test generation |
| R2 | 1 Jetson + 1–2 cheaper robots (RPi / Arduino UNO Q) | Semi-structured: coordinated search | Multi-robot coordination |
| R3A | Add drone | Autonomous, minimal hardcoding | Aerial + ground coordination |
| R3B | Any fleet | Fully autonomous: "find the red ball" | AI-defined missions, parallel sim runs |

### Showcase Moments

1. **Moment 1 (R1):** Single Jetson robot — simulation and real hardware performing the same mission. Drift detection demonstrated live. 1–2 minute video that gives a taste without revealing code.
2. **Moment 2 (R2):** 1 smart robot + 1–2 cheap robots completing a coordinated mission. Sim + real.
3. **Moment 3A (R3A):** Drone added, more autonomous mission. Simulation first, real hardware to follow.
4. **Moment 3B (R3B):** "Brains demo" — the AI-driven pipeline generating its own missions, running parallel simulations, finding bugs autonomously.

### Hardware Progression (Phase A → C)

| Phase | What runs | Stage 2 build time | Story |
|---|---|---|---|
| A (now) | QEMU on x86 workstation | ~25–30 min | Baseline — no hardware needed |
| B1 | Docker on Jetson Dev Kit (native arm64) | ~5–8 min | "Same container, real hardware, 4–5× faster" |
| B2 | Native bare metal on Jetson (no Docker) | ~2–3 min | "No overhead — this is what ships" |
| C | Jetson in Waveshare UGV PT rover (wifi/direct) | Same as B2 | "Same binary, deployed to the field" |

*Note: The Jetson Orin Nano is a module that can be moved between carrier boards (dev kit → rover). A second module allows simultaneous CI runner + field robot. Decision deferred.*

---

## The 6-Stage CI/CD Pipeline

Stages run in sequence. Each gates the next. Cheap fast gates protect expensive slow ones — this is shift left applied to the pipeline structure itself.

```
Push to main
     │
     ▼
┌─────────────┐
│   Stage 0   │  Requirements Gate
│  ~5 sec     │  check_traceability.py — every requirement ID must
│             │  have a matching test. Bidirectional (orphan warnings).
│             │  Robot-profile aware via skip_requirements.
└──────┬──────┘
       │ pass
       ▼
┌─────────────┐
│   Stage 1   │  Code Quality Gate
│  ~60 sec    │  flake8 lint + pep257 + pytest unit tests
│             │  (tools/ and tests/ — no ROS2 environment needed)
└──────┬──────┘
       │ pass
       ▼
┌─────────────┐
│   Stage 2   │  arm64 Cross-Compile
│  ~25 min    │  Docker buildx builds linux/arm64 image via QEMU.
│  (Phase A)  │  Proves nav_fleet package builds for Jetson target.
│             │  Pushes image to ghcr.io. Shrinks to ~3 min in Phase B.
└──────┬──────┘
       │ pass
       ▼
┌─────────────┐
│   Stage 3   │  Simulation Gate (Gazebo Harmonic)
│  ~5 min     │  Robot spawns in bedroom world. Nav2 navigates to goal.
│             │  Asserts: position error < 0.15m, zero collisions,
│             │  odom/lidar/camera Hz requirements met.
│             │  Drift detector runs against run history.
└──────┬──────┘
       │ pass
       ▼
┌─────────────┐
│   Stage 4   │  Perception Gate (Isaac Sim + RTX 5080)
│  ~10 min    │  Self-hosted runner on workstation.
│             │  YOLO detection mAP on simulated camera feed.
│             │  Validates GPU-accelerated perception pipeline.
└──────┬──────┘
       │ pass
       ▼
┌─────────────┐
│   Stage 5   │  Reports + Artifacts
│  ~30 sec    │  telemetry_logger.py → reports/history/<run_id>.json
│             │  generate_test_report.py → PDF artifact
│             │  Dashboard data refreshed. AI diagnosis generated.
│             │  Artifacts uploaded to GitHub Actions.
└──────┬──────┘
       │ pass (Phase C only)
       ▼
┌─────────────┐
│   Stage 6   │  Real Hardware Deploy
│  ~5 min     │  SSH deploy to Jetson. ros2 launch robot_launch.py.
│             │  Smoke test: topic Hz assertions.
│             │  Auto-rollback on failure.
│             │  sim_vs_real_comparison.py validates correlation ≥ 70%.
└─────────────┘
```

### Stage Artifacts

| Stage | Output |
|---|---|
| 0 | `reports/traceability_latest.json` (stdout → redirect) |
| 1 | Clean lint status, passing unit test results |
| 2 | `ghcr.io/sdfinn/autonomous-fleet-testbed:<sha>` Docker image |
| 3 | `reports/history/<run_id>.json` (nav + drift metrics) |
| 4 | `reports/history/<run_id>.json` (appended: perception metrics) |
| 5 | `reports/<run_id>.pdf`, dashboard data, GHA summary annotation |
| 6 | Deployment confirmation, sim-to-real comparison report |

### Local Testing vs. Self-Hosted Runners

**Two different concepts — often confused:**

- **Local script execution (primary approach):** Because all heavy logic lives in `tools/` Python scripts and the YAML just calls them (`python tools/check_traceability.py ...`), you can test every tool by running it directly in the terminal. No special tooling needed. This is the recommended first line of local testing.

- **`act` (https://github.com/nektos/act):** A local emulator that reads your `.github/workflows/` YAML and runs it in Docker on your machine. GitHub never sees it. Useful when you're debugging the workflow YAML structure itself — job dependencies, env variable injection, `needs:` ordering. Not needed for testing the Python logic inside the steps.

- **Self-hosted runner (official GitHub agent):** Software you register to your repo on GitHub. GitHub orchestrates the workflow on their servers and tells your machine to execute the steps. Requires internet connection to GitHub. Used in this project for stages that need specific hardware:

| Stage | Runner type | Label |
|---|---|---|
| 0–3 | GitHub-hosted (cloud) | `ubuntu-latest` |
| 4 | Self-hosted on workstation | `[self-hosted, rtx5080]` |
| 6 | Self-hosted on Jetson | `[self-hosted, arm64, jetson]` |

---

## Data Flow

```
                    ┌──────────────────────────────────┐
                    │        traceability.yaml          │
                    │  (requirements + descriptions)    │
                    └───────────────┬──────────────────┘
                                    │
                                    ▼
git push ──► Stage 0: check_traceability.py
                        │
                        └──► reports/traceability_latest.json
                                        │
                                        ▼
            Stage 1: lint + unit tests  │
                        │               │
                        ▼               │
            Stage 2: docker buildx      │
                        │               │
                        └──► ghcr.io/<sha> image
                                        │
                                        ▼
            Stage 3: Gazebo sim ────────┘
                        │
                        └──► reports/history/<run_id>.json
                                   │
                             ┌─────┴───────┐
                             ▼             ▼
                        Stage 4:     baseline_monitor.py
                        Isaac Sim    (drift detection:
                             │        reads last N runs,
                             │        compares to drift_config.yaml)
                             │             │
                             └──────┬──────┘
                                    ▼
                              Stage 5: Reports
                                    │
                       ┌────────────┼────────────┐
                       ▼            ▼             ▼
                  PDF report    dashboard     GHA summary
                               (SQLite +      annotation
                               Streamlit)
                                    │
                                    ▼
                              Stage 6: Deploy
                                    │
                              sim_vs_real_comparison.py
```

### The Central Artifact: `reports/history/<run_id>.json`

The canonical run record. Schema (enforced by `validate_telemetry.py` via Pandera):

```json
{
  "run_id": "abc123",
  "timestamp": "2026-06-27T14:00:00Z",
  "robot_type": "jetson_ugv_pt",
  "runner_type": "qemu",
  "stage_timings_sec": {"stage_2": 1620, "stage_3": 287},
  "nav_success_rate": 1.0,
  "mean_position_error": 0.08,
  "mean_time_to_goal": 14.2,
  "collision_rate": 0.0,
  "odom_hz_mean": 51.3,
  "lidar_hz_mean": 10.4,
  "camera_hz_mean": 10.1,
  "firmware_test_pass_rate": 1.0,
  "perception_map_score": 0.87
}
```

`validate_telemetry.py` is the gatekeeper — a malformed run JSON never propagates downstream.

---

## Tool Ecosystem

```
tools/
├── check_traceability.py    ← Session 06 (designing now)
├── baseline_monitor.py      ← Migrated; logging upgrade pending
├── telemetry_logger.py      ← Migrated; schema current
├── validate_telemetry.py    ← Migrated; Pandera schema gatekeeper
├── generate_test_report.py  ← Migrated; PDF via ReportLab
├── ai_test_generator.py     ← Migrated; Claude API scenario generation
├── scenario_analyzer.py     ← Migrated; scores coverage scenarios
└── sim_vs_real_comparison.py ← Migrated; Phase C sim-to-real delta
```

| Tool | Role | Stage |
|---|---|---|
| `check_traceability.py` | Requirements coverage gate | 0 |
| `validate_telemetry.py` | Schema enforcement gatekeeper | 3, 4 |
| `telemetry_logger.py` | Writes canonical run record | 3, 4 |
| `baseline_monitor.py` | Drift detection across history | 3, 4 |
| `generate_test_report.py` | PDF artifact generation | 5 |
| `ai_test_generator.py` | AI scenario generation from drift signals | 5 (now), 3 (future) |
| `scenario_analyzer.py` | Scores test coverage quality | 1, 5 |
| `sim_vs_real_comparison.py` | Validates sim-to-real correlation ≥ 70% | 6 |

**Logging pattern:** All tools use Python's `logging` module. DEBUG level to stderr via `--debug` flag. INFO and above to stdout. Established in `check_traceability.py` (Session 06), retrofitted to migrated tools as they are worked on in subsequent sessions.

---

## AI / Intelligence Layer

### Component 1: AI Test Generation (Release 1, expanding)

`ai_test_generator.py` calls Claude API. Drift signals feed it as context, producing scenarios that specifically stress the drifting metric.

```
drift detected: mean_time_to_goal +18% over 10 runs
        │
        ▼
ai_test_generator.py
  context fed in: last 10 run JSONs + drift report + robot profile
  output: 3 new Gazebo scenarios targeting navigation time regression
        │
        ▼
new scenario definitions → added to test matrix → Stage 3 next run
```

This is active shift left: the pipeline notices patterns and generates tests automatically, rather than waiting for a human to notice and respond.

### Component 2: AI Drift Diagnosis (Release 1 / early Release 2)

Upgrades `baseline_monitor.py` output from a cold sigma alert to a human-readable diagnosis panel in the PDF report and dashboard:

> *"Navigation success rate has dropped 3.2 sigma over the last 8 runs. The timing correlates with PR #14 which changed obstacle avoidance parameters. Recommend reverting nav2_params.yaml: inflation_radius from 0.3 to 0.2."*

### Component 3: Autonomous Mission Planning (Release 3)

The system designs its own missions to stress-test the software — no human-authored scenario required.

```
AI analyzes: robot capabilities + historical failure modes + environment
        │
        ▼
Generates: mission definition YAML + matching Gazebo world SDF
        │
        ▼
Runs: parallel simulation instances across scenario variations
      (friction, lighting, obstacle placement, map complexity)
        │
        ▼
Reports: which variations caused failures → feeds next generation
```

This is the RAG element: each generation retrieves the history of what scenarios found bugs and uses it to design better ones. The pipeline becomes self-improving.

### AI Evolution Across Releases

```
R1: drift signal ──► AI generates targeted test scenario  (reactive)
R2: drift signal ──► AI diagnoses + generates + coordinates multi-robot test
R3: no trigger   ──► AI proactively designs missions to find unknown failures
```

### Test Creation Evolution

```
R1: pytest functions testing Python tool code
        │
        ▼
R1+:  AI-generated scenarios within existing Gazebo worlds
        │
        ▼
R2:   AI-generated scenarios with new objects added to existing worlds
        │
        ▼
R3:   AI-generated complete worlds + missions for stress testing
```

---

## Drift Detection

Behavioral regression over time — not just CI timing metrics but robot performance in the field:

- Mission completion time increasing
- Detection range shrinking (robot must get closer to identify targets)
- Navigation success rate declining over rolling window
- Sensor Hz dropping below spec

Mechanism: `baseline_monitor.py` reads the last N run JSONs, computes rolling statistics, compares against thresholds in `drift_config.yaml`. Sigma levels: info (2σ), warning (3σ), error (4σ), critical (5σ). Hard thresholds for binary metrics (firmware pass rate).

---

## Design Principles

**1. The pipeline is the product.**
Robot code is what gets tested. The pipeline is what is being built. Every tool, every stage, every config file should be designed as if another team will use it on their robot fleet.

**2. Data-driven, never hardcoded.**
Thresholds in `drift_config.yaml`. Requirements in `traceability.yaml`. Robot capabilities in `robot_profiles/`. Mission parameters in mission definition YAMLs. If a value should be configurable, it belongs in a config file.

**3. Robot-agnostic tools.**
No tool in `tools/` knows what a Waveshare UGV PT is. Tools accept profiles and configs as inputs. Adding a Raspberry Pi, Arduino UNO Q, or drone is a YAML change, not a Python change.

**4. Shift left relentlessly.**
Cheap fast gates first. Expensive slow ones later, protected by fast gates passing. AI-generated scenarios find bugs earlier. Schema validation at Stage 3 prevents bad data reaching Stage 5.

**5. Every tool is production-grade.**
Python `logging` module with `--debug` to stderr. Meaningful exit codes. `--help` that explains usage. JSON output mode for machine consumption. These are not polish — they are what separates a script from a tool.

**6. History is the memory.**
`reports/history/` is the dataset the AI learns from, the baseline drift is measured against, and sim-to-real is validated with. First-class data asset. Never truncate without a retention policy decision.

**7. Two clean separation lines.**
- `tools/` (pipeline) vs `src/nav_fleet/` + future `mission_planner/` (robot intelligence): different owners, different release cycles, different audiences.
- Sim vs real: every metric that matters is measured in both; `sim_vs_real_comparison.py` is the arbiter of sim trustworthiness.

**8. Tag milestones, don't just merge.**
`ci-qemu-baseline`, `ci-jetson-upgrade`, `r1-complete` are evidence that progress was real and measurable. They anchor the before/after narrative for the portfolio and the v1→v2 business story.

---

## Implications for Session 06

Now that the full architecture is established, Session 06 (`check_traceability.py`) should be designed with these specifics in mind:

- **JSON output schema** must be compatible with what Stage 5 (`generate_test_report.py`) will eventually consume — include `git_sha` (not `run_id` — Stage 0 fires before a simulation run exists), `timestamp`, `profile`, per-requirement status, orphans list, summary counts.
- **The `description` field** in `traceability.yaml` makes the tool self-documenting — no cross-referencing required.
- **`skip_requirements` in robot profiles** must be designed generically enough to work for Raspberry Pi, Arduino UNO Q, and drones without Python changes.
- **Fleet sweep mode** (`--profile-dir`) is deferred to Release 2 but the single-profile path should be written so it composes naturally into a sweep loop.
- **Logging pattern established here** becomes the template for all subsequent tools.

---

## Milestones and Tags

| Tag | Session | What it proves |
|---|---|---|
| `ci-qemu-baseline` | 11 | Stages 0–3 all green; QEMU build time recorded |
| `ci-jetson-upgrade` | 15 | Stage 2 on native Jetson; speedup documented |
| `r1-complete` | 16 | Sim-to-real correlation ≥ 70%; all 6 stages green |
| `v1.0-portfolio` | Post-16 | Clean public release; career commentary removed |
