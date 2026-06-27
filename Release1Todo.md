# Release 1 Todo — autonomous-fleet-testbed

**Goal:** Complete 6-stage CI/CD pipeline with one real robot (Waveshare UGV PT + Jetson Orin Nano Super). Sim-to-real validation is real, not a placeholder.  
**Tag on completion:** `git tag r1-complete`  
**Format:** Each session ~3 hrs. Do sessions in order — each one gates the next.

---

## Session Index

| # | Title | Phase | Status |
|---|---|---|---|
| 01 | Ubuntu 24.04 Dual Boot | A | ✅ |
| 02 | ROS2 Jazzy + Gazebo Harmonic | A | ✅ |
| 03 | Docker + Tools + GitHub CLI | A | ✅ |
| 04 | GitHub Repo + Project Skeleton | A | ✅ |
| 05 | File Migration from Current Project | A | ✅ |
| 06 | Stage 0 — Requirements Gate | A | ✅ |
| 07 | Stage 1 — Code Quality Gate | A | ⬜ |
| 08 | Stage 2 — arm64 Cross-Compile + QEMU Baseline | A | ⬜ |
| 09 | Stage 3 Part 1 — URDF + Nav2 in Gazebo Headless | A | ⬜ |
| 10 | Stage 3 Part 2 — First Passing Nav Test + Drift Wired | A | ⬜ |
| 11 | Tag ci-qemu-baseline + Document Timing | A | ⬜ |
| 12 | Stage 4 — CUDA + NVIDIA Driver + Isaac Sim Perception | A | ⬜ |
| 13 | Stage 5 — Reports + Dashboard | A | ⬜ |
| 14 | Phase B — Jetson Dev Kit Setup + GHA Runner | B | ⬜ |
| 15 | Phase B — Jetson Native Build + Timing Benchmark | B | ⬜ |
| 16 | Phase C — Rover + Stage 6 Deploy + r1-complete | C | ⬜ |

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

- [ ] **Verify CI triggers on GitHub:**
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

- [ ] **Install ament linting tools:**
  ```bash
  sudo apt install ros-jazzy-ament-lint-auto ros-jazzy-ament-flake8 \
    ros-jazzy-ament-pep257 ros-jazzy-ament-copyright -y
  pip install flake8 pep257
  ```

- [ ] **Run ament lint locally on the ROS2 package:**
  ```bash
  cd ~/autonomous-fleet-testbed
  colcon build --symlink-install
  source install/setup.bash
  colcon test --packages-select nav_fleet
  colcon test-result --verbose
  # Fix any flake8/copyright lint errors reported
  ```

- [ ] **Common lint fixes:**
  - Each Python file needs a copyright header. Add to the top of `nav_runner.py` and `metrics_collector.py`:
    ```python
    # Copyright 2026 Mike. Licensed under MIT.
    ```
  - Max line length is 99 chars. Check `tools/*.py` too.
  - No trailing whitespace.

- [ ] **Wire Stage 1 into CI** — replace the Stage 1 stub job in `ci.yml`:
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

- [ ] **Commit and verify CI:**
  ```bash
  git add .
  git commit -m "feat: Stage 1 code quality gate — ament lint + pytest in CI"
  git push
  gh run watch   # watch the pipeline live
  ```

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

- [ ] **Create `Dockerfile`:**
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

- [ ] **Build arm64 image locally (QEMU — this is slow, ~25–30 min, record the time):**
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

- [ ] **Push image to GitHub Container Registry:**
  ```bash
  # Authenticate with GHCR
  echo $GITHUB_TOKEN | docker login ghcr.io -u sdfinn70 --password-stdin
  # If you don't have GITHUB_TOKEN, create a PAT at github.com → Settings → Developer settings → PATs
  # Scope: write:packages, read:packages

  docker push ghcr.io/sdfinn/autonomous-fleet-testbed:latest
  ```

- [ ] **Wire Stage 2 into CI** — replace the Stage 2 stub job in `ci.yml`:
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

- [ ] **Commit and let CI run:**
  ```bash
  git add .
  git commit -m "feat: Stage 2 arm64 QEMU cross-compile — Dockerfile + GHA workflow"
  git push

  # Watch CI — Stage 2 will take 25–30 min on QEMU
  gh run watch
  ```

- [ ] **Record the QEMU baseline time** from the GHA run summary. This number is the "before" for the Jetson runner upgrade in Phase B.

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

- [ ] **Get the Waveshare URDF as a reference:**
  ```bash
  cd ~
  git clone https://github.com/waveshareteam/ugv_ws.git waveshare_ref
  # Browse: ls waveshare_ref/src/
  # Find the URDF files — copy the relevant xacro as a starting point
  ```

- [ ] **Create a simplified URDF for Stage 3 (`urdf/ugv_pt.urdf.xacro`):**

  > **Note:** The full Waveshare URDF includes hardware-specific plugins. For Stage 3 (Gazebo only), use a simplified version with Gazebo diff-drive and lidar plugins. Refine to match real hardware specs in Session 15.

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

- [ ] **Create a simple bedroom world (`worlds/bedroom_simple.sdf`):**
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

- [ ] **Create a launch file (`src/nav_fleet/nav_fleet/sim_launch.py`):**

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

- [ ] **Create `config/nav2_params.yaml`** — copy from nav2_bringup defaults and customize namespace:
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

- [ ] **Add urdf/ and worlds/ to the installed package** — update `setup.py` data_files:
  ```python
  data_files=[
      ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
      ('share/' + package_name, ['package.xml']),
      ('share/' + package_name + '/config', ['config/nav2_params.yaml', 'config/drift_config.yaml']),
      ('share/' + package_name + '/urdf', ['urdf/ugv_pt.urdf.xacro']),
      ('share/' + package_name + '/worlds', ['worlds/bedroom_simple.sdf']),
  ],
  ```

- [ ] **Rebuild and launch:**
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

- [ ] **Commit:**
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

## Sessions 10–16 — Outlines (Expand When Reached)

---

### Session 10 — Stage 3 Part 2: First Passing Nav Test + Drift Wired (~3 hrs)

**Goal:** Nav2 sends the robot from start to goal. Test asserts < 0.15m position error, zero collisions. `test_baseline.py` runs against the first real run report. `test_ros2_contracts.py` passes.

**Key tasks:**
- Implement `nav_runner.py` — sends a Nav2 action goal via `NavigateToPose` action client, records result
- Implement `metrics_collector.py` — subscribes to `/robot_001/odom`, `/robot_001/scan`, measures Hz, detects collision via `/robot_001/scan` min range
- Write `tests/test_navigation.py` — BR-01 (position error), BR-02 (collisions), BR-10 (BT success)
- Enable `test_ros2_contracts.py` in Stage 3 CI job
- Wire Stage 3 Gazebo job into CI (headless, `--headless-rendering` flag)
- Remove `continue-on-error: true` from Stage 0 once all requirements are covered

**Reference:** [Nav2 action client tutorial](https://docs.nav2.org/tutorials/docs/get_started.html)

---

### Session 11 — Tag ci-qemu-baseline + Document Timing (~1 hr)

**Goal:** All Stages 0–3 green. Tag the baseline. Record timings.

**Key tasks:**
- Confirm all stages green in GHA
- Record Stage 2 QEMU build time from GHA summary (the "before" number)
- Record Stage 3 Gazebo test time
- `git tag ci-qemu-baseline && git push origin ci-qemu-baseline`
- Update BLUEPRINT.md Decisions Log with both timing numbers

---

### Session 12 — Stage 4: CUDA + NVIDIA Driver + Isaac Sim (~3 hrs)

**Goal:** RTX 5080 validated in Ubuntu. Isaac Sim launches. Stage 4 perception test runs (YOLO mAP on simulated camera feed).

**Key tasks:**
- Install NVIDIA driver 570+ on Ubuntu: `sudo ubuntu-drivers install`
- Install CUDA 13 toolkit from [developer.nvidia.com/cuda-downloads](https://developer.nvidia.com/cuda-downloads)
- Install Isaac Sim 5.x via Omniverse Launcher (Ubuntu)
- Write Stage 4 CI job: self-hosted runner with `[self-hosted, rtx5080]` label
- Register workstation as GHA self-hosted runner for Stage 4

**Note:** Isaac Sim install and first launch alone is a 2–3 hr task. This session may need to be split.

---

### Session 13 — Stage 5: Reports + Dashboard (~3 hrs)

**Goal:** Every CI run produces a JSON report saved to `reports/history/`. Dashboard shows run history. PDF report generates.

**Key tasks:**
- Complete `tools/telemetry_logger.py` — writes JSON to `reports/history/<run_id>.json`
- Complete `tools/generate_test_report.py` — reads history, produces PDF via ReportLab
- Complete `dashboard/app.py` — Streamlit multi-tab: Fleet Overview, Drift Alerts, Run Detail
- Wire Stage 5 into CI: artifact upload of JSON report + PDF
- Test that `baseline_monitor.py` reads 5+ history files and produces drift output

---

### Session 14 — Phase B: Jetson Dev Kit Setup + GHA Runner (~3 hrs)

**Goal:** Jetson Orin Nano Super Developer Kit is flashed, on the network, registered as a GHA runner.

**Key tasks:**
- Flash JetPack 7.2 via SDK Manager on Ubuntu host
- Install ROS2 Jazzy on Jetson (native arm64, no QEMU)
- Install CycloneDDS on Jetson
- Register Jetson as GHA self-hosted runner with label `[self-hosted, arm64, jetson]`
- Add `~/.bashrc` sourcing on Jetson: ROS2 + CycloneDDS

**Reference:** [Jetson SDK Manager](https://developer.nvidia.com/sdk-manager), [Self-hosted GHA runners](https://docs.github.com/en/actions/hosting-your-own-runners)

---

### Session 15 — Phase B: Jetson Native Build + Timing Benchmark (~3 hrs)

**Goal:** Stage 2 now runs on the Jetson native arm64 runner. Measure and record the speedup.

**Key tasks:**
- Update Stage 2 CI job: change `runs-on` from `ubuntu-latest` to `[self-hosted, arm64, jetson]`
- Push and let CI run
- Record Stage 2 build time (expect ~3–5 min vs 25–30 min on QEMU)
- `git tag ci-jetson-upgrade && git push origin ci-jetson-upgrade`
- Compute and document the delta in BLUEPRINT.md: "Stage 2: 28 min → 3 min (89% reduction)"

---

### Session 16 — Phase C: Rover + Stage 6 Deploy + r1-complete (~3 hrs)

**Goal:** Waveshare UGV PT received, flashed, connected. Stage 6 deploys nav_fleet to the rover and runs a smoke test. R1 is done.

**Key tasks:**
- Transfer Jetson module from Dev Kit to UGV PT carrier board (or buy second module)
- One-time SLAM map build:
  ```bash
  # On Jetson (SSH):
  ros2 launch slam_toolbox online_async_launch.py use_sim_time:=false
  # On workstation (teleop the rover around the room):
  ros2 run teleop_twist_keyboard teleop_twist_keyboard --ros-args -r /cmd_vel:=/robot_001/cmd_vel
  # Save map:
  ros2 run nav2_map_server map_saver_cli -f maps/bedroom_real
  ```
- Write Stage 6 CI job: SSH deploy, `ros2 launch nav_fleet robot_launch.py`, smoke test (topic Hz assertions), auto-rollback on failure
- Record sim-to-real comparison: run `tools/sim_vs_real_comparison.py` with sim DB and real DB. Check nav_success_rate and mean_position_error correlation.
- If correlation >= 70%: R1 done. `git tag r1-complete && git push origin r1-complete`
- If correlation < 70%: See "Kill Criteria" in BLUEPRINT.md

---

*End of Release1Todo.md — Sessions 10–16 to be expanded as each is reached.*
