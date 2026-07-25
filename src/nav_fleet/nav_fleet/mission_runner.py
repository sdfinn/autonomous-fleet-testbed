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
"""Mission executor: runs a named mission (waypoints + action primitives) against Nav2.

Run from the repo root (same reason as tools/agentic_loop.py — module imports):

    python -m nav_fleet.mission_runner mission1

Requires a live sim (sim_launch.py, or sim_only + nav2_only for HIL). Logs one telemetry
row per mission to FLEET_DB via tools.telemetry_logger.
"""
import argparse
import math
import os
import pathlib
import time
import traceback

import rclpy
from nav2_msgs.srv import ClearEntireCostmap
from rclpy.node import Node
from sensor_msgs.msg import Image
from vision_msgs.msg import Detection2DArray

from nav_fleet import failure_bag
from nav_fleet.ground_truth import get_ground_truth_xy
from nav_fleet.image_io import image_msg_to_png
from nav_fleet.missions import (MISSIONS, REACTION_FRAMES, REACTION_RANGE_M,
                                validate_mission)
from nav_fleet.nav_runner import NavRunner
from nav_fleet.semantic_map import SEMANTIC_MAP
from tools.log_setup import build_env_manifest, git_sha, resolve_level
from tools.telemetry_logger import PHOTO_DIR as _PHOTO_DIR, log_run

PHOTO_DIR = pathlib.Path(_PHOTO_DIR)
NAV_TIMEOUT_S = 90.0

# Cleared before every navigate leg (see MissionRunner._clear_costmaps for the why).
CLEAR_COSTMAP_SERVICES = (
    '/robot_001/global_costmap/clear_entirely_global_costmap',
    '/robot_001/local_costmap/clear_entirely_local_costmap',
)


class MissionRunner(Node):

    def __init__(self):
        super().__init__('mission_runner')
        self.get_logger().set_level(resolve_level())
        self.nav = NavRunner()
        self.photo_paths = []
        self.nav_durations = []
        self.nav_errors = []
        # Failure taxonomy (S17 Piece 3): 'nav_timeout'/'goal_rejected' (from
        # NavRunner.last_failure_reason), 'no_camera_frame', or 'crash' (set by main()'s
        # except block). None on a passing mission. _log_mission reads this for telemetry.
        self.failure_reason = None
        self._latest_image = None
        self.create_subscription(
            Image, '/robot_001/camera/image_raw', self._image_cb, 10
        )
        self._costmap_clearers = {
            srv: self.create_client(ClearEntireCostmap, srv)
            for srv in CLEAR_COSTMAP_SERVICES
        }
        self.reaction_events = []
        # Per-waypoint verdict list (Task 13, Option B): one (label, verdict) per executed
        # step — 'PASS'/'FAIL'/'REACTION'. The mission verdict IS this checklist; main()
        # prints it as the round-trip audit trail.
        self.checklist = []
        self._watch = None  # active only during a reactive navigate leg
        self.create_subscription(
            Detection2DArray, '/robot_001/detections', self._detection_cb, 10
        )

    def _image_cb(self, msg):
        self._latest_image = msg

    def _clear_costmaps(self, wait_s=3.0, call_s=3.0):
        """Clear both Nav2 costmaps before a navigate leg. Best-effort by design.

        Why: obstacle marks from live lidar accumulate across a long-lived session (the
        driving of a prior test, plus an earlier leg of the same mission) and can close a
        marginal corridor — here the hallway arch. Session 16 diagnosed exactly this as the
        cause of Mission 1's leg-3 planner failure ("Failed to create plan with tolerance").

        Best-effort: on service unavailability or a call timeout we log a warning and
        continue. A clear that doesn't land is not a mission failure — the navigate leg's
        own result is the real signal. The node is not being spun by an executor here, so we
        drive the future with spin_until_future_complete (same pattern as take_picture)."""
        for srv, client in self._costmap_clearers.items():
            if not client.wait_for_service(timeout_sec=wait_s):
                self.get_logger().warning(f'{srv} unavailable — skipping costmap clear')
                continue
            fut = client.call_async(ClearEntireCostmap.Request())
            rclpy.spin_until_future_complete(self, fut, timeout_sec=call_s)
            if not fut.done():
                self.get_logger().warning(f'{srv} clear timed out — continuing')

    def take_picture(self, label, timeout=15.0):
        """Capture one fresh camera frame and save it as a PNG under reports/photos/."""
        self._latest_image = None  # force a frame newer than this call
        deadline = time.time() + timeout
        while self._latest_image is None and time.time() < deadline:
            rclpy.spin_once(self, timeout_sec=0.1)
        if self._latest_image is None:
            self.get_logger().error(f'no camera frame within {timeout}s')
            self.failure_reason = 'no_camera_frame'
            return False
        PHOTO_DIR.mkdir(parents=True, exist_ok=True)
        path = PHOTO_DIR / f"{label}_{time.strftime('%Y%m%d_%H%M%S')}.png"
        image_msg_to_png(self._latest_image, str(path))
        self.photo_paths.append(str(path))
        self.get_logger().info(f'photo saved: {path}')
        return True

    def _detection_cb(self, msg):
        """Count consecutive in-range frames per watched color (trigger definition A).

        Empty detector frames arrive too (the detector publishes every frame), so a
        lost glimpse resets the count with no timing heuristics needed."""
        if self._watch is None:
            return
        w = self._watch
        in_range = set()
        for det in msg.detections:
            if not det.results:
                continue
            color = det.results[0].hypothesis.class_id.removesuffix('_ball')
            est_range = det.results[0].pose.pose.position.x
            # math.isfinite rejects NaN — hsv_detect.detect_balls sets range_m to NaN
            # for frame-edge-clipped bounding boxes (Task 9 fix, 2026-07-17): their
            # width-derived range is unreliable and must not drive the trigger. A plain
            # `est_range <= REACTION_RANGE_M[color]` would already be False for NaN
            # (IEEE754), but the explicit check documents the exclusion instead of
            # relying on that.
            # REACTION_RANGE_M[color] (Task 9 final batch, 2026-07-17): per-color
            # threshold — red=1.3 m (danger, react early), yellow=0.8 m (caution, closer
            # approach). Direct indexing is intentional: `color in w['reactions']` above
            # only admits colors that a mission actually declared a reaction for, and
            # every such color must have a matching threshold here — a missing key is a
            # real configuration bug that should raise, not be silently swallowed.
            if (color in w['reactions'] and math.isfinite(est_range) and est_range > 0
                    and est_range <= REACTION_RANGE_M[color]):
                in_range.add(color)
        for color in w['reactions']:
            if color in in_range:
                w['counts'][color] = w['counts'].get(color, 0) + 1
                if w['counts'][color] >= REACTION_FRAMES and w['triggered'] is None:
                    w['triggered'] = color
            else:
                w['counts'][color] = 0

    def _print_leg_truth(self, name, label):
        """Sim-only per-leg audit trail (Task 13 §5): where the robot PHYSICALLY is right
        after a navigate leg. None on the real robot (no Gazebo) — callers treat None as
        'no ground truth', never a failure. Kept out of the verdict; it's a log line."""
        truth = get_ground_truth_xy()
        self.get_logger().info(f'[{name}] leg done "{label}": ground truth = {truth}')
        return truth

    def _execute_reaction(self, name, reaction, color):
        """Run the declared reaction on existing primitives (spec §2): the goal is
        already cancelled (robot stopped). Photo first — document the hazard — then
        photo_then_home retreats (no reactions during the retreat, by design) and, per
        Task 13 Option B, takes a home ARRIVAL photo so the return-fidelity pair check
        applies to yellow too. photo_then_stop (red) stays put and takes NO home photo."""
        truth = get_ground_truth_xy()  # robot's OWN pose snapshot (None off-sim) — the
        # harness judges the reaction point against it; ball positions stay unknown here.
        self.get_logger().warning(f'[{name}] REACTION: {color} ball -> {reaction}')
        self.reaction_events.append(
            {'color': color, 'reaction': reaction, 'truth_xy': truth})
        ok = self.take_picture(f'{name}_reaction_{color}')
        if reaction == 'photo_then_home':
            self._clear_costmaps()
            hx, hy = SEMANTIC_MAP['home_base']
            ok = self.nav.send_goal(hx, hy, timeout=NAV_TIMEOUT_S, yaw=math.pi / 2) and ok
            self._print_leg_truth(name, 'return home (reaction)')
            # Home arrival photo — the return-fidelity anchor's partner (pair check).
            ok = self.take_picture(f'{name}_home_arrival') and ok
        return ok

    def run_mission(self, name):
        steps = MISSIONS[name]
        validate_mission(steps)
        self.checklist = []
        for i, step in enumerate(steps, start=1):
            self.get_logger().info(f'[{name}] step {i}/{len(steps)}: {step.label}')
            if step.action == 'navigate':
                self._clear_costmaps()  # marks accumulate across the session — clear per leg
                x, y = SEMANTIC_MAP[step.location]
                if step.reactions:
                    self._watch = {'reactions': step.reactions, 'counts': {},
                                   'triggered': None}
                    ok = self.nav.send_goal(
                        x, y, timeout=NAV_TIMEOUT_S, yaw=step.yaw,
                        interrupt_cb=lambda: self._watch['triggered'],
                        spin_extra=self)
                    triggered, self._watch = self._watch['triggered'], None
                    if triggered is not None:
                        # Reaction SHORTENS the mission (Option B): this navigate waypoint's
                        # verdict is the reaction outcome; the remaining waypoints are not
                        # expected (red stops here; yellow folds return+arrival into the
                        # reaction). Record it in the checklist and short-circuit.
                        self.checklist.append((f'{step.label} -> reaction {triggered}',
                                               'REACTION'))
                        react_ok = self._execute_reaction(
                            name, step.reactions[triggered], triggered)
                        self.checklist.append(
                            (f'reaction {triggered} completed',
                             'PASS' if react_ok else 'FAIL'))
                        return react_ok
                else:
                    ok = self.nav.send_goal(x, y, timeout=NAV_TIMEOUT_S, yaw=step.yaw)
                    if not ok:
                        self.failure_reason = self.nav.last_failure_reason
                if ok:
                    self._print_leg_truth(name, step.label)  # per-leg audit (sim only)
                # FAIL-leg policy (Session 16): a failed/timed-out leg's duration measures
                # the timeout, not the robot — keep it out of the row's aggregate metrics.
                # (An interrupted leg returns False, so it stays out automatically.)
                if ok:
                    if self.nav.last_duration_s is not None:
                        self.nav_durations.append(self.nav.last_duration_s)
                    if self.nav.last_position_error is not None:
                        self.nav_errors.append(self.nav.last_position_error)
            else:  # take_picture — validate_mission guarantees the action set
                label = f'{name}_{step.photo_tag}' if step.photo_tag else f'{name}_step{i}'
                ok = self.take_picture(label)
            self.checklist.append((step.label, 'PASS' if ok else 'FAIL'))
            if not ok:
                self.get_logger().error(f'[{name}] step {i} ({step.label}) FAILED')
                return False
        return True

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


def _mean(values):
    return sum(values) / len(values) if values else None


def _log_mission(name, ok, runner, crashed=False):
    nav = runner.nav if runner is not None else None
    # 'crash' overrides whatever runner.failure_reason holds — a constructor crash
    # leaves runner None (no failure_reason to read); a crash mid-mission is the more
    # severe, more specific fact worth recording over a stale nav/camera reason.
    if crashed:
        failure_reason = 'crash'
    elif not ok and runner is not None:
        failure_reason = runner.failure_reason
    else:
        failure_reason = None
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
        failure_reason=failure_reason,
    )


def main():
    parser = argparse.ArgumentParser(description='Run a named mission against Nav2.')
    parser.add_argument('mission', nargs='?', default=None, choices=sorted(MISSIONS))
    parser.add_argument('--day', action='store_true',
                        help='S17 Piece 9: run mission2 3x in one process, print one '
                             'combined JSON result instead of exiting after one '
                             'mission — replaces mission2_day.py calling this 3x over '
                             'SSH.')
    args = parser.parse_args()

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

    # Started before rclpy.init() — an independent OS process, not an rclpy node; a
    # snapshot-mode recorder writes NOTHING to disk until snapshot() below is called,
    # so this costs nothing on the (overwhelmingly common) passing mission.
    bag_proc, bag_path = failure_bag.start(args.mission)
    rclpy.init()
    runner = None
    ok = False
    crashed = False
    try:
        # Constructed INSIDE the try: a constructor crash (e.g. rclpy/DDS failure) must
        # still produce the FAIL telemetry row that stage-4-hil's verdict depends on.
        runner = MissionRunner()
        runner.get_logger().info(build_env_manifest(
            git_sha=git_sha(), power_mode=os.environ.get('POWER_MODE')))
        ok = runner.run_mission(args.mission)
    except Exception as exc:  # still log a FAIL row on crash — docstring contract
        traceback.print_exc()
        print(f'mission {args.mission} crashed: {exc!r}')
        crashed = True
    finally:
        rclpy.try_shutdown()
    bag_kept = (not ok or crashed) and failure_bag.snapshot()
    if bag_kept:
        print(f'failure bag kept: {bag_path}')
    failure_bag.stop(bag_proc, bag_path, keep=bag_kept)
    _log_mission(args.mission, ok, runner, crashed=crashed)

    print(f"Mission {args.mission}: {'PASS' if ok else 'FAIL'}")
    # Sim-only honesty readout (None on the real robot — no Gazebo there): where the
    # robot PHYSICALLY ended vs the final navigate goal. The verdict above trusts
    # Nav2/AMCL; a large miss here means a false PASS (see tests/test_mission_run.py).
    truth = get_ground_truth_xy()
    nav_steps = [s for s in MISSIONS[args.mission] if s.action == 'navigate']
    if truth is not None and nav_steps:
        gx, gy = SEMANTIC_MAP[nav_steps[-1].location]
        miss = math.hypot(truth[0] - gx, truth[1] - gy)
        print(f'  ground truth: ({truth[0]:.2f}, {truth[1]:.2f}) — '
              f'{miss:.2f} m from final goal ({gx}, {gy})')
    for p in (runner.photo_paths if runner is not None else []):
        print(f'  photo: {p}')
    for ev in (runner.reaction_events if runner is not None else []):
        print(f"  reaction: {ev['color']} -> {ev['reaction']} at {ev['truth_xy']}")
    # Per-waypoint checklist (Task 13 Option B): the mission verdict IS this checklist.
    if runner is not None and runner.checklist:
        print(f'  waypoint checklist ({args.mission}):')
        for label, verdict in runner.checklist:
            print(f'    [{verdict:^8}] {label}')
    raise SystemExit(0 if ok else 1)


if __name__ == '__main__':
    main()
