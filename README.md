# autonomous-fleet-testbed

![CI](https://github.com/sdfinn/autonomous-fleet-testbed/actions/workflows/ci.yml/badge.svg)

A CI/CD-native simulation testing framework for autonomous robots. Every push runs a
robot through requirements gates, simulated navigation missions in Gazebo, a native
arm64 build, and a hardware-in-the-loop stage on a real Jetson — with telemetry,
photo evidence, and statistical drift detection on the results. Sim-first: bugs are
flushed on a workstation in seconds, not on a robot in the field.

| The simulated world (a real, measured bedroom) | What the robot saw (CI run, real Jetson) |
|---|---|
| ![Gazebo bedroom world](docs/img/gazebo_bedroom_world.png) | ![Mission 2 red-ball reaction photo](docs/img/mission2_reaction_red.png) |

## Architecture

```mermaid
flowchart TD
    T["push to main / PR"] --> S0["Stage 0\ntraceability gate"]
    S0 --> S1["Stage 1\nlint + unit tests"]
    S1 --> S2["Stage 2\nGazebo sim nav tests\n(x86 GPU runner)"]
    S2 --> S3["Stage 3\nnative arm64 build\n(Jetson runner)"]
    S3 --> S4["Stage 4\nhardware-in-the-loop\nMission 2 day (real Jetson)"]
    S2 --> S5a["Stage 5\nworkstation reports"]
    S4 --> S5b["Stage 5\nHIL reports"]
    S4 -.-> S6["Stage 6\nreal-robot deploy\n(future)"]
```

Full clickable version — every stage and node explained with the real commands behind
it: [`docs/architecture.html`](docs/architecture.html) *(open locally in a browser;
GitHub renders it as source)*.

## Quickstart (everything already installed)

From the repo root, in a terminal with the environment set up (see below):

```bash
colcon build --symlink-install          # ~1 s
source install/setup.bash

# Unit tests (the live-ROS test files are excluded — they need the sim running)
python -m pytest tests/ -v \
  --ignore=tests/test_ros2_contracts.py --ignore=tests/test_navigation.py \
  --ignore=tests/test_mission_run.py --ignore=tests/test_mission2.py \
  --ignore=tests/test_nav_runner.py

# Launch the sim (Gazebo headless + Nav2). Wait for "Managed nodes are active".
ros2 launch src/nav_fleet/launch/sim_launch.py headless:=true

# In a second terminal: run Mission 1 (navigate → photograph → return)
python -m nav_fleet.mission_runner mission1
# → per-waypoint checklist prints; the photo lands in reports/photos/

# Telemetry dashboard
streamlit run dashboard/app.py
```

To watch the sim, open the viewer alongside the headless server: `gz sim -g`.
(Viewer navigation cheatsheet: [`GazeboCommands.md`](GazeboCommands.md).)

## Setup from scratch (one Ubuntu machine, no robot needed)

The entire sim pipeline runs on a single Ubuntu workstation. The Jetson/HIL tier is
optional extra hardware — see "Going further".

1. **Ubuntu 24.04** (bare metal recommended; the sim renders headless without a GPU,
   a discrete GPU just makes it faster).
2. **ROS2 Jazzy** — follow the
   [official install guide](https://docs.ros.org/en/jazzy/Installation/Ubuntu-Install-Debs.html),
   then the packages this project needs:
   ```bash
   sudo apt install ros-jazzy-desktop ros-jazzy-ros-gz \
     ros-jazzy-navigation2 ros-jazzy-nav2-bringup \
     ros-jazzy-rmw-cyclonedds-cpp ros-jazzy-robot-localization \
     ros-jazzy-vision-msgs python3-colcon-common-extensions
   ```
   *You should see:* `gz sim --version` reports Gazebo Harmonic.
3. **Python environment**:
   ```bash
   python3 -m venv ~/fleet-env && source ~/fleet-env/bin/activate
   pip install -r requirements-ci.txt
   ```
   (`requirements-ci.txt` is the curated dependency set; `requirements.txt` is a full
   local freeze — don't install that one.)
4. **Environment** — add to `~/.bashrc` or run per terminal:
   ```bash
   source /opt/ros/jazzy/setup.bash
   export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
   export ROS_LOCALHOST_ONLY=1   # single-machine setup: keep DDS on loopback
   ```
   *(All processes must agree on `ROS_LOCALHOST_ONLY` — set it everywhere or nowhere.
   Remove it if you later add a second machine.)*
5. **Clone, build, verify**:
   ```bash
   git clone https://github.com/sdfinn/autonomous-fleet-testbed.git
   cd autonomous-fleet-testbed
   colcon build --symlink-install && source install/setup.bash
   python -m pytest tests/ -v --ignore=tests/test_ros2_contracts.py \
     --ignore=tests/test_navigation.py --ignore=tests/test_mission_run.py \
     --ignore=tests/test_mission2.py --ignore=tests/test_nav_runner.py
   ```
   *You should see:* the build finishes in ~1 s and all unit tests pass.
6. **First mission** — run the Quickstart above. *You should see:* Nav2 reach
   "Managed nodes are active", the mission print a five-step checklist ending in
   `Mission mission1: PASS`, and a photo of the simulated bedroom in `reports/photos/`.

## What the CI expects

The full pipeline assumes two self-hosted runners: an x86 workstation with a GPU
(labels `self-hosted, x86, gpu, rtx5080`) for the sim stages, and a Jetson Orin Nano
(`self-hosted`, arm64) for the native build — plus the Jetson being reachable over
SSH for the HIL stage. **Stages 0–1 run on GitHub-hosted runners**, so a fork gets
the requirements gate and quality gate working with zero setup; stages 2–5 need the
hardware. Runs are serialized via a concurrency group because the runners are
physical, shared machines.

## Going further

- **Jetson / hardware-in-the-loop tier** — flash, provision, and register a Jetson
  Orin Nano: [`docs/runbooks/JetsonInstallSession14.md`](docs/runbooks/JetsonInstallSession14.md)
- **Mission 1 HIL runbook (manual procedure + first real run)** —
  [`docs/runbooks/Mission1HILSession15.md`](docs/runbooks/Mission1HILSession15.md)
- **Roadmap and session plans** — [`Release1Todo.md`](Release1Todo.md) (living doc)
- **Strategy background + decisions log** — [`BLUEPRINT.md`](BLUEPRINT.md)
- **Gazebo viewer cheatsheet** — [`GazeboCommands.md`](GazeboCommands.md)

## Repo map

| Path | What it is |
|---|---|
| `src/nav_fleet/` | ROS2 package: launch files, URDF, worlds, Nav2 config, mission runner, ball detector |
| `tools/` | CLI utilities: traceability gate, telemetry, drift detection, HIL day orchestrator, agentic loop |
| `tests/` | pytest suite — unit tier plus live sim/HIL integration tiers |
| `requirements/` | Requirement specs + traceability matrix (`traceability.yaml`) |
| `config/` | Drift thresholds (`drift_config.yaml`) — thresholds are data, never code |
| `robot_profiles/` | Per-robot capability YAML (drives requirement skips) |
| `dashboard/` | Streamlit telemetry dashboard |
| `scripts/` | `hil_stage.sh` — the whole HIL stage, runnable locally or from CI |
| `reports/` | Telemetry DB (`fleet_runs.db`), generated reports, mission photos |
| `.github/workflows/ci.yml` | The 6-stage pipeline (see architecture above) |
