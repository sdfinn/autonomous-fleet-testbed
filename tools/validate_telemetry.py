# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""Pandera schema validation for fleet telemetry database.

Column EXISTENCE comes from tools/telemetry_logger's registry (CR-15 — single source);
value RULES live here in RunsModel. test_registry_is_single_source enforces that the
model covers every registry column, so a column added to the registry without a rule
here fails CI instead of sliding through unvalidated.
"""
import os
import sqlite3
import sys

import pandas as pd
import pandera as pa
from pandera import Check, Column, DataFrameModel, DataFrameSchema
from pandera.typing import Series

# Plain-script safety (the documented `python tools/x.py` trap — it broke stage-5 the
# moment this module first imported a sibling): running as a script puts tools/ (not the
# repo root) on sys.path, so `tools.*` doesn't resolve. `python -m tools.x` is the
# canonical form (ci.yml uses it); this bootstrap keeps the script form working too.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.telemetry_logger import BASE_COLUMNS, RUNS_COLUMNS  # noqa: E402

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
    # home_photo_similarity: Mission 2 return-fidelity score [0..1] (Task 13 §3) — nullable,
    # NULL on non-mission2 rows and on red. Schema + logger column land in the SAME commit
    # (seed-column precedent above): a follow-up column breaks CI the moment the first real
    # row arrives before the schema knows about it.
    home_photo_similarity: Series[float] = pa.Field(ge=0, le=1, nullable=True)
    # power_mode: the Jetson nvpmodel label the run executed at (CR-13 — previously in
    # the known-column set but value-unvalidated).
    power_mode: Series[str] = pa.Field(isin=["15W", "25W", "MAXN_SUPER"], nullable=True)
    # failure_reason: why a FAIL row failed (S17 Piece 3) — nullable, NULL on PASS rows.
    # Fixed enum, same value-validation policy as power_mode (CR-13): garbage must fail
    # schema validation, not pass through unexamined.
    # startup_crash (added 2026-07-21): the process died before it ever reached
    # _log_mission — mission2_day.py's orchestrator synthesizes this row itself,
    # since mission_runner.py never got far enough to log anything.
    failure_reason: Series[str] = pa.Field(
        isin=["goal_rejected", "nav_timeout", "no_camera_frame", "crash", "startup_crash"],
        nullable=True)


RUNS_SCHEMA = RunsModel.to_schema()

STEPS_SCHEMA = DataFrameSchema({
    "id":     Column(int,   nullable=False),
    "run_id": Column(int,   nullable=False),
    "step":   Column(int,   Check.greater_than_or_equal_to(0)),
    "pos_x":  Column(float, Check.in_range(-150.0, 150.0)),
    "pos_y":  Column(float, Check.in_range(-150.0, 150.0)),
}, coerce=True)

# Derived from the logger's registry (CR-15) — no second hand-maintained list.
KNOWN_RUNS_COLS = set(BASE_COLUMNS) | set(RUNS_COLUMNS)


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
