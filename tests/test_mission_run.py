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
def _clear_costmaps(ros_context):
    """test_navigation's driving leaves accumulated obstacle marks in Nav2's costmaps;
    clear them so the mission plans against the static map + live scan only
    (Session 16 Task 4: combined-invocation return leg failed to plan otherwise)."""
    from rclpy.node import Node
    from nav2_msgs.srv import ClearEntireCostmap
    node = Node('costmap_clearer')
    try:
        for srv in ('/robot_001/global_costmap/clear_entirely_global_costmap',
                    '/robot_001/local_costmap/clear_entirely_local_costmap'):
            client = node.create_client(ClearEntireCostmap, srv)
            assert client.wait_for_service(timeout_sec=10.0), f'{srv} unavailable'
            fut = client.call_async(ClearEntireCostmap.Request())
            rclpy.spin_until_future_complete(node, fut, timeout_sec=10.0)
            assert fut.done(), f'{srv} call did not complete'
    finally:
        node.destroy_node()


@pytest.fixture(scope='session')
def runner(ros_context, _clear_costmaps):
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


class _StubNav:
    """Mimics NavRunner's metric attributes after a timed-out (failed) goal."""
    last_duration_s = 90.0        # the timeout value, not robot performance
    last_position_error = 3.2
    last_final_x = 0.0
    last_final_y = 0.0

    def send_goal(self, x, y, timeout=90.0, yaw=None):
        return False


def test_failed_leg_metrics_excluded(runner, monkeypatch):
    """A failed navigate leg must not feed nav_durations/nav_errors (FAIL-leg policy)."""
    monkeypatch.setattr(runner, 'nav', _StubNav())
    runner.nav_durations.clear()
    runner.nav_errors.clear()
    assert runner.run_mission('mission1') is False
    assert runner.nav_durations == []
    assert runner.nav_errors == []


def test_log_mission_tolerates_none_runner(monkeypatch):
    """Constructor crash path: _log_mission(runner=None) must still log a FAIL row."""
    from nav_fleet import mission_runner as mr
    recorded = {}
    monkeypatch.setattr(mr, 'log_run', lambda **kw: recorded.update(kw))
    mr._log_mission('mission1', False, None)
    assert recorded['result'] == 'FAIL'
    assert recorded['scenario'] == 'mission1'
    assert recorded['final_x'] == 0.0 and recorded['final_y'] == 0.0
    assert recorded['mean_time_to_goal'] is None
