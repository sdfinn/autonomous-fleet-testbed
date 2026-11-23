# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""nav_fleet.rfdetr_detect and rfdetr_backends: the arithmetic around the RF-DETR
network. No network is run here (no ONNX Runtime, no TensorRT, no ROS): a fake backend
returns hand-made boxes and scores. Agreement with the real network is checked by
reports/detect_exp_20261122/parity.py on the workstation and on the Jetson."""
import math

import numpy as np
import pytest

from nav_fleet import rfdetr_backends, rfdetr_detect
from nav_fleet.rfdetr_detect import COCO_NAMES, DEFAULTS

BALL, ORANGE, BED, TEDDY = 37, 55, 65, 88       # COCO category ids
HW = (720, 1280)


def _logit(p):
    return math.log(p / (1 - p))


def _raw(entries, queries=6, classes=91):
    """Network output with the given (query, class id, probability, cx, cy, w, h)."""
    boxes = np.full((queries, 4), 0.01, dtype=np.float32)
    logits = np.full((queries, classes), -12.0, dtype=np.float32)
    for q, class_id, prob, cx, cy, w, h in entries:
        boxes[q] = (cx, cy, w, h)
        logits[q, class_id] = _logit(prob)
    return boxes, logits


def test_class_names_cover_the_eighty_coco_classes():
    assert len(COCO_NAMES) == 80 and min(COCO_NAMES) == 1 and max(COCO_NAMES) == 90
    assert COCO_NAMES[BALL] == 'sports ball' and COCO_NAMES[TEDDY] == 'teddy bear'


def test_prepare_gives_the_network_its_shape_type_and_scaling():
    grey = np.full((720, 1280, 3), 128, dtype=np.uint8)
    batch = rfdetr_detect.prepare(grey, (512, 512))
    assert batch.shape == (1, 3, 512, 512) and batch.dtype == np.float32
    assert batch.flags['C_CONTIGUOUS']
    expected = (128 / 255.0 - rfdetr_detect.MEAN) / rfdetr_detect.STD
    for channel in range(3):
        assert batch[0, channel] == pytest.approx(expected[channel], abs=1e-5)


def test_prepare_keeps_red_green_blue_in_order():
    red = np.zeros((40, 60, 3), dtype=np.uint8)
    red[..., 0] = 255
    batch = rfdetr_detect.prepare(red, (32, 32))
    assert batch[0, 0].mean() > 2.0 and batch[0, 1].mean() < -2.0 and batch[0, 2].mean() < -1.5


def test_prepare_swaps_channels_for_a_blue_green_red_picture():
    """The robot's camera sends blue, green, red. Told so, prepare gives the same network
    input as for the red, green, blue copy of the same picture."""
    rng = np.random.default_rng(3)
    rgb = rng.integers(0, 256, size=(90, 160, 3), dtype=np.uint8)
    bgr = np.ascontiguousarray(rgb[:, :, ::-1])
    assert np.allclose(rfdetr_detect.prepare(bgr, (64, 64), bgr=True),
                       rfdetr_detect.prepare(rgb, (64, 64)), atol=1e-5)


def test_prepare_rejects_a_picture_that_is_not_three_channel():
    with pytest.raises(ValueError):
        rfdetr_detect.prepare(np.zeros((10, 10), dtype=np.uint8), (32, 32))


def test_resize_keeps_a_left_right_split_where_it_was():
    img = np.zeros((100, 200, 3), dtype=np.uint8)
    img[:, 100:] = 200
    small = rfdetr_detect.resize_bilinear(img, 50, 50, use_opencv=False)
    assert small.shape == (50, 50, 3)
    assert small[:, :24].max() == 0 and small[:, 26:].min() == 200
    same = rfdetr_detect.resize_bilinear(img, 100, 200)
    assert np.array_equal(same, img.astype(np.float32))


def test_opencv_and_numpy_resizes_agree():
    """The fast path must be the same picture as the definition (2026-11-22: 8 ms
    against 62 ms on the Jetson, largest difference 0.013 after normalizing)."""
    pytest.importorskip('cv2')
    rng = np.random.default_rng(7)
    picture = rng.integers(0, 256, size=(720, 1280, 3), dtype=np.uint8)
    fast = rfdetr_detect.resize_bilinear(picture, 512, 512)
    plain = rfdetr_detect.resize_bilinear(picture, 512, 512, use_opencv=False)
    assert fast.shape == plain.shape == (512, 512, 3) and fast.dtype == np.float32
    assert float(np.abs(fast - plain).max()) < 1.5          # out of 255


def test_numpy_resize_is_used_when_opencv_is_absent(monkeypatch):
    monkeypatch.setattr(rfdetr_detect._opencv, 'cv2', None, raising=False)
    img = np.zeros((100, 200, 3), dtype=np.uint8)
    img[:, 100:] = 200
    small = rfdetr_detect.resize_bilinear(img, 50, 50)
    assert small[:, :24].max() == 0 and small[:, 26:].min() == 200


def test_decode_scales_the_box_to_the_picture_and_names_it():
    boxes, logits = _raw([(2, BALL, 0.80, 0.5, 0.5, 0.1, 0.2)])
    (det,) = rfdetr_detect.decode(boxes, logits, HW)
    assert det.name == 'sports ball' and det.score == pytest.approx(0.80, abs=1e-4)
    assert (det.x0, det.x1) == pytest.approx((576.0, 704.0), abs=0.01)
    assert (det.y0, det.y1) == pytest.approx((288.0, 432.0), abs=0.01)


def test_decode_orders_by_score_and_drops_the_weak():
    boxes, logits = _raw([(0, TEDDY, 0.40, 0.3, 0.6, 0.1, 0.1),
                          (1, BALL, 0.90, 0.6, 0.6, 0.05, 0.08),
                          (2, BALL, 0.20, 0.8, 0.6, 0.05, 0.08)])
    dets = rfdetr_detect.decode(boxes, logits, HW)
    assert [(d.name, round(d.score, 2)) for d in dets] == [
        ('sports ball', 0.9), ('teddy bear', 0.4)]


def test_one_object_can_arrive_under_two_names():
    """2026-11-22: the same ball came back as "sports ball" 0.52 and "orange" 0.48.
    Both are passed on; which to believe is the reader's decision."""
    boxes, logits = _raw([(3, BALL, 0.52, 0.2, 0.55, 0.06, 0.1)])
    logits[3, ORANGE] = _logit(0.48)
    dets = rfdetr_detect.decode(boxes, logits, HW)
    assert [d.name for d in dets] == ['sports ball', 'orange']
    assert dets[0][2:6] == dets[1][2:6]


def test_a_box_covering_most_of_the_picture_is_not_an_object():
    """2026-11-22: RF-DETR small boxed most of the rug as "bed" in four of five frames.
    The rug box is the full width of the picture and 41% of its area; the real bed at
    the edge of the view is about 20%."""
    boxes, logits = _raw([(0, BED, 0.54, 0.14, 0.29, 0.285, 0.586),   # real bed, 17%: kept
                          (1, BED, 0.49, 0.5, 0.78, 0.996, 0.416)])   # the rug, 41%: dropped
    dets = rfdetr_detect.decode(boxes, logits, HW)
    assert len(dets) == 1 and dets[0].score == pytest.approx(0.54, abs=1e-4)


def test_unused_class_slots_and_empty_boxes_are_skipped():
    boxes, logits = _raw([(0, 0, 0.9, 0.5, 0.5, 0.1, 0.1),            # slot 0: no such class
                          (1, 12, 0.9, 0.5, 0.5, 0.1, 0.1),           # a gap in the COCO ids
                          (2, BALL, 0.9, 0.5, 0.5, 0.0, 0.1)])        # zero width
    assert rfdetr_detect.decode(boxes, logits, HW) == []


def test_boxes_are_clipped_to_the_picture():
    boxes, logits = _raw([(0, TEDDY, 0.7, 0.02, 0.5, 0.1, 0.2)])
    (det,) = rfdetr_detect.decode(boxes, logits, HW)
    assert det.x0 == 0.0 and det.x1 == pytest.approx(89.6, abs=0.01)


def test_max_detections_caps_the_list():
    entries = [(q, TEDDY, 0.5 + 0.01 * q, 0.1 + 0.1 * q, 0.5, 0.05, 0.05) for q in range(6)]
    cfg = dict(DEFAULTS, max_detections=3)
    dets = rfdetr_detect.decode(*_raw(entries), HW, cfg)
    assert len(dets) == 3 and dets[0].score > dets[2].score


def test_distance_from_box_width_for_ball_like_names_only():
    """Same rule as the hand-written detector: range = k / width. A croquet ball 86 px
    wide in a 1280-wide picture is 1.0 m away."""
    width = 86 / 1280
    boxes, logits = _raw([(0, BALL, 0.8, 0.5, 0.5, width, 0.1),
                          (1, ORANGE, 0.7, 0.3, 0.5, width / 2, 0.05),
                          (2, TEDDY, 0.6, 0.7, 0.5, width, 0.1)])
    by_name = {d.name: d for d in rfdetr_detect.decode(boxes, logits, HW)}
    assert by_name['sports ball'].range_m == pytest.approx(1.0, abs=0.01)
    assert by_name['orange'].range_m == pytest.approx(2.0, abs=0.02)
    assert math.isnan(by_name['teddy bear'].range_m)


def test_distance_scales_with_the_picture_width():
    """Half the picture width, half the pixels across the ball, same distance."""
    boxes, logits = _raw([(0, BALL, 0.8, 0.5, 0.5, 86 / 1280, 0.1)])
    (det,) = rfdetr_detect.decode(boxes, logits, (360, 640))
    assert det.range_m == pytest.approx(1.0, abs=0.01)


def test_a_ball_cut_by_the_frame_edge_gets_no_distance():
    boxes, logits = _raw([(0, BALL, 0.8, 0.03, 0.5, 0.06, 0.1)])      # touches x = 0
    (det,) = rfdetr_detect.decode(boxes, logits, HW)
    assert det.x0 == 0.0 and math.isnan(det.range_m)


def test_config_file_overrides_defaults_and_rejects_unknown_keys(tmp_path):
    good = tmp_path / 'd.yaml'
    good.write_text('min_confidence: 0.4\nball_like_classes: [sports ball]\n')
    cfg = rfdetr_detect.load_config(str(good))
    assert cfg['min_confidence'] == 0.4 and cfg['ball_like_classes'] == ['sports ball']
    assert cfg['max_box_fraction'] == DEFAULTS['max_box_fraction']
    assert rfdetr_detect.load_config() == DEFAULTS
    bad = tmp_path / 'bad.yaml'
    bad.write_text('min_confidense: 0.4\n')
    with pytest.raises(ValueError, match='min_confidense'):
        rfdetr_detect.load_config(str(bad))
    silly = tmp_path / 'silly.yaml'
    silly.write_text('min_confidence: 1.5\n')
    with pytest.raises(ValueError):
        rfdetr_detect.load_config(str(silly))


def test_the_shipped_config_file_loads():
    cfg = rfdetr_detect.load_config('src/nav_fleet/config/detector_rfdetr.yaml')
    assert set(cfg) == set(DEFAULTS)


class _FakeBackend:
    input_hw = (64, 64)

    def __init__(self):
        self.seen = None

    def infer(self, batch):
        self.seen = batch
        boxes, logits = _raw([(1, TEDDY, 0.88, 0.5, 0.5, 0.2, 0.2)])
        return boxes[None], logits[None]


def test_detector_runs_prepare_backend_decode_in_order():
    backend = _FakeBackend()
    picture = np.zeros((480, 640, 3), dtype=np.uint8)
    (det,) = rfdetr_detect.Detector(backend).detect(picture)
    assert backend.seen.shape == (1, 3, 64, 64)
    assert det.name == 'teddy bear'
    assert (det.x0, det.x1, det.y0, det.y1) == pytest.approx((256, 384, 192, 288), abs=0.01)


def test_outputs_are_told_apart_by_shape_not_by_order():
    boxes, logits = np.zeros((1, 300, 4)), np.zeros((1, 300, 91))
    assert rfdetr_backends._split_outputs([boxes, logits])[0] is boxes
    assert rfdetr_backends._split_outputs([logits, boxes])[0] is boxes
    with pytest.raises(RuntimeError):
        rfdetr_backends._split_outputs([boxes])
    with pytest.raises(RuntimeError):
        rfdetr_backends._split_outputs([boxes, boxes])


def test_backend_choice_follows_the_file_extension(monkeypatch):
    made = []
    monkeypatch.setattr(rfdetr_backends, 'TensorRTBackend', lambda p: made.append(('trt', p)))
    monkeypatch.setattr(rfdetr_backends, 'OnnxRuntimeBackend', lambda p: made.append(('ort', p)))
    rfdetr_backends.make_backend('auto', '/m/rfdetr-small.engine')
    rfdetr_backends.make_backend('auto', '/m/rfdetr-small.onnx')
    rfdetr_backends.make_backend('onnxruntime', '/m/x.engine')
    assert made == [('trt', '/m/rfdetr-small.engine'), ('ort', '/m/rfdetr-small.onnx'),
                    ('ort', '/m/x.engine')]
    with pytest.raises(ValueError):
        rfdetr_backends.make_backend('gpu', '/m/x.onnx')


def test_cuda_library_is_looked_for_in_the_jetpack_folder_too(monkeypatch):
    tried = []

    def fake_cdll(path):
        tried.append(path)
        if path != '/usr/local/cuda/lib64/libcudart.so':
            raise OSError('not found')
        return 'loaded'

    monkeypatch.setattr(rfdetr_backends.ctypes, 'CDLL', fake_cdll)
    assert rfdetr_backends._Cuda._load('libcudart.so') == 'loaded'
    assert tried == ['libcudart.so', '/usr/local/cuda/lib64/libcudart.so']
    monkeypatch.setattr(rfdetr_backends.ctypes, 'CDLL',
                        lambda path: (_ for _ in ()).throw(OSError('no')))
    with pytest.raises(RuntimeError, match='CUDA runtime library not found'):
        rfdetr_backends._Cuda._load('libcudart.so')
