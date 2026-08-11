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
source /opt/ros/jazzy/setup.bash
source "$REPO/install/setup.bash"
# ldlidar_ros2 lives in its own separate overlay (~/ros2_drivers_ws), normally
# sourced by .bashrc -- which a non-interactive boot-time script never runs. Without
# this, drivers_only_launch.py fails with "package 'ldlidar_ros2' not found" (hit
# live during Task 1's own verification and again during this task's Step 3 dry-run).
[ -f "$HOME/ros2_drivers_ws/install/setup.bash" ] && source "$HOME/ros2_drivers_ws/install/setup.bash"
set -u
bash "$REPO/scripts/regen_cyclonedds_config.sh"

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

# Clean bare-metal teardown on ANY exit path (mission success, mission failure, this
# script killed) — SIGINT (not SIGKILL) so ros2 launch propagates it to esp32_driver/
# lidar/camera/scan_masker/camera_relay the same clean way Ctrl+C already does
# (CLAUDE.md's own established teardown pattern), instead of leaving them orphaned to
# poison the NEXT boot's driver layer.
cleanup_drivers() {
  echo "=== [robot-boot] stopping the bare-metal driver layer (pid ${DRIVERS_PID}) ==="
  kill -INT "$DRIVERS_PID" 2>/dev/null || true
  wait "$DRIVERS_PID" 2>/dev/null || true
}
trap cleanup_drivers EXIT

echo "=== [robot-boot] waiting up to 60s for the driver layer to report up ==="
deadline=$((SECONDS + 60))
count=0
until [ "$count" -ge 1 ]; do
  if (( SECONDS >= deadline )); then
    echo "FATAL: drivers_only_launch.py not up within 60s — see $DRIVERS_LOG" >&2
    tail -n 40 "$DRIVERS_LOG" >&2 || true
    exit 1
  fi
  sleep 2
  count=$(grep -c 'camera_relay up' "$DRIVERS_LOG" 2>/dev/null || true)
  count="${count:-0}"
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
docker rm -f robot_mission 2>/dev/null || true
mkdir -p "$REPO/reports"
docker run --rm --name robot_mission --network host --ipc host \
  -v "$REPO/reports:/ros2_ws/reports" \
  -v "$HOME/fleet-ci-data:/root/fleet-ci-data" \
  -e USE_SIM_TIME=false \
  -e HSV_CONFIG_FILE=hsv_realcam.yaml \
  -e NAV2_MAP_FILE=bedroom_real.yaml \
  -e MISSION2_SELF_REPORT=1 \
  -e RUNNER_TYPE=real_robot \
  -e ROBOT_MODE=mission \
  "$IMAGE" bash /ros2_ws/scripts/container_entrypoint.sh \
  2>&1 | tee "$LOG_DIR/robot_boot_${TS}.log"
