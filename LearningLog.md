# LearningLog — Mike's curriculum record

> Standing Discipline #2 (see Release1Todo.md): each session appends the 3–5 concepts
> it introduced, phrased as teach-back questions Mike answers in his own words at the
> next session's start (or the same session's close). Shaky answers → re-explain and
> re-queue. Review the whole log at release boundaries.

## 2026-07-17/18 — Session 16 (Mission 2 observed runs) + planning night

**Concepts introduced (teach-back pending — answer at next session start):**

1. **Why did the "fuzzer" stop fuzzing?** What happened, mechanically, when tuning
   narrowed the ball-placement ranges — and why did fifteen different seeds produce
   what looked like the same scenario? What's the lesson about placement bounds being
   spec vs. tuning knobs?
2. **The FOV-edge range bug:** why does a ball clipped by the camera frame edge make
   the pinhole range formula (`range_k / width_px`) report the WRONG distance — and
   which direction is the error (too near or too far), and why?
3. **`ROS_LOCALHOST_ONLY=1`:** why did the sim silently break when the Jetson was off,
   why does this env var fix it, and why must EVERY process (launch, pytest, ros2 CLI)
   agree on it?
4. **Judges vs. observers:** the red test "passed" in 5 seconds with the robot parked.
   The ground-truth judge was satisfied — you weren't. What class of failure can only
   a human observer (or a min-travel assertion) catch, and what did we add so the
   judge catches it now?
5. **Real navigation vs. teleport for test cleanup:** why does the test *drive* the
   robot home instead of snapping it back — what breaks if you teleport (name the two
   stateful components), and why does drive-home transfer to the real robot while
   teleport can't?

**Session artifacts worth re-reading:** `.superpowers/sdd/progress.md` (the whole
Task 9 arc), the five commits `703469e..0b77e10`, reaction photos in `reports/photos/`.

**Teach-back outcomes (2026-07-18):**
1. Fuzzer — PARTIAL: answered with the parked-robot/degenerate-red story (that's Q4's
   lesson). The fuzzer mechanism (tuning narrowed placement bounds until all seeds
   converged on one spot; bounds are SPEC, not knobs) re-explained → RE-QUEUED.
2. FOV-edge range — unknown; re-explained (clipped bbox → width_px too small →
   range_k/width_px reads too FAR → trigger never fires) → RE-QUEUED.
3. ROS_LOCALHOST_ONLY — shaky (answered with a question); re-explained (CycloneDDS
   multicast on the dead Jetson link kills discovery; =1 confines DDS to loopback; all
   processes must share the setting or they can't see each other) → RE-QUEUED.
4. Judges vs observers — asked for the explanation; re-explained (vacuous-pass failure
   class; min-travel judge + start-position preconditions machine-encode it) → RE-QUEUED.
5. Teleport vs drive-home — MOSTLY RIGHT (knew localization/mapping state is lost);
   sharpened: the two stateful components are AMCL's particle filter and the costmaps'
   accumulated obstacle marks; drive-home transfers to the real robot, teleport can't.
   → PASSED with sharpening.

## 2026-07-18 — Session 16 close: merge day, the collision postmortems, the yellow bug

**Concepts introduced (teach-back pending — answer at next session start):**

1. **Branch → PR → merge:** we never pushed to main until tonight — what is a feature
   branch, what does "merging PR #4" actually do, and why did main stay frozen for a
   week while 46 commits piled up next to it?
2. **Docker layer caching & the cold build:** why did the same image build take 659 s,
   114 s, and 52 s at different times today? Which layer does a source-code change
   invalidate, and what three caches did we flush to force the cold build?
3. **The concurrency collision:** the merge fired TWO pipeline runs at once and they
   destroyed each other — why does GitHub allow that, what physical fact about OUR
   runners makes it fatal, and what one workflow block prevents it forever?
4. **The zombie goal:** the robot drove to the marker AFTER its mission had died —
   trace the chain (BT ack-timeout → aborted handle → controller still executing) and
   say why cancel-on-failure matters more on a real robot than in sim.
5. **Observation beats logs (4 events today):** name the four times your eyes
   overruled the recorded evidence today, and what each one changed.

**Open bug carried to tomorrow (the dossier is in progress.md):** post-merge, HIL
runs die around goal end/cancel — bond-drop lifecycle cascade + GraphicsMagick
recovery segfault. Prime suspects: yaw 0.15 tolerance, zombie-guard cancel on an
aborted handle.

**Teach-back outcomes (2026-07-19):**
1. Branch → PR → merge — PASS with sharpening: got the branch concept and the
   hotfix-on-main rationale. Sharpened: main stayed "frozen" only because nothing was
   merged (not locked); merging PR #4 landed all 46 commits onto main as one merge
   commit (7a86150); the PR is the review/CI container around the branch.
2. Docker layer caching — asked for the full explanation; explained (one layer per
   Dockerfile instruction, cached by content; a source change invalidates COPY-src and
   everything after it, never the apt/pip layers; 659s = no caches, 114s = registry
   buildcache warm, 52s = local BuildKit cache warm; the cold drill worked by bumping
   the registry cache ref so cache-from found nothing) → RE-QUEUED. Bonus question
   queued: docs-only push — which layers rebuild, and why is that a trick question in
   our pipeline?
3. Concurrency collision — PASS with sharpening: nailed the physical fact (one shared
   workstation + one Jetson; hosted runners would isolate). Sharpened: GitHub runs
   workflows concurrently by default because it assumes isolated runners; the fix is
   the workflow-level `concurrency:` group (fleet-ci-shared-hardware) that queues runs.
4. Zombie goal — MISS (guessed "made-up goal in sim"); re-explained (real 2026-07-18
   event: bt_navigator's 20ms ack window expired → goal handle ABORTED and the mission
   died — but controller_server had already accepted the path and kept driving:
   unsupervised robot reached the marker 12s after its mission was dead; on hardware
   that's a safety hazard, hence cancel-on-failure guard + 1000ms root fix) →
   RE-QUEUED.
5. Observation beats logs — principle PASS; the four events supplied: (a) Mike saw the
   robot driving after the logs said the mission died — that observation WAS the
   zombie-goal discovery; (b) his full-log paste overturned a too-narrow grep window
   (cold run's no_ball had ALSO failed); (c) his GUI review moved marker/ball east of
   the dresser; (d) home arrival visibly nosed-left while the old 0.5 rad tolerance
   called it arrived → yaw tightened to 0.15. Sharpened: the logs weren't wrong — they
   only answer the questions we thought to ask; eyes catch the unasked ones (why the
   GUI-observation standing rule exists).

## 2026-07-19 — Session 16 close: the forensics day (bug hunt by elimination)

**Concepts introduced (teach-back pending — answer at next session start):**

1. **The discriminating experiment:** we ran bare-metal BEFORE container, both at the
   exact failing sha. Why that order — what did each green result *eliminate*, and why
   is changing one variable at a time the whole game?
2. **"Didn't reproduce" ≠ "fixed":** the yellow bug never fired today, so we shipped
   no fix — what DID we ship instead, and why does instrumenting an intermittent beat
   guess-fixing it?
3. **Power modes as a timing variable:** which of today's runs were 25W and which
   15W, why does CI deliberately run the mission at 15W, and how can a slower clock
   turn a working system into a flaky one?
4. **Stale checkouts lie:** the Jetson was silently running July-13 code — how did it
   get there (what does CI's sync actually check out, and what did restore-checkout
   fail to do), and why does a repro on the wrong code prove nothing?
5. **`python file.py` vs `python -m package.module`:** the S17 fix wave broke both
   stage-5 jobs by adding one innocent import — explain where Python looks for
   imports in each invocation form, why the landmine sat harmless for months, and
   why the fix has two halves (canonical form in CI + self-defense in the tools).

**Carried re-queues:** Q2 Docker layers (+bonus: docs-only push — which layers
rebuild, and why is that a trick question in our pipeline?), Q4 zombie goal,
ROS_LOCALHOST_ONLY (+follow-up: Jetson powered on but Nav2 not running — do you need
the flag for a local sim session?).

## 2026-07-20 — S17 Piece 2 carry-ins, Piece 3 logging foundation, R1 autonomy planning

**Concepts introduced (teach-back pending — answer at next session start):**

1. **JetPack means two different things.** The OS image already flashed to the Jetson
   (Session 14, done) vs the `nvidia-jetpack` apt package (CUDA/cuDNN/TensorRT, not yet
   installed) — explain the difference and why NVIDIA overloading one name caused real
   confusion today.
2. **Two separate AI systems — don't conflate them.** `agentic_loop.py`'s Claude calls
   (cloud API, text/telemetry reasoning, off-robot) vs the on-device vision model being
   planned for R1 (local, edge, TensorRT-accelerated, works with the network off) —
   explain why the Jetson needs the second kind, not the first.
3. **The LaunchLogger bug — a live TDD win.** A `tools/log_setup.py` test passed
   standalone but failed under pytest with an empty log file, no errors. Explain the
   actual mechanism: why does merely having `launch-testing` *installed* (even with its
   pytest hooks disabled via `pytest.ini`) silently break every new logger created
   afterward in that process, and why does forcing `propagate = True` fix it? Why would
   writing the test AFTER the code already "worked" have been much less likely to catch
   this?
4. **Soft-fail CI gates.** Stage 0 showed green even though its traceability check
   exited 1. Explain the mechanism (`continue-on-error: true`) and why BR-03's missing
   recovery-behavior test is a real, deliberately-tracked gap — not something broken by
   today's changes.
5. **Classical primitives + inference-driven selection.** A pattern that came up twice
   today (detection-confidence-based speed, the recovery-move selector idea): proven,
   unmodified actions, but a model decides WHICH one to use given the situation. Explain
   why this project keeps preferring that shape over inventing new AI-driven maneuvers.

**Carried re-queues (STILL pending — now TWO sessions running, prioritize these FIRST
next time):** all five 2026-07-19 concepts above (the discriminating experiment,
"didn't reproduce" ≠ "fixed", power modes as a timing variable, stale checkouts lie,
`python file.py` vs `python -m package.module`) — teach-back didn't happen this session
either.

## 2026-07-21 — Session 17 Pieces 3/4/5: three full spec→plan→build→review cycles

**Concepts introduced (teach-back pending — answer at next session start):**

1. **Whole-branch review is not a formality.** All three pieces shipped today
   (Foundation, Piece 4, Piece 5) went through task-by-task review AND a separate
   final whole-branch review before merge — and all three final reviews found at
   least one real Important issue a task-scoped reviewer had missed (e.g. Piece 5's
   AI button crashing on a filtered-out run id — invisible to a reviewer looking at
   only the one commit that introduced it, since the guard pattern it was missing
   lived in an earlier commit). Explain why a review that only ever sees one task's
   diff structurally can't catch a cross-task gap, and why that's a *different*
   failure mode than "the reviewer wasn't thorough."
2. **The zero-variance baseline test trap.** A "does this correctly NOT flag as
   drift" test kept getting written by seeding a baseline with identical values
   (e.g. `nav_success_rate=0.95` ten times) — and `baseline_monitor.check_run()`
   explicitly skips any metric with zero variance (`if sd == 0.0: continue`), so
   the test's "no drift" assertion passed for the wrong reason: nothing was ever
   compared. Explain why a test that never actually exercises the code path it's
   named after is worse than no test at all, and why this bug pattern was so easy to
   keep re-introducing even after being fixed once (it recurred 4 times today).
3. **The same bug, found independently in three places.** Foundation fixed
   `FLEET_DB`/`DB_PATH` being a relative, checkout-dependent path instead of a
   persistent one. Piece 4's final review then found the IDENTICAL bug class — a
   relative `reports/photos` path — independently re-invented in three separate
   files (`mission_runner.py`, `mission2_day.py`, `generate_test_report.py`), none
   of which knew about the other two. Explain why "the same architectural mistake
   keeps happening in new files" is a signal about the codebase's *shared
   conventions*, not about any one file being sloppy — and what changed today to
   make it structurally harder to repeat (hint: where does the fix now live, and
   how many files import it instead of each defining their own).
4. **SQLite WAL mode, and why "set it once" wasn't actually a complete design.**
   Explain what WAL mode is, why it fixes the "dashboard reading while CI writes"
   concurrency case, why it's normally described as "set once, persists forever" —
   and then explain the real gap a reviewer found in that reasoning (what happens
   to a *brand-new* database file that's never had the PRAGMA run against it), and
   why baking the PRAGMA into `init_db()` closes that gap without contradicting the
   original "no per-connection changes" design goal.
5. **Git worktrees can branch from a stale `origin/main`.** All three pieces hit
   the same surprise when creating a worktree: it branched from `origin/main`
   (missing that day's local-only commits) rather than local `main`. Explain why a
   worktree tool would default to the remote tracking branch instead of local HEAD,
   and why `git merge main --ff-only` (not a rebase, not a manual re-commit) was
   the correct, safe fix each time.

**Carried re-queues (STILL pending — now THREE sessions running, prioritize these
FIRST next time, before today's 5 above):** all five 2026-07-19 concepts (the
discriminating experiment, "didn't reproduce" ≠ "fixed", power modes as a timing
variable, stale checkouts lie, `python file.py` vs `python -m package.module`) and
all five 2026-07-20 concepts (JetPack's two meanings, the two separate AI systems,
the LaunchLogger propagate=False bug, soft-fail CI gates, classical-primitives +
inference-driven-selection) — teach-back didn't happen either of the last two
sessions, and didn't happen today either given the session's length. This backlog is
now 15 concepts deep; next session should open with teach-back before any new work,
not just note it and move on again.
