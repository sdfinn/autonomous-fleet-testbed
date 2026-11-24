#!/bin/bash
# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
#
# Boot-time entry point for the real, deployed Waveshare UGV-PT (RealRobotStartup.md
# Part A). Two things run, in order: the real-hardware driver layer BARE-METAL
# (drivers_only_launch.py — esp32_driver/lidar/camera/scan_masker/camera_relay), then
# the SAME container image and entrypoint HIL uses (scripts/container_entrypoint.sh,
# ROBOT_MODE=mission — Nav2/EKF/mission_runner, skip_nav2 defaults to
# false so Nav2 runs exactly as before) — only the launch-argument VALUES differ from
# HIL (real-robot context: use_sim_time=false, the real room's map). The detector
# (RF-DETR) runs beside the drivers, outside the container: it needs the GPU.
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

# --- What a lost link does to a run (Mike, 2026-11-23) ---
#   ROBOT_BOOT_LINK_LOSS=carry_on   (default) the mission continues and keeps recording
#                                   when the operator's link or this terminal is lost.
#                                   No operator watch is started. While the link is down
#                                   nothing remote can stop the robot: its power switch
#                                   and the obstacle guard are what is left.
#   ROBOT_BOOT_LINK_LOSS=pause      the rule of 2026-11-19: the operator watch pauses the
#                                   robot after 2 s without the operator and ends the run
#                                   10 s later; a lost terminal (SIGHUP) stops the mission.
# Why the default changed: the robot's own messaging no longer depends on WiFi (loopback,
# below), so a mission that is on track can finish without the link; twice a WiFi hiccup
# ended one a few meters from home.
LINK_LOSS="${ROBOT_BOOT_LINK_LOSS:-carry_on}"
CONSOLE_TAIL_PID=""        # set just below; must not be reset later in this script
case "$LINK_LOSS" in
  carry_on|pause) ;;
  *) echo "FATAL: ROBOT_BOOT_LINK_LOSS must be carry_on or pause, got '${LINK_LOSS}'" >&2; exit 1 ;;
esac
if [ "$LINK_LOSS" = "carry_on" ]; then
  # A script whose terminal has gone cannot write to it: the next `echo` fails and, with
  # `set -e`, ends the run. So this script writes to a file from here on, and a separate
  # `tail` copies the file to the terminal for as long as there is one. The tail is its
  # own process group (set -m) so a Ctrl+C aimed at the mission does not silence it.
  CONSOLE_LOG="$LOG_DIR/console_${TS}.log"
  : > "$CONSOLE_LOG"
  exec 3>&1
  exec >>"$CONSOLE_LOG" 2>&1
  set -m
  tail -n +1 -f "$CONSOLE_LOG" >&3 2>/dev/null &
  CONSOLE_TAIL_PID=$!
  set +m
  # Until the full teardown below is installed, an early exit (a FATAL before anything
  # is started) must still end the tail, or the terminal waits on it forever.
  trap 'sleep 0.5; kill "$CONSOLE_TAIL_PID" 2>/dev/null || true' EXIT
fi

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
# The robot's own messaging stays on this machine (2026-11-23): loopback, no network
# interface. Every process of a mission runs on this Jetson, and twice a new WiFi
# address in the middle of a mission left them unable to hear each other (2026-11-20,
# 2026-11-23: stalled a few meters from home). WiFi is still how a mission is started
# and watched; it is no longer something the mission needs in order to finish.
# The same value goes to the container below, which writes its own copy of the file.
#   ROBOT_BOOT_DDS_SCOPE=network   the old behavior, for a tool on another machine that
#                                  must see the robot's topics during one run
export CYCLONEDDS_SCOPE="${ROBOT_BOOT_DDS_SCOPE:-local}"
if [ "$CYCLONEDDS_SCOPE" != "local" ]; then
  echo "=== [robot-boot] WARNING: messaging scope '${CYCLONEDDS_SCOPE}', not 'local' -- a WiFi address change can stop this run ===" >&2
fi
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
WATCH_PID=""
WATCH_WAITER_PID=""
DETECTOR_PID=""
MAST_PID=""

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
  trap '' INT TERM HUP USR1
  # The waiter first: the watch node is about to be stopped on purpose, and its exit
  # must not be reported as "the operator watch ended".
  # Kill it, and do NOT `wait` for it (2026-11-23). When the watch ends, the waiter
  # signals this script and then exits by itself. If it is already gone when this line
  # is reached, `wait` on it never returns here (bash, inside the EXIT trap of a script
  # whose `wait` was interrupted by that very signal): the container was never removed,
  # the bag never finalized, the drivers never stopped. A busy machine loses that race;
  # found when CI's unit-test stage hung, reproduced 6 times in 8 under load. Nothing
  # needs the waiter's exit status, and USR1 is ignored from the line above.
  if [ -n "$WATCH_WAITER_PID" ]; then
    kill "$WATCH_WAITER_PID" 2>/dev/null || true
  fi
  if [ -n "$MISSION_PID" ]; then
    echo "=== [robot-boot] removing the mission container ==="
    docker rm -f robot_mission >/dev/null 2>&1 || true
    wait "$MISSION_PID" 2>/dev/null || true
  fi
  # The operator watch goes AFTER the container: once it is gone esp32_driver holds the
  # wheels anyway (operator_watch_required), and while the container is being removed
  # the watch is still what holds them if the link is down.
  # `ros2 run` does not pass a signal on to the node it started; it expects the
  # terminal to have signalled both. The watch is its own process group (set -m), so
  # signal the group.
  if [ -n "$WATCH_PID" ]; then kill -INT -- "-$WATCH_PID" 2>/dev/null || true; fi
  stop_job "the operator watch" "$WATCH_PID"
  stop_job "the bag recorder" "$BAG_PID"
  # After the bag, so the recording holds the detections to the very end. Its own
  # process group, like the watch (`ros2 run` does not pass a signal on).
  if [ -n "$DETECTOR_PID" ]; then kill -INT -- "-$DETECTOR_PID" 2>/dev/null || true; fi
  stop_job "the RF-DETR detector" "$DETECTOR_PID"
  stop_job "the bare-metal driver layer" "$DRIVERS_PID"
  # The mast video last of all, so it shows the wheels stopping. SIGINT finalizes the file.
  stop_job "the mast camera recorder" "$MAST_PID"
  # The copy of this script's output to the terminal (link-loss rule "carry on", below).
  if [ -n "$CONSOLE_TAIL_PID" ]; then
    sleep 0.5                                  # let it show the lines just written
    kill "$CONSOLE_TAIL_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT
# `exit` inside a signal trap runs the EXIT trap above. 130/143 = the conventional
# "killed by SIGINT/SIGTERM" exit codes (128 + signal number).
trap 'echo "=== [robot-boot] Ctrl+C -- stopping the mission ===" >&2; exit 130' INT
trap 'echo "=== [robot-boot] SIGTERM -- stopping the mission ===" >&2; exit 143' TERM
# SIGHUP = the terminal went away (SSH session dropped, e.g. WiFi lost while the robot
# is driving). Nobody can press Ctrl+C any more, so stop the same way.
if [ "$LINK_LOSS" = "pause" ]; then
  trap 'echo "=== [robot-boot] terminal lost (SIGHUP) -- stopping the mission ===" >&2; exit 129' HUP
else
  # "carry on": the terminal going away is not a reason to stop. Ignored, not handled:
  # a handler would interrupt the `wait` for the mission at the bottom of this script.
  trap '' HUP
fi
# SIGUSR1 = the operator watch ended while the mission was running (sent by the waiter
# started next to the mission, below): either it gave up -- the operator's machine did
# not come back -- or it died. Either way nobody is watching an attended run any more.
# 131 = 128 + 3, free among this script's exit codes.
trap 'echo "=== [robot-boot] the operator watch ended -- stopping the mission ($(tail -n 1 "$WATCH_LOG" 2>/dev/null)) ===" >&2; exit 131' USR1

# --- Operator watch (2026-11-19): pause, then stop, when an ATTENDED run loses its operator ---
# A DROPPED link (WiFi lost, robot out of range) sends no SIGHUP -- the SSH session just
# hangs open on this side -- so the mission carries on and Ctrl+C cannot reach it. A run
# started over SSH has an operator, and SSH_CLIENT holds their address. For such a run:
#   * the `operator_watch` node (bare-metal, next to the drivers) pings that address five
#     times a second and publishes /robot_001/operator_hold;
#   * esp32_driver is started with operator_watch_required:=true, so it holds the wheels
#     whenever the watch says "unreachable" AND whenever the watch is not heard from;
#   * no answer for ROBOT_BOOT_OPERATOR_TIMEOUT_S (default 2): the robot PAUSES, two
#     short beeps. Nav2 is not told and carries on when the hold is released;
#   * link back: one long beep, then the robot moves again a second later;
#   * still silent ROBOT_BOOT_OPERATOR_GIVE_UP_S (default 10) after the pause: three low
#     beeps, the watch exits, and this script shuts the mission down (exit 131).
# Pause rather than stop, because this robot's WiFi adapter changes radio band by itself
# while driving and each change is ~2.4 s of silence (measured 2026-11-19).
# A run NOT started over SSH (robot-mission.service at boot) has no operator and none of
# this: the deployed robot needs no network at all.
#   ROBOT_BOOT_OPERATOR_IP=<addr>     watch this address instead of the SSH client's
#   ROBOT_BOOT_NO_OPERATOR_WATCH=1    watch nobody (e.g. the operator's machine drops pings)
#   ROBOT_BOOT_NO_BEEP=1              no sounds
# This covers "WiFi gone, Jetson alive". "Jetson gone" is the motor board's own
# stop-on-silence timer (esp32_driver, bench-proven 2026-11-19). Neither replaces a
# physical stop button.
OPERATOR_IP=""
OPERATOR_TIMEOUT_S="${ROBOT_BOOT_OPERATOR_TIMEOUT_S:-2}"
OPERATOR_GIVE_UP_S="${ROBOT_BOOT_OPERATOR_GIVE_UP_S:-10}"
WATCH_LOG=""
if [ "$LINK_LOSS" != "pause" ]; then
  echo "=== [robot-boot] link-loss rule: CARRY ON -- if the operator's link or this terminal is lost the mission continues and keeps recording; the only stop then is the robot's power switch (ROBOT_BOOT_LINK_LOSS=pause for the old rule) ==="
elif [ -n "${ROBOT_BOOT_NO_OPERATOR_WATCH:-}" ]; then
  echo "=== [robot-boot] WARNING: ROBOT_BOOT_NO_OPERATOR_WATCH set -- a lost link will NOT stop this run ===" >&2
else
  ssh_client="${SSH_CLIENT:-}"
  OPERATOR_IP="${ROBOT_BOOT_OPERATOR_IP:-${ssh_client%% *}}"
fi

# Pre-flight: at least one of five pings answered.
operator_reachable() {
  ping -c 5 -i 0.2 -W 1 "$OPERATOR_IP" >/dev/null 2>&1
}

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

# Obstacle guard (2026-11-19): on every mission, hold the wheels while the lidar sees
# something within 0.25 m of the bumper in the direction of travel, and (because the
# driver is told the guard is mandatory) whenever the guard or the lidar goes silent.
# One low beep when it holds. See nav_fleet/path_guard.py for what it does not cover.
#   ROBOT_BOOT_NO_OBSTACLE_GUARD=1    run without it
#   ROBOT_BOOT_NO_BEEP=1              no sounds (this and the operator watch)
if [ -n "${ROBOT_BOOT_NO_OBSTACLE_GUARD:-}" ]; then
  echo "=== [robot-boot] WARNING: ROBOT_BOOT_NO_OBSTACLE_GUARD set -- nothing stops this run driving into what the lidar sees ===" >&2
  GUARD_ARGS=(obstacle_guard:=false)
elif [ -n "${ROBOT_BOOT_NO_BEEP:-}" ]; then
  GUARD_ARGS=(obstacle_guard:=true obstacle_guard_beep:=false)
else
  GUARD_ARGS=(obstacle_guard:=true)
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
  ${OPERATOR_IP:+operator_watch_required:=true} \
  "${GUARD_ARGS[@]}" \
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

# --- Battery pre-flight (2026-11-18) ---
# Two sessions in a row ended on a flat pack; the second time the Jetson lost power in
# the middle of a spin. esp32_driver now logs one line a few seconds after start-up:
#   esp32_driver: battery 11.82 V (ok|low|critical)
# No mission starts unless that line says "ok". A missing line is treated the same as
# a bad one (fail closed). ROBOT_BOOT_IGNORE_BATTERY=1 overrides, for bench work on a
# supply or a deliberate last short run.
battery_line=""
battery_deadline=$((SECONDS + 15))
while [ -z "$battery_line" ] && (( SECONDS < battery_deadline )); do
  battery_line=$(grep -oE 'esp32_driver: battery [0-9.]+ V \((ok|low|critical)\)' "$DRIVERS_LOG" 2>/dev/null | tail -n 1 || true)
  [ -n "$battery_line" ] || sleep 1
done
if [ -n "$battery_line" ]; then
  echo "=== [robot-boot] ${battery_line#esp32_driver: } ==="
else
  echo "=== [robot-boot] no battery reading from esp32_driver within 15s ===" >&2
fi
case "$battery_line" in
  *"(ok)") ;;
  *)
    if [ -n "${ROBOT_BOOT_IGNORE_BATTERY:-}" ]; then
      echo "=== [robot-boot] WARNING: ROBOT_BOOT_IGNORE_BATTERY set -- starting anyway ===" >&2
    else
      echo "FATAL: battery is not OK -- charge the pack (12.6 V charger), or set ROBOT_BOOT_IGNORE_BATTERY=1 to run anyway" >&2
      exit 1
    fi ;;
esac

# --- IMU pre-flight (2026-11-20) ---
# After one power-on the motor board's IMU chip did not start: the board repeated the
# same nine numbers, gyro z among them at 706 deg/s. The robot's position estimate left
# the home spot before the first goal and the robot spun where it stood. esp32_driver
# now judges the IMU on its first ~2 s of samples and logs one line:
#   esp32_driver: imu ok|frozen|implausible (<why>)
# No mission starts unless it says "ok"; a missing line counts as bad (fail closed).
# There is no override: the driver itself refuses motion on a bad IMU.
imu_line=""
imu_deadline=$((SECONDS + 15))
while [ -z "$imu_line" ] && (( SECONDS < imu_deadline )); do
  imu_line=$(grep -oE 'esp32_driver: imu (ok|frozen|implausible) \([^)]*\)' "$DRIVERS_LOG" 2>/dev/null | tail -n 1 || true)
  [ -n "$imu_line" ] || sleep 1
done
case "$imu_line" in
  "esp32_driver: imu ok"*)
    echo "=== [robot-boot] ${imu_line#esp32_driver: } ===" ;;
  "")
    echo "FATAL: no IMU verdict from esp32_driver within 15s -- not starting a mission" >&2
    exit 1 ;;
  *)
    echo "FATAL: ${imu_line#esp32_driver: } -- the motor board's IMU is not working; switch the robot off and on again" >&2
    exit 1 ;;
esac

# --- The detector: RF-DETR (2026-11-22; the only detector since 2026-11-23) ---
# The RF-DETR node (nav_fleet/object_detector.py) runs here on the Jetson's GPU, outside
# the container, and publishes /robot_001/detections, the topic the mission reacts to.
# The container starts no detector of its own. The hand-written color detector that
# used to run there was removed on 2026-11-23 (its story: docs/detection-history.md).
#   ROBOT_BOOT_RFDETR=<file>   another .engine/.onnx file for this run (default: the
#                              engine built on this Jetson, below). 1 = the default.
# Not ready within 60 s is fatal, BEFORE anything moves: a mission that reacts to balls
# must not start blind.
for gone in ROBOT_BOOT_SHADOW_DETECTOR ROBOT_BOOT_DETECTOR; do
  if [ -n "${!gone:-}" ]; then
    echo "FATAL: ${gone} was removed on 2026-11-23 with the hand-written detector; RF-DETR is the only detector (ROBOT_BOOT_RFDETR=<file> picks another model file)" >&2
    exit 1
  fi
done
RFDETR_MODEL="${ROBOT_BOOT_RFDETR:-1}"
if [ "$RFDETR_MODEL" = "1" ]; then RFDETR_MODEL="$HOME/fleet-ci-data/models/rfdetr-small.engine"; fi
if [ ! -f "$RFDETR_MODEL" ]; then
  echo "FATAL: RF-DETR model ${RFDETR_MODEL} is not a file (build it on this Jetson: trtexec --onnx=rfdetr-small.onnx --saveEngine=rfdetr-small.engine --fp16)" >&2
  exit 1
fi
echo "=== [robot-boot] detector: RF-DETR on this Jetson (${RFDETR_MODEL}) ==="
DETECTOR_LOG="$LOG_DIR/rfdetr_detector_${TS}.log"
rm -f "$DETECTOR_LOG"
set -m
ros2 run nav_fleet object_detector --ros-args -p model_path:="$RFDETR_MODEL" \
  -p output_topic:=/robot_001/detections \
  > "$DETECTOR_LOG" 2>&1 < /dev/null &
DETECTOR_PID=$!
set +m
detector_waited=0
until grep -q 'detector ready' "$DETECTOR_LOG" 2>/dev/null; do
  if ! kill -0 "$DETECTOR_PID" 2>/dev/null || [ "$detector_waited" -ge 60 ]; then
    echo "FATAL: the RF-DETR detector did not become ready -- see $DETECTOR_LOG" >&2
    tail -n 15 "$DETECTOR_LOG" >&2 || true
    exit 1
  fi
  sleep 1
  detector_waited=$((detector_waited + 1))
done
echo "=== [robot-boot] RF-DETR detector ready after ${detector_waited}s ($(grep -o 'detector ready.*first picture [0-9]* ms' "$DETECTOR_LOG" | tail -n 1)); log: $DETECTOR_LOG ==="

# --- Mast camera video, on every run (2026-11-23) ---
# The second camera, on the pan-tilt mast, recorded beside the mission: it shows what the
# robot did. Not fatal when it cannot start (no camera, no OpenCV): said, and carried on.
#   ROBOT_BOOT_NO_MAST_VIDEO=1      do not record
#   ROBOT_BOOT_MAST_DEVICE=<path>   another camera device
MAST_DEVICE="${ROBOT_BOOT_MAST_DEVICE:-/dev/v4l/by-id/usb-Xitech_USB_Camera_20250606105-video-index0}"
if [ -n "${ROBOT_BOOT_NO_MAST_VIDEO:-}" ]; then
  echo "=== [robot-boot] ROBOT_BOOT_NO_MAST_VIDEO set -- no mast camera video for this run ==="
elif [ ! -e "$MAST_DEVICE" ] || [ ! -f "$REPO/tools/mast_record.py" ]; then
  echo "=== [robot-boot] no mast camera video: ${MAST_DEVICE} or tools/mast_record.py is not there ===" >&2
else
  MAST_VIDEO="$LOG_DIR/mast_${TS}.avi"
  MAST_LOG="$LOG_DIR/mast_${TS}.log"
  set -m
  python3 "$REPO/tools/mast_record.py" "$MAST_VIDEO" --device "$MAST_DEVICE" \
    > "$MAST_LOG" 2>&1 < /dev/null &
  MAST_PID=$!
  set +m
  sleep 2
  if kill -0 "$MAST_PID" 2>/dev/null; then
    echo "=== [robot-boot] mast camera video: ${MAST_VIDEO} ==="
  else
    echo "=== [robot-boot] WARNING: the mast camera recorder did not start ($(tail -n 1 "$MAST_LOG" 2>/dev/null)) -- carrying on without video ===" >&2
    MAST_PID=""
  fi
fi

# --- Operator pre-flight and watch (2026-11-19) ---
# A link that is already bad is no link to start a floor run on: check before anything
# moves. Then start the watch, BEFORE the mission: until it reports the operator
# reachable, esp32_driver holds the wheels.
if [ -n "$OPERATOR_IP" ]; then
  if ! operator_reachable; then
    echo "FATAL: operator ${OPERATOR_IP} does not answer pings -- fix the link, or set ROBOT_BOOT_NO_OPERATOR_WATCH=1 to run with no remote stop" >&2
    exit 1
  fi
  echo "=== [robot-boot] operator ${OPERATOR_IP} reachable -- the robot pauses after ${OPERATOR_TIMEOUT_S}s of silence and the run ends ${OPERATOR_GIVE_UP_S}s after that ==="
  WATCH_LOG="$LOG_DIR/operator_watch_${TS}.log"
  beep=true
  if [ -n "${ROBOT_BOOT_NO_BEEP:-}" ]; then beep=false; fi
  # ROS 2 parameters are typed: "2" would be an integer and the node declares floats.
  set -m
  ros2 run nav_fleet operator_watch --ros-args \
    -p operator_ip:="$OPERATOR_IP" \
    -p pause_after_s:="$(printf '%.1f' "$OPERATOR_TIMEOUT_S")" \
    -p give_up_after_s:="$(printf '%.1f' "$OPERATOR_GIVE_UP_S")" \
    -p beep:="$beep" \
    > "$WATCH_LOG" 2>&1 < /dev/null &
  WATCH_PID=$!
  set +m
  # The waiter: when the watch ends for ANY reason while this script is still running
  # (it gave up, or it crashed), stop the mission. cleanup() kills this waiter before
  # it stops the watch itself.
  ( while kill -0 "$WATCH_PID" 2>/dev/null; do sleep 0.2; done
    kill -USR1 $$ ) &
  WATCH_WAITER_PID=$!
fi

# --- Nav2/EKF/mission_runner, containerized ---
echo "=== [robot-boot] running ${IMAGE} (real-robot context, operator ball placement) ==="
# RUNNER_TYPE=real_robot matches the convention every other real-robot telemetry row
# in this project already uses. MISSION2_SELF_REPORT=1: no ground-truth judging (no
# Gazebo on the real robot) — mission_runner logs each leg's own self-reported
# PASS/FAIL instead; analysis of the resulting logs/photos happens after, manually.
# ROBOT_MODE=mission is hardcoded here, never a variable — standalone power-on can
# never run a smoke test (design spec). skip_nav2 is NOT set here — its default
# (false) means Nav2 runs exactly as it always has.
# (The map is chosen just below.)
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
# Trying a Nav2 setting on the robot without a new image (2026-11-19): the container
# runs the image's own copy of nav2_params.yaml, and a new image is a push plus a full
# CI run. ROBOT_BOOT_NAV2_PARAMS=<file on the Jetson> mounts that file over both of the
# image's copies for this run only. For tuning runs; the value that works still has to
# be committed, or the next run without this variable silently goes back to the old one.
PARAMS_ARGS=()
if [ -n "${ROBOT_BOOT_NAV2_PARAMS:-}" ]; then
  if [ ! -f "$ROBOT_BOOT_NAV2_PARAMS" ]; then
    echo "FATAL: ROBOT_BOOT_NAV2_PARAMS=${ROBOT_BOOT_NAV2_PARAMS} is not a file" >&2
    exit 1
  fi
  echo "=== [robot-boot] WARNING: Nav2 parameters come from ${ROBOT_BOOT_NAV2_PARAMS}, NOT from the image ===" >&2
  PARAMS_ARGS=(-v "$ROBOT_BOOT_NAV2_PARAMS:/ros2_ws/install/nav_fleet/share/nav_fleet/config/nav2_params.yaml:ro"
               -v "$ROBOT_BOOT_NAV2_PARAMS:/ros2_ws/src/nav_fleet/config/nav2_params.yaml:ro")
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
  -e CYCLONEDDS_SCOPE="$CYCLONEDDS_SCOPE" \
  "${MAP_ARGS[@]}" \
  ${PARAMS_ARGS[@]+"${PARAMS_ARGS[@]}"} \
  -e MISSION2_SELF_REPORT=1 \
  -e RUNNER_TYPE=real_robot \
  -e ROBOT_MODE=mission \
  ${MISSION2_IGNORE_REACTIONS:+-e MISSION2_IGNORE_REACTIONS=1} \
  ${ROBOT_BOOT_NO_START_POSE_CHECK:+-e MISSION_START_POSE_CHECK=off} \
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
