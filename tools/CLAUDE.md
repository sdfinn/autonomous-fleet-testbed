# tools/ — package notes

Python utilities (baseline monitor, telemetry logger, etc.). Migrated out of the repo
root CLAUDE.md by `/doctor` on 2026-07-27 (context-lazy-loading pass) — loads only when
Claude is working with files under this directory.

- `agentic_loop.py` — Session 13: reads the latest run + drift report, has Claude
  propose a nav2 param change / harder SDF world / mission plan, human approves.
  Requires `ANTHROPIC_API_KEY`. **Must run as `python -m tools.agentic_loop`, not
  `python tools/agentic_loop.py`** — the plain-script form fails with
  `ModuleNotFoundError` (see root CLAUDE.md Gotchas). **`diagnose()` bug fixed, Session 17
  Piece 5 (2026-07-21):** it used to let Claude *infer* `current_value` for a nav2 param
  from memory — caught wrong once, claimed 0.55 for `inflation_radius` when the real
  value is 0.25. Now injects `src/nav_fleet/config/nav2_params.yaml`'s real text
  directly into the prompt (`load_nav2_params_text()`) — direct context injection,
  not RAG, matching this project's standing no-RAG decision. Also gained an optional
  `trend_context` param (unused by the CLI's own `run_loop()`, which is unaffected)
  for `dashboard/app.py`'s Drift tab to feed big-picture context from
  `tools.baseline_monitor.build_trend_summary()`. First-ever unit test coverage for
  this file (`tests/test_agentic_loop.py`) — safe to import in pytest because
  `anthropic.Anthropic()` doesn't raise without an API key at construction (verified
  empirically), only on an actual `messages.create()` call, which every test
  monkeypatches. Gained a local Ollama backend, 2026-07-28 — diagnose()
  dispatches to _diagnose_claude or _diagnose_ollama via a backend= param or the
  AGENTIC_BACKEND env var (default 'ollama' as of 2026-07-28); OLLAMA_MODEL env var
  picks the local model (default qwen2.5:14b-instruct). Requires the ollama PyPI
  package (now in requirements-ci.txt) and a running Ollama daemon for the 'ollama'
  backend only — the 'claude' backend's requirements are unchanged. **Ollama
  tool-call bug fixed 2026-07-29:** `_diagnose_ollama()` silently returned no tool
  call at all (not an error — the model just answered in free text) once the real
  `nav2_params.yaml` text pushed the prompt to ~16K chars; confirmed by direct
  reproduction that the same model reliably calls a tool on a short prompt but not
  this one. Fix: `_diagnose_ollama_json_fallback()` retries once with Ollama's
  `format='json'` structured-output contract (schemas described in the prompt text)
  when native tool-calling returns nothing — the JSON-constrained decoder holds up
  where native tool-calling silently drops. Verified against the real dashboard UI
  (Playwright-driven click on "Diagnose with AI"), not just mocked tests.
  **Quality gap found 2026-07-29 (first real trend-view diagnosis against live drift
  data), fully redesigned the same day (three scope corrections in one session).** The
  local model's free-text narrative fabricated a config file that doesn't exist
  anywhere in this repo (`robot_description.yaml`, `scan_period`) and recommended
  reversing a deliberately-tuned, already-validated fix (`rotate_to_heading_angular_vel`,
  Session 16 Task 9e) — while its ONE actual structured tool call
  (`propose_mission_plan`) had nothing to do with any of it. Root design response:
  stop letting recommendations hide in prose at all.

  **`diagnose()`'s prompt now requires every recommendation as its own tool call**
  (Metrics Analysis prose is explanatory-only; "if it isn't submitted as its own tool
  call, it will not be reviewed") — **verified live 2026-07-29 that qwen2.5:14b-instruct
  does NOT reliably comply**: one real trend-view run still wrote 3 nav-param
  recommendations as fake-function-call-formatted prose (`propose_nav_param_change(
  local_costmap:robot_radius:0.237)`) alongside only 1 real tool call. Not a bug in
  the new design — the new Recommendations list makes this exact gap directly visible
  (prose says 4 things, the list shows 1 real item) instead of hiding it, which was
  the actual point. Left as a known, confirmed model-compliance limitation, not
  silently claimed fixed.

  **`evaluate_diagnosis_items(response, nav2_params_text=None)`** (supersedes the
  narrower `validate_nav_param_proposal`, same day) returns one
  `{tool_name, input, auto_verdict, auto_notes}` record per tool-use block:
  `'good'`/`'bad'` for `propose_nav_param_change` (same fact-check logic as before —
  claimed `current_value` vs the real injected file), `'unverified'` for
  `propose_mission_plan`/`generate_world_variant` (nothing to fact-check), and
  `'conflict'` when two-plus `propose_nav_param_change` items disagree on the same
  leaf param name with different `proposed_value`s — the clean, structured version of
  "the AI's own recommendations contradict each other." `'bad'` takes priority over
  `'conflict'` in the verdict label when both apply. Works via duck typing so it
  covers either backend's response shape (this bug class has bitten both Claude,
  Session 17 Piece 5, and Ollama, 2026-07-29). Pure function, nothing persisted here.

  **Second-round fix, same day:** Mike's first look caught the recommendation JSON
  hidden behind a collapsed `st.expander` (reverted to always-visible) and that
  item-vs-item conflict detection alone doesn't catch prose promising several
  actions where only some (or none) become real submitted items.

  **Third-round rebuild, same day — Mike's reaction to the second round: "not really
  what I expected... how do the recommendations map to the final recommendation...
  I expect checkmarks and X's on pretty well every run."** Root cause of ALL of it:
  splitting "the model's prose" and "the model's real tool calls" into two visually
  disconnected sections was the wrong shape. Rebuilt around one idea — **every
  recommendation the model produces, whether formally submitted or only described in
  prose, becomes one item in ONE list**, each independently fact-checked:

  - **`extract_prose_recommendations(analysis_text)`** (new): best-effort parser,
    supersedes `detect_narrative_item_mismatch` entirely (a mismatch COUNT was the
    wrong output — a real, checkable ITEM is). Handles THREE distinct formats
    confirmed live across different runs: kwargs-style (`tool_name(key=value,...)`),
    colon-style positional (`tool_name(a:b:c)`), and a flat JSON object
    (`{"tool": "...", ...}`) — the model doesn't consistently pick one. Best-effort
    title extraction skips markdown code-fence lines and stray punctuation (both
    caught live producing junk titles like `` ```python `` and `)` before the fix)
    — falls back to `None` (rendered as the bare tool name) rather than show
    garbage. Never silently drops a found call — an unparseable body still produces
    an item with `{'raw_text': ...}` so its existence stays visible.
  - **`_evaluate_one_item` now checks param EXISTENCE regardless of whether a
    `current_value` was claimed** — previously a missing `current_value` short-
    circuited straight to `'good'` without checking anything, and most real prose
    recommendations never state a current value at all, so ✅/❌ almost never fired
    in practice. This single change is most of what makes "checkmarks on pretty well
    every run" actually true now.
  - **`evaluate_diagnosis_items(response, nav2_params_text=None)`** now merges
    submitted tool-use blocks AND extracted prose items into one list, each tagged
    `'source'`: `'submitted'` or `'extracted'`, run through the SAME fact-check and
    the SAME cross-item conflict detection regardless of source (so a submitted item
    and a prose-only mention of the same param now correctly conflict with each
    other too, not just two submitted items).
  - **`summarize_diagnosis(items)`** (new, supersedes `build_conflict_notes`): a real
    tally — "N found, S submitted, E text-only" + a ✅/❌/⚠/➖ count line + conflict
    notes + the list of text-only titles — instead of one terse audit sentence.
  - Dashboard: each recommendation is its own bordered `st.container` with a real
    colored banner (`st.success`/`st.error`/`st.warning`/`st.info` — NOT usable as
    `with`-context managers themselves, confirmed via `inspect.signature` before
    trusting it, caught what would've been an immediate crash before it ever reached
    the live test) holding a **GOOD/BAD/CONFLICT/UNVERIFIED** label + title, a
    `**Why:**` line pulled straight from the item's `rationale` field (no more raw
    JSON as the only explanation), a source tag distinguishing submitted from
    text-only, and technical JSON detail in a small nested expander (collapsing raw
    JSON specifically is fine; the readable why/what above it is never hidden). The
    "Metrics Analysis" heading was renamed `"Model's Written Analysis (raw text)"` —
    the model writes its own "Metrics Analysis"/"Recommendations" headings inside
    the same prose, which looked like an accidental duplicate otherwise; shown once,
    not repeated, since the Recommendations list now extracts anything actionable
    from it.
  - `run_loop()` (CLI): same unified list, printed with title/why/verdict/tag per
    item; the human-approval/apply loop now only iterates `source='submitted'`
    items — extracted items are a best-effort text parse, not schema-validated, and
    aren't safe to apply as if they'd gone through the real tool-calling path.

  **Auto-logs every call (`tools.diagnosis_log`, see its own entry below)** — a
  `source='cli'`/`'dashboard'` param on `diagnose()` (per-DIAGNOSIS) is unrelated to
  each item's own `'source'` field (per-ITEM, submitted/extracted) — same name,
  different axis, worth not confusing. `ai_diagnosis_items` gained `source`/`title`
  columns (additive migration, same pattern as `telemetry_logger.py`'s
  `_ensure_run_columns` — this table already had real rows before the addition).
  Still explicitly NOT a human-feedback/scoring layer — deferred, not built.

  **Round 3.1 (same day, after Mike's next real click):** two more real bugs, both
  from format variety, not logic errors. (1) A 4th format: the model wrapped args in
  a NESTED `"parameters": {...}` sub-object — the original JSON regex explicitly
  excluded nested braces (`[^{}]*`) and silently matched **zero** of it. Replaced
  with a real balanced-brace scan (`_find_balanced_close_brace`, mirrors the
  paren-scanner) that tries every `{` as a candidate, `json.loads()`s the full
  matched span regardless of nesting depth, and flattens a `parameters`/`input`/
  `args` wrapper key into the top level before field-alias normalization — subsumes
  the old flat-object case, doesn't need two code paths. (2) Titles sometimes came
  out as the model's own generic `### Recommendations` section heading (not
  item-specific) — added `_GENERIC_SECTION_HEADINGS` denylist so `_extract_nearby_
  title` skips those too, same as code fences and stray punctuation.

  **A 5TH format was then found in the SAME live-verification pass** — plain
  colon-separated lines with no parens or braces at all
  (`propose_nav_param_change: parameter: "robot_radius" new_value: 0.245`). **Not
  yet built.** Deliberately stopped adding parsers reactively here — this is the
  3rd new format discovered in one session of live testing, and every fix so far has
  uncovered another one. Flagged to Mike as a real decision point rather than
  silently attempting a 5th parser: keep extending format-by-format as they're
  found (uncapped effort, always partial), accept the current best-effort coverage
  and lean on the Summary's count + the always-visible raw text as the safety net
  when extraction comes up short, or pursue something structurally different (e.g.
  a second call asking the model to re-emit its own recommendations as strict
  JSON). Not resolved as of this entry.

  5 more tests in this sub-round (72 total in `tests/test_agentic_loop.py` as of this
  entry), several built directly from Mike's own pasted real output as fixtures (the
  exact incidents that motivated each fix).
  Verified live via a running Streamlit instance + Playwright click FOUR times this
  round — caught the `st.success`-as-context-manager bug before it ever reached
  Mike, then three more real live-discovered bugs (formats 3 and 4, the generic-
  heading title bug) each fixed and re-verified live in turn. **Also: a manually-run
  `streamlit run dashboard/app.py` (no `--server.headless` flag — the tell for a
  human-started session, distinct from this session's own always-headless
  instances) was found bound to port 8501 mid-round, almost certainly Mike's own
  session used to produce the pasted output being debugged — left untouched
  throughout; verification moved to the auto-selected 8502 instead of assuming it
  was safe to kill.**

  **Round 4 (same day) — a genuine simplification, not another format-chasing
  patch.** After finding a 5th and 6th prose format in round 3.1, Mike stepped back
  from format-by-format extraction entirely and asked, via a careful step-by-step
  Q&A (not a spec), for the dashboard's whole "structured recommendations" concept
  to be retired: no tool names, no JSON, no good/bad/unverified/conflict badges, no
  submitted-vs-extracted distinction. The badge/verdict machinery from rounds 2-3
  (`evaluate_diagnosis_items`, `_evaluate_one_item`, `summarize_diagnosis`,
  `_detect_cross_item_conflicts`) is **NOT deleted** — it's untouched and still
  powers the CLI (`run_loop()`), which keeps its full propose/approve/apply
  workflow exactly as before. The dashboard gets an entirely separate, much
  simpler path:

  - **`diagnose()` gained `offer_tools=True`** (default — CLI unaffected).
    `dashboard/app.py` calls it with `offer_tools=False`: `_diagnose_claude`/
    `_diagnose_ollama` skip passing `tools=` to the API at all — the model is never
    given the *option* to make a real structured call, so there is no possibility
    of a `tool_use` block in the response. (`_diagnose_ollama`'s JSON-fallback
    retry, which only exists to rescue a failed tool-calling attempt, is skipped
    entirely here too — nothing to retry from when no tool call was ever
    possible.)
  - **`describe_potential_changes(analysis_text)`** (new): reuses
    `extract_prose_recommendations()`'s proven detection/parsing (same regex/
    balanced-brace scanning), but translates the output into plain sentences —
    `"A parameter change was mentioned: {param} → {value}. {rationale}"` — no tool
    name, no JSON, no verdict. This is the dashboard's ONLY path now; it does not
    call `evaluate_diagnosis_items` at all.
  - Dashboard layout: "Model's Written Analysis" (raw model text — **explicitly
    left untouched**, Mike's own words: "we will live with that") → one "Summary"
    section with `describe_potential_changes()`'s plain-language lines. The old
    badge/card "Recommendations" list and the old tally-based "Summary" are both
    gone, replaced by this single section. One necessary one-word fix inside the
    otherwise-untouched raw-analysis caption: it referenced "the Recommendations
    list below," which no longer exists — changed to "the Summary section below"
    to stay accurate, nothing else in that block touched.

  **Honest loose end, not yet resolved:** the prompt text still says "submit [every
  recommendation] as its own tool call" even on the `offer_tools=False` path, where
  that's now structurally impossible — the model has no tool-calling option at all
  on that call. Confirmed live: the model still writes `{"tool": ...}`-shaped JSON
  in its prose, seemingly still trying to follow that now-nonsensical instruction.
  Doesn't break anything (`describe_potential_changes` still parses it fine either
  way), but the prompt and the API call are now inconsistent with each other for
  the dashboard's case. Not fixed — flagged for Mike, not decided unilaterally.

  11 new tests this round (83 total in `tests/test_agentic_loop.py`), TDD
  throughout, plus 2 pre-existing `test_agentic_validate.py` fixtures updated for
  the new `offer_tools` kwarg. Verified live via Playwright — confirmed zero tool
  names, zero JSON, zero verdict badges anywhere on the rendered page.

  **Round 4.1 (same day) — the new plain-language Summary was live-quality-checked
  and found genuinely weak on Mike's next real click:** two of four lines came back
  as bare, content-free `"A parameter change was mentioned."` with nothing else,
  even though the model HAD written real information. Root cause, traced precisely:
  `_normalize_extracted_fields` started from an EMPTY dict and kept ONLY fields that
  matched a known alias — if the model used a field name not in the alias list (e.g.
  `"target"` instead of `"parameter"`), that value was silently discarded before
  `describe_potential_changes` ever saw it, even when a SIBLING field (like
  `proposed_value`) did match and made the dict non-empty (so the existing
  `raw_text` empty-dict fallback never triggered either — a gap between two
  fallbacks, not covered by either). Fixed at the source: `_normalize_extracted_
  fields` now starts from a COPY of everything the model wrote (`dict(raw_pairs)`)
  and adds canonical names on top, instead of starting empty and only keeping
  recognized ones — nothing the model writes is discarded anymore, matching the
  "never silently drop information" principle already established elsewhere in
  this file (`extract_prose_recommendations`'s own docstring). `_describe_one_change`
  also gained a genuine "show partial info" path (proposed_value alone, or any
  otherwise-unrecognized field) instead of requiring the full ideal shape before
  showing anything. 3 new tests (86 total), including one reproducing the exact
  silent-discard mechanism directly. Verified live again — no more bare/empty
  lines in that run's Summary.

  **Round 4.2 (same day) — that fix introduced a NEW bug, caught before push by
  reviewing the next real output rather than assuming "tests pass" meant "done":**
  preserving raw_pairs (4.1's fix) meant a raw key that successfully aliased (e.g.
  `"value"` → `proposed_value`) was ALSO left behind under its original name — so
  display showed the same value twice: `"local_costmap.width → 5. (parameter=
  local_costmap.width, value=5)"`. `_normalize_extracted_fields` now tracks which
  raw keys were actually consumed by a successful alias match and removes them
  afterward — with one care needed: `rationale` aliases to itself (`'rationale':
  ['rationale', 'reason', 'explanation']`), so naively removing "consumed" aliases
  deleted the value that had just been assigned to it; fixed by only marking an
  alias consumed when it differs from the canonical field name it maps to. 2 more
  tests (88 total), one reproducing the exact duplicate-value output verbatim.
  Verified live (no crash across two more clicks, though neither happened to hit a
  recognized format that round — separate, already-known variability, not this
  bug) plus the exact-field-name unit test.

  **Built 2026-07-29 (same day as flagged above):** the second "deep dive" dashboard
  button — `dashboard/app.py`'s "Experimental AI — May take a long time", using
  `diagnose()`'s existing `model_name=` override, no plumbing changes needed. Led to
  a full live comparison across 8 local Ollama models (both buttons, same real run)
  — full table, methodology, and findings in
  `docs/local-llm-diagnosis-model-comparison-2026-07-29.md`. Headline finding: every
  model produced a different, mostly-unparseable prose format — 5 of 8 runs left the
  Summary section flatly contradicting the raw text above it. **Final model pick,
  both buttons wired accordingly:** `PRIMARY_MODEL` (default "Diagnose with AI") =
  Phi-4 14B — fast, no fabrications found, best reasoning transparency in its speed
  class. `EXPERIMENTAL_MODEL` ("Experimental AI") = Llama 3.3 70B — best grounding of
  the whole comparison, ~4min latency acceptable for a button labeled as a slow
  deep-dive.

  **JSON-envelope redesign, built same day, directly off the comparison's own
  evidence.** The `offer_tools=False` path's prompt now asks for exactly one
  grammar-constrained JSON object instead of free-text prose with embedded
  recommendations: `{"analysis": "...", "recommendations": [{"tool": ..., "title":
  ..., "param_path": ..., "proposed_value": ..., "rationale": ..., ...}]}`. Ollama's
  side uses `format='json'` (the same grammar-constrained decoding mechanism that
  already fixed the original tool-call bug, see above) via a new `format=` param on
  `_call_ollama_chat`; Claude's side (no equivalent enforcement in a plain
  `messages.create()` call) relies on prompt-instruction-following only, parsed the
  same way. Both funnel through **`_parse_json_envelope_response(content,
  used_model)`** (new): `json.loads()`, degrading gracefully — never raising — to an
  empty analysis/empty recommendations on malformed JSON or an unexpected shape,
  since an AI response format problem must never crash the dashboard page.
  `_DiagnosisResponse` gained a `recommendations` field (default `[]`, only
  populated on this path) to carry the parsed list alongside the usual `content`
  text blocks.

  **`describe_potential_changes()`'s signature changed** from `(analysis_text)` to
  `(recommendations)` — it now consumes the already-structured list directly instead
  of best-effort-parsing it out of prose. It still runs each recommendation through
  `_normalize_extracted_fields` (the existing alias/dedup safety net — a model can
  still write `"parameter"` instead of `"param_path"` even under a JSON contract, as
  tonight's comparison showed more than once) — only the unreliable FORMAT-GUESSING
  step is gone, not the field-name safety net. `_describe_one_change` is unchanged,
  reused as-is.

  **`extract_prose_recommendations()` and everything under it (the "7 formats" code
  — balanced-paren/brace scanning, kwargs/colon parsing, title-guessing) is
  deliberately NOT deleted.** `evaluate_diagnosis_items()` (the CLI's own
  `offer_tools=True` path, `run_loop()`) still calls it to catch recommendations the
  model describes in prose but never formally submits as a tool call — a real,
  separately-motivated capability from Round 3 (see above) that has nothing to do
  with the dashboard's JSON-envelope path. `evaluate_diagnosis_items()` also gained a
  third item source, `'structured'`, reading `response.recommendations` when
  present, so `diagnose()`'s auto-log stays accurate for `offer_tools=False` calls
  too — without this, the log would show 0 items for every dashboard call even when
  the model proposed something, since the JSON path's `analysis` text no longer has
  recommendations embedded in it for prose-extraction to find.

  16 new/changed tests (104 total in `tests/test_agentic_loop.py`), TDD throughout —
  RED confirmed (16 failures, all expected) before implementing, GREEN after (104
  passed), full project suite re-run clean (399 passed). Verified live via a running
  Streamlit instance + Playwright click against `phi4` (the fast button, ~12s): raw
  analysis text came back clean prose with no embedded JSON (a free side-benefit —
  the model no longer has anywhere to embed its own "Recommendations" heading inside
  the analysis text, since recommendations are a separate JSON field now), and all 4
  recommendations rendered correctly in the Summary — the first fully clean parse
  on the very first live click of this redesign, vs. 5-of-8 misses under the old
  prose-parsing approach.
  **Follow-up same day:** Mike flagged that the raw `analysis` text had gone from
  itemized (old free-text prose often had its own markdown headers/bullets) to one
  flowing paragraph — a side effect of the JSON envelope's `"analysis": "<plain-
  language explanation...>"` field description not asking for any structure, not a
  deliberate choice. Fixed by changing that field's description to ask for a
  markdown bullet list (`"- "` per flagged metric/issue, `\n`-joined inside the JSON
  string) — prompt-text-only change, no parsing logic touched, since `analysis` was
  always displayed via `st.markdown()` as-is. Note: plain `\n` alone would NOT have
  worked — CommonMark collapses single newlines in `st.markdown()`, but consecutive
  `- ` list lines render correctly without needing blank lines between them, which is
  why bullets (not just newline-separated sentences) were the actual fix.
- `vlm_canary.py` — 2026-07-30: the CUDA/on-device-VLM red-ball canary. Fully
  decoupled, log-only classification of Mission 2's existing red-reaction photo by a
  small local vision model (`moondream:1.8b` via Ollama, pinned tag) — no pass/fail,
  zero writes to `runs`/`steps` or `ai_diagnoses`/`ai_diagnosis_items`. Own isolated
  `vlm_canary_log` table (`init_db`/`log_vlm_canary_result`/`find_vlm_canary_results`,
  same shape convention as `diagnosis_log.py` below). `classify_photo()`'s prompt is
  pinned to the literal string `'Describe this image.'` — a more elaborate prompt was
  live-tested and produced a broken 2-token response from this exact model; don't
  "improve" it without re-testing against a real photo first. Spawned as a detached
  subprocess (`python -m tools.vlm_canary <photo> <run_context>`) by `mission2_day.py`
  — that file imports nothing from here, so a broken import here can't break it.
  `generate_test_report.py`'s `build_job_summary()` surfaces a result via
  `find_vlm_canary_results()`, reusing `find_run_photos()`'s already-resolved paths as
  the join key rather than a second time-window match. **Code complete, all 3 tasks
  reviewed clean (Approved, no Critical/Important findings) — NOT yet live-verified
  end-to-end** (implementation plan's Task 5): a HIL day rerun needed to prove this
  first got derailed by two real, unrelated network regressions (see `CLAUDE.md`'s
  dated Gotchas) and then a still-open CPU/timing regression.
- `diagnosis_log.py` — 2026-07-29: auto-log for every `agentic_loop.diagnose()` call,
  same `fleet_runs.db`. `init_db()`/`log_diagnosis(**kwargs) -> diagnosis_id` mirror
  `telemetry_logger.py`'s `runs`/`steps` two-table shape: one `ai_diagnoses` row per
  call (backend, model_name, source, prompt_text, analysis_text, conflict_notes) plus
  one `ai_diagnosis_items` row per recommendation (tool_name, item_input JSON,
  auto_verdict, auto_notes, **source, title** — the latter two added same-day,
  third-round rebuild, via `DIAGNOSIS_ITEM_COLUMNS`/`_ensure_diagnosis_item_columns`,
  additive migration since the table already had real rows). Deliberately has NO
  human-verdict columns — this is the system-driven half only; a human-feedback/
  scoring layer is a separate, deferred design (see the 2026-07-29 spec's scope-
  correction history) that would arrive as an additive migration later, not
  retrofitted here speculatively.
- `agentic_validate.py` — 2026-07-28: `python -m tools.agentic_validate` runs a small
  set of synthetic drift scenarios through both agentic_loop.py backends (Claude and
  Ollama) and prints both proposals side by side for manual comparison — the canary
  step for judging local-model diagnosis quality. Dev-only, not wired into CI. First
  real validation run (2026-07-28) showed the local model (qwen2.5:14b-instruct) did
  not reliably invoke a tool for the full diagnose() prompt. **AGENTIC_BACKEND was
  flipped to default 'ollama' the same session anyway** (Mike's explicit, informed
  call) — this predicted exactly the live failure hit via the dashboard's "Diagnose
  with AI" button at session end (`RuntimeError: ... did not propose a tool call`).
  **Fixed 2026-07-29** — see the `agentic_loop.py` entry above.
- `baseline_monitor.py` — Session 12+: `check_run(run_id)` compares one run against a
  rolling PASS-only baseline (config-driven, `config/drift_config.yaml`), sliced by
  `(runner_type, power_mode, scenario)` — the `scenario` dimension added Session 17
  Piece 4 (2026-07-21): without it, a `mission2_red` run (stops after one step) was
  drift-comparing against `mission2_no_ball` history (a full round trip), letting the
  recent scenario mix masquerade as real drift. **New in Session 17 Piece 5
  (2026-07-21):** `check_history(runner_type=, power_mode=, scenario=)` — the same
  drift verdict across a WHOLE filtered run history (not just one `run_id`), reusing
  `check_run()` per row, used by `dashboard/app.py`'s Drift tab for trend charts.
  `is_trending_worse(values, direction, window=3)` — a pure, direction-aware leading
  indicator (strict monotonic worsening over the last 3 points) distinct from
  "flagged"; deliberately has no concept of flagged status, that's the caller's job
  to combine. `build_trend_summary(history)` — plain-text per-metric summary (flagged
  count + trending status) fed to `agentic_loop.diagnose()`'s new `trend_context` arg.
- `fleet_status.py` — 2026-07-28: `python -m tools.fleet_status [--stage
  sim|hil|real]` prints a plain-text pass/fail + drift summary per scenario, reusing
  `generate_test_report.load_run_rows()`/`baseline_monitor.check_run()` (no new query
  logic). Default freshness window is ~30 days (`DEFAULT_STATUS_MAX_AGE_MINUTES`) —
  deliberately wider than `generate_test_report`'s own 30-minute default, since this
  tool answers "what's the fleet's last known state" not "this CI run's own result";
  `--max-age-minutes` overrides it (CI passes `30` to get the tighter behavior back).
  Wired into three places: standalone CLI, the Claude Code SessionStart hook
  (`.claude/settings.json`, calling `.claude/hooks/session_start_status.sh` as of
  2026-07-29 — see root CLAUDE.md's Gotchas for why plain `echo` there never actually
  reached the user), and a `stage-5-reports-*` CI console-log step (deliberately not
  `$GITHUB_STEP_SUMMARY` — see the design spec for why).
- `generate_test_report.py` — Session 12: originally a blanket "last 100 runs" PDF.
  **Rewritten Session 17 Piece 4 (2026-07-21):** `generate_report(runner_type,
  scenarios, ...)` now scopes to one CI stage's own results only — the latest row
  per known scenario for that `runner_type` (`stage-2-gazebo` → `local` +
  `['bedroom_nav', 'mission1']`; `stage-4-hil` → `hil_jetson` +
  `['mission2_no_ball', 'mission2_yellow', 'mission2_red']`) — replacing the old
  unfiltered query that made `stage-5-reports-sim`/`-hw` produce near-duplicate
  reports. Historical trend charts (`make_pass_fail_chart`/`make_position_scatter`,
  `matplotlib`/`pandas` deps) removed entirely — that view is `dashboard/app.py`'s
  Drift tab now. Gained a bold red "⚠ DRIFT DETECTED" banner + a `-DRIFT` filename
  suffix when any watched metric flags (informational only — never fails the CI
  job), a GitHub Job Summary write (`$GITHUB_STEP_SUMMARY`, append mode, no-op
  locally), and inline photo embedding via `find_run_photos()` — time-window
  correlation (a photo taken in the seconds before a row's own timestamp), since
  there's no DB column linking a row to its photo. CLI now requires `--runner-type`
  and repeatable `--scenario` flags (breaking change from the old no-arg form) OR
  the declared `--stage` path below.
- `pipeline_matrix.py` — Session 17 Piece 6 (2026-07-21): `load_stage(stage)` reads
  `config/pipeline_matrix.yaml`, the single declared source for which
  `(runner_type, scenarios)` belong to which report stage — consumed by
  `generate_test_report.py --stage {sim,hil,real}` and `mission2_day.py`'s
  day-summary loop. **`real` stage added 2026-07-28** (`runner_type=real_robot`,
  `scenarios=[bedroom_nav]`) for `RealRobotStartup.md`'s validation gate.
  **Decided (2026-07-28, Mike):** BR-01 nav-only is the gate, deliberately — not a
  real run of `mission_runner`'s full `mission1`. Settled, no plan to change it.
- **`tests/test_navigation.py`'s `runner_type` bug, fixed 2026-07-28:** its
  `telemetry_run` fixture hardcoded `runner_type='local'` regardless of
  `sim_engine` — a real-robot run (`SIM_ENGINE=real`) would have logged
  `runner_type='local'`, silently mixing real-hardware rows into the sim drift
  baseline. Same bug class `baseline_monitor.py`'s `scenario` dimension above was
  already added to fix once (mission2 variants drift-comparing against the wrong
  history). Fixed to read `os.environ.get('RUNNER_TYPE', 'local')`, matching the
  pattern `mission_runner.py`/`mission2_harness.py` already use — this file was
  the one inconsistent holdout. `RealRobotStartup.md` sets `RUNNER_TYPE=real_robot`
  when invoking pytest against the real robot.
- `log_setup.py` — S17 Piece 3 (2026-07-20): shared logging setup for `tools/` and
  (pending) `nav_fleet/` modules. `FLEET_LOG_LEVEL` env var (default INFO) is the
  single debug switch, same env-var-driven pattern as `FLEET_DB`/`POWER_MODE_ID`.
  `get_logger(name)` for per-module loggers under `fleet.*`; `configure(log_file=...)`
  attaches a bracketed-tag console handler at the configured level PLUS an optional
  file handler that always captures DEBUG+ regardless (post-mortem forensics stay
  generous even on a quiet console). `build_env_manifest(**fields)` /`git_sha()` log a
  run's environment context (git sha, power mode, runner type, ...) alongside its
  events. `mission2_day.py` is fully migrated (its log lands at
  `STATE_DIR/mission2_day.log`, uploaded in Stage 4's evidence artifact); `NavRunner`/
  `MissionRunner` are NOT being switched to this (they already use ROS's own
  `self.get_logger()`, which already persists to `~/.ros/log`) — instead, both nodes'
  `__init__` now call `self.get_logger().set_level(resolve_level())` (2026-07-21;
  rcutils `LoggingSeverity` values are numerically identical to Python's `logging`
  levels, confirmed against `/opt/ros/jazzy/.../logging_severity.py` — no translation
  table needed), and both `main()`s log an env manifest (git sha, and `POWER_MODE` for
  the mission runner) via `self.get_logger().info(build_env_manifest(...))` before
  doing anything else. Covered by `tests/test_nav_runner.py` and `tests/test_mission_run.py`
  (constructing the node is enough to exercise this — no live Gazebo/Nav2 needed for
  these two tests specifically, even though the rest of those files require it). See
  root CLAUDE.md's `propagate=False` gotcha if you add a new logger name and its
  output vanishes under pytest.
- `pull_ros_logs.py` — S17 Piece 3 (2026-07-21): `python -m tools.pull_ros_logs` — the
  one documented command to retrieve a robot's ROS2 logs. `~/.ros/log/` has NO
  automatic retention (confirmed: 2,862 session dirs / 2.2 GB on the workstation
  alone, oldest 2026-06-28); this resolves rcl's own `latest` symlink (`readlink -f`,
  local or over `ssh` using `JETSON_USER`/`JETSON_IP` — same env vars as
  `scripts/hil_stage.sh`) and `scp -r`/`cp -r`s the session dir into
  `reports/ros_logs/`. `--host ''` forces local (no ssh).

## reports/ and the telemetry database

- `reports/` — generated PDF reports and mission photos (`reports/photos/`, untracked).
  The telemetry DB does **not** live here — see the `Telemetry database` entry below.
  (`reports/history/`, the old empty/unused JSON-per-run idea dropped at the 2026-07-03
  Session 12 review, was deleted along with this fix — Session 17 Foundation piece,
  2026-07-21.) **`reports/photos/` is now a persistent absolute path, not
  checkout-relative — Session 17 Piece 4 final-review fix (2026-07-21):** the exact
  same bug class Foundation fixed for `FLEET_DB`, found independently in THREE places
  (`nav_fleet/mission_runner.py`, `tools/mission2_day.py`, `tools/generate_test_report.py`
  each had their own relative `reports/photos` default). Since `actions/checkout@v4`
  wipes each CI job's workspace clean, no run's photos ever reached
  `stage-5-reports-*`'s checkout to be embedded — all three now import `PHOTO_DIR`
  from `tools.telemetry_logger` (sibling directory of `DB_PATH`, the same persistent
  `~/fleet-ci-data/` location). `reports/failure_bags/` (S17 Piece 3) is now included
  in the `hil-mission-evidence` CI artifact upload — found during the same final
  review: `mission2_day.py`'s `_pull_failure_bags` scp'd bags back to the workstation,
  but `ci.yml` never actually uploaded them, so they existed locally but were never
  visible on GitHub. **This absolute-path fix broke `mission2_day.py`'s photo
  pull-back the very next CI run** — see root CLAUDE.md's "Making a path absolute
  breaks every OTHER place..." Gotcha for the regression and its 2026-07-22 fix.
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
