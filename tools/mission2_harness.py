"""Mission 2 test harness — seeded ball placement, Gazebo spawn, ground-truth judging.

HARNESS-ONLY code (spec §5): the judge, not the contestant. Robot code must never import
this module or learn ball positions from it. Placement is seeded-random and deterministic
per seed; CI draws a fresh seed per run and logs it (telemetry `seed` column), so any
failure reproduces exactly.

Run as a CLI from the repo root for the HIL tier (python -m tools.mission2_harness ...);
the sim tier (tests/test_mission2.py) calls the functions in-process.
"""
import argparse
import json
import math
import os
import random
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'nav_fleet'))

from nav_fleet.missions import REACTION_RANGE_M  # noqa: E402
from nav_fleet.semantic_map import SEMANTIC_MAP  # noqa: E402
from tools.telemetry_logger import log_run  # noqa: E402

WORLD = 'bedroom'
BALL_RADIUS = 0.043           # 86 mm croquet ball (spec §6) — never inflate
IGNORE_MARGIN = 0.5           # ignorable = never within REACTION_RANGE_M + this of route
BAND_NEAR, BAND_FAR = 0.3, 1.3     # reaction band vs ball truth (spec §3)
HOME_TOL = 0.3                     # yellow: final pose vs home_base
SPHERE_NEAR, SPHERE_FAR = 0.25, 0.75  # ignore: final pose vs the green sphere
STATIONARY_TOL = 0.05              # red: max drift between two truth samples

# Camera-only ball, mirroring the goal_marker pattern: no collision geometry, so the
# reaction (not physics) is what the test measures; static so it can't roll.
BALL_SDF = """<?xml version="1.0"?>
<sdf version="1.9">
  <model name="{name}">
    <static>true</static>
    <pose>{x} {y} {z} 0 0 0</pose>
    <link name="link">
      <visual name="v">
        <geometry><sphere><radius>{r}</radius></sphere></geometry>
        <material><ambient>{rgba}</ambient><diffuse>{rgba}</diffuse></material>
      </visual>
    </link>
  </model>
</sdf>
"""
BALL_RGBA = {'red': '0.9 0.05 0.05 1', 'yellow': '0.9 0.9 0.05 1'}


def _route_points(step=0.05):
    """The planned-route corridor, sampled: home -> doorway -> sphere approach."""
    waypoints = [SEMANTIC_MAP['home_base'], SEMANTIC_MAP['doorway_center'],
                 SEMANTIC_MAP['sphere_approach']]
    pts = []
    for (ax, ay), (bx, by) in zip(waypoints, waypoints[1:]):
        n = max(1, int(math.hypot(bx - ax, by - ay) / step))
        pts.extend((ax + t / n * (bx - ax), ay + t / n * (by - ay)) for t in range(n + 1))
    return pts


def solve_placement(variant, seed):
    """Deterministic seeded placement. 'react': on the doorway->sphere_approach segment
    (mid-leg, small lateral offset). 'ignore': clear-floor anchor + jitter, verified
    outside the reaction envelope of every sampled route point."""
    rng = random.Random(seed)
    if variant == 'react':
        (ax, ay), (bx, by) = (SEMANTIC_MAP['doorway_center'],
                              SEMANTIC_MAP['sphere_approach'])
        t = rng.uniform(0.35, 0.75)
        dx, dy = bx - ax, by - ay
        norm = math.hypot(dx, dy)
        off = rng.uniform(-0.15, 0.15)
        return (ax + t * dx - dy / norm * off, ay + t * dy + dx / norm * off)
    if variant == 'ignore':
        # Clear floor per the world map: by the bed / hallway east. Visible-but-far
        # placements are deliberately possible — correctly ignoring them is the test.
        anchors = ((0.9, 5.2), (1.3, 1.7))
        route = _route_points()
        for _ in range(100):
            axx, ayy = anchors[rng.randrange(len(anchors))]
            x = axx + rng.uniform(-0.2, 0.2)
            y = ayy + rng.uniform(-0.2, 0.2)
            if all(math.hypot(x - rx, y - ry) >= REACTION_RANGE_M + IGNORE_MARGIN
                   for rx, ry in route):
                return (x, y)
        raise RuntimeError(f'no ignorable placement found for seed {seed}')
    raise ValueError(f'unknown variant {variant!r}')


def spawn_ball(color, x, y):
    """Spawn a camera-only croquet ball into the running Gazebo. Returns model name."""
    name = f'ball_{color}'
    sdf = BALL_SDF.format(name=name, x=x, y=y, z=BALL_RADIUS, r=BALL_RADIUS,
                          rgba=BALL_RGBA[color])
    with tempfile.NamedTemporaryFile('w', suffix='.sdf', delete=False) as f:
        f.write(sdf)
        path = f.name
    _gz_service(f'/world/{WORLD}/create', 'gz.msgs.EntityFactory',
                f'sdf_filename: "{path}"')
    return name


def remove_ball(name):
    _gz_service(f'/world/{WORLD}/remove', 'gz.msgs.Entity',
                f'name: "{name}" type: MODEL')


def _gz_service(srv, reqtype, req):
    out = subprocess.run(
        ['gz', 'service', '-s', srv, '--reqtype', reqtype,
         '--reptype', 'gz.msgs.Boolean', '--timeout', '5000', '--req', req],
        capture_output=True, text=True, timeout=15)
    if out.returncode != 0 or 'data: true' not in out.stdout:
        raise RuntimeError(f'gz service {srv} failed: {out.stdout} {out.stderr}')


def _dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def judge_red(ball_xy, events, photo_paths, truth_a, truth_b):
    """PASS = red event fired in-band + photo exists + robot stationary (spec §3)."""
    fails = []
    red = [e for e in events if e['color'] == 'red']
    if not red:
        fails.append('no red reaction event fired')
    elif red[0]['truth_xy'] is None:
        fails.append('reaction event carries no ground truth (sim only check)')
    elif not BAND_NEAR <= _dist(red[0]['truth_xy'], ball_xy) <= BAND_FAR:
        fails.append(f"reaction point {red[0]['truth_xy']} outside band "
                     f'[{BAND_NEAR}, {BAND_FAR}] m of ball {ball_xy}')
    if not photo_paths:
        fails.append('no reaction photo saved')
    if truth_a is None or truth_b is None:
        fails.append('no ground truth for stationary check')
    elif _dist(truth_a, truth_b) > STATIONARY_TOL:
        fails.append(f'robot not stationary: moved {_dist(truth_a, truth_b):.3f} m')
    elif not BAND_NEAR <= _dist(truth_b, ball_xy) <= BAND_FAR:
        fails.append(f'final pose {truth_b} outside band of ball {ball_xy}')
    return fails


def judge_yellow(ball_xy, events, photo_paths, final_truth):
    """PASS = yellow event in-band + photo + physically home (spec §3)."""
    fails = []
    yellow = [e for e in events if e['color'] == 'yellow']
    if not yellow:
        fails.append('no yellow reaction event fired')
    elif yellow[0]['truth_xy'] is None:
        fails.append('reaction event carries no ground truth (sim only check)')
    elif not BAND_NEAR <= _dist(yellow[0]['truth_xy'], ball_xy) <= BAND_FAR:
        fails.append(f"reaction point {yellow[0]['truth_xy']} outside band of {ball_xy}")
    if not photo_paths:
        fails.append('no reaction photo saved')
    if final_truth is None:
        fails.append('no ground truth for home check')
    elif _dist(final_truth, SEMANTIC_MAP['home_base']) > HOME_TOL:
        fails.append(f'not home: {final_truth} is '
                     f"{_dist(final_truth, SEMANTIC_MAP['home_base']):.2f} m from home")
    return fails


def judge_ignore(events, final_truth):
    """PASS = zero reactions + nominal stop-short of the green sphere (spec §3)."""
    fails = []
    if events:
        fails.append(f'spurious reaction(s): {events}')
    sphere = SEMANTIC_MAP['bedroom_goal']
    if final_truth is None:
        fails.append('no ground truth for sphere check')
    elif not SPHERE_NEAR <= _dist(final_truth, sphere) <= SPHERE_FAR:
        fails.append(f'final pose {final_truth} outside sphere band '
                     f'[{SPHERE_NEAR}, {SPHERE_FAR}] m of {sphere}')
    return fails


def log_variant_row(variant, seed, ok, runner=None):
    """One telemetry row per judged variant run — the row's result is the JUDGED verdict
    (ground-truth honest), which may be stricter than the mission's self-report."""
    nav = getattr(runner, 'nav', None)
    log_run(
        scenario=f'mission2_{variant}',
        steps=1,
        final_x=getattr(nav, 'last_final_x', None) or 0.0,
        final_y=getattr(nav, 'last_final_y', None) or 0.0,
        result='PASS' if ok else 'FAIL',
        step_log=[],
        robot_id=os.environ.get('ROBOT_ID', 'robot_001'),
        robot_type='jetson_ugv_pt',
        runner_type=os.environ.get('RUNNER_TYPE', 'local'),
        sim_engine=os.environ.get('SIM_ENGINE', 'gazebo'),
        nav_success_rate=1.0 if ok else 0.0,
        power_mode=os.environ.get('POWER_MODE'),
        seed=seed,
    )


def main():
    parser = argparse.ArgumentParser(description='Mission 2 harness CLI (HIL tier).')
    sub = parser.add_subparsers(dest='cmd', required=True)
    p_spawn = sub.add_parser('spawn', help='solve placement for seed + spawn the ball; '
                                           'prints JSON {name, x, y}')
    p_spawn.add_argument('--variant', choices=['react', 'ignore'], required=True)
    p_spawn.add_argument('--color', choices=['red', 'yellow'], required=True)
    p_spawn.add_argument('--seed', type=int, required=True)
    p_rm = sub.add_parser('remove', help='remove a spawned ball by model name')
    p_rm.add_argument('name')
    p_judge = sub.add_parser('judge-ignore', help='judge an ignore-variant HIL run: '
                                                  'greps the mission log for reactions, '
                                                  'checks ground truth, exits nonzero on '
                                                  'failure')
    p_judge.add_argument('--mission-log', required=True)
    p_judge.add_argument('--seed', type=int, required=True)
    args = parser.parse_args()

    if args.cmd == 'spawn':
        x, y = solve_placement(args.variant, args.seed)
        name = spawn_ball(args.color, x, y)
        print(json.dumps({'name': name, 'x': x, 'y': y}))
    elif args.cmd == 'remove':
        remove_ball(args.name)
    elif args.cmd == 'judge-ignore':
        from nav_fleet.ground_truth import get_ground_truth_xy
        with open(args.mission_log) as f:
            log_text = f.read()
        events = [{'color': line.split()[1], 'reaction': line.split()[3],
                   'truth_xy': None}
                  for line in log_text.splitlines()
                  if line.strip().startswith('reaction: ')]
        fails = judge_ignore(events, get_ground_truth_xy())
        for fail in fails:
            print(f'JUDGE FAIL: {fail}')
        print(f'mission2_ignore seed={args.seed}: {"PASS" if not fails else "FAIL"}')
        raise SystemExit(0 if not fails else 1)


if __name__ == '__main__':
    main()
