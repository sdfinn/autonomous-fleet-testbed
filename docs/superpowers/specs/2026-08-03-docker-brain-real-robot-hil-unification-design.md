# Docker Brain: Unifying Real-Robot and HIL Deployment

Status: **implemented and merged to `main` 2026-08-04** — live-validated end to end,
including a real `stage-4-hil` run on the actual Jetson (see root `CLAUDE.md`'s
2026-08-04 NEXT SESSION entry for the full result). This doc still describes the
ORIGINAL, wider idea as written 2026-08-03 — **two real deviations were decided live
with Mike during implementation and are NOT reflected below.** The plan doc's own
"Global Constraints" section (`docs/superpowers/plans/
2026-08-03-docker-brain-real-robot-hil-unification-plan.md`) has the real, current,
binding decision — read that section, not this doc's prose, if the two disagree:
1. Ball placement, ground-truth reading, and judging (`tools/mission2_harness.py`)
   stay workstation-side for HIL, unchanged — NOT moved into the container's own
   self-orchestration as this doc originally proposed.
2. The real robot gets no ground-truth judging at all (impossible — no Gazebo, no
   oracle) — it self-reports each leg's own PASS/FAIL; analysis happens after,
   manually, not in real time.
Left in place as historical context for the design reasoning, which is otherwise
still accurate.

Written 2026-08-03.

## Context

The 2026-08-01 `RealRobotStartup.md` rewrite settled on bare-metal end to end for the
real robot (Nav2/EKF/`ball_detector`/`mission_runner` all bare), on the grounds that
this is what HIL had actually hardened over weeks of real runs — the container's real,
proven role was always narrower than the original 2026-07-27 "containerized brain"
plan (see `docs/bare-metal-vs-container-decision.md`). That entry left one open
question for next session: given the container's proven role is this narrow, is
`stage-3-arm64` still earning its keep?

This session revisited that question directly and reversed it, deliberately: Mike's
explicit direction was to decide on long-term architectural merit for the fleet
testbed's actual future (multi-robot, OTA-style updates, a growing perception/
inference layer) rather than defer to what HIL happened to harden first, and to treat
rework as normal, not something to avoid for its own sake.

**Net decision: the Docker approach is back, restructured to be genuinely long-term —
not a re-adoption of the 2026-07-27 plan as originally written.**

## Guiding principle

Split by build mechanism, not by subsystem: **bare metal = only what's kept current
via `apt upgrade`/vendor install, with zero build of our own repo, ever. Everything
that needs a `colcon build` of our own code goes into one Docker image, one
container.** (Mike's framing, session 2026-08-03.) The one deliberate exception: the
vendor driver layer (`ugv_ws`, `/dev` access) stays bare regardless of its own build
mechanism — justified independently by device access and hardware-specific
validation, not by this rule.

## Corrections made to externally-sourced advice during this session

A pasted set of recommendations (assumed AI-generated, JetPack/Jazzy-specific) shaped
part of this design but contained real factual errors for this exact board, confirmed
against live device output (`nvcc --version`, `/etc/nv_tegra_release`, `dpkg -l`) and
independent web search:

- **Claimed JetPack 7.2 ships CUDA 12.6 pre-installed.** Wrong — this board runs CUDA
  13.2.1 (`nvcc` confirmed), matching JetPack 7.2 = L4T **r39.2** (confirmed via
  `/etc/nv_tegra_release`). 12.6 is the JetPack 6.x number.
- **Suggested Docker base image `nvcr.io/nvidia/l4t-pytorch:r36.4.0-pth2.5-py3`.**
  Wrong L4T generation — r36.x is JetPack 6.x. Would reintroduce exactly the
  host/container CUDA-version-mismatch problem this whole redesign exists to avoid.
- **Correctly assumed** Docker + `nvidia-container-toolkit` are present and
  configured — confirmed live: Docker 29.6.2, `nvidia-container-toolkit 1.19.1-1`,
  and `/etc/docker/daemon.json` already registers the `nvidia` runtime. No setup work
  needed here.

Lesson carried forward: verify version-specific claims about this exact board against
live device output before designing against them, regardless of source.

## Architecture

### Bare metal

- OS (Ubuntu 24.04) + `ros-jazzy-ros-base` + whatever `ros2_control`/
  `robot_state_publisher` packages the vendor driver workspace needs.
- Waveshare `ugv_ws` vendor workspace (motor/lidar/camera, `/dev` access) — unchanged
  from `RealRobotStartup.md` A2.
- Docker + `nvidia-container-toolkit` — already present, nothing to install.
- Ollama (model server, direct CUDA access) — stays bare-metal, systemd-managed,
  unchanged from today.
- **`~/autonomous-fleet-testbed`'s own bare `colcon build`/`install/` goes away
  entirely.** Nothing bare launches `nav_fleet` code once this lands. The checkout
  still needs to exist on the Jetson (for `regen_cyclonedds_config.sh`,
  `robot_boot.sh`, and identifying which image tag to run), but nothing in it gets
  built there.

### Container ("the brain")

One image, one container, `--network host --ipc host`, extending the existing
Dockerfile (already apt-installs generic Nav2 packages, copies `src/`+`tools/`,
`colcon build`s inside the image — unchanged):

- Add `ros-jazzy-robot-localization` (the one missing generic apt package for EKF —
  currently only installed on bare hosts, never in the image).
- Contains: EKF (`ekf_node`), `ball_detector`, Nav2 bringup, `mission_runner`,
  `mission2_day` (day orchestration/judging/telemetry/VLM-canary spawn), and the
  inference client module (below).
- No GPU/CUDA access needed in the image today — Ollama stays bare-metal, container
  calls it over `localhost` (free via `--network host`).

### Launch file: no new file needed

Compared `nav2_only_launch.py` (HIL's current launch) against the `robot_launch.py`
content originally proposed in `RealRobotStartup.md` A5 — they are structurally
identical (same three nodes: `ekf_node`, `ball_detector`, Nav2 bringup via
`nav2_bringup`'s `bringup_launch.py`; same remappings; same
`use_composition`/`use_namespace`/`autostart` settings). The only differences are
three parameter values:

| | HIL value (today's default) | Real robot value |
|---|---|---|
| `use_sim_time` | `true` | `false` |
| ball_detector `hsv_config` | `hsv_gazebo.yaml` | `hsv_realcam.yaml` |
| Nav2 `map` | `living_room.yaml` | `bedroom_real.yaml` |

**Decision: extend `nav2_only_launch.py` with three new `DeclareLaunchArgument`s for
these values, defaulted to today's HIL values (so HIL/CI behavior is unchanged by
default). Do not create `robot_launch.py` as a separate file** — the real robot's
container invokes the same launch file with different argument values. This is the
most literal form of "HIL should match the real robot as closely as possible": not
just the same shape, the same file.

### Unified container entrypoint — used identically by HIL and the real robot

One entrypoint script, one behavior, in both contexts:

1. Launch `nav2_only_launch.py` (EKF + `ball_detector` + Nav2 bringup), with launch
   arguments appropriate to context (HIL defaults vs. real-robot values above).
2. Wait for "Managed nodes are active" ×2.
3. Run `tools.mission2_day`'s full day loop (`no_ball` → `yellow` → `red`), with
   `--ball-ops {sim,operator}` as the one context-dependent flag.
4. Exit. One-shot `docker run` in both cases — no long-lived container, no
   `docker exec`-per-scenario.

**The container never places a ball, in either context** — `SimBallOps` (existing,
calls Gazebo's `spawn_ball`/`remove_ball` service) handles it automatically for HIL;
`OperatorBallOps` (existing, no prompting) leaves it to the human for the real robot.
This was explicit from Mike: ball placement is sim's job or the human's job, never
the container's.

### HIL orchestration restructuring (the biggest single piece of rework here)

Today, the workstation drives the whole day: `JetsonExecutor`/`hil_stage.sh` dispatch
each of the 3 scenarios to the Jetson individually over SSH, with judging/
telemetry/ball-choreography logic living on the workstation side.

**Under this design, that flips**: the workstation's HIL role shrinks to `sim_up()`
(Gazebo only, so there's a world for the robot to perceive/navigate in). The Jetson's
own container runs the entire day autonomously — identical to how the real robot
does it — with `mission2_day`'s existing `SimBallOps` reaching back to the
workstation's Gazebo instance over the (now-fixed) DDS link to place/remove balls.
`JetsonExecutor`'s per-scenario SSH dispatch goes away, replaced by triggering the
container's one full-day run and waiting on its result.

This is flagged explicitly as the largest, most invasive change in this design — it
restructures where HIL's day-loop orchestration lives, not just where Nav2 runs.

## DDS / CycloneDDS multicast fix

No new mechanism — `regen_cyclonedds_config.sh` (hardened 2026-07-31, proven through
the first fully-green HIL run) is reused as-is. The one concrete gap closed:

- **Write the regenerated config to a fixed, non-user-specific path** (not
  `$HOME`-relative — a container's default `$HOME` is `/root`, not `/home/mike`,
  which would silently break the "same file" assumption unless `HOME` is pinned
  explicitly for the container too).
- **Actually pass `-e CYCLONEDDS_URI=...` plus the bind mount into `docker run`** —
  today's mission container (`mission2_day.py`) never does this at all, silently
  relying on CycloneDDS's raw auto-selection instead of the regenerated config every
  bare process already uses. This was safe only because the container hosted just
  `mission_runner` (a light DDS participant); it becomes load-bearing once the
  container hosts the whole brain.

No discovery-server/static-peer-list, no Zenoh — not justified without a concrete
remaining failure once the above gap is closed. Documented as a fallback path if
multicast issues recur, not built now.

## Image deployment model

The Jetson **is** the self-hosted HIL runner (confirmed: one Jetson, no second CI
runner — this same physical box gets transplanted into the robot chassis). Whatever
image is already sitting in its local `docker images` cache after the last green CI
run (`stage-3-arm64` build, validated by `stage-4-hil`) is the image the robot runs —
no `docker pull`, no tag scheme, no deploy-time fetch of any kind. Consistent with the
robot needing no network access after WiFi associates.

## Inference

Two distinct things, not to be conflated:

- **What ships now, unchanged in mechanism:** the "what is this picture of" call
  originates from inside the container, but Ollama itself — the model server
  process, the model weights, the GPU/CUDA execution — stays bare-metal on the
  Jetson, exactly as it runs today. The container holds no model weights and never
  talks to the GPU for this; it's purely a network client making a `localhost` call
  (free via `--network host`) to the same bare Ollama process. Mechanically
  identical to today's VLM-canary path, just relocated from SSH-dispatched-to-Jetson
  into in-container — only the caller moved, not the model or the server. The
  inference client module is named/structured generically (not "VLM canary"
  specifically), since the forward-looking goal is broader navigation/object-
  detection support, not just the existing canary — "most likely using Ollama" per
  Mike, but not exclusively scoped to today's one use case.
- **What's genuinely deferred:** whether some future R2 capability needs to bypass
  Ollama entirely (a custom-trained model served via our own GPU-accessing code
  in-container, rather than through Ollama's API). Not a live requirement today, so
  no mechanism is chosen for it. GPU passthrough is confirmed available
  (`nvidia-container-toolkit` + Docker's `nvidia` runtime already configured) if this
  is ever needed — no setup blocker, just an unmade decision, correctly left unmade
  until a concrete requirement exists.

## Rollout / testing plan

Matches the existing safety pattern already established in `RealRobotStartup.md` —
manual verification before automation, at every layer:

1. Extend `nav2_only_launch.py` with the three new launch arguments; verify HIL's
   existing behavior is unchanged (defaults preserve current values).
2. Build the unified container entrypoint; verify manually on the Jetson, real-robot
   context, over SSH, before wiring into `robot-mission.service`.
3. Restructure HIL orchestration (workstation shrinks to `sim_up()`, Jetson container
   runs the full day); verify via a manual HIL run before merging into CI.
4. Only once both contexts are manually proven: update `stage-4-hil` in CI, and
   install `robot-mission.service` pointing at the container path.
5. `robot-mission.service` gains `After=docker.service`/`Requires=docker.service`
   alongside its existing `network-online.target` wait.

## Explicitly out of scope for this design

- The exact inference-serving mechanism beyond Ollama (deferred, see above).
- The `jetson.local` mDNS resolution regression noticed mid-session (parked,
  unrelated to this design).
- Whether `living_room.yaml` and `bedroom_real.yaml` represent geometrically
  equivalent spaces — irrelevant to this design (they're interchangeable as a launch
  argument regardless), but worth knowing before assuming HIL and real-robot runs are
  testing the same physical layout.

## Known implementation-time risks, not yet resolved

- `tools/mission2_day.py`'s executor abstraction (`InProcessExecutor`/
  `JetsonExecutor`) was built around "workstation dispatches to Jetson." Making the
  Jetson's own container self-orchestrate the full day (both `--ball-ops sim` and
  `--ball-ops operator`, invoked locally, no SSH) needs verification that this code
  path already exists or needs extending — not traced in this design session, real
  work for the implementation plan.
- `regen_cyclonedds_config.sh`'s fixed-path change and the container's `HOME`
  override need to be verified together, live, before trusting them silently.
