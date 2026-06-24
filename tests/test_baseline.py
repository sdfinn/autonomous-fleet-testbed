import sqlite3
import pytest

from tools.baseline_monitor import check_latest_run, check_run
from tools.telemetry_logger import init_db, log_run

# Baseline seed: 10 runs with natural variance around fleet navigation metrics.
# 2σ range is narrow enough that a clear outlier should be flagged.
_BASELINE_NAV_SUCCESS_RATES = [0.94, 0.95, 0.96, 0.95, 0.96, 0.94, 0.95, 0.96, 0.95, 0.94]


@pytest.fixture()
def db(tmp_path):
    path = str(tmp_path / "test_baseline.db")
    init_db(path)
    return path


def _insert(
    db_path,
    nav_success_rate=0.95,
    steps=100,
    result="PASS",
    mean_position_error=0.12,
    collision_rate=0.0,
    odom_hz_mean=50.0,
    camera_hz_mean=20.0,
):
    run_id = log_run(
        scenario="baseline_test",
        steps=steps,
        final_x=1.5,
        final_y=1.0,
        result=result,
        step_log=[],
        db_path=db_path,
    )
    conn = sqlite3.connect(db_path)
    conn.execute(
        "UPDATE runs SET nav_success_rate = ?, mean_position_error = ?, collision_rate = ?, odom_hz_mean = ?, camera_hz_mean = ? WHERE id = ?",
        (nav_success_rate, mean_position_error, collision_rate, odom_hz_mean, camera_hz_mean, run_id),
    )
    conn.commit()
    conn.close()
    return run_id


def _seed_baseline(db_path):
    for value in _BASELINE_NAV_SUCCESS_RATES:
        _insert(db_path, nav_success_rate=value)


def test_no_drift_within_baseline(db):
    _seed_baseline(db)
    run_id = _insert(db, nav_success_rate=0.95)
    reports = check_run(run_id, db_path=db)
    assert not any(r.flagged for r in reports)


def test_drift_detected_above_threshold(db):
    _seed_baseline(db)
    run_id = _insert(db, nav_success_rate=0.60, result="FAIL")  # large deviation below baseline
    reports = check_run(run_id, db_path=db)
    nav_reports = [r for r in reports if r.metric == "nav_success_rate"]
    assert nav_reports, "Expected a nav_success_rate metric report"
    assert nav_reports[0].flagged
    assert nav_reports[0].sigma > 2.0


def test_insufficient_baseline_data_returns_empty(db):
    # Only 2 PASS runs — below the 3-sample minimum
    _insert(db, steps=100)
    _insert(db, steps=110)
    run_id = _insert(db, steps=200)
    assert check_run(run_id, db_path=db) == []


def test_check_latest_run_empty_db(db):
    assert check_latest_run(db_path=db) is None


def test_fail_runs_excluded_from_baseline(db):
    _seed_baseline(db)
    # FAIL runs at 500 steps must not skew the baseline
    for _ in range(5):
        _insert(db, steps=500, result="FAIL")
    run_id = _insert(db, steps=101)
    reports = check_run(run_id, db_path=db)
    assert not any(r.flagged for r in reports)


def test_report_sigma_direction(db):
    _seed_baseline(db)
    run_id = _insert(db, nav_success_rate=0.10)  # extreme low outlier (~33σ below mean)
    reports = check_run(run_id, db_path=db)
    nav_reports = [r for r in reports if r.metric == "nav_success_rate"]
    assert nav_reports and nav_reports[0].flagged
