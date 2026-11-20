# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""HSV colored-ball detection on RGB frames — numpy (+ scipy for real-camera profiles), no
ROS, no OpenCV.

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

# Optional `shape:` section of a camera profile (2026-11-19). Without it, a colour's
# detection is the bounding box of EVERY matching pixel in the frame -- right for the
# simulator, where the ball is the only thing of its colour. In a real room it is not:
# the wood floor is yellow-orange, so on the real robot the "ball" was a box around the
# whole floor, tens of thousands of pixels wide, read as a ball 4 cm away (well inside
# the reaction distance) with no ball in the room. With a `shape:` section the matching
# pixels are split into connected blobs and only ball-shaped ones count; the largest
# wins. A disc fills pi/4 = 0.785 of its bounding box; shading on a real ball takes that
# down toward 0.6.
SHAPE_DEFAULTS = {
    'min_fill': 0.55,       # blob pixels / bounding-box pixels
    'max_fill': 1.0,
    'max_aspect': 1.35,     # longer bounding-box side / shorter side
    # Same limit for a blob that is WIDER than it is tall (None = use max_aspect). A ball
    # lit from above or behind loses its top to glare, and what is left is the full
    # width but only the lower half. Width is what range is read from, so with a
    # `floor:` section doing the real checking this can be looser than max_aspect.
    'max_flat_aspect': None,
    'min_width_px': 1,      # narrower blobs are speckle, whatever their pixel count
    'open_px': 3,           # erase specks and bridges thinner than this first (0 = off)
}


# Optional `floor:` section of a camera profile (2026-11-20). A ball rests on the floor
# and the camera is at a fixed height, so a nearer ball is both wider in the picture and
# lower in it: the bottom row of a real ball is a straight-line function of its width,
#     bottom_row = row0 + slope * width_px
# whatever the light is doing to its colour. Measured on the real front camera: 15 ball
# sightings (lamp, daylight, curtain; 0.5-1.55 m; yellow and red) within 26 px of the
# line; of 51 false blobs from ball-free photos, one within 30 px, and every one that
# read close enough to cause a reaction 75-359 px off it. With this section a blob must
# sit within `tolerance_px` of the line to count, and the largest blob that DOES is
# taken, not the largest blob in the frame.
FLOOR_KEYS = ('row0', 'slope', 'tolerance_px')


def load_hsv_config(path):
    """Load a per-camera HSV profile (colors, min_pixels, range_k) from YAML."""
    with open(path) as f:
        cfg = yaml.safe_load(f)
    for key in ('colors', 'min_pixels', 'range_k'):
        if key not in cfg:
            raise ValueError(f'hsv config {path} missing key {key!r}')
    if 'shape' in cfg:
        unknown = set(cfg['shape']) - set(SHAPE_DEFAULTS)
        if unknown:
            raise ValueError(f'hsv config {path}: unknown shape key(s) {sorted(unknown)}')
        cfg['shape'] = {**SHAPE_DEFAULTS, **cfg['shape']}
    if 'floor' in cfg:
        if 'shape' not in cfg:
            raise ValueError(f'hsv config {path}: a floor section needs a shape section')
        if set(cfg['floor']) != set(FLOOR_KEYS):
            raise ValueError(f'hsv config {path}: floor needs exactly {list(FLOOR_KEYS)}')
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
    'bottom_px', 'range_m', 'pixels', 'edge_clipped'}. One ball per color per frame by
    design (Mission 2 runs place a single ball; the bounding box of a multi-blob mask
    would simply be wrong — accepted). 'range_m' is NaN when 'edge_clipped' is True
    (see EDGE_MARGIN_PX).
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
        if 'shape' in cfg:
            mask = _largest_ball_shaped_blob(mask, cfg['shape'], cfg['min_pixels'],
                                             cfg.get('floor'))
            if mask is None:
                continue
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
            'bottom_px': int(ys.max()),       # lowest row of the ball (see FLOOR_KEYS)
            # A colour may carry its own range_k (see hsv_realcam.yaml for why).
            'range_m': (float('nan') if clipped
                        else band.get('range_k', cfg['range_k']) / width),
            'pixels': pixels,
            'edge_clipped': clipped,
        })
    return out


def _largest_ball_shaped_blob(mask, shape, min_pixels, floor=None):
    """The biggest connected blob in `mask` that could be a ball, as a mask of its own;
    None if there is none. See SHAPE_DEFAULTS for what "could be a ball" means, and
    FLOOR_KEYS for the extra test a `floor` section adds."""
    from scipy import ndimage          # local: the simulator profile never needs it
    shape = {**SHAPE_DEFAULTS, **shape}
    original = mask
    brush = None
    if shape['open_px']:
        size = int(shape['open_px'])
        brush = np.ones((size, size), dtype=bool)
        mask = ndimage.binary_opening(mask, structure=brush)
    labels, count = ndimage.label(mask, structure=np.ones((3, 3), dtype=bool))
    if count == 0:
        return None
    areas = np.bincount(labels.ravel())
    best = None
    for index, box in enumerate(ndimage.find_objects(labels), start=1):
        area = int(areas[index])
        if area < min_pixels:
            continue
        height = box[0].stop - box[0].start
        width = box[1].stop - box[1].start
        if width < shape['min_width_px']:
            continue
        flat_limit = shape['max_flat_aspect'] or shape['max_aspect']
        if width >= height:
            if width / height > flat_limit:
                continue
        elif height / width > shape['max_aspect']:
            continue
        if floor is not None:
            expected_bottom = floor['row0'] + floor['slope'] * width
            if abs((box[0].stop - 1) - expected_bottom) > floor['tolerance_px']:
                continue
        if not shape['min_fill'] <= area / (width * height) <= shape['max_fill']:
            continue
        if best is None or area > best[0]:
            best = (area, index)
    if best is None:
        return None
    blob = labels == best[1]
    if brush is not None:
        # Opening also shaves the blob's own one-pixel-wide extremes (a disc's top,
        # bottom and sides), which would make every ball read 2 px narrower and so a
        # little further away. Give back the original pixels that touch the blob.
        blob = ndimage.binary_dilation(blob, structure=brush) & original
    return blob
