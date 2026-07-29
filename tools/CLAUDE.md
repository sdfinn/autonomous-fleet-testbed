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
  monkeypatches. Gained a local Ollama backend, 2026-07-28 (design:
  docs/superpowers/specs/2026-07-28-local-llm-diagnosis-design.md) — diagnose()
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
  (Playwright-driven click on "Diagnose with AI"), not just mocked tests — see
  Release1Todo.md's resolved START HERE entry for the full verification trail.
  **Separate, still-OPEN quality gap found the same day the tool-call bug was fixed
  (2026-07-29, first real trend-view diagnosis against live drift data):** the local
  model's free-text "analysis" narrative fabricated a config file that doesn't exist
  anywhere in this repo (`robot_description.yaml`, `scan_period` param) and, for a
  real param it DID name correctly (`rotate_to_heading_angular_vel`), recommended
  reversing the sign of a deliberately-tuned, already-validated fix (Session 16 Task
  9e slowed it 1.8→0.5 rad/s specifically to give AMCL more lidar scans per radian;
  the model proposed speeding it back up to 1.2, exactly backwards) — while citing a
  fabricated YAML nesting path (`navigation_bringup:`) that doesn't match the real
  file's `controller_server:` structure. This is the same hallucination CLASS the
  real-nav2_params.yaml prompt injection (Session 17 Piece 5) was built to prevent,
  but that fix only grounds what the model CAN read, not what it reliably USES —
  the free-text narrative ignored the injected real values in favor of generic Nav2
  training-data boilerplate. Compounding the problem: the model's own structured tool
  call (`propose_mission_plan`) didn't match its prose recommendation at all — none
  of the narrative's parameter-change advice, right or wrong, ever reached a
  schema-validated `propose_nav_param_change` call a human could actually review via
  `human_approval()`. **Mitigation (b) built 2026-07-29 — `validate_nav_param_proposal(
  response, nav2_params_text=None)`:** when a response contains a
  `propose_nav_param_change` tool call with a `current_value`, checks it against the
  real injected `nav2_params.yaml` text and returns a list of human-readable warning
  strings (empty if nothing to flag) — closes the same gap as the original
  0.55-vs-0.25 `inflation_radius` incident, but as code instead of relying on a human
  to catch it every time. Deliberately does NOT raise, retry, or hide anything —
  Mike's explicit call (2026-07-29): keep showing the raw model output as feedback
  while iterating on quality, don't suppress it. Works via duck typing
  (`block.type`/`.name`/`.input`) so it covers response objects from EITHER backend —
  this bug class has bitten both Claude (Session 17 Piece 5) and Ollama (2026-07-29)
  historically, so the guardrail isn't Ollama-specific. Wired into both real call
  sites: `run_loop()`'s CLI (prints warnings before the approval prompt) and
  `dashboard/app.py`'s Drift tab (`st.warning()` per flag, plus the free-text block
  now carries an explicit "unverified model narrative" caption — mitigation (a)'s
  *spirit* without literally hiding anything, per Mike's ask). 7 unit tests, TDD,
  including exact regression fixtures for both the historical `inflation_radius`
  incident (via a real currently-tuned param) and the 2026-07-29 `scan_period`
  fabrication, run against the REAL `nav2_params.yaml` text, not a mock. **Scope
  limit, confirmed not just theoretical:** only catches claims made through the
  tool's structured `current_value` field — verified live the same day that the
  actual 2026-07-29 incident response (which fabricated in free text but called
  `propose_mission_plan`, not `propose_nav_param_change`) would NOT have been caught
  by this guardrail; the "unverified narrative" UI caption is what covers that gap,
  not this function. **Still open, not built:** (c) a bigger local model — parked,
  no longer the first lever per Mike's priority (fix the small model's guardrails
  first); a scored corrections-log table (schema design in progress, separate from
  this piece) is the next planned step, not yet built.
- `agentic_validate.py` — 2026-07-28: `python -m tools.agentic_validate` runs a small
  set of synthetic drift scenarios through both agentic_loop.py backends (Claude and
  Ollama) and prints both proposals side by side for manual comparison — the canary
  step for judging local-model diagnosis quality. Dev-only, not wired into CI. First
  real validation run (2026-07-28) showed the local model (qwen2.5:14b-instruct) did
  not reliably invoke a tool for the full diagnose() prompt. **AGENTIC_BACKEND was
  flipped to default 'ollama' the same session anyway** (Mike's explicit, informed
  call) — this predicted exactly the live failure hit via the dashboard's "Diagnose
  with AI" button at session end (`RuntimeError: ... did not propose a tool call`).
  **Fixed 2026-07-29** — see the `agentic_loop.py` entry above and
  Release1Todo.md's resolved START HERE entry.
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
