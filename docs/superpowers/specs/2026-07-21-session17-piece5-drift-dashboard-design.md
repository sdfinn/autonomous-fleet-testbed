# Session 17, Piece 5 — Interactive Drift Dashboard + AI-Loop Big Picture (design)

**Date:** 2026-07-21 · **Approved by:** Mike (conversation, 2026-07-21)
**Depends on:** `2026-07-21-session17-telemetry-foundation-design.md` (one consolidated
`FLEET_DB`) and `2026-07-21-session17-piece4-reporting-design.md` (scenario-aware
`baseline_monitor.check_run()` slicing — this piece's control charts reuse that fix).
**Goal / success criterion:** open the dashboard and answer "is anything drifting, and
has anything been quietly trending that direction?" at a glance, across the whole
project's history — not just the last run (that's Piece 4's job).

## Problem

The current `dashboard/app.py` (4 tabs: Overview, Scenarios, Telemetry, Sensor Health)
has **zero drift visualization** — no baseline comparison, no sigma bands, nothing
showing a metric evolving over time against its own history. `baseline_monitor`'s
drift math exists and is correct (as of Piece 4's scenario-slicing fix) but is only
ever invoked for a single run at a time (`check_run(run_id)` /
`check_latest_run()`), never rendered as a trend. Separately, `agentic_loop.py`'s
`diagnose()` has a known bug — it infers `current_value` for nav2 params via the LLM
instead of reading the real file, and was caught wrong once (claimed 0.55 for
`inflation_radius` when the real value is 0.25) — and is a standalone CLI, never
surfaced anywhere near the data it's reasoning about.

`ai_test_generator`/`scenario_analyzer` — an older Piece 5 checklist item asking
whether they're "earning their keep" — were already deleted in the Session 17 fix wave
(Q1 decision, CR-05). That item is closed; nothing to do here.

## Scope

In scope: the drift dashboard (below) and the AI-loop fix + read-only dashboard
integration. **Explicitly parked, separate follow-on work** (Mike, 2026-07-21): CI
pipeline self-health tracking (a `ci_steps` table logging per-job/per-step durations
from the GitHub API, drift-monitored like any other metric), a monthly scheduled
deliberate cold arm64 build (reproducibility proof), and a FAIL-row-policy
verification pass across baseline_monitor/dashboard/report. These stay on
Release1Todo's Piece 5 list as parked, not folded into this spec.

Also parked here (found during the cross-spec consistency review, 2026-07-21): a
**baseline window-size/sigma-band calibration review** — are the 20-run rolling
window and the 2.0/3.0/4.0/5.0σ bands in `config/drift_config.yaml` still the right
numbers, now that the DB holds real accumulated history? Piece 4's spec named this as
Piece 5's territory; it wasn't otherwise picked up anywhere, so it's recorded here
explicitly rather than silently dropped. Distinct from the scenario-slicing fix
(Piece 4, already handled) and from the older runner_type/power_mode mixing item
above (already handled by existing slicing) — this is specifically about whether the
threshold *numbers* themselves are well-calibrated.

## Design

### 1. New "Drift" tab

- Added to `dashboard/app.py` as a 5th tab, alongside the existing four.
- Reuses the existing sidebar filters (`robot_type`, `runner_type`, `sim_engine`,
  `power_mode`) and adds a new `scenario` filter — didn't exist before, needed now
  that baseline slicing is scenario-aware (Piece 4).

### 2. Per-metric control charts

- One small-multiple chart per watched metric from `config/drift_config.yaml`
  (`nav_success_rate`, `mean_position_error`, `mean_time_to_goal`, `collision_rate`,
  `odom_hz_mean`, `lidar_hz_mean`, `camera_hz_mean`, `home_photo_similarity`):
  value over time (x = timestamp), baseline mean line, shaded σ bands colored by
  severity (info/warning/error/critical per `drift_config.yaml`'s bands), individual
  points colored red when flagged.
- New function in `tools/baseline_monitor.py` — computes the drift verdict across a
  whole filtered run history (not just one `run_id`), reusing the same
  slicing/severity logic as `check_run()` rather than duplicating it in the
  dashboard. Drift math stays centralized in one module.

### 3. Drill-down

- Click a point to see that run's detail: scenario, timestamp, PASS/FAIL, link to its
  photo/report.
- Fallback if Streamlit's plotly click-selection proves fiddly: a searchable/sortable
  run-detail table below each chart, same drill-down capability without depending on
  click-event wiring.

### 4. Trending indicator (leading indicator, distinct from "flagged")

- A separate badge/color from the red "flagged" points: shown when a metric's last
  few PASS runs (same slice) are moving monotonically in the worse direction without
  yet reaching the `info` σ band.
- Simple heuristic — e.g. last 3 points worsening in sequence — not a regression
  model. Catches drift before it's officially flagged without overengineering the
  leading-indicator logic.

### 5. AI-loop: bug fix + read-only dashboard surfacing

- **Bug fix**: `agentic_loop.diagnose()` reads `src/nav_fleet/config/nav2_params.yaml`
  directly for `current_value` instead of having the LLM infer it.
- **Dashboard integration**: a "Diagnose with AI" button in the Drift tab calls
  `diagnose()` fed with the trend/flagged-metric context from the currently-filtered
  view (not just the single latest run) and displays the proposal as **read-only
  text** in the UI.
- **No write/approve action from the dashboard.** Applying a proposed fix still means
  running `agentic_loop` from the terminal, exactly as today —
  `human_approval()`'s existing gate is untouched. This deliberately does not move a
  config-mutating action into a web-UI click.
- Noted as a **stretch goal for later, not this spec**: full interactive
  approve/apply from the dashboard (a real approve button that writes
  `nav2_params.yaml` directly on click).

## Testing / verification

- Unit tests for the new historical drift-check function in `baseline_monitor.py`
  (synthetic multi-run DB, confirm per-run severity matches what `check_run()` would
  say for each individually).
- Unit tests for the trending heuristic (monotonic-worsening detection over a small
  synthetic sequence, including edge cases: fewer than the window size, a metric
  that's flat, a metric already flagged).
- Unit test for the `diagnose()` current_value fix (real YAML value used, not an
  LLM-inferred one).
- Manual verification: open the dashboard against the real consolidated DB (Foundation
  spec), confirm the Drift tab renders real historical trends correctly filtered by
  scenario/runner_type/power_mode, confirm a deliberately-flagged synthetic case shows
  correctly, confirm the "Diagnose with AI" button produces a sensible read-only
  proposal.

## Out of scope (explicitly, for this piece)

- CI pipeline self-health tracking, monthly cold build, FAIL-row-policy verification,
  baseline window-size/sigma-band calibration review (all parked, per Scope section
  above).
- Full interactive approve/apply from the dashboard (stretch goal, later).
- Any change to Piece 4's per-run reports (this piece only touches the workstation
  dashboard).
- Local disk retention/cleanup (Foundation's out-of-scope item — still separate).
