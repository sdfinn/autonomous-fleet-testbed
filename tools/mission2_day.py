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

Runs the WHOLE Mission 2 day, in order, against a LIVE stack, as one command — the
rehearsal of the real robot day:

  1. nominal  — no ball; the mission self-returns home (Option B).
  2. yellow   — place the yellow ball; the robot stops 0.8 m short, photographs it, and
                self-returns home. DURING its return leg the yellow ball is removed
                (>=3 s ghost settle) and the RED ball spawned at the same spot, behind the
                now-retreating robot (reactions are outbound-only, so red won't fire during
                the retreat).
  3. red      — the robot stops 1.3 m short, photographs, and STAYS; the ball STAYS; hold
                a few seconds so an observer unambiguously sees "done"; then clean shutdown.

Ball operations live behind a small BallOps interface so the on-Jetson ROBOT-day variant
swaps the Gazebo spawn/remove calls for operator prompts ("place the yellow ball, press
enter") — SAME procedure, different hands. That is the whole point of this file: it is
designed to BECOME the on-robot day runner, with only BallOps and the (sim-only) stack
launch swapped out.

Run from the repo root against a freshly-built workspace:

    python -m tools.mission2_day                 # headless, judged self-test (CI-style)
    python -m tools.mission2_day --hold-s 10      # GUI-watch rehearsal (see the report for
                                                  # the separate `gz sim -g` viewer command)
    python -m tools.mission2_day --ball-ops operator   # robot-day dry run (prompts, no gz)

The GUI-watched run (Mike observing) is intentionally NOT executed by CI/self-tests — this
tool just makes it a single command away.
"""
import argparse
import os
import pathlib
import signal
import subprocess
import threading
import time

import rclpy

from nav_fleet.ground_truth import get_ground_truth_xy
from nav_fleet.mission_runner import MissionRunner
from tools.mission2_harness import (BALL_AT_SPHERE_XY, BALL_REMOVAL_SETTLE_S,
                                    home_pair_similarity, judge_nominal, judge_red,
                                    judge_yellow, log_variant_row, remove_ball, spawn_ball)

REPO_DIR = pathlib.Path(__file__).resolve().parent.parent
LAUNCH_FILE = 'src/nav_fleet/launch/sim_launch.py'
NAV2_READY_MARK = 'Managed nodes are active'   # emitted once per lifecycle manager (x2)
STACK_READY_TIMEOUT_S = 150.0
SPAWN_APPEAR_SETTLE_S = 2.0                     # llvmpipe: new model takes ~1.5 s in-frame
RETREAT_DROP_M = 0.4                            # y-drop below peak that means "retreating"

# Orphan-sweep pattern (CLAUDE.md Gotchas): every process a Gazebo+Nav2 launch spawns that
# would poison the next run's DDS domain if it lingered. Kept in sync with ci.yml stage-2
# and scripts/hil_stage.sh teardown.
_SWEEP_PATTERNS = (
    'parameter_bridge|component_container_isolated|ekf_node',
    'static_transform_publisher|robot_state_publisher',
)


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
    """Sim day: spawn/remove camera-only balls in the running Gazebo (reuses the harness)."""
    concurrent = True

    def place(self, color, x, y):
        name = spawn_ball(color, x, y)
        print(f'[day] gz spawned {name} at ({x}, {y})')
        time.sleep(SPAWN_APPEAR_SETTLE_S)
        return name

    def remove(self, name):
        remove_ball(name)
        print(f'[day] gz removed {name}')


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
    print('[day] launching Gazebo + Nav2 (headless) ...')
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
            print('[day] stack ready (Nav2 managed nodes active)')
            time.sleep(5)   # let AMCL settle its first map->odom
            return proc
        time.sleep(3)
    raise RuntimeError(f'stack not ready within {STACK_READY_TIMEOUT_S}s; see {log_path}')


def shutdown_stack(proc):
    """SIGINT the launch process group, then sweep any orphans and verify none remain."""
    print('[day] shutting down the stack ...')
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
        print('[day] WARNING: orphans still present after sweep:\n' + leftovers)
    else:
        print('[day] clean — no orphans remain')


def _new_photos(runner, before, tag):
    """Photos this run appended to the session-scoped runner, filtered by semantic tag."""
    return [p for p in runner.photo_paths[before:] if tag in p]


def _print_checklist(runner, verdict, fails):
    for label, v in runner.checklist:
        print(f'    [{v:^8}] {label}')
    for f in fails:
        print(f'    JUDGE FAIL: {f}')
    print(f'  => {verdict}')


def run_nominal(runner):
    print('\n=== [day] RUN 1/3: nominal (no ball) — verified round trip ===')
    before = len(runner.photo_paths)
    print(f'  start ground truth: {get_ground_truth_xy()}')
    runner.run_mission('mission2')
    final = get_ground_truth_xy()
    sim = home_pair_similarity(_new_photos(runner, before, 'mission2_home_ref'),
                               _new_photos(runner, before, 'mission2_home_arrival'))
    fails = judge_nominal(runner.reaction_events, final,
                          _new_photos(runner, before, 'mission2_marker'), sim)
    ok = not fails
    log_variant_row('nominal', None, ok=ok, runner=runner, home_photo_similarity=sim)
    print(f'  home_photo_similarity = {sim}')
    _print_checklist(runner, f"nominal {'PASS' if ok else 'FAIL'}", fails)
    runner.reaction_events.clear()
    return ok


def _swap_during_return(ball_ops, yellow_name, ball_xy, holder, stop_evt):
    """Background swap: wait until the robot has begun retreating (ground-truth y has fallen
    RETREAT_DROP_M below its observed peak), then remove yellow, settle, and spawn red at the
    same spot. If the mission returns before retreat is detected, stop_evt fires the same
    swap as a fallback (red still ends up placed before the red run). gz calls are
    subprocess-based, so this shares no ROS state with the mission's rclpy spin."""
    peak_y = None
    while not stop_evt.is_set():
        xy = get_ground_truth_xy()
        if xy is not None:
            peak_y = xy[1] if peak_y is None else max(peak_y, xy[1])
            if peak_y - xy[1] >= RETREAT_DROP_M:
                print('[day] retreat detected — swapping yellow -> red behind the robot')
                break
        time.sleep(0.3)
    ball_ops.remove(yellow_name)
    ball_ops.settle()
    holder['red_name'] = ball_ops.place('red', *ball_xy)


def run_yellow(runner, ball_ops, ball_xy):
    print('\n=== [day] RUN 2/3: yellow — stop 0.8 m, photograph, self-return home ===')
    before = len(runner.photo_paths)
    yellow_name = ball_ops.place('yellow', *ball_xy)
    truth_start = get_ground_truth_xy()
    print(f'  start ground truth: {truth_start}')
    holder = {'red_name': None}
    swap_thread = None
    stop_evt = threading.Event()
    if ball_ops.concurrent:
        swap_thread = threading.Thread(
            target=_swap_during_return,
            args=(ball_ops, yellow_name, ball_xy, holder, stop_evt), daemon=True)
        swap_thread.start()
    runner.run_mission('mission2')
    final = get_ground_truth_xy()
    if swap_thread is not None:
        stop_evt.set()
        swap_thread.join(timeout=30)
    else:   # operator: swap after the robot is safely home
        ball_ops.remove(yellow_name)
        ball_ops.settle()
        holder['red_name'] = ball_ops.place('red', *ball_xy)
    sim = home_pair_similarity(_new_photos(runner, before, 'mission2_home_ref'),
                               _new_photos(runner, before, 'mission2_home_arrival'))
    fails = judge_yellow(ball_xy, runner.reaction_events,
                         _new_photos(runner, before, 'reaction_yellow'),
                         truth_start, final, sim)
    ok = not fails
    log_variant_row('yellow', None, ok=ok, runner=runner, home_photo_similarity=sim)
    print(f'  home_photo_similarity = {sim}')
    _print_checklist(runner, f"yellow {'PASS' if ok else 'FAIL'}", fails)
    runner.reaction_events.clear()
    return ok, holder['red_name']


def run_red(runner, ball_ops, ball_xy, red_name, hold_s):
    print('\n=== [day] RUN 3/3: red — stop 1.3 m, photograph, STAY ===')
    before = len(runner.photo_paths)
    if red_name is None:   # concurrent swap did not run (shouldn't happen) — place now
        red_name = ball_ops.place('red', *ball_xy)
    truth_start = get_ground_truth_xy()
    print(f'  start ground truth: {truth_start}')
    runner.run_mission('mission2')
    truth_a = get_ground_truth_xy()
    time.sleep(2.0)                       # explicit stationary-settle (matches the sim test)
    truth_b = get_ground_truth_xy()
    fails = judge_red(ball_xy, runner.reaction_events,
                      _new_photos(runner, before, 'reaction_red'),
                      truth_start, truth_a, truth_b,
                      home_arrival_photos=_new_photos(runner, before, 'mission2_home_arrival'))
    ok = not fails
    log_variant_row('red', None, ok=ok, runner=runner)
    _print_checklist(runner, f"red {'PASS' if ok else 'FAIL'}", fails)
    runner.reaction_events.clear()
    if hold_s > 0:
        print(f'  [day] red done — robot stays put; holding {hold_s:.0f}s for the observer')
        time.sleep(hold_s)
    # Ball STAYS (spec §4) — deliberately not removed.
    return ok


def run_day(runner, ball_ops, ball_xy, hold_s):
    """The reusable day core — SAME on sim and robot, only BallOps differs."""
    results = {}
    results['nominal'] = run_nominal(runner)
    results['yellow'], red_name = run_yellow(runner, ball_ops, ball_xy)
    results['red'] = run_red(runner, ball_ops, ball_xy, red_name, hold_s)
    print('\n=== [day] SUMMARY ===')
    for name in ('nominal', 'yellow', 'red'):
        print(f'  {name:8s}: {"PASS" if results[name] else "FAIL"}')
    return all(results.values())


def main():
    parser = argparse.ArgumentParser(description='Mission 2 "rehearse the real day".')
    parser.add_argument('--ball-ops', choices=['gz', 'operator'], default='gz',
                        help='gz = Gazebo spawn/remove (sim day); operator = human prompts '
                             '(robot-day dry run)')
    parser.add_argument('--hold-s', type=float, default=0.0,
                        help='seconds to hold after the red run so an observer sees "done" '
                             '(default 0 = headless self-test; use ~10 for a watched run)')
    parser.add_argument('--no-launch', action='store_true',
                        help='assume the stack is already up (do not launch/teardown it)')
    parser.add_argument('--log', default='/tmp/mission2_day_sim.log')
    args = parser.parse_args()

    ball_ops = GzBallOps() if args.ball_ops == 'gz' else OperatorBallOps()
    ball_xy = BALL_AT_SPHERE_XY
    proc = None
    ok = False
    try:
        if not args.no_launch:
            proc = launch_stack(args.log)
        rclpy.init()
        runner = MissionRunner()
        try:
            ok = run_day(runner, ball_ops, ball_xy, args.hold_s)
        finally:
            runner.nav.destroy_node()
            runner.destroy_node()
            rclpy.try_shutdown()
    finally:
        if not args.no_launch:
            shutdown_stack(proc)
    print(f'\nMission 2 day: {"PASS" if ok else "FAIL"}')
    raise SystemExit(0 if ok else 1)


if __name__ == '__main__':
    main()
