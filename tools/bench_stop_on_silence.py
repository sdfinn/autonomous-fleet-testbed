#!/usr/bin/env python3
# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""BENCH TEST, WHEELS OFF THE GROUND: does the motor board stop by itself when the
Jetson goes silent?

    python3 tools/bench_stop_on_silence.py                # the command the driver uses (T:1)
    python3 tools/bench_stop_on_silence.py --legacy-t13   # the old command, to see it FAIL

Run on the Jetson with esp32_driver NOT running (the serial port is exclusive) and the
robot on a stand so no wheel touches anything.

What it does: sets the board's stop-on-silence timeout, drives both sides slowly for
two seconds, then sends NOTHING -- no stop command -- and watches the wheel speeds the
board reports. PASS = the wheels reach zero on their own within the timeout plus a
margin. Whatever the verdict, an explicit stop is sent at the end (this script is still
alive, unlike the failure it imitates), and Ctrl+C also stops.

Why (2026-11-18): the Jetson lost power in the middle of a spin and the robot spun
until its power switch was thrown. The firmware has a stop-on-silence timer, but only
wheel-speed commands (T:1) re-arm it; the driver had been sending T:13, which leaves it
disarmed 3 s after power-on. See esp32_protocol.encode_wheel_speed_cmd. Nothing that
runs on the Jetson can cover a dead Jetson, so this is the check that matters -- repeat
it after any firmware update or change to how motion commands are sent.
"""
import argparse
import json
import sys
import time

TEST_SPEED_MPS = 0.10       # slow: this is a stand test, not a drive
DRIVE_S = 2.0
COMMAND_HZ = 20.0
OBSERVE_S = 6.0             # twice the firmware's 3 s default, so a default-only stop is seen too
STOP_MARGIN_S = 0.7         # motor run-down + one status period, on top of the timeout


def time_to_stop(samples, silence_start):
    """Seconds from silence_start until the wheels were at rest and STAYED at rest.

    samples: [(t, left_speed, right_speed)] as reported by the board, in time order.
    Returns None if they never came to rest (or there is nothing after silence_start).
    """
    after = [(t, left, right) for t, left, right in samples if t >= silence_start]
    if not after:
        return None
    stop_t = None
    for t, left, right in after:
        if left == 0 and right == 0:
            stop_t = t if stop_t is None else stop_t
        else:
            stop_t = None                     # moved again: that earlier zero did not hold
    return None if stop_t is None else stop_t - silence_start


def verdict(stop_after_s, timeout_ms):
    """(passed, one-line explanation)."""
    limit = timeout_ms / 1000.0 + STOP_MARGIN_S
    if stop_after_s is None:
        return False, f'wheels were STILL TURNING {OBSERVE_S:.0f} s after the last command'
    if stop_after_s <= limit:
        return True, f'wheels stopped by themselves {stop_after_s:.2f} s after the last command'
    return False, (f'wheels stopped after {stop_after_s:.2f} s -- later than the '
                   f'{limit:.2f} s allowed for a {timeout_ms} ms timeout')


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--device', default='/dev/ttyTHS1')
    ap.add_argument('--timeout-ms', type=int, default=500)
    ap.add_argument('--legacy-t13', action='store_true',
                    help='drive with T:13 instead of T:1 (expected to FAIL: shows the hazard)')
    ap.add_argument('--yes', action='store_true', help='skip the wheels-off-the-ground prompt')
    args = ap.parse_args(argv)
    import serial

    if not args.yes:
        answer = input('Wheels will turn. Is the robot on a stand with ALL wheels off '
                       'the ground? Type yes: ')
        if answer.strip().lower() != 'yes':
            print('not started')
            return 2

    ser = serial.Serial(args.device, 115200, timeout=0.05)

    def send(cmd):
        ser.write((json.dumps(cmd) + '\n').encode())

    def stop_now():
        send({'T': 1, 'L': 0.0, 'R': 0.0})
        send({'T': 13, 'X': 0.0, 'Z': 0.0})

    samples, volts = [], []

    def read_status(until):
        while time.monotonic() < until:
            line = ser.readline().decode(errors='ignore').strip()
            try:
                data = json.loads(line)
            except ValueError:
                continue
            if isinstance(data, dict) and data.get('T') == 1001:
                samples.append((time.monotonic(), data.get('L', 0), data.get('R', 0)))
                if 'v' in data:
                    volts.append(data['v'] / 100.0)

    try:
        send({'T': 131, 'cmd': 1})                      # status stream on
        send({'T': 136, 'cmd': args.timeout_ms})        # the board's stop-on-silence timeout
        read_status(time.monotonic() + 1.0)
        if volts:
            print(f'battery {sorted(volts)[len(volts) // 2]:.2f} V')
        kind = 'T:13 (legacy)' if args.legacy_t13 else 'T:1'
        print(f'driving both sides at {TEST_SPEED_MPS} m/s for {DRIVE_S:.0f} s with {kind} ...')
        end = time.monotonic() + DRIVE_S
        while time.monotonic() < end:
            if args.legacy_t13:
                send({'T': 13, 'X': TEST_SPEED_MPS, 'Z': 0.0})
            else:
                send({'T': 1, 'L': TEST_SPEED_MPS, 'R': TEST_SPEED_MPS})
            read_status(time.monotonic() + 1.0 / COMMAND_HZ)
        silence_start = time.monotonic()
        moving = any(left != 0 or right != 0 for _, left, right in samples[-10:])
        print(f'... now SILENT for {OBSERVE_S:.0f} s (no stop command sent)')
        read_status(silence_start + OBSERVE_S)
    except KeyboardInterrupt:
        print('\ninterrupted')
        return 130
    finally:
        stop_now()
        time.sleep(0.2)
        stop_now()
        ser.close()

    if not moving:
        print('INVALID: the wheels never turned, so nothing was tested '
              '(battery critical? wrong chassis type? motor power off?)')
        return 2
    passed, why = verdict(time_to_stop(samples, silence_start), args.timeout_ms)
    print(('PASS: ' if passed else 'FAIL: ') + why)
    if not passed:
        print('      -> the board will NOT stop the robot if the Jetson dies. Do not drive.')
    return 0 if passed else 1


if __name__ == '__main__':
    sys.exit(main())
