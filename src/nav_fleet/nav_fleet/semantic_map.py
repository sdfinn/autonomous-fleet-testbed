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
}
