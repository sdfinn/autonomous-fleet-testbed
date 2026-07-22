# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""Smoke tests for the Stage-5 reporting path (S17 Piece 4): telemetry rows in →
schema validation green → per-run PDF out, scoped to one runner_type's own scenarios."""
import os

from tools.telemetry_logger import init_db, log_run
from tools.validate_telemetry import detect_schema_drift, validate_runs, validate_steps


def _seed(db_path):
    for result, sim in (("PASS", 0.03), ("FAIL", 0.21)):
        log_run(scenario="mission2_no_ball", steps=5, final_x=-1.27, final_y=1.2,
                result=result, step_log=[{"step": 1, "x": 0.0, "y": 0.0}],
                db_path=db_path, runner_type="hil_jetson", power_mode="15W",
                nav_success_rate=1.0 if result == "PASS" else 0.0,
                home_photo_similarity=sim)


def test_validate_telemetry_green_on_real_logger_output(tmp_path):
    db = str(tmp_path / "t.db")
    init_db(db)
    _seed(db)
    assert validate_runs(db)
    assert validate_steps(db)
    assert detect_schema_drift(db)


def test_load_run_rows_returns_latest_per_scenario(tmp_path):
    db = str(tmp_path / "t.db")
    init_db(db)
    from tools.generate_test_report import load_run_rows
    # Two mission1 rows — the second (later) one must win.
    log_run(scenario="mission1", steps=3, final_x=0.0, final_y=0.0, result="FAIL",
            step_log=[], db_path=db, runner_type="local")
    log_run(scenario="mission1", steps=5, final_x=1.0, final_y=1.0, result="PASS",
            step_log=[], db_path=db, runner_type="local")
    log_run(scenario="bedroom_nav", steps=8, final_x=2.0, final_y=2.0, result="PASS",
            step_log=[], db_path=db, runner_type="local")
    rows = load_run_rows("local", ["bedroom_nav", "mission1"], db_path=db)
    by_scenario = {r["scenario"]: r for r in rows}
    assert by_scenario["mission1"]["result"] == "PASS"
    assert by_scenario["mission1"]["steps"] == 5
    assert by_scenario["bedroom_nav"]["result"] == "PASS"


def test_load_run_rows_skips_scenario_with_no_history(tmp_path):
    db = str(tmp_path / "t.db")
    init_db(db)
    from tools.generate_test_report import load_run_rows
    log_run(scenario="mission1", steps=5, final_x=0.0, final_y=0.0, result="PASS",
            step_log=[], db_path=db, runner_type="local")
    rows = load_run_rows("local", ["bedroom_nav", "mission1"], db_path=db)
    assert [r["scenario"] for r in rows] == ["mission1"]


def test_load_run_rows_respects_runner_type(tmp_path):
    db = str(tmp_path / "t.db")
    init_db(db)
    from tools.generate_test_report import load_run_rows
    log_run(scenario="mission1", steps=5, final_x=0.0, final_y=0.0, result="PASS",
            step_log=[], db_path=db, runner_type="hil_jetson")
    rows = load_run_rows("local", ["mission1"], db_path=db)
    assert rows == []


def test_generate_report_produces_pdf(tmp_path):
    db = str(tmp_path / "t.db")
    init_db(db)
    _seed(db)
    from tools.generate_test_report import generate_report
    out = str(tmp_path / "report.pdf")
    result_path = generate_report("hil_jetson", ["mission2_no_ball"], db_path=db,
                                   output_path=out)
    assert os.path.exists(result_path)
    assert os.path.getsize(result_path) > 1000  # a real PDF, not an empty stub


def test_generate_report_has_no_trend_chart_functions():
    """Piece 4 spec: no historical trend charts in the per-run report — that content
    moved to Piece 5's dashboard. Locks in the removal so it can't silently creep back."""
    import tools.generate_test_report as gtr
    assert not hasattr(gtr, "make_pass_fail_chart")
    assert not hasattr(gtr, "make_position_scatter")
