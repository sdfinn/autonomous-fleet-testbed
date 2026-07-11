# Copyright 2026 Mike
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Mission definitions: waypoint sequences + action primitives (Session 15, Decision 3).

Missions are data, not scripts — a mission is a tuple of MissionSteps executed in order
by nav_fleet.mission_runner. Pure Python (no ROS imports) so definitions are unit-testable
on CI runners without ROS2.
"""
import math
from dataclasses import dataclass

from nav_fleet.semantic_map import SEMANTIC_MAP

VALID_ACTIONS = ('navigate', 'take_picture')


@dataclass(frozen=True)
class MissionStep:
    action: str          # one of VALID_ACTIONS
    label: str           # human-readable step description (logged during execution)
    location: str = None  # SEMANTIC_MAP key — required for 'navigate'
    yaw: float = None    # optional final heading (radians, map frame) for 'navigate'


MISSIONS = {
    # Mission 1 (Session 15 first HIL milestone): navigate to the bedroom doorway centre
    # facing into the bedroom, photograph it, return to the spawn point.
    'mission1': (
        MissionStep('navigate', 'drive to bedroom doorway centre', 'doorway_center',
                    math.pi / 2),
        MissionStep('take_picture', 'photograph the bedroom'),
        MissionStep('navigate', 'return to start', 'home_base'),
    ),
}


def validate_mission(steps):
    """Raise ValueError if a mission is structurally invalid."""
    if not steps:
        raise ValueError('mission is empty')
    for i, step in enumerate(steps):
        if step.action not in VALID_ACTIONS:
            raise ValueError(f'step {i}: unknown action {step.action!r}')
        if step.action == 'navigate' and step.location not in SEMANTIC_MAP:
            raise ValueError(f'step {i}: location {step.location!r} not in SEMANTIC_MAP')


def yaw_to_quaternion(yaw):
    """Heading about +Z -> (z, w) quaternion components (x = y = 0 for planar robots)."""
    return math.sin(yaw / 2.0), math.cos(yaw / 2.0)
