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


def _all():
    return yaml.safe_load(PARAMS.read_text())


def test_the_planners_costmap_marks_what_the_lidar_sees():
    """2026-11-23. A source's max_obstacle_height defaults to 0.0 in Nav2, which throws
    away every lidar point above the floor. The global costmap's lidar source did not set
    it, so the planner only knew the saved map and every re-planned path went through
    the center of a box the lidar could plainly see."""
    for name in ('global_costmap', 'local_costmap'):
        layer = _all()[name][name]['ros__parameters']['obstacle_layer']
        assert layer['scan']['max_obstacle_height'] >= 0.5, name
    scan = _all()['global_costmap']['global_costmap']['ros__parameters']['obstacle_layer']['scan']
    assert scan['marking'] is True and scan['clearing'] is True


def test_the_behavior_tree_replans_and_recovers_and_the_tree_file_exists():
    bt = _all()['bt_navigator']['ros__parameters']['default_nav_to_pose_bt_xml']
    assert bt.endswith('navigate_to_pose_recovery.xml')
    text = (PARAMS.parent.parent.parent.parent / bt).read_text()
    assert '<RateController' in text and '<ComputePathToPose' in text     # re-planning
    order = [text.index(tag) for tag in ('<BackUp', '<Wait', '<Spin')]
    assert order == sorted(order), 'back away first: a spin swings a corner at the obstacle'
    assert 'ClearEntireCostmap' not in text, 'a cleared box is planned through again'


def test_the_behavior_server_works_in_the_frame_of_the_local_costmap():
    """"Pose Goes Off Grid" = a pose outside the behavior server's copy of the local
    costmap. That is what a frame mismatch looks like, and it kept recovery switched
    off from the summer until 2026-11-23."""
    everything = _all()
    server = everything['behavior_server']['ros__parameters']
    local = everything['local_costmap']['local_costmap']['ros__parameters']
    assert server['local_frame'] == local['global_frame'] == 'odom'
    assert set(server['behavior_plugins']) == {'spin', 'backup', 'wait'}


def test_a_stand_still_ends_in_seconds_and_a_turn_on_the_spot_counts_as_progress():
    """A hold by the obstacle guard looks to Nav2 like no progress. With recoveries on,
    that must end in seconds, not the old 60. And a long turn on the spot must not be
    mistaken for standing still, which the distance-only checker would do."""
    checker = _controller()['progress_checker']
    assert checker['plugin'] == 'nav2_controller::PoseProgressChecker'
    assert checker['movement_time_allowance'] <= 15.0
    assert 0.0 < checker['required_movement_angle'] <= 0.5


def test_the_planning_circle_holds_the_robot_at_any_heading_and_is_not_padded_beyond_need():
    """The robot turns on the spot, so the circle must reach past its corners. Mike
    measured the real robot at about 32 cm corner to corner (0.16 m from the center) and
    set the circle to 38 cm on 2026-11-23. 0.24 (an older, larger model's diagonal) made
    the planner refuse every gap under 0.48 m, including a 0.75 m doorway with a 15 cm
    box against one side."""
    measured_corner_reach_m = 0.16
    for name in ('global_costmap', 'local_costmap'):
        params = _all()[name][name]['ros__parameters']
        assert measured_corner_reach_m + 0.02 <= params['robot_radius'] <= 0.21, name
        assert params['inflation_layer']['inflation_radius'] > params['robot_radius'], name
