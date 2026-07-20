# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""HSV ball detector node (Mission 2, spec §4).

Always-on with the nav stack: launched by nav2_only_launch.py, runs wherever the robot
brain runs (workstation Tier-1, Jetson in HIL — camera frames arrive over DDS either
way). Publishes one vision_msgs/Detection2DArray per camera frame INCLUDING empty
frames, so 'N consecutive frames' is directly countable by subscribers with no timing
heuristics. Convention: results[0].pose.pose.position.x carries the estimated range in
metres (camera axis) — Detection2D has no native range field.

The image topic is remappable by design: the webcam follow-up plan remaps it to a real
camera topic and swaps hsv_config for hsv_realcam.yaml.
"""
import pathlib

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from vision_msgs.msg import Detection2D, Detection2DArray, ObjectHypothesisWithPose

from nav_fleet.hsv_detect import detect_balls, load_hsv_config
from nav_fleet.image_io import image_msg_to_rgb

DEFAULT_CONFIG = str(pathlib.Path(__file__).parent.parent / 'config' / 'hsv_gazebo.yaml')


class BallDetector(Node):

    def __init__(self):
        super().__init__('ball_detector')
        self.declare_parameter('hsv_config', DEFAULT_CONFIG)
        self.cfg = load_hsv_config(self.get_parameter('hsv_config').value)
        self.pub = self.create_publisher(Detection2DArray, '/robot_001/detections', 10)
        self.create_subscription(Image, '/robot_001/camera/image_raw', self._image_cb, 10)
        self.get_logger().info(
            f"ball_detector up — colors {sorted(self.cfg['colors'])}, "
            f"range_k {self.cfg['range_k']}")

    def _image_cb(self, msg):
        out = Detection2DArray()
        out.header = msg.header
        for d in detect_balls(image_msg_to_rgb(msg), self.cfg):
            det = Detection2D()
            det.header = msg.header
            hyp = ObjectHypothesisWithPose()
            hyp.hypothesis.class_id = f"{d['color']}_ball"
            hyp.hypothesis.score = min(1.0, d['pixels'] / 500.0)
            # estimated range (m) — see module doc. NaN for frame-edge-clipped boxes
            # (hsv_detect.EDGE_MARGIN_PX) — an unreliable width must not drive a
            # reaction; mission_runner._detection_cb excludes non-finite ranges.
            hyp.pose.pose.position.x = d['range_m']
            det.results.append(hyp)
            det.bbox.center.position.x = d['cx']
            det.bbox.center.position.y = d['cy']
            det.bbox.size_x = float(d['width_px'])
            det.bbox.size_y = float(d['height_px'])
            out.detections.append(det)
        self.pub.publish(out)


def main():
    rclpy.init()
    node = BallDetector()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
