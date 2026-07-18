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
"""Nav2 goal-sending test runner."""

import math
import time
import rclpy
from rclpy.node import Node
from rclpy.action import ActionClient
from rclpy.time import Time
from nav2_msgs.action import NavigateToPose
from geometry_msgs.msg import PoseStamped, PoseWithCovarianceStamped

from nav_fleet.goal_retry import (COLD_ABORT_RETRIES, classify_result)
from nav_fleet.missions import yaw_to_quaternion


class NavRunner(Node):

    def __init__(self):
        super().__init__('nav_runner')
        self._action_client = ActionClient(
            self, NavigateToPose, '/robot_001/navigate_to_pose'
        )
        # Telemetry from the most recent send_goal() call — read by the test session's
        # telemetry fixture after all tests complete.
        self.last_result = None
        self.last_duration_s = None
        self.last_steps = None
        self.last_final_x = None
        self.last_final_y = None
        self.last_position_error = None
        self.last_interrupt = None

        self._latest_pose = None
        self.create_subscription(
            PoseWithCovarianceStamped, '/robot_001/amcl_pose', self._pose_cb, 10
        )

    def _pose_cb(self, msg):
        self._latest_pose = msg.pose.pose

    def _pose_xy(self):
        """Latest AMCL (x, y), or None if no pose has arrived yet (cold start) — the
        cold-abort displacement check treats None as 'unmeasured' (still eligible to retry)."""
        if self._latest_pose is None:
            return None
        return (self._latest_pose.position.x, self._latest_pose.position.y)

    def _cancel_goal(self, goal_handle, timeout_s=5.0):
        """Cancel an in-flight Nav2 goal and wait briefly for the server to confirm —
        the controller stops publishing cmd_vel on cancellation, which IS the stop."""
        fut = goal_handle.cancel_goal_async()
        deadline = time.time() + timeout_s
        while time.time() < deadline and not fut.done():
            rclpy.spin_once(self, timeout_sec=0.1)
        if not fut.done():
            self.get_logger().warning('cancel_goal not confirmed within timeout')

    def send_goal(self, x, y, timeout=90.0, yaw=None, interrupt_cb=None, spin_extra=None):
        self.last_interrupt = None
        start_time = time.time()
        steps = 0

        def spin():
            nonlocal steps
            rclpy.spin_once(self, timeout_sec=0.1)
            steps += 1

        if not self._action_client.wait_for_server(timeout_sec=15.0):
            self.get_logger().error('Nav2 action server unavailable')
            return self._finish(False, x, y, start_time, steps)

        goal = NavigateToPose.Goal()
        goal.pose = PoseStamped()
        goal.pose.header.frame_id = 'map'
        goal.pose.header.stamp = Time().to_msg()  # zero = use latest TF, works with sim time
        goal.pose.pose.position.x = x
        goal.pose.pose.position.y = y
        if yaw is None:
            goal.pose.pose.orientation.w = 1.0
        else:
            z, w = yaw_to_quaternion(yaw)
            goal.pose.pose.orientation.z = z
            goal.pose.pose.orientation.w = w

        # One accept-then-await cycle. Returns a tuple whose first element is the outcome
        # kind: 'send_fail' (rejected/timed-out — terminal), 'interrupt' (caller cancelled —
        # terminal), or 'result' (finished; carries succeeded/elapsed/displacement so the
        # outer loop can classify a cold-start abort). Nested so it shares spin()/steps/goal.
        def attempt():
            # wait_for_server() only confirms the action is discoverable on the ROS graph,
            # which happens as soon as bt_navigator's node exists — not that its lifecycle
            # state is ACTIVE. A goal sent in that gap is rejected ("Action server is
            # inactive"), so retry a few times with a short backoff rather than treating one
            # rejection as final.
            goal_handle = None
            for a in range(5):
                send_goal_future = self._action_client.send_goal_async(goal)

                deadline = time.time() + 10.0
                while time.time() < deadline:
                    if send_goal_future.done():
                        break
                    spin()

                if not send_goal_future.done():
                    self.get_logger().warning('Goal send timed out')
                    return ('send_fail',)

                goal_handle = send_goal_future.result()
                if goal_handle.accepted:
                    break

                self.get_logger().warning(
                    f'Goal rejected (attempt {a + 1}/5) — bt_navigator likely not '
                    'active yet, retrying')
                time.sleep(1.0)
            else:
                self.get_logger().error('Goal rejected after all retries')
                return ('send_fail',)

            accept_time = time.time()
            self._last_goal_handle = goal_handle  # for cancel-on-final-failure (zombie guard)
            start_xy = self._pose_xy()  # for the cold-abort displacement check
            result_future = goal_handle.get_result_async()

            deadline = time.time() + timeout
            while time.time() < deadline:
                if result_future.done():
                    break
                spin()
                # goal finished during spin() — its real result wins over a
                # same-iteration interrupt (review 2026-07-17 race finding)
                if result_future.done():
                    break
                if spin_extra is not None:
                    # Service the caller's subscriptions (e.g. mission_runner's detection
                    # topic) — send_goal's spin loop only spins THIS node otherwise.
                    rclpy.spin_once(spin_extra, timeout_sec=0.0)
                if interrupt_cb is not None:
                    hit = interrupt_cb()
                    if hit:
                        self.get_logger().warning(f'goal interrupted: {hit!r} — cancelling')
                        self.last_interrupt = hit
                        self._cancel_goal(goal_handle)
                        return ('interrupt',)

            if not result_future.done():
                self.get_logger().warning('Goal wait timed out')
                return ('send_fail',)

            succeeded = result_future.result().status == 4
            elapsed = time.time() - accept_time
            end_xy = self._pose_xy()
            displacement = (math.hypot(end_xy[0] - start_xy[0], end_xy[1] - start_xy[1])
                            if start_xy is not None and end_xy is not None else None)
            return ('result', succeeded, elapsed, displacement)

        # Cold-start abort retry (Task 13a, see nav_fleet.goal_retry): a fresh process's
        # first goal is sometimes accepted then aborted in ~0.1-0.25 s before the robot moves
        # (bt_navigator->controller_server FollowPath ack-timeout race). Resend the goal,
        # bounded, ONLY for that signature; a real/slow failure or an interrupt is terminal.
        for cold_attempt in range(COLD_ABORT_RETRIES + 1):
            outcome = attempt()
            kind = outcome[0]
            if kind in ('send_fail', 'interrupt'):
                return self._finish(False, x, y, start_time, steps)
            _, succeeded, elapsed, displacement = outcome
            verdict = classify_result(succeeded, elapsed, displacement)
            if verdict == 'success':
                return self._finish(True, x, y, start_time, steps)
            if verdict == 'cold_abort' and cold_attempt < COLD_ABORT_RETRIES:
                disp_s = 'unmeasured' if displacement is None else f'{displacement:.3f} m'
                self.get_logger().error(
                    f'COLD-START GOAL ABORT (retry {cold_attempt + 1}/{COLD_ABORT_RETRIES}): '
                    f'non-success result in {elapsed:.2f}s, displacement {disp_s} — Nav2 '
                    'cold-goal ack-timeout race, resending the same goal')
                # Escalating backoff (live evidence 2026-07-18): rapid ~1 s resends failed
                # 6/6 — they land inside the same controller not-ready window. The bash-level
                # retries that DID work had multi-second process-restart gaps; mirror that.
                time.sleep(2.0 * (cold_attempt + 1))
                continue
            if verdict == 'cold_abort':
                self.get_logger().error(
                    f'cold-start abort persisted after {COLD_ABORT_RETRIES} retries — '
                    'treating as a real failure')
            # Zombie guard (2026-07-18, Jetson nav2_hil.log): bt_navigator can abort our
            # handle while the controller still executes the delivered path — the robot
            # then drives with NO supervising mission. Cancel whatever is outstanding
            # before reporting failure; on the real robot this is a safety issue.
            if getattr(self, '_last_goal_handle', None) is not None:
                self._cancel_goal(self._last_goal_handle)
            return self._finish(False, x, y, start_time, steps)

    def _finish(self, succeeded, goal_x, goal_y, start_time, steps):
        self.last_result = succeeded
        self.last_duration_s = time.time() - start_time
        self.last_steps = steps
        if self._latest_pose is not None:
            self.last_final_x = self._latest_pose.position.x
            self.last_final_y = self._latest_pose.position.y
            self.last_position_error = math.hypot(
                self.last_final_x - goal_x, self.last_final_y - goal_y
            )
        return succeeded


def main():
    rclpy.init()
    node = NavRunner()
    success = node.send_goal(1.0, 1.0)
    if success:
        print('Goal succeeded')
    else:
        print('Goal failed')
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
