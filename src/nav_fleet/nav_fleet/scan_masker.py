# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""Thin rclpy wrapper around scan_filter.py's pure masking logic — subscribes to the
lidar driver's raw scan topic, republishes a copy with the mast/antenna self-
occlusion sectors NaN'd out on the topic Nav2/SLAM actually consume.

Launched by drivers_only_launch.py (real-hardware group, same treatment as
esp32_driver.py) — primarily via robot_boot.sh (real mission boot) and
hil_stage.sh smoke() (the bench smoke test), both bare-metal; also reachable via
sensors_only_launch.py's own real-hardware group, which includes
drivers_only_launch.py (2026-08-10 refactor). sim/CI never constructs this node;
Gazebo's own lidar plugin has no self-occlusion to mask. Default input_topic='scan'
(ldlidar_ros2's own default output) and output_topic='/robot_001/scan' — this also
closes the lidar-side half of RealRobotStartup.md's separately-tracked
topic-remapping gap (the vendor launch file is included with no remappings at all)
as a side effect of masking, since the masked copy has to land somewhere Nav2/EKF
already expect it. The camera side of that remapping gap is untouched here.

Also rewrites header.frame_id to output_frame_id (default 'lidar_link') — a SECOND,
previously-undiscovered half of the same remapping gap, found 2026-08-12 chasing a
live AMCL scan-processing deadlock all the way to root cause. ldlidar_ros2's own
ld19.launch.py hardcodes 'base_laser' as the scan frame_id (confirmed by reading
that file directly on the Jetson), but ugv_pt.urdf.xacro (and therefore
robot_state_publisher, added to drivers_only_launch.py the same day) only knows the
link by its URDF name, 'lidar_link' — two different names for the same physical
sensor mount, so TF had no path connecting an incoming scan to the rest of the
tree at all. AMCL's TF-synchronized scan subscription silently buffered every scan
forever with zero related log output (confirmed live at DEBUG level), which looked
identical to "AMCL never receives scans" until this was found. Fixed here, not by
patching the vendor launch file (this project's own convention: don't hand-modify
vendor packages) and not with an extra static-transform node (no geometry offset
exists between the two names — it's a pure rename, matching this file's own
mask_sectors_deg precedent of correcting the message it's already republishing
anyway).
"""
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import LaserScan

from nav_fleet.scan_filter import mask_scan_values, parse_mask_sectors, rotate_scan_frame

# RAW lidar bearings hidden from Nav2. 46-123 is the pan-tilt mast (confirmed live
# 2026-08-10; see scan_filter.py's module docstring). A second sector, 268-277
# ("WiFi antenna"), was REMOVED 2026-11-16: with a box 0.5 m in front of the robot the
# unmasked scan showed clean box returns right through 268-277 (0.576-0.580 m, no near
# occluder), and that strip is the robot's dead-ahead direction (true forward ~269) --
# the mask was blinding the 9 degrees straight in front for nothing.
DEFAULT_MASK_SECTORS_DEG = [46.0, 123.0]

# Must match ugv_pt.urdf.xacro's real lidar link name (confirmed via grep, not
# assumed) — NOT ldlidar_ros2's own hardcoded 'base_laser' scan frame_id. See the
# module docstring above for the full story.
DEFAULT_OUTPUT_FRAME_ID = 'lidar_link'

# RAW lidar bearing of the robot's true forward. The published scan is rotated so
# this bearing becomes angle 0 -- until 2026-11-16 nothing did that for Nav2, which
# therefore saw the room turned (see scan_filter.rotate_scan_frame).
# 269, measured 2026-11-16 on the bench: a flat box 0.5 m ahead, line-fitted
# (2.7 mm rms), has its square-on direction at raw 269.9; the robot's own camera
# photo shows that box square to the robot (bench_box.png), and correcting the box's
# off-centre position by the camera gives ~267. Also consistent with the mast being
# directly behind (centre 84.5 + 180 = 264.5). The earlier value, 285 (2026-08-10,
# object placed by eye), was ~16 degrees off. Good to a few degrees; a long flat wall
# with the robot squared against it would tighten it.
# mask_sectors_deg above stay in RAW bearings and are applied BEFORE the rotation.
DEFAULT_FORWARD_BEARING_DEG = 269.0


class ScanMasker(Node):

    def __init__(self):
        super().__init__('scan_masker')
        self.declare_parameter('input_topic', 'scan')
        self.declare_parameter('output_topic', '/robot_001/scan')
        self.declare_parameter('mask_sectors_deg', DEFAULT_MASK_SECTORS_DEG)
        self.declare_parameter('output_frame_id', DEFAULT_OUTPUT_FRAME_ID)
        self.declare_parameter('forward_bearing_deg', DEFAULT_FORWARD_BEARING_DEG)

        output_topic = self.get_parameter('output_topic').value
        self.pub = self.create_publisher(LaserScan, output_topic, 10)
        input_topic = self.get_parameter('input_topic').value
        self.create_subscription(LaserScan, input_topic, self._cb, 10)

        self.get_logger().info(
            f"scan_masker up — {input_topic} -> {output_topic}, "
            f"mask_sectors_deg={list(self.get_parameter('mask_sectors_deg').value)}, "
            f"output_frame_id={self.get_parameter('output_frame_id').value}, "
            f"forward_bearing_deg={self.get_parameter('forward_bearing_deg').value}")

    def _cb(self, msg):
        # Re-read the params each message (not cached at __init__) so a live
        # `ros2 param set` during bring-up/debugging takes effect immediately,
        # matching this project's other params-are-live-tunable nodes.
        sectors_deg = parse_mask_sectors(list(self.get_parameter('mask_sectors_deg').value))
        msg.ranges = mask_scan_values(msg.ranges, msg.angle_min, msg.angle_increment,
                                      sectors_deg)
        if msg.intensities:
            msg.intensities = mask_scan_values(msg.intensities, msg.angle_min,
                                               msg.angle_increment, sectors_deg)
        # Masking above used the RAW angles. Now rotate the header angles so angle 0
        # is the robot's forward, matching what the frame_id below claims.
        msg.angle_min, msg.angle_max = rotate_scan_frame(
            msg.angle_min, msg.angle_max, self.get_parameter('forward_bearing_deg').value)
        # Rewrite the frame_id to match robot_state_publisher's real URDF link name —
        # see the module docstring for why the vendor driver's own 'base_laser' can't
        # be trusted to line up with the TF tree.
        msg.header.frame_id = self.get_parameter('output_frame_id').value
        self.pub.publish(msg)


def main():
    rclpy.init()
    node = ScanMasker()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
