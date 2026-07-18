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
"""Named locations in the bedroom_simple.sdf world (map-frame coordinates).

Pure data — no ROS imports — so it is importable on CI runners without ROS2
(stage-1-quality) and by tools/ scripts. Coordinates match the real measured
bedroom geometry (see worlds/bedroom_simple.sdf model poses). Canonical home
of the map since Session 15; tools/agentic_loop.py imports it from here.
"""

SEMANTIC_MAP = {
    'home_base':      (-1.276, 1.2),      # robot spawn — outer hallway arch
    'hallway_west':   (-2.6435, 1.6740),
    'hallway_east':   (1.2805, 1.6930),
    'bedroom_goal':   (0.0, 3.7),         # BR-01 goal — bedroom floor centre
    'doorway_center': (-0.974, 2.430),    # centre of the ~0.71 m Wall_South_W/E gap
    'dresser':        (0.0074, 2.7583),   # just inside the bedroom doorway
    'desk':           (-0.9590, 5.3240),
    'pc_tower':       (-1.0360, 4.2050),  # obstacle near the desk
    'bed':            (0.8130, 5.4360),
    # Mission 2 nav goal — where the robot stops and photographs the floor marker.
    # Moved (0.0, 3.5) -> (0.0, 3.85) in Task 13e (2026-07-18, Mike's HIL observation: the
    # robot stopped too SHALLOW — "a lot closer to the wall, well past the dresser"). This is
    # a RIGID +0.35 m north move of the whole stop/marker/ball cluster, so the 0.36 m
    # ball-to-stop closest-approach that the reaction calibration depends on is UNCHANGED.
    # (0.0, 3.85) is the DEEPEST plannable stop: the Bed (center (0.813, 5.436), 1.524x2.032
    # box) has its south-west CORNER at (0.051, 4.420); a robot centre at (0.0, 3.85) is
    # 0.572 m from that corner, i.e. 0.332 m of body clearance past the 0.24 m robot_radius —
    # just outside the 0.30 m global inflation band, so the goal is plannable with comfort.
    # Going deeper (y>3.9) pushes the centre inside the bed's inflation and RPP can't settle.
    # Dresser north face y=2.987 -> 0.863 m south clearance; the approach from doorway_center
    # still routes WEST of the dresser's NW corner; Wall_East x=1.600 is >1.5 m east.
    'sphere_approach': (0.0, 3.85),
}

# Mission 2 floor marker = the human-observability point of interest the robot approaches and
# photographs (Task 13: the raised green sphere became a flat floor disc — the robot navigates
# by AMCL coordinates, the marker is for the eyes in the room). Task 13e DECOUPLED it from
# bedroom_goal: bedroom_goal (0.0, 3.7) stays the BR-01 nav anchor (tests/test_navigation.py
# drives there), while the demo marker moved 0.35 m deeper to (0.0, 4.05) — 0.20 m ahead of
# the stop pose (sphere_approach) and 0.37 m short of the bed's south face, "well past the
# dresser" (1.06 m north of its face) and close to the bed/wall for the observer. The Mission
# 2 ball is placed relative to THIS point (tools.mission2_harness.BALL_AT_SPHERE_XY = MARKER +
# 0.3 m in +x = (0.3, 4.05)), so ball placement moves WITH the marker by construction, never
# tuned independently (spec) — and the rigid move keeps the 0.36 m ball-to-stop geometry.
MARKER_XY = (0.0, 4.05)
