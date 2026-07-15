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
"""Unit tests for the Gazebo ground-truth pose parser. Pure Python — no ROS2/Gazebo
needed, so this runs in stage-1-quality."""
from nav_fleet.ground_truth import parse_model_position

# Trimmed from a real `gz topic -e -t /model/robot_001/pose -n 1` capture (2026-07-15):
# link entries (model-relative offsets) precede the model entry (world pose).
SAMPLE = '''pose {
  name: "rear_right_wheel"
  position {
    x: -0.10000000000000031
    y: -0.14000000000000012
    z: 0.050000000000000017
  }
  orientation {
    w: 1
  }
}
pose {
  name: "robot_001"
  position {
    x: -0.89957772374958311
    y: 1.129427621170358
    z: 6.600341316867314e-08
  }
  orientation {
    x: -3.7141950849349139e-09
    w: 1
  }
}
'''


def test_parses_model_entry_not_link_entry():
    """The wheel link's block comes first; the parser must return the model's world pose."""
    assert parse_model_position(SAMPLE, 'robot_001') == (
        -0.89957772374958311, 1.129427621170358)


def test_missing_model_returns_none():
    assert parse_model_position(SAMPLE, 'robot_999') is None


def test_zero_fields_omitted_by_protobuf_text():
    """protobuf text output omits zero-valued fields — x/y may be absent entirely."""
    text = 'pose {\n  name: "robot_001"\n  position {\n    z: 0.05\n  }\n}\n'
    assert parse_model_position(text, 'robot_001') == (0.0, 0.0)
