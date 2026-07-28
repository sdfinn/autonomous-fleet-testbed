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
  the design spec), and a **read-only** "Diagnose with AI" button
  (`tools.agentic_loop.diagnose()`, fed `build_trend_summary()`'s big-picture context
  from the currently-filtered view). The button imports `tools.agentic_loop` LOCALLY
  inside its own `if st.button(...):` block specifically so `agentic_loop.py`'s
  module-level `client = anthropic.Anthropic()` is never constructed just from
  loading the dashboard page. No write/approve action exists anywhere in the
  dashboard — applying a proposed fix still means running `agentic_loop` from a
  terminal, where `human_approval()`'s existing gate is untouched. Zero automated
  test coverage for this file, by design (Streamlit script, executes top-to-bottom on
  import including a live DB read — confirmed unsafe to import in pytest); the new
  Drift-tab logic was verified via Streamlit's `AppTest` harness against the real
  populated DB plus a deliberately-flagged synthetic-DB check (a guaranteed outlier,
  confirmed to render as a red point outside the shaded bands — proving the flagged
  path, not just the clean one) and a live GUI pass.
