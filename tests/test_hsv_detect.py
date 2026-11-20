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


# --- `shape:` profiles (real cameras): only ball-shaped blobs count ---
YELLOW = (230, 200, 20)
WOOD = (200, 150, 30)        # the bedroom floor: inside the yellow band too


def _disc(frame, cx, cy, r, rgb):
    yy, xx = np.mgrid[:frame.shape[0], :frame.shape[1]]
    frame[(xx - cx) ** 2 + (yy - cy) ** 2 <= r * r] = rgb
    return frame


@pytest.fixture
def real_cfg(cfg):
    from nav_fleet.hsv_detect import SHAPE_DEFAULTS
    out = dict(cfg)
    out['colors'] = {'yellow': {'h': [30, 60], 's_min': 0.5, 'v_min': 0.2}}
    out['shape'] = dict(SHAPE_DEFAULTS)
    return out


def test_shape_profile_boxes_the_ball_not_the_whole_wood_floor(real_cfg):
    """2026-11-19, the real robot: with no ball in the room the floor alone was a
    'yellow ball 4 cm away'. With a ball, the box must be the ball's."""
    from nav_fleet.hsv_detect import detect_balls
    frame = _frame(w=320, h=240)
    _paint(frame, 0, 180, 320, 240, WOOD)              # floor: a wide strip
    _disc(frame, 100, 100, 20, YELLOW)                 # the ball, clear of the floor
    (det,) = detect_balls(frame, real_cfg)
    assert det['color'] == 'yellow'
    assert det['width_px'] == 41 and det['height_px'] == 41
    assert det['cx'] == pytest.approx(100, abs=0.5) and det['cy'] == pytest.approx(100, abs=0.5)
    assert det['range_m'] == pytest.approx(real_cfg['range_k'] / 41)


def test_shape_profile_sees_nothing_in_a_ball_free_room(real_cfg):
    from nav_fleet.hsv_detect import detect_balls
    frame = _frame(w=320, h=240)
    _paint(frame, 0, 180, 320, 240, WOOD)              # floor
    _paint(frame, 250, 20, 262, 150, WOOD)             # a table leg: tall and thin
    assert detect_balls(frame, real_cfg) == []


def test_without_a_shape_section_the_same_room_is_one_big_false_ball(cfg):
    """Pins the old behaviour the simulator profile still uses -- and shows the bug."""
    from nav_fleet.hsv_detect import detect_balls
    frame = _frame(w=320, h=240)
    _paint(frame, 10, 180, 310, 230, WOOD)
    dets = [d for d in detect_balls(frame, cfg) if d['color'] == 'yellow']
    assert len(dets) == 1 and dets[0]['width_px'] == 300


def test_shape_profile_picks_the_largest_of_two_balls(real_cfg):
    from nav_fleet.hsv_detect import detect_balls
    frame = _frame(w=320, h=240)
    _disc(frame, 60, 60, 8, YELLOW)
    _disc(frame, 200, 120, 25, YELLOW)
    (det,) = detect_balls(frame, real_cfg)
    assert det['width_px'] == 51 and det['cx'] == pytest.approx(200, abs=0.5)


def test_shape_profile_accepts_a_ball_with_a_shaded_edge(real_cfg):
    """A real ball's dark underside drops out of the colour band: still a ball."""
    from nav_fleet.hsv_detect import detect_balls
    frame = _frame(w=320, h=240)
    _disc(frame, 160, 120, 30, YELLOW)
    _paint(frame, 120, 138, 200, 160, (180, 180, 180))  # bottom fifth missing
    (det,) = detect_balls(frame, real_cfg)
    assert det['width_px'] == 61


def test_shape_profile_ignores_specks_joined_to_nothing(real_cfg):
    from nav_fleet.hsv_detect import detect_balls
    real_cfg['shape']['min_width_px'] = 12
    frame = _frame(w=320, h=240)
    _disc(frame, 50, 50, 4, YELLOW)                    # 9 px wide: round, but a speck
    assert detect_balls(frame, real_cfg) == []


def test_shape_profile_still_marks_a_ball_cut_by_the_frame_edge(real_cfg):
    from nav_fleet.hsv_detect import detect_balls
    frame = _frame(w=320, h=240)
    _disc(frame, 3, 120, 20, YELLOW)                   # mostly in frame, clipped left
    real_cfg['shape']['max_aspect'] = 2.0
    (det,) = detect_balls(frame, real_cfg)
    assert det['edge_clipped'] and math.isnan(det['range_m'])


def test_shape_section_is_validated_and_filled_with_defaults(tmp_path):
    from nav_fleet.hsv_detect import SHAPE_DEFAULTS, load_hsv_config
    good = tmp_path / 'good.yaml'
    good.write_text('colors: {}\nmin_pixels: 40\nrange_k: 80.0\nshape: {min_fill: 0.6}\n')
    assert load_hsv_config(str(good))['shape'] == {**SHAPE_DEFAULTS, 'min_fill': 0.6}
    bad = tmp_path / 'bad.yaml'
    bad.write_text('colors: {}\nmin_pixels: 40\nrange_k: 80.0\nshape: {roundness: 1}\n')
    with pytest.raises(ValueError, match='roundness'):
        load_hsv_config(str(bad))


def test_the_simulator_profile_has_no_shape_section():
    """Sim detection must stay exactly as it was; only real-camera profiles opt in."""
    from nav_fleet.hsv_detect import load_hsv_config
    assert 'shape' not in load_hsv_config('src/nav_fleet/config/hsv_gazebo.yaml')


def test_a_colour_can_carry_its_own_range_k(real_cfg):
    """Real camera: the red ball's dark rim drops out of the band, so red measures
    narrower than yellow at the same distance and needs its own scale."""
    from nav_fleet.hsv_detect import detect_balls
    real_cfg['colors']['yellow']['range_k'] = 90.0
    frame = _frame(w=320, h=240)
    _disc(frame, 160, 120, 22, YELLOW)                 # 45 px wide
    (det,) = detect_balls(frame, real_cfg)
    assert det['range_m'] == pytest.approx(90.0 / 45)


def test_real_camera_profile_loads_and_is_a_shape_profile():
    from nav_fleet.hsv_detect import load_hsv_config
    cfg = load_hsv_config('src/nav_fleet/config/hsv_realcam.yaml')
    assert set(cfg['colors']) == {'red', 'yellow'}
    assert cfg['shape']['max_aspect'] == 1.35 and cfg['shape']['open_px'] == 3
    lo, hi = cfg['colors']['red']['h']
    assert lo > hi                                     # red wraps through 0
    # Reaction distances are 1.3 m (red) and 0.8 m (yellow): the simulator's 47.1
    # would read every real ball at about half its distance.
    assert 75 < cfg['colors']['red']['range_k'] < 85
    assert 88 < cfg['colors']['yellow']['range_k'] < 96
