"""Unit tests for tools/telemetry_logger.py schema + log_run fields."""
import sqlite3

from tools.telemetry_logger import init_db, log_run


def test_power_mode_column_exists(tmp_path):
    db = str(tmp_path / "t.db")
    init_db(db)
    cols = {r[1] for r in sqlite3.connect(db).execute("PRAGMA table_info(runs)")}
    assert "power_mode" in cols


def test_log_run_records_power_mode(tmp_path):
    db = str(tmp_path / "t.db")
    log_run(scenario="s", steps=1, final_x=0.0, final_y=0.0, result="PASS",
            step_log=[], db_path=db, power_mode="25W")
    row = sqlite3.connect(db).execute(
        "SELECT power_mode FROM runs ORDER BY id DESC LIMIT 1").fetchone()
    assert row[0] == "25W"


def test_log_run_power_mode_defaults_null(tmp_path):
    db = str(tmp_path / "t.db")
    log_run(scenario="s", steps=1, final_x=0.0, final_y=0.0, result="PASS",
            step_log=[], db_path=db)
    row = sqlite3.connect(db).execute(
        "SELECT power_mode FROM runs ORDER BY id DESC LIMIT 1").fetchone()
    assert row[0] is None


def test_log_run_stores_seed(db_path):
    """Seed column stores integer placement seed for Mission 2 harness."""
    from tools.telemetry_logger import log_run
    run_id = log_run(scenario="mission2_red", steps=1, final_x=0.0, final_y=3.0,
                     result="PASS", step_log=[], db_path=db_path, seed=123456789)
    with sqlite3.connect(db_path) as conn:
        row = conn.execute("SELECT seed FROM runs WHERE id = ?", (run_id,)).fetchone()
    assert row == (123456789,)


def test_log_run_seed_defaults_null(db_path):
    """Seed column defaults to NULL when not supplied."""
    from tools.telemetry_logger import log_run
    run_id = log_run(scenario="mission1", steps=3, final_x=0.0, final_y=0.0,
                     result="PASS", step_log=[], db_path=db_path)
    with sqlite3.connect(db_path) as conn:
        row = conn.execute("SELECT seed FROM runs WHERE id = ?", (run_id,)).fetchone()
    assert row == (None,)


def test_schema_accepts_seed_column(db_path):
    """Pandera schema validates runs with seed column."""
    from tools.telemetry_logger import log_run
    from tools.validate_telemetry import validate_runs, detect_schema_drift
    log_run(scenario="mission2_ignore", steps=1, final_x=0.0, final_y=3.3,
            result="PASS", step_log=[], db_path=db_path, seed=42)
    assert validate_runs(db_path) is True
    assert detect_schema_drift(db_path) is True
