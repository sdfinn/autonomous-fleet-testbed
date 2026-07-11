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
"""Launch the full single-machine stack: Gazebo sim + Nav2 (Session 10 behavior).

Since Session 15 this is a thin composition of sim_only_launch.py (Gazebo, spawn, bridge,
RSP, lidar frame bridge) and nav2_only_launch.py (Nav2 bringup, delayed 13 s) so the two
halves can also run on separate machines for hardware-in-the-loop testing. Behavior and
timing of the single-machine run are unchanged.
"""
import pathlib

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource

LAUNCH_DIR = pathlib.Path(__file__).parent


def generate_launch_description():
    headless_arg = DeclareLaunchArgument(
        'headless', default_value='false',
        description='Run Gazebo headless (no GUI) — set true for CI',
    )

    sim = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(str(LAUNCH_DIR / 'sim_only_launch.py')),
    )
    nav2 = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(str(LAUNCH_DIR / 'nav2_only_launch.py')),
        launch_arguments={'start_delay': '13.0'}.items(),
    )

    return LaunchDescription([
        headless_arg,
        sim,
        nav2,
    ])
