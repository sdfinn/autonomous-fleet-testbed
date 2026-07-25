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
"""Gazebo ground-truth pose access (sim only).

Why this exists (Session 16): a mission can report PASS while the robot is physically
somewhere else — Nav2's goal checker trusts the AMCL pose estimate, and wheel slip
during an obstacle contact walks the *believed* pose into goal tolerance while the
robot is stuck (observed live 2026-07-15: mission PASS with the robot wedged at the
hallway arch corner, 0.38 m from the goal). In simulation, Gazebo's world pose is
perfect ground truth and free — sim tests must verify against it, not against the
robot's self-belief.

On hosts without Gazebo (the Jetson in HIL) every query returns None; callers that
run in both contexts treat None as "no ground truth available", not as a failure.
The world file spawns the robot at its map-frame pose, so Gazebo world coordinates
ARE map coordinates for this project (sim_only_launch.py spawn == AMCL initial pose).
"""
import re
import subprocess

# Off-sim (HIL Jetson, future real robot) this call can never succeed — every query
# blocks for the full timeout before returning None (confirmed live on the Jetson,
# 2026-07-25: two 8.0s stalls per mission leg, up to 48s/day wasted). Measured on this
# workstation with real Gazebo running locally (the case where the call DOES succeed):
# 5 consecutive calls completed in 0.09-0.11s each. 1.0s keeps ~10x margin over that
# real response time while cutting the off-sim/HIL/real-robot wasted stall 8x (8s -> 1s
# per call).
GZ_POSE_TIMEOUT_S = 1.0


def parse_model_position(pose_text, model):
    """Extract (x, y) of the entry named exactly `model` from `gz topic -e` output.

    The /model/<name>/pose message is a Pose_V holding one entry per link plus one for
    the model itself; link entries carry link-relative offsets, so only the block whose
    name is exactly the model name is the world pose. Returns (x, y) or None.
    """
    # Fields inside a position block may be omitted by protobuf text output when zero.
    pattern = (
        rf'name: "{re.escape(model)}"\s*\n\s*position\s*{{\s*'
        rf'(?:x:\s*(?P<x>[-\d.eE+]+)\s*)?(?:y:\s*(?P<y>[-\d.eE+]+)\s*)?'
    )
    m = re.search(pattern, pose_text)
    if m is None:
        return None
    return float(m.group('x') or 0.0), float(m.group('y') or 0.0)


def get_ground_truth_xy(model='robot_001', timeout=GZ_POSE_TIMEOUT_S):
    """World-frame (x, y) of `model` from the running Gazebo, or None off-sim/on error."""
    try:
        out = subprocess.run(
            ['gz', 'topic', '-e', '-t', f'/model/{model}/pose', '-n', '1'],
            capture_output=True, text=True, timeout=timeout,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None
    return parse_model_position(out.stdout, model)
