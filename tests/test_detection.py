# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""What mission logic is given about an object (nav_fleet.detection).
Scripted detections only: no ROS, no simulator."""
import math
from types import SimpleNamespace as NS

import pytest

from nav_fleet import detection as d


def test_a_class_in_the_table_gets_the_tables_kind():
    assert d.make_detection('red_ball', 0.9, 320.0, 1.0).kind == d.HAZARD
    assert d.make_detection('yellow_ball', 0.9, 320.0, 1.0).kind == d.HAZARD


def test_a_class_not_in_the_table_is_unknown_and_keeps_its_name():
    det = d.make_detection('teddy bear', 0.92, 320.0, 1.0)
    assert det.kind == d.UNKNOWN and det.class_name == 'teddy bear'


def test_a_class_below_its_minimum_confidence_is_unknown():
    table = {'red_ball': {'kind': d.HAZARD, 'min_confidence': 0.5}}
    assert d.make_detection('red_ball', 0.4, 320.0, 1.0, objects=table).kind == d.UNKNOWN
    assert d.make_detection('red_ball', 0.5, 320.0, 1.0, objects=table).kind == d.HAZARD


@pytest.mark.parametrize('bad', [float('nan'), float('inf'), 0.0, -1.0, None])
def test_a_distance_that_cannot_be_trusted_becomes_none(bad):
    det = d.make_detection('red_ball', 0.9, 320.0, bad)
    assert det.distance_m is None and det.distance_from == d.FROM_NOTHING


def test_a_good_distance_is_kept_with_where_it_came_from():
    det = d.make_detection('red_ball', 0.9, 320.0, 1.2)
    assert det.distance_m == 1.2 and det.distance_from == d.FROM_WIDTH


@pytest.mark.parametrize('camera', [d.GAZEBO_CAMERA, d.OAK_CAMERA])
def test_bearing_is_zero_at_the_center_and_half_the_field_of_view_at_the_edges(camera):
    def bearing(cx):
        return d.make_detection('red_ball', 0.9, cx, 1.0, camera=camera).bearing_rad
    assert bearing(camera.width_px / 2.0) == pytest.approx(0.0)
    assert bearing(0.0) == pytest.approx(camera.hfov_rad / 2)             # left: positive
    assert bearing(float(camera.width_px)) == pytest.approx(-camera.hfov_rad / 2)


def test_the_real_cameras_focal_length_matches_the_detectors_measured_ball_constant():
    # config/detector_rfdetr.yaml: ball_range_k 86.0 pixel-meters for a 0.078 m ball.
    assert d.OAK_CAMERA.focal_px * 0.078 == pytest.approx(86.0, rel=0.01)


def _box(class_id, score, cx, distance, cy=240.0, width=40.0, height=40.0):
    hyp = NS(hypothesis=NS(class_id=class_id, score=score),
             pose=NS(pose=NS(position=NS(x=distance))))
    return NS(results=[hyp],
              bbox=NS(center=NS(position=NS(x=cx, y=cy)), size_x=width, size_y=height))


def test_from_detector_msg_matches_make_detection_and_skips_a_box_with_no_result():
    msg = NS(detections=[_box('yellow_ball', 0.3, 100.0, 0.7),
                         NS(results=[], bbox=None),
                         _box('red_ball', 0.8, 320.0, float('nan'))])
    assert d.from_detector_msg(msg) == [
        d.make_detection('yellow_ball', 0.3, 100.0, 0.7),
        d.make_detection('red_ball', 0.8, 320.0, float('nan'))]


def test_nan_from_the_detector_stays_no_distance_even_for_a_class_of_known_size():
    """NaN means the detector looked and does not trust a distance. It must not be
    replaced by one worked out here: that would undo the detector's edge rule."""
    (det,) = d.from_detector_msg(NS(detections=[_box('red_ball', 0.8, 320.0, float('nan'))]))
    assert det.distance_m is None and det.distance_from == d.FROM_NOTHING


def test_zero_from_a_boxes_only_detector_gets_a_distance_from_the_objects_real_size():
    (det,) = d.from_detector_msg(NS(detections=[_box('red_ball', 0.8, 320.0, 0.0, width=47.0)]))
    # focal 554.3 px x 0.086 m / 47 px
    assert det.distance_m == pytest.approx(1.014, abs=0.005)
    assert det.distance_from == d.FROM_WIDTH


def test_distance_from_box_needs_a_known_size_and_a_box_that_is_not_cut_off():
    cam = d.GAZEBO_CAMERA
    assert d.distance_from_box('teddy bear', 320, 240, 40, 40) is None        # size unknown
    assert d.distance_from_box('red_ball', 320, 240, 0, 40) is None
    assert d.distance_from_box('red_ball', 15, 240, 40, 40) is None           # cut at the left
    assert d.distance_from_box('red_ball', cam.width_px - 15, 240, 40, 40) is None
    # cut at the bottom only: usable while most of the ball's height still shows
    assert d.distance_from_box('red_ball', 320, cam.height_px - 15, 40, 30) is not None
    assert d.distance_from_box('red_ball', 320, cam.height_px - 5, 40, 10) is None


def test_as_dict_has_the_six_fields_and_is_plain_data():
    out = d.make_detection('red_ball', 0.9, 320.0, 1.0).as_dict()
    assert set(out) == {'class_name', 'confidence', 'kind', 'bearing_rad', 'distance_m',
                        'distance_from'}
    assert not math.isnan(out['bearing_rad'])
