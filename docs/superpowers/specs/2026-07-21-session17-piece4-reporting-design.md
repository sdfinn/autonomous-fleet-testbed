# Session 17, Piece 4 — Per-CI-Run Reporting (design)

**Date:** 2026-07-21 · **Approved by:** Mike (conversation, 2026-07-21)
**Depends on:** `2026-07-21-session17-telemetry-foundation-design.md` (one consolidated
`FLEET_DB` both stages read/write — Piece 4 assumes this is already in place).
**Goal / success criterion:** push a commit, watch two genuinely distinct reports (sim,
HIL) land on GitHub — immediately visible on the run's Job Summary, with a downloadable
PDF for detail — that correctly and legibly say whether *this run* passed and whether
it drifted, without a human digging through artifacts or SQL.

## Problem

`stage-5-reports-sim` and `stage-5-reports-hw` currently call the identical
`generate_test_report.generate_report()` — same unfiltered `SELECT * FROM runs ORDER
BY id DESC LIMIT 100` query, same output filename `latest_report.pdf` — against the
same DB. They're time-shifted duplicates, not a real sim report and a real HIL report.
Drift detection (`baseline_monitor`) runs as a separate, silent CI step — it's never
folded into the report, and never fails the build (informational only, confirmed —
`baseline_monitor.main()` has no `sys.exit`). Reports only reach GitHub as artifacts
(90-day default retention, no `retention-days` set anywhere), with no on-page summary —
finding one means knowing to open the Actions run and download a zip. Rosbag failure
bags (Piece 3) are pulled back to local disk but never actually uploaded to GitHub.

## Prerequisite — scenario-aware baseline slicing

`baseline_monitor.check_run()` currently slices its rolling baseline window by
`(runner_type, power_mode)` only (`slice_cols`, Session 16 review finding I4) — not by
`scenario`. Mission 1, `mission2_no_ball`, `mission2_yellow`, and `mission2_red` get
mixed into the same 20-run window despite having genuinely different expected
`mean_time_to_goal`/`mean_position_error`/step counts (red stops early after its photo;
yellow's round trip is shorter; mission1 is a different route entirely). A flagged
metric today cannot be distinguished from "the recent scenario mix shifted" — there is
no signal in the current output that would let a human tell the two apart.

Since Piece 4 is about to put a bold red "DRIFT DETECTED" banner on every report, this
has to be fixed **first** — a loud, untrustworthy alarm trains people to stop reading
it, which defeats the whole point.

**Fix:** add `"scenario"` to `check_run()`'s existing `slice_cols` list — same
NULL-safe `IS ?` pattern already used for `runner_type`/`power_mode`. A
`mission2_red` run then only ever compares against other `mission2_red` history.
Small, mechanical, reuses an existing mechanism. Touches `tools/baseline_monitor.py`
(otherwise a Piece 5 file) but blocks Piece 4, so it lands first, as part of this
piece's implementation.

## Design

### 1. Two distinct, correctly-scoped reports

- `stage-5-reports-sim` generates a report filtered to this run's own `stage-2`
  (sim) result(s) only; `stage-5-reports-hw` generates one filtered to this run's own
  `stage-4` (HIL/mission-day) result(s) only. Filtering is by `runner_type` plus the
  run's own scenario(s), not a blanket "last 100" query.
- Output filenames reflect what they are: `sim-report-<run_number>.pdf` /
  `hil-report-<run_number>.pdf` (replacing the shared `latest_report.pdf`), with a
  `-DRIFT` suffix appended when any watched metric is flagged for that run (e.g.
  `hil-report-142-DRIFT.pdf`) — visible from the artifact list alone, no need to open
  anything.

### 2. Report content — narrowed to this run, not a trend view

Piece 5 owns "big picture / trend"; Piece 4's report is deliberately about *this run*
only:
- Scenario(s) tested and PASS/FAIL result.
- This run's own metric values (the same fields `generate_test_report.py` already
  reports: nav success, mean position error, mean time to goal, collision rate,
  Hz means, etc. — whichever are populated for the scenario(s) in this run).
- A drift-comparison table: for each watched metric (per `config/drift_config.yaml`),
  current value vs. baseline mean/σ, using the now-scenario-aware `check_run()`.
- This run's own mission photo(s) embedded inline in the PDF — not just a filename
  reference. Turns "did the robot end up where it should" into something you can see
  without downloading a separate artifact.
- No historical bar charts / position scatter across many runs — that content is
  removed from the per-run report (it moves conceptually to Piece 5's dashboard,
  which is designed separately).

### 3. Drift banner

- Informational only — a flagged metric never fails the CI job (confirmed decision;
  `baseline_monitor` stays exit-0 always).
- Flagged run: bold red "⚠ DRIFT DETECTED" heading at the top of both the PDF and the
  Job Summary, followed by the plain-language detail per flagged metric — e.g.
  "`mean_position_error` is 3.2σ above baseline (0.19 m vs 0.06 m typical)" — never a
  bare sigma number.
- Clean run: plain, quiet header — no alarm fatigue on the common case.

### 4. GitHub landing

- **Job Summary** (`$GITHUB_STEP_SUMMARY`, renders directly on the run's summary page,
  zero clicks): PASS/FAIL, the drift verdict (banner text or "no drift detected"),
  and links naming the evidence artifact(s) for that run (photos, Nav2 logs, failure
  bags) — so "where are this run's logs" is answered on the page itself, not by
  guessing an artifact name.
- **PDF** stays the detailed downloadable artifact, uploaded with the corrected
  per-type filename from §1.
- **Failure bags added to the evidence upload.** Confirmed gap: `mission2_day.py`'s
  `_pull_failure_bags` already scps rosbag failure bags back to the workstation, but
  `ci.yml`'s `hil-mission-evidence-${{ github.run_number }}` artifact `path:` list
  never includes them — they exist locally but were never actually visible on GitHub.
  Add the failure-bag directory to that artifact's path list.

### 5. Retention

- `retention-days: 30` set on both the report-PDF upload steps and the
  `hil-mission-evidence` upload step — one uniform value, replacing today's unset
  (90-day org default) on all of them.

## Testing / verification

- Unit tests for the scenario-slicing fix (`tests/test_baseline.py`) — a synthetic DB
  with mixed scenarios confirms a flagged/unflagged result no longer depends on
  scenario mix, matching the existing `(runner_type, power_mode)` slicing test pattern.
- Unit tests for the new filtered report generation (per-scenario, per-runner_type)
  and the `-DRIFT` filename suffix logic.
- One real CI run observed end-to-end: confirm the Job Summary renders correctly,
  both PDFs land with correct names/content, a deliberately-flagged metric (or a
  synthetic test case) produces the red banner + suffix correctly, and a clean run
  stays quiet.
- Confirm `retention-days: 30` is visible in the Actions UI for a real uploaded
  artifact.

## Out of scope (explicitly, for this piece)

- Any CI-failing behavior from drift (stays informational).
- Piece 5: interactive trend dashboard, AI-loop big-picture involvement, the deeper
  "are the window size/sigma bands themselves still right" review.
- Local disk retention/cleanup (Foundation's out-of-scope item — still separate).
- The existing `dashboard/app.py` streamlit tool is untouched by this piece.
