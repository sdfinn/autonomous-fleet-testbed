# tests/test_smoke_test.py
# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""Requires a live ROS2 environment (imports rclpy at module level via tools.smoke_test)
— same --ignore treatment as test_esp32_driver.py in stage-1-quality, run in
stage-2-gazebo. Doesn't need Gazebo for THIS file's tests specifically (a bare rclpy
context + a real publisher is enough), but stays out of stage-1 since rclpy itself
isn't installed there.
"""
import math
import threading
import time

import numpy as np
import pytest
import rclpy
from sensor_msgs.msg import Image, LaserScan
from unittest.mock import MagicMock, patch

from tools.mission2_day import GzBallOps
from tools.smoke_test import (check_ball_correlation, check_photo, check_topic,
                              compute_ball_placement_xy, is_degenerate_scan,
                              load_robot_profile, OperatorPlaceBallOps, is_degenerate_image)


def _make_test_image_msg(width=4, height=4, color=None):
    """Build a real sensor_msgs/Image (rgb8, no row padding) with genuine pixel content
    by default (two distinct non-black pixels, matching image_io.image_msg_to_rgb's
    documented rgb8/bgr8 + step=width*3-no-padding expectations), or a single uniform
    `color` for the degenerate-image case."""
    rgb = np.zeros((height, width, 3), dtype=np.uint8)
    if color is not None:
        rgb[:, :] = color
    else:
        rgb[0, 0] = [255, 0, 0]
        rgb[1, 2] = [0, 200, 40]
    msg = Image()
    msg.height = height
    msg.width = width
    msg.encoding = 'rgb8'
    msg.step = width * 3
    msg.data = rgb.tobytes()
    return msg


@pytest.fixture(scope='module', autouse=True)
def ros_context():
    rclpy.init()
    yield
    rclpy.try_shutdown()


def test_load_robot_profile_reads_real_profile():
    profile = load_robot_profile('robot_profiles/jetson_ugv_pt.yaml')
    assert profile['sensors']['odometry']['hz_min'] == 50
    assert profile['sub_controller']['baud'] == 115200


def test_is_degenerate_scan_all_inf():
    msg = LaserScan()
    msg.ranges = [float('inf')] * 10
    assert is_degenerate_scan(msg) is True


def test_is_degenerate_scan_real_readings():
    msg = LaserScan()
    msg.ranges = [1.2, 1.3, float('inf'), 0.9]
    assert is_degenerate_scan(msg) is False


def test_compute_ball_placement_xy_facing_positive_x():
    x, y = compute_ball_placement_xy(0.0, 0.0, 0.0, 0.305)
    assert x == pytest.approx(0.305)
    assert y == pytest.approx(0.0, abs=1e-9)


def test_compute_ball_placement_xy_facing_positive_y():
    x, y = compute_ball_placement_xy(1.0, 2.0, math.pi / 2, 0.305)
    assert x == pytest.approx(1.0, abs=1e-9)
    assert y == pytest.approx(2.305)


def test_check_topic_measures_hz_and_flags_low_rate():
    # Publishing must overlap check_topic's own subscription window, not finish before
    # it starts: default QoS is volatile (no late-joiner replay of already-sent
    # messages), so a publish loop that completes before check_topic subscribes would
    # deterministically leave message_count == 0 regardless of implementation
    # correctness. Background thread keeps the same ~2 Hz-under-threshold intent while
    # actually overlapping the window.
    node = rclpy.create_node('test_check_topic_low_rate')
    pub = node.create_publisher(LaserScan, '/test_smoke_topic_low', 10)
    stop_publishing = threading.Event()

    def _publish_loop():
        while not stop_publishing.is_set():
            msg = LaserScan()
            msg.ranges = [1.0, 1.0]
            pub.publish(msg)
            time.sleep(0.5)  # ~2 Hz, well under a 10 Hz hz_min

    publisher_thread = threading.Thread(target=_publish_loop, daemon=True)
    publisher_thread.start()
    try:
        result = check_topic(node, '/test_smoke_topic_low', LaserScan, hz_min=10,
                             degenerate_fn=is_degenerate_scan, window_s=1.0)
        assert result['pass'] is False
        assert result['message_count'] >= 1
    finally:
        stop_publishing.set()
        publisher_thread.join(timeout=2.0)
        node.destroy_node()


def test_check_topic_no_messages_received():
    node = rclpy.create_node('test_check_topic_silent')
    try:
        result = check_topic(node, '/nobody_publishes_here', LaserScan, hz_min=1,
                             degenerate_fn=is_degenerate_scan, window_s=0.5)
        assert result['pass'] is False
        assert result['message_count'] == 0
        assert result['degenerate'] is None
    finally:
        node.destroy_node()


def test_is_degenerate_image_uniform_black():
    rgb = np.zeros((10, 10, 3), dtype=np.uint8)
    assert is_degenerate_image(rgb) is True


def test_is_degenerate_image_real_content():
    rgb = np.zeros((10, 10, 3), dtype=np.uint8)
    rgb[0, 0] = [255, 0, 0]
    rgb[5, 5] = [0, 255, 0]
    assert is_degenerate_image(rgb) is False


def test_operator_place_ball_ops_prompts_with_inches(monkeypatch):
    prompts = []
    monkeypatch.setattr('builtins.input', lambda p: prompts.append(p) or '')
    OperatorPlaceBallOps().place('yellow', 0.305)
    assert len(prompts) == 1
    assert 'yellow' in prompts[0]
    assert '12' in prompts[0]  # 0.305 m -> ~12 inches


def test_check_ball_correlation_gzballops_places_at_known_distance_from_ground_truth(monkeypatch):
    # Regression test for a real bug found in this task: get_ground_truth_xy() (the
    # real nav_fleet.ground_truth function, confirmed by reading its source) returns
    # only (x, y) or None -- never a 3-tuple with yaw -- so check_ball_correlation
    # must not try to unpack a yaw out of it. This exercises that GzBallOps branch
    # end-to-end (no live Gazebo needed -- GzBallOps.place is monkeypatched) to prove
    # it doesn't raise.
    placed = []
    monkeypatch.setattr(GzBallOps, 'place', lambda self, color, x, y: placed.append((color, x, y)))
    monkeypatch.setattr('tools.smoke_test.get_ground_truth_xy', lambda: (1.0, 2.0))

    node = rclpy.create_node('test_check_ball_correlation_gz')
    try:
        result = check_ball_correlation(node, GzBallOps(), known_distance_m=0.305,
                                         tolerance_m=0.1, window_s=0.2)
    finally:
        node.destroy_node()

    assert len(placed) == 1
    color, bx, by = placed[0]
    assert color == 'yellow'
    # robot assumed to still be at its spawn heading (north, yaw=pi/2) -- see the
    # implementation's own comment for why -- so the ball lands directly north of
    # the ground-truth point, not east/west.
    assert bx == pytest.approx(1.0, abs=1e-9)
    assert by == pytest.approx(2.0 + 0.305)
    # No scan/detection publishers exist in this test, so the correlation itself
    # can't pass -- only proving the placement call succeeded without crashing.
    assert result['pass'] is False
    assert result['lidar_min_range_m'] is None
    assert result['yellow_ball_detected'] is False


def test_check_ball_correlation_gzballops_no_ground_truth_fails_gracefully(monkeypatch):
    # Review finding: get_ground_truth_xy() returning None (e.g. Gazebo not running)
    # used to raise AssertionError, which would crash run_smoke_test's whole check
    # sequence (Task 7 wraps the check loop in one try/finally, not a per-check
    # try/except). Must degrade to a {'pass': False, ...} dict like every other
    # failure path in this file instead.
    placed = []
    monkeypatch.setattr(GzBallOps, 'place', lambda self, color, x, y: placed.append((color, x, y)))
    monkeypatch.setattr('tools.smoke_test.get_ground_truth_xy', lambda: None)

    node = rclpy.create_node('test_check_ball_correlation_no_truth')
    try:
        result = check_ball_correlation(node, GzBallOps(), known_distance_m=0.305,
                                         tolerance_m=0.1, window_s=0.1)
    finally:
        node.destroy_node()

    assert result['pass'] is False
    assert 'reason' in result
    assert 'ground truth' in result['reason'].lower()
    # Must fail before ever attempting a placement -- there's no point in the world to
    # place the ball relative to.
    assert placed == []


def test_check_photo_saves_real_image_with_pixel_content(tmp_path):
    node = rclpy.create_node('test_check_photo_real')
    pub = node.create_publisher(Image, '/test_smoke_photo_real', 10)
    stop_publishing = threading.Event()

    def _publish_loop():
        while not stop_publishing.is_set():
            pub.publish(_make_test_image_msg())
            time.sleep(0.05)

    publisher_thread = threading.Thread(target=_publish_loop, daemon=True)
    publisher_thread.start()
    out_path = str(tmp_path / 'smoke_test_photo.png')
    try:
        result = check_photo(node, camera_topic='/test_smoke_photo_real', out_path=out_path,
                             timeout_s=3.0)
        assert result['pass'] is True
        assert result['path'] == out_path
        assert result['degenerate'] is False
        assert (tmp_path / 'smoke_test_photo.png').exists()
    finally:
        stop_publishing.set()
        publisher_thread.join(timeout=2.0)
        node.destroy_node()


def test_check_photo_no_image_received():
    node = rclpy.create_node('test_check_photo_silent')
    try:
        result = check_photo(node, camera_topic='/nobody_publishes_photos_here', timeout_s=0.5)
        assert result['pass'] is False
        assert result['path'] is None
        assert result['reason'] == 'no image received'
    finally:
        node.destroy_node()


def test_check_photo_degenerate_image_fails(tmp_path):
    # Reuses is_degenerate_image (already unit-tested on its own above) via a real
    # published uniform-color Image, closing the gap the review flagged: is_degenerate_
    # image had direct tests, but check_photo's own use of it (including the file it
    # writes) never did.
    node = rclpy.create_node('test_check_photo_degenerate')
    pub = node.create_publisher(Image, '/test_smoke_photo_degenerate', 10)
    stop_publishing = threading.Event()

    def _publish_loop():
        while not stop_publishing.is_set():
            pub.publish(_make_test_image_msg(color=(60, 60, 60)))
            time.sleep(0.05)

    publisher_thread = threading.Thread(target=_publish_loop, daemon=True)
    publisher_thread.start()
    out_path = str(tmp_path / 'smoke_test_photo_degenerate.png')
    try:
        result = check_photo(node, camera_topic='/test_smoke_photo_degenerate',
                             out_path=out_path, timeout_s=3.0)
        assert result['pass'] is False
        assert result['degenerate'] is True
    finally:
        stop_publishing.set()
        publisher_thread.join(timeout=2.0)
        node.destroy_node()
