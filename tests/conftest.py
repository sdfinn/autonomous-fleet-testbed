"""Pytest fixtures for fleet testbed tests."""
import pathlib
import sys

import pytest

# Make `nav_fleet` importable without a colcon build/overlay — stage-1-quality runs on a
# bare ubuntu-latest runner with no ROS2 workspace. Harmless when the overlay IS sourced:
# --symlink-install points the installed package at these same source files.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / 'src' / 'nav_fleet'))


@pytest.fixture(scope='session', autouse=False)
def ros_context():
    """Shared rclpy context for live-ROS2 test modules (test_navigation, test_mission_run).

    Guarded so the two modules can share one pytest session; autouse stays module-side
    so pure-Python test runs (stage-1, no rclpy installed) never touch this fixture.
    """
    import rclpy
    if not rclpy.ok():
        rclpy.init()
    yield
    rclpy.try_shutdown()


@pytest.fixture
def db_path(tmp_path):
    """In-memory SQLite DB for tests that need telemetry data."""
    db = tmp_path / "test_fleet.db"
    return str(db)


@pytest.fixture
def sample_run():
    """Minimal valid run dict matching the telemetry schema."""
    return {
        "run_id": "test-001",
        "robot_type": "jetson_ugv_pt",
        "runner_type": "local",
        "nav_success_rate": 1.0,
        "mean_position_error": 0.05,
        "mean_time_to_goal": 12.3,
        "collision_rate": 0.0,
        "odom_hz_mean": 52.1,
        "lidar_hz_mean": 10.2,
        "camera_hz_mean": 10.1,
        "firmware_test_pass_rate": 1.0,
        "stage_timings_sec": '{"stage_2": 45.2, "stage_3": 28.1}',
    }
