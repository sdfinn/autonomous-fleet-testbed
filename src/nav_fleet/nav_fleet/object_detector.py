# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""RF-DETR detector node.

Reads camera pictures, runs the RF-DETR network on each, and publishes one
vision_msgs/Detection2DArray per picture (including empty ones, so a reader can count
pictures). The arithmetic is in nav_fleet.rfdetr_detect and the machine-specific part in
nav_fleet.rfdetr_backends; this file is only the ROS wrapper.

SHADOW MODE is the default: it publishes on /robot_001/detections_shadow, which nothing
acts on. The mission script keeps reacting to the hand-written detector on
/robot_001/detections, and robot_boot.sh's bag records both, so the two can be compared
on the same run before this one is trusted (docs/detection-history.md). Switching over
later is the `output_topic` parameter.

Message convention, same as the hand-written detector:
  results[0].hypothesis.class_id   the name ("sports ball", "teddy bear", ...)
  results[0].hypothesis.score      the network's score, 0-1. NOT a measure of being right
  results[0].pose.pose.position.x  estimated distance in meters, NaN when there is none
  bbox                             center and size in pixels of the camera picture

Runs outside the container on the Jetson, beside the drivers, because it needs the GPU:
  ros2 run nav_fleet object_detector --ros-args \
      -p model_path:=$HOME/fleet-ci-data/models/rfdetr-small.engine
The `.engine` file is built on the Jetson from the `.onnx` file (rfdetr_backends.py).

Load before go: the network is loaded and run once on a blank picture before the node
subscribes to the camera, and the node says "detector ready" with how long that took.
If the model cannot be loaded the node exits with an error instead of running blind.
"""
import pathlib
import time

import numpy as np
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from sensor_msgs.msg import Image
from vision_msgs.msg import Detection2D, Detection2DArray, ObjectHypothesisWithPose

from nav_fleet.rfdetr_backends import make_backend
from nav_fleet.rfdetr_detect import Detector, load_config

DEFAULT_CONFIG = str(pathlib.Path(__file__).parent.parent / 'config' / 'detector_rfdetr.yaml')
SHADOW_TOPIC = '/robot_001/detections_shadow'
WARMUP_HW = (720, 1280)


class FrameStats:
    """Running numbers for the periodic log line: how many pictures, how long each took,
    and how old a picture was when its detections went out."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.count = 0
        self.total_ms = self.worst_ms = 0.0
        self.total_age_ms = 0.0
        self.boxes = 0

    def add(self, took_ms, age_ms, boxes):
        self.count += 1
        self.total_ms += took_ms
        self.worst_ms = max(self.worst_ms, took_ms)
        self.total_age_ms += age_ms
        self.boxes += boxes

    def line(self, period_s):
        if not self.count:
            return 'no pictures in the last %.0f s' % period_s
        return ('%.1f pictures/s; detect mean %.1f ms, worst %.1f ms; picture age at '
                'publish %.0f ms; %.1f boxes a picture' % (
                    self.count / period_s, self.total_ms / self.count, self.worst_ms,
                    self.total_age_ms / self.count, self.boxes / self.count))


def to_detection_array(detections, header):
    """Our Detection tuples -> one vision_msgs/Detection2DArray with the image's header."""
    out = Detection2DArray()
    out.header = header
    for d in detections:
        det = Detection2D()
        det.header = header
        hyp = ObjectHypothesisWithPose()
        hyp.hypothesis.class_id = d.name
        hyp.hypothesis.score = float(d.score)
        hyp.pose.pose.position.x = float(d.range_m)
        det.results.append(hyp)
        det.bbox.center.position.x = (d.x0 + d.x1) / 2.0
        det.bbox.center.position.y = (d.y0 + d.y1) / 2.0
        det.bbox.size_x = float(d.x1 - d.x0)
        det.bbox.size_y = float(d.y1 - d.y0)
        out.detections.append(det)
    return out


def image_msg_to_array(msg):
    """One sensor_msgs/Image -> (H x W x 3 uint8 array, is_bgr), WITHOUT copying the
    picture. A 1280 x 720 picture is 2.7 MB; at 10 a second the copies and the channel
    reorder of the general-purpose helper (nav_fleet.image_io) cost more processor time
    than the network costs GPU time (measured on the Jetson, 2026-11-22)."""
    if msg.encoding not in ('rgb8', 'bgr8'):
        raise ValueError('unsupported image encoding: %s' % msg.encoding)
    rows = np.frombuffer(msg.data, dtype=np.uint8).reshape(msg.height, msg.step)
    return (rows[:, :msg.width * 3].reshape(msg.height, msg.width, 3),
            msg.encoding == 'bgr8')


class ObjectDetector(Node):

    def __init__(self):
        super().__init__('object_detector')
        self.declare_parameter('model_path', '')
        self.declare_parameter('backend', 'auto')
        self.declare_parameter('config', DEFAULT_CONFIG)
        self.declare_parameter('input_topic', '/robot_001/camera/image_raw')
        self.declare_parameter('output_topic', SHADOW_TOPIC)
        self.declare_parameter('stats_period_s', 10.0)
        model_path = self.get_parameter('model_path').value
        if not model_path:
            raise RuntimeError('parameter model_path is required (a .engine or .onnx file)')
        if not pathlib.Path(model_path).is_file():
            raise RuntimeError('model file not found: %s' % model_path)

        started = time.perf_counter()
        backend = make_backend(self.get_parameter('backend').value, model_path)
        self.detector = Detector(backend, load_config(self.get_parameter('config').value))
        loaded_s = time.perf_counter() - started
        started = time.perf_counter()
        self.detector.detect(np.zeros(WARMUP_HW + (3,), dtype=np.uint8))
        first_ms = 1000 * (time.perf_counter() - started)

        output_topic = self.get_parameter('output_topic').value
        self.pub = self.create_publisher(Detection2DArray, output_topic, 10)
        # Depth 1: when a picture arrives while the last one is still being worked on,
        # only the newest is kept. An old picture's detections are worse than none.
        self.create_subscription(Image, self.get_parameter('input_topic').value,
                                 self._image_cb, 1)
        self.stats = FrameStats()
        self._period = float(self.get_parameter('stats_period_s').value)
        self.create_timer(self._period, self._log_stats)
        self._bad_frames = 0
        self.get_logger().info(
            'detector ready: %s on %s, input %dx%d; loaded in %.1f s, first picture %.0f ms; '
            'publishing on %s%s' % (
                pathlib.Path(model_path).name, type(backend).__name__,
                backend.input_hw[1], backend.input_hw[0], loaded_s, first_ms, output_topic,
                ' (shadow mode: nothing acts on this)' if output_topic == SHADOW_TOPIC else ''))

    def _image_cb(self, msg):
        started = time.perf_counter()
        try:
            picture, bgr = image_msg_to_array(msg)
        except ValueError as exc:
            self._bad_frames += 1
            if self._bad_frames in (1, 10, 100) or self._bad_frames % 1000 == 0:
                self.get_logger().warning('picture skipped (%s); %d so far'
                                          % (exc, self._bad_frames))
            return
        detections = self.detector.detect(picture, bgr=bgr)
        self.pub.publish(to_detection_array(detections, msg.header))
        took_ms = 1000 * (time.perf_counter() - started)
        stamp = msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9
        age_ms = 1000 * (self.get_clock().now().nanoseconds * 1e-9 - stamp)
        self.stats.add(took_ms, age_ms, len(detections))

    def _log_stats(self):
        self.get_logger().info(self.stats.line(self._period))
        self.stats.reset()

    def close(self):
        self.detector.backend.close()


def main():
    rclpy.init()
    node = None
    try:
        node = ObjectDetector()
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass                                   # Ctrl+C or SIGINT/SIGTERM from a launcher
    finally:
        if node is not None:
            node.close()
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
