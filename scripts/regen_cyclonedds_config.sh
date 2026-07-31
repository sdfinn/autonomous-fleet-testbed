#!/bin/bash
# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
#
# Regenerates ~/cyclonedds-hil.xml based on which network interface(s) are actually
# UP right now on the Jetson — Ethernet (enP8p1s0) preferred when up, WiFi (wlP1p1s0)
# used as a fallback when it isn't. Run ON THE JETSON (hil_stage.sh's nav2_up() calls
# this over SSH, every HIL day, before Nav2 launches).
#
# Why this exists (2026-07-31, confirmed live): CycloneDDS's <NetworkInterface> list
# requires EVERY listed entry to correspond to a currently-up interface — a statically
# listed DOWN interface makes CycloneDDS hard-fail ("enP8p1s0: does not match an
# available interface"), not gracefully skip to the next-priority one. A static file
# listing both interfaces therefore breaks whichever one happens to be down at boot
# time, regardless of declared priority. This script never lists an interface that
# isn't actually up at generation time, so it's correct however the Jetson happens to
# be connected when it boots — no manual step needed either way.
set -euo pipefail

CONFIG_PATH="$HOME/cyclonedds-hil.xml"
ETH_IFACE="enP8p1s0"
WIFI_IFACE="wlP1p1s0"

iface_state() {
  # /sys/class/net/<iface>/operstate is the real, reliable link state ("up"/"down") —
  # not `ip link`'s administrative UP flag, which stays "UP" even with no cable
  # plugged in (that's exactly what caused this bug in the first place).
  cat "/sys/class/net/$1/operstate" 2>/dev/null || echo "down"
}

eth_state=$(iface_state "$ETH_IFACE")
wifi_state=$(iface_state "$WIFI_IFACE")

interfaces=""
if [ "$eth_state" = "up" ]; then
  interfaces="${interfaces}    <NetworkInterface name=\"${ETH_IFACE}\" priority=\"10\"/>
"
fi
if [ "$wifi_state" = "up" ]; then
  interfaces="${interfaces}    <NetworkInterface name=\"${WIFI_IFACE}\" priority=\"1\"/>
"
fi

if [ -z "$interfaces" ]; then
  echo "FATAL: neither ${ETH_IFACE} nor ${WIFI_IFACE} is up — no viable network interface" >&2
  exit 1
fi

cat > "$CONFIG_PATH" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<CycloneDDS xmlns="https://cdds.io/config">
  <Domain>
    <General>
      <Interfaces>
${interfaces}      </Interfaces>
    </General>
  </Domain>
</CycloneDDS>
EOF

echo "cyclonedds-hil.xml regenerated (eth=${eth_state}, wifi=${wifi_state}):"
cat "$CONFIG_PATH"
