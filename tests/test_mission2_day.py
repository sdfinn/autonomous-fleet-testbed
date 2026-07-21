# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for tools/mission2_day.py's pure logic (S17 review CR-22): the day
orchestrator is THE stage-4 gate, and its output parsing + retreat detection were
previously untested."""
import subprocess

import pytest

from tools.mission2_day import ExecResult, JetsonExecutor, RetreatDetector, _parse_checklist


def test_parse_checklist_recovers_rows():
    log = """
[INFO] [123] [mission_runner]: [mission2] step 1/5: reference photo
    [  PASS  ] reference photo at home (return-fidelity anchor)
    [REACTION] drive toward the floor marker, watching for balls -> reaction yellow
    [  FAIL  ] reaction yellow completed
noise line that must be ignored
"""
    rows = _parse_checklist(log)
    assert rows == [
        ('reference photo at home (return-fidelity anchor)', 'PASS'),
        ('drive toward the floor marker, watching for balls -> reaction yellow',
         'REACTION'),
        ('reaction yellow completed', 'FAIL'),
    ]


def test_parse_checklist_empty_log():
    assert _parse_checklist('no checklist here\n') == []


def test_retreat_detector_fires_only_after_drop_from_peak():
    det = RetreatDetector(drop_m=0.4)
    assert det.update(None) is False              # no sample yet
    assert det.update((0.0, 1.0)) is False        # outbound, rising y
    assert det.update((0.0, 3.0)) is False        # still rising (peak 3.0)
    assert det.update((0.0, 2.8)) is False        # dipped 0.2 — below threshold
    assert det.update((0.0, 3.5)) is False        # new peak
    assert det.update((0.0, 3.2)) is False        # 0.3 below new peak — not yet
    assert det.update((0.0, 3.05)) is True        # 0.45 below peak — retreating


def test_exec_result_tagged_filters_by_substring():
    r = ExecResult(
        reaction_events=[], checklist=[], ok=True,
        photos=['reports/photos/mission2_home_ref_1.png',
                'reports/photos/mission2_marker_1.png',
                'reports/photos/mission2_home_arrival_1.png'])
    assert r.tagged('mission2_marker') == ['reports/photos/mission2_marker_1.png']
    assert len(r.tagged('mission2_home')) == 2
    assert r.tagged('nope') == []


def test_jetson_executor_bare_metal_skips_image_preflight(monkeypatch):
    """HIL_CONTAINER unset (bare-metal, the default) must never touch docker/SSH."""
    monkeypatch.delenv('HIL_CONTAINER', raising=False)

    def _boom(*a, **k):
        raise AssertionError('subprocess.run must not be called in bare-metal mode')
    monkeypatch.setattr(subprocess, 'run', _boom)

    ex = JetsonExecutor('10.42.0.217', '/tmp/hil_stage')
    assert ex.image is None


def test_jetson_executor_container_mode_passes_when_image_present(monkeypatch):
    monkeypatch.setenv('HIL_CONTAINER', '1')
    monkeypatch.setenv('HIL_IMAGE', 'ghcr.io/sdfinn/autonomous-fleet-testbed:deadbeef')
    monkeypatch.setattr(
        subprocess, 'run',
        lambda *a, **k: subprocess.CompletedProcess(a, returncode=0, stdout='', stderr=''))

    ex = JetsonExecutor('10.42.0.217', '/tmp/hil_stage')
    assert ex.image == 'ghcr.io/sdfinn/autonomous-fleet-testbed:deadbeef'


def test_jetson_executor_container_mode_fails_loud_when_image_missing(monkeypatch):
    monkeypatch.setenv('HIL_CONTAINER', '1')
    monkeypatch.setenv('HIL_IMAGE', 'ghcr.io/sdfinn/autonomous-fleet-testbed:wrongtag')
    monkeypatch.setattr(
        subprocess, 'run',
        lambda *a, **k: subprocess.CompletedProcess(
            a, returncode=1, stdout='', stderr='no such image'))

    with pytest.raises(RuntimeError, match='wrongtag'):
        JetsonExecutor('10.42.0.217', '/tmp/hil_stage')
