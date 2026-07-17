"""Unit tests for the Mission 2 harness geometry — pure Python (stage-1)."""
import math


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
    from nav_fleet.missions import REACTION_RANGE_M
    from tools.mission2_harness import solve_placement
    for seed in range(20):
        x, y = solve_placement('ignore', seed)
        assert _route_min_dist(x, y) >= REACTION_RANGE_M + 0.5


def test_judge_red_passes_good_run():
    from tools.mission2_harness import judge_red
    events = [{'color': 'red', 'reaction': 'photo_then_stop', 'truth_xy': (0.0, 2.4)}]
    fails = judge_red(ball_xy=(0.0, 3.0), events=events,
                      photo_paths=['reports/photos/x.png'],
                      truth_a=(0.0, 2.4), truth_b=(0.0, 2.41))
    assert fails == []


def test_judge_red_fails_outside_band_and_moving():
    from tools.mission2_harness import judge_red
    events = [{'color': 'red', 'reaction': 'photo_then_stop', 'truth_xy': (0.0, 0.5)}]
    fails = judge_red(ball_xy=(0.0, 3.0), events=events, photo_paths=['p.png'],
                      truth_a=(0.0, 0.5), truth_b=(0.0, 0.8))
    assert any('band' in f for f in fails)
    assert any('stationary' in f for f in fails)


def test_judge_red_fails_without_event_or_photo():
    from tools.mission2_harness import judge_red
    fails = judge_red(ball_xy=(0.0, 3.0), events=[], photo_paths=[],
                      truth_a=(0.0, 2.4), truth_b=(0.0, 2.4))
    assert any('no red reaction' in f for f in fails)
    assert any('photo' in f for f in fails)


def test_judge_yellow_checks_reaction_point_and_home():
    from tools.mission2_harness import judge_yellow
    events = [{'color': 'yellow', 'reaction': 'photo_then_home', 'truth_xy': (0.0, 2.4)}]
    ok = judge_yellow(ball_xy=(0.0, 3.0), events=events, photo_paths=['p.png'],
                      final_truth=(-1.2, 1.25))
    assert ok == []
    far = judge_yellow(ball_xy=(0.0, 3.0), events=events, photo_paths=['p.png'],
                       final_truth=(0.0, 3.0))
    assert any('home' in f for f in far)


def test_judge_ignore_zero_reactions_and_sphere_band():
    from tools.mission2_harness import judge_ignore
    assert judge_ignore(events=[], final_truth=(0.0, 3.2)) == []
    fails = judge_ignore(
        events=[{'color': 'red', 'reaction': 'photo_then_stop', 'truth_xy': None}],
        final_truth=(0.0, 1.0))
    assert any('reaction' in f for f in fails)
    assert any('sphere' in f for f in fails)
