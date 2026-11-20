# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""Put a box in the simulated robot's way, and take it out again.

Until 2026-11-20 nothing in the simulator or CI ever stood in the robot's path: the
room's furniture is in the map, so Nav2 plans around it and the obstacle guard never
has anything to do. A box spawned AFTER a leg has started is not in the plan, which
is the situation the guard exists for (the cardboard box of the 2026-11-20 floor test).

    python -m tools.sim_box spawn 0.2 2.6      # box centred at map/world (0.2, 2.6)
    python -m tools.sim_box remove

The box is static (it cannot be pushed) and 0.40 m tall: the simulated lidar's scan
plane is 0.225 m up, the real one 0.18 m.
"""
import argparse
import subprocess
import tempfile

WORLD = 'bedroom'
BOX_NAME = 'path_box'
BOX_SIZE_M = (0.30, 0.30, 0.40)

BOX_SDF = """<?xml version="1.0"?>
<sdf version="1.9">
  <model name="{name}">
    <static>true</static>
    <pose>{x} {y} {z} 0 0 {yaw}</pose>
    <link name="link">
      <collision name="c">
        <geometry><box><size>{sx} {sy} {sz}</size></box></geometry>
      </collision>
      <visual name="v">
        <geometry><box><size>{sx} {sy} {sz}</size></box></geometry>
        <material><ambient>0.6 0.45 0.25 1</ambient><diffuse>0.6 0.45 0.25 1</diffuse></material>
      </visual>
    </link>
  </model>
</sdf>
"""


def box_sdf(x, y, yaw=0.0, size=BOX_SIZE_M, name=BOX_NAME):
    """The SDF text for a box resting on the floor, centred at (x, y)."""
    sx, sy, sz = size
    return BOX_SDF.format(name=name, x=x, y=y, z=sz / 2.0, yaw=yaw, sx=sx, sy=sy, sz=sz)


def _gz_service(srv, reqtype, req):
    out = subprocess.run(
        ['gz', 'service', '-s', srv, '--reqtype', reqtype,
         '--reptype', 'gz.msgs.Boolean', '--timeout', '5000', '--req', req],
        capture_output=True, text=True, timeout=15)
    if out.returncode != 0 or 'data: true' not in out.stdout:
        raise RuntimeError(f'gz service {srv} failed: {out.stdout} {out.stderr}')


def spawn_box(x, y, yaw=0.0, size=BOX_SIZE_M, name=BOX_NAME):
    with tempfile.NamedTemporaryFile('w', suffix='.sdf', delete=False) as f:
        f.write(box_sdf(x, y, yaw, size, name))
        path = f.name
    _gz_service(f'/world/{WORLD}/create', 'gz.msgs.EntityFactory',
                f'sdf_filename: "{path}"')
    return name


def remove_box(name=BOX_NAME):
    _gz_service(f'/world/{WORLD}/remove', 'gz.msgs.Entity',
                f'name: "{name}" type: MODEL')


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = ap.add_subparsers(dest='cmd', required=True)
    sp = sub.add_parser('spawn')
    sp.add_argument('x', type=float)
    sp.add_argument('y', type=float)
    sp.add_argument('--yaw', type=float, default=0.0)
    sub.add_parser('remove')
    args = ap.parse_args(argv)
    if args.cmd == 'spawn':
        print(spawn_box(args.x, args.y, args.yaw))
    else:
        remove_box()


if __name__ == '__main__':
    main()
