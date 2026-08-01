# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
import sqlite3
import subprocess
import sys

from tools import coverage_log


def test_init_db_creates_coverage_runs_table(tmp_path):
    db_path = str(tmp_path / "test.db")
    coverage_log.init_db(db_path)

    conn = sqlite3.connect(db_path)
    tables = {row[0] for row in
              conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert "coverage_runs" in tables


def test_log_coverage_run_inserts_row_and_returns_id(tmp_path):
    db_path = str(tmp_path / "test.db")

    row_id = coverage_log.log_coverage_run(
        stage1_pct=66.0, stage2_pct=70.0, combined_pct=74.0,
        commit_sha="abc123", ci_run_number=42, db_path=db_path,
    )

    assert row_id is not None
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM coverage_runs WHERE id = ?", (row_id,)).fetchone()
    conn.close()
    assert row["stage1_pct"] == 66.0
    assert row["stage2_pct"] == 70.0
    assert row["combined_pct"] == 74.0
    assert row["commit_sha"] == "abc123"
    assert row["ci_run_number"] == 42
    assert row["timestamp"] is not None


def test_log_coverage_run_omitted_fields_stay_null(tmp_path):
    db_path = str(tmp_path / "test.db")

    row_id = coverage_log.log_coverage_run(combined_pct=74.0, db_path=db_path)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM coverage_runs WHERE id = ?", (row_id,)).fetchone()
    conn.close()
    assert row["stage1_pct"] is None
    assert row["stage2_pct"] is None
    assert row["commit_sha"] is None
    assert row["ci_run_number"] is None


def test_log_coverage_run_multiple_rows_are_independent(tmp_path):
    db_path = str(tmp_path / "test.db")

    id1 = coverage_log.log_coverage_run(combined_pct=60.0, db_path=db_path)
    id2 = coverage_log.log_coverage_run(combined_pct=65.0, db_path=db_path)

    assert id1 != id2
    conn = sqlite3.connect(db_path)
    count = conn.execute("SELECT COUNT(*) FROM coverage_runs").fetchone()[0]
    conn.close()
    assert count == 2


def test_cli_logs_a_row_via_db_flag(tmp_path):
    db_path = str(tmp_path / "test.db")

    result = subprocess.run(
        [sys.executable, "-m", "tools.coverage_log",
         "--stage1-pct", "66.0", "--stage2-pct", "70.0", "--combined-pct", "74.0",
         "--commit-sha", "deadbeef", "--ci-run-number", "7",
         "--db", db_path],
        capture_output=True, text=True,
    )

    assert result.returncode == 0, result.stderr
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM coverage_runs").fetchone()
    conn.close()
    assert row["stage1_pct"] == 66.0
    assert row["combined_pct"] == 74.0
    assert row["commit_sha"] == "deadbeef"
    assert row["ci_run_number"] == 7


def test_cli_treats_non_numeric_pct_as_null_instead_of_crashing(tmp_path):
    # CI's fallback ("n/a") when a stage's coverage data is unexpectedly missing —
    # must not crash the whole job at its last step.
    db_path = str(tmp_path / "test.db")

    result = subprocess.run(
        [sys.executable, "-m", "tools.coverage_log",
         "--stage1-pct", "n/a", "--stage2-pct", "70.0", "--combined-pct", "70.0",
         "--db", db_path],
        capture_output=True, text=True,
    )

    assert result.returncode == 0, result.stderr
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM coverage_runs").fetchone()
    conn.close()
    assert row["stage1_pct"] is None
    assert row["stage2_pct"] == 70.0
