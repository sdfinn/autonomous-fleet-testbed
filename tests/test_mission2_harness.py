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
        # between doorway (y=2.43) and sphere_approach (y=3.85, Task 13e deeper stop)
        assert 2.8 <= y <= 3.6


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
    # similarity=0.0 => a perfect home-photo pair, so the pair check contributes no fail.
    ok = judge_yellow(ball_xy=(0.0, 3.0), events=events, photo_paths=['p.png'],
                      truth_start=(-1.276, 1.2), final_truth=(-1.2, 1.25), similarity=0.0)
    assert ok == []
    far = judge_yellow(ball_xy=(0.0, 3.0), events=events, photo_paths=['p.png'],
                       truth_start=(-1.276, 1.2), final_truth=(0.0, 3.0), similarity=0.0)
    assert any('home' in f for f in far)


def test_judge_yellow_fails_on_bad_home_pair():
    """Task 13 §3: yellow self-returns and takes a home arrival photo, so a poor return
    (similarity above threshold) must fail even when everything else is good."""
    from tools.mission2_harness import HOME_PAIR_MAX_DIFF, judge_yellow
    events = [{'color': 'yellow', 'reaction': 'photo_then_home', 'truth_xy': (0.0, 2.4)}]
    fails = judge_yellow(ball_xy=(0.0, 3.0), events=events, photo_paths=['p.png'],
                         truth_start=(-1.276, 1.2), final_truth=(-1.2, 1.25),
                         similarity=HOME_PAIR_MAX_DIFF + 0.05)
    assert any('home photo pair mismatch' in f for f in fails)


def test_judge_yellow_fails_when_robot_did_not_drive():
    from tools.mission2_harness import judge_yellow
    events = [{'color': 'yellow', 'reaction': 'photo_then_home', 'truth_xy': (0.0, 1.2)}]
    fails = judge_yellow(ball_xy=(0.0, 1.7), events=events, photo_paths=['p.png'],
                         truth_start=(0.0, 1.2), final_truth=(-1.276, 1.2))
    assert any('barely moved' in f for f in fails)


def test_parse_reaction_events_recovers_color_reaction_and_tuple():
    """Task 12: the sim-side reaction print carries a real (x, y) truth tuple — recover it
    verbatim (color, reaction, truth_xy) so judge_red/judge_yellow consume it unchanged."""
    from tools.mission2_harness import parse_reaction_events
    log = ("[INFO] [mission_runner]: [mission2] step 1/2: drive toward the green sphere\n"
           "  reaction: red -> photo_then_stop at (0.31, 2.44)\n"
           "Mission mission2: PASS\n")
    assert parse_reaction_events(log) == [
        {'color': 'red', 'reaction': 'photo_then_stop', 'truth_xy': (0.31, 2.44)}]


def test_parse_reaction_events_handles_none_truth_from_jetson():
    """On the Jetson get_ground_truth_xy() returns None, so the printed truth is the literal
    'None' — it must parse to truth_xy=None (the HIL judge then supplies workstation truth)."""
    from tools.mission2_harness import parse_reaction_events
    log = "  reaction: yellow -> photo_then_home at None\n"
    assert parse_reaction_events(log) == [
        {'color': 'yellow', 'reaction': 'photo_then_home', 'truth_xy': None}]


def test_parse_reaction_events_empty_when_no_reactions():
    from tools.mission2_harness import parse_reaction_events
    assert parse_reaction_events("Mission mission2: PASS\nnothing to see here\n") == []


def test_parse_reaction_events_ignores_unparseable_truth():
    from tools.mission2_harness import parse_reaction_events
    events = parse_reaction_events("  reaction: red -> photo_then_stop at not_a_tuple\n")
    assert events == [{'color': 'red', 'reaction': 'photo_then_stop', 'truth_xy': None}]


def test_parse_reaction_events_feeds_judge_no_ball_spurious_reaction():
    """The nominal judge greps these lines expecting zero — a recovered event must make
    judge_no_ball report a spurious reaction (integration of parse + judge)."""
    from nav_fleet.semantic_map import SEMANTIC_MAP
    from tools.mission2_harness import judge_no_ball, parse_reaction_events
    events = parse_reaction_events("  reaction: red -> photo_then_stop at None\n")
    fails = judge_no_ball(events, final_truth=SEMANTIC_MAP['home_base'],
                          marker_photos=['m.png'], similarity=0.0)
    assert any('reaction' in f for f in fails)


def test_judge_no_ball_passes_good_round_trip():
    """Task 13 Option B: zero reactions + marker photo + ended home + good home pair."""
    from nav_fleet.semantic_map import SEMANTIC_MAP
    from tools.mission2_harness import judge_no_ball
    assert judge_no_ball(events=[], final_truth=SEMANTIC_MAP['home_base'],
                         marker_photos=['m.png'], similarity=0.02) == []


def test_judge_no_ball_fails_not_home_no_marker_and_bad_pair():
    from tools.mission2_harness import HOME_PAIR_MAX_DIFF, judge_no_ball
    fails = judge_no_ball(
        events=[{'color': 'red', 'reaction': 'photo_then_stop', 'truth_xy': None}],
        final_truth=(0.0, 3.5), marker_photos=[], similarity=HOME_PAIR_MAX_DIFF + 0.1)
    assert any('reaction' in f for f in fails)      # spurious reaction
    assert any('not home' in f for f in fails)      # ended at the marker, not home
    assert any('marker photo' in f for f in fails)  # never photographed the marker
    assert any('home photo pair' in f for f in fails)


def test_judge_red_fails_if_returned_home():
    """Task 13 §3: red must STOP mid-room — a home-arrival photo means it wrongly drove
    home, which the red judge now catches explicitly."""
    from tools.mission2_harness import judge_red
    events = [{'color': 'red', 'reaction': 'photo_then_stop', 'truth_xy': (0.0, 2.4)}]
    fails = judge_red(ball_xy=(0.0, 3.0), events=events,
                      photo_paths=['reports/photos/x.png'],
                      truth_start=(-1.276, 1.2), truth_a=(0.0, 2.4), truth_b=(0.0, 2.41),
                      home_arrival_photos=['mission2_home_arrival_x.png'])
    assert any('home-arrival photo' in f for f in fails)


def test_home_pair_similarity_and_judge(tmp_path):
    """photo_similarity: identical images -> 0.0; a very different image -> above threshold.
    home_pair_similarity picks the newest of each glob; judge_home_pair thresholds it."""
    from PIL import Image
    from tools.mission2_harness import (HOME_PAIR_MAX_DIFF, home_pair_similarity,
                                        judge_home_pair)
    ref = tmp_path / 'mission2_home_ref_1.png'
    same = tmp_path / 'mission2_home_arrival_1.png'
    diff = tmp_path / 'mission2_home_arrival_2.png'
    Image.new('RGB', (40, 40), (30, 60, 90)).save(ref)
    Image.new('RGB', (40, 40), (30, 60, 90)).save(same)
    Image.new('RGB', (40, 40), (240, 240, 240)).save(diff)
    s_same = home_pair_similarity([str(ref)], [str(same)])
    s_diff = home_pair_similarity([str(ref)], [str(diff)])
    assert s_same == pytest.approx(0.0, abs=1e-6)
    assert s_diff > HOME_PAIR_MAX_DIFF
    assert judge_home_pair(s_same) == []
    assert any('mismatch' in f for f in judge_home_pair(s_diff))
    # Missing photo -> None -> a clean fail, never a crash.
    assert home_pair_similarity([], [str(same)]) is None
    assert any('missing' in f for f in judge_home_pair(None))


def test_log_variant_row_passes_photos_as_json_to_log_run(monkeypatch):
    """2026-07-31: this leg's own photo list is now forwarded (JSON-encoded) to
    log_run() so generate_test_report.py can show each row's REAL photos instead of
    a time-window guess that cross-contaminates rows logged within the same second
    (mission2's 3 legs, judged in one tight loop, always share an identical
    timestamp). log_run/log_variant_row bind db_path at function-definition time
    (not per-call), so this mocks log_run itself rather than touching a real DB —
    see tools/vlm_canary.py's own comment on the identical binding trap."""
    import json

    from tools import mission2_harness
    captured = {}
    monkeypatch.setattr(mission2_harness, 'log_run', lambda **kw: captured.update(kw))

    mission2_harness.log_variant_row('red', None, ok=True, runner=None,
                                      photos=['/tmp/a.png', '/tmp/reaction_red.png'])

    assert json.loads(captured['photos']) == ['/tmp/a.png', '/tmp/reaction_red.png']


def test_log_variant_row_photos_null_when_not_given(monkeypatch):
    from tools import mission2_harness
    captured = {}
    monkeypatch.setattr(mission2_harness, 'log_run', lambda **kw: captured.update(kw))

    mission2_harness.log_variant_row('no_ball', None, ok=True, runner=None)

    assert captured['photos'] is None
