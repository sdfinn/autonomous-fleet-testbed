# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""Fleet telemetry: one `runs` row per mission/test run into FLEET_DB (SQLite).

Schema authority (CR-15, Session 17 review): RUNS_COLUMNS below is THE registry of
optional telemetry columns. The logger's migration, log_run's accepted kwargs, and
tools/validate_telemetry's known-column set all derive from it — adding a column is one
edit here plus one pandera rule there (the model has a test-enforced coverage guard).
History justified this: power_mode, hil_jetson, and seed each broke or nearly broke CI
when one of the previously-four declaration sites lagged the others.
"""
import os
import sqlite3
import time

DB_PATH = os.environ.get("FLEET_DB", os.path.expanduser("~/fleet-ci-data/fleet_runs.db"))

# Required per-run fields, created with the table (order matches the INSERT below).
BASE_COLUMNS = ("id", "scenario", "timestamp", "steps", "final_x", "final_y", "result")

# Optional telemetry columns: name -> sqlite type. THE single registry (see module doc).
RUNS_COLUMNS = {
    "runner_type": "TEXT",           # local | hil_jetson | jetson | qemu (legacy)
    "robot_type": "TEXT",
    "robot_id": "TEXT",
    "sim_engine": "TEXT",            # gazebo | isaac | real
    "nav_success_rate": "REAL",
    "mean_position_error": "REAL",
    "mean_time_to_goal": "REAL",
    "collision_rate": "REAL",
    "odom_hz_mean": "REAL",
    "lidar_hz_mean": "REAL",
    "camera_hz_mean": "REAL",
    "firmware_test_pass_rate": "REAL",   # reserved: no firmware tests exist yet (R3+)
    "stage_timings_sec": "TEXT",
    "lidar_min_range": "REAL",
    "lidar_max_range": "REAL",
    "num_obstacles_detected": "INTEGER",
    "power_mode": "TEXT",            # Jetson nvpmodel label the run executed at (15W/25W)
    "seed": "INTEGER",               # Mission 2 placement seed (nullable)
    # Mission 2 return-fidelity (Task 13 §3): mean-abs grayscale diff of the home
    # reference vs home arrival photo [0..1]; NULL on non-mission2 rows and on red.
    "home_photo_similarity": "REAL",
    # Failure taxonomy (S17 Piece 3): why a FAIL row failed, not just that it did.
    # NULL on PASS rows and on rows logged before this column existed.
    "failure_reason": "TEXT",
}


def init_db(db_path: str = DB_PATH):
    parent = os.path.dirname(db_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(db_path)
    # Whole-branch review (Finding 1): WAL mode is stored in the file's own header and
    # persists once set, but a brand-new file (fresh clone, or recreated after
    # deletion) otherwise starts in SQLite's default rollback-journal mode with no
    # code path that ever sets it — bake it in here so every DB this code creates or
    # opens ends up WAL, not just the one production file fixed by hand. Idempotent:
    # a no-op on a DB already in WAL mode.
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS runs (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            scenario                TEXT,
            timestamp               TEXT,
            steps                   INTEGER,
            final_x                 REAL,
            final_y                 REAL,
            result                  TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS steps (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id      INTEGER,
            step        INTEGER,
            pos_x       REAL,
            pos_y       REAL,
            FOREIGN KEY (run_id) REFERENCES runs(id)
        )
    """)
    _ensure_run_columns(conn)
    conn.commit()
    conn.close()


def _ensure_run_columns(conn):
    """Migrate an existing DB to the current registry (additive only)."""
    existing = {row[1] for row in conn.execute("PRAGMA table_info(runs)").fetchall()}
    for name, col_type in RUNS_COLUMNS.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE runs ADD COLUMN {name} {col_type}")


def log_run(scenario: str, steps: int, final_x: float, final_y: float,
            result: str, step_log: list, db_path: str = DB_PATH, **metrics):
    """Insert one row into `runs`.

    `scenario`/`steps`/`final_x`/`final_y`/`result` are required; every other field is
    an optional telemetry column passed by name (must exist in RUNS_COLUMNS — a typo'd
    name raises instead of silently vanishing). None values are left NULL.

    Returns the new row's id, or None if FLEET_TELEMETRY=off skipped the write
    entirely (for ad hoc/experimental runs that shouldn't join the drift-tracked
    record — no scratch DB, no partial write, a true no-op).
    """
    if os.environ.get("FLEET_TELEMETRY", "on") == "off":
        return None

    unknown = set(metrics) - set(RUNS_COLUMNS)
    if unknown:
        raise TypeError(f"unknown telemetry column(s): {sorted(unknown)} — "
                        "add to RUNS_COLUMNS (tools/telemetry_logger.py) first")
    optional_fields = {k: v for k, v in metrics.items() if v is not None}

    init_db(db_path)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    columns = ["scenario", "timestamp", "steps", "final_x", "final_y", "result"]
    values = [scenario, time.strftime("%Y-%m-%dT%H:%M:%S"), steps, final_x, final_y, result]
    columns.extend(optional_fields.keys())
    values.extend(optional_fields.values())
    placeholders = ",".join("?" * len(columns))
    cur.execute(
        f"INSERT INTO runs ({','.join(columns)}) VALUES ({placeholders})",
        values,
    )
    run_id = cur.lastrowid
    cur.executemany(
        "INSERT INTO steps (run_id, step, pos_x, pos_y) VALUES (?,?,?,?)",
        [(run_id, s["step"], s["x"], s["y"]) for s in step_log]
    )
    conn.commit()
    conn.close()
    return run_id


# The old TelemetryLogger class was removed in the Session 17 code review fix wave
# (CR-05/CR-14, 2026-07-19): `mark_scenario_complete` belonged to the deleted
# ai_scenarios subsystem and `log_sensor_summary` had no callers anywhere. Telemetry
# is a functions-only module — one write path (log_run), one schema authority above.
