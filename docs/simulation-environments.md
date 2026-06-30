# Simulation Environments — Gazebo vs Isaac Sim

This project uses two simulation environments at different stages of the pipeline.
They serve different purposes and are complementary, not redundant.

## Comparison

| | Gazebo Harmonic | Isaac Sim 5.x |
|---|---|---|
| **Cost** | Free, open source | Free (Omniverse), requires RTX GPU |
| **Startup time** | ~5 seconds | 2–5 minutes (+ 30 min shader compile on first launch) |
| **Physics engine** | ODE / Bullet — adequate for Nav2 flat-floor driving | PhysX 5 — accurate wheel-terrain contact, realistic inertia |
| **Sensor fidelity** | Good lidar / IMU / basic camera | Ray-traced depth, photorealistic RGB, synthetic ML training data |
| **CI cost** | Runs on self-hosted GPU runner (same workstation) | Requires self-hosted GPU runner (RTX class) |
| **ROS2 integration** | Native via ros_gz_bridge | ROS2 bridge via Isaac Sim Extension |
| **World format** | SDF (XML) | USD (Omniverse) |
| **Sim-to-real transfer** | Good enough for Nav2 differential-drive navigation | Better for perception / ML model alignment |
| **Primary use** | Fast nav regression testing, CI feedback loop | High-fidelity sensor validation before real hardware deploy |
| **Business signal** | "Fast, cheap feedback — 100 robot-hours for $0 cloud cost" | "High-fidelity validation before deploying to $50K hardware" |

## Why Both?

A mature robotics pipeline uses simulation at multiple fidelity levels:

- **Gazebo** catches navigation regressions in seconds per run. It is the inner CI loop —
  every push triggers a nav test, checks position error and collision rate, and reports
  back in under 2 minutes. Low cost, high iteration speed.

- **Isaac Sim** validates sensor data quality and physics accuracy before trusting the
  results on the real robot. Camera depth, synthetic training data for perception models,
  and realistic wheel dynamics all require Isaac-level fidelity.

Running both in the same pipeline demonstrates understanding that different test tiers
have different costs and purposes — something most robotics teams do not have packaged.

## Pipeline Position

```
Push → requirements gate → lint → arm64 build → Gazebo nav test → Isaac validation → reports
                                                   (fast, every push)   (slower, self-hosted GPU)
```

Both Gazebo and Isaac run on the same self-hosted runner (RTX 5080 workstation).
This eliminates cloud GPU costs entirely — the hardware is already owned.

## Self-Hosted Runner

The workstation (RTX 5080, 16 GB VRAM, CUDA 13.2) is registered as a GitHub Actions
self-hosted runner with labels `[self-hosted, x86, gpu, rtx5080]`. Both Gazebo
(OGRE2 renderer) and Isaac Sim use the GPU directly. No Xvfb or software rendering needed.
