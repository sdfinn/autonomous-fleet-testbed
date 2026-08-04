#!/bin/bash
# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
#
# Unified "brain" entrypoint (docs/superpowers/specs/2026-08-03-docker-brain-
# real-robot-hil-unification-design.md) — the ONE thing this container does,
# identically whether it's HIL (workstation Gazebo simulates the robot's body)
# or the real robot (vendor drivers on bare metal ARE the body): launch
# nav2_only_launch.py (EKF + ball_detector + Nav2 bringup) with context-
# appropriate launch arguments, wait for it to report ready, run one mission2
# day, exit. One-shot — no long-lived container, no docker exec.
#
# Env vars the CALLER (tools/mission2_day.py's JetsonExecutor for HIL,
# scripts/robot_boot.sh for the real robot) must set via `docker run -e`:
#   USE_SIM_TIME       'true' (HIL) or 'false' (real robot)
#   HSV_CONFIG_FILE    filename under src/nav_fleet/config/
#                      (hsv_gazebo.yaml or hsv_realcam.yaml)
#   NAV2_MAP_FILE      filename under src/nav_fleet/maps/
#                      (living_room.yaml or bedroom_real.yaml)
# Optional:
#   MISSION2_SELF_REPORT=1   real-robot only — mission_runner.py --day logs its
#                            own self-reported PASS/FAIL per leg (no ground
#                            truth, no judging — that harness never runs in this
#                            container). HIL must NOT set this: the
#                            workstation's JetsonExecutor judges from the
#                            printed MISSION2_DAY_RESULT line instead.
#   RUNNER_TYPE, POWER_MODE  passed through to telemetry (unchanged convention)
#
# Must be run with `docker run --network host --ipc host` — shares the host's
# network namespace, which is what lets regen_cyclonedds_config.sh see the
# SAME real interfaces the host sees, and what lets Nav2 talk DDS to whatever
# peer this context needs (the workstation's Gazebo bridge for HIL, or nothing
# external at all for the real robot).
set -euo pipefail

source /opt/ros/jazzy/setup.bash
source /ros2_ws/install/setup.bash
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export ROS_DOMAIN_ID=0

# Fixed, non-$HOME path (the design's DDS-fix gap): a container's default $HOME
# is /root, not /home/mike — pinning this explicitly means the regenerated
# config always lands somewhere predictable regardless of which user the image
# runs as, and regen_cyclonedds_config.sh already supports this override
# (CYCLONEDDS_CONFIG_PATH env var).
export CYCLONEDDS_CONFIG_PATH=/ros2_ws/cyclonedds-container.xml
export CYCLONEDDS_URI="file://${CYCLONEDDS_CONFIG_PATH}"
bash /ros2_ws/scripts/regen_cyclonedds_config.sh

mkdir -p /ros2_ws/reports
NAV2_LOG="/ros2_ws/reports/nav2_container_$(date +%Y%m%dT%H%M%S).log"
rm -f "$NAV2_LOG"
# Same (subshell) + < /dev/null pattern hil_stage.sh's nav2_up()/robot_boot.sh
# both already use and document: without the parens the backgrounded job
# inherits this script's own stdout/stderr and holds the shell open forever;
# < /dev/null stops it inheriting stdin.
(nohup ros2 launch nav_fleet nav2_only_launch.py \
   use_sim_time:="${USE_SIM_TIME}" \
   hsv_config:="/ros2_ws/src/nav_fleet/config/${HSV_CONFIG_FILE}" \
   map:="/ros2_ws/src/nav_fleet/maps/${NAV2_MAP_FILE}" \
   > "$NAV2_LOG" 2>&1 < /dev/null &)

echo "=== [container-entrypoint] waiting up to 120s for Nav2 to report active ==="
deadline=$((SECONDS + 120))
until [ "${count:-0}" -ge 2 ]; do
  if (( SECONDS >= deadline )); then
    echo "FATAL: Nav2 not active within 120s — see $NAV2_LOG" >&2
    tail -n 40 "$NAV2_LOG" >&2 || true
    exit 1
  fi
  sleep 3
  count=$(grep -c 'Managed nodes are active' "$NAV2_LOG" 2>/dev/null || true)
  count="${count:-0}"
done
echo "=== [container-entrypoint] Nav2 active — starting mission2 day ==="

python3 -m nav_fleet.mission_runner --day
