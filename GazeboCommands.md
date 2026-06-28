# Gazebo Harmonic — Viewer Cheat Sheet

Gazebo Harmonic uses **gz sim** (not the old `ign gazebo`). The 3D viewport
is an orbiting camera — you spin around a focal point, not a first-person walker.

---

## Mouse controls (3D viewport)

| Action | Mouse gesture |
|---|---|
| **Rotate** view | Left-click + drag |
| **Pan** (slide left/right/up/down) | Middle-click + drag |
| **Zoom** in / out | Scroll wheel |
| **Zoom** (alternate) | Right-click + drag up/down |
| **Select** an object/entity | Left-click on it |
| **Focus** camera on selection | Left-click entity, then press **F** |
| **Orbit** around a point | Left-click a surface, then drag while holding the click |

> **Tip — losing your way?** Press **F** after clicking the robot to re-center the view on it.

---

## Keyboard shortcuts

| Key | Action |
|---|---|
| **Space** | Play / Pause simulation |
| **F** | Focus camera on selected entity |
| **Escape** | Deselect / cancel current tool |
| **Ctrl + Z** | Undo last transform (move/rotate) |

---

## Simulation control (toolbar, top of window)

| Button | What it does |
|---|---|
| ▶ / ⏸ | Play / Pause (same as Space) |
| ⏭ | Step one physics step forward (useful for debugging) |
| ↺ | Reset simulation to t=0 |

The sim clock is shown next to those buttons. Pausing does NOT kill the ROS2 bridge —
topics stay connected but stop publishing until you resume.

---

## Entity tree (left panel)

Lists every model in the world. Click a name to select it in the viewport.
Right-click an entity → **Move To** to fly the camera directly to it.

---

## Coming next (will add as needed)

- Applying forces / torques for disturbance testing
- Adding/removing models at runtime via `gz service`
- Recording a video from the Gazebo viewport
- Headless rendering flags for CI runs
