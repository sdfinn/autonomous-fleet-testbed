# Next Steps — ROS2 Rover CI/CD Project

## Decisions Made (Session: 2026-06-17)

### Q: Start blank project or copy the Jetbot/Isaac Sim project?

**Decision: Fresh start (new directory), cherry-pick ~5 specific files.**

The existing project is ~70% Isaac Sim-specific code (launch_scene.py, nav_controller.py, OmniGraph nodes, USD scene setup) that becomes dead weight. The new project has a fundamentally different shape — Gazebo Harmonic as primary CI gate, ESP32 firmware layer, Docker arm64 image build, actual Jetson deployment.

Files to consciously port (not copy blindly — clean up Windows/WSL2 path assumptions):
- `src/baseline_monitor.py` — port the rolling-window drift logic; metric schema changes but algorithm reusable
- `dashboard/app.py` — Streamlit structure fine, swap the data model
- `src/ai_test_generator.py` — Claude API scenario generation translates directly
- `.github/workflows/` — copy skeleton, gut Isaac Sim steps, rebuild per 6-stage guide
- `tests/test_baseline.py` — pytest structure patterns

### Q: Ubuntu dual boot or stay on Windows/WSL2?

**Decision: Dual boot Ubuntu 24.04 bare metal.**

Everything flows from this. Gazebo Harmonic, Isaac Sim with RTX 5080, ROS2 Jazzy native — all require Ubuntu bare metal. The old WSL2 rsync workflow and Windows paths in CLAUDE.md do not carry over.

**Action: Set up Ubuntu 24.04 dual boot before writing a line of project code.**

### Q: Physical rover (Waveshare UGV Rover PT) — purchase now?

**Decision: No. Get as far as possible in sim first.**

Phasing:

| Phase | Stages | What it proves | Hardware needed |
|---|---|---|---|
| 1 | 0–3 | Requirements discipline + Gazebo CI gate + drift detection | None |
| 2 | 4 | Isaac Sim RTX perception validation | None (RTX 5080) |
| 3 | 5 | Reports, artifacts, ghcr.io image publish | None |
| 4 | 6 | Deploy YAML + smoke test scaffolding | None (placeholder) |
| Later | 6 live | Actual Jetson deploy | Rover purchase |

Stage 6 is written fully (GitHub Actions YAML, docker-compose.yml, SSH deploy + rollback logic) and documented as hardware-ready. README notes hardware pending. This is credible for employers.

### Q: Primary purpose of the new project?

**Decision: Portfolio first, business second.**

- v1: Follow the guide faithfully — clean, correct, conventional. Tag as `v1.0-portfolio` when complete.
- v2: Explicit 10x architectural upgrade, documented in `CHANGELOG.md` or `ARCHITECTURE_V2.md`.
- The diff between v1 and v2 is the product pitch for a potential business.

---

## Structural Decisions for v1 (keep clean for v2 transition)

These are NOT things to implement in v1 — just keep them clean enough to refactor:

1. **Sim-result schema in one place.** Keep Gazebo output parsing in a single function (`parse_gazebo_result()`). Becomes the adapter interface in v2 when Isaac Sim results need to feed the same downstream logic.

2. **Drift thresholds as data.** Put thresholds in `drift_config.yaml` from day 1. Zero extra logic. In v2, this is what makes `drift_detector.py` a generic CLI across robot types.

3. **`check_traceability.py` as zero-rover logic.** Takes `--requirements` and `--test-results` as CLI args. Knows nothing about the Waveshare UGV. Ships as-is into the open-source package in v2.

4. **Tag v1 before starting v2.** `git tag v1.0-portfolio` when portfolio version is complete. The tag anchors the before/after narrative for both employers and the product pitch.

---

## Reference Docs

| File | Purpose |
|---|---|
| `G:\BC\ros2_rover_cicd_guide.pdf` | Full 6-stage pipeline guide (v2, JetPack 7.2) |
| `G:\BC\rover_cicd_architecture.html` | Interactive architecture diagram |
| `G:\BC\rover_cicd_10x_notes.pdf` | 10x rethink + open-core business model notes |
