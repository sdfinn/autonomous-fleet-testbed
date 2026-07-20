# Session 17 Code Review (Piece 2)

**Date:** 2026-07-19 · **Reviewer:** Claude (senior developer/architect role, per Mike's
Piece 2 charter) · **Scope:** all Python (`src/nav_fleet/`, `tools/`, `tests/`,
`dashboard/`), launch files, `scripts/*.sh`, `Dockerfile`, requirements, config.
**Rule:** review only — NO code changes made. Every recommendation lives here until
approved.

---

## Executive summary

**The core is healthy.** The mission/navigation package (`missions.py`, `nav_runner.py`,
`mission_runner.py`, `hsv_detect.py`, `goal_retry.py`, the harness and day orchestrator)
is well-factored, deliberately unit-testable (pure modules split from ROS modules — a
real architecture decision, consistently executed), and carries the best decision-history
comments I have seen in a project this size. Class-vs-function judgment is right-sized
where it matters most: `mission2_day.py`'s BallOps/MissionExecutor polymorphism is
exemplary — one day sequence serving sim, CI/HIL, and the future robot day.

**The debt is concentrated in the periphery**, in three clusters:

1. **Drift detection does not do what the project says it does** (CR-01…CR-03). The
   flagship "thresholds are data" principle is violated at its flagship: neither copy
   (there are two, differing!) of `drift_config.yaml` is read by any code, directions are
   ignored (improvements flag as drift), and the sigma bands / post-merge sensitivity /
   hard thresholds exist only in YAML fiction. The agentic loop's prompt then repeats the
   fiction to Claude.
2. **A half-dead AI-scenario subsystem** migrated from isaac_project (CR-04, CR-05):
   `scenario_analyzer.py` queries columns that don't exist (crashes on execution),
   `ai_test_generator.py` inserts into a table nothing creates, and a third of the
   dashboard serves it. Park-or-delete decision needed.
3. **Reporting staleness** (CR-06, CR-07, CR-12): the dashboard can't filter to
   `hil_jetson` runs, shows Mission 2's new telemetry nowhere, has a `%` display bug, and
   both report and dashboard hard-code a goal zone that is wrong for Mission 2 rows.
   (This cluster feeds directly into MikesNotes' Reporting bucket.)

Also flagged: **no LICENSE file, with three contradictory license claims** in the tree —
a hard pre-public blocker (CR-20b).

Recommended fix order: CR-01/02/03 (wire the config — with a failing test first),
CR-06/07 (dashboard, small), CR-05 park decision (Mike's call), CR-08 (telemetry
staleness), then the minors opportunistically.

---

## A. Correctness / behavior findings

**CR-01 · IMPORTANT · Drift detection ignores metric direction.**
`tools/baseline_monitor.py:22-31` declares per-metric directions (`"down"`, `"up"`), but
`check_run()` (line 124) computes `abs(current - mean)/sd` — direction is never consulted.
A run whose `mean_time_to_goal` *improves* by >2σ is FLAGGED as drift, same as a
regression. False-positive drift alarms are how drift detection loses its audience.
*Recommend:* flag only deviations in each metric's bad direction; add a unit test that a
2σ improvement does NOT flag (this test would have caught the bug — none of
`test_baseline.py`'s 9 tests exercises direction).

**CR-02 · IMPORTANT · `drift_config.yaml` is read by nothing.**
`grep` proves no code loads it. `baseline_monitor.py` hardcodes `BASELINE_N=20`,
`SIGMA_THRESHOLD=2.0`, its own metric list; the YAML's sigma severity bands
(info/warn/error/critical), `post_merge_sensitivity`, per-metric `threshold_fail`,
`ci_health` metrics, and the firmware `hard_threshold` are all **unimplemented**.
`HARD_THRESHOLD_METRICS` (line 32) is defined and never used. Worse:
`tools/agentic_loop.py:152` tells Claude the drift report uses "config/drift_config.yaml
sigma thresholds" — feeding the LLM a false claim about its own input. And CLAUDE.md,
BLUEPRINT, and (as of today) `docs/architecture.html` all state the principle as fact.
*Recommend:* wire the YAML in (preserves the principle, makes three documents true), or
delete the YAML and bless the hardcoded scheme (ends the lie cheaply). My strong lean:
wire it — it is ~40 lines and the principle is a differentiator. Failing test first.

**CR-03 · IMPORTANT · Two differing copies of `drift_config.yaml`.**
`config/drift_config.yaml` and `src/nav_fleet/config/drift_config.yaml` both exist and
`diff` says they differ; `setup.py` installs the src one, docs point at the root one,
code reads neither. *Recommend:* one canonical copy (root `config/`, matching CLAUDE.md),
delete the other when CR-02 is fixed.

**CR-04 · IMPORTANT · `tools/scenario_analyzer.py` crashes on execution.**
`tag_high_value_scenarios()` SELECTs `r.battery_percent_start`, `r.fleet_coverage_pct`,
`r.coordination_failures` (lines 64-73) — columns that have never existed in this
project's `runs` schema (they are old isaac_project columns). The query raises
`OperationalError` the moment it runs. This is migrated dead-on-arrival code.
*Recommend:* delete (it is unsalvageable as-is; R2's quality-scoring can start fresh
against the real schema).

**CR-05 · IMPORTANT · The `ai_scenarios` subsystem is half-dead — park or delete.**
`ai_test_generator.py` INSERTs into `ai_scenarios`; `telemetry_logger.py:152`
(`mark_scenario_complete`) UPDATEs it; `dashboard` tabs 4 and part of 5 SELECT from it —
but **no code creates the table** (`init_db` doesn't; nothing does). On any fresh DB the
generator crashes at store time. It also pins an old model name (`claude-sonnet-4-6`)
while `agentic_loop.py` uses `claude-sonnet-5` — two hardcoded, diverging model choices.
The roadmap already parks AI test generation as R2 pillar-1 material and prior notes
flagged "park-or-keep ai_test_generator". *Recommend (Mike's call — question Q1 below):*
either delete `ai_test_generator.py` + `scenario_analyzer.py` +
`mark_scenario_complete` + dashboard tab 4/quality sections now and rebuild properly in
R2 (my lean — R2 will want the judged-mission architecture, not this shape), or park them
in an `attic/` with a README note. Keeping broken code live in `tools/` costs credibility
with every stranger who reads the repo.

**CR-06 · MINOR (but embarrassing) · Dashboard percent bug.**
`dashboard/app.py:115`: `nav_success_rate` mean (a 0–1 value) is rendered with a `%`
suffix and no ×100 — a perfect record displays as "1.0%". *Recommend:* multiply by 100
(and add the same fix wherever pass-rate-like columns render).

**CR-07 · IMPORTANT (Reporting bucket) · Dashboard is blind to the HIL era.**
`dashboard/app.py:46`: the Runner filter offers `qemu/jetson/local` — **no
`hil_jetson`**, the single most interesting runner type (and `qemu` is retired). Nowhere
in any tab: `power_mode`, `seed`, `home_photo_similarity` — Mission 2's telemetry is
invisible. `validate_telemetry.py` knows all of these; the dashboard predates them.
*Recommend:* add `hil_jetson` to the filter, drop `qemu`, add a Mission 2 panel
(similarity trend by scenario, power-mode split). Natural Piece for the Reporting work.

**CR-08 · MINOR · `NavRunner` telemetry attributes go stale across goals.**
`nav_runner.py:38-48` initializes `last_final_x/y`, `last_position_error`,
`last_duration_s` once; `send_goal()` only resets `last_interrupt` (line 76). `_finish()`
skips the pose fields when AMCL hasn't published (line 215) — so a failed goal can leave
the *previous* goal's final pose/error in place, and `_log_mission` /
`log_variant_row` will log them as if they belonged to this run. *Recommend:* reset all
`last_*` at `send_goal()` entry; unit-testable via `goal_retry`-style extraction or a
fake.

**CR-09 · NIT · Magic status number.** `nav_runner.py:168`: `status == 4` — use
`action_msgs.msg.GoalStatus.STATUS_SUCCEEDED`. Self-documenting and robust.

**CR-10 · MINOR · Collision threshold hardcoded.** `metrics_collector.py:83`:
`collision_detected = min_range < 0.12` — a threshold in code, in the project whose motto
is thresholds-are-data. Belongs in the (soon-to-be-wired) drift/config layer or a named
constant with derivation comment (robot radius? lidar min range?). Currently unexplained.

**CR-11 · MINOR · Agentic loop's follow-up instructions are wrong/unusable.**
(a) `agentic_loop.py:233` tells the user to re-run with `sim_launch.py
world:=<variant>` — `sim_only_launch.py:38` hardcodes `bedroom_simple.sdf`; there IS no
`world` argument, so generated world variants cannot actually be launched. The
"harder world" pillar is half-wired. (b) Line 236 says apply param changes to
`config/nav2_params.yaml` — actual path is `src/nav_fleet/config/nav2_params.yaml`.
(c) Known gap (already tracked in S17 inputs): `diagnose()` never feeds real current
param values, so `current_value` is hallucinated. *Recommend:* fix the path string now
(one line); add a `world` launch argument when the S19/R2 world work lands; the
current-value gap stays the tracked S17 Piece 5 item.

**CR-12 · MINOR · Goal-zone rectangle: duplicated and stale.**
Hardcoded twice (`generate_test_report.py:68`, `dashboard/app.py:158-163`) as
(0.0, 3.7)±0.15 — correct only for the BR-01 scenario. Mission 2 PASS rows end at
`home_base` (−1.276, 1.2): visually "outside the goal zone" on every healthy run.
*Recommend:* derive per-scenario end-zones from `SEMANTIC_MAP` + `MISSIONS` (both
importable without ROS — the report already could), single shared helper.

**CR-13 · MINOR · `validate_telemetry.RunsModel` doesn't validate `power_mode`.**
It's in `KNOWN_RUNS_COLS` (so schema-drift passes) but has no model field — values are
never checked (`isin` 15W/25W/MAXN_SUPER would be the obvious rule). Same for the model
missing `power_mode` while docs treat it as a first-class slice key.

---

## B. Architecture — classes vs functions, reuse (Mike's explicit asks)

**CR-14 · VERDICT · Class usage is right-sized — keep the house style.**
Where polymorphism earns its keep, classes exist and are small (`BallOps`/
`MissionExecutor`/`ExecResult`, `NavRunner`, ROS nodes); where pure logic suffices,
functions + NamedTuples/dataclasses (`goal_retry`, `check_traceability`, `hsv_detect`).
Two inconsistencies to iron out: (a) `telemetry_logger.py` mixes a module-level `log_run`
with a `TelemetryLogger` class holding two unrelated methods — one of which belongs to
the half-dead AI subsystem (CR-05). Make telemetry functions-only. (b)
`AITestScenarioGenerator` is a class wrapping a linear script — moot if CR-05 deletes it.

**CR-15 · IMPORTANT (reuse) · Telemetry columns are declared in FOUR places.**
`telemetry_logger.py` CREATE TABLE + `_ensure_run_columns` dict;
`validate_telemetry.py` `RunsModel` + `KNOWN_RUNS_COLS`. Adding one column = 4–5 edits,
and the project's own history proves the failure mode (power_mode, hil_jetson, and seed
each broke or nearly broke CI when one site lagged — the comments in
`validate_telemetry.py:43-51` document the scar tissue). *Recommend:* one column registry
(name → sqlite type → pandera rule) that the logger's migration AND the validator both
consume; `log_run` takes a metrics mapping instead of 20 keyword params. This is the
highest-leverage refactor in the repo (~1–2 h, removes a recurring CI-red class).

**CR-16 · IMPORTANT (reuse) · "Mirrored" constants have already drifted.**
`mission2_day.py:73-75`'s `JENV` claims to mirror `scripts/hil_stage.sh:43` — but the
bash copy exports `MAGICK_THREAD_LIMIT=1 OMP_NUM_THREADS=1` and the Python copy does
not. Harmless today (the mission process doesn't load maps) — but this is precisely how
mirror-by-comment rots, and yesterday's GraphicsMagick segfault is the cautionary tale.
The orphan-sweep pattern similarly exists in 3 copies (ci.yml stage-2, `hil_stage.sh`
teardown, `mission2_day._SWEEP_PATTERNS`). *Recommend:* single source — e.g. a
`scripts/hil_env.sh` both sides source/read, and one sweep-pattern definition; at minimum
sync the JENV copies and leave a pinned cross-reference.

**CR-17 · MINOR (reuse) · Near-duplicate retreat detectors.**
`mission2_day._place_during_return` and `_swap_during_return` share the identical
peak-y/RETREAT_DROP_M polling loop. Extract `_wait_for_retreat(stop_evt) -> bool`,
then each does its 2-line action. Also makes the retreat logic unit-testable (CR-22).

**CR-18 · WATCH · `NavRunner.send_goal` is at the complexity ceiling.**
~135 lines, nested `attempt()`, two retry loops, interrupt + zombie-guard paths. It is
*well-commented* and correct as far as I can trace, but the next feature added here
should trigger the refactor (a small GoalAttempt state object). Not a change request —
a tripwire.

**CR-19 · MINOR (packaging) · tools/ depends on repo-root CWD + sys.path hacks.**
`mission2_harness.py:28`, `agentic_loop.py:16-20`, `tests/conftest.py` all patch
`sys.path`; the "must run as `python -m tools.x` from repo root" trap is documented in
CLAUDE.md because it keeps biting. Fine for R1. Pre-public: make the repo pip-installable
(single `pyproject.toml`, console entry points) and the whole trap class disappears.

---

## C. Dead code & stale content (Mike's ask #4)

**Genuinely dead / broken — recommend delete (pending Q1):**
- `tools/scenario_analyzer.py` — crashes on nonexistent columns (CR-04).
- `tools/ai_test_generator.py` + `TelemetryLogger.mark_scenario_complete` + dashboard
  tab 4 & AI-quality section — table never created (CR-05).
- Dashboard YOLO remnants: `detections_per_frame_avg` (app.py:108), the whole
  `num_frames`/`class_distribution` Camera & Object Detection block (app.py:264-284) —
  guarded by try/except but describing a pipeline this project never built.
- `firmware_test_pass_rate` plumbing (schema, validator, report, drift YAML, scenario
  scoring): no firmware tests exist anywhere; ESP32 work is R3+. Keep the column (cheap,
  already in old rows), delete the aspirational references in the drift config when
  CR-02 lands.
- `tools/sim_vs_real_comparison.png` — a generated artifact committed into `tools/`;
  belongs in `reports/` (gitignored) — delete from the tree.
- `nav_runner.main()` sends a hardcoded (1.0, 1.0) goal as a console entry point —
  either give it argparse x/y or drop the entry point.

**Dormant on purpose — KEEP (documented):** seeded placement (`solve_placement` +
`spawn` verb — S19 item 5 revives it), harness `watch`/`judge-*` CLI verbs (robot-day
manual path), `reset-home` (manual use).

**Stale text (quick sweep, ~15 min total):** `baseline_monitor.py:9` usage says
`python src/baseline_monitor.py` (wrong dir); dashboard hints `python
src/ai_test_generator.py` ×2 (app.py:181, 299); `Dockerfile:2` header says "Stage 2 CI:
QEMU on GHA" (stage renumbered, QEMU retired); `agentic_loop.py:236` params path
(CR-11b).

---

## D. Comments & outsider readability (Mike's ask #3)

**Verdict: outstanding — genuinely the repo's superpower.** The decision-history comments
(`semantic_map.py` clearance math, `missions.py` trigger-tuning history, the harness's
band derivations, `goal_retry.py`'s defect signature) let an outsider reconstruct *why*
every number is what it is. Keep this discipline; it is rarer than good code.

Two systemic notes:
- **CR-20a · MINOR:** heavy internal jargon ("Task 13 §3", "Session 16 Piece 3",
  "Option B") is opaque to outsiders. Fine while private. On the pre-public pass, either
  add a one-page glossary (sessions → what happened) or soften the references. Don't
  strip the history — it's valuable — just make it decodable.
- **CR-20b · BLOCKER (pre-public) · License chaos:** `src/` files carry full Apache-2.0
  headers; several `tools/` files say "Licensed under MIT" one-liners; `setup.py` says
  MIT; `hsv_detect.py`, `telemetry_logger.py`, `dashboard/app.py`, `ball_detector.py`
  and others have no header at all; and there is **no LICENSE file**. Nothing is
  actually licensed until that's resolved. Pick one (question Q2), add LICENSE,
  normalize headers in one sweep.

---

## E. Test coverage (Mike's ask #5)

**Unit tier: strong.** 112 pure test functions across the right modules — and the
pure/ROS split was *designed* to enable exactly this. Coverage highlights:
`check_traceability` (41 tests), `mission2_harness` judges (22), `missions` (18).

**Gaps, in priority order:**
1. **CR-21:** No test pins drift-direction semantics (would have caught CR-01) and none
   pins config loading (CR-02's fix needs its failing test first).
2. **CR-22:** `mission2_day.py` has ZERO unit tests despite containing pure, easily
   testable logic: `_parse_checklist` (regex parsing of mission output — a classic
   silent-breakage spot), the retreat detector (after CR-17's extraction), and
   `ExecResult.tagged`. The day orchestrator is now THE stage-4 gate; its parsing
   deserves pinning.
3. `validate_telemetry.py` and `generate_test_report.py` have no tests at all — a smoke
   test each against a tmp-path DB (log 2 rows → validate → generate) is ~30 lines and
   protects the whole Stage-5 path.
4. `NavRunner` stale-telemetry reset (CR-08) — testable once reset logic exists.
5. **CR-23 (structural, nice-to-have):** the live-ROS ignore list is maintained by hand
   in ci.yml + README + CLAUDE.md (the "twice-bitten" class, now thrice-documented).
   pytest markers (`@pytest.mark.live_ros` + `-m "not live_ros"` in stage-1) would
   replace N `--ignore` flags in 3 files with one marker per test file — the forgetting
   failure-mode disappears.

---

## Questions for Mike — ANSWERED 2026-07-19

- **Q1 (CR-05): DECIDED — delete now, rebuild fresh in R2.** ai_test_generator.py,
  scenario_analyzer.py, `mark_scenario_complete`, dashboard tab 4 + AI-quality section
  all go; R2's pillar-1 work starts clean against the real judged-mission schema.
- **Q2 (CR-20b): DECIDED — Apache-2.0** (Mike accepted the recommendation after the
  MIT-vs-Apache walkthrough: ROS2/Nav2 ecosystem default, majority of src/ already
  carries Apache headers, patent grant suits a framework meant for reuse). Execution:
  add LICENSE (standard Apache-2.0 text), normalize the stray "MIT" one-liners and
  missing headers, fix `setup.py` license field. Pre-public gate item; can land any
  time.
- **Q3 (CR-02): DECIDED — wire `drift_config.yaml` in** (direction-aware, one canonical
  copy at root `config/`, failing tests first). The hardcoded scheme in
  baseline_monitor.py gets replaced by config loading; agentic_loop's prompt claim
  becomes true instead of being edited to match the lie.

## Suggested execution order (when fixes are approved)

1. CR-01 + CR-02 + CR-03 — drift config wired, direction-aware, one canonical file
   (failing tests first; ~half day incl. tests).
2. CR-06 + CR-07 — dashboard percent bug + HIL-era filters/panels (~1-2 h).
3. Q1 decision → CR-04/CR-05 deletions (~30 min).
4. CR-15 — telemetry column registry (~1-2 h, kills a recurring CI-red class).
5. CR-16 JENV/sweep single-sourcing + stale-text sweep + CR-09/10/11b/13 minors (~1 h).
6. CR-22/23 — day-orchestrator unit tests + marker migration (~1-2 h).
7. Q2 → license normalization (pre-public gate, any time).

*Not deep-reviewed this pass:* URDF/SDF/worlds content, `nav2_params.yaml` values
(live-tuned, evidence-backed), `ci.yml` (reviewed extensively in Sessions 16 forensics),
`nav2_isaac_launch.py` (Isaac path parked to R4).
