"""Launch a minimal Nav2 stack for Isaac Sim — no Gazebo, no ros_gz_bridge.

Isaac Sim publishes:
  /clock                   (sim time)
  /robot_001/odom          (odometry)
  /robot_001/scan          (lidar scan)
  /robot_001/tf            (odom → base_footprint)
  /robot_001/tf_static     (static transforms from RSP)

This launch adds:
  robot_state_publisher    → /robot_001/tf_static (base_footprint → base_link → lidar_link …)
  static map→odom TF       → replaces AMCL (see below)
  map_server, controller_server, planner_server, bt_navigator
  Two lifecycle_managers (map, nav)

Modeled directly on BC/isaac_project's proven-working nav2_min_launch.py. AMCL was replaced
with a static map→odom transform after AMCL produced a false "Goal succeeded" — extended
in-place rotation next to the Dresser (a large, close, flat surface) is a classic scan-matching
divergence trigger for a particle filter; AMCL's estimated pose drifted near the goal while the
physical robot was still stuck at the Dresser. IsaacComputeOdometry reads the articulation's
true physics pose directly, so odom-based tracking has no such divergence risk. Also drops
collision_monitor, behavior_server, smoother_server, velocity_smoother, route_server,
waypoint_follower, and opennav_docking — navigate_simple.xml (see nav2_params.yaml
bt_navigator.default_nav_to_pose_bt_xml) doesn't need any of them, and fewer composed nodes
means fewer places for the composable-node parameter-loading quirks we hit to resurface.
AMCL hardening is tracked as deferred work in Release1Todo.md Session 16+.

Run after isaac_bedroom_gui.py is up and publishing topics.

Usage:
  colcon build --symlink-install && source install/setup.bash
  ros2 launch src/nav_fleet/launch/nav2_isaac_launch.py
"""
import pathlib

from launch import LaunchDescription
from launch.actions import TimerAction
from launch.substitutions import Command
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue

PKG = pathlib.Path(__file__).parent.parent
PARAMS_FILE = str(PKG / 'config' / 'nav2_params.yaml')
MAP_YAML = str(PKG / 'maps' / 'living_room.yaml')

# No ROS namespace on any node below — nav2_params.yaml's top-level keys (controller_server:,
# local_costmap:, etc.) are unqualified, and launch_ros only matches a params_file's top-level
# key to a node's exact name (no implicit namespace handling, unlike nav2_bringup's own
# ReplaceString templating). Namespacing a node here would silently mismatch every key in the
# params file, falling back to compiled-in defaults with no error — exactly what happened on
# the first version of this file (DWBLocalPlanner loaded instead of RPP, "no critics defined").
# The /robot_001/ prefix is applied entirely through explicit absolute remappings instead,
# matching the pattern robot_state_publisher below already used successfully.
TF_REMAPPINGS = [('/tf', '/robot_001/tf'), ('/tf_static', '/robot_001/tf_static')]

# Spawn pose (isaac_bedroom_gui.py SPAWN_X/Y/YAW) = map→odom static transform. Matches the
# amcl.initial_pose values already in nav2_params.yaml exactly — IsaacComputeOdometry zeroes
# odom heading/position at play, so odom's origin coincides with the robot's true map-frame
# spawn pose.
SPAWN_X, SPAWN_Y, SPAWN_YAW = '-1.276', '1.2', '1.5708'


def generate_launch_description():
    urdf_path = str(PKG / 'urdf' / 'ugv_pt.urdf.xacro')
    robot_desc = ParameterValue(Command(['xacro ', urdf_path]), value_type=str)

    # RSP publishes the full TF tree: base_footprint → base_link → lidar_link, etc.
    # Isaac Sim OmniGraph already publishes odom → base_footprint via ROS2PublishRawTransformTree.
    robot_state_publisher = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        name='robot_state_publisher',
        parameters=[{
            'robot_description': robot_desc,
            'use_sim_time': True,
        }],
        remappings=[
            ('/tf',        '/robot_001/tf'),
            ('/tf_static', '/robot_001/tf_static'),
        ],
    )

    # Static map→odom transform — replaces AMCL (see module docstring).
    map_odom_tf = Node(
        package='tf2_ros',
        executable='static_transform_publisher',
        name='map_odom_tf',
        arguments=['--x', SPAWN_X, '--y', SPAWN_Y, '--z', '0',
                   '--yaw', SPAWN_YAW,
                   '--frame-id', 'map', '--child-frame-id', 'odom'],
        remappings=[('/tf_static', '/robot_001/tf_static')],
    )

    map_server = Node(
        package='nav2_map_server',
        executable='map_server',
        name='map_server',
        output='screen',
        parameters=[{'yaml_filename': MAP_YAML, 'use_sim_time': True}],
        remappings=[('map', '/robot_001/map')] + TF_REMAPPINGS,
    )

    controller_server = Node(
        package='nav2_controller',
        executable='controller_server',
        name='controller_server',
        output='screen',
        parameters=[PARAMS_FILE],
        remappings=[('cmd_vel', '/robot_001/cmd_vel')] + TF_REMAPPINGS,
    )

    planner_server = Node(
        package='nav2_planner',
        executable='planner_server',
        name='planner_server',
        output='screen',
        parameters=[PARAMS_FILE],
        remappings=TF_REMAPPINGS,
    )

    bt_navigator = Node(
        package='nav2_bt_navigator',
        executable='bt_navigator',
        name='bt_navigator',
        output='screen',
        parameters=[PARAMS_FILE],
        remappings=[('navigate_to_pose', '/robot_001/navigate_to_pose')] + TF_REMAPPINGS,
    )

    lifecycle_manager_map = Node(
        package='nav2_lifecycle_manager',
        executable='lifecycle_manager',
        name='lifecycle_manager_map',
        output='screen',
        parameters=[{
            'use_sim_time': True,
            'autostart': True,
            'node_names': ['map_server'],
        }],
    )

    lifecycle_manager_navigation = Node(
        package='nav2_lifecycle_manager',
        executable='lifecycle_manager',
        name='lifecycle_manager_navigation',
        output='screen',
        parameters=[{
            'use_sim_time': True,
            'autostart': True,
            'node_names': ['controller_server', 'planner_server', 'bt_navigator'],
        }],
    )

    # Short delay — Isaac Sim is already running by the time this launch starts.
    nav2_nodes = TimerAction(
        period=3.0,
        actions=[
            map_odom_tf,
            map_server,
            controller_server,
            planner_server,
            bt_navigator,
            lifecycle_manager_map,
            lifecycle_manager_navigation,
        ],
    )

    return LaunchDescription([
        robot_state_publisher,
        nav2_nodes,
    ])
