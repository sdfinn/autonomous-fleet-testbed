# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for tools/mission2_day.py's pure logic (S17 review CR-22): the day
orchestrator is THE stage-4 gate, and its output parsing + retreat detection were
previously untested."""
import subprocess

import pytest

import re

import tools.mission2_day as mission2_day_module
from tools.mission2_day import (ExecResult, JetsonExecutor, RetreatDetector, _parse_checklist,
                                 hil_variant_names, sweep_orphans)


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


def test_jetson_executor_container_mode_starts_long_lived_container(monkeypatch):
    """Piece 8 fix: container mode must start ONE long-lived container for the whole
    day instead of a fresh `docker run --rm` per scenario (was costing ~15.6-16.1s of
    container start/teardown per transition, measured live 2026-07-23)."""
    monkeypatch.setenv('HIL_CONTAINER', '1')
    monkeypatch.setenv('HIL_IMAGE', 'ghcr.io/sdfinn/autonomous-fleet-testbed:deadbeef')
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, returncode=0, stdout='', stderr='')

    monkeypatch.setattr(subprocess, 'run', fake_run)
    mission2_day_module.JetsonExecutor('10.42.0.217', '/tmp/hil_stage')

    ssh_cmds = [c for c in calls if c[:1] == ['ssh']]
    start_cmd = next(c for c in ssh_cmds if 'docker run -d' in c[-1])
    assert '--name hil_mission2' in start_cmd[-1]
    assert 'sleep infinity' in start_cmd[-1]
    assert 'ghcr.io/sdfinn/autonomous-fleet-testbed:deadbeef' in start_cmd[-1]
    assert '--rm' not in start_cmd[-1]
    rm_index = next(i for i, c in enumerate(ssh_cmds) if 'docker rm -f hil_mission2' in c[-1])
    assert rm_index < ssh_cmds.index(start_cmd)   # stale-container cleanup runs first


def test_close_container_mode_removes_the_container(monkeypatch):
    monkeypatch.setenv('HIL_CONTAINER', '1')
    monkeypatch.setenv('HIL_IMAGE', 'ghcr.io/sdfinn/autonomous-fleet-testbed:deadbeef')
    monkeypatch.setattr(
        subprocess, 'run',
        lambda *a, **k: subprocess.CompletedProcess(a, returncode=0, stdout='', stderr=''))
    ex = JetsonExecutor('10.42.0.217', '/tmp/hil_stage')

    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, returncode=0, stdout='', stderr='')

    monkeypatch.setattr(subprocess, 'run', fake_run)
    ex.close()

    assert any('docker rm -f hil_mission2' in c[-1] for c in calls if c[:1] == ['ssh'])


def test_close_bare_metal_is_a_noop(monkeypatch):
    monkeypatch.delenv('HIL_CONTAINER', raising=False)
    ex = JetsonExecutor('10.42.0.217', '/tmp/hil_stage')

    def _boom(*a, **k):
        raise AssertionError('close() must not touch docker/SSH in bare-metal mode')
    monkeypatch.setattr(subprocess, 'run', _boom)
    ex.close()   # must not raise


def test_ssh_mission2_container_mode_uses_docker_exec(monkeypatch, tmp_path):
    """The per-scenario call must exec into the long-lived container, not `docker run`
    a new one — that's the actual Piece 8 fix (container lifecycle alone isn't enough;
    this is what stops using a fresh container per scenario)."""
    monkeypatch.setenv('HIL_CONTAINER', '1')
    monkeypatch.setenv('HIL_IMAGE', 'ghcr.io/sdfinn/autonomous-fleet-testbed:deadbeef')
    monkeypatch.setattr(
        subprocess, 'run',
        lambda *a, **k: subprocess.CompletedProcess(a, returncode=0, stdout='', stderr=''))
    ex = JetsonExecutor('10.42.0.217', str(tmp_path))

    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, returncode=0, stdout='ok', stderr='')

    monkeypatch.setattr(subprocess, 'run', fake_run)
    ex._ssh_mission2('no_ball')

    ssh_cmd = next(c for c in calls if 'ssh' in c)
    assert 'docker exec hil_mission2' in ssh_cmd[-1]
    assert 'docker run' not in ssh_cmd[-1]
    assert 'python3 -m nav_fleet.mission_runner mission2' in ssh_cmd[-1]


def test_pull_photos_bare_metal_uses_absolute_path_verbatim(monkeypatch, tmp_path):
    """2026-07-22 regression: PHOTO_DIR became absolute (Piece 4 final-review fix), but
    _pull_photos still prepended 'autonomous-fleet-testbed/' assuming a relative path —
    mangling the remote path and failing every scp, 3/3 CI runs. Bare-metal mission_runner
    runs directly as JETSON_USER, so the logged path already IS the real host path."""
    monkeypatch.delenv('HIL_CONTAINER', raising=False)
    monkeypatch.setattr(mission2_day_module, 'PHOTO_DIR', tmp_path)
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, returncode=0, stdout='', stderr='')

    monkeypatch.setattr(subprocess, 'run', fake_run)
    ex = JetsonExecutor('10.42.0.217', '/tmp/hil_stage')
    log_text = 'photo saved: /home/mike/fleet-ci-data/photos/mission2_home_ref_1.png\n'
    ex._pull_photos(log_text)
    scp_cmd = next(c for c in calls if c[0] == 'scp')
    assert scp_cmd[-2] == (
        'mike@10.42.0.217:/home/mike/fleet-ci-data/photos/mission2_home_ref_1.png')


def test_pull_photos_container_mode_translates_root_prefix_to_tilde(monkeypatch, tmp_path):
    """Container mode: mission_runner's absolute path is INSIDE the container (root's
    HOME, per the image's missing USER directive), mapped to JETSON_USER's real home via
    the container-run bind mount — the scp path must be JETSON_USER's home, not root's."""
    monkeypatch.setenv('HIL_CONTAINER', '1')
    monkeypatch.setenv('HIL_IMAGE', 'ghcr.io/sdfinn/autonomous-fleet-testbed:deadbeef')
    monkeypatch.setattr(mission2_day_module, 'PHOTO_DIR', tmp_path)
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, returncode=0, stdout='', stderr='')

    monkeypatch.setattr(subprocess, 'run', fake_run)
    ex = JetsonExecutor('10.42.0.217', '/tmp/hil_stage')
    log_text = 'photo saved: /root/fleet-ci-data/photos/mission2_home_ref_1.png\n'
    ex._pull_photos(log_text)
    scp_cmd = next(c for c in calls if c[0] == 'scp')
    assert scp_cmd[-2] == (
        'mike@10.42.0.217:~/fleet-ci-data/photos/mission2_home_ref_1.png')


def test_pull_failure_bags_scps_the_directory_recursively(monkeypatch, tmp_path):
    """S17 Piece 3: a 'failure bag kept: <path>' log line must scp -r the whole bag
    directory back — a single-file scp (the photo pattern) would silently miss the
    .mcap files inside it."""
    monkeypatch.delenv('HIL_CONTAINER', raising=False)
    monkeypatch.setattr(mission2_day_module, 'FAILURE_BAG_DIR', tmp_path)
    captured = {}

    def fake_run(cmd, **kwargs):
        captured['cmd'] = cmd
        return subprocess.CompletedProcess(cmd, returncode=0, stdout='', stderr='')

    monkeypatch.setattr(subprocess, 'run', fake_run)
    ex = JetsonExecutor('10.42.0.217', '/tmp/hil_stage')
    log_text = 'failure bag kept: reports/failure_bags/mission2_20260721_010203\n'
    ex._pull_failure_bags(log_text)
    assert captured['cmd'][:2] == ['scp', '-r']
    assert captured['cmd'][-2] == (
        'mike@10.42.0.217:autonomous-fleet-testbed/'
        'reports/failure_bags/mission2_20260721_010203')
    assert captured['cmd'][-1] == str(tmp_path / 'mission2_20260721_010203')


def test_pull_failure_bags_no_bag_line_makes_no_scp_call(monkeypatch, tmp_path):
    monkeypatch.delenv('HIL_CONTAINER', raising=False)
    monkeypatch.setattr(mission2_day_module, 'FAILURE_BAG_DIR', tmp_path)

    def _boom(*a, **k):
        raise AssertionError('scp must not be called when no bag was kept')
    monkeypatch.setattr(subprocess, 'run', _boom)

    ex = JetsonExecutor('10.42.0.217', '/tmp/hil_stage')
    ex._pull_failure_bags('mission2: PASS, no failure bag here\n')


def test_no_startup_crash_row_on_clean_exit(monkeypatch):
    """mrc == 0 (script completed normally, whatever the mission result) — never
    synthesize a row; mission_runner.py's own _log_mission already handled it."""
    monkeypatch.delenv('HIL_CONTAINER', raising=False)
    captured = []
    monkeypatch.setattr(mission2_day_module, 'log_run', lambda **kw: captured.append(kw))
    ex = JetsonExecutor('10.42.0.217', '/tmp/hil_stage')
    ex._log_startup_crash_if_needed('Mission mission2: FAIL\n', mrc=0)
    assert captured == []


def test_no_startup_crash_row_when_completion_line_present(monkeypatch):
    """mrc != 0 CAN happen on a normal, handled FAIL (main() does `raise
    SystemExit(0 if ok else 1)`) — the completion print line is the real signal that
    _log_mission already ran, not the exit code alone."""
    monkeypatch.delenv('HIL_CONTAINER', raising=False)
    captured = []
    monkeypatch.setattr(mission2_day_module, 'log_run', lambda **kw: captured.append(kw))
    ex = JetsonExecutor('10.42.0.217', '/tmp/hil_stage')
    ex._log_startup_crash_if_needed('...\nMission mission2: FAIL\n', mrc=1)
    assert captured == []


def test_startup_crash_row_logged_when_process_died_before_completion_line(monkeypatch):
    """mrc != 0 AND no completion line — the process died before _log_mission ever
    ran (e.g. an import-time crash). Synthesize the FAIL row ourselves so the
    workstation DB has SOME record instead of the attempt being invisible."""
    monkeypatch.delenv('HIL_CONTAINER', raising=False)
    captured = []
    monkeypatch.setattr(mission2_day_module, 'log_run', lambda **kw: captured.append(kw))
    ex = JetsonExecutor('10.42.0.217', '/tmp/hil_stage')
    ex._log_startup_crash_if_needed(
        'Traceback (most recent call last):\nModuleNotFoundError: ...\n', mrc=1)
    assert len(captured) == 1
    row = captured[0]
    assert row['scenario'] == 'mission2'
    assert row['result'] == 'FAIL'
    assert row['failure_reason'] == 'startup_crash'
    assert row['runner_type'] == 'hil_jetson'
    assert row['sim_engine'] == 'real'


def test_hil_variant_names_matches_the_declared_pipeline_matrix():
    """Piece 6: run_day's summary loop must iterate the SAME variant names declared in
    config/pipeline_matrix.yaml's hil.scenarios (minus the 'mission2_' prefix), not a
    separately hardcoded tuple that could silently drift out of sync with it."""
    assert hil_variant_names() == ['no_ball', 'yellow', 'red']


def test_sweep_orphans_never_matches_the_gui_viewer_only_process(monkeypatch):
    """Piece 7 (found during a live timed GUI run, 2026-07-22): sweep_orphans() used to
    pkill a bare 'gz sim' pattern, which matches BOTH the headless server ('gz sim -s -r
    world.sdf') AND the separate GUI viewer ('gz sim -g') — killing an observer's viewer
    within seconds of every mission2_day run starting, since launch_stack() sweeps before
    it launches. None of the patterns swept may match a viewer-only cmdline; at least one
    must still match the real server cmdline."""
    patterns = []
    monkeypatch.setattr(
        mission2_day_module.subprocess, 'run',
        lambda cmd, **kw: patterns.append(cmd[cmd.index('-f') + 1]))

    sweep_orphans()

    viewer_cmdline = 'gz sim -g'
    server_cmdline = 'gz sim -s -r /home/mike/autonomous-fleet-testbed/worlds/bedroom_simple.sdf'
    assert not any(re.search(p, viewer_cmdline) for p in patterns)
    assert any(re.search(p, server_cmdline) for p in patterns)
