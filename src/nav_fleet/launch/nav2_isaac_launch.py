"""Launch Nav2 stack for Isaac Sim — no Gazebo, no ros_gz_bridge.

Isaac Sim publishes:
  /clock                   (sim time)
  /robot_001/odom          (odometry)
  /robot_001/scan          (lidar scan)
  /robot_001/tf            (odom → base_footprint)
  /robot_001/tf_static     (static transforms from RSP)

This launch adds:
  robot_state_publisher    → /robot_001/tf_static (base_footprint → base_link → lidar_link …)
  Nav2 bringup             → AMCL, planner, controller, BT navigator

Run after isaac_bedroom_gui.py is up and publishing topics.

Usage:
  colcon build --symlink-install && source install/setup.bash
  ros2 launch src/nav_fleet/launch/nav2_isaac_launch.py
"""
import os
import pathlib

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (IncludeLaunchDescription, TimerAction)
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import Command
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue

PKG = pathlib.Path(__file__).parent.parent


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

    nav2_bringup_dir = get_package_share_directory('nav2_bringup')
    nav2 = TimerAction(
        period=3.0,   # short delay — Isaac Sim is already running
        actions=[IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                os.path.join(nav2_bringup_dir, 'launch', 'bringup_launch.py')
            ),
            launch_arguments={
                'namespace':       'robot_001',
                'use_namespace':   'true',
                'use_sim_time':    'true',
                'params_file':     str(PKG / 'config' / 'nav2_params.yaml'),
                'map':             str(PKG / 'maps'   / 'living_room.yaml'),
                'use_composition': 'True',
                'autostart':       'true',
            }.items(),
        )],
    )

    return LaunchDescription([
        robot_state_publisher,
        nav2,
    ])
