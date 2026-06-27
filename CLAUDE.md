  # autonomous-fleet-testbed — Claude Code Context

  ## Project
  Open-source CI/CD-native fleet simulation testing framework for autonomous robots.
  Master brief: see BLUEPRINT.md in this repo (or G:\BC\MasterBrief.md on Windows).

  ## Environment
  - Ubuntu 24.04 bare metal (dual boot with Windows 11)
  - ROS2 Jazzy + Gazebo Harmonic + CycloneDDS
  - Python virtualenv: ~/fleet-env (activate before running Python tools)
  - Colcon workspace: ~/autonomous-fleet-testbed/ (build from here)

  ## Key Commands
  ```bash
  # Build ROS2 package
  cd ~/autonomous-fleet-testbed
  colcon build --symlink-install
  source install/setup.bash

  # Run Python tests (activate venv first)
  source ~/fleet-env/bin/activate
  python -m pytest tests/ -v --ignore=tests/test_ros2_contracts.py

  # Run traceability gate
  python tools/check_traceability.py requirements/traceability.yaml tests/ --profile robot_profiles/jetson_ugv_pt.yaml

  # Launch Gazebo world (Session 09+)
  ros2 launch nav_fleet sim_launch.py

  # Dashboard
  streamlit run dashboard/app.py
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
