# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
import pathlib
import sqlite3
import subprocess
import sys

from tools import smoke_test_log


def test_init_db_creates_smoke_test_runs_table(tmp_path):
    db_path = str(tmp_path / "test.db")
    smoke_test_log.init_db(db_path)

    conn = sqlite3.connect(db_path)
    tables = {row[0] for row in
              conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert "smoke_test_runs" in tables


def test_log_smoke_test_run_inserts_row_and_returns_id(tmp_path):
    db_path = str(tmp_path / "test.db")
    checks = {"odom": {"pass": True, "measured_hz": 52.0}}

    row_id = smoke_test_log.log_smoke_test_run(
        runner_type="local", overall_pass=True, checks=checks,
        commit_sha="abc123", ci_run_number=42, db_path=db_path,
    )

    assert row_id is not None
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM smoke_test_runs WHERE id = ?", (row_id,)).fetchone()
    conn.close()
    assert row["runner_type"] == "local"
    assert row["overall_pass"] == 1
    assert row["commit_sha"] == "abc123"
    assert row["ci_run_number"] == 42
    assert '"odom"' in row["checks_json"]
    assert row["timestamp"] is not None


def test_log_smoke_test_run_omitted_fields_stay_null(tmp_path):
    db_path = str(tmp_path / "test.db")

    row_id = smoke_test_log.log_smoke_test_run(overall_pass=False, db_path=db_path)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM smoke_test_runs WHERE id = ?", (row_id,)).fetchone()
    conn.close()
    assert row["runner_type"] is None
    assert row["commit_sha"] is None
    assert row["checks_json"] is None


def test_cli_logs_a_row_via_db_flag(tmp_path):
    db_path = str(tmp_path / "test.db")

    result = subprocess.run(
        [sys.executable, "-m", "tools.smoke_test_log",
         "--runner-type", "local", "--overall-pass", "1",
         "--checks-json", '{"odom": {"pass": true}}',
         "--commit-sha", "deadbeef", "--ci-run-number", "7", "--db", db_path],
        capture_output=True, text=True,
    )

    assert result.returncode == 0, result.stderr
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM smoke_test_runs").fetchone()
    conn.close()
    assert row["overall_pass"] == 1
    assert row["commit_sha"] == "deadbeef"


def test_smoke_test_runs_never_referenced_by_baseline_monitor():
    """Isolated-table guarantee (design spec) — smoke_test_runs must never feed drift
    tracking, same as coverage_runs/vlm_canary_log."""
    baseline_src = (pathlib.Path(__file__).resolve().parent.parent
                    / 'tools' / 'baseline_monitor.py')
    assert 'smoke_test_runs' not in baseline_src.read_text()
