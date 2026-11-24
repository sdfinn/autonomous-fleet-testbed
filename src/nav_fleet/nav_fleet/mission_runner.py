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
import json
import math
import os
import pathlib
import time
import traceback

import numpy as np
import rclpy
from geometry_msgs.msg import PoseWithCovarianceStamped
from nav2_msgs.srv import ClearEntireCostmap
from nav_msgs.msg import OccupancyGrid
from rclpy.node import Node
from rclpy.qos import (DurabilityPolicy, QoSProfile, ReliabilityPolicy,
                       qos_profile_sensor_data)
from sensor_msgs.msg import Image, LaserScan
from vision_msgs.msg import Detection2DArray

from nav_fleet import failure_bag
from nav_fleet.detection import CAMERA_BY_WIDTH, GAZEBO_CAMERA, HAZARD, from_detector_msg
from nav_fleet.ground_truth import get_ground_truth_xy
from nav_fleet.image_io import image_msg_to_png
from nav_fleet.missions import (MISSIONS, REACTION_RANGE_M, ReactionRule,
                                validate_mission)
from nav_fleet import start_pose
from nav_fleet.nav_runner import NavRunner
from nav_fleet.path_guard import scan_points
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

# Mirrors tools.mission2_day.hil_variant_names()'s declared order
# (config/pipeline_matrix.yaml) — duplicated here, not imported, because this file
# is ROBOT code and must never import tools.mission2_day (which pulls in
# tools.mission2_harness — ball positions/judge logic robot code must never see).
MISSION2_DAY_LEG_NAMES = ('no_ball', 'yellow', 'red')


def _log_mission2_day_self_report(results):
    """Real-robot-only telemetry (MISSION2_SELF_REPORT=1, set by
    scripts/container_entrypoint.sh's caller for the real-robot context only —
    never for HIL): log each leg's SELF-reported PASS/FAIL (leg['ok'], from Nav2's
    own goal completion) with NO ground-truth judging. The real robot has no
    Gazebo, no ground-truth oracle at all (RealRobotStartup.md: a human's own eyes
    are the accepted substitute, and analysis of the resulting logs/photos happens
    after, not in real time). HIL never sets MISSION2_SELF_REPORT — its judged
    verdict comes from the workstation's own ground-truth check instead
    (tools.mission2_day, which stays workstation-side precisely because it needs
    Gazebo)."""
    for name, leg in zip(MISSION2_DAY_LEG_NAMES, results):
        log_run(
            scenario=f'mission2_{name}',
            steps=1,
            final_x=0.0, final_y=0.0,
            result='PASS' if leg['ok'] else 'FAIL',
            step_log=[],
            robot_id=os.environ.get('ROBOT_ID', 'robot_001'),
            robot_type='jetson_ugv_pt',
            runner_type=os.environ.get('RUNNER_TYPE', 'real_robot'),
            sim_engine='real',
            nav_success_rate=1.0 if leg['ok'] else 0.0,
            power_mode=os.environ.get('POWER_MODE'),
            photos=json.dumps(leg['photos']) if leg['photos'] else None,
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
        # Which camera the detections' pixel columns belong to (for a Detection's
        # bearing). Learned from the first picture's width in _image_cb: this process
        # is not told whether it is on the simulator or the real robot.
        self._camera = None
        # None = not checked yet; then True/False for the rest of this process.
        self._start_pose_ok = None
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
        if self._camera is None:
            self._camera = CAMERA_BY_WIDTH.get(msg.width, GAZEBO_CAMERA)
            if msg.width not in CAMERA_BY_WIDTH:
                self.get_logger().warning(
                    f'no camera known for pictures {msg.width} wide: bearings will be '
                    f'worked out as for the simulated camera')

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
        """Feed each detector message to the leg's ReactionRule (missions.py): a watched
        color must stay in range for a set time, not a set number of messages.

        Empty detector messages arrive too (the detector publishes for every picture),
        so a lost glimpse ends the run at once."""
        if self._watch is None:
            return
        # Diagnostic escape hatch (2026-08-13): a real-hardware run kept getting a
        # navigate leg interrupted by a false-positive color detection (hsv_gazebo.yaml
        # stand-in vs real camera/lighting, A4 still open), making it impossible to test
        # navigation/localization in isolation from that separate, unrelated bug.
        # Ignores every detection while active — matches a genuine no-ball leg's
        # behavior — without touching the mission model itself (missions.py's declared
        # reactions stay armed; only the trigger-counting below is skipped). Not meant
        # for a real judged/self-reported run — diagnostic use only.
        if os.environ.get('MISSION2_IGNORE_REACTIONS'):
            return
        w = self._watch
        in_range = set()
        # nav_fleet.detection is the one place that reads the detector's message
        # (2026-11-23). A Detection's distance_m is None when the detector sent NaN: a
        # box cut off by the picture's edge has an unreliable width and must not drive
        # the trigger (Task 9 fix, 2026-07-17). Only a HAZARD reacts: a class that is not
        # in detection.OBJECTS ("sports ball" with no readable color, "teddy bear") is
        # UNKNOWN and is ignored here.
        for d in from_detector_msg(msg, camera=self._camera or GAZEBO_CAMERA):
            color = d.class_name.removesuffix('_ball')
            # REACTION_RANGE_M[color] (Task 9 final batch, 2026-07-17): per-color
            # threshold — red=1.3 m (danger, react early), yellow=0.8 m (caution, closer
            # approach). Direct indexing is intentional: `color in w['reactions']` above
            # only admits colors that a mission actually declared a reaction for, and
            # every such color must have a matching threshold here — a missing key is a
            # real configuration bug that should raise, not be silently swallowed.
            if (d.kind == HAZARD and color in w['reactions'] and d.distance_m is not None
                    and d.distance_m <= REACTION_RANGE_M[color]):
                in_range.add(color)
        # The picture's own time, so the rule means the same at any detector rate.
        stamp_s = msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9
        fired = w['rule'].update(in_range, w['reactions'], stamp_s)
        if fired is not None and w['triggered'] is None:
            w['triggered'] = fired

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

    def check_start_pose(self, timeout_s=20.0):
        """Before the first goal of this process: does the lidar agree with the map from
        the pose the robot believes it has? (nav_fleet.start_pose says why believing is
        not enough.) Checked once; the answer holds for the rest of the process.
        MISSION_START_POSE_CHECK=off skips it."""
        if self._start_pose_ok is not None:
            return self._start_pose_ok
        if os.environ.get('MISSION_START_POSE_CHECK') == 'off':
            self.get_logger().warning('start pose check: SKIPPED (MISSION_START_POSE_CHECK=off)')
            self._start_pose_ok = True
            return True
        got = {'map': None, 'pose': None, 'scans': []}
        latched = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL,
                             reliability=ReliabilityPolicy.RELIABLE)
        subs = [
            self.create_subscription(OccupancyGrid, '/robot_001/map',
                                     lambda m: got.__setitem__('map', m), latched),
            self.create_subscription(PoseWithCovarianceStamped, '/robot_001/amcl_pose',
                                     lambda m: got.__setitem__('pose', m.pose.pose), latched),
            self.create_subscription(LaserScan, '/robot_001/scan',
                                     lambda m: got['scans'].append(m), qos_profile_sensor_data),
        ]
        deadline = time.time() + timeout_s
        while time.time() < deadline and (
                got['map'] is None or got['pose'] is None or len(got['scans']) < 5):
            rclpy.spin_once(self, timeout_sec=0.1)
        for sub in subs:
            self.destroy_subscription(sub)
        missing = [name for name in ('map', 'pose') if got[name] is None]
        if len(got['scans']) < 5:
            missing.append('lidar scans')
        if missing:
            self.get_logger().error(
                f'start pose check: no {" / ".join(missing)} within {timeout_s:.0f} s — '
                'cannot tell where the robot is; not starting')
            self.failure_reason = 'start_pose_unchecked'
            self._start_pose_ok = False
            return False
        info = got['map'].info
        grid = np.asarray(got['map'].data, dtype=np.int16).reshape(info.height, info.width)
        near = start_pose.near_occupied(grid, info.resolution, start_pose.TOLERANCE_M)
        pose = got['pose']
        believed = (pose.position.x, pose.position.y,
                    start_pose.yaw_of((pose.orientation.z, pose.orientation.w)))
        results = [start_pose.match_score(
            scan_points(s.ranges, s.angle_min, s.angle_increment, s.range_min, s.range_max),
            believed, near, info.resolution,
            (info.origin.position.x, info.origin.position.y)) for s in got['scans'][:5]]
        score = float(np.median([r[0] for r in results]))
        points = int(np.median([r[1] for r in results]))
        ok = score >= start_pose.MIN_MATCH and points >= start_pose.MIN_POINTS
        where = f'({believed[0]:.2f}, {believed[1]:.2f}, {math.degrees(believed[2]):.0f} deg)'
        if ok:
            self.get_logger().info(
                f'start pose check: ok — {score:.0%} of {points} lidar points match the '
                f'map from {where} (pass mark {start_pose.MIN_MATCH:.0%})')
        else:
            self.get_logger().error(
                f'start pose check: FAILED — only {score:.0%} of {points} lidar points '
                f'match the map from {where} (pass mark {start_pose.MIN_MATCH:.0%}). The '
                'robot is probably not where it was told it is, or is turned; not starting')
            self.failure_reason = 'start_pose_mismatch'
        self._start_pose_ok = ok
        return ok

    def run_mission(self, name):
        steps = MISSIONS[name]
        validate_mission(steps)
        self.checklist = []
        if not self.check_start_pose():
            self.checklist.append(('start pose check (lidar against the map)', 'FAIL'))
            return False
        for i, step in enumerate(steps, start=1):
            self.get_logger().info(f'[{name}] step {i}/{len(steps)}: {step.label}')
            if step.action == 'navigate':
                self._clear_costmaps()  # marks accumulate across the session — clear per leg
                x, y = SEMANTIC_MAP[step.location]
                if step.reactions:
                    self._watch = {'reactions': step.reactions, 'rule': ReactionRule(),
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
        # Started before rclpy.init() — same reasoning as the one-shot path below:
        # an independent OS process, not an rclpy node; snapshot-mode writes NOTHING
        # to disk until snapshot() is called, so this costs nothing on an all-PASS day.
        # Pre-fix (S17 review, 2026-07-25): this branch exited via `raise SystemExit(0)`
        # before ever reaching the one-shot path's failure-bag code below — since HIL
        # only runs via --day now, no HIL run could ever produce a failure bag.
        bag_proc, bag_path = failure_bag.start('mission2')
        rclpy.init()
        runner = None
        try:
            runner = MissionRunner()
            runner.get_logger().info(build_env_manifest(
                git_sha=git_sha(), power_mode=os.environ.get('POWER_MODE')))
            results = runner.run_mission2_day()
            print('MISSION2_DAY_RESULT:' + json.dumps(results))
            if os.environ.get('MISSION2_SELF_REPORT') == '1':
                _log_mission2_day_self_report(results)
            bag_kept = any(not leg['ok'] for leg in results) and failure_bag.snapshot()
            if bag_kept:
                print(f'failure bag kept: {bag_path}')
            failure_bag.stop(bag_proc, bag_path, keep=bag_kept)
        except Exception:
            # A crash mid-day (construction, or anywhere inside run_mission2_day) is
            # exactly the "can't reproduce it, need evidence" case this bag exists for
            # (failure_bag.py's docstring) — snapshot before the exception propagates.
            # Re-raised (not swallowed): mrc != 0 with no 'Mission mission2:' line in
            # the output is what JetsonExecutor._log_startup_crash_if_needed reads as
            # a startup crash — this branch never prints that line at all, so that
            # check is exactly right for a mid-day crash too, not just an import-time one.
            bag_kept = failure_bag.snapshot()
            if bag_kept:
                print(f'failure bag kept: {bag_path}')
            failure_bag.stop(bag_proc, bag_path, keep=bag_kept)
            raise
        finally:
            rclpy.try_shutdown()
        raise SystemExit(0)
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
