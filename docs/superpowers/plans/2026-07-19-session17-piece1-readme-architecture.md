# Session 17 Piece 1 — README + Architecture Diagram Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A stranger clones the repo, works through a new lean `README.md`, and ends
with a working local pipeline; the repo gains an as-built interactive architecture
diagram at `docs/architecture.html`.

**Architecture:** Two documentation deliverables plus their image assets. The README
links out for depth (Jetson runbook, roadmap, architecture). The HTML diagram keeps
the existing `rover_cicd_architecture.html` skin (SVG flow + click-to-expand `NODES`
dict) with all content rewritten from the real `ci.yml` / `hil_stage.sh`.

**Tech Stack:** Markdown + Mermaid (GitHub-native render), single-file HTML/SVG/JS,
Playwright for click-testing, live shell for command verification.

**Spec:** `docs/superpowers/specs/2026-07-19-session17-piece1-readme-architecture-design.md`

## Global Constraints

- COPY `rover_cicd_architecture.html` → `docs/architecture.html`; the original is
  deleted only after Mike signs off on the new one (spec).
- Every README command must be executed for real before commit (Tier-1 rule).
- **Push discipline:** pushing fires stage-2 Gazebo on the workstation runner —
  pushing and local sim work are mutually exclusive. All sim-dependent tasks finish
  and tear down BEFORE the single end-of-piece push.
- `reports/photos/` stays untracked; README images live in `docs/img/`.
- Requirement IDs in the diagram only where they exist in
  `requirements/traceability.yaml`.
- LICENSE, Pages hosting, two-machine walkthrough: out of scope (spec "parked").

---

### Task 1: Visual assets → `docs/img/`

**Files:**
- Create: `docs/img/gazebo_bedroom_world.png` (viewer screenshot)
- Create: `docs/img/mission2_reaction_yellow.png` (robot-camera photo, copied from
  `reports/photos/`)

**Interfaces:**
- Produces: the two image paths above, referenced verbatim by Task 3's README.

- [ ] **Step 1: Bring the sim up and open the viewer** — `scripts/hil_stage.sh`-free
  local launch: `ros2 launch src/nav_fleet/launch/sim_only_launch.py` backgrounded,
  then the scrubbed-env `gz sim -g` recipe (CLAUDE.md snap/glibc workaround). Wait for
  the bedroom world to render.
- [ ] **Step 2: Screenshot the viewer window** — `import -window "$(xdotool search
  --name 'Gazebo' | head -1)" docs/img/gazebo_bedroom_world.png` (fallback: full-root
  `import` + crop with `convert -crop`). Read the PNG to verify: bedroom geometry,
  robot visible, not a black/blank frame (llvmpipe warm-up — retake after 5 s if so).
- [ ] **Step 3: Pick the mission photo** — newest
  `reports/photos/mission2_reaction_yellow_*.png`; Read it to confirm the yellow ball
  is in frame; `cp` into `docs/img/mission2_reaction_yellow.png`.
- [ ] **Step 4: Tear the sim down** — Ctrl-C equivalent: kill the launch process
  group, then verify with the full orphan pattern
  (`pgrep -af "gz sim|component_container|robot_state_publisher|ros2 launch|parameter_bridge|static_transform|ekf_node"`).
- [ ] **Step 5: Commit (no push)** — `git add docs/img && git commit -m "docs(img):
  Gazebo world screenshot + Mission 2 reaction photo for README"`.

### Task 2: `docs/architecture.html` — as-built rewrite in the same skin

**Files:**
- Create: `docs/architecture.html` (starts as a copy: `cp rover_cicd_architecture.html
  docs/architecture.html`)
- Read (sources of truth): `.github/workflows/ci.yml`, `scripts/hil_stage.sh`,
  `requirements/traceability.yaml`, `tools/baseline_monitor.py`, `tools/mission2_day.py`

**Interfaces:**
- Produces: `docs/architecture.html`, linked verbatim from Task 3's README.

- [ ] **Step 1: Copy the file** (constraint: original untouched).
- [ ] **Step 2: Rewrite header + badges** — title "autonomous-fleet-testbed — CI/CD &
  Autonomy Architecture"; badges: Ubuntu 24.04 · ROS2 Jazzy · Gazebo Harmonic ·
  Jetson Orin Nano (self-hosted runner) · RTX 5080 (self-hosted runner) · Waveshare
  UGV PT (on order). Subtitle keeps the "click any node" instruction.
- [ ] **Step 3: Rewrite the SVG stage flow** to the as-built pipeline, one block per
  stage, three nodes per stage (keep geometry; adjust labels):
  - Trigger: push to main / PR to main (paths-filter: docs-only skips 3–4).
  - Stage 0 — traceability gate: `check_traceability.py` · BR requirements ·
    known-gap note (BR-03 `continue-on-error`).
  - Stage 1 — code quality (hosted runner): ament lint · pytest unit suite ·
    live-ROS tests ignored here (the twice-bitten gotcha).
  - Stage 2 — Gazebo Harmonic headless (x86 GPU runner): sim+Nav2 stack · nav
    integration tests (BR-01/BR-02/BR-10 from traceability.yaml) · telemetry →
    FLEET_DB + drift gate.
  - Stage 3 — arm64 native build (Jetson runner): docker build on-device ·
    registry layer cache (buildcache-v2, 659 s cold / ~52 s warm) · GHCR image
    tagged by sha.
  - Stage 4 — HIL (x86 sim ↔ real Jetson Nav2): `hil_stage.sh` stack gate ·
    Mission 2 day (no_ball → yellow → red, container at 15W) · evidence artifact
    (photos, day outs, Jetson Nav2 log).
  - Stage 5 — reports split: Workstation Reports · HIL Reports (runs on stage-4
    failure too) · Streamlit dashboard + PDF.
  - Stage 6 — real-robot deploy: kept, visually FUTURE (dashed stroke + "FUTURE —
    Session 18" label).
- [ ] **Step 4: Rewrite all `NODES` panels** to match Step 3's nodes — every panel's
  body/code/items sourced from the named source-of-truth files (real commands, real
  file paths, real thresholds); delete ESP32/micro-ROS/YOLO/QEMU/Isaac-CI panels;
  keep only requirement IDs present in `requirements/traceability.yaml`; drift panel
  describes SQLite FLEET_DB + (runner_type, power_mode) baseline slicing; concurrency
  group noted on the trigger panel.
- [ ] **Step 5: Click-test with Playwright** — open `file:///home/mike/autonomous-fleet-testbed/docs/architecture.html`,
  click every node id, assert the detail panel populates and the console has no
  errors; take one screenshot for the record.
- [ ] **Step 6: Commit (no push)** — `git add docs/architecture.html && git commit -m
  "docs(architecture): as-built interactive diagram — copy of rover_cicd skin, content
  rewritten from ci.yml"`.

### Task 3: `README.md`

**Files:**
- Create: `README.md`
- Read: `CLAUDE.md` (commands), `docs/runbooks/JetsonInstallSession14.md` (link
  target), `GazeboCommands.md`, `Release1Todo.md`, `BLUEPRINT.md` (link targets)

**Interfaces:**
- Consumes: `docs/img/*.png` (Task 1), `docs/architecture.html` (Task 2).

- [ ] **Step 1: Write README.md** with exactly the spec's eight sections. Fixed
  elements:
  - Badge: `![CI](https://github.com/sdfinn/autonomous-fleet-testbed/actions/workflows/ci.yml/badge.svg)`
  - Mermaid (verbatim):
    ```mermaid
    flowchart TD
        T["push to main / PR"] --> S0["Stage 0\ntraceability gate"]
        S0 --> S1["Stage 1\nlint + unit tests"]
        S1 --> S2["Stage 2\nGazebo sim nav tests\n(x86 GPU runner)"]
        S2 --> S3["Stage 3\nnative arm64 build\n(Jetson runner)"]
        S3 --> S4["Stage 4\nhardware-in-the-loop\nMission 2 day (real Jetson)"]
        S2 --> S5a["Stage 5\nworkstation reports"]
        S4 --> S5b["Stage 5\nHIL reports"]
        S4 -.-> S6["Stage 6\nreal-robot deploy\n(future)"]
    ```
  - Quickstart commands = CLAUDE.md's Tier-1 block (build, pytest with the four
    ignores, `sim_launch.py`, `python -m nav_fleet.mission_runner mission1`,
    `streamlit run dashboard/app.py`).
  - From-scratch section: Ubuntu 24.04 → ROS2 Jazzy install → Gazebo Harmonic →
    CycloneDDS + `ROS_LOCALHOST_ONLY=1` note for Jetson-less machines → venv +
    `requirements.txt` caveat (`requirements-ci.txt` is the reproducible one) →
    clone/build/verify, each with a "you should see" line.
- [ ] **Step 2: Verify every command live** — fresh shell: `colcon build`, the pytest
  line, sim launch, `mission1` run (with `ROS_LOCALHOST_ONLY=1` if the Jetson is
  off), dashboard startup (curl the Streamlit port, then kill). Fix any README text
  that doesn't match observed output.
- [ ] **Step 3: Tear down + orphan-pattern check** (same pattern as Task 1 Step 4).
- [ ] **Step 4: Link check** — every relative link in README resolves
  (`ls` each target); image paths exist.
- [ ] **Step 5: Commit (no push)** — `git add README.md && git commit -m "docs: README
  — quickstart, from-scratch setup, architecture links (Session 17 Piece 1)"`.

### Task 4: Push + rendered verification + sign-off handoff

- [ ] **Step 1: Confirm machines idle** (orphan pattern clean, no CI in flight:
  `gh run list -L1`) then `git push origin main` (one push for the whole piece).
- [ ] **Step 2: Watch the CI run** (background `gh run watch`) — docs-only push ⇒
  light pipeline; expect green.
- [ ] **Step 3: Ask Mike to eyeball** the rendered README on GitHub (mermaid renders
  client-side — can't be asserted from here) and click through
  `docs/architecture.html` locally.
- [ ] **Step 4: On Mike's sign-off** — `git rm rover_cicd_architecture.html`, commit
  `"docs: retire pre-project architecture diagram (superseded by docs/architecture.html)"`,
  push. NOT before.

## Self-review

Spec coverage: README §1–8 → Task 3; diagram copy/rewrite/click-test → Task 2; images
→ Task 1; command verification → Task 3 Step 2; link check → Task 3 Step 4; mermaid
GitHub check → Task 4 Step 3 (human — client-side render); old-file retirement gated
on sign-off → Task 4 Step 4. Placeholders: none — panel content is enumerated per
node with named sources. Types/interfaces: image paths and architecture link used in
Task 3 match Task 1/2 outputs.
