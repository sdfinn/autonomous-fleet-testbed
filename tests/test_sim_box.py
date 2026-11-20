# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""tools/sim_box.py: the box model itself and the Gazebo requests (no Gazebo needed)."""
import xml.etree.ElementTree as ET
from unittest.mock import patch

from tools import sim_box


def test_the_box_rests_on_the_floor_and_reaches_above_both_lidars():
    root = ET.fromstring(sim_box.box_sdf(0.2, 2.6))
    x, y, z = (float(v) for v in root.find('model/pose').text.split()[:3])
    sx, sy, sz = (float(v) for v in root.find('model/link/collision/geometry/box/size').text.split())
    assert (x, y) == (0.2, 2.6)
    assert z - sz / 2.0 == 0.0                    # bottom face on the floor
    assert z + sz / 2.0 > 0.225                   # above the sim scan plane (real: 0.18)


def test_the_box_cannot_be_pushed_and_the_lidar_can_see_it():
    root = ET.fromstring(sim_box.box_sdf(0.0, 0.0))
    assert root.find('model/static').text == 'true'
    # The GPU lidar ray-casts against VISUALS (see urdf/ugv_pt.urdf.xacro's camera note).
    assert root.find('model/link/visual/geometry/box') is not None
    assert root.find('model/link/collision/geometry/box') is not None


def test_spawn_and_remove_ask_gazebo_for_the_right_things():
    with patch('tools.sim_box._gz_service') as gz:
        name = sim_box.spawn_box(0.2, 2.6)
        sim_box.remove_box()
    (create, remove) = gz.call_args_list
    assert create.args[0] == '/world/bedroom/create' and 'sdf_filename' in create.args[2]
    assert remove.args[0] == '/world/bedroom/remove' and f'name: "{name}"' in remove.args[2]
