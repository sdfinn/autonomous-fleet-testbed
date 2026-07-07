# Release 1 Todo — autonomous-fleet-testbed

**Goal:** Complete 6-stage CI/CD pipeline with one real robot (Waveshare UGV PT + Jetson Orin Nano Super). Sim-to-real validation is real, not a placeholder.  
**Tag on completion:** `git tag r1-complete`  
**Format:** Each session ~3 hrs. Do sessions in order — each one gates the next.

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
| 14 | Jetson Orin Nano: Flash + ROS2 + CI Runner | ⬜ |
| 15 | Real Robot: Deploy + Sim-to-Real Comparison | ⬜ |
| 16+ | Agentic Loop on Real Hardware + Advanced Missions | ⬜ |

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
  `propose_nav_param_change` response expected.

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

- [ ] **Install NVIDIA SDK Manager on workstation**:
  ```bash
  # Download .deb from https://developer.nvidia.com/sdk-manager
  sudo apt install ./sdkmanager_<version>_amd64.deb
  sdkmanager  # launches GUI
  ```

- [ ] **Flash JetPack via SDK Manager**:
  - Connect Jetson in recovery mode (hold RECOVERY button, press POWER)
  - SDK Manager → select Jetson Orin Nano → **JetPack 7.2** (not 6.x — see decision note above)
  - Select: Jetson Linux (BSP) + ROS-related components if offered
  - Flash — takes 20–40 min
  - On completion: Jetson boots to Ubuntu desktop
  - Verify: `cat /etc/os-release` reports 24.04

- [ ] **Storage: flash to MicroSD and record a baseline:**
  R1 ships on MicroSD (the dev kit default). Record during this session:
  - apt/ROS2 install wall time
  - `time colcon build --symlink-install` (native arm64 on SD)
  - first `docker pull` time of the stage-2 image (see container step below)
  > **SD hygiene:** don't record rosbags or heavy logs to the SD card while it's still in
  > use — storage write speed only bites when *recording*, and sustained writes are what
  > wear SD cards out. DDS traffic itself is RAM-to-RAM and doesn't touch storage.

- [ ] **Swap to NVMe SSD and re-record the same numbers (moved up from Session 16+,
  2026-07-06)** — do this now, while the module is still a bare dev kit on the desk, not
  after Session 15 transfers it into the robot chassis. Swapping storage is strictly easier
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

Not required for session completion, r1-complete, or Session 15 — only attempt this if the
core flow above (unpack → flash → storage baseline → native build → CI runner swap) goes
smoothly with session time left over. This is the "run ROS2 code on the Jetson as part of
sim" idea, refined through discussion:

- **Goal:** validate robustness/speed/reproducibility of running Nav2 on Jetson-class ARM
  hardware before Session 15's real robot arrives — mainly, does Nav2 (AMCL, costmaps,
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
  Session 15's actual target architecture where sensors and Nav2 will both live on the
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

## Session 15 — Real Robot: Deploy + Sim-to-Real Comparison (~3 hrs)

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
> **Waveshare UGV-PT dimensions note (carry-over from Session 10):** Before running real
> nav missions, measure the actual robot and update `urdf/ugv_pt.urdf.xacro` to match:
> body dimensions, wheel_radius, wheel_separation. Reference:
> [Waveshare UGV-PT spec sheet](https://www.waveshare.com/ugv-pt.htm).
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

## Session 16+ — Agentic Loop on Real Hardware + Advanced Missions

> Expand this section when Session 15 is complete. At this point the agentic loop from
> Session 13 runs against real robot telemetry instead of simulated data. The learning
> loop feeds live results back into both sim improvement and nav parameter tuning.

**Direction for Session 16:**
- Run `tools/agentic_loop.py` against real run reports (`sim_engine: 'real'`)
- Claude compares real vs sim metrics, identifies sim fidelity gaps, proposes sim
  parameter updates to close the gap
- Advanced mission types: natural language mission → Claude generates goal sequence →
  robot executes → results fed back to Claude for next iteration
- Log real-world navigation videos + telemetry for portfolio/demo

### Going untethered — systemd autostart (decision 2026-07-03: deferred out of R1)

r1-complete is achievable entirely over SSH (Session 15's smoke test, nav goal, and
sim-to-real comparison all run remotely). True autonomy — flip the power switch, robot boots
into nav with no monitor/keyboard/SSH — is this item:

- systemd units on the Jetson: one for the base+lidar driver bringup (Session 15's driver
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
fleet needs before Session 16 is for real — captured here so it doesn't quietly get forgotten:

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
  `behavior_server` is running) before Session 14+.
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

*End of Release1Todo.md*
