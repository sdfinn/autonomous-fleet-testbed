# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""HSV colored-ball detection on RGB frames — pure numpy, no ROS, no OpenCV.

The algorithm is BC/isaac_project's hardware-proven HSV thresholding
(behavior_controller.py) reimplemented to this project's conventions (spec §4):
threshold in HSV, take the mask's bounding box, estimate range from apparent width via
the pinhole relation range_m = range_k / width_px. Pure so it is unit-testable on CI
runners without ROS2 (stage-1). Thresholds and range_k are per-camera CONFIG, not code.
"""
import numpy as np
import yaml

# Task 9 fix (2026-07-17): a bounding box touching (within this many px of) the frame
# border is CLIPPED — its true width extends past the frame edge, so width_px
# underestimates the ball's apparent size and range_m = range_k / width_px overshoots
# badly (a live run measured 2.9-6.7 m estimated range for a true ~1.1 m distance).
# Such detections must not drive the reaction trigger. range_m is set to NaN rather than
# omitted so callers doing a numeric range comparison (est_range <= threshold) exclude
# them automatically with no extra branching — see mission_runner._detection_cb.
EDGE_MARGIN_PX = 2


def load_hsv_config(path):
    """Load a per-camera HSV profile (colors, min_pixels, range_k) from YAML."""
    with open(path) as f:
        cfg = yaml.safe_load(f)
    for key in ('colors', 'min_pixels', 'range_k'):
        if key not in cfg:
            raise ValueError(f'hsv config {path} missing key {key!r}')
    return cfg


def rgb_to_hsv(rgb):
    """Vectorized RGB uint8 [H,W,3] -> (h degrees 0-360, s 0-1, v 0-1) float arrays."""
    arr = rgb.astype(np.float64) / 255.0
    r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
    v = arr.max(axis=-1)
    c = v - arr.min(axis=-1)
    safe_c = np.where(c == 0, 1.0, c)
    h = np.where(
        c == 0, 0.0,
        np.where(v == r, ((g - b) / safe_c) % 6,
                 np.where(v == g, (b - r) / safe_c + 2, (r - g) / safe_c + 4)),
    ) * 60.0
    s = np.where(v > 0, c / np.where(v == 0, 1.0, v), 0.0)
    return h, s, v


def detect_balls(rgb, cfg):
    """Detect configured ball colors in one RGB frame.

    Returns one dict per detected color: {'color', 'cx', 'cy', 'width_px', 'height_px',
    'range_m', 'pixels', 'edge_clipped'}. One ball per color per frame by design (Mission
    2 runs place a single ball; the bounding box of a multi-blob mask would simply be
    wrong — accepted). 'range_m' is NaN when 'edge_clipped' is True (see EDGE_MARGIN_PX).
    """
    h_img, w_img = rgb.shape[:2]
    h, s, v = rgb_to_hsv(rgb)
    out = []
    for color, band in cfg['colors'].items():
        h_lo, h_hi = band['h']
        if h_lo <= h_hi:
            mask = (h >= h_lo) & (h <= h_hi)
        else:  # band wraps through 0 (red)
            mask = (h >= h_lo) | (h <= h_hi)
        mask &= (s >= band['s_min']) & (v >= band['v_min'])
        pixels = int(mask.sum())
        if pixels < cfg['min_pixels']:
            continue
        ys, xs = np.nonzero(mask)
        width = int(xs.max() - xs.min() + 1)
        clipped = bool(xs.min() < EDGE_MARGIN_PX or xs.max() >= w_img - EDGE_MARGIN_PX
                       or ys.min() < EDGE_MARGIN_PX or ys.max() >= h_img - EDGE_MARGIN_PX)
        out.append({
            'color': color,
            'cx': float(xs.mean()),
            'cy': float(ys.mean()),
            'width_px': width,
            'height_px': int(ys.max() - ys.min() + 1),
            'range_m': float('nan') if clipped else cfg['range_k'] / width,
            'pixels': pixels,
            'edge_clipped': clipped,
        })
    return out
