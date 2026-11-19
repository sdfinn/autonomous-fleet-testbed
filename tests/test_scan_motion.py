# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""Pure Python + numpy — no rclpy import, runs in stage-1-quality.

Each test builds a small 2D room out of wall segments, "scans" it from two robot
poses with a simulated lidar, and checks that scan_motion recovers the move.
"""
import math

import numpy as np
import pytest

from nav_fleet.scan_motion import (
    MotionEstimate,
    estimate_translation,
    forward_distance,
    scan_to_points,
    surface_normals,
)

N_RAYS = 500
INC = 2 * math.pi / N_RAYS
RANGE_MIN, RANGE_MAX = 0.02, 12.0
LIDAR_X = 0.05

# A 4 x 3 m room with the robot near the middle: walls on all four sides.
ROOM = [((-2.0, -1.5), (2.0, -1.5)), ((2.0, -1.5), (2.0, 1.5)),
        ((2.0, 1.5), (-2.0, 1.5)), ((-2.0, 1.5), (-2.0, -1.5))]
# Two parallel walls much longer than the lidar's range: nothing ahead or behind.
CORRIDOR = [((-50.0, -0.6), (50.0, -0.6)), ((-50.0, 0.6), (50.0, 0.6))]


def fake_scan(walls, x, y, yaw, noise_m=0.0, seed=0):
    """Ranges a lidar at (x, y, yaw) would report for the given wall segments."""
    ranges = np.full(N_RAYS, np.inf)
    for i in range(N_RAYS):
        a = yaw + i * INC
        dx, dy = math.cos(a), math.sin(a)
        for (x1, y1), (x2, y2) in walls:
            ex, ey = x2 - x1, y2 - y1
            den = dx * ey - dy * ex
            if abs(den) < 1e-12:
                continue
            t = ((x1 - x) * ey - (y1 - y) * ex) / den      # distance along the ray
            u = ((x1 - x) * dy - (y1 - y) * dx) / den      # position along the wall
            if t > 0 and 0.0 <= u <= 1.0:
                ranges[i] = min(ranges[i], t)
    if noise_m:
        ranges = ranges + np.random.default_rng(seed).normal(0.0, noise_m, N_RAYS)
    return ranges


def pts(walls, x, y, yaw, **kw):
    return scan_to_points(fake_scan(walls, x, y, yaw, **kw), 0.0, INC, RANGE_MIN, RANGE_MAX)


def test_scan_to_points_drops_invalid_and_out_of_range_readings():
    ranges = [1.0, float('nan'), float('inf'), 0.05, 20.0, 2.0]
    p = scan_to_points(ranges, 0.0, math.radians(90), RANGE_MIN, RANGE_MAX)
    # kept: index 0 (bearing 0, 1 m) and index 5 (bearing 450 = 90 deg, 2 m)
    assert p.shape == (2, 2)
    assert p[0] == pytest.approx([1.0, 0.0], abs=1e-9)
    assert p[1] == pytest.approx([0.0, 2.0], abs=1e-9)


def test_scan_to_points_deskew_undoes_turning_during_the_sweep():
    # Robot turning left at 1 rad/s while the lidar sweeps: ray i is fired with the
    # robot already turned by i * dt, so it hits the room at yaw + i * dt.
    tinc, rate = 0.1 / N_RAYS, 1.0
    ranges = np.array([fake_scan(ROOM, 0.0, 0.0, i * tinc * rate)[i] for i in range(N_RAYS)])
    smeared = scan_to_points(ranges, 0.0, INC, RANGE_MIN, RANGE_MAX)
    fixed = scan_to_points(ranges, 0.0, INC, RANGE_MIN, RANGE_MAX,
                           time_increment=tinc, yaw_rates=np.full(N_RAYS, rate))

    def off_wall(p):
        """Distance of each point from the nearest wall of the 4 x 3 m room."""
        return np.minimum(np.abs(np.abs(p[:, 0]) - 2.0), np.abs(np.abs(p[:, 1]) - 1.5))

    assert off_wall(smeared).max() > 0.05      # the smear is real: walls look bent
    assert off_wall(fixed).max() < 0.005       # de-skewed points sit back on the walls


def test_surface_normals_point_across_a_wall_and_are_nan_at_a_corner():
    wall = np.column_stack((np.linspace(0.0, 0.5, 11), np.full(11, 2.0)))   # along x
    n = surface_normals(wall)
    assert abs(n[5, 1]) == pytest.approx(1.0, abs=1e-6)       # normal is +-y
    assert math.isnan(n[0, 0])                                # no neighbours at the end
    corner = np.vstack((wall, np.column_stack((np.full(10, 0.5), np.linspace(1.95, 1.5, 10)))))
    assert math.isnan(surface_normals(corner)[10, 0])         # the corner point itself


def test_stationary_robot_reads_as_no_motion():
    est = estimate_translation(pts(ROOM, 0.3, 0.1, 0.2, noise_m=0.01, seed=1),
                               pts(ROOM, 0.3, 0.1, 0.2, noise_m=0.01, seed=2), 0.0)
    assert abs(forward_distance(est, 0.0, LIDAR_X)) < 0.005
    assert est.forward_support > 50


@pytest.mark.parametrize('step', [0.02, 0.10, 0.15, -0.08])
def test_straight_move_is_recovered(step):
    est = estimate_translation(pts(ROOM, 0.0, 0.0, 0.0, noise_m=0.01, seed=1),
                               pts(ROOM, step, 0.0, 0.0, noise_m=0.01, seed=2), 0.0)
    assert forward_distance(est, 0.0, LIDAR_X) == pytest.approx(step, abs=0.005)
    assert abs(est.ty) < 0.005


def test_move_while_turning_is_recovered_about_base_link_not_the_lidar():
    # base_link drives a 0.10 m arc while turning 0.3 rad; the lidar sits 5 cm ahead
    # of base_link, so its own path differs from the robot's.
    yaw0, dth, dist = 0.4, 0.3, 0.10

    def lidar_pose(bx, by, yaw):
        return bx + LIDAR_X * math.cos(yaw), by + LIDAR_X * math.sin(yaw), yaw

    mid = yaw0 + dth / 2
    a = lidar_pose(0.2, -0.1, yaw0)
    b = lidar_pose(0.2 + dist * math.cos(mid), -0.1 + dist * math.sin(mid), yaw0 + dth)
    est = estimate_translation(pts(ROOM, *a, noise_m=0.005, seed=1),
                               pts(ROOM, *b, noise_m=0.005, seed=2), dth)
    assert forward_distance(est, dth, LIDAR_X) == pytest.approx(dist, abs=0.005)


def test_pure_spin_on_the_spot_reads_as_no_forward_motion():
    dth = 0.5
    a = (LIDAR_X, 0.0, 0.0)
    b = (LIDAR_X * math.cos(dth), LIDAR_X * math.sin(dth), dth)
    est = estimate_translation(pts(ROOM, *a), pts(ROOM, *b), dth)
    assert abs(forward_distance(est, dth, LIDAR_X)) < 0.005


def test_plain_corridor_reports_no_forward_support():
    # The trap this module must not fall into: the robot really moves 10 cm along a
    # featureless corridor, the scans are identical, and the matcher says "0 cm".
    # That answer is only acceptable alongside forward_support ~ 0 ("I cannot tell").
    est = estimate_translation(pts(CORRIDOR, 0.0, 0.0, 0.0, noise_m=0.005, seed=1),
                               pts(CORRIDOR, 0.10, 0.0, 0.0, noise_m=0.005, seed=2), 0.0)
    assert est.forward_support < 5
    assert abs(est.ty) < 0.005          # sideways is still well measured


def test_corridor_with_an_end_wall_is_measurable_again():
    walls = CORRIDOR + [((3.0, -0.6), (3.0, 0.6))]
    est = estimate_translation(pts(walls, 0.0, 0.0, 0.0, noise_m=0.005, seed=1),
                               pts(walls, 0.10, 0.0, 0.0, noise_m=0.005, seed=2), 0.0)
    assert est.forward_support > 10
    assert forward_distance(est, 0.0, LIDAR_X) == pytest.approx(0.10, abs=0.01)


def test_too_few_points_gives_no_answer():
    few = np.column_stack((np.linspace(0, 1, 10), np.ones(10)))
    assert estimate_translation(few, few, 0.0) is None
    assert estimate_translation(pts(ROOM, 0, 0, 0), few, 0.0) is None


def test_forward_distance_plain_arithmetic():
    est = MotionEstimate(tx=0.10, ty=0.0, matched_points=100, rms_m=0.0, forward_support=50.0)
    assert forward_distance(est, 0.0, LIDAR_X) == pytest.approx(0.10)


# --- SlipDetector -----------------------------------------------------------------

from nav_fleet.scan_motion import (  # noqa: E402  (grouped with the tests that use them)
    SlipDetector, VERDICT_IDLE, VERDICT_OK, VERDICT_SLIP, VERDICT_SUSPECT, VERDICT_UNKNOWN,
)

GOOD_SUPPORT = 100.0


def test_slip_detector_idle_when_wheels_are_stopped():
    assert SlipDetector().update(0.0, 0.004, GOOD_SUPPORT, 0.5) == VERDICT_IDLE


def test_slip_detector_ok_when_wheels_and_walls_agree():
    d = SlipDetector()
    assert d.update(0.25, 0.24, GOOD_SUPPORT, 0.5) == VERDICT_OK
    assert d.update(-0.20, -0.19, GOOD_SUPPORT, 0.5) == VERDICT_OK     # reversing
    assert d.phantom_distance_m == 0.0


def test_slip_detector_needs_two_windows_then_counts_phantom_distance():
    d = SlipDetector()
    assert d.update(0.28, 0.01, GOOD_SUPPORT, 0.5) == VERDICT_SUSPECT
    assert d.update(0.28, 0.01, GOOD_SUPPORT, 0.5) == VERDICT_SLIP
    assert d.update(0.28, 0.01, GOOD_SUPPORT, 0.5) == VERDICT_SLIP
    assert d.phantom_distance_m == pytest.approx(2 * 0.27 * 0.5)


def test_slip_detector_single_low_window_while_pulling_away_is_not_slip():
    d = SlipDetector()
    assert d.update(0.14, 0.04, GOOD_SUPPORT, 0.5) == VERDICT_SUSPECT
    assert d.update(0.25, 0.24, GOOD_SUPPORT, 0.5) == VERDICT_OK
    assert d.update(0.25, 0.05, GOOD_SUPPORT, 0.5) == VERDICT_SUSPECT   # streak restarted


def test_slip_detector_refuses_to_judge_without_forward_support():
    # The corridor case: lidar says "0 m/s" but cannot actually tell. Must not be slip.
    d = SlipDetector()
    for _ in range(5):
        assert d.update(0.25, 0.0, 3.0, 0.5) == VERDICT_UNKNOWN
    assert d.update(0.25, None, 0.0, 0.5) == VERDICT_UNKNOWN
    assert d.phantom_distance_m == 0.0


def test_slip_detector_unknown_window_does_not_reset_a_running_streak():
    d = SlipDetector()
    assert d.update(0.28, 0.0, GOOD_SUPPORT, 0.5) == VERDICT_SUSPECT
    assert d.update(0.28, None, 0.0, 0.5) == VERDICT_UNKNOWN
    assert d.update(0.28, 0.0, GOOD_SUPPORT, 0.5) == VERDICT_SLIP


def test_slip_detector_rolling_backwards_while_driving_forward_is_slip():
    d = SlipDetector()
    d.update(0.20, -0.05, GOOD_SUPPORT, 0.5)
    assert d.update(0.20, -0.05, GOOD_SUPPORT, 0.5) == VERDICT_SLIP


# --- SlipMonitorCore: the buffered pipeline, driven like the robot drives it --------

from nav_fleet.scan_motion import SlipMonitorCore  # noqa: E402


def drive(core, wheel_speed, true_speed, seconds, t0=0.0, x0=0.0):
    """Feed `seconds` of 20 Hz wheel/gyro samples and 10 Hz scans; return the results."""
    out = []
    for tick in range(int(seconds * 20) + 1):
        t = t0 + tick * 0.05
        core.add_wheel_speed(t, wheel_speed)
        core.add_yaw_rate(t, 0.0)
        if tick % 2 == 0:
            ranges = fake_scan(ROOM, x0 + true_speed * (t - t0), 0.0, 0.0,
                               noise_m=0.005, seed=tick)
            r = core.add_scan(t, ranges, 0.0, INC, RANGE_MIN, RANGE_MAX, 0.1 / N_RAYS)
            if r is not None:
                out.append(r)
    return out


def test_core_emits_one_result_per_window_and_agrees_when_really_driving():
    res = drive(SlipMonitorCore(lidar_x=0.0), wheel_speed=0.2, true_speed=0.2, seconds=3.0)
    assert len(res) == 6                                   # 30 scans / 5 per window
    assert all(r.verdict == VERDICT_OK for r in res)
    assert all(r.window_s == pytest.approx(0.5) for r in res)
    assert all(r.lidar_speed == pytest.approx(0.2, abs=0.02) for r in res)
    assert res[-1].phantom_distance_m == 0.0


def test_core_calls_slip_when_wheels_turn_and_the_room_does_not_move():
    res = drive(SlipMonitorCore(lidar_x=0.0), wheel_speed=0.25, true_speed=0.0, seconds=3.0)
    assert [r.verdict for r in res][:3] == [VERDICT_SUSPECT, VERDICT_SLIP, VERDICT_SLIP]
    # 5 confirmed slip windows x 0.5 s x 0.25 m/s
    assert res[-1].phantom_distance_m == pytest.approx(5 * 0.5 * 0.25, abs=0.03)


def test_core_stays_silent_without_gyro_or_wheel_samples():
    core = SlipMonitorCore(lidar_x=0.0)
    for i in range(12):
        assert core.add_scan(i * 0.1, fake_scan(ROOM, 0, 0, 0), 0.0, INC, RANGE_MIN, RANGE_MAX,
                             0.1 / N_RAYS) is None


def test_core_skips_a_window_that_spans_dropped_scans():
    core = SlipMonitorCore(lidar_x=0.0)
    drive(core, 0.2, 0.2, 1.0)
    # 5 s with no scans at all, then scans resume: the first window back must be skipped
    res = drive(core, 0.2, 0.2, 0.3, t0=6.0, x0=1.2)
    assert res == []
