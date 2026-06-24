<!-- Page 1 -->
ROS2 Rover CI/CD: 10x Rethink & Tool Business
Model
Notes from a working session on the ROS2 Rover CI/CD & Autonomy Guide (v2, JetPack 7.2 /
Ubuntu 24.04 / ROS2 Jazzy)
1. The 10x rethink of the CI/CD pipeline
The pipeline in the guide is solid, conventional engineering: lint, unit test, cross-compile, simulate,
drift-check, publish, deploy, smoke-test, gated linearly, run once per push, validating one rover against
one set of fixed thresholds. 10x thinking means asking what changes structurally if one axis is multiplied
by ten, rather than optimized by ten percent — run it 10x more, with 10x more variation, or 10x earlier —
instead of just making the existing shape faster.


---

<!-- Page 2 -->
Figure 1. The 1x linear pipeline (top) versus the 10x rethink: a parallel perturbation matrix replacing the single fixed-seed
Gazebo run, fleet-aware staged rollout replacing single-rover deploy, and a portability layer that turns the pipeline into a
reusable product rather than a one-off script.
Drift detection should predict, not just report
The current drift_detector.py compares each run's metrics against the last five runs and fails if a fixed
threshold is crossed — a smoke alarm, not a thermostat. A 10x version trains a lightweight regression
that predicts the expected metric shift given a diff (files changed, parameters touched, world changed),
then flags runs where the actual result deviates from the predicted result rather than from a static
threshold. This catches the case a fixed threshold never will: a change that should have improved
nav_success_rate but didn't move it at all.


---

<!-- Page 3 -->
Stop running one simulation — run a perturbed swarm
Gazebo currently runs once per PR on a fixed, reproducible seed. That's good for determinism but blind
to the tail risks that actually matter: marginal wheel slip, dim lighting, a noisier lidar. Gazebo Harmonic
headless is cheap enough to run 20–50 short parallel episodes per PR with randomized friction, lighting,
obstacle placement, and sensor noise sampled around the SC-0x baseline values. The drift gate then
becomes a distribution comparison — did the spread of outcomes shift — rather than a single sample
comparison, and this is the right place to spend additional compute budget, not on a single longer or
prettier Isaac Sim run.
Fleet-aware deploy instead of single-rover deploy
Stage 6 treats deploy as ssh into one Jetson, push, smoke test, rollback on failure. Building rollout logic
in now, before a fleet exists, avoids a painful retrofit later. Canary deployment promotes to one rover first
and only pushes to the rest after a live monitoring window passes. Shadow mode goes further: a new
autonomy stack runs alongside the production one, consuming the same sensor data and computing
what it would do, while the motor watchdog still listens to the old stack. Logging the disagreement
between old and new decision-making lets a team validate new code on real hardware without betting the
robot on it — the same approach used in production self-driving validation — and it works even on a
single rover, since the ESP32 watchdog only consumes whichever stack is wired to /cmd_vel.
Traceability and drift as the most generalizable piece
check_traceability.py and drift_detector.py aren't rover-specific: enforcing that every requirement has a
test, and regression-testing behavioral metrics against history, is a discipline almost no robotics team
builds from scratch under deadline pressure. Packaging the traceability gate and drift detector as a
standalone, sim-agnostic GitHub Action or CLI — pointed at a team's own requirements YAML and their
own sim output — sells the discipline layer on top of whatever simulator a team already uses, rather than
competing with Gazebo or Isaac Sim directly.
Sim-agnostic adapter and a live requirements contract
The guide hand-wires Gazebo and Isaac Sim as two separate stages with separate report shapes.
Defining one internal sim-result schema and writing a thin adapter per simulator means drift_detector.py
and report_generator.py never need to know which simulator ran, which is also what makes the
standalone traceability tool usable across teams on different simulators. Separately, nothing today
verifies that the Gazebo world file actually matches what the SC-0x requirements claim it should be —
generating obstacle count, lighting, and friction directly from the requirements YAML at build time closes
that gap.
Hardware-in-the-loop firmware testing
Stage 1's PlatformIO Unity tests run in a native x86 environment, which validates PID math and JSON
parsing but never touches real watchdog timing or UART behavior — exactly where MCU-02's 200 ms
timeout and MCU-06's 921600 baud round-trip latency live. A self-hosted runner with a low-cost ESP32
dev board lets a CI stage flash the actual firmware and verify watchdog timing and UART latency on real
silicon, closing the one gap that no amount of cloud CI scaling fixes on its own.


---

<!-- Page 4 -->
2. Open-source core vs. paid layer for the traceability/drift tool
The split should follow a real value boundary rather than an arbitrary feature gate. A single team running
this on one rover, one repo, one CI runner has no need for a server — everything in the requirements
gate and the local drift check is a CLI operating on files already in their own repo. The boundary falls
where the tool stops being valuable solo and starts being valuable as infrastructure: comparing across
robots, keeping history beyond a single CI artifact window, or getting alerted without watching logs.
Figure 2. Open-source CLI core (top) versus the hosted paid layer (bottom). The fence sits where the feature requires
persistent infrastructure or aggregated data across teams, not where a feature happens to be more sophisticated.
Why traceability and local drift stay free


---

<!-- Page 5 -->
These need zero external state: the traceability check reads two YAML files and fails the build on an
uncovered requirement, and the local drift check reads the last N JSON reports from disk and compares
against fixed thresholds — exactly what the guide's own Stage 0 and reports/history/ folder already do.
Charging for this would just push competent teams back to maintaining their own version of the script,
since nothing here benefits from a vendor's servers. Giving it away is also how adoption happens: every
team running the open CLI is a team whose CI logs already speak the tool's schema, which is the
precondition for everything in the paid tier.
Why the predictive model is a natural fence, not an arbitrary one
A predictive drift model needs training data, and one team's history is thin — a few hundred data points
across one robot configuration after several months. The model improves meaningfully with pooled,
anonymized data from many teams' runs: diff characteristics in, metric deltas out. That pooling
requirement is a genuine network effect, the same shape as a security vendor aggregating threat
intelligence across customers, and it's a stronger moat than simply withholding source code.
Why the dashboard and alerting are paid even though they aren't hard
Fleet dashboards and notifications aren't technically difficult, but they require a server that's always on,
storage beyond CI artifact retention, and notification delivery — a hosted-service cost structure that a CLI
invoked once per CI run can't provide. This gates hosting cost, not cleverness, which is the conventional
and defensible place to charge in an open-core model.
Sequencing risk
The predictive model only becomes credible once several teams' worth of runs exist, which won't be true
on day one for a tool whose first user is its own creator. The realistic path is: open-source CLI first, get
teams using the free tier (useful standalone), let the hosted dashboard and alerts be the first paid tier,
and keep the predictive model as a stated roadmap item until there's enough pooled data for it to
outperform a per-team static threshold. Marketing the predictive model before the data exists to support it
is the kind of overclaim that erodes trust with the technical audience the tool depends on.
