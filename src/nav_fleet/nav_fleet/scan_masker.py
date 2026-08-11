# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""Thin rclpy wrapper around scan_filter.py's pure masking logic — subscribes to the
lidar driver's raw scan topic, republishes a copy with the mast/antenna self-
occlusion sectors NaN'd out on the topic Nav2/SLAM actually consume.

Only ever launched by sensors_only_launch.py's real-hardware group (same treatment
as esp32_driver.py) — sim/CI never constructs this node; Gazebo's own lidar plugin
has no self-occlusion to mask. Default input_topic='scan' (ldlidar_ros2's own
default output) and output_topic='/robot_001/scan' — this also closes the
lidar-side half of RealRobotStartup.md's separately-tracked topic-remapping gap
(sensors_only_launch.py includes the vendor launch file with no remappings at all)
as a side effect of masking, since the masked copy has to land somewhere Nav2/EKF
already expect it. The camera side of that remapping gap is untouched here.
"""
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import LaserScan

from nav_fleet.scan_filter import mask_scan_values, parse_mask_sectors

# Confirmed live against the real Waveshare UGV-PT + ldlidar_ros2, 2026-08-10 (see
# scan_filter.py's module docstring for how these were measured).
DEFAULT_MASK_SECTORS_DEG = [46.0, 123.0, 268.0, 277.0]


class ScanMasker(Node):

    def __init__(self):
        super().__init__('scan_masker')
        self.declare_parameter('input_topic', 'scan')
        self.declare_parameter('output_topic', '/robot_001/scan')
        self.declare_parameter('mask_sectors_deg', DEFAULT_MASK_SECTORS_DEG)

        output_topic = self.get_parameter('output_topic').value
        self.pub = self.create_publisher(LaserScan, output_topic, 10)
        input_topic = self.get_parameter('input_topic').value
        self.create_subscription(LaserScan, input_topic, self._cb, 10)

        self.get_logger().info(
            f"scan_masker up — {input_topic} -> {output_topic}, "
            f"mask_sectors_deg={list(self.get_parameter('mask_sectors_deg').value)}")

    def _cb(self, msg):
        # Re-read the param each message (not cached at __init__) so a live
        # `ros2 param set` during bring-up/debugging takes effect immediately,
        # matching this project's other params-are-live-tunable nodes.
        sectors_deg = parse_mask_sectors(list(self.get_parameter('mask_sectors_deg').value))
        msg.ranges = mask_scan_values(msg.ranges, msg.angle_min, msg.angle_increment,
                                      sectors_deg)
        if msg.intensities:
            msg.intensities = mask_scan_values(msg.intensities, msg.angle_min,
                                               msg.angle_increment, sectors_deg)
        self.pub.publish(msg)


def main():
    rclpy.init()
    node = ScanMasker()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
