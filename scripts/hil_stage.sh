#!/usr/bin/env bash
# scripts/hil_stage.sh — stage-4-hil orchestration (design: docs/session15-hil-ci-stage-design.md).
# Runs identically from a local shell and from the CI job — debug locally first (Tier-1 rule).
#
# Subcommands:
#   discover          print the Jetson's current IP (mDNS first, ip-neigh fallback), verify SSH
#   power-mode        set nvpmodel mode $POWER_MODE_ID on the Jetson and print it
#   sync <sha>        fetch+checkout <sha> on the Jetson and colcon build --base-paths src
#   run               full HIL test: sim-up -> nav2-up -> mission -> verify (+1 retry on
#                     a discovery-shaped failure, after full teardown + 5s DDS settle)
#   teardown          kill both sides (safe to run any time; used by CI's if:always() step)
#   restore-checkout  checkout main on the Jetson (run once at the very end, not mid-retry)
set -euo pipefail

JETSON_USER="${JETSON_USER:-mike}"
POWER_MODE_ID="${POWER_MODE_ID:-1}"
STATE_DIR="${STATE_DIR:-/tmp/hil_stage}"
SIM_LOG="${STATE_DIR}/sim.log"
NAV2_LOG=/tmp/nav2_hil.log   # on the Jetson
JETSON_REPO='~/autonomous-fleet-testbed'
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Every remote ROS command must source its own env — non-interactive SSH skips .bashrc.
JENV='source /opt/ros/jazzy/setup.bash && source ~/autonomous-fleet-testbed/install/setup.bash && export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp ROS_DOMAIN_ID=0'

case "$POWER_MODE_ID" in
  0) POWER_MODE_LABEL=15W ;;
  1) POWER_MODE_LABEL=25W ;;
  2) POWER_MODE_LABEL=MAXN_SUPER ;;
  *) echo "FATAL: unknown POWER_MODE_ID=$POWER_MODE_ID" >&2; exit 1 ;;
esac

jssh() { ssh -o ConnectTimeout=10 -o BatchMode=yes "${JETSON_USER}@${JETSON_IP}" "$@"; }

require_ip() {
  [ -n "${JETSON_IP:-}" ] || { echo "FATAL: JETSON_IP not set (run discover first)" >&2; exit 1; }
}

discover() {
  local ip
  ip=$(getent hosts jetson.local | awk '{print $1; exit}' || true)
  if [ -z "$ip" ]; then
    ip=$(ip neigh show dev enp6s0 | awk '$1 ~ /^10\.42\.0\./ && /lladdr/ {print $1; exit}' || true)
  fi
  [ -n "$ip" ] || { echo "FATAL: cannot discover Jetson IP (mDNS and ip-neigh both empty — is it powered on and cabled?)" >&2; exit 1; }
  ssh -o ConnectTimeout=10 -o BatchMode=yes "${JETSON_USER}@${ip}" true \
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
  jssh "cd ${JETSON_REPO} && git fetch origin ${sha} && git checkout --detach FETCH_HEAD"
  jssh "source /opt/ros/jazzy/setup.bash && cd ${JETSON_REPO} && colcon build --symlink-install --base-paths src"
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
  export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp ROS_DOMAIN_ID=0
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

nav2_up() {
  echo '=== [nav2-up] launching Nav2 on the Jetson (budget 120s) ==='
  require_ip
  # The (...) subshell + < /dev/null are BOTH required, or the local ssh call blocks
  # forever and nav2_up never reaches its polling loop:
  #  - bash's `&` binds to the ENTIRE preceding &&-list, so without the parens the
  #    backgrounded job is a subshell running the whole chain — that subshell inherits
  #    the SSH session's stdout/stderr pipes and holds the channel open indefinitely.
  #  - < /dev/null stops ros2 launch inheriting the session's stdin.
  # With the parens, only ros2 launch (all fds redirected) survives; the wrapper
  # subshell exits immediately and sshd can close the channel.
  jssh "$JENV && cd ${JETSON_REPO} && rm -f ${NAV2_LOG} && (nohup ros2 launch src/nav_fleet/launch/nav2_only_launch.py > ${NAV2_LOG} 2>&1 < /dev/null &) && sleep 1 && echo nav2-launched"
  local deadline=$((SECONDS + 120))
  # Two lifecycle managers report active (localization, then navigation) — gate on BOTH.
  local count
  count=$(jssh "grep -c 'Managed nodes are active' ${NAV2_LOG} 2>/dev/null || true")
  until [ "${count:-0}" -ge 2 ]; do
    if (( SECONDS >= deadline )); then
      echo 'FATAL: Nav2 not active within 120s — Jetson nav2 log tail:' >&2
      jssh "tail -n 40 ${NAV2_LOG}" >&2 || true
      return 1
    fi
    sleep 3
    count=$(jssh "grep -c 'Managed nodes are active' ${NAV2_LOG} 2>/dev/null || true")
  done
  echo '=== [nav2-up] managed nodes active ==='
}

mission() {
  echo '=== [mission] running mission1 on the Jetson (budget 300s) ==='
  require_ip
  local before_id
  before_id=$(jssh "python3 - <<'PY'
import os
import sqlite3
try:
    c = sqlite3.connect(os.path.expanduser('~/autonomous-fleet-testbed/reports/fleet_runs.db'))
    print(c.execute('SELECT COALESCE(MAX(id),0) FROM runs').fetchone()[0])
except sqlite3.OperationalError:
    print(0)
PY")
  echo "$before_id" > "$STATE_DIR/before_id"
  # HIL_CONTAINER=1 (stage-4-hil phase 2): run the mission executor INSIDE the stage-3
  # arm64 GHCR image on the Jetson instead of the Jetson's bare-metal workspace — this is
  # what finally makes the arm64→HIL pipeline edge consume the image it built. The reports
  # dir is bind-mounted so the photo + telemetry row still land on the host exactly as the
  # bare-metal path leaves them (verify()/before_id read the host DB either way). DDS is
  # host-networked (--network host --ipc host) so the container sees Gazebo over enp6s0.
  local mission_cmd
  if [ "${HIL_CONTAINER:-0}" = "1" ]; then
    echo "=== [mission] in-container execution: ${HIL_IMAGE:?HIL_CONTAINER=1 requires HIL_IMAGE} ==="
    mission_cmd="docker run --rm --network host --ipc host \
      -v \$HOME/autonomous-fleet-testbed/reports:/ros2_ws/reports \
      -e RUNNER_TYPE=hil_jetson -e POWER_MODE=${POWER_MODE_LABEL} \
      -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp -e ROS_DOMAIN_ID=0 \
      ${HIL_IMAGE} \
      bash -c 'source /opt/ros/jazzy/setup.bash && source /ros2_ws/install/setup.bash && python3 -m nav_fleet.mission_runner mission1'"
  else
    mission_cmd="$JENV && cd ${JETSON_REPO} && RUNNER_TYPE=hil_jetson POWER_MODE=${POWER_MODE_LABEL} python3 -m nav_fleet.mission_runner mission1"
  fi
  local rc=0
  timeout 300 ssh -o BatchMode=yes "${JETSON_USER}@${JETSON_IP}" "$mission_cmd" \
    2>&1 | tee "$STATE_DIR/mission.out" || rc=$?
  return "$rc"
}

verify() {
  echo '=== [verify] photo + telemetry row ==='
  require_ip
  local photo before_id row
  photo=$(grep -oP 'photo saved: \K\S+' "$STATE_DIR/mission.out" | tail -1 || true)
  [ -n "$photo" ] || { echo 'FATAL: no photo path in mission output' >&2; return 1; }
  scp -o BatchMode=yes "${JETSON_USER}@${JETSON_IP}:autonomous-fleet-testbed/${photo}" "$STATE_DIR/" \
    || { echo "FATAL: photo ${photo} missing on the Jetson" >&2; return 1; }
  before_id=$(cat "$STATE_DIR/before_id")
  row=$(jssh "python3 - <<PY
import os
import sqlite3
c = sqlite3.connect(os.path.expanduser('~/autonomous-fleet-testbed/reports/fleet_runs.db'))
r = c.execute(\"SELECT id, scenario, result, runner_type, sim_engine, power_mode, \"
              \"mean_time_to_goal, mean_position_error FROM runs \"
              \"WHERE id > ${before_id} AND runner_type='hil_jetson' \"
              \"ORDER BY id DESC LIMIT 1\").fetchone()
print(r if r else 'MISSING')
PY")
  echo "HIL telemetry row: ${row}"
  [ "$row" != "MISSING" ] || { echo 'FATAL: no new hil_jetson telemetry row' >&2; return 1; }
  echo "$row" | grep -q "'PASS'" || { echo 'FATAL: telemetry row is not PASS' >&2; return 1; }
  echo '=== [verify] OK ==='
}

run_once() {
  sim_up && nav2_up && mission && verify
}

run() {
  mkdir -p "$STATE_DIR"
  rm -f "$STATE_DIR/mission.out"
  if run_once; then return 0; fi
  # Retry-once policy (design doc §3): only for a discovery-shaped failure.
  if grep -qE 'Nav2 action server unavailable|Goal rejected after all retries|no camera frame' \
       "$STATE_DIR/mission.out" 2>/dev/null; then
    local reason_line
    reason_line=$(grep -oE 'Nav2 action server unavailable|Goal rejected after all retries|no camera frame' \
        "$STATE_DIR/mission.out" 2>/dev/null | head -1 || true)
    echo "HIL RETRY: first attempt failed (${reason_line}) — retrying once"
    echo '=== discovery-shaped failure: full both-sides teardown, 5s settle, ONE retry ==='
    if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
      {
        echo '### HIL retry occurred'
        echo "First attempt failed (${reason_line}) — retried once after full teardown + 5s DDS settle."
      } >> "$GITHUB_STEP_SUMMARY"
    fi
    teardown
    sleep 5
    run_once
  else
    echo '=== non-discovery failure: no retry (a second run would mask a real regression) ==='
    return 1
  fi
}

teardown() {
  echo '=== [teardown] both sides ==='
  if [ -n "${JETSON_IP:-}" ]; then
    jssh "pkill -9 -f '[n]av2|[c]omponent_container|[m]ission_runner' || true" || true
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
  echo '=== [teardown] done ==='
  return 0
}

restore_checkout() {
  require_ip
  jssh "cd ${JETSON_REPO} && git checkout main >/dev/null 2>&1 || true" || true
  echo '=== [restore-checkout] Jetson repo back on main ==='
}

cmd="${1:?usage: hil_stage.sh discover|power-mode|sync <sha>|run|teardown|restore-checkout}"
shift || true
case "$cmd" in
  discover)         discover ;;
  power-mode)       power_mode ;;
  sync)             sync "$@" ;;
  run)              run ;;
  teardown)         teardown ;;
  restore-checkout) restore_checkout ;;
  *) echo "FATAL: unknown subcommand '$cmd'" >&2; exit 1 ;;
esac
