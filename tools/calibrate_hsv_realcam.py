# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""One-time HSV threshold suggestion for the REAL camera (RealRobotStartup.md Part A).

hsv_gazebo.yaml's thresholds are tuned for Gazebo's rendered ball material — they have
no reason to match a real webcam's real-world color/lighting response. Unlike
tools/calibrate_ball_range.py (which calibrates range_k against Gazebo ground truth and
is sim-only, no analog exists for real hardware), there's no automated ground truth for
a real photo's HSV band, so this is a suggestion tool, not a solver: point it at a
close-up photo of the real ball (fills most of the frame, taken under the actual
deployment lighting), and it reports a threshold band from the photo's own pixel
statistics. Reuses nav_fleet.hsv_detect.rgb_to_hsv (pure numpy, already unit-tested) —
no new color-math code.

Usage: python -m tools.calibrate_hsv_realcam <photo.png> --color red
       python -m tools.calibrate_hsv_realcam <photo.png> --color yellow
Paste the printed block into a new src/nav_fleet/config/hsv_realcam.yaml (see
RealRobotStartup.md Part A) — same shape as hsv_gazebo.yaml (colors/min_pixels/range_k),
range_k stays hsv_gazebo.yaml's value unchanged (no real-camera range calibration exists
yet; the pinhole relation is a property of the camera's focal length, not per-color, so
reusing it is a reasonable starting point until a real discrepancy is observed).
"""
import argparse
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, 'src/nav_fleet')
from nav_fleet.hsv_detect import rgb_to_hsv  # noqa: E402


def suggest_hsv_thresholds(rgb, crop_fraction=0.6, low_pct=5, high_pct=95):
    """Sample the center crop_fraction of an RGB image and suggest an HSV threshold
    band from its own pixel statistics. Handles hue wraparound (red sits near 0/360)
    by shifting the whole hue distribution so its median lands at 180 before taking
    percentiles, then shifting back — this avoids the naive-min/max failure where a
    band straddling the 0/360 seam reports as an enormous [0, 359] range instead of a
    tight one. Returns {'h': [lo, hi], 's_min': float, 'v_min': float}."""
    h_img, w_img = rgb.shape[:2]
    margin_h = int(h_img * (1 - crop_fraction) / 2)
    margin_w = int(w_img * (1 - crop_fraction) / 2)
    crop = rgb[margin_h:h_img - margin_h, margin_w:w_img - margin_w]

    h, s, v = rgb_to_hsv(crop)
    h_flat, s_flat, v_flat = h.flatten(), s.flatten(), v.flatten()

    shift = 180.0 - float(np.median(h_flat))
    h_shifted = (h_flat + shift) % 360.0
    lo = (np.percentile(h_shifted, low_pct) - shift) % 360.0
    hi = (np.percentile(h_shifted, high_pct) - shift) % 360.0

    return {
        'h': [round(float(lo), 1), round(float(hi), 1)],
        's_min': round(float(np.percentile(s_flat, low_pct)), 2),
        'v_min': round(float(np.percentile(v_flat, low_pct)), 2),
    }


def main():
    parser = argparse.ArgumentParser(
        description='Suggest HSV thresholds for a real-camera ball photo'
    )
    parser.add_argument('photo', help='close-up photo of the ball, fills most of frame')
    parser.add_argument('--color', required=True, choices=['red', 'yellow'])
    parser.add_argument('--crop-fraction', type=float, default=0.6,
                        help='center fraction of the photo to sample (default 0.6 — '
                             'avoids background pixels near the frame edges)')
    args = parser.parse_args()

    rgb = np.array(Image.open(args.photo).convert('RGB'))
    result = suggest_hsv_thresholds(rgb, crop_fraction=args.crop_fraction)

    print(f'# Suggested threshold for {args.color!r} — paste into hsv_realcam.yaml,')
    print('# then verify live against ball_detector before trusting it unattended.')
    print(f"  {args.color}: {{h: {result['h']}, s_min: {result['s_min']}, "
          f"v_min: {result['v_min']}}}")


if __name__ == '__main__':
    main()
