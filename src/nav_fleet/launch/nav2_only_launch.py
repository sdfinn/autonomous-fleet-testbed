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
"""Nav2 half only: nav2_bringup with this project's map/params, no simulator.

The 'robot brain' — runs on the same machine as the sim (via sim_launch.py) or on the
real Jetson for hardware-in-the-loop, where /clock, /robot_001/tf, scan, odom etc. all
arrive over DDS from the sim machine (see Mission1HILSession15.md).

start_delay: seconds to wait before starting Nav2. sim_launch.py passes 13.0 (matches
the original single-file timing: world load + bridge up + first sensor data). Default
0.0 — an HIL operator starts this manually only after the sim side is confirmed up.
"""
import os
import pathlib

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (DeclareLaunchArgument, IncludeLaunchDescription,
                            TimerAction)
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

PKG = pathlib.Path(__file__).parent.parent


def generate_launch_description():
    start_delay_arg = DeclareLaunchArgument(
        'start_delay', default_value='0.0',
        description='Seconds to wait before Nav2 bringup (sim_launch.py uses 13.0)',
    )

    # robot_localization EKF — fuses IMU yaw-rate + wheel-odom translation and owns the
    # odom→base_footprint transform (Session 16 Task 9e; see config/ekf.yaml for the
    # measured ~30% wheel-odom rotation over-report this fixes). This lives on the robot
    # side (nav2_only) because odometry fusion belongs on the robot: in HIL it runs on the
    # Jetson while /robot_001/odom, /robot_001/imu/data and RSP's TF arrive over DDS.
    # Started with no delay so it is already publishing odom→base_footprint before Nav2
    # comes up at start_delay; it simply waits for the first odom/imu message.
    # NOT namespaced — per-robot isolation is applied purely via explicit absolute
    # remappings (a namespaced node's params silently fall through to defaults, a
    # documented failure in CLAUDE.md). /tf + /tf_static → /robot_001/*; filtered output
    # → /robot_001/odometry/filtered (what Nav2's odom_topic now points at).
    ekf_node = Node(
        package='robot_localization',
        executable='ekf_node',
        name='ekf_filter_node',
        output='screen',
        parameters=[str(PKG / 'config' / 'ekf.yaml'), {'use_sim_time': True}],
        remappings=[
            ('/tf', '/robot_001/tf'),
            ('/tf_static', '/robot_001/tf_static'),
            ('odometry/filtered', '/robot_001/odometry/filtered'),
        ],
    )

    nav2_bringup_dir = get_package_share_directory('nav2_bringup')
    nav2 = TimerAction(
        period=LaunchConfiguration('start_delay'),
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

    return LaunchDescription([
        start_delay_arg,
        ekf_node,
        nav2,
    ])
