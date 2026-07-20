# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""Smoke tests for the Stage-5 reporting path (S17 review item E3): telemetry rows in →
schema validation green → PDF out. Protects the whole reports pipeline for ~30 lines."""
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


def test_generate_report_produces_pdf(tmp_path):
    db = str(tmp_path / "t.db")
    init_db(db)
    _seed(db)
    from tools.generate_test_report import generate_report
    out = str(tmp_path / "report.pdf")
    result_path = generate_report(db_path=db, output_path=out)
    assert os.path.exists(result_path)
    assert os.path.getsize(result_path) > 1000  # a real PDF, not an empty stub
