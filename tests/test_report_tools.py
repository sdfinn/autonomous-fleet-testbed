# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""Smoke tests for the Stage-5 reporting path (S17 Piece 4): telemetry rows in →
schema validation green → per-run PDF out, scoped to one runner_type's own scenarios."""
import os
from datetime import datetime, timedelta

import pytest

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


def test_load_run_rows_excludes_stale_row_from_a_different_run(tmp_path):
    # Second-round review, 2026-07-26: with no recency bound, a red/crashed CI run could
    # show an unrelated earlier PASS for any scenario it never reached itself. Confirmed
    # live against the real DB — rows over 30 minutes old were shown as "this run's" data.
    import sqlite3
    db = str(tmp_path / "t.db")
    init_db(db)
    from tools.generate_test_report import load_run_rows
    run_id = log_run(scenario="mission2_no_ball", steps=5, final_x=0.0, final_y=0.0,
                      result="PASS", step_log=[], db_path=db, runner_type="hil_jetson")
    conn = sqlite3.connect(db)
    conn.execute("UPDATE runs SET timestamp = '2020-01-01T00:00:00' WHERE id = ?",
                 (run_id,))
    conn.commit()
    conn.close()
    rows = load_run_rows("hil_jetson", ["mission2_no_ball"], db_path=db)
    assert rows == []


def test_load_run_rows_keeps_row_within_max_age(tmp_path):
    import sqlite3
    from datetime import datetime, timedelta
    db = str(tmp_path / "t.db")
    init_db(db)
    from tools.generate_test_report import load_run_rows
    run_id = log_run(scenario="mission2_no_ball", steps=5, final_x=0.0, final_y=0.0,
                      result="PASS", step_log=[], db_path=db, runner_type="hil_jetson")
    old_ts = (datetime.now() - timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%S")
    conn = sqlite3.connect(db)
    conn.execute("UPDATE runs SET timestamp = ? WHERE id = ?", (old_ts, run_id))
    conn.commit()
    conn.close()
    rows = load_run_rows("hil_jetson", ["mission2_no_ball"], db_path=db, max_age_minutes=30)
    assert len(rows) == 1


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


def _seed_baseline_and_outlier(db_path):
    """10 PASS rows with natural variance (mean ~0.95, matching tests/test_baseline.py's
    established pattern — flat identical values would give zero variance, which
    check_run() explicitly skips) then one wild outlier."""
    for rate in (0.94, 0.95, 0.96, 0.95, 0.96, 0.94, 0.95, 0.96, 0.95, 0.94):
        log_run(scenario="mission1", steps=5, final_x=0.0, final_y=0.0, result="PASS",
                step_log=[], db_path=db_path, runner_type="local",
                nav_success_rate=rate)
    return log_run(scenario="mission1", steps=5, final_x=0.0, final_y=0.0,
                    result="PASS", step_log=[], db_path=db_path, runner_type="local",
                    nav_success_rate=0.10)


def test_generate_report_adds_drift_suffix_when_flagged(tmp_path):
    db = str(tmp_path / "t.db")
    init_db(db)
    _seed_baseline_and_outlier(db)
    from tools.generate_test_report import generate_report
    out = str(tmp_path / "report.pdf")
    result_path = generate_report("local", ["mission1"], db_path=db, output_path=out)
    assert result_path == str(tmp_path / "report-DRIFT.pdf")
    assert os.path.exists(result_path)


def test_generate_report_no_suffix_when_clean(tmp_path):
    db = str(tmp_path / "t.db")
    init_db(db)
    for rate in (0.94, 0.95, 0.96, 0.95, 0.96, 0.94, 0.95, 0.96, 0.95, 0.94):
        log_run(scenario="mission1", steps=5, final_x=0.0, final_y=0.0, result="PASS",
                step_log=[], db_path=db, runner_type="local", nav_success_rate=rate)
    # Well within the baseline's natural spread — a genuine "no drift" comparison,
    # not a vacuous pass from a zero-variance baseline being skipped entirely.
    log_run(scenario="mission1", steps=5, final_x=0.0, final_y=0.0, result="PASS",
            step_log=[], db_path=db, runner_type="local", nav_success_rate=0.95)
    from tools.generate_test_report import generate_report
    out = str(tmp_path / "report.pdf")
    result_path = generate_report("local", ["mission1"], db_path=db, output_path=out)
    assert result_path == out


def test_find_run_photos_matches_within_window(tmp_path):
    from tools.generate_test_report import find_run_photos
    photo_dir = tmp_path / "photos"
    photo_dir.mkdir()
    # Row timestamp 2026-07-21T10:05:00; a photo 90s earlier is well within a 180s window.
    (photo_dir / "mission1_step2_20260721_100330.png").write_bytes(b"fake-png")
    matches = find_run_photos("2026-07-21T10:05:00", photo_dir=str(photo_dir),
                               window_seconds=180)
    assert matches == [str(photo_dir / "mission1_step2_20260721_100330.png")]


def test_find_run_photos_excludes_outside_window(tmp_path):
    from tools.generate_test_report import find_run_photos
    photo_dir = tmp_path / "photos"
    photo_dir.mkdir()
    # 400s before the row — outside a 180s window.
    (photo_dir / "mission1_step2_20260721_095800.png").write_bytes(b"fake-png")
    matches = find_run_photos("2026-07-21T10:05:00", photo_dir=str(photo_dir),
                               window_seconds=180)
    assert matches == []


def test_find_run_photos_excludes_photos_after_the_row(tmp_path):
    from tools.generate_test_report import find_run_photos
    photo_dir = tmp_path / "photos"
    photo_dir.mkdir()
    # A photo AFTER the row's own timestamp belongs to a later run, not this one.
    (photo_dir / "mission1_step2_20260721_100600.png").write_bytes(b"fake-png")
    matches = find_run_photos("2026-07-21T10:05:00", photo_dir=str(photo_dir),
                               window_seconds=180)
    assert matches == []


def test_generate_report_embeds_matching_photo(tmp_path):
    db = str(tmp_path / "t.db")
    init_db(db)
    run_id = log_run(scenario="mission1", steps=5, final_x=0.0, final_y=0.0,
                      result="PASS", step_log=[], db_path=db, runner_type="local")
    # Read back the row's own timestamp so the fake photo lands inside the window.
    import sqlite3
    conn = sqlite3.connect(db)
    ts = conn.execute("SELECT timestamp FROM runs WHERE id = ?", (run_id,)).fetchone()[0]
    conn.close()
    photo_dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S")
    photo_name = f"mission1_step2_{(photo_dt - timedelta(seconds=5)).strftime('%Y%m%d_%H%M%S')}.png"
    photo_dir = tmp_path / "photos"
    photo_dir.mkdir()
    # A real tiny PNG (pillow is already a project dependency — nav_fleet/image_io.py
    # uses it — so this is safer than a hand-rolled byte blob reportlab might reject).
    from PIL import Image as PILImage
    PILImage.new("RGB", (4, 4), color=(0, 128, 0)).save(photo_dir / photo_name)

    from tools.generate_test_report import generate_report
    out = str(tmp_path / "report.pdf")
    result_path = generate_report("local", ["mission1"], db_path=db, output_path=out,
                                   photo_dir=str(photo_dir))
    assert os.path.exists(result_path)
    assert os.path.getsize(result_path) > 1000


def test_build_job_summary_plain_language_for_flagged_metric(tmp_path):
    db = str(tmp_path / "t.db")
    init_db(db)
    outlier_id = _seed_baseline_and_outlier(db)
    from tools.baseline_monitor import check_run
    from tools.generate_test_report import build_job_summary, load_run_rows
    rows = load_run_rows("local", ["mission1"], db_path=db)
    reports_by_row_id = {row["id"]: check_run(row["id"], db_path=db) for row in rows}
    any_flagged = any(r.flagged for rs in reports_by_row_id.values() for r in rs)
    summary = build_job_summary("local", rows, reports_by_row_id, any_flagged)
    assert "DRIFT DETECTED" in summary
    assert "nav_success_rate" in summary
    assert "σ" in summary  # plain-language sigma detail, not silence


def test_build_job_summary_quiet_when_clean(tmp_path):
    db = str(tmp_path / "t.db")
    init_db(db)
    # Real variance (not 11 identical values — a zero-variance baseline makes
    # check_run() skip the metric entirely, which would pass this test vacuously
    # without ever exercising a genuine non-flagged BaselineReport; see
    # _seed_baseline_and_outlier's comment and test_generate_report_no_suffix_when_clean
    # for the same established pattern).
    for rate in (0.94, 0.95, 0.96, 0.95, 0.96, 0.94, 0.95, 0.96, 0.95, 0.94):
        log_run(scenario="mission1", steps=5, final_x=0.0, final_y=0.0, result="PASS",
                step_log=[], db_path=db, runner_type="local", nav_success_rate=rate)
    # Well within the baseline's natural spread — a genuine "no drift" comparison.
    log_run(scenario="mission1", steps=5, final_x=0.0, final_y=0.0, result="PASS",
            step_log=[], db_path=db, runner_type="local", nav_success_rate=0.95)
    from tools.baseline_monitor import check_run
    from tools.generate_test_report import build_job_summary, load_run_rows
    rows = load_run_rows("local", ["mission1"], db_path=db)
    reports_by_row_id = {row["id"]: check_run(row["id"], db_path=db) for row in rows}
    # Guard against the vacuous case for real: at least one metric must have actually
    # been compared (a non-empty report list), not just silently skipped.
    assert any(reports_by_row_id.values())
    any_flagged = any(r.flagged for rs in reports_by_row_id.values() for r in rs)
    assert not any_flagged
    summary = build_job_summary("local", rows, reports_by_row_id, any_flagged)
    assert "DRIFT DETECTED" not in summary


def test_generate_report_writes_github_step_summary(tmp_path, monkeypatch):
    summary_file = tmp_path / "step_summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_file))
    db = str(tmp_path / "t.db")
    init_db(db)
    log_run(scenario="mission1", steps=5, final_x=0.0, final_y=0.0, result="PASS",
            step_log=[], db_path=db, runner_type="local")
    from tools.generate_test_report import generate_report
    out = str(tmp_path / "report.pdf")
    generate_report("local", ["mission1"], db_path=db, output_path=out)
    assert summary_file.exists()
    assert "mission1" in summary_file.read_text()


def test_generate_report_no_summary_write_when_env_unset(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    db = str(tmp_path / "t.db")
    init_db(db)
    log_run(scenario="mission1", steps=5, final_x=0.0, final_y=0.0, result="PASS",
            step_log=[], db_path=db, runner_type="local")
    from tools.generate_test_report import generate_report
    out = str(tmp_path / "report.pdf")
    # Must not raise even though GITHUB_STEP_SUMMARY is unset (local/dev invocation).
    generate_report("local", ["mission1"], db_path=db, output_path=out)


# ── Finding 1: directional wording (whole-branch review) ───────────────────────────────


def test_drift_detail_says_below_for_down_direction_metric(tmp_path):
    """nav_success_rate is direction=down (lower=worse) — a flagged low value must say
    'below baseline', not 'above' (the bug this fix corrects: sigma is always positive,
    so the old hardcoded 'above' wording was backwards for down-direction metrics)."""
    db = str(tmp_path / "t.db")
    init_db(db)
    _seed_baseline_and_outlier(db)  # outlier is nav_success_rate=0.10, well below baseline
    from tools.baseline_monitor import check_run
    from tools.generate_test_report import build_job_summary, load_run_rows
    rows = load_run_rows("local", ["mission1"], db_path=db)
    reports_by_row_id = {row["id"]: check_run(row["id"], db_path=db) for row in rows}
    summary = build_job_summary("local", rows, reports_by_row_id, True)
    assert "below baseline" in summary
    assert "above baseline" not in summary


def test_drift_detail_says_above_for_up_direction_metric(tmp_path):
    """mean_position_error is direction=up (higher=worse) — a flagged high value must
    say 'above baseline'."""
    db = str(tmp_path / "t.db")
    init_db(db)
    for err in (0.10, 0.12, 0.14, 0.11, 0.13, 0.10, 0.12, 0.14, 0.11, 0.13):
        log_run(scenario="mission1", steps=5, final_x=0.0, final_y=0.0, result="PASS",
                step_log=[], db_path=db, runner_type="local", mean_position_error=err)
    log_run(scenario="mission1", steps=5, final_x=0.0, final_y=0.0, result="PASS",
            step_log=[], db_path=db, runner_type="local", mean_position_error=5.0)
    from tools.baseline_monitor import check_run
    from tools.generate_test_report import build_job_summary, load_run_rows
    rows = load_run_rows("local", ["mission1"], db_path=db)
    reports_by_row_id = {row["id"]: check_run(row["id"], db_path=db) for row in rows}
    summary = build_job_summary("local", rows, reports_by_row_id, True)
    assert "above baseline" in summary
    assert "below baseline" not in summary


# ── Finding 3: evidence-artifact link in the Job Summary ───────────────────────────────


def test_build_job_summary_includes_evidence_artifact_when_given(tmp_path):
    db = str(tmp_path / "t.db")
    init_db(db)
    log_run(scenario="mission2_no_ball", steps=5, final_x=0.0, final_y=0.0, result="PASS",
            step_log=[], db_path=db, runner_type="hil_jetson")
    from tools.generate_test_report import build_job_summary, load_run_rows
    rows = load_run_rows("hil_jetson", ["mission2_no_ball"], db_path=db)
    summary = build_job_summary("hil_jetson", rows, {}, False,
                                 evidence_artifact="hil-mission-evidence-142")
    assert "hil-mission-evidence-142" in summary


def test_build_job_summary_omits_evidence_line_when_not_given(tmp_path):
    db = str(tmp_path / "t.db")
    init_db(db)
    log_run(scenario="mission1", steps=5, final_x=0.0, final_y=0.0, result="PASS",
            step_log=[], db_path=db, runner_type="local")
    from tools.generate_test_report import build_job_summary, load_run_rows
    rows = load_run_rows("local", ["mission1"], db_path=db)
    summary = build_job_summary("local", rows, {}, False)
    assert "Evidence" not in summary


# ── Piece 6: --stage as a declared alternative to --runner-type/--scenario ─────────────


def test_resolve_runner_and_scenarios_from_stage():
    from tools.generate_test_report import resolve_runner_and_scenarios
    runner_type, scenarios = resolve_runner_and_scenarios(
        stage="sim", runner_type=None, scenarios=None,
        load_stage=lambda s: ("local", ["bedroom_nav", "mission1"]),
    )
    assert runner_type == "local"
    assert scenarios == ["bedroom_nav", "mission1"]


def test_resolve_runner_and_scenarios_from_explicit_flags():
    from tools.generate_test_report import resolve_runner_and_scenarios
    runner_type, scenarios = resolve_runner_and_scenarios(
        stage=None, runner_type="local", scenarios=["mission1"],
        load_stage=lambda s: (_ for _ in ()).throw(AssertionError("should not be called")),
    )
    assert runner_type == "local"
    assert scenarios == ["mission1"]


def test_resolve_runner_and_scenarios_rejects_stage_plus_explicit_flags():
    from tools.generate_test_report import resolve_runner_and_scenarios
    with pytest.raises(ValueError):
        resolve_runner_and_scenarios(
            stage="sim", runner_type="local", scenarios=None,
            load_stage=lambda s: ("local", ["mission1"]),
        )


def test_resolve_runner_and_scenarios_rejects_neither_stage_nor_flags():
    from tools.generate_test_report import resolve_runner_and_scenarios
    with pytest.raises(ValueError):
        resolve_runner_and_scenarios(
            stage=None, runner_type=None, scenarios=None,
            load_stage=lambda s: ("local", ["mission1"]),
        )
