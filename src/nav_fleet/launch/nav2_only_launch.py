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

The 'robot brain' — runs inside the Docker container (docs/superpowers/specs/
2026-08-03-docker-brain-real-robot-hil-unification-design.md), on the same
machine as the sim (via sim_launch.py) for local dev, or on the real Jetson for
both hardware-in-the-loop AND the real robot — the only difference between HIL
and the real robot is the VALUE of the three launch arguments below, never the
file.

start_delay: seconds to wait before starting Nav2. sim_launch.py passes 13.0 (matches
the original single-file timing: world load + bridge up + first sensor data). Default
0.0 — an HIL operator starts this manually only after the sim side is confirmed up.
"""
import os
import pathlib

import yaml
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (DeclareLaunchArgument, GroupAction,
                            IncludeLaunchDescription, OpaqueFunction,
                            SetLaunchConfiguration, TimerAction)
from launch.conditions import UnlessCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

PKG = pathlib.Path(__file__).parent.parent


def _resolve_use_sim_time_in_params(context, *args, **kwargs):
    """nav2_bringup's own bringup_launch.py (confirmed 2026-08-12 by reading its real
    installed source, /opt/ros/jazzy/share/nav2_bringup/launch/bringup_launch.py) calls
    RewrittenYaml with param_rewrites={} -- an EMPTY dict. This ROS2 Jazzy build never
    dynamically injects use_sim_time into params_file at all for composed nodes; the
    'use_sim_time' launch argument only reaches a handful of standalone nodes
    bringup_launch.py starts directly, never AMCL/map_server/controller_server/etc,
    which are all loaded straight from whatever's hardcoded in the params file.

    This silently broke the real robot: nav2_params.yaml hardcodes use_sim_time: true
    (needed for sim/HIL, where it correctly matches what's requested) -- so on the real
    robot, passing use_sim_time:=false had ZERO effect on AMCL/map_server/etc, which
    kept running with use_sim_time=true regardless (confirmed live via `ros2 param get
    /robot_001/amcl use_sim_time` -> True, even with :=false passed). With no /clock
    publisher on real hardware (no Gazebo), a node believing use_sim_time=true has its
    internal clock frozen -- which stalled AMCL's own time-dependent localization-update
    processing: it correctly received a request_nomotion_update call (a simple flag/
    counter, doesn't need clock progression) but never completed the actual update or
    published map->odom, even after several minutes of real wall-clock time. Never
    surfaced in sim/HIL, which always requests use_sim_time=true anyway -- matching the
    hardcoded default by coincidence, so this exact code path was never really exercised
    there.

    Fix: since bringup_launch.py's own rewrite mechanism is a no-op for this key, don't
    depend on it -- rewrite nav2_params.yaml's use_sim_time for every node ourselves,
    to match the ACTUAL resolved launch argument, and hand bringup_launch.py our own
    corrected copy instead of the original static file."""
    use_sim_time_str = LaunchConfiguration('use_sim_time').perform(context)
    use_sim_time_bool = use_sim_time_str.lower() == 'true'

    src_path = PKG / 'config' / 'nav2_params.yaml'
    with open(src_path) as f:
        params = yaml.safe_load(f)

    for node_cfg in params.values():
        if isinstance(node_cfg, dict) and 'ros__parameters' in node_cfg:
            node_cfg['ros__parameters']['use_sim_time'] = use_sim_time_bool

    out_path = f'/tmp/nav2_params_resolved_{os.getpid()}.yaml'
    with open(out_path, 'w') as f:
        yaml.safe_dump(params, f)

    return [SetLaunchConfiguration('resolved_nav2_params_file', out_path)]


def generate_launch_description():
    start_delay_arg = DeclareLaunchArgument(
        'start_delay', default_value='0.0',
        description='Seconds to wait before Nav2 bringup (sim_launch.py uses 13.0)',
    )
    log_level_arg = DeclareLaunchArgument(
        'log_level', default_value='info',
        description='Passed through to nav2_bringup (e.g. debug, to see per-cycle '
                    'controller_server/goal_checker reasoning during a stall diagnosis)',
    )
    # Docker-brain unification (2026-08-03 design): the ONE difference between HIL
    # and the real robot. Defaults preserve today's HIL behavior exactly, so every
    # existing caller (sim_launch.py, hil_stage.sh) that doesn't pass these three
    # is unaffected.
    use_sim_time_arg = DeclareLaunchArgument(
        'use_sim_time', default_value='true',
        description='true for sim/HIL (Gazebo clock), false for the real robot',
    )
    hsv_config_arg = DeclareLaunchArgument(
        'hsv_config', default_value=str(PKG / 'config' / 'hsv_gazebo.yaml'),
        description='ball_detector HSV thresholds — hsv_gazebo.yaml for sim/HIL, '
                    'hsv_realcam.yaml for the real robot',
    )
    map_arg = DeclareLaunchArgument(
        'map', default_value=str(PKG / 'maps' / 'living_room.yaml'),
        description='Nav2 map yaml — living_room.yaml for sim/HIL, bedroom_real.yaml '
                    'for the real robot',
    )
    skip_nav2_arg = DeclareLaunchArgument(
        'skip_nav2', default_value='false',
        description='true skips Nav2/AMCL/map_server bringup entirely — EKF '
                    'and ball_detector still start. Used by the bench smoke '
                    'test to exercise the real container boundary without '
                    'needing a real map to exist yet (RealRobotStartup.md '
                    'A2 runs before A3/A4). Real missions and HIL always use '
                    'the default false.',
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
        parameters=[str(PKG / 'config' / 'ekf.yaml'),
                    {'use_sim_time': LaunchConfiguration('use_sim_time')}],
        remappings=[
            ('/tf', '/robot_001/tf'),
            ('/tf_static', '/robot_001/tf_static'),
            ('odometry/filtered', '/robot_001/odometry/filtered'),
        ],
    )

    # Mission 2 HSV ball detector — always-on with the nav stack (spec §4): lives on the
    # robot side so HIL runs it on the Jetson while camera frames arrive over DDS.
    # mission_runner simply ignores detections during steps with no reactions.
    ball_detector = Node(
        package='nav_fleet',
        executable='ball_detector',
        name='ball_detector',
        output='screen',
        parameters=[{'use_sim_time': LaunchConfiguration('use_sim_time'),
                     'hsv_config': LaunchConfiguration('hsv_config')}],
    )

    # Resolves use_sim_time into our own corrected copy of nav2_params.yaml before
    # bringup_launch.py ever sees it -- see _resolve_use_sim_time_in_params's own
    # docstring for why this is necessary (bringup_launch.py's own rewrite mechanism
    # is a no-op for this key on this ROS2 Jazzy build).
    resolve_params_action = OpaqueFunction(function=_resolve_use_sim_time_in_params)

    nav2_bringup_dir = get_package_share_directory('nav2_bringup')
    nav2 = GroupAction(
        condition=UnlessCondition(LaunchConfiguration('skip_nav2')),
        actions=[TimerAction(
            period=LaunchConfiguration('start_delay'),
            actions=[IncludeLaunchDescription(
                PythonLaunchDescriptionSource(
                    os.path.join(nav2_bringup_dir, 'launch', 'bringup_launch.py')
                ),
                launch_arguments={
                    'namespace': 'robot_001',
                    'use_namespace': 'true',
                    'use_sim_time': LaunchConfiguration('use_sim_time'),
                    'params_file': LaunchConfiguration('resolved_nav2_params_file'),
                    'map': LaunchConfiguration('map'),
                    'use_composition': 'True',
                    'autostart': 'true',
                    # Forwarded, not previously wired (found in second-round review,
                    # 2026-07-26): bringup_launch.py DOES declare its own 'log_level' arg
                    # and applies it via --ros-args --log-level to the composed container
                    # (see nav2_bringup's own bringup_launch.py) — this repo's log_level
                    # arg just never reached it, so `log_level:=debug` was silently a
                    # no-op even though Piece 9's stall investigation depended on real
                    # DEBUG-level Nav2 logging to do its diagnosis.
                    'log_level': LaunchConfiguration('log_level'),
                }.items(),
            )],
        )],
    )

    return LaunchDescription([
        start_delay_arg,
        log_level_arg,
        use_sim_time_arg,
        hsv_config_arg,
        map_arg,
        skip_nav2_arg,
        ekf_node,
        ball_detector,
        resolve_params_action,
        nav2,
    ])
