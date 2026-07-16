# Session 15 — HIL CI Stage Design (design only, not yet implemented)

This document is the design the future CI-implementation session executes from. It does
**not** change `.github/workflows/ci.yml` — no workflow, launch, or code files were touched
by the work that produced it. It records *decisions* (write these as decided, not as open
options) plus the operational learnings from the manually-executed first HIL run
(`docs/runbooks/Mission1HILSession15.md`, 2026-07-11) that the CI stage must account for.

**What "HIL" means here (for the reader learning the setup):** Hardware-in-the-Loop. The
simulator (Gazebo — the bedroom world plus the robot's lidar/camera sensors) runs on the x86
workstation. The *robot brain under test* — Nav2 (path planning + control) and the mission
executor — runs on the **real Jetson Orin Nano**, the same compute that would sit on a
physical robot. The two halves exchange ROS2 topics (`/robot_001/scan`, `/clock`, `/cmd_vel`,
camera frames) over CycloneDDS across the shared-Ethernet link. So we test the actual robot
computer against a simulated body — catching Jetson-specific timing/perf/DDS problems that a
pure-sim CI stage on the x86 box never would.

**Status:** design approved for a later implementation PR. The manual prototype it is based on
passed on the first attempt (single run — see the reproducibility caveat under Open items).

---

## 1. Orchestration: one GHA job on the x86 runner, driving the Jetson over SSH

**Decision.** The HIL stage is a **single GitHub Actions job**, running on the existing x86
GPU self-hosted runner (`[self-hosted, x86, gpu, rtx5080]`), which drives the Jetson entirely
over `ssh mike@<jetson>`: Nav2 launch, mission run, DB read, photo retrieval, and teardown all
happen as SSH commands issued from the x86 job. The workstation hosts Gazebo (the sim half)
locally in that same job.

**Why one job and not two coordinated runners.** A GitHub Actions *job* is pinned to exactly
one runner for its whole lifetime. "One HIL test" inherently spans two machines (sim on x86,
brain on Jetson), but that cannot be expressed as a single job running on two runners at once.
The alternative — an x86 job and a Jetson job that hand off through uploaded artifacts or the
GitHub API — means each side polls for the other's state. That is brittle (polling races,
partial-failure ambiguity) and, critically, makes **teardown on failure unreliable**: if the
x86 job dies, nothing guarantees the Jetson job ever cleans up its Nav2/mission processes, and
vice-versa. Driving the Jetson as a subordinate over SSH keeps the whole test under one job's
control, so a single `if: always()` teardown step can clean **both** sides deterministically.

**The Jetson stays a registered runner — but this stage treats it as a lab instrument, not a
runner.** The Jetson keeps its GHA-runner registration (`[self-hosted, arm64, jetson]`)
because `stage-3-arm64` still legitimately uses it to *build* the arm64 image natively. During
the HIL stage, though, the Jetson is not asked to run a job — the x86 job SSHes into it and
uses it like a bench instrument. Both roles coexist: stage-3 dispatches a job *to* the Jetson;
stage-4-hil reaches *into* the Jetson over SSH from the x86 job.

**Network / addressing decisions (from the executed run).**
- **Link:** NetworkManager-shared Ethernet, `10.42.0.0/24`, workstation gateway `10.42.0.1`,
  Jetson `10.42.0.217` *today*. Not USB-C.
- **The Jetson IP is a DHCP lease and must be resolved at job start**, never hard-coded. First
  step of the job: `ip neigh show dev enp6s0` on the workstation to discover the current
  lease, export it as `JETSON_IP`, and fail fast with a clear message if none is found. WHY:
  a lease change across a Jetson reboot must not silently point the job at a dead or wrong
  host. (Where the user/host *inventory* should live — repo variable vs. pure discovery — is
  an Open item; the IP itself is always discovered, not stored.)
- **Discovery mode:** plain **CycloneDDS multicast**. In the manual run, multicast traversed
  the shared link cleanly on the first try — `ros2 topic list` on the Jetson showed all
  `/robot_001/*` topics and `/robot_001/scan` held a steady **~10 Hz**. The unicast-peers
  fallback (`~/cyclonedds-hil.xml`) was **not needed** and is **not** part of the CI happy
  path. WHY document it anyway: it stays in the runbook as insurance, and the CI stage should
  treat a discovery miss as the most likely flake (see retry policy under §3).
- **Prereq:** the workstation's SSH key is already authorized on the Jetson (Session 14), so
  SSH is non-interactive. This design assumes that key stays valid.

**Every SSH command must source its own environment.** Non-interactive SSH gets a **bare
environment** on the Jetson: its `~/.bashrc` has the standard Ubuntu early interactivity guard
(`case $- in *i*) ;; *) return ;; esac`), so a scripted shell skips *all* of the file's
sourcing — ROS2, the colcon overlay, and `RMW_IMPLEMENTATION` are simply absent. Therefore
every `ros2`/mission SSH command in the job MUST prefix:

```bash
source /opt/ros/jazzy/setup.bash \
  && source ~/autonomous-fleet-testbed/install/setup.bash \
  && export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp \
  && export ROS_DOMAIN_ID=0 \
  && <the ros2 / mission command>
```

WHY: this bit us in the manual run (topics invisible until the env was sourced explicitly).
Human interactive SSH is unaffected, so it is an easy trap to forget in automation. The x86
side already sources everything from its own `.bashrc`/CI setup; this sourcing burden is a
Jetson-side, over-SSH-only concern.

**Jetson-side environment quirks the job scripts must respect (from the run):**
- `python3`, **not** `python` — matches the Session-14 Jetson env.
- **No `sqlite3` CLI** on the Jetson — read the telemetry row with
  `python3 -c "import sqlite3; ..."`, never a `sqlite3` shell invocation.
- **`colcon build --base-paths src`** is mandatory on the Jetson. The self-hosted runner lives
  *inside* the repo (`~/autonomous-fleet-testbed/actions-runner`, Session 14 Part 8) and its
  `_work/` tree holds a *second* `src/nav_fleet`. A bare `colcon build` scans both, finds two
  `nav_fleet` packages, and aborts with "Duplicate package names not supported". Scoping to
  `src/` avoids the runner's own checkout. (Latent trap flagged under Concerns — relocating
  the runner out of the repo tree is the real fix; `--base-paths src` is the workaround.)
- pillow is present as the system package `python3-pil` (10.2.0). If a re-flashed board lacks
  it, install via `apt install -y python3-pil`, **not** pip — Ubuntu 24.04 is PEP-668
  externally-managed and bare pip is refused.

---

## 2. Success / failure definition

**PASS.** `RUNNER_TYPE=hil_jetson python3 -m nav_fleet.mission_runner mission1`, run on the
Jetson over SSH, **exits 0 within its timeout**. On exit 0 the job then, as verification (not
as pass/fail gates — these are evidence collection):
1. `scp`s the mission photo (`reports/photos/mission1_step2_*.png`) back to the x86 runner and
   `uploads it as a workflow artifact` so a human can eyeball the bedroom-from-doorway frame.
2. Reads the new telemetry row from the Jetson's local `reports/fleet_runs.db` over SSH with
   `python3` (no `sqlite3` CLI) and prints it to the job log:
   ```
   SELECT scenario, result, runner_type, sim_engine, mean_time_to_goal, mean_position_error
     FROM runs ORDER BY id DESC LIMIT 1;
   -- expected: ('mission1','PASS','hil_jetson','gazebo', ~7.95, ~0.21)
   ```
   The `runner_type='hil_jetson'` tag is what distinguishes a HIL row from a pure-sim row.

**FAIL** = any of: nonzero mission exit code, SSH timeout/connection failure, a per-phase
timeout tripping (§3), or the **photo or DB row missing** after a claimed pass. WHY require the
photo *and* row, not just exit 0: the mission executor's exit code proves the nav goals
succeeded, but the photo proves the *camera pipeline crossed the network intact* and the DB
row proves telemetry was actually recorded — both are the point of a HIL test and both have
independent failure modes (camera bridge, DB write).

**Telemetry shipping to the workstation drift DB is phase 2 (deferred, but the mechanism is
decided).** For `baseline_monitor` to watch HIL trends over time, the Jetson's HIL row must
land in the workstation's `fleet_runs.db`. **Decision:** ship the **row**, via a `sqlite3`/
`python3` `SELECT` over SSH followed by a local `INSERT` into the workstation DB — **not** by
copying the whole Jetson DB file over. WHY row-not-file: the two databases have independent
histories (the workstation accumulates sim runs continuously); copying the file would clobber
that. A single-row transfer is also cheap and keeps the schema authority on the workstation
side. Phase 1 (first implementation) only prints the row to the log; wiring it into the drift
DB is an explicit follow-up so the first CI iteration stays small and debuggable.

---

## 3. Timeout / teardown

### Timeouts — budgets and the measured numbers they come from

| Scope | Budget | Measured (manual run) | Why this budget |
|---|---|---|---|
| **Job-level** | `timeout-minutes: 15` | ~28 s of actual test work (Nav2 ~5 s + mission ~18 s + sim/bridge bring-up ~5 s) | Matches the retired `stage-4-isaac` slot. Leaves headroom for the Jetson `colcon build --base-paths src` (~5 s warm), SSH round-trips, and a one-shot retry, while still bounding a hung job. |
| **Sim up (x86)** | ≤ 60 s | ros_gz bridge came up ~5 s after Gazebo | 60 s = ~12× margin. The bridge must be up before the Jetson sees any topic; generous because a cold Gazebo world load under CI load is the slow case. |
| **Nav2 active (Jetson)** | ≤ 120 s | **~5 s** warm (`ros2 launch` → `Managed nodes are active`, log epochs 1783820710→…715) | 5 s was on a warm Orin with sim topics already live and 1 s log resolution — treat as "well under 10 s," not a precise benchmark. 120 s = ~24× margin absorbs a cold/loaded bringup and DDS discovery settling. Gate on the literal `Managed nodes are active` log line. |
| **Mission (Jetson)** | ≤ 300 s | **~18 s** total (step1 nav ~5.3 s, take_picture ~0.07 s, step3 nav ~10.6 s; mean_time_to_goal 7.95 s) | 300 s = ~16× margin. Sized deliberately large to cover the mission executor's **5× goal-rejection retry** loop (bt_navigator not yet ACTIVE) plus possible DDS discovery flake, without a slow-but-succeeding run being killed. |

WHY margins this wide across the board: the manual run was a single warm-system success. CI
adds cold checkouts, build load, and unproven reboot/fresh-DDS reproducibility — the budgets
are set to fail only on a genuine hang, not on the normal spread of a healthy run.

Note on the Nav2-active budget: the ≤ 120 s figure **deliberately tightens the 180 s working
budget used during the manual run** — the measured ~5 s bringup showed 180 s was far looser
than needed, and 120 s still leaves ~24× the measured time.

**Retry policy (decided).** The stage retries the mission **once** on a DDS-discovery-shaped
failure (no topics / goal never accepted), after a full both-sides teardown and a ~5 s DDS
settle. WHY: reproducibility across fresh DDS state is not yet established, and discovery is
the most likely intermittent failure; one clean retry converts a transient flake into a pass
without masking a real regression (a second failure still fails the stage).

### Teardown — `if: always()`, unconditional `pkill -9` fallback, correct PID discovery

A teardown step runs with **`if: always()`** (so it fires on pass, fail, *and* timeout) and
cleans **both** sides:

**Jetson (over SSH):**
```bash
ssh mike@$JETSON_IP \
  "pkill -9 -f '[n]av2|[c]omponent_container|[m]ission_runner' || true"
```
(This pattern is generalized from — not byte-identical to — the one used in the manual run's
teardown, which was `pkill -9 -f "[c]omponent_container|nav2_only_launch|ros2 launch"`; the CI
form adds `mission_runner` and matches any nav2 process, not just the specific launch file.)

**Workstation (local):** kill the sim launch process group, then an **unconditional
`pkill -9` fallback**:
```bash
kill -INT -$LAUNCH_PGID 2>/dev/null || true
pkill -9 -f '[g]z sim' || true
pkill -9 -f '[c]omponent_container' || true
pkill -9 -f '[r]obot_state_publisher' || true
```

**WHY the `pkill -9` fallback is unconditional (not "only if kill -INT failed").** SIGINT
teardown reliability was **mixed across Session 15's manual runs**: the single HIL run's
teardown was clean (SIGINT to the launch process sufficed — recorded in
`docs/runbooks/Mission1HILSession15.md`), but **both Tier-1 (single-machine x86 sim) verification teardowns**
earlier in the session left orphaned `gz sim` / `component_container` /
`robot_state_publisher` processes and needed `pkill -9` (observed during the session; not
preserved in a committed artifact). Since a CI job has no human at a foreground terminal to
Ctrl+C, the unconditional `pkill -9` fallback is **defense-in-depth, not an optional path** —
the one place a scripted force-kill is not only acceptable but required
(this mirrors the existing CI-cleanup note in `CLAUDE.md`: never chain `pkill` hopefully
mid-session, but a job's final cleanup step is exactly where it belongs). Leftover processes
would poison the *next* run's DDS state, so partial cleanup is worse than none.

**WHY the `[g]z sim` bracket trick and `ps aux | grep "[r]os2 launch"` PID discovery.** Two
traps this session's manual runs exposed:
1. The bracket in `'[g]z sim'` stops the `pkill`/`grep` pattern from matching *itself* in the
   process table (the grep process contains the literal string otherwise).
2. **`$!` after a compound backgrounded command captures the wrong PID** — it grabs the last
   element of the pipeline/compound, not the `ros2 launch` we want to signal. So the launch
   PID must be discovered by pattern: `ps aux | grep "[r]os2 launch" | awk '{print $2}'`
   (capture its process-group id for `kill -INT -$PGID`), not by trusting `$!`.

---

## 4. Job naming / renumbering decision

**Decision: no renumbering.** The HIL job takes the existing **Stage 4 slot** as
**`stage-4-hil`**, *replacing* `stage-4-isaac` when implemented. Isaac is shelved per the
Session 15 spec, but its job and scripts are **retired to git history, not deleted from disk
preemptively** — we remove `stage-4-isaac` from the workflow only in the same PR that adds
`stage-4-hil`, keeping the numbering and the downstream `needs:` edges stable.

Resulting pipeline shape (unchanged except the stage-4 identity):
```
stage-0-requirements → stage-1-quality → stage-2-gazebo ─┬─→ stage-3-arm64 ─→ stage-4-hil ─→ stage-5-reports-hw
                                                         └─→ stage-5-reports-sim
```

**`needs: stage-3-arm64` is preserved — and finally becomes REAL.** Today `stage-4-isaac`
declares `needs: stage-3-arm64` but the dependency is nominal (Isaac never consumed the arm64
image). Under `stage-4-hil` the edge earns its meaning in **phase 2**: the stage pulls the
stage-3 GHCR arm64 image *onto the Jetson* and runs the mission executor **inside that
container**. That is the `arm64 → HIL` edge the original hand-drawn pipeline diagram always
intended — the arm64 build finally gets exercised on real hardware end-to-end.

**Phase 1 runs natively on the Jetson**, exactly like the manual prototype (host `python3 -m
nav_fleet.mission_runner`, no container). WHY split the phases: keep the *first* CI iteration
as close to the debugged manual run as possible — one new variable at a time. Add the
container indirection only once the native HIL stage is green and trusted, so a phase-2 failure
is unambiguously a containerization problem, not a HIL problem.

**`stage-5-reports-hw` is unchanged in shape** — it keeps `needs: stage-4-hil` (was
`needs: stage-4-isaac`; only the referenced job name changes with the rename). Its job key and
position stay put.

**Suggested addition (belongs to the implementation PR, noted here for the reader):** the same
mission logic can run sim-only and cheaply in `stage-2-gazebo` via `tests/test_mission_run.py`
— leaning yes, but it is a separate change from wiring the HIL stage (see Open items).

---

## 5. Open items for the implementation session

These are the **only** items intentionally left unresolved; everything a spec success-criterion
asks for is decided in §1–§4 above.

- **Reproducibility under CI load and across reboots.** The manual prototype was a **single
  successful, warm-system run** — reproducibility across reboots / fresh DDS state is not yet
  established. The implementation session must confirm Gazebo-headless + Nav2-on-Orin under CI
  load stays within the §3 phase timeouts across several runs, and validate the retry-once
  policy actually rescues a discovery flake. Manual-run reference numbers to size against:
  Nav2 active **~5 s**, mission total **~18 s** (step1 ~5.3 s / take_picture ~0.07 s /
  step3 ~10.6 s), scan cross-link **~10 Hz**, DB row
  `('mission1','PASS','hil_jetson','gazebo',7.95,0.21)`.
- **Secrets / inventory.** Where the Jetson user/host live — a repo/organization variable
  (e.g. `JETSON_SSH_USER`) vs. deriving everything at runtime from the `ip neigh` discovery
  step. (The IP itself is always discovered at job start; this item is about the *user* and
  any static config.)
- **Sim-only mission test in stage-2-gazebo.** Whether `stage-2-gazebo` should also run
  `tests/test_mission_run.py` (same mission logic, sim-only, cheap) — leaning **yes**, but it
  is part of the implementation PR, not this design.
- **Phase-2 containerized mission on the Jetson.** The mechanics of pulling the stage-3 GHCR
  arm64 image onto the Jetson and running the executor inside it (registry auth on the Jetson,
  DDS/host-network passthrough into the container) are deferred to phase 2.
- **Relocating the nested `actions-runner`.** `--base-paths src` is the documented workaround
  for the duplicate-package trap; moving the runner out of the repo tree is the real fix and a
  candidate for a future maintenance session.

---

## Appendix — spec success-criterion → section map (self-check)

The Session 15 spec requires this design to settle four things. Each maps to a section above,
with no "TBD" anywhere outside §5 Open items:

| Spec success-criterion | Answered by |
|---|---|
| Network orchestration approach | §1 (one x86 job driving the Jetson over SSH; IP discovered via `ip neigh`; multicast DDS; per-SSH env sourcing) |
| Success / failure definition | §2 (mission exit 0 + photo artifact + `hil_jetson` DB row; FAIL conditions; telemetry-shipping phase-2 mechanism) |
| Timeout / teardown behavior | §3 (job 15 min; per-phase 60/120/300 s budgets derived from measured 5 s / 18 s; `if: always()` both-sides teardown with unconditional `pkill -9` and PID-discovery pattern; retry-once policy) |
| Job renumbering plan decided | §4 (**no renumbering**; `stage-4-hil` replaces `stage-4-isaac`; `needs: stage-3-arm64` preserved and made real in phase 2; `stage-5-reports-hw` shape unchanged) |
