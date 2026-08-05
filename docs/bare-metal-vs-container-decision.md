# Bare-metal vs. containerized: why Nav2 runs bare and mission logic runs in Docker

> **Superseded 2026-08-03.** This doc's conclusion (Nav2 stays bare-metal, only the
> mission loop containerizes) was reversed by the docker-brain unification — Nav2/EKF/
> `ball_detector`/`mission_runner` now all run inside one container on both HIL and the
> real robot. See `RealRobotStartup.md`'s intro item 2 and `docs/superpowers/specs/
> 2026-08-03-docker-brain-real-robot-hil-unification-design.md` for the current
> architecture. Left in place as historical context for the earlier decision's own
> reasoning, not as current guidance.

Written 2026-08-01, during the `RealRobotStartup.md` rewrite for real-robot deployment.
This is the honest version of a real architecture decision — including the part where
the first attempt was wrong — kept as a standing reference (interview prep, design
reviews, or just re-deriving "why is it built this way" six months from now).

## The short answer

This project does **not** run everything in a container, and it does **not** run
everything bare-metal. It's a deliberate split by layer:

| Layer | Where it runs | Why |
|---|---|---|
| Nav2 bringup, EKF (`robot_localization`), `ball_detector` — the whole ROS2/DDS navigation stack | **Bare host process**, from a native `colcon build` checkout | Real-time-adjacent, DDS-networking-heavy, needs to be maximally reliable at boot |
| Mission-level orchestration (`mission_runner.py`'s day loop, invoked via `mission_runner.py --day`) | **Inside the CI-built Docker image**, `--network host` | Plain Python + rclpy, no device access, no unusual dependencies — containerizing it buys artifact-identity guarantees with none of Nav2's DDS pain |

Neither half was picked from a rule of thumb. Both came from actually building the
thing and hitting real failures.

## What we tried first, and why it seemed obviously right

The original plan (2026-07-27 decision, `Release1Todo.md` Session 18) was
**"bare vendor driver + containerized brain"** — the vendor driver layer (motor serial,
lidar, camera — genuine `/dev` access) stays bare-metal, but the "brain" (EKF +
`ball_detector` + Nav2 bringup, i.e. `robot_launch.py`) runs inside the same container
image CI builds and tests. The reasoning at the time was sound on its face: this
project already had a proven, hardened container path for the mission-orchestration
layer (0.0000s inter-scenario overhead across bare-metal AND container, measured 3x
independently), and running the brain in the exact bits CI tested — a real
"bit-identical deployment" story — is a genuinely strong claim to be able to make.

## What actually happened once the real HIL pipeline got built

Two concrete, reproducible failures, both found live, both root-caused with real
evidence rather than guessed at:

1. **CycloneDDS's default interface auto-selection picked `docker0`** (Docker's own
   virtual bridge, an unrelated 172.17.0.0/16 subnet) **over the real network
   interface**, on the workstation side of HIL. `--network host` puts a container on
   the *same* network namespace as the host — including the host's own Docker bridges
   — so DDS's interface selection has to compete with virtual interfaces a real
   deployment has no reason to route through. The workstation's Gazebo/bridge topics
   never reached the Jetson at all, even though the two machines could ping each other
   fine (ping is unicast; DDS discovery is multicast — a different question entirely).

2. **A statically-configured CycloneDDS interface list hard-fails if that interface
   isn't currently up — it does not fall back to the next-priority one.** Confirmed
   live: with Ethernet physically unplugged, Nav2 died at startup with `enP8p1s0: does
   not match an available interface` — every ROS2 node on the Jetson failed together,
   not gracefully. For a robot that might legitimately boot on WiFi-only with no
   Ethernet ever connected (the real deployment scenario), a static config listing an
   absent interface is a real, boot-blocking risk, not a cosmetic issue.

Both got fixed (`scripts/regen_cyclonedds_config.sh` — regenerates the interface list
from real, current `/sys/class/net/*/operstate` link state before every launch,
auto-detecting physical-vs-virtual interfaces so it needs no per-machine hardcoded
list) — but fixing them meant the DDS-networking-in-a-container problem was never
free. It cost real engineering time, on both ends of the HIL link, to make
containerized ROS2 networking behave.

## The actual fault line, once we looked for it

Tracing the real, currently-running code (not the original decision doc) found that
the container role that HIL actually proved was narrower than the plan: `JetsonExecutor`
(`tools/mission2_day.py`) only ever wraps the raw `python3 -m nav_fleet.mission_runner
--day` ROS2 process — nothing about ball-choreography selection, per-leg judging, the
`fleet_runs.db` telemetry write, or the VLM-canary spawn ever runs inside a container,
anywhere. `scripts/hil_stage.sh`'s own `nav2_up()` — the thing that actually brings up
Nav2/EKF/`ball_detector` for every single HIL run — has always launched them as a bare
host process (`nohup ros2 launch ...`), never through `docker run`, regardless of
`HIL_CONTAINER`. That's not an oversight; it's confirmed as deliberate in this
project's own Gotchas: *"controller_server/bt_navigator are NEVER containerized in
EITHER HIL mode."*

So the plan said "containerized brain," but the thing that actually got built, proven,
and hardened over weeks of real HIL runs never containerized the brain at all — only
the thinner mission-orchestration layer sitting on top of it. The plan and the
implementation had quietly diverged, and nothing had gone back to reconcile them until
this review.

## The general principle, if you want the transferable version

This isn't "containers are bad for robotics" — it's:

- **Containerize the layer that's just software** — no device access, no unusual
  runtime dependencies, no hard real-time constraint. You get reproducibility and
  artifact-identity guarantees essentially for free, because there's nothing about the
  layer that resists being packaged.
- **Be much more careful about containerizing anything that talks DDS, owns a
  real-time control loop, or touches `/dev` directly.** `--network host` is close to
  mandatory for ROS2-in-a-container to work at all, which means you give up most of
  Docker's actual network isolation anyway — you're paying the integration cost
  without the corresponding benefit. Vendor hardware drivers are also frequently only
  validated against native installs.
- **A pipeline gate that keeps passing doesn't mean the decision behind it hasn't
  drifted.** HIL was green, repeatedly, the whole time the plan and the code disagreed
  about which layer was containerized — because HIL's own container role was always the
  narrower one, and nothing tested the wider claim ("robot_launch.py runs clean... in
  container") in Part A of `RealRobotStartup.md`. The lesson isn't "test more" in the
  abstract — it's that a design decision written down in a runbook needs to be
  re-verified against what actually got built, not assumed still true because CI is
  green for something adjacent.

## Where this leaves R1's real deployment

`RealRobotStartup.md`'s `robot_launch.py` (Nav2/EKF/`ball_detector`) runs bare, from a
native `colcon build` checkout synced with `scripts/hil_stage.sh sync <sha>` — matching
`nav2_up()` exactly. The Docker image's proven role stays what HIL actually validated:
being the thing CI tests before that same commit gets pulled onto the robot's own
checkout — not something the robot runs at power-on.

**Open item for next session:** with the mission-orchestration layer's role now this
narrow, revisit what `stage-3-arm64` (the native arm64 Docker build) is actually buying
the pipeline going forward — see `CLAUDE.md`'s NEXT SESSION block.
