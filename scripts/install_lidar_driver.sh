#!/bin/bash
# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
#
# Idempotent lidar driver (ldlidar_ros2, D500/STL-19P) install for a fresh Jetson --
# RealRobotStartup.md A2. Clones the VENDOR repo (ldrobotSensorTeam/ldlidar_ros2,
# a separate upstream project, NOT part of autonomous-fleet-testbed) into
# ~/ros2_drivers_ws, applies the two real, confirmed-necessary local patches, then
# builds.
#
# Why this script exists instead of re-typing RealRobotStartup.md's shell commands
# by hand on the next Jetson: those commands genuinely worked (confirmed live,
# 2026-08-09), but only as prose in a markdown file -- not a versioned, re-runnable
# artifact. The doc's own text even flags the fragility directly ("verify the line
# number still matches yours... in case the vendor repo changes upstream"). A stored
# script that checks-before-patching is safe to run verbatim on a replacement unit;
# a person re-transcribing steps from a doc is not.
#
# Safe to re-run: clones only if the directory doesn't already exist; both patches
# check their target text first and no-op if already applied (or if the vendor
# happens to have already fixed it upstream); rosdep/colcon build always re-run
# (cheap, idempotent by nature).
set -euo pipefail

DRIVERS_WS="$HOME/ros2_drivers_ws"
LIDAR_PKG_DIR="$DRIVERS_WS/src/ldlidar_ros2"
LOG_MODULE_H="$LIDAR_PKG_DIR/sdk/include/ldlidar_driver/log_module.h"
LAUNCH_FILE="$LIDAR_PKG_DIR/launch/ld19.launch.py"

# This unit's real serial device (confirmed 2026-08-09 against actual hardware --
# lsusb showed a QinHeng Electronics USB Single Serial device, a CH340-family chip).
# A different physical unit might enumerate differently -- override via LIDAR_PORT.
LIDAR_PORT="${LIDAR_PORT:-/dev/ttyACM0}"

echo "=== [install_lidar_driver] rosdep init (one-time; safe to re-run) ==="
sudo rosdep init 2>/dev/null || echo "  (already initialized -- fine)"
rosdep update

if [ ! -d "$LIDAR_PKG_DIR" ]; then
  echo "=== [install_lidar_driver] cloning ldrobotSensorTeam/ldlidar_ros2 ==="
  mkdir -p "$DRIVERS_WS/src"
  git clone https://github.com/ldrobotSensorTeam/ldlidar_ros2.git "$LIDAR_PKG_DIR"
else
  echo "=== [install_lidar_driver] $LIDAR_PKG_DIR already exists -- skipping clone ==="
fi

echo "=== [install_lidar_driver] submodule (sdk/ -- a plain clone leaves it empty) ==="
( cd "$LIDAR_PKG_DIR" && git submodule update --init --recursive )

echo "=== [install_lidar_driver] vendor SDK compile bug -- restoring pthread.h ==="
# Confirmed 2026-08-09 against a known upstream issue (ldrobotSensorTeam/
# ldlidar_stl_ros2 issue #23, same underlying SDK code): the vendor SDK's own
# log_module.h ships with this #include commented out on its Linux branch, which
# fails to compile pthread_mutex_init/_lock/_unlock on a modern toolchain.
if grep -q '^//#include <pthread.h>' "$LOG_MODULE_H"; then
  sed -i 's|^//#include <pthread.h>|#include <pthread.h>|' "$LOG_MODULE_H"
  echo "  patched: $LOG_MODULE_H"
else
  echo "  already patched (or the vendor fixed it upstream) -- skipping"
fi

echo "=== [install_lidar_driver] port name -- pinning this unit's real port ==="
# The vendor's ld19.launch.py hardcodes /dev/ttyUSB0 with no CLI/LaunchConfiguration
# override at all (confirmed 2026-08-09 -- `ros2 launch ... --show-args` returned
# "No arguments"). LIDAR_PORT is overridable since a different physical unit might
# not enumerate the same way.
if grep -q "'/dev/ttyUSB0'" "$LAUNCH_FILE"; then
  sed -i "s|'/dev/ttyUSB0'|'$LIDAR_PORT'|" "$LAUNCH_FILE"
  echo "  patched: $LAUNCH_FILE -> $LIDAR_PORT"
elif grep -q "'$LIDAR_PORT'" "$LAUNCH_FILE"; then
  echo "  already patched to $LIDAR_PORT -- skipping"
else
  echo "  WARNING: neither '/dev/ttyUSB0' nor '$LIDAR_PORT' found in $LAUNCH_FILE --" >&2
  echo "  the vendor launch file may have changed upstream; check it by hand before trusting this." >&2
fi

echo "=== [install_lidar_driver] rosdep install + colcon build ==="
set +u
source /opt/ros/jazzy/setup.bash
set -u
(
  cd "$DRIVERS_WS"
  rosdep install --from-paths src --ignore-src -r -y
  colcon build --symlink-install --cmake-args=-DCMAKE_BUILD_TYPE=Release
)

echo "=== [install_lidar_driver] done -- 'source $DRIVERS_WS/install/setup.bash' to use ==="
echo "Reminder (separate, real permission requirement, not handled by this script):"
echo "  sudo usermod -a -G dialout \$USER   # then log out/in -- see RealRobotStartup.md"
