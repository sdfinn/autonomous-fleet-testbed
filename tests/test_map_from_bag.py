# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""Pure Python + numpy — tools/map_from_bag.py imports ROS only inside main()."""
import math

import pytest

from tools.map_from_bag import (
    FIXED_BEAMS, DeadReckoner, resample_scan, resting_gyro_offset,
)


@pytest.mark.parametrize('n_in', [500, 502, 503, 505])
def test_resample_always_returns_the_fixed_beam_count(n_in):
    # The LD19 delivers 500-505 readings per turn; slam_toolbox needs the same count
    # every time.
    ranges, amin, inc, amax = resample_scan([2.0] * n_in, 1.588, 2 * math.pi / n_in)
    assert len(ranges) == FIXED_BEAMS
    assert amin == pytest.approx(-math.pi)
    assert inc == pytest.approx(2 * math.pi / FIXED_BEAMS)
    assert amax == pytest.approx(amin + (FIXED_BEAMS - 1) * inc)
    assert all(r == 2.0 for r in ranges)


def test_resample_keeps_each_reading_at_its_bearing():
    # A scan that starts at +91 deg (like the rotated real one): one near object dead
    # ahead (bearing 0), everything else far.
    n = 360
    inc = math.radians(1.0)
    amin = math.radians(91.0)
    ranges = [5.0] * n
    ranges[269] = 0.7          # 91 + 269 = 360 deg = dead ahead
    out, out_min, out_inc, _ = resample_scan(ranges, amin, inc)
    nearest = min(range(FIXED_BEAMS), key=lambda i: out[i])
    assert out[nearest] == 0.7
    assert out_min + nearest * out_inc == pytest.approx(0.0, abs=math.radians(1.0))


def test_resample_turns_nan_and_inf_into_no_return_without_spreading_them():
    n = 500
    ranges = [3.0] * n
    ranges[10] = float('nan')
    ranges[20] = float('inf')
    out, _, _, _ = resample_scan(ranges, -math.pi, 2 * math.pi / n)
    assert sum(1 for r in out if math.isinf(r)) == 2
    assert not any(math.isnan(r) for r in out)


def test_resample_does_not_blend_a_wall_with_the_gap_beside_it():
    n = 250                                   # coarser than the output grid
    ranges = [1.0] * 125 + [6.0] * 125
    out, _, _, _ = resample_scan(ranges, -math.pi, 2 * math.pi / n)
    assert set(out) == {1.0, 6.0}             # never a made-up 3.5


def test_dead_reckoner_drives_straight_along_its_start_heading():
    dr = DeadReckoner(x=-1.276, y=1.2, yaw=math.radians(90))
    for i in range(21):                       # 1 s at 20 Hz, 0.2 m/s
        dr.on_gyro(0.0)
        x, y, yaw = dr.on_wheel_speed(i * 0.05, 0.2)
    assert (x, y) == pytest.approx((-1.276, 1.4), abs=1e-6)
    assert yaw == pytest.approx(math.radians(90))


def test_dead_reckoner_follows_a_quarter_circle():
    dr = DeadReckoner()
    speed, rate = 0.2, 0.4                    # radius 0.5 m
    steps = int(round((math.pi / 2) / rate / 0.01))
    for i in range(steps + 1):
        dr.on_gyro(rate)
        x, y, yaw = dr.on_wheel_speed(i * 0.01, speed)
    assert yaw == pytest.approx(math.pi / 2, abs=0.01)
    assert (x, y) == pytest.approx((0.5, 0.5), abs=0.01)


def test_dead_reckoner_subtracts_the_gyro_offset_and_ignores_long_gaps():
    dr = DeadReckoner(gyro_offset=0.005)
    for i in range(101):                      # 5 s standing still with a biased gyro
        dr.on_gyro(0.005)
        dr.on_wheel_speed(i * 0.05, 0.0)
    assert dr.yaw == pytest.approx(0.0, abs=1e-9)
    dr.on_wheel_speed(60.0, 0.3)              # 55 s dropout: must not teleport 16 m
    assert dr.x == pytest.approx(0.0)


def _still_then_moving(offset, still_s=6.0, hz=20):
    wheel, gyro = [], []
    for i in range(int(still_s * hz)):
        t = i / hz
        wheel.append((t, 0.0, 0.0))
        gyro.append((t, offset))
    for i in range(int(3 * hz)):
        t = still_s + i / hz
        wheel.append((t, 0.15, 0.3))
        gyro.append((t, 0.3 + offset))
    return wheel, gyro


def test_resting_gyro_offset_measured_from_the_stand_still_stretch_only():
    wheel, gyro = _still_then_moving(offset=0.0047)       # 0.27 deg/s, as on 2026-11-18
    assert resting_gyro_offset(wheel, gyro) == pytest.approx(0.0047, abs=1e-6)


def test_resting_gyro_offset_is_zero_without_a_long_enough_stand_still():
    wheel, gyro = _still_then_moving(offset=0.0047, still_s=1.0)
    assert resting_gyro_offset(wheel, gyro) == 0.0
    assert resting_gyro_offset([], []) == 0.0


def test_resting_gyro_offset_ignores_a_robot_turned_by_hand_with_wheels_stopped():
    wheel, gyro = _still_then_moving(offset=0.5)          # 29 deg/s: carried, not resting
    assert resting_gyro_offset(wheel, gyro) == 0.0
