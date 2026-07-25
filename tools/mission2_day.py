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

* BallOps — WHO places the ball: Gazebo spawn/remove (sim) or operator places/swaps manually
  (robot day, unprompted).
* MissionExecutor (Task 13d) — WHERE the mission runs: in-process on the workstation (sim),
  or on the Jetson over SSH (HIL). Ball ops + ground-truth judging ALWAYS stay workstation-
  side (Gazebo lives on the workstation in both modes); only the mission executor moves.

Run from the repo root against a freshly-built workspace:

    python -m tools.mission2_day                  # sim, headless judged self-test (CI-style)
    python -m tools.mission2_day --hold-s 10       # sim GUI-watch rehearsal (separate gz -g)
    python -m tools.mission2_day --ball-ops operator   # robot-day dry run (no gz, human handles ball timing)
    python -m tools.mission2_day --executor jetson --no-launch   # HIL: mission on the Jetson
                                                   # (stack brought up by scripts/hil_stage.sh)

The GUI-watched run (Mike observing) is intentionally NOT executed by CI/self-tests — this
tool just makes it a single command away.
"""
import argparse
import math
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
                                    judge_yellow, log_variant_row, remove_ball, spawn_ball)
from tools.pipeline_matrix import load_stage
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
    """Robot day: the operator's hands are the actuator, not Gazebo. `concurrent = False`
    means run_day()'s choreography thread never starts for this mode — Mike's explicit
    call (2026-07-24, S17 Piece 9 rewrite): no delays, no prompting; it's up to the human
    to place/swap the ball at the correct time while the day runs. A marker class only —
    `.place()`/`.remove()` are unreachable (nothing calls them), so they're left
    unimplemented (inherited from BallOps) rather than kept as dead prompt code."""
    concurrent = False


# ── Mission execution (WHERE) ─────────────────────────────────────────────────────────────
class MissionExecutor:
    def run_day(self):
        """Run the WHOLE day (3 legs: no_ball, yellow, red) in one call and return the 3
        leg dicts MissionRunner.run_mission2_day() produces (t_start/t_end/ok/checklist/
        photos/reaction_events) — same shape whether the mission ran in-process or on the
        Jetson."""
        raise NotImplementedError

    def close(self):
        """Tear down any day-level resources. No-op by default — S17 Piece 9's single
        continuous run_day() call removed the only real user this ever had
        (JetsonExecutor's now-removed persistent container, Piece 8)."""


class InProcessExecutor(MissionExecutor):
    """Sim day: run the mission in-process on the workstation via a live MissionRunner —
    one continuous run_mission2_day() call replaces the old 3 separately-invoked run()s."""

    def __init__(self, runner):
        self.runner = runner

    def run_day(self):
        return self.runner.run_mission2_day()


class JetsonExecutor(MissionExecutor):
    """HIL day: run the WHOLE day on the Jetson over SSH with ONE `--day` invocation of
    mission_runner.py (S17 Piece 9) — replaces the old per-scenario SSH call (and, before
    that, the long-lived-container machinery from Piece 8, which existed only to amortize
    3 `docker run`s/day; with a single `run_day()` call there is only ONE docker
    invocation/day either way now, so that machinery is gone too — see the module-level
    JetsonExecutor docstring history in mission2_day.py's git log for Piece 8 if needed).
    The Jetson has no Gazebo, so ground truth (reaction truth_xy, home-arrival comparisons)
    comes from the workstation-side GroundTruthLog run_day() (top-level function) collects
    for the whole call — not from anything this class does. Photos are scp'd back to
    reports/photos/ AND STATE_DIR."""

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
            cmd = (f'{JENV} && cd {JETSON_REPO} && RUNNER_TYPE=hil_jetson '
                   f'POWER_MODE={POWER_MODE_LABEL} {cmd_suffix}')
        out_path = os.path.join(self.state_dir, 'day.out')
        dispatch_time = time.time()
        log.info(f'[timing] ssh dispatch for the day at {dispatch_time:.3f}')
        # 1080s (18 min: comfortable headroom over worst-case real leg work + cold-start
        # retry backoff, while leaving a 2-min safety margin under CI's 1200s outer
        # timeout — S17 review fix, 2026-07-25) — the inner timeout must fire FIRST so
        # the normal teardown/evidence-upload steps can still run via `if: always()`.
        proc = subprocess.run(
            ['timeout', '1080', 'ssh', '-o', 'BatchMode=yes',
             f'{JETSON_USER}@{self.ip}', cmd],
            capture_output=True, text=True)
        log.info(f'[timing] ssh returned for the day at {time.time():.3f} '
                 f'(+{time.time() - dispatch_time:.3f}s total)')
        log_text = proc.stdout + proc.stderr
        pathlib.Path(out_path).write_text(log_text)
        # raw ssh output — verbose; the MISSION2_DAY_RESULT line below is the summary.
        log.debug(log_text.rstrip())
        self._log_startup_crash_if_needed(log_text, proc.returncode)
        self._pull_failure_bags(log_text)  # before result parsing — succeeds even on crash
        results = self._parse_day_result(log_text)
        for leg in results:
            leg['photos'] = self._pull_photos_from_paths(leg['photos'])
        return results

    def _parse_day_result(self, log_text):
        import json
        for line in log_text.splitlines():
            if line.startswith('MISSION2_DAY_RESULT:'):
                return json.loads(line[len('MISSION2_DAY_RESULT:'):])
        raise RuntimeError('no MISSION2_DAY_RESULT line found in Jetson output — '
                            'process likely crashed before printing it; see day.out')

    def _pull_photos_from_paths(self, remote_paths):
        """scp each already-known remote photo path (from the day JSON's own 'photos'
        list for this leg — no regex scrape of log text needed, unlike the old
        per-scenario call) to reports/photos/ AND STATE_DIR (Task 13g — photos always
        visible on the workstation + in the CI evidence artifact)."""
        PHOTO_DIR.mkdir(parents=True, exist_ok=True)
        pathlib.Path(self.state_dir).mkdir(parents=True, exist_ok=True)
        local = []
        for rel in remote_paths:
            base = os.path.basename(rel)
            dest = PHOTO_DIR / base
            remote_path = self._remote_photo_path(rel)
            rc = subprocess.run(
                ['scp', '-o', 'BatchMode=yes',
                 f'{JETSON_USER}@{self.ip}:{remote_path}', str(dest)],
                capture_output=True, text=True).returncode
            if rc == 0:
                subprocess.run(['cp', '-f', str(dest),
                                os.path.join(self.state_dir, base)], check=False)
                local.append(str(dest))
            else:
                log.warning(f'could not scp Jetson photo {rel}')
        return local

    def _remote_photo_path(self, rel):
        """`rel` (from a 'photo saved: <path>' log line) is PHOTO_DIR-relative absolute
        (2026-07-22 fix — was checkout-relative, see _ssh_mission2's comment) — but that
        absolute path was recorded from wherever mission_runner actually ran, which isn't
        always the real Jetson filesystem path:
          - bare-metal: mission_runner runs directly as JETSON_USER, so `rel` already IS
            the real host path — use it as-is.
          - container: `rel` is a path INSIDE the container (root's HOME, e.g.
            '/root/fleet-ci-data/...'), which the container-run bind mount
            (-v $HOME/fleet-ci-data:/root/fleet-ci-data) maps onto JETSON_USER's real
            fleet-ci-data dir on the host — substitute the container's root prefix for
            '~' so the remote shell expands it to JETSON_USER's actual home."""
        if self.image is not None:
            return '~' + rel[len('/root'):]
        return rel

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


# ── Stack lifecycle (sim mode only; HIL's stack is owned by scripts/hil_stage.sh) ───────────
def _pkill(pattern):
    subprocess.run(['pkill', '-9', '-f', pattern], check=False)


def sweep_orphans():
    """Kill any Gazebo/Nav2/bridge/TF/ekf orphans (best-effort). The orchestrator's own
    cmdline ('python -m tools.mission2_day') matches none of these patterns, so there is no
    self-match to bracket-trick around here.

    Scoped to 'gz sim -s' (the headless SERVER, always launched with -s -r) — NOT a bare
    'gz sim', which also matches the separate GUI viewer ('gz sim -g', no -s). A live
    2026-07-22 GUI-watched run found the old bare pattern killing an observer's viewer
    within seconds of every run starting, since this sweep runs before the stack even
    launches (Piece 7)."""
    for pat in _SWEEP_PATTERNS:
        _pkill(pat)
    subprocess.run(['pkill', '-f', 'gz sim -s'], check=False)


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


class OutboundDetector:
    """Mirror image of RetreatDetector (S17 Piece 9 gap fix, 2026-07-25): the robot is
    'heading back out' once its ground-truth y has risen `climb_m` above the trough y
    observed so far. Closes a live bug found in run_ball_choreography(): two back-to-back
    RetreatDetector waits used to share no memory of each other, so a FRESH detector
    started for the second wait could be fooled by more of the SAME still-in-progress
    descent from leg 1's own return (not a new leg 2 return) into firing immediately —
    confirmed live: place-yellow and swap-to-red happened only 4s apart, both still
    within leg 1's own ~27s return-home drive. Requiring a genuine climb back out FIRST
    (this detector) before arming the second RetreatDetector closes the gap: the second
    wait can no longer start listening until leg 2's own outbound drive has actually
    begun."""

    def __init__(self, climb_m=RETREAT_DROP_M):
        self._climb_m = climb_m
        self._trough_y = None

    def update(self, xy):
        """Feed one ground-truth sample (or None); True once a genuine climb back out
        is detected."""
        if xy is None:
            return False
        y = xy[1]
        self._trough_y = y if self._trough_y is None else min(self._trough_y, y)
        return (y - self._trough_y) >= self._climb_m


def run_ground_truth_log_only(stop_evt, poll_s=0.3):
    """S17 review fix (2026-07-25): ground-truth LOGGING must run regardless of
    `ball_ops.concurrent` — only the actual ball placement/swap ACTIONS are gated on
    that flag. Pre-fix, run_day() only ever started a background thread `if
    ball_ops.concurrent:` (run_ball_choreography), which is the ONLY thing that
    populated a GroundTruthLog — so operator mode (the real-robot day, non-concurrent
    ball ops) never logged any ground truth at all, and every judge_* function reads
    "no ground truth" as an unconditional FAIL. This is the operator-mode counterpart
    to run_ball_choreography's own polling loop, minus every ball_ops call — used by
    run_day() whenever `ball_ops.concurrent` is False so a GroundTruthLog is ALWAYS
    populated, in every mode."""
    truth_log = GroundTruthLog()
    while not stop_evt.is_set():
        xy = get_ground_truth_xy()
        if xy is not None:
            truth_log.record(time.time(), xy)
        time.sleep(poll_s)
    return truth_log


def run_ball_choreography(ball_ops, ball_xy, stop_evt, poll_s=0.3):
    """S17 Piece 9: ONE thread for the whole day (was 2 separate per-call threads).
    Sequences the SAME 2 actions today's design already does — place yellow behind
    the robot during leg 1's retreat, swap yellow->red during leg 2's retreat — but
    now driven by ONE continuous ground-truth poll loop spanning the single blocking
    run_day() call, since there's no longer a per-leg call boundary to scope a
    separate thread to. Concurrent-only (gz mode) — run_day() only calls this function
    `if ball_ops.concurrent:`; operator mode instead runs run_ground_truth_log_only()
    (S17 review fix, 2026-07-25), which shares this function's polling/logging loop but
    makes no ball_ops calls at all, leaving human ball placement/swap timing fully
    unprompted while still keeping ground-truth logging on in every mode.

    Three waits, not two (2026-07-25 gap fix): a RetreatDetector for leg 1's return
    (places yellow), an OutboundDetector confirming leg 2's own outbound drive has
    genuinely started (see OutboundDetector docstring for why this gate is needed),
    THEN a fresh RetreatDetector for leg 2's return (swaps yellow -> red). Without the
    middle wait, the second RetreatDetector could fire on leftover descent from leg
    1's own still-in-progress return instead of a real leg 2 return.

    Returns the GroundTruthLog recorded along the way (reused for judging - Task 3)."""
    truth_log = GroundTruthLog()
    holder = {'placed_name': None, 'red_name': None}

    def _wait_for(detector):
        while not stop_evt.is_set():
            xy = get_ground_truth_xy()
            t = time.time()
            if xy is not None:
                truth_log.record(t, xy)
            if detector.update(xy):
                return True
            time.sleep(poll_s)
        return False

    if _wait_for(RetreatDetector()):
        log.info('retreat detected — placing yellow behind the returning robot')
    holder['placed_name'] = ball_ops.place('yellow', *ball_xy)

    if _wait_for(OutboundDetector()):
        log.info('robot heading back out — arming swap detection')

    if _wait_for(RetreatDetector()):
        log.info('retreat detected — swapping yellow -> red behind the robot')
    ball_ops.remove(holder['placed_name'])
    ball_ops.settle()
    holder['red_name'] = ball_ops.place('red', *ball_xy)

    # Keep logging (no more ball actions left) until the caller signals the day is
    # done, so leg 3's own closest-approach/truth samples are still captured.
    while not stop_evt.is_set():
        xy = get_ground_truth_xy()
        if xy is not None:
            truth_log.record(time.time(), xy)
        time.sleep(poll_s)
    return truth_log


def hil_variant_names():
    """The HIL day's variant names, declared once in config/pipeline_matrix.yaml
    (as full 'mission2_*' scenario names, stripped here to the bare form run_day's
    results dict uses) — replaces a separately hardcoded tuple that could silently
    drift out of sync with ci.yml's --stage hil report scoping (Piece 6). Also the
    declared ORDER run_day() zips against MissionRunner.run_mission2_day()'s 3
    returned leg dicts — unchanged by this task, ['no_ball', 'yellow', 'red']."""
    _, scenarios = load_stage('hil')
    return [s.removeprefix('mission2_') for s in scenarios]


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
    per-call SSH/process boundary. A background thread runs for the WHOLE call and
    ALWAYS ends up populating a GroundTruthLog — judging happens in a loop after the
    single call returns.

    `ball_ops.concurrent == False` (OperatorBallOps, robot-day dry run): only the
    ball ACTIONS are skipped — run_ground_truth_log_only() still runs so judging has
    real ground truth (S17 review fix, 2026-07-25: pre-fix, operator mode started NO
    thread at all, so every leg FAILed unconditionally on "no ground truth", even on
    a mission that ran correctly). `ball_ops.concurrent == True` (GzBallOps) keeps
    running the full run_ball_choreography() (places/swaps the ball too). Mike's
    explicit call (2026-07-24) still holds for operator mode: no prompting, no
    delays — it is up to the human to place/swap the ball at the correct time.

    The `finally` block waits a real ~2.5s AFTER the executor call returns before
    signalling the thread to stop (S17 review fix, 2026-07-25): without this, the
    logging thread on the in-process (x86) executor stops within milliseconds of the
    day finishing, so judge_red's two "is the robot still stationary" samples
    (t_end and t_end + 2.0) both clamp to the same last sample and the check can
    never fail — a vacuous check, not a real one. This wait is real time, once per
    run_day() call (not per leg)."""
    log.info('\n=== Mission 2 day: one continuous run, 3 legs ===')
    stop_evt = threading.Event()
    gt_log_holder = {}

    def _run():
        if ball_ops.concurrent:
            gt_log_holder['log'] = run_ball_choreography(ball_ops, ball_xy, stop_evt)
        else:
            gt_log_holder['log'] = run_ground_truth_log_only(stop_evt)

    gt_thread = threading.Thread(target=_run, daemon=True)
    gt_thread.start()
    try:
        legs = executor.run_day()
    finally:
        time.sleep(2.5)   # let the gt thread keep sampling past the day's nominal end
        stop_evt.set()
        gt_thread.join(timeout=30)
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


def main():
    parser = argparse.ArgumentParser(description='Mission 2 "rehearse the real day".')
    parser.add_argument('--executor', choices=['inprocess', 'jetson'], default='inprocess',
                        help='inprocess = run the mission on the workstation (sim); '
                             'jetson = run it on the Jetson over SSH (HIL). Ball ops + judging '
                             'stay workstation-side either way.')
    parser.add_argument('--ball-ops', choices=['gz', 'operator'], default='gz',
                        help='gz = Gazebo spawn/remove (sim/HIL); operator = human places/swaps '
                             'unprompted (robot-day dry run)')
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
    log.info(f'\nMission 2 day: {"PASS" if ok else "FAIL"}')
    raise SystemExit(0 if ok else 1)


if __name__ == '__main__':
    main()
