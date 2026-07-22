# Piece 4 — Per-CI-Run Reporting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the two identical, unscoped "last 100 runs" PDF reports with two
genuinely distinct, per-run reports (sim, HIL) that show only that run's own results,
a real drift comparison against baseline, that run's own mission photo(s), and land
both a GitHub Job Summary and a correctly-named downloadable PDF — with a 30-day
retention policy and the rosbag failure bags finally visible on GitHub.

**Architecture:** `tools/generate_test_report.py` is rescoped from a blanket historical
dump to a per-run report generator: given a `runner_type` and a list of `scenarios`,
it loads the single latest row per scenario (that stage's own results), computes drift
via the now-scenario-aware `baseline_monitor.check_run()`, and builds a PDF + a GitHub
Job Summary from that. `ci.yml`'s two `stage-5-reports-*` jobs pass their own
runner_type/scenario list explicitly instead of relying on an implicit "last 100" query.

**Tech Stack:** Python 3, `reportlab` (PDF), `sqlite3` (stdlib), pytest, GitHub Actions
(`ci.yml`).

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-21-session17-piece4-reporting-design.md`
  (approved by Mike, 2026-07-21) — implements it exactly; do not add scope beyond it.
- Depends on the Foundation piece, already merged (`main` @ `ca5aa06`) — one
  consolidated `FLEET_DB`, `tools/telemetry_logger.DB_PATH` is the schema+path owner.
- TDD is this project's norm: write the failing test before the implementation for
  every behavioral change.
- Drift stays informational only — a flagged metric never fails a CI job.
  `baseline_monitor` stays exit-0 always; this plan does not change that.
- No historical trend charts in the per-run report (removed, not just left unused) —
  that content belongs to Piece 5's dashboard, designed separately.
- Report content is per-run only: this run's own scenario(s), PASS/FAIL, its own
  metric values, its own drift comparison, its own photo(s).

## Design decision made while writing this plan (flag for review)

The spec says reports are "filtered by runner_type plus the run's own scenario(s)"
but doesn't specify the exact row-selection mechanic. Two facts from the current
codebase pin this down:
- `stage-2-gazebo` produces telemetry rows for exactly two scenarios:
  `bedroom_nav` (`tests/test_navigation.py:58-59`) and `mission1`
  (`src/nav_fleet/nav_fleet/mission_runner.py`, invoked by `tests/test_mission_run.py`),
  both logged with `runner_type='local'` (the `RUNNER_TYPE` env default).
- `stage-4-hil` produces rows for exactly three scenarios:
  `mission2_no_ball`, `mission2_yellow`, `mission2_red`
  (`tools/mission2_harness.py:443`, `scenario=f'mission2_{variant}'`), all logged with
  `runner_type='hil_jetson'`.

So **"this run's own result" = the single most recent row for each of that stage's
known scenarios, filtered by runner_type.** This is deterministic and needs no new
cross-job state-passing in `ci.yml` (GitHub Actions jobs don't share env vars; passing
a row-id watermark between jobs would need the `needs.<job>.outputs` mechanism, which
this plan deliberately avoids as unnecessary complexity for a single shared runner).

**Photo correlation is the other unresolved piece the spec left implicit.** There is
no DB column linking a run row to its photo file(s) — photos are saved by
`nav_fleet/mission_runner.py:take_picture()` as
`reports/photos/{label}_{%Y%m%d_%H%M%S}.png`, where `label` doesn't always match the
row's `scenario` string exactly (e.g. Mission 2's reaction photos are labeled
`mission2_reaction_red`, not `mission2_red`). Parsing every label convention to match
scenarios exactly would be its own small feature. This plan uses a simpler, more
robust signal instead: **time-window correlation** — a photo taken in the seconds
immediately before a row's own `timestamp` almost certainly belongs to that row's
mission, since missions run sequentially on one machine and each takes well under the
window. This needs no knowledge of label conventions and doesn't break if a label
changes. Flagging this explicitly: if this correlation approach doesn't match what you
pictured, this is the task (Task 4) to redirect before merging.

---

### Task 1: Scenario-aware baseline slicing (prerequisite)

**Files:**
- Modify: `tools/baseline_monitor.py:123` (`slice_cols` in `check_run`)
- Test: `tests/test_baseline.py`

**Interfaces:**
- Produces: `check_run()`'s baseline window is now sliced by
  `(runner_type, power_mode, scenario)` instead of just `(runner_type, power_mode)`.
  No signature change — later tasks call `check_run(row_id, ...)` exactly as today.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_baseline.py`, after `test_null_power_rows_baseline_against_each_other`:

```python
def test_baseline_sliced_by_scenario(db):
    """Piece 4 prerequisite: mixing scenarios in one baseline window produces a false
    drift signal from the scenario mix shifting, not from anything actually getting
    worse — scenario must be sliced exactly like runner_type/power_mode already are.
    Two well-separated cohorts, same runner_type/power_mode, different scenario."""
    for rate in _COHORT_HI:
        _insert(db, nav_success_rate=rate, runner_type="hil_jetson", power_mode="15W")
    for rate in _COHORT_LO:
        _insert(db, nav_success_rate=rate, runner_type="hil_jetson", power_mode="15W")

    # Without scenario slicing this fails: both cohorts share (runner_type, power_mode),
    # so a naive baseline would mix them into one ~0.72-mean pool and nothing would flag.
```

That test as written can't actually distinguish cohorts by scenario yet, because
`_insert()` in `tests/test_baseline.py` doesn't take a `scenario` argument (it hardcodes
`scenario="baseline_test"` inside `log_run`, per `tests/test_baseline.py:38-53`).
Extend `_insert()` first — add a `scenario="baseline_test"` parameter and pass it
through to `log_run`:

```python
def _insert(
    db_path,
    nav_success_rate=0.95,
    steps=100,
    result="PASS",
    mean_position_error=0.12,
    collision_rate=0.0,
    odom_hz_mean=50.0,
    camera_hz_mean=20.0,
    runner_type=None,
    power_mode=None,
    scenario="baseline_test",
):
    return log_run(
        scenario=scenario,
        steps=steps,
        final_x=1.5,
        final_y=1.0,
        result=result,
        step_log=[],
        db_path=db_path,
        nav_success_rate=nav_success_rate,
        mean_position_error=mean_position_error,
        collision_rate=collision_rate,
        odom_hz_mean=odom_hz_mean,
        camera_hz_mean=camera_hz_mean,
        runner_type=runner_type,
        power_mode=power_mode,
    )
```

Now write the real test:

```python
def test_baseline_sliced_by_scenario(db):
    """Piece 4 prerequisite: mixing scenarios in one baseline window produces a false
    drift signal from the scenario mix shifting, not from anything actually getting
    worse. scenario must be sliced exactly like runner_type/power_mode already are.
    Same runner_type/power_mode for both cohorts — only scenario differs — so this
    fails today (scenario isn't in slice_cols yet) and passes once it is.
    """
    for rate in _COHORT_HI:
        _insert(db, nav_success_rate=rate, runner_type="hil_jetson", power_mode="15W",
                scenario="mission2_no_ball")
    for rate in _COHORT_LO:
        _insert(db, nav_success_rate=rate, runner_type="hil_jetson", power_mode="15W",
                scenario="mission2_red")

    # A mission2_red run at 0.95 (the OTHER cohort's value) is a huge outlier vs the
    # mission2_red baseline (~0.50) — flagged only if mission2_no_ball rows were
    # correctly excluded from this scenario's own baseline.
    red_run = _insert(db, nav_success_rate=0.95, runner_type="hil_jetson",
                       power_mode="15W", scenario="mission2_red")
    red_reports = {r.metric: r for r in check_run(red_run, db_path=db)}
    assert red_reports["nav_success_rate"].flagged
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_baseline.py::test_baseline_sliced_by_scenario -v`
Expected: FAIL — `nav_success_rate` isn't flagged, because without scenario slicing
the baseline mixes both cohorts (mean ~0.72), and 0.95 isn't far enough outside that
mixed pool to cross the `info` sigma band.

- [ ] **Step 3: Implement**

In `tools/baseline_monitor.py`, change line 123:

```python
    slice_cols = [c for c in ("runner_type", "power_mode") if c in available]
```

to:

```python
    slice_cols = [c for c in ("runner_type", "power_mode", "scenario") if c in available]
```

Also update the comment directly above it (currently lines 116-122) to mention the
third dimension:

```python
    # Compare like with like (Session 16 finding I4, extended Session 17 Piece 4): the
    # baseline window must only contain runs from the SAME execution context AND the
    # SAME mission scenario as the run under check — otherwise a mission2_red row
    # (which stops after one step) would drift-compare against mission2_no_ball history
    # (a full round trip), or a 15W hil_jetson row against 25W sim history, and every
    # metric would flag on the context/scenario delta, not on real drift. Slice on
    # (runner_type, power_mode, scenario). power_mode is NULL on all pre-Session-16 sim
    # rows, so a NULL-power run must baseline against NULL-power history: use `IS ?`
    # (NULL-safe equality in SQLite) rather than `= ?` (which never matches NULL).
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_baseline.py -v`
Expected: all PASS, including the new test and every pre-existing one (confirms
`scenario` slicing didn't break the `runner_type`/`power_mode` slicing tests, since
`_insert()`'s new `scenario` parameter defaults to `"baseline_test"` — the same value
every pre-existing call in this file already implicitly used).

- [ ] **Step 5: Commit**

```bash
git add tools/baseline_monitor.py tests/test_baseline.py
git commit -m "$(cat <<'EOF'
fix(drift): slice baseline window by scenario too, not just runner/power

Piece 4 prerequisite: mixing scenarios in one rolling baseline lets the
recent scenario mix masquerade as drift (mission2_red vs mission2_no_ball
have genuinely different expected metrics). Must land before the new
drift banner, or the banner cries wolf on scenario-mix artifacts instead
of real regressions.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Rescope report generation to one run's own results

**Files:**
- Modify: `tools/generate_test_report.py` (near-total rewrite of the body; keep the
  copyright header, `_RESULT_COLORS`, and the module's overall shape)
- Test: `tests/test_report_tools.py`

**Interfaces:**
- Produces: `load_run_rows(runner_type: str, scenarios: list[str], db_path: str = DB_PATH) -> list[dict]`
  — one dict per scenario (the latest row), in the order `scenarios` was given; a
  scenario with no matching row is silently omitted (not an error — e.g. a brand new
  scenario with no history yet).
- Produces: `generate_report(runner_type: str, scenarios: list[str], db_path: str = DB_PATH, output_path: str = REPORT_PATH, config_path: str = None) -> str`
  — returns the actual output path used (Task 3 changes this to sometimes differ from
  `output_path` via the `-DRIFT` suffix — not in this task yet).
- Consumes: `tools.baseline_monitor.check_run` (already scenario-aware after Task 1).

- [ ] **Step 1: Write the failing tests**

Replace the entire content of `tests/test_report_tools.py`:

```python
# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""Smoke tests for the Stage-5 reporting path (S17 Piece 4): telemetry rows in →
schema validation green → per-run PDF out, scoped to one runner_type's own scenarios."""
import os

from tools.telemetry_logger import init_db, log_run
from tools.validate_telemetry import detect_schema_drift, validate_runs, validate_steps


def _seed(db_path):
    for result, sim in (("PASS", 0.03), ("FAIL", 0.21)):
        log_run(scenario="mission2_no_ball", steps=5, final_x=-1.27, final_y=1.2,
                result=result, step_log=[{"step": 1, "x": 0.0, "y": 0.0}],
                db_path=db_path, runner_type="hil_jetson", power_mode="15W",
                nav_success_rate=1.0 if result == "PASS" else 0.0,
                home_photo_similarity=sim)


def test_validate_telemetry_green_on_real_logger_output(tmp_path):
    db = str(tmp_path / "t.db")
    init_db(db)
    _seed(db)
    assert validate_runs(db)
    assert validate_steps(db)
    assert detect_schema_drift(db)


def test_load_run_rows_returns_latest_per_scenario(tmp_path):
    db = str(tmp_path / "t.db")
    init_db(db)
    from tools.generate_test_report import load_run_rows
    # Two mission1 rows — the second (later) one must win.
    log_run(scenario="mission1", steps=3, final_x=0.0, final_y=0.0, result="FAIL",
            step_log=[], db_path=db, runner_type="local")
    log_run(scenario="mission1", steps=5, final_x=1.0, final_y=1.0, result="PASS",
            step_log=[], db_path=db, runner_type="local")
    log_run(scenario="bedroom_nav", steps=8, final_x=2.0, final_y=2.0, result="PASS",
            step_log=[], db_path=db, runner_type="local")
    rows = load_run_rows("local", ["bedroom_nav", "mission1"], db_path=db)
    by_scenario = {r["scenario"]: r for r in rows}
    assert by_scenario["mission1"]["result"] == "PASS"
    assert by_scenario["mission1"]["steps"] == 5
    assert by_scenario["bedroom_nav"]["result"] == "PASS"


def test_load_run_rows_skips_scenario_with_no_history(tmp_path):
    db = str(tmp_path / "t.db")
    init_db(db)
    from tools.generate_test_report import load_run_rows
    log_run(scenario="mission1", steps=5, final_x=0.0, final_y=0.0, result="PASS",
            step_log=[], db_path=db, runner_type="local")
    rows = load_run_rows("local", ["bedroom_nav", "mission1"], db_path=db)
    assert [r["scenario"] for r in rows] == ["mission1"]


def test_load_run_rows_respects_runner_type(tmp_path):
    db = str(tmp_path / "t.db")
    init_db(db)
    from tools.generate_test_report import load_run_rows
    log_run(scenario="mission1", steps=5, final_x=0.0, final_y=0.0, result="PASS",
            step_log=[], db_path=db, runner_type="hil_jetson")
    rows = load_run_rows("local", ["mission1"], db_path=db)
    assert rows == []


def test_generate_report_produces_pdf(tmp_path):
    db = str(tmp_path / "t.db")
    init_db(db)
    _seed(db)
    from tools.generate_test_report import generate_report
    out = str(tmp_path / "report.pdf")
    result_path = generate_report("hil_jetson", ["mission2_no_ball"], db_path=db,
                                   output_path=out)
    assert os.path.exists(result_path)
    assert os.path.getsize(result_path) > 1000  # a real PDF, not an empty stub


def test_generate_report_has_no_trend_chart_functions():
    """Piece 4 spec: no historical trend charts in the per-run report — that content
    moved to Piece 5's dashboard. Locks in the removal so it can't silently creep back."""
    import tools.generate_test_report as gtr
    assert not hasattr(gtr, "make_pass_fail_chart")
    assert not hasattr(gtr, "make_position_scatter")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_report_tools.py -v`
Expected: `test_load_run_rows_returns_latest_per_scenario`,
`test_load_run_rows_skips_scenario_with_no_history`,
`test_load_run_rows_respects_runner_type`, and
`test_generate_report_has_no_trend_chart_functions` all FAIL — `load_run_rows` doesn't
exist yet. `test_generate_report_produces_pdf` FAILs too, since `generate_report`'s
current signature is `(db_path, output_path)`, not `(runner_type, scenarios, ...)`.
`test_validate_telemetry_green_on_real_logger_output` still PASSes (untouched code path).

- [ ] **Step 3: Implement**

Replace the entire content of `tools/generate_test_report.py`:

```python
# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""Generate a per-run PDF report (+ GitHub Job Summary) scoped to one runner_type's
own scenarios — not a rolling window of the last N runs. Historical trend views live
in the Piece 5 dashboard, not here."""
import argparse
import os
import sqlite3
import sys
from datetime import datetime

# Plain-script safety — see tools/validate_telemetry.py for the why (same trap).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from tools.baseline_monitor import check_run  # noqa: E402
from tools.telemetry_logger import DB_PATH  # noqa: E402

REPORT_PATH = os.getenv(
    "REPORT_PATH",
    os.path.join(_PROJECT_ROOT, "reports", "test_report.pdf")
)

_RESULT_COLORS = {
    "PASS":    "#00cc44",
    "FAIL":    "#ff4444",
    "STOPPED": "#ff8800",
    "TIMEOUT": "#888888",
}

_TABLE_STYLE = TableStyle([
    ("BACKGROUND",   (0, 0), (-1, 0),  colors.grey),
    ("TEXTCOLOR",    (0, 0), (-1, 0),  colors.whitesmoke),
    ("FONTNAME",     (0, 0), (-1, 0),  "Helvetica-Bold"),
    ("GRID",         (0, 0), (-1, -1), 0.5, colors.black),
    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.lightgrey]),
])


def load_run_rows(runner_type: str, scenarios: list, db_path: str = DB_PATH) -> list:
    """The latest row for each of `scenarios`, filtered to `runner_type` — 'this run's
    own result(s)', not a rolling window. A scenario with no matching row is omitted."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = []
    for scenario in scenarios:
        row = conn.execute(
            "SELECT * FROM runs WHERE runner_type = ? AND scenario = ? "
            "ORDER BY id DESC LIMIT 1",
            (runner_type, scenario),
        ).fetchone()
        if row is not None:
            rows.append(dict(row))
    conn.close()
    return rows


def generate_report(runner_type: str, scenarios: list, db_path: str = DB_PATH,
                     output_path: str = REPORT_PATH, config_path: str = None) -> str:
    rows = load_run_rows(runner_type, scenarios, db_path=db_path)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    reports_by_row_id = {
        row["id"]: check_run(row["id"], db_path=db_path, config_path=config_path)
        for row in rows
    }

    doc = SimpleDocTemplate(output_path, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph(f"Test Report — {runner_type}", styles["Title"]))
    story.append(Paragraph(
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}  |  "
        f"Scenarios: {', '.join(scenarios)}",
        styles["Normal"],
    ))
    story.append(Spacer(1, 12))

    for row in rows:
        story.append(Paragraph(
            f"{row['scenario']} — {row['result']}", styles["Heading2"]
        ))
        reports = reports_by_row_id[row["id"]]
        metric_table = [["Metric", "Current", "Baseline"]]
        for r in reports:
            metric_table.append([
                r.metric,
                f"{r.current:.2f}",
                f"{r.mean:.2f} ± {r.stddev:.2f}",
            ])
        if len(metric_table) > 1:
            t = Table(metric_table, colWidths=[180, 100, 140])
            t.setStyle(_TABLE_STYLE)
            story.append(t)
        else:
            story.append(Paragraph("No metrics available for comparison.",
                                    styles["Normal"]))
        story.append(Spacer(1, 16))

    doc.build(story)
    print(f"Report saved to {output_path}")
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a per-run PDF report for one runner_type's own scenarios"
    )
    parser.add_argument("--runner-type", required=True)
    parser.add_argument("--scenario", action="append", required=True, dest="scenarios",
                         help="repeatable — one of this stage's known scenarios")
    parser.add_argument("--db", default=DB_PATH)
    parser.add_argument("--report-path", default=REPORT_PATH)
    parser.add_argument("--config", default=None)
    args = parser.parse_args()
    generate_report(args.runner_type, args.scenarios, db_path=args.db,
                     output_path=args.report_path, config_path=args.config)


if __name__ == "__main__":
    main()
```

Note what's deliberately gone from the old file: `make_pass_fail_chart`,
`make_position_scatter`, `matplotlib`/`pandas` imports (no longer used — the report no
longer aggregates many rows into a chart), and the `tools.goal_zones` import (only
used by the removed scatter plot). The drift banner, `-DRIFT` filename, photo
embedding, and Job Summary output are NOT in this task — they land in Tasks 3-5. This
task's job is just: real per-run data in, a real (if plain) PDF out.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_report_tools.py -v`
Expected: all PASS.

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
Expected: all PASS. `tools/generate_test_report.py`'s CLI signature changed (now
requires `--runner-type`/`--scenario`) — this confirms nothing else in the test suite
calls the old no-argument form.

- [ ] **Step 6: Commit**

```bash
git add tools/generate_test_report.py tests/test_report_tools.py
git commit -m "$(cat <<'EOF'
refactor(reporting): rescope generate_test_report to one run's own scenarios

Piece 4: replaces the unscoped "last 100 runs" query (which made
stage-5-reports-sim/hw produce near-duplicate reports) with load_run_rows(),
which returns the latest row per scenario for one runner_type — this run's
own result, not a rolling window. Historical trend charts (pass/fail bar,
position scatter) are removed entirely; that view belongs to Piece 5's
dashboard.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Drift banner + `-DRIFT` filename suffix

**Files:**
- Modify: `tools/generate_test_report.py` (`generate_report`)
- Test: `tests/test_report_tools.py`

**Interfaces:**
- Consumes: `reports_by_row_id` (from Task 2, already built inside `generate_report`).
- Produces: `generate_report(...)` now returns a path that may have `-DRIFT` inserted
  before the extension when any row's drift check flags anything. No signature change.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_report_tools.py`:

```python
def _seed_baseline_and_outlier(db_path):
    """10 PASS rows with natural variance (mean ~0.95, matching tests/test_baseline.py's
    established pattern — flat identical values would give zero variance, which
    check_run() explicitly skips) then one wild outlier."""
    for rate in (0.94, 0.95, 0.96, 0.95, 0.96, 0.94, 0.95, 0.96, 0.95, 0.94):
        log_run(scenario="mission1", steps=5, final_x=0.0, final_y=0.0, result="PASS",
                step_log=[], db_path=db_path, runner_type="local",
                nav_success_rate=rate)
    return log_run(scenario="mission1", steps=5, final_x=0.0, final_y=0.0,
                    result="PASS", step_log=[], db_path=db_path, runner_type="local",
                    nav_success_rate=0.10)


def test_generate_report_adds_drift_suffix_when_flagged(tmp_path):
    db = str(tmp_path / "t.db")
    init_db(db)
    _seed_baseline_and_outlier(db)
    from tools.generate_test_report import generate_report
    out = str(tmp_path / "report.pdf")
    result_path = generate_report("local", ["mission1"], db_path=db, output_path=out)
    assert result_path == str(tmp_path / "report-DRIFT.pdf")
    assert os.path.exists(result_path)


def test_generate_report_no_suffix_when_clean(tmp_path):
    db = str(tmp_path / "t.db")
    init_db(db)
    for _ in range(10):
        log_run(scenario="mission1", steps=5, final_x=0.0, final_y=0.0, result="PASS",
                step_log=[], db_path=db, runner_type="local", nav_success_rate=0.95)
    log_run(scenario="mission1", steps=5, final_x=0.0, final_y=0.0, result="PASS",
            step_log=[], db_path=db, runner_type="local", nav_success_rate=0.95)
    from tools.generate_test_report import generate_report
    out = str(tmp_path / "report.pdf")
    result_path = generate_report("local", ["mission1"], db_path=db, output_path=out)
    assert result_path == out
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_report_tools.py -k drift_suffix_or_no_suffix -v`

(Use the exact `-k` expression: `python -m pytest tests/test_report_tools.py -k "drift_suffix or no_suffix" -v`)

Expected: `test_generate_report_adds_drift_suffix_when_flagged` FAILs — `result_path`
is still `out` (no `-DRIFT` insertion exists yet). `test_generate_report_no_suffix_when_clean`
PASSes already (nothing to change for the clean case).

- [ ] **Step 3: Implement**

In `tools/generate_test_report.py`, modify `generate_report` (from Task 2):

```python
def generate_report(runner_type: str, scenarios: list, db_path: str = DB_PATH,
                     output_path: str = REPORT_PATH, config_path: str = None) -> str:
    rows = load_run_rows(runner_type, scenarios, db_path=db_path)

    reports_by_row_id = {
        row["id"]: check_run(row["id"], db_path=db_path, config_path=config_path)
        for row in rows
    }
    any_flagged = any(
        r.flagged for reports in reports_by_row_id.values() for r in reports
    )

    if any_flagged:
        root, ext = os.path.splitext(output_path)
        output_path = f"{root}-DRIFT{ext}"

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    doc = SimpleDocTemplate(output_path, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []

    if any_flagged:
        story.append(Paragraph(
            "⚠ DRIFT DETECTED",
            ParagraphStyle("DriftBanner", parent=styles["Title"], textColor=colors.red),
        ))
    else:
        story.append(Paragraph(f"Test Report — {runner_type}", styles["Title"]))

    story.append(Paragraph(
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}  |  "
        f"Scenarios: {', '.join(scenarios)}",
        styles["Normal"],
    ))
    story.append(Spacer(1, 12))

    for row in rows:
        story.append(Paragraph(
            f"{row['scenario']} — {row['result']}", styles["Heading2"]
        ))
        reports = reports_by_row_id[row["id"]]
        flagged = [r for r in reports if r.flagged]
        if flagged:
            for r in flagged:
                story.append(Paragraph(
                    f"⚠ {r.metric} is {r.sigma:.1f}σ above baseline "
                    f"({r.current:.2f} vs {r.mean:.2f} typical)",
                    ParagraphStyle("DriftDetail", parent=styles["Normal"],
                                   textColor=colors.red),
                ))
        metric_table = [["Metric", "Current", "Baseline"]]
        for r in reports:
            metric_table.append([
                r.metric,
                f"{r.current:.2f}",
                f"{r.mean:.2f} ± {r.stddev:.2f}",
            ])
        if len(metric_table) > 1:
            t = Table(metric_table, colWidths=[180, 100, 140])
            t.setStyle(_TABLE_STYLE)
            story.append(t)
        else:
            story.append(Paragraph("No metrics available for comparison.",
                                    styles["Normal"]))
        story.append(Spacer(1, 16))

    doc.build(story)
    print(f"Report saved to {output_path}")
    return output_path
```

The only structural changes from Task 2's version: `any_flagged` computed once up
front, the `-DRIFT` suffix applied to `output_path` *before* `os.makedirs`/`doc =
SimpleDocTemplate(...)` (so the file actually gets written to the suffixed path), the
banner title swapped conditionally, and a red per-metric detail line for each row's
own flagged metrics (in addition to the existing metric table, not replacing it).

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_report_tools.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/generate_test_report.py tests/test_report_tools.py
git commit -m "$(cat <<'EOF'
feat(reporting): drift banner + -DRIFT filename suffix

Piece 4: a flagged metric (per the now-scenario-aware baseline check) gets
a bold red "DRIFT DETECTED" banner and plain-language per-metric detail at
the top of the PDF, plus a -DRIFT filename suffix visible from the artifact
list alone. Clean runs stay quiet. Still informational only — nothing here
touches CI exit codes.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Embed this run's own photo(s)

**Files:**
- Modify: `tools/generate_test_report.py`
- Test: `tests/test_report_tools.py`

**Interfaces:**
- Produces: `find_run_photos(row_timestamp: str, photo_dir: str = PHOTO_DIR, window_seconds: int = PHOTO_WINDOW_SECONDS) -> list`
  — paths of photos taken in the window immediately before `row_timestamp`, oldest
  first.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_report_tools.py`:

```python
def test_find_run_photos_matches_within_window(tmp_path):
    from tools.generate_test_report import find_run_photos
    photo_dir = tmp_path / "photos"
    photo_dir.mkdir()
    # Row timestamp 2026-07-21T10:05:00; a photo 90s earlier is well within a 180s window.
    (photo_dir / "mission1_step2_20260721_100330.png").write_bytes(b"fake-png")
    matches = find_run_photos("2026-07-21T10:05:00", photo_dir=str(photo_dir),
                               window_seconds=180)
    assert matches == [str(photo_dir / "mission1_step2_20260721_100330.png")]


def test_find_run_photos_excludes_outside_window(tmp_path):
    from tools.generate_test_report import find_run_photos
    photo_dir = tmp_path / "photos"
    photo_dir.mkdir()
    # 400s before the row — outside a 180s window.
    (photo_dir / "mission1_step2_20260721_095800.png").write_bytes(b"fake-png")
    matches = find_run_photos("2026-07-21T10:05:00", photo_dir=str(photo_dir),
                               window_seconds=180)
    assert matches == []


def test_find_run_photos_excludes_photos_after_the_row(tmp_path):
    from tools.generate_test_report import find_run_photos
    photo_dir = tmp_path / "photos"
    photo_dir.mkdir()
    # A photo AFTER the row's own timestamp belongs to a later run, not this one.
    (photo_dir / "mission1_step2_20260721_100600.png").write_bytes(b"fake-png")
    matches = find_run_photos("2026-07-21T10:05:00", photo_dir=str(photo_dir),
                               window_seconds=180)
    assert matches == []


def test_generate_report_embeds_matching_photo(tmp_path):
    db = str(tmp_path / "t.db")
    init_db(db)
    run_id = log_run(scenario="mission1", steps=5, final_x=0.0, final_y=0.0,
                      result="PASS", step_log=[], db_path=db, runner_type="local")
    # Read back the row's own timestamp so the fake photo lands inside the window.
    import sqlite3
    conn = sqlite3.connect(db)
    ts = conn.execute("SELECT timestamp FROM runs WHERE id = ?", (run_id,)).fetchone()[0]
    conn.close()
    photo_dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S")
    from datetime import timedelta
    photo_name = f"mission1_step2_{(photo_dt - timedelta(seconds=5)).strftime('%Y%m%d_%H%M%S')}.png"
    photo_dir = tmp_path / "photos"
    photo_dir.mkdir()
    # A real tiny PNG (pillow is already a project dependency — nav_fleet/image_io.py
    # uses it — so this is safer than a hand-rolled byte blob reportlab might reject).
    from PIL import Image as PILImage
    PILImage.new("RGB", (4, 4), color=(0, 128, 0)).save(photo_dir / photo_name)

    from tools.generate_test_report import generate_report
    out = str(tmp_path / "report.pdf")
    result_path = generate_report("local", ["mission1"], db_path=db, output_path=out,
                                   photo_dir=str(photo_dir))
    assert os.path.exists(result_path)
    assert os.path.getsize(result_path) > 1000
```

Add `from datetime import datetime` stays already imported at top of the test file? It
is not — `tests/test_report_tools.py` doesn't import `datetime` yet. Add it to the
test file's imports:

```python
from datetime import datetime, timedelta
```

(place alongside the existing `import os` line at the top of the file; remove the
redundant inline `from datetime import timedelta` inside the test above since it's now
a top-level import).

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_report_tools.py -k find_run_photos -v`
Expected: all three FAIL — `find_run_photos` doesn't exist yet.

Run: `python -m pytest tests/test_report_tools.py::test_generate_report_embeds_matching_photo -v`
Expected: FAIL — `generate_report()` doesn't accept a `photo_dir` keyword yet.

- [ ] **Step 3: Implement**

In `tools/generate_test_report.py`, add near the top (after `REPORT_PATH`):

```python
PHOTO_DIR = os.path.join(_PROJECT_ROOT, "reports", "photos")
PHOTO_WINDOW_SECONDS = 180
```

Add `from datetime import datetime, timedelta` (replacing the existing
`from datetime import datetime` import at the top of the file).

Add the new function (place it above `generate_report`):

```python
def find_run_photos(row_timestamp: str, photo_dir: str = PHOTO_DIR,
                     window_seconds: int = PHOTO_WINDOW_SECONDS) -> list:
    """Photos taken in the window immediately before this row's own timestamp. There's
    no DB column linking a row to its photo(s) — proximity in time is the correlation
    signal instead, since missions run sequentially on one machine and each mission's
    own photo(s) land well inside the window before that mission's telemetry row is
    logged. Returns paths oldest-first."""
    if not os.path.isdir(photo_dir):
        return []
    row_dt = datetime.strptime(row_timestamp, "%Y-%m-%dT%H:%M:%S")
    matches = []
    for name in os.listdir(photo_dir):
        if not name.endswith(".png"):
            continue
        parts = name[:-4].rsplit("_", 2)  # label, YYYYmmdd, HHMMSS
        if len(parts) != 3:
            continue
        _, date_part, time_part = parts
        try:
            photo_dt = datetime.strptime(date_part + time_part, "%Y%m%d%H%M%S")
        except ValueError:
            continue
        delta = (row_dt - photo_dt).total_seconds()
        if 0 <= delta <= window_seconds:
            matches.append((photo_dt, os.path.join(photo_dir, name)))
    matches.sort()
    return [path for _, path in matches]
```

Add `Image as RLImage` to the reportlab import (currently `from reportlab.platypus
import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer`):

```python
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image as RLImage
)
```

Modify `generate_report`'s signature and per-row loop (from Task 3's version) to
accept `photo_dir` and embed matches:

```python
def generate_report(runner_type: str, scenarios: list, db_path: str = DB_PATH,
                     output_path: str = REPORT_PATH, config_path: str = None,
                     photo_dir: str = PHOTO_DIR) -> str:
```

(only the signature line changes here — everything up through the `any_flagged`/banner
setup stays exactly as Task 3 left it). Inside the per-row `for row in rows:` loop,
after the metric-table `if`/`else` block and before `story.append(Spacer(1, 16))`, add:

```python
        for photo_path in find_run_photos(row["timestamp"], photo_dir=photo_dir):
            story.append(Spacer(1, 8))
            story.append(RLImage(photo_path, width=300, height=225))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_report_tools.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/generate_test_report.py tests/test_report_tools.py
git commit -m "$(cat <<'EOF'
feat(reporting): embed this run's own mission photo(s) in the PDF

Piece 4: no DB column links a row to its photo, so correlation is by time
window — a photo taken in the seconds before a row's own timestamp belongs
to that run's mission, since missions run sequentially on one machine.
Turns "did the robot end up where it should" into something visible
without downloading a separate artifact.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: GitHub Job Summary

**Files:**
- Modify: `tools/generate_test_report.py`
- Test: `tests/test_report_tools.py`

**Interfaces:**
- Produces: `build_job_summary(runner_type: str, rows: list, reports_by_row_id: dict, any_flagged: bool) -> str`
  — markdown text. `generate_report()` writes this to `$GITHUB_STEP_SUMMARY` (append
  mode) when that env var is set; no-op locally where it's unset.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_report_tools.py`:

```python
def test_build_job_summary_plain_language_for_flagged_metric(tmp_path):
    db = str(tmp_path / "t.db")
    init_db(db)
    outlier_id = _seed_baseline_and_outlier(db)
    from tools.baseline_monitor import check_run
    from tools.generate_test_report import build_job_summary, load_run_rows
    rows = load_run_rows("local", ["mission1"], db_path=db)
    reports_by_row_id = {row["id"]: check_run(row["id"], db_path=db) for row in rows}
    any_flagged = any(r.flagged for rs in reports_by_row_id.values() for r in rs)
    summary = build_job_summary("local", rows, reports_by_row_id, any_flagged)
    assert "DRIFT DETECTED" in summary
    assert "nav_success_rate" in summary
    assert "σ" in summary  # plain-language sigma detail, not silence


def test_build_job_summary_quiet_when_clean(tmp_path):
    db = str(tmp_path / "t.db")
    init_db(db)
    for _ in range(10):
        log_run(scenario="mission1", steps=5, final_x=0.0, final_y=0.0, result="PASS",
                step_log=[], db_path=db, runner_type="local", nav_success_rate=0.95)
    log_run(scenario="mission1", steps=5, final_x=0.0, final_y=0.0, result="PASS",
            step_log=[], db_path=db, runner_type="local", nav_success_rate=0.95)
    from tools.baseline_monitor import check_run
    from tools.generate_test_report import build_job_summary, load_run_rows
    rows = load_run_rows("local", ["mission1"], db_path=db)
    reports_by_row_id = {row["id"]: check_run(row["id"], db_path=db) for row in rows}
    any_flagged = any(r.flagged for rs in reports_by_row_id.values() for r in rs)
    summary = build_job_summary("local", rows, reports_by_row_id, any_flagged)
    assert "DRIFT DETECTED" not in summary


def test_generate_report_writes_github_step_summary(tmp_path, monkeypatch):
    summary_file = tmp_path / "step_summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_file))
    db = str(tmp_path / "t.db")
    init_db(db)
    log_run(scenario="mission1", steps=5, final_x=0.0, final_y=0.0, result="PASS",
            step_log=[], db_path=db, runner_type="local")
    from tools.generate_test_report import generate_report
    out = str(tmp_path / "report.pdf")
    generate_report("local", ["mission1"], db_path=db, output_path=out)
    assert summary_file.exists()
    assert "mission1" in summary_file.read_text()


def test_generate_report_no_summary_write_when_env_unset(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    db = str(tmp_path / "t.db")
    init_db(db)
    log_run(scenario="mission1", steps=5, final_x=0.0, final_y=0.0, result="PASS",
            step_log=[], db_path=db, runner_type="local")
    from tools.generate_test_report import generate_report
    out = str(tmp_path / "report.pdf")
    # Must not raise even though GITHUB_STEP_SUMMARY is unset (local/dev invocation).
    generate_report("local", ["mission1"], db_path=db, output_path=out)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_report_tools.py -k "job_summary or step_summary" -v`
Expected: `test_build_job_summary_plain_language_for_flagged_metric` and
`test_build_job_summary_quiet_when_clean` FAIL — `build_job_summary` doesn't exist.
`test_generate_report_writes_github_step_summary` FAILs — nothing writes the file yet.
`test_generate_report_no_summary_write_when_env_unset` already PASSes (nothing to
break yet), which is expected and fine.

- [ ] **Step 3: Implement**

Add to `tools/generate_test_report.py`, above `generate_report`:

```python
def build_job_summary(runner_type: str, rows: list, reports_by_row_id: dict,
                       any_flagged: bool) -> str:
    """Markdown for $GITHUB_STEP_SUMMARY — renders directly on the run's summary page,
    so PASS/FAIL and the drift verdict are visible with zero clicks."""
    lines = [f"## {'⚠ DRIFT DETECTED' if any_flagged else 'Report'} — {runner_type}", ""]
    for row in rows:
        lines.append(f"- **{row['scenario']}**: {row['result']}")
        for r in reports_by_row_id.get(row["id"], []):
            if r.flagged:
                lines.append(
                    f"  - ⚠ `{r.metric}` is {r.sigma:.1f}σ above baseline "
                    f"({r.current:.2f} vs {r.mean:.2f} typical)"
                )
    lines.append("")
    return "\n".join(lines)
```

Modify `generate_report`'s final lines — currently ends with:

```python
    doc.build(story)
    print(f"Report saved to {output_path}")
    return output_path
```

change to:

```python
    doc.build(story)
    print(f"Report saved to {output_path}")

    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a") as f:
            f.write(build_job_summary(runner_type, rows, reports_by_row_id, any_flagged))

    return output_path
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_report_tools.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/generate_test_report.py tests/test_report_tools.py
git commit -m "$(cat <<'EOF'
feat(reporting): GitHub Job Summary — PASS/FAIL + drift verdict on the run page

Piece 4: writes to $GITHUB_STEP_SUMMARY (append mode) when the env var is
set, so a run's PASS/FAIL and drift verdict are visible directly on the
Actions run page — no download required. No-op locally where the env var
is unset (matches how the existing "Stage 4 HIL wall time" step already
uses this same mechanism in ci.yml).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Wire `ci.yml` — correct invocations, artifact names, failure bags, retention

**Files:**
- Modify: `.github/workflows/ci.yml` (`stage-4-hil`, `stage-5-reports-sim`,
  `stage-5-reports-hw`)

**Interfaces:** none — CI config only.

- [ ] **Step 1: Edit `stage-4-hil` — add failure bags to the evidence upload**

Current block (`.github/workflows/ci.yml`, "Upload mission evidence artifact" step):

```yaml
      - name: Upload mission evidence artifact
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: hil-mission-evidence-${{ github.run_number }}
          path: |
            /tmp/hil_stage/*.png
            /tmp/hil_stage/sim.log
            /tmp/hil_stage/mission2_day.log
            /tmp/hil_stage/day_no_ball.out
            /tmp/hil_stage/day_yellow.out
            /tmp/hil_stage/day_red.out
            /tmp/hil_stage/nav2_hil_*.log
            reports/photos/*.png
          if-no-files-found: warn
```

becomes (adds one line; `_pull_failure_bags` in `tools/mission2_day.py` already scps
bags into `reports/failure_bags/`, per `nav_fleet/failure_bag.py:42`'s `BAG_DIR` and
`tools/mission2_day.py:299-312` — they exist locally today but were never actually
uploaded):

```yaml
      - name: Upload mission evidence artifact
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: hil-mission-evidence-${{ github.run_number }}
          path: |
            /tmp/hil_stage/*.png
            /tmp/hil_stage/sim.log
            /tmp/hil_stage/mission2_day.log
            /tmp/hil_stage/day_no_ball.out
            /tmp/hil_stage/day_yellow.out
            /tmp/hil_stage/day_red.out
            /tmp/hil_stage/nav2_hil_*.log
            reports/photos/*.png
            reports/failure_bags/**
          if-no-files-found: warn
          retention-days: 30
```

(the `retention-days: 30` line is this task's retention requirement, added here too
since this is the same artifact upload — see Global Constraints.)

- [ ] **Step 2: Edit `stage-5-reports-sim` — correct report invocation, filename, retention**

Current block:

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
          name: test-report-${{ github.run_number }}-sim
          path: reports/latest_report.pdf
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
      REPORT_PATH: reports/sim-report-${{ github.run_number }}.pdf
    steps:
      - uses: actions/checkout@v4

      - name: Generate report (this run's own sim scenarios only, per Piece 4)
        run: |
          source ~/fleet-env/bin/activate
          python -m tools.generate_test_report \
            --runner-type local \
            --scenario bedroom_nav \
            --scenario mission1 \
            --report-path "$REPORT_PATH"

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
          name: test-report-${{ github.run_number }}-sim
          # Glob, not the exact REPORT_PATH: generate_test_report appends a -DRIFT
          # suffix to the actual filename when a metric is flagged, which isn't known
          # until the step above runs — this must match either form.
          path: reports/sim-report-${{ github.run_number }}*.pdf
          retention-days: 30
```

- [ ] **Step 3: Edit `stage-5-reports-hw` — same treatment, HIL scenarios**

Current block:

```yaml
  stage-5-reports-hw:
    name: "Stage 5 — HIL Reports + Dashboard"
    runs-on: [self-hosted, x86, gpu, rtx5080]
    needs: stage-4-hil
    # Fair-weather fix part (a) (2026-07-18, pulled forward from S17 after biting twice in
    # one evening): run on stage-4 FAILURE too — failure telemetry is the most valuable
    # kind — but still skip when stage-4 was SKIPPED (docs-only pushes).
    if: ${{ !cancelled() && needs.stage-4-hil.result != 'skipped' }}
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

becomes:

```yaml
  stage-5-reports-hw:
    name: "Stage 5 — HIL Reports + Dashboard"
    runs-on: [self-hosted, x86, gpu, rtx5080]
    needs: stage-4-hil
    # Fair-weather fix part (a) (2026-07-18, pulled forward from S17 after biting twice in
    # one evening): run on stage-4 FAILURE too — failure telemetry is the most valuable
    # kind — but still skip when stage-4 was SKIPPED (docs-only pushes).
    if: ${{ !cancelled() && needs.stage-4-hil.result != 'skipped' }}
    env:
      REPORT_PATH: reports/hil-report-${{ github.run_number }}.pdf
    steps:
      - uses: actions/checkout@v4

      - name: Generate report (this run's own HIL scenarios only, per Piece 4)
        run: |
          source ~/fleet-env/bin/activate
          python -m tools.generate_test_report \
            --runner-type hil_jetson \
            --scenario mission2_no_ball \
            --scenario mission2_yellow \
            --scenario mission2_red \
            --report-path "$REPORT_PATH"

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
          path: reports/hil-report-${{ github.run_number }}*.pdf
          retention-days: 30
```

- [ ] **Step 4: Verify the YAML is still valid**

Run: `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml')); print('valid')"`
Expected: `valid`

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "$(cat <<'EOF'
chore(ci): wire generate_test_report's new per-run args, name reports, retention

Piece 4: stage-5-reports-sim/hw now pass explicit --runner-type/--scenario
so each generates a report scoped to its own stage's results, not an
unfiltered "last 100" query. Output filenames reflect what they are
(sim-report-<run>.pdf / hil-report-<run>.pdf), upload globs account for the
possible -DRIFT suffix. Rosbag failure bags added to the hil-mission-
evidence upload (existed locally, scp'd back by mission2_day.py, never
actually visible on GitHub). retention-days: 30 uniform across all three
artifact uploads touched by this piece.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: End-to-end verification against the real DB

**Files:** none (verification-only, no commit expected unless it surfaces a real
problem — mirrors the Foundation plan's Task 7).

**Interfaces:** none.

- [ ] **Step 1: Full local test suite**

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

- [ ] **Step 2: Generate a real sim report against the real DB**

Run (with `FLEET_DB` unset, exercising the real default from the Foundation piece):
```bash
unset FLEET_DB
python -m tools.generate_test_report --runner-type local --scenario bedroom_nav --scenario mission1 --report-path /tmp/piece4-sim-check.pdf
```
Expected: prints `Report saved to /tmp/piece4-sim-check.pdf` (or
`/tmp/piece4-sim-check-DRIFT.pdf` if something's genuinely flagged right now — either
is a valid pass). Confirm the file exists and is a real PDF:
`ls -la /tmp/piece4-sim-check*.pdf`.

- [ ] **Step 3: Generate a real HIL report against the real DB**

```bash
python -m tools.generate_test_report --runner-type hil_jetson --scenario mission2_no_ball --scenario mission2_yellow --scenario mission2_red --report-path /tmp/piece4-hil-check.pdf
ls -la /tmp/piece4-hil-check*.pdf
```
Expected: a real PDF exists, distinct in content from the sim one (different
scenarios/metrics) — the concrete proof the two reports are no longer time-shifted
duplicates of the same query.

- [ ] **Step 4: Confirm the Job Summary path works locally**

```bash
GITHUB_STEP_SUMMARY=/tmp/piece4-job-summary.md python -m tools.generate_test_report \
  --runner-type local --scenario bedroom_nav --scenario mission1 \
  --report-path /tmp/piece4-sim-check2.pdf
cat /tmp/piece4-job-summary.md
```
Expected: markdown content with the real scenario names and PASS/FAIL, matching
`build_job_summary`'s format.

- [ ] **Step 5: Visual check — open one of the generated PDFs**

Open `/tmp/piece4-sim-check.pdf` (or the `-DRIFT` variant if that's what was produced)
in a PDF viewer and confirm: this run's own scenario(s) and result are shown, a metric
table is present (not empty unless the scenario genuinely has no comparable metrics —
see the Foundation Task 7 precedent where a sparse `mission2_red` row legitimately had
almost no populated metrics), and if a photo existed in the matching time window, it's
embedded. **This step needs your own eyes** — per this project's GUI-observation
convention, report what you actually saw before this task is considered verified.

- [ ] **Step 6: No commit expected** unless Step 5 surfaces a real problem needing a
      follow-up fix — in that case, stop and report back rather than force-fixing
      forward.
