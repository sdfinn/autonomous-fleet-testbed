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
import sys

import pytest
pytest.importorskip('rclpy', reason='live-ROS tier: needs a ROS2 environment (S17 review CR-23 safety net - a forgotten stage-1 ignore now skips instead of breaking the stage)')
import rclpy  # noqa: F401,E402
from rclpy.logging import LoggingSeverity
from PIL import Image as PILImage

from nav_fleet import mission_runner as mission_runner_module
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
    last_interrupt = None
    last_failure_reason = 'nav_timeout'

    def send_goal(self, x, y, timeout=90.0, yaw=None, interrupt_cb=None, spin_extra=None):
        return False


def test_failed_leg_metrics_excluded(runner, monkeypatch):
    """A failed navigate leg must not feed nav_durations/nav_errors (FAIL-leg policy)."""
    monkeypatch.setattr(runner, 'nav', _StubNav())
    runner.nav_durations.clear()
    runner.nav_errors.clear()
    assert runner.run_mission('mission1') is False
    assert runner.nav_durations == []
    assert runner.nav_errors == []
    assert runner.failure_reason == 'nav_timeout'


def test_take_picture_sets_no_camera_frame_failure_reason(ros_context, monkeypatch):
    # Stub spin_once to a no-op so no callback ever fires, regardless of whether a real
    # camera is publishing in this environment — stage-2-gazebo's live Nav2/Gazebo DOES
    # publish real frames (found 2026-07-21: relying on "no live camera in this sandbox"
    # passed locally but failed in CI once Gazebo was actually up and publishing).
    monkeypatch.setattr(mission_runner_module.rclpy, 'spin_once', lambda *a, **k: None)
    node = MissionRunner()
    try:
        assert node.take_picture('probe', timeout=0.2) is False
        assert node.failure_reason == 'no_camera_frame'
    finally:
        node.nav.destroy_node()
        node.destroy_node()


def test_log_mission_records_crash_failure_reason(monkeypatch):
    """main()'s except-block sets crashed=True when construction/run_mission raises —
    _log_mission must report 'crash', not whatever runner.failure_reason happens to be
    (runner is often None here — the constructor itself is what crashed)."""
    captured = {}
    monkeypatch.setattr(mission_runner_module, 'log_run', lambda **kwargs: captured.update(kwargs))
    mission_runner_module._log_mission('mission1', False, None, crashed=True)
    assert captured['failure_reason'] == 'crash'


def test_logger_level_bridges_from_fleet_log_level_env(ros_context, monkeypatch):
    # Fresh instance, not the shared session `runner` fixture — the env var must be set
    # before construction, and the session fixture may already be built by other tests.
    monkeypatch.setenv('FLEET_LOG_LEVEL', 'DEBUG')
    node = MissionRunner()
    try:
        assert node.get_logger().get_effective_level() == LoggingSeverity.DEBUG
    finally:
        node.nav.destroy_node()
        node.destroy_node()


class _StubNavOk:
    """Mimics NavRunner after a successful goal, with no metric side effects."""
    last_duration_s = None
    last_position_error = None
    last_final_x = 0.0
    last_final_y = 0.0
    last_interrupt = None

    def send_goal(self, x, y, timeout=90.0, yaw=None, interrupt_cb=None, spin_extra=None):
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


def _detection_msg(entries):
    """Fake Detection2DArray via SimpleNamespace — _detection_cb reads attributes only."""
    import types
    dets = []
    for class_id, rng in entries:
        hyp = types.SimpleNamespace(
            hypothesis=types.SimpleNamespace(class_id=class_id),
            pose=types.SimpleNamespace(pose=types.SimpleNamespace(
                position=types.SimpleNamespace(x=rng))))
        dets.append(types.SimpleNamespace(results=[hyp]))
    return types.SimpleNamespace(detections=dets)


def test_detection_cb_triggers_after_consecutive_frames(runner):
    runner._watch = {'reactions': {'red': 'photo_then_stop'}, 'counts': {},
                     'triggered': None}
    for _ in range(2):
        runner._detection_cb(_detection_msg([('red_ball', 0.8)]))
    assert runner._watch['triggered'] is None          # 2 frames < REACTION_FRAMES
    runner._detection_cb(_detection_msg([('red_ball', 0.8)]))
    assert runner._watch['triggered'] == 'red'


def test_detection_cb_gap_resets_count(runner):
    runner._watch = {'reactions': {'red': 'photo_then_stop'}, 'counts': {},
                     'triggered': None}
    runner._detection_cb(_detection_msg([('red_ball', 0.8)]))
    runner._detection_cb(_detection_msg([('red_ball', 0.8)]))
    runner._detection_cb(_detection_msg([]))            # glimpse lost — reset
    runner._detection_cb(_detection_msg([('red_ball', 0.8)]))
    assert runner._watch['triggered'] is None


def test_detection_cb_ignores_far_and_unwatched(runner):
    runner._watch = {'reactions': {'red': 'photo_then_stop'}, 'counts': {},
                     'triggered': None}
    for _ in range(5):
        runner._detection_cb(_detection_msg([('red_ball', 2.5),      # beyond 1.0 m
                                             ('yellow_ball', 0.5)]))  # not watched
    assert runner._watch['triggered'] is None


def test_detection_cb_inactive_outside_reactive_leg(runner):
    runner._watch = None
    runner._detection_cb(_detection_msg([('red_ball', 0.5)]))  # must not raise


def test_reaction_red_stops_and_photographs(runner, monkeypatch):
    """Triggered red: cancel -> photo -> stop; no further navigation; event recorded."""
    goals = []

    class _StubNavInterrupt:
        last_duration_s = None
        last_position_error = None
        last_final_x = 0.0
        last_final_y = 0.0
        last_interrupt = None

        def send_goal(self, x, y, timeout=90.0, yaw=None,
                      interrupt_cb=None, spin_extra=None):
            goals.append((x, y))
            if interrupt_cb is not None:
                runner._watch['triggered'] = 'red'   # simulate the detector firing
                self.last_interrupt = interrupt_cb()
                return False
            return True

    photos = []
    monkeypatch.setattr(runner, 'nav', _StubNavInterrupt())
    monkeypatch.setattr(runner, '_clear_costmaps', lambda *a, **k: None)
    monkeypatch.setattr(runner, 'take_picture', lambda label: photos.append(label) or True)
    import nav_fleet.mission_runner as mr
    monkeypatch.setattr(mr, 'get_ground_truth_xy', lambda *a, **k: (0.0, 2.9))
    runner.reaction_events.clear()
    assert runner.run_mission('mission2') is True
    assert len(goals) == 1                      # no retreat leg on photo_then_stop
    # Option B (Task 13): mission2 takes a home reference photo FIRST, before the
    # reactive navigate leg even starts — so a red stop-in-place still yields two
    # photos, not one.
    assert photos == ['mission2_home_ref', 'mission2_reaction_red']
    assert runner.reaction_events == [
        {'color': 'red', 'reaction': 'photo_then_stop', 'truth_xy': (0.0, 2.9)}]


def test_reaction_yellow_photographs_then_drives_home(runner, monkeypatch):
    goals = []

    class _StubNavYellow:
        last_duration_s = None
        last_position_error = None
        last_final_x = 0.0
        last_final_y = 0.0
        last_interrupt = None

        def send_goal(self, x, y, timeout=90.0, yaw=None,
                      interrupt_cb=None, spin_extra=None):
            goals.append((x, y))
            if interrupt_cb is not None:
                runner._watch['triggered'] = 'yellow'
                self.last_interrupt = interrupt_cb()
                return False
            return True                          # the retreat leg (no interrupt_cb)

    monkeypatch.setattr(runner, 'nav', _StubNavYellow())
    monkeypatch.setattr(runner, '_clear_costmaps', lambda *a, **k: None)
    monkeypatch.setattr(runner, 'take_picture', lambda label: True)
    import nav_fleet.mission_runner as mr
    monkeypatch.setattr(mr, 'get_ground_truth_xy', lambda *a, **k: None)
    runner.reaction_events.clear()
    assert runner.run_mission('mission2') is True
    from nav_fleet.semantic_map import SEMANTIC_MAP
    assert goals[-1] == SEMANTIC_MAP['home_base']
    assert runner.reaction_events[0]['color'] == 'yellow'


def test_mission2_no_trigger_completes_normally(runner, monkeypatch):
    monkeypatch.setattr(runner, 'nav', _StubNavOk())
    monkeypatch.setattr(runner, '_clear_costmaps', lambda *a, **k: None)
    runner.reaction_events.clear()
    assert runner.run_mission('mission2') is True
    assert runner.reaction_events == []


# ── main() --day branch: failure-bag capture (S17 review fix, 2026-07-25) ──────────────────
# Pre-fix, main()'s --day block exited via `raise SystemExit(0)` before ever reaching the
# one-shot path's failure-bag start/snapshot/stop code below it — since HIL only runs via
# --day now, no HIL run could ever produce a failure bag. rclpy.init/try_shutdown and
# MissionRunner are fully stubbed here (no live node needed) so these tests are fast and
# deterministic, independent of the module's session-scoped ros_context fixture.
class _FakeDayLogger:
    def info(self, *a, **k):
        pass


def _fake_leg(ok):
    return {'ok': ok, 't_start': 0, 't_end': 1, 'checklist': [], 'photos': [],
            'reaction_events': []}


def test_day_mode_captures_failure_bag_on_failing_leg(monkeypatch, capsys):
    class _FakeRunner:
        def get_logger(self):
            return _FakeDayLogger()

        def run_mission2_day(self):
            return [_fake_leg(True), _fake_leg(False), _fake_leg(True)]

    monkeypatch.setattr(mission_runner_module, 'MissionRunner', _FakeRunner)
    monkeypatch.setattr(mission_runner_module.rclpy, 'init', lambda *a, **k: None)
    monkeypatch.setattr(mission_runner_module.rclpy, 'try_shutdown', lambda *a, **k: None)

    bag_calls = {'start_scenario': None, 'snapshotted': False, 'stop_keep': None}

    def fake_start(scenario):
        bag_calls['start_scenario'] = scenario
        return ('proc', pathlib.Path('/tmp/fake_bag'))

    def fake_snapshot():
        bag_calls['snapshotted'] = True
        return True

    monkeypatch.setattr(mission_runner_module.failure_bag, 'start', fake_start)
    monkeypatch.setattr(mission_runner_module.failure_bag, 'snapshot', fake_snapshot)
    monkeypatch.setattr(mission_runner_module.failure_bag, 'stop',
                        lambda proc, bag_path, keep: bag_calls.update(stop_keep=keep))
    monkeypatch.setattr(sys, 'argv', ['mission_runner', '--day'])

    with pytest.raises(SystemExit) as exc_info:
        mission_runner_module.main()

    assert exc_info.value.code == 0
    assert bag_calls['start_scenario'] == 'mission2'
    assert bag_calls['snapshotted'] is True
    assert bag_calls['stop_keep'] is True
    assert 'failure bag kept: /tmp/fake_bag' in capsys.readouterr().out


def test_day_mode_skips_failure_bag_when_all_legs_pass(monkeypatch, capsys):
    """A fully-passing day must NOT snapshot — zero disk cost on the common case."""
    class _FakeRunner:
        def get_logger(self):
            return _FakeDayLogger()

        def run_mission2_day(self):
            return [_fake_leg(True), _fake_leg(True), _fake_leg(True)]

    monkeypatch.setattr(mission_runner_module, 'MissionRunner', _FakeRunner)
    monkeypatch.setattr(mission_runner_module.rclpy, 'init', lambda *a, **k: None)
    monkeypatch.setattr(mission_runner_module.rclpy, 'try_shutdown', lambda *a, **k: None)

    bag_calls = {'stop_keep': None}

    def _boom_snapshot():
        raise AssertionError('snapshot must not be called on an all-PASS day')

    monkeypatch.setattr(mission_runner_module.failure_bag, 'start',
                        lambda scenario: ('proc', pathlib.Path('/tmp/fake_bag')))
    monkeypatch.setattr(mission_runner_module.failure_bag, 'snapshot', _boom_snapshot)
    monkeypatch.setattr(mission_runner_module.failure_bag, 'stop',
                        lambda proc, bag_path, keep: bag_calls.update(stop_keep=keep))
    monkeypatch.setattr(sys, 'argv', ['mission_runner', '--day'])

    with pytest.raises(SystemExit) as exc_info:
        mission_runner_module.main()

    assert exc_info.value.code == 0
    assert bag_calls['stop_keep'] is False
    assert 'failure bag kept' not in capsys.readouterr().out


def test_day_mode_captures_failure_bag_and_reraises_on_crash(monkeypatch, capsys):
    """A crash mid-day (run_mission2_day() itself raising) must still snapshot before
    the exception propagates — re-raised, not swallowed, so the process's own
    non-zero exit (--day mode never prints 'Mission mission2:') is exactly what
    JetsonExecutor._log_startup_crash_if_needed reads as a crash."""
    class _FakeRunner:
        def get_logger(self):
            return _FakeDayLogger()

        def run_mission2_day(self):
            raise RuntimeError('boom')

    monkeypatch.setattr(mission_runner_module, 'MissionRunner', _FakeRunner)
    monkeypatch.setattr(mission_runner_module.rclpy, 'init', lambda *a, **k: None)
    monkeypatch.setattr(mission_runner_module.rclpy, 'try_shutdown', lambda *a, **k: None)

    bag_calls = {'snapshotted': False, 'stop_keep': None}

    monkeypatch.setattr(mission_runner_module.failure_bag, 'start',
                        lambda scenario: ('proc', pathlib.Path('/tmp/fake_bag')))
    monkeypatch.setattr(mission_runner_module.failure_bag, 'snapshot',
                        lambda: bag_calls.update(snapshotted=True) or True)
    monkeypatch.setattr(mission_runner_module.failure_bag, 'stop',
                        lambda proc, bag_path, keep: bag_calls.update(stop_keep=keep))
    monkeypatch.setattr(sys, 'argv', ['mission_runner', '--day'])

    with pytest.raises(RuntimeError, match='boom'):
        mission_runner_module.main()

    assert bag_calls['snapshotted'] is True
    assert bag_calls['stop_keep'] is True
    assert 'failure bag kept: /tmp/fake_bag' in capsys.readouterr().out
