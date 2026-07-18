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

VALID_ACTIONS = ('navigate', 'take_picture')  # Mission 2 adds reaction supervision atop these
VALID_REACTIONS = ('photo_then_stop', 'photo_then_home')

# Trigger definition A (spec §2): a ball whose apparent range is at or under
# REACTION_RANGE_M[color] for REACTION_FRAMES consecutive detector frames. Values shared
# by mission_runner (counting) and the Mission 2 test harness (placement envelope).
# REACTION_RANGE_M widened 1.0 -> 1.3 during Task 9 live tuning (2026-07-17): the
# harness places a ball ~on the planned route, but Nav2's actual SMAC/RPP path doesn't
# hug that line exactly, so closest-approach range varies run to run. At 1.0 m and the
# detector's ~10 Hz rate, a live run measured only ONE frame in-band during a
# closest-approach of ~0.94 m (a clean, evenly-sampled 10Hz hyperbola confirmed the
# camera-range estimate is accurate, not a sensor artifact) — one frame can't satisfy
# REACTION_FRAMES=3, so the reaction never fired. 1.3 m reproduces >=3 in-band frames
# for a >=0.94 m closest approach (verified against the same failing seed) while still
# leaving >=1.8 m of ignore-variant clearance (REACTION_RANGE_M['red'] + IGNORE_MARGIN)
# versus both clear-floor anchors (simulated 2000 seeds, 0 placement failures).
#
# Converted to a per-color dict in Task 9's final pre-commit batch (2026-07-17, Mike's
# severity model): red keeps the live-tuned 1.3 m (danger — react early, keep distance);
# yellow is 0.8 m (caution — safe to approach closer before retreating). Supervision below
# looks up the threshold by the detected color. The harness derives its judge bands from
# these same values instead of hardcoding a second copy (see BAND_FAR in
# tools/mission2_harness.py).
REACTION_RANGE_M = {'red': 1.3, 'yellow': 0.8}
REACTION_FRAMES = 3


@dataclass(frozen=True)
class MissionStep:
    action: str          # one of VALID_ACTIONS
    label: str           # human-readable step description (logged during execution)
    location: str = None  # SEMANTIC_MAP key — required for 'navigate'
    yaw: float = None    # optional final heading (radians, map frame) for 'navigate'
    reactions: dict = None  # navigate only: detected color -> VALID_REACTIONS entry


MISSIONS = {
    # Mission 1 (Session 15 first HIL milestone): navigate to the bedroom doorway centre
    # facing into the bedroom, photograph it, return to the spawn point.
    'mission1': (
        MissionStep('navigate', 'drive to bedroom doorway centre', 'doorway_center',
                    math.pi / 2),
        MissionStep('take_picture', 'photograph the bedroom'),
        # yaw: return to the start POSE, not just the position — without it the goal
        # defaults to yaw=0 (east) and the robot ends with an arbitrary-looking left
        # turn at the arch (observed eyes-on 2026-07-15). Spawn faces north (pi/2).
        MissionStep('navigate', 'return to start', 'home_base', math.pi / 2),
    ),
    # Mission 2 (Session 16 Plan B): drive toward the green sphere and stop short of it,
    # reacting to croquet balls come across en route (spec §1-2). If a reaction fires,
    # mission_runner.run_mission returns from inside the navigate step (see its
    # `if triggered is not None: return self._execute_reaction(...)`) — the take_picture
    # step below never runs on a reaction leg; it's reached only on the clean/no-ball
    # (nominal) path, mirroring Mission 1's navigate -> take_picture pattern (Task 9
    # rework, 2026-07-17, Mike's deterministic-placement decision).
    'mission2': (
        MissionStep('navigate', 'drive toward the green sphere, watching for balls',
                    'sphere_approach', math.pi / 2,
                    reactions={'red': 'photo_then_stop', 'yellow': 'photo_then_home'}),
        MissionStep('take_picture', 'photograph the green sphere'),
    ),
    # Reset leg (Session 16 HIL rungs, Task 12): drive straight back to home_base. Used
    # between HIL react rungs to return the robot home WITHOUT teleporting (a teleport
    # breaks AMCL + the costmaps). Run via mission_runner, which clears both costmaps
    # before the navigate leg — mirroring the sim tests' `_drive_home_after` janitor
    # (clear costmaps + send_goal(home_base, yaw=pi/2)). yaw=pi/2 restores the spawn/home
    # heading (north), matching what nominal/yellow/red expect at their start.
    'go_home': (
        MissionStep('navigate', 'return to home base', 'home_base', math.pi / 2),
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
        if step.reactions is not None:
            if step.action != 'navigate':
                raise ValueError(f'step {i}: reactions are only valid on navigate steps')
            for color, reaction in step.reactions.items():
                if reaction not in VALID_REACTIONS:
                    raise ValueError(
                        f'step {i}: unknown reaction {reaction!r} for color {color!r}')


def yaw_to_quaternion(yaw):
    """Heading about +Z -> (z, w) quaternion components (x = y = 0 for planar robots)."""
    return math.sin(yaw / 2.0), math.cos(yaw / 2.0)
