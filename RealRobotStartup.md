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
   2026-08-03 — see `docs/superpowers/specs/ 2026-08-03-docker-brain-real-robot-hil-unification-design.md`, which supersedes
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

- [X] Confirm the **whole** last run on `main` is green — `gh run list`, or the
  dashboard — not just `stage-3-arm64`. The commit you're about to sync is the one
  `robot_boot.sh` will run: it derives the container image tag from `git rev-parse HEAD`
  on the Jetson checkout, so the image must have been cached locally from when
  `stage-4-hil` pulled it during CI testing. `robot_boot.sh` checks for image presence
  and fails loudly if it's missing. This manual check for a green run is the entire
  gate — there's no automated re-verification beyond it, deliberately.
  **A green overall run is NOT enough by itself — check the JOB LIST, not just the
  run's conclusion.** `dorny/paths-filter` correctly SKIPS `stage-3-arm64`/`stage-4-hil`
  on a commit that touches no watched path (docs-only, tests-only, etc.) — confirmed
  live 2026-08-06: the actual latest green run on `main` at the time had both stages
  `skipped`, one commit after the last one that really built+pushed an image. Syncing
  to a skipped-stage commit means no image was ever tagged for that sha —
  `robot_boot.sh` fails loudly (correctly) rather than silently running stale code, but
  better to catch this here than at power-on: `gh run view <run-id> --json jobs -q '.jobs[] | "\(.name)\t\(.conclusion)"'` and pick the last sha where `Stage 3 — arm64 Native Build` AND the HIL stage both say `success`, not just the run as a whole.
- [X] Confirm the Jetson's power mode: `nvpmodel -q` should read 25W. Do not run
  `nvpmodel -m` to "fix" this unless it's genuinely wrong — see the power-mode note
  above.
- [X] Check for root-owned residue from prior container-mode HIL runs:
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

- [X] Follow Waveshare's assembly video/wiki for the physical steps (screws, cable
  routing, Jetson seating) — fill in as you go, this doc can't verify hardware steps
  from a video:

  - [ ] ---
  - [ ] ---
  - [ ] ---
- [X] Power on. Connect to the robot's WiFi network (or confirm it joins yours).
- [X] SSH in over WiFi: `ssh mike@jetson.local` (should resolve reliably — see the
  WiFi note above; fall back to the router admin page's DHCP lease list if not).
- [X] Check Jetson health: `nvidia-smi`, temp, `df -h` free space.
- [X] **Build the native workspace — found missing 2026-08-09, first time this
  checkout has ever needed a bare-metal build.** Every prior HIL/CI run on this
  Jetson used the pre-built CONTAINER image (`stage-3-arm64`'s output) — this exact
  native checkout (`~/autonomous-fleet-testbed`) has never actually been
  `colcon build`'d. **A1's `sync` step does NOT build anything** — it only
  fast-forwards the git checkout — so don't assume this is already done just
  because A1 is checked off. Confirmed live: `install/` on a fresh Jetson only
  contains a `COLCON_IGNORE` placeholder, no real build output, and `.bashrc`
  does NOT auto-source the workspace overlay (unlike the workstation's `.bashrc`,
  which does — this Jetson's is different, don't assume parity between the two
  machines' shell setups).

  ```bash
  # Two system packages this project needs that aren't in a base ROS2 install —
  # check first, only install if actually missing:
  dpkg -l | grep -E "ros-jazzy-robot-localization|ros-jazzy-vision-msgs"
  sudo apt install -y ros-jazzy-robot-localization ros-jazzy-vision-msgs
  # (ekf_node needs the first, ball_detector needs the second)

  source /opt/ros/jazzy/setup.bash
  cd ~/autonomous-fleet-testbed
  colcon build --symlink-install
  source install/setup.bash
  ```

  If the build itself errors, that's a real problem to resolve here, not push
  past — don't proceed to the driver-layer step below until `colcon build`
  finishes clean.
- [X] **Driver layer — resolved 2026-08-06, do NOT install `ugv_ws`. Concrete
  check/install commands added 2026-08-09 (this section was found too vague on a
  live first pass — links only, no actual commands).**
  [`waveshareteam/ugv_ws`](https://github.com/waveshareteam/ugv_ws) only has Humble
  branches (`ros2-humble-develop`, `ros2-humble-develop-251125`) — no Jazzy, official
  or community-confirmed-working for Jetson Orin. Everything else in this project is
  Jazzy-only. `robot_profiles/jetson_ugv_pt.yaml` already names the real hardware, and
  it splits cleanly:

  - **Odom + IMU + `cmd_vel`→wheels (ESP32 sub-controller, UART, per
    `robot_profiles/jetson_ugv_pt.yaml`'s `sub_controller` block): built 2026-08-06,
    no longer a gap.** `nav_fleet/esp32_protocol.py` (pure JSON encode/decode +
    diff-drive odometry integration) + `nav_fleet/esp32_driver.py` (the ROS2 node —
    serial bridge to the sub-controller) publish `/robot_001/odom` +
    `/robot_001/imu/data` and subscribe `/robot_001/cmd_vel`, against Waveshare's
    documented JSON-over-serial protocol. Baud is 115200, not 921600 — the profile's
    `imu.hz_min` was found to not be achievable at 921600 either way and was lowered
    to 50 to match the driver's real default (see `CLAUDE.md`/the driver's own commit
    history if the discrepancy matters later). Nothing to separately install — it's
    this repo's own code, covered by the native workspace build above (NOT by A1's
    sync, which only fast-forwards git — see that new step if this comes back empty).
    Check:

    ```bash
    ros2 pkg executables nav_fleet | grep esp32
    ```

    **WORKING against real hardware, confirmed 2026-08-10 — root-caused and
    fixed.** Wiring/baud/UART device were never the problem (`/dev/ttyTHS1`,
    115200, confirmed 2026-08-09). Run directly (no launch-arg support was
    checked/needed, just pass params on the CLI):

    ```bash
    ros2 run nav_fleet esp32_driver --ros-args -p serial_device:=/dev/ttyTHS1 -p baud:=115200
    ```

    Then in a second terminal: `ros2 topic hz /robot_001/odom` /
    `ros2 topic hz /robot_001/imu/data` — both now publish at ~19.8Hz.

    **Root cause (2026-08-09's "genuinely unresolved" ZERO-messages bug):**
    `esp32_protocol.py`'s field-mapping for the two feedback messages
    (reconstructed 2026-08-06 from firmware source) had the shapes backwards —
    a real firmware-source-vs-runtime-JSON discrepancy, not a transcription
    error. Confirmed by bypassing `esp32_driver`/ROS2 entirely and probing
    `/dev/ttyTHS1` directly with raw pyserial: the ESP32 responds perfectly to
    both `T:131` (enable stream) and `T:126` (IMU request) — wiring/protocol
    commands were always fine. The bug: `T:1001` (continuous stream) actually
    carries wheel speeds + RAW accel/gyro/mag + encoder ticks, NOT fused
    roll/pitch/yaw/temp as assumed; `T:1002` (one-shot `T:126` reply) actually
    carries fused roll/pitch/yaw + a quaternion, NOT raw IMU data as assumed.
    `parse_base_info`/`parse_imu_data` were both hitting `KeyError` on every
    real line and silently returning `None` — regardless of power state, which
    is exactly why the untested power-cycle hypothesis below didn't fix it
    when tried first this session (real information at the time: it ruled out
    a stuck-firmware explanation, correctly pointing the investigation at the
    driver's own parsing instead of the hardware).
    A second real bug was caught by the same fix, before ever reaching hardware:
    the real ESP32 sends whole-number readings as bare JSON ints (`"ax":-36`),
    and `esp32_driver._publish_imu`'s direct field assignment into a ROS
    `geometry_msgs/Vector3` has no arithmetic to coerce int→float the way
    `_publish_odom`'s `/2.0` division accidentally does — an int there
    hard-**aborts the whole process** (`rosidl`'s C converter asserts
    `PyFloat_Check` rather than raising a catchable exception). Would have
    crashed the real driver the instant it published a real IMU reading;
    caught via TDD using the actual captured bytes as test fixtures before it
    ever ran unguarded on hardware. Both fixes, plus regression tests built
    from the real captures: `src/nav_fleet/nav_fleet/esp32_protocol.py`
    (renamed `ImuData`/`parse_imu_data` → `OrientationData`/`parse_orientation`
    to match what that message actually carries), `esp32_driver.py`,
    `tests/test_esp32_protocol.py`, `tests/test_esp32_driver.py`.
    **Known, deliberately deferred gap:** the real fused orientation
    (`T:1002`'s quaternion) is parsed and cached (`driver._last_orientation`)
    but NOT YET wired into the published `Imu` message's `orientation` field —
    its axis convention (q0=w vs q0=x, Hamilton vs JPL) is unconfirmed against
    real hardware rotation testing. Flagged in code, not guessed.
  - **Lidar (D500 / STL-19P):** [`ldrobotSensorTeam/ldlidar_ros2`](https://github.com/ldrobotSensorTeam/ldlidar_ros2)
    — vendor-maintained, no apt package, build from source. Confirmed against a guide
    written for this exact model + ROS2 Jazzy combo. Check:

    ```bash
    ros2 pkg list | grep ldlidar
    ```

    Install:

    ```bash
    mkdir -p ~/ros2_drivers_ws/src
    cd ~/ros2_drivers_ws/src
    git clone https://github.com/ldrobotSensorTeam/ldlidar_ros2.git
    cd ~/ros2_drivers_ws
    rosdep install --from-paths src --ignore-src -r -y
    colcon build --symlink-install --cmake-args=-DCMAKE_BUILD_TYPE=Release
    source install/setup.bash
    ```

    **On a fresh Jetson, both `rosdep install` AND `colcon build` above will FAIL —
    confirmed live, 2026-08-09, two separate root causes, both one-time fixes.**
    Do NOT just re-run one of the two failed steps individually — both actually
    failed (0 packages built), so both need re-running after fixing their causes.
    Full corrected sequence:

    ```bash
    # One-time fixes for both root causes:
    sudo rosdep init                                          # rosdep was never
    rosdep update                                             # initialized on this Jetson
    cd ~/ros2_drivers_ws/src/ldlidar_ros2
    git submodule update --init --recursive                  # sdk/ is a git submodule;
                                                               # plain clone leaves it empty,
                                                               # causing a CMake error citing
                                                               # sdk/CMakeLists.txt missing

    # THEN redo the full original sequence — both steps failed the first time:
    cd ~/ros2_drivers_ws
    rosdep install --from-paths src --ignore-src -r -y
    colcon build --symlink-install --cmake-args=-DCMAKE_BUILD_TYPE=Release
    source install/setup.bash
    ```

    **A THIRD error hits after both of those are fixed — vendor SDK bug, not this
    Jetson's fault, confirmed 2026-08-09 against a known upstream GitHub issue**
    (`ldrobotSensorTeam/ldlidar_stl_ros2` issue #23 — same underlying SDK code):
    a real C++ compile error, `pthread_mutex_init`/`_lock`/`_unlock` "not declared
    in this scope" in `sdk/src/log_module.cpp`. Root cause: `sdk/include/ ldlidar_driver/log_module.h` has `#include <pthread.h>` commented out on its
    Linux branch (line 37 on the commit this project's clone pulled) — the vendor
    SDK simply doesn't compile clean on a modern toolchain as shipped. Fix,
    confirmed against this exact clone (verify the line number still matches
    yours with `grep -n pthread.h sdk/include/ldlidar_driver/log_module.h` first,
    in case the vendor repo changes upstream):

    ```bash
    sed -i '37s|^//#include <pthread.h>|#include <pthread.h>|' \
      ~/ros2_drivers_ws/src/ldlidar_ros2/sdk/include/ldlidar_driver/log_module.h
    cd ~/ros2_drivers_ws
    colcon build --symlink-install --cmake-args=-DCMAKE_BUILD_TYPE=Release
    source install/setup.bash
    ```

    **Confirmed working, 2026-08-09** — `colcon build` finishes clean
    (`1 package finished`). It still prints stderr, but that's just a compiler
    warning in the vendor's own demo executable (`serial_baudrate` used
    uninitialized as a `declare_parameter` default) — harmless in real use, where
    that parameter is always set explicitly via launch args, not left at its
    default. Don't mistake "package had stderr output" in the colcon summary for
    a failure — only "Failed <<<" / a nonzero package-failed count means that.

    D500/STL-19P uses the **`ld19.launch.py`** launch file (not `ld06`/`ld14`/`ld14p`
    — those are for other LD-series models).

    **Two more real, live issues hit getting this far, confirmed working
    2026-08-09 — this Jetson's actual D500 unit needs BOTH fixes. (Briefly lost
    from this doc 2026-08-09 by a later same-day edit that accidentally deleted
    this whole block instead of just adding the camera section next to it —
    caught and restored 2026-08-10 via `git log -p`, not from memory. Lesson: a
    large same-session edit can silently drop unrelated content it never meant
    to touch — worth a quick `git show <commit> -- <file>` sanity check on any
    edit that's supposed to be purely additive.)**
    - **The lidar enumerates as `/dev/ttyACM0`, NOT `/dev/ttyUSB0`** — the launch
      file's `port_name` is hardcoded (no `LaunchConfiguration`/CLI-override
      support at all, confirmed via `--show-args` returning "No arguments" — don't
      go looking for a `-p port_name:=...` override, it doesn't exist).
      `lsusb` showed a `QinHeng Electronics USB Single Serial` device (the CH340-
      family chip actually used here) — that's the tell, if this comes up again on
      a different unit. Fix (source is symlink-installed, takes effect immediately,
      no rebuild needed):
      ```bash
      ls /dev/ttyACM* /dev/ttyUSB* 2>/dev/null   # confirm which one shows up first
      sed -i "s|'/dev/ttyUSB0'|'/dev/ttyACM0'|" ~/ros2_drivers_ws/src/ldlidar_ros2/launch/ld19.launch.py
      ```
    - **Permission denied opening `/dev/ttyACM0`** even once the path was right —
      standard Linux serial-device permissions: `crw-rw---- root dialout`, and a
      fresh user account won't be in the `dialout` group yet. Fix, then **log out
      and back in (or open a brand new SSH session) — group membership does NOT
      apply to an already-open shell**:
      ```bash
      sudo usermod -a -G dialout $USER
      # new session required here — verify with: groups
      ```
      A fresh session also means re-sourcing both ROS2 and the drivers workspace
      overlay (neither persists across a fresh login, same as the main project
      workspace — see the native-build note above):
      ```bash
      source /opt/ros/jazzy/setup.bash
      source ~/ros2_drivers_ws/install/setup.bash
      ```

    Raw sanity check before wiring it into this repo (do this AFTER both fixes
    above, not before — an unfixed port/permission will just look like a hang):
    **`ros2 launch` runs in the foreground and never returns on its own** — the
    commands below are two SEPARATE terminals/SSH sessions, not one sequential
    block:

    ```bash
    # Terminal 1:
    ros2 launch ldlidar_ros2 ld19.launch.py
    # leave this running — watch for "ldlidar communication is normal" /
    # "start normal, pub lidar data" in its own output

    # Terminal 2 (new SSH session, while Terminal 1's launch is still running):
    ros2 topic echo /scan   # bare /scan, NOT /robot_001/scan yet — see the
                            # remapping gap note below
    ```
    **Confirmed working end-to-end after both fixes** — real, varying range data
    streams on `/scan`.
  - **Camera (OAK-D Lite):** [`luxonis/depthai-ros`](https://github.com/luxonis/depthai-ros)
    — apt package exists for Jazzy, no source build needed. Check:

    ```bash
    dpkg -l | grep depthai
    ```

    Install:

    ```bash
    sudo apt update
    sudo apt install -y ros-jazzy-depthai-ros ros-jazzy-depthai-bridge ros-jazzy-depthai-examples
    ```

    **Launch file confirmed 2026-08-09: `camera.launch.py`** (the other name found
    online, `driver.launch.py`, doesn't exist in the actually-installed package —
    checked directly: `ls /opt/ros/jazzy/share/depthai_ros_driver/launch/`).

    ```bash
    ros2 launch depthai_ros_driver camera.launch.py
    ```

    **Confirmed working end-to-end, 2026-08-09** — connects to the real OAK-D-LITE
    (`Camera with MXID: ... connected!`, `Device type: OAK-D-LITE`), real frames
    stream on `/oak/rgb/image_rect` once the CycloneDDS large-message fix below is
    also applied (without it, the camera boots fine but delivers zero image
    messages — a completely different, separate problem from the udev-rule one).
    Also needed, same as the lidar: the Movidius USB device (`03e7:2485` in
    `lsusb`) hits the identical "Insufficient permissions... X_LINK_UNBOOTED...
    Make sure udev rules are set" error until a udev rule is added:

    ```bash
    echo 'SUBSYSTEM=="usb", ATTRS{idVendor}=="03e7", MODE="0666"' | sudo tee /etc/udev/rules.d/80-movidius.rules
    sudo udevadm control --reload-rules && sudo udevadm trigger
    # then unplug/replug the camera's USB cable (or power-cycle the whole robot --
    # udevd's boot-time coldplug pass re-applies rules to already-connected
    # devices too, confirmed live, no need to physically find/replug the cable)
    ```
  - **CycloneDDS large-message gap — found 2026-08-09, confirmed working around it
    live, NOT yet fixed in the project's own permanent config.** Real, uncompressed
    `sensor_msgs/Image` topics (`/oak/rgb/image_raw`, `/oak/rgb/image_rect`) publish
    with zero delivery to any subscriber — `ros2 topic hz` on either hangs
    indefinitely, while the SAME topics' compressed siblings
    (`/oak/rgb/image_rect/compressed`) work immediately. This is a well-documented,
    known ROS2/CycloneDDS limitation (official ROS docs' own DDS-tuning guide),
    not a depthai-ros or project-specific bug. **This will also hit the real
    robot/HIL path once the camera is wired into `sensors_only_launch.py`** —
    `ball_detector.py` subscribes to `/robot_001/camera/image_raw`, the exact same
    class of uncompressed Image topic. Worked around live for bench-testing
    purposes only (a one-off `~/cyclonedds_bigmsg.xml`, NOT part of this project's
    own `scripts/regen_cyclonedds_config.sh`-generated config, which is what
    `container_entrypoint.sh`/the real container path actually uses):

    ```bash
    sudo sysctl -w net.core.rmem_max=2147483647
    echo 'net.core.rmem_max=2147483647' | sudo tee /etc/sysctl.d/10-cyclone-max.conf
    echo '<?xml version="1.0" encoding="UTF-8" ?>' > ~/cyclonedds_bigmsg.xml
    echo '<CycloneDDS xmlns="https://cdds.io/config">' >> ~/cyclonedds_bigmsg.xml
    echo '  <Domain id="any">' >> ~/cyclonedds_bigmsg.xml
    echo '    <Internal>' >> ~/cyclonedds_bigmsg.xml
    echo '      <SocketReceiveBufferSize min="10MB"/>' >> ~/cyclonedds_bigmsg.xml
    echo '    </Internal>' >> ~/cyclonedds_bigmsg.xml
    echo '  </Domain>' >> ~/cyclonedds_bigmsg.xml
    echo '</CycloneDDS>' >> ~/cyclonedds_bigmsg.xml
    export CYCLONEDDS_URI=file://$HOME/cyclonedds_bigmsg.xml   # both publisher + subscriber terminals
    ```

    **TODO, not yet done — real code change, needs full CI+HIL verification before
    trusted (Ethernet-connected HIL, per this doc's own established bar for any
    change touching the real container path):** fold the `<Internal><SocketReceive BufferSize>` element into `scripts/regen_cyclonedds_config.sh`'s own generated
    XML (additive to its existing `<Interfaces>` block, should not touch the
    interface-priority logic already proven there) — the `sysctl` half is already
    permanent/system-wide on this Jetson and doesn't need repeating, only the
    CycloneDDS XML half is still bench-test-only.
  - **Remapping gap — confirmed 2026-08-09, not yet fixed.** `sensors_only_launch.py`
    includes both vendor launch files raw (`lidar_include`/`camera_include`), with
    **no topic remapping at all** — its own code comment already flagged this as
    deferred ("NOT pinned by this project yet... until Mike wires this in"). Once
    both drivers are installed and running, they'll publish to their own default
    topic names (bare `/scan`, and whatever depthai-ros's own default is) — NOT
    `/robot_001/scan` / `/robot_001/camera/image_raw`, which is what the rest of this
    project's ROS graph (EKF, `ball_detector`, the smoke test's own checks) actually
    expects. `ros2 topic hz /robot_001/scan` in the NEXT checklist item will hang
    even with a fully working lidar until this is fixed. This needs a real code
    change to `sensors_only_launch.py` (adding `remappings=[...]` to each
    `IncludeLaunchDescription`, or equivalent) — verified against the real running
    driver's actual topic names, not guessed in advance. Flag this to Claude once
    both drivers are confirmed running with their own default topics visible.
- [X] **Verify all four real topics report, before anything else:**

  ```bash
  ros2 topic hz /robot_001/odom
  ros2 topic hz /robot_001/scan
  ros2 topic hz /robot_001/camera/image_raw
  ros2 topic hz /robot_001/imu/data
  ```

  (the 4th, IMU, is easy to miss but real — `config/ekf.yaml`'s `imu0` input fuses
  yaw-rate from this exact topic; a silently-missing IMU degrades the EKF fusion the
  6-wheel-skid-steer mitigation below depends on, without an obvious error anywhere)
  and confirm `teleop_twist_keyboard`/`teleop_twist_joy` physically drives the wheels.
  (`ball_detector` subscribes to the camera topic and stays silently uninitialized,
  not crashed, if it's missing — check explicitly rather than discovering it later.)
- [X] **Command the pan-tilt gimbal to a fixed forward/level pose — code built AND
  verified live against real hardware, 2026-08-10 (TDD, `encode_gimbal_cmd` +
  `tools/pin_gimbal.py`).** This doc previously said this "depends on what `ugv_ws` exposes" —
  stale/contradictory leftover from before the 2026-08-06 "do NOT install `ugv_ws`"
  decision above; there is no `ugv_ws`-specific gimbal mechanism to depend on
  anymore. Per Waveshare's own documented sub-controller JSON command set, the
  gimbal is driven over the SAME serial link/protocol `esp32_protocol.py` already
  implements (its `T:13`/`T:126`/`T:131`/`T:136`/`T:142` commands) — a `T:133`
  command: `{"T":133,"X":<pan_deg>,"Y":<tilt_deg>,"SPD":0,"ACC":0}`. Sourced from
  Waveshare's wiki via web search — direct fetches of the actual wiki page 403'd
  twice, so this was search-engine-indexed content, not a primary-source read — but
  the field names AND sign convention are now confirmed against the real robot
  (below), so this caveat no longer blocks trusting the command shape.

  `esp32_protocol.encode_gimbal_cmd(pan_deg, tilt_deg)` mirrors the file's existing
  encoders (unit-tested, `tests/test_esp32_protocol.py`); `tools/pin_gimbal.py` is
  the one-off CLI that sends it once over the serial link directly (no ROS2 node —
  this only needs to run once at setup time, the mast holds its last commanded
  pose). **Stop `esp32_driver`/`robot_boot.sh` first if either is running — two
  writers on the same serial port will interleave and corrupt lines.**

  ```bash
  python -m tools.pin_gimbal --pan 0 --tilt 0
  # add --port/--baud only if this Jetson's wiring differs from the confirmed
  # defaults (/dev/ttyTHS1 @ 115200, same as esp32_driver's real hardware config)
  ```

  **Confirmed live, 2026-08-10, Mike watching the physical mast for each move:**
  `--tilt -20` moved the mast down ~20° (and `--tilt 0` returned it to level);
  `--pan 20` swung it right, `--pan -20` swung it all the way left, `--pan 0
  --tilt 0` returned to forward/level. Sign convention now documented in
  `encode_gimbal_cmd`'s own docstring: X (pan) negative=left/positive=right,
  Y (tilt) negative=down (observed)/positive=up (inferred by symmetry, not
  separately tested — this robot's use case never needed to look up). Take a test
  photo before moving on — `take_picture` assumes camera-heading == robot-yaw,
  which only holds now that the gimbal is confirmed pinned forward.
- [ ] Add a scan FOV mask for the pan-tilt mast's rear self-occlusion (a
  `LaserScanRangeFilter`/equivalent clearing the mast's known bearing range) —
  do this before the SLAM mapping step, not after; an unmasked scan corrupts the
  map, not just the costmap.
- [ ] Confirm the URDF footprint against the vendor drawing
  (`docs/img/waveshare_ugv_pt_dimensions.png`): 253×231 mm footprint, 289 mm height
  w/ mast, 126 mm wheelbase, 25 mm ground clearance. **This doc previously claimed the
  URDF was "230×252 mm, already close" — checked against the actual code 2026-08-05
  and that's wrong: `ugv_pt.urdf.xacro`'s `base_length`/`base_width` are 0.35/0.30 m
  (350×300 mm), unchanged since Session 9, and Nav2's real costmap footprint is a
  circular `robot_radius: 0.24` (480 mm diameter) — not a rectangle at all. Whether
  350×300 mm (or the 480 mm circular footprint) is "close enough" to the real
  253×231 mm chassis hasn't actually been re-verified — do that here, don't assume
  the old "geometry is not the gap" conclusion still holds.** (6-wheel skid-steer vs.
  the URDF's 4-wheel diff-drive model IS a separate, already-known real gap — the EKF
  node in A5 below is the mitigation, not a new task here.)
- [ ] **Run the bench smoke test — do this before anything past this point relies on
  the driver layer.** `tools/smoke_test.py` (built 2026-08-06) is a bench sanity check
  for exactly this moment: it proves odom/scan/camera/imu are all publishing at real
  rates, takes a photo, verifies a known-distance ball placement against BOTH the
  lidar and the camera, and runs a small open-loop motion pulse (forward, then a
  turn) — all BEFORE Nav2/SLAM/the mission is ever trusted to drive this robot.
  From the workstation:

  ```bash
  scripts/hil_stage.sh smoke <the synced commit sha>
  ```

  This is attended, not automated — it will prompt you (in the same terminal) to
  place the yellow ball. Two placement details matter, found live 2026-08-09 getting
  this check to actually pass in sim:- **Distance: ~2.5 ft (0.75 m) directly in front of the robot** — NOT the original
  12"/0.305 m the design spec started with; 12" turned out to be geometrically
  outside the camera's own field of view (confirmed via the real URDF geometry — a
  floor-level object that close sits well below what a level, forward-mounted
  camera can see). The prompt itself states the live distance, so this is a safety
  note, not something you need to calculate by hand.

  - **Height: on a riser/box, NOT the bare floor/bench surface** — this robot's lidar
    (real hardware: `ldlidar_ros2`) is a 2D PLANAR lidar, one fixed scan height, zero
    vertical resolution. A small ball sitting directly on the floor is entirely below
    that scan plane and the lidar will never see it, at any distance. The ball's
    CENTER needs to sit at roughly the lidar's own mount height (~10 in / 0.25 m off
    the surface) — again, the prompt states the live number, use a box/riser under
    the ball to get it there.
  - **PASS requires every check to pass, including both sensors on the ball** — if it
    FAILs, read which specific check failed before assuming the driver layer itself
    is broken; a placement-distance/height miss looks identical to a real sensor
    fault in the summary output, so double-check your physical placement first.
  - **Don't run this back-to-back without resetting the robot's position.** The
    motion check at the end physically moves the robot (a short forward pulse, then a
    turn) — a SECOND smoke-test run right after, without physically repositioning the
    robot back to its start spot/heading, will place the ball relative to the
    robot's now-stale assumed heading and can fail for that reason alone, not a real
    problem. Physically reset the robot's position between runs if you want to run it
    more than once in a session.

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
- [ ] **Determine and set the real AMCL seed pose — found 2026-08-05, not yet done
  anywhere.** `nav2_params.yaml`'s `amcl.initial_pose` is ONE shared block for
  sim/HIL/real robot; today it's hardcoded to the SIM map's coordinates
  (`x: -1.276, y: 1.2, yaw: 1.5708`, commented "hallway entrance — robot_001 spawn
  point" — `living_room.yaml`'s frame, meaningless once `bedroom_real.yaml` exists).
  `set_initial_pose: true` means this value is what AMCL seeds from on EVERY boot,
  unattended — no RViz "2D Pose Estimate" click happens in the automated systemd
  flow, so this IS the entire localization strategy, not a one-time nicety.
  Procedure:
  1. Physically mark the exact spot + facing direction the robot will always start
     from day-to-day — this becomes B1's "known starting position, documented
     heading." Write it down / tape a mark; don't rely on memory.
  2. With `bedroom_real.yaml` loaded, bring up Nav2 on the Jetson
     (`nav2_only_launch.py use_sim_time:=false map:=.../bedroom_real.yaml ...`); run
     RViz2 from the workstation over WiFi against the robot's topics (same
     remote-viz pattern as any GUI-watched HIL run).
  3. Place the robot at the marked spot, give AMCL a rough seed via RViz's "2D Pose
     Estimate," let the particle cloud converge (drive a short loop if needed).
  4. Read the converged pose: `ros2 topic echo /robot_001/amcl_pose --once` (or read
     it off RViz) — record x, y, yaw.
  5. Update `nav2_params.yaml`'s `amcl.initial_pose` block with these real values,
     and fix the stale `# Map: maps/living_room.pgm` / `# Initial pose: hallway entrance` comments above it to describe the real map instead.
  6. Commit the updated `nav2_params.yaml` alongside the map/HSV config.

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
  (no ground-truth judging — the real robot has none). Place the yellow ball, then the
  red ball, at the right moments (see A7) and confirm the whole day runs to
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
  won't see you place it), put the **yellow ball** at the marker position.
- [ ] The robot reacts to yellow (stops ~0.8 m short, photographs it) and heads home
  again.
- [ ] **While the robot is heading home** on that leg's return, swap the ball for
  **red**, same way (see `tools/mission2_day.py`'s `run_ball_choreography`/
  `BALL_AT_SPHERE_XY` if you need to double check the exact sequence and marker
  coordinates).
- [ ] The final leg reacts to red and the day ends — the mission_runner process
  exits with no artificial pause, so watch for the container's own exit and check
  the log's final lines to confirm the mission completed normally.
- [ ] **Ground-truth check — do this every time, not just this once:** visually
  confirm what the robot actually did (reacted to the right color, at roughly the
  right point, returned home cleanly) matches the self-reported PASS/FAIL per leg
  before trusting it. There's no software oracle for this on real hardware — your own
  observation is the accepted mitigation, same as it's always been for GUI-watched
  sim/HIL runs.
- [ ] Check the result: `python -m tools.fleet_status --stage real` (or just read the
  log at `~/fleet-ci-data/robot_boot_logs/robot_boot_<timestamp>.log`). All 3 legs
  PASS + your own eyes-on confirmation = the mission worked.

### A8. Tag and commit

- [ ] If all 3 legs passed and you're satisfied by the ground-truth check:
  ```bash
  git tag r1-complete
  git push origin r1-complete
  ```
- [ ] Commit everything from Part A (map, `hsv_realcam.yaml`):
  ```bash
  git add .
  git commit -m "feat: real robot deploy — SLAM map, HSV calibration, r1-complete"
  git push
  ```

**Part A complete when:** `bedroom_real.pgm`/`.yaml` and `hsv_realcam.yaml` are both
committed; `robot_boot.sh` has been run manually at least once and passed all 3 legs
with your own eyes-on confirmation; the systemd unit is installed and enabled;
`r1-complete` is tagged.

---

## Part B — Day-to-Day Operation

### B1. Turn on and go

- [ ] Physically place the robot at the known starting position, facing the
  documented heading.
- [ ] Power on. That's it — `robot-mission.service` handles everything from there:
  waits for WiFi, regenerates the DDS config, brings up the container (which runs
  Nav2/EKF/`ball_detector` inside), and runs the mission2 day with operator ball
  placement. Step back and watch; place the balls per A7's timing when the moment comes.
- [ ] Ground-truth check by eye, every time.

### B2. After a mission — evidence stays local, nothing pushes automatically

**No expectation of automatically pushing logs or results to the workstation for R1 —
this is manual, by design** (log/result analysis and real-robot drift detection are
explicitly R2 scope, not R1):

- [ ] The mission's own log sits at
  `~/fleet-ci-data/robot_boot_logs/robot_boot_<timestamp>.log` on the Jetson, and the
  telemetry row is already in the Jetson's own local `fleet_runs.db` — both stay there
  until you choose to look, no push happens on their own.
- [ ] **For Nav2's own detailed launch output, `python -m tools.pull_ros_logs` is NOT
  the right tool anymore — found + fixed in review, 2026-08-09.** That tool's entire
  mechanism is resolving `~/.ros/log/latest` on the target host, which only ever
  gets written by a BARE-METAL `ros2 launch` process. Since the docker-brain
  unification, Nav2/EKF/`ball_detector` all run INSIDE the container (see the intro
  note at the top of this doc), and the container's own internal `~/.ros/log` is
  never bind-mounted out — `robot_boot.sh` only mounts `reports/` and
  `fleet-ci-data/`. Running `pull_ros_logs.py` against the Jetson now will NOT error;
  it will silently hand you whatever old bare-metal session happens to still be
  sitting there (confirmed live: a session from 2026-08-01, over a week stale, on a
  Jetson that had run several real missions since) — worse than doing nothing, since
  it looks like it worked. The real, current mechanism: `container_entrypoint.sh`
  redirects Nav2's own `ros2 launch` output to
  `~/autonomous-fleet-testbed/reports/nav2_container_<timestamp>.log` on the
  Jetson — inside the SAME bind-mounted `reports/` directory `robot_boot.sh` already
  uses, so it lands on the Jetson's host filesystem automatically, no pull needed for
  that first hop. To get it to the workstation: `scp mike@jetson.local: ~/autonomous-fleet-testbed/reports/nav2_container_*.log .` (or just SSH in and
  read it directly on the Jetson). `pull_ros_logs.py` itself isn't broken as code —
  it still works correctly for bare-metal contexts (stage-2 sim, SLAM Toolbox in A3)
  — it's specifically wrong for this container-mode real-robot path.
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
- [ ] Re-check `~/fleet-ci-data` ownership before the next real-robot run (the
  container runs as root and will re-poison the directory with root-owned files —
  see A1's check).

### B4. Code passed CI/CD — redeploy to the real robot

- [ ] `scripts/hil_stage.sh sync <the new green run's sha>` — gets the newly-tested
  commit onto the Jetson's native checkout (same mechanism as A6).
- [ ] `sudo systemctl enable robot-mission.service` (re-enable, if B3 disabled it).
- [ ] Repeat A2's physical transplant steps to reinstall the Jetson into the robot.
- [ ] Run B1's turn-on-and-go loop to confirm.

### B5. Running the bench smoke test again, once `robot-mission.service` is enabled

The smoke test (A2) isn't a one-time thing — run it again any time you want a quick
driver-layer sanity check (after reconnecting a sensor, after a driver code change too
small to warrant a full B3 HIL round-trip, etc.). Once `robot-mission.service` is
installed and enabled, though, it's no longer automatically safe to just SSH in and
run it — worth understanding why, not just following steps blindly:

- **`robot-mission.service` starts the mission unconditionally, immediately, on every
  single boot — there is no built-in check that waits for or defers to a smoke test.**
  If the robot has just been power-cycled (or is about to be), the mission is either
  already running or about to start the instant boot completes — there's no way to
  SSH in fast enough to beat that, so don't try to race it.

- [ ] **If you know ahead of time** you'll want to smoke-test after the next boot:
  `sudo systemctl disable robot-mission.service` **before** power-cycling, not after —
  disabling in advance means the mission never attempts to start on that boot at all,
  no race involved.
- [ ] **If the mission is already running** (you forgot to disable it first, or it
  auto-started before you got to a terminal): stop it directly, don't reboot again to
  try to catch a gap — `docker rm -f robot_mission` (or `sudo systemctl stop robot-mission.service`) frees the hardware immediately, no timing involved. **Watch
  the robot physically when you do this** — you're removing whatever is supervising
  `cmd_vel` while the robot may still be mid-motion; don't assume it stops cleanly on
  its own without checking.
- [ ] Run the smoke test (A2's instructions — same command, same riser/height and
  distance notes, same "don't run it back-to-back without repositioning" caution).
- [ ] When done: `sudo systemctl enable robot-mission.service` again.
- [ ] **Re-enabling alone does NOT run anything — `systemctl enable` only arms the
  service for the *next* boot, it doesn't start it now.** Don't consider this closed
  out until you've actually confirmed a real mission run afterward — either let the
  next natural power-cycle do it, or run B1's turn-on-and-go loop directly to confirm
  now. This mirrors B4's own last step for exactly the same reason: config alone
  proves nothing ran.
