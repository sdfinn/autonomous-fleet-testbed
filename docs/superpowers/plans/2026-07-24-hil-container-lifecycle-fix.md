# HIL Container Lifecycle Fix — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate the ~15.6–16.1s of dead time per Mission 2 scenario transition on
container-mode HIL days, root-caused in Session 17 Piece 8 to `tools/mission2_day.py`
launching a fresh `docker run --rm` per scenario (3×/day) instead of reusing one
container for the whole day.

**Architecture:** `JetsonExecutor` starts ONE long-lived container (`docker run -d ...
sleep infinity`) when it's constructed (container mode only — bare-metal is
unaffected), and each scenario's `_ssh_mission2()` becomes a `docker exec` into that
same container instead of a fresh `docker run --rm`. The container is torn down once,
at day end, via a new `close()` method wired into `mission2_day.main()`'s existing
cleanup `finally` block.

**Tech Stack:** Python 3, pytest, `subprocess`/SSH to the Jetson, Docker on the Jetson.

## Global Constraints

- Bare-metal mode (`HIL_CONTAINER` unset) must not change behavior at all — it never
  had a container to begin with.
- The two existing bind mounts (`reports/`, `fleet-ci-data`) and `--network host
  --ipc host` flags must still apply — they just move from being per-`docker run`
  flags to one-time flags on the long-lived container's `docker run -d`.
- `RUNNER_TYPE`/`POWER_MODE` don't vary within a day — bake them into the container's
  environment at start instead of passing `-e` on every `docker exec` (docker exec
  inherits the container's `docker run -e` environment by default, no extra flags
  needed).
- Keep the already-present (uncommitted) `[timing] ssh dispatch`/`ssh returned` log
  lines in `_ssh_mission2` exactly as they are — they still bracket the whole call and
  remain useful as the regression tripwire for this exact class of problem (Piece 8
  recommended keeping them either way).
- Follow existing test style in `tests/test_mission2_day.py` (monkeypatch
  `subprocess.run` with a call-capturing fake, `HIL_CONTAINER`/`HIL_IMAGE` env vars via
  `monkeypatch.setenv`).

---

### Task 0: Branch setup

- [ ] **Step 1: Create a feature branch**

```bash
cd /home/mike/autonomous-fleet-testbed
git checkout -b fix/hil-container-lifecycle
```

The two currently-uncommitted `[timing]` log lines in `tools/mission2_day.py` come
along for the ride (working tree changes survive a `checkout -b`) — they'll be
committed together with Task 2's changes to the same function.

---

### Task 1: Long-lived container lifecycle on `JetsonExecutor`

**Files:**
- Modify: `tools/mission2_day.py` (module constants ~line 83–90, `MissionExecutor`
  class ~line 166–172, `JetsonExecutor.__init__`/`_require_image_local` ~line 200–231)
- Test: `tests/test_mission2_day.py`

**Interfaces:**
- Produces: `mission2_day.HIL_CONTAINER_NAME` (module constant, `'hil_mission2'`),
  `MissionExecutor.close()` (no-op base method), `JetsonExecutor._start_container()`,
  `JetsonExecutor._stop_container()`, `JetsonExecutor.close()`.
- Consumes (existing): `JETSON_USER`, `POWER_MODE_LABEL`, `self.image`, `self.ip`,
  `log` (module logger from `tools.log_setup.get_logger`).

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_mission2_day.py`, right after
`test_jetson_executor_container_mode_fails_loud_when_image_missing` (around line 92):

```python
def test_jetson_executor_container_mode_starts_long_lived_container(monkeypatch):
    """Piece 8 fix: container mode must start ONE long-lived container for the whole
    day instead of a fresh `docker run --rm` per scenario (was costing ~15.6-16.1s of
    container start/teardown per transition, measured live 2026-07-23)."""
    monkeypatch.setenv('HIL_CONTAINER', '1')
    monkeypatch.setenv('HIL_IMAGE', 'ghcr.io/sdfinn/autonomous-fleet-testbed:deadbeef')
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, returncode=0, stdout='', stderr='')

    monkeypatch.setattr(subprocess, 'run', fake_run)
    mission2_day_module.JetsonExecutor('10.42.0.217', '/tmp/hil_stage')

    ssh_cmds = [c for c in calls if c[:1] == ['ssh']]
    start_cmd = next(c for c in ssh_cmds if 'docker run -d' in c[-1])
    assert '--name hil_mission2' in start_cmd[-1]
    assert 'sleep infinity' in start_cmd[-1]
    assert 'ghcr.io/sdfinn/autonomous-fleet-testbed:deadbeef' in start_cmd[-1]
    assert '--rm' not in start_cmd[-1]
    rm_index = next(i for i, c in enumerate(ssh_cmds) if 'docker rm -f hil_mission2' in c[-1])
    assert rm_index < ssh_cmds.index(start_cmd)   # stale-container cleanup runs first


def test_close_container_mode_removes_the_container(monkeypatch):
    monkeypatch.setenv('HIL_CONTAINER', '1')
    monkeypatch.setenv('HIL_IMAGE', 'ghcr.io/sdfinn/autonomous-fleet-testbed:deadbeef')
    monkeypatch.setattr(
        subprocess, 'run',
        lambda *a, **k: subprocess.CompletedProcess(a, returncode=0, stdout='', stderr=''))
    ex = mission2_day_module.JetsonExecutor('10.42.0.217', '/tmp/hil_stage')

    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, returncode=0, stdout='', stderr='')

    monkeypatch.setattr(subprocess, 'run', fake_run)
    ex.close()

    assert any('docker rm -f hil_mission2' in c[-1] for c in calls if c[:1] == ['ssh'])


def test_close_bare_metal_is_a_noop(monkeypatch):
    monkeypatch.delenv('HIL_CONTAINER', raising=False)
    ex = mission2_day_module.JetsonExecutor('10.42.0.217', '/tmp/hil_stage')

    def _boom(*a, **k):
        raise AssertionError('close() must not touch docker/SSH in bare-metal mode')
    monkeypatch.setattr(subprocess, 'run', _boom)
    ex.close()   # must not raise
```

- [ ] **Step 2: Run the new tests to verify they fail**

```bash
cd /home/mike/autonomous-fleet-testbed
python -m pytest tests/test_mission2_day.py -v -k "starts_long_lived or close_container or close_bare_metal"
```

Expected: FAIL — `AttributeError`/`NameError` (`HIL_CONTAINER_NAME` doesn't exist yet,
`close()` doesn't exist yet, `_start_container` never gets called).

- [ ] **Step 3: Add the module constant**

In `tools/mission2_day.py`, near the other Jetson-connection constants (right after the
`JENV = (...)` block, before `STATE_DIR = ...`, around line 88):

```python
HIL_CONTAINER_NAME = 'hil_mission2'   # long-lived container reused for the whole HIL
# day (S17 Piece 8 fix) — a fresh `docker run --rm` per scenario was measured costing
# ~15.6-16.1s of pure container start/teardown per transition, none of it robot motion.
```

- [ ] **Step 4: Add `close()` to the `MissionExecutor` base class**

Find (around line 166–172):

```python
class MissionExecutor:
    def run(self, ball_xy=None, color=None):
        raise NotImplementedError

    def reset(self):
        """Clear any per-run bookkeeping before the next execution."""
```

Replace with:

```python
class MissionExecutor:
    def run(self, ball_xy=None, color=None):
        raise NotImplementedError

    def reset(self):
        """Clear any per-run bookkeeping before the next execution."""

    def close(self):
        """Tear down any day-level resources (e.g. a long-lived container). No-op by
        default — only JetsonExecutor's container mode currently needs this."""
```

- [ ] **Step 5: Start the container in `JetsonExecutor.__init__`, add the lifecycle methods**

Find (around line 200–231):

```python
    def __init__(self, jetson_ip, state_dir):
        if not jetson_ip:
            raise RuntimeError('JetsonExecutor needs JETSON_IP (run: hil_stage.sh discover)')
        self.ip = jetson_ip
        self.state_dir = state_dir
        self.image = None
        if os.environ.get('HIL_CONTAINER') == '1':
            self.image = os.environ['HIL_IMAGE']   # KeyError is a real misconfiguration — surface
            self._require_image_local()

    def _require_image_local(self):
```

Replace the `__init__` body's last two lines and add the new methods right after
`_require_image_local` (before `def run(self, ...)`):

```python
    def __init__(self, jetson_ip, state_dir):
        if not jetson_ip:
            raise RuntimeError('JetsonExecutor needs JETSON_IP (run: hil_stage.sh discover)')
        self.ip = jetson_ip
        self.state_dir = state_dir
        self.image = None
        if os.environ.get('HIL_CONTAINER') == '1':
            self.image = os.environ['HIL_IMAGE']   # KeyError is a real misconfiguration — surface
            self._require_image_local()
            self._start_container()

    def _require_image_local(self):
```

...and immediately after the existing `_require_image_local` method body (right before
`def run(self, ball_xy=None, color=None):`):

```python
    def _start_container(self):
        """Start ONE long-lived container for the whole HIL day (S17 Piece 8 fix): the
        old `docker run --rm` per scenario paid ~15.6-16.1s of container start/teardown
        per transition (measured live 2026-07-23, manual HIL day) — a fresh overlay
        filesystem + network namespace + `--rm` cleanup, three times a day, none of it
        robot motion. `_ssh_mission2` now `docker exec`s into THIS container per
        scenario instead. RUNNER_TYPE/POWER_MODE are baked in here since they don't
        vary within a day (docker exec inherits a container's `docker run -e`
        environment by default — no need to repeat them per exec)."""
        self._stop_container()   # best-effort: clear a stale container from a crashed prior day
        cmd = (
            f'docker run -d --name {HIL_CONTAINER_NAME} --network host --ipc host '
            "-v $HOME/autonomous-fleet-testbed/reports:/ros2_ws/reports "
            "-v $HOME/fleet-ci-data:/root/fleet-ci-data "
            f"-e RUNNER_TYPE=hil_jetson -e POWER_MODE={POWER_MODE_LABEL} "
            "-e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp -e ROS_DOMAIN_ID=0 "
            f"{self.image} sleep infinity")
        proc = subprocess.run(
            ['ssh', '-o', 'BatchMode=yes', f'{JETSON_USER}@{self.ip}', cmd],
            capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(f'failed to start long-lived HIL container: {proc.stderr}')
        log.info(f'started long-lived HIL container {HIL_CONTAINER_NAME} ({self.image})')

    def _stop_container(self):
        subprocess.run(
            ['ssh', '-o', 'BatchMode=yes', f'{JETSON_USER}@{self.ip}',
             f'docker rm -f {HIL_CONTAINER_NAME}'],
            capture_output=True, text=True)

    def close(self):
        """Tear down the long-lived container at the end of the day (container mode
        only — bare-metal never had a container to close)."""
        if self.image is not None:
            log.info(f'stopping long-lived HIL container {HIL_CONTAINER_NAME}')
            self._stop_container()

```

- [ ] **Step 6: Run the tests again to verify they pass**

```bash
python -m pytest tests/test_mission2_day.py -v -k "starts_long_lived or close_container or close_bare_metal"
```

Expected: PASS (3 tests).

- [ ] **Step 7: Run the full existing `test_mission2_day.py` suite to check nothing broke**

```bash
python -m pytest tests/test_mission2_day.py -v
```

Expected: all PASS, including the pre-existing container-mode tests
(`test_jetson_executor_container_mode_passes_when_image_present` and
`test_pull_photos_container_mode_translates_root_prefix_to_tilde` now also exercise
`_start_container`'s extra SSH call as a side effect of construction — they should
still pass unchanged since they only look for specific command shapes, not an exact
call count).

- [ ] **Step 8: Commit**

```bash
git add tools/mission2_day.py tests/test_mission2_day.py
git commit -m "feat(mission2_day): long-lived HIL container lifecycle (JetsonExecutor)"
```

---

### Task 2: Rewire `_ssh_mission2` to `docker exec`, wire `close()` into `main()`

**Files:**
- Modify: `tools/mission2_day.py` (`_ssh_mission2` ~line 252–298, `main()` ~line
  678–736)
- Test: `tests/test_mission2_day.py`

**Interfaces:**
- Consumes: `HIL_CONTAINER_NAME`, `JetsonExecutor.close()` from Task 1.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_mission2_day.py`, after the tests added in Task 1:

```python
def test_ssh_mission2_container_mode_uses_docker_exec(monkeypatch):
    """The per-scenario call must exec into the long-lived container, not `docker run`
    a new one — that's the actual Piece 8 fix (Task 1 only added the container's
    lifecycle; this is what stops using it)."""
    monkeypatch.setenv('HIL_CONTAINER', '1')
    monkeypatch.setenv('HIL_IMAGE', 'ghcr.io/sdfinn/autonomous-fleet-testbed:deadbeef')
    monkeypatch.setattr(
        subprocess, 'run',
        lambda *a, **k: subprocess.CompletedProcess(a, returncode=0, stdout='', stderr=''))
    ex = mission2_day_module.JetsonExecutor('10.42.0.217', '/tmp/hil_stage')

    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, returncode=0, stdout='ok', stderr='')

    monkeypatch.setattr(subprocess, 'run', fake_run)
    ex._ssh_mission2('no_ball')

    ssh_cmd = next(c for c in calls if 'ssh' in c)
    assert 'docker exec hil_mission2' in ssh_cmd[-1]
    assert 'docker run' not in ssh_cmd[-1]
    assert 'python3 -m nav_fleet.mission_runner mission2' in ssh_cmd[-1]
```

- [ ] **Step 2: Run it to verify it fails**

```bash
python -m pytest tests/test_mission2_day.py -v -k test_ssh_mission2_container_mode_uses_docker_exec
```

Expected: FAIL — the current `_ssh_mission2` still emits `docker run --rm ...`.

- [ ] **Step 3: Rewrite `_ssh_mission2`'s container branch**

Find (around line 271–284):

```python
        if os.environ.get('HIL_CONTAINER') == '1':
            image = self.image
            cmd = (
                "docker run --rm --name hil_mission2 --network host --ipc host "
                "-v $HOME/autonomous-fleet-testbed/reports:/ros2_ws/reports "
                "-v $HOME/fleet-ci-data:/root/fleet-ci-data "
                f"-e RUNNER_TYPE=hil_jetson -e POWER_MODE={POWER_MODE_LABEL} "
                "-e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp -e ROS_DOMAIN_ID=0 "
                f"{image} bash -c 'source /opt/ros/jazzy/setup.bash && "
                "source /ros2_ws/install/setup.bash && "
                "python3 -m nav_fleet.mission_runner mission2'")
        else:
            cmd = (f'{JENV} && cd {JETSON_REPO} && RUNNER_TYPE=hil_jetson '
                   f'POWER_MODE={POWER_MODE_LABEL} python3 -m nav_fleet.mission_runner mission2')
```

Replace with:

```python
        if os.environ.get('HIL_CONTAINER') == '1':
            cmd = (
                f"docker exec {HIL_CONTAINER_NAME} bash -c "
                "'source /opt/ros/jazzy/setup.bash && "
                "source /ros2_ws/install/setup.bash && "
                "python3 -m nav_fleet.mission_runner mission2'")
        else:
            cmd = (f'{JENV} && cd {JETSON_REPO} && RUNNER_TYPE=hil_jetson '
                   f'POWER_MODE={POWER_MODE_LABEL} python3 -m nav_fleet.mission_runner mission2')
```

Also update the comment block directly above `_ssh_mission2` (the "Two bind mounts,
two different writers" paragraph, around line 256–270) — the mounts now apply once at
`_start_container()` time rather than per call. Change its opening line from:

```python
        # HIL_CONTAINER=1 runs the mission inside the stage-3 arm64 GHCR image (consuming the
        # arm64->HIL pipeline edge), mirroring scripts/hil_stage.sh. Bare-metal (HIL_CONTAINER
        # unset) is the default — used for local proofs.
```

to:

```python
        # HIL_CONTAINER=1 execs into the long-lived container started by
        # _start_container() (S17 Piece 8) — the stage-3 arm64 GHCR image, mirroring
        # scripts/hil_stage.sh. Bare-metal (HIL_CONTAINER unset) is the default — used
        # for local proofs.
```

(Leave the rest of that comment block — the bind-mount rationale — as-is; it's still
accurate, just now describing flags on `_start_container`'s `docker run -d` instead of
this method's own `docker run --rm`.)

- [ ] **Step 4: Run it to verify it passes**

```bash
python -m pytest tests/test_mission2_day.py -v -k test_ssh_mission2_container_mode_uses_docker_exec
```

Expected: PASS.

- [ ] **Step 5: Wire `executor.close()` into `main()`'s cleanup**

Find in `main()` (around line 708–734):

```python
    proc = None
    runner = None
    rclpy = None
    ok = False
    try:
        if not no_launch:
            proc = launch_stack(args.log)
        if hil:
            executor = JetsonExecutor(os.environ.get('JETSON_IP'), STATE_DIR)
        else:
            import rclpy as _rclpy
            rclpy = _rclpy
            from nav_fleet.mission_runner import MissionRunner
            rclpy.init()
            runner = MissionRunner()
            executor = InProcessExecutor(runner)
        try:
            ok = run_day(executor, ball_ops, ball_xy, args.hold_s)
        finally:
            if runner is not None:
                runner.nav.destroy_node()
                runner.destroy_node()
            if rclpy is not None:
                rclpy.try_shutdown()
    finally:
        if not no_launch:
            shutdown_stack(proc)
```

Replace with:

```python
    proc = None
    runner = None
    rclpy = None
    executor = None
    ok = False
    try:
        if not no_launch:
            proc = launch_stack(args.log)
        if hil:
            executor = JetsonExecutor(os.environ.get('JETSON_IP'), STATE_DIR)
        else:
            import rclpy as _rclpy
            rclpy = _rclpy
            from nav_fleet.mission_runner import MissionRunner
            rclpy.init()
            runner = MissionRunner()
            executor = InProcessExecutor(runner)
        try:
            ok = run_day(executor, ball_ops, ball_xy, args.hold_s)
        finally:
            if runner is not None:
                runner.nav.destroy_node()
                runner.destroy_node()
            if rclpy is not None:
                rclpy.try_shutdown()
            if executor is not None:
                executor.close()
    finally:
        if not no_launch:
            shutdown_stack(proc)
```

There's no practical unit test for this wiring (it's inside `main()`, which
orchestrates live stack launch) — Task 4's live HIL day is what actually proves
`close()` gets called (the container will no longer be present on the Jetson after the
day ends; `docker ps -a` should show it gone).

- [ ] **Step 6: Run the full test suite (Tier 1, matching CLAUDE.md's dev loop)**

```bash
cd /home/mike/autonomous-fleet-testbed
colcon build --symlink-install
source install/setup.bash
python -m pytest tests/ -v \
  --ignore=tests/test_ros2_contracts.py \
  --ignore=tests/test_navigation.py \
  --ignore=tests/test_mission_run.py \
  --ignore=tests/test_mission2.py
```

Expected: all green (239+ tests, matching Piece 8's baseline of 239/239 plus the 4 new
tests from this plan).

- [ ] **Step 7: Commit**

```bash
git add tools/mission2_day.py tests/test_mission2_day.py
git commit -m "fix(mission2_day): docker exec into one long-lived HIL container per day

Replaces a fresh 'docker run --rm' per Mission 2 scenario (3x/day) with one
container started at day begin and torn down at day end — removes ~15.6-16.1s
of pure container start/teardown cost per scenario transition (root-caused
in S17 Piece 8, 2026-07-23 live timed HIL day)."
```

---

### Task 3: Live GUI-watched HIL verification (container mode)

This is a hands-on verification step, not an automated test — it needs the real
Jetson, a freshly built arm64 image containing this fix, and Mike watching the Gazebo
GUI (per this project's standing "GUI Run Observation" practice: ask what Mike
observed before declaring anything green).

- [ ] **Step 1: Build and push the arm64 image with this fix**

CI normally builds this image (`stage-3-arm64`), but CI only triggers on a push to
`main` or a PR targeting it — this branch isn't pushed yet. Build and push it manually
so the Jetson can pull a tag that has today's fix in it:

```bash
cd /home/mike/autonomous-fleet-testbed
docker buildx build --platform linux/arm64 \
  --tag ghcr.io/sdfinn/autonomous-fleet-testbed:hil-container-fix-dev \
  --push .
```

- [ ] **Step 2: Sync the branch to the Jetson and pull the image**

```bash
scripts/hil_stage.sh sync   # only works with pushed shas per CLAUDE.md gotcha —
                             # push the branch to origin first if this fails:
                             # git push -u origin fix/hil-container-lifecycle
ssh mike@jetson.local "gh auth token | docker login ghcr.io -u sdfinn --password-stdin && \
  docker pull ghcr.io/sdfinn/autonomous-fleet-testbed:hil-container-fix-dev"
```

- [ ] **Step 3: Bring the stack up and watch it live**

Follow the documented GUI-watched sequence from CLAUDE.md's Gotchas:

```bash
scripts/hil_stage.sh run
```

In a separate terminal, view it with the scrubbed-env recipe (snap/glibc GUI-crash
workaround):

```bash
env -i HOME=$HOME USER=$USER TERM=xterm PATH=/usr/local/bin:/usr/bin:/bin DISPLAY=:0 \
  XAUTHORITY=${XAUTHORITY:-/run/user/1000/gdm/Xauthority} \
  bash -c 'source /opt/ros/jazzy/setup.bash && gz sim -g'
```

- [ ] **Step 4: Run the day in container mode with the new image, hold at the end**

```bash
DAY_HOLD_S=10 HIL_CONTAINER=1 \
  HIL_IMAGE=ghcr.io/sdfinn/autonomous-fleet-testbed:hil-container-fix-dev \
  scripts/hil_stage.sh day
```

- [ ] **Step 5: Compare timing against the Piece 8 baseline**

Pull the `[timing]` lines from this run's log (`STATE_DIR/mission2_day.log`, default
`/tmp/hil_stage/mission2_day.log`) and diff the per-transition gap against Piece 8's
recorded baseline (~15.6–16.1s/transition, ~31s total for the 2 transitions/day):

```bash
grep '\[timing\]' /tmp/hil_stage/mission2_day.log
```

Compute `ssh returned` timestamp of one scenario → `ssh dispatch` timestamp of the
next scenario, for both transitions (no_ball→yellow, yellow→red). Expect this gap to
have dropped from ~15–16s to near-zero (the workstation bookkeeping ~1.6s plus a
`docker exec` startup, which is far cheaper than a fresh `docker run`).

- [ ] **Step 6: Confirm the container was actually reused, not recreated**

```bash
ssh mike@jetson.local "docker ps -a --filter name=hil_mission2"
```

During the run, this should show exactly ONE `hil_mission2` container for all 3
scenarios (not 3 short-lived ones). After the day completes, it should be gone
(`close()` removed it).

- [ ] **Step 7: Ask Mike what he observed**

Per this project's standing practice: before declaring this fix verified, ask Mike
directly what he saw on the GUI-watched run (any stall, any visual glitch, timing that
matched or didn't match Step 5's numbers) — his observation is the ground-truth
signal, not just the log diff.

---

### Task 4: Push, open/update PR, check CI reporting

- [ ] **Step 1: Push the branch**

```bash
git push -u origin fix/hil-container-lifecycle
```

- [ ] **Step 2: Open a PR (draft) so CI actually runs**

Per CLAUDE.md's gotcha ("CI triggers ONLY on push-to-main and PRs targeting main" —
pushing a feature branch alone runs nothing):

```bash
gh pr create --draft --title "fix(mission2_day): long-lived HIL container per day" --body "$(cat <<'EOF'
## Summary
- Root cause (S17 Piece 8, 2026-07-23): container-mode HIL days paid ~15.6-16.1s of
  pure Docker container start/teardown cost per Mission 2 scenario transition (fresh
  `docker run --rm` x3/day).
- Fix: JetsonExecutor now starts ONE long-lived container per day; each scenario
  `docker exec`s into it instead. Torn down once at day end via a new `close()`.

## Test plan
- [x] New unit tests (start/stop/close lifecycle, docker exec rewiring) — see
      tests/test_mission2_day.py
- [x] Full local Tier-1 suite green
- [x] Live GUI-watched HIL day (container mode) — timing confirmed to drop from
      ~15-16s/transition to near-zero; Mike observed the run directly

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 3: Watch CI and report the current state of CI reporting**

```bash
gh pr checks --watch
```

Once `stage-4-hil` and `stage-5-reports-hw`/`stage-5-reports-sim` finish, check the
run's actual reporting output (the two things Piece 8 left as still-open, unrelated
findings — DO NOT fix them here, just report current state):

```bash
gh run view --job=<stage-5-reports-hw job id> --log | grep -i "GITHUB_STEP_SUMMARY\|Report\|DRIFT"
gh run list --branch fix/hil-container-lifecycle --limit 1
```

Summarize back to Mike: whether the summary still lacks a PDF-artifact link, whether
the HIL PDF is still photo-less, and — the actual point of this task — whether the
`hil_jetson` telemetry rows for this run show the improved per-transition timing.

---

### Session Complete When
- [ ] All 4 new unit tests pass locally, plus the full Tier-1 suite
- [ ] A live, Mike-observed GUI HIL day confirms the ~15–16s/transition delay is gone
- [ ] Branch pushed, PR opened, CI green (or failures triaged)
- [ ] Mike has been told the current state of the two open CI-reporting gaps
      (PDF-link-in-summary, photo-less HIL PDF) — informational only, not fixed in
      this plan
