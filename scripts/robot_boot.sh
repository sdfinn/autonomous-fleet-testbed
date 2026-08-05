#!/bin/bash
# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
#
# Boot-time entry point for the real, deployed Waveshare UGV-PT (RealRobotStartup.md
# Part A). Runs the SAME container image and the SAME entrypoint script HIL uses
# (scripts/container_entrypoint.sh) — only the launch-argument VALUES differ
# (real-robot context: use_sim_time=false, the real-camera HSV profile, the real
# room's map) — see docs/superpowers/specs/
# 2026-08-03-docker-brain-real-robot-hil-unification-design.md.
#
# No `docker pull`, no tag-selection scheme: whatever image is already sitting in
# this Jetson's local `docker images` cache is the image that runs — the one
# `scripts/hil_stage.sh sync <sha>` last checked out here, which is the SAME sha
# that image is tagged with (stage-3-arm64 tags every build with the commit sha).
# Get the exact HIL-tested commit onto this checkout BEFORE relying on this script
# (see RealRobotStartup.md Part A) — this script always runs whatever is currently
# checked out here, same as it always has.
#
# NOT yet exercised by CI/HIL — a power cycle can't be simulated there. Run this
# manually over SSH first and confirm a full mission2 day passes with your own eyes-on
# check before trusting the systemd unit (scripts/robot-mission.service) that calls it
# automatically at boot.
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

echo "=== [robot-boot] running ${IMAGE} (real-robot context, operator ball placement) ==="
# RUNNER_TYPE=real_robot matches the convention every other real-robot telemetry row
# in this project already uses. MISSION2_SELF_REPORT=1: no ground-truth judging (no
# Gazebo on the real robot) — mission_runner logs each leg's own self-reported
# PASS/FAIL instead; analysis of the resulting logs/photos happens after, manually.
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
  "$IMAGE" bash /ros2_ws/scripts/container_entrypoint.sh \
  2>&1 | tee "$LOG_DIR/robot_boot_${TS}.log"
