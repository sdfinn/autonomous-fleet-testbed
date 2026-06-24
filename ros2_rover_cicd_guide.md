<!-- Page 1 -->
ROS2 Rover — CI/CD & Autonomy
Guide
v2 — Updated for JetPack 7.2 / Ubuntu 24.04 / ROS2 Jazzy
Waveshare UGV Rover PT + Jetson Orin Nano Super + ESP32 + Gazebo Harmonic +
Isaac Sim
4-wheel rover with D500 lidar + OAK-D Lite camera | end-to-end pipeline | drift detection |
run reports
This document covers requirements definition (including MCU/ESP32 firmware), full CI/CD pipeline setup,
simulation strategy (Gazebo for CI gating, Isaac Sim for advanced validation), drift detection, reporting, and
deployment to the Jetson Orin Nano Super running JetPack 7.2.
v2 Changes: JetPack 7.2 brings Ubuntu 24.04 + CUDA 13 + kernel 6.8 to the full Jetson Orin family
(released June 1, 2026). This eliminates the Ubuntu 22.04 / ROS2 Humble constraint. Workstation
and rover now run an identical stack: Ubuntu 24.04 + ROS2 Jazzy. A single arm64 Docker image
targets both. MCU section updated to ESP32 (Waveshare sub-controller).


---

<!-- Page 2 -->
Table of contents
0. Hardware and software environment (v2: JetPack 7.2)
1. Requirements — scene, brain, and MCU firmware
2. Repository structure
3. Stage 0 — requirements gate
4. Stage 1 — code quality (ROS2 + ESP32 firmware)
5. Stage 2 — cross-compile arm64 single image
6. Stage 3 — Gazebo Harmonic CI gate + drift detection
7. Stage 4 — Isaac Sim advanced validation
8. Stage 5 — run reports and artifact publish
9. Stage 6 — deploy to Jetson Orin Nano Super
10. ESP32 motor control — firmware and micro-ROS
11. Full GitHub Actions workflow file
Appendix A — drift detection implementation
Appendix B — run report schema


---

<!-- Page 3 -->
0. Hardware and software environment
JetPack 7.2 (released June 1, 2026) brings Ubuntu 24.04 LTS and kernel 6.8 to the entire Jetson Orin
family including Orin Nano Super. This means a single consistent stack across workstation and
rover — no OS or ROS2 distro mismatch.
Component
Specification
Notes
Workstation OS
Ubuntu 24.04 LTS (bare metal)
Direct boot, no VM
ROS2
Jazzy Jalisco
Same on workstation AND rover
CPU/RAM
96 GB RAM
Enables large Isaac Sim worlds
GPU
NVIDIA RTX 5080 16 GB
CUDA 13, Isaac Sim, TensorRT 10.16
Simulator A
Gazebo Harmonic
CI gate, headless, fast
Simulator B
Isaac Sim 4.x
GPU photorealistic, workstation
Rover chassis
Waveshare UGV Rover PT
6-wheel 4WD, 1.3 m/s, aluminum
Mission computer
Jetson Orin Nano Super
JetPack 7.2, Ubuntu 24.04, Jazzy
Jetson GPU stack
CUDA 13, cuDNN 9.20, TRT 10.16
Same generation as workstation
MCU
ESP32 (Waveshare sub-controller)
micro-ROS, UART 921600 baud
Lidar
D500 (included in PT kit)
10 Hz, /scan topic
Depth camera
OAK-D Lite (included in PT kit)
/camera/depth/points
Container reg.
ghcr.io
Single arm64 Jazzy image
JetPack 7.2 flashing: The Jetson Orin Nano Super ships with JetPack 6.x by default. Download the unified
ISO from developer.nvidia.com/embedded/jetpack/downloads and flash via USB stick. No SD card or
SDK Manager required. After flashing: Ubuntu 24.04, kernel 6.8, CUDA 13. Then install ROS2 Jazzy
natively via apt.
Motor control architecture: The ESP32 sub-controller owns all real-time loops. ROS2 on the Jetson
publishes geometry_msgs/Twist to /cmd_vel; the ESP32 receives this via micro-ROS UART at 921600 baud
using a JSON instruction set, translates to wheel velocities, and runs 1 kHz PID. Watchdog halts motors
after 200 ms of no command (MCU-02).


---

<!-- Page 4 -->
1. Requirements — scene, brain, and MCU firmware
Requirements written before any code become the backbone of the test suite and drift detection baseline.
This version adds MCU-level firmware requirements for the ESP32 sub-controller.
1.1 Scene requirements
Define the simulation world before writing a URDF
ID
Requirement
Acceptance test
SC-01
Flat indoor floor, 8m x 8m minimum
World SDF loads without error
SC-02
At least 4 static box obstacles, 0.3m tall
Costmap shows obstacles
SC-03
Defined start pose + 3 named goal poses
Nav2 goal accepted from all
SC-04
D500 lidar scan valid, no NaN/inf in all dirs Topic rate >= 10 Hz
SC-05
OAK-D Lite depth cloud valid at 1m-6m range
PCL not empty
SC-06
Ground friction 0.7 (concrete sim), no wheel slip
No slip at 0.5 m/s
SC-07
400 lux uniform lighting (Isaac Sim stage)
Camera exposure nominal
SC-08
Scene reproducible from fixed random seedTwo runs produce same costmap
1.2 Brain (autonomy) requirements
Define autonomy behavior before Nav2 config
ID
Requirement
Acceptance test
BR-01
Navigate to goal within 0.15m
Euclidean error < 0.15m
BR-02
Avoid obstacles with 0.25m clearance
No collision in 10 runs
BR-03
Recover from stuck state within 10 sec
Recovery behavior triggered
BR-04
Publish /odom at >= 50 Hz
Topic rate check in CI
BR-05
SLAM map converges within 60 sec
Map entropy threshold
BR-06
E-stop halts motion within 100 ms
Latency measured in sim
BR-07
Nav success rate regression <= 5%
Drift detection gate
BR-08
CPU usage on Jetson < 80% during nav
Profiling in smoke test
BR-09
Lidar-camera extrinsic error < 3 cm
Reprojection error check
BR-10
BT completes waypoint mission
BT returns SUCCESS


---

<!-- Page 5 -->
1.3 MCU / ESP32 firmware requirements
Define ESP32 behavior before writing firmware
These requirements cover the Waveshare UGV Rover PT's ESP32 sub-controller. They are tested via
PlatformIO Unity tests in Stage 1 and verified in the smoke test in Stage 6.
ID
Requirement
Acceptance test
MCU-01
PID control loop runs at 1 kHz, independent of ROS2
Loop timer assertion in firmware test
MCU-02
Watchdog: safe-stop if no cmd_vel for 200 ms
Unity test: timeout triggers zero velocity
MCU-03
Wheel encoder odometry published at >= 50 Hz
Topic rate check (BR-04)
MCU-04
IMU data published at >= 200 Hz
Topic rate check
MCU-05
Max motor current limit enforced in firmwareUnity test: overcurrent triggers limit
MCU-06
UART JSON instruction set at 921600 baudRound-trip latency < 5 ms
1.4 Traceability matrix
# 
requirements/traceability.yaml 
tests: 
test_waypoint_arrival: 
covers: 
[BR-01]
test_obstacle_avoidance: covers: [BR-02, SC-02] test_odom_rate: covers: [BR-04, MCU-03]
test_slam_convergence: covers: [BR-05, SC-08] test_estop_latency: covers: [BR-06, MCU-02]
test_drift_nav_success: 
covers: 
[BR-07] 
test_lidar_valid: 
covers: 
[SC-04]
test_camera_pointcloud: 
covers: 
[SC-05] 
test_mcu_pid_rate: 
covers: 
[MCU-01]
test_mcu_watchdog: covers: [MCU-02] test_mcu_current_limit: covers: [MCU-05]


---

<!-- Page 6 -->
2. Repository structure
rover_ws/ III .github/workflows/cicd.yml III requirements/ I III scene_requirements.yaml I
III brain_requirements.yaml I III mcu_requirements.yaml # NEW: ESP32 firmware reqs I III
traceability.yaml III src/ I III rover_description/ # URDF (from ugv_ws), SDF I III
rover_bringup/ # launch files (sim + real) I III rover_navigation/ # Nav2 config, BTs I III
rover_perception/ # camera, lidar, YOLO nodes I III rover_slam/ # slam_toolbox config I III
rover_control/ # /cmd_vel -> micro-ROS pub I III rover_tests/ # integration + drift tests
III firmware/ I III esp32_motor_control/ # PlatformIO project I III platformio.ini I III
src/main.cpp # PID, watchdog, micro-ROS I III test/ # Unity tests (native env) III docker/ I
III Dockerfile.ros2 # Ubuntu 24.04, Jazzy, arm64 I III docker-compose.yml III simulation/ I
III gazebo/ # world SDF, models I III isaac/ # USD scenes, scripts III reports/history/ #
drift 
archive 
(gitignored 
build) 
III 
scripts/ 
III 
check_traceability.py 
III
drift_detector.py III report_generator.py


---

<!-- Page 7 -->
3. Stage 0 — requirements gate
Runs first on every PR, < 5 seconds
Validates the traceability matrix. Every requirement (BR, SC, MCU) must have at least one test mapped to it.
Orphan requirements fail the pipeline immediately.
- 
name: 
Validate 
requirements 
traceability 
run: 
| 
pip 
install 
pyyaml 
python
scripts/check_traceability.py 
\ 
--req 
requirements/scene_requirements.yaml 
\ 
--req
requirements/brain_requirements.yaml \ --req requirements/mcu_requirements.yaml \ --trace
requirements/traceability.yaml


---

<!-- Page 8 -->
4. Stage 1 — code quality (ROS2 + ESP32 firmware)
Lint, static analysis, unit tests — ROS2 Jazzy + PlatformIO
4.1 ROS2 Jazzy linting (Ubuntu 24.04)
# 
package.xml 
ament_lint_auto 
ament_lint_common 
# 
CMakeLists.txt 
if(BUILD_TESTING)
find_package(ament_lint_auto REQUIRED) ament_lint_auto_find_test_dependencies() endif()
4.2 ESP32 firmware tests — PlatformIO + Unity
The ESP32 firmware is tested in a native PlatformIO environment — no physical hardware needed. Unity
test framework runs on the CI host (x86_64) to verify PID logic, watchdog, and JSON parsing.
# firmware/esp32_motor_control/platformio.ini [env:native] platform = native test_framework =
unity build_flags = -DUNIT_TEST # GitHub Actions step: - name: ESP32 firmware tests run: | cd
firmware/esp32_motor_control pip install platformio --break-system-packages pio test -e native
--verbose
// 
firmware/test/test_watchdog.cpp 
void 
test_watchdog_triggers_after_200ms(void) 
{
last_cmd_ms = millis() - 201; run_watchdog(); TEST_ASSERT_EQUAL(0, motor_left_setpoint); //
MCU-02 TEST_ASSERT_EQUAL(0, motor_right_setpoint); } void test_current_limit_enforced(void) {
set_motor_current(5.0f); 
// 
over 
limit 
TEST_ASSERT_FLOAT_WITHIN(0.01f, 
MAX_CURRENT,
motor_current); // MCU-05 } void test_pid_output_within_bounds(void) { float out =
compute_pid(1.0f, 0.0f); // 1 m/s setpoint, 0 actual TEST_ASSERT_TRUE(out >= -MAX_PWM && out
<= MAX_PWM); // MCU-01 }


---

<!-- Page 9 -->
5. Stage 2 — cross-compile arm64 single image
Single ROS2 Jazzy arm64 image — workstation and rover identical OS stack
5.1 Dockerfile (Ubuntu 24.04 / Jazzy)
# docker/Dockerfile.ros2 FROM ros:jazzy-ros-base AS base # Ubuntu 24.04 RUN apt-get update &&
apt-get 
install 
-y 
\ 
ros-jazzy-nav2-bringup 
\ 
ros-jazzy-slam-toolbox 
\
ros-jazzy-micro-ros-agent 
\ 
ros-jazzy-vision-opencv 
\ 
ros-jazzy-rmw-cyclonedds-cpp 
\
python3-colcon-common-extensions \ && rm -rf /var/lib/apt/lists/* FROM base AS deps WORKDIR
/rover_ws COPY src/*/package.xml src/*/ RUN rosdep install --from-paths src --ignore-src -y
FROM deps AS build COPY src/ src/ RUN . /opt/ros/jazzy/setup.sh && \ colcon build --cmake-args
-DCMAKE_BUILD_TYPE=Release 
FROM 
base 
AS 
runtime 
COPY 
--from=build 
/rover_ws/install
/rover_ws/install 
ENV 
RMW_IMPLEMENTATION=rmw_cyclonedds_cpp 
COPY 
docker/entrypoint.sh
/entrypoint.sh RUN chmod +x /entrypoint.sh ENTRYPOINT ["/entrypoint.sh"]
5.2 GitHub Actions cross-compile
- 
uses: 
docker/setup-qemu-action@v3 
- 
uses: 
docker/setup-buildx-action@v3 
- 
uses:
docker/build-push-action@v5 with: platforms: linux/arm64 push: false cache-from: type=gha
cache-to: type=gha,mode=max file: docker/Dockerfile.ros2 build-args: | ROS_DISTRO=jazzy
UBUNTU_VERSION=24.04 tags: ghcr.io/${{ github.repository }}:${{ github.sha }}
v2: Single image. No Humble/Jazzy split. No DDS bridge. JetPack 7.2 on the Jetson Orin Nano Super
runs Ubuntu 24.04 + Jazzy natively, exactly matching the Docker base image.


---

<!-- Page 10 -->
6. Stage 3 — Gazebo Harmonic CI gate + drift detection
Headless simulation — primary gate before Isaac Sim or deploy
6.1 URDF starting point
Use the Waveshare open-source ugv_ws repository as the URDF/SDF starting point. It ships with a Gazebo
world and ROS2 launch files for the UGV Rover. Adapt for Jazzy and Gazebo Harmonic.
git clone https://github.com/waveshareteam/ugv_ws # Adapt for ROS2 Jazzy + Gazebo Harmonic: #
- Update CMakeLists to ament_cmake # - Replace gazebo_ros plugins with gz_ros2_control # -
Verify TF tree: base_link -> lidar_link -> camera_link
6.2 Nav2 integration test
class 
NavIntegrationTest(unittest.TestCase): 
def 
test_goal_arrival(self): 
goal 
=
NavigateToPose.Goal() goal.pose.pose.position.x = 3.0 self.client.send_goal_async(goal) #
Assert pose error < 0.15m (BR-01) # Assert /odom Hz >= 50 (BR-04, MCU-03) # Assert /scan Hz >=
10 (SC-04)
6.3 Drift detection metrics
* nav_success_rate — threshold: -5% (BR-07)
* odom_hz_mean — threshold: -5 Hz (BR-04,
MCU-03)
* mean_position_error — threshold: +3 cm (BR-01)
* lidar_hz_mean — threshold: -1 Hz (SC-04)
* mean_time_to_goal — threshold: +5 s
* camera_hz_mean — threshold: -1 Hz (SC-05)
* collision_rate — threshold: +2% (BR-02)
* firmware_test_pass_rate — threshold: -0% (MCU
all)


---

<!-- Page 11 -->
7. Stage 4 — Isaac Sim advanced validation
RTX 5080 workstation, Ubuntu 24.04, CUDA 13 — manual trigger
7.1 Install on Ubuntu 24.04
pip install isaacsim-rl isaacsim-replicator \ isaacsim-extscache-physics \ --extra-index-url
https://pypi.nvidia.com # Enable ROS2 Jazzy bridge in Isaac Sim UI: # Isaac Utils > ROS2
Bridge > Enable nvidia-smi # need driver >= 560, CUDA 13
v2: Ubuntu 24.04 on both workstation and Jetson means CUDA 13 / TensorRT 10.16 align between
development, simulation, and deployment. No library version mismatch between Isaac Sim and the
rover's inference stack.
7.2 USD scene — Waveshare UGV Rover
* Import UGV Rover URDF via Isaac URDF importer
* Multiple lighting rigs at 400 lux (SC-07)
* D500 lidar material preset
* Static obstacles matching SC-02
* OAK-D Lite RGB-D camera material
* Ground truth pose annotator
* PhysX physics, concrete friction (SC-06)
* Save as simulation/isaac/rover_scene.usd
7.3 Sim-to-real gap metrics
Metric
Target
Tool
D500 lidar point density< 5% difference at 5m
pcl_compare
OAK-D Lite depth RMSE< 3 cm at 2m range
Isaac annotator
SLAM trajectory RMSE< 0.05m over 10m route
evo_ape
Nav2 success rate
sim >= real minus 5%
drift_detector.py
Velocity profile RMSE < 0.1 m/s vs commanded
rosbag compare


---

<!-- Page 12 -->
8. Stage 5 — run reports and artifact publish
Single Jazzy arm64 image, HTML report, drift archive
8.1 Report JSON (key additions in v2)
{ "run_id": "sha-abc123", "rover_hw": "Waveshare UGV Rover PT", "jetson_stack": "JetPack 7.2 /
Ubuntu 24.04 / ROS2 Jazzy", "mcu": "ESP32 @ 921600 baud, JSON instruction set", "stages": {
"firmware_tests": { "status": "pass", "unity_passed": 12, "unity_failed": 0 }, "gazebo_sim": {
"nav_success_rate": 0.92, "odom_hz_mean": 51.2, "lidar_hz_mean": 10.1, "drift_status":
"clean" } }, "overall": "pass" }
8.2 Publish step
- uses: docker/build-push-action@v5 with: platforms: linux/arm64 push: true build-args: |
ROS_DISTRO=jazzy 
UBUNTU_VERSION=24.04 
tags: 
| 
ghcr.io/${{ 
github.repository 
}}:latest
ghcr.io/${{ github.repository }}:${{ github.sha }}


---

<!-- Page 13 -->
9. Stage 6 — deploy to Jetson Orin Nano Super
JetPack 7.2 / Ubuntu 24.04 / ROS2 Jazzy — same as workstation
9.1 One-time Jetson setup — JetPack 7.2
# 1. Download unified ISO from: # developer.nvidia.com/embedded/jetpack/downloads # 2. Flash
via USB stick (no SD card, no SDK Manager required) # 3. After flash: Ubuntu 24.04, kernel
6.8, CUDA 13 # 4. Install ROS2 Jazzy natively sudo apt install ros-jazzy-ros-base sudo apt
install ros-jazzy-micro-ros-agent # 5. Install Docker curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER # 6. Login to ghcr.io echo $GITHUB_TOKEN | docker login ghcr.io
-u $USER --password-stdin
9.2 docker-compose.yml on the Jetson
version: "3.9" services: ros2_stack: image: ghcr.io/youruser/rover_ws:latest network_mode:
host privileged: true devices: - /dev/ttyUSB0:/dev/ttyUSB0 # ESP32 UART environment: -
RMW_IMPLEMENTATION=rmw_cyclonedds_cpp 
- 
ROS_DOMAIN_ID=0 
command: 
> 
bash 
-c 
"source
/rover_ws/install/setup.bash && ros2 launch rover_bringup rover_real.launch.py" restart:
unless-stopped
9.3 Deploy + smoke test
# Deploy ssh -i /tmp/key jetson@$JETSON_HOST \ "docker pull ghcr.io/$REPO:latest && docker
compose -f ~/rover/docker-compose.yml up -d" # Smoke test sleep 15 ssh -i /tmp/key
jetson@$JETSON_HOST \ "source /opt/ros/jazzy/setup.bash && ros2 topic hz /odom --once && #
MCU-03: >= 50 Hz ros2 topic hz /scan --once && # SC-04: >= 10 Hz ros2 topic hz /imu/data
--once && # MCU-04: >= 100 Hz echo SMOKE_PASS" | grep SMOKE_PASS || rollback


---

<!-- Page 14 -->
10. ESP32 motor control — firmware and micro-ROS
Waveshare UGV Rover PT sub-controller — owns all real-time control
10.1 PlatformIO project structure
# firmware/esp32_motor_control/platformio.ini [env:esp32dev] platform = espressif32 board =
esp32dev framework = arduino lib_deps = micro_ros_arduino PID monitor_speed = 921600
[env:native] platform = native test_framework = unity build_flags = -DUNIT_TEST
10.2 Main control loop
// src/main.cpp #include #include rcl_subscription_t cmd_vel_sub; geometry_msgs__msg__Twist
cmd_vel_msg; uint32_t last_cmd_ms = 0; void cmd_vel_callback(const void* msg) { const auto*
twist 
= 
(const 
geometry_msgs__msg__Twist*)msg; 
last_cmd_ms 
= 
millis(); 
float 
v 
=
twist->linear.x; float w = twist->angular.z; // Differential drive kinematics (MCU-01) float
v_left = v - w * WHEEL_BASE / 2.0f; float v_right = v + w * WHEEL_BASE / 2.0f; // Clamp to max
speed (MCU-05 analog for velocity) v_left = constrain(v_left, -MAX_SPEED, MAX_SPEED); v_right
= constrain(v_right, -MAX_SPEED, MAX_SPEED); pid_left.Setpoint = v_left; pid_right.Setpoint =
v_right; } void loop() { // micro-ROS executor spin (1ms timeout = 1 kHz rate, MCU-01)
rclc_executor_spin_some(&executor;, RCL_MS_TO_NS(1)); // Watchdog: halt if no cmd_vel for
200ms (MCU-02) if (millis() - last_cmd_ms > WATCHDOG_MS) { pid_left.Setpoint = 0;
pid_right.Setpoint 
= 
0; 
} 
// 
PID 
compute 
and 
PWM 
write 
pid_left.Compute();
pid_right.Compute(); write_motor_pwm(left_output, right_output); // Publish odometry (MCU-03)
publish_odom(); }
10.3 micro-ROS agent on the Jetson
# Launch agent (baked into Docker entrypoint) ros2 run micro_ros_agent micro_ros_agent serial
\ --dev /dev/ttyUSB0 \ --baudrate 921600 \ --verbose 4 # Topics that appear on the ROS2 graph:
# /cmd_vel <- subscribed by ESP32 (Twist in) # /odom -> published by ESP32 (50 Hz, MCU-03) #
/imu/data -> published by ESP32 (200 Hz, MCU-04) # /motor_status -> published by ESP32
(current, temp, errors)


---

<!-- Page 15 -->
11. Full GitHub Actions workflow
# .github/workflows/cicd.yml name: ROS2 Rover CI/CD v2 on: push: branches: [main,
'feature/**', 
'release/**'] 
pull_request: 
branches: 
[main] 
workflow_dispatch: 
inputs:
run_isaac: description: 'Run Isaac Sim stage' type: boolean default: false env: REGISTRY:
ghcr.io IMAGE_NAME: ${{ github.repository }} jobs: requirements-gate: runs-on: ubuntu-24.04
steps: 
- 
uses: 
actions/checkout@v4 
- 
run: 
| 
pip 
install 
pyyaml 
python
scripts/check_traceability.py 
firmware-and-quality: 
needs: 
requirements-gate 
runs-on:
ubuntu-24.04 container: ros:jazzy # Ubuntu 24.04 steps: - uses: actions/checkout@v4 - name:
ESP32 firmware tests (PlatformIO native) run: | pip install platformio --break-system-packages
cd firmware/esp32_motor_control pio test -e native --verbose - name: ROS2 colcon build + lint
+ gtest run: | rosdep install --from-paths src --ignore-src -y colcon build --cmake-args
-DCMAKE_BUILD_TYPE=Release colcon test && colcon test-result --verbose cross-compile: needs:
firmware-and-quality runs-on: ubuntu-24.04 steps: - uses: actions/checkout@v4 - uses:
docker/setup-qemu-action@v3 
- 
uses: 
docker/setup-buildx-action@v3 
- 
uses:
docker/login-action@v3 with: registry: ghcr.io username: ${{ github.actor }} password: ${{
secrets.GITHUB_TOKEN }} - uses: docker/build-push-action@v5 with: platforms: linux/arm64 push:
false 
cache-from: 
type=gha 
cache-to: 
type=gha,mode=max 
file: 
docker/Dockerfile.ros2
build-args: | ROS_DISTRO=jazzy UBUNTU_VERSION=24.04 gazebo-sim: needs: cross-compile runs-on:
ubuntu-24.04 
container: 
image: 
ros:jazzy 
options: 
--privileged 
steps: 
- 
uses:
actions/checkout@v4 - run: apt-get install -y ros-jazzy-ros-gz gz-harmonic - run: | source
/opt/ros/jazzy/setup.bash 
colcon 
build 
ros2 
launch 
rover_bringup 
sim_test.launch.py
headless:=true 
- 
run: 
python 
scripts/drift_detector.py 
- 
run: 
python
scripts/report_generator.py - uses: actions/upload-artifact@v4 with: name: run-report-${{
github.sha }} path: reports/ publish: needs: gazebo-sim if: github.ref == 'refs/heads/main'
runs-on: ubuntu-24.04 steps: - uses: docker/build-push-action@v5 with: platforms: linux/arm64
push: true build-args: | ROS_DISTRO=jazzy UBUNTU_VERSION=24.04 tags: | ${{ env.REGISTRY }}/${{
env.IMAGE_NAME }}:latest ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:${{ github.sha }} deploy:
needs: publish if: github.ref == 'refs/heads/main' runs-on: ubuntu-24.04 environment:
rover-production steps: - name: Deploy + smoke test env: JETSON_HOST: ${{ secrets.JETSON_HOST
}} SSH_KEY: ${{ secrets.JETSON_SSH_KEY }} run: | echo "$SSH_KEY" > /tmp/key && chmod 600
/tmp/key ssh -i /tmp/key jetson@$JETSON_HOST \ "docker pull ${{ env.REGISTRY }}/${{
env.IMAGE_NAME }}:latest && docker compose -f ~/rover/docker-compose.yml up -d" sleep 15 ssh
-i /tmp/key jetson@$JETSON_HOST \ "source /opt/ros/jazzy/setup.bash && ros2 topic hz /odom
--once && ros2 topic hz /scan --once && ros2 topic hz /imu/data --once && echo SMOKE_PASS" |
grep SMOKE_PASS || exit 1


---

<!-- Page 16 -->
Appendix A — drift detection in detail
Metric
Fail direction
Threshold
Req
nav_success_rate
decrease > 5%
0.05
BR-07
mean_position_error
increase > 3 cm
0.03m
BR-01
mean_time_to_goal
increase > 5 s
5.0s
BR-01
collision_rate
increase > 2%
0.02
BR-02
odom_hz_mean
decrease > 5 Hz
5 Hz
BR-04, MCU-03
lidar_hz_mean
decrease > 1 Hz
1 Hz
SC-04
firmware_test_pass
any failure
100%
MCU all
# scripts/drift_detector.py THRESHOLDS = { "nav_success_rate": {"dir":"down", "delta":0.05},
"mean_position_error": 
{"dir":"up", 
"delta":0.03}, 
"mean_time_to_goal": 
{"dir":"up",
"delta":5.0}, "collision_rate": {"dir":"up", "delta":0.02}, "odom_hz_mean": {"dir":"down",
"delta":5.0}, 
"lidar_hz_mean": 
{"dir":"down", 
"delta":1.0}, 
"firmware_test_pass_rate":
{"dir":"down", 
"delta":0.001}, 
} 
history 
= 
load_history(n=5) 
current 
=
json.load(open("reports/current_run.json")) 
failures 
=
detect_drift(current["stages"]["gazebo_sim"], history) if failures: for f in failures:
print("DRIFT:", f) sys.exit(1)


---

<!-- Page 17 -->
Appendix B — run report schema
{ "run_id": "string — git SHA", "timestamp": "ISO 8601", "branch": "string", "rover_hw":
"Waveshare UGV Rover PT", "jetson_stack": "JetPack 7.2 / Ubuntu 24.04 / ROS2 Jazzy", "mcu":
"ESP32 
@ 
921600 
baud", 
"stages": 
{ 
"requirements": 
{"status":"pass|fail",
"uncovered_reqs":[]}, 
"firmware_tests": 
{"status":"pass|fail", 
"unity_passed":0,
"unity_failed":0}, "code_quality": {"status":"pass|fail", "lint_warnings":0, "test_count":0},
"cross_compile": 
{"status":"pass|fail", 
"image_size_mb":0, 
"ros_distro":"jazzy"},
"gazebo_sim": { "status": "pass|fail", "nav_success_rate": 0.0, "mean_position_error": 0.0,
"mean_time_to_goal": 0.0, "collision_rate": 0.0, "odom_hz_mean": 0.0, "lidar_hz_mean": 0.0,
"camera_hz_mean": 0.0, "firmware_test_pass_rate":0.0, "drift_status": "clean|drift_detected",
"drift_details": 
[] 
}, 
"isaac_sim": 
{ 
"status": 
"pass|fail|skip", 
"yolo_map": 
0.0,
"lidar_density_5m": 0, "depth_rmse_m": 0.0, "sim_to_real_trajectory_rmse": 0.0 }, "publish":
{"status":"pass|fail|skip", 
"image_tag":"string"}, 
"deploy": 
{"status":"pass|fail|skip",
"smoke_test":"pass|fail"} }, "overall": "pass|fail" }
End of document. All code samples are illustrative starting points. JetPack 7.2 was released June 1, 2026 and is the
recommended base for new Jetson Orin projects.
