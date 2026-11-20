# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""operator_watch — holds the robot while the operator's machine cannot be reached.

Started by scripts/robot_boot.sh for an ATTENDED run (one started over SSH), bare-metal
next to esp32_driver. Pings the operator five times a second and publishes

    /robot_001/operator_hold   std_msgs/Bool, 10 Hz    True = wheels must not turn

which esp32_driver obeys (and treats a SILENT topic as True, so this node dying holds
the robot too). The decisions are nav_fleet.operator_link.LinkWatch; this file is the
wiring: the ping process, the topic, the beeps, and the exit code.

Exit codes:  0 = asked to stop (Ctrl+C / SIGTERM)
             3 = gave up: the operator did not come back (robot_boot.sh ends the run)

Beeps (switchable, parameter `beep`): two short = link lost, robot paused; one long =
link back, robot moves again in `resume_delay_s`; three low = giving up.
"""
import os
import subprocess
import sys
import tempfile
import threading
import time

import rclpy
from rclpy.node import Node
from std_msgs.msg import Bool

from nav_fleet.operator_link import (
    BEEPS, GAVE_UP, GIVE_UP, LOST, REGAINED, RESUMED, LinkWatch, is_reply_line,
    write_beep_wav)

EXIT_GAVE_UP = 3
PUBLISH_HZ = 10.0
PING_INTERVAL_S = 0.2
# After giving up, keep publishing hold=True this long so the three-beep pattern is
# heard before the node (and with it the sound) goes away.
GIVE_UP_LINGER_S = 1.8


class OperatorWatch(Node):

    def __init__(self):
        super().__init__('operator_watch')
        self.declare_parameter('operator_ip', '')
        self.declare_parameter('pause_after_s', 2.0)
        self.declare_parameter('give_up_after_s', 10.0)
        self.declare_parameter('resume_delay_s', 1.0)
        self.declare_parameter('beep', True)
        # ALSA device of the robot's USB speaker (`aplay -L`). Named by card id, not
        # index: indexes move when USB devices are plugged in a different order.
        self.declare_parameter('beep_device', 'plughw:CARD=Device,DEV=0')

        self._ip = self.get_parameter('operator_ip').value
        if not self._ip:
            raise ValueError('operator_watch: parameter operator_ip is required')
        self._watch = LinkWatch(
            now=time.monotonic(),
            pause_after_s=self.get_parameter('pause_after_s').value,
            give_up_after_s=self.get_parameter('give_up_after_s').value,
            resume_delay_s=self.get_parameter('resume_delay_s').value)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self.exit_code = 0
        self._gave_up_at = None
        self._ping = None

        self._beep_files = {}
        self._beep_failed = False
        if self.get_parameter('beep').value:
            self._beep_dir = tempfile.mkdtemp(prefix='operator_watch_')
            for name, pattern in BEEPS.items():
                self._beep_files[name] = str(
                    write_beep_wav(os.path.join(self._beep_dir, f'{name}.wav'), pattern))

        self._pub = self.create_publisher(Bool, '/robot_001/operator_hold', 10)
        self._reader = threading.Thread(target=self._read_ping, daemon=True)
        self._reader.start()
        self.create_timer(1.0 / PUBLISH_HZ, self._tick)
        self.get_logger().info(
            f'operator_watch up — pinging {self._ip} every {PING_INTERVAL_S}s; pause after '
            f'{self._watch.pause_after_s:.1f}s of silence, give up '
            f'{self._watch.give_up_after_s:.1f}s later; '
            f'beeps {"on" if self._beep_files else "off"}')

    # --- ping ---------------------------------------------------------------------
    def _start_ping(self):
        # -O: also print a line for every UNANSWERED probe, so the pipe never goes
        # quiet and ping notices (SIGPIPE) when this node is gone.
        return subprocess.Popen(
            ['ping', '-O', '-i', str(PING_INTERVAL_S), self._ip],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)

    def _read_ping(self):
        """One long-lived ping; restarted if it exits (interface down, etc.). While it
        is not answering, nothing calls reply() and LinkWatch runs out the clock."""
        while not self._stop.is_set():
            try:
                self._ping = self._start_ping()
            except OSError as exc:
                self.get_logger().error(f'operator_watch: cannot run ping: {exc}')
                self._stop.wait(1.0)
                continue
            for line in self._ping.stdout:
                if self._stop.is_set():
                    break
                if is_reply_line(line):
                    with self._lock:
                        self._watch.reply(time.monotonic())
            self._ping.wait()
            if not self._stop.is_set():
                self.get_logger().warn(
                    f'operator_watch: ping exited ({self._ping.returncode}); restarting it')
                self._stop.wait(0.5)

    # --- decisions ----------------------------------------------------------------
    def _tick(self):
        now = time.monotonic()
        with self._lock:
            events = self._watch.step(now)
            hold = self._watch.hold
            state = self._watch.state
        self._pub.publish(Bool(data=hold))
        for event in events:
            self._announce(event)
        if state == GAVE_UP:
            if self._gave_up_at is None:
                self._gave_up_at = now
                self.exit_code = EXIT_GAVE_UP
            elif now - self._gave_up_at >= GIVE_UP_LINGER_S:
                raise SystemExit(EXIT_GAVE_UP)

    def _announce(self, event):
        log = self.get_logger()
        if event == LOST:
            log.warn(f'operator_watch: operator {self._ip} silent for '
                     f'{self._watch.pause_after_s:.1f}s — robot PAUSED')
        elif event == REGAINED:
            log.info(f'operator_watch: operator {self._ip} is back — moving again in '
                     f'{self._watch.resume_delay_s:.1f}s')
        elif event == RESUMED:
            log.info('operator_watch: robot RELEASED')
        elif event == GIVE_UP:
            log.error(f'operator_watch: operator {self._ip} still silent '
                      f'{self._watch.give_up_after_s:.1f}s after the pause — GIVING UP')
        self._beep(event)

    def _beep(self, event):
        path = self._beep_files.get(event)
        if path is None or self._beep_failed:
            return
        try:
            # Not waited for: a beep must never delay holding the wheels.
            subprocess.Popen(
                ['aplay', '-q', '-D', self.get_parameter('beep_device').value, path],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL)
        except OSError as exc:
            self._beep_failed = True
            self.get_logger().warn(f'operator_watch: no beeps — cannot run aplay: {exc}')

    def summary(self):
        with self._lock:
            return (f'operator_watch: {self._watch.pauses} pause(s), longest silence '
                    f'{self._watch.longest_silence_s:.2f}s, final state {self._watch.state}')

    def destroy_node(self):
        self._stop.set()
        if self._ping is not None and self._ping.poll() is None:
            self._ping.terminate()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = OperatorWatch()
    code = 0
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 1
    finally:
        # print, not the ROS logger: the context may already be shut down by SIGINT.
        print(node.summary(), flush=True)
        node.destroy_node()
        rclpy.try_shutdown()
    sys.exit(code)


if __name__ == '__main__':
    main()
