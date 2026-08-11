# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""Closes the camera half of RealRobotStartup.md's topic-remapping gap — the same
problem scan_masker.py already solved for the lidar, minus any masking logic (a
camera image needs no self-occlusion mask, just the right topic name). Subscribes
to depthai-ros's real output topic and republishes it unchanged on the topic
ball_detector.py and the bench smoke test actually expect.

depthai_ros_driver's camera.launch.py hardcodes its own topic names with no
IncludeLaunchDescription-level remapping support (same class of gap ldlidar_ros2's
own launch file has, confirmed 2026-08-09/10) — a relay node sidesteps needing to
patch a third vendor launch file the way lidar's port name needed patching.

input_topic default is the RECTIFIED image (/oak/rgb/image_rect), not the raw one
— this project has only ever pulled real, non-degenerate photos from image_rect
(confirmed live, 2026-08-10), and a rectified image is the more sensible input for
HSV-based ball detection/range estimation anyway.

Launched by drivers_only_launch.py (real-hardware group, same treatment as
esp32_driver.py/scan_masker.py) — primarily via robot_boot.sh (real mission boot)
and hil_stage.sh smoke() (the bench smoke test), both bare-metal; also reachable
via sensors_only_launch.py's own real-hardware group, which includes
drivers_only_launch.py (2026-08-10 refactor). sim/CI never constructs this node;
Gazebo's own camera plugin already publishes directly to
/robot_001/camera/image_raw.
"""
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image


class CameraRelay(Node):

    def __init__(self, parameter_overrides=None):
        super().__init__('camera_relay', parameter_overrides=parameter_overrides)
        self.declare_parameter('input_topic', '/oak/rgb/image_rect')
        self.declare_parameter('output_topic', '/robot_001/camera/image_raw')

        output_topic = self.get_parameter('output_topic').value
        self.pub = self.create_publisher(Image, output_topic, 10)
        input_topic = self.get_parameter('input_topic').value
        self.create_subscription(Image, input_topic, self._cb, 10)

        self.get_logger().info(f"camera_relay up — {input_topic} -> {output_topic}")

    def _cb(self, msg):
        self.pub.publish(msg)


def main():
    rclpy.init()
    node = CameraRelay()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
