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
    # Moved (0.0, 3.2) -> (0.0, 3.5) in Task 13 (2026-07-18) to clear the dresser squeeze:
    # the Dresser's north face is y=2.987 (center 2.7583 + 0.457/2), so the old (0.0, 3.2)
    # left only 0.213 m of center-to-face clearance — LESS than the robot_radius 0.24 m
    # (nav2_params.yaml), i.e. the robot body overlapped the dresser's inflated footprint at
    # the stop pose. (0.0, 3.5) gives 0.513 m center clearance (0.273 m past the wheel edge);
    # the approach path from doorway_center now passes WEST of the dresser's NW corner
    # instead of clipping it. Bed south face y=4.420 -> 0.920 m north clearance; Wall_West
    # x=-1.473 and Wall_East x=1.600 are >1.5 m away. The floor marker (MARKER_XY below,
    # bedroom_goal) sits 0.2 m ahead at the clear-zone center — the robot stops just short.
    'sphere_approach': (0.0, 3.5),
}

# Mission 2 floor marker = the human-observability point of interest the robot approaches
# and photographs (Task 13: the raised green sphere became a flat floor disc — the robot
# navigates by AMCL coordinates, the marker is for the eyes in the room). It coincides with
# bedroom_goal (0.0, 3.7), the BR-01 anchor at the clear-zone CENTRE between the dresser
# (north face y=2.987) and the bed (south face y=4.420) — already optimally placed, so it
# stays put while the APPROACH moved north to clear the squeeze. The Mission 2 ball is
# placed relative to THIS point (tools.mission2_harness.BALL_AT_SPHERE_XY), so ball
# placement moves with the marker by construction, never tuned independently (spec).
MARKER_XY = SEMANTIC_MAP['bedroom_goal']
