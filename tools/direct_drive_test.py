#!/usr/bin/env python3
"""Spin-in-place test — prints live yaw every 0.2 s while spinning.

Goal: see the number climb in the terminal AND watch the robot rotate in
Gazebo at the same time. Do NOT proceed to Nav2 debugging until both match.

Run with the minimal launch (no Nav2):
    Terminal 1: ros2 launch src/nav_fleet/launch/sim_launch_minimal.py
    Terminal 2: gz sim -g
    Terminal 3: python tools/direct_drive_test.py

Expects /robot_001/odom from the ros_gz_bridge.
"""
import math
import sys
import time
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry


def quat_to_yaw(q):
    siny = 2.0 * (q.w * q.z + q.x * q.y)
    cosy = 1.0 - 2.0 * (q.y * q.y + q.z * q.z)
    return math.atan2(siny, cosy)


class SpinTest(Node):
    def __init__(self):
        super().__init__('spin_test')
        self.pub = self.create_publisher(Twist, '/robot_001/cmd_vel', 10)
        self.yaw_deg = None
        self.odom_count = 0
        self.create_subscription(Odometry, '/robot_001/odom', self._cb, 10)

    def _cb(self, msg):
        self.yaw_deg = math.degrees(quat_to_yaw(msg.pose.pose.orientation))
        self.odom_count += 1

    def spin_cmd(self, angular_z):
        msg = Twist()
        msg.angular.z = float(angular_z)
        self.pub.publish(msg)

    def stop(self):
        self.pub.publish(Twist())


def wait_for_odom(node, timeout=15.0):
    print("Waiting for /robot_001/odom ...")
    t0 = time.time()
    while time.time() - t0 < timeout:
        rclpy.spin_once(node, timeout_sec=0.1)
        if node.odom_count > 0:
            return True
    return False


def main():
    rclpy.init()
    node = SpinTest()

    print()
    print("=" * 55)
    print("  SPIN TEST — verify robot turns in Gazebo AND odom")
    print("=" * 55)
    print()
    print("Step 1: open 'gz sim -g' and find the robot in the scene.")
    print("Step 2: watch the YAW line below change while robot spins.")
    print("Step 3: both odom AND visual must confirm rotation.")
    print()

    if not wait_for_odom(node, timeout=20.0):
        print("ERROR: no /robot_001/odom received after 20 s.")
        print("  - Is sim_launch_minimal.py running?")
        print("  - Did the bridge start? (should see 'Odom bridge' in launch output)")
        sys.exit(1)

    print(f"Odom is live ({node.odom_count} msgs received so far).")
    print()
    print("Starting spin: angular.z = +1.0 rad/s for 8 seconds.")
    print("Expected: ~458° total rotation (1.0 rad/s × 8 s at 1× RTF).")
    print("Watch the robot spin in Gazebo and the YAW value below:")
    print()

    yaw_start = node.yaw_deg
    t_start = time.time()
    t_end = t_start + 8.0
    last_print = 0.0

    while time.time() < t_end:
        node.spin_cmd(1.0)
        rclpy.spin_once(node, timeout_sec=0.02)

        now = time.time()
        if now - last_print >= 0.2:
            elapsed = now - t_start
            yaw_now = node.yaw_deg if node.yaw_deg is not None else 0.0
            # unwrap: count accumulated rotation
            print(f"  t={elapsed:4.1f}s  YAW={yaw_now:+7.1f}°  odom_msgs={node.odom_count}",
                  flush=True)
            last_print = now

    node.stop()
    rclpy.spin_once(node, timeout_sec=0.2)

    yaw_end = node.yaw_deg
    delta = yaw_end - yaw_start
    # unwrap if crossed ±180
    if delta > 180:
        delta -= 360
    elif delta < -180:
        delta += 360

    print()
    print(f"Start yaw: {yaw_start:+.1f}°   End yaw: {yaw_end:+.1f}°")
    print(f"Δyaw (odom): {delta:+.1f}°")
    print()

    if abs(delta) < 10.0:
        print("FAIL: odom shows <10° rotation — cmd_vel is not reaching the diff-drive.")
        print("      Check: bridge running? Gazebo server up? Correct topic?")
    else:
        print(f"Odom OK: {abs(delta):.0f}° rotation reported.")
        print()
        print("Did you see the robot rotate in Gazebo?")
        print("  YES → diff-drive + bridge confirmed working. Ready to debug Nav2.")
        print("  NO  → odom/visual mismatch. Likely cause: gz sim -g is connected")
        print("         to a DIFFERENT sim server than the one the robot is in.")
        print("         Kill everything, relaunch, open gz sim -g AFTER spawn.")

    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
