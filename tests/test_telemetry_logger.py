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
