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

import time
import rclpy
from rclpy.node import Node
from rclpy.action import ActionClient
from rclpy.time import Time
from nav2_msgs.action import NavigateToPose
from geometry_msgs.msg import PoseStamped


class NavRunner(Node):

    def __init__(self):
        super().__init__('nav_runner')
        self._action_client = ActionClient(
            self, NavigateToPose, '/robot_001/navigate_to_pose'
        )

    def send_goal(self, x, y, timeout=90.0):
        if not self._action_client.wait_for_server(timeout_sec=15.0):
            self.get_logger().error('Nav2 action server unavailable')
            return False

        goal = NavigateToPose.Goal()
        goal.pose = PoseStamped()
        goal.pose.header.frame_id = 'map'
        goal.pose.header.stamp = Time().to_msg()  # zero = use latest TF, works with sim time
        goal.pose.pose.position.x = x
        goal.pose.pose.position.y = y
        goal.pose.pose.orientation.w = 1.0

        # wait_for_server() only confirms the action is discoverable on the ROS graph, which
        # happens as soon as bt_navigator's node exists — not that its lifecycle state is
        # ACTIVE. A goal sent in that gap is rejected ("Action server is inactive"), so retry
        # a few times with a short backoff rather than treating one rejection as final.
        goal_handle = None
        for attempt in range(5):
            send_goal_future = self._action_client.send_goal_async(goal)

            deadline = time.time() + 10.0
            while time.time() < deadline:
                if send_goal_future.done():
                    break
                rclpy.spin_once(self, timeout_sec=0.1)

            if not send_goal_future.done():
                self.get_logger().warning('Goal send timed out')
                return False

            goal_handle = send_goal_future.result()
            if goal_handle.accepted:
                break

            self.get_logger().warning(
                f'Goal rejected (attempt {attempt + 1}/5) — bt_navigator likely not '
                'active yet, retrying')
            time.sleep(1.0)
        else:
            self.get_logger().error('Goal rejected after all retries')
            return False

        result_future = goal_handle.get_result_async()

        deadline = time.time() + timeout
        while time.time() < deadline:
            if result_future.done():
                break
            rclpy.spin_once(self, timeout_sec=0.1)

        if not result_future.done():
            self.get_logger().warning('Goal wait timed out')
            return False

        return result_future.result().status == 4


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
