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
TURN_RATE = 0.5


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


def test_a_robot_that_is_not_asked_to_move_is_not_held_for_what_is_near_it():
    """Standing next to something is not a reason to hold: nothing is being asked for."""
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


def test_nav2_giving_up_and_turning_away_releases_the_hold_when_there_is_room_to_turn():
    """Held 0.15 m short of a wall; Nav2 then asks for a turn on the spot. The wall is
    outside the circle the corners sweep, so after the usual second the robot may turn."""
    guard = PathGuard(clear_after_s=1.0)
    guard.update(_wall(FRONT + 0.15), FORWARD, 0.0)
    assert guard.update(_wall(FRONT + 0.15), 0.0, 0.5, angular_z=TURN_RATE) == []
    assert guard.update(_wall(FRONT + 0.15), 0.0, 1.0, angular_z=TURN_RATE) == [CLEARED]


# --- 2026-11-23: the floor run in which the robot inched into a box, then turned into it ---
def test_a_pause_in_the_commands_does_not_release_a_hold():
    """Nav2 stopped asking for speed while it tried a recovery. The hold used to be
    released a second later with the box still there, and the next forward command
    moved the robot a few centimeters before it was caught again: 4 cm, 4, 1, 0."""
    guard = PathGuard(clear_after_s=1.0)
    box = _wall(FRONT + 0.04)
    assert guard.update(box, FORWARD, 0.0) == [BLOCKED]
    for i in range(1, 80):                                # 8 s with nothing asked for
        assert guard.update(box, 0.0, i * 0.1) == []
        assert guard.blocked, f'released after {i * 0.1:.1f} s with the box still there'
    # Nav2 asks to drive on: the robot is ALREADY held, so it cannot creep.
    assert guard.update(box, FORWARD, 8.0) == [] and guard.blocked
    assert guard.blocks == 1


def test_a_hold_that_survived_a_pause_ends_when_the_box_is_taken_away():
    guard = PathGuard(clear_after_s=1.0)
    guard.update(_wall(FRONT + 0.04), FORWARD, 0.0)
    assert guard.update(np.empty((0, 2)), 0.0, 0.5) == []          # gone, nothing asked
    assert guard.update(np.empty((0, 2)), 0.0, 1.5) == [CLEARED]


def test_a_turn_on_the_spot_is_held_when_a_corner_would_hit():
    """0.04 m ahead of the bumper is INSIDE the circle the corners sweep (0.171 m from
    the center; the bumper is 0.1265 m from it). That is how the robot hit the box."""
    guard = PathGuard()
    box = _wall(FRONT + 0.04, y_from=-0.1, y_to=0.1)
    assert guard.update(box, 0.0, 0.0, angular_z=TURN_RATE) == [BLOCKED]
    assert guard.zone == 'turn'
    assert guard.update(box, 0.0, 0.1, angular_z=-TURN_RATE) == [] and guard.blocked


def test_a_turn_on_the_spot_is_free_with_room_all_round():
    guard = PathGuard()
    # A doorway 0.75 m wide: its edges are 0.375 m to either side of the center.
    jambs = np.array([[x, y] for x in (-0.2, -0.05, 0.1) for y in (-0.375, 0.375)])
    assert guard.update(jambs, 0.0, 0.0, angular_z=TURN_RATE) == []
    # Something a full stop-distance ahead of the bumper does not stop a turn either.
    assert guard.update(_wall(FRONT + 0.25, y_from=-0.1, y_to=0.1), 0.0, 0.1,
                        angular_z=TURN_RATE) == []


def test_the_robots_own_parts_in_the_scan_do_not_hold_a_turn():
    """The real lidar returns points 0.03 m from the robot's center on every scan: the
    robot itself. Replaying the clean floor run of 2026-11-23 through the first version
    of the turn rule gave 11 holds with nothing near the robot."""
    guard = PathGuard()
    own = np.array([[-0.05 + dx, dy] for dx in (-0.03, 0.0, 0.03, 0.10) for dy in (-0.03, 0.03, 0.10)])
    for i in range(20):
        assert guard.update(own, 0.0, i * 0.1, angular_z=TURN_RATE) == []
    # ... while something just OUTSIDE the outline, inside the swept circle, still holds.
    beside = np.array([[-0.05 + 0.02 * k, 0.14] for k in range(-2, 3)])
    assert guard.update(np.vstack((own, beside)), 0.0, 2.1, angular_z=TURN_RATE) == [BLOCKED]


def test_held_ahead_the_robot_may_still_back_away():
    """Something 0.04 m ahead blocks driving on and blocks turning, but the rear is
    empty: a reverse command frees the robot after the usual second."""
    guard = PathGuard(clear_after_s=1.0)
    box = _wall(FRONT + 0.04, y_from=-0.1, y_to=0.1)
    assert guard.update(box, FORWARD, 0.0) == [BLOCKED]
    assert guard.update(box, 0.0, 0.5, angular_z=TURN_RATE) == [] and guard.zone == 'turn'
    assert guard.update(box, REVERSE, 1.0) == [] and guard.blocked     # last seen at 0.5
    assert guard.update(box, REVERSE, 1.6) == [CLEARED]


def test_the_turn_margin_is_a_setting_and_cannot_be_negative():
    assert PathGuard(turn_margin_m=0.10).turn_reach_m == pytest.approx(0.171 + 0.10, abs=0.001)
    with pytest.raises(ValueError):
        PathGuard(turn_margin_m=-0.01)


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
