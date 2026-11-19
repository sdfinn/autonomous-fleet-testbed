#!/bin/bash
# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
#
# Make sure the bare-metal colcon install of nav_fleet has a launcher for every node
# setup.py declares; rebuild the package if one is missing.
#
#   scripts/ensure_nav_fleet_built.sh <repo_dir>      (ROS must already be sourced)
#
# Why (2026-11-18): the Jetson's workspace is a --symlink-install build from
# 2026-08-11 and `hil_stage.sh sync` deliberately no longer rebuilds it. Edits to
# existing Python files reach it through the symlinks, so that went unnoticed -- but a
# NEW console script (slip_monitor) has no launcher in install/ until the next build,
# and drivers_only_launch.py would die with "executable 'slip_monitor' not found",
# taking the whole driver layer with it. Called by robot_boot.sh and
# robot_map_drive.sh before they source install/setup.bash. Costs nothing when the
# install is current; a rebuild takes a few seconds and needs no network.
set -euo pipefail

REPO="${1:?usage: ensure_nav_fleet_built.sh <repo_dir>}"
SETUP_PY="$REPO/src/nav_fleet/setup.py"
BIN_DIR="$REPO/install/nav_fleet/lib/nav_fleet"
[ -f "$SETUP_PY" ] || { echo "FATAL: $SETUP_PY not found -- is $REPO a checkout?" >&2; exit 1; }

missing=()
while read -r name; do
  [ -x "$BIN_DIR/$name" ] || missing+=("$name")
done < <(grep -oE "'[A-Za-z0-9_]+ *= *nav_fleet\.[A-Za-z0-9_.]+:[A-Za-z0-9_]+'" "$SETUP_PY" \
           | sed -E "s/^'([A-Za-z0-9_]+).*/\1/")

if [ "${#missing[@]}" -eq 0 ]; then
  exit 0
fi
echo "=== [ensure-built] install/ has no launcher for: ${missing[*]} -- rebuilding nav_fleet ==="
BUILD_LOG="$REPO/log/ensure_nav_fleet_built.log"
mkdir -p "$REPO/log"
if ! (cd "$REPO" && colcon build --symlink-install --packages-select nav_fleet) > "$BUILD_LOG" 2>&1; then
  echo "FATAL: colcon build failed -- see $BUILD_LOG" >&2
  tail -n 20 "$BUILD_LOG" >&2 || true
  exit 1
fi
for name in "${missing[@]}"; do
  [ -x "$BIN_DIR/$name" ] || { echo "FATAL: still no launcher for $name after the rebuild -- see $BUILD_LOG" >&2; exit 1; }
done
echo "=== [ensure-built] nav_fleet rebuilt ==="
