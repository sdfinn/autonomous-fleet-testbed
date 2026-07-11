"""Unit tests for the mission framework — pure Python, no ROS2 required (runs in stage-1)."""
import math

import pytest


def test_semantic_map_has_doorway_center():
    from nav_fleet.semantic_map import SEMANTIC_MAP
    # Doorway = gap between Wall_South_W and Wall_South_E in bedroom_simple.sdf
    assert SEMANTIC_MAP['doorway_center'] == (-0.974, 2.430)


def test_semantic_map_keeps_existing_locations():
    from nav_fleet.semantic_map import SEMANTIC_MAP
    assert SEMANTIC_MAP['home_base'] == (-1.276, 1.2)
    assert SEMANTIC_MAP['bedroom_goal'] == (0.0, 3.7)
    assert len(SEMANTIC_MAP) == 9  # 8 original + doorway_center


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
