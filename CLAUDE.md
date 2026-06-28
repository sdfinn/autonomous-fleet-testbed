# autonomous-fleet-testbed — Claude Code Context

## Project
Open-source CI/CD-native fleet simulation testing framework for autonomous robots.
Master strategic brief: BLUEPRINT.md (working doc — vision, roadmap, decisions).
robotics_cicd_10x_blueprint.md is reference-only source dialogue, not for coding.
Execute from Release1Todo.md (session plans); code from .superpowers/sdd/ specs.

## Development workflow — tier 1 first

**Primary dev loop (x86 bare metal — use this to flush bugs before touching CI):**
```bash
colcon build --symlink-install          # ~1s — build the ROS2 package
source install/setup.bash
python -m pytest tests/ -v \
  --ignore=tests/test_ros2_contracts.py # seconds — run Python unit tests
ros2 launch nav_fleet sim_launch.py    # Session 09+ — Gazebo + Nav2 locally
# nav_runner, metrics_collector, drift check all run here
```

x86 is not the robot's target OS but finds 90% of bugs at ~1s build vs 23 min QEMU.
Commit to CI only when the x86 pipeline is clean. See BLUEPRINT.md "Tiered development loop."

## Environment
- Ubuntu 24.04 bare metal (dual boot with Windows 11)
- ROS2 Jazzy + Gazebo Harmonic + CycloneDDS
- Python virtualenv: ~/fleet-env (activate before running Python tools)
- Colcon workspace: ~/autonomous-fleet-testbed/ (build from here)

## Key Commands
```bash
# Full local pipeline (Tier 1 — primary dev loop)
source ~/fleet-env/bin/activate
colcon build --symlink-install && source install/setup.bash
python -m pytest tests/ -v --ignore=tests/test_ros2_contracts.py
ros2 launch nav_fleet sim_launch.py    # Session 09+

# Traceability gate
python tools/check_traceability.py requirements/traceability.yaml tests/ \
  --profile robot_profiles/jetson_ugv_pt.yaml

# Dashboard
streamlit run dashboard/app.py

# arm64 Docker build (Tier 2 — only after Tier 1 is clean)
docker buildx build --platform linux/arm64 \
  --tag ghcr.io/sdfinn/autonomous-fleet-testbed:latest --load .
```

## Directory Layout
- `src/nav_fleet/`  — ROS2 colcon package (nav runner, metrics collector)
- `tools/`          — Python utilities (baseline monitor, telemetry logger, etc.)
- `tests/`          — pytest test suite
- `config/`         — nav2_params.yaml, drift_config.yaml
- `worlds/`         — Gazebo SDF world files
- `urdf/`           — Robot URDF/xacro files
- `robot_profiles/` — Per-robot capability YAML
- `requirements/`   — Traceability matrix and requirement specs
- `reports/history/`— CI run JSON reports (drift detection reads from here)
- `.github/workflows/ci.yml` — 6-stage CI pipeline

## Gotchas
- Always `source install/setup.bash` after colcon build
- RMW_IMPLEMENTATION=rmw_cyclonedds_cpp must be set (in .bashrc)
- Gazebo Harmonic command is `gz sim`, NOT `ign gazebo`
- URDF topics must use /robot_001/ namespace
- Isaac Sim session (Session 12): requires NVIDIA driver 570+ for RTX 5080
- `requirements.txt` is a full pip freeze of the local ROS2 venv — NOT for CI use. Use `requirements-ci.txt` in CI jobs.
- DB path env var is `FLEET_DB` (default: `reports/fleet_runs.db`) — used by telemetry_logger, validate_telemetry, ai_test_generator, dashboard
- `tests/test_ros2_contracts.py` requires a live ROS2 environment — always `--ignore` it in local pytest runs
