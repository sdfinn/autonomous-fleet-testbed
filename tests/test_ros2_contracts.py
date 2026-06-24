"""
ROS2 Topic Contract Tests
Validates message schemas for each topic the system publishes/subscribes.
Isaac Sim must be running with Play pressed for /odom, /scan, /camera/image_raw tests.
"""
import pytest
import rclpy
from rclpy.node import Node


@pytest.fixture(scope="module")
def ros_node():
    rclpy.init()
    node = rclpy.create_node("contract_test_node")
    yield node
    node.destroy_node()
    rclpy.shutdown()


# --- /cmd_vel publisher contract ---

def test_cmd_vel_message_schema():
    """Verify geometry_msgs/Twist has valid linear/angular fields."""
    from geometry_msgs.msg import Twist
    msg = Twist()
    msg.linear.x = 0.3
    msg.angular.z = 0.0

    assert hasattr(msg, "linear"), "Twist must have linear field"
    assert hasattr(msg, "angular"), "Twist must have angular field"
    assert hasattr(msg.linear, "x"), "linear must have x"
    assert hasattr(msg.angular, "z"), "angular must have z"
    assert -1.0 <= msg.linear.x <= 1.0, "linear.x out of safe range"
    assert -2.0 <= msg.angular.z <= 2.0, "angular.z out of safe range"


# --- /odom subscriber contract ---

def test_odom_message_schema(ros_node):
    """Verify /odom publishes nav_msgs/Odometry with valid pose fields."""
    from nav_msgs.msg import Odometry
    received = []

    sub = ros_node.create_subscription(
        Odometry, "/robot_001/odom",
        lambda msg: received.append(msg), 10
    )

    import time
    deadline = time.time() + 5.0
    while time.time() < deadline:
        rclpy.spin_once(ros_node, timeout_sec=0.1)

    ros_node.destroy_subscription(sub)

    assert received, "/robot_001/odom produced no messages within 5 seconds"
    duration = max(time.time() - (deadline - 5.0), 1e-6)
    rate = len(received) / duration
    assert rate >= 50.0, f"odom rate {rate:.1f} Hz below required 50 Hz"
    msg = received[0]
    assert hasattr(msg.pose, "pose"), "Odometry must have pose.pose"
    assert hasattr(msg.pose.pose, "position"), "pose.pose must have position"
    assert hasattr(msg.twist, "twist"), "Odometry must have twist.twist"

    pos = msg.pose.pose.position
    assert -150.0 <= pos.x <= 150.0, f"odom x={pos.x} outside arena bounds"
    assert -150.0 <= pos.y <= 150.0, f"odom y={pos.y} outside arena bounds"


# --- /scan subscriber contract ---

def test_scan_message_schema(ros_node):
    """Verify /scan publishes sensor_msgs/PointCloud2.
    ROS2RtxLidarHelper (used in Isaac Sim) publishes PointCloud2, not LaserScan.
    """
    from sensor_msgs.msg import PointCloud2
    received = []

    sub = ros_node.create_subscription(
        PointCloud2, "/robot_001/scan",
        lambda msg: received.append(msg), 10
    )

    import time
    deadline = time.time() + 5.0
    while time.time() < deadline:
        rclpy.spin_once(ros_node, timeout_sec=0.1)

    ros_node.destroy_subscription(sub)

    assert received, "/robot_001/scan produced no messages"
    duration = max(time.time() - (deadline - 5.0), 1e-6)
    rate = len(received) / duration
    assert rate >= 10.0, f"scan rate {rate:.1f} Hz below required 10 Hz"
    msg = received[0]
    assert msg.point_step > 0, "PointCloud2 point_step must be non-zero"
    assert len(msg.data) > 0, "PointCloud2 data array is empty"
    assert msg.width > 0 or msg.height > 0, "PointCloud2 has no points"


# --- /camera/image_raw subscriber contract ---

def test_camera_image_schema(ros_node):
    """Verify /camera/image_raw publishes sensor_msgs/Image with expected encoding."""
    from sensor_msgs.msg import Image
    received = []

    sub = ros_node.create_subscription(
        Image, "/robot_001/camera/image_raw",
        lambda msg: received.append(msg), 10
    )

    import time
    deadline = time.time() + 5.0
    while time.time() < deadline:
        rclpy.spin_once(ros_node, timeout_sec=0.1)

    ros_node.destroy_subscription(sub)

    assert received, "/robot_001/camera/image_raw produced no messages"
    duration = max(time.time() - (deadline - 5.0), 1e-6)
    rate = len(received) / duration
    assert rate >= 10.0, f"camera rate {rate:.1f} Hz below required 10 Hz"
    msg = received[0]
    assert msg.encoding in ("rgb8", "bgr8", "rgba8"), \
        f"Unexpected image encoding: {msg.encoding}"
    assert msg.width > 0 and msg.height > 0, "Image dimensions must be non-zero"
    bytes_per_pixel = 4 if "a" in msg.encoding else 3
    assert len(msg.data) == msg.width * msg.height * bytes_per_pixel, \
        f"Image data size does not match width × height × {bytes_per_pixel} (encoding: {msg.encoding})"