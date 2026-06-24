import os
import sqlite3
import pandas as pd
import pandera as pa
from pandera import Check, DataFrameModel
from pandera.typing import Series

# Resolves to project root on any OS; overridable via env var for CI ephemeral DBs
DB_PATH = os.getenv(
    "ROBOT_DB_PATH",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "robot_test_results.db")
)

class RunsModel(DataFrameModel):
    id: Series[int]
    scenario: Series[str]
    timestamp: Series[str]
    steps: Series[int] = pa.Field(gt=0)
    final_x: Series[float] = pa.Field(in_range=(-150.0, 150.0))
    final_y: Series[float] = pa.Field(in_range=(-150.0, 150.0))
    result: Series[str] = pa.Field(isin=["PASS", "FAIL", "STOPPED", "TIMEOUT"])
    runner_type: Series[str] = pa.Field(isin=["qemu", "jetson", "local"], nullable=True)
    robot_type: Series[str] = pa.Field(nullable=True)
    camera_hz_mean: Series[float] = pa.Field(ge=0, nullable=True)
    firmware_test_pass_rate: Series[float] = pa.Field(ge=0, le=1, nullable=True)
    stage_timings_sec: Series[str] = pa.Field(nullable=True)
    battery_percent_start: Series[float] = pa.Field(in_range=(0, 100), nullable=True)
    battery_percent_end: Series[float] = pa.Field(in_range=(0, 100), nullable=True)
    # float not int: pandas stores nullable integer columns as float64 (NaN can't live in int64)
    obstacle_count: Series[float] = pa.Field(in_range=(0, 10), nullable=True)

RUNS_SCHEMA = RunsModel.to_schema(coerce=True)

STEPS_SCHEMA = DataFrameSchema({
    "id":     Column(int,   nullable=False),
    "run_id": Column(int,   nullable=False),
    "step":   Column(int,   Check.greater_than_or_equal_to(0)),
    "pos_x":  Column(float, Check.in_range(-150.0, 150.0)),
    "pos_y":  Column(float, Check.in_range(-150.0, 150.0)),
}, coerce=True)

KNOWN_RUNS_COLS = {
    "id", "scenario", "timestamp", "steps", "final_x", "final_y", "result",
    "runner_type", "robot_type", "camera_hz_mean", "firmware_test_pass_rate",
    "stage_timings_sec",
    "speed_avg", "battery_percent_start", "battery_percent_end", "obstacle_count",
    "lidar_min_range", "lidar_max_range", "num_obstacles_detected",
    "num_frames", "detections_per_frame_avg", "class_distribution",
}


def validate_runs(db_path=DB_PATH) -> bool:
    conn = sqlite3.connect(db_path)
    df = pd.read_sql("SELECT * FROM runs", conn)
    conn.close()
    try:
        RUNS_SCHEMA.validate(df, lazy=True)
        print(f"✅ runs: {len(df)} rows valid")
        return True
    except pa.errors.SchemaErrors as e:
        print(f"❌ runs validation failed:\n{e.failure_cases}")
        return False


def validate_steps(db_path=DB_PATH) -> bool:
    conn = sqlite3.connect(db_path)
    df = pd.read_sql("SELECT * FROM steps", conn)
    conn.close()
    try:
        STEPS_SCHEMA.validate(df, lazy=True)
        print(f"✅ steps: {len(df)} rows valid")
        return True
    except pa.errors.SchemaErrors as e:
        print(f"❌ steps validation failed:\n{e.failure_cases}")
        return False


def detect_schema_drift(db_path=DB_PATH) -> bool:
    conn = sqlite3.connect(db_path)
    actual = {row[1] for row in conn.execute("PRAGMA table_info(runs)").fetchall()}
    conn.close()
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