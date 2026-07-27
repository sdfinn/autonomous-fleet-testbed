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
"""Simulation half only: Gazebo + robot spawn + ros_gz bridge + RSP + lidar frame bridge.

No Nav2 — pair with nav2_only_launch.py (same machine, or another machine over DDS for
hardware-in-the-loop; see Mission1HILSession15.md). sim_launch.py composes both for the
classic single-machine run.

Path resolution uses pathlib.Path(__file__) instead of get_package_share_directory
because colcon-ament-python is not installed on this system (see CLAUDE.md's
launch-file gotcha: colcon-ament-python is not installed, so AMENT_PREFIX_PATH is
not populated for workspace Python packages).
"""
import pathlib

from launch import LaunchDescription
from launch.actions import ExecuteProcess, TimerAction
from launch.substitutions import Command
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue

PKG = pathlib.Path(__file__).parent.parent


def generate_launch_description():
    urdf_path = str(PKG / 'urdf' / 'ugv_pt.urdf.xacro')
    world_path = str(PKG / 'worlds' / 'bedroom_simple.sdf')

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
                # NOTE: the Gazebo diff-drive plugin's odom→base_footprint TF is
                # deliberately NOT bridged here anymore (Session 16 Task 9e). That
                # wheel-odom TF over-reports in-place rotation ~30% (measured; see
                # config/ekf.yaml). The robot_localization EKF in nav2_only_launch.py
                # now owns odom→base_footprint by fusing IMU yaw-rate + wheel-odom
                # translation. The plugin's tf_topic is redirected to a dead gz topic
                # in urdf/ugv_pt.urdf.xacro so it can never re-enter /robot_001/tf.
                # The odom MESSAGE above is still bridged — the EKF consumes it.
                '/robot_001/imu/data@sensor_msgs/msg/Imu[gz.msgs.IMU',
                '/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock',
            ],
            output='screen',
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

    # Same Gazebo-Harmonic frame-naming issue as the lidar (Session 16 Task 9e): the IMU
    # sensor publishes /robot_001/imu/data stamped with frame_id
    # robot_001/base_footprint/imu (a Gazebo entity path), which is NOT in RSP's TF tree.
    # The robot_localization EKF must transform the IMU angular velocity into
    # base_footprint; without this the frame lookup fails and every IMU sample is dropped
    # (measured — fused yaw stayed 0 while the body turned ~145°). Zero-offset static TF
    # from imu_link (URDF name) to the Gazebo sensor frame — same physical frame, and the
    # imu_joint is rpy 0 0 0 so no rotation is introduced into the gyro vector.
    imu_frame_bridge = Node(
        package='tf2_ros',
        executable='static_transform_publisher',
        name='imu_frame_bridge',
        arguments=['0', '0', '0', '0', '0', '0',
                   'imu_link',
                   'robot_001/base_footprint/imu'],
        parameters=[{'use_sim_time': True}],
        remappings=[
            ('/tf_static', '/robot_001/tf_static'),
        ],
    )

    return LaunchDescription([
        robot_state_publisher,
        gazebo,
        spawn_robot,
        bridge,
        lidar_frame_bridge,
        imu_frame_bridge,
    ])
