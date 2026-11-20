# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""obstacle_guard — holds the robot while the lidar sees something in its path.

Bare-metal, in the driver launch (drivers_only_launch.py, obstacle_guard:=true), next
to the lidar and the motor driver it sits between. On every scan it publishes

    /robot_001/obstacle_hold   std_msgs/Bool   True = wheels must not turn

which esp32_driver obeys; started with obstacle_guard_required:=true the driver also
holds whenever this topic goes quiet, so a dead lidar or a dead guard stops the robot
rather than leaving it blind. The decisions are nav_fleet.path_guard.PathGuard; this
file is the wiring. Nav2 is not told anything: see path_guard's docstring for why.

One short low beep when the robot is held (parameter `beep`).
"""
import os
import subprocess
import tempfile
import time

import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node
from sensor_msgs.msg import LaserScan
from std_msgs.msg import Bool

from nav_fleet.operator_link import write_beep_wav
from nav_fleet.path_guard import BLOCKED, CLEARED, PathGuard, scan_points

# A command older than this is not a command any more (Nav2 sends at 20 Hz).
CMD_FRESH_S = 0.3
BLOCKED_BEEP = [(330, 0.25)]


class ObstacleGuard(Node):

    def __init__(self):
        super().__init__('obstacle_guard')
        self.declare_parameter('stop_distance_m', 0.25)
        self.declare_parameter('side_margin_m', 0.02)
        self.declare_parameter('min_points', 3)
        self.declare_parameter('clear_after_s', 1.0)
        self.declare_parameter('beep', True)
        self.declare_parameter('beep_device', 'plughw:CARD=Device,DEV=0')

        self._guard = PathGuard(
            stop_distance_m=self.get_parameter('stop_distance_m').value,
            side_margin_m=self.get_parameter('side_margin_m').value,
            min_points=self.get_parameter('min_points').value,
            clear_after_s=self.get_parameter('clear_after_s').value)
        self._cmd_x = 0.0
        self._cmd_time = 0.0
        self._beep_file = None
        self._beep_failed = False
        if self.get_parameter('beep').value:
            self._beep_file = str(write_beep_wav(
                os.path.join(tempfile.mkdtemp(prefix='obstacle_guard_'), 'blocked.wav'),
                BLOCKED_BEEP))

        self._pub = self.create_publisher(Bool, '/robot_001/obstacle_hold', 10)
        self.create_subscription(Twist, '/robot_001/cmd_vel', self._cmd_cb, 10)
        self.create_subscription(LaserScan, '/robot_001/scan', self._scan_cb, 10)
        self.get_logger().info(
            f'obstacle_guard up — holds for anything within '
            f'{self._guard.stop_distance_m:.2f} m of the bumper, '
            f'{2 * self._guard.half_width_m:.3f} m wide; beeps '
            f'{"on" if self._beep_file else "off"}')

    def _cmd_cb(self, msg):
        self._cmd_x = msg.linear.x
        self._cmd_time = time.monotonic()

    def _scan_cb(self, msg):
        now = time.monotonic()
        linear_x = self._cmd_x if now - self._cmd_time < CMD_FRESH_S else 0.0
        points = scan_points(msg.ranges, msg.angle_min, msg.angle_increment,
                             msg.range_min, msg.range_max)
        events = self._guard.update(points, linear_x, now)
        # Published on EVERY scan, not only on change: the driver reads silence as
        # "the guard or the lidar is gone".
        self._pub.publish(Bool(data=self._guard.blocked))
        for event in events:
            if event == BLOCKED:
                way = 'ahead' if linear_x > 0 else 'behind'
                self.get_logger().warn(
                    f'obstacle_guard: something {self._guard.nearest_m:.2f} m {way} of the '
                    f'bumper — robot HELD')
                self._beep()
            elif event == CLEARED:
                self.get_logger().info('obstacle_guard: path clear — robot RELEASED')

    def _beep(self):
        if self._beep_file is None or self._beep_failed:
            return
        try:
            subprocess.Popen(
                ['aplay', '-q', '-D', self.get_parameter('beep_device').value,
                 self._beep_file],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL)
        except OSError as exc:
            self._beep_failed = True
            self.get_logger().warn(f'obstacle_guard: no beeps — cannot run aplay: {exc}')

    def summary(self):
        return f'obstacle_guard: {self._guard.blocks} hold(s)'


def main(args=None):
    rclpy.init(args=args)
    node = ObstacleGuard()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        print(node.summary(), flush=True)
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
