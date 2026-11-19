# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""Thin rclpy wrapper around scan_motion.SlipMonitorCore: watches for wheel slip.

Compares, twice a second, how far the wheel encoders say the robot went with how far
the lidar saw the walls move (see scan_motion.py for the method and the 2026-11-17 run
that motivated it). OBSERVES ONLY: it publishes and logs, it does not touch cmd_vel,
the EKF or AMCL. What to DO about slip is a separate, later decision.

Publishes (under the robot namespace by default):
  slip/status        std_msgs/String   idle | ok | suspect | slip | unknown, every window
  slip/lidar_speed   std_msgs/Float32  forward speed from the walls, m/s (NaN = unknown)
  slip/phantom_m     std_msgs/Float32  running total of wheel distance the walls never saw

robot_boot.sh's bag records all three, and tools/slip_replay.py re-runs the same core
over any bag, so live verdicts can always be checked after the fact.

Runs bare-metal with the driver layer (drivers_only_launch.py): it needs only the
scan, wheel odometry and IMU topics, all of which originate there.
"""
import rclpy
from nav_msgs.msg import Odometry
from rclpy.node import Node
from sensor_msgs.msg import Imu, LaserScan
from std_msgs.msg import Float32, String

from nav_fleet.scan_motion import (
    DEFAULT_WINDOW_SCANS, VERDICT_SLIP, SlipMonitorCore,
)

# How far ahead of base_link the lidar sits: ugv_pt.urdf.xacro lidar_joint origin x.
DEFAULT_LIDAR_X_M = 0.05


def _stamp(msg):
    return msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9


class SlipMonitor(Node):

    def __init__(self):
        super().__init__('slip_monitor')
        self.declare_parameter('scan_topic', '/robot_001/scan')
        self.declare_parameter('odom_topic', '/robot_001/odom')
        self.declare_parameter('imu_topic', '/robot_001/imu/data')
        self.declare_parameter('output_prefix', '/robot_001/slip')
        self.declare_parameter('lidar_x_m', DEFAULT_LIDAR_X_M)
        self.declare_parameter('window_scans', DEFAULT_WINDOW_SCANS)

        self.core = SlipMonitorCore(self.get_parameter('lidar_x_m').value,
                                    self.get_parameter('window_scans').value)
        self._slipping = False

        prefix = self.get_parameter('output_prefix').value
        self.status_pub = self.create_publisher(String, f'{prefix}/status', 10)
        self.speed_pub = self.create_publisher(Float32, f'{prefix}/lidar_speed', 10)
        self.phantom_pub = self.create_publisher(Float32, f'{prefix}/phantom_m', 10)

        self.create_subscription(Odometry, self.get_parameter('odom_topic').value,
                                 self._odom_cb, 50)
        self.create_subscription(Imu, self.get_parameter('imu_topic').value, self._imu_cb, 50)
        self.create_subscription(LaserScan, self.get_parameter('scan_topic').value,
                                 self._scan_cb, 10)
        self.get_logger().info(
            f"slip_monitor up — scan {self.get_parameter('scan_topic').value}, "
            f"wheels {self.get_parameter('odom_topic').value}, "
            f"gyro {self.get_parameter('imu_topic').value} -> {prefix}/status (observe only)")

    def _odom_cb(self, msg):
        self.core.add_wheel_speed(_stamp(msg), msg.twist.twist.linear.x)

    def _imu_cb(self, msg):
        self.core.add_yaw_rate(_stamp(msg), msg.angular_velocity.z)

    def _scan_cb(self, msg):
        result = self.core.add_scan(_stamp(msg), msg.ranges, msg.angle_min,
                                    msg.angle_increment, msg.range_min, msg.range_max,
                                    msg.time_increment)
        if result is None:
            return
        self.status_pub.publish(String(data=result.verdict))
        self.speed_pub.publish(Float32(data=float(result.lidar_speed)))
        self.phantom_pub.publish(Float32(data=float(result.phantom_distance_m)))
        # Log only the edges, not every window: one line when slip starts, one when it ends.
        slipping = result.verdict == VERDICT_SLIP
        if slipping and not self._slipping:
            self.get_logger().warning(
                f'WHEEL SLIP: wheels {result.wheel_speed:.2f} m/s, walls '
                f'{result.lidar_speed:.2f} m/s (support {result.forward_support:.0f})')
        elif self._slipping and not slipping:
            self.get_logger().info(
                f'wheel slip ended ({result.verdict}); phantom distance so far '
                f'{result.phantom_distance_m:.2f} m')
        self._slipping = slipping


def main():
    rclpy.init()
    node = SlipMonitor()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
