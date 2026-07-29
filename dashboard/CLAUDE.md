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
  **AI Diagnosis section rebuilt across THREE rounds, 2026-07-29** (design:
  docs/superpowers/specs/2026-07-29-ai-diagnosis-items-and-feedback-design.md — full
  scope-correction history there). No longer "read-only" in the strictest sense — the
  button calls `diagnose(..., source='dashboard')`, which auto-logs to
  `tools.diagnosis_log`'s tables every click (system-driven, no separate save button
  — see that module's own CLAUDE.md entry); caption updated to say so plainly instead
  of claiming "nothing here writes any file."

  **Round 1** shipped a two-section layout (raw model text, then a separate
  structured proposal). **Round 2** un-collapsed an `st.expander` that had hidden
  each item by default (a straight regression against "don't hide anything," caught
  immediately on Mike's first look). **Round 3 (current)** rebuilt the whole section
  after Mike's sharper feedback — "how do the recommendations map to the final
  recommendation... I expect checkmarks and X's on pretty well every run" — around
  one unified list (`evaluate_diagnosis_items()`, now merging real submitted tool
  calls AND best-effort-extracted prose recommendations, see `tools/CLAUDE.md`'s
  `agentic_loop.py` entry for the full mechanism):

  - `"Model's Written Analysis (raw text)"` — the model's free text, shown once,
    captioned explanatory-only (renamed from a bare "Metrics Analysis" heading,
    which visually duplicated the model's OWN internal heading of the same name).
  - Recommendations — one bordered `st.container` per item, a real colored banner
    (`st.success`/`error`/`warning`/`info` called AS the banner content, NOT as a
    `with`-context manager — that mistake was caught by checking
    `inspect.signature(st.success)` before trusting it, not by a crash) showing
    GOOD/BAD/CONFLICT/UNVERIFIED + a title, a `**Why:**` line from the item's real
    `rationale` field (not raw JSON as the only explanation), a source tag
    (submitted vs. text-only), and a small nested "Technical details" expander for
    the raw JSON — collapsing JSON specifically is fine, the readable content above
    it never is.
  - Summary — `summarize_diagnosis()`'s real tally (found/submitted/text-only counts,
    a ✅/❌/⚠/➖ count line, conflict notes, text-only titles) instead of one terse
    sentence, plus the fixed closing line.

  Verified live via Playwright against a real running instance on EVERY round
  (4 separate live passes across the three rounds) — this session hit a stray
  leftover `streamlit` process serving a stale import more than once, and would have
  shipped the `st.success`-as-context-manager bug straight to Mike if the first
  round-3 live click hadn't been done before reporting back. Never trust "the tests
  pass" for this file — it has zero automated coverage by design (see below) and
  every real bug in this section so far was caught by an actual browser click, not
  by reading the diff.
