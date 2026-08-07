# tools/smoke_test.py
# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""Bench smoke-test orchestrator (design spec §tools/smoke_test.py). Attended, bench-
side sanity check for the driver layer: topic Hz/sanity, one photo, a known-distance
ball correlation check, and an odom-verified motion pulse — BEFORE the driver layer is
ever trusted under Nav2. Interactive prompting is deliberate here (unlike
mission_runner's hard no-prompting rule) — a human runs this standing at the bench.

Run: python -m tools.smoke_test [--ball-ops operator|gz] [--runner-type local] ...
"""
import argparse
import math
import pathlib
import sys
import time

import rclpy
import yaml

REPO_DIR = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_PROFILE = str(REPO_DIR / 'robot_profiles' / 'jetson_ugv_pt.yaml')


def load_robot_profile(path):
    """Load a robot_profiles/*.yaml file (first real consumer of its sensors.*.hz_min
    values, per the design spec — this profile was previously documentation-only)."""
    with open(path) as f:
        return yaml.safe_load(f)


def is_degenerate_scan(msg):
    """True if every range reading is non-finite or non-positive — the lidar 'exists
    on the topic' but never actually initialized."""
    real_readings = [r for r in msg.ranges if math.isfinite(r) and r > 0.0]
    return len(real_readings) == 0


def compute_ball_placement_xy(robot_x, robot_y, robot_yaw, distance_m):
    """The known-distance ball-placement point (design spec: 'known-distance ball
    placement, not a vague wave') — exactly `distance_m` directly ahead of the robot's
    CURRENT heading, so this works regardless of which world/coordinate frame the
    robot happens to start in."""
    return (robot_x + distance_m * math.cos(robot_yaw),
            robot_y + distance_m * math.sin(robot_yaw))


def check_topic(node, topic, msg_type, hz_min, degenerate_fn, window_s=3.0):
    """Subscribe to `topic` for `window_s` seconds. PASS requires: message rate >=
    hz_min AND the most recently received message is not degenerate per degenerate_fn.
    Returns {'pass', 'measured_hz', 'message_count', 'degenerate' (None if zero
    messages received)}."""
    state = {'count': 0, 'last_msg': None}

    def _cb(msg):
        state['count'] += 1
        state['last_msg'] = msg

    sub = node.create_subscription(msg_type, topic, _cb, 10)
    deadline = time.time() + window_s
    while time.time() < deadline:
        rclpy.spin_once(node, timeout_sec=0.1)
    node.destroy_subscription(sub)

    measured_hz = state['count'] / window_s
    degenerate = degenerate_fn(state['last_msg']) if state['last_msg'] is not None else None
    passed = measured_hz >= hz_min and degenerate is False
    return {'pass': passed, 'measured_hz': round(measured_hz, 2),
            'message_count': state['count'], 'degenerate': degenerate}
