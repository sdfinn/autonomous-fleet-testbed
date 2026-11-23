# src/nav_fleet/launch/sensors_only_launch.py
# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""Driver layer + EKF (+ the RF-DETR detector on request), for bare-metal bring-up/debugging use
(RealRobotStartup.md A2's own live driver checks) — deliberately WITHOUT Nav2/
AMCL/map_server. No map required, so this runs even before bedroom_real.yaml
exists.

STILL LOAD-BEARING, not dead/superseded code: ci.yml launches this file in EVERY
stage-2-gazebo run (use_sim_time:=true, the default — the real-hardware group
below is skipped entirely in that context). Don't delete this file thinking it's
been fully replaced by drivers_only_launch.py/robot_boot.sh/hil_stage.sh smoke() —
none of those touch stage-2's sim regression at all.

Refactored 2026-08-10: the five driver nodes (esp32_driver/lidar/camera/
scan_masker/camera_relay) moved out to drivers_only_launch.py. NOTE: the bench
smoke test itself (hil_stage.sh smoke) does NOT use this file any more as of
the same day's later revision — it launches drivers_only_launch.py bare-metal
AND nav2_only_launch.py (skip_nav2:=true) in the container separately, to
actually exercise the container boundary. This file remains for convenient
bare-metal-only driver+EKF bring-up/debugging (A2's own live
checks already use it this way). See
docs/superpowers/plans/2026-08-10-drivers-bare-metal-boot-fix.md.

use_sim_time gating: sim/CI regression relies entirely on Gazebo's own bridge
for /robot_001/{odom,imu/data,scan,camera/image_raw} — matching how
nav2_only_launch.py never launches its own odom/scan/camera source either. The
real-hardware driver layer (drivers_only_launch.py) is skipped entirely when
use_sim_time is true.
"""
import pathlib

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, GroupAction, IncludeLaunchDescription
from launch.conditions import IfCondition, UnlessCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

PKG = pathlib.Path(__file__).parent.parent


def generate_launch_description():
    use_sim_time_arg = DeclareLaunchArgument(
        'use_sim_time', default_value='true',
        description='true for sim/CI regression (Gazebo bridge feeds odom/imu/'
                    'scan/camera directly — the real driver layer is skipped '
                    'entirely); false for the real robot bench.',
    )
    # The detector (RF-DETR). false inside the container on the Jetson, where the node
    # runs outside it on the GPU (hil_stage.sh); true on the workstation.
    object_detector_arg = DeclareLaunchArgument(
        'object_detector', default_value='false',
        description='true = start the RF-DETR node (object_detector) here, publishing '
                    '/robot_001/detections',
    )
    detector_model_arg = DeclareLaunchArgument(
        'detector_model',
        default_value=str(pathlib.Path.home() / 'fleet-ci-data' / 'models' / 'rfdetr-small.onnx'),
        description='RF-DETR network file for object_detector',
    )
    detector_config_arg = DeclareLaunchArgument(
        'detector_config', default_value=str(PKG / 'config' / 'detector_rfdetr_gazebo.yaml'),
        description='object_detector settings: detector_rfdetr_gazebo.yaml for the '
                    'simulated camera, detector_rfdetr.yaml for the real one',
    )
    serial_device_arg = DeclareLaunchArgument('serial_device', default_value='/dev/ttyUSB0')
    serial_baud_arg = DeclareLaunchArgument('serial_baud', default_value='115200')
    lidar_launch_file_arg = DeclareLaunchArgument('lidar_launch_file', default_value='')
    camera_launch_file_arg = DeclareLaunchArgument('camera_launch_file', default_value='')

    drivers_include = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(str(PKG / 'launch' / 'drivers_only_launch.py')),
        launch_arguments={
            'serial_device': LaunchConfiguration('serial_device'),
            'serial_baud': LaunchConfiguration('serial_baud'),
            'lidar_launch_file': LaunchConfiguration('lidar_launch_file'),
            'camera_launch_file': LaunchConfiguration('camera_launch_file'),
        }.items(),
    )
    real_hardware_drivers = GroupAction(
        condition=UnlessCondition(LaunchConfiguration('use_sim_time')),
        actions=[drivers_include],
    )

    # Always on, both modes — matches nav2_only_launch.py's own always-on
    # pattern for these two nodes exactly (same params, same remappings).
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
    object_detector = Node(
        package='nav_fleet',
        executable='object_detector',
        name='object_detector',
        output='screen',
        parameters=[{'use_sim_time': LaunchConfiguration('use_sim_time'),
                     'model_path': LaunchConfiguration('detector_model'),
                     'config': LaunchConfiguration('detector_config'),
                     'output_topic': '/robot_001/detections'}],
        condition=IfCondition(LaunchConfiguration('object_detector')),
    )

    return LaunchDescription([
        use_sim_time_arg, object_detector_arg, detector_model_arg, detector_config_arg,
        serial_device_arg, serial_baud_arg,
        lidar_launch_file_arg, camera_launch_file_arg,
        real_hardware_drivers, ekf_node, object_detector,
    ])
