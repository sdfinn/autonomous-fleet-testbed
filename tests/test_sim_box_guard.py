# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""A box in the simulated robot's way: the obstacle guard must hold it short of the box.

Needs live Gazebo + Nav2 started WITH the guard:

    ros2 launch src/nav_fleet/launch/sim_launch.py obstacle_guard:=true

Skipped when no simulator is running at all (tier-1 unit runs); FAILS when a simulator
is running without the guard, because then nothing would be tested and the result
would look like a pass.

What it does: starts the home -> marker leg, and once the robot is moving drops a box
onto the path Nav2 has ALREADY planned (the behaviour tree plans once per goal, so the
box is not planned around: the same situation as the cardboard box of the 2026-11-20
floor test). Then:
  1. the guard reports a hold and the robot stands still,
  2. the robot never touches the box,
  3. with the box taken away the robot carries on and reaches the goal.
"""
import math
import time

import pytest
pytest.importorskip('rclpy', reason='live-ROS tier: needs a ROS2 environment')
import rclpy  # noqa: E402
from geometry_msgs.msg import Twist  # noqa: E402
from nav_msgs.msg import Odometry, Path  # noqa: E402
from std_msgs.msg import Bool  # noqa: E402

from nav_fleet.ground_truth import get_ground_truth_xy  # noqa: E402
from nav_fleet.nav_runner import NavRunner  # noqa: E402
from nav_fleet.path_guard import ROBOT_LENGTH_M, ROBOT_WIDTH_M  # noqa: E402
from nav_fleet.semantic_map import SEMANTIC_MAP  # noqa: E402
from tools import sim_box  # noqa: E402

# Drop the box once the robot has driven this far ...
SPAWN_AFTER_M = 0.30
# ... this far ahead of it along the planned path. Far enough that the lidar has seen
# the new model (headless rendering shows a spawned model up to ~1.5 s late, 0.45 m at
# cruise speed) well before the robot arrives.
BOX_AHEAD_M = 1.30
HOLD_TIMEOUT_S = 40.0
# Furthest any corner of the robot's footprint is from its centre, and of the box's.
ROBOT_REACH_M = math.hypot(ROBOT_LENGTH_M, ROBOT_WIDTH_M) / 2.0
BOX_REACH_M = math.hypot(sim_box.BOX_SIZE_M[0], sim_box.BOX_SIZE_M[1]) / 2.0


@pytest.fixture(scope='module', autouse=True)
def _module_ros(ros_context):
    yield


@pytest.fixture(scope='module')
def nav(ros_context):
    node = NavRunner()
    yield node
    node.destroy_node()


class _Watch:
    """Latest hold state, planned path and commands, on the NavRunner's own node."""

    def __init__(self, node):
        self.hold = None
        self.hold_changes = []          # (time, bool)
        self.plan = None
        # name -> (time, linear, angular) of the newest message: what Nav2 asked for,
        # what reached Gazebo, and what the wheels did. Read only when a run fails.
        self.last = {}
        self._subs = [
            node.create_subscription(
                Twist, '/robot_001/cmd_vel', lambda m: self._twist('nav2 asked', m), 10),
            node.create_subscription(
                Twist, '/robot_001/cmd_vel_wheels',
                lambda m: self._twist('reached gazebo', m), 10),
            node.create_subscription(
                Odometry, '/robot_001/odom',
                lambda m: self._twist('wheels did', m.twist.twist), 10),
            node.create_subscription(Bool, '/robot_001/obstacle_hold', self._hold_cb, 10),
            node.create_subscription(Path, '/robot_001/plan', self._plan_cb, 10),
        ]
        self._node = node

    def _hold_cb(self, msg):
        if msg.data != self.hold:
            self.hold_changes.append((time.time(), msg.data))
        self.hold = msg.data

    def _twist(self, name, twist):
        self.last[name] = (time.time(), twist.linear.x, twist.angular.z)

    def describe(self):
        now = time.time()
        return '; '.join(
            f'{name}: lin {lin:.2f} ang {ang:.2f}, {now - t:.1f} s ago'
            for name, (t, lin, ang) in sorted(self.last.items())) or 'no commands seen'

    def _plan_cb(self, msg):
        self.plan = [(p.pose.position.x, p.pose.position.y) for p in msg.poses]

    def close(self):
        for sub in self._subs:
            self._node.destroy_subscription(sub)


def _point_ahead(plan, xy, ahead_m):
    """The plan point `ahead_m` of path length beyond the plan point nearest `xy`."""
    start = min(range(len(plan)), key=lambda i: math.dist(plan[i], xy))
    travelled = 0.0
    for i in range(start + 1, len(plan)):
        travelled += math.dist(plan[i - 1], plan[i])
        if travelled >= ahead_m:
            return plan[i]
    return None


def test_the_robot_holds_short_of_a_box_and_drives_on_when_it_is_removed(nav):
    if nav.count_publishers('/robot_001/scan') == 0:
        # Discovery can take a moment on a fresh node.
        deadline = time.time() + 3.0
        while time.time() < deadline and nav.count_publishers('/robot_001/scan') == 0:
            rclpy.spin_once(nav, timeout_sec=0.2)
    if nav.count_publishers('/robot_001/scan') == 0:
        pytest.skip('no simulator running (no /robot_001/scan publisher)')
    assert nav.count_publishers('/robot_001/obstacle_hold') > 0, (
        'the simulator is running WITHOUT the obstacle guard: launch it with '
        'obstacle_guard:=true')

    home = SEMANTIC_MAP['home_base']
    goal = SEMANTIC_MAP['sphere_approach']
    start = get_ground_truth_xy()
    assert start is not None, 'no ground truth from Gazebo'
    if math.dist(start, home) > 0.3:
        assert nav.send_goal(*home, yaw=math.pi / 2), 'could not get back to home first'
        start = get_ground_truth_xy()

    watch = _Watch(nav)
    seen = {'phase': 'drive', 'box': None, 'held_at': None, 'held_xy': None,
            'still_xy': None, 'removed_at': None}

    def choreography():
        """Called on every spin of send_goal's loop. Never interrupts the goal."""
        now = time.time()
        if seen['phase'] == 'drive':
            xy = nav._pose_xy()
            if xy is None or watch.plan is None or math.dist(xy, home) < SPAWN_AFTER_M:
                return None
            box = _point_ahead(watch.plan, xy, BOX_AHEAD_M)
            if box is None:
                return None
            sim_box.spawn_box(*box)
            seen.update(phase='approach', box=box, spawned_at=now)
        elif seen['phase'] == 'approach':
            if watch.hold:
                seen.update(phase='held', held_at=now, held_xy=get_ground_truth_xy())
            elif now - seen['spawned_at'] > HOLD_TIMEOUT_S:
                seen['phase'] = 'never_held'
                return 'never_held'                       # cancels the goal
        elif seen['phase'] == 'held' and now - seen['held_at'] >= 3.0:
            seen['still_xy'] = get_ground_truth_xy()
            sim_box.remove_box()
            seen.update(phase='released', removed_at=now)
        return None

    try:
        reached = nav.send_goal(*goal, timeout=150.0, interrupt_cb=choreography)
    finally:
        watch.close()
        if seen['phase'] in ('approach', 'held', 'never_held'):
            sim_box.remove_box()                          # never leave it in the world

    assert seen['box'] is not None, 'the box was never placed (no plan or no pose seen)'
    assert seen['phase'] != 'never_held', (
        f"the guard never held the robot within {HOLD_TIMEOUT_S:.0f} s of a box at "
        f"{seen['box']}")
    assert seen['phase'] == 'released', f"choreography stopped in phase {seen['phase']}"

    # 1. Held, and standing still while held.
    assert seen['held_xy'] is not None and seen['still_xy'] is not None
    crept = math.dist(seen['held_xy'], seen['still_xy'])
    assert crept < 0.05, f'robot moved {crept:.2f} m while held'

    # 2. Short of the box: the footprints cannot overlap at this centre distance,
    #    whatever their headings ...
    gap = math.dist(seen['still_xy'], seen['box'])
    assert gap > ROBOT_REACH_M + BOX_REACH_M, (
        f'robot centre stopped {gap:.2f} m from the box centre; closer than '
        f'{ROBOT_REACH_M + BOX_REACH_M:.2f} m the two footprints can touch')
    #    ... and it did stop FOR the box, not somewhere else on the route.
    assert gap < 0.9, f'robot held {gap:.2f} m from the box: held by something else?'

    # 3. Nav2 was never told: with the box gone the same goal completes.
    assert reached is True, (
        'the leg did not complete after the box was removed: robot really at '
        f'{get_ground_truth_xy()}, believes it is at {nav._pose_xy()}, goal {goal}, '
        f"box was at {seen['box']}, held at {seen['still_xy']}; holds {watch.hold_changes}; "
        f'last seen -- {watch.describe()}')
    assert [state for _t, state in watch.hold_changes if state] == [True], (
        f'expected exactly one hold, saw {watch.hold_changes}')
