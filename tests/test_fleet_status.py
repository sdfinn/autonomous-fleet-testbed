# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""Tests for tools/fleet_status.py's plain-text status summary."""
import sys

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


def test_main_prints_all_stages_by_default(db, monkeypatch, capsys):
    _seed_baseline(db)
    monkeypatch.setattr(sys, "argv", ["fleet_status", "--db", db])

    main()

    out = capsys.readouterr().out
    assert "Fleet status — local" in out
    assert "Fleet status — hil_jetson" in out
    assert "Fleet status — real_robot" in out
