"""Retry-loop integration tests for NavRunner.send_goal with a MOCKED action client
(Task 13a). No live Nav2 — the fake action client drives the accept/await outcomes directly,
so this verifies the cold-start-abort retry loop wiring end to end.

Imports rclpy at module level (NavRunner is a rclpy Node), so this is --ignored in
stage-1-quality and runs in stage-2-gazebo where ROS2 is available (see CLAUDE.md Gotchas).
The pure classification logic is unit-tested separately in tests/test_goal_retry.py (stage-1).
"""
from types import SimpleNamespace

import pytest
import rclpy  # noqa: F401 — module-level import ensures collection fails without ROS2

from nav_fleet.goal_retry import COLD_ABORT_RETRIES
from nav_fleet.nav_runner import NavRunner

SUCCEEDED = 4
ABORTED = 6


@pytest.fixture(scope='module')
def _ros():
    if not rclpy.ok():
        rclpy.init()
    yield
    rclpy.try_shutdown()


class _FakeFuture:
    def __init__(self, value, done=True):
        self._value = value
        self._done = done

    def done(self):
        return self._done

    def result(self):
        return self._value


class _FakeGoalHandle:
    def __init__(self, accepted=True, status=SUCCEEDED, result_done=True):
        self.accepted = accepted
        self._status = status
        self._result_done = result_done

    def get_result_async(self):
        return _FakeFuture(SimpleNamespace(status=self._status), done=self._result_done)

    def cancel_goal_async(self):
        return _FakeFuture(None)


class _FakeActionClient:
    """Returns one queued goal handle per send_goal_async call (= one accepted attempt)."""

    def __init__(self, handles):
        self._handles = list(handles)
        self.send_calls = 0

    def wait_for_server(self, timeout_sec=None):
        return True

    def send_goal_async(self, goal):
        self.send_calls += 1
        return _FakeFuture(self._handles.pop(0))


def _make_runner(_ros, handles, pose_seq):
    node = NavRunner()
    node._action_client = _FakeActionClient(handles)
    # _pose_xy is called twice per attempt (accept, then result) — drive displacement
    # deterministically instead of relying on a live AMCL topic.
    node._pose_xy = lambda seq=iter(pose_seq): next(seq)
    return node


def test_cold_abort_then_success_retries_and_passes(_ros):
    # attempt 1: aborted, stationary -> cold_abort -> retry; attempt 2: succeeded.
    node = _make_runner(_ros,
                        handles=[_FakeGoalHandle(status=ABORTED),
                                 _FakeGoalHandle(status=SUCCEEDED)],
                        pose_seq=[(0.0, 0.0), (0.0, 0.0), (0.0, 0.0), (0.0, 0.0)])
    try:
        assert node.send_goal(1.0, 1.0, timeout=5.0) is True
        assert node._action_client.send_calls == 2
    finally:
        node.destroy_node()


def test_persistent_cold_abort_fails_after_bounded_retries(_ros):
    handles = [_FakeGoalHandle(status=ABORTED) for _ in range(COLD_ABORT_RETRIES + 1)]
    node = _make_runner(_ros, handles=handles,
                        pose_seq=[(0.0, 0.0)] * (2 * (COLD_ABORT_RETRIES + 1)))
    try:
        assert node.send_goal(1.0, 1.0, timeout=5.0) is False
        assert node._action_client.send_calls == COLD_ABORT_RETRIES + 1
    finally:
        node.destroy_node()


def test_immediate_success_does_not_retry(_ros):
    node = _make_runner(_ros, handles=[_FakeGoalHandle(status=SUCCEEDED)],
                        pose_seq=[(0.0, 0.0), (0.0, 0.0)])
    try:
        assert node.send_goal(1.0, 1.0, timeout=5.0) is True
        assert node._action_client.send_calls == 1
    finally:
        node.destroy_node()


def test_real_failure_after_moving_is_not_retried(_ros):
    # Non-success but the robot actually drove (displacement 1.0 m) -> real failure, no retry.
    node = _make_runner(_ros, handles=[_FakeGoalHandle(status=ABORTED)],
                        pose_seq=[(0.0, 0.0), (1.0, 0.0)])
    try:
        assert node.send_goal(1.0, 1.0, timeout=5.0) is False
        assert node._action_client.send_calls == 1
    finally:
        node.destroy_node()


def test_interrupt_is_terminal_and_not_retried(_ros):
    # Result never completes; interrupt_cb fires -> cancel + terminal, no cold-abort retry.
    node = _make_runner(_ros,
                        handles=[_FakeGoalHandle(status=ABORTED, result_done=False)],
                        pose_seq=[(0.0, 0.0), (0.0, 0.0)])
    try:
        assert node.send_goal(1.0, 1.0, timeout=2.0,
                              interrupt_cb=lambda: 'red') is False
        assert node._action_client.send_calls == 1
        assert node.last_interrupt == 'red'
    finally:
        node.destroy_node()
