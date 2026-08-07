# arm64 ROS2 Jazzy nav_fleet build — built natively on the Jetson runner (stage-3-arm64).
# THE brain: EKF + ball_detector + Nav2 bringup + mission_runner, run identically by
# HIL (tools/mission2_day.py's JetsonExecutor) and the real robot
# (scripts/robot_boot.sh) via scripts/container_entrypoint.sh — see
# docs/superpowers/specs/2026-08-03-docker-brain-real-robot-hil-unification-design.md.
FROM ros:jazzy-ros-base

SHELL ["/bin/bash", "-c"]

# System deps. ros-jazzy-robot-localization added 2026-08 (docker-brain unification):
# EKF now runs inside this image — previously only ever installed on bare hosts.
RUN apt-get update && apt-get install -y \
    python3-pip \
    python3-serial \
    ros-jazzy-navigation2 \
    ros-jazzy-nav2-bringup \
    ros-jazzy-rmw-cyclonedds-cpp \
    ros-jazzy-vision-msgs \
    ros-jazzy-robot-localization \
    && rm -rf /var/lib/apt/lists/*

# Python deps (CI-safe subset — not the full venv pip freeze)
COPY requirements-ci.txt /tmp/requirements-ci.txt
RUN pip3 install --no-cache-dir --break-system-packages --ignore-installed -r /tmp/requirements-ci.txt

# DDS
ENV RMW_IMPLEMENTATION=rmw_cyclonedds_cpp

# Copy workspace source
WORKDIR /ros2_ws
COPY src/ src/

# tools/ is imported by nav_fleet.mission_runner (telemetry_logger) — required to run
# the mission executor inside this image.
COPY tools/ tools/

# robot_profiles/ is tools/smoke_test.py's DEFAULT_PROFILE source (2026-08-06 smoke-
# test plan) — REPO_DIR resolves to /ros2_ws inside this image, so without this COPY
# `ROBOT_MODE=smoke_test` crashes immediately with FileNotFoundError on every run.
COPY robot_profiles/ robot_profiles/

# Entrypoint + the DDS-interface-regeneration script it calls — same script every bare
# process (hil_stage.sh, robot_boot.sh) already uses, so the container gets the exact
# same interface-selection behavior.
COPY scripts/container_entrypoint.sh scripts/regen_cyclonedds_config.sh scripts/
RUN chmod +x scripts/container_entrypoint.sh scripts/regen_cyclonedds_config.sh

# Build colcon package.
# NOT --symlink-install here (unlike the Tier-1 x86/Jetson dev loop): symlink-install's
# nav_fleet PYTHONPATH hook (pythonpath_develop.sh) lives under build/, which the next
# `rm -rf build/` deletes — leaving `source install/setup.bash` unable to put nav_fleet on
# PYTHONPATH inside the image. A plain install copies the package into install/ so
# build/ is safe to drop.
RUN source /opt/ros/jazzy/setup.bash && \
    colcon build \
    && rm -rf build/ log/

# Source on container start
RUN echo "source /opt/ros/jazzy/setup.bash" >> /root/.bashrc && \
    echo "source /ros2_ws/install/setup.bash" >> /root/.bashrc

CMD ["/bin/bash"]
