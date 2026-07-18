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
