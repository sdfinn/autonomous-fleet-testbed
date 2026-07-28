---
name: isaac-gui-nav-test
description: Use when running a manual GUI-watched Isaac Sim navigation test in this repo (autonomous-fleet-testbed) — the 3-terminal Isaac + Nav2 + pytest procedure from Session 12+. Migrated from the root CLAUDE.md by /doctor on 2026-07-27.
---

# Isaac GUI Nav Test — Terminal Procedure (Session 12+)

Three terminals. **Do not start Nav2 more than ~5s after Isaac is ready** (DDS TF history grows
with every second Isaac runs; a late Nav2 startup gets thousands of replayed messages).

**Terminal 1 — Isaac (start first):**
```bash
# New terminal (auto-sources from .bashrc)
cd ~/autonomous-fleet-testbed
colcon build --symlink-install && source install/setup.bash
DISPLAY=:0 OMNI_KIT_ACCEPT_EULA=YES PYTHONUNBUFFERED=1 python -u scripts/isaac_bedroom_gui.py
```
Wait for: `[Isaac] *** Simulation running ***`

**Terminal 2 — Nav2 (start IMMEDIATELY after Terminal 1 is ready):**
```bash
# New terminal
cd ~/autonomous-fleet-testbed
ros2 launch src/nav_fleet/launch/nav2_isaac_launch.py
```
Wait for: `Managed nodes are active` and `Setting pose … -1.276 1.200 1.571`

**Terminal 3 — Test:**
```bash
# New terminal
cd ~/autonomous-fleet-testbed
python -m pytest tests/test_navigation.py::test_navigation_succeeds -v --timeout=120
```

**Optional Terminal 4 — Monitor AMCL (run after Nav2 active):**
```bash
ros2 topic echo /robot_001/amcl_pose
```

**Between runs:** `pkill -9 -f "isaac_bedroom|component_container_isolated|robot_state_publisher"`
then wait 5s for DDS to clear before restarting.

See `scripts/CLAUDE.md` for the underlying Isaac Sim gotchas this procedure works around.
