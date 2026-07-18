"""Unit tests for the cold-start goal-result classifier (Task 13a) — pure Python (stage-1).

No ROS import, so these run on the bare ubuntu-latest stage-1 runner. The retry LOOP that
consumes classify_result lives in nav_fleet.nav_runner.send_goal and is exercised with a
mocked action client in tests/test_nav_runner.py (stage-2) plus the live 6x cold-start proof.
"""
from nav_fleet.goal_retry import (COLD_ABORT_MAX_DISP_M, COLD_ABORT_WINDOW_S,
                                  classify_result)


def test_success_is_success_regardless_of_timing():
    assert classify_result(True, 0.1, 0.0) == 'success'
    assert classify_result(True, 999.0, 5.0) == 'success'


def test_fast_stationary_nonsuccess_is_cold_abort():
    # The exact defect: accepted then aborted in ~0.2 s with the robot not having moved.
    assert classify_result(False, 0.2, 0.001) == 'cold_abort'
    assert classify_result(False, 0.2, 0.0) == 'cold_abort'


def test_unmeasured_displacement_still_retries_when_fast():
    # AMCL had not published a pose yet (cold start) -> displacement None -> still a retry.
    assert classify_result(False, 0.25, None) == 'cold_abort'


def test_slow_nonsuccess_is_a_real_failure():
    # A genuine navigation attempt that fails drives/replans/recovers first — it takes far
    # longer than the window, so it must NOT be retried.
    assert classify_result(False, COLD_ABORT_WINDOW_S + 0.01, 0.0) == 'failure'
    assert classify_result(False, 45.0, None) == 'failure'


def test_moved_then_nonsuccess_is_a_real_failure():
    # The robot actually drove and then failed — not the pre-motion cold abort.
    assert classify_result(False, 0.3, COLD_ABORT_MAX_DISP_M + 0.01) == 'failure'
    assert classify_result(False, 1.0, 1.5) == 'failure'


def test_window_and_disp_edges_are_inclusive():
    assert classify_result(False, COLD_ABORT_WINDOW_S, COLD_ABORT_MAX_DISP_M) == 'cold_abort'
