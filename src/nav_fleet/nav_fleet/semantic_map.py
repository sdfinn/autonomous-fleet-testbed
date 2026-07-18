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
    # Mission 2 nav goal — where the robot stops and photographs the floor marker. History:
    # (0.0, 3.5) [Task 13 initial] -> (0.0, 3.85) [Task 13e, 2026-07-18: Mike's HIL observation
    # that the robot stopped too SHALLOW, "a lot closer to the wall, well past the dresser"] ->
    # (0.9, 3.70) [Task 13 fix wave, same day: Mike's GUI review relocated the whole
    # stop/marker/ball cluster EAST of the dresser, into the open pocket between the dresser's
    # NE corner and the bed's SW corner]. Each move kept the stop/marker/ball offsets RIGID
    # (marker 0.20 m ahead of the stop in y; ball 0.30 m east of the marker in x), so the
    # 0.36 m ball-to-stop closest-approach the reaction calibration depends on is UNCHANGED
    # across all three positions.
    #
    # Clearances at the current (0.9, 3.70): Bed (center (0.813, 5.436), size 1.524x2.032 ->
    # south face y = 5.436 - 1.016 = 4.420) is 4.420 - 3.70 = 0.72 m north of the stop — 0.18 m
    # past the 0.54 m required (0.30 m global costmap inflation + 0.24 m robot_radius), so the
    # goal is plannable with comfortable margin. Dresser (center (0.0074, 2.7583), size
    # 0.813x0.457 -> NE corner ~(0.4139, 2.987)) is ~1.03 m SW of the stop. Wall_East (pose
    # x=1.625, thickness 0.05 -> near face x=1.600) is 0.70 m east of the stop.
    'sphere_approach': (0.9, 3.70),
}

# Mission 2 floor marker = the human-observability point of interest the robot approaches and
# photographs (Task 13: the raised green sphere became a flat floor disc — the robot navigates
# by AMCL coordinates, the marker is for the eyes in the room). 0.20 m ahead (north) of the
# stop pose (sphere_approach, above) in the same east-of-dresser cluster: 0.52 m south of the
# Bed's south face (y=4.420), ~1.03 m NE of the Dresser's NE corner (~(0.4139, 2.987)), 0.70 m
# west of Wall_East's near face (x=1.600). The Mission 2 ball is placed relative to THIS point
# (tools.mission2_harness.BALL_AT_SPHERE_XY = MARKER + 0.3 m in +x = (1.2, 3.90), which sits
# 0.40 m west of Wall_East's near face), so ball placement moves WITH the marker by
# construction, never tuned independently (spec).
MARKER_XY = (0.9, 3.90)
