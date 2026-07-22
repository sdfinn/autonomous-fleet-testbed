import pytest

from tools.baseline_monitor import check_latest_run, check_run, load_config
from tools.telemetry_logger import init_db, log_run

# Baseline seed: 10 runs with natural variance around fleet navigation metrics.
# 2σ range is narrow enough that a clear outlier should be flagged.
_BASELINE_NAV_SUCCESS_RATES = [0.94, 0.95, 0.96, 0.95, 0.96, 0.94, 0.95, 0.96, 0.95, 0.94]

# Two tight, well-separated cohorts for context-slicing tests (Session 16 finding I4).
# Each has small non-zero variance (so nav_success_rate isn't a zero-variance skip) but
# the two means (~0.95 vs ~0.50) are far enough apart that a mixed baseline has ~1σ span
# — a value from one cohort would NOT flag against the mixed pool but WILL flag against
# its own cohort's tight baseline. That gap is what makes these tests decisive.
_COHORT_HI = [0.94, 0.95, 0.96, 0.95, 0.96, 0.94, 0.95, 0.96, 0.95, 0.94]  # mean ~0.95
_COHORT_LO = [0.49, 0.50, 0.51, 0.50, 0.51, 0.49, 0.50, 0.51, 0.50, 0.49]  # mean ~0.50


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
    runner_type=None,
    power_mode=None,
    scenario="baseline_test",
):
    return log_run(
        scenario=scenario,
        steps=steps,
        final_x=1.5,
        final_y=1.0,
        result=result,
        step_log=[],
        db_path=db_path,
        nav_success_rate=nav_success_rate,
        mean_position_error=mean_position_error,
        collision_rate=collision_rate,
        odom_hz_mean=odom_hz_mean,
        camera_hz_mean=camera_hz_mean,
        runner_type=runner_type,
        power_mode=power_mode,
    )


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


def test_fail_rows_excluded_from_baseline(db):
    """Policy (Session 16): FAIL rows never enter the drift baseline window."""
    # Seed baseline with variance in both nav_success_rate AND mean_position_error
    # so both metrics appear in reports (zero-variance metrics are skipped).
    for rate, err in zip(_BASELINE_NAV_SUCCESS_RATES,
                         [0.10, 0.12, 0.14, 0.11, 0.13, 0.10, 0.12, 0.14, 0.11, 0.13]):
        _insert(db, nav_success_rate=rate, mean_position_error=err)
    # A wild FAIL row that would wreck the baseline mean if included:
    _insert(db, nav_success_rate=0.0, result="FAIL",
            mean_position_error=99.0)
    run_id = _insert(db, nav_success_rate=0.95)  # normal PASS run under check
    reports = check_run(run_id, db_path=db)
    by_metric = {r.metric: r for r in reports}
    # FAIL row is excluded from baseline by the query filter (WHERE result='PASS'),
    # so nav_success_rate baseline remains unaffected by the extreme 0.0 value
    assert not by_metric["nav_success_rate"].flagged
    assert not by_metric["mean_position_error"].flagged


def test_baseline_sliced_by_runner_and_power(db):
    """Finding I4 (Session 16): drift compares like with like. A 15W hil_jetson run must
    baseline only against 15W hil_jetson history — never against 25W sim rows, and vice
    versa. Two well-separated cohorts share the same DB; a value drawn from cohort B must
    flag when checked in cohort A, proving the other cohort was excluded from its baseline.
    (If slicing were absent, the mixed 0.95/0.50 pool spans ~1σ and neither would flag.)
    """
    for rate in _COHORT_HI:
        _insert(db, nav_success_rate=rate, runner_type="hil_jetson", power_mode="15W")
    for rate in _COHORT_LO:
        _insert(db, nav_success_rate=rate, runner_type="local", power_mode="25W")

    # A 15W HIL run at 0.50 (the *sim* cohort's value) is a huge outlier vs the 15W
    # baseline (~0.95) — flagged only if the 25W rows were correctly excluded.
    hil_run = _insert(db, nav_success_rate=0.50, runner_type="hil_jetson", power_mode="15W")
    hil_reports = {r.metric: r for r in check_run(hil_run, db_path=db)}
    assert hil_reports["nav_success_rate"].flagged

    # Symmetric leg REWRITTEN with CR-01 (direction-aware flagging): the old version used
    # 0.95 vs the low cohort — an IMPROVEMENT, which correctly no longer flags. Use a
    # worse-direction outlier (0.10 vs the ~0.50 cohort) instead, and assert sigma > 10:
    # only the tight own-cohort baseline (sd ~0.008 → sigma ~50) can produce that; a
    # slicing regression that mixed both cohorts (sd ~0.23) would cap sigma near ~2.7.
    sim_run = _insert(db, nav_success_rate=0.10, runner_type="local", power_mode="25W")
    sim_reports = {r.metric: r for r in check_run(sim_run, db_path=db)}
    assert sim_reports["nav_success_rate"].flagged
    assert sim_reports["nav_success_rate"].sigma > 10


def test_null_power_rows_baseline_against_each_other(db):
    """Finding I4 corollary: pre-Session-16 sim rows have power_mode=NULL. A NULL-power
    run must baseline against NULL-power history via NULL-safe `IS ?` (a plain `= ?` would
    match no NULL row → empty baseline → no report). Non-NULL rows must not pollute it.
    """
    for rate in _COHORT_HI:
        _insert(db, nav_success_rate=rate)  # runner_type/power_mode default to NULL
    for rate in _COHORT_LO:
        _insert(db, nav_success_rate=rate, runner_type="hil_jetson", power_mode="15W")

    # NULL-power run at 0.50: outlier vs the NULL baseline (~0.95). A report existing AND
    # flagged proves (a) the NULL rows matched each other via `IS NULL`, and (b) the 15W
    # rows were excluded (else the mixed pool would not flag it).
    null_run = _insert(db, nav_success_rate=0.50)
    reports = {r.metric: r for r in check_run(null_run, db_path=db)}
    assert "nav_success_rate" in reports, "NULL-power baseline produced no report"
    assert reports["nav_success_rate"].flagged


def test_baseline_sliced_by_scenario(db):
    """Piece 4 prerequisite: mixing scenarios in one baseline window produces a false
    drift signal from the scenario mix shifting, not from anything actually getting
    worse. scenario must be sliced exactly like runner_type/power_mode already are.
    Same runner_type/power_mode for both cohorts — only scenario differs — so this
    fails today (scenario isn't in slice_cols yet) and passes once it is.
    """
    for rate in _COHORT_HI:
        _insert(db, nav_success_rate=rate, runner_type="hil_jetson", power_mode="15W",
                scenario="mission2_no_ball")
    for rate in _COHORT_LO:
        _insert(db, nav_success_rate=rate, runner_type="hil_jetson", power_mode="15W",
                scenario="mission2_red")

    # A mission2_red run at 0.10 (much worse than either cohort) is a huge outlier vs
    # the mission2_red baseline (~0.50) — flagged only if mission2_no_ball rows were
    # correctly excluded from this scenario's own baseline. Without scenario slicing,
    # the mixed baseline (~0.72, sd ~0.23) gives sigma ~2.7; with slicing, the tight
    # mission2_red baseline (sd ~0.008) gives sigma ~50.
    red_run = _insert(db, nav_success_rate=0.10, runner_type="hil_jetson",
                       power_mode="15W", scenario="mission2_red")
    red_reports = {r.metric: r for r in check_run(red_run, db_path=db)}
    assert red_reports["nav_success_rate"].flagged
    assert red_reports["nav_success_rate"].sigma > 10


# ── CR-01/CR-02 (Session 17 code review): direction-aware flagging + config wiring ──────


def test_improvement_is_not_flagged_down_metric(db):
    """CR-01: nav_success_rate direction is 'down' (lower = worse). A run BETTER than
    baseline by many sigma is an improvement, not drift — it must never flag."""
    _seed_baseline(db)                      # mean ~0.95, sd ~0.008
    run_id = _insert(db, nav_success_rate=1.0)   # ~6 sigma ABOVE mean — an improvement
    reports = {r.metric: r for r in check_run(run_id, db_path=db)}
    assert not reports["nav_success_rate"].flagged
    assert reports["nav_success_rate"].severity is None


def test_improvement_is_not_flagged_up_metric(db):
    """CR-01 symmetric: mean_position_error direction is 'up' (higher = worse). A run
    far BELOW baseline error is an improvement — never flagged."""
    for err in (0.10, 0.12, 0.14, 0.11, 0.13, 0.10, 0.12, 0.14, 0.11, 0.13):
        _insert(db, mean_position_error=err)     # mean ~0.12
    run_id = _insert(db, mean_position_error=0.001)  # dramatically better
    reports = {r.metric: r for r in check_run(run_id, db_path=db)}
    assert not reports["mean_position_error"].flagged


def test_regression_in_bad_direction_still_flags(db):
    """CR-01 control: a worse-direction outlier still flags (behavior preserved)."""
    for err in (0.10, 0.12, 0.14, 0.11, 0.13, 0.10, 0.12, 0.14, 0.11, 0.13):
        _insert(db, mean_position_error=err)
    run_id = _insert(db, mean_position_error=0.90)   # much WORSE
    reports = {r.metric: r for r in check_run(run_id, db_path=db)}
    assert reports["mean_position_error"].flagged


def test_severity_bands_from_config(db):
    """CR-02: sigma severity bands come from drift_config.yaml (info 2 / warning 3 /
    error 4 / critical 5). An extreme worse-direction outlier lands 'critical'."""
    _seed_baseline(db)
    run_id = _insert(db, nav_success_rate=0.10)      # ~100 sigma below mean
    reports = {r.metric: r for r in check_run(run_id, db_path=db)}
    assert reports["nav_success_rate"].severity == "critical"
    assert reports["nav_success_rate"].flagged


def test_config_history_window_and_threshold_honored(db, tmp_path):
    """CR-02: check_run must read history_window and sigma bands from the YAML, not
    hardcode them. A config with an absurdly high info threshold must un-flag an
    outlier the default config would flag."""
    cfg = tmp_path / "drift_test.yaml"
    cfg.write_text(
        "history_window: 5\n"
        "sigma:\n  info: 50.0\n  warning: 60.0\n  error: 70.0\n  critical: 80.0\n"
        "metrics:\n  nav_success_rate:\n    direction: down\n"
    )
    _seed_baseline(db)
    run_id = _insert(db, nav_success_rate=0.60)      # huge worse-direction outlier
    default_reports = {r.metric: r for r in check_run(run_id, db_path=db)}
    assert default_reports["nav_success_rate"].flagged
    lax_reports = {r.metric: r for r in check_run(run_id, db_path=db,
                                                  config_path=str(cfg))}
    assert not lax_reports["nav_success_rate"].flagged
    # The lax config only watches nav_success_rate — other metrics must not report.
    assert set(lax_reports) == {"nav_success_rate"}


def test_canonical_config_loads_and_is_valid():
    """CR-02/CR-03: the repo's canonical config/drift_config.yaml parses and declares
    everything baseline_monitor needs — this test IS the guard against config rot."""
    cfg = load_config()
    assert cfg["history_window"] >= 3
    for band in ("info", "warning", "error", "critical"):
        assert band in cfg["sigma"]
    assert cfg["metrics"], "no watched metrics configured"
    for name, spec in cfg["metrics"].items():
        assert spec["direction"] in ("up", "down"), f"{name}: bad direction"
