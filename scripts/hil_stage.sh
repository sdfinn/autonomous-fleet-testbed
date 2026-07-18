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
#   mission2-nominal  HIL graduation rung 1 (spec §8, Task 13 Option B): reuse the sim+Nav2
#                     left up by `run`, run mission2 (NO ball) on the Jetson — the VERIFIED
#                     ROUND TRIP (home_ref photo -> marker -> marker photo -> home ->
#                     home_arrival photo). Judge workstation-side: zero reactions + marker
#                     photo + ended HOME + home-photo pair. The mission SELF-RETURNS, so no
#                     reset-home step follows it. Run AFTER `run`, BEFORE the react rungs.
#   reset-home        drive the robot to home_base (go_home mission) — RETAINED for manual
#                     use, but NO LONGER a CI step: under Option B nominal/yellow self-return.
#   mission2-yellow   HIL rung 2 (spec §8): deterministic yellow ball beside the marker;
#                     reaction photo_then_home (robot returns home by itself + home_arrival
#                     photo for the pair check). No reset after.
#   mission2-red      HIL rung 3 (spec §8): deterministic red ball; reaction photo_then_stop
#                     (robot STAYS mid-room, takes NO home photo). Run LAST — only teardown
#                     follows.
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
# Ghost-ball settle (CLAUDE.md Gotchas, 2026-07-17): the headless llvmpipe renderer keeps a
# REMOVED model in camera frames for seconds — wait this long after remove_ball so the next
# rung never reacts to the previous rung's ball. Mirrors tests/test_mission2.py's constant.
BALL_REMOVAL_SETTLE_S="${BALL_REMOVAL_SETTLE_S:-3}"

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
    mission_cmd="docker run --rm --name hil_mission --network host --ipc host \
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

  # Ship the row (design §2): SELECT the just-logged hil_jetson row over SSH → INSERT it
  # into the workstation drift DB. We ship the ROW, never the DB file — the Jetson and the
  # workstation keep independent histories and schema authority stays on the workstation.
  # Only runs when FLEET_DB is set (CI + the local scratch-DB test); a bare local run skips
  # shipping. Placed after the OK gate above, so a PASS hil_jetson row is known to exist —
  # the remote SELECT can never hit a None row (keeps set -e safe).
  if [ -n "${FLEET_DB:-}" ]; then
    echo '=== [verify] shipping HIL row to workstation drift DB ==='
    # before_id was read from the state file above; quoting mirrors the SELECT just above
    # (escaped double-quotes wrap the SQL, plain single-quotes inside — proven pattern).
    jssh "python3 - <<PY
import json, os, sqlite3
c = sqlite3.connect(os.path.expanduser('~/autonomous-fleet-testbed/reports/fleet_runs.db'))
c.row_factory = sqlite3.Row
r = c.execute(\"SELECT * FROM runs WHERE id > ${before_id} AND runner_type='hil_jetson' \"
              \"ORDER BY id DESC LIMIT 1\").fetchone()
print(json.dumps({k: r[k] for k in r.keys() if k != 'id'}))
PY" > "$STATE_DIR/hil_row.json"
    # Local INSERT into FLEET_DB. Subshell cd's to the repo so `tools.telemetry_logger`
    # imports; init_db creates/migrates the schema; we keep only columns present locally so
    # power_mode (and every other shipped field) survives intact into the workstation DB.
    ( cd "$REPO_DIR"
      STATE_DIR="$STATE_DIR" FLEET_DB="$FLEET_DB" python3 - <<'PY'
import json, os, sqlite3, sys
row = json.load(open(os.path.join(os.environ['STATE_DIR'], 'hil_row.json')))
sys.path.insert(0, '.')
from tools.telemetry_logger import init_db
db = os.environ['FLEET_DB']
init_db(db)
conn = sqlite3.connect(db)
cols = {r[1] for r in conn.execute('PRAGMA table_info(runs)')}
row = {k: v for k, v in row.items() if k in cols}
conn.execute("INSERT INTO runs ({}) VALUES ({})".format(
    ','.join(row), ','.join('?' * len(row))), list(row.values()))
conn.commit()
print('shipped HIL row into %s — runner_type=%r power_mode=%r'
      % (db, row.get('runner_type'), row.get('power_mode')))
PY
    )
    echo '=== [verify] shipped ==='
  fi
}

scp_tagged_photo() {
  # Pull the newest photo whose 'photo saved:' path contains $2 from mission output $1 to
  # STATE_DIR — FIRST removing any stale copies of that tag (Task 12 review item 2: a
  # leftover photo from a prior CI run otherwise satisfies the judge's presence check, and
  # a stale home_arrival would even FALSE-FAIL the red rung). Best-effort scp: a missing
  # photo is left for the judge to flag, not a hard error here.
  local out="$1" tag="$2"
  rm -f "$STATE_DIR"/*"${tag}"*.png
  local photo
  photo=$(grep -oP 'photo saved: \K\S+' "$out" 2>/dev/null | grep -- "$tag" | tail -1 || true)
  if [ -n "$photo" ]; then
    scp -o BatchMode=yes "${JETSON_USER}@${JETSON_IP}:autonomous-fleet-testbed/${photo}" \
        "$STATE_DIR/" || echo "WARN: photo ${photo} (${tag}) not on the Jetson" >&2
  else
    echo "WARN: no '${tag}' photo path in mission output (judge flags it if required)" >&2
  fi
}

retry_reason() {
  # Print a one-line reason IFF the just-failed `run` is a known TRANSIENT flake worth ONE
  # retry, else print nothing (caller then fails hard — a second run would mask a real
  # regression). Checked BEFORE teardown so the Jetson's Nav2 log is still intact.
  local m
  m=$(grep -oE 'Nav2 action server unavailable|Goal rejected after all retries|no camera frame' \
      "$STATE_DIR/mission.out" 2>/dev/null | head -1 || true)
  if [ -n "$m" ]; then echo "$m"; return 0; fi
  # follow_path ACK-TIMEOUT (Task 12 review item 1): the cold-goal flake that bit mission1's
  # own return leg once. bt_navigator times out waiting for a cold controller_server to
  # acknowledge the FollowPath goal — "Timed out while waiting for action server to
  # acknowledge goal request for follow_path" -> "Aborting handle" -> the leg returns False.
  # That text lands in the JETSON's Nav2 log (${NAV2_LOG}), NOT in mission.out (which only
  # carries mission_runner's own stdout), so the old mission.out-only filter never caught it.
  # Bounded to one retry; run_once re-runs verify(), so a retried run stays fully judged.
  if [ -n "${JETSON_IP:-}" ]; then
    local f
    f=$(jssh "grep -c 'acknowledge goal request for follow_path' ${NAV2_LOG} 2>/dev/null || true")
    if [ "${f:-0}" -ge 1 ] 2>/dev/null; then
      echo 'follow_path ack-timeout (Nav2 cold-goal flake, Jetson nav2 log)'; return 0
    fi
  fi
  return 0
}

run_once() {
  sim_up && nav2_up && mission && verify
}

run() {
  mkdir -p "$STATE_DIR"
  rm -f "$STATE_DIR/mission.out"
  if run_once; then return 0; fi
  # Retry-once policy (design doc §3): only for a known TRANSIENT flake — discovery-shaped
  # (mission.out) OR the follow_path ack-timeout cold-goal flake (Jetson nav2 log). See
  # retry_reason(). A retried run still goes through verify() (fully judged).
  local reason_line
  reason_line=$(retry_reason)
  if [ -n "$reason_line" ]; then
    echo "HIL RETRY: first attempt failed (${reason_line}) — retrying once"
    echo '=== transient failure: full both-sides teardown, 5s settle, ONE retry ==='
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
    echo '=== non-transient failure: no retry (a second run would mask a real regression) ==='
    return 1
  fi
}

run_mission2_nominal() {
  echo '=== [mission2-nominal] no-ball nominal variant on the Jetson (budget 300s) ==='
  require_ip
  mkdir -p "$STATE_DIR"
  # Workstation env for the ground-truth judge (mirrors sim_up): cd to the repo so
  # `python3 -m tools.mission2_harness` resolves, source ROS so `gz` is on PATH. The sim +
  # Nav2 that `run` (mission1) left up are reused — this variant launches neither.
  cd "$REPO_DIR"
  set +u
  source /opt/ros/jazzy/setup.bash
  source install/setup.bash
  set -u
  export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp ROS_DOMAIN_ID=0
  # Rung 1 spawns NO ball (Mike, 2026-07-17). The Jetson runs plain mission2 — the Option B
  # verified round trip (home_ref -> marker -> marker photo -> home -> home_arrival); the
  # workstation judges zero reactions + marker photo + ended home + home-photo pair. Same
  # docker-vs-bare shape as mission(), different mission + container name + log file.
  local mission_cmd
  if [ "${HIL_CONTAINER:-0}" = "1" ]; then
    echo "=== [mission2-nominal] in-container: ${HIL_IMAGE:?HIL_CONTAINER=1 requires HIL_IMAGE} ==="
    mission_cmd="docker run --rm --name hil_mission2 --network host --ipc host \
      -v \$HOME/autonomous-fleet-testbed/reports:/ros2_ws/reports \
      -e RUNNER_TYPE=hil_jetson -e POWER_MODE=${POWER_MODE_LABEL} \
      -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp -e ROS_DOMAIN_ID=0 \
      ${HIL_IMAGE} \
      bash -c 'source /opt/ros/jazzy/setup.bash && source /ros2_ws/install/setup.bash && python3 -m nav_fleet.mission_runner mission2'"
  else
    mission_cmd="$JENV && cd ${JETSON_REPO} && RUNNER_TYPE=hil_jetson POWER_MODE=${POWER_MODE_LABEL} python3 -m nav_fleet.mission_runner mission2"
  fi
  local mrc=0
  timeout 300 ssh -o BatchMode=yes "${JETSON_USER}@${JETSON_IP}" "$mission_cmd" \
    2>&1 | tee "$STATE_DIR/mission2.out" || mrc=$?
  # Option B (Task 13): the nominal round trip takes home_ref + marker + home_arrival photos
  # on the Jetson. The Jetson has no Gazebo, so the ground-truth home check AND the
  # return-fidelity pair check both run HERE — pull the three photos (stale copies removed
  # first) and hand their globs to the judge.
  scp_tagged_photo "$STATE_DIR/mission2.out" mission2_marker
  scp_tagged_photo "$STATE_DIR/mission2.out" mission2_home_ref
  scp_tagged_photo "$STATE_DIR/mission2.out" mission2_home_arrival
  # Workstation-side judge (Gazebo runs here, so ground truth is available here). Zero
  # reactions + marker photo + ended home + home-photo pair. Capture rc — never let a judge
  # nonzero abort under `set -e`.
  local jrc=0
  RUNNER_TYPE=hil_jetson POWER_MODE="${POWER_MODE_LABEL}" \
  python3 -m tools.mission2_harness judge-nominal \
    --mission-log "$STATE_DIR/mission2.out" \
    --marker-glob "$STATE_DIR/mission2_marker_*.png" \
    --home-ref-glob "$STATE_DIR/mission2_home_ref_*.png" \
    --home-arrival-glob "$STATE_DIR/mission2_home_arrival_*.png" || jrc=$?
  if [ "$mrc" -ne 0 ]; then
    echo "FATAL: mission2 self-reported failure on the Jetson (rc=${mrc})" >&2
    return "$mrc"
  fi
  return "$jrc"
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

reset_home() {
  echo '=== [reset-home] drive the robot back to home_base (mirrors the sim janitor) ==='
  require_ip
  ws_source
  # RETAINED for manual use (Task 13): under Option B the nominal/yellow missions self-return
  # home, so CI no longer runs this between rungs. When invoked manually it drives the robot
  # to home_base via the go_home mission (a single navigate leg; mission_runner clears both
  # costmaps first). Teleporting is forbidden: it breaks AMCL + the costmaps.
  # Bare-metal on the Jetson (a plain nav needs no container image). 180s: one nav leg.
  # Retry up to 3x: go_home is a COLD first goal (fresh mission_runner process, idle Nav2),
  # the case most exposed to a transient flake where bt_navigator's FollowPath call times
  # out waiting for the cold controller_server to acknowledge — the plan succeeds but the
  # handoff misses its ack window (observed live 2026-07-18: ~2 of 3 cold home-goal attempts
  # flaked; a warm goal in an already-running process, e.g. yellow's retreat, does not). Each
  # failed attempt aborts in ~0.2 s, so the retries are cheap. This is an UNJUDGED reset leg,
  # so retrying is safe — it never masks a react-rung regression (those stay single-shot).
  local rc=0 attempt
  for attempt in 1 2 3; do
    rc=0
    timeout 180 ssh -o BatchMode=yes "${JETSON_USER}@${JETSON_IP}" \
      "$JENV && cd ${JETSON_REPO} && RUNNER_TYPE=hil_jetson POWER_MODE=${POWER_MODE_LABEL} python3 -m nav_fleet.mission_runner go_home" \
      2>&1 | tee "$STATE_DIR/reset_home.out" || rc=$?
    [ "$rc" -eq 0 ] && break
    echo "WARN: drive-home reset attempt ${attempt} failed (rc=${rc}) — retry after 5s settle" >&2
    sleep 5
  done
  if [ "$rc" -ne 0 ]; then
    echo "FATAL: drive-home reset failed after retries (rc=${rc})" >&2
    return "$rc"
  fi
  # Confirm the robot actually reached home before the next rung runs off a bad pose.
  python3 -m tools.mission2_harness assert-home
}

run_mission2_react() {
  # HIL react rung (spec §8): deterministic ball beside the green sphere, mission2 on the
  # Jetson, judged workstation-side. Shared by the yellow and red rungs — only the color,
  # the judge verb, and the reaction reaction differ. Mirrors tests/test_mission2.py's
  # red/yellow variants: assert home -> spawn at BALL_AT_SPHERE_XY -> run -> judge -> remove
  # + settle. Reuses the sim + Nav2 that `run` (mission1) left up (launches neither).
  local color="${1:?run_mission2_react needs a color}"
  echo "=== [mission2-${color}] deterministic ${color}-ball react rung on the Jetson (budget 300s) ==="
  require_ip
  ws_source
  # Precondition (mirrors _assert_at_home_base): a failed drive-home must abort here, not
  # silently displace the rung's placement/travel geometry.
  python3 -m tools.mission2_harness assert-home
  # Deterministic spawn beside the green sphere (mirrors spawn_ball(color, *BALL_AT_SPHERE_XY)).
  local spawn ballx bally ballname
  spawn=$(python3 -m tools.mission2_harness spawn-at --color "$color")
  ballx=$(printf '%s' "$spawn" | python3 -c 'import json,sys; print(json.load(sys.stdin)["x"])')
  bally=$(printf '%s' "$spawn" | python3 -c 'import json,sys; print(json.load(sys.stdin)["y"])')
  ballname=$(printf '%s' "$spawn" | python3 -c 'import json,sys; print(json.load(sys.stdin)["name"])')
  echo "=== [mission2-${color}] spawned ${ballname} at (${ballx}, ${bally}) ==="
  # Workstation ground-truth poller: captures the reaction point (closest approach to the
  # ball) DURING the mission. Required for yellow, which drives home after reacting — its
  # reaction point can't be recovered from any post-mission sample. Backgrounded; killed
  # (SIGTERM) once the mission ssh returns, at which point it writes its JSON.
  local watch="$STATE_DIR/mission2_${color}_watch.json"
  rm -f "$watch"
  python3 -m tools.mission2_harness watch --ball-x "$ballx" --ball-y "$bally" \
      --out "$watch" --max-s 300 &
  local watch_pid=$!
  # Run mission2 on the Jetson — same container-vs-bare-metal shape as mission()/nominal.
  local mission_cmd
  if [ "${HIL_CONTAINER:-0}" = "1" ]; then
    echo "=== [mission2-${color}] in-container: ${HIL_IMAGE:?HIL_CONTAINER=1 requires HIL_IMAGE} ==="
    mission_cmd="docker run --rm --name hil_mission2 --network host --ipc host \
      -v \$HOME/autonomous-fleet-testbed/reports:/ros2_ws/reports \
      -e RUNNER_TYPE=hil_jetson -e POWER_MODE=${POWER_MODE_LABEL} \
      -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp -e ROS_DOMAIN_ID=0 \
      ${HIL_IMAGE} \
      bash -c 'source /opt/ros/jazzy/setup.bash && source /ros2_ws/install/setup.bash && python3 -m nav_fleet.mission_runner mission2'"
  else
    mission_cmd="$JENV && cd ${JETSON_REPO} && RUNNER_TYPE=hil_jetson POWER_MODE=${POWER_MODE_LABEL} python3 -m nav_fleet.mission_runner mission2"
  fi
  local mrc=0
  timeout 300 ssh -o BatchMode=yes "${JETSON_USER}@${JETSON_IP}" "$mission_cmd" \
      2>&1 | tee "$STATE_DIR/mission2_${color}.out" || mrc=$?
  # Stop the poller (it writes its JSON in a SIGTERM handler).
  kill -TERM "$watch_pid" 2>/dev/null || true
  wait "$watch_pid" 2>/dev/null || true
  # Pull the reaction photo to the workstation (stale copy removed first — Task 12 review
  # item 2). The bind-mounted reports dir puts it on the Jetson host; the judge globs it.
  scp_tagged_photo "$STATE_DIR/mission2_${color}.out" "reaction_${color}"
  # Return-fidelity photos (Task 13 §3). Yellow self-returns and takes home_ref + home_arrival
  # -> pull both for the pair check. Red STAYS and takes NO home_arrival -> just clear any
  # stale one so the judge's no-home-photo check can't be tripped by the yellow rung's
  # leftover (this is exactly the stale-photo false-pass/false-fail hazard from item 2).
  rm -f "$STATE_DIR"/*mission2_home_arrival*.png "$STATE_DIR"/*mission2_home_ref*.png
  local home_globs=()
  if [ "$color" = "yellow" ]; then
    scp_tagged_photo "$STATE_DIR/mission2_${color}.out" mission2_home_ref
    scp_tagged_photo "$STATE_DIR/mission2_${color}.out" mission2_home_arrival
    home_globs=(--home-ref-glob "$STATE_DIR/mission2_home_ref_*.png"
                --home-arrival-glob "$STATE_DIR/mission2_home_arrival_*.png")
  else
    # Red: assert NO home-arrival exists (the glob will match nothing after the rm above).
    home_globs=(--home-arrival-glob "$STATE_DIR/mission2_home_arrival_*.png")
    # Stationary check depends on the robot having decelerated by the time judge-red takes
    # its two ground-truth samples. The kill/scp above already spent a second; add a short
    # explicit settle so red's stop is unambiguous rather than relying on that latency.
    sleep 2
  fi
  # Workstation-side judge (ground truth is here). Tag the judged verdict row as a HIL run.
  local jrc=0
  RUNNER_TYPE=hil_jetson POWER_MODE="${POWER_MODE_LABEL}" \
  python3 -m tools.mission2_harness "judge-${color}" \
      --ball-x "$ballx" --ball-y "$bally" \
      --mission-log "$STATE_DIR/mission2_${color}.out" \
      --watch-file "$watch" \
      --photo-glob "$STATE_DIR/mission2_reaction_${color}_*.png" \
      "${home_globs[@]}" || jrc=$?
  # Ball swap hygiene: remove the ball and settle >=3 s (ghost-ball gotcha) so the next rung
  # can't react to this one's ball. Done after judging (the judge needs the world unchanged).
  python3 -m tools.mission2_harness remove "$ballname" >/dev/null 2>&1 || true
  sleep "$BALL_REMOVAL_SETTLE_S"
  if [ "$mrc" -ne 0 ]; then
    echo "FATAL: mission2 (${color}) self-reported failure on the Jetson (rc=${mrc})" >&2
    return "$mrc"
  fi
  return "$jrc"
}

teardown() {
  echo '=== [teardown] both sides ==='
  if [ -n "${JETSON_IP:-}" ]; then
    jssh "pkill -9 -f '[n]av2|[c]omponent_container|[m]ission_runner' || true" || true
    # HIL_CONTAINER=1's mission() process runs inside the container's own PID namespace —
    # invisible to the host-side pkill above. A fixed --name (hil_mission) lets teardown
    # reach it directly. Best-effort: no-op when docker is absent or nothing is running,
    # and must never fail teardown itself.
    jssh "command -v docker >/dev/null 2>&1 && docker rm -f hil_mission hil_mission2 >/dev/null 2>&1 || true" || true
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
  echo '=== [teardown] done ==='
  return 0
}

restore_checkout() {
  require_ip
  jssh "cd ${JETSON_REPO} && git checkout main >/dev/null 2>&1 || true" || true
  echo '=== [restore-checkout] Jetson repo back on main ==='
}

cmd="${1:?usage: hil_stage.sh discover|power-mode|sync <sha>|run|mission2-nominal|reset-home|mission2-yellow|mission2-red|teardown|restore-checkout}"
shift || true
case "$cmd" in
  discover)         discover ;;
  power-mode)       power_mode ;;
  sync)             sync "$@" ;;
  run)              run ;;
  mission2-nominal) run_mission2_nominal ;;
  reset-home)       reset_home ;;
  mission2-yellow)  run_mission2_react yellow ;;
  mission2-red)     run_mission2_react red ;;
  teardown)         teardown ;;
  restore-checkout) restore_checkout ;;
  *) echo "FATAL: unknown subcommand '$cmd'" >&2; exit 1 ;;
esac
