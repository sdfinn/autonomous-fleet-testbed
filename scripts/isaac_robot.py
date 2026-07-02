"""
Isaac Sim 6.0 — spawn ugv_pt with ROS2 odom + scan topics.

Architecture:
  Odom: OmniGraph (IsaacComputeOdometry → ROS2PublishOdometry)  ~90 Hz
  Scan: RotatingLidarPhysX → rclpy publisher                   ~10 Hz
        (RTX lidar has no sensor-specific render product in headless mode;
         PhysX raycasting works natively without a render product)

Prim layout after URDF import:
  /ugv_pt                                                    Articulation root
  /ugv_pt/Geometry/base_footprint/base_link/lidar_link       lidar mount
  /ugv_pt/Geometry/base_footprint/base_link/lidar_link/Lidar RotatingLidarPhysX prim

ROS2 topics published:
  /clock              — sim time
  /robot_001/odom     — odometry   (~90 Hz)
  /robot_001/tf       — odom → base_footprint
  /robot_001/scan     — LaserScan  (~10 Hz)

Usage:
  source ~/isaac-env/bin/activate
  source /opt/ros/jazzy/setup.bash
  OMNI_KIT_ACCEPT_EULA=YES python scripts/isaac_robot.py
"""
import os
import pathlib
import math

os.environ["OMNI_KIT_ACCEPT_EULA"] = "YES"

from isaacsim import SimulationApp

simulation_app = SimulationApp({"headless": True, "renderer": "RayTracedLighting"})

import omni.graph.core as og
import omni.timeline
import omni.usd
from pxr import Sdf, Gf
from isaacsim.core.utils.extensions import enable_extension
from isaacsim.asset.importer.urdf import URDFImporter, URDFImporterConfig
from isaacsim.sensors.physx import RotatingLidarPhysX
import isaacsim.core.utils.stage as stage_utils

enable_extension("isaacsim.ros2.bridge")
enable_extension("isaacsim.asset.importer.urdf")
enable_extension("isaacsim.sensors.physx")
simulation_app.update()

# ── URDF import ───────────────────────────────────────────────────────────────
REPO_ROOT = pathlib.Path(__file__).parent.parent
URDF_PATH = str(REPO_ROOT / "src/nav_fleet/urdf/ugv_pt.urdf")
USD_PATH  = "/tmp/isaac_ugv_pt.usd"  # outside repo — avoids versioned dir accumulation
NS        = "robot_001"

ARTIC_ROOT      = "/ugv_pt"
LIDAR_LINK_PRIM = "/ugv_pt/Geometry/base_footprint/base_link/lidar_link"
LIDAR_PRIM      = f"{LIDAR_LINK_PRIM}/Lidar"

print(f"[Isaac] Importing URDF: {URDF_PATH}")
cfg = URDFImporterConfig(
    urdf_path=URDF_PATH,
    usd_path=USD_PATH,
    merge_fixed_joints=False,
    fix_base=False,
    joint_drive_type="velocity",
)
output_path = URDFImporter(cfg).import_urdf()
print(f"[Isaac] Imported → {output_path}")
stage_utils.open_stage(output_path)
simulation_app.update()

# ── Physics lidar ─────────────────────────────────────────────────────────────
print("[Isaac] Creating RotatingLidarPhysX...")
lidar = RotatingLidarPhysX(
    prim_path=LIDAR_PRIM,
    rotation_frequency=10.0,      # 10 Hz full rotation → ~10 Hz scan topic
    fov=(360.0, 1.0),             # 360° horizontal, 1° vertical slice
    resolution=(0.4, 1.0),        # 0.4° angular resolution → 900 rays/scan
    valid_range=(0.12, 12.0),     # matches nav2_params: laser_min_range/max_range
)
lidar.add_linear_depth_data_to_frame()
print(f"[Isaac] Lidar created at {LIDAR_PRIM}")
simulation_app.update()

# ── OmniGraph — Odom ─────────────────────────────────────────────────────────
print("[Isaac] Wiring odom OmniGraph...")
keys = og.Controller.Keys

og.Controller.edit(
    {"graph_path": f"{ARTIC_ROOT}/ros2_odom", "evaluator_name": "execution"},
    {
        keys.CREATE_NODES: [
            ("OnTick",        "omni.graph.action.OnPlaybackTick"),
            ("SimTime",       "isaacsim.core.nodes.IsaacReadSimulationTime"),
            ("Context",       "isaacsim.ros2.bridge.ROS2Context"),
            ("ComputeOdom",   "isaacsim.core.nodes.IsaacComputeOdometry"),
            ("PublishOdom",   "isaacsim.ros2.bridge.ROS2PublishOdometry"),
            ("PublishTF",     "isaacsim.ros2.bridge.ROS2PublishRawTransformTree"),
            ("PublishClock",  "isaacsim.ros2.bridge.ROS2PublishClock"),
        ],
        keys.SET_VALUES: [
            ("ComputeOdom.inputs:chassisPrim",     [Sdf.Path(ARTIC_ROOT)]),
            ("PublishOdom.inputs:topicName",       f"/{NS}/odom"),
            ("PublishOdom.inputs:odomFrameId",     "odom"),
            ("PublishOdom.inputs:chassisFrameId",  "base_footprint"),
            ("PublishTF.inputs:topicName",          f"/{NS}/tf"),
            ("PublishTF.inputs:childFrameId",      "base_footprint"),
            ("PublishTF.inputs:parentFrameId",     "odom"),
            ("Context.inputs:domain_id",           0),
        ],
        keys.CONNECT: [
            ("OnTick.outputs:tick",                "ComputeOdom.inputs:execIn"),
            ("ComputeOdom.outputs:execOut",        "PublishOdom.inputs:execIn"),
            ("ComputeOdom.outputs:position",       "PublishOdom.inputs:position"),
            ("ComputeOdom.outputs:orientation",    "PublishOdom.inputs:orientation"),
            ("ComputeOdom.outputs:linearVelocity", "PublishOdom.inputs:linearVelocity"),
            ("ComputeOdom.outputs:angularVelocity","PublishOdom.inputs:angularVelocity"),
            ("SimTime.outputs:simulationTime",     "PublishOdom.inputs:timeStamp"),
            ("Context.outputs:context",            "PublishOdom.inputs:context"),
            ("OnTick.outputs:tick",                "PublishTF.inputs:execIn"),
            ("ComputeOdom.outputs:position",       "PublishTF.inputs:translation"),
            ("ComputeOdom.outputs:orientation",    "PublishTF.inputs:rotation"),
            ("SimTime.outputs:simulationTime",     "PublishTF.inputs:timeStamp"),
            ("Context.outputs:context",            "PublishTF.inputs:context"),
            ("OnTick.outputs:tick",                "PublishClock.inputs:execIn"),
            ("SimTime.outputs:simulationTime",     "PublishClock.inputs:timeStamp"),
            ("Context.outputs:context",            "PublishClock.inputs:context"),
        ],
    },
)

# ── ROS2 scan publisher (rclpy, driven by lidar frame callback) ───────────────
print("[Isaac] Setting up rclpy scan publisher...")
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import LaserScan
from builtin_interfaces.msg import Time as RosTime
import numpy as np

rclpy.init()
scan_node = Node("isaac_scan_publisher")
scan_pub  = scan_node.create_publisher(LaserScan, f"/{NS}/scan", 10)

NUM_RAYS         = 900            # 360° / 0.4° resolution
ANGLE_INCREMENT  = math.radians(0.4)

# ── Run simulation ─────────────────────────────────────────────────────────────
print("[Isaac] Starting playback...")
omni.timeline.get_timeline_interface().play()
lidar.initialize()

print("[Isaac] Publishing /robot_001/odom and /robot_001/scan for 60 seconds...")
scan_step = 0
for i in range(600):
    simulation_app.update()

    # Publish scan at ~10 Hz (every 6 steps at ~60 fps)
    if i % 6 == 0:
        frame = lidar.get_current_frame()
        if frame and "linear_depth" in frame:
            depth = frame["linear_depth"].flatten()
            msg = LaserScan()
            t_sim = omni.timeline.get_timeline_interface().get_current_time()
            msg.header.stamp    = RosTime(sec=int(t_sim), nanosec=int((t_sim % 1) * 1e9))
            msg.header.frame_id = "lidar_link"
            msg.angle_min       = -math.pi
            msg.angle_max       =  math.pi
            msg.angle_increment = ANGLE_INCREMENT
            msg.time_increment  = 0.0
            msg.scan_time       = 1.0 / 10.0
            msg.range_min       = 0.12
            msg.range_max       = 12.0
            msg.ranges          = depth.tolist()
            scan_pub.publish(msg)
            scan_step += 1

    if i % 100 == 0:
        print(f"[Isaac] Step {i}/600  scans_published={scan_step}")

print(f"[Isaac] Done. Published {scan_step} scan messages.")
rclpy.shutdown()
simulation_app.close()
