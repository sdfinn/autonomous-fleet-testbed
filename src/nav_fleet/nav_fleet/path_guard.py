# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""Is something the lidar can see in the way? Decision logic, no ROS in it.

The real robot had no collision protection at all: Nav2's own layers (RPP collision
detection, collision_monitor, recovery behaviours) each deadlocked it when enabled, so
all three were switched off, and on 2026-11-18 it drove into a dresser and kept pushing
for the rest of the leg. This is deliberately the smallest thing that stops that:

    a box just ahead of the bumper (or just behind it, when reversing), as wide as the
    robot plus a small margin. Lidar returns inside it -> BLOCKED -> the wheels are held
    (the `obstacle_guard` node publishes /robot_001/obstacle_hold; esp32_driver obeys).
    Box empty for `clear_after_s` -> CLEARED -> the wheels are released.

Nav2 is not told. It keeps commanding, so the robot carries on by itself when the way
clears (someone walked past), and if it never clears Nav2's progress checker fails the
leg after its usual 60 s -- with the robot standing still instead of pushing.

What this does NOT do: go around anything, back away, or see anything outside the
lidar's single horizontal slice (a croquet ball is under it; so is a rug edge). Turning
on the spot is not guarded: the box is only checked while a forward or reverse speed is
being asked for.

Frames: scan points are in the lidar's frame, x forward, y left (scan_masker's output).
The geometry below is this robot's measured footprint (CLAUDE.md, calibration facts).
"""
import numpy as np

# Robot footprint 0.253 m long x 0.231 m wide, centred on base_link; the lidar sits
# 0.05 m ahead of base_link.
ROBOT_LENGTH_M = 0.253
ROBOT_WIDTH_M = 0.231
LIDAR_X_M = 0.05

BLOCKED = 'blocked'
CLEARED = 'cleared'

# Below this commanded speed the robot is turning on the spot or standing still.
MOVING_SPEED_MPS = 0.02


def scan_points(ranges, angle_min, angle_increment, range_min, range_max):
    """LaserScan fields -> (N, 2) xy points in the lidar frame. Unlike
    scan_motion.scan_to_points this keeps NEAR returns: for this job they are the ones
    that matter. Masked rays (NaN) and out-of-range values are dropped."""
    r = np.asarray(ranges, dtype=float)
    angles = angle_min + np.arange(len(r)) * angle_increment
    ok = np.isfinite(r) & (r >= range_min) & (r <= range_max)
    return np.column_stack((r[ok] * np.cos(angles[ok]), r[ok] * np.sin(angles[ok])))


class PathGuard:
    """Feed it every scan with the speed Nav2 is asking for; read `.blocked`."""

    def __init__(self, stop_distance_m=0.25, side_margin_m=0.02, min_points=3,
                 clear_after_s=1.0):
        if stop_distance_m <= 0 or side_margin_m < 0 or min_points < 1 or clear_after_s < 0:
            raise ValueError('stop_distance_m > 0, side_margin_m >= 0, min_points >= 1, '
                             'clear_after_s >= 0')
        self.stop_distance_m = float(stop_distance_m)
        self.half_width_m = ROBOT_WIDTH_M / 2.0 + float(side_margin_m)
        self.min_points = int(min_points)
        self.clear_after_s = float(clear_after_s)
        # Bumper positions along x, in the LIDAR's frame.
        self._front_x = ROBOT_LENGTH_M / 2.0 - LIDAR_X_M
        self._rear_x = -ROBOT_LENGTH_M / 2.0 - LIDAR_X_M
        self.blocked = False
        self.blocks = 0
        self.nearest_m = None          # gap from the bumper to the nearest blocking point
        self._last_seen = None

    def in_the_way(self, points, linear_x):
        """(count, nearest gap in metres or None) of points in the box for this
        direction of travel. No box (0, None) when not driving forward or back."""
        pts = np.asarray(points, dtype=float).reshape(-1, 2)
        if linear_x > MOVING_SPEED_MPS:
            gap = pts[:, 0] - self._front_x
        elif linear_x < -MOVING_SPEED_MPS:
            gap = self._rear_x - pts[:, 0]
        else:
            return 0, None
        inside = (gap >= 0.0) & (gap <= self.stop_distance_m) \
            & (np.abs(pts[:, 1]) <= self.half_width_m)
        count = int(inside.sum())
        return count, (float(gap[inside].min()) if count else None)

    def update(self, points, linear_x, now):
        """One scan. Returns the events it caused: [], [BLOCKED] or [CLEARED]."""
        count, nearest = self.in_the_way(points, linear_x)
        if count >= self.min_points:
            self._last_seen = float(now)
            self.nearest_m = nearest
            if not self.blocked:
                self.blocked = True
                self.blocks += 1
                return [BLOCKED]
            return []
        if self.blocked and now - self._last_seen >= self.clear_after_s:
            self.blocked = False
            self.nearest_m = None
            return [CLEARED]
        return []
