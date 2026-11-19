# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""How far did the robot really move? Answered from two lidar scans, not the wheels.

Pure numpy, no rclpy (same split as scan_filter.py / scan_masker.py), so it runs in
stage-1-quality and can be replayed offline against a recorded bag.

Why this exists (2026-11-17, reports/robot_boot_20261117_navonly/): at the edge of the
hallway runner the wheels spun for ~16 s. The wheel encoders are the EKF's only speed
source, so odometry counted ~1.1 m that never happened, AMCL followed it, and the robot
turned for a door a metre early. Nothing in the stack could see that. The walls can:
if two scans half a second apart line up with no shift, the robot did not move, whatever
the wheels say.

Method, in three steps:
  1. scan_to_points   -- ranges -> xy points, undoing the smear caused by turning while
                         the lidar is still sweeping (uses the gyro, verified 2026-11-16).
  2. estimate_translation -- rotation between the scans is TAKEN from the gyro; only the
                         shift is solved, by sliding the new points onto the old scan's
                         wall lines (point-to-line matching).
  3. forward_distance -- turn the lidar's shift into base_link forward travel.

The one thing to stay honest about: walls only tell you about motion ACROSS them. In a
long plain corridor nothing constrains motion ALONG it, and a naive matcher would report
"no movement" -- exactly the slip signature. MotionEstimate.forward_support says how
many points actually pin down forward motion; callers must treat a low value as
"unknown", never as "stopped".
"""
from dataclasses import dataclass

import numpy as np

# Readings closer than this are the robot's own body/mast edges; farther than
# MAX_USEFUL_RANGE_M the LD19's range noise is larger than the motion being measured.
MIN_USEFUL_RANGE_M = 0.15
MAX_USEFUL_RANGE_M = 8.0

# A wall normal is fitted to a point and its NORMAL_HALF_WINDOW neighbours each side.
NORMAL_HALF_WINDOW = 3
# Neighbours further apart than this are different surfaces (a doorway edge, a chair leg).
NORMAL_MAX_NEIGHBOUR_GAP_M = 0.12
# The neighbourhood must be at least this much longer than it is thick to count as a wall.
NORMAL_MAX_THICKNESS_RATIO = 0.3

# Matching: accept loose pairs first (the robot may have moved 15 cm), then tighten.
MATCH_COARSE_DISTANCE_M = 0.30
MATCH_FINE_DISTANCE_M = 0.10
MATCH_COARSE_ITERATIONS = 4
MATCH_MAX_ITERATIONS = 12
MATCH_CONVERGED_M = 1e-4
# Residuals beyond this are down-weighted (Huber): people, curtains, range speckle.
MATCH_HUBER_M = 0.02
# Fewer usable points than this and no answer is given at all.
MIN_MATCHED_POINTS = 30


@dataclass(frozen=True)
class MotionEstimate:
    """Result of matching one scan onto an earlier one."""

    tx: float                # lidar shift along the earlier scan's x (forward), metres
    ty: float                # lidar shift along the earlier scan's y (left), metres
    matched_points: int      # point pairs used in the final iteration
    rms_m: float             # leftover point-to-wall distance; ~0.005-0.03 on this robot
    forward_support: float   # effective number of points that constrain FORWARD motion


def scan_to_points(ranges, angle_min, angle_increment, range_min, range_max,
                   time_increment=0.0, yaw_rates=None):
    """LaserScan fields -> (N, 2) xy points in the lidar frame as of the first ray.

    yaw_rates: optional per-ray yaw rate in rad/s (same length as ranges). The LD19
    takes 0.1 s per revolution; at 1 rad/s the last ray is 0.1 rad (6 deg) off from
    where a frozen snapshot would put it, which at 3 m is 30 cm. Passing the gyro's
    rate removes that smear. Translation during the sweep (<= 3 cm) is left alone.
    """
    r = np.asarray(ranges, dtype=float)
    idx = np.arange(len(r))
    angles = angle_min + idx * angle_increment
    if yaw_rates is not None and time_increment:
        angles = angles + np.cumsum(np.asarray(yaw_rates, dtype=float)) * time_increment
    ok = (np.isfinite(r) & (r > max(range_min, MIN_USEFUL_RANGE_M))
          & (r < min(range_max, MAX_USEFUL_RANGE_M)))
    return np.column_stack((r[ok] * np.cos(angles[ok]), r[ok] * np.sin(angles[ok])))


def surface_normals(points):
    """Unit wall normal at each point; NaN where the neighbourhood is not one flat surface.

    Points must be in scan order (neighbours in the array are neighbours on the wall).
    """
    pts = np.asarray(points, dtype=float)
    n = len(pts)
    k = NORMAL_HALF_WINDOW
    normals = np.full((n, 2), np.nan)
    if n < 2 * k + 1:
        return normals
    win = np.lib.stride_tricks.sliding_window_view(pts, 2 * k + 1, axis=0)  # (n-2k, 2, w)
    win = np.transpose(win, (0, 2, 1))                                      # (n-2k, w, 2)
    gaps = np.linalg.norm(np.diff(win, axis=1), axis=2).max(axis=1)
    centred = win - win.mean(axis=1, keepdims=True)
    cov = np.einsum('nwi,nwj->nij', centred, centred)
    evals, evecs = np.linalg.eigh(cov)                  # ascending: [thin, long]
    thin = np.sqrt(np.maximum(evals[:, 0], 0.0))
    long_ = np.sqrt(np.maximum(evals[:, 1], 1e-18))
    good = (gaps <= NORMAL_MAX_NEIGHBOUR_GAP_M) & (thin <= NORMAL_MAX_THICKNESS_RATIO * long_)
    centre = normals[k:n - k]
    centre[good] = evecs[good, :, 0]
    return normals


def estimate_translation(ref_points, cur_points, dtheta):
    """Shift t such that R(dtheta) @ cur + t lies on the walls seen in ref.

    ref_points / cur_points: (N, 2) from scan_to_points, earlier and later scan.
    dtheta: how far the robot turned between them (rad, left positive), from the gyro.
    Returns a MotionEstimate, or None when there is too little to match.

    The start guess is "no movement" on purpose: seeding it with the wheel odometry
    would bias the answer toward the very thing being checked.
    """
    ref = np.asarray(ref_points, dtype=float)
    cur = np.asarray(cur_points, dtype=float)
    if len(ref) < MIN_MATCHED_POINTS or len(cur) < MIN_MATCHED_POINTS:
        return None
    normals = surface_normals(ref)
    has_normal = np.isfinite(normals[:, 0])
    ref, normals = ref[has_normal], normals[has_normal]
    if len(ref) < MIN_MATCHED_POINTS:
        return None

    c, s = np.cos(dtheta), np.sin(dtheta)
    rotated = cur @ np.array([[c, s], [-s, c]])        # row-vector form of R(dtheta) @ p
    t = np.zeros(2)
    info = np.zeros((2, 2))
    residual = np.zeros(0)
    used = 0
    for iteration in range(MATCH_MAX_ITERATIONS):
        moved = rotated + t
        d2 = ((moved[:, None, :] - ref[None, :, :]) ** 2).sum(axis=2)
        nearest = d2.argmin(axis=1)
        dist = np.sqrt(d2[np.arange(len(moved)), nearest])
        limit = (MATCH_COARSE_DISTANCE_M if iteration < MATCH_COARSE_ITERATIONS
                 else MATCH_FINE_DISTANCE_M)
        keep = dist < limit
        used = int(keep.sum())
        if used < MIN_MATCHED_POINTS:
            return None
        n = normals[nearest[keep]]
        residual = ((moved[keep] - ref[nearest[keep]]) * n).sum(axis=1)
        weight = 1.0 / np.maximum(1.0, np.abs(residual) / MATCH_HUBER_M)
        info = (n * weight[:, None]).T @ n
        step = -np.linalg.solve(info + 1e-9 * np.eye(2), (n * weight[:, None]).T @ residual)
        t = t + step
        if np.linalg.norm(step) < MATCH_CONVERGED_M:
            break

    # 1 / inv(info)[0, 0] = how many "full-strength" points constrain x once the
    # x/y coupling is accounted for. A wall dead ahead gives 1 per point; a wall
    # alongside gives 0 per point.
    det = info[0, 0] * info[1, 1] - info[0, 1] * info[1, 0]
    forward_support = float(det / info[1, 1]) if info[1, 1] > 1e-9 else float(info[0, 0])
    return MotionEstimate(tx=float(t[0]), ty=float(t[1]), matched_points=used,
                          rms_m=float(np.sqrt(np.mean(residual ** 2))),
                          forward_support=max(forward_support, 0.0))


def forward_distance(estimate, dtheta, lidar_x):
    """base_link forward travel (m) between the two scans, from the lidar's shift.

    lidar_x: how far ahead of base_link the lidar sits (0.05 m on this robot, from
    ugv_pt.urdf.xacro's lidar_joint). Turning swings the lidar sideways around
    base_link even when the robot goes nowhere; that part is removed first. "Forward"
    is measured along the robot's average heading over the interval.
    """
    base_x = estimate.tx - (np.cos(dtheta) - 1.0) * lidar_x
    base_y = estimate.ty - np.sin(dtheta) * lidar_x
    return float(base_x * np.cos(dtheta / 2.0) + base_y * np.sin(dtheta / 2.0))


# --- Deciding "the wheels are slipping" from a stream of comparisons -----------------

# Below this wheel speed there is nothing to check (lidar noise floor is ~0.01 m/s
# standing still, and a creeping robot cannot lose much distance anyway).
SLIP_MIN_WHEEL_SPEED_MPS = 0.08
# Slip = the walls say the robot covered less than this fraction of what the wheels say.
# On 2026-11-17 real driving sat at 0.8-1.3 and the slip at 0.0-0.4.
SLIP_MAX_SPEED_RATIO = 0.5
# Below this forward_support the lidar's answer is not trusted either way (plain corridor).
SLIP_MIN_FORWARD_SUPPORT = 20.0
# One bad window is not slip: pulling away from rest reads low for one window because
# the wheels lead the chassis. This many in a row is.
SLIP_CONFIRM_WINDOWS = 2

VERDICT_OK = 'ok'                # wheels and walls agree
VERDICT_SLIP = 'slip'            # wheels turning, walls say (nearly) stationary
VERDICT_SUSPECT = 'suspect'      # looks like slip but not yet confirmed
VERDICT_IDLE = 'idle'            # wheels (nearly) stopped: nothing to compare
VERDICT_UNKNOWN = 'unknown'      # lidar could not measure forward motion this window


class SlipDetector:
    """Feed it one (wheel speed, lidar speed, support) per window; it says what is going on.

    Also keeps a running total of distance the wheels claimed but the walls did not
    see (phantom_distance_m) -- the number that explains a pose error after the fact.
    """

    def __init__(self):
        self._suspect_windows = 0
        self.phantom_distance_m = 0.0

    def update(self, wheel_speed, lidar_speed, forward_support, window_s):
        """wheel_speed / lidar_speed in m/s (signed, forward positive); lidar_speed may be None."""
        if abs(wheel_speed) < SLIP_MIN_WHEEL_SPEED_MPS:
            self._suspect_windows = 0
            return VERDICT_IDLE
        if lidar_speed is None or forward_support < SLIP_MIN_FORWARD_SUPPORT:
            # Deliberately does NOT clear the streak: losing the measurement for one
            # window in the middle of a slip should not reset the count.
            return VERDICT_UNKNOWN
        # Progress in the direction the wheels claim, as a fraction of the claim.
        ratio = (lidar_speed * np.sign(wheel_speed)) / abs(wheel_speed)
        if ratio >= SLIP_MAX_SPEED_RATIO:
            self._suspect_windows = 0
            return VERDICT_OK
        self._suspect_windows += 1
        if self._suspect_windows < SLIP_CONFIRM_WINDOWS:
            return VERDICT_SUSPECT
        self.phantom_distance_m += abs(wheel_speed - lidar_speed) * window_s
        return VERDICT_SLIP


# --- The whole pipeline, with buffers: used live (slip_monitor.py) AND offline --------

# Compare scans this many apart. The LD19 scans at 10 Hz, so 5 = one check per 0.5 s:
# long enough that real motion (>= 4 cm at 0.08 m/s) stands clear of the ~0.5 cm noise.
DEFAULT_WINDOW_SCANS = 5
# A window longer than this means scans were dropped; skip it rather than match across it.
MAX_WINDOW_S = 1.5
# Wheel/gyro samples are kept this long (they arrive at ~20 Hz).
SAMPLE_HISTORY_S = 5.0


@dataclass(frozen=True)
class WindowResult:
    """One wheels-vs-walls comparison."""

    stamp: float              # time of the later scan, seconds
    window_s: float
    wheel_speed: float        # m/s, from the wheel encoders
    lidar_speed: float        # m/s, from the walls; NaN when it could not be measured
    yaw_rate: float           # rad/s, from the gyro
    forward_support: float
    verdict: str              # one of the VERDICT_* strings
    phantom_distance_m: float  # running total of wheel distance the walls did not see


class SlipMonitorCore:
    """Buffers wheel speed, gyro rate and scans; emits a WindowResult every N scans.

    No ROS in here: times are plain float seconds (header stamps), so the same object
    is driven by slip_monitor.py on the robot and by tools/slip_replay.py from a bag.
    """

    def __init__(self, lidar_x, window_scans=DEFAULT_WINDOW_SCANS):
        self.lidar_x = lidar_x
        self.window_scans = window_scans
        self.detector = SlipDetector()
        self._wheel = []      # (t, forward speed)
        self._gyro = []       # (t, yaw rate)
        self._ref = None      # (stamp, points) of the scan being compared against
        self._scans_since_ref = 0

    def add_wheel_speed(self, t, speed):
        self._append(self._wheel, t, speed)

    def add_yaw_rate(self, t, rate):
        self._append(self._gyro, t, rate)

    @staticmethod
    def _append(buf, t, value):
        buf.append((t, value))
        while buf and buf[0][0] < t - SAMPLE_HISTORY_S:
            buf.pop(0)

    @staticmethod
    def _integrate(buf, t0, t1):
        """Integral of the buffered signal over [t0, t1]; None without enough samples."""
        inside = [(t, v) for t, v in buf if t0 <= t <= t1]
        if len(inside) < 2:
            return None
        t = np.array([s[0] for s in inside])
        v = np.array([s[1] for s in inside])
        return float(np.sum(0.5 * (v[1:] + v[:-1]) * np.diff(t)))

    def add_scan(self, stamp, ranges, angle_min, angle_increment, range_min, range_max,
                 time_increment):
        """Returns a WindowResult when this scan closes a window, else None."""
        self._scans_since_ref += 1
        if self._ref is not None and self._scans_since_ref < self.window_scans:
            return None
        yaw_rates = None
        if len(self._gyro) >= 2 and time_increment:
            gt = np.array([s[0] for s in self._gyro])
            gv = np.array([s[1] for s in self._gyro])
            yaw_rates = np.interp(stamp + np.arange(len(ranges)) * time_increment, gt, gv)
        pts = scan_to_points(ranges, angle_min, angle_increment, range_min, range_max,
                             time_increment, yaw_rates)
        ref, self._ref, self._scans_since_ref = self._ref, (stamp, pts), 0
        if ref is None:
            return None
        window = stamp - ref[0]
        if not 0.0 < window <= MAX_WINDOW_S:
            return None
        dtheta = self._integrate(self._gyro, ref[0], stamp)
        wheel_dist = self._integrate(self._wheel, ref[0], stamp)
        if dtheta is None or wheel_dist is None:
            return None
        est = estimate_translation(ref[1], pts, dtheta)
        lidar_speed = None if est is None else forward_distance(est, dtheta, self.lidar_x) / window
        support = 0.0 if est is None else est.forward_support
        verdict = self.detector.update(wheel_dist / window, lidar_speed, support, window)
        return WindowResult(stamp=stamp, window_s=window, wheel_speed=wheel_dist / window,
                            lidar_speed=float('nan') if lidar_speed is None else lidar_speed,
                            yaw_rate=dtheta / window, forward_support=support, verdict=verdict,
                            phantom_distance_m=self.detector.phantom_distance_m)
