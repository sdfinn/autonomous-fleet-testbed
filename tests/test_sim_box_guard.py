# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""A box in the simulated robot's way (item B, 2026-11-23).

Needs live Gazebo + Nav2 started WITH the obstacle guard:

    ros2 launch src/nav_fleet/launch/sim_launch.py obstacle_guard:=true

Skipped when no simulator is running at all (tier-1 unit runs); FAILS when a simulator
is running without the guard, because then nothing would be tested and the result
would look like a pass.

Two situations, both with a box dropped onto the path Nav2 has planned and LEFT there:

  1. Open floor. The lidar puts the box into the planner's costmap, the path is planned
     again every second, and the robot drives around it and reaches its goal.
  2. No way around (the funnel between the doorway, a wall and the dresser, where the
     box leaves less than the robot's planning circle on either side). The robot must
     stay clear of the box, the goal must END as failed instead of standing there for
     minutes, and the robot must be able to drive on to another goal afterward.

Until 2026-11-23 this file held one test for a different robot: the plan was made once
per goal and nothing followed an obstacle hold, so the test dropped a box, checked the
guard held the robot, took the box away and checked the robot carried on. The guard's
own behavior is still pinned by tests/test_path_guard.py and tests/test_sim_wheel_hold.py.
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
# ... this far ahead of it along the planned path (home -> sphere_approach is about
# 3.6 m of path). 2.9 m is the middle of the bedroom, open floor on every side. 2.2 m is
# 0.9 m inside the doorway, in the funnel described above. Both are far enough ahead
# that the lidar has seen the new model (headless rendering shows a spawned model up to
# ~1.5 s late, 0.45 m at cruise speed) well before the robot arrives.
BOX_AHEAD_OPEN_M = 2.90
BOX_AHEAD_FUNNEL_M = 2.20
# A goal with no way around must end by itself well inside this. Measured 2026-11-23:
# 40-55 s when the planner finds no path at all, 113 s when the box leaves a marginal
# gap and the robot is held at it again and again (6 tries, each after 10 s without
# progress plus the recovery itself).
NO_WAY_TIMEOUT_S = 240.0
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


def _require_simulator_with_guard(nav):
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


def _drive_with_a_box_left_on_the_path(nav, box_ahead_m, timeout_s):
    """From home toward the marker; once moving, drop a box `box_ahead_m` along the
    planned path and leave it. Returns (reached, seen, watch) with the box REMOVED."""
    home = SEMANTIC_MAP['home_base']
    goal = SEMANTIC_MAP['sphere_approach']
    start = get_ground_truth_xy()
    assert start is not None, 'no ground truth from Gazebo'
    if math.dist(start, home) > 0.3:
        assert nav.send_goal(*home, yaw=math.pi / 2), 'could not get back to home first'

    watch = _Watch(nav)
    seen = {'box': None, 'closest_m': None, 'closest_xy': None, 'last_look': 0.0}

    def choreography():
        """Called on every spin of send_goal's loop. Never interrupts the goal."""
        now = time.time()
        if seen['box'] is None:
            xy = nav._pose_xy()
            if xy is None or watch.plan is None or math.dist(xy, home) < SPAWN_AFTER_M:
                return None
            box = _point_ahead(watch.plan, xy, box_ahead_m)
            if box is not None:
                sim_box.spawn_box(*box)
                seen['box'] = box
        elif now - seen['last_look'] >= 0.3:
            seen['last_look'] = now
            truth = get_ground_truth_xy()
            if truth is not None:
                gap = math.dist(truth, seen['box'])
                if seen['closest_m'] is None or gap < seen['closest_m']:
                    seen['closest_m'], seen['closest_xy'] = gap, truth
        return None

    goal_started = time.time()
    try:
        reached = nav.send_goal(*goal, timeout=timeout_s, interrupt_cb=choreography)
    finally:
        seen['goal_took_s'] = time.time() - goal_started
        watch.close()
        if seen['box'] is not None:
            sim_box.remove_box()                          # never leave it in the world
    assert seen['box'] is not None, 'the box was never placed (no plan or no pose seen)'
    assert seen['closest_m'] is not None, 'the robot was never seen after the box was placed'
    return reached, seen, watch


def _assert_never_touched(seen):
    """The footprints cannot overlap at this centre distance, whatever their headings."""
    assert seen['closest_m'] > ROBOT_REACH_M + BOX_REACH_M, (
        f"robot centre came within {seen['closest_m']:.2f} m of the box centre at "
        f"{seen['closest_xy']} (box {seen['box']}); below "
        f'{ROBOT_REACH_M + BOX_REACH_M:.2f} m the two footprints can touch')


def test_the_robot_drives_around_a_box_in_open_floor(nav):
    _require_simulator_with_guard(nav)
    goal = SEMANTIC_MAP['sphere_approach']
    reached, seen, watch = _drive_with_a_box_left_on_the_path(nav, BOX_AHEAD_OPEN_M, 150.0)

    _assert_never_touched(seen)
    assert reached is True, (
        'the robot did not get around the box: really at '
        f'{get_ground_truth_xy()}, believes it is at {nav._pose_xy()}, goal {goal}, box at '
        f"{seen['box']}, closest {seen['closest_m']:.2f} m; holds {watch.hold_changes}; "
        f'last seen -- {watch.describe()}')
    # It did have to go around: the box was really on the route.
    assert seen['closest_m'] < 1.0, (
        f"the robot never came within 1 m of the box at {seen['box']}: it was not on "
        'the route, so nothing was tested')


def test_a_box_with_no_way_around_ends_the_goal_and_leaves_the_robot_usable(nav):
    _require_simulator_with_guard(nav)
    reached, seen, watch = _drive_with_a_box_left_on_the_path(
        nav, BOX_AHEAD_FUNNEL_M, NO_WAY_TIMEOUT_S)
    took_s = seen['goal_took_s']          # the goal itself, not the drive home before it

    _assert_never_touched(seen)
    assert reached is False, (
        f"the robot reached the goal past a box at {seen['box']} that should leave no way "
        'through for its planning circle: the funnel case is not being tested any more')
    # The goal ended because Nav2 gave up, not because our own wait ran out.
    assert took_s < NO_WAY_TIMEOUT_S - 30.0, (
        f'the goal was still running after {took_s:.0f} s: nothing ended it '
        f'(holds {watch.hold_changes}; last seen -- {watch.describe()})')
    # With the box gone (removed above) the robot is not stuck: it can drive home.
    home = SEMANTIC_MAP['home_base']
    assert nav.send_goal(*home, yaw=math.pi / 2, timeout=120.0), (
        f'after the failed goal the robot could not drive home: really at '
        f'{get_ground_truth_xy()}, believes it is at {nav._pose_xy()}')
