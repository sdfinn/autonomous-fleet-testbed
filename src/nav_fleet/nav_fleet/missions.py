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
# REACTION_RANGE_M[color] for long enough (ReactionRule, below). Values shared
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
# The reaction rule is in SECONDS, not detector messages (2026-11-23). It used to be "3
# messages in a row", and how long that is depended on how fast the detector happened to
# run: 0.2 s from the first to the third at the simulator's 10 a second, 0.4 s at the
# real robot's 5, and 0.55 s at the 3.6 a second of the first real detector, where on
# 2026-11-20 the yellow ball was in range for two messages and the robot arrived before
# the third. A ball must now stay in range for REACTION_HOLD_S of picture time, seen in
# at least REACTION_MIN_DETECTIONS messages, with no gap longer than REACTION_MAX_GAP_S.
REACTION_HOLD_S = 0.3
REACTION_MIN_DETECTIONS = 2
REACTION_MAX_GAP_S = 0.6


class ReactionRule:
    """Which watched color, if any, has been in range long enough. One instance per
    reactive leg; feed it every detector message with the picture's time stamp."""

    def __init__(self, hold_s=REACTION_HOLD_S, min_detections=REACTION_MIN_DETECTIONS,
                 max_gap_s=REACTION_MAX_GAP_S):
        self.hold_s, self.min_detections, self.max_gap_s = hold_s, min_detections, max_gap_s
        self._since = {}       # color -> stamp of the first message of its current run
        self._last = {}        # color -> stamp of its latest in-range message
        self._count = {}       # color -> messages in its current run

    def update(self, in_range, watched, stamp_s):
        """One detector message: `in_range` is the set of colors in range in it, `watched`
        the colors this leg reacts to. Returns the color whose rule is met, or None. A
        message without the color ends its run, and so does a gap in the messages."""
        fired = None
        for color in watched:
            if color not in in_range:
                self._since.pop(color, None)
                self._count.pop(color, None)
                self._last.pop(color, None)
                continue
            if color in self._last and stamp_s - self._last[color] > self.max_gap_s:
                self._since.pop(color, None)           # the detector went quiet: start again
                self._count.pop(color, None)
            self._since.setdefault(color, stamp_s)
            self._last[color] = stamp_s
            self._count[color] = self._count.get(color, 0) + 1
            if (fired is None and self._count[color] >= self.min_detections
                    and stamp_s - self._since[color] >= self.hold_s - 1e-3):   # stamps are floats
                fired = color
        return fired


@dataclass(frozen=True)
class MissionStep:
    action: str          # one of VALID_ACTIONS
    label: str           # human-readable step description (logged during execution)
    location: str = None  # SEMANTIC_MAP key — required for 'navigate'
    yaw: float = None    # optional final heading (radians, map frame) for 'navigate'
    reactions: dict = None  # navigate only: detected color -> VALID_REACTIONS entry
    # take_picture only: stable semantic tag for the saved PNG (`{mission}_{photo_tag}`).
    # Lets a waypoint's photo be found by MEANING (home_ref / marker / home_arrival) rather
    # than by a fragile step index — the return-fidelity pair check (Task 13, Option B) pairs
    # the `home_ref` and `home_arrival` photos regardless of where they land in the sequence
    # (no_ball takes home_arrival as step 5; yellow's reaction takes it mid-mission). When
    # absent, the runner falls back to the `{mission}_step{i}` label (Mission 1 unchanged).
    photo_tag: str = None


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
    # Mission 2 (Session 16 Plan B, Task 13 Option B — Mike, 2026-07-18): ONE mission =
    # a verified round trip. Each waypoint carries its own verification (a checklist);
    # the mission verdict IS the checklist. The red/yellow/no-ball variants are the SAME
    # mission under different WORLD STATES — a reaction legitimately SHORTENS the path,
    # and the shortened path is judged against its own expected waypoints. (R3 lineage:
    # this hand-built five-waypoint sequence is the concrete precursor to the
    # input-ised / DSL-driven missions R3 will generalise — deliberately NOT a generalised
    # verification DSL here; Mission 2's four concrete checks only: photo, photo-match,
    # position, reaction.)
    #
    # Sequence (Option B): the mission OWNS its return home and takes THREE photos —
    #   1. home reference photo BEFORE any movement (return-fidelity anchor: spawn pose,
    #      facing north/pi_2, doorway just to the right);
    #   2. navigate to the floor marker (reactions armed — red photo_then_stop,
    #      yellow photo_then_home);
    #   3. marker photo;
    #   4. navigate HOME (the robot always drives itself home — no external reset leg);
    #   5. home arrival photo — must MATCH photo 1 (see the return-fidelity pair check in
    #      tools/mission2_harness.judge_home_pair).
    # Variant endings (same mission, different world state):
    #   no_ball (no ball) — all 5 steps; pair-check photo 1 vs photo 5.
    #   yellow — reaction interrupts step 2 -> reaction photo -> self-return home ->
    #     home arrival photo (photo_then_home now takes the arrival photo too, so the pair
    #     check applies to yellow); steps 3 is skipped, 4/5 are folded into the reaction.
    #   red — reaction interrupts step 2 -> reaction photo -> STOPS; steps 3-5 never run,
    #     no second home photo. PASS for no_ball/yellow requires the whole round trip.
    # A fired reaction short-circuits run_mission from inside the navigate step (see
    # mission_runner.run_mission `if triggered is not None: return self._execute_reaction`).
    'mission2': (
        MissionStep('take_picture', 'reference photo at home (return-fidelity anchor)',
                    photo_tag='home_ref'),
        MissionStep('navigate', 'drive toward the floor marker, watching for balls',
                    'sphere_approach', math.pi / 2,
                    reactions={'red': 'photo_then_stop', 'yellow': 'photo_then_home'}),
        MissionStep('take_picture', 'photograph the floor marker', photo_tag='marker'),
        MissionStep('navigate', 'return home', 'home_base', math.pi / 2),
        MissionStep('take_picture', 'arrival photo at home (must match the reference)',
                    photo_tag='home_arrival'),
    ),
    # Reset leg (Session 16 HIL rungs, Task 12): drive straight back to home_base. Used
    # between HIL react rungs to return the robot home WITHOUT teleporting (a teleport
    # breaks AMCL + the costmaps). Run via mission_runner, which clears both costmaps
    # before the navigate leg — mirroring the sim tests' `_drive_home_after` janitor
    # (clear costmaps + send_goal(home_base, yaw=pi/2)). yaw=pi/2 restores the spawn/home
    # heading (north), matching what no_ball/yellow/red expect at their start.
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
