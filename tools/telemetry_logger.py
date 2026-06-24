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
    }
    existing = {row[1] for row in conn.execute("PRAGMA table_info(runs)").fetchall()}
    for name, col_type in expected_columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE runs ADD COLUMN {name} {col_type}")


def log_run(scenario: str, steps: int, final_x: float, final_y: float,
            result: str, step_log: list, db_path: str = DB_PATH):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO runs (scenario, timestamp, steps, final_x, final_y, result)"
        " VALUES (?,?,?,?,?,?)",
        (scenario, time.strftime("%Y-%m-%dT%H:%M:%S"), steps, final_x, final_y, result)
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
