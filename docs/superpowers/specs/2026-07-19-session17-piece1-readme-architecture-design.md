# Session 17 Piece 1 — README + Architecture Diagram (design)

**Date:** 2026-07-19 · **Approved by:** Mike (conversation, 2026-07-19)
**Goal / success criterion:** a stranger clones the repo, works through the README top
to bottom, and ends with a working local pipeline. Lean README; depth lives in linked
docs.

## Deliverable 1 — `README.md` (repo root; currently none exists)

Target ~150 lines. Every command verified by actually running it before commit.

1. **Header:** project title; one paragraph — CI/CD-native fleet simulation testing
   framework for autonomous robots: sim-first testing, telemetry + drift detection,
   real-Jetson hardware-in-the-loop. CI status badge (GitHub Actions, main).
2. **Visuals:** one Gazebo bedroom-world screenshot + one robot-camera mission photo,
   stored under `docs/img/` (repo-tracked; `reports/photos/` stays untracked).
3. **Architecture:** Mermaid diagram of the six CI stages as built (GitHub renders
   natively), then: "Full clickable architecture: `docs/architecture.html` — open
   locally in a browser." (Private repo ⇒ no Pages/preview; revisit at repo-public.)
4. **Quickstart** (everything already installed): colcon build → pytest (with the
   standard ignores) → launch sim → `python -m nav_fleet.mission_runner mission1` →
   dashboard. The Tier-1 loop.
5. **Setup from scratch — workstation only:** prerequisites (Ubuntu 24.04, ROS2 Jazzy,
   Gazebo Harmonic, CycloneDDS, Python venv, colcon), ordered install steps, each with
   a "you should see…" verification checkpoint. No Jetson required for this path.
6. **Going further (links only):** Jetson/HIL tier → `docs/runbooks/JetsonInstallSession14.md`;
   Gazebo viewer → `GazeboCommands.md`; mission runbook → `docs/runbooks/Mission1HILSession15.md`;
   roadmap → `Release1Todo.md`; strategy/background → `BLUEPRINT.md`.
7. **What the CI expects:** honest note — the full pipeline assumes two self-hosted
   runners (x86 GPU workstation + Jetson Orin Nano); stages 0–1 run on GitHub-hosted
   runners, so a fork gets the quality gates with zero setup.
8. **Repo map:** short table (`src/nav_fleet`, `tools/`, `tests/`, `requirements/`,
   `config/`, `robot_profiles/`, `dashboard/`, `reports/`, `.github/workflows/`).

## Deliverable 2 — `docs/architecture.html`

**COPY** (not move) `rover_cicd_architecture.html` → `docs/architecture.html`; the
original stays untouched until Mike signs off on the new one, then gets deleted.

Keep the skin exactly: layout, palette, SVG flow, click-to-expand sticky detail panel,
`NODES` dict mechanism. Rewrite all content to as-built reality (source of truth:
`.github/workflows/ci.yml`, `scripts/hil_stage.sh`, `tools/`, `requirements/traceability.yaml`):

- Stage 0 traceability gate → Stage 1 quality (ament lint + pytest; hosted runners) →
  Stage 2 Gazebo Harmonic headless Nav2 (self-hosted x86 GPU) → Stage 3 native arm64
  build on the Jetson runner (QEMU retired) → Stage 4 HIL: Gazebo (x86) ↔ Nav2 on the
  real Jetson, Mission 2 day in the GHCR container at 15W → Stage 5 split reports
  (Workstation / HIL) → Stage 6 real-robot deploy marked **FUTURE (Session 18)**.
- Panels describe real mechanisms: SQLite `FLEET_DB` drift baselines sliced by
  runner_type/power_mode; concurrency group for shared hardware; HSV detection (no
  YOLO); container mission executor; evidence artifacts incl. the Jetson Nav2 log.
- Remove: ESP32/micro-ROS nodes and MCU-xx requirements (no firmware testing exists),
  YOLO, QEMU/buildx, Isaac-in-CI (Isaac noted only as retired/history), branch-strategy
  panel replaced by the real trigger rule (push-to-main + PRs to main).
- Requirement IDs shown only where they exist in `requirements/traceability.yaml`.
- Badges row updated to the real stack (Ubuntu 24.04, ROS2 Jazzy, Gazebo Harmonic,
  Jetson Orin Nano, RTX 5080 runner, Waveshare UGV PT — on order).
- Title loses "Rover": "autonomous-fleet-testbed — CI/CD & Autonomy Architecture".

## Verification

- All README commands executed in a fresh shell before commit (Tier-1 rule).
- Mermaid confirmed rendering on GitHub after push.
- `docs/architecture.html` opened locally and click-tested (Playwright): every node
  populates the panel, no JS errors.
- All README links resolve to files that exist.

## Out of scope / parked

- Two-machine HIL walkthrough (linked, not inlined).
- LICENSE choice → pre-public checklist.
- Hosting the interactive diagram (Pages) → repo-public time.
- Deleting `rover_cicd_architecture.html` → only after Mike's sign-off on the new one.
