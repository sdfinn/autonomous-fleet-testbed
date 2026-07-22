# Copyright 2026 Mike
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Mission 2 "rehearse the real day" orchestrator (Task 13 §4).

THE single day-sequence owner — GUI demo, CI stage-4-hil, and the future robot day all run
THIS file, in THIS order:

  1. no_ball  — no ball; the mission self-returns home (Option B verified round trip).
  2. yellow   — place the yellow ball; the robot stops 0.8 m short, photographs it, and
                self-returns home. DURING its return leg the yellow ball is removed
                (>=3 s ghost settle) and the RED ball spawned at the same spot, behind the
                now-retreating robot (reactions are outbound-only, so red won't fire during
                the retreat).
  3. red      — the robot stops 1.3 m short, photographs, and STAYS; the ball STAYS; hold
                a few seconds so an observer unambiguously sees "done"; then clean shutdown.

Two axes of pluggability keep the SAME sequence usable across sim, CI/HIL, and the robot:

* BallOps — WHO places the ball: Gazebo spawn/remove (sim) or operator prompts (robot day).
* MissionExecutor (Task 13d) — WHERE the mission runs: in-process on the workstation (sim),
  or on the Jetson over SSH (HIL). Ball ops + ground-truth judging ALWAYS stay workstation-
  side (Gazebo lives on the workstation in both modes); only the mission executor moves.

Run from the repo root against a freshly-built workspace:

    python -m tools.mission2_day                  # sim, headless judged self-test (CI-style)
    python -m tools.mission2_day --hold-s 10       # sim GUI-watch rehearsal (separate gz -g)
    python -m tools.mission2_day --ball-ops operator   # robot-day dry run (prompts, no gz)
    python -m tools.mission2_day --executor jetson --no-launch   # HIL: mission on the Jetson
                                                   # (stack brought up by scripts/hil_stage.sh)

The GUI-watched run (Mike observing) is intentionally NOT executed by CI/self-tests — this
tool just makes it a single command away.
"""
import argparse
import os
import pathlib
import re
import signal
import subprocess
import threading
import time

from nav_fleet.ground_truth import get_ground_truth_xy
from nav_fleet.missions import MISSIONS
from tools.log_setup import build_env_manifest, configure, get_logger, git_sha
from tools.mission2_harness import (BALL_AT_SPHERE_XY, BALL_REMOVAL_SETTLE_S,
                                    home_pair_similarity, judge_no_ball, judge_red,
                                    judge_yellow, log_variant_row, parse_reaction_events,
                                    remove_ball, spawn_ball)
from tools.telemetry_logger import PHOTO_DIR as _PHOTO_DIR, log_run

log = get_logger('mission2_day')

REPO_DIR = pathlib.Path(__file__).resolve().parent.parent
PHOTO_DIR = pathlib.Path(_PHOTO_DIR)  # persistent across jobs (Piece 4 final-review fix) — was
# REPO_DIR-relative, which broke across job checkouts on the same self-hosted runner; now the
# same sibling-of-DB_PATH location tools/telemetry_logger.py and generate_test_report.py use.
FAILURE_BAG_DIR = REPO_DIR / 'reports' / 'failure_bags'  # scp'd back from the Jetson on FAIL
LAUNCH_FILE = 'src/nav_fleet/launch/sim_launch.py'
NAV2_READY_MARK = 'Managed nodes are active'   # emitted once per lifecycle manager (x2)
STACK_READY_TIMEOUT_S = 150.0
SPAWN_APPEAR_SETTLE_S = 2.0                     # llvmpipe: new model takes ~1.5 s in-frame
RETREAT_DROP_M = 0.4                            # y-drop below peak that means "retreating"

# Jetson connection (HIL executor) — MUST stay in sync with scripts/hil_stage.sh's JENV
# (pinned cross-reference; CR-16 caught these two drifting: the MAGICK/OMP knobs existed
# only in the bash copy). Non-interactive SSH skips .bashrc, so every remote ROS command
# must source its own env. MAGICK_THREAD_LIMIT/OMP: GraphicsMagick single-threading —
# the known workaround for its ARM SIGSEGV under threading (see hil_stage.sh).
JETSON_USER = os.environ.get('JETSON_USER', 'mike')
JETSON_REPO = '~/autonomous-fleet-testbed'
JENV = ('source /opt/ros/jazzy/setup.bash && '
        'source ~/autonomous-fleet-testbed/install/setup.bash && '
        'export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp ROS_DOMAIN_ID=0 '
        'MAGICK_THREAD_LIMIT=1 OMP_NUM_THREADS=1')
STATE_DIR = os.environ.get('STATE_DIR', '/tmp/hil_stage')
POWER_MODE_LABEL = os.environ.get('POWER_MODE', '15W')

# Orphan-sweep pattern (CLAUDE.md Gotchas): every process a Gazebo+Nav2 launch spawns that
# would poison the next run's DDS domain if it lingered. Kept in sync with ci.yml stage-2
# and scripts/hil_stage.sh teardown.
_SWEEP_PATTERNS = (
    'parameter_bridge|component_container_isolated|ekf_node',
    'static_transform_publisher|robot_state_publisher',
)
_CHECKLIST_RE = re.compile(r'^\s*\[\s*(PASS|FAIL|REACTION)\s*\]\s+(.*\S)\s*$')


# ── Ball placement (WHO) ──────────────────────────────────────────────────────────────────
class BallOps:
    """Placement of the reaction ball. Two implementations: Gazebo (sim) and operator
    (the on-robot day). `concurrent` says whether a ball swap can happen WHILE the robot is
    driving (True for gz — a subprocess call; False for a human, who swaps after the robot
    is home)."""
    concurrent = False

    def place(self, color, x, y):
        raise NotImplementedError

    def remove(self, name):
        raise NotImplementedError

    def settle(self):
        """Wait out the llvmpipe ghost-model lag after a removal (>=3 s)."""
        time.sleep(BALL_REMOVAL_SETTLE_S)


class GzBallOps(BallOps):
    """Sim/HIL day: spawn/remove camera-only balls in the workstation Gazebo (reuses the
    harness). Gazebo is workstation-side in BOTH sim and HIL, so this is unchanged for HIL."""
    concurrent = True

    def place(self, color, x, y):
        name = spawn_ball(color, x, y)
        log.info(f'gz spawned {name} at ({x}, {y})')
        time.sleep(SPAWN_APPEAR_SETTLE_S)
        return name

    def remove(self, name):
        remove_ball(name)
        log.info(f'gz removed {name}')


class OperatorBallOps(BallOps):
    """Robot day: the operator's hands are the actuator. SAME procedure, different hands —
    a swap can't happen mid-drive, so the orchestrator does it after the robot is home."""
    concurrent = False

    def place(self, color, x, y):
        input(f'[day] >>> place the {color.upper()} ball beside the marker '
              f'(~{x:.1f}, {y:.1f}), then press Enter... ')
        return f'{color}_ball'

    def remove(self, name):
        input(f'[day] >>> remove the {name.split("_")[0].upper()} ball, then press Enter... ')


# ── Mission execution (WHERE) ─────────────────────────────────────────────────────────────
class ExecResult:
    """What the day judges need from ONE mission2 execution, independent of where it ran."""

    def __init__(self, reaction_events, photos, checklist, ok, nav=None):
        self.reaction_events = reaction_events    # list of {color, reaction, truth_xy}
        self.photos = photos                      # local workstation photo paths (this run)
        self.checklist = checklist                # list of (label, verdict)
        self.ok = ok                              # the mission's OWN self-report (informational)
        self.nav = nav                            # for telemetry final_x/y (in-process only)

    def tagged(self, tag):
        return [p for p in self.photos if tag in p]


class MissionExecutor:
    def run(self, ball_xy=None, color=None):
        raise NotImplementedError

    def reset(self):
        """Clear any per-run bookkeeping before the next execution."""


class InProcessExecutor(MissionExecutor):
    """Sim day: run the mission in-process on the workstation via a live MissionRunner. The
    reaction event's truth_xy is captured in-process (Gazebo is right here), so no poller."""

    def __init__(self, runner):
        self.runner = runner

    def run(self, ball_xy=None, color=None):
        before = len(self.runner.photo_paths)
        ok = self.runner.run_mission('mission2')
        return ExecResult(
            reaction_events=list(self.runner.reaction_events),
            photos=list(self.runner.photo_paths[before:]),
            checklist=list(self.runner.checklist),
            ok=ok, nav=self.runner.nav)

    def reset(self):
        self.runner.reaction_events.clear()


class JetsonExecutor(MissionExecutor):
    """HIL day: run the mission on the Jetson over SSH (bare-metal, HIL_CONTAINER unset). The
    Jetson has no Gazebo, so the reaction event's truth_xy is None in its log — a workstation
    ground-truth poller (closest approach to the ball) supplies it, exactly as the retired
    discrete react rung did. Photos are scp'd back to reports/photos/ AND STATE_DIR."""

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
        # Pre-flight (S17 Piece 2 carry-in, from the sign-off false start): a wrong tag ->
        # GHCR pull denied -> `docker run` dies in ~2s, three times, silently — looks
        # exactly like a mission failure with no clue why. Check the tag exists LOCALLY on
        # the Jetson BEFORE the day starts and fail with ONE loud line naming it instead.
        # Tag gotcha: CI's pull_request builds tag the image with the synthetic MERGE
        # commit sha (GITHUB_SHA), NOT the branch head sha — a manual run must read the
        # real tag from the CI run's env or `docker images` on the Jetson, never construct
        # one from `git rev-parse`.
        proc = subprocess.run(
            ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
             f'{JETSON_USER}@{self.ip}',
             f'docker image inspect {self.image} >/dev/null 2>&1'],
            capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(
                f'HIL_IMAGE {self.image!r} is not present locally on the Jetson — '
                f'`docker run` would fail in ~2s per mission and look like a mission '
                f'failure, not a config error. Pull it first (docker login ghcr.io + '
                f'docker pull {self.image}), or read the real tag from `docker images` '
                f'on the Jetson / the CI run env instead of constructing one from '
                f'git rev-parse.')

    def run(self, ball_xy=None, color=None):
        label = color or 'no_ball'
        poller = _ReactionPoller(ball_xy) if ball_xy is not None else None
        if poller is not None:
            poller.start()
        log_text, mrc = self._ssh_mission2(label)
        if poller is not None:
            poller.stop()
        self._log_startup_crash_if_needed(log_text, mrc)
        events = parse_reaction_events(log_text)
        if poller is not None and color is not None:
            rxy = poller.reaction_xy
            for e in events:
                if e['color'] == color and rxy is not None:
                    e['truth_xy'] = tuple(rxy)
        photos = self._pull_photos(log_text)
        self._pull_failure_bags(log_text)
        return ExecResult(events, photos, _parse_checklist(log_text), ok=(mrc == 0), nav=None)

    def _ssh_mission2(self, label):
        # HIL_CONTAINER=1 runs the mission inside the stage-3 arm64 GHCR image (consuming the
        # arm64->HIL pipeline edge), mirroring scripts/hil_stage.sh. The bind-mounted reports
        # dir puts photos on the Jetson host so the same scp path works either way. Bare-metal
        # (HIL_CONTAINER unset) is the default — used for local proofs.
        if os.environ.get('HIL_CONTAINER') == '1':
            image = self.image
            cmd = (
                "docker run --rm --name hil_mission2 --network host --ipc host "
                "-v $HOME/autonomous-fleet-testbed/reports:/ros2_ws/reports "
                f"-e RUNNER_TYPE=hil_jetson -e POWER_MODE={POWER_MODE_LABEL} "
                "-e RMW_IMPLEMENTATION=rmw_cyclonedds_cpp -e ROS_DOMAIN_ID=0 "
                f"{image} bash -c 'source /opt/ros/jazzy/setup.bash && "
                "source /ros2_ws/install/setup.bash && "
                "python3 -m nav_fleet.mission_runner mission2'")
        else:
            cmd = (f'{JENV} && cd {JETSON_REPO} && RUNNER_TYPE=hil_jetson '
                   f'POWER_MODE={POWER_MODE_LABEL} python3 -m nav_fleet.mission_runner mission2')
        out_path = os.path.join(self.state_dir, f'day_{label}.out')
        log.info(f'ssh Jetson mission2 ({label}) ...')
        proc = subprocess.run(
            ['timeout', '300', 'ssh', '-o', 'BatchMode=yes',
             f'{JETSON_USER}@{self.ip}', cmd],
            capture_output=True, text=True)
        log_text = proc.stdout + proc.stderr
        pathlib.Path(out_path).write_text(log_text)
        log.debug(log_text.rstrip())   # raw ssh output — verbose; checklist below is the summary
        return log_text, proc.returncode

    def _pull_photos(self, log_text):
        """scp every 'photo saved: <path>' from the Jetson to reports/photos/ AND STATE_DIR
        (Task 13g — photos always visible on the workstation + in the CI evidence artifact)."""
        PHOTO_DIR.mkdir(parents=True, exist_ok=True)
        pathlib.Path(self.state_dir).mkdir(parents=True, exist_ok=True)
        local = []
        for rel in re.findall(r'photo saved:\s*(\S+)', log_text):
            base = os.path.basename(rel)
            dest = PHOTO_DIR / base
            rc = subprocess.run(
                ['scp', '-o', 'BatchMode=yes',
                 f'{JETSON_USER}@{self.ip}:autonomous-fleet-testbed/{rel}', str(dest)],
                capture_output=True, text=True).returncode
            if rc == 0:
                subprocess.run(['cp', '-f', str(dest),
                                os.path.join(self.state_dir, base)], check=False)
                local.append(str(dest))
            else:
                log.warning(f'could not scp Jetson photo {rel}')
        return local

    def _pull_failure_bags(self, log_text):
        """scp -r every 'failure bag kept: <path>' from the Jetson to reports/failure_bags/
        (S17 Piece 3) — same reasoning as _pull_photos: a bag sitting only on the robot's
        disk is exactly the "trapped, never retrieved" gap this Piece exists to close."""
        FAILURE_BAG_DIR.mkdir(parents=True, exist_ok=True)
        for rel in re.findall(r'failure bag kept:\s*(\S+)', log_text):
            base = os.path.basename(rel)
            dest = FAILURE_BAG_DIR / base
            rc = subprocess.run(
                ['scp', '-r', '-o', 'BatchMode=yes',
                 f'{JETSON_USER}@{self.ip}:autonomous-fleet-testbed/{rel}', str(dest)],
                capture_output=True, text=True).returncode
            if rc != 0:
                log.warning(f'could not scp Jetson failure bag {rel}')

    def _log_startup_crash_if_needed(self, log_text, mrc):
        """S17 Piece 3 finding (2026-07-21): if mission_runner.py dies before its own
        _log_mission() call runs (e.g. an import-time crash, or anything before
        rclpy.init()), NO telemetry row is written anywhere — the attempt is invisible
        to fleet_runs.db, not merely a FAIL, even though the raw crash text IS captured
        in day_<label>.out. The process's own completion print ('Mission mission2:
        PASS/FAIL') only ever fires AFTER _log_mission() has already run — main() does
        `raise SystemExit(0 if ok else 1)` for every OTHER outcome (including a normal,
        handled FAIL), so mrc != 0 alone is not the signal; its combination with the
        completion line being ABSENT is. Synthesize the row ourselves here so the
        workstation DB (what stage-5/the dashboard actually read) has some record of
        the attempt instead of silence."""
        if mrc == 0 or 'Mission mission2:' in log_text:
            return
        log.warning('mission_runner died before logging its own telemetry row — '
                    'synthesizing a startup_crash FAIL row')
        log_run(
            scenario='mission2',
            steps=len(MISSIONS['mission2']),
            final_x=0.0, final_y=0.0,
            result='FAIL',
            step_log=[],
            robot_id=os.environ.get('ROBOT_ID', 'robot_001'),
            robot_type='jetson_ugv_pt',
            runner_type='hil_jetson',
            sim_engine='real',
            power_mode=POWER_MODE_LABEL,
            failure_reason='startup_crash',
        )


class _ReactionPoller(threading.Thread):
    """Workstation ground-truth poller (HIL only): records the CLOSEST approach to the ball as
    the reaction point (the robot reacts, then stops/retreats, so it never gets closer). The
    Jetson can't measure ground truth; this is the yellow rung's only way to recover its
    reaction point (yellow drives home after reacting). Same equivalence caveat as the retired
    harness `watch`: valid only because the path never loops back past the ball."""

    def __init__(self, ball_xy, poll_s=0.5):
        super().__init__(daemon=True)
        self._ball = ball_xy
        self._poll_s = poll_s
        self._halt = threading.Event()
        self.reaction_xy = None
        self._best = None

    def run(self):
        while not self._halt.is_set():
            xy = get_ground_truth_xy()
            if xy is not None:
                d = (xy[0] - self._ball[0]) ** 2 + (xy[1] - self._ball[1]) ** 2
                if self._best is None or d < self._best:
                    self._best = d
                    self.reaction_xy = list(xy)
            time.sleep(self._poll_s)

    def stop(self):
        self._halt.set()
        self.join(timeout=5)


def _parse_checklist(log_text):
    """Recover the per-waypoint checklist rows the Jetson's mission_runner printed."""
    return [(m.group(2), m.group(1)) for m in
            (_CHECKLIST_RE.match(ln) for ln in log_text.splitlines()) if m]


# ── Stack lifecycle (sim mode only; HIL's stack is owned by scripts/hil_stage.sh) ───────────
def _pkill(pattern):
    subprocess.run(['pkill', '-9', '-f', pattern], check=False)


def sweep_orphans():
    """Kill any Gazebo/Nav2/bridge/TF/ekf orphans (best-effort). The orchestrator's own
    cmdline ('python -m tools.mission2_day') matches none of these patterns, so there is no
    self-match to bracket-trick around here."""
    for pat in _SWEEP_PATTERNS:
        _pkill(pat)
    subprocess.run(['pkill', '-f', 'gz sim'], check=False)


def launch_stack(log_path):
    """Launch Gazebo + Nav2 (headless server) in its OWN process group and wait until Nav2
    is active. Returns the Popen. The GUI viewer, when wanted, is a SEPARATE `gz sim -g`
    client (this machine's Gazebo GUI crashes when co-launched — CLAUDE.md) — the report
    carries that command for the observed run."""
    sweep_orphans()
    time.sleep(2)
    log.info('launching Gazebo + Nav2 (headless) ...')
    logf = open(log_path, 'w')
    proc = subprocess.Popen(
        ['ros2', 'launch', LAUNCH_FILE, 'headless:=true'],
        cwd=str(REPO_DIR), stdout=logf, stderr=subprocess.STDOUT,
        start_new_session=True)   # own process group => killpg SIGINTs the whole tree
    deadline = time.time() + STACK_READY_TIMEOUT_S
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f'launch exited early (rc={proc.returncode}); see {log_path}')
        try:
            text = pathlib.Path(log_path).read_text(errors='ignore')
        except OSError:
            text = ''
        if text.count(NAV2_READY_MARK) >= 2:
            log.info('stack ready (Nav2 managed nodes active)')
            time.sleep(5)   # let AMCL settle its first map->odom
            return proc
        time.sleep(3)
    raise RuntimeError(f'stack not ready within {STACK_READY_TIMEOUT_S}s; see {log_path}')


def shutdown_stack(proc):
    """SIGINT the launch process group, then sweep any orphans and verify none remain."""
    log.info('shutting down the stack ...')
    if proc is not None and proc.poll() is None:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGINT)
        except ProcessLookupError:
            pass
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            pass
    sweep_orphans()
    time.sleep(2)
    leftovers = subprocess.run(
        ['pgrep', '-af', 'gz sim|component_container|robot_state_publisher|ros2 launch|'
         'parameter_bridge|static_transform|ekf_node'],
        capture_output=True, text=True).stdout.strip()
    if leftovers:
        log.warning('orphans still present after sweep:\n' + leftovers)
    else:
        log.info('clean — no orphans remain')


# ── The day sequence (SAME for sim and HIL — only executor + ball_ops differ) ───────────────
def _print_checklist(checklist, verdict, fails):
    for label, v in checklist:
        log.info(f'    [{v:^8}] {label}')
    for f in fails:
        log.info(f'    JUDGE FAIL: {f}')
    log.info(f'  => {verdict}')


def run_no_ball(executor, ball_ops=None, ball_xy=None):
    """Mike's day design (2026-07-18 GUI review): the YELLOW ball is placed DURING this run's
    return leg — the observer sees it appear behind the retreating robot, and run 2 starts
    with no dead air. gz mode only; operator mode keeps its explicit post-run prompt."""
    log.info('\n=== RUN 1/3: no_ball — verified round trip ===')
    log.info(f'  start ground truth: {get_ground_truth_xy()}')
    holder = {'placed_name': None}
    place_thread = None
    stop_evt = threading.Event()
    if ball_ops is not None and ball_ops.concurrent and ball_xy is not None:
        place_thread = threading.Thread(
            target=_place_during_return,
            args=(ball_ops, 'yellow', ball_xy, holder, stop_evt), daemon=True)
        place_thread.start()
    try:
        result = executor.run()
    finally:
        # finally (not inline after run()): an exception out of executor.run() must not
        # leave the placement thread spawning/polling into shutdown — stop it either way.
        if place_thread is not None:
            stop_evt.set()
            place_thread.join(timeout=30)
    final = get_ground_truth_xy()
    sim = home_pair_similarity(result.tagged('mission2_home_ref'),
                               result.tagged('mission2_home_arrival'))
    fails = judge_no_ball(result.reaction_events, final,
                          result.tagged('mission2_marker'), sim)
    ok = not fails
    log_variant_row('no_ball', None, ok=ok, runner=result,
                    home_photo_similarity=sim)
    log.info(f'  home_photo_similarity = {sim}')
    _print_checklist(result.checklist, f"no_ball {'PASS' if ok else 'FAIL'}", fails)
    executor.reset()
    return ok, holder['placed_name']


class RetreatDetector:
    """Pure retreat detection (extracted in S17 review CR-17 so both background threads
    share one implementation and it is unit-testable): the robot is 'retreating' once its
    ground-truth y has fallen `drop_m` below the peak y observed so far. Valid because
    Mission 2's outbound leg drives monotonically north (+y) and its return drives south —
    a mission whose path zig-zags in y would need a different signal."""

    def __init__(self, drop_m=RETREAT_DROP_M):
        self._drop_m = drop_m
        self._peak_y = None

    def update(self, xy):
        """Feed one ground-truth sample (or None); True once retreat is detected."""
        if xy is None:
            return False
        y = xy[1]
        self._peak_y = y if self._peak_y is None else max(self._peak_y, y)
        return (self._peak_y - y) >= self._drop_m


def _wait_for_retreat(stop_evt, poll_s=0.3):
    """Poll workstation ground truth until retreat is detected or stop_evt fires.
    Returns True on detected retreat, False when stopped first (mission ended — the
    caller then performs its action anyway as the fallback). Mode-agnostic: ground
    truth is workstation-side in BOTH sim and HIL."""
    detector = RetreatDetector()
    while not stop_evt.is_set():
        if detector.update(get_ground_truth_xy()):
            return True
        time.sleep(poll_s)
    return False


def _place_during_return(ball_ops, color, ball_xy, holder, stop_evt):
    """Background placement for run 1's return leg: wait until the robot has begun
    retreating, then place `color` behind it. If the mission finishes first, stop_evt
    fires the same placement as a fallback — the ball is always in place before the next
    run. NOTE: placement happens on the return leg, where reactions are NOT armed
    (outbound-only) — verified in missions.py."""
    if _wait_for_retreat(stop_evt):
        log.info(f'retreat detected — placing {color} behind the returning robot')
    holder['placed_name'] = ball_ops.place(color, *ball_xy)


def _swap_during_return(ball_ops, yellow_name, ball_xy, holder, stop_evt):
    """Background swap: on retreat (or mission-end fallback), remove yellow, settle past
    the ghost-model lag, and spawn red at the same spot. gz calls are subprocess-based,
    so this shares no ROS state with the mission."""
    if _wait_for_retreat(stop_evt):
        log.info('retreat detected — swapping yellow -> red behind the robot')
    ball_ops.remove(yellow_name)
    ball_ops.settle()
    holder['red_name'] = ball_ops.place('red', *ball_xy)


def run_yellow(executor, ball_ops, ball_xy, yellow_name=None):
    log.info('\n=== RUN 2/3: yellow — stop 0.8 m, photograph, self-return home ===')
    if yellow_name is None:   # operator mode, or run-1 placement didn't happen
        yellow_name = ball_ops.place('yellow', *ball_xy)
    truth_start = get_ground_truth_xy()
    log.info(f'  start ground truth: {truth_start}')
    holder = {'red_name': None}
    swap_thread = None
    stop_evt = threading.Event()
    if ball_ops.concurrent:
        swap_thread = threading.Thread(
            target=_swap_during_return,
            args=(ball_ops, yellow_name, ball_xy, holder, stop_evt), daemon=True)
        swap_thread.start()
    try:
        result = executor.run(ball_xy=ball_xy, color='yellow')
    finally:
        # finally (not inline after run()): an exception out of executor.run() must not
        # leave the swap thread spawning/polling into shutdown — stop it either way.
        if swap_thread is not None:
            stop_evt.set()
            swap_thread.join(timeout=30)
    final = get_ground_truth_xy()
    if swap_thread is None:   # operator: swap after the robot is safely home
        ball_ops.remove(yellow_name)
        ball_ops.settle()
        holder['red_name'] = ball_ops.place('red', *ball_xy)
    sim = home_pair_similarity(result.tagged('mission2_home_ref'),
                               result.tagged('mission2_home_arrival'))
    fails = judge_yellow(ball_xy, result.reaction_events,
                         result.tagged('reaction_yellow'), truth_start, final, sim)
    ok = not fails
    log_variant_row('yellow', None, ok=ok, runner=result,
                    home_photo_similarity=sim)
    log.info(f'  home_photo_similarity = {sim}')
    _print_checklist(result.checklist, f"yellow {'PASS' if ok else 'FAIL'}", fails)
    executor.reset()
    return ok, holder['red_name']


def run_red(executor, ball_ops, ball_xy, red_name, hold_s):
    log.info('\n=== RUN 3/3: red — stop 1.3 m, photograph, STAY ===')
    if red_name is None:   # concurrent swap did not run (shouldn't happen) — place now
        red_name = ball_ops.place('red', *ball_xy)
    truth_start = get_ground_truth_xy()
    log.info(f'  start ground truth: {truth_start}')
    result = executor.run(ball_xy=ball_xy, color='red')
    truth_a = get_ground_truth_xy()
    time.sleep(2.0)                       # explicit stationary-settle (matches the sim test)
    truth_b = get_ground_truth_xy()
    fails = judge_red(ball_xy, result.reaction_events, result.tagged('reaction_red'),
                      truth_start, truth_a, truth_b,
                      home_arrival_photos=result.tagged('mission2_home_arrival'))
    ok = not fails
    log_variant_row('red', None, ok=ok, runner=result)
    _print_checklist(result.checklist, f"red {'PASS' if ok else 'FAIL'}", fails)
    executor.reset()
    if hold_s > 0:
        log.info(f'  red done — robot stays put; holding {hold_s:.0f}s for the observer')
        time.sleep(hold_s)
    # Ball STAYS (spec §4) — deliberately not removed.
    return ok


def run_day(executor, ball_ops, ball_xy, hold_s):
    """The reusable day core — SAME on sim and HIL, only executor + BallOps differ."""
    results = {}
    results['no_ball'], yellow_name = run_no_ball(executor, ball_ops, ball_xy)
    results['yellow'], red_name = run_yellow(executor, ball_ops, ball_xy, yellow_name)
    results['red'] = run_red(executor, ball_ops, ball_xy, red_name, hold_s)
    log.info('\n=== SUMMARY ===')
    for name in ('no_ball', 'yellow', 'red'):
        log.info(f'  {name:8s}: {"PASS" if results[name] else "FAIL"}')
    return all(results.values())


def main():
    parser = argparse.ArgumentParser(description='Mission 2 "rehearse the real day".')
    parser.add_argument('--executor', choices=['inprocess', 'jetson'], default='inprocess',
                        help='inprocess = run the mission on the workstation (sim); '
                             'jetson = run it on the Jetson over SSH (HIL). Ball ops + judging '
                             'stay workstation-side either way.')
    parser.add_argument('--ball-ops', choices=['gz', 'operator'], default='gz',
                        help='gz = Gazebo spawn/remove (sim/HIL); operator = human prompts '
                             '(robot-day dry run)')
    parser.add_argument('--hold-s', type=float, default=0.0,
                        help='seconds to hold after the red run so an observer sees "done" '
                             '(default 0 = headless self-test; use ~10 for a watched run)')
    parser.add_argument('--no-launch', action='store_true',
                        help='assume the stack is already up (do not launch/teardown it). '
                             'Implied by --executor jetson (hil_stage.sh owns the HIL stack).')
    parser.add_argument('--log', default='/tmp/mission2_day_sim.log')
    args = parser.parse_args()

    pathlib.Path(STATE_DIR).mkdir(parents=True, exist_ok=True)
    configure(log_file=os.path.join(STATE_DIR, 'mission2_day.log'))
    log.info(build_env_manifest(
        git_sha=git_sha(), executor=args.executor,
        runner_type=os.environ.get('RUNNER_TYPE'), power_mode=POWER_MODE_LABEL,
        hil_image=os.environ.get('HIL_IMAGE')))

    hil = args.executor == 'jetson'
    no_launch = args.no_launch or hil
    ball_ops = GzBallOps() if args.ball_ops == 'gz' else OperatorBallOps()
    ball_xy = BALL_AT_SPHERE_XY

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
    log.info(f'\nMission 2 day: {"PASS" if ok else "FAIL"}')
    raise SystemExit(0 if ok else 1)


if __name__ == '__main__':
    main()
