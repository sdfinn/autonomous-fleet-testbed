"""Unit tests for HSV ball detection — pure numpy, no ROS2 (runs in stage-1)."""
import math

import numpy as np
import pytest


def _frame(w=64, h=48, bg=(180, 180, 180)):
    return np.full((h, w, 3), bg, dtype=np.uint8)


def _paint(frame, x0, y0, x1, y1, rgb):
    frame[y0:y1, x0:x1] = rgb
    return frame


@pytest.fixture
def cfg():
    from nav_fleet.hsv_detect import load_hsv_config
    return load_hsv_config('src/nav_fleet/config/hsv_gazebo.yaml')


def test_detects_red_patch(cfg):
    from nav_fleet.hsv_detect import detect_balls
    frame = _paint(_frame(), 10, 10, 30, 30, (220, 20, 20))
    out = detect_balls(frame, cfg)
    assert [d['color'] for d in out] == ['red']
    d = out[0]
    assert d['width_px'] == 20 and d['height_px'] == 20
    assert d['cx'] == pytest.approx(19.5, abs=0.5)
    assert d['range_m'] == pytest.approx(cfg['range_k'] / 20)


def test_detects_yellow_not_green(cfg):
    from nav_fleet.hsv_detect import detect_balls
    frame = _paint(_frame(), 5, 5, 25, 25, (220, 220, 20))    # yellow, hue ~60
    frame = _paint(frame, 40, 5, 60, 25, (20, 220, 20))       # green sphere, hue ~120
    out = detect_balls(frame, cfg)
    assert [d['color'] for d in out] == ['yellow']


def test_red_hue_wraparound(cfg):
    from nav_fleet.hsv_detect import detect_balls
    # hue just below 360 (pinkish red) must still match the wrapped red band
    frame = _paint(_frame(), 10, 10, 30, 30, (220, 20, 60))
    assert [d['color'] for d in detect_balls(frame, cfg)] == ['red']


def test_ignores_small_speckle(cfg):
    from nav_fleet.hsv_detect import detect_balls
    frame = _paint(_frame(), 10, 10, 13, 13, (220, 20, 20))   # 9 px < min_pixels
    assert detect_balls(frame, cfg) == []


def test_empty_frame_returns_empty(cfg):
    from nav_fleet.hsv_detect import detect_balls
    assert detect_balls(_frame(), cfg) == []


def test_edge_clipped_bbox_range_excluded(cfg):
    """A bbox touching the frame border (Task 9, 2026-07-17) has an unreliable
    width-derived range — range_m must be NaN and edge_clipped True, so a downstream
    numeric range comparison naturally excludes it from the reaction trigger."""
    from nav_fleet.hsv_detect import detect_balls
    frame = _paint(_frame(), 0, 10, 20, 30, (220, 20, 20))  # touches left edge (x=0)
    out = detect_balls(frame, cfg)
    assert len(out) == 1
    assert out[0]['edge_clipped'] is True
    assert math.isnan(out[0]['range_m'])


def test_interior_bbox_range_included(cfg):
    """A bbox well clear of every border is NOT edge-clipped and keeps a normal,
    finite width-derived range estimate."""
    from nav_fleet.hsv_detect import detect_balls
    frame = _paint(_frame(), 10, 10, 30, 30, (220, 20, 20))
    out = detect_balls(frame, cfg)
    assert out[0]['edge_clipped'] is False
    assert out[0]['range_m'] == pytest.approx(cfg['range_k'] / 20)
