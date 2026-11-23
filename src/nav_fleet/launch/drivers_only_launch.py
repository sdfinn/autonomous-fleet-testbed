# src/nav_fleet/launch/drivers_only_launch.py
# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""Real-hardware driver layer ONLY — esp32_driver (odom/imu/cmd_vel) + the lidar and
camera vendor launch files + scan_masker + camera_relay. No EKF, no detector, no
Nav2 — those stay in nav2_only_launch.py (the container), started separately.

Extracted 2026-08-10 out of sensors_only_launch.py (which used to bundle these five
driver nodes together with EKF for the bench smoke test's own
self-contained convenience) so this exact driver set can ALSO be launched bare-metal
by robot_boot.sh AND by the bench smoke test for the real deployed robot, without
duplicating EKF against the copies nav2_only_launch.py already starts
inside the container. See
docs/superpowers/plans/2026-08-10-drivers-bare-metal-boot-fix.md for the full story:
neither robot_boot.sh's ROBOT_MODE=mission container branch nor the smoke test's old
ROBOT_MODE=smoke_test container branch could ever actually reach the real lidar/
camera — the vendor packages were never installed in the Docker image, and were
never meant to be (this project's own docker-brain-unification decision: the driver
layer stays bare-metal, only Nav2/EKF/mission_runner run in the
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
from launch.substitutions import Command, LaunchConfiguration, PythonExpression
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue

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
    # Attended runs only (scripts/robot_boot.sh sets it when started over SSH):
    # esp32_driver then holds the wheels unless operator_watch is running and says the
    # operator's machine is reachable. See esp32_driver's parameter of the same name.
    operator_watch_required_arg = DeclareLaunchArgument(
        'operator_watch_required', default_value='false',
        description='true = hold the wheels unless operator_watch reports the operator '
                    'reachable',
    )
    # Missions only (scripts/robot_boot.sh sets it): start obstacle_guard, which holds
    # the wheels while the lidar sees something in the robot's path, and make it
    # mandatory for esp32_driver (no guard or no lidar = no motion). Off by default so
    # the mapping drive can still be steered right up to a wall.
    obstacle_guard_beep_arg = DeclareLaunchArgument(
        'obstacle_guard_beep', default_value='true',
        description='false = obstacle_guard makes no sound when it holds the robot',
    )
    obstacle_guard_arg = DeclareLaunchArgument(
        'obstacle_guard', default_value='false',
        description='true = run obstacle_guard and hold the wheels unless it reports the '
                    'path clear',
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

    # robot_state_publisher: real, previously-undiscovered gap found live, 2026-08-12
    # (bench smoke test AMCL-stall investigation, dug all the way to root cause) --
    # this file NEVER started it, and neither does nav2_only_launch.py or
    # container_entrypoint.sh -- confirmed by grepping the whole real-robot boot
    # chain, zero references anywhere outside the SIM launch files
    # (sim_launch_minimal.py/sim_only_launch.py/nav2_isaac_launch.py). Without it, no
    # process ever publishes the URDF's static sensor-frame transforms (e.g.
    # base_footprint -> the real lidar's own frame_id, "base_laser" per
    # ld19.launch.py, confirmed by reading that file directly) -- AMCL's TF-
    # synchronized scan subscription can NEVER resolve a transform for an incoming
    # scan message with no known path to odom, so it silently buffers/drops every
    # single scan forever without ever invoking its own processing callback (0 laser-
    # related log lines, even at DEBUG level, confirmed live -- not a guess). This
    # silently explains the map->odom deadlock chased across several live tests
    # tonight; never caught in sim/HIL because sim_only_launch.py (the workstation-
    # side Gazebo bridge) DOES start robot_state_publisher, so HIL's TF tree was
    # always complete. Same URDF/remapping pattern as sim_only_launch.py's own
    # already-proven robot_state_publisher -- hardcoded use_sim_time False, matching
    # this file's own real-hardware-only convention (no use_sim_time arg exists here
    # at all, see this file's own module docstring).
    robot_desc = ParameterValue(
        Command(['xacro ', str(PKG / 'urdf' / 'ugv_pt.urdf.xacro')]), value_type=str)
    robot_state_publisher = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        name='robot_state_publisher',
        parameters=[{'robot_description': robot_desc, 'use_sim_time': False}],
        remappings=[
            ('/tf', '/robot_001/tf'),
            ('/tf_static', '/robot_001/tf_static'),
        ],
    )

    esp32_driver = Node(
        package='nav_fleet',
        executable='esp32_driver',
        name='esp32_driver',
        output='screen',
        parameters=[{'serial_device': LaunchConfiguration('serial_device'),
                     'baud': LaunchConfiguration('serial_baud'),
                     'operator_watch_required': ParameterValue(
                         LaunchConfiguration('operator_watch_required'), value_type=bool),
                     'obstacle_guard_required': ParameterValue(
                         LaunchConfiguration('obstacle_guard'), value_type=bool)}],
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

    # slip_monitor (2026-11-18): compares wheel odometry with scan-to-scan motion and
    # publishes /robot_001/slip/status. Observe-only -- it commands nothing. Lives
    # here because scan, wheel odometry and IMU all originate in this driver layer.
    slip_monitor = Node(
        package='nav_fleet',
        executable='slip_monitor',
        name='slip_monitor',
        output='screen',
    )

    obstacle_guard = Node(
        package='nav_fleet',
        executable='obstacle_guard',
        name='obstacle_guard',
        output='screen',
        parameters=[{'beep': ParameterValue(
            LaunchConfiguration('obstacle_guard_beep'), value_type=bool)}],
        condition=IfCondition(LaunchConfiguration('obstacle_guard')),
    )

    # camera_relay: closes the CAMERA half of the same topic-remapping gap
    # (2026-08-10) — depthai-ros's camera.launch.py has no remapping support of
    # its own, so a small relay node republishes its real image_rect topic as
    # /robot_001/camera/image_raw, which the detector expects. Always
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
        serial_device_arg, serial_baud_arg, operator_watch_required_arg,
        obstacle_guard_arg, obstacle_guard_beep_arg,
        lidar_launch_file_arg,
        camera_launch_file_arg,
        robot_state_publisher,
        esp32_driver, lidar_include, camera_include, scan_masker, camera_relay,
        slip_monitor, obstacle_guard,
    ])
