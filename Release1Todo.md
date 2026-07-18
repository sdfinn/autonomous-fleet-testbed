# Release 1 Todo — autonomous-fleet-testbed

**Goal:** Complete 6-stage CI/CD pipeline with one real robot (Waveshare UGV PT + Jetson Orin Nano Super). Sim-to-real validation is real, not a placeholder.  
**Tag on completion:** `git tag r1-complete`  
**Format:** Each session ~3 hrs. Do sessions in order — each one gates the next.  
**This file is the go-to doc** (Mike, 2026-07-18): sessions AND the future-release
roadmap live here, self-contained — **Session 20 (end of this file) is the living
description of everything beyond R1**, including the Standing Disciplines. BLUEPRINT.md
holds strategy background and the decisions log; nothing here requires reading it.

<!-- moved to Session 20 (Mike 2026-07-18: no release summary at the top) -->

---

## Session Index

| # | Title | Status |
|---|---|---|
| 01 | Ubuntu 24.04 Dual Boot | ✅ |
| 02 | ROS2 Jazzy + Gazebo Harmonic | ✅ |
| 03 | Docker + Tools + GitHub CLI | ✅ |
| 04 | GitHub Repo + Project Skeleton | ✅ |
| 05 | File Migration from Current Project | ✅ |
| 06 | Requirements Gate | ✅ |
| 07 | Code Quality Gate | ✅ |
| 08 | arm64 Cross-Compile + QEMU Baseline | ✅ |
| 09 | URDF + Nav2 in Gazebo | ✅ |
| 10 | First Passing Nav Test + Self-Hosted CI Runner | ✅ |
| 11 | Isaac Sim: Install + First Nav Test | ✅ |
| 12 | Reports + Dashboard: True End-to-End | ✅ |
| 13 | Agentic Test Loop in Sim | ✅ |
| 14 | Jetson Orin Nano: Flash + ROS2 + CI Runner | ✅ (2026-07-14 — NVMe fresh install executed 2026-07-13, runner re-registered, full 8-job CI cycle green (run 29301726080), manual HIL run on the NVMe install PASS first-attempt 2026-07-14; see `docs/runbooks/JetsonInstallSession14.md`) |
| 15 | Gazebo + Real Jetson Hardware-in-the-Loop (Mission 1) | ✅ (2026-07-11 — Mission 1 PASS on x86 sim AND real-Jetson HIL, merged to main; CI stage designed but not yet implemented — see `docs/runbooks/Mission1HILSession15.md` + `docs/session15-hil-ci-stage-design.md`) |
| 16 | HIL CI Stage with Gazebo + Mission 2 | ⬜ (created 2026-07-12, rescoped same evening — implement `stage-4-hil` from `docs/session15-hil-ci-stage-design.md`, retire `stage-4-isaac`; + Mission 2 camera-reactive incl. real USB camera manual tier; tidy-up review work moved to Session 17) |
| 17 | Harden, Stabilize & Review (pre-robot gate) | ⬜ (created 2026-07-12 evening — code review, perf, reuse, robot-debuggable logging, report UX, drift/AI review; gate: "robot good to go out of the gate?") |
| 18 | Real Robot: Deploy + Sim-to-Real Comparison | ⬜ (was 16 until 2026-07-12, then 17 until the same evening) |
| 19 | Real-Robot Expansion & Deferred Capability (pick-list) | ⬜ (rewritten 2026-07-17 as a menu ordered by robot-day de-risking; was "Agentic Loop on Real Hardware + Advanced Missions") |
| 20 | Future Releases: Working Plan (R2–R5, living) | 🔄 (executed 2026-07-17/18 — ladder relabeled, all candidates placed; LIVING section, updated as decisions change) |

---

## Session 01 — Ubuntu 24.04 Dual Boot (~3 hrs)

### Recommended Reading
- [Ubuntu 24.04 Installation Guide](https://ubuntu.com/tutorials/install-ubuntu-desktop) — official step-by-step with screenshots
- [Dual Boot Windows 11 + Ubuntu](https://www.how2shout.com/linux/install-ubuntu-24-04-alongside-windows-11/) — covers UEFI/GRUB specifics

### Prerequisites
- Windows 11 machine with at least 150 GB free disk space
- 8 GB+ USB drive (contents will be erased)
- Know your BitLocker status (check before starting)

### Before You Start — Windows Prep

- [x] **Check BitLocker.** Open Settings → Privacy & Security → Device Encryption. If on, save your recovery key to a safe location — dual boot can trigger a recovery prompt on next Windows boot.

- [x] **Disable Fast Startup.** Control Panel → Power Options → "Choose what the power buttons do" → uncheck "Turn on fast startup". Without this, Windows can lock the NTFS partition and corrupt it from Ubuntu.

- [x] **Shrink Windows partition.** Right-click Start → Disk Management → right-click C: → Shrink Volume. Shrink by **150 GB minimum** (200 GB if space allows — Isaac Sim alone needs 50+ GB). Leave it as unallocated space.

- [x] **Download Ubuntu 24.04.4 LTS ISO** from [ubuntu.com/download/desktop](https://ubuntu.com/download/desktop).

- [x] **Download Rufus** from [rufus.ie](https://rufus.ie). Run it, select the ISO, set Partition scheme to **GPT**, Target system to **UEFI (non CSM)**. Write in ISO Image mode when prompted. This takes ~10 min.

### Install Ubuntu

- [x] Reboot. Press F12 (or DEL, or F2 — check your motherboard) at the POST screen to get the boot menu. Select the USB drive.

- [x] Choose **"Try or Install Ubuntu"**.

- [x] At the installer: choose **"Install Ubuntu"** → **"Interactive installation"** → **"Default selection"**.

- [x] At the disk screen: choose **"Install Ubuntu alongside Windows Boot Manager"**. The installer will use the unallocated space automatically. Accept the proposed partition layout (Ubuntu handles swap as a file, no swap partition needed).

- [x] Set your timezone, username, and password. Enable auto-login if convenient (lab machine).

- [x] Install takes 15–25 min. When prompted, remove the USB and reboot.

- [x] On reboot, **GRUB appears** — arrow key selects Windows or Ubuntu. Verify both boot.


### First Boot into Ubuntu

- [x] Boot into Ubuntu. Open a terminal (Ctrl+Alt+T).

- [x] Verify NVIDIA GPU is visible:
  ```bash
  lspci | grep -i nvidia
  # Should show your RTX 5080
  ```

- [x] Run system update:
  ```bash
  sudo apt update && sudo apt upgrade -y
  sudo reboot
  ```

- [x] After reboot, verify internet and locale:
  ```bash
  ping -c 3 google.com
  locale  # Should show en_US.UTF-8
  ```

### Session Complete When
- Both Windows 11 and Ubuntu 24.04 boot from GRUB menu
- NVIDIA GPU visible in Ubuntu via `lspci`
- System fully updated, internet working

---

## Session 02 — ROS2 Jazzy + Gazebo Harmonic (~3 hrs)

### Recommended Reading
- [ROS2 Jazzy install on Ubuntu 24.04](https://docs.ros.org/en/jazzy/Installation/Ubuntu-Install-Debs.html) — official, follow exactly
- [Gazebo Harmonic install](https://gazebosim.org/docs/harmonic/install_ubuntu/) — separate from ROS2
- [CycloneDDS with Nav2](https://docs.nav2.org/tutorials/docs/get_started.html) — why CycloneDDS over FastRTPS

### Prerequisites
- Session 01 complete
- Running in Ubuntu (not WSL)

### Steps

- [x] **Set locale:**
  ```bash
  sudo apt update && sudo apt install locales -y
  sudo locale-gen en_US en_US.UTF-8
  sudo update-locale LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8
  export LANG=en_US.UTF-8
  ```

- [x] **Add ROS2 apt repo:**
  ```bash
  sudo apt install software-properties-common curl -y
  sudo add-apt-repository universe
  sudo curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key \
    -o /usr/share/keyrings/ros-archive-keyring.gpg
  echo "deb [arch=$(dpkg --print-architecture) \
    signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] \
    http://packages.ros.org/ros2/ubuntu \
    $(. /etc/os-release && echo $UBUNTU_CODENAME) main" | \
    sudo tee /etc/apt/sources.list.d/ros2.list > /dev/null
  sudo apt update
  ```

- [x] **Install ROS2 Jazzy Desktop + dev tools:**
  ```bash
  sudo apt install ros-jazzy-desktop ros-dev-tools -y
  ```

- [x] **Install CycloneDDS (Nav2-recommended DDS):**
  ```bash
  sudo apt install ros-jazzy-rmw-cyclonedds-cpp -y
  ```

- [x] **Install Nav2 + slam_toolbox:**
  ```bash
  sudo apt install ros-jazzy-navigation2 ros-jazzy-nav2-bringup -y
  sudo apt install ros-jazzy-slam-toolbox -y
  ```

- [x] **Add ROS2 + CycloneDDS to .bashrc:**
  ```bash
  echo "source /opt/ros/jazzy/setup.bash" >> ~/.bashrc
  echo "export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp" >> ~/.bashrc
  source ~/.bashrc
  ```

- [x] **Add Gazebo Harmonic apt repo:**
  ```bash
  sudo curl https://packages.osrfoundation.org/gazebo.gpg \
    --output /usr/share/keyrings/pkgs-osrf-archive-keyring.gpg
  echo "deb [arch=$(dpkg --print-architecture) \
    signed-by=/usr/share/keyrings/pkgs-osrf-archive-keyring.gpg] \
    http://packages.osrfoundation.org/gazebo/ubuntu-stable \
    $(lsb_release -cs) main" | \
    sudo tee /etc/apt/sources.list.d/gazebo-stable.list > /dev/null
  sudo apt-get update
  ```

- [x] **Install Gazebo Harmonic + ROS2-Gazebo bridge:**
  ```bash
  sudo apt-get install gz-harmonic -y
  sudo apt install ros-jazzy-ros-gz -y
  ```

- [x] **Install ros2_control + teleop (needed for SLAM map-building later):**
  ```bash
  sudo apt install ros-jazzy-ros2-control ros-jazzy-ros2-controllers -y
  sudo apt install ros-jazzy-teleop-twist-keyboard -y
  ```

- [x] **Verify everything:**
  ```bash
  ros2 pkg xml ros2cli | grep version
  # ros2cli 0.x.x (Jazzy)

  gz sim --version
  # Gazebo Harmonic 8.x.x

  echo $RMW_IMPLEMENTATION
  # rmw_cyclonedds_cpp

  ros2 pkg list | grep nav2
  # Should show multiple nav2_* packages
  ```

- [x] **Quick smoke test — launch Gazebo:**
  ```bash
  gz sim shapes.sdf
  # Should open Gazebo with some shapes. Close it.
  ```

- [x] **Quick smoke test — ROS2 talker/listener:**
  ```bash
  # Terminal 1
  ros2 run demo_nodes_py talker
  # Terminal 2
  ros2 run demo_nodes_py listener
  # Should see "Hello World: N" messages. Ctrl+C both.
  ```

### Session Complete When
- `ros2 --version` and `gz sim --version` both return without error
- `$RMW_IMPLEMENTATION` = `rmw_cyclonedds_cpp`
- Talker/listener demo works
- Gazebo opens without crashing

---

## Session 03 — Docker + Tools + GitHub CLI (~3 hrs)

### Recommended Reading
- [Docker Engine install on Ubuntu](https://docs.docker.com/engine/install/ubuntu/) — use the apt repository method, not Snap
- [Docker buildx for multi-arch](https://docs.docker.com/build/building/multi-platform/) — understand QEMU emulation vs native arm64


### Prerequisites
- Session 02 complete

### Steps

- [x] **Install Docker Engine (not Docker Desktop):**
  ```bash
  sudo apt-get install ca-certificates curl gnupg -y
  sudo install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
    sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  sudo chmod a+r /etc/apt/keyrings/docker.gpg

  echo "deb [arch=$(dpkg --print-architecture) \
    signed-by=/etc/apt/keyrings/docker.gpg] \
    https://download.docker.com/linux/ubuntu \
    $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
    sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

  sudo apt-get update
  sudo apt-get install docker-ce docker-ce-cli containerd.io \
    docker-buildx-plugin docker-compose-plugin -y
  ```

- [x] **Add user to docker group (avoids sudo on every docker command):**
  ```bash
  sudo usermod -aG docker $USER
  newgrp docker
  # Verify:
  docker run hello-world
  ```

- [x] **Set up buildx for arm64 cross-compilation:**
  ```bash
  # Enable QEMU binfmt support (lets x86 machine run arm64 binaries)
  sudo apt-get install qemu-user-static -y
  docker run --rm --privileged multiarch/qemu-user-static --reset -p yes

  # Create and activate a multi-arch builder
  docker buildx create --name multiarch --driver docker-container --use
  docker buildx inspect --bootstrap
  # Should show: Platforms: linux/amd64, linux/arm64, linux/arm/v7, ...
  ```

- [x] **Install GitHub CLI:**
  ```bash
  curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | \
    sudo dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg
  sudo chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg
  echo "deb [arch=$(dpkg --print-architecture) \
    signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] \
    https://cli.github.com/packages stable main" | \
    sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null
  sudo apt update && sudo apt install gh -y

  # Authenticate (opens browser):
  gh auth login
  # Choose: GitHub.com → HTTPS → Yes (authenticate Git) → Login with browser
  ```

- [x] **Install Python tools:**
  ```bash
  sudo apt install python3-pip python3-venv python3-colcon-common-extensions -y

  # Create project virtualenv (use this for all Python tools in this project)
  python3 -m venv ~/fleet-env
  echo "source ~/fleet-env/bin/activate" >> ~/.bashrc
  source ~/fleet-env/bin/activate

  pip install --upgrade pip
  pip install pytest pytest-cov pandera pandas numpy scipy \
    streamlit reportlab matplotlib anthropic pyzmq pymupdf
  ```
NOTE: I created a requirements.txt file and then frooze the versions.  pip freeze > requirements.txt

- [x] **Install colcon + rosdep:**
  ```bash
  sudo apt install python3-rosdep -y
  sudo rosdep init
  rosdep update
  ```

- [x] **Install git + configure:**
  ```bash
  sudo apt install git -y
  git config --global user.name "Mike"
  git config --global user.email "sdfinn70@gmail.com"
  git config --global init.defaultBranch main
  ```

- [x] **Verify:**
  ```bash
  docker buildx ls
  # Should show 'multiarch' with linux/arm64 listed

  gh auth status
  # Should show: Logged in to github.com as sdfinn70

  python3 -m pytest --version
  # pytest 8.x.x
  ```

### Session Complete When
- `docker run hello-world` works without sudo
- `docker buildx ls` shows arm64 platform support
- `gh auth status` shows authenticated
- `pytest --version` works in activated virtualenv

---

## Session 04 — GitHub Repo + Project Skeleton (~3 hrs)

### Recommended Reading
- [ROS2 Python package creation](https://docs.ros.org/en/jazzy/Tutorials/Beginner-Client-Libraries/Creating-Your-First-ROS2-Package.html) — understand package.xml and setup.py before writing them
- [colcon build basics](https://colcon.readthedocs.io/en/released/user/quick-start.html) — understand workspace vs package

### Prerequisites
- Session 03 complete
- GitHub account authenticated via `gh`

### Create the Repo

- [x] **Create private repo on GitHub:**
  ```bash
  cd ~
  gh repo create autonomous-fleet-testbed \
    --private \
    --description "CI/CD-native fleet simulation testing framework for autonomous robots" \
    --clone
  cd autonomous-fleet-testbed
  ```

### Create Directory Structure

- [x] **Create all directories:**
  ```bash
  mkdir -p src/nav_fleet/nav_fleet
  mkdir -p tools
  mkdir -p tests
  mkdir -p dashboard
  mkdir -p config
  mkdir -p worlds
  mkdir -p urdf
  mkdir -p maps
  mkdir -p requirements
  mkdir -p robot_profiles
  mkdir -p reports/history
  mkdir -p .github/workflows
  mkdir -p docs
  touch maps/.gitkeep
  touch reports/history/.gitkeep
  ```

### Create Core Config Files

- [x] **Create `.gitignore`:**
  ```bash
  cat > .gitignore << 'EOF'
  # ROS2 colcon build artifacts
  build/
  install/
  log/

  # Python
  __pycache__/
  *.pyc
  *.pyo
  .pytest_cache/
  *.egg-info/
  dist/

  # Virtualenv
  fleet-env/

  # Databases
  *.db
  *.sqlite3

  # Generated reports
  reports/*.pdf
  reports/*.html

  # Generated maps (from SLAM)
  maps/*.pgm
  maps/*.yaml
  !maps/.gitkeep

  # Environment secrets
  .env
  *.env

  # IDE
  .vscode/settings.json
  .idea/

  # OS
  .DS_Store
  Thumbs.db
  EOF
  ```

- [x] **Create `robot_profiles/jetson_ugv_pt.yaml`:**
  ```bash
  cat > robot_profiles/jetson_ugv_pt.yaml << 'EOF'
  name: jetson_ugv_pt
  compute_tier: edge_gpu
  target_arch: arm64
  jetpack_version: "7.2"
  ubuntu_version: "24.04"
  cuda_version: "13"
  nav_stack: nav2_full
  namespace: /robot_001

  sensors:
    lidar:
      model: d500
      topic: /robot_001/scan
      hz_min: 10
    camera:
      model: oak_d_lite
      topic: /robot_001/camera/image_raw
      hz_min: 10
    depth:
      model: oak_d_lite
      topic: /robot_001/camera/depth/points
    imu:
      topic: /robot_001/imu/data
      hz_min: 200
    odometry:
      topic: /robot_001/odom
      hz_min: 50

  sub_controller:
    type: esp32
    interface: uart
    baud: 921600
    watchdog_timeout_ms: 200

  deploy:
    method: ssh
    runner_label: self-hosted-jetson
  EOF
  ```

- [x] **Create `config/drift_config.yaml`:**
  ```bash
  cat > config/drift_config.yaml << 'EOF'
  # Drift detection thresholds. Edit here — never hardcode in Python.
  history_window: 20

  sigma:
    info: 2.0
    warning: 3.0
    error: 4.0
    critical: 5.0

  post_merge_sensitivity:
    runs: 5
    multiplier: 0.7   # tighten thresholds for first 5 runs after a commit

  metrics:
    nav_success_rate:
      direction: down     # lower = worse
      threshold_fail: 0.05
      requirement: BR-07

    mean_position_error:
      direction: up       # higher = worse
      threshold_fail: 0.03
      requirement: BR-01

    mean_time_to_goal:
      direction: up
      threshold_fail: 5.0

    collision_rate:
      direction: up
      threshold_fail: 0.02
      requirement: BR-02

    odom_hz_mean:
      direction: down
      threshold_fail: 5.0
      requirement: BR-04

    lidar_hz_mean:
      direction: down
      threshold_fail: 1.0
      requirement: SC-04

    camera_hz_mean:
      direction: down
      threshold_fail: 1.0
      requirement: SC-05

    firmware_test_pass_rate:
      direction: down
      hard_threshold: true    # any failure = fail; bypasses sigma analysis
      threshold_fail: 0.0
      requirement: MCU-all

    stage_2_arm64_build_s:
      direction: up
      threshold_warn: 60.0    # warn only — slow build is a signal, not a blocker
      ci_health: true

    stage_3_gazebo_s:
      direction: up
      threshold_warn: 30.0
      ci_health: true
  EOF
  ```

- [x] **Create `requirements/brain_requirements.md`:**
  ```bash
  cat > requirements/brain_requirements.md << 'EOF'
  # Brain (Navigation) Requirements

  | ID | Requirement | Test Method |
  |---|---|---|
  | BR-01 | Robot reaches goal within 0.15m Euclidean distance | Automated assertion per run |
  | BR-02 | Zero collisions per navigation run | Collision count assertion |
  | BR-03 | Recovery behavior completes within 10s if triggered | Timed assertion on recovery |
  | BR-04 | /robot_001/odom publishes at >= 50 Hz | Hz measurement over 10s window |
  | BR-07 | nav_success_rate >= 95% over rolling 20 runs | Drift detector |
  | BR-10 | Nav2 behavior tree returns SUCCESS | BT status assertion |
  'EOF'
  ```

- [x] **Create `requirements/scene_requirements.md`:**
  ```bash
  cat > requirements/scene_requirements.md << 'EOF'
  # Scene (Environment) Requirements

  | ID | Requirement | Test Method |
  |---|---|---|
  | SC-01 | World includes at least 2 obstacles placed within robot path | SDF world assertion |
  | SC-02 | Robot start position >= 2m from goal | Distance assertion at spawn |
  | SC-03 | At least 1 perturbation axis varied per test run (friction, lighting, or obstacle placement) | Perturbation matrix config check |
  | SC-04 | /robot_001/scan publishes at >= 10 Hz | Hz measurement |
  | SC-05 | /robot_001/camera/image_raw publishes at >= 10 Hz | Hz measurement |
  EOF
  ```

- [x] **Create `requirements/traceability.yaml`:**
  ```bash
  cat > requirements/traceability.yaml << 'EOF'
  # Every requirement ID must map to at least one test.
  # check_traceability.py fails CI if any ID is uncovered.

  requirements:
    - id: BR-01
      tests:
        - tests/test_navigation.py::test_goal_position_error
    - id: BR-02
      tests:
        - tests/test_navigation.py::test_zero_collisions
    - id: BR-03
      tests:
        - tests/test_navigation.py::test_recovery_timeout
    - id: BR-04
      tests:
        - tests/test_ros2_contracts.py::test_odom_hz
    - id: BR-07
      tests:
        - tests/test_baseline.py::test_nav_success_rate_drift
    - id: BR-10
      tests:
        - tests/test_navigation.py::test_bt_success
    - id: SC-04
      tests:
        - tests/test_ros2_contracts.py::test_lidar_hz
    - id: SC-05
      tests:
        - tests/test_ros2_contracts.py::test_camera_hz
  EOF
  ```

### Create ROS2 Package

- [x] **Create `src/nav_fleet/package.xml`:**
  ```bash
  cat > src/nav_fleet/package.xml << 'EOF'
  <?xml version="1.0"?>
  <?xml-model href="http://download.ros.org/schema/package_format3.xsd" schematypens="http://www.w3.org/2001/XMLSchema"?>
  <package format="3">
    <name>nav_fleet</name>
    <version>0.1.0</version>
    <description>Fleet navigation test harness</description>
    <maintainer email="sdfinn70@gmail.com">Mike</maintainer>
    <license>MIT</license>

    <depend>rclpy</depend>
    <depend>std_msgs</depend>
    <depend>geometry_msgs</depend>
    <depend>nav_msgs</depend>
    <depend>sensor_msgs</depend>
    <depend>nav2_msgs</depend>
    <depend>action_msgs</depend>

    <test_depend>ament_copyright</test_depend>
    <test_depend>ament_flake8</test_depend>
    <test_depend>ament_pep257</test_depend>
    <test_depend>pytest</test_depend>

    <export>
      <build_type>ament_python</build_type>
    </export>
  </package>
  EOF
  ```

- [x] **Create `src/nav_fleet/setup.py`:**
  ```bash
  cat > src/nav_fleet/setup.py << 'EOF'
  from setuptools import find_packages, setup

  package_name = 'nav_fleet'

  setup(
      name=package_name,
      version='0.1.0',
      packages=find_packages(exclude=['test']),
      data_files=[
          ('share/ament_index/resource_index/packages',
           ['resource/' + package_name]),
          ('share/' + package_name, ['package.xml']),
          ('share/' + package_name + '/config',
           ['config/nav2_params.yaml', 'config/drift_config.yaml']),
      ],
      install_requires=['setuptools'],
      zip_safe=True,
      maintainer='Mike',
      maintainer_email='sdfinn70@gmail.com',
      description='Fleet navigation test harness',
      license='MIT',
      entry_points={
          'console_scripts': [
              'nav_runner = nav_fleet.nav_runner:main',
              'metrics_collector = nav_fleet.metrics_collector:main',
          ],
      },
  )
  EOF
  ```

- [x] **Create `src/nav_fleet/setup.cfg`:**
  ```bash
  cat > src/nav_fleet/setup.cfg << 'EOF'
  [develop]
  script_dir=$base/lib/nav_fleet
  [install]
  install_scripts=$base/lib/nav_fleet
  EOF
  ```

- [x] **Create resource marker and `__init__.py`:**
  ```bash
  mkdir -p src/nav_fleet/resource
  touch src/nav_fleet/resource/nav_fleet
  touch src/nav_fleet/nav_fleet/__init__.py
  ```

- [x] **Stub out the two entry point modules (real code comes in Session 09):**
  ```bash
  cat > src/nav_fleet/nav_fleet/nav_runner.py << 'EOF'
  """Nav2 goal-sending test runner. Implemented in Session 09."""


  def main():
      print("nav_runner stub — implement in Session 09")
  EOF

  cat > src/nav_fleet/nav_fleet/metrics_collector.py << 'EOF'
  """ROS2 topic Hz + collision metric collector. Implemented in Session 09."""


  def main():
      print("metrics_collector stub — implement in Session 09")
  EOF
  ```

- [x] **Create `src/nav_fleet/test/` (ament lint tests):**
  ```bash
  mkdir -p src/nav_fleet/test
  cat > src/nav_fleet/test/test_copyright.py << 'EOF'
  import pytest
  from ament_copyright.main import main


  @pytest.mark.linter
  @pytest.mark.copyright
  def test_copyright():
      rc = main(argv=['.', 'test'])
      assert rc == 0, 'Found copyright errors'
  EOF

  cat > src/nav_fleet/test/test_flake8.py << 'EOF'
  import pytest
  from ament_flake8.main import main_with_errors


  @pytest.mark.linter
  @pytest.mark.flake8
  def test_flake8():
      rc, errors = main_with_errors(argv=[])
      assert rc == 0, f'Found flake8 errors:\n' + '\n'.join(errors)
  EOF
  ```

### Create CLAUDE.md Starter

- [x] **Create `CLAUDE.md`:**
  ```bash
  cat > CLAUDE.md << 'EOF'
  # autonomous-fleet-testbed — Claude Code Context

  ## Project
  Open-source CI/CD-native fleet simulation testing framework for autonomous robots.
  Master brief: see BLUEPRINT.md in this repo (or G:\BC\MasterBrief.md on Windows).

  ## Environment
  - Ubuntu 24.04 bare metal (dual boot with Windows 11)
  - ROS2 Jazzy + Gazebo Harmonic + CycloneDDS
  - Python virtualenv: ~/fleet-env (activate before running Python tools)
  - Colcon workspace: ~/autonomous-fleet-testbed/ (build from here)

  ## Key Commands
  ```bash
  # Build ROS2 package
  cd ~/autonomous-fleet-testbed
  colcon build --symlink-install
  source install/setup.bash

  # Run Python tests (activate venv first)
  source ~/fleet-env/bin/activate
  python -m pytest tests/ -v

  # Run traceability gate
  python tools/check_traceability.py requirements/traceability.yaml tests/

  # Launch Gazebo world (Session 09+)
  ros2 launch nav_fleet sim_launch.py

  # Dashboard
  streamlit run dashboard/app.py
  ```

  ## Directory Layout
  - `src/nav_fleet/`  — ROS2 colcon package (nav runner, metrics collector)
  - `tools/`          — Python utilities (baseline monitor, telemetry logger, etc.)
  - `tests/`          — pytest test suite
  - `config/`         — nav2_params.yaml, drift_config.yaml
  - `worlds/`         — Gazebo SDF world files
  - `urdf/`           — Robot URDF/xacro files
  - `robot_profiles/` — Per-robot capability YAML
  - `requirements/`   — Traceability matrix and requirement specs
  - `reports/history/`— CI run JSON reports (drift detection reads from here)
  - `.github/workflows/ci.yml` — 6-stage CI pipeline

  ## Gotchas
  - Always `source install/setup.bash` after colcon build
  - RMW_IMPLEMENTATION=rmw_cyclonedds_cpp must be set (in .bashrc)
  - Gazebo Harmonic command is `gz sim`, NOT `ign gazebo`
  - URDF topics must use /robot_001/ namespace
  - Isaac Sim session (Session 12): requires NVIDIA driver 570+ for RTX 5080
  EOF
  ```

### First Commit

- [x] **Initial commit:**
  ```bash
  cd ~/autonomous-fleet-testbed
  git add .
  git commit -m "feat: project skeleton — directories, robot profile, requirements, ROS2 package stub"
  git push -u origin main
  ```

- [x] **Verify on GitHub:** `gh browse` — opens the repo in browser. Confirm all files pushed.

### Session Complete When
- Repo exists on GitHub, all files pushed
- `colcon build` runs without error (package builds, even though nodes are stubs)
- Directory structure matches the layout in CLAUDE.md

---

## Session 05 — File Migration from Current Project (~3 hrs)

### Recommended Reading
- [Pandera schema validation](https://pandera.readthedocs.io/en/stable/dataframe_models.html) — you'll be rewriting schemas; refresh the DataFrameModel syntax
- [SQLite with Python](https://docs.python.org/3/library/sqlite3.html) — baseline_monitor reads from SQLite; understand the connection pattern

### Prerequisites
- Session 04 complete
- Current project accessible at `G:\BC\isaac_project\` (Windows side) OR `/mnt/g/BC/isaac_project/` (accessible from Ubuntu via WSL mount — but you're in bare metal Ubuntu now, so Windows files are on the NTFS partition)

### Access Windows Files from Ubuntu

- [x] **Mount the Windows partition:**  Used GUI
  ```bash
  # Find your Windows partition (usually /dev/sda1 or /dev/nvme0n1p3)
  lsblk
  # Look for a large NTFS partition — that's Windows C:

  sudo mkdir -p /mnt/windows
  sudo mount -t ntfs-3g /dev/nvme0n1p4 /mnt/windows
  # Replace nvme0n1p3 with your actual device name

  # Verify:
  ls /mnt/windows/Users/Mike/
  # Should see Desktop, Documents, etc.

  ls "/mnt/windows/Users/Mike/BC/isaac_project/src/"
  # Should see baseline_monitor.py, telemetry_logger.py, etc.
  ```

- [x] **Copy source files:**
  ```bash
  SRC="/mnt/windows/Users/Mike/BC/isaac_project"
  DEST=~/autonomous-fleet-testbed

  cp "$SRC/src/baseline_monitor.py"        "$DEST/tools/"
  cp "$SRC/src/telemetry_logger.py"        "$DEST/tools/"
  cp "$SRC/src/validate_telemetry.py"      "$DEST/tools/"
  cp "$SRC/src/generate_test_report.py"    "$DEST/tools/"
  cp "$SRC/src/ai_test_generator.py"       "$DEST/tools/"
  cp "$SRC/src/scenario_analyzer.py"       "$DEST/tools/"
  cp "$SRC/src/sim_vs_real_comparison.py"  "$DEST/tools/"    .png?
  cp "$SRC/dashboard/app.py"               "$DEST/dashboard/" 
  cp -r "$SRC/.github/workflows/"          "$DEST/.github/"
  cp "$SRC/tests/test_baseline.py"         "$DEST/tests/"
  cp "$SRC/tests/test_ros2_contracts.py"   "$DEST/tests/"
  ```

### Edit Each Migrated File

The changes below are the minimum needed to run correctly in the new project. Deeper refactoring happens as each stage is built.

- [x] **`tools/telemetry_logger.py`** — Update the schema:
  - Find the `CREATE TABLE` statement. Add these columns if missing:
    ```sql
    runner_type TEXT,        -- 'qemu' | 'jetson' | 'local'
    robot_type TEXT,         -- 'jetson_ugv_pt' | 'rpi_rover' etc.
    camera_hz_mean REAL,
    firmware_test_pass_rate REAL,
    stage_timings_sec TEXT   -- JSON blob: {"stage_2": 45.2, "stage_3": 28.1}
    ```
  - Remove any hardcoded Windows paths (e.g. `G:\\BC\\...`). Replace with:
    ```python
    import os
    DB_PATH = os.environ.get("FLEET_DB", "reports/fleet_runs.db")
    ```

- [x] **`tools/validate_telemetry.py`** — Update Pandera schema class:
  - Find the `DataFrameModel` subclass. Add:
    ```python
    camera_hz_mean: float = pa.Field(ge=0)
    firmware_test_pass_rate: float = pa.Field(ge=0, le=1)
    runner_type: str = pa.Field(isin=["qemu", "jetson", "local"])
    robot_type: str = pa.Field()
    ```
  - Remove any Isaac Sim-specific fields (e.g. replicator metrics, USD paths).

- [x] **`tools/baseline_monitor.py`** — Update metrics list:
  - Find the metrics dict/list. Replace with:
    ```python
    METRICS = {
        "nav_success_rate":        "down",
        "mean_position_error":     "up",
        "mean_time_to_goal":       "up",
        "collision_rate":          "up",
        "odom_hz_mean":            "down",
        "lidar_hz_mean":           "down",
        "camera_hz_mean":          "down",
    }
    HARD_THRESHOLD_METRICS = {"firmware_test_pass_rate"}
    ```
  - Update DB path to use `os.environ.get("FLEET_DB", "reports/fleet_runs.db")`
  - Remove Windows path references.

- [x] **`tools/generate_test_report.py`** — Swap metrics:
  - Update any hardcoded metric names to match the new schema above.
  - Remove Windows paths; use relative paths or `FLEET_DB` env var.

- [x] **`tools/ai_test_generator.py`** — Update model and context:
  - Find the `model=` parameter. Confirm it is `"claude-sonnet-4-6"` (should already be current).
  - Update the system prompt context to reference multi-robot fleet scenarios, `/robot_001/` namespace, Gazebo Harmonic, and ROS2 Jazzy. Remove Isaac Sim / OmniGraph references.

- [x] **`tools/scenario_analyzer.py`** — Update scoring rubric:
  - Update any scenario scoring logic to evaluate fleet/coverage scenarios rather than single-robot Isaac Sim scenarios. Specific changes depend on the file content — the key is ensuring coverage % and multi-robot coordination are scored.

- [x] **`tools/sim_vs_real_comparison.py`** — Update metrics and DB paths:
  - Update metric names to match new schema.
  - Ensure the function accepts two DB paths (one for sim runs, one for real runs) — this enables apples-to-apples comparison in Stage 6.
  NOTE: This was missing and has been recreated.

- [x] **`dashboard/app.py`** — Add filter fields:
  - Find the Streamlit sidebar or filter widgets. Add:
    ```python
    robot_type_filter = st.sidebar.selectbox("Robot Type", ["All", "jetson_ugv_pt"])
    runner_type_filter = st.sidebar.selectbox("Runner", ["All", "qemu", "jetson", "local"])
    ```
  - Update any hardcoded metric column names to match the new schema.

- [x] **`tests/test_baseline.py`** — Update metric names:
  - Replace old metric names (whatever they were in the Isaac Sim project) with the new schema: `nav_success_rate`, `mean_position_error`, `collision_rate`, `odom_hz_mean`, `camera_hz_mean`.
  - Keep the pytest fixture structure — it's the pattern worth reusing.

- [x] **`tests/test_ros2_contracts.py`** — Update namespace:
  - Replace any `/odom`, `/scan`, `/camera` topic references with `/robot_001/odom`, `/robot_001/scan`, `/robot_001/camera/image_raw`.
  - Update expected Hz values: odom >= 50, scan >= 10, camera >= 10.

- [x] **`.github/workflows/`** — Stub out (full rewrite in Session 08):
  - Replace all workflow content with a minimal stub that just runs `echo "CI stub"` for each job. This lets the pipeline exist and trigger without failing on unbuilt stages.
  ```bash
  cat > .github/workflows/ci.yml << 'EOF'
  name: Fleet CI

  on:
    push:
      branches: [main]
    pull_request:
      branches: [main]

  jobs:
    stage-0-requirements:
      runs-on: ubuntu-latest
      steps:
        - uses: actions/checkout@v4
        - run: echo "Stage 0 stub — implement in Session 06"

    stage-1-quality:
      runs-on: ubuntu-latest
      needs: stage-0-requirements
      steps:
        - uses: actions/checkout@v4
        - run: echo "Stage 1 stub — implement in Session 07"

    stage-2-arm64:
      runs-on: ubuntu-latest
      needs: stage-1-quality
      steps:
        - uses: actions/checkout@v4
        - run: echo "Stage 2 stub — implement in Session 08"

    stage-3-gazebo:
      runs-on: ubuntu-latest
      needs: stage-2-arm64
      steps:
        - uses: actions/checkout@v4
        - run: echo "Stage 3 stub — implement in Session 09"
  EOF
  ```

- [x] **Create `tests/conftest.py`:**
  ```bash
  cat > tests/conftest.py << 'EOF'
  """Pytest fixtures for fleet testbed tests."""
  import os
  import pytest
  import sqlite3


  @pytest.fixture
  def db_path(tmp_path):
      """In-memory SQLite DB for tests that need telemetry data."""
      db = tmp_path / "test_fleet.db"
      return str(db)


  @pytest.fixture
  def sample_run():
      """Minimal valid run dict matching the telemetry schema."""
      return {
          "run_id": "test-001",
          "robot_type": "jetson_ugv_pt",
          "runner_type": "local",
          "nav_success_rate": 1.0,
          "mean_position_error": 0.05,
          "mean_time_to_goal": 12.3,
          "collision_rate": 0.0,
          "odom_hz_mean": 52.1,
          "lidar_hz_mean": 10.2,
          "camera_hz_mean": 10.1,
          "firmware_test_pass_rate": 1.0,
          "stage_timings_sec": '{"stage_2": 45.2, "stage_3": 28.1}',
      }
  EOF
  ```

- [x] **Commit:**
  ```bash
  cd ~/autonomous-fleet-testbed
  git add .
  git commit -m "feat: migrate 11 files from isaac_project — schema updates, namespace fixes, path cleanup"
  git push
  ```

### Session Complete When
- All 11 files present in `tools/`, `dashboard/`, `tests/`, `.github/workflows/`
- No hardcoded Windows paths remain in any migrated file
- `python -m pytest tests/test_baseline.py -v` runs (may fail on missing DB — that's fine; it should not crash with import errors)
- `python tools/baseline_monitor.py --help` (or equivalent) runs without import errors

---

## Session 06 — Stage 0: Requirements Gate (~3 hrs)

### Recommended Reading
- [YAML in Python (PyYAML)](https://pyyaml.org/wiki/PyYAMLDocumentation) — you'll parse traceability.yaml
- [argparse tutorial](https://docs.python.org/3/howto/argparse.html) — check_traceability.py is a CLI tool

### Prerequisites
- Session 05 complete

### Goal
`check_traceability.py` reads `traceability.yaml` and scans test files. If any requirement ID has no matching test function, it exits non-zero and CI fails.

### Steps

- [x] **Create `tools/check_traceability.py`:**
  ```python
  #!/usr/bin/env python3
  """Stage 0 CI gate: every requirement ID must map to a test that exists."""
  import argparse
  import ast
  import sys
  from pathlib import Path

  import yaml


  def get_test_functions(test_dir: Path) -> set[str]:
      """Return all 'module::function' test IDs found in test_dir."""
      found = set()
      for test_file in test_dir.rglob("test_*.py"):
          rel = test_file.relative_to(test_dir.parent)
          try:
              tree = ast.parse(test_file.read_text())
          except SyntaxError:
              continue
          for node in ast.walk(tree):
              if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                  found.add(f"{rel}::{node.name}")
      return found


  def check(traceability_path: Path, test_dir: Path, profile_path: Path | None) -> int:
      data = yaml.safe_load(traceability_path.read_text())
      existing = get_test_functions(test_dir)

      # Optional: filter requirements by robot profile capabilities
      skip_ids: set[str] = set()
      if profile_path and profile_path.exists():
          profile = yaml.safe_load(profile_path.read_text())
          if profile.get("nav_stack") != "nav2_full":
              # Lightweight profile: skip Nav2-specific requirements
              skip_ids = {"BR-03", "BR-10"}

      failures = []
      for req in data["requirements"]:
          rid = req["id"]
          if rid in skip_ids:
              print(f"  SKIP {rid} (not applicable for this robot profile)")
              continue
          for test_ref in req["tests"]:
              if test_ref not in existing:
                  failures.append(f"  MISSING {rid}: {test_ref}")
              else:
                  print(f"  OK    {rid}: {test_ref}")

      if failures:
          print("\nTraceability failures:")
          for f in failures:
              print(f)
          return 1
      print(f"\nAll {len(data['requirements'])} requirements covered.")
      return 0


  def main():
      parser = argparse.ArgumentParser(description="Stage 0 traceability gate")
      parser.add_argument("traceability", help="Path to traceability.yaml")
      parser.add_argument("test_dir", help="Path to tests/ directory")
      parser.add_argument("--profile", help="Optional robot_profiles/*.yaml to filter requirements")
      args = parser.parse_args()

      profile = Path(args.profile) if args.profile else None
      rc = check(Path(args.traceability), Path(args.test_dir), profile)
      sys.exit(rc)


  if __name__ == "__main__":
      main()
  ```

- [x] **Test it locally:**
  ```bash
  cd ~/autonomous-fleet-testbed
  python tools/check_traceability.py requirements/traceability.yaml tests/
  # Expected: MISSING lines for tests not yet written — that's correct for now.
  # The tool itself must not crash. Exit code 1 is expected until Session 09.
  ```

- [x] **Wire Stage 0 into CI:**
  Edit `.github/workflows/ci.yml` — replace the Stage 0 stub job:
  ```yaml
  stage-0-requirements:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pip install pyyaml
      - name: Traceability gate
        run: |
          python tools/check_traceability.py \
            requirements/traceability.yaml \
            tests/ \
            --profile robot_profiles/jetson_ugv_pt.yaml
        continue-on-error: true   # Remove this once all tests are written (Session 10)
  ```

  > **Note:** `continue-on-error: true` on Stage 0 is intentional while tests are being built out. Remove it in Session 10 when Stage 3 tests pass.

- [x] **Add PyYAML to a requirements.txt:**
  ```bash
  cat > requirements.txt << 'EOF'
  pyyaml>=6.0
  pandera>=0.18
  pandas>=2.0
  numpy>=1.26
  scipy>=1.12
  streamlit>=1.33
  reportlab>=4.0
  matplotlib>=3.8
  anthropic>=0.25
  pymupdf>=1.24
  EOF
  ```

- [x] **Commit:**
  ```bash
  git add .
  git commit -m "feat: Stage 0 traceability gate — check_traceability.py + requirements.txt + CI job"
  git push
  ```

- [x] **Verify CI triggers on GitHub:**
  ```bash
  gh run list --limit 5
  # Should show the push triggered a workflow run
  gh run view   # pick the run ID from above
  ```

### Session Complete When
- `check_traceability.py` runs locally without crashing
- CI workflow triggers on push and Stage 0 job completes (even with `continue-on-error`)
- `gh run list` shows a green (or yellow `continue-on-error`) pipeline

---

## Session 07 — Stage 1: Code Quality Gate (~3 hrs)

### Recommended Reading
- [ament_lint for Python packages](https://docs.ros.org/en/jazzy/Contributing/Code-Style-Language-Versions.html) — the linting suite ROS2 uses
- [GitHub Actions: needs and job dependencies](https://docs.github.com/en/actions/writing-workflows/choosing-what-your-workflow-does/using-jobs-in-a-workflow) — understand the `needs:` key

### Prerequisites
- Session 06 complete

### Steps

- [x] **Install ament linting tools:**
  ```bash
  sudo apt install ros-jazzy-ament-lint-auto ros-jazzy-ament-flake8 \
    ros-jazzy-ament-pep257 ros-jazzy-ament-copyright -y
  pip install flake8 pep257
  ```

- [x] **Run ament lint locally on the ROS2 package:**
  ```bash
  cd ~/autonomous-fleet-testbed
  colcon build --symlink-install
  source install/setup.bash
  colcon test --packages-select nav_fleet
  colcon test-result --verbose
  # Fix any flake8/copyright lint errors reported
  ```
  NOTE: `colcon test` uses `python -m unittest` (not pytest) for ament_python packages — requires
  `python3-colcon-pytest` (apt only) to route through pytest. Tests pass via `python -m pytest test/`
  directly and via `python -m unittest discover test/`. All 40 pytest tests pass locally.

- [x] **Common lint fixes:**
  - Apache 2.0 full header required on all nav_fleet files (ament_copyright rejects MIT shorthand).
    Used the standard 13-line Apache 2.0 block on `__init__.py`, `nav_runner.py`,
    `metrics_collector.py`, `test_copyright.py`, `test_flake8.py`.
  - Fixed W293 trailing whitespace, E501 long lines, E302/E305 spacing, F401 unused imports,
    E402 noqa on sys.path manipulation, E127 over-indented continuation across tools/ and tests/.
  - Fixed broken 2-space leading indent in `setup.cfg` and both ament test files (heredoc artifact
    from Session 04 creation).
  - Rewrote ament test files as `unittest.TestCase` so they work under both `python -m unittest`
    (colcon) and pytest.

- [x] **Wire Stage 1 into CI** — replace the Stage 1 stub job in `ci.yml`:
  ```yaml
  stage-1-quality:
    runs-on: ubuntu-latest
    needs: stage-0-requirements
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: Install ROS2 + ament lint
        run: |
          sudo apt-get update -qq
          sudo apt-get install -y \
            ros-jazzy-ament-flake8 \
            ros-jazzy-ament-pep257 \
            ros-jazzy-ament-copyright
      - name: Lint nav_fleet package
        run: |
          source /opt/ros/jazzy/setup.bash
          cd src/nav_fleet
          python -m flake8 nav_fleet/ --max-line-length=99
          python -m flake8 test/ --max-line-length=99
      - name: Run Python unit tests (tools/)
        run: |
          pip install -r requirements.txt
          python -m pytest tools/ tests/ -v \
            --ignore=tests/test_ros2_contracts.py \
            -k "not integration"
  ```

  > **Note:** `test_ros2_contracts.py` requires a running ROS2 environment — excluded here, included in Stage 3.

- [x] **Commit and verify CI:**
  ```bash
  git add .
  git commit -m "feat: Stage 1 code quality gate — ament lint + pytest in CI"
  git push
  gh run watch   # watch the pipeline live
  ```
  NOTE: Required a second fix commit — flake8 not available in the actions/setup-python env
  until pip install runs. Fixed by moving `pip install -r requirements-ci.txt flake8` before
  the lint step. All 4 stages green on final run (Stage 0: 39s, Stage 1: 54s).

### Session Complete When
- `colcon test` passes locally for `nav_fleet` package
- Stage 1 CI job passes (green) in GitHub Actions
- `gh run list` shows both Stage 0 and Stage 1 completing

---

## Session 08 — Stage 2: arm64 Cross-Compile + QEMU Baseline (~3 hrs)

### Recommended Reading
- [Docker multi-arch builds](https://docs.docker.com/build/building/multi-platform/) — specifically the QEMU emulation section
- [ROS2 Docker images on GHCR](https://github.com/ros/rosdistro/blob/master/ros2/distros/jazzy.yaml) — understand the `ros:jazzy` base image

### Prerequisites
- Session 07 complete
- `docker buildx ls` shows arm64 platform (from Session 03)

### Steps

- [x] **Create `Dockerfile`:**
  ```dockerfile
  # Dockerfile — arm64 ROS2 Jazzy nav_fleet build
  FROM ros:jazzy-ros-base

  SHELL ["/bin/bash", "-c"]

  # System deps
  RUN apt-get update && apt-get install -y \
      python3-pip \
      ros-jazzy-navigation2 \
      ros-jazzy-nav2-bringup \
      ros-jazzy-rmw-cyclonedds-cpp \
      && rm -rf /var/lib/apt/lists/*

  # Python deps
  COPY requirements.txt /tmp/requirements.txt
  RUN pip3 install --no-cache-dir -r /tmp/requirements.txt

  # Set DDS
  ENV RMW_IMPLEMENTATION=rmw_cyclonedds_cpp

  # Copy workspace
  WORKDIR /ros2_ws
  COPY src/ src/

  # Build
  RUN source /opt/ros/jazzy/setup.bash && \
      colcon build --symlink-install \
      && rm -rf build/ log/

  # Source on container start
  RUN echo "source /opt/ros/jazzy/setup.bash" >> /root/.bashrc && \
      echo "source /ros2_ws/install/setup.bash" >> /root/.bashrc

  CMD ["/bin/bash"]
  ```

- [x] **Build arm64 image locally (QEMU — this is slow, ~25–30 min, record the time):**
  ```bash
  cd ~/autonomous-fleet-testbed

  # Record start time
  START=$(date +%s)

  docker buildx build \
    --platform linux/arm64 \
    --tag ghcr.io/sdfinn/autonomous-fleet-testbed:latest \
    --load \
    .

  # Record end time
  END=$(date +%s)
  echo "arm64 build time (QEMU): $((END - START)) seconds"
  # Write this number down — it's the baseline for Phase B comparison
  ```

- [x] **Push image to GitHub Container Registry:**
  ```bash
  # Authenticate with GHCR
  echo $GITHUB_TOKEN | docker login ghcr.io -u sdfinn70 --password-stdin
  # If you don't have GITHUB_TOKEN, create a PAT at github.com → Settings → Developer settings → PATs
  # Scope: write:packages, read:packages

  docker push ghcr.io/sdfinn/autonomous-fleet-testbed:latest
  ```

- [x] **Wire Stage 2 into CI** — replace the Stage 2 stub job in `ci.yml`:
  ```yaml
  stage-2-arm64:
    runs-on: ubuntu-latest
    needs: stage-1-quality
    permissions:
      packages: write
    steps:
      - uses: actions/checkout@v4

      - name: Set up QEMU
        uses: docker/setup-qemu-action@v3

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Log in to GHCR
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Record start time
        run: echo "BUILD_START=$(date +%s)" >> $GITHUB_ENV

      - name: Build and push arm64 image
        uses: docker/build-push-action@v5
        with:
          context: .
          platforms: linux/arm64
          push: true
          tags: ghcr.io/${{ github.repository }}:${{ github.sha }}
          cache-from: type=gha
          cache-to: type=gha,mode=max

      - name: Record build time
        run: |
          END=$(date +%s)
          BUILD_S=$((END - BUILD_START))
          echo "Stage 2 arm64 build time (QEMU): ${BUILD_S}s"
          echo "stage_2_build_s=${BUILD_S}" >> $GITHUB_STEP_SUMMARY
  ```

- [x] **Commit and let CI run:**
  ```bash
  git add .
  git commit -m "feat: Stage 2 arm64 QEMU cross-compile — Dockerfile + GHA workflow"
  git push

  # Watch CI — Stage 2 will take 25–30 min on QEMU
  gh run watch
  ```

- [x] **Record the QEMU baseline time** from the GHA run summary. This number is the "before" for the Jetson runner upgrade in Phase B.
  NOTE: GHA QEMU cold build = **23m43s** (authoritative baseline). Local workstation QEMU
  (pip+colcon only, apt cached) = 37m23s; full uncached local ~60+ min. Both recorded in
  BLUEPRINT.md Decisions Log 2026-06-28. Two fixes required: (1) `contents: read` missing
  from permissions block; (2) `--ignore-installed` needed for pluggy apt/pip conflict.

### Session Complete When
- `docker buildx build --platform linux/arm64` completes without errors
- Image pushed to `ghcr.io/sdfinn/autonomous-fleet-testbed`
- Stage 2 CI job completes (slow but passing)
- QEMU build time recorded somewhere (in Decisions Log in BLUEPRINT.md)

---

## Session 09 — Stage 3 Part 1: URDF + Nav2 in Gazebo Headless (~3 hrs)

### Recommended Reading
- [URDF tutorial](https://docs.ros.org/en/jazzy/Tutorials/Intermediate/URDF/URDF-Main.html) — links, joints, visual, collision, inertia
- [Gazebo Harmonic + ROS2 integration](https://gazebosim.org/docs/harmonic/ros2_integration/) — how ros_gz bridge wires topics
- [Nav2 Getting Started](https://docs.nav2.org/getting_started/index.html) — first read the architecture overview, then the "Running Nav2" section
- [Waveshare ugv_ws URDF](https://github.com/waveshareteam/ugv_ws) — source URDF for the real robot (use as reference, not as-is)

### Prerequisites
- Session 08 complete
- Understanding of URDF link/joint structure (read the tutorial first)

### Steps

- [x] **Get the Waveshare URDF as a reference:**
  ```bash
  cd ~
  git clone https://github.com/waveshareteam/ugv_ws.git waveshare_ref
  # Browse: ls waveshare_ref/src/
  # Find the URDF files — copy the relevant xacro as a starting point
  ```

- [x] **Create a simplified URDF for Stage 3 (`urdf/ugv_pt.urdf.xacro`):**

  > **Note:** The full Waveshare URDF includes hardware-specific plugins. For Stage 3 (Gazebo only), use a simplified version with Gazebo diff-drive and lidar plugins. Refine to match real hardware specs in Session 18.

  ```xml
  <?xml version="1.0"?>
  <robot name="ugv_pt" xmlns:xacro="http://www.ros.org/wiki/xacro">

    <xacro:property name="base_mass" value="5.0"/>
    <xacro:property name="base_length" value="0.35"/>
    <xacro:property name="base_width" value="0.30"/>
    <xacro:property name="base_height" value="0.15"/>
    <xacro:property name="wheel_radius" value="0.05"/>
    <xacro:property name="wheel_width" value="0.04"/>
    <xacro:property name="wheel_separation" value="0.28"/>

    <!-- Base link -->
    <link name="base_link">
      <visual>
        <geometry>
          <box size="${base_length} ${base_width} ${base_height}"/>
        </geometry>
        <material name="grey"><color rgba="0.5 0.5 0.5 1.0"/></material>
      </visual>
      <collision>
        <geometry>
          <box size="${base_length} ${base_width} ${base_height}"/>
        </geometry>
      </collision>
      <inertial>
        <mass value="${base_mass}"/>
        <inertia ixx="0.05" ixy="0" ixz="0" iyy="0.05" iyz="0" izz="0.07"/>
      </inertial>
    </link>

    <!-- Left wheel -->
    <link name="left_wheel">
      <visual>
        <geometry><cylinder radius="${wheel_radius}" length="${wheel_width}"/></geometry>
        <material name="black"><color rgba="0.1 0.1 0.1 1.0"/></material>
      </visual>
      <collision>
        <geometry><cylinder radius="${wheel_radius}" length="${wheel_width}"/></geometry>
      </collision>
      <inertial>
        <mass value="0.5"/>
        <inertia ixx="0.001" ixy="0" ixz="0" iyy="0.001" iyz="0" izz="0.002"/>
      </inertial>
    </link>
    <joint name="left_wheel_joint" type="continuous">
      <parent link="base_link"/>
      <child link="left_wheel"/>
      <origin xyz="0 ${wheel_separation/2} -${base_height/2}" rpy="-1.5708 0 0"/>
      <axis xyz="0 0 1"/>
    </joint>

    <!-- Right wheel -->
    <link name="right_wheel">
      <visual>
        <geometry><cylinder radius="${wheel_radius}" length="${wheel_width}"/></geometry>
        <material name="black"><color rgba="0.1 0.1 0.1 1.0"/></material>
      </visual>
      <collision>
        <geometry><cylinder radius="${wheel_radius}" length="${wheel_width}"/></geometry>
      </collision>
      <inertial>
        <mass value="0.5"/>
        <inertia ixx="0.001" ixy="0" ixz="0" iyy="0.001" iyz="0" izz="0.002"/>
      </inertial>
    </link>
    <joint name="right_wheel_joint" type="continuous">
      <parent link="base_link"/>
      <child link="right_wheel"/>
      <origin xyz="0 -${wheel_separation/2} -${base_height/2}" rpy="-1.5708 0 0"/>
      <axis xyz="0 0 1"/>
    </joint>

    <!-- Caster (passive, fixed) -->
    <link name="caster">
      <visual><geometry><sphere radius="0.02"/></geometry></visual>
      <collision><geometry><sphere radius="0.02"/></geometry></collision>
      <inertial>
        <mass value="0.1"/>
        <inertia ixx="0.00001" ixy="0" ixz="0" iyy="0.00001" iyz="0" izz="0.00001"/>
      </inertial>
    </link>
    <joint name="caster_joint" type="fixed">
      <parent link="base_link"/>
      <child link="caster"/>
      <origin xyz="${base_length/2 - 0.05} 0 -${base_height/2}"/>
    </joint>

    <!-- LiDAR -->
    <link name="lidar_link">
      <visual><geometry><cylinder radius="0.03" length="0.05"/></geometry></visual>
      <collision><geometry><cylinder radius="0.03" length="0.05"/></geometry></collision>
      <inertial>
        <mass value="0.2"/>
        <inertia ixx="0.0001" ixy="0" ixz="0" iyy="0.0001" iyz="0" izz="0.0001"/>
      </inertial>
    </link>
    <joint name="lidar_joint" type="fixed">
      <parent link="base_link"/>
      <child link="lidar_link"/>
      <origin xyz="0.1 0 ${base_height/2 + 0.025}"/>
    </joint>

    <!-- Camera -->
    <link name="camera_link">
      <visual><geometry><box size="0.02 0.08 0.03"/></geometry></visual>
      <collision><geometry><box size="0.02 0.08 0.03"/></geometry></collision>
      <inertial>
        <mass value="0.1"/>
        <inertia ixx="0.00001" ixy="0" ixz="0" iyy="0.00001" iyz="0" izz="0.00001"/>
      </inertial>
    </link>
    <joint name="camera_joint" type="fixed">
      <parent link="base_link"/>
      <child link="camera_link"/>
      <origin xyz="${base_length/2} 0 ${base_height/2 + 0.015}"/>
    </joint>

    <!-- Gazebo plugins -->
    <gazebo>
      <!-- Differential drive -->
      <plugin filename="gz-sim-diff-drive-system"
              name="gz::sim::systems::DiffDrive">
        <left_joint>left_wheel_joint</left_joint>
        <right_joint>right_wheel_joint</right_joint>
        <wheel_separation>${wheel_separation}</wheel_separation>
        <wheel_radius>${wheel_radius}</wheel_radius>
        <odom_publish_frequency>50</odom_publish_frequency>
        <topic>/robot_001/cmd_vel</topic>
        <odom_topic>/robot_001/odom</odom_topic>
        <tf_topic>/robot_001/tf</tf_topic>
        <frame_id>robot_001/odom</frame_id>
        <child_frame_id>robot_001/base_link</child_frame_id>
      </plugin>

      <!-- Ground truth pose (for test assertions) -->
      <plugin filename="gz-sim-pose-publisher-system"
              name="gz::sim::systems::PosePublisher">
        <publish_link_pose>true</publish_link_pose>
        <publish_model_pose>true</publish_model_pose>
        <use_pose_vector_msg>true</use_pose_vector_msg>
        <static_publisher>false</static_publisher>
        <update_frequency>10</update_frequency>
      </plugin>
    </gazebo>

    <!-- LiDAR sensor -->
    <gazebo reference="lidar_link">
      <sensor name="lidar" type="gpu_lidar">
        <topic>/robot_001/scan</topic>
        <update_rate>10</update_rate>
        <ray>
          <scan>
            <horizontal>
              <samples>360</samples>
              <resolution>1</resolution>
              <min_angle>-3.14159</min_angle>
              <max_angle>3.14159</max_angle>
            </horizontal>
          </scan>
          <range>
            <min>0.12</min>
            <max>12.0</max>
          </range>
          <noise>
            <type>gaussian</type>
            <mean>0.0</mean>
            <stddev>0.01</stddev>
          </noise>
        </ray>
        <always_on>1</always_on>
        <visualize>true</visualize>
      </sensor>
    </gazebo>

    <!-- Camera sensor -->
    <gazebo reference="camera_link">
      <sensor name="camera" type="camera">
        <topic>/robot_001/camera/image_raw</topic>
        <update_rate>10</update_rate>
        <camera>
          <horizontal_fov>1.047</horizontal_fov>
          <image>
            <width>640</width>
            <height>480</height>
            <format>R8G8B8</format>
          </image>
          <clip><near>0.1</near><far>100</far></clip>
        </camera>
        <always_on>1</always_on>
      </sensor>
    </gazebo>

  </robot>
  ```

- [x] **Create a simple bedroom world (`worlds/bedroom_simple.sdf`):**
  ```xml
  <?xml version="1.0"?>
  <sdf version="1.9">
    <world name="bedroom">
      <physics name="default" type="ode">
        <real_time_update_rate>1000</real_time_update_rate>
        <max_step_size>0.001</max_step_size>
      </physics>

      <plugin filename="gz-sim-physics-system"
              name="gz::sim::systems::Physics"/>
      <plugin filename="gz-sim-sensors-system"
              name="gz::sim::systems::Sensors">
        <render_engine>ogre2</render_engine>
      </plugin>
      <plugin filename="gz-sim-scene-broadcaster-system"
              name="gz::sim::systems::SceneBroadcaster"/>
      <plugin filename="gz-sim-user-commands-system"
              name="gz::sim::systems::UserCommands"/>

      <light name="sun" type="directional">
        <cast_shadows>true</cast_shadows>
        <pose>0 0 10 0 0 0</pose>
        <diffuse>0.8 0.8 0.8 1</diffuse>
        <specular>0.2 0.2 0.2 1</specular>
        <direction>-0.5 0.1 -0.9</direction>
      </light>

      <!-- Floor -->
      <model name="floor">
        <static>true</static>
        <link name="link">
          <collision name="collision">
            <geometry><plane><normal>0 0 1</normal><size>10 10</size></plane></geometry>
          </collision>
          <visual name="visual">
            <geometry><plane><normal>0 0 1</normal><size>10 10</size></plane></geometry>
            <material><ambient>0.8 0.7 0.6 1</ambient></material>
          </visual>
        </link>
      </model>

      <!-- North wall -->
      <model name="wall_north">
        <static>true</static>
        <pose>0 3.5 0.5 0 0 0</pose>
        <link name="link">
          <collision name="collision">
            <geometry><box><size>7 0.2 1</size></box></geometry>
          </collision>
          <visual name="visual">
            <geometry><box><size>7 0.2 1</size></box></geometry>
            <material><ambient>0.9 0.9 0.9 1</ambient></material>
          </visual>
        </link>
      </model>

      <!-- South wall -->
      <model name="wall_south">
        <static>true</static>
        <pose>0 -3.5 0.5 0 0 0</pose>
        <link name="link">
          <collision name="collision">
            <geometry><box><size>7 0.2 1</size></box></geometry>
          </collision>
          <visual name="visual">
            <geometry><box><size>7 0.2 1</size></box></geometry>
            <material><ambient>0.9 0.9 0.9 1</ambient></material>
          </visual>
        </link>
      </model>

      <!-- East wall -->
      <model name="wall_east">
        <static>true</static>
        <pose>3.5 0 0.5 0 0 1.5708</pose>
        <link name="link">
          <collision name="collision">
            <geometry><box><size>7 0.2 1</size></box></geometry>
          </collision>
          <visual name="visual">
            <geometry><box><size>7 0.2 1</size></box></geometry>
            <material><ambient>0.9 0.9 0.9 1</ambient></material>
          </visual>
        </link>
      </model>

      <!-- West wall -->
      <model name="wall_west">
        <static>true</static>
        <pose>-3.5 0 0.5 0 0 1.5708</pose>
        <link name="link">
          <collision name="collision">
            <geometry><box><size>7 0.2 1</size></box></geometry>
          </collision>
          <visual name="visual">
            <geometry><box><size>7 0.2 1</size></box></geometry>
            <material><ambient>0.9 0.9 0.9 1</ambient></material>
          </visual>
        </link>
      </model>

      <!-- Obstacle 1 (box — represents furniture) -->
      <model name="obstacle_1">
        <static>true</static>
        <pose>1.0 1.0 0.25 0 0 0</pose>
        <link name="link">
          <collision name="collision">
            <geometry><box><size>0.4 0.4 0.5</size></box></geometry>
          </collision>
          <visual name="visual">
            <geometry><box><size>0.4 0.4 0.5</size></box></geometry>
            <material><ambient>0.4 0.2 0.1 1</ambient></material>
          </visual>
        </link>
      </model>

      <!-- Obstacle 2 -->
      <model name="obstacle_2">
        <static>true</static>
        <pose>-1.0 0.5 0.25 0 0 0</pose>
        <link name="link">
          <collision name="collision">
            <geometry><box><size>0.3 0.6 0.5</size></box></geometry>
          </collision>
          <visual name="visual">
            <geometry><box><size>0.3 0.6 0.5</size></box></geometry>
            <material><ambient>0.3 0.4 0.6 1</ambient></material>
          </visual>
        </link>
      </model>

      <!-- Robot spawn point -->
      <include>
        <uri>model://ugv_pt</uri>
        <name>robot_001</name>
        <pose>-2.0 -2.0 0.1 0 0 0</pose>
      </include>

    </world>
  </sdf>
  ```

- [x] **Create a launch file (`src/nav_fleet/nav_fleet/sim_launch.py`):**

  > This is the key file that wires URDF → Gazebo → ros_gz_bridge → Nav2 together.

  ```python
  # Copyright 2026 Mike. Licensed under MIT.
  """Launch Gazebo simulation with Nav2 for fleet testbed."""
  import os
  from ament_index_python.packages import get_package_share_directory
  from launch import LaunchDescription
  from launch.actions import (
      DeclareLaunchArgument, ExecuteProcess, IncludeLaunchDescription,
      SetEnvironmentVariable,
  )
  from launch.launch_description_sources import PythonLaunchDescriptionSource
  from launch.substitutions import LaunchConfiguration, Command
  from launch_ros.actions import Node


  def generate_launch_description():
      pkg_nav_fleet = get_package_share_directory('nav_fleet')
      pkg_nav2_bringup = get_package_share_directory('nav2_bringup')

      urdf_path = os.path.join(pkg_nav_fleet, 'urdf', 'ugv_pt.urdf.xacro')
      world_path = os.path.join(pkg_nav_fleet, 'worlds', 'bedroom_simple.sdf')
      nav2_params = os.path.join(pkg_nav_fleet, 'config', 'nav2_params.yaml')

      robot_desc = Command(['xacro ', urdf_path])

      return LaunchDescription([
          # Publish robot description
          Node(
              package='robot_state_publisher',
              executable='robot_state_publisher',
              name='robot_state_publisher',
              parameters=[{
                  'robot_description': robot_desc,
                  'use_sim_time': True,
              }],
              remappings=[('/tf', '/robot_001/tf'),
                          ('/tf_static', '/robot_001/tf_static')],
          ),

          # Gazebo Harmonic (headless for CI)
          ExecuteProcess(
              cmd=['gz', 'sim', '-r', world_path, '--headless-rendering'],
              output='screen',
          ),

          # ROS2-Gazebo bridge
          Node(
              package='ros_gz_bridge',
              executable='parameter_bridge',
              arguments=[
                  '/robot_001/cmd_vel@geometry_msgs/msg/Twist@gz.msgs.Twist',
                  '/robot_001/odom@nav_msgs/msg/Odometry@gz.msgs.Odometry',
                  '/robot_001/scan@sensor_msgs/msg/LaserScan@gz.msgs.LaserScan',
                  '/robot_001/camera/image_raw@sensor_msgs/msg/Image@gz.msgs.Image',
                  '/clock@rosgraph_msgs/msg/Clock@gz.msgs.Clock',
              ],
              output='screen',
          ),

          # Nav2
          IncludeLaunchDescription(
              PythonLaunchDescriptionSource(
                  os.path.join(pkg_nav2_bringup, 'launch', 'bringup_launch.py')
              ),
              launch_arguments={
                  'use_sim_time': 'true',
                  'params_file': nav2_params,
                  'namespace': 'robot_001',
              }.items(),
          ),
      ])
  ```

  > **Note:** `nav2_params.yaml` doesn't exist yet. Next step.

- [x] **Create `config/nav2_params.yaml`** — copy from nav2_bringup defaults and customize namespace:
  ```bash
  # Get the default nav2 params as a starting point
  cp /opt/ros/jazzy/share/nav2_bringup/params/nav2_params.yaml config/nav2_params.yaml
  ```

  Then open `config/nav2_params.yaml` and add namespace remapping. Find the top-level `amcl:` block and add:
  ```yaml
  amcl:
    ros__parameters:
      use_sim_time: True
      # ... existing params ...
  ```
  The full nav2_params.yaml customization is a session in itself — at this stage, the default params get the robot moving. Tune in Session 10.

- [x] **Add urdf/ and worlds/ to the installed package** — update `setup.py` data_files:
  ```python
  data_files=[
      ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
      ('share/' + package_name, ['package.xml']),
      ('share/' + package_name + '/config', ['config/nav2_params.yaml', 'config/drift_config.yaml']),
      ('share/' + package_name + '/urdf', ['urdf/ugv_pt.urdf.xacro']),
      ('share/' + package_name + '/worlds', ['worlds/bedroom_simple.sdf']),
  ],
  ```

- [x] **Rebuild and launch:**
  ```bash
  cd ~/autonomous-fleet-testbed
  colcon build --symlink-install
  source install/setup.bash

  # Test Gazebo opens and robot spawns (with display — not headless yet):
  ros2 launch nav_fleet sim_launch.py
  # Gazebo should open. Check that /robot_001/odom, /robot_001/scan topics exist:
  # (new terminal)
  ros2 topic list | grep robot_001
  ros2 topic hz /robot_001/odom    # should show ~50 Hz
  ros2 topic hz /robot_001/scan    # should show ~10 Hz
  ```

- [x] **Commit:**
  ```bash
  git add .
  git commit -m "feat: Stage 3 Part 1 — URDF, bedroom world, Gazebo+Nav2 launch file"
  git push
  ```

### Session Complete When
- `gz sim` opens the bedroom world with the robot spawned
- `ros2 topic hz /robot_001/odom` reports ~50 Hz
- `ros2 topic hz /robot_001/scan` reports ~10 Hz
- No transform errors in `ros2 run tf2_tools view_frames`

---

---

## Session 10 — First Passing Nav Test + Self-Hosted CI Runner (~3-4 hrs)

### Recommended Reading
- [Nav2 NavigateToPose action](https://docs.nav2.org/configuration/packages/configuring-bt-navigator.html) — understand the action server/client pattern
- [GitHub Actions self-hosted runners](https://docs.github.com/en/actions/hosting-your-own-runners/managing-self-hosted-runners/about-self-hosted-runners) — registration, labels, systemd service
- [robot_localization EKF](https://docs.ros.org/en/jazzy/p/robot_localization/) — why IMU + odom fusion matters for Nav2 pose accuracy
- [ros2 action CLI](https://docs.ros.org/en/jazzy/Tutorials/Beginner-CLI-Tools/Understanding-ROS2-Actions/Understanding-ROS2-Actions.html) — useful for testing nav goals manually

### Prerequisites
- Session 09 complete: `gz sim` opens bedroom world, robot spawns, odom ~50 Hz, scan ~10 Hz
- `colcon build --symlink-install` currently clean

### Steps

- [x] **Fix KDL root-link inertia warning (`base_footprint`)** — quick fix, clears the warning
  that appears every launch. ROS2 standard pattern: a massless root link with a fixed joint
  to `base_link`.

  Open `src/nav_fleet/urdf/ugv_pt.urdf.xacro`. Before `<link name="base_link">`, add:
  ```xml
  <link name="base_footprint"/>
  <joint name="base_footprint_joint" type="fixed">
    <parent link="base_footprint"/>
    <child link="base_link"/>
    <origin xyz="0 0 0.125" rpy="0 0 0"/>
  </joint>
  ```

  In the `<plugin filename="gz-sim-diff-drive-system"...>` block, update:
  ```xml
  <child_frame_id>robot_001/base_footprint</child_frame_id>
  ```

  In `config/nav2_params.yaml`, under `amcl` and `controller_server`, update:
  ```yaml
  base_frame_id: robot_001/base_footprint
  ```

- [x] **Add IMU sensor** — Nav2's `robot_localization` EKF fuses IMU + odometry for better pose
  estimates. Without IMU the pose drifts faster on longer runs. The real ugv_pt has an IMU
  at 200 Hz (see `robot_profiles/jetson_ugv_pt.yaml`).

  Add to `src/nav_fleet/urdf/ugv_pt.urdf.xacro` after the camera joint:
  ```xml
  <link name="imu_link">
    <inertial>
      <mass value="0.01"/>
      <inertia ixx="0.00001" ixy="0" ixz="0" iyy="0.00001" iyz="0" izz="0.00001"/>
    </inertial>
  </link>
  <joint name="imu_joint" type="fixed">
    <parent link="base_link"/>
    <child link="imu_link"/>
    <origin xyz="0 0 0.05" rpy="0 0 0"/>
  </joint>

  <gazebo reference="imu_link">
    <sensor name="imu" type="imu">
      <topic>/robot_001/imu/data</topic>
      <update_rate>200</update_rate>
      <always_on>true</always_on>
    </sensor>
  </gazebo>
  ```

  Add to the bridge arguments list in `src/nav_fleet/launch/sim_launch.py`:
  ```python
  '/robot_001/imu/data@sensor_msgs/msg/Imu@gz.msgs.IMU',
  ```

- [x] **Implement `nav_runner.py`** — replace the stub in
  `src/nav_fleet/nav_fleet/nav_runner.py`:

  ```python
  # Copyright 2026 Mike. Licensed under Apache 2.0.
  """Nav2 NavigateToPose action client — sends a goal and waits for result."""
  import rclpy
  from rclpy.node import Node
  from rclpy.action import ActionClient
  from nav2_msgs.action import NavigateToPose
  from geometry_msgs.msg import PoseStamped
  import time


  class NavRunner(Node):
      def __init__(self):
          super().__init__('nav_runner')
          self._client = ActionClient(
              self, NavigateToPose, '/robot_001/navigate_to_pose'
          )

      def send_goal(self, x, y, timeout=90.0):
          """Send goal pose and block until success or timeout. Returns bool."""
          if not self._client.wait_for_server(timeout_sec=15.0):
              self.get_logger().error('Nav2 action server not available')
              return False

          goal = NavigateToPose.Goal()
          goal.pose = PoseStamped()
          goal.pose.header.frame_id = 'map'
          goal.pose.header.stamp = self.get_clock().now().to_msg()
          goal.pose.pose.position.x = x
          goal.pose.pose.position.y = y
          goal.pose.pose.orientation.w = 1.0

          future = self._client.send_goal_async(goal)
          rclpy.spin_until_future_complete(self, future, timeout_sec=10.0)
          goal_handle = future.result()
          if not goal_handle or not goal_handle.accepted:
              self.get_logger().error('Goal rejected')
              return False

          result_future = goal_handle.get_result_async()
          deadline = time.time() + timeout
          while not result_future.done():
              rclpy.spin_once(self, timeout_sec=0.1)
              if time.time() > deadline:
                  self.get_logger().warn('Navigation timed out')
                  return False

          return result_future.result().status == 4  # STATUS_SUCCEEDED


  def main():
      rclpy.init()
      runner = NavRunner()
      success = runner.send_goal(1.0, 1.0)
      print(f'Navigation {"succeeded" if success else "failed"}')
      runner.destroy_node()
      rclpy.shutdown()


  if __name__ == '__main__':
      main()
  ```

- [x] **Implement `metrics_collector.py`** — replace the stub in
  `src/nav_fleet/nav_fleet/metrics_collector.py`:

  ```python
  # Copyright 2026 Mike. Licensed under Apache 2.0.
  """Collect topic Hz and collision metrics from a live ROS2 session."""
  import rclpy
  from rclpy.node import Node
  from nav_msgs.msg import Odometry
  from sensor_msgs.msg import LaserScan
  import time
  import json


  class MetricsCollector(Node):
      def __init__(self):
          super().__init__('metrics_collector')
          self._odom_times = []
          self._scan_times = []
          self._min_range = float('inf')
          self.create_subscription(Odometry, '/robot_001/odom', self._odom_cb, 10)
          self.create_subscription(LaserScan, '/robot_001/scan', self._scan_cb, 10)

      def _odom_cb(self, msg):
          self._odom_times.append(time.time())

      def _scan_cb(self, msg):
          self._scan_times.append(time.time())
          valid = [r for r in msg.ranges if msg.range_min < r < msg.range_max]
          if valid:
              self._min_range = min(self._min_range, min(valid))

      def collect(self, duration=5.0):
          """Spin for duration seconds, return metrics dict."""
          deadline = time.time() + duration
          while time.time() < deadline:
              rclpy.spin_once(self, timeout_sec=0.05)

          def hz(times):
              if len(times) < 2:
                  return 0.0
              elapsed = times[-1] - times[0]
              return (len(times) - 1) / elapsed if elapsed > 0 else 0.0

          return {
              'odom_hz': round(hz(self._odom_times), 1),
              'scan_hz': round(hz(self._scan_times), 1),
              'min_scan_range_m': round(self._min_range, 3),
              'collision_detected': self._min_range < 0.12,
          }


  def main():
      rclpy.init()
      collector = MetricsCollector()
      metrics = collector.collect(duration=5.0)
      print(json.dumps(metrics, indent=2))
      collector.destroy_node()
      rclpy.shutdown()


  if __name__ == '__main__':
      main()
  ```

- [x] **Write `tests/test_navigation.py`** — these tests require a live Gazebo + Nav2 session
  (run locally after `ros2 launch nav_fleet sim_launch.py`):

  ```python
  # Copyright 2026 Mike. Licensed under Apache 2.0.
  """Navigation integration tests — require live Gazebo + Nav2 (not mocked)."""
  import sys
  import os
  import pytest
  import rclpy

  sys.path.insert(0, os.path.join(
      os.path.dirname(__file__), '..', 'src', 'nav_fleet', 'nav_fleet'
  ))
  from nav_runner import NavRunner  # noqa: E402
  from metrics_collector import MetricsCollector  # noqa: E402


  @pytest.fixture(scope='module')
  def ros_ctx():
      rclpy.init()
      yield
      rclpy.shutdown()


  def test_navigation_succeeds(ros_ctx):
      """BR-01: NavigateToPose action succeeds (robot reaches goal)."""
      runner = NavRunner()
      success = runner.send_goal(1.0, 1.0, timeout=90.0)
      runner.destroy_node()
      assert success, 'NavigateToPose did not return STATUS_SUCCEEDED within 90s'


  def test_no_collision(ros_ctx):
      """BR-02: min scan range > robot_radius (0.20m) during 30s observation."""
      collector = MetricsCollector()
      metrics = collector.collect(duration=30.0)
      collector.destroy_node()
      assert not metrics['collision_detected'], (
          f"Collision: min scan range {metrics['min_scan_range_m']}m < 0.12m"
      )


  def test_topic_hz(ros_ctx):
      """BR-10: odom >= 45 Hz, scan >= 9 Hz during normal operation."""
      collector = MetricsCollector()
      metrics = collector.collect(duration=5.0)
      collector.destroy_node()
      assert metrics['odom_hz'] >= 45.0, f"odom Hz {metrics['odom_hz']} < 45"
      assert metrics['scan_hz'] >= 9.0, f"scan Hz {metrics['scan_hz']} < 9"
  ```

- [x] **Register workstation as GitHub Actions self-hosted runner** — one-time setup that
  handles both the Gazebo CI job (this session) and the Isaac Sim CI job (Session 11):

  ```bash
  mkdir -p ~/actions-runner && cd ~/actions-runner

  # Get the exact download URL from:
  # Your repo on GitHub → Settings → Actions → Runners → "New self-hosted runner"
  # (Linux x64). Copy and run the curl + tar commands shown there — the version number
  # changes with each release. The pattern is:
  curl -o actions-runner-linux-x64-<VERSION>.tar.gz -L \
    https://github.com/actions/runner/releases/download/v<VERSION>/actions-runner-linux-x64-<VERSION>.tar.gz
  tar xzf ./actions-runner-linux-x64-<VERSION>.tar.gz

  # Configure — the registration token is shown on the same GitHub page (expires in 1 hr):
  ./config.sh \
    --url https://github.com/sdfinn/autonomous-fleet-testbed \
    --token <TOKEN_FROM_GITHUB_PAGE> \
    --labels self-hosted,x86,gpu,rtx5080 \
    --name mikeubuntu-runner \
    --unattended

  # Install and start as a systemd service (survives reboots):
  sudo ./svc.sh install
  sudo ./svc.sh start
  sudo ./svc.sh status   # should show "active (running)"
  ```

  Verify on GitHub: Settings → Actions → Runners → `mikeubuntu-runner` shows as **Idle**.

  > **Gotcha:** The systemd service runs as your user but in a non-interactive shell, so
  > `.bashrc` is NOT sourced automatically. Source ROS2 explicitly in each CI job step (see
  > below) rather than relying on `.bashrc`.

- [x] **Wire the Gazebo CI job** — in `.github/workflows/ci.yml`, replace the `stage-3-sim`
  stub with:

  ```yaml
  sim-navigation:
    runs-on: [self-hosted, x86, gpu]
    needs: arm64-build
    steps:
      - uses: actions/checkout@v4

      - name: Build workspace
        run: |
          source /opt/ros/jazzy/setup.bash
          colcon build --symlink-install
          echo "source $(pwd)/install/setup.bash" >> $GITHUB_ENV

      - name: Launch Gazebo (background) and wait for Nav2
        run: |
          source /opt/ros/jazzy/setup.bash
          source install/setup.bash
          DISPLAY=:0 ros2 launch nav_fleet sim_launch.py &
          sleep 20
        env:
          DISPLAY: ':0'

      - name: Run navigation tests
        run: |
          source /opt/ros/jazzy/setup.bash
          source install/setup.bash
          python -m pytest tests/test_navigation.py tests/test_ros2_contracts.py -v
        env:
          DISPLAY: ':0'

      - name: Record timing
        run: date >> reports/session10_timings.txt && cat reports/session10_timings.txt
  ```

  > **Why `DISPLAY=:0`?** Gazebo's OGRE2 renderer checks for a display server even in
  > headless rendering mode. Your workstation is running Xorg (visible in nvidia-smi output),
  > so `:0` is already there — just needs to be declared for the non-interactive shell.

- [x] **Remove `continue-on-error: true` from Stage 0** in `ci.yml` — now that
  `test_navigation.py` covers the missing requirements, Stage 0 should fail the pipeline
  if traceability breaks.

- [x] **Also rename CI job labels to match** — the old `stage-0-requirements`,
  `stage-1-quality`, `stage-2-arm64` job names can stay as-is; just ensure the `needs:`
  chain is correct: `sim-navigation` needs `arm64-build`.

- [x] **Build, launch locally, verify all three tests pass**:

  ```bash
  colcon build --symlink-install
  source install/setup.bash

  # Terminal 1 — launch simulation:
  ros2 launch nav_fleet sim_launch.py

  # Terminal 2 — run tests against live Gazebo (wait ~15s for Nav2 to initialise first):
  python -m pytest tests/test_navigation.py tests/test_ros2_contracts.py -v
  # All tests should pass

  # Spot-check Hz:
  ros2 topic hz /robot_001/odom       # ~50 Hz
  ros2 topic hz /robot_001/imu/data   # ~200 Hz
  ros2 topic hz /robot_001/scan       # ~10 Hz
  ```

- [x] **Record bare-metal timing** and add to BLUEPRINT.md under Timings:
  ```bash
  time python -m pytest tests/test_navigation.py -v
  # Note: includes Nav2 startup (~15s) + navigation execution (~30-60s depending on goal)
  ```

- [x] **Commit and push** — CI will trigger on the self-hosted runner:
  ```bash
  git add .
  git commit -m "feat(session-10): first passing nav test, IMU, base_footprint, self-hosted CI runner"
  git push
  gh run watch   # watch the sim-navigation job run on mikeubuntu-runner
  ```

### Session Complete When
- `python -m pytest tests/test_navigation.py tests/test_ros2_contracts.py -v` — all tests green locally
- GitHub Actions `sim-navigation` job green on the self-hosted runner
- `continue-on-error` removed from Stage 0 and pipeline still green
- Bare-metal nav test timing recorded in BLUEPRINT.md

---

## Session 11 — Isaac Sim: Install + First Nav Test (~3-4 hrs)

### Recommended Reading
- [Isaac Sim 5.x installation (pip)](https://docs.isaacsim.omniverse.nvidia.com/latest/installation/install_python.html) — pip install is the fastest path; no Omniverse Launcher needed
- [Isaac Sim ROS2 bridge](https://docs.isaacsim.omniverse.nvidia.com/latest/ros2_tutorials/tutorial_ros2_overview.html) — how to enable the bridge and what topics it publishes
- [USD basics for robotics](https://docs.isaacsim.omniverse.nvidia.com/latest/scene_setup/stage_setup.html) — Isaac uses USD (not SDF); understanding the stage/prim model helps
- [Isaac Sim Python scripting](https://docs.isaacsim.omniverse.nvidia.com/latest/python_scripting/index.html) — how to drive Isaac from Python (needed for CI job)

### Prerequisites
- Session 10 complete and CI green
- NVIDIA driver 595.71.05, CUDA 13.2 ✓ already installed (verified 2026-06-29)
- Self-hosted runner already registered (`mikeubuntu-runner`)
- ~25 GB free disk space for Isaac Sim

### Steps

- [x] **Install Isaac Sim 6.0.1.0 via pip** — fastest installation path; no Omniverse GUI needed:

  ```bash
  # Use a separate venv to avoid conflicts with the fleet-env:
  python3 -m venv ~/isaac-env
  source ~/isaac-env/bin/activate

  # Install Isaac Sim (large download — ~20 GB, takes 20-40 min):
  # Note: 5.x was never published to pypi.nvidia.com. 6.0.1.0 is the correct version.
  # Requires Python 3.12 (cp312 wheels) — Ubuntu 24.04 default. Jazzy auto-loaded.
  pip install isaacsim==6.0.1.0 \
    --extra-index-url https://pypi.nvidia.com

  # Verify:
  python -c "import isaacsim; print('Isaac Sim installed')"
  ```

  > **Gotcha — first launch takes 30+ minutes.** Isaac Sim compiles shaders for your GPU
  > on the first run. This is a one-time cost but must complete before any further steps.
  > Launch headless and wait for the "Isaac Sim is running" log line:
  > ```bash
  > python -m isaacsim.kit --headless
  > # Wait for: "[Isaac Sim] Simulation app is running"
  > # Ctrl+C to exit once confirmed
  > ```

- [x] **Enable the ROS2 bridge extension** — Isaac Sim 6.0 API changed from 4.x.
  Extension name: `isaacsim.ros2.bridge` (not `omni.isaac.ros2_bridge`).
  Import path: `isaacsim.core.utils.extensions` (not `omni.isaac.core`).
  EULA must be accepted via env var for headless use.
  Script is at `scripts/isaac_ros2_bridge.py`:

  ```python
  import os
  os.environ["OMNI_KIT_ACCEPT_EULA"] = "YES"

  from isaacsim import SimulationApp
  simulation_app = SimulationApp({"headless": True, "renderer": "RayTracedLighting"})

  from isaacsim.core.utils.extensions import enable_extension
  enable_extension("isaacsim.ros2.bridge")

  from isaacsim.core import World
  world = World()
  world.reset()

  for i in range(600):   # ~60s at 10 Hz
      world.step(render=False)

  simulation_app.close()
  ```

  Run it and verify ROS2 topics appear:
  ```bash
  source ~/isaac-env/bin/activate
  source /opt/ros/jazzy/setup.bash
  OMNI_KIT_ACCEPT_EULA=YES python scripts/isaac_ros2_bridge.py &
  sleep 30
  ros2 topic list   # should show /clock and other Isaac topics
  ```

- [x] **Load the bedroom world in Isaac** ← deferred to Session 12 — Isaac uses USD format. The simplest first step
  is a programmatic scene rather than converting the SDF. Create
  `src/nav_fleet/worlds/bedroom_isaac.py`:

  ```python
  """Build the bedroom world in Isaac Sim programmatically (matches bedroom_simple.sdf)."""
  import omni.isaac.core.utils.prims as prim_utils
  from omni.isaac.core.objects import FixedCuboid
  import numpy as np

  def create_bedroom(world):
      """Add walls and obstacles matching bedroom_simple.sdf geometry."""
      # Floor
      FixedCuboid('/World/floor', scale=np.array([7.0, 7.0, 0.02]),
                  position=np.array([0, 0, -0.01]), color=np.array([0.8, 0.8, 0.8]))
      # North wall
      FixedCuboid('/World/wall_north', scale=np.array([7.0, 0.2, 1.0]),
                  position=np.array([0, 3.5, 0.5]))
      # South wall
      FixedCuboid('/World/wall_south', scale=np.array([7.0, 0.2, 1.0]),
                  position=np.array([0, -3.5, 0.5]))
      # East wall
      FixedCuboid('/World/wall_east', scale=np.array([0.2, 7.0, 1.0]),
                  position=np.array([3.5, 0, 0.5]))
      # West wall
      FixedCuboid('/World/wall_west', scale=np.array([0.2, 7.0, 1.0]),
                  position=np.array([-3.5, 0, 0.5]))
      # Obstacle 1 (furniture)
      FixedCuboid('/World/obstacle_1', scale=np.array([0.4, 0.4, 0.5]),
                  position=np.array([1.0, 1.0, 0.25]), color=np.array([0.4, 0.2, 0.1]))
      # Obstacle 2
      FixedCuboid('/World/obstacle_2', scale=np.array([0.3, 0.6, 0.5]),
                  position=np.array([-1.0, 0.5, 0.25]), color=np.array([0.3, 0.4, 0.6]))
  ```

- [x] **Spawn ugv_pt and run a simple Nav2 test in Isaac** — wire nav_runner.py against
  the Isaac ROS2 bridge (same topic namespace `/robot_001/`):

  > **Note:** Full Nav2 in Isaac is more complex than Gazebo because Nav2 needs the transform
  > tree and map to be published by Isaac. For Session 11, the goal is: robot spawned,
  > `/robot_001/odom` and `/robot_001/scan` topics visible, and nav_runner.py can send
  > a goal. A full nav test comparable to Session 10 can be a Session 11 stretch goal.

  ```bash
  # After Isaac is running with ROS2 bridge:
  ros2 topic list | grep robot_001
  ros2 topic hz /robot_001/odom   # target: ~50 Hz
  ros2 topic hz /robot_001/scan   # target: ~10 Hz
  ```

- [x] **Wire Isaac Sim CI job** — uses the same self-hosted runner as Session 10's
  Gazebo job. Add to `.github/workflows/ci.yml` after `sim-navigation`:

  ```yaml
  isaac-validation:
    runs-on: [self-hosted, x86, gpu]
    needs: sim-navigation
    steps:
      - uses: actions/checkout@v4
      - name: Run Isaac Sim nav test
        run: |
          source /opt/ros/jazzy/setup.bash
          source ~/isaac-env/bin/activate
          python scripts/isaac_ros2_bridge.py &
          sleep 30
          python -m pytest tests/test_navigation.py -v -k "hz"
        env:
          DISPLAY: ':0'
      - name: Record Isaac timing
        run: date >> reports/session11_timings.txt
  ```

- [x] **Record Isaac Sim timing** — note first-launch shader compile time (one-time) vs
  subsequent launch time. Added to BLUEPRINT.md under Timings:
  ```
  Isaac Sim first launch (shader compile): ~10 s (RTX 5080 — much faster than expected)
  Isaac Sim subsequent launch to ready: ~7 s
  Isaac robot script (600 steps, odom+scan): ~60 s wall time
  ```

- [x] **Commit**:
  ```bash
  git add .
  git commit -m "feat(session-11): Isaac Sim bare metal, ROS2 bridge, isaac-validation CI job"
  git push
  ```

### Session Complete When
- `python scripts/isaac_ros2_bridge.py` launches without error, ROS2 topics visible ✅
- `/robot_001/odom` (~96 Hz) and `/robot_001/scan` (~22 Hz) publishing in Isaac ✅
- `stage-4-isaac` CI job wired in ci.yml ✅
- Isaac timing numbers recorded in BLUEPRINT.md ✅

### GUI Nav Test Procedure (pre-Session-12, 3 terminals)

> **Critical:** Start Nav2 within ~5s of Isaac ready. DDS TRANSIENT_LOCAL caches TF history —
> a late Nav2 start gets thousands of old messages replayed → goal rejected. Kill BOTH Isaac
> AND Nav2 between runs (never restart Nav2 alone).

**Terminal 1 — Isaac (start first):**
```bash
cd ~/autonomous-fleet-testbed
colcon build --symlink-install && source install/setup.bash
source ~/isaac-env/bin/activate   # isaacsim lives here, NOT in fleet-env (kept separate
                                   # to avoid its heavy deps — torch, usd-exchange, etc. —
                                   # polluting the project venv, see Session 11 install step)
DISPLAY=:0 OMNI_KIT_ACCEPT_EULA=YES PYTHONUNBUFFERED=1 python -u scripts/isaac_bedroom_gui.py
```
Wait for: `[Isaac] *** Simulation running ***`

**Terminal 2 — Nav2 (start IMMEDIATELY after Terminal 1 ready):**
```bash
cd ~/autonomous-fleet-testbed
ros2 launch src/nav_fleet/launch/nav2_isaac_launch.py
```
Wait for: `Managed nodes are active` and `Setting pose … -1.276 1.200 1.571`

**Terminal 3 — Test:**
```bash
cd ~/autonomous-fleet-testbed
python -m pytest tests/test_navigation.py::test_navigation_succeeds -v --timeout=120
```

**Terminal 4 — Monitor AMCL (optional, run after Nav2 active):**
```bash
ros2 topic echo /robot_001/amcl_pose
```

**Between runs:** `pkill -9 -f "isaac_bedroom|component_container_isolated|robot_state_publisher"` then wait 5s.

---

## Session 12 — Reports + Dashboard: True End-to-End (~3 hrs)

### Recommended Reading
- [Streamlit documentation](https://docs.streamlit.io/) — multi-page apps, `st.sidebar`, `st.tabs`
- [ReportLab PDF generation](https://docs.reportlab.com/reportlab/userguide/ch1_intro/) — generating PDFs programmatically
- [Pandera data validation](https://pandera.readthedocs.io/en/stable/) — schema validation for the telemetry JSON

> **Session reviewed against actual code 2026-07-03 — original text was stale.** It described
> a JSON-file-per-run architecture (`reports/history/<run_id>.json`), but all five migrated
> tools (`telemetry_logger`, `generate_test_report`, `baseline_monitor`, `validate_telemetry`,
> `dashboard/app.py`) are already built on **SQLite** — `reports/fleet_runs.db` via the
> `FLEET_DB` env var — and *nothing* in the repo reads `reports/history/` (it's empty).
> Decision: SQLite stays the single source of truth (Session 13's `ai_test_generator` also
> depends on it); the JSON-per-run idea is dropped. The steps below are rewritten to match.

### Prerequisites
- Sessions 10 and 11 complete — nav test passes locally against Gazebo and Isaac.
  (No run data exists yet: `reports/fleet_runs.db` is created by this session's wiring —
  `test_navigation.py` currently never calls `telemetry_logger`.)
- `pip install streamlit reportlab pandera` in fleet-env (already in requirements.txt)

### Steps

- [x] **Add a `sim_engine` column to `tools/telemetry_logger.py`** — also added `robot_id`
  (distinct from `robot_type`, which is the robot *model*/profile) — the specific unit
  instance, e.g. `robot_001`. Not needed for this single-robot project, but keeps the schema
  open for the next project's multi-robot fleet without a later migration. Both read from
  `ROBOT_ID`/`SIM_ENGINE` env vars in the test fixture, defaulting to `robot_001`/`gazebo`.

- [x] **Wire the telemetry hook.** `log_run()`'s signature only took
  `scenario/steps/final_x/final_y/result/step_log` — none of the "rate" metrics
  (`nav_success_rate`, `mean_position_error`, etc.) despite those columns existing in the
  schema; `test_baseline.py` worked around this with a manual post-insert `UPDATE`. Extended
  `log_run()` with optional kwargs for all of them (backward compatible), and simplified
  `test_baseline.py` to use the real API instead of the workaround.
  `NavRunner`/`MetricsCollector` had no way to produce most of this data either — added an
  `/robot_001/amcl_pose` subscription + wall-clock duration + step counter to `NavRunner`
  (for position error / time-to-goal / steps), and a camera subscription to
  `MetricsCollector` (for `camera_hz`, alongside existing odom/scan Hz). Wired one
  `log_run()` call per pytest session in `test_navigation.py` (session-scoped fixture
  teardown), combining all of it into a single row.
  **Also found:** `log_run()` never called `init_db()` — it assumed the table already
  existed, so pointing it at a fresh DB path threw `no such table: runs`. Fixed by having
  `log_run()` call `init_db()` itself.

- [x] **Verify `tools/generate_test_report.py` against real data** — ran clean, but the
  "Goal Zone" scatter rectangle was stale `isaac_project` living-room coordinates
  (x: 0.76–3.05, y: 0.56–1.93) that don't match this project's bedroom goal at all — fixed
  to the actual goal (0.0, 3.7) ± Nav2's `xy_goal_tolerance` (0.15 m). Also: the real output
  filename is `reports/test_report.pdf` (the `REPORT_PATH` default), not
  `reports/latest_report.pdf` as this doc and the CI snippet below assumed — set
  `REPORT_PATH` explicitly in CI rather than change the tool's default.
  ```bash
  python tools/generate_test_report.py
  evince reports/latest_report.pdf
  ```

- [x] **Verify `dashboard/app.py` against real data** — five tabs confirmed via Playwright
  against the real DB row. Added a `sim_engine` sidebar filter + Run Log column (matching
  the existing `robot_type`/`runner_type` filters). Found two real bugs, both fixed:
  the same stale-coordinates issue in the Telemetry tab's goal-zone rectangle (was
  x0=1.0,x1=4.0,y0=-11.0,y1=-5.0 — nowhere near the bedroom), and a hard traceback in
  Sensor Health from `num_frames`/`detections_per_frame_avg`/`class_distribution` —
  leftover `isaac_project` YOLO object-detection columns that were never added to this
  project's schema (unlike `lidar_min_range` etc., which are real). Wrapped both that query
  and the `ai_scenarios` query (table doesn't exist until Session 13) in try/except,
  matching the existing `load_ai_scenarios()` pattern, so they degrade to "no data yet"
  instead of crashing the tab.
  ```bash
  streamlit run dashboard/app.py
  # localhost:8501 — every tab renders real data without tracebacks
  ```

- [x] **Run `tools/validate_telemetry.py`** — caught the new `sim_engine`/`robot_id`
  columns as schema drift (correctly — it hadn't been told about them yet). Added both to
  `RunsModel` and `KNOWN_RUNS_COLS`. Clean exit 0 after.
  ```bash
  python tools/validate_telemetry.py && echo VALID
  ```

- [x] **Wire the `stage-5-reports` CI job** on the self-hosted runner, `needs: stage-4-isaac`,
  `FLEET_DB` + `REPORT_PATH` set at job level; added a `mkdir -p /home/mike/fleet-ci-data`
  step since that directory doesn't exist yet on `mikeubuntu`. Also added `python
  tools/baseline_monitor.py` as a step (checks the just-generated run against history — the
  session's actual purpose, not just report/schema checks). Set `FLEET_DB` +
  `SIM_ENGINE: gazebo`/`isaac` at the job-env level on `stage-3-gazebo`/`stage-4-isaac` so
  their nav-test runs log to the same persistent DB.

- [x] **Test `baseline_monitor.py`** — seeded 9 runs with realistic small variance around a
  real captured row (in a scratch copy of the DB, not the real `reports/fleet_runs.db`),
  injected one bad run (`mean_position_error` 10x normal). Correctly flagged: `sigma=122.0`
  on `mean_position_error`, all other metrics OK.
  ```bash
  python tools/baseline_monitor.py
  # Should print drift summary — any metric outside drift_config.yaml thresholds flagged
  ```

- [ ] **Commit**:
  ```bash
  git add .
  git commit -m "feat(session-12): reports, dashboard, E2E pipeline complete"
  git push
  ```

### Session Complete When
- [x] `test_navigation.py` logs a row to `reports/fleet_runs.db` on every run, with `sim_engine` set
- [x] `streamlit run dashboard/app.py` shows real run data in all five tabs
- [x] `reports/test_report.pdf` generates from real DB rows (see filename note above)
- [ ] `stage-5-reports` CI job green, PDF artifact downloadable from the GitHub Actions run
      — wired but not yet observed on a real CI push
- [x] `baseline_monitor.py` detects a simulated drift breach when you inject a bad run

---

## Session 13 — Agentic Test Loop in Sim (~4 hrs)

> **This is the differentiator.** The pipeline now closes the loop: Claude watches test
> results, diagnoses failures, generates new scenarios, and proposes improvements.
> Human approval is required before any change is applied.

### Recommended Reading
- [Anthropic tool use / function calling](https://docs.anthropic.com/en/docs/tool-use) — how to give Claude structured output capabilities
- [Claude API Python SDK](https://github.com/anthropics/anthropic-sdk-python) — `anthropic` package, Messages API
- [Nav2 BT Navigator](https://docs.nav2.org/configuration/packages/bt-navigator.html) — understand what a Behavior Tree failure means in the telemetry
- [Gazebo SDF reference](https://gazebosim.org/api/sim/8/sdf_worlds.html) — needed for generative world creation

> **Session reviewed against actual code 2026-07-06 — original text was stale in the same
> way Session 12's was.** `load_latest_run()` assumed the dropped `reports/history/*.json`
> per-run-file architecture; Session 12 confirmed (again) that SQLite (`reports/fleet_runs.db`,
> `FLEET_DB` env var) is the single source of truth. The prompt's hardcoded drift thresholds
> (`nav_success_rate >= 0.95`, etc.) also duplicated logic that `tools/baseline_monitor.py`
> now does for real, with a proper rolling baseline + sigma comparison instead of fixed
> absolute values — verified working in Session 12 (flagged an injected 10x
> `mean_position_error` at sigma=122). `SEMANTIC_MAP` was a generic 4-direction placeholder
> (`north_corridor`, `east_zone`, ...) drafted before `bedroom_simple.sdf` existed; the real
> world is one hallway leading into a single bedroom, not a symmetric grid — rewritten below
> against the actual model poses in that file. The model string (`claude-sonnet-4-6`) is also
> stale — updated to `claude-sonnet-5`. `tools/ai_test_generator.py` has the same stale model
> string; out of scope here since Session 13 doesn't touch that file, but worth fixing next
> time it's touched. Steps below are rewritten to match.

### Prerequisites
- Session 12 complete — `reports/fleet_runs.db` has at least one real run row (Session 12
  wired `test_navigation.py` to log one every run)
- `pip install anthropic` in fleet-env (already in requirements.txt)
- `ANTHROPIC_API_KEY` set in environment (add to `.env` or export in shell):
  ```bash
  echo 'export ANTHROPIC_API_KEY=sk-ant-...' >> ~/.bashrc
  source ~/.bashrc
  ```
- Note: `baseline_monitor.check_run()` needs 3+ prior PASS runs before it can flag
  anything — with only a run or two logged so far, the "inject a failure" step below
  seeds a scratch copy of the DB with more history first (same pattern used to verify
  `baseline_monitor.py` itself in Session 12).

### Steps

- [x] **Create `tools/agentic_loop.py`** — the main orchestrator. Reads the latest run
  row from `FLEET_DB`, calls Claude with telemetry + drift context, gets a structured
  diagnosis + proposed action, presents it to the human for approval, then applies the
  approved action:

  ```python
  # Copyright 2026 Mike. Licensed under Apache 2.0.
  """Agentic test loop: diagnose failures, propose fixes, await human approval."""
  import anthropic
  import json
  import os
  import sqlite3
  from pathlib import Path

  from tools.baseline_monitor import check_run

  client = anthropic.Anthropic()

  FLEET_DB = os.environ.get("FLEET_DB", "reports/fleet_runs.db")

  # Named locations matching the real bedroom_simple.sdf model poses — one hallway
  # leading into a single bedroom, not a symmetric grid. Claude uses these names in
  # mission plans instead of raw (x, y) coordinates.
  SEMANTIC_MAP = {
      'home_base':     (-1.276, 1.2),      # robot spawn — outer hallway arch
      'hallway_west':  (-2.6435, 1.6740),
      'hallway_east':  (1.2805, 1.6930),
      'bedroom_goal':  (0.0, 3.7),         # BR-01 goal — bedroom floor centre
      'dresser':       (0.0074, 2.7583),   # just inside the bedroom doorway
      'desk':          (-0.9590, 5.3240),
      'pc_tower':      (-1.0360, 4.2050),  # obstacle near the desk
      'bed':           (0.8130, 5.4360),
  }

  TOOLS = [
      {
          'name': 'propose_nav_param_change',
          'description': 'Propose a change to nav2_params.yaml to address a navigation failure.',
          'input_schema': {
              'type': 'object',
              'properties': {
                  'param_path': {'type': 'string', 'description': 'Dot-separated param key'},
                  'current_value': {'type': 'string'},
                  'proposed_value': {'type': 'string'},
                  'rationale': {'type': 'string'},
              },
              'required': ['param_path', 'proposed_value', 'rationale'],
          },
      },
      {
          'name': 'generate_world_variant',
          'description': 'Generate a new SDF world file with different obstacle positions for broader test coverage.',
          'input_schema': {
              'type': 'object',
              'properties': {
                  'variant_name': {'type': 'string'},
                  'obstacle_layout': {
                      'type': 'array',
                      'items': {
                          'type': 'object',
                          'properties': {
                              'name': {'type': 'string'},
                              'x': {'type': 'number'},
                              'y': {'type': 'number'},
                              'size_x': {'type': 'number'},
                              'size_y': {'type': 'number'},
                          },
                      },
                  },
                  'rationale': {'type': 'string'},
              },
              'required': ['variant_name', 'obstacle_layout', 'rationale'],
          },
      },
      {
          'name': 'propose_mission_plan',
          'description': (
              'Generate a sequence of Nav2 goal poses from a natural language mission description. '
              'Prefer named locations from SEMANTIC_MAP over raw coordinates.'
          ),
          'input_schema': {
              'type': 'object',
              'properties': {
                  'mission_description': {'type': 'string'},
                  'goals': {
                      'type': 'array',
                      'items': {
                          'type': 'object',
                          'properties': {
                              'location': {
                                  'type': 'string',
                                  'description': 'Named location from SEMANTIC_MAP, or "custom"',
                              },
                              'label': {'type': 'string', 'description': 'Human-readable step label'},
                              'x': {'type': 'number', 'description': 'Only if location is "custom"'},
                              'y': {'type': 'number', 'description': 'Only if location is "custom"'},
                          },
                          'required': ['location', 'label'],
                      },
                  },
                  'rationale': {'type': 'string'},
              },
              'required': ['mission_description', 'goals', 'rationale'],
          },
      },
  ]


  def load_latest_run(db_path=FLEET_DB):
      """Load the most recent row from the `runs` table."""
      conn = sqlite3.connect(db_path)
      conn.row_factory = sqlite3.Row
      row = conn.execute('SELECT * FROM runs ORDER BY id DESC LIMIT 1').fetchone()
      conn.close()
      if row is None:
          raise FileNotFoundError(f'No runs found in {db_path}')
      return dict(row)


  def resolve_goals(goals):
      """Resolve named locations to (x, y) coordinates."""
      resolved = []
      for g in goals:
          loc = g.get('location', 'custom')
          if loc in SEMANTIC_MAP:
              x, y = SEMANTIC_MAP[loc]
          else:
              x, y = g.get('x', 0.0), g.get('y', 0.0)
          resolved.append({'x': x, 'y': y, 'label': g.get('label', loc)})
      return resolved


  def diagnose(run_data, db_path=FLEET_DB):
      """Call Claude with telemetry + drift context; get structured diagnosis and proposed action."""
      locations_str = '\n'.join(f'  {k}: {v}' for k, v in SEMANTIC_MAP.items())

      # Reuse the real drift detector (Session 12) instead of re-deriving pass/fail from
      # hardcoded thresholds — it compares against a rolling baseline of past PASS runs.
      drift_reports = check_run(run_data['id'], db_path=db_path)
      if drift_reports:
          drift_str = '\n'.join(
              f'  {r.metric}: current={r.current:.2f} baseline_mean={r.mean:.2f} '
              f'sigma={r.sigma:.1f} {"FLAGGED" if r.flagged else "ok"}'
              for r in drift_reports
          )
      else:
          drift_str = '  Not enough baseline history yet (need 3+ prior PASS runs).'

      prompt = f"""You are an autonomous robotics test engineer.

  The latest nav test run (id={run_data['id']}, scenario={run_data['scenario']},
  result={run_data['result']}, sim_engine={run_data.get('sim_engine')}):
  {json.dumps(run_data, indent=2)}

  Drift report against the rolling baseline (config/drift_config.yaml sigma thresholds):
{drift_str}

  Available named locations in this environment (use these in mission plans):
{locations_str}

  Analyse the results. If any metric is FLAGGED, diagnose the likely cause and use ONE
  tool to propose a concrete action. If nothing is flagged, use propose_mission_plan
  with semantic location names to create a more challenging multi-waypoint mission
  (e.g. "visit the bedroom goal, then the desk, then return to home_base") or use
  generate_world_variant to propose a harder obstacle layout."""

      response = client.messages.create(
          model='claude-sonnet-5',
          max_tokens=2048,
          tools=TOOLS,
          messages=[{'role': 'user', 'content': prompt}],
      )
      return response


  def apply_world_variant(layout, name):
      """Write a new SDF world file from Claude's obstacle layout."""
      obstacles_sdf = ''
      for obs in layout:
          obstacles_sdf += f"""
    <model name="{obs['name']}">
      <static>true</static>
      <pose>{obs['x']} {obs['y']} 0.25 0 0 0</pose>
      <link name="link">
        <collision name="collision">
          <geometry><box><size>{obs['size_x']} {obs['size_y']} 0.5</size></box></geometry>
        </collision>
        <visual name="visual">
          <geometry><box><size>{obs['size_x']} {obs['size_y']} 0.5</size></box></geometry>
          <material><diffuse>0.5 0.3 0.1 1</diffuse></material>
        </visual>
      </link>
    </model>"""

      world_path = Path(f'src/nav_fleet/worlds/{name}.sdf')
      # Read the base world template and inject obstacles
      base = Path('src/nav_fleet/worlds/bedroom_simple.sdf').read_text()
      # Insert before </world>
      new_world = base.replace('  </world>', obstacles_sdf + '\n  </world>')
      world_path.write_text(new_world)
      print(f'[agentic] Created world variant: {world_path}')
      return world_path


  def human_approval(action_type, details):
      """Print the proposed action and ask for human approval."""
      print(f'\n{"="*60}')
      print(f'PROPOSED ACTION: {action_type}')
      print(json.dumps(details, indent=2))
      print('="*60}')
      answer = input('\nApprove? [y/N]: ').strip().lower()
      return answer == 'y'


  def run_loop():
      run_data = load_latest_run()
      print(f"[agentic] Loaded run {run_data['id']}: "
            f"{run_data['scenario']} ({run_data['result']})")

      response = diagnose(run_data)

      for block in response.content:
          if block.type == 'tool_use':
              tool = block.name
              inputs = block.input
              print(f'\n[agentic] Claude proposes: {tool}')

              if not human_approval(tool, inputs):
                  print('[agentic] Proposal rejected by human. Exiting.')
                  return

              if tool == 'generate_world_variant':
                  apply_world_variant(inputs['obstacle_layout'], inputs['variant_name'])
                  print(f'[agentic] World variant created. Re-run: '
                        f'ros2 launch nav_fleet sim_launch.py world:={inputs["variant_name"]}')

              elif tool == 'propose_nav_param_change':
                  print(f'[agentic] Apply this change to config/nav2_params.yaml:')
                  print(f'  {inputs["param_path"]}: {inputs["proposed_value"]}')
                  print(f'  Rationale: {inputs["rationale"]}')

              elif tool == 'propose_mission_plan':
                  resolved = resolve_goals(inputs['goals'])
                  plan = {**inputs, 'goals_resolved': resolved}
                  plan_path = Path('reports/mission_plan.json')
                  plan_path.write_text(json.dumps(plan, indent=2))
                  print(f'[agentic] Mission plan saved to {plan_path}')
                  print(f'  Mission: {inputs["mission_description"]}')
                  for step in resolved:
                      print(f'    → {step["label"]}: ({step["x"]}, {step["y"]})')

          elif block.type == 'text':
              print(f'\n[Claude analysis]\n{block.text}')


  if __name__ == '__main__':
      run_loop()
  ```

  **Two bugs found and fixed while implementing (2026-07-06):** `human_approval()`'s
  separator line was a typo — `print('="*60}')`, a literal broken string, not an f-string —
  fixed to build the separator correctly. And confirmed by actually running it:
  `python tools/agentic_loop.py` fails outright with `ModuleNotFoundError: No module named
  'tools'` — running a script directly sets `sys.path[0]` to the script's own directory
  (`tools/`), not the repo root, so `from tools.baseline_monitor import check_run` can't
  resolve. Every invocation below uses `python -m tools.agentic_loop` instead, which does
  add the repo root to `sys.path`.

- [x] **Test the loop end-to-end on bare metal**:
  ```bash
  # Confirm at least one run exists (no `sqlite3` CLI on this machine — use python):
  python -c "
  import sqlite3
  print(sqlite3.connect('reports/fleet_runs.db').execute('SELECT COUNT(*) FROM runs').fetchone())
  "

  # Run the agentic loop — must use -m, not `python tools/agentic_loop.py`: the plain
  # script form sets sys.path[0] to tools/ itself, not the repo root, so
  # `from tools.baseline_monitor import check_run` fails with ModuleNotFoundError.
  # Confirmed by actually running it (2026-07-06) — this isn't a hypothetical.
  python -m tools.agentic_loop
  # Claude analyses the run + drift report, proposes an action
  # You see the proposal and approve/reject
  # If approved: world variant created OR nav param change shown OR mission plan saved
  ```
  **Actually ran (2026-07-06):** with the real DB's single PASS run and no baseline history
  yet, Claude correctly reported "not enough baseline history" and chose
  `propose_mission_plan` — a valid multi-waypoint mission using real `SEMANTIC_MAP` names
  (`hallway_east`, `dresser`, `desk`, `pc_tower`, `bed`, `home_base`), reasoned about
  cumulative drift and furniture-adjacent maneuvering in its rationale. Approved it;
  `reports/mission_plan.json` was written correctly with `goals_resolved` containing the
  real coordinates for every named location.

- [x] **Inject a failure and verify diagnosis** — work on a scratch copy of the DB, not
  the real `reports/fleet_runs.db` (same pattern used to verify `baseline_monitor.py` in
  Session 12): seed a few extra PASS rows so `check_run()` has a baseline, then insert one
  bad row and confirm Claude sees it FLAGGED and proposes a nav param change.
  ```bash
  cp reports/fleet_runs.db /tmp/agentic_test.db
  python -c "
  import random
  from tools.telemetry_logger import log_run
  db = '/tmp/agentic_test.db'
  random.seed(42)
  # Needs real variance across seed rows — 3+ identical values give stddev=0.0, which
  # check_run() treats as 'no meaningful baseline' and skips (found the hard way
  # verifying baseline_monitor.py itself in Session 12).
  for _ in range(9):
      log_run(scenario='bedroom_nav', steps=73, final_x=0.0, final_y=3.7, result='PASS',
              step_log=[], db_path=db, nav_success_rate=1.0,
              mean_position_error=0.15 + random.uniform(-0.03, 0.03),
              collision_rate=0.0, odom_hz_mean=50.0, lidar_hz_mean=10.5, camera_hz_mean=10.5)
  log_run(scenario='bedroom_nav', steps=73, final_x=1.5, final_y=2.8, result='FAIL',
          step_log=[], db_path=db, nav_success_rate=0.0, mean_position_error=1.5,
          collision_rate=0.0, odom_hz_mean=50.0, lidar_hz_mean=10.5, camera_hz_mean=10.5)
  "
  FLEET_DB=/tmp/agentic_test.db python -m tools.agentic_loop
  # Claude should see mean_position_error FLAGGED and propose: propose_nav_param_change
  # (e.g. increase inflation_radius or reduce speed)
  ```
  **Actually ran (2026-07-06):** flagged at sigma=76.6, correctly reasoned it was a
  planning/costmap issue rather than collision or sensor (zero collisions, healthy Hz
  metrics) since the robot moved but stopped short of goal, and proposed reducing
  `local_costmap.inflation_layer.inflation_radius` from 0.55 to 0.30 — exactly the
  `propose_nav_param_change` response expected. **Caught a real limitation checking
  this:** the claimed `current_value` (0.55) is wrong — the actual value in
  `nav2_params.yaml` is 0.25 (confirmed directly). `diagnose()`'s prompt never includes
  the real params file, so Claude infers a plausible `current_value` rather than reading
  ground truth. Trust `proposed_value` + rationale, not `current_value`, until the real
  file gets fed into the prompt — not done this session, worth a follow-up.

- [x] **Test generative world variant** — when all metrics are healthy, Claude should call
  `generate_world_variant`. Approve it, then verify the new SDF file is valid:
  ```bash
  python -m tools.agentic_loop
  # After approval, a new .sdf should appear in src/nav_fleet/worlds/
  gz sdf -k src/nav_fleet/worlds/<variant_name>.sdf  # validate the SDF
  ```
  **Actually verified (2026-07-06):** Claude consistently chose `propose_mission_plan` over
  `generate_world_variant` across several runs against the single-PASS-run DB (reasonable —
  more mission coverage is more useful than a harder world when there's this little data
  yet). Re-rolling the LLM call repeatedly isn't a real test of a deterministic code path,
  so `apply_world_variant()` was verified directly with a synthetic obstacle layout instead —
  `gz sdf -k` reported the generated SDF "Valid."

- [x] **Commit**:
  ```bash
  git add .
  git commit -m "feat(session-13): agentic loop — diagnosis, world generation, mission planning"
  git push
  ```

### Session Complete When
- [x] `python -m tools.agentic_loop` runs end-to-end: loads the latest run row from `FLEET_DB`, Claude diagnoses against the real drift report, proposes action, human approves, action applied
- [x] Injected failure (scratch DB) triggers a `propose_nav_param_change` response
- [x] Healthy run triggers a `propose_mission_plan` response (Claude's actual, reasonable choice — `generate_world_variant` is the other valid option per the tool spec, not a guaranteed one; the SDF-writing code path itself was verified directly instead)
- [x] New SDF world variant passes `gz sdf -k` validation

---

## Session 14 — Jetson Orin Nano: Flash + ROS2 + CI Runner (~3 hrs)

> **✅ COMPLETE (2026-07-14).** The final proof — step 13c, one manual HIL run on the NVMe
> install — **passed first-attempt 2026-07-14**: multicast DDS crossed the shared link
> (scan 9.96 Hz on the Jetson), Nav2 active, mission nav → photo → return in ~10 s, exit 0,
> photo + `('mission1', 'PASS', 'hil_jetson', 'gazebo')` telemetry row on the Jetson.
> History below.
> SD era (Parts 1–8, done 2026-07-10): real hardware flashed, networked, ROS2 Jazzy
> installed, native `colcon build` (4.76s), full pytest suite native, Jetson registered as
> a self-hosted GitHub Actions runner, and the native arm64 build stage confirmed on it
> (~2.4x faster than the QEMU baseline — see BLUEPRINT.md's decision log). Two real CI
> permissions bugs were hit and fixed along the way (PR #1) — see
> `docs/runbooks/JetsonInstallSession14.md` Part 8.2 for the story. **Part 9 executed
> 2026-07-13:** headless NVMe **fresh install** via SDK Manager recovery flash (~12 min;
> the clone path was retired unattempted — JetPack-6-era scripts vs this board's r39.2
> boot layout, evidence in the runbook's Part 9 decision notes), re-provisioned end-to-end
> from the runbook, NVMe-at-25W baselines recorded (colcon 5.31s ≈ SD tie; docker pull
> 2.5× faster; cold arm64 CI build 568s ≈ SD 585s — Part 7 table), runner re-registered
> and **proven by a full 8-job-green CI cycle (run 29301726080)**. Part 10 closeout items
> done except marking this session ✅, which waits on 13c. State to know: username **`mike`**
> (lowercase — the SD era's capital-M `Mike` is gone), hostname **`jetson`**
> (`ssh mike@jetson.local` works via mDNS), IP `10.42.0.217` (DHCP lease, may shift —
> re-check with `ip neigh show dev enp6s0`), rootfs on NVMe, GUI off (`multi-user.target`),
> power pinned 25W, CUDA/TensorRT intentionally not installed. The microSD is the untouched
> rollback — stored until Session 16's `stage-4-hil` is 3× green. **Condition met
> 2026-07-15** (run 29457812843 green 3×, all 8 jobs incl HIL) — microSD released for
> wipe/repurpose.
>
> **CI pipeline rewiring done in parallel tonight (2026-07-10), not part of this session's
> original scope:** `stage-3-arm64` now fails fast behind `stage-2-gazebo` passing, and
> `stage-4-isaac` now runs after `stage-3-arm64` (job keys renumbered to match execution
> order); drift/report recording was split into independent sim and hardware paths. Full
> rationale in BLUEPRINT.md's decision log. This surfaced a bigger idea — Isaac Sim + the
> real Jetson talking to each other as genuine hardware-in-the-loop CI — that's promoted out
> of this
> session's stretch goal below into its own **Session 15**.

### Recommended Reading
- [NVIDIA SDK Manager](https://developer.nvidia.com/sdk-manager) — the flashing tool; install on Ubuntu host
- [JetPack 7.x release notes](https://developer.nvidia.com/embedded/jetpack) — confirm Orin Nano Super support for the JetPack 7.2 release specifically before flash day (linked page covers the JetPack family generally, not a version-specific archive URL)
- [Self-hosted runners: adding from org](https://docs.github.com/en/actions/hosting-your-own-runners/managing-self-hosted-runners/adding-self-hosted-runners) — same flow as Session 10 but on the Jetson

> **Session reviewed against actual code 2026-07-06** — the flash step and CI job snippet
> below were stale (see corrections inline). Not yet re-verified against real hardware or
> current NVIDIA downloads — see "Double-check before starting" below.
>
> **Hardware dependency:** This session requires the Jetson Orin Nano Super Developer Kit
> to be physically on hand. Sessions 10–13 can be completed while waiting for hardware.
>
> **JetPack / ROS2 note (2026-07-03):** Plan is **JetPack 7.2** (L4T 39.2 = Ubuntu 24.04 →
> ROS2 **Jazzy**) — supported on Orin Nano and verified in BLUEPRINT's compatibility matrix.
> That makes the entire chain one distro: x86 workstation (24.04/Jazzy), stage-2 Docker image
> (`ros:jazzy-ros-base` = 24.04/Jazzy), Jetson (24.04/Jazzy). **There is no Humble anywhere
> in the pipeline.** Flash-day sanity check: `cat /etc/os-release` should report 24.04; in
> SDK Manager select JetPack 7.2, not 6.x (the flash step below said 6.x until this review —
> that directly contradicted this same note and would have flashed the wrong OS/ROS2 distro
> entirely if followed as originally written).
>
> **Double-check before starting:** confirm JetPack 7.2 is still SDK Manager's selectable
> option for Orin Nano *Super* specifically (vs. the plain Orin Nano) — this plan has not
> been re-verified against NVIDIA's current downloads since the 2026-07-03 decision.
>
> **How this session is actually expected to go (2026-07-06):** core session — unpack, plug
> in, connect, flash, do a smoke test. The "retire QEMU" outcome isn't a separate future task —
> it's already the natural result of the step order below: native `colcon build` first (a
> quick compile test), and *if* that goes cleanly, the `stage-2-arm64` runner swap later in
> this same session follows from it. If the native build has problems, stop there and debug
> before touching the CI job — don't force the runner swap on a build that isn't solid yet.
> Beyond that core flow, there's one **optional** stretch goal (Jetson-in-the-loop with sim)
> captured near the end of this session, below — not required for session completion, and
> explicitly not something to force if the core flow above takes the full session.

### Prerequisites
- Sessions 10–13 complete
- Jetson Orin Nano Super Developer Kit received
- Ubuntu workstation with SDK Manager installed
- USB-C cable + power supply for Jetson
- Ethernet cable (Jetson to router or direct to workstation)

### Steps

> **➡️ Detailed do-it-yourself runbook: [`docs/runbooks/JetsonInstallSession14.md`](JetsonInstallSession14.md).**
> That doc is the step-by-step version of everything below (unpack → flash → headless SSH →
> smoke tests → ROS2 → baseline → CI runner → NVMe). The checkboxes here are the summary.

> **⚠️ Correction (2026-07-08): JetPack 7.2 removed the microSD card image.** The old
> "burn an SD image with Etcher and boot it" workflow — and the "R1 ships on MicroSD, the dev
> kit default (a pre-imaged card)" framing below — no longer exist. JetPack 7.2 installs only
> via (a) **SDK Manager** over USB-C in recovery mode, or (b) a unified **Jetson ISO** written
> to a *USB stick* that installs onto microSD/NVMe. We use SDK Manager (host = the x86 box).
> "MicroSD first" still works: you just select microSD as the *flash target* in SDK Manager.

- [ ] **Install NVIDIA SDK Manager on workstation**:
  ```bash
  # Download .deb from https://developer.nvidia.com/sdk-manager
  sudo apt install ./sdkmanager_<version>_amd64.deb
  sdkmanager  # launches GUI
  ```

- [ ] **Flash JetPack 7.2 via SDK Manager** (full steps in `docs/runbooks/JetsonInstallSession14.md` Part 3):
  - Jetson into recovery mode: **short `FC REC`↔`GND` on J14 while applying power** (confirm
    pin numbers against the printed quick-start card), USB-C to the host; verify with
    `lsusb | grep -i nvidia` → `0955:7523 APX`.
  - SDK Manager → Jetson Orin Nano (module **P3767-0005** / carrier **P3768-0000**) →
    **JetPack 7.2** (not 6.x — see decision note above).
  - **Pre-config the OS account** (username/password/hostname) so first boot is headless — no
    OEM wizard, SSH-ready.
  - **Storage target = microSD** for this first flash (OS image only; add SDK components after).
  - Flash — takes 20–40 min. Verify after first boot: `cat /etc/os-release` reports 24.04.

- [ ] **Storage: flash to MicroSD and record a baseline:**
  R1's baseline is captured on MicroSD (selected as the SDK Manager flash target — there is no
  pre-imaged card in JetPack 7.2). Record during this session:
  - apt/ROS2 install wall time
  - `time colcon build --symlink-install` (native arm64 on SD)
  - first `docker pull` time of the stage-2 image (see container step below)
  > **SD hygiene:** don't record rosbags or heavy logs to the SD card while it's still in
  > use — storage write speed only bites when *recording*, and sustained writes are what
  > wear SD cards out. DDS traffic itself is RAM-to-RAM and doesn't touch storage.

- [ ] **Swap to NVMe SSD and re-record the same numbers (moved up from Session 18+,
  2026-07-06)** — do this now, while the module is still a bare dev kit on the desk, not
  after Session 18 transfers it into the robot chassis. Swapping storage is strictly easier
  before it's wired into anything:
  ```bash
  # Reflash to NVMe via SDK Manager — same recovery-mode/USB-C process as the
  # original flash step above, just targeting the NVMe device this time.
  ```
  Re-run the exact same three measurements (apt/ROS2 install, `colcon build`, `docker
  pull`) on NVMe and publish the SD-vs-NVMe before/after table in BLUEPRINT.md's decisions
  log — the second "measured, marketed" number after QEMU→native.
  > **Trade-off to know going in:** an SD card can be re-flashed from any PC with a card
  > reader — quick, no special mode needed. Wiping/reflashing NVMe requires recovery mode
  > + SDK Manager every time. The SD card's "golden image, quick-restore" convenience goes
  > away once you're on NVMe — worth it for write endurance, but it's a real cost, not a
  > pure upgrade. **This becomes mandatory, not optional, if the R2 leader-node role ever
  > lands** — central telemetry logging + an on-robot fleet DB is sustained-write duty a
  > MicroSD card can't take.

- [ ] **Initial Jetson setup** (SSH from workstation — find Jetson IP via router or `arp -a`):
  ```bash
  ssh mike@<jetson-ip>
  sudo apt update && sudo apt upgrade -y

  # Install ROS2 Jazzy — JetPack 7.2 = Ubuntu 24.04, same distro as the workstation and
  # the stage-2 Docker image, no Humble anywhere in this pipeline (2026-07-03 decision):
  sudo apt install software-properties-common curl -y
  sudo curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key \
    -o /usr/share/keyrings/ros-archive-keyring.gpg
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] \
    http://packages.ros.org/ros2/ubuntu $(. /etc/os-release && echo $UBUNTU_CODENAME) main" \
    | sudo tee /etc/apt/sources.list.d/ros2.list > /dev/null
  sudo apt update
  sudo apt install ros-jazzy-desktop ros-jazzy-navigation2 ros-jazzy-nav2-bringup \
    ros-jazzy-rmw-cyclonedds-cpp python3-colcon-common-extensions -y

  # Add to .bashrc:
  echo "source /opt/ros/jazzy/setup.bash" >> ~/.bashrc
  echo "export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp" >> ~/.bashrc
  source ~/.bashrc
  ```

- [ ] **Clone the repo and do a native arm64 build**:
  ```bash
  # On Jetson:
  cd ~
  git clone https://github.com/sdfinn/autonomous-fleet-testbed.git
  cd autonomous-fleet-testbed
  colcon build --symlink-install
  # This is the native arm64 build — record the time:
  time colcon build --symlink-install
  ```

- [ ] **Pull the stage-2 CI image on the Jetson and run the unit tests inside it** — this is
  the "hardware-verified binaries to the edge" claim made literal: the *exact arm64 artifact*
  stage-2 built and pushed to GHCR runs on the target silicon, not a rebuild from source.
  The image only bakes in `src/` (no `tests/`), so mount the repo checkout for the test files:
  ```bash
  # On Jetson (Docker Engine install: same apt-repo method as Session 03):
  time docker pull ghcr.io/sdfinn/autonomous-fleet-testbed:latest   # record — SD baseline number
  docker run --rm --network=host \
    -v ~/autonomous-fleet-testbed:/repo -w /repo \
    ghcr.io/sdfinn/autonomous-fleet-testbed:latest \
    bash -c "source /ros2_ws/install/setup.bash && python3 -m pytest tests/ -v \
      --ignore=tests/test_ros2_contracts.py --ignore=tests/test_navigation.py"
  ```
  > **Decision (2026-07-03 — bare metal + container hybrid):** bare metal stays the runner/
  > build path for Session 14 (simplest first boot, and it produces the QEMU→native speedup
  > headline). The stage-2 image is NOT retired — it's repurposed as this artifact-parity
  > check. Since the Jetson is natively 24.04/Jazzy (JetPack 7.2), identical to the image,
  > running the robot *from* a container buys environment pinning and rollback — not distro
  > compatibility. So: **bare metal robot runtime is the R1 default**; container runtime is
  > an R2+ option (pairs with the RaaS/OTA framing in BLUEPRINT's What's Next). If the
  > container ever drives hardware it needs `--network=host` (DDS) plus `--device`
  > passthrough for the serial/lidar ports.

- [ ] **Register Jetson as GHA self-hosted runner**:
  ```bash
  # On Jetson — same flow as Session 10 but with arm64 labels:
  mkdir -p ~/actions-runner && cd ~/actions-runner
  # Get the arm64 runner download URL from GitHub →
  # Your repo → Settings → Actions → Runners → New self-hosted runner → Linux → ARM64
  curl -o actions-runner-linux-arm64-<VERSION>.tar.gz -L <URL>
  tar xzf ./actions-runner-linux-arm64-<VERSION>.tar.gz
  ./config.sh \
    --url https://github.com/sdfinn/autonomous-fleet-testbed \
    --token <TOKEN> \
    --labels self-hosted,arm64,jetson \
    --name jetson-runner \
    --unattended
  sudo ./svc.sh install && sudo ./svc.sh start
  ```

- [ ] **Update the real `stage-2-arm64` job** in `ci.yml` to run on the Jetson runner —
  this was a from-scratch bespoke job in the original draft (wrong name `arm64-build`,
  wrong `needs: code-quality`, and a plain `colcon build` that doesn't match what
  `stage-2-arm64` actually does today: build+push a Docker image via `docker buildx`,
  not a native workspace build). The actual change needed is two edits to the existing
  job, not a new one — the QEMU setup step becomes unnecessary once the runner itself
  is native arm64 hardware, since `docker buildx` can then build `linux/arm64` directly:
  ```yaml
  stage-2-arm64:
    runs-on: [self-hosted, arm64, jetson]   # was: ubuntu-latest
    needs: [stage-1-quality, changes]        # unchanged — keep the docs-only-push skip
    if: needs.changes.outputs.docker == 'true'
    permissions:
      contents: read
      packages: write
    steps:
      - uses: actions/checkout@v4

      # "Set up QEMU" step REMOVED — only needed to emulate arm64 on an x86 runner;
      # the Jetson runner already is arm64.

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3
      # ...rest of the job (GHCR login, build-and-push, timing) stays as-is; just
      # relabel the "Record build time" log line "native" instead of "QEMU".
  ```

  > **Gotcha (amended 2026-07-03):** The Jetson native runner replaces QEMU for the *build*
  > job, but stage-2's image build is NOT obsolete — the artifact-parity step above depends
  > on stage-2 continuing to push the arm64 image to GHCR. Keep stage-2 producing the image
  > (natively on the Jetson runner now, so it should drop from ~24 min to minutes); what goes
  > away is only the QEMU emulation, not the Dockerfile or the image.

- [ ] **Push and record the speedup**:
  ```bash
  git add .
  git commit -m "feat(session-14): Jetson arm64 native CI runner replaces QEMU"
  git push
  gh run watch   # watch stage-2-arm64 run on jetson-runner
  # Compare time vs QEMU baseline recorded in BLUEPRINT.md (Session 08)
  ```

  Record in BLUEPRINT.md:
  ```
  arm64 build — QEMU (Session 08): ~25-30 min
  arm64 build — Jetson native (Session 14): ~X min
  Speedup: ~Xx reduction
  ```

### Optional stretch goal — Jetson-in-the-loop with sim (2026-07-06, not required)

> **Promoted to its own session, 2026-07-10 — see Session 15.** What started here as an
> optional stretch goal turned into a real pipeline design idea (Isaac Sim + the real Jetson
> as genuine hardware-in-the-loop CI, not just a local resource-budget check). This block is
> kept as-written for the historical record of the original idea and its reasoning (notably:
> Gazebo over Isaac, argued below) — Session 15 is where that reasoning gets re-examined and
> the actual design happens, since the new idea explicitly puts Isaac in this slot instead.

Not required for session completion, r1-complete, or Session 18 — only attempt this if the
core flow above (unpack → flash → storage baseline → native build → CI runner swap) goes
smoothly with session time left over. This is the "run ROS2 code on the Jetson as part of
sim" idea, refined through discussion:

- **Goal:** validate robustness/speed/reproducibility of running Nav2 on Jetson-class ARM
  hardware before Session 18's real robot arrives — mainly, does Nav2 (AMCL, costmaps,
  planners) actually fit the Orin Nano's CPU/RAM budget, or does it need retuning first.
- **Use Gazebo, not Isaac Sim, as the sim side.** Isaac's ROS2 integration is already the
  most fragile part of this project (manual `/clock` wiring, TF replay requiring
  synchronized restarts — see the CLAUDE.md gotcha). Adding a second machine and a live
  network link on top of that is asking for a new multi-day debugging saga for a benefit
  that doesn't need Isaac's fidelity at all. Gazebo's `ros_gz_bridge` is a standard,
  well-behaved bridge with none of that baggage, and it's already this project's cheaper
  "throughput tier" — the natural fit.
- **Connect the Jetson directly, not over WiFi.** Either the Jetson's USB-C device-mode
  networking (comes up as a point-to-point virtual Ethernet link, default IP
  `192.168.55.1` — the same feature NVIDIA's headless dev-kit setup uses) or a plain
  Ethernet cable / unmanaged switch. Either removes WiFi's contention/jitter, which
  matters for anything clock-sensitive. Verify with `ping` and a cross-machine
  `ros2 topic list` (or the Session 02 talker/listener smoke test) before touching
  Nav2 at all.
- **Same `ROS_DOMAIN_ID` on both machines.** If DDS discovery doesn't work over the USB
  gadget link (multicast sometimes doesn't traverse it cleanly), CycloneDDS supports an
  explicit unicast peers list in `CYCLONEDDS_URI` (`<Peers><Peer address="..."/></Peers>`)
  as a documented fallback — a known fix, not a research project.
- **Sensors stay on the Gazebo/workstation side; Nav2 runs entirely on the Jetson** — the
  workstation's job is only to stream sensor topics and listen for `cmd_vel`, matching
  Session 18's actual target architecture where sensors and Nav2 will both live on the
  Jetson (this exercise doesn't test that exact network topology, since nothing streams
  over a network in the real robot — but it does validate Nav2-on-Jetson resource usage).

### Session Complete When
- Jetson boots, SSH accessible, ROS2 installed
- `colcon build` succeeds on Jetson (native arm64)
- `stage-2-arm64` CI job runs green on `jetson-runner`
- Speedup vs QEMU recorded in BLUEPRINT.md
- SD-vs-NVMe before/after table (apt/ROS2 install, `colcon build`, `docker pull`) published
  in BLUEPRINT.md's decisions log

---

## Session 15 — Gazebo + Real Jetson Hardware-in-the-Loop (Mission 1)

> **Session title renamed 2026-07-12:** created as "Isaac Sim + Real Jetson HIL" on
> 2026-07-10 *before* the design pass chose Gazebo over Isaac — the old title outlived the
> decision it predated and caused real confusion on review. The prose below still says
> "Isaac Sim" in places because it's the historical record of how the session was framed
> when it was created; the decisions and the delivered system are Gazebo-based.
>
> **Status: COMPLETE (2026-07-11, merged to main 2026-07-12).** Designed 2026-07-10 (spec
> approved); implemented and HIL-proven 2026-07-11 — Mission 1 (navigate → photograph →
> return) PASS on x86 Gazebo and PASS on the real Jetson (Nav2 + mission executor on the
> Orin, Gazebo on the workstation, first attempt, ~18 s — `docs/runbooks/Mission1HILSession15.md`
> Results). The CI stage is **designed, not implemented**
> (`docs/session15-hil-ci-stage-design.md` — `stage-4-hil` replaces `stage-4-isaac` when
> built); until then CI's Stage 4 remains the existing Isaac check. Promoted from Session
> 14's optional "Jetson-in-the-loop with sim" stretch goal (preserved as-written there,
> including its original Gazebo-over-Isaac reasoning) into its own session, after a CI
> pipeline-restructuring conversation surfaced a bigger version of the same idea: not just
> "does Nav2 fit the Orin Nano's resource budget," but **Isaac Sim and the real Jetson
> genuinely talking to each other as a CI-testable hardware-in-the-loop stage**. A full
> `/superpowers:brainstorming` pass (same day) resolved the "Open questions to resolve"
> below — decisions and reasoning are captured in full at
> `docs/superpowers/specs/2026-07-10-session15-gazebo-hil-mission1-design.md`, summarized
> here (mission numbering below uses the revised 2026-07-11 scheme — on review Mike flagged
> "Mission 2 first, Mission 1 second" as confusing, so the first milestone is now Mission 1
> and the deferred coverage/reactive follow-up is Mission 2):
> - **Gazebo, not Isaac Sim, for both Stage 2 and Stage 4/HIL.** Isaac shelved (not
>   discarded) — its proven fragility in this project is Nav2/AMCL-specific plus a general
>   operational tax, neither of which the actual near-term mission exercises; no
>   camera/perception-specific Isaac issue has ever been hit here. Isaac's real
>   differentiators (Replicator synthetic data, NITROS-accelerated Isaac ROS) only pay off
>   once a mission needs a *trained* model — not the case yet.
> - **Scope: one robot, not a fleet, to start.** The long-term multi-sensor/multi-robot
>   vision is real but is its own multi-subsystem project, not designed here.
> - **First concrete milestone: "Mission 1"** — navigate to the doorway center (real
>   heading-correction navigation), take a picture (new action primitive), return to start.
>   Deliberately excludes ball-reaction and full-coverage sweep — those are "Mission 2," an
>   explicitly deferred follow-up (approach for both is decided in the spec, just not built).
> - Mission framework builds on Session 13's `SEMANTIC_MAP` multi-waypoint infrastructure
>   rather than a bespoke script, so different missions (Mission 1, Mission 2, ...) are
>   actually switchable.
>
> **Next step:** review the spec doc, then `/superpowers:writing-plans` for the actual
> implementation plan (bare-metal Mission 1 prototype first, per this project's tiered
> dev-loop philosophy, before touching CI).
>
> **Does not include NVMe SSD migration** — that stays in Session 14 (Part 9), since it's
> Jetson hardware setup, not HIL design; the two can proceed in parallel.

### Where this came from

A CI pipeline-restructuring discussion (2026-07-10, captured from a hand-drawn diagram —
`IMG_5291.jpg`) proposed splitting the pipeline into two verification paths after Stage 2
(Gazebo): a fast sim path straight to its own drift/report job, and a slower hardware path
(`stage-3-arm64` → `stage-4-isaac` → its own drift/report job). That rewiring, including
renumbering the job keys and wiring the literal arm64→Isaac ordering edge to match the
diagram exactly, is done — see BLUEPRINT.md's 2026-07-10 decision log entries for the full
`ci.yml` changes and the mid-course correction once the graph was checked against the
drawing. What's still missing, and is Piece 2 (this session): `stage-4-isaac` runs *after*
`stage-3-arm64` now, but doesn't yet *consume* anything from it — Isaac Sim still doesn't
touch the real Jetson at all. Actually deploying/exercising the arm64-built image on the
Jetson as part of Stage 4 is the real work this session designs.

### Open questions to resolve (in order, before implementation)

> **All resolved 2026-07-10** — kept below as the historical record of the reasoning process
> (including the research/pushback that shaped it), not because they're still open. See
> `docs/superpowers/specs/2026-07-10-session15-gazebo-hil-mission1-design.md` for the actual
> decisions and full reasoning, and the status block at the top of this session for a summary.

1. **Isaac vs. Gazebo vs. something else as the sim side — genuinely open, not decided.**
   Session 14's original 2026-07-06 note picked Gazebo specifically for this use case,
   calling Isaac's ROS2 integration "the most fragile part of this project" (manual `/clock`
   wiring, TF replay requiring synchronized restarts — see `CLAUDE.md`'s Isaac gotchas).
   Tonight's diagram instead puts HIL on Isaac, reusing Stage 4's existing slot. Both are
   defensible: Isaac has gotten measurably more stable since that note (Session 11/12 got it
   green in CI), but stacking real-hardware network sync on top of either engine's existing
   fragility is a new failure mode regardless of which one.
   - **Do the research this session should start with:** what does the robotics/AMR industry
     actually do for hardware-in-the-loop testing — is Isaac Sim the trend, or do most teams
     use Gazebo (or something else entirely, e.g. Webots, a custom HIL rig) for this
     specifically? Don't assume Isaac is "the fidelity tier so it must be the HIL choice" —
     verify that reasoning against real practice before committing engineering time to it.
2. **Bare-metal-first, branch to arm64 later — matches this project's existing "tiered dev
   loop" philosophy (BLUEPRINT.md).** Rather than building the HIL bridge directly against
   the CI/arm64 path, prototype it bare-metal first: both Gazebo-HIL and Isaac-HIL running
   against the Jetson's native OS install (no Docker, no CI), get one solid, *then* decide
   whether/how it becomes a CI stage. Cheaper iteration, same reasoning as why Tier 1 (x86
   bare metal) comes before Tier 2/3 for everything else in this project.
3. **Network orchestration mechanics — real open questions, not yet researched:**
   - Does a GitHub Actions job running on the x86 GPU runner (Isaac's host) have a clean way
     to orchestrate the Jetson (a *separate* self-hosted runner) mid-job? Or does this need to
     be structured as two coordinated jobs, or a job that SSHes into the Jetson directly
     rather than treating it as a GHA runner for this stage?
   - What defines "success" for a HIL test — Nav2 goal-reached on the real hardware side,
     matched against Isaac's simulated ground truth? Timeout/teardown behavior if the Jetson
     side hangs or the network link drops mid-test?
   - Network topology: Session 14's original note suggested direct Ethernet or the Jetson's
     USB-C device-mode link (point-to-point, default `192.168.55.1`), same `ROS_DOMAIN_ID`
     on both machines, CycloneDDS unicast peers (`CYCLONEDDS_URI`) as a fallback if multicast
     discovery doesn't traverse the link — still the right starting point, re-verify once
     bare-metal prototyping (point 2) is underway.
4. **Only after 1–3 are answered:** design the actual CI stage — whether it replaces Stage 4
   outright, becomes a new Stage 4b, or something else. The job *ordering* already matches
   the diagram (`stage-4-isaac` runs after `stage-3-arm64`, renumbered 2026-07-10 — see
   BLUEPRINT.md decision log) but Stage 4 doesn't yet *consume* anything from arm64's build —
   this session designs the actual mechanism for Isaac (or whichever engine) to deploy/pull
   that image onto the real Jetson and exercise it as hardware-in-the-loop.

### Session Complete When
- [x] Isaac-vs-Gazebo decision made and recorded — see spec doc + BLUEPRINT.md decision log
      (2026-07-10). Gazebo, for both Stage 2 and Stage 4/HIL.
- [x] First concrete milestone scoped — "Mission 1" (navigate → photograph → return),
      ball-reaction/coverage explicitly deferred to a "Mission 2" follow-up (numbering
      revised 2026-07-11 on review — build order now matches mission number)
- [x] A bare-metal HIL prototype (Jetson + Gazebo, real network link) runs Mission 1 at least
      once, manually, outside CI — **PASS on the first attempt (2026-07-11)**, see
      `docs/runbooks/Mission1HILSession15.md` Results section (multicast DDS discovery worked, Nav2 active
      in ~5 s on the Orin, mission total ~18 s, DB row
      `('mission1','PASS','hil_jetson','gazebo')`; single-run caveat noted there)
- [x] A design for the actual CI stage exists (even if not yet implemented) — network
      orchestration approach, success/failure definition, timeout/teardown behavior — see
      `docs/session15-hil-ci-stage-design.md` (one GHA job on the x86 runner driving the
      Jetson over SSH; §1–§3 cover orchestration, success/failure, timeout/teardown)
- [x] Job renumbering plan decided for any new CI stage this work introduces (separate from
      the existing stage-0..5 renumbering already done 2026-07-10 — see BLUEPRINT.md) — **no
      renumbering; `stage-4-hil` takes the existing Stage 4 slot, replacing `stage-4-isaac`
      when implemented** (`docs/session15-hil-ci-stage-design.md` §4)
- [x] Implementation plan written (`/superpowers:writing-plans`) from the approved design spec
      — `docs/superpowers/plans/2026-07-11-session15-mission1-hil.md`

---

## Session 16 — HIL CI Stage with Gazebo + Mission 2

> **Created 2026-07-12** — closes the gap Mike caught on review: Session 15 *designed* the
> Gazebo HIL CI stage but (deliberately) did not implement it, and the plan then jumped
> straight to the real robot. The pipeline should run hardware-in-the-loop automatically
> before a rover exists. Prior Session 16 (Real Robot) renumbered to 17; prior 17+ (Agentic
> on hardware) to 18+ — second renumbering, same convention as 2026-07-10: dated historical
> entries keep their original numbers, living text uses the new ones.
>
> **Rescoped 2026-07-12 (evening).** This session is now *build only*: implement
> `stage-4-hil` (Gazebo in, Isaac out) **and Mission 2** — the camera-reactive half of the
> spec's Decision 5, including a real USB camera on the Jetson as a manual perception-HIL
> tier. The old "Tidy Up E2E Simulation" review work moved to the **new Session 17
> (Harden, Stabilize & Review)**, except items that directly protect this session's
> deliverables (kept below as Piece 3). Prior Session 17 (Real Robot) → 18; prior 18+
> (Agentic) → 19+ — third renumbering, same convention. Per the same discussion: **no
> per-session runbook** — everything executable lives here.

**Build from:** `docs/session15-hil-ci-stage-design.md` (the decided design — one
SSH-orchestrated job on the x86 runner driving the Jetson; success/failure definition;
timeout budgets; teardown), `docs/runbooks/Mission1HILSession15.md` (the proven manual
procedure this stage automates — its Troubleshooting section already documents the
non-interactive-SSH sourcing trap the CI job will hit), and
`docs/superpowers/specs/2026-07-10-session15-gazebo-hil-mission1-design.md` **Decision 5**
(the approved camera-reactive approach Mission 2 implements: split by behavior type, using
Nav2's own mechanisms — no custom BT).

> **Ordering rule (same reasoning the Session 15 spec used):** get `stage-4-hil` green 3×
> with **Mission 1** — the proven mission — before Mission 2 enters the stage. Never debug
> a new CI stage and a new mission at the same time.
>
> **▶ Execution started 2026-07-14 — Plan A:**
> `docs/superpowers/plans/2026-07-14-session16-stage4-hil.md` (branch
> `session-16-stage4-hil`; live task ledger: `.superpowers/sdd/progress.md`). The plan
> sequences this session's pieces per the ordering rule above — **Piece 3 first** (its
> fixes protect the stage), **then Piece 1, then Piece 2 as a separate Plan B** after the
> 3×-green gate:
> | Plan A task | Implements |
> |---|---|
> | 1 | Piece 1 power-policy item (b): `power_mode` telemetry column |
> | 2 | Piece 3: FAIL-row metric skew policy |
> | 3 | Piece 3: `MissionRunner()` constructor inside try |
> | 4 | Piece 3: `test_mission_run.py` into stage-2 (found+fixed a real costmap-accumulation bug) |
> | 5 | Piece 1 power-policy item (a): passwordless nvpmodel (already provisioned — no-op) |
> | 6–7 | Piece 1: all stage logic as locally-runnable `scripts/hil_stage.sh` + local E2E proof at 15W |
> | 8 | Piece 1: `stage-4-hil` job replaces `stage-4-isaac` + registry build cache + BuildKit GC |
> | 9–10 | Piece 1: PR, then the ≥3×-consecutive-green reproducibility gate; closeout ticks the boxes below |
> | 11 | Piece 3: return-leg corner-clip investigation |
> | 12–13 | Piece 1 phase 2 (gated on 3×-green): containerized mission + HIL row into drift DB |
> | Plan B | Piece 2: Mission 2 (written after the Task 10 gate) |
> **Hard precondition on Task 13 (phase 2b — ship HIL row to drift DB):** `baseline_monitor`
> MUST partition/filter by `power_mode` before HIL rows enter the shared baseline. Task 1's
> `power_mode` telemetry field exists but nothing enforces never-compare-15W-vs-25W today —
> Task 13 inserting `hil_jetson` rows into the shared workstation `FLEET_DB` unpartitioned
> would land 15W HIL timings in the same baseline as 25W sim timings, exactly the silent
> cross-mode comparison Task 1 was meant to prevent (final review 2026-07-15, I4). Do not
> start Task 13 until this partition/filter is in place.
> Power split decided 2026-07-14: Jetson builds at 25W, HIL mission at **15W** (deployment
> budget), always-restore 25W. The boxes below are ticked at plan closeout, not per-task.
>
> **Status at 2026-07-15 pause:** Plan A tasks 1–8 complete + review-approved (the local
> E2E HIL run PASSED at 15W: mission ~19 s, photo + `hil_jetson`/`15W` telemetry row).
> **PR #2 open; first pipeline run RED at stage-2** — diagnosed and reproduced: after the
> combined test session's driving, accumulated global-costmap marks close the
> hallway-arch corridor and the mission return leg fails to plan (`"Failed to create plan
> with tolerance of: 0.300000"` → abort). This confirms the Piece-3 corner-clip item is
> real costmap marginality at the arch. Full diagnosis + resume sequence:
> `.superpowers/sdd/progress.md` ("SESSION PAUSED 2026-07-15"). Next session starts
> there: confirm the clear-costmaps-per-leg mitigation, pick fix altitude, add the
> stage-2 log artifact, re-run PR #2, then the 3×-green gate.
>
> **✅ MERGED 2026-07-15 evening — PR #2 → main (`af9c769`), Tasks 9–11 closed.** The
> stage-2 red became a five-layer debugging arc, executed live with Mike at the GUI
> (full record: `.superpowers/sdd/progress.md`, briefs/reports `task-9b`–`task-9e`,
> `final-review-session16.md`):
> 1. **Costmap accumulation** (pre-diagnosed) → mission_runner clears both costmaps
>    before every navigate leg.
> 2. **AMCL delocalization** on the return leg (multi-modal flips in the symmetric
>    hallway) → traced past alphas to the real source:
> 3. **Skid-steer odometry lies ~30% about in-place rotation** (measured:
>    `.superpowers/sdd/spin_experiment.py` — body 146.5° vs odom ~192°) → **EKF fusion**
>    (`config/ekf.yaml`: IMU yaw-rate + wheel-odom translation; the URDF's IMU had never
>    actually published — world SDF lacked `gz-sim-imu-system`), asymmetric AMCL alphas,
>    slower rotate-to-heading. Fused yaw now tracks body <1°; misses 0.38–0.70 m → 0.08–0.20 m.
> 4. **False-PASS hole Mike caught eyes-on** (mission PASSed while the robot was
>    physically stuck): stage-2 now asserts **Gazebo ground-truth arrival** (0.25 m);
>    mission_runner prints the ground-truth miss every sim run. "Return to start" ends
>    at the start POSE (explicit yaw).
> 5. **Orphaned bridge processes poison DDS domain 0** (root cause of the CI
>    goal-rejection red — 8,716 "jump back in time" lines in the new stage-2 log
>    artifact): stage-2 sweeps the full process pattern before launch + after job;
>    CLAUDE.md gotcha added.
> **Task 10 gate: run 29457812843 green 3× (all 8 jobs incl real-Jetson HIL each time)**;
> final whole-branch review: 0 Critical / 4 Important — all fixed (`92359f5`).
> **Task 11 (corner-clip) closed by this arc:** root cause was the odometry rotation lie
> driving the controller east of a clean plan — not inflation-vs-arch-width; verified
> eyes-on with Mike (step-4 alignment pass) + ground-truth meter. Inflation tuning not
> needed. **Remaining in this session's scope: Tasks 12–13 (phase 2, gate now open —
> note the hard `power_mode` precondition on 13 above) and Plan B (Mission 2).**
> Future capability noted (Mike): uncertainty-aware speed — "slow down when unsure,
> speed up when the risk is low" (rotate-to-heading slowdown is its first crumb; pairs
> with Session 19+ recovery work).

### Piece 1 — Implement `stage-4-hil` (replaces `stage-4-isaac`)

- [x] New CI job `stage-4-hil` per the design doc: x86 runner launches
      `sim_only_launch.py`, drives the Jetson over SSH (explicit ROS+overlay sourcing +
      `RMW_IMPLEMENTATION` export in every SSH command), runs
      `RUNNER_TYPE=hil_jetson python3 -m nav_fleet.mission_runner mission1`, scps the photo
      back as a workflow artifact, prints the Jetson's telemetry row to the job log.
- [x] Timeouts and teardown exactly per design doc §3 — job `timeout-minutes: 15`; phase
      budgets 60/120/300 s; `if: always()` teardown with unconditional `pkill -9` on BOTH
      sides (SIGINT alone left orphans in 2 of 3 Session 15 manual Tier-1 teardowns).
- [x] **Retire `stage-4-isaac` in the SAME change** (slot swap — keep `needs: stage-3-arm64`
      and `stage-5-reports-hw`'s shape; Isaac scripts stay in git history, not deleted from
      disk preemptively).
- [x] Jetson-side prerequisites: resolve the DHCP lease at job start
      (`ip neigh show dev enp6s0`); deal with the nested `actions-runner/` checkout inside
      the repo (relocate it, or standardize `colcon build --base-paths src` — it's a latent
      colcon trap either way).
- [x] **Reproducibility:** ≥3 consecutive green `stage-4-hil` runs. Session 15's HIL record
      is a single successful run — this is the open risk the CI stage exists to close.
- [x] Phase 2 (this session or explicitly re-deferred): the job pulls the `stage-3-arm64`
      GHCR arm64 image onto the Jetson and runs the mission executor *inside that
      container* — finally making the arm64→Stage-4 edge consume something real.
      (Shipped 2026-07-15, PR #3 → cf343da; second run all green — first CI exercise of
      the full chain: arm64 image → GHCR pull → in-container mission at 15W → HIL
      telemetry row shipped to the workstation drift DB.)
- [x] **Registry-backed Docker build cache** for `stage-3-arm64`: add
      `cache-from`/`cache-to: type=registry,ref=ghcr.io/sdfinn/autonomous-fleet-testbed:buildcache,mode=max`
      to the build-push step so layer cache survives BuildKit GC, builder recreation, and
      Jetson reboots. (Root cause of the 2026-07-12 18-minute build: the apt layer's cache
      was evicted, so the build ran fully cold — vs Session 14's 9m45s baseline which kept
      apt cached and only rebuilt pip+colcon.)
- [x] **Per-job power-mode policy (decided 2026-07-12): build fast, test at deployment
      power.** Modes on the Orin Nano Super: 0=15W, 1=25W, 2=MAXN_SUPER
      (`sudo nvpmodel -p --verbose` to list, `-q` to query, `-m <id>` to set). `nvpmodel`
      is **global, persistent state** (`/var/lib/nvpmodel/status` — board pinned to 25W on
      2026-07-12), so CI jobs must not trust ambient state — **each job sets its mode
      explicitly as a first step**: `stage-3-arm64` → 25W (docker/build throughput);
      `stage-4-hil` → **15W if that's the robot's real deployment power budget — confirm
      when Session 18's battery/power design is decided; until then run HIL at 25W and
      record it** — with an `if: always()` teardown step restoring 25W either way. To make
      that work: (a) a passwordless-sudo rule for `nvpmodel` on the Jetson (sudoers
      drop-in, `mike ALL=(root) NOPASSWD: /usr/sbin/nvpmodel`); (b) **record the power mode
      in the telemetry row** (env var → `log_run`), or drift detection will silently
      compare 15W mission timings against 25W ones; (c) re-validate the design doc's phase
      budgets (60/120/300 s) at whatever mode HIL runs at before trusting them — 15W
      changes Nav2 timing. `sudo jetson_clocks` as a per-job step additionally locks
      clocks to the mode's max (not persistent — suits CI, not set-and-forget).
- [x] **Raise BuildKit's GC budget** on the Jetson builder (`buildkitd.toml` `keepBytes` —
      the SD/NVMe has ~90 GB free; the default budget evicts the ~1–2 GB apt layer first).
      Belt-and-braces alongside the registry cache.
- [x] **Re-benchmark the arm64 build after the NVMe migration** (runbook Part 9) at the
      pinned power mode — one fully-cold and one cached timing, recorded in the Part 7
      baseline table, so future "is CI slow?" questions have honest reference numbers.

### Piece 2 — Mission 2: camera-reactive navigation (croquet-ball behaviors)

> **Scope decision (2026-07-12):** Mission 2 = the **camera-reactive half** of the spec's
> Decision 5 only. The full-coverage sweep needs a coverage planner that doesn't exist in
> this project (`opennav_coverage` or a hand-rolled boustrophedon generator) — that is
> **Mission 3**, deferred; numbering follows build order, per the 2026-07-11 rule.
> Approach is the approved one: red ball → stop (supervisor cancels the Nav2 goal via
> `cancel_goal_async()` — urgent/binary, no planning needed); yellow ball → avoid (mark the
> detected area keepout/lethal via a dynamic `nav2_costmap_2d` layer — the planner routes
> around it natively). No custom Behavior Tree — that risk was explicitly rejected.
>
> **Update (2026-07-16): the APPROVED Mission 2 spec
> `docs/superpowers/specs/2026-07-16-mission2-design.md` supersedes this section where
> they conflict.** Yellow is now photo + return home (NO costmap keepout in Mission 2 —
> avoid-and-continue deferred to Mission 3); red = photo + full stop; trigger =
> proximity + persistence (~1 m / 3 frames); ball placement is harness-owned, seeded
> random per CI run; detector publishes vision_msgs; webcam tier is a follow-up plan
> (its checkboxes below transfer there). The checkboxes below predate the spec —
> reconcile them when Plan B is written.

- [x] **HSV ball-detector node** (new, in `nav_fleet/`): reimplement the *algorithm* from
      BC's `behavior_controller.py` (HSV thresholding — hardware-proven, zero training
      data), not the file — this project's `/robot_001/` topic conventions, subscribing to
      a **remappable** image topic, publishing detections (color + bearing + apparent
      size). **HSV thresholds are config data, not code** (e.g. `config/hsv_gazebo.yaml` /
      `config/hsv_realcam.yaml`): Gazebo's OGRE2 rendering and a real webcam under room
      lighting will need different numbers, and that measured delta is itself a
      sim-to-real data point worth keeping.
      **(2026-07-18: implemented** — `nav_fleet/ball_detector.py` + `nav_fleet/hsv_detect.py`,
      publishing the standard `vision_msgs/Detection2D` contract rather than a bespoke
      color+bearing+size message, per the approved 2026-07-16 spec.)
- [x] Red-ball supervisor node (goal cancel) + yellow-ball costmap keepout wiring, per the
      spec bullet above.
      **(2026-07-18: red-ball half implemented, yellow-ball half superseded.** Red-ball
      react (goal cancel + photo + stop) is a reactive step inside `mission_runner.py`
      (`_execute_reaction`), not a separate supervisor node. Yellow-ball costmap keepout is
      **superseded** — the approved spec replaced it with `photo_then_home` (photo, then
      retreat to home_base), no dynamic costmap layer, per the 2026-07-16 design.)
- [x] **Mission framework groundwork** (moved from the old tidy-up list — it IS Mission 2
      work): tighten `validate_mission` (clear error for navigate-without-location; reject
      stray fields per action type) before adding Mission 2's new action types; gate
      `take_picture` freshness on `msg.header.stamp` (required before photo *content*
      becomes a pass/fail signal).
      **(2026-07-18: partially done.** Reactions validation shipped (per-step `reactions`
      dict validated, unknown colors/actions rejected). The `take_picture` freshness stamp
      gate is NOT in scope for this plan — remains open, not silently dropped.)
- [x] **Mission 2 definition** in `missions.py` + executor support in `mission_runner.py`
      (new action types as needed — e.g. enabling/disabling ball-watching around navigate
      legs), telemetry row per run same as Mission 1.
      **(2026-07-18: implemented** — Mission 2 defined in `missions.py`, watch-window
      enable/disable around navigate legs and reaction telemetry (`reaction_events`) shipped
      in `mission_runner.py`.)
- [x] **Sim tier (the CI-able one):** scripted colored-sphere spawn/move in the Gazebo
      world at a key mission moment (`gz service` spawn or a world plugin) so Mission 2
      runs fully unattended. Prove Tier-1 PASS → HIL PASS → then add to `stage-4-hil`,
      only after the Piece-1 3×-green gate with Mission 1.
      **(2026-07-18: implemented — harness-owned, DETERMINISTIC placement, not seeded.**
      Design pivot 2026-07-17 (Mike): `tools/mission2_harness.py` places the ball at a
      fixed spot beside the green sphere (`BALL_AT_SPHERE_XY` = (0.3, 3.7)) instead of the
      seeded-random placement this bullet and the spec originally described. Seeded fuzzing
      returns in Session 19, constrained to an area-of-interest — placement bounds are
      spec, not a tuning knob. Per-color triggers as shipped: red 1.3 m → photo + stop;
      yellow 0.8 m → photo + return home.)
      **(2026-07-18: all three HIL rungs now in `stage-4-hil` — Task 11 rung 1 (nominal,
      no ball) + Task 12 rung 2 (yellow, photo_then_home) + rung 3 (red, photo_then_stop).
      HIL sequence: mission1 → nominal → reset-home (drive-home janitor) → yellow → red
      (red last, robot stays mid-room). Ground truth for the react judges comes from a
      workstation poller — the Jetson has no Gazebo, so its reaction log reads "at None";
      the poller's closest-approach point is the reaction point. Both react rungs
      LIVE-PROVEN on the real Jetson 2026-07-18: yellow reaction @0.64 m returned home,
      red reaction @1.31 m stayed stationary, both judge PASS. draft PR #4.)
- [ ] **Real-camera tier (manual by design — stays OUT of CI):** USB UVC webcam on the
      Jetson via `ros-jazzy-v4l2-camera` (or `usb_cam`), publishing on its **own topic —
      do NOT reuse `/robot_001/camera/image_raw`**, the Gazebo bridge owns that in sim;
      remap the detector's input to the real camera instead. Procedure: run Mission 2 HIL,
      Mike presents red/yellow croquet balls to the camera at key moments → observe robot
      stop / re-route. Deliverables: the calibrated `hsv_realcam.yaml` profile + observed
      detection latency, both of which Session 18 (real robot) consumes directly.
      **Bill of materials: one UVC USB webcam.**
      **(2026-07-18: deferred** — to the webcam follow-up plan, per spec §9. Not in scope
      for this Plan B.)
- [ ] **Pin the real camera's auto-exposure and auto-white-balance before calibrating.**
      Consumer webcams continuously shift exposure and color temperature, which moves a
      croquet ball's hue frame to frame — HSV thresholding against floating white balance
      is chasing a moving target. Disable/fix via `v4l2-ctl` controls (e.g.
      `white_balance_automatic=0`, fixed `exposure_*`; exact control names vary — check
      `v4l2-ctl -d /dev/video0 --list-ctrls`) and **record the pinned settings alongside
      `hsv_realcam.yaml`** — the calibration is only valid for that camera configuration.
      **(2026-07-18: deferred** — to the webcam follow-up plan, per spec §9. Not in scope
      for this Plan B.)
- [ ] **Decide the clock-domain handling for real-camera frames in HIL (wall clock vs sim
      time).** The HIL stack runs on Gazebo sim time (`use_sim_time`), but a real webcam
      stamps frames with wall clock. This breaks two planned mechanisms: the
      `take_picture` freshness gate (wall-clock stamp vs sim-time "now" is meaningless)
      and the yellow-ball keepout (a stamped detection must transform into the map frame
      via TF — wall-clock stamps against a sim-time TF buffer fail or grab garbage). The
      red-ball stop is immune (binary trigger, no stamp needed). Decide deliberately —
      e.g. detector re-stamps detections with its own node clock, or the real-camera tier
      treats detections as stampless triggers only (stop yes, keepout sim-tier-only) —
      don't discover it live mid-run.
      **(2026-07-18: deferred** — to the webcam follow-up plan, per spec §9. Not in scope
      for this Plan B.)

> **Webcam follow-up plan (deferred, spec §9) — its own future scope, NOT Plan B.**
> The three real-camera bullets above (UVC webcam tier, auto-exposure/white-balance pin,
> and the wall-clock-vs-sim-time clock-domain decision) are consolidated here as one
> deferred deliverable: swap the sim camera for a real UVC webcam on the Jetson, publishing
> on its own topic (never `/robot_001/camera/image_raw`, which the Gazebo bridge owns),
> remap the detector's input, and run Mission 2 HIL with Mike presenting red/yellow croquet
> balls by hand. Outputs Session 18 (real robot) consumes: a calibrated `hsv_realcam.yaml`
> + pinned camera settings + observed detection latency. **Bill of materials: one UVC USB
> webcam.** Explicitly out of CI (manual by design) and out of the Mission 2 Plan B closed
> here — the CI/HIL tiers use the sim camera. Written up so it isn't lost, not scheduled.

### Piece 3 — E2E fixes that protect the new stage (kept from the old tidy-up list)

> Everything else from the old "Tidy Up E2E Simulation" list moved to **Session 17**.
> These four stay because they guard this session's own deliverables.

- [ ] FAIL-row metric skew: failed/timed-out navigate durations currently feed
      `mean_time_to_goal` — decide how FAIL rows enter drift analysis **before
      `stage-4-hil` starts generating rows on every push** (it will produce FAILs
      eventually; the policy must exist first).
- [ ] Move `MissionRunner()` construction inside `main()`'s try (constructor crash
      currently skips the FAIL telemetry row — the CI stage depends on that row existing).
- [ ] **Review Mission 1's return-leg clearance at the outer hallway arch** — now also a
      flaky-CI-stage risk, not just cosmetics. Mike observed (2026-07-12, GUI viewing
      session) the robot appearing to clip/bang the hallway door/corner on the
      doorway→home_base leg. Not captured by telemetry: the mission CLI logs nav metrics
      but does NOT run the MetricsCollector collision check (that's only in
      `tests/test_navigation.py` BR-02, which watches a different leg). To investigate:
      re-run Mission 1 with the GUI up and the metrics collector alongside; check RPP's
      `use_collision_detection: false` + inflation radius vs the arch corner; consider a
      collision assertion on mission runs. May be visual-only (wheel near-miss at 3× RTF)
      — needs eyes + data before touching params.
- [ ] Add `tests/test_mission_run.py` to `stage-2-gazebo` — a single pytest invocation
      with `test_navigation.py` works as of 2026-07-12 (shared guarded rclpy fixture in
      conftest).

### Session Complete When
- [ ] `stage-4-hil` green on a real code push, 3× consecutively **with Mission 1**, with
      `stage-4-isaac` retired in the same change and `stage-5-reports-hw` running off the
      new stage
- [ ] Mission 2 (camera-reactive) PASS at Tier-1 and HIL with the sim camera, then added
      to `stage-4-hil`
- [ ] Real-camera tier executed end-to-end at least once (croquet-ball stop + avoid both
      observed), `hsv_realcam.yaml` committed
- [ ] Power modes set explicitly per CI job and recorded in telemetry rows
- [ ] `docs/runbooks/Mission1HILSession15.md` updated to note the CI stage exists (manual
      procedure remains as the debugging path)
- [ ] Every Piece 3 item closed or explicitly re-deferred with a written reason

> **STOPPED 2026-07-17 (Mike) — mid-plan, pickup point.** Tasks 1–9 of the Mission 2
> plan are complete on branch `mission2-camera-reactive` (Task 9 ended with the
> deterministic-placement pivot + observed GUI runs; per-color triggers red 1.3 m /
> yellow 0.8 m; shadows off). Branch pushed; **draft PR #4** open; **full CI green
> first try incl. stage-4 HIL on the Jetson** (run 29626889652). **REMAINING to close
> Session 16:** Task 10 (wire `tests/test_mission2.py` into stage-2), Tasks 11–12
> (Mission 2 HIL rungs: ignorable → red → yellow), final whole-branch review (include
> the per-task carry-forward findings ledger), un-draft + merge PR #4. Authoritative
> resume state: `.superpowers/sdd/progress.md`.

---

## Session 17 — Harden, Stabilize & Review (pre-robot gate)

> **Created 2026-07-12 (evening restructure)** — split out of Session 16 so *building*
> (16) and *hardening/reviewing* (17) don't share a session; absorbed the review-flavored
> items from 16's old tidy-up list plus the drift/reports/AI review. Prior Session 17
> (Real Robot) → 18; prior 18+ → 19+.
>
> **Refreshed 2026-07-17 (planning session with Mike, from MikesNotes.md):** new Piece 1
> (Onboarding & ease of use — the "stranger onboards" test), docs pass + second review
> round added to the code-review piece, Python logging framework + debug modes added to
> logging, real-robot report parity added to reporting, Session 16 observed-run findings
> folded in as concrete carry-ins. Pieces renumbered 1–6 (Onboarding first).

**Purpose:** harden, stabilize, and where sensible speed up the whole pipeline, then
answer one question with evidence: **"Have we done everything we can to make the robot
good to go right out of the gate?"** Session 18 puts the Jetson in a chassis in the real
world — after that, every bug costs a hardware session to find and a room to walk to.
This is the last cheap chance to find them at a desk.

### Piece 1 — Onboarding & ease of use (the "stranger onboards" test)

> Frame: a competent ROS2 developer who has never seen this repo clones it today. Can
> they install, run a sim mission, and understand what they're looking at from README.md
> alone — without archaeology through session docs?

- [ ] Walk the onboarding path yourself, literally: fresh clone in a scratch directory,
      follow README.md verbatim, note every point where it lies, omits, or assumes
      tribal knowledge. Fix the README (or the code) at each.
- [ ] "Kick off a run" ergonomics: is there ONE documented command each for (a) unit
      tests, (b) a full local sim mission, (c) the dashboard? If any needs a paragraph
      of caveats, wrap it in a script/make target instead.
- [ ] **Future-proofing review (audit only, no implementation):** could a user *configure*
      a mission? a world? add to a world? change or add robots? Much of this is
      deliberately not implemented in R1 — the check is that R1 decisions don't make it
      HARDER later (hardcoded robot_001 strings, missions only as Python literals,
      worlds only as hand-edited SDF). Write the gaps down; placement decisions belong
      to Session 20. Feeds the long-term "world request / mission request" pipeline
      vision (BLUEPRINT / 10x blueprint).
- [ ] Terminology glossary in BLUEPRINT.md — we are inconsistent across *sessions,
      pieces, tasks, steps, stages, todos* (Mike, 2026-07-17). Define the hierarchy once
      (proposal: **Session** = one work sitting → contains **Pieces** = thematic chunks →
      containing **Tasks** = checkboxes; **Stage** = CI pipeline jobs ONLY; retire
      "steps"/"todos" in docs), then sweep the docs to match.

### Piece 2 — Full code review + performance + reuse

- [ ] Whole-repo code review (`/code-review` at high effort, or `/code-review ultra` for
      the multi-agent cloud pass). Triage every finding: fix now / defer with reason /
      reject with reason — no silent drops.
- [ ] Performance pass: mission wall time, Nav2 CPU/RAM on the Jetson at the HIL power
      mode, CI stage wall times (are Session 16's cache fixes holding?), report/dashboard
      generation time as `fleet_runs.db` grows.
- [ ] Code-reuse pass: `NavRunner` vs `mission_runner` overlap, telemetry write paths,
      launch-file duplication (`sim_launch` vs the `sim_only`/`nav2_only` split) — fold
      duplicates rather than letting three variants drift apart.
- [ ] Delete dead code found along the way — starting with the `headless` launch arg
      (moved here from Session 16: wire it to `gz sim` or delete it in both
      `sim_launch.py` and `sim_only_launch.py`).
- [ ] Docs pass (Mike 2026-07-17): review all docs, consolidate overlapping ones, delete
      stale ones. Includes applying the Piece 1 terminology glossary, and writing the
      **Cosmos / world-foundation-models positioning paragraph** into BLUEPRINT.md
      ("the testbed for the Cosmos era" — S20 decision 2026-07-17; angles in the
      session-17-inputs memory).
- [ ] **Second review round with a different model** after the first round's fixes land
      (Mike 2026-07-17) — fresh eyes, different blind spots; `/code-review` or ultra.
- [ ] **Carry-ins from Session 16's observed runs (2026-07-17):**
      - Green-photo content verification: add a *green* HSV band to the detector config
        and make the nominal-variant judge assert the sphere photo actually CONTAINS
        green pixels (found live: the "photograph the sphere" photo captured the bed —
        sphere below camera FOV at the 0.5 m standoff + `rotate_to_heading_min_angle`
        0.3 rad lets the final heading point ~17° off; judge only checked existence).
      - `sphere_approach` dresser clearance: robot's stop leaves <10 cm edge clearance
        to the dresser and the nominal goal tolerance can't catch it — nudge the goal,
        add a clearance judge, or accept-with-reason.
      - Final-review triage of the accumulated per-task Minor findings + tonight's
        deterministic-pivot record in `.superpowers/sdd/progress.md` (this may fold
        into finishing Session 16's branch instead — whichever comes first).

### Piece 3 — Logging: can we debug the robot from the workstation?

> Design question for every item: a mission fails on the real robot in another room —
> can you determine **why**, from the workstation, after the fact, without re-running it?

- [ ] Inventory what actually persists per run today (one telemetry row, photos, whatever
      scrolled past in launch terminals) and write down the post-mortem gaps.
- [ ] Mission runner logs to a file on-device (not just stdout): per-step timestamps,
      goal sent, result/error, durations — retrievable over SSH after the fact.
- [ ] Nav2/ROS log retention + retrieval: where do they land (ROS log dir / journald once
      Session 19+'s systemd units exist), how long are they kept, one documented command
      to pull them back to the workstation.
- [ ] **rosbag-on-failure:** rolling record of the key topics (`cmd_vel`, `scan`,
      `amcl_pose`, goal status), persist the last N seconds when a mission step fails.
      NVMe makes sustained recording fine (the SD-hygiene constraint died with runbook
      Part 9).
- [ ] Failure taxonomy in telemetry: FAIL rows should say *what kind* of failure — nav
      timeout, goal rejected, no camera frame, detector timeout, crash — one enum column,
      so reports can answer "why", not just "failed".
- [ ] **Python `logging` framework with a debug switch** (Mike 2026-07-17): tools and
      nodes currently print; move to `logging` with per-module loggers, a single
      documented way to flip debug verbosity on the workstation AND on the robot
      (env var or launch arg), file handlers where Piece items above need persistence.

### Piece 4 — Reporting & user-friendliness

> Frame: could a less-technical reader (or future-you, six months out) answer "did last
> night's runs pass, and if not, why?" in under a minute, without writing SQL?

- [ ] Review `generate_test_report.py` output and every dashboard tab against that frame;
      fix what fails it.
- [ ] One-command status after a run — e.g. `python -m tools.fleet_status` (or promote
      the report's summary page to this): last N runs, PASS/FAIL, drift flags, plain
      language.
- [ ] Photos surfaced next to their runs (dashboard or report), not just files in a
      directory.
- [ ] Drift alerts readable by a human: "mean_position_error is 3.2σ above baseline
      (0.19 m vs 0.06 m typical)" beats a bare sigma number.
- [ ] **Real-robot report parity** (Mike 2026-07-17): confirm reports/dashboard work as
      well for `hil_jetson`/real rows as for sim rows — same one-minute answerability
      for "did last night's REAL runs pass, and why not?"
- [ ] **Fair-weather reporting fix** (Mike 2026-07-18, run 29653564095 finding): the
      pipeline loses failure data twice — (a) `stage-5-reports-hw` has `needs:` with no
      `if:` so it SKIPS when stage-4 FAILS (add `if: ${{ !cancelled() }}`; upstream-
      skipped on docs-only pushes stays a correct skip); (b) the HIL row-ship step lives
      in a phase that never runs after a failed gate — move it to the always-run
      teardown/evidence path so FAIL rows reach the drift DB; (c) report/dashboard must
      render failed runs prominently. Failure telemetry is the highest-value data for
      drift + R2 test/heal — today it's filtered out exactly when it matters.

### Piece 5 — Drift detection, reports & AI loop review

> State today, recorded for review honesty: `baseline_monitor` = sigma-vs-rolling-baseline
> over `fleet_runs.db`, thresholds as data in `config/drift_config.yaml`; `agentic_loop` =
> Claude proposes a nav2-param / harder-world / mission-plan change from the latest run +
> the real drift report, human-approved; `ai_test_generator` = Claude proposes test
> scenarios from run history. **There is no RAG anywhere — context is direct SQL queries
> injected into the prompt, which at this data scale is simpler and better than RAG.
> Keep it that way and record it as a decision, so nobody "adds RAG" for its own sake.**

- [ ] Verify the FAIL-row policy (decided in Session 16 Piece 3) actually holds across
      `baseline_monitor`, dashboard, and report — no skew regression.
- [ ] Baseline windows/thresholds sanity pass now that the DB mixes `local` and
      `hil_jetson` rows and (post-Session 16) power modes — confirm slicing prevents
      apples-vs-oranges drift alarms.
- [ ] **Feed the real `nav2_params.yaml` into `agentic_loop`'s `diagnose()` prompt**
      (pulled forward from Session 19+ — the known gap: Claude *infers* `current_value`
      and was verified wrong once, claiming 0.55 for `inflation_radius` when the real
      value is 0.25). Must be fixed before the loop ever runs against real-robot data.
- [ ] `ai_test_generator`: is it earning its keep? Run it against the accumulated DB;
      keep, fix, or park it with a written reason.

### Piece 6 — Repo hygiene (candidate, time permitting)

- [ ] The pre-public cleanup pass (repo is private; personal/career context in docs is
      fine today but needs a sweep before any public flip) — this session is a natural
      slot since the repo gets read end-to-end anyway. Includes deciding the
      `reports/photos/` tracking policy (currently untracked in the workstation repo).
- [ ] **Image/disk purge strategy** (Mike 2026-07-18): CI pushes a uniquely-tagged arm64
      image per build to GHCR (accumulates forever) + docker layer caches grow on BOTH
      hosts. Keep-last-N GHCR tags (retention policy or cleanup job) + scheduled selective
      prune on workstation and Jetson — must SPARE the registry-cache layers stage-3's
      warm 150 s builds depend on (a naive `prune -a` costs us ~8 min/build).
- [ ] **Stage-tiered mission matrix, remaining half** (Mike 2026-07-18): stage-4 already
      runs ONLY the deployment mission (shipped in Session 16 Task 13); finish the design
      by making "current/deployment mission" a DECLARED pipeline input (env/profile
      config, not hardcode) — deliberately the first seed of R3 input-ization — and
      center stage-5 reports on that mission with regression results summarized.

### Piece 7 — Demo prep (Mike, 2026-07-18)

> Frame: the R1 demo video films the Mission 2 day. Anything the film needs that the
> robot does NOT need to wait for gets built in sim NOW — don't stack demo polish into
> robot week.

- [ ] **Kill the inter-run dead air** (observed in the 2026-07-18 narrated GUI day): the
      gaps between runs are serial bookkeeping — judging, photo scp, telemetry, next
      mission-process startup. Overlap the bookkeeping with the next run's startup (keep
      verdict print ORDER stable) so the filmed sequence flows run-to-run without a
      visible "nothing is happening" stretch. Sim-testable now; robot day inherits it.

### Session Complete When
- [ ] The gate question — **"have we done everything we can so the robot is good to go
      right out of the gate?"** — answered *yes, in writing* (short section in
      BLUEPRINT.md), with every Piece's findings fixed or explicitly deferred with a
      reason
- [ ] No known silent-failure paths: every failure mode found in review either surfaces
      in telemetry/logs or is documented as a known gap

---

## Session 18 — Real Robot: Deploy + Sim-to-Real Comparison (~3 hrs)

> **Renumbered from Session 16 on 2026-07-12, then from 17 to 18 later the same day**
> (first a new Session 16 — HIL CI stage — was inserted ahead of it; then the evening
> restructure inserted Session 17 — Harden, Stabilize & Review; see above).

### Recommended Reading
- [SLAM Toolbox online async](https://github.com/SteveMacenski/slam_toolbox#readme) — for building the real-room map
- [Nav2 map server](https://docs.nav2.org/configuration/packages/configuring-map-server.html) — serving the saved SLAM map
- [teleop_twist_keyboard](https://index.ros.org/p/teleop_twist_keyboard/) — driving the robot during SLAM mapping

> **Session reviewed against actual code 2026-07-06** — see corrections inline: the
> sim-to-real comparison step didn't actually log telemetry (called `NavRunner.send_goal()`
> directly instead of the pytest fixture Session 12 wired it into) and sent a goal that
> doesn't match this project's real BR-01 goal; the CI smoke test used a `ros2 topic hz`
> flag that doesn't exist; and a dangling reference to a BLUEPRINT.md section that was
> never written. **Not resolved — needs your decision, not silently fixed:**
> `sim_vs_real_comparison.py` expects two separate DB files (`FLEET_SIM_DB`/`FLEET_REAL_DB`)
> but Session 12 built `sim_engine` specifically so one DB could hold gazebo/isaac/real rows
> together — these two pieces disagree on the architecture and someone needs to pick one
> before this step can run for real.
>
> **Hardware dependency:** Requires Jetson module transferred to the UGV-PT carrier board
> (or a second Jetson module purchased). The Jetson from Session 14 can be transferred;
> buy a second module if you want to keep the Dev Kit as the CI runner.
>
> **Purchase decision (researched 2026-07-13):** the robot is the **Waveshare UGV Rover PT
> Jetson Orin ROS2 Kit, ACCE variant — SKU 29227, $539.99 direct**:
> <https://www.waveshare.com/ugv-rover-pt-jetson-orin-ros2-kit.htm?sku=29227>
> - **Must be the ROS2 Kit, not the "AI Kit"** — only the ROS2 Kit includes the **D500
>   lidar + OAK-D-Lite depth camera** (no lidar = no `/scan` = no Nav2). The cheaper AI-Kit
>   ACCE (SKU 27772) looks like a deal precisely because those sensors are missing.
> - **ACCE = bring your own Jetson "module including its baseboard"** — SKU 29224 is the
>   same kit + a Jetson Orin Nano **4GB** for $976.99; pointless given our 8GB Super.
> - Amazon equivalent [B0DM4KBWT7](https://www.amazon.com/dp/B0DM4KBWT7) runs ~$140 more
>   than Waveshare direct — Prime shipping/returns is all you'd be buying.
> - **⚠️ Unverified before ordering: whether the official Orin Nano Dev Kit (with stock
>   fan, 103×90.5×34.8 mm) fits the Jetson bay.** The Jetson mounts in an ENCLOSED bay
>   under the top deck (only the port edge is exposed at the rear), and Waveshare's bundled
>   option is a bare 4GB SoM + their low-profile base board — the bay may be too shallow
>   for the dev-kit fan stack. **The official ACCE assembly video answers this — watch
>   before ordering: <https://www.youtube.com/watch?v=R0-QG33DznY>** (linked from the
>   [product wiki](https://www.waveshare.com/wiki/UGV_Rover_Jetson_Orin_ROS2) as the
>   assembly tutorial; explicitly covers the ACCE Jetson/OAK/lidar install). Fallback if
>   the dev kit doesn't fit: Waveshare's Orin Nano/NX Base Board (low-profile, has M.2) —
>   module + NVMe transfer, install boots unchanged (QSPI firmware lives on the module).
> - **Add 3× 18650 lithium cells to the order** (2200 mAh+, 4C discharge) — not included,
>   robot won't run without them. Chassis has built-in active cooling + external wifi
>   antennas (SSH-over-wifi per Prerequisites works inside the aluminum body).
>
> **Sim-vs-real fidelity deltas (recorded 2026-07-13, feeds the URDF/tuning steps below):**
> the real rover is **6-wheel 4WD skid-steer** vs our 4-wheel diff-drive sim URDF —
> kinematically equivalent at the `cmd_vel` level (nothing above the driver layer changes),
> but expect (1) more rotation-scrub odometry error than sim showed, (2) the **camera on a
> 2-axis pan-tilt** vs sim's body-fixed camera — decide consciously: simplest is commanding
> the gimbal to a fixed forward/level pose so take_picture's camera-heading==robot-yaw
> assumption holds, (3) the **lidar mounted low/front on the deck** (sim: top-mounted,
> clean 360°) — the pan-tilt tower sits inside the real scan's rear sector, so add a scan
> FOV mask before the costmap sees phantom obstacles, and the low mount sees bed legs, not
> mattresses (fine — this session builds its own SLAM map).
>
> **Open decision for this session — brain from container or bare (raised 2026-07-14):**
> CI compiles/tests via Docker either way (stage-3 image; stage-4-hil phase 2 runs the
> mission inside it). For the rover: **leaning containerized brain + bare vendor driver**,
> talking over DDS on the host network. Container pros: the deployed artifact is
> bit-identical to what stage-4-hil tested (the project's core thesis), SHA-tagged rollback,
> host OS stays clean, fleet-scale story. Bare pros: simpler `/dev` access (motor serial,
> D500 lidar, OAK-D — container needs explicit `--device` passthroughs), simpler on-robot
> debugging, no nvidia-container-runtime complexity if GPU inference ever lands. Session 16
> phase 2 is the deliberate de-risk of the container path before the rover exists; decide
> here with that evidence in hand.
>
> **Waveshare UGV-PT dimensions note (carry-over from Session 10):** Before running real
> nav missions, measure the actual robot and update `urdf/ugv_pt.urdf.xacro` to match:
> body dimensions, wheel_radius, wheel_separation. Reference:
> [UGV Rover PT product page](https://www.waveshare.com/ugv-rover-pt-jetson-orin-ros2-kit.htm)
> (the plan's old `ugv-pt.htm` link now redirects into marketing; the
> [wiki](https://www.waveshare.com/wiki/UGV_Rover_Jetson_Orin_ROS2) has the spec detail).
>
> **Same code, same topics — but expect a param-tuning pass (2026-07-03):** "the brain code
> doesn't change" is true for *code*, not *parameters*. `nav2_params.yaml` was tuned against
> sim physics; real wheel slip, lidar noise, and motor response will likely need RPP
> speed/accel and costmap adjustments. Budget time for this and don't treat a first-run nav
> failure as a code bug — walk the systematic-debugging path: drivers verified → TF tree
> clean → localization converged → then look at nav params.

### Prerequisites
- Sessions 10–14 complete
- Jetson Orin Nano transferred to / installed in Waveshare UGV-PT
- Robot powered on, accessible via SSH over WiFi or Ethernet
- Real bedroom clear enough to drive the robot safely for SLAM mapping

### Steps

- [ ] **Bring up the hardware driver layer FIRST (gap identified 2026-07-03)** — nothing
  earlier in the plan provides `/robot_001/cmd_vel → wheels`, wheel odometry, or
  `/robot_001/scan` on real hardware; every step below silently assumes they exist. The
  UGV-PT's motor board is an ESP32 speaking JSON-over-serial to the Jetson.
  - Evaluate Waveshare's `ugv_ws` ROS2 workspace (github.com/waveshareteam) before writing
    anything — it may cover base driver + lidar out of the box.
  - Only if it doesn't fit: write a thin driver node (cmd_vel → serial commands;
    serial feedback → `/robot_001/odom` + odom TF; lidar driver → `/robot_001/scan`).
    Remember the TF architecture rules from CLAUDE.md: unprefixed frame names, `/robot_001/`
    topic namespace.
  - **Verify before proceeding:** `ros2 topic hz /robot_001/odom` and `/robot_001/scan`
    both report, and teleop_twist_keyboard physically drives the wheels.

- [ ] **Build a real-room SLAM map** — drive the robot around the room once while
  SLAM Toolbox records the map:

  ```bash
  # Terminal 1 — on the Jetson (SSH):
  source /opt/ros/jazzy/setup.bash
  ros2 launch slam_toolbox online_async_launch.py use_sim_time:=false

  # Terminal 2 — on workstation (teleop):
  source /opt/ros/jazzy/setup.bash
  ros2 run teleop_twist_keyboard teleop_twist_keyboard \
    --ros-args -r /cmd_vel:=/robot_001/cmd_vel
  # Drive the robot slowly around the room perimeter + past furniture

  # Terminal 3 — on workstation, save the map when coverage looks good:
  ros2 run nav2_map_server map_saver_cli -f src/nav_fleet/maps/bedroom_real
  # Creates: maps/bedroom_real.pgm + maps/bedroom_real.yaml
  ```

- [ ] **Create `src/nav_fleet/launch/robot_launch.py`** — launches Nav2 on the real robot
  (no Gazebo, no bridge — real sensors only):

  ```python
  # Copyright 2026 Mike. Licensed under Apache 2.0.
  """Launch Nav2 on the real ugv_pt robot (Jetson, no simulation)."""
  import os
  from pathlib import Path
  from launch import LaunchDescription
  from launch.actions import IncludeLaunchDescription
  from launch.launch_description_sources import PythonLaunchDescriptionSource
  from launch_ros.actions import Node
  from ament_index_python.packages import get_package_share_directory

  def generate_launch_description():
      pkg = Path(__file__).parent.parent
      nav2_params = str(pkg / 'config' / 'nav2_params.yaml')
      map_yaml = str(pkg / 'maps' / 'bedroom_real.yaml')
      pkg_nav2 = get_package_share_directory('nav2_bringup')

      return LaunchDescription([
          IncludeLaunchDescription(
              PythonLaunchDescriptionSource(
                  os.path.join(pkg_nav2, 'launch', 'bringup_launch.py')
              ),
              launch_arguments={
                  'use_sim_time': 'false',
                  'params_file': nav2_params,
                  'map': map_yaml,
                  'namespace': 'robot_001',
              }.items(),
          ),
      ])
  ```

- [ ] **Write the Stage 6 CI job** — SSH deploy + smoke test + auto-rollback on failure.
  Add to `ci.yml` (runs on a schedule or `workflow_dispatch`, not every push):

  ```yaml
  real-robot-deploy:
    runs-on: ubuntu-latest
    needs: stage-5-reports
    if: github.event_name == 'workflow_dispatch'
    steps:
      - uses: actions/checkout@v4
      - name: Deploy to robot via SSH
        uses: appleboy/ssh-action@v1.0.3
        with:
          host: ${{ secrets.ROBOT_IP }}
          username: mike
          key: ${{ secrets.ROBOT_SSH_KEY }}
          script: |
            cd ~/autonomous-fleet-testbed
            git pull origin main
            source /opt/ros/jazzy/setup.bash
            colcon build --symlink-install
            source install/setup.bash
            # Smoke test: launch Nav2 and check topics
            ros2 launch nav_fleet robot_launch.py &
            sleep 15
            # `ros2 topic hz` has no --once flag — it runs until killed, printing
            # "average rate: X" periodically. Bound it with timeout instead.
            timeout 3 ros2 topic hz /robot_001/odom | grep -q "average rate" || exit 1
            timeout 3 ros2 topic hz /robot_001/scan | grep -q "average rate" || exit 1
            echo "Smoke test passed"
  ```

  > **Gotcha — SSH secrets:** `ROBOT_IP` and `ROBOT_SSH_KEY` must be set in
  > GitHub → Settings → Secrets. Generate a dedicated key pair for the robot:
  > `ssh-keygen -t ed25519 -f ~/.ssh/robot_deploy_key` on the workstation, then
  > `ssh-copy-id -i ~/.ssh/robot_deploy_key mike@<robot-ip>`.

- [ ] **Run sim-to-real comparison** — reuse `tests/test_navigation.py` rather than
  calling `NavRunner` directly: `NavRunner.send_goal()` alone doesn't write to the DB —
  Session 12 wired `log_run()` into the pytest session fixture, not into `NavRunner`
  itself — and the test file's hardcoded goal (0.0, 3.7) is the actual, real BR-01 goal
  used everywhere else in this project (an ad-hoc script sending an arbitrary different
  point wouldn't be comparing the same mission at all). Reusing the same file is also
  exactly the pattern `stage-3-gazebo`/`stage-4-isaac` already use — same test, different
  backend — so this is the third leg of that same design, not a new mechanism:
  ```bash
  # On robot (SSH): ros2 launch nav_fleet robot_launch.py
  # On workstation:
  FLEET_DB=reports/fleet_runs.db SIM_ENGINE=real python -m pytest tests/test_navigation.py -v --timeout=120
  # Logs one row with sim_engine='real' to the same FLEET_DB gazebo/isaac rows live in
  # (single SQLite store — see Session 12's 2026-07-03 review note) — ASSUMING the
  # sim_vs_real_comparison.py architecture question above has been resolved first.

  # Compare:
  python tools/sim_vs_real_comparison.py
  # Reports: correlation between sim and real nav_success_rate, mean_position_error
  # Target: correlation >= 70%
  ```
  > **Double-check before starting:** the SLAM map's coordinate frame is whatever
  > `bedroom_real.yaml` ends up being zeroed to when mapping starts — it has no reason to
  > line up with the Gazebo/Isaac world's coordinate origin. Sending literally `(0.0, 3.7)`
  > may not land anywhere near the real bedroom's floor centre. After building the real
  > map, confirm (or update) the goal `test_navigation_succeeds` sends actually corresponds
  > to the same physical location in the real world — may need a per-`sim_engine` goal
  > override rather than one hardcoded literal.

- [ ] **Tag r1-complete** if sim-to-real correlation >= 70%:
  ```bash
  git tag r1-complete
  git push origin r1-complete
  ```
  If correlation < 70%: tune `nav2_params.yaml`, fix URDF dimensions, or accept the gap
  with documentation. (The plan previously pointed here to a BLUEPRINT.md "Kill Criteria"
  section — checked, it doesn't exist. Removed the dangling reference; these three options
  are the actual guidance.)

- [ ] **Commit**:
  ```bash
  git add .
  git commit -m "feat(session-15): real robot deploy, SLAM map, sim-to-real comparison, r1-complete"
  git push
  ```

### Session Complete When
- `bedroom_real.pgm` + `bedroom_real.yaml` saved and committed
- `robot_launch.py` launches Nav2 on the real robot successfully
- Real robot navigates to the confirmed real-world equivalent of the bedroom goal (see
  "Double-check before starting" above — may not be the literal `(0.0, 3.7)`) without collision
- `sim_vs_real_comparison.py` reports correlation >= 70%
- `git tag r1-complete` pushed

---

## Session 19 — Real-Robot Expansion & Deferred Capability (pick-list)

> **Renumbered 17+→18+ on 2026-07-12, then 18+→19+ the same evening. Rewritten
> 2026-07-17 (planning session with Mike, from MikesNotes.md):** this is now a MENU,
> not a commitment — pick items by how much time remains before/around the robot's
> arrival (~2026-07-31); any or all can be pushed to future releases via Session 20.
> Ordering principle: **what most de-risks robot day, soonest, with hardware already
> in hand** — items 1–4 are doable pre-chassis, item 5 is anytime, item 6 is
> post-Session-18 by definition.

**1. Real-camera tier (webcam → Jetson; HIGHEST value, doable today).** The biggest
sim-to-real unknown in Mission 2: HSV bands were tuned on rendered pixels; real
lighting/hue is where they break. Plug the webcam into the Jetson, run ball_detector
against the real croquet balls (hue and lighting factors — Mike's note), measure a real
`hsv_realcam.yaml` + real `range_k` with the Session 16 calibration tool. (Matches the
Mission 2 spec's deferred "webcam manual tier".)

**2. WiFi module bring-up (small, hardware in hand).** Install/enable the Jetson's WiFi
module, verify DDS discovery + topics over WiFi (the untethered link everything later
depends on). Quick win; do early.

**3. Physical test protocol code (code now, validate on robot day).** Operator-paced
harness prompts ("place red ball on the marked spot, press enter" — Mike is the
actuator, never timed); taped-X conventions for home base (place robot, face marked
heading, THEN power on) and the ball spot beside the sphere position; **boot-mode
switch** — autonomous mode (boot → localize → run configured mission, zero network) vs
testbed mode (boot → localize → idle, await harness), designed 2026-07-17; systemd
autostart per "Going untethered" below.

**4. Deferred Nav2 capability ladder (sim work, time-boxed pieces).** See "Deferred
Nav2 capability" below — kept verbatim, its methodology is hard-won. Order: AMCL
stuck-near-furniture regression → collision_monitor (cmd_vel self-lock aware) →
footprint-aware planning → recovery behaviors last (root-cause the CostmapSubscriber
bug first). Note: recovery is also the BR-03 traceability gap — finishing even one rung
retires the CI `continue-on-error` wart.

**5. Mission evolution (valuable, not robot-blocking).** Area-of-interest concept (the
bedroom zone between bed↔dresser and PC↔wall as "area to clean/detect");
"ignore red/yellow if not in your path / area of interest" behavior (Mike 2026-07-17);
seeded placement fuzzing RETURNS here, constrained to the AOI — placement bounds are
spec, not tuning knobs (lesson of 2026-07-17: the fuzzer was quietly tuned into
determinism to chase green). Possible new mission.

**6. Agentic loop on real telemetry (inherently last — needs Session 18 data).**
- ~~Feed the real `nav2_params.yaml` into `diagnose()`'s prompt (gap found 2026-07-06)~~
  — **pulled forward into Session 17 Piece 5 (2026-07-12)**; Claude inferred a wrong
  `current_value` once already (claimed 0.55 for `inflation_radius`; real value 0.25).
- Run `tools/agentic_loop.py` against real run reports (`sim_engine: 'real'`)
- Claude compares real vs sim metrics, identifies sim fidelity gaps, proposes sim
  parameter updates to close the gap
- Advanced mission types: natural language mission → Claude generates goal sequence →
  robot executes → results fed back to Claude for next iteration
- Log real-world navigation videos + telemetry for portfolio/demo

### Going untethered — systemd autostart (decision 2026-07-03: deferred out of R1)

r1-complete is achievable entirely over SSH (Session 18's smoke test, nav goal, and
sim-to-real comparison all run remotely). True autonomy — flip the power switch, robot boots
into nav with no monitor/keyboard/SSH — is this item:

- systemd units on the Jetson: one for the base+lidar driver bringup (Session 18's driver
  layer), one for `robot_launch.py` (Nav2). Order them with `After=`/`Requires=` (drivers
  before Nav2); restart policy `on-failure`.
- **Non-interactive shell gotcha** (same one as the Session 10 runner service): systemd units
  don't read `.bashrc` — source ROS2 + workspace overlay explicitly in an `ExecStart` wrapper
  script.
- Acceptance test: power-cycle the robot headless; it localizes and accepts a
  `navigate_to_pose` goal sent from the workstation.

### Deferred Nav2 capability (from Session 11/12 Isaac debugging)

Session 11/12's Isaac Sim nav test was stripped down to a minimal, hand-rolled Nav2 stack
(modeled on the proven-working `BC/isaac_project` reference) after ~20 debugging iterations on
the full stack (AMCL + SmacPlannerHybrid + collision_monitor + recovery behaviors, layered on
all at once with no working baseline underneath). **Result: BR-01 passes green** —
`nav2_isaac_launch.py` now runs `robot_state_publisher`, a static `map→odom` TF, `map_server`,
`controller_server` (RPP + `NavfnPlanner`, plain `robot_radius: 0.24`), `planner_server`,
`bt_navigator` (minimal one-shot `navigate_simple.xml`, no periodic replanning, no recovery
dependency), and two lifecycle managers — nothing else. This deliberately defers capability the
fleet needs before Session 19 is for real — captured here so it doesn't quietly get forgotten:

> **Methodology for re-adding these (2026-07-06 review):** the root cause of the ~20-iteration
> debugging saga wasn't fundamental Isaac Sim fragility — it was re-enabling AMCL,
> `SmacPlannerHybrid`, `collision_monitor`, and recovery all at once with no working baseline
> underneath, which made a real bug indistinguishable from a tuning problem indistinguishable
> from a false positive. Don't repeat that: (1) prototype each capability in **Gazebo first** —
> cheaper iteration, none of Isaac's manual clock/TF wiring baggage — get it solid there, *then*
> port the working config to Isaac; (2) add back **one piece at a time**, with a green baseline
> after each one (AMCL alone, confirmed holding under rotation-near-furniture, *then* recovery,
> *then* `SmacPlannerHybrid`/replanning) — never all at once again.

- **AMCL / real localization.** Replaced with a hardcoded static `map→odom` TF, because the
  spawn pose is known in advance. This isn't just "a real robot can't assume a known start pose"
  in the abstract — we hit a **concrete, confirmed failure**: AMCL reported `Goal succeeded`
  while the robot was actually stuck spinning in place against the Dresser, nowhere near the
  goal. Extended in-place rotation next to a large, close, flat surface is a classic
  scan-matching divergence trigger for a particle filter — the lidar sweeps the same nearby
  surface repeatedly with little else to disambiguate against, and the estimate can drift to a
  false pose while the physical robot hasn't moved. A false "success" is worse than an honest
  failure for a CI-style pipeline whose whole point is a trustworthy signal. Re-add AMCL as its
  own isolated step, with a regression test, and specifically re-test the "stuck spinning near a
  wall/furniture" scenario before trusting it again — don't just check that it converges from a
  known start.
- **Recovery behaviors (spin/backup).** `behavior_server`'s collision check is broken:
  `nav2_behaviors::Spin`/`BackUp` failed 100% of attempts with `Pose Goes Off Grid` — they
  collision-check against a *subscribed* costmap snapshot (`nav2_costmap_2d::CostmapSubscriber`)
  that never appeared to get populated correctly in our setup, independent of timing or of
  whether a costmap clear preceded the call. Unattended real-hardware operation needs working
  recovery — nobody can Ctrl-C a fleet robot stuck in a warehouse aisle. Root-cause this (check
  whether `/robot_001/local_costmap/costmap_raw` is actually being published/received while
  `behavior_server` is running) before Session 18 (real robot) needs unattended operation.
- **Accurate footprint-aware planning (`SmacPlannerHybrid`/`Lattice`).** Reverted to
  `NavfnPlanner`'s circular `robot_radius` approximation for the passing test. A circle can't
  correctly represent a rectangular chassis in tight spaces — this was the single biggest time
  sink in Session 11/12 (a radius sized for the doorway clipped furniture; a radius sized for
  furniture clearance couldn't fit the doorway). Revisit once the basic pipeline is solid; this
  will matter more, not less, once the fleet includes robots of different shapes/sizes.
- **`collision_monitor`.** Neutered (one real polygon, sized 2cm — smaller than lidar's own
  0.12m minimum range, so it can never actually trigger) rather than disabled outright — an
  empty `polygons: []`/`observation_sources: []` crashes `collision_monitor` when it's loaded as
  a composable node (see gotcha below). It also turned out `collision_monitor` sits *between*
  `controller_server` and Isaac in the cmd_vel pipeline (`cmd_vel_smoothed → cmd_vel`) and can
  silently clamp the outgoing command to zero independent of `use_collision_detection` — once
  the robot got close enough that any nonzero speed read as "too close," it self-locked (distance
  never changes if the robot never moves). No error logged; looked identical to the robot just
  stopping. Re-enabling this for real needs the neutered-polygon workaround kept in mind, and a
  specific eye on this self-lock failure mode.
- **Multi-robot launch parameterization.** The minimal launch (`nav2_isaac_launch.py`) hardcodes
  `robot_001` as literal strings in remap targets and the spawn-pose TF, rather than a
  `LaunchConfiguration('namespace')` — `nav2_bringup`'s `bringup_launch.py` had this for free via
  `ReplaceString`/`<robot_namespace>` templating; our hand-rolled replacement doesn't. Adding
  `robot_002` right now means copying and hand-editing this file, not passing an argument. (Note:
  `nav2_params.yaml`'s topic *values* — `scan topic: /robot_001/scan` etc. — were already
  hardcoded per-robot before this session, so a per-robot params file was always going to be
  needed too; this isn't a new category of problem, just a second file added to the same list.)

**Two hard-won ROS2/Nav2 launch gotchas from writing the minimal launch file** (worth folding
into `CLAUDE.md` if we keep hand-rolling Nav2 launches):
- A ROS2 params YAML's top-level key (`controller_server:`, `local_costmap:`, ...) only matches
  a node whose **exact, unqualified name** equals that key. Giving a node `namespace='robot_001'`
  changes its real name to `/robot_001/controller_server`, which silently fails to match — no
  error, just a fall-through to compiled-in defaults (this is exactly how we ended up with
  `DWBLocalPlanner` loaded instead of our configured RPP, with "no critics defined" as the only
  clue). `nav2_bringup` avoids this with its own namespace-templating machinery. Our workaround
  for hand-rolled launches: don't namespace the node at all — apply the `/robot_001/` prefix
  entirely through explicit **absolute** topic/action remappings instead.
- Composable nodes loaded via a container's `load_node` service call (as `nav2_bringup`'s
  composition does) can't accept an empty-list parameter (`polygons: []`) — the parameter
  bridging code can't infer the array's element type from zero elements and crashes with
  `Expected 'value' to be ... got '()' of type 'tuple'`. A reference config with this exact
  syntax can still "work" if its launch never actually instantiates that node live.

**Suggested re-introduction order:** AMCL alone first (its own regression test, including the
stuck-near-an-obstacle scenario above) → `collision_monitor` (aware of the cmd_vel self-lock) →
accurate footprint/Hybrid planner → recovery behaviors last, once the `CostmapSubscriber` bug is
actually understood. Get a green nav test after each single addition before layering on the
next — the Session 11/12 mistake was combining all of these at once with no working baseline
underneath, which made it impossible to tell a real bug (recovery) apart from a tuning problem
(footprint sizing) apart from a false positive (AMCL).

---

## Session 20 — Future Releases: Working Plan (R2–R5) — LIVING SECTION

> **Status: 🔄 living.** First executed 2026-07-17/18 (planning pass with Mike, same
> night it was chartered). This is not a "session to run once" — it is **the working,
> living description of what the upcoming releases contain.** Update it whenever a
> decision changes (with a matching BLUEPRINT decisions-log entry); read it at every
> release kickoff. BLUEPRINT.md keeps a synced summary + the change history; THIS
> section leads.

**Guiding principle (Mike, standing):** *keep thinking 10x — best for career prospects
and truly creating something unique and needed.* Re-read
`robotics_cicd_10x_blueprint.md` at every release kickoff.

### The release ladder (5 releases, numbered = execution order; relabeled 2026-07-17)

| New | Name | Essence | Was |
|---|---|---|---|
| **R1** | Foundation | Finish S16–18: single rover, scripted missions, 6-stage pipeline, drift detection, sim+HIL+real. Ends at `r1-complete`. | R1 |
| **R2** | Agentic & Alignment Layer | The differentiator: agentic test/heal (human-approved, 3 named failure modes), automated sim-to-real alignment, generative scenario→SDF. Outputs: local-first benchmark + positioning write-up. | R4 |
| **R3** | Fleet & Input Expansion | Second robot (UNO Q bumper bot fed by the Jetson), multi-robot launch parameterization, user-input missions/worlds/robots as pipeline inputs, remote WiFi camera as a fleet resource, new indoor world. | R2 (+new) |
| **R4** | Autonomy & Perception | Wake-up-anywhere (SLAM), dynamic/outdoor worlds (movable walls), Cosmos/VLA-class perception on or beside the robot, semantic costmaps. | R3A (+new) |
| **R5** | Self-Testing Fleet ("brains demo") | AI defines and runs its own missions; parallel sim swarms; the pipeline stress-tests itself. The 10x endgame. | R3B |

Definition sharpness deliberately degrades down the ladder: R2 tight, R3 moderate,
R4/R5 themes — we will know more by then (YAGNI applies to planning too).

**Cut (2026-07-17, revivable only with a written reason):** drone / aerial
coordination — a whole new physics/safety/sim domain for demo value the ground fleet
already provides. The half-built BC drone stays on its shelf.

---

### R1 — Foundation (active; ends at `r1-complete`)

**Remaining scope:** finish Session 16 (Tasks 10–12, final whole-branch review, merge
PR #4) → Session 17 (six Pieces, gate question answered in writing) → Session 18 (robot
deploy + sim-to-real comparison, tag `r1-complete`). Session 19's pick-list is post-R1
bridge work, credited to the R2 era — pick items by time available around robot arrival
(~2026-07-31).
**LLM leverage in R1:** drift detection interpretation (`baseline_monitor` +
`agentic_loop` diagnose), AI test generation (`ai_test_generator`).
**Demo (Showcase Moment 1):** sim + real robot doing the SAME mission side by side,
drift detection visible. 1–2 min video.

### R2 — Agentic & Alignment Layer (next; was "R4")

**Why it is next:** the career/product value lives on the infrastructure axis (agentic
test/heal, alignment, local-first economics), not the robot-ambition axis. Decided
2026-06-27, labels fixed 2026-07-17.

**Entry criteria (before pillar work starts):** the hardened-nav remainder — whatever
Session 19's ladder didn't finish: AMCL stuck-near-furniture regression, real
`collision_monitor` (cmd_vel self-lock aware), footprint-aware planning, working
recovery behaviors (also retires the BR-03 traceability gap / CI `continue-on-error`
wart). Rationale: the agentic loop's credibility requires trustworthy nav signals — a
false AMCL "success" poisons test/heal at the root.

**Three pillars:**
1. **Closed-loop agentic test/heal** on **3 named failure modes** (candidates: nav
   collision, odom Hz drop, sim-to-real drift breach). Claude detects the invariant
   violation, diagnoses from telemetry, **proposes** a fix; **human-in-the-loop
   approval, non-negotiable** — under-claim, over-deliver; full autonomy is framed as
   roadmap, never claimed.
2. **Automated sim-to-real alignment** (the 10x blueprint's "monkey"): ingest real
   rover/Jetson telemetry, auto-tune sim/domain-randomization parameters so the digital
   twin tracks reality. `sim_vs_real_comparison.py` is the seed; the auto-tuning is the
   new work.
3. **Generative scenario→SDF (NL→world):** a natural-language prompt ("dense clutter,
   low light") becomes an actual Gazebo world — not just the JSON scenario descriptions
   `ai_test_generator` emits today. This is the seed of full input-ization (R3).

**Outputs (these ARE the career assets):** the local-first benchmark ("N robot-hours
validated, $0 cloud spend, one RTX 5080", reproducible) and the positioning write-up
("20 years of enterprise release engineering meets physical AI") with the RaaS framing
doc as adjacency.
**LLM leverage added:** test/heal loop + NL→world generation.
**Demo (the one that lands the role):** agentic loop catches an injected regression,
diagnoses it from telemetry, proposes a fix, human approves — sim-to-real alignment
shown tracking, benchmark number on screen.

### R3 — Fleet & Input Expansion

**Robot side:** Arduino UNO Q bumper bot (combined microprocessor/microcontroller) —
wakes up and gets ALL instructions from the Jetson; may explore/map while the Jetson
robot stays put. Prerequisites carried from the Session 19+ deferred list: multi-robot
launch parameterization (kill the hardcoded `robot_001` strings), per-robot params
files, DDS traffic scoping (CycloneDDS config or Zenoh) so sensor topics stay local;
leader-node duties on the Jetson (fleet DB, compact telemetry only over WiFi). Remote
stationary WiFi camera as a fleet resource the Jetson can consult for mapping/decisions.
New indoor world: the living room.
**Pipeline side (the 10x half):** full user-INPUT missions/worlds/robots — a user
submits a mission request / world request / robot profile and the pipeline builds,
simulates, and HIL-tests it. The input-ization layer IS the LLM interface (R2's
NL→world grows into it). MQTT telemetry (production AMR pattern) and the safety-cert
framing doc (SIL2 / UL 60730-1 mapping, not certification) land here.
**Test-infra note (decided 2026-07-17):** the per-test reset strategy becomes
pluggable — drive-home is fine for one robot; resetting MULTIPLE robots between tests
likely prefers full stack restart (hermetic isolation scales to fleets better than
choreographed drive-homes).
**LLM leverage added:** LLM-assisted building of missions/worlds/robot configs.
**Demo:** a user-typed mission request runs end-to-end through the pipeline onto two
real robots, coordinated.

### R4 — Autonomy & Perception (theme)

Wake-up-anywhere: robot boots with the mission but WITHOUT the map — SLAM to build it
(today both sim and plan assume a known map + taped-X start). Dynamic/outdoor worlds:
the outdoor basketball court with movable cardboard walls; dynamic SLAM (costmap layer
that ages out moving obstacles). Perception: the **Cosmos Edge spike** — a foundation
model as an *alternative perception node* behind the same `Detection2DArray` interface
ball_detector publishes, judged by the same ground-truth harness (classical HSV vs
foundation model, same mission, same judges — a uniquely honest comparison our
architecture makes cheap); the **workstation↔Jetson "above-paygrade inference" split**
(heavy models on the RTX 5080, reflexes on the Jetson — mirrors the proven HIL split);
VLA-class semantic navigation ("go to the area with the green box"); SEMANTIC_MAP
upgraded to a live semantic costmap fed by camera detections.
**Caveat recorded at collection time (2026-07-17):** Cosmos 3 Edge weights/quantization/
Jetson support unconfirmed — verify availability when R4 scoping starts; don't trust
"adapt in a day" marketing.
**LLM leverage added:** foundation-model perception in the loop.
**Demo:** robot wakes up somewhere it has never been, maps it, completes a mission —
with classical vs foundation-model perception judged side by side.

### R5 — Self-Testing Fleet ("brains demo"; theme)

The 10x endgame, in Mike's own words: users input **world requests** and **mission
requests**; the pipeline implements, simulates, and HIL-tests them before migrating to
a robot capable of AI inference. The robot wakes in an unknown environment, completes
a given mission autonomously, with access to less-intelligent helper robots, fixed
cameras (and if ever revived, drones) to map and achieve goals. The system designs its
own missions to stress-test the software — including generating new worlds and
objects. Parallel sim swarms; SelfPath-style auto-route generation; full VLA
integration as candidate tech.
**LLM leverage added:** the pipeline defines and runs its own test missions.
**Demo:** the pipeline invents a scenario, finds a REAL bug with it, and shows the fix
validated — no human-authored test anywhere in the loop.

---

### Standing Disciplines (apply to EVERY release and session — added 2026-07-18, Mike)

**1. The 10x check.** At each release's kickoff AND close, answer in writing: *"what in
this release is a 10x move rather than a 10% improvement?"* If the honest answer is
"nothing," the release is mis-scoped — revisit before proceeding. Check against the
three 10x anchors: continuous synthesis/validation engine (not just a pipeline),
automated sim-to-real alignment (the "monkey"), unified virtu-real orchestration.
Current honest reading: R2 pillars are genuine 10x; R3's robot items (UNO Q, worlds)
are 10% ambition riding along with the 10x input-ization — acceptable and fun, but
watch the ratio.

**2. The coaching contract.** Mike is learning robotics/ROS2/CI deeply alongside
building — teaching is a deliverable, not a courtesy. Four mechanisms, every session:
- **Explain-before-doing:** a short who/what/where/how/why before any non-trivial
  technical move (standing policy since Session ~10, now written here).
- **Teach-back close:** each session ends with its 3–5 new concepts posed as questions
  Mike answers in his own words; shaky answers get re-explained and re-queued.
- **`LearningLog.md`** (repo root): append each session's concepts + teach-back
  outcomes; review the log at release boundaries. Seeded 2026-07-18 with Session 16's
  five concepts (teach-back pending).
- **Mike drives** at least one hands-on segment per session (terminal, GUI observation,
  tuning) with Claude navigating — watching builds familiarity; driving builds skill.

**3. The LLM-leverage ramp.** Each release must ADD a new way the pipeline uses AI —
the "LLM leverage added" lines above are the ramp (R1 drift+test-gen → R2 test/heal +
NL→world → R3 LLM-assisted building of missions/worlds/robots → R4 foundation-model
perception → R5 self-defining tests). At each release close ask: *"what does the
pipeline do with AI now that it didn't at the last release?"* Cross-cutting candidate
to pull into ANY release when pain justifies it: **LLM-assisted simulation debugging**
(feed launch logs + telemetry + this file's gotchas to an agent that diagnoses sim
failures — the 2026-07-17 orphan-bridge/TF-flood class of problem is exactly its prey).
**Standing decision:** no RAG at current data scale — direct SQL context injection into
prompts is simpler and better; revisit only when the DB outgrows a prompt.

**4. Demo-first releases.** Every release's demo is defined AT KICKOFF (they are the
**Demo** lines above), budgeted like a feature, and shipped at close — 1–2 min video,
sim + real side by side per the showcase format. **A release without its demo is not
done.** Rule of thumb: if a session's work can't answer "which demo does this feed?",
question it.

---

### Decision record

- **2026-07-17/18 (this pass):** ladder relabeled (agentic layer = R2; numbers =
  execution order); all candidates placed (MikesNotes list + BLUEPRINT What's-Next +
  the 2026-07-17 collected findings) — full change history in BLUEPRINT.md decisions
  log; drone cut; hardened-nav = R2 entry criteria; R1 boundary = `r1-complete` at
  Session 18; Cosmos positioning paragraph assigned to Session 17 Piece 2's docs pass.
- **2026-07-18 (same night, Mike):** Release1Todo.md is the go-to doc — this section
  is the living roadmap home (no summary at the top of the file); Standing Disciplines
  1–4 added; `LearningLog.md` created.

*End of Release1Todo.md*
