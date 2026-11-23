# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""What mission logic is given about one object in one picture.

The detector (a separate process, nav_fleet.object_detector) publishes boxes with names
and scores. This file turns one such box into a Detection: class, confidence, kind,
bearing, distance and where the distance came from. It is the only place that knows the
detector's message layout and the only place that decides a kind, so a different
detector changes nothing above it.

Where this came from (2026-11-23): the sister project, wayfarer, wrote this layer first
(its `nav_fleet/detection.py`). The six fields, the three kinds and the function names
are kept identical on purpose, so that a mission's behavior tree or a brain proven there
reads the same object here. The code is a copy written into this repo: neither project
imports the other. What differs here: the camera is an argument (this repo has two, the
simulated one and the real one), and the table of objects is this robot's.

Pure Python, no ROS: the message is read by attribute, so tests pass plain objects.
"""
import math
from dataclasses import asdict, dataclass

KNOWN, HAZARD, UNKNOWN = 'known', 'hazard', 'unknown'
FROM_WIDTH, FROM_DEPTH, FROM_LIDAR, FROM_NOTHING = 'width', 'depth', 'lidar', 'none'


@dataclass(frozen=True)
class Camera:
    """What is needed to turn a pixel column into an angle and a box width into a
    distance: the picture's size and the horizontal field of view."""
    width_px: int
    height_px: int
    hfov_rad: float

    @property
    def focal_px(self):
        return (self.width_px / 2.0) / math.tan(self.hfov_rad / 2.0)


# The simulated camera: src/nav_fleet/urdf/ugv_pt.urdf.xacro.
GAZEBO_CAMERA = Camera(640, 480, 1.047)
# The real camera (OAK, 1280 x 720). Its field of view is NOT measured: 1.052 rad
# (60.3 deg) is what the detector's measured ball constant implies (86.0 pixel-meters for
# a 0.078 m ball gives a focal length of 1103 pixels). Good enough for a bearing; measure
# it before a bearing is used to place an object on the map.
OAK_CAMERA = Camera(1280, 720, 1.052)
# A reader that sees the pictures can tell the two apart by their width.
CAMERA_BY_WIDTH = {c.width_px: c for c in (GAZEBO_CAMERA, OAK_CAMERA)}

# Every class mission logic may act on. A class missing from this table, or seen with
# less than its minimum confidence, is given the kind UNKNOWN: it keeps the detector's
# name ("teddy bear", "refrigerator") and nothing reacts to it.
#
# The minimums are 0 because a detector's score is not a measure of being right (a
# yellow ball was "orange" at 0.92, docs/detection-history.md); the detector's own
# min_confidence already removes the weakest boxes.
#
# size_m is the object's real width. It gives a distance from the width of its box when
# the detector sends none. The simulator's ball is 0.086 m (tools/mission2_harness.py);
# the real croquet ball is 0.078 m.
BALL_SIZE_M = 0.086
OBJECTS = {
    'red_ball':    {'kind': HAZARD, 'min_confidence': 0.0, 'size_m': BALL_SIZE_M},
    'yellow_ball': {'kind': HAZARD, 'min_confidence': 0.0, 'size_m': BALL_SIZE_M},
}
# A box within this many pixels of the picture's edge is cut off there, so its width is
# not the object's width. A box cut off only at the top or bottom keeps a usable width
# while its height is at least this fraction of its width (the widest part is in view).
EDGE_MARGIN_PX = 2
WIDTH_VALID_MIN_ASPECT = 0.6


@dataclass(frozen=True)
class Detection:
    class_name: str            # the detector's name for it, e.g. 'red_ball'
    confidence: float          # the detector's score, 0 to 1. NOT a measure of being right
    kind: str                  # KNOWN, HAZARD or UNKNOWN
    bearing_rad: float         # from the camera's axis, left positive
    distance_m: float | None   # from the lens; None when there is none to trust
    distance_from: str         # FROM_WIDTH, FROM_DEPTH, FROM_LIDAR or FROM_NOTHING

    def as_dict(self):
        return asdict(self)


def kind_of(class_name, confidence, objects=OBJECTS):
    entry = objects.get(class_name)
    if entry is None or confidence < entry['min_confidence']:
        return UNKNOWN
    return entry['kind']


def bearing_from_pixel(cx, camera=GAZEBO_CAMERA):
    """Angle of a pixel column from the camera's axis; left of center is positive.
    Pinhole camera: a column `offset` pixels left of center is at atan(offset / focal)."""
    return math.atan((camera.width_px / 2.0 - cx) / camera.focal_px)


def make_detection(class_name, confidence, cx, distance_m, distance_from=FROM_WIDTH,
                   objects=OBJECTS, camera=GAZEBO_CAMERA):
    """One Detection from a box: its name, score, center column in pixels and distance.
    A distance that is missing, not a number or not positive becomes None, FROM_NOTHING
    (the detector sends NaN for a box cut off by the picture's edge)."""
    if distance_m is None or not math.isfinite(distance_m) or distance_m <= 0:
        distance_m, distance_from = None, FROM_NOTHING
    return Detection(class_name, float(confidence),
                     kind_of(class_name, confidence, objects),
                     bearing_from_pixel(cx, camera), distance_m, distance_from)


def distance_from_box(class_name, cx, cy, width_px, height_px, objects=OBJECTS,
                      camera=GAZEBO_CAMERA):
    """Distance from the lens to an object of known size, from the width of its box:
    focal length (pixels) x real width / width in pixels. None when the class has no
    known size, or the box is cut off by the picture's edge so its width is not the
    object's width."""
    size_m = objects.get(class_name, {}).get('size_m')
    if size_m is None or width_px <= 0:
        return None
    left, right = cx - width_px / 2, cx + width_px / 2
    top, bottom = cy - height_px / 2, cy + height_px / 2
    side_cut = left < EDGE_MARGIN_PX or right > camera.width_px - EDGE_MARGIN_PX
    top_bottom_cut = top < EDGE_MARGIN_PX or bottom > camera.height_px - EDGE_MARGIN_PX
    if side_cut or (top_bottom_cut and height_px < WIDTH_VALID_MIN_ASPECT * width_px):
        return None
    return camera.focal_px * size_m / width_px


def from_detector_msg(msg, objects=OBJECTS, camera=GAZEBO_CAMERA):
    """Every object in one vision_msgs/Detection2DArray.

    The distance convention of results[0].pose.pose.position.x:
      a positive number  the detector's own estimate, in meters. Used as it is.
      NaN                the detector looked and does not trust a distance for this box
                         (cut off by the picture's edge, or not a ball). Stays "none".
      0.0                the detector sends boxes only. The distance is worked out here
                         from the box's width and the object's real size.
    This repo's detector sends the first two; wayfarer's own node sent the third."""
    out = []
    for det in msg.detections:
        if not det.results:
            continue
        name = det.results[0].hypothesis.class_id
        center = det.bbox.center.position
        distance = det.results[0].pose.pose.position.x
        if distance == 0.0:
            distance = distance_from_box(name, center.x, center.y, det.bbox.size_x,
                                         det.bbox.size_y, objects, camera)
        out.append(make_detection(name, det.results[0].hypothesis.score, center.x,
                                  distance, objects=objects, camera=camera))
    return out
