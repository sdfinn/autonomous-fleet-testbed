# autonomous-fleet-testbed — Claude Code Context

## Project
Open-source CI/CD-native fleet simulation testing framework for autonomous robots.
**Release1Todo.md is THE go-to doc** (Mike, 2026-07-18): session plans AND the roadmap —
its **Session 20 section (end of file) is the LIVING working plan for releases R2–R5**,
including the four Standing Disciplines (10x check; coaching contract; LLM-leverage
ramp; demo-first — a release without its shipped demo is not done). Execute sessions
from it; code from .superpowers/sdd/ specs.
**Releases relabeled 2026-07-17: numbers now = execution order.** The agentic &
alignment layer is **R2** — docs/notes older than 2026-07-17 saying "R4" mean today's
R2. Ladder: R1 Foundation → R2 Agentic & Alignment → R3 Fleet & Input Expansion → R4
Autonomy & Perception → R5 Self-Testing Fleet; drone CUT (revivable with reason).
BLUEPRINT.md holds strategy background + the decisions log (change history), synced
copy of the roadmap; Release1Todo.md leads.
`LearningLog.md` (repo root) = Mike's teach-back/curriculum record — append each
session's 3–5 new concepts (coaching contract, Standing Discipline #2); at session
start, check it for pending teach-backs.
robotics_cicd_10x_blueprint.md is reference-only source dialogue, not for coding —
re-read at every release kickoff (standing).

## Development workflow — tier 1 first

**Primary dev loop (x86 bare metal — use this to flush bugs before touching CI):**
```bash
colcon build --symlink-install          # ~1s — build the ROS2 package
source install/setup.bash
python -m pytest tests/ -v \
  --ignore=tests/test_ros2_contracts.py \
  --ignore=tests/test_navigation.py \
  --ignore=tests/test_mission_run.py \
  --ignore=tests/test_mission2.py    # seconds — run Python unit tests
ros2 launch nav_fleet sim_launch.py    # Session 09+ — Gazebo + Nav2 locally
# nav_runner, metrics_collector, drift check all run here
```

x86 is not the robot's target OS but finds 90% of bugs at ~1s build vs 23 min QEMU.
Commit to CI only when the x86 pipeline is clean. See BLUEPRINT.md "Tiered development loop."

## Environment
- Ubuntu 24.04 bare metal (dual boot with Windows 11)
- ROS2 Jazzy + Gazebo Harmonic + CycloneDDS
- Python virtualenv: ~/fleet-env (activate before running Python tools)
- Colcon workspace: ~/autonomous-fleet-testbed/ (build from here)
- `ros-jazzy-robot-localization` (ekf_node) required on BOTH machines since Session 16 —
  workstation + Jetson (`sudo apt install ros-jazzy-robot-localization` on a rebuilt Jetson)
- `ros-jazzy-vision-msgs` required on BOTH machines since Session 16 Plan B (ball_detector) —
  `sudo apt install ros-jazzy-vision-msgs`

## Key Commands
```bash
# New terminal — .bashrc auto-sources ROS2, CycloneDDS, fleet-env, and workspace overlay.
# Only need to build + launch:
colcon build --symlink-install
ros2 launch src/nav_fleet/launch/sim_launch.py   # Session 09+ — Gazebo locally

# Run Python unit tests (venv auto-activated by .bashrc)
python -m pytest tests/ -v --ignore=tests/test_ros2_contracts.py \
  --ignore=tests/test_navigation.py --ignore=tests/test_mission_run.py \
  --ignore=tests/test_mission2.py

# Run a mission (repo root; sim must be up — see launch commands above)
python -m nav_fleet.mission_runner mission1

# Traceability gate
python tools/check_traceability.py requirements/traceability.yaml tests/ \
  --profile robot_profiles/jetson_ugv_pt.yaml

# Dashboard
streamlit run dashboard/app.py

# arm64 Docker build (Tier 2 — only after Tier 1 is clean)
docker buildx build --platform linux/arm64 \
  --tag ghcr.io/sdfinn/autonomous-fleet-testbed:latest --load .
```

## Directory Layout
- `src/nav_fleet/`         — ROS2 colcon package (nav runner, metrics collector)
  - `launch/sim_launch.py` — main launch file (Gazebo + bridge); Session 15 split it into
    `launch/sim_only_launch.py` (Gazebo + bridge) and `launch/nav2_only_launch.py` (Nav2
    bringup only — the mission executor is a separate third process,
    `python -m nav_fleet.mission_runner`), which `sim_launch.py` now composes for Tier-1 —
    the same split lets the two halves run on separate machines for HIL (Gazebo on x86,
    Nav2 on the Jetson).
  - `nav_fleet/semantic_map.py` — Session 15: `SEMANTIC_MAP` waypoint registry (doorway_center,
    home_base, ...) that missions reference by name
  - `nav_fleet/missions.py` — Session 15: mission data model (`MissionStep(action, label,
    location=None, yaw=None)`) — Mission 1 is navigate → take_picture → navigate
  - `nav_fleet/mission_runner.py` — Session 15: mission executor CLI
    (`python -m nav_fleet.mission_runner <mission_name>`)
  - `nav_fleet/failure_bag.py` — S17 Piece 3 (2026-07-21): rolling rosbag2 evidence on
    FAIL. Uses `ros2 bag record --snapshot-mode` (CLI-only, no rclpy API) — buffers
    `cmd_vel`/`scan`/`amcl_pose`/`navigate_to_pose`'s action-status in memory ONLY until
    the `/rosbag2_recorder/snapshot` service is called, which persists the buffered
    window to disk. `mission_runner.py`'s `main()` starts it before `rclpy.init()`,
    calls `snapshot()` only on FAIL/crash, and keeps the bag (`reports/failure_bags/`)
    only if that snapshot succeeded — zero disk cost on a passing mission. Prints
    `failure bag kept: <path>` on keep; `mission2_day.py`'s `JetsonExecutor` scrapes
    that line and `scp -r`s the bag back from the Jetson (mirrors the existing
    `_pull_photos` pattern).
  - `nav_fleet/image_io.py` — Session 15: `take_picture` action primitive support
    (`image_msg_to_png`), backed by pillow
  - `urdf/ugv_pt.urdf.xacro` — 4-wheel UGV robot URDF (diff-drive, lidar, camera)
  - `worlds/bedroom_simple.sdf` — real bedroom geometry from BC/isaac_project measurements
  - `maps/`                — pre-built Nav2 occupancy grid from BC project (0.05 m/px)
  - `config/nav2_params.yaml` — Nav2 params tuned for this room and robot
- `tools/`          — Python utilities (baseline monitor, telemetry logger, etc.)
  - `agentic_loop.py` — Session 13: reads the latest run + drift report, has Claude
    propose a nav2 param change / harder SDF world / mission plan, human approves.
    Requires `ANTHROPIC_API_KEY`. **Must run as `python -m tools.agentic_loop`, not
    `python tools/agentic_loop.py`** — the plain-script form fails with
    `ModuleNotFoundError` (see Gotchas). **`diagnose()` bug fixed, Session 17 Piece 5
    (2026-07-21):** it used to let Claude *infer* `current_value` for a nav2 param
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
    monkeypatches.
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
    and repeatable `--scenario` flags (breaking change from the old no-arg form).
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
    CLAUDE.md's `propagate=False` gotcha below if you add a new logger name and its
    output vanishes under pytest.
  - `pull_ros_logs.py` — S17 Piece 3 (2026-07-21): `python -m tools.pull_ros_logs` — the
    one documented command to retrieve a robot's ROS2 logs. `~/.ros/log/` has NO
    automatic retention (confirmed: 2,862 session dirs / 2.2 GB on the workstation
    alone, oldest 2026-06-28); this resolves rcl's own `latest` symlink (`readlink -f`,
    local or over `ssh` using `JETSON_USER`/`JETSON_IP` — same env vars as
    `scripts/hil_stage.sh`) and `scp -r`/`cp -r`s the session dir into
    `reports/ros_logs/`. `--host ''` forces local (no ssh).
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
- `tests/`          — pytest test suite
- `config/`         — drift_config.yaml
- `robot_profiles/` — Per-robot capability YAML
- `requirements/`   — Traceability matrix and requirement specs
- `docs/`           — architecture review notes, simulation-environments writeup, project
  overview slide deck (`autonomous-fleet-testbed-overview.pptx`, python-pptx generated)
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
  pull-back the very next CI run** — see the "Making a path absolute breaks every OTHER
  place..." Gotcha below for the regression and its 2026-07-22 fix.
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
- `.github/workflows/ci.yml` — 6-stage CI pipeline (job keys renumbered 2026-07-10 to match
  execution order — Gazebo is `stage-2-gazebo`, arm64 is `stage-3-arm64`, both gate
  `stage-4-isaac`; if older docs/notes say `stage-2-arm64`/`stage-3-gazebo`, that's the
  pre-2026-07-10 naming)
- `GazeboCommands.md` — Gazebo viewer navigation cheat sheet
- `docs/runbooks/Mission1HILSession15.md` — Session 15 Mission 1 hardware-in-the-loop runbook (Jetson +
  Gazebo terminal procedure) and the first real HIL run's Results (2026-07-11, PASS)
- `docs/superpowers/specs/` — dated design specs from `/superpowers:brainstorming` sessions
  (e.g. `2026-07-10-session15-gazebo-hil-mission1-design.md`) — read before continuing any
  session that has one; it's the source of truth over any summary in `Release1Todo.md`
- **`/home/mike/BC/isaac_project`** (outside this repo, not migrated) — has more reference
  material than what was pulled into this project. Notably `src/behavior_controller.py`
  (HSV color-threshold ball detection — proven, hardware-validated, zero training data) and
  `src/nav_controller.py` (the reactive coverage/avoidance mission it drives). `MasterBrief.md`
  in that same directory describes a fancier YOLO+ArUco design that was **never actually
  built** — don't trust that file over the real code when the two disagree (found 2026-07-10).

## Gotchas
- `.bashrc` now sources ROS2, CycloneDDS, fleet-env venv, AND workspace overlay automatically.
  After `colcon build`, a new terminal picks up all changes — no manual `source install/setup.bash` needed.
- `source install/setup.bash` still required in the same terminal that ran `colcon build`.
- Gazebo Harmonic command is `gz sim`, NOT `ign gazebo`
- URDF topics must use /robot_001/ namespace
- Launch file uses `pathlib.Path(__file__).parent.parent` instead of `get_package_share_directory`
  because `colcon-ament-python` is not installed — this is intentional and correct.
- OGRE2 (Gazebo Harmonic renderer) needs `<diffuse>` in SDF materials, not just `<ambient>`.
  Ambient-only = black surfaces. Both the SDF world and URDF gazebo blocks use `<diffuse>`.
- Isaac Sim session (Session 11): requires NVIDIA driver 570+. Driver 595.71.05 already installed.
- `requirements.txt` is a full pip freeze of the local ROS2 venv — NOT for CI use. Use `requirements-ci.txt` in CI jobs.
- DB path env var is `FLEET_DB` (default: `~/fleet-ci-data/fleet_runs.db`, owned by
  `tools/telemetry_logger.DB_PATH` — Session 17 Foundation piece, 2026-07-21; previously
  each of 6 files redeclared its own default independently, which is exactly how it
  drifted out of sync with CI's real path for 5 sessions) — used by telemetry_logger,
  validate_telemetry, dashboard, baseline_monitor, generate_test_report, agentic_loop
  (ai_test_generator/scenario_analyzer deleted 2026-07-19 — S17 review CR-05, rebuilt
  fresh in R2). `FLEET_TELEMETRY=off` skips writing a telemetry row entirely.
- **`ANTHROPIC_API_KEY` in `.bashrc` doesn't reach non-interactive shells/tools.** Ubuntu's
  default `.bashrc` has an early guard (`case $- in *i*) ;; *) return;; esac`) that skips
  the entire rest of the file when the shell isn't interactive — which includes Claude
  Code's own Bash tool. `source ~/.bashrc` there silently does nothing past that guard, so
  any export added below it (e.g. `ANTHROPIC_API_KEY` for `tools/agentic_loop.py`) never
  takes effect. Workaround for a non-interactive shell: `eval "$(grep '^export
  ANTHROPIC_API_KEY' ~/.bashrc)"` — targeted, doesn't print the key. Real terminals
  (interactive) are unaffected and work fine as-is.
- `tests/test_ros2_contracts.py` requires a live ROS2 environment — always `--ignore` it in local pytest runs
- `tests/test_navigation.py` also requires a live ROS2 environment (`import rclpy` at module
  level) plus a running Gazebo/Isaac + Nav2 stack — same treatment as `test_ros2_contracts.py`
  above. It was added in Session 10 but never added to `stage-1-quality`'s `--ignore` list in
  `ci.yml`, which silently broke that stage on a bare `ubuntu-latest` runner (no ROS2 at all)
  until Session 11/12 caught it. It's correctly run as an integration test in
  `stage-2-gazebo`/`stage-4-isaac`, where live ROS2 actually exists. If a new test file imports
  `rclpy` at module level, it needs the same `--ignore` treatment in `stage-1-quality` — this
  has now bitten twice. `tests/test_mission2.py` (Session 16+ Plan B camera-reactive Mission 2)
  is the same shape — live ROS2 + a running sim — and got the `--ignore` treatment in
  `stage-1-quality` up front this time (commit 0b77e10), correctly running instead as an
  integration test in `stage-2-gazebo`.
- **CI stage-0's traceability gate has `continue-on-error: true` — this is a live, ongoing gap,
  not stale.** Session 10 added `test_navigation.py`, but 2 of its 3 test function names never
  matched `requirements/traceability.yaml`'s placeholder names (fixed in Session 11/12: BR-01/
  BR-10 → `test_navigation_succeeds`, BR-02 → `test_no_collision`). BR-03 (recovery behavior)
  has no test at all — recovery is genuinely broken (see "Recovery behaviors" in
  `Release1Todo.md` Session 19+), so this isn't a naming fix, it's a real missing capability.
  Remove `continue-on-error` only once BR-03 has an actual test. Until then: this gate silently
  went from "intentionally red" to "actually blocking every downstream CI stage" once someone
  removed `continue-on-error` without the underlying gaps being fixed — check `gh run list`
  occasionally to make sure stage-3/stage-4 are still actually running, not skipped.
- **Under pytest in this repo, ANY new `logging.getLogger(...)` defaults to
  `propagate=False` — silently swallowing output.** Found 2026-07-20 building
  `tools/log_setup.py`: a test passed standalone (`python3 -c ...`) but failed under
  pytest with an empty log file, no errors, no exceptions. Root cause: the
  `launch-testing`/`launch-testing-ros` pytest plugins are *installed* (they show in
  `plugins:` even though `pytest.ini`'s `addopts` disables their hooks via
  `-p no:launch-testing -p no:launch-testing-ros`) — pytest still *imports* the plugin
  module during collection to know what to disable, and `launch.logging` runs
  `logging.setLoggerClass(LaunchLogger)` as an import side effect, which defaults
  `propagate=False`. This silently affects every NEW logger name created anywhere in
  a pytest run in this repo, not just `tools/log_setup.py`'s. Fix: any code creating
  its own logger must explicitly set `.propagate = True` rather than trust the
  default — see `tools/log_setup.get_logger()`.
- **Claude Code's own Bash tool runs with an isolated `/tmp`, separate from the real
  filesystem the user's browser/file manager sees.** Found 2026-07-21 (Session 17
  Piece 4): files written to `/tmp/...` via the Bash tool exist and are readable from
  *later* Bash calls in the same session, but Mike couldn't open them — they were
  never on his real filesystem. Files written inside the repo checkout (e.g.
  `reports/scratch-name.pdf`, cleaned up after) don't have this problem — that
  directory IS the real, shared filesystem (confirmed: it's what the IDE has open all
  session). Rule: when a file needs to be handed to the user directly (not served over
  a network port like Streamlit, which works fine from `/tmp` since a port isn't a
  filesystem path), write it inside the repo, not `/tmp`.
- **A "clean run" / "no drift" test that seeds a rolling baseline with IDENTICAL
  values gives a vacuous pass, not a real one.** Recurred at least 4 times across
  Session 17 (Foundation, Piece 4 ×2, Piece 5) — `baseline_monitor.check_run()`
  explicitly skips any metric whose baseline has zero variance
  (`if sd == 0.0: continue`), so a test seeding e.g. 11 identical
  `nav_success_rate=0.95` rows never actually compares anything — `flagged=False` is
  true only because nothing was checked, not because a real comparison found no
  drift. The fix pattern used throughout, matching `tests/test_baseline.py`'s
  original `_BASELINE_NAV_SUCCESS_RATES`: seed with real (small) variance
  (`0.94, 0.95, 0.96, 0.95, ...`) so `check_run()` performs a genuine comparison. The
  other legitimate way to dodge this trap (used once, in
  `test_build_trend_summary_reports_stable_metric`): bypass `check_run()` entirely by
  hand-constructing a `BaselineReport` and testing only the CONSUMING function's own
  formatting logic — sound as long as that consumer never reads `.sigma`/`.stddev`.
- **Making a path absolute breaks every OTHER place that assumed it was relative — a
  same-day regression, not a hypothetical.** The Piece 4 final-review fix above made
  `PHOTO_DIR` absolute; it fixed `stage-5-reports-*` but broke `tools/mission2_day.py`'s
  `_pull_photos()`, which still built the remote scp path as
  `f'...:autonomous-fleet-testbed/{rel}'` — correct when `rel` was checkout-relative,
  nonsense once `rel` became absolute. Silent failure: `mission_runner`'s own on-Jetson
  checklist still logged 100% PASS (the robot genuinely drove and photographed
  correctly, both variants), but every scp pull-back failed
  (`could not scp Jetson photo ...`, a WARNING not an error), so the workstation judge
  saw zero photos and FAILed all 3 mission2 variants in the very next CI run
  (29892759160, 2026-07-22) — a pure evidence-retrieval regression, not a
  navigation/perception bug. Compounding wrinkle found during the fix: the
  container-mode HIL path (`HIL_CONTAINER=1`) additionally lost the photos entirely —
  the image has no `USER` directive (`ros:jazzy-ros-base` default = root), so `PHOTO_DIR`
  resolves to `/root/fleet-ci-data` *inside the container*, which wasn't captured by the
  existing `-v $HOME/autonomous-fleet-testbed/reports:/ros2_ws/reports` bind mount at
  all — photos were written into the ephemeral container and vanished on `--rm`. Fixed
  (2026-07-22) with two changes in `tools/mission2_day.py`: (1) `_ssh_mission2` gained a
  second bind mount, `-v $HOME/fleet-ci-data:/root/fleet-ci-data`, so the container's
  root-HOME photos land in `JETSON_USER`'s real `fleet-ci-data` on the host; (2)
  `_pull_photos` gained `_remote_photo_path()`, which uses the logged absolute path
  verbatim for bare-metal (already the real host path) and substitutes the container's
  `/root` prefix for `~` in container mode (relying on the remote shell's own tilde
  expansion to land on `JETSON_USER`'s home) — covered by
  `test_pull_photos_bare_metal_uses_absolute_path_verbatim` and
  `test_pull_photos_container_mode_translates_root_prefix_to_tilde` in
  `tests/test_mission2_day.py`, the first tests either code path has ever had.
  `_pull_failure_bags` was NOT touched — `failure_bag.py`'s `BAG_DIR` is still
  checkout-relative, so its existing `autonomous-fleet-testbed/{rel}` scp path is still
  correct. **Lesson for next time: when a path constant changes from relative to
  absolute (or vice versa), grep every OTHER consumer of that same log line / directory
  convention, not just the one place the bug report points at** — Piece 4's own review
  found 3 duplicate relative-path bugs by doing exactly this for the *definition* side;
  this regression was the *consumption* side of the identical fix, missed because no
  task/review step in Piece 4 exercised a live HIL day's SSH pull-back, only photo
  existence-on-disk and dashboard rendering of already-local data.

- **The Jetson's `~/fleet-ci-data/` can be silently poisoned root-owned by a container-mode
  HIL run, breaking every later bare-metal run — found 2026-07-22 (Piece 7 timing exercise).**
  Root cause: the arm64 Docker image has no `USER` directive (default = root), and the
  2026-07-22 photo-pullback fix's bind mount (`-v $HOME/fleet-ci-data:/root/fleet-ci-data`)
  doesn't remap UIDs — every file a container-mode run (`HIL_CONTAINER=1`, which every
  CI `stage-4-hil` run uses) writes there lands root-owned on the Jetson's real disk. A
  later bare-metal run (`HIL_CONTAINER` unset — any manual local proof) runs
  `mission_runner.py` as `mike` over plain SSH, which then can't create files in a
  root-owned directory (mode 755 — group/other have no write bit): `PermissionError` on
  the first photo save, immediately followed by a cascading
  `sqlite3.OperationalError: attempt to write a readonly database` when it tries to log
  even the crash itself — looks exactly like the robot never started (it didn't: it died
  at mission step 1, before any navigation). Fix applied: `chown -R mike:mike
  ~/fleet-ci-data` + `chmod -R u+rwX,g+rwX` + setgid (`g+s`) on the directories so a
  FUTURE root-written file still lands in a group mike can traverse/create alongside.
  This can recur any time a container-mode run touches the directory again — if a bare-
  metal run gets a `PermissionError`/readonly-database crash with zero navigation
  logged, check `ls -la ~/fleet-ci-data` on the Jetson before assuming a code regression.
- **A real motion-start stall on HIL exists starting from the 2nd goal of a Mission 2 day
  onward and is NOT visible in any Nav2 log line — confirmed live 2026-07-22, root cause
  still unknown, NOT fixed (Piece 7 stays open until it is).** Live-narrated observation
  (Mike watching the Gazebo viewer while Claude tailed the Jetson's real Nav2 stdout log
  and correlated timestamps in real time, twice) confirmed: the FIRST goal of a HIL day
  (fresh Nav2 stack) starts the robot moving right when `controller_server` logs
  "Received a goal, begin computing control effort" — no stall. The 2nd and 3rd goals
  (no_ball→yellow, yellow→red transitions) do NOT: the robot visibly sits still for a
  real, observable stretch AFTER that same log line appears, then starts moving on its
  own with no further log activity in between — no abort, reject, or retry logged by
  bt_navigator/controller_server/planner_server.
  **Ruled out:** fresh-process cold start alone — bt_navigator/controller_server are the
  SAME persistent processes across all 3 runs (only `mission_runner` restarts per run
  over SSH), yet goal #1 on that persistent stack is clean and #2/#3 aren't.
  **Also ruled out (weaker, worth re-checking):** "goal right after a cancellation is
  slow to settle" — no_ball's own run ends via NORMAL SUCCESS (arrival home), not a
  cancelled goal, yet the FOLLOWING transition (into yellow's first goal) still stalled.
  So the trigger looks like "which goal number this is for the Nav2 stack's lifetime,"
  not specifically "did the prior goal get cancelled."
  **Diagnostic plan for next time (not yet done, in this order):**
  1. Add timestamped debug logging in `nav_runner.py` around goal dispatch — log the
     instant the goal is sent, the instant the "goal accepted" callback fires, and the
     instant odometry/feedback first shows non-negligible velocity. This turns the stall
     into something measurable from a log, not something that needs a human watching a
     screen every time.
  2. Live-watch `/robot_001/cmd_vel` publish activity (`ros2 topic echo`) during a
     transition: is the controller actually publishing near-zero velocity commands
     during the stall (a controller-side issue — e.g. RPP still converging/rotating),
     or is it publishing real commands that aren't reaching the simulated robot (a
     bridge/DDS issue)? This is the fastest way to split the hypothesis space in half.
  3. Check whether the same stall appears on a goal WITHIN a single run (e.g. no_ball's
     own return-home leg, its 2nd goal within the same mission_runner process) — this
     would tell us whether the trigger is "2nd+ goal of the whole Nav2 stack's uptime"
     (survives across mission_runner restarts) vs. something scoped to inter-run
     transitions specifically.
  4. If (1)-(3) point at costmap/localization settling rather than the controller
     itself, check AMCL/costmap timestamps around the stall — the log already shows a
     "Received request to clear entirely the global/local costmap" line right at goal
     start; worth checking whether that clear-and-rebuild has a real settle cost that
     grows after the first goal.
  Piece 7 (Release1Todo.md) tracks this as confirmed-but-unroot-caused — do not mark it
  done until an actual fix (not just a diagnosis) lands.
  **UPDATE 2026-07-24 (Piece 9, Release1Todo.md): likely explained, under a different
  framing, not the one this entry originally used.** A much deeper live investigation
  (jetson_clocks, DEBUG-level Nav2 logging, live cmd_vel watching, x86-vs-Jetson A/B)
  found TWO separate real things, neither of which is "motion won't start": (1) an
  inter-scenario gap (~17.6s on Jetson, ~0.4s on x86) caused by `mission_runner`
  restarting as a fresh SSH-spawned process every scenario on Jetson vs. staying
  resident in-process on x86 — fix designed, not yet implemented (see the
  `mission2_day.py` entry above); (2) a ~18-29s intra-goal
  "pegged rotation" stall, reproducible identically on x86 AND Jetson, bare-metal AND
  container — platform-independent, likely a `yaw_goal_tolerance`/RPP tuning issue,
  still not root-caused. Neither is "no log activity, no abort/reject/retry" in the
  way originally described — DEBUG-level logging (not available at the time this entry
  was written) shows real, continuous, explainable activity in both cases. Leave this
  entry as historical context; treat Piece 9 as the current source of truth.
- **Docker/JetPack "docker exec is slow" write-ups are a plausible-sounding dead end for
  ANY delay that occurs mid-mission on the Jetson, not just this one — verify against
  bare-metal before spending time here.** Found 2026-07-24 (Piece 9): a detailed,
  specific-sounding explanation (PAM/`systemd-logind` D-Bus timeout, cgroups-v2 driver
  mismatch, NSS/mDNS hostname lookup, `nvidia-container-runtime` hook overhead — all
  real, documented JetPack 7.2 + Ubuntu 24.04 phenomena in general) was offered for the
  Piece 9 inter-scenario/intra-goal delays. All of it is about `docker exec -it ...
  bash` SESSION-STARTUP latency specifically. Two things rule it out for any delay that
  happens ONCE a mission is already running: (1) `controller_server`/`bt_navigator` are
  NEVER containerized in EITHER HIL mode — `scripts/hil_stage.sh run` always launches
  them as bare host processes via `nohup ros2 launch`, regardless of `HIL_CONTAINER`;
  (2) the fastest way to check is simply reproducing the SAME delay in bare-metal mode
  (`HIL_CONTAINER` unset) — if it's still there with zero Docker involved anywhere in
  the path, Docker was never the cause. Don't skip straight to Docker-daemon-config
  changes for an in-mission delay without this check first.
- **jetson_clocks is a legitimate, fast (~5s), reversible test for "is this CPU/GPU/
  memory clock throttling" — but confirm it actually changed something before trusting
  a null result.** `sudo jetson_clocks --show` before/after: if `CurrentFreq` already
  equals `MaxFreq` on all cores before running it (i.e. the CPU governor already has
  you at the current power mode's ceiling), running `jetson_clocks` again will lock
  GPU/EMC higher but can't push CPU past a ceiling it was already at — a "no change"
  result there rules out DVFS/idle-scaling specifically, not "not enough Jetson compute
  at this power mode" in general (a genuinely higher `nvpmodel` mode, e.g. MAXN_SUPER,
  is a separate, bigger test with real deployment-power tradeoffs — don't conflate the
  two).
- **A DEBUG-level dump of `ros2 launch`'s log is enormous (hundreds of thousands of
  lines for one ~18s goal, mostly `[rcl]`/`[rcl_action]` subscription-taking noise) —
  grep it, don't read it.** Found 2026-07-24 (Piece 9): useful signal (goal-received/
  reached lines, `bt_navigator`'s "unknown goal" feedback-tracking messages,
  `controller_server`'s "Control loop missed its desired rate" warnings) is present but
  buried; filter explicitly for `[rcl]:`/`[rcl_action]:`/`[rmw` exclusion plus the
  specific node-tagged messages you care about, and use Python (not shell `awk`, whose
  default `mawk` on this box lacks 3-arg `match()`) for timestamp-windowed extraction
  from a raw Jetson-side log file over SSH.
- **A 1-second-bucketed "max value per bucket" summary of a live topic can look
  identical to "continuously pegged at max" even when it isn't — always spot-check
  against raw, unbucketed samples before drawing a conclusion from a bucketed one.**
  Practice adopted 2026-07-24 (Piece 9) after this exact concern was raised mid-
  investigation: a cmd_vel bucketing script reporting `max|ang_z|=0.5000` for 7
  straight 1-second buckets was checked against the raw per-sample stream before being
  trusted — in that specific case the raw data DID confirm genuinely continuous
  pegged commands (smooth ramps, no gaps), but the check itself is now a standing
  practice for any bucketed live-topic analysis in this project, since the failure
  mode (a brief real blip inflating an otherwise-quiet bucket to look "pegged") is
  real and easy to miss.
- **When a live GUI-watched observation contradicts an already-computed timing number,
  re-derive the number from the SAME event the observer is describing before arguing
  with the observation.** The costliest mistake in Piece 9 (Release1Todo.md,
  2026-07-24): an intra-goal delay (`goal accepted` → `goal result received`, ~18-29s,
  confirmed identical on x86 and Jetson) was conflated with the inter-scenario gap Mike
  was actually describing (`goal result received` → next scenario's dispatch) — which
  turned out to be ~40x different between platforms (~0.4s x86 vs. ~17.6s Jetson) and
  fully explained his repeated, correct, "watching the whole time" observation. Don't
  minimize a repeated, specific live observation as "which moment you happened to be
  watching" — re-measure the SPECIFIC boundary being described first.

## Nav2 Launch Gotchas (Session 10+)
- `gz sim` WITHOUT `-s` launches a GUI that crashes on this machine (snap/glibc libpthread conflict)
  and takes the Gazebo server down with it. Always use `gz sim -s -r <world>` (server only).
  To view the simulation separately: `gz sim -g` (GUI client only, connects to running server).
- **The snap/glibc GUI crash is caused by snap-VS-Code environment pollution — and it hits the
  separate `gz sim -g` client too when launched from a VS-Code/Claude-Code shell** (found
  2026-07-12: `GTK_PATH`/`GTK_EXE_PREFIX`/etc. point into `/snap/code/...`, whose GTK modules
  drag in snap core20's libpthread → `symbol lookup error: __libc_pthread_init`). Plain user
  terminals are unaffected. Workaround from a polluted shell — scrubbed environment:
  ```bash
  env -i HOME=$HOME USER=$USER TERM=xterm PATH=/usr/local/bin:/usr/bin:/bin DISPLAY=:0 \
    XAUTHORITY=${XAUTHORITY:-/run/user/1000/gdm/Xauthority} \
    bash -c 'source /opt/ros/jazzy/setup.bash && gz sim -g'
  ```
- **Jetson powered off ⇒ local sim breaks (silently) unless `ROS_LOCALHOST_ONLY=1`.** With the
  Jetson down, `enp6s0` goes `NO-CARRIER`/DOWN and CycloneDDS floods "Exception sending a
  multicast message: Network is unreachable" — DDS discovery fails, so Nav2 never reaches
  "Managed nodes are active" (found 2026-07-12). For any local-only session while the shared
  link is down, prefix EVERY command (launch, mission runner, pytest) with
  `ROS_LOCALHOST_ONLY=1`. All processes must agree — mixing localhost-only and normal
  processes means they can't see each other. Unset it (or use fresh terminals) for HIL work.
- The ros_gz_bridge must be delayed ~5s after Gazebo starts. If the bridge subscribes before
  Gazebo's gz-transport publishers are up, the GZ→ROS subscriptions silently fail (no reconnect).
- Nav2 Jazzy requires `use_composition: 'True'` (capital F). 'False' launches ~16 separate
  processes that exhaust CycloneDDS domain 0 participant limit.
- Nav2 Jazzy requires collision_monitor with `polygons` + `observation_sources` populated (empty
  lists fail). Docking_server requires `dock_plugins`. Both added to nav2_params.yaml.
- Nav2 Jazzy `controller_server` requires `progress_checker_plugins` (plural, list) NOT the old
  `progress_checker_plugin` (singular string). Also requires `controller_frequency`,
  `costmap_update_timeout`, `failure_tolerance`, `use_realtime_priority` — see Jazzy defaults.
- **TF architecture (multi-robot):** RSP publishes frames by URDF link name (no prefix: `odom`,
  `base_footprint`, `lidar_link`). diff_drive `<frame_id>` and `<child_frame_id>` must also be
  unprefixed (`odom`, `base_footprint`). Both sources publish to `/robot_001/tf` (RSP remapped).
  Nav2 with `namespace:robot_001` + `use_namespace:true` subscribes to `/robot_001/tf` — per-robot
  TF isolation is at the TOPIC level, not the frame-name level. frame_prefix NOT supported in
  Jazzy RSP 3.3.4.
- nav2_params.yaml frame names (`base_frame_id`, `odom_frame_id`, `robot_base_frame`) must use
  unprefixed frame names (`odom`, `base_footprint`, `base_link`) to match RSP output.
  Topic names (`scan_topic`, `odom_topic`) still use `/robot_001/` prefix — those are correct.
- **ros_gz_bridge direction:** Use `[` (GZ→ROS) and `]` (ROS→GZ) NOT `@` (bidirectional).
  Bidirectional on `/robot_001/tf` creates an echo loop: AMCL's map→odom goes ROS→GZ→ROS,
  causing "jump back in time" warnings that clear the TF buffer continuously.
  Rule: odom/scan/camera/imu/tf/clock = `[` (GZ→ROS). cmd_vel = `]` (ROS→GZ).
- Gazebo GPU lidar publishes scan with frame_id = `robot_001/base_footprint/lidar` (Gazebo internal
  entity path). A zero-offset static TF from `lidar_link` → `robot_001/base_footprint/lidar`
  is needed in the launch file (lidar_frame_bridge node).
- Nav2 bringup with `use_namespace:true` + `namespace:robot_001` remaps all Nav2 topics to
  `/robot_001/` prefix. The action server is at `/robot_001/navigate_to_pose`.
- AMCL `set_initial_pose: true` with initial_pose params works — sets pose to bedroom origin.
- **Gazebo RTF:** RTX 5080 runs Gazebo at ~3x real-time. After 95s wall time, sim time is ~280s.
  Old sim-time TF data from a previous run can pollute a fresh TF buffer if the nav2 container
  isn't fully killed. Power down between debug sessions to avoid stale data.
- **Killing sim processes:** `pkill` on individual processes is unreliable — orphaned Gazebo
  and nav2 container processes persist. Correct approach: Ctrl+C on the `ros2 launch` foreground
  process (it sends SIGINT to the whole process group). For CI, the launch process is killed by
  the runner's job cleanup. Never chain `pkill` calls hoping to clean up mid-session.
- **Orphaned `parameter_bridge`/`static_transform_publisher` processes poison EVERY later sim
  run on their DDS domain — including CI (domain 0).** Found 2026-07-15: 13+ bridges had
  accumulated across a debug day because every teardown pattern checked
  `gz sim|component_container|robot_state_publisher|ros2 launch` and none matched
  `parameter_bridge`, `static_transform_publisher`, or `ekf_node`. gz-transport has NO DDS
  domain isolation, so an old bridge attaches to any NEW Gazebo server and re-publishes
  /clock + TF into its OLD domain: two interleaved /clock publishers → out-of-order stamps →
  tf2 "Detected jump back in time" floods (8,716 in one CI run) → AMCL can't anchor TF →
  goals REJECTED, and the nav2 container can even SIGABRT on an uncaught
  `tf2::NoDataForExtrapolationException`. The COMPLETE teardown/verify pattern is:
  `pgrep -af "gz sim|component_container|robot_state_publisher|ros2 launch|parameter_bridge|static_transform|ekf_node"`.
  stage-2 in ci.yml now sweeps this pattern before launch and after the job. Also: unique
  `ROS_DOMAIN_ID` per local run only hides leftovers, it doesn't prevent them — and reusing a
  domain number (or running on 0, like CI) collides with them. From a Claude Code shell,
  subagent-spawned leftovers may not respond to sandboxed pkill — kill by explicit PID with
  sandbox disabled if the pattern kill reports success but pgrep still shows them.
- **Headless Gazebo here renders via llvmpipe (software) — a newly spawned model takes up to
  ~1.5 s to appear in camera frames.** Found 2026-07-17 (Mission 2 calibration): a fixed
  `sleep(1.0)` after `gz service` spawn is flaky; poll-until-detected (≤5 s, 0.5 s steps) is
  the pattern for any test/tool that spawns a model then expects the camera to see it.
  **Removal lags too** (found same evening): a REMOVED model lingers in rendered camera
  frames for seconds — back-to-back tests reacted to the previous test's "ghost" ball.
  Hence `BALL_REMOVAL_SETTLE_S = 3.0` after `remove_ball` in tests/test_mission2.py.
- **`pkill -f`/`pgrep -f` SELF-MATCH: the pattern matches the invoking shell's own command
  line.** Bit twice on 2026-07-17: a teardown containing `pkill -INT -f "ros2 launch …"`
  plus a relaunch of that same string SIGINT'd its own shell (exit 144) and never killed the
  target; a `pgrep -f "gz sim -g"` check listed itself. Rules: derive PIDs with
  `ps -eo pid,cmd | grep/awk` + `grep -v grep` (or `awk '/[r]os2 launch/'` bracket trick),
  kill by explicit PID, and never put the literal pattern in the same command that greps
  for it.
- **CI triggers ONLY on push-to-main and PRs targeting main** — pushing a feature branch
  runs nothing. To exercise CI from a branch, open a (draft) PR; that's what draft PR #4
  is for on `mission2-camera-reactive` (2026-07-17: full 8-job green first try, incl.
  stage-4 HIL on the Jetson, run 29626889652).
- **Mission 2 state (post-2026-07-18, Task 13 Option B):** Mission 2 is now ONE
  self-returning mission — a verified round trip, not a one-way drive. Five steps: (1) home
  reference photo BEFORE any movement, (2) navigate to the floor marker with reactions armed
  (red 1.3 m -> `photo_then_stop`, yellow 0.8 m -> `photo_then_home`), (3) marker photo,
  (4) navigate itself HOME (no external reset leg), (5) home arrival photo — must MATCH the
  reference (see `tools/mission2_harness.judge_home_pair` / `HOME_PAIR_MAX_DIFF`, a
  gross-failure guard, not a precision instrument — see its comment in
  `tools/mission2_harness.py`). The mission's own per-waypoint checklist (`runner.checklist`,
  printed by `mission_runner.main()`) IS the verdict. A fired reaction SHORTENS the mission
  (Option B): red stops in place after its photo (no further steps); yellow folds its own
  return-and-arrival-photo into the reaction, so the pair check still applies. The no-ball
  scenario is renamed `mission2_no_ball` (was `mission2_nominal`) — old telemetry rows keep
  their old name, only new rows use the new one. Marker (0.9, 3.90) / ball (1.2, 3.90) now
  sit EAST of the dresser (Mike's GUI review, 2026-07-18) — see `semantic_map.py`'s
  `sphere_approach`/`MARKER_XY` comments for the clearance math. `tools/mission2_day.py` is
  THE single day orchestrator — it is stage-4's only Mission 2 step, the GUI demo command,
  and the future real-robot-day runner, all running the SAME sequence (no_ball -> yellow ->
  red). Ball placement is pluggable (`GzBallOps` for sim/HIL, `OperatorBallOps` for a human
  on the real robot) and mid-return placement is part of the choreography: the yellow ball
  is placed DURING no_ball's return leg, and yellow is swapped for red DURING yellow's
  return leg (both behind the retreating robot, after a settle — reactions are
  outbound-only, so this can't self-trigger). Judges enforce min-travel (≥0.5 m before a
  reaction counts) + start-position preconditions. World sun `cast_shadows` is FALSE
  (observability; detection revalidated live shadow-free). Detector ignores
  frame-edge-clipped bboxes (clipped width corrupts the range estimate). `-k red`-style
  pytest filters are substring matches — the ignore test was renamed after `-k red` matched
  `…is_ignoRED`.
  **One continuous day, S17 Piece 9 (2026-07-25, branch `fix/hil-container-lifecycle`,
  PR #5, not yet merged): the day is now ONE continuous execution, not 3 externally-invoked
  scenario calls.** Supersedes both the old per-scenario architecture AND Piece 8's
  persistent-container fix below (which became unnecessary once there's only one
  invocation per day). `mission_runner.py` gained `MissionRunner.run_mission2_day()`
  (loops `run_mission('mission2')` 3x in one process, collects each leg's
  checklist/photos/reaction_events) and a `--day` CLI mode (prints one
  `MISSION2_DAY_RESULT:<json>` line). `tools/mission2_day.py`'s `InProcessExecutor`/
  `JetsonExecutor` both implement `run_day() -> list[dict]` — `JetsonExecutor.run_day()`
  is now a SINGLE `docker run --rm`/bare-SSH call for the whole day (Piece 8's
  `_start_container`/`close()`/`HIL_CONTAINER_NAME`/`docker exec`-into-a-persistent-
  container machinery was REMOVED, not kept dormant, since one call/day has nothing
  left to amortize). `run_no_ball`/`run_yellow`/`run_red` (the old scenario-named
  functions) are DELETED. Ball choreography is now `GroundTruthLog` (continuous
  timestamped ground-truth samples for the whole day, `record`/`nearest`/
  `closest_approach_to`) + `run_ball_choreography()` (ONE thread for the whole day,
  concurrent/gz mode only — `if ball_ops.concurrent:` guards it, so operator mode gets
  no thread and no ball_ops calls at all: **no prompting of any kind** — Mike's explicit
  call, "it's up to the human to place the balls at the correct time themselves,
  watching the robot," `OperatorBallOps.place`/`.remove` (the old `input()`-prompting
  methods) were removed as unreachable). `_judge_and_log_leg`/`run_day()` (top-level)
  replace the old `run_no_ball`/`run_yellow`/`run_red`, feeding `judge_*`/
  `log_variant_row`/`home_pair_similarity` (unchanged signatures — frozen by design)
  from post-hoc `GroundTruthLog` lookups instead of live point-in-time polls.
  **Measured result: 0.0000s leg-to-leg loop overhead**, confirmed 3x independently
  (x86 in-process, Jetson bare-metal, Jetson container) — down from the ~17.6s Jetson
  inter-scenario gap this piece targeted (see Release1Todo.md Piece 9 for the full
  investigation, the scrapped persistent-service/DDS-RPC first direction, and the
  design conversation).
  **Two real bugs found live during GUI-watched verification, both fixed the same
  session (neither anticipated by the plan) — see Release1Todo.md Piece 9 for full
  detail:** (1) a premature yellow→red ball swap — the second retreat-wait armed a
  fresh `RetreatDetector` immediately after placing yellow, while leg 1's OWN return
  was still in progress, getting fooled by leftover leg-1 descent into firing almost
  instantly; fixed with a new `OutboundDetector` (mirrors `RetreatDetector` — tracks
  the lowest y seen, fires once climbed back up `climb_m` above it) that gates the
  second wait behind a genuine "robot has left home again" signal. (2) an 8-second
  ground-truth-polling stall, TWICE per leg (`get_ground_truth_xy()` in
  `ground_truth.py` runs `gz topic -e` with `GZ_POSE_TIMEOUT_S`, which off-sim can
  never succeed and always burned the full timeout) — pre-existing (Session 13-era),
  not a Piece 9 regression, just newly VISIBLE once Piece 9 removed the bigger cost
  that used to mask it; fixed by cutting `GZ_POSE_TIMEOUT_S` 8.0 -> 1.0 (evidence-based:
  measured real local x86 response 0.09-0.11s, ~10x margin retained) rather than an
  env-var-gated skip, since a timeout fix covers HIL now AND any future real-robot
  runner-type automatically.
  **Known, deliberately accepted/deferred gap:** `final_x`/`final_y` telemetry columns
  are now always `0.0` for Mission 2 rows (both executors return plain dicts, not a
  live object with `.nav.last_final_x` for `log_variant_row` to read — its signature
  is frozen by this piece's own design). Confirmed the HIL path was ALREADY zeroed
  before this change; only x86 loses real data; `mean_position_error` (the actual
  drift-watched metric) was never sourced from Mission 2 rows either way — no
  monitoring capability lost. A real fix exists (thread the robot's own final-position
  estimate through the leg dict, same treatment photos already get) but Mike
  deliberately deferred it: Mission 2 is scripted/hardcoded so the fix would be easy,
  but Mission 3 will be autonomous enough that "final position" may not even be a
  well-defined concept — that design work should decide the shape of this fix, not
  a Mission-2-specific patch made now.
- **nav_runner goal stamp:** Use `Time().to_msg()` (zero timestamp = "use latest TF") for the
  NavigateToPose goal header stamp. Wall-clock `get_clock().now()` will be rejected by Nav2
  which uses sim time (far-future wall timestamp has no TF data in Nav2's buffer).
- Self-hosted CI runner: labels `self-hosted, x86, gpu, rtx5080`. Service: actions.runner.*.service.
  Token must be regenerated if expired (GitHub → Settings → Actions → Runners → Add Runner).
- **4-wheel diff-drive: ALL wheel joints must be in the plugin.** The Gazebo Harmonic
  `gz-sim-diff-drive-system` plugin supports multiple `<left_joint>`/`<right_joint>` entries.
  If only rear wheels are driven and front wheels are passive `continuous` joints, the front
  wheels resist in-place rotation via lateral friction — the robot cannot rotate. The odom is
  computed from the DRIVEN wheel joint positions only, so it reports rotation even when the body
  is physically stationary. Fix: include all four wheel joints.
  ```xml
  <left_joint>rear_left_wheel_joint</left_joint>
  <left_joint>front_left_wheel_joint</left_joint>
  <right_joint>rear_right_wheel_joint</right_joint>
  <right_joint>front_right_wheel_joint</right_joint>
  ```
- **RPP (RegulatedPurePursuitController) — two params required for in-place rotation:**
  `use_collision_detection: false` (default true fires before rotation on tight corridors) and
  `rotate_to_heading_min_angle: 0.3` (17° — lower than the 45° default to catch small heading
  errors from diagonal SMAC paths).
- **SMAC Planner 2D vs NavFn:** NavFn A* penalises diagonal grid moves (cost √2 vs 1.0),
  producing north-first paths. SMAC 2D uses equal cost for all 8 directions — it naturally
  routes diagonally toward the goal. Use SMAC when diagonal paths matter for controller heading
  error. Plugin: `nav2_smac_planner::SmacPlanner2D`.
- **bt_navigator `default_server_timeout` 20ms → 1000ms is the ROOT FIX for the cold-goal
  abort storm** (Task 13 fix wave, 2026-07-18): on a fresh mission_runner process, the FIRST
  goal was sometimes accepted then aborted in ~0.1-0.25s before the robot moved. Cause: the
  BT's internal goal-ack window (20ms default) is too short on a loaded Jetson — the
  controller_server's ack legitimately takes longer than that under load, so bt_navigator
  gives up on a goal that was actually fine. Worse, the controller could go on to EXECUTE the
  delivered path after bt_navigator had already aborted the handle — a "zombie goal": the
  robot drives with no supervising mission, a real safety issue on hardware. Fix has two
  parts: the timeout bump (root fix, `src/nav_fleet/config/nav2_params.yaml`
  `default_server_timeout: 1000`) removes the race at the source; `nav_runner.py`'s bounded
  cold-start retry (escalating `sleep(2.0 * (attempt+1))` backoff, `COLD_ABORT_RETRIES`) is
  now just a safety net for whatever the timeout doesn't catch, not the primary fix; and a
  cancel-on-failure guard (`NavRunner._last_goal_handle`) cancels any still-outstanding goal
  before reporting failure, so a giving-up mission can never leave an unsupervised robot
  driving.
- **`yaw_goal_tolerance` tightened 0.5 → 0.15 rad** (`src/nav_fleet/config/nav2_params.yaml`):
  needed for home-pose squareness — Mike observed the robot arriving home visibly
  off-heading (nosed left) even though the old 0.5 rad (~29°) tolerance called it arrived.
  0.15 rad (~8.6°) is what makes Mission 2's home-arrival photo actually match the reference
  pose (see `HOME_PAIR_MAX_DIFF` in `tools/mission2_harness.py` for why photo similarity
  alone can't police this).
- **stage-4-hil runs ONLY the deployment mission** — the day orchestrator
  (`tools/mission2_day.py`), invoked via `scripts/hil_stage.sh day`. Mission 1 stays in
  stage-2 (sim regression, `tests/test_mission_run.py`); it is no longer run on hardware as
  a warm-up. `hil_stage.sh run` is now just the stack-up gate (sim + Nav2, no mission, no
  retry) — a mission failure must surface RED, so all harness-level whole-mission retries
  were removed (the in-process cold-goal retry above is the only retry left anywhere).
- **GUI-watched Mission 2 day, the command sequence:** bring the HIL stack up with
  `scripts/hil_stage.sh run`, view it with the scrubbed-env `gz sim -g` recipe above (the
  snap/glibc GUI-crash workaround), then run `DAY_HOLD_S=10 scripts/hil_stage.sh day` — the
  env var reaches `tools/mission2_day.py --hold-s` and keeps the robot in place after the
  final red run so an observer sees an unambiguous "done" instead of the process exiting
  mid-frame.
- **`hil_stage.sh sync` works only with PUSHED shas** (`git fetch origin <sha>` of an
  unpushed commit fails "not our ref") — and the Jetson's local `main` only advances via
  `restore-checkout`, which fast-forwards since d3bb66e (2026-07-19; before that it sat on
  week-old code and silently invalidated a bare-metal bug repro). Manual Jetson runs:
  sync to `$(git rev-parse origin/main)`, and verify with `git log -1` on the Jetson.
- **A "CI-exact" local HIL run must export `POWER_MODE_ID=0` (15W) for the run/day steps.**
  ci.yml's stage-4 builds at 25W then drops to 15W for the mission (deployment power,
  2026-07-14); `hil_stage.sh`'s default is 1 (25W) — a full local day at the default
  silently tests a faster Jetson than CI does (this masked the 15W axis during the
  2026-07-19 yellow-bug forensics).
- **Container-mode HIL image tag: verified locally before the day starts, since S17 Piece
  2's container preflight (`JetsonExecutor._require_image_local`, `tools/mission2_day.py`).**
  The sign-off false start hit this: a wrong `HIL_IMAGE` tag → GHCR pull denied → `docker
  run` dies in ~2s → looked exactly like three silent mission failures with no clue why.
  Now `JetsonExecutor.__init__` SSHes a `docker image inspect` check before any mission
  runs and raises one loud error naming the missing tag. **Tag gotcha (the root cause):**
  CI's `pull_request` builds tag the image with the synthetic MERGE-commit sha
  (`GITHUB_SHA`), NOT the branch head sha — a manual container-mode run must read the real
  tag from the CI run's env or `docker images` on the Jetson, never construct one from
  `git rev-parse`.
- **The 2026-07-18 "yellow bug" is an UNREPRODUCED INTERMITTENT, instrumented not fixed:**
  post-merge stage-4 died 3/3 that night (goal-end abort → bt_navigator bond drop →
  lifecycle cascade → GraphicsMagick SIGSEGV in recovery map-load), then 2026-07-19 went
  12/12 local + 1/1 CI green at the same sha with every code suspect exonerated. Leading
  theory: accumulated Jetson uptime/load state (reboots preceded every green). Since
  d3bb66e stage-4 uploads the Jetson `nav2_hil_*.log` in the mission-evidence artifact —
  on any recurrence, pull the artifact FIRST; full dossier + forensics in
  `.superpowers/sdd/progress.md` ("FORENSICS DAY 2026-07-19"). The GraphicsMagick env
  knobs (`MAGICK_THREAD_LIMIT=1 OMP_NUM_THREADS=1`) are VERIFIED delivered to the Nav2
  processes (/proc/environ) — if the SIGSEGV recurs, the knob is insufficient, not missing.

## Isaac Sim Gotchas (Session 11+)
- **Version:** `isaacsim==6.0.1.0` is the correct pip package (`isaacsim[all,extscache]==6.0.1.0`
  for the full bundle). Isaac Sim 5.x was never published to pypi.nvidia.com.
- **EULA:** Set `OMNI_KIT_ACCEPT_EULA=YES` env var (or `os.environ` before import) for headless
  non-interactive use. Without it, the process hangs at an interactive prompt.
- **Import ordering:** ALL `omni.*` and `isaacsim.*` imports must come AFTER `SimulationApp` is
  instantiated. The Carbonite framework won't load extensions before the app exists.
- **URDF import API (6.0):** Use `URDFImporter(URDFImporterConfig(...)).import_urdf()` from
  `isaacsim.asset.importer.urdf`. The old `omni.kit.commands.execute("URDFCreateImportConfig")`
  command is not registered in 6.0.
- **URDF prim layout after import:** The importer adds a `Geometry` layer:
  `/ugv_pt/Geometry/base_footprint/base_link/...` (not `/ugv_pt/base_footprint/...`).
  Joints are at `/ugv_pt/Physics/`. Always traverse the stage after import to discover paths.
- **USD output path:** Pass `usd_path="/tmp/..."` (outside the repo). If the path already exists,
  the importer creates versioned subdirs (`ugv_pt_1/`, `ugv_pt_2/`, ...) inside it.
- **RTX lidar headless:** In headless mode, `IsaacSensorCreateRtxLidar` creates an `OmniLidar`
  prim (not a Camera prim). No sensor-specific render product is created — only the generic
  `/Render/OmniverseKit/HydraTextures/Replicator` product exists. `ROS2RtxLidarHelper` can't
  get scan data from it. Use `RotatingLidarPhysX` (PhysX raycasting) for headless scan publishing.
- **RotatingLidarPhysX frame key:** Frame dict key is `'linear_depth'` (not `'linear_depth_data'`).
  Call `lidar.add_linear_depth_data_to_frame()` before `initialize()`, then `get_current_frame()`
  in the loop. Publish via rclpy `sensor_msgs/LaserScan` manually.
- **IsaacSensorCreateRtxLidar orientation:** Pass `Gf.Quatd(w, x, y, z)` not a plain tuple —
  plain tuples are interpreted as `GfVec4d` and cause a USD type mismatch error.
- **ROS2 bridge extension name (6.0):** `isaacsim.ros2.bridge` (not `omni.isaac.ros2_bridge`).
  Import path: `from isaacsim.core.utils.extensions import enable_extension`.
- **OmniGraph odom chassis prim:** `IsaacComputeOdometry` needs the articulation root (`/ugv_pt`),
  not a link prim. Link prims fail with "not a valid rigid body or articulation root".
- **`/clock` must be explicitly published via OmniGraph.** `isaacsim.ros2.bridge` does NOT
  auto-publish `/clock`. Without it, Nav2 nodes with `use_sim_time: true` stay at time 0 — their
  clocks never advance, they request TF at t≈0, but all TF data from Isaac starts at the sim time
  when Isaac started (e.g. t=24s). Add `ROS2PublishClock` to the OmniGraph:
  ```python
  ("PublishClock", "isaacsim.ros2.bridge.ROS2PublishClock"),
  # connect: OnTick→execIn, SimTime→timeStamp, Context→context
  ```
- **Scan timestamps must use Isaac timeline directly** (`omni.timeline.get_timeline_interface().get_current_time()`),
  NOT `rclpy Node.get_clock().now()`. The rclpy clock with `use_sim_time` returns 0 before the first
  /clock message arrives, causing AMCL to anchor map→odom at t≈0 while odom TF starts at t=24s+.
- **OmniGraph TF topic must be namespaced:** `PublishTF.inputs:topicName` defaults to `/tf` but
  Nav2 with `namespace:robot_001` + `use_namespace:true` subscribes to `/robot_001/tf`. Set:
  `("PublishTF.inputs:topicName", f"/{NS}/tf")`
- **PhysX wheel velocity drives must be set programmatically.** The URDF importer warns
  "Stiffness and damping not available" for wheel joints with no `<dynamics>` tag — it creates
  velocity drives with damping=0. `set_joint_velocity_targets()` is silently ignored. Fix:
  set `damping=100` via `UsdPhysics.DriveAPI.Apply` AFTER `robot.initialize()`:
  ```python
  from pxr import UsdPhysics
  for dof in robot.dof_names:
      jp = stage.GetPrimAtPath(f"{ARTIC_ROOT}/Physics/{dof}")
      drive = UsdPhysics.DriveAPI.Get(jp, "angular") or UsdPhysics.DriveAPI.Apply(jp, "angular")
      drive.GetDampingAttr().Set(100.0)
      drive.GetStiffnessAttr().Set(0.0)
  ```
- **Scan timestamp source (GUI mode):** `omni.timeline.get_timeline_interface().get_current_time()`
  reads the Python/app thread which is stale in GUI mode. Use `rclpy Node.get_clock().now()` AFTER
  OmniGraph has published `/clock` (gate on `clock_now.nanoseconds > 0`).
- **`spin_once(timeout_sec=0)` misses cmd_vel with CycloneDDS.** Zero-timeout returns immediately;
  async DDS messages are consistently missed. Fix: background `SingleThreadedExecutor` daemon thread:
  ```python
  from rclpy.executors import SingleThreadedExecutor
  import threading
  _exec = SingleThreadedExecutor(); _exec.add_node(ros_node)
  threading.Thread(target=_exec.spin, daemon=True).start()
  ```
  Remove `rclpy.spin_once()` calls from the main loop entirely.
- **DDS TRANSIENT_LOCAL TF replay — must restart Isaac AND Nav2 together.** Isaac's
  `/robot_001/tf` publisher uses TRANSIENT_LOCAL QoS. DDS caches the full TF history. Any new
  Nav2 subscriber (even if Isaac kept running) gets the entire history replayed, causing thousands
  of "jump back in time" warnings and goal rejection. Rule: kill BOTH Isaac and Nav2 between runs.
  Start Nav2 within ~5s of Isaac's "Simulation running" message so the replayed history is small.
  **Worth investigating (2026-07-06), not yet done:** `scripts/isaac_bedroom_gui.py`'s
  `ROS2PublishRawTransformTree` OmniGraph node has no explicit QoS override — TRANSIENT_LOCAL
  is just whatever it defaults to, not a setting anyone chose deliberately. Standard ROS2
  convention is `/tf` on VOLATILE QoS (only `/tf_static` should be TRANSIENT_LOCAL). If that
  node exposes a `qosProfile` input, overriding it to VOLATILE could remove this restart
  requirement at the source instead of managing around it forever — hasn't been tried yet.
- **Global costmap obstacle_layer causes "Start occupied" on replan — only with periodic
  replanning.** During navigation, live lidar scans of furniture (e.g. PC tower) accumulate in
  the global costmap's obstacle layer. If the BT triggers a *periodic* replan from a position
  adjacent to that furniture, the global planner finds the start cell occupied and aborts.
  Session 11 fix was to remove `obstacle_layer` from `global_costmap.plugins`. Session 11/12's
  minimal one-shot BT (`navigate_simple.xml` — plan once, no `RateController` replanning loop)
  removes the actual trigger for this, so `obstacle_layer` was restored to the global costmap
  (matches `BC/isaac_project`). If a future BT reintroduces periodic replanning, this failure
  mode comes back and `obstacle_layer` should come back out of `global_costmap.plugins`.
- **`PYTHONUNBUFFERED=1` + `python -u` required.** Isaac's stdout is fully buffered when piped
  to a file — the "Simulation running" message is never flushed without these flags.
- **A ROS2 params YAML's top-level key must equal a node's exact, unqualified name.** Giving a
  node `namespace='robot_001'` in a hand-rolled launch file changes its real name to
  `/robot_001/controller_server`, which no longer matches a plain `controller_server:` key in
  the params file — no error, just a silent fall-through to compiled-in defaults (this is how
  `DWBLocalPlanner` got loaded instead of our configured RPP, with "no critics defined" as the
  only clue). `nav2_bringup`'s `bringup_launch.py` avoids this with its own namespace-templating
  machinery (`ReplaceString`/`<robot_namespace>`). For hand-rolled Nav2 launches: don't namespace
  the node at all — apply the `/robot_001/` prefix entirely through explicit **absolute**
  topic/action remappings instead (see `nav2_isaac_launch.py`).
- **Composable nodes can't accept an empty-list parameter.** A node loaded via a container's
  `load_node` service call (as `nav2_bringup`'s composition does) crashes on `polygons: []` /
  `observation_sources: []` — `Expected 'value' to be ... got '()' of type 'tuple'`. The
  parameter bridging code can't infer an empty array's element type. A reference config with
  this exact syntax can still "work" if its launch never actually instantiates that node live
  (that's why `BC/isaac_project`'s config has this and never hits the bug). Workaround for
  `collision_monitor`: give it one real, harmless polygon instead of an empty list — e.g. a 2cm
  square, smaller than the lidar's own minimum range, so it can never actually trigger.

## Isaac GUI Nav Test — Terminal Procedure (Session 12+)

Three terminals. **Do not start Nav2 more than ~5s after Isaac is ready** (DDS TF history grows
with every second Isaac runs; a late Nav2 startup gets thousands of replayed messages).

**Terminal 1 — Isaac (start first):**
```bash
# New terminal (auto-sources from .bashrc)
cd ~/autonomous-fleet-testbed
colcon build --symlink-install && source install/setup.bash
DISPLAY=:0 OMNI_KIT_ACCEPT_EULA=YES PYTHONUNBUFFERED=1 python -u scripts/isaac_bedroom_gui.py
```
Wait for: `[Isaac] *** Simulation running ***`

**Terminal 2 — Nav2 (start IMMEDIATELY after Terminal 1 is ready):**
```bash
# New terminal
cd ~/autonomous-fleet-testbed
ros2 launch src/nav_fleet/launch/nav2_isaac_launch.py
```
Wait for: `Managed nodes are active` and `Setting pose … -1.276 1.200 1.571`

**Terminal 3 — Test:**
```bash
# New terminal
cd ~/autonomous-fleet-testbed
python -m pytest tests/test_navigation.py::test_navigation_succeeds -v --timeout=120
```

**Optional Terminal 4 — Monitor AMCL (run after Nav2 active):**
```bash
ros2 topic echo /robot_001/amcl_pose
```

**Between runs:** `pkill -9 -f "isaac_bedroom|component_container_isolated|robot_state_publisher"`
then wait 5s for DDS to clear before restarting.

## Jetson Orin Nano Gotchas (Session 14+)

Full step-by-step runbook: `docs/runbooks/JetsonInstallSession14.md`. **Parts 1–9 done as
of 2026-07-13** — Part 9's NVMe FRESH INSTALL executed: headless SDK Manager recovery
flash to NVMe (~12 min), re-provisioned end-to-end from the runbook (Part 9 step 11
inlines all of it), NVMe-at-25W baselines recorded (Part 7 table: colcon 5.312s ≈ SD tie;
docker pull 1m40s = 2.5× vs SD; cold arm64 CI build 568s ≈ SD 585s), runner re-registered
and **proven by a full 8-job-green CI cycle (run 29301726080)**. **Session 14 is COMPLETE
(2026-07-14):** step 14's closeout + `Mike@`→`mike@` doc sweep done, and step 13c — the
manual HIL run on the NVMe install — **passed first-attempt 2026-07-14** (multicast DDS
across the link, mission PASS, photo + `hil_jetson` telemetry row on the Jetson; results
in the runbook at 13c). **Session 16 SIGNED OFF 2026-07-19** (`stage-4-hil` live, Mission 2
merged, GUI day + clean CI run 29697469463) — next: Session 17 scoping (see Release1Todo).
Confirmed-for-this-board state, not guesses: username **`mike`** (lowercase, matches the
workstation — the SD era's capital-M `Mike` is gone; old docs saying `Mike@` predate
2026-07-13), hostname **`jetson`** — **`ssh mike@jetson.local` works via mDNS** (needed
the post-hostname reboot; fresh installs also ship NO `127.0.1.1` line in `/etc/hosts` —
one was added; don't put a static entry on the workstation, the DHCP lease moves). IP
still `10.42.0.217` (lease — re-check with `ip neigh show dev enp6s0`), rootfs on NVMe
`/dev/nvme0n1p1` (456G, 421G free), GUI off (`multi-user.target`, idle RAM 433 MB), CUDA
still intentionally absent (OS-only flash). The microSD rollback was released 2026-07-15
(stage-4-hil 3×-green condition met). GHCR pulls on the Jetson need
`gh auth refresh -s read:packages` then `gh auth token | docker login ghcr.io -u sdfinn
--password-stdin` (the image is private; gh's default scopes lack packages).
- **Power mode: pinned to 25W (`sudo nvpmodel -m 1`) on 2026-07-12.** Orin Nano Super modes:
  0=15W (the out-of-box state we found), 1=25W, 2=MAXN_SUPER. `sudo nvpmodel -q` to query,
  `-p --verbose` to list, `-m <id>` to set; the chosen mode **persists across reboots** via
  `/var/lib/nvpmodel/status`. The SD-era build baselines predate the pin (mode unrecorded
  — flagged historical in the Part 7 table); **NVMe-at-25W is the go-forward reference,
  recorded 2026-07-13**. The pin was re-applied on the NVMe install (Part 9 step 10 ✅).
  `sudo jetson_clocks` additionally locks clocks at the mode's max but does NOT persist —
  suitable as a per-job CI step, not a set-and-forget.
- **JetPack 7.2 removed the microSD card image.** The old "flash an SD image with Etcher and
  boot it" workflow no longer exists. Flash via **SDK Manager** over USB-C in recovery mode
  (what we used), or the Jetson-ISO-on-USB installer as a fallback (needs a monitor+keyboard).
- **NVIDIA SDK Manager's "Download for Ubuntu" button is a login-gated browser redirect with
  no stable URL** — not curl/wget-able directly. Use the apt network-install method instead:
  ```bash
  wget https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2404/x86_64/cuda-keyring_1.1-1_all.deb
  sudo dpkg -i cuda-keyring_1.1-1_all.deb
  sudo apt-get update && sudo apt-get -y install sdkmanager
  ```
- **Recovery mode:** short `FC REC`↔`GND` on the J14 header while applying DC power, hold ~2–3s
  after power comes on, then release. Verify from the host with `lsusb | grep -i nvidia` →
  expect `0955:7523 NVIDIA Corp. APX`. A charge-only USB-C cable (no data lines) is the #1
  cause of recovery mode not being detected.
- **SDK Manager's OEM pre-config screen isn't guaranteed to ask for all three fields.** It
  prompted for username/password but silently skipped hostname on this flash — don't assume
  "it asked for some fields" means "it asked for all of them"; check `hostname` after first
  boot before relying on `<hostname>.local` mDNS (it won't resolve if hostname wasn't set).
- **`ssh-copy-id` requires an existing local SSH keypair** — `ssh-keygen -t ed25519` first if
  `~/.ssh/*.pub` doesn't exist, or it fails with `ERROR: No identities found`.
- **`ping` failing after the shared-Ethernet setup doesn't necessarily mean NAT is broken.**
  Confirmed on this network: `ping nvidia.com` gets 100% packet loss even with `ip_forward=1`,
  `ufw` inactive, and a correct `MASQUERADE` rule with live, incrementing packet counters
  (`sudo iptables -t nat -L POSTROUTING -n -v`). The network silently drops outbound ICMP;
  `curl -I http://nvidia.com` or `curl -s ifconfig.me` from the Jetson is the real test.
- **Target Components (CUDA/cuDNN/TensorRT) are worth skipping on the first flash.** Uncheck
  them in SDK Manager for a clean OS-only flash, confirm boot, then add later with
  `sudo apt install nvidia-jetpack` if on-device GPU inference is ever needed (L4T apt sources
  are already present post-flash — no re-flash required). `nvcc: command not found` and empty
  `dpkg-query --show nvidia-jetpack` are expected in this state, not a problem.
