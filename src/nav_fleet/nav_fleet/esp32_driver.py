# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""ROS2 node bridging the Waveshare UGV's ESP32 sub-controller (odom + IMU in,
cmd_vel out) — real-robot driver layer + bench smoke-test design spec
(docs/superpowers/specs/2026-08-05-real-robot-driver-smoke-test-design.md).

Design intent (from the spec): from ekf_node/Nav2's point of view, this node is a
drop-in replacement for Gazebo's sim bridge — same topics (/robot_001/odom,
/robot_001/imu/data, subscribes /robot_001/cmd_vel), same message types, same frame
convention (unprefixed odom/base_footprint, matching ekf.yaml's odom0/imu0 topic
names).

Only ever launched by sensors_only_launch.py's real-hardware group (use_sim_time
false) — sim/CI never constructs this node; Gazebo's bridge publishes the same
topics directly instead.
"""
import json
import math
import threading
import time

import rclpy
import serial
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from rclpy.node import Node
from sensor_msgs.msg import Imu

from nav_fleet.esp32_protocol import (encode_enable_feedback_flow, encode_get_imu_data,
                                      encode_velocity_cmd, integrate_odometry,
                                      parse_base_info, parse_feedback_line, parse_orientation)


class Esp32Driver(Node):

    def __init__(self):
        super().__init__('esp32_driver')
        self.declare_parameter('serial_device', '/dev/ttyUSB0')
        self.declare_parameter('baud', 115200)
        self.declare_parameter('watchdog_timeout_ms', 200)
        self.declare_parameter('imu_poll_hz', 50.0)
        # Must match the ESP32 firmware's own TRACK_WIDTH constant (ugv_config.h) —
        # 0.172 for the active "UGV Rover" mainType config as of 2026-08-06.
        self.declare_parameter('track_width', 0.172)

        self._track_width = self.get_parameter('track_width').value
        self._watchdog_timeout_s = self.get_parameter('watchdog_timeout_ms').value / 1000.0

        device = self.get_parameter('serial_device').value
        baud = self.get_parameter('baud').value
        try:
            self._ser = serial.Serial(device, baud, timeout=1.0)
        except serial.SerialException as exc:
            # Fail loudly on init, don't retry-forever-silently (design spec's Error
            # handling section — matches this project's established convention).
            self.get_logger().fatal(f"esp32_driver: cannot open {device} @ {baud}: {exc}")
            raise
        self._write_lock = threading.Lock()

        self._x = 0.0
        self._y = 0.0
        self._yaw = 0.0
        # Latest fused orientation from a T:1002 reply (see esp32_protocol.py's
        # module docstring, corrected 2026-08-10) — parsed and cached, but NOT yet
        # wired into _publish_imu's msg.orientation: the quaternion's real axis
        # convention (q0=w vs q0=x, Hamilton vs JPL) is unconfirmed against real
        # hardware rotation testing. Flag, don't guess — same pattern this file
        # already uses for the raw accel/gyro units below.
        self._last_orientation = None
        self._last_base_info_time = None
        self._last_cmd_time = time.time()
        self._stopped = False
        # Per-node stop signal for _read_loop — rclpy.ok() alone is process-global,
        # so it never stops this node's own reader thread on destroy_node() (only on
        # process exit, which happens to be the only case today since main() runs a
        # single node per process — see review finding, Task 2 fix round).
        self._stop_event = threading.Event()

        self.odom_pub = self.create_publisher(Odometry, '/robot_001/odom', 10)
        self.imu_pub = self.create_publisher(Imu, '/robot_001/imu/data', 10)
        self.create_subscription(Twist, '/robot_001/cmd_vel', self._cmd_vel_cb, 10)

        self._send(encode_enable_feedback_flow(True))

        imu_poll_hz = self.get_parameter('imu_poll_hz').value
        self.create_timer(1.0 / imu_poll_hz, self._imu_poll_cb)
        self.create_timer(self._watchdog_timeout_s / 2.0, self._watchdog_cb)

        self._reader_thread = threading.Thread(target=self._read_loop, daemon=True)
        self._reader_thread.start()

        self.get_logger().info(
            f"esp32_driver up — {device}@{baud}, track_width={self._track_width}m, "
            f"watchdog={self.get_parameter('watchdog_timeout_ms').value}ms")

    def _send(self, cmd):
        line = (json.dumps(cmd) + '\n').encode('utf-8')
        with self._write_lock:
            self._ser.write(line)

    def _cmd_vel_cb(self, msg):
        self._last_cmd_time = time.time()
        self._stopped = False
        self._send(encode_velocity_cmd(msg.linear.x, msg.angular.z))

    def _imu_poll_cb(self):
        self._send(encode_get_imu_data())

    def _watchdog_cb(self):
        # Driver-side watchdog — proactive, in ADDITION to the firmware's own
        # HEART_BEAT_DELAY (3000ms default) — see Global Constraints in the plan.
        if self._stopped:
            return
        if time.time() - self._last_cmd_time > self._watchdog_timeout_s:
            self._stopped = True
            self._send(encode_velocity_cmd(0.0, 0.0))
            self.get_logger().warn('esp32_driver: cmd_vel watchdog tripped — zero-velocity sent')

    def destroy_node(self):
        # Signal the reader thread to stop and wait for it before tearing down the
        # node it depends on (get_clock()/get_logger() via _publish_odom/_publish_imu)
        # — join happens BEFORE super().destroy_node() so the thread never touches a
        # half-destroyed node. Bounded by the mocked/real serial readline's own
        # timeout=1.0s, so this is a short, deterministic wait, not an indefinite one.
        self._stop_event.set()
        self._reader_thread.join(timeout=1.5)
        super().destroy_node()

    def _read_loop(self):
        while rclpy.ok() and not self._stop_event.is_set():
            try:
                raw = self._ser.readline()
            except serial.SerialException as exc:
                self.get_logger().error(f'esp32_driver: serial read error: {exc}')
                time.sleep(0.5)
                continue
            if not raw:
                continue  # readline timeout, no data yet
            data = parse_feedback_line(raw.decode('utf-8', errors='replace'))
            if data is None:
                continue
            self._dispatch_line(data)

    def _dispatch_line(self, data):
        # Split out from _read_loop so the dispatch logic is directly unit-testable
        # without driving the background reader thread (matches this file's own
        # existing pattern of pulling synchronous logic out of the thread loop, e.g.
        # _publish_odom/_publish_imu below).
        base_info = parse_base_info(data)
        if base_info is not None:
            # Both odom AND imu come off the SAME T:1001 message now (corrected
            # 2026-08-10) — it carries wheel speeds (odom) plus raw accel/gyro (imu)
            # in one line, not two separate messages as originally assumed.
            self._publish_odom(base_info)
            self._publish_imu(base_info)
            return
        orientation = parse_orientation(data)
        if orientation is not None:
            self._last_orientation = orientation

    def _publish_odom(self, info):
        now = self.get_clock().now()
        now_s = now.nanoseconds / 1e9
        if self._last_base_info_time is not None:
            dt = now_s - self._last_base_info_time
            if dt > 0.0:
                self._x, self._y, self._yaw = integrate_odometry(
                    self._x, self._y, self._yaw, info.speed_l, info.speed_r,
                    self._track_width, dt)
        self._last_base_info_time = now_s

        msg = Odometry()
        msg.header.stamp = now.to_msg()
        msg.header.frame_id = 'odom'
        msg.child_frame_id = 'base_footprint'
        msg.pose.pose.position.x = self._x
        msg.pose.pose.position.y = self._y
        msg.pose.pose.orientation.z = math.sin(self._yaw / 2.0)
        msg.pose.pose.orientation.w = math.cos(self._yaw / 2.0)
        msg.twist.twist.linear.x = (info.speed_l + info.speed_r) / 2.0
        msg.twist.twist.angular.z = (info.speed_r - info.speed_l) / self._track_width
        self.odom_pub.publish(msg)

    def _publish_imu(self, info):
        """info is a BaseInfo (T:1001) — corrected 2026-08-10, see esp32_protocol.py's
        module docstring. Raw accel/gyro/mag live in the SAME continuous message as
        the wheel speeds _publish_odom reads; there is no separate "IMU data" feedback
        message despite T:126's name (its T:1002 reply is fused orientation only —
        see _dispatch_line/self._last_orientation)."""
        msg = Imu()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = 'imu_link'
        # ax/ay/az/gx/gy/gz units are NOT confirmed against real hardware — the
        # firmware's own field names ("Raw" in the C++ struct names) are ambiguous
        # about whether QMI8658.cpp's driver already scales to physical SI units or
        # returns raw LSB counts. Passed through as-is; confirm on real hardware
        # before trusting these as calibrated m/s^2 / rad/s (design spec's "Known
        # implementation-time risks" pattern — flag, don't guess).
        msg.linear_acceleration.x = info.ax
        msg.linear_acceleration.y = info.ay
        msg.linear_acceleration.z = info.az
        msg.angular_velocity.x = info.gx
        msg.angular_velocity.y = info.gy
        msg.angular_velocity.z = info.gz
        # self._last_orientation (from a T:1002 reply, if one has arrived yet) is NOT
        # used to populate msg.orientation here — its quaternion axis convention is
        # unconfirmed against real hardware (see __init__'s comment). Real, scoped
        # follow-up, not silently dropped.
        msg.orientation_covariance[0] = -1.0  # orientation not populated from this message
        self.imu_pub.publish(msg)


def main():
    rclpy.init()
    node = Esp32Driver()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
