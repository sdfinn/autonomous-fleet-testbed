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


# ---------------------------------------------------------------------------
# scan_tests
# ---------------------------------------------------------------------------

class TestScanTests:
    def test_finds_test_functions(self, test_dir_full):
        found = ct.scan_tests(test_dir_full)
        assert "tests/test_navigation.py::test_goal_position_error" in found
        assert "tests/test_navigation.py::test_zero_collisions" in found

    def test_ignores_non_test_functions(self, test_dir_full):
        found = ct.scan_tests(test_dir_full)
        assert not any("helper" in t for t in found)

    def test_empty_directory_returns_empty_set(self, tmp_path):
        d = tmp_path / "tests"
        d.mkdir()
        assert ct.scan_tests(d) == set()

    def test_gracefully_skips_syntax_error_files(self, tmp_path):
        d = tmp_path / "tests"
        d.mkdir()
        (d / "test_broken.py").write_text("def test_ok(): pass\ndef broken(: !!!")
        result = ct.scan_tests(d)
        assert isinstance(result, set)  # did not raise


# ---------------------------------------------------------------------------
# find_orphans
# ---------------------------------------------------------------------------

class TestFindOrphans:
    def test_no_orphans_when_all_mapped(self):
        existing = {"tests/test_nav.py::test_foo"}
        mapped = {"tests/test_nav.py::test_foo"}
        assert ct.find_orphans(existing, mapped) == []

    def test_finds_unmapped_test(self):
        existing = {"tests/test_nav.py::test_foo", "tests/test_nav.py::test_bar"}
        mapped = {"tests/test_nav.py::test_foo"}
        assert ct.find_orphans(existing, mapped) == ["tests/test_nav.py::test_bar"]

    def test_returns_sorted_list(self):
        existing = {"tests/z.py::test_z", "tests/a.py::test_a"}
        assert ct.find_orphans(existing, set()) == [
            "tests/a.py::test_a",
            "tests/z.py::test_z",
        ]


# ---------------------------------------------------------------------------
# check_coverage
# ---------------------------------------------------------------------------

class TestCheckCoverage:
    def _reqs(self):
        return [
            Requirement("BR-01", "desc1",
                        ["tests/test_navigation.py::test_goal_position_error"]),
            Requirement("BR-02", "desc2",
                        ["tests/test_navigation.py::test_zero_collisions"]),
        ]

    def test_all_covered(self, test_dir_full):
        existing = ct.scan_tests(test_dir_full)
        result = ct.check_coverage(self._reqs(), existing, set())
        assert len(result.covered) == 2
        assert len(result.missing) == 0
        assert len(result.skipped) == 0

    def test_partial_coverage_marks_missing(self, test_dir_partial):
        existing = ct.scan_tests(test_dir_partial)
        result = ct.check_coverage(self._reqs(), existing, set())
        assert len(result.covered) == 1
        assert len(result.missing) == 1
        assert result.missing[0].id == "BR-02"

    def test_skipped_requirements_not_in_missing(self, test_dir_partial):
        existing = ct.scan_tests(test_dir_partial)
        result = ct.check_coverage(self._reqs(), existing, {"BR-02"})
        assert len(result.skipped) == 1
        assert result.skipped[0].id == "BR-02"
        assert len(result.missing) == 0

    def test_unmapped_test_becomes_orphan(self, test_dir_full):
        # test_dir_full has test_zero_collisions; only map BR-01
        existing = ct.scan_tests(test_dir_full)
        reqs = [Requirement("BR-01", "d",
                            ["tests/test_navigation.py::test_goal_position_error"])]
        result = ct.check_coverage(reqs, existing, set())
        assert "tests/test_navigation.py::test_zero_collisions" in result.orphans


# ---------------------------------------------------------------------------
# Output formatters
# ---------------------------------------------------------------------------

def _make_full_result():
    return Result(
        covered=[Requirement("BR-01", "Robot reaches goal", ["tests/t.py::test_foo"])],
        missing=[Requirement("BR-02", "Zero collisions", ["tests/t.py::test_bar"])],
        skipped=[Requirement("BR-03", "Recovery timeout", ["tests/t.py::test_baz"])],
        orphans=["tests/t.py::test_orphan"],
    )


class TestFormatJson:
    def test_required_top_level_keys(self):
        result = _make_full_result()
        data = json.loads(ct.format_json(result, "abc123", "jetson_ugv_pt"))
        assert data["git_sha"] == "abc123"
        assert data["profile"] == "jetson_ugv_pt"
        assert "summary" in data
        assert "requirements" in data
        assert "orphans" in data

    def test_summary_counts(self):
        result = _make_full_result()
        data = json.loads(ct.format_json(result, "sha1", None))
        assert data["summary"]["covered"] == 1
        assert data["summary"]["missing"] == 1
        assert data["summary"]["skipped"] == 1
        assert data["summary"]["orphans"] == 1
        assert data["summary"]["total"] == 3  # covered + missing + skipped

    def test_requirement_status_field(self):
        result = _make_full_result()
        data = json.loads(ct.format_json(result, "sha1", None))
        statuses = {r["id"]: r["status"] for r in data["requirements"]}
        assert statuses["BR-01"] == "covered"
        assert statuses["BR-02"] == "missing"
        assert statuses["BR-03"] == "skipped"

    def test_orphans_list(self):
        result = _make_full_result()
        data = json.loads(ct.format_json(result, "sha1", None))
        assert data["orphans"] == ["tests/t.py::test_orphan"]

    def test_null_git_sha_falls_back_gracefully(self):
        result = Result(covered=[], missing=[], skipped=[], orphans=[])
        data = json.loads(ct.format_json(result, None, None))
        assert isinstance(data["git_sha"], str)  # falls back to env or "unknown"


class TestFormatRich:
    def test_covered_requirement_shown(self, capsys):
        result = Result(
            covered=[Requirement("BR-01", "Robot reaches goal", ["tests/t.py::test_foo"])],
            missing=[], skipped=[], orphans=[],
        )
        ct.format_rich(result, None)
        out = capsys.readouterr().out
        assert "BR-01" in out
        assert "Robot reaches goal" in out

    def test_missing_requirement_shown(self, capsys):
        result = Result(
            covered=[],
            missing=[Requirement("BR-02", "Zero collisions", ["tests/t.py::test_bar"])],
            skipped=[], orphans=[],
        )
        ct.format_rich(result, None)
        out = capsys.readouterr().out
        assert "BR-02" in out
        assert "Zero collisions" in out

    def test_orphan_warning_shown(self, capsys):
        result = Result(covered=[], missing=[], skipped=[],
                        orphans=["tests/t.py::test_orphan"])
        ct.format_rich(result, None)
        out = capsys.readouterr().out
        assert "test_orphan" in out


class TestFormatQuiet:
    def test_covered_shows_ok(self, capsys):
        result = Result(
            covered=[Requirement("BR-01", "desc", ["tests/t.py::test_foo"])],
            missing=[], skipped=[], orphans=[],
        )
        ct.format_quiet(result)
        assert "OK" in capsys.readouterr().out

    def test_missing_shows_fail(self, capsys):
        result = Result(
            covered=[],
            missing=[Requirement("BR-02", "desc", ["tests/t.py::test_bar"])],
            skipped=[], orphans=[],
        )
        ct.format_quiet(result)
        assert "FAIL" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# main() integration tests
# ---------------------------------------------------------------------------

class TestMainCLI:
    def test_exit_0_when_all_covered(self, traceability_yaml, test_dir_full):
        with patch("sys.argv", [
            "check_traceability.py",
            str(traceability_yaml),
            str(test_dir_full),
        ]):
            rc = ct.main()
        assert rc == 0

    def test_exit_1_when_requirement_missing(self, traceability_yaml, test_dir_partial):
        with patch("sys.argv", [
            "check_traceability.py",
            str(traceability_yaml),
            str(test_dir_partial),
        ]):
            rc = ct.main()
        assert rc == 1

    def test_exit_2_on_missing_traceability_file(self, tmp_path, test_dir_full):
        with patch("sys.argv", [
            "check_traceability.py",
            str(tmp_path / "nonexistent.yaml"),
            str(test_dir_full),
        ]):
            with pytest.raises(SystemExit) as exc:
                ct.main()
        assert exc.value.code == 2

    def test_exit_2_on_missing_test_dir(self, traceability_yaml, tmp_path):
        with patch("sys.argv", [
            "check_traceability.py",
            str(traceability_yaml),
            str(tmp_path / "nonexistent_dir"),
        ]):
            with pytest.raises(SystemExit) as exc:
                ct.main()
        assert exc.value.code == 2

    def test_json_flag_produces_valid_json(self, traceability_yaml, test_dir_full, capsys):
        with patch("sys.argv", [
            "check_traceability.py",
            str(traceability_yaml),
            str(test_dir_full),
            "--json",
        ]):
            ct.main()
        data = json.loads(capsys.readouterr().out)
        assert "summary" in data
        assert data["summary"]["covered"] == 2

    def test_profile_skip_makes_partial_pass(
        self, traceability_yaml, test_dir_partial, profile_yaml_with_skip
    ):
        """BR-02 skipped by profile + BR-01 covered → exit 0 despite partial tests."""
        with patch("sys.argv", [
            "check_traceability.py",
            str(traceability_yaml),
            str(test_dir_partial),
            "--profile", str(profile_yaml_with_skip),
        ]):
            rc = ct.main()
        assert rc == 0

    def test_orphans_do_not_affect_exit_code(self, traceability_yaml, test_dir_full, capsys):
        """Extra test in test_dir_full that isn't in traceability → warning, exit 0."""
        extra_test_dir = test_dir_full
        # Add an extra unmapped test to the test dir
        (extra_test_dir / "test_extra.py").write_text("def test_unmapped(): pass\n")
        with patch("sys.argv", [
            "check_traceability.py",
            str(traceability_yaml),
            str(extra_test_dir),
        ]):
            rc = ct.main()
        assert rc == 0
