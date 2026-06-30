"""Launch Gazebo simulation with the ugv_pt robot. Nav2 wired in Session 10.

Path resolution uses pathlib.Path(__file__) instead of get_package_share_directory
because colcon-ament-python is not installed on this system, so AMENT_PREFIX_PATH
is not populated for workspace Python packages. Path(__file__).parent.parent resolves
to share/nav_fleet/ when launched via the installed path, or src/nav_fleet/ when
launched directly — both contain urdf/, worlds/, maps/ after colcon build.
"""
import os
import pathlib

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, TimerAction
from launch.substitutions import Command, LaunchConfiguration
from launch_ros.actions import Node

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

    robot_desc = Command(['xacro ', urdf_path])

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

    gazebo = ExecuteProcess(
        cmd=['gz', 'sim', '-r', world_path],
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
                '-x', '-1.276', '-y', '1.09', '-z', '0.15',
                '-Y', '1.5708',  # facing North (+Y) into the room
            ],
            output='screen',
        )],
    )

    bridge = Node(
        package='ros_gz_bridge',
        executable='parameter_bridge',
        arguments=[
            '/robot_001/cmd_vel@geometry_msgs/msg/Twist@gz.msgs.Twist',
            '/robot_001/odom@nav_msgs/msg/Odometry@gz.msgs.Odometry',
            '/robot_001/scan@sensor_msgs/msg/LaserScan@gz.msgs.LaserScan',
            '/robot_001/camera/image_raw@sensor_msgs/msg/Image@gz.msgs.Image',
            '/robot_001/tf@tf2_msgs/msg/TFMessage@gz.msgs.Pose_V',
            '/robot_001/imu/data@sensor_msgs/msg/Imu@gz.msgs.IMU',
            '/clock@rosgraph_msgs/msg/Clock@gz.msgs.Clock',
        ],
        output='screen',
    )

    return LaunchDescription([
        headless_arg,
        robot_state_publisher,
        gazebo,
        spawn_robot,
        bridge,
    ])
