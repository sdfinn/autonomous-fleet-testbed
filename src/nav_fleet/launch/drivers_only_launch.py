# src/nav_fleet/launch/drivers_only_launch.py
# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""Real-hardware driver layer ONLY — esp32_driver (odom/imu/cmd_vel) + the lidar and
camera vendor launch files + scan_masker + camera_relay. No EKF, no ball_detector, no
Nav2 — those stay in nav2_only_launch.py (the container), started separately.

Extracted 2026-08-10 out of sensors_only_launch.py (which used to bundle these five
driver nodes together with EKF + ball_detector for the bench smoke test's own
self-contained convenience) so this exact driver set can ALSO be launched bare-metal
by robot_boot.sh AND by the bench smoke test for the real deployed robot, without
duplicating EKF/ball_detector against the copies nav2_only_launch.py already starts
inside the container. See
docs/superpowers/plans/2026-08-10-drivers-bare-metal-boot-fix.md for the full story:
neither robot_boot.sh's ROBOT_MODE=mission container branch nor the smoke test's old
ROBOT_MODE=smoke_test container branch could ever actually reach the real lidar/
camera — the vendor packages were never installed in the Docker image, and were
never meant to be (this project's own docker-brain-unification decision: the driver
layer stays bare-metal, only Nav2/EKF/ball_detector/mission_runner run in the
container).

No use_sim_time argument here at all — this file is ONLY ever invoked in real-
hardware contexts; sim/CI regression never constructs any of these five nodes,
matching how nav2_only_launch.py never launches its own odom/scan/camera source
either.
"""
import pathlib

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PythonExpression
from launch_ros.actions import Node

PKG = pathlib.Path(__file__).parent.parent


def generate_launch_description():
    serial_device_arg = DeclareLaunchArgument(
        'serial_device', default_value='/dev/ttyUSB0',
        description='ESP32 sub-controller serial device — this Jetson uses '
                    '/dev/ttyTHS1 (40-pin header UART), confirmed 2026-08-09/10.',
    )
    serial_baud_arg = DeclareLaunchArgument(
        'serial_baud', default_value='115200',
        description='Confirmed 2026-08-06 against the real ugv_base_general '
                    'firmware source (Serial.begin(115200)) — see '
                    'robot_profiles/jetson_ugv_pt.yaml',
    )
    lidar_launch_file_arg = DeclareLaunchArgument(
        'lidar_launch_file', default_value='',
        description="Absolute path to ldlidar_ros2's own launch file for the "
                    "exact physical model (D500/STL-19P) — this Jetson's real "
                    "path is ~/ros2_drivers_ws/install/ldlidar_ros2/share/"
                    "ldlidar_ros2/launch/ld19.launch.py, confirmed 2026-08-09. "
                    "Left empty = skipped, not a launch error.",
    )
    camera_launch_file_arg = DeclareLaunchArgument(
        'camera_launch_file', default_value='',
        description="Absolute path to depthai-ros's own launch file (OAK-D "
                    "Lite) — this Jetson's real path is /opt/ros/jazzy/share/"
                    "depthai_ros_driver/launch/camera.launch.py, confirmed "
                    "2026-08-09. Left empty = skipped, not a launch error.",
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
    # real hardware 2026-08-10 (see scan_filter.py's module docstring). Also
    # closes the lidar half of the topic-remapping gap (lidar_include below has
    # no remappings at all) as a side effect. Always included alongside
    # lidar_include — harmless with no publisher on 'scan' yet.
    scan_masker = Node(
        package='nav_fleet',
        executable='scan_masker',
        name='scan_masker',
        output='screen',
    )

    # camera_relay: closes the CAMERA half of the same topic-remapping gap
    # (2026-08-10) — depthai-ros's camera.launch.py has no remapping support of
    # its own, so a small relay node republishes its real image_rect topic as
    # /robot_001/camera/image_raw, which ball_detector.py expects. Always
    # included alongside camera_include — harmless with no publisher on
    # image_rect yet.
    camera_relay = Node(
        package='nav_fleet',
        executable='camera_relay',
        name='camera_relay',
        output='screen',
    )

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

    return LaunchDescription([
        serial_device_arg, serial_baud_arg, lidar_launch_file_arg,
        camera_launch_file_arg,
        esp32_driver, lidar_include, camera_include, scan_masker, camera_relay,
    ])
