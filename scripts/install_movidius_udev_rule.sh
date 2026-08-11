#!/bin/bash
# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
#
# Installs scripts/udev/80-movidius.rules (RealRobotStartup.md A2, OAK-D Lite
# camera). Previously a one-off `echo ... | sudo tee ...` line typed straight into
# a terminal from the doc -- moved to a real, versioned rules file + this installer
# so a replacement Jetson gets the exact same rule from source control instead of a
# retyped shell one-liner.
#
# Safe to re-run: `install -m 0644` overwrites idempotently; reload/trigger are
# both idempotent udev operations.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RULE_SRC="$REPO_DIR/scripts/udev/80-movidius.rules"
RULE_DST="/etc/udev/rules.d/80-movidius.rules"

echo "=== [install_movidius_udev_rule] installing ${RULE_DST} ==="
sudo install -m 0644 "$RULE_SRC" "$RULE_DST"
sudo udevadm control --reload-rules
sudo udevadm trigger

echo "=== [install_movidius_udev_rule] done ==="
echo "If the camera was already plugged in before this rule existed, unplug/replug"
echo "its USB cable once (or power-cycle the whole robot -- udevd's boot-time"
echo "coldplug pass re-applies rules to already-connected devices too)."
