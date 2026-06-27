# Session 06: Stage 0 Requirements Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `tools/check_traceability.py` — a production-grade CLI tool that reads `requirements/traceability.yaml` and scans `tests/` to verify every requirement ID has a matching test function, then wire it into the Stage 0 CI job.

**Architecture:** Single Python file with clear function boundaries (load → scan → check → format → exit). All heavy logic lives in named functions so each is independently testable without running the CLI. Python `logging` module handles debug output to stderr; all result output goes to stdout, keeping `--json > file.json` clean.

**Tech Stack:** Python 3.12, PyYAML, Python `ast` module (stdlib), `argparse` (stdlib), `logging` (stdlib), `json` (stdlib), pytest 8.3.2, GitHub Actions.

## Global Constraints

- Python virtualenv: `~/fleet-env` — activate with `source ~/fleet-env/bin/activate` before running any Python command
- pytest version: 8.3.2 (pinned — do not upgrade)
- All Python files need copyright header: `# Copyright 2026 Mike. Licensed under MIT.`
- Max line length: 99 chars (flake8)
- Exit codes: 0 = clean or orphan warnings only, 1 = missing requirement, 2 = tool/config error
- Orphan tests (exist in tests/ but unmapped in traceability.yaml) are warnings only — exit 0
- `--json` output goes to stdout only; logging always goes to stderr
- `--json` takes priority over `--quiet` if both flags are passed
- `reports/traceability_latest.json` must be gitignored (regenerated every CI run)
- All design decisions: `docs/superpowers/specs/2026-06-27-pipeline-architecture-design.md`

---

## File Map

| Action | File | Responsibility |
|---|---|---|
| Modify | `requirements/traceability.yaml` | Add `description` field to all 8 requirements |
| Modify | `robot_profiles/jetson_ugv_pt.yaml` | Add `skip_requirements: []` field |
| Modify | `.gitignore` | Add `reports/traceability_latest.json` |
| Create | `tools/check_traceability.py` | The Stage 0 gate tool — all logic here |
| Create | `tests/test_check_traceability.py` | Unit + integration tests for the tool |
| Modify | `.github/workflows/ci.yml` | Replace Stage 0 stub with real job |

---

## Task 1: Update YAML Schemas and .gitignore

**Files:**
- Modify: `requirements/traceability.yaml`
- Modify: `robot_profiles/jetson_ugv_pt.yaml`
- Modify: `.gitignore`

**Interfaces:**
- Produces: `traceability.yaml` with `description` field on every requirement; `jetson_ugv_pt.yaml` with `skip_requirements` list; `.gitignore` with CI artifact excluded

No tests — these are data files validated by Task 2's tests.

- [ ] **Step 1: Replace `requirements/traceability.yaml` with description-annotated version**

Write this exact content to `requirements/traceability.yaml`:

```yaml
# Every requirement ID must map to at least one test.
# check_traceability.py fails CI if any ID is uncovered.

requirements:
  - id: BR-01
    description: "Robot reaches goal within 0.15m Euclidean distance"
    tests:
      - tests/test_navigation.py::test_goal_position_error
  - id: BR-02
    description: "Zero collisions per navigation run"
    tests:
      - tests/test_navigation.py::test_zero_collisions
  - id: BR-03
    description: "Recovery behavior completes within 10s if triggered"
    tests:
      - tests/test_navigation.py::test_recovery_timeout
  - id: BR-04
    description: "/robot_001/odom publishes at >= 50 Hz"
    tests:
      - tests/test_ros2_contracts.py::test_odom_hz
  - id: BR-07
    description: "nav_success_rate >= 95% over rolling 20 runs"
    tests:
      - tests/test_baseline.py::test_nav_success_rate_drift
  - id: BR-10
    description: "Nav2 behavior tree returns SUCCESS"
    tests:
      - tests/test_navigation.py::test_bt_success
  - id: SC-04
    description: "/robot_001/scan publishes at >= 10 Hz"
    tests:
      - tests/test_ros2_contracts.py::test_lidar_hz
  - id: SC-05
    description: "/robot_001/camera/image_raw publishes at >= 10 Hz"
    tests:
      - tests/test_ros2_contracts.py::test_camera_hz
```

- [ ] **Step 2: Add `skip_requirements` to `robot_profiles/jetson_ugv_pt.yaml`**

Open `robot_profiles/jetson_ugv_pt.yaml`. Add these two lines immediately after the `nav_stack: nav2_full` line:

```yaml
skip_requirements: []  # Jetson UGV PT supports full Nav2 stack — no requirements skipped
```

The file around that section should look like:
```yaml
  nav_stack: nav2_full
  skip_requirements: []  # Jetson UGV PT supports full Nav2 stack — no requirements skipped
  namespace: /robot_001
```

- [ ] **Step 3: Add CI artifact to `.gitignore`**

Add this block to `.gitignore` after the `# Generated reports` section:

```
# CI-generated traceability report (regenerated each run)
reports/traceability_latest.json
```

- [ ] **Step 4: Commit**

```bash
git add requirements/traceability.yaml robot_profiles/jetson_ugv_pt.yaml .gitignore
git commit -m "feat: add description fields to traceability.yaml and skip_requirements to robot profile"
```

---

## Task 2: Tool Skeleton — Logging + YAML Loading

**Files:**
- Create: `tools/check_traceability.py`
- Create: `tests/test_check_traceability.py`

**Interfaces:**
- Produces:
  - `Requirement(id: str, description: str, tests: list[str])` — NamedTuple
  - `Result(covered, missing, skipped, orphans)` — NamedTuple (lists of Requirement + list[str])
  - `setup_logging(debug: bool) -> None`
  - `load_traceability(path: Path) -> list[Requirement]` — raises SystemExit(2) on error
  - `load_profile(path: Path) -> set[str]` — raises SystemExit(2) on error

- [ ] **Step 1: Write failing tests for `load_traceability` and `load_profile`**

Create `tests/test_check_traceability.py`:

```python
# Copyright 2026 Mike. Licensed under MIT.
"""Tests for tools/check_traceability.py"""
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
import check_traceability as ct
from check_traceability import Requirement, Result


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def traceability_yaml(tmp_path):
    content = """\
requirements:
  - id: BR-01
    description: Robot reaches goal within 0.15m
    tests:
      - tests/test_navigation.py::test_goal_position_error
  - id: BR-02
    description: Zero collisions per run
    tests:
      - tests/test_navigation.py::test_zero_collisions
"""
    p = tmp_path / "traceability.yaml"
    p.write_text(content)
    return p


@pytest.fixture
def profile_yaml(tmp_path):
    p = tmp_path / "robot_profile.yaml"
    p.write_text("name: test_robot\nskip_requirements: []\n")
    return p


@pytest.fixture
def profile_yaml_with_skip(tmp_path):
    p = tmp_path / "robot_profile_skip.yaml"
    p.write_text("name: test_robot\nskip_requirements:\n  - BR-02\n")
    return p


@pytest.fixture
def test_dir_full(tmp_path):
    """Both BR-01 and BR-02 tests exist."""
    d = tmp_path / "tests"
    d.mkdir()
    (d / "test_navigation.py").write_text(
        "def test_goal_position_error(): pass\n"
        "def test_zero_collisions(): pass\n"
        "def helper_not_a_test(): pass\n"
    )
    return d


@pytest.fixture
def test_dir_partial(tmp_path):
    """Only BR-01 test exists — BR-02 test is missing."""
    d = tmp_path / "tests"
    d.mkdir()
    (d / "test_navigation.py").write_text(
        "def test_goal_position_error(): pass\n"
    )
    return d


# ---------------------------------------------------------------------------
# load_traceability
# ---------------------------------------------------------------------------

class TestLoadTraceability:
    def test_loads_id_description_and_tests(self, traceability_yaml):
        reqs = ct.load_traceability(traceability_yaml)
        assert len(reqs) == 2
        assert reqs[0].id == "BR-01"
        assert reqs[0].description == "Robot reaches goal within 0.15m"
        assert reqs[0].tests == ["tests/test_navigation.py::test_goal_position_error"]

    def test_exits_2_on_missing_file(self, tmp_path):
        with pytest.raises(SystemExit) as exc:
            ct.load_traceability(tmp_path / "nonexistent.yaml")
        assert exc.value.code == 2

    def test_exits_2_on_malformed_yaml(self, tmp_path):
        bad = tmp_path / "bad.yaml"
        bad.write_text("requirements: [invalid: {")
        with pytest.raises(SystemExit) as exc:
            ct.load_traceability(bad)
        assert exc.value.code == 2


# ---------------------------------------------------------------------------
# load_profile
# ---------------------------------------------------------------------------

class TestLoadProfile:
    def test_returns_empty_set_when_no_skips(self, profile_yaml):
        assert ct.load_profile(profile_yaml) == set()

    def test_returns_skip_ids(self, profile_yaml_with_skip):
        assert ct.load_profile(profile_yaml_with_skip) == {"BR-02"}

    def test_exits_2_on_missing_profile(self, tmp_path):
        with pytest.raises(SystemExit) as exc:
            ct.load_profile(tmp_path / "missing.yaml")
        assert exc.value.code == 2
```

- [ ] **Step 2: Run tests — verify they fail with ImportError (file doesn't exist yet)**

```bash
source ~/fleet-env/bin/activate
python -m pytest tests/test_check_traceability.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError: No module named 'check_traceability'`

- [ ] **Step 3: Create `tools/check_traceability.py` with skeleton, logging, and loading functions**

```python
# Copyright 2026 Mike. Licensed under MIT.
"""Stage 0 CI gate: every requirement ID must map to a test that exists."""
import argparse
import ast
import json
import logging
import sys
from pathlib import Path
from typing import NamedTuple

import yaml

log = logging.getLogger(__name__)


class Requirement(NamedTuple):
    id: str
    description: str
    tests: list


class Result(NamedTuple):
    covered: list
    missing: list
    skipped: list
    orphans: list


def setup_logging(debug: bool) -> None:
    """Configure logging: DEBUG to stderr when --debug, else WARNING only."""
    level = logging.DEBUG if debug else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(levelname)s: %(message)s",
        stream=sys.stderr,
    )


def load_traceability(path: Path) -> list:
    """Load requirements/traceability.yaml. Calls sys.exit(2) on any error."""
    try:
        data = yaml.safe_load(path.read_text())
    except Exception as exc:
        log.error("Cannot load %s: %s", path, exc)
        sys.exit(2)
    requirements = []
    for req in data.get("requirements", []):
        requirements.append(Requirement(
            id=req["id"],
            description=req.get("description", ""),
            tests=req.get("tests", []),
        ))
    log.debug("Loaded %d requirements from %s", len(requirements), path)
    return requirements


def load_profile(path: Path) -> set:
    """Load skip_requirements list from robot profile YAML. sys.exit(2) on error."""
    try:
        data = yaml.safe_load(path.read_text())
    except Exception as exc:
        log.error("Cannot load profile %s: %s", path, exc)
        sys.exit(2)
    skip = set(data.get("skip_requirements", []))
    log.debug("Profile %s: skipping %s", path.stem, skip or "nothing")
    return skip
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
python -m pytest tests/test_check_traceability.py::TestLoadTraceability \
                 tests/test_check_traceability.py::TestLoadProfile -v
```

Expected: 6 PASSED

- [ ] **Step 5: Commit**

```bash
git add tools/check_traceability.py tests/test_check_traceability.py
git commit -m "feat: check_traceability skeleton — Requirement/Result types, logging, YAML loading"
```

---

## Task 3: AST Test Scanner

**Files:**
- Modify: `tools/check_traceability.py` — add `scan_tests()`
- Modify: `tests/test_check_traceability.py` — add `TestScanTests`

**Interfaces:**
- Consumes: `test_dir: Path`
- Produces: `scan_tests(test_dir: Path) -> set[str]` — returns `{"tests/module.py::test_func", ...}`
  - IDs are relative to `test_dir.parent` (e.g., if test_dir is `tests/`, IDs start with `tests/`)

- [ ] **Step 1: Write failing tests for `scan_tests`**

Append to `tests/test_check_traceability.py` (inside the file, after `TestLoadProfile`):

```python
# ---------------------------------------------------------------------------
# scan_tests
# ---------------------------------------------------------------------------

class TestScanTests:
    def test_finds_test_functions(self, test_dir_full):
        found = ct.scan_tests(test_dir_full)
        assert "tests/test_navigation.py::test_goal_position_error" in found
        assert "tests/test_navigation.py::test_zero_collisions" in found

    def test_ignores_non_test_functions(self, test_dir_full):
        found = ct.scan_tests(test_dir_full)
        assert not any("helper" in t for t in found)

    def test_empty_directory_returns_empty_set(self, tmp_path):
        d = tmp_path / "tests"
        d.mkdir()
        assert ct.scan_tests(d) == set()

    def test_gracefully_skips_syntax_error_files(self, tmp_path):
        d = tmp_path / "tests"
        d.mkdir()
        (d / "test_broken.py").write_text("def test_ok(): pass\ndef broken(: !!!")
        result = ct.scan_tests(d)
        assert isinstance(result, set)  # did not raise
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
python -m pytest tests/test_check_traceability.py::TestScanTests -v
```

Expected: `AttributeError: module 'check_traceability' has no attribute 'scan_tests'`

- [ ] **Step 3: Implement `scan_tests` in `tools/check_traceability.py`**

Add after `load_profile()`:

```python
def scan_tests(test_dir: Path) -> set:
    """Return all 'tests/module.py::func_name' IDs found in test_dir.

    IDs are relative to test_dir.parent so they match traceability.yaml entries
    (e.g. test_dir=tests/ → ID starts with 'tests/').
    """
    found = set()
    for test_file in sorted(test_dir.rglob("test_*.py")):
        log.debug("Scanning %s", test_file)
        try:
            tree = ast.parse(test_file.read_text())
        except SyntaxError as exc:
            log.warning("Skipping %s — syntax error: %s", test_file, exc)
            continue
        rel = test_file.relative_to(test_dir.parent)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                tid = f"{rel}::{node.name}"
                found.add(tid)
                log.debug("  found %s", tid)
    log.debug("Total test functions found: %d", len(found))
    return found
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
python -m pytest tests/test_check_traceability.py::TestScanTests -v
```

Expected: 4 PASSED

- [ ] **Step 5: Commit**

```bash
git add tools/check_traceability.py tests/test_check_traceability.py
git commit -m "feat: check_traceability — scan_tests() AST scanner"
```

---

## Task 4: Coverage Check + Orphan Detection

**Files:**
- Modify: `tools/check_traceability.py` — add `check_coverage()`, `find_orphans()`
- Modify: `tests/test_check_traceability.py` — add `TestCheckCoverage`, `TestFindOrphans`

**Interfaces:**
- Consumes: `list[Requirement]`, `set[str]` (existing tests), `set[str]` (skip IDs)
- Produces:
  - `find_orphans(existing: set, all_mapped: set) -> list[str]`
  - `check_coverage(requirements: list, existing: set, skip_ids: set) -> Result`
    - A requirement is `covered` when ALL its listed tests exist in `existing`
    - A requirement is `skipped` when its ID is in `skip_ids`
    - A requirement is `missing` otherwise

- [ ] **Step 1: Write failing tests**

Append to `tests/test_check_traceability.py`:

```python
# ---------------------------------------------------------------------------
# find_orphans
# ---------------------------------------------------------------------------

class TestFindOrphans:
    def test_no_orphans_when_all_mapped(self):
        existing = {"tests/test_nav.py::test_foo"}
        mapped = {"tests/test_nav.py::test_foo"}
        assert ct.find_orphans(existing, mapped) == []

    def test_finds_unmapped_test(self):
        existing = {"tests/test_nav.py::test_foo", "tests/test_nav.py::test_bar"}
        mapped = {"tests/test_nav.py::test_foo"}
        assert ct.find_orphans(existing, mapped) == ["tests/test_nav.py::test_bar"]

    def test_returns_sorted_list(self):
        existing = {"tests/z.py::test_z", "tests/a.py::test_a"}
        assert ct.find_orphans(existing, set()) == [
            "tests/a.py::test_a",
            "tests/z.py::test_z",
        ]


# ---------------------------------------------------------------------------
# check_coverage
# ---------------------------------------------------------------------------

class TestCheckCoverage:
    def _reqs(self):
        return [
            Requirement("BR-01", "desc1",
                        ["tests/test_navigation.py::test_goal_position_error"]),
            Requirement("BR-02", "desc2",
                        ["tests/test_navigation.py::test_zero_collisions"]),
        ]

    def test_all_covered(self, test_dir_full):
        existing = ct.scan_tests(test_dir_full)
        result = ct.check_coverage(self._reqs(), existing, set())
        assert len(result.covered) == 2
        assert len(result.missing) == 0
        assert len(result.skipped) == 0

    def test_partial_coverage_marks_missing(self, test_dir_partial):
        existing = ct.scan_tests(test_dir_partial)
        result = ct.check_coverage(self._reqs(), existing, set())
        assert len(result.covered) == 1
        assert len(result.missing) == 1
        assert result.missing[0].id == "BR-02"

    def test_skipped_requirements_not_in_missing(self, test_dir_partial):
        existing = ct.scan_tests(test_dir_partial)
        result = ct.check_coverage(self._reqs(), existing, {"BR-02"})
        assert len(result.skipped) == 1
        assert result.skipped[0].id == "BR-02"
        assert len(result.missing) == 0

    def test_unmapped_test_becomes_orphan(self, test_dir_full):
        # test_dir_full has test_zero_collisions; only map BR-01
        existing = ct.scan_tests(test_dir_full)
        reqs = [Requirement("BR-01", "d",
                            ["tests/test_navigation.py::test_goal_position_error"])]
        result = ct.check_coverage(reqs, existing, set())
        assert "tests/test_navigation.py::test_zero_collisions" in result.orphans
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
python -m pytest tests/test_check_traceability.py::TestFindOrphans \
                 tests/test_check_traceability.py::TestCheckCoverage -v
```

Expected: `AttributeError: module 'check_traceability' has no attribute 'find_orphans'`

- [ ] **Step 3: Implement `find_orphans` and `check_coverage` in `tools/check_traceability.py`**

Add after `scan_tests()`:

```python
def find_orphans(existing: set, all_mapped: set) -> list:
    """Return sorted list of test IDs that exist but are not mapped to any requirement."""
    return sorted(existing - all_mapped)


def check_coverage(requirements: list, existing: set, skip_ids: set) -> Result:
    """Classify each requirement as covered, missing, or skipped.

    A requirement is covered when ALL its listed tests exist in existing.
    Skipped requirements (per robot profile) count neither covered nor missing.
    Orphans are tests that exist but are not referenced by any non-skipped requirement.
    """
    covered, missing, skipped = [], [], []
    all_mapped: set = set()

    for req in requirements:
        if req.id in skip_ids:
            skipped.append(req)
            log.debug("SKIP %s (robot profile)", req.id)
            continue
        req_test_set = set(req.tests)
        all_mapped.update(req_test_set)
        if req_test_set.issubset(existing):
            covered.append(req)
            log.debug("OK   %s", req.id)
        else:
            missing.append(req)
            log.debug("MISS %s — absent: %s", req.id, req_test_set - existing)

    orphans = find_orphans(existing, all_mapped)
    if orphans:
        log.debug("Orphan tests found: %s", orphans)
    return Result(covered=covered, missing=missing, skipped=skipped, orphans=orphans)
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
python -m pytest tests/test_check_traceability.py::TestFindOrphans \
                 tests/test_check_traceability.py::TestCheckCoverage -v
```

Expected: 7 PASSED

- [ ] **Step 5: Commit**

```bash
git add tools/check_traceability.py tests/test_check_traceability.py
git commit -m "feat: check_traceability — check_coverage() and find_orphans()"
```

---

## Task 5: Output Formatters

**Files:**
- Modify: `tools/check_traceability.py` — add `_print_summary()`, `format_rich()`, `format_quiet()`, `format_json()`
- Modify: `tests/test_check_traceability.py` — add `TestFormatJson`, `TestFormatRich`, `TestFormatQuiet`

**Interfaces:**
- Consumes: `Result`, optional `git_sha: str | None`, optional `profile_name: str | None`
- Produces:
  - `_print_summary(result: Result) -> None` — prints one-line summary to stdout
  - `format_rich(result: Result, profile_name: str | None) -> None` — prints to stdout
  - `format_quiet(result: Result) -> None` — prints to stdout
  - `format_json(result: Result, git_sha: str | None, profile_name: str | None) -> str` — returns JSON string

- [ ] **Step 1: Write failing tests**

Append to `tests/test_check_traceability.py`:

```python
# ---------------------------------------------------------------------------
# Output formatters
# ---------------------------------------------------------------------------

def _make_full_result():
    return Result(
        covered=[Requirement("BR-01", "Robot reaches goal", ["tests/t.py::test_foo"])],
        missing=[Requirement("BR-02", "Zero collisions", ["tests/t.py::test_bar"])],
        skipped=[Requirement("BR-03", "Recovery timeout", ["tests/t.py::test_baz"])],
        orphans=["tests/t.py::test_orphan"],
    )


class TestFormatJson:
    def test_required_top_level_keys(self):
        result = _make_full_result()
        data = json.loads(ct.format_json(result, "abc123", "jetson_ugv_pt"))
        assert data["git_sha"] == "abc123"
        assert data["profile"] == "jetson_ugv_pt"
        assert "summary" in data
        assert "requirements" in data
        assert "orphans" in data

    def test_summary_counts(self):
        result = _make_full_result()
        data = json.loads(ct.format_json(result, "sha1", None))
        assert data["summary"]["covered"] == 1
        assert data["summary"]["missing"] == 1
        assert data["summary"]["skipped"] == 1
        assert data["summary"]["orphans"] == 1
        assert data["summary"]["total"] == 3  # covered + missing + skipped

    def test_requirement_status_field(self):
        result = _make_full_result()
        data = json.loads(ct.format_json(result, "sha1", None))
        statuses = {r["id"]: r["status"] for r in data["requirements"]}
        assert statuses["BR-01"] == "covered"
        assert statuses["BR-02"] == "missing"
        assert statuses["BR-03"] == "skipped"

    def test_orphans_list(self):
        result = _make_full_result()
        data = json.loads(ct.format_json(result, "sha1", None))
        assert data["orphans"] == ["tests/t.py::test_orphan"]

    def test_null_git_sha_falls_back_gracefully(self):
        result = Result(covered=[], missing=[], skipped=[], orphans=[])
        data = json.loads(ct.format_json(result, None, None))
        assert isinstance(data["git_sha"], str)  # falls back to env or "unknown"


class TestFormatRich:
    def test_covered_requirement_shown(self, capsys):
        result = Result(
            covered=[Requirement("BR-01", "Robot reaches goal", ["tests/t.py::test_foo"])],
            missing=[], skipped=[], orphans=[],
        )
        ct.format_rich(result, None)
        out = capsys.readouterr().out
        assert "BR-01" in out
        assert "Robot reaches goal" in out

    def test_missing_requirement_shown(self, capsys):
        result = Result(
            covered=[],
            missing=[Requirement("BR-02", "Zero collisions", ["tests/t.py::test_bar"])],
            skipped=[], orphans=[],
        )
        ct.format_rich(result, None)
        out = capsys.readouterr().out
        assert "BR-02" in out
        assert "Zero collisions" in out

    def test_orphan_warning_shown(self, capsys):
        result = Result(covered=[], missing=[], skipped=[],
                        orphans=["tests/t.py::test_orphan"])
        ct.format_rich(result, None)
        out = capsys.readouterr().out
        assert "test_orphan" in out


class TestFormatQuiet:
    def test_covered_shows_ok(self, capsys):
        result = Result(
            covered=[Requirement("BR-01", "desc", ["tests/t.py::test_foo"])],
            missing=[], skipped=[], orphans=[],
        )
        ct.format_quiet(result)
        assert "OK" in capsys.readouterr().out

    def test_missing_shows_fail(self, capsys):
        result = Result(
            covered=[],
            missing=[Requirement("BR-02", "desc", ["tests/t.py::test_bar"])],
            skipped=[], orphans=[],
        )
        ct.format_quiet(result)
        assert "FAIL" in capsys.readouterr().out
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
python -m pytest tests/test_check_traceability.py::TestFormatJson \
                 tests/test_check_traceability.py::TestFormatRich \
                 tests/test_check_traceability.py::TestFormatQuiet -v
```

Expected: `AttributeError: module 'check_traceability' has no attribute 'format_json'`

- [ ] **Step 3: Implement formatters in `tools/check_traceability.py`**

Add after `check_coverage()`:

```python
def _print_summary(result: Result) -> None:
    total = len(result.covered) + len(result.missing) + len(result.skipped)
    parts = [f"{len(result.covered)}/{total} requirements covered"]
    if result.skipped:
        parts.append(f"{len(result.skipped)} skipped by profile")
    if result.orphans:
        parts.append(f"{len(result.orphans)} orphan test(s)")
    print("  ".join(parts))


def format_rich(result: Result, profile_name) -> None:
    """Human-readable output with requirement text inline."""
    if profile_name:
        print(f"Profile: {profile_name}")
    print()
    for req in result.covered:
        print(f"  ✓  {req.id}  [{req.description}]")
        for test in req.tests:
            print(f"       {test}")
    for req in result.skipped:
        print(f"  –  {req.id}  [{req.description}]  (skipped by profile)")
    for req in result.missing:
        print(f"  ✗  {req.id}  [{req.description}]")
        for test in req.tests:
            print(f"       MISSING: {test}")
    if result.orphans:
        print()
        print("  Orphan tests (exist but not mapped to any requirement):")
        for t in result.orphans:
            print(f"    ⚠  {t}")
    print()
    _print_summary(result)


def format_quiet(result: Result) -> None:
    """Terse output — IDs and status only."""
    for req in result.covered:
        print(f"OK    {req.id}")
    for req in result.skipped:
        print(f"SKIP  {req.id}")
    for req in result.missing:
        print(f"FAIL  {req.id}")
    for t in result.orphans:
        print(f"WARN  ORPHAN {t}")
    _print_summary(result)


def format_json(result: Result, git_sha, profile_name) -> str:
    """Machine-readable JSON for stdout redirect and CI artifact upload."""
    import os
    sha = git_sha or os.environ.get("GITHUB_SHA", "unknown")

    def _req_dict(req: Requirement, status: str) -> dict:
        return {
            "id": req.id,
            "description": req.description,
            "status": status,
            "tests": req.tests,
        }

    return json.dumps({
        "git_sha": sha,
        "profile": profile_name,
        "summary": {
            "total": len(result.covered) + len(result.missing) + len(result.skipped),
            "covered": len(result.covered),
            "missing": len(result.missing),
            "skipped": len(result.skipped),
            "orphans": len(result.orphans),
        },
        "requirements": (
            [_req_dict(r, "covered") for r in result.covered]
            + [_req_dict(r, "missing") for r in result.missing]
            + [_req_dict(r, "skipped") for r in result.skipped]
        ),
        "orphans": result.orphans,
    }, indent=2)
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
python -m pytest tests/test_check_traceability.py::TestFormatJson \
                 tests/test_check_traceability.py::TestFormatRich \
                 tests/test_check_traceability.py::TestFormatQuiet -v
```

Expected: 11 PASSED

- [ ] **Step 5: Commit**

```bash
git add tools/check_traceability.py tests/test_check_traceability.py
git commit -m "feat: check_traceability — format_rich, format_quiet, format_json output modes"
```

---

## Task 6: CLI Entry Point + Integration Tests

**Files:**
- Modify: `tools/check_traceability.py` — add `main()` + `if __name__ == "__main__"` block
- Modify: `tests/test_check_traceability.py` — add `TestMainCLI`

**Interfaces:**
- Consumes: `sys.argv`
- Produces:
  - `main() -> int` — returns 0, 1. Calls `sys.exit(2)` directly for config errors.
  - Script callable as `python tools/check_traceability.py <args>`

- [ ] **Step 1: Write failing integration tests**

Append to `tests/test_check_traceability.py`:

```python
# ---------------------------------------------------------------------------
# main() integration tests
# ---------------------------------------------------------------------------

class TestMainCLI:
    def test_exit_0_when_all_covered(self, traceability_yaml, test_dir_full):
        with patch("sys.argv", [
            "check_traceability.py",
            str(traceability_yaml),
            str(test_dir_full),
        ]):
            rc = ct.main()
        assert rc == 0

    def test_exit_1_when_requirement_missing(self, traceability_yaml, test_dir_partial):
        with patch("sys.argv", [
            "check_traceability.py",
            str(traceability_yaml),
            str(test_dir_partial),
        ]):
            rc = ct.main()
        assert rc == 1

    def test_exit_2_on_missing_traceability_file(self, tmp_path, test_dir_full):
        with patch("sys.argv", [
            "check_traceability.py",
            str(tmp_path / "nonexistent.yaml"),
            str(test_dir_full),
        ]):
            with pytest.raises(SystemExit) as exc:
                ct.main()
        assert exc.value.code == 2

    def test_exit_2_on_missing_test_dir(self, traceability_yaml, tmp_path):
        with patch("sys.argv", [
            "check_traceability.py",
            str(traceability_yaml),
            str(tmp_path / "nonexistent_dir"),
        ]):
            with pytest.raises(SystemExit) as exc:
                ct.main()
        assert exc.value.code == 2

    def test_json_flag_produces_valid_json(self, traceability_yaml, test_dir_full, capsys):
        with patch("sys.argv", [
            "check_traceability.py",
            str(traceability_yaml),
            str(test_dir_full),
            "--json",
        ]):
            ct.main()
        data = json.loads(capsys.readouterr().out)
        assert "summary" in data
        assert data["summary"]["covered"] == 2

    def test_profile_skip_makes_partial_pass(
        self, traceability_yaml, test_dir_partial, profile_yaml_with_skip
    ):
        """BR-02 skipped by profile + BR-01 covered → exit 0 despite partial tests."""
        with patch("sys.argv", [
            "check_traceability.py",
            str(traceability_yaml),
            str(test_dir_partial),
            "--profile", str(profile_yaml_with_skip),
        ]):
            rc = ct.main()
        assert rc == 0

    def test_orphans_do_not_affect_exit_code(self, traceability_yaml, test_dir_full, capsys):
        """Extra test in test_dir_full that isn't in traceability → warning, exit 0."""
        extra_test_dir = test_dir_full
        # Add an extra unmapped test to the test dir
        (extra_test_dir / "test_extra.py").write_text("def test_unmapped(): pass\n")
        with patch("sys.argv", [
            "check_traceability.py",
            str(traceability_yaml),
            str(extra_test_dir),
        ]):
            rc = ct.main()
        assert rc == 0
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
python -m pytest tests/test_check_traceability.py::TestMainCLI -v
```

Expected: `AttributeError: module 'check_traceability' has no attribute 'main'`

- [ ] **Step 3: Implement `main()` in `tools/check_traceability.py`**

Add at the bottom of the file:

```python
def main() -> int:
    """CLI entry point. Returns 0 (clean), 1 (missing requirements).
    Calls sys.exit(2) directly for configuration/tool errors.
    """
    parser = argparse.ArgumentParser(
        description="Stage 0 CI gate: every requirement must have a matching test.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Exit codes:\n"
            "  0  All requirements covered (orphan warnings do not affect exit)\n"
            "  1  One or more requirements have no matching test\n"
            "  2  Tool error: bad YAML, missing file, unreadable test\n"
        ),
    )
    parser.add_argument("traceability", help="Path to traceability.yaml")
    parser.add_argument("test_dir", help="Path to tests/ directory")
    parser.add_argument(
        "--profile", help="Robot profile YAML (enables skip_requirements filtering)"
    )
    parser.add_argument(
        "--quiet", action="store_true", help="Terse output — IDs and status only"
    )
    parser.add_argument(
        "--json", action="store_true", help="Machine-readable JSON to stdout"
    )
    parser.add_argument(
        "--debug", action="store_true", help="Verbose DEBUG logging to stderr"
    )
    args = parser.parse_args()

    setup_logging(args.debug)

    traceability_path = Path(args.traceability)
    test_dir = Path(args.test_dir)

    if not traceability_path.exists():
        log.error("Not found: %s", traceability_path)
        sys.exit(2)
    if not test_dir.is_dir():
        log.error("Not a directory: %s", test_dir)
        sys.exit(2)

    requirements = load_traceability(traceability_path)

    skip_ids: set = set()
    profile_name = None
    if args.profile:
        profile_path = Path(args.profile)
        if not profile_path.exists():
            log.error("Profile not found: %s", profile_path)
            sys.exit(2)
        skip_ids = load_profile(profile_path)
        profile_name = profile_path.stem

    existing = scan_tests(test_dir)
    result = check_coverage(requirements, existing, skip_ids)

    if args.json:
        print(format_json(result, None, profile_name))
    elif args.quiet:
        format_quiet(result)
    else:
        format_rich(result, profile_name)

    return 1 if result.missing else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run all tests — verify they pass**

```bash
python -m pytest tests/test_check_traceability.py -v
```

Expected: All tests PASSED (no failures)

- [ ] **Step 5: Smoke test against the real project files**

```bash
python tools/check_traceability.py requirements/traceability.yaml tests/ \
  --profile robot_profiles/jetson_ugv_pt.yaml
```

Expected output (rich mode, missing tests are expected at this stage):
```
Profile: jetson_ugv_pt

  –  BR-04  [/robot_001/odom publishes at >= 50 Hz]  (skipped by profile)
  ...
  ✗  BR-01  [Robot reaches goal within 0.15m Euclidean distance]
       MISSING: tests/test_navigation.py::test_goal_position_error
  ...
  ⚠  tests/test_baseline.py::test_nav_success_rate_drift  (orphan — not yet mapped)
  ...
X/8 requirements covered  ...
```

> **Note:** Many tests don't exist yet (they're built in Sessions 09–10). Missing requirements and orphan warnings are expected here. Exit code 1 is correct at this stage.

- [ ] **Step 6: Verify `--json` mode works**

```bash
python tools/check_traceability.py requirements/traceability.yaml tests/ \
  --profile robot_profiles/jetson_ugv_pt.yaml --json | python -m json.tool | head -20
```

Expected: Valid JSON printed with `git_sha`, `profile`, `summary`, `requirements`, `orphans` keys.

- [ ] **Step 7: Verify `--debug` goes to stderr, not stdout**

```bash
python tools/check_traceability.py requirements/traceability.yaml tests/ \
  --json --debug > /tmp/traceability.json 2> /tmp/traceability_debug.log
echo "stdout lines: $(wc -l < /tmp/traceability.json)"
echo "stderr lines: $(wc -l < /tmp/traceability_debug.log)"
```

Expected: stdout contains only JSON; debug lines are in the log file.

- [ ] **Step 8: Commit**

```bash
git add tools/check_traceability.py tests/test_check_traceability.py
git commit -m "feat: check_traceability — main() CLI, argparse, exit codes, integration tests"
```

---

## Task 7: Wire Stage 0 into CI

**Files:**
- Modify: `.github/workflows/ci.yml` — replace Stage 0 stub with real job

**Interfaces:**
- Consumes: `tools/check_traceability.py` (all tasks above)
- Produces: Stage 0 CI job that runs the tool, captures JSON artifact, continues on error until Session 10

- [ ] **Step 1: Replace the Stage 0 stub in `.github/workflows/ci.yml`**

Replace this block:

```yaml
  stage-0-requirements:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: echo "Stage 0 stub — implement in Session 06"
```

With:

```yaml
  stage-0-requirements:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install dependencies
        run: pip install pyyaml

      - name: Traceability gate
        run: |
          python tools/check_traceability.py \
            requirements/traceability.yaml \
            tests/ \
            --profile robot_profiles/jetson_ugv_pt.yaml \
            --json > reports/traceability_latest.json
          cat reports/traceability_latest.json
        continue-on-error: true
        # ↑ Remove continue-on-error in Session 10 once all Session 09 tests pass

      - name: Upload traceability report
        uses: actions/upload-artifact@v4
        if: always()
        with:
          name: traceability-report
          path: reports/traceability_latest.json
```

- [ ] **Step 2: Run the full test suite to confirm nothing is broken**

```bash
source ~/fleet-env/bin/activate
python -m pytest tests/ -v --ignore=tests/test_ros2_contracts.py
```

Expected: All non-ROS2 tests pass. (`test_ros2_contracts.py` requires a live ROS2 environment — excluded here, same as Session 07 plan.)

- [ ] **Step 3: Commit and push**

```bash
git add .github/workflows/ci.yml
git commit -m "feat: Stage 0 CI job — check_traceability wired into GitHub Actions with artifact upload"
git push
```

- [ ] **Step 4: Verify CI triggers and Stage 0 runs**

```bash
gh run list --limit 3
```

Wait ~2 minutes, then:

```bash
gh run watch
```

Expected: Stage 0 job completes. It will show as yellow/warning (continue-on-error) because test_navigation.py tests don't exist yet. The traceability artifact is uploaded.

- [ ] **Step 5: Download and inspect the CI artifact**

```bash
gh run download --name traceability-report --dir /tmp/ci-artifact
cat /tmp/ci-artifact/traceability_latest.json | python -m json.tool
```

Expected: Valid JSON with `summary.missing > 0` (expected — those tests come in Session 09).

---

## Self-Review Checklist

**Spec coverage:**
- ✓ Rich output with description inline (Task 5 `format_rich`)
- ✓ `--quiet` terse mode (Task 5 `format_quiet`)
- ✓ `--json` machine-readable stdout (Task 5 `format_json`)
- ✓ `--debug` logging to stderr (Task 2 `setup_logging`)
- ✓ Exit codes 0/1/2 (Task 6 `main()`)
- ✓ Bidirectional: orphans as warnings, exit 0 (Task 4 `find_orphans`, Task 6 tests)
- ✓ `description` field in traceability.yaml (Task 1)
- ✓ `skip_requirements` in robot profile YAML (Task 1)
- ✓ Profile filtering data-driven, not hardcoded (Task 4 `check_coverage`)
- ✓ Single file, clear function boundaries (architecture: Option B)
- ✓ `--json > reports/traceability_latest.json` CI pattern (Task 7)
- ✓ `reports/traceability_latest.json` gitignored (Task 1)
- ✓ Artifact upload in CI (Task 7)
- ✓ `continue-on-error: true` until Session 10 (Task 7, comment in YAML)
- ✓ `git_sha` not `run_id` in JSON output (Task 5 `format_json`)
- ✓ Copyright header on both new files (Task 2, Task 3 — check_traceability.py has it; test file has it)

**Type consistency:** `Requirement` and `Result` NamedTuples defined in Task 2, used consistently in Tasks 3–6. `format_json` uses `_req_dict()` helper to avoid repeating the dict shape. ✓

**No placeholders:** All steps contain actual code or exact commands. ✓
