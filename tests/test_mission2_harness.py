"""Unit tests for the Mission 2 harness geometry — pure Python (stage-1)."""
import math

import pytest


def _route_min_dist(x, y):
    from tools.mission2_harness import _route_points
    return min(math.hypot(x - rx, y - ry) for rx, ry in _route_points())


def test_placement_deterministic_per_seed():
    from tools.mission2_harness import solve_placement
    assert solve_placement('react', 42) == solve_placement('react', 42)
    assert solve_placement('ignore', 42) == solve_placement('ignore', 42)
    assert solve_placement('react', 42) != solve_placement('react', 43)


def test_react_placement_sits_on_the_approach_corridor():
    from tools.mission2_harness import solve_placement
    for seed in range(20):
        x, y = solve_placement('react', seed)
        assert _route_min_dist(x, y) <= 0.2         # on/next to the route line
        assert 2.4 <= y <= 3.2                       # between doorway and sphere approach


def test_ignore_placement_stays_outside_reaction_envelope():
    from tools.mission2_harness import MAX_REACTION_RANGE_M, solve_placement
    for seed in range(20):
        x, y = solve_placement('ignore', seed)
        # Must clear the LARGEST per-color trigger threshold (red, 1.3 m) so an
        # "ignore" placement is safe for either color spawned there (Task 9 final
        # batch, 2026-07-17 — REACTION_RANGE_M became per-color).
        assert _route_min_dist(x, y) >= MAX_REACTION_RANGE_M + 0.5


def test_react_placement_keeps_min_spawn_distance_from_home():
    """Task 9 fix (2026-07-17): a react ball must be far enough from home_base that the
    robot has to actually drive to reach the trigger envelope — otherwise the mission
    "reacts" at t=0 with no movement and the judge (pre-fix) had no way to catch it."""
    from nav_fleet.semantic_map import SEMANTIC_MAP
    from tools.mission2_harness import MIN_SPAWN_DIST_M, solve_placement
    hx, hy = SEMANTIC_MAP['home_base']
    for seed in range(20):
        x, y = solve_placement('react', seed)
        assert math.hypot(x - hx, y - hy) >= MIN_SPAWN_DIST_M


def test_band_far_is_per_color_derived_from_reaction_range():
    """Task 9 final batch (2026-07-17): BAND_FAR must track REACTION_RANGE_M per color,
    not a single hardcoded constant — red 1.3+0.3=1.6 (unchanged in effect), yellow
    0.8+0.3=1.1 (new)."""
    from nav_fleet.missions import REACTION_RANGE_M
    from tools.mission2_harness import BAND_FAR
    assert BAND_FAR == {'red': pytest.approx(1.6), 'yellow': pytest.approx(1.1)}
    for color, threshold in REACTION_RANGE_M.items():
        assert BAND_FAR[color] == pytest.approx(threshold + 0.3)


def test_judge_yellow_reaction_point_within_tighter_yellow_band():
    """A reaction point just outside yellow's tighter 1.1 m far band (but that would have
    passed under the old shared 1.6 m band) must now fail — this is the behavior change
    the per-color BAND_FAR is meant to enforce."""
    from tools.mission2_harness import judge_yellow
    events = [{'color': 'yellow', 'reaction': 'photo_then_home', 'truth_xy': (0.0, 1.7)}]
    fails = judge_yellow(ball_xy=(0.0, 3.0), events=events, photo_paths=['p.png'],
                         truth_start=(-1.276, 1.2), final_truth=(-1.276, 1.2))
    assert any('band' in f for f in fails)


def test_judge_red_passes_good_run():
    from tools.mission2_harness import judge_red
    events = [{'color': 'red', 'reaction': 'photo_then_stop', 'truth_xy': (0.0, 2.4)}]
    fails = judge_red(ball_xy=(0.0, 3.0), events=events,
                      photo_paths=['reports/photos/x.png'],
                      truth_start=(-1.276, 1.2), truth_a=(0.0, 2.4), truth_b=(0.0, 2.41))
    assert fails == []


def test_judge_red_fails_outside_band_and_moving():
    from tools.mission2_harness import judge_red
    events = [{'color': 'red', 'reaction': 'photo_then_stop', 'truth_xy': (0.0, 0.5)}]
    fails = judge_red(ball_xy=(0.0, 3.0), events=events, photo_paths=['p.png'],
                      truth_start=(0.0, 1.5), truth_a=(0.0, 0.5), truth_b=(0.0, 0.8))
    assert any('band' in f for f in fails)
    assert any('stationary' in f for f in fails)


def test_judge_red_fails_without_event_or_photo():
    from tools.mission2_harness import judge_red
    fails = judge_red(ball_xy=(0.0, 3.0), events=[], photo_paths=[],
                      truth_start=(-1.276, 1.2), truth_a=(0.0, 2.4), truth_b=(0.0, 2.4))
    assert any('no red reaction' in f for f in fails)
    assert any('photo' in f for f in fails)


def test_judge_red_fails_when_robot_did_not_drive():
    """Task 9 fix (2026-07-17): the degenerate-pass regression test — same start and
    reaction-point truth (robot never moved) must fail even with a good in-band event."""
    from tools.mission2_harness import judge_red
    events = [{'color': 'red', 'reaction': 'photo_then_stop', 'truth_xy': (0.0, 1.2)}]
    fails = judge_red(ball_xy=(0.0, 1.7), events=events, photo_paths=['p.png'],
                      truth_start=(0.0, 1.2), truth_a=(0.0, 1.2), truth_b=(0.0, 1.2))
    assert any('barely moved' in f for f in fails)


def test_judge_yellow_checks_reaction_point_and_home():
    from tools.mission2_harness import judge_yellow
    events = [{'color': 'yellow', 'reaction': 'photo_then_home', 'truth_xy': (0.0, 2.4)}]
    ok = judge_yellow(ball_xy=(0.0, 3.0), events=events, photo_paths=['p.png'],
                      truth_start=(-1.276, 1.2), final_truth=(-1.2, 1.25))
    assert ok == []
    far = judge_yellow(ball_xy=(0.0, 3.0), events=events, photo_paths=['p.png'],
                       truth_start=(-1.276, 1.2), final_truth=(0.0, 3.0))
    assert any('home' in f for f in far)


def test_judge_yellow_fails_when_robot_did_not_drive():
    from tools.mission2_harness import judge_yellow
    events = [{'color': 'yellow', 'reaction': 'photo_then_home', 'truth_xy': (0.0, 1.2)}]
    fails = judge_yellow(ball_xy=(0.0, 1.7), events=events, photo_paths=['p.png'],
                         truth_start=(0.0, 1.2), final_truth=(-1.276, 1.2))
    assert any('barely moved' in f for f in fails)


def test_judge_ignore_zero_reactions_and_sphere_band():
    from tools.mission2_harness import judge_ignore
    assert judge_ignore(events=[], final_truth=(0.0, 3.2)) == []
    fails = judge_ignore(
        events=[{'color': 'red', 'reaction': 'photo_then_stop', 'truth_xy': None}],
        final_truth=(0.0, 1.0))
    assert any('reaction' in f for f in fails)
    assert any('sphere' in f for f in fails)
