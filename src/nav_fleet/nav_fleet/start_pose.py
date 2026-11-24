# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""Is the robot where it believes it is, before it moves?

At start-up the robot is TOLD its pose (AMCL's initial pose is the configured home
pose), so asking it where it is proves nothing: it repeats what it was told. This asks
the lidar instead. From the believed pose, every lidar point is placed on the map; if
the robot really is there, most points land on or next to something the map knows (a
wall, a piece of furniture). If the robot was set down somewhere else, or turned, they
land in free space.

    score = share of the lidar's points within `tolerance_m` of an occupied map cell

Pure numpy, no ROS: the mission runner feeds it one scan, the map and the believed pose.
What it cannot tell: two places that look the same to a lidar (two similar corners).
What lowers a true score: things in the room that are not on the map (a person, a box).
"""
import math

import numpy as np

# Lidar position ahead of the robot's center (ugv_pt.urdf.xacro, lidar_joint).
LIDAR_X_M = 0.05
# The pass mark, calibrated on the real robot (2026-11-23: real scans from two floor
# recordings scored against the robot's own map, bedroom_real):
#     at home 0.90 / 0.98      10 cm off or 5 degrees turned 0.85 / 0.98
#     15 degrees turned 0.62 / 0.68       30 cm sideways 0.26 / 0.44
#     60 cm off, or 30 to 180 degrees turned 0.23 to 0.47
# Known blind spot: 30 cm FORWARD along the hallway scored 0.88 / 0.82, because the
# hallway looks the same a step further along.
TOLERANCE_M = 0.15
MIN_MATCH = 0.75
MIN_POINTS = 50

# Occupancy values at or above this are "occupied" (nav_msgs/OccupancyGrid: 0-100, -1 unknown).
OCCUPIED_AT = 65


def near_occupied(grid, resolution, tolerance_m):
    """Boolean grid: True where an occupied cell is within `tolerance_m`. `grid` is the
    map as rows of occupancy values, row 0 at the map's origin (the OccupancyGrid order)."""
    occupied = np.asarray(grid) >= OCCUPIED_AT
    reach = int(math.ceil(tolerance_m / resolution))
    near = occupied.copy()
    height, width = occupied.shape
    for dj in range(-reach, reach + 1):
        for di in range(-reach, reach + 1):
            if (di * resolution) ** 2 + (dj * resolution) ** 2 > tolerance_m ** 2 + 1e-9:
                continue
            src = occupied[max(0, -dj):height - max(0, dj), max(0, -di):width - max(0, di)]
            near[max(0, dj):height - max(0, -dj), max(0, di):width - max(0, -di)] |= src
    return near


def match_score(points_xy, pose, near, resolution, origin_xy, max_range_m=3.5):
    """(score 0-1, points used) for lidar points `points_xy` (N x 2, lidar frame, x
    forward) seen from `pose` = (x, y, yaw) of the robot's center in the map frame.
    Points farther than `max_range_m` are left out: far points are few and noisy."""
    pts = np.asarray(points_xy, dtype=float).reshape(-1, 2)
    pts = pts[np.hypot(pts[:, 0], pts[:, 1]) <= max_range_m]
    if len(pts) == 0:
        return 0.0, 0
    x, y, yaw = pose
    bx, by = pts[:, 0] + LIDAR_X_M, pts[:, 1]
    mx = x + bx * math.cos(yaw) - by * math.sin(yaw)
    my = y + bx * math.sin(yaw) + by * math.cos(yaw)
    col = np.floor((mx - origin_xy[0]) / resolution).astype(int)
    row = np.floor((my - origin_xy[1]) / resolution).astype(int)
    height, width = near.shape
    on_map = (col >= 0) & (col < width) & (row >= 0) & (row < height)
    hits = np.zeros(len(pts), dtype=bool)
    hits[on_map] = near[row[on_map], col[on_map]]
    return float(hits.mean()), int(len(pts))


def yaw_of(quaternion_zw):
    """Yaw of a flat-ground orientation from its (z, w) quaternion parts."""
    z, w = quaternion_zw
    return 2.0 * math.atan2(z, w)
