# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""Pure Python — key_teleop imports rclpy only inside main(), so this runs in stage-1-quality."""
import pytest

from nav_fleet.key_teleop import (
    ANGULAR_SPEED_RPS, KEY_HOLD_TIMEOUT_S, LINEAR_SPEED_MPS, REVERSE_SPEED_MPS, TeleopState,
)


def test_no_key_means_no_motion():
    assert TeleopState().command(now=0.0) == (0.0, 0.0)


@pytest.mark.parametrize('key, expected', [
    ('w', (LINEAR_SPEED_MPS, 0.0)),
    ('s', (-REVERSE_SPEED_MPS, 0.0)),
    ('a', (0.0, ANGULAR_SPEED_RPS)),       # +angular = left
    ('d', (0.0, -ANGULAR_SPEED_RPS)),
    ('W', (LINEAR_SPEED_MPS, 0.0)),        # caps lock must not change behaviour
])
def test_key_maps_to_velocity(key, expected):
    s = TeleopState()
    s.on_key(key, now=10.0)
    assert s.command(now=10.1) == expected


def test_curve_keys_move_forward_and_turn_the_matching_way():
    s = TeleopState()
    s.on_key('q', now=0.0)
    lin, ang = s.command(now=0.0)
    assert lin > 0 and ang > 0
    s.on_key('e', now=0.0)
    lin, ang = s.command(now=0.0)
    assert lin > 0 and ang < 0


def test_releasing_the_key_stops_the_robot_after_the_hold_timeout():
    s = TeleopState()
    s.on_key('w', now=0.0)
    assert s.command(now=KEY_HOLD_TIMEOUT_S - 0.01)[0] > 0
    assert s.command(now=KEY_HOLD_TIMEOUT_S + 0.01) == (0.0, 0.0)


def test_holding_the_key_keeps_it_moving_across_the_terminal_repeat_pause():
    # A terminal sends the first repeat ~0.5 s after the press, then ~30 per second.
    s = TeleopState()
    s.on_key('w', now=0.0)
    assert s.command(now=0.49)[0] > 0          # still moving during the pause
    t = 0.5
    while t < 3.0:
        s.on_key('w', now=t)
        assert s.command(now=t + 0.02)[0] > 0
        t += 0.033


def test_space_stops_immediately():
    s = TeleopState()
    s.on_key('w', now=0.0)
    s.on_key(' ', now=0.1)
    assert s.command(now=0.1) == (0.0, 0.0)


def test_unknown_key_neither_moves_nor_extends_a_running_command():
    s = TeleopState()
    s.on_key('p', now=0.0)
    assert s.command(now=0.0) == (0.0, 0.0)
    s.on_key('w', now=1.0)
    s.on_key('p', now=1.5)                     # leaning on a wrong key must not keep it alive
    assert s.command(now=1.0 + KEY_HOLD_TIMEOUT_S + 0.01) == (0.0, 0.0)


@pytest.mark.parametrize('key', ['x', '\x03', '\x04'])
def test_quit_keys_stop_and_request_exit(key):
    s = TeleopState()
    s.on_key('w', now=0.0)
    s.on_key(key, now=0.1)
    assert s.quit_requested
    assert s.command(now=0.1) == (0.0, 0.0)
