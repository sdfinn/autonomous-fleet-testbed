"""Unit tests for the mission framework — pure Python, no ROS2 required (runs in stage-1)."""
import math
import types

import pytest


def test_semantic_map_has_doorway_center():
    from nav_fleet.semantic_map import SEMANTIC_MAP
    # Doorway = gap between Wall_South_W and Wall_South_E in bedroom_simple.sdf
    assert SEMANTIC_MAP['doorway_center'] == (-0.974, 2.430)


def test_semantic_map_keeps_existing_locations():
    from nav_fleet.semantic_map import SEMANTIC_MAP
    assert SEMANTIC_MAP['home_base'] == (-1.276, 1.2)
    assert SEMANTIC_MAP['bedroom_goal'] == (0.0, 3.7)
    assert len(SEMANTIC_MAP) == 10  # 9 as of Session 15 + sphere_approach (Mission 2)


def test_mission1_shape():
    from nav_fleet.missions import MISSIONS
    steps = MISSIONS['mission1']
    assert [s.action for s in steps] == ['navigate', 'take_picture', 'navigate']
    assert steps[0].location == 'doorway_center'
    assert steps[0].yaw == pytest.approx(math.pi / 2)  # face north, into the bedroom
    assert steps[-1].location == 'home_base'


def test_all_defined_missions_are_valid():
    from nav_fleet.missions import MISSIONS, validate_mission
    for steps in MISSIONS.values():
        validate_mission(steps)  # must not raise


def test_validate_rejects_unknown_action():
    from nav_fleet.missions import MissionStep, validate_mission
    with pytest.raises(ValueError, match='unknown action'):
        validate_mission((MissionStep('teleport', 'zap'),))


def test_validate_rejects_unknown_location():
    from nav_fleet.missions import MissionStep, validate_mission
    with pytest.raises(ValueError, match='not in SEMANTIC_MAP'):
        validate_mission((MissionStep('navigate', 'go', 'narnia'),))


def test_validate_rejects_empty_mission():
    from nav_fleet.missions import validate_mission
    with pytest.raises(ValueError, match='empty'):
        validate_mission(())


def test_yaw_to_quaternion():
    from nav_fleet.missions import yaw_to_quaternion
    assert yaw_to_quaternion(0.0) == pytest.approx((0.0, 1.0))
    z, w = yaw_to_quaternion(math.pi / 2)
    assert (z, w) == pytest.approx((0.7071, 0.7071), abs=1e-4)


def _fake_image_msg(encoding='rgb8', step=None):
    """2x2 image: (red, green) / (blue, white) in the named channel order."""
    row0 = bytes([255, 0, 0, 0, 255, 0])
    row1 = bytes([0, 0, 255, 255, 255, 255])
    step = step or 6
    pad = bytes(step - 6)
    return types.SimpleNamespace(
        height=2, width=2, step=step, encoding=encoding, data=row0 + pad + row1 + pad,
    )


def test_image_msg_to_png_rgb8(tmp_path):
    from PIL import Image
    from nav_fleet.image_io import image_msg_to_png
    out = tmp_path / 'shot.png'
    image_msg_to_png(_fake_image_msg('rgb8'), str(out))
    img = Image.open(out)
    assert img.size == (2, 2)
    assert img.getpixel((0, 0)) == (255, 0, 0)
    assert img.getpixel((1, 1)) == (255, 255, 255)


def test_image_msg_to_png_bgr8_swaps_channels(tmp_path):
    from PIL import Image
    from nav_fleet.image_io import image_msg_to_png
    out = tmp_path / 'shot.png'
    image_msg_to_png(_fake_image_msg('bgr8'), str(out))
    # bytes (255,0,0) read as BGR = pure blue -> stored RGB (0,0,255)
    assert Image.open(out).getpixel((0, 0)) == (0, 0, 255)


def test_image_msg_to_png_handles_row_padding(tmp_path):
    from PIL import Image
    from nav_fleet.image_io import image_msg_to_png
    out = tmp_path / 'shot.png'
    image_msg_to_png(_fake_image_msg('rgb8', step=8), str(out))
    assert Image.open(out).getpixel((1, 1)) == (255, 255, 255)


def test_image_msg_to_png_rejects_unknown_encoding(tmp_path):
    from nav_fleet.image_io import image_msg_to_png
    with pytest.raises(ValueError, match='mono16'):
        image_msg_to_png(_fake_image_msg('mono16'), str(tmp_path / 'x.png'))


def test_semantic_map_has_sphere_approach():
    from nav_fleet.semantic_map import MARKER_XY, SEMANTIC_MAP
    # 2026-07-18 GUI review (Mike): marker EAST of the dresser toward the far wall — the
    # pocket between dresser NE and bed SW. Stop (0.9, 3.70), marker (0.9, 3.90); ball moves
    # with it by construction (BALL_AT_SPHERE_XY = MARKER + 0.3x). bedroom_goal (BR-01) stays.
    assert SEMANTIC_MAP['sphere_approach'] == (0.9, 3.70)
    assert MARKER_XY == (0.9, 3.90)


def test_mission2_shape():
    import math
    from nav_fleet.missions import MISSIONS
    steps = MISSIONS['mission2']
    # Task 13 Option B (2026-07-18): ONE mission = a verified round trip with THREE photos.
    # home_ref (before moving) -> navigate to marker (reactions armed) -> marker photo ->
    # navigate home -> home_arrival photo (pairs with home_ref for the return-fidelity
    # check). A fired reaction short-circuits run_mission from inside the navigate step,
    # so the no_ball path is the only one that runs all five waypoints.
    assert [s.action for s in steps] == [
        'take_picture', 'navigate', 'take_picture', 'navigate', 'take_picture']
    assert [s.photo_tag for s in steps if s.action == 'take_picture'] == [
        'home_ref', 'marker', 'home_arrival']
    navs = [s for s in steps if s.action == 'navigate']
    assert navs[0].location == 'sphere_approach'
    assert navs[0].yaw == pytest.approx(math.pi / 2)  # face north, toward the marker
    assert navs[0].reactions == {'red': 'photo_then_stop', 'yellow': 'photo_then_home'}
    assert navs[1].location == 'home_base'            # the mission owns its return leg
    assert navs[1].yaw == pytest.approx(math.pi / 2)  # restore spawn heading (north)


def test_validate_rejects_unknown_reaction():
    from nav_fleet.missions import MissionStep, validate_mission
    with pytest.raises(ValueError, match='unknown reaction'):
        validate_mission((MissionStep('navigate', 'go', 'bedroom_goal',
                                      reactions={'red': 'explode'}),))


def test_validate_rejects_reactions_on_take_picture():
    from nav_fleet.missions import MissionStep, validate_mission
    with pytest.raises(ValueError, match='navigate steps'):
        validate_mission((MissionStep('take_picture', 'snap',
                                      reactions={'red': 'photo_then_stop'}),))


def test_validate_rejects_navigate_without_location():
    from nav_fleet.missions import MissionStep, validate_mission
    with pytest.raises(ValueError, match='not in SEMANTIC_MAP'):
        validate_mission((MissionStep('navigate', 'go nowhere'),))


def test_reaction_range_is_per_color():
    """Task 9 final batch (2026-07-17, Mike's severity model): red keeps the live-tuned
    1.3 m (danger — react early); yellow is 0.8 m (caution — approach closer first)."""
    from nav_fleet.missions import MISSIONS, REACTION_RANGE_M
    assert REACTION_RANGE_M == {'red': 1.3, 'yellow': 0.8}
    # Every color mission2 declares a reaction for must have a threshold —
    # mission_runner._detection_cb indexes this dict directly (KeyError = config bug).
    reactions = next(s.reactions for s in MISSIONS['mission2'] if s.reactions)
    for color in reactions:
        assert color in REACTION_RANGE_M


# --- The reaction rule is in seconds, not detector messages (2026-11-23) ---
def _feed(rule, rate_hz, seconds, color='yellow', start=0.0):
    """Messages with `color` in range, `rate_hz` a second, for `seconds`. Returns the
    time of the message that met the rule, or None."""
    from nav_fleet.missions import ReactionRule  # noqa: F401  (documents what `rule` is)
    n = int(round(seconds * rate_hz)) + 1
    for i in range(n):
        t = start + i / rate_hz
        if rule.update({color}, {color: 'photo_then_home'}, t) == color:
            return t
    return None


@pytest.mark.parametrize('rate_hz', [10.0, 5.0, 3.6])
def test_a_ball_in_range_fires_after_the_same_time_at_any_detector_rate(rate_hz):
    """"Three messages in a row" was 0.2 s at 10 a second and 0.55 s at 3.6: on
    2026-11-20 the yellow ball was in range for two messages at 3.6 a second and the
    robot arrived before the third."""
    from nav_fleet.missions import REACTION_HOLD_S, ReactionRule
    fired_at = _feed(ReactionRule(), rate_hz, 2.0)
    assert fired_at is not None
    assert REACTION_HOLD_S <= fired_at <= REACTION_HOLD_S + 1.0 / rate_hz + 1e-9


def test_one_message_never_fires_however_long_ago_it_was():
    from nav_fleet.missions import ReactionRule
    rule = ReactionRule()
    assert rule.update({'red'}, {'red': 'x'}, 0.0) is None
    # the same ball seen again much later is a NEW sighting, not a long one
    assert rule.update({'red'}, {'red': 'x'}, 5.0) is None


def test_a_message_without_the_ball_starts_the_time_again():
    from nav_fleet.missions import ReactionRule
    rule, watched = ReactionRule(), {'red': 'x'}
    assert rule.update({'red'}, watched, 0.0) is None
    assert rule.update({'red'}, watched, 0.2) is None
    assert rule.update(set(), watched, 0.3) is None            # glimpse lost
    assert rule.update({'red'}, watched, 0.4) is None
    assert rule.update({'red'}, watched, 0.6) is None          # only 0.2 s since 0.4
    assert rule.update({'red'}, watched, 0.7) == 'red'


def test_only_a_watched_color_can_fire():
    from nav_fleet.missions import ReactionRule
    rule = ReactionRule()
    for i in range(10):
        assert rule.update({'yellow'}, {'red': 'x'}, i * 0.1) is None
