# Copyright 2026 Mike. Licensed under MIT.
"""Pandera schema validation for fleet telemetry database."""
import os
import sqlite3
import pandas as pd
import pandera as pa
from pandera import Check, Column, DataFrameModel, DataFrameSchema
from pandera.typing import Series

DB_PATH = os.environ.get("FLEET_DB", "reports/fleet_runs.db")


class RunsModel(DataFrameModel):
    class Config:
        coerce = True

    id: Series[int]
    scenario: Series[str]
    timestamp: Series[str]
    steps: Series[int] = pa.Field(gt=0)
    final_x: Series[float] = pa.Field(in_range=(-150.0, 150.0))
    final_y: Series[float] = pa.Field(in_range=(-150.0, 150.0))
    result: Series[str] = pa.Field(isin=["PASS", "FAIL", "STOPPED", "TIMEOUT"])
    # hil_jetson: Session 16 Task 13 ships the Jetson's HIL row into this DB — the
    # workstation schema first met that runner_type on the first shipped row (CI red).
    runner_type: Series[str] = pa.Field(
        isin=["qemu", "jetson", "local", "hil_jetson"], nullable=True)
    robot_type: Series[str] = pa.Field(nullable=True)
    robot_id: Series[str] = pa.Field(nullable=True)
    sim_engine: Series[str] = pa.Field(isin=["gazebo", "isaac", "real"], nullable=True)
    nav_success_rate: Series[float] = pa.Field(ge=0, le=1, nullable=True)
    mean_position_error: Series[float] = pa.Field(ge=0, nullable=True)
    mean_time_to_goal: Series[float] = pa.Field(ge=0, nullable=True)
    collision_rate: Series[float] = pa.Field(ge=0, le=1, nullable=True)
    odom_hz_mean: Series[float] = pa.Field(ge=0, nullable=True)
    lidar_hz_mean: Series[float] = pa.Field(ge=0, nullable=True)
    camera_hz_mean: Series[float] = pa.Field(ge=0, nullable=True)
    firmware_test_pass_rate: Series[float] = pa.Field(ge=0, le=1, nullable=True)
    stage_timings_sec: Series[str] = pa.Field(nullable=True)
    lidar_min_range: Series[float] = pa.Field(ge=0, nullable=True)
    lidar_max_range: Series[float] = pa.Field(ge=0, nullable=True)
    num_obstacles_detected: Series[float] = pa.Field(ge=0, nullable=True)
    # seed: Mission 2 harness placement seed (spec §7) — nullable, NULL on all Mission 1
    # rows. Added IN THE SAME COMMIT as the logger column: power_mode and hil_jetson each
    # broke CI when the schema met its first real row as a follow-up.
    seed: Series[float] = pa.Field(nullable=True)


RUNS_SCHEMA = RunsModel.to_schema()

STEPS_SCHEMA = DataFrameSchema({
    "id":     Column(int,   nullable=False),
    "run_id": Column(int,   nullable=False),
    "step":   Column(int,   Check.greater_than_or_equal_to(0)),
    "pos_x":  Column(float, Check.in_range(-150.0, 150.0)),
    "pos_y":  Column(float, Check.in_range(-150.0, 150.0)),
}, coerce=True)

KNOWN_RUNS_COLS = {
    "id", "scenario", "timestamp", "steps", "final_x", "final_y", "result",
    "runner_type", "robot_type", "robot_id", "sim_engine",
    "nav_success_rate", "mean_position_error", "mean_time_to_goal", "collision_rate",
    "odom_hz_mean", "lidar_hz_mean", "camera_hz_mean", "firmware_test_pass_rate",
    "stage_timings_sec",
    "lidar_min_range", "lidar_max_range", "num_obstacles_detected",
    "power_mode",  # Session 16 Task 1 — Jetson nvpmodel mode the mission ran at (HIL)
    "seed",  # Mission 2 placement seed (Session 16 Plan B)
}


def validate_runs(db_path=DB_PATH) -> bool:
    with sqlite3.connect(db_path) as conn:
        df = pd.read_sql("SELECT * FROM runs", conn)
    try:
        RUNS_SCHEMA.validate(df, lazy=True)
        print(f"✅ runs: {len(df)} rows valid")
        return True
    except pa.errors.SchemaErrors as e:
        print(f"❌ runs validation failed:\n{e.failure_cases}")
        return False


def validate_steps(db_path=DB_PATH) -> bool:
    with sqlite3.connect(db_path) as conn:
        df = pd.read_sql("SELECT * FROM steps", conn)
    try:
        STEPS_SCHEMA.validate(df, lazy=True)
        print(f"✅ steps: {len(df)} rows valid")
        return True
    except pa.errors.SchemaErrors as e:
        print(f"❌ steps validation failed:\n{e.failure_cases}")
        return False


def detect_schema_drift(db_path=DB_PATH) -> bool:
    with sqlite3.connect(db_path) as conn:
        actual = {row[1] for row in conn.execute("PRAGMA table_info(runs)").fetchall()}
    unexpected = actual - KNOWN_RUNS_COLS
    if unexpected:
        print(f"⚠️  Schema drift — unexpected columns: {unexpected}")
        return False
    print("✅ No schema drift")
    return True


if __name__ == "__main__":
    r1 = validate_runs()
    r2 = validate_steps()
    r3 = detect_schema_drift()
    exit(0 if all([r1, r2, r3]) else 1)
