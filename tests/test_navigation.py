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

import pytest
import rclpy

from nav_fleet.nav_runner import NavRunner
from nav_fleet.metrics_collector import MetricsCollector


@pytest.fixture(scope='session', autouse=True)
def ros_context():
    rclpy.init()
    yield
    rclpy.shutdown()


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
