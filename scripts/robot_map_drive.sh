#!/bin/bash
# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
#
# Mapping drive: start ONLY the bare-metal driver layer, record a bag, and hand the
# terminal to the hold-to-move keyboard teleop. No container, no Nav2, no EKF, no map.
#
#   ssh -t mike@<jetson> '~/autonomous-fleet-testbed/scripts/robot_map_drive.sh'
#
# The map itself is built afterwards, OFFLINE on the workstation, from the bag (wheel
# speed + gyro + scans are all it needs). Doing it offline means the drive never has to
# be repeated to try different mapping settings, and nothing new has to be installed or
# kept running on the robot. Bag: ~/fleet-ci-data/map_drive_logs/bag_<ts>/ (scans,
# wheel odometry, IMU, TF, commands; no camera -- the camera driver is not started).
#
# How to drive for a good map: slowly; one full lap of every room and the hallway,
# ending where you started (closing the loop lets the mapper cancel its drift); turn
# on the spot gently; stay BEHIND the robot or out of its sight so your legs are not
# mapped as furniture; keep doors in the position they will be in during missions.
#
# Stopping: x or Ctrl+C in the teleop. Losing the ssh session also stops everything
# (teleop dies with the terminal -> the driver's 200 ms watchdog zeroes the wheels,
# then this script's cleanup stops the recorder and the drivers).
set -euo pipefail

REPO="$HOME/autonomous-fleet-testbed"
# MAP_DRIVE_TELEOP lets a not-yet-synced copy of key_teleop.py be used.
TELEOP="${MAP_DRIVE_TELEOP:-$REPO/src/nav_fleet/nav_fleet/key_teleop.py}"
[ -f "$TELEOP" ] || { echo "FATAL: teleop script not found at $TELEOP" >&2; exit 1; }
[ -t 0 ] || { echo "FATAL: needs a terminal for the keyboard -- run it with 'ssh -t'" >&2; exit 1; }

LOG_DIR="$HOME/fleet-ci-data/map_drive_logs"
mkdir -p "$LOG_DIR"
TS=$(date +%Y%m%dT%H%M%S)

# Same environment robot_boot.sh sets up (non-interactive shells do not source .bashrc).
set +u
source /opt/ros/jazzy/setup.bash
set -u
# A node added since the last colcon build here has no launcher yet (see the script).
bash "$REPO/scripts/ensure_nav_fleet_built.sh" "$REPO"
set +u
source "$REPO/install/setup.bash"
[ -f "$HOME/ros2_drivers_ws/install/setup.bash" ] && source "$HOME/ros2_drivers_ws/install/setup.bash"
set -u
bash "$REPO/scripts/regen_cyclonedds_config.sh"
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp ROS_DOMAIN_ID=0 \
  CYCLONEDDS_URI="file://$HOME/cyclonedds-hil.xml"

BAG_PID=""
DRIVERS_PID=""

stop_job() {
  local name=$1 pid=$2 waited=0
  [ -n "$pid" ] || return 0
  kill -0 "$pid" 2>/dev/null || { wait "$pid" 2>/dev/null || true; return 0; }
  echo "=== [map-drive] stopping ${name} (pid ${pid}) ==="
  kill -INT "$pid" 2>/dev/null || true
  while kill -0 "$pid" 2>/dev/null; do
    if [ "$waited" -ge 150 ]; then
      echo "WARN: ${name} still running 15s after SIGINT -- killing it" >&2
      kill -KILL "$pid" 2>/dev/null || true
      break
    fi
    sleep 0.1
    waited=$((waited + 1))
  done
  wait "$pid" 2>/dev/null || true
}

cleanup() {
  trap '' INT TERM HUP
  # Recorder first (so the bag is finalized), then the drivers -- same order and
  # reason as robot_boot.sh.
  stop_job "the bag recorder" "$BAG_PID"
  stop_job "the bare-metal driver layer" "$DRIVERS_PID"
}
trap cleanup EXIT
trap 'echo "=== [map-drive] Ctrl+C ===" >&2; exit 130' INT
trap 'echo "=== [map-drive] SIGTERM ===" >&2; exit 143' TERM
trap 'echo "=== [map-drive] terminal lost (SIGHUP) ===" >&2; exit 129' HUP

BAG_DIR="$LOG_DIR/bag_${TS}"
BAG_LOG="$LOG_DIR/bag_${TS}.log"
DRIVERS_LOG="$LOG_DIR/drivers_${TS}.log"
echo "=== [map-drive] recording a bag to ${BAG_DIR} ==="
# set -m around each backgrounding line: see robot_boot.sh (without it the job
# ignores SIGINT and can never be stopped cleanly).
set -m
ros2 bag record --node-name map_drive_recorder -o "$BAG_DIR" \
  /robot_001/scan /scan /robot_001/odom /robot_001/imu/data /robot_001/cmd_vel \
  /robot_001/tf /robot_001/tf_static /tf_static \
  > "$BAG_LOG" 2>&1 < /dev/null &
BAG_PID=$!
set +m
bag_deadline=$((SECONDS + 15))
until [ -d "$BAG_DIR" ]; do
  if ! kill -0 "$BAG_PID" 2>/dev/null || (( SECONDS >= bag_deadline )); then
    echo "FATAL: the bag recorder did not start -- see $BAG_LOG" >&2
    tail -n 20 "$BAG_LOG" >&2 || true
    exit 1
  fi
  sleep 0.5
done

# camera_launch_file is deliberately NOT passed: its default (empty) means "no camera".
# Passing it as an empty value (camera_launch_file:='') is a malformed argument that
# makes ros2 launch exit at once -- found the hard way 2026-11-18.
echo "=== [map-drive] starting the driver layer (motors + lidar, no camera) ==="
set -m
ros2 launch nav_fleet drivers_only_launch.py \
  serial_device:=/dev/ttyTHS1 \
  serial_baud:=115200 \
  lidar_launch_file:="$HOME/ros2_drivers_ws/install/ldlidar_ros2/share/ldlidar_ros2/launch/ld19.launch.py" \
  > "$DRIVERS_LOG" 2>&1 < /dev/null &
DRIVERS_PID=$!
set +m

deadline=$((SECONDS + 60))
until grep -q 'esp32_driver up' "$DRIVERS_LOG" 2>/dev/null \
      && grep -q 'ldlidar communication is normal' "$DRIVERS_LOG" 2>/dev/null; do
  if ! kill -0 "$DRIVERS_PID" 2>/dev/null; then
    echo "FATAL: the driver layer exited during start-up -- see $DRIVERS_LOG" >&2
    tail -n 40 "$DRIVERS_LOG" >&2 || true
    exit 1
  fi
  if (( SECONDS >= deadline )); then
    echo "FATAL: motors/lidar not up within 60s -- see $DRIVERS_LOG" >&2
    tail -n 40 "$DRIVERS_LOG" >&2 || true
    exit 1
  fi
  sleep 1
done
echo "=== [map-drive] drivers up -- the keyboard now drives the robot ==="

# Foreground, on the terminal. Its exit (x / Ctrl+C / lost terminal) ends the drive.
python3 "$TELEOP" || true

echo "=== [map-drive] drive ended; bag: ${BAG_DIR} ==="
