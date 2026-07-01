# Copyright 2026 Mike
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Launch Gazebo simulation with the ugv_pt robot. Nav2 wired in Session 10.

Path resolution uses pathlib.Path(__file__) instead of get_package_share_directory
because colcon-ament-python is not installed on this system, so AMENT_PREFIX_PATH
is not populated for workspace Python packages. Path(__file__).parent.parent resolves
to share/nav_fleet/ when launched via the installed path, or src/nav_fleet/ when
launched directly — both contain urdf/, worlds/, maps/ after colcon build.
"""
import os
import pathlib

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (DeclareLaunchArgument, ExecuteProcess,
                            IncludeLaunchDescription, TimerAction)
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import Command, LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue

# Resolves to the package share directory regardless of whether the launch file
# is invoked via the installed path or directly from source.
PKG = pathlib.Path(__file__).parent.parent


def generate_launch_description():
    urdf_path = str(PKG / 'urdf' / 'ugv_pt.urdf.xacro')
    world_path = str(PKG / 'worlds' / 'bedroom_simple.sdf')

    headless_arg = DeclareLaunchArgument(
        'headless', default_value='false',
        description='Run Gazebo headless (no GUI) — set true for CI',
    )

    robot_desc = ParameterValue(Command(['xacro ', urdf_path]), value_type=str)

    robot_state_publisher = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        name='robot_state_publisher',
        parameters=[{
            'robot_description': robot_desc,
            'use_sim_time': True,
        }],
        remappings=[
            ('/tf', '/robot_001/tf'),
            ('/tf_static', '/robot_001/tf_static'),
        ],
    )

    # -s = server only (no GUI process). GUI crashes on this machine due to a
    # snap/glibc libpthread conflict; when it dies it takes the server with it.
    # Open a separate viewer with `gz sim -g` if you need visual inspection.
    gazebo = ExecuteProcess(
        cmd=['gz', 'sim', '-s', '-r', world_path],
        output='screen',
    )

    # Wait 3s for Gazebo to load world before spawning robot
    spawn_robot = TimerAction(
        period=3.0,
        actions=[Node(
            package='ros_gz_sim',
            executable='create',
            arguments=[
                '-name', 'robot_001',
                '-topic', '/robot_description',
                '-x', '-1.276', '-y', '1.2', '-z', '0.15',
                '-Y', '1.5708',   # facing North (+Y)
            ],
            output='screen',
        )],
    )

    # Delayed 5 s so gz-transport discovery completes before the bridge
    # subscribes. Starting the bridge before Gazebo publishers are live causes
    # the GZ→ROS subscriptions to silently fail (no reconnect in this version).
    bridge = TimerAction(
        period=5.0,
        actions=[Node(
            package='ros_gz_bridge',
            executable='parameter_bridge',
            arguments=[
                # ] = ROS→GZ only (Nav2 sends velocity commands to Gazebo)
                '/robot_001/cmd_vel@geometry_msgs/msg/Twist]gz.msgs.Twist',
                # [ = GZ→ROS only (Gazebo publishes sensor/state data; ROS reads it)
                '/robot_001/odom@nav_msgs/msg/Odometry[gz.msgs.Odometry',
                '/robot_001/scan@sensor_msgs/msg/LaserScan[gz.msgs.LaserScan',
                '/robot_001/camera/image_raw@sensor_msgs/msg/Image[gz.msgs.Image',
                '/robot_001/tf@tf2_msgs/msg/TFMessage[gz.msgs.Pose_V',
                '/robot_001/imu/data@sensor_msgs/msg/Imu[gz.msgs.IMU',
                '/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock',
            ],
            output='screen',
        )],
    )

    nav2_bringup_dir = get_package_share_directory('nav2_bringup')
    nav2 = TimerAction(
        period=13.0,
        actions=[IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                os.path.join(nav2_bringup_dir, 'launch', 'bringup_launch.py')
            ),
            launch_arguments={
                'namespace': 'robot_001',
                'use_namespace': 'true',
                'use_sim_time': 'true',
                'params_file': str(PKG / 'config' / 'nav2_params.yaml'),
                'map': str(PKG / 'maps' / 'living_room.yaml'),
                'use_composition': 'True',
                'autostart': 'true',
            }.items(),
        )],
    )

    # Gazebo Harmonic names the GPU lidar frame as {model}/{parent_link}/{sensor}
    # = robot_001/base_footprint/lidar, but RSP publishes lidar_link (no prefix).
    # Bridge the two so AMCL can look up scan → base_footprint chain.
    lidar_frame_bridge = Node(
        package='tf2_ros',
        executable='static_transform_publisher',
        name='lidar_frame_bridge',
        arguments=['0', '0', '0', '0', '0', '0',
                   'lidar_link',
                   'robot_001/base_footprint/lidar'],
        parameters=[{'use_sim_time': True}],
        remappings=[
            ('/tf_static', '/robot_001/tf_static'),
        ],
    )

    return LaunchDescription([
        headless_arg,
        robot_state_publisher,
        gazebo,
        spawn_robot,
        bridge,
        lidar_frame_bridge,
        nav2,
    ])
