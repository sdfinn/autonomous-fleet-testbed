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

Launched by drivers_only_launch.py (real-hardware group, use_sim_time false) —
primarily via robot_boot.sh (real mission boot) and hil_stage.sh smoke() (the bench
smoke test), both bare-metal; also reachable via sensors_only_launch.py's own
real-hardware group, which includes drivers_only_launch.py (2026-08-10 refactor).
sim/CI never constructs this node; Gazebo's bridge publishes the same topics
directly instead.
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
from std_msgs.msg import Bool, Float32

from nav_fleet.hold_input import HoldInput
from nav_fleet.esp32_protocol import (BATTERY_CRITICAL, BATTERY_LOW, IMU_OK,
                                      BatteryMonitor, GyroBiasEstimator, ImuHealth,
                                      battery_volts,
                                      encode_boot_mission_info,
                                      encode_enable_feedback_flow, encode_get_imu_data,
                                      encode_set_heartbeat_timeout, encode_wheel_speed_cmd,
                                      integrate_odometry, parse_base_info,
                                      parse_chassis_main_type, parse_feedback_line,
                                      parse_orientation, scale_imu_raw, twist_to_wheel_speeds)

# Publish the pack voltage once per this many status lines (~1 Hz at the board's ~20 Hz).
BATTERY_PUBLISH_EVERY = 20
# Repeat the low/critical log line this often while the state persists.
BATTERY_REMIND_S = 60.0
# Same for a frozen or implausible IMU.
IMU_REMIND_S = 60.0

# Variance published on the gyro's angular_velocity_covariance diagonal, (rad/s)^2.
# Measured 2026-11-16 from 15 s of a stationary real robot: gyro z std = 0.0028 rad/s
# (variance 7.6e-6); x/y std ~0.005. 1e-4 (std 0.01 rad/s) is deliberately ~3.6x the
# resting z noise, because noise while driving has not been characterized. It must be
# POSITIVE: robot_localization ignores the gyro entirely when element [0] is -1, and
# treats 0 as a perfect measurement. Not corrected here: a resting z bias of
# +0.0046 rad/s (0.26 deg/s), and the unverified 16 LSB/dps gyro scale.
GYRO_VARIANCE_RAD2_S2 = 1.0e-4


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
        # The firmware's stored chassis type this driver expects: 2 = UGV Rover (the
        # 6-wheel chassis this robot is). Checked at start-up; see _check_chassis_line.
        self.declare_parameter('expected_main_type', 2)
        # Multiplier on angular.z before it is sent to the firmware. The firmware
        # turns a rate into wheel speeds with the geometric track width (0.172 m), but
        # a 6-wheel skid-steer scrubs its tyres when it turns: measured 2026-11-16 by
        # gyro on the bench, on-the-spot commands of 1.0 / 2.0 / -2.0 / 3.0 rad/s
        # produced 0.42 / 0.62 / 0.77 / 1.03 rad/s (0.5 rad/s produced almost nothing).
        # 2.8 is the mean ratio; it makes a commanded turn rate roughly the real one.
        # First-cut value from one floor: surface-dependent, and only measured for
        # turns on the spot, not while driving forward.
        self.declare_parameter('angular_cmd_gain', 2.8)
        # The BOARD's own stop-on-silence timeout (T:136), set at every start-up: if no
        # wheel-speed command reaches it for this long, the firmware zeroes the motors
        # by itself. This is the only protection that still works when the Jetson
        # process, the Jetson's OS or the Jetson's power is gone (2026-11-18: it was
        # not armed at all, and the robot spun until its power switch was thrown --
        # see esp32_protocol.encode_wheel_speed_cmd). Must be comfortably longer than
        # the gap between commands (Nav2 and key_teleop both send at ~20 Hz = 50 ms)
        # and short enough to matter: at 0.3 m/s, 500 ms is 15 cm.
        self.declare_parameter('firmware_stop_ms', 500)
        # Attended runs (2026-11-19): operator_watch publishes /robot_001/operator_hold
        # (True = the operator's machine cannot be reached; hold the wheels). With this
        # parameter True, a SILENT topic also holds -- nothing published for
        # OPERATOR_HOLD_STALE_S means the watch is not running or has died, and a run
        # that asked to be watched must not drive unwatched. False (the default, and
        # every unattended run): the topic is obeyed if someone publishes it, and its
        # absence means nothing.
        self.declare_parameter('operator_watch_required', False)
        # Same idea for obstacle_guard and /robot_001/obstacle_hold (True = the lidar
        # sees something in the robot's path). Required on the real robot's missions:
        # a dead lidar or a dead guard must stop the robot, not leave it blind.
        self.declare_parameter('obstacle_guard_required', False)

        self._track_width = self.get_parameter('track_width').value
        self._angular_cmd_gain = self.get_parameter('angular_cmd_gain').value
        self._expected_main_type = self.get_parameter('expected_main_type').value
        # None = not reported yet; True/False once the controller has answered T:602.
        self._chassis_ok = None
        # Resting gyro offset, re-learned every ~2 s the robot sits still (40 samples
        # at the ~20 Hz feedback rate). See GyroBiasEstimator.
        self._gyro_bias = GyroBiasEstimator(window=40)
        # Is the IMU alive? See ImuHealth. _imu_state is the last state logged: None
        # until the first ~2 s of samples, then 'ok' / 'frozen' / 'implausible'.
        self._imu_health = ImuHealth()
        self._imu_state = None
        self._imu_last_log = 0.0
        # Pack voltage from the same status line; see BatteryMonitor. _battery_state is
        # the last state logged (None until the first full window of samples).
        self._battery = BatteryMonitor()
        self._battery_state = None
        self._battery_last_log = 0.0
        self._battery_samples = 0
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
        # True while the most recent cmd_vel asked for no motion at all (see
        # _publish_imu's "stationary" test for why this exists next to _stopped).
        self._cmd_is_zero = False
        # Per-node stop signal for _read_loop — rclpy.ok() alone is process-global,
        # so it never stops this node's own reader thread on destroy_node() (only on
        # process exit, which happens to be the only case today since main() runs a
        # single node per process — see review finding, Task 2 fix round).
        self._stop_event = threading.Event()
        # Everything that may hold the wheels, keyed by the parameter that makes it
        # mandatory. See HoldInput.
        self._holds = {
            'operator_watch_required': HoldInput(
                '/robot_001/operator_hold', 'operator unreachable',
                'no operator watch running'),
            'obstacle_guard_required': HoldInput(
                '/robot_001/obstacle_hold', 'obstacle in the path',
                'no obstacle guard running'),
        }

        self.odom_pub = self.create_publisher(Odometry, '/robot_001/odom', 10)
        self.imu_pub = self.create_publisher(Imu, '/robot_001/imu/data', 10)
        self.battery_pub = self.create_publisher(Float32, '/robot_001/battery_voltage', 10)
        self.create_subscription(Twist, '/robot_001/cmd_vel', self._cmd_vel_cb, 10)
        for param, hold in self._holds.items():
            self.create_subscription(
                Bool, hold.topic, lambda msg, param=param: self._hold_cb(param, msg), 10)

        self._send(encode_enable_feedback_flow(True))
        self._send(encode_boot_mission_info())
        self._send(encode_set_heartbeat_timeout(
            int(self.get_parameter('firmware_stop_ms').value)))

        imu_poll_hz = self.get_parameter('imu_poll_hz').value
        self.create_timer(1.0 / imu_poll_hz, self._imu_poll_cb)
        self.create_timer(self._watchdog_timeout_s / 2.0, self._watchdog_cb)

        self._reader_thread = threading.Thread(target=self._read_loop, daemon=True)
        self._reader_thread.start()

        self.get_logger().info(
            f"esp32_driver up — {device}@{baud}, track_width={self._track_width}m, "
            f"watchdog={self.get_parameter('watchdog_timeout_ms').value}ms, "
            f"board stop-on-silence={self.get_parameter('firmware_stop_ms').value}ms")

    def _send(self, cmd):
        line = (json.dumps(cmd) + '\n').encode('utf-8')
        with self._write_lock:
            self._ser.write(line)

    def _cmd_vel_cb(self, msg):
        self._last_cmd_time = time.time()
        self._stopped = False
        self._cmd_is_zero = (msg.linear.x == 0.0 and msg.angular.z == 0.0)
        # Refuse to drive if the controller reported the wrong chassis type: in that
        # state it runs ~2.5x faster than commanded and possibly backwards.
        if self._chassis_ok is False:
            self._send_motion(0.0, 0.0)
            return
        # Refuse to drive on a critically low pack: the next heavy turn can pull the
        # voltage low enough to switch the Jetson off mid-command (2026-11-18).
        if self._battery_state == BATTERY_CRITICAL:
            self._send_motion(0.0, 0.0)
            return
        # Refuse to drive on an IMU that is frozen or not feeling gravity: the heading
        # filter trusts the gyro, so Nav2 would be steering from a position the robot
        # is not in (2026-11-20: it spun on the home spot).
        if self._imu_bad():
            self._send_motion(0.0, 0.0)
            return
        # Hold while a watcher says so: the operator of an attended run cannot be
        # reached, or the lidar sees something in the path. Nav2 is not told: it keeps
        # sending commands and carries on when the hold is released.
        if self._holding():
            self._send_motion(0.0, 0.0)
            return
        # No sign flips. From 2026-08-11 to 2026-11-16 both linear.x and angular.z
        # were negated here, on the belief that this unit was wired backwards. The
        # real cause was the firmware's stored chassis type (main=3, UGV Beast, which
        # sets SET_MOTOR_DIR=true) on a UGV Rover. With main=2 stored, bench-verified
        # 2026-11-16: +X drives forward (lidar: 0.281 m for a 0.30 m command) and +Z
        # turns left (gyro positive). angular.z is scaled by angular_cmd_gain for
        # skid-steer tyre scrub (see the parameter's comment).
        self._send_motion(msg.linear.x, msg.angular.z * self._angular_cmd_gain)

    def _hold_cb(self, param, msg):
        was_holding = self._holding()
        self._holds[param].update(msg.data, time.time())
        if not was_holding and self._holding():
            # Do not wait for the next cmd_vel (up to 50 ms away) to stop the wheels.
            self._send_motion(0.0, 0.0)

    def _holding(self):
        """True while any watcher holds the wheels. Logs each watcher's changes."""
        now = time.time()
        any_held = False
        for param, hold in self._holds.items():
            held, reason = hold.state(now, self.get_parameter(param).value)
            if held != hold.held:
                hold.held = held
                if held:
                    self.get_logger().warn(f'esp32_driver: wheels HELD — {reason}')
                else:
                    self.get_logger().info(
                        f'esp32_driver: hold released — not ({hold.when_true})')
            any_held = any_held or held
        return any_held

    def _send_motion(self, linear_x, angular_z):
        """Send a body twist as left/right wheel speeds (T:1), never as T:13: only T:1
        re-arms the board's stop-on-silence timer. Same arithmetic the firmware applies
        to T:13, so the motion itself is unchanged."""
        self._send(encode_wheel_speed_cmd(
            *twist_to_wheel_speeds(linear_x, angular_z, self._track_width)))

    def _imu_poll_cb(self):
        self._send(encode_get_imu_data())

    def _watchdog_cb(self):
        # Driver-side watchdog — proactive, in ADDITION to the firmware's own
        # HEART_BEAT_DELAY (3000ms default) — see Global Constraints in the plan.
        if self._stopped:
            return
        if time.time() - self._last_cmd_time > self._watchdog_timeout_s:
            self._stopped = True
            self._send_motion(0.0, 0.0)
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
            text = raw.decode('utf-8', errors='replace')
            self._check_chassis_line(text)
            data = parse_feedback_line(text)
            if data is None:
                continue
            self._dispatch_line(data)

    def _check_chassis_line(self, text):
        """Looks for the controller's stored chassis type in the T:602 reply (plain
        text). A mismatch blocks all motion (see _cmd_vel_cb) and logs an error on
        every sighting; a match is logged once."""
        main_type = parse_chassis_main_type(text)
        if main_type is None:
            return
        if main_type == self._expected_main_type:
            if self._chassis_ok is not True:
                self.get_logger().info(
                    f'esp32_driver: controller chassis type main={main_type} (as expected)')
            self._chassis_ok = True
        else:
            self._chassis_ok = False
            self.get_logger().error(
                f'esp32_driver: controller chassis type is main={main_type}, expected '
                f'{self._expected_main_type} — REFUSING TO DRIVE (speed and direction '
                f'would be wrong). Fix once with: '
                f'{{"T":900,"main":{self._expected_main_type},"module":0}}')

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
            self._on_imu_sample(base_info)
            # A known-bad IMU is not published at all: silence makes the heading
            # filter coast, garbage makes it spin.
            if not self._imu_bad():
                self._publish_imu(base_info)
            self._on_battery_sample(base_info.voltage)
            return
        orientation = parse_orientation(data)
        if orientation is not None:
            self._last_orientation = orientation

    def _imu_bad(self):
        """True once the IMU is KNOWN to be frozen or implausible (not before the
        first verdict: same rule as the chassis-type check)."""
        return self._imu_state is not None and self._imu_state != IMU_OK

    def _on_imu_sample(self, info):
        """Judge the IMU on its raw counts and log when the verdict changes."""
        state = self._imu_health.update(info.ax, info.ay, info.az,
                                        info.gx, info.gy, info.gz)
        if state is None:
            return
        now = time.time()
        changed = state != self._imu_state
        remind = state != IMU_OK and now - self._imu_last_log >= IMU_REMIND_S
        if not (changed or remind):
            return
        # One fixed, greppable shape: robot_boot.sh reads this line before a mission.
        line = f'esp32_driver: imu {state} ({self._imu_health.detail})'
        self._imu_state = state
        self._imu_last_log = now
        if state == IMU_OK:
            self.get_logger().info(line)
        else:
            self.get_logger().error(
                line + ' -- motion REFUSED; switch the robot off and on again')
            if changed:
                self._send_motion(0.0, 0.0)

    def _on_battery_sample(self, raw):
        """Publish the pack voltage (~1 Hz) and log when its state changes."""
        volts = battery_volts(raw)
        self._battery_samples += 1
        if self._battery_samples % BATTERY_PUBLISH_EVERY == 0:
            self.battery_pub.publish(Float32(data=volts))
        state = self._battery.update(volts)
        if state is None:
            return
        now = time.time()
        changed = state != self._battery_state
        remind = (state in (BATTERY_LOW, BATTERY_CRITICAL)
                  and now - self._battery_last_log >= BATTERY_REMIND_S)
        if not (changed or remind):
            return
        # One fixed, greppable shape: robot_boot.sh reads this line before a mission.
        line = f'esp32_driver: battery {self._battery.volts:.2f} V ({state})'
        if state == BATTERY_CRITICAL:
            self.get_logger().error(line + ' -- motion REFUSED until the pack is charged')
            if changed:
                self._send_motion(0.0, 0.0)
        elif state == BATTERY_LOW:
            self.get_logger().warning(line + ' -- charge before the next mission')
        else:
            self.get_logger().info(line)
        self._battery_state = state
        self._battery_last_log = now

    def _publish_odom(self, info):
        # Used as reported — no sign flip. They were negated from 2026-08-11 to
        # 2026-11-16 for the same wrong-chassis-type reason as _cmd_vel_cb's old flips
        # (see its comment). With main=2 stored, forward motion reports positive
        # speeds and the firmware's distance counters match the lidar (27/31 cm for a
        # real 28.1 cm). Note the published angular.z below is wheel-implied and reads
        # roughly 3x the real turn rate on this skid-steer chassis; ekf.yaml fuses the
        # gyro for heading, not this.
        speed_l = info.speed_l
        speed_r = info.speed_r

        now = self.get_clock().now()
        now_s = now.nanoseconds / 1e9
        if self._last_base_info_time is not None:
            dt = now_s - self._last_base_info_time
            if dt > 0.0:
                self._x, self._y, self._yaw = integrate_odometry(
                    self._x, self._y, self._yaw, speed_l, speed_r,
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
        msg.twist.twist.linear.x = (speed_l + speed_r) / 2.0
        msg.twist.twist.angular.z = (speed_r - speed_l) / self._track_width
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
        # ax/ay/az/gx/gy/gz are RAW QMI8658 LSB counts, NOT already-scaled physical
        # units — confirmed the hard way, 2026-08-12/13: this used to pass them
        # straight through (the "confirm on real hardware before trusting these"
        # comment this replaced was correct to flag it, and real hardware said no).
        # A live AMCL investigation found a STATIONARY robot's odom->base_footprint
        # yaw jumping through the full +/-pi range every ~100ms, traced through
        # ekf_node's gyro-rate-only motion-model input straight back to these
        # unscaled counts (raw az~8556-8576 read as 8556-8576 rad/s^2 instead of
        # ~9.8 m/s^2 — ~2 orders of magnitude too large). See
        # esp32_protocol.scale_imu_raw's own docstring for the conversion, and its
        # sensitivity constants' comments for the confidence level behind each axis
        # (accel is real-physics-verified against gravity; gyro is a flagged,
        # unverified best estimate pending a real calibration test).
        ax, ay, az, gx, gy, gz = scale_imu_raw(info.ax, info.ay, info.az,
                                               info.gx, info.gy, info.gz)
        msg.linear_acceleration.x = ax
        msg.linear_acceleration.y = ay
        msg.linear_acceleration.z = az
        # Subtract the resting offset. "Stationary" = wheels report zero AND nothing is
        # asking the robot to move: either the watchdog has zeroed the command
        # (nobody is publishing) or the latest command is itself zero. The second
        # case was missing until 2026-11-18: key_teleop publishes zero-speed commands
        # at 20 Hz while idle, so _stopped never became True, the offset was never
        # learned, and a 4-minute mapping drive carried the full +0.27 deg/s (about
        # 65 deg of false heading). The estimator itself rejects windows that still
        # contain motion (robot carried or turned by hand).
        commanded_still = self._stopped or self._cmd_is_zero
        stationary = (info.speed_l == 0 and info.speed_r == 0 and commanded_still)
        bx, by, bz = self._gyro_bias.update(gx, gy, gz, stationary)
        msg.angular_velocity.x = gx - bx
        msg.angular_velocity.y = gy - by
        msg.angular_velocity.z = gz - bz
        # self._last_orientation (from a T:1002 reply, if one has arrived yet) is NOT
        # used to populate msg.orientation here — its quaternion axis convention is
        # unconfirmed against real hardware (see __init__'s comment). Real, scoped
        # follow-up, not silently dropped.
        msg.orientation_covariance[0] = -1.0  # orientation not populated from this message
        # Gyro: a real, positive variance (see GYRO_VARIANCE_RAD2_S2). This was -1
        # from 2026-08-12 (commit bf764d1) to 2026-11-16, intended as "not
        # characterized" — but robot_localization reads -1 in element [0] as "ignore
        # the angular velocity", so ekf_node never fused the gyro at all. On the real
        # robot the fused odom->base_footprint yaw stayed at exactly 0.0 while the
        # robot turned (bag: reports/robot_boot_20261116_navonly), so Nav2's
        # rotate-to-heading never finished: the "hits a wall, then circles" symptom.
        # HIL never saw it — Gazebo supplies its own IMU message there.
        msg.angular_velocity_covariance[0] = GYRO_VARIANCE_RAD2_S2
        msg.angular_velocity_covariance[4] = GYRO_VARIANCE_RAD2_S2
        msg.angular_velocity_covariance[8] = GYRO_VARIANCE_RAD2_S2
        # Accel: -1 stays. ekf.yaml does not fuse linear acceleration, so "ignore"
        # is exactly the intended meaning, and its noise is uncharacterized.
        msg.linear_acceleration_covariance[0] = -1.0
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
