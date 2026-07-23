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
from action_msgs.msg import GoalStatus
from rclpy.node import Node
from rclpy.action import ActionClient
from rclpy.time import Time
from nav2_msgs.action import NavigateToPose
from geometry_msgs.msg import PoseStamped, PoseWithCovarianceStamped

from nav_fleet.goal_retry import (COLD_ABORT_RETRIES, classify_result)
from nav_fleet.missions import yaw_to_quaternion
from tools.log_setup import build_env_manifest, git_sha, resolve_level

# S17 Piece 7 timing investigation (2026-07-22): the HIL motion-start stall — the
# robot sits still for a real, observable stretch after Nav2 logs "goal accepted" —
# is invisible in bt_navigator/controller_server's own log output. This threshold
# turns feedback pose deltas into a velocity estimate so "first real motion" becomes
# a timestamped log line instead of something that needs a human watching a screen.
# 0.03 m/s is comfortably above AMCL localization jitter while the robot is at rest.
MOTION_VELOCITY_THRESHOLD_MPS = 0.03


class NavRunner(Node):

    def __init__(self):
        super().__init__('nav_runner')
        self.get_logger().set_level(resolve_level())
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
        # Failure taxonomy (S17 Piece 3): 'goal_rejected' (couldn't send/accept the goal)
        # or 'nav_timeout' (accepted but didn't succeed — real failure or a persisted
        # cold-start abort). None on success or on an interrupt (a fired reaction is not
        # a failure). mission_runner.py reads this to populate telemetry's failure_reason.
        self.last_failure_reason = None
        # Cancel-on-final-failure zombie guard (Task 13 fix wave): the most recent goal
        # handle, so a failure path can cancel a still-executing controller instead of
        # leaving an unsupervised robot driving a goal Nav2's BT already gave up on.
        self._last_goal_handle = None

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
        # Reset ALL per-goal telemetry (S17 review CR-08): without this, a goal that
        # fails before AMCL publishes (or before _finish's pose branch runs) leaves the
        # PREVIOUS goal's final pose / error in these attributes, and the mission's
        # telemetry row logs stale values as if they belonged to this run.
        self.last_result = None
        self.last_duration_s = None
        self.last_steps = None
        self.last_final_x = None
        self.last_final_y = None
        self.last_position_error = None
        self.last_interrupt = None
        self.last_failure_reason = None
        start_time = time.time()
        steps = 0

        def spin():
            nonlocal steps
            rclpy.spin_once(self, timeout_sec=0.1)
            steps += 1

        if not self._action_client.wait_for_server(timeout_sec=15.0):
            self.get_logger().error('Nav2 action server unavailable')
            self.last_failure_reason = 'goal_rejected'
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
            # Timing instrumentation (S17 Piece 7, 2026-07-22): a mutable dict rather than
            # closure-captured locals because feedback_cb is registered before accept_time
            # is known — feedback only starts flowing once the goal is actually accepted
            # and executing, so accept_time is always set by the time feedback arrives.
            motion_state = {
                'accept_time': None, 'last_xy': None, 'last_time': None, 'logged': False,
            }

            def feedback_cb(feedback_msg):
                now = time.time()
                pos = feedback_msg.feedback.current_pose.pose.position
                xy = (pos.x, pos.y)
                prev_xy, prev_time = motion_state['last_xy'], motion_state['last_time']
                motion_state['last_xy'], motion_state['last_time'] = xy, now
                if prev_xy is None:
                    self.get_logger().info(
                        f'[timing] first feedback at {now:.3f} '
                        f'(+{now - motion_state["accept_time"]:.3f}s since accept), '
                        f'pose=({xy[0]:.3f}, {xy[1]:.3f})')
                    return
                if motion_state['logged']:
                    return
                dt = now - prev_time
                if dt <= 0:
                    return
                velocity = math.hypot(xy[0] - prev_xy[0], xy[1] - prev_xy[1]) / dt
                if velocity > MOTION_VELOCITY_THRESHOLD_MPS:
                    motion_state['logged'] = True
                    self.get_logger().info(
                        f'[timing] first real motion at {now:.3f} '
                        f'(+{now - motion_state["accept_time"]:.3f}s since accept), '
                        f'velocity={velocity:.3f} m/s')

            goal_handle = None
            for a in range(5):
                dispatch_time = time.time()
                self.get_logger().info(
                    f'[timing] goal dispatched at {dispatch_time:.3f} -> '
                    f'({x:.2f}, {y:.2f})')
                send_goal_future = self._action_client.send_goal_async(
                    goal, feedback_callback=feedback_cb)

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
            motion_state['accept_time'] = accept_time
            self.get_logger().info(
                f'[timing] goal accepted at {accept_time:.3f} '
                f'(+{accept_time - dispatch_time:.3f}s since dispatch)')
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

            succeeded = result_future.result().status == GoalStatus.STATUS_SUCCEEDED
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
            if kind == 'send_fail':
                self.last_failure_reason = 'goal_rejected'
                return self._finish(False, x, y, start_time, steps)
            if kind == 'interrupt':
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
            # verdict is 'failure' or an exhausted 'cold_abort' — both are the goal
            # accepting but not completing successfully within its attempt(s).
            self.last_failure_reason = 'nav_timeout'
            # Zombie guard (2026-07-18, Jetson nav2_hil.log): bt_navigator can abort our
            # handle while the controller still executes the delivered path — the robot
            # then drives with NO supervising mission. Cancel whatever is outstanding
            # before reporting failure; on the real robot this is a safety issue.
            if self._last_goal_handle is not None:
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
    # CLI for ad-hoc single goals (S17 review: was a hardcoded (1.0, 1.0) demo).
    import argparse
    parser = argparse.ArgumentParser(description='Send one NavigateToPose goal.')
    parser.add_argument('x', type=float)
    parser.add_argument('y', type=float)
    parser.add_argument('--yaw', type=float, default=None, help='final heading (rad)')
    args = parser.parse_args()
    rclpy.init()
    node = NavRunner()
    node.get_logger().info(build_env_manifest(git_sha=git_sha()))
    success = node.send_goal(args.x, args.y, yaw=args.yaw)
    print('Goal succeeded' if success else 'Goal failed')
    node.destroy_node()
    rclpy.shutdown()
    raise SystemExit(0 if success else 1)


if __name__ == '__main__':
    main()
