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
"""ROS2 topic Hz + collision metric collector."""

import json
import time

import rclpy
from nav_msgs.msg import Odometry
from rclpy.node import Node
from sensor_msgs.msg import Image, LaserScan

# A scan return closer than this is scored as a collision (S17 review CR-10: was a bare
# magic number). Derivation: the lidar sits inside the chassis footprint; the URDF's
# body half-width is ~0.11 m, so a real obstacle can never legitimately return closer
# than ~0.12 m — anything nearer means contact (or a self-return, which the URDF's
# camera-geometry removal already prevents).
COLLISION_RANGE_M = 0.12


class MetricsCollector(Node):
    def __init__(self):
        super().__init__('metrics_collector')
        self._odom_times = []
        self._scan_times = []
        self._camera_times = []
        self._min_range = float('inf')
        self.last_metrics = None

        self.subscription_odom = self.create_subscription(
            Odometry,
            '/robot_001/odom',
            self._odom_cb,
            10
        )

        self.subscription_scan = self.create_subscription(
            LaserScan,
            '/robot_001/scan',
            self._scan_cb,
            10
        )

        self.subscription_camera = self.create_subscription(
            Image,
            '/robot_001/camera/image_raw',
            self._camera_cb,
            10
        )

    def _odom_cb(self, msg):
        self._odom_times.append(time.time())

    def _scan_cb(self, msg):
        self._scan_times.append(time.time())
        valid = [r for r in msg.ranges if msg.range_min < r < msg.range_max]
        if valid:
            self._min_range = min(self._min_range, min(valid))

    def _camera_cb(self, msg):
        self._camera_times.append(time.time())

    def collect(self, duration=5.0):
        time_start = time.time()

        while time.time() < time_start + duration:
            rclpy.spin_once(self, timeout_sec=0.05)

        def hz(times):
            if len(times) < 2:
                return 0.0
            return (len(times) - 1) / (times[-1] - times[0])

        self.last_metrics = {
            'odom_hz': round(hz(self._odom_times), 1),
            'scan_hz': round(hz(self._scan_times), 1),
            'camera_hz': round(hz(self._camera_times), 1),
            'min_scan_range_m': round(self._min_range, 3),
            'collision_detected': self._min_range < COLLISION_RANGE_M
        }
        return self.last_metrics


def main():
    rclpy.init()
    node = MetricsCollector()
    metrics = node.collect(duration=5.0)
    print(json.dumps(metrics, indent=2))
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
