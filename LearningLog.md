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
