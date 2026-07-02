"""
Isaac Sim 6.0 — GUI bedroom world with ugv_pt robot + Nav2 drive loop.

What this script does:
  - Opens Isaac Sim in GUI mode showing the bedroom world (matching bedroom_simple.sdf)
  - Spawns ugv_pt at (-1.276, 1.2, 0.15) facing north — same as Gazebo Session 10
  - Green goal sphere at (0.0, 3.7, 0.04)
  - Publishes: /robot_001/odom, /robot_001/scan, /robot_001/tf, /clock
  - Subscribes: /robot_001/cmd_vel → DifferentialController → wheel joint velocities
  - Runs until the GUI window is closed (or Ctrl+C)

Run sequence (3 terminals):
  Terminal 1 — Isaac Sim GUI (start first, wait for "Simulation running" message):
    source ~/isaac-env/bin/activate && source /opt/ros/jazzy/setup.bash
    OMNI_KIT_ACCEPT_EULA=YES python scripts/isaac_bedroom_gui.py

  Terminal 2 — Nav2 (start once Terminal 1 shows "Simulation running"):
    source install/setup.bash
    ros2 launch src/nav_fleet/launch/nav2_isaac_launch.py

  Terminal 3 — Tests (wait until Nav2 shows "Activating ... active"):
    source install/setup.bash
    python -m pytest tests/test_navigation.py -v

Wheel geometry (ugv_pt.urdf.xacro):
  wheel_radius = 0.05 m   wheel_separation = 0.28 m
  DOF order: [rear_left, rear_right, front_left, front_right]
"""
import os
import math
import pathlib
import threading

os.environ["OMNI_KIT_ACCEPT_EULA"] = "YES"

from isaacsim import SimulationApp

# GUI mode — omit headless
simulation_app = SimulationApp({"renderer": "RayTracedLighting"})

import omni.graph.core as og
import omni.timeline
import omni.usd
import numpy as np
from pxr import UsdGeom, UsdPhysics, PhysxSchema, Gf, Vt, Sdf
from isaacsim.core.utils.extensions import enable_extension
from isaacsim.asset.importer.urdf import URDFImporter, URDFImporterConfig
from isaacsim.sensors.physx import RotatingLidarPhysX
from isaacsim.core.prims import Articulation
from isaacsim.core.utils.types import ArticulationAction
from isaacsim.robot.wheeled_robots import DifferentialController
import isaacsim.core.utils.stage as stage_utils

enable_extension("isaacsim.ros2.bridge")
enable_extension("isaacsim.asset.importer.urdf")
enable_extension("isaacsim.sensors.physx")
simulation_app.update()

# ── Config ────────────────────────────────────────────────────────────────────
REPO_ROOT       = pathlib.Path(__file__).parent.parent
URDF_PATH       = str(REPO_ROOT / "src/nav_fleet/urdf/ugv_pt.urdf")
USD_PATH        = "/tmp/isaac_bedroom_gui.usd"
NS              = "robot_001"

ARTIC_ROOT      = "/ugv_pt"
LIDAR_LINK_PRIM = "/ugv_pt/Geometry/base_footprint/base_link/lidar_link"
LIDAR_PRIM      = f"{LIDAR_LINK_PRIM}/Lidar"

WHEEL_RADIUS    = 0.05
WHEEL_BASE      = 0.28

SPAWN_X, SPAWN_Y, SPAWN_Z = -1.276, 1.2, 0.15
SPAWN_YAW = math.pi / 2   # facing north (+Y)

# ── Import URDF → use as base stage ──────────────────────────────────────────
print("[Isaac] Importing ugv_pt URDF...")
cfg = URDFImporterConfig(
    urdf_path=URDF_PATH,
    usd_path=USD_PATH,
    merge_fixed_joints=False,
    fix_base=False,
    joint_drive_type="velocity",
)
output_path = URDFImporter(cfg).import_urdf()
print(f"[Isaac] Imported → {output_path}")

# Open the robot USD as the active stage, then add bedroom geometry to it
stage_utils.open_stage(output_path)
simulation_app.update()
stage = omni.usd.get_context().get_stage()

# ── Physics scene ─────────────────────────────────────────────────────────────
scene_prim = stage.DefinePrim("/World/PhysicsScene", "PhysicsScene")
UsdPhysics.Scene(scene_prim).GetGravityDirectionAttr().Set(Gf.Vec3f(0, 0, -1))
UsdPhysics.Scene(scene_prim).GetGravityMagnitudeAttr().Set(9.81)
PhysxSchema.PhysxSceneAPI.Apply(scene_prim)

# Ground plane (invisible collision surface at z=0)
gp_xform = stage.DefinePrim("/World/GroundPlane", "Xform")
gp_plane = stage.DefinePrim("/World/GroundPlane/CollisionPlane", "Plane")
UsdPhysics.CollisionAPI.Apply(gp_plane)

# ── Bedroom geometry ──────────────────────────────────────────────────────────
print("[Isaac] Building bedroom world...")

def add_box(path, pos_xyz, dims_xyz, color=(0.75, 0.75, 0.75)):
    """Add a static textured box with physics collision."""
    xform = stage.DefinePrim(path, "Xform")
    UsdGeom.Xformable(xform).AddTranslateOp().Set(Gf.Vec3d(*pos_xyz))
    cube = UsdGeom.Cube.Define(stage, path + "/cube")
    cube.GetSizeAttr().Set(1.0)
    UsdGeom.Xformable(cube.GetPrim()).AddScaleOp().Set(Gf.Vec3f(*dims_xyz))
    cube.GetPrim().GetAttribute("primvars:displayColor").Set(
        Vt.Vec3fArray([Gf.Vec3f(*color)])
    )
    UsdPhysics.CollisionAPI.Apply(cube.GetPrim())

# Walls — exact coordinates from bedroom_simple.sdf
add_box("/World/Hallway_West",    [-2.6435, 1.6740, 0.5],  [0.050, 1.381, 1.0])
add_box("/World/Hallway_East",    [ 1.2805, 1.6930, 0.5],  [0.050, 1.507, 1.0])
add_box("/World/Hallway_South_W", [-2.2747, 0.9584, 0.5],  [1.016, 0.050, 1.0])
add_box("/World/Hallway_South_E", [ 0.2863, 0.9138, 0.5],  [2.140, 0.050, 1.0])
add_box("/World/Wall_South_W",    [-1.9686, 2.3887, 0.5],  [1.274, 0.050, 1.0])
add_box("/World/Wall_South_E",    [ 0.4914, 2.4706, 0.5],  [2.217, 0.050, 1.0])
add_box("/World/Wall_North",      [ 0.0760, 6.5020, 0.5],  [3.148, 0.050, 1.0])
add_box("/World/Wall_East",       [ 1.6250, 4.4699, 0.5],  [0.050, 4.000, 1.0])
add_box("/World/Wall_West",       [-1.4730, 4.4960, 0.5],  [0.050, 3.962, 1.0])
# Furniture
add_box("/World/Dresser",  [0.0074, 2.7583, 0.40], [0.813, 0.457, 0.80], (0.55, 0.35, 0.15))
add_box("/World/Bed",      [0.8130, 5.4360, 0.25], [1.524, 2.032, 0.50], (0.30, 0.45, 0.70))
add_box("/World/Desk",     [-0.9590, 5.3240, 0.375],[0.762, 1.524, 0.75], (0.60, 0.45, 0.25))
add_box("/World/PC_Tower", [-1.0360, 4.2050, 0.25], [0.559, 0.508, 0.50], (0.20, 0.20, 0.20))

# Green goal sphere — visual only, no collision
sphere = UsdGeom.Sphere.Define(stage, "/World/goal_marker")
sphere.GetRadiusAttr().Set(0.0381)
UsdGeom.Xformable(sphere.GetPrim()).AddTranslateOp().Set(Gf.Vec3d(0.0, 3.7, 0.0381))
sphere.GetPrim().GetAttribute("primvars:displayColor").Set(
    Vt.Vec3fArray([Gf.Vec3f(0.0, 0.9, 0.0)])
)

simulation_app.update()
print("[Isaac] Bedroom world built.")

# ── Robot spawn position ───────────────────────────────────────────────────────
robot_prim = stage.GetPrimAtPath(ARTIC_ROOT)
if robot_prim and robot_prim.IsValid():
    xf = UsdGeom.Xformable(robot_prim)
    xf.ClearXformOpOrder()
    xf.AddTranslateOp().Set(Gf.Vec3d(SPAWN_X, SPAWN_Y, SPAWN_Z))
    w = math.cos(SPAWN_YAW / 2)
    z = math.sin(SPAWN_YAW / 2)
    xf.AddOrientOp().Set(Gf.Quatd(w, 0.0, 0.0, z))
    print(f"[Isaac] Robot placed at ({SPAWN_X}, {SPAWN_Y}, {SPAWN_Z}), yaw=90°")
else:
    print(f"[Isaac] WARNING: robot prim {ARTIC_ROOT} not found after stage open")

simulation_app.update()

# ── Physics lidar ─────────────────────────────────────────────────────────────
print("[Isaac] Creating RotatingLidarPhysX...")
lidar = RotatingLidarPhysX(
    prim_path=LIDAR_PRIM,
    rotation_frequency=10.0,
    fov=(360.0, 1.0),
    resolution=(0.4, 1.0),
    valid_range=(0.12, 12.0),
)
lidar.add_linear_depth_data_to_frame()
simulation_app.update()

# ── OmniGraph — Odom + TF publishing ─────────────────────────────────────────
print("[Isaac] Wiring odom/TF OmniGraph...")
keys = og.Controller.Keys
og.Controller.edit(
    {"graph_path": f"{ARTIC_ROOT}/ros2_odom", "evaluator_name": "execution"},
    {
        keys.CREATE_NODES: [
            ("OnTick",      "omni.graph.action.OnPlaybackTick"),
            ("SimTime",     "isaacsim.core.nodes.IsaacReadSimulationTime"),
            ("Context",     "isaacsim.ros2.bridge.ROS2Context"),
            ("ComputeOdom", "isaacsim.core.nodes.IsaacComputeOdometry"),
            ("PublishOdom", "isaacsim.ros2.bridge.ROS2PublishOdometry"),
            ("PublishTF",   "isaacsim.ros2.bridge.ROS2PublishRawTransformTree"),
        ],
        keys.SET_VALUES: [
            ("ComputeOdom.inputs:chassisPrim",      [Sdf.Path(ARTIC_ROOT)]),
            ("PublishOdom.inputs:topicName",        f"/{NS}/odom"),
            ("PublishOdom.inputs:odomFrameId",      "odom"),
            ("PublishOdom.inputs:chassisFrameId",   "base_footprint"),
            ("PublishTF.inputs:childFrameId",       "base_footprint"),
            ("PublishTF.inputs:parentFrameId",      "odom"),
            ("Context.inputs:domain_id",            0),
        ],
        keys.CONNECT: [
            ("OnTick.outputs:tick",                  "ComputeOdom.inputs:execIn"),
            ("ComputeOdom.outputs:execOut",          "PublishOdom.inputs:execIn"),
            ("ComputeOdom.outputs:position",         "PublishOdom.inputs:position"),
            ("ComputeOdom.outputs:orientation",      "PublishOdom.inputs:orientation"),
            ("ComputeOdom.outputs:linearVelocity",   "PublishOdom.inputs:linearVelocity"),
            ("ComputeOdom.outputs:angularVelocity",  "PublishOdom.inputs:angularVelocity"),
            ("SimTime.outputs:simulationTime",       "PublishOdom.inputs:timeStamp"),
            ("Context.outputs:context",              "PublishOdom.inputs:context"),
            ("OnTick.outputs:tick",                  "PublishTF.inputs:execIn"),
            ("ComputeOdom.outputs:position",         "PublishTF.inputs:translation"),
            ("ComputeOdom.outputs:orientation",      "PublishTF.inputs:rotation"),
            ("SimTime.outputs:simulationTime",       "PublishTF.inputs:timeStamp"),
            ("Context.outputs:context",              "PublishTF.inputs:context"),
        ],
    },
)

# ── ROS2 scan publisher + cmd_vel subscriber ──────────────────────────────────
print("[Isaac] Setting up rclpy...")
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import LaserScan
from geometry_msgs.msg import Twist

rclpy.init()
ros_node = Node("isaac_bedroom_node")
scan_pub = ros_node.create_publisher(LaserScan, f"/{NS}/scan", 10)

_cmd_vel_lock = threading.Lock()
_current_cmd  = [0.0, 0.0]  # [linear_x, angular_z]

def _cmd_vel_cb(msg: Twist):
    with _cmd_vel_lock:
        _current_cmd[0] = msg.linear.x
        _current_cmd[1] = msg.angular.z

ros_node.create_subscription(Twist, f"/{NS}/cmd_vel", _cmd_vel_cb, 10)

ANGLE_INCREMENT = math.radians(0.4)

# ── Start simulation ──────────────────────────────────────────────────────────
print("[Isaac] Starting playback...")
omni.timeline.get_timeline_interface().play()
lidar.initialize()
simulation_app.update()

robot = Articulation(ARTIC_ROOT)
robot.initialize()
print(f"[Isaac] Robot DOFs: {robot.dof_names}")

diff_ctrl = DifferentialController(
    name="diff_drive",
    wheel_radius=WHEEL_RADIUS,
    wheel_base=WHEEL_BASE,
)

print("\n[Isaac] *** Simulation running ***")
print(f"[Isaac] Spawn: ({SPAWN_X}, {SPAWN_Y})  Goal: (0.0, 3.7)")
print("[Isaac] Now start: ros2 launch src/nav_fleet/launch/nav2_isaac_launch.py")
print("[Isaac] Close the GUI window or Ctrl+C to stop.\n")

step = 0
try:
    while simulation_app.is_running():
        simulation_app.update()

        rclpy.spin_once(ros_node, timeout_sec=0)

        with _cmd_vel_lock:
            cmd = list(_current_cmd)

        drive_action = diff_ctrl.forward(np.array(cmd))
        if drive_action.joint_velocities is not None and len(drive_action.joint_velocities) >= 2:
            vl = float(drive_action.joint_velocities[0])
            vr = float(drive_action.joint_velocities[1])
            # DOF order: [rear_left, rear_right, front_left, front_right]
            robot.apply_action(ArticulationAction(
                joint_velocities=np.array([vl, vr, vl, vr])
            ))

        if step % 6 == 0:
            frame = lidar.get_current_frame()
            if frame and "linear_depth" in frame:
                depth = frame["linear_depth"].flatten()
                msg = LaserScan()
                msg.header.stamp    = ros_node.get_clock().now().to_msg()
                msg.header.frame_id = "lidar_link"
                msg.angle_min       = -math.pi
                msg.angle_max       =  math.pi
                msg.angle_increment = ANGLE_INCREMENT
                msg.time_increment  = 0.0
                msg.scan_time       = 0.1
                msg.range_min       = 0.12
                msg.range_max       = 12.0
                msg.ranges          = depth.tolist()
                scan_pub.publish(msg)

        if step % 600 == 0 and step > 0:
            with _cmd_vel_lock:
                c = list(_current_cmd)
            print(f"[Isaac] step={step}  cmd=({c[0]:.2f}, {c[1]:.2f})")

        step += 1

except KeyboardInterrupt:
    print("\n[Isaac] Shutting down...")

rclpy.shutdown()
simulation_app.close()
