# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""Pure logic for masking a LaserScan's self-occluded bearing sectors — no ROS2, no
pyserial, same treatment this project already gives esp32_protocol.py's pure
encode/parse functions vs. esp32_driver.py's thin rclpy wrapper (scan_masker.py).

Built for RealRobotStartup.md A2's real-hardware lidar FOV mask, confirmed live
2026-08-10 against the real Waveshare UGV-PT + ldlidar_ros2 (D500/STL-19P): the
pan-tilt mast occludes ~46-123deg and the WiFi antenna occludes ~268-277deg (both in
the lidar's own 0-360deg bearing convention, angle_min=0). ldlidar_ros2's own
built-in angle_crop_min/angle_crop_max (src/demo.cpp) masks only ONE contiguous arc —
this project needs two non-contiguous sectors, hence this standalone filter.
"""
import math


def mask_scan_values(values, angle_min, angle_increment, mask_sectors_deg):
    """Returns a NEW list, same length as `values`, with every entry whose bearing
    (degrees, wrapped to [0, 360)) falls inside any (lo, hi) pair in
    mask_sectors_deg replaced with NaN. Works on either a LaserScan's `ranges` or
    `intensities` array (both float lists of the same length) — ldlidar_ros2's own
    angle_crop masks both together on a real crop, so this is called for each.
    Boundaries are inclusive (a reading sitting exactly on `lo`/`hi` counts as
    inside — the mast/antenna's own edge must not leak through as if just outside).
    Does not mutate `values`. A (lo, hi) pair with lo > hi wraps across the 0/360
    seam (e.g. (350, 10) covers dead-ahead)."""
    masked = []
    angle = angle_min
    for v in values:
        deg = math.degrees(angle) % 360.0
        if any(_in_sector(deg, lo, hi) for lo, hi in mask_sectors_deg):
            masked.append(float('nan'))
        else:
            masked.append(v)
        angle += angle_increment
    return masked


def _in_sector(deg, lo, hi):
    if lo <= hi:
        return lo <= deg <= hi
    return deg >= lo or deg <= hi  # wraps across the 0/360 seam


def parse_mask_sectors(flat_degrees):
    """Converts a flat [lo1, hi1, lo2, hi2, ...] list — the wire format a ROS2
    double-array parameter can actually carry, since there's no list-of-tuples
    param type — into the [(lo1, hi1), (lo2, hi2), ...] form mask_scan_values
    expects. Raises ValueError on an odd-length list (a misconfigured param should
    fail loudly, not silently drop the trailing value)."""
    if len(flat_degrees) % 2 != 0:
        raise ValueError(
            f'mask_sectors_deg must have an even number of values (lo,hi pairs), '
            f'got {len(flat_degrees)}: {flat_degrees}')
    return [(flat_degrees[i], flat_degrees[i + 1]) for i in range(0, len(flat_degrees), 2)]
