# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""Pure Python — no rclpy import, runs in stage-1-quality like test_esp32_protocol.py."""
import math

import pytest

from nav_fleet.scan_filter import mask_scan_values, parse_mask_sectors, rotate_scan_frame


def test_mask_scan_values_leaves_readings_outside_sectors_untouched():
    ranges = [1.0, 1.0, 1.0, 1.0]
    # 4 readings spanning 0-360deg in 90deg steps: bearings 0, 90, 180, 270
    masked = mask_scan_values(ranges, angle_min=0.0, angle_increment=math.radians(90),
                              mask_sectors_deg=[(45.0, 135.0)])
    assert masked[0] == 1.0    # bearing 0 — outside
    assert math.isnan(masked[1])  # bearing 90 — inside (45-135)
    assert masked[2] == 1.0    # bearing 180 — outside
    assert masked[3] == 1.0    # bearing 270 — outside


def test_mask_scan_values_masks_multiple_non_contiguous_sectors():
    # This project's real case: mast (46-123deg) and antenna (268-277deg) — the
    # vendor driver's own angle_crop only supports ONE contiguous arc (confirmed
    # against ldlidar_ros2/src/demo.cpp), which is exactly why this function exists.
    ranges = [1.0] * 8
    # bearings: 0, 45, 90, 135, 180, 225, 270, 315
    masked = mask_scan_values(ranges, angle_min=0.0, angle_increment=math.radians(45),
                              mask_sectors_deg=[(46.0, 123.0), (268.0, 277.0)])
    assert masked[0] == 1.0        # 0 — clear
    assert masked[1] == 1.0        # 45 — just outside 46-123
    assert math.isnan(masked[2])   # 90 — inside 46-123
    assert masked[3] == 1.0        # 135 — just outside 46-123
    assert masked[4] == 1.0        # 180 — clear
    assert masked[5] == 1.0        # 225 — clear
    assert math.isnan(masked[6])   # 270 — inside 268-277
    assert masked[7] == 1.0        # 315 — clear


def test_mask_scan_values_boundary_inclusive():
    ranges = [1.0, 1.0]
    masked = mask_scan_values(ranges, angle_min=math.radians(46.0), angle_increment=0.0,
                              mask_sectors_deg=[(46.0, 123.0)])
    # Both readings sit at exactly 46deg (angle_increment=0.0) — the boundary itself
    # must be masked, not treated as just-outside (an off-by-one here would silently
    # leave the mast's own edge visible).
    assert math.isnan(masked[0])
    assert math.isnan(masked[1])


def test_mask_scan_values_handles_wraparound_sector():
    # A sector where lo > hi wraps across the 0/360 seam (e.g. 350-10 covers dead
    # ahead) — not this project's current two sectors, but a real case the function
    # must not silently mishandle if a sector is ever added that straddles 0deg.
    ranges = [1.0, 1.0, 1.0]
    masked = mask_scan_values(ranges, angle_min=math.radians(350.0),
                              angle_increment=math.radians(20.0),
                              mask_sectors_deg=[(350.0, 10.0)])
    # bearings: 350, 10, 30
    assert math.isnan(masked[0])   # 350 — inside (wraps)
    assert math.isnan(masked[1])   # 10 — inside (wraps)
    assert masked[2] == 1.0        # 30 — outside


def test_mask_scan_values_preserves_non_finite_readings():
    # A pre-existing NaN/inf reading (no return, out of range_max, etc.) outside any
    # masked sector must pass through unchanged, not become a spurious 1.0 or crash.
    ranges = [float('inf'), float('nan')]
    masked = mask_scan_values(ranges, angle_min=0.0, angle_increment=math.radians(180),
                              mask_sectors_deg=[(46.0, 123.0)])
    assert math.isinf(masked[0])
    assert math.isnan(masked[1])


def test_mask_scan_values_does_not_mutate_input():
    ranges = [1.0, 1.0]
    mask_scan_values(ranges, angle_min=0.0, angle_increment=math.radians(90),
                     mask_sectors_deg=[(46.0, 123.0)])
    assert ranges == [1.0, 1.0]


def test_parse_mask_sectors_pairs_up_flat_list():
    # ROS2 params don't support a list-of-tuples type — a flat double array
    # ([lo1, hi1, lo2, hi2, ...]) is the only clean way to expose N sectors as one
    # parameter; this converts that wire format into the pair-tuple form
    # mask_scan_values expects.
    assert parse_mask_sectors([46.0, 123.0, 268.0, 277.0]) == [(46.0, 123.0), (268.0, 277.0)]


def test_parse_mask_sectors_empty_list():
    assert parse_mask_sectors([]) == []


def test_parse_mask_sectors_odd_length_raises():
    # An odd-length flat list means a misconfigured launch arg/param — fail loudly
    # rather than silently drop the trailing value.
    import pytest
    with pytest.raises(ValueError):
        parse_mask_sectors([46.0, 123.0, 268.0])


# --- rotate_scan_frame: make the published scan's angle 0 = the ROBOT's forward ---
# Real-robot bug, 2026-11-16: the lidar is mounted rotated (true forward is raw
# bearing ~269deg; these tests use 285 purely as a worked example), but the scan was published in lidar_link (zero rotation in the URDF) with
# its raw angles, so Nav2/AMCL/costmaps saw the whole room rotated by 75deg.

def test_rotate_scan_frame_puts_true_forward_at_angle_zero():
    # Raw scan: angle_min=0, 360 readings 1deg apart. An object at raw index 285
    # (raw bearing 285deg) must end up at published angle 0 (dead ahead).
    inc = math.radians(1.0)
    new_min, new_max = rotate_scan_frame(0.0, 359 * inc, 285.0)
    angle_of_index_285 = new_min + 285 * inc
    assert math.atan2(math.sin(angle_of_index_285),
                      math.cos(angle_of_index_285)) == pytest.approx(0.0, abs=1e-9)


def test_rotate_scan_frame_keeps_left_on_the_left():
    # REP-103: +angle = counter-clockwise = robot's LEFT. With forward at raw 285,
    # the robot's left is raw 285+90 = 15deg; it must publish at +90deg, not -90.
    inc = math.radians(1.0)
    new_min, _ = rotate_scan_frame(0.0, 359 * inc, 285.0)
    a = new_min + 15 * inc
    assert math.degrees(math.atan2(math.sin(a), math.cos(a))) == pytest.approx(90.0)


def test_rotate_scan_frame_preserves_span_and_normalizes_angle_min():
    inc = math.radians(0.72)
    span = 502 * inc
    new_min, new_max = rotate_scan_frame(0.0, span, 285.0)
    assert new_max - new_min == pytest.approx(span)
    assert -math.pi < new_min <= math.pi        # 0 - 285deg wraps to +75deg
    assert math.degrees(new_min) == pytest.approx(75.0)


def test_rotate_scan_frame_zero_bearing_is_a_no_op():
    assert rotate_scan_frame(0.1, 6.0, 0.0) == (pytest.approx(0.1), pytest.approx(6.0))
