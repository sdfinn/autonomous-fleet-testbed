# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""Scenario end-zones for reports/dashboards, derived from mission data (CR-12).

Before this module, generate_test_report.py and dashboard/app.py each hardcoded a
single goal rectangle at the BR-01 goal — wrong for every Mission 2 row (a healthy
Mission 2 run ends at home_base). One derivation, both consumers.
"""
import sys
from pathlib import Path

try:
    from nav_fleet.missions import MISSIONS
    from nav_fleet.semantic_map import SEMANTIC_MAP
except ModuleNotFoundError:  # no colcon overlay (bare runner / plain shell)
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src' / 'nav_fleet'))
    from nav_fleet.missions import MISSIONS
    from nav_fleet.semantic_map import SEMANTIC_MAP

# Nav2 xy_goal_tolerance for nav-test goals; harness HOME_TOL for mission home arrivals.
NAV_GOAL_TOL_M = 0.15
HOME_TOL_M = 0.3


def end_zones():
    """One zone per distinct final navigate target across all missions, plus the BR-01
    nav-test goal. Returns [{'label', 'x', 'y', 'tol'}]."""
    zones = {}
    for name, steps in MISSIONS.items():
        nav_steps = [s for s in steps if s.action == 'navigate']
        if not nav_steps:
            continue
        loc = nav_steps[-1].location
        x, y = SEMANTIC_MAP[loc]
        if loc in zones:
            zones[loc]['label'] += f'/{name}'
        else:
            tol = HOME_TOL_M if loc == 'home_base' else NAV_GOAL_TOL_M
            zones[loc] = {'label': f'{loc} ({name}', 'x': x, 'y': y, 'tol': tol}
    for z in zones.values():
        z['label'] += ')'
    # The BR-01 nav-test goal (tests/test_navigation.py) isn't a mission but logs runs.
    bx, by = SEMANTIC_MAP['bedroom_goal']
    zones.setdefault('bedroom_goal', {
        'label': 'bedroom_goal (BR-01 nav test)', 'x': bx, 'y': by, 'tol': NAV_GOAL_TOL_M})
    return list(zones.values())
