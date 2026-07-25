# Mission 2: One Continuous Run, No "Scenario" Concept — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate the Jetson inter-scenario gap (~17.6s, Release1Todo.md Piece 9) at
its root by removing the "3 external invocations" structure entirely — Mission 2's
day becomes ONE continuous `run_mission('mission2')`-driven execution (3 repetitions
internally, whether on x86 or Jetson), not 3 separately-invoked scenario runs. Mike's
explicit design intent (2026-07-24): don't build "legs" out as a deep, rigid
abstraction — this is Mission-2-specific glue on top of an otherwise-unchanged mission
model, since future missions (more autonomy, random objects, multiple robots) may not
fit a fixed "N legs" shape at all and shouldn't be constrained by this.

**Architecture:** `nav_fleet/mission_runner.py` gains a one-shot "day" entry point that
loops calling `run_mission('mission2')` 3 times **within one process** (no
persistent-service, no DDS RPC — that earlier plan is scrapped, see the deleted
`2026-07-24-hil-persistent-mission-runner.md`), collecting each repetition's
checklist/new-photos/reaction-events (with wall-clock timestamps) into one combined
JSON result printed at the end. `tools/mission2_day.py` calls this ONCE per day
(Jetson: one SSH call; x86: one in-process loop, same shape) instead of 3 times, and
the ball-placement/ground-truth machinery — which currently assumes 3 separate call
boundaries to hang timing off of — is reworked into ONE continuous background thread
that logs timestamped ground-truth samples for the whole call's duration and performs
its 2 ball actions (place yellow, swap to red) off live retreat detection, exactly as
today, just sequenced within one thread instead of split across 3. Judging
(`judge_no_ball`/`judge_yellow`/`judge_red`) and per-leg telemetry logging
(`log_variant_row` ×3) are UNCHANGED — they still run 3 times, they just now run in a
loop after the single call returns, fed from the returned bundles + nearest-timestamp
lookups into the continuous ground-truth log instead of point-in-time polls taken
between separate calls.

**Tech Stack:** Python 3, `rclpy` (unchanged — no new ROS interfaces), pytest.

## Global Constraints

- Do NOT add a generic "legs" data structure to `missions.py`'s `MISSIONS`/
  `MissionStep` model. Mission 2's 3-repetition behavior lives entirely in
  `mission_runner.py`'s new day-entry-point and `mission2_day.py` — the shared mission
  model (used by mission1 and future missions) is untouched.
- `judge_no_ball`/`judge_yellow`/`judge_red`/`log_variant_row`/`home_pair_similarity`
  in `tools/mission2_harness.py` keep their exact current signatures and logic — only
  what feeds them (live polls → continuous-log lookups) changes.
- Unify BOTH executors (`InProcessExecutor` and `JetsonExecutor`) around the same new
  `run_day()` interface — this is not a Jetson-only fix. `run_no_ball`/`run_yellow`/
  `run_red` (today's scenario-named functions) are deleted, not kept alongside the new
  path.
- Ball-placement/swap timing must not change: yellow still placed during no_ball's own
  retreat, red still swapped in during yellow's own retreat, both still
  workstation-side and Gazebo-direct (never through the Jetson/SSH/service path).
- Clock correlation between the Jetson's embedded timestamps and the workstation's own
  continuous ground-truth log relies on the two machines' clocks being close enough
  (same LAN; already relied on implicitly this session correlating Jetson `nav_runner`
  timestamps against workstation `mission2_day` timestamps without adjustment) —
  events are separated by many seconds, so this only needs sub-second accuracy, not
  NTP-grade precision.
- Every behavior change here needs a live HIL verification (GUI-watched, both
  no-Docker Jetson AND x86) confirming Mission 2 still produces the same 3 PASS
  verdicts with correct photos/reactions, AND that the inter-scenario gap is gone.

---

### Task 1: Jetson/x86-shared day-entry-point in `mission_runner.py`

**Files:**
- Modify: `src/nav_fleet/nav_fleet/mission_runner.py`

**Interfaces:**
- Produces: `MissionRunner.run_mission2_day()` → returns a list of 3 dicts, each:
  `{'t_start': float, 't_end': float, 'ok': bool, 'checklist': [[label, verdict], ...],
  'photos': [str, ...], 'reaction_events': [{'color', 'reaction', 'truth_xy', 't'}, ...]}`.
  `truth_xy` is always `None` here (no Gazebo on the Jetson) — the workstation fills it
  in post-hoc from its own continuous ground-truth log, keyed by `t`.

- [ ] **Step 1: Add `MissionRunner.run_mission2_day()`**

Add after `run_mission` (the method already reset by TODAY's `InProcessExecutor` per
call — this consolidates that reset/collect logic into the runner itself, used by
BOTH the new Jetson entry point below AND the rewritten `InProcessExecutor` in Task 3):

```python
    def run_mission2_day(self, legs=3):
        """S17 Piece 9 (Mike, 2026-07-24): run mission2 `legs` times in one process —
        replaces 3 externally-invoked processes/SSH calls with one continuous
        execution. Each repetition's own checklist/new-photos/reaction-events are
        collected separately (same reset-between-calls pattern InProcessExecutor
        already used) so the day's 3 separately-judged/logged rows are unaffected —
        only the execution boundary moves, not the judging granularity. Deliberately
        NOT a generic 'legs' concept in the mission model (missions.py is untouched);
        this is Mission-2-specific day orchestration living where it always has."""
        import time
        results = []
        for _ in range(legs):
            self.reaction_events.clear()
            photos_before = len(self.photo_paths)
            t_start = time.time()
            ok = self.run_mission('mission2')
            t_end = time.time()
            events = [{'color': e['color'], 'reaction': e['reaction'], 't': t_end,
                       'truth_xy': None} for e in self.reaction_events]
            results.append({
                't_start': t_start, 't_end': t_end, 'ok': ok,
                'checklist': [[label, verdict] for label, verdict in self.checklist],
                'photos': self.photo_paths[photos_before:],
                'reaction_events': events,
            })
        return results
```

(Reaction event timestamp uses `t_end`, not a per-reaction instant — `_execute_reaction`
doesn't currently timestamp itself and reactions happen near the end of their leg
anyway; `t_end` is close enough for nearest-sample correlation given the multi-second
separation between legs. If Task 5's live verification shows this isn't precise
enough, tighten it by timestamping inside `_execute_reaction` instead — don't
preemptively over-engineer this.)

- [ ] **Step 2: Add the CLI entry point**

In `main()`, add a new mutually-exclusive mode (alongside the existing one-shot
`mission` positional arg):

```python
    parser.add_argument('--day', action='store_true',
                        help='S17 Piece 9: run mission2 3x in one process, print one '
                             'combined JSON result instead of exiting after one '
                             'mission — replaces mission2_day.py calling this 3x over '
                             'SSH.')
```

Branch near the top of `main()` (before the existing `bag_proc = failure_bag.start(...)`
line, mirroring the structure Task 1 of the earlier scrapped plan used for `--serve`,
but one-shot, not persistent):

```python
    if args.day:
        import json
        rclpy.init()
        runner = MissionRunner()
        runner.get_logger().info(build_env_manifest(
            git_sha=git_sha(), power_mode=os.environ.get('POWER_MODE')))
        results = runner.run_mission2_day()
        rclpy.try_shutdown()
        print('MISSION2_DAY_RESULT:' + json.dumps(results))
        raise SystemExit(0 if all(r['ok'] or True for r in results) else 1)
        # ^ exit code is informational only here — mission2_day.py judges PASS/FAIL
        # itself from ground truth, same as today; a leg's own self-report 'ok' is
        # not the verdict (see judge_* functions) — always exit 0 if the process
        # itself didn't crash, so the workstation always gets to parse the JSON.
    if args.mission is None:
        parser.error('mission is required unless --day is given')
```

The `MISSION2_DAY_RESULT:` prefix makes the JSON line trivially greppable out of
whatever else gets printed to stdout (ROS logging, checklist prints, etc.) — the
workstation parser looks for this exact prefix, not "the whole stdout is JSON."

- [ ] **Step 3: Manual smoke test on x86**

```bash
cd /home/mike/autonomous-fleet-testbed
colcon build --symlink-install && source install/setup.bash
# sim must be up (sim_launch.py) — no ball placement needed for this smoke test,
# expect 'no reaction' outcomes on all 3 legs, that's fine, this is just proving the
# loop/collection/JSON mechanics work.
python3 -m nav_fleet.mission_runner --day
```

Expected: robot drives the round trip 3 times in a row, no process restart between
them (watch it — should look visibly continuous, no pause), one
`MISSION2_DAY_RESULT:[...]` line at the end containing 3 result dicts.

- [ ] **Step 4: Commit**

```bash
git add src/nav_fleet/nav_fleet/mission_runner.py
git commit -m "feat(mission_runner): run_mission2_day() + --day CLI mode

Runs mission2 3x within one process instead of exiting after one mission
— the actual fix for the S17 Piece 9 inter-scenario gap: there is no
longer a process-restart boundary between legs to pay a cost for, on
either platform. Mission-2-specific; missions.py's shared model is
untouched per Mike's explicit steer against a generic 'legs' abstraction."
```

---

### Task 2: Continuous ground-truth logger + unified ball-management thread

**Files:**
- Modify: `tools/mission2_day.py` (`RetreatDetector` stays; replace
  `_place_during_return`/`_swap_during_return`/`_wait_for_retreat`/`_ReactionPoller`)
- Test: `tests/test_mission2_day.py`

**Interfaces:**
- Produces: `GroundTruthLog` (records `(t, xy)` samples; `nearest(t)` → `xy` or
  `None`), `run_ball_choreography(ball_ops, ball_xy, stop_evt) -> GroundTruthLog` (one
  thread-driving function, started before the single `run_day()` call, joined after).

- [ ] **Step 1: Write the failing tests for `GroundTruthLog`**

Add to `tests/test_mission2_day.py` (pure logic, no live ROS needed — matches
`RetreatDetector`'s existing pure-unit-test treatment):

```python
def test_ground_truth_log_nearest_returns_closest_sample():
    log = mission2_day_module.GroundTruthLog()
    log.record(10.0, (1.0, 2.0))
    log.record(10.5, (1.5, 2.5))
    log.record(11.0, (2.0, 3.0))
    assert log.nearest(10.4) == (1.5, 2.5)
    assert log.nearest(10.0) == (1.0, 2.0)
    assert log.nearest(100.0) == (2.0, 3.0)   # clamps to the last sample, doesn't crash


def test_ground_truth_log_nearest_empty_returns_none():
    log = mission2_day_module.GroundTruthLog()
    assert log.nearest(10.0) is None


def test_ground_truth_log_closest_approach_between_finds_local_minimum():
    """For reaction-point recovery: the closest approach to a KNOWN target xy,
    restricted to a time window (one leg's own approach, not a different leg's)."""
    log = mission2_day_module.GroundTruthLog()
    log.record(0.0, (0.0, 0.0))
    log.record(1.0, (0.0, 3.0))    # closest to (0, 4) in this window
    log.record(2.0, (0.0, 1.0))
    log.record(10.0, (0.0, 3.9))   # a LATER, closer sample outside the window — must
                                    # not be picked for a query scoped to t in [0, 2]
    assert log.closest_approach_to((0.0, 4.0), t_start=0.0, t_end=2.0) == (0.0, 3.0)
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/test_mission2_day.py -v -k ground_truth_log
```

Expected: FAIL (`AttributeError`/`NameError` — `GroundTruthLog` doesn't exist yet).

- [ ] **Step 3: Implement `GroundTruthLog`**

Add to `tools/mission2_day.py`, near `RetreatDetector`:

```python
class GroundTruthLog:
    """Continuous timestamped ground-truth samples for the WHOLE day's single
    blocking executor call (S17 Piece 9) — replaces the old per-call point-in-time
    get_ground_truth_xy() polls (truth_start/truth_a/truth_b/_ReactionPoller), all of
    which assumed a call boundary to poll AROUND. One thread now logs continuously;
    judging looks up 'ground truth near timestamp T' post-hoc against this log,
    using the leg-boundary/reaction timestamps mission_runner.py's --day mode already
    embeds in its JSON result."""

    def __init__(self):
        self._samples = []   # list of (t, (x, y)), append-only, time-ordered

    def record(self, t, xy):
        self._samples.append((t, xy))

    def nearest(self, t):
        if not self._samples:
            return None
        best = min(self._samples, key=lambda s: abs(s[0] - t))
        return best[1]

    def closest_approach_to(self, target_xy, t_start, t_end):
        """Minimum-distance sample to target_xy, restricted to [t_start, t_end] —
        the reaction-point recovery a HIL _ReactionPoller used to do live, now done
        post-hoc against one leg's own time window so a later leg's approach to the
        same fixed marker position can't be mistaken for this leg's."""
        window = [(t, xy) for t, xy in self._samples if t_start <= t <= t_end]
        if not window:
            return None
        best = min(window, key=lambda s: math.hypot(
            s[1][0] - target_xy[0], s[1][1] - target_xy[1]))
        return best[1]
```

(Needs `import math` at the top of `mission2_day.py` if not already present — check
before adding.)

- [ ] **Step 4: Run to verify pass**

```bash
python -m pytest tests/test_mission2_day.py -v -k ground_truth_log
```

- [ ] **Step 5: Replace the ball-management threads with one sequential function**

Find `_place_during_return`/`_swap_during_return`/`_wait_for_retreat` (around lines
558-611 as of this writing). Replace all three with:

```python
def run_ball_choreography(ball_ops, ball_xy, stop_evt, poll_s=0.3):
    """S17 Piece 9: ONE thread for the whole day (was 2 separate per-call threads).
    Sequences the SAME 2 actions today's design already does — place yellow behind
    the robot during leg 1's retreat, swap yellow->red during leg 2's retreat — but
    now driven by ONE continuous ground-truth poll loop spanning the single blocking
    run_day() call, since there's no longer a per-leg call boundary to scope a
    separate thread to. Concurrent-only (gz mode) — operator mode still does its
    explicit post-run prompts, unchanged, in the caller.
    Returns the GroundTruthLog recorded along the way (reused for judging - Task 3)."""
    log = GroundTruthLog()
    holder = {'placed_name': None, 'red_name': None}

    def _wait_for_retreat():
        detector = RetreatDetector()
        while not stop_evt.is_set():
            xy = get_ground_truth_xy()
            t = time.time()
            if xy is not None:
                log.record(t, xy)
            if detector.update(xy):
                return True
            time.sleep(poll_s)
        return False

    if _wait_for_retreat():
        log.info('retreat detected — placing yellow behind the returning robot')
    holder['placed_name'] = ball_ops.place('yellow', *ball_xy)

    if _wait_for_retreat():
        log.info('retreat detected — swapping yellow -> red behind the robot')
    ball_ops.remove(holder['placed_name'])
    ball_ops.settle()
    holder['red_name'] = ball_ops.place('red', *ball_xy)

    # Keep logging (no more ball actions left) until the caller signals the day is
    # done, so leg 3's own closest-approach/truth samples are still captured.
    while not stop_evt.is_set():
        xy = get_ground_truth_xy()
        if xy is not None:
            log.record(time.time(), xy)
        time.sleep(poll_s)
    return log
```

Note this reuses the module `log` (the fleet logger) for the two info lines — same as
today's originals; don't confuse it with the new `GroundTruthLog` class's `log`
variable name inside the function (rename the local if this reads ambiguously when
writing it for real — a real naming collision to watch for, not just a style nit).

- [ ] **Step 6: Delete `_ReactionPoller`**

No longer needed — `GroundTruthLog.closest_approach_to()` replaces its live-tracking
role, scoped per-leg via timestamps instead of per-call via thread start/stop.

- [ ] **Step 7: Commit**

```bash
git add tools/mission2_day.py tests/test_mission2_day.py
git commit -m "feat(mission2_day): GroundTruthLog + one continuous ball-choreography
thread, replacing per-call _ReactionPoller/_place_during_return/_swap_during_return"
```

---

### Task 3: Unify `MissionExecutor` around `run_day()`, delete the scenario functions

**Files:**
- Modify: `tools/mission2_day.py` (`MissionExecutor`, `InProcessExecutor`,
  `JetsonExecutor`, delete `run_no_ball`/`run_yellow`/`run_red`, rewrite `run_day`,
  `main()`)
- Test: `tests/test_mission2_day.py`

**Interfaces:**
- Produces: `MissionExecutor.run_day() -> list[dict]` (same 3-dict shape Task 1's
  `run_mission2_day()` returns — `InProcessExecutor` and `JetsonExecutor` both
  implement this, replacing the old single-scenario `run(ball_xy, color)`).

- [ ] **Step 1: `InProcessExecutor.run_day()`**

Replace `InProcessExecutor`'s `run`/`reset` methods:

```python
class InProcessExecutor(MissionExecutor):
    def __init__(self, runner):
        self.runner = runner

    def run_day(self):
        return self.runner.run_mission2_day()
```

- [ ] **Step 2: `JetsonExecutor.run_day()`**

Replace `_ssh_mission2`/`run` with one method that invokes `--day` once:

```python
    def run_day(self):
        cmd_suffix = 'python3 -m nav_fleet.mission_runner --day'
        if self.image is not None:
            cmd = (
                "docker run --rm --name hil_mission2 --network host --ipc host "
                "-v $HOME/autonomous-fleet-testbed/reports:/ros2_ws/reports "
                "-v $HOME/fleet-ci-data:/root/fleet-ci-data "
                f"-e RUNNER_TYPE=hil_jetson -e POWER_MODE={POWER_MODE_LABEL} "
                "-e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp -e ROS_DOMAIN_ID=0 "
                f"{self.image} bash -c 'source /opt/ros/jazzy/setup.bash && "
                f"source /ros2_ws/install/setup.bash && {cmd_suffix}'")
        else:
            cmd = f'{JENV} && cd {JETSON_REPO} && RUNNER_TYPE=hil_jetson POWER_MODE={POWER_MODE_LABEL} {cmd_suffix}'
        out_path = os.path.join(self.state_dir, 'day.out')
        dispatch_time = time.time()
        log.info(f'[timing] ssh dispatch for the day at {dispatch_time:.3f}')
        proc = subprocess.run(
            ['timeout', '600', 'ssh', '-o', 'BatchMode=yes',
             f'{JETSON_USER}@{self.ip}', cmd],
            capture_output=True, text=True)
        log.info(f'[timing] ssh returned for the day at {time.time():.3f} '
                 f'(+{time.time() - dispatch_time:.3f}s total)')
        log_text = proc.stdout + proc.stderr
        pathlib.Path(out_path).write_text(log_text)
        self._log_startup_crash_if_needed(log_text, proc.returncode)
        results = self._parse_day_result(log_text)
        for leg in results:
            leg['photos'] = self._pull_photos_from_paths(leg['photos'])
        self._pull_failure_bags(log_text)
        return results

    def _parse_day_result(self, log_text):
        import json
        for line in log_text.splitlines():
            if line.startswith('MISSION2_DAY_RESULT:'):
                return json.loads(line[len('MISSION2_DAY_RESULT:'):])
        raise RuntimeError('no MISSION2_DAY_RESULT line found in Jetson output — '
                            'process likely crashed before printing it; see day.out')
```

(NOTE: `--network host` means the container-mode `docker run --rm` here doesn't need
Task 1/2's long-lived-container machinery from the EARLIER, now-scrapped Piece 8
follow-on plan — this is a single one-shot call for the WHOLE day now, not
per-scenario, so the original `docker run --rm` per-scenario cost this session
started by fixing no longer applies at all: there is only ONE `docker run` for the
whole day either way now. Double check this reasoning holds before writing the code —
if it doesn't, keep the persistent-container mechanism from commits
`ed2bf76`/`53a1376` and `docker exec` into it instead of `docker run --rm` here, for
consistency with that already-shipped, already-tested fix.)

`_pull_photos_from_paths`/`_pull_failure_bags` reuse Task 3 Step 5 of the (deleted)
persistent-process plan's renaming — implement that renaming here instead if it
wasn't already done: split `_pull_photos`'s regex-scan into "take an explicit path
list" (the new call site here has `leg['photos']` as a ready-made list from the JSON,
no regex needed).

- [ ] **Step 3: Delete `run_no_ball`/`run_yellow`/`run_red`, rewrite `run_day`**

Replace all three scenario-specific functions plus the old `run_day` with:

```python
def _judge_and_log_leg(name, leg, ball_xy, gt_log, ref_photos_from_prev=None):
    """One leg's judging + telemetry row — same judge_*/log_variant_row calls as
    today's run_no_ball/run_yellow/run_red, just called from a loop over one day's
    3 returned bundles instead of from 3 separately-invoked functions."""
    events = leg['reaction_events']
    for e in events:
        if e['truth_xy'] is None:
            e['truth_xy'] = gt_log.closest_approach_to(ball_xy, leg['t_start'], leg['t_end'])
    final = gt_log.nearest(leg['t_end'])
    sim = home_pair_similarity(
        [p for p in leg['photos'] if 'mission2_home_ref' in p],
        [p for p in leg['photos'] if 'mission2_home_arrival' in p])
    truth_start = gt_log.nearest(leg['t_start'])

    if name == 'no_ball':
        fails = judge_no_ball(events, final,
                              [p for p in leg['photos'] if 'mission2_marker' in p], sim)
    elif name == 'yellow':
        fails = judge_yellow(ball_xy, events,
                             [p for p in leg['photos'] if 'reaction_yellow' in p],
                             truth_start, final, sim)
    else:  # red
        truth_a = gt_log.nearest(leg['t_end'])
        truth_b = gt_log.nearest(leg['t_end'] + 2.0)
        fails = judge_red(ball_xy, events,
                          [p for p in leg['photos'] if 'reaction_red' in p],
                          truth_start, truth_a, truth_b,
                          home_arrival_photos=[p for p in leg['photos']
                                               if 'mission2_home_arrival' in p])
    ok = not fails
    log_variant_row(name, None, ok=ok, runner=None, home_photo_similarity=sim)
    log.info(f'  {name}: home_photo_similarity = {sim}')
    _print_checklist([tuple(row) for row in leg['checklist']],
                     f"{name} {'PASS' if ok else 'FAIL'}", fails)
    return ok


def run_day(executor, ball_ops, ball_xy, hold_s):
    """S17 Piece 9: ONE continuous mission execution, 3 separately-judged/logged
    legs (Mike's explicit design, 2026-07-24) — no scenario-named functions, no
    per-call SSH/process boundary. Ball choreography runs on its own thread for the
    WHOLE call; judging happens in a loop after the single call returns."""
    log.info('\n=== Mission 2 day: one continuous run, 3 legs ===')
    stop_evt = threading.Event()
    gt_log_holder = {}
    choreography_thread = None
    if ball_ops.concurrent:
        def _run():
            gt_log_holder['log'] = run_ball_choreography(ball_ops, ball_xy, stop_evt)
        choreography_thread = threading.Thread(target=_run, daemon=True)
        choreography_thread.start()
    try:
        legs = executor.run_day()
    finally:
        stop_evt.set()
        if choreography_thread is not None:
            choreography_thread.join(timeout=30)
    gt_log = gt_log_holder.get('log', GroundTruthLog())

    names = hil_variant_names()   # ['no_ball', 'yellow', 'red'] — declared order, unchanged
    results = {}
    for name, leg in zip(names, legs):
        results[name] = _judge_and_log_leg(name, leg, ball_xy, gt_log)
    log.info('\n=== SUMMARY ===')
    for name in names:
        log.info(f'  {name:8s}: {"PASS" if results[name] else "FAIL"}')
    if hold_s > 0:
        log.info(f'  holding {hold_s:.0f}s for the observer')
        time.sleep(hold_s)
    return all(results.values())
```

(`operator` ball-ops mode, `ball_ops.concurrent == False`: today's `OperatorBallOps`
path did explicit post-run prompts inside `run_yellow`'s `if swap_thread is None`
branch. With the scenario functions gone, that prompt sequence needs a new home —
add it as an `else` branch in `run_day` above, prompting for yellow placement before
`executor.run_day()` is called and red swap after, roughly matching today's operator
UX. Flag this explicitly in review — it's a real behavior path (robot-day dry run)
that must not silently break; write it out fully rather than leaving it as a TODO
when actually implementing this step.)

- [ ] **Step 4: Update `main()`**

Remove the `run_no_ball`/`run_yellow`/`run_red` imports/calls — `run_day` is now the
only entry point (its signature is unchanged from today's `run_day(executor,
ball_ops, ball_xy, hold_s)`, so `main()`'s own call site doesn't need to change).

- [ ] **Step 5: Update tests**

Rewrite `tests/test_mission2_day.py`'s executor tests around the new `run_day()`
interface (was `run(ball_xy, color)`) and the new `_parse_day_result`/photo-path-list
shape (was regex-on-log-text). Read the existing tests first, preserve their intent
(bare-metal path shape, container path shape, photo path translation, failure-bag
scp, startup-crash synthesis) against the new call shapes.

- [ ] **Step 6: Full local Tier-1 suite green, commit**

```bash
colcon build --symlink-install
source install/setup.bash
python -m pytest tests/ -v \
  --ignore=tests/test_ros2_contracts.py \
  --ignore=tests/test_navigation.py \
  --ignore=tests/test_mission_run.py \
  --ignore=tests/test_mission2.py
```

```bash
git add tools/mission2_day.py tests/test_mission2_day.py
git commit -m "refactor(mission2_day): one continuous run_day(), delete
run_no_ball/run_yellow/run_red — no more scenario-named functions"
```

---

### Task 4: Live verification — x86 first (fast iteration), then Jetson (GUI-watched)

- [ ] **Step 1: x86 functional pass** — `python -m tools.mission2_day` (default
      in-process), confirm 3 PASS, photos/reactions correct, no regression vs. today's
      behavior. Fast to iterate on; find bugs here before touching the Jetson.

- [ ] **Step 2: x86 GUI-watched pass** — same run with the GUI open, confirm visually
      continuous (no artificial pauses introduced by this refactor).

- [ ] **Step 3: Full clean teardown + fresh bare-metal Jetson HIL stack**, same
      procedure used earlier this session.

- [ ] **Step 4: Jetson GUI-watched day run**, `--executor jetson --no-launch`.
      Confirm: 3 PASS, correct photos/reactions, AND — the actual point — no
      multi-second stationary gap between legs. Ask Mike what he observed before
      declaring this fixed, per this project's standing practice.

- [ ] **Step 5: Container-mode pass** (if Task 3 Step 2's `docker run --rm`-per-day
      reasoning holds) — confirm the same result in `HIL_CONTAINER=1` mode.

- [ ] **Step 6: Measure and record the actual before/after inter-scenario numbers**,
      same method as Piece 9's own measurement, for the docs update in Task 5.

---

### Task 5: Documentation

- [ ] **Step 1: Update Release1Todo.md Piece 9** — mark the architecture-fix open item
      done, with real before/after numbers from Task 4, and a short note on the final
      design (one continuous run, no scenario functions, no legs abstraction in
      `missions.py`) superseding the persistent-process/DDS approach that was
      originally planned then scrapped mid-session.
- [ ] **Step 2: Update CLAUDE.md's `mission2_day.py`/Mission 2 description** to match
      the new architecture — remove references to `run_no_ball`/`run_yellow`/
      `run_red`/`_ssh_mission2`/`_ReactionPoller` as current; describe `run_day()`,
      `run_mission2_day()`, `GroundTruthLog`, `run_ball_choreography` instead.
- [ ] **Step 3: Commit**

```bash
git add Release1Todo.md CLAUDE.md
git commit -m "docs(s17): Piece 9 — one-continuous-run architecture landed and verified"
```

---

### Session Complete When
- [ ] `mission_runner.py --day` works standalone, 3 legs in one process (Task 1)
- [ ] `GroundTruthLog`/`run_ball_choreography` replace the per-call ball-management
      threads and `_ReactionPoller`, unit tests green (Task 2)
- [ ] Both executors implement `run_day()`, scenario-named functions deleted, full
      local suite green (Task 3)
- [ ] Live-verified on x86 AND bare-metal Jetson (GUI-watched, Mike's confirmation)
      AND container mode, with real measured numbers showing the inter-scenario gap
      is gone (Task 4)
- [ ] Findings written into Release1Todo.md/CLAUDE.md (Task 5)
