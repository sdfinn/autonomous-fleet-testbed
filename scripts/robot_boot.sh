#!/bin/bash
# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
#
# Boot-time entry point for the real, deployed Waveshare UGV-PT (RealRobotStartup.md
# Part A). Brings up Nav2/EKF/ball_detector bare — matching scripts/hil_stage.sh's
# nav2_up() exactly, same launch pattern, same env vars, same DDS regen step — then
# runs one mission2 day (no_ball -> yellow -> red) with a human placing/swapping the
# ball (tools.mission2_day --ball-ops operator: no prompting, no delays, the operator
# watches the robot and acts unprompted — see tools/mission2_day.py's OperatorBallOps
# docstring).
#
# Deliberately bare-metal end to end, NOT the Docker image (see
# docs/bare-metal-vs-container-decision.md for the full reasoning): the container role
# proven by HIL only ever wraps the raw `mission_runner.py --day` ROS2 loop, never
# tools/mission2_day.py's judging/telemetry/VLM-canary logic — running the container
# here would mean the mission runs but nothing gets judged or logged. Get the exact
# HIL-tested commit onto this checkout with `scripts/hil_stage.sh sync <sha>` BEFORE
# relying on this script (see RealRobotStartup.md Part A) — this script always runs
# whatever is currently checked out and built here, same as nav2_up() always has.
#
# NOT yet exercised by CI/HIL — a power cycle can't be simulated there. Run this
# manually over SSH first and confirm a full mission2 day passes with your own eyes-on
# check before trusting the systemd unit (scripts/robot-mission.service) that calls it
# automatically at boot.
set -euo pipefail

REPO="$HOME/autonomous-fleet-testbed"
LOG_DIR="$HOME/fleet-ci-data/robot_boot_logs"
mkdir -p "$LOG_DIR"
TS=$(date +%Y%m%dT%H%M%S)
NAV2_LOG="$LOG_DIR/nav2_${TS}.log"

cd "$REPO"

echo "=== [robot-boot] regenerating CycloneDDS interface config ==="
# Same script, same reasoning as nav2_up() (scripts/hil_stage.sh): a statically listed
# down interface makes CycloneDDS hard-fail outright, not fall back gracefully. This
# makes Nav2 come up correctly whichever interface (WiFi, here) happens to be up at
# boot, with no manual step needed.
bash scripts/regen_cyclonedds_config.sh

echo "=== [robot-boot] launching Nav2 + EKF + ball_detector (bare — matches nav2_up()) ==="
source /opt/ros/jazzy/setup.bash
source "$REPO/install/setup.bash"
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export ROS_DOMAIN_ID=0
export CYCLONEDDS_URI="file://$HOME/cyclonedds-hil.xml"
# Same (subshell) + < /dev/null pattern nav2_up() uses and documents: without the
# parens, `&` binds the whole preceding &&-chain, and the backgrounded job inherits
# this script's own stdout/stderr, holding the boot service "running" forever instead
# of handing off to the launched process. < /dev/null stops it inheriting stdin.
rm -f "$NAV2_LOG"
(nohup ros2 launch nav_fleet robot_launch.py > "$NAV2_LOG" 2>&1 < /dev/null &)

echo "=== [robot-boot] waiting up to 120s for Nav2 to report active ==="
deadline=$((SECONDS + 120))
count=0
until [ "$count" -ge 2 ]; do
  if (( SECONDS >= deadline )); then
    echo "FATAL: Nav2 not active within 120s — see $NAV2_LOG" >&2
    tail -n 40 "$NAV2_LOG" >&2 || true
    exit 1
  fi
  sleep 3
  count=$(grep -c 'Managed nodes are active' "$NAV2_LOG" 2>/dev/null || echo 0)
done
echo "=== [robot-boot] Nav2 active — starting mission2 day (operator ball placement) ==="

# RUNNER_TYPE=real_robot matches the convention every other real-robot telemetry row in
# this project already uses (tests/test_navigation.py's own invocation, pre-mission2-
# target). --no-launch: Nav2 is already up (above), don't have this tool try to launch
# a sim stack. --hold-s 10: hold in place after the red leg so it's visually obvious
# the day is done, not mid-frame.
RUNNER_TYPE=real_robot python -m tools.mission2_day \
  --ball-ops operator --no-launch --hold-s 10 \
  --log "$LOG_DIR/mission2_day_${TS}.log"
