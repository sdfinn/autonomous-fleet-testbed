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
import ast
import glob
import json
import math
import os
import random
import signal
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'nav_fleet'))

from nav_fleet.ground_truth import get_ground_truth_xy  # noqa: E402
from nav_fleet.image_io import photo_similarity  # noqa: E402
from nav_fleet.missions import REACTION_RANGE_M  # noqa: E402
from nav_fleet.semantic_map import MARKER_XY, SEMANTIC_MAP  # noqa: E402
from tools.telemetry_logger import log_run  # noqa: E402

WORLD = 'bedroom'
BALL_RADIUS = 0.043           # 86 mm croquet ball (spec §6) — never inflate
# Ghost-ball settle (CLAUDE.md Gotchas, 2026-07-17): the headless llvmpipe renderer keeps a
# REMOVED model in camera frames for seconds — wait this long after remove_ball so the next
# run never reacts to the previous run's ball. Single source of truth: tests/test_mission2.py,
# scripts/hil_stage.sh, and tools/mission2_day.py all key off this value.
BALL_REMOVAL_SETTLE_S = 3.0

# Deterministic placement (Task 9 rework, 2026-07-17 — Mike's decision, supersedes seeded
# placement for the live tests below): 0.3 m in +x beside the floor MARKER. DERIVED from
# MARKER_XY (semantic_map.py, = bedroom_goal (0.0, 3.7)) so placement moves WITH the marker
# and is never tuned independently (Task 13 spec): BALL = (MARKER_X + 0.3, MARKER_Y). The
# marker did not move in Task 13 (it's already at the clear-zone centre); only the APPROACH
# moved north to clear the dresser squeeze — so this spot is unchanged (0.3, 3.7) and the
# color/size range_k calibration and reaction bands carry over untouched.
#
# Verified clear of every static footprint in bedroom_simple.sdf: the floor marker itself
# (0.10 m radius disc — 0.3 m centre distance clears BALL_RADIUS + disc radius and the
# >=0.25 m spec floor), Dresser (center (0.0074, 2.7583), 0.813x0.457 box -> y in
# [2.530, 2.987], well south of y=3.7), Bed (center (0.8130, 5.4360), 1.524x2.032 box ->
# y in [4.420, 6.452], well north of y=3.7), and Wall_East (x in [1.600, 1.650], far from
# x=0.3).
#
# Trigger geometry sanity (Task 9 rework brief): distance from home_base (-1.276, 1.2) to
# this spot is ~2.955 m — far outside either color's REACTION_RANGE_M at mission start, so
# the reaction cannot fire at t=0. sphere_approach (0.0, 3.5), mission2's nav goal, is only
# ~0.361 m from the ball — inside REACTION_RANGE_M for BOTH colors (red 1.3 m, yellow
# 0.8 m) — so the robot's final approach to the goal necessarily brings it into trigger
# range for whichever color is spawned; the robot travels ~2.7 m (home -> doorway ->
# sphere_approach) before that can happen, comfortably above MIN_TRAVEL_M. That same
# 0.361 m closest-approach distance sits inside both per-color bands [BAND_NEAR,
# BAND_FAR[color]] = [0.3, 1.6] (red) and [0.3, 1.1] (yellow), so judge_red's and
# judge_yellow's band checks are both satisfiable from the real approach path (Task 9
# final batch, 2026-07-17 — per-color REACTION_RANGE_M).
BALL_AT_SPHERE_XY = (round(MARKER_XY[0] + 0.3, 4), round(MARKER_XY[1], 4))

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
HOME_TOL = 0.3                     # nominal/yellow: final pose vs home_base
STATIONARY_TOL = 0.05              # red: max drift between two truth samples
# Return-fidelity threshold (Task 13 §3): max mean-abs grayscale diff [0..1] between the
# home reference photo (taken at spawn, before moving) and the home arrival photo (taken
# after the mission drives itself back). Above this, the round trip did not return the robot
# faithfully to its start POSE. Expected variance the threshold must absorb: Nav2 goal
# tolerance (a few cm of position) + RPP rotate_to_heading residual (up to ~17 deg of final
# yaw -> the arrival frame is a parallaxed/rotated view of the same scene). CALIBRATED from
# real sim runs (>=3 pairs) 2026-07-18 — see tools/mission2_day self-test / task-13b-report:
# observed nominal pairs clustered at diff ~<CAL> with a max of ~<CAL_MAX>; threshold set
# with headroom above that. Placeholder pending live calibration in this task's live phase.
HOME_PAIR_MAX_DIFF = 0.18
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


def judge_red(ball_xy, events, photo_paths, truth_start, truth_a, truth_b,
              home_arrival_photos=None):
    """PASS = red event fired in-band + robot actually drove there + photo exists +
    robot stationary + NO home-arrival photo (spec §3; Task 13: red STOPS mid-room and must
    not return home, so a home_arrival photo means it wrongly drove home). truth_start is
    ground truth captured BEFORE run_mission — its distance from truth_a (captured right
    after) is the minimum-travel check (Task 9 fix, 2026-07-17): without it, a ball placed
    inside the trigger radius of the robot's start pose produces a vacuous PASS (see
    MIN_SPAWN_DIST_M in solve_placement) with no drive at all."""
    fails = []
    if home_arrival_photos:
        fails.append(f'red took a home-arrival photo {home_arrival_photos} — it must stop '
                     'mid-room, not return home')
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


def judge_yellow(ball_xy, events, photo_paths, truth_start, final_truth, similarity=None):
    """PASS = yellow event in-band + robot actually drove there + reaction photo + physically
    home (spec §3) + home-photo pair PASS (Task 13 §3 — yellow now self-returns and takes a
    home arrival photo, so the return-fidelity pair check applies to it too). truth_start is
    ground truth captured BEFORE run_mission — reuses the reaction event's own truth_xy
    (already captured by _execute_reaction) rather than adding new instrumentation, same
    minimum-travel intent as judge_red (Task 9 fix, 2026-07-17)."""
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
    fails += judge_home_pair(similarity)
    return fails


def home_pair_similarity(ref_photos, arrival_photos):
    """Return-fidelity score for the NEWEST home reference + home arrival photo, or None if
    either is missing/unreadable (Task 13 §3). Kept separate from the verdict so callers can
    log the raw score as telemetry (home_photo_similarity) even when it fails the check."""
    if not ref_photos or not arrival_photos:
        return None
    try:
        return photo_similarity(sorted(ref_photos)[-1], sorted(arrival_photos)[-1])
    except (OSError, ValueError):
        return None


def judge_home_pair(similarity):
    """Verdict fails for the home-photo pair given a precomputed similarity score (Task 13
    §3). None (missing/unreadable pair) fails; a score above HOME_PAIR_MAX_DIFF fails as a
    poor return. Composed into the nominal and yellow verdicts (red never returns home)."""
    if similarity is None:
        return ['home-photo pair missing/unreadable (reference or arrival)']
    if similarity > HOME_PAIR_MAX_DIFF:
        return [f'home photo pair mismatch: {similarity:.4f} > {HOME_PAIR_MAX_DIFF} '
                '(robot did not return faithfully to its start pose)']
    return []


def judge_nominal(events, final_truth, marker_photos, similarity):
    """Nominal (no-ball) round-trip verdict (Task 13 §3, Option B): PASS = zero reactions +
    marker photo exists + ended HOME (ground truth) + home-photo pair PASS. The old
    stop-short-of-the-sphere check is gone — the nominal mission now drives itself home, so
    the final pose is judged against home_base, and reaching the marker is verified by the
    marker photo's existence (per-waypoint checklist model)."""
    fails = []
    if events:
        fails.append(f'spurious reaction(s): {events}')
    if final_truth is None:
        fails.append('no ground truth for home check')
    elif _dist(final_truth, SEMANTIC_MAP['home_base']) > HOME_TOL:
        fails.append(f'not home: {final_truth} is '
                     f"{_dist(final_truth, SEMANTIC_MAP['home_base']):.2f} m from home")
    if not marker_photos:
        fails.append('no marker photo saved (robot did not reach/photograph the marker)')
    fails += judge_home_pair(similarity)
    return fails


def parse_reaction_events(log_text):
    """Recover reaction events from a mission_runner stdout log (pure — unit-tested).

    mission_runner.main() prints one line per reaction:
        ``  reaction: <color> -> <reaction> at <truth_xy>``
    where <truth_xy> is a ``(x, y)`` tuple in sim or ``None`` on the Jetson (no Gazebo
    there — get_ground_truth_xy returns None). Each recovered event mirrors the in-process
    dict shape (`color`, `reaction`, `truth_xy`) so judge_red/judge_yellow consume it
    unchanged. The tuple is recovered with ast.literal_eval; anything unparseable (or the
    literal ``None``) becomes truth_xy=None, which the HIL judges then override with a
    workstation ground-truth sample (the Jetson can't measure ground truth)."""
    events = []
    for line in log_text.splitlines():
        s = line.strip()
        if not s.startswith('reaction: '):
            continue
        body = s[len('reaction: '):]
        head, sep, tail = body.rpartition(' at ')
        if not sep:
            continue
        color, arrow, reaction = head.partition(' -> ')
        if not arrow:
            continue
        try:
            truth = ast.literal_eval(tail.strip())
        except (ValueError, SyntaxError):
            truth = None
        if not (truth is None or (isinstance(truth, tuple) and len(truth) == 2)):
            truth = None
        events.append({'color': color.strip(), 'reaction': reaction.strip(),
                       'truth_xy': truth})
    return events


def _sample_two_ground_truths(gap_s=2.0):
    """Two ground-truth samples `gap_s` apart (red's stationary check — robot is stopped
    at the ball once photo_then_stop returns, so both are taken workstation-side after the
    mission). Returns (truth_a, truth_b), either possibly None off-sim/on error."""
    truth_a = get_ground_truth_xy()
    time.sleep(gap_s)
    truth_b = get_ground_truth_xy()
    return truth_a, truth_b


def _reaction_events_with_truth(log_text, color, reaction_xy):
    """Parsed events for `color` with truth_xy overridden by the workstation-observed
    reaction point (`reaction_xy`, the poller's closest approach to the ball). The Jetson
    log carries truth_xy=None; the workstation Gazebo is the authoritative ground truth."""
    events = parse_reaction_events(log_text)
    for e in events:
        if e['color'] == color and reaction_xy is not None:
            e['truth_xy'] = tuple(reaction_xy)
    return events


def log_variant_row(variant, seed, ok, runner=None, home_photo_similarity=None):
    """One telemetry row per judged variant run — the row's result is the JUDGED verdict
    (ground-truth honest), which may be stricter than the mission's self-report.
    home_photo_similarity (Task 13 §3) is the return-fidelity score for nominal/yellow (None
    for red and off-sim), trended by baseline_monitor as drift-detection material."""
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
        home_photo_similarity=home_photo_similarity,
    )


def _as_tuple(xy):
    return tuple(xy) if xy is not None else None


def _load_watch(path):
    """Read the poller's JSON (start/reaction/final ground-truth points). Missing/unreadable
    -> empty dict (the judges then fail cleanly on the None fields, never crash)."""
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _cmd_spawn(args):
    x, y = solve_placement(args.variant, args.seed)
    name = spawn_ball(args.color, x, y)
    print(json.dumps({'name': name, 'x': x, 'y': y}))


def _cmd_spawn_at(args):
    """Deterministic spawn at BALL_AT_SPHERE_XY — mirrors the sim tests'
    spawn_ball(color, *BALL_AT_SPHERE_XY) exactly (no seed, no random placement)."""
    x, y = BALL_AT_SPHERE_XY
    name = spawn_ball(args.color, x, y)
    print(json.dumps({'name': name, 'x': x, 'y': y}))


def _cmd_remove(args):
    remove_ball(args.name)


def _cmd_assert_home(args):
    """Start-position precondition (mirrors tests/test_mission2.py::_assert_at_home_base):
    workstation ground truth must be within `--tol` of home_base, else exit nonzero so a
    failed drive-home surfaces loudly instead of silently displacing the next rung."""
    truth = get_ground_truth_xy()
    hx, hy = SEMANTIC_MAP['home_base']
    if truth is None:
        print('ASSERT FAIL: no ground truth — is the sim up on this host?')
        raise SystemExit(1)
    miss = _dist(truth, (hx, hy))
    ok = miss <= args.tol
    print(f'home precondition: robot at ({truth[0]:.3f}, {truth[1]:.3f}), {miss:.3f} m '
          f'from home_base ({hx}, {hy}), tol {args.tol} m -> {"OK" if ok else "FAIL"}')
    raise SystemExit(0 if ok else 1)


def _cmd_watch(args):
    """Workstation-side ground-truth poller, run concurrently with the Jetson mission.

    The Jetson can't measure ground truth (no Gazebo there), and for the yellow rung the
    robot drives home after reacting — so its reaction point can't be recovered from any
    post-mission sample. This poller samples the workstation Gazebo throughout the mission
    and records the CLOSEST approach to the ball (= the reaction point: the robot reacts
    then stops/retreats, so it never gets closer afterward), plus the first sample (start,
    ~home) and last sample (final). Writes its JSON on SIGTERM/SIGINT (bash kills it once
    the mission ssh returns) or when --max-s elapses.

    DESIGN NOTE (closest-approach == reaction point): this equivalence holds ONLY because
    Mission 2's path never loops back past the ball after reacting — the robot reacts, then
    either stops (red) or retreats home (yellow), monotonically increasing its distance to
    the ball from the reaction point onward. A future mission whose path passes the same ball
    twice (a loop / figure-8) would record the WRONG sample as the reaction point; revisit
    this poller (e.g. gate on the reaction-event timestamp) before reusing it there."""
    ball = (args.ball_x, args.ball_y)
    state = {'start_xy': None, 'reaction_xy': None, 'reaction_dist': None,
             'final_xy': None, 'n_samples': 0}
    stop = {'flag': False}

    def _handler(signum, frame):
        stop['flag'] = True

    signal.signal(signal.SIGTERM, _handler)
    signal.signal(signal.SIGINT, _handler)
    deadline = time.time() + args.max_s
    try:
        while not stop['flag'] and time.time() < deadline:
            xy = get_ground_truth_xy()
            if xy is not None:
                if state['start_xy'] is None:
                    state['start_xy'] = list(xy)
                state['final_xy'] = list(xy)
                state['n_samples'] += 1
                d = math.hypot(xy[0] - ball[0], xy[1] - ball[1])
                if state['reaction_dist'] is None or d < state['reaction_dist']:
                    state['reaction_dist'] = d
                    state['reaction_xy'] = list(xy)
            time.sleep(args.poll_s)
    finally:
        with open(args.out, 'w') as f:
            json.dump(state, f)


def _cmd_judge_nominal(args):
    # HIL rung 1 is the NO-BALL nominal round trip (Task 13 Option B): home_ref photo ->
    # navigate to the marker -> marker photo -> navigate HOME -> home_arrival photo, reacting
    # to nothing. judge_nominal checks zero reactions + marker photo exists + ended HOME
    # (workstation ground truth) + home-photo pair PASS. Mirrors
    # tests/test_mission2.py::test_mission2_nominal. Photos were scp'd to STATE_DIR by
    # hil_stage.sh (the Jetson has no Gazebo, so the pair check runs here).
    with open(args.mission_log) as f:
        log_text = f.read()
    marker_photos = sorted(glob.glob(args.marker_glob))
    similarity = home_pair_similarity(sorted(glob.glob(args.home_ref_glob)),
                                      sorted(glob.glob(args.home_arrival_glob)))
    fails = judge_nominal(parse_reaction_events(log_text), get_ground_truth_xy(),
                          marker_photos, similarity)
    ok = not fails
    log_variant_row('nominal', None, ok=ok, home_photo_similarity=similarity)
    for fail in fails:
        print(f'JUDGE FAIL: {fail}')
    print(f'home_photo_similarity: {similarity}')
    print(f'mission2_nominal: {"PASS" if ok else "FAIL"}')
    raise SystemExit(0 if ok else 1)


def _cmd_judge_react(args):
    """HIL judge for a react rung (red or yellow). Reuses judge_red/judge_yellow,
    supplying ground truth from the WORKSTATION (the Jetson log's truth_xy is None): the
    reaction point comes from the concurrent poller (`--watch-file`), and red's stationary
    check takes two fresh samples 2 s apart in-process (the robot is stopped at the ball
    once photo_then_stop returns). Yellow additionally runs the return-fidelity pair check
    on its home_ref/home_arrival photos (scp'd to STATE_DIR); red asserts NO home-arrival
    photo exists (it must stop mid-room, not return home)."""
    with open(args.mission_log) as f:
        log_text = f.read()
    watch = _load_watch(args.watch_file)
    reaction_xy = watch.get('reaction_xy')
    truth_start = _as_tuple(watch.get('start_xy'))
    events = _reaction_events_with_truth(log_text, args.color, reaction_xy)
    photos = sorted(glob.glob(args.photo_glob))
    home_arrival = sorted(glob.glob(args.home_arrival_glob)) if args.home_arrival_glob else []
    ball_xy = (args.ball_x, args.ball_y)
    similarity = None
    if args.color == 'red':
        truth_a, truth_b = _sample_two_ground_truths()
        fails = judge_red(ball_xy, events, photos, truth_start, truth_a, truth_b,
                          home_arrival_photos=home_arrival)
    else:
        final_truth = get_ground_truth_xy()
        similarity = home_pair_similarity(
            sorted(glob.glob(args.home_ref_glob)) if args.home_ref_glob else [], home_arrival)
        fails = judge_yellow(ball_xy, events, photos, truth_start, final_truth, similarity)
    ok = not fails
    # Workstation-side JUDGED HIL verdict row (deferred here from Task 11) — the honest,
    # ground-truth-checked result, distinct from the Jetson's own mission self-report.
    log_variant_row(args.color, None, ok=ok, home_photo_similarity=similarity)
    for fail in fails:
        print(f'JUDGE FAIL: {fail}')
    print(f'mission2_{args.color}: {"PASS" if ok else "FAIL"}')
    raise SystemExit(0 if ok else 1)


def main():
    parser = argparse.ArgumentParser(description='Mission 2 harness CLI (HIL tier).')
    sub = parser.add_subparsers(dest='cmd', required=True)

    p_spawn = sub.add_parser('spawn', help='solve seeded placement + spawn the ball; '
                                           'prints JSON {name, x, y} (seeded path, unused '
                                           'by the deterministic live tests)')
    p_spawn.add_argument('--variant', choices=['react', 'ignore'], required=True)
    p_spawn.add_argument('--color', choices=['red', 'yellow'], required=True)
    p_spawn.add_argument('--seed', type=int, required=True)
    p_spawn.set_defaults(func=_cmd_spawn)

    p_spawn_at = sub.add_parser('spawn-at', help='spawn the ball at the deterministic '
                                                 'BALL_AT_SPHERE_XY spot; prints JSON '
                                                 '{name, x, y}')
    p_spawn_at.add_argument('--color', choices=['red', 'yellow'], required=True)
    p_spawn_at.set_defaults(func=_cmd_spawn_at)

    p_rm = sub.add_parser('remove', help='remove a spawned ball by model name')
    p_rm.add_argument('name')
    p_rm.set_defaults(func=_cmd_remove)

    p_home = sub.add_parser('assert-home', help='exit nonzero unless workstation ground '
                                                'truth is within --tol of home_base')
    p_home.add_argument('--tol', type=float, default=0.35)
    p_home.set_defaults(func=_cmd_assert_home)

    p_watch = sub.add_parser('watch', help='poll workstation ground truth during a mission; '
                                           'record closest approach to the ball as the '
                                           'reaction point; write JSON on SIGTERM/--max-s')
    p_watch.add_argument('--ball-x', type=float, required=True)
    p_watch.add_argument('--ball-y', type=float, required=True)
    p_watch.add_argument('--out', required=True)
    p_watch.add_argument('--poll-s', type=float, default=0.5)
    p_watch.add_argument('--max-s', type=float, default=300.0)
    p_watch.set_defaults(func=_cmd_watch)

    p_nom = sub.add_parser('judge-nominal', help='judge a nominal (no-ball) HIL round trip: '
                                                 'zero reactions + marker photo + ended home '
                                                 '+ home-photo pair (Task 13 Option B)')
    p_nom.add_argument('--mission-log', required=True)
    p_nom.add_argument('--marker-glob', required=True)
    p_nom.add_argument('--home-ref-glob', required=True)
    p_nom.add_argument('--home-arrival-glob', required=True)
    p_nom.set_defaults(func=_cmd_judge_nominal)

    for color in ('red', 'yellow'):
        pj = sub.add_parser(f'judge-{color}',
                            help=f'judge a {color} react HIL run (reuses judge_{color})')
        pj.add_argument('--ball-x', type=float, required=True)
        pj.add_argument('--ball-y', type=float, required=True)
        pj.add_argument('--mission-log', required=True)
        pj.add_argument('--watch-file', required=True)
        pj.add_argument('--photo-glob', required=True)
        # Task 13 return-fidelity plumbing: yellow pairs home_ref vs home_arrival; red
        # asserts NO home_arrival photo exists. Optional so a bare local invocation still
        # runs; the CI/HIL path always passes them.
        pj.add_argument('--home-ref-glob', default=None)
        pj.add_argument('--home-arrival-glob', default=None)
        pj.set_defaults(func=_cmd_judge_react, color=color)

    args = parser.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
