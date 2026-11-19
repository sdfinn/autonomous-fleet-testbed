# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""Drive the robot from the keyboard, hold-to-move: for mapping drives and bench work.

    python3 key_teleop.py            (in a terminal on the Jetson, e.g. over ssh)

        q   w   e          w / s   forward / back
        a   s   d          a / d   spin left / right on the spot
                           q / e   forward while curving left / right
        space = stop now       x or Ctrl+C = quit

HOLD a key to move; let go and the robot stops by itself. That is the safety design:
a command only lives KEY_HOLD_TIMEOUT_S after the last key byte arrived, so a frozen
ssh session, a dropped WiFi link or a closed terminal all end in "stop" (and
esp32_driver's own 200 ms watchdog zeroes the wheels once this node goes quiet).
There is no "keep driving" mode on purpose: this robot has no collision avoidance.

No dependency beyond rclpy + geometry_msgs: teleop_twist_keyboard is not installed on
the Jetson, and its press-once-to-keep-moving behaviour is the wrong default here.
The key -> speed logic (TeleopState) is plain Python so it is unit-tested without ROS;
rclpy is imported inside main() for the same reason.
"""
import select
import sys
import termios
import time
import tty

# Slow on purpose: a mapping drive wants crisp scans, and the operator is steering
# over WiFi with 100-300 ms of lag.
LINEAR_SPEED_MPS = 0.15
REVERSE_SPEED_MPS = 0.10
# esp32_driver multiplies angular.z by its angular_cmd_gain (2.8, skid-steer scrub),
# so this is the real on-the-spot turn rate: about 30 deg/s.
ANGULAR_SPEED_RPS = 0.5
CURVE_ANGULAR_SPEED_RPS = 0.3

# A terminal repeats a held key ~30x/s, but only after an initial pause of up to
# ~0.5 s. The timeout has to bridge that pause or every move would start with a stutter.
KEY_HOLD_TIMEOUT_S = 0.6
PUBLISH_HZ = 20.0          # well inside esp32_driver's 200 ms watchdog

# key -> (linear m/s, angular rad/s); +angular = left
KEY_BINDINGS = {
    'w': (LINEAR_SPEED_MPS, 0.0),
    's': (-REVERSE_SPEED_MPS, 0.0),
    'a': (0.0, ANGULAR_SPEED_RPS),
    'd': (0.0, -ANGULAR_SPEED_RPS),
    'q': (LINEAR_SPEED_MPS, CURVE_ANGULAR_SPEED_RPS),
    'e': (LINEAR_SPEED_MPS, -CURVE_ANGULAR_SPEED_RPS),
}
STOP_KEYS = (' ',)
QUIT_KEYS = ('x', '\x03', '\x04')      # x, Ctrl+C, Ctrl+D (raw mode delivers them as bytes)


class TeleopState:
    """Turns key presses + the passage of time into the velocity to command right now."""

    def __init__(self):
        self._command = (0.0, 0.0)
        self._last_key_time = None
        self.quit_requested = False

    def on_key(self, key, now):
        key = key.lower()
        if key in QUIT_KEYS:
            self.quit_requested = True
            self._command, self._last_key_time = (0.0, 0.0), None
        elif key in STOP_KEYS:
            self._command, self._last_key_time = (0.0, 0.0), None
        elif key in KEY_BINDINGS:
            self._command, self._last_key_time = KEY_BINDINGS[key], now
        # any other key: ignored, and it does NOT keep a running command alive

    def command(self, now):
        """(linear, angular) to publish at time `now`; zero once the key has been released."""
        if self._last_key_time is None or now - self._last_key_time > KEY_HOLD_TIMEOUT_S:
            return (0.0, 0.0)
        return self._command


def main():
    import rclpy
    from geometry_msgs.msg import Twist

    if not sys.stdin.isatty():
        sys.exit('key_teleop needs a real terminal (use `ssh -t`), stdin is not a tty')
    rclpy.init()
    node = rclpy.create_node('key_teleop')
    topic = node.declare_parameter('cmd_vel_topic', '/robot_001/cmd_vel').value
    pub = node.create_publisher(Twist, topic, 10)
    state = TeleopState()
    print(__doc__.split('HOLD a key')[0].split('\n', 2)[2])
    print(f'HOLD a key to move, release to stop.  Publishing on {topic}\r')

    saved = termios.tcgetattr(sys.stdin)
    last_shown = None
    try:
        tty.setraw(sys.stdin.fileno())
        while rclpy.ok() and not state.quit_requested:
            readable, _, _ = select.select([sys.stdin], [], [], 1.0 / PUBLISH_HZ)
            now = time.monotonic()
            if readable:
                state.on_key(sys.stdin.read(1), now)
            linear, angular = state.command(now)
            msg = Twist()
            msg.linear.x, msg.angular.z = linear, angular
            pub.publish(msg)
            if (linear, angular) != last_shown:
                sys.stdout.write(f'\r  forward {linear:+.2f} m/s   turn {angular:+.2f} rad/s   ')
                sys.stdout.flush()
                last_shown = (linear, angular)
    finally:
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, saved)
        pub.publish(Twist())           # explicit stop on the way out
        time.sleep(0.1)
        print('\nkey_teleop: stopped')
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
