"""
Isaac Sim 6.0 headless startup with ROS2 Jazzy bridge.

Usage:
    source ~/isaac-env/bin/activate
    source /opt/ros/jazzy/setup.bash
    OMNI_KIT_ACCEPT_EULA=YES python scripts/isaac_ros2_bridge.py

Topics published after startup (verify with: ros2 topic list):
    /clock
    /robot_001/odom
    /robot_001/scan
    /robot_001/tf

Session 11 CI job runs this script, then checks topic Hz.
"""
import os
os.environ["OMNI_KIT_ACCEPT_EULA"] = "YES"

from isaacsim import SimulationApp

simulation_app = SimulationApp({"headless": True, "renderer": "RayTracedLighting"})

# Isaac Sim 6.0: extension name changed from omni.isaac.ros2_bridge → isaacsim.ros2.bridge
from isaacsim.core.utils.extensions import enable_extension
enable_extension("isaacsim.ros2.bridge")

print("[Isaac] ROS2 Jazzy bridge enabled. Spinning for 60 seconds...")
for i in range(600):   # 600 steps × ~0.1s = ~60s
    simulation_app.update()
    if i % 100 == 0:
        print(f"[Isaac] Step {i}/600")

print("[Isaac] Done.")
simulation_app.close()
