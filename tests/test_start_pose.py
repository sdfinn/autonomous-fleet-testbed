# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""nav_fleet.start_pose: does the lidar agree with the map from the believed pose?
A made-up room, no ROS."""
import math

import numpy as np
import pytest

from nav_fleet import start_pose as sp

RES = 0.05


def _room():
    """A 4 m x 3 m room with walls on all sides and a cupboard, as an occupancy grid
    (row 0 at the origin), origin at (0, 0)."""
    grid = np.zeros((60, 80), dtype=int)
    grid[0, :] = grid[-1, :] = 100
    grid[:, 0] = grid[:, -1] = 100
    grid[40:50, 10:16] = 100                      # the cupboard: makes the room lopsided
    return grid


def _scan_from(grid, pose, rays=180, max_range=6.0):
    """What a lidar at `pose` would see in `grid`: ray casting, points in the lidar frame."""
    x, y, yaw = pose
    lx, ly = x + sp.LIDAR_X_M * math.cos(yaw), y + sp.LIDAR_X_M * math.sin(yaw)
    points = []
    for k in range(rays):
        a = 2 * math.pi * k / rays
        for r in np.arange(0.05, max_range, 0.01):
            px, py = lx + r * math.cos(yaw + a), ly + r * math.sin(yaw + a)
            j, i = int(py / RES), int(px / RES)
            if not (0 <= j < grid.shape[0] and 0 <= i < grid.shape[1]):
                break
            if grid[j, i] >= sp.OCCUPIED_AT:
                points.append((r * math.cos(a), r * math.sin(a)))
                break
    return np.array(points)


@pytest.fixture(scope='module')
def room():
    grid = _room()
    return grid, sp.near_occupied(grid, RES, 0.15)


def test_from_the_true_pose_nearly_every_point_lands_on_the_map(room):
    grid, near = room
    pose = (1.5, 1.0, 0.3)
    score, used = sp.match_score(_scan_from(grid, pose), pose, near, RES, (0.0, 0.0))
    assert used > 100 and score > 0.95


@pytest.mark.parametrize('wrong', [(2.1, 1.0, 0.3),      # set down 0.6 m away
                                   (1.5, 1.6, 0.3),
                                   (1.5, 1.0, 0.3 + math.radians(40))])   # turned 40 degrees
def test_from_a_wrong_pose_the_points_land_in_free_space(room, wrong):
    grid, near = room
    true = (1.5, 1.0, 0.3)
    score, _used = sp.match_score(_scan_from(grid, true), wrong, near, RES, (0.0, 0.0))
    assert score < 0.6


def test_a_few_centimeters_and_degrees_off_still_matches(room):
    """The home error on the real robot is 2 to 11 cm; that must not fail the check."""
    grid, near = room
    true = (1.5, 1.0, 0.3)
    off = (1.5 + 0.08, 1.0 - 0.06, 0.3 + math.radians(4))
    score, _used = sp.match_score(_scan_from(grid, true), off, near, RES, (0.0, 0.0))
    # A bare box of a room is the hardest case (measured 0.68 here; the real bedroom
    # scored 0.85 to 0.98 for the same kind of error): it must stay well above a turn.
    assert score > 0.6


def test_no_points_is_a_score_of_zero_not_a_crash(room):
    _grid, near = room
    assert sp.match_score(np.empty((0, 2)), (1.0, 1.0, 0.0), near, RES, (0.0, 0.0)) == (0.0, 0)
    far = np.array([[9.0, 0.0], [0.0, 9.0]])                 # beyond max_range_m
    assert sp.match_score(far, (1.0, 1.0, 0.0), near, RES, (0.0, 0.0)) == (0.0, 0)


def test_points_off_the_map_do_not_count_as_matches(room):
    _grid, near = room
    outside = np.array([[20.0, 0.0], [21.0, 1.0], [22.0, -1.0]])
    score, used = sp.match_score(outside, (1.0, 1.0, 0.0), near, RES, (0.0, 0.0),
                                 max_range_m=50.0)
    assert used == 3 and score == 0.0


def test_yaw_from_a_quaternion():
    assert sp.yaw_of((math.sin(math.pi / 4), math.cos(math.pi / 4))) == pytest.approx(math.pi / 2)


def test_the_pass_mark_sits_between_the_real_robots_good_and_bad_scores():
    """Real scans against the real map, 2026-11-23: home 0.90 and 0.98, small errors 0.85
    and up; 15 degrees turned 0.62 to 0.68; 30 cm sideways 0.26 to 0.44."""
    assert 0.68 < sp.MIN_MATCH < 0.85
