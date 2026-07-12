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
"""Integration test for the Mission 1 executor. Requires live Gazebo + Nav2
(ros2 launch src/nav_fleet/launch/sim_launch.py). Ignored in stage-1-quality —
imports rclpy at module level, and that runner has no ROS2 (see CLAUDE.md Gotchas)."""
import pathlib

import pytest
import rclpy  # noqa: F401 — module-level import ensures collection fails without ROS2
from PIL import Image as PILImage

from nav_fleet.mission_runner import MissionRunner


@pytest.fixture(scope='session', autouse=True)
def _module_ros(ros_context):
    """Activate the shared session ros_context for this module."""
    yield


@pytest.fixture(scope='session')
def runner(ros_context):
    node = MissionRunner()
    yield node
    node.nav.destroy_node()
    node.destroy_node()


def test_mission1_completes(runner):
    """Mission 1: doorway centre -> photograph -> home. Two Nav2 goals + one capture."""
    assert runner.run_mission('mission1') is True
    assert len(runner.photo_paths) == 1
    photo = pathlib.Path(runner.photo_paths[0])
    assert photo.exists()
    with PILImage.open(photo) as img:
        assert img.size[0] > 0 and img.size[1] > 0
