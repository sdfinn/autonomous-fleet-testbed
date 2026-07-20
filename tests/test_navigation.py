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
"""Integration tests for Nav2 navigation. Requires live Gazebo + Nav2."""

import os

import pytest
pytest.importorskip('rclpy', reason='live-ROS tier: needs a ROS2 environment (S17 review CR-23 safety net - a forgotten stage-1 ignore now skips instead of breaking the stage)')
import rclpy  # noqa: F401,E402

from nav_fleet.nav_runner import NavRunner
from nav_fleet.metrics_collector import MetricsCollector
from tools.telemetry_logger import log_run


@pytest.fixture(scope='session', autouse=True)
def _module_ros(ros_context):
    """Activate the shared session ros_context for this module."""
    yield


@pytest.fixture(scope='session')
def nav_runner(ros_context):
    node = NavRunner()
    yield node
    node.destroy_node()


@pytest.fixture(scope='session')
def metrics(ros_context):
    node = MetricsCollector()
    yield node
    node.destroy_node()


@pytest.fixture(scope='session', autouse=True)
def telemetry_run(nav_runner, metrics):
    """Logs one `runs` row for this pytest session — combines the nav result,
    position error, and duration from NavRunner with the collision/Hz metrics
    from MetricsCollector. Runs after all tests in the session (pass or fail).

    SIM_ENGINE / ROBOT_ID let the same test log correctly from stage-3-gazebo,
    stage-4-isaac, and (Session 15+) a real robot / additional fleet members.
    """
    yield
    m = metrics.last_metrics or {}
    log_run(
        scenario='bedroom_nav',
        steps=max(nav_runner.last_steps or 0, 1),
        final_x=nav_runner.last_final_x if nav_runner.last_final_x is not None else 0.0,
        final_y=nav_runner.last_final_y if nav_runner.last_final_y is not None else 0.0,
        result='PASS' if nav_runner.last_result else 'FAIL',
        step_log=[],
        robot_id=os.environ.get('ROBOT_ID', 'robot_001'),
        robot_type='jetson_ugv_pt',
        runner_type='local',
        sim_engine=os.environ.get('SIM_ENGINE', 'gazebo'),
        nav_success_rate=1.0 if nav_runner.last_result else 0.0,
        mean_position_error=nav_runner.last_position_error,
        mean_time_to_goal=nav_runner.last_duration_s,
        collision_rate=1.0 if m.get('collision_detected') else 0.0,
        odom_hz_mean=m.get('odom_hz'),
        lidar_hz_mean=m.get('scan_hz'),
        camera_hz_mean=m.get('camera_hz'),
    )


def test_navigation_succeeds(nav_runner):
    """BR-01: robot reaches bedroom goal from outer hallway doorway within timeout.

    Spawn: (-1.276, 1.2) facing north. Goal: (0.0, 3.7) bedroom floor centre.
    SMAC planner routes NNE (~27° heading error). RPP rotate-to-heading threshold
    is 17° so robot rotates ~27° CW before driving northeast through the corridor
    and bedroom doorway to the green sphere.
    """
    result = nav_runner.send_goal(0.0, 3.7, timeout=90.0)
    assert result is True


def test_no_collision(metrics):
    """BR-02: no collision detected during navigation."""
    m = metrics.collect(duration=10.0)
    assert m['collision_detected'] is False


def test_topic_hz(metrics):
    """BR-10: odometry >= 45 Hz, scan >= 9 Hz."""
    m = metrics.collect(duration=5.0)
    assert m['odom_hz'] >= 45.0
    assert m['scan_hz'] >= 9.0
