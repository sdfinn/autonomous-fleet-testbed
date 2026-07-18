"""Mission 2 integration tests — three deterministic variants (spec §3).

Requires live Gazebo + Nav2 (ros2 launch src/nav_fleet/launch/sim_launch.py). Ignored in
stage-1-quality — imports rclpy at module level (see CLAUDE.md Gotchas; bitten twice).

Placement (Task 9 rework, 2026-07-17 — Mike's explicit decision): the red/yellow balls are
spawned at the fixed tools.mission2_harness.BALL_AT_SPHERE_XY spot beside the green sphere,
not seeded-random. Seeded fuzzing is deferred to a later session (area-of-interest
sampling) — solve_placement() and the seed machinery stay in tools/mission2_harness.py
unused for now. Telemetry rows from these tests log `seed=None` (the DB column is
nullable) since there is no seed to reproduce.

Test order matters: each test's autouse teardown drives the robot home for the next one.
That drive-home result is currently discarded (real navigation can still fail), so every
test below asserts the start-position precondition (_assert_at_home_base, Task 9 final
batch, 2026-07-17) before doing anything else — a prior test's cleanup failure surfaces
loudly in the next test's setup instead of silently corrupting its placement geometry.
"""
import math
import pathlib
import time

import pytest
import rclpy  # noqa: F401 — module-level import ensures collection fails without ROS2

from nav_fleet.ground_truth import get_ground_truth_xy
from nav_fleet.mission_runner import MissionRunner
from nav_fleet.semantic_map import SEMANTIC_MAP
from tools.mission2_harness import (BALL_AT_SPHERE_XY, judge_red, judge_yellow,
                                    log_variant_row, remove_ball, spawn_ball)


@pytest.fixture(scope='session', autouse=True)
def _module_ros(ros_context):
    yield


@pytest.fixture(scope='session')
def runner(ros_context):
    node = MissionRunner()
    yield node
    node.nav.destroy_node()
    node.destroy_node()


@pytest.fixture(autouse=True)
def _drive_home_after(runner):
    """Cleanup, not judgment: park the robot at home_base for the next variant."""
    yield
    runner.reaction_events.clear()
    runner._clear_costmaps()
    hx, hy = SEMANTIC_MAP['home_base']
    runner.nav.send_goal(hx, hy, timeout=90.0, yaw=math.pi / 2)


# Renderer-lag settle after remove_ball (Task 9 fix, 2026-07-17): the headless llvmpipe
# software renderer takes up to ~1.5 s for a newly SPAWNED model to appear in camera
# frames (CLAUDE.md Gotchas, 2026-07-17 Mission 2 calibration); a REMOVED model was
# observed to linger in rendered frames for a comparable or longer span, causing spurious
# reactions in the NEXT test. There's no cheap poll target here (no fixture currently
# subscribes to /robot_001/detections from the test side — only mission_runner's own node
# does, internally, during run_mission), so a conservative fixed sleep — roughly double
# the known spawn-appearance lag — is used instead of a tighter poll loop.
BALL_REMOVAL_SETTLE_S = 3.0

# Final-arrival tolerance for the nominal variant (no reaction — a plain navigate leg, same
# kind of check as test_mission_run.py's GROUND_TRUTH_TOLERANCE_M, widened slightly per
# the Task 9 rework brief).
NOMINAL_GOAL_TOLERANCE_M = 0.35

# Start-position precondition tolerance (Task 9 final batch, 2026-07-17): the
# `_drive_home_after` teardown above is real navigation whose result is currently
# discarded — a failed drive-home silently leaves the NEXT test starting from the wrong
# pose, corrupting its placement geometry and travel-distance checks without any visible
# error. Each test below asserts ground truth is close to home_base at the START of the
# test, so a prior test's cleanup failure surfaces loudly (in the next test's setup)
# instead of silently producing a bogus PASS/FAIL for a test that never actually started
# from home. 0.35 m matches NOMINAL_GOAL_TOLERANCE_M.
START_POSITION_TOL_M = 0.35


def _assert_at_home_base():
    truth = get_ground_truth_xy()
    hx, hy = SEMANTIC_MAP['home_base']
    assert truth is not None, 'no ground truth — is the sim up on this host?'
    miss = math.dist(truth, (hx, hy))
    assert miss <= START_POSITION_TOL_M, (
        f'precondition failed: robot not at home_base ({truth} is {miss:.2f} m from '
        f'({hx}, {hy}), tolerance {START_POSITION_TOL_M} m) — cleanup failure in a '
        f'previous test?')


@pytest.mark.timeout(300)
def test_mission2_red_stops_at_the_ball(runner):
    _assert_at_home_base()
    ball_xy = BALL_AT_SPHERE_XY
    name = spawn_ball('red', *ball_xy)
    fails = None
    try:
        truth_start = get_ground_truth_xy()  # Task 9: minimum-travel check (judge_red)
        runner.run_mission('mission2')
        truth_a = get_ground_truth_xy()
        time.sleep(2.0)
        truth_b = get_ground_truth_xy()
        photos = [p for p in runner.photo_paths if 'reaction_red' in p]
        fails = judge_red(ball_xy, runner.reaction_events, photos, truth_start, truth_a,
                          truth_b)
        for p in photos:
            assert pathlib.Path(p).exists()
    finally:
        remove_ball(name)
        time.sleep(BALL_REMOVAL_SETTLE_S)
        log_variant_row('red', None, ok=(fails == []), runner=runner)
    assert fails == [], '; '.join(fails)


@pytest.mark.timeout(300)
def test_mission2_yellow_photographs_and_retreats(runner):
    _assert_at_home_base()
    ball_xy = BALL_AT_SPHERE_XY
    name = spawn_ball('yellow', *ball_xy)
    fails = None
    try:
        truth_start = get_ground_truth_xy()  # Task 9: minimum-travel check (judge_yellow)
        runner.run_mission('mission2')
        final_truth = get_ground_truth_xy()
        photos = [p for p in runner.photo_paths if 'reaction_yellow' in p]
        fails = judge_yellow(ball_xy, runner.reaction_events, photos, truth_start,
                             final_truth)
    finally:
        remove_ball(name)
        time.sleep(BALL_REMOVAL_SETTLE_S)
        log_variant_row('yellow', None, ok=(fails == []), runner=runner)
    assert fails == [], '; '.join(fails)


@pytest.mark.timeout(300)
def test_mission2_nominal_green_sphere_only(runner):
    """No ball: navigate to sphere_approach, take a picture, stop. Zero reactions."""
    _assert_at_home_base()
    fails = []
    photos_before = len(runner.photo_paths)
    try:
        ok = runner.run_mission('mission2')
        if not ok:
            fails.append('mission itself reported FAIL')
        if runner.reaction_events:
            fails.append(f'spurious reaction(s): {runner.reaction_events}')
        # mission2's take_picture step is index 2 of 2 (see MISSIONS['mission2']) -> label
        # 'mission2_step2' in mission_runner.take_picture. Sliced from photos_before so an
        # earlier test's reaction photo (still sitting in the session-scoped runner's
        # photo_paths) can't be mistaken for this run's picture.
        new_photos = [p for p in runner.photo_paths[photos_before:] if 'mission2_step2' in p]
        if len(new_photos) != 1:
            fails.append(f'expected exactly 1 new mission2_step2 photo, got {new_photos}')
        else:
            assert pathlib.Path(new_photos[0]).exists()
        final_truth = get_ground_truth_xy()
        goal = SEMANTIC_MAP['sphere_approach']
        if final_truth is None:
            fails.append('no ground truth — is the sim up on this host?')
        else:
            miss = math.dist(final_truth, goal)
            if miss > NOMINAL_GOAL_TOLERANCE_M:
                fails.append(f'final pose {final_truth} is {miss:.2f} m from goal {goal} '
                             f'(tolerance {NOMINAL_GOAL_TOLERANCE_M} m)')
    finally:
        log_variant_row('nominal', None, ok=(fails == []), runner=runner)
    assert fails == [], '; '.join(fails)
