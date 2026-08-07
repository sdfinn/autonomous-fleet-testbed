# tools/smoke_test.py
# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""Bench smoke-test orchestrator (design spec §tools/smoke_test.py). Attended, bench-
side sanity check for the driver layer: topic Hz/sanity, one photo, a known-distance
ball correlation check, and an odom-verified motion pulse — BEFORE the driver layer is
ever trusted under Nav2. Interactive prompting is deliberate here (unlike
mission_runner's hard no-prompting rule) — a human runs this standing at the bench.

Run: python -m tools.smoke_test [--ball-ops operator|gz] [--runner-type local] ...
"""
import argparse
import math
import pathlib
import sys
import time

import numpy as np
import rclpy
import yaml
from sensor_msgs.msg import Image, Imu, LaserScan
from vision_msgs.msg import Detection2DArray

from nav_fleet.ground_truth import get_ground_truth_xy
from nav_fleet.image_io import image_msg_to_png, image_msg_to_rgb
from tools.mission2_day import GzBallOps
from tools.telemetry_logger import PHOTO_DIR

REPO_DIR = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_PROFILE = str(REPO_DIR / 'robot_profiles' / 'jetson_ugv_pt.yaml')

KNOWN_DISTANCE_M = 0.305       # 12 inches — design spec §3
DISTANCE_TOLERANCE_M = 0.102   # ~4 inches placement-imprecision tolerance — design spec §3
FORWARD_ARC_HALF_WIDTH_RAD = math.radians(15)


def load_robot_profile(path):
    """Load a robot_profiles/*.yaml file (first real consumer of its sensors.*.hz_min
    values, per the design spec — this profile was previously documentation-only)."""
    with open(path) as f:
        return yaml.safe_load(f)


def is_degenerate_scan(msg):
    """True if every range reading is non-finite or non-positive — the lidar 'exists
    on the topic' but never actually initialized."""
    real_readings = [r for r in msg.ranges if math.isfinite(r) and r > 0.0]
    return len(real_readings) == 0


def compute_ball_placement_xy(robot_x, robot_y, robot_yaw, distance_m):
    """The known-distance ball-placement point (design spec: 'known-distance ball
    placement, not a vague wave') — exactly `distance_m` directly ahead of the robot's
    CURRENT heading, so this works regardless of which world/coordinate frame the
    robot happens to start in."""
    return (robot_x + distance_m * math.cos(robot_yaw),
            robot_y + distance_m * math.sin(robot_yaw))


def check_topic(node, topic, msg_type, hz_min, degenerate_fn, window_s=3.0):
    """Subscribe to `topic` for `window_s` seconds. PASS requires: message rate >=
    hz_min AND the most recently received message is not degenerate per degenerate_fn.
    Returns {'pass', 'measured_hz', 'message_count', 'degenerate' (None if zero
    messages received)}."""
    state = {'count': 0, 'last_msg': None}

    def _cb(msg):
        state['count'] += 1
        state['last_msg'] = msg

    sub = node.create_subscription(msg_type, topic, _cb, 10)
    deadline = time.time() + window_s
    while time.time() < deadline:
        rclpy.spin_once(node, timeout_sec=0.1)
    node.destroy_subscription(sub)

    measured_hz = state['count'] / window_s
    degenerate = degenerate_fn(state['last_msg']) if state['last_msg'] is not None else None
    passed = measured_hz >= hz_min and degenerate is False
    return {'pass': passed, 'measured_hz': round(measured_hz, 2),
            'message_count': state['count'], 'degenerate': degenerate}


class OperatorPlaceBallOps:
    """Bench smoke test: lighter than mission2_day.py's BallOps contract (design spec
    §3) — a single place() only, no remove()/swap choreography needed. The operator's
    hands are the actuator; smoke_test.py waits for them."""

    def place(self, color, distance_m):
        inches = distance_m * 39.37
        input(f"Place the {color} ball {inches:.0f} inches ({distance_m:.3f} m) "
              f"directly in front of the robot, then press Enter: ")


def is_degenerate_image(rgb):
    """True if an image is uniformly one color — a camera that 'publishes' without
    ever actually capturing. rgb: HxWx3 numpy array."""
    return bool(np.all(rgb == rgb[0, 0]))


def check_photo(node, camera_topic='/robot_001/camera/image_raw', out_path=None,
                timeout_s=5.0):
    """One take_picture call (design spec §2), reusing the same primitive Mission 2
    already uses. PASS if the file exists afterward and isn't degenerate."""
    state = {'msg': None}

    def _cb(msg):
        state['msg'] = msg

    sub = node.create_subscription(Image, camera_topic, _cb, 10)
    deadline = time.time() + timeout_s
    while state['msg'] is None and time.time() < deadline:
        rclpy.spin_once(node, timeout_sec=0.1)
    node.destroy_subscription(sub)

    if state['msg'] is None:
        return {'pass': False, 'path': None, 'reason': 'no image received'}

    if out_path is None:
        out_path = str(pathlib.Path(PHOTO_DIR) / f"smoke_test_{time.strftime('%Y%m%dT%H%M%S')}.png")
    image_msg_to_png(state['msg'], out_path)
    degenerate = is_degenerate_image(image_msg_to_rgb(state['msg']))
    exists = pathlib.Path(out_path).exists()
    return {'pass': bool(exists and not degenerate), 'path': out_path if exists else None,
            'degenerate': degenerate}


def _forward_arc_min_range(msg, half_width_rad=FORWARD_ARC_HALF_WIDTH_RAD):
    """Minimum finite, positive range within +/- half_width_rad of the scan's zero
    bearing (straight ahead) — restricting to the forward arc so an object beside or
    behind the robot isn't mistaken for the ball placed in front of it."""
    best = None
    angle = msg.angle_min
    for r in msg.ranges:
        if -half_width_rad <= angle <= half_width_rad and math.isfinite(r) and r > 0.0:
            if best is None or r < best:
                best = r
        angle += msg.angle_increment
    return best


def check_ball_correlation(node, ball_ops, known_distance_m=KNOWN_DISTANCE_M,
                           tolerance_m=DISTANCE_TOLERANCE_M, window_s=3.0):
    """Design spec §3: PASS requires the lidar's measured range agrees with
    known_distance_m within tolerance_m, AND a yellow_ball detection is present during
    the window. Camera-estimated range is reported, not gated — hsv_realcam.yaml's
    range_k isn't calibrated against a real camera yet."""
    if isinstance(ball_ops, GzBallOps):
        # nav_fleet.ground_truth.get_ground_truth_xy() only parses the model's
        # world-frame POSITION (x, y) — not orientation/yaw (see its own
        # parse_model_position, which never reads the `orientation` block the raw
        # `gz topic` text actually contains). Every existing ground-truth consumer
        # that needs a placement DIRECTION, not just a point
        # (tools/calibrate_ball_range.py), works around this the same way: this
        # check runs before any navigation, so the robot is still at its spawn
        # heading — north, yaw = pi/2 in this world. Matches that same convention
        # rather than inventing a new one; see calibrate_ball_range.py's own
        # "facing north" comment.
        truth = get_ground_truth_xy()
        assert truth is not None, 'sim not up / no ground truth available for GzBallOps placement'
        rx, ry = truth
        ryaw = math.pi / 2
        bx, by = compute_ball_placement_xy(rx, ry, ryaw, known_distance_m)
        ball_ops.place('yellow', bx, by)
    else:
        ball_ops.place('yellow', known_distance_m)

    scan_state = {'min_range': None}
    det_state = {'yellow_range_m': None}

    def _scan_cb(msg):
        r = _forward_arc_min_range(msg)
        if r is not None:
            scan_state['min_range'] = r

    def _det_cb(msg):
        for det in msg.detections:
            for hyp in det.results:
                if hyp.hypothesis.class_id == 'yellow_ball':
                    det_state['yellow_range_m'] = hyp.pose.pose.position.x

    scan_sub = node.create_subscription(LaserScan, '/robot_001/scan', _scan_cb, 10)
    det_sub = node.create_subscription(Detection2DArray, '/robot_001/detections', _det_cb, 10)
    deadline = time.time() + window_s
    while time.time() < deadline:
        rclpy.spin_once(node, timeout_sec=0.1)
    node.destroy_subscription(scan_sub)
    node.destroy_subscription(det_sub)

    lidar_ok = (scan_state['min_range'] is not None and
                abs(scan_state['min_range'] - known_distance_m) <= tolerance_m)
    detection_present = det_state['yellow_range_m'] is not None
    return {
        'pass': bool(lidar_ok and detection_present),
        'lidar_min_range_m': scan_state['min_range'],
        'known_distance_m': known_distance_m,
        'yellow_ball_detected': detection_present,
        'camera_estimated_range_m': det_state['yellow_range_m'],  # reported, not gated
    }
