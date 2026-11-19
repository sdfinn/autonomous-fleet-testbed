#!/bin/bash
# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
#
# Build the robot's own map, OFFLINE on the workstation, from a mapping-drive bag.
#
#   scripts/build_map_from_bag.sh <bag_dir> [out_prefix] [start_pose]
#
#     bag_dir     a bag recorded by scripts/robot_map_drive.sh (copied from the Jetson's
#                 ~/fleet-ci-data/map_drive_logs/)
#     out_prefix  default reports/maps/bedroom_real  ->  bedroom_real.yaml + .pgm
#     start_pose  "x,y,yaw_deg" of the spot where the drive began; default is the
#                 configured home pose, so start mapping drives on the home spot
#
# Then install it on the robot (it is deliberately NOT committed -- a floor plan of a
# real home in a public repo; robot_boot.sh picks it up from this location):
#
#   ssh mike@jetson.local 'mkdir -p ~/fleet-ci-data/maps'
#   scp <out_prefix>.yaml <out_prefix>.pgm mike@jetson.local:fleet-ci-data/maps/
#
# Takes about half the drive's length (the bag is played at 2x). Runs slam_toolbox in
# its own DDS domain, localhost only, so it cannot see or disturb a simulation, CI or
# the robot on this shared machine.
set -eo pipefail

BAG="${1:?usage: build_map_from_bag.sh <bag_dir> [out_prefix] [start_pose]}"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${2:-$REPO/reports/maps/bedroom_real}"
START_POSE="${3:-}"
[ -f "$BAG/metadata.yaml" ] || { echo "FATAL: $BAG is not a bag directory" >&2; exit 1; }
mkdir -p "$(dirname "$OUT")"

source /opt/ros/jazzy/setup.bash
export ROS_DOMAIN_ID="${MAP_BUILD_DOMAIN_ID:-88}" ROS_LOCALHOST_ONLY=1 \
  RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
unset CYCLONEDDS_URI
export PYTHONPATH="$REPO:${PYTHONPATH:-}"

SLAM_LOG="$OUT.slam.log"
SLAM_PID=""
cleanup() {
  # The launch is its own process group (set -m below): signal the whole group.
  if [ -n "$SLAM_PID" ] && kill -0 "$SLAM_PID" 2>/dev/null; then
    kill -INT -- "-$SLAM_PID" 2>/dev/null || true
    for _ in $(seq 50); do kill -0 "$SLAM_PID" 2>/dev/null || break; sleep 0.1; done
    kill -KILL -- "-$SLAM_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

echo "=== [build-map] starting slam_toolbox (log: $SLAM_LOG) ==="
set -m
ros2 launch slam_toolbox online_async_launch.py \
  slam_params_file:="$REPO/src/nav_fleet/config/slam_offline_params.yaml" \
  use_sim_time:=true > "$SLAM_LOG" 2>&1 < /dev/null &
SLAM_PID=$!
set +m
sleep 6
kill -0 "$SLAM_PID" 2>/dev/null || { echo "FATAL: slam_toolbox did not start -- see $SLAM_LOG" >&2; exit 1; }

echo "=== [build-map] feeding $BAG ==="
python3 "$REPO/tools/map_from_bag.py" "$BAG" ${START_POSE:+--start-pose "$START_POSE"}

echo "=== [build-map] saving the map to $OUT.{yaml,pgm} ==="
rm -f "$OUT.yaml" "$OUT.pgm"
timeout 40 ros2 run nav2_map_server map_saver_cli -f "$OUT" \
  --ros-args -p save_map_timeout:=10.0 > "$OUT.save.log" 2>&1 || true
if [ ! -s "$OUT.yaml" ] || [ ! -s "$OUT.pgm" ]; then
  echo "FATAL: no map was saved -- see $OUT.save.log and $SLAM_LOG" >&2
  exit 1
fi
echo "=== [build-map] done: $OUT.yaml ==="
