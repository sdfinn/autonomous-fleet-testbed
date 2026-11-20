# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""sim_wheel_hold — the simulator's stand-in for the real motor driver's wheel hold.

On the real robot, obstacle_guard publishes /robot_001/obstacle_hold and esp32_driver
obeys it: while the hold is True (or, on a mission, silent) every command becomes a
stop. Gazebo replaces esp32_driver, so in the simulator nothing applied that hold and
no test could put anything in the robot's way.

This node is that one behaviour and nothing else. It sits between Nav2 and Gazebo:

    Nav2 -> /robot_001/cmd_vel -> [sim_wheel_hold] -> /robot_001/cmd_vel_wheels -> Gazebo

and uses the same HoldInput rule as the real driver (nav_fleet.hold_input), so "held",
"released" and "the guard went silent" mean exactly what they mean on the robot. As on
the robot, Nav2 is not told: it keeps commanding and carries on when the hold lifts.

Started by sim_only_launch.py with obstacle_guard:=true, which also points the Gazebo
bridge at /robot_001/cmd_vel_wheels.
"""
import time

import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node
from std_msgs.msg import Bool

from nav_fleet.hold_input import HoldInput


class SimWheelHold(Node):

    def __init__(self):
        super().__init__('sim_wheel_hold')
        # True (the default, as on a real mission): no word from the guard = no motion.
        self.declare_parameter('obstacle_guard_required', True)
        self._hold = HoldInput('/robot_001/obstacle_hold', 'obstacle in the path',
                               'no obstacle guard running')
        self.holds = 0
        self._pub = self.create_publisher(Twist, '/robot_001/cmd_vel_wheels', 10)
        self.create_subscription(Twist, '/robot_001/cmd_vel', self._cmd_cb, 10)
        self.create_subscription(Bool, self._hold.topic, self._hold_cb, 10)
        self.get_logger().info(
            'sim_wheel_hold up — /robot_001/cmd_vel -> /robot_001/cmd_vel_wheels, '
            'zeroed while /robot_001/obstacle_hold says so')

    def _holding(self):
        """True while the wheels are held. Logs each change, like the real driver."""
        held, reason = self._hold.state(
            time.time(), self.get_parameter('obstacle_guard_required').value)
        if held != self._hold.held:
            self._hold.held = held
            if held:
                self.holds += 1
                self.get_logger().warn(f'sim_wheel_hold: wheels HELD — {reason}')
            else:
                self.get_logger().info(
                    f'sim_wheel_hold: hold released — not ({self._hold.when_true})')
        return held

    def _hold_cb(self, msg):
        was_holding = self._holding()
        self._hold.update(msg.data, time.time())
        if not was_holding and self._holding():
            # Do not wait for the next cmd_vel to stop the wheels (the driver's rule).
            self._pub.publish(Twist())

    def _cmd_cb(self, msg):
        self._pub.publish(Twist() if self._holding() else msg)


def main(args=None):
    rclpy.init(args=args)
    node = SimWheelHold()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
