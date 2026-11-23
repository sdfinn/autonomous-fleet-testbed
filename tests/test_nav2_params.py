# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""Settings in nav2_params.yaml that a failure taught us, pinned so that a tidy-up
cannot quietly undo them. Each test says what happened without the setting. Plain YAML:
no ROS, no simulator."""
import pathlib

import yaml

PARAMS = pathlib.Path(__file__).resolve().parent.parent / 'src/nav_fleet/config/nav2_params.yaml'


def _controller():
    return yaml.safe_load(PARAMS.read_text())['controller_server']['ros__parameters']


def test_the_path_follower_does_not_latch_position_reached():
    """2026-11-23. With FollowPath.stateful at its default (true) the follower latched
    "position reached" at 0.144 m from the goal (circle 0.150), the robot then sat at
    0.163 m, the goal checker never saw it inside, and the goal died 60 s later with
    "Failed to make progress". 6 of 14 first drives without a display; 0 of 13 with
    false. The goal checker keeps the latch instead."""
    controller = _controller()
    assert controller['FollowPath']['stateful'] is False
    assert controller['goal_checker']['stateful'] is True


def test_the_follower_and_the_goal_checker_agree_on_the_goal_circle():
    """The follower takes its own "reached" distance from the goal checker. If someone
    adds a separate tolerance to the follower, the two can disagree again."""
    controller = _controller()
    assert 'xy_goal_tolerance' in controller['goal_checker']
    assert 'goal_dist_tol' not in controller['FollowPath']
