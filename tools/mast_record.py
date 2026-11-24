#!/usr/bin/env python3
# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""Record the mast (pan-tilt) USB camera to an AVI, with the wall-clock time on each frame.

    python3 tools/mast_record.py OUT.avi [--device /dev/v4l/by-id/...] [--seconds 3600]

scripts/robot_boot.sh starts this beside every mission (since 2026-11-23) and stops it
with SIGINT, which finalizes the file. The mast camera looks down the robot's path from
above the chassis camera, so the video shows what the robot did, not only what it
logged: on 2026-11-23 the robot touched a box and the only record was Mike's account.
Ten frames a second at 640 x 480 is about 20 MB a minute.

Needs OpenCV (cv2) and the camera; exits with a message, non-zero, when either is
missing. That is not fatal to a mission: robot_boot.sh says so and carries on.
"""
import argparse
import signal
import sys
import time

DEFAULT_DEVICE = '/dev/v4l/by-id/usb-Xitech_USB_Camera_20250606105-video-index0'
WIDTH, HEIGHT, FPS = 640, 480, 10


def frame_stamp(now):
    """HH:MM:SS.cc of a wall-clock time, as drawn on the frame."""
    return time.strftime('%H:%M:%S', time.localtime(now)) + '.%02d' % int((now % 1) * 100)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('out')
    parser.add_argument('--device', default=DEFAULT_DEVICE)
    parser.add_argument('--seconds', type=float, default=3600.0)
    args = parser.parse_args(argv)
    try:
        import cv2
    except ImportError:
        sys.exit('mast_record: OpenCV (cv2) is not installed')

    running = {'on': True}

    def _stop(*_):
        running['on'] = False
    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    cap = cv2.VideoCapture(args.device, cv2.CAP_V4L2)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, HEIGHT)
    cap.set(cv2.CAP_PROP_FPS, 30)
    if not cap.isOpened():
        sys.exit('mast_record: cannot open ' + args.device)
    out = cv2.VideoWriter(args.out, cv2.VideoWriter_fourcc(*'MJPG'), FPS, (WIDTH, HEIGHT))
    print('mast_record: recording %s to %s' % (args.device, args.out), flush=True)
    start = time.time()
    due = start
    frames = 0
    while running['on'] and time.time() - start < args.seconds:
        ok, frame = cap.read()
        if not ok:
            continue
        now = time.time()
        if now < due:
            continue                      # the camera sends 30 a second; keep 10
        due += 1.0 / FPS
        if due < now:
            due = now + 1.0 / FPS
        if frame.shape[1] != WIDTH or frame.shape[0] != HEIGHT:
            frame = cv2.resize(frame, (WIDTH, HEIGHT))
        stamp = frame_stamp(now)
        cv2.putText(frame, stamp, (8, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 4)
        cv2.putText(frame, stamp, (8, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        out.write(frame)
        frames += 1
    out.release()
    cap.release()
    print('mast_record: %d frames in %.1f s -> %s' % (frames, time.time() - start, args.out),
          flush=True)


if __name__ == '__main__':
    main()
