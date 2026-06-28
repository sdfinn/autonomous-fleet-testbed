# arm64 ROS2 Jazzy nav_fleet build
# Used by Stage 2 CI: QEMU on GHA ubuntu-latest, native arm64 on Jetson runner (Phase B)
FROM ros:jazzy-ros-base

SHELL ["/bin/bash", "-c"]

# System deps
RUN apt-get update && apt-get install -y \
    python3-pip \
    ros-jazzy-navigation2 \
    ros-jazzy-nav2-bringup \
    ros-jazzy-rmw-cyclonedds-cpp \
    && rm -rf /var/lib/apt/lists/*

# Python deps (CI-safe subset — not the full venv pip freeze)
COPY requirements-ci.txt /tmp/requirements-ci.txt
RUN pip3 install --no-cache-dir --break-system-packages -r /tmp/requirements-ci.txt

# DDS
ENV RMW_IMPLEMENTATION=rmw_cyclonedds_cpp

# Copy workspace source
WORKDIR /ros2_ws
COPY src/ src/

# Build colcon package
RUN source /opt/ros/jazzy/setup.bash && \
    colcon build --symlink-install \
    && rm -rf build/ log/

# Source on container start
RUN echo "source /opt/ros/jazzy/setup.bash" >> /root/.bashrc && \
    echo "source /ros2_ws/install/setup.bash" >> /root/.bashrc

CMD ["/bin/bash"]
