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
"""Cold-start goal-result classification for NavRunner (Task 13a).

Pure Python — no ROS imports — so the retry DECISION logic is unit-testable in
stage-1-quality (bare ubuntu-latest, no ROS2), like nav_fleet.missions. nav_runner.py
imports the constants + classifier from here and wraps its accept-then-await cycle in a
bounded retry loop.

The defect this guards (signature in .superpowers/sdd/task-12b-report.md, hit 3 of 6 cold
starts on 2026-07-18): on a FRESH mission_runner process, the first NavigateToPose goal is
sometimes accepted by bt_navigator and then aborted in ~0.1-0.25 s BEFORE the robot moves —
a bt_navigator -> controller_server FollowPath ack-timeout race while the cold
controller_server finishes coming up. A warm goal in an already-running process does not hit
it. The fix mirrors the existing goal-REJECTED retry: resend the goal (bounded) when a
non-success result arrives fast AND with the robot essentially stationary. A slow failure, or
one where the robot actually drove, is a REAL failure and is never retried.
"""

# A non-success result arriving within this window of goal-accept is consistent with the
# cold ack-timeout race (a real navigation attempt that fails takes far longer — it drives,
# replans, exhausts recoveries). Measured aborts were 0.1-0.25 s; 2.0 s leaves generous
# headroom without reaching into real-failure territory.
COLD_ABORT_WINDOW_S = 2.0
# "Zero displacement" tolerance. AMCL pose jitters a few cm at rest; a genuine cold abort
# fires before the controller emits any cmd_vel, so true motion is ~0. 0.10 m cleanly
# separates jitter from a robot that actually started driving.
COLD_ABORT_MAX_DISP_M = 0.10
# Bounded resends (mirrors the 5x accept-rejection retry's spirit; 3 is enough — live, a
# retried cold goal has always taken on the very next attempt).
COLD_ABORT_RETRIES = 3


def classify_result(succeeded, elapsed_s, displacement_m,
                    window_s=COLD_ABORT_WINDOW_S, max_disp_m=COLD_ABORT_MAX_DISP_M):
    """Classify a finished NavigateToPose goal result.

    Returns one of:
      'success'    — status was SUCCEEDED; done.
      'cold_abort' — non-success, arrived within window_s, robot essentially stationary
                     (displacement_m <= max_disp_m, or None when the pose was unmeasurable —
                     e.g. AMCL had not published yet on a cold start, which IS the case we
                     want to retry). Caller resends the goal, bounded.
      'failure'    — a real/slow failure: retrying would only mask a genuine regression.

    Pure: elapsed_s and displacement_m are measured by the caller from goal-accept to result.
    """
    if succeeded:
        return 'success'
    if elapsed_s <= window_s and (displacement_m is None or displacement_m <= max_disp_m):
        return 'cold_abort'
    return 'failure'
