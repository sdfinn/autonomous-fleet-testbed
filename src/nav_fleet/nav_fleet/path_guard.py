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
lidar's single horizontal slice (a croquet ball is under it; so is a rug edge).

Two rules added 2026-11-23, after the first floor run with Nav2's re-planning and
recoveries switched on, in which the robot inched into a box and then turned into it:

  * A hold lasts until the zone that caused it is really empty, not until the command
    pauses. Before, the box was only checked while a speed was being asked for; when
    Nav2 stopped asking (to try a recovery) the hold was released one second later
    with the box still there, and the next forward command moved the robot a few
    centimeters before the guard caught it again: 4 cm, 4, 1, 0, contact.
  * A turn on the spot is guarded. The robot's corners sweep a circle wider than the
    distance to its bumper, so something just ahead of the bumper is hit by a corner
    when the robot turns. Turns are held while anything is inside that circle plus a
    margin. Reversing away is still allowed whenever the rear box is empty.

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
# Above this commanded turn rate (and below the speed above) it is turning on the spot.
TURNING_RATE_RADPS = 0.05
# The farthest any corner is from the robot's center: what a turn on the spot sweeps.
CORNER_REACH_M = float(np.hypot(ROBOT_LENGTH_M, ROBOT_WIDTH_M) / 2.0)

AHEAD, BEHIND, TURN = 'ahead', 'behind', 'turn'


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
                 clear_after_s=1.0, turn_margin_m=0.03):
        if (stop_distance_m <= 0 or side_margin_m < 0 or min_points < 1 or clear_after_s < 0
                or turn_margin_m < 0):
            raise ValueError('stop_distance_m > 0, side_margin_m >= 0, min_points >= 1, '
                             'clear_after_s >= 0, turn_margin_m >= 0')
        self.turn_reach_m = CORNER_REACH_M + float(turn_margin_m)
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
        self.zone = None               # AHEAD, BEHIND or TURN: what the hold is for
        self._last_seen = None

    def asked_zone(self, linear_x, angular_z=0.0):
        """Which zone the commanded motion needs clear, or None when nothing is asked."""
        if linear_x > MOVING_SPEED_MPS:
            return AHEAD
        if linear_x < -MOVING_SPEED_MPS:
            return BEHIND
        if abs(angular_z) > TURNING_RATE_RADPS:
            return TURN
        return None

    def in_zone(self, points, zone):
        """(count, nearest gap in meters or None) of points inside `zone`. The gap is
        measured from the bumper (AHEAD, BEHIND) or from the circle the corners sweep
        (TURN, where it is negative for a point a corner would hit)."""
        pts = np.asarray(points, dtype=float).reshape(-1, 2)
        if zone == TURN:
            # The robot's center is LIDAR_X_M behind the lidar.
            cx, cy = pts[:, 0] + LIDAR_X_M, pts[:, 1]
            gap = np.hypot(cx, cy) - CORNER_REACH_M
            # Returns inside the robot's own outline are the robot: the real lidar sees
            # part of it 0.03 m from the center on every scan (floor bags, 2026-11-23),
            # which the simulated lidar never does. Without this, every turn was held.
            own = (np.abs(cx) <= ROBOT_LENGTH_M / 2.0) & (np.abs(cy) <= ROBOT_WIDTH_M / 2.0)
            inside = (gap <= self.turn_reach_m - CORNER_REACH_M) & ~own
        elif zone == AHEAD:
            gap = pts[:, 0] - self._front_x
            inside = (gap >= 0.0) & (gap <= self.stop_distance_m) \
                & (np.abs(pts[:, 1]) <= self.half_width_m)
        elif zone == BEHIND:
            gap = self._rear_x - pts[:, 0]
            inside = (gap >= 0.0) & (gap <= self.stop_distance_m) \
                & (np.abs(pts[:, 1]) <= self.half_width_m)
        else:
            return 0, None
        count = int(inside.sum())
        return count, (float(gap[inside].min()) if count else None)

    def in_the_way(self, points, linear_x, angular_z=0.0):
        """(count, nearest gap) for the motion being asked for; (0, None) when the robot
        is not being asked to move at all."""
        return self.in_zone(points, self.asked_zone(linear_x, angular_z))

    def update(self, points, linear_x, now, angular_z=0.0):
        """One scan. Returns the events it caused: [], [BLOCKED] or [CLEARED].

        The zone checked is the one the commanded motion needs. While NOTHING is being
        asked for and the robot is held, the zone that caused the hold keeps being
        checked: a pause in the commands is not evidence that the way is clear."""
        zone = self.asked_zone(linear_x, angular_z)
        if zone is None and self.blocked:
            zone = self.zone
        count, nearest = self.in_zone(points, zone)
        if count >= self.min_points:
            self._last_seen = float(now)
            self.nearest_m = nearest
            self.zone = zone
            if not self.blocked:
                self.blocked = True
                self.blocks += 1
                return [BLOCKED]
            return []
        if self.blocked and now - self._last_seen >= self.clear_after_s:
            self.blocked = False
            self.nearest_m = None
            self.zone = None
            return [CLEARED]
        return []
