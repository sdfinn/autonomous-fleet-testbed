# Session 15 — Mission 1 + Gazebo HIL Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the mission framework and Mission 1 (navigate to doorway center → take a picture → return to start), prove it on x86 Gazebo (Tier 1), then run it hardware-in-the-loop with Nav2 + the mission executor on the real Jetson Orin Nano against Gazebo on the workstation, and produce the CI-stage design doc.

**Architecture:** Missions are data (waypoint names + action primitives) in a pure-Python module, executed by a `MissionRunner` ROS2 node that composes the existing `NavRunner` for navigation and adds a `take_picture` primitive. The existing `sim_launch.py` is split into `sim_only_launch.py` (Gazebo side) and `nav2_only_launch.py` (robot-brain side) so the two halves can run on different machines for HIL; `sim_launch.py` becomes a thin composition of both, preserving today's single-machine behavior.

**Tech Stack:** ROS2 Jazzy, Nav2 (`nav2_bringup`), Gazebo Harmonic (`gz sim -s`), CycloneDDS (cross-machine DDS), Python (numpy + Pillow for PNG writing), pytest, SQLite telemetry (`tools/telemetry_logger.log_run`).

**Spec:** `docs/superpowers/specs/2026-07-10-session15-gazebo-hil-mission1-design.md` (Approved; mission numbering revised 2026-07-11 — Mission 1 = navigate/photograph/return).

## Global Constraints

- All new `src/nav_fleet/nav_fleet/*.py` files: flake8-clean at `--max-line-length=99` (stage-1 lints this) and carry the same Apache-2.0 header block as `nav_runner.py`.
- Any test file that imports `rclpy` (directly or transitively) at module level MUST be added to `stage-1-quality`'s pytest `--ignore` list in `.github/workflows/ci.yml` **in the same commit that creates it**. This has bitten twice (see CLAUDE.md Gotchas).
- Pure-Python modules (`semantic_map.py`, `missions.py`, `image_io.py`) must NOT import `rclpy`, `sensor_msgs`, or any ROS package — they must be importable on a bare `ubuntu-latest` runner.
- Run Python tools from the repo root with `python -m ...` (same reason as the `tools/agentic_loop.py` gotcha: plain-script invocation breaks `tools.*`/`nav_fleet` imports).
- Gazebo: always `gz sim -s -r` (server only). GUI crashes on this machine. View separately with `gz sim -g`.
- Kill sim sessions with Ctrl+C on the foreground `ros2 launch` process — never chained `pkill`s.
- After `colcon build` in a terminal, `source install/setup.bash` in that same terminal (new terminals auto-source via `.bashrc`).
- This plan implements the bare-metal prototype and the CI **design doc** only. Do not implement a new CI stage/job (spec: "design, not necessarily implement").
- Editing `requirements-ci.txt` (Task 3 adds Pillow) invalidates the Dockerfile pip/colcon layers → the next `stage-3-arm64` run will be a non-cached ~10 min native Jetson build. Expected, not a regression.
- Commit messages: conventional-commit style matching repo history (`feat:`, `fix:`, `ci:`, `docs:`, `test:`), ending with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- The working tree starts with uncommitted Session-15 doc updates (`BLUEPRINT.md`, `CLAUDE.md`, `Release1Todo.md`, spec rename). Commit those first as `docs(session-15): record approved design + mission renumbering` before starting Task 1, so task commits stay clean.

## File Structure

| File | Status | Responsibility |
|---|---|---|
| `src/nav_fleet/nav_fleet/semantic_map.py` | Create | Named world locations (pure data, no ROS). Canonical home of `SEMANTIC_MAP`, moved out of `tools/agentic_loop.py`. Adds `doorway_center`. |
| `src/nav_fleet/nav_fleet/missions.py` | Create | Mission definitions as data (`MissionStep`, `MISSIONS`), validation, yaw→quaternion helper. Pure Python. |
| `src/nav_fleet/nav_fleet/image_io.py` | Create | `sensor_msgs/Image`-shaped message → PNG file (duck-typed; numpy + Pillow only). |
| `src/nav_fleet/nav_fleet/mission_runner.py` | Create | ROS2 mission executor node: iterates mission steps, drives `NavRunner`, `take_picture` primitive, telemetry row per mission. CLI entry point. |
| `src/nav_fleet/nav_fleet/nav_runner.py` | Modify | `send_goal()` gains optional `yaw` (Nav2 enforces final heading — `yaw_goal_tolerance: 0.5`). |
| `src/nav_fleet/launch/sim_only_launch.py` | Create | Gazebo + spawn + bridge + RSP + lidar frame bridge — the "simulated world" half (workstation side in HIL). |
| `src/nav_fleet/launch/nav2_only_launch.py` | Create | Nav2 bringup only — the "robot brain" half (Jetson side in HIL). `start_delay` launch arg. |
| `src/nav_fleet/launch/sim_launch.py` | Modify | Becomes a thin include of the two halves (single-machine behavior unchanged). |
| `tools/agentic_loop.py` | Modify | Imports `SEMANTIC_MAP` from `nav_fleet.semantic_map` (DRY — one map, two consumers). |
| `tests/conftest.py` | Modify | Adds `src/nav_fleet` to `sys.path` so pure `nav_fleet.*` modules import without a colcon overlay (stage-1 runner has no ROS2). |
| `tests/test_missions.py` | Create | Pure unit tests: semantic map, mission validation, quaternion helper, PNG writer. Runs in stage-1. |
| `tests/test_mission_run.py` | Create | Live integration test (Gazebo + Nav2 required): Mission 1 end-to-end. Ignored in stage-1. |
| `.github/workflows/ci.yml` | Modify | One line: `--ignore=tests/test_mission_run.py` in stage-1. Nothing else. |
| `requirements-ci.txt` | Modify | Add `pillow>=10.0`. |
| `Mission1HILSession15.md` | Create | HIL runbook (Jetson setup, network config, run procedure, results) — same pattern as `JetsonInstallSession14.md`. |
| `docs/session15-hil-ci-stage-design.md` | Create | CI-stage design: orchestration, success/failure/timeout/teardown, job naming. Design only. |
| `Release1Todo.md`, `BLUEPRINT.md`, `CLAUDE.md` | Modify | Closeout: checkboxes, decision log, new commands/gotchas. |

**Doorway center derivation (used in Task 1):** in `worlds/bedroom_simple.sdf`, the bedroom's south wall is `Wall_South_W` (center x=−1.9686, length 1.274 → east edge x=−1.3316, at y=2.3887) and `Wall_South_E` (center x=0.4914, length 2.217 → west edge x=−0.6171, at y=2.4706). The doorway is the gap between them: x ∈ [−1.3316, −0.6171] → center **(−0.974, 2.430)**, width ≈ 0.71 m. This sits on BR-01's proven NNE route from spawn to the bedroom.

---

### Task 1: Extract `SEMANTIC_MAP` into `nav_fleet`, add `doorway_center`

**Files:**
- Create: `src/nav_fleet/nav_fleet/semantic_map.py`
- Modify: `tests/conftest.py`
- Modify: `tools/agentic_loop.py:16-28`
- Test: `tests/test_missions.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `nav_fleet.semantic_map.SEMANTIC_MAP: dict[str, tuple[float, float]]` — named map-frame locations. Keys used later: `'doorway_center'`, `'home_base'`.

- [ ] **Step 1: Add the `sys.path` shim to `tests/conftest.py`**

Append to the existing imports at the top of `tests/conftest.py` (keep the existing fixtures untouched):

```python
"""Pytest fixtures for fleet testbed tests."""
import pathlib
import sys

import pytest

# Make `nav_fleet` importable without a colcon build/overlay — stage-1-quality runs on a
# bare ubuntu-latest runner with no ROS2 workspace. Harmless when the overlay IS sourced:
# --symlink-install points the installed package at these same source files.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / 'src' / 'nav_fleet'))
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_missions.py`:

```python
"""Unit tests for the mission framework — pure Python, no ROS2 required (runs in stage-1)."""


def test_semantic_map_has_doorway_center():
    from nav_fleet.semantic_map import SEMANTIC_MAP
    # Doorway = gap between Wall_South_W and Wall_South_E in bedroom_simple.sdf
    assert SEMANTIC_MAP['doorway_center'] == (-0.974, 2.430)


def test_semantic_map_keeps_existing_locations():
    from nav_fleet.semantic_map import SEMANTIC_MAP
    assert SEMANTIC_MAP['home_base'] == (-1.276, 1.2)
    assert SEMANTIC_MAP['bedroom_goal'] == (0.0, 3.7)
    assert len(SEMANTIC_MAP) == 9  # 8 original + doorway_center
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd ~/autonomous-fleet-testbed && python -m pytest tests/test_missions.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'nav_fleet.semantic_map'`

- [ ] **Step 4: Create `src/nav_fleet/nav_fleet/semantic_map.py`**

```python
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
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_missions.py -v`
Expected: 2 PASSED

- [ ] **Step 6: Point `tools/agentic_loop.py` at the new module**

In `tools/agentic_loop.py`, delete the whole `SEMANTIC_MAP = { ... }` block AND its two
comment lines ("Named locations matching..." through the closing `}`), and add one import
below the existing `from tools.baseline_monitor import check_run` line:

```python
from tools.baseline_monitor import check_run
# Canonical map lives in the nav_fleet package (Session 15) — the workspace overlay
# (auto-sourced by .bashrc) makes it importable here.
from nav_fleet.semantic_map import SEMANTIC_MAP
```

- [ ] **Step 7: Verify agentic_loop still resolves the map**

Run (the `eval` is the documented non-interactive-shell workaround for the API key,
required because `agentic_loop` instantiates the Anthropic client at import time):

```bash
eval "$(grep '^export ANTHROPIC_API_KEY' ~/.bashrc)" && \
  python -c "from tools.agentic_loop import SEMANTIC_MAP; print(len(SEMANTIC_MAP))"
```

Expected: `9`. Also confirm no duplicate map remains: `grep -c "'home_base'" tools/agentic_loop.py` → `0`.

- [ ] **Step 8: Run the full pure-Python suite (regression check)**

Run: `python -m pytest tests/ -v --ignore=tests/test_ros2_contracts.py --ignore=tests/test_navigation.py`
Expected: all PASS (previous 40 + the 2 new).

- [ ] **Step 9: Commit**

```bash
git add src/nav_fleet/nav_fleet/semantic_map.py tests/conftest.py tests/test_missions.py tools/agentic_loop.py
git commit -m "feat(session-15): move SEMANTIC_MAP into nav_fleet, add doorway_center

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Mission definitions — `missions.py`

**Files:**
- Create: `src/nav_fleet/nav_fleet/missions.py`
- Test: `tests/test_missions.py` (append)

**Interfaces:**
- Consumes: `nav_fleet.semantic_map.SEMANTIC_MAP` (Task 1).
- Produces:
  - `MissionStep` — frozen dataclass: `action: str` (`'navigate'` | `'take_picture'`), `label: str`, `location: str = None` (SEMANTIC_MAP key, required for `'navigate'`), `yaw: float = None` (optional final heading, radians, map frame).
  - `MISSIONS: dict[str, tuple[MissionStep, ...]]` — contains key `'mission1'`.
  - `validate_mission(steps) -> None`, raises `ValueError` on bad action / unknown location / empty mission.
  - `yaw_to_quaternion(yaw: float) -> tuple[float, float]` returning `(z, w)` for rotation about +Z.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_missions.py`)

```python
import math

import pytest


def test_mission1_shape():
    from nav_fleet.missions import MISSIONS
    steps = MISSIONS['mission1']
    assert [s.action for s in steps] == ['navigate', 'take_picture', 'navigate']
    assert steps[0].location == 'doorway_center'
    assert steps[0].yaw == pytest.approx(math.pi / 2)  # face north, into the bedroom
    assert steps[-1].location == 'home_base'


def test_all_defined_missions_are_valid():
    from nav_fleet.missions import MISSIONS, validate_mission
    for steps in MISSIONS.values():
        validate_mission(steps)  # must not raise


def test_validate_rejects_unknown_action():
    from nav_fleet.missions import MissionStep, validate_mission
    with pytest.raises(ValueError, match='unknown action'):
        validate_mission((MissionStep('teleport', 'zap'),))


def test_validate_rejects_unknown_location():
    from nav_fleet.missions import MissionStep, validate_mission
    with pytest.raises(ValueError, match='not in SEMANTIC_MAP'):
        validate_mission((MissionStep('navigate', 'go', 'narnia'),))


def test_validate_rejects_empty_mission():
    from nav_fleet.missions import validate_mission
    with pytest.raises(ValueError, match='empty'):
        validate_mission(())


def test_yaw_to_quaternion():
    from nav_fleet.missions import yaw_to_quaternion
    assert yaw_to_quaternion(0.0) == pytest.approx((0.0, 1.0))
    z, w = yaw_to_quaternion(math.pi / 2)
    assert (z, w) == pytest.approx((0.7071, 0.7071), abs=1e-4)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_missions.py -v`
Expected: the 6 new tests FAIL with `ModuleNotFoundError: No module named 'nav_fleet.missions'`; the 2 Task-1 tests still PASS.

- [ ] **Step 3: Create `src/nav_fleet/nav_fleet/missions.py`**

```python
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
"""Mission definitions: waypoint sequences + action primitives (Session 15, Decision 3).

Missions are data, not scripts — a mission is a tuple of MissionSteps executed in order
by nav_fleet.mission_runner. Pure Python (no ROS imports) so definitions are unit-testable
on CI runners without ROS2.
"""
import math
from dataclasses import dataclass

from nav_fleet.semantic_map import SEMANTIC_MAP

VALID_ACTIONS = ('navigate', 'take_picture')


@dataclass(frozen=True)
class MissionStep:
    action: str          # one of VALID_ACTIONS
    label: str           # human-readable step description (logged during execution)
    location: str = None  # SEMANTIC_MAP key — required for 'navigate'
    yaw: float = None    # optional final heading (radians, map frame) for 'navigate'


MISSIONS = {
    # Mission 1 (Session 15 first HIL milestone): navigate to the bedroom doorway centre
    # facing into the bedroom, photograph it, return to the spawn point.
    'mission1': (
        MissionStep('navigate', 'drive to bedroom doorway centre', 'doorway_center',
                    math.pi / 2),
        MissionStep('take_picture', 'photograph the bedroom'),
        MissionStep('navigate', 'return to start', 'home_base'),
    ),
}


def validate_mission(steps):
    """Raise ValueError if a mission is structurally invalid."""
    if not steps:
        raise ValueError('mission is empty')
    for i, step in enumerate(steps):
        if step.action not in VALID_ACTIONS:
            raise ValueError(f'step {i}: unknown action {step.action!r}')
        if step.action == 'navigate' and step.location not in SEMANTIC_MAP:
            raise ValueError(f'step {i}: location {step.location!r} not in SEMANTIC_MAP')


def yaw_to_quaternion(yaw):
    """Heading about +Z -> (z, w) quaternion components (x = y = 0 for planar robots)."""
    return math.sin(yaw / 2.0), math.cos(yaw / 2.0)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_missions.py -v`
Expected: 8 PASSED

- [ ] **Step 5: Lint**

Run: `cd src/nav_fleet && python -m flake8 nav_fleet/ --max-line-length=99 && cd ../..`
Expected: no output (clean).

- [ ] **Step 6: Commit**

```bash
git add src/nav_fleet/nav_fleet/missions.py tests/test_missions.py
git commit -m "feat(session-15): mission framework — MissionStep/MISSIONS data model + mission1

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: PNG writer — `image_io.py` + Pillow dependency

**Files:**
- Create: `src/nav_fleet/nav_fleet/image_io.py`
- Modify: `requirements-ci.txt`
- Test: `tests/test_missions.py` (append)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `nav_fleet.image_io.image_msg_to_png(msg, path: str) -> None` — duck-typed: `msg` needs `.height`, `.width`, `.step`, `.encoding` (`'rgb8'`/`'bgr8'`), `.data` (bytes-like). Writes a PNG. Raises `ValueError` on unsupported encoding.

- [ ] **Step 1: Add Pillow to dependencies**

In `requirements-ci.txt`, add after the `numpy>=1.26` line:

```
pillow>=10.0
```

Then install locally: `pip install 'pillow>=10.0'` (fleet-env is auto-activated).
Note: this edit invalidates the arm64 Docker build cache — next `stage-3-arm64` will be a full ~10 min build. Expected.

- [ ] **Step 2: Write the failing tests** (append to `tests/test_missions.py`)

```python
import types


def _fake_image_msg(encoding='rgb8', step=None):
    """2x2 image: (red, green) / (blue, white) in the named channel order."""
    row0 = bytes([255, 0, 0, 0, 255, 0])
    row1 = bytes([0, 0, 255, 255, 255, 255])
    step = step or 6
    pad = bytes(step - 6)
    return types.SimpleNamespace(
        height=2, width=2, step=step, encoding=encoding, data=row0 + pad + row1 + pad,
    )


def test_image_msg_to_png_rgb8(tmp_path):
    from PIL import Image
    from nav_fleet.image_io import image_msg_to_png
    out = tmp_path / 'shot.png'
    image_msg_to_png(_fake_image_msg('rgb8'), str(out))
    img = Image.open(out)
    assert img.size == (2, 2)
    assert img.getpixel((0, 0)) == (255, 0, 0)
    assert img.getpixel((1, 1)) == (255, 255, 255)


def test_image_msg_to_png_bgr8_swaps_channels(tmp_path):
    from PIL import Image
    from nav_fleet.image_io import image_msg_to_png
    out = tmp_path / 'shot.png'
    image_msg_to_png(_fake_image_msg('bgr8'), str(out))
    # bytes (255,0,0) read as BGR = pure blue -> stored RGB (0,0,255)
    assert Image.open(out).getpixel((0, 0)) == (0, 0, 255)


def test_image_msg_to_png_handles_row_padding(tmp_path):
    from PIL import Image
    from nav_fleet.image_io import image_msg_to_png
    out = tmp_path / 'shot.png'
    image_msg_to_png(_fake_image_msg('rgb8', step=8), str(out))
    assert Image.open(out).getpixel((1, 1)) == (255, 255, 255)


def test_image_msg_to_png_rejects_unknown_encoding(tmp_path):
    from nav_fleet.image_io import image_msg_to_png
    with pytest.raises(ValueError, match='mono16'):
        image_msg_to_png(_fake_image_msg('mono16'), str(tmp_path / 'x.png'))
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_missions.py -v -k image`
Expected: 4 FAIL with `ModuleNotFoundError: No module named 'nav_fleet.image_io'`

- [ ] **Step 4: Create `src/nav_fleet/nav_fleet/image_io.py`**

```python
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
"""sensor_msgs/Image -> PNG, without importing ROS.

Duck-typed on purpose: takes anything with .height/.width/.step/.encoding/.data so the
conversion is unit-testable on CI runners without ROS2 (the actual sensor_msgs.msg.Image
instances arrive only inside mission_runner, which never runs there).
"""
import numpy as np
from PIL import Image as PILImage


def image_msg_to_png(msg, path):
    """Write one camera frame to `path` as PNG. Supports rgb8 and bgr8 encodings."""
    if msg.encoding not in ('rgb8', 'bgr8'):
        raise ValueError(f'unsupported image encoding: {msg.encoding}')
    # `step` is the stride in bytes per row (may exceed width*3 due to padding).
    arr = np.frombuffer(bytes(msg.data), dtype=np.uint8).reshape(msg.height, msg.step)
    arr = arr[:, : msg.width * 3].reshape(msg.height, msg.width, 3)
    if msg.encoding == 'bgr8':
        arr = arr[:, :, ::-1]
    PILImage.fromarray(arr, 'RGB').save(path)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_missions.py -v`
Expected: 12 PASSED

- [ ] **Step 6: Lint + commit**

```bash
cd src/nav_fleet && python -m flake8 nav_fleet/ --max-line-length=99 && cd ../..
git add src/nav_fleet/nav_fleet/image_io.py requirements-ci.txt tests/test_missions.py
git commit -m "feat(session-15): image_io PNG writer for the take_picture primitive

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: `NavRunner.send_goal()` gains optional `yaw`

**Files:**
- Modify: `src/nav_fleet/nav_fleet/nav_runner.py:50-69`

**Interfaces:**
- Consumes: `nav_fleet.missions.yaw_to_quaternion` (Task 2).
- Produces: `NavRunner.send_goal(x, y, timeout=90.0, yaw=None) -> bool`. `yaw=None` keeps today's behavior exactly (`orientation.w = 1.0`); a float makes Nav2 rotate to that heading at the goal (`yaw_goal_tolerance` is 0.5 rad in `nav2_params.yaml`, so it IS enforced).

Why: Mission 1 photographs the bedroom from the doorway — the camera faces forward, so the robot must finish facing north (`yaw = π/2`). Existing callers (`test_navigation.py`) pass no yaw and are unaffected.

- [ ] **Step 1: Make the change**

In `nav_runner.py`, add the import after the existing `geometry_msgs` import:

```python
from geometry_msgs.msg import PoseStamped, PoseWithCovarianceStamped

from nav_fleet.missions import yaw_to_quaternion
```

Change the `send_goal` signature and the orientation line:

```python
    def send_goal(self, x, y, timeout=90.0, yaw=None):
```

and replace `goal.pose.pose.orientation.w = 1.0` with:

```python
        if yaw is None:
            goal.pose.pose.orientation.w = 1.0
        else:
            z, w = yaw_to_quaternion(yaw)
            goal.pose.pose.orientation.z = z
            goal.pose.pose.orientation.w = w
```

- [ ] **Step 2: Verify import graph + lint** (rclpy prevents pure unit tests; behavior is covered by Task 7's live run)

```bash
colcon build --symlink-install && source install/setup.bash
python -c "from nav_fleet.nav_runner import NavRunner; print('ok')"
cd src/nav_fleet && python -m flake8 nav_fleet/ --max-line-length=99 && cd ../..
```

Expected: `ok`, then clean flake8.

- [ ] **Step 3: Commit**

```bash
git add src/nav_fleet/nav_fleet/nav_runner.py
git commit -m "feat(session-15): optional final-heading (yaw) support in NavRunner.send_goal

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: Mission executor — `mission_runner.py`

**Files:**
- Create: `src/nav_fleet/nav_fleet/mission_runner.py`

**Interfaces:**
- Consumes: `NavRunner.send_goal(x, y, timeout, yaw)` (Task 4), `MISSIONS`/`validate_mission` (Task 2), `SEMANTIC_MAP` (Task 1), `image_msg_to_png` (Task 3), `tools.telemetry_logger.log_run` (existing).
- Produces: `MissionRunner(Node)` with `.nav: NavRunner`, `.photo_paths: list[str]`, `.run_mission(name: str) -> bool`, `.take_picture(label: str, timeout: float = 15.0) -> bool`. CLI: `python -m nav_fleet.mission_runner mission1` from the repo root (exit code 0 = PASS). Env: `ROBOT_ID` (default `robot_001`), `SIM_ENGINE` (default `gazebo`), `RUNNER_TYPE` (default `local` — the HIL run sets `RUNNER_TYPE=hil_jetson`).

- [ ] **Step 1: Create `src/nav_fleet/nav_fleet/mission_runner.py`**

```python
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
"""Mission executor: runs a named mission (waypoints + action primitives) against Nav2.

Run from the repo root (same reason as tools/agentic_loop.py — module imports):

    python -m nav_fleet.mission_runner mission1

Requires a live sim (sim_launch.py, or sim_only + nav2_only for HIL). Logs one telemetry
row per mission to FLEET_DB via tools.telemetry_logger.
"""
import argparse
import os
import pathlib
import time

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image

from nav_fleet.image_io import image_msg_to_png
from nav_fleet.missions import MISSIONS, validate_mission
from nav_fleet.nav_runner import NavRunner
from nav_fleet.semantic_map import SEMANTIC_MAP
from tools.telemetry_logger import log_run

PHOTO_DIR = pathlib.Path('reports/photos')
NAV_TIMEOUT_S = 90.0


class MissionRunner(Node):

    def __init__(self):
        super().__init__('mission_runner')
        self.nav = NavRunner()
        self.photo_paths = []
        self.nav_durations = []
        self.nav_errors = []
        self._latest_image = None
        self.create_subscription(
            Image, '/robot_001/camera/image_raw', self._image_cb, 10
        )

    def _image_cb(self, msg):
        self._latest_image = msg

    def take_picture(self, label, timeout=15.0):
        """Capture one fresh camera frame and save it as a PNG under reports/photos/."""
        self._latest_image = None  # force a frame newer than this call
        deadline = time.time() + timeout
        while self._latest_image is None and time.time() < deadline:
            rclpy.spin_once(self, timeout_sec=0.1)
        if self._latest_image is None:
            self.get_logger().error(f'no camera frame within {timeout}s')
            return False
        PHOTO_DIR.mkdir(parents=True, exist_ok=True)
        path = PHOTO_DIR / f"{label}_{time.strftime('%Y%m%d_%H%M%S')}.png"
        image_msg_to_png(self._latest_image, str(path))
        self.photo_paths.append(str(path))
        self.get_logger().info(f'photo saved: {path}')
        return True

    def run_mission(self, name):
        steps = MISSIONS[name]
        validate_mission(steps)
        for i, step in enumerate(steps, start=1):
            self.get_logger().info(f'[{name}] step {i}/{len(steps)}: {step.label}')
            if step.action == 'navigate':
                x, y = SEMANTIC_MAP[step.location]
                ok = self.nav.send_goal(x, y, timeout=NAV_TIMEOUT_S, yaw=step.yaw)
                if self.nav.last_duration_s is not None:
                    self.nav_durations.append(self.nav.last_duration_s)
                if self.nav.last_position_error is not None:
                    self.nav_errors.append(self.nav.last_position_error)
            else:  # take_picture — validate_mission guarantees the action set
                ok = self.take_picture(f'{name}_step{i}')
            if not ok:
                self.get_logger().error(f'[{name}] step {i} ({step.label}) FAILED')
                return False
        return True


def _mean(values):
    return sum(values) / len(values) if values else None


def _log_mission(name, ok, runner):
    log_run(
        scenario=name,
        steps=len(MISSIONS[name]),
        final_x=runner.nav.last_final_x if runner.nav.last_final_x is not None else 0.0,
        final_y=runner.nav.last_final_y if runner.nav.last_final_y is not None else 0.0,
        result='PASS' if ok else 'FAIL',
        step_log=[],
        robot_id=os.environ.get('ROBOT_ID', 'robot_001'),
        robot_type='jetson_ugv_pt',
        runner_type=os.environ.get('RUNNER_TYPE', 'local'),
        sim_engine=os.environ.get('SIM_ENGINE', 'gazebo'),
        nav_success_rate=1.0 if ok else 0.0,
        mean_position_error=_mean(runner.nav_errors),
        mean_time_to_goal=_mean(runner.nav_durations),
    )


def main():
    parser = argparse.ArgumentParser(description='Run a named mission against Nav2.')
    parser.add_argument('mission', choices=sorted(MISSIONS))
    args = parser.parse_args()

    rclpy.init()
    runner = MissionRunner()
    try:
        ok = runner.run_mission(args.mission)
    finally:
        rclpy.try_shutdown()
    _log_mission(args.mission, ok, runner)

    print(f"Mission {args.mission}: {'PASS' if ok else 'FAIL'}")
    for p in runner.photo_paths:
        print(f'  photo: {p}')
    raise SystemExit(0 if ok else 1)


if __name__ == '__main__':
    main()
```

- [ ] **Step 2: Verify import graph + lint**

```bash
colcon build --symlink-install && source install/setup.bash
python -c "from nav_fleet.mission_runner import MissionRunner; print('ok')"
cd src/nav_fleet && python -m flake8 nav_fleet/ --max-line-length=99 && cd ../..
python -m pytest tests/ -v --ignore=tests/test_ros2_contracts.py --ignore=tests/test_navigation.py
```

Expected: `ok`; clean flake8; all pure tests PASS. (Live behavior verified in Task 7.)

- [ ] **Step 3: Commit**

```bash
git add src/nav_fleet/nav_fleet/mission_runner.py
git commit -m "feat(session-15): MissionRunner executor node with take_picture primitive

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: Split the launch file for HIL — `sim_only` + `nav2_only`

**Files:**
- Create: `src/nav_fleet/launch/sim_only_launch.py`
- Create: `src/nav_fleet/launch/nav2_only_launch.py`
- Modify: `src/nav_fleet/launch/sim_launch.py` (becomes a thin composition — single-machine behavior unchanged)

**Interfaces:**
- Consumes: existing world/URDF/map/params files.
- Produces: `sim_only_launch.py` (Gazebo server + robot spawn + ros_gz bridge + RSP + lidar frame bridge — runs on the workstation in HIL) and `nav2_only_launch.py` (Nav2 bringup only, launch arg `start_delay:=<float seconds>` default `0.0` — runs on the Jetson in HIL). `sim_launch.py` includes both with `start_delay:=13.0`, preserving today's timing.

Design note (who runs where in HIL): the "robot brain" under test is Nav2 + the mission executor — those move to the Jetson. RSP (robot_state_publisher) stays sim-side because the Gazebo spawner reads `/robot_description` from it and it's a trivial CPU load; migrating RSP onboard is a real-robot (Session 16) concern, not a HIL one.

- [ ] **Step 1: Create `sim_only_launch.py`**

Copy `sim_launch.py` and delete only the Nav2 parts — the result must be exactly:

```python
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
"""Simulation half only: Gazebo + robot spawn + ros_gz bridge + RSP + lidar frame bridge.

No Nav2 — pair with nav2_only_launch.py (same machine, or another machine over DDS for
hardware-in-the-loop; see Mission1HILSession15.md). sim_launch.py composes both for the
classic single-machine run.

Path resolution uses pathlib.Path(__file__) instead of get_package_share_directory
because colcon-ament-python is not installed on this system (see sim_launch.py).
"""
import pathlib

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, TimerAction
from launch.substitutions import Command
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue

PKG = pathlib.Path(__file__).parent.parent


def generate_launch_description():
    urdf_path = str(PKG / 'urdf' / 'ugv_pt.urdf.xacro')
    world_path = str(PKG / 'worlds' / 'bedroom_simple.sdf')

    headless_arg = DeclareLaunchArgument(
        'headless', default_value='false',
        description='Run Gazebo headless (no GUI) — set true for CI',
    )

    robot_desc = ParameterValue(Command(['xacro ', urdf_path]), value_type=str)

    robot_state_publisher = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        name='robot_state_publisher',
        parameters=[{
            'robot_description': robot_desc,
            'use_sim_time': True,
        }],
        remappings=[
            ('/tf', '/robot_001/tf'),
            ('/tf_static', '/robot_001/tf_static'),
        ],
    )

    # -s = server only (no GUI process). GUI crashes on this machine due to a
    # snap/glibc libpthread conflict; when it dies it takes the server with it.
    # Open a separate viewer with `gz sim -g` if you need visual inspection.
    gazebo = ExecuteProcess(
        cmd=['gz', 'sim', '-s', '-r', world_path],
        output='screen',
    )

    # Wait 3s for Gazebo to load world before spawning robot
    spawn_robot = TimerAction(
        period=3.0,
        actions=[Node(
            package='ros_gz_sim',
            executable='create',
            arguments=[
                '-name', 'robot_001',
                '-topic', '/robot_description',
                '-x', '-1.276', '-y', '1.2', '-z', '0.15',
                '-Y', '1.5708',   # facing North (+Y)
            ],
            output='screen',
        )],
    )

    # Delayed 5 s so gz-transport discovery completes before the bridge
    # subscribes. Starting the bridge before Gazebo publishers are live causes
    # the GZ→ROS subscriptions to silently fail (no reconnect in this version).
    bridge = TimerAction(
        period=5.0,
        actions=[Node(
            package='ros_gz_bridge',
            executable='parameter_bridge',
            arguments=[
                # ] = ROS→GZ only (Nav2 sends velocity commands to Gazebo)
                '/robot_001/cmd_vel@geometry_msgs/msg/Twist]gz.msgs.Twist',
                # [ = GZ→ROS only (Gazebo publishes sensor/state data; ROS reads it)
                '/robot_001/odom@nav_msgs/msg/Odometry[gz.msgs.Odometry',
                '/robot_001/scan@sensor_msgs/msg/LaserScan[gz.msgs.LaserScan',
                '/robot_001/camera/image_raw@sensor_msgs/msg/Image[gz.msgs.Image',
                '/robot_001/tf@tf2_msgs/msg/TFMessage[gz.msgs.Pose_V',
                '/robot_001/imu/data@sensor_msgs/msg/Imu[gz.msgs.IMU',
                '/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock',
            ],
            output='screen',
        )],
    )

    # Gazebo Harmonic names the GPU lidar frame as {model}/{parent_link}/{sensor}
    # = robot_001/base_footprint/lidar, but RSP publishes lidar_link (no prefix).
    # Bridge the two so AMCL can look up scan → base_footprint chain.
    lidar_frame_bridge = Node(
        package='tf2_ros',
        executable='static_transform_publisher',
        name='lidar_frame_bridge',
        arguments=['0', '0', '0', '0', '0', '0',
                   'lidar_link',
                   'robot_001/base_footprint/lidar'],
        parameters=[{'use_sim_time': True}],
        remappings=[
            ('/tf_static', '/robot_001/tf_static'),
        ],
    )

    return LaunchDescription([
        headless_arg,
        robot_state_publisher,
        gazebo,
        spawn_robot,
        bridge,
        lidar_frame_bridge,
    ])
```

- [ ] **Step 2: Create `nav2_only_launch.py`**

```python
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
"""Nav2 half only: nav2_bringup with this project's map/params, no simulator.

The 'robot brain' — runs on the same machine as the sim (via sim_launch.py) or on the
real Jetson for hardware-in-the-loop, where /clock, /robot_001/tf, scan, odom etc. all
arrive over DDS from the sim machine (see Mission1HILSession15.md).

start_delay: seconds to wait before starting Nav2. sim_launch.py passes 13.0 (matches
the original single-file timing: world load + bridge up + first sensor data). Default
0.0 — an HIL operator starts this manually only after the sim side is confirmed up.
"""
import os
import pathlib

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (DeclareLaunchArgument, IncludeLaunchDescription,
                            TimerAction)
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration

PKG = pathlib.Path(__file__).parent.parent


def generate_launch_description():
    start_delay_arg = DeclareLaunchArgument(
        'start_delay', default_value='0.0',
        description='Seconds to wait before Nav2 bringup (sim_launch.py uses 13.0)',
    )

    nav2_bringup_dir = get_package_share_directory('nav2_bringup')
    nav2 = TimerAction(
        period=LaunchConfiguration('start_delay'),
        actions=[IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                os.path.join(nav2_bringup_dir, 'launch', 'bringup_launch.py')
            ),
            launch_arguments={
                'namespace': 'robot_001',
                'use_namespace': 'true',
                'use_sim_time': 'true',
                'params_file': str(PKG / 'config' / 'nav2_params.yaml'),
                'map': str(PKG / 'maps' / 'living_room.yaml'),
                'use_composition': 'True',
                'autostart': 'true',
            }.items(),
        )],
    )

    return LaunchDescription([
        start_delay_arg,
        nav2,
    ])
```

- [ ] **Step 3: Rewrite `sim_launch.py` as the composition**

Replace the entire body of `sim_launch.py` (keep the license header) with:

```python
"""Launch the full single-machine stack: Gazebo sim + Nav2 (Session 10 behavior).

Since Session 15 this is a thin composition of sim_only_launch.py (Gazebo, spawn, bridge,
RSP, lidar frame bridge) and nav2_only_launch.py (Nav2 bringup, delayed 13 s) so the two
halves can also run on separate machines for hardware-in-the-loop testing. Behavior and
timing of the single-machine run are unchanged.
"""
import pathlib

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource

LAUNCH_DIR = pathlib.Path(__file__).parent


def generate_launch_description():
    headless_arg = DeclareLaunchArgument(
        'headless', default_value='false',
        description='Run Gazebo headless (no GUI) — set true for CI',
    )

    sim = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(str(LAUNCH_DIR / 'sim_only_launch.py')),
    )
    nav2 = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(str(LAUNCH_DIR / 'nav2_only_launch.py')),
        launch_arguments={'start_delay': '13.0'}.items(),
    )

    return LaunchDescription([
        headless_arg,
        sim,
        nav2,
    ])
```

- [ ] **Step 4: Verify Tier 1 still works end-to-end (regression — this is the load-bearing check)**

Terminal A: `colcon build --symlink-install && source install/setup.bash && ros2 launch src/nav_fleet/launch/sim_launch.py`
Wait for Nav2 `Managed nodes are active` + AMCL initial pose log.
Terminal B: `python -m pytest tests/test_navigation.py::test_navigation_succeeds -v --timeout=120`
Expected: PASS. Then Ctrl+C Terminal A.

If Nav2 never starts and the log shows a TimerAction/period type error on `start_delay`, fall back to a fixed `period=13.0` in `nav2_only_launch.py` plus a separate `nav2_now_launch.py`-style zero-delay variant — but try the substitution form first (supported in Jazzy's launch).

- [ ] **Step 5: Commit**

```bash
git add src/nav_fleet/launch/sim_only_launch.py src/nav_fleet/launch/nav2_only_launch.py src/nav_fleet/launch/sim_launch.py
git commit -m "feat(session-15): split sim_launch into sim-only and nav2-only halves for HIL

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 7: Mission 1 integration test + protective CI ignore + Tier-1 run

**Files:**
- Create: `tests/test_mission_run.py`
- Modify: `.github/workflows/ci.yml:113-115` (stage-1 pytest ignore list — same commit, per Global Constraints)

**Interfaces:**
- Consumes: `MissionRunner` (Task 5), full launch stack (Task 6).
- Produces: a repeatable live test for Mission 1; proof of the Tier-1 milestone (mission PASS, photo on disk, telemetry row in `reports/fleet_runs.db`).

- [ ] **Step 1: Create `tests/test_mission_run.py`**

```python
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
"""Integration test for the Mission 1 executor. Requires live Gazebo + Nav2
(ros2 launch src/nav_fleet/launch/sim_launch.py). Ignored in stage-1-quality —
imports rclpy at module level, and that runner has no ROS2 (see CLAUDE.md Gotchas)."""
import pathlib

import pytest
import rclpy
from PIL import Image as PILImage

from nav_fleet.mission_runner import MissionRunner


@pytest.fixture(scope='session', autouse=True)
def ros_context():
    rclpy.init()
    yield
    rclpy.shutdown()


@pytest.fixture(scope='session')
def runner(ros_context):
    node = MissionRunner()
    yield node
    node.nav.destroy_node()
    node.destroy_node()


def test_mission1_completes(runner):
    """Mission 1: doorway centre -> photograph -> home. Two Nav2 goals + one capture."""
    assert runner.run_mission('mission1') is True
    assert len(runner.photo_paths) == 1
    photo = pathlib.Path(runner.photo_paths[0])
    assert photo.exists()
    with PILImage.open(photo) as img:
        assert img.size[0] > 0 and img.size[1] > 0
```

- [ ] **Step 2: Add the stage-1 ignore (same commit!)**

In `.github/workflows/ci.yml`, the stage-1 "Run Python unit tests" step becomes:

```yaml
          python -m pytest tests/ -v \
            --ignore=tests/test_ros2_contracts.py \
            --ignore=tests/test_navigation.py \
            --ignore=tests/test_mission_run.py \
            -k "not integration"
```

- [ ] **Step 3: Verify stage-1's exact command locally excludes it**

Run: `python -m pytest tests/ -v --ignore=tests/test_ros2_contracts.py --ignore=tests/test_navigation.py --ignore=tests/test_mission_run.py -k "not integration"`
Expected: all pure tests PASS, `test_mission_run.py` absent from the collected list.

- [ ] **Step 4: Run Mission 1 live — CLI first (the Tier-1 milestone run)**

Terminal A: `ros2 launch src/nav_fleet/launch/sim_launch.py` → wait for `Managed nodes are active`.
Terminal B (repo root): `python -m nav_fleet.mission_runner mission1`
Expected: three step log lines, then `Mission mission1: PASS` and a `photo: reports/photos/mission1_step2_*.png` line; exit code 0.

Checks:
```bash
sqlite3 reports/fleet_runs.db \
  "SELECT scenario, result, runner_type, sim_engine FROM runs ORDER BY run_id DESC LIMIT 1;"
```
Expected: `mission1|PASS|local|gazebo`. Open the photo (`xdg-open reports/photos/mission1_step2_*.png`) — it should show the bedroom (dresser/bed/goal sphere region), i.e. the camera was facing north through the doorway.

If Nav2 rejects the doorway goal or aborts with the goal inside the inflated zone (the doorway is only ~0.71 m wide): nudge `doorway_center` north to `(-0.974, 2.70)` (just inside the bedroom, clear of the wall gap) in `semantic_map.py`, update the Task 1 test expectation, and note the change in the commit message. Try the true center first.

- [ ] **Step 5: Run the integration test (fresh sim)**

Ctrl+C Terminal A, wait ~5 s, relaunch `ros2 launch src/nav_fleet/launch/sim_launch.py`, wait for active, then:
`python -m pytest tests/test_mission_run.py -v --timeout=300`
Expected: 1 PASSED. Ctrl+C the launch afterwards.

- [ ] **Step 6: Commit**

```bash
git add tests/test_mission_run.py .github/workflows/ci.yml
git commit -m "test(session-15): Mission 1 end-to-end integration test; ignore in stage-1

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 8: HIL runbook + the actual Jetson-in-the-loop run

**Files:**
- Create: `Mission1HILSession15.md` (repo root — same pattern as `JetsonInstallSession14.md`)

**Interfaces:**
- Consumes: `sim_only_launch.py` / `nav2_only_launch.py` (Task 6), `mission_runner` CLI (Task 5), the Session-14 Jetson (user `Mike`, IP `10.42.0.217` — re-check with `ip neigh show dev enp6s0`, ROS2 Jazzy installed, repo cloned, per `JetsonInstallSession14.md`).
- Produces: the runbook, and a recorded successful (or honestly-recorded failed) HIL run — the spec's "bare-metal HIL prototype runs Mission 1 at least once, manually, outside CI" criterion.

- [ ] **Step 1: Write `Mission1HILSession15.md`** with exactly these sections and content (fill the Results section during Steps 2–4):

````markdown
# Mission 1 Hardware-in-the-Loop — Session 15 Runbook

Gazebo (world + sensors) runs on the x86 workstation; Nav2 + the mission executor (the
"robot brain" under test) run on the real Jetson Orin Nano. The two halves talk over the
existing NetworkManager-shared Ethernet link via CycloneDDS. Spec:
docs/superpowers/specs/2026-07-10-session15-gazebo-hil-mission1-design.md.

## Part 1 — One-time Jetson setup

SSH in (`ssh Mike@10.42.0.217` — if the DHCP lease moved, find it with
`ip neigh show dev enp6s0` on the workstation), then:

```bash
sudo apt install -y ros-jazzy-navigation2 ros-jazzy-nav2-bringup ros-jazzy-rmw-cyclonedds-cpp
cd ~/autonomous-fleet-testbed && git pull
# Same Python environment as the Session 14 native pytest run (JetsonInstallSession14.md Part 7):
pip install 'pillow>=10.0'
colcon build --symlink-install && source install/setup.bash
```

## Part 2 — Environment on BOTH machines (every session)

Both sides must agree on the RMW and domain. The workstation already uses CycloneDDS;
the Jetson defaults to FastDDS unless told otherwise:

```bash
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export ROS_DOMAIN_ID=0
```

(Workstation `.bashrc` already handles this; on the Jetson add both lines to `~/.bashrc`
above any interactivity guard, or export per-terminal.)

**If discovery fails** (Part 3's `ros2 topic list` on the Jetson shows nothing): multicast
may not traverse the shared link. Fall back to unicast peers — on BOTH machines, write
`~/cyclonedds-hil.xml` (substitute the current Jetson IP):

```xml
<CycloneDDS>
  <Domain>
    <General><AllowMulticast>false</AllowMulticast></General>
    <Discovery>
      <Peers>
        <Peer address="10.42.0.1"/>    <!-- workstation, shared-link gateway -->
        <Peer address="10.42.0.217"/>  <!-- Jetson (re-check the lease) -->
      </Peers>
    </Discovery>
  </Domain>
</CycloneDDS>
```

and `export CYCLONEDDS_URI=file://$HOME/cyclonedds-hil.xml` in every terminal on both sides.

## Part 3 — Run procedure (three terminals)

**Terminal 1 — workstation, sim half:**
```bash
cd ~/autonomous-fleet-testbed
ros2 launch src/nav_fleet/launch/sim_only_launch.py
```
Wait for the bridge node to start (~5 s after Gazebo). Optional viewer: `gz sim -g`.

**Terminal 2 — Jetson (SSH), sanity check then Nav2:**
```bash
cd ~/autonomous-fleet-testbed
ros2 topic hz /robot_001/scan --window 20   # expect ~10 Hz — proves DDS crosses the link
ros2 topic echo /clock --once               # proves sim time arrives
ros2 launch src/nav_fleet/launch/nav2_only_launch.py
```
Wait for `Managed nodes are active` and the AMCL initial-pose log.

**Terminal 3 — Jetson (SSH), the mission:**
```bash
cd ~/autonomous-fleet-testbed
RUNNER_TYPE=hil_jetson python -m nav_fleet.mission_runner mission1
```

**Success =** `Mission mission1: PASS`, exit code 0, a PNG under `reports/photos/` on the
Jetson, and a `runs` row with `runner_type='hil_jetson'` in the Jetson's local
`reports/fleet_runs.db`. (Shipping HIL telemetry/photos back to the workstation DB is a
CI-stage design question — see docs/session15-hil-ci-stage-design.md — not part of the
manual prototype.)

## Part 4 — Teardown

Ctrl+C Terminal 2 (Nav2) and Terminal 1 (sim), in that order. Between HIL attempts, give
DDS ~5 s after both sides are down before relaunching.

## Troubleshooting

- **Jetson sees no topics:** RMW mismatch (check `echo $RMW_IMPLEMENTATION` on both) or
  multicast — use the unicast-peers fallback above. `ping` is NOT a valid link test on
  this network (outbound ICMP is silently dropped — Session 14); use `ros2 topic hz`.
- **Nav2 stuck at time 0 on the Jetson:** `/clock` isn't arriving — check Terminal 1's
  bridge started, and the `/clock` echo in Part 3.
- **Goal rejected repeatedly:** bt_navigator not ACTIVE yet — the runner retries 5×, but
  if it still fails, Nav2 bringup on the Orin may just be slower than x86; wait for
  `Managed nodes are active` before Terminal 3.

## Results — first HIL run (2026-07-__)

- Date/time, Jetson IP, link type (shared Ethernet / USB-C):
- Discovery mode used (multicast / unicast peers):
- Mission result + wall time per navigate step:
- Photo path + does it show the bedroom:
- Telemetry row (paste the SELECT output):
- Deviations from this runbook (fold fixes back into the sections above):
````

- [ ] **Step 2: Do Part 1 (Jetson prep) over SSH** — commands as written in the runbook. If the repo on the Jetson can't `git pull` the un-pushed branch, push first (`git push origin main`) or pull over the local network (`git pull ssh://Mike@... ` is not set up — pushing to origin is the simple path; ask Mike if pushing mid-session is OK, since all prior tasks are committed locally).

- [ ] **Step 3: Do Parts 2–3 (the HIL run).** Follow the runbook verbatim. If a step deviates, fix the runbook text — the doc must end up matching what actually worked.

- [ ] **Step 4: Fill in the Results section with real numbers** (including a FAIL honestly, if that's the outcome, plus what's blocking).

- [ ] **Step 5: Commit**

```bash
git add Mission1HILSession15.md
git commit -m "docs(session-15): Mission 1 HIL runbook + first real Jetson-in-the-loop run results

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 9: CI-stage design doc (design only — no workflow changes)

**Files:**
- Create: `docs/session15-hil-ci-stage-design.md`

**Interfaces:**
- Consumes: Task 8's measured HIL behavior (startup times, discovery mode that worked, failure modes hit).
- Produces: the design the future CI-implementation session executes from.

- [ ] **Step 1: Write the doc** with these sections and positions (adjust specifics with Task 8's real measurements; the *decisions* below are the design — write them as decisions, not options, unless Task 8 contradicts one):

```markdown
# Session 15 — HIL CI Stage Design (design only, not yet implemented)

## Orchestration: one GHA job on the x86 runner, driving the Jetson over SSH
A GitHub Actions job runs on exactly one runner, so "one HIL test" cannot natively span
the x86 runner and the Jetson runner. Coordinating two self-hosted runners requires
artifact/API polling between jobs — brittle, and teardown on failure is unreliable.
Decision: the HIL job runs on the existing x86 GPU runner (which must host Gazebo anyway),
and drives the Jetson via `ssh Mike@<jetson>` for Nav2 launch, mission run, and teardown.
The Jetson's GHA-runner registration stays — it still serves stage-3-arm64 builds — but
this stage treats the Jetson as a lab instrument, not a runner.
Prereq: workstation SSH key already authorized on the Jetson (Session 14); the Jetson IP
must be resolved at job start (`ip neigh show dev enp6s0`) — a DHCP lease change must not
break the job.

## Success / failure definition
PASS = `python -m nav_fleet.mission_runner mission1` on the Jetson exits 0 within its
timeout. The job then: scps the photo back and uploads it as a workflow artifact; queries
the Jetson's fleet_runs.db for the new row (`runner_type='hil_jetson'`) and prints it to
the job log. FAIL = nonzero exit, SSH timeout, or missing photo/row.
Telemetry shipping (appending the Jetson's HIL row into the workstation drift DB so
baseline_monitor can watch HIL trends) is phase 2 — design decision: ship the row via
`sqlite3` SELECT over SSH + local INSERT, not by copying the whole DB file.

## Timeout / teardown
Job-level `timeout-minutes: 15`. Per-phase: sim up ≤ 60 s (from Task 8: measure), Nav2
active on Jetson ≤ 120 s (measure), mission ≤ 300 s. Teardown step with `if: always()`:
SSH `pkill -f 'nav2|component_container|mission_runner'` on the Jetson, then kill the
local launch process group — the one place a scripted pkill is acceptable, because CI has
no foreground Ctrl+C (mirrors the existing CI-cleanup note in CLAUDE.md).

## Job naming / renumbering decision
No renumbering needed. The HIL job takes the existing Stage 4 slot as `stage-4-hil`,
replacing `stage-4-isaac` when implemented (Isaac shelved per the Session 15 spec — the
job and its scripts are retired to git history, not deleted from disk preemptively).
`needs: stage-3-arm64` is preserved and finally becomes REAL: phase 2 of this stage pulls
the stage-3 GHCR arm64 image onto the Jetson and runs the mission executor inside that
container — the arm64→HIL edge the original hand-drawn diagram meant. Phase 1 (first
implementation) runs natively on the Jetson, exactly like the manual prototype, to keep
the first CI iteration debuggable.
`stage-5-reports-hw` keeps `needs: stage-4-hil` unchanged in shape.

## Open items for the implementation session
- Measure whether Gazebo headless + Nav2-on-Orin under CI load stays within the phase
  timeouts above (numbers from Task 8's manual run: <fill in>).
- Secrets/inventory: where the Jetson IP/user live (repo variable vs. discovery step).
- Whether stage-2-gazebo should also run tests/test_mission_run.py (cheap win: the same
  mission logic sim-only) — leaning yes, but it belongs to the implementation PR.
```

- [ ] **Step 2: Sanity-check the doc against the spec's success criteria** (spec lines: "network orchestration approach, success/failure definition, timeout/teardown behavior", "job renumbering plan decided") — each must be answered by a section above, with no "TBD" outside the explicitly-labeled "Open items" list.

- [ ] **Step 3: Commit**

```bash
git add docs/session15-hil-ci-stage-design.md
git commit -m "docs(session-15): HIL CI stage design — SSH-orchestrated stage-4-hil, no renumber

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 10: Closeout — checkboxes, decision log, CLAUDE.md

**Files:**
- Modify: `Release1Todo.md` (Session 15 "Session Complete When" checkboxes)
- Modify: `BLUEPRINT.md` (decisions log — new dated entry)
- Modify: `CLAUDE.md` (commands, layout, gotchas)

- [ ] **Step 1: `Release1Todo.md`** — in Session 15's "Session Complete When", check the three remaining boxes ([x] bare-metal HIL prototype ran Mission 1 — cite `Mission1HILSession15.md` Results; [x] CI stage design exists — cite `docs/session15-hil-ci-stage-design.md`; [x] renumbering decided — "no renumber; stage-4-hil takes the Stage 4 slot"; [x] implementation plan written — cite this plan file). If the HIL run FAILED in Task 8, do NOT check that box — note the honest status instead.

- [ ] **Step 2: `BLUEPRINT.md`** — append a decisions-log entry dated with the actual completion date: Mission 1 implemented (mission framework on `SEMANTIC_MAP`, `take_picture` primitive, launch split for HIL), first real HIL run result (honest numbers from the runbook), CI design decided (stage-4-hil over SSH, no renumbering), and that Isaac's `stage-4-isaac` remains in place until `stage-4-hil` is implemented.

- [ ] **Step 3: `CLAUDE.md`** — three edits:
  1. Key Commands: add `python -m nav_fleet.mission_runner mission1  # run a mission (repo root; sim must be up)`.
  2. Directory Layout: under `src/nav_fleet/`, note `launch/sim_only_launch.py` + `launch/nav2_only_launch.py` (HIL split, composed by `sim_launch.py`) and `nav_fleet/missions.py`/`mission_runner.py`/`semantic_map.py`/`image_io.py`; add `Mission1HILSession15.md` to the root-docs list.
  3. Fix the Tier-1 pytest command in "Development workflow" and "Key Commands" to ignore ALL THREE live-ROS2 test files (`test_ros2_contracts.py`, `test_navigation.py`, `test_mission_run.py`) — the current documented command only ignores the first and would fail without a live sim.

- [ ] **Step 4: Run the traceability gate (unchanged expectations, just confirm no regression)**

Run: `python tools/check_traceability.py requirements/traceability.yaml tests/ --profile robot_profiles/jetson_ugv_pt.yaml`
Expected: same result as before this plan (BR-03 still unmatched — known, Session 17+ work).

- [ ] **Step 5: Commit**

```bash
git add Release1Todo.md BLUEPRINT.md CLAUDE.md
git commit -m "docs(session-15): closeout — Mission 1 + HIL results, CI design recorded

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Self-review notes (done at plan time)

- **Spec coverage:** Decision 1 (Gazebo) → Tasks 6–8 build on Gazebo only; Decision 2 (one robot) → no fleet code anywhere; Decision 3 (mission framework) → Tasks 2+5; Decision 4 (Mission 1) → Tasks 1–7; Decision 5 (Mission 2 deferred) → intentionally absent; HIL topology → Task 8 Part 2; success criteria (bare-metal first → Task 7 before Task 8; CI design → Task 9; BLUEPRINT record → Task 10; renumbering decision → Task 9). Mission 2 items (coverage planner, ball detection) deliberately have no tasks.
- **Known risks flagged inline:** doorway-goal inflation rejection (Task 7 Step 4 fallback), `TimerAction` substitution period (Task 6 Step 4 fallback), Jetson repo sync requiring a push (Task 8 Step 2 — ask Mike), Jetson DHCP lease drift (runbook + design doc).
- **Type consistency check:** `MissionStep(action, label, location=None, yaw=None)` used identically in Tasks 2/5; `send_goal(x, y, timeout=90.0, yaw=None)` defined Task 4, consumed Task 5; `image_msg_to_png(msg, path)` defined Task 3, consumed Task 5; `photo_paths: list[str]` produced Task 5, consumed Task 7.
