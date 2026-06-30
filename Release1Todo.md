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
| 10 | First Passing Nav Test + Self-Hosted CI Runner | ⬜ |
| 11 | Isaac Sim: Install + First Nav Test | ⬜ |
| 12 | Reports + Dashboard: True End-to-End | ⬜ |
| 13 | Agentic Test Loop in Sim | ⬜ |
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

- [ ] **Build, launch locally, verify all three tests pass**:

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

- [ ] **Record bare-metal timing** and add to BLUEPRINT.md under Timings:
  ```bash
  time python -m pytest tests/test_navigation.py -v
  # Note: includes Nav2 startup (~15s) + navigation execution (~30-60s depending on goal)
  ```

- [ ] **Commit and push** — CI will trigger on the self-hosted runner:
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

- [ ] **Install Isaac Sim 5.x via pip** — fastest installation path; no Omniverse GUI needed:

  ```bash
  # Use a separate venv to avoid conflicts with the fleet-env:
  python3 -m venv ~/isaac-env
  source ~/isaac-env/bin/activate

  # Install Isaac Sim (large download — ~20 GB, takes 20-40 min):
  pip install isaacsim==5.0.0 \
    --extra-index-url https://pypi.nvidia.com \
    --extra-index-url https://download.pytorch.org/whl/cu121

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

- [ ] **Enable the ROS2 bridge extension** — Isaac Sim loads extensions at runtime. Create
  a startup script that enables the ROS2 bridge and loads a simple scene:

  ```python
  # scripts/isaac_ros2_bridge.py
  """Start Isaac Sim with ROS2 bridge enabled."""
  from isaacsim import SimulationApp

  app = SimulationApp({'headless': True, 'renderer': 'RayTracedLighting'})

  # Enable ROS2 bridge extension
  from omni.isaac.core.utils.extensions import enable_extension
  enable_extension('omni.isaac.ros2_bridge')

  import omni
  import rclpy
  from omni.isaac.core import World

  world = World()
  world.reset()

  print('[Isaac] ROS2 bridge enabled. Spinning...')
  for _ in range(300):   # run for ~30 seconds at 10 Hz
      world.step(render=False)

  app.close()
  ```

  Run it and verify ROS2 topics appear:
  ```bash
  source ~/isaac-env/bin/activate
  source /opt/ros/jazzy/setup.bash
  python scripts/isaac_ros2_bridge.py &
  sleep 10
  ros2 topic list   # should show /clock and other Isaac topics
  ```

- [ ] **Load the bedroom world in Isaac** — Isaac uses USD format. The simplest first step
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

- [ ] **Spawn ugv_pt and run a simple Nav2 test in Isaac** — wire nav_runner.py against
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

- [ ] **Wire Isaac Sim CI job** — uses the same self-hosted runner as Session 10's
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

- [ ] **Record Isaac Sim timing** — note first-launch shader compile time (one-time) vs
  subsequent launch time. Add both to BLUEPRINT.md under Timings:
  ```
  Isaac Sim first launch (shader compile): ~XX min
  Isaac Sim subsequent launch to ready: ~X min
  Isaac nav test wall time: ~XX s
  ```

- [ ] **Commit**:
  ```bash
  git add .
  git commit -m "feat(session-11): Isaac Sim bare metal, ROS2 bridge, isaac-validation CI job"
  git push
  ```

### Session Complete When
- `python scripts/isaac_ros2_bridge.py` launches without error, ROS2 topics visible
- `/robot_001/odom` and `/robot_001/scan` publishing in Isaac (check with `ros2 topic hz`)
- `isaac-validation` CI job green on self-hosted runner
- Isaac timing numbers recorded in BLUEPRINT.md

---

## Session 12 — Reports + Dashboard: True End-to-End (~3 hrs)

### Recommended Reading
- [Streamlit documentation](https://docs.streamlit.io/) — multi-page apps, `st.sidebar`, `st.tabs`
- [ReportLab PDF generation](https://docs.reportlab.com/reportlab/userguide/ch1_intro/) — generating PDFs programmatically
- [Pandera data validation](https://pandera.readthedocs.io/en/stable/) — schema validation for the telemetry JSON

### Prerequisites
- Sessions 10 and 11 complete — at least one real run report in `reports/history/`
- `pip install streamlit reportlab pandera` in fleet-env (already in requirements.txt)

### Steps

- [ ] **Complete `tools/telemetry_logger.py`** — writes a structured JSON file per CI run to
  `reports/history/<run_id>.json`. The run_id is `YYYYMMDD_HHMMSS` or the GHA run number.

  Key schema fields (match `tests/test_baseline.py` expectations):
  ```json
  {
    "run_id": "20260629_143022",
    "timestamp": "2026-06-29T14:30:22Z",
    "robot_id": "robot_001",
    "nav_success_rate": 1.0,
    "mean_position_error_m": 0.08,
    "odom_hz": 50.1,
    "scan_hz": 10.0,
    "collision_count": 0,
    "mission_duration_s": 47.3,
    "sim_engine": "gazebo"
  }
  ```

  Call `telemetry_logger.log_run(metrics, sim_engine='gazebo')` at the end of
  `test_navigation.py` to write the file automatically on each test run.

- [ ] **Complete `tools/generate_test_report.py`** — reads all JSON files from
  `reports/history/`, produces a PDF summary with run table + drift trend chart:

  ```python
  # Key output: reports/latest_report.pdf
  # Sections: Run Summary table, Position Error trend (matplotlib), Pass/Fail per run
  ```

  Test locally:
  ```bash
  python tools/generate_test_report.py
  # Should produce reports/latest_report.pdf — open with a PDF viewer to verify
  evince reports/latest_report.pdf
  ```

- [ ] **Complete `dashboard/app.py`** — Streamlit app with three tabs:

  - **Fleet Overview** — table of all runs, pass/fail, position error trend line chart
  - **Drift Alerts** — runs where any metric breached `config/drift_config.yaml` thresholds
  - **Run Detail** — select a run_id and see all metrics for that run

  Test locally:
  ```bash
  streamlit run dashboard/app.py
  # Opens browser at localhost:8501 — verify all three tabs render with real data
  ```

- [ ] **Wire the Reports CI job** — add to `ci.yml` after `isaac-validation`:

  ```yaml
  reports-dashboard:
    runs-on: ubuntu-latest
    needs: isaac-validation
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pip install -r requirements-ci.txt
      - name: Generate report
        run: python tools/generate_test_report.py
      - name: Upload PDF report
        uses: actions/upload-artifact@v4
        with:
          name: test-report-${{ github.run_number }}
          path: reports/latest_report.pdf
      - name: Upload JSON history
        uses: actions/upload-artifact@v4
        with:
          name: run-history-${{ github.run_number }}
          path: reports/history/
  ```

- [ ] **Test `baseline_monitor.py`** — generate 5+ run JSON files (run the nav test five
  times or copy/tweak existing ones), then:
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
- `streamlit run dashboard/app.py` shows real run data in all three tabs
- `reports/latest_report.pdf` generates from real run history
- `reports-dashboard` CI job green, PDF artifact downloadable from GitHub Actions run
- `baseline_monitor.py` detects a simulated drift breach when you inject a bad run

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

### Prerequisites
- Session 12 complete — `reports/history/` has real run JSON files
- `pip install anthropic` in fleet-env (already in requirements.txt)
- `ANTHROPIC_API_KEY` set in environment (add to `.env` or export in shell):
  ```bash
  echo 'export ANTHROPIC_API_KEY=sk-ant-...' >> ~/.bashrc
  source ~/.bashrc
  ```

### Steps

- [ ] **Create `tools/agentic_loop.py`** — the main orchestrator. Reads the latest run
  report, calls Claude with telemetry context, gets a structured diagnosis + proposed
  action, presents it to the human for approval, then applies the approved action:

  ```python
  # Copyright 2026 Mike. Licensed under Apache 2.0.
  """Agentic test loop: diagnose failures, propose fixes, await human approval."""
  import anthropic
  import json
  import os
  import glob
  import subprocess
  from pathlib import Path

  client = anthropic.Anthropic()

  # Named locations matching the bedroom world geometry.
  # Claude uses these names in mission plans instead of raw (x, y) coordinates.
  SEMANTIC_MAP = {
      'home_base':       (-1.276, 1.09),   # robot spawn point
      'center':          (0.0,   0.0),
      'north_corridor':  (0.0,   2.5),
      'south_corridor':  (0.0,  -2.5),
      'east_zone':       (2.5,   0.0),
      'west_zone':       (-2.5,  0.0),
      'obstacle_zone_1': (1.0,   1.0),     # furniture obstacle 1 in SDF
      'obstacle_zone_2': (-1.0,  0.5),     # furniture obstacle 2 in SDF
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


  def load_latest_run():
      """Load the most recent run JSON from reports/history/."""
      files = sorted(glob.glob('reports/history/*.json'))
      if not files:
          raise FileNotFoundError('No run reports found in reports/history/')
      with open(files[-1]) as f:
          return json.load(f)


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


  def diagnose(run_data):
      """Call Claude with telemetry; get structured diagnosis and proposed action."""
      locations_str = '\n'.join(f'  {k}: {v}' for k, v in SEMANTIC_MAP.items())
      prompt = f"""You are an autonomous robotics test engineer.

  The latest nav test run produced these results:
  {json.dumps(run_data, indent=2)}

  Drift thresholds (from config/drift_config.yaml):
  - nav_success_rate: >= 0.95
  - mean_position_error_m: <= 0.15
  - odom_hz: >= 45
  - scan_hz: >= 9
  - collision_count: 0

  Available named locations in this environment (use these in mission plans):
{locations_str}

  Analyse the results. If any metric is outside threshold, diagnose the likely cause
  and use ONE tool to propose a concrete action. If all metrics are healthy, use
  propose_mission_plan with semantic location names to create a more challenging
  multi-waypoint mission (e.g. "patrol north and south corridors, return to home_base")
  or use generate_world_variant to propose a harder obstacle layout."""

      response = client.messages.create(
          model='claude-sonnet-4-6',
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
      print(f'[agentic] Loaded run: {run_data["run_id"]}')

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

- [ ] **Test the loop end-to-end on bare metal**:
  ```bash
  # Make sure a run report exists:
  ls reports/history/

  # Run the agentic loop:
  python tools/agentic_loop.py
  # Claude analyses the run, proposes an action
  # You see the proposal and approve/reject
  # If approved: world variant created OR nav param change shown OR mission plan saved
  ```

- [ ] **Inject a failure and verify diagnosis** — manually edit a copy of a run report,
  set `nav_success_rate` to 0.7 and `mean_position_error_m` to 0.22, save it as a new
  file in `reports/history/`, then run `agentic_loop.py` and check that Claude correctly
  identifies the failure and proposes a nav param change:
  ```bash
  cp reports/history/<latest>.json reports/history/injected_failure.json
  # Edit injected_failure.json: nav_success_rate=0.7, mean_position_error_m=0.22
  python tools/agentic_loop.py
  # Claude should propose: propose_nav_param_change (e.g. increase inflation_radius or reduce speed)
  ```

- [ ] **Test generative world variant** — when all metrics are healthy, Claude should call
  `generate_world_variant`. Approve it, then verify the new SDF file is valid:
  ```bash
  python tools/agentic_loop.py
  # After approval, a new .sdf should appear in src/nav_fleet/worlds/
  gz sdf -k src/nav_fleet/worlds/<variant_name>.sdf  # validate the SDF
  ```

- [ ] **Commit**:
  ```bash
  git add .
  git commit -m "feat(session-13): agentic loop — diagnosis, world generation, mission planning"
  git push
  ```

### Session Complete When
- `python tools/agentic_loop.py` runs end-to-end: loads report, Claude diagnoses, proposes action, human approves, action applied
- Injected failure triggers a `propose_nav_param_change` response
- Healthy run triggers a `generate_world_variant` response
- New SDF world variant passes `gz sdf -k` validation

---

## Session 14 — Jetson Orin Nano: Flash + ROS2 + CI Runner (~3 hrs)

### Recommended Reading
- [NVIDIA SDK Manager](https://developer.nvidia.com/sdk-manager) — the flashing tool; install on Ubuntu host
- [JetPack 6.x release notes](https://developer.nvidia.com/embedded/jetpack-sdk-62) — check ROS2 Jazzy compatibility; JetPack 6.x = Ubuntu 22.04 base on Jetson, may need ROS2 Humble instead
- [Self-hosted runners: adding from org](https://docs.github.com/en/actions/hosting-your-own-runners/managing-self-hosted-runners/adding-self-hosted-runners) — same flow as Session 10 but on the Jetson

> **Hardware dependency:** This session requires the Jetson Orin Nano Super Developer Kit
> to be physically on hand. Sessions 10–13 can be completed while waiting for hardware.
>
> **JetPack / ROS2 compatibility note:** JetPack 6.x ships Ubuntu 22.04 (not 24.04).
> ROS2 Jazzy requires Ubuntu 24.04. On the Jetson you will likely use **ROS2 Humble**
> (Ubuntu 22.04 native) and keep Jazzy on the x86 workstation. The arm64 CI build
> (Docker) already uses the `ros:jazzy-ros-base` image which is multiarch — this
> is fine. The Jetson native runner builds and tests on Humble. Confirm the JetPack
> version you receive and adjust accordingly.

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
  - SDK Manager → select Jetson Orin Nano → latest JetPack (6.x)
  - Select: Jetson Linux (BSP) + ROS-related components if offered
  - Flash — takes 20–40 min
  - On completion: Jetson boots to Ubuntu desktop

- [ ] **Initial Jetson setup** (SSH from workstation — find Jetson IP via router or `arp -a`):
  ```bash
  ssh mike@<jetson-ip>
  sudo apt update && sudo apt upgrade -y

  # Install ROS2 (Humble on Ubuntu 22.04 / Jazzy on Ubuntu 24.04 — match your JetPack):
  sudo apt install software-properties-common curl -y
  sudo curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key \
    -o /usr/share/keyrings/ros-archive-keyring.gpg
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] \
    http://packages.ros.org/ros2/ubuntu $(. /etc/os-release && echo $UBUNTU_CODENAME) main" \
    | sudo tee /etc/apt/sources.list.d/ros2.list > /dev/null
  sudo apt update
  sudo apt install ros-<DISTRO>-desktop ros-<DISTRO>-navigation2 ros-<DISTRO>-nav2-bringup \
    ros-<DISTRO>-rmw-cyclonedds-cpp python3-colcon-common-extensions -y

  # Add to .bashrc:
  echo "source /opt/ros/<DISTRO>/setup.bash" >> ~/.bashrc
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

- [ ] **Update the `arm64-build` CI job** in `ci.yml` to use the Jetson runner**:
  ```yaml
  arm64-build:
    runs-on: [self-hosted, arm64, jetson]   # was: ubuntu-latest
    needs: code-quality
    steps:
      - uses: actions/checkout@v4
      - name: Native arm64 build
        run: |
          source /opt/ros/<DISTRO>/setup.bash
          colcon build --symlink-install
      - name: Record build time
        run: echo "arm64 native build at $(date)" >> reports/session14_timings.txt
  ```

  > **Gotcha:** Remove (or comment out) the Docker buildx steps that ran QEMU emulation
  > — the Jetson native runner makes them obsolete. Keep the Dockerfile in the repo for
  > reference but the CI no longer needs it for the arm64 build job.

- [ ] **Push and record the speedup**:
  ```bash
  git add .
  git commit -m "feat(session-14): Jetson arm64 native CI runner replaces QEMU"
  git push
  gh run watch   # watch the arm64 build run on jetson-runner
  # Compare time vs QEMU baseline recorded in BLUEPRINT.md (Session 08)
  ```

  Record in BLUEPRINT.md:
  ```
  arm64 build — QEMU (Session 08): ~25-30 min
  arm64 build — Jetson native (Session 14): ~X min
  Speedup: ~Xx reduction
  ```

### Session Complete When
- Jetson boots, SSH accessible, ROS2 installed
- `colcon build` succeeds on Jetson (native arm64)
- `arm64-build` CI job runs green on `jetson-runner`
- Speedup vs QEMU recorded in BLUEPRINT.md

---

## Session 15 — Real Robot: Deploy + Sim-to-Real Comparison (~3 hrs)

### Recommended Reading
- [SLAM Toolbox online async](https://github.com/SteveMacenski/slam_toolbox#readme) — for building the real-room map
- [Nav2 map server](https://docs.nav2.org/configuration/packages/configuring-map-server.html) — serving the saved SLAM map
- [teleop_twist_keyboard](https://index.ros.org/p/teleop_twist_keyboard/) — driving the robot during SLAM mapping

> **Hardware dependency:** Requires Jetson module transferred to the UGV-PT carrier board
> (or a second Jetson module purchased). The Jetson from Session 14 can be transferred;
> buy a second module if you want to keep the Dev Kit as the CI runner.
>
> **Waveshare UGV-PT dimensions note (carry-over from Session 10):** Before running real
> nav missions, measure the actual robot and update `urdf/ugv_pt.urdf.xacro` to match:
> body dimensions, wheel_radius, wheel_separation. Reference:
> [Waveshare UGV-PT spec sheet](https://www.waveshare.com/ugv-pt.htm).

### Prerequisites
- Sessions 10–14 complete
- Jetson Orin Nano transferred to / installed in Waveshare UGV-PT
- Robot powered on, accessible via SSH over WiFi or Ethernet
- Real bedroom clear enough to drive the robot safely for SLAM mapping

### Steps

- [ ] **Build a real-room SLAM map** — drive the robot around the room once while
  SLAM Toolbox records the map:

  ```bash
  # Terminal 1 — on the Jetson (SSH):
  source /opt/ros/<DISTRO>/setup.bash
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
    needs: reports-dashboard
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
            source /opt/ros/<DISTRO>/setup.bash
            colcon build --symlink-install
            source install/setup.bash
            # Smoke test: launch Nav2 and check topics
            ros2 launch nav_fleet robot_launch.py &
            sleep 15
            ros2 topic hz /robot_001/odom --once | grep -q "Hz" || exit 1
            ros2 topic hz /robot_001/scan --once | grep -q "Hz" || exit 1
            echo "Smoke test passed"
  ```

  > **Gotcha — SSH secrets:** `ROBOT_IP` and `ROBOT_SSH_KEY` must be set in
  > GitHub → Settings → Secrets. Generate a dedicated key pair for the robot:
  > `ssh-keygen -t ed25519 -f ~/.ssh/robot_deploy_key` on the workstation, then
  > `ssh-copy-id -i ~/.ssh/robot_deploy_key mike@<robot-ip>`.

- [ ] **Run sim-to-real comparison**:
  ```bash
  # Run the same nav goal on the real robot that you ran in Gazebo (1.0, 1.0):
  # On robot (SSH): ros2 launch nav_fleet robot_launch.py
  # On workstation:
  python -c "
  import rclpy
  import sys; sys.path.insert(0, 'src/nav_fleet/nav_fleet')
  from nav_runner import NavRunner
  rclpy.init()
  r = NavRunner()
  print(r.send_goal(1.0, 1.0))
  r.destroy_node(); rclpy.shutdown()
  "
  # telemetry_logger.py writes a real run JSON to reports/history/ with sim_engine='real'

  # Compare:
  python tools/sim_vs_real_comparison.py
  # Reports: correlation between sim and real nav_success_rate, mean_position_error
  # Target: correlation >= 70%
  ```

- [ ] **Tag r1-complete** if sim-to-real correlation >= 70%:
  ```bash
  git tag r1-complete
  git push origin r1-complete
  ```
  If correlation < 70%: check BLUEPRINT.md Kill Criteria section and decide next steps
  (usually: tune nav2_params, fix URDF dimensions, or accept the gap with documentation).

- [ ] **Commit**:
  ```bash
  git add .
  git commit -m "feat(session-15): real robot deploy, SLAM map, sim-to-real comparison, r1-complete"
  git push
  ```

### Session Complete When
- `bedroom_real.pgm` + `bedroom_real.yaml` saved and committed
- `robot_launch.py` launches Nav2 on the real robot successfully
- Real robot navigates to (1.0, 1.0) without collision
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

---

*End of Release1Todo.md*
