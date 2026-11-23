# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""RF-DETR detector: the arithmetic around the network, with no ROS and no GPU code.

A picture goes through three steps:

    prepare()   camera picture (H x W x 3, 0-255)  ->  network input (1 x 3 x S x S)
    a backend   network input                      ->  raw boxes and raw class scores
    decode()    raw boxes and scores               ->  a list of Detection

The backend (nav_fleet.rfdetr_backends) is the only part that differs between machines:
a TensorRT engine on the Jetson's GPU, ONNX Runtime anywhere else. Everything here is
plain numpy so it runs in CI's bare stage 1 and can be checked against the reference
implementation (docs/detection-history.md; the model is RF-DETR, Apache-2.0, exported
to ONNX with its own `export()`).

What the network returns (RF-DETR small: 300 candidates, 91 class slots):
    boxes   (1, Q, 4)  centre x, centre y, width, height, each 0-1 of the picture
    logits  (1, Q, C)  one raw score per candidate per class; sigmoid() gives 0-1
Slot c of the class axis is COCO category id c (slot 0 is unused), so the names below
are indexed by that id.

Lessons from 2026-11-22 that this module encodes (docs/detection-history.md):
  * A confident name can be wrong (a yellow croquet ball is "orange" at 0.92), so the
    name and score are passed on as they are and judged by whoever reads them.
  * The model repeatedly boxes most of the rug as "bed". A box covering more than
    `max_box_fraction` of the picture is not an object on the floor and is dropped.
  * Box width gives distance for a ball to 6-8% with the same k / width rule the
    hand-written detector uses; `ball_like_classes` lists the names a ball arrives under.
"""
from collections import namedtuple

import numpy as np

# COCO category ids as used by the RF-DETR checkpoints (80 names, ids 1-90 with gaps).
COCO_NAMES = {
    1: 'person', 2: 'bicycle', 3: 'car', 4: 'motorcycle', 5: 'airplane', 6: 'bus',
    7: 'train', 8: 'truck', 9: 'boat', 10: 'traffic light', 11: 'fire hydrant',
    13: 'stop sign', 14: 'parking meter', 15: 'bench', 16: 'bird', 17: 'cat', 18: 'dog',
    19: 'horse', 20: 'sheep', 21: 'cow', 22: 'elephant', 23: 'bear', 24: 'zebra',
    25: 'giraffe', 27: 'backpack', 28: 'umbrella', 31: 'handbag', 32: 'tie',
    33: 'suitcase', 34: 'frisbee', 35: 'skis', 36: 'snowboard', 37: 'sports ball',
    38: 'kite', 39: 'baseball bat', 40: 'baseball glove', 41: 'skateboard',
    42: 'surfboard', 43: 'tennis racket', 44: 'bottle', 46: 'wine glass', 47: 'cup',
    48: 'fork', 49: 'knife', 50: 'spoon', 51: 'bowl', 52: 'banana', 53: 'apple',
    54: 'sandwich', 55: 'orange', 56: 'broccoli', 57: 'carrot', 58: 'hot dog',
    59: 'pizza', 60: 'donut', 61: 'cake', 62: 'chair', 63: 'couch', 64: 'potted plant',
    65: 'bed', 67: 'dining table', 70: 'toilet', 72: 'tv', 73: 'laptop', 74: 'mouse',
    75: 'remote', 76: 'keyboard', 77: 'cell phone', 78: 'microwave', 79: 'oven',
    80: 'toaster', 81: 'sink', 82: 'refrigerator', 84: 'book', 85: 'clock', 86: 'vase',
    87: 'scissors', 88: 'teddy bear', 89: 'hair drier', 90: 'toothbrush',
}

# What every RF-DETR checkpoint was trained with (ImageNet statistics, RGB order).
MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)

DEFAULTS = {
    'min_confidence': 0.25,       # below this a box is not reported
    'max_box_fraction': 0.35,     # a box covering more of the picture than this is dropped
    'max_detections': 50,         # most boxes reported for one picture
    'ball_like_classes': ['sports ball', 'orange', 'apple'],
    'ball_range_k': 86.0,         # range_m = ball_range_k / width_px, for 1280-wide pictures
    'range_reference_width_px': 1280,
    'edge_margin_px': 4,          # a box this close to the frame edge gets no distance
    # Color of a ball-like box, read from the pixels inside it (hue in degrees; a band
    # may wrap through 0, as red does). See ball_color().
    'ball_colors': {'yellow': [20, 70], 'red': [300, 20]},
    'color_min_saturation': 0.25,  # paler pixels than this do not vote
    'color_min_value': 0.08,       # darker pixels than this do not vote
    'color_min_fraction': 0.7,     # this share of the box's middle must vote, or no color
    'color_min_agreement': 0.6,    # this share of the votes must be in the winning band
}

# name: what the network called it. color: for a ball-like box, the color read from
# inside the box ('yellow', 'red', ...) or None.
Detection = namedtuple('Detection', 'name score x0 y0 x1 y1 range_m color',
                       defaults=(None,))


def load_config(path=None):
    """DEFAULTS, overridden by the YAML file at `path` when one is given."""
    cfg = dict(DEFAULTS)
    if path:
        import yaml                       # local: the defaults need no YAML
        with open(path) as handle:
            loaded = yaml.safe_load(handle) or {}
        unknown = set(loaded) - set(DEFAULTS)
        if unknown:
            raise ValueError('unknown detector setting(s): %s' % ', '.join(sorted(unknown)))
        cfg.update(loaded)
    if not 0.0 < cfg['min_confidence'] < 1.0:
        raise ValueError('min_confidence must be between 0 and 1')
    if not 0.0 < cfg['max_box_fraction'] <= 1.0:
        raise ValueError('max_box_fraction must be between 0 and 1')
    return cfg


def _opencv():
    """OpenCV if this machine has it, else None. Looked up once."""
    if 'cv2' not in _opencv.__dict__:
        try:
            import cv2
        except ImportError:
            cv2 = None
        _opencv.cv2 = cv2
    return _opencv.cv2


def resize_bilinear(rgb, height, width, use_opencv=True):
    """Resize an H x W x 3 picture straight to height x width (no cropping, no bars),
    as float32. Pixel centers are aligned the way the reference implementation's resize
    aligns them.

    Uses OpenCV when the machine has it: on the Jetson the plain-numpy version below
    took 62 ms for a 1280 x 720 picture against 8 ms, five times the network's own 13 ms
    (measured 2026-11-22). The numpy version is the fallback and the definition: the
    two agree to within rounding, and a test holds them to that."""
    src_h, src_w = rgb.shape[:2]
    if (src_h, src_w) == (height, width):
        return rgb.astype(np.float32)
    cv2 = _opencv() if use_opencv else None
    if cv2 is not None:
        return cv2.resize(np.ascontiguousarray(rgb), (width, height),
                          interpolation=cv2.INTER_LINEAR).astype(np.float32)
    ys = (np.arange(height, dtype=np.float32) + 0.5) * (src_h / height) - 0.5
    xs = (np.arange(width, dtype=np.float32) + 0.5) * (src_w / width) - 0.5
    ys = np.clip(ys, 0, src_h - 1)
    xs = np.clip(xs, 0, src_w - 1)
    y0 = np.floor(ys).astype(np.int32)
    x0 = np.floor(xs).astype(np.int32)
    y1 = np.minimum(y0 + 1, src_h - 1)
    x1 = np.minimum(x0 + 1, src_w - 1)
    wy = (ys - y0)[:, None, None]
    wx = (xs - x0)[None, :, None]
    img = rgb.astype(np.float32)
    top = img[y0][:, x0] * (1 - wx) + img[y0][:, x1] * wx
    bottom = img[y1][:, x0] * (1 - wx) + img[y1][:, x1] * wx
    return top * (1 - wy) + bottom * wy


def prepare(picture, input_hw, bgr=False):
    """Camera picture (H x W x 3, 0-255) -> network input (1 x 3 x S x S, float32).

    `bgr=True` says the picture's channels are blue, green, red (what the robot's camera
    sends). The channels are then swapped AFTER the resize, on the small picture, which
    avoids copying the full-size one just to reorder it."""
    if picture.ndim != 3 or picture.shape[2] != 3:
        raise ValueError('expected an H x W x 3 picture, got shape %s' % (picture.shape,))
    resized = resize_bilinear(picture, int(input_hw[0]), int(input_hw[1]))
    if bgr:
        resized = resized[:, :, ::-1]
    normalized = (resized * (1.0 / 255.0) - MEAN) / STD
    return np.ascontiguousarray(normalized.transpose(2, 0, 1)[None], dtype=np.float32)


def _sigmoid(x):
    return 1.0 / (1.0 + np.exp(-np.clip(x, -60.0, 60.0)))


def estimate_range(name, x0, y0, x1, y1, image_hw, cfg):
    """Distance in metres from the box width, for ball-like names only; NaN otherwise.

    NaN also when the box touches the frame edge: a ball cut by the edge looks narrow
    and would read far too distant (the hand-written detector's 2026-07-17 lesson)."""
    if name not in cfg['ball_like_classes']:
        return float('nan')
    height, width = image_hw
    margin = cfg['edge_margin_px']
    if x0 < margin or y0 < margin or x1 > width - margin or y1 > height - margin:
        return float('nan')
    box_width = x1 - x0
    if box_width <= 0:
        return float('nan')
    scale = width / float(cfg['range_reference_width_px'])
    return float(cfg['ball_range_k']) * scale / box_width


def decode(boxes, logits, image_hw, cfg=None, names=None):
    """Raw network output for one picture -> list of Detection, best score first.

    Follows the reference post-processing: sigmoid over every (candidate, class) pair,
    take the highest-scoring pairs, read the box of each pair's candidate. One candidate
    can therefore appear under two names (the same ball as "sports ball" and "orange");
    both are kept, because which name to believe is the reader's decision."""
    cfg = DEFAULTS if cfg is None else cfg
    names = COCO_NAMES if names is None else names
    boxes = np.asarray(boxes, dtype=np.float32).reshape(-1, 4)
    logits = np.asarray(logits, dtype=np.float32)
    logits = logits.reshape(boxes.shape[0], -1)
    num_classes = logits.shape[1]
    scores = _sigmoid(logits).ravel()
    keep = np.flatnonzero(scores >= cfg['min_confidence'])
    keep = keep[np.argsort(-scores[keep], kind='stable')]
    height, width = image_hw
    out = []
    for flat in keep:
        candidate, class_id = divmod(int(flat), num_classes)
        name = names.get(class_id)
        if name is None:                       # an unused slot of the class axis
            continue
        cx, cy, w, h = (float(v) for v in boxes[candidate])
        x0 = min(max((cx - w / 2) * width, 0.0), float(width))
        y0 = min(max((cy - h / 2) * height, 0.0), float(height))
        x1 = min(max((cx + w / 2) * width, 0.0), float(width))
        y1 = min(max((cy + h / 2) * height, 0.0), float(height))
        if x1 <= x0 or y1 <= y0:
            continue
        if (x1 - x0) * (y1 - y0) > cfg['max_box_fraction'] * width * height:
            continue                           # "the rug is a bed": not an object on the floor
        out.append(Detection(name, float(scores[flat]), x0, y0, x1, y1,
                             estimate_range(name, x0, y0, x1, y1, image_hw, cfg)))
        if len(out) >= cfg['max_detections']:
            break
    return out


def _in_band(hue, band):
    low, high = band
    return (hue >= low) & (hue <= high) if low <= high else (hue >= low) | (hue <= high)


def ball_color(picture, box, cfg, bgr=False):
    """The color name of a ball-like box, from the pixels in the middle of the box, or
    None when they do not agree on one.

    Why this exists (2026-11-22): the network finds a ball in any light but has no idea
    what color it is: a yellow croquet ball is "sports ball" or "orange", a red one
    "sports ball" or "apple". The mission reacts differently to yellow and red. Finding
    a ball BY color is what failed in three sessions (the floor, the light); telling two
    colors apart INSIDE a box the network already drew is a much easier question, and
    the bands can be wide because nothing but the ball is being looked at.

    Only the middle half of the box votes (the corners of a ball's box are floor), and
    only pixels with enough color and light to have a meaningful hue."""
    x0, y0, x1, y1 = (int(round(v)) for v in box)
    w, h = x1 - x0, y1 - y0
    if w < 4 or h < 4:
        return None
    crop = picture[y0 + h // 4:y1 - h // 4, x0 + w // 4:x1 - w // 4].astype(np.float32) / 255.0
    if crop.size == 0:
        return None
    if bgr:
        crop = crop[:, :, ::-1]
    r, g, b = crop[..., 0], crop[..., 1], crop[..., 2]
    value = crop.max(axis=-1)
    spread = value - crop.min(axis=-1)
    saturation = np.where(value > 0, spread / np.maximum(value, 1e-6), 0.0)
    votes = (saturation >= cfg['color_min_saturation']) & (value >= cfg['color_min_value'])
    if votes.mean() < cfg['color_min_fraction']:
        return None
    safe = np.maximum(spread, 1e-6)
    hue = np.where(value == r, ((g - b) / safe) % 6.0,
                   np.where(value == g, (b - r) / safe + 2.0, (r - g) / safe + 4.0)) * 60.0
    hue = hue[votes]
    best, best_share = None, 0.0
    for name, band in cfg['ball_colors'].items():
        share = float(_in_band(hue, band).mean())
        if share > best_share:
            best, best_share = name, share
    return best if best_share >= cfg['color_min_agreement'] else None


class Detector:
    """prepare -> backend -> decode, for one picture at a time.

    `backend` is any object with `input_hw` (height, width of the network input) and
    `infer(batch) -> (boxes, logits)`; see nav_fleet.rfdetr_backends."""

    def __init__(self, backend, cfg=None):
        self.backend = backend
        self.cfg = load_config() if cfg is None else cfg

    def detect(self, picture, bgr=False):
        boxes, logits = self.backend.infer(prepare(picture, self.backend.input_hw, bgr))
        found = decode(boxes[0], logits[0], picture.shape[:2], self.cfg)
        return [d._replace(color=ball_color(picture, d[2:6], self.cfg, bgr))
                if d.name in self.cfg['ball_like_classes'] else d for d in found]
