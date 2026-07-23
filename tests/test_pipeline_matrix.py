"""Tests for tools.pipeline_matrix — the single declared source for which
scenarios belong to which CI report stage (Session 17 Piece 6)."""

import pytest

from tools.pipeline_matrix import UnknownStageError, load_stage


def test_load_stage_reads_runner_type_and_scenarios(tmp_path):
    config = tmp_path / "matrix.yaml"
    config.write_text(
        "sim:\n"
        "  runner_type: local\n"
        "  scenarios: [bedroom_nav, mission1]\n"
    )

    runner_type, scenarios = load_stage("sim", path=config)

    assert runner_type == "local"
    assert scenarios == ["bedroom_nav", "mission1"]


def test_load_stage_raises_for_unknown_stage(tmp_path):
    config = tmp_path / "matrix.yaml"
    config.write_text("sim:\n  runner_type: local\n  scenarios: [mission1]\n")

    with pytest.raises(UnknownStageError):
        load_stage("nonexistent", path=config)


def test_real_config_declares_sim_stage_matching_ci():
    runner_type, scenarios = load_stage("sim")

    assert runner_type == "local"
    assert scenarios == ["bedroom_nav", "mission1"]


def test_real_config_declares_hil_stage_matching_ci():
    runner_type, scenarios = load_stage("hil")

    assert runner_type == "hil_jetson"
    assert scenarios == ["mission2_no_ball", "mission2_yellow", "mission2_red"]
