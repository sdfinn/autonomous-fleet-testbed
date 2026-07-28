"""Unit tests for tools/sim_vs_real_comparison.py.

Regression coverage for the 2026-07-27 fix: the original tool expected two
separate database files and had no `sim_engine` filter at all, so even pointing
both args at the same unified DB would have silently compared identical
unfiltered rows against themselves. These tests seed ONE db with both gazebo
and real rows (matching how telemetry_logger.log_run actually writes) and
assert the two sides are genuinely separated.
"""
from tools.sim_vs_real_comparison import compare_metrics, load_run_metrics
from tools.telemetry_logger import log_run


def test_load_run_metrics_filters_by_sim_engine(tmp_path):
    db = str(tmp_path / "t.db")
    log_run(scenario="mission1", steps=3, final_x=0.0, final_y=3.7, result="PASS",
            step_log=[], db_path=db, sim_engine="gazebo", nav_success_rate=1.0)
    log_run(scenario="mission1", steps=3, final_x=0.0, final_y=3.7, result="PASS",
            step_log=[], db_path=db, sim_engine="gazebo", nav_success_rate=1.0)
    log_run(scenario="mission1", steps=3, final_x=0.1, final_y=3.6, result="PASS",
            step_log=[], db_path=db, sim_engine="real", nav_success_rate=0.5)

    gazebo_rows = load_run_metrics(db, "gazebo")
    real_rows = load_run_metrics(db, "real")

    assert len(gazebo_rows) == 2
    assert len(real_rows) == 1


def test_compare_metrics_does_not_cross_contaminate_sim_and_real(tmp_path):
    db = str(tmp_path / "t.db")
    for scenario in ("mission2_no_ball", "mission2_yellow", "mission2_red"):
        log_run(scenario=scenario, steps=3, final_x=0.0, final_y=3.7, result="PASS",
                step_log=[], db_path=db, sim_engine="gazebo", nav_success_rate=1.0,
                mean_position_error=0.08)
    for scenario in ("mission2_no_ball", "mission2_yellow", "mission2_red"):
        log_run(scenario=scenario, steps=3, final_x=0.1, final_y=3.5, result="PASS",
                step_log=[], db_path=db, sim_engine="real", nav_success_rate=0.5,
                mean_position_error=0.30)

    results = compare_metrics(db, sim_engine="gazebo", real_engine="real")

    assert results["scenario_matches"] == 3
    nav = results["metrics"]["nav_success_rate"]
    assert nav["sim_mean"] == 1.0
    assert nav["real_mean"] == 0.5
    pos_err = results["metrics"]["mean_position_error"]
    assert pos_err["sim_mean"] == 0.08
    assert pos_err["real_mean"] == 0.30


def test_main_defaults_to_the_shared_fleet_db(monkeypatch, tmp_path, capsys):
    """--db defaults to tools.telemetry_logger.DB_PATH, not a separate guessed path
    (the drift-prone pattern CLAUDE.md documents for FLEET_DB consumers) — verified
    by actually running main() with no --db flag and checking it read the
    monkeypatched DB_PATH, not some other default."""
    import sys

    import tools.sim_vs_real_comparison as svc

    fake_db = str(tmp_path / "shared.db")
    log_run(scenario="mission1", steps=3, final_x=0.0, final_y=3.7, result="PASS",
            step_log=[], db_path=fake_db, sim_engine="gazebo", nav_success_rate=1.0)
    log_run(scenario="mission1", steps=3, final_x=0.1, final_y=3.6, result="PASS",
            step_log=[], db_path=fake_db, sim_engine="real", nav_success_rate=0.5)

    monkeypatch.setattr(svc, "DB_PATH", fake_db)
    monkeypatch.setattr(sys, "argv", ["sim_vs_real_comparison.py"])

    svc.main()

    out = capsys.readouterr().out
    assert fake_db in out
    assert "sim_mean:  1" in out
    assert "real_mean: 0.5" in out
