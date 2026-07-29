# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""Tests for tools/fleet_status.py's plain-text status summary."""
import sqlite3
import sys
from datetime import datetime, timedelta

import pytest

from tools.fleet_status import build_status_summary, main
from tools.telemetry_logger import init_db, log_run

_BASELINE = [0.94, 0.95, 0.96, 0.95, 0.96, 0.94, 0.95, 0.96, 0.95, 0.94]


@pytest.fixture()
def db(tmp_path):
    path = str(tmp_path / "status.db")
    init_db(path)
    return path


def _seed_baseline(db_path, scenario="mission1", runner_type="local"):
    for rate in _BASELINE:
        log_run(scenario=scenario, steps=100, final_x=1.0, final_y=1.0, result="PASS",
                step_log=[], db_path=db_path, runner_type=runner_type,
                nav_success_rate=rate)


def test_reports_ok_when_nothing_flagged(db):
    _seed_baseline(db)
    log_run(scenario="mission1", steps=100, final_x=1.0, final_y=1.0, result="PASS",
            step_log=[], db_path=db, runner_type="local", nav_success_rate=0.95)

    summary = build_status_summary("local", ["mission1"], db_path=db)

    assert "mission1: PASS — ok" in summary
    assert "DRIFT" not in summary


def test_reports_drift_when_flagged(db):
    _seed_baseline(db)
    log_run(scenario="mission1", steps=100, final_x=1.0, final_y=1.0, result="FAIL",
            step_log=[], db_path=db, runner_type="local", nav_success_rate=0.10)

    summary = build_status_summary("local", ["mission1"], db_path=db)

    assert "⚠ mission1" in summary
    assert "DRIFT" in summary
    assert "nav_success_rate" in summary
    assert "python -m tools.agentic_validate" in summary


def test_reports_no_recent_run_for_unseen_scenario(db):
    summary = build_status_summary("local", ["mission1"], db_path=db)

    assert "mission1: no recent run" in summary


def test_reports_old_but_recent_run_within_default_window(db):
    """Regression test for the Critical staleness-window finding: the default window
    must NOT be generate_test_report's tight 30-minute 'this CI run's own result'
    window, or every real-world CLI/hook invocation shows 'no recent run' for
    genuinely fresh (just older than 30 min) data."""
    _seed_baseline(db)
    run_id = log_run(scenario="mission1", steps=100, final_x=1.0, final_y=1.0,
                      result="PASS", step_log=[], db_path=db, runner_type="local",
                      nav_success_rate=0.95)
    old_ts = (datetime.now() - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%S")
    conn = sqlite3.connect(db)
    conn.execute("UPDATE runs SET timestamp = ? WHERE id = ?", (old_ts, run_id))
    conn.commit()
    conn.close()

    summary = build_status_summary("local", ["mission1"], db_path=db)

    assert "mission1: PASS — ok" in summary
    assert "no recent run" not in summary
    assert "2h ago" in summary


def test_max_age_minutes_can_be_tightened_back_to_ci_behavior(db):
    """CI's own use case: pass max_age_minutes=30 explicitly to get generate_test_
    report's original 'this run's own result' behavior back.

    NOTE: ages out ALL 'mission1' rows (baseline seed rows included), not just the
    target run — load_run_rows()'s query picks the freshest row that still satisfies
    the age cutoff among ALL matching (runner_type, scenario) rows, so if only the
    target row were aged out, the freshest surviving _seed_baseline() row would be
    picked instead and the assertion below would spuriously fail (confirmed live
    while implementing this fix)."""
    _seed_baseline(db)
    run_id = log_run(scenario="mission1", steps=100, final_x=1.0, final_y=1.0,
                      result="PASS", step_log=[], db_path=db, runner_type="local",
                      nav_success_rate=0.95)
    old_ts = (datetime.now() - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%S")
    conn = sqlite3.connect(db)
    conn.execute("UPDATE runs SET timestamp = ? WHERE scenario = 'mission1'", (old_ts,))
    conn.commit()
    conn.close()

    summary = build_status_summary("local", ["mission1"], db_path=db, max_age_minutes=30)

    assert "mission1: no recent run" in summary


def test_main_prints_all_stages_by_default(db, monkeypatch, capsys):
    _seed_baseline(db)
    monkeypatch.setattr(sys, "argv", ["fleet_status", "--db", db])

    main()

    out = capsys.readouterr().out
    assert "Fleet status — local" in out
    assert "Fleet status — hil_jetson" in out
    assert "Fleet status — real_robot" in out
