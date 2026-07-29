# dashboard/ — package notes

Migrated out of the repo root CLAUDE.md by `/doctor` on 2026-07-27 (context-lazy-loading
pass) — loads only when Claude is working with files under this directory.

- `dashboard/app.py` — Session 12: Streamlit telemetry dashboard, 4 tabs (Overview,
  Scenarios, Telemetry, Sensor Health). **Gained a 5th "Drift" tab, Session 17 Piece 5
  (2026-07-21):** a `scenario` sidebar filter (alongside the existing robot_type/
  runner_type/sim_engine/power_mode four), one small-multiple control chart per
  watched metric (`tools.baseline_monitor.check_history()` — baseline mean line,
  shaded severity bands drawn widest-first as base layers, points red when flagged),
  a trending badge (distinct yellow/orange banner, explicitly excludes anything
  already flagged — `is_trending_worse()`), a sortable/searchable drill-down table
  (`st.dataframe`, not fragile Plotly click-event wiring — a deliberate fallback per
  the design spec), and a "Diagnose with AI" button
  (`tools.agentic_loop.diagnose()`, fed `build_trend_summary()`'s big-picture context
  from the currently-filtered view). The button imports `tools.agentic_loop` LOCALLY
  inside its own `if st.button(...):` block specifically so `agentic_loop.py`'s
  module-level `client = anthropic.Anthropic()` is never constructed just from
  loading the dashboard page. **No fix-apply action exists anywhere in the
  dashboard** — applying a proposed fix still means running `agentic_loop` from a
  terminal, where `human_approval()`'s existing gate is untouched. Zero automated
  test coverage for this file, by design (Streamlit script, executes top-to-bottom on
  import including a live DB read — confirmed unsafe to import in pytest); the new
  Drift-tab logic was verified via Streamlit's `AppTest` harness against the real
  populated DB plus a deliberately-flagged synthetic-DB check (a guaranteed outlier,
  confirmed to render as a red point outside the shaded bands — proving the flagged
  path, not just the clean one) and a live GUI pass.
  **AI Diagnosis section rebuilt 2026-07-29** (design:
  docs/superpowers/specs/2026-07-29-ai-diagnosis-items-and-feedback-design.md):
  no longer "read-only" in the strictest sense — the button now calls `diagnose(...,
  source='dashboard')`, which auto-logs to `tools.diagnosis_log`'s tables every click
  (system-driven, no separate save button — see that module's own CLAUDE.md entry).
  The caption was updated to say so plainly instead of claiming "nothing here writes
  any file," which stopped being true. Layout: Metrics Analysis (the model's free
  text, captioned explanatory-only) → Recommendations (`evaluate_diagnosis_items()`,
  ✅/❌/⚠/➖ verdict badge + `st.json(..., expanded=True)` per item, ALWAYS visible —
  still display-only, no verdict controls, no save button, that's a separate deferred
  feature) → Summary (`build_conflict_notes()`'s code-generated notes + a fixed
  closing line, not the model's own words). **First version of this section used
  `st.expander` (collapsed by default) for each item — a straight regression against
  "don't hide anything," caught immediately by Mike on first look ("seems like a lot
  less information than before") and reverted the same day.** Verified live via
  Playwright against a real running instance twice (once per round), not just read
  from the diff — this session hit a stray leftover `streamlit` process serving a
  stale import more than once, only ever caught by an actual browser click, never by
  tests or a syntax check.
