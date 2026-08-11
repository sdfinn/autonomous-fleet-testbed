# tools/smoke_test.py
# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""Bench smoke-test orchestrator (design spec §tools/smoke_test.py). Attended, bench-
side sanity check for the driver layer: topic Hz/sanity, one photo, a known-distance
ball correlation check, and an odom-verified motion pulse — BEFORE the driver layer is
ever trusted under Nav2. Interactive prompting is deliberate here (unlike
mission_runner's hard no-prompting rule) — a human runs this standing at the bench.

Run: python -m tools.smoke_test [--ball-ops operator|gz] [--runner-type local] ...

2026-08-09: distance/height/tolerance/HIL-skip fixes landed and verified green on
real Jetson hardware (see CLAUDE.md and RealRobotStartup.md for the full history) —
this comment-only line exists solely to re-trigger the full CI pipeline (stage-3-arm64
+ stage-4-hil, which the docs-only commits right before it correctly skipped) for one
more full end-to-end confirmation before the robot gets unpacked.

2026-08-10: camera_relay (closes the camera half of the topic-remapping gap) and the
real-measured bench ball-placement height (LIDAR_HEIGHT_REAL_M, corrected from a
sim-URDF-derived guess) both landed and were verified green end to end, including a
real HIL mission day on the Jetson (run 31453495866) — this comment-only line exists
solely to re-trigger the full pipeline once more for a clean, uncomplicated
confirmation, same reason as the 2026-08-09 line above.
"""
import argparse
import math
import pathlib
import sys
import time

import numpy as np
import rclpy
import yaml
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from sensor_msgs.msg import Image, Imu, LaserScan
from vision_msgs.msg import Detection2DArray

from nav_fleet.ground_truth import get_ground_truth_xy
from nav_fleet.image_io import image_msg_to_png, image_msg_to_rgb
from tools.mission2_day import GzBallOps, SPAWN_APPEAR_SETTLE_S
from tools.mission2_harness import spawn_lidar_ball
from tools.telemetry_logger import PHOTO_DIR
from tools import smoke_test_log

REPO_DIR = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_PROFILE = str(REPO_DIR / 'robot_profiles' / 'jetson_ugv_pt.yaml')

# 0.75 m (~2.5 ft), not the design spec's original 12"/0.305 m -- raised 2026-08-09
# after a confirmed root-cause: at 12", a floor-level ball sits geometrically outside
# the level-mounted camera's vertical field of view (real URDF geometry: camera
# 0.175 m forward of base, ~0.24 m high, ~23.4 deg vertical half-FOV -- the look-down
# angle needed at 12" is ~56.6 deg, more than double that). 0.75 m keeps real margin
# (~18-19 deg, comfortably inside the FOV) while staying well short of Mission 2's own
# 0.8-1.3 m reaction range, so this stays a visually/physically distinct close-bench
# check, not a copy of Mission 2's numbers.
KNOWN_DISTANCE_M = 0.75
DISTANCE_TOLERANCE_M = 0.102   # ~4 inches placement-imprecision tolerance — design spec §3
FORWARD_ARC_HALF_WIDTH_RAD = math.radians(15)
# True forward bearing, in the RAW lidar's own bearing convention (angle_min=0 at
# the lidar's physical zero, NOT the robot's forward) -- found empirically 2026-08-10
# (RealRobotStartup.md A2): placed a known object at true forward (the same
# direction the pinned-forward gimbal looks) and read back the lidar's own reported
# bearing for it. The URDF's lidar_joint has zero rotation (no rpy set) -- nothing
# else in the stack corrects for this, so any code reading the RAW scan message
# directly (not via TF) must apply this offset itself. Real bug found + fixed
# 2026-08-11: this smoke test's own _forward_arc_min_range checked around raw
# bearing 0 (never applying this offset), so it was reading whatever's nearest to
# the WRONG direction entirely -- root cause of a live ball_correlation FAIL where
# the reported "lidar distance" (0.511m) didn't match the true placement (0.75m).
TRUE_FORWARD_BEARING_RAD = math.radians(285)

# check_topic()'s hz_min values (robot_profiles/*.yaml) are each sensor's own nominal
# publish rate with zero slack -- found live in CI, 2026-08-09 (run 31332673543): a
# genuinely-fine 10 Hz camera measured 9.67 Hz over a 3.0s window (29 msgs, not 30)
# purely from timing-phase luck around the window boundary -- re-running the identical
# stack passed cleanly. A real sensor problem (dead/hung publisher) reads as a rate
# far below nominal, not 3% under it -- this tolerance absorbs window-boundary jitter
# without hiding an actually-broken sensor. Applies to every check_topic() call
# (odom/scan/camera/imu all hit this same zero-tolerance design, not just camera).
HZ_TOLERANCE_FACTOR = 0.9

# This robot's lidar (sim and the real ldlidar_ros2 hardware) is a 2D PLANAR lidar —
# one fixed horizontal scan plane, no vertical resolution at all (confirmed live,
# 2026-08-09: a ball resting on the floor was undetectable at any distance, even after
# adding real <collision> geometry — the beam was simply passing entirely over it).
# Placing the ball's CENTER at the scan plane's own height means the plane passes
# straight through it, with the ball's own radius as margin either side.
#
# SIM ball spawn height (LidarVisibleGzBallOps, below) — the plane sits ~0.25 m off
# the ground per the SIMULATED URDF's own geometry: spawn z 0.15 m + the lidar
# joint's own 0.1 m local mount offset (ugv_pt.urdf.xacro). This is the sim
# geometry's number, already validated by the sim-side ball correlation check —
# don't change it to "fix" the real-bench number below, they're deliberately
# different constants for deliberately different physical setups.
LIDAR_HEIGHT_M = 0.25

# REAL bench ball-placement height (OperatorPlaceBallOps, below) — measured directly
# against the real hardware, 2026-08-10 (Mike's own visual inspection: "about 6
# inches", corrected from an earlier, wrong assumption that the sim URDF's 0.25 m/
# 10in figure would also hold on the real chassis — it doesn't; the two mounts
# aren't at the same height). On the real bench, this means an actual physical
# riser/box under the ball — OperatorPlaceBallOps's prompt below says so explicitly.
LIDAR_HEIGHT_REAL_M = 0.1524


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
    hz_min * HZ_TOLERANCE_FACTOR (absorbs window-boundary timing jitter — see that
    constant's own comment) AND the most recently received message is not degenerate
    per degenerate_fn. Returns {'pass', 'measured_hz', 'message_count', 'degenerate'
    (None if zero messages received)}."""
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
    passed = measured_hz >= hz_min * HZ_TOLERANCE_FACTOR and degenerate is False
    return {'pass': passed, 'measured_hz': round(measured_hz, 2),
            'message_count': state['count'], 'degenerate': degenerate}


class OperatorPlaceBallOps:
    """Bench smoke test: lighter than mission2_day.py's BallOps contract (design spec
    §3) — a single place() only, no remove()/swap choreography needed. The operator's
    hands are the actuator; smoke_test.py waits for them."""

    def place(self, color, distance_m):
        inches = distance_m * 39.37
        height_inches = LIDAR_HEIGHT_REAL_M * 39.37
        input(f"Place the {color} ball {inches:.0f} inches ({distance_m:.3f} m) "
              f"directly in front of the robot, ON A RISER/BOX so its CENTER sits "
              f"~{height_inches:.0f} inches ({LIDAR_HEIGHT_REAL_M:.2f} m) off the bench "
              f"surface (the lidar's own scan height — a floor-level ball is below "
              f"its single scan plane and won't be seen), then press Enter: ")


class LidarVisibleGzBallOps(GzBallOps):
    """check_ball_correlation's own sim/CI ball placement — a GzBallOps subclass so
    check_ball_correlation's isinstance(ball_ops, GzBallOps) branch (ground-truth-based
    placement math) still applies, but place() spawns via mission2_harness's
    LIDAR_BALL_SDF/spawn_lidar_ball instead of Mission 2's own camera-only ball.
    Root cause (2026-08-09, confirmed live): this robot's lidar is a 2D PLANAR lidar
    (one fixed scan height, no vertical resolution) — a floor-level ball sits entirely
    below its scan plane, undetectable at any distance regardless of collision/visual
    geometry. Spawns the ball's center at LIDAR_HEIGHT_M (the lidar's own scan height)
    instead of on the floor, matching the real bench test's riser/box requirement."""

    def place(self, color, x, y):
        name = spawn_lidar_ball(color, x, y, z=LIDAR_HEIGHT_M)
        print(f'gz spawned lidar-visible {name} at ({x}, {y}, {LIDAR_HEIGHT_M})')
        time.sleep(SPAWN_APPEAR_SETTLE_S)
        return name


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
        ts = time.strftime('%Y%m%dT%H%M%S')
        out_path = str(pathlib.Path(PHOTO_DIR) / f"smoke_test_{ts}.png")
    image_msg_to_png(state['msg'], out_path)
    degenerate = is_degenerate_image(image_msg_to_rgb(state['msg']))
    exists = pathlib.Path(out_path).exists()
    return {'pass': bool(exists and not degenerate), 'path': out_path if exists else None,
            'degenerate': degenerate}


def _forward_arc_min_range(msg, half_width_rad=FORWARD_ARC_HALF_WIDTH_RAD,
                           forward_bearing_rad=TRUE_FORWARD_BEARING_RAD):
    """Minimum finite, positive range within +/- half_width_rad of TRUE forward
    (forward_bearing_rad, in the scan's own RAW bearing convention — NOT the scan's
    bearing 0, which is the lidar's physical zero, not the robot's forward; see
    TRUE_FORWARD_BEARING_RAD's own comment) — restricting to the forward arc so an
    object beside or behind the robot isn't mistaken for the ball placed in front of
    it. Uses atan2-based angle normalization (not a plain subtraction) so the
    +/-half_width_rad window is correctly evaluated even when it straddles the
    scan's own 0/2pi wraparound seam."""
    best = None
    angle = msg.angle_min
    for r in msg.ranges:
        delta = math.atan2(math.sin(angle - forward_bearing_rad),
                           math.cos(angle - forward_bearing_rad))
        if -half_width_rad <= delta <= half_width_rad and math.isfinite(r) and r > 0.0:
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
        if truth is None:
            # 'skipped' (not just 'pass': False) distinguishes "couldn't judge" from
            # "judged and failed" -- found live in CI, 2026-08-09 (stage-4-hil run
            # 31333381064): the HIL-container path runs on the Jetson, which can
            # never reach Gazebo's ground truth (that only exists on the
            # workstation) -- a structural limitation of that specific path, not a
            # real sensor/driver fault. ball_correlation is already exercised for
            # real, with real ground truth, by stage-2-gazebo (sim) -- Mike's call:
            # keep this simple, don't drag down overall_pass for a check that
            # genuinely cannot run here.
            return {
                'pass': False,
                'skipped': True,
                'reason': 'no ground truth available (Gazebo not running?)',
                'lidar_min_range_m': None,
                'known_distance_m': known_distance_m,
                'yellow_ball_detected': False,
                'camera_estimated_range_m': None,
            }
        rx, ry = truth
        ryaw = math.pi / 2
        bx, by = compute_ball_placement_xy(rx, ry, ryaw, known_distance_m)
        ball_ops.place('yellow', bx, by)
        # Sim/Gazebo's own lidar sensor has NO physical mounting error -- the
        # ros_gz_bridge's bearing 0 genuinely IS the robot's forward, matching
        # compute_ball_placement_xy's own placement math above. TRUE_FORWARD_
        # BEARING_RAD (285deg) is a REAL-HARDWARE-ONLY correction for this exact
        # robot's actual, uncorrected lidar_joint rotation (RealRobotStartup.md
        # A2) -- applying it here would break sim, which was never broken. Found
        # live in CI, 2026-08-11 (stage-2-gazebo run 31522807860): this exact
        # regression, the FIRST real exercise of the bearing fix outside the real
        # Jetson, caught immediately by the sim smoke-test regression step.
        forward_bearing_rad = 0.0
    else:
        ball_ops.place('yellow', known_distance_m)
        forward_bearing_rad = TRUE_FORWARD_BEARING_RAD

    scan_state = {'min_range': None}
    det_state = {'yellow_range_m': None}

    def _scan_cb(msg):
        r = _forward_arc_min_range(msg, forward_bearing_rad=forward_bearing_rad)
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


MOTION_FORWARD_S = 1.0
MOTION_TURN_S = 1.0
# Retuned 2026-08-11 (Mike's ask, same bench smoke test session as the direction-bug
# fix): target ~1 inch forward / ~20deg turn, at PASS-time human-observable scale
# rather than the old ~5.9in/~28.6deg defaults — holding the SAME 1.0s pulse
# duration validated across this whole session rather than shortening it, since a
# shorter one-shot burst risks losing most of its motion to the documented ~1.2s
# command-to-motion startup delay (RealRobotStartup.md A2 finding).
MOTION_FORWARD_MPS = 0.0254 / MOTION_FORWARD_S    # ~1 inch over MOTION_FORWARD_S
MOTION_TURN_RADPS = math.radians(20) / MOTION_TURN_S    # ~20deg over MOTION_TURN_S
# Thresholds lowered proportionally (~40% of the new, smaller targets) so the check
# stays meaningful at this scale — the OLD 0.03m/5deg thresholds were themselves
# larger than the NEW 1in/20deg targets, which would have made this check
# structurally unpassable. Still generous — a sanity check, not a calibration
# (design spec §4).
MOTION_MIN_DELTA_M = 0.0254 * 0.4      # ~0.4 inches
MOTION_MIN_DELTA_RAD = math.radians(20) * 0.4    # ~8 degrees


def _latest_odom(node, timeout_s=2.0):
    state = {'msg': None}

    def _cb(msg):
        state['msg'] = msg

    sub = node.create_subscription(Odometry, '/robot_001/odom', _cb, 10)
    deadline = time.time() + timeout_s
    while state['msg'] is None and time.time() < deadline:
        rclpy.spin_once(node, timeout_sec=0.1)
    node.destroy_subscription(sub)
    return state['msg']


def _yaw_from_quat(q):
    return math.atan2(2.0 * (q.w * q.z), 1.0 - 2.0 * (q.z * q.z))


def _publish_for(node, cmd_pub, twist, duration_s, rate_hz=10.0):
    deadline = time.time() + duration_s
    period = 1.0 / rate_hz
    while time.time() < deadline:
        cmd_pub.publish(twist)
        rclpy.spin_once(node, timeout_sec=period)


def check_motion(node, cmd_pub):
    """Design spec §4: two short open-loop cmd_vel pulses (forward, then a turn),
    /robot_001/odom read before and after each. PASS requires: (a) the forward pulse
    produces a genuinely FORWARD (not just nonzero) displacement, resolved along the
    robot's own heading BEFORE the pulse — plain math.hypot() can't distinguish
    forward from backward, and this exact gap let a real backward-motion sign-
    inversion bug through undetected on 2026-08-11 (caught only by an operator
    watching the robot, not by this check); (b) the turn pulse produces a
    non-trivial turn delta. A generous sanity check, not a calibration. Operator
    visual confirmation is still recommended (catches e.g. wheels spinning but the
    chassis stuck)."""
    before = _latest_odom(node)
    if before is None:
        return {'pass': False, 'reason': 'no odom before motion check'}
    yaw_before_forward = _yaw_from_quat(before.pose.pose.orientation)

    forward = Twist()
    forward.linear.x = MOTION_FORWARD_MPS
    _publish_for(node, cmd_pub, forward, MOTION_FORWARD_S)
    cmd_pub.publish(Twist())
    time.sleep(0.5)
    after_forward = _latest_odom(node)

    turn = Twist()
    turn.angular.z = MOTION_TURN_RADPS
    _publish_for(node, cmd_pub, turn, MOTION_TURN_S)
    cmd_pub.publish(Twist())
    time.sleep(0.5)
    after_turn = _latest_odom(node)

    if after_forward is None or after_turn is None:
        return {'pass': False, 'reason': 'no odom after motion pulses'}

    dx = after_forward.pose.pose.position.x - before.pose.pose.position.x
    dy = after_forward.pose.pose.position.y - before.pose.pose.position.y
    # Resolved along the robot's OWN heading at the start of the forward pulse --
    # positive means genuinely forward, negative means backward. Unlike a plain
    # math.hypot() (magnitude only, always >= 0), this can actually FAIL a real
    # backward-motion regression instead of silently passing it (see this
    # function's own docstring).
    forward_delta_m = (dx * math.cos(yaw_before_forward) +
                       dy * math.sin(yaw_before_forward))

    yaw_before_turn = _yaw_from_quat(after_forward.pose.pose.orientation)
    yaw_after_turn = _yaw_from_quat(after_turn.pose.pose.orientation)
    turn_delta_rad = abs(math.atan2(math.sin(yaw_after_turn - yaw_before_turn),
                                    math.cos(yaw_after_turn - yaw_before_turn)))

    return {'pass': bool(forward_delta_m >= MOTION_MIN_DELTA_M and
                         turn_delta_rad >= MOTION_MIN_DELTA_RAD),
            'forward_delta_m': round(forward_delta_m, 3),
            'turn_delta_rad': round(turn_delta_rad, 3)}


def _is_degenerate_odom(msg):
    """NaN/inf in pose or twist — a genuinely broken publisher. A legitimately
    stationary robot has an all-zero pose/twist (this integrator starts at the
    origin), so all-zero is deliberately NOT treated as degenerate — only non-finite
    values are."""
    p, t = msg.pose.pose.position, msg.twist.twist
    values = (p.x, p.y, p.z, t.linear.x, t.linear.y, t.linear.z,
              t.angular.x, t.angular.y, t.angular.z)
    return not all(math.isfinite(v) for v in values)


def _is_degenerate_image_msg(msg):
    return is_degenerate_image(image_msg_to_rgb(msg))


def _is_degenerate_imu(msg):
    values = (msg.angular_velocity.x, msg.angular_velocity.y, msg.angular_velocity.z,
              msg.linear_acceleration.x, msg.linear_acceleration.y, msg.linear_acceleration.z)
    return not all(math.isfinite(v) for v in values)


def _print_summary(checks, overall_pass):
    print("=== Smoke test summary ===")
    for name, result in checks.items():
        if result.get('skipped'):
            status = 'SKIP'
        elif result.get('pass'):
            status = 'PASS'
        else:
            status = 'FAIL'
        print(f"[{status}] {name}: {result}")
    print(f"=== Overall: {'PASS' if overall_pass else 'FAIL'} ===")


def run_smoke_test(profile_path, ball_ops, runner_type='local', commit_sha=None,
                   ci_run_number=None, db_path=None):
    """Design spec §5: run every check regardless of earlier failures (the checklist
    IS the verdict, matching mission_runner's own philosophy), print an itemized
    summary, log one row, return overall PASS/FAIL."""
    profile = load_robot_profile(profile_path)
    sensors = profile['sensors']

    rclpy.init()
    node = rclpy.create_node('smoke_test')
    cmd_pub = node.create_publisher(Twist, '/robot_001/cmd_vel', 10)
    checks = {}
    try:
        checks['odom'] = check_topic(node, sensors['odometry']['topic'], Odometry,
                                     sensors['odometry']['hz_min'], _is_degenerate_odom)
        checks['scan'] = check_topic(node, sensors['lidar']['topic'], LaserScan,
                                     sensors['lidar']['hz_min'], is_degenerate_scan)
        checks['camera'] = check_topic(node, sensors['camera']['topic'], Image,
                                       sensors['camera']['hz_min'], _is_degenerate_image_msg)
        checks['imu'] = check_topic(node, sensors['imu']['topic'], Imu,
                                    sensors['imu']['hz_min'], _is_degenerate_imu)
        checks['photo'] = check_photo(node)
        checks['ball_correlation'] = check_ball_correlation(node, ball_ops)
        checks['motion'] = check_motion(node, cmd_pub)
    finally:
        node.destroy_node()
        rclpy.shutdown()

    # Skipped checks (couldn't judge -- e.g. no ground truth reachable from the HIL
    # container) don't count toward overall_pass either way; a real failure still
    # does. See check_ball_correlation's own comment for why this exists.
    overall_pass = all(c.get('pass', False) for c in checks.values() if not c.get('skipped'))
    _print_summary(checks, overall_pass)

    smoke_test_log.log_smoke_test_run(
        runner_type=runner_type, overall_pass=overall_pass, checks=checks,
        commit_sha=commit_sha, ci_run_number=ci_run_number,
        db_path=db_path or smoke_test_log.DB_PATH)
    return overall_pass


def main():
    parser = argparse.ArgumentParser(
        description="Bench smoke test — driver-layer sanity check before Nav2 trusts it")
    parser.add_argument('--profile', default=DEFAULT_PROFILE)
    parser.add_argument('--ball-ops', choices=['gz', 'operator'], default='operator')
    parser.add_argument('--runner-type', default='local')
    parser.add_argument('--commit-sha', default=None)
    parser.add_argument('--ci-run-number', type=int, default=None)
    parser.add_argument('--db', default=None)
    args = parser.parse_args()

    ball_ops = LidarVisibleGzBallOps() if args.ball_ops == 'gz' else OperatorPlaceBallOps()
    overall_pass = run_smoke_test(
        args.profile, ball_ops, runner_type=args.runner_type, commit_sha=args.commit_sha,
        ci_run_number=args.ci_run_number, db_path=args.db)
    sys.exit(0 if overall_pass else 1)


if __name__ == '__main__':
    main()
