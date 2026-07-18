import os
import sqlite3
import time

DB_PATH = os.environ.get("FLEET_DB", "reports/fleet_runs.db")


def init_db(db_path: str = DB_PATH):
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS runs (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            scenario                TEXT,
            timestamp               TEXT,
            steps                   INTEGER,
            final_x                 REAL,
            final_y                 REAL,
            result                  TEXT,
            runner_type             TEXT,
            robot_type              TEXT,
            nav_success_rate        REAL,
            mean_position_error     REAL,
            mean_time_to_goal       REAL,
            collision_rate          REAL,
            odom_hz_mean            REAL,
            lidar_hz_mean           REAL,
            camera_hz_mean          REAL,
            firmware_test_pass_rate REAL,
            stage_timings_sec       TEXT,
            lidar_min_range         REAL,
            lidar_max_range         REAL,
            num_obstacles_detected  INTEGER
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
    expected_columns = {
        "runner_type": "TEXT",
        "robot_type": "TEXT",
        "robot_id": "TEXT",
        "sim_engine": "TEXT",
        "nav_success_rate": "REAL",
        "mean_position_error": "REAL",
        "mean_time_to_goal": "REAL",
        "collision_rate": "REAL",
        "odom_hz_mean": "REAL",
        "lidar_hz_mean": "REAL",
        "camera_hz_mean": "REAL",
        "firmware_test_pass_rate": "REAL",
        "stage_timings_sec": "TEXT",
        "lidar_min_range": "REAL",
        "lidar_max_range": "REAL",
        "num_obstacles_detected": "INTEGER",
        "power_mode": "TEXT",
        "seed": "INTEGER",
        "home_photo_similarity": "REAL",
    }
    existing = {row[1] for row in conn.execute("PRAGMA table_info(runs)").fetchall()}
    for name, col_type in expected_columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE runs ADD COLUMN {name} {col_type}")


def log_run(scenario: str, steps: int, final_x: float, final_y: float,
            result: str, step_log: list, db_path: str = DB_PATH,
            robot_id: str = None, robot_type: str = None, runner_type: str = None,
            sim_engine: str = None, nav_success_rate: float = None,
            mean_position_error: float = None, mean_time_to_goal: float = None,
            collision_rate: float = None, odom_hz_mean: float = None,
            lidar_hz_mean: float = None, camera_hz_mean: float = None,
            power_mode: str = None, seed: int = None,
            home_photo_similarity: float = None):
    """Insert one row into `runs`. Only `scenario`/`steps`/`final_x`/`final_y`/`result`
    are required — every other field is optional telemetry attached to the same run,
    left NULL when not supplied by the caller.
    """
    optional_fields = {
        "robot_id": robot_id,
        "robot_type": robot_type,
        "runner_type": runner_type,
        "sim_engine": sim_engine,
        "nav_success_rate": nav_success_rate,
        "mean_position_error": mean_position_error,
        "mean_time_to_goal": mean_time_to_goal,
        "collision_rate": collision_rate,
        "odom_hz_mean": odom_hz_mean,
        "lidar_hz_mean": lidar_hz_mean,
        "camera_hz_mean": camera_hz_mean,
        "power_mode": power_mode,
        "seed": seed,
        # Mission 2 return-fidelity (Task 13 §3): mean-abs grayscale diff of the home
        # reference vs home arrival photo [0..1], nullable — NULL on every non-mission2 row
        # and on red (which stops mid-room and takes no arrival photo). Trended by
        # baseline_monitor as drift-detection material.
        "home_photo_similarity": home_photo_similarity,
    }
    optional_fields = {k: v for k, v in optional_fields.items() if v is not None}

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


class TelemetryLogger:
    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path

    def log_sensor_summary(self, run_id: int, lidar_min: float, lidar_max: float,
                           obstacles_detected: int):
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            UPDATE runs SET
                lidar_min_range = ?,
                lidar_max_range = ?,
                num_obstacles_detected = ?
            WHERE id = ?
        """, (lidar_min, lidar_max, obstacles_detected, run_id))
        conn.commit()
        conn.close()

    def mark_scenario_complete(self, ai_scenario_id, status):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE ai_scenarios SET test_status = ? WHERE id = ?",
            (status, ai_scenario_id)
        )
        conn.commit()
        conn.close()
