#!/usr/bin/env bash
# scripts/hil_stage.sh — stage-4-hil orchestration (design: docs/session15-hil-ci-stage-design.md).
# Runs identically from a local shell and from the CI job — debug locally first (Tier-1 rule).
#
# Subcommands:
#   discover          print the Jetson's current IP (mDNS first, ip-neigh fallback), verify SSH
#   power-mode        set nvpmodel mode $POWER_MODE_ID on the Jetson and print it
#   sync <sha>        fetch+checkout <sha> on the Jetson and colcon build --base-paths src
#   run               HIL STACK GATE (Task 13b): clean STATE_DIR, then sim-up (workstation
#                     Gazebo) -> nav2-up (Jetson). NO mission, NO retry — a mission failure
#                     must be RED (the in-process nav_runner cold-goal retry, Task 13a, is the
#                     only retry left; harness-level whole-mission retries were removed).
#   day               THE Mission 2 day (Task 13d): runs tools/mission2_day.py in HIL mode
#                     against the stack `run` brought up — no_ball -> yellow (swap to red
#                     during its return) -> red (stays). The mission executes on the Jetson;
#                     ball ops + ground-truth judging stay workstation-side. Judged verdicts +
#                     per-waypoint checklists print per run; photos land in reports/photos/ AND
#                     STATE_DIR (CI evidence). This is the ONE stage-4 test step.
#   reset-home        drive the robot to home_base (go_home mission) — RETAINED for manual
#                     use, but NOT a CI step: the day's no_ball/yellow missions self-return.
#   teardown          kill both sides (safe to run any time; used by CI's if:always() step)
#   restore-checkout  checkout main on the Jetson (run once at the very end)
set -euo pipefail

JETSON_USER="${JETSON_USER:-mike}"
POWER_MODE_ID="${POWER_MODE_ID:-1}"
STATE_DIR="${STATE_DIR:-/tmp/hil_stage}"
SIM_LOG="${STATE_DIR}/sim.log"
# Per-run log name (2026-07-18): a fixed name let a later nav2-up OVERWRITE the crash
# evidence of the run before it — a Nav2 SIGSEGV autopsy was lost exactly that way.
NAV2_LOG="/tmp/nav2_hil_$(date +%Y%m%d_%H%M%S).log"   # on the Jetson
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
  jssh "cd ${JETSON_REPO} && git fetch origin ${sha} && git checkout --detach FETCH_HEAD"
  jssh "source /opt/ros/jazzy/setup.bash && cd ${JETSON_REPO} && colcon build --symlink-install --base-paths src"
}

clean_state() {
  # STATE_DIR hygiene (Task 13g): the self-hosted runner's STATE_DIR persists across runs, so
  # a prior local-prove run's photos/logs/JSON otherwise contaminate this run's CI evidence
  # artifact and can even satisfy a judge's photo-presence check with stale data. Wipe first.
  mkdir -p "$STATE_DIR"
  rm -f "$STATE_DIR"/*.png "$STATE_DIR"/*.out "$STATE_DIR"/*.json \
        "$STATE_DIR"/nav2_hil_*.log "$STATE_DIR"/mission2_day.log 2>/dev/null || true
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

run() {
  # HIL stack GATE (Task 13b): clean state, bring up the workstation Gazebo half and the
  # Jetson Nav2. NO mission, NO verify, NO retry — the `day` orchestrator runs the missions,
  # and a mission failure must surface RED. The only retry left anywhere is nav_runner's
  # in-process cold-goal retry (Task 13a); all harness-level whole-mission retries were removed.
  clean_state
  sim_up && nav2_up
}

day() {
  # THE Mission 2 day (Task 13d) — tools/mission2_day.py in HIL mode against the stack `run`
  # brought up. The mission runs on the Jetson (bare-metal, or in the stage-3 arm64 image when
  # HIL_CONTAINER=1 — both inherited from the environment); ball ops + ground-truth judging +
  # telemetry all stay workstation-side. The orchestrator scps each run's photos to
  # reports/photos/ AND STATE_DIR (CI evidence) and prints per-run judged verdicts + waypoint
  # checklists. FLEET_DB (when set) receives the JUDGED rows directly here — no SSH row-
  # shipping, because the judge runs on the workstation where FLEET_DB lives.
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
    timeout 180 ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new "${JETSON_USER}@${JETSON_IP}" \
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
    jssh "pkill -9 -f '[n]av2|[c]omponent_container|[m]ission_runner|[e]kf_node|[b]all_detector' || true" || true
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

cmd="${1:?usage: hil_stage.sh discover|power-mode|sync <sha>|run|day|reset-home|teardown|restore-checkout}"
shift || true
case "$cmd" in
  discover)         discover ;;
  power-mode)       power_mode ;;
  sync)             sync "$@" ;;
  run)              run ;;
  day)              day ;;
  reset-home)       reset_home ;;
  teardown)         teardown ;;
  restore-checkout) restore_checkout ;;
  *) echo "FATAL: unknown subcommand '$cmd'" >&2; exit 1 ;;
esac
