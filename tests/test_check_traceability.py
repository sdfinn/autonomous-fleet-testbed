# Copyright 2026 Mike. Licensed under MIT.
"""Tests for tools/check_traceability.py"""
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
import check_traceability as ct
from check_traceability import Requirement, Result


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def traceability_yaml(tmp_path):
    content = """\
requirements:
  - id: BR-01
    description: Robot reaches goal within 0.15m
    tests:
      - tests/test_navigation.py::test_goal_position_error
  - id: BR-02
    description: Zero collisions per run
    tests:
      - tests/test_navigation.py::test_zero_collisions
"""
    p = tmp_path / "traceability.yaml"
    p.write_text(content)
    return p


@pytest.fixture
def profile_yaml(tmp_path):
    p = tmp_path / "robot_profile.yaml"
    p.write_text("name: test_robot\nskip_requirements: []\n")
    return p


@pytest.fixture
def profile_yaml_with_skip(tmp_path):
    p = tmp_path / "robot_profile_skip.yaml"
    p.write_text("name: test_robot\nskip_requirements:\n  - BR-02\n")
    return p


@pytest.fixture
def test_dir_full(tmp_path):
    """Both BR-01 and BR-02 tests exist."""
    d = tmp_path / "tests"
    d.mkdir()
    (d / "test_navigation.py").write_text(
        "def test_goal_position_error(): pass\n"
        "def test_zero_collisions(): pass\n"
        "def helper_not_a_test(): pass\n"
    )
    return d


@pytest.fixture
def test_dir_partial(tmp_path):
    """Only BR-01 test exists — BR-02 test is missing."""
    d = tmp_path / "tests"
    d.mkdir()
    (d / "test_navigation.py").write_text(
        "def test_goal_position_error(): pass\n"
    )
    return d


# ---------------------------------------------------------------------------
# load_traceability
# ---------------------------------------------------------------------------

class TestLoadTraceability:
    def test_loads_id_description_and_tests(self, traceability_yaml):
        reqs = ct.load_traceability(traceability_yaml)
        assert len(reqs) == 2
        assert reqs[0].id == "BR-01"
        assert reqs[0].description == "Robot reaches goal within 0.15m"
        assert reqs[0].tests == ["tests/test_navigation.py::test_goal_position_error"]

    def test_exits_2_on_missing_file(self, tmp_path):
        with pytest.raises(SystemExit) as exc:
            ct.load_traceability(tmp_path / "nonexistent.yaml")
        assert exc.value.code == 2

    def test_exits_2_on_malformed_yaml(self, tmp_path):
        bad = tmp_path / "bad.yaml"
        bad.write_text("requirements: [invalid: {")
        with pytest.raises(SystemExit) as exc:
            ct.load_traceability(bad)
        assert exc.value.code == 2


# ---------------------------------------------------------------------------
# load_profile
# ---------------------------------------------------------------------------

class TestLoadProfile:
    def test_returns_empty_set_when_no_skips(self, profile_yaml):
        assert ct.load_profile(profile_yaml) == set()

    def test_returns_skip_ids(self, profile_yaml_with_skip):
        assert ct.load_profile(profile_yaml_with_skip) == {"BR-02"}

    def test_exits_2_on_missing_profile(self, tmp_path):
        with pytest.raises(SystemExit) as exc:
            ct.load_profile(tmp_path / "missing.yaml")
        assert exc.value.code == 2
