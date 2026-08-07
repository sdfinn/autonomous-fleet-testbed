# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""Bench smoke-test result logging: one row per tools/smoke_test.py run into FLEET_DB.

Isolated-table convention, same shape as coverage_log.py/diagnosis_log.py/
vlm_canary.py — smoke_test_runs is NEVER read by baseline_monitor.check_run() (drift
tracking only reads the runs/steps mission-telemetry tables); a bench smoke test is a
driver-layer sanity check, not a mission, and must never be able to move a drift
baseline.

Run standalone: python -m tools.smoke_test_log --runner-type local --overall-pass 1 \
  --checks-json '{"odom": {...}}' [--commit-sha SHA] [--ci-run-number N] [--db PATH]
"""
import argparse
import json
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
        CREATE TABLE IF NOT EXISTS smoke_test_runs (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp       TEXT,
            runner_type     TEXT,
            commit_sha      TEXT,
            ci_run_number   INTEGER,
            overall_pass    INTEGER,
            checks_json     TEXT
        )
    """)
    conn.commit()
    conn.close()


def log_smoke_test_run(runner_type=None, overall_pass=None, checks=None,
                       commit_sha=None, ci_run_number=None, db_path: str = DB_PATH) -> int:
    """Insert one row into `smoke_test_runs`. `checks` is a dict (per-check name ->
    {'pass': bool, ...measured values}), stored as a JSON string. Returns the new
    row's id."""
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO smoke_test_runs "
        "(timestamp, runner_type, commit_sha, ci_run_number, overall_pass, checks_json) "
        "VALUES (?,?,?,?,?,?)",
        (time.strftime("%Y-%m-%dT%H:%M:%S"), runner_type, commit_sha, ci_run_number,
         int(bool(overall_pass)) if overall_pass is not None else None,
         json.dumps(checks) if checks is not None else None),
    )
    row_id = cur.lastrowid
    conn.commit()
    conn.close()
    return row_id


def main():
    parser = argparse.ArgumentParser(
        description="Log one bench smoke-test run's result to FLEET_DB"
    )
    parser.add_argument("--runner-type", default=None)
    parser.add_argument("--overall-pass", type=int, choices=[0, 1], default=None)
    parser.add_argument("--checks-json", default=None,
                        help="JSON string, e.g. output of json.dumps(checks)")
    parser.add_argument("--commit-sha", default=None)
    parser.add_argument("--ci-run-number", type=int, default=None)
    parser.add_argument("--db", default=DB_PATH)
    args = parser.parse_args()

    checks = json.loads(args.checks_json) if args.checks_json else None
    log_smoke_test_run(
        runner_type=args.runner_type,
        overall_pass=bool(args.overall_pass) if args.overall_pass is not None else None,
        checks=checks, commit_sha=args.commit_sha, ci_run_number=args.ci_run_number,
        db_path=args.db,
    )


if __name__ == "__main__":
    main()
