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
"""Rolling failure-evidence bag recorder (S17 Piece 3): "a mission fails on the real
robot in another room — can you determine why, from the workstation, after the fact,
without re-running it?"

Uses rosbag2's own `--snapshot-mode` (no rclpy Python API for this — CLI-only): `ros2
bag record --snapshot-mode` buffers the declared topics in memory ONLY (bounded by
`--max-cache-size`, zero disk writes) until the `/rosbag2_recorder/snapshot` service is
called, which persists whatever is currently buffered to disk. A passing mission never
calls it — zero disk cost for the overwhelmingly common case. A failing mission calls
it once, so the bag holds a genuine trailing window, not an approximation (record-
everything-then-delete-on-PASS was considered and rejected once this flag was found).

mission_runner.py's main() owns the start -> (maybe) snapshot -> stop lifecycle, one
recorder per mission process.
"""
import pathlib
import shutil
import signal
import subprocess
import time

TOPICS = (
    '/robot_001/cmd_vel',
    '/robot_001/scan',
    '/robot_001/amcl_pose',
    '/robot_001/navigate_to_pose/_action/status',
)

BAG_DIR = pathlib.Path('reports/failure_bags')
SNAPSHOT_SERVICE = '/rosbag2_recorder/snapshot'
SNAPSHOT_SERVICE_TYPE = 'rosbag2_interfaces/srv/Snapshot'


def start(scenario, bag_dir=BAG_DIR, topics=TOPICS, max_cache_size=None):
    """Launch a snapshot-mode `ros2 bag record` in the background. Returns
    (Popen, bag_path) — bag_path only actually exists on disk after a successful
    snapshot() call."""
    bag_dir = pathlib.Path(bag_dir)
    bag_dir.mkdir(parents=True, exist_ok=True)
    bag_path = bag_dir / f'{scenario}_{time.strftime("%Y%m%d_%H%M%S")}'
    cmd = ['ros2', 'bag', 'record', '--snapshot-mode', '-o', str(bag_path), *topics]
    if max_cache_size is not None:
        cmd += ['--max-cache-size', str(max_cache_size)]
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return proc, bag_path


def snapshot():
    """Ask the running recorder to persist its current in-memory window to disk.
    Best-effort: a failed call must never be treated as a mission-level failure, so
    this returns False rather than raising."""
    result = subprocess.run(
        ['ros2', 'service', 'call', SNAPSHOT_SERVICE, SNAPSHOT_SERVICE_TYPE, '{}'],
        capture_output=True, text=True, timeout=10)
    return result.returncode == 0 and 'success=True' in result.stdout


def stop(proc, bag_path, keep):
    """Stop the recorder (SIGINT — graceful rosbag2 shutdown, this repo's standing
    convention over SIGKILL for ROS2 processes) and discard the bag directory unless
    `keep` (a no-op if snapshot() was never called — there is nothing on disk yet)."""
    proc.send_signal(signal.SIGINT)
    proc.wait(timeout=10)
    if not keep and bag_path.exists():
        shutil.rmtree(bag_path)
