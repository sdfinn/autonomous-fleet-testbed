# BLUEPRINT.md — Master Strategic Brief

**This is the working strategic brief for autonomous-fleet-testbed. Read it for direction; execute from `Release1Todo.md`.**

## Document map (what to read, what to build from)

| Document | Role | Build from it? |
|---|---|---|
| **BLUEPRINT.md** (this file) | Master strategic brief — vision, roadmap, career framing, decisions | No — sets direction |
| `robotics_cicd_10x_blueprint.md` | Source strategic dialogue (10x / VC brainstorm) | **No — reference only** |
| `Release1Todo.md` | Session-by-session execution plan | **Yes — tasks come from here** |
| `.superpowers/sdd/` specs | Per-feature design specs | **Yes — code comes from here** |
| `config/drift_config.yaml`, `robot_profiles/*.yaml`, `requirements/traceability.yaml` | Data-driven config | Yes — behavior is data, not code |

We do **not** code directly from either strategy doc. Strategy sets the "why"; session plans and SDD specs set the "what" and "how."

---

## The project in one line

A CI/CD-native, **local-first** testing framework for autonomous robots that brings 20 years of enterprise release discipline to a field full of brilliant ML/hardware engineers who lack it — and layers an **AI agentic test-and-heal loop** plus **automated sim-to-real alignment** on top.

## Two products (independently demoable, mutually reinforcing)

1. **Fleet CI/CD Pipeline Framework** — "How do you know your robot software works before it touches hardware?" Robot-agnostic, open-source-ready. Lives in `tools/` + `.github/workflows/`.
2. **AI Autonomous Mission Planner** — "How do you tell a fleet what to do and prove they can do it?" Scripted in R1, AI-driven later. Lives in `src/nav_fleet/` (+ future `mission_planner/`).

The pipeline validates the planner; the planner generates the scenarios the pipeline tests.

---

## Career context — the actual optimization target

- **Who:** Mike, 66, Principal Test Engineer with 20 years in enterprise automation, test pipelines, CI/CD, and release management (call-center software). Building this at home.
- **Goal:** Within ~6 months, have a portfolio artifact strong enough to (a) transition out of call-center software into a **Principal AI Infrastructure / MLOps** role in robotics-adjacent industry, and/or (b) seed a product on the side while still employed. Leverage the experience card, not the youth card.
- **Honest monetization read (VC/startup hat):**
  - Classic VC rocketship, solo, at 66 → low probability. Not the bet to optimize for.
  - **High-credibility paths:** commercial open-source (Temporal/Tailscale/Sidero model) and **founding-architect / principal-infra** roles. The 20-year release-discipline background is a genuine, nameable moat in a field starved for it.
  - **Highest risk-adjusted outcome:** a polished open-source artifact + a metrics-driven technical write-up that lands a principal role — possibly while keeping the day job until something concrete lands.
  - The job artifact, the OSS project, and the product seed are **the same deliverable.** No effort split.

---

## The core strategic insight: two axes, optimize the right one

There are two ways to grow this project. They are different axes:

- **Robot ambition ladder** (the original R1→R3B plan): 1 robot → fleet → drone → autonomous missions. Adds *hardware and coordination complexity.*
- **Infrastructure value ladder** (the 10x blueprint): cloud/local orchestration → generative scenarios → hardware-in-the-loop, wrapped in an agentic self-healing loop and local-first economics.

**The differentiator — and the career/product value — lives on the infrastructure axis.** Adding a second robot or a drone does little for a hiring director or investor. Proving an **agentic test-and-heal loop** + **automated sim-to-real alignment** on a *single rover*, on a *$3K workstation*, with *reproducible cost numbers*, is the thing nobody else has packaged. Multi-robot/drone work is a **demo flourish**, not the core value.

Consequence: **the roadmap is reprioritized.** The agentic/alignment layer (R4) is pulled *before* the multi-robot ladder (R2/R3).

---

## Revised roadmap

```
R1  (current)   Finish the 6-stage pipeline in sim, single rover → Showcase Moment 1
                Stage 4 / Isaac Sim = reserved slot, NOT built (see Simulation Tiers)

R4  (NEXT after R1)   The Agentic & Alignment Layer — THE differentiator
                Pillars: agentic test/heal · sim-to-real alignment · generative worlds
                Outputs: local-throughput benchmark · positioning write-up

R2 / R3  (OPTIONAL, demo flourish)   Multi-robot · drone · autonomous missions
                Pulled forward only if a specific role/customer/demo demands it

Stage 4 / Isaac Sim   Fidelity tier — drops into reserved slot when perception matters
```

| Release | Robot composition | Mission style | Intelligence layer | Priority |
|---|---|---|---|---|
| R1 (current) | 1 Jetson Orin Nano (sim + real) | Scripted: navigate, sweep, stop/avoid | Drift detection + AI test generation | **Active** |
| **R4** | Same single rover | Same scripted missions | **Agentic test/heal + sim-to-real alignment + generative worlds** | **Next** |
| R2 | 1 Jetson + 1–2 cheaper robots | Coordinated search | Multi-robot coordination | Optional |
| R3A | Add drone | More autonomous | Aerial + ground coordination | Optional |
| R3B | Any fleet | Fully autonomous ("go find the red ball") | AI-defined missions, parallel sim | Optional |

---

## R4 — The Agentic & Alignment Layer (the differentiator)

**Three pillars:**

1. **Closed-loop agentic test/heal** — on **3 named failure modes** (candidates: nav collision, odom Hz drop, sim-to-real drift breach). Claude detects the invariant violation, diagnoses from telemetry, and **proposes** a fix. **Human-in-the-loop approval.** This is the blueprint's Part 4 loop, scoped honestly.
2. **Automated sim-to-real alignment** (the "monkey") — ingest real rover/Jetson telemetry, auto-tune domain-randomization params so the sim tracks reality. `sim_vs_real_comparison.py` is the seed; the *auto-tuning* is the new work.
3. **Generative scenario → real world** — NL prompt ("dense clutter, low light") → actual Gazebo SDF, not just the JSON scenario descriptions `ai_test_generator.py` produces today.

**Two outputs (these ARE the career assets):**

4. **Local-first benchmark** — "N robot-hours validated, $0 cloud spend, one RTX 5080," reproducible.
5. **Positioning write-up** — "20 years of enterprise release engineering meets physical AI."

**⚠️ Credibility discipline (non-negotiable):** Ship and demo the **human-in-the-loop** version of the agentic loop. *Frame* full unattended autonomy as the roadmap, do not claim it. Full autonomy-until-SLA is research-grade and cherry-pickable; claiming it before it's robust will get caught by exactly the technical buyers we target. **Under-claim, over-deliver.**

---

## The local-first economics wedge

The sharpest, most-unique angle: **enterprise-grade agentic robot CI without a cloud bill.** RTX 5080 (Blackwell, FP4/FP8), 96 GB RAM, Jetson Orin Nano for real HIL. The message: *"Eliminate ballooning cloud R&D costs — bring disciplined agentic automation local, deliver hardware-verified binaries to the edge."* This is a first-class, **measured, marketed** feature — captured by R4 output #4, not an afterthought.

## Simulation tiers: throughput vs. fidelity

Two tiers, complementary — not competitors:

- **Throughput / economics tier → Gazebo Harmonic headless.** Cheap, parallel, "100 robot-hours for $0." Drives the local-first story. Built in R1/R4.
- **Fidelity tier → Isaac Sim (Stage 4).** Photorealistic perception (YOLO mAP) when a customer/role demands it. **Deferred-and-positioned**, not deferred-and-forgotten.

**Isaac Sim decision (2026-06-27):** Deferred from R1 on **priority grounds, not difficulty.** (Mike has run Isaac Sim on Windows + ROS2-on-WSL; bare-metal Ubuntu is doable and faster — setup is not the blocker.) Stage 4 stays a **reserved, designed slot** in the 6-stage pipeline; CI keeps a clean stub/skip so it drops in later with no rework. Offering *both* tiers (developer picks per-PR) is a stronger, "enterprise tiering discipline" story than either alone — exactly the kind of thing the experience card articulates that ML-heavy teams won't.

---

## Showcase moments

1. **Moment 1 (R1):** Single rover in sim + real doing the same mission; drift detection visible. 1–2 min video.
2. **Moment "R4" (the real differentiator):** Agentic loop catches an injected regression, diagnoses it from telemetry, proposes a fix (human approves), sim-to-real alignment shown tracking; plus the local-first benchmark number on screen. **This is the demo that lands the role / opens the pitch.**
3. **Moment 2 (R2, optional):** 1 smart + 1–2 cheap robots, coordinated mission.
4. **Moment 3A/3B (R3, optional):** Drone added / "brains demo" — pipeline defines and runs its own test missions.

## Design principles (preserve across all releases)

- **Data-driven:** thresholds, requirements, profiles in YAML — never hardcoded in Python.
- **Robot-agnostic:** tools know nothing about specific robots; profiles declare capabilities.
- **Shift left:** catch bugs in sim before hardware; generate scenarios to find more bugs sooner.
- **Pipeline as product:** the CI/CD pipeline IS the deliverable, not just a quality gate.
- **Under-claim, over-deliver:** especially on agentic autonomy.

---

## Decisions log

- **2026-06-27 — Roadmap reprioritized.** R4 (Agentic & Alignment Layer) pulled *before* R2/R3. Rationale: the differentiator and all career/product value live on the infrastructure axis, not the robot-ambition axis. R2/R3 become optional demo flourishes.
- **2026-06-27 — Isaac Sim / Stage 4 deferred-and-positioned.** Reserved slot in the 6-stage pipeline; reframed as the "fidelity tier" alongside Gazebo's "throughput tier." Deferred on priority, not difficulty. Affects `Release1Todo.md` session 12 only.
- **2026-06-27 — Agentic loop scoped to human-in-the-loop for portfolio/demo.** Full unattended autonomy is roadmap, not a claim.
- **2026-06-27 — BLUEPRINT.md created** as the master brief; `robotics_cicd_10x_blueprint.md` retained as reference-only source dialogue. CLAUDE.md pointer corrected.
