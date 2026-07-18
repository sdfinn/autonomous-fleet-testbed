"""Mission 2 test harness — ball placement, Gazebo spawn, ground-truth judging.

HARNESS-ONLY code (spec §5): the judge, not the contestant. Robot code must never import
this module or learn ball positions from it.

Placement (Task 9 rework, 2026-07-17 — Mike's explicit decision): tests/test_mission2.py
now uses the DETERMINISTIC BALL_AT_SPHERE_XY spot below, not seeded random placement.
Seeded fuzzing (`solve_placement` + the seed machinery, still below/unused by the live
tests) is deferred to a later session, constrained to an "area of interest" sampling
region rather than the free-roam corridor/anchor sampling here.

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

# Deterministic placement (Task 9 rework, 2026-07-17 — Mike's decision, supersedes seeded
# placement for the live tests below): 0.3 m in +x beside the green sphere/goal_marker at
# (0.0, 3.7) in worlds/bedroom_simple.sdf. Verified clear of every static footprint in that
# SDF: goal_marker itself (0.0381 m radius sphere — 0.3 m center distance clears
# BALL_RADIUS + sphere radius with room to spare, and satisfies the >=0.25 m spec floor),
# Dresser (center (0.0074, 2.7583), 0.813x0.457 box -> y in [2.530, 2.987], well south of
# y=3.7), Bed (center (0.8130, 5.4360), 1.524x2.032 box -> y in [4.420, 6.452], well north
# of y=3.7), and Wall_East (x in [1.600, 1.650], far from x=0.3).
#
# Trigger geometry sanity (Task 9 rework brief): distance from home_base (-1.276, 1.2) to
# this spot is ~2.955 m — far outside either color's REACTION_RANGE_M at mission start, so
# the reaction cannot fire at t=0. sphere_approach (0.0, 3.2), mission2's nav goal, is only
# ~0.583 m from the ball — inside REACTION_RANGE_M for BOTH colors (red 1.3 m, yellow
# 0.8 m) — so the robot's final approach to the goal necessarily brings it into trigger
# range for whichever color is spawned; the robot travels ~2.5 m (home -> doorway ->
# sphere_approach) before that can happen, comfortably above MIN_TRAVEL_M. That same
# 0.583 m closest-approach distance sits inside both per-color bands [BAND_NEAR,
# BAND_FAR[color]] = [0.3, 1.6] (red) and [0.3, 1.1] (yellow), so judge_red's and
# judge_yellow's band checks are both satisfiable from the real approach path (Task 9
# final batch, 2026-07-17 — per-color REACTION_RANGE_M).
BALL_AT_SPHERE_XY = (0.3, 3.7)

# Task 9 final batch (2026-07-17): REACTION_RANGE_M is now per-color ({'red': 1.3,
# 'yellow': 0.8} — missions.py). Placement-side geometry below (IGNORE_MARGIN,
# MIN_SPAWN_DIST_M) must clear the LARGEST threshold to stay safe for every color, so it's
# derived from max(REACTION_RANGE_M.values()) rather than either color individually.
MAX_REACTION_RANGE_M = max(REACTION_RANGE_M.values())
IGNORE_MARGIN = 0.5           # ignorable = never within MAX_REACTION_RANGE_M + this of route
# react placements: min distance from the goal (see solve_placement) — keeps the ball
# out of the final in-place-rotation dead zone (Task 9 tuning, 2026-07-17)
REACT_GOAL_CLEARANCE_M = 0.7
# Task 9 fix (2026-07-17): a live GUI-observed run caught a DEGENERATE PASS — with t
# narrowed to (0.30, 0.40) (see the comment below on t's history), some seeds place the
# ball only 0.71-0.95 m from home_base, inside REACTION_RANGE_M['red'] (1.3). The robot
# "reacts" at t=0 without ever driving, and the judge (pre-Task-9) had no way to catch
# it. Fix has two parts: this distance floor (encodes "the robot must actually drive to
# reach the ball") plus judge_red/judge_yellow's new minimum-travel check (belt +
# suspenders — the judge must not trust placement geometry alone). Derived from
# MAX_REACTION_RANGE_M, not hardcoded, so the two stay in lockstep if either color's
# trigger range is retuned again.
MIN_SPAWN_DIST_M = MAX_REACTION_RANGE_M + 0.3  # react ball must spawn this far from home
# BAND_FAR widened to trigger-threshold + 0.3 during Task 9 live tuning (2026-07-17): a
# legitimate trigger fires when the DETECTOR's estimated range crosses
# REACTION_RANGE_M[color], but the JUDGE checks TRUE ground-truth distance — a live run
# measured a real 1.342 m closest approach for a red trigger that fired correctly (est.
# range within the detector's known ~4% calibration spread), which fails a band edge
# sitting exactly at REACTION_RANGE_M['red']. BAND_FAR needs headroom over the trigger
# threshold to absorb detector noise + the robot's brief settling drift between cancel
# and the ground-truth snapshot, not just re-express the trigger definition.
#
# Made per-color in Task 9's final batch (2026-07-17) alongside REACTION_RANGE_M: red's
# far band is unchanged in effect (1.3 + 0.3 = 1.6); yellow's is 0.8 + 0.3 = 1.1, derived
# the same way rather than hardcoded, so the two stay in lockstep with missions.py.
# BAND_NEAR stays a single shared floor — it reflects physical closest-approach geometry
# (robot + ball radii, not the trigger threshold), so it doesn't need a per-color split.
BAND_NEAR = 0.3                    # reaction band vs ball truth, near edge (spec §3)
BAND_FAR = {color: r + 0.3 for color, r in REACTION_RANGE_M.items()}  # per-color far edge
HOME_TOL = 0.3                     # yellow: final pose vs home_base
SPHERE_NEAR, SPHERE_FAR = 0.25, 0.75  # ignore: final pose vs the green sphere
STATIONARY_TOL = 0.05              # red: max drift between two truth samples
# Task 9 fix (2026-07-17): minimum start->reaction displacement for red/yellow judges —
# a robot that "reacts" without actually driving (see MIN_SPAWN_DIST_M above for the
# placement-side half of this fix) must not pass. 0.5 m is comfortably below
# MIN_SPAWN_DIST_M (1.6) so any real drive toward a correctly-placed ball clears it, but
# well above GPS/AMCL settle jitter.
MIN_TRAVEL_M = 0.5

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
    (mid-leg, small lateral offset), rejecting draws too close to the goal. 'ignore':
    clear-floor anchor + jitter, verified outside the reaction envelope of every sampled
    route point."""
    rng = random.Random(seed)
    if variant == 'react':
        (ax, ay), (bx, by) = (SEMANTIC_MAP['doorway_center'],
                              SEMANTIC_MAP['sphere_approach'])
        dx, dy = bx - ax, by - ay
        norm = math.hypot(dx, dy)
        # t range: 0.35-0.75, RESTORED during Task 9 fix (2026-07-17) after a brief
        # narrowing to (0.30, 0.40) during the same day's earlier live tuning. That
        # narrowing was a mistake, not a fix: it pinned the ball 0.71-0.95 m from
        # home_base — inside REACTION_RANGE_M — so several seeds spawned the ball
        # already within the trigger radius of the robot's start pose. The robot
        # "reacted" without driving anywhere and the (then-instrumentation-free) judge
        # passed it anyway. MIN_SPAWN_DIST_M above now encodes the actual intent ("must
        # drive to reach the ball") directly as a placement constraint, and
        # judge_red/judge_yellow independently check displacement — so the wide t range
        # (which better matches Nav2's real path and the camera's FOV during the
        # approach) is safe to restore. The FOV-edge / heading-arc concerns recorded in
        # the superseded comment (perpendicular path deviation growing for t > ~0.4,
        # bearing sweeping wide near the goal) are real but are exactly what
        # REACT_GOAL_CLEARANCE_M and the retry loop below already guard against — they
        # do not require re-narrowing t.
        #
        # Lateral jitter kept at +/-0.08 m (Task 9 fix, 2026-07-17) rather than restored
        # to the earlier +/-0.15 m: the narrower jitter was tuned against a real
        # frame-edge clipping failure (bearing hovering at the camera's FOV edge,
        # width_px underestimated, range estimate overshooting to 2.9-6.7 m for a true
        # ~1.1 m distance — see change 3, edge-clipped detections now excluded from the
        # trigger at the source). With that root cause now fixed in the detector, +/-0.08
        # is probably tighter than necessary, but re-widening it wasn't asked for and
        # untangling it from t's restore in the same change risks re-introducing a
        # regression without a live run to confirm — left as an open question for the
        # next live-tuning pass, not decided here.
        for _ in range(100):
            t = rng.uniform(0.35, 0.75)
            off = rng.uniform(-0.08, 0.08)
            xy = (ax + t * dx - dy / norm * off, ay + t * dy + dx / norm * off)
            if (math.hypot(xy[0] - bx, xy[1] - by) >= REACT_GOAL_CLEARANCE_M
                    and math.hypot(xy[0] - SEMANTIC_MAP['home_base'][0],
                                   xy[1] - SEMANTIC_MAP['home_base'][1])
                    >= MIN_SPAWN_DIST_M):
                return xy
        raise RuntimeError(f'no react placement found for seed {seed}')
    if variant == 'ignore':
        # Clear floor per the world map: by the bed / hallway east. Visible-but-far
        # placements are deliberately possible — correctly ignoring them is the test.
        anchors = ((0.9, 5.2), (1.3, 1.7))
        route = _route_points()
        for _ in range(100):
            axx, ayy = anchors[rng.randrange(len(anchors))]
            x = axx + rng.uniform(-0.2, 0.2)
            y = ayy + rng.uniform(-0.2, 0.2)
            if all(math.hypot(x - rx, y - ry) >= MAX_REACTION_RANGE_M + IGNORE_MARGIN
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


def judge_red(ball_xy, events, photo_paths, truth_start, truth_a, truth_b):
    """PASS = red event fired in-band + robot actually drove there + photo exists +
    robot stationary (spec §3). truth_start is ground truth captured BEFORE
    run_mission — its distance from truth_a (captured right after) is the
    minimum-travel check (Task 9 fix, 2026-07-17): without it, a ball placed inside the
    trigger radius of the robot's start pose produces a vacuous PASS (see
    MIN_SPAWN_DIST_M in solve_placement) with no drive at all."""
    fails = []
    red = [e for e in events if e['color'] == 'red']
    if not red:
        fails.append('no red reaction event fired')
    elif red[0]['truth_xy'] is None:
        fails.append('reaction event carries no ground truth (sim only check)')
    elif not BAND_NEAR <= _dist(red[0]['truth_xy'], ball_xy) <= BAND_FAR['red']:
        fails.append(f"reaction point {red[0]['truth_xy']} outside band "
                     f"[{BAND_NEAR}, {BAND_FAR['red']}] m of ball {ball_xy}")
    if truth_start is None or truth_a is None:
        fails.append('no ground truth for minimum-travel check')
    elif _dist(truth_start, truth_a) < MIN_TRAVEL_M:
        fails.append(f'robot barely moved: {_dist(truth_start, truth_a):.3f} m from '
                     f'start (< {MIN_TRAVEL_M} m) — reacted without driving')
    if not photo_paths:
        fails.append('no reaction photo saved')
    if truth_a is None or truth_b is None:
        fails.append('no ground truth for stationary check')
    elif _dist(truth_a, truth_b) > STATIONARY_TOL:
        fails.append(f'robot not stationary: moved {_dist(truth_a, truth_b):.3f} m')
    elif not BAND_NEAR <= _dist(truth_b, ball_xy) <= BAND_FAR['red']:
        fails.append(f'final pose {truth_b} outside band of ball {ball_xy}')
    return fails


def judge_yellow(ball_xy, events, photo_paths, truth_start, final_truth):
    """PASS = yellow event in-band + robot actually drove there + photo + physically
    home (spec §3). truth_start is ground truth captured BEFORE run_mission — reuses
    the reaction event's own truth_xy (already captured by _execute_reaction) rather
    than adding new instrumentation, same minimum-travel intent as judge_red (Task 9
    fix, 2026-07-17)."""
    fails = []
    yellow = [e for e in events if e['color'] == 'yellow']
    if not yellow:
        fails.append('no yellow reaction event fired')
    elif yellow[0]['truth_xy'] is None:
        fails.append('reaction event carries no ground truth (sim only check)')
    elif not BAND_NEAR <= _dist(yellow[0]['truth_xy'], ball_xy) <= BAND_FAR['yellow']:
        fails.append(f"reaction point {yellow[0]['truth_xy']} outside band "
                     f"[{BAND_NEAR}, {BAND_FAR['yellow']}] m of ball {ball_xy}")
    if truth_start is None or not yellow or yellow[0]['truth_xy'] is None:
        fails.append('no ground truth for minimum-travel check')
    elif _dist(truth_start, yellow[0]['truth_xy']) < MIN_TRAVEL_M:
        fails.append(f"robot barely moved: "
                     f"{_dist(truth_start, yellow[0]['truth_xy']):.3f} m from start "
                     f'(< {MIN_TRAVEL_M} m) — reacted without driving')
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
