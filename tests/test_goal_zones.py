"""Unit tests for tools.goal_zones (CR-12: goal zones derived from mission data,
not hardcoded per-consumer)."""
from tools.goal_zones import end_zones


def test_every_mission_final_goal_has_a_zone():
    zones = end_zones()
    labels = {z['label'] for z in zones}
    # Every mission's final navigate target must be represented (mission1/mission2/
    # go_home all end at home_base — one shared zone) plus the BR-01 nav-test goal.
    assert any('home_base' in lbl for lbl in labels)
    assert any('bedroom_goal' in lbl for lbl in labels)


def test_zone_coordinates_come_from_semantic_map():
    from nav_fleet.semantic_map import SEMANTIC_MAP
    zones = {z['label']: z for z in end_zones()}
    home = next(z for lbl, z in zones.items() if 'home_base' in lbl)
    assert (home['x'], home['y']) == SEMANTIC_MAP['home_base']
    assert home['tol'] > 0
