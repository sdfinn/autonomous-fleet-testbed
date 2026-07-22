# Piece 5 — Interactive Drift Dashboard + AI-Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Drift" tab to `dashboard/app.py` showing every watched metric's value
over time against its own rolling baseline (not just the last run), plus a read-only
"Diagnose with AI" button that feeds that trend context to `agentic_loop.diagnose()`
(whose real `current_value` bug also gets fixed here).

**Architecture:** Three new pure functions in `tools/baseline_monitor.py`
(`check_history`, `is_trending_worse`, `build_trend_summary`) do all the drift-history
math and stay independently unit-testable — `dashboard/app.py`'s new tab is a thin
Streamlit rendering layer on top of them, consistent with how this file has always
worked (and consistent with why it's never had unit tests: Streamlit script-execution
+ live DB reads at import time make it unsafe to import in a test, confirmed during
the Foundation piece). `agentic_loop.py`'s `diagnose()` gets the real
`nav2_params.yaml` text injected into its prompt (direct context injection, matching
this project's standing "no RAG" decision) instead of letting the LLM infer a value.

**Tech Stack:** Python 3, Streamlit, Plotly (`plotly.graph_objects` — new import;
`plotly.express` alone can't build the varying-per-point shaded sigma bands this
needs), pytest, the `anthropic` SDK (already a dependency).

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-21-session17-piece5-drift-dashboard-design.md`
  (approved by Mike, 2026-07-21, amended once to record a parked item) — implements
  it exactly; do not add scope beyond it.
- Depends on Foundation (merged, `main` @ `ca5aa06`) and Piece 4 (merged, `main` @
  `22f3a2c`) — `baseline_monitor.check_run()` is already scenario-aware; this plan's
  Task 1 builds directly on that, does not re-implement slicing.
- Drift stays informational only everywhere — nothing in this plan may fail a build
  or block anything. The dashboard is read-only by design (spec §5): no write/approve
  action moves into it. `agentic_loop.human_approval()`'s terminal-only gate is
  untouched.
- Explicitly parked, NOT in scope for this plan (per the spec's Scope section — do
  not pull these in): CI pipeline self-health tracking, monthly cold build,
  FAIL-row-policy verification, baseline window-size/sigma-band calibration review,
  full interactive approve/apply from the dashboard.
- `dashboard/app.py` has zero existing unit test coverage and stays that way in this
  plan — it's a Streamlit script (executes top-to-bottom on import, does a live DB
  read via `st.cache_data`), unsafe to import in pytest. All new *logic* goes into
  testable functions in `tools/baseline_monitor.py`/`tools/agentic_loop.py`; the
  dashboard changes themselves are manually verified (Task 8).
- TDD for every task that touches `tools/*.py`. Manual verification (documented,
  not skipped) for every task that touches `dashboard/app.py`.

---

### Task 1: `check_history()` — drift verdict across a filtered run history

**Files:**
- Modify: `tools/baseline_monitor.py` (add function, after `check_run`)
- Test: `tests/test_baseline.py`

**Interfaces:**
- Produces: `check_history(runner_type: str = None, power_mode: str = None, scenario: str = None, db_path: str = DB_PATH, n: int = None, config_path: str = None) -> dict[int, list[BaselineReport]]`
  — one entry per matching run (PASS **and** FAIL — a failure's own metrics compared
  against the healthy baseline is exactly the informative case), keyed by run id,
  ordered ascending by insertion (Python dicts preserve insertion order; the query
  itself is `ORDER BY id ASC`, so callers get chronological order for free). `None`
  for any filter argument means "don't filter on that column." Reuses `check_run()`
  for every row — no slicing/severity logic duplicated.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_baseline.py`, after the existing tests:

```python
def test_check_history_returns_one_entry_per_matching_run(db):
    _seed_baseline(db)  # 10 PASS rows, scenario="baseline_test", runner_type=None
    run_id_1 = _insert(db, nav_success_rate=0.95)
    run_id_2 = _insert(db, nav_success_rate=0.10)  # a clear outlier
    history = check_history(db_path=db)
    assert run_id_1 in history
    assert run_id_2 in history
    # The outlier's own report must show it flagged — same verdict check_run() alone
    # would give for that run_id, proving check_history() didn't reimplement the logic.
    outlier_reports = {r.metric: r for r in history[run_id_2]}
    assert outlier_reports["nav_success_rate"].flagged


def test_check_history_filters_by_scenario(db):
    for rate in _COHORT_HI:
        _insert(db, nav_success_rate=rate, scenario="mission2_no_ball")
    for rate in _COHORT_LO:
        _insert(db, nav_success_rate=rate, scenario="mission2_red")
    history = check_history(scenario="mission2_no_ball", db_path=db)
    conn_check_ids = set(history)
    # Every returned run must actually be a mission2_no_ball row — spot check via a
    # direct query rather than trusting the function's own filter silently.
    import sqlite3
    conn = sqlite3.connect(db)
    real_ids = {r[0] for r in conn.execute(
        "SELECT id FROM runs WHERE scenario = 'mission2_no_ball'"
    )}
    conn.close()
    assert conn_check_ids == real_ids


def test_check_history_includes_fail_rows(db):
    """A FAIL run's own metrics, compared against the healthy PASS-only baseline, is
    exactly the informative case for a trend chart — FAIL rows must NOT be excluded
    from the returned history (they're already correctly excluded from the BASELINE
    itself, inside check_run() — a different thing)."""
    _seed_baseline(db)
    fail_id = _insert(db, nav_success_rate=0.0, result="FAIL")
    history = check_history(db_path=db)
    assert fail_id in history


def test_check_history_empty_db_returns_empty_dict(db):
    assert check_history(db_path=db) == {}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_baseline.py -k check_history -v`
Expected: all four FAIL — `check_history` doesn't exist yet (`ImportError` or
`AttributeError` depending on how the test imports it).

First add the import at the top of `tests/test_baseline.py` (currently
`from tools.baseline_monitor import check_latest_run, check_run, load_config`):

```python
from tools.baseline_monitor import check_history, check_latest_run, check_run, load_config
```

- [ ] **Step 3: Implement**

Add to `tools/baseline_monitor.py`, directly after `check_run` (before
`check_latest_run`):

```python
def check_history(
    runner_type: str = None,
    power_mode: str = None,
    scenario: str = None,
    db_path: str = DB_PATH,
    n: int = None,
    config_path: str = None,
) -> dict:
    """Drift verdict for EVERY run matching the given slice filters (None = no filter
    on that column), not just one run_id — the trend view check_run() alone can't
    provide. Includes FAIL rows (a failure's own metrics vs. the healthy baseline is
    informative) — only the baseline window itself stays PASS-only, via check_run()'s
    own existing query, unchanged here. Reuses check_run() per row; no duplicated
    slicing/severity logic.

    Returns {run_id: [BaselineReport, ...]}, ordered ascending by run id.
    """
    conn = sqlite3.connect(db_path)
    where = []
    params = []
    for col, val in (("runner_type", runner_type), ("power_mode", power_mode),
                      ("scenario", scenario)):
        if val is not None:
            where.append(f"{col} = ?")
            params.append(val)
    query = "SELECT id FROM runs"
    if where:
        query += " WHERE " + " AND ".join(where)
    query += " ORDER BY id ASC"
    row_ids = [r[0] for r in conn.execute(query, params).fetchall()]
    conn.close()

    return {
        run_id: check_run(run_id, db_path=db_path, n=n, config_path=config_path)
        for run_id in row_ids
    }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_baseline.py -v`
Expected: all PASS, including every pre-existing test in this file.

- [ ] **Step 5: Commit**

```bash
git add tools/baseline_monitor.py tests/test_baseline.py
git commit -m "$(cat <<'EOF'
feat(drift): check_history() — drift verdict across a filtered run history

Piece 5: the dashboard's trend view needs every matching run's drift
verdict, not just the latest one. Reuses check_run() per row rather than
duplicating its slicing/severity logic — drift math stays in one module.
Includes FAIL rows (informative against the healthy baseline); only the
baseline window itself stays PASS-only, unchanged inside check_run().

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: `is_trending_worse()` — leading indicator, distinct from "flagged"

**Files:**
- Modify: `tools/baseline_monitor.py` (add function)
- Test: `tests/test_baseline.py`

**Interfaces:**
- Produces: `is_trending_worse(values: list, direction: str, window: int = 3) -> bool`
  — pure function, no I/O. `direction` is `"up"` or `"down"`, matching
  `BaselineReport.direction`/`drift_config.yaml`'s convention. Returns `True` only
  when the last `window` values are *strictly* monotonic toward the worse direction.
  Fewer than `window` values returns `False`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_baseline.py`:

```python
def test_is_trending_worse_detects_monotonic_decrease_for_down_direction():
    # nav_success_rate: direction=down (lower is worse) — strictly decreasing = trending.
    assert is_trending_worse([0.95, 0.93, 0.91, 0.89], direction="down", window=3)


def test_is_trending_worse_detects_monotonic_increase_for_up_direction():
    # mean_position_error: direction=up (higher is worse) — strictly increasing = trending.
    assert is_trending_worse([0.10, 0.12, 0.15, 0.19], direction="up", window=3)


def test_is_trending_worse_false_when_flat():
    assert not is_trending_worse([0.95, 0.95, 0.95, 0.95], direction="down", window=3)


def test_is_trending_worse_false_when_improving():
    # Decreasing values with direction=up (higher is worse) means IMPROVING, not trending.
    assert not is_trending_worse([0.19, 0.15, 0.12, 0.10], direction="up", window=3)


def test_is_trending_worse_false_when_fewer_than_window():
    assert not is_trending_worse([0.95, 0.93], direction="down", window=3)


def test_is_trending_worse_only_looks_at_last_window_values():
    # An early non-monotonic blip outside the window must not prevent detection —
    # only the LAST `window` values matter.
    assert is_trending_worse([0.50, 0.99, 0.95, 0.93, 0.91], direction="down", window=3)


def test_is_trending_worse_does_not_know_about_flagged_status():
    """Design note (spec's testing section lists 'a metric already flagged' as an
    edge case): is_trending_worse() takes only raw values — it has no concept of
    'flagged' at all, deliberately, since that's a property of a specific point's
    deviation from ITS OWN baseline (check_run()'s job), not of the sequence's shape.
    A monotonically-worsening sequence is reported as trending regardless of whether
    its last point would separately be classified as flagged elsewhere — the caller
    (dashboard Task 6) is responsible for suppressing the trending badge when the
    metric is ALSO already flagged (`if not already_flagged and is_trending_worse(...)`),
    not this function. This test locks in that the function itself doesn't special-case
    it, so a future change can't silently break that separation of concerns."""
    # A sequence that would also read as a large-sigma outlier if checked against a
    # tight baseline — is_trending_worse still just reports the monotonic shape.
    assert is_trending_worse([0.95, 0.50, 0.10], direction="down", window=3)
```

Update the import line in `tests/test_baseline.py` to also pull in `is_trending_worse`:

```python
from tools.baseline_monitor import check_history, check_latest_run, check_run, is_trending_worse, load_config
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_baseline.py -k is_trending_worse -v`
Expected: all seven FAIL — `is_trending_worse` doesn't exist yet.

- [ ] **Step 3: Implement**

Add to `tools/baseline_monitor.py`, directly after `check_history`:

```python
def is_trending_worse(values: list, direction: str, window: int = 3) -> bool:
    """True if the last `window` values are moving strictly monotonically toward the
    metric's configured WORSE direction ('down' = lower is worse, 'up' = higher is
    worse) — a leading indicator distinct from 'flagged' (which requires crossing the
    info sigma band). Not a regression model, deliberately simple. Fewer than
    `window` values returns False."""
    if len(values) < window:
        return False
    recent = values[-window:]
    if direction == "down":
        return all(recent[i] > recent[i + 1] for i in range(len(recent) - 1))
    return all(recent[i] < recent[i + 1] for i in range(len(recent) - 1))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_baseline.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/baseline_monitor.py tests/test_baseline.py
git commit -m "$(cat <<'EOF'
feat(drift): is_trending_worse() — leading indicator ahead of flagging

Piece 5: catches a metric quietly worsening over its last 3 PASS runs
before it ever crosses the info sigma band and gets flagged. Simple
monotonic-sequence check, direction-aware, deliberately not a regression
model.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: `build_trend_summary()` — plain-text drift summary for the AI loop

**Files:**
- Modify: `tools/baseline_monitor.py` (add function)
- Test: `tests/test_baseline.py`

**Interfaces:**
- Consumes: `check_history()`'s return shape (Task 1), `is_trending_worse()` (Task 2).
- Produces: `build_trend_summary(history: dict) -> str` — plain-text, one line per
  metric found in `history`, reporting flagged-run count and trending status. Used
  by Task 4's `diagnose()` extension to feed big-picture context instead of just the
  latest run.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_baseline.py`:

```python
def test_build_trend_summary_reports_flagged_and_trending(db):
    _seed_baseline(db)
    outlier_id = _insert(db, nav_success_rate=0.10)
    history = check_history(db_path=db)
    summary = build_trend_summary(history)
    assert "nav_success_rate" in summary
    assert "flagged" in summary.lower()


def test_build_trend_summary_reports_stable_metric():
    from tools.baseline_monitor import BaselineReport
    history = {
        1: [BaselineReport(metric="mean_position_error", mean=0.12, stddev=0.01,
                            current=0.12, sigma=0.0, flagged=False, direction="up")],
    }
    summary = build_trend_summary(history)
    assert "mean_position_error" in summary
    assert "stable" in summary.lower()


def test_build_trend_summary_empty_history():
    summary = build_trend_summary({})
    assert "no comparable metrics" in summary.lower()
```

Update the import line in `tests/test_baseline.py` once more:

```python
from tools.baseline_monitor import build_trend_summary, check_history, check_latest_run, check_run, is_trending_worse, load_config
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_baseline.py -k build_trend_summary -v`
Expected: all three FAIL — `build_trend_summary` doesn't exist yet.

- [ ] **Step 3: Implement**

Add to `tools/baseline_monitor.py`, directly after `is_trending_worse`:

```python
def build_trend_summary(history: dict) -> str:
    """Plain-text summary of a check_history() result — which metrics are currently
    flagged (and how often across this filtered view), and which are trending toward
    the worse direction without having flagged yet. For feeding into
    agentic_loop.diagnose() as big-picture context, not just the single latest run."""
    by_metric = {}
    for run_id in sorted(history):
        for r in history[run_id]:
            by_metric.setdefault(r.metric, []).append(r)

    if not by_metric:
        return "  No comparable metrics in this filtered view."

    lines = []
    for metric, reports in by_metric.items():
        flagged_count = sum(1 for r in reports if r.flagged)
        values = [r.current for r in reports]
        direction = reports[-1].direction
        trending = is_trending_worse(values, direction)
        status = []
        if flagged_count:
            status.append(f"{flagged_count}/{len(reports)} runs flagged")
        if trending:
            status.append("trending worse over the last 3 runs, not yet flagged")
        if not status:
            status.append("stable")
        lines.append(f"  {metric}: {', '.join(status)}")
    return "\n".join(lines)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_baseline.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/baseline_monitor.py tests/test_baseline.py
git commit -m "$(cat <<'EOF'
feat(drift): build_trend_summary() — plain-text big-picture summary

Piece 5: turns a check_history() result into the plain-text context
agentic_loop.diagnose() needs to reason about a filtered view's trend,
not just the single latest run. Built on Tasks 1-2, no new logic
duplicated.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Fix `agentic_loop.diagnose()`'s `current_value` bug

**Files:**
- Modify: `tools/agentic_loop.py`
- Test: `tests/test_agentic_loop.py` (new file)

**Interfaces:**
- Produces: `load_nav2_params_text(path=NAV2_PARAMS_PATH) -> str` — reads the real
  file. `diagnose(run_data, db_path=FLEET_DB, trend_context: str = None)` — signature
  gains one new optional keyword arg (backward compatible — `run_loop()`'s existing
  call, `diagnose(run_data)`, is unaffected).

**Note on testability (confirmed empirically before writing this task):**
`tools/agentic_loop.py` constructs `client = anthropic.Anthropic()` at **module
level**. This was flagged as an "unsafe to import in a test" risk during the
Foundation piece's Task 3 review — verified now: `anthropic.Anthropic()` does **not**
raise without an API key (confirmed via `python3 -c "import anthropic;
anthropic.Anthropic()"` with `ANTHROPIC_API_KEY` unset — constructs fine, lazy
validation only happens on an actual API call). So `import tools.agentic_loop` in a
test is safe, **as long as the test never calls the real `client.messages.create`** —
this task's test monkeypatches that method, so no real network call ever happens.

- [ ] **Step 1: Write the failing test**

Create `tests/test_agentic_loop.py`:

```python
# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for tools/agentic_loop.py's diagnose() prompt-building — no real
Anthropic API calls (client.messages.create is monkeypatched in every test)."""
from tools import agentic_loop
from tools.telemetry_logger import init_db, log_run


class _FakeResponse:
    content = []


def test_load_nav2_params_text_reads_the_real_file():
    text = agentic_loop.load_nav2_params_text()
    assert "inflation_radius: 0.25" in text


def test_diagnose_injects_real_nav2_params_into_prompt(monkeypatch, tmp_path):
    """Bug fix: diagnose() must inject the REAL nav2_params.yaml content into the
    prompt sent to Claude, so current_value comes from the actual file, not an LLM
    guess (caught wrong once: claimed 0.55 for inflation_radius, real value 0.25)."""
    db = str(tmp_path / "t.db")
    init_db(db)
    run_id = log_run(scenario="mission1", steps=5, final_x=0.0, final_y=0.0,
                      result="PASS", step_log=[], db_path=db, runner_type="local")

    captured = {}

    def _fake_create(**kwargs):
        captured["messages"] = kwargs["messages"]
        return _FakeResponse()

    monkeypatch.setattr(agentic_loop.client.messages, "create", _fake_create)

    run_data = {"id": run_id, "scenario": "mission1", "result": "PASS",
                "sim_engine": "gazebo"}
    agentic_loop.diagnose(run_data, db_path=db)

    prompt_text = captured["messages"][0]["content"]
    assert "inflation_radius: 0.25" in prompt_text


def test_diagnose_includes_trend_context_when_given(monkeypatch, tmp_path):
    db = str(tmp_path / "t.db")
    init_db(db)
    run_id = log_run(scenario="mission1", steps=5, final_x=0.0, final_y=0.0,
                      result="PASS", step_log=[], db_path=db, runner_type="local")

    captured = {}

    def _fake_create(**kwargs):
        captured["messages"] = kwargs["messages"]
        return _FakeResponse()

    monkeypatch.setattr(agentic_loop.client.messages, "create", _fake_create)

    run_data = {"id": run_id, "scenario": "mission1", "result": "PASS",
                "sim_engine": "gazebo"}
    agentic_loop.diagnose(run_data, db_path=db,
                           trend_context="  nav_success_rate: 3/20 runs flagged")

    prompt_text = captured["messages"][0]["content"]
    assert "nav_success_rate: 3/20 runs flagged" in prompt_text


def test_diagnose_omits_trend_section_when_not_given(monkeypatch, tmp_path):
    db = str(tmp_path / "t.db")
    init_db(db)
    run_id = log_run(scenario="mission1", steps=5, final_x=0.0, final_y=0.0,
                      result="PASS", step_log=[], db_path=db, runner_type="local")

    captured = {}

    def _fake_create(**kwargs):
        captured["messages"] = kwargs["messages"]
        return _FakeResponse()

    monkeypatch.setattr(agentic_loop.client.messages, "create", _fake_create)

    run_data = {"id": run_id, "scenario": "mission1", "result": "PASS",
                "sim_engine": "gazebo"}
    agentic_loop.diagnose(run_data, db_path=db)

    prompt_text = captured["messages"][0]["content"]
    assert "Big-picture trend context" not in prompt_text
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_agentic_loop.py -v`
Expected: `test_load_nav2_params_text_reads_the_real_file` FAILs (`AttributeError`,
function doesn't exist). The three `diagnose`-related tests FAIL too — either the
same `AttributeError` for the missing function, or (if reached) an assertion failure
because the real file's content isn't in the prompt yet.

- [ ] **Step 3: Implement**

In `tools/agentic_loop.py`, add near the top (after the `client =
anthropic.Anthropic()` line, before `TOOLS = [`):

```python
NAV2_PARAMS_PATH = Path(__file__).resolve().parent.parent / 'src' / 'nav_fleet' / 'config' / 'nav2_params.yaml'


def load_nav2_params_text(path=NAV2_PARAMS_PATH):
    """Raw text of the real nav2_params.yaml — injected into diagnose()'s prompt so
    Claude reads actual current values instead of inferring them from memory (the
    bug: it once claimed 0.55 for inflation_radius when the real value is 0.25).
    Direct context injection, no RAG — matches this project's standing decision."""
    return Path(path).read_text()
```

Then replace `diagnose()`'s current body:

```python
def diagnose(run_data, db_path=FLEET_DB):
    """Call Claude with telemetry + drift context; get structured diagnosis and proposed action."""
    locations_str = '\n'.join(f'  {k}: {v}' for k, v in SEMANTIC_MAP.items())

    # Reuse the real drift detector (Session 12) instead of re-deriving pass/fail from
    # hardcoded thresholds — it compares against a rolling baseline of past PASS runs.
    drift_reports = check_run(run_data['id'], db_path=db_path)
    if drift_reports:
        drift_str = '\n'.join(
            f'  {r.metric}: current={r.current:.2f} baseline_mean={r.mean:.2f} '
            f'sigma={r.sigma:.1f} '
            + (f'FLAGGED ({r.severity})' if r.flagged else 'ok')
            for r in drift_reports
        )
    else:
        drift_str = '  Not enough baseline history yet (need 3+ prior PASS runs).'

    prompt = f"""You are an autonomous robotics test engineer.

The latest nav test run (id={run_data['id']}, scenario={run_data['scenario']},
result={run_data['result']}, sim_engine={run_data.get('sim_engine')}):
{json.dumps(run_data, indent=2)}

Drift report against the rolling baseline (config/drift_config.yaml sigma thresholds):
{drift_str}

Available named locations in this environment (use these in mission plans):
{locations_str}

Analyse the results. If any metric is FLAGGED, diagnose the likely cause and use ONE
tool to propose a concrete action. If nothing is flagged, use propose_mission_plan
with semantic location names to create a more challenging multi-waypoint mission
(e.g. "visit the bedroom goal, then the desk, then return to home_base") or use
generate_world_variant to propose a harder obstacle layout."""

    response = client.messages.create(
        model='claude-sonnet-5',
        max_tokens=2048,
        tools=TOOLS,
        messages=[{'role': 'user', 'content': prompt}],
    )
    return response
```

with:

```python
def diagnose(run_data, db_path=FLEET_DB, trend_context=None):
    """Call Claude with telemetry + drift context; get structured diagnosis and proposed action.

    trend_context (Piece 5, optional): a plain-text summary from
    tools.baseline_monitor.build_trend_summary() — the dashboard's "Diagnose with AI"
    button feeds the currently-filtered view's big-picture trend here, not just this
    one run. None (the default) matches the original single-run CLI behavior exactly.
    """
    locations_str = '\n'.join(f'  {k}: {v}' for k, v in SEMANTIC_MAP.items())

    # Reuse the real drift detector (Session 12) instead of re-deriving pass/fail from
    # hardcoded thresholds — it compares against a rolling baseline of past PASS runs.
    drift_reports = check_run(run_data['id'], db_path=db_path)
    if drift_reports:
        drift_str = '\n'.join(
            f'  {r.metric}: current={r.current:.2f} baseline_mean={r.mean:.2f} '
            f'sigma={r.sigma:.1f} '
            + (f'FLAGGED ({r.severity})' if r.flagged else 'ok')
            for r in drift_reports
        )
    else:
        drift_str = '  Not enough baseline history yet (need 3+ prior PASS runs).'

    nav2_params_text = load_nav2_params_text()

    prompt = f"""You are an autonomous robotics test engineer.

The latest nav test run (id={run_data['id']}, scenario={run_data['scenario']},
result={run_data['result']}, sim_engine={run_data.get('sim_engine')}):
{json.dumps(run_data, indent=2)}

Drift report against the rolling baseline (config/drift_config.yaml sigma thresholds):
{drift_str}

The REAL current contents of src/nav_fleet/config/nav2_params.yaml — use these exact
values for `current_value` if proposing a param change. Do not guess or infer a
current value from memory or training data; read it from this text:
{nav2_params_text}
"""

    if trend_context:
        prompt += f"""
Big-picture trend context across the currently-filtered dashboard view (not just this
one run):
{trend_context}
"""

    prompt += f"""
Available named locations in this environment (use these in mission plans):
{locations_str}

Analyse the results. If any metric is FLAGGED, diagnose the likely cause and use ONE
tool to propose a concrete action. If nothing is flagged, use propose_mission_plan
with semantic location names to create a more challenging multi-waypoint mission
(e.g. "visit the bedroom goal, then the desk, then return to home_base") or use
generate_world_variant to propose a harder obstacle layout."""

    response = client.messages.create(
        model='claude-sonnet-5',
        max_tokens=2048,
        tools=TOOLS,
        messages=[{'role': 'user', 'content': prompt}],
    )
    return response
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_agentic_loop.py -v`
Expected: all 4 PASS.

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
Expected: all PASS — confirms `import tools.agentic_loop` (now exercised by pytest
for the first time in this project's history) doesn't have any import-time side
effect that breaks collection of the rest of the suite.

- [ ] **Step 6: Commit**

```bash
git add tools/agentic_loop.py tests/test_agentic_loop.py
git commit -m "$(cat <<'EOF'
fix(agentic): diagnose() reads the real nav2_params.yaml, not an LLM guess

Piece 5: diagnose()'s prompt now injects the real file's text directly
(this project's standing "no RAG, direct context injection" decision) so
Claude reads actual current values instead of inferring them — the bug
that once claimed 0.55 for inflation_radius when the real value is 0.25.
Also adds an optional trend_context param (unused by the existing CLI,
which is unaffected) for the dashboard's "Diagnose with AI" button (Task 7).

First-ever test coverage for this file — verified empirically first that
anthropic.Anthropic() doesn't raise without an API key at construction, so
importing this module in pytest is safe as long as the real
client.messages.create is never called (monkeypatched in every test here).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Dashboard — new "Drift" tab with per-metric control charts

**Files:**
- Modify: `dashboard/app.py`

**Interfaces:**
- Consumes: `check_history()` (Task 1).
- Produces: nothing new consumed by later tasks beyond the `tab5` block itself,
  which Tasks 6-7 append to.

**No automated test** — Streamlit script, unsafe to import in pytest (see Global
Constraints). Manually verified in Task 8 against the real DB.

- [ ] **Step 1: Add the new imports**

At the top of `dashboard/app.py`, current:

```python
from tools.goal_zones import end_zones  # noqa: E402
from tools.telemetry_logger import DB_PATH  # noqa: E402
```

change to:

```python
import plotly.graph_objects as go

from tools.baseline_monitor import check_history, load_config  # noqa: E402
from tools.goal_zones import end_zones  # noqa: E402
from tools.telemetry_logger import DB_PATH  # noqa: E402
```

(`plotly.graph_objects` goes with the other top-level `import`s, not the `# noqa:
E402` block — it doesn't depend on the `sys.path.insert` bootstrap above it.)

- [ ] **Step 2: Add the scenario filter**

Current (sidebar filter block):

```python
robot_type_filter = st.sidebar.selectbox("Robot Type", _filter_options(runs, "robot_type"))
runner_type_filter = st.sidebar.selectbox("Runner", _filter_options(runs, "runner_type"))
sim_engine_filter = st.sidebar.selectbox("Sim Engine", _filter_options(runs, "sim_engine"))
power_mode_filter = st.sidebar.selectbox("Power Mode", _filter_options(runs, "power_mode"))

for column, choice in (("robot_type", robot_type_filter),
                       ("runner_type", runner_type_filter),
                       ("sim_engine", sim_engine_filter),
                       ("power_mode", power_mode_filter)):
    if choice != "All" and column in runs.columns:
        runs = runs[runs[column] == choice]
```

change to:

```python
robot_type_filter = st.sidebar.selectbox("Robot Type", _filter_options(runs, "robot_type"))
runner_type_filter = st.sidebar.selectbox("Runner", _filter_options(runs, "runner_type"))
sim_engine_filter = st.sidebar.selectbox("Sim Engine", _filter_options(runs, "sim_engine"))
power_mode_filter = st.sidebar.selectbox("Power Mode", _filter_options(runs, "power_mode"))
scenario_filter = st.sidebar.selectbox("Scenario", _filter_options(runs, "scenario"))

for column, choice in (("robot_type", robot_type_filter),
                       ("runner_type", runner_type_filter),
                       ("sim_engine", sim_engine_filter),
                       ("power_mode", power_mode_filter),
                       ("scenario", scenario_filter)):
    if choice != "All" and column in runs.columns:
        runs = runs[runs[column] == choice]
```

- [ ] **Step 3: Add the 5th tab**

Current:

```python
tab1, tab2, tab3, tab4 = st.tabs([
    'Overview', 'Scenarios', 'Telemetry', 'Sensor Health'
])
```

change to:

```python
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    'Overview', 'Scenarios', 'Telemetry', 'Sensor Health', 'Drift'
])
```

- [ ] **Step 4: Append the Drift tab's control-chart section**

At the end of the file (after Tab 4's closing content, currently ending at
`st.dataframe(df_lidar, use_container_width=True)`), append:

```python

# ── Tab 5: Drift ─────────────────────────────────────────────────────────────
with tab5:
    st.subheader('Drift Detection — Big Picture')
    st.caption(
        'Every watched metric over time against its own rolling baseline — not just '
        'the last run. Filters above (Runner, Power Mode, Scenario) scope this view.'
    )

    _drift_runner_type = None if runner_type_filter == "All" else runner_type_filter
    _drift_power_mode = None if power_mode_filter == "All" else power_mode_filter
    _drift_scenario = None if scenario_filter == "All" else scenario_filter

    history = check_history(
        runner_type=_drift_runner_type,
        power_mode=_drift_power_mode,
        scenario=_drift_scenario,
        db_path=DB_PATH,
    )

    if not history:
        st.info('No runs match the current filters — widen them to see drift trends.')
    else:
        _cfg = load_config()
        _bands = _cfg['sigma']
        _severity_order = ('critical', 'error', 'warning', 'info')  # widest drawn first
        _severity_colors = {
            'info': 'rgba(255, 235, 59, 0.15)',
            'warning': 'rgba(255, 152, 0, 0.15)',
            'error': 'rgba(244, 67, 54, 0.15)',
            'critical': 'rgba(183, 28, 28, 0.15)',
        }

        # Runs metadata (timestamp) for the x-axis — `runs` here is already filtered
        # by the sidebar, so this join is scoped consistently with `history`.
        _runs_by_id = runs.set_index('id')

        by_metric = {}
        for run_id in sorted(history):
            if run_id not in _runs_by_id.index:
                continue
            for r in history[run_id]:
                by_metric.setdefault(r.metric, []).append((run_id, r))

        for metric, points in by_metric.items():
            xs = [_runs_by_id.loc[run_id, 'timestamp'] for run_id, _ in points]
            means = [r.mean for _, r in points]
            stddevs = [r.stddev for _, r in points]
            currents = [r.current for _, r in points]
            flagged_flags = [r.flagged for _, r in points]

            fig = go.Figure()
            for severity in _severity_order:
                threshold = _bands.get(severity)
                if threshold is None:
                    continue
                upper = [m + threshold * sd for m, sd in zip(means, stddevs)]
                lower = [m - threshold * sd for m, sd in zip(means, stddevs)]
                fig.add_trace(go.Scatter(x=xs, y=upper, mode='lines',
                                          line=dict(width=0), showlegend=False,
                                          hoverinfo='skip'))
                fig.add_trace(go.Scatter(x=xs, y=lower, mode='lines',
                                          line=dict(width=0), fill='tonexty',
                                          fillcolor=_severity_colors[severity],
                                          name=severity, hoverinfo='skip'))

            fig.add_trace(go.Scatter(x=xs, y=means, mode='lines',
                                      line=dict(color='blue', dash='dash'),
                                      name='baseline mean'))

            point_colors = ['#e74c3c' if f else '#2ecc71' for f in flagged_flags]
            fig.add_trace(go.Scatter(
                x=xs, y=currents, mode='markers+lines',
                marker=dict(color=point_colors, size=8),
                line=dict(color='rgba(100,100,100,0.3)'),
                name=metric,
                text=[f'run {run_id}' for run_id, _ in points],
                hovertemplate='%{text}<br>%{y:.3f}<extra></extra>',
            ))
            fig.update_layout(title=metric, showlegend=False, height=250,
                               margin=dict(l=40, r=20, t=40, b=20))
            st.plotly_chart(fig, use_container_width=True)
```

- [ ] **Step 5: Manual verification (Streamlit — no automated test for this task)**

Run: `unset FLEET_DB && streamlit run dashboard/app.py`

Open the printed local URL. Confirm the sidebar now has a **Scenario** dropdown, the
tab bar now shows **Drift** as a 5th tab, and opening it renders a chart per watched
metric with data — a dashed blue baseline-mean line, shaded bands, and green/red
points. Report what you actually saw before considering this task done (per this
project's GUI-observation convention) — don't just confirm the server started without
an error.

- [ ] **Step 6: Commit**

```bash
git add dashboard/app.py
git commit -m "$(cat <<'EOF'
feat(dashboard): Drift tab — per-metric control charts over the run history

Piece 5: 5th tab, scenario filter added alongside the existing four. Each
watched metric gets its own small-multiple chart: baseline mean line,
shaded sigma bands by severity, points colored red when flagged. Built on
check_history() (Task 1) — all the drift math stays in
tools/baseline_monitor.py, this file only renders it.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Dashboard — trending indicator + drill-down table

**Files:**
- Modify: `dashboard/app.py`

**Interfaces:**
- Consumes: `is_trending_worse()` (Task 2), `history`/`by_metric` (built in Task 5's
  `with tab5:` block, extended here).

**No automated test** — same reasoning as Task 5.

- [ ] **Step 1: Add the import**

Current (from Task 5):

```python
from tools.baseline_monitor import check_history, load_config  # noqa: E402
```

change to:

```python
from tools.baseline_monitor import check_history, is_trending_worse, load_config  # noqa: E402
```

- [ ] **Step 2: Add the trending badge, before the per-metric chart loop**

Locate this line (added in Task 5, inside `with tab5:`, right after `by_metric` is
built and right before `for metric, points in by_metric.items():`):

```python
        for metric, points in by_metric.items():
```

Insert immediately before it:

```python
        _trending_metrics = []
        for metric, points in by_metric.items():
            _values = [r.current for _, r in points]
            _direction = points[-1][1].direction
            _already_flagged = points[-1][1].flagged
            if not _already_flagged and is_trending_worse(_values, _direction):
                _trending_metrics.append(metric)
        if _trending_metrics:
            st.warning(
                f'⚠️ Trending toward drift (not yet flagged): '
                f'{", ".join(_trending_metrics)}'
            )

        for metric, points in by_metric.items():
```

- [ ] **Step 3: Add the drill-down table, after the per-metric chart loop**

At the very end of the `with tab5:` block (after the `st.plotly_chart(fig,
use_container_width=True)` line that ends the per-metric loop from Task 5), append:

```python

        st.divider()
        st.subheader('Run Detail (drill-down)')
        detail_rows = []
        for run_id in sorted(history, reverse=True):
            if run_id not in _runs_by_id.index:
                continue
            row = _runs_by_id.loc[run_id]
            flagged_metrics = [r.metric for r in history[run_id] if r.flagged]
            detail_rows.append({
                'run_id': run_id,
                'scenario': row['scenario'],
                'timestamp': row['timestamp'],
                'result': row['result'],
                'flagged_metrics': ', '.join(flagged_metrics) if flagged_metrics else '—',
            })
        st.dataframe(pd.DataFrame(detail_rows), use_container_width=True)
```

(`pd` is already imported at the top of this file — no new import needed for this
step. This table is the spec's drill-down fallback: Streamlit's `st.dataframe`
already supports click-to-sort per column and a built-in search box natively, so
this alone satisfies "searchable/sortable run-detail table" without needing fragile
Plotly click-event wiring — a real click-to-jump interaction is a nice-to-have, not
required by this task.)

- [ ] **Step 4: Manual verification**

Run: `unset FLEET_DB && streamlit run dashboard/app.py`

Open the Drift tab. Confirm a run-detail table appears below the charts, sortable by
clicking column headers, showing which metrics (if any) were flagged per run. If any
metric in the current data is trending-but-not-flagged, confirm the yellow/orange
warning banner appears above the charts (distinct from the red flagged points) — if
nothing is currently trending in the real data, that's fine, just note that you
didn't see the banner (rather than being unable to tell whether it would work).
Report what you actually saw.

- [ ] **Step 5: Commit**

```bash
git add dashboard/app.py
git commit -m "$(cat <<'EOF'
feat(dashboard): Drift tab — trending badge + drill-down run-detail table

Piece 5: a distinct yellow/orange banner (not the flagged points' red)
when a metric's last 3 PASS runs are worsening without having crossed the
info sigma band yet — built on is_trending_worse() (Task 2). Drill-down
via a sortable/searchable st.dataframe rather than Plotly click-event
wiring, per the spec's own documented fallback.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: Dashboard — "Diagnose with AI" button (read-only)

**Files:**
- Modify: `dashboard/app.py`

**Interfaces:**
- Consumes: `build_trend_summary()` (Task 3), `agentic_loop.diagnose()` (Task 4,
  now scenario-aware via `trend_context`).

**No automated test** — same reasoning as Tasks 5-6. The logic this button calls
(`build_trend_summary`, `diagnose`) is already unit-tested in Tasks 3-4; this task
is purely the thin Streamlit wiring around them.

- [ ] **Step 1: Add the button, at the very end of the `with tab5:` block**

After the `st.dataframe(pd.DataFrame(detail_rows), use_container_width=True)` line
added in Task 6, append:

```python

        st.divider()
        st.subheader('AI Diagnosis (read-only)')
        st.caption(
            'Feeds this filtered view\'s trend to Claude for a proposed diagnosis. '
            'Read-only — nothing here writes any file. Applying a fix still means '
            'running `python -m tools.agentic_loop` from the terminal, where the '
            'existing human-approval gate is unchanged.'
        )
        if st.button('Diagnose with AI'):
            from tools.agentic_loop import diagnose  # local import: avoid constructing
            # anthropic.Anthropic() (module-level in agentic_loop.py) unless this
            # button is actually clicked.
            trend_context = build_trend_summary(history)
            latest_run_id = max(history)
            latest_row = _runs_by_id.loc[latest_run_id]
            run_data = latest_row.to_dict()
            run_data['id'] = latest_run_id
            with st.spinner('Asking Claude...'):
                response = diagnose(run_data, db_path=DB_PATH, trend_context=trend_context)
            for block in response.content:
                if block.type == 'text':
                    st.markdown(block.text)
                elif block.type == 'tool_use':
                    st.write(f'**Proposed action:** `{block.name}`')
                    st.json(block.input)
```

- [ ] **Step 2: Add the import**

Current (from Task 5/6):

```python
from tools.baseline_monitor import check_history, is_trending_worse, load_config  # noqa: E402
```

change to:

```python
from tools.baseline_monitor import build_trend_summary, check_history, is_trending_worse, load_config  # noqa: E402
```

- [ ] **Step 3: Manual verification**

Run: `unset FLEET_DB && streamlit run dashboard/app.py`

Open the Drift tab, scroll to the bottom, click **Diagnose with AI**. Confirm a
spinner appears, then either a text analysis or a proposed-action JSON block renders
— and confirm nothing on disk changes as a result (no new/modified files in
`src/nav_fleet/config/` or `src/nav_fleet/worlds/`) — this button must be provably
read-only. This step requires `ANTHROPIC_API_KEY` to be set in your terminal (per
CLAUDE.md's documented gotcha — a normal interactive terminal has it via `.bashrc`;
Claude Code's own non-interactive shell does not, so this specific verification step
needs to be run by you, in your own terminal, not delegated). Report what you
actually saw.

- [ ] **Step 4: Commit**

```bash
git add dashboard/app.py
git commit -m "$(cat <<'EOF'
feat(dashboard): "Diagnose with AI" button — read-only, trend-fed

Piece 5: calls agentic_loop.diagnose() with the currently-filtered view's
trend context (build_trend_summary(), Task 3) instead of just the latest
run. Purely read-only display — no write/approve action moves into the
dashboard; applying a proposed fix still means running agentic_loop from
the terminal, where human_approval()'s existing gate is untouched.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 8: End-to-end verification against the real DB

**Files:** none (verification-only, no commit expected unless it surfaces a real
problem — mirrors the Foundation and Piece 4 plans' final tasks).

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

- [ ] **Step 2: Verify `check_history()`/`is_trending_worse()`/`build_trend_summary()`
      against the real DB**

```bash
unset FLEET_DB
python3 -c "
from tools.baseline_monitor import check_history, build_trend_summary
history = check_history(runner_type='hil_jetson')
print(f'{len(history)} hil_jetson runs found')
print(build_trend_summary(history))
"
```
Expected: a nonzero run count (the real accumulated CI history from the Foundation
piece) and a real per-metric summary, not an empty/error result.

- [ ] **Step 3: Visual check — the full Drift tab, live, against real data**

Run: `unset FLEET_DB && streamlit run dashboard/app.py`

**This step needs your own eyes on the running dashboard** — per this project's
GUI-observation convention. Open the Drift tab and confirm: charts render for real
watched metrics with real historical data, the Scenario filter narrows the charts
correctly when changed, and the drill-down table matches what the charts show.
Report what you actually saw before continuing — not just that the command ran
without an error. Stop the server (`Ctrl+C`) when done with this step.

- [ ] **Step 4: Visual check — a deliberately-flagged synthetic case**

The real DB may or may not currently have any flagged metric visible — Step 3 alone
can't guarantee the red-point/shaded-band rendering and the trending banner actually
get exercised. Build a scratch DB with a guaranteed outlier, point the dashboard at
it, and look again:

```bash
python3 -c "
from tools.telemetry_logger import init_db, log_run
db = '/tmp/piece5_drift_check.db'
init_db(db)
for rate in (0.94, 0.95, 0.96, 0.95, 0.96, 0.94, 0.95, 0.96, 0.95, 0.94):
    log_run(scenario='mission1', steps=5, final_x=0.0, final_y=0.0, result='PASS',
            step_log=[], db_path=db, runner_type='local', nav_success_rate=rate)
log_run(scenario='mission1', steps=5, final_x=0.0, final_y=0.0, result='PASS',
        step_log=[], db_path=db, runner_type='local', nav_success_rate=0.10)
print('scratch DB ready:', db)
"
FLEET_DB=/tmp/piece5_drift_check.db streamlit run dashboard/app.py
```

Open the Drift tab, filter Runner to `local` and Scenario to `mission1`. Confirm the
`nav_success_rate` chart shows the outlier point in red, sitting outside the shaded
bands. Report what you actually saw. Stop the server and delete the scratch file
afterward: `rm /tmp/piece5_drift_check.db`.

- [ ] **Step 5: AI button check (needs your own terminal, not this session's)**

If you have `ANTHROPIC_API_KEY` set in your own interactive terminal (per CLAUDE.md's
documented gotcha — this session's non-interactive shell doesn't have it), run
`unset FLEET_DB && streamlit run dashboard/app.py` yourself, open the Drift tab,
click **Diagnose with AI**, and confirm a sensible read-only response renders and
nothing on disk changes as a result. Report what you saw — or that you're skipping
this specific check for now if you don't have the key handy in this session.

- [ ] **Step 6: No commit expected** unless Steps 3-5 surface a real problem needing a
      follow-up fix — in that case, stop and report back rather than force-fixing
      forward.
