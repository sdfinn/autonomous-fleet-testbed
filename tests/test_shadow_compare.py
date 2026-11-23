# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""tools/shadow_compare.py: lining up the hand-written detector and RF-DETR on one run.
Plain lists in, no ROS and no bag (read_bag is the only part that needs them)."""
import math
import types

from tools import shadow_compare as sc
from tools.shadow_compare import Box, Frame

NAN = float('nan')


def _ball(name, cx, width, range_m, score=0.9):
    return Box(name, score, range_m, cx, 400.0, width, width)


def test_same_object_needs_overlap_and_similar_size():
    yellow = _ball('yellow_ball', 300, 80, 1.0)
    assert sc.same_object(yellow, _ball('orange', 310, 84, 1.02))
    assert not sc.same_object(yellow, _ball('sports ball', 600, 80, 1.0))     # elsewhere
    assert not sc.same_object(yellow, Box('bed', 0.4, NAN, 300, 400, 900, 300))  # far bigger
    assert not sc.same_object(yellow, _ball('x', 300, 0, 1.0))


def test_frames_pair_by_picture_stamp_only():
    main = [Frame(10.00, []), Frame(10.28, []), Frame(10.56, [])]
    shadow = [Frame(10.00, []), Frame(10.10, []), Frame(10.28, []), Frame(10.40, [])]
    pairs = sc.pair_frames(main, shadow)
    assert [(m.stamp, s.stamp if s else None) for m, s in pairs] == [
        (10.00, 10.00), (10.28, 10.28), (10.56, None)]
    assert sc.pair_frames(main, []) == [(f, None) for f in main]


def test_compare_reports_agreement_names_and_distance():
    main = [Frame(5.0, [_ball('yellow_ball', 300, 60, 1.50)]),
            Frame(5.3, [_ball('yellow_ball', 300, 80, 1.10)]),
            Frame(5.6, [_ball('yellow_ball', 300, 100, 0.90), _ball('red_ball', 700, 50, 1.6)])]
    shadow = [Frame(5.0, [_ball('orange', 302, 58, 1.48), _ball('teddy bear', 900, 150, NAN)]),
              Frame(5.1, [_ball('orange', 302, 62, 1.40)]),          # a picture main skipped
              Frame(5.3, [_ball('sports ball', 301, 78, 1.12)]),
              Frame(5.6, [_ball('orange', 300, 99, 0.87)])]           # red not boxed
    out = sc.compare(main, shadow)
    assert (out['main_frames'], out['shadow_frames'], out['paired_frames']) == (3, 4, 3)
    yellow = out['objects']['yellow_ball']
    assert (yellow['frames'], yellow['also_boxed']) == (3, 3)
    assert yellow['names'] == {'orange': 2, 'sports ball': 1}
    assert [round(d, 2) for d in yellow['range_diff']] == [-0.02, 0.02, -0.03]
    assert yellow['first_main_s'] == 0.0 and yellow['first_main_range'] == 1.50
    red = out['objects']['red_ball']
    assert (red['frames'], red['also_boxed']) == (1, 0)
    assert out['shadow_only'] == {'teddy bear': 1}
    assert out['unpaired_shadow'] == {'orange': 1}
    assert out['main_rate_hz'] > 3.0 and out['shadow_rate_hz'] > 4.9
    text = sc.report(out)
    assert 'RF-DETR boxed the same object in 3 (100%)' in text
    assert 'orange x2, sports ball x1' in text and 'teddy bear x1' in text
    assert 'median -0.02 m' in text


def test_a_box_without_distance_is_counted_but_not_measured():
    out = sc.compare([Frame(1.0, [_ball('red_ball', 400, 70, NAN)])],
                     [Frame(1.0, [_ball('apple', 400, 70, 1.2)])])
    red = out['objects']['red_ball']
    assert red['also_boxed'] == 1 and red['range_diff'] == []
    assert 'no distance' in sc.report(out)


def test_empty_runs_do_not_crash():
    out = sc.compare([], [])
    assert out['paired_frames'] == 0 and out['main_rate_hz'] == 0.0
    assert 'reported no object' in sc.report(out)


def test_boxes_from_a_message_shaped_object():
    ns = types.SimpleNamespace
    det = ns(results=[ns(hypothesis=ns(class_id='sports ball', score=0.8),
                         pose=ns(pose=ns(position=ns(x=1.25))))],
             bbox=ns(center=ns(position=ns(x=640.0, y=400.0)), size_x=70.0, size_y=72.0))
    empty = ns(results=[], bbox=None)
    msg = ns(header=ns(stamp=ns(sec=12, nanosec=500_000_000)), detections=[det, empty])
    frame = sc.boxes_from_msg(msg)
    assert math.isclose(frame.stamp, 12.5)
    assert frame.boxes == [Box('sports ball', 0.8, 1.25, 640.0, 400.0, 70.0, 72.0)]


def test_wrong_arguments_print_usage(capsys):
    assert sc.main([]) == 2
    assert 'usage:' in capsys.readouterr().out
