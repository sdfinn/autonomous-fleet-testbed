"""Minimal launch: Gazebo + bridge + robot only. NO Nav2, AMCL, or costmaps.
Use this to test diff-drive response directly via cmd_vel.
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
        parameters=[{'robot_description': robot_desc, 'use_sim_time': True}],
        remappings=[('/tf', '/robot_001/tf'), ('/tf_static', '/robot_001/tf_static')],
    )

    gazebo = ExecuteProcess(
        cmd=['gz', 'sim', '-s', '-r', world_path],
        output='screen',
    )

    spawn_robot = TimerAction(
        period=3.0,
        actions=[Node(
            package='ros_gz_sim',
            executable='create',
            arguments=[
                '-name', 'robot_001',
                '-topic', '/robot_description',
                '-x', '-1.276', '-y', '1.2', '-z', '0.15',
                '-Y', '1.5708',
            ],
            output='screen',
        )],
    )

    bridge = TimerAction(
        period=5.0,
        actions=[Node(
            package='ros_gz_bridge',
            executable='parameter_bridge',
            arguments=[
                '/robot_001/cmd_vel@geometry_msgs/msg/Twist]gz.msgs.Twist',
                '/robot_001/odom@nav_msgs/msg/Odometry[gz.msgs.Odometry',
                '/robot_001/scan@sensor_msgs/msg/LaserScan[gz.msgs.LaserScan',
                '/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock',
            ],
            output='screen',
        )],
    )

    return LaunchDescription([
        robot_state_publisher,
        gazebo,
        spawn_robot,
        bridge,
    ])
