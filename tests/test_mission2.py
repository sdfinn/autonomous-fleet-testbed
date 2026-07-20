"""Mission 2 integration tests — Option B verified round trip, three variants (spec §3).

Requires live Gazebo + Nav2 (ros2 launch src/nav_fleet/launch/sim_launch.py). Ignored in
stage-1-quality — imports rclpy at module level (see CLAUDE.md Gotchas; bitten twice).

Task 13 Option B (2026-07-18): Mission 2 is ONE mission = a verified round trip. Each
variant is the SAME mission under a different WORLD STATE; a reaction legitimately SHORTENS
the path, and the shortened path is judged against its own expected waypoints (per-waypoint
checklist). nominal and yellow now END AT HOME — the mission owns its return leg — so there
is NO drive-home janitor between tests: each self-returning mission parks the robot at home
for the next one. Red is LAST and leaves the robot mid-room; nothing runs after it (the next
CI run relaunches fresh). Every test still asserts the start-position precondition, so a
mission that fails to return home surfaces LOUDLY in the next test's setup.

Placement (Task 9 rework, 2026-07-17 — Mike's decision): the red/yellow balls spawn at the
fixed tools.mission2_harness.BALL_AT_SPHERE_XY spot beside the floor marker, not
seeded-random. Telemetry rows log seed=None (nullable column).
"""
import math
import pathlib
import time

import pytest
pytest.importorskip('rclpy', reason='live-ROS tier: needs a ROS2 environment (S17 review CR-23 safety net - a forgotten stage-1 ignore now skips instead of breaking the stage)')
import rclpy  # noqa: F401,E402

from nav_fleet.ground_truth import get_ground_truth_xy
from nav_fleet.mission_runner import MissionRunner
from nav_fleet.semantic_map import SEMANTIC_MAP
from tools.mission2_harness import (BALL_AT_SPHERE_XY, BALL_REMOVAL_SETTLE_S,
                                    home_pair_similarity, judge_no_ball, judge_red,
                                    judge_yellow, log_variant_row, remove_ball, spawn_ball)


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
def _reset_events_after(runner):
    """No drive-home janitor under Option B — nominal and yellow self-return home, and red
    (last) leaves the robot mid-room with nothing after it. Only the session-scoped runner's
    per-test in-memory bookkeeping is cleared here."""
    yield
    runner.reaction_events.clear()


# Start-position precondition tolerance (Task 9 final batch, 2026-07-17): each test asserts
# ground truth is close to home_base at its START, so a prior mission's failed self-return
# surfaces loudly instead of silently corrupting this test's placement/travel geometry.
START_POSITION_TOL_M = 0.35


def _assert_at_home_base():
    truth = get_ground_truth_xy()
    hx, hy = SEMANTIC_MAP['home_base']
    assert truth is not None, 'no ground truth — is the sim up on this host?'
    miss = math.dist(truth, (hx, hy))
    assert miss <= START_POSITION_TOL_M, (
        f'precondition failed: robot not at home_base ({truth} is {miss:.2f} m from '
        f'({hx}, {hy}), tolerance {START_POSITION_TOL_M} m) — a previous mission failed to '
        f'return home?')


def _tagged(runner, before, tag):
    """This run's photos (appended to the session-scoped runner), filtered by semantic tag."""
    return [p for p in runner.photo_paths[before:] if tag in p]


@pytest.mark.timeout(300)
def test_mission2_no_ball_round_trip(runner):
    """No ball: home_ref photo -> navigate to marker -> marker photo -> navigate HOME ->
    home_arrival photo. Zero reactions, ended home, home-photo pair PASS."""
    _assert_at_home_base()
    before = len(runner.photo_paths)
    fails = None
    similarity = None
    try:
        ok = runner.run_mission('mission2')
        assert ok, 'mission itself reported FAIL'
        marker = _tagged(runner, before, 'mission2_marker')
        similarity = home_pair_similarity(_tagged(runner, before, 'mission2_home_ref'),
                                          _tagged(runner, before, 'mission2_home_arrival'))
        fails = judge_no_ball(runner.reaction_events, get_ground_truth_xy(), marker,
                              similarity)
        for p in marker:
            assert pathlib.Path(p).exists()
    finally:
        log_variant_row('no_ball', None, ok=(fails == []), runner=runner,
                        home_photo_similarity=similarity)
    assert fails == [], '; '.join(fails)


@pytest.mark.timeout(300)
def test_mission2_yellow_photographs_and_returns_home(runner):
    _assert_at_home_base()
    before = len(runner.photo_paths)
    ball_xy = BALL_AT_SPHERE_XY
    name = spawn_ball('yellow', *ball_xy)
    fails = None
    similarity = None
    try:
        truth_start = get_ground_truth_xy()  # minimum-travel check (judge_yellow)
        runner.run_mission('mission2')
        final_truth = get_ground_truth_xy()
        similarity = home_pair_similarity(_tagged(runner, before, 'mission2_home_ref'),
                                          _tagged(runner, before, 'mission2_home_arrival'))
        fails = judge_yellow(ball_xy, runner.reaction_events,
                             _tagged(runner, before, 'reaction_yellow'),
                             truth_start, final_truth, similarity)
    finally:
        remove_ball(name)
        time.sleep(BALL_REMOVAL_SETTLE_S)
        log_variant_row('yellow', None, ok=(fails == []), runner=runner,
                        home_photo_similarity=similarity)
    assert fails == [], '; '.join(fails)


@pytest.mark.timeout(300)
def test_mission2_red_stops_at_the_ball(runner):
    """LAST test (Option B): red stops mid-room and STAYS — no self-return, no home-arrival
    photo, and no janitor after it (the next CI run relaunches fresh)."""
    _assert_at_home_base()
    before = len(runner.photo_paths)
    ball_xy = BALL_AT_SPHERE_XY
    name = spawn_ball('red', *ball_xy)
    fails = None
    try:
        truth_start = get_ground_truth_xy()  # minimum-travel check (judge_red)
        runner.run_mission('mission2')
        truth_a = get_ground_truth_xy()
        time.sleep(2.0)                      # explicit stationary settle
        truth_b = get_ground_truth_xy()
        photos = _tagged(runner, before, 'reaction_red')
        fails = judge_red(ball_xy, runner.reaction_events, photos, truth_start, truth_a,
                          truth_b,
                          home_arrival_photos=_tagged(runner, before, 'mission2_home_arrival'))
        for p in photos:
            assert pathlib.Path(p).exists()
    finally:
        remove_ball(name)
        time.sleep(BALL_REMOVAL_SETTLE_S)
        log_variant_row('red', None, ok=(fails == []), runner=runner)
    assert fails == [], '; '.join(fails)
