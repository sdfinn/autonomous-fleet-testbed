# Real Robot Startup

Step-by-step checklist for taking the robot from "arrived" to "running the validation
mission and staying in sync with CI/CD." **Part A is done once.** **Part B is the
repeatable loop** you use every time you power the robot on, or every time new code
needs to reach it. Written to be followed close to verbatim.

**Rewritten 2026-08-01** — supersedes the earlier version in full. Two things changed
from the ground up, both worth knowing before reading further:

1. **The validation target is the mission2 day (no_ball → yellow → red), not BR-01/
   `test_navigation.py`.** This is the same 3-leg day `stage-2-gazebo` and `stage-4-hil`
   already run in sim/HIL — same judging, same telemetry shape. `sim_vs_real_comparison.py`
   and its correlation-≥70% gate are dropped entirely for R1; getting/reviewing logs and
   real-robot drift detection are explicitly R2 scope, not R1. The gate is: the mission
   runs, passes per leg (same PASS/FAIL judging HIL already does), and you visually
   confirm it — nothing more automated than that.
2. **Nav2/EKF/`ball_detector`/`mission_runner` run INSIDE the container** (reversed
   2026-08-03 — see `docs/superpowers/specs/
   2026-08-03-docker-brain-real-robot-hil-unification-design.md`, which supersedes
   `docs/bare-metal-vs-container-decision.md`'s conclusion). Ball placement and
   ground-truth judging stay workstation-side for HIL (that harness never runs on the
   real robot either way); the real robot self-reports each leg's PASS/FAIL with no
   ground-truth check at all — analysis of logs/photos happens after, manually.

**WiFi is proven, not just assumed.** The Jetson's WiFi + CycloneDDS + mDNS have all
been hardened and live-verified (multiple full reboots, zero regressions) — see
`CLAUDE.md`'s dated Gotchas if you want the full incident history. Two things worth
knowing going in:
- `ssh mike@jetson.local` should resolve reliably. This depends on two **OS-level
  config changes on this exact Jetson** (`use-ipv6=no` in avahi's config;
  `systemd-time-wait-sync.service` gating avahi's start) that are **not in git** — if
  this Jetson is ever reflashed/re-provisioned, both need redoing (see `CLAUDE.md`'s
  avahi Gotchas for the exact commands).
- The deployed robot does not need WiFi to reach anything else once running — it's a
  purely local prerequisite (CycloneDDS needs at least one physical, up interface to
  bind its own internal DDS discovery to; nothing about Nav2/EKF/`ball_detector`/
  `mission_runner`/Ollama needs to reach the workstation or the internet). WiFi has to
  be associated *before* the boot sequence starts (see Part A, the systemd unit waits
  on it); nothing after that point talks in or out.

**Power mode: leave the Jetson at 25W, don't touch `nvpmodel -m` casually.** Set once
by hand outside any script; `nvpmodel -m` has a confirmed bug where it can demand an
interactive reboot confirmation even when setting the mode it's already in (`CLAUDE.md`
Gotchas — the fix, if this ever recurs, is `echo yes | ssh ... nvpmodel -m <id>`, never
a generic reboot). `nvpmodel -q` (read-only) is always safe.

**Confirmed setup: ONE Jetson, no second CI runner.** The Session 14 Jetson transfers
into the robot permanently — getting back into HIL mode after a code change means
physically pulling it back out (Part B3), a real repeated cost, not one-time.

---

## Part A — One-Time Setup

### A1. Pre-flight, still on the bench (Ethernet, connected to workstation)

- [ ] Confirm the **whole** last run on `main` is green — `gh run list`, or the
  dashboard — not just `stage-3-arm64`. `stage-3-arm64` builds and pushes `:latest`
  *before* `stage-4-hil` even runs and doesn't wait on it, so a green build stage alone
  doesn't mean that commit's mission actually passed. This manual check is the entire
  gate for "is `:latest` trustworthy" — there's no automated re-verification beyond it,
  deliberately (see `docs/bare-metal-vs-container-decision.md`'s closing note on this
  session's simplification).
- [ ] Confirm the Jetson's power mode: `nvpmodel -q` should read 25W. Do not run
  `nvpmodel -m` to "fix" this unless it's genuinely wrong — see the power-mode note
  above.
- [ ] Check for root-owned residue from prior container-mode HIL runs:
  ```bash
  ls -la ~/fleet-ci-data
  # If anything is root-owned:
  sudo chown -R mike:mike ~/fleet-ci-data
  sudo chmod -R u+rwX,g+rwX ~/fleet-ci-data
  sudo find ~/fleet-ci-data -type d -exec chmod g+s {} \;
  ```
- [ ] (Optional but recommended) Run one more full HIL day as a "last known good"
  checkpoint before touching anything physical: `scripts/hil_stage.sh day`.

### A2. Physical transplant into the Waveshare UGV-PT

- [ ] Follow Waveshare's assembly video/wiki for the physical steps (screws, cable
  routing, Jetson seating) — fill in as you go, this doc can't verify hardware steps
  from a video:
  - [ ] ______________________________________________
  - [ ] ______________________________________________
  - [ ] ______________________________________________
- [ ] Power on. Connect to the robot's WiFi network (or confirm it joins yours).
- [ ] SSH in over WiFi: `ssh mike@jetson.local` (should resolve reliably — see the
  WiFi note above; fall back to the router admin page's DHCP lease list if not).
- [ ] Check Jetson health: `nvidia-smi`, temp, `df -h` free space.
- [ ] Evaluate Waveshare's `ugv_ws` ROS2 workspace (github.com/waveshareteam) — it may
  cover the base driver + lidar + camera out of the box. Install/build it.
- [ ] **Verify all four real topics report, before anything else:**
  ```bash
  ros2 topic hz /robot_001/odom
  ros2 topic hz /robot_001/scan
  ros2 topic hz /robot_001/camera/image_raw
  ```
  and confirm `teleop_twist_keyboard`/`teleop_twist_joy` physically drives the wheels.
  (`ball_detector` subscribes to the camera topic and stays silently uninitialized,
  not crashed, if it's missing — check explicitly rather than discovering it later.)
- [ ] Command the pan-tilt gimbal to a fixed forward/level pose (exact mechanism
  depends on what `ugv_ws` exposes — joint command or vendor service call). Verify
  with a test photo. `take_picture` assumes camera-heading == robot-yaw; this only
  holds if the gimbal is pinned forward first.
- [ ] Add a scan FOV mask for the pan-tilt mast's rear self-occlusion (a
  `LaserScanRangeFilter`/equivalent clearing the mast's known bearing range) —
  do this before the SLAM mapping step, not after; an unmasked scan corrupts the
  map, not just the costmap.
- [ ] Confirm — don't re-measure from scratch — the URDF footprint against the vendor
  drawing (`docs/img/waveshare_ugv_pt_dimensions.png`): 253×231 mm footprint, 289 mm
  height w/ mast, 126 mm wheelbase, 25 mm ground clearance. Current URDF (230×252 mm)
  is already close — geometry is not the gap. (6-wheel skid-steer vs. the URDF's
  4-wheel diff-drive model IS a real gap — the EKF node in A5 below is the mitigation,
  not a new task here.)

### A3. Build the real-room SLAM map

- [ ] Joystick setup — pick one and note which for next time:
  - [ ] **Plug the joystick into the Jetson** (USB dongle or Bluetooth), run
    `teleop_twist_joy` locally on the robot. No laptop needed while driving — just
    walk around with the controller.
  - [ ] OR plug the joystick into the workstation, run `teleop_twist_joy` there,
    commands travel over WiFi.
- [ ] Start SLAM Toolbox on the Jetson:
  ```bash
  source /opt/ros/jazzy/setup.bash
  ros2 launch slam_toolbox online_async_launch.py use_sim_time:=false
  ```
- [ ] Drive the robot slowly around the room perimeter + past all furniture.
- [ ] **Done when:** the map has no big unexplored gaps and the perimeter closes
  cleanly (check in RViz if available, or by eye if the map image looks complete).
- [ ] Save the map:
  ```bash
  ros2 run nav2_map_server map_saver_cli -f src/nav_fleet/maps/bedroom_real
  # Creates: maps/bedroom_real.pgm + maps/bedroom_real.yaml
  ```
- [ ] Commit `bedroom_real.pgm`/`.yaml`.

### A4. Calibrate ball-color detection for the real camera

**New — this didn't matter under the old BR-01 gate (Mission 1 never consumed
detections), but mission2's yellow/red legs are entirely about reacting to a detected
ball, so `ball_detector`'s color thresholds have to actually work against the real
camera.** `hsv_gazebo.yaml`'s thresholds are tuned for Gazebo's rendered ball material
— there's no reason they hold for a real webcam's real-world color/lighting response.

- [ ] Take a close-up photo of the real red ball with the robot's actual camera, under
  the actual deployment lighting, filling most of the frame. Repeat for yellow.
- [ ] Get a suggested threshold from each photo:
  ```bash
  python -m tools.calibrate_hsv_realcam red_ball_photo.png --color red
  python -m tools.calibrate_hsv_realcam yellow_ball_photo.png --color yellow
  ```
  This is a suggestion tool, not a solver — there's no ground truth for a real photo's
  HSV band the way `tools/calibrate_ball_range.py` has Gazebo ground truth for range.
  Sanity-check the printed numbers look like real hue values (red near 0/360, yellow
  in the 40-75 range) before trusting them.
- [ ] Create `src/nav_fleet/config/hsv_realcam.yaml`, same shape as `hsv_gazebo.yaml`:
  ```yaml
  colors:
    red:    {h: [<from tool>], s_min: <from tool>, v_min: <from tool>}
    yellow: {h: [<from tool>], s_min: <from tool>, v_min: <from tool>}
  min_pixels: 40
  range_k: 47.1   # unchanged from hsv_gazebo.yaml — a property of focal length, not
                  # color; no real-camera range calibration exists yet
  ```
- [ ] Verify live: point the camera at each real ball, watch `ball_detector`'s output
  topic (`/robot_001/detections` or equivalent) for a correct-color hit before moving
  on. Don't trust the tool's numbers unverified.
- [ ] Commit `hsv_realcam.yaml`.

### A5. No new launch file needed

Superseded 2026-08 by the docker-brain unification (docs/superpowers/specs/
2026-08-03-docker-brain-real-robot-hil-unification-design.md): `robot_launch.py` is
never created. `src/nav_fleet/launch/nav2_only_launch.py` — the same file HIL already
uses — is reused directly, parameterized by three launch arguments
(`use_sim_time:=false hsv_config:=.../hsv_realcam.yaml map:=.../bedroom_real.yaml`),
passed in by `scripts/container_entrypoint.sh` (see A6). Nothing to write here.

### A6. Build the power-on boot sequence

`scripts/robot_boot.sh`, `scripts/robot-mission.service`, and
`scripts/container_entrypoint.sh` already exist in the repo — nothing to write here,
just install and verify:

- [ ] Get the exact HIL-tested commit onto this checkout (from the workstation):
  ```bash
  scripts/hil_stage.sh sync <the green run's commit sha>
  ```
  This ALSO determines which container image `robot_boot.sh` runs — it derives the
  image tag from this checkout's own `git rev-parse HEAD`, and stage-3-arm64 tags
  every build with its commit sha. No `docker pull` ever happens here: the image
  must already be cached locally from when `stage-4-hil` pulled it for this exact
  commit during CI. `robot_boot.sh` checks this and fails loudly (naming the
  missing tag) rather than trying to fetch it.
- [ ] Run `scripts/robot_boot.sh` **manually over SSH** first — don't install the
  systemd unit yet. Watch it: image-present check → container starts → DDS regen →
  Nav2/EKF/`ball_detector` come up (inside the container) → "Managed nodes are
  active" ×2 → `mission_runner --day` starts, self-reporting each leg's PASS/FAIL
  (no ground-truth judging — the real robot has none). Place the red ball, then the
  yellow ball, at the right moments (see A7) and confirm the whole day runs to
  completion.
- [ ] Only once that manual run has actually passed: install the systemd unit so
  power-on triggers it automatically.
  ```bash
  sudo cp scripts/robot-mission.service /etc/systemd/system/
  sudo systemctl daemon-reload
  sudo systemctl enable robot-mission.service
  ```
  This is genuinely new — nothing in CI/HIL exercises a power cycle, so there's no
  automated proof this works, only the manual run above. Treat the manual invocation
  as the real test; the systemd unit is convenience wired on top of something already
  proven to work by hand.

### A7. Validate the mission with balls placed manually

Ball timing matches exactly what sim/HIL already do (`tools/mission2_day.py`'s own
choreography, just done by hand instead of `spawn_ball`/`remove_ball`) — **no
prompting exists in operator mode; watch the robot and act on your own judgment**:

- [ ] The day starts with the **no_ball** leg — no ball out yet. The robot navigates
  out, finds nothing, returns home.
- [ ] **While the robot is heading home** on that first return leg (behind it, it
  won't see you place it), put the **red ball** at the marker position.
- [ ] The **yellow leg** starts automatically — actually the ball placed is meant to
  trigger a "yellow" reaction; place whichever ball your day's ordering expects at
  that point (see `tools/mission2_day.py`'s `run_ball_choreography`/`BALL_AT_SPHERE_XY`
  if you need to double check the exact sequence and marker coordinates).
- [ ] **While the robot is heading home** on that leg's return, swap the ball for
  **red**, same way.
- [ ] The final leg reacts to red and the day ends; the script holds 10s so you can
  see it's actually done, not mid-frame.
- [ ] **Ground-truth check — do this every time, not just this once:** visually
  confirm what the robot actually did (reacted to the right color, at roughly the
  right point, returned home cleanly) matches the logged PASS/FAIL per leg before
  trusting it. There's no software oracle for this on real hardware — your own
  observation is the accepted mitigation, same as it's always been for GUI-watched
  sim/HIL runs.
- [ ] Check the result: `python -m tools.fleet_status --stage real` (or just read the
  log at `~/fleet-ci-data/robot_boot_logs/mission2_day_<timestamp>.log`). All 3 legs
  PASS + your own eyes-on confirmation = the mission worked.

### A8. Tag and commit

- [ ] If all 3 legs passed and you're satisfied by the ground-truth check:
  ```bash
  git tag r1-complete
  git push origin r1-complete
  ```
- [ ] Commit everything from Part A (map, `hsv_realcam.yaml`, `robot_launch.py`):
  ```bash
  git add .
  git commit -m "feat: real robot deploy — SLAM map, HSV calibration, robot_launch.py, r1-complete"
  git push
  ```

**Part A complete when:** `bedroom_real.pgm`/`.yaml`, `hsv_realcam.yaml`, and
`robot_launch.py` are all committed; `robot_boot.sh` has been run manually at least
once and passed all 3 legs with your own eyes-on confirmation; the systemd unit is
installed and enabled; `r1-complete` is tagged.

---

## Part B — Day-to-Day Operation

### B1. Turn on and go

- [ ] Physically place the robot at the known starting position, facing the
  documented heading.
- [ ] Power on. That's it — `robot-mission.service` handles everything from there:
  waits for WiFi, regenerates the DDS config, brings up Nav2 bare, runs the mission2
  day with operator ball placement. Step back and watch; place the balls per A7's
  timing when the moment comes.
- [ ] Ground-truth check by eye, every time.

### B2. After a mission — evidence stays local, nothing pushes automatically

**No expectation of automatically pushing logs or results to the workstation for R1 —
this is manual, by design** (log/result analysis and real-robot drift detection are
explicitly R2 scope, not R1):

- [ ] The mission's own log sits at
  `~/fleet-ci-data/robot_boot_logs/mission2_day_<timestamp>.log` on the Jetson, and the
  telemetry row is already in the Jetson's own local `fleet_runs.db` — both stay there
  until you choose to look, no push happens on their own.
- [ ] If you want to pull ROS2 logs to the workstation: `python -m tools.pull_ros_logs
  --host mike@jetson.local` (optional, whenever you actually want to look at them).
- [ ] A rosbag evidence bag auto-captures to `reports/failure_bags/` on any FAIL — pull
  it the same way if you want it (`scp`), not required.

### B3. Code changed — getting back into HIL mode

One Jetson, no separate CI runner — this is a physical swap, every time:
- [ ] Physically remove the Jetson from the robot chassis.
- [ ] Reconnect it to the workstation bench (Ethernet, same as the original HIL
  setup).
- [ ] `sudo systemctl disable robot-mission.service` before testing (so a HIL day
  doesn't collide with the boot-time unit trying to start its own mission at the same
  time) — `sudo systemctl enable` it again before B4's reinstall.
- [ ] Re-run `scripts/hil_stage.sh day` / the normal CI pipeline as usual.
- [ ] Re-check `~/fleet-ci-data` ownership before the NEXT bare-metal real-robot run
  (container-mode HIL will re-poison it — see A1's check).

### B4. Code passed CI/CD — redeploy to the real robot

- [ ] `scripts/hil_stage.sh sync <the new green run's sha>` — gets the newly-tested
  commit onto the Jetson's native checkout (same mechanism as A6).
- [ ] `sudo systemctl enable robot-mission.service` (re-enable, if B3 disabled it).
- [ ] Repeat A2's physical transplant steps to reinstall the Jetson into the robot.
- [ ] Run B1's turn-on-and-go loop to confirm.
