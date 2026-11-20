# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""sim_wheel_hold: the simulator's stand-in for the real driver's wheel hold.

Needs rclpy (a bare context, no Gazebo); skipped where ROS 2 is not installed.
"""
import time

import pytest
pytest.importorskip('rclpy', reason='live-ROS tier: needs a ROS2 environment')
import rclpy  # noqa: E402
from geometry_msgs.msg import Twist  # noqa: E402
from std_msgs.msg import Bool  # noqa: E402

from nav_fleet import hold_input  # noqa: E402
from nav_fleet.sim_wheel_hold import SimWheelHold  # noqa: E402


@pytest.fixture(scope='module', autouse=True)
def ros_context():
    if not rclpy.ok():
        rclpy.init()
    yield
    rclpy.try_shutdown()


@pytest.fixture
def gate():
    node = SimWheelHold()
    sent = []
    node._pub.publish = sent.append          # what would reach Gazebo
    yield node, sent
    node.destroy_node()


def _forward(speed=0.3):
    msg = Twist()
    msg.linear.x = speed
    return msg


def test_commands_pass_straight_through_while_the_guard_says_clear(gate):
    node, sent = gate
    node._hold_cb(Bool(data=False))
    node._cmd_cb(_forward())
    assert sent[-1].linear.x == pytest.approx(0.3)


def test_a_hold_stops_the_wheels_at_once_and_zeroes_every_later_command(gate):
    node, sent = gate
    node._hold_cb(Bool(data=False))
    node._cmd_cb(_forward())
    node._hold_cb(Bool(data=True))
    assert sent[-1].linear.x == 0.0              # stopped by the hold message itself
    node._cmd_cb(_forward())
    assert sent[-1].linear.x == 0.0 and sent[-1].angular.z == 0.0


def test_releasing_the_hold_lets_nav2_carry_on(gate):
    """Nav2 is never told about the hold: the same commands simply get through again."""
    node, sent = gate
    node._hold_cb(Bool(data=True))
    node._cmd_cb(_forward())
    node._hold_cb(Bool(data=False))
    node._cmd_cb(_forward())
    assert sent[-1].linear.x == pytest.approx(0.3)


def test_no_word_from_the_guard_means_no_motion(gate):
    """A mission does not drive blind: a guard that never started holds the robot."""
    node, sent = gate
    node._cmd_cb(_forward())
    assert sent[-1].linear.x == 0.0


def test_a_guard_that_goes_silent_holds_the_robot(gate, monkeypatch):
    node, sent = gate
    node._hold_cb(Bool(data=False))
    node._cmd_cb(_forward())
    assert sent[-1].linear.x == pytest.approx(0.3)
    real_time = time.time
    monkeypatch.setattr('nav_fleet.sim_wheel_hold.time.time',
                        lambda: real_time() + 2 * hold_input.HOLD_STALE_S)
    node._cmd_cb(_forward())
    assert sent[-1].linear.x == 0.0


def test_with_the_guard_optional_silence_means_nothing(gate):
    node, sent = gate
    node.set_parameters([rclpy.parameter.Parameter('obstacle_guard_required', value=False)])
    node._cmd_cb(_forward())
    assert sent[-1].linear.x == pytest.approx(0.3)
