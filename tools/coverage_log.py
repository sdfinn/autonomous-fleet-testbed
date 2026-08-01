# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""Code coverage trend logging: one row per CI run into FLEET_DB (SQLite).

Same DB, same isolated-table shape convention as diagnosis_log.py/vlm_canary.py — no
relation to the runs/steps mission-telemetry schema (RUNS_COLUMNS' migration registry
exists for that table's many optional per-scenario columns; coverage is a handful of
fixed numeric fields logged together every time, so it doesn't need that machinery).

Pure-local replacement for the Codecov-hosted merge (2026-08-01 decision): CI computes
stage-1/stage-2 percentages and the real `coverage combine`-merged total itself, then
logs all three here so dashboard/app.py can chart the trend — no third-party service.

Run standalone: python -m tools.coverage_log --stage1-pct N --stage2-pct N \
  --combined-pct N [--commit-sha SHA] [--ci-run-number N] [--db PATH]
"""
import argparse
import os
import sqlite3
import sys
import time

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)

from tools.telemetry_logger import DB_PATH  # noqa: E402


def init_db(db_path: str = DB_PATH):
    parent = os.path.dirname(db_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS coverage_runs (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp       TEXT,
            commit_sha      TEXT,
            ci_run_number   INTEGER,
            stage1_pct      REAL,
            stage2_pct      REAL,
            combined_pct    REAL
        )
    """)
    conn.commit()
    conn.close()


def log_coverage_run(stage1_pct=None, stage2_pct=None, combined_pct=None,
                     commit_sha=None, ci_run_number=None, db_path: str = DB_PATH) -> int:
    """Insert one row into `coverage_runs`. Any field left as None (e.g. a stage that
    didn't run) is stored NULL. Returns the new row's id."""
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO coverage_runs "
        "(timestamp, commit_sha, ci_run_number, stage1_pct, stage2_pct, combined_pct) "
        "VALUES (?,?,?,?,?,?)",
        (time.strftime("%Y-%m-%dT%H:%M:%S"), commit_sha, ci_run_number,
         stage1_pct, stage2_pct, combined_pct),
    )
    row_id = cur.lastrowid
    conn.commit()
    conn.close()
    return row_id


def _pct_or_none(value):
    """CI passes a literal 'n/a' string when a stage's coverage data is
    unexpectedly missing — treat that (or any other non-numeric value) as no
    data rather than crashing the whole job at its last step."""
    try:
        return float(value)
    except ValueError:
        return None


def main():
    parser = argparse.ArgumentParser(
        description="Log one CI run's code coverage percentages to FLEET_DB"
    )
    parser.add_argument("--stage1-pct", type=_pct_or_none, default=None)
    parser.add_argument("--stage2-pct", type=_pct_or_none, default=None)
    parser.add_argument("--combined-pct", type=_pct_or_none, default=None)
    parser.add_argument("--commit-sha", default=None)
    parser.add_argument("--ci-run-number", type=int, default=None)
    # Explicit default=DB_PATH here (not read fresh inside main()) is fine — unlike
    # vlm_canary.py's caution, this CLI always takes --db explicitly in CI, and tests
    # pass --db directly too, so there's no monkeypatch-after-import path relying on a
    # fresh module-global read.
    parser.add_argument("--db", default=DB_PATH)
    args = parser.parse_args()

    log_coverage_run(
        stage1_pct=args.stage1_pct, stage2_pct=args.stage2_pct,
        combined_pct=args.combined_pct, commit_sha=args.commit_sha,
        ci_run_number=args.ci_run_number, db_path=args.db,
    )


if __name__ == "__main__":
    main()
