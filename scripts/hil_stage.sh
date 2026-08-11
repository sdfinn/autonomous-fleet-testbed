#!/usr/bin/env bash
# scripts/hil_stage.sh — stage-4-hil orchestration (design: docs/session15-hil-ci-stage-design.md).
# Runs identically from a local shell and from the CI job — debug locally first (Tier-1 rule).
#
# Subcommands:
#   discover          print the Jetson's current IP (mDNS first, ip-neigh fallback), verify SSH
#   power-mode        set nvpmodel mode $POWER_MODE_ID on the Jetson and print it
#   sync <sha>        fetch+checkout <sha> on the Jetson (no build — the checkout only identifies which commit is under test)
#   run               HIL STACK GATE (Task 13b): clean STATE_DIR, then sim-up (workstation
#                     Gazebo). Nav2 bring-up happens later inside the container as part of day(). NO mission, NO retry — a mission failure
#                     must be RED (the in-process nav_runner cold-goal retry, Task 13a, is the
#                     only retry left; harness-level whole-mission retries were removed).
#   day               THE Mission 2 day (Task 13d): runs tools/mission2_day.py in HIL mode
#                     against the stack `run` brought up — no_ball -> yellow (swap to red
#                     during its return) -> red (stays). The mission executes on the Jetson;
#                     ball ops + ground-truth judging stay workstation-side. Judged verdicts +
#                     per-waypoint checklists print per run; photos land in reports/photos/ AND
#                     STATE_DIR (CI evidence). This is the ONE stage-4 test step.
#   teardown          kill both sides (safe to run any time; used by CI's if:always() step)
#   restore-checkout  checkout main on the Jetson (run once at the very end)
#   smoke <sha>       Bench smoke test (attended — prompts for ball placement over
#                      this same SSH session). Real-robot-only (USE_SIM_TIME=false).
#   smoke-ci <sha>     CI-only counterpart — non-interactive, GzBallOps, USE_SIM_TIME=true.
#                      Never run by hand; ci.yml's stage-4-hil is the only caller.
set -euo pipefail

JETSON_USER="${JETSON_USER:-mike}"
POWER_MODE_ID="${POWER_MODE_ID:-1}"
STATE_DIR="${STATE_DIR:-/tmp/hil_stage}"
SIM_LOG="${STATE_DIR}/sim.log"
JETSON_REPO='~/autonomous-fleet-testbed'
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# Ghost-ball settle (CLAUDE.md Gotchas, 2026-07-17): the headless llvmpipe renderer keeps a
# REMOVED model in camera frames for seconds — wait this long after remove_ball so the next
# rung never reacts to the previous rung's ball. Mirrors tests/test_mission2.py's constant.
BALL_REMOVAL_SETTLE_S="${BALL_REMOVAL_SETTLE_S:-3}"

# Every remote ROS command must source its own env — non-interactive SSH skips .bashrc.
# MAGICK_THREAD_LIMIT/OMP: GraphicsMagick (nav2 map_server's image loader) SIGSEGVs on the
# Jetson's ARM build under threading — killed Nav2 twice on 2026-07-18 (once mid-day during
# lifecycle respawn-recovery, once at startup). Single-threading it is the known workaround.
# CYCLONEDDS_URI (2026-07-30): CycloneDDS's default interface auto-selection picks the first
# viable multicast-capable interface by ifindex, not necessarily the one that reaches the
# workstation. Confirmed live via `ip maddr show`: once the Jetson's WiFi (wlP1p1s0, ifindex 2)
# came up, CycloneDDS joined its discovery multicast group (239.255.0.1) on WiFi instead of
# Ethernet (enP8p1s0, ifindex 5) — the workstation is only reachable via Ethernet, so cross-
# machine discovery broke silently (Nav2 came up locally, map_server/amcl activated fine, but
# were completely invisible from the workstation and vice versa; survived both a soft reboot
# and a hard power cycle, since WiFi auto-reconnects and CycloneDDS re-picks it every time).
# Fix: ~/cyclonedds-hil.xml on the Jetson explicitly lists BOTH interfaces with Ethernet
# given a higher priority (10 vs WiFi's 1 — higher wins, CycloneDDS docs) — Ethernet stays
# preferred whenever it's up, WiFi remains configured as a genuine fallback if Ethernet is
# ever disconnected (the untethered-robot scenario), rather than pinning to Ethernet ONLY
# (an earlier, narrower version of this fix — corrected same day after Mike pointed out
# untethered operation needs WiFi to still work when Ethernet is unplugged). See CLAUDE.md's
# matching gotcha.
#
# UPDATE (2026-07-31): this file is now REGENERATED fresh, from real link state, before
# every launch — see scripts/regen_cyclonedds_config.sh, called by sim_up() (workstation)
# and by container_entrypoint.sh inside the container (Jetson). Two more real bugs found the same day, same failure class:
# (1) a statically-listed DOWN interface makes CycloneDDS hard-fail outright ("X: does not
# match an available interface"), not gracefully skip to the next-priority one — so the
# static file above broke the moment Ethernet was actually unplugged, regardless of
# priority; (2) sim_up() had NO CycloneDDS config at all, so its own default auto-selection
# picked docker0 (a virtual bridge on an unrelated subnet) over the workstation's real WiFi
# interface. Even with both fixed, cross-machine DDS discovery over WiFi ALONE still didn't
# work in live testing (Nav2's local_costmap never received the workstation's `map`
# transform) — leading theory is WiFi AP/client isolation or multicast filtering on the
# router, not investigated further. Recommendation: use Ethernet for HIL day-to-day — the
# REAL, deployed robot doesn't need WiFi validated at all (everything it does is
# self-contained on one Jetson, loopback-only), so there's no R1 payoff to chasing this.
JENV='source /opt/ros/jazzy/setup.bash && source ~/autonomous-fleet-testbed/install/setup.bash && export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp ROS_DOMAIN_ID=0 CYCLONEDDS_URI=file://$HOME/cyclonedds-hil.xml MAGICK_THREAD_LIMIT=1 OMP_NUM_THREADS=1'

case "$POWER_MODE_ID" in
  0) POWER_MODE_LABEL=15W ;;
  1) POWER_MODE_LABEL=25W ;;
  2) POWER_MODE_LABEL=MAXN_SUPER ;;
  *) echo "FATAL: unknown POWER_MODE_ID=$POWER_MODE_ID" >&2; exit 1 ;;
esac

jssh() { ssh -o ConnectTimeout=10 -o BatchMode=yes -o StrictHostKeyChecking=accept-new "${JETSON_USER}@${JETSON_IP}" "$@"; }

require_ip() {
  [ -n "${JETSON_IP:-}" ] || { echo "FATAL: JETSON_IP not set (run discover first)" >&2; exit 1; }
}

# Query the Jetson's ACTUAL nvpmodel state rather than trusting POWER_MODE_ID's env-var
# label. Found 2026-07-26 (Piece 2 perf pass): a manual `nvpmodel -m 0` run without also
# exporting POWER_MODE_ID=0 silently mislabeled 3 telemetry rows as 25W while the hardware
# was really at 15W the whole time — corrupted the drift baseline's 25W slice until caught
# and fixed by hand. `day` now derives its telemetry label from this live query;
# POWER_MODE_ID/POWER_MODE_LABEL above remain the REQUESTED mode for `power_mode()` (setting
# it), never trusted as a label for what actually happened. `nvpmodel -q` needs no sudo.
# Falls back to the requested label (with a loud WARNING) only if the live query itself
# fails — a labeling nicety should never abort a mission day.
real_power_mode_label() {
  local q parsed
  if q=$(jssh "nvpmodel -q 2>/dev/null" 2>/dev/null) && [ -n "$q" ]; then
    parsed=$(echo "$q" | awk -F': ' '/NV Power Mode/ {print $2; exit}')
  else
    parsed=""
  fi
  # Validate against the same known-label set POWER_MODE_ID's case statement enforces on
  # the requested side (found in second-round review, 2026-07-26): an `nvpmodel -q` output
  # that doesn't match the expected "NV Power Mode: <label>" line — or any other unexpected
  # format — made awk fall through with no match, silently returning an EMPTY string. That
  # empty POWER_MODE then landed in a telemetry row and failed `validate_telemetry.py`'s
  # schema check for every later stage-5-reports-* job until someone edited the bad row by
  # hand — exactly what this function's own "never abort a mission day" comment promises
  # NOT to do. Any parse failure or unrecognized value now falls back the same way an SSH
  # failure already did.
  case "$parsed" in
    15W|25W|MAXN_SUPER) echo "$parsed" ;;
    *)
      echo "WARN: could not determine a valid live nvpmodel state on the Jetson (got '${parsed}') — falling back to POWER_MODE_ID=${POWER_MODE_ID} (${POWER_MODE_LABEL}); telemetry label may not reflect real hardware state" >&2
      echo "$POWER_MODE_LABEL"
      ;;
  esac
}

discover() {
  local ip
  ip=$(getent hosts jetson.local | awk '{print $1; exit}' || true)
  if [ -z "$ip" ]; then
    ip=$(ip neigh show dev enp6s0 | awk '$1 ~ /^10\.42\.0\./ && /lladdr/ {print $1; exit}' || true)
  fi
  [ -n "$ip" ] || { echo "FATAL: cannot discover Jetson IP (mDNS and ip-neigh both empty — is it powered on and cabled?)" >&2; exit 1; }
  ssh -o ConnectTimeout=10 -o BatchMode=yes -o StrictHostKeyChecking=accept-new "${JETSON_USER}@${ip}" true \
    || { echo "FATAL: SSH to ${JETSON_USER}@${ip} failed" >&2; exit 1; }
  echo "$ip"
}

power_mode() {
  require_ip
  jssh "sudo -n nvpmodel -m ${POWER_MODE_ID} && sudo -n nvpmodel -q"
}

sync() {
  require_ip
  local sha="${1:?usage: hil_stage.sh sync <git-sha>}"
  # git reset --hard + git clean -fd (2026-08-11, found live): a plain `git checkout
  # --detach FETCH_HEAD` correctly REFUSES to overwrite any local change on the
  # Jetson's native checkout -- which sounds safe, but this checkout is the ONE
  # shared target for CI's own sync AND every live-hardware-verification workflow
  # that touches this exact directory (this project's whole terminal-in-hand-with-
  # Claude-over-SSH bring-up pattern edits/rsyncs files here directly). A single
  # leftover local edit -- from live debugging, a half-finished manual test, an
  # rsync'd file never committed/cleaned up -- silently blocks EVERY future CI run
  # on this stage until someone notices the log and cleans it by hand (recurred
  # twice now: 2026-08-10 and again 2026-08-11, same failure signature both times).
  # This function's own job is "make the Jetson match commit X" -- nothing about
  # that job requires preserving local state, so make it self-healing instead of
  # failing hard: `git reset --hard` discards tracked-file edits, `git clean -fd`
  # (no `-x`) removes untracked files WITHOUT touching anything gitignored.
  # IMPORTANT, found live testing THIS fix (2026-08-11): reports/ is only safe from
  # `git clean` to the extent .gitignore actually covers every filename pattern
  # written there -- the first version of this fix was tested against a real dirty
  # Jetson tree and genuinely deleted 6 real reports/sensors_container_*.log files
  # that .gitignore had never covered (only reports/nav2_container_*.log was listed,
  # not sensors_container_*.log -- a real, separate gap, now fixed in .gitignore
  # alongside this). If a NEW container_entrypoint.sh branch ever writes a report
  # file under a name not already covered there, this function WILL delete it on
  # the next sync -- keep .gitignore's reports/ coverage current, don't assume this
  # comment's claim as a substitute for checking.
  jssh "cd ${JETSON_REPO} && git fetch origin ${sha} && git reset --hard FETCH_HEAD && git clean -fd"
  # No bare colcon build any more (docker-brain unification, 2026-08) — the checkout
  # persists here for two reasons: (a) it's the bind-mount target for reports/
  # (HIL's photo/log evidence lands here), and (b) robot_boot.sh reads `git rev-parse
  # HEAD` from this exact checkout to pick which image tag to run.
}

clean_state() {
  # STATE_DIR hygiene (Task 13g): the self-hosted runner's STATE_DIR persists across runs, so
  # a prior local-prove run's photos/logs/JSON otherwise contaminate this run's CI evidence
  # artifact and can even satisfy a judge's photo-presence check with stale data. Wipe first.
  mkdir -p "$STATE_DIR"
  rm -f "$STATE_DIR"/*.png "$STATE_DIR"/*.out "$STATE_DIR"/*.json \
        "$STATE_DIR"/mission2_day.log "$STATE_DIR"/nav2_container_*.log 2>/dev/null || true
}

sim_up() {
  echo '=== [sim-up] launching Gazebo sim half (budget 60s) ==='
  mkdir -p "$STATE_DIR"
  cd "$REPO_DIR"
  # ROS2's setup.bash references unbound vars internally (e.g. AMENT_TRACE_SETUP_FILES) —
  # incompatible with this script's `set -u`. Relax it only around the sourcing.
  set +u
  source /opt/ros/jazzy/setup.bash
  source install/setup.bash
  set -u
  # Regenerate this machine's OWN cyclonedds config from its real current link state
  # (2026-07-31) — sim_up() previously set no CycloneDDS config at all, so CycloneDDS's
  # default auto-selection picked docker0 (a virtual Docker bridge on an unrelated
  # subnet) over the real WiFi interface, silently keeping every Gazebo/bridge topic
  # from ever reaching the Jetson even though the machines could ping each other fine.
  # Same script container_entrypoint.sh runs inside the container on the Jetson side —
  # auto-detects physical vs virtual interfaces, so it needs no per-machine interface name list.
  bash scripts/regen_cyclonedds_config.sh
  export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp ROS_DOMAIN_ID=0 \
    CYCLONEDDS_URI="file://$HOME/cyclonedds-hil.xml"
  # setsid: own process group, so teardown's kill -INT -<pid> signals the whole launch tree.
  setsid ros2 launch src/nav_fleet/launch/sim_only_launch.py > "$SIM_LOG" 2>&1 &
  local deadline=$((SECONDS + 60))
  until grep -q 'gz.msgs.Clock' "$SIM_LOG" 2>/dev/null; do
    if (( SECONDS >= deadline )); then
      echo 'FATAL: sim/bridge not up within 60s — sim log tail:' >&2
      tail -n 40 "$SIM_LOG" >&2 || true
      return 1
    fi
    sleep 2
  done
  sleep 3   # let the bridge's subscriptions settle after the creation log lines
  echo '=== [sim-up] bridge up ==='
}

run() {
  # HIL stack GATE (Task 13b, narrowed 2026-08 for the docker-brain unification):
  # clean state, bring up ONLY the workstation's Gazebo half — Nav2/EKF/
  # ball_detector now start INSIDE the container as part of `day()`'s one-shot
  # run (see container_entrypoint.sh), not as a separate bare pre-step.
  clean_state
  sim_up
}

day() {
  # THE Mission 2 day (Task 13d) — tools/mission2_day.py in HIL mode against the stack `run`
  # brought up. The mission runs on the Jetson inside the container via container_entrypoint.sh;
  # ball ops + ground-truth judging + telemetry all stay workstation-side. The orchestrator scps
  # each run's photos to reports/photos/ AND STATE_DIR (CI evidence) and prints per-run judged
  # verdicts + waypoint checklists. FLEET_DB (when set) receives the JUDGED rows directly here —
  # no SSH row-shipping, because the judge runs on the workstation where FLEET_DB lives.
  require_ip
  ws_source
  local live_power_label
  live_power_label="$(real_power_mode_label)"
  RUNNER_TYPE=hil_jetson POWER_MODE="${live_power_label}" JETSON_IP="${JETSON_IP}" \
    JETSON_USER="${JETSON_USER}" STATE_DIR="${STATE_DIR}" \
    PYTHONUNBUFFERED=1 python3 -u -m tools.mission2_day --executor jetson --no-launch \
      --hold-s "${DAY_HOLD_S:-0}"
}

ws_source() {
  # Workstation-side ROS env (mirrors sim_up): cd the repo so `python3 -m tools.mission2_harness`
  # resolves and `gz` is on PATH for ground truth; source ROS + overlay; set DDS. Relax `set -u`
  # only around ROS's setup.bash, which references unbound vars internally.
  cd "$REPO_DIR"
  set +u
  source /opt/ros/jazzy/setup.bash
  source install/setup.bash
  set -u
  export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp ROS_DOMAIN_ID=0
}

smoke() {
  # Bench smoke test (real-robot driver + smoke-test design spec, 2026-08-05/06,
  # redesigned 2026-08-10 -- see docs/superpowers/plans/2026-08-10-drivers-bare-
  # metal-boot-fix.md): exercises the REAL production interface -- EKF +
  # ball_detector running INSIDE the container (nav2_only_launch.py,
  # skip_nav2:=true), talking to the real driver layer bare-metal outside it --
  # not a bare-metal stand-in for EKF/ball_detector. Only the driver layer
  # (vendor lidar/camera packages, never installed in the image, and per this
  # project's architecture never should be) runs bare-metal. ATTENDED: this
  # prompts you, via THIS terminal, to place the yellow ball.
  require_ip
  local sha="${1:?usage: hil_stage.sh smoke <git-sha>}"
  sync "$sha"

  local image="ghcr.io/sdfinn/autonomous-fleet-testbed:${sha}"
  echo "=== [smoke] checking ${image} is present locally on the Jetson ==="
  if ! jssh "docker image inspect ${image} >/dev/null 2>&1"; then
    echo "FATAL: ${image} is not present locally on the Jetson -- sync to a sha a" >&2
    echo "green stage-3-arm64 run already pushed, or docker pull it by hand first." >&2
    exit 1
  fi

  local hsv="${HSV_CONFIG_FILE:-hsv_gazebo.yaml}"
  # I5 (2026-08-11): a silent hsv_gazebo.yaml (SIM color thresholds) default here
  # can make the ball-correlation check false-FAIL against the real camera, and
  # the operator (present for exactly this check) would have no idea why.
  if [ -z "${HSV_CONFIG_FILE:-}" ]; then
    echo "WARNING: HSV_CONFIG_FILE is unset -- defaulting to hsv_gazebo.yaml (SIM color" >&2
    echo "thresholds). The ball-correlation check below runs against a REAL camera and" >&2
    echo "may false-FAIL until hsv_realcam.yaml exists (RealRobotStartup.md A4). Set" >&2
    echo "HSV_CONFIG_FILE=hsv_realcam.yaml once it does." >&2
  fi

  # I4 (2026-08-11): a prior container-mode run can leave ~/fleet-ci-data
  # root-owned on the Jetson (CLAUDE.md Gotchas, 2026-07-22), which breaks THIS
  # bare-metal tools.smoke_test write with a PermissionError that looks like a
  # driver problem, not a permissions one. Cheap, non-blocking check -- warn,
  # don't FATAL.
  local fleet_ci_owner
  fleet_ci_owner=$(jssh "stat -c '%U' \$HOME/fleet-ci-data 2>/dev/null || true")
  if [ -n "$fleet_ci_owner" ] && [ "$fleet_ci_owner" != "${JETSON_USER}" ]; then
    echo "WARNING: ~/fleet-ci-data on the Jetson is owned by '${fleet_ci_owner}', not" >&2
    echo "'${JETSON_USER}' -- tools.smoke_test's bare-metal write below may hit a" >&2
    echo "PermissionError. Likely a prior container-mode run left it root-owned. Fix:" >&2
    echo "  ssh ${JETSON_USER}@${JETSON_IP} 'sudo chown -R ${JETSON_USER}:${JETSON_USER} \$HOME/fleet-ci-data'" >&2
  fi

  # I3 (2026-08-11): a teardown trap, not just an explicit block at the end -- an
  # operator Ctrl+C at the ball-placement prompt below (likely, in an attended
  # test) previously killed this script and left the bare-metal driver layer AND
  # the detached container running, orphaned. Fires on EVERY exit path (normal
  # completion, a FATAL exit 1 above/below, or a signal) -- this is now the SOLE
  # teardown mechanism (no separate explicit block later, so nothing races or
  # double-runs it); every command inside is already `|| true`-guarded, safe to
  # call even before anything was ever started (e.g. the image-not-present FATAL
  # above).
  cleanup_smoke() {
    echo "=== [smoke] tearing down the container and the bare-metal driver layer ==="
    jssh "docker rm -f hil_smoke_test" >/dev/null 2>&1 || true
    jssh "pkill -INT -f '[r]os2 launch nav_fleet drivers_only_launch.py'" || true
  }
  trap cleanup_smoke EXIT

  echo "=== [smoke] starting the real driver layer bare-metal ==="
  # set -m (job control) bracketed tightly around ONLY the backgrounding line --
  # confirmed live 2026-08-11 (Task 5 investigation) that a plain (non -t) `ssh
  # host "cmd &"` invocation hits the EXACT SAME bug Task 3 found for
  # robot_boot.sh's local backgrounding: bash auto-sets SIGINT/SIGQUIT to
  # SIG_IGN for a job backgrounded from a non-interactive shell with job
  # control off -- which describes this remote subshell too (no -t means no
  # pty, so the remote bash is non-interactive regardless of BatchMode).
  # Verified directly via /proc/<pid>/status: without set -m, a backgrounded
  # `sleep 300 &` here showed SigIgn=0000000000000006 (bits 1+2 = SIGINT +
  # SIGQUIT) and a follow-up `kill -INT` on it was a confirmed silent no-op;
  # with set -m bracketing the launch line (matching robot_boot.sh's own
  # pattern exactly), SigIgn dropped to 0000000000000001 (SIGHUP only, from
  # nohup) and `kill -INT` killed it cleanly. Without this, cleanup_smoke's
  # `pkill -INT` above would silently never stop the driver layer.
  # I1 (2026-08-11): ldlidar_ros2 lives in its own separate overlay
  # (~/ros2_drivers_ws), normally sourced by .bashrc -- which this non-
  # interactive SSH subshell never runs. robot_boot.sh already hit and fixed
  # "package 'ldlidar_ros2' not found" this exact way (Task 3); this subshell
  # never picked that fix up until now.
  # C2 (2026-08-11): this bare-metal driver layer previously got NO
  # RMW_IMPLEMENTATION/CYCLONEDDS_URI export at all under this non-interactive
  # SSH path -- it silently defaulted to ROS2's own default RMW (FastDDS),
  # while the container ALWAYS hardcodes rmw_cyclonedds_cpp
  # (container_entrypoint.sh) -- zero DDS traffic would ever cross the driver-
  # layer/container boundary, reproducing this whole plan's original bug in a
  # new form, invisibly.
  jssh "cd ${JETSON_REPO} && \
    (source /opt/ros/jazzy/setup.bash; source install/setup.bash; \
     [ -f \$HOME/ros2_drivers_ws/install/setup.bash ] && source \$HOME/ros2_drivers_ws/install/setup.bash; \
     bash scripts/regen_cyclonedds_config.sh; \
     export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp ROS_DOMAIN_ID=0 CYCLONEDDS_URI=file://\$HOME/cyclonedds-hil.xml; \
     rm -f /tmp/smoke_drivers.log; \
     set -m; \
     nohup ros2 launch nav_fleet drivers_only_launch.py \
       serial_device:=${SERIAL_DEVICE:-/dev/ttyTHS1} \
       serial_baud:=${SERIAL_BAUD:-115200} \
       lidar_launch_file:=\$HOME/ros2_drivers_ws/install/ldlidar_ros2/share/ldlidar_ros2/launch/ld19.launch.py \
       camera_launch_file:=/opt/ros/jazzy/share/depthai_ros_driver/launch/camera.launch.py \
       > /tmp/smoke_drivers.log 2>&1 < /dev/null & \
     set +m)"

  echo "=== [smoke] waiting up to 60s for the driver layer to report up ==="
  # I2 (2026-08-11): the old single 'camera_relay up' check could report the
  # whole driver layer "up" even with NO lidar and NO odometry actually running
  # -- camera_relay/scan_masker start regardless of whether esp32_driver/
  # ldlidar_ros2/depthai-ros themselves came up. Require all 4 real confirmation
  # lines (task-1-report.md's own live-verified log excerpt) before proceeding.
  local deadline=$((SECONDS + 60))
  local esp32_up=0 lidar_up=0 camera_up=0 relay_up=0
  until [ "$esp32_up" -ge 1 ] && [ "$lidar_up" -ge 1 ] \
        && [ "$camera_up" -ge 1 ] && [ "$relay_up" -ge 1 ]; do
    if (( SECONDS >= deadline )); then
      echo "FATAL: driver layer not fully up within 60s on the Jetson (esp32_driver=${esp32_up} ldlidar=${lidar_up} camera=${camera_up} camera_relay=${relay_up}) -- see" >&2
      echo "/tmp/smoke_drivers.log there:" >&2
      jssh "tail -n 40 /tmp/smoke_drivers.log" >&2 || true
      exit 1
    fi
    sleep 2
    esp32_up=$(jssh "grep -c 'esp32_driver up' /tmp/smoke_drivers.log 2>/dev/null || true")
    esp32_up="${esp32_up:-0}"
    lidar_up=$(jssh "grep -c 'ldlidar communication is normal' /tmp/smoke_drivers.log 2>/dev/null || true")
    lidar_up="${lidar_up:-0}"
    camera_up=$(jssh "grep -c 'Camera with MXID' /tmp/smoke_drivers.log 2>/dev/null || true")
    camera_up="${camera_up:-0}"
    relay_up=$(jssh "grep -c 'camera_relay up' /tmp/smoke_drivers.log 2>/dev/null || true")
    relay_up="${relay_up:-0}"
  done
  echo "=== [smoke] driver layer up ==="

  echo "=== [smoke] starting EKF+ball_detector in the container (ROBOT_MODE=smoke_test) ==="
  jssh "docker rm -f hil_smoke_test 2>/dev/null || true; \
    docker run -d --name hil_smoke_test --network host --ipc host \
      -v \$HOME/autonomous-fleet-testbed/reports:/ros2_ws/reports \
      -v \$HOME/fleet-ci-data:/root/fleet-ci-data \
      -e USE_SIM_TIME=false -e HSV_CONFIG_FILE=${hsv} \
      -e ROBOT_MODE=smoke_test \
      ${image} bash /ros2_ws/scripts/container_entrypoint.sh"

  echo "=== [smoke] waiting up to 60s for EKF+ball_detector to report up in the container ==="
  local count=0
  deadline=$((SECONDS + 60))
  until [ "$count" -ge 1 ]; do
    if (( SECONDS >= deadline )); then
      echo "FATAL: EKF+ball_detector not up within 60s in the container -- see" >&2
      jssh "docker logs hil_smoke_test 2>&1 | tail -n 40" >&2 || true
      exit 1
    fi
    sleep 2
    count=$(jssh "docker logs hil_smoke_test 2>&1 | grep -c 'ball_detector up' || true")
    count="${count:-0}"
  done
  echo "=== [smoke] EKF+ball_detector up in the container -- running the smoke test"
  echo "(you will be prompted to place the yellow ball when the correlation check"
  echo "starts) =="
  # Plain SSH (no docker -it involved this time -- that's exactly what broke the
  # OLD container-based invocation in a non-interactive tool environment on
  # 2026-08-10). -t is still used here purely to match every other attended step
  # in this file; a bare python3 input() prompt doesn't actually need a pty.
  #
  # Deliberate `|| rc=$?` (not a bare `rc=$?` on the next line): under this
  # file's own `set -euo pipefail`, capturing this command's exit code via a
  # bare assignment on the line *after* it would trigger an immediate script
  # exit if the smoke test FAILs -- but cleanup_smoke (above, via `trap ... EXIT`)
  # always runs regardless of how this function exits, so this no longer needs
  # to dodge `set -e` for teardown's sake the way it originally did; kept as-is
  # since it's still the correct way to capture a non-zero exit code without
  # `set -e` aborting this line itself.
  local rc=0
  ssh -t -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new \
    "${JETSON_USER}@${JETSON_IP}" \
    "cd ${JETSON_REPO} && source /opt/ros/jazzy/setup.bash && source install/setup.bash && \
     python3 -m tools.smoke_test --runner-type real_robot" || rc=$?

  return "$rc"
}

smoke_ci() {
  # CI-only counterpart to smoke() — non-interactive (no -t, no operator prompt):
  # SMOKE_BALL_OPS=gz makes tools/smoke_test.py place the ball itself via GzBallOps,
  # same mechanism mission2_day.py's own CI regression already uses. Never used from
  # a human bench session — that's smoke(), above. USE_SIM_TIME=true so
  # sensors_only_launch.py skips esp32_driver/ldlidar_ros2/depthai-ros entirely and
  # relies on the WORKSTATION's Gazebo bridge reaching the Jetson over DDS — the
  # same cross-machine pattern day()'s mission-mode container run already uses.
  # Precondition: run() (sim_up) must already be up, same as day().
  require_ip
  local sha="${1:?usage: hil_stage.sh smoke-ci <git-sha>}"

  local image="ghcr.io/sdfinn/autonomous-fleet-testbed:${sha}"
  if ! jssh "docker image inspect ${image} >/dev/null 2>&1"; then
    echo "FATAL: ${image} is not present locally on the Jetson" >&2
    exit 1
  fi

  jssh "docker rm -f hil_smoke_test_ci 2>/dev/null || true; \
        docker run --rm --name hil_smoke_test_ci --network host --ipc host \
          -v \$HOME/autonomous-fleet-testbed/reports:/ros2_ws/reports \
          -v \$HOME/fleet-ci-data:/root/fleet-ci-data \
          -e USE_SIM_TIME=true -e HSV_CONFIG_FILE=hsv_gazebo.yaml \
          -e ROBOT_MODE=smoke_test -e SMOKE_BALL_OPS=gz -e RUNNER_TYPE=hil_jetson \
          -e COMMIT_SHA=${sha} -e CI_RUN_NUMBER=${CI_RUN_NUMBER:-} \
          ${image} bash /ros2_ws/scripts/container_entrypoint.sh"
}

teardown() {
  echo '=== [teardown] both sides ==='
  if [ -n "${JETSON_IP:-}" ]; then
    # ekf_node added 2026-07-26 (Session 17 Piece 2 perf pass): this pattern predates the
    # CLAUDE.md gotcha's "COMPLETE teardown pattern" (2026-07-15) and never picked up
    # ekf_node — found live, an orphaned ekf_node survived teardown and had to be killed by
    # hand. That gotcha's fix only ever reached ci.yml's stage-2 sweep, not this function.
    # ball_detector added 2026-07-26 (second-round code review, same day): confirmed LIVE
    # orphans on the Jetson (2 stale processes, oldest ~2h) — its cmdline contains
    # "nav_fleet", not "nav2", so it matched NONE of the four sweep sites in the repo
    # (this one, ci.yml's stage-2 sweep, mission2_day.py's _SWEEP_PATTERNS, and the
    # verification pgrep that prints "clean — no orphans remain"). Not cosmetic: extra
    # publishers on /robot_001/detections raise the effective detection frame rate, which
    # shortens REACTION_FRAMES's time-to-trigger — a silent confound on Mission 2's
    # reaction-distance judging.
    # drivers_only_launch/esp32_driver/ldlidar/depthai/scan_masker/camera_relay added
    # 2026-08-11 (final-review I3): the driver-layer processes Task 5's smoke()
    # starts bare-metal weren't part of this sweep at all -- a general `hil_stage.sh
    # teardown` call couldn't clean up an orphaned driver layer (e.g. after a crash
    # that skipped smoke()'s own cleanup_smoke trap).
    jssh "pkill -9 -f '[n]av2|[c]omponent_container|[m]ission_runner|[e]kf_node|[b]all_detector|[d]rivers_only_launch|[e]sp32_driver|[l]dlidar|[d]epthai|[s]can_masker|[c]amera_relay' || true" || true
    # The mission() process runs inside the container's own PID namespace — invisible to the
    # host-side pkill above. A fixed --name (hil_mission) lets teardown reach it directly.
    # Best-effort: no-op when docker is absent or nothing is running, and must never fail
    # teardown itself.
    # hil_smoke_test/hil_smoke_test_ci added alongside (smoke/smoke-ci, 2026-08-06) —
    # same reasoning: the container's own PID namespace hides it from the host-side
    # pkill above, and a job cancelled mid-run (docker run --rm doesn't clean up if
    # the ssh session dies abnormally) would otherwise leak an orphaned container.
    jssh "command -v docker >/dev/null 2>&1 && docker rm -f hil_mission hil_mission2 hil_smoke_test hil_smoke_test_ci >/dev/null 2>&1 || true" || true
  fi
  # Safety net (Task 11): remove any Mission 2 ball still in the workstation Gazebo before
  # we kill it, so an aborted react run (Task 12+) never leaves a ball in the world for the
  # next job. Only attempt while a Gazebo server is actually up — a `gz service` against a
  # dead server would block on its 5s timeout per name. Bracket-trick pgrep so the pattern
  # never self-matches. Rung 1 (nominal) spawns no ball, so this is normally a no-op.
  if pgrep -f '[g]z sim' >/dev/null 2>&1; then
    ( cd "$REPO_DIR" 2>/dev/null || exit 0
      for ball in ball_red ball_yellow; do
        python3 -m tools.mission2_harness remove "$ball" >/dev/null 2>&1 || true
      done ) || true
  fi
  local launch_pid
  launch_pid=$(pgrep -f '[s]im_only_launch' | head -1 || true)
  if [ -n "$launch_pid" ]; then
    kill -INT -- "-${launch_pid}" 2>/dev/null || true   # setsid => pid == pgid
    sleep 5
  fi
  # Unconditional -9 fallback (design doc §3): SIGINT teardown was unreliable in 2 of 3
  # Session-15 manual teardowns; leftovers poison the next run's DDS state.
  pkill -9 -f '[g]z sim' || true
  pkill -9 -f '[p]arameter_bridge' || true
  pkill -9 -f '[c]omponent_container' || true
  pkill -9 -f '[r]obot_state_publisher' || true
  pkill -9 -f '[s]im_only_launch' || true
  # static_transform_publisher added 2026-07-26 (Session 17 Piece 2 perf pass) — same gap as
  # the ekf_node one above, on the workstation side of the same pattern.
  pkill -9 -f '[s]tatic_transform_publisher' || true
  # ball_detector added 2026-07-26 (second-round code review) — same reasoning as the
  # Jetson-side pattern above, for a local single-machine (non-HIL) sim_launch.py run
  # where nav2_only_launch.py, and therefore ball_detector, runs on this same box.
  pkill -9 -f '[b]all_detector' || true
  echo '=== [teardown] done ==='
  return 0
}

restore_checkout() {
  require_ip
  # Fast-forward main, don't just check it out: the Jetson's local main only ever advances
  # here (CI syncs detached shas), and it silently sat on week-old code for days — any
  # manual/bare run that trusted it was running a different program than it claimed
  # (invalidated a bug-repro attempt on 2026-07-19). Best-effort: an offline Jetson still
  # lands on main, just possibly stale — the pull failing must never fail the CI job.
  jssh "cd ${JETSON_REPO} && git checkout main >/dev/null 2>&1 && git pull --ff-only origin main >/dev/null 2>&1 || true" || true
  echo '=== [restore-checkout] Jetson repo back on main (fast-forwarded when reachable) ==='
}

cmd="${1:?usage: hil_stage.sh discover|power-mode|sync <sha>|run|day|teardown|restore-checkout|smoke <sha>|smoke-ci <sha>}"
shift || true
case "$cmd" in
  discover)         discover ;;
  power-mode)       power_mode ;;
  sync)             sync "$@" ;;
  run)              run ;;
  day)              day ;;
  teardown)         teardown ;;
  restore-checkout) restore_checkout ;;
  smoke)            smoke "$@" ;;
  smoke-ci)         smoke_ci "$@" ;;
  *) echo "FATAL: unknown subcommand '$cmd'" >&2; exit 1 ;;
esac
