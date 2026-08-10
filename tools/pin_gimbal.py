#!/usr/bin/env python3
# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""One-off CLI to pin the Waveshare UGV-PT's pan-tilt gimbal to a fixed pose over
the ESP32 sub-controller's serial link — RealRobotStartup.md A2's gimbal checklist
item. This only needs to run ONCE at setup time (the mast stays wherever it's last
commanded), so it's a standalone script, not a ROS2 node/topic — same treatment this
project already gives other one-off hardware setup actions
(tools/calibrate_ball_range.py, tools/direct_drive_test.py).

Sends esp32_protocol.encode_gimbal_cmd's T:133 command directly over pyserial — no
ROS2, no esp32_driver.py (that node owns the link only while running; this script
assumes esp32_driver ISN'T running, since two writers on the same serial port would
interleave and corrupt lines). Stop robot_boot.sh/esp32_driver first if either is up.

Usage (defaults match the ESP32's real hardware wiring, see RealRobotStartup.md A2):
    python -m tools.pin_gimbal
    python -m tools.pin_gimbal --pan 0 --tilt 0
    python -m tools.pin_gimbal --pan 10 --tilt -5 --port /dev/ttyTHS1 --baud 115200

Field names/ranges for T:133 are sourced from Waveshare's wiki via web search (direct
fetches 403'd — see esp32_protocol.encode_gimbal_cmd's docstring) — NOT yet confirmed
against real hardware. Run this once, watch the physical mast, and confirm it actually
moves to forward/level before trusting the command shape.
"""
import argparse
import json
import sys

import serial

from nav_fleet.esp32_protocol import encode_gimbal_cmd

DEFAULT_PORT = '/dev/ttyTHS1'  # confirmed real wiring, RealRobotStartup.md A2
DEFAULT_BAUD = 115200  # confirmed against vendor firmware source, same doc


def send_gimbal_cmd(port, baud, pan_deg, tilt_deg):
    """Opens the serial link, sends one T:133 line, closes it. Returns the dict that
    was sent (for the CLI to print) — kept separate from main() so a test can mock
    serial.Serial directly instead of touching real hardware."""
    cmd = encode_gimbal_cmd(pan_deg, tilt_deg)
    line = (json.dumps(cmd) + '\n').encode('utf-8')
    with serial.Serial(port, baud, timeout=1.0) as ser:
        ser.write(line)
    return cmd


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--pan', type=float, default=0.0,
                        help='pan angle in degrees (0 = forward, default: 0)')
    parser.add_argument('--tilt', type=float, default=0.0,
                        help='tilt angle in degrees (0 = level, default: 0)')
    parser.add_argument('--port', default=DEFAULT_PORT,
                        help=f'serial device (default: {DEFAULT_PORT})')
    parser.add_argument('--baud', type=int, default=DEFAULT_BAUD,
                        help=f'baud rate (default: {DEFAULT_BAUD})')
    args = parser.parse_args(argv)

    try:
        cmd = send_gimbal_cmd(args.port, args.baud, args.pan, args.tilt)
    except serial.SerialException as exc:
        print(f'ERROR: cannot open {args.port} @ {args.baud}: {exc}', file=sys.stderr)
        print('  Is esp32_driver (or robot_boot.sh) already holding this port open?',
              file=sys.stderr)
        return 1

    print(f'Sent: {json.dumps(cmd)}')
    print('Check the physical mast — pan should be 0=forward, tilt 0=level '
          '(or whatever you passed). If it did NOT move as expected, the T:133 '
          "field names/ranges need re-checking against real hardware before this "
          'is trusted — see this file\'s module docstring.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
