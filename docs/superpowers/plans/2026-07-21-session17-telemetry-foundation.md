# Telemetry Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Consolidate the two telemetry databases (in-repo `reports/fleet_runs.db`, the
default every tool falls back to; and `~/fleet-ci-data/fleet_runs.db`, the path CI has
actually written to since Session 12) into one canonical file every tool reads/writes by
default, with no data migration needed.

**Architecture:** `tools/telemetry_logger.py` already owns the telemetry schema (column
registry) — it becomes the single owner of the DB *path* too. Five other files that each
independently redeclare the same default literal import it from there instead. CI's
per-job `FLEET_DB:` overrides become redundant once the Python-side default is correct,
so they're removed. No new abstractions, no migration script — the CI-side file is
adopted as-is.

**Tech Stack:** Python 3, sqlite3 (stdlib), pytest + `tmp_path`/`monkeypatch` fixtures,
GitHub Actions (`ci.yml`).

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-21-session17-telemetry-foundation-design.md`
  (approved by Mike, 2026-07-21) — this plan implements it exactly; do not add scope
  beyond it.
- TDD is this project's norm: write the failing test before the implementation for every
  behavioral change.
- The `FLEET_DB` env var override must keep working exactly as today — existing tests
  pass `db_path=` explicitly and must not need changes.
- No data migration: the local `reports/fleet_runs.db`'s rows are discarded, not merged
  (explicit decision, spec §Decisions.3).
- Every step's commands are meant to be run from the repo root
  (`/home/mike/autonomous-fleet-testbed`) with the project's Python venv active (already
  true in an interactive terminal per `.bashrc`; a non-interactive shell must activate
  `~/fleet-env` explicitly first — see CLAUDE.md's `ANTHROPIC_API_KEY` gotcha for why).

---

### Task 1: Centralize `DB_PATH` in `tools/telemetry_logger.py` + auto-create its directory

**Files:**
- Modify: `tools/telemetry_logger.py:16` (the `DB_PATH` line), `tools/telemetry_logger.py:50-52` (`init_db`)
- Test: `tests/test_telemetry_logger.py`

**Interfaces:**
- Produces: `tools.telemetry_logger.DB_PATH` (str) — now defaults to
  `os.path.expanduser("~/fleet-ci-data/fleet_runs.db")` when `FLEET_DB` is unset. Every
  later task that imports `DB_PATH` relies on this exact module attribute.
- Produces: `tools.telemetry_logger.init_db(db_path: str = DB_PATH) -> None` — now creates
  `db_path`'s parent directory if missing, before connecting.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_telemetry_logger.py`. First, update its imports at the top of the file:

```python
"""Unit tests for tools/telemetry_logger.py schema + log_run fields."""
import importlib
import os
import sqlite3

from tools import telemetry_logger
from tools.telemetry_logger import init_db, log_run
```

Then append these three tests at the end of the file:

```python
def _reload_telemetry_logger_after(monkeypatch):
    """Restores tools.telemetry_logger to reflect the real environment after a test
    reloads it under a monkeypatched FLEET_DB. DB_PATH is bound once, at import time
    (same pattern the module used before this change) — re-evaluating it after a test
    changes the env var requires an explicit reload, and monkeypatch's automatic
    teardown alone won't re-run that module-level assignment."""
    monkeypatch.undo()
    importlib.reload(telemetry_logger)


def test_db_path_defaults_to_home_fleet_ci_data(monkeypatch):
    monkeypatch.delenv("FLEET_DB", raising=False)
    importlib.reload(telemetry_logger)
    try:
        assert telemetry_logger.DB_PATH == os.path.expanduser(
            "~/fleet-ci-data/fleet_runs.db"
        )
    finally:
        _reload_telemetry_logger_after(monkeypatch)


def test_db_path_honors_fleet_db_override(monkeypatch, tmp_path):
    override = str(tmp_path / "custom.db")
    monkeypatch.setenv("FLEET_DB", override)
    importlib.reload(telemetry_logger)
    try:
        assert telemetry_logger.DB_PATH == override
    finally:
        _reload_telemetry_logger_after(monkeypatch)


def test_init_db_creates_missing_parent_directory(tmp_path):
    db = tmp_path / "nested" / "does_not_exist_yet" / "t.db"
    assert not db.parent.exists()
    init_db(str(db))
    assert db.exists()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_telemetry_logger.py -v -k "db_path or init_db_creates"`
Expected: `test_db_path_defaults_to_home_fleet_ci_data` and
`test_db_path_honors_fleet_db_override` FAIL (current default is
`reports/fleet_runs.db`, a relative in-repo path, not `~/fleet-ci-data/fleet_runs.db`);
`test_init_db_creates_missing_parent_directory` FAILs with
`sqlite3.OperationalError: unable to open database file` (the nested dir doesn't exist
yet and nothing creates it).

- [ ] **Step 3: Implement**

In `tools/telemetry_logger.py`, change line 16:

```python
DB_PATH = os.environ.get("FLEET_DB", "reports/fleet_runs.db")
```

to:

```python
DB_PATH = os.environ.get("FLEET_DB", os.path.expanduser("~/fleet-ci-data/fleet_runs.db"))
```

Then change `init_db` (currently lines 50-52):

```python
def init_db(db_path: str = DB_PATH):
    conn = sqlite3.connect(db_path)
```

to:

```python
def init_db(db_path: str = DB_PATH):
    parent = os.path.dirname(db_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(db_path)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_telemetry_logger.py -v`
Expected: all PASS (including the pre-existing tests in this file — confirms the change
didn't break the explicit-`db_path=` path).

- [ ] **Step 5: Commit**

```bash
git add tools/telemetry_logger.py tests/test_telemetry_logger.py
git commit -m "$(cat <<'EOF'
feat(telemetry): centralize DB_PATH default to ~/fleet-ci-data/fleet_runs.db

Foundation piece (Session 17): this is the exact file CI has written to
since Session 12 while every tool's own default silently fell back to the
in-repo reports/fleet_runs.db instead — two different databases. No data
migration needed, this file already holds the real history. init_db() now
creates its target directory if missing.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: `FLEET_TELEMETRY=off` opt-out for ad hoc runs

**Files:**
- Modify: `tools/telemetry_logger.py:86-119` (`log_run`)
- Test: `tests/test_telemetry_logger.py`

**Interfaces:**
- Consumes: nothing new from Task 1 beyond what already exists.
- Produces: `log_run(...)` now returns `None` (instead of writing a row and returning its
  id) when the `FLEET_TELEMETRY` env var is `"off"`. No caller in this codebase
  (`src/nav_fleet/nav_fleet/mission_runner.py:263`, `tools/mission2_day.py:330`,
  `tools/mission2_harness.py:442`) uses `log_run`'s return value today, so this is safe.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_telemetry_logger.py`:

```python
def test_log_run_skips_write_when_telemetry_off(tmp_path, monkeypatch):
    monkeypatch.setenv("FLEET_TELEMETRY", "off")
    db = str(tmp_path / "t.db")
    result = log_run(scenario="s", steps=1, final_x=0.0, final_y=0.0, result="PASS",
                      step_log=[], db_path=db)
    assert result is None
    assert not os.path.exists(db)


def test_log_run_writes_when_telemetry_on(tmp_path, monkeypatch):
    monkeypatch.setenv("FLEET_TELEMETRY", "on")
    db = str(tmp_path / "t.db")
    run_id = log_run(scenario="s", steps=1, final_x=0.0, final_y=0.0, result="PASS",
                      step_log=[], db_path=db)
    assert run_id is not None
    assert os.path.exists(db)


def test_log_run_writes_when_telemetry_unset(tmp_path, monkeypatch):
    monkeypatch.delenv("FLEET_TELEMETRY", raising=False)
    db = str(tmp_path / "t.db")
    run_id = log_run(scenario="s", steps=1, final_x=0.0, final_y=0.0, result="PASS",
                      step_log=[], db_path=db)
    assert run_id is not None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_telemetry_logger.py -v -k "telemetry_off or telemetry_on or telemetry_unset"`
Expected: `test_log_run_skips_write_when_telemetry_off` FAILs (a row gets written; the
env var is currently ignored). The other two PASS already (this is expected — they're
guarding the *default* behavior, which isn't broken yet).

- [ ] **Step 3: Implement**

In `tools/telemetry_logger.py`, `log_run`'s current opening (lines 86-98):

```python
def log_run(scenario: str, steps: int, final_x: float, final_y: float,
            result: str, step_log: list, db_path: str = DB_PATH, **metrics):
    """Insert one row into `runs`.

    `scenario`/`steps`/`final_x`/`final_y`/`result` are required; every other field is
    an optional telemetry column passed by name (must exist in RUNS_COLUMNS — a typo'd
    name raises instead of silently vanishing). None values are left NULL.
    """
    unknown = set(metrics) - set(RUNS_COLUMNS)
```

becomes:

```python
def log_run(scenario: str, steps: int, final_x: float, final_y: float,
            result: str, step_log: list, db_path: str = DB_PATH, **metrics):
    """Insert one row into `runs`.

    `scenario`/`steps`/`final_x`/`final_y`/`result` are required; every other field is
    an optional telemetry column passed by name (must exist in RUNS_COLUMNS — a typo'd
    name raises instead of silently vanishing). None values are left NULL.

    Returns the new row's id, or None if FLEET_TELEMETRY=off skipped the write
    entirely (for ad hoc/experimental runs that shouldn't join the drift-tracked
    record — no scratch DB, no partial write, a true no-op).
    """
    if os.environ.get("FLEET_TELEMETRY", "on") == "off":
        return None

    unknown = set(metrics) - set(RUNS_COLUMNS)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_telemetry_logger.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/telemetry_logger.py tests/test_telemetry_logger.py
git commit -m "$(cat <<'EOF'
feat(telemetry): FLEET_TELEMETRY=off opt-out for ad hoc runs

Foundation piece (Session 17): a single choke point in log_run() — every
write path (NavRunner, MissionRunner, mission2_day.py's judge) already goes
through it. No caller uses the return value, so returning None on skip is
safe.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Migrate the 5 downstream files to import `DB_PATH` from `telemetry_logger`

**Files:**
- Modify: `tools/baseline_monitor.py:27`
- Modify: `tools/validate_telemetry.py:25-27`
- Modify: `tools/agentic_loop.py:12,25`
- Modify: `tools/generate_test_report.py:22-27`
- Modify: `dashboard/app.py:22-27`
- Test: `tests/test_fleet_db_consolidation.py` (new file)

**Interfaces:**
- Consumes: `tools.telemetry_logger.DB_PATH` (from Task 1).
- Produces: nothing new consumed by later tasks — this is the last code task before the
  ci.yml/docs/cutover tasks.

- [ ] **Step 1: Write the failing test**

Create `tests/test_fleet_db_consolidation.py`:

```python
"""Regression guard for the Foundation piece (Session 17, 2026-07-21): DB_PATH used to
be independently redeclared — os.environ.get("FLEET_DB", "reports/fleet_runs.db") or a
os.path.join equivalent — in 6 different files, and silently drifted out of sync with
the real path CI actually wrote to. Every consumer must import DB_PATH from
tools.telemetry_logger (the single owner) instead of redeclaring its own default.

This checks source text rather than importing the modules directly: dashboard/app.py
runs Streamlit calls and a live DB read at import time, and tools/agentic_loop.py
constructs an anthropic.Anthropic() client at import time — neither is safe or
meaningful to import in a unit test just to check an import line.
"""
import pathlib

EXPECTED_IMPORTS = {
    "tools/baseline_monitor.py": "from tools.telemetry_logger import DB_PATH",
    # validate_telemetry.py combines this with its existing BASE_COLUMNS/RUNS_COLUMNS
    # import into one line — the substring below must match that exact line, not just
    # "import DB_PATH" (which never appears verbatim there).
    "tools/validate_telemetry.py":
        "from tools.telemetry_logger import BASE_COLUMNS, DB_PATH, RUNS_COLUMNS",
    "tools/agentic_loop.py": "from tools.telemetry_logger import DB_PATH as FLEET_DB",
    "tools/generate_test_report.py": "from tools.telemetry_logger import DB_PATH",
    "dashboard/app.py": "from tools.telemetry_logger import DB_PATH",
}


def test_downstream_modules_import_db_path_from_telemetry_logger():
    repo_root = pathlib.Path(__file__).resolve().parent.parent
    for rel_path, expected_import in EXPECTED_IMPORTS.items():
        source = (repo_root / rel_path).read_text()
        assert expected_import in source, (
            f"{rel_path} should import DB_PATH from tools.telemetry_logger, "
            "not redeclare its own default"
        )
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_fleet_db_consolidation.py -v`
Expected: FAIL — none of the 5 files contain the expected import string yet.

- [ ] **Step 3: Implement — edit each of the 5 files**

`tools/baseline_monitor.py` — replace line 27:

```python
DB_PATH = os.environ.get("FLEET_DB", "reports/fleet_runs.db")
```

with:

```python
from tools.telemetry_logger import DB_PATH
```

`tools/validate_telemetry.py` — replace lines 25-27:

```python
from tools.telemetry_logger import BASE_COLUMNS, RUNS_COLUMNS  # noqa: E402

DB_PATH = os.environ.get("FLEET_DB", "reports/fleet_runs.db")
```

with:

```python
from tools.telemetry_logger import BASE_COLUMNS, DB_PATH, RUNS_COLUMNS  # noqa: E402
```

`tools/agentic_loop.py` — replace line 12:

```python
from tools.baseline_monitor import check_run
```

with:

```python
from tools.baseline_monitor import check_run
from tools.telemetry_logger import DB_PATH as FLEET_DB
```

and remove line 25 entirely:

```python
FLEET_DB = os.environ.get("FLEET_DB", "reports/fleet_runs.db")
```

(the blank lines around it collapse to one blank line between `client =
anthropic.Anthropic()` and `TOOLS = [`).

`tools/generate_test_report.py` — replace lines 22-27:

```python
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DB_PATH = os.getenv(
    "FLEET_DB",
    os.path.join(_PROJECT_ROOT, "reports", "fleet_runs.db")
)
REPORT_PATH = os.getenv(
```

with:

```python
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from tools.telemetry_logger import DB_PATH  # noqa: E402

REPORT_PATH = os.getenv(
```

`dashboard/app.py` — replace lines 22-27:

```python
from tools.goal_zones import end_zones  # noqa: E402

DB_PATH = os.environ.get(
    "FLEET_DB",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "reports", "fleet_runs.db"))
```

with:

```python
from tools.goal_zones import end_zones  # noqa: E402
from tools.telemetry_logger import DB_PATH  # noqa: E402
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_fleet_db_consolidation.py -v`
Expected: PASS.

- [ ] **Step 5: Run the full local test suite (regression check)**

Run:
```bash
colcon build --symlink-install
source install/setup.bash
python -m pytest tests/ -v \
  --ignore=tests/test_ros2_contracts.py \
  --ignore=tests/test_navigation.py \
  --ignore=tests/test_mission_run.py \
  --ignore=tests/test_mission2.py
```
Expected: all PASS. This is the standard Tier-1 command from CLAUDE.md — confirms
`baseline_monitor`/`validate_telemetry`/`generate_test_report`'s existing tests
(`test_baseline.py`, `test_report_tools.py`) still import and run correctly now that
they get `DB_PATH` from `telemetry_logger` instead of declaring it themselves.

- [ ] **Step 6: Commit**

```bash
git add tools/baseline_monitor.py tools/validate_telemetry.py tools/agentic_loop.py \
        tools/generate_test_report.py dashboard/app.py tests/test_fleet_db_consolidation.py
git commit -m "$(cat <<'EOF'
refactor(telemetry): 5 tools import DB_PATH from telemetry_logger, not redeclare it

Foundation piece (Session 17): baseline_monitor, validate_telemetry,
agentic_loop, generate_test_report, and dashboard/app.py each independently
redeclared the same os.environ.get("FLEET_DB", ...) default — this is
exactly how the default drifted out of sync with CI's real persistent path
in the first place. tools/telemetry_logger.py (already the schema owner) is
now the single owner of the path too. New regression-guard test.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Remove the now-redundant `FLEET_DB:` lines from `ci.yml`

**Files:**
- Modify: `.github/workflows/ci.yml` (4 jobs: `stage-2-gazebo`, `stage-4-hil`,
  `stage-5-reports-sim`, `stage-5-reports-hw`)

**Interfaces:**
- Consumes: Task 1's corrected Python-side default (this task removes the CI-level
  override that's now redundant with it) and Task 1's `init_db` directory auto-creation
  (this task also removes the now-redundant `mkdir -p` steps).
- Produces: nothing consumed by later tasks.

- [ ] **Step 1: Edit `stage-2-gazebo`**

In `.github/workflows/ci.yml`, this block:

```yaml
      DISPLAY: ':0'
      RMW_IMPLEMENTATION: rmw_cyclonedds_cpp
      # Persistent path outside the job workspace — history accumulates across CI runs,
      # which drift detection (stage-5-reports) needs.
      FLEET_DB: /home/mike/fleet-ci-data/fleet_runs.db
      SIM_ENGINE: gazebo
    steps:
      - uses: actions/checkout@v4

      - name: Ensure persistent telemetry dir exists
        # FLEET_DB above points outside the job workspace so history accumulates across
        # runs — sqlite3.connect() doesn't create missing parent dirs, so the first-ever
        # run needs this before any test can log a row.
        run: mkdir -p /home/mike/fleet-ci-data

      - name: Build workspace
```

becomes:

```yaml
      DISPLAY: ':0'
      RMW_IMPLEMENTATION: rmw_cyclonedds_cpp
      SIM_ENGINE: gazebo
    steps:
      - uses: actions/checkout@v4

      - name: Build workspace
```

(`FLEET_DB`'s default — `~/fleet-ci-data/fleet_runs.db`, Task 1 — already resolves to
this exact path on this runner, and `telemetry_logger.init_db` now creates the
directory itself, so both the env override and the explicit `mkdir` step are genuinely
redundant, not just unused.)

- [ ] **Step 2: Edit `stage-4-hil`**

This block:

```yaml
      HIL_IMAGE: ghcr.io/${{ github.repository }}:${{ github.sha }}
      # The day's JUDGED verdict rows (mission2_no_ball / _yellow / _red) are logged HERE on
      # the workstation (where the judge runs) directly into the shared drift DB — no SSH row-
      # shipping needed any more (Task 13d). Same persistent path stage-2/5 use so
      # baseline_monitor tracks HIL trends and stage-5-reports-hw is genuinely hardware-fed.
      FLEET_DB: /home/mike/fleet-ci-data/fleet_runs.db
    steps:
      - uses: actions/checkout@v4

      - name: Ensure persistent telemetry dir exists
        run: mkdir -p /home/mike/fleet-ci-data
```

becomes:

```yaml
      HIL_IMAGE: ghcr.io/${{ github.repository }}:${{ github.sha }}
      # The day's JUDGED verdict rows (mission2_no_ball / _yellow / _red) are logged HERE on
      # the workstation (where the judge runs) directly into the shared drift DB — no SSH row-
      # shipping needed any more (Task 13d). Same persistent DB stage-2/5 use (the default
      # owned by tools/telemetry_logger.DB_PATH, Session 17 Foundation piece) so
      # baseline_monitor tracks HIL trends and stage-5-reports-hw is genuinely hardware-fed.
    steps:
      - uses: actions/checkout@v4
```

- [ ] **Step 3: Edit `stage-5-reports-sim`**

This block:

```yaml
  stage-5-reports-sim:
    name: "Stage 5 — Workstation Reports + Dashboard"
    # Runs on the self-hosted runner, not ubuntu-latest: stage-2's nav tests write
    # telemetry to this runner's local disk (FLEET_DB above), so a hosted job's fresh
    # checkout would have no run data — it would PDF an empty database.
    runs-on: [self-hosted, x86, gpu, rtx5080]
    needs: stage-2-gazebo
    env:
      FLEET_DB: /home/mike/fleet-ci-data/fleet_runs.db
      REPORT_PATH: reports/latest_report.pdf
    steps:
      - uses: actions/checkout@v4

      - name: Ensure persistent telemetry dir exists
        run: mkdir -p /home/mike/fleet-ci-data

      - name: Generate report
```

becomes:

```yaml
  stage-5-reports-sim:
    name: "Stage 5 — Workstation Reports + Dashboard"
    # Runs on the self-hosted runner, not ubuntu-latest: stage-2's nav tests write
    # telemetry to this runner's persistent DB (~/fleet-ci-data/fleet_runs.db, the
    # default owned by tools/telemetry_logger.DB_PATH), so a hosted job's fresh
    # checkout would have no run data — it would PDF an empty database.
    runs-on: [self-hosted, x86, gpu, rtx5080]
    needs: stage-2-gazebo
    env:
      REPORT_PATH: reports/latest_report.pdf
    steps:
      - uses: actions/checkout@v4

      - name: Generate report
```

- [ ] **Step 4: Edit `stage-5-reports-hw`**

This block:

```yaml
    env:
      FLEET_DB: /home/mike/fleet-ci-data/fleet_runs.db
      REPORT_PATH: reports/latest_report.pdf
    steps:
      - uses: actions/checkout@v4

      - name: Ensure persistent telemetry dir exists
        run: mkdir -p /home/mike/fleet-ci-data

      - name: Generate report
        run: |
          source ~/fleet-env/bin/activate
          python -m tools.generate_test_report

      - name: Validate telemetry schema
        run: |
          source ~/fleet-env/bin/activate
          python -m tools.validate_telemetry

      - name: Check baseline drift
        run: |
          source ~/fleet-env/bin/activate
          python -m tools.baseline_monitor

      - name: Upload PDF report
        uses: actions/upload-artifact@v4
        with:
          name: test-report-${{ github.run_number }}-hw
          path: reports/latest_report.pdf
```

becomes:

```yaml
    env:
      REPORT_PATH: reports/latest_report.pdf
    steps:
      - uses: actions/checkout@v4

      - name: Generate report
        run: |
          source ~/fleet-env/bin/activate
          python -m tools.generate_test_report

      - name: Validate telemetry schema
        run: |
          source ~/fleet-env/bin/activate
          python -m tools.validate_telemetry

      - name: Check baseline drift
        run: |
          source ~/fleet-env/bin/activate
          python -m tools.baseline_monitor

      - name: Upload PDF report
        uses: actions/upload-artifact@v4
        with:
          name: test-report-${{ github.run_number }}-hw
          path: reports/latest_report.pdf
```

(Only the `env:`/`steps:` header changes — the four named steps below "Generate
report" are unchanged and shown here only so the surrounding context in the diff is
unambiguous.)

- [ ] **Step 5: Verify the YAML is still valid**

Run: `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml')); print('valid')"`
Expected: `valid` (this file has no dedicated linter in this repo — `flake8` in
stage-1-quality only runs against `nav_fleet/`/`test/`, confirmed by checking
`.github/workflows/ci.yml`'s own lint step — so a plain YAML parse is the correct and
sufficient syntax check here).

- [ ] **Step 6: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "$(cat <<'EOF'
chore(ci): remove redundant FLEET_DB env overrides + mkdir steps

Foundation piece (Session 17): now that tools/telemetry_logger.DB_PATH's own
default resolves to this exact path (~/fleet-ci-data/fleet_runs.db) and
init_db() creates its own directory, the per-job env override and explicit
mkdir step in stage-2-gazebo/stage-4-hil/stage-5-reports-sim/
stage-5-reports-hw were redundant, not just unused.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Delete the stale local DB and the dead `reports/history/` directory

**Files:**
- Delete: `reports/fleet_runs.db` (gitignored — confirmed via `.gitignore:18` `*.db` — a
  plain `rm`, not `git rm`)
- Delete: `reports/history/` (tracked via `reports/history/.gitkeep` — needs `git rm`)

**Interfaces:** none — this task has no code interface, just filesystem/git state.

- [ ] **Step 1: Confirm what's about to be removed**

Run: `git status --short reports/ && git ls-files reports/history/`
Expected: `reports/fleet_runs.db` does NOT appear in `git status` output (confirming
it's genuinely gitignored, not accidentally tracked); `git ls-files` shows
`reports/history/.gitkeep`.

- [ ] **Step 2: Delete the stale local DB**

Run: `rm reports/fleet_runs.db`

- [ ] **Step 3: Remove the dead history directory from git**

Run: `git rm -r reports/history`

- [ ] **Step 4: Verify**

Run: `git status --short`
Expected: shows `reports/history/.gitkeep` staged for deletion; `reports/fleet_runs.db`
does not appear at all (it was gitignored, so its removal isn't a git-tracked change).

- [ ] **Step 5: Commit**

```bash
git commit -m "$(cat <<'EOF'
chore: remove stale local telemetry DB and dead reports/history/

Foundation piece (Session 17): reports/fleet_runs.db held only ad hoc local
runs, superseded now that every tool defaults to the real, already-populated
~/fleet-ci-data/fleet_runs.db (Task 1). reports/history/ was already
confirmed dead — the JSON-per-run idea was dropped at the Session 12 review
and nothing ever wrote to it.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Fix CLAUDE.md and README documentation

**Files:**
- Modify: `CLAUDE.md:148-151`, `CLAUDE.md:181-183`
- Modify: `README.md:139`

**Interfaces:** none — documentation only.

- [ ] **Step 1: Fix CLAUDE.md's directory-layout entry**

Replace (lines 148-151):

```markdown
- `reports/fleet_runs.db` — SQLite telemetry store (`FLEET_DB` env var) — the single source
  all tools read/write (telemetry_logger, baseline_monitor drift detection, dashboard,
  generate_test_report, validate_telemetry, agentic_loop). `reports/history/` is
  empty/unused — the JSON-per-run idea was dropped in the 2026-07-03 Session 12 review.
```

with:

```markdown
- `reports/` — generated PDF reports and mission photos (`reports/photos/`, untracked).
  The telemetry DB does **not** live here — see the `Telemetry database` entry below.
  (`reports/history/`, the old empty/unused JSON-per-run idea dropped at the 2026-07-03
  Session 12 review, was deleted along with this fix — Session 17 Foundation piece,
  2026-07-21.)
- **Telemetry database — `~/fleet-ci-data/fleet_runs.db`** (env var `FLEET_DB` to
  override; owned by `tools/telemetry_logger.DB_PATH`) — THE single source every tool
  reads/writes (telemetry_logger, baseline_monitor, dashboard, generate_test_report,
  validate_telemetry, agentic_loop). Lives outside the repo deliberately: the
  self-hosted CI runner's checkout is ephemeral, so history has to survive somewhere
  that isn't wiped between runs — local dev and every CI job write to this same file,
  since they're the same physical machine (Session 17 Foundation piece, 2026-07-21).
  **This fixes a real bug**, not a hypothetical one: from Session 12 to Session 17, CI
  wrote here while every tool's own *default* silently fell back to the in-repo
  `reports/fleet_runs.db` instead — two different databases, with the dashboard and
  local report generation only ever seeing whichever ad hoc local runs happened to hit
  the wrong one. `FLEET_TELEMETRY=off` skips writing a telemetry row entirely, for ad
  hoc/experimental runs that shouldn't join the drift-tracked record.
```

- [ ] **Step 2: Fix CLAUDE.md's Gotchas entry**

Replace (lines 181-183):

```markdown
- DB path env var is `FLEET_DB` (default: `reports/fleet_runs.db`) — used by telemetry_logger,
  validate_telemetry, dashboard, baseline_monitor, generate_test_report, agentic_loop
  (ai_test_generator/scenario_analyzer deleted 2026-07-19 — S17 review CR-05, rebuilt fresh in R2)
```

with:

```markdown
- DB path env var is `FLEET_DB` (default: `~/fleet-ci-data/fleet_runs.db`, owned by
  `tools/telemetry_logger.DB_PATH` — Session 17 Foundation piece, 2026-07-21; previously
  each of 6 files redeclared its own default independently, which is exactly how it
  drifted out of sync with CI's real path for 5 sessions) — used by telemetry_logger,
  validate_telemetry, dashboard, baseline_monitor, generate_test_report, agentic_loop
  (ai_test_generator/scenario_analyzer deleted 2026-07-19 — S17 review CR-05, rebuilt
  fresh in R2). `FLEET_TELEMETRY=off` skips writing a telemetry row entirely.
```

- [ ] **Step 3: Fix README.md's repo-map table row**

Replace (line 139):

```markdown
| `reports/` | Telemetry DB (`fleet_runs.db`), generated reports, mission photos |
```

with:

```markdown
| `reports/` | Generated reports, mission photos (telemetry DB lives at `~/fleet-ci-data/fleet_runs.db` — see CLAUDE.md) |
```

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md README.md
git commit -m "$(cat <<'EOF'
docs: fix inaccurate telemetry-DB claims in CLAUDE.md and README

Foundation piece (Session 17): CLAUDE.md claimed reports/fleet_runs.db was
"the single source all tools read/write" — only true when FLEET_DB was
unset, which CI never was. Documents the real canonical path, why it lives
outside the repo, and the new FLEET_TELEMETRY=off flag.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: Cutover — enable WAL mode on the real DB, then verify end-to-end

**Files:** none (operational step against the live file + manual verification) —
this task has no test file of its own; it's the spec's own "Testing / verification"
section executed for real.

**Interfaces:** none.

- [ ] **Step 1: Confirm the real file already holds CI's history**

Run: `sqlite3 ~/fleet-ci-data/fleet_runs.db "SELECT runner_type, COUNT(*) FROM runs GROUP BY runner_type;"`
Expected: more than one `runner_type` value (e.g. `local`, `hil_jetson`, possibly
`gazebo`/others), with nonzero counts — confirms this is genuinely the file with real
accumulated CI history, not an empty one.

- [ ] **Step 2: Enable WAL mode, once, against the real file**

Run: `sqlite3 ~/fleet-ci-data/fleet_runs.db "PRAGMA journal_mode=WAL;"`
Expected output: `wal`

This is a one-time operational step, not a code change — WAL mode is stored in the
SQLite file's own header and persists across every future connection/process, which is
exactly why no `PRAGMA` call needs to be added to any `connect()` call anywhere in the
codebase (per the spec's explicit design decision).

- [ ] **Step 3: Run the full local test suite one more time (final regression check)**

Run:
```bash
colcon build --symlink-install
source install/setup.bash
python -m pytest tests/ -v \
  --ignore=tests/test_ros2_contracts.py \
  --ignore=tests/test_navigation.py \
  --ignore=tests/test_mission_run.py \
  --ignore=tests/test_mission2.py
```
Expected: all PASS.

- [ ] **Step 4: Verify `generate_test_report` and `baseline_monitor` see real CI data**

Run (with `FLEET_DB` deliberately left unset, to exercise the new default exactly as
every real invocation will):
```bash
unset FLEET_DB
python -m tools.generate_test_report
python -m tools.baseline_monitor
```
Expected: `generate_test_report` prints `Report saved to
/home/mike/autonomous-fleet-testbed/reports/test_report.pdf` (note: this now draws
from `~/fleet-ci-data/fleet_runs.db`'s ~100 most recent real rows, not an ad hoc local
handful); `baseline_monitor` prints a `Baseline drift report` for the latest real run
in that file, not "No metrics available for comparison."

- [ ] **Step 5: Visually confirm the dashboard sees real CI data (manual, GUI-observed)**

Run: `unset FLEET_DB && streamlit run dashboard/app.py`

Open the printed local URL in a browser. In the sidebar, confirm the **Runner** filter
dropdown offers more than just `local` — it should include `hil_jetson` (and possibly
other real CI `runner_type` values) if any HIL runs have ever completed. Confirm the
**Overview** tab's "Total Runs" count is large (accumulated CI history), not just a
handful of local ad hoc runs. Stop the server with `Ctrl+C` when done.

**This step needs your own eyes on the running dashboard** — per this project's
GUI-observation convention, report what you actually saw (the Runner dropdown's real
values, the total run count) before this task is considered verified, not just that
the command ran without an error.

- [ ] **Step 6: Final commit (if Steps 1-5 required no code changes, this task has
      nothing further to commit — it's a verification-only task)**

No commit expected for this task unless Step 5's manual check surfaces a real problem
that needs a follow-up fix — in that case, stop and report back rather than
force-fixing forward, per this project's standing practice of pausing for review
between meaningful steps.
