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
  **AI Diagnosis section rebuilt across FOUR rounds, 2026-07-29** (design:
  docs/superpowers/specs/2026-07-29-ai-diagnosis-items-and-feedback-design.md — full
  scope-correction history there). No longer "read-only" in the strictest sense — the
  button calls `diagnose(..., source='dashboard')`, which auto-logs to
  `tools.diagnosis_log`'s tables every click (system-driven, no separate save button
  — see that module's own CLAUDE.md entry); caption updated to say so plainly instead
  of claiming "nothing here writes any file."

  **Current shape (round 4), what's actually on the page today:**
  1. `"Model's Written Analysis (raw text)"` — the model's free text, shown once,
     unedited. Deliberately left alone by explicit instruction ("Leave the Model's
     Written Analysis alone. We will live with that.") — the one intentional touch
     inside it is a single word-level fix, since its caption referenced "the
     Recommendations list below," a section that no longer exists after round 4;
     changed to "the Summary section below," nothing else in that block changed.
  2. `"Summary"` — `tools.agentic_loop.describe_potential_changes()`'s plain-language
     lines only. No tool names, no JSON, no good/bad/unverified/conflict badges, no
     submitted-vs-extracted distinction — Mike's explicit round-4 ask, after
     confirming via direct back-and-forth that this reads as "internal machinery,"
     not something a user needs to see. The button call passes `offer_tools=False`
     (see `tools/CLAUDE.md`'s `agentic_loop.py` entry) — the model is never given
     tools to call on this specific request at all.

  **Rounds 1-3 (superseded, kept here only as history — do not treat as current
  behavior):** round 1 shipped a two-section layout (raw text, then a separate
  structured proposal). Round 2 un-collapsed an `st.expander` that had hidden each
  item by default. Round 3 rebuilt around a unified badge/card list
  (`evaluate_diagnosis_items()`, GOOD/BAD/CONFLICT/UNVERIFIED banners, "Technical
  details" JSON expanders) after Mike asked for checkmarks and traceability — round 3
  ALSO caught a real bug live (`st.success`/`error`/`warning`/`info` are not usable
  as `with`-context managers; found via `inspect.signature` before it ever reached a
  click). **All of round 3's dashboard-facing badge/card UI was then retired in
  round 4** — not because it was broken, but because Mike concluded, after walking
  through exactly what the tool-calling/verdict machinery was and wasn't doing, that
  it was presenting invented structure around an unreliable local model's free text
  as if it were more trustworthy than it actually is. **The underlying
  `evaluate_diagnosis_items()`/`summarize_diagnosis()` machinery from round 3 is
  NOT deleted** — it's untouched and still powers `tools/agentic_loop.py`'s CLI
  (`run_loop()`), which keeps working exactly as it always has; round 4 only
  changed what the DASHBOARD calls and renders.

  Verified live via Playwright against a real running instance on EVERY round
  (5 separate live passes across four rounds) — this session hit a stray leftover
  `streamlit` process serving a stale import more than once (including once that
  turned out to be Mike's own manually-started session, left untouched once
  identified by the missing `--server.headless` flag), and would have shipped the
  `st.success`-as-context-manager bug straight to Mike if the round-3 live click
  hadn't happened before reporting back. Never trust "the tests pass" for this file
  — it has zero automated coverage by design (see below) and every real bug in this
  section so far was caught by an actual browser click, not by reading the diff.
