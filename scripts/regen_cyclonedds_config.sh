#!/bin/bash
# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
#
# Regenerates ~/cyclonedds-hil.xml (or $CYCLONEDDS_CONFIG_PATH) from THIS machine's
# real current link state — Ethernet preferred over WiFi, whichever physical
# interface is actually up right now. Runs unmodified on both the Jetson (called by
# container_entrypoint.sh inside the container for both HIL and real robot) and the
# workstation (sim_up(), before the Gazebo/bridge launch) — auto-detects physical vs
# virtual interfaces instead of hardcoding names per machine, since the two
# machines' real interface names differ (enP8p1s0/wlP1p1s0 vs enp6s0/wlp5s0).
#
# Why this exists (2026-07-31, confirmed live, same day, same failure CLASS on both
# machines):
#   - On the Jetson: CycloneDDS's <NetworkInterface> list requires EVERY listed entry
#     to correspond to a currently-up interface — a statically listed DOWN interface
#     makes it hard-fail ("enP8p1s0: does not match an available interface"), not
#     gracefully fall back to the next-priority one. A static file listing both
#     interfaces therefore breaks whichever one happens to be down at boot time,
#     regardless of declared priority.
#   - On the workstation: sim_up() set NO CycloneDDS config at all, relying on
#     CycloneDDS's own default auto-selection — which picked `docker0` (a virtual
#     Docker bridge on an unrelated 172.17.0.0/16 subnet) over the real WiFi
#     interface, so the workstation's Gazebo/bridge topics never reached the Jetson
#     at all, even though both machines were mutually pingable (Jetson's own local
#     nodes came up fine in that same run — only cross-machine discovery was dark).
# This script never lists a down interface, and never lists a virtual one (no
# /sys/class/net/<iface>/device symlink — the standard way to tell a real NIC apart
# from a virtual bridge/veth/loopback on Linux), so it's correct on either machine,
# however it's connected, with no manual step or per-machine interface name list to
# maintain.
set -euo pipefail

CONFIG_PATH="${CYCLONEDDS_CONFIG_PATH:-$HOME/cyclonedds-hil.xml}"

is_physical() {
  [ -e "/sys/class/net/$1/device" ]
}

iface_state() {
  # /sys/class/net/<iface>/operstate is the real, reliable link state ("up"/"down") —
  # not `ip link`'s administrative UP flag, which stays "UP" even with no cable
  # plugged in (that's exactly what caused the Jetson-side bug in the first place).
  cat "/sys/class/net/$1/operstate" 2>/dev/null || echo "down"
}

# Ethernet-named interfaces (en*/eth*) get priority 10, WiFi-named (wl*) get priority 1
# — the standard systemd predictable-network-interface-naming convention holds on
# both machines, so this needs no per-machine interface name list. An unrecognized
# but genuinely physical, up interface still gets included (priority 5) rather than
# silently dropped.
priority_for() {
  case "$1" in
    en*|eth*) echo 10 ;;
    wl*)      echo 1 ;;
    *)        echo 5 ;;
  esac
}

interfaces=""
for iface_path in /sys/class/net/*; do
  iface="$(basename "$iface_path")"
  [ "$iface" = "lo" ] && continue
  is_physical "$iface" || continue
  [ "$(iface_state "$iface")" = "up" ] || continue
  interfaces="${interfaces}    <NetworkInterface name=\"${iface}\" priority=\"$(priority_for "$iface")\"/>
"
done

if [ -z "$interfaces" ]; then
  echo "FATAL: no physical, currently-up network interface found" >&2
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

echo "cyclonedds-hil.xml regenerated at ${CONFIG_PATH}:"
cat "$CONFIG_PATH"
