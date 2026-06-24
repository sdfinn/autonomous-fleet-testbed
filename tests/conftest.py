"""Pytest fixtures for fleet testbed tests."""
import pytest


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
