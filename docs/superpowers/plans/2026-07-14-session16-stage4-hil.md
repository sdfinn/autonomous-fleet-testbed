# Session 16 Plan A — `stage-4-hil` CI Stage (+ protective fixes) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `stage-4-isaac` with `stage-4-hil` — a CI job that runs Mission 1 hardware-in-the-loop (Gazebo on the x86 runner, Nav2 + mission executor on the real Jetson over SSH) on every code push — proven 3× consecutively green, with the telemetry/robustness fixes that stage depends on landed first.

**Architecture:** One GitHub Actions job on the x86 GPU runner drives the Jetson over SSH as a lab instrument (design: `docs/session15-hil-ci-stage-design.md`, all §1–§4 decisions are final). All orchestration lives in a repo shell script (`scripts/hil_stage.sh`) with subcommands, so the entire stage is runnable and debuggable **locally** (Tier-1 principle) before any CI push. Phase 1 runs the mission natively on the Jetson; phase 2 (containerized mission + telemetry-row shipping) is gated on the 3×-green milestone.

**Tech Stack:** GitHub Actions (self-hosted x86 + Jetson runners), bash, SSH, ROS2 Jazzy, Gazebo Harmonic, CycloneDDS, SQLite, pytest.

## Global Constraints

- **Mission 2 is OUT of scope for this plan** — separate Plan B, only after Task 10's 3×-green gate (Release1Todo Session 16 ordering rule).
- Python style: flake8, `--max-line-length=99` (stage-1 lints `src/nav_fleet/` only; `tools/` and `tests/` follow the same style by convention).
- On the Jetson, always `python3` (never `python`), no `sqlite3` CLI (use `python3 -c "import sqlite3; ..."`), and `colcon build --base-paths src` (nested `actions-runner/` checkout trap).
- Every SSH command that touches ROS must prefix: `source /opt/ros/jazzy/setup.bash && source ~/autonomous-fleet-testbed/install/setup.bash && export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp ROS_DOMAIN_ID=0` (non-interactive shells skip `.bashrc` on BOTH machines).
- Every `pkill`/`pgrep -f` pattern must bracket-protect **every** alternative (`'[n]av2|[c]omponent_container'`), or the pattern kills its own shell — bit us 2026-07-14.
- Jetson identity: `mike@jetson.local` (mDNS) / lease IP discovered at job start, never hard-coded. SSH user decision (design doc §5 open item, resolved here): plain job-level env `JETSON_USER: mike` in `ci.yml` — single-user testbed, no secrets indirection needed.
- Power modes (Orin Nano Super): 0=15W, 1=25W, 2=MAXN_SUPER. **Policy (Mike, 2026-07-14): build fast, test at deployment power — Jetson-side builds at 25W, the HIL mission itself at 15W** (simulates the real rover's power budget), restored to 25W in an `if: always()` step. Every mode change explicit per job, recorded in telemetry (`power_mode` column). Evidence 15W fits the §3 budgets: the first HIL run (2026-07-11) predated the 25W pin — the board was in out-of-box mode 0 (15W) and passed with Nav2 active ~5 s, mission ~18 s.
- Commit style: `type(scope): message`, commit after each task. Work happens on branch `session-16-stage4-hil`; the PR itself is the CI test vehicle (a PR to main triggers the full pipeline including the new stage).
- Timeout budgets are fixed by design doc §3: job 15 min; sim-up ≤60 s; Nav2-active ≤120 s; mission ≤300 s; retry **once** on a discovery-shaped failure after full both-sides teardown + ~5 s settle.

## File Structure

- `tools/telemetry_logger.py` — add `power_mode` column + `log_run` kwarg (schema migration already handled by `_ensure_run_columns`)
- `tests/test_telemetry_logger.py` — NEW: unit tests for the `power_mode` field
- `src/nav_fleet/nav_fleet/mission_runner.py` — FAIL-leg metric policy, constructor-inside-try, `power_mode` passthrough
- `tests/test_baseline.py` — regression test: FAIL rows excluded from drift baselines
- `tests/test_mission_run.py` — `_log_mission(runner=None)` unit test
- `scripts/hil_stage.sh` — NEW: all HIL orchestration (discover / power-mode / sync / run / teardown)
- `.github/workflows/ci.yml` — `stage-4-hil` replaces `stage-4-isaac`; `stage-5-reports-hw` rewire; stage-3 registry build cache; stage-2 runs `test_mission_run.py`
- `Dockerfile` — (phase 2 only) `COPY tools/` so the image can run the mission executor

---

### Task 1: `power_mode` telemetry field, end to end

**Files:**
- Modify: `tools/telemetry_logger.py` (`_ensure_run_columns` dict, `log_run` signature + `optional_fields`)
- Modify: `src/nav_fleet/nav_fleet/mission_runner.py:99-114` (`_log_mission`)
- Test: `tests/test_telemetry_logger.py` (new)

**Interfaces:**
- Produces: `log_run(..., power_mode: str = None)`; `runs.power_mode TEXT` column; mission rows carry `power_mode` from the `POWER_MODE` env var (e.g. `"25W"`), NULL when unset.

**WHY:** drift detection must never silently compare 15W mission timings against 25W ones (Release1Todo Session 16, power-policy item b). The CI job exports `POWER_MODE` (Task 6); the mission runner records it.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_telemetry_logger.py
"""Unit tests for tools/telemetry_logger.py schema + log_run fields."""
import sqlite3

from tools.telemetry_logger import init_db, log_run


def test_power_mode_column_exists(tmp_path):
    db = str(tmp_path / "t.db")
    init_db(db)
    cols = {r[1] for r in sqlite3.connect(db).execute("PRAGMA table_info(runs)")}
    assert "power_mode" in cols


def test_log_run_records_power_mode(tmp_path):
    db = str(tmp_path / "t.db")
    log_run(scenario="s", steps=1, final_x=0.0, final_y=0.0, result="PASS",
            step_log=[], db_path=db, power_mode="25W")
    row = sqlite3.connect(db).execute(
        "SELECT power_mode FROM runs ORDER BY id DESC LIMIT 1").fetchone()
    assert row[0] == "25W"


def test_log_run_power_mode_defaults_null(tmp_path):
    db = str(tmp_path / "t.db")
    log_run(scenario="s", steps=1, final_x=0.0, final_y=0.0, result="PASS",
            step_log=[], db_path=db)
    row = sqlite3.connect(db).execute(
        "SELECT power_mode FROM runs ORDER BY id DESC LIMIT 1").fetchone()
    assert row[0] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_telemetry_logger.py -v`
Expected: 3 FAIL — `power_mode` not in columns / unexpected keyword argument.

- [ ] **Step 3: Implement**

In `tools/telemetry_logger.py`, add to the `_ensure_run_columns` `expected_columns` dict:

```python
        "power_mode": "TEXT",
```

In `log_run`, add `power_mode: str = None` to the signature (after `camera_hz_mean`) and to `optional_fields`:

```python
        "power_mode": power_mode,
```

In `src/nav_fleet/nav_fleet/mission_runner.py` `_log_mission`, add after `mean_time_to_goal=...`:

```python
        power_mode=os.environ.get('POWER_MODE'),
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_telemetry_logger.py tests/test_baseline.py -v`
Expected: all PASS (test_baseline confirms no regression from the schema addition).

- [ ] **Step 5: Commit**

```bash
git add tools/telemetry_logger.py src/nav_fleet/nav_fleet/mission_runner.py tests/test_telemetry_logger.py
git commit -m "feat(telemetry): record power_mode per run — HIL rows must not be compared across power modes"
```

---

### Task 2: FAIL-leg metric policy — failed navigate durations stay out of `mean_time_to_goal`

**Files:**
- Modify: `src/nav_fleet/nav_fleet/mission_runner.py:82-86` (`run_mission` navigate branch)
- Test: `tests/test_baseline.py` (add regression test)

**Interfaces:**
- Consumes: `NavRunner._finish()` sets `last_duration_s`/`last_position_error` **even on failure** (a timed-out leg reports ~90 s — the timeout value, not robot performance).
- Produces: the decided policy — **(a)** a failed leg's duration/error never feeds the row's `mean_time_to_goal`/`mean_position_error` (they measure the timeout, not the robot); **(b)** FAIL rows are excluded from drift baselines (already true in `baseline_monitor.check_run` via `WHERE result = 'PASS'` — locked in by regression test).

**WHY:** `stage-4-hil` will generate rows on every push and will eventually produce FAILs; the policy must exist first (Release1Todo Session 16 Piece 3, item 1).

- [ ] **Step 1: Write the failing/locking tests**

Append to `tests/test_baseline.py`:

```python
def test_fail_rows_excluded_from_baseline(db):
    """Policy (Session 16): FAIL rows never enter the drift baseline window."""
    _seed_baseline(db)
    # A wild FAIL row that would wreck the baseline mean if included:
    _insert(db, nav_success_rate=0.0, result="FAIL", mean_position_error=99.0)
    run_id = _insert(db, nav_success_rate=0.95)  # normal PASS run under check
    reports = check_run(run_id, db_path=db)
    by_metric = {r.metric: r for r in reports}
    assert not by_metric["nav_success_rate"].flagged
    assert not by_metric["mean_position_error"].flagged
```

For the mission-runner half, append to `tests/test_mission_run.py` (runs in stage-2 where rclpy exists):

```python
class _StubNav:
    """Mimics NavRunner's metric attributes after a timed-out (failed) goal."""
    last_duration_s = 90.0        # the timeout value, not robot performance
    last_position_error = 3.2
    last_final_x = 0.0
    last_final_y = 0.0

    def send_goal(self, x, y, timeout=90.0, yaw=None):
        return False


def test_failed_leg_metrics_excluded(runner, monkeypatch):
    """A failed navigate leg must not feed nav_durations/nav_errors (FAIL-leg policy)."""
    monkeypatch.setattr(runner, 'nav', _StubNav())
    runner.nav_durations.clear()
    runner.nav_errors.clear()
    assert runner.run_mission('mission1') is False
    assert runner.nav_durations == []
    assert runner.nav_errors == []
```

- [ ] **Step 2: Run to verify current state**

Run: `python -m pytest tests/test_baseline.py -v`
Expected: `test_fail_rows_excluded_from_baseline` PASSes already (locks in existing behavior — that is the point).
Run (needs live sim NOT running — the stub never touches Nav2, but the module needs rclpy):
`python -m pytest tests/test_mission_run.py::test_failed_leg_metrics_excluded -v`
Expected: FAIL — `nav_durations == [90.0]` (the bug).

- [ ] **Step 3: Implement**

In `run_mission`, replace the navigate branch's metric collection:

```python
            if step.action == 'navigate':
                x, y = SEMANTIC_MAP[step.location]
                ok = self.nav.send_goal(x, y, timeout=NAV_TIMEOUT_S, yaw=step.yaw)
                # FAIL-leg policy (Session 16): a failed/timed-out leg's duration measures
                # the timeout, not the robot — keep it out of the row's aggregate metrics.
                if ok:
                    if self.nav.last_duration_s is not None:
                        self.nav_durations.append(self.nav.last_duration_s)
                    if self.nav.last_position_error is not None:
                        self.nav_errors.append(self.nav.last_position_error)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_mission_run.py::test_failed_leg_metrics_excluded tests/test_baseline.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/nav_fleet/nav_fleet/mission_runner.py tests/test_baseline.py tests/test_mission_run.py
git commit -m "fix(telemetry): failed navigate legs no longer skew mean_time_to_goal; lock FAIL-row baseline exclusion"
```

---

### Task 3: Constructor crash still logs a FAIL telemetry row

**Files:**
- Modify: `src/nav_fleet/nav_fleet/mission_runner.py:117-137` (`main`, `_log_mission`)
- Test: `tests/test_mission_run.py`

**Interfaces:**
- Produces: `_log_mission(name, ok, runner)` accepts `runner=None` (constructor never ran) and logs a FAIL row with zeroed position and NULL metrics. `main()` constructs `MissionRunner()` **inside** the try.

**WHY:** the CI stage's FAIL detection depends on the row existing (Release1Todo Session 16 Piece 3, item 2).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_mission_run.py`:

```python
def test_log_mission_tolerates_none_runner(monkeypatch):
    """Constructor crash path: _log_mission(runner=None) must still log a FAIL row."""
    from nav_fleet import mission_runner as mr
    recorded = {}
    monkeypatch.setattr(mr, 'log_run', lambda **kw: recorded.update(kw))
    mr._log_mission('mission1', False, None)
    assert recorded['result'] == 'FAIL'
    assert recorded['scenario'] == 'mission1'
    assert recorded['final_x'] == 0.0 and recorded['final_y'] == 0.0
    assert recorded['mean_time_to_goal'] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_mission_run.py::test_log_mission_tolerates_none_runner -v`
Expected: FAIL — `AttributeError: 'NoneType' object has no attribute 'nav'`.

- [ ] **Step 3: Implement**

Rewrite `_log_mission` and `main` in `mission_runner.py`:

```python
def _log_mission(name, ok, runner):
    nav = runner.nav if runner is not None else None
    log_run(
        scenario=name,
        steps=len(MISSIONS[name]),
        final_x=nav.last_final_x if nav is not None and nav.last_final_x is not None else 0.0,
        final_y=nav.last_final_y if nav is not None and nav.last_final_y is not None else 0.0,
        result='PASS' if ok else 'FAIL',
        step_log=[],
        robot_id=os.environ.get('ROBOT_ID', 'robot_001'),
        robot_type='jetson_ugv_pt',
        runner_type=os.environ.get('RUNNER_TYPE', 'local'),
        sim_engine=os.environ.get('SIM_ENGINE', 'gazebo'),
        nav_success_rate=1.0 if ok else 0.0,
        mean_position_error=_mean(runner.nav_errors) if runner is not None else None,
        mean_time_to_goal=_mean(runner.nav_durations) if runner is not None else None,
        power_mode=os.environ.get('POWER_MODE'),
    )


def main():
    parser = argparse.ArgumentParser(description='Run a named mission against Nav2.')
    parser.add_argument('mission', choices=sorted(MISSIONS))
    args = parser.parse_args()

    rclpy.init()
    runner = None
    ok = False
    try:
        # Constructed INSIDE the try: a constructor crash (e.g. rclpy/DDS failure) must
        # still produce the FAIL telemetry row that stage-4-hil's verdict depends on.
        runner = MissionRunner()
        ok = runner.run_mission(args.mission)
    except Exception as exc:  # still log a FAIL row on crash — docstring contract
        traceback.print_exc()
        print(f'mission {args.mission} crashed: {exc!r}')
    finally:
        rclpy.try_shutdown()
    _log_mission(args.mission, ok, runner)

    print(f"Mission {args.mission}: {'PASS' if ok else 'FAIL'}")
    for p in (runner.photo_paths if runner is not None else []):
        print(f'  photo: {p}')
    raise SystemExit(0 if ok else 1)
```

(Note: the crash log line moves from `runner.get_logger().error` to `print` — `runner` may be None on exactly this path.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_mission_run.py::test_log_mission_tolerates_none_runner tests/test_telemetry_logger.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/nav_fleet/nav_fleet/mission_runner.py tests/test_mission_run.py
git commit -m "fix(mission): constructor crash still logs FAIL telemetry row (stage-4-hil depends on it)"
```

---

### Task 4: `stage-2-gazebo` also runs the mission integration test

**Files:**
- Modify: `.github/workflows/ci.yml:221` (stage-2's pytest step)

**WHY:** same mission logic, sim-only, cheap — catches mission regressions before the HIL stage pays hardware time (design doc §4 suggestion; single-invocation works since the shared guarded `ros_context` conftest fixture, 2026-07-12).

- [ ] **Step 1: Edit the pytest step**

```yaml
      - name: Run navigation + mission integration tests
        run: |
          source /opt/ros/jazzy/setup.bash
          source install/setup.bash
          source ~/fleet-env/bin/activate   # pinned pytest 8.3.2 — GHA steps don't source
                                             # .bashrc, so this runner falls back to apt's
                                             # pytest 7.4.4 (owned by colcon-core) otherwise
          python -m pytest tests/test_navigation.py tests/test_mission_run.py -v --timeout=120
```

- [ ] **Step 2: Verify locally (the stage-2 equivalent run)**

With the sim up (`ros2 launch src/nav_fleet/launch/sim_launch.py headless:=true`, wait ~20 s):
Run: `python -m pytest tests/test_navigation.py tests/test_mission_run.py -v --timeout=120`
Expected: all tests PASS in one session (including the new Task 2/3 unit tests). Shut the sim down after (`pkill -f "gz sim" || true` plus Ctrl+C on the launch).

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci(stage-2): run mission integration test alongside navigation tests"
```

---

### Task 5: Jetson one-time prep — passwordless `nvpmodel` sudo + name-resolution check

**Files:** none in-repo (machine config on the Jetson, recorded in `docs/runbooks/JetsonInstallSession14.md` as a follow-up note if desired at review time).

**WHY:** the CI job must set the power mode non-interactively (Release1Todo power-policy item a).

- [ ] **Step 1: Install the sudoers drop-in on the Jetson**

```bash
ssh mike@jetson.local 'which nvpmodel'                     # confirm path, expect /usr/sbin/nvpmodel
ssh -t mike@jetson.local "echo 'mike ALL=(root) NOPASSWD: /usr/sbin/nvpmodel' | sudo tee /etc/sudoers.d/nvpmodel-ci && sudo chmod 440 /etc/sudoers.d/nvpmodel-ci && sudo visudo -c"
```

Expected: `visudo -c` prints `... parsed OK`. (If `which nvpmodel` returns a different path, use that path in the sudoers line — the rule must match the binary exactly.)

- [ ] **Step 2: Verify non-interactive sudo works**

```bash
ssh mike@jetson.local 'sudo -n nvpmodel -q'
```

Expected: prints the current mode (`NV Power Mode: 25W` / mode `1`) with **no password prompt**.

- [ ] **Step 3: Verify workstation name resolution (used by `discover`)**

```bash
getent hosts jetson.local
```

Expected: one line with the lease IP (e.g. `10.42.0.217`). If empty, the script's `ip neigh` fallback covers it — but note which path worked for the runbook.

---

### Task 6: `scripts/hil_stage.sh` — the HIL orchestration script

**Files:**
- Create: `scripts/hil_stage.sh` (executable: `chmod +x`)

**Interfaces:**
- Consumes: `JETSON_USER` (default `mike`), `JETSON_IP` (required except for `discover`), `POWER_MODE_ID` (default `1` = 25W), `STATE_DIR` (default `/tmp/hil_stage`).
- Produces subcommands the CI job (Task 8) calls: `discover` (prints the IP), `power-mode`, `sync <sha>`, `run` (sim-up → Nav2-up → mission → verify, with the retry-once policy), `teardown`. `run` leaves the mission photo in `$STATE_DIR/` and prints the Jetson's telemetry row to stdout.

- [ ] **Step 1: Write the script**

```bash
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
  source /opt/ros/jazzy/setup.bash
  source install/setup.bash
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
  jssh "$JENV && cd ${JETSON_REPO} && rm -f ${NAV2_LOG} && nohup ros2 launch src/nav_fleet/launch/nav2_only_launch.py > ${NAV2_LOG} 2>&1 & sleep 1; echo nav2-launched"
  local deadline=$((SECONDS + 120))
  # Two lifecycle managers report active (localization, then navigation) — gate on BOTH.
  until [ "$(jssh "grep -c 'Managed nodes are active' ${NAV2_LOG} 2>/dev/null" || echo 0)" -ge 2 ]; do
    if (( SECONDS >= deadline )); then
      echo 'FATAL: Nav2 not active within 120s — Jetson nav2 log tail:' >&2
      jssh "tail -n 40 ${NAV2_LOG}" >&2 || true
      return 1
    fi
    sleep 3
  done
  echo '=== [nav2-up] managed nodes active ==='
}

mission() {
  echo '=== [mission] running mission1 on the Jetson (budget 300s) ==='
  require_ip
  local before_id
  before_id=$(jssh "python3 - <<'PY'
import sqlite3
try:
    c = sqlite3.connect('autonomous-fleet-testbed/reports/fleet_runs.db')
    print(c.execute('SELECT COALESCE(MAX(id),0) FROM runs').fetchone()[0])
except Exception:
    print(0)
PY")
  echo "$before_id" > "$STATE_DIR/before_id"
  local rc=0
  timeout 300 ssh -o BatchMode=yes "${JETSON_USER}@${JETSON_IP}" \
    "$JENV && cd ${JETSON_REPO} && RUNNER_TYPE=hil_jetson POWER_MODE=${POWER_MODE_LABEL} python3 -m nav_fleet.mission_runner mission1" \
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
import sqlite3
c = sqlite3.connect('autonomous-fleet-testbed/reports/fleet_runs.db')
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
  if run_once; then return 0; fi
  # Retry-once policy (design doc §3): only for a discovery-shaped failure.
  if grep -qE 'Nav2 action server unavailable|Goal rejected after all retries|no camera frame' \
       "$STATE_DIR/mission.out" 2>/dev/null; then
    echo '=== discovery-shaped failure: full both-sides teardown, 5s settle, ONE retry ==='
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
    jssh "pkill -9 -f '[n]av2|[c]omponent_container|[m]ission_runner' || true; cd ${JETSON_REPO} && git checkout main >/dev/null 2>&1 || true" || true
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

cmd="${1:?usage: hil_stage.sh discover|power-mode|sync <sha>|run|teardown}"
shift || true
case "$cmd" in
  discover)   discover ;;
  power-mode) power_mode ;;
  sync)       sync "$@" ;;
  run)        run ;;
  teardown)   teardown ;;
  *) echo "FATAL: unknown subcommand '$cmd'" >&2; exit 1 ;;
esac
```

- [ ] **Step 2: Syntax check + make executable**

Run: `bash -n scripts/hil_stage.sh && chmod +x scripts/hil_stage.sh && echo OK`
Expected: `OK`.

- [ ] **Step 3: Smoke-test the safe subcommands (no sim involved)**

```bash
scripts/hil_stage.sh discover                 # expect the Jetson IP printed
JETSON_IP=$(scripts/hil_stage.sh discover) scripts/hil_stage.sh power-mode   # expect 25W printed
scripts/hil_stage.sh teardown                 # expect clean no-op run, exit 0
```

Expected: IP printed; `NV Power Mode: 25W`; teardown exits 0 with nothing to kill.

- [ ] **Step 4: Commit**

```bash
git add scripts/hil_stage.sh
git commit -m "feat(ci): hil_stage.sh — locally-runnable stage-4-hil orchestration (design doc §1–§3)"
```

---

### Task 7: Local end-to-end HIL run via the script (the stage's Tier-1 test)

**Files:** none — verification only.

**WHY:** the whole point of the script layout — prove the exact code CI will run, locally, before any push. This is the same procedure as the 2026-07-14 13c run, now automated.

- [ ] **Step 1: Full run**

```bash
export JETSON_IP=$(scripts/hil_stage.sh discover)
POWER_MODE_ID=1 scripts/hil_stage.sh power-mode      # 25W for the build
scripts/hil_stage.sh sync $(git rev-parse HEAD)
export POWER_MODE_ID=0                                # 15W for the mission (deployment power)
scripts/hil_stage.sh power-mode
scripts/hil_stage.sh run
echo "exit=$?"
POWER_MODE_ID=1 scripts/hil_stage.sh power-mode      # restore 25W steady-state
```

Expected: phase banners in order (`[sim-up]` → `[nav2-up]` → `[mission]` → `[verify] OK`), `Mission mission1: PASS`, a printed telemetry row containing `'hil_jetson'` and `'15W'`, `exit=0`. Watch the mission wall time — this is the first *measured* 15W-pinned mission; if it drifts far from the 2026-07-11 ~18 s reference, note it against the §3 budgets.

**Note:** `sync` requires the current commit to be pushed (the Jetson fetches from origin) — push the branch first: `git push -u origin session-16-stage4-hil`.

- [ ] **Step 2: Verify the photo landed locally**

Run: `ls -la /tmp/hil_stage/*.png`
Expected: one PNG with today's timestamp. Open it — it should show the bedroom from the doorway.

- [ ] **Step 3: Teardown + confirm clean**

```bash
scripts/hil_stage.sh teardown
pgrep -af 'gz sim|parameter_bridge|robot_state_publisher' || echo CLEAN
ssh mike@$JETSON_IP "pgrep -af 'component_container|mission_runner' || echo JETSON_CLEAN"
```

Expected: `CLEAN` and `JETSON_CLEAN`.

- [ ] **Step 4: Fix anything that surfaced, commit fixes**

Any script bug found here gets fixed and committed now (`fix(ci): ...`) — this loop is cheap; the CI loop is not.

---

### Task 8: `ci.yml` — `stage-4-hil` replaces `stage-4-isaac`; registry build cache

**Files:**
- Modify: `.github/workflows/ci.yml` (delete the `stage-4-isaac` job block entirely; add `stage-4-hil` in its place; change `stage-5-reports-hw`'s `needs`; stage-3 cache config; update the `changes` job comment that references Isaac)

**Interfaces:**
- Consumes: `scripts/hil_stage.sh` subcommands (Task 6).
- Produces: pipeline shape `stage-2-gazebo → stage-3-arm64 → stage-4-hil → stage-5-reports-hw` (design doc §4 — no renumbering; Isaac scripts stay on disk, retired from the workflow only).

- [ ] **Step 1: Replace the `stage-4-isaac` job with `stage-4-hil`**

Delete lines for the whole `stage-4-isaac:` job and insert:

```yaml
  stage-4-hil:
    name: "Stage 4 — HIL: Gazebo (x86) ↔ Nav2 + Mission 1 (real Jetson)"
    # Replaces stage-4-isaac (retired 2026-07 — Session 16; scripts stay in git/on disk).
    # One job on the x86 runner drives the Jetson over SSH as a lab instrument — see
    # docs/session15-hil-ci-stage-design.md for every decision (orchestration §1,
    # pass/fail §2, timeouts+teardown §3, naming §4). All logic lives in
    # scripts/hil_stage.sh so the stage is runnable/debuggable locally.
    # Skips on docs-only pushes (inherits stage-3-arm64's `changes` gate) — same
    # accepted behavior as stage-4-isaac had.
    runs-on: [self-hosted, x86, gpu, rtx5080]
    needs: stage-3-arm64
    timeout-minutes: 15
    env:
      RMW_IMPLEMENTATION: rmw_cyclonedds_cpp
      ROS_DOMAIN_ID: "0"
      JETSON_USER: mike
      POWER_MODE_ID: "0"          # 15W — the HIL mission runs at the rover's deployment
                                  # power budget (Mike, 2026-07-14); builds run at 25W
                                  # (explicit override below); restored to 25W at the end.
      STATE_DIR: /tmp/hil_stage
    steps:
      - uses: actions/checkout@v4

      - name: Discover Jetson (DHCP lease — never hard-coded)
        run: |
          JETSON_IP=$(scripts/hil_stage.sh discover)
          echo "JETSON_IP=${JETSON_IP}" >> $GITHUB_ENV
          echo "Jetson at ${JETSON_IP}"

      - name: Jetson to 25W for the build (build fast, test at deployment power)
        run: POWER_MODE_ID=1 scripts/hil_stage.sh power-mode

      - name: Sync + build the commit under test on the Jetson
        run: scripts/hil_stage.sh sync ${{ github.sha }}

      - name: Build x86 workspace
        run: |
          source /opt/ros/jazzy/setup.bash
          colcon build --symlink-install

      - name: Jetson to 15W — the mission runs at deployment power, recorded in telemetry
        run: scripts/hil_stage.sh power-mode

      - name: Record start time
        run: echo "HIL_START=$(date +%s)" >> $GITHUB_ENV

      - name: Run HIL mission (sim up → Nav2 up → mission → verify; one retry on discovery flake)
        run: scripts/hil_stage.sh run

      - name: Record HIL timing
        if: always()
        run: |
          END=$(date +%s)
          HIL_S=$((END - HIL_START))
          echo "Stage 4 HIL wall time: ${HIL_S}s"
          echo "### Stage 4 HIL wall time: ${HIL_S}s" >> $GITHUB_STEP_SUMMARY

      - name: Upload mission photo artifact
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: hil-mission-photo-${{ github.run_number }}
          path: /tmp/hil_stage/*.png
          if-no-files-found: warn

      - name: Show sim log tail on failure
        if: failure()
        run: tail -n 60 /tmp/hil_stage/sim.log 2>/dev/null || true

      - name: Teardown (both sides, unconditional)
        if: always()
        run: scripts/hil_stage.sh teardown

      - name: Restore Jetson to 25W (its steady-state runner mode)
        if: always()
        run: POWER_MODE_ID=1 scripts/hil_stage.sh power-mode || true
```

- [ ] **Step 2: Rewire `stage-5-reports-hw`**

Change its `needs:` line:

```yaml
    needs: stage-4-hil
```

Add a comment above the job noting: in phase 1 the HIL telemetry row lives on the Jetson's local DB (printed to the stage-4 log); shipping it into the workstation `FLEET_DB` for drift tracking is phase 2 (Task 13) — until then this job re-reports sim-path data after a hardware-path success, same as it effectively did in the Isaac era.

- [ ] **Step 3: Registry-backed build cache for `stage-3-arm64`**

Replace the `cache-from`/`cache-to` lines in the build-push step:

```yaml
          cache-from: type=registry,ref=ghcr.io/${{ github.repository }}:buildcache
          cache-to: type=registry,ref=ghcr.io/${{ github.repository }}:buildcache,mode=max
```

And raise BuildKit's GC budget in the same job's buildx setup (belt-and-braces — the default budget evicts the ~1–2 GB apt layer first):

```yaml
      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3
        with:
          buildkitd-config-inline: |
            [worker.oci]
              gc = true
            [[worker.oci.gcpolicy]]
              all = true
              keepBytes = 20000000000
```

- [ ] **Step 4: Sanity-check the workflow file**

Run: `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml')); print('YAML OK')"`
Expected: `YAML OK`. Also `grep -c "stage-4-isaac" .github/workflows/ci.yml` → expect `0`.

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: stage-4-hil replaces stage-4-isaac; registry-backed arm64 build cache"
```

---

### Task 9: PR + first green pipeline

**WHY:** a PR to main triggers the full pipeline including the new stage — the CI test vehicle for the workflow change itself.

- [ ] **Step 1: Push and open the PR**

```bash
git push -u origin session-16-stage4-hil
gh pr create --title "Session 16: stage-4-hil replaces stage-4-isaac (+ telemetry hardening)" \
  --body "Implements docs/session15-hil-ci-stage-design.md phase 1. Gazebo on the x86 runner, Nav2 + Mission 1 on the real Jetson over SSH, photo artifact + hil_jetson telemetry row. Also: power_mode telemetry, FAIL-leg metric policy, constructor-crash FAIL row, mission test in stage-2, registry-backed arm64 build cache.

🤖 Generated with [Claude Code](https://claude.com/claude-code)"
```

- [ ] **Step 2: Watch the run; iterate to green**

```bash
gh pr checks --watch
```

Expected: all jobs green including `stage-4-hil`. On failure: read the job log (phase banners point at the failing phase), reproduce **locally** with `scripts/hil_stage.sh run` — never debug via push-and-pray. Commit fixes to the branch; each push re-runs the pipeline.

- [ ] **Step 3: Confirm the photo artifact**

On the green run's page (or `gh run view <id>`), confirm the `hil-mission-photo-*` artifact exists and contains the doorway photo, and the job log prints the `('mission1', 'PASS', 'hil_jetson', 'gazebo', '25W', ...)` row.

---

### Task 10: The 3×-green reproducibility gate

**WHY:** Session 15's HIL record was a single warm run; reproducibility across fresh DDS state is the open risk this stage exists to close (design doc §5). This gate also releases the microSD rollback card (runbook policy).

- [ ] **Step 1: Two more consecutive green runs of the same head SHA**

```bash
gh run rerun <run-id-of-the-green-run>   # wait for green
gh run rerun <run-id>                    # and once more
```

Expected: `stage-4-hil` green 3× consecutively (the Task 9 run + these two). Any red run resets the count — investigate locally, fix, start the count again.

- [ ] **Step 2: Merge**

```bash
gh pr merge --squash --delete-branch   # or Mike's preferred merge mode — ASK before merging
```

(Per repo convention, confirm the integration choice with Mike — squash vs merge commit.)

- [ ] **Step 3: Record the milestone**

- Tick the Piece 1 boxes + "Session Complete When" item 1 in `Release1Todo.md` Session 16, with run IDs.
- Note in `docs/runbooks/JetsonInstallSession14.md` (microSD paragraph) and memory: the 3×-green condition for the microSD is met once this holds **on main** as well — confirm the post-merge main run is green too.
- Update `docs/runbooks/Mission1HILSession15.md` intro: the CI stage now exists; the manual procedure remains as the debugging path ("Session Complete When" item 5).
- Commit: `docs(session-16): stage-4-hil 3x green — Piece 1 milestone recorded`

---

### Task 11: Corner-clip investigation (manual, with Mike — flaky-stage risk)

**WHY:** Mike observed (2026-07-12, GUI session) the robot appearing to clip the hallway arch corner on the doorway→home_base return leg. Not captured by telemetry (the mission CLI doesn't run the collision check). If real, it is a latent `stage-4-hil` flake.

- [ ] **Step 1: Reproduce with eyes + data**

Terminal A (plain terminal, NOT a VS-Code/Claude-Code shell — snap GTK pollution): `gz sim -g` after the sim is up.
Terminal B: `ros2 launch src/nav_fleet/launch/sim_launch.py` and run `python -m nav_fleet.mission_runner mission1` 3×, watching the arch corner on each return leg.
Data: in a third terminal, `ros2 topic echo /robot_001/scan --field ranges | ...` is too raw — instead run `python -m pytest tests/test_navigation.py::test_no_collision -v --timeout=120` once after the mission runs to get the BR-02 collision check's verdict on the same session.

- [ ] **Step 2: Decide and record**

Three possible outcomes, each with its action:
- **Visual-only near-miss** (wheel close at 3× RTF, no contact): record as no-op in Release1Todo with the evidence; done.
- **Real contact**: file it as a param-tuning item (inflation radius vs the arch corner; RPP `use_collision_detection: false` interaction) — tune as a separate reviewed change, re-run Task 7's local HIL to confirm no regression, and note the 3×-green count restarts if the fix lands after Task 10.
- **Unclear**: add a scan-min-range assertion to the mission path as a Session 17 hardening item; record.

Tick the Piece 3 box in `Release1Todo.md` either way — "closed or explicitly re-deferred with a written reason."

---

### Task 12 (phase 2a — GATED on Task 10): containerized mission on the Jetson

**Files:**
- Modify: `Dockerfile` (add `COPY tools/ tools/` — the image currently lacks `tools/`, so `mission_runner`'s `from tools.telemetry_logger import log_run` would crash in-container)
- Modify: `scripts/hil_stage.sh` (a `mission_container` variant behind `HIL_CONTAINER=1`)
- Modify: `.github/workflows/ci.yml` (stage-4-hil: `permissions: packages: read`, docker login + pull on the Jetson over SSH, `HIL_CONTAINER: "1"`)

**Interfaces:**
- Consumes: the `stage-3-arm64` GHCR image `ghcr.io/<repo>:<sha>` (finally making the arm64→HIL edge real, design doc §4).
- Produces: the mission executor runs inside the arm64 container on the Jetson with `--network host --ipc host` (DDS via host network), `-v ~/autonomous-fleet-testbed/reports:/ros2_ws/reports` (photo + DB land on the host as before), env `RUNNER_TYPE=hil_jetson POWER_MODE=<label> RMW_IMPLEMENTATION=rmw_cyclonedds_cpp ROS_DOMAIN_ID=0`.

- [ ] **Step 1: Dockerfile** — after the existing `COPY src/ src/` line add:

```dockerfile
# tools/ is imported by nav_fleet.mission_runner (telemetry_logger) — required to run
# the mission executor inside this image (stage-4-hil phase 2).
COPY tools/ tools/
```

- [ ] **Step 2: `hil_stage.sh` container mission** — in `mission()`, branch on `HIL_CONTAINER`:

```bash
  local mission_cmd
  if [ "${HIL_CONTAINER:-0}" = "1" ]; then
    mission_cmd="docker run --rm --network host --ipc host \
      -v \$HOME/autonomous-fleet-testbed/reports:/ros2_ws/reports \
      -e RUNNER_TYPE=hil_jetson -e POWER_MODE=${POWER_MODE_LABEL} \
      -e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp -e ROS_DOMAIN_ID=0 \
      ${HIL_IMAGE:?HIL_CONTAINER=1 requires HIL_IMAGE} \
      bash -c 'source /opt/ros/jazzy/setup.bash && source /ros2_ws/install/setup.bash && python3 -m nav_fleet.mission_runner mission1'"
  else
    mission_cmd="$JENV && cd ${JETSON_REPO} && RUNNER_TYPE=hil_jetson POWER_MODE=${POWER_MODE_LABEL} python3 -m nav_fleet.mission_runner mission1"
  fi
  timeout 300 ssh -o BatchMode=yes "${JETSON_USER}@${JETSON_IP}" "$mission_cmd" \
    2>&1 | tee "$STATE_DIR/mission.out" || rc=$?
```

- [ ] **Step 3: ci.yml** — stage-4-hil gains `permissions: { packages: read }`, env `HIL_CONTAINER: "1"` and `HIL_IMAGE: ghcr.io/${{ github.repository }}:${{ github.sha }}`, plus a pull step after `sync`:

```yaml
      - name: Pull the stage-3 arm64 image onto the Jetson
        run: |
          echo "${{ secrets.GITHUB_TOKEN }}" | \
            ssh -o BatchMode=yes ${JETSON_USER}@${JETSON_IP} \
              "docker login ghcr.io -u ${{ github.actor }} --password-stdin && docker pull ${HIL_IMAGE}"
```

- [ ] **Step 4: Verify locally first** (`HIL_CONTAINER=1 HIL_IMAGE=ghcr.io/sdfinn/autonomous-fleet-testbed:latest scripts/hil_stage.sh run` after a manual pull with Mike's gh-token flow), then via a PR run. Expected: same PASS + photo + row, but the executor ran inside the arm64 image.

- [ ] **Step 5: Commit** — `feat(ci): stage-4-hil phase 2 — mission executor runs inside the stage-3 arm64 image`

---

### Task 13 (phase 2b — GATED on Task 10): ship the HIL telemetry row to the workstation drift DB

**Files:**
- Modify: `scripts/hil_stage.sh` (`verify()` gains a ship step)

**Interfaces:**
- Consumes: design doc §2 decision — ship the **row** (SELECT over SSH → local INSERT), never the DB file (independent histories; schema authority stays on the workstation).
- Produces: the new `hil_jetson` row appended to `$FLEET_DB` (workstation, `/home/mike/fleet-ci-data/fleet_runs.db` in CI) so `baseline_monitor` tracks HIL trends; `stage-5-reports-hw` becomes genuinely hardware-fed.

- [ ] **Step 1: Implement** — append to `verify()` (only when `FLEET_DB` is set, so local runs without it skip shipping):

```bash
  if [ -n "${FLEET_DB:-}" ]; then
    echo '=== [verify] shipping row to workstation drift DB ==='
    jssh "python3 - <<PY
import json, sqlite3
c = sqlite3.connect('autonomous-fleet-testbed/reports/fleet_runs.db')
c.row_factory = sqlite3.Row
r = c.execute('SELECT * FROM runs WHERE id > ${before_id} AND runner_type=\'hil_jetson\' ORDER BY id DESC LIMIT 1').fetchone()
print(json.dumps({k: r[k] for k in r.keys() if k != 'id'}))
PY" > "$STATE_DIR/hil_row.json"
    python3 - <<PY
import json, os, sqlite3
row = json.load(open(os.environ['STATE_DIR'] + '/hil_row.json'))
import sys; sys.path.insert(0, '.')
from tools.telemetry_logger import init_db
db = os.environ['FLEET_DB']
init_db(db)
conn = sqlite3.connect(db)
cols = {r[1] for r in conn.execute('PRAGMA table_info(runs)')}
row = {k: v for k, v in row.items() if k in cols}
conn.execute(f"INSERT INTO runs ({','.join(row)}) VALUES ({','.join('?'*len(row))})",
             list(row.values()))
conn.commit()
print('shipped HIL row into', db)
PY
  fi
```

And add `FLEET_DB: /home/mike/fleet-ci-data/fleet_runs.db` to stage-4-hil's `env` in `ci.yml`.

- [ ] **Step 2: Test locally** with a scratch DB: `FLEET_DB=/tmp/hil_ship_test.db scripts/hil_stage.sh run`, then `python3 -c "import sqlite3; print(*sqlite3.connect('/tmp/hil_ship_test.db').execute('SELECT scenario,result,runner_type,power_mode FROM runs'))"` → expect the shipped row.

- [ ] **Step 3: Commit** — `feat(ci): ship HIL telemetry row into workstation drift DB (design §2 phase 2)`

---

## Self-Review (done at write time)

1. **Spec coverage:** Piece 1 → Tasks 5–10 + 12–13 (phase 2 explicitly gated, re-deferrable per session text); Piece 3 items 1/2/4 → Tasks 2/3/4; Piece 3 item 3 → Task 11; power policy a/b/c → Tasks 5/1/9 (budgets validated live during Task 9's runs at 25W); registry cache + GC budget → Task 8; NVMe re-benchmark → cold number already recorded 2026-07-13 (568s, run 29301726080); the cached number falls out of Task 9's second/third runs — record it in the Part 7 table during Task 10 step 3. Mission 2 = Plan B (out of scope here by design).
2. **Placeholder scan:** none — all code/commands are concrete.
3. **Type consistency:** `power_mode` is `TEXT`/`str` end to end (`"25W"` label, not the nvpmodel id); `log_run(power_mode=...)` matches Task 1's signature in Tasks 3/12; `hil_stage.sh` subcommand names in Task 8's YAML match Task 6's `case` arms.

**Known judgment calls for Mike's review:**
- `JETSON_USER` as plain workflow env (not a repo variable/secret) — resolves design §5's inventory item the simple way.
- `sync` leaves the Jetson repo detached during a run; teardown restores `main`.
- Nav2-active gate = TWO "Managed nodes are active" lines (localization + navigation).
- Retry trigger markers: `Nav2 action server unavailable` / `Goal rejected after all retries` / `no camera frame` — the three discovery-shaped failure strings the mission actually emits.
- Power split per Mike (2026-07-14): Jetson builds at 25W, HIL mission at 15W (deployment budget), restore to 25W always. First HIL run (2026-07-11, pre-pin) was already at 15W and passed — budgets hold.
- Robot deployment (container vs bare) is a Session 18 decision; phase 2 (Task 12) exists to de-risk the container path — leaning containerized brain + bare vendor driver, hybrid over DDS.
