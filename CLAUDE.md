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
- `src/nav_fleet/` — ROS2 colcon package (nav runner, metrics collector, Nav2 launch
  files). Package internals and Nav2 launch gotchas: `src/nav_fleet/CLAUDE.md`.
- `tools/` — Python utilities (baseline monitor, telemetry logger, etc.), including the
  telemetry DB and `reports/` conventions. Details: `tools/CLAUDE.md`.
- `dashboard/app.py` — Streamlit telemetry dashboard. Details: `dashboard/CLAUDE.md`.
- `scripts/` — Isaac Sim scripts (`isaac_bedroom_gui.py` etc.) and `hil_stage.sh`. Isaac
  Sim gotchas: `scripts/CLAUDE.md`; the manual GUI nav-test procedure is the
  `isaac-gui-nav-test` skill.
- Jetson Orin Nano hardware (flashing, power modes, SSH/mDNS): the `jetson-hardware-notes`
  skill.
- `requirements/`   — Traceability matrix and requirement specs
- `docs/`           — architecture review notes, simulation-environments writeup, project
  overview slide deck (`autonomous-fleet-testbed-overview.pptx`, python-pptx generated)
- `.github/workflows/ci.yml` — CI pipeline (job keys renumbered 2026-07-10 to match
  execution order — Gazebo is `stage-2-gazebo`, arm64 is `stage-3-arm64`, both gate
  `stage-4-hil`, real-hardware-in-the-loop on the Jetson runner; `stage-4-isaac` was
  retired in Session 16 — if older docs/notes say `stage-4-isaac` or
  `stage-2-arm64`/`stage-3-gazebo`, that's pre-Session-16/pre-2026-07-10 naming)
- `GazeboCommands.md` — Gazebo viewer navigation cheat sheet
- `docs/runbooks/Mission1HILSession15.md` — Session 15 Mission 1 hardware-in-the-loop runbook (Jetson +
  Gazebo terminal procedure) and the first real HIL run's Results (2026-07-11, PASS)
- `RealRobotStartup.md` — the real-robot bring-up runbook (2026-07-28), extracted from
  `Release1Todo.md`'s Session 18 into its own living doc (same class of exception as
  `JetsonInstallSession14.md` — one of only two living runbooks outside
  `Release1Todo.md`, deliberately not sprawl). Part A = one-time setup (driver
  bring-up, SLAM map, `robot_launch.py`); Part B = the repeatable day-to-day loop,
  including the physical Jetson swap required to get back into HIL mode (confirmed
  single-Jetson deployment, no dedicated CI runner).
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
- **`.github/workflows/ci.yml` uses CRLF line endings — a raw Python `open(path).read()`/
  `open(path, 'w').write()` round-trip silently strips them all to LF, producing a
  1000+-line noise diff that buries the real 2-line change.** Found 2026-07-26 (Piece 2
  second-round review fixes): patched two `pkill` lines via a small Python script for a
  `str.replace()` across 2 occurrences — worked, but `git diff --stat` showed 1102 lines
  changed for what was actually a 6-line diff, because text-mode Python I/O converts
  CRLF→LF on read and never restores it on write. No other file in this repo has this
  issue (checked: only `ci.yml` is CRLF). Fix used: `git checkout HEAD -- <file>` to
  restore the original CRLF, then reapply the SAME edit via the Edit tool instead (which
  does an exact string replacement without a full-file read/write round-trip and
  correctly preserves CRLF) — verified after with `file ci.yml` still reporting "with
  CRLF line terminators". Rule: never touch `ci.yml` with a raw Python/shell
  read-modify-write script; always use Edit (or `sed -i` with GNU sed, which also
  preserves line endings) for this specific file.

## See also (moved out of this file by /doctor, 2026-07-27, context-lazy-loading pass)
- Nav2 launch gotchas (Session 10+) — `src/nav_fleet/CLAUDE.md`
- Isaac Sim gotchas (Session 11+) — `scripts/CLAUDE.md`
- Isaac GUI nav-test terminal procedure (Session 12+) — `isaac-gui-nav-test` skill
- Jetson Orin Nano hardware gotchas (Session 14+) — `jetson-hardware-notes` skill

