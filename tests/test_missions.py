"""Unit tests for the mission framework — pure Python, no ROS2 required (runs in stage-1)."""


def test_semantic_map_has_doorway_center():
    from nav_fleet.semantic_map import SEMANTIC_MAP
    # Doorway = gap between Wall_South_W and Wall_South_E in bedroom_simple.sdf
    assert SEMANTIC_MAP['doorway_center'] == (-0.974, 2.430)


def test_semantic_map_keeps_existing_locations():
    from nav_fleet.semantic_map import SEMANTIC_MAP
    assert SEMANTIC_MAP['home_base'] == (-1.276, 1.2)
    assert SEMANTIC_MAP['bedroom_goal'] == (0.0, 3.7)
    assert len(SEMANTIC_MAP) == 9  # 8 original + doorway_center
