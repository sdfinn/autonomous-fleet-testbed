#!/usr/bin/env bash
# Tier-1 gate in one prompt-friendly command: build + unit suite (+ optional flake8 targets).
# Exists so interactive sessions don't chain `source` inline (permission-heuristic noise).
cd "$(dirname "$0")/.."
# NOTE: no `set -u` before the ROS sources — setup.bash reads unset vars (Task 7 gotcha).
source /opt/ros/jazzy/setup.bash 2>/dev/null
set -o pipefail
colcon build --symlink-install --packages-select nav_fleet 2>&1 | tail -1
source install/setup.bash 2>/dev/null
python -m pytest tests/ -q \
  --ignore=tests/test_ros2_contracts.py --ignore=tests/test_navigation.py \
  --ignore=tests/test_mission_run.py --ignore=tests/test_mission2.py 2>&1 | tail -3
