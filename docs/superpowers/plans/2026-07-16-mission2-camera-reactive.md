# Mission 2 — Camera-Reactive Navigation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps
> use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The robot drives toward the green sphere and reacts to croquet balls it comes
across — red = photo + full stop, yellow = photo + return home — with seeded-random,
harness-owned ball placement and Gazebo-ground-truth pass/fail, wired into stage-2 CI and
then graduated incrementally into stage-4 HIL.

**Architecture:** A new always-on HSV detector node publishes
`vision_msgs/Detection2DArray` per camera frame (empty frames included). The `navigate`
mission step gains a declarative `reactions` field; `mission_runner` supervises — it counts
consecutive in-range detections while `NavRunner` waits on the Nav2 goal, cancels the goal
on trigger, and executes the reaction with existing primitives. A test harness
(`tools/mission2_harness.py`) owns seeded ball placement, Gazebo spawn/remove, and
ground-truth judging; robot code never knows ball positions.

**Tech Stack:** ROS2 Jazzy, Gazebo Harmonic, Nav2, `vision_msgs`, numpy (no OpenCV),
pytest, SQLite/pandera telemetry.

**Spec (source of truth):** `docs/superpowers/specs/2026-07-16-mission2-design.md`

## Global Constraints

- flake8 max line length is **99** (stage-1 gate; broke CI on 2026-07-16 — check before commit).
- Trigger = apparent range ≤ **1.0 m** sustained **3 consecutive detector frames**; camera
  FOV is the only bearing filter.
- Ground-truth bands (initial values, may be re-fixed during Task 9 calibration then
  frozen in code): red/yellow reaction band **0.3–1.3 m** from ball; home tolerance
  **0.3 m**; ignore-variant sphere stop band **0.25–0.75 m** from (0.0, 3.7).
- Ball is **86 mm diameter** (radius 0.043), camera/marker-only (no collision geometry),
  matching the existing `goal_marker` pattern. Never inflate the ball to fix detection.
- **Robot code must not know ball positions.** Placement, spawn, and judging live in the
  harness only. (Snapshotting the robot's OWN ground-truth pose for reporting is allowed —
  `get_ground_truth_xy()` precedent.)
- Telemetry scenario names: `mission2_red` / `mission2_yellow` / `mission2_ignore`. New
  nullable `seed` column — logger, pandera schema, and `KNOWN_RUNS_COLS` all learn it **in
  the same commit** (Task 3).
- `ros-jazzy-vision-msgs` is declared in the Dockerfile, installed on the workstation AND
  the Jetson, and noted in CLAUDE.md **in the same commit** that first imports it (Task 4).
- New test files that import `rclpy` (or any ROS msg package) at module level MUST be
  added to stage-1-quality's `--ignore` list in `ci.yml` AND to CLAUDE.md's local pytest
  command in the same commit (this has bitten twice — see CLAUDE.md Gotchas).
- All work on a branch (`mission2-camera-reactive`), PR to main, stage-2 green before HIL
  tasks. Commit messages follow repo style (`feat(...)`, `fix(...)`, `docs(...)`).
- Run everything Tier-1 (x86 local) first; the Primary dev loop in CLAUDE.md applies.

## Reference facts (verified 2026-07-16, so tasks don't re-derive them)

- Camera: 640×480 RGB, HFOV 1.047 rad (60°), 10 Hz, topic `/robot_001/camera/image_raw`,
  mounted 0.175 m forward of base_link centre. Focal length f_px = 320/tan(0.5235) ≈ 554.3,
  so analytic size→range constant k = 554.3 × 0.086 ≈ **47.7 m·px** (Task 9 measures the
  real value).
- Gazebo world name: `bedroom` (`/world/bedroom/create` / `/world/bedroom/remove`).
- Green sphere (`goal_marker`) at (0.0, 3.7), hue ≈ 120° — outside both ball hue bands.
- `SEMANTIC_MAP` lives in `src/nav_fleet/nav_fleet/semantic_map.py`; `home_base` =
  (-1.276, 1.2), `doorway_center` = (-0.974, 2.430), `bedroom_goal` = (0.0, 3.7).
- `NavRunner.send_goal()` spins only the NavRunner node; MissionRunner's subscriptions are
  NOT serviced during a goal wait — Task 5 adds `spin_extra` for exactly this.
- The arm64 image does a plain (non-symlink) `colcon build`; config files ship via
  `setup.py` `data_files` under `share/nav_fleet/config/` — launch files resolve config via
  `PKG = pathlib.Path(__file__).parent.parent`, which works in both install modes.
- `tests/conftest.py` puts `src/nav_fleet` on `sys.path`, so `nav_fleet.*` imports work in
  stage-1 without ROS.

---

### Task 1: Mission data model — `reactions` field, mission2, validation

**Files:**
- Modify: `src/nav_fleet/nav_fleet/missions.py`
- Modify: `src/nav_fleet/nav_fleet/semantic_map.py`
- Test: `tests/test_missions.py` (pure Python — already runs in stage-1)

**Interfaces:**
- Consumes: existing `MissionStep`, `SEMANTIC_MAP`, `validate_mission`.
- Produces: `MissionStep.reactions: dict|None`; constants `VALID_REACTIONS =
  ('photo_then_stop', 'photo_then_home')`, `REACTION_RANGE_M = 1.0`,
  `REACTION_FRAMES = 3`; `MISSIONS['mission2']`; `SEMANTIC_MAP['sphere_approach']
  == (0.0, 3.2)`. Tasks 6, 7, 9 rely on these exact names.

- [ ] **Step 1: Write the failing tests** — append to `tests/test_missions.py`:

```python
def test_semantic_map_has_sphere_approach():
    from nav_fleet.semantic_map import SEMANTIC_MAP
    # 0.5 m short of the green sphere at bedroom_goal (0.0, 3.7) — Mission 2 nav goal
    assert SEMANTIC_MAP['sphere_approach'] == (0.0, 3.2)


def test_mission2_shape():
    import math
    from nav_fleet.missions import MISSIONS
    steps = MISSIONS['mission2']
    assert [s.action for s in steps] == ['navigate']
    assert steps[0].location == 'sphere_approach'
    assert steps[0].yaw == pytest.approx(math.pi / 2)  # face north, toward the sphere
    assert steps[0].reactions == {'red': 'photo_then_stop', 'yellow': 'photo_then_home'}


def test_validate_rejects_unknown_reaction():
    from nav_fleet.missions import MissionStep, validate_mission
    with pytest.raises(ValueError, match='unknown reaction'):
        validate_mission((MissionStep('navigate', 'go', 'bedroom_goal',
                                      reactions={'red': 'explode'}),))


def test_validate_rejects_reactions_on_take_picture():
    from nav_fleet.missions import MissionStep, validate_mission
    with pytest.raises(ValueError, match='navigate steps'):
        validate_mission((MissionStep('take_picture', 'snap',
                                      reactions={'red': 'photo_then_stop'}),))


def test_validate_rejects_navigate_without_location():
    from nav_fleet.missions import MissionStep, validate_mission
    with pytest.raises(ValueError, match='not in SEMANTIC_MAP'):
        validate_mission((MissionStep('navigate', 'go nowhere'),))
```

Also update the existing count assertion in `test_semantic_map_keeps_existing_locations`:
`assert len(SEMANTIC_MAP) == 10  # 9 as of Session 15 + sphere_approach (Mission 2)`.

- [ ] **Step 2: Run tests to verify the new ones fail**

Run: `python -m pytest tests/test_missions.py -v`
Expected: the 5 new tests FAIL (`KeyError: 'mission2'`, `TypeError: unexpected keyword
argument 'reactions'`, `KeyError: 'sphere_approach'`); existing ones PASS.

- [ ] **Step 3: Implement.** In `semantic_map.py`, add to the dict:

```python
    'sphere_approach': (0.0, 3.2),         # Mission 2 nav goal — 0.5 m short of the sphere
```

In `missions.py`: extend the constants and dataclass —

```python
VALID_ACTIONS = ('navigate', 'take_picture')  # Mission 2 adds reaction supervision atop these
VALID_REACTIONS = ('photo_then_stop', 'photo_then_home')

# Trigger definition A (spec §2): a ball whose apparent range is at or under
# REACTION_RANGE_M for REACTION_FRAMES consecutive detector frames. Values shared by
# mission_runner (counting) and the Mission 2 test harness (placement envelope).
REACTION_RANGE_M = 1.0
REACTION_FRAMES = 3


@dataclass(frozen=True)
class MissionStep:
    action: str          # one of VALID_ACTIONS
    label: str           # human-readable step description (logged during execution)
    location: str = None  # SEMANTIC_MAP key — required for 'navigate'
    yaw: float = None    # optional final heading (radians, map frame) for 'navigate'
    reactions: dict = None  # navigate only: detected color -> VALID_REACTIONS entry
```

Add to `MISSIONS`:

```python
    # Mission 2 (Session 16 Plan B): drive toward the green sphere and stop short of it,
    # reacting to croquet balls come across en route (spec §1-2). Single leg — the
    # reaction itself supplies any further movement (photo_then_home drives back).
    'mission2': (
        MissionStep('navigate', 'drive toward the green sphere, watching for balls',
                    'sphere_approach', math.pi / 2,
                    reactions={'red': 'photo_then_stop', 'yellow': 'photo_then_home'}),
    ),
```

Extend `validate_mission` (replace the body's loop):

```python
    for i, step in enumerate(steps):
        if step.action not in VALID_ACTIONS:
            raise ValueError(f'step {i}: unknown action {step.action!r}')
        if step.action == 'navigate' and step.location not in SEMANTIC_MAP:
            raise ValueError(f'step {i}: location {step.location!r} not in SEMANTIC_MAP')
        if step.reactions is not None:
            if step.action != 'navigate':
                raise ValueError(f'step {i}: reactions are only valid on navigate steps')
            for color, reaction in step.reactions.items():
                if reaction not in VALID_REACTIONS:
                    raise ValueError(
                        f'step {i}: unknown reaction {reaction!r} for color {color!r}')
```

- [ ] **Step 4: Run the full pure-Python suite**

Run: `python -m pytest tests/ -v --ignore=tests/test_ros2_contracts.py --ignore=tests/test_navigation.py --ignore=tests/test_mission_run.py`
Expected: ALL PASS (including the updated map-count test).

- [ ] **Step 5: Commit**

```bash
git add src/nav_fleet/nav_fleet/missions.py src/nav_fleet/nav_fleet/semantic_map.py tests/test_missions.py
git commit -m "feat(missions): reactions field + mission2 definition (spec §1-2, §4)"
```

---

### Task 2: Pure HSV detection module + Gazebo color profile

**Files:**
- Create: `src/nav_fleet/nav_fleet/hsv_detect.py`
- Create: `src/nav_fleet/config/hsv_gazebo.yaml`
- Modify: `src/nav_fleet/setup.py` (ship the yaml in `data_files`)
- Test: `tests/test_hsv_detect.py` (pure numpy — runs in stage-1)

**Interfaces:**
- Consumes: nothing project-side (numpy + pyyaml only — both already in requirements-ci).
- Produces: `load_hsv_config(path) -> dict`; `detect_balls(rgb: np.ndarray, cfg: dict) ->
  list[dict]` where each dict has keys `color` (str), `cx`, `cy` (float px), `width_px`,
  `height_px` (int), `range_m` (float), `pixels` (int). Task 4's node and Task 9's
  calibration tool call these.

- [ ] **Step 1: Write the failing tests** — create `tests/test_hsv_detect.py`:

```python
"""Unit tests for HSV ball detection — pure numpy, no ROS2 (runs in stage-1)."""
import numpy as np
import pytest


def _frame(w=64, h=48, bg=(180, 180, 180)):
    return np.full((h, w, 3), bg, dtype=np.uint8)


def _paint(frame, x0, y0, x1, y1, rgb):
    frame[y0:y1, x0:x1] = rgb
    return frame


@pytest.fixture
def cfg():
    from nav_fleet.hsv_detect import load_hsv_config
    return load_hsv_config('src/nav_fleet/config/hsv_gazebo.yaml')


def test_detects_red_patch(cfg):
    from nav_fleet.hsv_detect import detect_balls
    frame = _paint(_frame(), 10, 10, 30, 30, (220, 20, 20))
    out = detect_balls(frame, cfg)
    assert [d['color'] for d in out] == ['red']
    d = out[0]
    assert d['width_px'] == 20 and d['height_px'] == 20
    assert d['cx'] == pytest.approx(19.5, abs=0.5)
    assert d['range_m'] == pytest.approx(cfg['range_k'] / 20)


def test_detects_yellow_not_green(cfg):
    from nav_fleet.hsv_detect import detect_balls
    frame = _paint(_frame(), 5, 5, 25, 25, (220, 220, 20))    # yellow, hue ~60
    frame = _paint(frame, 40, 5, 60, 25, (20, 220, 20))       # green sphere, hue ~120
    out = detect_balls(frame, cfg)
    assert [d['color'] for d in out] == ['yellow']


def test_red_hue_wraparound(cfg):
    from nav_fleet.hsv_detect import detect_balls
    # hue just below 360 (pinkish red) must still match the wrapped red band
    frame = _paint(_frame(), 10, 10, 30, 30, (220, 20, 60))
    assert [d['color'] for d in detect_balls(frame, cfg)] == ['red']


def test_ignores_small_speckle(cfg):
    from nav_fleet.hsv_detect import detect_balls
    frame = _paint(_frame(), 10, 10, 13, 13, (220, 20, 20))   # 9 px < min_pixels
    assert detect_balls(frame, cfg) == []


def test_empty_frame_returns_empty(cfg):
    from nav_fleet.hsv_detect import detect_balls
    assert detect_balls(_frame(), cfg) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_hsv_detect.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'nav_fleet.hsv_detect'`.

- [ ] **Step 3: Create `src/nav_fleet/config/hsv_gazebo.yaml`:**

```yaml
# HSV detection profile for the GAZEBO camera (spec §4, §6). A real webcam gets its own
# profile (hsv_realcam.yaml) in the webcam follow-up plan — thresholds are per-camera
# config data, never code, and the measured delta between profiles is itself a
# sim-to-real data point.
colors:
  red:    {h: [345, 15], s_min: 0.5, v_min: 0.2}   # wraps through 0
  yellow: {h: [40, 75],  s_min: 0.5, v_min: 0.2}   # green sphere is ~120 — outside band
min_pixels: 40          # reject speckle; an 86 mm ball at 3 m is still ~200 px
range_k: 47.7           # analytic pinhole estimate (f_px 554.3 x 0.086 m ball) —
                        # REPLACED by the measured value in Task 9 calibration
```

- [ ] **Step 4: Create `src/nav_fleet/nav_fleet/hsv_detect.py`:**

```python
"""HSV colored-ball detection on RGB frames — pure numpy, no ROS, no OpenCV.

The algorithm is BC/isaac_project's hardware-proven HSV thresholding
(behavior_controller.py) reimplemented to this project's conventions (spec §4):
threshold in HSV, take the mask's bounding box, estimate range from apparent width via
the pinhole relation range_m = range_k / width_px. Pure so it is unit-testable on CI
runners without ROS2 (stage-1). Thresholds and range_k are per-camera CONFIG, not code.
"""
import numpy as np
import yaml


def load_hsv_config(path):
    """Load a per-camera HSV profile (colors, min_pixels, range_k) from YAML."""
    with open(path) as f:
        cfg = yaml.safe_load(f)
    for key in ('colors', 'min_pixels', 'range_k'):
        if key not in cfg:
            raise ValueError(f'hsv config {path} missing key {key!r}')
    return cfg


def rgb_to_hsv(rgb):
    """Vectorized RGB uint8 [H,W,3] -> (h degrees 0-360, s 0-1, v 0-1) float arrays."""
    arr = rgb.astype(np.float64) / 255.0
    r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
    v = arr.max(axis=-1)
    c = v - arr.min(axis=-1)
    safe_c = np.where(c == 0, 1.0, c)
    h = np.where(
        c == 0, 0.0,
        np.where(v == r, ((g - b) / safe_c) % 6,
                 np.where(v == g, (b - r) / safe_c + 2, (r - g) / safe_c + 4)),
    ) * 60.0
    s = np.where(v > 0, c / np.where(v == 0, 1.0, v), 0.0)
    return h, s, v


def detect_balls(rgb, cfg):
    """Detect configured ball colors in one RGB frame.

    Returns one dict per detected color: {'color', 'cx', 'cy', 'width_px', 'height_px',
    'range_m', 'pixels'}. One ball per color per frame by design (Mission 2 runs place a
    single ball; the bounding box of a multi-blob mask would simply be wrong — accepted).
    """
    h, s, v = rgb_to_hsv(rgb)
    out = []
    for color, band in cfg['colors'].items():
        h_lo, h_hi = band['h']
        if h_lo <= h_hi:
            mask = (h >= h_lo) & (h <= h_hi)
        else:  # band wraps through 0 (red)
            mask = (h >= h_lo) | (h <= h_hi)
        mask &= (s >= band['s_min']) & (v >= band['v_min'])
        pixels = int(mask.sum())
        if pixels < cfg['min_pixels']:
            continue
        ys, xs = np.nonzero(mask)
        width = int(xs.max() - xs.min() + 1)
        out.append({
            'color': color,
            'cx': float(xs.mean()),
            'cy': float(ys.mean()),
            'width_px': width,
            'height_px': int(ys.max() - ys.min() + 1),
            'range_m': cfg['range_k'] / width,
            'pixels': pixels,
        })
    return out
```

In `setup.py`, extend the config `data_files` entry:

```python
        ('share/' + package_name + '/config',
         ['config/nav2_params.yaml', 'config/drift_config.yaml',
          'config/hsv_gazebo.yaml']),
```

(Note: `setup.py`'s config list references `src/nav_fleet/config/` — the same directory
`nav2_only_launch.py` reads via `PKG / 'config'`. Also add `config/ekf.yaml` to that list
if it is missing — check while in the file.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_hsv_detect.py -v`
Expected: 5 PASS.

- [ ] **Step 6: Lint + commit**

```bash
flake8 --max-line-length=99 src/nav_fleet/nav_fleet/hsv_detect.py tests/test_hsv_detect.py
git add src/nav_fleet/nav_fleet/hsv_detect.py src/nav_fleet/config/hsv_gazebo.yaml \
        src/nav_fleet/setup.py tests/test_hsv_detect.py
git commit -m "feat(perception): pure-numpy HSV ball detection + Gazebo color profile"
```

---

### Task 3: Telemetry `seed` column (logger + pandera, same commit)

**Files:**
- Modify: `tools/telemetry_logger.py`
- Modify: `tools/validate_telemetry.py`
- Test: `tests/test_telemetry_logger.py`

**Interfaces:**
- Produces: `log_run(..., seed: int = None)` — Tasks 7 and 11 pass the placement seed.
- Schema: `runs.seed` INTEGER nullable; pandera `seed: Series[float] =
  pa.Field(nullable=True)` (SQLite ints with NULLs arrive as float in pandas);
  `KNOWN_RUNS_COLS` gains `"seed"`.

- [ ] **Step 1: Write the failing test** — append to `tests/test_telemetry_logger.py`
  (match the file's existing style — read it first; the test below follows the
  `db_path` fixture pattern from `conftest.py`):

```python
def test_log_run_stores_seed(db_path):
    import sqlite3
    from tools.telemetry_logger import log_run
    run_id = log_run(scenario="mission2_red", steps=1, final_x=0.0, final_y=3.0,
                     result="PASS", step_log=[], db_path=db_path, seed=123456789)
    with sqlite3.connect(db_path) as conn:
        row = conn.execute("SELECT seed FROM runs WHERE id = ?", (run_id,)).fetchone()
    assert row == (123456789,)


def test_log_run_seed_defaults_null(db_path):
    import sqlite3
    from tools.telemetry_logger import log_run
    run_id = log_run(scenario="mission1", steps=3, final_x=0.0, final_y=0.0,
                     result="PASS", step_log=[], db_path=db_path)
    with sqlite3.connect(db_path) as conn:
        row = conn.execute("SELECT seed FROM runs WHERE id = ?", (run_id,)).fetchone()
    assert row == (None,)


def test_schema_accepts_seed_column(db_path):
    from tools.telemetry_logger import log_run
    from tools.validate_telemetry import validate_runs, detect_schema_drift
    log_run(scenario="mission2_ignore", steps=1, final_x=0.0, final_y=3.3,
            result="PASS", step_log=[], db_path=db_path, seed=42)
    assert validate_runs(db_path) is True
    assert detect_schema_drift(db_path) is True
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_telemetry_logger.py -v`
Expected: new tests FAIL (`unexpected keyword argument 'seed'`).

- [ ] **Step 3: Implement.** `tools/telemetry_logger.py`:
  - `_ensure_run_columns`: add `"seed": "INTEGER",` to `expected_columns`.
  - `log_run`: add `seed: int = None` to the signature (after `power_mode`) and
    `"seed": seed,` to `optional_fields`.

  `tools/validate_telemetry.py`:
  - `RunsModel`: add (with this comment — the first-consumer lesson is the point):

```python
    # seed: Mission 2 harness placement seed (spec §7) — nullable, NULL on all Mission 1
    # rows. Added IN THE SAME COMMIT as the logger column: power_mode and hil_jetson each
    # broke CI when the schema met its first real row as a follow-up.
    seed: Series[float] = pa.Field(nullable=True)
```

  - `KNOWN_RUNS_COLS`: add `"seed",  # Mission 2 placement seed (Session 16 Plan B)`.

- [ ] **Step 4: Run the pure-Python suite**

Run: `python -m pytest tests/ -v --ignore=tests/test_ros2_contracts.py --ignore=tests/test_navigation.py --ignore=tests/test_mission_run.py`
Expected: ALL PASS.

- [ ] **Step 5: Migrate + validate the real dev DB (regression, not just tmp DBs)**

A pandera DataFrameModel field is REQUIRED once declared, and existing DBs don't have the
`seed` column until something writes a row. `init_db()` is idempotent and
`_ensure_run_columns` adds any missing column in place — so migrate explicitly, then
validate:

```bash
python -c "from tools.telemetry_logger import init_db; init_db()"
python tools/validate_telemetry.py
```
Expected: `✅ runs ... valid`, `✅ steps ... valid`, `✅ No schema drift`. Note for the PR:
the CI drift DB (`/home/mike/fleet-ci-data/fleet_runs.db`) migrates itself on the first
post-merge `log_run` (every `log_run` calls `init_db`), which happens in stage-2 BEFORE
stage-5 validates — same ordering that made the power_mode migration safe.

- [ ] **Step 6: Commit**

```bash
git add tools/telemetry_logger.py tools/validate_telemetry.py tests/test_telemetry_logger.py
git commit -m "feat(telemetry): nullable seed column — schema + logger in one commit (spec §7)"
```

---

### Task 4: Ball detector ROS node + launch wiring + vision_msgs dependency

**Files:**
- Create: `src/nav_fleet/nav_fleet/ball_detector.py`
- Modify: `src/nav_fleet/nav_fleet/image_io.py` (extract array decoding for reuse)
- Modify: `src/nav_fleet/setup.py` (entry point)
- Modify: `src/nav_fleet/launch/nav2_only_launch.py` (always-on with the nav stack)
- Modify: `Dockerfile` (apt dep)
- Modify: `CLAUDE.md` (env requirement note)
- Test: `tests/test_missions.py` untouched; decode refactor covered by existing
  `tests/test_missions.py::test_image_msg_to_png_*`; node exercised live in Task 9/10.

**Interfaces:**
- Consumes: `hsv_detect.load_hsv_config/detect_balls` (Task 2).
- Produces: node `ball_detector` publishing `vision_msgs/Detection2DArray` on
  `/robot_001/detections`, one message per camera frame INCLUDING empty frames;
  per detection: `results[0].hypothesis.class_id` = `red_ball`/`yellow_ball`,
  `results[0].pose.pose.position.x` = **estimated range in metres** (documented
  convention), bbox filled from the mask. `image_io.image_msg_to_rgb(msg) -> np.ndarray`.
  Task 6's `_detection_cb` reads exactly `class_id` and `pose.pose.position.x`.

- [ ] **Step 1: Install and verify vision_msgs on the workstation**

```bash
sudo apt install -y ros-jazzy-vision-msgs
bash -c 'source /opt/ros/jazzy/setup.bash && ros2 interface show vision_msgs/msg/Detection2D'
```
Expected: shows `results` (ObjectHypothesisWithPose[]) and `bbox` (BoundingBox2D). Confirm
the bbox centre field path — Jazzy is `bbox.center.position.x` (Pose2D holds a Point2D);
if the interface print shows a different shape, use what it prints in Step 3's code.

- [ ] **Step 2: Refactor `image_io.py`** — extract the decode so the detector reuses it:

```python
def image_msg_to_rgb(msg):
    """Decode one sensor_msgs/Image (rgb8/bgr8, row padding OK) to an RGB uint8 array."""
    if msg.encoding not in ('rgb8', 'bgr8'):
        raise ValueError(f'unsupported image encoding: {msg.encoding}')
    # `step` is the stride in bytes per row (may exceed width*3 due to padding).
    arr = np.frombuffer(bytes(msg.data), dtype=np.uint8).reshape(msg.height, msg.step)
    arr = arr[:, : msg.width * 3].reshape(msg.height, msg.width, 3)
    if msg.encoding == 'bgr8':
        arr = arr[:, :, ::-1]
    return arr


def image_msg_to_png(msg, path):
    """Write one camera frame to `path` as PNG. Supports rgb8 and bgr8 encodings."""
    PILImage.fromarray(image_msg_to_rgb(msg), 'RGB').save(path)
```

Run: `python -m pytest tests/test_missions.py -v -k image_msg` — Expected: 4 PASS
(existing tests cover the refactor).

- [ ] **Step 3: Create `src/nav_fleet/nav_fleet/ball_detector.py`:**

```python
"""HSV ball detector node (Mission 2, spec §4).

Always-on with the nav stack: launched by nav2_only_launch.py, runs wherever the robot
brain runs (workstation Tier-1, Jetson in HIL — camera frames arrive over DDS either
way). Publishes one vision_msgs/Detection2DArray per camera frame INCLUDING empty
frames, so 'N consecutive frames' is directly countable by subscribers with no timing
heuristics. Convention: results[0].pose.pose.position.x carries the estimated range in
metres (camera axis) — Detection2D has no native range field.

The image topic is remappable by design: the webcam follow-up plan remaps it to a real
camera topic and swaps hsv_config for hsv_realcam.yaml.
"""
import pathlib

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from vision_msgs.msg import Detection2D, Detection2DArray, ObjectHypothesisWithPose

from nav_fleet.hsv_detect import detect_balls, load_hsv_config
from nav_fleet.image_io import image_msg_to_rgb

DEFAULT_CONFIG = str(pathlib.Path(__file__).parent.parent / 'config' / 'hsv_gazebo.yaml')


class BallDetector(Node):

    def __init__(self):
        super().__init__('ball_detector')
        self.declare_parameter('hsv_config', DEFAULT_CONFIG)
        self.cfg = load_hsv_config(self.get_parameter('hsv_config').value)
        self.pub = self.create_publisher(Detection2DArray, '/robot_001/detections', 10)
        self.create_subscription(Image, '/robot_001/camera/image_raw', self._image_cb, 10)
        self.get_logger().info(
            f"ball_detector up — colors {sorted(self.cfg['colors'])}, "
            f"range_k {self.cfg['range_k']}")

    def _image_cb(self, msg):
        out = Detection2DArray()
        out.header = msg.header
        for d in detect_balls(image_msg_to_rgb(msg), self.cfg):
            det = Detection2D()
            det.header = msg.header
            hyp = ObjectHypothesisWithPose()
            hyp.hypothesis.class_id = f"{d['color']}_ball"
            hyp.hypothesis.score = min(1.0, d['pixels'] / 500.0)
            hyp.pose.pose.position.x = d['range_m']  # estimated range (m) — see module doc
            det.results.append(hyp)
            det.bbox.center.position.x = d['cx']
            det.bbox.center.position.y = d['cy']
            det.bbox.size_x = float(d['width_px'])
            det.bbox.size_y = float(d['height_px'])
            out.detections.append(det)
        self.pub.publish(out)


def main():
    rclpy.init()
    node = BallDetector()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
```

- [ ] **Step 4: Wire it up.** `setup.py` `console_scripts` gains:

```python
            'ball_detector = nav_fleet.ball_detector:main',
```

`nav2_only_launch.py` gains (alongside `ekf_node`, started with no delay — it just waits
for frames; add `ball_detector` to the `LaunchDescription` list):

```python
    # Mission 2 HSV ball detector — always-on with the nav stack (spec §4): lives on the
    # robot side so HIL runs it on the Jetson while camera frames arrive over DDS.
    # mission_runner simply ignores detections during steps with no reactions.
    ball_detector = Node(
        package='nav_fleet',
        executable='ball_detector',
        name='ball_detector',
        output='screen',
        parameters=[{'use_sim_time': True,
                     'hsv_config': str(PKG / 'config' / 'hsv_gazebo.yaml')}],
    )
```

`Dockerfile` apt list gains (same RUN block, keep alphabetical-ish):

```dockerfile
    ros-jazzy-vision-msgs \
```

`CLAUDE.md` Environment section: extend the `robot-localization` line's pattern with a
new bullet: `ros-jazzy-vision-msgs required on BOTH machines since Session 16 Plan B
(ball_detector) — sudo apt install ros-jazzy-vision-msgs`.

- [ ] **Step 5: Install on the Jetson (it must not wait for the HIL task to discover it)**

```bash
ssh mike@jetson.local "sudo apt-get update && sudo apt-get install -y ros-jazzy-vision-msgs"
```
Expected: installs cleanly. (Jetson may be off — if unreachable, note it as a pending
step in the PR description and do it before Task 11.)

- [ ] **Step 6: Build + live smoke test (Tier-1).** Terminal A:
`colcon build --symlink-install && source install/setup.bash`, then
`ros2 launch src/nav_fleet/launch/sim_launch.py headless:=true`. Terminal B after ~25 s:

```bash
source install/setup.bash
ros2 topic hz /robot_001/detections --window 20
```
Expected: ~10 Hz (one message per camera frame — empty frames still publish).
`ros2 topic echo /robot_001/detections --once` → `detections: []` (no balls in the world;
the green sphere must NOT appear). Tear down with Ctrl+C on the launch, then verify with
the full orphan pattern from CLAUDE.md.

- [ ] **Step 7: Lint + commit**

```bash
flake8 --max-line-length=99 src/nav_fleet/nav_fleet/ball_detector.py src/nav_fleet/nav_fleet/image_io.py
git add src/nav_fleet/nav_fleet/ball_detector.py src/nav_fleet/nav_fleet/image_io.py \
        src/nav_fleet/setup.py src/nav_fleet/launch/nav2_only_launch.py Dockerfile CLAUDE.md
git commit -m "feat(perception): ball_detector node + launch wiring + vision_msgs dep (spec §4)"
```

---

### Task 5: NavRunner interrupt support (goal cancel on trigger)

**Files:**
- Modify: `src/nav_fleet/nav_fleet/nav_runner.py`
- Test: `tests/test_mission_run.py` (live-ROS module; the new test is stub-based and runs
  wherever that file runs — stage-2)

**Interfaces:**
- Consumes: existing `send_goal` machinery.
- Produces: `send_goal(x, y, timeout=90.0, yaw=None, interrupt_cb=None, spin_extra=None)`.
  While waiting on the goal result: spins `spin_extra` (a second Node) so its
  subscriptions are serviced, and polls `interrupt_cb()`; a truthy return cancels the
  Nav2 goal, sets `self.last_interrupt` to that value, and returns False.
  `self.last_interrupt` is reset to None at the start of every `send_goal`. Task 6 relies
  on exactly this contract.

- [ ] **Step 1: Implement** (no pure-unit test can exercise the action client without a
  live server; the live proof is Task 9's red variant — but the interrupt/no-interrupt
  contract at the MissionRunner level gets stub tests in Task 6). In `send_goal`:
  add parameters `interrupt_cb=None, spin_extra=None`; first line of the method body:
  `self.last_interrupt = None` (and add `self.last_interrupt = None` to `__init__`'s
  telemetry block). Replace the result-wait loop:

```python
        result_future = goal_handle.get_result_async()

        deadline = time.time() + timeout
        while time.time() < deadline:
            if result_future.done():
                break
            spin()
            if spin_extra is not None:
                # Service the caller's subscriptions (e.g. mission_runner's detection
                # topic) — send_goal's spin loop only spins THIS node otherwise.
                rclpy.spin_once(spin_extra, timeout_sec=0.0)
            if interrupt_cb is not None:
                hit = interrupt_cb()
                if hit:
                    self.get_logger().warning(f'goal interrupted: {hit!r} — cancelling')
                    self.last_interrupt = hit
                    self._cancel_goal(goal_handle)
                    return self._finish(False, x, y, start_time, steps)

        if not result_future.done():
            self.get_logger().warning('Goal wait timed out')
            return self._finish(False, x, y, start_time, steps)
```

  Add the cancel helper to the class:

```python
    def _cancel_goal(self, goal_handle, timeout_s=5.0):
        """Cancel an in-flight Nav2 goal and wait briefly for the server to confirm —
        the controller stops publishing cmd_vel on cancellation, which IS the stop."""
        fut = goal_handle.cancel_goal_async()
        deadline = time.time() + timeout_s
        while time.time() < deadline and not fut.done():
            rclpy.spin_once(self, timeout_sec=0.1)
        if not fut.done():
            self.get_logger().warning('cancel_goal not confirmed within timeout')
```

- [ ] **Step 2: Verify Mission 1 path unchanged** (no interrupt args → behavior identical):

Run: `python -m pytest tests/ -v --ignore=tests/test_ros2_contracts.py --ignore=tests/test_navigation.py --ignore=tests/test_mission_run.py`
Expected: ALL PASS. Also `flake8 --max-line-length=99 src/nav_fleet/nav_fleet/nav_runner.py`.

- [ ] **Step 3: Commit**

```bash
git add src/nav_fleet/nav_fleet/nav_runner.py
git commit -m "feat(nav): send_goal interrupt_cb + spin_extra — reaction cancel path (spec §4)"
```

---

### Task 6: MissionRunner supervision — detection counting + reaction execution

**Files:**
- Modify: `src/nav_fleet/nav_fleet/mission_runner.py`
- Test: `tests/test_mission_run.py` (stub-based additions)

**Interfaces:**
- Consumes: Task 1 constants (`REACTION_RANGE_M`, `REACTION_FRAMES`), Task 4's detection
  message shape, Task 5's `send_goal(..., interrupt_cb, spin_extra)` + `last_interrupt`.
- Produces: `MissionRunner.reaction_events: list[dict]` — each
  `{'color': str, 'reaction': str, 'truth_xy': (x, y)|None}`; reaction photos named
  `{mission}_reaction_{color}_<ts>.png`; `run_mission` returns True when a triggered
  reaction executes cleanly. `main()` prints one `reaction: <color> -> <reaction>` line
  per event (Task 11's HIL judge greps for this). Tasks 7/9/11 rely on all of these.

- [ ] **Step 1: Write the failing stub tests** — append to `tests/test_mission_run.py`:

```python
def _detection_msg(entries):
    """Fake Detection2DArray via SimpleNamespace — _detection_cb reads attributes only."""
    import types
    dets = []
    for class_id, rng in entries:
        hyp = types.SimpleNamespace(
            hypothesis=types.SimpleNamespace(class_id=class_id),
            pose=types.SimpleNamespace(pose=types.SimpleNamespace(
                position=types.SimpleNamespace(x=rng))))
        dets.append(types.SimpleNamespace(results=[hyp]))
    return types.SimpleNamespace(detections=dets)


def test_detection_cb_triggers_after_consecutive_frames(runner):
    runner._watch = {'reactions': {'red': 'photo_then_stop'}, 'counts': {},
                     'triggered': None}
    for _ in range(2):
        runner._detection_cb(_detection_msg([('red_ball', 0.8)]))
    assert runner._watch['triggered'] is None          # 2 frames < REACTION_FRAMES
    runner._detection_cb(_detection_msg([('red_ball', 0.8)]))
    assert runner._watch['triggered'] == 'red'


def test_detection_cb_gap_resets_count(runner):
    runner._watch = {'reactions': {'red': 'photo_then_stop'}, 'counts': {},
                     'triggered': None}
    runner._detection_cb(_detection_msg([('red_ball', 0.8)]))
    runner._detection_cb(_detection_msg([('red_ball', 0.8)]))
    runner._detection_cb(_detection_msg([]))            # glimpse lost — reset
    runner._detection_cb(_detection_msg([('red_ball', 0.8)]))
    assert runner._watch['triggered'] is None


def test_detection_cb_ignores_far_and_unwatched(runner):
    runner._watch = {'reactions': {'red': 'photo_then_stop'}, 'counts': {},
                     'triggered': None}
    for _ in range(5):
        runner._detection_cb(_detection_msg([('red_ball', 2.5),      # beyond 1.0 m
                                             ('yellow_ball', 0.5)]))  # not watched
    assert runner._watch['triggered'] is None


def test_detection_cb_inactive_outside_reactive_leg(runner):
    runner._watch = None
    runner._detection_cb(_detection_msg([('red_ball', 0.5)]))  # must not raise


def test_reaction_red_stops_and_photographs(runner, monkeypatch):
    """Triggered red: cancel -> photo -> stop; no further navigation; event recorded."""
    goals = []

    class _StubNavInterrupt:
        last_duration_s = None
        last_position_error = None
        last_final_x = 0.0
        last_final_y = 0.0
        last_interrupt = None

        def send_goal(self, x, y, timeout=90.0, yaw=None,
                      interrupt_cb=None, spin_extra=None):
            goals.append((x, y))
            if interrupt_cb is not None:
                runner._watch['triggered'] = 'red'   # simulate the detector firing
                self.last_interrupt = interrupt_cb()
                return False
            return True

    photos = []
    monkeypatch.setattr(runner, 'nav', _StubNavInterrupt())
    monkeypatch.setattr(runner, '_clear_costmaps', lambda *a, **k: None)
    monkeypatch.setattr(runner, 'take_picture', lambda label: photos.append(label) or True)
    import nav_fleet.mission_runner as mr
    monkeypatch.setattr(mr, 'get_ground_truth_xy', lambda *a, **k: (0.0, 2.9))
    runner.reaction_events.clear()
    assert runner.run_mission('mission2') is True
    assert len(goals) == 1                      # no retreat leg on photo_then_stop
    assert photos == ['mission2_reaction_red']
    assert runner.reaction_events == [
        {'color': 'red', 'reaction': 'photo_then_stop', 'truth_xy': (0.0, 2.9)}]


def test_reaction_yellow_photographs_then_drives_home(runner, monkeypatch):
    goals = []

    class _StubNavYellow:
        last_duration_s = None
        last_position_error = None
        last_final_x = 0.0
        last_final_y = 0.0
        last_interrupt = None

        def send_goal(self, x, y, timeout=90.0, yaw=None,
                      interrupt_cb=None, spin_extra=None):
            goals.append((x, y))
            if interrupt_cb is not None:
                runner._watch['triggered'] = 'yellow'
                self.last_interrupt = interrupt_cb()
                return False
            return True                          # the retreat leg (no interrupt_cb)

    monkeypatch.setattr(runner, 'nav', _StubNavYellow())
    monkeypatch.setattr(runner, '_clear_costmaps', lambda *a, **k: None)
    monkeypatch.setattr(runner, 'take_picture', lambda label: True)
    import nav_fleet.mission_runner as mr
    monkeypatch.setattr(mr, 'get_ground_truth_xy', lambda *a, **k: None)
    runner.reaction_events.clear()
    assert runner.run_mission('mission2') is True
    from nav_fleet.semantic_map import SEMANTIC_MAP
    assert goals[-1] == SEMANTIC_MAP['home_base']
    assert runner.reaction_events[0]['color'] == 'yellow'


def test_mission2_no_trigger_completes_normally(runner, monkeypatch):
    monkeypatch.setattr(runner, 'nav', _StubNavOk())
    monkeypatch.setattr(runner, '_clear_costmaps', lambda *a, **k: None)
    runner.reaction_events.clear()
    assert runner.run_mission('mission2') is True
    assert runner.reaction_events == []
```

Note: `_StubNavOk`/`_StubNav` already exist in this file; their `send_goal` signatures
must gain `interrupt_cb=None, spin_extra=None` (add `last_interrupt = None` class attr to
both) — update them in this step.

- [ ] **Step 2: Run to verify failure** (requires live ROS env for the module import; run
  from a sourced terminal WITHOUT the sim — these stub tests don't need Gazebo, but the
  module imports rclpy and the `runner` fixture constructs nodes, so
  `ROS_LOCALHOST_ONLY=1` if the Jetson link is down):

Run: `ROS_LOCALHOST_ONLY=1 python -m pytest tests/test_mission_run.py -v -k "detection or reaction or no_trigger"`
Expected: FAIL — `AttributeError: 'MissionRunner' object has no attribute '_detection_cb'`.

- [ ] **Step 3: Implement in `mission_runner.py`.** Imports:

```python
from nav_fleet.missions import (MISSIONS, REACTION_FRAMES, REACTION_RANGE_M,
                                validate_mission)
from vision_msgs.msg import Detection2DArray
```

`__init__` additions (after the costmap clients):

```python
        self.reaction_events = []
        self._watch = None  # active only during a reactive navigate leg
        self.create_subscription(
            Detection2DArray, '/robot_001/detections', self._detection_cb, 10
        )
```

New methods:

```python
    def _detection_cb(self, msg):
        """Count consecutive in-range frames per watched color (trigger definition A).

        Empty detector frames arrive too (the detector publishes every frame), so a
        lost glimpse resets the count with no timing heuristics needed."""
        if self._watch is None:
            return
        w = self._watch
        in_range = set()
        for det in msg.detections:
            if not det.results:
                continue
            color = det.results[0].hypothesis.class_id.removesuffix('_ball')
            est_range = det.results[0].pose.pose.position.x
            if color in w['reactions'] and est_range <= REACTION_RANGE_M:
                in_range.add(color)
        for color in w['reactions']:
            if color in in_range:
                w['counts'][color] = w['counts'].get(color, 0) + 1
                if w['counts'][color] >= REACTION_FRAMES and w['triggered'] is None:
                    w['triggered'] = color
            else:
                w['counts'][color] = 0

    def _execute_reaction(self, name, reaction, color):
        """Run the declared reaction on existing primitives (spec §2): the goal is
        already cancelled (robot stopped). Photo first — document the hazard — then
        photo_then_home retreats (no reactions during the retreat, by design)."""
        truth = get_ground_truth_xy()  # robot's OWN pose snapshot (None off-sim) — the
        # harness judges the reaction point against it; ball positions stay unknown here.
        self.get_logger().warning(f'[{name}] REACTION: {color} ball -> {reaction}')
        self.reaction_events.append(
            {'color': color, 'reaction': reaction, 'truth_xy': truth})
        ok = self.take_picture(f'{name}_reaction_{color}')
        if reaction == 'photo_then_home':
            self._clear_costmaps()
            hx, hy = SEMANTIC_MAP['home_base']
            ok = self.nav.send_goal(hx, hy, timeout=NAV_TIMEOUT_S, yaw=math.pi / 2) and ok
        return ok
```

In `run_mission`, replace the navigate branch:

```python
            if step.action == 'navigate':
                self._clear_costmaps()  # marks accumulate across the session — clear per leg
                x, y = SEMANTIC_MAP[step.location]
                if step.reactions:
                    self._watch = {'reactions': step.reactions, 'counts': {},
                                   'triggered': None}
                    ok = self.nav.send_goal(
                        x, y, timeout=NAV_TIMEOUT_S, yaw=step.yaw,
                        interrupt_cb=lambda: self._watch['triggered'],
                        spin_extra=self)
                    triggered, self._watch = self._watch['triggered'], None
                    if triggered is not None:
                        return self._execute_reaction(
                            name, step.reactions[triggered], triggered)
                else:
                    ok = self.nav.send_goal(x, y, timeout=NAV_TIMEOUT_S, yaw=step.yaw)
                # FAIL-leg policy (Session 16): a failed/timed-out leg's duration measures
                # the timeout, not the robot — keep it out of the row's aggregate metrics.
                # (An interrupted leg returns False, so it stays out automatically.)
                if ok:
                    if self.nav.last_duration_s is not None:
                        self.nav_durations.append(self.nav.last_duration_s)
                    if self.nav.last_position_error is not None:
                        self.nav_errors.append(self.nav.last_position_error)
```

In `main()`, after the photo printout loop, add the reaction printout (HIL judge greps
this — Task 11):

```python
    for ev in (runner.reaction_events if runner is not None else []):
        print(f"  reaction: {ev['color']} -> {ev['reaction']} at {ev['truth_xy']}")
```

- [ ] **Step 4: Run the stub tests**

Run: `ROS_LOCALHOST_ONLY=1 python -m pytest tests/test_mission_run.py -v -k "detection or reaction or no_trigger or excluded or cleared or none_runner"`
Expected: ALL PASS (new + existing stub tests; the live `test_mission1_completes` needs a
sim — skip it here with `-k`).

- [ ] **Step 5: Lint + commit**

```bash
flake8 --max-line-length=99 src/nav_fleet/nav_fleet/mission_runner.py tests/test_mission_run.py
git add src/nav_fleet/nav_fleet/mission_runner.py tests/test_mission_run.py
git commit -m "feat(mission): reaction supervision — trigger counting + photo_then_stop/home (spec §2, §4)"
```

---

### Task 7: Mission 2 harness — seeded placement, spawn/remove, judges, telemetry

**Files:**
- Create: `tools/mission2_harness.py`
- Test: `tests/test_mission2_harness.py` (pure Python — runs in stage-1)

**Interfaces:**
- Consumes: `SEMANTIC_MAP`, `REACTION_RANGE_M` (Task 1), `log_run(..., seed=)` (Task 3),
  `reaction_events` shape (Task 6).
- Produces (Tasks 9 and 11 call all of these):
  - `solve_placement(variant: str, seed: int) -> (x, y)` — `variant` in
    `('react', 'ignore')`; deterministic per seed.
  - `spawn_ball(color: str, x: float, y: float) -> str` (returns model name),
    `remove_ball(name: str)` — `gz service` subprocess against world `bedroom`.
  - `judge_red(ball_xy, events, photo_paths, truth_a, truth_b) -> list[str]` (empty =
    PASS; entries are human-readable failure reasons), `judge_yellow(ball_xy, events,
    photo_paths, final_truth) -> list[str]`, `judge_ignore(events, final_truth) ->
    list[str]`.
  - `log_variant_row(variant, seed, ok, runner)` — writes the `mission2_<variant>`
    telemetry row with the seed.
  - CLI: `python -m tools.mission2_harness spawn|remove|judge-ignore ...` (Task 11).
  - Band constants: `BAND_NEAR = 0.3`, `BAND_FAR = 1.3`, `HOME_TOL = 0.3`,
    `SPHERE_NEAR = 0.25`, `SPHERE_FAR = 0.75`, `STATIONARY_TOL = 0.05`.

- [ ] **Step 1: Write the failing tests** — create `tests/test_mission2_harness.py`:

```python
"""Unit tests for the Mission 2 harness geometry — pure Python (stage-1)."""
import math

import pytest


def _route_min_dist(x, y):
    from tools.mission2_harness import _route_points
    return min(math.hypot(x - rx, y - ry) for rx, ry in _route_points())


def test_placement_deterministic_per_seed():
    from tools.mission2_harness import solve_placement
    assert solve_placement('react', 42) == solve_placement('react', 42)
    assert solve_placement('ignore', 42) == solve_placement('ignore', 42)
    assert solve_placement('react', 42) != solve_placement('react', 43)


def test_react_placement_sits_on_the_approach_corridor():
    from tools.mission2_harness import solve_placement
    for seed in range(20):
        x, y = solve_placement('react', seed)
        assert _route_min_dist(x, y) <= 0.2         # on/next to the route line
        assert 2.4 <= y <= 3.2                       # between doorway and sphere approach


def test_ignore_placement_stays_outside_reaction_envelope():
    from nav_fleet.missions import REACTION_RANGE_M
    from tools.mission2_harness import solve_placement
    for seed in range(20):
        x, y = solve_placement('ignore', seed)
        assert _route_min_dist(x, y) >= REACTION_RANGE_M + 0.5


def test_judge_red_passes_good_run():
    from tools.mission2_harness import judge_red
    events = [{'color': 'red', 'reaction': 'photo_then_stop', 'truth_xy': (0.0, 2.4)}]
    fails = judge_red(ball_xy=(0.0, 3.0), events=events,
                      photo_paths=['reports/photos/x.png'],
                      truth_a=(0.0, 2.4), truth_b=(0.0, 2.41))
    assert fails == []


def test_judge_red_fails_outside_band_and_moving():
    from tools.mission2_harness import judge_red
    events = [{'color': 'red', 'reaction': 'photo_then_stop', 'truth_xy': (0.0, 0.5)}]
    fails = judge_red(ball_xy=(0.0, 3.0), events=events, photo_paths=['p.png'],
                      truth_a=(0.0, 0.5), truth_b=(0.0, 0.8))
    assert any('band' in f for f in fails)
    assert any('stationary' in f for f in fails)


def test_judge_red_fails_without_event_or_photo():
    from tools.mission2_harness import judge_red
    fails = judge_red(ball_xy=(0.0, 3.0), events=[], photo_paths=[],
                      truth_a=(0.0, 2.4), truth_b=(0.0, 2.4))
    assert any('no red reaction' in f for f in fails)
    assert any('photo' in f for f in fails)


def test_judge_yellow_checks_reaction_point_and_home():
    from tools.mission2_harness import judge_yellow
    events = [{'color': 'yellow', 'reaction': 'photo_then_home', 'truth_xy': (0.0, 2.4)}]
    ok = judge_yellow(ball_xy=(0.0, 3.0), events=events, photo_paths=['p.png'],
                      final_truth=(-1.2, 1.25))
    assert ok == []
    far = judge_yellow(ball_xy=(0.0, 3.0), events=events, photo_paths=['p.png'],
                       final_truth=(0.0, 3.0))
    assert any('home' in f for f in far)


def test_judge_ignore_zero_reactions_and_sphere_band():
    from tools.mission2_harness import judge_ignore
    assert judge_ignore(events=[], final_truth=(0.0, 3.2)) == []
    fails = judge_ignore(
        events=[{'color': 'red', 'reaction': 'photo_then_stop', 'truth_xy': None}],
        final_truth=(0.0, 1.0))
    assert any('reaction' in f for f in fails)
    assert any('sphere' in f for f in fails)
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_mission2_harness.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tools.mission2_harness'`.

- [ ] **Step 3: Create `tools/mission2_harness.py`:**

```python
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
```

- [ ] **Step 4: Run the tests**

Run: `python -m pytest tests/test_mission2_harness.py -v`
Expected: 8 PASS. Then the full pure suite (Task 1 Step 4 command) — ALL PASS.

- [ ] **Step 5: Lint + commit**

```bash
flake8 --max-line-length=99 tools/mission2_harness.py tests/test_mission2_harness.py
git add tools/mission2_harness.py tests/test_mission2_harness.py
git commit -m "feat(harness): seeded ball placement + gz spawn + ground-truth judges (spec §3, §5)"
```

---

### Task 8: Live calibration — measure `range_k`, sanity-check HSV bands

**Files:**
- Create: `tools/calibrate_ball_range.py`
- Modify: `src/nav_fleet/config/hsv_gazebo.yaml` (record the measured `range_k`)

**Interfaces:**
- Consumes: `spawn_ball`/`remove_ball` (Task 7), `detect_balls`/`load_hsv_config`
  (Task 2), `image_msg_to_rgb` (Task 4), `get_ground_truth_xy`.
- Produces: the measured `range_k` frozen into `hsv_gazebo.yaml`; console evidence that
  red AND yellow detect reliably at 0.5–2.0 m under Gazebo lighting.

- [ ] **Step 1: Create `tools/calibrate_ball_range.py`:**

```python
"""One-time size->range calibration against Gazebo ground truth (spec §6).

With the sim up (robot parked at spawn, facing north), spawns a ball at known camera
distances directly ahead, measures the detected width_px per distance, and reports the
fitted range_k (range_m = range_k / width_px). Paste the reported value into
src/nav_fleet/config/hsv_gazebo.yaml. Run per color to sanity-check both HSV bands.

Usage (repo root, sim running):  python -m tools.calibrate_ball_range [--color red]
"""
import argparse
import math
import sys
import time

sys.path.insert(0, 'src/nav_fleet')

import rclpy  # noqa: E402
from rclpy.node import Node  # noqa: E402
from sensor_msgs.msg import Image  # noqa: E402

from nav_fleet.ground_truth import get_ground_truth_xy  # noqa: E402
from nav_fleet.hsv_detect import detect_balls, load_hsv_config  # noqa: E402
from nav_fleet.image_io import image_msg_to_rgb  # noqa: E402
from tools.mission2_harness import remove_ball, spawn_ball  # noqa: E402

CAMERA_FORWARD_OFFSET = 0.175   # camera_joint x in the URDF: base centre -> lens
DISTANCES = (0.5, 0.75, 1.0, 1.5, 2.0)


class _Grab(Node):
    def __init__(self):
        super().__init__('calibration_grabber')
        self.frame = None
        self.create_subscription(Image, '/robot_001/camera/image_raw', self._cb, 10)

    def _cb(self, msg):
        self.frame = msg

    def grab(self, timeout=10.0):
        self.frame = None
        deadline = time.time() + timeout
        while self.frame is None and time.time() < deadline:
            rclpy.spin_once(self, timeout_sec=0.1)
        return self.frame


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--color', choices=['red', 'yellow'], default='red')
    args = parser.parse_args()

    cfg = load_hsv_config('src/nav_fleet/config/hsv_gazebo.yaml')
    truth = get_ground_truth_xy()
    assert truth is not None, 'sim not up / no ground truth'
    rx, ry = truth
    print(f'robot at ({rx:.3f}, {ry:.3f}), facing north — camera {CAMERA_FORWARD_OFFSET}'
          f' m ahead of base centre')

    rclpy.init()
    grabber = _Grab()
    ks = []
    for d_cam in DISTANCES:
        # ball placed d_cam ahead of the LENS along +y (robot faces north at spawn)
        name = spawn_ball(args.color, rx, ry + CAMERA_FORWARD_OFFSET + d_cam)
        time.sleep(1.0)  # let the render settle
        try:
            frame = grabber.grab()
            assert frame is not None, 'no camera frame'
            dets = [d for d in detect_balls(image_msg_to_rgb(frame), cfg)
                    if d['color'] == args.color]
            if not dets:
                print(f'  d={d_cam:.2f} m: NOT DETECTED — fix the HSV band first')
                continue
            width = dets[0]['width_px']
            ks.append(d_cam * width)
            print(f"  d={d_cam:.2f} m: width={width} px, pixels={dets[0]['pixels']}"
                  f' -> k={d_cam * width:.1f}')
        finally:
            remove_ball(name)
            time.sleep(0.5)
    rclpy.try_shutdown()
    if ks:
        mean_k = sum(ks) / len(ks)
        spread = max(ks) - min(ks)
        print(f'\nmeasured range_k = {mean_k:.1f} (spread {spread:.1f} across '
              f'{len(ks)} samples)\n-> paste into src/nav_fleet/config/hsv_gazebo.yaml')
    else:
        print('\nNO SAMPLES — HSV thresholds need tuning before calibration')


if __name__ == '__main__':
    main()
```

- [ ] **Step 2: Run it live (Tier-1).** Terminal A: build + launch sim (Task 4 Step 6
  pattern). Terminal B (repo root, overlay sourced):

```bash
python -m tools.calibrate_ball_range --color red
python -m tools.calibrate_ball_range --color yellow
```
Expected: both colors detected at ALL five distances; a `measured range_k = ...` line per
run with spread < ~15% of the mean. If a color is NOT DETECTED: save a frame
(`ros2 topic echo` won't help — add a temporary PNG dump via `image_msg_to_png`), inspect
the actual rendered RGB, adjust that color's `h`/`s_min`/`v_min` band in
`hsv_gazebo.yaml`, rerun. If width saturates near 0.5 m (ball taller than frame), drop
that sample — the trigger operates at ~1 m.

- [ ] **Step 3: Record the measured `range_k`** in `hsv_gazebo.yaml`, replacing 47.7 and
  updating its comment to `# measured via tools/calibrate_ball_range 2026-MM-DD (analytic
  estimate was 47.7)`. Then verify the trigger geometry once: with the sim still up,
  spawn a red ball ~0.9 m ahead of the camera, confirm
  `ros2 topic echo /robot_001/detections --once` shows `position.x` ≈ 0.9 ± 0.1.
  Tear down (full orphan pattern).

- [ ] **Step 4: Re-run pure tests (range_k change must not break the fixed-expectation
  test — it asserts `range_m == range_k / width`, which adapts automatically):**

Run: `python -m pytest tests/test_hsv_detect.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/calibrate_ball_range.py src/nav_fleet/config/hsv_gazebo.yaml
git commit -m "feat(perception): size->range calibration tool + measured range_k (spec §6)"
```

---

### Task 9: Integration tests — the three variants, live (Tier-1 proof)

**Files:**
- Create: `tests/test_mission2.py`
- Test: itself (live — Gazebo + Nav2 required)

**Interfaces:**
- Consumes: everything above. Seeds: fresh random per run, overridable via
  `MISSION2_SEED_RED` / `MISSION2_SEED_YELLOW` / `MISSION2_SEED_IGNORE` env vars for
  exact reproduction (spec §5).
- Produces: the stage-2 CI test surface (Task 10 wires it in).

- [ ] **Step 1: Create `tests/test_mission2.py`:**

```python
"""Mission 2 integration tests — the three seeded variants (spec §3).

Requires live Gazebo + Nav2 (ros2 launch src/nav_fleet/launch/sim_launch.py). Ignored in
stage-1-quality — imports rclpy at module level (see CLAUDE.md Gotchas; bitten twice).

Seeds are fresh-random per run and PRINTED + logged to telemetry (seed column): a CI
failure reproduces exactly by re-running with MISSION2_SEED_<VARIANT>=<printed seed>.
Test order matters: each test's autouse teardown drives the robot home for the next one.
"""
import math
import os
import pathlib
import random
import time

import pytest
import rclpy  # noqa: F401 — module-level import ensures collection fails without ROS2

from nav_fleet.ground_truth import get_ground_truth_xy
from nav_fleet.mission_runner import MissionRunner
from nav_fleet.semantic_map import SEMANTIC_MAP
from tools.mission2_harness import (judge_ignore, judge_red, judge_yellow,
                                    log_variant_row, remove_ball, solve_placement,
                                    spawn_ball)


def _seed(variant):
    env = os.environ.get(f'MISSION2_SEED_{variant.upper()}')
    seed = int(env) if env else random.SystemRandom().randrange(2 ** 31)
    print(f'\n[mission2_{variant}] SEED={seed}  '
          f'(reproduce: MISSION2_SEED_{variant.upper()}={seed})')
    return seed


@pytest.fixture(scope='session', autouse=True)
def _module_ros(ros_context):
    yield


@pytest.fixture(scope='session')
def runner(ros_context):
    node = MissionRunner()
    yield node
    node.nav.destroy_node()
    node.destroy_node()


@pytest.fixture(autouse=True)
def _drive_home_after(runner):
    """Cleanup, not judgment: park the robot at home_base for the next variant."""
    yield
    runner.reaction_events.clear()
    runner._clear_costmaps()
    hx, hy = SEMANTIC_MAP['home_base']
    runner.nav.send_goal(hx, hy, timeout=90.0, yaw=math.pi / 2)


@pytest.mark.timeout(300)
def test_mission2_red_stops_at_the_ball(runner):
    seed = _seed('red')
    ball_xy = solve_placement('react', seed)
    name = spawn_ball('red', *ball_xy)
    fails = None
    try:
        runner.run_mission('mission2')
        truth_a = get_ground_truth_xy()
        time.sleep(2.0)
        truth_b = get_ground_truth_xy()
        photos = [p for p in runner.photo_paths if 'reaction_red' in p]
        fails = judge_red(ball_xy, runner.reaction_events, photos, truth_a, truth_b)
        for p in photos:
            assert pathlib.Path(p).exists()
    finally:
        remove_ball(name)
        log_variant_row('red', seed, ok=(fails == []), runner=runner)
    assert fails == [], f'seed {seed}: ' + '; '.join(fails)


@pytest.mark.timeout(300)
def test_mission2_yellow_photographs_and_retreats(runner):
    seed = _seed('yellow')
    ball_xy = solve_placement('react', seed)
    name = spawn_ball('yellow', *ball_xy)
    fails = None
    try:
        runner.run_mission('mission2')
        final_truth = get_ground_truth_xy()
        photos = [p for p in runner.photo_paths if 'reaction_yellow' in p]
        fails = judge_yellow(ball_xy, runner.reaction_events, photos, final_truth)
    finally:
        remove_ball(name)
        log_variant_row('yellow', seed, ok=(fails == []), runner=runner)
    assert fails == [], f'seed {seed}: ' + '; '.join(fails)


@pytest.mark.timeout(300)
def test_mission2_ignorable_ball_is_ignored(runner):
    seed = _seed('ignore')
    ball_xy = solve_placement('ignore', seed)
    name = spawn_ball('red', *ball_xy)   # red — the scarier color must ALSO be ignored
    fails = None
    try:
        ok = runner.run_mission('mission2')
        final_truth = get_ground_truth_xy()
        fails = judge_ignore(runner.reaction_events, final_truth)
        if not ok:
            fails = (fails or []) + ['mission itself reported FAIL']
    finally:
        remove_ball(name)
        log_variant_row('ignore', seed, ok=(fails == []), runner=runner)
    assert fails == [], f'seed {seed}: ' + '; '.join(fails)
```

- [ ] **Step 2: Run live (Tier-1), full sequence.** Terminal A: build + launch sim.
  Terminal B:

```bash
source install/setup.bash
python -m pytest tests/test_mission2.py -v
```
Expected: 3 PASS, three `SEED=` lines printed. **This step WILL surface real tuning
issues** (trigger too eager/lazy, band edges, home tolerance): debug with the printed
seed (`MISSION2_SEED_RED=<seed> python -m pytest ... -k red`), adjust ONLY config/band
constants (never the ball size), and record what changed. Run the file **3 times in a
row** (fresh seeds each time) before calling it stable.

- [ ] **Step 3: Verify telemetry rows landed**

```bash
python - <<'EOF'
import sqlite3
conn = sqlite3.connect('reports/fleet_runs.db')
for r in conn.execute("SELECT scenario, result, seed FROM runs WHERE scenario LIKE"
                      " 'mission2%' ORDER BY id DESC LIMIT 6"):
    print(r)
EOF
python tools/validate_telemetry.py
```
Expected: `mission2_red/_yellow/_ignore` rows with integer seeds; validation all green.

- [ ] **Step 4: Lint + commit**

```bash
flake8 --max-line-length=99 tests/test_mission2.py
git add tests/test_mission2.py
git commit -m "test(mission2): live 3-variant integration tests, seeded + ground-truth judged (spec §3)"
```

---

### Task 10: CI stage-2 wiring + docs (the twice-bitten ignore rule)

**Files:**
- Modify: `.github/workflows/ci.yml` (stage-1 ignore list at ~line 116; stage-2 pytest at
  ~line 247)
- Modify: `CLAUDE.md` (local pytest command + Gotchas list mention)
- Modify: `Release1Todo.md` (reconcile Piece 2 checkboxes with what actually shipped)

- [ ] **Step 1: `ci.yml` stage-1-quality** — add to the pytest ignore block:

```yaml
            --ignore=tests/test_mission2.py \
```

**stage-2-gazebo** — extend the test line:

```yaml
          python -m pytest tests/test_navigation.py tests/test_mission_run.py \
            tests/test_mission2.py -v --timeout=300
```

(`--timeout` goes from 120 to 300: the yellow variant is a two-leg drive; per-test
timeout, not job — the job's `timeout-minutes: 30` still bounds the whole stage.)

- [ ] **Step 2: `CLAUDE.md`** — add `--ignore=tests/test_mission2.py` to BOTH local pytest
  command blocks (Development workflow + Key Commands), and extend the Gotchas line that
  lists live-ROS test files to include `tests/test_mission2.py`.

- [ ] **Step 3: `Release1Todo.md` Piece 2** — under the 2026-07-16 spec-pointer blockquote,
  tick/annotate the checkboxes this plan supersedes or implements: HSV detector node
  (implemented — vision_msgs contract, not custom bearing msg), red-ball supervisor
  (implemented as reactive step in mission_runner, not a separate node), yellow-ball
  costmap keepout (**superseded** — photo_then_home per approved spec), mission framework
  groundwork (partially: reactions validation shipped; photo-freshness stamp gate NOT in
  scope this plan), sim tier scripted spawn (implemented — harness-owned, seeded),
  real-camera tier + auto-exposure + clock-domain items (deferred to the webcam follow-up
  plan per spec §9). Keep the checkbox text, add dated annotations — same style the file
  already uses.

- [ ] **Step 4: Full local gate before push** (Tier-1 discipline):

```bash
python -m pytest tests/ -v --ignore=tests/test_ros2_contracts.py \
  --ignore=tests/test_navigation.py --ignore=tests/test_mission_run.py \
  --ignore=tests/test_mission2.py
flake8 --max-line-length=99 src/nav_fleet/nav_fleet/ tools/mission2_harness.py \
  tools/calibrate_ball_range.py tests/test_mission2.py tests/test_hsv_detect.py \
  tests/test_mission2_harness.py
```
Expected: all pass, lint clean.

- [ ] **Step 5: Commit, push branch, open PR**

```bash
git add .github/workflows/ci.yml CLAUDE.md Release1Todo.md
git commit -m "ci(stage-2): run mission2 variants; stage-1 ignores the live test file (twice-bitten rule)"
git push -u origin mission2-camera-reactive
gh pr create --title "Mission 2: camera-reactive navigation (Plan B)" \
  --body "Implements docs/superpowers/specs/2026-07-16-mission2-design.md ..."
```

Watch the PR run (`gh run watch`). Expected: all sim-path jobs green, including the three
mission2 variants in stage-2 and the arm64 image build (vision_msgs layer). Investigate
any red WITH the printed seed before rerunning. Merge per repo convention (check
`git log --merges` for the current style). **Mission 2 is now in stage-2 with fresh seeds
every push — let it soak while Task 11 proceeds.**

---

### Task 11: HIL rung 1 — `mission2_ignore` into stage-4-hil

**Files:**
- Modify: `scripts/hil_stage.sh`
- Modify: `.github/workflows/ci.yml` (stage-4 job calls the new step)

**Interfaces:**
- Consumes: harness CLI (Task 7), `mission_runner` CLI printing `reaction:` lines
  (Task 6), the existing hil_stage.sh mission/verify machinery (read the whole script
  before editing — its subcommand pattern, `$STATE_DIR`, docker invocation and teardown
  are the template).
- Produces: stage-4 runs Mission 1 (unchanged) THEN mission2_ignore: workstation spawns
  the seeded ball → Jetson runs `python3 -m nav_fleet.mission_runner mission2` inside the
  arm64 container → workstation judges (grep reactions + ground truth) and removes the
  ball. Graduation per spec §8: NO formal green-count gate; add red (Task 12) once this
  rung looks stable across normal CI traffic.

- [ ] **Step 1: Read `scripts/hil_stage.sh` end to end.** Map its subcommands and where
  mission1 is invoked (line ~118 `run_mission`), how mission output is captured, and the
  `always()` teardown. Mirror that structure exactly.

- [ ] **Step 2: Add a `mission2-ignore` subcommand** to `hil_stage.sh` following the
  existing `run_mission` pattern. Shape (adapt variable names to what the script actually
  uses — this is the logic contract, written against the script's own conventions):

```bash
run_mission2_ignore() {
  echo '=== [mission2] ignore variant on the Jetson (budget 300s) ==='
  SEED=$(( RANDOM * 32768 + RANDOM ))
  echo "mission2_ignore SEED=${SEED}"
  # Workstation side: solve placement + spawn (Gazebo runs here)
  BALL_JSON=$(python3 -m tools.mission2_harness spawn --variant ignore --color red \
              --seed "${SEED}")
  echo "ball: ${BALL_JSON}"
  BALL_NAME=$(python3 -c "import json,sys; print(json.loads(sys.argv[1])['name'])" \
              "${BALL_JSON}")
  # Jetson side: same docker-run shape as mission1, different mission + log file
  ...docker run ... 'python3 -m nav_fleet.mission_runner mission2' \
      | tee "${STATE_DIR}/mission2.out"
  # Workstation side: judge (reaction grep + ground-truth sphere band), then clean up
  python3 -m tools.mission2_harness judge-ignore \
      --mission-log "${STATE_DIR}/mission2.out" --seed "${SEED}"
  JUDGE_RC=$?
  python3 -m tools.mission2_harness remove "${BALL_NAME}" || true
  return ${JUDGE_RC}
}
```

  Also extend the script's teardown/cleanup path to `remove ball_red || true` so an
  aborted run never leaves a ball in the world for the next job. Telemetry: the row is
  written on the Jetson by mission_runner (scenario `mission2`, no seed — self-report);
  the judged verdict gates the JOB. Log the seed prominently — the workstation-side
  `log_variant_row` equivalent for HIL rows moves to Task 12 if wanted (note it in the
  PR; rung 1 keeps the diff minimal).

- [ ] **Step 3: Wire into `ci.yml` stage-4** — add a step after the mission1 step, same
  env/pattern:

```yaml
      - name: Mission 2 ignore variant (HIL rung 1 — spec §8 graduation ladder)
        run: bash scripts/hil_stage.sh mission2-ignore
```

(Match how the existing steps invoke the script's subcommands — read the job first.)

- [ ] **Step 4: Test locally against the REAL Jetson before pushing** (this is exactly
  what `hil_stage.sh` exists for — it runs outside CI): Jetson on, sim up on the
  workstation, then run the script's subcommand sequence manually (its header documents
  the order: power-mode → ... → mission2-ignore → verify → teardown).
Expected: seed printed, ball spawned, Jetson mission completes with zero `reaction:`
lines, judge prints `mission2_ignore seed=...: PASS`, ball removed.

- [ ] **Step 5: Commit + push + watch stage-4 green**

```bash
flake8 --max-line-length=99 tools/mission2_harness.py
git add scripts/hil_stage.sh .github/workflows/ci.yml
git commit -m "feat(ci): stage-4-hil runs mission2_ignore — HIL graduation rung 1 (spec §8)"
git push && gh run watch
```

---

### Task 12: HIL rungs 2–3 — red, then yellow, into stage-4 + closeout

**Files:**
- Modify: `scripts/hil_stage.sh`, `.github/workflows/ci.yml`
- Modify: `tools/mission2_harness.py` (judge-red / judge-yellow CLI subcommands)
- Modify: `Release1Todo.md`, `docs/superpowers/specs/2026-07-16-mission2-design.md`
  (status note), memory/progress ledger per session habit

**Interfaces:**
- Consumes: everything; rung 1 stable across normal CI traffic (spec §8: no formal count
  — judgment call with Mike, several green runs on main is the bar).
- Produces: all three variants running in stage-4; Release 1's Mission 2 scope complete.

- [ ] **Step 1: Extend the harness CLI with `judge-red` and `judge-yellow`** following the
  `judge-ignore` pattern: parse `reaction:` lines from the mission log (color, reaction,
  and the printed `truth_xy` tuple — extend the `main()` reaction print parsing to
  recover the tuple with `ast.literal_eval` of the text after ` at `), take
  `--ball-x/--ball-y` from the spawn JSON, take two ground-truth samples 2 s apart
  in-process for the stationary check (red), and reuse `judge_red`/`judge_yellow`
  verbatim. Photo check: `--photo-glob "reports/photos/mission2_reaction_red_*.png"`
  against the bind-mounted photos dir the mission1 verify step already checks. Unit-test
  the new log-parsing function in `tests/test_mission2_harness.py` (pure).

- [ ] **Step 2: Add `mission2-red` and `mission2-yellow` subcommands** to `hil_stage.sh`
  (clone the rung-1 shape; `--variant react --color red|yellow`; judge with the matching
  subcommand). Wire both as stage-4 steps. Note the wall-time cost in the step names —
  if stage-4 exceeds its `timeout-minutes`, raise that value in the same commit and
  record the new expected band in the job summary step.

- [ ] **Step 3: Manual HIL proof of both rungs** (Task 11 Step 4 pattern), then commit +
  push + watch stage-4 green:

```bash
git add scripts/hil_stage.sh .github/workflows/ci.yml tools/mission2_harness.py \
        tests/test_mission2_harness.py
git commit -m "feat(ci): stage-4-hil runs mission2 red + yellow — HIL rungs 2-3 (spec §8)"
git push && gh run watch
```

- [ ] **Step 4: Closeout.** Release1Todo: tick Piece 2's implemented items with dated
  annotations; add the webcam follow-up as its own labeled block (spec §9 pointer). Spec:
  append a one-line `**Implemented:** <date>, PR #N` note under Status. Update the
  project memory per session habit. Confirm with Mike before merging anything he said he
  wants eyes on (GUI observation policy applies to any run he watched).

---

## Self-Review (done at write time)

- **Spec coverage:** §1–§2 → Tasks 1, 6. §3 bands/judges → Tasks 7, 9. §4 architecture →
  Tasks 2, 4, 5, 6. §5 placement/seed policy → Tasks 7, 9 (fresh seed per run + env
  override). §6 geometry/calibration → Task 8. §7 telemetry → Tasks 3, 7. §8 CI/HIL
  ladder → Tasks 10, 11, 12. §9 webcam follow-up → explicitly out of scope (Task 10/12
  annotate Release1Todo). §10 future framework → no implementation required.
- **Known open risk (deliberate):** Task 9 Step 2 is where trigger/band tuning happens
  against reality; the plan freezes initial numbers and names the knobs rather than
  pretending they're final. HIL rows for mission2 variants carry no seed in rung 1
  (noted in Task 11) — acceptable, judged verdict gates the job.
- **Type consistency check:** `reactions` dict shape, `reaction_events` dict keys,
  `send_goal(..., interrupt_cb, spin_extra)`, `detect_balls` return keys, and judge
  signatures are each defined once and used identically across Tasks 1→6→7→9→11.
