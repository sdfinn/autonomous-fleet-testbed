# autonomous-fleet-testbed — Claude Code Context

## Project
Open-source CI/CD-native fleet simulation testing framework for autonomous robots.
Session plans and the release roadmap are tracked in internal planning docs (not part
of this public snapshot); this file captures the durable technical context and
gotchas that survive across sessions.
**Releases relabeled 2026-07-17: numbers now = execution order.** The agentic &
alignment layer is **R2** — docs/notes older than 2026-07-17 saying "R4" mean today's
R2. Ladder: R1 Foundation → R2 Agentic & Alignment → R3 Fleet & Input Expansion → R4
Autonomy & Perception → R5 Self-Testing Fleet; drone CUT (revivable with reason).

## NEXT SESSION — START HERE (2026-08-04 — docker-brain unification SHIPPED, merged, live-validated on real hardware; Task 9 closed)

**The whole docker-brain-unification effort (all 9 tasks) is done and merged to
`main`.** Implemented via subagent-driven-development in an isolated worktree (Tasks
1-8, each independently reviewed, plus two rounds of whole-branch review), merged
`feat/docker-brain-unification` → `main` same day, then pushed straight to CI
(deliberate call, skipping the plan's own manual-first Task 9 steps — see below for
why that was still the right call). Nav2/EKF/`ball_detector`/`mission_runner` now run
identically, via one container/one entrypoint (`scripts/container_entrypoint.sh`), on
both HIL and the eventual real robot — differing only by env-var values
(`use_sim_time`/`hsv_config`/`map`/self-report vs. judged).

- **First-ever fully green CI run including a real, live `stage-4-hil` on the actual
  Jetson** (run `30970690023`) — the container-based HIL path, container-based real-
  robot path, and the whole convergence this branch exists for are now proven on real
  hardware, not just on paper.
- **Pushing straight to CI (skipping manual Task 9 verification first) found 2 real
  bugs a manual-only path might have taken longer to catch** — both fixed live,
  same day, re-verified green:
  1. A stale pre-existing unit test (`tests/test_pipeline_matrix.py`) outside every
     diff any reviewer looked at, still asserting the pre-branch `bedroom_nav`
     scenario — `config/pipeline_matrix.yaml`'s `real` stage was correctly changed by
     Task 4, the test just never got updated. `stage-1-quality` caught it correctly.
  2. **`container_entrypoint.sh` crashed immediately (1.7s, before Nav2 ever started)**
     — `/opt/ros/jazzy/setup.bash: line 8: AMENT_TRACE_SETUP_FILES: unbound variable`.
     ROS2's own `setup.bash` isn't `set -u`-safe; `hil_stage.sh`'s `sim_up()`/
     `ws_source()` already work around this exact issue (`set +u` bracketing the
     source calls) — this brand-new file just never inherited that guard. Nothing in
     Task 3's manual verification (`docker buildx build` succeeding) could have caught
     this, since that only proves the image builds, not that the entrypoint runs. Fix:
     same `set +u`/`set -u` bracket, matching the established pattern exactly.
  A separate, one-off infra hiccup also hit `stage-3-arm64` mid-session: a GHCR push
  got stuck on a genuinely dead, half-closed TCP connection (`FIN-WAIT-1`, confirmed
  via `ss`) — not a code issue, not GHCR being down (direct `curl` to `ghcr.io/v2/`
  was healthy throughout) — cancel + rerun fixed it immediately. Worth knowing this
  failure mode exists if `stage-3-arm64` ever hangs post-build-step with no forward
  log progress for several minutes.
- **GUI-watched runs, both sim and HIL, done live with Mike watching, both fully
  PASS** (all 3 legs, no_ball/yellow/red) — results saved for comparison at
  `~/fleet-ci-data/{sim,hil}_gui_comparison_2026-08-04/` (log + photos + telemetry
  rows each). Yellow leg's `home_photo_similarity` matched almost exactly between sim
  and HIL (0.033 vs 0.034); `no_ball` diverged more (0.112 vs 0.029) — not flagged as
  a problem by either run's own judging, just a real difference worth knowing exists.
  Ollama/VLM canary fired successfully on all 4 runs checked (2 CI, 2 manual),
  correctly identifying "a red ball" every time, zero errors — confirmed the
  `--ingest-vlm-canary` step is CI-only, `hil_stage.sh day` doesn't call it on its own
  (a manual HIL run's canary result needs that step run by hand or it's stranded on
  the Jetson).
- **Task 9 closed, deliberately, with Step 2 not completed — decided with Mike, not
  a gap to revisit:** Steps 1/3/4 (build-on-Jetson / full HIL day / push+CI-proof) are
  genuinely done, on real hardware. Step 2 (an isolated container run with
  `MISSION2_SELF_REPORT=1`, no Gazebo, no real robot) was attempted twice — first
  attempt was contaminated by a leftover HIL Gazebo simulation from an earlier
  run that never got torn down (a real process-hygiene mistake, not a product bug —
  the still-running workstation Gazebo's live camera bridge fed the "isolated"
  container a real detection of its own leftover red ball); teardown fixed that, but
  the clean rerun then hit a genuine wall: **Nav2 never reaches "active" at all with
  zero sensor input of any kind** (no camera, no lidar, no odometry — `local_costmap`
  times out after 120s unable to get the `map` transform, since AMCL/EKF have nothing
  to localize against). Building a stub sensor source just to unblock this would
  amount to reinventing Gazebo badly — Mike's call, and the right one: not worth it.
  `mission_runner`'s actual self-report telemetry code path (the thing Step 2 was
  meant to validate) was therefore never exercised by either attempt — genuinely
  inconclusive, not proven, not a real risk either (the actual deployed robot will
  have real sensors, so this specific "zero sensors at all" failure mode shouldn't
  occur there). The self-report path's real validation waits for the actual physical
  robot.

**What's next (no urgency, no firm date — whenever the physical robot is ready):**
`RealRobotStartup.md` Part A (one-time setup: real SLAM map, real-camera HSV
calibration via `calibrate_hsv_realcam.py`, install `robot_boot.sh` +
`robot-mission.service`) then Part B (day-to-day operation) — this is the only
remaining piece that needs the actual hardware. Nothing else is blocking. Older,
lower-priority backlog items (Release 1→2 branching/tagging, self-hosted-runner CI
docs) are unrelated carryover from before this session, still open, not urgent.

## (superseded 2026-08-04) PREVIOUS (2026-08-03 evening — docker-brain implementation, Tasks 1-4 of 9 done)
**Spec reviewed/approved earlier this session** (with two real deviations from the
original spec text, decided live with Mike — see below), **implementation plan
written and execution started via subagent-driven-development, 4 of 9 tasks
complete.** Work is happening in an isolated git worktree, NOT on `main`:
`/home/mike/autonomous-fleet-testbed/.worktrees/feat/docker-brain-unification`
(branch `feat/docker-brain-unification`) — `cd` there to resume, don't redo this
work on `main`. Nothing has been pushed anywhere.

- **Plan:** `docs/superpowers/plans/2026-08-03-docker-brain-real-robot-hil-unification-plan.md`
  (9 tasks, already committed to `main` and inherited by the worktree).
- **Ledger (full task-by-task history, gitignored — worktree-local, not on `main`):**
  `.worktrees/feat/docker-brain-unification/.superpowers/sdd/progress.md`.
- **Done, each independently reviewed (spec + quality) via the subagent-driven-development
  loop, all Approved:** Task 1 (`nav2_only_launch.py` launch args), Task 2
  (`mission_runner.py` self-report telemetry for the real robot), Task 3 (Dockerfile +
  new `scripts/container_entrypoint.sh` — real arm64 build verified, ~39 min under QEMU
  emulation on this workstation since the Jetson runner wasn't used for this manual
  check), Task 4 (`pipeline_matrix.yaml` real-stage scenario fix — was stale, still
  pointing at the old BR-01 gate).
- **Real bug found + fixed along the way:** a `grep -c ... || echo 0` double-print bug
  in `container_entrypoint.sh`'s Nav2-readiness wait loop (the plan's own transcribed
  code carried this forward from an existing, unrelated bug already present in
  `robot_boot.sh`) — fixed to match `hil_stage.sh`'s already-correct pattern, re-reviewed
  clean. **`scripts/robot_boot.sh` itself still has this same bug on `main` today,
  unfixed** — Task 6 (below) replaces that file's Nav2-wait loop entirely with a
  container invocation, so it'll disappear there as a side effect, not a targeted fix;
  worth confirming that actually happens when Task 6 lands.
- **Two important deviations from the design spec doc's literal text, decided live with
  Mike this session, NOT yet folded back into the spec file itself** (the spec doc at
  `docs/superpowers/specs/2026-08-03-docker-brain-real-robot-hil-unification-design.md`
  still describes the ORIGINAL, wider idea — reading the spec doc alone would be
  misleading; the plan doc's own "Global Constraints" section has the real, current
  decision):
  1. Ball placement, ground-truth reading, and judging (`tools/mission2_harness.py`)
     stay workstation-side for HIL, unchanged from today — NOT moved into the
     container's self-orchestration as the spec originally described. Reason: they use
     `gz`/Gazebo-transport, a separate protocol from CycloneDDS with unverified
     cross-machine reachability, and that harness code never runs on the real robot
     either way (no Gazebo there) — so moving it wouldn't actually converge HIL with
     the robot, just add unproven risk.
  2. The real robot does NOT get ground-truth judging at all (impossible — no Gazebo,
     no oracle) — it self-reports each leg's own PASS/FAIL and saves logs/photos;
     analysis happens after, manually, not in real time.
  Consider updating the spec doc itself to match, or at least adding a pointer at its
  top to the plan's Global Constraints section, before this is forgotten.
- **Remaining, in order:** Task 5 (`JetsonExecutor`/`hil_stage.sh` → always-container
  HIL, the biggest remaining piece — retires the bare-metal Nav2-on-Jetson path
  entirely), Task 6 (`robot_boot.sh`/`robot-mission.service` rewrite), Task 7 (`ci.yml`
  cleanup — drop the now-dead `HIL_CONTAINER` env var), Task 8 (`RealRobotStartup.md`
  doc updates — A5/A6 + intro item 2), Task 9 (manual hardware-verification
  checkpoints — needs live Jetson access, cannot be subagent-dispatched, needs Mike or
  a session with real SSH access to the robot).
- **Known process-hygiene lesson from this session, worth carrying into future
  subagent-driven-development dispatches in this repo:** an implementer subagent left
  orphaned `gz sim`/`robot_state_publisher` processes running after its own manual
  live-ROS verification step — the controller had to sweep them by hand
  (`CLAUDE.md`'s own documented teardown pattern). Future dispatch prompts for any task
  that launches Gazebo/Nav2 should explicitly include a teardown/sweep step, not just a
  check-before-launch step.

**Summary of the decision this spec captures:** reverses the 2026-08-01 bare-metal-
end-to-end call — item 1 of that session's punch list ("does `stage-3-arm64` still
earn its keep") got a real answer: yes, restructured. Nav2/EKF/`ball_detector`/
`mission_runner`/`mission2_day` all move into one Docker container long-term (driver
layer stays bare, Ollama stays bare); HIL and the real robot converge onto the exact
same container entrypoint and the exact same `nav2_only_launch.py` (parameterized by
3 new launch args — `use_sim_time`/`hsv_config`/`map` — not a separate
`robot_launch.py` file); the biggest single piece of rework is HIL's own orchestration
moving from workstation-SSH-dispatch onto the Jetson's own container, matching how
the real robot already has to run. Mike's explicit framing for this reversal: decide
on long-term architectural merit for the fleet testbed's future, not on which
direction avoids rework — read the spec's own "Context" section for the full
reasoning, and its "Known implementation-time risks" section before starting
implementation.

## (superseded 2026-08-03) PREVIOUS (2026-08-01, evening session — real robot deploy rewrite)
**Item 1, first thing next session (Mike's explicit ask): review the docker/no-docker
decision and review what real value `stage-3-arm64` is providing.** This session found
(see `docs/bare-metal-vs-container-decision.md` for the full writeup, and the
`RealRobotStartup.md` rewrite) that the container role HIL actually proved was always
narrower than the original 2026-07-27 "containerized brain" decision — only the raw
`mission_runner.py --day` ROS2 loop ever runs in a container, never Nav2/EKF/
`ball_detector`, and the real robot's own deployment (`scripts/robot_boot.sh`) ended up
bare-metal end to end, not using the Docker image at all. Given that, is `stage-3-arm64`
(the native arm64 build, ~10 min of the pipeline) still earning its keep, or has its
actual value shrunk now that the real robot doesn't consume its output? Concretely to
revisit: does `stage-4-hil` still need the arm64 image at all (currently gates
`HIL_CONTAINER=1`'s mission_runner-in-container run), or could HIL also move to running
`mission_runner.py --day` bare, matching what the real robot now does — collapsing two
divergent "how does the mission actually run" paths into one? Not decided, not started —
this is the open question to bring to Mike, not a predetermined answer.

Also carried forward, not yet started: item 4 (Release 1 → Release 2 planning — branching
strategy, `r1-complete` tag now real per the deploy rewrite above) and item 6 (GitHub CI
pipeline docs, self-hosted runner setup writeup) from the prior punch list below.

**This evening's session, full summary:** `RealRobotStartup.md` fully rewritten (was
last-verified 2026-07-28, materially stale against everything hardened since — WiFi/DDS/
avahi fixes, HIL hardening's 6 fixes, container-mode findings). Real-time collaborative
correction with Mike caught several wrong assumptions before they got written down:
mission target moved from BR-01/`test_navigation.py` to the mission2 3-leg day
(`sim_vs_real_comparison.py`'s correlation gate dropped entirely — log/drift analysis is
R2 scope per Mike); the architecture is bare-metal end to end (not the originally-planned
containerized brain, corrected mid-conversation after tracing the ACTUAL `nav2_up()`/
`JetsonExecutor` code, not the plan doc); power-on now fully automates the mission via a
new `scripts/robot_boot.sh` + `scripts/robot-mission.service` (systemd, `network-
online.target`-gated) — NOT yet exercised by CI/HIL (can't simulate a power cycle there),
manual-first-then-systemd is the explicit safety pattern in the doc. New: `tools/
calibrate_hsv_realcam.py` (+ 4 tests) — a real, previously-missed gap, since mission2's
yellow/red legs need real-camera HSV thresholds that never mattered under the old
BR-01-only gate. `docs/bare-metal-vs-container-decision.md` is a new standing reference
(the honest architecture-drift story, written for reuse — design reviews, interview prep).
**Nothing in this session has been pushed** — Mike wanted to log off; everything is
committed locally on `main` only, push next session after a final look.

## (superseded 2026-08-01 evening) PREVIOUS (2026-08-01, paused mid-Item-3, machine-safety pause)
Session continued the 2026-07-31 punch list. Items 1 and 2 fully closed out today
(details below and in the dated Gotchas). Item 3 (real code coverage) is IN PROGRESS —
deliberately paused, not blocked on anything code-related, purely because the
workstation (this repo's self-hosted CI runner) is unsafe to run Gazebo on right now —
see the new dated Gotchas entries below before resuming. Punch list for next time, in
order:
1. ~~**Remove the duplicate mission2 tests from stage-2.**~~ **Done 2026-08-01.**
   `tests/test_mission2.py` (the 3 old per-scenario no_ball/yellow/red tests) deleted
   outright — confirmed redundant with `tools/mission2_day.py`'s in-process run
   already in the same stage (same 3 legs, same judging, plus VLM canary coverage the
   old tests never had). Every reference across `ci.yml`, `README.md`,
   `tools/mission2_harness.py`, and `src/nav_fleet/CLAUDE.md` updated or repointed at
   `mission2_day.py`. **Audit of the rest of stage-2's suite (`test_navigation.py`,
   `test_mission_run.py`, `test_nav_runner.py`) — conclusion: nothing else moves.**
   `test_nav_runner.py`/`test_mission_run.py` mock out Nav2 itself (no live Gazebo
   needed for their own logic), but all 4 files still `import rclpy` at module level,
   and `stage-1-quality` (bare `ubuntu-latest`) never installs `rclpy` — only the
   ROS2 apt repo + `ros-jazzy-ament-*` lint tools, confirmed by reading that job's
   steps directly. Moving any of them would require installing full ROS2
   (`ros-jazzy-ros-base`+) in stage-1, which defeats its whole "cheap/fast feedback"
   purpose — not done. Already optimally split as-is.
2. ~~**Revisit CI + PDF output.**~~ **Done 2026-08-01.** Sim PDF (`sim-report-159-DRIFT.pdf`)
   confirmed correct: VLM canary text appears exactly once, under `mission2_red`'s own
   section, never duplicated into `no_ball`/`yellow`. The HIL PDF (`hil-report-159.pdf`)
   check found a REAL bug, not just an unfinished verification: `ingest_vlm_canary_
   from_jetson()` (`tools/mission2_day.py`) was joining the wrong photo directory
   (`state_dir` instead of `PHOTO_DIR`) — a copy of the reaction-red photo exists in
   BOTH directories with the same basename but a different absolute path, and
   `find_vlm_canary_results()`'s exact-string join silently matched nothing. Confirmed
   directly against the real `fleet_runs.db` (run 690): the `photos` column and
   `vlm_canary_log.photo_path` pointed at two different directories for the same
   photo. Every HIL PDF report has shown ZERO canary text since the feature shipped
   2026-07-31, even though the canary genuinely ran and was ingested every time. Fixed
   with a one-line change (glob `PHOTO_DIR`, not `state_dir`), TDD throughout (test
   rewritten to prove the bug RED, fix confirmed GREEN, full 435-test suite still
   green) — commit `bba663b`.
3. **Real code coverage — CI wiring done + validated 2026-08-01, pure-local (no
   third-party site).** A Codecov-hosted design was built first, then dropped the
   same day — pushing real coverage data to an external site "did not sit well"
   with Mike (his words), and a live CI run had already surfaced that Codecov's
   tokenless upload doesn't actually work for this repo by default anyway (`error
   -- Upload queued for processing failed: {"message":"Token required - not valid
   tokenless upload"}` — confirmed from the real job log, not assumed from docs).
   Rebuilt entirely on `coverage.py`'s own built-in `coverage combine` instead —
   still `pytest-cov`, no new dependency, no network call, no token.
   **How it works:** `.coveragerc` (repo root) scopes measurement to `tools/` +
   `src/nav_fleet/nav_fleet/` and omits the 3 hand-invoked hardware debug scripts
   (`calibrate_ball_range.py`, `direct_drive_test.py`, `ghcr_prune.py`). `stage-1-
   quality` and `stage-2-gazebo` (the latter via `coverage run -a` across BOTH the
   pytest integration tests AND the in-process `mission2_day` run, so the VLM-
   canary code path is covered too, not just what pytest touches) each save their
   own `.coverage` data file (renamed `.coverage.stageN`) as a GitHub Actions
   artifact. A new job, **`coverage-report`** (needs `stage-2-gazebo`, runs even on
   a stage-2 FAILURE — best-effort, same pattern as `stage-5-reports-hw`),
   downloads both artifacts, computes each stage's own % via `COVERAGE_FILE=` env
   overrides, then `coverage combine` for the REAL merged total (not double-counted
   — the two stages run non-overlapping test files, confirmed by the Item 1 audit).
   `coverage html` is uploaded as a `coverage-html-<run>` artifact (download,
   unzip, open `index.html` — the browsable view, no hosted dashboard needed).
   Each stage plus the combine job also writes a ONE-LINE `$GITHUB_STEP_SUMMARY`
   pointer only, never the full report, per the confirmed Summary-tab mis-caching
   bug Gotcha.
   **Trend history: `tools/coverage_log.py`** (new, TDD, 6 tests, same isolated-
   table-in-`fleet_runs.db` convention as `diagnosis_log.py`/`vlm_canary.py` —
   `coverage_runs` table, `log_coverage_run()`, a `--db`-flag CLI). The
   `coverage-report` job's last step calls `python -m tools.coverage_log
   --stage1-pct ... --stage2-pct ... --combined-pct ... --commit-sha
   ${{ github.sha }} --ci-run-number ${{ github.run_number }}` — logged into the
   SAME self-hosted DB every other telemetry tool already reads/writes, not a new
   system. `dashboard/app.py` gained a 6th tab, **Coverage** — 3 metric tiles
   (latest stage1/stage2/combined %), a trend line chart (`load_coverage_history()`,
   guarded for the table not existing yet on a fresh/pre-feature DB — catches BOTH
   `sqlite3.OperationalError` and `pd.errors.DatabaseError`, since pandas wraps the
   former as the latter and that wrapping isn't guaranteed across pandas
   versions/connection types — found live, not assumed, see below), and a run-log
   table. **Verified live via Playwright both ways** (this file's own dashboard/
   CLAUDE.md precedent — zero automated pytest coverage for `app.py` by design):
   once against a throwaway DB copy seeded with fake trend rows (real chart, real
   metrics, no crash) and once against the REAL production DB, which doesn't have
   `coverage_runs` yet (empty-state info message, no crash) — this second pass is
   what caught the `sqlite3.OperationalError`-only guard being wrong; a naive
   `pd.read_sql` against a missing table actually raises `pd.errors.DatabaseError`,
   confirmed from a real traceback, not from memory of how `vlm_canary.py`'s
   different (`conn.execute`, not `pd.read_sql`) guard behaves.
   **Two real bugs found + fixed getting the pure-local `coverage-report` job
   itself to a genuine green run, both root-caused against real CI artifacts, not
   guessed:**
   1. **`actions/upload-artifact@v4`'s glob matcher silently skips dotfiles.**
      `mv .coverage .coverage.stage1` succeeded and `coverage report` printed a
      real 66% right before it, but the upload step logged `"No files were found
      with the provided path: .coverage.stage1. No artifacts will be uploaded"`
      and uploaded nothing (confirmed via the run's real artifact list — no
      `coverage-data-stage1`/`2` existed at all). Fixed by dropping the leading
      dot everywhere (`coverage.stage1`/`coverage.stage2`) — `coverage combine`
      takes explicit filenames as arguments, so the name never needed to match
      any convention.
   2. **Coverage data files record ABSOLUTE source paths — combining data
      collected on two different machines breaks reporting.** `stage-1-quality`
      runs on a GitHub-hosted `ubuntu-latest` runner (`/home/runner/work/...`);
      `stage-2-gazebo`/`coverage-report` run on the self-hosted runner (a
      different absolute checkout path). Once bug 1 was fixed and the artifacts
      actually downloaded, `coverage report`/`combine` failed with `"No source
      for code: /home/runner/work/autonomous-fleet-testbed/.../__init__.py"` —
      reproduced locally against the REAL downloaded artifacts (`gh run download
      <run> -n coverage-data-stageN`) before touching `.coveragerc` again, ruling
      out a coverage.py VERSION mismatch first (hosted runner's fresh `pip
      install` got 7.15.2, self-hosted `~/fleet-env` has 7.14.3 — tested
      cross-version combine directly, it worked fine, not the cause). Fixed with
      a `[paths]` section in `.coveragerc` (coverage.py's documented mechanism
      for exactly this multi-machine scenario) remapping either machine's
      absolute prefix back to the relative path — verified end-to-end against
      the real downloaded artifacts before re-pushing (STAGE1_PCT=66,
      STAGE2_PCT=31, COMBINED_PCT=82, `coverage html` succeeds).
   **Lesson for next time this bites:** when a CI step fails with no visible
   error text between two log lines, don't assume `set -e` swallowed something —
   download the run's REAL artifacts (`gh run download`) and reproduce locally
   with the actual data before touching config; both bugs here needed exactly
   that to root-cause instead of guessing from the step names alone.
   Below is prior-session context (still accurate — this pivot only changed HOW
   the numbers get combined/reported, not what was measured):
   `pytest-cov` is already a dependency — no external service needed to get a real
   number locally.  Numbers gathered so far:
   - Stage-1-only subset (pure Python, no ROS): **62%** (`tools/` + `src/nav_fleet/nav_fleet/`).
   - + `test_nav_runner.py` (mocked ROS, no Gazebo needed): **67%**.
   - Full suite (all 3 live-ROS files via real Gazebo) attempted twice — **both runs
     produced unreliable numbers, DO NOT trust either one.** Root causes found (see the
     two new dated Gotchas below): a real test-ordering fragility in
     `test_nav_runner.py`'s rclpy teardown, AND a live, concurrent `synthetic-fleet`
     Gazebo/Nav2 session sharing this exact machine's `/robot_001` DDS namespace at the
     time — found mid-investigation, session paused there rather than fight through it.
   - **Resume checklist:** (1) confirm no OTHER Gazebo/Nav2 session is running on this
     machine — `pgrep -fa "gz sim|robot_state_publisher"` and check the launching
     PROJECT PATH in the command line, not just process existence (`synthetic-fleet`
     vs `autonomous-fleet-testbed` look identical at the process-name level); (2)
     confirm no CI run is in-flight (`gh run list`) since a push auto-triggers CI on
     this same self-hosted machine; (3) launch fresh, wait for "Managed nodes are
     active"; (4) run the CI-safe-ORDER invocation from the test-ordering Gotcha below
     (NOT a naive `pytest tests/` — that reorders `test_nav_runner.py` before
     `test_navigation.py` and silently breaks the shared rclpy context).
   - **Decided with Mike (2026-08-01), later SUPERSEDED same day:** the original plan
     here was Codecov as a hosted reporting layer (trend history + PR diff-coverage),
     README badge deferred. **Reversed later the same session** — see the pure-local
     `coverage combine`/`coverage-report`-job/`tools/coverage_log.py`/dashboard design
     above, which is what's actually built. What DID survive the reversal unchanged:
     coverage collection spans BOTH stage-1 and stage-2 (non-overlapping test files —
     stage-2 doesn't re-run stage-1's own tests), NOT stage-4-hil (doesn't invoke
     pytest at all — runs `mission_runner.py --day` directly over SSH on the Jetson —
     would just re-measure the same lines stage-2 already covers via a different
     executor, not teach us anything new); and the `.coveragerc` omit list for the
     one-off manual CLI tools (`calibrate_ball_range.py`, `direct_drive_test.py`,
     `ghcr_prune.py`) so they don't drag the headline number down — they're
     hand-invoked hardware debug scripts, never meant to be unit-tested.
4. Release 1 → Release 2 planning (branching strategy, `r1-complete` tag).
5. ~~`RealRobotStartup.md` accuracy check~~ **Done 2026-08-01 evening** — full rewrite,
   see the NEXT SESSION block above for the summary.
6. GitHub CI pipeline docs (self-hosted runner setup writeup).

## Development workflow — tier 1 first

**Primary dev loop (x86 bare metal — use this to flush bugs before touching CI):**
```bash
colcon build --symlink-install          # ~1s — build the ROS2 package
source install/setup.bash
python -m pytest tests/ -v \
  --ignore=tests/test_ros2_contracts.py \
  --ignore=tests/test_navigation.py \
  --ignore=tests/test_mission_run.py \
  --ignore=tests/test_nav_runner.py    # seconds — run Python unit tests
ros2 launch nav_fleet sim_launch.py    # Session 09+ — Gazebo + Nav2 locally
# nav_runner, metrics_collector, drift check all run here
```

x86 is not the robot's target OS but finds 90% of bugs at ~1s build vs 23 min QEMU.
Commit to CI only when the x86 pipeline is clean.

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
  --ignore=tests/test_nav_runner.py

# Run a mission (repo root; sim must be up — see launch commands above)
python -m nav_fleet.mission_runner mission1

# Traceability gate
python tools/check_traceability.py requirements/traceability.yaml tests/ \
  --profile robot_profiles/jetson_ugv_pt.yaml

# Code coverage — stage-1 (unit) subset, safe to run anytime, no Gazebo needed.
# .coveragerc (repo root) scopes to tools/ + src/nav_fleet/nav_fleet/, omits the 3
# hand-invoked hardware debug scripts. CI mirrors this exact invocation for its own
# stage-1 number; the real combined stage-1+stage-2 total (via `coverage combine`,
# pure-local, no third-party site) only exists in CI's coverage-report job — not
# locally runnable in one shot (stage-2's half needs live Gazebo — see the
# shared-machine gotcha before running that locally).
python -m pytest tests/ --ignore=tests/test_ros2_contracts.py \
  --ignore=tests/test_navigation.py --ignore=tests/test_mission_run.py \
  --ignore=tests/test_nav_runner.py -k "not integration" \
  --cov=tools --cov=src/nav_fleet/nav_fleet --cov-report=term-missing
# Browsable HTML instead of the terminal table:
coverage html && xdg-open htmlcov/index.html
# Combined stage-1+stage-2 trend + browsable HTML report:
# - trend/latest numbers: streamlit dashboard, Coverage tab (below)
# - full browsable report: download the coverage-html-<run> artifact from any CI
#   run's coverage-report job, unzip, open index.html

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
- `RealRobotStartup.md` — the real-robot bring-up runbook. Part A = one-time setup
  (driver bring-up, SLAM map, `robot_launch.py`); Part B = the repeatable day-to-day
  loop, including the physical Jetson swap required to get back into HIL mode
  (confirmed single-Jetson deployment, no dedicated CI runner).
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
  (interactive) are unaffected and work fine as-is. Two related env-var switches added
  2026-07-28 in `tools/agentic_loop.py`: `AGENTIC_BACKEND` (default `'claude'`; set to
  `'ollama'` to use a local model instead) and `OLLAMA_MODEL` (default
  `'qwen2.5:14b-instruct'`, only consulted when the Ollama backend is selected).
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
  integration test in `stage-2-gazebo`. (File itself removed 2026-08-01 as redundant
  with `tools/mission2_day.py`'s in-process run — left here as historical context for
  the `--ignore`-treatment lesson, which still applies to any new rclpy-importing file.)
- **CI stage-0's traceability gate has `continue-on-error: true` — this is a live, ongoing gap,
  not stale.** Session 10 added `test_navigation.py`, but 2 of its 3 test function names never
  matched `requirements/traceability.yaml`'s placeholder names (fixed in Session 11/12: BR-01/
  BR-10 → `test_navigation_succeeds`, BR-02 → `test_no_collision`). BR-03 (recovery behavior)
  has no test at all — recovery is genuinely broken, so this isn't a naming fix, it's a
  real missing capability.
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
  This is tracked as confirmed-but-not-root-caused — do not mark it done until an
  actual fix (not just a diagnosis) lands.
  **UPDATE 2026-07-24: likely explained, under a different
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
  with the observation.** The costliest mistake in this investigation
  (2026-07-24): an intra-goal delay (`goal accepted` → `goal result received`, ~18-29s,
  confirmed identical on x86 and Jetson) was conflated with the inter-scenario gap Mike
  was actually describing (`goal result received` → next scenario's dispatch) — which
  turned out to be ~40x different between platforms (~0.4s x86 vs. ~17.6s Jetson) and
  fully explained his repeated, correct, "watching the whole time" observation. Don't
  minimize a repeated, specific live observation as "which moment you happened to be
  watching" — re-measure the SPECIFIC boundary being described first.
- **GitHub Actions' own Summary tab has a confirmed platform-side bug — it mis-caches/
  mis-maps job-summary content client-side, unrelated to anything in `ci.yml`. Not
  fixable from this repo; stop re-investigating it as if it were our bug.** Confirmed
  twice, independently (2026-07-23 and again 2026-07-25, same signature both times):
  `stage-1-quality`'s own Summary panel displayed `stage-5`'s drift-report content
  (`hil_jetson: FAIL`, a large σ-drift banner) verbatim — even though `stage-1-quality`'s
  job spec (checkout → ROS2 apt install → ament lint install → flake8 → pytest) writes
  to `$GITHUB_STEP_SUMMARY` **zero times**, re-verified line-by-line against `ci.yml`
  both times. The 2026-07-25 recurrence went further: the displayed content didn't match
  that run's own console log OR its own downloadable PDF artifact either — genuinely
  stale/cached data from an unrelated run, not just a rendering-order mix-up. The Checks
  API confirms `output.summary` is `null` for every job; `$GITHUB_STEP_SUMMARY` has no
  public REST/GraphQL surface at all — the browser's Summary tab (a JS-rendered SPA) is
  the only place this data exists, which is exactly why no automated check can catch it.
  **Workaround in place, not a fix for the underlying bug:** `stage-5-reports-sim`/`-hw`
  moved their real "Fleet status" content off `$GITHUB_STEP_SUMMARY` into plain
  console-log output (`ci.yml`, the `Fleet status` steps) so the actually-meaningful
  content lives somewhere trustworthy even though the Summary tab can't be. This does
  NOT generalize to "never touch `$GITHUB_STEP_SUMMARY`" — every stage still writes a
  short one-line timing/link summary (`Stage N ... wall time`, `Download the PDF
  report`) with no reported problem; only large report-content blocks have been
  observed getting mis-cached. `stage-1-quality` still carries a diagnostic canary step
  (`"Canary summary line"`, `echo "### Message from Mike" >> $GITHUB_STEP_SUMMARY`,
  added 2026-07-25 specifically to probe this bug in its own panel) — its own comment
  says to remove it once confirmed live, which already happened; left in place
  deliberately (2026-08-01, Mike's call) rather than removed, so don't treat that
  comment as a live TODO.
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
- **A Claude Code `SessionStart` hook's plain stdout reaches ONLY Claude's own context,
  never the human user's terminal — confirmed against the official docs 2026-07-29,
  after Mike reported the dashboard-reminder hook (added 2026-07-28, `.claude/
  settings.json`) "isn't working."** It wasn't a flake: Claude Code's docs state
  plainly that for `SessionStart` (and `UserPromptSubmit`/`UserPromptExpansion`),
  stdout is "added as context that Claude can see and act on" — nothing about the
  user seeing it. The hook was genuinely running (Claude's own system-reminder showed
  `SessionStart:startup hook success: ...` every session), which is exactly why this
  was easy to wrongly call "already working" from inside a session — the assistant
  DOES see it fire, the human never does. To make a `SessionStart` hook's output
  user-visible, its stdout must be JSON with a `systemMessage` field (shown to the
  user) — `hookSpecificOutput.additionalContext` is the separate field for Claude-only
  context; plain unstructured stdout is Claude-only for this event, full stop. Fixed
  by moving the hook's logic into `.claude/hooks/session_start_status.sh`, which emits
  `{"systemMessage": ..., "hookSpecificOutput": {"additionalContext": ...}}` via `jq`
  instead of plain `echo`; `.claude/settings.json` now invokes that script via
  `${CLAUDE_PROJECT_DIR}` (the documented placeholder for referencing hook scripts
  regardless of working directory) rather than inlining two bare `echo`/`python -m`
  commands. **Lesson for any future hook meant to inform the human specifically:**
  "the assistant received it in a system-reminder" is NOT evidence the user saw
  anything — verify hook user-visibility by checking for `systemMessage` in its JSON
  output, not by trusting that a hook "fired successfully."
- **CUDA/Ollama installed on the Jetson, 2026-07-30 (VLM red-ball canary).** Installed
  manually by Mike, per plan: `nvidia-jetpack 7.2-b187` (`sudo apt install
  nvidia-jetpack` — no reflash, L4T apt sources already present from the original
  OS-only flash), CUDA Toolkit `13.2.1-1` (`nvcc` — real version confirmed:
  `Cuda compilation tools, release 13.2, V13.2.78`), Ollama `0.32.5` on the Jetson
  (workstation is `0.32.0` — versions don't need to match). Model pinned:
  `moondream:1.8b`.
  **Gotcha 1 — `nvcc` isn't on `PATH` after `nvidia-jetpack` installs**, even though
  the toolkit itself installed correctly (`dpkg -l | grep cuda-toolkit` shows it real).
  Fix: `echo 'export PATH=/usr/local/cuda/bin:$PATH' >> ~/.bashrc`.
  **Gotcha 2 — Ollama's install script warns `"Unsupported JetPack version detected.
  GPU may not be supported"` on JetPack 7.2 — this is a false alarm, not a real
  problem.** JetPack 7.2 is NEWER than what `install.sh`'s version-detection list
  currently recognizes (native support tops out at JetPack 6.2), so the script's
  warning is a version-list gap, not evidence of a broken GPU path. Confirmed via
  `journalctl -u ollama`: Ollama's runner correctly skips one bundled CUDA library
  variant (`cuda_v12`, which lacks compiled support for Orin's compute capability
  8.7) and falls back to a working one (`cuda_v13`) — the real proof is
  `load_tensors: offloaded 25/25 layers to GPU` and `clip_ctx: CLIP using CUDA0
  backend` in the log, both present and correct. Don't trust the install-time warning
  text either way — check `journalctl -u ollama | grep -iE "cuda|gpu|offload"` for
  the real answer.
  **Gotcha 3 — the FIRST inference call after a fresh Ollama server start is
  dramatically slower than every call after it** (~45s vs ~4s, measured live,
  `moondream:1.8b` on this exact board) — one-time CUDA kernel JIT compilation for
  Orin's specific compute capability (not precompiled in the bundled library) plus
  cold model load, not a sustained performance problem. This is why the design spec
  calls for pre-warming (one throwaway inference call) before any timing-sensitive
  use — see that spec's "Model choice + pre-warming" section.
  **Gotcha 4 — the Ollama *server* install (`curl -fsSL https://ollama.com/install.sh
  | sh`) does NOT install the `ollama` Python client package** — that's a separate,
  additional `pip3 install ollama` (or `pip3 install --break-system-packages ollama`
  on this Ubuntu/JetPack userland, which enforces PEP 668's
  externally-managed-environment restriction) needed on the Jetson's bare-metal
  system Python for any bare-metal script/tool that does `import ollama` directly
  (confirmed live: `ModuleNotFoundError: No module named 'ollama'` until this was
  done). **Container-mode HIL does NOT need this extra step** — `requirements-ci.txt`
  already pins `ollama>=0.4` (added earlier for `tools/agentic_loop.py`'s Ollama
  backend), so the arm64 Docker image already has it baked in.
- **Connecting a second network interface (WiFi) on the Jetson broke HIL's cross-machine
  ROS2 discovery entirely — root-caused 2026-07-30, same session as the CUDA/Ollama install
  above, but a separate, unrelated bug.** After enabling the Jetson's WiFi (`wlP1p1s0`,
  connected to a real home network for testing before the robot's arrival), `scripts/
  hil_stage.sh run` started reliably failing: Nav2 came up fine locally on the Jetson
  (`map_server`/`amcl` activated, bonded, "Managed nodes are active" all logged normally),
  but was **completely invisible from the workstation** (`ros2 node list` showed zero
  Jetson-side nodes) and vice versa (the Jetson received zero data on topics the workstation
  publishes — confirmed with `ros2 topic hz /robot_001/scan` timing out with no output at
  all). `local_costmap` looped forever on "Timed out waiting for transform from
  base_footprint to map". Survived a full soft reboot AND a hard power cycle identically —
  ruled out as a transient/stale-process issue. Root cause, found via `ip maddr show` (no
  `tcpdump` needed): CycloneDDS's default interface auto-selection picks the first viable
  multicast-capable interface by **ifindex**, not necessarily the one that actually reaches
  the other machine. On the Jetson, WiFi's ifindex (2) is lower than Ethernet's (5) — likely
  because the WiFi driver probes before the Ethernet controller at boot — so CycloneDDS
  joined its discovery multicast group (`239.255.0.1`) on `wlP1p1s0` instead of `enP8p1s0`,
  the only interface that actually reaches the workstation. (The workstation's own Ethernet
  happens to have the lower ifindex there, so it was never affected — pure luck, not a
  difference in configuration.) This is exactly why WiFi hadn't broken anything before this
  session: it was never up long enough to matter until today. **Fix:** `~/cyclonedds-hil.xml`
  on the Jetson lists BOTH interfaces explicitly with an assigned `priority` (higher wins,
  per CycloneDDS's own docs — default is 0 for a regular interface, 2 for loopback):
  `enP8p1s0` at `priority="10"`, `wlP1p1s0` at `priority="1"`. Ethernet stays preferred
  whenever it's up; WiFi remains genuinely available as a fallback if Ethernet is ever
  disconnected (the untethered-robot scenario this WiFi bring-up exists for in the first
  place) — a narrower first version of this fix pinned Ethernet ONLY, which would have
  silently broken untethered operation the same way the original bug broke tethered
  operation; corrected same day after Mike caught it. `scripts/hil_stage.sh`'s `JENV` now
  exports `CYCLONEDDS_URI=file://$HOME/cyclonedds-hil.xml` for every Jetson-side launch, so
  this is immune to future interface/ifindex changes (a new USB-Ethernet dongle, a different
  WiFi card, etc.) regardless of enumeration order. **Diagnostic lesson:** `ros2 topic hz` on a
  topic the SAME machine also locally publishes (e.g. via its own Gazebo bridge) proves
  nothing about cross-machine delivery — check the topic from the OTHER machine's side, or
  check a topic/node that can only exist on the remote side, to actually test the link.
- **`ssh mike@jetson.local` stopped resolving the same day as the WiFi bring-up above — a
  separate bug from the CycloneDDS one, root-caused 2026-07-30.** `avahi-daemon` on the
  Jetson logged `Host name conflict, retrying with jetson-3` at boot and started
  advertising as `jetson-3.local` instead of `jetson.local` — confirmed via `journalctl -u
  avahi-daemon`, not a workstation-side or firewall issue (ruled out: workstation's own
  `avahi-browse -a -t` showed real mDNS traffic from other devices on WiFi, `ip maddr show`
  confirmed `224.0.0.251` correctly joined on the Ethernet interface both sides, and
  `239.255.0.1` — a DIFFERENT multicast group, CycloneDDS's own — was independently proven
  working on that exact same Ethernet link at that exact same time, ruling out "multicast is
  blocked on this interface" as a category). **Root cause: a boot-time race, specific to
  having Ethernet AND WiFi both come up together at avahi's own startup** — the log showed
  IPv6 privacy/temporary addresses on `wlP1p1s0` churning (registering, withdrawing,
  re-registering within the same second) exactly while avahi was probing for name
  uniqueness, triggering a spurious self-conflict. Confirmed by elimination: restarting
  avahi-daemon *after* boot (interfaces already settled) always claimed `jetson.local`
  cleanly with zero conflict, every time. **Fix:** `use-ipv6=no` in
  `/etc/avahi/avahi-daemon.conf`'s `[server]` section on the Jetson — this project doesn't
  use IPv6 anywhere (SSH, ROS2/DDS are all IPv4), so removing it removes the churn that
  triggered the boot race. Verified with a full reboot (not just a service restart): clean
  `jetson.local` claim with zero conflict, both interfaces up together at boot, confirmed
  both by the journal log (no `Joining mDNS multicast group on interface *.IPv6` lines at
  all this time, vs. explicit IPv6 joins before the fix) and by a live `ping`/`ssh
  mike@jetson.local` against the fresh boot. Not committed to git — this is a Jetson
  OS-level config file, outside the repo; re-provisioning this exact board (or a
  replacement) needs this step redone manually.
  **UPDATE 2026-07-30 (same day, next power cycle): recurred with a THIRD, different
  trigger — the `use-ipv6=no` fix above is confirmed still holding (zero IPv6 multicast
  joins), so this is additive, not a regression of that fix.** After a full workstation +
  Jetson power-down/power-up, `ssh mike@jetson.local` failed again
  (`jetson-2.local` this time). `journalctl -b` (whole system, not just the avahi unit)
  pinpointed the trigger to the exact millisecond: `systemd-timesyncd[465]: Initial clock
  synchronization to Thu 2026-07-30 15:33:14...` fires in the SAME event-loop tick as
  avahi's withdraw-everything/re-register-everything burst that produces `Host name
  conflict, retrying with jetson-2` — this Jetson has no trustworthy RTC, boots showing a
  bogus date (`Dec 31`), and only gets its first real NTP fix once WiFi associates
  (Ethernet's DHCP hadn't even completed yet at the moment of conflict, ruling out
  "Ethernet coming up" as this trigger, unlike what the previous entry's framing might
  suggest for a similar-looking symptom). The abrupt `CLOCK_REALTIME` step while avahi is
  mid-probe corrupts its own timing/scheduling and it loses a race against its own
  in-flight re-announcement. **Fix: stop avahi from starting until the clock is already
  synced, rather than reacting after the fact** — `sudo systemctl enable
  systemd-time-wait-sync.service` (ships with systemd, disabled by default) plus a
  drop-in override at `/etc/systemd/system/avahi-daemon.service.d/override.conf`
  (`[Unit]` / `After=systemd-time-wait-sync.service` / `Wants=systemd-time-wait-sync.service`)
  so `avahi-daemon.service` waits on it. Verified with **three consecutive full reboots**
  (this project's bar for an intermittent-fix, `feedback_proof_bar_sizing`): zero
  `Host name conflict` lines in any of the three, `ssh mike@jetson.local` resolved
  immediately every time with no manual restart, CycloneDDS's `~/cyclonedds-hil.xml`
  confirmed byte-identical throughout (this fix touches only avahi/systemd, not DDS
  interface selection). Also not committed to git, same reason as above — two systemd
  changes to redo on any re-provision: `systemctl enable systemd-time-wait-sync.service`
  and the avahi-daemon.service.d override file. **Lesson: when the same user-visible
  symptom recurs after a fix already verified by a full reboot, don't assume the old fix
  regressed — pull the FULL system journal (not just the one unit) around the exact
  failure timestamp first. Two unrelated root causes can produce byte-identical log
  output (`Host name conflict, retrying with jetson-N`).**
- **`nvpmodel -m <id>` started demanding an interactive reboot confirmation on
  2026-07-30, breaking `scripts/hil_stage.sh power-mode` (and therefore every
  stage-4-hil CI run) even when setting the Jetson to the mode it was ALREADY in** —
  `NVPM WARN: Golden image context is already created` / `Reboot required for
  changing to this power mode: 1` / `DO YOU WANT TO REBOOT NOW?`, which a
  non-interactive SSH/CI invocation answers with EOF, producing `NVPM ERROR: bad
  input!` and a nonzero exit — `hil_stage.sh`'s `set -euo pipefail` (and CI's lack of
  `|| true` on this specific step) then aborts the whole job before sync/build/mission
  ever run, which is why a "failed HIL run" can show almost NO mission logs at all —
  check `gh api .../jobs/<id> -q '.steps[]'` for per-step conclusions before assuming
  the mission itself ran. **Two things ruled out before finding the real fix:** (1) a
  leftover `jetson_clocks` diagnostic (forced CPU clocks to hardware max, MinFreq=
  MaxFreq=1728000, never restored) was a real, separate, self-inflicted issue — found
  via `jetson_clocks --show` still showing the stuck state — but a clean `sudo
  reboot` fixed THAT specific problem while the nvpmodel prompt persisted unchanged,
  proving it wasn't the (sole) cause; (2) `ollama.service` actively holding a live
  GPU/CUDA context was a plausible read of "Golden image context" — ruled out by
  `sudo systemctl stop ollama` then retrying `nvpmodel -m 1`, which showed the
  identical prompt with Ollama fully stopped. **Real fix: nvpmodel tracks its own
  internal "confirmed reboot pending" state, separate from live hardware clocks —
  a GENERIC `sudo reboot` does NOT clear it; only letting nvpmodel drive its OWN
  confirm-and-reboot cycle does.** Fixed by piping the confirmation directly: `echo
  yes | ssh ... "sudo -n nvpmodel -m 1"` — nvpmodel printed `NVPM WARN: rebooting..`
  and rebooted itself; after that reboot, `nvpmodel -m 1` returned cleanly (`rc=0`,
  no output) twice in a row, non-interactively, matching the behavior every prior
  session had relied on. Exact trigger not fully certain — most likely the JetPack/
  CUDA install earlier the same day (`nvidia-jetpack 7.2-b187`) initialized the GPU
  driver on this board for the first time ever and set this pending-reboot flag as a
  one-time side effect, needing exactly one nvpmodel-confirmed reboot to clear (apt
  history shows the install itself never touched `nvidia-l4t-nvpmodel`, the package
  that actually owns `/usr/sbin/nvpmodel`, ruling out a package-version change as the
  direct cause). **If this recurs, the fix is the same one-line `echo yes | ssh ...
  nvpmodel -m <id>` — don't reach for a plain reboot or restart-a-service guess
  first**, both were tried and ruled out this time.
- **This repo went public 2026-07-31 — it uses two SELF-HOSTED runners (the workstation
  + the Jetson), which is a real, well-known GitHub Actions risk category for a public
  repo: a fork PR can trigger a workflow run that executes on physical hardware.**
  Confirmed and hardened the same day. Facts, not guesses: `ci.yml` has no
  `workflow_dispatch` trigger (no one, including the owner, can manually trigger a run
  from the web UI); `sdfinn` is the sole collaborator (confirmed via API — direct push
  to `main` is impossible for anyone else); `ci.yml` uses `pull_request`, not the
  riskier `pull_request_target`, so GitHub automatically withholds repository secrets
  from any fork-PR-triggered run regardless of settings; `default_workflow_permissions`
  is `read` (confirmed via `gh api repos/.../actions/permissions/workflow`), so even the
  automatic `GITHUB_TOKEN` can't push/write. The one real, findable, worth-doing setting
  is Settings → Actions → General → "Fork pull request workflows from outside
  collaborators" → **set to "require approval for all outside collaborators"** (done
  2026-07-31) — every fork PR now needs an explicit manual click before anything runs,
  no exception for repeat contributors. Self-hosted runner network exposure itself was
  never a real concern regardless of ISP/CGNAT — these runners are outbound-only by
  design (they long-poll GitHub for work; GitHub never connects inbound), so the actual
  risk category is "approved code executes on my hardware," not "my machine is
  reachable from the internet." **A specific pair of checkboxes was initially described
  as also worth checking ("Send write tokens"/"Send secrets to workflows from fork pull
  requests") — Mike couldn't find them on this personal-account repo, most likely an
  org-only setting or a misremembered UI detail from a general-knowledge recall, not
  verified against the live page before being stated.** Don't re-describe specific UI
  element names/locations as fact without a way to verify them live (API check, or the
  user's own screen) — the two structural facts above (secrets withheld from
  `pull_request` fork runs; read-only `GITHUB_TOKEN`) already cover what those
  checkboxes would have, so there's nothing to keep hunting for.
- **HIL hardening session, 2026-07-31 — full arc, ending in the first fully-green
  end-to-end CI run of the project (run 30657248798).** Six real, distinct problems
  found and fixed in sequence; each looked plausible as "the" fix at the time and each
  turned out to be real but incomplete on its own:
  1. **25W always, no more `nvpmodel -m` calls in CI at all (Mike's decision).** HIL is
     wall-powered and the real robot's own short (<30min) field experiments also stay
     at 25W, so the old 15W-during-mission/25W-during-build switch bought nothing real
     — and that exact switch is what was tripping nvpmodel's stuck reboot-confirmation
     bug (see the 2026-07-30 entry above) on *every* HIL run, not a rare one-off as
     first assumed. Fix wasn't "pick a different number" — an initial pass still kept
     an explicit `nvpmodel -m 1` "safety net" step and it STILL tripped the bug (the
     mode requested doesn't have to differ from the current one for the bug to fire).
     Real fix: stop calling `nvpmodel -m` anywhere in the automated CI path at all.
     `nvpmodel -q` (read-only, no reboot risk) stays for telemetry's power-mode label.
  2. **CycloneDDS interface list hard-fails on ANY down interface, doesn't skip to the
     next-priority one.** The 2026-07-30 fix below (list both interfaces, Ethernet
     priority 10, WiFi priority 1) assumed CycloneDDS would silently prefer whichever
     listed interface was actually up. Confirmed false, live: with Ethernet physically
     unplugged, Nav2 hard-failed on the Jetson with `enP8p1s0: does not match an
     available interface` / `rmw_create_node: failed to create domain` — every ROS2
     node on the Jetson died at startup, never got to try wlP1p1s0 at all. This exact
     "Ethernet unplugged, real CycloneDDS traffic" scenario had never actually been
     exercised before — the 2026-07-30 WiFi work only verified SSH/mDNS, a different
     subsystem entirely, unrelated to CycloneDDS's own interface binding.
  3. **`scripts/regen_cyclonedds_config.sh` (new)** — regenerates the interface config
     from REAL current link state (`/sys/class/net/<iface>/operstate` — NOT `ip
     link`'s administrative UP flag, which stays "UP" with no cable plugged in, the
     root cause of #2) immediately before every launch, on the Jetson
     (`hil_stage.sh`'s `nav2_up()`, over SSH) — never lists a down interface, so it's
     correct however the Jetson happens to be connected at boot, no manual step ever
     needed. Verified live via a direct manual test (bare `ros2 launch
     nav2_only_launch.py` with the interface removed from the file by hand): fixed
     immediately, all nodes came up clean.
  4. **Same failure CLASS, different machine: the workstation's `sim_up()` had NO
     CycloneDDS config at all**, relying on CycloneDDS's own default auto-selection —
     which picked `docker0` (a virtual Docker bridge on an unrelated 172.17.0.0/16
     subnet) over the real WiFi interface. Confirmed via `/sys/class/net/<iface>/
     device` — the standard way to tell a real NIC from a virtual bridge/veth/loopback
     apart on Linux (docker0/veth* have no `device` symlink; enp6s0/wlp5s0 do). Result:
     the workstation's own Gazebo/bridge topics never reached the Jetson at all, even
     though both machines could ping each other fine (SSH/ping are unicast; CycloneDDS
     discovery is multicast — a fully separate question). `regen_cyclonedds_config.sh`
     was generalized (not duplicated per-machine) to auto-detect physical-vs-virtual
     interfaces via the `/device` check and prioritize by the standard `en*`/`eth*`
     (Ethernet) vs `wl*` (WiFi) naming convention, so ONE script runs unmodified on
     both machines despite their real interface names differing
     (enP8p1s0/wlP1p1s0 vs enp6s0/wlp5s0). Wired into `sim_up()` the same way.
     Verified live on the workstation itself (real `hil_stage.sh run` invocation,
     `JETSON_IP` deliberately unset so `nav2_up()` cleanly stopped at its own
     `require_ip` check before ever touching the Jetson) — regenerated correctly,
     `docker0` excluded, Gazebo + bridge came up clean.
  5. **Even with #3 and #4 both fixed, cross-machine DDS discovery over WiFi ALONE
     still didn't work** — `local_costmap` kept timing out waiting for the `map`
     transform, live, in CI, with both machines confirmed correctly bound to their
     real WiFi interfaces (no wrong-interface, no docker0). Leading theory, NOT
     confirmed further: the WiFi router (AT&T-provided) has AP/client isolation
     enabled, or filters multicast between wireless clients (common consumer/ISP-
     router behavior) — would exactly explain why unicast (SSH, ping) worked fine all
     session but CycloneDDS's multicast-based discovery never crossed the AP.
     **Deliberately not investigated further** — see the insight below for why, and
     `scripts/hil_stage.sh`'s own top-of-file comment for the pointer.
  6. **`scripts/**` was missing from `ci.yml`'s `dorny/paths-filter`** — a
     `hil_stage.sh`-only push silently skipped the ENTIRE arm64+HIL chain (a run came
     back green only because everything that ran passed, not because stage-4-hil did
     — it never ran at all). `hil_stage.sh` drives HIL's entire SSH orchestration, so
     a change to it should never be able to skip validation this way. Fixed by adding
     `scripts/**` to the filter's watched paths.
  **Key insight (Mike): the real, deployed robot does not need WiFi/Ethernet for its
  core operation at all.** HIL is a two-machine system *by design* — Gazebo (the
  simulated world) runs on the workstation while Nav2/mission_runner run on the real
  Jetson, specifically so real onboard software can be tested against a simulated
  world it can't tell apart from reality. That split is the ENTIRE reason any of #2-#5
  above exist. The deployed robot has none of it: Nav2, mission_runner, ball_detector,
  ekf_node, and the VLM canary's Ollama call all run on the same Jetson; even the
  Docker container path (`HIL_CONTAINER=1`) uses `--network host`, so container-to-
  host traffic (e.g. reaching Ollama) goes over `localhost` regardless of whether
  WiFi/Ethernet exists at all. Given that, there's no R1 payoff to chasing #5 further
  — Ethernet was reconnected for HIL instead (2026-07-31), which is what actually
  produced the first fully-green run. A dedicated WiFi router/AP Mike controls (not
  the AT&T gateway) is the right fix if/when it's actually needed — deferred until
  either a second/slave robot arrives (R2/R3 multi-robot coordination will need real
  wireless) or R1 debugging over Ethernet-tethered HIL gets cumbersome enough to
  justify it sooner. Bluetooth was considered and ruled out for this purpose — wrong
  transport for ROS2/DDS (no standard transport, assumes IP networking + bandwidth for
  topics like `/scan`/camera streams).
- **On-device VLM canary, 2026-07-31 — the canary was silently classifying
  workstation-side even for stage-4-hil, missing the entire point of "on-device."**
  `_maybe_spawn_vlm_canary()` (`tools/mission2_day.py`) is called from the shared,
  workstation-side `run_day()` function regardless of executor — so even in HIL mode,
  classification happened on the WORKSTATION's own Ollama/GPU, using the ALREADY-
  pulled-back local photo copy, never touching the Jetson's own CUDA/Ollama install
  (the one specifically installed for this purpose, 2026-07-30). Found when Mike
  pointed out HIL is "primarily where we want it, the main reason for implementing
  now." Fixed: `JetsonExecutor` now spawns BOTH the warm-up and the real
  classification directly on the Jetson over SSH (fire-and-forget, detached,
  `_spawn_vlm_canary_on_jetson`/`spawn_vlm_warmup`), using `_remote_photo_path`'s
  existing bare-metal/container path translation, BEFORE `_pull_photos_from_paths`
  overwrites the leg's photo list with workstation-local copies. A new
  `MissionExecutor.spawns_own_vlm_canary` flag stops the workstation-side spawn from
  ALSO firing for a Jetson-executed leg (the same red photo would otherwise get
  classified twice, by two different machines). Stage-2 (sim, no real Jetson) is
  unaffected — workstation-side classification is the only sensible option there.
  **The result has to get back to the WORKSTATION's real `fleet_runs.db`** (the
  Jetson's own local sqlite write is invisible to every report/dashboard tool, which
  all read the workstation's copy) — `tools/vlm_canary.py`'s `main()` now also writes
  a small `vlm_canary_last_result.json` snapshot (overwritten each call — at most one
  red reaction per day, so "last" is unambiguous) alongside the sqlite DB; a new
  `python -m tools.mission2_day --ingest-vlm-canary` CI step (placed as LATE as
  possible in `stage-4-hil`, after the Nav2-log fetch, to give the fire-and-forget
  background call maximum wall-clock time) pulls that file back and logs it into the
  workstation's real DB — deliberately re-resolving `photo_path` to the ALREADY-
  pulled-back workstation-local equivalent rather than trusting the Jetson's own
  (meaningless-on-the-workstation) path, so it joins correctly against
  `generate_test_report.py`'s `photos` column (next entry). **Verified end-to-end,
  live, in the first fully-green run**: `vlm_canary_log` row created at the same
  wall-clock second as the HIL mission's own `PASS` telemetry row, `photo_path`
  pointing at the real pulled-HIL-photo (distinct timestamp from the sim run's own
  canary photo), ingest step logging the real filename rather than "no result file to
  ingest yet" (which is what every earlier, blocked attempt logged).
- **Photo/VLM-canary cross-contamination in PDF reports, found + fixed 2026-07-31 —
  likely present in every HIL report since Piece 9 (2026-07-24), not just today's sim
  addition.** `generate_test_report.py`'s `find_run_photos()` matches by a ±180s time
  window around a row's own timestamp — but mission2's 3 legs get telemetry-logged
  within the same wall-clock second (one tight judging loop, no meaningful delay), so
  EVERY leg's PDF section showed every OTHER leg's photos and VLM canary text too.
  Confirmed directly: the exact same canary answer (belonging only to the red leg)
  appeared duplicated under `no_ball` and `yellow`'s sections in a real generated PDF.
  Fixed with a new `photos` telemetry column (JSON-encoded, this row's own exact
  list, populated by `_judge_and_log_leg`/`log_variant_row`) that
  `generate_test_report.py`'s new `_row_photos()` helper prefers over the time-window
  guess, falling back to it only for scenarios that don't populate it yet
  (bedroom_nav/mission1 — unaffected, no reported bug there). Regression-tested
  directly: two rows sharing an identical timestamp but distinct `photos` columns now
  correctly produce distinct PDF sections.
- **`ingest_vlm_canary_from_jetson()` was joining the wrong photo directory — every HIL
  PDF report has shown zero VLM canary text since the feature shipped 2026-07-31, found
  + fixed 2026-08-01.** `_pull_photos_from_paths()` writes each leg's `photos`
  telemetry column using `PHOTO_DIR`-based paths (`~/fleet-ci-data/photos/...`), but
  `ingest_vlm_canary_from_jetson()` globbed `state_dir` (e.g. `/tmp/hil_stage/...`)
  for the local reaction-red photo instead — a real copy of the same file exists in
  BOTH directories (state_dir gets a `cp -f`'d duplicate), same basename, different
  absolute path, so `find_vlm_canary_results()`'s exact-string `WHERE photo_path IN
  (...)` join silently matched nothing. Confirmed directly against the real
  `fleet_runs.db` (run 690): `photos` column pointed at PHOTO_DIR, `vlm_canary_log.
  photo_path` pointed at state_dir. The sim report never had this bug (sim never goes
  through this Jetson-specific ingest path), which is exactly why only the HIL PDF was
  affected. Fixed: glob `PHOTO_DIR` instead — TDD, `tests/test_mission2_day.py`'s
  `test_ingest_vlm_canary_from_jetson_logs_result_with_photo_dir_path` (replaces the
  old test, which had enshrined the WRONG assumption) confirmed RED against the old
  code, GREEN after.
- **`test_nav_runner.py`'s rclpy teardown will silently break `test_navigation.py`/
  `test_mission_run.py` if pytest's file collection order ever changes — found
  2026-08-01 running a naive `pytest tests/` for a coverage check.** `conftest.py`'s
  `ros_context` fixture (session-scoped) is deliberately shared ONLY between
  `test_navigation.py` and `test_mission_run.py` — its own docstring says so. But
  `test_nav_runner.py` has a SEPARATE, independent module-scoped `_ros` fixture that
  calls `rclpy.try_shutdown()` unconditionally on teardown — if `test_nav_runner.py`
  happens to run BEFORE the other two finish (which is exactly what plain alphabetical
  pytest discovery does: `test_nav_runner.py` < `test_navigation.py`), its teardown
  kills the shared rclpy context out from under them, and every subsequent
  `test_navigation.py`/`test_mission_run.py` test ERRORs with
  `rclpy.exceptions.NotInitializedException`. **CI never hits this** — `ci.yml`'s
  `Run navigation + mission integration tests` step explicitly orders the 3 files
  (`test_navigation.py test_mission_run.py test_nav_runner.py`, nav_runner LAST) —
  but ANY local ad-hoc `pytest tests/ ...` invocation that lets pytest auto-discover
  will silently hit this. **Not fixed** (a real fix would make `test_nav_runner.py`'s
  `_ros` fixture check whether it OWNS the context before shutting it down, mirroring
  `ros_context`'s own care) — flagged, not yet a priority; the safe workaround for now
  is to always pass the 3 live-ROS files explicitly in CI's order:
  `pytest tests/test_navigation.py tests/test_mission_run.py tests/test_nav_runner.py
  tests/ --ignore=tests/test_ros2_contracts.py --ignore=tests/test_navigation.py
  --ignore=tests/test_mission_run.py --ignore=tests/test_nav_runner.py ...`. **Caution
  found the same session, still being separated out:** a second, independent full-suite
  attempt using exactly that safe-order command still came back with wildly wrong
  numbers (~15% total, only 29 tests collected) — root cause NOT this ordering bug (a
  different symptom entirely) — see the next entry; don't assume this ordering fix
  alone is sufficient before re-verifying against a genuinely idle machine.
- **This workstation is BOTH `autonomous-fleet-testbed`'s self-hosted CI runner AND a
  general dev machine that can have OTHER projects' full Gazebo/Nav2 stacks running at
  the same time — found 2026-08-01, mid-coverage-investigation, twice in one session.**
  Two distinct instances of the same hazard class:
  1. **A `git push` to `main` auto-triggers a real CI run on THIS machine.** Pushed two
     commits, then immediately launched a local Gazebo session for a coverage check —
     CI's own `stage-2-gazebo` job started concurrently, and its "Sweep stale sim
     processes" step (`pkill -9 -f "parameter_bridge|component_container_isolated|
     ekf_node|ball_detector"`, etc.) killed the local session out from under it
     mid-run. The collision also caused two REAL test failures in CI itself
     (`test_navigation_succeeds`, `test_mission1_completes` — genuine `Goal rejected
     after all retries` errors from two Nav2 stacks fighting over the same DDS
     topics/action servers), which needed a re-run to clear (confirmed: same commit,
     zero code change, passed clean the second time — pure resource contention, not a
     regression). **Practice adopted:** check `gh run list` for an in-flight run before
     launching anything Gazebo-related locally, especially right after a push.
  2. **A SEPARATE, unrelated local Gazebo/Nav2 stack from the `synthetic-fleet` project
     (a different git working directory on this same machine, open in another VS Code
     window) was found ALREADY RUNNING**, bound to the identical `/robot_001/...` DDS
     topic namespace as this repo's own launch — `pgrep -fa` showed two full sets of
     `robot_state_publisher`/`ball_detector`/`ekf_node`/Nav2-container processes
     side by side, one launched from `/home/mike/synthetic-fleet/install/...`, one from
     `/home/mike/autonomous-fleet-testbed/install/...`. This most likely explains the
     wildly-wrong ~15%/29-tests coverage run in the previous entry (two stacks
     cross-talking on the same topics looks exactly like flaky/failing navigation, not
     an obviously "two robots" symptom) and possibly some of the earlier collision's
     confusion too. **Deliberately NOT killed by Claude** — another project's live
     session in a window Mike may be actively using is not something to touch without
     being asked. Session paused here rather than work around it. **Before resuming
     Item 3 (or any local Gazebo-dependent test run on this machine going forward):**
     `pgrep -fa "gz sim|robot_state_publisher"` and check the launching PROJECT PATH in
     the command line specifically — process names alone look identical across
     projects that share the same `nav_fleet` package name.

## See also (moved out of this file by /doctor, 2026-07-27, context-lazy-loading pass)
- Nav2 launch gotchas (Session 10+) — `src/nav_fleet/CLAUDE.md`
- Isaac Sim gotchas (Session 11+) — `scripts/CLAUDE.md`
- Isaac GUI nav-test terminal procedure (Session 12+) — `isaac-gui-nav-test` skill
- Jetson Orin Nano hardware gotchas (Session 14+) — `jetson-hardware-notes` skill

