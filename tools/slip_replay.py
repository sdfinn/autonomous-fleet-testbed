#!/usr/bin/env python3
# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""Replay a robot_boot bag through the wheel-slip detector: wheels vs walls, per 0.5 s.

    python tools/slip_replay.py <bag_dir>            # timeline + totals
    python tools/slip_replay.py <bag_dir> --table    # plus one row per window

Runs the SAME code the robot runs live (nav_fleet.scan_motion.SlipMonitorCore), so a
recorded run can be re-judged after any change to the detector. Needs a sourced ROS 2
environment (rosbag2_py); robot_boot.sh records a suitable bag on every run.
"""
import argparse
import math
import sys

import rosbag2_py
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message

from nav_fleet.scan_motion import (
    VERDICT_IDLE, VERDICT_OK, VERDICT_SLIP, VERDICT_SUSPECT, VERDICT_UNKNOWN,
    SlipMonitorCore,
)

SCAN, ODOM, IMU = '/robot_001/scan', '/robot_001/odom', '/robot_001/imu/data'
LIDAR_X = 0.05   # ugv_pt.urdf.xacro lidar_joint
MARK = {VERDICT_IDLE: '_', VERDICT_OK: '.', VERDICT_SUSPECT: 's', VERDICT_SLIP: 'S',
        VERDICT_UNKNOWN: '?'}


def _stamp(msg):
    return msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9


def replay(bag_dir, window_scans=5):
    """Returns the list of WindowResult for the bag."""
    reader = rosbag2_py.SequentialReader()
    reader.open(rosbag2_py.StorageOptions(uri=bag_dir, storage_id='mcap'),
                rosbag2_py.ConverterOptions('', ''))
    types = {t.name: t.type for t in reader.get_all_topics_and_types()}
    missing = [t for t in (SCAN, ODOM, IMU) if t not in types]
    if missing:
        raise SystemExit(f'bag has no {missing} -- not a robot_boot bag?')
    reader.set_filter(rosbag2_py.StorageFilter(topics=[SCAN, ODOM, IMU]))
    core = SlipMonitorCore(LIDAR_X, window_scans)
    results = []
    while reader.has_next():
        topic, data, _ = reader.read_next()
        msg = deserialize_message(data, get_message(types[topic]))
        if topic == ODOM:
            core.add_wheel_speed(_stamp(msg), msg.twist.twist.linear.x)
        elif topic == IMU:
            core.add_yaw_rate(_stamp(msg), msg.angular_velocity.z)
        else:
            r = core.add_scan(_stamp(msg), msg.ranges, msg.angle_min, msg.angle_increment,
                              msg.range_min, msg.range_max, msg.time_increment)
            if r is not None:
                results.append(r)
    return results


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('bag_dir')
    ap.add_argument('--table', action='store_true', help='print one row per window')
    ap.add_argument('--window-scans', type=int, default=5)
    args = ap.parse_args(argv)
    res = replay(args.bag_dir, args.window_scans)
    if not res:
        print('no comparison windows -- bag too short or topics empty')
        return 1
    t0 = res[0].stamp - res[0].window_s
    if args.table:
        print('  t(s) | wheel v | lidar v | gyro w | support | verdict')
        for r in res:
            print(f'{r.stamp - t0:6.1f} | {r.wheel_speed:6.3f}  | {r.lidar_speed:6.3f}  | '
                  f'{r.yaw_rate:5.2f}  | {r.forward_support:6.0f}  | {r.verdict}')
    print('one character per window   _ idle   . ok   s suspect   S slip   ? unknown')
    print(''.join(MARK[r.verdict] for r in res))
    wheel = sum(r.wheel_speed * r.window_s for r in res)
    lidar = sum(r.lidar_speed * r.window_s for r in res if not math.isnan(r.lidar_speed))
    slips = [r for r in res if r.verdict == VERDICT_SLIP]
    print(f'windows {len(res)}; wheels counted {wheel:.2f} m, walls saw {lidar:.2f} m; '
          f'slip windows {len(slips)}; phantom distance {res[-1].phantom_distance_m:.2f} m')
    if slips:
        print(f'first slip at t={slips[0].stamp - t0:.1f} s')
    return 0


if __name__ == '__main__':
    sys.exit(main())
