# src/nav_fleet/launch/sensors_only_launch.py
# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""Driver layer + EKF + ball_detector, deliberately WITHOUT Nav2/AMCL/map_server —
the bench smoke test's launch file (design spec §Architecture). No map required, so
this runs even before bedroom_real.yaml exists.

use_sim_time gating: sim/CI regression relies entirely on Gazebo's own bridge for
/robot_001/{odom,imu/data,scan,camera/image_raw} — matching how nav2_only_launch.py
never launches its own odom/scan/camera source either. esp32_driver/ldlidar_ros2/
depthai-ros are real-hardware-only and skipped entirely when use_sim_time is true.
"""
import pathlib

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, GroupAction, IncludeLaunchDescription
from launch.conditions import IfCondition, UnlessCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PythonExpression
from launch_ros.actions import Node

PKG = pathlib.Path(__file__).parent.parent


def generate_launch_description():
    use_sim_time_arg = DeclareLaunchArgument(
        'use_sim_time', default_value='true',
        description='true for sim/CI regression (Gazebo bridge feeds odom/imu/scan/'
                    'camera directly — esp32_driver/ldlidar_ros2/depthai-ros are '
                    'skipped entirely); false for the real robot bench.',
    )
    hsv_config_arg = DeclareLaunchArgument(
        'hsv_config', default_value=str(PKG / 'config' / 'hsv_gazebo.yaml'),
        description='ball_detector HSV thresholds — hsv_gazebo.yaml for sim, '
                    'hsv_realcam.yaml for the real robot bench',
    )
    serial_device_arg = DeclareLaunchArgument(
        'serial_device', default_value='/dev/ttyUSB0',
        description='ESP32 sub-controller serial device — depends on how Mike wires '
                    'the physical connection; real-robot-only, unused when '
                    'use_sim_time is true',
    )
    serial_baud_arg = DeclareLaunchArgument(
        'serial_baud', default_value='115200',
        description='Confirmed 2026-08-06 against the real ugv_base_general firmware '
                    'source (Serial.begin(115200)) — see robot_profiles/jetson_ugv_pt.yaml',
    )
    lidar_launch_file_arg = DeclareLaunchArgument(
        'lidar_launch_file', default_value='',
        description="Absolute path to ldlidar_ros2's own launch file for the exact "
                    "physical model (D500/STL-19P) — NOT pinned by this project yet "
                    "(package not installed as of 2026-08-06). Left empty = skipped "
                    "even in real-hardware mode, until Mike wires this in.",
    )
    camera_launch_file_arg = DeclareLaunchArgument(
        'camera_launch_file', default_value='',
        description="Absolute path to depthai-ros's own launch file (OAK-D Lite) — "
                    "NOT pinned by this project yet. Left empty = skipped even in "
                    "real-hardware mode, until Mike wires this in.",
    )

    esp32_driver = Node(
        package='nav_fleet',
        executable='esp32_driver',
        name='esp32_driver',
        output='screen',
        parameters=[{'serial_device': LaunchConfiguration('serial_device'),
                     'baud': LaunchConfiguration('serial_baud')}],
    )

    # scan_masker: subscribes to ldlidar_ros2's raw 'scan' topic, republishes
    # /robot_001/scan with the pan-tilt mast (46-123deg) and WiFi antenna
    # (268-277deg) self-occlusion sectors NaN'd out — confirmed live against the
    # real hardware 2026-08-10 (see scan_filter.py's module docstring). Also closes
    # the lidar half of this file's own topic-remapping gap (lidar_include above has
    # no remappings at all) as a side effect: Nav2/EKF read /robot_001/scan either
    # way, masked or not. Always included alongside lidar_include (not separately
    # gated on lidar_launch_file) — harmless with no publisher on 'scan' yet.
    scan_masker = Node(
        package='nav_fleet',
        executable='scan_masker',
        name='scan_masker',
        output='screen',
    )

    # camera_relay: closes the CAMERA half of this file's own topic-remapping gap
    # (2026-08-10) — depthai-ros's camera.launch.py has no remapping support of its
    # own (confirmed, same class of gap as the lidar's launch file), so a small
    # relay node republishes its real image_rect topic as /robot_001/camera/
    # image_raw, which ball_detector.py and the bench smoke test both expect.
    # Always included alongside camera_include (not separately gated on
    # camera_launch_file) — harmless with no publisher on image_rect yet.
    camera_relay = Node(
        package='nav_fleet',
        executable='camera_relay',
        name='camera_relay',
        output='screen',
    )

    # Real launch files exist today (verified 2026-08-06) at ldrobotSensorTeam/
    # ldlidar_ros2's launch/{ld06,ld14,ld14p,ld19}.launch.py and luxonis/depthai-ros's
    # jazzy-branch depthai_ros_driver/launch/camera.launch.py — neither is wired to a
    # default path here (see this plan's Global Constraints: exact model/params not
    # yet confirmed against the physical hardware). PythonExpression guards each
    # include so an empty path is simply skipped, not a launch error.
    lidar_include = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(LaunchConfiguration('lidar_launch_file')),
        condition=IfCondition(PythonExpression(
            ["'", LaunchConfiguration('lidar_launch_file'), "' != ''"])),
    )
    camera_include = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(LaunchConfiguration('camera_launch_file')),
        condition=IfCondition(PythonExpression(
            ["'", LaunchConfiguration('camera_launch_file'), "' != ''"])),
    )

    real_hardware_drivers = GroupAction(
        condition=UnlessCondition(LaunchConfiguration('use_sim_time')),
        actions=[esp32_driver, lidar_include, camera_include, scan_masker, camera_relay],
    )

    # Always on, both modes — matches nav2_only_launch.py's own always-on pattern
    # for these two nodes exactly (same params, same remappings).
    ekf_node = Node(
        package='robot_localization',
        executable='ekf_node',
        name='ekf_filter_node',
        output='screen',
        parameters=[str(PKG / 'config' / 'ekf.yaml'),
                    {'use_sim_time': LaunchConfiguration('use_sim_time')}],
        remappings=[
            ('/tf', '/robot_001/tf'),
            ('/tf_static', '/robot_001/tf_static'),
            ('odometry/filtered', '/robot_001/odometry/filtered'),
        ],
    )
    ball_detector = Node(
        package='nav_fleet',
        executable='ball_detector',
        name='ball_detector',
        output='screen',
        parameters=[{'use_sim_time': LaunchConfiguration('use_sim_time'),
                     'hsv_config': LaunchConfiguration('hsv_config')}],
    )

    return LaunchDescription([
        use_sim_time_arg, hsv_config_arg, serial_device_arg, serial_baud_arg,
        lidar_launch_file_arg, camera_launch_file_arg,
        real_hardware_drivers, ekf_node, ball_detector,
    ])
