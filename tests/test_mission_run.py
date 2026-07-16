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
import math
import pathlib

import pytest
import rclpy  # noqa: F401 — module-level import ensures collection fails without ROS2
from PIL import Image as PILImage

from nav_fleet.ground_truth import get_ground_truth_xy
from nav_fleet.mission_runner import MissionRunner
from nav_fleet.missions import MISSIONS
from nav_fleet.semantic_map import SEMANTIC_MAP

# Physical arrival tolerance for the ground-truth check: Nav2's xy_goal_tolerance (0.15)
# plus a 0.10 localization-error budget — AMCL steers the robot, so a correctly behaving
# robot can physically stop up to its localization error beyond the believed tolerance.
# The 2026-07-15 false PASS this check exists to catch missed by 0.38 m.
GROUND_TRUTH_TOLERANCE_M = 0.25


@pytest.fixture(scope='session', autouse=True)
def _module_ros(ros_context):
    """Activate the shared session ros_context for this module."""
    yield


@pytest.fixture(scope='session')
def runner(ros_context):
    # No session-scoped costmap-clear fixture: the mission runner now clears both costmaps
    # before every navigate leg (Session 16 leg-3 fix). A fixture that cleared once up front
    # would mask a regression of exactly the per-leg behavior the tests must exercise.
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
    # The goal checker trusts AMCL's belief — verify PHYSICAL arrival against Gazebo
    # ground truth (world coords == map coords: spawn pose == AMCL initial pose).
    # Guards the 2026-07-15 false-PASS mode: wheel slip during an obstacle contact
    # walked the believed pose into tolerance while the robot was wedged at the arch.
    truth = get_ground_truth_xy()
    assert truth is not None, 'no Gazebo ground truth — is the sim up on this host?'
    goal = SEMANTIC_MAP[MISSIONS['mission1'][-1].location]
    miss = math.dist(truth, goal)
    assert miss <= GROUND_TRUTH_TOLERANCE_M, (
        f'false PASS: mission reported success but ground truth {truth} is '
        f'{miss:.2f} m from goal {goal} (tolerance {GROUND_TRUTH_TOLERANCE_M} m)')


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


class _StubNavOk:
    """Mimics NavRunner after a successful goal, with no metric side effects."""
    last_duration_s = None
    last_position_error = None
    last_final_x = 0.0
    last_final_y = 0.0

    def send_goal(self, x, y, timeout=90.0, yaw=None):
        return True


def test_costmaps_cleared_before_each_navigate_leg(runner, monkeypatch):
    """Regression guard for the Session 16 leg-3 fix: the runner must clear costmaps once
    per navigate step so accumulated obstacle marks can't close the marginal hallway arch.
    Fails if the per-leg clear is dropped. mission1 has exactly two navigate steps."""
    calls = []
    monkeypatch.setattr(runner, '_clear_costmaps', lambda *a, **k: calls.append(1))
    monkeypatch.setattr(runner, 'nav', _StubNavOk())
    monkeypatch.setattr(runner, 'take_picture', lambda label: True)
    assert runner.run_mission('mission1') is True
    assert len(calls) == 2


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
