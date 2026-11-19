#!/usr/bin/env python3
# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""Feed a mapping-drive bag to slam_toolbox so the map is built OFFLINE on the workstation.

Not run directly -- scripts/build_map_from_bag.sh starts slam_toolbox in an isolated DDS
domain, runs this feeder against it, and saves the map. This file publishes, in bag
time: /scan, /tf (odom -> base_footprint), /tf_static and /clock.

Why a feeder instead of `ros2 bag play` (all three found on 2026-11-18):
  * The LD19's scans vary between 500 and 505 readings; slam_toolbox's Karto front end
    rejects any scan whose count differs from the first. Every scan is resampled onto
    a fixed beam grid here (resample_scan).
  * A mapping drive (scripts/robot_map_drive.sh) runs only the driver layer: no EKF, so
    the bag has no odom -> base_footprint transform. It is rebuilt here from the same
    two signals config/ekf.yaml fuses -- wheel forward speed and gyro yaw rate
    (DeadReckoner). A map built this way matched one built from the EKF's own TF to
    within one 5 cm cell for 98% of wall cells.
  * key_teleop publishes zero-speed commands while idle, which (until the same day's
    esp32_driver fix) stopped the driver from learning the gyro's resting offset; a
    4-minute drive carried +0.27 deg/s. resting_gyro_offset() measures it from the
    bag's own stand-still stretches and it is subtracted.

The dead reckoning STARTS at --start-pose, so the map comes out in the mission's frame
with the spot where the drive began at exactly that pose. Start the mapping drive on
the robot's home spot and pass the configured home pose (the default below): the map's
home then IS nav2_params.yaml's AMCL initial pose and semantic_map's home_base, and
nothing else has to change.

The helpers at the top are plain Python/numpy and unit-tested (tests/test_map_from_bag.py);
everything ROS is imported inside main().
"""
import argparse
import math
import sys
import time

import numpy as np

SCAN_TOPIC = '/robot_001/scan'
ODOM_TOPIC = '/robot_001/odom'
IMU_TOPIC = '/robot_001/imu/data'
STATIC_TF_TOPIC = '/robot_001/tf_static'

# nav2_params.yaml amcl.initial_pose == semantic_map.SEMANTIC_MAP['home_base'], facing +y.
DEFAULT_START_POSE = (-1.276, 1.2, 90.0)
FIXED_BEAMS = 500

# resting_gyro_offset(): a stand-still stretch = wheels reporting exactly zero for at
# least this long. Its first and last half second are dropped (settling after a stop,
# the hand that is about to press a key).
MIN_STILL_S = 2.0
STILL_EDGE_S = 0.5
# A "resting offset" larger than this is not an offset, it is the robot being turned
# by hand; such a stretch is ignored. Same limit as esp32_protocol.GyroBiasEstimator.
MAX_PLAUSIBLE_OFFSET_RPS = 0.06


def resample_scan(ranges, angle_min, angle_increment, n_beams=FIXED_BEAMS):
    """One scan -> exactly n_beams ranges on a fixed grid from -pi, one full turn.

    Each output beam takes the reading whose bearing is nearest (no blending: averaging
    a wall with the gap beside it would invent points in mid-air). NaN/inf readings
    become +inf ("no return"), which slam_toolbox skips.
    Returns (ranges list, angle_min, angle_increment, angle_max) for the new scan.
    """
    r = np.asarray(ranges, dtype=float).copy()
    r[~np.isfinite(r)] = np.inf
    src = angle_min + np.arange(len(r)) * angle_increment
    src = (src + math.pi) % (2 * math.pi) - math.pi
    order = np.argsort(src)
    src, r = src[order], r[order]
    out_inc = 2 * math.pi / n_beams
    grid = -math.pi + np.arange(n_beams) * out_inc
    hi = np.clip(np.searchsorted(src, grid), 0, len(src) - 1)
    lo = np.clip(hi - 1, 0, len(src) - 1)
    # also consider the wrap-around neighbours at the two ends of the turn
    cands = np.stack([lo, hi, np.zeros_like(hi), np.full_like(hi, len(src) - 1)])
    diff = np.abs((src[cands] - grid[None, :] + math.pi) % (2 * math.pi) - math.pi)
    pick = cands[diff.argmin(axis=0), np.arange(n_beams)]
    return ([float(x) for x in r[pick]], -math.pi, out_inc, -math.pi + (n_beams - 1) * out_inc)


class DeadReckoner:
    """Pose from wheel forward speed + gyro yaw rate: the two things ekf.yaml fuses."""

    def __init__(self, x=0.0, y=0.0, yaw=0.0, gyro_offset=0.0):
        self.x, self.y, self.yaw = x, y, yaw
        self.gyro_offset = gyro_offset
        self._yaw_rate = 0.0
        self._last_t = None

    def on_gyro(self, yaw_rate):
        self._yaw_rate = yaw_rate - self.gyro_offset

    def on_wheel_speed(self, t, speed):
        """Advance to time t (seconds) at the given forward speed; returns (x, y, yaw)."""
        if self._last_t is not None:
            dt = t - self._last_t
            if 0.0 < dt < 1.0:                  # a gap longer than this is a dropout
                mid = self.yaw + self._yaw_rate * dt / 2.0
                self.x += speed * dt * math.cos(mid)
                self.y += speed * dt * math.sin(mid)
                self.yaw += self._yaw_rate * dt
        self._last_t = t
        return self.x, self.y, self.yaw


def resting_gyro_offset(wheel_samples, gyro_samples):
    """Mean gyro yaw rate (rad/s) over the bag's stand-still stretches; 0.0 if none.

    wheel_samples: [(t, forward speed, wheel yaw rate)], gyro_samples: [(t, yaw rate)].
    """
    if not wheel_samples or not gyro_samples:
        return 0.0
    stretches, start = [], None
    for t, v, w in wheel_samples:
        if v == 0.0 and w == 0.0:
            start = t if start is None else start
            end = t
        else:
            if start is not None and end - start >= MIN_STILL_S:
                stretches.append((start, end))
            start = None
    if start is not None and end - start >= MIN_STILL_S:
        stretches.append((start, end))
    gt = np.array([g[0] for g in gyro_samples])
    gv = np.array([g[1] for g in gyro_samples])
    total, count = 0.0, 0
    for a, b in stretches:
        sel = gv[(gt >= a + STILL_EDGE_S) & (gt <= b - STILL_EDGE_S)]
        if len(sel) >= 10 and abs(sel.mean()) <= MAX_PLAUSIBLE_OFFSET_RPS:
            total += float(sel.sum())
            count += len(sel)
    return total / count if count else 0.0


def _stamp(msg):
    return msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('bag_dir')
    ap.add_argument('--rate', type=float, default=2.0, help='playback speed (x real time)')
    ap.add_argument('--start-pose', default=','.join(str(v) for v in DEFAULT_START_POSE),
                    help='x,y,yaw_deg of the spot where the drive began (default: home)')
    args = ap.parse_args(argv)
    sx, sy, syaw = (float(v) for v in args.start_pose.split(','))

    import rclpy
    import rosbag2_py
    from builtin_interfaces.msg import Time
    from geometry_msgs.msg import TransformStamped
    from rclpy.qos import DurabilityPolicy, QoSProfile
    from rclpy.serialization import deserialize_message
    from rosgraph_msgs.msg import Clock
    from rosidl_runtime_py.utilities import get_message
    from sensor_msgs.msg import LaserScan
    from tf2_msgs.msg import TFMessage

    def open_reader(topics):
        reader = rosbag2_py.SequentialReader()
        reader.open(rosbag2_py.StorageOptions(uri=args.bag_dir, storage_id='mcap'),
                    rosbag2_py.ConverterOptions('', ''))
        types = {t.name: t.type for t in reader.get_all_topics_and_types()}
        missing = [t for t in (SCAN_TOPIC, ODOM_TOPIC, IMU_TOPIC) if t not in types]
        if missing:
            sys.exit(f'{args.bag_dir} has no {missing} -- not a mapping-drive bag?')
        reader.set_filter(rosbag2_py.StorageFilter(topics=topics))
        return reader, types

    # Pass 1: the gyro's resting offset, from the bag itself.
    reader, types = open_reader([ODOM_TOPIC, IMU_TOPIC])
    wheel, gyro = [], []
    while reader.has_next():
        topic, data, _ = reader.read_next()
        msg = deserialize_message(data, get_message(types[topic]))
        if topic == ODOM_TOPIC:
            wheel.append((_stamp(msg), msg.twist.twist.linear.x, msg.twist.twist.angular.z))
        else:
            gyro.append((_stamp(msg), msg.angular_velocity.z))
    offset = resting_gyro_offset(wheel, gyro)
    print(f'gyro resting offset in this bag: {math.degrees(offset):+.3f} deg/s (subtracted)')

    # Pass 2: play it to slam_toolbox.
    rclpy.init()
    node = rclpy.create_node('map_from_bag')
    latched = QoSProfile(depth=10, durability=DurabilityPolicy.TRANSIENT_LOCAL)
    scan_pub = node.create_publisher(LaserScan, '/scan', 10)
    tf_pub = node.create_publisher(TFMessage, '/tf', 100)
    static_pub = node.create_publisher(TFMessage, '/tf_static', latched)
    clock_pub = node.create_publisher(Clock, '/clock', 10)
    reckoner = DeadReckoner(sx, sy, math.radians(syaw), gyro_offset=offset)
    time.sleep(2.0)                              # let slam_toolbox discover the publishers

    reader, types = open_reader([SCAN_TOPIC, ODOM_TOPIC, IMU_TOPIC, STATIC_TF_TOPIC])
    first, wall0, scans = None, time.monotonic(), 0
    while reader.has_next() and rclpy.ok():
        topic, data, t_ns = reader.read_next()
        t = t_ns * 1e-9
        first = t if first is None else first
        msg = deserialize_message(data, get_message(types[topic]))
        if topic == STATIC_TF_TOPIC:
            static_pub.publish(msg)
            continue
        wait = (t - first) / args.rate - (time.monotonic() - wall0)
        if wait > 0:
            time.sleep(wait)
        clock_pub.publish(Clock(clock=Time(sec=int(t), nanosec=int((t - int(t)) * 1e9))))
        if topic == IMU_TOPIC:
            reckoner.on_gyro(msg.angular_velocity.z)
        elif topic == ODOM_TOPIC:
            x, y, yaw = reckoner.on_wheel_speed(_stamp(msg), msg.twist.twist.linear.x)
            tr = TransformStamped()
            tr.header.stamp = msg.header.stamp
            tr.header.frame_id, tr.child_frame_id = 'odom', 'base_footprint'
            tr.transform.translation.x, tr.transform.translation.y = x, y
            tr.transform.rotation.z, tr.transform.rotation.w = math.sin(yaw / 2), math.cos(yaw / 2)
            tf_pub.publish(TFMessage(transforms=[tr]))
        else:
            out = LaserScan()
            out.header = msg.header
            out.ranges, out.angle_min, out.angle_increment, out.angle_max = resample_scan(
                msg.ranges, msg.angle_min, msg.angle_increment)
            out.range_min, out.range_max = msg.range_min, msg.range_max
            out.scan_time = msg.scan_time
            out.time_increment = msg.scan_time / FIXED_BEAMS
            scan_pub.publish(out)
            scans += 1
    print(f'fed {scans} scans; drive ended at x={reckoner.x:.2f} y={reckoner.y:.2f} '
          f'yaw={math.degrees(reckoner.yaw) % 360:.0f} deg by dead reckoning')
    time.sleep(3.0)                              # let the last scans be processed
    node.destroy_node()
    rclpy.try_shutdown()
    return 0


if __name__ == '__main__':
    sys.exit(main())
