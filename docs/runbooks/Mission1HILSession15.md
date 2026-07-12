# Mission 1 Hardware-in-the-Loop — Session 15 Runbook

Gazebo (world + sensors) runs on the x86 workstation; Nav2 + the mission executor (the
"robot brain" under test) run on the real Jetson Orin Nano. The two halves talk over the
existing NetworkManager-shared Ethernet link via CycloneDDS. Spec:
docs/superpowers/specs/2026-07-10-session15-gazebo-hil-mission1-design.md.

## Part 1 — One-time Jetson setup

SSH in (`ssh Mike@10.42.0.217` — if the DHCP lease moved, find it with
`ip neigh show dev enp6s0` on the workstation), then:

```bash
sudo apt install -y ros-jazzy-navigation2 ros-jazzy-nav2-bringup ros-jazzy-rmw-cyclonedds-cpp
# (during Session 15 development this was the `session-15-mission1-hil` branch —
# substitute whatever branch holds the code under test)
cd ~/autonomous-fleet-testbed && git fetch && git checkout main && git pull
# pillow is needed by nav_fleet.image_io (take_picture writes PNGs). On this board it is
# already present as the Ubuntu 24.04 system package python3-pil (PIL 10.2.0, satisfies
# >=10.0) — no pip install needed. If a fresh board lacks it, prefer `sudo apt install -y
# python3-pil` over pip: Ubuntu 24.04 is PEP-668 externally-managed and a bare
# `pip install pillow` is refused without `--break-system-packages`.
# --base-paths src is REQUIRED on the Jetson: the self-hosted CI runner lives at
# ~/autonomous-fleet-testbed/actions-runner (nested inside the repo, from Session 14 Part 8),
# and its _work/ tree holds a second checkout with its own src/nav_fleet. A bare
# `colcon build` scans the cwd recursively, finds both nav_fleet packages, and aborts with
# "Duplicate package names not supported". Scoping to src/ avoids the runner's checkout.
colcon build --symlink-install --base-paths src && source install/setup.bash
```

## Part 2 — Environment on BOTH machines (every session)

Both sides must agree on the RMW and domain. The workstation already uses CycloneDDS;
the Jetson defaults to FastDDS unless told otherwise:

```bash
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export ROS_DOMAIN_ID=0
```

(Workstation `.bashrc` already handles this; on the Jetson add both lines to `~/.bashrc`
above any interactivity guard, or export per-terminal.)

**If discovery fails** (Part 3's `ros2 topic list` on the Jetson shows nothing): multicast
may not traverse the shared link. Fall back to unicast peers — on BOTH machines, write
`~/cyclonedds-hil.xml` (substitute the current Jetson IP):

```xml
<CycloneDDS>
  <Domain>
    <General><AllowMulticast>false</AllowMulticast></General>
    <Discovery>
      <Peers>
        <Peer address="10.42.0.1"/>    <!-- workstation, shared-link gateway -->
        <Peer address="10.42.0.217"/>  <!-- Jetson (re-check the lease) -->
      </Peers>
    </Discovery>
  </Domain>
</CycloneDDS>
```

and `export CYCLONEDDS_URI=file://$HOME/cyclonedds-hil.xml` in every terminal on both sides.

## Part 3 — Run procedure (three terminals)

**Terminal 1 — workstation, sim half:**
```bash
cd ~/autonomous-fleet-testbed
ros2 launch src/nav_fleet/launch/sim_only_launch.py
```
Wait for the bridge node to start (~5 s after Gazebo). Optional viewer: `gz sim -g`.

**Terminal 2 — Jetson (SSH), sanity check then Nav2:**
```bash
cd ~/autonomous-fleet-testbed
ros2 topic hz /robot_001/scan --window 20   # expect ~10 Hz — proves DDS crosses the link
ros2 topic echo /clock --once               # proves sim time arrives
ros2 launch src/nav_fleet/launch/nav2_only_launch.py
```
Wait for `Managed nodes are active` and the AMCL initial-pose log.

**Terminal 3 — Jetson (SSH), the mission:**
```bash
cd ~/autonomous-fleet-testbed
# python3 (not python) — matches the Session 14 Jetson env (JetsonInstallSession14.md Part 7).
RUNNER_TYPE=hil_jetson python3 -m nav_fleet.mission_runner mission1
```

**Success =** `Mission mission1: PASS`, exit code 0, a PNG under `reports/photos/` on the
Jetson, and a `runs` row with `runner_type='hil_jetson'` in the Jetson's local
`reports/fleet_runs.db`. The Jetson has **no `sqlite3` CLI** — read the row with python3:
```bash
python3 -c "import sqlite3; c=sqlite3.connect('reports/fleet_runs.db'); \
  print(*c.execute('SELECT scenario,result,runner_type,sim_engine FROM runs ORDER BY id DESC LIMIT 1'))"
# -> ('mission1', 'PASS', 'hil_jetson', 'gazebo')   (PK column is `id`, not `run_id`)
```
(Shipping HIL telemetry/photos back to the workstation DB is a CI-stage design question —
see docs/session15-hil-ci-stage-design.md — not part of the manual prototype.)

## Part 4 — Teardown

Ctrl+C Terminal 2 (Nav2) and Terminal 1 (sim), in that order. Between HIL attempts, give
DDS ~5 s after both sides are down before relaunching.

## Troubleshooting

- **Jetson sees no topics:** RMW mismatch (check `echo $RMW_IMPLEMENTATION` on both) or
  multicast — use the unicast-peers fallback above. `ping` is NOT a valid link test on
  this network (outbound ICMP is silently dropped — Session 14); use `ros2 topic hz`.
- **Nav2 stuck at time 0 on the Jetson:** `/clock` isn't arriving — check Terminal 1's
  bridge started, and the `/clock` echo in Part 3.
- **Goal rejected repeatedly:** bt_navigator not ACTIVE yet — the runner retries 5×, but
  if it still fails, Nav2 bringup on the Orin may just be slower than x86; wait for
  `Managed nodes are active` before Terminal 3.
- **Non-interactive SSH (automation, CI) gets a bare environment.** The Jetson's `.bashrc`
  has the same early interactivity guard as the workstation's (see CLAUDE.md Gotchas) —
  a non-interactive shell skips all of its sourcing, so ROS2, the workspace overlay, and
  the RMW setting are simply absent. Every scripted SSH command must explicitly run
  `source /opt/ros/jazzy/setup.bash && source ~/autonomous-fleet-testbed/install/setup.bash
  && export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp` before any `ros2`/mission command.
  Human interactive SSH terminals are unaffected. Known trap for the future HIL CI stage —
  do not rely on login-shell env there.

## Results — first HIL run (2026-07-11)

**Outcome: PASS on the first attempt.** Gazebo on the x86 workstation, Nav2 + mission
executor on the real Jetson Orin Nano, talking over the shared-Ethernet link.

- **Date/time:** 2026-07-11 ~18:46 local.
- **Jetson IP / link:** `10.42.0.217`, NetworkManager shared Ethernet (`10.42.0.0/24`,
  workstation gateway `10.42.0.1`). Not USB-C.
- **Discovery mode:** **plain multicast — the unicast-peers fallback was NOT needed.** From
  the Jetson, `ros2 topic list` showed all `/robot_001/*` topics; `ros2 topic hz
  /robot_001/scan` held a steady **~10.0 Hz** (min 0.088 s / max 0.108 s); `/clock` echoed
  sim time. CycloneDDS multicast traverses this shared link cleanly.
- **Nav2 bring-up wall time (Jetson):** **~5 s** from `ros2 launch` to `Managed nodes are
  active` (start epoch 1783820710 → active 1783820715). Much faster than the ≤180 s budget —
  the Orin Nano Super handles the composed Nav2 bringup comfortably. (Task 9 sizing input.)
- **Mission result:** `Mission mission1: PASS`, exit code 0. Per-step wall times (from the
  executor's step log):
  - step 1 `navigate → doorway_center` (yaw π/2): **~5.3 s**
  - step 2 `take_picture`: **~0.07 s** (one `/robot_001/camera/image_raw` frame → PNG)
  - step 3 `navigate → home_base`: **~10.6 s**
  - total mission wall (rclpy init → PASS): **~18 s**. `mean_time_to_goal` = **7.95 s**,
    `mean_position_error` = **0.21 m** (both navigate steps).
- **Photo:** `reports/photos/mission1_step2_20260711_184627.png` (14.9 KB) on the Jetson.
  **Yes — it shows the bedroom from the doorway:** the dark dresser box (brown-framed, left),
  the blue bed/desk box (centre-right), the **green sphere** on the tan floor, grey walls.
  The camera pipeline crosses the network intact.
- **Telemetry row** (Jetson's local `reports/fleet_runs.db`; queried with `python3`, since
  the `sqlite3` CLI is not installed on the Jetson):
  ```
  SELECT scenario, result, runner_type, sim_engine, mean_time_to_goal, mean_position_error
    FROM runs ORDER BY id DESC LIMIT 1;
  -> ('mission1', 'PASS', 'hil_jetson', 'gazebo', 7.9537869691848755, 0.21399501914205987)
  ```
- **Deviations from this runbook (all folded back into the sections above):**
  1. **Part 1 — `colcon build` needs `--base-paths src` on the Jetson.** The self-hosted CI
     runner lives *inside* the repo (`~/autonomous-fleet-testbed/actions-runner`, Session 14
     Part 8) and its `_work/` tree carries a second `src/nav_fleet`; a bare `colcon build`
     scans both and aborts on "Duplicate package names". Folded into Part 1.
  2. **Part 1 — pillow was already present** as the Ubuntu system package `python3-pil`
     (10.2.0, satisfies `>=10.0`); the `pip install 'pillow>=10.0'` step was a no-op and, on
     PEP-668 Ubuntu 24.04, a bare pip install would have been refused anyway. Part 1 now
     documents `apt install python3-pil` as the correct install path if a board lacks it.
  3. **Part 1 — nav2 install timing:** `ros-jazzy-navigation2 ros-jazzy-nav2-bringup` (plus
     the ros-gz sim deps they pull) took **~524 s (~8.7 min)** on the microSD Jetson.
  4. **Part 3 — the mission runs under `python3`** (not `python`) to match the Session-14
     Jetson env; DB verification uses `python3` (no `sqlite3` CLI on the Jetson).
  5. **Discovery:** multicast worked first try — the unicast-peers fallback in Part 2 was not
     exercised this run (left in place as documented insurance).
  6. **Part 1 — branch:** this run checked out `session-15-mission1-hil` (the Session 15
     development branch, pre-merge); Part 1 now says `git checkout main` so the runbook stays
     correct after the branch merges — substitute the branch under test where applicable.

**Caveat:** this is a **single successful run**. Reproducibility across reboots / fresh DDS
state is not yet established — open item for the HIL CI-stage design (Task 9 /
docs/session15-hil-ci-stage-design.md).
