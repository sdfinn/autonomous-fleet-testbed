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
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from sensor_msgs.msg import Image, Imu, LaserScan
from unittest.mock import MagicMock, patch

from tools.mission2_day import GzBallOps
from tools.mission2_harness import LIDAR_BALL_SDF
from tools.smoke_test import (KNOWN_DISTANCE_M, LIDAR_HEIGHT_M, LidarVisibleGzBallOps,
                              check_ball_correlation, check_motion, check_photo,
                              check_topic, compute_ball_placement_xy, is_degenerate_scan,
                              load_robot_profile, OperatorPlaceBallOps, is_degenerate_image,
                              _is_degenerate_imu, _is_degenerate_image_msg,
                              _is_degenerate_odom, _print_summary, run_smoke_test)


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


def test_check_topic_tolerates_one_boundary_message_below_exact_hz_min():
    # Real bug, found live in CI (run 31332673543, 2026-08-09): hz_min set to the
    # EXACT nominal publish rate with zero tolerance means a single message landing
    # just outside the measurement window (pure timing-phase luck vs a real sensor
    # problem -- confirmed by re-running the identical stack and seeing it pass
    # cleanly) flips PASS to FAIL. A camera genuinely publishing at ~10 Hz for the
    # window's whole duration but yielding 29 messages instead of 30 in a 3.0s window
    # (9.67 measured -- exactly the real CI failure) must still PASS -- this is what
    # "we want the real robot with real sensors to work" means in practice. Mirrors
    # the real bug's own window_s=3.0/hz_min=10 exactly, rather than an artificially
    # short window -- a too-short window doesn't leave room for the tolerance itself
    # to be exercised meaningfully.
    node = rclpy.create_node('test_check_topic_boundary_tolerance')
    pub = node.create_publisher(LaserScan, '/test_smoke_topic_boundary', 10)
    stop_publishing = threading.Event()

    def _publish_loop():
        while not stop_publishing.is_set():
            msg = LaserScan()
            msg.ranges = [1.0, 1.0]  # non-empty, non-degenerate per is_degenerate_scan
            pub.publish(msg)
            time.sleep(0.1)  # ~10 Hz -- the real camera's own nominal rate

    publisher_thread = threading.Thread(target=_publish_loop, daemon=True)
    publisher_thread.start()
    try:
        result = check_topic(node, '/test_smoke_topic_boundary', LaserScan, hz_min=10,
                             degenerate_fn=is_degenerate_scan, window_s=3.0)
        # A real 10 Hz publisher over 3.0s realistically yields ~27-31 messages
        # depending on timing-phase luck -- all of which must PASS under the new
        # tolerance (>= hz_min * 0.9 * window_s = 27 messages). A message_count this
        # low would only happen if the publisher genuinely wasn't running.
        assert result['message_count'] >= 25
        assert result['pass'] is True
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
    # end-to-end (no live Gazebo needed -- LidarVisibleGzBallOps.place is
    # monkeypatched) to prove it doesn't raise.
    placed = []
    monkeypatch.setattr(LidarVisibleGzBallOps, 'place',
                        lambda self, color, x, y: placed.append((color, x, y)))
    monkeypatch.setattr('tools.smoke_test.get_ground_truth_xy', lambda: (1.0, 2.0))

    node = rclpy.create_node('test_check_ball_correlation_gz')
    try:
        result = check_ball_correlation(node, LidarVisibleGzBallOps(), known_distance_m=0.305,
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
    monkeypatch.setattr(LidarVisibleGzBallOps, 'place',
                        lambda self, color, x, y: placed.append((color, x, y)))
    monkeypatch.setattr('tools.smoke_test.get_ground_truth_xy', lambda: None)

    node = rclpy.create_node('test_check_ball_correlation_no_truth')
    try:
        result = check_ball_correlation(node, LidarVisibleGzBallOps(), known_distance_m=0.305,
                                        tolerance_m=0.1, window_s=0.1)
    finally:
        node.destroy_node()

    assert result['pass'] is False
    assert 'reason' in result
    assert 'ground truth' in result['reason'].lower()
    # Must fail before ever attempting a placement -- there's no point in the world to
    # place the ball relative to.
    assert placed == []
    # Real gap, found live in CI (stage-4-hil run 31333381064, 2026-08-09):
    # smoke_ci's HIL container runs on the Jetson, which can never reach Gazebo's
    # ground truth (that only exists on the workstation) -- this is a structural
    # limitation of that specific path, not a real sensor/driver fault, and
    # ball_correlation is already exercised for real with real ground truth by
    # stage-2-gazebo (sim). 'skipped' distinguishes "couldn't judge" from "judged
    # and failed" so run_smoke_test's overall_pass can treat it accordingly.
    assert result['skipped'] is True


def test_check_ball_correlation_normal_failure_is_not_marked_skipped(monkeypatch):
    # The 'skipped' marker must be specific to "no ground truth" -- a REAL
    # correlation failure (ground truth WAS available, the ball genuinely wasn't
    # detected) must still count as a real failure, not get silently excused.
    monkeypatch.setattr(LidarVisibleGzBallOps, 'place', lambda self, color, x, y: None)
    monkeypatch.setattr('tools.smoke_test.get_ground_truth_xy', lambda: (1.0, 2.0))

    node = rclpy.create_node('test_check_ball_correlation_real_failure')
    try:
        result = check_ball_correlation(node, LidarVisibleGzBallOps(), known_distance_m=0.305,
                                        tolerance_m=0.1, window_s=0.1)
    finally:
        node.destroy_node()

    # No scan/detection publishers in this test -> a real, judged FAIL.
    assert result['pass'] is False
    assert result.get('skipped', False) is False


def test_lidar_visible_gz_ball_ops_is_a_gzballops_subclass():
    # check_ball_correlation's isinstance(ball_ops, GzBallOps) branch (the one that
    # computes placement from ground truth) must still match -- LidarVisibleGzBallOps
    # exists ONLY to override place() with a lidar-visible spawn, not to opt out of
    # that branch.
    assert issubclass(LidarVisibleGzBallOps, GzBallOps)


def test_lidar_ball_sdf_has_collision_geometry_unlike_mission2s_camera_only_ball():
    # This SDF gives the ball real <collision> geometry (Mission 2's own
    # mission2_harness.spawn_ball() deliberately has none, so its robot never
    # physically bumps a reaction ball) -- physical realism for a bench-test ball,
    # not (per live testing, 2026-08-09) what actually fixes lidar visibility. See
    # tools.smoke_test.LIDAR_HEIGHT_M for the real fix (this lidar is 2D/planar; a
    # floor-level ball sits below its single scan plane regardless of collision).
    sdf = LIDAR_BALL_SDF.format(name='ball_yellow', x=1.0, y=2.0, z=0.043, r=0.043,
                                rgba='0.9 0.9 0.05 1')
    assert '<collision' in sdf
    assert '<sphere>' in sdf  # collision geometry present, not just declared


def test_lidar_visible_gz_ball_ops_spawns_at_lidar_scan_height_not_floor_level(monkeypatch):
    # Real root cause (2026-08-09, confirmed live): this robot's lidar is a 2D planar
    # lidar -- one fixed scan height, no vertical resolution -- so a floor-level ball
    # (spawn_lidar_ball's own z default, BALL_RADIUS) sits entirely below the scan
    # plane and is undetectable at any distance. place() must spawn the ball's CENTER
    # at LIDAR_HEIGHT_M instead of accepting the floor-level default.
    calls = []

    def _fake_spawn(color, x, y, z=None):
        calls.append((color, x, y, z))
        return 'ball_yellow'

    monkeypatch.setattr('tools.smoke_test.spawn_lidar_ball', _fake_spawn)
    monkeypatch.setattr('tools.smoke_test.time.sleep', lambda s: None)

    LidarVisibleGzBallOps().place('yellow', 1.0, 2.0)

    assert len(calls) == 1
    color, x, y, z = calls[0]
    assert (color, x, y) == ('yellow', 1.0, 2.0)
    assert z == pytest.approx(LIDAR_HEIGHT_M)
    assert z != pytest.approx(0.043)  # must NOT be the floor-level default


def test_operator_place_ball_ops_prompts_with_riser_height(monkeypatch):
    # A real physical bench test needs the operator to know to use a riser/box --
    # otherwise a correctly-distance-placed but floor-level real ball hits the exact
    # same 2D-lidar-scan-height problem the sim ball did.
    # Height uses LIDAR_HEIGHT_REAL_M (real hardware, measured 2026-08-10 -- ~6in),
    # NOT LIDAR_HEIGHT_M (that one's sim-URDF-geometry-derived, ~10in, and only
    # correct for LidarVisibleGzBallOps's own sim spawn height -- see that constant's
    # own comment for why the two must NOT be the same value).
    prompts = []
    monkeypatch.setattr('builtins.input', lambda p: prompts.append(p) or '')
    OperatorPlaceBallOps().place('yellow', 0.75)
    assert len(prompts) == 1
    assert 'riser' in prompts[0].lower() or 'box' in prompts[0].lower()
    assert '6' in prompts[0]  # 0.1524 m -> ~6 inches


def test_known_distance_m_clears_the_camera_field_of_view():
    # Root cause, part 2 (2026-08-09): at the old 0.305 m (12"), a floor-level ball is
    # geometrically outside the level-mounted camera's vertical FOV -- confirmed via
    # the real URDF (camera 0.175 m forward of base, ~0.24 m high, level, ~23.4 deg
    # vertical half-FOV): the required look-down angle at 0.305 m is ~56.6 deg, more
    # than double the camera's own half-FOV. This just pins the fixed regression
    # value (0.75 m, ~2.5 ft) so a future accidental edit back toward "12 inches"
    # fails loudly here instead of silently reintroducing the camera-FOV bug.
    assert KNOWN_DISTANCE_M == pytest.approx(0.75)


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


def test_check_motion_detects_forward_and_turn_deltas():
    node = rclpy.create_node('test_check_motion')
    odom_pub = node.create_publisher(Odometry, '/robot_001/odom', 10)
    cmd_pub = node.create_publisher(Twist, '/robot_001/cmd_vel', 10)
    try:
        # Simulate a driver publishing odom that visibly moves during the check —
        # a background timer nudges x forward and yaw around so before/after differ.
        state = {'x': 0.0, 'yaw': 0.0, 'tick': 0}

        def _tick():
            state['tick'] += 1
            if state['tick'] > 3:
                state['x'] += 0.02
            if state['tick'] > 15:
                state['yaw'] += 0.05
            msg = Odometry()
            msg.pose.pose.position.x = state['x']
            msg.pose.pose.orientation.z = math.sin(state['yaw'] / 2.0)
            msg.pose.pose.orientation.w = math.cos(state['yaw'] / 2.0)
            odom_pub.publish(msg)

        timer = node.create_timer(0.05, _tick)
        result = check_motion(node, cmd_pub)
        node.destroy_timer(timer)
        assert result['pass'] is True
        assert result['forward_delta_m'] > 0.0
        assert result['turn_delta_rad'] > 0.0
    finally:
        node.destroy_node()


def test_check_motion_no_odom_fails_cleanly():
    node = rclpy.create_node('test_check_motion_no_odom')
    cmd_pub = node.create_publisher(Twist, '/robot_001/cmd_vel', 10)
    try:
        result = check_motion(node, cmd_pub)
        assert result['pass'] is False
        assert 'reason' in result
    finally:
        node.destroy_node()


def test_is_degenerate_odom_flags_nan_and_inf():
    msg = Odometry()
    msg.pose.pose.position.x = float('nan')
    assert _is_degenerate_odom(msg) is True

    msg2 = Odometry()
    msg2.twist.twist.linear.x = float('inf')
    assert _is_degenerate_odom(msg2) is True


def test_is_degenerate_odom_all_zero_is_not_degenerate():
    # A legitimately stationary robot has an all-zero pose/twist (this integrator
    # starts at the origin) -- must NOT be flagged degenerate, only non-finite values
    # should be (see the implementation's own docstring).
    msg = Odometry()
    assert _is_degenerate_odom(msg) is False


def test_is_degenerate_imu_flags_nan_and_inf():
    msg = Imu()
    msg.angular_velocity.z = float('nan')
    assert _is_degenerate_imu(msg) is True

    msg2 = Imu()
    msg2.linear_acceleration.x = float('inf')
    assert _is_degenerate_imu(msg2) is True


def test_is_degenerate_imu_real_readings_not_degenerate():
    msg = Imu()
    msg.angular_velocity.z = 0.01
    msg.linear_acceleration.z = 9.81
    assert _is_degenerate_imu(msg) is False


def test_is_degenerate_image_msg_uniform_color_flagged():
    assert _is_degenerate_image_msg(_make_test_image_msg(color=(60, 60, 60))) is True


def test_is_degenerate_image_msg_real_content_not_flagged():
    assert _is_degenerate_image_msg(_make_test_image_msg()) is False


def test_print_summary_reports_pass_and_fail(capsys):
    checks = {
        'odom': {'pass': True, 'measured_hz': 51.0},
        'motion': {'pass': False, 'reason': 'no odom before motion check'},
    }
    _print_summary(checks, overall_pass=False)
    captured = capsys.readouterr()
    assert '[PASS] odom:' in captured.out
    assert '[FAIL] motion:' in captured.out
    assert '=== Overall: FAIL ===' in captured.out


def test_print_summary_reports_skip_distinct_from_fail(capsys):
    # A skipped check (couldn't judge -- e.g. no ground truth in HIL) must read
    # differently from a real FAIL in the printed summary, not just in the DB.
    checks = {
        'ball_correlation': {'pass': False, 'skipped': True,
                             'reason': 'no ground truth available (Gazebo not running?)'},
    }
    _print_summary(checks, overall_pass=True)
    captured = capsys.readouterr()
    assert '[SKIP] ball_correlation:' in captured.out
    assert '[FAIL] ball_correlation:' not in captured.out


# --- run_smoke_test orchestration tests -------------------------------------
#
# run_smoke_test() calls rclpy.init()/rclpy.shutdown() itself, which would
# conflict with this file's own module-scoped, autouse `ros_context` fixture
# (already holding a live rclpy context for the whole file) if it actually ran.
# Patching the WHOLE `tools.smoke_test.rclpy` module reference to a MagicMock
# makes every rclpy.* call inside run_smoke_test (init/create_node/shutdown) a
# no-op mock call instead — no second real init, no real node. The individual
# check_* functions (which already have their own real-publisher tests above)
# are stubbed via unittest.mock.patch so these tests exercise ONLY
# run_smoke_test's own orchestration logic: call order/completeness, the
# overall_pass computation, and the log_smoke_test_run call — not the checks
# themselves.

def test_run_smoke_test_all_checks_pass_yields_overall_pass_true():
    with patch('tools.smoke_test.rclpy') as mock_rclpy, \
         patch('tools.smoke_test.smoke_test_log') as mock_log, \
         patch('tools.smoke_test.check_topic', return_value={'pass': True}) as mock_check_topic, \
         patch('tools.smoke_test.check_photo', return_value={'pass': True}) as mock_check_photo, \
         patch('tools.smoke_test.check_ball_correlation',
               return_value={'pass': True}) as mock_check_ball, \
         patch('tools.smoke_test.check_motion', return_value={'pass': True}) as mock_check_motion:
        mock_rclpy.create_node.return_value = MagicMock()
        result = run_smoke_test('robot_profiles/jetson_ugv_pt.yaml', ball_ops=MagicMock(),
                                runner_type='local', commit_sha='abc123', ci_run_number=42,
                                db_path='/tmp/fake_smoke.db')

    assert result is True
    assert mock_check_topic.call_count == 4  # odom, scan, camera, imu
    mock_check_photo.assert_called_once()
    mock_check_ball.assert_called_once()
    mock_check_motion.assert_called_once()

    mock_log.log_smoke_test_run.assert_called_once()
    _, kwargs = mock_log.log_smoke_test_run.call_args
    assert kwargs['overall_pass'] is True
    assert set(kwargs['checks'].keys()) == {
        'odom', 'scan', 'camera', 'imu', 'photo', 'ball_correlation', 'motion'}


def test_run_smoke_test_overall_pass_ignores_a_skipped_ball_correlation():
    # Real gap, found live in CI (stage-4-hil, run 31333381064, 2026-08-09): the
    # HIL-container path can never reach Gazebo ground truth, so
    # check_ball_correlation degrades to a 'skipped' result there -- that must NOT
    # drag down overall_pass when every check that COULD run actually passed.
    # ball_correlation is already exercised for real (with real ground truth) by
    # stage-2-gazebo -- this keeps stage-4-hil's own smoke-test regression honest
    # about what it can and can't judge, per Mike's call: keep it simple, gate 2
    # already covers the real check.
    with patch('tools.smoke_test.rclpy') as mock_rclpy, \
         patch('tools.smoke_test.smoke_test_log') as mock_log, \
         patch('tools.smoke_test.check_topic', return_value={'pass': True}), \
         patch('tools.smoke_test.check_photo', return_value={'pass': True}), \
         patch('tools.smoke_test.check_ball_correlation',
               return_value={'pass': False, 'skipped': True,
                             'reason': 'no ground truth available (Gazebo not running?)'}), \
         patch('tools.smoke_test.check_motion', return_value={'pass': True}):
        mock_rclpy.create_node.return_value = MagicMock()
        result = run_smoke_test('robot_profiles/jetson_ugv_pt.yaml', ball_ops=MagicMock())

    assert result is True
    assert mock_log.log_smoke_test_run.call_args.kwargs['overall_pass'] is True


def test_run_smoke_test_runs_every_check_even_after_early_failure():
    # The most important orchestration requirement (design spec §5, and the
    # implementation's own docstring): "run every check regardless of earlier
    # failures." Making the FIRST checks (the 4 check_topic calls) all fail
    # and then asserting photo/ball_correlation/motion were STILL each called
    # exactly once is what actually distinguishes this from a short-circuiting
    # implementation -- a test that only inspected the final overall_pass
    # boolean would pass identically either way.
    with patch('tools.smoke_test.rclpy') as mock_rclpy, \
         patch('tools.smoke_test.smoke_test_log') as mock_log, \
         patch('tools.smoke_test.check_topic', return_value={'pass': False}) as mock_check_topic, \
         patch('tools.smoke_test.check_photo', return_value={'pass': True}) as mock_check_photo, \
         patch('tools.smoke_test.check_ball_correlation',
               return_value={'pass': True}) as mock_check_ball, \
         patch('tools.smoke_test.check_motion', return_value={'pass': True}) as mock_check_motion:
        mock_rclpy.create_node.return_value = MagicMock()
        result = run_smoke_test('robot_profiles/jetson_ugv_pt.yaml', ball_ops=MagicMock())

    assert result is False
    assert mock_check_topic.call_count == 4
    mock_check_photo.assert_called_once()
    mock_check_ball.assert_called_once()
    mock_check_motion.assert_called_once()
    mock_log.log_smoke_test_run.assert_called_once()
    assert mock_log.log_smoke_test_run.call_args.kwargs['overall_pass'] is False


def test_run_smoke_test_logs_full_checks_dict_and_passthrough_args():
    topic_results = [
        {'pass': True, 'measured_hz': 51.0},   # odom
        {'pass': True, 'measured_hz': 12.0},   # scan
        {'pass': False, 'measured_hz': 2.0},   # camera -- fails
        {'pass': True, 'measured_hz': 100.0},  # imu
    ]
    photo_result = {'pass': True, 'path': '/tmp/x.png', 'degenerate': False}
    ball_result = {'pass': True, 'lidar_min_range_m': 0.3}
    motion_result = {'pass': True, 'forward_delta_m': 0.05, 'turn_delta_rad': 0.2}

    with patch('tools.smoke_test.rclpy') as mock_rclpy, \
         patch('tools.smoke_test.smoke_test_log') as mock_log, \
         patch('tools.smoke_test.check_topic', side_effect=topic_results), \
         patch('tools.smoke_test.check_photo', return_value=photo_result), \
         patch('tools.smoke_test.check_ball_correlation', return_value=ball_result), \
         patch('tools.smoke_test.check_motion', return_value=motion_result):
        mock_rclpy.create_node.return_value = MagicMock()
        result = run_smoke_test('robot_profiles/jetson_ugv_pt.yaml', ball_ops=MagicMock(),
                                runner_type='hil_jetson', commit_sha='deadbeef',
                                ci_run_number=7, db_path='/tmp/other_smoke.db')

    assert result is False  # camera check failed -> overall FAIL
    mock_log.log_smoke_test_run.assert_called_once()
    kwargs = mock_log.log_smoke_test_run.call_args.kwargs
    assert kwargs['runner_type'] == 'hil_jetson'
    assert kwargs['commit_sha'] == 'deadbeef'
    assert kwargs['ci_run_number'] == 7
    assert kwargs['db_path'] == '/tmp/other_smoke.db'
    assert kwargs['overall_pass'] is False

    checks = kwargs['checks']
    assert checks['odom'] == topic_results[0]
    assert checks['scan'] == topic_results[1]
    assert checks['camera'] == topic_results[2]
    assert checks['imu'] == topic_results[3]
    assert checks['photo'] == photo_result
    assert checks['ball_correlation'] == ball_result
    assert checks['motion'] == motion_result
