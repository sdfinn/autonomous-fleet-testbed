# Copyright 2026 Mike
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Mission executor: runs a named mission (waypoints + action primitives) against Nav2.

Run from the repo root (same reason as tools/agentic_loop.py — module imports):

    python -m nav_fleet.mission_runner mission1

Requires a live sim (sim_launch.py, or sim_only + nav2_only for HIL). Logs one telemetry
row per mission to FLEET_DB via tools.telemetry_logger.
"""
import argparse
import os
import pathlib
import time
import traceback

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image

from nav_fleet.image_io import image_msg_to_png
from nav_fleet.missions import MISSIONS, validate_mission
from nav_fleet.nav_runner import NavRunner
from nav_fleet.semantic_map import SEMANTIC_MAP
from tools.telemetry_logger import log_run

PHOTO_DIR = pathlib.Path('reports/photos')
NAV_TIMEOUT_S = 90.0


class MissionRunner(Node):

    def __init__(self):
        super().__init__('mission_runner')
        self.nav = NavRunner()
        self.photo_paths = []
        self.nav_durations = []
        self.nav_errors = []
        self._latest_image = None
        self.create_subscription(
            Image, '/robot_001/camera/image_raw', self._image_cb, 10
        )

    def _image_cb(self, msg):
        self._latest_image = msg

    def take_picture(self, label, timeout=15.0):
        """Capture one fresh camera frame and save it as a PNG under reports/photos/."""
        self._latest_image = None  # force a frame newer than this call
        deadline = time.time() + timeout
        while self._latest_image is None and time.time() < deadline:
            rclpy.spin_once(self, timeout_sec=0.1)
        if self._latest_image is None:
            self.get_logger().error(f'no camera frame within {timeout}s')
            return False
        PHOTO_DIR.mkdir(parents=True, exist_ok=True)
        path = PHOTO_DIR / f"{label}_{time.strftime('%Y%m%d_%H%M%S')}.png"
        image_msg_to_png(self._latest_image, str(path))
        self.photo_paths.append(str(path))
        self.get_logger().info(f'photo saved: {path}')
        return True

    def run_mission(self, name):
        steps = MISSIONS[name]
        validate_mission(steps)
        for i, step in enumerate(steps, start=1):
            self.get_logger().info(f'[{name}] step {i}/{len(steps)}: {step.label}')
            if step.action == 'navigate':
                x, y = SEMANTIC_MAP[step.location]
                ok = self.nav.send_goal(x, y, timeout=NAV_TIMEOUT_S, yaw=step.yaw)
                # FAIL-leg policy (Session 16): a failed/timed-out leg's duration measures
                # the timeout, not the robot — keep it out of the row's aggregate metrics.
                if ok:
                    if self.nav.last_duration_s is not None:
                        self.nav_durations.append(self.nav.last_duration_s)
                    if self.nav.last_position_error is not None:
                        self.nav_errors.append(self.nav.last_position_error)
            else:  # take_picture — validate_mission guarantees the action set
                ok = self.take_picture(f'{name}_step{i}')
            if not ok:
                self.get_logger().error(f'[{name}] step {i} ({step.label}) FAILED')
                return False
        return True


def _mean(values):
    return sum(values) / len(values) if values else None


def _log_mission(name, ok, runner):
    nav = runner.nav if runner is not None else None
    log_run(
        scenario=name,
        steps=len(MISSIONS[name]),
        final_x=nav.last_final_x if nav is not None and nav.last_final_x is not None else 0.0,
        final_y=nav.last_final_y if nav is not None and nav.last_final_y is not None else 0.0,
        result='PASS' if ok else 'FAIL',
        step_log=[],
        robot_id=os.environ.get('ROBOT_ID', 'robot_001'),
        robot_type='jetson_ugv_pt',
        runner_type=os.environ.get('RUNNER_TYPE', 'local'),
        sim_engine=os.environ.get('SIM_ENGINE', 'gazebo'),
        nav_success_rate=1.0 if ok else 0.0,
        mean_position_error=_mean(runner.nav_errors) if runner is not None else None,
        mean_time_to_goal=_mean(runner.nav_durations) if runner is not None else None,
        power_mode=os.environ.get('POWER_MODE'),
    )


def main():
    parser = argparse.ArgumentParser(description='Run a named mission against Nav2.')
    parser.add_argument('mission', choices=sorted(MISSIONS))
    args = parser.parse_args()

    rclpy.init()
    runner = None
    ok = False
    try:
        # Constructed INSIDE the try: a constructor crash (e.g. rclpy/DDS failure) must
        # still produce the FAIL telemetry row that stage-4-hil's verdict depends on.
        runner = MissionRunner()
        ok = runner.run_mission(args.mission)
    except Exception as exc:  # still log a FAIL row on crash — docstring contract
        traceback.print_exc()
        print(f'mission {args.mission} crashed: {exc!r}')
    finally:
        rclpy.try_shutdown()
    _log_mission(args.mission, ok, runner)

    print(f"Mission {args.mission}: {'PASS' if ok else 'FAIL'}")
    for p in (runner.photo_paths if runner is not None else []):
        print(f'  photo: {p}')
    raise SystemExit(0 if ok else 1)


if __name__ == '__main__':
    main()
