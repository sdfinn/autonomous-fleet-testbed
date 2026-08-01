# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
import numpy as np

from tools.calibrate_hsv_realcam import suggest_hsv_thresholds


def _solid_image(rgb_triplet, size=40):
    img = np.zeros((size, size, 3), dtype=np.uint8)
    img[:, :] = rgb_triplet
    return img


def test_solid_yellow_image_yields_tight_band_around_yellow_hue():
    # Pure yellow (255,255,0) is hue 60.
    img = _solid_image((255, 255, 0))
    result = suggest_hsv_thresholds(img)
    lo, hi = result['h']
    assert 50 <= lo <= 60
    assert 60 <= hi <= 70
    assert result['s_min'] > 0.9
    assert result['v_min'] > 0.9


def test_solid_red_image_does_not_blow_up_across_the_hue_wrap():
    # Pure red (255,0,0) is hue 0 exactly — the wraparound seam itself.
    img = _solid_image((255, 0, 0))
    result = suggest_hsv_thresholds(img)
    lo, hi = result['h']
    # A naive min/max over raw hue would report something like [0, 359] here.
    # The band should stay tight and close to 0 (accounting for wrap), not span
    # most of the circle.
    span = (hi - lo) % 360
    assert span < 20, f'band too wide, wraparound not handled: {result["h"]}'


def test_crop_fraction_ignores_a_different_colored_border():
    size = 40
    img = _solid_image((255, 255, 0), size=size)  # yellow everywhere
    # Paint a thick red border around the edges — should be excluded by the crop.
    img[:5, :] = (255, 0, 0)
    img[-5:, :] = (255, 0, 0)
    img[:, :5] = (255, 0, 0)
    img[:, -5:] = (255, 0, 0)

    result = suggest_hsv_thresholds(img, crop_fraction=0.5)
    lo, hi = result['h']
    # Should still read as yellow (~60), not contaminated by the red border.
    assert 40 <= lo <= 70
    assert 40 <= hi <= 80


def test_returns_expected_keys():
    img = _solid_image((255, 255, 0))
    result = suggest_hsv_thresholds(img)
    assert set(result.keys()) == {'h', 's_min', 'v_min'}
