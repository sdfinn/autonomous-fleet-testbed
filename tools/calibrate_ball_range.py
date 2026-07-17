"""One-time size->range calibration against Gazebo ground truth (spec §6).

With the sim up (robot parked at spawn, facing north), spawns a ball at known camera
distances directly ahead, measures the detected width_px per distance, and reports the
fitted range_k (range_m = range_k / width_px). Paste the reported value into
src/nav_fleet/config/hsv_gazebo.yaml. Run per color to sanity-check both HSV bands.

Usage (repo root, sim running):  python -m tools.calibrate_ball_range [--color red]
"""
import argparse
import sys
import time

sys.path.insert(0, 'src/nav_fleet')

import rclpy  # noqa: E402
from rclpy.node import Node  # noqa: E402
from sensor_msgs.msg import Image  # noqa: E402

from nav_fleet.ground_truth import get_ground_truth_xy  # noqa: E402
from nav_fleet.hsv_detect import detect_balls, load_hsv_config  # noqa: E402
from nav_fleet.image_io import image_msg_to_rgb  # noqa: E402
from tools.mission2_harness import remove_ball, spawn_ball  # noqa: E402

CAMERA_FORWARD_OFFSET = 0.175   # camera_joint x in the URDF: base centre -> lens
DISTANCES = (0.5, 0.75, 1.0, 1.5, 2.0)
# Live-measured (2026-07-16, headless llvmpipe software rendering on this workstation):
# the Gazebo render does not catch up to a just-spawned model within 1 s — a fixed
# 1.0 s settle sleep was flaky (same ball/config detected fine once the render caught
# up, ~1.5 s later). Poll across several frames instead of a single grab.
RENDER_SETTLE_TIMEOUT_S = 5.0
RENDER_SETTLE_POLL_S = 0.5


class _Grab(Node):
    def __init__(self):
        super().__init__('calibration_grabber')
        self.frame = None
        self.create_subscription(Image, '/robot_001/camera/image_raw', self._cb, 10)

    def _cb(self, msg):
        self.frame = msg

    def grab(self, timeout=10.0):
        self.frame = None
        deadline = time.time() + timeout
        while self.frame is None and time.time() < deadline:
            rclpy.spin_once(self, timeout_sec=0.1)
        return self.frame


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--color', choices=['red', 'yellow'], default='red')
    args = parser.parse_args()

    cfg = load_hsv_config('src/nav_fleet/config/hsv_gazebo.yaml')
    truth = get_ground_truth_xy()
    assert truth is not None, 'sim not up / no ground truth'
    rx, ry = truth
    print(f'robot at ({rx:.3f}, {ry:.3f}), facing north — camera {CAMERA_FORWARD_OFFSET}'
          f' m ahead of base centre')

    rclpy.init()
    grabber = _Grab()
    ks = []
    for d_cam in DISTANCES:
        # ball placed d_cam ahead of the LENS along +y (robot faces north at spawn)
        name = spawn_ball(args.color, rx, ry + CAMERA_FORWARD_OFFSET + d_cam)
        try:
            # Poll across several frames — the headless render needs >1s to catch up
            # to a just-spawned model on this workstation (measured 2026-07-16).
            dets = []
            deadline = time.time() + RENDER_SETTLE_TIMEOUT_S
            while not dets and time.time() < deadline:
                time.sleep(RENDER_SETTLE_POLL_S)
                frame = grabber.grab()
                assert frame is not None, 'no camera frame'
                dets = [d for d in detect_balls(image_msg_to_rgb(frame), cfg)
                        if d['color'] == args.color]
            if not dets:
                print(f'  d={d_cam:.2f} m: NOT DETECTED — fix the HSV band first')
                continue
            width = dets[0]['width_px']
            ks.append(d_cam * width)
            print(f"  d={d_cam:.2f} m: width={width} px, pixels={dets[0]['pixels']}"
                  f' -> k={d_cam * width:.1f}')
        finally:
            remove_ball(name)
            time.sleep(0.5)
    rclpy.try_shutdown()
    if ks:
        mean_k = sum(ks) / len(ks)
        spread = max(ks) - min(ks)
        print(f'\nmeasured range_k = {mean_k:.1f} (spread {spread:.1f} across '
              f'{len(ks)} samples)\n-> paste into src/nav_fleet/config/hsv_gazebo.yaml')
    else:
        print('\nNO SAMPLES — HSV thresholds need tuning before calibration')


if __name__ == '__main__':
    main()
