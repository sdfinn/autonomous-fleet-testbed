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
#
# The generated file's <Internal><SocketReceiveBufferSize> block (found live,
# 2026-08-09, bench-verified, folded in here 2026-08-10): CycloneDDS's default
# receive buffer is too small to deliver uncompressed sensor_msgs/Image at all —
# 'ros2 topic hz' on /oak/rgb/image_raw hung indefinitely with no error, while the
# same topic's compressed sibling worked immediately. A known, documented
# ROS2/CycloneDDS limitation with large messages, not a depthai-ros or
# project-specific bug. Additive to the Interfaces block above; doesn't touch
# interface-priority selection at all. The matching sysctl
# net.core.rmem_max=2147483647 half of this fix is a one-time, OS-level setting
# (see RealRobotStartup.md); not something this per-launch-regenerated file can
# express. This story was originally embedded as a long comment INSIDE the
# generated XML itself — moved here 2026-08-12 after it started printing to
# console on every single driver-layer/container start (twice per robot_boot.sh
# run), which was pure noise for routine operation; the XML's own comment is now
# a short pointer back to this file. NOTE: an XML comment body may never contain a
# literal double hyphen — a real parse failure confirmed that the hard way.
#
# CYCLONEDDS_SCOPE=local (2026-11-23): everything that talks is on THIS machine, so the
# messaging goes over the loopback interface and no network interface is listed at all.
# robot_boot.sh sets it for the real robot and hands it to the container. Why: on the
# real robot every process (drivers, detector, obstacle guard, and the container with
# Nav2 and the mission) runs on the one Jetson, yet they found each other through the
# WiFi interface's address. On 2026-11-20 and again on 2026-11-23 the router gave the
# Jetson a new address in the middle of a mission; the processes kept sending to the old
# one, could no longer hear each other, and the mission died a few meters from home.
# Loopback has no cable, no radio and an address that never changes.
#   - Loopback has no multicast, so discovery is by unicast to "localhost": each
#     process probes a list of participant slots. CycloneDDS's default list is 10
#     slots; this robot runs more processes than that, and a process beyond the list is
#     silently never found. MaxAutoParticipantIndex below is the list's length.
#   - Nothing off the machine can see these topics. That is the point; a later "mother
#     ship" or second robot gets a deliberate bridge for what should leave the robot.
#   - NOT for CI's Jetson stage (HIL), where Gazebo runs on the workstation and the two
#     machines really do talk over Ethernet: that path leaves the variable unset.
set -euo pipefail

CONFIG_PATH="${CYCLONEDDS_CONFIG_PATH:-$HOME/cyclonedds-hil.xml}"
SCOPE="${CYCLONEDDS_SCOPE:-network}"
LOCAL_MAX_PARTICIPANTS=120

case "$SCOPE" in
  network) ;;
  local)
    cat > "$CONFIG_PATH" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<CycloneDDS xmlns="https://cdds.io/config">
  <Domain>
    <General>
      <Interfaces>
        <NetworkInterface name="lo"/>
      </Interfaces>
      <AllowMulticast>false</AllowMulticast>
    </General>
    <Discovery>
      <ParticipantIndex>auto</ParticipantIndex>
      <MaxAutoParticipantIndex>${LOCAL_MAX_PARTICIPANTS}</MaxAutoParticipantIndex>
      <Peers>
        <Peer address="localhost"/>
      </Peers>
    </Discovery>
    <Internal>
      <!-- Large-message fix: see this script's header. An XML comment body may never
           contain a literal double hyphen. -->
      <SocketReceiveBufferSize min="10MB"/>
    </Internal>
  </Domain>
</CycloneDDS>
EOF
    echo "cyclonedds config regenerated at ${CONFIG_PATH} (this machine only: loopback, no network interface)"
    exit 0 ;;
  *)
    echo "FATAL: CYCLONEDDS_SCOPE must be 'network' or 'local', got '${SCOPE}'" >&2
    exit 1 ;;
esac

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
    <Internal>
      <!-- Large-message fix, 2026-08-09/10: see this script's own header comment
           for the full story. Kept short here on purpose (2026-08-12: the full
           version got printed to console on every single driver/container start,
           twice per run); do not lengthen without moving the story back out.
           An XML comment body may never contain a literal double hyphen. -->
      <SocketReceiveBufferSize min="10MB"/>
    </Internal>
  </Domain>
</CycloneDDS>
EOF

n_ifaces=$(grep -c NetworkInterface "$CONFIG_PATH")
echo "cyclonedds config regenerated at ${CONFIG_PATH} (${n_ifaces} interface(s) -- cat it to see the full file)"
