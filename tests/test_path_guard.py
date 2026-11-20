# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""PathGuard: hold the robot for what the lidar sees in its path. No ROS (stage-1 safe).

Geometry reminder: points are in the lidar's frame. The front bumper is 0.0765 m ahead
of the lidar, the rear one 0.1765 m behind it, and the robot is 0.231 m wide.
"""
import numpy as np
import pytest

from nav_fleet.path_guard import BLOCKED, CLEARED, PathGuard, scan_points

FRONT = 0.0765
REAR = -0.1765
FORWARD = 0.3
REVERSE = -0.2


def _wall(x, y_from=-0.5, y_to=0.5, n=40):
    """A wall across the robot's path at lidar-frame x."""
    return np.column_stack((np.full(n, x), np.linspace(y_from, y_to, n)))


def test_open_floor_never_holds():
    guard = PathGuard()
    for i in range(50):
        assert guard.update(_wall(FRONT + 0.71), FORWARD, i * 0.1) == []
    assert not guard.blocked and guard.blocks == 0


def test_something_inside_the_stop_distance_holds_at_once():
    guard = PathGuard(stop_distance_m=0.25)
    assert guard.update(_wall(FRONT + 0.20), FORWARD, 0.0) == [BLOCKED]
    assert guard.blocked
    assert guard.nearest_m == pytest.approx(0.20)


def test_just_outside_the_stop_distance_does_not_hold():
    guard = PathGuard(stop_distance_m=0.25)
    assert guard.update(_wall(FRONT + 0.26), FORWARD, 0.0) == []


def test_the_doorway_does_not_hold():
    """0.75 m door, robot centred: the frames are 0.375 m to each side, far outside the
    box (0.1355 m). 2026-11-19: four clean runs through it, replayed, zero holds."""
    guard = PathGuard()
    frames = np.vstack((_wall(FRONT + 0.10, 0.375, 0.60, 10),
                        _wall(FRONT + 0.10, -0.60, -0.375, 10)))
    assert guard.update(frames, FORWARD, 0.0) == []


def test_an_obstacle_beside_the_robot_is_not_in_the_way():
    guard = PathGuard()
    beside = np.column_stack((np.linspace(-0.1, 0.1, 20), np.full(20, 0.16)))
    assert guard.update(beside, FORWARD, 0.0) == []


def test_an_obstacle_clipping_one_corner_holds():
    guard = PathGuard()
    corner = _wall(FRONT + 0.10, 0.10, 0.40, 30)        # overlaps the left 3.5 cm
    assert guard.update(corner, FORWARD, 0.0) == [BLOCKED]


def test_one_or_two_stray_points_are_not_an_obstacle():
    guard = PathGuard(min_points=3)
    assert guard.update(np.array([[FRONT + 0.1, 0.0], [FRONT + 0.12, 0.01]]), FORWARD, 0.0) == []


def test_turning_on_the_spot_is_not_guarded():
    """Stated limit, pinned: with no forward or reverse speed asked for, no box."""
    guard = PathGuard()
    assert guard.update(_wall(FRONT + 0.05), 0.0, 0.0) == []
    assert guard.in_the_way(_wall(FRONT + 0.05), 0.0) == (0, None)


def test_reversing_checks_behind_not_ahead():
    guard = PathGuard()
    assert guard.update(_wall(FRONT + 0.10), REVERSE, 0.0) == []          # ahead: ignored
    assert guard.update(_wall(REAR - 0.10), REVERSE, 0.1) == [BLOCKED]    # behind: held
    assert guard.nearest_m == pytest.approx(0.10)


def test_driving_forward_ignores_what_is_behind():
    guard = PathGuard()
    assert guard.update(_wall(REAR - 0.05), FORWARD, 0.0) == []


def test_released_only_after_the_way_has_been_clear_for_a_second():
    guard = PathGuard(clear_after_s=1.0)
    guard.update(_wall(FRONT + 0.15), FORWARD, 0.0)
    assert guard.update(_wall(FRONT + 0.15), FORWARD, 0.5) == []          # still there
    assert guard.update(np.empty((0, 2)), FORWARD, 0.6) == []             # just gone
    assert guard.update(np.empty((0, 2)), FORWARD, 1.4) == [] and guard.blocked
    assert guard.update(np.empty((0, 2)), FORWARD, 1.5) == [CLEARED]
    assert not guard.blocked and guard.nearest_m is None


def test_a_flickering_obstacle_does_not_flicker_the_hold():
    guard = PathGuard(clear_after_s=1.0)
    events = []
    for i in range(30):                                   # seen on every third scan
        pts = _wall(FRONT + 0.15) if i % 3 == 0 else np.empty((0, 2))
        events += guard.update(pts, FORWARD, i * 0.1)
    assert events == [BLOCKED] and guard.blocks == 1


def test_nav2_giving_up_and_turning_away_releases_the_hold():
    """Held in front of a wall; Nav2 then asks for a turn on the spot (no box): after
    the usual second, the robot is free to turn."""
    guard = PathGuard(clear_after_s=1.0)
    guard.update(_wall(FRONT + 0.15), FORWARD, 0.0)
    assert guard.update(_wall(FRONT + 0.15), 0.0, 0.5) == []
    assert guard.update(_wall(FRONT + 0.15), 0.0, 1.0) == [CLEARED]


@pytest.mark.parametrize('kwargs', [
    {'stop_distance_m': 0}, {'side_margin_m': -0.01}, {'min_points': 0}, {'clear_after_s': -1}])
def test_nonsense_settings_are_refused(kwargs):
    with pytest.raises(ValueError):
        PathGuard(**kwargs)


def test_scan_points_keeps_near_returns_and_drops_masked_rays():
    ranges = [0.10, float('nan'), 0.30, 20.0, 0.01]       # near, masked, ok, too far, too near
    pts = scan_points(ranges, 0.0, np.pi / 2, 0.02, 12.0)
    assert pts == pytest.approx(np.array([[0.10, 0.0], [-0.30, 0.0]]), abs=1e-9)


def test_a_scan_of_a_box_dead_ahead_holds_end_to_end():
    """From LaserScan fields to a decision: 500 rays, a 20 cm wide box 0.25 m from the
    lidar (0.17 m from the bumper), open room elsewhere."""
    n = 500
    inc = 2 * np.pi / n
    angles = np.arange(n) * inc
    ranges = np.full(n, 3.0)
    ahead = np.abs(np.arctan2(np.sin(angles), np.cos(angles))) < np.arctan2(0.10, 0.25)
    ranges[ahead] = 0.25 / np.cos(angles[ahead])
    guard = PathGuard()
    assert guard.update(scan_points(ranges, 0.0, inc, 0.02, 12.0), FORWARD, 0.0) == [BLOCKED]
    assert guard.nearest_m == pytest.approx(0.25 - FRONT, abs=0.005)
