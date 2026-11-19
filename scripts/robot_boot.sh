#!/bin/bash
# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
#
# Boot-time entry point for the real, deployed Waveshare UGV-PT (RealRobotStartup.md
# Part A). Two things run, in order: the real-hardware driver layer BARE-METAL
# (drivers_only_launch.py — esp32_driver/lidar/camera/scan_masker/camera_relay), then
# the SAME container image and entrypoint HIL uses (scripts/container_entrypoint.sh,
# ROBOT_MODE=mission — Nav2/EKF/ball_detector/mission_runner, skip_nav2 defaults to
# false so Nav2 runs exactly as before) — only the launch-argument VALUES differ from
# HIL (real-robot context: use_sim_time=false, the real-camera HSV profile, the real
# room's map).
#
# Fixed 2026-08-10 (see docs/superpowers/plans/2026-08-10-drivers-bare-metal-boot-fix.md
# for the full story): this script used to start ONLY the container. Nothing ever
# started the real driver layer for a power-on mission run — Nav2/EKF/ball_detector
# came up inside the container expecting real /robot_001/{odom,scan,camera,imu} data
# with nothing producing it. The container image was also never going to be able to
# run the driver layer itself even if asked to — ldlidar_ros2/depthai-ros were never
# installed in the Docker image, and per this project's own docker-brain-unification
# decision, never should be: the driver layer stays bare-metal, only Nav2/EKF/
# ball_detector/mission_runner run in the container.
#
# NOT yet exercised by CI/HIL (a power cycle can't be simulated there, and HIL's own
# use_sim_time=true path never needs the real driver layer at all — Gazebo provides
# sensor data instead). Run this manually over SSH first and confirm a full mission2
# day passes with your own eyes-on check before trusting the systemd unit
# (scripts/robot-mission.service) that calls it automatically at boot.
#
# Known, separately-tracked gap this script still has (RealRobotStartup.md A4, not
# part of the 2026-08-10 fix above): HSV_CONFIG_FILE below is hardcoded to
# hsv_realcam.yaml, which doesn't exist until HSV calibration is done — a full run of
# this script will still fail at the container step until then.
set -euo pipefail

REPO="$HOME/autonomous-fleet-testbed"
cd "$REPO"

SHA=$(git rev-parse HEAD)
IMAGE="ghcr.io/sdfinn/autonomous-fleet-testbed:${SHA}"

echo "=== [robot-boot] checking image ${IMAGE} is already local (no pull, ever) ==="
if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  echo "FATAL: ${IMAGE} is not present locally — this checkout's sha (${SHA}) was" >&2
  echo "never pulled here by a green stage-4-hil run. Sync to a sha that WAS:" >&2
  echo "  scripts/hil_stage.sh sync <the last green run's commit sha>  (from the workstation)" >&2
  exit 1
fi

LOG_DIR="$HOME/fleet-ci-data/robot_boot_logs"
mkdir -p "$LOG_DIR"
TS=$(date +%Y%m%dT%H%M%S)

# --- Real-hardware driver layer, BARE-METAL (fixed 2026-08-10) ---
echo "=== [robot-boot] starting the real driver layer bare-metal ==="
set +u
# ROBOT_BOOT_ROS_SETUP exists only so tests/test_robot_boot_script.py can run this
# script on a machine with no ROS 2 installed (CI stage 1). Never set it on the robot.
source "${ROBOT_BOOT_ROS_SETUP:-/opt/ros/jazzy/setup.bash}"
set -u
# A node added since the last colcon build here has no launcher yet (see the script).
bash "$REPO/scripts/ensure_nav_fleet_built.sh" "$REPO"
set +u
source "$REPO/install/setup.bash"
# ldlidar_ros2 lives in its own separate overlay (~/ros2_drivers_ws), normally
# sourced by .bashrc -- which a non-interactive boot-time script never runs. Without
# this, drivers_only_launch.py fails with "package 'ldlidar_ros2' not found" (hit
# live during Task 1's own verification and again during this task's Step 3 dry-run).
[ -f "$HOME/ros2_drivers_ws/install/setup.bash" ] && source "$HOME/ros2_drivers_ws/install/setup.bash"
set -u
bash "$REPO/scripts/regen_cyclonedds_config.sh"
# Final-review C2 (2026-08-11): this bare-metal driver layer previously got NO
# RMW_IMPLEMENTATION/CYCLONEDDS_URI export at all under this script's
# non-interactive path (systemd boot, non-interactive SSH -- .bashrc never runs
# here) -- it silently defaulted to ROS2's own default RMW (FastDDS), while the
# container ALWAYS hardcodes rmw_cyclonedds_cpp (container_entrypoint.sh) --
# zero DDS traffic would ever cross the driver-layer/container boundary,
# reproducing this whole plan's original bug in a new form, invisibly.
# regen_cyclonedds_config.sh (above) writes to $HOME/cyclonedds-hil.xml by
# default here (CYCLONEDDS_CONFIG_PATH is unset in this script) -- confirmed
# by reading that script directly, not assumed.
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp ROS_DOMAIN_ID=0 \
  CYCLONEDDS_URI="file://$HOME/cyclonedds-hil.xml"

# --- Teardown, defined BEFORE anything is started (2026-11-17) ---
# Three things get started below, each as a background job in its own process group
# (`set -m` around each `&`): the bag recorder, the driver layer, the mission container.
# Because none of them shares this script's process group, a Ctrl+C in the terminal
# reaches ONLY this script, and this script decides the stop order:
#   1. the mission container (the thing commanding the wheels) -- force-removed, because
#      its PID 1 is a plain bash script and Linux drops SIGINT/SIGTERM for a container's
#      PID 1 with no handler (found live 2026-11-16: Ctrl+C did nothing for 25 s). With
#      it gone, esp32_driver's 200 ms watchdog zeroes the wheels.
#   2. the bag recorder -- SIGINT, so the mcap is finalized, and AFTER the container so
#      the recording still contains the wheels stopping.
#   3. the driver layer -- SIGINT, so ros2 launch shuts its nodes down cleanly instead
#      of leaving them orphaned to poison the next run.
BAG_PID=""
DRIVERS_PID=""
MISSION_PID=""

# SIGINT a background job, give it 15 s to exit by itself, then SIGKILL it.
stop_job() {
  local name=$1 pid=$2 waited=0
  [ -n "$pid" ] || return 0
  kill -0 "$pid" 2>/dev/null || { wait "$pid" 2>/dev/null || true; return 0; }
  echo "=== [robot-boot] stopping ${name} (pid ${pid}) ==="
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
  # A second Ctrl+C must not cut the teardown short (an unfinalized bag is useless).
  trap '' INT TERM HUP
  if [ -n "$MISSION_PID" ]; then
    echo "=== [robot-boot] removing the mission container ==="
    docker rm -f robot_mission >/dev/null 2>&1 || true
    wait "$MISSION_PID" 2>/dev/null || true
  fi
  stop_job "the bag recorder" "$BAG_PID"
  stop_job "the bare-metal driver layer" "$DRIVERS_PID"
}
trap cleanup EXIT
# `exit` inside a signal trap runs the EXIT trap above. 130/143 = the conventional
# "killed by SIGINT/SIGTERM" exit codes (128 + signal number).
trap 'echo "=== [robot-boot] Ctrl+C -- stopping the mission ===" >&2; exit 130' INT
trap 'echo "=== [robot-boot] SIGTERM -- stopping the mission ===" >&2; exit 143' TERM
# SIGHUP = the terminal went away (SSH session dropped, e.g. WiFi lost while the robot
# is driving). Nobody can press Ctrl+C any more, so stop the same way.
trap 'echo "=== [robot-boot] terminal lost (SIGHUP) -- stopping the mission ===" >&2; exit 129' HUP

# --- Evidence bag, BARE-METAL, on every run (2026-11-17) ---
# Run 2 on 2026-11-16 finished with a 0.55 m position error and no recording, so it
# could not be diagnosed. The recorder runs out here, not in the container, so it
# survives the container being force-removed, and it starts before the drivers so the
# very first odometry/scan/TF messages are in it. Written under ~/fleet-ci-data, not
# reports/: `hil_stage.sh sync` runs `git clean -fd` on this checkout.
# --all-topics minus full camera frames: raw ones are megabytes each, and their
# compressed/zstd copies are not much smaller (checked on the Jetson 2026-11-17: the
# zstd topics alone wrote 5 MB/s). The small theora video streams stay, so the bag
# still has pictures: about 0.5 MB/s in total (run 1's bag was 41 MB for 82 s).
# --node-name: the default name, rosbag2_recorder, is also the name of the container's
# failure-bag recorder (nav_fleet/failure_bag.py), whose /rosbag2_recorder/snapshot
# service must be answered by that recorder only.
# ROBOT_BOOT_NO_BAG=1 skips the recording (e.g. a full disk); otherwise no recorder
# means no mission.
BAG_DIR="$LOG_DIR/bag_${TS}"
if [ -n "${ROBOT_BOOT_NO_BAG:-}" ]; then
  echo "=== [robot-boot] ROBOT_BOOT_NO_BAG set -- NOT recording a bag for this run ==="
else
  echo "=== [robot-boot] recording a bag to ${BAG_DIR} ==="
  BAG_LOG="$LOG_DIR/bag_${TS}.log"
  set -m
  ros2 bag record --all-topics \
    --exclude-regex '.*/image_(raw|rect)(/compressed|/compressedDepth|/zstd)?$' \
    --node-name robot_boot_recorder \
    -o "$BAG_DIR" \
    > "$BAG_LOG" 2>&1 < /dev/null &
  BAG_PID=$!
  set +m
  bag_deadline=$((SECONDS + 15))
  until [ -d "$BAG_DIR" ]; do
    if ! kill -0 "$BAG_PID" 2>/dev/null || (( SECONDS >= bag_deadline )); then
      echo "FATAL: the bag recorder did not start -- see $BAG_LOG (ROBOT_BOOT_NO_BAG=1 runs without one)" >&2
      tail -n 20 "$BAG_LOG" >&2 || true
      exit 1
    fi
    sleep 0.5
  done
fi

DRIVERS_LOG="$LOG_DIR/drivers_${TS}.log"
rm -f "$DRIVERS_LOG"
# set -m (job control) bracketed around only the backgrounding itself: without it, bash
# auto-sets SIGINT/SIGQUIT to SIG_IGN on ANY `&`-backgrounded job started from a
# non-interactive script (POSIX/bash's standard behavior for asynchronous lists when job
# control is off -- true for every invocation of this script, interactive terminal,
# ssh -t, or systemd, since a `#!/bin/bash` script file is always non-interactive).
# Confirmed live (Task 3 Step 3): without this, `kill -INT "$DRIVERS_PID"` below is a
# silent no-op forever -- ros2 launch inherits SIG_IGN for SIGINT and never reacts to it,
# which would orphan the whole driver layer on every single run.
set -m
ros2 launch nav_fleet drivers_only_launch.py \
  serial_device:=/dev/ttyTHS1 \
  serial_baud:=115200 \
  lidar_launch_file:="$HOME/ros2_drivers_ws/install/ldlidar_ros2/share/ldlidar_ros2/launch/ld19.launch.py" \
  camera_launch_file:=/opt/ros/jazzy/share/depthai_ros_driver/launch/camera.launch.py \
  > "$DRIVERS_LOG" 2>&1 < /dev/null &
DRIVERS_PID=$!
set +m

# Teardown of the driver layer on ANY exit path is cleanup() above (EXIT trap).

echo "=== [robot-boot] waiting up to 60s for the driver layer to report up ==="
# I2 (2026-08-11): the old single 'camera_relay up' check could report the whole
# driver layer "up" even with NO lidar and NO odometry actually running --
# camera_relay/scan_masker start regardless of whether esp32_driver/ldlidar_ros2/
# depthai-ros themselves came up (their own launch-file comments say "harmless
# with no publisher yet"). Require all 4 real confirmation lines (task-1-report.md's
# own live-verified log excerpt) before proceeding.
deadline=$((SECONDS + 60))
count_esp32=0
count_lidar=0
count_camera=0
count_relay=0
until [ "$count_esp32" -ge 1 ] && [ "$count_lidar" -ge 1 ] \
      && [ "$count_camera" -ge 1 ] && [ "$count_relay" -ge 1 ]; do
  if (( SECONDS >= deadline )); then
    echo "FATAL: driver layer not fully up within 60s (esp32_driver=${count_esp32} ldlidar=${count_lidar} camera=${count_camera} camera_relay=${count_relay}) — see $DRIVERS_LOG" >&2
    tail -n 40 "$DRIVERS_LOG" >&2 || true
    exit 1
  fi
  sleep 2
  count_esp32=$(grep -c 'esp32_driver up' "$DRIVERS_LOG" 2>/dev/null || true)
  count_esp32="${count_esp32:-0}"
  count_lidar=$(grep -c 'ldlidar communication is normal' "$DRIVERS_LOG" 2>/dev/null || true)
  count_lidar="${count_lidar:-0}"
  count_camera=$(grep -c 'Camera with MXID' "$DRIVERS_LOG" 2>/dev/null || true)
  count_camera="${count_camera:-0}"
  count_relay=$(grep -c 'camera_relay up' "$DRIVERS_LOG" 2>/dev/null || true)
  count_relay="${count_relay:-0}"
done
echo "=== [robot-boot] driver layer up ==="

# --- Nav2/EKF/ball_detector/mission_runner, containerized (unchanged) ---
echo "=== [robot-boot] running ${IMAGE} (real-robot context, operator ball placement) ==="
# RUNNER_TYPE=real_robot matches the convention every other real-robot telemetry row
# in this project already uses. MISSION2_SELF_REPORT=1: no ground-truth judging (no
# Gazebo on the real robot) — mission_runner logs each leg's own self-reported
# PASS/FAIL instead; analysis of the resulting logs/photos happens after, manually.
# ROBOT_MODE=mission is hardcoded here, never a variable — standalone power-on can
# never run a smoke test (design spec). skip_nav2 is NOT set here — its default
# (false) means Nav2 runs exactly as it always has.
# HSV_CONFIG_FILE stand-in, 2026-08-11: hsv_realcam.yaml (A4, real-camera HSV
# calibration) does not exist yet. (The map is chosen just below.)
# hsv_gazebo.yaml is a genuine stand-in — sim color thresholds, not calibrated
# against this room's real camera/lighting — ball_detector will run without
# crashing but its detection accuracy is unproven until A4 happens.
#
# Map selection (A3 done 2026-11-18). The robot's own map lives OUTSIDE git, in
# ~/fleet-ci-data/maps/bedroom_real.{yaml,pgm}: it is a floor plan of a real home and
# this repo is public. When both files are there they are mounted read-only over the
# image's maps directory and used; otherwise the run falls back to living_room.yaml
# with a loud warning. That fallback is NOT equivalent: its bedroom half is accurate
# but its hallway is not, and its home pose is ~0.6 m from where the robot is really
# put down -- the cause of the 2026-11-16 and 2026-11-18 home errors (see
# docs/sessions/2026-11-18.md). Build the real map with scripts/build_map_from_bag.sh.
REAL_MAP_DIR="$HOME/fleet-ci-data/maps"
if [ -f "$REAL_MAP_DIR/bedroom_real.yaml" ] && [ -f "$REAL_MAP_DIR/bedroom_real.pgm" ]; then
  echo "=== [robot-boot] map: the robot's own map, ${REAL_MAP_DIR}/bedroom_real.yaml ==="
  MAP_ARGS=(-v "$REAL_MAP_DIR/bedroom_real.yaml:/ros2_ws/src/nav_fleet/maps/bedroom_real.yaml:ro"
            -v "$REAL_MAP_DIR/bedroom_real.pgm:/ros2_ws/src/nav_fleet/maps/bedroom_real.pgm:ro"
            -e NAV2_MAP_FILE=bedroom_real.yaml)
else
  echo "=== [robot-boot] WARNING: no real map at ${REAL_MAP_DIR}/bedroom_real.{yaml,pgm} -- falling back to the BORROWED living_room.yaml (hallway and home pose do not match this house; expect a home error) ===" >&2
  MAP_ARGS=(-e NAV2_MAP_FILE=living_room.yaml)
fi
docker rm -f robot_mission 2>/dev/null || true
mkdir -p "$REPO/reports"
# Navigation-only diagnostic runs (2026-11-16): the container only sees env vars
# passed with -e, so exporting MISSION2_IGNORE_REACTIONS in the calling shell did
# nothing before this line existed. Usage:  MISSION2_IGNORE_REACTIONS=1 scripts/robot_boot.sh
# Unset (the normal case, incl. systemd boot) adds no argument at all.
if [ -n "${MISSION2_IGNORE_REACTIONS:-}" ]; then
  echo "=== [robot-boot] MISSION2_IGNORE_REACTIONS set — ball reactions SUPPRESSED (navigation-only diagnostic run) ==="
fi
# Run in the BACKGROUND and `wait` for it: bash only runs a signal trap once the
# foreground command returns, and `docker run` never returns on Ctrl+C (see the
# teardown comment above) -- but `wait` is interrupted by a trapped signal at once.
# The ( ) keeps `docker run | tee` one job whose exit status is docker's (pipefail).
set -m
(docker run --rm --name robot_mission --network host --ipc host \
  -v "$REPO/reports:/ros2_ws/reports" \
  -v "$HOME/fleet-ci-data:/root/fleet-ci-data" \
  -e USE_SIM_TIME=false \
  -e HSV_CONFIG_FILE=hsv_gazebo.yaml \
  "${MAP_ARGS[@]}" \
  -e MISSION2_SELF_REPORT=1 \
  -e RUNNER_TYPE=real_robot \
  -e ROBOT_MODE=mission \
  ${MISSION2_IGNORE_REACTIONS:+-e MISSION2_IGNORE_REACTIONS=1} \
  "$IMAGE" bash /ros2_ws/scripts/container_entrypoint.sh \
  2>&1 < /dev/null | tee "$LOG_DIR/robot_boot_${TS}.log") &
MISSION_PID=$!
set +m
MISSION_RC=0
wait "$MISSION_PID" || MISSION_RC=$?
MISSION_PID=""
if [ -n "$BAG_PID" ]; then
  echo "=== [robot-boot] mission exited with ${MISSION_RC}; bag: ${BAG_DIR} ==="
fi
exit "$MISSION_RC"
